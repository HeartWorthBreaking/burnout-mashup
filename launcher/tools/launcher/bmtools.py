"""bmtools.py - the build prerequisites of BUILD MASHUP: find them, check their versions, and (only when you confirm it, one tool at a
time) download a pinned tool from its official URL, verify its sha256 and unpack it into the tools folder. Python 3.8+, standard library.

Where tools are looked for, per tool, first match wins:
  1. a path you give (--deps FOLDER with llvm-mingw\\ SDL2\\ glslang\\ vulkan\\, --cmake, --ninja, --git, --python-capstone)
  2. --toolchain FOLDER: an existing toolchain folder in one of the known layouts (prepare_deps.py's, or deps under bo3-windeps\\)
  3. the tools folder (default %LOCALAPPDATA%\\BurnoutMashup\\tools): where downloads are unpacked (same layout as prepare_deps.py)
Nothing is searched on PATH except git (any Git 2.x works for reading the pinned sources; PortableGit is offered when none is found).
Downloads: BUILD_TOOLS.json (same pins as tools/prepare_deps.py and docs/BUILDING.md). The licence notice, URL, size and sha256 are shown
before you confirm; a file whose sha256 differs is deleted and never used; an interrupted download leaves nothing behind but its own
.part file (removed). Archives are unpacked into <name>.partial and renamed when complete. No administrator rights, no installer, no PATH
or registry change. Original code (MIT)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(HERE, "BUILD_TOOLS.json")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GLSLANG_OPTS = ["-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DENABLE_OPT=OFF", "-DENABLE_GLSLANG_BINARIES=OFF",
                "-DENABLE_GLSLANG_JS=OFF", "-DENABLE_HLSL=ON", "-DENABLE_SPIRV=ON", "-DGLSLANG_TESTS=OFF", "-DENABLE_CTEST=OFF",
                "-DBUILD_EXTERNAL=OFF", "-DALLOW_EXTERNAL_SPIRV_TOOLS=OFF", "-DALLOW_EXTERNAL_GTEST=OFF", "-DBUILD_WERROR=OFF",
                "-DGLSLANG_ENABLE_INSTALL=ON"]          # = tools/prepare_deps.py (the reference build's glslang)


COMPONENTS = ("llvm-mingw", "SDL2", "glslang", "vulkan")      # the -Deps folder of build/build.ps1


class ToolError(Exception):
    pass


def spec():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return {t["id"]: t for t in json.load(f)["tools"]}


def default_tools_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "BurnoutMashup", "tools")


def sha_f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _run(cmd, timeout=60, **kw):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NOWIN, **kw)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def _read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# ------------------------------------------------------------------------------------------------------------------ locate
def layout(tools_dir=None, toolchain=None, deps=None, cmake=None, ninja=None, git=None, python_capstone=None):
    """-> {deps, cmake, ninja, git, python_capstone, where:{...}}: the paths that will be checked (explicit > toolchain > tools folder)"""
    td = os.path.abspath(tools_dir or default_tools_dir())
    out = {"tools_dir": td, "where": {}}

    def pick(key, explicit, cands):
        if explicit:
            out[key], out["where"][key] = os.path.abspath(explicit), "given"
            return
        for p, w in cands:
            if p and os.path.exists(p):
                out[key], out["where"][key] = p, w
                return
        out[key], out["where"][key] = cands[-1][0], "tools folder (missing)"

    tc = os.path.abspath(toolchain) if toolchain else None
    tcands = lambda *rel: [(os.path.join(tc, *r), "toolchain folder") for r in rel] if tc else []  # noqa: E731
    cm_tc = []
    if tc and os.path.isdir(os.path.join(tc, "cmake")):
        for sub in sorted(os.listdir(os.path.join(tc, "cmake"))):
            cm_tc.append((os.path.join(tc, "cmake", sub, "bin", "cmake.exe"), "toolchain folder"))
    out["comp"] = {}
    for comp in COMPONENTS:                     # each library folder on its own: a toolchain folder may lack one that was downloaded
        key = "deps:" + comp
        pick(key, os.path.join(deps, comp) if deps else None,
             tcands(("deps", comp), ("bo3-windeps", comp)) + [(os.path.join(td, "deps", comp), "tools folder")])
        out["comp"][comp] = out.pop(key)
        out["where"][comp] = out["where"].pop(key)
    parents = {os.path.normcase(os.path.dirname(p)) for p in out["comp"].values()}
    out["deps"] = os.path.dirname(out["comp"]["llvm-mingw"]) if len(parents) == 1 else None   # None: the build gets a junction view
    pick("cmake", cmake, tcands(("cmake", "bin", "cmake.exe")) + cm_tc + [(os.path.join(td, "cmake", "bin", "cmake.exe"), "tools folder")])
    pick("ninja", ninja, tcands(("ninja", "ninja.exe")) + [(os.path.join(td, "ninja", "ninja.exe"), "tools folder")])
    gitw = shutil.which("git")
    pick("git", git, tcands(("git", "cmd", "git.exe")) + [(os.path.join(td, "git", "cmd", "git.exe"), "tools folder")] +
         ([(gitw, "PATH")] if gitw else []) + [(os.path.join(td, "git", "cmd", "git.exe"), "tools folder")])
    pick("python_capstone", python_capstone, tcands(("pyenv", "Scripts", "python.exe"), ("pyvenv", "Scripts", "python.exe")) +
         [(os.path.join(td, "pyenv", "Scripts", "python.exe"), "tools folder")])
    return out


# ------------------------------------------------------------------------------------------------------------------ check
def check(lay):
    """-> {tool id: {ok, found, want, path, where, problem}} for every tool of BUILD_TOOLS.json + powershell + python"""
    S = spec()
    cp = lay["comp"]
    res = {}

    key_of = {"sdl2": "SDL2", "capstone": "python_capstone"}

    def put(tid, ok, found, path, problem=""):
        res[tid] = {"ok": ok, "found": found, "want": S[tid]["check"], "path": path,
                    "where": lay["where"].get(key_of.get(tid, tid), ""), "problem": problem}
    # llvm-mingw
    clang = os.path.join(cp["llvm-mingw"], "bin", "clang.exe")
    if os.path.isfile(clang):
        rc, o = _run([clang, "--version"])
        m = re.search(r"clang version ([0-9.]+)", o)
        v = m.group(1) if m else "?"
        put("llvm-mingw", v == "23.1.2" and os.path.isfile(os.path.join(cp["llvm-mingw"], "bin", "x86_64-w64-mingw32-clang.exe")),
            "clang " + v, clang, "" if v == "23.1.2" else "clang %s is not the pinned 23.1.2 (llvm-mingw 20260922)" % v)
    else:
        put("llvm-mingw", False, "missing", clang, "not found")
    # cmake / ninja
    for tid, key, rx, want in (("cmake", "cmake", r"cmake version ([0-9.]+)", "4.4.4"), ("ninja", "ninja", r"^([0-9.]+)", "1.13.2")):
        p = lay[key]
        if os.path.isfile(p):
            rc, o = _run([p, "--version"])
            m = re.search(rx, o.strip())
            v = m.group(1) if m else "?"
            put(tid, v == want, "%s %s" % (tid, v), p, "" if v == want else "%s %s is not the pinned %s" % (tid, v, want))
        else:
            put(tid, False, "missing", p, "not found")
    # SDL2
    sv = os.path.join(cp["SDL2"], "x86_64-w64-mingw32", "include", "SDL2", "SDL_version.h")
    t = _read(sv)
    if t:
        v = ".".join(re.search(r"define SDL_%s\s+(\d+)" % k, t).group(1) if re.search(r"define SDL_%s\s+(\d+)" % k, t) else "?"
                     for k in ("MAJOR_VERSION", "MINOR_VERSION", "PATCHLEVEL"))
        dll = os.path.isfile(os.path.join(cp["SDL2"], "x86_64-w64-mingw32", "bin", "SDL2.dll"))
        put("sdl2", v == "2.32.10" and dll, "SDL " + v, os.path.dirname(os.path.dirname(os.path.dirname(sv))),
            "" if v == "2.32.10" and dll else ("SDL2.dll missing" if not dll else "SDL %s is not the pinned 2.32.10" % v))
    else:
        put("sdl2", False, "missing", os.path.join(cp["SDL2"]), "not found")
    # glslang
    bi = _read(os.path.join(cp["glslang"], "include", "glslang", "build_info.h"))
    if bi and os.path.isdir(os.path.join(cp["glslang"], "lib", "cmake", "glslang")):
        v = ".".join((re.search(r"GLSLANG_VERSION_%s (\d+)" % k, bi) or [None, "?"])[1] for k in ("MAJOR", "MINOR", "PATCH"))
        put("glslang", v == "16.6.0", "glslang " + v, os.path.join(cp["glslang"]), "" if v == "16.6.0" else "glslang %s is not the pinned 16.6.0" % v)
    else:
        put("glslang", False, "missing", os.path.join(cp["glslang"]), "not found (built libraries + lib/cmake/glslang)")
    # vulkan
    vk = _read(os.path.join(cp["vulkan"], "include", "vulkan", "vulkan_core.h"))
    m = re.search(r"#define VK_HEADER_VERSION (\d+)", vk)
    lib = os.path.isfile(os.path.join(cp["vulkan"], "lib", "libvulkan-1.dll.a"))
    if m:
        put("vulkan", m.group(1) == "363" and lib, "VK_HEADER_VERSION %s%s" % (m.group(1), "" if lib else ", no import library"),
            os.path.join(cp["vulkan"]), "" if m.group(1) == "363" and lib else ("libvulkan-1.dll.a missing" if not lib else "headers are not 1.4.363"))
    else:
        put("vulkan", False, "missing", os.path.join(cp["vulkan"]), "not found")
    # git
    g = lay["git"]
    if g and os.path.isfile(g):
        rc, o = _run([g, "--version"])
        m = re.search(r"git version (\d+)\.(\d+)", o)
        put("git", bool(m) and int(m.group(1)) >= 2, o.strip().splitlines()[0] if o.strip() else "?", g, "" if m else "not a working git")
    else:
        put("git", False, "missing", g or "", "not found (no git on PATH)")
    # python with capstone
    pc = lay["python_capstone"]
    if os.path.isfile(pc):
        rc, o = _run([pc, "-I", "-c", "import capstone,sys;print(capstone.__version__);print('%d.%d'%sys.version_info[:2])"])
        lines = o.strip().splitlines()
        v = lines[0] if rc == 0 and lines else "?"
        put("capstone", v == "5.0.7", "capstone module %s" % v if rc == 0 else "python without capstone", pc,
            "" if v == "5.0.7" else "needs capstone==5.0.9 (module version 5.0.7): %s" % (o.strip().splitlines()[-1][:120] if o.strip() else "?"))
    else:
        put("capstone", False, "missing", pc, "not found")
    # fixed system pieces
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    res["powershell"] = {"ok": os.path.isfile(ps), "found": "Windows PowerShell 5.1" if os.path.isfile(ps) else "missing", "want": "Windows PowerShell 5.1",
                         "path": ps, "where": "Windows", "problem": "" if os.path.isfile(ps) else "Windows PowerShell is part of Windows 10 / 11"}
    res["python"] = {"ok": sys.version_info >= (3, 8), "found": "Python %d.%d" % sys.version_info[:2], "want": "Python 3.8+ (this launcher's)",
                     "path": sys.executable, "where": "this launcher", "problem": ""}
    return res


def fingerprint(lay, res=None):
    """the toolchain identity of a build (versions + sha256 of the files that decide the compiled bytes); a change invalidates the build step"""
    res = res or check(lay)
    cp = lay["comp"]
    files = {"cmake.exe": lay["cmake"], "ninja.exe": lay["ninja"],
             "SDL2.dll": os.path.join(cp["SDL2"], "x86_64-w64-mingw32", "bin", "SDL2.dll"),
             "libSDL2.dll.a": os.path.join(cp["SDL2"], "x86_64-w64-mingw32", "lib", "libSDL2.dll.a"),
             "libvulkan-1.dll.a": os.path.join(cp["vulkan"], "lib", "libvulkan-1.dll.a")}
    llb = os.path.join(cp["llvm-mingw"], "bin")
    if os.path.isdir(llb):
        for n in sorted(os.listdir(llb)):
            if n.lower().endswith(".dll") or n.lower() in ("clang-23.exe", "lld.exe", "ld.lld.exe", "llvm-ar.exe", "llvm-windres.exe", "llvm-rc.exe"):
                files["llvm-mingw/bin/" + n] = os.path.join(llb, n)
    gl = os.path.join(cp["glslang"], "lib")
    if os.path.isdir(gl):
        for n in sorted(os.listdir(gl)):
            if n.endswith(".a"):
                files["glslang/lib/" + n] = os.path.join(gl, n)
    sums = {k: (sha_f(p) if os.path.isfile(p) else None) for k, p in sorted(files.items())}
    vers = {k: res[k]["found"] for k in ("llvm-mingw", "cmake", "ninja", "sdl2", "glslang", "vulkan")}
    doc = json.dumps({"versions": vers, "files": sums}, sort_keys=True)
    return hashlib.sha256(doc.encode()).hexdigest(), vers


# ------------------------------------------------------------------------------------------------------------------ download
def plan_download(tid, tools_dir, mirror=None):
    t = spec()[tid]
    url = t["url"]
    if mirror and t["archive"]:
        url = mirror.rstrip("/") + urllib.parse.urlsplit(t["url"]).path
    return {"id": tid, "name": t["name"], "version": t["version"], "url": url, "official_url": t["url"], "size": t["size"],
            "sha256": t["sha256"], "licence": t["licence"], "licence_note": t["licence_note"], "licence_url": t["licence_url"],
            "needs": t["needs"], "dest": os.path.join(tools_dir, t["target"].replace("/", os.sep)), "mirror": bool(mirror)}


def notice_text(p):
    size = ("%.1f MB" % (p["size"] / 1e6)) if p["size"] else "size decided by pip"
    lines = ["Download %s %s" % (p["name"], p["version"]),
             "  from     %s%s" % (p["url"], "  (TEST MIRROR of %s)" % p["official_url"] if p["mirror"] else ""),
             "  size     %s" % size]
    if p["sha256"]:
        lines.append("  sha256   %s (checked before anything is unpacked; a different file is deleted)" % p["sha256"])
    lines += ["  into     %s" % p["dest"], "  licence  %s" % p["licence"], "  " + p["licence_note"], "  licence text: %s" % p["licence_url"]]
    if p["needs"]:
        lines.append("  needs    %s (already present or downloaded first)" % ", ".join(p["needs"]))
    return "\n".join(lines)


def fetch(url, dest, sha, size, progress=None, cancelled=None, timeout=60):
    """download url to dest (via dest.part); sha256 and size checked; raises ToolError with a plain reason"""
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(part):
        os.remove(part)
    req = urllib.request.Request(url, headers={"User-Agent": "BurnoutMashup-launcher/1 (build tools download)"})
    got = 0
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            if size and total and total != size:
                raise ToolError("the server offers %d bytes, the pinned file has %d: not the pinned file (nothing was used)" % (total, size))
            last = 0
            while True:
                if cancelled and cancelled():
                    raise ToolError("cancelled")
                blk = r.read(1 << 20)
                if not blk:
                    break
                f.write(blk)
                h.update(blk)
                got += len(blk)
                if progress and time.time() - last > 0.5:
                    progress(got, size or total)
                    last = time.time()
    except urllib.error.HTTPError as e:
        _rm(part)
        raise ToolError("HTTP %d from %s: the file is not available there (%s). Try again later, or download it by hand from the official "
                        "page and give its folder with --downloads" % (e.code, url, e.reason))
    except (urllib.error.URLError, OSError, ConnectionError, TimeoutError) as e:
        _rm(part)
        raise ToolError("the download was interrupted after %d bytes (%s): nothing was kept. Check the connection and try again" % (got, getattr(e, "reason", e)))
    except ToolError:
        _rm(part)
        raise
    if size and got != size:
        _rm(part)
        raise ToolError("the download ended after %d of %d bytes (interrupted): nothing was kept. Try again" % (got, size))
    if sha and h.hexdigest() != sha:
        _rm(part)
        raise ToolError("integrity check FAILED: sha256 %s, pinned %s. The file was deleted and NOT used (a wrong or tampered file, or a "
                        "changed release). Download it by hand from %s only if you trust it, then compare its sha256" % (h.hexdigest(), sha, url))
    os.replace(part, dest)
    return dest


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _strip_one(tmp, dest):
    tops = os.listdir(tmp)
    src = os.path.join(tmp, tops[0]) if len(tops) == 1 and os.path.isdir(os.path.join(tmp, tops[0])) else tmp
    shutil.move(src, dest)
    shutil.rmtree(tmp, ignore_errors=True)


def _safe_members_zip(z, root):
    for n in z.namelist():
        p = os.path.normpath(os.path.join(root, n))
        if not (p + os.sep).startswith(os.path.normpath(root) + os.sep) and p != os.path.normpath(root):
            raise ToolError("archive path escapes the folder: %s" % n)


def install(tid, tools_dir, archive=None, log=print, mirror=None, lay=None):
    """unpack / build one tool into the tools folder from its verified archive (or pip for capstone). Atomic: <target>.partial -> <target>."""
    t = spec()[tid]
    dest = os.path.join(tools_dir, t["target"].replace("/", os.sep))
    if os.path.exists(dest):
        raise ToolError("%s exists already: remove it first to install %s again" % (dest, tid))
    if archive and sha_f(archive) != t["sha256"]:
        raise ToolError("%s is not the pinned %s (sha256 differs)" % (archive, t["archive"]))
    part = dest + ".partial"
    shutil.rmtree(part, ignore_errors=True)
    tmp = dest + ".unpack"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        kind = t["install"]
        if kind == "unzip":
            with zipfile.ZipFile(archive) as z:
                _safe_members_zip(z, tmp)
                z.extractall(tmp)
            _strip_one(tmp, part)
        elif kind == "ninja":
            os.makedirs(part)
            with zipfile.ZipFile(archive) as z:
                z.extract("ninja.exe", part)
        elif kind in ("untar", "vulkan", "glslang"):
            with tarfile.open(archive, "r:gz") as tf:
                for m in tf.getmembers():
                    if m.issym() or m.islnk() or os.path.isabs(m.name) or ".." in m.name.replace("\\", "/").split("/"):
                        raise ToolError("unsafe archive member: %s" % m.name)
                if sys.version_info >= (3, 12):
                    tf.extractall(tmp, filter="data")
                else:
                    tf.extractall(tmp)
            if kind == "untar":
                _strip_one(tmp, part)
            elif kind == "vulkan":
                src = dest + ".src"
                shutil.rmtree(src, ignore_errors=True)
                _strip_one(tmp, src)
                os.makedirs(os.path.join(part, "lib"))
                shutil.copytree(os.path.join(src, "include"), os.path.join(part, "include"))
                shutil.rmtree(src, ignore_errors=True)
                llvm = os.path.join(lay["comp"]["llvm-mingw"], "bin")
                vk = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vulkan-1.dll")
                if not os.path.isfile(vk):
                    raise ToolError("no %s: install your graphics driver (it brings the Vulkan loader)" % vk)
                try:
                    r = subprocess.run([os.path.join(llvm, "gendef.exe"), "-", vk], capture_output=True, text=True, errors="replace",
                                       timeout=120, creationflags=NOWIN)
                except (OSError, subprocess.TimeoutExpired) as e:
                    raise ToolError("gendef could not run: %s" % e)
                if r.returncode or "EXPORTS" not in r.stdout:
                    raise ToolError("gendef printed no export list for %s" % vk)
                deff = os.path.join(part, "lib", "vulkan-1.def")
                with open(deff, "w", encoding="ascii", errors="replace", newline="\n") as f:
                    f.write(r.stdout)
                rc, o = _run([os.path.join(llvm, "llvm-dlltool.exe"), "-m", "i386:x86-64", "-d", deff, "-l",
                              os.path.join(part, "lib", "libvulkan-1.dll.a")], timeout=120)
                if rc:
                    raise ToolError("llvm-dlltool failed: %s" % o[-300:])
            else:  # glslang: build static Release libraries with the pinned llvm-mingw / cmake / ninja (prepare_deps.py's options)
                src = dest + ".src"
                shutil.rmtree(src, ignore_errors=True)
                _strip_one(tmp, src)
                llvm = os.path.join(lay["comp"]["llvm-mingw"], "bin")
                env = dict(os.environ, PATH=os.pathsep.join([llvm, os.path.dirname(lay["ninja"]), os.environ.get("PATH", "")]))
                fw = lambda p: p.replace("\\", "/")  # noqa: E731
                b = dest + ".bld"
                shutil.rmtree(b, ignore_errors=True)
                for cmd in ([lay["cmake"], "-S", src, "-B", b, "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + fw(lay["ninja"]),
                             "-DCMAKE_SYSTEM_NAME=Windows", "-DCMAKE_SYSTEM_PROCESSOR=x86_64",
                             "-DCMAKE_C_COMPILER=" + fw(os.path.join(llvm, "x86_64-w64-mingw32-clang.exe")),
                             "-DCMAKE_CXX_COMPILER=" + fw(os.path.join(llvm, "x86_64-w64-mingw32-clang++.exe")),
                             "-DCMAKE_RC_COMPILER=" + fw(os.path.join(llvm, "x86_64-w64-mingw32-windres.exe")),
                             "-DCMAKE_INSTALL_PREFIX=" + fw(part)] + GLSLANG_OPTS,
                            [lay["cmake"], "--build", b, "--target", "install"]):
                    log("  $ cmake %s" % " ".join(cmd[1:4]))
                    rc, o = _run(cmd, timeout=3600, env=env)
                    if rc:
                        raise ToolError("glslang build step failed (rc %d): %s" % (rc, o[-400:]))
                shutil.rmtree(b, ignore_errors=True)
                shutil.rmtree(src, ignore_errors=True)
        elif kind == "portablegit":
            rc, o = _run([archive, "-o" + part, "-y"], timeout=1800)
            if rc or not os.path.isfile(os.path.join(part, "cmd", "git.exe")):
                raise ToolError("PortableGit did not unpack (rc %d): %s" % (rc, o[-300:]))
        elif kind == "pip":
            rc, o = _run([sys.executable, "-m", "venv", part], timeout=600)
            if rc:
                raise ToolError("python -m venv failed: %s" % o[-300:])
            py = os.path.join(part, "Scripts", "python.exe")
            rc, o = _run([py, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--only-binary=:all:", t["pip"]], timeout=1800)
            if rc:
                raise ToolError("pip install %s failed (network or index): %s" % (t["pip"], o.strip()[-300:]))
            sp = os.path.join(part, "Lib", "site-packages")
            for rel, want in t["installed_sha256"].items():
                p = os.path.join(sp, *rel.split("/"))
                if not os.path.isfile(p) or sha_f(p) != want:
                    raise ToolError("installed %s is not the pinned file (sha256 differs): capstone is not the reference build" % rel)
        else:
            raise ToolError("unknown install kind %s" % kind)
        with open(os.path.join(part, ".bm-tool.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"id": tid, "version": t["version"], "archive": t["archive"], "sha256": t["sha256"], "installed": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
        os.replace(part, dest)
    except BaseException:
        for p in (part, tmp, dest + ".src", dest + ".bld"):
            shutil.rmtree(p, ignore_errors=True)
        raise
    return dest


def acquire(tid, tools_dir, downloads=None, mirror=None, log=print, progress=None, cancelled=None, lay=None):
    """verified archive (from --downloads, the tools folder's download cache, or a fresh download) + install"""
    t = spec()[tid]
    arc = None
    if t["archive"]:
        cache = os.path.join(tools_dir, "downloads", t["archive"])
        for cand in ([os.path.join(downloads, t["archive"])] if downloads else []) + [cache]:
            if os.path.isfile(cand):
                if sha_f(cand) == t["sha256"]:
                    arc = cand
                    log("  %s: verified archive %s (sha256 ok)" % (tid, cand))
                    break
                log("  %s: %s has the wrong sha256: not used" % (tid, cand))
        if not arc:
            p = plan_download(tid, tools_dir, mirror)
            log("  %s: downloading %s" % (tid, p["url"]))
            arc = fetch(p["url"], cache, t["sha256"], t["size"], progress, cancelled)
            log("  %s: sha256 ok (%s)" % (tid, t["sha256"][:16]))
    return install(tid, tools_dir, arc, log=log, mirror=mirror, lay=lay)


def head_check(tid, timeout=20):
    """real-network coverage without downloading: HEAD of the official URL (redirects followed), size compared with the pin"""
    t = spec()[tid]
    req = urllib.request.Request(t["url"], method="HEAD", headers={"User-Agent": "BurnoutMashup-launcher/1 (head check)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            n = int(r.headers.get("Content-Length") or 0)
            return {"id": tid, "status": r.status, "size": n or None, "size_ok": (n == t["size"]) if (t["size"] and n) else None,
                    "note": "" if n else "no Content-Length announced (a generated source archive): size and sha256 are checked after the download",
                    "final_host": urllib.parse.urlsplit(r.geturl()).netloc}
    except urllib.error.HTTPError as e:
        return {"id": tid, "status": e.code, "error": str(e.reason)}
    except (urllib.error.URLError, OSError) as e:
        return {"id": tid, "status": None, "error": str(getattr(e, "reason", e))}
