"""wb_te_geom - track-editor authoring queue geometry (gp\\workbench_te, 2026-11-01). Pure functions: no file or kit access.

Conventions = wb_construct / trackbuild: Y up, metres, lateral axis n+ = (-tz, tx), faces wound so cross(b - a, c - a) points
along the normal, vertex colour 0.2 neutral. Everything returns SOURCE data (faces [(material, [(pos, uv, normal, colour)])] or
description values); wb_te_author applies it through the editor's exact re-read / clip rule / kit dry run / undo.

Stage 1 (road design): profiled roads - per control point width and bank (degrees, + = the n+ edge higher), interpolated with
smoothstep between control points (zero rate at each control point: smooth transitions); elevation = the curve's y (centripetal
Catmull-Rom, C1). Cross-sections and continuity warnings. UV: u 0 (n- edge) .. 1 (n+ edge), v = centre-line distance / uv_len
(continuous along the road whatever the width); normals = each quad's Newell normal.
"""
import math

import wb_construct as wc

V2_TOL = 0.05                       # kit validate.py V2_drivable_coverage: floor within 0.05 m of the route height
V2_SAFETY = 0.04                    # the editor keeps a margin below the gate (4-decimal source coordinates, quad triangulation)
WARN = {'width_rate': 0.5,          # m of width change per m along: abrupt
        'bank_rate': 1.0,           # degrees per m along
        'grade_pct': 15.0,          # steep
        'grade_change': 1.0,        # % grade change per m along (a vertical kink)
        'bank_deg': 25.0}


def smooth(f):
    return f * f * (3 - 2 * f)


def sample_param(points, closed, step=None, count=None):
    """wb_construct.sample + for every sample its control-point parameter (segment index i, local fraction f along that segment's
    Catmull-Rom parameter) -> (samples, params, length). Positions match wb_construct.sample for the same arguments."""
    P = points
    n = len(P)
    seg = n if closed else n - 1
    dense, par = [], []
    for i in range(seg):
        p0 = P[(i - 1) % n] if closed or i > 0 else [2 * P[0][k] - P[1][k] for k in range(3)]
        p1, p2 = P[i], P[(i + 1) % n]
        p3 = P[(i + 2) % n] if closed or i + 2 < n else [2 * P[-1][k] - P[-2][k] for k in range(3)]
        m = max(8, int(math.dist(p1, p2) / 0.25))
        for j in range(m):
            dense.append(wc._cr(p0, p1, p2, p3, j / m))
            par.append((i, j / m))
    dense.append(list(P[0]) if closed else list(P[-1]))
    par.append((0, 0.0) if closed else (seg - 1, 1.0))
    acc = [0.0]
    for i in range(1, len(dense)):
        acc.append(acc[-1] + math.dist(dense[i - 1], dense[i]))
    L = acc[-1]
    wc.need(L > 2.0, 'the curve is shorter than 2 m')
    if count is None:
        count = max(2, int(round(L / step))) + (0 if closed else 1)
    k, out, pars = 0, [], []
    N = count if closed else count - 1
    for i in range(count):
        s = L * i / N
        while k + 1 < len(acc) - 1 and acc[k + 1] < s:
            k += 1
        f = 0.0 if acc[k + 1] == acc[k] else (s - acc[k]) / (acc[k + 1] - acc[k])
        out.append([dense[k][j] + (dense[k + 1][j] - dense[k][j]) * f for j in range(3)])
        a, b = par[k], par[k + 1]
        if b[0] == a[0]:
            pars.append((a[0], a[1] + (b[1] - a[1]) * f))
        else:                                               # the step crosses a control point
            pars.append((a[0], a[1] + (1.0 - a[1]) * f) if f < 1 else b)
    return out, pars, L


def interp_profile(values, pars, closed, name):
    """per control point values -> per sample (smoothstep between control points)"""
    n = len(values)
    out = []
    for i, f in pars:
        a, b = values[i % n], values[(i + 1) % n] if closed or i + 1 < n else values[i % n]
        out.append(a + (b - a) * smooth(min(1.0, max(0.0, f))))
    return out


def monotone_y(points, closed, pars):
    """elevation per sample from the control points' y with a monotone cubic (Fritsch-Carlson) over the plan distance between
    control points: never above / below its neighbouring control points (no Catmull-Rom overshoot), continuous grade, level where
    neighbouring control points are level"""
    P = points
    n = len(P)
    m = n if closed else n - 1
    h = [max(1e-9, math.hypot(P[(k + 1) % n][0] - P[k][0], P[(k + 1) % n][2] - P[k][2])) for k in range(m)]
    d = [(P[(k + 1) % n][1] - P[k][1]) / h[k] for k in range(m)]
    tan = []
    for k in range(n):
        if not closed and k in (0, n - 1):
            tan.append(d[0] if k == 0 else d[-1])
            continue
        a, b = d[(k - 1) % m], d[k % m]
        tan.append(0.0 if a * b <= 0 else 3 * (h[(k - 1) % m] + h[k % m]) / ((2 * h[k % m] + h[(k - 1) % m]) / a +
                                                                                  (h[k % m] + 2 * h[(k - 1) % m]) / b))
    out = []
    for i, f in pars:
        i %= m
        f = min(1.0, max(0.0, f))
        y0, y1 = P[i][1], P[(i + 1) % n][1]
        m0, m1 = tan[i] * h[i], tan[(i + 1) % n] * h[i]
        f2, f3 = f * f, f * f * f
        out.append((2 * f3 - 3 * f2 + 1) * y0 + (f3 - 2 * f2 + f) * m0 + (-2 * f3 + 3 * f2) * y1 + (f3 - f2) * m1)
    return out


