"""bmbuild.py - BUILD MASHUP: build the Burnout Mashup host locally from this source tree and YOUR copy of the game (CLI; the launcher's
Build window runs exactly this). Python 3.8+, standard library. Windows x64. Original code (MIT).

    build-mashup.cmd check-input PATH                         what PATH is (game folder / disc image / default.xbe), supported or why not
    build-mashup.cmd tools [TOOL OPTIONS]                      the prerequisites: found / version / where, what can be downloaded
    build-mashup.cmd download TOOL [TOOL...] [--yes] [--tools DIR] [--downloads DIR]
                                                               explicit download of pinned tools (licence notice first; asks unless --yes)
    build-mashup.cmd plan  --input PATH [BUILD OPTIONS]        the steps, which are reused, time / disk estimates, free space
    build-mashup.cmd build --input PATH [BUILD OPTIONS]        build, verify, write HOST_INFO.json, install into host-local\\
    build-mashup.cmd status [--build-dir DIR]                  the recorded steps of a build folder
    build-mashup.cmd cancel [--build-dir DIR]                  ask a running build to stop (it kills its child processes)
    build-mashup.cmd switch-back                               use the previous build again (host-local <-> host-local.prev)
    build-mashup.cmd remove-build-dir [--build-dir DIR] --yes  delete a build folder (frees its disk space; host-local is kept)
    build-mashup.cmd head-check [TOOL...]                      real-network check of the official tool URLs (HEAD only, sizes)
    build-mashup.cmd play-state                                the Play rule: is a verified build + HOST_INFO.json installed?

TOOL OPTIONS: --tools DIR (default %LOCALAPPDATA%\\BurnoutMashup\\tools), --toolchain DIR (an existing toolchain folder), --deps DIR,
    --cmake EXE, --ninja EXE, --git EXE, --python-capstone EXE (tools you already have; versions are checked against the pins)
BUILD OPTIONS: TOOL OPTIONS + --build-dir DIR (default %LOCALAPPDATA%\\BurnoutMashup\\build; must be writable, outside the source checkout)
    --profile release|dev (default release: BurnoutMashup.exe, installed; dev: the reference development build burnout3.exe, not installed)
    --source github|local|remote [--takedawn-src X --xboxrecomp-src Y] (github: the pinned upstream repositories over the network; local:
    folders of local clones, read only; remote: any git URL, also file:///... of a local repository, cloned like a network remote)
    --download-missing (offer the missing pinned tools; each needs your yes, or --yes), --no-install, --events (machine-readable progress)

Steps (each runs the repository's own build/*.py / build.ps1, nothing else): fetch -> layers -> regen -> marks -> build -> verify ->
host_info -> install. Every step is recorded in <build dir>\\BUILD_STATE.json with the IDENTITY of its inputs (pins, script hashes, layer
files, the default.xbe sha256, the toolchain fingerprint, the profile, the outputs of the steps before it). A step whose identity is
unchanged and whose output still verifies is reused; any change re-runs it and every step after it; nothing stale is ever reused.
Children run with a minimal environment (the reference build's: no user PATH, no TAKEDAWN_* / BMASHUP_* / PYTHON* variables, TEMP inside
the build folder); tools are given by path. A build folder whose path has spaces or non-ASCII characters is reached through a junction
(the upstream CMake splits a list at spaces) in the first of %LOCALAPPDATA%\\BurnoutMashup\\links, %ProgramData%\\BurnoutMashup\\links,
C:\\BMashup-links where the junction can be made AND folders can be made, renamed and removed through it (checked every run; some
PCs refuse renames through a junction in some folders), else its 8.3 short name; nothing is elevated. Your default.xbe is read in place (a disc image: copied once into
the build folder, nothing else); generated code, objects and the exe stay in the build folder and host-local\\ (local only: never share
them). The previous working build is kept (host-local.prev) and restored when an install fails; Play is enabled only for a verified build.
Exit: 0 done, 1 usage, 2 refused (input / tools / space / folder; nothing changed), 3 a step failed (previous build unchanged),
4 built but NOT identical to the reference (not installed), 5 cancelled (completed steps are kept and reused next time).
For other programs (the launcher window; an updater that has placed a NEW verified source checkout): main(argv, out=callback) returns the
exit code and, with --events, reports progress as "@@ {json}" lines (plan / step / download / result with the recovery text); --repo
DIR builds another source checkout and --launcher DIR names the launcher folder whose host-local receives the result. Updated sources
built into the same build folder re-run only the steps whose inputs changed, and the install keeps the build in use as host-local.prev,
so "switch-back" undoes an update. Without --repo the source is bmhost.active_source(): the source folder an update installed from
(launcher\\update-state\\STATE.json, tools/launcher/bmupdate.py), else the checkout around the launcher."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmhost  # noqa: E402
import bmimage  # noqa: E402
import bmtools  # noqa: E402

LAUNCHER = bmhost.LAUNCHER
STEPS = ("fetch", "layers", "regen", "marks", "build", "verify", "host_info", "install")
SLOT = {"fetch": "s1_fetch", "layers": "s2_layers", "regen": "s3_regen", "marks": "s4_marks", "build": "s5_build", "verify": "s6_verify",
        "host_info": "s7_host_info", "install": "s8_install"}
BUILDER = "tools/launcher/bmbuild.py 1"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
EST_PATH = os.path.join(HERE, "BUILD_ESTIMATES.json")
RC_OK, RC_USAGE, RC_REFUSED, RC_FAILED, RC_NOT_IDENTICAL, RC_CANCELLED = 0, 1, 2, 3, 4, 5
RECOVERY = {
    "input": "Give the retail North American (NTSC-U) Burnout 3: Takedown: your installed game data folder, the extracted disc folder or a "
             "disc image of it. Other regions, revisions and modified files are not supported.",
    "tools": "Download the missing pinned tools (each one after you confirm it), or point the launcher at tools you already have "
             "(--toolchain / --deps / --cmake / --ninja / --git / --python-capstone). Versions must be the pinned ones (docs/BUILDING.md).",
    "space": "Free disk space on the build folder's drive or choose a build folder on another drive, then start again.",
    "folder": "Choose a build folder you can write to (not inside Program Files, not on a read-only drive, not inside the source checkout).",
    "lock": "Another build is running in this build folder: wait for it, cancel it, or use another build folder.",
    "fetch": "The pinned upstream sources could not be obtained or are not the pinned ones: check the network (github source), or use local "
             "clones that contain the pinned commits (--source local), then start again. Nothing after this step ran.",
    "layers": "The Mashup host layers do not apply to the fetched sources: the sources or this checkout differ from the pins. Use a fresh "
              "copy of this repository; completed steps before this one are reused.",
    "regen": "The recompiler did not reproduce the pinned generated code: check that the Python with capstone 5.0.9 is the pinned one and "
             "that the game file is the supported one (check-input).",
    "marks": "The hook marks do not apply exactly to your generated code: the generated code or the marks differ from the pins.",
    "build": "Compiling failed: see the build log (logs\\build.log and s5_build\\build.logs). Check the toolchain pins (tools).",
    "verify": "Your build is not byte-identical to the reference build: it was NOT installed and Play still uses your previous build. "
              "Check that every tool is the pinned version (tools) and that this checkout is unmodified; report it if it persists.",
    "host_info": "HOST_INFO.json could not be made from this build (the build's own records disagree): build again into a new build folder.",
    "install": "Installing failed and the previous build was restored: close the game if it is running from host-local, then run Build "
               "Mashup again (only the install step runs).",
    "cancelled": "Cancelled. Completed steps are kept and verified before they are reused: run Build Mashup again to continue.",
}


class Refused(Exception):
    def __init__(self, cls, msg):
        super().__init__(msg)
        self.cls = cls


class StepFailed(Exception):
    def __init__(self, step, msg, rc=RC_FAILED):
        super().__init__(msg)
        self.step, self.rc = step, rc


class Cancelled(Exception):
    pass


# ------------------------------------------------------------------------------------------------------------------ small helpers
def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def sha_f(p):
    return bmtools.sha_f(p)


def ident(obj):
    return sha_b(json.dumps(obj, sort_keys=True).encode("utf-8"))


def dir_digest(d, skip=("__pycache__", ".git")):
    man = {}
    for dp, dn, fn in os.walk(d):
        dn[:] = sorted(x for x in dn if x not in skip)
        for f in sorted(fn):
            p = os.path.join(dp, f)
            man[os.path.relpath(p, d).replace(os.sep, "/")] = sha_f(p)
    return sha_b("".join("%s  %s\n" % (v, k) for k, v in sorted(man.items())).encode()), len(man)


def is_link(p):
    """a symbolic link or a junction (never followed when sizing or removing a folder)"""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return os.path.islink(p) or bool(getattr(st, "st_file_attributes", 0) & 0x400)      # FILE_ATTRIBUTE_REPARSE_POINT


def dir_mb(d):
    n = 0
    for dp, dn, fn in os.walk(d):
        dn[:] = [x for x in dn if not is_link(os.path.join(dp, x))]
        for f in fn:
            try:
                n += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return round(n / 1e6, 1)


def jload(p, default=None):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def jsave(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, p)


def is_plain(p):
    return all(c.isascii() and (c.isalnum() or c in "_-.:\\/~") for c in p)


def short_path(p):
    try:
        import ctypes
        from ctypes import wintypes
        f = ctypes.windll.kernel32.GetShortPathNameW
        f.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        buf = ctypes.create_unicode_buffer(1024)
        n = f(p, buf, 1024)
        return buf.value if 0 < n < 1024 else None
    except (OSError, AttributeError):
        return None


def junction(link, target):
    """make (or reuse) the junction `link` -> `target`. An existing junction that points elsewhere is replaced; anything at `link`
    that is NOT a junction (a real folder or file) is never touched: OSError, the caller tries another place."""
    import _winapi
    if os.path.lexists(link):
        if not is_link(link):
            raise OSError("%s exists and is not a junction (left untouched)" % link)
        if os.path.normcase(os.path.realpath(link)) == os.path.normcase(os.path.realpath(target)):
            return link
        os.rmdir(link)                  # a junction is removed with rmdir (its target is untouched)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    _winapi.CreateJunction(target, link)
    return link


def alias_roots():
    """candidate folders for the build folder's junction, in order (each must have a plain ASCII path). %TEMP% is deliberately NOT a
    candidate: temp clean-up tools may walk into a junction there."""
    roots = [os.path.join(os.environ.get(v, ""), "BurnoutMashup", "links") for v in ("LOCALAPPDATA", "ProgramData") if os.environ.get(v)]
    return roots + [os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "BMashup-links")]


def probe_alias(link, target):
    """the file operations the build steps and tools do, done THROUGH the junction (make folders, write, rename a folder, replace a
    file, remove); also checks that the junction resolves to `target`. -> None if all work, else the first failure (text).
    Some PCs refuse renames through a junction in some folders (E16: WinError 3 under %LOCALAPPDATA% on the maintainer PC)."""
    if os.path.normcase(os.path.realpath(link)) != os.path.normcase(os.path.realpath(target)):
        return "the junction does not lead to the build folder"
    if os.environ.get("BMBUILD_FAULT_ALIAS") and any(os.path.normcase(os.path.dirname(link)) == os.path.normcase(r)
                                                     for r in os.environ["BMBUILD_FAULT_ALIAS"].split(";") if r):
        return "rename: fault injected (test)"
    name = "_aliasprobe-%d-%d" % (os.getpid(), int(time.time() * 1000) % 100000000)
    real = os.path.join(target, name)
    via = os.path.join(link, name)
    step = "make folders"
    try:
        os.makedirs(os.path.join(via, "a.partial", "sub"))
        step = "write"
        with open(os.path.join(via, "a.partial", "sub", "f.tmp"), "w") as f:
            f.write("probe")
        step = "rename a folder"
        os.rename(os.path.join(via, "a.partial"), os.path.join(via, "a"))
        step = "replace a file"
        os.replace(os.path.join(via, "a", "sub", "f.tmp"), os.path.join(via, "a", "sub", "f.json"))
        step = "remove"
        shutil.rmtree(via)
        return None
    except OSError as e:
        return "%s: %s" % (step, e)
    finally:
        shutil.rmtree(real, ignore_errors=True)      # through the real path: works even where the junction did not


def ascii_alias(path, mode="auto", alias_root=None, roots=None):
    """-> (a path to `path` without spaces / non-ASCII characters, for the tools; how it was made). The path itself if it is plain;
    else a junction in the FIRST candidate folder where creating it AND the probe through it (probe_alias) both work (each refusal
    is reported, the junction of a refused place is removed again); else the 8.3 short name; else Refused. Nothing is elevated:
    junctions need no administrator rights or developer mode. --alias-root DIR: only DIR is tried."""
    # a junction first: build.ps1 normalises paths with GetFullPath, which turns an 8.3 short name back into the long name
    if mode != "junction" and is_plain(path):
        return path, "direct"
    if roots is None:
        roots = [alias_root] if alias_root else alias_roots()
    tried = []
    if mode in ("auto", "junction"):
        for root in roots:
            if not root or not is_plain(root):
                tried.append("%s: not a plain ASCII path" % root)
                continue
            link = os.path.join(root, "b-" + sha_b(os.path.normcase(path).encode("utf-8"))[:12])
            made = False
            try:
                existed = os.path.lexists(link)
                junction(link, path)
                made = not existed
            except OSError as e:
                tried.append("%s: junction not made (%s)" % (root, e))
                continue
            bad = probe_alias(link, path)
            if bad is None:
                how = "junction in " + root
                if tried:
                    how += " (not usable: " + "; ".join(tried) + ")"
                return link, how
            tried.append("%s: junction made but %s" % (root, bad))
            try:
                if made or is_link(link):
                    os.rmdir(link)               # the refused junction itself (its target, the build folder, is untouched)
            except OSError:
                pass
    if mode in ("auto", "short") and not alias_root:
        sp = short_path(path)
        if sp and is_plain(sp):
            return sp, "8.3 short name (the build step then sees the long name: it refuses spaces)"
        tried.append("8.3 short name: not available")
    raise Refused("folder", "the build folder %s has spaces or non-ASCII characters and no plain-ASCII junction to it works on this PC "
                  "(%s): choose a build folder whose path has neither, or give --alias-root with a plain folder where you may create "
                  "folders" % (path, "; ".join(tried) or "no candidate folder"))


def default_build_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "BurnoutMashup", "build")


def inside(p, base):
    p, b = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(base))
    return p == b or p.startswith(b.rstrip("\\/") + os.sep)


def pid_alive(pid):
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259                                             # STILL_ACTIVE
    except (OSError, AttributeError, ValueError):
        return False


def kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NOWIN)


def minimal_env(tmp):
    """the reference build's environment (proof/run_pipeline.ps1 of the maintainers): system essentials only"""
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    s32 = os.path.join(sysroot, "System32")
    env = {"SystemRoot": sysroot, "windir": sysroot, "SystemDrive": os.environ.get("SystemDrive", "C:"),
           "ComSpec": os.path.join(s32, "cmd.exe"), "PATHEXT": ".COM;.EXE;.BAT;.CMD", "OS": "Windows_NT",
           "PROCESSOR_ARCHITECTURE": "AMD64", "NUMBER_OF_PROCESSORS": os.environ.get("NUMBER_OF_PROCESSORS", "4"),
           "TEMP": tmp, "TMP": tmp, "PATH": s32 + ";" + os.path.join(s32, "WindowsPowerShell", "v1.0")}
    return env


