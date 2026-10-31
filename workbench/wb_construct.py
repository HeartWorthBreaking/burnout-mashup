"""wb_construct - Workbench v0.23..v0.26 construction geometry (gp\\workbench, 2026-10-29). Pure functions: no file or kit access.

Everything here produces SOURCE data for the kit's trackbuild (0.2 schema; v0.28: bound to 0.3.0) (docs\\ADVANCED.md s3): faces for the OBJ (material, corners
with position / uv / normal / colour) and description values (stations, units, route corners, grid, start line, checkpoints,
traffic). wb_trackedit.TrackSource applies them (preview key, exact re-read, clip check, the kit's build_units dry run, one undo
entry, transactional save). Conventions = trackbuild / the demo generator (trackbuild.testloop): Y up, metres, lateral axis
n+ = (-tz, tx), faces wound so cross(b - a, c - a) points along the normal, vertex colour 0.2 = neutral brightness.

Kit limits that shape this module (facts from the kit source, not guesses):
- V2_drivable_coverage samples wall to wall along every station and requires the floor within 0.05 m of station 0's height:
  a drivable ROUTE must be flat (one height). Roads off the route may have elevation. trackbuild 0.3.0 (main21 patch 66)
  compares with the ROUTE height at each sample instead (stations interpolated; route_samples), so a route may climb; the
  race layout generator here still builds one height.
- V2_walls_hold probes car-solid walls at station offsets[1] / [4] (inner wall faces): a route needs walls on both sides.
- build_units: 4..17 units with pvs "all" (4..162 computed), mesh / LOD block slots 0x28000 / 0x18000, regions convex, neighbours
  share one negated cut lane (units tile the loop in order).
- route: stations_per_slice divides the station count; 5 lanes (corridor / edge / main / edge / corridor) need 6 offsets.
"""
import math

VCOL = 0.2                                     # demo neutral vertex colour (trackbuild.testloop vcol 0.2)
LANES = [{"name": "corridor_out", "type": 5}, {"name": "edge_out", "type": 4}, {"name": "main", "type": 0x80},
         {"name": "edge_in", "type": 4}, {"name": "corridor_in", "type": 5}]          # = the demo route (runtime-validated)
CORNER_MIN_DEG = 20.0                          # a run of curved slices turning at least this much becomes a corner record
CORNER_RADIUS_MAX = 200.0                      # slices with a larger radius count as straight


class ConstructError(Exception):
    pass


def need(c, msg):
    if not c:
        raise ConstructError(msg)


# ------------------------------------------------------------------ curves
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def check_points(points, closed, lo=2):
    need(isinstance(points, list) and len(points) >= (3 if closed else lo) and len(points) <= 512,
         'control points: a list of %d..512 [x, y, z] points (metres)' % (3 if closed else lo))
    out = []
    for i, p in enumerate(points):
        need(isinstance(p, (list, tuple)) and len(p) == 3 and all(_num(v) for v in p) and max(abs(v) for v in p) < 1e6,
             'control point %d: [x, y, z] finite numbers in metres' % i)
        out.append([float(v) for v in p])
    for i in range(len(out) - (0 if closed else 1)):
        a, b = out[i], out[(i + 1) % len(out)]
        need(math.hypot(b[0] - a[0], b[2] - a[2]) >= 1.0, 'control points %d and %d are closer than 1 m in plan' % (i, (i + 1) % len(out)))
    return out


def _cr(p0, p1, p2, p3, t):
    """centripetal Catmull-Rom (alpha 0.5) between p1 and p2"""
    def tj(ti, a, b):
        return ti + max(1e-9, math.dist(a, b)) ** 0.5
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    u = t1 + (t2 - t1) * t

    def lerp(a, b, ta, tb):
        return [(tb - u) / (tb - ta) * a[k] + (u - ta) / (tb - ta) * b[k] for k in range(3)]
    A1, A2, A3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
    B1, B2 = lerp(A1, A2, t0, t2), lerp(A2, A3, t1, t3)
    return lerp(B1, B2, t1, t2)


