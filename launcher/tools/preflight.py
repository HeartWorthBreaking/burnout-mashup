"""preflight.py - read-only check of a Burnout Mashup alpha tester bundle (bmashup-alpha-tester) before the first start.

    preflight.cmd                                   (from the bundle folder; same as the line below)
    py -3 -B tools\\preflight.py                     bundle files, host, Windows, Vulkan, the bundle's own game data
    py -3 -B tools\\preflight.py --data "X:\\folder"  also check another game data root (holds "Burnout 3 Takedown\\default.xbe")

Python 3.8+ only (standard library). It writes only its own result to diag\\preflight_last.txt (for diag.cmd); it never copies
or changes game data and never starts the game.
It runs `vulkaninfo --summary` when vulkaninfo is installed (it only queries the driver).
Every line is PASS / FAIL / WARN / INFO with a fix; the last line is RESULT PASS or RESULT FAIL; exit 0 = no FAIL, 1 = a FAIL.
Adapted from the p2 / p3 host distributions' check_host.py (same checks, bundle layout, game-data and mod checks).
Tester package 0.4.0: TWO hosts. Option A = the prebuilt host in host\\ (shipped, listed in SHA256SUMS.txt); Option B = your own
build in host-local\\ (build-host.cmd). Which one play.cmd starts: BMASHUP_HOST=prebuilt|local, else host-local\\ when it holds a
host, else host\\. This check reports the host in use with its sha256 and warns when it is neither the expected reference build
(main21, sha256 below) nor a documented local build (host-local\\BUILD_RESULT.json written by build-host.cmd).
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

BUNDLE = "bmashup-alpha-tester"
HOST_DIR = "host"
HOST_EXE = "burnout3_bmashup.exe"
HOST_SHA256 = "f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656"   # reference build main21
HOST_IDENTITY = b"bmp-0.1.9+2c8142e65f20"
def _host_info_reference():
    """R1: the package's own host description (host\\HOST_INFO.json, written at packaging) names the reference host"""
    import json as _j
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), HOST_DIR, "HOST_INFO.json")
    try:
        i = _j.load(open(p, encoding="utf-8"))
        if i.get("exe_sha256") and i.get("identity"):
            return i["exe_sha256"], i["identity"].encode("ascii")
    except (OSError, ValueError, UnicodeError):
        pass
    return None


if _host_info_reference():
    HOST_SHA256, HOST_IDENTITY = _host_info_reference()
HOST_LOCAL = "host-local"                            # Option B: what build-host.cmd installs (the host\\ prebuilt files are package files)
SDL_SHA256 = "53e8fa7e9ed43c30bd650c39396f0d9d2067d2fff0b926c9433b75202592e4aa"
GAME_SIGNATURE = "D0FC2EF4E9B2A86F"                 # FNV-1a 64 over the XBE image header, as the host computes it
XBE_SHA256 = "9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9"   # retail NTSC-U default.xbe
MANIFEST_ID = "81dc20fd647fb0b1"                   # the .complete marker's manifest
GAME_DIR = "Burnout 3 Takedown"
SYSTEM_DLLS = ["kernel32.dll", "user32.dll", "advapi32.dll", "shell32.dll", "winmm.dll", "winhttp.dll", "dbghelp.dll",
               "ucrtbase.dll", "gdi32.dll", "imm32.dll", "msvcrt.dll", "ole32.dll", "oleaut32.dll", "setupapi.dll",
               "version.dll"]

# runtime folders the bundle creates; they are not in SHA256SUMS.txt
RUNTIME_DIRS = ("gamedata", "profile", os.path.join("mods", "generated"), os.path.join("mods", "user"), "diag", "work", "build") + \
    (HOST_LOCAL, HOST_LOCAL + ".prev", HOST_LOCAL + ".new", HOST_LOCAL + ".old", HOST_LOCAL + ".swap")
FREE_GB_MIN = 4.0                                    # game data copy 2.4 GB + shader cache + generated mods (~90 MB); the
                                                     # host build needs ~6 GB more under build\ (BUILD_HOST.md)

results = []


lines = []


def say(kind, name, text, fix=None):
    line = "%-4s  %s: %s" % (kind, name, text)
    if fix:
        line += "\n      -> " + fix
    print(line, flush=True)
    lines.append(line)
    results.append(kind)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def system32():
    root = os.environ.get("SystemRoot", r"C:\Windows")
    native = os.path.join(root, "Sysnative")
    if struct.calcsize("P") == 4 and os.path.isdir(native):
        return native
    return os.path.join(root, "System32")


