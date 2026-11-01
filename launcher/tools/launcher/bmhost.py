"""bmhost.py - the host program the launcher starts: host-local\\ (written ONLY by BUILD MASHUP), the Play rule, the atomic install and
"switch back to the previous build". Python 3.8+, standard library. Original code (MIT).

host-local\\            the build in use: BurnoutMashup.exe, SDL2.dll, shaders\\, licenses\\, HOST_INFO.json, BUILD_RESULT.json
host-local.prev\\       the previous working build (kept by every install; "switch back" swaps the two)
host-local.new\\        an install being staged (never used; removed by the next install)
<repository>\\HOST_INFO.json   the same HOST_INFO.json for the Workbench (the kit root), written after host-local\\ is in place
update-state\\STATE.json  (only after an update, tools/launcher/bmupdate.py) the source folder host-local was built from and the previous
                       one; "switch back" swaps them together with the builds

Play rule (play_state): Play is enabled only when host-local\\ holds BurnoutMashup.exe, its HOST_INFO.json and BUILD_RESULT.json, and
they agree: the exe's sha256 = HOST_INFO.json exe_sha256 = BUILD_RESULT.json sha256, the build identity read from the exe's bytes =
HOST_INFO.json identity (exactly one identity string in the exe), BUILD_RESULT.json says verified (verify.py: identical to the reference
build of EXPECTED.json), and - inside a source checkout - the repository's HOST_INFO.json is byte-identical to host-local's. The
game itself is never started here. A prebuilt host\\ folder (private tester packages only) is accepted under the same consistency rule
(exe sha256 = its HOST_INFO.json)."""
import hashlib
import json
import os
import re
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.dirname(os.path.dirname(HERE))
EXE = "BurnoutMashup.exe"
LEGACY_EXE = "burnout3_bmashup.exe"                    # the private tester packages' prebuilt host\
HOST_FILES = (EXE, "SDL2.dll", "shaders", "licenses", "HOST_INFO.json", "BUILD_RESULT.json")
IDENT_RE = re.compile(rb"bmp-[0-9]+\.[0-9]+\.[0-9]+\+[0-9a-f]{12}")


class InstallError(Exception):
    pass


def is_source(d):
    """a Burnout Mashup source checkout: has host/PINS.json and build/verify.py"""
    return bool(d) and os.path.isfile(os.path.join(d, "host", "PINS.json")) and os.path.isfile(os.path.join(d, "build", "verify.py"))


def repo_root(launcher=LAUNCHER):
    """the source checkout around the launcher (has host/PINS.json and build/verify.py), else None (a copied launcher folder)"""
    up = os.path.dirname(os.path.abspath(launcher))
    return up if is_source(up) else None


# ---- the update state (launcher\update-state\STATE.json, written by tools/launcher/bmupdate.py): which source folder the build in
# host-local was made from ("active") and the one before it ("previous"). Without it the source is the checkout around the launcher.
UPDATE_STATE = os.path.join("update-state", "STATE.json")


def load_update_state(launcher=LAUNCHER):
    st = _jload(os.path.join(launcher, UPDATE_STATE))
    return st if isinstance(st, dict) and st.get("format") == "bm-update-state 1" else {"format": "bm-update-state 1"}


