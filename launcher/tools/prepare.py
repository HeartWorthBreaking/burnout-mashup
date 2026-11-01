"""prepare.py - local preparation for the Burnout Mashup alpha tester bundle (game data + the demos that need your data).

    prepare.cmd data --copy-from "X:\\installed data root"       copy your INSTALLED game data into gamedata\\
    prepare.cmd data --install-from "X:\\disc.iso or folder"      install + check it with the host's own installer
    prepare.cmd demos [--only coupe,loop,canyon]                 build the demo mods that need donor parts from YOUR data
    prepare.cmd status                                           what is prepared
    prepare.cmd "X:\\dropped folder or disc image"                 (drag it onto prepare.cmd) picks --copy-from or --install-from

Python 3.11+ (standard library; the bundled generator tools need 3.11). Writes ONLY inside the bundle folder: gamedata\\,
work\\ (scratch, removed after a successful build), mods\\generated\\ and, for --install-from, profile\\ (installer logs).
Never changes the source you copy or install from. Generated mods contain parts derived from your game data: keep them on
this machine (never share them). Exit 0 = done, 2 = usage, 3 = refused (the reason and the fix are printed), 4 = a tool failed.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "launcher"))
try:
    import bmpaths  # noqa: E402  (0.2.0 layout 2: game copy + mods\\user / mods\\generated in <install>\\gamedata)
except ImportError:      # this tool copied without tools\\launcher (the tester bundle layout): everything stays in this folder
    import types
    bmpaths = types.SimpleNamespace(
        install_root=lambda l: None, gamedata=lambda l: os.path.join(os.path.abspath(l), "gamedata"),
        mods_dir=lambda l, k: os.path.join(os.path.abspath(l), "mods", k), display=lambda l, p: os.path.relpath(p, l),
        game_entries=lambda gd: sorted(n for n in (os.listdir(gd) if os.path.isdir(gd) else []) if n.lower() != "mods"))
GAMEDATA = bmpaths.gamedata(ROOT)
MODS_GENERATED = bmpaths.mods_dir(ROOT, "generated")
LAYOUT2 = bool(bmpaths.install_root(ROOT))
STAGE_COPY, STAGE_INSTALL = ".copying", ".installing-data"     # 0.2.0: staged INSIDE gamedata\, moved into place at the end
GAME_DIR = "Burnout 3 Takedown"
GAME_SIGNATURE = "D0FC2EF4E9B2A86F"
MANIFEST_ID = "81dc20fd647fb0b1"
def _pick_host():
    # same rule as play.cmd: BMASHUP_HOST=prebuilt or local; else host-local (your own build) if present, else the prebuilt host
    sel = (os.environ.get("BMASHUP_HOST") or "").strip().lower()
    loc = os.path.join(ROOT, "host-local", "BurnoutMashup.exe")          # BUILD MASHUP installs the release-named host
    if not os.path.isfile(loc) and os.path.isfile(os.path.join(ROOT, "host-local", "burnout3_bmashup.exe")):
        loc = os.path.join(ROOT, "host-local", "burnout3_bmashup.exe")    # an older build-host.cmd build
    pre = os.path.join(ROOT, "host", "burnout3_bmashup.exe")
    return loc if sel == "local" else pre if sel == "prebuilt" else (loc if os.path.isfile(loc) else pre)


HOST = _pick_host()   # Option A: the prebuilt host\ ; Option B: your own build in host-local\ (build-host.cmd)
PREPARE_VERSION = "0.4.0"
INSTALL_MARK = "gamedata.installing"     # R1: beside gamedata\ while the host's installer writes it (removed when checked)


class Refused(Exception):
    pass


def say(msg):
    print(msg, flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fnv_signature(header):
    hsz = struct.unpack_from("<I", header, 0x108)[0]
    if hsz == 0 or hsz > 0x10000:
        hsz = 0x1000
    h = 1469598103934665603
    for b in header[:hsz]:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return "%016X" % h


def inside(path, base):
    p, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return p == b or p.startswith(b.rstrip("\\/") + os.sep)


def data_root_of(arg):
    p = os.path.abspath(arg)
    if os.path.basename(p.rstrip("\\/")).lower() == GAME_DIR.lower():
        p = os.path.dirname(p.rstrip("\\/"))
    return p


def check_installed_root(root, what):
    xbe = os.path.join(root, GAME_DIR, "default.xbe")
    if not os.path.isfile(xbe):
        raise Refused("%s: %s not found. Give the folder that holds '%s\\default.xbe' (an INSTALLED copy: Takedawn's "
                      "%%LOCALAPPDATA%%\\Takedawn\\Game, or a folder made with --install-from)" % (what, xbe, GAME_DIR))
    with open(xbe, "rb") as f:
        head = f.read(0x10000)
    if head[:4] != b"XBEH":
        raise Refused("%s: %s is not an Xbox executable" % (what, xbe))
    sig = fnv_signature(head)
    if sig != GAME_SIGNATURE:
        raise Refused("%s: game signature %s, expected %s: only the retail NTSC-U Burnout 3: Takedown is supported"
                      % (what, sig, GAME_SIGNATURE))
    mk = os.path.join(root, ".complete")
    txt = open(mk, encoding="utf-8", errors="replace").read() if os.path.isfile(mk) else ""
    m = re.search(r"^manifest\s+(\S+)", txt, re.M)
    if not (txt.startswith("xr-install 1") and m and m.group(1) == MANIFEST_ID):
        raise Refused("%s: %s is missing or not manifest %s: the data was not installed / checked. Use "
                      "prepare.cmd data --install-from <disc image or extracted disc folder> instead" % (what, mk, MANIFEST_ID))
    return txt


def missing_host_message():
    """the text depends on what this package ships: BUILD_HOST.md (no-host package: build your own) or not (prebuilt package: unpack again)"""
    if os.path.isfile(os.path.join(ROOT, "BUILD_HOST.md")):
        return ("this package contains no host program (%s is missing): build your own first (BUILD_HOST.md; build-host.cmd --xbe "
                "<your disc folder>\\default.xbe), or use --copy-from with an installed copy of the game" % HOST)
    return ("the host program %s is missing: unpack the package again (the host belongs in the host folder), or use --copy-from "
            "with an installed copy of the game" % HOST)


def _clear_game(dest):
    """remove the game copy in dest (everything but mods\\ - your mods are never touched)"""
    for n in bmpaths.game_entries(dest):
        p = os.path.join(dest, n)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def _move_into(stage, dest):
    """move the staged game copy's entries into dest; the .complete marker last (it makes the copy count as checked)"""
    names = sorted(os.listdir(stage), key=lambda n: (n == ".complete", n))
    for n in names:
        os.replace(os.path.join(stage, n), os.path.join(dest, n))
    os.rmdir(stage)