def file_version(path):
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        n = ver.GetFileVersionInfoSizeW(path, None)
        if not n:
            return None
        buf = ctypes.create_string_buffer(n)
        if not ver.GetFileVersionInfoW(path, 0, n, buf):
            return None
        p = ctypes.c_void_p()
        ln = wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(p), ctypes.byref(ln)) or ln.value < 52:
            return None
        ffi = ctypes.string_at(p.value, 52)
        ms, ls = struct.unpack_from("<II", ffi, 8)
        return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except Exception:  # noqa: BLE001
        return None


def is_runtime(rel):
    r = rel.replace("/", os.sep)
    return any(r == d or r.startswith(d + os.sep) for d in RUNTIME_DIRS) or "__pycache__" in r.split(os.sep)


def check_location(here):
    say("INFO", "bundle", here)
    low = here.lower()
    appdata = (os.environ.get("APPDATA") or "").lower()
    for bad, why in ((os.path.join(appdata, "takedawn") if appdata else None, "your Takedawn settings / saves folder"),
                     (os.path.join((os.environ.get("LOCALAPPDATA") or "").lower(), "takedawn") if os.environ.get("LOCALAPPDATA") else None,
                      "your Takedawn install / data folder")):
        if bad and (low == bad or low.startswith(bad + os.sep)):
            say("FAIL", "location", "the bundle is inside %s (%s)" % (bad, why),
                "unpack the bundle into its own new folder, e.g. C:\\Games\\" + BUNDLE)
    if os.path.isfile(os.path.join(here, "Takedawn.exe")) or os.path.isfile(os.path.join(here, "takedawn-setup.exe")):
        say("FAIL", "location", "a Takedawn install is in the same folder", "unpack the bundle into its own new folder")
    if len(here) > 160:
        say("WARN", "location", "the folder path is %d characters long; deep paths can exceed Windows' 260-character limit "
            "inside the game data" % len(here), "use a short folder such as C:\\Games\\" + BUNDLE)
    try:
        here.encode("ascii")
    except UnicodeEncodeError:
        say("WARN", "location", "the folder path has non-ASCII characters (NOT TESTED with the host)",
            "if the game does not start, move the bundle to a plain ASCII path such as C:\\Games\\" + BUNDLE)
    try:
        free = shutil.disk_usage(here).free / 1e9
        if free < FREE_GB_MIN:
            say("FAIL" if free < 1 else "WARN", "disk space", "%.1f GB free; about %.0f GB are needed (game data copy, caches, "
                "generated demos)" % (free, FREE_GB_MIN), "free space on this drive or move the bundle")
        else:
            say("PASS", "disk space", "%.1f GB free" % free)
    except OSError:
        pass
    probe = os.path.join(here, "profile")
    parent = probe if os.path.isdir(probe) else here
    if not os.access(parent, os.W_OK):
        say("FAIL", "write access", "%s is not writable (settings, saves and logs are written into the bundle)" % parent,
            "unpack the bundle into a folder you own (not Program Files)")


