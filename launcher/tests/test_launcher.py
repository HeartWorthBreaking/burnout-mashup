"""test_launcher.py - release readiness R1: the launcher's compatibility gate, mod manager, step runner and window.

    py -3 -B tests\\test_launcher.py OUT.json [--gui]

Every case builds its own temporary bundle (path with spaces AND non-ASCII characters) from the candidate's tools; nothing in
the candidate or the workspace is written. HOST_INFO comes from tests\\fixtures\\HOST_INFO_fixture.json (a real host build's own
platform table). --gui also opens the window (withdrawn), refreshes, resizes to the minimum, checks keyboard bindings, closes.
Exit 0 = all cases passed; OUT.json = {case: "PASS" | "FAIL: why"}."""
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (public tree: SRC = launcher/, the HOST_INFO fixture, a sandboxed %APPDATA% / %LOCALAPPDATA%)
CAND = SRC = pubfix.SRC
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmcompat  # noqa: E402
import bmmods  # noqa: E402
import bmops  # noqa: E402

INFO = pubfix.INFO
RES = {}


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def make_bundle(tag):
    base = tempfile.mkdtemp(prefix="bm r1 ")
    root = os.path.join(base, "Bündel mit Leerzeichen %s" % tag)
    os.makedirs(os.path.join(root, "mods", "demo"))
    os.makedirs(os.path.join(root, "mods", "user"))
    os.makedirs(os.path.join(root, "host"))
    open(os.path.join(root, "host", "burnout3_bmashup.exe"), "wb").write(b"MZ stand-in")
    shutil.copy2(INFO, os.path.join(root, "host", "HOST_INFO.json"))
    shutil.copytree(os.path.join(SRC, "tools"), os.path.join(root, "tools"))
    return root


def write_mod(folder, toml, files=None):
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "mod.toml"), "w", encoding="utf-8").write(toml)
    for n, data in (files or {}).items():
        open(os.path.join(folder, n), "wb").write(data)
    return folder


def T(mid, extra="", ver="1.0.0"):
    return 'id = "%s"\nname = "%s"\nversion = "%s"\n%s' % (mid, mid, ver, extra)


def lvl(info, folder, installed=None):
    return bmcompat.check_mod(info, folder, installed)


# ---------------- compatibility gate ----------------
@case
def compat_rules():
    info = bmcompat.load_host_info(INFO)
    # phase 9: every version below is read from the host description (the generated fixture), none is typed: a requirement AT the host's
    # version is met, one above it is refused
    rules, tune = info["services"]["bmashup.rules"], info["tables"]["tune"]["version"]
    t = tempfile.mkdtemp()
    ok = write_mod(os.path.join(t, "ok"), T("a.ok", '[bmashup]\nplatform = ">=' + pubfix.PLAT + '"\nrequires = ["bmashup.rules>=%d", '
                                                    '"bmashup.textures>=1"]\n[bmashup.tune]\nversion = %d\nset = []\n' % (rules, tune)))
    assert lvl(info, ok)["level"] == "OK", lvl(info, ok)
    cases = {
        "platform": '[bmashup]\nplatform = ">=0.2.0"\n',
        "svc_new": '[bmashup]\nrequires = ["bmashup.rules>=%d"]\n' % (rules + 1),
        "svc_none": '[bmashup]\nrequires = ["bmashup.nothing"]\n',
        "svc_dotted": '[bmashup]\nrequires = ["bmashup.rules>=%d.1"]\n' % rules,
        "svc_zero": '[bmashup]\nrequires = ["bmashup.rules>=0"]\n',
        "table_new": '[bmashup.tune]\nversion = %d\nset = []\n' % (tune + 1),
        "table_unknown": '[bmashup.weather]\nversion = 1\n',
        "table_typo": '[bmashup.tune]\nversion = %d\nsett = []\n' % tune,
        "own_key": '[bmashup]\nplatfrom = ">=' + pubfix.PLAT + '"\n',
        "plugin_api": '[plugin]\napi = 2\nwindows = "x.asi"\n',
        "plugin_missing": '[plugin]\napi = 1\nwindows = "x.asi"\n',
        "bad_toml": 'this is = not [ toml\n',
    }
    for k, extra in cases.items():
        r = lvl(info, write_mod(os.path.join(t, k), T("a." + k.replace("_", "-"), extra)))
        assert r["level"] == "BLOCKED" and r["reasons"], (k, r)
    nat = write_mod(os.path.join(t, "nat"), T("a.nat", '[plugin]\napi = 1\nwindows = "x.asi"\n'), {"x.asi": b"MZ"})
    r = lvl(info, nat)
    assert r["level"] == "WARN" and r["native_code"] and "never approves" in r["reasons"][0], r
    dep = write_mod(os.path.join(t, "dep"), T("a.dep", '[bmashup]\nrequires_mods = ["a.base >= 1.2"]\n'))
    assert lvl(info, dep, {})["level"] == "BLOCKED"
    assert lvl(info, dep, {"a.base": "1.1.9"})["level"] == "BLOCKED"
    assert lvl(info, dep, {"a.base": "1.2.0-rc1"})["level"] == "BLOCKED"       # prerelease ranks below 1.2.0
    assert lvl(info, dep, {"a.base": "1.2"})["level"] == "OK"
    assert bmcompat.meets("0.1.10", "0.1.9") and not bmcompat.meets("0.1.9", "0.1.10")


