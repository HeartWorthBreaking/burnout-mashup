"""trackbuild.testloop - the ORIGINAL procedural test area "BM Test Loop" (AUTHORED): a stadium loop (flat; 0.3.0: optional
hill profile, HILL_VARIANT) (two 200 m
straights, two 180-degree turns of 50 m centre-line radius, 14 m road) with 1.5 m walls on both sides, a 20 m wide concrete
pad on the outside of the start straight, grass verges and infield, and a chequered start line. Everything here is generated
from parameters; no game data is read.

Writes the source assets the importer consumes (all original, deterministic):
  <out>/test_loop.obj          geometry: `v x y z r g b` (vertex colour extension), vt, vn, `usemtl`, faces (quads / tris)
  <out>/textures/*.png         5 procedural textures (asphalt, pad, start, wall, grass), 128 x 128 RGB
  <out>/test_loop.track.json   track description: materials (texture, collision surface word), stations (centre line, tangent,
                               lateral lane-boundary offsets), unit cuts + lateral bounds, start grid, lap lines, corners, ids

Conventions (B3 Xbox, see FORMAT notes in README): Y up; lateral axis n+ = (-tz, tx) (the side a positive turn turns
toward; route node1 side); offsets are measured along n+ (positive = infield here). Faces are wound so that
cross(b - a, c - a) points along the face normal (the renderer culls back faces; collision floors face up)."""
import json
import math
import os
import random

from . import dxt

P = dict(Ls=200.0, Rc=50.0, hw=7.0, wall_t=0.6, wall_h=1.5, verge=25.0, pad_w=20.0, pad_from=10.0, pad_to=110.0,
         pad_taper=30.0, y0=20.0, X0=-6000.0, Z0=-6000.0, s_start_x=-40.0, n_units=17, st_per_unit=21, st_per_slice=3,
         infield_arc_gap=3.0, tex=128, vcol=0.2)   # vcol 0.2 since 0.1.2 (gp_trk_3: 0.5 was over-bright, road luma x2.5)
# crash / off-track test variant (separate package EU_T2_V1, never combined with the example): a 2 m barrier across the whole
# road in the middle of the back straight (station 200, ~400 m after the start: > 40 m/s) and a 28 m gap in the outer wall
# of the start straight (stations 10..24) leading onto the 25 m verge and its unbounded edge (off-track exit / fall test)
CRASH_VARIANT = dict(name="BM Crash Test", barrier_st=200, wall_gap_st=(10, 24))
# brightness A/B variant (separate package EU_T3_V1): the example geometry with vertex colours scaled 0.5 -> 0.2 (retail road /
# grass vertex colours: median RGB 42 / 39 on EU/M1_V1, 51-86 on US/C3_V1, i.e. 0.16-0.34; the example uses 0.5 = 128)
BRIGHT_B_VARIANT = dict(name="BM Test Loop B", vcol=0.2)
# Gamedata-header experiment (separate package EU_T4_V1): the example with every undecoded header / event-record byte zeroed
ZEROED_HEADER_VARIANT = dict(name="BM Test Loop Z", gamedata_header="zeroed")
# LOD diagnostic variant (separate package EU_T5_V1): the decimated LOD records get a blue tint so that a frame shows which
# units the game draws from the LOD block (|rel| 5..8 from the ring centre) - never for real use
LOD_TINT_VARIANT = dict(name="BM Test Loop L", lod_tint=(0.35, 0.6, 2.0))
# the larger AUTHORED track for the visibility generator (separate package EU_T6_V1 "BM Canyon Ring"): a 150 m-radius ring
# (942 m) in 30 units with 8 m walls, so a camera sees about 4 units ahead / behind and nothing across the infield: the
# computed PVS flags must hide the far side (the "all visible" PVS of <= 17-unit tracks cannot be used with 30 units)
CANYON_RING_V1 = dict(name="BM Canyon Ring", shape="circle", Rc=150.0, n_units=30, wall_h=8.0, verge=6.0, pad_w=0.0,
                      circle_infield=8.0, pvs="computed")
