r"""bmlayout.py - the install layout of Burnout Mashup: moving an older install into layout 2, installing a new version over an
installed one, switching back, and recovering an interrupted change. Python 3.8+, standard library only; Windows x64 (works on
any OS for the tests). Original code (MIT).

Layout 2 (0.2.0 and later, bmpaths.py):  <install>\Burnout Mashup.exe, Burnout Mashup Workbench.exe, gamedata\ (game copy +
mods\user, mods\generated), app\ (the program; app\.update\ = this module's work folder).

Every change is a TRANSACTION of renames (same drive; nothing is copied or deleted while it runs):
  1. the complete list of steps is planned first and written to app\.update\JOURNAL.json;
  2. each step is done and recorded; any error -> the done steps are undone in reverse order (the exact old state);
  3. a crash / power loss -> the next start (the starter exes or the launcher) runs "recover": not committed = undone,
     committed = finished.
What belongs to YOU is carried over by one rule: every file or folder of the old program folder that the old version did not ship
(its SHIPPED_FILES.sha256; for 0.1.0-alpha.1 the published list in legacy\0.1.0-alpha.1.sha256) moves to the same place in the new
one - saves, settings, approvals, progress (launcher\profile), your builds (host-local, host-local.prev), HOST_INFO.json, the
Workbench's settings and data, anything you added. The old shipped files (and the ones you changed) are kept in
app\.update\previous\ (Switch back; the report names changed files). The game copy and your mods go to <install>\gamedata.

    bmapply.py recover [--root INSTALL] [--then launcher|workbench]     finish or undo an interrupted change (the starters run it)
    bmapply.py migrate --root INSTALL                                  move a 0.1.0-alpha.1 folder (around app\) into layout 2
    bmapply.py status --root INSTALL
(app\.update\bmapply.py is a copy of this file, kept outside the folders a change renames.) Exit 0 done, 2 refused (nothing
changed), 3 failed and undone, 4 failed and NOT fully undone (see the journal; never happened in the tests)."""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

APP, EXE, WB_EXE, GAMEDATA, UPDATE = "app", "Burnout Mashup.exe", "Burnout Mashup Workbench.exe", "gamedata", ".update"
EXES = (EXE, WB_EXE)
SHIPPED = "SHIPPED_FILES.sha256"
LEGACY = "0.1.0-alpha.1"
JOURNAL_FORMAT = "bm-layout-journal 1"
RC_OK, RC_REFUSED, RC_FAILED, RC_BROKEN = 0, 2, 3, 4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class LayoutError(Exception):
    def __init__(self, msg, rc=RC_REFUSED):
        super().__init__(msg)
        self.rc = rc


class _Crash(BaseException):
    """test hook: stop like a power loss (no undo)"""


# ------------------------------------------------------------------------------------------------------------------ helpers
def sha_f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def read_sums(p):
    out = {}
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\r\n")
            if len(ln) > 66 and ln[64:66] == "  " and re.match(r"^[0-9a-f]{64}$", ln[:64]):
                out[ln[66:]] = ln[:64]
    return out