@case
def compat_real_mods():
    info = bmcompat.load_host_info(INFO)
    demo = pubfix.DEMO
    for d in os.listdir(demo):
        r = lvl(info, os.path.join(demo, d))
        assert r["level"] == "OK", (d, r)


# ---------------- mod list ----------------
@case
def mod_list_atomic():
    b = bmmods.Bundle(make_bundle("list"))
    write_mod(os.path.join(b.root, "mods", "user", "m1"), T("a.one"))
    assert b.disabled() == []
    b.set_enabled("a.one", False)
    assert b.disabled() == ["a.one"] and not os.path.exists(b.mod_list + ".bak")
    b.set_enabled("a.two", False)
    assert b.disabled() == ["a.one", "a.two"] and os.path.exists(b.mod_list + ".bak")
    b.set_enabled("a.one", True)
    assert b.disabled() == ["a.two"]
    assert [r for r in b.mods() if r["id"] == "a.one"][0]["enabled"]
    leftovers = [f for f in os.listdir(b.settings_dir) if f.startswith(".tmp-")]
    assert not leftovers, leftovers
    try:
        b.set_enabled('x"; evil = 1 #', False)
        raise AssertionError("bad id accepted")
    except bmmods.ModError:
        pass


@case
def mod_list_readonly_keeps_old():
    b = bmmods.Bundle(make_bundle("ro"))
    b.set_enabled("a.one", False)
    before = open(b.mod_list, encoding="utf-8").read()
    os.chmod(b.mod_list, stat.S_IREAD)
    try:
        try:
            b.set_enabled("a.two", False)
            raised = False
        except OSError:
            raised = True
        assert raised, "write over a read-only mod list did not fail"
        assert open(b.mod_list, encoding="utf-8").read() == before
        assert not [f for f in os.listdir(b.settings_dir) if f.startswith(".tmp-")]
    finally:
        os.chmod(b.mod_list, stat.S_IREAD | stat.S_IWRITE)


# ---------------- import ----------------
@case
def import_folder_zip_replace():
    b = bmmods.Bundle(make_bundle("imp"))
    src = write_mod(os.path.join(tempfile.mkdtemp(), "My Mod ä"), T("a.imp", ver="1.0.0"), {"readme.txt": b"hi"})
    pv = b.preview(src)
    assert pv["id"] == "a.imp" and pv["files"] == 2 and not pv["native_code"], pv
    dest = b.import_mod(src)
    assert os.path.isfile(os.path.join(dest, "mod.toml"))
    try:
        b.import_mod(src)
        raise AssertionError("duplicate import accepted")
    except bmmods.ModError as e:
        assert "Replace" in str(e)
    z = os.path.join(tempfile.mkdtemp(), "mod.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a-imp/mod.toml", T("a.imp", ver="2.0.0"))
        zf.writestr("a-imp/run_me.cmd", "echo should never run")
    pv = b.preview(z)
    assert pv["version"] == "2.0.0" and pv["executable_files"] == ["run_me.cmd"], pv
    b.import_mod(z, replace=True)
    assert "2.0.0" in open(os.path.join(dest, "mod.toml"), encoding="utf-8").read()
    bk = os.path.join(b.root, "mods", ".backup")
    assert os.listdir(bk) and "1.0.0" in open(os.path.join(bk, os.listdir(bk)[0], "mod.toml"), encoding="utf-8").read()
    assert not os.path.exists(os.path.join(b.root, "should_never_run.txt"))


