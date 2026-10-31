"""test_update_real.py - the launcher's updater with REAL builds: a copy of this checkout is the installed version, a second copy with
a version bump (signed with the TEST key of upd_testkit.py, served by a local mock channel) is the new release; the update is built
by BUILD MASHUP (bmbuild.py) from the unpacked new source. Needs your own game and the pinned toolchain; several minutes; the game is
never started.

    py -3 -B launcher\\tests\\test_update_real.py OUT.json --input GAME --toolchain TOOLCHAIN --work NEW_FOLDER
          [--source local --takedawn-src X --xboxrecomp-src Y] [--alias-root PLAIN_FOLDER]
NEW_FOLDER (outside this checkout; spaces / non-ASCII allowed) receives both copies, the new source folders, the update cache and the
build folder. The installed copy starts with a SYNTHETIC previous build in host-local (a consistent stand-in: only one real build
identity exists), so the install of the real rebuilt exe and the switch back between two different builds are both visible.
Cases: good (check -> download -> prepare -> build: clean build from the new source, exe = the manifest's reference, installed, the
synthetic build kept as previous, Play rule OK, user data untouched), switch (back: synthetic build + old source; forward again),
failed_rebuild (a release whose host layer file differs -> BUILD MASHUP refuses -> the version in use unchanged), cancel_build (cancel
while compiling -> exit 5, unchanged; resumed -> the same exe, sources switch without a build swap; switch back = source only)."""
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
REPO = os.path.dirname(SRC)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import upd_testkit as K  # noqa: E402
import bmhost  # noqa: E402
import bmupdate as U  # noqa: E402

RES = {}
A = {}
CH = None
IGN = shutil.ignore_patterns("__pycache__", "host-local*", "HOST_INFO.json", "update-state")


def arg(name, default=None):
    v = sys.argv[1:]
    return v[v.index(name) + 1] if name in v else default


def run(fn):
    t0 = time.time()
    try:
        r = fn()
        RES[fn.__name__] = ("PASS" if r is None else r) + " (%.0f s)" % (time.time() - t0)
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, " / ".join(x.strip() for x in traceback.format_exc().splitlines()[-4:-1]))
    print("%-16s %s" % (fn.__name__, RES[fn.__name__][:400]), flush=True)
    return RES[fn.__name__].startswith("PASS")


