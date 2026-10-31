"""test_build.py - BUILD MASHUP without a real build (fast; no game files needed, no network, nothing launched).

    py -3 -B launcher\\tests\\test_build.py OUT.json
Optional (owner-supplied, READ ONLY): BM_TEST_XBE = a supported default.xbe (input + image-extract cases), BM_TEST_TOOLCHAIN = a folder
with the pinned toolchain (tool detection and the free-space / lock refusals that come after the tool check), BM_TEST_DL_DIR = a
folder holding the pinned ninja-win.zip (a REAL archive served by the local mock server under its official path).
Cases: inputs (game folder, not a game folder, other game, other region, other revision, plain file, disc image incl. a truncated one),
tools (all missing -> offers; pins = tools/prepare_deps.py), downloads through a local mock server (OK, 404, wrong sha256, interrupted,
size mismatch, not confirmed), refusals of the build command (input, tools, low disk (simulated), read-only folder, folder inside the
checkout, a running build's lock), the install / previous build / switch back / Play rule with synthetic hosts (incl. failures injected
at each install point), and the Build window + the launcher window (headless). Writes only temporary folders. Exit 0 = all PASS."""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (sandboxed %APPDATA% / %LOCALAPPDATA% for this process)
SRC = pubfix.SRC
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
sys.path.insert(0, os.path.join(SRC, "tools"))
import bmbuild  # noqa: E402
import bmhost  # noqa: E402
import bmimage  # noqa: E402
import bmtools  # noqa: E402
import mockhttp  # noqa: E402

RES = {}
WANT = json.load(open(os.path.join(pubfix.REPO, "build", "EXPECTED.json"), encoding="utf-8"))["regen"]["xbe_sha256"]
XBE = os.environ.get("BM_TEST_XBE")
TC = os.environ.get("BM_TEST_TOOLCHAIN")
BMB = os.path.join(SRC, "tools", "launcher", "bmbuild.py")


def case(fn):
    try:
        r = fn()
        RES[fn.__name__] = "PASS" if r is None else r
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def tmp(prefix="bm build test "):
    return tempfile.mkdtemp(prefix=prefix)


def fake_xbe(title_id=0x4541005B, title="Burnout 3", region=1, version=1, pad=8192):
    b = bytearray(0x1000)
    b[0:4] = b"XBEH"
    struct.pack_into("<I", b, 0x104, 0x10000)
    struct.pack_into("<I", b, 0x118, 0x10000 + 0x200)
    struct.pack_into("<I", b, 0x200 + 0x8, title_id)
    nm = title.encode("utf-16-le")
    b[0x20C:0x20C + len(nm)] = nm
    struct.pack_into("<I", b, 0x200 + 0xA0, region)
    struct.pack_into("<I", b, 0x200 + 0xAC, version)
    return bytes(b) + os.urandom(pad)


def fake_image(xbe_bytes, path, cut=None):
    S = 2048
    img = bytearray(34 * S)
    vd = bytearray(S)
    vd[0:20] = bmimage.XDVD_MAGIC
    struct.pack_into("<II", vd, 20, 33, S)
    vd[0x7EC:0x7EC + 20] = bmimage.XDVD_MAGIC
    img[32 * S:33 * S] = vd
    ent = struct.pack("<HHIIBB", 0, 0, 34, len(xbe_bytes), 0x20, 11) + b"default.xbe"
    tbl = bytearray(b"\xff" * S)
    tbl[:len(ent)] = ent
    img[33 * S:34 * S] = tbl
    img += xbe_bytes
    data = bytes(img)
    if cut:
        data = data[:cut]
    open(path, "wb").write(data)
    return path


