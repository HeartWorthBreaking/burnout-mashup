"""host_info.py - write HOST_INFO.json for a host that was BUILT here, from that build only (step 7; the launcher and Workbench read it).

    py -3 -B host_info.py --build-dir BUILD_FOLDER [--takedawn TREE] [--xboxrecomp XR] [--log-dir LOGDIR] [--expected EXPECTED.json]
                          [--checkout ROOT] [--out FILE]
    py -3 -B host_info.py --check HOST_INFO.json --exe HOST_EXE        (re-check an existing file against its exe; reads only)
    py -3 -B verify.py --build-dir BUILD_FOLDER --host-info FILE         (verify the build, then write the file when it is OK)

The file describes the exe it sits beside: its sha256 and size, the build identity (bmp-<platform>+<12 hex>) READ FROM THE EXE'S
BYTES (the host is never started, not even with --version), and what that host offers: the platform version, the services and the
mod.toml tables with the newest version each reader takes, and the plugin api, all read from the host source tree that was built
(src/game/bm_platform_table.h, include/takedawn_plugin.h: the same tables the bmpack readers copy). The schema is format 1 of the
release's make_host_info.py (platform, plugin_api, services, tables, exe_sha256, host_name, identity: what bmcompat.py reads), plus
additive provenance fields. Every field names its source in "sources"; nothing is typed in, and no field is written without one.

REFUSED (exit 2, no file written) when: the exe or the build's files are missing; verify.py's checks fail (the 27 generated-code objects
and the exe are not the reference's); the identity inside the exe is absent, ambiguous or differs from the build's own record
(bo3_build_id.h) or from build_result.json; the digest of the source tree that is on disk now (recomputed here exactly as
cmake/bo3_source_id.cmake does) differs from the manifest the build recorded or from the identity in the exe (a tree changed after the
build); the platform table cannot be read; the regen stamp / marks pins differ from host/PINS.json. A build made with another
toolchain is refused too (verify.py), so a HOST_INFO.json exists only for a verified, reproducible build.
Standard library only (Python 3.8+). Original code (MIT)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmb_common as C  # noqa: E402

FORMAT = 1
GENERATOR = "build/host_info.py 1"
IDENT_RE = re.compile(rb"bmp-[0-9]+\.[0-9]+\.[0-9]+\+[0-9a-f]{12}")
# bo3_source_id.cmake: what the game digest and the toolkit digest are taken over
BMP_ENTRIES = ("CMakeLists.txt", "VERSION", "cmake/", "config/", "graphics/", "include/", "src/game/", "assets/glyphs/",
               "tools/glyphs/build.py", "tools/install/supported.json", "tools/release/windows/")
XR_ENTRIES = ("CMakeLists.txt", "cmake/", "include/", "src/", "templates/", "third_party/")
_SKIP_DIR = re.compile(r"(^|/)(\.git|__pycache__)(/|$)")
_SKIP_EXT = re.compile(r"\.(pyc|o|obj|exe|dll|a|lib)$")


def cache_value(build, key):
    """a value of <build>/CMakeCache.txt (KEY:TYPE=value), or None"""
    p = os.path.join(build, "CMakeCache.txt")
    if not os.path.isfile(p):
        return None
    for line in open(p, encoding="utf-8", errors="replace"):
        m = re.match(r"^%s:[A-Z]+=(.*)$" % re.escape(key), line.rstrip("\r\n"))
        if m:
            return m.group(1)
    return None


def exe_identities(exe):
    """the distinct build identities inside the exe (the string occurs in several places: all must agree)"""
    with open(exe, "rb") as f:
        data = f.read()
    return sorted({m.decode("ascii") for m in IDENT_RE.findall(data)})


def parse_table(text):
    """bm_platform_table.h -> (platform version, {service: version}, {table: {version, keys}})  (as the release's make_host_info.py)"""
    m = re.search(r'#define\s+BO3_PLATFORM_VERSION\s+"([0-9]+\.[0-9]+\.[0-9]+)"', text)
    if not m:
        raise C.Refused("BO3_PLATFORM_VERSION not found in bm_platform_table.h")
    services, tables = {}, {}
    for name, ver in re.findall(r'X\("([a-z0-9_.]+)",\s*([0-9]+),', text):
        services[name] = int(ver)
    for name, ver, keys in re.findall(r'T\("([a-z0-9_]+)",\s*([0-9]+),\s*"([^"]*)"\)', text):
        tables[name] = {"version": int(ver), "keys": keys.split()}
    if not services or not tables:
        raise C.Refused("no service / table rows found in bm_platform_table.h")
    return m.group(1), services, tables


def source_lines(base, tag, entries):
    """the 'sha256  tag/path' lines of cmake/bo3_source_id.cmake _bo3_lines(): an entry ending in '/' is a folder (every file under it),
    else one file; .git / __pycache__ and *.pyc|o|obj|exe|dll|a|lib and a root file BUILD_COMMIT are left out; sorted by path bytes"""
    found = set()
    for e in entries:
        if e.endswith("/"):
            root = os.path.join(base, e.rstrip("/").replace("/", os.sep))
            for dp, dn, fn in os.walk(root):
                for f in fn:
                    found.add(os.path.relpath(os.path.join(dp, f), base).replace(os.sep, "/"))
        elif os.path.exists(os.path.join(base, e.replace("/", os.sep))):
            found.add(e)
    keep = sorted((f for f in found if not _SKIP_DIR.search(f) and not _SKIP_EXT.search(f) and f != "BUILD_COMMIT"),
                  key=lambda f: f.encode("utf-8"))
    return "".join("%s  %s/%s\n" % (C.sha_f(os.path.join(base, f.replace("/", os.sep))), tag, f) for f in keep), len(keep)


def tree_digests(td, xr, platform, config_text):
    """-> (bmp manifest text, bmp digest, toolkit digest, file counts): the same text and digests the build's cmake step made"""
    xr_lines, n_xr = source_lines(xr, "toolkit", XR_ENTRIES)
    xr_digest = C.sha_b(("xboxrecomp source manifest v1\n" + xr_lines).encode("utf-8"))
    bmp_lines, n_bmp = source_lines(td, "bmp", BMP_ENTRIES)
    text = "bmp build manifest v1\nplatform %s\n%stoolkit %s\n%s" % (platform, bmp_lines, xr_digest, config_text.replace("\r", ""))
    return text, C.sha_b(text.encode("utf-8")), xr_digest, {"bmp_files": n_bmp, "toolkit_files": n_xr}


def _jload(p):
    """build_result.json is written by PowerShell 5.1 (UTF-8 with BOM)"""
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise C.Refused("%s is unreadable: %s" % (p, e))


def _read(p):
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def make(build, td=None, xr=None, log_dir=None, expected=None, checkout=None, out=None, verify_result=None):
    """-> (info dict, written path). Raises bmb_common.Refused (nothing written) for every refusal in the module docstring."""
    build = os.path.abspath(build)
    import verify as V
    profile = (verify_result or {}).get("profile") or V.profile_of(build)
    exe = os.path.join(build, "bin", V.EXE_OF[profile])
    if not os.path.isfile(exe):
        raise C.Refused("the built exe is missing: %s (build first: build.ps1)" % exe)
    bid = os.path.join(build, "src", "game", "build_id")
    for n in ("bo3_build_id.h", "bo3_build_manifest.txt", "bo3_build_config.txt"):
        if not os.path.isfile(os.path.join(bid, n)):
            raise C.Refused("the build's own identity record is missing: %s" % os.path.join(bid, n))
    td = os.path.abspath(td or cache_value(build, "CMAKE_HOME_DIRECTORY") or "")
    xr = os.path.abspath(xr or cache_value(build, "XBOXRECOMP_DIR") or "")
    if not os.path.isdir(os.path.join(td, "src", "game")):
        raise C.Refused("the host source tree that was built is not there: %s" % td)
    if not os.path.isdir(os.path.join(xr, "src")):
        raise C.Refused("the toolkit source tree that was built is not there: %s" % xr)
    ck = os.path.abspath(checkout or C.ROOT)
    exp_path = expected or os.path.join(C.HERE, "EXPECTED.json")
    log_dir = log_dir or (build.rstrip("\\/") + ".logs")
    br = os.path.join(log_dir, "build_result.json")
    if not os.path.isfile(br):
        raise C.Refused("no build_result.json (written by build.ps1) in %s: the toolchain of this build is not recorded" % log_dir)

    # 1. verified: the generated-code objects and the exe are the reference's (verify.py)
    if verify_result is None:
        verify_result = V.run(["--build-dir", build, "--expected", exp_path, "--profile", profile])
    if not verify_result.get("ok"):
        raise C.Refused("the build is not verified (verify.py: generated objects %s, exe %s): no HOST_INFO.json for it" % (
            verify_result.get("generated_objects"), "identical" if verify_result.get("exe_ok") else "different"))

    # 2. the exe's own identity (read from its bytes) against the build's records
    exe_sha, exe_size = C.sha_f(exe), os.path.getsize(exe)
    ids = exe_identities(exe)
    if len(ids) != 1:
        raise C.Refused("the exe holds %d different build identity strings (%s): expected exactly one" % (len(ids), ", ".join(ids) or "none"))
    ident = ids[0]
    m = re.search(r'BO3_BUILD_COMMIT "([^"]+)"', _read(os.path.join(bid, "bo3_build_id.h")))
    if not m or m.group(1) != ident:
        raise C.Refused("identity in the exe (%s) differs from the build's bo3_build_id.h (%s)" % (ident, m and m.group(1)))
    brj = _jload(br)
    if brj.get("identity") != ident or brj.get("exe_sha256") != exe_sha:
        raise C.Refused("build_result.json does not describe this exe (identity %s / sha256 %s)" % (brj.get("identity"), str(brj.get("exe_sha256"))[:12]))
    manifest_disk = _read(os.path.join(bid, "bo3_build_manifest.txt"))
    if C.sha_b(manifest_disk.encode("utf-8"))[:12] != ident.split("+", 1)[1]:
        raise C.Refused("the build's manifest digest does not give the identity in the exe %s" % ident)

    # 3. the host source tree on disk now is the one the identity was taken over
    table = os.path.join(td, "src", "game", "bm_platform_table.h")
    if not os.path.isfile(table):
        raise C.Refused("host source tree has no src/game/bm_platform_table.h: %s" % td)
    platform, services, tables = parse_table(_read(table))
    if ident.split("-", 1)[1].split("+", 1)[0] != platform:
        raise C.Refused("platform version of the source tree (%s) differs from the identity in the exe (%s)" % (platform, ident))
    text, digest, xr_digest, counts = tree_digests(td, xr, platform, _read(os.path.join(bid, "bo3_build_config.txt")))
    if text != manifest_disk:
        a, b = text.splitlines(), manifest_disk.splitlines()
        first = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
        raise C.Refused("the source tree on disk is not the one that was built (manifest line %d differs: %s): it changed after the build or is "
                        "another tree" % (first + 1, (a[first] if first < len(a) else "(end)")[:100]))
    if digest[:12] != ident.split("+", 1)[1]:
        raise C.Refused("source digest %s does not match the identity in the exe %s" % (digest[:12], ident))

    # 4. plugin api, pins of the inputs (read from files that exist in the tree / the checkout)
    ph = os.path.join(td, "include", "takedawn_plugin.h")
    pm = re.search(r"#define\s+TD_PLUGIN_API_VERSION\s+([0-9]+)u?\b", _read(ph)) if os.path.isfile(ph) else None
    if not pm:
        raise C.Refused("TD_PLUGIN_API_VERSION not found in include/takedawn_plugin.h of the host tree")
    pins = C.load_pins(os.path.join(ck, "host", "PINS.json"))
    stamp = os.path.join(td, "src", "game", "recomp", "gen", "regen.stamp")
    st = dict(l.split(" ", 1) for l in _read(stamp).splitlines() if " " in l) if os.path.isfile(stamp) else {}
    if profile == "release":
        # apply_marks.py --release: "tree" = the marked tree (recomputed here from the files on disk), "pristine" = the pinned tree
        if st.get("pristine", "").strip() != pins["pristine_gen_tree_hash"]:
            raise C.Refused("pristine tree hash in the release regen.stamp (%s) is not the pinned one (%s)" % (st.get("pristine", "?")[:12], pins["pristine_gen_tree_hash"][:12]))
        if st.get("tree", "").strip() != C.gen_tree_hash(os.path.dirname(stamp)):
            raise C.Refused("the release regen.stamp does not describe the generated files on disk (marked tree changed after the build)")
    elif st.get("tree", "").strip() != pins["pristine_gen_tree_hash"]:
        raise C.Refused("generated-code tree hash in regen.stamp (%s) is not the pinned one (%s)" % (st.get("tree", "?")[:12], pins["pristine_gen_tree_hash"][:12]))
    anchors = os.path.join(ck, "host", "marks", "anchors.json")
    hdr = os.path.join(td, "src", "game", "bm_gen_access.h")
    a_sha = C.sha_f(anchors) if os.path.isfile(anchors) else None
    h_sha = C.sha_f(hdr) if os.path.isfile(hdr) else None
    if a_sha != pins["marks"]["anchors_sha256"] or h_sha != pins["marks"]["header_sha256"]:
        raise C.Refused("anchors.json / bm_gen_access.h are not the pinned ones (host/PINS.json)")
    bres = C.jload(exp_path)
    section = V.SECTION_OF[profile]
    stage_exe = os.path.join(build, "stage", "BurnoutMashup.exe")
    staged = os.path.isfile(stage_exe) and C.sha_f(stage_exe) == exe_sha
    exe_file = "burnout3.exe" + (" (staged copy: stage/BurnoutMashup.exe)" if staged else "")
    if profile == "release":
        exe_file = "BurnoutMashup.exe" + (" (staged copy: stage/BurnoutMashup.exe)" if staged else "")

    info = {
        "format": FORMAT, "host_name": ident, "identity": ident, "platform": platform, "plugin_api": int(pm.group(1)),
        "services": dict(sorted(services.items())), "tables": dict(sorted(tables.items())),
        "exe_sha256": exe_sha, "exe_size": exe_size, "exe_file": exe_file,
        "source_digest_sha256": digest, "toolkit_identity": "xr+" + xr_digest[:12], "toolkit_digest_sha256": xr_digest,
        "source_files": counts,
        "inputs": {"takedawn_commit": pins["takedawn"]["commit"], "takedawn_tree_id": pins["takedawn"]["tree_id"],
                   "xboxrecomp_commit": pins["xboxrecomp"]["commit"], "xboxrecomp_tree_id": pins["xboxrecomp"]["tree_id"],
                   "gen_tree_hash": st["tree"].strip(), "anchors_json_sha256": a_sha, "bm_gen_access_h_sha256": h_sha,
                   "marks": pins["marks"]["count"]},
        "toolchain": brj.get("toolchain", {}),
        "verification": {"expected_json_sha256": C.sha_f(exp_path), "generated_objects": verify_result.get("generated_objects"),
                         "exe": "identical to the reference in EXPECTED.json", "expected_exe_sha256": bres[section]["exe_sha256"]},
        "generator": GENERATOR,
        "sources": {
            "format": "schema of the release's kit_tools/make_host_info.py (format 1); additive fields are ignored by bmcompat.py",
            "exe_sha256": "sha256 of <build>/bin/burnout3.exe (verify.py: identical to EXPECTED.json build.exe_sha256)",
            "exe_size": "size of the same file",
            "exe_file": "the build output name; stage/BurnoutMashup.exe compared byte for byte when present",
            "identity": "the string bmp-<platform>+<12 hex> read from the exe's bytes; equals bo3_build_id.h, build_result.json and the "
                        "recomputed digest of the source tree",
            "host_name": "= identity (a build has no other name)",
            "platform": "BO3_PLATFORM_VERSION in <host tree>/src/game/bm_platform_table.h (also the platform part of the identity)",
            "services": "X(name, version, ...) rows of <host tree>/src/game/bm_platform_table.h",
            "tables": "T(name, version, keys) rows of the same file",
            "plugin_api": "TD_PLUGIN_API_VERSION in <host tree>/include/takedawn_plugin.h",
            "source_digest_sha256": "recomputed from the files of the host tree on disk (cmake/bo3_source_id.cmake's rule) + the build's "
                                    "bo3_build_config.txt; equals the digest of the build's bo3_build_manifest.txt",
            "toolkit_identity": "digest of the toolkit tree files (same rule); equals the 'toolkit' line of the build manifest",
            "toolkit_digest_sha256": "the same digest, in full",
            "source_files": "number of files the two digests were taken over (counted while recomputing them)",
            "inputs.takedawn_*, inputs.xboxrecomp_*": "host/PINS.json (checked by fetch_upstream.py against the fetched archives; not re-derived here)",
            "inputs.gen_tree_hash": "<host tree>/src/game/recomp/gen/regen.stamp, equal to host/PINS.json pristine_gen_tree_hash",
            "inputs.anchors_json_sha256": "sha256 of host/marks/anchors.json of the checkout, equal to host/PINS.json marks.anchors_sha256",
            "inputs.bm_gen_access_h_sha256": "sha256 of <host tree>/src/game/bm_gen_access.h, equal to host/PINS.json marks.header_sha256",
            "toolchain": "<build>.logs/build_result.json (tool versions queried by build.ps1; checked against EXPECTED.json by verify.py)",
            "verification": "verify.py run on this build with EXPECTED.json",
        },
    }
    if profile == "release":                   # additive fields (bmcompat.py ignores them); the development file keeps its exact bytes
        info["profile"] = "release"
        info["inputs"]["gen_tree_hash"] = st["pristine"].strip()
        info["inputs"]["marked_gen_tree_hash"] = st["tree"].strip()
        info["verification"]["expected_section"] = section
        info["sources"]["exe_sha256"] = "sha256 of <build>/bin/BurnoutMashup.exe (verify.py --profile release: identical to EXPECTED.json build_release.exe_sha256)"
        info["sources"]["inputs.gen_tree_hash"] = ("the 'pristine' line of <host tree>/src/game/recomp/gen/regen.stamp (apply_marks.py --release), equal to "
                                                   "host/PINS.json pristine_gen_tree_hash")
        info["sources"]["inputs.marked_gen_tree_hash"] = "the 'tree' line of the same stamp, recomputed from the generated files on disk"
        info["sources"]["profile"] = "build.ps1 -Release (BO3_RELEASE=ON, BMASHUP_IDENTITY=ON): the release-named executable"
    dest = os.path.abspath(out or os.path.join(build, "stage", "HOST_INFO.json"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, dest)
    return info, dest


def check(path, exe):
    """re-check an existing HOST_INFO.json against the exe it describes -> list of problems ([] = fine). Reads only."""
    bad = []
    try:
        info = C.jload(path)
    except (OSError, ValueError) as e:
        return ["HOST_INFO.json unreadable: %s" % e]
    for k in ("platform", "services", "tables", "exe_sha256", "identity"):
        if k not in info:
            bad.append("HOST_INFO.json has no '%s'" % k)
    if not os.path.isfile(exe):
        return bad + ["the exe is missing: %s" % exe]
    if info.get("exe_sha256") != C.sha_f(exe):
        bad.append("the exe is not the one HOST_INFO.json describes (sha256 differs)")
    try:
        ids = exe_identities(exe)
    except OSError as e:
        return bad + ["the exe cannot be read: %s" % e]
    if ids != [info.get("identity")]:
        bad.append("the identity inside the exe (%s) is not HOST_INFO.json's (%s)" % (", ".join(ids) or "none", info.get("identity")))
    return bad


def run(argv):
    if "--check" in argv:
        bad = check(C.arg_value(argv, "--check", required=True), C.arg_value(argv, "--exe", required=True))
        C.say("host_info check: %s" % ("OK" if not bad else "; ".join(bad)))
        return {"ok": not bad, "problems": bad}
    build = C.arg_value(argv, "--build-dir", required=True)
    info, dest = make(build, C.arg_value(argv, "--takedawn"), C.arg_value(argv, "--xboxrecomp"), C.arg_value(argv, "--log-dir"),
                      C.arg_value(argv, "--expected"), C.arg_value(argv, "--checkout"), C.arg_value(argv, "--out"))
    C.say("host_info: %s platform %s, %d services, %d tables, identity %s" % (dest, info["platform"], len(info["services"]),
                                                                              len(info["tables"]), info["identity"]))
    return {"ok": True, "host_info": dest, "identity": info["identity"], "exe_sha256": info["exe_sha256"], "platform": info["platform"],
            "services": len(info["services"]), "tables": len(info["tables"])}


def main():
    try:
        res = run(sys.argv[1:])
    except C.Refused as e:
        print(json.dumps({"refused": True, "reason": str(e)}))
        C.say("REFUSED: %s" % e)
        return 2
    print(json.dumps(res, sort_keys=True))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