def cmd_data(a):
    dest = GAMEDATA
    if os.path.isfile(os.path.join(dest, ".complete")):
        check_installed_root(dest, "gamedata")
        say("gamedata already holds a checked install (%s). Nothing to do. To replace it, delete the gamedata folder first."
            % dest)
        return 0
    if os.path.isfile(os.path.join(ROOT, INSTALL_MARK)):     # R1: our own unfinished install (Cancel / crash): start over
        say("removing an unfinished install in %s and starting again" % dest)
        if os.path.isdir(dest):
            _clear_game(dest) if LAYOUT2 else shutil.rmtree(dest)
        os.remove(os.path.join(ROOT, INSTALL_MARK))
    left = [n for n in bmpaths.game_entries(dest) if n not in (STAGE_COPY, STAGE_INSTALL)]
    if left:
        raise Refused("%s holds game files but no .complete marker (an interrupted copy?). Delete them (keep the mods folder) "
                      "and run this step again: %s" % (dest, ", ".join(left[:6])))
    if a.copy_from:
        src = data_root_of(a.copy_from)
        base = bmpaths.install_root(ROOT) or ROOT
        if inside(src, base) or inside(base, src) or inside(src, dest):
            raise Refused("the source %s and the bundle %s overlap" % (src, base))
        marker = check_installed_root(src, "source")
        need = 0
        for dp, dn, fn in os.walk(os.path.join(src, GAME_DIR)):
            for f in fn:
                need += os.path.getsize(os.path.join(dp, f))
        os.makedirs(dest, exist_ok=True)
        free = shutil.disk_usage(dest).free
        if free < need + 512 * 1024 * 1024:
            raise Refused("not enough space: %.1f GB needed, %.1f GB free on the bundle's drive" % (need / 1e9, free / 1e9))
        tmp = os.path.join(dest, STAGE_COPY) if LAYOUT2 else dest + ".partial"
        if os.path.exists(tmp):                    # R1: our own scratch copy from an interrupted run (Cancel): start over
            say("removing an interrupted copy (%s) and starting again" % tmp)
            shutil.rmtree(tmp)
        say("copying %.2f GB from %s (read only) to %s ..." % (need / 1e9, src, dest))
        n = 0
        for dp, dn, fn in os.walk(os.path.join(src, GAME_DIR)):
            rel = os.path.relpath(dp, src)
            os.makedirs(os.path.join(tmp, rel), exist_ok=True)
            for f in fn:
                s, d = os.path.join(dp, f), os.path.join(tmp, rel, f)
                shutil.copyfile(s, d)
                if os.path.getsize(s) != os.path.getsize(d):
                    raise Refused("copy of %s is incomplete" % s)
                n += 1
                if n % 100 == 0:
                    say("  %d files" % n)
        with open(os.path.join(tmp, ".complete"), "w", encoding="utf-8", newline="\n") as f:
            f.write(marker)
        if sha256_file(os.path.join(tmp, GAME_DIR, "default.xbe")) != sha256_file(os.path.join(src, GAME_DIR, "default.xbe")):
            raise Refused("default.xbe copy differs from the source")
        if LAYOUT2:
            _move_into(tmp, dest)
        else:
            if os.path.isdir(dest):
                os.rmdir(dest)
            os.replace(tmp, dest)
        check_installed_root(dest, "gamedata")
        say("OK: %d files copied; gamedata holds a checked install (manifest %s). Next: preflight.cmd, then prepare.cmd demos"
            % (n, MANIFEST_ID))
        return 0
    if a.install_from:
        src = os.path.abspath(a.install_from)
        if not os.path.exists(src):
            raise Refused("%s does not exist" % src)
        if not os.path.isfile(HOST):
            raise Refused(missing_host_message())
        os.makedirs(dest, exist_ok=True)
        stage = os.path.join(dest, STAGE_INSTALL) if LAYOUT2 else dest
        if LAYOUT2:
            if os.path.exists(stage):
                shutil.rmtree(stage)
            os.makedirs(stage)
        env = dict(os.environ)
        for k in list(env):
            if k.upper().startswith(("RECOMP_", "BO3_", "TAKEDAWN_", "BMASHUP_")):
                del env[k]
        env["APPDATA"] = os.path.join(ROOT, "profile", "Roaming")
        env["LOCALAPPDATA"] = os.path.join(ROOT, "profile", "Local")
        os.makedirs(env["APPDATA"], exist_ok=True)
        os.makedirs(env["LOCALAPPDATA"], exist_ok=True)
        cmd = [HOST, "--install", src, "--dest", stage]
        with open(os.path.join(ROOT, INSTALL_MARK), "w", encoding="utf-8") as f:     # removed only after a checked install
            f.write("install from %s started by prepare.py %s\n" % (src, PREPARE_VERSION))
        say("running the host's installer (checks every file against the retail NTSC-U manifest): %s" % " ".join(cmd))
        rc = subprocess.call(cmd, cwd=os.path.dirname(HOST), env=env)
        if rc != 0:
            raise Refused("the installer ended with exit status %d (see its STEP / RESULT lines above). An image or folder "
                          "of the retail NTSC-U disc is needed" % rc)
        if LAYOUT2:
            check_installed_root(stage, "gamedata")
            _move_into(stage, dest)
        check_installed_root(dest, "gamedata")
        os.remove(os.path.join(ROOT, INSTALL_MARK))
        say("OK: gamedata holds a checked install. Next: preflight.cmd, then prepare.cmd demos")
        return 0
    raise Refused("give --copy-from <installed data root> or --install-from <disc image or extracted disc folder>")


