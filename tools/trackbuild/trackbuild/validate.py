"""trackbuild.validate - INDEPENDENT structural validators for a built track folder (never trackbuild's own writers):
  V1 streamed layout    CT1 xbtopo MeshModel / LodModel re-serialise every block byte-identically; xbmesh.Block decodes every
                        non-zero byte; trackconv strict rules (b3_mesh_to_rev / b3_lod_to_rev) accept every block
  V2 collision          bolib.collision.check == [] on every tree; every drivable sample point is held by exactly one region
                        and its unit's tree has a floor under it (ray-down, y within 0.05 m of the floor); 0.3.0: the floor is
                        compared with the ROUTE height at the sample (stations interpolated), so routes may climb / descend;
                        walls: every wall
                        sample has a vertical quad in the tree of the unit holding the point in front of it
  V3 render / PVS       every strip decodes to front faces agreeing with the vertex normals; the PVS walk (as xbmesh.Track.
                        material_map / sub_0019D100) reaches every record of every block once per centre unit, no chain error
  V4 static.dat         trackconv b3static strict parse -> build identity (0 rule mismatches); the unit table tiles streamed.dat
  V5 route / Gamedata   ct2_route parse / identity / check / lint; ctnav camera / planner hazards; grid slots assigned to the
                        main lane by the init-search model (ctnav.grid); ct2_gamedata parse / build identity / check; S1 counts
  V6 budgets            mesh <= 0x28000, LOD <= 0x18000, static <= 0xD00000, Gamedata need <= 0x176000"""
import json
import math
import os
import struct
import sys

# 0.2.0: the independent readers are vendored into the package (trackbuild/_vendor, provenance in VENDOR.json); 0.1.6
# imported the same modules from the developer workspace through sys.path.
from ._vendor import xbmesh as X  # noqa: E402
from ._vendor import xbtopo as T  # noqa: E402
from ._vendor import ct2_route as CR  # noqa: E402
from ._vendor import ct2_gamedata as GD  # noqa: E402
from ._vendor.bolib import collision as C  # noqa: E402
from ._vendor.trackconv import b3static as S  # noqa: E402
from ._vendor.trackconv import streamed as TS  # noqa: E402


def _units(st):
    n, ut = struct.unpack_from("<hI", st, 0x54)[0], struct.unpack_from("<I", st, 0x58)[0]
    return [struct.unpack_from("<4I", st, ut + 16 * i) for i in range(n)]


