"""pubfix.py - shared fixtures of the launcher tests in the public source tree (Burnout Mashup identity).

The tests live in launcher/tests/ of the repository. Layout used by every test:
  SRC   = launcher/                       (tools/, docs/, *.cmd)
  REPO  = the repository root             (host/, examples/, workbench/)
  INFO  = tests/fixtures/HOST_INFO_fixture.json   (a HOST_INFO.json of a real host build, used as a fixture: platform, services, tables)
  DEMO  = examples/demo-mods/             (the shipped demo mods)
Identity: the launcher keeps a profile INSIDE the bundle (profile\\Roaming\\BurnoutMashup); the host started by play.cmd is given
that profile as %APPDATA%. Tests therefore use IDENT = "BurnoutMashup" and BMASHUP_* variables. A separate Takedawn install
(%APPDATA%\\Takedawn, %LOCALAPPDATA%\\Takedawn) must never be read or written: importing this module points %APPDATA% and
%LOCALAPPDATA% of the TEST PROCESS at fresh temporary folders, so no test can touch the real ones by accident
(tests/test_isolation.py checks the launcher against fake Takedawn folders explicitly)."""
import json
import os
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
REPO = os.path.dirname(SRC)
INFO = os.path.join(HERE, "fixtures", "HOST_INFO_fixture.json")
DEMO = os.path.join(REPO, "examples", "demo-mods")
TREE = os.path.join(REPO, "host", "tree")
IDENT = "BurnoutMashup"
PLAT = json.load(open(INFO, encoding="utf-8"))["platform"]


def sandbox_env():
    """point %APPDATA% / %LOCALAPPDATA% of this process at new empty temporary folders; returns the base folder"""
    base = tempfile.mkdtemp(prefix="bm test env ")
    for var, sub in (("APPDATA", "Roaming"), ("LOCALAPPDATA", "Local")):
        d = os.path.join(base, sub)
        os.makedirs(d)
        os.environ[var] = d
    return base


SANDBOX = sandbox_env()


def find_cc():
    """a C compiler for the launcher starter: BMASHUP_CC / BMKIT_CC, BMKIT_LLVM_MINGW\\bin, or clang on PATH"""
    for var in ("BMASHUP_CC", "BMKIT_CC"):
        v = os.environ.get(var)
        if v and os.path.isfile(v):
            return v
    root = os.environ.get("BMKIT_LLVM_MINGW")
    if root:
        p = os.path.join(root, "bin", "x86_64-w64-mingw32-clang.exe")
        if os.path.isfile(p):
            return p
    for name in ("x86_64-w64-mingw32-clang", "clang"):
        p = shutil.which(name)
        if p:
            return p
    raise AssertionError("no C compiler: set BMASHUP_CC (path of x86_64-w64-mingw32-clang.exe) or put clang on PATH")


def bump(version):
    """one patch level above a 'a.b.c' version"""
    parts = version.split(".")
    return ".".join(parts[:-1] + [str(int(parts[-1]) + 1)])
