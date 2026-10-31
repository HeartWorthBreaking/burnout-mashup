"""test_lifecycle.py - release readiness R1 stage 4: backup / clean / upgrade / verify / repair of a bundle (tools\\uninstall.py).

    py -3 -B tests\\test_lifecycle.py OUT.json

Temporary bundles under a path with spaces and non-ASCII characters; the candidate is never written. Exit 0 = all PASS."""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
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


def bundle(tag, with_data=True):
    root = os.path.join(tempfile.mkdtemp(prefix="bm lc "), "Spiel ü %s" % tag)
    os.makedirs(os.path.join(root, "tools"))
    shutil.copy2(os.path.join(SRC, "tools", "uninstall.py"), os.path.join(root, "tools", "uninstall.py"))
    open(os.path.join(root, "BUNDLE.json"), "w").write('{"bundle": "test"}')
    shipped = {"README.txt": b"readme", os.path.join("docs", "A.md"): b"doc a", "play.cmd": b"@echo off"}
    for rel, data in shipped.items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)) or root, exist_ok=True)
        open(os.path.join(root, rel), "wb").write(data)
    with open(os.path.join(root, "SHA256SUMS.txt"), "w") as f:
        for rel, data in sorted(shipped.items()):
            f.write("%s  %s\n" % (hashlib.sha256(data).hexdigest(), rel.replace(os.sep, "/")))
    if with_data:
        t = os.path.join(root, "profile", "Roaming", pubfix.IDENT)
        os.makedirs(os.path.join(t, "UDATA", "4541005b"))
        open(os.path.join(t, "UDATA", "4541005b", "save.xbx"), "wb").write(b"SAVE" * 100)
        open(os.path.join(t, "settings.toml"), "w").write("x = 1\n")
        os.makedirs(os.path.join(root, "mods", "user", "my-mod"))
        open(os.path.join(root, "mods", "user", "my-mod", "mod.toml"), "w").write('id = "a.mine"\n')
        for d in ("gamedata", os.path.join("mods", "generated"), "work", "diag"):
            os.makedirs(os.path.join(root, d), exist_ok=True)
            open(os.path.join(root, d, "f.bin"), "wb").write(b"x")
    return root


def tool(root):
    spec = importlib.util.spec_from_file_location("uninst_%d" % id(root), os.path.join(root, "tools", "uninstall.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(m, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = m.main(list(argv))
    return rc, buf.getvalue()


@case
def clean_keeps_my_data():
    root = bundle("clean")
    m = tool(root)
    rc, out = run(m, "clean")
    assert rc == 2 and "kept" in out
    rc, out = run(m, "clean", "--yes")
    assert rc == 0, out
    assert os.path.isfile(os.path.join(root, "profile", "Roaming", pubfix.IDENT, "UDATA", "4541005b", "save.xbx"))
    assert os.path.isfile(os.path.join(root, "mods", "user", "my-mod", "mod.toml"))
    for d in ("gamedata", os.path.join("mods", "generated"), "work", "diag"):
        assert not os.path.exists(os.path.join(root, d)), d
    assert os.path.isfile(os.path.join(root, "README.txt"))          # shipped files stay


@case
def remove_my_data_needs_checked_backup():
    root = bundle("rm")
    m = tool(root)
    rc, out = run(m, "clean", "--yes", "--remove-my-data")
    assert rc == 3 and os.path.isdir(os.path.join(root, "profile")), out
    rc, out = run(m, "clean", "--yes", "--remove-my-data", "--backup-to", os.path.join(root, "inside"))
    assert rc == 3 and os.path.isdir(os.path.join(root, "profile")), out          # backup inside the bundle refused
    m._free_bytes = lambda p: 1024                                               # a nearly full disk
    out_dir = tempfile.mkdtemp(prefix="bm bk ")
    rc, out = run(m, "clean", "--yes", "--remove-my-data", "--backup-to", out_dir)
    assert rc == 3 and "free space" in out and os.path.isdir(os.path.join(root, "profile")), out
    m = tool(root)
    rc, out = run(m, "clean", "--yes", "--remove-my-data", "--backup-to", out_dir)
    assert rc == 0, out
    bk = [d for d in os.listdir(out_dir) if d.startswith("bmashup-backup-")]
    assert len(bk) == 1
    b = os.path.join(out_dir, bk[0])
    assert open(os.path.join(b, "profile", "Roaming", pubfix.IDENT, "UDATA", "4541005b", "save.xbx"), "rb").read() == b"SAVE" * 100
    assert os.path.isfile(os.path.join(b, "mods", "user", "my-mod", "mod.toml"))
    assert not os.path.exists(os.path.join(root, "profile")) and not os.path.exists(os.path.join(root, "mods", "user"))


@case
def upgrade_into_new_bundle():
    old = bundle("old")
    new = bundle("new", with_data=False)
    m = tool(new)
    rc, out = run(m, "upgrade", "--from", old)
    assert rc == 0, out
    assert open(os.path.join(new, "profile", "Roaming", pubfix.IDENT, "UDATA", "4541005b", "save.xbx"), "rb").read() == b"SAVE" * 100
    assert os.path.isfile(os.path.join(new, "mods", "user", "my-mod", "mod.toml"))
    assert os.path.isfile(os.path.join(old, "profile", "Roaming", pubfix.IDENT, "settings.toml"))   # old only read
    rc, out = run(m, "upgrade", "--from", old)
    assert rc == 3 and "never overwritten" in out, out
    rc, out = run(m, "upgrade", "--from", new)
    assert rc == 2, out
    rc, out = run(m, "upgrade", "--from", tempfile.mkdtemp())
    assert rc == 3 and "not a Burnout Mashup bundle" in out


@case
def verify_and_repair():
    root = bundle("rep")
    fresh = bundle("fresh", with_data=False)
    m = tool(root)
    rc, out = run(m, "verify")
    assert rc == 0 and "RESULT OK" in out, out
    os.remove(os.path.join(root, "docs", "A.md"))
    open(os.path.join(root, "README.txt"), "wb").write(b"tampered")
    rc, out = run(m, "verify")
    assert rc == 1 and "missing" in out and "changed" in out, out
    other = bundle("other", with_data=False)
    open(os.path.join(other, "SHA256SUMS.txt"), "a").write("%s  extra.txt\n" % ("0" * 64))
    rc, out = run(m, "repair", "--from", other)
    assert rc == 3 and "not the same version" in out, out
    rc, out = run(m, "repair", "--from", fresh)
    assert rc == 0 and "RESULT OK: 2 restored" in out, out
    assert open(os.path.join(root, "README.txt"), "rb").read() == b"readme"
    assert os.path.isfile(os.path.join(root, "profile", "Roaming", pubfix.IDENT, "settings.toml"))


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