def check_profile(values, n, name, lo, hi):
    wc.need(isinstance(values, list) and len(values) == n and all(wc._num(v) and lo <= v <= hi for v in values),
            '%s: a list of %d numbers (one per control point), each %g..%g' % (name, n, lo, hi))
    return [float(v) for v in values]


def cross_y(c, o, bank_deg):
    return c[1] + o * math.tan(math.radians(bank_deg))


def profiled_strip(S, T, closed, hws, banks, mat, uv_len=14.0):
    """a road strip with per-sample half widths `hws` and banks (degrees). Refused when an edge runs backwards (folds) or crosses
    itself, or a face is steeper than 78 degrees. -> (faces, centre length)"""
    wc.need(wc._num(uv_len) and 0.5 <= uv_len <= 200, 'uv length %r: 0.5..200 m per texture repeat' % (uv_len,))
    n = len(S)
    s = [0.0]
    for i in range(1, n + (1 if closed else 0)):
        s.append(s[-1] + math.dist(S[i - 1], S[i % n]))
    m = n if closed else n - 1
    for side in (-1, 1):
        E = [edge_pt(S[i], T[i], side * hws[i], banks[i]) for i in range(n)]
        for i in range(m):
            a, b = E[i], E[(i + 1) % n]
            wc.need((b[0] - a[0]) * T[i][0] + (b[2] - a[2]) * T[i][1] > 0,
                    'the %s edge folds over at sample %d (the curve radius there is smaller than the half width %.2f m): use a '
                    'narrower road or a wider curve' % ('n+' if side > 0 else 'n-', i, hws[i]))
        x = wc.self_intersections(E, closed)
        wc.need(not x, 'the %s edge crosses itself (segments %s)' % ('n+' if side > 0 else 'n-', x[:2]))
    x = wc.self_intersections(S, closed)
    wc.need(not x, 'the road crosses itself (segments %s): use the junction tools (no self-crossing strip)' % x[:2])
    out = []
    for i in range(m):
        j = (i + 1) % n
        pts = [edge_pt(S[i], T[i], -hws[i], banks[i]), edge_pt(S[j], T[j], -hws[j], banks[j]),
               edge_pt(S[j], T[j], hws[j], banks[j]), edge_pt(S[i], T[i], hws[i], banks[i])]
        uvs = [(0, s[i] / uv_len), (0, s[i + 1] / uv_len), (1, s[i + 1] / uv_len), (1, s[i] / uv_len)]
        f = wc.face(mat, pts, uvs, want=(0, 1, 0))
        wc.need(f[1][0][2][1] > 0.2, 'the road strip is steeper than 78 degrees at sample %d' % i)
        out.append(f)
    return out, s[-1]


def edge_pt(c, t, o, bank_deg):
    return wc.offset_pt(c, t, o, cross_y(c, o, bank_deg))


def cross_sections(S, T, hws, banks, closed):
    n = len(S)
    out, sacc = [], 0.0
    for i in range(n):
        if i:
            sacc += math.dist(S[i - 1], S[i])
        j = (i + 1) % n if closed or i + 1 < n else i
        k = i if j != i else max(0, i - 1)
        run = math.hypot(S[j if j != i else i][0] - S[k][0], S[j if j != i else i][2] - S[k][2]) if j != i else \
            math.hypot(S[i][0] - S[k][0], S[i][2] - S[k][2])
        rise = (S[j][1] - S[i][1]) if j != i else (S[i][1] - S[k][1])
        out.append({'i': i, 's': round(sacc, 3), 'centre': [round(v, 4) for v in S[i]], 'width': round(2 * hws[i], 4),
                    'bank_deg': round(banks[i], 4), 'grade_pct': round(100 * rise / run, 3) if run > 1e-9 else 0.0,
                    'left': [round(v, 4) for v in edge_pt(S[i], T[i], -hws[i], banks[i])],
                    'right': [round(v, 4) for v in edge_pt(S[i], T[i], hws[i], banks[i])]})
    return out


def continuity_warnings(xs, closed):
    """abrupt width / bank changes, steep grades, vertical kinks, steep banks -> [text] (warnings, never refusals)"""
    W = []
    n = len(xs)
    m = n if closed else n - 1
    worst = {}
    for i in range(m):
        a, b = xs[i], xs[(i + 1) % n]
        ds = max(1e-9, math.dist(a['centre'], b['centre']))
        for key, val in (('width_rate', abs(b['width'] - a['width']) / ds), ('bank_rate', abs(b['bank_deg'] - a['bank_deg']) / ds),
                         ('grade_change', abs(b['grade_pct'] - a['grade_pct']) / ds)):
            if val > worst.get(key, (0, 0))[0]:
                worst[key] = (val, i)
    for x in xs:
        for key, val in (('grade_pct', abs(x['grade_pct'])), ('bank_deg', abs(x['bank_deg']))):
            if val > worst.get(key, (0, 0))[0]:
                worst[key] = (val, x['i'])
    names = {'width_rate': 'width changes %.2f m per m', 'bank_rate': 'bank changes %.2f deg per m',
             'grade_change': 'grade changes %.2f %% per m (vertical kink)', 'grade_pct': 'grade %.1f %%', 'bank_deg': 'bank %.1f deg'}
    for key, (val, i) in sorted(worst.items()):
        if val > WARN[key]:
            W.append('%s at sample %d (warning above %g)' % (names[key] % val, i, WARN[key]))
    return W, {k: [round(v[0], 4), v[1]] for k, v in worst.items()}