# gp_trk_5: the pure ring failed at runtime - the game's rolling start drives the grid STRAIGHT for ~100 m before GO (no
# collision in that phase), which left the 150 m-radius ring and fell into the void. The canyon is therefore a stadium with a
# 180 m start straight (the rolling start stays on it) and 120 m-radius turns: 1,114 m in 30 units of 37 m (36 units of 31 m left a back view along the straight 9 units long: rejected by the ring check), 8 m walls, computed PVS.
CANYON_VARIANT = dict(name="BM Canyon Ring", Ls=180.0, Rc=120.0, s_start_x=-55.0, n_units=30, wall_h=8.0, verge=6.0, pad_w=0.0,
                      infield_strip=8.0, pvs="computed")
# 0.3.0 sloped-route variant (test / demo, separate package): the example loop with a smooth hill of `amp` metres between the
# fractions s_from .. s_to of the lap (height = amp * sin^2 over that span, 0 elsewhere). The start line, the grid behind it
# and the first 30 % of the lap (the rolling start drives the grid straight for ~100 m) stay at the base height; road, pad,
# walls, verges, stations, checkpoints follow the profile; floor normals are each face's own (Newell). Max grade = pi * amp / span.
HILL_VARIANT = dict(name="BM Hill Loop", elevation=dict(amp=8.0, s_from=0.30, s_to=0.90))


def height(s, total, p=P):
    """route height at arc length s (0.3.0): the base height, plus the HILL_VARIANT profile when the parameters ask for one"""
    e = p.get("elevation")
    if not e:
        return p["y0"]
    f = (s % total) / total
    if not e["s_from"] < f < e["s_to"]:
        return p["y0"]
    return p["y0"] + e["amp"] * math.sin(math.pi * (f - e["s_from"]) / (e["s_to"] - e["s_from"])) ** 2


# ---------------------------------------------------------------------------------------------- centre line
def centreline(p=P):
    Ls, Rc = p["Ls"], p["Rc"]
    if p.get("shape") == "circle":
        return [("arc", (0.0, 0.0), -math.pi / 2, 2 * math.pi * Rc)], 2 * math.pi * Rc
    xs = p["s_start_x"]
    arc = math.pi * Rc
    parts = [("line", (xs, -Rc), (1.0, 0.0), Ls / 2 - xs),           # bottom straight to x = +Ls/2
             ("arc", (Ls / 2, 0.0), -math.pi / 2, arc),               # turn 1 (centre (+Ls/2, 0)), heading +x -> -x
             ("line", (Ls / 2, Rc), (-1.0, 0.0), Ls),                 # top straight
             ("arc", (-Ls / 2, 0.0), math.pi / 2, arc),               # turn 2
             ("line", (-Ls / 2, -Rc), (1.0, 0.0), xs + Ls / 2)]       # back to the start
    total = sum(q[3] for q in parts)
    return parts, total


def at(s, p=P):
    """-> (x, z, tx, tz, kind) at arc length s (local frame, before the world offset)"""
    parts, total = centreline(p)
    s %= total
    for kind, a, b, L in parts:
        if s <= L + 1e-9:
            if kind == "line":
                return a[0] + b[0] * s, a[1] + b[1] * s, b[0], b[1], "line"
            Rc = p["Rc"]
            ang = b + s / Rc                                          # anticlockwise in (x, z): heading turns toward n+
            x, z = a[0] + Rc * math.cos(ang), a[1] + Rc * math.sin(ang)
            return x, z, -math.sin(ang), math.cos(ang), "arc"
        s -= L
    raise AssertionError


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def pad_extra(x_local, kind, p=P):
    """extra outer width of the pad at this station (bottom straight only)"""
    if kind != "line":
        return 0.0
    return p["pad_w"] * min(smooth((x_local - p["pad_from"]) / p["pad_taper"]), smooth((p["pad_to"] - x_local) / p["pad_taper"]))


