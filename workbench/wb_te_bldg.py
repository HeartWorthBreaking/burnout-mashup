"""wb_te_bldg - Workbench 0.33 buildings and simple scenery generators (Workbench 0.33, 2026-11-01), a mixin of
wb_trackedit.TrackSource (through wb_te_author.AuthorMixin).

Everything here is STATIC GEOMETRY written as a tagged construction block (trackbuild has no prop instances: see
TRACK_EDITOR_AUTHORING.md "Buildings and scenery"). Supported geometry only: opaque quads / triangles with the existing materials.

building: a simple polygon footprint (3..32 corners, plan x / z), a height, walls (single-sided or with a real thickness), a
roof (flat / gable / none) and optional door-style openings (real gaps in the walls AND in their collision: the kit builds
collision from the faces, so an opening is open). The generator adds no floor: the ground inside is whatever floor lies below.
Deferred, with the reason: windows / glass (no transparency in trackbuild materials), interiors and storeys (no use without
cameras / gameplay inside), hip / curved roofs (not needed for the first slice), per-face texture atlases.

tree / post: low-poly OPAQUE objects (trunk prism + foliage cone; a box post). Billboard / cut-out foliage needs alpha-tested
materials, which the bound trackbuild cannot write.
"""
import json
import math

import wb_construct as wc

T = {}

DEFERRED = {'windows / glass': 'trackbuild materials are opaque DXT1 (no transparency): a window would be a solid recess only',
            'interiors / storeys': 'no floors are generated; drive-through openings use the existing ground',
            'hip / curved roofs': 'flat and gable only in this slice',
            'real prop instances': 'trackbuild writes no prop instances; every object is a geometry copy in its unit'}


def E(msg, detail=None):
    e = T['EditError'](msg)
    if detail is not None:
        e.detail = detail
    return e


def num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


def _newell(P):
    n = [0.0, 0.0, 0.0]
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    m = math.sqrt(sum(x * x for x in n)) or 1.0
    return [x / m for x in n]


SUN = (0.4364, 0.7274, 0.5297)                 # a fixed baking light direction (normalised (0.6, 1.0, 0.728))


def shade(n, base=wc.VCOL):
    """baked vertex light from a face / vertex normal: up-facing = base, faces turned away from SUN darker (min 60 %). The
    editor preview has no lighting and the game uses vertex colour as baked light, so this is what makes shapes readable."""
    d = max(0.0, sum(a * b for a, b in zip(n, SUN)))
    return round(base * (0.6 + 0.4 * d) / (0.6 + 0.4 * SUN[1]), 3)


def shade_faces(faces, base=wc.VCOL):
    """smooth baked light for a generated surface (terrain): vertex normals averaged by position"""
    acc = {}
    for _m, cs in faces:
        for p, _uv, n, _c in cs:
            k = tuple(round(x, 4) for x in p)
            a = acc.setdefault(k, [0.0, 0.0, 0.0])
            for j in range(3):
                a[j] += n[j]
    out = []
    for m, cs in faces:
        nc = []
        for p, uv, n, _c in cs:
            a = acc[tuple(round(x, 4) for x in p)]
            ln = math.sqrt(sum(x * x for x in a)) or 1.0
            v = shade([x / ln for x in a], base)
            nc.append((p, uv, n, (v, v, v)))
        out.append((m, nc))
    return out


def _face(mat, P, UV, want, col=None, base=wc.VCOL):
    """a face with corners ordered so its Newell normal points along `want`; the stored normal = that Newell normal; colour =
    col, or baked light from the normal (shade) when col is None"""
    n = _newell(P)
    if sum(a * b for a, b in zip(n, want)) < 0:
        P, UV = P[::-1], UV[::-1]
        n = _newell(P)
    if col is None:
        col = shade(n, base)
    c = (col, col, col)
    return (mat, [(tuple(p), tuple(uv), tuple(n), c) for p, uv in zip(P, UV)])


def _area2(fp):
    return sum(fp[i][0] * fp[(i + 1) % len(fp)][1] - fp[(i + 1) % len(fp)][0] * fp[i][1] for i in range(len(fp))) / 2.0


