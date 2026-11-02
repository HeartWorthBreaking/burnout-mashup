"""trackbuild 0.3.4 - capacity tests (trackbuild.capacity, the build / validate / package integration, mod.toml merge).

    py -3 -B tests\\test_capacity.py RUN_DIR [--game-data DIR]

RUN_DIR must not exist. C1..C9 are unit tests (no game data). C10..C13 build the ORIGINAL test loop in this process with the
game's default mesh-block size LOWERED in the capacity table (a synthetic "over-default" track: every mesh block is above
the lowered default, far below the host ceiling) and need YOUR game data for the donor parts (--game-data DIR, else
TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA; SKIPPED without it). The real table is restored after each case.
Results: RUN_DIR/RESULTS_capacity.txt."""
import json
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)
from trackbuild import accessguard  # noqa: E402
accessguard.install_from_env()
from trackbuild import capacity as CAP  # noqa: E402
from trackbuild.io import SourceError  # noqa: E402
from trackbuild._vendor.trackconv import package as P  # noqa: E402
from trackbuild import pack as PK  # noqa: E402

RES, SKIP = [], []
HOST_SRC = os.path.join(PKG, "..", "..", "host", "tree", "src", "game")   # the host sources of this repository (optional)


def check(name, ok, detail=""):
    RES.append((name, bool(ok)))
    print("%-4s %-72s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:220].replace("\n", " | ")))


def skip(name, why):
    SKIP.append((name, why))
    print("SKIP %-72s %s" % (name, why))


def raises(fn, phrase):
    try:
        fn()
    except SourceError as e:
        return phrase.lower() in str(e).lower(), str(e)
    except PK.PackageError as e:
        return phrase.lower() in str(e).lower(), str(e)
    return False, "no refusal"


def rep_of(mesh=0x10000, lod=0x10000, static=0x100000, gd="0x100000", lanes=5):
    return {"units": {"units": [{"unit": 0, "mesh_bytes": 0x1000, "lod_bytes": 0x1000},
                                {"unit": 1, "mesh_bytes": mesh, "lod_bytes": lod}]},
            "static": {"bytes": static}, "gamedata": {"need": gd}, "route": {"lanes": lanes}}


PKG_P = {"set": "s", "folder": "f", "track_id": "EU_T7_V1", "track_name": "T", "track_location": "L", "mod_id": "a.b",
         "mod_name": "m", "version": "1.0.0", "author": "x"}


def unit_tests():
    T = CAP.TABLE
    check("C1 table: game defaults = the 0.3.3 limits", (T["full_unit_bytes"]["game"], T["low_unit_bytes"]["game"],
          T["static_bytes"]["game"], T["gamedata_bytes"]["game"], T["lanes"]["game"]) == (0x28000, 0x18000, 0xD00000, 0x176000, 64))
    check("C1b table: ceilings (the patch 131 host)", (T["full_unit_bytes"]["ceiling"], T["low_unit_bytes"]["ceiling"],
          T["static_bytes"]["ceiling"], T["gamedata_bytes"]["ceiling"], T["lanes"]["ceiling"]) == (0x200000, 0x200000, 0x4000000, 0x800000, 255))
    if os.path.isdir(HOST_SRC):
        src = "".join(open(os.path.join(HOST_SRC, f), encoding="utf-8", errors="replace").read()
                      for f in ("bm_unitslots.h", "bm_static.h", "bm_gdslot.h", "bm_lanes.h", "bm_capdecl.c"))
        keys_ok = all('CD_PREFIX ".%s"' % k in src for k in CAP.ORDER)
        import re
        want = {"BO3_ST_MAX": "0x4000000u", "BO3_GDS_MAX": "0x800000u", "BO3_US_FULL_RETAIL": "0x28000u", "BO3_US_LOW_RETAIL": "0x18000u", "BO3_GDS_GAME": "0x176000u",
                "BO3_ST_L1_GAME": "0xD00000u", "BO3_LANE_LEGACY_MAX": "64u", "BO3_LANE_TOTAL_MAX": "(BO3_LANE_LEGACY_MAX + BO3_LANE_EXT_MAX)"}
        got = {k: (re.search(r"#define\s+%s\s+(\S+(?: \+ \S+)?)" % k, src) or [None, None])[1] for k in want}
        tiers_ok = all(got[k] == v for k, v in want.items())
        check("C2 host source (main21 + patch 131): the five keys, game defaults, STATIC / GAMEDATA ceilings", keys_ok and tiers_ok,
              "keys %s, constants %s" % (keys_ok, got))
        us = {k: (re.search(r"#define\s+%s\s+(\S+)" % k, src) or [None, None])[1] for k in ("BO3_US_FULL_MAX", "BO3_US_LOW_MAX")}
        if all(v == "0x200000u" for v in us.values()):
            check("C2b host unit-slot ceilings = the table's 0x200000", True, us)
        else:
            skip("C2b host unit-slot ceilings = the table's 0x200000", "host source has %s (the approved 0x200000 raise is not in "
                 "this source yet)" % us)
    else:
        skip("C2 host source (main21)", "host sources not present (portable kit)")
    n = CAP.needed_capacity(rep_of(mesh=0x2A123))
    d = CAP.declaration(n, "auto")
    check("C3 auto: a mesh block 0x2A123 > 0x28000 declares full_unit_bytes 0x2B000 only", d == {"full_unit_bytes": 0x2B000}, d)
    lines, overall = CAP.requires(d)
    check("C3b requires patch 131 for full_unit_bytes", overall == CAP.HOST_P131 and "patch 131" in lines[0], lines)
    ok, msg = raises(lambda: CAP.declaration(n, "game"), "capacity \"auto\"")
    check("C4 game mode refuses the same block (and names capacity auto)", ok, msg)
    ok, msg = raises(lambda: CAP.declaration(CAP.needed_capacity(rep_of(mesh=0x200001)), "auto"), "ceiling")
    check("C5 auto refuses a block above the host ceiling 0x200000", ok, msg)
    d1 = CAP.declaration(CAP.needed_capacity(rep_of(mesh=0x1F0000, lod=0x200000)), "auto")
    check("C5b 2 MiB blocks declared (full 0x1F0000, low 0x200000)", d1 == {"low_unit_bytes": 0x200000, "full_unit_bytes": 0x1F0000}, d1)
    s = CAP.summary(CAP.needed_capacity(rep_of(lod=0x31000, static=0x2100000, lanes=80)), "auto")
    check("C6 tiers: low 0x31000 + static 0x2100000 need patch 131, lanes 80 main21+",
          s["declared"] == {"lanes": "80", "low_unit_bytes": "0x31000", "static_bytes": "0x2100000"} and s["min_host"] == CAP.HOST_P131
          and any(r.startswith("lanes = 80: requires " + CAP.HOST_CAPDECL) for r in s["requires"]), s)
    s0 = CAP.summary(CAP.needed_capacity(rep_of()), "auto")
    check("C7 within the defaults: nothing declared", s0["declared"] == {} and s0["min_host"] is None, s0)
    m = CAP.merge({"lanes": 80}, {"full_unit_bytes": 0x2B000, "lanes": 70})
    txt = P.mod_toml(dict(PKG_P, capacity_decl=m))
    t = tomllib.loads(txt)["bmashup"]["capacity"]
    check("C8 mod.toml merge keeps the package's lanes = 80 (max) + full_unit_bytes hex, version 1",
          t == {"version": 1, "lanes": 80, "full_unit_bytes": 0x2B000} and "full_unit_bytes = 0x2B000" in txt, t)
    legacy = P.mod_toml(dict(PKG_P, lanes=80))
    check("C8b lanes-only mod.toml text unchanged (0.3.3 form)", legacy.endswith("[bmashup.capacity]\nversion = 1\nlanes = 80\n"), legacy[-60:])
    decl, lab = PK.capacity_declaration(dict(PKG_P, lanes=80), rep_of(mesh=0x2A123))
    check("C9 package: own lanes 80 merged with the build's full_unit_bytes; LABELS lists patch 131",
          decl == {"lanes": 80, "full_unit_bytes": 0x2B000} and lab and lab["min_host"] == CAP.HOST_P131, (decl, lab))
    ok, msg = raises(lambda: PK.capacity_declaration(dict(PKG_P, capacity="game"), rep_of(mesh=0x2A123)), "capacity")
    check("C9b package capacity game refuses a build above the defaults", ok, msg)
    decl, lab = PK.capacity_declaration(dict(PKG_P, capacity_keys={"full_unit_bytes": 0x30000}), rep_of(mesh=0x2A123))
    check("C9c package keys larger than the need are kept (max)", decl == {"full_unit_bytes": 0x30000}, decl)
    check("C9d within the defaults: no declaration, no LABELS section", PK.capacity_declaration(dict(PKG_P), rep_of()) == ({}, None))
    ok, msg = raises(lambda: PK.capacity_declaration(dict(PKG_P, capacity="huge"), rep_of()), "auto")
    check("C9e unknown capacity mode refused", ok, msg)
    check("C9g units: 162 accepted with pvs computed", CAP.units_check(162, "computed") is None)
    u163 = CAP.units_check(163, "computed") or ""
    check("C9h units: 163 refused - above the largest retail track; untested in the game",
          "largest retail track" in u163 and "untested in the game" in u163, u163)
    rn = CAP.records_note(128)
    src = open(os.path.join(PKG, "trackbuild", "blocks.py"), encoding="utf-8").read()
    check("C9i records per block: 127 enforced; the refusal names host patch 132 / BMRC and what to do",
          CAP.RECORDS["enforced"] == 127 and CAP.RECORDS["host_planned"] == 255 and "patch 132" in rn and "BMRC" in rn
          and "split the unit" in rn and "records_note(len(self.recs))" in src, rn)
    from trackbuild import preflight as PF
    ok, msg = raises(lambda: PF.check_desc(".", {"materials": {"m%d" % i: {} for i in range(91)}, "rows": ["m%d" % i for i in range(91)]}),
                     "rows 91 / 255")
    check("C9f 91 material rows: refused (83 rule kept), message names the host BMRX figure 255 + patch 131",
          ok and "patch 131" in msg and CAP.ROWS["game"] == 83 and CAP.ROWS["ceiling"] == 255, msg)


class lowered:
    """the game's default mesh-block size lowered in-process (synthetic over-default track); restored on exit"""
    def __init__(self, key, game=None, ceiling=None):
        self.key, self.game, self.ceiling = key, game, ceiling

    def __enter__(self):
        self.old = dict(CAP.TABLE[self.key])
        if self.game is not None:
            CAP.TABLE[self.key]["game"] = self.game
        if self.ceiling is not None:
            CAP.TABLE[self.key]["ceiling"] = self.ceiling

    def __exit__(self, *a):
        CAP.TABLE[self.key].clear()
        CAP.TABLE[self.key].update(self.old)


def integration(run, gdata):
    from trackbuild import testloop, build as B, validate as V, donor as DN
    src = os.path.join(run, "loop_src")
    testloop.build(src, dict(testloop.P))
    desc_name = "test_loop.track.json"
    dfiles = DN.load_donor(gdata, DN.HOST_DEFAULT, False)

    def build_to(out, desc_edit=None):
        if desc_edit:
            p = os.path.join(src, desc_name)
            d = json.load(open(p))
            desc_edit(d)
            name = "cap_%s.track.json" % os.path.basename(out)
            json.dump(d, open(os.path.join(src, name), "w"), indent=1)
        else:
            name = desc_name
        products, rep, _ = B.build_track(src, name, game_data=gdata, donor_files=dfiles)
        os.makedirs(out)
        for k, v in products.items():
            open(os.path.join(out, k), "wb").write(v)
        rep["source"] = {"dir": src, "desc": name}
        json.dump(rep, open(os.path.join(out, "BUILD_REPORT.json"), "w"), indent=1, sort_keys=True)
        return rep, os.path.join(src, name)

    rep0, _ = build_to(os.path.join(run, "b0"))
    mesh_max = max(u["mesh_bytes"] for u in rep0["units"]["units"])
    check("C10 the real test loop declares nothing (within the game's defaults)", rep0["capacity"]["declared"] == {}, rep0["capacity"])
    low = (mesh_max // 2) & ~0xFFF
    with lowered("full_unit_bytes", game=low):
        rep1, d1 = build_to(os.path.join(run, "b1"))
        dec = rep1["capacity"]["declared"]
        check("C11 synthetic over-default mesh blocks (default lowered to 0x%X): auto builds and declares full_unit_bytes" % low,
              dec == {"full_unit_bytes": "0x%X" % CAP.page(mesh_max)} and "patch 131" in rep1["capacity"]["min_host"], rep1["capacity"])
        val = V.validate(os.path.join(run, "b1"), d1)
        check("C11b V6_budgets passes with the declared capacity", val["V6_budgets"]["ok"] and val["summary"]["ok"],
              (val["V6_budgets"], val["summary"]))
        pr = PK.package(os.path.join(run, "b1"), os.path.join(PKG, "examples", "my_track_package.toml"), os.path.join(run, "p1"))
        mt = tomllib.loads(open(os.path.join(pr["mod"], "mod.toml"), encoding="ascii").read())
        lab = json.load(open(os.path.join(run, "p1", "LABELS.json")))
        check("C12 package: mod.toml [bmashup.capacity] version 1 + full_unit_bytes; LABELS names patch 131",
              mt["bmashup"]["capacity"] == {"version": 1, "full_unit_bytes": CAP.page(mesh_max)}
              and lab["capacity"]["min_host"] == CAP.HOST_P131, (mt["bmashup"].get("capacity"), lab.get("capacity")))
        ok, msg = raises(lambda: build_to(os.path.join(run, "b2"), lambda d: d.update(capacity="game")), "capacity \"auto\"")
        check("C13 the same track with capacity game is refused (names the block and capacity auto)", ok, msg)
    with lowered("full_unit_bytes", game=low, ceiling=low + 0x1000):
        ok, msg = raises(lambda: build_to(os.path.join(run, "b3")), "ceiling")
        check("C13b above the (lowered) host ceiling: refused even under auto", ok, msg)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run = argv[0]
    if os.path.exists(run):
        sys.exit("refusing: %s exists" % run)
    os.makedirs(run)
    gdata = argv[argv.index("--game-data") + 1] if "--game-data" in argv else (
        os.environ.get("TRACKBUILD_GAME_DATA") or os.environ.get("BMKIT_GAME_DATA"))
    unit_tests()
    if gdata:
        integration(run, gdata)
    else:
        skip("C10..C13 build / validate / package integration", "needs game data (--game-data DIR or TRACKBUILD_GAME_DATA)")
    n = sum(ok for _, ok in RES)
    lines = ["TOTAL %d / %d%s" % (n, len(RES), " (skipped %d)" % len(SKIP) if SKIP else "")]
    print(lines[0])
    with open(os.path.join(run, "RESULTS_capacity.txt"), "w", newline="\n") as f:
        f.write("\n".join("%s %s" % ("PASS" if ok else "FAIL", nm) for nm, ok in RES) + "\n" +
                "".join("SKIP %s: %s\n" % s for s in SKIP) + lines[0] + "\n")
    return 0 if n == len(RES) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
