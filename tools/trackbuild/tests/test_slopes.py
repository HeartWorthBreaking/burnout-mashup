"""trackbuild 0.3.0 sloped routes: a route may climb and descend; the floor gate follows each station's own height.

    py -3 -B tests\\test_slopes.py RUN_DIR [--game-data DIR]

h01 hill pipeline (documented CLI): gen-testloop --variant hill -> build --game-data -> validate -> package
    (examples\\hill_package.toml): every gate passes; the route really climbs (station heights span >= 7.9 m, max grade >= 3 %),
    the floor stays within 0.05 m of the route everywhere; the start line / grid / first 30 % of the lap stay flat; the BUILT
    AI route (Gamedata S4, parsed by the vendored ct2_route reader) carries the station heights on its nodes;
h02 route lifted 0.3 m above the road (every station y + 0.3): V2_drivable_coverage refuses it (the gate binds the route to the
    road surface, it is not just relaxed);
h03 route flattened to the start height on the hill geometry (what 0.2.1 required): V2_drivable_coverage AND V2_walls_hold
    refuse it (the wall probes run at each station's height).
Needs YOUR game data (the donor parts): --game-data DIR, else TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA; without it every check is
SKIPPED with that message. Results: RUN_DIR/RESULTS_slopes.txt."""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
TB = os.path.join(PKG, "tb.py")
sys.path.insert(0, PKG)
from trackbuild import accessguard  # noqa: E402
accessguard.install_from_env()                         # opt-in isolation monitor (TRACKBUILD_ACCESS_LOG); no-op otherwise
from trackbuild._vendor import ct2_gamedata as GD  # noqa: E402
from trackbuild._vendor import ct2_route as CR  # noqa: E402

DESC = "test_loop.track.json"


def tb(*args):
    r = subprocess.run([sys.executable, "-B", TB] + list(args), capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()[-400:]


def validation(out):
    return json.load(open(os.path.join(out, "VALIDATION.json"), encoding="utf-8"))


def h01(run, gd):
    src, out, pkg = (os.path.join(run, "hill" + x) for x in ("_src", "_build", "_pkg"))
    for st in (["gen-testloop", src, "--variant", "hill"], ["build", src, DESC, out, "--game-data", gd], ["validate", out],
               ["package", out, os.path.join(PKG, "examples", "hill_package.toml"), pkg]):
        rc, tail = tb(*st)
        assert rc == 0, "%s rc %d: %s" % (st[0], rc, tail)
    v = validation(out)
    assert v["summary"]["ok"] and not v["summary"]["failed"], v["summary"]
    d = v["V2_drivable_coverage"]["detail"]
    desc = json.load(open(os.path.join(src, DESC), encoding="utf-8"))
    ys = [s["p"][1] for s in desc["stations"]]
    y0 = desc["generator"]["params"]["y0"]
    assert max(ys) - min(ys) >= 7.9 and d["max_route_grade_pct"] >= 3.0 and d["max_floor_dy"] < 0.05, (max(ys) - min(ys), d)
    n = len(ys)
    assert all(abs(y - y0) < 1e-9 for y in ys[:int(0.30 * n)]), "the first 30 % of the lap is not flat"
    assert desc["start_line"]["pos"][1] == y0 and all(g["pos"][1] == y0 + 0.5 for g in desc["grid"]), "start / grid not flat"
    for c in desc["checkpoints"]:
        st = min(desc["stations"], key=lambda s: (s["p"][0] - c["pos"][0]) ** 2 + (s["p"][2] - c["pos"][2]) ** 2)
        assert abs(c["pos"][1] - st["p"][1]) < 1e-3, ("checkpoint height", c, st["p"])
    gdb = open(os.path.join(out, "Gamedata.bgd"), "rb").read()
    o4, s4 = GD.Gamedata.parse(gdb).s4()
    r = CR.Route.parse(gdb[o4:o4 + s4])
    ny = [q[1] for q in r.pos]
    assert max(ny) - min(ny) >= 7.9, ("built S4 route nodes do not climb", min(ny), max(ny))
    sps = desc["stations_per_slice"]
    nb = len(desc["route"]["lanes"]) + 1                    # nodes per slice (lane boundaries), in slice order
    assert len(ny) == nb * (n // sps), (len(ny), nb, n // sps)
    err = max(abs(ny[k * nb + j] - desc["stations"][k * sps]["p"][1]) for k in range(n // sps) for j in range(nb))
    assert err < 1e-4, ("S4 node heights != the slice stations' heights", err)
    return "all %d gates; stations %.2f..%.2f m, max grade %.2f %%, max floor dy %.4f m; start / grid / first 30 %% flat; built S4 " \
           "nodes %.2f..%.2f m = the slice stations' heights; packaged (%s)" % (
               v["summary"]["gates"], min(ys), max(ys), d["max_route_grade_pct"], d["max_floor_dy"], min(ny), max(ny),
               os.path.basename(pkg))


def mutant(run, gd, name, fn, want_failed):
    src0 = os.path.join(run, "hill_src")
    src, out = os.path.join(run, name + "_src"), os.path.join(run, name + "_build")
    shutil.copytree(src0, src)
    p = os.path.join(src, DESC)
    desc = json.load(open(p, encoding="utf-8"))
    y0 = desc["generator"]["params"]["y0"]
    for s in desc["stations"]:
        s["p"][1] = round(fn(s["p"][1], y0), 4)
    json.dump(desc, open(p, "w", encoding="utf-8", newline="\n"), indent=1)
    rc, tail = tb("build", src, DESC, out, "--game-data", gd)
    assert rc == 0, "build rc %d: %s" % (rc, tail)
    rc, tail = tb("validate", out)
    v = validation(out)
    failed = set(v["summary"]["failed"])
    assert rc != 0 and set(want_failed) <= failed, (rc, sorted(failed))
    return "refused (rc %d): %s" % (rc, ", ".join(sorted(failed)))


def main(argv):
    run = argv[0]
    if os.path.exists(run):
        sys.exit("refusing: %s exists" % run)
    gd = argv[argv.index("--game-data") + 1] if "--game-data" in argv else (
        os.environ.get("TRACKBUILD_GAME_DATA") or os.environ.get("BMKIT_GAME_DATA"))
    os.makedirs(run)
    cases = [("h01 hill pipeline", lambda: h01(run, gd)),
             ("h02 route lifted 0.3 m", lambda: mutant(run, gd, "lifted", lambda y, y0: y + 0.3, ["V2_drivable_coverage"])),
             ("h03 route flattened (0.2.1 rule)", lambda: mutant(run, gd, "flat", lambda y, y0: y0,
                                                                 ["V2_drivable_coverage", "V2_walls_hold"]))]
    lines, npass = [], 0
    if not gd:
        lines = ["SKIP %s (needs game data: give --game-data DIR or TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA)" % c for c, _ in cases]
        tot = "TOTAL 0 / 0 (skipped %d)" % len(cases)
    else:
        for name, fn in cases:
            try:
                lines.append("PASS %s: %s" % (name, fn()))
                npass += 1
            except Exception as e:  # noqa: BLE001
                lines.append("FAIL %s: %s" % (name, repr(e)[:600]))
                if name.startswith("h01"):
                    lines += ["SKIP %s (needs h01's sources)" % c for c, _ in cases[1:]]
                    break
        tot = "TOTAL %d / %d" % (npass, len(cases))
    lines.append(tot)
    print("\n".join(lines))
    open(os.path.join(run, "RESULTS_slopes.txt"), "w", newline="\n").write("\n".join(lines) + "\n")
    return 0 if (not gd or npass == len(cases)) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