def stations(p=P):
    parts, total = centreline(p)
    n = p["n_units"] * p["st_per_unit"]
    out = []
    for i in range(n):
        s = total * i / n
        x, z, tx, tz, kind = at(s, p)
        bottom = kind == "line" and z < 0
        extra = pad_extra(x, kind, p) if bottom else 0.0
        o_in = p["Rc"] if kind == "line" and abs(abs(tz)) < 1e-9 and (abs(x) < p["Ls"] / 2 - 1e-6) else p["Rc"] - p["infield_arc_gap"]
        if p.get("shape") == "circle" or p.get("infield_strip") is not None:
            o_in = p["hw"] + p["wall_t"] + p.get("infield_strip", p.get("circle_infield", 8.0))
        out.append({"i": i, "s": s, "x": x + p["X0"], "z": z + p["Z0"], "tx": tx, "tz": tz, "kind": kind,
                    "hw_out": p["hw"] + extra, "hw_in": p["hw"], "o_in": o_in, "y": height(s, total, p)})
    return out, total


# ---------------------------------------------------------------------------------------------- textures (procedural)
def _noise(rng, w, h, base, amp):
    return [[tuple(max(0, min(255, int(c + rng.uniform(-amp, amp)))) for c in base) for _ in range(w)] for _ in range(h)]


