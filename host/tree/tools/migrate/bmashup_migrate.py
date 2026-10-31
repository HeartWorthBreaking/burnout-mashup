"""bmashup_migrate.py - bring Takedawn saves and settings over to Burnout Mashup: an explicit, optional, reversible COPY.

Burnout Mashup keeps its own folders (Windows: %APPDATA%\\BurnoutMashup, %LOCALAPPDATA%\\BurnoutMashup) and never reads, moves
or writes the Takedawn ones. This tool copies - never moves, never overwrites - the files of a Takedawn save root into an EMPTY
Burnout Mashup save root and writes a manifest, so the copy can be undone exactly.

    py -3 bmashup_migrate.py plan   [--from takedawn|burnout3] [--src DIR] [--dest DIR] [--no-approvals] [--game-data]
    py -3 bmashup_migrate.py apply  [same options]          copies; writes <dest>/migrate-manifest-<stamp>.json
    py -3 bmashup_migrate.py revert --manifest FILE         deletes ONLY the files it copied whose sha256 is unchanged
Options:
    --from      takedawn (default: %APPDATA%\\Takedawn) or burnout3 (%APPDATA%\\Burnout3, the port's earlier name)
    --src/--dest   explicit folders instead of the per-user defaults (the defaults follow the host: APPDATA / LOCALAPPDATA on
                Windows, ~/Library/Application Support on macOS, $XDG_DATA_HOME or ~/.local/share lower-cased on Linux)
    --no-approvals  leave plugin-approvals.toml out (plugins then ask to be approved again in Burnout Mashup)
    --game-data write <local dest>/data-folder.txt naming the existing Takedawn game data root (read only, nothing copied)
    --json      one JSON line instead of text
What is copied: everything in the save root (the game saves UDATA / TDATA, settings.toml, mod-list.toml, plugin-approvals.toml,
mixer.toml, plugin-settings.toml, ...) EXCEPT logs/, crash/, cache/, backup/, save-before-import/, the instance lock and
migrate manifests. plugin-approvals.toml is copied as is: an approval binds the plugin's exact bytes, so the copy grants exactly
what was granted before (use --no-approvals to start without approvals).
Refusals (exit 2, nothing written): the game is running on the source or destination (instance.lock held), the destination save
root holds any file (the Workbench's own workbench/ sub-folder is ignored), a destination file exists, a source file changes
during the copy (the copied files are removed again). Exit 0 ok, 1 revert kept changed files, 2 refused. Standard library only."""
import hashlib
import json
import os
import shutil
import sys
import time

TOOL = "bmashup_migrate 1.0 (pfid1)"
EXCLUDE_DIRS = {"logs", "crash", "cache", "backup", "save-before-import", "__pycache__"}
EXCLUDE_FILES = {"instance.lock"}
APPROVALS = "plugin-approvals.toml"
IGNORE_IN_DEST = {"workbench"}         # Burnout Mashup Workbench's own folder (%APPDATA%\BurnoutMashup\workbench)
NAMES = {"takedawn": "Takedawn", "burnout3": "Burnout3", "mashup": "BurnoutMashup"}


class Refused(Exception):
    pass


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def user_dir(kind, name):
    """the host's per-user folder (toolkit recomp_save_dir.c): kind 'data' (saves) or 'local' (game data root)"""
    if os.name == "nt":
        base = os.environ.get("APPDATA" if kind == "data" else "LOCALAPPDATA")
        if not base:
            raise Refused("%s is not set" % ("APPDATA" if kind == "data" else "LOCALAPPDATA"))
        return os.path.join(base, name)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), name)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, name.lower())


def lock_held(root):
    """True when a running game holds <root>/instance.lock (Windows: opened without sharing; POSIX: flock)"""
    p = os.path.join(root, "instance.lock")
    if not os.path.isfile(p):
        return False
    if os.name == "nt":
        try:
            with open(p, "rb"):
                return False
        except PermissionError:
            return True
    import fcntl
    with open(p, "rb") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
        except OSError:
            return True


def files_of(src, approvals=True):
    out = []
    for dp, dn, fn in os.walk(src):
        rel_dir = os.path.relpath(dp, src)
        if rel_dir == ".":
            dn[:] = sorted(d for d in dn if d not in EXCLUDE_DIRS)
        else:
            dn[:] = sorted(d for d in dn if d != "__pycache__")
        for f in sorted(fn):
            rel = os.path.normpath(os.path.join(rel_dir, f)) if rel_dir != "." else f
            if rel_dir == ".":
                if f in EXCLUDE_FILES or (f.startswith("migrate-manifest-") and f.endswith(".json")):
                    continue
                if f == APPROVALS and not approvals:
                    continue
            out.append(rel.replace(os.sep, "/"))
    return out


