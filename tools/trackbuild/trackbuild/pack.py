"""trackbuild.pack - a built track folder -> a Burnout Mashup data mod (trackconv.package: mod.toml, bmpack.json with the
Gamedata rename donor ID -> new ID, files\\Tracks\\RR\\NN_VN\\, SHA256SUMS.txt) + LABELS.json.
The package decisions come from a TOML file ([package] table, trackconv profile keys).

0.2.0: trackconv / bmpack are the vendored pure-Python subsets (trackbuild/_vendor); the packaged bytes are those of 0.1.6.
The host-reader check (bmpack validate, which compiles the host's real parsers) is no longer implicit: pass the mod kit's
bmpack.py with --bmpack FILE (package then runs `bmpack.py validate SET` and fails on a refusal), or run it yourself."""
import json
import os
import subprocess
import sys
import tomllib

from ._vendor.trackconv import package as P  # noqa: E402
from ._vendor.trackconv.common import OutRoot  # noqa: E402


class PackageError(Exception):
    """a packaging precondition or the optional host-reader check failed; the message says what to do"""


def _decisions(toml_path):
    try:
        with open(toml_path, "rb") as f:
            t = tomllib.load(f)
    except OSError as e:
        raise PackageError("cannot read the package description %s: %s" % (toml_path, e.strerror or e))
    except tomllib.TOMLDecodeError as e:
        raise PackageError("%s is not valid TOML: %s. Compare it with examples\\test_loop_package.toml." % (toml_path, e))
    if not isinstance(t.get("package"), dict):
        raise PackageError("%s has no [package] table (see examples\\test_loop_package.toml)" % toml_path)
    p = t["package"]
    miss = [k for k in ("set", "folder", "track_id", "track_name", "track_location", "mod_id", "mod_name", "version", "author")
            if k not in p]
    if miss:
        raise PackageError("%s [package] lacks %s (see examples\\test_loop_package.toml)" % (toml_path, ", ".join(miss)))
    return p


def package(build_dir, toml_path, set_root, bmpack=None):
    p = _decisions(toml_path)
    if bmpack:
        bmpack = _bmpack_file(bmpack)                            # a wrong --bmpack is refused before anything is written
    rep = json.load(open(os.path.join(build_dir, "BUILD_REPORT.json")))
    products = {f: open(os.path.join(build_dir, f), "rb").read() for f in P.FILES}
    donor_id = rep["host"].replace("/", "_")
    out = OutRoot(set_root)
    r = P.package(out, p, products, donor_id, None, validate=False)
    host = None
    if bmpack:
        host = host_check(bmpack, r["set"])
    P.write_sums(out, r["rels"])
    authored_traffic = rep["gamedata"].get("authored_traffic", False)
    labels = {"track": p["track_id"], "AUTHORED": ["static.dat", "streamed.dat", "Gamedata.bgd S1 page + S4 route" +
                                                   (" + S2 traffic set + S3 lane network" if authored_traffic else "")],
              "DONOR": ["Gamedata.bgd header / event records%s (%s)" % ("" if authored_traffic else " / S2 traffic sets / S3 lane network",
                                                                       rep["host"])] + sorted(rep["label"]["donor"]),
              "gamedata_label": rep["label"]["Gamedata.bgd"],
              "build_sha256": rep["sha256"]}
    out.write("LABELS.json", (json.dumps(labels, indent=1, sort_keys=True) + "\n").encode())
    return {"set": r["set"], "mod": r["mod"], "files": r["files"], "renamed": r["renamed"],
            "validate": host or {"host_readers": "not run (pass --bmpack <mod kit>\\tools\\bmpack\\bmpack.py, or run bmpack validate on the set)"}}


def _bmpack_file(bmpack):
    bmpack = os.path.abspath(bmpack)
    if not os.path.isfile(bmpack) or os.path.basename(bmpack).lower() != "bmpack.py":
        raise PackageError("--bmpack %s: not a bmpack.py file. Give the mod kit's tools\\bmpack\\bmpack.py." % bmpack)
    return bmpack


def host_check(bmpack, set_dir):
    """run the mod kit's bmpack validate on the set (the host's real readers); refusal -> PackageError"""
    bmpack = _bmpack_file(bmpack)
    r = subprocess.run([sys.executable, "-B", bmpack, "validate", set_dir], capture_output=True, text=True)
    if r.returncode != 0:
        raise PackageError("the host's readers (bmpack validate, rc %d) refuse or could not check the set %s:\n%s%s\nThe mod files are "
                           "written but NOT accepted: fix the refusal (or the bmpack configuration it names) and package again into a "
                           "new folder." % (r.returncode, set_dir, r.stdout[-1500:], r.stderr[-800:]))
    return {"host_readers": "bmpack validate rc 0", "bmpack": bmpack, "summary_tail": r.stdout.strip().splitlines()[-1:]}