def textures(p=P):
    n = p["tex"]
    rng = random.Random(20261027)
    tx = {}
    a = _noise(rng, n, n, (72, 72, 76), 10)                          # asphalt: edge lines + dashed centre line
    for y in range(n):
        for x in range(n):
            u = x / n
            if 0.03 < u < 0.06 or 0.94 < u < 0.97:
                a[y][x] = (225, 225, 225)
            if 0.49 < u < 0.51 and y < n // 2:
                a[y][x] = (230, 210, 60)
    tx["bm_asphalt"] = a
    c = _noise(rng, n, n, (170, 168, 160), 8)                         # pad concrete: 4 m tile with dark joints + a mark
    for y in range(n):
        for x in range(n):
            if x < 3 or y < 3:
                c[y][x] = (90, 90, 95)
            if 56 < x < 72 and 56 < y < 72:
                c[y][x] = (40, 110, 200)
    tx["bm_pad"] = c
    k = []                                                            # start line: black / white chequer 8 x 8
    for y in range(n):
        k.append([(240, 240, 240) if ((x * 8 // n) + (y * 8 // n)) % 2 else (20, 20, 20) for x in range(n)])
    tx["bm_start"] = k
    w = []                                                            # wall: red / white stripes (2 m period on u)
    for y in range(n):
        w.append([(200, 30, 30) if x < n // 2 else (235, 235, 235) for x in range(n)])
    for y in range(0, 6):
        w[y] = [(60, 60, 60)] * n
    tx["bm_wall"] = w
    g = _noise(rng, n, n, (60, 120, 45), 18)                         # grass
    tx["bm_grass"] = g
    return tx


# ---------------------------------------------------------------------------------------------- geometry
def _n_plus(st):
    return -st["tz"], st["tx"]


def _pt(st, o, y):
    nx, nz = _n_plus(st)
    return (st["x"] + nx * o, y, st["z"] + nz * o)


def build(out_dir, p=P):
    """write the source assets; -> description dict"""
    os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
    sts, total = stations(p)
    n = len(sts)
    y0, hw, t, h = p["y0"], p["hw"], p["wall_t"], p["wall_h"]
    V, VT, VN, F = [], [], [], []                                     # F: (material, [(v, vt, vn)])
    vidx, tidx, nidx = {}, {}, {}

    vk = p.get("vcol", 0.5) / 0.5                        # vertex-colour scale (brightness A/B variant)

    def v(pos, col=(0.5, 0.5, 0.5)):
        key = tuple(round(c, 4) for c in pos) + tuple(round(c * vk, 3) for c in col)
        if key not in vidx:
            V.append(key)
            vidx[key] = len(V)
        return vidx[key]

    def vt(u, w):
        key = (round(u, 5), round(w, 5))
        if key not in tidx:
            VT.append(key)
            tidx[key] = len(VT)
        return tidx[key]

    def vn(nrm):
        key = tuple(round(c, 5) for c in nrm)
        if key not in nidx:
            VN.append(key)
            nidx[key] = len(VN)
        return nidx[key]

    def face(mat, pts, uvs, nrm, col=(0.5, 0.5, 0.5)):
        cr = [0.0, 0.0, 0.0]                              # Newell normal (robust for near-degenerate quads)
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            cr[0] += (a[1] - b[1]) * (a[2] + b[2])
            cr[1] += (a[2] - b[2]) * (a[0] + b[0])
            cr[2] += (a[0] - b[0]) * (a[1] + b[1])
        if nrm is None:                                   # 0.3.0: sloped floor faces carry their own (upward) normal
            L = math.sqrt(sum(c * c for c in cr)) or 1.0
            nrm = tuple((c / L) * (1 if cr[1] >= 0 else -1) for c in cr)
        if sum(x * y for x, y in zip(cr, nrm)) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        F.append((mat, [(v(q, col), vt(*uv), vn(nrm)) for q, uv in zip(pts, uvs)]))

    for i in range(n):
        A, B = sts[i], sts[(i + 1) % n]
        sA, sB = A["s"], A["s"] + total / n
        nA, nB = _n_plus(A), _n_plus(B)
        up = (0.0, 1.0, 0.0) if not p.get("elevation") else None
        yA, yB = A["y"], B["y"]                           # 0.3.0: each station's own height (the base height when flat)
        # road (asphalt or start chequer) between -hw .. +hw
        mat = "start" if i == 0 else "asphalt"
        face(mat, [_pt(A, -hw, yA), _pt(B, -hw, yB), _pt(B, hw, yB), _pt(A, hw, yA)],
             [(0, sA / 14), (0, sB / 14), (1, sB / 14), (1, sA / 14)], up)
        # pad (concrete) between -hw_out .. -hw where the road is wider
        if A["hw_out"] > hw + 0.01 or B["hw_out"] > hw + 0.01:
            face("pad", [_pt(A, -A["hw_out"], yA), _pt(B, -B["hw_out"], yB), _pt(B, -hw, yB), _pt(A, -hw, yA)],
                 [(-A["hw_out"] / 4, sA / 4), (-B["hw_out"] / 4, sB / 4), (-hw / 4, sB / 4), (-hw / 4, sA / 4)], up)
        # walls: (side sign, inner face offset A/B)
        gap = p.get("wall_gap_st")
        in_gap = gap is not None and gap[0] <= i < gap[1]
        if in_gap:                                        # deliberate outer-wall gap (crash-test variant): floor under it
            pts = [_pt(A, -(A["hw_out"] + t), yA), _pt(B, -(B["hw_out"] + t), yB), _pt(B, -B["hw_out"], yB), _pt(A, -A["hw_out"], yA)]
            face("grass", pts, [(q[0] / 8, q[2] / 8) for q in pts], up)
        for sgn, oA, oB in ((-1, A["hw_out"], B["hw_out"]), (1, A["hw_in"], B["hw_in"])):
            if in_gap and sgn < 0:
                continue
            fa, fb = sgn * oA, sgn * oB                   # front face (towards the road)
            ba, bb = sgn * (oA + t), sgn * (oB + t)       # back face
            nf = (-sgn * (nA[0] + nB[0]) / 2, 0.0, -sgn * (nA[1] + nB[1]) / 2)
            L = math.hypot(nf[0], nf[2]) or 1.0
            nf = (nf[0] / L, 0.0, nf[2] / L)
            nb = (-nf[0], 0.0, -nf[2])
            uA, uB = sA / 4, sB / 4
            face("wall", [_pt(A, fa, yA), _pt(B, fb, yB), _pt(B, fb, yB + h), _pt(A, fa, yA + h)],
                 [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], nf)
            face("wall", [_pt(A, fa, yA + h), _pt(B, fb, yB + h), _pt(B, bb, yB + h), _pt(A, ba, yA + h)],
                 [(uA, 0.05), (uB, 0.05), (uB, 0.0), (uA, 0.0)], up, (0.45, 0.45, 0.45))
            face("wallback", [_pt(A, ba, yA), _pt(B, bb, yB), _pt(B, bb, yB + h), _pt(A, ba, yA + h)],
                 [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], nb, (0.4, 0.4, 0.4))
        # grass: outer verge and infield
        go_a, go_b = -(A["hw_out"] + t), -(B["hw_out"] + t)
        ge_a, ge_b = go_a - p["verge"], go_b - p["verge"]
        pts = [_pt(A, ge_a, yA), _pt(B, ge_b, yB), _pt(B, go_b, yB), _pt(A, go_a, yA)]
        face("grass", pts, [(q[0] / 8, q[2] / 8) for q in pts], up)
        gi_a, gi_b = A["hw_in"] + t, B["hw_in"] + t
        pts = [_pt(A, gi_a, yA), _pt(B, gi_b, yB), _pt(B, B["o_in"], yB), _pt(A, A["o_in"], yA)]
        face("grass", pts, [(q[0] / 8, q[2] / 8) for q in pts], up)

    # ---- crash-test barrier (variant only): a 2 m thick, 2 m tall box across the whole road (wall to wall) at a station
    bi = p.get("barrier_st")
    if bi is not None:
        S0 = sts[bi]
        tx_, tz_ = S0["tx"], S0["tz"]
        nx_, nz_ = _n_plus(S0)
        bh = 2.0

        def bp(along, o, y):
            return (S0["x"] + tx_ * along + nx_ * o, y, S0["z"] + tz_ * along + nz_ * o)
        lo_o, hi_o = -S0["hw_out"], S0["hw_in"]
        y0 = S0["y"]                                      # 0.3.0: the barrier stands at its station's height
        for along, nrm in ((-1.0, (-tx_, 0.0, -tz_)), (1.0, (tx_, 0.0, tz_))):      # front (faces the traffic) / back
            face("wall", [bp(along, lo_o, y0), bp(along, hi_o, y0), bp(along, hi_o, y0 + bh), bp(along, lo_o, y0 + bh)],
                 [(0, 1), (3.5, 1), (3.5, 0), (0, 0)], nrm)
        face("wall", [bp(-1.0, lo_o, y0 + bh), bp(-1.0, hi_o, y0 + bh), bp(1.0, hi_o, y0 + bh), bp(1.0, lo_o, y0 + bh)],
             [(0, 0.05), (3.5, 0.05), (3.5, 0), (0, 0)], (0.0, 1.0, 0.0), (0.45, 0.45, 0.45))

    # ---- OBJ
    lines = ["# BM Test Loop - ORIGINAL procedural geometry (trackbuild.testloop). Y up, metres, B3 game frame.",
             "# vertex lines carry an RGB colour extension (baked light, 0.5 = neutral)", "mtllib test_loop.mtl"]
    lines += ["v %.4f %.4f %.4f %.3f %.3f %.3f" % q for q in V]
    lines += ["vt %.5f %.5f" % q for q in VT]
    lines += ["vn %.5f %.5f %.5f" % q for q in VN]
    cur = None
    for mat, fv in F:
        if mat != cur:
            lines.append("usemtl %s" % mat)
            cur = mat
        lines.append("f " + " ".join("%d/%d/%d" % x for x in fv))
    with open(os.path.join(out_dir, "test_loop.obj"), "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    tex = textures(p)
    mtl = []
    for name, rgb in sorted(tex.items()):
        dxt.write_png(os.path.join(out_dir, "textures", name + ".png"), p["tex"], p["tex"], rgb)
    for mat, tn in (("asphalt", "bm_asphalt"), ("pad", "bm_pad"), ("start", "bm_start"), ("wall", "bm_wall"), ("wallback", "bm_wall"),
                    ("grass", "bm_grass")):
        mtl += ["newmtl %s" % mat, "map_Kd textures/%s.png" % tn, ""]
    with open(os.path.join(out_dir, "test_loop.mtl"), "w", newline="\n") as fh:
        fh.write("\n".join(mtl))

    # ---- description
    route_offsets = []
    for st in sts:                       # node offsets along n+, node0 side first (outside -> infield)
        route_offsets.append([-(st["hw_out"] + t + p["verge"]), -st["hw_out"], -(hw - 1.0), hw - 1.0, st["hw_in"], st["hw_in"] + t + 8.0])
    sps = p["st_per_slice"]
    slices = n // sps
    units = []
    for k in range(p["n_units"]):
        a, b = k * p["st_per_unit"], ((k + 1) * p["st_per_unit"]) % n
        units.append({"cut_from": a, "cut_to": b})
    # lateral bounds of each unit from its stations' extreme offsets, projected on the unit chord normal
    for u in units:
        A, B = sts[u["cut_from"]], sts[u["cut_to"]]
        cx, cz = B["x"] - A["x"], B["z"] - A["z"]
        L = math.hypot(cx, cz)
        mx, mz = -cz / L, cx / L
        lo, hi = 1e9, -1e9
        j = u["cut_from"]
        while True:
            st = sts[j % n]
            for o in (-(st["hw_out"] + t + p["verge"]), st["o_in"]):
                q = _pt(st, o, y0)
                d = (q[0] - A["x"]) * mx + (q[2] - A["z"]) * mz
                lo, hi = min(lo, d), max(hi, d)
            if j % n == u["cut_to"]:
                break
            j += 1
        u["lateral"] = [round(lo - 0.25, 4), round(hi + 0.25, 4)]
        u["chord_normal"] = [mx, mz]
    # start grid: 2 columns x 3 rows behind the start line (station 0), facing +t
    st0 = sts[0]
    grid = []
    for r in range(3):
        for c, o in enumerate((-2.0, 2.0)):          # +-2 m (0.1.5): +-3 m let the init search pick the edge lane on the ring
            back = 12.0 + 8.0 * r + (4.0 if c else 0.0)
            gx, gz, gtx, gtz, _ = at(-back, p)              # ON the centre line (a straight-line offset drifts on a ring)
            x = gx + p["X0"] + (-gtz) * o
            z = gz + p["Z0"] + gtx * o
            grid.append({"pos": [round(x, 3), height(-back, total, p) + 0.5, round(z, 3)], "fwd": [round(gtx, 6), 0.0, round(gtz, 6)]})
    checkpoints = []
    for k in range(1, 7):
        st = sts[(k * n) // 7]
        checkpoints.append({"pos": [round(st["x"], 3), st["y"], round(st["z"], 3)], "normal": [st["tx"], 0.0, st["tz"]], "width": 45.0})
    corners = []
    if p.get("shape") == "circle":                    # a constant-radius ring: four quarter-turn corner records
        for q in range(4):
            first, last = q * slices // 4, (q + 1) * slices // 4 - 1
            corners.append({"first": first, "apex": (first + last) // 2, "last": last, "radius": p["Rc"],
                            "turn": "toward_n_plus", "degrees": 90})
    for arc_start in (() if p.get("shape") == "circle" else
                      (p["Ls"] / 2 - p["s_start_x"], p["Ls"] / 2 - p["s_start_x"] + math.pi * p["Rc"] + p["Ls"])):
        sl = total / slices
        first = int(arc_start / sl) - 2
        last = int((arc_start + math.pi * p["Rc"]) / sl)
        corners.append({"first": first, "apex": (first + 2 + last) // 2, "last": last, "radius": p["Rc"], "turn": "toward_n_plus",
                        "degrees": 180})
    desc = {
        "format": "trackbuild.track/1", "label": "AUTHORED", "name": p.get("name", "BM Test Loop"),
        "generator": {"module": "trackbuild.testloop", "params": p},
        "obj": "test_loop.obj",
        "materials": {
            "asphalt": {"texture": "textures/bm_asphalt.png", "surface": "0x0001", "collide": True},
            "start": {"texture": "textures/bm_start.png", "surface": "0x0001", "collide": True},
            "pad": {"texture": "textures/bm_pad.png", "surface": "0x0002", "collide": True},
            # road-facing walls: a word WITHOUT flag 0x10 (0x10 = excluded from the car's query; gp_trk_1: the car passed
            # through 0x181C walls). Retail: road-facing faces 0x0018 / 0x0124 / 0x081A ..., outer faces 0x1018 / 0x1816.
            "wall": {"texture": "textures/bm_wall.png", "surface": "0x0018", "collide": True},
            "wallback": {"texture": "textures/bm_wall.png", "surface": "0x1018", "collide": True, "car_solid": False},
            "grass": {"texture": "textures/bm_grass.png", "surface": "0x000F", "collide": True}},
        "rows": ["asphalt", "start", "pad", "grass", "wall", "wallback"],
        "stations": [{"p": [round(s_["x"], 4), round(s_["y"], 4), round(s_["z"], 4)], "t": [round(s_["tx"], 6), round(s_["tz"], 6)],
                      "offsets": [round(o, 4) for o in route_offsets[s_["i"]]]} for s_ in sts],
        "loop_length": total, "closed": True,
        "units": units, "stations_per_slice": sps,
        "route": {"lanes": [{"name": "corridor_out", "type": 5}, {"name": "edge_out", "type": 4},
                            {"name": "main", "type": 0x80}, {"name": "edge_in", "type": 4}, {"name": "corridor_in", "type": 5}],
                  "corners": corners},
        "grid": grid, "start_line": {"pos": [round(st0["x"], 3), st0["y"], round(st0["z"], 3)], "normal": [st0["tx"], 0.0, st0["tz"]],
                                     "width": 45.0},
        "checkpoints": checkpoints,
        "traffic": None if not p.get("traffic", True) else {
            # AUTHORED traffic (0.1.3): two same-way lanes on the 14 m road, open (retail lanes are open), nodes every 3
            # stations (6 m) from station 30 to station 330; online whole-track set (flags 3). Flows = vehicles per minute
            # per class (retail ONSGRCF lane flows 1.3-2.3 / 2.3-3.6 / 0 / 0.2-0.5). Vehicle IDs name retail traffic models.
            "lanes": [{"offset": -3.5, "width": 6.0, "speed": 30.0, "flow": [1.5, 2.5, 0.0, 0.3, 0.0, 0.0]},
                      {"offset": 3.5, "width": 6.0, "speed": 30.0, "flow": [1.5, 2.5, 0.0, 0.3, 0.0, 0.0]}],
            "node_stations": 3, "first_station": 30 * n // 357, "last_station": 330 * n // 357 // 3 * 3 + (30 * n // 357) % 3,
            "spawn_points": [[0, 5], [1, 30], [0, 55], [1, 80]],
            "vehicles": [["COMPCAR11", "COMPCAR12"], ["HEVYCAR11", "HEVYCAR12", "HEVYCAR13", "HEVYCAR14", "HEVYCAR15", "HEVYCAR34"],
                         [], [], ["HEVYCAR23"], ["HEVYCAR24", "HEVYCAR27"]]},
        "gamedata_header": p.get("gamedata_header", "donor"),
        "pvs": {"mode": p.get("pvs", "all")},
        # 0.1.4: decimated LOD (bounded error 0.3 m; outline / material borders 0.05 m); lod_tint = diagnostic variant only
        "lod": {"mode": "decimate", "e_max": 0.3, "e_border": 0.05, "debug_tint": p.get("lod_tint")},
        "wall_gaps": [list(p["wall_gap_st"])] if p.get("wall_gap_st") else [],
        "barrier_station": p.get("barrier_st")}
    with open(os.path.join(out_dir, "test_loop.track.json"), "w", newline="\n") as fh:
        json.dump(desc, fh, indent=1)
    return {"faces": len(F), "vertices": len(V), "stations": n, "units": len(units), "slices": slices, "length": total}
