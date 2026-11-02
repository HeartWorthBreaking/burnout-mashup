"""trackbuild 0.3.0 - every test suite in one command.

    py -3 -B tests\\run_tests.py RUN_DIR [--game-data DIR] [--converted TRACK_DIR]

RUN_DIR must not exist. Runs tb.py selfcheck, tests\\test_errors.py, tests\\test_trackbuild.py, tests\\test_regression.py and
tests\\test_slopes.py (0.3.0), tests\\test_capacity.py (0.3.4; each in RUN_DIR\\<suite>) and writes RUN_DIR\\SUMMARY.txt. Game data: --game-data DIR, else TRACKBUILD_GAME_DATA /
BMKIT_GAME_DATA; without it the game-data checks are SKIPPED (named in each RESULTS file). Exit 0 = no failure."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)
from trackbuild import accessguard  # noqa: E402
accessguard.install_from_env()                         # opt-in isolation monitor (TRACKBUILD_ACCESS_LOG); no-op otherwise


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run = argv[0]
    if os.path.exists(run):
        sys.exit("refusing: %s exists" % run)
    os.makedirs(run)
    gd = ["--game-data", argv[argv.index("--game-data") + 1]] if "--game-data" in argv else []
    cv = ["--converted", argv[argv.index("--converted") + 1]] if "--converted" in argv else []
    suites = [("selfcheck", [os.path.join(PKG, "tb.py"), "selfcheck"]),
              ("errors", [os.path.join(HERE, "test_errors.py"), os.path.join(run, "errors")] + gd),
              ("trackbuild", [os.path.join(HERE, "test_trackbuild.py"), os.path.join(run, "trackbuild")] + gd + cv),
              ("regression", [os.path.join(HERE, "test_regression.py"), os.path.join(run, "regression")] + gd),
              ("slopes", [os.path.join(HERE, "test_slopes.py"), os.path.join(run, "slopes")] + gd),
              ("capacity", [os.path.join(HERE, "test_capacity.py"), os.path.join(run, "capacity")] + gd)]   # 0.3.4
    out, bad = [], 0
    for name, cmd in suites:
        r = subprocess.run([sys.executable, "-B"] + cmd, capture_output=True, text=True)
        tail = [ln for ln in r.stdout.splitlines() if ln.startswith(("TOTAL", "SKIP", "FAIL"))] if name != "selfcheck" else []
        out.append("%-11s rc %d  %s" % (name, r.returncode, " | ".join(t for t in tail if t.startswith("TOTAL"))))
        out += ["    " + t for t in tail if not t.startswith("TOTAL")]
        if r.returncode:
            bad += 1
            out.append("    stderr: " + r.stderr.strip()[-400:].replace("\n", " | "))
        with open(os.path.join(run, "%s.log" % name), "w", newline="\n") as f:
            f.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
    out.append("SUITES FAILED %d / %d" % (bad, len(suites)))
    print("\n".join(out))
    with open(os.path.join(run, "SUMMARY.txt"), "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