def sample(points, closed, step=None, count=None):
    """control points -> points spaced evenly by arc length along a centripetal Catmull-Rom curve through them (a closed loop
    returns `count` points, the first = control point 0; an open curve includes both ends). -> (points, length)"""
    P = points
    n = len(P)
    seg = n if closed else n - 1
    dense = []
    for i in range(seg):
        p0 = P[(i - 1) % n] if closed or i > 0 else [2 * P[0][k] - P[1][k] for k in range(3)]
        p1, p2 = P[i], P[(i + 1) % n]
        p3 = P[(i + 2) % n] if closed or i + 2 < n else [2 * P[-1][k] - P[-2][k] for k in range(3)]
        m = max(8, int(math.dist(p1, p2) / 0.25))
        for j in range(m):
            dense.append(_cr(p0, p1, p2, p3, j / m))
    if not closed:
        dense.append(list(P[-1]))
    else:
        dense.append(list(P[0]))
    acc = [0.0]
    for i in range(1, len(dense)):
        acc.append(acc[-1] + math.dist(dense[i - 1], dense[i]))
    L = acc[-1]
    need(L > 2.0, 'the curve is shorter than 2 m')
    if count is None:
        count = max(2, int(round(L / step))) + (0 if closed else 1)
    k, out = 0, []
    N = count if closed else count - 1
    for i in range(count):
        s = L * i / N
        while k + 1 < len(acc) - 1 and acc[k + 1] < s:
            k += 1
        f = 0.0 if acc[k + 1] == acc[k] else (s - acc[k]) / (acc[k + 1] - acc[k])
        out.append([dense[k][j] + (dense[k + 1][j] - dense[k][j]) * f for j in range(3)])
    return out, L


def tangents(S, closed):
    out = []
    n = len(S)
    for i in range(n):
        a = S[(i - 1) % n] if closed or i > 0 else S[i]
        b = S[(i + 1) % n] if closed or i < n - 1 else S[i]
        tx, tz = b[0] - a[0], b[2] - a[2]
        L = math.hypot(tx, tz)
        need(L > 1e-9, 'the curve doubles back on itself at sample %d' % i)
        out.append([tx / L, tz / L])
    return out


def _seg_x(a, b, c, d):
    """proper intersection of segments ab, cd in plan"""
    def o(p, q, r):
        return (q[0] - p[0]) * (r[2] - p[2]) - (q[2] - p[2]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def self_intersections(S, closed, skip=2):
    n = len(S)
    m = n if closed else n - 1
    hits = []
    for i in range(m):
        for j in range(i + skip, m):
            if closed and (j + 1) % n == i:
                continue
            if _seg_x(S[i], S[(i + 1) % n], S[j], S[(j + 1) % n]):
                hits.append((i, j))
                if len(hits) > 3:
                    return hits
    return hits


def min_radius(S, closed):
    """smallest turning radius in plan (circumradius of consecutive samples) -> (radius, index)"""
    best = (float('inf'), 0)
    n = len(S)
    for i in range(n if closed else n - 2):
        a, b, c = S[i], S[(i + 1) % n], S[(i + 2) % n]
        ab, bc, ca = math.hypot(b[0] - a[0], b[2] - a[2]), math.hypot(c[0] - b[0], c[2] - b[2]), math.hypot(a[0] - c[0], a[2] - c[2])
        cr = abs((b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0]))
        if cr > 1e-12:
            best = min(best, (ab * bc * ca / (2 * cr), (i + 1) % n))
    return best


def _np(t):
    return (-t[1], t[0])


def offset_pt(p, t, o, y=None):
    n = _np(t)
    return (p[0] + n[0] * o, p[1] if y is None else y, p[2] + n[1] * o)


# ------------------------------------------------------------------ faces
def newell(P):
    n = [0.0, 0.0, 0.0]
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    L = math.sqrt(sum(x * x for x in n))
    return [x / L for x in n] if L > 0 else None


def face(mat, pts, uvs, want=None, col=None):
    """one face (3 or 4 corners) with its Newell normal; `want` = a direction the normal must agree with (the face is reversed
    otherwise, as trackbuild.testloop does)"""
    nrm = newell(pts)
    need(nrm is not None, 'a generated %s face is degenerate' % mat)
    if want is not None and sum(a * b for a, b in zip(nrm, want)) < 0:
        pts, uvs = pts[::-1], uvs[::-1]
        nrm = [-x for x in nrm]
    c = col or (VCOL, VCOL, VCOL)
    return (mat, [(tuple(p), tuple(uv), tuple(nrm), tuple(c)) for p, uv in zip(pts, uvs)])