# ---- drag and drop -------------------------------------------------------------------------------------------------
DISC_IMAGE_EXT = (".iso", ".xiso")


def classify_drop(path):
    """what a dropped path is: ('copy', root) | ('install', path) ; anything else raises Refused with a plain message"""
    p = os.path.abspath(path.strip().strip('"'))
    if not os.path.exists(p):
        raise Refused("%s does not exist. Drag a folder or a disc image (.iso / .xiso) onto prepare.cmd" % p)
    if os.path.isfile(p):
        if p.lower().endswith(DISC_IMAGE_EXT):
            return "install", p
        raise Refused("%s is a file, not a disc image. Drag your installed game folder, an extracted disc folder or a "
                      ".iso / .xiso disc image onto prepare.cmd" % p)
    if os.path.isfile(os.path.join(data_root_of(p), GAME_DIR, "default.xbe")) and os.path.isfile(os.path.join(data_root_of(p), ".complete")):
        return "copy", data_root_of(p)
    if os.path.isfile(os.path.join(p, "default.xbe")):
        return "install", p
    if os.path.isfile(os.path.join(data_root_of(p), GAME_DIR, "default.xbe")):
        raise Refused("%s holds the game but has no .complete marker (it was not installed and checked by the host's installer). "
                      "Drag the original disc image or the extracted disc folder instead" % p)
    raise Refused("%s is not recognised. Drag a folder that holds '%s\\default.xbe' (an installed copy of the game), an "
                  "extracted disc folder (default.xbe at its top) or a .iso / .xiso disc image onto prepare.cmd" % (p, GAME_DIR))