def v2_bank_limit(lo, hi):
    """the largest bank (degrees) a DRIVABLE ROUTE section with wall faces at lateral lo / hi keeps inside the kit's V2 gate
    (samples 0.5 m inside the walls; the editor keeps V2_SAFETY of the 0.05 m)"""
    reach = max(abs(lo + 0.5), abs(hi - 0.5))
    return math.degrees(math.atan(V2_SAFETY / reach)) if reach > 1e-9 else 90.0


def wall_strip_var(S, T, closed, offs, side, height, thick, front, back, banks):
    """wb_construct.wall_strip with per-sample offsets and the base on the banked cross-section (3 faces per step, same order)"""
    wc.need(wc._num(height) and 0.3 <= height <= 30, 'wall height %r: 0.3..30 m' % (height,))
    wc.need(wc._num(thick) and 0.1 <= thick <= 5, 'wall thickness %r: 0.1..5 m' % (thick,))
    n = len(S)
    s = [0.0]
    for i in range(1, n + (1 if closed else 0)):
        s.append(s[-1] + math.dist(S[i - 1], S[i % n]))
    out = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        A, B, TA, TB = S[i], S[j], T[i], T[j]
        ya, yb = cross_y(A, offs[i], banks[i]), cross_y(B, offs[j], banks[j])
        fa, fb = wc.offset_pt(A, TA, offs[i], ya), wc.offset_pt(B, TB, offs[j], yb)
        ba, bb = wc.offset_pt(A, TA, offs[i] + side * thick, ya), wc.offset_pt(B, TB, offs[j] + side * thick, yb)
        up = lambda p: (p[0], p[1] + height, p[2])  # noqa: E731
        nA, nB = wc._np(TA), wc._np(TB)
        nf = (-side * (nA[0] + nB[0]) / 2, 0.0, -side * (nA[1] + nB[1]) / 2)
        uA, uB = s[i] / 4, s[i + 1] / 4
        out.append(wc.face(front, [fa, fb, up(fb), up(fa)], [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], want=nf))
        out.append(wc.face(front, [up(fa), up(fb), up(bb), up(ba)], [(uA, 0.05), (uB, 0.05), (uB, 0.0), (uA, 0.0)], want=(0, 1, 0),
                           col=(0.18, 0.18, 0.18)))
        out.append(wc.face(back, [ba, bb, up(bb), up(ba)], [(uA, 1), (uB, 1), (uB, 0.1), (uA, 0.1)], want=(-nf[0], 0, -nf[2]),
                           col=(0.16, 0.16, 0.16)))
    return out


def verge_strip_var(S, T, closed, o0s, o1s, mat, banks, uv_m=8.0):
    """a strip between per-sample lateral offsets; heights continue the banked cross-section plane"""
    n = len(S)
    out = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        A, B, TA, TB = S[i], S[j], T[i], T[j]
        pts = [edge_pt(A, TA, o0s[i], banks[i]), edge_pt(B, TB, o0s[j], banks[j]), edge_pt(B, TB, o1s[j], banks[j]),
               edge_pt(A, TA, o1s[i], banks[i])]
        out.append(wc.face(mat, pts, [(p[0] / uv_m, p[2] / uv_m) for p in pts], want=(0, 1, 0)))
    return out


# ------------------------------------------------------------------ stage 2: junctions, joins, overlaps
need = wc.need
face = wc.face
_num = wc._num


def _dir(a_deg):
    a = math.radians(a_deg)
    return (math.cos(a), math.sin(a))                   # (x, z)


def _isect(p, d, q, e):
    """lines p + t d, q + u e in plan -> (t, u) or None (parallel)"""
    det = d[0] * (-e[1]) - d[1] * (-e[0])
    if abs(det) < 1e-9:
        return None
    rx, rz = q[0] - p[0], q[1] - p[1]
    t = (rx * (-e[1]) - rz * (-e[0])) / det
    u = (d[0] * rz - d[1] * rx) / det
    return t, u