def dest_has_files(dest):
    if not os.path.isdir(dest):
        return []
    found = []
    for dp, dn, fn in os.walk(dest):
        if os.path.relpath(dp, dest) == ".":
            dn[:] = [d for d in dn if d not in IGNORE_IN_DEST]
        found += [os.path.relpath(os.path.join(dp, f), dest) for f in fn]
    return found


def takedawn_game_root(src_name):
    """the existing game data root of the source install: its data-folder.txt's first line, else <local>/<name>/Game"""
    local = user_dir("local", src_name)
    loc = os.path.join(local, "data-folder.txt")
    if os.path.isfile(loc):
        first = open(loc, encoding="utf-8", errors="replace").readline().strip()
        if first:
            return first
    return os.path.join(local, "Game")


def make_plan(a):
    src = os.path.abspath(a["src"] or user_dir("data", NAMES[a["from"]]))
    dest = os.path.abspath(a["dest"] or user_dir("data", NAMES["mashup"]))
    if os.path.normcase(src) == os.path.normcase(dest):
        raise Refused("source and destination are the same folder")
    if not os.path.isdir(src):
        raise Refused("no %s save folder at %s: nothing to copy" % (NAMES[a["from"]], src))
    if lock_held(src):
        raise Refused("the game is running with %s (instance.lock is held): close it first" % src)
    if lock_held(dest):
        raise Refused("Burnout Mashup is running with %s: close it first" % dest)
    there = dest_has_files(dest)
    if there:
        raise Refused("the Burnout Mashup save folder %s is not empty (%d file(s), e.g. %s): nothing is overwritten, ever. "
                      "Revert an earlier copy or move those files away first" % (dest, len(there), there[0]))
    rows = []
    for rel in files_of(src, a["approvals"]):
        p = os.path.join(src, *rel.split("/"))
        rows.append({"rel": rel, "src": p, "dest": os.path.join(dest, *rel.split("/")), "size": os.path.getsize(p), "sha256": sha(p)})
    game = None
    if a["game_data"]:
        local_dest = os.path.abspath(a["local_dest"] or user_dir("local", NAMES["mashup"]))
        target = os.path.join(local_dest, "data-folder.txt")
        if os.path.exists(target):
            raise Refused("%s exists: nothing is overwritten" % target)
        game = {"file": target, "points_at": a["game_root"] or takedawn_game_root(NAMES[a["from"]])}
    return {"tool": TOOL, "from": a["from"], "src": src, "dest": dest, "files": rows, "approvals_copied": a["approvals"]
            and any(r["rel"] == APPROVALS for r in rows), "game_data": game}


def print_plan(p, as_json):
    if as_json:
        print(json.dumps({"plan": p}))
        return
    print("%s: copy (never move) %d file(s), %d bytes" % (TOOL, len(p["files"]), sum(r["size"] for r in p["files"])))
    print("  from %s\n  to   %s" % (p["src"], p["dest"]))
    for r in p["files"]:
        print("  %s  %10d  %s" % (r["sha256"][:12], r["size"], r["rel"]))
    if p["approvals_copied"]:
        print("  NOTE: plugin-approvals.toml is copied as is: the same plugin bytes stay approved (--no-approvals to leave it out)")
    if p["game_data"]:
        print("  game data: %s will name %s (read only; nothing copied)" % (p["game_data"]["file"], p["game_data"]["points_at"]))
    print("  Not copied: logs, crash reports, caches, backups. The source folder is never changed.")


