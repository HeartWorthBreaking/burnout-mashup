"""uninstall.py - back up, list, upgrade, verify / repair and remove what the bundle created (everything lives inside the bundle).

    remove.cmd list                       what the bundle created, with sizes (read only)
    remove.cmd backup --to "X:\\folder"    copy YOUR data out: saves, mod progress, settings (profile\\) and your imported mods
                                          (mods\\user\\); the copy is checked file by file
    remove.cmd clean --yes [--keep-gamedata] [--keep-host]
                                          delete what the bundle can re-create: gamedata\\ (a copy of your game), mods\\generated\\,
                                          work\\, diag\\, build\\, host-local\\. YOUR data (profile\\, mods\\user\\) is KEPT.
    remove.cmd clean --yes --remove-my-data --backup-to "X:\\folder"
                                          also delete profile\\ and mods\\user\\ - only after a checked backup made in the same call
    remove.cmd upgrade --from "X:\\old bundle"
                                          (in a NEW bundle) copy profile\\ and mods\\user\\ from an older bundle; the old bundle is
                                          only read; refused when this bundle already has a profile
    remove.cmd verify                     the shipped files against SHA256SUMS.txt (read only): missing / changed files
    remove.cmd repair --from "X:\\fresh unpacked copy of the SAME version"
                                          restore only the shipped files that are missing or changed, from a copy whose files match
                                          SHA256SUMS.txt; your data is not touched
Downgrade (an older bundle using a newer bundle's profile) is not supported: keep the backup; settings written by a newer host
may be refused by an older one (it starts with defaults and says why in the log).

Python 3.8+. Nothing outside the bundle folder is written, except the --to / --backup-to folder of a backup.
"""
import hashlib
import os
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "launcher"))
try:
    import bmpaths  # noqa: E402  (0.2.0 layout 2: game copy + mods\\user / mods\\generated in <install>\\gamedata)
except ImportError:      # this tool copied without tools\\launcher (the tester bundle layout): everything stays in this folder
    import types
    bmpaths = types.SimpleNamespace(
        install_root=lambda l: None, gamedata=lambda l: os.path.join(os.path.abspath(l), "gamedata"),
        mods_dir=lambda l, k: os.path.join(os.path.abspath(l), "mods", k), display=lambda l, p: os.path.relpath(p, l),
        game_entries=lambda gd: sorted(n for n in (os.listdir(gd) if os.path.isdir(gd) else []) if n.lower() != "mods"))
# tester package 0.4.0 / 0.3.0: + build\ (toolchain + host build work) and host-local\ (your own host build, Option B). The shipped
# prebuilt host\ is part of the package (listed in SHA256SUMS.txt) and is never deleted by clean.
# R1 (release readiness): the player's own data is never deleted by a plain clean.
DERIVED = ["gamedata", "gamedata.partial", "gamedata.installing", os.path.join("mods", "generated"), "work", "diag", "build",
           "host-local"]
MY_DATA = ["profile", os.path.join("mods", "user")]
CREATED = DERIVED + MY_DATA


def where(rel):
    r"""the real place of a DERIVED / MY_DATA name: layout 2 keeps the game copy in <install>\gamedata (its mods\ folder is NOT part
    of it) and mods\user / mods\generated in <install>\gamedata\mods; everything else stays in this launcher folder"""
    if rel == "gamedata":
        return bmpaths.gamedata(ROOT)
    if rel in (os.path.join("mods", "user"), os.path.join("mods", "generated")):
        return bmpaths.mods_dir(ROOT, os.path.basename(rel))
    return os.path.join(ROOT, rel)


def _game_paths():
    gd = bmpaths.gamedata(ROOT)
    if not bmpaths.install_root(ROOT):              # layout 1 (0.1.0 behaviour): the folder holds only the game copy
        return [gd] if os.path.exists(gd) else []
    return [os.path.join(gd, n) for n in bmpaths.game_entries(gd)]


def _base():
    return bmpaths.install_root(ROOT) or ROOT
# what backup copies (relative to profile\Roaming\BurnoutMashup): saves, BurnoutMashup progress sidecars, settings files
BACKUP = ["UDATA", "TDATA", os.path.join("bmashup", "progress"), "settings.toml", "mod-list.toml", "plugin-approvals.toml",
          "plugin-settings.toml", "enhance.toml", "mixer.toml"]


def size_of(p):
    if os.path.isfile(p):
        return os.path.getsize(p), 1
    t = n = 0
    for dp, dn, fn in os.walk(p):
        for f in fn:
            try:
                t += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return t, n


def cmd_list():
    print("bundle: %s" % ROOT)
    for rel in CREATED:
        p = where(rel)
        if rel == "gamedata" and not _game_paths():
            print("  %-16s (not created)" % rel)
            continue
        if os.path.exists(p):
            b, n = size_of(p)
            print("  %-16s %8.1f MB  %6d files" % (rel, b / 1e6, n))
        else:
            print("  %-16s (not created)" % rel)
    print("Outside this folder the bundle writes nothing. Windows itself may keep its usual records of a program that ran "
          "(e.g. Prefetch, the firewall / SmartScreen decisions) and your GPU driver may keep its own shader cache; they are "
          "not the bundle's files (docs\\INSTALL.md section 7).")
    return 0


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _inside(p, root=None):
    root = os.path.normcase(os.path.abspath(root or ROOT))
    return os.path.normcase(os.path.abspath(p)).startswith(root + os.sep)