def road_strip(S, T, closed, width, mat, uv_len=14.0, shoulder=None):
    """a road strip: one quad per sample step, -width/2 .. +width/2 across n+; uv u = 0 (n- side) .. 1 (n+ side), v = distance
    along / uv_len. Normal = each quad's Newell normal (facing up). Refused when the inner edge would fold (a radius under half
    the width) or the strip crosses itself."""
    need(_num(width) and 2.0 <= width <= 60.0, 'road width %r: 2..60 m' % (width,))
    need(_num(uv_len) and 0.5 <= uv_len <= 200, 'uv length %r: 0.5..200 m per texture repeat' % (uv_len,))
    hw = width / 2.0
    r, at = min_radius(S, closed)
    need(r > hw * 1.25, 'the curve turns too tightly for a %.1f m road: radius %.1f m at sample %d (at least %.1f m: the inner '
         'edge would fold over)' % (width, r, at, hw * 1.25))
    x = self_intersections(S, closed)
    need(not x, 'the road crosses itself (segments %s): unsupported (no junctions / bridges)' % x[:2])
    n = len(S)
    s = [0.0]
    for i in range(1, n + (1 if closed else 0)):
        s.append(s[-1] + math.dist(S[i - 1], S[i % n]))
    out = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        A, B, TA, TB = S[i], S[j], T[i], T[j]
        pts = [offset_pt(A, TA, -hw), offset_pt(B, TB, -hw), offset_pt(B, TB, hw), offset_pt(A, TA, hw)]
        uvs = [(0, s[i] / uv_len), (0, s[i + 1] / uv_len), (1, s[i + 1] / uv_len), (1, s[i] / uv_len)]
        f = face(mat, pts, uvs, want=(0, 1, 0))
        need(f[1][0][2][1] > 0.2, 'the road strip is steeper than 78 degrees at sample %d' % i)
        out.append(f)
    return out, s[-1]


def wall_strip(S, T, closed, offset, side, height, thick, front, back, top=None, y=None):
    """a wall along the curve whose road-facing face stands at lateral `offset` (n+), the wall body extending `side` (+1 towards
    n+, -1 towards n-) by `thick`: front face (material `front`, facing the road), top (material `top` or `front`), back face
    (material `back`, facing away). Heights from the sample's y (or `y`)."""
    need(_num(height) and 0.3 <= height <= 30, 'wall height %r: 0.3..30 m' % (height,))
    need(_num(thick) and 0.1 <= thick <= 5, 'wall thickness %r: 0.1..5 m' % (thick,))
    need(side in (1, -1), 'wall side must be +1 or -1')
    n = len(S)
    s = [0.0]
    for i in range(1, n + (1 if closed else 0)):
        s.append(s[-1] + math.dist(S[i - 1], S[i % n]))
    out = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        A, B, TA, TB = S[i], S[j], T[i], T[j]
        ya, yb = (A[1], B[1]) if y is None else (y, y)
        fa, fb = offset_pt(A, TA, offset, ya), offset_pt(B, TB, offset, yb)
        ba, bb = offset_pt(A, TA, offset + side * thick, ya), offset_pt(B, TB, offset + side * thick, yb)
        up = lambda p: (p[0], p[1] + height, p[2])  # noqa: E731
        nA, nB = _np(TA), _np(TB)
        nf = (-side * (nA[0] + nB[0]) / 2, 0.0, -side * (nA[1] + nB[1]) / 2)
        uA, uB = s[i] / 4, s[i + 1] / 4
        out.append(face(front, [fa, fb, up(fb), up(fa)], [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], want=nf))
        out.append(face(top or front, [up(fa), up(fb), up(bb), up(ba)], [(uA, 0.05), (uB, 0.05), (uB, 0.0), (uA, 0.0)], want=(0, 1, 0),
                        col=(0.18, 0.18, 0.18)))
        out.append(face(back, [ba, bb, up(bb), up(ba)], [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], want=(-nf[0], 0, -nf[2]),
                        col=(0.16, 0.16, 0.16)))
    return out


def verge_strip(S, T, closed, o0, o1, mat, y=None, uv_m=8.0):
    """a flat strip between lateral offsets o0 .. o1 (e.g. grass outside a wall); uv = plan position / uv_m"""
    n = len(S)
    out = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        A, B, TA, TB = S[i], S[j], T[i], T[j]
        ya, yb = (A[1], B[1]) if y is None else (y, y)
        pts = [offset_pt(A, TA, o0, ya), offset_pt(B, TB, o0, yb), offset_pt(B, TB, o1, yb), offset_pt(A, TA, o1, ya)]
        out.append(face(mat, pts, [(p[0] / uv_m, p[2] / uv_m) for p in pts], want=(0, 1, 0)))
    return out


