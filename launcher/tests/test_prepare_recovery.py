"""test_prepare_recovery.py - release readiness R1 stage 4: an interrupted or failed prepare step never leaves a half result
that blocks or poisons the next run (tools\\prepare.py of the candidate; game checks stubbed, file operations real).

    py -3 -B tests\\test_prepare_recovery.py OUT.json

r01 a leftover gamedata.partial (Cancel during a copy) is removed and the copy completes; r02 an unfinished install
(gamedata.installing beside a half gamedata\\) is cleared and the next step runs; r03 a demo build that fails half way leaves no
mods\\generated\\<folder> and no .partial-*; an existing demo is never touched; a successful build appears whole (rename);
r04 clean removes the scratch leftovers. Paths contain spaces and non-ASCII characters. Exit 0 = all PASS."""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
import types
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (public tree: SRC = launcher/, a sandboxed %APPDATA% / %LOCALAPPDATA%)
SRC = pubfix.SRC
RES = {}


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def bundle():
    root = os.path.join(tempfile.mkdtemp(prefix="bm pr "), "Pakét %d" % len(RES))
    shutil.copytree(os.path.join(SRC, "tools"), os.path.join(root, "tools"))
    return root


def load(root, name, rel):
    spec = importlib.util.spec_from_file_location("%s_%d" % (name, id(root)), os.path.join(root, "tools", rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def game_source():
    src = os.path.join(tempfile.mkdtemp(prefix="bm src "), "Installed Game")
    os.makedirs(os.path.join(src, "Burnout 3 Takedown", "Data"))
    open(os.path.join(src, "Burnout 3 Takedown", "default.xbe"), "wb").write(b"XBEH" + b"\0" * 100)
    open(os.path.join(src, "Burnout 3 Takedown", "Data", "a.bin"), "wb").write(b"x" * 1000)
    open(os.path.join(src, ".complete"), "w").write("xr-install 1\nmanifest 81dc20fd647fb0b1\n")
    return src


def quiet(fn, *a):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            rc = fn(*a)
        except Exception as e:  # noqa: BLE001  (Refused etc.: reported with the output)
            return ("EXC", repr(e)), buf.getvalue()
    return rc, buf.getvalue()


def stub_checks(m):
    m.check_installed_root = lambda root, what: open(os.path.join(root, ".complete")).read() if os.path.isfile(
        os.path.join(root, ".complete")) else (_ for _ in ()).throw(m.Refused("no .complete in %s" % root))


@case
def r01_partial_copy_restarts():
    root = bundle()
    m = load(root, "prep", "prepare.py")
    stub_checks(m)
    part = os.path.join(root, "gamedata.partial")
    os.makedirs(os.path.join(part, "Burnout 3 Takedown"))
    open(os.path.join(part, "Burnout 3 Takedown", "half.bin"), "wb").write(b"half")
    rc, out = quiet(m.cmd_data, types.SimpleNamespace(copy_from=game_source(), install_from=None))
    assert rc == 0, out
    assert "removing an interrupted copy" in out
    assert not os.path.exists(part) and os.path.isfile(os.path.join(root, "gamedata", ".complete"))
    assert not os.path.exists(os.path.join(root, "gamedata", "Burnout 3 Takedown", "half.bin"))


@case
def r02_unfinished_install_cleared():
    root = bundle()
    m = load(root, "prep", "prepare.py")
    stub_checks(m)
    os.makedirs(os.path.join(root, "gamedata", "Burnout 3 Takedown"))
    open(os.path.join(root, "gamedata", "Burnout 3 Takedown", "junk.bin"), "wb").write(b"junk")
    open(os.path.join(root, m.INSTALL_MARK), "w").write("started")
    rc, out = quiet(m.cmd_data, types.SimpleNamespace(copy_from=game_source(), install_from=None))
    assert rc == 0 and "unfinished install" in out, out
    assert not os.path.exists(os.path.join(root, m.INSTALL_MARK))
    assert not os.path.exists(os.path.join(root, "gamedata", "Burnout 3 Takedown", "junk.bin"))
    # without the marker a foreign non-empty gamedata is still refused (never deleted)
    root2 = bundle()
    m2 = load(root2, "prep2", "prepare.py")
    stub_checks(m2)
    os.makedirs(os.path.join(root2, "gamedata"))
    open(os.path.join(root2, "gamedata", "mine.txt"), "w").write("mine")
    rc, out = quiet(m2.cmd_data, types.SimpleNamespace(copy_from=game_source(), install_from=None))
    assert rc[0] == "EXC" and os.path.isfile(os.path.join(root2, "gamedata", "mine.txt")), (rc, out)


@case
def r03_demo_failure_leaves_nothing():
    root = bundle()
    m = load(root, "prep", "prepare.py")
    stub_checks(m)
    os.makedirs(os.path.join(root, "gamedata"))
    open(os.path.join(root, "gamedata", ".complete"), "w").write("ok")
    tools = m.load_tools()
    key = [k for k in tools["demos"] if k != "coupe"][0]
    folder = tools["demos"][key]["folder"]

    def failing(tools_, ctx, log, out, k):
        os.makedirs(os.path.join(out, folder, "files"))
        open(os.path.join(out, folder, "mod.toml"), "w").write("half")
        raise RuntimeError("tool failed half way")
    m.demo_track = failing
    rc, out = quiet(m.cmd_demos, types.SimpleNamespace(only=key))
    gen = os.path.join(root, "mods", "generated")
    assert rc == 4, (rc, out)
    assert not os.path.exists(os.path.join(gen, folder)), os.listdir(gen)
    assert not [d for d in os.listdir(gen) if d.startswith(".partial-")], os.listdir(gen)

    def good(tools_, ctx, log, out, k):
        os.makedirs(os.path.join(out, folder))
        open(os.path.join(out, folder, "mod.toml"), "w").write('id = "x"\n')
        return "identical"
    m.demo_track = good
    rc, out = quiet(m.cmd_demos, types.SimpleNamespace(only=key))
    assert rc == 0 and open(os.path.join(gen, folder, "mod.toml")).read() == 'id = "x"\n', (rc, out)
    m.demo_track = failing                                      # an existing demo is skipped, never touched
    rc, out = quiet(m.cmd_demos, types.SimpleNamespace(only=key))
    assert rc == 0 and "already exists" in out and open(os.path.join(gen, folder, "mod.toml")).read() == 'id = "x"\n'


@case
def r03b_killed_build_is_rebuilt():
    """Cancel = the process is stopped mid-copy (no exception handler runs): simulated with SystemExit inside the builder"""
    root = bundle()
    m = load(root, "prep", "prepare.py")
    stub_checks(m)
    os.makedirs(os.path.join(root, "gamedata"))
    open(os.path.join(root, "gamedata", ".complete"), "w").write("ok")
    tools = m.load_tools()
    key = [k for k in tools["demos"] if k != "coupe"][0]
    folder = tools["demos"][key]["folder"]

    def killed(tools_, ctx, log, out, k):
        os.makedirs(os.path.join(out, folder))
        open(os.path.join(out, folder, "mod.toml"), "w").write("half")
        raise SystemExit("killed")
    m.demo_track = killed
    try:
        quiet(m.cmd_demos, types.SimpleNamespace(only=key))
    except SystemExit:
        pass
    gen = os.path.join(root, "mods", "generated")
    assert not os.path.exists(os.path.join(gen, folder)), "a half demo folder is left where the next run would skip it"

    def good(tools_, ctx, log, out, k):
        os.makedirs(os.path.join(out, folder))
        open(os.path.join(out, folder, "mod.toml"), "w").write("whole")
        return "identical"
    m.demo_track = good
    rc, out = quiet(m.cmd_demos, types.SimpleNamespace(only=key))
    assert rc == 0 and open(os.path.join(gen, folder, "mod.toml")).read() == "whole", (rc, out)
    assert not [d for d in os.listdir(gen) if d.startswith(".partial-")]


@case
def r04_clean_removes_scratch():
    root = bundle()
    u = load(root, "un", "uninstall.py")
    for d in ("gamedata.partial", os.path.join("mods", "generated", ".partial-loop")):
        os.makedirs(os.path.join(root, d))
    open(os.path.join(root, "gamedata.installing"), "w").write("x")
    os.makedirs(os.path.join(root, "profile"))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = u.main(["clean", "--yes"])
    assert rc == 0, buf.getvalue()
    assert not os.path.exists(os.path.join(root, "gamedata.partial")) and not os.path.exists(os.path.join(root, "gamedata.installing"))
    assert not os.path.exists(os.path.join(root, "mods", "generated")) and os.path.isdir(os.path.join(root, "profile"))


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