def bmu(*args, timeout=3600):
    e = dict(os.environ, PYTHONIOENCODING="utf-8", LOCALAPPDATA=A["local"])
    r = subprocess.run([sys.executable, "-B", A["bmu"]] + list(args) + ["--updates", A["upd"]], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=e, timeout=timeout, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    with open(os.path.join(A["work"], "cli.log"), "a", encoding="utf-8") as f:
        f.write("\n==== %s\n%s\n" % (" ".join(args[:2]), out))
    last = None
    for ln in out.splitlines():
        if ln.startswith("{"):
            try:
                last = json.loads(ln)
            except ValueError:
                pass
    return r.returncode, last, out


def compiler_running():
    """a clang / ninja process of this test's build folder (matched by the build folder path or its junction name b-<sha12>)"""
    import hashlib
    needles = [A["bd"].lower(), "b-" + hashlib.sha256(os.path.normcase(A["bd"]).encode("utf-8")).hexdigest()[:12]]
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    r = subprocess.run([ps, "-NoProfile", "-Command", "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [ln for ln in r.stdout.splitlines() if any(n in ln.lower() for n in needles) and ("clang" in ln.lower() or "ninja" in ln.lower())]


def wait_until(what, pred, timeout):
    """bounded readiness check (no fixed sleep)"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = pred()
        if r:
            return r
        time.sleep(0.5)
    raise AssertionError("not ready within %d s: %s" % (timeout, what))


def build_args():
    a = ["--input", A["input"], "--toolchain", A["toolchain"], "--tools", os.path.join(A["work"], "tools-empty"), "--build-dir", A["bd"],
         "--source", A["source"]]
    if A["source"] != "github":
        a += ["--takedawn-src", A["td"], "--xboxrecomp-src", A["xr"]]
    if A.get("alias_root"):
        a += ["--alias-root", A["alias_root"]]
    return a


def release(n, version, change=None):
    """a new version: a copy of this checkout with launcher\\VERSION.json release = version (+ change(tree)), zipped like git archive,
    a manifest by make-manifest, signed with the TEST key, published on the mock channel"""
    src = os.path.join(A["work"], "rel src %d" % n)
    shutil.rmtree(src, ignore_errors=True)
    shutil.copytree(REPO, src, ignore=IGN)
    vp = os.path.join(src, "launcher", "VERSION.json")
    v = json.load(open(vp, encoding="utf-8"))
    v["release"] = version
    open(vp, "w", encoding="utf-8", newline="\n").write(json.dumps(v, indent=1, sort_keys=True) + "\n")
    if change:
        change(src)
    z = K.zip_tree(src, os.path.join(A["work"], "channel", "BurnoutMashup-%s-source.zip" % version), "BurnoutMashup-%s" % version)
    data, sig = K.make_release(U, z, version, n, "bm-test")
    CH.routes["/" + os.path.basename(z)] = ("ok", open(z, "rb").read())
    CH.publish(data, sig)
    return json.loads(data)


def host():
    return bmhost.folder_state(os.path.join(A["L"], "host-local"))


def steps_of(out):
    return {ln.split("]")[0][1:]: ln.split("] ", 1)[1].split(" ")[0] for ln in out.splitlines() if ln.startswith("[") and "] " in ln}


def good():
    m = release(1, "0.1.1-test.1")
    rc, v, out = bmu("check")
    assert rc == 0 and v["cls"] == "available" and v["version"] == "0.1.1-test.1", out[-1500:]
    rc, v, out = bmu("download")
    assert rc == 0, out[-1500:]
    rc, v, out = bmu("prepare")
    assert rc == 0 and os.path.dirname(v["source"]) == A["work"], out[-1500:]
    A["new1"] = v["source"]
    rc, v, out = bmu("build", *build_args())
    assert rc == 0 and v["ok"], out[-2500:]
    st = steps_of(out)
    assert all(st.get(s) == "done" for s in ("fetch", "layers", "regen", "marks", "build", "verify", "host_info", "install")), st
    h = host()
    assert h["ok"] and h["sha256"] == m["expected"]["exe_sha256"] and v["exe_sha256"] == m["expected"]["exe_sha256"], (h, m["expected"])
    exp = json.load(open(os.path.join(REPO, "build", "EXPECTED.json"), encoding="utf-8"))["build_release"]
    assert h["sha256"] == exp["exe_sha256"] and h["identity"] == exp["identity"]
    prev = bmhost.folder_state(os.path.join(A["L"], "host-local.prev"))
    assert prev["ok"] and prev["sha256"] == A["synthetic"], prev
    ps = bmhost.play_state(A["L"])
    assert ps["host_ok"], ps["problems"]
    assert bmhost.active_source(A["L"]) == A["new1"]
    assert user_digest() == A["user"], "user data changed"
    return "PASS clean build from the new source (8 steps), exe %s = manifest reference, installed; synthetic build kept as previous" % h["sha256"][:12]


def switch():
    rc, v, out = bmu("switch-back")
    base = json.load(open(os.path.join(os.path.dirname(HERE), "VERSION.json"), encoding="utf-8"))["release"]   # this checkout's own version
    assert rc == 0 and v["now"] == base, (base, out[-800:])
    assert host()["sha256"] == A["synthetic"] and bmhost.active_source(A["L"]) == A["old"] and bmhost.play_state(A["L"])["host_ok"]
    rc, v, out = bmu("switch-back")
    assert rc == 0 and v["now"] == "0.1.1-test.1", out[-800:]
    assert host()["sha256"] == A["real"] and bmhost.active_source(A["L"]) == A["new1"] and bmhost.play_state(A["L"])["host_ok"]
    assert user_digest() == A["user"]
    return "PASS back: synthetic build + old source; forward: real build + new source; Play rule OK both ways"


def failed_rebuild():
    def change(src):
        tree = os.path.join(src, "host", "tree")
        f = next(os.path.join(dp, x) for dp, dn, fn in sorted(os.walk(tree)) for x in sorted(fn) if x.endswith(".c"))
        open(f, "a", encoding="utf-8", newline="\n").write("\n/* changed by test_update_real.py */\n")
    release(2, "0.1.2-test.1", change)
    for c in ("check", "download", "prepare"):
        rc, v, out = bmu(c)
        assert rc == 0, (c, out[-1200:])
    before = json.dumps(bmhost.load_update_state(A["L"]).get("active"), sort_keys=True)
    rc, v, out = bmu("build", *build_args())
    assert rc in (2, 3) and v["cls"] == "build" and "unchanged" in v["message"], (rc, out[-1500:])
    assert host()["sha256"] == A["real"] and bmhost.active_source(A["L"]) == A["new1"]
    assert json.dumps(bmhost.load_update_state(A["L"]).get("active"), sort_keys=True) == before
    brc, msg = rc, v["message"]
    rc, v, out = bmu("discard", "--yes")
    assert rc == 0
    return "PASS changed host layer -> %s (update exit %d), version in use unchanged; discarded" % (msg[:90], brc)


def cancel_build():
    release(3, "0.1.3-test.1", lambda src: open(os.path.join(src, "build", "build.ps1"), "a", encoding="utf-8", newline="\n").write(
        "# a comment added by test_update_real.py (cancel case)\n"))
    for c in ("check", "download", "prepare"):
        rc, v, out = bmu(c)
        assert rc == 0, (c, out[-1200:])
    e = dict(os.environ, PYTHONIOENCODING="utf-8", LOCALAPPDATA=A["local"])
    p = subprocess.Popen([sys.executable, "-B", A["bmu"], "build", "--events", "--updates", A["upd"]] + build_args(), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=e, stdin=subprocess.DEVNULL)
    seen = False
    for ln in p.stdout:
        if ln.startswith("@@ ") and '"name": "build"' in ln and '"running"' in ln:
            seen = True
            wait_until("compiler running", compiler_running, 600)      # ready = we really cancel a compile
            rc, v, o = bmu("cancel", A["bd"])
            assert rc == 0, o
            break
    rest = p.communicate(timeout=300)[0]
    assert seen and p.returncode == 5, (p.returncode, rest[-1200:])
    assert host()["sha256"] == A["real"] and bmhost.active_source(A["L"]) == A["new1"]
    rc, v, out = bmu("build", *build_args())
    assert rc == 0 and not v["host_changed"] and v["exe_sha256"] == A["real"], out[-1500:]
    st = steps_of(out)
    assert st.get("build") == "done" and st.get("regen") == "reused", st
    assert bmhost.active_source(A["L"]) != A["new1"] and bmhost.play_state(A["L"])["host_ok"]
    rc, v, out = bmu("switch-back")
    assert rc == 0 and v["now"] == "0.1.1-test.1" and bmhost.active_source(A["L"]) == A["new1"] and host()["sha256"] == A["real"], out[-600:]
    assert user_digest() == A["user"]
    return "PASS cancel while compiling -> exit 5, unchanged; resumed: compile re-run, same exe (no build swap), source switched; switch back = source only"


def user_digest():
    out = {}
    for sub in ("profile", "mods/user", "gamedata"):
        d = os.path.join(A["L"], *sub.split("/"))
        out.update({sub + "/" + k: v for k, v in U.dir_files(d).items()})
    return out


def main():
    global CH
    if len(sys.argv) < 2 or not arg("--input") or not arg("--toolchain") or not arg("--work"):
        print(__doc__)
        return 1
    A.update(input=arg("--input"), toolchain=arg("--toolchain"), work=os.path.abspath(arg("--work")), source=arg("--source", "github"),
             td=arg("--takedawn-src"), xr=arg("--xboxrecomp-src"), alias_root=arg("--alias-root"))
    if os.path.normcase(A["work"]).startswith(os.path.normcase(REPO)):
        print("--work must be outside this checkout")
        return 1
    os.makedirs(A["work"], exist_ok=True)
    A["old"] = os.path.join(A["work"], "Mashup old é")
    shutil.rmtree(A["old"], ignore_errors=True)
    shutil.copytree(REPO, A["old"], ignore=IGN)
    A["L"] = os.path.join(A["old"], "launcher")
    A["bmu"] = os.path.join(A["L"], "tools", "launcher", "bmupdate.py")         # the INSTALLED launcher's own updater
    A["upd"], A["bd"], A["local"] = os.path.join(A["work"], "upd cache"), os.path.join(A["work"], "bd upd"), os.path.join(A["work"], "local")
    A["real"] = json.load(open(os.path.join(REPO, "build", "EXPECTED.json"), encoding="utf-8"))["build_release"]["exe_sha256"]
    A["synthetic"] = K.host_folder(os.path.join(A["L"], "host-local"), "bmp-0.1.8+0123456789ab", "previous")
    shutil.copy2(os.path.join(A["L"], "host-local", "HOST_INFO.json"), os.path.join(A["old"], "HOST_INFO.json"))
    for rel, data in (("profile/Roaming/BurnoutMashup/plugin-approvals.toml", "approved = []\n"), ("profile/Roaming/BurnoutMashup/UDATA/s.bin", "save"),
                      ("mods/user/m/mod.toml", "id = 'm'\n"), ("gamedata/.complete", "test\n")):
        p = os.path.join(A["L"], *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(data)
    A["user"] = user_digest()
    CH = K.Channel()
    K.channel_config(A["L"], CH.url)
    try:
        if run(good):
            A["real"] = host()["sha256"]
            run(switch)
            run(failed_rebuild)
            run(cancel_build)
    finally:
        CH.stop()
    ok = all(v.startswith("PASS") for v in RES.values()) and len(RES) == 4
    json.dump({"results": RES, "work": A["work"], "ok": ok}, open(sys.argv[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("RESULT %s %d/4" % ("PASS" if ok else "FAIL", sum(v.startswith("PASS") for v in RES.values())))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