def junction_faces(centre, heading, arms, mat, uv_len=14.0, hub_uv=8.0):
    """a level junction piece: arms [{angle (deg from `heading`), width, length}] (3..6 arms, >= 25 deg apart); angle 0 = +x,
    90 = +z. Hub = the polygon of the arm edges' corners, as triangles from the centre (planar uv / hub_uv m: a texture seam at the
    hub edges, documented); each arm = quads from its hub edge to its end, u 0..1 across, v along / uv_len from 0 at the centre.
    -> (faces, ends [{arm, centre, t (out of the junction), width, bank 0, v}])"""
    need(isinstance(arms, list) and 3 <= len(arms) <= 6, 'a junction needs 3..6 arms')
    need(isinstance(centre, (list, tuple)) and len(centre) == 3 and all(_num(v) for v in centre), 'centre: [x, y, z]')
    need(_num(heading), 'heading: degrees')
    cx, cy, cz = [float(v) for v in centre]
    A = []
    for k, a in enumerate(arms):
        need(isinstance(a, dict) and set(a) <= {'angle', 'width', 'length'} and _num(a.get('angle')) and _num(a.get('width')) and
             _num(a.get('length')), 'arm %d: {angle, width, length}' % k)
        need(2 <= a['width'] <= 40 and 2 <= a['length'] <= 200, 'arm %d: width 2..40 m, length 2..200 m' % k)
        A.append({'k': k, 'ang': (heading + a['angle']) % 360, 'hw': a['width'] / 2, 'len': float(a['length'])})
    A.sort(key=lambda x: x['ang'])
    m = len(A)
    for i in range(m):
        gap = (A[(i + 1) % m]['ang'] - A[i]['ang']) % 360
        need(gap >= 25, 'arms %d and %d are only %.1f deg apart (at least 25)' % (A[i]['k'], A[(i + 1) % m]['k'], gap))
    C = (cx, cz)
    G = []                                              # per gap i (arm i -> arm i+1): corner point(s) and edge sides
    for i in range(m):
        a, b = A[i], A[(i + 1) % m]
        da, db = _dir(a['ang']), _dir(b['ang'])
        na, nb = (-da[1], da[0]), (-db[1], db[0])
        gap = (b['ang'] - a['ang']) % 360
        bis = _dir(a['ang'] + gap / 2)                  # the gap's bisector: each arm's edge facing it (a 180 deg gap has
        sa = 1 if na[0] * bis[0] + na[1] * bis[1] > 0 else -1   # na . db = 0, so the other arm's direction cannot decide)
        sb = 1 if nb[0] * bis[0] + nb[1] * bis[1] > 0 else -1
        pa = (C[0] + na[0] * sa * a['hw'], C[1] + na[1] * sa * a['hw'])
        pb = (C[0] + nb[0] * sb * b['hw'], C[1] + nb[1] * sb * b['hw'])
        x = _isect(pa, da, pb, db) if gap < 170 else None
        g = {'pa': pa, 'pb': pb, 'sa': sa, 'sb': sb, 'pts': None}
        if x and x[0] > 0 and x[1] > 0:
            g.update(pts=[(pa[0] + da[0] * x[0], pa[1] + da[1] * x[0])], ta=x[0], tb=x[1])
        G.append(g)
    hwmax = max(x['hw'] for x in A)
    for i in range(m):                                  # wide gaps: each arm's edge point at its other corner's distance
        g = G[i]
        if g['pts'] is None:
            ta = G[i - 1].get('tb') or hwmax
            tb = G[(i + 1) % m].get('ta') or hwmax
            da, db = _dir(A[i]['ang']), _dir(A[(i + 1) % m]['ang'])
            g.update(ta=ta, tb=tb, pts=[(g['pa'][0] + da[0] * ta, g['pa'][1] + da[1] * ta),
                                        (g['pb'][0] + db[0] * tb, g['pb'][1] + db[1] * tb)])
    y = cy
    P3 = lambda p: (p[0], y, p[1])  # noqa: E731
    faces, ends = [], []
    for i in range(m):                                  # hub triangles: centre, this arm's two hub corners
        right, left = G[i - 1]['pts'][-1], G[i]['pts'][0]
        tri = [P3(C), P3(right), P3(left)]
        faces.append(face(mat, tri, [(p[0] / hub_uv, p[2] / hub_uv) for p in tri], want=(0, 1, 0)))
        if len(G[i]['pts']) == 2:                       # the fill between a wide gap's two points
            tri = [P3(C), P3(G[i]['pts'][0]), P3(G[i]['pts'][1])]
            faces.append(face(mat, tri, [(p[0] / hub_uv, p[2] / hub_uv) for p in tri], want=(0, 1, 0)))
    for i in range(m):
        a = A[i]
        d = _dir(a['ang'])
        n = (-d[1], d[0])
        sl = G[i]['sa']                                 # this arm's side towards the next arm
        hub = {sl: G[i]['pts'][0], -sl: G[i - 1]['pts'][-1]}
        t0 = max((hub[s][0] - C[0]) * d[0] + (hub[s][1] - C[1]) * d[1] for s in (1, -1))
        need(t0 + 1.0 < a['len'], 'arm %d is shorter (%.1f m) than its hub corner distance + 1 m (%.1f m)' % (a['k'], a['len'], t0 + 1))
        steps = max(1, int(math.ceil((a['len'] - t0) / 6.0)))
        ts = [t0 + (a['len'] - t0) * j / steps for j in range(steps + 1)]

        def edge(t, s):
            return (C[0] + d[0] * t + n[0] * s * a['hw'], C[1] + d[1] * t + n[1] * s * a['hw'])
        prev, tprev = dict(hub), {s: (hub[s][0] - C[0]) * d[0] + (hub[s][1] - C[1]) * d[1] for s in (1, -1)}
        for j, t in enumerate(ts):
            cur = {1: edge(t, 1), -1: edge(t, -1)}
            same = {s: math.dist(cur[s], prev[s]) < 1e-6 for s in (1, -1)}
            if j == 0 and same[1] and same[-1]:
                continue
            pts = [P3(prev[-1]), P3(cur[-1]), P3(cur[1]), P3(prev[1])]
            uvs = [(0, tprev[-1] / uv_len), (0, t / uv_len), (1, t / uv_len), (1, tprev[1] / uv_len)]
            keep = [k for k in range(4) if not (k == 0 and same[-1]) and not (k == 3 and same[1])]
            faces.append(face(mat, [pts[k] for k in keep], [uvs[k] for k in keep], want=(0, 1, 0)))
            prev, tprev = cur, {1: t, -1: t}
        ends.append({'arm': a['k'], 'centre': [cx + d[0] * a['len'], y, cz + d[1] * a['len']], 't': [d[0], d[1]],
                     'width': 2 * a['hw'], 'bank': 0.0, 'v': a['len'] / uv_len})
    ends.sort(key=lambda e: e['arm'])
    return faces, ends


