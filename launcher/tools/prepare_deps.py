"""prepare_deps.py - lay out the pinned build toolchain for build-host.cmd from the archives YOU downloaded (tester package 0.2.0).

    py -3 -B tools\\prepare_deps.py --downloads <folder with the downloaded archives> [--out build\\deps]

Reads only the archives named in BUILD_HOST.md section 2 (each must match its pinned sha256; nothing is downloaded by this
script) and writes everything under --out (default: <package>\\build\\deps, refused if it exists):
  llvm-mingw\\      llvm-mingw 20260922 ucrt x86_64           cmake\\   CMake 4.4.4        ninja\\ninja.exe   Ninja 1.13.2
  SDL2\\            SDL2 2.32.10 mingw devel package          git\\     PortableGit 2.56.0.2 (only with --extract-git: its
                                                              7-Zip self-extractor shows a progress window; else your own git)
  vulkan\\include\\ Vulkan-Headers vulkan-sdk-1.4.363.0       vulkan\\lib\\libvulkan-1.dll.a (import library made by llvm-dlltool
                                                              from the export list of your driver's System32\\vulkan-1.dll;
                                                              the host does not import it, the build only needs the file)
  glslang\\         glslang 16.6.0 built here as static Release libraries with llvm-mingw (the reference build's options)
Python 3.8+, standard library. Exit 0 ok, 1 an archive is missing / wrong, 3 a step failed. Log: <out>\\prepare_deps.log.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PINS = [  # file name, sha256, url, required
    ("llvm-mingw-20260922-ucrt-x86_64.zip", "e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666",
     "https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/llvm-mingw-20260922-ucrt-x86_64.zip", True),
    ("cmake-4.4.4-windows-x86_64.zip", "bace36e94b31c68ab6fa295f26dfa11219e0701cf7c94b0284a7d1cb13dac536",
     "https://github.com/Kitware/CMake/releases/download/v4.4.4/cmake-4.4.4-windows-x86_64.zip", True),
    ("ninja-win.zip", "07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65",
     "https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-win.zip", True),
    ("SDL2-devel-2.32.10-mingw.tar.gz", "83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2",
     "https://github.com/libsdl-org/SDL/releases/download/release-2.32.10/SDL2-devel-2.32.10-mingw.tar.gz", True),
    ("glslang-16.6.0.tar.gz", "9c09b901149c729df745057dafa815278aaa101b84d2b6e14f16a42de52f97f2",
     "https://github.com/KhronosGroup/glslang/archive/refs/tags/16.6.0.tar.gz", True),
    ("Vulkan-Headers-vulkan-sdk-1.4.363.0.tar.gz", "4a078be12bef21cfebc09d878b77a63cff9d68f899254a0b00d0e37ef73e7f7e",
     "https://github.com/KhronosGroup/Vulkan-Headers/archive/refs/tags/vulkan-sdk-1.4.363.0.tar.gz", True),
    ("PortableGit-2.56.0.2-64-bit.7z.exe", "075e158ef8e1f0ab80b347e245405d3eca735c2dc88fd8e032e137d0ca61f61b",
     "https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.2/PortableGit-2.56.0.2-64-bit.7z.exe", False),
]
GLSLANG_OPTS = ["-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DENABLE_OPT=OFF", "-DENABLE_GLSLANG_BINARIES=OFF",
                "-DENABLE_GLSLANG_JS=OFF", "-DENABLE_HLSL=ON", "-DENABLE_SPIRV=ON", "-DGLSLANG_TESTS=OFF", "-DENABLE_CTEST=OFF",
                "-DBUILD_EXTERNAL=OFF", "-DALLOW_EXTERNAL_SPIRV_TOOLS=OFF", "-DALLOW_EXTERNAL_GTEST=OFF", "-DBUILD_WERROR=OFF",
                "-DGLSLANG_ENABLE_INSTALL=ON"]


class Fail(Exception):
    pass


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def log(out, s):
    print(s, flush=True)
    with open(os.path.join(out, "prepare_deps.log"), "a", encoding="utf-8") as f:
        f.write(s + "\n")


def run(out, cmd, cwd=None, env=None):
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors="replace")
    log(out, "$ %s  (rc %d, %.0f s)" % (" ".join(cmd)[:400], r.returncode, time.time() - t0))
    for ln in (r.stdout + r.stderr).strip().splitlines()[-8:]:
        log(out, "    " + ln)
    if r.returncode:
        raise Fail("step failed (rc %d): %s" % (r.returncode, os.path.basename(cmd[0])))
    return r


def strip_one(members_root, dest):
    """move the single top folder of an unpacked archive to dest"""
    tops = os.listdir(members_root)
    src = os.path.join(members_root, tops[0]) if len(tops) == 1 and os.path.isdir(os.path.join(members_root, tops[0])) else members_root
    shutil.move(src, dest)
    shutil.rmtree(members_root, ignore_errors=True)


def unzip(arc, dest, tmp):
    zipfile.ZipFile(arc).extractall(tmp)
    strip_one(tmp, dest)


def untar(arc, dest, tmp):
    with tarfile.open(arc, "r:gz") as t:
        if sys.version_info >= (3, 12):
            t.extractall(tmp, filter="data")
        else:
            t.extractall(tmp)
    strip_one(tmp, dest)


def main(argv):
    ap = argparse.ArgumentParser(description="lay out the pinned build toolchain from your downloaded archives")
    ap.add_argument("--downloads", required=True, help="folder holding the downloaded archives (BUILD_HOST.md s2)")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "deps"), help="new folder (default build\\deps)")
    ap.add_argument("--extract-git", action="store_true",
                    help="also unpack PortableGit into <out>\\git (its self-extractor shows a small progress window); "
                         "without it, use your installed git")
    a = ap.parse_args(argv)
    dl, out = os.path.abspath(a.downloads), os.path.abspath(a.out)
    have = {}
    bad = []
    for name, want, url, req in PINS:
        p = os.path.join(dl, name)
        if not os.path.isfile(p):
            if req:
                bad.append("MISSING %s - download it from %s" % (name, url))
            continue
        h = sha(p)
        if h != want:
            bad.append("WRONG %s: sha256 %s, expected %s - download it again from %s" % (name, h, want, url))
        else:
            have[name] = p
    if bad:
        print("prepare_deps: CANNOT RUN:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    if os.path.exists(out):
        print("prepare_deps: %s exists; give a new --out folder (or delete it to start over)" % out, file=sys.stderr)
        return 1
    os.makedirs(out)
    tmp = os.path.join(out, "_unpack")
    try:
        log(out, "prepare_deps: archives verified (%d); unpacking into %s" % (len(have), out))
        unzip(have[PINS[0][0]], os.path.join(out, "llvm-mingw"), tmp)
        unzip(have[PINS[1][0]], os.path.join(out, "cmake"), tmp)
        os.makedirs(os.path.join(out, "ninja"))
        zipfile.ZipFile(have[PINS[2][0]]).extract("ninja.exe", os.path.join(out, "ninja"))
        untar(have[PINS[3][0]], os.path.join(out, "SDL2"), tmp)
        untar(have[PINS[4][0]], os.path.join(out, "glslang-src"), tmp)
        untar(have[PINS[5][0]], os.path.join(out, "vulkan-src"), tmp)
        shutil.copytree(os.path.join(out, "vulkan-src", "include"), os.path.join(out, "vulkan", "include"))
        llvm = os.path.join(out, "llvm-mingw", "bin")
        cmake = os.path.join(out, "cmake", "bin", "cmake.exe")
        ninja = os.path.join(out, "ninja", "ninja.exe")
        # Vulkan import library (not imported by the host; the build only needs the file)
        os.makedirs(os.path.join(out, "vulkan", "lib"))
        vk = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vulkan-1.dll")
        if not os.path.isfile(vk):
            raise Fail("no %s: install your GPU driver (it brings the Vulkan loader)" % vk)
        r = run(out, [os.path.join(llvm, "gendef.exe"), "-", vk])
        if "EXPORTS" not in r.stdout:
            raise Fail("gendef printed no export list for %s" % vk)
        with open(os.path.join(out, "vulkan", "lib", "vulkan-1.def"), "w", encoding="ascii", errors="replace", newline="\n") as f:
            f.write(r.stdout)
        run(out, [os.path.join(llvm, "llvm-dlltool.exe"), "-m", "i386:x86-64", "-d", os.path.join(out, "vulkan", "lib", "vulkan-1.def"),
                  "-l", os.path.join(out, "vulkan", "lib", "libvulkan-1.dll.a")])
        # glslang 16.6.0, static Release, llvm-mingw
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([llvm, os.path.dirname(ninja), env.get("PATH", "")])
        b = os.path.join(out, "glslang-build")
        fw = lambda p: p.replace("\\", "/")  # noqa: E731  (CMake reads backslashes as escapes)
        run(out, [cmake, "-S", os.path.join(out, "glslang-src"), "-B", b, "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + fw(ninja),
                  "-DCMAKE_SYSTEM_NAME=Windows", "-DCMAKE_SYSTEM_PROCESSOR=x86_64",
                  "-DCMAKE_C_COMPILER=" + fw(os.path.join(llvm, "x86_64-w64-mingw32-clang.exe")),
                  "-DCMAKE_CXX_COMPILER=" + fw(os.path.join(llvm, "x86_64-w64-mingw32-clang++.exe")),
                  "-DCMAKE_RC_COMPILER=" + fw(os.path.join(llvm, "x86_64-w64-mingw32-windres.exe")),
                  "-DCMAKE_INSTALL_PREFIX=" + fw(os.path.join(out, "glslang"))] + GLSLANG_OPTS, env=env)
        run(out, [cmake, "--build", b, "--target", "install"], env=env)
        git = None
        if PINS[6][0] in have and a.extract_git:
            run(out, [have[PINS[6][0]], "-o" + os.path.join(out, "git"), "-y"])
            git = os.path.join(out, "git", "cmd", "git.exe")
        libs = sorted(os.listdir(os.path.join(out, "glslang", "lib")))
        log(out, "glslang libraries: %s" % ", ".join("%s %s" % (n, sha(os.path.join(out, "glslang", "lib", n))[:16])
                                                   for n in libs if n.endswith(".a")))
        log(out, "DONE. deps = %s; cmake = %s; ninja = %s; git = %s" % (out, cmake, ninja, git or "(yours, on PATH)"))
        log(out, "Next: the Python for the recompiler (BUILD_HOST.md s3), then build-host.cmd")
        return 0
    except (Fail, OSError, zipfile.BadZipFile, tarfile.TarError) as e:
        log(out, "prepare_deps: FAILED: %s" % e)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
