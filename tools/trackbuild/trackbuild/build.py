"""trackbuild.build - import an authored track (OBJ + textures + track description) and build the B3 track files.

Pipelines (each with its own function and report section):
  render    OBJ polygons -> per-unit clipped polygons -> mesh records (one strip per material row) + identical LOD records
  units     description cuts -> region quads (LOD +0x70) / culling prisms (+0x10); STATIC unit table tiling streamed.dat
  collision collide-material polygons -> per-unit KD trees (grown regions), surface words from the description
  lod       LOD records = the full-detail geometry (no decimation in 0.1: the LOD ring draws the same mesh at |rel| 5..8)
  pvs       generated rows: every unit sees all 17 units of its +-8 window (U <= 17 keeps the whole track resident)
  materials authored PNG -> DXT1 + mip chain in static.dat; material records type 0 / flags 0 / 1 texture (the most common
            retail combination, 2,928 of the retail census)
  route     stations -> S4 v3 (cyclic lanes corridor | edge | main | edge | corridor, corners on the main lane, 8 zones, race
            distance), S1 page (6 grid slots, start / finish line, checkpoints) on the Gamedata host's template
  donor     enviro.dat and the 6 audio files are byte copies of the Gamedata host (DONOR, non-geometry, labelled)
Every product is checked by INDEPENDENT readers in validate.py (xbtopo / xbmesh / bolib.collision / trackconv strict rules /
ct2_route / ct2_gamedata / bmpack)."""
import hashlib
import json
import math
import os
import struct
import sys

from . import blocks as BK
from . import dxt
from . import units as UN
from .io import need, read_desc, read_obj, read_png

from ._vendor.trackconv import b3static as S  # noqa: E402   (0.2.0: vendored, package-relative; no workspace sys.path)
from . import donor as DN  # noqa: E402
from . import capacity as CAP  # noqa: E402   (0.3.4: game defaults / host ceilings, ONE table)

HOST_DEFAULT = DN.HOST_DEFAULT
DONOR_FILES = DN.DONOR_FILES
# the GAME's default sizes (0.3.3 names kept); the limits a build applies come from trackbuild.capacity (mode auto / game)
MESH_SLOT, LOD_SLOT = CAP.TABLE["full_unit_bytes"]["game"], CAP.TABLE["low_unit_bytes"]["game"]
STATIC_POOL = CAP.TABLE["static_bytes"]["game"]
GAMEDATA_SLOT = CAP.TABLE["gamedata_bytes"]["game"]


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------------------------- textures / materials
def texture_record(name, w, h, rgb):
    need(w == h or True, "")
    need(w & (w - 1) == 0 and h & (h - 1) == 0 and 4 <= w <= 1024 and 4 <= h <= 1024,
         "texture %s: %dx%d (power of two, 4..1024)" % (name, w, h))
    texels, mips = dxt.chain(w, h, rgb)
    lw, lh = w.bit_length() - 1, h.bit_length() - 1
    fw = 0x29 | (0x0C << 8) | (mips << 16) | (lw << 20) | (lh << 24)
    d3d = bytearray(0x40)
    struct.pack_into("<4I", d3d, 0, 0x00040001, 0, 0, fw)
    struct.pack_into("<3I", d3d, 0x34, 0x0C, w, h)
    nm = name.encode("ascii")
    need(len(nm) < 32, "texture name %s longer than 31 characters" % name)
    return {"d3d": bytes(d3d), "f": 0, "name": nm.ljust(32, b"\0"), "texels": texels}


def material_record(type_=0, flags=0):
    raw = bytearray(0x28)
    struct.pack_into("<IffI", raw, 0, type_, 0.0, 1.0, 0)
    raw[0x11] = 1
    struct.pack_into("<I", raw, 0x24, flags)
    return bytes(raw)


def type_keys(objs, family):
    """distinct (track, index) of one family in first-appearance order = the written type order"""
    out = []
    for ob in objs or []:
        if ob["family"] == family and (ob["track"], ob["index"]) not in out:
            out.append((ob["track"], ob["index"]))
    return out