@case
def import_refusals():
    b = bmmods.Bundle(make_bundle("ref"))
    t = tempfile.mkdtemp()
    for name, entries in {"slip": {"../evil/mod.toml": T("a.e")}, "abs": {"/abs/mod.toml": T("a.e")},
                          "drive": {"C:/x/mod.toml": T("a.e")}, "none": {"x/readme.txt": "no mod"},
                          "two": {"a/mod.toml": T("a.a"), "b/mod.toml": T("a.b")}, "badid": {"m/mod.toml": T("Bad ID")}}.items():
        z = os.path.join(t, name + ".zip")
        with zipfile.ZipFile(z, "w") as zf:
            for n, d in entries.items():
                zf.writestr(n, d)
        try:
            b.import_mod(z)
            raise AssertionError("%s accepted" % name)
        except bmmods.ModError:
            pass
    assert not os.listdir(os.path.join(b.root, "mods", "user"))
    assert not os.path.exists(os.path.join(os.path.dirname(b.root), "evil"))
    shipped = write_mod(os.path.join(b.root, "mods", "demo", "s"), T("a.ship"))
    try:
        b.import_mod(write_mod(os.path.join(t, "s2"), T("a.ship")), replace=True)
        raise AssertionError("a shipped mod was replaced")
    except bmmods.ModError:
        pass
    assert os.path.isdir(shipped)


@case
def import_readonly_target():
    b = bmmods.Bundle(make_bundle("rot"))
    user = os.path.join(b.root, "mods", "user")
    src = write_mod(os.path.join(tempfile.mkdtemp(), "m"), T("a.ro"))
    os.chmod(user, stat.S_IREAD | stat.S_IEXEC)
    try:
        try:
            b.import_mod(src)
            ok = os.path.isdir(os.path.join(user, "a.ro"))   # Windows ignores the folder read-only bit: then it must be whole
        except OSError:
            ok = not os.path.exists(os.path.join(user, "a.ro"))
        assert ok
        assert not os.path.exists(os.path.join(user, "a.ro.importing"))
    finally:
        os.chmod(user, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)


# ---------------- stale profile + results ----------------
@case
def stale_and_results():
    b = bmmods.Bundle(make_bundle("st"))
    write_mod(os.path.join(b.root, "mods", "user", "p"), T("a.plug", '[plugin]\napi = 1\nwindows = "p.asi"\n'), {"p.asi": b"MZ v2"})
    os.makedirs(os.path.join(b.settings_dir, "logs"))
    open(b.approvals, "w").write('approved = ["a.plug sha256:%s", "a.gone sha256:%s"]\n' % ("0" * 64, "1" * 64))
    open(b.plugin_settings, "w").write('values = [\n "a.gone/x = on",\n "bmashup.host/debug_menu = off",\n]\n')
    st = b.stale()
    whys = sorted((x["file"], x["id"]) for x in st)
    assert whys == [("plugin-approvals.toml", "a.gone"), ("plugin-approvals.toml", "a.plug"), ("plugin-settings.toml", "a.gone")], st
    open(b.log, "w", encoding="utf-8").write(
        "[ADMIT] mod a.bad 1.0 (x) refused, the game starts without it: needs bmashup.rules >= 9\n"
        "[ADMIT] 3 mods' [bmashup.*] declarations checked together before any is used (platform 0.1.9): 2 admitted, 1 refused\n"
        "[MOD] mod a.one 1.0: X\n[MOD] mod a.two 1.0: Y\n[PLUGIN] a.plug: running (plugin API 1)\n"
        "[PLUGIN] a.other: not run: not approved. It is native code\n")
    r = b.results()
    assert r["admitted"] == 2 and len(r["refused"]) == 1 and r["plugins_running"] == ["a.plug"] and len(r["plugins_not_run"]) == 1
    assert r["mods_loaded"] == 2 and not r["fatal"], r


@case
def launcher_never_approves():
    """No code path of the launcher writes plugin-approvals.toml (text check over the launcher sources)."""
    for f in os.listdir(os.path.join(SRC, "tools", "launcher")):
        if f.endswith((".py", ".pyw")):
            txt = open(os.path.join(SRC, "tools", "launcher", f), encoding="utf-8").read()
            for bad in ("approvals, \"w\"", "atomic_write(self.approvals", "open(self.approvals, \"w\"", "approved = ["):
                assert bad not in txt, (f, bad)


# ---------------- steps: cancel, explain ----------------
@case
def step_cancel_and_explain():
    root = make_bundle("ops")
    open(os.path.join(root, "tools", "sleeper.py"), "w").write("import time\nprint('start', flush=True)\ntime.sleep(60)\n")
    bmops.STEPS["sleeper"] = ("sleeper.py", [])
    s = bmops.Step("sleeper", root=root)
    assert s.lines.get(timeout=20) == "start"
    t0 = time.time()
    s.cancel()
    while s.running() and time.time() - t0 < 15:
        time.sleep(0.1)
    assert not s.running() and s.cancelled
    assert "Cancelled" in bmops.explain("sleeper", s.rc, True, [])
    assert "Python 3.11" in bmops.explain("x", 9, False, [])
    assert "refused: no data" in bmops.explain("x", 3, False, ["refused: no data"])