def jload(p, default=None):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def jsave(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, indent=1, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def is_reparse(p):
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def is_real_dir(p):
    return os.path.isdir(p) and not is_reparse(p)


def norm(p):
    return os.path.normcase(os.path.abspath(p))


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def legacy_list():
    return read_sums(os.path.join(HERE, "legacy", LEGACY + ".sha256"))


# ------------------------------------------------------------------------------------------------------------------ what is where
def tree_version(tree):
    v = jload(os.path.join(tree, "launcher", "VERSION.json"), {}) or {}
    return v.get("release") if v.get("product") == "BurnoutMashup" else None


def legacy_release(folder):
    """a 0.1.0-alpha.1 program folder in the source layout (launcher\\, host\\, build\\ directly inside; not a git clone) -> its
    version, else None"""
    if not folder or os.path.isdir(os.path.join(folder, ".git")):
        return None
    if not (os.path.isfile(os.path.join(folder, "host", "PINS.json")) and os.path.isfile(os.path.join(folder, "build", "EXPECTED.json"))):
        return None
    v = tree_version(folder)
    return v if v == LEGACY else None


def shipped_of(tree):
    """the files the version in `tree` shipped: {posix path: sha256}"""
    p = os.path.join(tree, SHIPPED)
    if os.path.isfile(p):
        return read_sums(p)
    if tree_version(tree) == LEGACY:
        return legacy_list()
    raise LayoutError("%s has no %s and is not %s: its shipped files are unknown, so your data cannot be told apart (nothing "
                      "changed)" % (tree, SHIPPED, LEGACY))


def install_of(tree):
    """<install> for a layout-2 program folder <install>\\app"""
    return os.path.dirname(os.path.abspath(tree))


def update_dir(install):
    return os.path.join(install, APP, UPDATE)


def journal_path(install):
    return os.path.join(update_dir(install), "JOURNAL.json")


# ------------------------------------------------------------------------------------------------------------------ the transaction
class Txn:
    """a planned list of steps: ("mkdir", path) | ("rename", src, dst); executed with a write-ahead journal"""

    def __init__(self, install, kind, info=None):
        self.install = os.path.abspath(install)
        self.kind, self.info = kind, dict(info or {})
        self.ops, self.made = [], set()
        self.exists_after, self.vacated = set(), set()
        os.makedirs(update_dir(self.install), exist_ok=True)      # the work folder itself is not part of a change (journal, logs)

    # -- planning (nothing changes on disk)
    def _parent(self, path):
        d = os.path.dirname(path)
        chain = []
        while not os.path.isdir(d) and norm(d) not in self.made:
            chain.append(d)
            d = os.path.dirname(d)
        for x in reversed(chain):
            self.ops.append(["mkdir", x])
            self.made.add(norm(x))

    def mkdir(self, path):
        if os.path.isdir(path) or norm(path) in self.made:
            return
        self._parent(path)
        self.ops.append(["mkdir", path])
        self.made.add(norm(path))

    def rename(self, src, dst):
        if self.taken(dst):
            raise LayoutError("internal: planned target exists: %s" % dst, RC_FAILED)
        self._parent(dst)
        self.ops.append(["rename", src, dst])
        self.exists_after.add(norm(dst))
        self.exists_after.discard(norm(src))
        self.vacated.add(norm(src))

    def _vacated(self, p):
        n = norm(p)
        return any(n == v or n.startswith(v + os.sep) for v in self.vacated)

    def taken(self, p):
        """will p exist when this step runs? (on disk and not moved away earlier in the plan, or planned to arrive)"""
        n = norm(p)
        return (os.path.lexists(p) and not self._vacated(p)) or n in self.exists_after or n in self.made

    # -- running
    def run(self, fail_after=None):
        jp = journal_path(self.install)
        if os.path.exists(jp):
            raise LayoutError("an earlier change is not finished (%s): run recover first" % jp)
        j = {"format": JOURNAL_FORMAT, "kind": self.kind, "install": self.install, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
             "state": "running", "done": 0, "ops": self.ops, "info": self.info}
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        _keep_helper(self.install)
        jsave(jp, j)
        crash_after = os.environ.get("BMLAYOUT_TEST_CRASH_AFTER")       # test hooks (launcher tests): a power loss / an error
        if fail_after is None and os.environ.get("BMLAYOUT_TEST_FAIL_AFTER"):
            fail_after = int(os.environ["BMLAYOUT_TEST_FAIL_AFTER"])
        try:
            for i, op in enumerate(self.ops):
                if fail_after is not None and i >= fail_after:
                    raise OSError("test: failure injected before step %d" % (i + 1))
                if crash_after is not None and i >= int(crash_after):
                    raise _Crash()
                if op[0] == "mkdir":
                    os.mkdir(op[1])
                else:
                    os.rename(op[1], op[2])
                j["done"] = i + 1
                jsave(jp, j)
        except _Crash:
            raise
        except BaseException as e:      # noqa: BLE001  (also KeyboardInterrupt: undo, then report)
            left = undo(j)
            j["state"] = "rolledback" if not left else "broken"
            j["error"] = "%s: %s" % (type(e).__name__, e)
            j["undo_left"] = left
            _retire_journal(jp, j)
            if left:
                raise LayoutError("FAILED at step %d (%s) and %d step(s) could not be undone: %s. Nothing is deleted; the journal "
                                  "is kept in %s" % (j["done"] + 1, e, len(left), left[:3], os.path.dirname(jp)), RC_BROKEN)
            raise LayoutError("not done: step %d failed (%s). Everything is as it was before (%d step(s) undone)%s"
                              % (j["done"] + 1, e, j["done"], hint(e)), RC_FAILED)
        j["state"] = "committed"
        jsave(jp, j)
        return j

    def commit_done(self, j):
        _retire_journal(journal_path(self.install), j)


def hint(e):
    if isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33):
        return (". A file is in use: close the game, the Workbench, other Burnout Mashup windows and any Explorer / editor window "
                "showing a file of this folder, then try again")
    return ""


