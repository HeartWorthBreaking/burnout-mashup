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

HOST_DEFAULT = DN.HOST_DEFAULT
DONOR_FILES = DN.DONOR_FILES
MESH_SLOT, LOD_SLOT = 0x28000, 0x18000
STATIC_POOL = 0xD00000
GAMEDATA_SLOT = 0x176000


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


def static_object(src_dir, desc, unit_table):
    texs, mats = [], []
    tex_index = {}
    for r, mat in enumerate(desc["rows"]):
        m = desc["materials"][mat]
        tp = m["texture"]
        if tp not in tex_index:
            w, h, rgb = read_png(os.path.join(src_dir, tp))
            tex_index[tp] = len(texs)
            texs.append(texture_record(os.path.splitext(os.path.basename(tp))[0], w, h, rgb))
        mats.append({"raw": material_record(), "tex": [tex_index[tp]]})
    n = len(unit_table)
    o = {"game": "b3", "w14": 0, "textures": texs, "materials": mats, "anim": [],
         "sets": {0x24: [], 0x28: [], 0x2C: [], 0x30: []}, "instances": [], "proptypes": [], "w56": 0,
         "pbytes": b"", "matrices": [], "ucounts": [b""] * n, "ulists": [[] for _ in range(n)],
         "units": [tuple(e) for e in unit_table], "garbage": []}
    return o


# ---------------------------------------------------------------------------------------------- streamed units
def build_units(src_dir, desc):
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
        need(pvs_mode == "computed" and 4 <= U <= 162, "pvs mode computed: 4..162 units (retail STATIC unit range)")
    units = UN.make_units(desc)
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
            polys, sst = LD.decimate(u.polys, lodd.get("e_max", 0.3), lodd.get("e_border", 0.05))
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
        m = BK.mesh_block(k, prism, gm[k], rows, pvs)
        l, tst = BK.lod_block(k, prism, u, gl[k], u.coll)
        need(len(m) <= MESH_SLOT, "unit %d mesh block 0x%X > slot 0x%X" % (k, len(m), MESH_SLOT))
        need(len(l) <= LOD_SLOT, "unit %d LOD block 0x%X > slot 0x%X" % (k, len(l), LOD_SLOT))
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
                                           "pvs": {"mode": pvs_mode, "computed": vis_info}}


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
    return r, {"slices": slices, "lanes": len(r.lanes), "nodes": len(r.pos), "corners": len(recs), "main_lane": main,
               "main_length_m": round(md[-1][0], 3)}


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
    need(needb <= GAMEDATA_SLOT, "route data need 0x%X > slot" % needb)
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
    need(needb <= GAMEDATA_SLOT, "route data need 0x%X > slot" % needb)
    changed = [i for i in range(min(len(out), len(host_bgd))) if out[i] != host_bgd[i] and not (s1o <= i < s1o + 0x800)
               and i < o4]
    return out, {"host_sha256": sha(host_bgd), "s1_page": "0x%X" % s1o, "s4_offset": "0x%X" % o4, "s4_bytes": len(s4),
                 "need": "0x%X" % needb, "changed_bytes_outside_s1_s4": len(changed)}


# ---------------------------------------------------------------------------------------------- whole track
def build_track(src_dir, desc_name, host=HOST_DEFAULT, game_data=None, unpinned_donor=False, donor_files=None):
    """0.2.0: the donor parts come from `game_data` (the user's own prepared data, explicit: donor.resolve) or from
    `donor_files` already loaded by donor.load_donor (tb.py loads them first, so a data problem stops the command at once);
    every donor file is hash-checked against donor.DONOR_PINS (DonorError otherwise). Source problems are reported first."""
    desc = read_desc(os.path.join(src_dir, desc_name))
    from .preflight import check_desc
    check_desc(src_dir, desc)                                    # 0.2.0: unsupported features refused with a reason
    streamed, table, units, uinfo = build_units(src_dir, desc)
    so = static_object(src_dir, desc, table)
    static = S.build(so, "b3")
    need(len(static) <= STATIC_POOL, "static.dat 0x%X > pool" % len(static))
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
              "streamed": {"bytes": len(streamed), "units": len(table)},
              "sha256": {k: sha(v) for k, v in sorted(products.items())}, "host": host}
    return products, report, (desc, units, r, so, table)
