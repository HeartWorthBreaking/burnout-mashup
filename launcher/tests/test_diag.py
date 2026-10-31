"""test_diag.py - release readiness R1 stage 4: the diagnostic export (tools\\bmdiag.py) holds versions and a redacted log,
never saves, game files, mod contents, the user name, computer name, home path, e-mail addresses or environment values.

    py -3 -B tests\\test_diag.py OUT.json

A temporary bundle (path with the user name, spaces and non-ASCII characters) with a profile log that contains the user name,
computer name, home folder, an e-mail address and the bundle path; a save file, a progress sidecar, a game file and a mod with a
secret line in a data file; plain export and --include-more. Every byte of the zip is searched. Exit 0 = all PASS."""
import getpass
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (public tree: SRC = launcher/, a sandboxed %APPDATA% / %LOCALAPPDATA%)
SRC = pubfix.SRC
RES = {}
USER = getpass.getuser()
COMPUTER = socket.gethostname()
HOME = os.path.expanduser("~")
MODDATA = "SECRET-MOD-CONTENT-7f3a"
SAVE = "SAVE-BYTES-91c2"
GAME = "GAME-FILE-BYTES-55d1"
ENVV = "ENV-VALUE-0b77"


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def make():
    root = os.path.join(tempfile.mkdtemp(prefix="bm diag "), "Bündel %s" % USER)
    shutil.copytree(os.path.join(SRC, "tools"), os.path.join(root, "tools"))
    open(os.path.join(root, "BUNDLE.json"), "w").write('{"bundle": "test"}')
    t = os.path.join(root, "profile", "Roaming", pubfix.IDENT)
    os.makedirs(os.path.join(t, "logs"))
    os.makedirs(os.path.join(t, "UDATA", "4541005b"))
    os.makedirs(os.path.join(t, "bmashup", "progress"))
    open(os.path.join(t, "UDATA", "4541005b", "save.xbx"), "w").write(SAVE)
    open(os.path.join(t, "bmashup", "progress", "x.bmprog"), "w").write(SAVE)
    open(os.path.join(t, "logs", "run.log"), "w", encoding="utf-8").write(
        "[PLATFORM] host ok\n[MOD] mod a.b 1.0: %s\\mods\\user\\a\n[ADMIT] 1 mods ... 1 admitted, 0 refused\n"
        "path %s\\AppData and user %s on %s, mail someone.name+tag@example.org\nFATAL nothing really\n" % (root, HOME, USER, COMPUTER))
    open(os.path.join(t, "plugin-approvals.toml"), "w").write('approved = ["a.b sha256:%s"]\n' % ("0" * 64))
    g = os.path.join(root, "gamedata", "Burnout 3 Takedown")
    os.makedirs(g)
    open(os.path.join(g, "default.xbe"), "w").write(GAME)
    m = os.path.join(root, "mods", "user", "a")
    os.makedirs(m)
    open(os.path.join(m, "mod.toml"), "w").write('id = "a.b"\nversion = "1.0"\nname = "A"\n')
    open(os.path.join(m, "data.bin"), "w").write(MODDATA)
    return root


def export(root, more):
    out = os.path.join(tempfile.mkdtemp(prefix="bm diag out "), "r.zip")
    env = dict(os.environ, BMASHUP_TEST_VAR=ENVV)
    r = subprocess.run([sys.executable, "-B", os.path.join(root, "tools", "bmdiag.py"), "--bundle", root, "--out", out] +
                       (["--include-more"] if more else []), capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    blob, names = b"", []
    with zipfile.ZipFile(out) as z:
        for i in z.infolist():
            names.append(i.filename)
            blob += z.read(i)
    return blob.decode("utf-8", "replace"), names


def check(more):
    root = make()
    text, names = export(root, more)
    for bad, what in ((SAVE, "save / progress bytes"), (GAME, "game file bytes"), (MODDATA, "mod file contents"),
                      (ENVV, "an environment value"), ("someone.name+tag@example.org", "an e-mail address"),
                      (root, "the bundle path"), (HOME, "the home folder")):
        assert bad not in text, "%s found in the export" % what
    if len(USER) >= 3:
        assert USER.lower() not in text.lower(), "the user name is in the export"
    if len(COMPUTER) >= 3:
        assert COMPUTER.lower() not in text.lower(), "the computer name is in the export"
    assert "[PLATFORM] host ok" in text and "FATAL nothing really" in text, "the key log lines are missing"
    assert not any(n.lower().endswith((".xbx", ".bmprog", ".bin")) for n in names), names


@case
def diag_plain():
    check(False)


@case
def diag_include_more():
    check(True)


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad, "user_len": len(USER), "computer_len": len(COMPUTER),
                      "platform": platform.platform()}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