def join_faces(ea, eb, mat, step=4.0, uv_len=14.0):
    """a connector between two road ends ea / eb = {centre, t (pointing OUT of its road), width, bank (along its own road's
    direction), v}. Plan = cubic Hermite leaving ea along its t and arriving at eb against its t (tangent length = the end
    distance); elevation smoothstep; width / bank smoothstep; the first / last cross-sections are exactly the ends' (same corners;
    eb's bank changes sign: the connector runs against eb's direction); v continues from ea's v. -> (faces, samples, info)"""
    P0, P1 = [float(v) for v in ea['centre']], [float(v) for v in eb['centre']]
    D = math.hypot(P1[0] - P0[0], P1[2] - P0[2])
    need(D >= 2.0, 'the road ends are %.2f m apart (at least 2 m)' % D)
    need(abs(ea['width'] - eb['width']) <= 0.5 * max(ea['width'], eb['width']),
         'end widths %.1f / %.1f m differ by more than 50 %%: incompatible' % (ea['width'], eb['width']))
    bb = -eb['bank']
    need(abs(ea['bank'] - bb) <= 10, 'end banks differ by more than 10 deg along the connector: incompatible')
    need(abs(P1[1] - P0[1]) / D <= 0.25, 'the ends differ %.2f m in height over %.1f m (> 25 %% grade): incompatible' % (
        abs(P1[1] - P0[1]), D))
    ta, tb = ea['t'], [-eb['t'][0], -eb['t'][1]]
    count = max(2, int(round(D / step)))
    S, T_ = [], []
    for j in range(count + 1):
        u = j / count
        h = (2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2)
        dh = (6 * u ** 2 - 6 * u, 3 * u ** 2 - 4 * u + 1, -6 * u ** 2 + 6 * u, 3 * u ** 2 - 2 * u)
        x = h[0] * P0[0] + h[1] * D * ta[0] + h[2] * P1[0] + h[3] * D * tb[0]
        z = h[0] * P0[2] + h[1] * D * ta[1] + h[2] * P1[2] + h[3] * D * tb[1]
        dx = dh[0] * P0[0] + dh[1] * D * ta[0] + dh[2] * P1[0] + dh[3] * D * tb[0]
        dz = dh[0] * P0[2] + dh[1] * D * ta[1] + dh[2] * P1[2] + dh[3] * D * tb[1]
        ln = math.hypot(dx, dz)
        need(ln > 1e-9, 'the connector doubles back')
        S.append([x, P0[1] + (P1[1] - P0[1]) * smooth(u), z])
        T_.append([dx / ln, dz / ln])
    S[0], S[-1] = list(P0), list(P1)
    T_[0], T_[-1] = list(ta), list(tb)
    hws = [(ea['width'] + (eb['width'] - ea['width']) * smooth(j / count)) / 2 for j in range(count + 1)]
    banks = [ea['bank'] + (bb - ea['bank']) * smooth(j / count) for j in range(count + 1)]
    faces, length = profiled_strip(S, T_, False, hws, banks, mat, uv_len)
    v0 = float(ea.get('v', 0.0))
    faces = [(m_, [(p, (uv[0], uv[1] + v0), nn, c) for p, uv, nn, c in cs]) for m_, cs in faces]
    grade = max(abs(S[i + 1][1] - S[i][1]) / max(1e-9, math.hypot(S[i + 1][0] - S[i][0], S[i + 1][2] - S[i][2])) for i in range(len(S) - 1))
    return faces, S, {'length_m': round(length, 3), 'samples': len(S), 'v_from': round(v0, 5), 'max_grade_pct': round(100 * grade, 2)}


def _lx(p, q, a, b):
    den = (p[0] - q[0]) * (a[1] - b[1]) - (p[1] - q[1]) * (a[0] - b[0])
    if abs(den) < 1e-15:
        return q
    t = ((p[0] - a[0]) * (a[1] - b[1]) - (p[1] - a[1]) * (a[0] - b[0])) / den
    return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))


def _clip_poly(subj, clip):
    """Sutherland-Hodgman against a convex counter-clockwise polygon (x, z pairs)"""
    out = list(subj)
    n = len(clip)
    for i in range(n):
        a, b = clip[i], clip[(i + 1) % n]
        inp, out = out, []
        if not inp:
            break

        def inside(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-12
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            if inside(q):
                if not inside(p):
                    out.append(_lx(p, q, a, b))
                out.append(q)
            elif inside(p):
                out.append(_lx(p, q, a, b))
    return out


def _area2(P):
    return sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P))) / 2