def static_object(src_dir, desc, unit_table, retail=None, objs=None):
    """0.3.2: `retail` = {material name: trackbuild.retailmat.resolve(...)} -> that material's record and textures verbatim"""
    texs, mats = [], []
    tex_index = {}
    for r, mat in enumerate(desc["rows"]):
        m = desc["materials"][mat]
        if retail and mat in retail:
            rm = retail[mat]
            ids = []
            for t in rm["textures"]:
                if t["_src"] not in tex_index:
                    tex_index[t["_src"]] = len(texs)
                    texs.append({k: v for k, v in t.items() if k != "_src"})
                ids.append(tex_index[t["_src"]])
            mats.append({"raw": rm["raw"], "tex": ids})
            continue
        tp = m["texture"]
        if tp not in tex_index:
            w, h, rgb = read_png(os.path.join(src_dir, tp))
            tex_index[tp] = len(texs)
            texs.append(texture_record(os.path.splitext(os.path.basename(tp))[0], w, h, rgb))
        mats.append({"raw": material_record(), "tex": [tex_index[tp]]})
    n = len(unit_table)
    inst, ptypes, pbytes, matrices = [], [], b"", []
    ucounts, ulists = [b""] * n, [[] for _ in range(n)]
    if objs:                                                    # 0.3.2: verbatim records, materials appended after the rows
        mat_index = {}

        def mat_of(src_mi, rm):
            key = (rm["source"]["track"], src_mi)
            if key not in mat_index:
                ids = []
                for t in rm["textures"]:
                    if t["_src"] not in tex_index:
                        tex_index[t["_src"]] = len(texs)
                        texs.append({k: v for k, v in t.items() if k != "_src"})
                    ids.append(tex_index[t["_src"]])
                mat_index[key] = len(mats)
                mats.append({"raw": rm["raw"], "tex": ids})
            return mat_index[key]
        recs = {}
        for ob in objs:
            key = (ob["family"], ob["track"], ob["index"])
            if key in recs:
                continue
            raw = bytearray(ob["record"]["raw"])
            for at, m in zip((0x5C, 0x5E, 0x60), ob["materials"]):
                struct.pack_into("<h", raw, at, -1 if m is None else mat_of(m[0], m[1]))
            recs[key] = {"raw": bytes(raw), "lods": ob["record"]["lods"]}
        inst = [recs[("instance",) + k] for k in type_keys(objs, "instance")]
        pk = type_keys(objs, "prop")
        if pk:
            ptypes = [recs[("prop",) + k] for k in pk]
            cls = {}
            per = [[[] for _ in pk] for _ in range(n)]
            for ob in objs:
                if ob["family"] != "prop":
                    continue
                ty = pk.index((ob["track"], ob["index"]))
                cls[ty] = ob["class"]
                for u, m in zip(ob["units"], ob["matrices"]):
                    per[u][ty].append((cls[ty] << 16) | len(matrices))
                    matrices.append(m)
            need(len(matrices) <= 0xFFFF, "more than 65,535 prop placements")
            pbytes = bytes(cls[t] for t in range(len(pk)))
            ucounts = [bytes(len(L) for L in per[u]) for u in range(n)]          # never null (retail 2,838 / 2,838)
            ulists = [[struct.pack("<%dI" % len(L), *L) if L else None for L in per[u]] for u in range(n)]
    o = {"game": "b3", "w14": 0, "textures": texs, "materials": mats, "anim": [],
         "sets": {0x24: [], 0x28: [], 0x2C: [], 0x30: []}, "instances": inst, "proptypes": ptypes, "w56": 0,
         "pbytes": pbytes, "matrices": matrices, "ucounts": ucounts, "ulists": ulists,
         "units": [tuple(e) for e in unit_table], "garbage": []}
    return o


