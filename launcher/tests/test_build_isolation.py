"""test_build_isolation.py - BUILD MASHUP never reads or writes a separate Takedawn install's folders, and its build steps cannot.

    py -3 -B launcher\\tests\\test_build_isolation.py OUT.json
Same approach as test_isolation.py: a FAKE %APPDATA%\\Takedawn and %LOCALAPPDATA%\\Takedawn (temporary folders filled with sentinel
files); every bmbuild.py command runs under audited.py (an audit hook logs every path the process opens, lists, writes or deletes) with
APPDATA / LOCALAPPDATA pointing at the fake environment: check-input, tools, plan, download (local mock server), build refusals, a full
build when BM_TEST_XBE + BM_TEST_TOOLCHAIN (+ BM_TEST_TD / BM_TEST_XR local clones) are given, play-state, switch-back, status, cancel.
Afterwards the fake environment is byte-identical (names, sizes, sha256, times), no audited event touched a path below a fake Takedawn
folder, no sentinel appears in any output, and the build steps' environment (bmbuild.minimal_env) has no APPDATA / LOCALAPPDATA /
USERPROFILE / TAKEDAWN_* / BMASHUP_* at all. The detector is tested first (a process that does read the fake approvals IS caught)."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402
import mockhttp  # noqa: E402
SRC = pubfix.SRC
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmbuild  # noqa: E402

AUDITED = os.path.join(HERE, "audited.py")
BMB = os.path.join(SRC, "tools", "launcher", "bmbuild.py")
SENT = "TAKEDAWN-SENTINEL"
RES = {}


def case(fn):
    try:
        r = fn()
        RES[fn.__name__] = "PASS" if r is None else r
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


class Fake:
    def __init__(self):
        self.base = tempfile.mkdtemp(prefix="bm build fake env ")
        self.roaming, self.local = os.path.join(self.base, "Roaming"), os.path.join(self.base, "Local")
        self.td = [os.path.join(self.roaming, "Takedawn"), os.path.join(self.local, "Takedawn")]
        for root, rel, data in ((self.td[0], "plugin-approvals.toml", 'approved = ["a.plug sha256:%s"]\n# %s\n' % ("2" * 64, SENT)),
                                (self.td[0], "settings.toml", "x = 1\n# %s\n" % SENT),
                                (self.td[0], os.path.join("UDATA", "4541005b", "save.xbx"), SENT * 30),
                                (self.td[1], os.path.join("Game", "Burnout 3 Takedown", "default.xbe"), "XBEH " + SENT),
                                (self.td[1], os.path.join("tools", "deps", "x.txt"), SENT), (self.td[1], os.path.join("cache", "c.bin"), SENT)):
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(data)
        self.before = self.snapshot()

    def snapshot(self):
        out = {}
        for dp, dn, fn in os.walk(self.base):
            for d in dn:
                out[os.path.relpath(os.path.join(dp, d), self.base) + "\\"] = "dir"
            for f in fn:
                p = os.path.join(dp, f)
                st = os.stat(p)
                out[os.path.relpath(p, self.base)] = (st.st_size, st.st_mtime_ns, hashlib.sha256(open(p, "rb").read()).hexdigest())
        return out

    def env(self, log):
        e = {k: v for k, v in os.environ.items() if not k.upper().startswith(("TAKEDAWN_", "BMASHUP_", "RECOMP_", "BO3_"))}
        e.update(APPDATA=self.roaming, LOCALAPPDATA=self.local, BM_AUDIT_LOG=log, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        e.pop("PYTHONPATH", None)
        return e

    def violations(self, log):
        fk = [os.path.normcase(os.path.abspath(p)) for p in self.td]
        bad = []
        if os.path.isfile(log):
            for ln in open(log, encoding="utf-8", errors="replace"):
                ev, _, p = ln.rstrip("\n").partition("\t")
                n = os.path.normcase(os.path.abspath(p))
                if any(n == f or n.startswith(f + os.sep) for f in fk):
                    bad.append(ln.strip())
        return bad


F = Fake()
LOGS = []


def audited(script, *args, timeout=3600):
    log = os.path.join(tempfile.mkdtemp(prefix="bm audit "), "audit.log")
    r = subprocess.run([sys.executable, "-B", AUDITED, script] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=F.env(log), timeout=timeout, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    LOGS.append((args[:1], log, out))
    assert SENT not in out, "a sentinel leaked into the output of %s" % (args[:1],)
    return r.returncode, out, F.violations(log), log


@case
def detector_catches_a_reader():
    probe = os.path.join(tempfile.mkdtemp(), "reader.py")
    open(probe, "w").write("import os,sys\nprint(len(open(os.path.join(os.environ['APPDATA'],'Takedawn','settings.toml')).read()))\n")
    rc, out, bad, log = audited(probe)
    assert bad and "settings.toml" in bad[0], "the audit hook did not see the read"


@case
def commands_never_touch_takedawn():
    d = tempfile.mkdtemp(prefix="bm iso work ")
    xbe = os.environ.get("BM_TEST_XBE")
    inp = os.path.dirname(xbe) if xbe else d
    data = b"x" * 5000
    z = os.path.join(d, "t.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("ninja.exe", data)
    srv = mockhttp.MockServer({"/ninja-build/ninja/releases/download/v1.13.2/ninja-win.zip": ("wrong", open(z, "rb").read())})
    runs = {}
    try:
        for name, args in (("check-input", ["check-input", inp]), ("tools", ["tools"]), ("tools-dir", ["tools", "--tools", os.path.join(d, "tools")]),
                           ("plan", ["plan", "--input", inp, "--build-dir", os.path.join(d, "bd")]),
                           ("download-wrong-hash", ["download", "ninja", "--yes", "--tools", os.path.join(d, "tools"), "--mirror", srv.url]),
                           ("build-refused", ["build", "--input", d, "--build-dir", os.path.join(d, "bd")]),
                           ("build-no-tools", ["build", "--input", inp, "--build-dir", os.path.join(d, "bd")]),
                           ("play-state", ["play-state"]), ("status", ["status", "--build-dir", os.path.join(d, "bd")]),
                           ("cancel", ["cancel", "--build-dir", os.path.join(d, "bd")]), ("switch-back", ["switch-back", "--launcher", d])):
            rc, out, bad, log = audited(BMB, *args)
            assert not bad, "%s touched the fake Takedawn folders: %s" % (name, bad[:3])
            runs[name] = rc
        assert runs["download-wrong-hash"] == 2 and runs["build-refused"] == 2, runs
    finally:
        srv.stop()
    assert F.snapshot() == F.before, "the fake Takedawn environment changed"
    for v in (F.roaming, F.local):
        assert not os.path.exists(os.path.join(v, "BurnoutMashup")), "a BurnoutMashup folder was created in the fake %s" % v
    return "PASS %s" % json.dumps(runs)


@case
def full_build_never_touches_takedawn():
    xbe, tc, td, xr = (os.environ.get(k) for k in ("BM_TEST_XBE", "BM_TEST_TOOLCHAIN", "BM_TEST_TD", "BM_TEST_XR"))
    if not (xbe and tc and td and xr):
        return "SKIP (BM_TEST_XBE / BM_TEST_TOOLCHAIN / BM_TEST_TD / BM_TEST_XR not set)"
    d = tempfile.mkdtemp(prefix="bm iso build ")
    rc, out, bad, log = audited(BMB, "build", "--input", os.path.dirname(xbe), "--build-dir", os.path.join(d, "bd"), "--toolchain", tc,
                                "--tools", os.path.join(d, "tools"), "--alias-root", tempfile.mkdtemp(prefix="bmlinks"), "--source", "local",
                                "--takedawn-src", td, "--xboxrecomp-src", xr, "--no-install")
    assert rc == 0, out[-1200:]
    assert not bad, bad[:3]
    assert F.snapshot() == F.before
    for v in (F.roaming, F.local):
        assert not os.path.exists(os.path.join(v, "BurnoutMashup"))
    n = sum(1 for _ in open(log, encoding="utf-8", errors="replace"))
    return "PASS (a whole clean build under the audit hook: %d audited events, none below a Takedawn folder)" % n


@case
def steps_get_a_minimal_environment():
    env = bmbuild.minimal_env(tempfile.mkdtemp())
    for k in env:
        assert not k.upper().startswith(("TAKEDAWN_", "BMASHUP_", "PYTHON", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME")), k
    assert set(env) == {"SystemRoot", "windir", "SystemDrive", "ComSpec", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
                        "TEMP", "TMP", "PATH"}, sorted(env)


def main():
    json.dump(RES, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
    bad = {k: v for k, v in RES.items() if not str(v).startswith(("PASS", "SKIP"))}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