def _pip(p, a, b, c):
    """point (x, z) in triangle (xz) -> barycentric y or None"""
    (x, z), (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p, a, b, c
    d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
    if abs(d) < 1e-9:
        return None
    l1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
    l2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
    l3 = 1 - l1 - l2
    if min(l1, l2, l3) < -1e-6:
        return None
    return l1 * ay + l2 * by + l3 * cy


def _tris_of_quad(q, verts):
    i = list(q[:4])
    t = [(verts[i[0]], verts[i[1]], verts[i[2]])]
    if i[3] != 0xFF:
        t.append((verts[i[1]], verts[i[3]], verts[i[2]]))
    return t


def _region(lod):
    f = struct.unpack_from("<12f", lod, 0x70)
    return list(zip(f[0:4], f[4:8], f[8:12]))


def _inside(reg, x, z, grow=0.0):
    return all(a * x + c * z - b >= -grow for a, c, b in reg)


def validate(out_dir, desc_path=None):
    rd = lambda n: open(os.path.join(out_dir, n), "rb").read()  # noqa: E731
    st, sm, gd = rd("static.dat"), rd("streamed.dat"), rd("Gamedata.bgd")
    rep = json.load(open(os.path.join(out_dir, "BUILD_REPORT.json")))
    if desc_path is None:
        desc_path = os.path.join(rep["source"]["dir"], rep["source"]["desc"])
    desc = json.load(open(desc_path))
    res = {}
    fails = []

    def gate(name, ok, detail):
        res[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            fails.append(name)

    U = _units(st)
    nprop = struct.unpack_from("<h", st, 0x34)[0]
    # ---- V4 static + tiling
    ok, info, o = S.identity(st, "b3")
    pos = 0
    tiles = True
    for mo, lo, ms, ls in U:
        tiles &= mo == pos and lo == mo + ms
        pos = lo + ls
    tiles &= pos == len(sm)
    gate("V4_static_identity", ok and info["garbage_bytes"] == 0, info)
    gate("V4_unit_table_tiles_streamed", tiles, {"units": len(U), "streamed_bytes": len(sm), "nprop": nprop})
    # ---- V1 layout
    v1 = {"mesh_identical": 0, "lod_identical": 0, "uncovered_nonzero": 0, "strict_mesh": 0, "strict_lod": 0, "errors": []}
    blocks = []
    for u, (mo, lo, ms, ls) in enumerate(U):
        mb, lb = sm[mo:mo + ms], sm[lo:lo + ls]
        try:
            v1["mesh_identical"] += T.MeshModel(mb).serialize(ms) == mb
            v1["lod_identical"] += T.LodModel(lb, nprop).serialize(ls) == lb
        except Exception as e:  # noqa: BLE001
            v1["errors"].append("unit %d xbtopo: %r" % (u, e))
        bm, bl = X.Block(sm, mo, ms, "mesh", u), X.Block(sm, lo, ls, "lod", u)
        rt = bm.roundtrip()
        v1["uncovered_nonzero"] += rt["uncovered_nonzero_bytes"]
        try:
            TS.b3_mesh_to_rev(mb)
            v1["strict_mesh"] += 1
        except Exception as e:  # noqa: BLE001
            v1["errors"].append("unit %d strict mesh: %s" % (u, e))
        try:
            TS.b3_lod_to_rev(lb, nprop)
            v1["strict_lod"] += 1
        except Exception as e:  # noqa: BLE001
            v1["errors"].append("unit %d strict LOD: %s" % (u, e))
        blocks.append((bm, bl))
    n = len(U)
    gate("V1_streamed_layout", v1["mesh_identical"] == n and v1["lod_identical"] == n and v1["strict_mesh"] == n and
         v1["strict_lod"] == n and not v1["errors"], v1)
    gate("V1_header_decoded", v1["uncovered_nonzero"] == 0, {"uncovered_nonzero_mesh_bytes": v1["uncovered_nonzero"]})
    # ---- V10 chevron index (0.2.1, capdbg T1): the game draws chevron entry [STATIC+0x28][mesh +0x7D] for every index >= 0
    # without checking the set count s16 STATIC[+0x1E]; an index past the set reads the following structure as entries
    # (crash at race start once the STATIC pool is relocated, e.g. by a bmashup.streaming STATIC request).
    nchev = struct.unpack_from("<h", st, 0x1E)[0]
    zbad = [(u, struct.unpack_from("<b", sm, mo + 0x7D)[0]) for u, (mo, _, _, _) in enumerate(U)
            if not (struct.unpack_from("<b", sm, mo + 0x7D)[0] < 0 or struct.unpack_from("<b", sm, mo + 0x7D)[0] < nchev)]
    gate("V10_chevron_index_in_set", not zbad, {"chevron_entries": nchev, "units_out_of_set": len(zbad), "first": zbad[:3]})
    # ---- V2 collision
    trees, regs = [], []
    probs = []
    for u, (bm, bl) in enumerate(blocks):
        t = C.parse(bl.b, struct.unpack_from("<I", bl.b, 0xA0)[0], "b3")
        p = C.check(t)
        if p:
            probs.append((u, p[:2]))
        trees.append(t)
        regs.append(_region(bl.b))
    gate("V2_tree_check", not probs, {"problems": probs, "trees": len(trees),
                                       "leaves": sum(len(t.leaves) for t in trees),
                                       "quads": sum(len(lf.quads) for t in trees for lf in t.leaves)})
    sts = desc["stations"]
    # 0.3.0: each sample is compared with the route height there (the stations' own y, interpolated), not with station 0
    # (0.2.1 required one height for the whole route). A flat route gives the same result as before.
    samples, holes, multi, worst = 0, [], [], 0.0
    grade = 0.0
    floors = {}
    for u, t in enumerate(trees):
        fl = []
        for lf in t.leaves:
            for q in lf.quads:
                w = struct.unpack_from("<H", q, 4)[0]
                for tri in _tris_of_quad(q, lf.verts):
                    fl.append((w, tri))
        floors[u] = fl
    for i, s_ in enumerate(sts):
        s2 = sts[(i + 1) % len(sts)]
        for f in (0.2, 0.6):                             # off the cut lines (a point ON a shared cut is in both units)
            P = [s_["p"][k] + (s2["p"][k] - s_["p"][k]) * f for k in range(3)]
            tx, tz = s_["t"][0] + (s2["t"][0] - s_["t"][0]) * f, s_["t"][1] + (s2["t"][1] - s_["t"][1]) * f
            L = math.hypot(tx, tz)
            nx, nz = -tz / L, tx / L
            offs = [a + (b - a) * f for a, b in zip(s_["offsets"], s2["offsets"])]
            if f == 0.2:
                run = math.hypot(s2["p"][0] - s_["p"][0], s2["p"][2] - s_["p"][2])
                grade = max(grade, abs(s2["p"][1] - s_["p"][1]) / run if run > 1e-9 else 0.0)
            lo, hi = offs[1] + 0.5, offs[4] - 0.5        # wall to wall (road + pad), 0.5 m from the wall faces
            for j in range(9):
                o = lo + (hi - lo) * j / 8
                x = P[0] + nx * o
                z = P[2] + nz * o
                holders = [u for u in range(n) if _inside(regs[u], x, z)]
                samples += 1
                if len(holders) != 1:
                    multi.append(((round(x, 2), round(z, 2)), holders))
                    continue
                u = holders[0]
                ys = [(y, w) for w, tri in floors[u] for y in [_pip((x, z), *tri)] if y is not None and (w & 0xFF) <= 20]
                if not ys:
                    holes.append(((round(x, 2), round(z, 2)), u))
                    continue
                y = max(ys)[0]
                worst = max(worst, abs(y - P[1]))
    gate("V2_drivable_coverage", not holes and not multi and worst < 0.05,
         {"samples": samples, "not_one_region": multi[:5], "n_not_one_region": len(multi), "no_floor": holes[:5],
          "n_no_floor": len(holes), "max_floor_dy": round(worst, 4),
          "max_route_grade_pct": round(100 * grade, 2)})
    # walls: a horizontal probe from the road edge outwards must cross a wall quad of the holding unit
    wall_miss = 0
    wall_n = 0
    gaps = desc.get("wall_gaps", [])
    for i in range(0, len(sts), 3):
        s_ = sts[i]
        nx, nz = -s_["t"][1], s_["t"][0]
        for o_wall, sgn in ((s_["offsets"][1], -1), (s_["offsets"][4], 1)):
            if sgn < 0 and any(a - 1 <= i <= b for a, b in gaps):     # a DECLARED outer-wall gap (crash-test variant)
                continue
            x = s_["p"][0] + nx * (o_wall - sgn * 0.3)
            z = s_["p"][2] + nz * (o_wall - sgn * 0.3)
            holders = [u for u in range(n) if _inside(regs[u], x, z)]
            if len(holders) != 1:
                continue
            wall_n += 1
            u = holders[0]
            hit = False
            for w, (a, b, c) in floors[u]:
                if (w & 0xFF) < 21 or w & 0x1000:        # only car-solid wall words (flag 0x10 = not in the car query)
                    continue
                # segment from (x, y+0.7, z) to 1 m outwards vs triangle (Moller-Trumbore); y = this station's height (0.3.0)
                p0 = (x, s_["p"][1] + 0.7, z)
                d = (nx * sgn * 1.0, 0.0, nz * sgn * 1.0)
                e1 = [b[k] - a[k] for k in range(3)]
                e2 = [c[k] - a[k] for k in range(3)]
                h = (d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0])
                det = sum(e1[k] * h[k] for k in range(3))
                if abs(det) < 1e-9:
                    continue
                f = 1 / det
                sv = [p0[k] - a[k] for k in range(3)]
                uu = f * sum(sv[k] * h[k] for k in range(3))
                if not 0 <= uu <= 1:
                    continue
                qv = (sv[1] * e1[2] - sv[2] * e1[1], sv[2] * e1[0] - sv[0] * e1[2], sv[0] * e1[1] - sv[1] * e1[0])
                vv = f * sum(d[k] * qv[k] for k in range(3))
                if vv < 0 or uu + vv > 1:
                    continue
                tt = f * sum(e2[k] * qv[k] for k in range(3))
                if 0 <= tt <= 1:
                    hit = True
                    break
            wall_miss += not hit
    gate("V2_walls_hold", wall_miss == 0 and wall_n > 0, {"probes": wall_n, "missed": wall_miss})
    # ---- V3 render winding + PVS walk
    bad_wind, tris, wind_ex = 0, 0, []
    for bm, bl in blocks:
        for blk in (bm, bl):
            for m in blk.meshes:
                for a, b, c in X.triangles(6, m["idx"])[0]:
                    va, vb, vc = blk.verts[a], blk.verts[b], blk.verts[c]
                    e1 = [vb[k] - va[k] for k in range(3)]
                    e2 = [vc[k] - va[k] for k in range(3)]
                    cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                    nrm = X.dec_normal(va[3])
                    tris += 1
                    if sum(cr[k] * nrm[k] for k in range(3)) <= 0:
                        bad_wind += 1
                        if len(wind_ex) < 5:
                            wind_ex.append([round(x, 2) for x in va[:3]] + [round(x, 3) for x in nrm] + [round(x, 4) for x in cr])
    gate("V3_winding", bad_wind == 0, {"triangles": tris, "disagree": bad_wind, "examples": wind_ex})
    walk_err, unreached = 0, 0
    for c in range(n):
        cb = blocks[c][0]
        seen = set()
        for ch in cb.chunks:
            tgt = (c + ch["rel"]) % n
            kind = 0 if abs(ch["rel"]) <= X.NEAR else 1
            blk = blocks[tgt][kind]
            for r in range(X.NROWS):
                k = ch["rowsA"][r]
                if r >= cb.rows_total and k >= 0:
                    walk_err += 1
                while k >= 0:
                    if k >= blk.nmesh or (tgt, kind, k) in seen:
                        walk_err += 1
                        break
                    seen.add((tgt, kind, k))
                    k = blk.meshes[k]["next"]
            if ch["flag"] != 1 and (desc.get("pvs") or {}).get("mode", "all") == "all":
                walk_err += 1
        for ch in cb.chunks:
            tgt = (c + ch["rel"]) % n
            kind = 0 if abs(ch["rel"]) <= X.NEAR else 1
            unreached += sum(1 for k in range(blocks[tgt][kind].nmesh) if (tgt, kind, k) not in seen)
    gate("V3_pvs_walk", walk_err == 0 and unreached == 0, {"chain_errors": walk_err, "unreached_records": unreached,
                                                           "centre_units": n})
    # ---- V5 route / gamedata
    g = GD.Gamedata.parse(gd)
    gp = GD.check(g)
    gate("V5_gamedata", g.build() == gd and not gp, {"check": gp, "events": g.count})
    o4, s4 = g.s4()
    r = CR.Route.parse(gd[o4:o4 + s4])
    rid = r.serialize(s4) == gd[o4:o4 + s4]
    chk, lint = CR.check(r), CR.lint(r)
    from ._vendor import ctnav_min as CAM  # noqa: E402   (0.2.0: vendored ctnav.camera / ctnav.grid subset)
    GRID = CAM
    cam = CAM.camera_hazards(r)
    pl = CAM.planner_hazards(r)
    gate("V5_route", rid and not chk and not lint and not cam and not pl,
         {"identity": rid, "check": chk, "lint": lint, "camera_hazards": len(cam), "planner_hazards": len(pl),
          "lanes": len(r.lanes), "slices": r.slices, "corners": len(r.corners)})
    main = rep["route"]["main_lane"]
    slots = GRID.slots(gd)
    asg = [(e, k, GRID.assign(r, p)) for e, page, k, p in slots]
    gate("V5_grid_on_main_lane", asg and all(a[2][0] == main for a in asg),
         {"slots": len(slots), "assigned": sorted({(a[2][0], a[2][2]) for a in asg}), "max_dist": round(max(a[2][3] for a in asg), 3)})
    # grid / checkpoints on the floor and inside one region each
    gpos = [p for _, _, _, p in slots]
    su_bad = []
    for e, page, k, p in slots:
        hold = [u for u in range(n) if _inside(regs[u], p[0], p[2])]
        su = struct.unpack_from("<I", gd, page + 0x50 * k + 0x40)[0]
        if hold != [su]:
            su_bad.append((e, k, su, hold))
    gate("V5_grid_in_regions", all(sum(_inside(regs[u], p[0], p[2]) for u in range(n)) == 1 for p in gpos) and not su_bad,
         {"slots": len(gpos), "start_unit_mismatch (slot +0x40 vs holding unit)": su_bad[:6]})
    # ---- V9 computed PVS: the flags STORED in the built mesh blocks vs a denser recomputation from the source geometry
    if (desc.get("pvs") or {}).get("mode") == "computed":
        from . import io as TIO, units as TUN, visibility as TVI  # noqa: E402
        obj = TIO.read_obj(os.path.join(os.path.dirname(desc_path), desc["obj"]))
        us = TUN.make_units(desc)
        TUN.assign(us, obj, desc["materials"])
        dense, _ = TVI.compute(us, desc, cam_heights=(1.0, 2.5, 4.0, 6.0, 7.5), target_max=400, seed=7, dilate=0)
        stored_bad, missed = [], []
        for c in range(n):
            for ch in blocks[c][0].chunks:
                t = (c + ch["rel"]) % n
                if ch["flag"] == 0 and t in dense[c]:
                    missed.append((c, ch["rel"]))
        errs, warns = TVI.ring_check(dense, n)
        gate("V9_pvs_computed", not missed and not errs,
             {"flag0_but_visible_in_dense": missed[:8], "n_missed": len(missed), "dense_beyond_ring": errs[:5],
              "dense_ahead_beyond_4": len(warns), "visible_per_unit_dense": [len(v) for v in dense]})
    # ---- V8 LOD: the LOD block's records against the mesh block's, per unit and material row, measured from the FILES
    lodd = desc.get("lod") or {"mode": "identity"}
    if lodd.get("mode") == "decimate":
        from .lod import pt_tri_dist  # noqa: E402
        e_max = lodd.get("e_max", 0.3)
        worst, tri_m, tri_l, area_bad = 0.0, 0, 0, []
        for u, (bm, bl) in enumerate(blocks):
            ch0 = bm.chunks[0]                                   # rel 0: rowsA -> this unit's mesh records
            for r in range(bm.rows_total):
                km = ch0["rowsA"][r]
                if km < 0:
                    continue
                # the LOD record for row r of unit u: from any centre c with |rel| > 4 pointing at u
                c = (u - 5) % n
                chs = blocks[c][0].chunks
                rel_idx = [k for k, x in enumerate(chs) if x["rel"] == 5][0]
                kl = chs[rel_idx]["rowsA"][r]
                if kl < 0 or km >= bm.nmesh or kl >= bl.nmesh:          # out-of-range rows are V3's failure
                    continue
                tm = [tuple(bm.verts[i][:3] for i in t) for t in X.triangles(6, bm.meshes[km]["idx"])[0]]
                tl = [tuple(bl.verts[i][:3] for i in t) for t in X.triangles(6, bl.meshes[kl]["idx"])[0]]
                tri_m += len(tm)
                tri_l += len(tl)
                area = lambda ts: sum(0.5 * math.sqrt(sum(x * x for x in ((b[1]-a[1])*(c_[2]-a[2])-(b[2]-a[2])*(c_[1]-a[1]),  # noqa: E731
                                     (b[2]-a[2])*(c_[0]-a[0])-(b[0]-a[0])*(c_[2]-a[2]), (b[0]-a[0])*(c_[1]-a[1])-(b[1]-a[1])*(c_[0]-a[0])))) for a, b, c_ in ts)
                am, al_ = area(tm), area(tl)
                if am > 1 and abs(al_ - am) / am > 0.02:
                    area_bad.append((u, r, round(am, 1), round(al_, 1)))
                for src, dst in ((tm, tl), (tl, tm)):
                    pts = {p for t in src for p in t} | {tuple((t[0][k] + t[1][k] + t[2][k]) / 3 for k in range(3)) for t in src}
                    for p in pts:
                        best = min(pt_tri_dist(p, *t) for t in dst)
                        worst = max(worst, best)
        gate("V8_lod", worst <= e_max + 1e-3 and not area_bad,
             {"max_two_sided_err_m": round(worst, 4), "bound": e_max, "mesh_tris": tri_m, "lod_tris": tri_l,
              "reduction": round(1 - tri_l / max(1, tri_m), 3), "area_mismatch": area_bad[:5]})
    # ---- V7 traffic (authored S2 / S3 only): bolib structural checks + every lane node centre on the drivable floor
    if desc.get("traffic"):
        from ._vendor.bolib import traffic as TR  # noqa: E402
        rec0 = 0x3000
        s3o, s3s = struct.unpack_from("<I", gd, rec0 + 0x3D0)[0], struct.unpack_from("<I", gd, rec0 + 0x3CC)[0]
        s3 = gd[s3o:s3o + s3s]
        probs = list(TR.check_s3(s3))
        P = TR.parse_s3(s3)
        groups = [gr[3] for gr in P["groups"]]
        sets = {(struct.unpack_from("<I", gd, ro + 0x3C8)[0], struct.unpack_from("<I", gd, ro + 0x3C4)[0]) for ro in g.rec_off}
        for o, s in sets:
            st_ = gd[o:o + s]
            bad, _ = TR.check_set(st_, "b3", groups)
            probs += bad + TR.check_triggers(st_, "b3")
        off_floor = 0
        nodes = 0
        for a, b_, c, cnt in P["groups"]:
            for k in range(cnt + 1):
                e0, e1 = struct.unpack_from("<2H", s3, a + 4 * k)
                p0 = struct.unpack_from("<3f", s3, P["positions_at"] + 16 * e0)
                p1 = struct.unpack_from("<3f", s3, P["positions_at"] + 16 * e1)
                x, z = (p0[0] + p1[0]) / 2, (p0[2] + p1[2]) / 2
                hold = [u for u in range(n) if _inside(regs[u], x, z)]
                nodes += 1
                ok_ = len(hold) >= 1 and any(_pip((x, z), *tri) is not None for w, tri in floors[hold[0]] if (w & 0xFF) <= 20)
                off_floor += not ok_
        gate("V7_traffic", not probs and off_floor == 0, {"problems": probs[:5], "sets": len(sets), "lanes": len(groups),
                                                         "lane_nodes": nodes, "nodes_off_floor": off_floor})
    # ---- V6 budgets
    mm = max(ms for _, _, ms, _ in U)
    ml = max(ls for _, _, _, ls in U)
    gate("V6_budgets", mm <= 0x28000 and ml <= 0x18000 and len(st) <= 0xD00000 and int(rep["gamedata"]["need"], 16) <= 0x176000,
         {"max_mesh": hex(mm), "max_lod": hex(ml), "static": hex(len(st)), "gamedata_need": rep["gamedata"]["need"]})
    res["summary"] = {"ok": not fails, "failed": fails, "gates": len(res)}
    return res


def inspect(out_dir):
    st = open(os.path.join(out_dir, "static.dat"), "rb").read()
    sm = open(os.path.join(out_dir, "streamed.dat"), "rb").read()
    out = []
    for u, (mo, lo, ms, ls) in enumerate(_units(st)):
        bm, bl = X.Block(sm, mo, ms, "mesh", u), X.Block(sm, lo, ls, "lod", u)
        t = C.parse(bl.b, struct.unpack_from("<I", bl.b, 0xA0)[0], "b3")
        out.append({"unit": u, "mesh": hex(ms), "lod": hex(ls), "records": bm.nmesh, "vertices": bm.nvert,
                    "tree": C.stats(t), "rows": bm.rows_total})
    return out
