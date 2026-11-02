"""trackbuild.fig8 (0.3.3-rta) - the ORIGINAL procedural multi-level test track "BM Figure-8 Bridge" (AUTHORED, no game data).

Shape: two circles of radius R centred at (+-D, 0) joined by their two internal common tangents, which cross at the origin at
2 * asin(R / D) (73.7 deg for R 120 / D 200). Lap: straight L1 (start, ground level) -> right lobe (clockwise) -> straight L2
(the BRIDGE: +H over the crossing, sin^2 ramps) -> left lobe (anticlockwise). Road 14 m, 1.5 m walls, 10 m verges.
Multi-level rule (rta4 evidence, RTA phase 4 MULTI_LEVEL.md): the game's unit lookup sub_001AD4A0 returns the FIRST unit region
holding the point (plan-only, +-4 window, XC); retail puts BOTH decks into every unit whose region holds a crossing
(AS/M1, EU/C1, EU/C2, EU/M1). The kit's plan assignment (units.assign) does exactly that, so the description only DECLARES the
crossing (desc["levels"]); the validator then requires every holder of a route sample to carry the floor at the route's own
height and >= 5.5 m clearance under any floor above.
Elevated stations (> 0.3 m above ground): no verge faces; outer skirts (non-solid wallback word) from the wall back down to the
ground, except within `span_clear` metres (plan) of the lower road (an open span); a deck underside (non-solid) 1 m below.
RUNTIME-UNVERIFIED: driving under / over the bridge, respawn level, camera, AI on both levels."""
import json
import math
import os

from . import dxt
from . import testloop as TL

P8 = dict(name="BM Figure-8 Bridge", R=120.0, D=200.0, hw=7.0, wall_t=0.6, wall_h=1.5, verge=10.0, y0=20.0, X0=-6000.0,
          Z0=-6000.0, n_units=17, st_per_slice=3, step=2.0, H=8.0, plateau=50.0, ramp=150.0, deck_t=1.0, span_clear=20.0,
          start_s=100.0, tex=128, vcol=0.2)


def parts(p=P8):
    R, D = p["R"], p["D"]
    phi = math.asin(R / D)
    c, s = math.cos(phi), math.sin(phi)
    Ls = 2 * D * c
    arc = R * (math.pi + 2 * phi)
    return phi, [("line", (-D * c * c, -D * c * s), (c, s), Ls),                       # L1 (ground)
                 ("arc", (D, 0.0), math.pi / 2 + phi, -1.0, arc),                     # right lobe, clockwise
                 ("line", (D * c * c, -D * c * s), (-c, s), Ls),                      # L2 (bridge)
                 ("arc", (-D, 0.0), -math.pi / 2 - phi + math.pi, 1.0, arc)]          # left lobe, anticlockwise


def at(sv, p=P8):
    _phi, ps = parts(p)
    total = sum(q[-1] for q in ps)
    sv %= total
    for q in ps:
        if sv <= q[-1] + 1e-9:
            if q[0] == "line":
                a, d = q[1], q[2]
                return a[0] + d[0] * sv, a[1] + d[1] * sv, d[0], d[1], "line"
            cen, a0, sg = q[1], q[2], q[3]
            ang = a0 + sg * sv / p["R"]
            x, z = cen[0] + p["R"] * math.cos(ang), cen[1] + p["R"] * math.sin(ang)
            return x, z, -sg * math.sin(ang), sg * math.cos(ang), "arc"
        sv -= q[-1]
    raise AssertionError


def total_len(p=P8):
    return sum(q[-1] for q in parts(p)[1])


def bridge_centre(p=P8):
    _phi, ps = parts(p)
    return ps[0][-1] + ps[1][-1] + ps[2][-1] / 2


def height(sv, p=P8):
    L = total_len(p)
    d = abs(((sv - bridge_centre(p)) + L / 2) % L - L / 2)
    if d <= p["plateau"]:
        f = 1.0
    elif d >= p["plateau"] + p["ramp"]:
        f = 0.0
    else:
        f = math.cos(math.pi / 2 * (d - p["plateau"]) / p["ramp"]) ** 2
    return p["y0"] + p["H"] * f


def _dist_to_L1(x, z, p=P8):
    _phi, ps = parts(p)
    a, d, Ls = ps[0][1], ps[0][2], ps[0][-1]
    t = max(0.0, min(Ls, (x - a[0]) * d[0] + (z - a[1]) * d[1]))
    return math.hypot(x - (a[0] + d[0] * t), z - (a[1] + d[1] * t))