def _copy_checked(src, dst):
    """copy a file or tree; every file's sha256 compared afterwards. -> files copied; raises OSError on a mismatch."""
    pairs = []
    if os.path.isdir(src):
        shutil.copytree(src, dst)
        for dp, _, fn in os.walk(src):
            for f in fn:
                s = os.path.join(dp, f)
                pairs.append((s, os.path.join(dst, os.path.relpath(s, src))))
    else:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)
        pairs.append((src, dst))
    for s, d in pairs:
        if _sha(s) != _sha(d):
            raise OSError("copy check failed: %s" % d)
    return len(pairs)


def _free_bytes(path):
    p = os.path.abspath(path)
    while not os.path.exists(p):
        p = os.path.dirname(p)
    return shutil.disk_usage(p).free


def cmd_backup(to):
    """-> (rc, backup folder or None). Saves + settings (profile) and mods\\user, checked file by file."""
    src = os.path.join(ROOT, "profile", "Roaming", "BurnoutMashup")
    user = where(os.path.join("mods", "user"))
    if not os.path.isdir(src) and not (os.path.isdir(user) and os.listdir(user)):
        print("nothing to back up: no profile and no imported mods in this bundle")
        return 0, None
    dest = os.path.join(os.path.abspath(to), "bmashup-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    if _inside(dest) or _inside(dest, _base()):
        print("REFUSED: back up to a folder OUTSIDE the bundle (it is deleted on removal)")
        return 3, None
    need = (size_of(src)[0] if os.path.isdir(src) else 0) + (size_of(user)[0] if os.path.isdir(user) else 0)
    if _free_bytes(to) < need + 50 * 1024 * 1024:
        print("REFUSED: not enough free space at %s (need %.1f MB + 50 MB); choose another folder or free some space" %
              (to, need / 1e6))
        return 3, None
    try:
        os.makedirs(dest)
        n = 0
        for rel in BACKUP:
            s = os.path.join(src, rel)
            if os.path.exists(s):
                n += _copy_checked(s, os.path.join(dest, "profile", "Roaming", "BurnoutMashup", rel))
        if os.path.isdir(user) and os.listdir(user):
            n += _copy_checked(user, os.path.join(dest, "mods", "user"))
    except OSError as e:
        print("REFUSED: the backup failed (%s); nothing in the bundle was changed. Folder left for you to inspect: %s" % (e, dest))
        return 4, None
    print("OK: %d files copied and checked to %s (to continue in a new bundle: remove.cmd upgrade --from <old bundle>, or "
          "copy profile\\ and mods\\user\\ from this backup into it)" % (n, dest))
    return 0, dest


def cmd_upgrade(old):
    old = os.path.abspath(old)
    if os.path.normcase(old) == os.path.normcase(ROOT):
        print("REFUSED: --from must be the OLD bundle folder, not this one")
        return 2
    try:
        import bmlayout
    except ImportError:                              # copied without tools\launcher: bundles only
        bmlayout = None
    if bmlayout and not bmlayout.legacy_release(old) and os.path.basename(old).lower() == "launcher" and bmlayout.legacy_release(os.path.dirname(old)):
        old = os.path.dirname(old)                  # the 0.1.0 launcher folder was chosen: its program folder is the parent
    if bmlayout and bmlayout.legacy_release(old):   # 0.2.0: a Burnout Mashup 0.1.0-alpha.1 folder (source layout)
        return bmlayout.import_main(old, ROOT)
    if not os.path.isfile(os.path.join(old, "BUNDLE.json")):
        print("REFUSED: %s is not a Burnout Mashup bundle (no BUNDLE.json) or 0.1.0-alpha.1 folder" % old)
        return 3
    if os.path.exists(os.path.join(ROOT, "profile")) and os.listdir(os.path.join(ROOT, "profile")):
        print("REFUSED: this bundle already has a profile\\ (it is never overwritten); upgrade into a fresh bundle")
        return 3
    copied = 0
    try:
        for rel in MY_DATA:
            s = os.path.join(old, rel)
            if not os.path.isdir(s):
                continue
            d = where(rel)
            if os.path.isdir(d) and os.listdir(d):
                print("REFUSED: %s is not empty in this bundle" % rel)
                return 3
            if os.path.isdir(d):
                os.rmdir(d)
            copied += _copy_checked(s, d)
    except OSError as e:
        print("REFUSED: copy failed (%s); the old bundle is unchanged" % e)
        return 4
    print("OK: %d files of your data copied from %s and checked; the old bundle was only read (delete it yourself when this "
          "one works)" % (copied, old))
    return 0


def _sums(root):
    p = os.path.join(root, "SHA256SUMS.txt")
    out = {}
    for ln in open(p, encoding="utf-8"):
        ln = ln.strip()
        if len(ln) > 66 and ln[64:66] == "  ":
            out[ln[66:].replace("/", os.sep)] = ln[:64]
    return out


def cmd_verify(root=None, quiet=False):
    root = root or ROOT
    bad = []
    for rel, digest in sorted(_sums(root).items()):
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            bad.append((rel, "missing"))
        elif _sha(p) != digest:
            bad.append((rel, "changed"))
    if not quiet:
        for rel, why in bad:
            print("  %-8s %s" % (why, rel))
        print("RESULT %s: %d shipped file(s) missing or changed" % ("OK" if not bad else "PROBLEM", len(bad)) +
              ("" if not bad else " - remove.cmd repair --from <a fresh unpacked copy of this version>"))
    return bad


def cmd_repair(src):
    src = os.path.abspath(src)
    mine = _sums(ROOT)
    try:
        theirs = _sums(src)
    except OSError:
        print("REFUSED: %s has no SHA256SUMS.txt (unpack the same version there first)" % src)
        return 3
    if theirs != mine:
        print("REFUSED: %s is not the same version as this bundle (its SHA256SUMS.txt differs)" % src)
        return 3
    if cmd_verify(src, quiet=True):
        print("REFUSED: the copy at %s is itself incomplete or changed" % src)
        return 3
    bad = cmd_verify(ROOT, quiet=True)
    for rel, _ in bad:
        d = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        tmp = d + ".repair"
        shutil.copy2(os.path.join(src, rel), tmp)
        os.replace(tmp, d)
        print("restored %s" % rel)
    left = cmd_verify(ROOT, quiet=True)
    print("RESULT %s: %d restored, %d still wrong; your profile\\ and mods\\user\\ were not touched" %
          ("OK" if not left else "PROBLEM", len(bad) - len(left), len(left)))
    return 0 if not left else 4


def _force(func, path, _exc):
    """remove a read-only file / folder entry (Windows: git pack files are read-only)"""
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    func(path)


def cmd_clean(yes, keep_gamedata, keep_host=False, remove_my_data=False, backup_to=None):
    targets = [r for r in DERIVED + (MY_DATA if remove_my_data else []) if not (keep_gamedata and r == "gamedata")
               and not (keep_host and (r == "build" or r == "host-local"))]
    present = [r for r in targets if (_game_paths() if r == "gamedata" else os.path.exists(where(r)))]
    if not yes:
        print("would delete: %s" % (", ".join(present) or "nothing"))
        print("kept: your saves and settings (profile\\) and your imported mods (mods\\user\\)" if not remove_my_data else
              "your saves (profile\\) and imported mods (mods\\user\\) WOULD be deleted after a checked backup")
        return 2
    if remove_my_data:
        if not backup_to:
            print("REFUSED: --remove-my-data needs --backup-to <folder outside the bundle> (a checked backup comes first)")
            return 3
        rc, dest = cmd_backup(backup_to)
        if rc:
            print("REFUSED: nothing deleted because the backup did not succeed")
            return rc
    for r in present:
        for p in (_game_paths() if r == "gamedata" else [where(r)]):     # gamedata: the game copy only, never its mods\ folder
            assert os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(_base()) + os.sep), p
            if os.path.isdir(p):
                shutil.rmtree(p, onerror=_force)       # git checkouts under build\ hold read-only files
            else:
                _force(os.remove, p, None)
        print("deleted %s" % (bmpaths.display(ROOT, where(r)) + (" (the game copy; its mods folder is kept)" if r == "gamedata" else "")))
    print("OK. The bundle's own files remain; to remove the bundle completely, delete the folder %s" % ROOT)
    return 0


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="alpha tester bundle: list / back up / remove what it created")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    p = sub.add_parser("backup")
    p.add_argument("--to", required=True)
    p = sub.add_parser("clean")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--keep-gamedata", action="store_true")
    p.add_argument("--keep-host", action="store_true", help="keep your own host build (host-local\\ and build\\); the prebuilt host\\ is never deleted")
    p.add_argument("--remove-my-data", action="store_true", help="also delete profile\\ and mods\\user\\ (needs --backup-to)")
    p.add_argument("--backup-to")
    p = sub.add_parser("upgrade")
    p.add_argument("--from", dest="old", required=True)
    sub.add_parser("verify")
    p = sub.add_parser("repair")
    p.add_argument("--from", dest="src", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        return cmd_list()
    if a.cmd == "backup":
        return cmd_backup(a.to)[0]
    if a.cmd == "clean":
        return cmd_clean(a.yes, a.keep_gamedata, a.keep_host, a.remove_my_data, a.backup_to)
    if a.cmd == "upgrade":
        return cmd_upgrade(a.old)
    if a.cmd == "verify":
        return 1 if cmd_verify() else 0
    if a.cmd == "repair":
        return cmd_repair(a.src)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