def _seg_cross(a, b, c, d):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])  # noqa: E731
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def check_footprint(fp):
    if not (isinstance(fp, list) and 3 <= len(fp) <= 32 and all(isinstance(p, (list, tuple)) and len(p) == 2 and
                                                                 all(num(v, -1e6, 1e6) for v in p) for p in fp)):
        raise wc.ConstructError('footprint: 3..32 corners [x, z] (metres, plan)')
    P = [(float(p[0]), float(p[1])) for p in fp]
    n = len(P)
    for i in range(n):
        if math.dist(P[i], P[(i + 1) % n]) < 1.0:
            raise wc.ConstructError('footprint edge %d is shorter than 1 m' % i)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _seg_cross(P[i], P[(i + 1) % n], P[j], P[(j + 1) % n]):
                raise wc.ConstructError('footprint edges %d and %d cross (the outline must be a simple polygon)' % (i, j))
    a = _area2(P)
    if abs(a) < 4.0:
        raise wc.ConstructError('footprint area %.2f m2: at least 4 m2' % abs(a))
    if a < 0:
        P = P[::-1]                                                 # counter-clockwise in (x, z)
    xs, zs = [p[0] for p in P], [p[1] for p in P]
    if max(xs) - min(xs) > 300 or max(zs) - min(zs) > 300:
        raise wc.ConstructError('footprint larger than 300 m: split it')
    for i in range(n):                                              # corner angles (thick walls mitre at every corner)
        a_, b_, c_ = P[i - 1], P[i], P[(i + 1) % n]
        u = (a_[0] - b_[0], a_[1] - b_[1])
        v = (c_[0] - b_[0], c_[1] - b_[1])
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))))))
        if ang < 30:
            raise wc.ConstructError('footprint corner %d is sharper than 30 deg (%.1f deg)' % (i, ang))
    return P, a < 0


def inset(P, t):
    """counter-clockwise polygon -> the polygon t metres inside (mitred corners)"""
    n = len(P)
    L = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        dx, dz = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dz)
        nx, nz = -dz / m, dx / m                                    # inward normal of a CCW edge
        L.append(((a[0] + nx * t, a[1] + nz * t), (dx / m, dz / m)))
    out = []
    for i in range(n):
        (p, d), (q, e) = L[i - 1], L[i]
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-9:
            out.append(q)
            continue
        s = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
        out.append((p[0] + d[0] * s, p[1] + d[1] * s))
    if _area2(out) <= 0.5:
        raise wc.ConstructError('wall thickness %.2f m leaves no inside: thinner walls or a larger footprint' % t)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _seg_cross(out[i], out[(i + 1) % n], out[j], out[(j + 1) % n]):
                raise wc.ConstructError('the inner wall outline crosses itself at %.2f m thickness: thinner walls' % t)
    return out


def _ear(P):
    import wb_te_mesh as tm
    try:
        return tm.ear_clip(P)
    except tm.MeshError as e:
        raise wc.ConstructError('roof triangulation failed: %s' % e)