def build(out_dir, p=P8):
    os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
    L = total_len(p)
    sps = p["st_per_slice"]
    spu = sps * max(1, int(round(L / (p["n_units"] * p["step"] * sps))))
    n = p["n_units"] * spu
    hw, t, h, vg, y0 = p["hw"], p["wall_t"], p["wall_h"], p["verge"], p["y0"]
    st = []
    for i in range(n):
        sv = L * i / n
        x, z, tx, tz, kind = at(sv, p)
        st.append({"i": i, "s": sv, "x": x + p["X0"], "z": z + p["Z0"], "lx": x, "lz": z, "tx": tx, "tz": tz, "y": height(sv, p)})
    V, VT, VN, F = [], [], [], []
    vidx, tidx, nidx = {}, {}, {}
    vk = p["vcol"] / 0.5

    def v(pos, col):
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

    def face(mat, pts, uvs, nrm=None, col=(0.5, 0.5, 0.5), want_up=None):
        cr = [0.0, 0.0, 0.0]
        for k in range(len(pts)):
            a, b = pts[k], pts[(k + 1) % len(pts)]
            cr[0] += (a[1] - b[1]) * (a[2] + b[2])
            cr[1] += (a[2] - b[2]) * (a[0] + b[0])
            cr[2] += (a[0] - b[0]) * (a[1] + b[1])
        Ln = math.sqrt(sum(c * c for c in cr))
        if Ln < 1e-6:
            return
        if nrm is None:
            sgn = 1 if (cr[1] >= 0) == (want_up is not False) else -1
            nrm = tuple(c / Ln * sgn for c in cr)
        if sum(x * y for x, y in zip(cr, nrm)) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        F.append((mat, [(v(q, col), vt(*uv), vn(nrm)) for q, uv in zip(pts, uvs)]))

    def pt(S, o, y):
        return (S["x"] - S["tz"] * o, y, S["z"] + S["tx"] * o)

    elev = [S["y"] - y0 > 0.3 for S in st]
    open_span = [elev[i] and _dist_to_L1(st[i]["lx"], st[i]["lz"], p) < p["span_clear"] for i in range(n)]
    start_i = int(round(p["start_s"] / L * n / spu)) * spu        # whole units: unit 0 starts at the start line
    start_s = L * start_i / n
    for i in range(n):
        A, B = st[i], st[(i + 1) % n]
        sA, sB = A["s"], A["s"] + L / n
        yA, yB = A["y"], B["y"]
        face("start" if i == start_i else "asphalt", [pt(A, -hw, yA), pt(B, -hw, yB), pt(B, hw, yB), pt(A, hw, yA)],
             [(0, sA / 14), (0, sB / 14), (1, sB / 14), (1, sA / 14)])
        nA = (-A["tz"], A["tx"])
        nB = (-B["tz"], B["tx"])
        for sgn in (-1, 1):
            fa = sgn * hw
            ba = sgn * (hw + t)
            nf = (-sgn * (nA[0] + nB[0]) / 2, 0.0, -sgn * (nA[1] + nB[1]) / 2)
            Lf = math.hypot(nf[0], nf[2]) or 1.0
            nf = (nf[0] / Lf, 0.0, nf[2] / Lf)
            nb = (-nf[0], 0.0, -nf[2])
            uA, uB = sA / 4, sB / 4
            face("wall", [pt(A, fa, yA), pt(B, fa, yB), pt(B, fa, yB + h), pt(A, fa, yA + h)], [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], nf)
            face("wall", [pt(A, fa, yA + h), pt(B, fa, yB + h), pt(B, ba, yB + h), pt(A, ba, yA + h)], [(uA, 0.05), (uB, 0.05), (uB, 0), (uA, 0)],
                 None, (0.45, 0.45, 0.45))
            face("wallback", [pt(A, ba, yA), pt(B, ba, yB), pt(B, ba, yB + h), pt(A, ba, yA + h)], [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], nb,
                 (0.4, 0.4, 0.4))
            if not (elev[i] or elev[(i + 1) % n]):
                o0, o1 = sgn * (hw + t), sgn * (hw + t + vg)
                pts = [pt(A, o0, yA), pt(B, o0, yB), pt(B, o1, yB), pt(A, o1, yA)]
                face("grass", pts, [(q[0] / 8, q[2] / 8) for q in pts])
            elif not (open_span[i] or open_span[(i + 1) % n]):        # embankment skirt down to the ground
                face("wallback", [pt(A, ba, y0), pt(B, ba, y0), pt(B, ba, yB), pt(A, ba, yA)], [(uA, 1), (uB, 1), (uB, 0), (uA, 0)], nb,
                     (0.4, 0.4, 0.4))
        if elev[i] and elev[(i + 1) % n]:                                # deck underside (seen from the lower road)
            dt = p["deck_t"]
            face("wallback", [pt(A, -(hw + t), yA - dt), pt(B, -(hw + t), yB - dt), pt(B, hw + t, yB - dt), pt(A, hw + t, yA - dt)],
                 [(0, 0), (1, 0), (1, 1), (0, 1)], None, (0.35, 0.35, 0.35), want_up=False)
            if open_span[i] != open_span[(i + 1) % n]:                   # abutment face across the deck end
                E = B if open_span[(i + 1) % n] else A
                ye = E["y"]
                face("wallback", [pt(E, -(hw + t), y0), pt(E, hw + t, y0), pt(E, hw + t, ye - dt), pt(E, -(hw + t), ye - dt)],
                     [(0, 1), (1, 1), (1, 0), (0, 0)], None, (0.4, 0.4, 0.4))
    # OBJ
    lines = ["# BM Figure-8 Bridge - ORIGINAL procedural geometry (trackbuild.fig8). Y up, metres, B3 game frame.", "mtllib fig8.mtl"]
    lines += ["v %.4f %.4f %.4f %.3f %.3f %.3f" % q for q in V]
    lines += ["vt %.5f %.5f" % q for q in VT]
    lines += ["vn %.5f %.5f %.5f" % q for q in VN]
    cur = None
    for mat, fv in F:
        if mat != cur:
            lines.append("usemtl %s" % mat)
            cur = mat
        lines.append("f " + " ".join("%d/%d/%d" % x for x in fv))
    with open(os.path.join(out_dir, "fig8.obj"), "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    tp = dict(TL.P, tex=p["tex"])
    tex = TL.textures(tp)
    for name, rgb in sorted(tex.items()):
        dxt.write_png(os.path.join(out_dir, "textures", name + ".png"), p["tex"], p["tex"], rgb)
    mtl = []
    for mat, tn in (("asphalt", "bm_asphalt"), ("start", "bm_start"), ("wall", "bm_wall"), ("wallback", "bm_wall"), ("grass", "bm_grass")):
        mtl += ["newmtl %s" % mat, "map_Kd textures/%s.png" % tn, ""]
    with open(os.path.join(out_dir, "fig8.mtl"), "w", newline="\n") as fh:
        fh.write("\n".join(mtl))
    # description
    offs = [[-(hw + t + vg), -hw, -(hw - 1.0), hw - 1.0, hw, hw + t + vg] for _ in st]
    units = []
    for k in range(p["n_units"]):
        a, b = k * spu, ((k + 1) * spu) % n
        A, B = st[a], st[b]
        cx, cz = B["x"] - A["x"], B["z"] - A["z"]
        Lc = math.hypot(cx, cz)
        mx, mz = -cz / Lc, cx / Lc
        lo, hi = 1e9, -1e9
        j = a
        while True:
            S = st[j % n]
            for o in (-(hw + t + vg), hw + t + vg):
                q = pt(S, o, y0)
                d = (q[0] - A["x"]) * mx + (q[2] - A["z"]) * mz
                lo, hi = min(lo, d), max(hi, d)
            if j % n == b:
                break
            j += 1
        units.append({"cut_from": a, "cut_to": b, "lateral": [round(lo - 0.25, 4), round(hi + 0.25, 4)], "chord_normal": [mx, mz]})
    S0 = st[start_i]
    grid = []
    for r in range(3):
        for c, o in enumerate((-2.0, 2.0)):
            back = 12.0 + 8.0 * r + (4.0 if c else 0.0)
            gx, gz, gtx, gtz, _ = at(start_s - back, p)
            grid.append({"pos": [round(gx + p["X0"] - gtz * o, 3), height(start_s - back, p) + 0.5, round(gz + p["Z0"] + gtx * o, 3)],
                         "fwd": [round(gtx, 6), 0.0, round(gtz, 6)]})
    cps = []
    for k in range(1, 7):
        j = (start_i + (k * n) // 7) % n
        while _dist_to_L1(st[j]["lx"], st[j]["lz"], p) < 60.0 and abs(st[j]["lx"]) < 60.0:   # keep lap lines off the crossing
            j = (j + spu // 3) % n
        S = st[j]
        cps.append({"pos": [round(S["x"], 3), S["y"], round(S["z"], 3)], "normal": [S["tx"], 0.0, S["tz"]], "width": 45.0})
    phi, ps = parts(p)
    slices = n // sps
    corners = []
    acc = 0.0
    for q in ps:
        if q[0] == "arc":
            first = int(acc / L * slices) - 2
            last = int((acc + q[-1]) / L * slices)
            corners.append({"first": first, "apex": (first + 2 + last) // 2, "last": last, "radius": p["R"],
                            "turn": "toward_n_plus" if q[3] > 0 else "toward_n_minus", "degrees": round(math.degrees(math.pi + 2 * phi), 1)})
        acc += q[-1]
    # rotate the station list so that station 0 = the start line (route slice 0 = the start, as the test loop)
    rot = start_i
    st = st[rot:] + st[:rot]
    offs = offs[rot:] + offs[:rot]
    ku = rot // spu
    units = units[ku:] + units[:ku]
    units = [{"cut_from": (u["cut_from"] - rot) % n, "cut_to": (u["cut_to"] - rot) % n, "lateral": u["lateral"],
              "chord_normal": u["chord_normal"]} for u in units]
    sh = rot // sps
    corners = [dict(c, first=(c["first"] - sh) % slices, apex=(c["apex"] - sh) % slices, last=(c["last"] - sh) % slices) for c in corners]
    for c in corners:
        if c["last"] < c["first"]:
            c["last"] += slices
        if c["apex"] < c["first"]:
            c["apex"] += slices
    cross_s = [(math.fmod(ps[0][-1] / 2 - start_s + L, L)), math.fmod(bridge_centre(p) - start_s + L, L)]
    desc = {
        "format": "trackbuild.track/1", "label": "AUTHORED", "name": p["name"], "generator": {"module": "trackbuild.fig8", "params": p},
        "obj": "fig8.obj",
        "materials": {
            "asphalt": {"texture": "textures/bm_asphalt.png", "surface": "0x0001", "collide": True},
            "start": {"texture": "textures/bm_start.png", "surface": "0x0001", "collide": True},
            "wall": {"texture": "textures/bm_wall.png", "surface": "0x0018", "collide": True},
            "wallback": {"texture": "textures/bm_wall.png", "surface": "0x1018", "collide": True, "car_solid": False},
            "grass": {"texture": "textures/bm_grass.png", "surface": "0x000F", "collide": True}},
        "rows": ["asphalt", "start", "grass", "wall", "wallback"],
        "stations": [{"p": [round(S["x"], 4), round(S["y"], 4), round(S["z"], 4)], "t": [round(S["tx"], 6), round(S["tz"], 6)],
                      "offsets": [round(o, 4) for o in offs[k]]} for k, S in enumerate(st)],
        "loop_length": L, "closed": True, "units": units, "stations_per_slice": sps,
        "route": {"lanes": [{"name": "corridor_out", "type": 5}, {"name": "edge_out", "type": 4}, {"name": "main", "type": 0x80},
                            {"name": "edge_in", "type": 4}, {"name": "corridor_in", "type": 5}], "corners": corners},
        "grid": grid, "start_line": {"pos": [round(S0["x"], 3), S0["y"], round(S0["z"], 3)], "normal": [S0["tx"], 0.0, S0["tz"]], "width": 45.0},
        "checkpoints": cps,
        "traffic": {"lanes": [{"offset": -3.5, "width": 6.0, "speed": 30.0, "flow": [1.5, 2.5, 0.0, 0.3, 0.0, 0.0]},
                              {"offset": 3.5, "width": 6.0, "speed": 30.0, "flow": [1.5, 2.5, 0.0, 0.3, 0.0, 0.0]}],
                    "node_stations": 3, "first_station": 30, "last_station": n - 30 - (n - 60) % 3,
                    "spawn_points": [[0, 5], [1, 30], [0, 55], [1, 80]],
                    "vehicles": [["COMPCAR11", "COMPCAR12"], ["HEVYCAR11", "HEVYCAR12", "HEVYCAR13", "HEVYCAR14", "HEVYCAR15", "HEVYCAR34"],
                                 [], [], ["HEVYCAR23"], ["HEVYCAR24", "HEVYCAR27"]]},
        "gamedata_header": "donor", "pvs": {"mode": "all"},
        "lod": {"mode": "decimate", "e_max": 0.3, "e_border": 0.05, "debug_tint": None},
        "wall_gaps": [], "barrier_station": None,
        "levels": {"crossings": [{"lower_s_m": round(cross_s[0], 2), "upper_s_m": round(cross_s[1], 2), "deck_height_m": p["H"],
                                  "deck_thickness_m": p["deck_t"], "rule": "both decks in every holding unit (retail; kit plan assignment)"}]}}
    with open(os.path.join(out_dir, "fig8.track.json"), "w", newline="\n") as fh:
        json.dump(desc, fh, indent=1)
    return {"faces": len(F), "vertices": len(V), "stations": n, "units": len(units), "slices": slices, "length": L,
            "crossing_angle_deg": round(math.degrees(2 * phi), 1), "elevated_stations": sum(elev), "open_span_stations": sum(open_span)}