def apply(a):
    p = make_plan(a)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    manifest = os.path.join(p["dest"], "migrate-manifest-%s.json" % stamp)
    made_dirs, copied = [], []

    def mkdirs(d):
        todo = []
        while not os.path.isdir(d):
            todo.append(d)
            d = os.path.dirname(d)
        for x in reversed(todo):
            os.mkdir(x)
            made_dirs.append(x)

    try:
        mkdirs(p["dest"])
        for r in p["files"]:
            if os.path.exists(r["dest"]):
                raise Refused("%s exists: nothing is overwritten" % r["dest"])
            mkdirs(os.path.dirname(r["dest"]))
            shutil.copy2(r["src"], r["dest"])
            copied.append(r["dest"])
            if sha(r["dest"]) != r["sha256"]:
                raise Refused("copy of %s does not match its source" % r["rel"])
        for r in p["files"]:     # the source must be unchanged after the copy (the game was not writing it)
            if sha(r["src"]) != r["sha256"]:
                raise Refused("%s changed during the copy: the copy is undone, try again with the game closed" % r["src"])
        written = []
        if p["game_data"]:
            g = p["game_data"]
            mkdirs(os.path.dirname(g["file"]))
            with open(g["file"], "x", encoding="utf-8", newline="\n") as f:
                f.write(g["points_at"] + "\n# Written by %s: Burnout Mashup uses the Takedawn game data here (read only).\n" % TOOL)
            copied.append(g["file"])
            written.append({"dest": g["file"], "sha256": sha(g["file"]), "points_at": g["points_at"]})
    except BaseException:
        for f in reversed(copied):
            if os.path.isfile(f):
                os.remove(f)
        for d in sorted(made_dirs, key=len, reverse=True):
            try:
                os.rmdir(d)
            except OSError:
                pass
        raise
    rec = {"tool": TOOL, "stamp": stamp, "from": p["from"], "src": p["src"], "dest": p["dest"],
           "files": [{"rel": r["rel"], "src": r["src"], "dest": r["dest"], "size": r["size"], "sha256": r["sha256"]} for r in p["files"]],
           "written": written, "created_dirs": made_dirs, "approvals_copied": p["approvals_copied"]}
    with open(manifest, "x", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, indent=1) + "\n")
    return rec, manifest


def revert(manifest):
    rec = json.load(open(manifest, encoding="utf-8"))
    if not str(rec.get("tool", "")).startswith("bmashup_migrate"):
        raise Refused("%s is not a bmashup_migrate manifest" % manifest)
    if lock_held(rec["dest"]):
        raise Refused("Burnout Mashup is running with %s: close it first" % rec["dest"])
    removed, kept, missing = [], [], []
    for r in rec["files"] + rec.get("written", []):
        d = r["dest"]
        if not os.path.isfile(d):
            missing.append(d)
        elif sha(d) == r["sha256"]:
            os.remove(d)
            removed.append(d)
        else:
            kept.append(d)       # changed since the copy (the game or the player wrote it): kept
    for d in sorted(rec.get("created_dirs", []), key=len, reverse=True):
        try:
            os.rmdir(d)          # only when empty
        except OSError:
            pass
    if not kept:
        os.remove(manifest)
        if os.path.isdir(rec["dest"]) and rec["dest"] in rec.get("created_dirs", []):
            try:
                os.rmdir(rec["dest"])
            except OSError:
                pass
    return {"removed": len(removed), "kept_changed": kept, "missing": missing, "manifest_removed": not kept}


def parse(argv):
    a = {"cmd": argv[0] if argv else "", "from": "takedawn", "src": None, "dest": None, "local_dest": None, "game_root": None,
         "approvals": True, "game_data": False, "json": False, "manifest": None}
    i = 1
    while i < len(argv):
        k = argv[i]
        if k in ("--from", "--src", "--dest", "--local-dest", "--game-root", "--manifest"):
            a[k[2:].replace("-", "_")] = argv[i + 1]
            i += 2
            continue
        if k == "--no-approvals":
            a["approvals"] = False
        elif k == "--game-data":
            a["game_data"] = True
        elif k == "--json":
            a["json"] = True
        else:
            raise Refused("unknown option %s" % k)
        i += 1
    if a["from"] not in ("takedawn", "burnout3"):
        raise Refused("--from takedawn or burnout3")
    return a


def main(argv):
    try:
        a = parse(argv)
        if a["cmd"] == "plan":
            print_plan(make_plan(a), a["json"])
            return 0
        if a["cmd"] == "apply":
            rec, man = apply(a)
            if a["json"]:
                print(json.dumps({"applied": len(rec["files"]), "manifest": man}))
            else:
                print("copied %d file(s) into %s; undo: py -3 bmashup_migrate.py revert --manifest \"%s\"" % (len(rec["files"]), rec["dest"], man))
            return 0
        if a["cmd"] == "revert":
            if not a["manifest"]:
                raise Refused("revert needs --manifest FILE")
            r = revert(a["manifest"])
            if a["json"]:
                print(json.dumps(r))
            else:
                print("removed %d copied file(s); kept %d changed since the copy%s" % (r["removed"], len(r["kept_changed"]),
                      "".join("\n  kept: " + k for k in r["kept_changed"])))
            return 1 if r["kept_changed"] else 0
        print(__doc__)
        return 2
    except Refused as e:
        print(json.dumps({"refused": str(e)}) if "--json" in argv else "REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