def terrain_patch(x0, z0, x1, z1, heights, cell, mat, uv_m=8.0):
    """a terrain patch over the plan rectangle x0..x1, z0..z1 in square-ish cells of about `cell` m; heights = one number (flat)
    or [h00, h10, h11, h01] at the corners (x0 z0, x1 z0, x1 z1, x0 z1; bilinear). Faces up; uv = plan position / uv_m."""
    need(all(_num(v) for v in (x0, z0, x1, z1)) and x1 - x0 >= 1 and z1 - z0 >= 1, 'terrain rectangle: x0 < x1, z0 < z1, at least 1 m')
    need(x1 - x0 <= 2000 and z1 - z0 <= 2000, 'terrain rectangle: at most 2000 m per side')
    need(_num(cell) and 1.0 <= cell <= 100.0, 'terrain cell %r: 1..100 m' % (cell,))
    if _num(heights):
        heights = [heights] * 4
    need(isinstance(heights, (list, tuple)) and len(heights) == 4 and all(_num(h) for h in heights),
         'terrain heights: one number or four corner heights [x0z0, x1z0, x1z1, x0z1]')
    nx, nz = max(1, int(round((x1 - x0) / cell))), max(1, int(round((z1 - z0) / cell)))
    need(nx * nz <= 4096, 'terrain patch of %d cells: at most 4096 (use a larger cell)' % (nx * nz))
    h00, h10, h11, h01 = heights

    def P(i, k):
        u, v = i / nx, k / nz
        y = h00 * (1 - u) * (1 - v) + h10 * u * (1 - v) + h11 * u * v + h01 * (1 - u) * v
        return (x0 + (x1 - x0) * u, y, z0 + (z1 - z0) * v)
    out = []
    for i in range(nx):
        for k in range(nz):
            pts = [P(i, k), P(i, k + 1), P(i + 1, k + 1), P(i + 1, k)]
            out.append(face(mat, pts, [(p[0] / uv_m, p[2] / uv_m) for p in pts], want=(0, 1, 0)))
    return out


def transform_faces(faces, offset, angle_deg, pivot):
    """yaw (positive = counter-clockwise seen from above: +x towards -z, as the v0.20 transforms) + offset; normals turn too"""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)

    def R(v):
        return (c * v[0] + s * v[2], v[1], c * v[2] - s * v[0])
    out = []
    for mat, cs in faces:
        nc = []
        for p, uv, n, col in cs:
            q = R((p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]))
            nc.append(((q[0] + pivot[0] + offset[0], q[1] + pivot[1] + offset[1], q[2] + pivot[2] + offset[2]), uv, R(n), col))
        out.append((mat, nc))
    return out