def check_files(here):
    sums = os.path.join(here, "SHA256SUMS.txt")
    if not os.path.isfile(sums):
        say("FAIL", "files", "SHA256SUMS.txt is missing from %s" % here,
            "run preflight inside the unpacked %s folder; unpack the zip again into an empty folder" % BUNDLE)
        return
    want = {}
    for ln in open(sums, encoding="utf-8").read().splitlines():
        m = re.match(r"^([0-9a-f]{64}) [ *](.+)$", ln.strip())
        if m:
            want[m.group(2).replace("/", os.sep)] = m.group(1)
    bad, missing = [], []
    for rel, h in sorted(want.items()):
        p = os.path.join(here, rel)
        if not os.path.isfile(p):
            missing.append(rel)
        elif sha256_file(p) != h:
            bad.append(rel)
    have = set()
    for dp, dn, fn in os.walk(here):
        dn[:] = [d for d in dn if not is_runtime(os.path.relpath(os.path.join(dp, d), here))]
        for f in fn:
            have.add(os.path.relpath(os.path.join(dp, f), here))
    extra = sorted(x for x in have - set(want) - {"SHA256SUMS.txt"} if not is_runtime(x))
    hk = pick_host(here)[1]
    soft = lambda x: x.startswith(HOST_DIR + os.sep) and hk == "local"   # prebuilt host files replaced / removed by choice
    sm = [x for x in missing if soft(x)]
    sb = [x for x in bad if soft(x)]
    missing = [x for x in missing if not soft(x)]
    bad = [x for x in bad if not soft(x)]
    if sm or sb:
        say("WARN", "files", "prebuilt host files %s while you use host-local\\ (BMASHUP_HOST / host-local rule): %s" %
            ("removed or changed", ", ".join((sm + sb)[:6])), "fine for Option B; unpack the zip again to restore the prebuilt host")
    if missing:
        say("FAIL", "files", "%d file(s) missing: %s" % (len(missing), ", ".join(missing[:8])),
            "unpack the bundle zip again into an empty folder")
    if bad:
        say("FAIL", "files", "%d file(s) differ from SHA256SUMS.txt: %s" % (len(bad), ", ".join(bad[:8])),
            "a file was changed or damaged: unpack the zip again into an empty folder")
    if not missing and not bad and not (sm or sb):
        say("PASS", "files", "%d bundle files match SHA256SUMS.txt" % len(want))
    dlls = [x for x in extra if x.lower().endswith(".dll")]
    if dlls:
        say("FAIL", "extra DLLs", "DLLs that are not part of the bundle: %s" % ", ".join(dlls),
            "remove them: a DLL beside the exe is loaded before the system's (a vulkan-1.dll would replace the driver's)")
    other = [x for x in extra if not x.lower().endswith(".dll")]
    if other:
        say("WARN", "extra files", "not part of the bundle (allowed, but check): %s" % ", ".join(other[:10]))


def pick_host(here):
    """Which host play.cmd starts (same rule): BMASHUP_HOST=prebuilt|local, else host-local\\ if it holds a host, else host\\.
    Returns (folder, kind, why); folder is None when BMASHUP_HOST is invalid."""
    sel = (os.environ.get("BMASHUP_HOST") or "").strip().lower()
    pre = os.path.join(here, HOST_DIR)
    loc = os.path.join(here, HOST_LOCAL)
    if sel == "prebuilt":
        return pre, "prebuilt", "BMASHUP_HOST=prebuilt"
    if sel == "local":
        return loc, "local", "BMASHUP_HOST=local"
    if sel:
        return None, "?", "BMASHUP_HOST=%s is not prebuilt / local" % sel
    if os.path.isfile(os.path.join(loc, HOST_EXE)) or os.path.isfile(os.path.join(loc, RELEASE_EXE)):
        return loc, "local", "host-local\\ holds a host: your own build wins"
    return pre, "prebuilt", "host-local\\ is empty: the shipped prebuilt host"


RELEASE_EXE = "BurnoutMashup.exe"                    # BUILD MASHUP: the release-named host it installs into host-local\


def verified_build(hd, h):
    """True when hd holds a Build Mashup install for exactly this exe: BUILD_RESULT.json verified + HOST_INFO.json of the same sha256"""
    try:
        r = json.load(open(os.path.join(hd, "BUILD_RESULT.json"), encoding="utf-8"))
        i = json.load(open(os.path.join(hd, "HOST_INFO.json"), encoding="utf-8"))
        return r.get("sha256") == h == i.get("exe_sha256") and bool(r.get("verified"))
    except (OSError, ValueError, AttributeError):
        return False


def _local_identity(hd):
    try:
        return json.load(open(os.path.join(hd, "HOST_INFO.json"), encoding="utf-8"))["identity"].encode("ascii")
    except (OSError, ValueError, KeyError, AttributeError, UnicodeError):
        return None


def documented_build(hd, h):
    """True when hd holds BUILD_RESULT.json written by build-host.cmd for exactly this exe hash."""
    try:
        r = json.load(open(os.path.join(hd, "BUILD_RESULT.json"), encoding="utf-8"))
        return r.get("sha256") == h and r.get("exe", "").endswith((HOST_EXE, RELEASE_EXE)) and bool(r.get("documented_local_build"))
    except (OSError, ValueError, AttributeError):
        return False