def save_update_state(launcher, st):
    p = os.path.join(launcher, UPDATE_STATE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    st["format"] = "bm-update-state 1"
    _atomic_write(p, (json.dumps(st, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def active_source(launcher=LAUNCHER):
    """the source checkout BUILD MASHUP builds from: the updater's active source when it is recorded and still a source, else the
    checkout around the launcher (None for a copied launcher folder)"""
    a = (load_update_state(launcher).get("active") or {}).get("source")
    return os.path.abspath(a) if a and is_source(a) else repo_root(launcher)


def swap_sources(launcher=LAUNCHER):
    """the recorded active <-> previous source (the updater's 'switch back' when both versions have the same host program)"""
    st = load_update_state(launcher)
    if st.get("active") and st.get("previous"):
        st["active"], st["previous"] = st["previous"], st["active"]
        save_update_state(launcher, st)
        return True
    return False


def _follow_sources(launcher, now_sha):
    """after a build swap: the recorded sources follow when the build now in use is the previous version's build"""
    st = load_update_state(launcher)
    a, b = st.get("active") or {}, st.get("previous") or {}
    if a and b and b.get("host_sha256") == now_sha and a.get("host_sha256") != now_sha:
        swap_sources(launcher)


def sha_f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _jload(p):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def exe_name(folder):
    for n in (EXE, LEGACY_EXE):
        if os.path.isfile(os.path.join(folder, n)):
            return n
    return None


def folder_state(folder, require_build_result=True):
    """-> {ok, problems, exe, sha256, identity, profile}: does this host folder hold a consistent, verified build?"""
    st = {"folder": folder, "ok": False, "problems": []}
    n = exe_name(folder) if os.path.isdir(folder) else None
    if not n:
        st["problems"].append("no host program in %s (Build Mashup first)" % folder)
        return st
    exe = os.path.join(folder, n)
    st["exe"] = exe
    info = _jload(os.path.join(folder, "HOST_INFO.json"))
    if not info:
        st["problems"].append("HOST_INFO.json is missing or unreadable beside %s" % n)
        return st
    try:
        data_sha = sha_f(exe)
        with open(exe, "rb") as f:
            ids = sorted({m.decode("ascii") for m in IDENT_RE.findall(f.read())})
    except OSError as e:
        st["problems"].append("the host program cannot be read: %s" % e)
        return st
    st.update(sha256=data_sha, identity=info.get("identity"), profile=info.get("profile", "dev"))
    if info.get("exe_sha256") != data_sha:
        st["problems"].append("the host program is not the one HOST_INFO.json describes (sha256 differs)")
    if ids != [info.get("identity")]:
        st["problems"].append("the build identity inside the program (%s) is not HOST_INFO.json's (%s)" % (", ".join(ids) or "none", info.get("identity")))
    if require_build_result:
        br = _jload(os.path.join(folder, "BUILD_RESULT.json"))
        if not br:
            st["problems"].append("BUILD_RESULT.json is missing: this host was not installed by Build Mashup")
        else:
            if br.get("sha256") != data_sha:
                st["problems"].append("BUILD_RESULT.json describes another program (sha256 differs)")
            if not br.get("verified"):
                st["problems"].append("the build is not verified (BUILD_RESULT.json)")
    st["ok"] = not st["problems"]
    return st


def play_state(launcher=LAUNCHER):
    """the Play rule -> {host_ok, host_kind, problems, data_ok, play, ...}"""
    loc = os.path.join(launcher, "host-local")
    pre = os.path.join(launcher, "host")
    out = {"host_ok": False, "host_kind": None, "problems": []}
    if exe_name(loc):
        st = folder_state(loc)
        out.update(host_kind="your build (host-local)", state=st)
        probs = list(st["problems"])
        rr = repo_root(launcher)
        if st["ok"] and rr:
            a, b = os.path.join(loc, "HOST_INFO.json"), os.path.join(rr, "HOST_INFO.json")
            if not os.path.isfile(b) or sha_f(a) != sha_f(b):
                probs.append("the repository's HOST_INFO.json (for the Workbench) is not the one of host-local (run Build Mashup again: it "
                             "repairs the install step only)")
        out["problems"] = probs
        out["host_ok"] = not probs
    elif exe_name(pre):
        st = folder_state(pre, require_build_result=False)
        out.update(host_kind="prebuilt (host)", state=st, problems=st["problems"], host_ok=st["ok"])
    else:
        out["problems"] = ["no host built yet: Build Mashup first"]
    import bmpaths
    out["data_ok"] = os.path.isfile(os.path.join(bmpaths.gamedata(launcher), ".complete"))
    out["play"] = out["host_ok"] and out["data_ok"]
    return out


# ------------------------------------------------------------------------------------------------------------------ install
def _rename(a, b, tries=5):
    for i in range(tries):
        try:
            os.rename(a, b)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.4)


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def install(stage_src, launcher=LAUNCHER, fault=None, log=print):
    """install a verified build atomically. stage_src = folder with HOST_FILES (BurnoutMashup.exe ... BUILD_RESULT.json).
    host-local.new <- copy + re-verify; then host-local -> host-local.prev, host-local.new -> host-local; any failure restores the previous
    state. fault (tests only): name of a point at which to raise ("copy", "verify", "swap", "repo")."""
    loc = os.path.join(launcher, "host-local")
    new, prev, old = loc + ".new", loc + ".prev", loc + ".old"
    for d in (new, old):
        if os.path.exists(d):
            shutil.rmtree(d)
    os.makedirs(new)
    for n in HOST_FILES:
        s = os.path.join(stage_src, n)
        if not os.path.exists(s):
            shutil.rmtree(new, ignore_errors=True)
            raise InstallError("the build output lacks %s" % n)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, os.path.join(new, n))
    if fault == "copy":
        shutil.rmtree(new, ignore_errors=True)
        raise InstallError("test fault after the copy")
    st = folder_state(new)
    if not st["ok"] or fault == "verify":
        shutil.rmtree(new, ignore_errors=True)
        raise InstallError("the staged install does not verify: %s" % "; ".join(st["problems"] or ["test fault"]))
    had_loc, had_prev = os.path.isdir(loc), os.path.isdir(prev)
    steps = []
    try:
        if had_loc:
            if had_prev:
                _rename(prev, old)
                steps.append((old, prev))
            _rename(loc, prev)
            steps.append((prev, loc))
        if fault == "swap":
            raise InstallError("test fault during the swap")
        _rename(new, loc)
        steps.append((loc, new))
        rr = repo_root(launcher)
        if rr:
            if fault == "repo":
                raise InstallError("test fault while writing the repository's HOST_INFO.json")
            _atomic_write(os.path.join(rr, "HOST_INFO.json"), open(os.path.join(loc, "HOST_INFO.json"), "rb").read())
    except BaseException as e:
        for a, b in reversed(steps):             # undo: every rename back
            try:
                _rename(a, b)
            except OSError:
                pass
        shutil.rmtree(new, ignore_errors=True)
        rr = repo_root(launcher)
        if rr and os.path.isdir(loc):            # the repository copy follows the restored build
            try:
                _atomic_write(os.path.join(rr, "HOST_INFO.json"), open(os.path.join(loc, "HOST_INFO.json"), "rb").read())
            except OSError:
                pass
        if isinstance(e, PermissionError):
            raise InstallError("host-local is in use (is the game running from it?): close it and run Build Mashup again; the previous build "
                               "is unchanged")
        raise
    if os.path.isdir(old):
        shutil.rmtree(old, ignore_errors=True)
    log("installed into %s (previous build kept in %s)" % (loc, prev if had_loc else "-"))
    return {"installed": loc, "previous": prev if had_loc else None, "sha256": st["sha256"], "identity": st["identity"]}


def switch_back(launcher=LAUNCHER, log=print):
    """swap host-local and host-local.prev (both must hold consistent builds); the repository's HOST_INFO.json follows"""
    loc = os.path.join(launcher, "host-local")
    prev, tmp = loc + ".prev", loc + ".swap"
    if not os.path.isdir(prev):
        raise InstallError("there is no previous build (host-local.prev): nothing to switch back to")
    st = folder_state(prev)
    if not st["ok"]:
        raise InstallError("the previous build does not verify (%s): not switched" % "; ".join(st["problems"]))
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    done = []
    try:
        if os.path.isdir(loc):
            _rename(loc, tmp)
            done.append((tmp, loc))
        _rename(prev, loc)
        done.append((loc, prev))
        if os.path.isdir(tmp):
            _rename(tmp, prev)
            done.append((prev, tmp))
        rr = repo_root(launcher)
        if rr:
            _atomic_write(os.path.join(rr, "HOST_INFO.json"), open(os.path.join(loc, "HOST_INFO.json"), "rb").read())
    except BaseException:
        for a, b in reversed(done):
            try:
                _rename(a, b)
            except OSError:
                pass
        raise
    _follow_sources(launcher, st["sha256"])
    log("switched: host-local now holds %s (the other build is in host-local.prev)" % st["identity"])
    return {"now": st["identity"], "sha256": st["sha256"]}