# ---------------------------------------------------------------------------------------------- streamed units
def build_units(src_dir, desc, first_pass=None, objs=None):
    obj = read_obj(os.path.join(src_dir, desc["obj"]))
    for m in obj["materials_used"]:
        need(m in desc["rows"], "OBJ material %s has no row (description 'rows'): describe it under 'materials' and list it in 'rows'" % m)
    for name, m in desc["materials"].items():
        w = int(m["surface"], 16)
        # flag 0x10 (high byte) = excluded from the car's collision query (gp_trk_1 RT: the car passed through 0x181C walls;
        # retail: road-facing faces carry words without 0x10, outer / back faces with it). Car-solid materials must not set it.
        need(not (m.get("collide") and m.get("car_solid", True) and w & 0x1000),
             "material %s: surface 0x%04X has flag 0x10 (not solid for cars); use a word without it or set car_solid false" % (name, w))
    U = len(desc["units"])
    pvs_mode = (desc.get("pvs") or {"mode": "all"})["mode"]
    if pvs_mode == "all":
        need(4 <= U <= 17, "trackbuild 0.1 supports 4..17 units (every unit stays inside the +-8 low ring; see README s5)")
    else:
        need(pvs_mode == "computed", "pvs mode must be all or computed")
        need(CAP.units_check(U, "computed") is None, CAP.units_check(U, "computed") or "")   # 0.3.4: 4..162 (largest retail)
    units = UN.make_units(desc)
    inst_tail, obj_cap = None, None
    if objs:                                                    # 0.3.2: retail instance models / props (trackbuild.retailobj)
        from . import retailobj as RO
        obj_cap = RO.assign_units(objs, units)
        itypes = type_keys(objs, "instance")
        if itypes:
            inst_tail = [{} for _ in units]
            for ob in objs:
                if ob["family"] == "instance":
                    ty = itypes.index((ob["track"], ob["index"]))
                    for u, m in zip(ob["units"], ob["matrices"]):
                        inst_tail[u].setdefault(ty, []).append(m)
    ast = UN.assign(units, obj, desc["materials"])
    need(ast["render_unassigned"] == 0, "%d render polygons lie outside every unit region" % ast["render_unassigned"])
    need(ast["coll_unassigned"] == 0, "%d collision polygons lie outside every unit region" % ast["coll_unassigned"])
    rows = desc["rows"]
    gm = [BK.BlockGeom(u.polys, rows) for u in units]
    lodd = desc.get("lod") or {"mode": "identity"}
    lod_stats = []
    if lodd["mode"] == "decimate":                              # 0.1.4: simplified far mesh (trackbuild.lod)
        from . import lod as LD
        gl = []
        for u in units:
            polys, sst = LD.decimate(u.polys, lodd.get("e_max", 0.3), lodd.get("e_border", 0.05), lodd.get("drop_below"))
            tint = lodd.get("debug_tint")
            if tint:                                            # diagnostic only: makes the LOD records identifiable
                polys = [(m, [(p, uv, n, tuple(min(1.0, c * k) for c, k in zip(rgb, tint))) for p, uv, n, rgb in poly])
                         for m, poly in polys]
            gl.append(BK.BlockGeom(polys, rows))
            lod_stats.append(sst)
    else:
        need(lodd["mode"] == "identity", "lod mode must be identity or decimate")
        gl = gm                                                 # LOD = full detail geometry (0.1 .. 0.1.3)
    vis_info = None
    visible = lambda c, t: True  # noqa: E731
    if pvs_mode == "computed":                                   # 0.1.5: conservative generated PVS (trackbuild.visibility)
        from . import visibility as VI
        vis, vst = VI.compute(units, desc)
        errs, warns = VI.ring_check(vis, U)
        need(not errs, "%d units are visible beyond the +-8 ring (never drawable: pop-in), first %s" % (len(errs), errs[:3]))
        visible = lambda c, t: t in vis[c]  # noqa: E731
        vis_info = dict(vst, visible_per_unit=[len(v) for v in vis], ahead_beyond_4=len(warns),
                        max_ahead=max(((j - k) % U if (j - k) % U <= U // 2 else -((k - j) % U)) for k in range(U) for j in vis[k]),
                        matrix=[sorted(v) for v in vis])
    meshes, lods, info = [], [], []
    for k, u in enumerate(units):
        ys = [v[0][1] for v in gm[k].verts]
        prism = BK.prism_of(u, (min(ys), max(ys)))
        pvs = BK.pvs_chunks(k, U, gm, gl, len(rows), visible)
        m = BK.mesh_block(k, prism, gm[k], rows, pvs, first_pass)
        l, tst = BK.lod_block(k, prism, u, gl[k], u.coll,
                              (len(type_keys(objs, "instance")), inst_tail[k]) if inst_tail else None)
        CAP.check_value("full_unit_bytes", len(m), CAP.mode_of(desc), "unit %d mesh block" % k)
        CAP.check_value("low_unit_bytes", len(l), CAP.mode_of(desc), "unit %d LOD block" % k)
        meshes.append(m)
        lods.append(l)
        need(gm[k].dropped_area < 0.5, "unit %d: %.3f m2 of sliver triangles would be dropped" % (k, gm[k].dropped_area))
        info.append({"unit": k, "mesh_bytes": len(m), "lod_bytes": len(l), "records": len(gm[k].recs), "vertices": len(gm[k].verts),
                     "dropped_slivers": gm[k].dropped_slivers, "dropped_sliver_m2": round(gm[k].dropped_area, 4),
                     "render_polys": len(u.polys), "collision_polys": len(u.coll), "tree": tst,
                     "region_corners": [[round(c[0], 3), round(c[1], 3)] for c in u.corners]})
    table, parts, pos = [], [], 0
    for m, l in zip(meshes, lods):
        table.append((pos, pos + len(m), len(m), len(l)))
        parts += [m, l]
        pos += len(m) + len(l)
    lod_sum = None
    if lod_stats:
        lod_sum = {"mode": "decimate", "e_max": lodd.get("e_max", 0.3), "tris_in": sum(s["tris_in"] for s in lod_stats),
                   "tris_out": sum(s["tris_out"] for s in lod_stats), "max_err": max(s["max_err"] for s in lod_stats),
                   "per_unit": lod_stats, "debug_tint": lodd.get("debug_tint")}
    return b"".join(parts), table, units, {"assign": ast, "units": info, "obj": obj["counts"], "lod": lod_sum,
                                           "pvs": {"mode": pvs_mode, "computed": vis_info}, "objects": obj_cap}


# ---------------------------------------------------------------------------------------------- route (S4) + S1 page
def _ct2():
    from ._vendor import ct2_gamedata, ct2_route
    import types
    return types.SimpleNamespace(GD=ct2_gamedata, CR=ct2_route)


def _bolib():
    from ._vendor.bolib import collision, routes, traffic, gtid
    import types
    return types.SimpleNamespace(K=collision, RT=routes, TR=traffic, gtid=gtid)


def route_model(desc):
    CR = _ct2().CR
    st = desc["stations"]
    sps = desc["stations_per_slice"]
    n = len(st)
    need(n % sps == 0, "station count %d is not a multiple of stations_per_slice %d" % (n, sps))
    slices = n // sps
    lanes_d = desc["route"]["lanes"]
    nb = len(lanes_d) + 1
    r = CR.Route()
    r.pos = []
    node = []
    for k in range(slices):
        s_ = st[k * sps]
        need(len(s_["offsets"]) == nb, "station %d: %d offsets for %d lanes" % (k * sps, len(s_["offsets"]), len(lanes_d)))
        nx, nz = -s_["t"][1], s_["t"][0]
        row = []
        for o in s_["offsets"]:
            r.pos.append([s_["p"][0] + nx * o, s_["p"][1], s_["p"][2] + nz * o, 0.0])
            row.append(len(r.pos) - 1)
        node.append(row)
    corners = desc["route"]["corners"]
    main = next(i for i, l in enumerate(lanes_d) if l["type"] & 0xC0)
    seg_corner = {}
    recs = []
    for ci, c in enumerate(corners):
        rad = int(round(1.03 * c["radius"]))  # XD: retail hairpins 60.7 m -> 62, 57.1 m -> 60, 50.3 m -> 53 (US/C3, EU/C4)
        dirn = 2 if c["turn"] == "toward_n_plus" else 1
        hard = 4 if c["degrees"] >= 45 else 0
        recs.append(struct.pack("<4HBBBB", c["first"] % slices, c["apex"] % slices, c["last"] % slices, rad, main,
                                max(0, 255 - rad // 20), dirn | hard, 0))
        for k in range(c["first"], c["last"] + 1):
            seg_corner[k % slices] = ci
    strips = desc["route"].get("strips") or []
    if not strips:
        r.lanes = []
        for li, ld in enumerate(lanes_d):
            rungs = [[node[k % slices][li], node[k % slices][li + 1]] for k in range(slices + 1)]
            segs, dims, acc = [], [], 0.0
            for k in range(slices):
                left = li - 1 if li > 0 else 0xFF
                right = li + 1 if li < len(lanes_d) - 1 else 0xFF
                cb = seg_corner.get(k, 0xFF) if li == main else 0xFF
                segs.append([k, cb, ld["type"], left, right, k if left != 0xFF else 0xFFFF, k if right != 0xFF else 0xFFFF])
                a0, b0 = rungs[k]
                a1, b1 = rungs[k + 1]
                c0 = [(r.pos[a0][i] + r.pos[b0][i]) / 2 for i in range(3)]
                c1 = [(r.pos[a1][i] + r.pos[b1][i]) / 2 for i in range(3)]
                acc += math.dist(c0, c1)
                w0 = math.dist(r.pos[a0][:3], r.pos[b0][:3])
                w1 = math.dist(r.pos[a1][:3], r.pos[b1][:3])
                dims.append([acc, (w0 + w1) / 2])
            r.lanes.append({"flags": 1, "rungs": rungs, "dims": dims, "segs": segs})
        sinfo = None
    else:
        sinfo = _strip_lanes(r, desc, st, sps, slices, lanes_d, main, seg_corner, corners)
        recs = r.corners_built
    CAP.check_value("lanes", len(r.lanes), CAP.mode_of(desc), "%d route lanes (route-lane table)" % len(r.lanes))
    r.slices = slices
    md = r.lanes[main]["dims"]
    r.dist = [[md[k][0], 0] for k in range(slices)]
    r.corners = recs
    r.nzones = 8
    z = bytearray(0x8C)
    for q in range(8):
        a, b = q * slices // 8, (q + 1) * slices // 8
        length = md[b - 1][0] - (md[a - 1][0] if a else 0.0)
        struct.pack_into("<3fI", z, 16 * q, length, 8.0, 15.0, a)
    r.zones_raw = bytes(z)
    r.size = 0
    info = {"slices": slices, "lanes": len(r.lanes), "nodes": len(r.pos), "corners": len(recs), "main_lane": main,
            "main_length_m": round(md[-1][0], 3)}
    if sinfo is not None:
        info["strips"] = sinfo
    return r, info


def _strip_lanes(r, desc, st, sps, slices, lanes_d, main, seg_corner, corners):
    """0.3.3-rta: route strips (branches, medians) inserted into the lateral lane sequence - the retail rule decoded in
    trackbuild.lanegraph (36 / 36 tracks). desc["route"]["strips"][k] = {name, type, between [A, B] (lane indices; cyclic
    lanes 0..nc-1, strip k = nc + k, earlier strips only), first, last (slices, 1 <= first < last <= slices - 2: no wrap),
    edges [[lo, hi] per rung k = 0..last-first+1, offsets along n+ at the row station], corners: "main" | "none"}.
    Rung 0 and the last rung must have zero width at the A | B boundary (|lo - hi| <= 1e-4 and within 0.05 m of it);
    nodes / links / segment indices are DERIVED from the per-row lateral sequence (nothing is guessed). Replaces r.pos /
    r.lanes; r.corners_built = the corner records sorted by lane (main first, then strips that copy main corners)."""
    nc = len(lanes_d)
    strips = desc["route"]["strips"]
    CAP.check_value("lanes", len(strips) + nc, CAP.mode_of(desc), "%d route lanes (route-lane table)" % (len(strips) + nc))
    for k, sd in enumerate(strips):
        a, b = sd["between"]
        need(0 <= a < nc + k and 0 <= b < nc + k and a != b, "strip %d (%s): between %s must name earlier lanes" % (k, sd.get("name"), sd["between"]))
        need(1 <= sd["first"] < sd["last"] <= slices - 2, "strip %d (%s): slices %d..%d outside 1..%d (no wrap at the start line)"
             % (k, sd.get("name"), sd["first"], sd["last"], slices - 2))
        need(len(sd["edges"]) == sd["last"] - sd["first"] + 2, "strip %d (%s): %d edge pairs, need %d (one per rung)"
             % (k, sd.get("name"), len(sd["edges"]), sd["last"] - sd["first"] + 2))
        need(sd["type"] in (0x00, 0x01, 0x04, 0x05, 0x40, 0x41, 0x80, 0x81), "strip %d: type 0x%X not a retail strip type" % (k, sd["type"]))
        need(sd["last"] - sd["first"] + 1 >= 3, "strip %d: shorter than 3 segments" % k)
    pos, rows = [], []                      # rows[t] = {"seq": [lanes], "node": [node per boundary]}
    for t in range(slices):
        s_ = st[t * sps]
        nx, nz = -s_["t"][1], s_["t"][0]
        seq = list(range(nc))
        bnd = list(s_["offsets"])
        for k, sd in enumerate(strips):
            X = nc + k
            if not sd["first"] <= t <= sd["last"]:
                continue
            A, B = sd["between"]
            need(A in seq and B in seq and seq.index(B) == seq.index(A) + 1,
                 "strip %d (%s) at slice %d: lanes %d | %d are not neighbours there" % (k, sd.get("name"), t, A, B))
            i = seq.index(B)                # boundary index between A and B = i
            lo, hi = sd["edges"][t - sd["first"]]
            if t == sd["first"]:
                need(abs(lo - hi) <= 1e-4 and abs(lo - bnd[i]) <= 0.05,
                     "strip %d (%s): opens at %.3f / %.3f m, must open at zero width on the %d | %d boundary (%.3f m)"
                     % (k, sd.get("name"), lo, hi, A, B, bnd[i]))
                lo = hi = bnd[i]
            else:
                need(hi - lo > 0.05, "strip %d (%s): width %.3f m at slice %d (zero width only at the first / last rung, KB R1)"
                     % (k, sd.get("name"), hi - lo, t))
            seq.insert(i, X)
            bnd[i:i + 1] = [lo, hi]
        for j in range(len(bnd) - 1):
            need(bnd[j + 1] - bnd[j] >= -1e-6, "slice %d: lane boundaries out of order (%s)" % (t, [round(x, 3) for x in bnd]))
        node = []
        for j, o in enumerate(bnd):
            if j and abs(o - bnd[j - 1]) <= 1e-4:
                node.append(node[-1])       # zero-width opening rung: the strip's two edges are ONE node (retail)
                continue
            pos.append([s_["p"][0] + nx * o, s_["p"][1], s_["p"][2] + nz * o, 0.0])
            node.append(len(pos) - 1)
        rows.append({"seq": seq, "node": node, "bnd": bnd})
    for k, sd in enumerate(strips):         # closing rung: zero width on the A | B boundary of row last + 1
        t = sd["last"] + 1
        A, B = sd["between"]
        seq = rows[t]["seq"]
        need(A in seq and B in seq and seq.index(B) == seq.index(A) + 1,
             "strip %d (%s): lanes %d | %d are not neighbours at its closing slice %d" % (k, sd.get("name"), A, B, t))
        lo, hi = sd["edges"][-1]
        ob = rows[t]["bnd"][seq.index(B)]
        need(abs(lo - hi) <= 1e-4 and abs(lo - ob) <= 0.05,
             "strip %d (%s): closes at %.3f / %.3f m, must close at zero width on the %d | %d boundary (%.3f m)"
             % (k, sd.get("name"), lo, hi, A, B, ob))
    r.pos = pos

    def rung(L, t):
        """L's rung on row t: its own two boundary nodes, or (closing) the node between its last neighbours"""
        row = rows[t % slices]
        if L in row["seq"]:
            i = row["seq"].index(L)
            return [row["node"][i], row["node"][i + 1]]
        sd = strips[L - nc]
        A, B = sd["between"]
        i = row["seq"].index(B)
        return [row["node"][i], row["node"][i]]

    def segidx(L, t):
        return t if L < nc else t - strips[L - nc]["first"]

    lane_types = [ld["type"] for ld in lanes_d] + [sd["type"] for sd in strips]
    span = [(0, slices - 1)] * nc + [(sd["first"], sd["last"]) for sd in strips]
    copied = {}                              # strip lane -> [(corner index, first, apex, last) relative]
    for k, sd in enumerate(strips):
        if sd.get("corners", "none") == "main" and lane_types[nc + k] & 0xC0:
            for ci, c in enumerate(corners):
                if sd["first"] <= c["first"] and c["last"] <= sd["last"]:
                    copied.setdefault(nc + k, []).append(ci)
    r.lanes = []
    for L in range(nc + len(strips)):
        f, l = span[L]
        segs, dims, rungs, acc = [], [], [], 0.0
        for t in range(f, l + 1):
            seq = rows[t]["seq"]
            i = seq.index(L)
            left = seq[i - 1] if i > 0 else 0xFF
            right = seq[i + 1] if i + 1 < len(seq) else 0xFF
            if L == main:
                cb = seg_corner.get(t, 0xFF)
            elif L in copied:
                cb = next((ci for ci in copied[L] if corners[ci]["first"] <= t <= corners[ci]["last"]), 0xFF)
            else:
                cb = 0xFF
            segs.append([t, cb, lane_types[L], left, right, segidx(left, t) if left != 0xFF else 0xFFFF,
                         segidx(right, t) if right != 0xFF else 0xFFFF])
            rungs.append(rung(L, t))
        rungs.append(rung(L, l + 1))
        for j in range(len(segs)):
            a0, b0 = rungs[j]
            a1, b1 = rungs[j + 1]
            c0 = [(pos[a0][i] + pos[b0][i]) / 2 for i in range(3)]
            c1 = [(pos[a1][i] + pos[b1][i]) / 2 for i in range(3)]
            acc += math.dist(c0, c1)
            dims.append([acc, (math.dist(pos[a0][:3], pos[b0][:3]) + math.dist(pos[a1][:3], pos[b1][:3])) / 2])
        r.lanes.append({"flags": 1 if L < nc else 0, "rungs": rungs, "dims": dims, "segs": segs})
    # corner records sorted by lane (the planner stops at the first record of a higher lane: AI s5)
    recs = []
    for ci, c in enumerate(corners):
        rad = int(round(1.03 * c["radius"]))
        dirn = 2 if c["turn"] == "toward_n_plus" else 1
        hard = 4 if c["degrees"] >= 45 else 0
        recs.append((main, struct.pack("<4HBBBB", c["first"] % slices, c["apex"] % slices, c["last"] % slices, rad, main,
                                       max(0, 255 - rad // 20), dirn | hard, 0)))
    for L, cis in sorted(copied.items()):
        f = span[L][0]
        for ci in cis:
            c = corners[ci]
            rad = int(round(1.03 * c["radius"]))
            dirn = 2 if c["turn"] == "toward_n_plus" else 1
            hard = 4 if c["degrees"] >= 45 else 0
            recs.append((L, struct.pack("<4HBBBB", c["first"] - f, c["apex"] - f, c["last"] - f, rad, L,
                                        max(0, 255 - rad // 20), dirn | hard, 0)))
    recs.sort(key=lambda x: x[0])
    need(main == min(x[0] for x in recs) if recs else True, "main lane must carry the lowest corner lane index")
    r.corners_built = [x[1] for x in recs]
    return {"strips": [{"name": sd.get("name"), "lane": nc + k, "type": "0x%02X" % sd["type"], "between": sd["between"],
                        "slices": [sd["first"], sd["last"]], "segments": sd["last"] - sd["first"] + 1,
                        "corner_records": len(copied.get(nc + k, []))} for k, sd in enumerate(strips)],
            "nodes": len(pos)}


def s4_bytes(r):
    return r.serialize(0, grow=True)          # the smallest 0x800 multiple holding the section


def s1_page(template, desc, units=None):
    """grid slot k = page + 0x50 k: 4x4 matrix (row 0 right, row 2 forward, row 3 position) + u32 at +0x40 = the START UNIT
    (the unit whose region holds the slot: XD 4 / 4 retail tracks, e.g. EU/M1_V1 104, US/C3_V1 2; it seeds the stream ring
    MEM32(0x739C58) via sub_0018C470, and the car's collision unit is searched only in the low centre +-4: a wrong value
    = no collision at the start - gp_trk_5 / gp_trk_6 fell through the canyon with the donor's 104)"""
    p = bytearray(template)
    p[0:0x3E0] = bytes(0x3E0)
    for k, g in enumerate(desc["grid"][:6]):
        fx, _, fz = g["fwd"]
        m = [fz, 0.0, -fx, 0.0, 0.0, 1.0, 0.0, 0.0, fx, 0.0, fz, 0.0, g["pos"][0], g["pos"][1], g["pos"][2], 0.0]
        struct.pack_into("<16f", p, 0x50 * k, *m)
        p[0x50 * k + 0x40:0x50 * k + 0x50] = template[0x50 * k + 0x40:0x50 * k + 0x50]
        if units is not None:
            hold = [u.k for u in units if u.inside(g["pos"][0], g["pos"][2])]
            need(len(hold) == 1, "grid slot %d is in %d unit regions" % (k, len(hold)))
            struct.pack_into("<I", p, 0x50 * k + 0x40, hold[0])
    need(len(desc["grid"]) == 6, "the start grid needs exactly 6 slots")

    def line(at, L):
        struct.pack_into("<8f", p, at, L["pos"][0], L["pos"][1], L["pos"][2], L["width"], *L["normal"], 0.0)
    line(0x1E0, desc["start_line"])
    line(0x220, desc["start_line"])
    cps = desc["checkpoints"]
    need(1 <= len(cps) <= 12, "1..12 checkpoints (S1 cap 12)")
    for j, c in enumerate(cps):
        line(0x260 + 0x20 * j, c)
    struct.pack_into("<3I", p, 0x3EC, 1, 1, len(cps))
    return bytes(p)


def _gtid(name):
    return _bolib().gtid.encode(name)


# decoded Gamedata header / event-record fields (KB XBOX_TRACK_FORMATS s2, ct2_gamedata, RACE_DATA_OVERRIDE, bmpack rename);
# everything else is undecoded (build-tool memory or unknown values) - the "zeroed" experiment writes 0 there
HEADER_DECODED = [(0x8, 0x198), (0x198, 0x260), (0x260, 0x278), (0x2810, 0x2850)]
RECORD_DECODED = [(0x390, 0x3A0), (0x3B4, 0x3DC)]


def zero_undecoded(out, n):
    """EXPERIMENT (description "gamedata_header": "zeroed"): every header / event-record byte outside the decoded fields
    becomes 0 -> count of bytes changed. Removes the donor's undecoded header content; runtime decides if the game needs it."""
    changed = 0
    keep = bytearray(0x3000)
    for a, b in HEADER_DECODED:
        keep[a:b] = b"\x01" * (b - a)
    for i in range(0x3000):
        if not keep[i] and out[i]:
            out[i] = 0
            changed += 1
    keep = bytearray(0x800)
    for a, b in RECORD_DECODED:
        keep[a:b] = b"\x01" * (b - a)
    for k in range(n):
        base = 0x3000 + 0x800 * k
        for i in range(0x800):
            if not keep[i] and out[base + i]:
                out[base + i] = 0
                changed += 1
    return changed


def gamedata_authored_traffic(host_bgd, desc, r, units=None):
    """header + event records from the host (DONOR); S1 page, the S2 traffic set, the S3 lane network and S4 AUTHORED, laid
    out S1 | S2 | S3 | S4 after the records; every record's four {offset, size} pairs, the header section table and the
    per-variant S2 table rewritten. Nothing of the host's sections is kept."""
    from . import traffic as TF
    GD = _ct2().GD
    TR = _bolib().TR
    g = GD.Gamedata.parse(host_bgd)
    need(not GD.check(g), "host Gamedata check")
    n = g.count
    need(g.rec_off == [0x3000 + 0x800 * k for k in range(n)], "host records not contiguous from 0x3000")
    s1o = {struct.unpack_from("<I", r_, 0x3C0)[0] for r_ in g.records}
    need(len(s1o) == 1, "host events use several S1 pages")
    s1o = s1o.pop()
    s3, s3i = TF.build_s3(desc)
    need(not TR.check_s3(s3), "authored S3: %s" % TR.check_s3(s3)[:2])
    st, sti = TF.build_set(desc, s3i["nodes"])
    groups = [gr[3] for gr in TR.parse_s3(s3)["groups"]]
    bad, _ = TR.check_set(st, "b3", groups)
    bad = bad or TR.check_triggers(st, "b3")
    need(not bad, "authored traffic set: %s" % bad[:2])
    s4 = s4_bytes(r)
    out = bytearray(host_bgd[:0x3000 + 0x800 * n])
    a1 = len(out)
    out += s1_page(host_bgd[s1o:s1o + 0x800], desc, units)
    a2 = len(out)
    out += st
    a3 = len(out)
    out += s3
    a4 = len(out)
    out += s4
    for ro in g.rec_off:
        for nm, (o, sz) in (("S1", (a1, 0x800)), ("S2", (a2, len(st))), ("S3", (a3, len(s3))), ("S4", (a4, len(s4)))):
            fo, fs = GD.REFS[nm]
            struct.pack_into("<I", out, ro + fo, o)
            struct.pack_into("<I", out, ro + fs, sz)
    struct.pack_into("<5I", out, 0x264, 0x3000, a1, a2, a3, a4)
    for k in range(3):
        struct.pack_into("<I", out, 0x2834 + 4 * k, len(st))
        struct.pack_into("<I", out, 0x2840 + 4 * k, a2)
    zeroed = 0
    if desc.get("gamedata_header") == "zeroed":
        zeroed = zero_undecoded(out, n)
    out = bytes(out)
    g2 = GD.Gamedata.parse(out)
    pr = GD.check(g2)
    need(not pr, "built Gamedata fails ct2_gamedata.check: %s" % pr)
    needb = max(0x3800 + sum(struct.unpack_from("<I", out, ro + fs)[0] for _, fs in GD.REFS.values()) for ro in g.rec_off)
    CAP.check_value("gamedata_bytes", needb, CAP.mode_of(desc), "Gamedata route data need")
    return out, {"host_sha256": sha(host_bgd), "zeroed_undecoded_bytes": zeroed, "layout": {"S1": "0x%X" % a1, "S2": "0x%X" % a2, "S3": "0x%X" % a3, "S4": "0x%X" % a4},
                 "s4_bytes": len(s4), "need": "0x%X" % needb, "traffic": {"s3": s3i, "set": sti}, "authored_traffic": True}


def gamedata(host_bgd, desc, r, units=None):
    if desc.get("traffic"):
        return gamedata_authored_traffic(host_bgd, desc, r, units)
    """host header / records / S2 traffic sets / S3 lane network kept byte for byte (DONOR, see README s4); the single S1 page
    replaced in place; S4 replaced at the end of the file and every record's S4 size field rewritten."""
    GD = _ct2().GD
    g = GD.Gamedata.parse(host_bgd)
    need(not GD.check(g), "host Gamedata check")
    s1 = {(struct.unpack_from("<I", r_, 0x3C0)[0], struct.unpack_from("<I", r_, 0x3BC)[0]) for r_ in g.records}
    need(len(s1) == 1, "the host's events use %d S1 pages (choose a host without crash junctions)" % len(s1))
    s1o, s1s = s1.pop()
    need(s1s == 0x800, "host S1 page size")
    o4, sz4 = g.s4()
    need(o4 + sz4 == len(host_bgd), "host S4 is not last")
    s4 = s4_bytes(r)
    out = bytearray(host_bgd[:o4])
    out[s1o:s1o + 0x800] = s1_page(host_bgd[s1o:s1o + 0x800], desc, units)
    out += s4
    for ro in g.rec_off:
        struct.pack_into("<I", out, ro + GD.REFS["S4"][1], len(s4))
    out = bytes(out)
    g2 = GD.Gamedata.parse(out)
    pr = GD.check(g2)
    need(not pr, "built Gamedata fails ct2_gamedata.check: %s" % pr)
    needb = max(0x3800 + sum(struct.unpack_from("<I", out, ro + fs)[0] for _, fs in GD.REFS.values()) for ro in g.rec_off)
    CAP.check_value("gamedata_bytes", needb, CAP.mode_of(desc), "Gamedata route data need")
    changed = [i for i in range(min(len(out), len(host_bgd))) if out[i] != host_bgd[i] and not (s1o <= i < s1o + 0x800)
               and i < o4]
    return out, {"host_sha256": sha(host_bgd), "s1_page": "0x%X" % s1o, "s4_offset": "0x%X" % o4, "s4_bytes": len(s4),
                 "need": "0x%X" % needb, "changed_bytes_outside_s1_s4": len(changed)}


# ---------------------------------------------------------------------------------------------- 0.3.2 retail materials
def retail_materials(desc, game_data):
    """resolve every row material that names retail_material (trackbuild.retailmat; verbatim copy) and order the rows:
    pass A (no blend bit) first, then pass B (blend bit 0x01) - a stable reorder of desc["rows"] in place, so row r is still
    material r. -> (retail, report, first_pass row count or None when every row is pass A = the 0.3.1 bytes)"""
    rows = desc["rows"]
    named = [r for r in rows if "retail_material" in desc["materials"][r]]
    if not named:
        return None, {"retail": [], "first_pass_rows": len(rows), "rows_reordered": False}, None
    from . import retailmat as RM
    need(game_data is not None or os.environ.get("TRACKBUILD_GAME_DATA"),
         "retail_material needs your game data (--game-data) to copy the material from")
    retail = {r: RM.resolve(r, desc["materials"][r]["retail_material"], game_data) for r in named}
    a = [r for r in rows if r not in retail or retail[r]["pass"] == "A"]
    b = [r for r in rows if r in retail and retail[r]["pass"] == "B"]
    reordered = a + b != rows
    desc["rows"] = a + b
    info = {"retail": [{"material": r, "row": (a + b).index(r), "kind": retail[r]["kind"], "flags": "0x%X" % retail[r]["flags"],
                        "pass": retail[r]["pass"], "formats": retail[r]["formats"],
                        "source": {k: v for k, v in retail[r]["source"].items() if k != "path"},
                        "source_record_sha256": sha(retail[r]["raw"]),
                        "source_texture_sha256": [sha(t["d3d"] + t["name"] + struct.pack("<I", t["f"]) + t["texels"])
                                                  for t in retail[r]["textures"]]}
                       for r in named],
            "first_pass_rows": len(a), "rows_reordered": reordered, "rows": list(desc["rows"]),
            "label": "LOCAL ONLY: retail material records and texels copied verbatim from your game data"}
    return retail, info, (len(a) if b else None)


# ---------------------------------------------------------------------------------------------- whole track
def build_track(src_dir, desc_name, host=HOST_DEFAULT, game_data=None, unpinned_donor=False, donor_files=None):
    """0.2.0: the donor parts come from `game_data` (the user's own prepared data, explicit: donor.resolve) or from
    `donor_files` already loaded by donor.load_donor (tb.py loads them first, so a data problem stops the command at once);
    every donor file is hash-checked against donor.DONOR_PINS (DonorError otherwise). Source problems are reported first."""
    desc = read_desc(os.path.join(src_dir, desc_name))
    from .preflight import check_desc
    check_desc(src_dir, desc)                                    # 0.2.0: unsupported features refused with a reason
    retail, minfo, first_pass = retail_materials(desc, game_data)
    objs = None
    if desc.get("retail_objects"):
        from . import retailobj as RO
        objs = RO.resolve(desc["retail_objects"], game_data)
    streamed, table, units, uinfo = build_units(src_dir, desc, first_pass, objs)
    so = static_object(src_dir, desc, table, retail, objs)
    if objs:
        minfo["objects"] = [{"family": ob["family"], "track": ob["track"], "index": ob["index"], "placements": len(ob["matrices"]),
                             "units": ob["units"], "class": ob["class"],
                             "source_record_sha256": sha(ob["record"]["raw"][:0x5C] + ob["record"]["raw"][0x62:]),
                             "source_lods_sha256": sha(b"".join(L["vtx"] + L["idx"] for L in ob["record"]["lods"])),
                             "source_material_sha256": [None if m is None else sha(m[1]["raw"]) for m in ob["materials"]],
                             "matrix_elements_3_7_11_15": "copied from the source's first placement (APPROXIMATE)"}
                            for ob in objs]
    static = S.build(so, "b3")
    CAP.check_value("static_bytes", len(static), CAP.mode_of(desc), "static.dat")
    r, rinfo = route_model(desc)
    dfiles = donor_files if donor_files is not None else DN.load_donor(game_data, host, unpinned_donor)
    host_bgd = dfiles["Gamedata.bgd"]
    gd, ginfo = gamedata(host_bgd, desc, r, units)
    products = {"static.dat": static, "streamed.dat": streamed, "Gamedata.bgd": gd}
    donor = {}
    for f in DONOR_FILES:
        b = dfiles[f]
        products[f] = b
        donor[f] = {"sha256": sha(b), "bytes": len(b), "label": "DONOR (unchanged retail %s/%s)" % (host, f)}
    report = {"label": {"static.dat": "AUTHORED (textures, materials, unit table from the source)",
                        "streamed.dat": "AUTHORED (geometry, collision, PVS from the source; retail constants listed)",
                        "Gamedata.bgd": ("AUTHORED S1 page + S2 traffic set + S3 lane network + S4 route on a DONOR header / event "
                                         "records" if desc.get("traffic") else
                                         "AUTHORED S1 page + S4 route on a DONOR header / records / S2 traffic sets / S3 lane network"),
                        "donor": donor},
              "retail_constants": BK.RETAIL_CONSTANTS, "units": uinfo, "route": rinfo, "gamedata": ginfo,
              "static": {"bytes": len(static), "textures": len(so["textures"]), "materials": len(so["materials"])},
              "materials": minfo,
              "streamed": {"bytes": len(streamed), "units": len(table)},
              "sha256": {k: sha(v) for k, v in sorted(products.items())}, "host": host}
    report["capacity"] = CAP.summary(CAP.needed_capacity(report), CAP.mode_of(desc))      # 0.3.4: what mod.toml must declare
    return products, report, (desc, units, r, so, table)
