"""test_mod_clash.py - the launcher warns before a game about mods that clash (bmcompat.find_clashes, bmmods.Bundle.mods), naming the one the host would refuse. Made mods in a
made folder; no host, no game. BMCLASH_DIR: a folder searched first (mutated copies)."""
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "launcher"))
import bmcompat  # noqa: E402
import bmmods  # noqa: E402
if os.environ.get("BMCLASH_DIR"):
    sys.path.insert(0, os.environ["BMCLASH_DIR"])
    import importlib.util as u
    sp = u.spec_from_file_location("bmcompat", os.path.join(os.environ["BMCLASH_DIR"], "bmcompat.py"))
    bmcompat = u.module_from_spec(sp)
    sp.loader.exec_module(bmcompat)
    bmmods.bmcompat = bmcompat

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def toml(mid, tracks=(), region=None, name=None, platform=None):
    t = 'id = "%s"\nname = "%s"\nversion = "1.0.0"\n' % (mid, name or mid)
    t += "[bmashup]\n" + ('platform = ">=%s"\n' % platform if platform else "")
    if region:
        t += '[bmashup.regions]\nversion = 1\nadd = ["%s"]\ndj = ["B = DJEU"]\n' % region
    if tracks:
        t += "[bmashup.tracks]\nversion = 1\nadd = [%s]\n" % ", ".join('"%s"' % x for x in tracks)
    return t


def bundle(t, mods):
    b = bmmods.Bundle(t)
    base = bmmods.bmpaths.mods_dir(t, "user")
    for folder, text in mods.items():
        os.makedirs(os.path.join(base, folder))
        open(os.path.join(base, folder, "mod.toml"), "w", encoding="utf-8").write(text)
    return b


def by_id(b):
    return {r["id"]: r for r in b.mods()}


@case
def same_track_later_one_refused(t):
    b = bundle(t, {"a": toml("x.white-mountain", ["BR_W1_V1"], name="WM"), "b": toml("x.white-mountain-b3eu", ["BR_W1_V1"], name="WM B3")})
    r = by_id(b)
    lost, kept = r["x.white-mountain-b3eu"], r["x.white-mountain"]
    assert lost["level"] == bmcompat.BLOCKED and any("clashes with WM" in x and "BR_W1_V1" in x and "starts without" in x for x in lost["reasons"]), lost
    assert kept["level"] != bmcompat.BLOCKED and any("clashes with WM B3" in x and "refuses the other" in x for x in kept["reasons"]), kept


@case
def host_order_is_by_id_not_folder(t):
    b = bundle(t, {"z-first-folder": toml("a.mod", ["T1"]), "a-first-folder": toml("b.mod", ["T1"])})
    r = by_id(b)
    assert r["b.mod"]["level"] == bmcompat.BLOCKED and r["a.mod"]["level"] != bmcompat.BLOCKED, r


@case
def turning_one_off_clears_it(t):
    b = bundle(t, {"a": toml("x.a", ["T1"]), "b": toml("x.b", ["T1"])})
    b.set_enabled("x.a", False)
    r = by_id(b)
    assert not any("clashes" in x for m in r.values() for x in m["reasons"]), r
    assert r["x.b"]["level"] != bmcompat.BLOCKED


@case
def different_tracks_are_fine(t):
    b = bundle(t, {"a": toml("x.a", ["T1"], "B = BREVENGE"), "b": toml("x.b", ["T2"], "B = BREVENGE"), "c": toml("x.c", ["T3"])})
    assert not any("clashes" in x for m in by_id(b).values() for x in m["reasons"])


@case
def a_region_said_differently(t):
    b = bundle(t, {"a": toml("x.a", ["T1"], "B = BREVENGE"), "b": toml("x.b", ["T2"], "B = OTHER")})
    r = by_id(b)
    assert r["x.b"]["level"] == bmcompat.BLOCKED and any("region B" in x for x in r["x.b"]["reasons"]), r
    assert r["x.a"]["level"] != bmcompat.BLOCKED


@case
def a_refused_mod_claims_nothing(t):
    rows = [dict(id="a", enabled=True, level="OK", manifest={"bmashup": {"tracks": {"add": ["T1"]}}}),
            dict(id="b", enabled=True, level="OK", manifest={"bmashup": {"tracks": {"add": ["T1", "T2"]}}}),
            dict(id="c", enabled=True, level="OK", manifest={"bmashup": {"tracks": {"add": ["T2"]}}})]
    n = bmcompat.find_clashes(rows)
    assert [x[0] for x in n[1]] == [True] and 2 not in n, n
    rows[0]["level"] = "BLOCKED"
    rows[1]["level"] = "BLOCKED"
    assert not bmcompat.find_clashes([rows[1], rows[2]]), "a mod already blocked keeps nothing"


@case
def three_of_a_track(t):
    b = bundle(t, {"a": toml("x.a", ["T1"]), "b": toml("x.b", ["T1"]), "c": toml("x.c", ["T1"])})
    r = by_id(b)
    assert r["x.b"]["level"] == r["x.c"]["level"] == bmcompat.BLOCKED and r["x.a"]["level"] != bmcompat.BLOCKED, r


@case
def odd_manifests_do_not_break_it(t):
    assert bmcompat.find_clashes([dict(id="a", enabled=True, level="OK", manifest={"bmashup": {"tracks": "no"}}), dict(id="b", enabled=True, level="OK", manifest=None), dict(id="c", enabled=True, level="OK", manifest={"bmashup": 3})]) == {}


def main():
    bad = 0
    for fn in CASES:
        t = tempfile.mkdtemp(prefix="clash")
        try:
            fn(t)
            print("PASS", fn.__name__)
        except Exception:  # noqa: BLE001
            bad += 1
            print("FAIL", fn.__name__, traceback.format_exc().strip().splitlines()[-1][:220])
        finally:
            shutil.rmtree(t, ignore_errors=True)
    print("%d cases, %d failed" % (len(CASES), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
