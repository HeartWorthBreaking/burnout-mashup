"""build_host.py - build the Burnout Mashup host from source with YOUR OWN game and install it into host\\ (tester package 0.4.0, Option B).

    build-host.cmd [--xbe "<your default.xbe>"] [--deps build\\deps] [--python-capstone <python with capstone 5.0.9>]
                   [--takedawn <URL or clone>] [--xboxrecomp <URL or clone>] [--git <git.exe>] [--replace]

Runs host-source\\build_from_source.py (the host source package, unchanged) with the toolchain laid out by prepare_deps.py, then
copies its result (burnout3_bmashup.exe, SDL2.dll, shaders\\upscale, licenses\\) into host-local\\ (beside the prebuilt host\\, which is
never touched) and compares the exe with the reference build (EXPECTED.json). play.cmd uses host-local\\ when it holds a host. Defaults: --xbe = gamedata\\Burnout 3 Takedown\\default.xbe (after prepare.cmd data), --deps =
build\\deps, --python-capstone = build\\deps\\pyenv\\Scripts\\python.exe, --git = build\\deps\\git\\cmd\\git.exe (else git on PATH),
--takedawn / --xboxrecomp = the GitHub repositories (network needed; or give local clones). Work folder: build\\work-<n> (new).
Exit 0 = installed and byte-identical to the reference; 2 = installed but NOT identical (unsupported: check the toolchain pins);
1 = refused input; 3 = a build step failed (log: build\\work-<n>\\build_from_source.log).
Python 3.8+, standard library. Nothing outside this package folder is written.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

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
SRC = os.path.join(ROOT, "host-source")
HOST = os.path.join(ROOT, "host-local")        # your build; the shipped prebuilt host\ is never written
EXE = "burnout3_bmashup.exe"
BUILT = [EXE, "SDL2.dll", "shaders", "licenses", "BUILD_RESULT.json"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main(argv):
    ap = argparse.ArgumentParser(description="build the host from source with your own game and install it into host\\")
    ap.add_argument("--xbe", default=os.path.join(bmpaths.gamedata(ROOT), "Burnout 3 Takedown", "default.xbe"))
    ap.add_argument("--deps", default=os.path.join(ROOT, "build", "deps"))
    ap.add_argument("--python-capstone")
    ap.add_argument("--takedawn", default="https://github.com/xenophobentx/takedawn")
    ap.add_argument("--xboxrecomp", default="https://github.com/xenophobentx/xboxrecomp")
    ap.add_argument("--git")
    ap.add_argument("--replace", action="store_true", help="replace an existing host-local\\%s" % EXE)
    a = ap.parse_args(argv)
    exp = json.load(open(os.path.join(SRC, "EXPECTED.json"), encoding="utf-8"))
    deps = os.path.abspath(a.deps)
    cmake = os.path.join(deps, "cmake", "bin", "cmake.exe")
    ninja = os.path.join(deps, "ninja", "ninja.exe")
    pyc = a.python_capstone or os.path.join(deps, "pyenv", "Scripts", "python.exe")
    git = a.git or (os.path.join(deps, "git", "cmd", "git.exe") if os.path.isfile(os.path.join(deps, "git", "cmd", "git.exe"))
                    else shutil.which("git"))
    problems = []
    if not os.path.isfile(a.xbe):
        problems.append("no default.xbe at %s: run prepare.cmd data first, or give --xbe <your disc folder>\\default.xbe" % a.xbe)
    elif sha(a.xbe) != exp["default_xbe_sha256"]:
        problems.append("%s is not the retail NTSC-U default.xbe (sha256 %s expected)" % (a.xbe, exp["default_xbe_sha256"]))
    for what, p in (("llvm-mingw", os.path.join(deps, "llvm-mingw", "bin", "x86_64-w64-mingw32-clang.exe")),
                    ("SDL2", os.path.join(deps, "SDL2", "x86_64-w64-mingw32", "bin", "SDL2.dll")),
                    ("glslang", os.path.join(deps, "glslang", "lib", "libglslang.a")),
                    ("Vulkan headers", os.path.join(deps, "vulkan", "include", "vulkan", "vulkan.h")),
                    ("Vulkan import library", os.path.join(deps, "vulkan", "lib", "libvulkan-1.dll.a")),
                    ("cmake", cmake), ("ninja", ninja)):
        if not os.path.isfile(p):
            problems.append("%s missing (%s): run tools\\prepare_deps.py first (BUILD_HOST.md s2)" % (what, p))
    if not pyc or not os.path.isfile(pyc):
        problems.append("no Python with capstone at %s (BUILD_HOST.md s3: py -3 -m venv build\\deps\\pyenv, then "
                        "build\\deps\\pyenv\\Scripts\\pip install capstone==5.0.9)" % pyc)
    if not git:
        problems.append("git not found: install Git for Windows or give --git, or put PortableGit in the downloads (BUILD_HOST.md s2)")
    if os.path.isfile(os.path.join(HOST, EXE)) and not a.replace:
        problems.append("host-local\\%s exists already (use --replace to build again)" % EXE)
    if problems:
        print("build-host: CANNOT RUN:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    n = 1
    while os.path.exists(os.path.join(ROOT, "build", "work-%d" % n)):
        n += 1
    work = os.path.join(ROOT, "build", "work-%d" % n)
    cmd = [sys.executable, "-B", os.path.join(SRC, "build_from_source.py"), "--work", work, "--xbe", os.path.abspath(a.xbe),
           "--takedawn", a.takedawn, "--xboxrecomp", a.xboxrecomp, "--deps", deps, "--cmake", cmake, "--ninja", ninja,
           "--git", git, "--python-capstone", pyc]
    print("build-host: %s\n(about 3-6 minutes; log %s)" % (" ".join(cmd), os.path.join(work, "build_from_source.log")), flush=True)
    rc = subprocess.call(cmd, cwd=ROOT)
    res = os.path.join(work, "RESULT.json")
    if rc or not os.path.isfile(res):
        print("build-host: the build FAILED (rc %s). Log: %s" % (rc, os.path.join(work, "build_from_source.log")), file=sys.stderr)
        return 3
    r = json.load(open(res, encoding="utf-8"))
    for n_ in BUILT:
        p = os.path.join(HOST, n_)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)
    os.makedirs(HOST, exist_ok=True)
    src = os.path.join(work, "host")
    for n_ in os.listdir(src):
        s = os.path.join(src, n_)
        (shutil.copytree if os.path.isdir(s) else shutil.copyfile)(s, os.path.join(HOST, n_))
    h = sha(os.path.join(HOST, EXE))
    out = {"exe": "host-local/" + EXE, "sha256": h, "reference_sha256": exp["reference_exe_sha256"],
           "reference_identity": exp["reference_identity"], "identical": h == exp["reference_exe_sha256"], "documented_local_build": True,
           "sdl2_sha256": sha(os.path.join(HOST, "SDL2.dll")), "work": os.path.relpath(work, ROOT)}
    with open(os.path.join(HOST, "BUILD_RESULT.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    if out["identical"]:
        print("build-host: DONE - host-local\\%s sha256 %s = the reference build (identity %s). Next: preflight.cmd" %
              (EXE, h, exp["reference_identity"]))
        return 0
    print("build-host: installed, but host-local\\%s sha256 %s is NOT the reference %s. It may work, but it is unsupported in this "
          "alpha: check the toolchain pins (BUILD_HOST.md s2) and report it (docs\\BUGS_AND_CONTRIBUTING.md)." %
          (EXE, h, exp["reference_exe_sha256"]), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
