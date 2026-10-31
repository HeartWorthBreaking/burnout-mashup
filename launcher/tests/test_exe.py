"""test_exe.py - "Burnout Mashup.exe" (tools\\launcher\\exe\\bmstart.c): deterministic build, starts the launcher script beside it
with the dropped paths unchanged (spaces, non-ASCII), returns at once. The Python search / no-Python message box are not run here
(they would show a dialog): BMASHUP_PYW points the exe at this Python and a stand-in bmlauncher.pyw records its argv.

    py -3 -B tests\\test_exe.py OUT.json"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402
EXE_DIR = os.path.join(pubfix.SRC, "tools", "launcher", "exe")
RES = {}


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s" % e
    return fn


def build(out):
    cc = pubfix.find_cc()
    r = subprocess.run([sys.executable, "-B", os.path.join(EXE_DIR, "build_exe.py"), out, "--cc", cc], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return hashlib.sha256(open(out, "rb").read()).hexdigest()


T = tempfile.mkdtemp(prefix="bm exe test ")
A, B = os.path.join(T, "a.exe"), os.path.join(T, "b.exe")


@case
def deterministic_build():
    assert build(A) == build(B), "two builds differ"


@case
def starts_launcher_with_dropped_paths():
    root = os.path.join(T, "Bündel mit Leerzeichen")
    os.makedirs(os.path.join(root, "tools", "launcher"))
    rec = os.path.join(T, "argv.json")
    open(os.path.join(root, "tools", "launcher", "bmlauncher.pyw"), "w", encoding="utf-8").write(
        "import json, os, sys\njson.dump({'argv': sys.argv, 'cwd': os.getcwd()}, open(%r, 'w', encoding='utf-8'))\n" % rec)
    exe = os.path.join(root, "Burnout Mashup.exe")
    shutil.copy2(A, exe)
    drops = [os.path.join(T, "my game data"), "C:\\a dir\\with trailing\\", "zip with ' quote.zip", "é ü"]
    t0 = time.time()
    r = subprocess.run([exe] + drops, env=dict(os.environ, BMASHUP_PYW=sys.executable), timeout=30)
    assert r.returncode == 0, "exit %d" % r.returncode
    assert time.time() - t0 < 10, "the starter did not return at once"
    for _ in range(100):
        if os.path.exists(rec):
            break
        time.sleep(0.1)
    got = json.load(open(rec, encoding="utf-8"))
    assert os.path.normcase(got["argv"][0]) == os.path.normcase(os.path.join(root, "tools", "launcher", "bmlauncher.pyw")), got
    assert got["argv"][1:] == drops, got["argv"]
    assert os.path.normcase(got["cwd"]) == os.path.normcase(root), got["cwd"]


@case
def has_icon_and_version():
    b = open(A, "rb").read()
    assert b"B\x00u\x00r\x00n\x00o\x00u\x00t\x00 \x00M\x00a\x00s\x00h\x00u\x00p\x00" in b, "no version strings"
    assert len(b) < 1024 * 1024, "unexpectedly large"


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    shutil.rmtree(T, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