def cmd_auto(a):
    kind, src = classify_drop(a.path)
    if kind == "copy":
        say("dropped: an installed copy of the game -> data --copy-from %s" % src)
        a.copy_from, a.install_from = src, None
    else:
        say("dropped: a disc image or extracted disc -> data --install-from %s" % src)
        a.copy_from, a.install_from = None, src
    return cmd_data(a)


# ---- demos ---------------------------------------------------------------------------------------------------------
def load_tools():
    p = os.path.join(HERE, "TOOLS.json")
    try:
        t = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused("tools\\TOOLS.json unreadable (%s): unpack the bundle again" % e)
    return t


def run_tool(tools, name, args, log):
    t = tools["tools"].get(name)
    if not t or not t.get("available"):
        raise Refused("the %s tool is not in this bundle (%s)" % (name, (t or {}).get("note", "not packaged")))
    entry = os.path.join(ROOT, t["dir"].replace("/", os.sep), t["entry"])
    if not os.path.isfile(entry):
        raise Refused("%s missing: unpack the bundle again" % entry)
    cmd = [sys.executable, "-B", entry] + args
    say("  > %s %s" % (name, " ".join(args)))
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run(cmd, cwd=os.path.dirname(entry), env=env, capture_output=True, text=True, errors="replace")
    log.write("$ %s\n%s\n%s\n[exit %d]\n" % (" ".join(cmd), r.stdout, r.stderr, r.returncode))
    if r.returncode != 0:
        tail = (r.stdout + r.stderr).strip().splitlines()[-12:]
        raise Exception("%s failed (exit %d):\n    %s" % (name, r.returncode, "\n    ".join(tail)))
    return r.stdout


def fmt(seq, ctx):
    return [s.format(**ctx) for s in seq]


def find_mod_folder(set_dir):
    """the one folder holding a mod.toml, at most two levels below set_dir (tools write <set>/<mod> or <set>/<name>/<mod>)"""
    hits = []
    for dp, dn, fn in os.walk(set_dir):
        if os.path.relpath(dp, set_dir).count(os.sep) > 1:
            dn[:] = []
        if "mod.toml" in fn and dp != set_dir:
            hits.append(dp)
            dn[:] = []
    if len(hits) != 1:
        raise Exception("expected one mod folder in %s, found %s" % (set_dir, hits))
    return hits[0]