def run_cli(*args, env=None, timeout=600):
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    e.update(env or {})
    r = subprocess.run([sys.executable, "-B", BMB] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=e, timeout=timeout, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    last = None
    for ln in out.splitlines():
        if ln.startswith("{"):
            try:
                last = json.loads(ln)
            except ValueError:
                pass
    return r.returncode, last, out


# ------------------------------------------------------------------------------------------------------------------ inputs
@case
def input_refusals():
    d = tmp()
    try:
        bmimage.inspect(d, WANT)
        raise AssertionError("an empty folder was accepted")
    except bmimage.Refused as e:
        assert "not a game folder" in str(e), e
    try:
        bmimage.inspect(os.path.join(d, "nope"), WANT)
        raise AssertionError("a missing path was accepted")
    except bmimage.Refused as e:
        assert "does not exist" in str(e)
    p = os.path.join(d, "notes.txt")
    open(p, "w").write("x")
    try:
        bmimage.inspect(p, WANT)
        raise AssertionError("a text file was accepted")
    except bmimage.Refused as e:
        assert "not a disc image" in str(e)
    g = os.path.join(d, "other game", "default.xbe")
    os.makedirs(os.path.dirname(g))
    open(g, "wb").write(fake_xbe(title_id=0x4D530004, title="Some Other Game"))
    i = bmimage.inspect(os.path.dirname(g), WANT)
    assert not i["supported"] and "not Burnout 3" in i["reason"], i["reason"]
    pal = os.path.join(d, "pal", bmimage.GAME_DIR, "default.xbe")
    os.makedirs(os.path.dirname(pal))
    open(pal, "wb").write(fake_xbe(region=4))
    i = bmimage.inspect(os.path.dirname(os.path.dirname(pal)), WANT)
    assert not i["supported"] and "Europe" in i["reason"] and i["kind"] == "installed game data folder", i
    rev = os.path.join(d, "rev", "default.xbe")
    os.makedirs(os.path.dirname(rev))
    open(rev, "wb").write(fake_xbe(version=2))
    i = bmimage.inspect(rev, WANT)
    assert not i["supported"] and "another revision or a modified executable" in i["reason"], i["reason"]
    bad = os.path.join(d, "junk", "default.xbe")
    os.makedirs(os.path.dirname(bad))
    open(bad, "wb").write(b"MZ not an xbe" * 100)
    try:
        bmimage.inspect(bad, WANT)
        raise AssertionError("a non-XBE default.xbe was accepted")
    except bmimage.Refused as e:
        assert "not an Xbox executable" in str(e)
    rc, v, out = run_cli("check-input", d)
    assert rc == 2 and v and v["refused"] and "What to do" in out, (rc, out[-300:])


@case
def input_disc_images():
    d = tmp("bm image test ")
    x = fake_xbe(version=3)
    img = fake_image(x, os.path.join(d, "game.iso"))
    i = bmimage.inspect(img, WANT)
    assert i["source"] == "image" and i["sha256"] == hashlib.sha256(x).hexdigest() and not i["supported"], i
    cut = fake_image(x, os.path.join(d, "cut.iso"), cut=34 * 2048 + 1000)
    try:
        bmimage.inspect(cut, WANT)
        raise AssertionError("a truncated image was accepted")
    except bmimage.Refused as e:
        assert "truncated" in str(e), e
    tiny = os.path.join(d, "tiny.iso")
    open(tiny, "wb").write(b"\0" * 5000)
    try:
        bmimage.inspect(tiny, WANT)
        raise AssertionError("a tiny image was accepted")
    except bmimage.Refused as e:
        assert "truncated" in str(e) or "not" in str(e)
    junk = os.path.join(d, "junk.xiso")
    open(junk, "wb").write(os.urandom(200000))
    try:
        bmimage.inspect(junk, WANT)
        raise AssertionError("random bytes were accepted as an image")
    except bmimage.Refused as e:
        assert "XDVDFS" in str(e)
    rc, v, out = run_cli("check-input", cut)
    assert rc == 2 and "truncated" in out, out[-300:]
    if not XBE:
        return "PASS (synthetic images; the real-xbe image case needs BM_TEST_XBE)"
    real = open(XBE, "rb").read()                    # the owner's file, read only: put into a TEMPORARY test image, deleted below
    try:
        img2 = fake_image(real, os.path.join(d, "real.iso"))
        i = bmimage.inspect(img2, WANT)
        assert i["supported"], i["reason"]
        out_dir = os.path.join(d, "build", "xbe")
        p = bmimage.extract_xbe(i, out_dir)
        assert hashlib.sha256(open(p, "rb").read()).hexdigest() == WANT and os.path.dirname(p) == out_dir
        i2 = bmimage.inspect(os.path.dirname(XBE), WANT)
        assert i2["supported"] and i2["xbe"] == os.path.abspath(XBE) and bmimage.extract_xbe(i2, out_dir + "2") == i2["xbe"]
        assert not os.path.exists(out_dir + "2"), "a folder input must be read in place, never copied"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------------------ tools
@case
def tools_missing_and_offers():
    d = tmp()
    lay = bmtools.layout(d)
    res = bmtools.check(lay)
    for k in ("llvm-mingw", "cmake", "ninja", "sdl2", "glslang", "vulkan", "capstone"):
        assert not res[k]["ok"] and res[k]["where"].startswith("tools folder"), (k, res[k])
    rc, v, out = run_cli("tools", "--tools", d)
    assert rc == 2 and "offer: download" in out and "Apache-2.0" in out and v["missing"], out[-500:]
    assert not os.listdir(d), "checking the tools must not write anything"


@case
def tools_pins_match_prepare_deps():
    import prepare_deps
    S = bmtools.spec()
    by_name = {t["archive"]: t for t in S.values() if t["archive"]}
    for name, sha, url, req in prepare_deps.PINS:
        t = by_name[name]
        assert t["sha256"] == sha and t["url"] == url, name
    assert bmtools.GLSLANG_OPTS == prepare_deps.GLSLANG_OPTS
    for t in S.values():
        assert t["licence"] and t["licence_note"] and t["licence_url"].startswith("https://"), t["id"]


@case
def tools_given_toolchain():
    if not TC:
        return "SKIP (BM_TEST_TOOLCHAIN not set)"
    res = bmtools.check(bmtools.layout(tmp(), TC))
    bad = {k: v["problem"] for k, v in res.items() if not v["ok"]}
    assert not bad, bad
    fp1, v1 = bmtools.fingerprint(bmtools.layout(tmp(), TC), res)
    assert len(fp1) == 64 and v1["cmake"] == "cmake 4.4.4"


# ------------------------------------------------------------------------------------------------------------------ downloads
def _spec_with(test_tools):
    real = bmtools.spec

    def fake():
        s = real()
        s.update(test_tools)
        return s
    return fake


@case
def downloads_mock_server():
    z = os.path.join(tmp(), "t.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("ninja.exe", b"MZ fake ninja " * 1000)
    data = open(z, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    srv = mockhttp.MockServer({"/rel/ok.zip": ("ok", data), "/rel/cut.zip": ("cut", data), "/rel/bad.zip": ("wrong", data),
                               "/rel/short.zip": ("ok", data[:-10])})
    try:
        d = tmp()
        out = {}
        for name, path, want in (("ok", "/rel/ok.zip", None), ("404", "/rel/gone.zip", "HTTP 404"), ("cut", "/rel/cut.zip", "interrupted"),
                                 ("wrong", "/rel/bad.zip", "integrity check FAILED"), ("short", "/rel/short.zip", "not the pinned file")):
            dest = os.path.join(d, name + ".zip")
            try:
                bmtools.fetch(srv.url + path, dest, sha, len(data))
                out[name] = "ok"
                assert want is None, name
                assert bmtools.sha_f(dest) == sha
            except bmtools.ToolError as e:
                out[name] = str(e)
                assert want and want in str(e), (name, e)
                assert not os.path.exists(dest) and not os.path.exists(dest + ".part"), "%s left a file" % name
        # a whole tool through acquire/install with a test pin (the test tool is a fake 'ninja' layout)
        t = {"tt": {"id": "tt", "name": "test tool", "version": "1", "check": "", "archive": "ok.zip", "url": "https://example.invalid/rel/ok.zip",
                    "sha256": sha, "size": len(data), "licence": "MIT", "licence_note": "test", "licence_url": "https://example.invalid/",
                    "install": "ninja", "target": "tt", "required": False, "needs": []}}
        old = bmtools.spec
        bmtools.spec = _spec_with(t)
        try:
            p = bmtools.plan_download("tt", d, mirror=srv.url)
            assert p["url"] == srv.url + "/rel/ok.zip" and p["mirror"] and "TEST MIRROR" in bmtools.notice_text(p)
            dest = bmtools.acquire("tt", d, mirror=srv.url, log=lambda s: None)
            assert os.path.isfile(os.path.join(dest, "ninja.exe")) and os.path.isfile(os.path.join(dest, ".bm-tool.json"))
            # not confirmed: nothing is fetched
            hits = len(srv.hits)
            r = bmbuild.download(["tt"], {"tools": tmp(), "mirror": srv.url}, out=lambda s: None, ask=lambda q: "n")
            assert not r["ok"] and r["failed"] == {"tt": "not confirmed"} and len(srv.hits) == hits, r
        finally:
            bmtools.spec = old
        return "PASS %s" % json.dumps({k: (v[:40] if v != "ok" else v) for k, v in out.items()})
    finally:
        srv.stop()


@case
def downloads_real_archive_via_mirror():
    dl = os.environ.get("BM_TEST_DL_DIR")
    if not dl or not os.path.isfile(os.path.join(dl, "ninja-win.zip")):
        return "SKIP (BM_TEST_DL_DIR with ninja-win.zip not set)"
    S = bmtools.spec()["ninja"]
    import urllib.parse
    data = open(os.path.join(dl, "ninja-win.zip"), "rb").read()
    srv = mockhttp.MockServer({urllib.parse.urlsplit(S["url"]).path: ("ok", data)})
    try:
        d = tmp("bm tools ü ")
        rc, v, out = run_cli("download", "ninja", "--yes", "--tools", d, "--mirror", srv.url)
        assert rc == 0 and v["installed"] == ["ninja"], out[-600:]
        assert "Apache-2.0" in out and S["sha256"] in out, "the licence notice / sha256 must be shown first"
        res = bmtools.check(bmtools.layout(d))
        assert res["ninja"]["ok"] and res["ninja"]["found"] == "ninja 1.13.2", res["ninja"]
        rc, v, out = run_cli("download", "ninja", "--tools", d, "--mirror", srv.url)       # already present: no second download
        assert rc == 0 and "already present" in out and srv.hits.count(urllib.parse.urlsplit(S["url"]).path) == 1
        rc, v, out = run_cli("download", "cmake", "--tools", tmp(), "--mirror", srv.url)   # no --yes and no answer: nothing happens
        assert rc == 2 and "not confirmed" in out, out[-300:]
    finally:
        srv.stop()


# ------------------------------------------------------------------------------------------------------------------ build refusals
@case
def build_refusals():
    good = XBE and os.path.dirname(XBE)
    d = tmp()
    fake = os.path.join(d, "g", "default.xbe")
    os.makedirs(os.path.dirname(fake))
    open(fake, "wb").write(fake_xbe(version=9))
    rc, v, out = run_cli("build", "--input", fake, "--build-dir", os.path.join(d, "bd"), "--tools", os.path.join(d, "tools"))
    assert rc == 2 and v["refused"] == "input" and v["recovery"], out[-400:]
    rc, v, out = run_cli("build", "--input", d, "--build-dir", os.path.join(pubfix.REPO, "work-x"))
    assert rc == 2 and v["refused"] == "folder" and "inside the source checkout" in v["reason"], out[-400:]
    assert not os.path.exists(os.path.join(pubfix.REPO, "work-x"))
    # read-only build folder: an ACL that denies this user writing (removed again below)
    ro = os.path.join(d, "read only")
    os.makedirs(ro)
    user = os.environ.get("USERNAME", "")
    subprocess.run(["icacls", ro, "/deny", "%s:(OI)(CI)(W,AD,WD)" % user], capture_output=True)
    try:
        rc, v, out = run_cli("build", "--input", fake, "--build-dir", os.path.join(ro, "bd"))
        assert rc == 2 and v["refused"] == "folder" and "not writable" in v["reason"], out[-400:]
    finally:
        subprocess.run(["icacls", ro, "/remove:d", user], capture_output=True)
    notes = ["input", "inside-checkout", "read-only"]
    if good:
        rc, v, out = run_cli("build", "--input", good, "--build-dir", os.path.join(d, "bd2"), "--tools", os.path.join(d, "tools"))
        assert rc == 2 and v["refused"] == "tools" and "llvm-mingw" in v["reason"], out[-400:]
        notes.append("missing-tools")
        if TC:
            rc, v, out = run_cli("build", "--input", good, "--build-dir", os.path.join(d, "bd3"), "--toolchain", TC, "--source", "local",
                                 "--takedawn-src", d, "--xboxrecomp-src", d, "--alias-root", tempfile.mkdtemp(prefix="bmlinks"),
                                 env={"BMBUILD_FREE_MB": "100"})
            assert rc == 2 and v["refused"] == "space" and "not enough free space" in v["reason"], out[-400:]
            assert not os.path.exists(os.path.join(d, "bd3", "s1_fetch")), "nothing may be built when the space is too small"
            bd4 = os.path.join(d, "bd4")
            os.makedirs(bd4)
            json.dump({"pid": os.getpid()}, open(os.path.join(bd4, "LOCK"), "w"))      # this (alive) process holds the folder
            rc, v, out = run_cli("build", "--input", good, "--build-dir", bd4, "--toolchain", TC)
            assert rc == 2 and v["refused"] == "lock", out[-400:]
            notes += ["low-disk", "lock"]
    return "PASS (%s)" % ", ".join(notes)


# ------------------------------------------------------------------------------------------------------------------ install / Play rule
def fake_repo():
    r = os.path.join(tmp("bm fake repo "), "repo")
    os.makedirs(os.path.join(r, "host"))
    os.makedirs(os.path.join(r, "build"))
    os.makedirs(os.path.join(r, "launcher"))
    open(os.path.join(r, "host", "PINS.json"), "w").write("{}")
    open(os.path.join(r, "build", "verify.py"), "w").write("")
    return r, os.path.join(r, "launcher")


def fake_host(folder, tag, verified=True):
    os.makedirs(os.path.join(folder, "shaders", "upscale"))
    os.makedirs(os.path.join(folder, "licenses"))
    ident = "bmp-0.1.9+%012x" % tag
    exe = b"MZ" + os.urandom(64) + ident.encode() + b"\0" * 32 + ident.encode()
    open(os.path.join(folder, bmhost.EXE), "wb").write(exe)
    open(os.path.join(folder, "SDL2.dll"), "wb").write(b"MZ sdl")
    sha = hashlib.sha256(exe).hexdigest()
    json.dump({"identity": ident, "exe_sha256": sha, "platform": "0.1.9", "services": {}, "tables": {}}, open(os.path.join(folder, "HOST_INFO.json"), "w"))
    json.dump({"sha256": sha, "verified": verified, "exe": "host-local/BurnoutMashup.exe"}, open(os.path.join(folder, "BUILD_RESULT.json"), "w"))
    return ident


@case
def install_previous_switch_and_play_rule():
    repo, L = fake_repo()
    ps = bmhost.play_state(L)
    assert not ps["host_ok"] and "no host built yet" in ps["problems"][0]
    a = os.path.join(tmp(), "a")
    ia = fake_host(a, 0xA)
    r = bmhost.install(a, L, log=lambda s: None)
    assert r["previous"] is None and bmhost.play_state(L)["host_ok"], bmhost.play_state(L)
    assert open(os.path.join(repo, "HOST_INFO.json"), "rb").read() == open(os.path.join(L, "host-local", "HOST_INFO.json"), "rb").read()
    open(os.path.join(L, "gamedata.txt"), "w").close()
    os.makedirs(os.path.join(L, "gamedata"))
    assert not bmhost.play_state(L)["play"], "Play needs the game data too"
    open(os.path.join(L, "gamedata", ".complete"), "w").write("xr-install 1\n")
    assert bmhost.play_state(L)["play"]
    b = os.path.join(tmp(), "b")
    ib = fake_host(b, 0xB)
    r = bmhost.install(b, L, log=lambda s: None)
    assert r["identity"] == ib and bmhost.folder_state(os.path.join(L, "host-local.prev"))["identity"] == ia
    # a failure at every install point leaves the build in use (b) and the previous one (a) as they were
    for fault in ("copy", "verify", "swap", "repo"):
        c = os.path.join(tmp(), "c")
        fake_host(c, 0xC)
        try:
            bmhost.install(c, L, fault=fault, log=lambda s: None)
            raise AssertionError("fault %s did not fail" % fault)
        except bmhost.InstallError:
            pass
        assert bmhost.folder_state(os.path.join(L, "host-local"))["identity"] == ib, fault
        assert bmhost.folder_state(os.path.join(L, "host-local.prev"))["identity"] == ia, fault
        assert bmhost.play_state(L)["host_ok"], (fault, bmhost.play_state(L)["problems"])
        assert not os.path.exists(os.path.join(L, "host-local.new")), fault
    # an unverified build is never installed
    u = os.path.join(tmp(), "u")
    fake_host(u, 0xD, verified=False)
    try:
        bmhost.install(u, L, log=lambda s: None)
        raise AssertionError("an unverified build was installed")
    except bmhost.InstallError as e:
        assert "not verified" in str(e)
    # switch back and forth
    bmhost.switch_back(L, log=lambda s: None)
    assert bmhost.folder_state(os.path.join(L, "host-local"))["identity"] == ia and bmhost.play_state(L)["host_ok"]
    bmhost.switch_back(L, log=lambda s: None)
    assert bmhost.folder_state(os.path.join(L, "host-local"))["identity"] == ib
    rc, v, out = run_cli("switch-back", "--launcher", L)
    assert rc == 0 and v["now"] == ia, out[-300:]
    rc, v, out = run_cli("play-state", "--launcher", L)
    assert rc == 0 and v["play"] and v["host_ok"], out
    # the Play rule refuses every inconsistency
    loc = os.path.join(L, "host-local")
    hi = os.path.join(loc, "HOST_INFO.json")
    good_hi = open(hi, "rb").read()
    checks = {}
    open(os.path.join(repo, "HOST_INFO.json"), "w").write("{}")
    checks["repo copy differs"] = bmhost.play_state(L)
    open(os.path.join(repo, "HOST_INFO.json"), "wb").write(good_hi)
    d = json.loads(good_hi)
    d["identity"] = "bmp-0.1.9+ffffffffffff"
    open(hi, "w").write(json.dumps(d))
    checks["identity"] = bmhost.play_state(L)
    open(hi, "wb").write(good_hi)
    br = os.path.join(loc, "BUILD_RESULT.json")
    good_br = open(br, "rb").read()
    os.remove(br)
    checks["no BUILD_RESULT"] = bmhost.play_state(L)
    open(br, "wb").write(good_br)
    exe = os.path.join(loc, bmhost.EXE)
    good_exe = open(exe, "rb").read()
    open(exe, "wb").write(good_exe + b"x")
    checks["exe changed"] = bmhost.play_state(L)
    open(exe, "wb").write(good_exe)
    assert bmhost.play_state(L)["play"]
    bad = {k: v["problems"] for k, v in checks.items() if v["host_ok"] or v["play"]}
    assert not bad, bad
    rc, v, out = run_cli("switch-back", "--launcher", fake_repo()[1])
    assert rc == 2 and "no previous build" in out


# ------------------------------------------------------------------------------------------------------------------ windows (headless)
class FakeStep:
    """stands in for bmops.Step: replays bmbuild --events lines"""
    def __init__(self, lines, rc):
        import queue
        self.lines = queue.Queue()
        for ln in lines:
            self.lines.put(ln)
        self.lines.put(None)
        self.rc, self.cancelled, self.args = rc, False, None

    def running(self):
        return False

    def cancel(self):
        self.cancelled = True


@case
def build_window_headless():
    import tkinter as tk
    import bmbuild_gui
    root = tk.Tk()
    root.withdraw()
    try:
        ev = lambda **k: "@@ " + json.dumps(k)  # noqa: E731
        script = [ev(ev="plan", steps=list(bmbuild.STEPS), free_mb=9000, need_mb=500)] + \
                 [ev(ev="step", name=s, status="reused", seconds=0, disk_mb=1) for s in bmbuild.STEPS[:4]] + \
                 [ev(ev="step", name="build", status="running", why="inputs changed"), "  compiling...",
                  ev(ev="step", name="build", status="done", seconds=37.5, disk_mb=101), ev(ev="step", name="verify", status="failed", message="x"),
                  ev(ev="result", rc=4, cls="verify", message="NOT identical", recovery=bmbuild.RECOVERY["verify"])]
        made = []

        def factory(name, args, root=None):
            made.append(args)
            return FakeStep(script, 4)
        asked = []
        w = bmbuild_gui.BuildWindow(root, step_factory=factory, ask=lambda *a, **k: asked.append(a) or False)
        w.withdraw()
        x = os.path.join(tmp(), "g")
        os.makedirs(x)
        open(os.path.join(x, "default.xbe"), "wb").write(fake_xbe(version=7))
        w.v_input.set(x)
        assert not w.check_input() and "REFUSED" in w.input_lbl.cget("text")
        assert w.start_build() is False and not made, "a refused input must not start a build"
        if XBE:
            w.v_input.set(os.path.dirname(XBE))
            assert w.check_input()
            w.v_bd.set(os.path.join(tmp(), "bd"))
            assert w.start_build() and made[-1][0] == "build" and "--events" in made[-1]
            for _ in range(50):
                root.update()
                if str(w.build_btn["state"]) == "normal":
                    break
                w.after(20)
            w._poll()
            root.update()
            assert w.steps_tv.item("fetch")["values"][1] == "reused (verified)" and w.steps_tv.item("build")["values"][2] == "38 s"
            assert w.steps_tv.item("verify")["values"][1] == "FAILED" and "What to do" in w.result.cget("text")
        # downloads ask per tool and start nothing when every answer is no
        w.v_tools.set(tmp())
        w.recheck_tools()
        n = len(made)
        assert w.download_selected() == [] and asked and "licence" in asked[0][1] and len(made) == n
        w.destroy()
    finally:
        root.destroy()
    return "PASS" if XBE else "PASS (build replay needs BM_TEST_XBE)"


@case
def launcher_window_play_rule():
    import tkinter as tk  # noqa: F401
    import bmgui
    repo, L = fake_repo()
    st = bmgui.bundle_state(L)
    assert st["host"] is None and "no host built yet" in st["host_problems"][0]
    a = os.path.join(tmp(), "a")
    fake_host(a, 0x1)
    bmhost.install(a, L, log=lambda s: None)
    os.makedirs(os.path.join(L, "gamedata"))
    open(os.path.join(L, "gamedata", ".complete"), "w").write("xr-install 1\n")
    st = bmgui.bundle_state(L)
    assert st["host"] == "your build (host-local)", st
    assert "bmp-0.1.9+" in bmgui.versions_line(L)
    old = bmgui.bundle_state.__defaults__
    bmgui.bundle_state.__defaults__ = (L,)
    try:
        app = bmgui.Launcher()
        app.withdraw()
        app.update()
        app.refresh()
        assert str(app.play_btn["state"]) == "normal", "a verified build + game data enables Play (never pressed here)"
        assert len(app.nb.tabs()) == 4 and hasattr(app, "open_build")
        exe = os.path.join(L, "host-local", bmhost.EXE)
        open(exe, "ab").write(b"tampered")
        app.refresh()
        assert str(app.play_btn["state"]) == "disabled" and "NOT USABLE" in app.setup_rows["host"].cget("text"), app.setup_rows["host"].cget("text")
        w = app.open_build()
        w.withdraw()
        assert w.winfo_exists() and app.open_build() is w
        w.destroy()
        app.destroy()
    finally:
        bmgui.bundle_state.__defaults__ = old


def main():
    json.dump(RES, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
    bad = {k: v for k, v in RES.items() if not str(v).startswith(("PASS", "SKIP"))}
    print(json.dumps({"cases": len(RES), "failed": bad, "skipped": [k for k, v in RES.items() if str(v).startswith("SKIP")]}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