def check_host(here):
    hd, kind, why = pick_host(here)
    if hd is None:
        say("FAIL", "host selection", why, "unset BMASHUP_HOST, or set it to prebuilt or local")
        return
    p = os.path.join(hd, RELEASE_EXE if os.path.isfile(os.path.join(hd, RELEASE_EXE)) else HOST_EXE)
    name = "prebuilt host (Option A, host\\)" if kind == "prebuilt" else "local build (Option B, host-local\\)"
    # the other host, for information
    other = os.path.join(here, HOST_LOCAL if kind == "prebuilt" else HOST_DIR, HOST_EXE)
    if not os.path.isfile(p):
        if kind == "prebuilt" and not os.path.isdir(hd):
            say("FAIL", "host exe", "no host built yet: this source tree has no prebuilt host (no host\\ folder) and host-local\\ is empty",
                "Setup tab > Build Mashup... (or build-mashup.cmd build --input <your game>): it builds, verifies and installs the host into host-local\\")
        else:
            say("FAIL", "host exe", "%s: %s is not there (%s)" % (name, p, why),
                "prebuilt: unpack the zip again (host\\ is part of the package); own build: build-host.cmd (BUILD_HOST.md)")
        return
    data = open(p, "rb").read()
    h = hashlib.sha256(data).hexdigest()
    say("INFO", "host in use", "%s - %s; %s sha256 %s (%d bytes)" % (name, why, HOST_EXE, h, len(data)))
    if os.path.isfile(other):
        say("INFO", "other host", "%s also present, sha256 %s (not used by play.cmd unless BMASHUP_HOST selects it)" %
            (other, sha256_file(other)[:16] + "..."))
    if h == HOST_SHA256:
        say("PASS", "host exe", "sha256 matches the expected reference build main21, platform 0.1.9 (%s)" % name)
    elif kind == "local" and verified_build(hd, h):
        say("PASS", "host exe", "your verified Build Mashup build (host-local\\BUILD_RESULT.json + HOST_INFO.json: identical to the "
            "reference build of this source tree, sha256 %s...)" % h[:16])
    elif kind == "local" and documented_build(hd, h):
        say("WARN", "host exe", "your local build differs from the reference main21 (expected %s...); it is recorded in "
            "host-local\\BUILD_RESULT.json, but it is UNSUPPORTED in this alpha" % HOST_SHA256[:16],
            "use the pinned toolchain (BUILD_HOST.md s2) or the prebuilt host (BMASHUP_HOST=prebuilt); report it if it persists")
    else:
        say("WARN", "host exe", "sha256 %s is neither the expected reference build (%s...) nor a documented local build "
            "(host-local\\BUILD_RESULT.json from build-host.cmd)" % (h, HOST_SHA256[:16]),
            "restore the prebuilt host by unpacking the zip again, or build with build-host.cmd")
    want_id = (_local_identity(hd) or HOST_IDENTITY) if kind == "local" and verified_build(hd, h) else HOST_IDENTITY
    if want_id in data:
        say("PASS", "host identity", "build identity %s present" % want_id.decode())
    else:
        say("FAIL" if h == HOST_SHA256 else "WARN", "host identity", "build identity %s not found in the exe" % want_id.decode())
    sdl = os.path.join(hd, "SDL2.dll")
    sdl_bad = "FAIL" if kind == "prebuilt" else "WARN"
    if not os.path.isfile(sdl):
        say("FAIL", "SDL2.dll", "missing beside the exe (Windows refuses to start the program without it)",
            "prebuilt: unpack the zip again; own build: build-host.cmd --replace puts SDL2.dll into host-local\\")
    elif sha256_file(sdl) != SDL_SHA256:
        say(sdl_bad, "SDL2.dll", "not the pinned SDL 2.32.10", "use the pinned SDL2-devel-2.32.10-mingw.tar.gz and build-host.cmd --replace")
    else:
        v = file_version(sdl)
        say("PASS", "SDL2.dll", "beside the exe%s" % (", version %d.%d.%d" % v[:3] if v else ""))
    if os.path.isfile(os.path.join(hd, "shaders", "upscale", "VERSION")):
        say("PASS", "upscale shaders", "%s\\shaders\\upscale present (only used with texture upscale on; default off)" % os.path.basename(hd))
    else:
        say("WARN", "upscale shaders", "%s\\shaders\\upscale\\VERSION missing: texture upscale stays off "
            "(the host looks only beside itself; no other location is built in)" % os.path.basename(hd),
            "build-host.cmd --replace copies them; the prebuilt host\\ ships them")
    lic = os.path.join(hd, "licenses")
    need = ["takedawn-LICENSE.txt", "xboxrecomp-LICENSE.txt", "xboxrecomp-NOTICE.txt", "xboxrecomp-LGPL-2.1.txt"]
    miss = [n for n in need if not os.path.isfile(os.path.join(lic, n))]
    if miss:
        say("WARN", "licences", "%s\\licenses lacks %s" % (os.path.basename(hd), ", ".join(miss)), "build-host.cmd --replace copies them")
    else:
        say("PASS", "licences", "%s\\licenses holds the Takedawn / xboxrecomp licence and LGPL texts" % os.path.basename(hd))
    if kind == "prebuilt" and not os.path.isdir(os.path.join(here, "lgpl-kit")):
        say("WARN", "lgpl-kit", "lgpl-kit\\ (the LGPL library source) is missing from the package", "unpack the zip again")


