"""test_nobuild.py - the launcher and the Workbench BEFORE a host is built (no HOST_INFO.json anywhere), and with the generated file.

    py -3 -B tests\\test_nobuild.py OUT.json

Fix 2 of the owner brief: host-independent functions must start and work before a build, and what needs a host must say so, never crash
and never fall back to an invented host description.
  launcher (no host*\\ folder): the window starts and refreshes; the Setup row for the host says 'needs a built host ... Build Mashup first';
    Play is disabled with that explanation; the Mods tab lists a mod WITHOUT a compatibility verdict ('needs a built host', level WARN, not OK);
    import preview and import work; the versions line says 'no host built yet'; with the generated fixture (a host folder) the same mod gets a
    real verdict.
  Workbench (this repository as the kit; no HOST_INFO.json): templates list without a traceback, 'available', with the note; the catalogue
    search works; a tune-data project is created (with the note) and edited through the tuning editor; validate says VALID plus the info line
    'needs a built host'; the Test flow stops at its settings step naming 'needs a built host'; the GUI starts and shows the same.
  Workbench with the generated HOST_INFO.json in a COPY of the kit: the templates are checked against it, validate has no 'unchecked' note, a
    mod that needs a newer platform than the fixture's is BLOCKED by the same gate as the launcher's.
Exit 0 = all PASS."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (public tree: SRC = launcher/, the HOST_INFO fixture, a sandboxed %APPDATA% / %LOCALAPPDATA%)
SRC, REPO, INFO = pubfix.SRC, pubfix.REPO, pubfix.INFO
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
sys.path.insert(0, os.path.join(REPO, "workbench"))
import bmcompat  # noqa: E402
import bmmods  # noqa: E402
RES = {}
WB = os.path.join(REPO, "workbench", "wbn.py")
NEEDS = "needs a built host"


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def wb(*args, cwd=None):
    r = subprocess.run([sys.executable, "-B", WB] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd,
                       env=dict(os.environ))
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    return r.returncode, r.stdout, r.stderr


def write_mod(folder, toml):
    os.makedirs(folder)
    open(os.path.join(folder, "mod.toml"), "w", encoding="utf-8").write(toml)
    return folder


def bundle_without_host():
    root = os.path.join(tempfile.mkdtemp(prefix="bm nobuild "), "Burnout Mashup")
    os.makedirs(root)
    return root


def host_folders_absent():
    return not any(os.path.exists(os.path.join(SRC, d)) for d in ("host", "host-local"))


@case
def launcher_mods_without_host():
    root = bundle_without_host()
    b = bmmods.Bundle(root)
    assert b.host_info_path is None and b.host_info() is None
    fresh = write_mod(os.path.join(tempfile.mkdtemp(prefix="Documents "), "My Mods", "a-mod"),
                      'id = "me.a-mod"\nname = "A mod"\nversion = "1.0.0"\n[bmashup]\nplatform = ">=0.1.1"\n')
    pv = b.preview(fresh)
    assert pv["id"] == "me.a-mod" and pv["level"] == bmcompat.WARN and NEEDS in " ".join(pv["reasons"]), pv
    dest = b.import_mod(fresh)
    rows = b.mods()
    assert len(rows) == 1 and rows[0]["id"] == "me.a-mod" and rows[0]["level"] == bmcompat.WARN, rows
    assert NEEDS in " ".join(rows[0]["reasons"]) and "Build Mashup" in " ".join(rows[0]["reasons"]), rows[0]["reasons"]
    assert rows[0]["level"] != bmcompat.OK, "a verdict of OK without a host would be invented"
    b.set_enabled("me.a-mod", False)
    assert [r["enabled"] for r in b.mods()] == [False]
    assert os.path.isdir(dest)


@case
def launcher_gui_without_host():
    assert host_folders_absent(), "the repository's launcher folder must not hold a host"
    import bmgui
    app = bmgui.Launcher()
    app.withdraw()
    app.update()
    app.refresh()
    host_txt = app.setup_rows["host"].cget("text")
    assert NEEDS in host_txt and "Build Mashup" in host_txt, host_txt
    assert str(app.play_btn["state"]) == "disabled"
    assert NEEDS.split()[0] and "Build Mashup first" in app.play_hint["text"] and "Play needs a built host" in app.play_hint["text"], app.play_hint["text"]
    assert "no host built yet" in bmgui.versions_line(), bmgui.versions_line()
    assert len(app.nb.tabs()) == 4
    app.destroy()


@case
def launcher_with_generated_host_info():
    root = bundle_without_host()
    os.makedirs(os.path.join(root, "host-local"))
    open(os.path.join(root, "host-local", "burnout3_bmashup.exe"), "wb").write(b"MZ")
    shutil.copy2(INFO, os.path.join(root, "host-local", "HOST_INFO.json"))
    b = bmmods.Bundle(root)
    info = b.host_info()
    assert info["platform"] == pubfix.PLAT and info["identity"].startswith("bmp-" + pubfix.PLAT + "+")
    ok = write_mod(os.path.join(tempfile.mkdtemp(), "ok"), 'id = "me.ok"\nname = "ok"\nversion = "1"\n[bmashup]\nplatform = ">=' + pubfix.PLAT + '"\n')
    new = write_mod(os.path.join(tempfile.mkdtemp(), "new"), 'id = "me.new"\nname = "n"\nversion = "1"\n[bmashup]\nplatform = ">=' +
                    pubfix.bump(pubfix.PLAT) + '"\n')
    assert b.preview(ok)["level"] == bmcompat.OK
    pv = b.preview(new)
    assert pv["level"] == bmcompat.BLOCKED and any(pubfix.bump(pubfix.PLAT) in x for x in pv["reasons"]), pv
    assert "bmp-" in __import__("bmgui").versions_line(root) and "no host built yet" not in __import__("bmgui").versions_line(root)


@case
def bundle_sees_host_built_later():
    """phase 15 finding D5: the launcher keeps ONE Bundle from start; a host that Build Mashup installs afterwards must count at once"""
    root = bundle_without_host()
    b = bmmods.Bundle(root)
    ok = write_mod(os.path.join(tempfile.mkdtemp(), "ok"), 'id = "me.ok"\nname = "ok"\nversion = "1"\n[bmashup]\nplatform = ">=' + pubfix.PLAT + '"\n')
    before = b.preview(ok)
    assert before["level"] == bmcompat.WARN and NEEDS in " ".join(before["reasons"]), before
    os.makedirs(os.path.join(root, "host-local"))
    open(os.path.join(root, "host-local", "BurnoutMashup.exe"), "wb").write(b"MZ")
    shutil.copy2(INFO, os.path.join(root, "host-local", "HOST_INFO.json"))
    assert b.host_info() is not None and b.preview(ok)["level"] == bmcompat.OK, b.preview(ok)


@case
def workbench_templates_and_catalogue_without_host():
    rc, out, err = wb("templates")
    assert rc == 0, (rc, err[-300:])
    lst = json.loads(out)
    assert {t["id"] for t in lst} >= {"tune-data", "traffic-density", "events-observer", "events-v2"}, [t["id"] for t in lst]
    assert all(t["available"] and not t["host_checked"] and NEEDS in " ".join(t["notes"]) for t in lst), lst[0]
    rc, out, err = wb("catalogue", "search", "boost")
    assert rc == 0 and len(json.loads(out)) > 0
    import wbn_templates
    assert wbn_templates.host_info(None) is None and wbn_templates.host_info("") is None
    assert all(t["id"] for t in wbn_templates.list_templates(None))


@case
def workbench_project_tune_validate_without_host():
    d = tempfile.mkdtemp(prefix="wb nb ")
    proj = os.path.join(d, "my tuning")
    rc, out, err = wb("new", "tune-data", proj, "--id", "me.tuning", "--name", "My tuning", "--json")
    assert rc == 0, (rc, out[-400:], err[-300:])
    r = json.loads(out)
    assert r["ok"] and NEEDS in " ".join(r.get("warnings", [])), r
    rc, out, err = wb("catalogue", "search", "minimum boost")
    key = json.loads(out)[0]["key"]
    rc, out, err = wb("tune", "set", proj, key, "2", "--save", "--json")
    assert rc == 0 and json.loads(out)["saved"], (rc, out[-400:])
    rc, out, err = wb("tune", "list", proj, "--json")
    assert rc == 0 and any(x["key"] == key and x["value"] is not None for x in json.loads(out)["rows"])
    rc, out, err = wb("validate", proj)
    assert rc == 0 and out.startswith("VALID") and NEEDS in out, (rc, out[-500:])
    rc, out, err = wb("validate", proj, "--json")
    probs = json.loads(out)["problems"]
    assert any(p["code"] == "compat-unchecked" and p["sev"] == "info" for p in probs), probs
    # a plain-text mistake is still caught without any host
    t = open(os.path.join(proj, "mod.toml"), encoding="utf-8").read().replace("set = [", "sett = [")
    open(os.path.join(proj, "mod.toml"), "w", encoding="utf-8").write(t)
    rc, out, err = wb("validate", proj)
    assert rc == 1 and "NOT VALID" in out, (rc, out[-300:])


@case
def workbench_test_flow_needs_host_and_says_so():
    import wbn_flow
    d = tempfile.mkdtemp(prefix="wb nbflow ")
    proj = os.path.join(d, "p")
    rc, out, err = wb("new", "tune-data", proj, "--id", "me.flow", "--name", "Flow", "--json")
    assert rc == 0, out[-300:]
    s, bad = wbn_flow.load_settings(None, kit=REPO, state=os.path.join(d, "state"))
    probs = wbn_flow.settings_problems(s, False)
    assert any(NEEDS in p and "HOST_INFO.json" in p for p in probs), probs
    r = wbn_flow.run_sync(proj, s)
    assert not r["ok"] and r["verdict"] == "SETTINGS INCOMPLETE" and any(NEEDS in p["msg"] for p in r["problems"]), r["verdict"]
    assert not r["launched"]


@case
def workbench_gui_without_host():
    import tkinter as tk
    import wbn_gui
    root = tk.Tk()
    root.withdraw()
    try:
        app = wbn_gui.App(root)
        root.update()
        assert app.kit.get() == REPO or os.path.normcase(app.kit.get()) == os.path.normcase(REPO), app.kit.get()
        t = app.show_template()
        assert t and t["available"] and NEEDS in " ".join(t["notes"]), t
        d = tempfile.mkdtemp(prefix="wb nbgui ")
        r = app.create_project(folder=os.path.join(d, "g"), mod_id="me.gui", name="Gui", template="tune-data")
        assert r["ok"] and NEEDS in "".join(app.new_out.get("1.0", "end")), r
        v = app.validate_project()
        assert v and v["ok"] and any(p["code"] == "compat-unchecked" for p in v["problems"]), v
    finally:
        root.destroy()


@case
def workbench_with_generated_host_info():
    kit = os.path.join(tempfile.mkdtemp(prefix="wb kit "), "kit copy")
    shutil.copytree(REPO, kit, ignore=shutil.ignore_patterns("__pycache__", ".git", "build", "out", "work"))
    shutil.copy2(INFO, os.path.join(kit, "HOST_INFO.json"))
    wbk = os.path.join(kit, "workbench", "wbn.py")

    def run(*args):
        r = subprocess.run([sys.executable, "-B", wbk] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ))
        assert "Traceback" not in r.stderr, r.stderr[-800:]
        return r.returncode, r.stdout, r.stderr
    rc, out, err = run("templates")
    lst = json.loads(out)
    assert rc == 0 and all(t["host_checked"] and not t["notes"] for t in lst), lst[0]
    assert {x["id"]: x["available"] for x in lst}["tune-data"], lst   # checked against the generated file's tables
    d = tempfile.mkdtemp(prefix="wb gen ")
    proj = os.path.join(d, "p")
    rc, out, err = run("new", "tune-data", proj, "--id", "me.gen", "--name", "Gen", "--json")
    r = json.loads(out)
    assert rc == 0 and r["ok"] and "warnings" not in r, r
    rc, out, err = run("validate", proj, "--json")
    probs = json.loads(out)["problems"]
    assert rc == 0 and not any(p["code"] == "compat-unchecked" for p in probs), probs
    t = open(os.path.join(proj, "mod.toml"), encoding="utf-8").read()
    t = re.sub(r'platform = ">=[0-9.]+"', 'platform = ">=' + pubfix.bump(pubfix.PLAT) + '"', t)
    assert pubfix.bump(pubfix.PLAT) in t
    open(os.path.join(proj, "mod.toml"), "w", encoding="utf-8").write(t)
    rc, out, err = run("validate", proj, "--json")
    probs = json.loads(out)["problems"]
    assert rc == 1 and any(p["code"] == "compat" and p["sev"] == "error" and pubfix.bump(pubfix.PLAT) in p["msg"] for p in probs), probs


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
