"""trackbuild 0.3.0 - actionable-error tests (end to end through tb.py / tb.cmd: exit code AND message).

    py -3 -B tests\\test_errors.py RUN_DIR [--game-data DIR]

RUN_DIR must not exist. Without game data every test runs that does not need it (fake game-data folders are made in
RUN_DIR); the two tests that need YOUR game data (a real build mutated so that a gate fails; a donor mismatch on a real
folder layout) are SKIPPED with a message. Game data: --game-data DIR, else TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA.
Every check: the command must exit with the documented code and stderr must contain the phrase that tells the user what
to do. Results: RUN_DIR/RESULTS_errors.txt (no times)."""
import json
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
TB = os.path.join(PKG, "tb.py")
sys.path.insert(0, PKG)
from trackbuild import accessguard  # noqa: E402
from trackbuild import VERSION  # noqa: E402   (0.3.0: E1 checks the package's own version, not a fixed string)
accessguard.install_from_env()                         # opt-in isolation monitor (TRACKBUILD_ACCESS_LOG); no-op otherwise
RES = []
SKIP = []


def check(name, ok, detail=""):
    RES.append((name, bool(ok)))
    print("%-4s %-70s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:200].replace("\n", " | ")))


def skip(name, why):
    SKIP.append((name, why))
    print("SKIP %-70s %s" % (name, why))


def clean_env(extra=None):
    """the caller's environment without any trackbuild / kit game-data setting (the access monitor is passed through)"""
    env = {k: v for k, v in os.environ.items() if k not in ("TRACKBUILD_GAME_DATA", "BMKIT_GAME_DATA")}
    env.update(extra or {})
    return env


def tb(args, env=None, script=TB):
    r = subprocess.run([sys.executable, "-B", script] + list(args), capture_output=True, text=True, env=env or clean_env())
    return r.returncode, r.stdout, r.stderr


def expect(name, args, code, phrases, env=None, script=TB):
    rc, out, err = tb(args, env, script)
    miss = [p for p in phrases if p.lower() not in err.lower()]
    check(name, rc == code and not miss, "rc %s (want %d)%s; %s" % (rc, code, " missing %s" % miss if miss else "", err.strip()[-160:]))
    return rc, out, err


def fake_game_data(root, files=None, xbe=None):
    """a folder with Tracks/EU/M1_V1 holding `files` {name: bytes} (wrong bytes = mismatch tests)"""
    t = os.path.join(root, "Tracks", "EU", "M1_V1")
    os.makedirs(t)
    for n, b in (files or {}).items():
        open(os.path.join(t, n), "wb").write(b)
    if xbe is not None:
        open(os.path.join(root, "default.xbe"), "wb").write(xbe)
    return root


def mut_src(src, d, edit_obj=None, edit_desc=None, edit_files=None):
    shutil.copytree(src, d)
    if edit_obj:
        p = os.path.join(d, "test_loop.obj")
        t = open(p).read()
        open(p, "w", newline="\n").write(edit_obj(t))
    if edit_desc:
        p = os.path.join(d, "test_loop.track.json")
        j = json.load(open(p))
        edit_desc(j)
        json.dump(j, open(p, "w"))
    if edit_files:
        edit_files(d)
    return d


def first_face_to(text, new):
    i = text.index("\nf ")
    j = text.index("\n", i + 1)
    return text[:i + 1] + new + text[j:]


def resolve_game_data(argv):
    if "--game-data" in argv:
        return argv[argv.index("--game-data") + 1]
    return os.environ.get("TRACKBUILD_GAME_DATA") or os.environ.get("BMKIT_GAME_DATA")


def main(argv):
    run = argv[0]
    if os.path.exists(run):
        sys.exit("refusing: %s exists" % run)
    os.makedirs(run)
    gdata = resolve_game_data(argv)
    J = lambda *p: os.path.join(run, *p)  # noqa: E731
    from trackbuild import donor
    import tb as TBM

    # ---------------------------------------------------------------- E1 missing / old Python
    m = TBM.python_problem((3, 10))
    check("E1 Python 3.10 refused with the install hint", m and "3.11" in m and "python.org" in m, m)
    check("E1 Python 3.11 accepted", TBM.python_problem((3, 11)) is None)
    if os.name == "nt":
        sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        r = subprocess.run(["cmd", "/c", os.path.join(PKG, "tb.cmd"), "version"], capture_output=True, text=True,
                           env={"PATH": sysdir, "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows")})
        check("E1 tb.cmd without any Python on PATH -> rc 3 + install hint", r.returncode == 3 and "no Python found" in r.stderr,
              "rc %d %s" % (r.returncode, r.stderr.strip()[:120]))
        r = subprocess.run(["cmd", "/c", os.path.join(PKG, "tb.cmd"), "version"], capture_output=True, text=True, env=clean_env())
        check("E1 tb.cmd with Python -> runs tb.py (rc 0, version %s)" % VERSION, r.returncode == 0 and '"%s"' % VERSION in r.stdout, r.stdout.strip()[:80])
    else:
        skip("E1 tb.cmd", "Windows only")

    # ---------------------------------------------------------------- E2 missing dependency (package files)
    broken = J("pkg_missing_vendor")
    shutil.copytree(PKG, broken, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    os.remove(os.path.join(broken, "trackbuild", "_vendor", "xbtopo.py"))
    expect("E2 vendored module missing -> rc 3 'incomplete ... unpack'", ["version"], 3, ["incomplete", "unpack the whole"],
           script=os.path.join(broken, "tb.py"))
    changed = J("pkg_changed_vendor")
    shutil.copytree(PKG, changed, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    with open(os.path.join(changed, "trackbuild", "_vendor", "ct2_s4.py"), "a") as f:
        f.write("\n# local edit\n")
    expect("E2 selfcheck: changed vendored file -> rc 3 names the file", ["selfcheck"], 3, ["changed _vendor/ct2_s4.py"],
           script=os.path.join(changed, "tb.py"))
    expect("E2 selfcheck on the intact package -> rc 0", ["selfcheck"], 0, [])

    # ---------------------------------------------------------------- sources for the input tests (pure, no game data)
    src = J("src")
    rc, out, err = tb(["gen-testloop", src])
    check("gen-testloop (ORIGINAL demo source, no game data)", rc == 0, err[-200:])
    fake = fake_game_data(J("fake_gd_empty"))                      # resolves; donor files absent

    # ---------------------------------------------------------------- E3 invalid paths
    expect("E3 build: source folder missing -> rc 2", ["build", J("nope"), "x.json", J("o1"), "--game-data", fake], 2, ["does not exist"])
    expect("E3 build: description missing -> rc 2", ["build", src, "missing.track.json", J("o2"), "--game-data", fake], 2, ["track description"])
    os.makedirs(J("o3"))
    open(J("o3", "keep.txt"), "w").write("x")
    expect("E3 build: output folder not empty -> rc 2 'never overwrites'", ["build", src, "test_loop.track.json", J("o3"), "--game-data", fake],
           2, ["never overwrites"])
    expect("E3 build: output parent missing -> rc 2", ["build", src, "test_loop.track.json", J("no", "such", "o4"), "--game-data", fake],
           2, ["parent folder"])
    expect("E3 gen-testloop into a non-empty folder -> rc 2", ["gen-testloop", src], 2, ["not empty"])
    expect("E3 validate a folder that is no build -> rc 2", ["validate", src], 2, ["not a complete trackbuild build folder"])
    expect("E3 unknown command / bad option -> rc 2 + help hint", ["bild", src], 2, ["--help"])

    # ---------------------------------------------------------------- E4 unsupported OBJ features
    obj_cases = [("E4 OBJ pentagon (n-gon)", lambda t: first_face_to(t, "f 1/1/1 2/2/1 3/3/1 4/4/1 5/5/1"), "only triangles and quads"),
                 ("E4 OBJ face without uv / normal", lambda t: first_face_to(t, "f 1//1 2//1 3//1"), "uv and normal required"),
                 ("E4 OBJ line element (l)", lambda t: t.replace("mtllib test_loop.mtl", "l 1 2"), "unsupported OBJ statement"),
                 ("E4 OBJ negative (relative) index", lambda t: first_face_to(t, "f -1/-1/-1 -2/-2/-2 -3/-3/-3"), "negative / zero indices"),
                 ("E4 OBJ curve / free-form (curv)", lambda t: t.replace("mtllib test_loop.mtl", "curv 0 1 1 2"), "unsupported OBJ statement"),
                 ("E4 OBJ zero-area face", lambda t: first_face_to(t, "f 1/1/1 1/1/1 1/1/1"), "zero-area"),
                 ("E4 OBJ material without a description", lambda t: t.replace("usemtl grass", "usemtl lava", 1), "has no row")]
    for k, (name, fn, phrase) in enumerate(obj_cases):
        d = mut_src(src, J("neg_obj%d" % k), edit_obj=fn)
        expect(name + " -> rc 4", ["build", d, "test_loop.track.json", J("out_obj%d" % k), "--game-data", fake], 4, [phrase, "REFUSED"])

    # ---------------------------------------------------------------- E5 unsupported materials / textures / sizes
    from trackbuild import dxt

    def alpha_tex(d):
        rows = [[(0, 128, 0)] * 128 for _ in range(128)]
        write_rgba(os.path.join(d, "textures", "bm_grass.png"), 128, 128, rows, 100)

    def npot(d):
        dxt.write_png(os.path.join(d, "textures", "bm_grass.png"), 96, 96, [[(0, 128, 0)] * 96 for _ in range(96)])

    def big(d):
        dxt.write_png(os.path.join(d, "textures", "bm_grass.png"), 2048, 4, [[(0, 128, 0)] * 2048 for _ in range(4)])

    def gray(d):
        write_gray(os.path.join(d, "textures", "bm_grass.png"), 4, 4)

    def more_units(j):
        n = len(j["stations"])
        j["units"] = [{"cut_from": k * 21 % n, "cut_to": (k + 1) * 21 % n, "lateral": j["units"][0]["lateral"],
                       "chord_normal": j["units"][0]["chord_normal"]} for k in range(17)] + [j["units"][0]]

    def lanes_mismatch(j):
        j["route"]["lanes"] = j["route"]["lanes"][:4]

    def too_many_rows(j):
        for k in range(84):
            j["materials"]["m%d" % k] = dict(j["materials"]["grass"])
        j["rows"] = j["rows"] + ["m%d" % k for k in range(84)]

    def not_closed(j):
        j["closed"] = False

    def drop_key(j):
        del j["grid"]
    mat_cases = [
        ("E5 material key 'alpha' (transparency)", dict(edit_desc=lambda j: j["materials"]["grass"].update(alpha=0.5)), ["alpha is not supported", "opaque"]),
        ("E5 material key 'shader' / 'animated'", dict(edit_desc=lambda j: j["materials"]["wall"].update(shader="water", animated=True)), ["animated, shader are not supported"]),
        ("E5 material surface not a hex word", dict(edit_desc=lambda j: j["materials"]["wall"].update(surface="tarmac")), ["not a hex word"]),
        ("E5 car-solid wall with flag 0x10", dict(edit_desc=lambda j: j["materials"]["wall"].update(surface="0x181C")), ["flag 0x10"]),
        ("E5 texture with transparent pixels", dict(edit_files=alpha_tex), ["transparent pixels"]),
        ("E5 texture not power of two (96x96)", dict(edit_files=npot), ["power of two"]),
        ("E5 texture too large (2048 wide)", dict(edit_files=big), ["power of two, 4..1024"]),
        ("E5 texture 8-bit grey (not RGB / RGBA)", dict(edit_files=gray), ["8-bit RGB / RGBA"]),
        ("E5 18 units with pvs all (size envelope)", dict(edit_desc=more_units), ["4..17 units"]),
        ("E5 84 material rows (block limit 83)", dict(edit_desc=too_many_rows), ["at most 83"]),
        ("E5 open (point-to-point) track", dict(edit_desc=not_closed), ["only closed"]),
        ("E5 description key missing", dict(edit_desc=drop_key), ["missing key grid"]),
        ("E5 route lanes / offsets mismatch", dict(edit_desc=lanes_mismatch), ["offsets for 4 lanes"]),
    ]
    for k, (name, kw, phrases) in enumerate(mat_cases):
        d = mut_src(src, J("neg_mat%d" % k), **kw)
        expect(name + " -> rc 4", ["build", d, "test_loop.track.json", J("out_mat%d" % k), "--game-data", fake], 4, phrases)
    bad_json = mut_src(src, J("neg_json"), edit_files=lambda d: open(os.path.join(d, "test_loop.track.json"), "w").write("{ not json"))
    expect("E5 description not JSON -> rc 4", ["build", bad_json, "test_loop.track.json", J("out_json"), "--game-data", fake], 4, ["not valid JSON"])

    # ---------------------------------------------------------------- E6 absent / wrong game data
    expect("E6 no game data given (no option, no variable) -> rc 3", ["build", src, "test_loop.track.json", J("g1")], 3,
           ["--game-data", "TRACKBUILD_GAME_DATA", "YOUR OWN"])
    expect("E6 game-data folder does not exist -> rc 3", ["check-game-data", "--game-data", J("missing_gd")], 3, ["does not exist"])
    os.makedirs(J("gd_parent", "Burnout 3 Takedown", "Tracks"))
    expect("E6 parent of the data folder given -> rc 3 + 'give that folder'", ["check-game-data", "--game-data", J("gd_parent")], 3,
           ["no Tracks folder", "give that folder instead"])
    expect("E6 the Tracks folder itself given -> rc 3 + 'PARENT'", ["check-game-data", "--game-data", J("gd_parent", "Burnout 3 Takedown", "Tracks")],
           3, ["PARENT folder"])
    expect("E6 donor track folder missing -> rc 3", ["check-game-data", "--game-data", J("gd_parent", "Burnout 3 Takedown")], 3,
           ["no track folder", "EU\\M1_V1"])
    expect("E6 donor files missing -> rc 3 names them", ["check-game-data", "--game-data", fake], 3, ["Gamedata.bgd is missing", "MUSIC.RWS is missing"])
    wrong = fake_game_data(J("fake_gd_wrong"), {n: b"not the retail bytes" for n in ("Gamedata.bgd",) + donor.DONOR_FILES})
    expect("E6 donor hash mismatch -> rc 3 names the file + expected hash", ["check-game-data", "--game-data", wrong], 3,
           ["Gamedata.bgd has sha256", donor.DONOR_PINS["EU/M1_V1"]["Gamedata.bgd"][0], "unmodified"])
    expect("E6 donor hash mismatch via BMKIT_GAME_DATA -> rc 3", ["check-game-data"], 3, ["the environment variable BMKIT_GAME_DATA"],
           env=clean_env({"BMKIT_GAME_DATA": wrong}))
    expect("E6 donor hash mismatch stops a build (after the source checks) -> rc 3",
           ["build", src, "test_loop.track.json", J("g2"), "--game-data", wrong], 3, ["is not the expected retail"])
    xbe = fake_game_data(J("fake_gd_xbe"), xbe=b"PAL or patched")
    expect("E6 non-NTSC-U default.xbe -> rc 3", ["check-game-data", "--game-data", xbe], 3, ["not the North America"])
    expect("E6 unpinned host refused without --unpinned-donor -> rc 3", ["check-game-data", "--game-data", fake, "--host", "US/C3_V1"], 3,
           ["no pinned donor hashes", "--unpinned-donor"])

    # ---------------------------------------------------------------- E7 validation gate failing / packaging preconditions
    fb = J("fake_build")
    os.makedirs(fb)
    from trackbuild._vendor.trackconv.package import FILES
    for f in FILES:
        open(os.path.join(fb, f), "wb").write(b"x")
    json.dump({"host": "EU/M1_V1"}, open(os.path.join(fb, "BUILD_REPORT.json"), "w"))
    toml = os.path.join(PKG, "examples", "test_loop_package.toml")
    expect("E7 package before validate -> rc 2 'run ... validate'", ["package", fb, toml, J("set0")], 2, ["has not been validated"])
    json.dump({"summary": {"ok": False, "failed": ["V2_walls_hold"], "gates": 16}}, open(os.path.join(fb, "VALIDATION.json"), "w"))
    expect("E7 package of a build with a FAILED gate -> rc 1 names the gate", ["package", fb, toml, J("set1")], 1, ["V2_walls_hold", "never packaged"])
    json.dump({"summary": {"ok": True, "failed": [], "gates": 16}, "trackbuild": {"build_sha256": {}}}, open(os.path.join(fb, "VALIDATION.json"), "w"))
    expect("E7 VALIDATION.json not matching the files -> rc 2 'validate again'", ["package", fb, toml, J("set2")], 2, ["validate", "again"])

    # ---------------------------------------------------------------- real build (needs YOUR game data)
    if not gdata:
        for n in ("E7 mutated build -> validate rc 1 names the failing gate", "E8 package decisions refused (track ID / TOML)",
                  "E9 --bmpack not a bmpack.py"):
            skip(n, "needs game data: give --game-data DIR (or TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA)")
    else:
        b1 = J("b1")
        rc, out, err = tb(["build", src, "test_loop.track.json", b1, "--game-data", gdata])
        check("real build with the given game data", rc == 0, err[-200:])
        rc, out, err = tb(["validate", b1])
        check("real build validates (rc 0)", rc == 0, out[-120:])
        mb = J("b1_mut")
        shutil.copytree(b1, mb)
        sm = bytearray(open(os.path.join(mb, "streamed.dat"), "rb").read())
        st = open(os.path.join(mb, "static.dat"), "rb").read()
        ut = struct.unpack_from("<I", st, 0x58)[0]
        n = struct.unpack_from("<h", st, 0x54)[0]
        for u in range(n):                                         # every wall quad becomes road (as T5 walls_become_road)
            mo, lo, ms, ls = struct.unpack_from("<4I", st, ut + 16 * u)
            tree = lo + struct.unpack_from("<I", sm, lo + 0xA0)[0]
            pl, nl = struct.unpack_from("<IH", sm, tree + 0x24)
            for i in range(nl):
                o = tree + pl + 16 * i
                pa, nq = struct.unpack_from("<I", sm, o)[0], sm[o + 14]
                for q in range(nq):
                    w = struct.unpack_from("<H", sm, o + pa + 14 * q + 4)[0]
                    if (w & 0xFF) >= 21:
                        struct.pack_into("<H", sm, o + pa + 14 * q + 4, 0x0001)
        open(os.path.join(mb, "streamed.dat"), "wb").write(bytes(sm))
        expect("E7 mutated build -> validate rc 1 names the failing gate", ["validate", mb], 1, ["V2_walls_hold", "must not be packaged"])
        expect("E7 ... and package refuses it -> rc 1", ["package", mb, toml, J("set3")], 1, ["never packaged"])
        bad_t = J("bad_id.toml")
        open(bad_t, "w").write(open(toml).read().replace('track_id = "EU_T1_V1"', 'track_id = "EU-T1-V1"'))
        expect("E8 package: track ID not RR_NN_VN -> rc 4", ["package", b1, bad_t, J("set4")], 4, ["not RR_NN_VN"])
        bad_s = J("bad_syntax.toml")
        open(bad_s, "w").write("[package\nset = 1\n")
        expect("E8 package: TOML syntax error -> rc 1", ["package", b1, bad_s, J("set5")], 1, ["not valid TOML"])
        expect("E9 package --bmpack that is not bmpack.py -> rc 1", ["package", b1, toml, J("set6"), "--bmpack", toml], 1, ["not a bmpack.py"])

    npass = sum(1 for _, ok in RES if ok)
    lines = ["%s %s" % ("PASS" if ok else "FAIL", n) for n, ok in RES] + ["SKIP %s (%s)" % s for s in SKIP] + \
            ["TOTAL %d / %d (skipped %d)" % (npass, len(RES), len(SKIP))]
    open(os.path.join(run, "RESULTS_errors.txt"), "w", newline="\n").write("\n".join(lines) + "\n")
    print("TOTAL %d / %d (skipped %d)" % (npass, len(RES), len(SKIP)))
    return 0 if npass == len(RES) else 1


def _png(path, w, h, ctype, raw_rows):
    import zlib

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in raw_rows)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def write_rgba(path, w, h, rows, alpha):
    _png(path, w, h, 6, [bytes(c for px in r for c in (px[0], px[1], px[2], alpha)) for r in rows])


def write_gray(path, w, h):
    _png(path, w, h, 0, [bytes(w) for _ in range(h)])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
