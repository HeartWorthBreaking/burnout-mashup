"""verify.py - check a finished build against the reference recorded in build/EXPECTED.json.

    py -3 -B verify.py --build-dir BUILD_FOLDER [--profile dev|release] [--expected build/EXPECTED.json] [--log LOGDIR/verify.json]
                       [--host-info OUT.json [--takedawn TREE] [--xboxrecomp XR] [--log-dir LOGDIR]]

Profiles: dev = bin/burnout3.exe against EXPECTED.json "build" (the development reference); release = bin/BurnoutMashup.exe (build.ps1
-Release) against EXPECTED.json "build_release". Without --profile the build folder decides: release when bin/BurnoutMashup.exe is there
and bin/burnout3.exe is not, else dev.

Checks, in this order (exit 0 only when 1 and 2 hold; 3 is explanation):
  1. the generated-code objects (recomp/gen/*.obj, 27): sha256 of every object equals the reference's. These are the objects that
     contain your locally generated code with the Mashup marks: equal = the same marked code was compiled the same way.
  2. the executable bin/burnout3.exe: sha256 equals build.exe_sha256. Byte-identical only with the pinned toolchain and the pinned
     inputs (docs/BUILDING.md); the build identity string inside it (bmp-<version>+<12 hex>) is a digest of every source file
     that was built, so ANY different input changes it.
  3. explanation when 1 or 2 fail: identity string vs reference, toolchain versions of the build vs the pins, which of the
     other objects differ (names only). Hashes of objects/exes are not game data; nothing of your game is in this report.
With --host-info OUT.json and exit 0 of checks 1 and 2, host_info.py then writes HOST_INFO.json from this build only (step 7); it refuses
(exit 2, no file) when the exe's identity does not match the source tree. Without a verified build no file is written.
Original code (MIT).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmb_common as C  # noqa: E402


def norm(rel):
    return re.sub(r"\.dir/[0-9a-f]{32}/", ".dir/<h>/", rel)


def objects(build):
    out = {}
    for dp, dn, fn in os.walk(build):
        dn[:] = sorted(d for d in dn if d not in ("stage",))
        for f in sorted(fn):
            if f.endswith((".obj", ".res")):
                p = os.path.join(dp, f)
                out[norm(os.path.relpath(p, build).replace(os.sep, "/"))] = C.sha_f(p)
    return out


def identity_of(build):
    t = open(os.path.join(build, "src", "game", "build_id", "bo3_build_id.h"), encoding="utf-8").read()
    return re.search(r'BO3_BUILD_COMMIT "([^"]+)"', t).group(1)


EXE_OF = {"dev": "burnout3.exe", "release": "BurnoutMashup.exe"}
SECTION_OF = {"dev": "build", "release": "build_release"}


def profile_of(build, argv=()):
    """the profile named by --profile, else the one the build folder holds (release only when bin/BurnoutMashup.exe alone is there)"""
    p = C.arg_value(list(argv), "--profile")
    if p:
        if p not in EXE_OF:
            raise SystemExit("usage: --profile dev or release")
        return p
    b = os.path.join(build, "bin")
    return "release" if os.path.isfile(os.path.join(b, EXE_OF["release"])) and not os.path.isfile(os.path.join(b, EXE_OF["dev"])) else "dev"


def run(argv):
    build = os.path.abspath(C.arg_value(argv, "--build-dir", required=True))
    profile = profile_of(build, argv)
    allexp = C.load_expected(C.arg_value(argv, "--expected"))
    if SECTION_OF[profile] not in allexp:
        raise SystemExit("usage: EXPECTED.json has no %s section (no reference for the %s profile)" % (SECTION_OF[profile], profile))
    exp = allexp[SECTION_OF[profile]]
    exe = os.path.join(build, "bin", EXE_OF[profile])
    if not os.path.isfile(exe):
        raise SystemExit("usage: no %s" % exe)
    O = objects(build)
    gen_want = exp["generated_objects"]
    gen_have = {k: v for k, v in O.items() if "/recomp/gen/" in k}
    gen_diff = sorted(k for k in gen_want if gen_have.get(k) != gen_want[k])
    gen_extra = sorted(set(gen_have) - set(gen_want))
    exe_sha = C.sha_f(exe)
    ident = identity_of(build)
    res = {"generated_objects": "%d/%d identical" % (len(gen_want) - len(gen_diff), len(gen_want)),
           "generated_ok": not gen_diff and not gen_extra,
           "exe_sha256": exe_sha, "exe_expected": exp["exe_sha256"], "exe_ok": exe_sha == exp["exe_sha256"],
           "identity": ident, "identity_expected": exp["identity"]}
    if profile != "dev":                      # the development verdict keeps its exact fields (recorded proofs compare it)
        res["profile"] = profile
        res["exe_name"] = EXE_OF[profile]
    res["ok"] = res["generated_ok"] and res["exe_ok"]
    if not res["ok"]:
        why = {"generated_objects_differ": gen_diff, "generated_objects_unexpected": gen_extra}
        if ident != exp["identity"]:
            why["identity"] = "the build identity differs: some input file is not the reference one (line ends, upstream revision, " \
                              "layer or marks changed, other force-include list)"
        other_want = exp.get("objects", {})
        why["other_objects_differ"] = sorted(k for k in other_want if k not in gen_want and O.get(k) != other_want[k])[:40]
        lg = os.path.join(os.path.dirname(build.rstrip("\\/")), os.path.basename(build.rstrip("\\/")) + ".logs", "build_result.json")
        if os.path.isfile(lg):
            with open(lg, encoding="utf-8-sig") as f:          # written by PowerShell 5.1 (UTF-8 with BOM)
                tc = json.load(f).get("toolchain", {})
            why["toolchain_differs"] = {k: [tc.get(k), v] for k, v in C.load_expected(C.arg_value(argv, "--expected"))["toolchain"].items() if tc.get(k) != v}
        res["why"] = why
    if C.arg_value(argv, "--log"):
        C.jdump(res, C.arg_value(argv, "--log"))
    C.say("verify: generated objects %s; exe %s" % (res["generated_objects"], "IDENTICAL to the reference" if res["exe_ok"] else "DIFFERENT"))
    return res


def main():
    try:
        res = run(sys.argv[1:])
    except SystemExit:
        raise
    rc = 0 if res["ok"] else 1
    hi = C.arg_value(sys.argv[1:], "--host-info")
    if hi and res["ok"]:                       # step 7 in one go: HOST_INFO.json only for a verified build (host_info.py's refusals apply)
        import host_info as H
        try:
            info, dest = H.make(C.arg_value(sys.argv[1:], "--build-dir", required=True), C.arg_value(sys.argv[1:], "--takedawn"),
                                C.arg_value(sys.argv[1:], "--xboxrecomp"), C.arg_value(sys.argv[1:], "--log-dir"),
                                C.arg_value(sys.argv[1:], "--expected"), C.arg_value(sys.argv[1:], "--checkout"), hi, verify_result=res)
            res["host_info"] = dest
            C.say("verify: HOST_INFO.json written: %s (identity %s)" % (dest, info["identity"]))
        except C.Refused as e:
            res["host_info_refused"] = str(e)
            C.say("verify: HOST_INFO.json REFUSED: %s" % e)
            rc = 2
    elif hi:
        res["host_info_refused"] = "the build is not verified"
        rc = 1
    print(json.dumps(res, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main())