def undo(j):
    """undo the steps 0..done (the one at `done` may or may not have happened) in reverse; -> steps that could not be undone"""
    left = []
    n = min(j["done"] + 1, len(j["ops"]))
    for op in reversed(j["ops"][:n]):
        try:
            if op[0] == "rename":
                src, dst = op[1], op[2]
                if os.path.lexists(dst) and not os.path.lexists(src):
                    os.rename(dst, src)
                elif os.path.lexists(dst) and os.path.lexists(src):
                    left.append(op)
            elif op[0] == "mkdir":
                if os.path.isdir(op[1]):
                    try:
                        os.rmdir(op[1])
                    except OSError:
                        if os.listdir(op[1]):
                            left.append(op)
        except OSError as e:
            left.append(op + ["%s" % e])
    return left


def _retire_journal(jp, j):
    """the journal of a finished change -> app\\.update\\logs\\ (kept for reading)"""
    d = os.path.join(os.path.dirname(jp), "logs")
    os.makedirs(d, exist_ok=True)
    jsave(os.path.join(d, "%s-%s-%s.json" % (stamp(), j["kind"], j["state"])), j)
    try:
        os.remove(jp)
    except OSError:
        pass


def _keep_helper(install):
    """app\\.update\\bmapply.py = this file (+ legacy list): the starters run it to recover even when app\\launcher is renamed away"""
    d = update_dir(install)
    os.makedirs(d, exist_ok=True)
    me = os.path.abspath(__file__)
    dst = os.path.join(d, "bmapply.py")
    if norm(me) != norm(dst):
        shutil.copyfile(me, dst + ".tmp")
        os.replace(dst + ".tmp", dst)
        os.makedirs(os.path.join(d, "legacy"), exist_ok=True)
        lp = os.path.join(HERE, "legacy", LEGACY + ".sha256")
        if os.path.isfile(lp):
            shutil.copyfile(lp, os.path.join(d, "legacy", LEGACY + ".sha256"))