# ------------------------------------------------------------------------------------------------------------------ the build
class Build:
    def __init__(self, a, out=print, events=False):
        self.a, self.out, self.events = a, out, events
        self.repo = bmhost.active_source(os.path.abspath(a.get("launcher") or LAUNCHER)) if not a.get("repo") else os.path.abspath(a["repo"])
        if not self.repo:
            raise Refused("folder", "this launcher is not inside a Burnout Mashup source checkout (no host/PINS.json and build/verify.py beside "
                          "it): BUILD MASHUP builds from the repository it ships in")
        self.scripts = os.path.join(self.repo, "build")
        self.pins = jload(os.path.join(self.repo, "host", "PINS.json"))
        self.expected = jload(os.path.join(self.scripts, "EXPECTED.json"))
        self.profile = a.get("profile") or "release"
        if self.profile not in ("release", "dev"):
            raise Refused("input", "--profile is release or dev")
        self.bd = os.path.abspath(a.get("build_dir") or default_build_dir())
        self.launcher = os.path.abspath(a.get("launcher") or LAUNCHER)
        self.cancel_file = os.path.join(self.bd, "CANCEL")
        self.proc = None
        self._ok, self._memo = {}, {}

    # ---- output
    def say(self, msg):
        self.out(msg)
        if getattr(self, "logf", None):
            self.logf.write(msg + "\n")
            self.logf.flush()

    def ev(self, **kw):
        if self.events:
            self.out("@@ " + json.dumps(kw, sort_keys=True))

    # ---- checks before anything is written
    def check_folder(self):
        if inside(self.bd, self.repo) or inside(self.bd, self.launcher):
            raise Refused("folder", "the build folder %s is inside the source checkout / launcher folder: choose one outside (the default is "
                          "%s)" % (self.bd, default_build_dir()))
        try:
            os.makedirs(self.bd, exist_ok=True)
            probe = os.path.join(self.bd, ".write-test")
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
        except OSError as e:
            raise Refused("folder", "the build folder %s is not writable (%s)" % (self.bd, e.strerror or e))

    def check_input(self):
        want = self.expected["regen"].get("xbe_sha256")
        try:
            info = bmimage.inspect(self.a["input"], want)
        except bmimage.Refused as e:
            raise Refused("input", str(e))
        if not info["supported"]:
            raise Refused("input", "%s: %s" % (info["input"], info["reason"]))
        return info

    def check_tools(self):
        lay = bmtools.layout(self.a.get("tools"), self.a.get("toolchain"), self.a.get("deps"), self.a.get("cmake"), self.a.get("ninja"),
                             self.a.get("git"), self.a.get("python_capstone"))
        res = bmtools.check(lay)
        return lay, res

    def estimates(self):
        return jload(EST_PATH, {}) or {}

    # ---- identities
    def script_sha(self, *names):
        return {n: self._memo.setdefault("s:" + n, sha_f(os.path.join(self.scripts, n))) for n in names}

    def host_layer_digest(self):
        if "host" not in self._memo:
            self._memo["host"] = self._host_layer_digest()
        return self._memo["host"]

    def _host_layer_digest(self):
        host = os.path.join(self.repo, "host")
        man = {}
        for dp, dn, fn in os.walk(host):
            rel = os.path.relpath(dp, host).replace(os.sep, "/")
            if rel == "marks" or rel.startswith("marks/"):
                continue
            dn[:] = sorted(d for d in dn if d != "__pycache__")
            for f in sorted(fn):
                man[os.path.relpath(os.path.join(dp, f), host).replace(os.sep, "/")] = sha_f(os.path.join(dp, f))
        return ident(man)

    def identities(self, ctx, st):
        """identity of every step, from the inputs and the recorded outputs of the steps before it"""
        P, E = self.pins, self.expected
        o = lambda s: (st.get(s) or {}).get("out")  # noqa: E731
        ids = {}
        ids["fetch"] = ident({"takedawn": P["takedawn"], "xboxrecomp": P["xboxrecomp"], "scripts": self.script_sha("fetch_upstream.py", "bmb_common.py")})
        ids["layers"] = ident({"fetch": o("fetch"), "host": self.host_layer_digest(), "expected": E["host_layers"],
                               "scripts": self.script_sha("apply_layers.py", "bmb_common.py")})
        lt = (o("layers") or {})
        ids["regen"] = ident({"xbe": ctx["input"]["sha256"], "python_capstone": ctx["capstone_id"], "xboxrecomp": lt.get("xboxrecomp"),
                              "regen_inputs": lt.get("regen_inputs"), "pins": P["pristine_gen_tree_hash"], "expected": E["regen"],
                              "scripts": self.script_sha("regen.py", "bmb_common.py")})
        marks_files = {}
        for rel in ("marks/anchors.json", "marks/include/bm_gen_access.h", "marks/tools/anchors.py", "marks/tools/bm_rewrite.py"):
            p = os.path.join(self.repo, "host", *rel.split("/"))
            marks_files[rel] = sha_f(p) if os.path.isfile(p) else None
        ids["marks"] = ident({"layers": lt.get("takedawn"), "regen": o("regen"), "marks": marks_files, "pins": P["marks"],
                              "profile": self.profile, "scripts": self.script_sha("apply_marks.py", "bmb_common.py")})
        ids["build"] = ident({"marks": o("marks"), "xboxrecomp": lt.get("xboxrecomp"), "toolchain": ctx["toolchain_id"], "profile": self.profile,
                              "gen_opt": E["build"]["gen_opt_headers"], "scripts": self.script_sha("build.ps1")})
        sec = "build_release" if self.profile == "release" else "build"
        ids["verify"] = ident({"build": o("build"), "expected": ident(E.get(sec)), "toolchain_pins": E["toolchain"],
                               "scripts": self.script_sha("verify.py", "bmb_common.py")})
        ids["host_info"] = ident({"verify": o("verify"), "pins": P, "scripts": self.script_sha("host_info.py", "verify.py", "bmb_common.py")})
        ids["install"] = ident({"host_info": o("host_info"), "launcher": os.path.normcase(self.launcher), "builder": BUILDER})
        return ids

    # ---- children
    def run_child(self, step, cmd, ctx):
        logp = os.path.join(self.bd, "logs", step + ".log")
        os.makedirs(os.path.dirname(logp), exist_ok=True)
        self.say("  $ %s" % " ".join(('"%s"' % c if " " in c else c) for c in cmd)[:600])
        last = ""
        t0 = time.time()
        with open(logp, "a", encoding="utf-8", errors="replace") as lf:
            lf.write("\n==== %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(cmd)))
            self.proc = subprocess.Popen(cmd, cwd=ctx["A"], env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=NOWIN, text=True, encoding="utf-8", errors="replace",
                                         bufsize=1)
            import threading
            lines = []

            def pump():
                for ln in self.proc.stdout:
                    lines.append(ln.rstrip("\r\n"))
            th = threading.Thread(target=pump, daemon=True)
            th.start()
            shown = 0
            try:
                while True:
                    while shown < len(lines):
                        ln = lines[shown]
                        shown += 1
                        lf.write(ln + "\n")
                        if ln.startswith("{"):
                            last = ln
                        self.say("    " + ln[:400])
                    if self.proc.poll() is not None and not th.is_alive():
                        break
                    if os.path.exists(self.cancel_file):
                        raise Cancelled()
                    time.sleep(0.2)
                    if self.proc.poll() is not None:
                        th.join(2)
            except (Cancelled, KeyboardInterrupt):
                kill_tree(self.proc.pid)
                self.proc.wait()
                raise Cancelled()
            rc = self.proc.returncode
        self.proc = None
        verdict = None
        if last:
            try:
                verdict = json.loads(last)
            except ValueError:
                verdict = None
        return rc, verdict, round(time.time() - t0, 1)

    def py(self, script, *args):
        return [sys.executable, "-B", os.path.join(self.scripts, script)] + [str(x) for x in args]

    # ---- the steps (run / verify-before-reuse)
    def slot(self, ctx, step, fresh=False):
        d = os.path.join(ctx["A"], SLOT[step])
        if fresh and os.path.exists(d):
            shutil.rmtree(d)
        if fresh:
            os.makedirs(d)
        return d

    def do_fetch(self, ctx):
        s = self.slot(ctx, "fetch", fresh=True)
        src = ctx["sources"]
        rc, v, sec = self.run_child("fetch", self.py("fetch_upstream.py", "--git", ctx["lay"]["git"], "--work", s,
                                                     "--takedawn", src["takedawn"], "--xboxrecomp", src["xboxrecomp"]), ctx)
        if rc or not (v or {}).get("ok"):
            raise StepFailed("fetch", "fetch_upstream.py: %s" % ((v or {}).get("reason") or "rc %s" % rc))
        shutil.rmtree(os.path.join(s, "_git"), ignore_errors=True)       # a URL source's bare clone: not needed once verified
        return {"takedawn": v["fetched"]["takedawn"]["archive_digest"], "xboxrecomp": v["fetched"]["xboxrecomp"]["archive_digest"]}

    def ok_fetch(self, ctx, rec):
        s = os.path.join(ctx["A"], SLOT["fetch"])
        for n in ("takedawn", "xboxrecomp"):
            d = os.path.join(s, n)
            if not os.path.isdir(d) or dir_digest(d)[0] != rec["out"][n] or rec["out"][n] != self.pins[n]["archive_digest"]:
                return False
        return True

    REGEN_INPUTS = ("config/patches.json", "config/seed_functions.json", "config/spin_waits.json", "src/game/recomp/recomp_manual.c",
                    "tools/install/supported.json")

    def layer_out(self, s):
        td, xr = os.path.join(s, "takedawn"), os.path.join(s, "xboxrecomp")
        ri = {r: (sha_f(os.path.join(td, *r.split("/"))) if os.path.isfile(os.path.join(td, *r.split("/"))) else None) for r in self.REGEN_INPUTS}
        return {"takedawn": dir_digest(td)[0], "xboxrecomp": dir_digest(xr)[0], "regen_inputs": ri}

    def do_layers(self, ctx):
        s = self.slot(ctx, "layers", fresh=True)
        f = os.path.join(ctx["A"], SLOT["fetch"])
        for n in ("takedawn", "xboxrecomp"):
            shutil.copytree(os.path.join(f, n), os.path.join(s, n))
        rc, v, sec = self.run_child("layers", self.py("apply_layers.py", "host", "--takedawn", os.path.join(s, "takedawn"),
                                                      "--xboxrecomp", os.path.join(s, "xboxrecomp")), ctx)
        if rc or not (v or {}).get("ok"):
            raise StepFailed("layers", "apply_layers.py: %s" % ((v or {}).get("reason") or "rc %s" % rc))
        return self.layer_out(s)

    def ok_layers(self, ctx, rec):
        s = os.path.join(ctx["A"], SLOT["layers"])
        return os.path.isdir(os.path.join(s, "takedawn")) and self.layer_out(s) == rec["out"]

    def do_regen(self, ctx):
        s = self.slot(ctx, "regen", fresh=True)
        L = os.path.join(ctx["A"], SLOT["layers"])
        rc, v, sec = self.run_child("regen", self.py("regen.py", "--takedawn", os.path.join(L, "takedawn"), "--xboxrecomp", os.path.join(L, "xboxrecomp"),
                                                     "--xbe", ctx["xbe"], "--python", ctx["lay"]["python_capstone"], "--work", s), ctx)
        if rc or not (v or {}).get("ok"):
            raise StepFailed("regen", "regen.py: %s" % ((v or {}).get("reason") or "rc %s (see logs\\regen.log)" % rc))
        xr = os.path.join(s, "xr")                 # the recompiler's analysis folder (large, derived from your game): keep its logs only
        keep = os.path.join(s, "logs")
        os.makedirs(keep)
        for n in os.listdir(xr):
            if n.endswith((".log", ".json")) and os.path.isfile(os.path.join(xr, n)):
                shutil.copy2(os.path.join(xr, n), os.path.join(keep, n))
        shutil.rmtree(xr)
        gen = os.path.join(s, "gen_pristine")
        return {"gen_tree_hash": v["gen_tree_hash"], "stamp": sha_f(os.path.join(gen, "regen.stamp")), "files": v["files"]}

    def ok_regen(self, ctx, rec):
        gen = os.path.join(ctx["A"], SLOT["regen"], "gen_pristine")
        if not os.path.isdir(gen) or not os.path.isfile(os.path.join(gen, "regen.stamp")):
            return False
        sys.path.insert(0, self.scripts)
        import bmb_common as BC
        return BC.gen_tree_hash(gen) == rec["out"]["gen_tree_hash"] == self.pins["pristine_gen_tree_hash"] and \
            sha_f(os.path.join(gen, "regen.stamp")) == rec["out"]["stamp"]

    def do_marks(self, ctx):
        s = self.slot(ctx, "marks", fresh=True)
        L = os.path.join(ctx["A"], SLOT["layers"])
        shutil.copytree(os.path.join(L, "takedawn"), os.path.join(s, "takedawn"))
        args = ["--takedawn", os.path.join(s, "takedawn"), "--pristine", os.path.join(ctx["A"], SLOT["regen"], "gen_pristine")]
        if self.profile == "release":
            args.append("--release")
        rc, v, sec = self.run_child("marks", self.py("apply_marks.py", *args), ctx)
        if rc or not (v or {}).get("ok"):
            raise StepFailed("marks", "apply_marks.py: %s" % ((v or {}).get("reason") or "rc %s" % rc))
        return {"takedawn": dir_digest(os.path.join(s, "takedawn"))[0], "marked": v.get("marked_sha12"), "profile": self.profile}

    def ok_marks(self, ctx, rec):
        t = os.path.join(ctx["A"], SLOT["marks"], "takedawn")
        return os.path.isdir(t) and dir_digest(t)[0] == rec["out"]["takedawn"]

    def exe_name(self):
        return "BurnoutMashup.exe" if self.profile == "release" else "burnout3.exe"

    def do_build(self, ctx):
        s = self.slot(ctx, "build", fresh=True)
        L = os.path.join(ctx["A"], SLOT["layers"])
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        tc = ctx["tc"]
        cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(self.scripts, "build.ps1"),
               "-Takedawn", os.path.join(ctx["A"], SLOT["marks"], "takedawn"), "-Xboxrecomp", os.path.join(L, "xboxrecomp"),
               "-Deps", tc["deps"], "-Cmake", tc["cmake"], "-Ninja", tc["ninja"],
               "-BuildDir", os.path.join(s, "build"), "-LogDir", os.path.join(s, "build.logs")]
        if self.profile == "release":
            cmd.append("-Release")
        rc, v, sec = self.run_child("build", cmd, ctx)
        if rc or not (v or {}).get("ok"):
            raise StepFailed("build", "build.ps1 rc %s (see logs\\build.log and %s)" % (rc, os.path.join(SLOT["build"], "build.logs")))
        exe = os.path.join(s, "build", "bin", self.exe_name())
        return {"exe_sha256": sha_f(exe), "identity": v.get("identity"), "toolchain": v.get("toolchain")}

    def ok_build(self, ctx, rec):
        exe = os.path.join(ctx["A"], SLOT["build"], "build", "bin", self.exe_name())
        return os.path.isfile(exe) and sha_f(exe) == rec["out"]["exe_sha256"]

    def do_verify(self, ctx):
        s = self.slot(ctx, "verify", fresh=True)
        rc, v, sec = self.run_child("verify", self.py("verify.py", "--build-dir", os.path.join(ctx["A"], SLOT["build"], "build"),
                                                      "--profile", self.profile, "--log", os.path.join(s, "verify.json")), ctx)
        if v is None:
            raise StepFailed("verify", "verify.py gave no verdict (rc %s)" % rc)
        if not v.get("ok"):
            raise StepFailed("verify", "NOT identical to the reference build: generated objects %s, exe %s (reference %s...)" % (
                v.get("generated_objects"), v.get("exe_sha256", "?")[:12], v.get("exe_expected", "?")[:12]), RC_NOT_IDENTICAL)
        return {"ok": True, "exe_sha256": v["exe_sha256"], "identity": v["identity"], "generated_objects": v["generated_objects"]}

    def ok_verify(self, ctx, rec):
        return rec["out"].get("ok") and self.ok_build(ctx, ctx["state"]["build"])

    def do_host_info(self, ctx):
        s = self.slot(ctx, "host_info", fresh=True)
        B = os.path.join(ctx["A"], SLOT["build"])
        out = os.path.join(s, "HOST_INFO.json")
        rc, v, sec = self.run_child("host_info", self.py("host_info.py", "--build-dir", os.path.join(B, "build"),
                                                         "--takedawn", os.path.join(ctx["A"], SLOT["marks"], "takedawn"),
                                                         "--xboxrecomp", os.path.join(ctx["A"], SLOT["layers"], "xboxrecomp"),
                                                         "--log-dir", os.path.join(B, "build.logs"), "--out", out), ctx)
        if rc or not (v or {}).get("ok"):
            raise StepFailed("host_info", "host_info.py: %s" % ((v or {}).get("reason") or "rc %s" % rc))
        rc, v2, sec = self.run_child("host_info", self.py("host_info.py", "--check", out, "--exe", os.path.join(B, "build", "bin", self.exe_name())), ctx)
        if rc or not (v2 or {}).get("ok"):
            raise StepFailed("host_info", "the written HOST_INFO.json does not check against the exe: %s" % (v2 or {}).get("problems"))
        return {"sha256": sha_f(out), "identity": v["identity"], "exe_sha256": v["exe_sha256"], "platform": v["platform"]}

    def ok_host_info(self, ctx, rec):
        p = os.path.join(ctx["A"], SLOT["host_info"], "HOST_INFO.json")
        return os.path.isfile(p) and sha_f(p) == rec["out"]["sha256"] and self.ok_build(ctx, ctx["state"]["build"])

    def do_install(self, ctx):
        s = self.slot(ctx, "install", fresh=True)
        B = os.path.join(ctx["A"], SLOT["build"], "build")
        pay = os.path.join(s, "payload")
        shutil.copytree(os.path.join(B, "stage"), pay)
        shutil.copy2(os.path.join(ctx["A"], SLOT["host_info"], "HOST_INFO.json"), os.path.join(pay, "HOST_INFO.json"))
        v = ctx["state"]["verify"]["out"]
        st = ctx["state"]
        br = {"format": "bm-build-result 1", "exe": "host-local/" + bmhost.EXE, "sha256": v["exe_sha256"], "identity": v["identity"],
              "profile": self.profile, "verified": True, "identical": True, "documented_local_build": True,
              "reference_sha256": self.expected["build_release"]["exe_sha256"], "generated_objects": v["generated_objects"],
              "builder": BUILDER, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
              "steps": {k: (st.get(k) or {}).get("identity", "")[:12] for k in STEPS if k != "install"},
              "toolchain": (st["build"]["out"] or {}).get("toolchain"), "xbe_sha256": ctx["input"]["sha256"]}
        jsave(os.path.join(pay, "BUILD_RESULT.json"), br)
        if sha_f(os.path.join(pay, bmhost.EXE)) != v["exe_sha256"]:
            raise StepFailed("install", "the staged BurnoutMashup.exe is not the verified exe")
        try:
            r = bmhost.install(pay, self.launcher, fault=os.environ.get("BMBUILD_FAULT_INSTALL"), log=self.say)
        except bmhost.InstallError as e:
            raise StepFailed("install", str(e))
        shutil.rmtree(pay, ignore_errors=True)
        return {"sha256": r["sha256"], "identity": r["identity"], "host_info": ctx["state"]["host_info"]["out"]["sha256"]}

    def ok_install(self, ctx, rec):
        loc = os.path.join(self.launcher, "host-local")
        st = bmhost.folder_state(loc)
        if not st["ok"] or st.get("sha256") != rec["out"]["sha256"]:
            return False
        if sha_f(os.path.join(loc, "HOST_INFO.json")) != rec["out"]["host_info"]:
            return False
        rr = bmhost.repo_root(self.launcher)
        return not rr or (os.path.isfile(os.path.join(rr, "HOST_INFO.json")) and sha_f(os.path.join(rr, "HOST_INFO.json")) == rec["out"]["host_info"])

    # ---- main
    def prepare(self):
        """all checks that write nothing (except creating the build folder): -> ctx"""
        self.check_folder()
        info = self.check_input()
        lay, res = self.check_tools()
        missing = [k for k, v in res.items() if not v["ok"]]
        ctx = {"input": info, "lay": lay, "tools": res, "missing": missing}
        return ctx

    def plan(self, ctx):
        st = (jload(os.path.join(self.bd, "BUILD_STATE.json"), {}) or {}).get("steps", {})
        est = self.estimates().get("clean", {})
        rows = []
        for s in STEPS:
            if self.profile == "dev" and s == "install":
                continue
            rec = st.get(s) or {}
            rows.append({"step": s, "last": rec.get("status", "never"), "seconds": rec.get("seconds"), "disk_mb": rec.get("disk_mb"),
                         "estimate_s": (est.get(s) or {}).get("s"), "estimate_mb": (est.get(s) or {}).get("mb")})
        return rows

    def free_mb(self):
        if os.environ.get("BMBUILD_FREE_MB"):                 # tests: a simulated free-space value
            return float(os.environ["BMBUILD_FREE_MB"])
        return shutil.disk_usage(self.bd).free / 1e6

    def run(self):
        t_all = time.time()
        self.check_folder()
        lock = os.path.join(self.bd, "LOCK")
        old = jload(lock)
        if old and old.get("pid") != os.getpid() and pid_alive(old.get("pid", 0)):
            raise Refused("lock", "a build (process %s) is running in %s" % (old.get("pid"), self.bd))
        jsave(lock, {"pid": os.getpid(), "since": time.strftime("%Y-%m-%d %H:%M:%S")})
        if os.path.exists(self.cancel_file):
            os.remove(self.cancel_file)
        os.makedirs(os.path.join(self.bd, "logs"), exist_ok=True)
        self.logf = open(os.path.join(self.bd, "logs", "bmbuild.log"), "a", encoding="utf-8")
        try:
            return self._run(t_all)
        finally:
            self.logf.close()
            self.logf = None
            try:
                os.remove(lock)
            except OSError:
                pass

    def _run(self, t_all):
        self.say("BUILD MASHUP %s - build folder %s, profile %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), self.bd, self.profile))
        ctx = self.prepare()
        info = ctx["input"]
        self.say("input: %s (%s) - %s" % (info["input"], info["kind"], info["reason"]))
        if ctx["missing"]:
            raise Refused("tools", "missing or not the pinned version: " + "; ".join("%s (%s)" % (k, ctx["tools"][k]["problem"] or ctx["tools"][k]["found"])
                                                                                  for k in ctx["missing"]))
        lay = ctx["lay"]
        statep = os.path.join(self.bd, "BUILD_STATE.json")
        doc = jload(statep, {}) or {}
        st = doc.get("steps", {})
        for k, v in list(st.items()):
            if v.get("status") == "running":                 # killed while running (cancel from the window / a crash): redo it
                v["status"] = "interrupted"
        ctx["state"] = st
        # aliases and the toolchain view (ASCII paths, no spaces: the tools see only these)
        A, how = ascii_alias(self.bd, self.a.get("alias_mode") or "auto", self.a.get("alias_root"))
        ctx["A"] = A
        doc["alias"] = {"path": A, "how": how}           # recorded for diagnosis (the build step always starts in a fresh folder)
        self.say("tool path of the build folder: %s (%s)" % (A, how))
        tmp = os.path.join(A, "tmp")
        os.makedirs(tmp, exist_ok=True)
        ctx["env"] = minimal_env(tmp)
        view = os.path.join(A, "toolchain")
        os.makedirs(view, exist_ok=True)
        tc = {"deps": os.path.join(view, "deps")}
        os.makedirs(tc["deps"], exist_ok=True)
        for comp, path in lay["comp"].items():
            junction(os.path.join(tc["deps"], comp), path)
        junction(os.path.join(view, "cmake"), os.path.dirname(os.path.dirname(lay["cmake"])))
        junction(os.path.join(view, "ninja"), os.path.dirname(lay["ninja"]))
        tc["cmake"] = os.path.join(view, "cmake", "bin", "cmake.exe")
        tc["ninja"] = os.path.join(view, "ninja", os.path.basename(lay["ninja"]))
        ctx["tc"] = tc
        ctx["toolchain_id"], vers = bmtools.fingerprint(lay, ctx["tools"])
        pc = lay["python_capstone"]
        ctx["capstone_id"] = ident({"found": ctx["tools"]["capstone"]["found"],
                                    "dll": [sha_f(os.path.join(dp, f)) for dp, dn, fn in os.walk(os.path.join(os.path.dirname(os.path.dirname(pc)), "Lib",
                                                                                                                 "site-packages", "capstone")) for f in fn if f == "capstone.dll"]})
        src = self.a.get("source") or "github"
        if src == "github":
            ctx["sources"] = {"takedawn": self.pins["takedawn"]["repo"], "xboxrecomp": self.pins["xboxrecomp"]["repo"]}
        elif src in ("local", "remote"):
            if not self.a.get("takedawn_src") or not self.a.get("xboxrecomp_src"):
                raise Refused("input", "--source %s needs --takedawn-src and --xboxrecomp-src" % src)
            ctx["sources"] = {"takedawn": self.a["takedawn_src"], "xboxrecomp": self.a["xboxrecomp_src"]}
            if src == "local":
                for k, v in ctx["sources"].items():
                    if not os.path.isdir(v):
                        raise Refused("input", "--%s-src %s is not a folder (a local clone)" % (k, v))
        else:
            raise Refused("input", "--source is github, local or remote")
        # the xbe: read in place; a disc image's default.xbe goes into the build folder (only there)
        if info["source"] == "image":
            ctx["xbe"] = bmimage.extract_xbe(info, os.path.join(A, "xbe"))
        else:
            ctx["xbe"] = info["xbe"]
        steps = [s for s in STEPS if not (s == "install" and (self.profile == "dev" or self.a.get("no_install")))]
        # decide what runs (identity chain), then the free-space check for what will run
        doc.update(format="bm-build-state 1", profile=self.profile, input={"path": info["input"], "kind": info["kind"], "sha256": info["sha256"]},
                   sources={"mode": src, **ctx["sources"]}, toolchain={"fingerprint": ctx["toolchain_id"], "versions": vers})
        doc["steps"] = st
        est = self.estimates().get("clean", {})
        need = sum(float((est.get(s) or {}).get("mb", 0)) for s in steps if not self._reusable(ctx, s, st))
        free = self.free_mb()
        self.ev(ev="plan", steps=steps, free_mb=round(free), need_mb=round(need))
        self.say("free space %.0f MB on the build folder's drive; this run needs about %.0f MB (+ 500 MB margin)" % (free, need))
        if free < need + 500:
            raise Refused("space", "not enough free space in %s: about %.0f MB needed (+500 MB margin), %.0f MB free" % (self.bd, need, free))
        jsave(os.path.join(self.bd, "BUILD_STATE.json"), doc)
        summary = {}
        for s in steps:
            if os.path.exists(self.cancel_file):
                st.setdefault(s, {})["status"] = "cancelled"
                jsave(statep, doc)
                raise Cancelled()
            ids = self.identities(ctx, st)
            rec = st.get(s)
            if self._reusable(ctx, s, st):
                self.say("[%s] reused (inputs unchanged, output verified)" % s)
                summary[s] = {"status": "reused", "seconds": 0, "disk_mb": rec.get("disk_mb")}
                self.ev(ev="step", name=s, status="reused", seconds=0, disk_mb=rec.get("disk_mb"))
                continue
            why = "first run" if not rec else ("inputs changed" if rec.get("identity") != ids[s] else
                                               "previous run %s" % rec.get("status") if rec.get("status") != "done" else "output no longer verifies")
            # the steps after this one see its new output in their identities: each is reused only if what IT reads is unchanged
            st[s] ={"status": "running", "identity": ids[s], "started": time.strftime("%Y-%m-%d %H:%M:%S"), "why": why}
            jsave(statep, doc)
            self.say("[%s] running (%s)" % (s, why))
            self.ev(ev="step", name=s, status="running", why=why)
            t0 = time.time()
            try:
                out = getattr(self, "do_" + s)(ctx)
            except Cancelled:
                st[s].update(status="cancelled", seconds=round(time.time() - t0, 1))
                shutil.rmtree(os.path.join(ctx["A"], SLOT[s]), ignore_errors=True)
                jsave(statep, doc)
                self.ev(ev="step", name=s, status="cancelled")
                raise
            except StepFailed as e:
                st[s].update(status="failed", seconds=round(time.time() - t0, 1), message=str(e))
                jsave(statep, doc)
                self.ev(ev="step", name=s, status="failed", message=str(e))
                raise
            except (OSError, shutil.Error) as e:
                st[s].update(status="failed", seconds=round(time.time() - t0, 1), message=str(e))
                jsave(statep, doc)
                self.ev(ev="step", name=s, status="failed", message=str(e))
                raise StepFailed(s, "%s: %s" % (type(e).__name__, e))
            sec = round(time.time() - t0, 1)
            mb = dir_mb(os.path.join(ctx["A"], SLOT[s])) if s != "install" else dir_mb(os.path.join(self.launcher, "host-local"))
            st[s].update(status="done", out=out, seconds=sec, disk_mb=mb, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
            jsave(statep, doc)
            summary[s] = {"status": "done", "seconds": sec, "disk_mb": mb}
            self.say("[%s] done in %.1f s, %.1f MB" % (s, sec, mb))
            self.ev(ev="step", name=s, status="done", seconds=sec, disk_mb=mb)
        doc["last_result"] = {"ok": True, "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t_all, 1),
                              "summary": summary}
        jsave(statep, doc)
        v = st["verify"]["out"]
        res = {"ok": True, "profile": self.profile, "exe": self.exe_name(), "exe_sha256": v["exe_sha256"], "identity": v["identity"],
               "installed": None if "install" not in steps else os.path.join(self.launcher, "host-local"), "steps": summary,
               "seconds": round(time.time() - t_all, 1), "build_dir": self.bd, "disk_mb": dir_mb(self.bd)}
        return res

    def _reusable(self, ctx, s, st):
        """recorded as done, same input identity, and its output verifies now (memoised per identity within one run)"""
        try:
            ids = self.identities(ctx, st)
            rec = st.get(s)
            if not (rec and rec.get("status") == "done" and rec.get("identity") == ids[s]):
                return False
            key = (s, ids[s])
            if key not in self._ok:
                self._ok[key] = bool(getattr(self, "ok_" + s)(ctx, rec))
            return self._ok[key]
        except (KeyError, TypeError, OSError):
            return False


# ------------------------------------------------------------------------------------------------------------------ CLI
def parse(argv):
    a = {"cmd": argv[0] if argv else "help", "args": []}
    flags = {"--yes": "yes", "--download-missing": "download_missing", "--no-install": "no_install", "--events": "events", "--json": "json"}
    i = 1
    while i < len(argv):
        x = argv[i]
        if x in flags:
            a[flags[x]] = True
        elif x.startswith("--"):
            if i + 1 >= len(argv):
                raise SystemExit("usage: %s needs a value" % x)
            a[x[2:].replace("-", "_")] = argv[i + 1]
            i += 1
        else:
            a["args"].append(x)
        i += 1
    return a


def confirm(p, a, ask=input):
    print(bmtools.notice_text(p), flush=True)
    if a.get("yes"):
        print("  -> confirmed by --yes", flush=True)
        return True
    try:
        return ask("Download it? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def download(ids, a, out=print, ask=input):
    tools_dir = os.path.abspath(a.get("tools") or bmtools.default_tools_dir())
    S = bmtools.spec()
    order = []

    def add(t):
        for n in S[t]["needs"]:
            add(n)
        if t not in order:
            order.append(t)
    for t in ids:
        if t not in S:
            raise SystemExit("usage: unknown tool %s (one of %s)" % (t, ", ".join(S)))
        add(t)
    done, failed = [], {}
    for t in order:
        lay = bmtools.layout(tools_dir, a.get("toolchain"), a.get("deps"), a.get("cmake"), a.get("ninja"), a.get("git"), a.get("python_capstone"))
        res = bmtools.check(lay)
        if res.get(t, {}).get("ok"):
            out("%s: already present (%s at %s)" % (t, res[t]["found"], res[t]["path"]))
            continue
        p = bmtools.plan_download(t, tools_dir, a.get("mirror"))
        if a.get("downloads") and S[t]["archive"] and os.path.isfile(os.path.join(a["downloads"], S[t]["archive"])):
            out("%s: using your downloaded archive %s (checked against the pinned sha256)" % (t, os.path.join(a["downloads"], S[t]["archive"])))
        elif not confirm(p, a, ask):
            out("%s: not downloaded (not confirmed)" % t)
            failed[t] = "not confirmed"
            continue
        try:
            def prog(n, total, t=t):
                out("@@ " + json.dumps({"ev": "download", "tool": t, "bytes": n, "total": total}) if a.get("events") else
                    "  %s: %.1f / %.1f MB" % (t, n / 1e6, (total or 0) / 1e6))
            dest = bmtools.acquire(t, tools_dir, a.get("downloads"), a.get("mirror"), log=out, progress=prog, lay=lay)
            done.append(t)
            out("%s: installed into %s" % (t, dest))
        except bmtools.ToolError as e:
            failed[t] = str(e)
            out("%s: FAILED - %s" % (t, e))
    return {"ok": not failed, "installed": done, "failed": failed, "tools_dir": tools_dir}


def remove_build_dir(bd, yes=False, out=print):
    """delete a BUILD MASHUP build folder (only one that holds BUILD_STATE.json; junctions are unlinked first, their targets - your
    toolchain - are never entered). host-local\\ and your game files are not touched."""
    if not os.path.isfile(os.path.join(bd, "BUILD_STATE.json")):
        return {"removed": False, "reason": "%s is not a Build Mashup build folder (no BUILD_STATE.json): not touched" % bd}
    st = jload(os.path.join(bd, "LOCK"))
    if st and pid_alive(st.get("pid", 0)):
        return {"removed": False, "reason": "a build is running in it"}
    if not yes:
        return {"removed": False, "reason": "add --yes to delete %s (%.0f MB)" % (bd, dir_mb(bd))}
    links = 0
    al = ((jload(os.path.join(bd, "BUILD_STATE.json"), {}) or {}).get("alias") or {}).get("path")
    if (al and os.path.normcase(al) != os.path.normcase(bd) and is_link(al)
            and os.path.normcase(os.path.realpath(al)) == os.path.normcase(os.path.realpath(bd))):
        os.rmdir(al)                             # the build folder's own junction (only when it still leads to this folder)
        links += 1
    for dp, dn, fn in os.walk(bd, topdown=True):
        keep = []
        for x in dn:
            p = os.path.join(dp, x)
            if is_link(p):
                os.rmdir(p)                      # removes the junction itself, not what it points to
                links += 1
            else:
                keep.append(x)
        dn[:] = keep
    shutil.rmtree(bd)
    out("removed %s (%d junctions unlinked first)" % (bd, links))
    return {"removed": True, "junctions": links}


def main(argv=None, out=None):
    argv = sys.argv[1:] if argv is None else argv
    pr = out or (lambda s: print(s, flush=True))
    try:
        a = parse(argv)
    except SystemExit as e:
        pr(str(e))
        return RC_USAGE
    cmd = a["cmd"]
    try:
        if cmd in ("help", "-h", "--help"):
            pr(__doc__)
            return RC_OK
        if cmd == "check-input":
            if not a["args"]:
                pr("usage: check-input PATH")
                return RC_USAGE
            exp = jload(os.path.join(bmhost.active_source(os.path.abspath(a.get("launcher") or LAUNCHER)) or "", "build", "EXPECTED.json"), {}) or {}
            want = (exp.get("regen") or {}).get("xbe_sha256")
            try:
                info = bmimage.inspect(a["args"][0], want)
            except bmimage.Refused as e:
                pr(json.dumps({"supported": False, "reason": str(e), "refused": True}))
                pr("REFUSED: %s\nWhat to do: %s" % (e, RECOVERY["input"]))
                return RC_REFUSED
            info = {k: v for k, v in info.items() if k not in ("image_entry",)}
            pr(json.dumps(info, sort_keys=True))
            pr(("SUPPORTED: " if info["supported"] else "NOT SUPPORTED: ") + info["reason"])
            return RC_OK if info["supported"] else RC_REFUSED
        if cmd == "tools":
            lay = bmtools.layout(a.get("tools"), a.get("toolchain"), a.get("deps"), a.get("cmake"), a.get("ninja"), a.get("git"), a.get("python_capstone"))
            res = bmtools.check(lay)
            S = bmtools.spec()
            for k, v in res.items():
                offer = ""
                if not v["ok"] and k in S:
                    offer = "  -> offer: download %s %s (%s, %s) from %s" % (S[k]["name"], S[k]["version"],
                                                                            "%.0f MB" % (S[k]["size"] / 1e6) if S[k]["size"] else "pip", S[k]["licence"].split(" (")[0], S[k]["url"])
                pr("%-10s %-4s %-40s %s%s" % (k, "OK" if v["ok"] else "MISS", v["found"][:40], v["path"], ("  [" + v["problem"] + "]") if v["problem"] else "") + offer)
            pr(json.dumps({"ok": all(v["ok"] for v in res.values()), "missing": [k for k, v in res.items() if not v["ok"]], "tools_dir": lay["tools_dir"]}))
            return RC_OK if all(v["ok"] for v in res.values()) else RC_REFUSED
        if cmd == "download":
            if not a["args"]:
                pr("usage: download TOOL [TOOL...] (%s)" % ", ".join(bmtools.spec()))
                return RC_USAGE
            r = download(a["args"], a, out=pr)
            pr(json.dumps(r, sort_keys=True))
            return RC_OK if r["ok"] else RC_REFUSED
        if cmd == "head-check":
            r = [bmtools.head_check(t) for t in (a["args"] or [t for t, v in bmtools.spec().items() if v["archive"]])]
            pr(json.dumps(r))
            return RC_OK
        if cmd == "play-state":
            r = bmhost.play_state(os.path.abspath(a.get("launcher") or LAUNCHER))
            r.pop("state", None)
            pr(json.dumps(r, sort_keys=True))
            return RC_OK if r["host_ok"] else RC_REFUSED
        if cmd == "switch-back":
            try:
                r = bmhost.switch_back(os.path.abspath(a.get("launcher") or LAUNCHER), log=pr)
            except bmhost.InstallError as e:
                pr("REFUSED: %s" % e)
                return RC_REFUSED
            pr(json.dumps(r))
            return RC_OK
        bd = os.path.abspath(a.get("build_dir") or default_build_dir())
        if cmd == "status":
            pr(json.dumps(jload(os.path.join(bd, "BUILD_STATE.json"), {"steps": {}}), indent=1, sort_keys=True))
            return RC_OK
        if cmd == "remove-build-dir":
            r = remove_build_dir(bd, a.get("yes"), out=pr)
            pr(json.dumps(r))
            return RC_OK if r.get("removed") else RC_REFUSED
        if cmd == "cancel":
            if not os.path.isdir(bd):
                pr("no build folder %s" % bd)
                return RC_REFUSED
            open(os.path.join(bd, "CANCEL"), "w").close()
            pr("cancel requested in %s" % bd)
            return RC_OK
        if cmd not in ("plan", "build"):
            pr("usage: unknown command %s (help)" % cmd)
            return RC_USAGE
        if not a.get("input"):
            pr("usage: %s --input PATH (your game folder, disc image or default.xbe)" % cmd)
            return RC_USAGE
        b = Build(a, out=pr, events=a.get("events"))
        if cmd == "plan":
            ctx = b.prepare()
            rows = b.plan(ctx)
            est = b.estimates()
            free = b.free_mb()
            pr(json.dumps({"input": {k: ctx["input"][k] for k in ("input", "kind", "supported", "reason", "sha256")}, "missing_tools": ctx["missing"],
                           "steps": rows, "free_mb": round(free), "estimate": {k: est.get(k) for k in ("clean_total_s", "clean_total_mb", "warm_total_s", "measured")},
                           "build_dir": b.bd}, sort_keys=True))
            return RC_OK
        if a.get("download_missing"):
            lay, res = b.check_tools()
            miss = [k for k, v in res.items() if not v["ok"] and k in bmtools.spec()]
            if miss:
                r = download(miss, a, out=pr)
                if not r["ok"]:
                    raise Refused("tools", "not all missing tools were installed: %s" % r["failed"])
        try:
            res = b.run()
        except Refused as e:
            pr(json.dumps({"ok": False, "refused": e.cls, "reason": str(e), "recovery": RECOVERY.get(e.cls, "")}))
            pr("REFUSED (%s): %s\nWhat to do: %s" % (e.cls, e, RECOVERY.get(e.cls, "")))
            b.ev(ev="result", rc=RC_REFUSED, cls=e.cls, message=str(e), recovery=RECOVERY.get(e.cls, ""))
            return RC_REFUSED
        except StepFailed as e:
            pr(json.dumps({"ok": False, "failed_step": e.step, "reason": str(e), "recovery": RECOVERY.get(e.step, ""),
                           "previous_build": "unchanged (host-local)"}))
            pr("FAILED at %s: %s\nWhat to do: %s" % (e.step, e, RECOVERY.get(e.step, "")))
            b.ev(ev="result", rc=e.rc, cls=e.step, message=str(e), recovery=RECOVERY.get(e.step, ""))
            return e.rc
        except Cancelled:
            pr(json.dumps({"ok": False, "cancelled": True, "recovery": RECOVERY["cancelled"]}))
            pr("CANCELLED. %s" % RECOVERY["cancelled"])
            b.ev(ev="result", rc=RC_CANCELLED, cls="cancelled", message="cancelled", recovery=RECOVERY["cancelled"])
            return RC_CANCELLED
        pr(json.dumps(res, sort_keys=True))
        pr("DONE: %s %s (%s) verified%s." % (res["exe"], res["exe_sha256"][:12], res["identity"],
                                             ", installed into host-local" if res["installed"] else ""))
        b.ev(ev="result", rc=RC_OK, cls="done", message="verified" + (" and installed" if res["installed"] else ""), recovery="")
        return RC_OK
    except Refused as e:
        pr(json.dumps({"ok": False, "refused": e.cls, "reason": str(e), "recovery": RECOVERY.get(e.cls, "")}))
        pr("REFUSED (%s): %s\nWhat to do: %s" % (e.cls, e, RECOVERY.get(e.cls, "")))
        return RC_REFUSED
    except KeyboardInterrupt:
        pr("CANCELLED")
        return RC_CANCELLED


if __name__ == "__main__":
    sys.exit(main())
