"""trackbuild 0.2.1 regression: the BM Test Loop and BM Canyon Ring packages must be BYTE-IDENTICAL to the trackbuild 0.2.1
reference (tests/REFERENCE_0_2_1.json: sha256 + size of every file of both sets), given the same donor data. 0.2.1 differs from
0.1.6 / 0.2.0 (tests/REFERENCE_0_1_6.json) only in streamed.dat (mesh +0x7D chevron index -1, one byte per unit) and the
manifests that hash it.

    py -3 -B tests\\test_regression.py RUN_DIR [--game-data DIR]

Runs the documented CLI end to end per set: gen-testloop [--variant canyon] -> build --game-data -> validate -> package
(examples\\*_package.toml). Needs YOUR game data (the donor parts are part of the packages): --game-data DIR, else
TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA; without it every check is SKIPPED with that message. Results: RUN_DIR/RESULTS_regression.txt."""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
TB = os.path.join(PKG, "tb.py")
sys.path.insert(0, PKG)
from trackbuild import accessguard  # noqa: E402
accessguard.install_from_env()                         # opt-in isolation monitor (TRACKBUILD_ACCESS_LOG); no-op otherwise


def main(argv):
    run = argv[0]
    if os.path.exists(run):
        sys.exit("refusing: %s exists" % run)
    gdata = argv[argv.index("--game-data") + 1] if "--game-data" in argv else (
        os.environ.get("TRACKBUILD_GAME_DATA") or os.environ.get("BMKIT_GAME_DATA"))
    os.makedirs(run)
    ref = json.load(open(os.path.join(HERE, "REFERENCE_0_2_1.json")))
    lines, ok_all = [], True
    if not gdata:
        for name in ref["sets"]:
            lines.append("SKIP %s byte-identical to 0.2.1 (needs game data: give --game-data DIR or TRACKBUILD_GAME_DATA / "
                         "BMKIT_GAME_DATA)" % name)
        print("\n".join(lines))
        open(os.path.join(run, "RESULTS_regression.txt"), "w", newline="\n").write("\n".join(lines) + "\nTOTAL 0 / 0 (skipped %d)\n" % len(lines))
        return 0
    npass = ntot = 0
    for name, s in ref["sets"].items():
        src, out, pkg = (os.path.join(run, name + x) for x in ("_src", "_build", "_pkg"))
        steps = [["gen-testloop", src] + (["--variant", s["variant"]] if s["variant"] else []),
                 ["build", src, "test_loop.track.json", out, "--game-data", gdata],
                 ["validate", out],
                 ["package", out, os.path.join(PKG, *s["package_toml"].split("/")), pkg]]
        failed = None
        for st in steps:
            r = subprocess.run([sys.executable, "-B", TB] + st, capture_output=True, text=True)
            if r.returncode:
                failed = "%s rc %d: %s" % (st[0], r.returncode, r.stderr.strip()[-300:])
                break
        ntot += 1
        if failed:
            lines.append("FAIL %s pipeline (%s)" % (name, failed))
            ok_all = False
            continue
        got = {}
        for root, _, fs in os.walk(pkg):
            for f in fs:
                p = os.path.join(root, f)
                b = open(p, "rb").read()
                got[os.path.relpath(p, pkg).replace(os.sep, "/")] = [hashlib.sha256(b).hexdigest(), len(b)]
        diff = sorted(k for k in set(got) | set(s["files"]) if got.get(k) != s["files"].get(k))
        ok = not diff
        npass += ok
        ok_all &= ok
        lines.append("%s %s: %d files byte-identical to 0.2.1%s" % ("PASS" if ok else "FAIL", name, len(s["files"]),
                                                                    "" if ok else " - differ: %s" % diff))
        for k in sorted(got):
            lines.append("     %s %s %s" % (got[k][0], got[k][1], k))
    lines.append("TOTAL %d / %d" % (npass, ntot))
    print("\n".join(lines))
    open(os.path.join(run, "RESULTS_regression.txt"), "w", newline="\n").write("\n".join(lines) + "\n")
    return 0 if ok_all else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