def _ccw(P):
    return P if _area2(P) > 0 else P[::-1]


def floor_overlaps(new, old, dy=1.5, min_m2=0.01):
    """plan overlap of new faces with existing faces at a similar height (mean heights within dy; bridges / tunnels are not counted;
    shared edges have zero area). new / old = [[(x, y, z), ...]] -> [(i_new, i_old, m2)]"""
    cell = 8.0
    grid = {}
    for j, P in enumerate(old):
        xs, zs = [p[0] for p in P], [p[2] for p in P]
        for gx in range(int(math.floor(min(xs) / cell)), int(math.floor(max(xs) / cell)) + 1):
            for gz in range(int(math.floor(min(zs) / cell)), int(math.floor(max(zs) / cell)) + 1):
                grid.setdefault((gx, gz), []).append(j)
    out = []
    for i, P in enumerate(new):
        xs, zs = [p[0] for p in P], [p[2] for p in P]
        cand = set()
        for gx in range(int(math.floor(min(xs) / cell)), int(math.floor(max(xs) / cell)) + 1):
            for gz in range(int(math.floor(min(zs) / cell)), int(math.floor(max(zs) / cell)) + 1):
                cand.update(grid.get((gx, gz), ()))
        ya = sum(p[1] for p in P) / len(P)
        A = _ccw([(p[0], p[2]) for p in P])
        for j in sorted(cand):
            Q = old[j]
            if abs(sum(p[1] for p in Q) / len(Q) - ya) > dy:
                continue
            X = _clip_poly(A, _ccw([(p[0], p[2]) for p in Q]))
            if len(X) >= 3:
                a = abs(_area2(X))
                if a > min_m2:
                    cx, cz = sum(q[0] for q in X) / len(X), sum(q[1] for q in X) / len(X)
                    yn, yo = _poly_y(P, cx, cz), _poly_y(Q, cx, cz)
                    dyc = round(yn - yo, 4) if yn is not None and yo is not None else round(ya - sum(p[1] for p in Q) / len(Q), 4)
                    out.append((i, j, round(a, 4), dyc))
    return out


LAYER_DY = 0.03                                  # a new floor at least this far ABOVE an existing one lies on top of it (layered)


# ------------------------------------------------------------------ stage 3: height-grid terrain
HGRID_MAX_CELLS = 4096                   # the v0.26 terrain patch limit (per block); the kit's per-unit capacity is checked on apply


def hgrid_check(origin, cell, nx, nz, heights):
    need(isinstance(origin, (list, tuple)) and len(origin) == 2 and all(_num(v) and abs(v) < 1e6 for v in origin), 'origin: [x0, z0]')
    need(_num(cell) and 1.0 <= cell <= 50.0, 'cell %r: 1..50 m' % (cell,))
    need(isinstance(nx, int) and isinstance(nz, int) and 1 <= nx <= 128 and 1 <= nz <= 128 and nx * nz <= HGRID_MAX_CELLS,
         'grid %r x %r cells: 1..128 each, at most %d cells (larger areas: several blocks or a larger cell)' % (nx, nz, HGRID_MAX_CELLS))
    need(isinstance(heights, list) and len(heights) == (nx + 1) * (nz + 1) and all(_num(h) and abs(h) < 1e5 for h in heights),
         'heights: (nx + 1) x (nz + 1) = %d numbers' % ((nx + 1) * (nz + 1)))


def hgrid_point(origin, cell, i, k, h):
    return (origin[0] + i * cell, h, origin[1] + k * cell)


def hgrid_faces(origin, cell, nx, nz, heights, mat, uv_m=8.0, planar_tol=1e-3):
    """one quad per cell when planar within planar_tol m, else two triangles along the diagonal whose triangles fold less (each
    with its own correct normal); faces up; uv = plan / uv_m"""
    hgrid_check(origin, cell, nx, nz, heights)

    def H(i, k):
        return heights[k * (nx + 1) + i]

    def uv(P):
        return [(p[0] / uv_m, p[2] / uv_m) for p in P]
    out = []
    for k in range(nz):
        for i in range(nx):
            a, b = hgrid_point(origin, cell, i, k, H(i, k)), hgrid_point(origin, cell, i, k + 1, H(i, k + 1))
            c, d = hgrid_point(origin, cell, i + 1, k + 1, H(i + 1, k + 1)), hgrid_point(origin, cell, i + 1, k, H(i + 1, k))
            n = wc.newell([a, b, c])
            off = abs(sum(n[j] * (d[j] - a[j]) for j in range(3)))
            if off <= planar_tol:
                out.append(face(mat, [a, b, c, d], uv([a, b, c, d]), want=(0, 1, 0)))
                continue
            d1 = abs(sum(x * y for x, y in zip(wc.newell([a, b, c]), wc.newell([a, c, d]))))
            d2 = abs(sum(x * y for x, y in zip(wc.newell([a, b, d]), wc.newell([b, c, d]))))
            tris = ([a, b, c], [a, c, d]) if d1 >= d2 else ([a, b, d], [b, c, d])
            for P in tris:
                out.append(face(mat, P, uv(P), want=(0, 1, 0)))
    return out