def check_os():
    if os.name != "nt":
        say("FAIL", "Windows", "this is not Windows (%s)" % sys.platform, "the host is a Windows x64 program")
        return False
    arch = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or "").upper()
    wv = sys.getwindowsversion()
    name = "Windows %d.%d build %d" % (wv.major, wv.minor, wv.build)
    if wv.major < 10:
        say("FAIL", "Windows version", "%s: Windows 10 or 11 x64 is required" % name)
    elif wv.build >= 22000:
        say("PASS", "Windows version", "%s (Windows 11; the alpha was tested on build 26300 only)" % name)
    else:
        say("WARN", "Windows version", "%s (Windows 10: supported in principle, NOT tested)" % name,
            "please report how it goes (docs\\BUGS_AND_CONTRIBUTING.md)")
    if arch == "AMD64":
        say("PASS", "CPU architecture", "x64 (AMD64)")
    elif arch == "ARM64":
        say("WARN", "CPU architecture", "ARM64: the x64 program runs under emulation; NOT tested")
    else:
        say("FAIL", "CPU architecture", "%s: a 64-bit x64 Windows is required" % (arch or "unknown"))
    return True


def check_system_dlls():
    s32 = system32()
    missing = [d for d in SYSTEM_DLLS if not os.path.isfile(os.path.join(s32, d))]
    if missing:
        say("FAIL", "system DLLs", "missing from %s: %s" % (s32, ", ".join(missing)),
            "these are part of Windows (ucrtbase.dll = the Universal C Runtime); install Windows updates")
    else:
        say("PASS", "system DLLs", "%d Windows DLLs present; no Visual C++ redistributable needed" % len(SYSTEM_DLLS))
    vk = os.path.join(s32, "vulkan-1.dll")
    if not os.path.isfile(vk):
        say("FAIL", "Vulkan loader", "vulkan-1.dll is not in %s" % s32,
            "install the current graphics driver from AMD, NVIDIA or Intel (it installs the Vulkan runtime)")
        return
    v = file_version(vk)
    if v and (v[0], v[1]) >= (1, 3):
        say("PASS", "Vulkan loader", "%s version %d.%d.%d" % (vk, v[0], v[1], v[2]))
    elif v:
        say("FAIL", "Vulkan loader", "version %d.%d.%d: Vulkan 1.3 is needed" % (v[0], v[1], v[2]),
            "update the graphics driver")
    else:
        say("WARN", "Vulkan loader", "%s present, version unreadable" % vk)


