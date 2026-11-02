"""trackbuild 0.3.0 - build an ORIGINAL Burnout 3 track (OBJ + PNG + track description) into a Burnout Mashup data mod.

  py -3 -B tb.py gen-testloop SRC_DIR [--variant crash|bright_b|zeroed|lod_tint|canyon|hill|branch|fig8]   the ORIGINAL procedural demo sources
  py -3 -B tb.py check-game-data --game-data DIR [--host RR/NN_VN]          check the donor files (hashes) and stop
  py -3 -B tb.py build SRC_DIR DESC.json OUT_DIR --game-data DIR [--host RR/NN_VN] [--unpinned-donor]
  py -3 -B tb.py validate OUT_DIR [DESC.json]                               independent gates -> VALIDATION.json
  py -3 -B tb.py inspect OUT_DIR                                            per-unit summary of a build
  py -3 -B tb.py package OUT_DIR PACKAGE.toml SET_ROOT [--bmpack FILE]      the mod set (needs a passing validate)
  py -3 -B tb.py capacity [OUT_DIR]                                         0.3.4: game defaults / host ceilings; with OUT_DIR the
                                                                            build's need and its mod.toml [bmashup.capacity]
  py -3 -B tb.py selfcheck                                                  Python version + package completeness
  py -3 -B tb.py version

--game-data may be replaced by TRACKBUILD_GAME_DATA or BMKIT_GAME_DATA. Output folders must be new (or empty): nothing is
overwritten. Exit codes: 0 ok, 1 validation / host check failed, 2 usage or path error, 3 missing prerequisite (Python,
package files, game data), 4 unsupported input (refused with the reason). README.md: quick start; docs/ADVANCED.md: details."""
import sys

MIN_PYTHON = (3, 11)
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_PREREQ, EXIT_INPUT = 0, 1, 2, 3, 4


def python_problem(version=None):
    v = tuple(version or sys.version_info[:2])
    if v < MIN_PYTHON:
        return ("Python %d.%d found; trackbuild needs Python %d.%d or later (it uses tomllib). Install a current Python 3 from "
                "python.org and run: py -3 -B tb.py ... (or the full path of that python.exe)." % (v[0], v[1], MIN_PYTHON[0], MIN_PYTHON[1]))
    return None


def _say(kind, msg):
    sys.stderr.write("trackbuild: %s: %s\n" % (kind, msg))


if __name__ == "__main__":
    _p = python_problem()
    if _p:
        _say("CANNOT RUN", _p)
        sys.exit(EXIT_PREREQ)

import os  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)                          # package-relative only: the trackbuild package next to this file
if __name__ == "__main__":
    try:                                              # opt-in access monitor (TRACKBUILD_ACCESS_LOG), first thing loaded
        from trackbuild import accessguard as _ag
        _ag.install_from_env()
    except ImportError:
        pass                                          # reported by _import_package with the actionable message

import json  # noqa: E402


class UsageError(Exception):
    pass


def _import_package():
    """import every module; a missing / damaged file -> an actionable prerequisite error"""
    try:
        import trackbuild  # noqa: F401
        from trackbuild import build, validate, pack, testloop, donor, preflight  # noqa: F401
        return trackbuild
    except ImportError as e:
        raise PrereqError("the trackbuild package next to tb.py is incomplete (%s). Unpack the whole trackbuild folder again "
                          "(tb.py, trackbuild\\ and trackbuild\\_vendor\\ belong together) and run: py -3 -B tb.py selfcheck" % e)


class PrereqError(Exception):
    pass


def _fresh(d, what):
    if os.path.exists(d) and not os.path.isdir(d):
        raise UsageError("%s %s exists and is a file; give a new folder" % (what, d))
    if os.path.isdir(d) and os.listdir(d):
        raise UsageError("%s %s exists and is not empty; trackbuild never overwrites: give a new folder" % (what, d))
    parent = os.path.dirname(os.path.abspath(d))
    if not os.path.isdir(parent):
        raise UsageError("%s %s: its parent folder %s does not exist; create it first" % (what, d, parent))
    os.makedirs(d, exist_ok=True)


def _need_dir(d, what):
    if not os.path.isdir(d):
        raise UsageError("%s %s does not exist or is not a folder" % (what, d))


def _need_file(p, what):
    if not os.path.isfile(p):
        raise UsageError("%s %s does not exist or is not a file" % (what, p))


