"""test_build_real.py - BUILD MASHUP with REAL builds through the launcher CLI of this checkout (needs your own game and the pinned
toolchain; several minutes; nothing is launched, the game never starts).

    py -3 -B launcher\\tests\\test_build_real.py OUT.json --input GAME --toolchain TOOLCHAIN --work NEW_FOLDER
          [--source local|remote|github --takedawn-src X --xboxrecomp-src Y] [--alias-root PLAIN_FOLDER] [--only a,b,...]
GAME is read only. NEW_FOLDER (outside this checkout; spaces / non-ASCII allowed) receives the build folders and two scratch copies of
this checkout. This checkout's launcher\\host-local receives the verified build (that is what Build Mashup does).
Cases: clean (every step runs; exe = EXPECTED build_release; installed; Play rule OK), warm (every step reused), cancel_resume (cancel during
regen via the CANCEL request -> no child process left, the step's partial output removed; resume reuses fetch + layers; then the process
tree is ended during compile (what the window does when a build does not answer) -> the next run redoes that step only), incremental
(a build script changed -> only build/verify/host_info/install run, the exe is still identical; a host layer file changed -> only the layer
step runs again and is refused (pinned layers), nothing after it, the installed build stays), verify_failure (another reference ->
NOT identical, not installed, previous build kept) and install_fault (failure injected while swapping -> previous build restored).
Per-step seconds and MB are recorded (BUILD_ESTIMATES.json is made from such a run). Exit 0 = all PASS."""
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
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmhost  # noqa: E402

RES, MEAS = {}, {}
A = {}


def arg(name, default=None):
    v = sys.argv[1:]
    return v[v.index(name) + 1] if name in v else default


def case(fn):
    only = arg("--only")
    if only and fn.__name__ not in only.split(","):
        return fn
    t0 = time.time()
    try:
        r = fn()
        RES[fn.__name__] = ("PASS" if r is None else r) + " (%.0f s)" % (time.time() - t0)
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def common(repo=None):
    a = ["--input", A["input"], "--toolchain", A["toolchain"], "--tools", os.path.join(A["work"], "tools-empty"), "--source", A["source"]]
    if A["source"] != "github":
        a += ["--takedawn-src", A["td"], "--xboxrecomp-src", A["xr"]]
    if A.get("alias_root"):
        a += ["--alias-root", A["alias_root"]]
    return a