def check_gpu():
    exe = None
    c = os.path.join(system32(), "vulkaninfo.exe")
    if os.path.isfile(c):
        exe = c
    if not exe:
        for d in os.environ.get("PATH", "").split(os.pathsep):
            c = os.path.join(d, "vulkaninfo.exe")
            if d and os.path.isfile(c):
                exe = c
                break
    if not exe:
        say("INFO", "GPU Vulkan 1.3", "vulkaninfo not installed: the game checks the GPU at start "
            "(a message 'needs a Vulkan 1.3 graphics driver' if it is not good enough)")
        return
    try:
        r = subprocess.run([exe, "--summary"], capture_output=True, text=True, timeout=60, errors="replace")
        out = r.stdout
    except Exception as e:  # noqa: BLE001
        say("WARN", "GPU Vulkan 1.3", "vulkaninfo failed: %s" % e)
        return
    devs = []
    for block in re.split(r"\n(?=GPU\d+:)", out):
        n = re.search(r"deviceName\s*=\s*(.+)", block)
        a = re.search(r"apiVersion\s*=\s*(\d+)\.(\d+)(?:\.(\d+))?", block)
        if n and a:
            devs.append((n.group(1).strip(), int(a.group(1)), int(a.group(2)), a.group(0).split("=")[1].strip()))
    ok = [d for d in devs if (d[1], d[2]) >= (1, 3)]
    if ok:
        say("PASS", "GPU Vulkan 1.3", "; ".join("%s (Vulkan %s)" % (d[0], d[3]) for d in ok))
    elif devs:
        say("FAIL", "GPU Vulkan 1.3", "no device with Vulkan 1.3: %s" % "; ".join("%s (%s)" % (d[0], d[3]) for d in devs),
            "update the graphics driver; without Vulkan 1.3 the game is not playable")
    else:
        say("WARN", "GPU Vulkan 1.3", "vulkaninfo --summary listed no device (exit %s)" % r.returncode,
            "update the graphics driver")


def fnv_signature(header):
    hsz = struct.unpack_from("<I", header, 0x108)[0]
    if hsz == 0 or hsz > 0x10000:
        hsz = 0x1000
    h = 1469598103934665603
    for b in header[:hsz]:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return "%016X" % h


def check_data(arg, own):
    label = "game data" if own else "game data (--data)"
    p = os.path.abspath(arg)
    if os.path.basename(p.rstrip("\\/")).lower() == GAME_DIR.lower() and os.path.isfile(os.path.join(p, "default.xbe")):
        root = os.path.dirname(p.rstrip("\\/"))
        say("INFO", label, "you named the game folder itself; the data root is its parent %s" % root)
    else:
        root = p
    xbe = os.path.join(root, GAME_DIR, "default.xbe")
    if not os.path.isfile(xbe):
        if own:
            say("FAIL", label, "the bundle has no game data yet (%s not found)" % xbe,
                "run prepare.cmd data --copy-from <your installed data root>  (or --install-from <disc image or folder>); "
                "see docs\\INSTALL.md section 3")
        else:
            say("FAIL", label, "%s not found" % xbe,
                "give the folder that holds '%s\\default.xbe' (your own installed copy of the game data)" % GAME_DIR)
        return False
    with open(xbe, "rb") as f:
        head = f.read(0x10000)
    if head[:4] != b"XBEH":
        say("FAIL", label, "%s is not an Xbox executable (no XBEH magic)" % xbe)
        return False
    sig = fnv_signature(head)
    if sig == GAME_SIGNATURE:
        say("PASS", "game signature", "%s (retail NTSC-U, the only supported version)" % sig)
    else:
        say("FAIL", "game signature", "%s, expected %s: not the retail NTSC-U Burnout 3: Takedown" % (sig, GAME_SIGNATURE),
            "only the retail North American (NTSC-U) disc is supported; PAL / Japanese / modified copies are refused")
    h = sha256_file(xbe)
    if h == XBE_SHA256:
        say("PASS", "default.xbe sha256", "%s... = the retail disc's" % h[:16])
    else:
        say("WARN", "default.xbe sha256", "%s... differs from the retail disc's %s... (modified xbe?)" % (h[:16], XBE_SHA256[:16]))
    mk = os.path.join(root, ".complete")
    txt = open(mk, encoding="utf-8", errors="replace").read() if os.path.isfile(mk) else ""
    m = re.search(r"^manifest\s+(\S+)", txt, re.M)
    if txt.startswith("xr-install 1") and m and m.group(1) == MANIFEST_ID:
        say("PASS", "install marker", ".complete: manifest %s" % MANIFEST_ID)
    else:
        say("FAIL", "install marker", "%s %s" % (mk, "missing" if not txt else "is not manifest %s" % MANIFEST_ID),
            "the game starts only from a checked install: prepare.cmd data --install-from <disc image or folder>")
    dl = [f for f in os.listdir(root) if f.lower().endswith(".dll")]
    if dl:
        say("WARN", "data root DLLs", "DLLs in the data root: %s" % ", ".join(dl), "remove them")
    return True