def _parser():
    import argparse

    class P(argparse.ArgumentParser):
        def error(self, message):
            raise UsageError("%s (run: py -3 -B tb.py --help)" % message)
    ap = P(prog="tb.py", description="trackbuild 0.3.0", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sp = ap.add_subparsers(dest="cmd")
    g = sp.add_parser("gen-testloop")
    g.add_argument("src_dir")
    g.add_argument("--variant", choices=["crash", "bright_b", "zeroed", "lod_tint", "canyon", "hill", "branch", "fig8"])
    c = sp.add_parser("check-game-data")
    c.add_argument("--game-data")
    c.add_argument("--host", default=None)
    c.add_argument("--unpinned-donor", action="store_true")
    b = sp.add_parser("build")
    b.add_argument("src_dir")
    b.add_argument("desc")
    b.add_argument("out_dir")
    b.add_argument("--game-data")
    b.add_argument("--host", default=None)
    b.add_argument("--unpinned-donor", action="store_true")
    v = sp.add_parser("validate")
    v.add_argument("out_dir")
    v.add_argument("desc", nargs="?")
    i = sp.add_parser("inspect")
    i.add_argument("out_dir")
    k = sp.add_parser("package")
    k.add_argument("out_dir")
    k.add_argument("toml")
    k.add_argument("set_root")
    k.add_argument("--bmpack")
    cp = sp.add_parser("capacity")
    cp.add_argument("out_dir", nargs="?")
    sp.add_parser("selfcheck")
    sp.add_parser("version")
    return ap


def _build_sha(out_dir):
    import hashlib
    from trackbuild._vendor.trackconv.package import FILES
    return {f: hashlib.sha256(open(os.path.join(out_dir, f), "rb").read()).hexdigest() for f in sorted(FILES)}


def _need_build(out_dir):
    _need_dir(out_dir, "build folder")
    from trackbuild._vendor.trackconv.package import FILES
    miss = [f for f in ("BUILD_REPORT.json",) + FILES if not os.path.isfile(os.path.join(out_dir, f))]
    if miss:
        raise UsageError("%s is not a complete trackbuild build folder (missing %s); run tb.py build into a new folder" % (out_dir, ", ".join(miss)))


def run(argv):
    a = _parser().parse_args(argv)
    if not a.cmd:
        print(__doc__)
        return EXIT_USAGE
    tb = _import_package()
    if a.cmd == "version":
        print(json.dumps({"trackbuild": tb.VERSION, "succeeds": tb.SUCCEEDS, "python": "%d.%d.%d" % sys.version_info[:3]}))
        return EXIT_OK
    if a.cmd == "selfcheck":
        return selfcheck(tb)
    if a.cmd == "capacity":                                       # 0.3.4: the capacity table / a build's declaration
        from trackbuild import capacity as CAP
        if not a.out_dir:
            print(json.dumps(CAP.table_json(), indent=1))
            return EXIT_OK
        _need_build(a.out_dir)
        rep = json.load(open(os.path.join(a.out_dir, "BUILD_REPORT.json")))
        units = (rep.get("units") or {}).get("units") or []
        print(json.dumps({"capacity": rep.get("capacity") or CAP.summary(CAP.needed_capacity(rep), "auto"),
                          "units": [{"unit": r["unit"], "mesh": "0x%X" % r["mesh"], "lod": "0x%X" % r["lod"], "mesh_state": r["mesh_state"],
                                     "lod_state": r["lod_state"], "notes": r["notes"]}
                                    for r in CAP.unit_usage(units, (rep.get("capacity") or {}).get("mode", "auto"))
                                    if r["notes"]]}, indent=1))
        return EXIT_OK
    from trackbuild import donor
    if a.cmd == "gen-testloop" and a.variant == "fig8":
        from trackbuild import fig8
        _fresh(a.src_dir, "source folder")
        print(json.dumps(fig8.build(a.src_dir)))
        return EXIT_OK
    if a.cmd == "gen-testloop":
        from trackbuild import testloop
        _fresh(a.src_dir, "source folder")
        p = dict(testloop.P)
        if a.variant:
            p.update({"crash": testloop.CRASH_VARIANT, "bright_b": testloop.BRIGHT_B_VARIANT,
                      "zeroed": testloop.ZEROED_HEADER_VARIANT, "lod_tint": testloop.LOD_TINT_VARIANT,
                      "canyon": testloop.CANYON_VARIANT, "hill": testloop.HILL_VARIANT,
                      "branch": testloop.BRANCH_VARIANT}[a.variant])
        print(json.dumps(testloop.build(a.src_dir, p)))
        return EXIT_OK
    if a.cmd == "check-game-data":
        host = a.host or donor.HOST_DEFAULT
        files = donor.load_donor(a.game_data, host, a.unpinned_donor)
        root, src = donor.resolve(a.game_data)
        print(json.dumps({"game_data": root, "from": src, "host": host, "pinned": host in donor.DONOR_PINS,
                          "files_ok": sorted(files)}, indent=1))
        return EXIT_OK
    if a.cmd == "build":
        from trackbuild import build as B
        _need_dir(a.src_dir, "source folder")
        _need_file(os.path.join(a.src_dir, a.desc), "track description")
        host = a.host or B.HOST_DEFAULT
        donor.resolve(a.game_data)                    # no / wrong game-data folder: stop before any work (hashes: at use)
        if host not in donor.DONOR_PINS and not a.unpinned_donor:
            donor.load_donor(a.game_data, host, False)              # raises the actionable "unpinned host" refusal
        _fresh(a.out_dir, "output folder")
        products, report, _ = B.build_track(a.src_dir, a.desc, host, game_data=a.game_data, unpinned_donor=a.unpinned_donor)
        for k_, v_ in products.items():
            with open(os.path.join(a.out_dir, k_), "wb") as fh:
                fh.write(v_)
        report["source"] = {"dir": os.path.abspath(a.src_dir), "desc": a.desc}
        report["trackbuild"] = tb.VERSION
        report["donor_pinned"] = host in donor.DONOR_PINS
        with open(os.path.join(a.out_dir, "BUILD_REPORT.json"), "w", newline="\n") as fh:
            json.dump(report, fh, indent=1, sort_keys=True)
        print(json.dumps({k_: report[k_] for k_ in ("static", "streamed", "route", "gamedata")}, indent=1))
        print("next: py -3 -B tb.py validate %s" % a.out_dir)
        return EXIT_OK
    if a.cmd == "validate":
        from trackbuild import validate as V
        _need_build(a.out_dir)
        desc = a.desc
        if desc is None:
            rep = json.load(open(os.path.join(a.out_dir, "BUILD_REPORT.json")))
            desc = os.path.join(rep["source"]["dir"], rep["source"]["desc"])
            if not os.path.isfile(desc):
                raise UsageError("the track description recorded in BUILD_REPORT.json (%s) is gone (moved source folder?); give it: "
                                 "tb.py validate %s <path to the .track.json>" % (desc, a.out_dir))
        else:
            _need_file(desc, "track description")
        res = V.validate(a.out_dir, desc)
        res["trackbuild"] = {"version": tb.VERSION, "build_sha256": _build_sha(a.out_dir)}
        with open(os.path.join(a.out_dir, "VALIDATION.json"), "w", newline="\n") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
        print(json.dumps(res["summary"], indent=1))
        if not res["summary"]["ok"]:
            _say("VALIDATION FAILED", "gate(s) %s failed (details in %s). The build must not be packaged: fix the source (see "
                 "docs/ADVANCED.md 'Validation gates' for what each gate checks) and build again."
                 % (", ".join(res["summary"]["failed"]), os.path.join(a.out_dir, "VALIDATION.json")))
            return EXIT_FAILED
        print("next: py -3 -B tb.py package %s <PACKAGE.toml> <SET_ROOT>" % a.out_dir)
        return EXIT_OK
    if a.cmd == "inspect":
        from trackbuild import validate as V
        _need_build(a.out_dir)
        print(json.dumps(V.inspect(a.out_dir), indent=1))
        return EXIT_OK
    if a.cmd == "package":
        from trackbuild import pack
        _need_build(a.out_dir)
        _need_file(a.toml, "package description")
        vp = os.path.join(a.out_dir, "VALIDATION.json")
        if not os.path.isfile(vp):
            raise UsageError("%s has not been validated: run py -3 -B tb.py validate %s first" % (a.out_dir, a.out_dir))
        val = json.load(open(vp))
        if not val.get("summary", {}).get("ok"):
            _say("VALIDATION FAILED", "%s failed gate(s) %s; a failing build is never packaged" % (vp, val.get("summary", {}).get("failed")))
            return EXIT_FAILED
        if (val.get("trackbuild") or {}).get("build_sha256") != _build_sha(a.out_dir):
            raise UsageError("VALIDATION.json in %s does not belong to the current track files (changed after validate, or written by "
                             "trackbuild 0.1.x); run tb.py validate %s again" % (a.out_dir, a.out_dir))
        if os.path.exists(a.set_root) and not os.path.isdir(a.set_root):
            raise UsageError("SET_ROOT %s is a file; give a folder" % a.set_root)
        if os.path.isfile(os.path.join(a.set_root, "SHA256SUMS.txt")) or os.path.isfile(os.path.join(a.set_root, "LABELS.json")):
            raise UsageError("SET_ROOT %s already holds a packaged set (SHA256SUMS.txt / LABELS.json); give a new folder" % a.set_root)
        print(json.dumps(pack.package(a.out_dir, a.toml, a.set_root, a.bmpack), indent=1))
        return EXIT_OK
    raise UsageError("unknown command %s" % a.cmd)


def selfcheck(tb):
    """Python version, tomllib, every vendored file present with its recorded hash (VENDOR.json)"""
    import hashlib
    import importlib
    probs = []
    p = python_problem()
    if p:
        probs.append(p)
    try:
        importlib.import_module("tomllib")
    except ImportError:
        probs.append("the Python standard module tomllib is missing (Python 3.11+ required)")
    vdir = os.path.join(HERE, "trackbuild", "_vendor")
    vj = os.path.join(vdir, "VENDOR.json")
    n = 0
    if not os.path.isfile(vj):
        probs.append("trackbuild\\_vendor\\VENDOR.json is missing")
    else:
        for f in json.load(open(vj))["files"]:
            fp = os.path.join(HERE, "trackbuild", *f["file"].split("/"))
            n += 1
            if not os.path.isfile(fp):
                probs.append("missing %s" % f["file"])
            elif hashlib.sha256(open(fp, "rb").read()).hexdigest() != f["vendored_sha256"]:
                probs.append("changed %s (sha256 differs from VENDOR.json)" % f["file"])
    print(json.dumps({"trackbuild": tb.VERSION, "python": "%d.%d.%d" % sys.version_info[:3], "vendored_files_checked": n,
                      "problems": probs}, indent=1))
    if probs:
        raise PrereqError("selfcheck found %d problem(s): %s. Unpack the whole trackbuild folder again." % (len(probs), "; ".join(probs[:4])))
    return EXIT_OK


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = python_problem()
    if p:
        _say("CANNOT RUN", p)
        return EXIT_PREREQ
    try:
        return run(argv)
    except UsageError as e:
        _say("USAGE", str(e))
        return EXIT_USAGE
    except PrereqError as e:
        _say("CANNOT RUN", str(e))
        return EXIT_PREREQ
    except Exception as e:  # noqa: BLE001  (classified below; anything else is a bug and keeps its traceback)
        kind = _classify(e)
        if kind is None:
            raise
        code, label = kind
        _say(label, str(e))
        return code


def _classify(e):
    mods = sys.modules
    tb_io = mods.get("trackbuild.io")
    dn = mods.get("trackbuild.donor")
    pk = mods.get("trackbuild.pack")
    tc = mods.get("trackbuild._vendor.trackconv.common")
    bp = mods.get("trackbuild._vendor.bmpack_min")
    gd = mods.get("trackbuild._vendor.ct2_gamedata")
    rt = mods.get("trackbuild._vendor.ct2_route")
    if dn and isinstance(e, dn.DonorError):
        return EXIT_PREREQ, "CANNOT RUN (game data)"
    if tb_io and isinstance(e, tb_io.SourceError):
        return EXIT_INPUT, "REFUSED (unsupported input)"
    if tc and isinstance(e, tc.TCError):
        return EXIT_INPUT, "REFUSED (unsupported input / package decision)"
    if (gd and isinstance(e, getattr(gd, "GamedataError", ()))) or (rt and isinstance(e, getattr(rt, "RouteError", ()))):
        return EXIT_INPUT, "REFUSED (route / Gamedata rule)"
    if pk and isinstance(e, pk.PackageError):
        return EXIT_FAILED, "PACKAGE FAILED"
    if bp and isinstance(e, bp.BmpackError):
        return EXIT_FAILED, "PACKAGE FAILED"
    if isinstance(e, KeyError):
        return EXIT_INPUT, "REFUSED (the description lacks the key %s; compare with a gen-testloop description)" % e
    if isinstance(e, PermissionError):
        return EXIT_USAGE, "USAGE (no permission: %s)" % getattr(e, "filename", "")
    return None


if __name__ == "__main__":
    sys.exit(main())