def cli(repo, *args, env=None, timeout=3600):
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    e.update(env or {})
    r = subprocess.run([sys.executable, "-B", os.path.join(repo, "launcher", "tools", "launcher", "bmbuild.py")] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=e, timeout=timeout, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    last = None
    for ln in out.splitlines():
        if ln.startswith("{"):
            try:
                last = json.loads(ln)
            except ValueError:
                pass
    with open(os.path.join(A["work"], "cli.log"), "a", encoding="utf-8") as f:
        f.write("\n==== %s\n%s\n" % (" ".join(args[:3]), out))
    return r.returncode, last, out


def state(bd):
    return json.load(open(os.path.join(bd, "BUILD_STATE.json"), encoding="utf-8"))["steps"]


def statuses(out):
    """the final state of each step in a run's output: reused / done (ran and finished) / running (ran, did not finish)"""
    return {ln.split("]")[0][1:]: ln.split("] ", 1)[1].split(" ")[0] for ln in out.splitlines() if ln.startswith("[") and "] " in ln}


def expected():
    return json.load(open(os.path.join(REPO, "build", "EXPECTED.json"), encoding="utf-8"))


def copy_repo(name):
    d = os.path.join(A["work"], name)
    if os.path.exists(d):
        shutil.rmtree(d)
    shutil.copytree(REPO, d, ignore=shutil.ignore_patterns("__pycache__", "host-local*", "HOST_INFO.json"))
    return d


def leftovers(*needles):
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    r = subprocess.run([ps, "-NoProfile", "-Command", "Get-CimInstance Win32_Process | ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    me = str(os.getpid())
    return [ln[:200] for ln in r.stdout.splitlines() if any(n and n.lower() in ln.lower() for n in needles) and not ln.startswith(me + "|")
            and "Get-CimInstance" not in ln]


def wait_until(what, pred, timeout):
    """bounded readiness check (no fixed sleep): poll pred() until it returns a true value, at most `timeout` seconds"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = pred()
        if r:
            return r
        time.sleep(0.5)
    raise AssertionError("not ready within %d s: %s" % (timeout, what))


def tool_running(alias, bd, names):
    """a child process of this build folder whose command line names one of `names` (e.g. the recompiler, clang, ninja)"""
    return [ln for ln in leftovers(alias, bd) if any(n in ln.lower() for n in names)]


@case
def clean():
    bd = os.path.join(A["work"], "bd main")
    rc, v, out = cli(REPO, "build", "--build-dir", bd, *common())
    assert rc == 0 and v["ok"], out[-1500:]
    st = statuses(out)
    assert all(st.get(s) == "done" for s in ("fetch", "layers", "regen", "marks", "build", "verify", "host_info", "install")), st
    exp = expected()["build_release"]
    assert v["exe_sha256"] == exp["exe_sha256"] and v["identity"] == exp["identity"], (v["exe_sha256"], exp["exe_sha256"])
    ps = bmhost.play_state(SRC)
    assert ps["host_ok"], ps["problems"]
    assert open(os.path.join(REPO, "HOST_INFO.json"), "rb").read() == open(os.path.join(SRC, "host-local", "HOST_INFO.json"), "rb").read()
    s = state(bd)
    MEAS["clean"] = {k: {"s": s[k].get("seconds"), "mb": s[k].get("disk_mb")} for k in s}
    MEAS["clean_total_s"] = v["seconds"]
    MEAS["clean_build_dir_mb"] = v["disk_mb"]
    return "PASS exe %s identity %s" % (v["exe_sha256"][:12], v["identity"])


@case
def warm():
    bd = os.path.join(A["work"], "bd main")
    t0 = time.time()
    rc, v, out = cli(REPO, "build", "--build-dir", bd, *common())
    sec = time.time() - t0
    st = statuses(out)
    assert rc == 0 and all(x == "reused" for x in st.values()) and len(st) == 8, (rc, st, out[-800:])
    MEAS["warm_total_s"] = round(sec, 1)
    return "PASS all 8 steps reused in %.1f s" % sec


@case
def cancel_resume():
    bd = os.path.join(A["work"], "bd cancel")
    cmd = [sys.executable, "-B", os.path.join(SRC, "tools", "launcher", "bmbuild.py"), "build", "--build-dir", bd, "--no-install", "--events"] + common()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
    alias = None
    seen_regen = False
    for ln in p.stdout:
        if ln.startswith("tool path of the build folder:"):
            alias = ln.split(":", 1)[1].strip().split(" (")[0]
        if ln.startswith("@@ ") and '"name": "regen"' in ln and '"running"' in ln:
            seen_regen = True
            # ready = the regen child (regen.py, which runs the recompiler) is alive for this build folder
            wait_until("regen child process running", lambda: tool_running(alias, bd, ("regen.py", "recomp")), 120)
            rc, v, o = cli(REPO, "cancel", "--build-dir", bd)
            assert rc == 0, o
            break
    rest = p.communicate(timeout=120)[0]
    assert seen_regen and p.returncode == 5, (p.returncode, rest[-600:])
    wait_until("no child process left after cancel: %s" % leftovers(alias, bd), lambda: not leftovers(alias, bd), 60)
    s = state(bd)
    assert s["fetch"]["status"] == "done" and s["layers"]["status"] == "done" and s["regen"]["status"] == "cancelled", {k: v["status"] for k, v in s.items()}
    assert not os.path.exists(os.path.join(bd, "s3_regen")), "the cancelled step's partial output must be removed"
    # resume; end the whole process tree during the compile step (the window's fallback when a build does not answer)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
    seen = {}
    for ln in p.stdout:
        if ln.startswith("["):
            seen[ln.split("]")[0][1:]] = ln.split("] ", 1)[1].split(" ")[0]
        if ln.startswith("@@ ") and '"name": "build"' in ln and '"running"' in ln:
            # ready = the compiler is running (clang / ninja of this build folder), i.e. we really kill a compile
            wait_until("compiler running", lambda: tool_running(alias, bd, ("clang", "ninja")), 600)
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            break
    p.wait(timeout=120)
    assert seen.get("fetch") == "reused" and seen.get("layers") == "reused" and seen.get("regen") == "done" and seen.get("marks") == "done", seen
    wait_until("no child process left after the kill: %s" % leftovers(alias, bd), lambda: not leftovers(alias, bd), 60)
    assert state(bd)["build"]["status"] == "running", "a killed run leaves its step marked running (redone next time)"
    rc, v, out = cli(REPO, "build", "--build-dir", bd, "--no-install", *common())
    st = statuses(out)
    assert rc == 0 and st.get("regen") == "reused" and st.get("marks") == "reused" and st.get("build") == "done", (rc, st, out[-800:])
    assert v["exe_sha256"] == expected()["build_release"]["exe_sha256"]
    return "PASS (cancel during regen, kill during compile, resume; exe identical)"


@case
def incremental():
    bd = os.path.join(A["work"], "bd main")
    r2 = copy_repo("repo copy 2")
    shutil.copytree(os.path.join(bd), os.path.join(A["work"], "bd incr"), symlinks=True,
                    ignore=shutil.ignore_patterns("toolchain", "tmp", "LOCK"))
    bdi = os.path.join(A["work"], "bd incr")
    ps1 = os.path.join(r2, "build", "build.ps1")
    open(ps1, "a", encoding="utf-8", newline="\n").write("# a comment added by test_build_real.py (incremental case)\n")
    rc, v, out = cli(r2, "build", "--build-dir", bdi, *common())
    st = statuses(out)
    # the compile step and what reads its output again; verify / host_info are reused because the exe they checked is unchanged
    want = {"fetch": "reused", "layers": "reused", "regen": "reused", "marks": "reused", "build": "done", "verify": "reused",
            "host_info": "reused", "install": "done"}
    assert rc == 0 and st == want, (rc, st, out[-800:])
    assert v["exe_sha256"] == expected()["build_release"]["exe_sha256"]
    l2 = os.path.join(r2, "launcher")
    before = bmhost.folder_state(os.path.join(l2, "host-local"))
    assert before["ok"]
    # a file of the host layer folder that apply_layers does not apply (host/README.md): the layer step runs again, its output is the
    # same, so every later step is reused
    open(os.path.join(r2, "host", "README.md"), "a", encoding="utf-8", newline="\n").write("\nchanged by test_build_real.py\n")
    rc, v, out = cli(r2, "build", "--build-dir", bdi, *common())
    st = statuses(out)
    assert rc == 0 and st.get("layers") == "done" and all(st[k] == "reused" for k in st if k != "layers"), (rc, st)
    # a real layer file (one of the files the layer adds to the Takedawn tree): the layer step runs again; it refuses (the layer
    # results are pinned) or, if accepted, the build that follows is not the reference one -> never installed
    tree = os.path.join(r2, "host", "tree")
    f = next(os.path.join(dp, x) for dp, dn, fn in sorted(os.walk(tree)) for x in sorted(fn) if x.endswith(".c"))
    open(f, "a", encoding="utf-8", newline="\n").write("\n/* changed by test_build_real.py */\n")
    rc, v, out = cli(r2, "build", "--build-dir", bdi, *common())
    st = statuses(out)
    after = bmhost.folder_state(os.path.join(l2, "host-local"))
    if v.get("failed_step") == "layers":
        assert rc == 3 and st == {"fetch": "reused", "layers": "running"}, (rc, st, v)
        detail = "layer file %s changed -> layers re-run and REFUSED (%s); nothing after it ran" % (os.path.relpath(f, r2), v.get("reason", "")[:90])
    else:
        assert rc == 4 and v.get("failed_step") == "verify" and st.get("regen") in ("reused", "running"), (rc, st, v)
        detail = "layer file changed -> layers..build re-run, verify NOT identical, not installed (%s)" % st
    assert after["ok"] and after["sha256"] == before["sha256"] and bmhost.play_state(l2)["host_ok"], "the installed build must stay"
    return "PASS (build.ps1 changed: build + install re-run, exe identical; README in host/: only layers re-run; %s)" % detail


@case
def verify_failure():
    r3 = copy_repo("repo copy 3")
    l3 = os.path.join(r3, "launcher")
    bd = os.path.join(A["work"], "bd verify")
    shutil.copytree(os.path.join(A["work"], "bd main"), bd, symlinks=True, ignore=shutil.ignore_patterns("toolchain", "tmp", "LOCK"))
    rc, v, out = cli(r3, "build", "--build-dir", bd, *common())
    assert rc == 0, out[-800:]
    good = bmhost.folder_state(os.path.join(l3, "host-local"))
    ep = os.path.join(r3, "build", "EXPECTED.json")
    e = json.load(open(ep, encoding="utf-8"))
    e["build_release"]["exe_sha256"] = "0" * 64
    open(ep, "w", encoding="utf-8", newline="\n").write(json.dumps(e, indent=1, sort_keys=True) + "\n")
    rc, v, out = cli(r3, "build", "--build-dir", bd, *common())
    st = statuses(out)
    assert rc == 4 and v["failed_step"] == "verify" and st.get("build") == "reused" and "install" not in st, (rc, st, v)
    now = bmhost.folder_state(os.path.join(l3, "host-local"))
    assert now["ok"] and now["sha256"] == good["sha256"] and bmhost.play_state(l3)["host_ok"]
    return "PASS (NOT identical -> rc 4, not installed, previous build in use)"


@case
def install_fault():
    bd = os.path.join(A["work"], "bd main")
    loc = os.path.join(SRC, "host-local")
    used = bmhost.folder_state(loc)
    assert used["ok"]
    # the repository's HOST_INFO.json (the Workbench copy) is gone: Play is refused and the next build repairs the install step only
    os.remove(os.path.join(REPO, "HOST_INFO.json"))
    assert not bmhost.play_state(SRC)["host_ok"]
    rc, v, out = cli(REPO, "build", "--build-dir", bd, *common(), env={"BMBUILD_FAULT_INSTALL": "swap"})
    st = statuses(out)
    assert rc == 3 and v["failed_step"] == "install" and st.get("install") == "running" and \
        all(st[k] == "reused" for k in st if k != "install"), (rc, st, v)
    now = bmhost.folder_state(loc)
    assert now["ok"] and now["sha256"] == used["sha256"], "the build in use must be restored"
    assert not os.path.exists(loc + ".new"), "no staged install may stay behind"
    os.remove(os.path.join(REPO, "HOST_INFO.json")) if os.path.exists(os.path.join(REPO, "HOST_INFO.json")) else None
    rc, v, out = cli(REPO, "build", "--build-dir", bd, *common())
    st = statuses(out)
    assert rc == 0 and st.get("install") == "done" and bmhost.play_state(SRC)["host_ok"], (rc, st, out[-600:])
    assert bmhost.folder_state(loc + ".prev")["ok"], "the install keeps the previous build"
    return "PASS (fault while swapping -> previous state restored, rc 3; the next run re-installs (install step only) and keeps the previous build)"


def main():
    A.update(input=arg("--input"), toolchain=arg("--toolchain"), work=os.path.abspath(arg("--work")), source=arg("--source", "local"),
             td=arg("--takedawn-src"), xr=arg("--xboxrecomp-src"), alias_root=arg("--alias-root"))
    out = sys.argv[1]
    os.makedirs(A["work"], exist_ok=True)
    for fn in (clean, warm, cancel_resume, incremental, verify_failure, install_fault):
        case(fn)
    json.dump({"results": RES, "measured": MEAS}, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    bad = {k: v for k, v in RES.items() if not v.startswith("PASS")}
    print(json.dumps({"cases": len(RES), "failed": bad, "measured": {k: MEAS.get(k) for k in ("clean_total_s", "warm_total_s", "clean_build_dir_mb")}}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