def hgrid_sample(origin, cell, nx, nz, heights, x, z):
    """bilinear height at (x, z) or None outside the grid"""
    u, v = (x - origin[0]) / cell, (z - origin[1]) / cell
    if not (0 <= u <= nx and 0 <= v <= nz):
        return None
    i, k = min(int(u), nx - 1), min(int(v), nz - 1)
    fu, fv = u - i, v - k

    def H(i_, k_):
        return heights[k_ * (nx + 1) + i_]
    return H(i, k) * (1 - fu) * (1 - fv) + H(i + 1, k) * fu * (1 - fv) + H(i + 1, k + 1) * fu * fv + H(i, k + 1) * (1 - fu) * fv


BRUSHES = ('raise', 'lower', 'flatten', 'smooth', 'set', 'blend')


def brush(origin, cell, nx, nz, heights, mode, centre=None, radius=None, strength=None, target=None, points=None, polys=None,
          drop=0.05):
    """-> (new heights, changed vertex indices). raise / lower: +- strength m x falloff; flatten: towards target by strength (0..1)
    x falloff; smooth: towards the 4-neighbour mean by strength x falloff; set: exact heights at [[i, k, h], ...]; blend: road-edge
    blending - vertices under the given floor polygons (plan) go to the polygon's height - drop, vertices within radius of their
    boundary move towards the nearest boundary height - drop by strength x falloff (the polygons are never changed).
    Falloff = smoothstep(1 - distance / radius)."""
    need(mode in BRUSHES, 'brush %r: %s' % (mode, ' / '.join(BRUSHES)))
    H = list(heights)
    changed = []
    if mode == 'set':
        need(isinstance(points, list) and 1 <= len(points) <= 4096, 'set: [[i, k, height], ...] (1..4096)')
        for p in points:
            need(isinstance(p, list) and len(p) == 3 and isinstance(p[0], int) and isinstance(p[1], int) and 0 <= p[0] <= nx and
                 0 <= p[1] <= nz and _num(p[2]) and abs(p[2]) < 1e5, 'set point %r: [i 0..%d, k 0..%d, height]' % (p, nx, nz))
            j = p[1] * (nx + 1) + p[0]
            H[j] = float(p[2])
            changed.append(j)
        return H, sorted(set(changed))
    need(_num(radius) and 0.5 <= radius <= 500, 'radius %r: 0.5..500 m' % (radius,))
    if mode in ('raise', 'lower'):
        need(_num(strength) and 0 < strength <= 50, 'strength %r: 0..50 m' % (strength,))
    else:
        need(_num(strength) and 0 < strength <= 1, 'strength %r: 0..1' % (strength,))
    if mode == 'flatten':
        need(_num(target) and abs(target) < 1e5, 'flatten needs a target height')
    if mode != 'blend':
        need(isinstance(centre, (list, tuple)) and len(centre) == 2 and all(_num(v) for v in centre), 'centre: [x, z]')

    def pos(j):
        return (origin[0] + (j % (nx + 1)) * cell, origin[1] + (j // (nx + 1)) * cell)
    if mode == 'blend':
        need(isinstance(polys, list) and polys, 'blend needs the target road faces')
        need(_num(drop) and 0 <= drop <= 2, 'drop %r: 0..2 m below the road' % (drop,))
        cs = max(radius, 4.0)
        bins, pb = {}, {}
        for P in polys:
            xs, zs = [p[0] for p in P], [p[2] for p in P]
            for gx in range(int(math.floor(min(xs) / cs)) - 1, int(math.floor(max(xs) / cs)) + 2):
                for gz in range(int(math.floor(min(zs) / cs)) - 1, int(math.floor(max(zs) / cs)) + 2):
                    bins.setdefault((gx, gz), []).extend((P[q], P[(q + 1) % len(P)]) for q in range(len(P)))
                    pb.setdefault((gx, gz), []).append(P)
        for j in range(len(H)):
            x, z = pos(j)
            key = (int(math.floor(x / cs)), int(math.floor(z / cs)))
            inside = None
            for P in pb.get(key, ()):
                y = _poly_y(P, x, z)
                if y is not None:
                    inside = y if inside is None else max(inside, y)
            if inside is not None:
                t = inside - drop
                if abs(H[j] - t) > 1e-9:
                    H[j] = t
                    changed.append(j)
                continue
            best = None
            for a, b in bins.get(key, ()):
                d, y = _seg_dist(a, b, x, z)
                if best is None or d < best[0]:
                    best = (d, y)
            if best and best[0] < radius:
                w = smooth(1 - best[0] / radius) * strength
                nh = H[j] + (best[1] - drop - H[j]) * w
                if best[0] < 1.5 * cell:                    # vertices of cells reaching under the road: never above it
                    nh = min(nh, best[1] - drop)
                if abs(nh - H[j]) > 1e-9:
                    H[j] = nh
                    changed.append(j)
        H = [round(h, 4) for h in H]
        extra = clearance(origin, cell, nx, nz, H, polys, drop)
        return H, sorted(set(changed) | set(extra))
    cx, cz = centre
    H0 = list(H)
    for j in range(len(H)):
        x, z = pos(j)
        d = math.hypot(x - cx, z - cz)
        if d >= radius:
            continue
        w = smooth(1 - d / radius)
        if mode == 'raise':
            H[j] = H0[j] + strength * w
        elif mode == 'lower':
            H[j] = H0[j] - strength * w
        elif mode == 'flatten':
            H[j] = H0[j] + (target - H0[j]) * strength * w
        else:
            i, k = j % (nx + 1), j // (nx + 1)
            nb = [H0[kk * (nx + 1) + ii] for ii, kk in ((i - 1, k), (i + 1, k), (i, k - 1), (i, k + 1)) if 0 <= ii <= nx and 0 <= kk <= nz]
            H[j] = H0[j] + (sum(nb) / len(nb) - H0[j]) * strength * w
        if abs(H[j] - H0[j]) > 1e-9:
            changed.append(j)
    return [round(h, 4) for h in H], changed


def hgrid_height(origin, cell, nx, nz, heights, x, z):
    """the height of the terrain AS GENERATED (hgrid_faces: planar quads or the chosen triangle pair) at (x, z), or None"""
    u, v = (x - origin[0]) / cell, (z - origin[1]) / cell
    if not (0 <= u <= nx and 0 <= v <= nz):
        return None
    i, k = min(int(u), nx - 1), min(int(v), nz - 1)
    H = lambda a, b: heights[b * (nx + 1) + a]  # noqa: E731
    a_, b_ = hgrid_point(origin, cell, i, k, H(i, k)), hgrid_point(origin, cell, i, k + 1, H(i, k + 1))
    c_, d_ = hgrid_point(origin, cell, i + 1, k + 1, H(i + 1, k + 1)), hgrid_point(origin, cell, i + 1, k, H(i + 1, k))
    n = wc.newell([a_, b_, c_])
    if abs(sum(n[j] * (d_[j] - a_[j]) for j in range(3))) <= 1e-3:
        return _poly_y([a_, b_, c_, d_], x, z)
    d1 = abs(sum(p * q for p, q in zip(wc.newell([a_, b_, c_]), wc.newell([a_, c_, d_]))))
    d2 = abs(sum(p * q for p, q in zip(wc.newell([a_, b_, d_]), wc.newell([b_, c_, d_]))))
    for P in (([a_, b_, c_], [a_, c_, d_]) if d1 >= d2 else ([a_, b_, d_], [b_, c_, d_])):
        y = _poly_y(P, x, z)
        if y is not None:
            return y
    return None


def _probe_points(P):
    """corners, edge midpoints / quarters and the centroid of a polygon (where terrain must stay below a road face)"""
    out = [tuple(p) for p in P]
    for q in range(len(P)):
        a, b = P[q], P[(q + 1) % len(P)]
        for f in (0.25, 0.5, 0.75):
            out.append(tuple(a[j] + (b[j] - a[j]) * f for j in range(3)))
    out.append(tuple(sum(p[j] for p in P) / len(P) for j in range(3)))
    return out


def clearance(origin, cell, nx, nz, H, polys, drop, rounds=8):
    """lower the 4 vertices of every terrain cell whose generated surface rises above a road face (- drop) at the face's probe
    points, until none does (max `rounds`); edits H in place -> changed vertex indices. The road is never changed."""
    changed = set()
    for _r in range(rounds):
        bad = 0
        for P in polys:
            for x, y, z in _probe_points(P):
                h = hgrid_height(origin, cell, nx, nz, H, x, z)
                if h is None or h <= y - drop + 1e-4:
                    continue
                bad += 1
                u, v = (x - origin[0]) / cell, (z - origin[1]) / cell
                i, k = min(int(u), nx - 1), min(int(v), nz - 1)
                for a, b in ((i, k), (i + 1, k), (i, k + 1), (i + 1, k + 1)):
                    j = b * (nx + 1) + a
                    t = round(min(H[j], y - drop - (h - (y - drop))), 4)
                    if t < H[j]:
                        H[j] = t
                        changed.add(j)
        if not bad:
            break
    return sorted(changed)


def terrain_above(origin, cell, nx, nz, H, polys, drop=0.0):
    """road probe points the generated terrain surface covers (terrain > road - drop + 0.1 mm) -> [(point, terrain height)]"""
    out = []
    for P in polys:
        for x, y, z in _probe_points(P):
            h = hgrid_height(origin, cell, nx, nz, H, x, z)
            if h is not None and h > y - drop + 1e-4:
                out.append(((round(x, 3), round(y, 3), round(z, 3)), round(h, 4)))
    return out


def _poly_y(P, x, z):
    """height of a (fan-triangulated) polygon at plan point (x, z), or None outside"""
    for i in range(1, len(P) - 1):
        a, b, c = P[0], P[i], P[i + 1]
        det = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(det) < 1e-12:
            continue
        l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / det
        l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / det
        if l1 >= -1e-9 and l2 >= -1e-9 and l1 + l2 <= 1 + 1e-9:
            return l1 * a[1] + l2 * b[1] + (1 - l1 - l2) * c[1]
    return None


def _seg_dist(a, b, x, z):
    dx, dz = b[0] - a[0], b[2] - a[2]
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[2]) * dz) / L2))
    return math.hypot(x - (a[0] + dx * t), z - (a[2] + dz * t)), a[1] + (b[1] - a[1]) * t