def check_mods(here):
    demo = os.path.join(here, "mods", "demo")
    n = len([d for d in os.listdir(demo) if os.path.isfile(os.path.join(demo, d, "mod.toml"))]) if os.path.isdir(demo) else 0
    if n:
        say("PASS", "demo mods", "%d ready-made demo mods in mods\\demo" % n)
    else:
        say("FAIL", "demo mods", "mods\\demo has no mods", "unpack the zip again")
    gen = os.path.join(here, "mods", "generated")
    st = os.path.join(gen, "PREPARE_STATE.json")
    if os.path.isfile(st):
        try:
            s = json.load(open(st, encoding="utf-8"))
            say("PASS" if s.get("ok") else "WARN", "generated demos",
                "built by prepare %s: %s" % (s.get("prepare", "?"), ", ".join(s.get("mods", [])) or "none"))
        except ValueError:
            say("WARN", "generated demos", "mods\\generated\\PREPARE_STATE.json unreadable", "run prepare.cmd demos again")
    else:
        say("INFO", "generated demos", "not built yet (the coupe and the test tracks need your game data)",
            "after the game data step: prepare.cmd demos")
    user = os.path.join(here, "mods", "user")
    if os.path.isdir(user):
        mods = [d for d in os.listdir(user) if os.path.isfile(os.path.join(user, d, "mod.toml"))]
        if mods:
            say("INFO", "your mods", "mods\\user: %s" % ", ".join(sorted(mods)[:12]))
    total = 0
    for d in (demo, gen, user):
        if os.path.isdir(d):
            total += len([x for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, "mod.toml"))])
    if total > 64:
        say("FAIL", "mod count", "%d mods in mods\\demo + generated + user; the host reads at most 64" % total,
            "move mods you do not need out of mods\\user")


def check_env():
    for k in ("RECOMP_VULKAN_LOADER", "BMASHUP_SETUP", "TAKEDAWN_SETUP", "RECOMP_DEBUG"):
        if os.environ.get(k):
            say("WARN", "environment", "%s is set in this shell; play.cmd clears it for the game" % k)
    xd, home = os.environ.get("XDG_DATA_HOME"), os.environ.get("HOME")
    first = os.path.join(xd, "Takedawn", "shaders", "upscale") if xd else (
        os.path.join(home, ".local", "share", "Takedawn", "shaders", "upscale") if home else None)
    if first and os.path.isfile(os.path.join(first, "VERSION")):
        say("INFO", "upscale shaders", "%s has shaders; play.cmd clears HOME / XDG_DATA_HOME so host\\shaders\\upscale is used"
            % first)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Burnout Mashup alpha tester bundle preflight (read only)")
    ap.add_argument("--data", help="another game data root to check (holds 'Burnout 3 Takedown\\default.xbe')")
    ap.add_argument("--dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="bundle folder (default: the folder above tools\\)")
    a = ap.parse_args(argv)
    here = os.path.abspath(a.dir)
    ver = "?"
    try:
        ver = json.load(open(os.path.join(here, "BUNDLE.json"), encoding="utf-8"))["bundle"]["version"]
    except (OSError, ValueError, KeyError):
        pass
    head = "preflight - %s %s (host platform 0.1.9, reference build main21; prebuilt host or your own build) - Python %d.%d" % (BUNDLE, ver, *sys.version_info[:2])
    print(head)
    if sys.version_info < (3, 8):
        say("FAIL", "Python", "Python %d.%d; 3.8+ is needed for preflight, 3.11+ for prepare.cmd demos" % sys.version_info[:2])
    elif sys.version_info < (3, 11):
        say("WARN", "Python", "Python %d.%d: preflight works; prepare.cmd demos needs 3.11+" % sys.version_info[:2],
            "install Python 3.11 or newer from python.org")
    else:
        say("PASS", "Python", "%d.%d" % sys.version_info[:2])
    check_location(here)
    check_files(here)
    check_host(here)
    if check_os():
        check_system_dlls()
        check_gpu()
    check_data(os.path.join(here, "gamedata"), True)
    if a.data:
        check_data(a.data, False)
    check_mods(here)
    check_env()
    nf, nw = results.count("FAIL"), results.count("WARN")
    res = "RESULT %s (%d FAIL, %d WARN)" % ("FAIL" if nf else "PASS", nf, nw)
    print(res)
    try:
        os.makedirs(os.path.join(here, "diag"), exist_ok=True)
        with open(os.path.join(here, "diag", "preflight_last.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join([head] + lines + [res]) + "\n")
    except OSError:
        pass
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