def compare_expected(folder, expected, label):
    """reports whether the generated files equal the bytes that were runtime-validated (informational)"""
    if not expected:
        return "no reference"
    diff = []
    for rel, h in sorted(expected.items()):
        p = os.path.join(folder, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            diff.append(rel + " missing")
        elif sha256_file(p) != h:
            diff.append(rel)
    if diff:
        say("  NOTE %s: %d file(s) differ from the reference build: %s (the build itself passed; report it if the game "
            "refuses the mod)" % (label, len(diff), ", ".join(diff[:6])))
        return "differs: " + ", ".join(diff)
    say("  %s: byte-identical to the reference build (%d files)" % (label, len(expected)))
    return "identical"


def demo_coupe(tools, ctx, log, out):
    d = tools["demos"]["coupe"]
    src = os.path.join(ROOT, d["source"].replace("/", os.sep))
    w = os.path.join(ctx["work"], "coupe")
    shutil.copytree(src, os.path.join(w, "src"))
    ctx2 = dict(ctx, car=os.path.join(w, "src", "car.toml"), set=os.path.join(w, "set"))
    run_tool(tools, "carimport", fmt(d["validate"], ctx2), log)
    run_tool(tools, "carimport", fmt(d["package"], ctx2), log)
    pkg = find_mod_folder(ctx2["set"])
    series = os.path.join(out, d["folder"])
    shutil.copytree(os.path.join(ROOT, d["series_source"].replace("/", os.sep)), series)
    dst = os.path.join(series, "files", "pveh", "BMCO")
    os.makedirs(dst)
    for f in ("CIC1.bgv", "CIC1.hwd", "CIC1.lwd"):
        shutil.copyfile(os.path.join(pkg, "files", "pveh", "COMP", f), os.path.join(dst, f))
    with open(os.path.join(series, "LABELS.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("mod.toml (series, names, paints): AUTHORED\n"
                "files/pveh/BMCO/CIC1.bgv: AUTHORED geometry + texture (carimport coupe) + DERIVED donor blocks (COMPCAR1) "
                "from YOUR game data - LOCAL ONLY, never share\n"
                "files/pveh/BMCO/CIC1.hwd, .lwd: DERIVED (donor engine audio, COMPCAR1) from YOUR game data - LOCAL ONLY\n"
                "Built by prepare.py %s with %s\n" % (PREPARE_VERSION, tools["tools"]["carimport"].get("version", "?")))
    return compare_expected(series, d.get("expected"), d["folder"])


def demo_track(tools, ctx, log, out, key):
    d = tools["demos"][key]
    w = os.path.join(ctx["work"], key)
    os.makedirs(w, exist_ok=True)
    ctx2 = dict(ctx, src=os.path.join(w, "src"), build=os.path.join(w, "build"), set=os.path.join(w, "set"),
                package=os.path.join(ROOT, d["package_toml"].replace("/", os.sep)))
    run_tool(tools, "trackbuild", fmt(d["gen"], ctx2), log)
    descs = [f for f in os.listdir(ctx2["src"]) if f.endswith(".track.json")]
    if len(descs) != 1:
        raise Exception("expected one *.track.json in %s, found %s" % (ctx2["src"], descs))
    ctx2["desc"] = os.path.join(ctx2["src"], descs[0])
    run_tool(tools, "trackbuild", fmt(d["build"], ctx2), log)
    run_tool(tools, "trackbuild", fmt(d["validate"], ctx2), log)
    run_tool(tools, "trackbuild", fmt(d["package"], ctx2), log)
    pkg = find_mod_folder(ctx2["set"])
    target = os.path.join(out, d["folder"])
    shutil.copytree(pkg, target)
    return compare_expected(target, d.get("expected"), d["folder"])


def cmd_demos(a):
    if sys.version_info < (3, 11):
        raise Refused("Python %d.%d: the demo generators need Python 3.11 or newer (python.org)" % sys.version_info[:2])
    gd = GAMEDATA
    check_installed_root(gd, "gamedata (run prepare.cmd data first)")
    tools = load_tools()
    want = [x.strip() for x in (a.only or ",".join(tools["demos"].keys())).split(",") if x.strip()]
    for x in want:
        if x not in tools["demos"]:
            raise Refused("unknown demo %s (known: %s)" % (x, ", ".join(tools["demos"])))
    out = MODS_GENERATED
    os.makedirs(out, exist_ok=True)
    state_p = os.path.join(out, "PREPARE_STATE.json")
    state = json.load(open(state_p, encoding="utf-8")) if os.path.isfile(state_p) else {"mods": [], "results": {}}
    work = os.path.join(ROOT, "work")
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    ctx = {"game": os.path.join(gd, GAME_DIR), "work": work}
    log_p = os.path.join(work, "prepare_demos.log")
    failed = []
    with open(log_p, "w", encoding="utf-8") as log:
        for key in want:
            d = tools["demos"][key]
            target = os.path.join(out, d["folder"])
            if os.path.exists(target):
                say("%s: %s already exists - skipped (delete that folder to rebuild it)" % (key, target))
                continue
            say("%s: building %s ..." % (key, d["folder"]))
            # R1 (release readiness): build into mods\generated\.partial-<key>\ and rename at the end, so a cancelled or
            # failed build never leaves a half mod that a later run would skip as "already exists"
            part = os.path.join(out, ".partial-" + key)
            if os.path.exists(part):
                shutil.rmtree(part)
            os.makedirs(part)
            try:
                if key == "coupe":
                    r = demo_coupe(tools, ctx, log, part)
                else:
                    r = demo_track(tools, ctx, log, part, key)
                os.replace(os.path.join(part, d["folder"]), target)
                shutil.rmtree(part, ignore_errors=True)
                state["results"][d["folder"]] = r
                if d["folder"] not in state["mods"]:
                    state["mods"].append(d["folder"])
                say("%s: OK -> mods\\generated\\%s" % (key, d["folder"]))
            except Refused:
                raise
            except Exception as e:  # noqa: BLE001  (a tool failure: report it, keep going with the next demo)
                failed.append(key)
                shutil.rmtree(part, ignore_errors=True)     # only our own partial folder; an existing target is never touched
                say("%s: FAILED - %s" % (key, e))
    state.update({"prepare": PREPARE_VERSION, "ok": not failed, "failed": failed, "tools": {
        k: v.get("version") for k, v in tools["tools"].items() if v.get("available")}})
    with open(state_p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, indent=1)
        f.write("\n")
    if failed:
        keep = os.path.join(ROOT, "diag", "prepare_demos.log")
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        shutil.copyfile(log_p, keep)
        say("FAILED: %s. The full tool output is in %s (diag.cmd adds it to a bug report)." % (", ".join(failed), keep))
        return 4
    shutil.rmtree(work)
    say("OK: demos in mods\\generated: %s. Start play.cmd." % ", ".join(state["mods"]))
    return 0


def cmd_status(a):
    gd = GAMEDATA
    try:
        check_installed_root(gd, "gamedata")
        say("game data: OK (%s)" % gd)
    except Refused as e:
        say("game data: not ready - %s" % e)
    st = os.path.join(MODS_GENERATED, "PREPARE_STATE.json")
    say("generated demos: %s" % (open(st, encoding="utf-8").read().strip() if os.path.isfile(st) else "none"))
    return 0


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Burnout Mashup alpha tester bundle: local preparation")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("data", help="put a checked copy of your game data into gamedata\\")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--copy-from", help="an INSTALLED data root (holds 'Burnout 3 Takedown\\default.xbe' and .complete)")
    g.add_argument("--install-from", help="a disc image (.iso / .xiso) or an extracted disc folder (host installer)")
    p = sub.add_parser("demos", help="build the demo mods that need donor parts from your data")
    p.add_argument("--only", help="comma list of: coupe, loop, canyon")
    sub.add_parser("status", help="what is prepared")
    p = sub.add_parser("auto", help="(drag and drop) route a dropped folder or disc image to data --copy-from / --install-from")
    p.add_argument("path", help="the dropped installed-game folder, extracted disc folder or .iso / .xiso file")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    try:
        return {"data": cmd_data, "demos": cmd_demos, "status": cmd_status, "auto": cmd_auto}[a.cmd](a)
    except Refused as e:
        say("REFUSED: %s" % e)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