def building_faces(P, base, height, wall_mat, roof_mat, roof, roof_height, openings, thickness, uv_len, col=None):
    """P counter-clockwise (x, z). Returns faces [(material, corners)] and info."""
    n = len(P)
    top = base + height
    faces = []
    per = {}
    for o in openings:
        per.setdefault(o['edge'], []).append(o)
    inner = inset(P, thickness) if thickness > 0 else None
    perim = 0.0
    n_open = 0
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        L = math.dist(a, b)
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        out_n = [d[1], 0.0, -d[0]]                                  # outward normal of a CCW edge in (x, z)
        ops = sorted(per.get(i, []), key=lambda o: o['offset'])
        cuts, s = [], 0.0
        for o in ops:
            if o['offset'] < s - 1e-9:
                raise wc.ConstructError('openings on edge %d overlap' % i)
            cuts.append(('solid', s, o['offset'], base))
            cuts.append(('open', o['offset'], o['offset'] + o['width'], base + o['height']))
            s = o['offset'] + o['width']
        cuts.append(('solid', s, L, base))
        if inner:
            ia, ib = inner[i], inner[(i + 1) % n]

        def at(s_, edge_a, edge_b, L_):
            return (edge_a[0] + (edge_b[0] - edge_a[0]) * s_ / L_, edge_a[1] + (edge_b[1] - edge_a[1]) * s_ / L_)
        for kind, s0, s1, y0 in cuts:
            if s1 - s0 < 1e-6 or top - y0 < 0.05:
                continue
            p0, p1 = at(s0, a, b, L), at(s1, a, b, L)
            Q = [(p0[0], y0, p0[1]), (p1[0], y0, p1[1]), (p1[0], top, p1[1]), (p0[0], top, p0[1])]
            UV = [((perim + s0) / uv_len, (y0 - base) / uv_len), ((perim + s1) / uv_len, (y0 - base) / uv_len),
                  ((perim + s1) / uv_len, height / uv_len), ((perim + s0) / uv_len, height / uv_len)]
            faces.append(_face(wall_mat, Q, UV, out_n, col))
            if inner:                                               # inner shell: project s along the inner edge

                # the inner edge is shorter at mitred corners: map the opening positions by the outward normal projection
                q0 = (p0[0] - out_n[0] * thickness, p0[1] - out_n[2] * thickness)
                q1 = (p1[0] - out_n[0] * thickness, p1[1] - out_n[2] * thickness)
                if kind == 'solid':                                 # solid runs end at the inner corners
                    if s0 < 1e-9:
                        q0 = ia
                    if abs(s1 - L) < 1e-9:
                        q1 = ib
                Qi = [(q0[0], y0, q0[1]), (q1[0], y0, q1[1]), (q1[0], top, q1[1]), (q0[0], top, q0[1])]
                UVi = [(s0 / uv_len, (y0 - base) / uv_len), (s1 / uv_len, (y0 - base) / uv_len), (s1 / uv_len, height / uv_len),
                       (s0 / uv_len, height / uv_len)]
                faces.append(_face(wall_mat, Qi, UVi, [-out_n[0], 0.0, -out_n[2]], col))
            if kind == 'open':
                n_open += 1
                if inner:                                           # jambs and the lintel's underside (soffit)
                    q0 = (p0[0] - out_n[0] * thickness, p0[1] - out_n[2] * thickness)
                    q1 = (p1[0] - out_n[0] * thickness, p1[1] - out_n[2] * thickness)
                    for pp, qq, w in ((p0, q0, [d[0], 0.0, d[1]]), (p1, q1, [-d[0], 0.0, -d[1]])):
                        J = [(pp[0], base, pp[1]), (qq[0], base, qq[1]), (qq[0], y0, qq[1]), (pp[0], y0, pp[1])]
                        faces.append(_face(wall_mat, J, [(0, 0), (thickness / uv_len, 0), (thickness / uv_len, (y0 - base) / uv_len),
                                                         (0, (y0 - base) / uv_len)], w, col))
                    if top - y0 >= 0.05:
                        S_ = [(p0[0], y0, p0[1]), (p1[0], y0, p1[1]), (q1[0], y0, q1[1]), (q0[0], y0, q0[1])]
                        faces.append(_face(wall_mat, S_, [(0, 0), ((s1 - s0) / uv_len, 0), ((s1 - s0) / uv_len, thickness / uv_len),
                                                          (0, thickness / uv_len)], [0.0, -1.0, 0.0], col))
        perim += L
    info = {'perimeter_m': round(perim, 3), 'openings': n_open, 'roof': roof, 'thickness_m': thickness}
    up = [0.0, 1.0, 0.0]
    if roof == 'flat':
        R = P
        if len(R) == 4 and all(_cross_z(R[i - 1], R[i], R[(i + 1) % 4]) > 0 for i in range(4)):
            tris = [(0, 1, 2, 3)]
        else:
            tris = _ear(R)
        x0, z0 = min(p[0] for p in R), min(p[1] for p in R)
        for t in tris:
            Q = [(R[k][0], top, R[k][1]) for k in t]
            faces.append(_face(roof_mat, Q, [((R[k][0] - x0) / uv_len, (R[k][1] - z0) / uv_len) for k in t], up, col))
    elif roof == 'gable':
        if n != 4:
            raise wc.ConstructError('a gable roof needs a 4-corner footprint (use flat for other outlines)')
        e0, e1 = math.dist(P[0], P[1]), math.dist(P[1], P[2])
        k = 0 if e0 >= e1 else 1                                    # the ridge runs along the longer edges
        A, B, C, D = P[k], P[(k + 1) % 4], P[(k + 2) % 4], P[(k + 3) % 4]
        m1 = ((B[0] + C[0]) / 2, (B[1] + C[1]) / 2)                  # ridge ends: midpoints of the short edges
        m0 = ((D[0] + A[0]) / 2, (D[1] + A[1]) / 2)
        ry = top + roof_height
        L = math.dist(A, B)
        half = math.dist(A, D) / 2
        sl = math.hypot(half, roof_height)
        for (p, q, mq, mp) in ((A, B, m1, m0), (C, D, m0, m1)):
            Q = [(p[0], top, p[1]), (q[0], top, q[1]), (mq[0], ry, mq[1]), (mp[0], ry, mp[1])]
            faces.append(_face(roof_mat, Q, [(0, 0), (L / uv_len, 0), (L / uv_len, sl / uv_len), (0, sl / uv_len)], up, col))
        for (p, q, mid) in ((B, C, m1), (D, A, m0)):               # gable triangles in the short walls' planes
            dx, dz = q[0] - p[0], q[1] - p[1]
            m_ = math.hypot(dx, dz)
            Q = [(p[0], top, p[1]), (q[0], top, q[1]), (mid[0], ry, mid[1])]
            faces.append(_face(wall_mat, Q, [(0, height / uv_len), (m_ / uv_len, height / uv_len),
                                             (m_ / 2 / uv_len, (height + roof_height) / uv_len)], [dz / m_, 0.0, -dx / m_], col))
        info['ridge_m'] = round(ry, 3)
    elif roof == 'none' and inner:                                  # wall tops
        for i in range(n):
            a, b, ia, ib = P[i], P[(i + 1) % n], inner[i], inner[(i + 1) % n]
            Q = [(a[0], top, a[1]), (b[0], top, b[1]), (ib[0], top, ib[1]), (ia[0], top, ia[1])]
            faces.append(_face(wall_mat, Q, [(0, 0), (math.dist(a, b) / uv_len, 0), (math.dist(a, b) / uv_len, thickness / uv_len),
                                             (0, thickness / uv_len)], up, col))
    info['faces'] = len(faces)
    return faces, info


