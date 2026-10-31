"""test_onboarding.py - release readiness R1 stage 5: the player quickstart and the first-mod tutorial do what they say.

    py -3 -B tests\\test_onboarding.py OUT.json

- tutorial: its mod.toml (taken from the document itself) in a FRESH folder outside any bundle -> the launcher's verdict is
  BLOCKED naming 'sett' (the deliberate error); with the documented fix -> OK; import into a fresh temporary bundle -> listed,
  on; the key is in TUNING_CATALOGUE.md and in the host's catalogue; 2500 is inside the limit (16 x 1000)
- docs vs window: every button / tab named in QUICKSTART.md and the tutorial exists in bmgui.py with that text
- docs links: every docs\\*.md the window opens exists in the candidate
Exit 0 = all PASS."""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (public tree: SRC = launcher/, the HOST_INFO fixture, a sandboxed %APPDATA% / %LOCALAPPDATA%)
CAND = SRC = pubfix.SRC
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmcompat  # noqa: E402
import bmmods  # noqa: E402

INFO = pubfix.INFO
TREE = pubfix.TREE
DOC_T = open(os.path.join(SRC, "docs", "FIRST_MOD_TUTORIAL.md"), encoding="utf-8").read()
DOC_Q = open(os.path.join(SRC, "docs", "QUICKSTART.md"), encoding="utf-8").read()
GUI = open(os.path.join(SRC, "tools", "launcher", "bmgui.py"), encoding="utf-8").read()
RES = {}


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


@case
def tutorial_error_fix_import():
    toml = re.search(r"```toml\n(.*?)```", DOC_T, re.S).group(1)
    assert "sett = [" in toml
    info = bmcompat.load_host_info(INFO)
    fresh = os.path.join(tempfile.mkdtemp(prefix="Documents "), "My Mods", "bigger-takedowns")
    os.makedirs(fresh)
    open(os.path.join(fresh, "mod.toml"), "w", encoding="utf-8").write(toml)
    r = bmcompat.check_mod(info, fresh)
    assert r["level"] == "BLOCKED" and any("sett" in x and "typo" in x for x in r["reasons"]), r
    shown = re.search(r"> - (\[bmashup\.tune\][^\n]*)", DOC_T).group(1)
    assert shown in r["reasons"], (shown, r["reasons"])                # the document quotes the real message
    open(os.path.join(fresh, "mod.toml"), "w", encoding="utf-8").write(toml.replace("sett = [", "set = ["))
    r = bmcompat.check_mod(info, fresh)
    assert r["level"] == "OK", r
    root = os.path.join(tempfile.mkdtemp(prefix="bm tut "), "Burnout Mashup")
    os.makedirs(os.path.join(root, "host"))
    open(os.path.join(root, "host", "burnout3_bmashup.exe"), "wb").write(b"MZ")
    shutil.copy2(INFO, os.path.join(root, "host", "HOST_INFO.json"))
    b = bmmods.Bundle(root)
    dest = b.import_mod(fresh)
    assert dest.endswith(os.path.join("mods", "user", "me.bigger-takedowns")), dest
    row = [x for x in b.mods() if x["id"] == "me.bigger-takedowns"][0]
    assert row["enabled"] and row["level"] == "OK"
    try:
        b.import_mod(fresh)
        raise AssertionError("re-import without replace accepted")
    except bmmods.ModError as e:
        assert "replace" in str(e).lower()


@case
def tutorial_key_and_limit():
    m = re.search(r'sett? = \["([^"]+) = ([0-9]+)"\]', DOC_T)
    key, val = m.group(1), int(m.group(2))
    cat = open(os.path.join(SRC, "docs", "TUNING_CATALOGUE.md"), encoding="utf-8").read()
    row = re.search(r"\| `%s` \| whole number \| ([0-9]+) \|" % re.escape(key.replace("|", "\\|")), cat)
    assert row, key
    game = int(row.group(1))
    assert game == 1000 and 0 <= val <= 16 * max(game, 1)
    host = open(os.path.join(TREE, "src", "game", "bm_tune_catalog.h"), encoding="utf-8").read()
    assert '{"%s",' % key in host


@case
def docs_name_real_buttons():
    named = set(re.findall(r"(?<!\*)\*([A-Z][^*\n]{2,60}?)\*(?!\*)", DOC_Q + DOC_T))   # *italic* = a window text
    ignore = {"Save as type: All files", "View > File name extensions", "Approve and turn on"}   # Windows / in-game texts
    missing = []
    for n in sorted(named - ignore):
        if n.rstrip(".") not in GUI:
            missing.append(n)
    assert not missing, missing
    for tab in ("Setup", "Mods", "Play", "Help"):
        assert 'text="%s"' % tab in GUI, tab                     # the tab names the docs use (plain since the polish)


@case
def help_links_exist():
    for rel in re.findall(r'"(docs\\\\[A-Z_]+\.md)"', GUI):
        p = os.path.join(SRC, rel.replace("\\\\", os.sep))
        assert os.path.isfile(p), rel


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