# ------------------------------------------------------------------ race layout (description values)
def heading_corners(S, T, sps, slices):
    """corner records from the plan curvature per slice (the demo's convention: turn toward n+ / n-, first extended 2 slices
    early, apex = the middle, radius = arc length / turned angle)"""
    head = [math.atan2(T[k * sps][1], T[k * sps][0]) for k in range(slices)]
    d = []
    for k in range(slices):
        x = head[(k + 1) % slices] - head[k]
        x = (x + math.pi) % (2 * math.pi) - math.pi
        d.append(x)
    seg = [math.dist(S[k * sps], S[((k + 1) % slices) * sps]) for k in range(slices)]
    curved = [abs(d[k]) > 1e-9 and seg[k] / abs(d[k]) < CORNER_RADIUS_MAX for k in range(slices)]
    if all(curved):                                         # a pure ring: no straight to start from (as the demo's ring: quarters)
        runs = [(q * slices // 4, (q + 1) * slices // 4 - 1) for q in range(4)]
    else:
        start = next(k for k in range(slices) if not curved[k])
        runs, k, cur = [], 0, None
        while k < slices:
            i = (start + k) % slices
            if curved[i] and (cur is None or (d[i] > 0) == (d[cur[0] % slices] > 0)):
                cur = (cur[0], start + k) if cur else (start + k, start + k)
            else:
                if cur:
                    runs.append(cur)
                cur = (start + k, start + k) if curved[i] else None
            k += 1
        if cur:
            runs.append(cur)
    out = []
    for a, b in runs:
        ang = sum(d[k % slices] for k in range(a, b + 1))
        deg = abs(math.degrees(ang))
        if deg < CORNER_MIN_DEG:
            continue
        arc = sum(seg[k % slices] for k in range(a, b + 1))
        out.append({"first": (a - 2) % slices, "apex": ((a + b) // 2) % slices, "last": b % slices,
                    "radius": round(arc / abs(ang), 2), "turn": "toward_n_plus" if ang > 0 else "toward_n_minus",
                    "degrees": int(round(deg))})
    return out


def stations_from(S, T, hw, wall_t, verge_out, verge_in, y0):
    """route stations: centre p (flat at y0), tangent t, the 6 lane-boundary offsets along n+ of the demo convention
    [corridor_out, outer wall face, edge_out, edge_in, inner wall face, corridor_in]"""
    offs = [round(-(hw + wall_t + verge_out), 4), round(-hw, 4), round(-(hw - 1.0), 4), round(hw - 1.0, 4), round(hw, 4),
            round(hw + wall_t + verge_in, 4)]
    return [{"p": [round(p[0], 4), y0, round(p[2], 4)], "t": [round(t[0], 6), round(t[1], 6)], "offsets": list(offs)}
            for p, t in zip(S, T)]


def along(S, closed_len, s):
    """the point / tangent at arc length s (wrapping) along evenly spaced closed samples S"""
    n = len(S)
    step = closed_len / n
    s %= closed_len
    i = int(s // step) % n
    f = (s - i * step) / step
    A, B = S[i], S[(i + 1) % n]
    p = [A[k] + (B[k] - A[k]) * f for k in range(3)]
    tx, tz = B[0] - A[0], B[2] - A[2]
    L = math.hypot(tx, tz)
    return p, [tx / L, tz / L]


def start_objects(S, L, y0, n_checkpoints=6, cp_width=45.0):
    """start line at station 0, 6 grid slots behind it (2 columns at +-2 m on the centre line, rows every 8 m from 12 m back:
    the demo's layout, runtime-validated), checkpoints evenly spaced in lap order (k * n / (count + 1))"""
    need(isinstance(n_checkpoints, int) and not isinstance(n_checkpoints, bool) and 1 <= n_checkpoints <= 12, 'checkpoints: 1..12')
    p0, t0 = S[0], along(S, L, 0.0)[1]
    grid = []
    for r in range(3):
        for c, o in enumerate((-2.0, 2.0)):
            back = 12.0 + 8.0 * r + (4.0 if c else 0.0)
            p, t = along(S, L, -back)
            q = offset_pt(p, t, o)
            grid.append({"pos": [round(q[0], 3), y0 + 0.5, round(q[2], 3)], "fwd": [round(t[0], 6), 0.0, round(t[1], 6)]})
    n = len(S)
    cps = []
    for k in range(1, n_checkpoints + 1):
        i = (k * n) // (n_checkpoints + 1)
        t = along(S, L, L * i / n)[1]
        cps.append({"pos": [round(S[i][0], 3), y0, round(S[i][2], 3)], "normal": [t[0], 0.0, t[1]], "width": cp_width})
    return ({"pos": [round(p0[0], 3), y0, round(p0[2], 3)], "normal": [t0[0], 0.0, t0[1]], "width": cp_width}, grid, cps)


def traffic_for(n, hw):
    """authored traffic in the demo's shape (two same-way lanes, nodes every 3 stations over 30/357 .. 330/357 of the loop):
    the demo values, re-scaled to n stations"""
    first = 30 * n // 357
    return {"lanes": [{"offset": -hw / 2, "width": hw - 1.0, "speed": 30.0, "flow": [1.5, 2.5, 0.0, 0.3, 0.0, 0.0]},
                      {"offset": hw / 2, "width": hw - 1.0, "speed": 30.0, "flow": [1.5, 2.5, 0.0, 0.3, 0.0, 0.0]}],
            "node_stations": 3, "first_station": first, "last_station": 330 * n // 357 // 3 * 3 + first % 3,
            "spawn_points": [[0, 5], [1, 30], [0, 55], [1, 80]],
            "vehicles": [["COMPCAR11", "COMPCAR12"], ["HEVYCAR11", "HEVYCAR12", "HEVYCAR13", "HEVYCAR14", "HEVYCAR15", "HEVYCAR34"],
                         [], [], ["HEVYCAR23"], ["HEVYCAR24", "HEVYCAR27"]]}


# ------------------------------------------------------------------ units
def chord_normal(stations, a, b):
    A, B = stations[a]["p"], stations[b]["p"]
    cx, cz = B[0] - A[0], B[2] - A[2]
    L = math.hypot(cx, cz)
    need(L > 1e-6, 'unit cut stations %d and %d are at one point' % (a, b))
    return [-cz / L, cx / L]


def fit_lateral(stations, a, b, pts, margin=0.25):
    """lateral bounds of the unit from cut station a to b: the extremes, along its chord normal, of the route corridor
    (offsets[0] / [-1] of every station a..b) and of `pts` (plan points of the geometry between its cuts), + margin"""
    m = chord_normal(stations, a, b)
    A = stations[a]["p"]
    n = len(stations)
    lo, hi = float('inf'), -float('inf')
    j = a
    while True:
        st = stations[j % n]
        for o in (st["offsets"][0], st["offsets"][-1]):
            q = offset_pt(st["p"], st["t"], o)
            d = (q[0] - A[0]) * m[0] + (q[2] - A[2]) * m[1]
            lo, hi = min(lo, d), max(hi, d)
        if j % n == b:
            break
        j += 1
    for x, z in pts:
        d = (x - A[0]) * m[0] + (z - A[2]) * m[1]
        lo, hi = min(lo, d), max(hi, d)
    return [round(lo - margin, 4), round(hi + margin, 4)], m


def drivable_samples(stations):
    """the kit validator's V2_drivable_coverage sample points (validate.py: f 0.2 / 0.6 between stations, 9 points wall to wall
    0.5 m inside the wall faces) -> [(x, z, station)]"""
    out = []
    n = len(stations)
    for i, s_ in enumerate(stations):
        s2 = stations[(i + 1) % n]
        for f in (0.2, 0.6):
            P = [s_["p"][k] + (s2["p"][k] - s_["p"][k]) * f for k in range(3)]
            tx, tz = s_["t"][0] + (s2["t"][0] - s_["t"][0]) * f, s_["t"][1] + (s2["t"][1] - s_["t"][1]) * f
            L = math.hypot(tx, tz)
            nx, nz = -tz / L, tx / L
            offs = [a + (b - a) * f for a, b in zip(s_["offsets"], s2["offsets"])]
            lo, hi = offs[1] + 0.5, offs[4] - 0.5
            for j in range(9):
                o = lo + (hi - lo) * j / 8
                out.append((P[0] + nx * o, P[2] + nz * o, i))
    return out


def route_samples(stations):
    """v0.28 (trackbuild 0.3.0 sloped routes): drivable_samples + the ROUTE height at each sample (the stations' own y,
    interpolated as validate.py does) -> [(x, z, station, route_y)]. A flat route gives station 0's y everywhere."""
    n = len(stations)
    ys = [stations[i]["p"][1] + (stations[(i + 1) % n]["p"][1] - stations[i]["p"][1]) * f
          for i in range(n) for f in (0.2, 0.6)]
    return [(x, z, i, ys[j // 9]) for j, (x, z, i) in enumerate(drivable_samples(stations))]   # 9 samples per (station, f)


# ------------------------------------------------------------------ structural race checks (offline; the kit's gates decide)
class TriGrid:
    """plan-space bucket grid of triangles (a, b, c) for point / short segment queries"""

    def __init__(self, tris, cell=8.0):
        self.cell, self.b = cell, {}
        for t in tris:
            xs, zs = [t[k][0] for k in range(3)], [t[k][2] for k in range(3)]
            for i in range(int(math.floor(min(xs) / cell)), int(math.floor(max(xs) / cell)) + 1):
                for j in range(int(math.floor(min(zs) / cell)), int(math.floor(max(zs) / cell)) + 1):
                    self.b.setdefault((i, j), []).append(t)

    def at(self, x, z):
        return self.b.get((int(math.floor(x / self.cell)), int(math.floor(z / self.cell))), [])


def _bary_y(t, x, z):
    a, b, c = t[0], t[1], t[2]
    det = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
    if abs(det) < 1e-12:
        return None
    l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / det
    l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / det
    if l1 < -1e-9 or l2 < -1e-9 or l1 + l2 > 1 + 1e-9:
        return None
    return l1 * a[1] + l2 * b[1] + (1 - l1 - l2) * c[1]


def _seg_tri(p0, d, t):
    a, b, c = t[0], t[1], t[2]
    e1 = [b[k] - a[k] for k in range(3)]
    e2 = [c[k] - a[k] for k in range(3)]
    h = (d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0])
    det = sum(e1[k] * h[k] for k in range(3))
    if abs(det) < 1e-9:
        return False
    f = 1 / det
    sv = [p0[k] - a[k] for k in range(3)]
    u = f * sum(sv[k] * h[k] for k in range(3))
    if not 0 <= u <= 1:
        return False
    q = (sv[1] * e1[2] - sv[2] * e1[1], sv[2] * e1[0] - sv[0] * e1[2], sv[0] * e1[1] - sv[1] * e1[0])
    v = f * sum(d[k] * q[k] for k in range(3))
    if v < 0 or u + v > 1:
        return False
    return 0 <= f * sum(e2[k] * q[k] for k in range(3)) <= 1


def race_checks(desc, faces, units):
    """STRUCTURAL validation of a race layout: an offline re-implementation of the kit validator's sampling plus layout rules. The
    kit's own gates at Build -> Validate stay the authority; nothing here proves AI, lap counting or respawn in the game.
    desc = the description; faces = [(surface word or None = no collision, [corners (x, y, z)])]; units = kit Unit objects.
    -> [{'check', 'ok', 'detail'}]"""
    st = desc.get('stations') or []
    out = []

    def add(name, ok, detail):
        out.append({'check': name, 'ok': bool(ok), 'detail': detail})
    n = len(st)
    if n < 12:
        add('connectivity', False, '%d stations: a closed route needs many more' % n)
        return out
    P = [s_['p'] for s_ in st]
    seg = [math.dist(P[i], P[(i + 1) % n]) for i in range(n)]
    mean = sum(seg) / n
    turn = []
    for i in range(n):
        a, b = st[i]['t'], st[(i + 1) % n]['t']
        turn.append(math.degrees(math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))))
    cross = self_intersections([[p[0], p[1], p[2]] for p in P], True, skip=2)
    gaps = [i for i in range(n) if seg[i] > 2.5 * mean or seg[i] < 1e-3]
    add('connectivity', not gaps and not cross and max(turn) < 30,
        {'stations': n, 'closed': True, 'mean_spacing_m': round(mean, 3), 'max_spacing_m': round(max(seg), 3),
         'spacing_outliers': gaps[:5], 'self_crossings': cross[:3], 'max_tangent_turn_deg': round(max(turn), 2),
         'loop_length_m': round(sum(seg), 2)})
    bad_dir = [i for i in range(n) if (P[(i + 1) % n][0] - P[(i - 1) % n][0]) * st[i]['t'][0] +
               (P[(i + 1) % n][2] - P[(i - 1) % n][2]) * st[i]['t'][1] <= 0]

    def near(q):
        return min(range(n), key=lambda i: (P[i][0] - q[0]) ** 2 + (P[i][2] - q[2]) ** 2)
    gdir = []
    for k, g in enumerate(desc.get('grid') or []):
        t = st[near(g['pos'])]['t']
        if g['fwd'][0] * t[0] + g['fwd'][2] * t[1] < 0.9:
            gdir.append(k)
    sl = desc.get('start_line') or {}
    sdir = bool(sl) and sl['normal'][0] * st[near(sl['pos'])]['t'][0] + sl['normal'][2] * st[near(sl['pos'])]['t'][1] >= 0.9
    cdir = [j for j, c in enumerate(desc.get('checkpoints') or [])
            if c['normal'][0] * st[near(c['pos'])]['t'][0] + c['normal'][2] * st[near(c['pos'])]['t'][1] < 0.9]
    add('direction', not bad_dir and not gdir and sdir and not cdir,
        {'stations_against_their_tangent': bad_dir[:5], 'grid_slots_not_facing_the_route': gdir, 'start_line_faces_the_route': sdir,
         'checkpoints_not_facing_the_route': cdir})
    y0 = P[0][1]
    floors = TriGrid([(f[1][0], f[1][i], f[1][i + 1]) for f in faces if f[0] is not None and (f[0] & 0xFF) <= 20
                      for i in range(1, len(f[1]) - 1)])
    walls = TriGrid([(f[1][0], f[1][i], f[1][i + 1]) for f in faces if f[0] is not None and (f[0] & 0xFF) >= 21 and not f[0] & 0x1000
                     for i in range(1, len(f[1]) - 1)], cell=4.0)
    samp = route_samples(st)                        # v0.28: kit 0.3.0 compares with the route height at each sample
    multi, holes, worst = [], [], 0.0
    for x, z, i, ry in samp:
        h = sum(1 for u in units if u.inside(x, z))
        if h != 1:
            multi.append((round(x, 2), round(z, 2), i, h))
            continue
        ys = [y for t in floors.at(x, z) for y in [_bary_y(t, x, z)] if y is not None]
        if not ys:
            holes.append((round(x, 2), round(z, 2), i))
            continue
        worst = max(worst, abs(max(ys) - ry))
    add('drivable coverage', not multi and not holes and worst < 0.05,
        {'samples': len(samp), 'not_in_one_unit': len(multi), 'first_not_in_one_unit': multi[:3], 'no_floor': len(holes),
         'first_no_floor': holes[:3], 'max_floor_dy_m': round(worst, 4),
         'rule': 'kit V2_drivable_coverage sampling (wall to wall; the highest floor within 0.05 m of the route height there)'})
    gap_ranges = desc.get('wall_gaps') or []
    probes = miss = 0
    first = []
    for i in range(0, n, 3):
        s_ = st[i]
        nx, nz = -s_['t'][1], s_['t'][0]
        for o_wall, sgn in ((s_['offsets'][1], -1), (s_['offsets'][4], 1)):
            if sgn < 0 and any(a - 1 <= i <= b for a, b in gap_ranges):
                continue
            x, z = s_['p'][0] + nx * (o_wall - sgn * 0.3), s_['p'][2] + nz * (o_wall - sgn * 0.3)
            probes += 1
            p0, d = (x, s_['p'][1] + 0.7, z), (nx * sgn, 0.0, nz * sgn)   # v0.28: this station's height (kit 0.3.0)
            cand = walls.at(x + nx * sgn * 0.5, z + nz * sgn * 0.5) + walls.at(x, z) + walls.at(x + nx * sgn, z + nz * sgn)
            if not any(_seg_tri(p0, d, t) for t in cand):
                miss += 1
                first.append(i)
    add('walls hold', probes > 0 and miss == 0, {'probes': probes, 'missed': miss, 'first_missed_stations': first[:5],
                                                'rule': 'kit V2_walls_hold probes (car-solid wall words, 1 m outward at 0.7 m)'})
    cps = desc.get('checkpoints') or []
    idx = [near(c['pos']) for c in cps]
    s0 = near(sl['pos']) if sl else 0
    rel = [(i - s0) % n for i in idx]
    order = all(rel[k] < rel[k + 1] for k in range(len(rel) - 1)) and (not rel or rel[0] > 0)
    spacing = min([rel[0]] + [rel[k + 1] - rel[k] for k in range(len(rel) - 1)] + [n - rel[-1]]) if rel else 0
    add('lap order', 1 <= len(cps) <= 12 and order and spacing >= 10,
        {'start_station': s0, 'checkpoint_stations': idx, 'in_lap_order': order, 'min_spacing_stations': spacing,
         'count': len(cps), 'rule': 'start line, then checkpoints in increasing route order, >= 10 stations apart, 1..12 (S1 cap)'})
    gi = []
    for k, g in enumerate(desc.get('grid') or []):
        i = near(g['pos'])
        s_ = st[i]
        o = (g['pos'][0] - s_['p'][0]) * -s_['t'][1] + (g['pos'][2] - s_['p'][2]) * s_['t'][0]
        h = sum(1 for u in units if u.inside(g['pos'][0], g['pos'][2]))
        if not (s_['offsets'][2] < o < s_['offsets'][3]) or h != 1:
            gi.append((k, round(o, 2), h))
    add('grid', len(desc.get('grid') or []) == 6 and not gi,
        {'slots': len(desc.get('grid') or []), 'off_main_lane_or_not_in_one_unit': gi,
         'rule': '6 slots between the main lane edges (offsets[2] .. [3]), each in exactly one unit (kit V5 grid gates)'})
    return out