@case
def every_step_command_line_parses():
    """every launcher step reaches its tool's own logic: never an argparse usage error (owner run 2026-10-31: data_auto called
    prepare.py without its 'auto' command -> 'invalid choice')"""
    root = make_bundle("argv")
    missing = os.path.join(root, "no such folder")
    takes_path = {"data_copy", "data_install", "data_auto", "diag", "backup", "upgrade", "repair"}
    bad = []
    for name in sorted(bmops.STEPS):
        if name in ("sleeper",):
            continue
        s = bmops.Step(name, [missing] if name in takes_path else [], root=root)
        out = []
        while True:
            ln = s.lines.get(timeout=180)
            if ln is None:
                break
            out.append(ln)
        if s.rc == 2 or any(ln.startswith("usage:") or "error: argument" in ln or "invalid choice" in ln for ln in out):
            bad.append("%s rc %s: %s" % (name, s.rc, " | ".join(out[-3:])))
    assert not bad, bad


@case
def preflight_without_host_is_actionable():
    root = make_bundle("pf")
    os.remove(os.path.join(root, "host", "burnout3_bmashup.exe"))
    s = bmops.Step("preflight", root=root)
    out = []
    while True:
        ln = s.lines.get(timeout=120)
        if ln is None:
            break
        out.append(ln)
    assert s.rc != 0 and any(ln.startswith("FAIL") for ln in out) and out[-1].startswith("RESULT FAIL"), out[-5:]


@case
def theme_shared_and_readable():
    """the launcher and the Workbench ship one theme (byte-identical copies); text colours keep WCAG AA contrast"""
    import bmtheme
    wb = os.path.join(pubfix.REPO, "workbench", "wb_theme.py")
    assert open(bmtheme.__file__, "rb").read() == open(wb, "rb").read(), "wb_theme.py differs from bmtheme.py"

    def lum(c):
        ch = [int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]

    def ratio(a, b):
        la, lb = sorted((lum(a), lum(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)
    t = bmtheme
    pairs = [(t.TEXT, s, 7.0) for s in (t.BG, t.PAGE, t.CARD, t.RAISED, t.ACCENT_LO)]
    pairs += [(c, s, 4.5) for c in (t.MUTED, t.OK, t.WARN, t.BAD, t.ACCENT_HI) for s in (t.BG, t.PAGE, t.CARD)]
    pairs += [(t.ON_ACCENT, t.ACCENT, 4.5), (t.ON_ACCENT, t.ACCENT_HOVER, 3.0)]
    low = ["%s on %s = %.2f" % (a, b, ratio(a, b)) for a, b, need in pairs if ratio(a, b) < need]
    assert not low, low


@case
def compat_newer_platform_refused():
    """negative compatibility, derived from the fixture (no typed version): a mod that needs exactly the host's platform is OK, one patch
    level above it is BLOCKED naming the platform; a service one version above the host's is BLOCKED"""
    info = bmcompat.load_host_info(INFO)
    t = tempfile.mkdtemp()
    ok = write_mod(os.path.join(t, "eq"), T("a.eq", '[bmashup]\nplatform = ">=' + pubfix.PLAT + '"\n'))
    assert lvl(info, ok)["level"] == "OK", lvl(info, ok)
    nxt = write_mod(os.path.join(t, "next"), T("a.next", '[bmashup]\nplatform = ">=' + pubfix.bump(pubfix.PLAT) + '"\n'))
    r = lvl(info, nxt)
    assert r["level"] == "BLOCKED" and any(pubfix.bump(pubfix.PLAT) in x for x in r["reasons"]), r
    svc, ver = sorted(json.load(open(INFO, encoding="utf-8"))["services"].items())[0]
    hi = write_mod(os.path.join(t, "svc"), T("a.svc", '[bmashup]\nrequires = ["%s>=%d"]\n' % (svc, ver + 1)))
    r = lvl(info, hi)
    assert r["level"] == "BLOCKED" and any(svc in x for x in r["reasons"]), r


def gui_smoke():
    import bmgui
    app = bmgui.Launcher()
    app.withdraw()
    app.update()
    app.refresh()
    for key in ("<Control-Key-1>", "<Control-Key-4>", "<F5>", "<Escape>", "<Alt-p>", "<Alt-c>", "<Alt-i>", "<Alt-z>", "<Alt-t>", "<Alt-r>", "<Alt-l>"):
        assert app.bind(key), key
    app.geometry("720x480")
    app.update()
    assert app.nb.winfo_width() > 0 and len(app.nb.tabs()) == 4
    app.destroy()


def main():
    out = sys.argv[1]
    if "--gui" in sys.argv:
        case(gui_smoke)
    json.dump(RES, open(out, "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
