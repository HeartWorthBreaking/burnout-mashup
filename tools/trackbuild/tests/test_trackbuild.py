"""trackbuild 0.2.0 offline suite (port of the 0.1.6 suite; same checks, game data from an explicit folder).

    py -3 -B tests\\test_trackbuild.py RUN_DIR [--game-data DIR] [--converted TRACK_DIR]

RUN_DIR must not exist; RESULTS.txt has no times. Game data: --game-data DIR, else TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA.
Without it, the checks that need it are SKIPPED with a message (the importer negatives and source determinism still run).
T1 determinism        source generated twice identical; build twice identical (track files)                 [build: game data]
T2 validators         every independent gate PASSES on the build                                              [game data]
T3 retail controls    US/C3_V1 + EU/M1_V1 units: the collision builder rebuilt from the retail quads passes the bolib check
                      with the same quad multiset; the mesh writer rebuilt from the retail triangles decodes to the same
                      triangles and is accepted by xbtopo / strict rules; layout + tree validators accept the unchanged
                      retail US/C3_V1                                                                          [game data]
T4 converted control  OPTIONAL: --converted <a converted track folder with static.dat / streamed.dat> (0.1.6 used White
                      Mountain 1.0.2) accepted by the same layout / tree validators
T5 negatives          malformed sources refused by the importer (no game data); mutated builds rejected by the validators"""
import hashlib
import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TB = os.path.dirname(HERE)
sys.path.insert(0, TB)
from trackbuild import accessguard  # noqa: E402
accessguard.install_from_env()                         # opt-in isolation monitor (TRACKBUILD_ACCESS_LOG); no-op otherwise
from trackbuild import build as B, blocks as BK, testloop, validate as V, donor as DN  # noqa: E402
from trackbuild.io import SourceError  # noqa: E402

RES = []
SKIP = []
NEED = "needs game data: give --game-data DIR (or TRACKBUILD_GAME_DATA / BMKIT_GAME_DATA)"
WHY = {"pentagon face refused": "only triangles and quads", "face without uv refused": "uv and normal required",
       "unknown OBJ statement refused": "unsupported OBJ statement", "material without a description refused": "has no row",
       "zero-area face refused": "zero-area", "18 units refused (+-8 ring)": "4..17 units",
       "inverted lateral bounds refused (non-convex region)": "not convex", "non power-of-two texture refused": "power of two",
       "route lanes / offsets mismatch refused": "offsets for 4 lanes"}