def recover(install, out=print):
    """finish or undo an interrupted change -> None (nothing to do) | "committed" | "rolledback"; raises LayoutError(RC_BROKEN)"""
    jp = journal_path(install)
    j = jload(jp)
    if j is None:
        if os.path.exists(jp):
            raise LayoutError("the journal %s is unreadable: nothing was changed by recover; keep the folder as it is and report it" % jp, RC_BROKEN)
        return None
    if j.get("format") != JOURNAL_FORMAT:
        raise LayoutError("%s is not a %s file" % (jp, JOURNAL_FORMAT), RC_BROKEN)
    if j.get("state") == "committed":
        out("recover: the %s change was complete; finishing it" % j.get("kind"))
        _finish(j)
        _retire_journal(jp, j)
        return "committed"
    out("recover: the %s change was interrupted after step %d of %d; undoing it" % (j.get("kind"), j.get("done", 0), len(j.get("ops", []))))
    left = undo(j)
    j["state"] = "rolledback" if not left else "broken"
    j["undo_left"] = left
    j["recovered"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if left:
        jsave(jp, j)
        raise LayoutError("recover could not undo %d step(s): %s (journal kept: %s)" % (len(left), left[:3], jp), RC_BROKEN)
    _retire_journal(jp, j)
    return "rolledback"


def _finish(j):
    """after a committed change (also from recover): the previous-version pointer, then removal of what was retired"""
    info = j.get("info") or {}
    if info.get("previous"):
        jsave(os.path.join(os.path.join(j["install"], APP, UPDATE), "PREVIOUS.json"), info["previous"])
    for p in info.get("cleanup", []):
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------------------ carrying your data
def plan_carry(txn, old, new, shipped, mapper=None, skip=(), report=None):
    """plan the renames that carry what `old` did not ship into `new` (mapper(rel) -> target path; default new/rel).
    report: dict of lists (moved, archived_changed, conflicts)"""
    mapper = mapper or (lambda rel: os.path.join(new, *rel.split("/")))
    report = report if report is not None else {}
    for k in ("moved", "changed_shipped", "conflicts"):
        report.setdefault(k, [])
    dirs_with_shipped = set()
    for p in shipped:
        parts = p.split("/")
        for i in range(1, len(parts)):
            dirs_with_shipped.add("/".join(parts[:i]))
    skip = {s.lower() for s in skip}

    def walk(rel):
        base = os.path.join(old, *rel.split("/")) if rel else old
        for name in sorted(os.listdir(base)):
            r = (rel + "/" + name) if rel else name
            if r.lower() in skip:
                continue
            src = os.path.join(base, name)
            dst = mapper(r)
            if is_real_dir(src):
                if r not in dirs_with_shipped and not txn.taken(dst):
                    txn.rename(src, dst)
                    report["moved"].append(r + "/")
                elif r not in dirs_with_shipped and os.path.isdir(dst) and not os.listdir(dst) and norm(dst) not in txn.exists_after:
                    walk(r)                       # an empty folder the new version ships / made: fill it
                else:
                    walk(r)
            else:
                if r in shipped:
                    if not is_reparse(src) and sha_f(src) != shipped[r]:
                        report["changed_shipped"].append(r)
                    continue                      # stays with the old version (archived)
                if txn.taken(dst):
                    report["conflicts"].append(r)
                    continue
                txn.rename(src, dst)
                report["moved"].append(r)
    walk("")
    return report


def legacy_mapper(install, new_tree):
    """0.1.0-alpha.1 -> layout 2: launcher\\gamedata\\* -> gamedata\\*, launcher\\mods\\{user,generated,.backup} -> gamedata\\mods\\..."""
    gd = os.path.join(install, GAMEDATA)

    def m(rel):
        low = rel.lower()
        if low == "launcher/gamedata":
            return gd
        if low.startswith("launcher/gamedata/"):
            return os.path.join(gd, *rel.split("/")[2:])
        for k in ("user", "generated", ".backup"):
            if low == "launcher/mods/" + k or low.startswith("launcher/mods/" + k + "/"):
                return os.path.join(gd, "mods", *rel.split("/")[2:])
        return os.path.join(new_tree, *rel.split("/"))
    return m


# ------------------------------------------------------------------------------------------------------------------ A: migrate in place
def find_legacy_beside(install):
    """the 0.1.0-alpha.1 tree around a layout-2 install (the package unzipped INTO the old folder) -> version or None"""
    return legacy_release(install)


def migrate(install, out=print, fail_after=None):
    """move the 0.1.0-alpha.1 program folder that surrounds app\\ into layout 2. -> report dict"""
    install = os.path.abspath(install)
    new = os.path.join(install, APP)
    ver = legacy_release(install)
    if not ver:
        raise LayoutError("%s holds no Burnout Mashup %s folder around app\\: nothing to migrate" % (install, LEGACY))
    if not os.path.isfile(os.path.join(new, "launcher", "tools", "launcher", "bmlauncher.pyw")):
        raise LayoutError("%s is not a complete new program folder: unpack the whole package again" % new)
    if os.path.exists(journal_path(install)):
        raise LayoutError("an earlier change is not finished: run recover first")
    shipped = legacy_list()
    archive = os.path.join(update_dir(install), "versions", "%s-%s" % (ver, stamp()))
    rep = {"from": ver, "install": install, "archive": archive}
    txn = Txn(install, "migrate", {"from": ver, "archive": archive})
    skip = set(EXES) | {APP, GAMEDATA}
    # the game copy: its folder moves as a whole when <install>\gamedata does not hold a game copy yet (the package ships it
    # empty except mods\): its entries are carried one by one by the mapper
    plan_carry(txn, install, new, shipped, legacy_mapper(install, new), skip=skip, report=rep)
    # everything that is left of the old version -> the archive (whole top-level entries)
    left = []
    for name in sorted(os.listdir(install)):
        if name.lower() in {s.lower() for s in skip}:
            continue
        src = os.path.join(install, name)
        if norm(src) in {norm(op[1]) for op in txn.ops if op[0] == "rename"}:
            continue
        left.append(name)
        txn.rename(src, os.path.join(archive, "tree", name))
    rep["archived_entries"] = left
    rep["steps"] = len(txn.ops)
    out("migrating %s -> layout 2: %d step(s), %d item(s) of your data, %d old entries to %s"
        % (install, len(txn.ops), len(rep["moved"]), len(left), archive))
    j = txn.run(fail_after=fail_after)
    post = _post_migrate(install, new, archive, rep)
    j["info"]["post"] = post
    txn.commit_done(j)
    jsave(os.path.join(archive, "MIGRATION_REPORT.json"), rep)
    rep["report_file"] = os.path.join(archive, "MIGRATION_REPORT.json")
    return rep


def _post_migrate(install, new, archive, rep):
    """content fixes after the commit (each original kept in the archive): update-state source folders and Workbench paths"""
    done = []
    keep = os.path.join(archive, "rewritten")
    stp = os.path.join(new, "launcher", "update-state", "STATE.json")
    st = jload(stp)
    if isinstance(st, dict) and any(k in st for k in ("active", "previous", "pending")):
        os.makedirs(keep, exist_ok=True)
        shutil.copyfile(stp, os.path.join(keep, "STATE.json"))
        for k in ("active", "previous", "pending"):
            st.pop(k, None)
        jsave(stp, st)
        done.append("launcher/update-state/STATE.json: the 0.1.0 source-folder entries removed (replay record kept)")
    wb = os.path.join(new, "workbench", "workbench.json")
    c = jload(wb)
    if isinstance(c, dict):
        old_root = norm(install)
        changed = []

        def fix(v):
            if isinstance(v, str) and len(v) > 2 and (norm(v) == old_root or norm(v).startswith(old_root + os.sep)):
                rel = os.path.relpath(os.path.abspath(v), install)
                first = rel.split(os.sep)[0].lower()
                if first not in {e.lower() for e in EXES} | {APP, GAMEDATA}:
                    nv = new if rel == "." else os.path.normpath(legacy_mapper(install, new)(rel.replace(os.sep, "/")))
                    changed.append((v, nv))
                    return nv
            if isinstance(v, dict):
                return {k: fix(x) for k, x in v.items()}
            if isinstance(v, list):
                return [fix(x) for x in v]
            return v
        c2 = fix(c)
        if changed:
            os.makedirs(keep, exist_ok=True)
            shutil.copyfile(wb, os.path.join(keep, "workbench.json"))
            jsave(wb, c2)
            done.append("workbench/workbench.json: %d path(s) moved with the folder" % len(changed))
    gd = os.path.join(install, GAMEDATA, "mods")
    for k in ("user", "generated"):
        os.makedirs(os.path.join(gd, k), exist_ok=True)
    rep["post"] = done
    return done


# ------------------------------------------------------------------------------------------------------------------ B: copy from an old folder
def import_copy(old, launcher, out=print, fail_after=None):
    """copy your data from a 0.1.0-alpha.1 folder `old` (only read) into this install (layout 2 or 1) by the same map; every file
    copied is compared by sha256; the copy is staged in app\\.update\\import-*, then moved into place as one transaction"""
    import bmpaths
    old = os.path.abspath(old)
    ver = legacy_release(old)
    if not ver:
        raise LayoutError("%s is not a Burnout Mashup %s folder" % (old, LEGACY))
    tree = bmpaths.tree_root(launcher)
    inst = bmpaths.install_root(launcher)
    if inst is None:
        raise LayoutError("importing a 0.1.0-alpha.1 folder needs the Windows package layout (Burnout Mashup.exe beside app\\)")
    if norm(old) in (norm(inst), norm(tree)):
        raise LayoutError("that is this folder itself: migration in place happens automatically at start")
    prof = os.path.join(tree, "launcher", "profile")
    if os.path.isdir(prof) and os.listdir(prof):
        raise LayoutError("this install already has a profile (launcher\\profile): it is never overwritten; import into a fresh install")
    shipped = legacy_list()
    stage = os.path.join(update_dir(inst), "import-" + stamp())
    m = legacy_mapper(inst, tree)
    # 1. copy (read only from old) into the stage, mirrored by target path relative to the install
    plan = Txn(inst, "import-plan")
    rep = {"from": ver, "old": old, "moved": [], "changed_shipped": [], "conflicts": []}
    plan_carry(plan, old, tree, shipped, m, skip=set(EXES) | {APP, GAMEDATA}, report=rep)
    pairs = [(op[1], op[2]) for op in plan.ops if op[0] == "rename"]
    n = 0
    try:
        for src, dst in pairs:
            rel = os.path.relpath(dst, inst)
            sdst = os.path.join(stage, rel)
            if is_real_dir(src):
                shutil.copytree(src, sdst, symlinks=True)
            else:
                os.makedirs(os.path.dirname(sdst), exist_ok=True)
                shutil.copy2(src, sdst, follow_symlinks=False)
        for src, dst in pairs:
            sdst = os.path.join(stage, os.path.relpath(dst, inst))
            for a, b in (_files(src, sdst)):
                if not is_reparse(a) and sha_f(a) != sha_f(b):
                    raise LayoutError("copy check failed: %s" % b, RC_FAILED)
                n += 1
    except (OSError, shutil.Error) as e:
        shutil.rmtree(stage, ignore_errors=True)
        raise LayoutError("the copy failed (%s): nothing in this install was changed; the old folder was only read" % e, RC_FAILED)
    # 2. move the staged copies into place (one transaction)
    txn = Txn(inst, "import", {"from": old, "cleanup": [stage]})
    for src, dst in pairs:
        txn.rename(os.path.join(stage, os.path.relpath(dst, inst)), dst)
    try:
        j = txn.run(fail_after=fail_after)
    except LayoutError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    _finish(j)
    txn.commit_done(j)
    for k in ("user", "generated"):
        os.makedirs(bmpaths.mods_dir(launcher, k), exist_ok=True)
    rep["files_copied"] = n
    return rep


def _files(a, b):
    if is_real_dir(a):
        for dp, dn, fn in os.walk(a):
            for f in fn:
                s = os.path.join(dp, f)
                yield s, os.path.join(b, os.path.relpath(s, a))
    else:
        yield a, b


def import_main(old, launcher):
    """remove.cmd upgrade --from <0.1.0-alpha.1 folder> / the launcher's 'Bring my data ...' (printing variant)"""
    try:
        r = import_copy(old, launcher)
    except LayoutError as e:
        print("REFUSED: %s" % e)
        return 3
    print("OK: %d file(s) of your data copied from %s and checked (%d item(s)); the old folder was only read (delete it yourself "
          "when this one works)" % (r["files_copied"], old, len(r["moved"])))
    for c in r["conflicts"]:
        print("  not copied (this install ships a file with that name): %s" % c)
    return 0


# ------------------------------------------------------------------------------------------------------------------ updates (layout 2)
def versions_dir(install):
    return os.path.join(update_dir(install), "versions")


def previous_of(install):
    """the kept previous version -> {"path", "version", ...} or None (app\\.update\\PREVIOUS.json points at versions\\<v>-<time>)"""
    p = jload(os.path.join(update_dir(install), "PREVIOUS.json"))
    if isinstance(p, dict) and p.get("path") and os.path.isfile(os.path.join(p["path"], "app", "launcher", "VERSION.json")):
        return p
    return None


def apply_update(install, stage_app, stage_exes, version, out=print, fail_after=None, kind="update", extra_cleanup=()):
    """install the verified program folder `stage_app` (+ the exes in `stage_exes`) over <install>\\app: your data carried over,
    the version in use kept as app\\.update\\versions\\<version>-<time> (PREVIOUS.json points at it: Switch back). -> report"""
    install = os.path.abspath(install)
    app = os.path.join(install, APP)
    if os.path.exists(journal_path(install)):
        raise LayoutError("an earlier change is not finished: run recover first")
    shipped = shipped_of(app)
    cur = tree_version(app)
    old_prev = previous_of(install)
    keep = os.path.join(versions_dir(install), "%s-%s" % (cur, stamp()))
    while os.path.lexists(keep):
        keep += "x"
    rep = {"from": cur, "to": version, "install": install, "kept_as": keep}
    cleanup = list(extra_cleanup)
    if kind == "update" and old_prev and norm(old_prev["path"]) != norm(os.path.dirname(stage_app)):
        cleanup.append(old_prev["path"])          # the version before the previous one: removed after the commit
    pointer = {"path": keep, "version": cur, "kept": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind}
    txn = Txn(install, kind, {"from": cur, "to": version, "cleanup": cleanup, "previous": pointer})
    plan_carry(txn, app, stage_app, shipped, skip={UPDATE}, report=rep)
    moved_src = {norm(op[1]) for op in txn.ops if op[0] == "rename"}
    for name in sorted(os.listdir(app)):
        if name.lower() == UPDATE or norm(os.path.join(app, name)) in moved_src:
            continue
        txn.rename(os.path.join(app, name), os.path.join(keep, "app", name))
    arriving = set(os.listdir(stage_app)) | {os.path.basename(op[2]) for op in txn.ops
                                              if op[0] == "rename" and norm(os.path.dirname(op[2])) == norm(stage_app)}
    for name in sorted(arriving):
        txn.rename(os.path.join(stage_app, name), os.path.join(app, name))
    for e in EXES:
        if os.path.lexists(os.path.join(install, e)):
            txn.rename(os.path.join(install, e), os.path.join(keep, "exe", e))
        if os.path.isfile(os.path.join(stage_exes, e)):
            txn.rename(os.path.join(stage_exes, e), os.path.join(install, e))
    rep["steps"] = len(txn.ops)
    out("installing %s over %s: %d step(s), %d item(s) of your data carried over" % (version, cur, len(txn.ops), len(rep["moved"])))
    j = txn.run(fail_after=fail_after)
    _finish(j)
    txn.commit_done(j)
    return rep


def switch_back(install, out=print, fail_after=None):
    """the previous version becomes the one in use; the current one becomes the previous one (pressed again = forward)"""
    install = os.path.abspath(install)
    p = previous_of(install)
    if not p:
        raise LayoutError("there is no previous version (app\\.update\\PREVIOUS.json) to switch back to")
    sa = os.path.join(p["path"], "app")
    return apply_update(install, sa, os.path.join(p["path"], "exe"), tree_version(sa), out=out, fail_after=fail_after,
                        kind="switch", extra_cleanup=[p["path"]])


# ------------------------------------------------------------------------------------------------------------------ start-up (launcher)
def startup(launcher, out=print):
    """run by the launcher at start: recover an interrupted change, then migrate a 0.1.0-alpha.1 folder around app\\.
    -> {"recovered": ..., "migrated": report or None, "error": text or None}"""
    import bmpaths
    inst = bmpaths.install_root(launcher)
    res = {"recovered": None, "migrated": None, "error": None}
    if not inst:
        return res
    try:
        res["recovered"] = recover(inst, out=out)
        if legacy_release(inst):
            res["migrated"] = migrate(inst, out=out)
    except LayoutError as e:
        res["error"] = str(e)
        res["rc"] = e.rc
    return res


# ------------------------------------------------------------------------------------------------------------------ CLI (bmapply.py)
def _start(install, what):
    tgt = {"launcher": os.path.join(install, APP, "launcher", "tools", "launcher", "bmlauncher.pyw"),
           "workbench": os.path.join(install, APP, "workbench", "workbench.py")}.get(what)
    if tgt and os.path.isfile(tgt):
        exe = sys.executable
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        subprocess.Popen([w if os.path.isfile(w) else exe, tgt], cwd=install, close_fds=True)


def default_install():
    """bmapply.py in <install>\\app\\.update -> <install>; bmlayout.py in <install>\\app\\launcher\\tools\\launcher -> <install>"""
    if os.path.basename(HERE).lower() == UPDATE:
        return os.path.dirname(os.path.dirname(HERE))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "help"
    opt = {}
    i = 1
    while i < len(argv):
        if argv[i] in ("--root", "--then") and i + 1 < len(argv):
            opt[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            print("usage: unknown argument %s" % argv[i])
            return 1
    install = os.path.abspath(opt["root"]) if opt.get("root") else default_install()
    try:
        if cmd == "recover":
            r = recover(install)
            print(json.dumps({"ok": True, "recover": r}))
            if opt.get("then"):
                _start(install, opt["then"])
            return RC_OK
        if cmd == "migrate":
            r = migrate(install)
            print(json.dumps({"ok": True, "moved": len(r["moved"]), "archive": r["archive"], "report": r.get("report_file")}))
            return RC_OK
        if cmd == "status":
            j = jload(journal_path(install))
            print(json.dumps({"install": install, "journal": (j or {}).get("state"), "legacy_beside": legacy_release(install),
                              "version": tree_version(os.path.join(install, APP)), "previous": previous_of(install)}))
            return RC_OK
    except LayoutError as e:
        print(json.dumps({"ok": False, "rc": e.rc, "message": str(e)}))
        return e.rc
    print(__doc__)
    return RC_OK if cmd in ("help", "-h", "--help") else 1


if __name__ == "__main__":
    sys.exit(main())