def _cross_z(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def tree_faces(pos, height, radius, sides, trunk_mat, foliage_mat, uv_len, col=None):
    """low-poly opaque tree: trunk prism (radius 0.12 x crown radius, 30 % of the height) + foliage cone"""
    x, y, z = pos
    th = height * 0.3
    tr = max(0.15, radius * 0.12)
    faces = []
    for i in range(sides):
        a0, a1 = 2 * math.pi * i / sides, 2 * math.pi * (i + 1) / sides
        c0, c1 = (math.cos(a0), math.sin(a0)), (math.cos(a1), math.sin(a1))
        mid = ((c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2)
        Q = [(x + tr * c0[0], y, z + tr * c0[1]), (x + tr * c1[0], y, z + tr * c1[1]), (x + tr * c1[0], y + th, z + tr * c1[1]),
             (x + tr * c0[0], y + th, z + tr * c0[1])]
        faces.append(_face(trunk_mat, Q, [(i / sides, 0), ((i + 1) / sides, 0), ((i + 1) / sides, th / uv_len), (i / sides, th / uv_len)],
                           [mid[0], 0.0, mid[1]], col, 0.13))
        apex = (x, y + height, z)
        Cq = [(x + radius * c0[0], y + th, z + radius * c0[1]), (x + radius * c1[0], y + th, z + radius * c1[1]), apex]
        faces.append(_face(foliage_mat, Cq, [(i / sides, 0), ((i + 1) / sides, 0), ((i + 0.5) / sides, 1)],
                           [mid[0], radius / max(0.1, height - th), mid[1]], col, 0.15))
        B = [(x, y + th, z), (x + radius * c1[0], y + th, z + radius * c1[1]), (x + radius * c0[0], y + th, z + radius * c0[1])]
        faces.append(_face(foliage_mat, B, [(0.5, 0.5), (0.5 + c1[0] / 2, 0.5 + c1[1] / 2), (0.5 + c0[0] / 2, 0.5 + c0[1] / 2)],
                           [0.0, -1.0, 0.0], col, 0.15))
    return faces


class BldgMixin:
    def _bldg_req(self, footprint, base_y, ground, height, wall_material, roof_material, roof, roof_height, openings, thickness,
                  uv_len, collision, id_):
        try:
            P, flipped = check_footprint(footprint)
        except wc.ConstructError as e:
            raise E('building refused: %s' % e)
        if not num(height, 2, 100):
            raise E('height: 2..100 m')
        if roof not in ('flat', 'gable', 'none'):
            raise E("roof: 'flat', 'gable' or 'none'")
        if roof == 'gable' and not num(roof_height, 0.3, 30):
            raise E('roof_height: 0.3..30 m for a gable roof')
        if not num(thickness, 0, 3):
            raise E('thickness: 0 (single-sided walls) .. 3 m')
        if not num(uv_len, 0.5, 200):
            raise E('uv length 0.5..200 m per texture repeat')
        if not isinstance(ground, bool):
            raise E('ground: true (sit on the lowest floor below the corners) or false (base_y)')
        n = len(footprint)
        ops = []
        for k, o in enumerate(openings or []):
            if not (isinstance(o, dict) and set(o) <= {'edge', 'offset', 'width', 'height'} and isinstance(o.get('edge'), int)
                    and not isinstance(o.get('edge'), bool) and 0 <= o['edge'] < n):
                raise E('opening %d: {edge 0..%d, offset, width, height} (edge = footprint edge from corner edge to edge+1)' % (k, n - 1))
            i = o['edge'] if not flipped else (n - 2 - o['edge']) % n       # the outline was reversed to counter-clockwise
            a, b = P[i], P[(i + 1) % n]
            L = math.dist(a, b)
            off = o.get('offset', (L - o.get('width', 4.0)) / 2)
            w, h = o.get('width', 4.0), o.get('height', min(4.0, height - 0.5))
            if flipped:
                off = L - off - w
            clear = 0.3 + thickness
            if not (num(w, 0.8, 30) and num(h, 1.0, height - 0.3) and num(off, clear, L - w - clear)):
                raise E('opening %d on edge %d (%.1f m long): width 0.8..30 m, height 1 m .. height - 0.3 m, at least %.1f m from both '
                        'corners' % (k, o['edge'], L, clear))
            ops.append({'edge': i, 'offset': round(float(off), 4), 'width': float(w), 'height': float(h), 'requested_edge': o['edge']})
        mats = sorted({wall_material, roof_material if roof != 'none' else wall_material})
        cmap = self._collision_map(mats, collision)
        for m in cmap.values():
            self._mat_ok(m, 'building')
        excl = self.constructs()[id_]['groups'] if id_ else ()
        if ground:
            ys = [self._ground_y(p[0], p[1], excl) for p in P]
            if any(y is None for y in ys):
                raise E('ground: no collision floor below corner(s) %s; give base_y instead' % [i for i, y in enumerate(ys) if y is None])
            base = round(min(ys) - 0.05, 4)                         # walls start just below the lowest corner's floor
            gap = round(max(ys) - min(ys), 3)
        else:
            if not num(base_y, -1e5, 1e5):
                raise E('base_y: the ground height (m), or ground true')
            base, gap = float(base_y), None
        if id_ is not None:
            C = self.constructs()
            if id_ not in C or C[id_]['meta'].get('kind') != 'building':
                raise E('building %r does not exist' % (id_,))
        return {'footprint': [list(p) for p in P], 'base': base, 'ground': ground, 'ground_spread_m': gap, 'height': float(height),
                'wall_material': cmap[wall_material], 'roof_material': cmap[roof_material if roof != 'none' else wall_material],
                'roof': roof, 'roof_height': float(roof_height or 0.0), 'openings': ops, 'thickness': float(thickness),
                'uv_len': float(uv_len), 'collision': collision, 'id': id_}

    def _bldg_plan(self, req):
        try:
            faces, info = building_faces([tuple(p) for p in req['footprint']], req['base'], req['height'], req['wall_material'],
                                         req['roof_material'], req['roof'], req['roof_height'], req['openings'], req['thickness'],
                                         req['uv_len'])
        except wc.ConstructError as e:
            raise E('building refused: %s. Nothing changed' % e)
        C = self.constructs()
        repl = C[req['id']]['groups'] if req['id'] else []
        roofs = [f for f in faces if f[0] == req['roof_material'] and req['roof'] == 'flat']
        ov = self._overlap_check(roofs, set(repl), 'roof faces') if roofs else {'checked_against': 0, 'overlaps': 0}
        rid = req['id'] or self._new_id('building')
        meta = {'kind': 'building', 'id': rid, **{k: v for k, v in req.items() if k != 'id'}}
        after, blk = self._block_bytes(faces, meta, repl)
        warn = []
        for o in req['openings']:
            if o['width'] < 3.0:
                warn.append('opening on edge %d is %.1f m wide: narrower than about 3 m, a car may not fit (runtime unproven)' % (
                    o['requested_edge'], o['width']))
            if o['height'] < 2.2:
                warn.append('opening on edge %d is %.1f m high: low for a car (runtime unproven)' % (o['requested_edge'], o['height']))
        if req['openings']:
            warn.append('openings are real gaps in the walls and their collision; the generator adds no floor - drive-through needs '
                        'a floor (terrain / road) inside')
        if req['ground_spread_m'] and req['ground_spread_m'] > 0.5:
            warn.append('the ground under the corners differs by %.2f m: walls stand on the lowest corner and float elsewhere by up to '
                        'that much (flatten the terrain first)' % req['ground_spread_m'])
        warn += self._route_floor_warnings(blk['faces'])
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': dict(info, building=rid, base_y=req['base'], height_m=req['height'], collision=req['collision'],
                                materials={'walls': req['wall_material'], 'roof': req['roof_material']}, overlap=ov, warnings=warn,
                                deferred=DEFERRED, static_geometry='static geometry block (not a prop instance: copies count fully '
                                'in each unit)', v_added=blk['v_added'], vt_added=blk['vt_added'], vn_added=blk['vn_added'],
                                removed_faces=blk['removed_faces'], markers=[[p[0], req['base'], p[1]] for p in req['footprint']],
                                new_faces=[[list(q) for q in P] for P in blk['faces'][:3000]],
                                summary_lines=['building %s: %d corners, %.1f m high, roof %s, %d opening(s), walls %s m thick, %d faces, '
                                               'collision %s' % (rid, len(req['footprint']), req['height'], req['roof'],
                                                                 len(req['openings']), req['thickness'], len(faces), req['collision'])]
                                + ['WARNING: ' + w for w in warn])}

    def building_preview(self, footprint=None, base_y=None, ground=False, height=6.0, wall_material=None, roof_material=None,
                         roof='flat', roof_height=2.0, openings=None, thickness=0.0, uv_len=4.0, collision='keep', id=None):  # noqa: A002
        """v0.33: a simple building (footprint, height, walls, roof, openings) WITHOUT changing anything"""
        req = self._bldg_req(footprint, base_y, ground, height, wall_material, roof_material, roof, roof_height, openings, thickness,
                             uv_len, collision, id)
        plan = self._bldg_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('building', req), note='preview only: nothing changed')

    def building(self, footprint=None, base_y=None, ground=False, height=6.0, wall_material=None, roof_material=None, roof='flat',
                 roof_height=2.0, openings=None, thickness=0.0, uv_len=4.0, collision='keep', id=None, preview_key=None):  # noqa: A002
        req = self._bldg_req(footprint, base_y, ground, height, wall_material, roof_material, roof, roof_height, openings, thickness,
                             uv_len, collision, id)
        if preview_key != self._cons_key('building', req):
            raise E('NEEDS PREVIEW: preview this building first and apply it with its preview_key')
        plan = self._bldg_plan(req)
        S = plan['summary']
        label = '%s building %s (%d faces)' % ('re-generate' if id else 'new', plan['id'], S['faces'])
        r = self._apply_block(plan, label, 'building', S['faces'])
        return dict(S, **r)

    # ---------------- simple scenery objects
    def _tree_req(self, position, height, radius, sides, trunk_material, foliage_material, ground, id_):
        if not (isinstance(position, list) and len(position) == 3 and all(num(v, -1e6, 1e6) for v in position)):
            raise E('position: [x, y, z] metres')
        if not (num(height, 1, 40) and num(radius, 0.3, 15) and isinstance(sides, int) and not isinstance(sides, bool) and 3 <= sides <= 12):
            raise E('height 1..40 m, radius 0.3..15 m, sides 3..12')
        for m, role in ((trunk_material, 'trunk'), (foliage_material, 'foliage')):
            self._mat_ok(m, role)
        pos = [float(v) for v in position]
        excl = self.constructs()[id_]['groups'] if id_ else ()
        if ground:
            g = self._ground_y(pos[0], pos[2], excl)
            if g is None:
                raise E('ground: no collision floor below (%.2f, %.2f)' % (pos[0], pos[2]))
            pos[1] = round(g - 0.05, 4)
        if id_ is not None:
            C = self.constructs()
            if id_ not in C or C[id_]['meta'].get('kind') != 'tree':
                raise E('tree %r does not exist' % (id_,))
        return {'position': pos, 'height': float(height), 'radius': float(radius), 'sides': sides, 'trunk_material': trunk_material,
                'foliage_material': foliage_material, 'ground': bool(ground), 'id': id_}

    def _tree_plan(self, req):
        faces = tree_faces(req['position'], req['height'], req['radius'], req['sides'], req['trunk_material'], req['foliage_material'], 4.0)
        C = self.constructs()
        repl = C[req['id']]['groups'] if req['id'] else []
        rid = req['id'] or self._new_id('tree')
        meta = {'kind': 'tree', 'id': rid, **{k: v for k, v in req.items() if k != 'id'}}
        after, blk = self._block_bytes(faces, meta, repl)
        col = self.desc().get('materials', {})
        notes = ['foliage material %s %s collision' % (req['foliage_material'], 'HAS' if (col.get(req['foliage_material']) or {}).get('collide', True) else 'has no'),
                 'opaque low-poly tree (cut-out foliage needs alpha materials: not supported by the bound trackbuild)']
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'tree': rid, 'faces': len(faces), 'position': req['position'], 'notes': notes,
                            'static_geometry': 'static geometry block (not a prop instance)', 'markers': [req['position']],
                            'v_added': blk['v_added'], 'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]],
                            'summary_lines': ['tree %s: %.1f m, %d faces at %s' % (rid, req['height'], len(faces), req['position'])] + notes}}

    def tree_preview(self, position=None, height=8.0, radius=2.5, sides=6, trunk_material=None, foliage_material=None, ground=True,
                     id=None):  # noqa: A002
        req = self._tree_req(position, height, radius, sides, trunk_material, foliage_material, ground, id)
        plan = self._tree_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('tree', req), note='preview only: nothing changed')

    def tree(self, position=None, height=8.0, radius=2.5, sides=6, trunk_material=None, foliage_material=None, ground=True, id=None,  # noqa: A002
             preview_key=None):
        req = self._tree_req(position, height, radius, sides, trunk_material, foliage_material, ground, id)
        if preview_key != self._cons_key('tree', req):
            raise E('NEEDS PREVIEW: preview this tree first and apply it with its preview_key')
        plan = self._tree_plan(req)
        S = plan['summary']
        r = self._apply_block(plan, '%s tree %s (%d faces)' % ('re-generate' if id else 'new', plan['id'], S['faces']), 'tree', S['faces'])
        return dict(S, **r)


    # ---------------- road lanes: retail-style texture layout of the route road (edge strip | lane asphalt | edge strip)
    def _lanes_req(self, edge_material, edge_width, main_u_m, main_v_m, edge_u_m, block):
        C = self.constructs()
        if block not in C or C[block]['meta'].get('kind') != 'race':
            raise E('block: the route road block (%s)' % ', '.join(k for k, c in C.items() if c['meta'].get('kind') == 'race') or 'none')
        if 'road_lanes' in C:
            raise E('the road already has lane bands (block road_lanes): undo it or re-generate the race layout first')
        self._mat_ok(edge_material, 'road edge')
        if not (num(edge_width, 0.5, 6) and num(main_u_m, 1, 30) and num(main_v_m, 1, 30) and num(edge_u_m, 1, 30)):
            raise E('edge_width 0.5..6 m; main_u_m / main_v_m / edge_u_m 1..30 m per texture repeat')
        return {'block': block, 'edge_material': edge_material, 'edge_width': float(edge_width), 'main_u_m': float(main_u_m),
                'main_v_m': float(main_v_m), 'edge_u_m': float(edge_u_m)}

    def _lanes_plan(self, req):
        import wb_te_mesh as tm
        o = tm.Obj(self.obj_cur)
        groups = self.constructs()[req['block']]['groups']
        lines = [li for g in groups for li in o.groups[g]['faces']]
        if not lines:
            raise E('the route road block has no faces')
        # per face: corners with their uv; n- side = u 0, n+ side = u 1 (race layout convention); v = distance along / uv length
        quads = []
        for li in lines:
            cs = o.F[li]
            if len(cs) != 4:
                raise E('road face line %d is not a quad (%d corners): not a generated route road' % (li + 1, len(cs)))
            pts = [o.V[v - 1] for v, _t, _n in cs]
            uvs = [o.VT[t - 1] for _v, t, _n in cs]
            lo = [k for k in range(4) if uvs[k][0] < 0.5]
            hi = [k for k in range(4) if uvs[k][0] >= 0.5]
            if len(lo) != 2 or len(hi) != 2:
                raise E('road face line %d: corners are not two at u 0 and two at u 1' % (li + 1))
            lo.sort(key=lambda k: uvs[k][1])
            hi.sort(key=lambda k: uvs[k][1])
            quads.append((li, cs, pts, uvs, lo, hi))
        # metres per v unit, measured from the faces themselves (centre line length / v span)
        ks = []
        for li, cs, pts, uvs, lo, hi in quads:
            c0 = [(pts[lo[0]][j] + pts[hi[0]][j]) / 2 for j in range(3)]
            c1 = [(pts[lo[1]][j] + pts[hi[1]][j]) / 2 for j in range(3)]
            dv = uvs[lo[1]][1] - uvs[lo[0]][1]
            if abs(dv) > 1e-6:
                ks.append(math.dist(c0, c1) / abs(dv))
        ks.sort()
        mpv = ks[len(ks) // 2] if ks else 14.0
        w = tm.Writer(o)
        edge_faces = []
        e_req = req['edge_width']
        for li, cs, pts, uvs, lo, hi in quads:
            rows = []                                       # two stations: (n- point, n+ point, distance, colour n-, colour n+, normal)
            for s_ in (0, 1):
                a, b_ = lo[s_], hi[s_]
                rows.append((pts[a], pts[b_], uvs[a][1] * mpv, o.VC[cs[a][0] - 1], o.VC[cs[b_][0] - 1]))
            nrm = o.VN[cs[0][2] - 1]
            kn = w.vn([round(x, 6) for x in nrm])

            def at(r, f):
                return [r[0][j] + f * (r[1][j] - r[0][j]) for j in range(3)]
            wid = [math.dist(r[0], r[1]) for r in rows]
            e = min(e_req, 0.3 * min(wid))
            f1 = [e / x for x in wid]
            f2 = [1 - e / x for x in wid]

            def corner(r, f, col):
                return w.v(at(r, f), col)
            # main band (the original face line, same group / material): retail lane tile = u ALONG (6.2 m, stretches in curves),
            # v ACROSS (6.0 m = one lane, fixed); its dashed lane line sits at v 0.05 -> placed on the road centre
            main = []
            for s_, f in ((0, 'a'), (1, 'a'), (1, 'b'), (0, 'b')):
                r = rows[s_]
                ff = f1[s_] if f == 'a' else f2[s_]
                lat = (ff - 0.5) * wid[s_]
                main.append((corner(r, ff, r[3] if f == 'a' else r[4]), w.vt((round(r[2] / req['main_u_m'], 5), round(0.05 + lat / req['main_v_m'], 5)))))
            # keep the original winding: the original order was lo0, lo1?, ... -> rebuild in the order of the original corners
            order = []
            for k in range(4):
                side = 'a' if k in lo else 'b'
                st_ = 0 if (k == lo[0] or k == hi[0]) else 1
                order.append({(0, 'a'): 0, (1, 'a'): 1, (1, 'b'): 2, (0, 'b'): 3}[(st_, side)])
            w.replace[li] = [o.face_line([(main[i][0], main[i][1], kn) for i in order])]
            # edge bands: u along, v across (0 at the wall side = the kerb band of the retail edge texture)
            for side in ('a', 'b'):
                cl = []
                for k in range(4):
                    s_ = 0 if (k == lo[0] or k == hi[0]) else 1
                    r = rows[s_]
                    outer = (k in lo) if side == 'a' else (k in hi)       # this corner is on the wall side
                    ff = (0.0 if outer else f1[s_]) if side == 'a' else (1.0 if outer else f2[s_])
                    col = r[3] if side == 'a' else r[4]
                    vv = 0.0 if outer else 1.0
                    cl.append((corner(r, ff, col), w.vt((round(r[2] / req['edge_u_m'], 5), vv)), kn))
                edge_faces.append(o.face_line(cl))
        tag = ('# wb-construct ' + json.dumps({'kind': 'road_lanes', 'id': 'road_lanes', 'block': req['block'], 'edge_material': req['edge_material'],
                                               'edge_width': req['edge_width'], 'main_u_m': req['main_u_m'], 'main_v_m': req['main_v_m'],
                                               'edge_u_m': req['edge_u_m']}, sort_keys=True)).encode('ascii')
        w.tail = [('usemtl %s' % req['edge_material']).encode('ascii') + o.eol, tag + o.eol] + edge_faces
        try:
            after = w.build()
        except tm.MeshError as e_:
            raise E('road lanes refused: %s. Nothing changed' % e_)
        return after, {'road_faces': len(quads), 'edge_faces': len(edge_faces), 'metres_per_v_unit': round(mpv, 3)}

    def road_lanes_preview(self, edge_material=None, edge_width=3.0, main_u_m=6.2, main_v_m=6.0, edge_u_m=6.2, block='route_road'):
        """retail-style road texture layout (measured on US/C1_V1: lane tiles 6.2 m along (u) / 6.0 m across (v), 3 m edge strips 6.2 m long)
        on the generated route road, WITHOUT changing anything; geometry stays in the same plane"""
        req = self._lanes_req(edge_material, edge_width, main_u_m, main_v_m, edge_u_m, block)
        _after, rep = self._lanes_plan(req)
        return dict(rep, ok=True, preview_key=self._cons_key('road_lanes', req), note='preview only: nothing changed',
                    summary_lines=['road lanes: %d road faces -> lane band + 2 edge strips (%s, %.1f m), %d edge faces' % (
                        rep['road_faces'], req['edge_material'], req['edge_width'], rep['edge_faces'])])

    def road_lanes(self, edge_material=None, edge_width=3.0, main_u_m=6.2, main_v_m=6.0, edge_u_m=6.2, block='route_road', preview_key=None):
        req = self._lanes_req(edge_material, edge_width, main_u_m, main_v_m, edge_u_m, block)
        if preview_key != self._cons_key('road_lanes', req):
            raise E('NEEDS PREVIEW: preview the road lanes first and apply them with the preview_key')
        before = self.obj_cur
        after, rep = self._lanes_plan(req)
        if self.desc().get('stations'):                    # the drivable floor must stay exactly as checked
            r0, r1 = self.race_check(before), self.race_check(after)
            ok0 = {c['check']: c['ok'] for c in r0['structural']}
            newly = [c['check'] for c in r1['structural'] if not c['ok'] and ok0.get(c['check'], False)]
            if newly:
                raise E('road lanes refused: route checks %s would fail. Nothing changed' % newly)
        self.regenerate(after)                              # kit dry run (slots, collision)
        label = 'road lanes (%d faces split into lane + edge bands)' % rep['road_faces']
        self._push('obj', label, after, kind='road_lanes', index=None)
        return dict(rep, ok=True, label=label, summary_lines=[label, 'WARNING: re-generating the race layout replaces the road and '
                                                                      'leaves these edge strips stale (undo or remove them first)'])

    BLDG_LAYOUT = {'building_preview': 'building_preview', 'building': 'building', 'tree_preview': 'tree_preview', 'tree': 'tree', 'road_lanes_preview': 'road_lanes_preview', 'road_lanes': 'road_lanes'}