def check(name, ok, detail=""):
    RES.append((name, bool(ok), detail))
    print("%-4s %-60s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:160]))


def skip(name, why=NEED):
    SKIP.append((name, why))
    print("SKIP %-60s %s" % (name, why))


def tree_hash(d):
    out = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(root, f)
            out[os.path.relpath(p, d).replace("\\", "/")] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def build_into(src, out, gdata, desc="test_loop.track.json"):
    os.makedirs(out)
    products, report, _ = B.build_track(src, desc, game_data=gdata)
    for k, v in products.items():
        open(os.path.join(out, k), "wb").write(v)
    report["source"] = {"dir": os.path.abspath(src), "desc": desc}
    json.dump(report, open(os.path.join(out, "BUILD_REPORT.json"), "w"), indent=1, sort_keys=True)
    return products


def t1_t2(run, gdata):
    s1, s2 = os.path.join(run, "src1"), os.path.join(run, "src2")
    os.makedirs(s1)
    os.makedirs(s2)
    testloop.build(s1)
    testloop.build(s2)
    h1, h2 = tree_hash(s1), tree_hash(s2)
    check("T1 source generated twice identical (%d files)" % len(h1), h1 == h2)
    if not gdata:
        skip("T1 build twice identical")
        skip("T2 independent validators")
        return s1, None
    p1 = build_into(s1, os.path.join(run, "b1"), gdata)
    p2 = build_into(s2, os.path.join(run, "b2"), gdata)
    check("T1 build twice identical (10 track files)", all(p1[k] == p2[k] for k in p1), {k: hashlib.sha256(v).hexdigest()[:12] for k, v in sorted(p1.items()) if k in ("static.dat", "streamed.dat", "Gamedata.bgd")})
    res = V.validate(os.path.join(run, "b1"), os.path.join(s1, "test_loop.track.json"))
    check("T2 independent validators %d gates" % (res["summary"]["gates"] - 1), res["summary"]["ok"], res["summary"]["failed"])
    return s1, os.path.join(run, "b1")


def retail_units(gdata, tid, n):
    f = DN.load_control(gdata, tid)
    st, sm = f["static.dat"], f["streamed.dat"]
    return st, sm, V._units(st)[:n]


def layout_tree(label, st, sm):
    U = V._units(st)
    nprop = struct.unpack_from("<h", st, 0x34)[0]
    ok_l = ok_t = 0
    for u, (mo, lo, ms, ls) in enumerate(U):
        mb, lb = sm[mo:mo + ms], sm[lo:lo + ls]
        ok_l += V.T.MeshModel(mb).serialize(ms) == mb and V.T.LodModel(lb, nprop).serialize(ls) == lb
        t = V.C.parse(lb, struct.unpack_from("<I", lb, 0xA0)[0], "b3")
        ok_t += not V.C.check(t)
    check("%s: layout + tree validators accept (%d units)" % (label, len(U)), ok_l == len(U) and ok_t == len(U), "%d / %d" % (ok_l, ok_t))


def t3_t4(gdata, converted):
    if not gdata:
        for tid in ("US/C3_V1", "EU/M1_V1"):
            skip("T3 %s collision builder / mesh writer on retail data" % tid)
        skip("T3 retail US/C3_V1 layout + tree validators")
    else:
        for tid in ("US/C3_V1", "EU/M1_V1"):
            st, sm, U = retail_units(gdata, tid, 6)
            cok = mok = 0
            for u, (mo, lo, ms, ls) in enumerate(U):
                bl = V.X.Block(sm, lo, ls, "lod", u)
                t = V.C.parse(bl.b, struct.unpack_from("<I", bl.b, 0xA0)[0], "b3")
                coll, ref = [], []
                for lf in t.leaves:
                    for q in lf.quads:
                        i = list(q[:4])
                        w = struct.unpack_from("<H", q, 4)[0]
                        pts = [lf.verts[k] for k in i if k != 0xFF]
                        if len(pts) == 4:                       # strip order (a b c d) -> polygon (a b d c)
                            pts = [pts[0], pts[1], pts[3], pts[2]]
                        coll.append((w, pts))
                        ref.append((w, tuple(sorted(tuple(round(c, 3) for c in p) for p in pts))))
                tb, _ = BK.collision_tree(coll)
                t2 = V.C.parse(tb, 0, "b3")
                got = sorted((struct.unpack_from("<H", q, 4)[0], tuple(sorted(tuple(round(c, 3) for c in lf.verts[k]) for k in q[:4] if k != 0xFF)))
                             for lf in t2.leaves for q in lf.quads)
                cok += (not V.C.check(t2)) and got == sorted(ref)
                bm = V.X.Block(sm, mo, ms, "mesh", u)
                polys = []
                for r, m in enumerate(bm.meshes):
                    if m["prim"] != 6:
                        continue
                    for a, b, c in V.X.triangles(6, m["idx"])[0]:
                        vs = [bm.verts[k] for k in (a, b, c)]
                        poly = [(v[:3], (v[5], v[6]), V.X.dec_normal(v[3]), (0.5, 0.5, 0.5)) for v in vs]
                        polys.append(("r%d" % r, poly))
                rows = sorted({p[0] for p in polys}, key=lambda s: int(s[1:]))
                if len(rows) > 83 or len(rows) > 127:
                    continue
                try:
                    g = BK.BlockGeom(polys, rows)
                    n_in = len(polys)
                    n_out = sum(len(BK.decode_strip(s)) for _, _, s, _ in g.recs)
                    pvs = BK.pvs_chunks(0, 1, [g], [g], len(rows))
                    prism = [(0.0, 0.0, 0.0, 1.0)] * 4
                    blk = BK.mesh_block(u, prism, g, rows, pvs)
                    same = V.T.MeshModel(blk).serialize(len(blk)) == blk
                    V.TS.b3_mesh_to_rev(blk)
                    mok += same and n_out + g.dropped_slivers == n_in
                except Exception as e:  # noqa: BLE001
                    print("   mesh rebuild unit %d: %r" % (u, e))
            check("T3 %s collision builder on retail quads (6 units)" % tid, cok == len(U), "%d / %d" % (cok, len(U)))
            check("T3 %s mesh writer on retail triangles (6 units)" % tid, mok == len(U), "%d / %d" % (mok, len(U)))
        f = DN.load_control(gdata, "US/C3_V1")
        layout_tree("T3 retail US/C3_V1", f["static.dat"], f["streamed.dat"])
    if converted:
        st = open(os.path.join(converted, "static.dat"), "rb").read()
        sm = open(os.path.join(converted, "streamed.dat"), "rb").read()
        layout_tree("T4 converted track %s" % os.path.basename(os.path.normpath(converted)), st, sm)
    else:
        skip("T4 converted control", "optional: --converted <a converted track folder> (0.1.6 used White Mountain 1.0.2)")


def t5(run, src, b1, gdata):
    def refused(name, fn, why=None):
        why = why or WHY[name]
        try:
            fn()
            check("T5 " + name, False, "accepted")
        except (SourceError, AssertionError, ValueError) as e:
            check("T5 " + name, why in str(e), str(e)[:100])        # refused for the EXPECTED reason only

    def mut_src(name, edit_obj=None, edit_desc=None):
        d = os.path.join(run, "neg_" + name)
        shutil.copytree(src, d)
        if edit_obj:
            p = os.path.join(d, "test_loop.obj")
            txt = open(p).read()
            open(p, "w", newline="\n").write(edit_obj(txt))
        if edit_desc:
            p = os.path.join(d, "test_loop.track.json")
            with open(p) as fh:
                j = json.load(fh)
            edit_desc(j)
            json.dump(j, open(p, "w"))
        return d

    def first_face_to(text, new):
        i = text.index("\nf ")
        j = text.index("\n", i + 1)
        return text[:i + 1] + new + text[j:]
    # the importer refuses before the donor stage: these need no game data (game_data None would refuse at the donor)
    bt = lambda d: B.build_track(d, "test_loop.track.json", game_data=gdata)  # noqa: E731
    refused("pentagon face refused", lambda: bt(mut_src("pent", lambda t: first_face_to(t, "f 1/1/1 2/2/1 3/3/1 4/4/1 5/5/1"))))
    refused("face without uv refused", lambda: bt(mut_src("nouv", lambda t: first_face_to(t, "f 1//1 2//1 3//1"))))
    refused("unknown OBJ statement refused", lambda: bt(mut_src("stmt", lambda t: t.replace("mtllib test_loop.mtl", "l 1 2"))))
    refused("material without a description refused", lambda: bt(mut_src("mat", lambda t: t.replace("usemtl grass", "usemtl lava", 1))))
    refused("zero-area face refused", lambda: bt(mut_src("zero", lambda t: first_face_to(t, "f 1/1/1 1/1/1 1/1/1"))))

    def more_units(j):
        n = len(j["stations"])
        j["units"] = [{"cut_from": k * 21 % n, "cut_to": (k + 1) * 21 % n, "lateral": j["units"][0]["lateral"],
                       "chord_normal": j["units"][0]["chord_normal"]} for k in range(17)] + [j["units"][0]]
    refused("18 units refused (+-8 ring)", lambda: bt(mut_src("u18", edit_desc=more_units)))

    def nonconvex(j):
        j["units"][3]["lateral"] = [5.0, -5.0]
    refused("inverted lateral bounds refused (non-convex region)", lambda: bt(mut_src("ncv", edit_desc=nonconvex)))
    d = mut_src("npot")
    from trackbuild import dxt
    dxt.write_png(os.path.join(d, "textures", "bm_grass.png"), 96, 96, [[(0, 128, 0)] * 96 for _ in range(96)])
    refused("non power-of-two texture refused", lambda: bt(d))

    def flag10(j):
        j["materials"]["wall"]["surface"] = "0x181C"          # the 0.1.0 word (gp_trk_1: car drove through)
    refused("car-solid wall with flag 0x10 refused (gp_trk_1 regression)", lambda: bt(mut_src("f10", edit_desc=flag10)), "flag 0x10")

    def gaps(j):
        j["route"]["lanes"] = j["route"]["lanes"][:4]
    refused("route lanes / offsets mismatch refused", lambda: bt(mut_src("lanes", edit_desc=gaps)))
    if not b1:
        for n in ("region_lane_flipped", "walls_become_road", "walls_flag_0x10", "pvs_row_out_of_range", "strip_reversed",
                  "route_slice_gap", "grid_slot_off_track", "static_pointer_moved", "unit_table_size"):
            skip("T5 mutant %s" % n)
        return

    def rd(d, f):
        return bytearray(open(os.path.join(d, f), "rb").read())

    def wr(d, f, b):
        open(os.path.join(d, f), "wb").write(bytes(b))

    def mutate(name, fn, gate):
        d = os.path.join(run, "mut_" + name)
        shutil.copytree(b1, d)
        fn(d)
        res = V.validate(d, os.path.join(src, "test_loop.track.json"))
        check("T5 mutant %s -> %s fails" % (name, gate), not res[gate]["ok"], res["summary"]["failed"])

    def m_walls10(d):
        st, sm = rd(d, "static.dat"), rd(d, "streamed.dat")
        for mo, lo, ms, ls in V._units(bytes(st)):
            tree = lo + struct.unpack_from("<I", sm, lo + 0xA0)[0]
            pl, nl = struct.unpack_from("<IH", sm, tree + 0x24)
            for i in range(nl):
                o = tree + pl + 16 * i
                pa, nq = struct.unpack_from("<I", sm, o)[0], sm[o + 14]
                for k in range(nq):
                    w = struct.unpack_from("<H", sm, o + pa + 14 * k + 4)[0]
                    if w == 0x0018:
                        struct.pack_into("<H", sm, o + pa + 14 * k + 4, 0x181C)
        wr(d, "streamed.dat", sm)

    def m_region(d):
        st, sm = rd(d, "static.dat"), rd(d, "streamed.dat")
        mo, lo, ms, ls = V._units(bytes(st))[5]
        a = struct.unpack_from("<f", sm, lo + 0x70)[0]
        struct.pack_into("<f", sm, lo + 0x70, -a)         # unit 5: start-cut lane sign flipped
        wr(d, "streamed.dat", sm)
    mutate("region_lane_flipped", m_region, "V2_drivable_coverage")

    def m_quadsurf(d):
        st, sm = rd(d, "static.dat"), rd(d, "streamed.dat")
        for mo, lo, ms, ls in V._units(bytes(st)):
            t = V.C.parse(bytes(sm[lo:lo + ls]), struct.unpack_from("<I", sm, lo + 0xA0)[0], "b3")
            tree = lo + struct.unpack_from("<I", sm, lo + 0xA0)[0]
            pl = struct.unpack_from("<I", sm, tree + 0x24)[0]
            for i in range(len(t.leaves)):
                o = tree + pl + 16 * i
                pa, nq = struct.unpack_from("<I", sm, o)[0], sm[o + 14]
                for k in range(nq):
                    w = struct.unpack_from("<H", sm, o + pa + 14 * k + 4)[0]
                    if (w & 0xFF) >= 21:
                        struct.pack_into("<H", sm, o + pa + 14 * k + 4, 0x0001)     # every wall quad becomes road
        wr(d, "streamed.dat", sm)
    mutate("walls_become_road", m_quadsurf, "V2_walls_hold")
    mutate("walls_flag_0x10 (0.1.0 word)", m_walls10, "V2_walls_hold")

    def m_pvs(d):
        st, sm = rd(d, "static.dat"), rd(d, "streamed.dat")
        mo = V._units(bytes(st))[2][0]
        sm[mo + 0x12A + 3] = 100                           # rowsA[0] of chunk 0 -> record 100 (beyond the block)
        wr(d, "streamed.dat", sm)
    mutate("pvs_row_out_of_range", m_pvs, "V3_pvs_walk")

    def m_wind(d):
        st, sm = rd(d, "static.dat"), rd(d, "streamed.dat")
        mo, lo, ms, ls = V._units(bytes(st))[1]
        ma = mo + 0x50 + struct.unpack_from("<I", sm, mo + 0x5C)[0]
        n, rel = struct.unpack_from("<II", sm, ma + 0x84)
        a, b = struct.unpack_from("<HH", sm, ma + rel)
        struct.pack_into("<HH", sm, ma + rel, b, a)         # first two strip indices swapped: reversed faces
        wr(d, "streamed.dat", sm)
    mutate("strip_reversed", m_wind, "V3_winding")

    def m_route(d):
        gd = rd(d, "Gamedata.bgd")
        g = V.GD.Gamedata.parse(bytes(gd))
        o4, s4 = g.s4()
        r = V.CR.Route.parse(bytes(gd[o4:o4 + s4]))
        r.lanes[2]["segs"][10][0] = 50                      # main lane slice sequence broken
        gd[o4:o4 + s4] = r.serialize(s4)
        wr(d, "Gamedata.bgd", gd)
    mutate("route_slice_gap", m_route, "V5_route")

    def m_grid(d):
        gd = rd(d, "Gamedata.bgd")
        page = struct.unpack_from("<I", gd, 0x3000 + 0x3C0)[0]
        struct.pack_into("<f", gd, page + 0x30, struct.unpack_from("<f", gd, page + 0x30)[0] + 400.0)   # slot 0 400 m away
        wr(d, "Gamedata.bgd", gd)
    mutate("grid_slot_off_track", m_grid, "V5_grid_on_main_lane")

    def m_static(d):
        st = rd(d, "static.dat")
        struct.pack_into("<I", st, 0x08, struct.unpack_from("<I", st, 0x08)[0] + 4)     # material table pointer moved
        wr(d, "static.dat", st)
    try:
        mutate("static_pointer_moved", m_static, "V4_static_identity")
    except Exception as e:  # noqa: BLE001  (the strict reader raises: also a rejection)
        check("T5 mutant static_pointer_moved -> strict reader refuses", True, repr(e)[:100])

    def m_tile(d):
        st = rd(d, "static.dat")
        ut = struct.unpack_from("<I", st, 0x58)[0]
        struct.pack_into("<I", st, ut + 16 * 3 + 8, struct.unpack_from("<I", st, ut + 16 * 3 + 8)[0] + 0x1000)
        wr(d, "static.dat", st)
    try:
        mutate("unit_table_size", m_tile, "V4_unit_table_tiles_streamed")
    except Exception as e:  # noqa: BLE001
        check("T5 mutant unit_table_size -> a reader refuses", True, repr(e)[:100])


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv):
    run = argv[0]
    if os.path.exists(run):
        sys.exit("refusing: %s exists" % run)
    gdata = opt(argv, "--game-data") or os.environ.get("TRACKBUILD_GAME_DATA") or os.environ.get("BMKIT_GAME_DATA")
    if gdata:
        DN.load_donor(gdata)                                # wrong / incomplete data: stop here with the actionable message
    os.makedirs(run)
    src, b1 = t1_t2(run, gdata)
    t3_t4(gdata, opt(argv, "--converted"))
    t5(run, src, b1, gdata)
    npass = sum(1 for _, ok, _ in RES if ok)
    lines = ["%s %s" % ("PASS" if ok else "FAIL", n) for n, ok, _ in RES] + ["SKIP %s (%s)" % s for s in SKIP] + \
            ["TOTAL %d / %d (skipped %d)" % (npass, len(RES), len(SKIP))]
    open(os.path.join(run, "RESULTS.txt"), "w", newline="\n").write("\n".join(lines) + "\n")
    print("TOTAL %d / %d (skipped %d)" % (npass, len(RES), len(SKIP)))
    return 0 if npass == len(RES) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
