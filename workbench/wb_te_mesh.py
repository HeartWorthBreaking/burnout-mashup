"""wb_te_mesh - track-editor authoring queue stage 4: mesh editing on the authored OBJ (gp\\workbench_te, 2026-11-01).

Pure byte / geometry planning (no kit, no files): wb_te_author applies the result through the editor's checks (kit re-read, clip
rule, structural route checks, manifold count, kit dry run, one undo entry).

Selections: faces = OBJ line numbers (1-based, as the editor reports them); vertices = v indices (1-based); edges = [v, v] pairs.
A vertex selection moves EVERY v line at the same position (4 decimals): faces split by uv / colour seams stay welded.
Line rules (as v0.22 / v0.24): new v / vt / vn lines go right after the last existing line of their kind; edited faces are
rewritten in place (same group); new faces (extrude sides, hole fills) are appended at the end as a tagged face group; every other
line stays byte for byte. Coordinates: 4 decimals, uv / normals 5 (the editor's convention).
"""
import decimal
import math

import wb_construct as wc


class MeshError(Exception):
    pass


def need(c, msg):
    if not c:
        raise MeshError(msg)


def _fmt(x, d):
    q = decimal.Decimal(1).scaleb(-d)
    v = decimal.Decimal(repr(float(x))).quantize(q, decimal.ROUND_HALF_EVEN)
    return format(abs(v) if v == 0 else v, 'f')


def pkey(p):
    return tuple(round(float(x), 4) + 0.0 for x in p)


class Obj:
    """an index over OBJ bytes: lines, v / vt / vn line numbers and values, faces {line: [(v, vt, vn)]}, face -> group"""

    def __init__(self, b):
        self.b = b
        self.lines = b.splitlines(keepends=True)
        self.eol = self.lines[-1][len(self.lines[-1].rstrip(b'\r\n')):] or b'\n'
        self.vl, self.tl, self.nl = [], [], []
        self.V, self.VC, self.VT, self.VN = [], [], [], []
        self.F, self.fgroup, self.groups = {}, {}, []
        for li, raw in enumerate(self.lines):
            s = raw.split(b'#', 1)[0].split()
            if not s:
                continue
            k = s[0]
            if k == b'v':
                self.vl.append(li)
                self.V.append([float(x) for x in s[1:4]])
                self.VC.append([x.decode('ascii') for x in s[4:7]])
            elif k == b'vt':
                self.tl.append(li)
                self.VT.append([float(x) for x in s[1:3]])
            elif k == b'vn':
                self.nl.append(li)
                self.VN.append([float(x) for x in s[1:4]])
            elif k == b'usemtl' and len(s) == 2:
                self.groups.append({'i': len(self.groups), 'line': li, 'mat': s[1].decode('ascii', 'replace'), 'faces': []})
            elif k == b'f' and self.groups:
                self.F[li] = [tuple(int(q) for q in t.split(b'/')) for t in s[1:]]
                self.fgroup[li] = self.groups[-1]['i']
                self.groups[-1]['faces'].append(li)

    def pts(self, li):
        return [self.V[v - 1] for v, _t, _n in self.F[li]]

    def mat(self, li):
        return self.groups[self.fgroup[li]]['mat']

    def face_line(self, corners):
        return ('f ' + ' '.join('%d/%d/%d' % c for c in corners)).encode('ascii') + self.eol

    def faces_at(self):
        """position key -> v indices"""
        out = {}
        for i, p in enumerate(self.V):
            out.setdefault(pkey(p), []).append(i + 1)
        return out

    def edge_use(self, faces=None):
        """edges by position -> [(face line, a index in face)] for the given faces (default: all)"""
        out = {}
        for li in (self.F if faces is None else faces):
            P = [pkey(self.V[v - 1]) for v, _t, _n in self.F[li]]
            for i in range(len(P)):
                e = tuple(sorted((P[i], P[(i + 1) % len(P)])))
                out.setdefault(e, []).append((li, i))
        return out


class Writer:
    """collects line edits and appends; build() -> new bytes"""

    def __init__(self, o):
        self.o = o
        self.replace = {}                                # line -> [bytes]
        self.addv, self.addt, self.addn, self.tail = [], [], [], []
        self.kv, self.kt, self.kn = {}, {}, {}
        for i, (p, c) in enumerate(zip(o.V, o.VC)):
            self.kv.setdefault((pkey(p), tuple(c)), i + 1)
        for i, t in enumerate(o.VT):
            self.kt.setdefault(tuple(_fmt(x, 5) for x in t), i + 1)
        for i, n in enumerate(o.VN):
            self.kn.setdefault(tuple(_fmt(x, 5) for x in n), i + 1)

    def v(self, p, col, reuse=True):
        toks = [_fmt(x, 4) for x in p] + list(col)
        key = (tuple(float(t) for t in toks[:3]), tuple(col))
        if reuse and key in self.kv:
            return self.kv[key]
        self.addv.append(('v ' + ' '.join(toks)).encode('ascii') + self.o.eol)
        idx = len(self.o.V) + len(self.addv)
        self.kv[key] = idx
        return idx

    def vt(self, uv):
        key = tuple(_fmt(x, 5) for x in uv)
        if key not in self.kt:
            self.addt.append(('vt ' + ' '.join(key)).encode('ascii') + self.o.eol)
            self.kt[key] = len(self.o.VT) + len(self.addt)
        return self.kt[key]

    def vn(self, n):
        key = tuple(_fmt(x, 5) for x in n)
        if key not in self.kn:
            self.addn.append(('vn ' + ' '.join(key)).encode('ascii') + self.o.eol)
            self.kn[key] = len(self.o.VN) + len(self.addn)
        return self.kn[key]

    def vpos(self, idx):
        """position of an existing or added v index"""
        if idx <= len(self.o.V):
            return self.o.V[idx - 1]
        return [float(x) for x in self.addv[idx - len(self.o.V) - 1].split()[1:4]]

    def build(self):
        o = self.o
        need(o.F, 'the OBJ has no faces')
        last = max(o.vl[-1] if o.vl else -1, o.tl[-1] if o.tl else -1, o.nl[-1] if o.nl else -1)
        need(min(o.F) > last, 'faces come before the last v / vt / vn line: new lines would need renumbering (unsupported OBJ layout)')
        need(o.lines[-1].endswith((b'\n', b'\r')), 'the OBJ does not end with a line end (unsupported layout)')
        out = []
        self.map = {}                                    # old line -> first new line (both 0-based) of its replacement
        for i, ln in enumerate(o.lines):
            self.map[i] = len(out)
            out.extend(self.replace.get(i, [ln]))
            if o.vl and i == o.vl[-1]:
                out.extend(self.addv)
            if o.tl and i == o.tl[-1]:
                out.extend(self.addt)
            if o.nl and i == o.nl[-1]:
                out.extend(self.addn)
        return b''.join(out + self.tail)


def unit(v):
    L = math.sqrt(sum(x * x for x in v))
    return [x / L for x in v] if L > 1e-12 else None


def newell(P):
    return wc.newell(P)


def planarity(P):
    n = newell(P)
    if n is None:
        return float('inf')
    return max(abs(sum(n[k] * (p[k] - P[0][k]) for k in range(3))) for p in P)


# ------------------------------------------------------------------ selections
def sel_vertices(o, verts=None, edges=None, faces=None):
    """the selected positions (vertex / edge / face selection) -> set of position keys"""
    keys = set()
    for v in verts or []:
        need(isinstance(v, int) and 1 <= v <= len(o.V), 'vertex %r: 1..%d' % (v, len(o.V)))
        keys.add(pkey(o.V[v - 1]))
    for e in edges or []:
        need(isinstance(e, list) and len(e) == 2, 'edge %r: [v, v]' % (e,))
        for v in e:
            need(isinstance(v, int) and 1 <= v <= len(o.V), 'edge vertex %r: 1..%d' % (v, len(o.V)))
            keys.add(pkey(o.V[v - 1]))
    for li in faces or []:
        need(isinstance(li, int) and li - 1 in o.F, 'face line %r is not a face' % (li,))
        keys.update(pkey(p) for p in o.pts(li - 1))
    need(keys, 'nothing selected (vertices, edges or faces)')
    return keys


def face_list(o, faces):
    need(isinstance(faces, list) and 1 <= len(faces) <= 20000, 'faces: a list of OBJ face line numbers')
    out = []
    for li in faces:
        need(isinstance(li, int) and not isinstance(li, bool) and li - 1 in o.F, 'face line %r is not a face' % (li,))
        out.append(li - 1)
    need(len(set(out)) == len(out), 'a face is listed twice')
    return out


def _renormal(o, w, li, corners, P):
    """face corners with the normal of the face's new plane (an existing identical vn reused; else one vn line added)"""
    n = newell(P)
    need(n is not None, 'face line %d would collapse (zero area)' % (li + 1))
    k = w.vn([round(x, 6) for x in n])
    return [(v, t, k) for v, t, _n in corners], n


# ------------------------------------------------------------------ operations -> (writer, report)
def op_transform(o, keys, delta=(0, 0, 0), angle=0.0, scale=1.0, pivot=None, axis=None):
    """move / yaw-rotate / scale the selected positions (every v line at them); affected faces get the normal of their new plane"""
    need(all(isinstance(x, (int, float)) and math.isfinite(x) for x in delta) and len(delta) == 3, 'delta: [dx, dy, dz]')
    need(isinstance(scale, (int, float)) and 0.1 <= scale <= 10, 'scale 0.1..10')
    need(isinstance(angle, (int, float)) and -360 <= angle <= 360, 'angle -360..360')
    if axis is not None:                                 # axis constraint: only that component of the move
        need(axis in ('x', 'y', 'z'), 'axis: x / y / z')
        delta = [d if 'xyz'[k] == axis else 0.0 for k, d in enumerate(delta)]
    need(any(abs(x) > 0 for x in delta) or angle or scale != 1, 'nothing to do (zero move, no turn, scale 1)')
    P = [list(k) for k in keys]
    piv = pivot or [(min(p[0] for p in P) + max(p[0] for p in P)) / 2, min(p[1] for p in P), (min(p[2] for p in P) + max(p[2] for p in P)) / 2]
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)

    def X(p):
        q = [(p[k] - piv[k]) * scale for k in range(3)]
        q = [c * q[0] + s * q[2], q[1], c * q[2] - s * q[0]]
        return [q[k] + piv[k] + delta[k] for k in range(3)]
    w = Writer(o)
    moved = {}
    for i, p in enumerate(o.V):
        if pkey(p) in keys:
            np_ = X(p)
            moved[i + 1] = np_
            w.replace[o.vl[i]] = [('v ' + ' '.join([_fmt(x, 4) for x in np_] + o.VC[i])).encode('ascii') + o.eol]
    affected = sorted(li for li, cs in o.F.items() if any(v in moved for v, _t, _n in cs))
    for li in affected:
        Pn = [moved.get(v, o.V[v - 1]) for v, _t, _n in o.F[li]]
        Pn = [[float(_fmt(x, 4)) for x in p] for p in Pn]
        cs, _n = _renormal(o, w, li, o.F[li], Pn)
        w.replace[li] = [o.face_line(cs)]
    return w, {'moved_v_lines': len(moved), 'positions': len(keys), 'affected_faces': [li + 1 for li in affected], 'pivot': piv,
               'delta': list(delta), 'angle': angle, 'scale': scale,
               'normals': 'every affected face gets the normal of its new plane (vn reused or added)'}


def op_delete(o, faces):
    fl = face_list(o, faces)
    w = Writer(o)
    for li in fl:
        w.replace[li] = []
    return w, {'deleted_faces': [li + 1 for li in fl], 'note': 'v / vt / vn lines are kept (unused lines are harmless)'}


def op_triangulate(o, faces, diagonal='short'):
    fl = face_list(o, faces)
    need(diagonal in ('short', '02', '13'), "diagonal: 'short' / '02' / '13'")
    w = Writer(o)
    out = []
    for li in fl:
        cs = o.F[li]
        need(len(cs) == 4, 'face line %d is already a triangle' % (li + 1))
        P = o.pts(li)
        d = diagonal
        if d == 'short':
            d = '02' if math.dist(P[0], P[2]) <= math.dist(P[1], P[3]) else '13'
        tris = ((0, 1, 2), (0, 2, 3)) if d == '02' else ((0, 1, 3), (1, 2, 3))
        new = []
        flat = planarity(P) <= 1e-3
        for t in tris:
            c3 = [cs[k] for k in t]
            if not flat:                                 # a non-planar quad: each triangle the normal of its own plane
                c3, _n = _renormal(o, w, li, c3, [P[k] for k in t])
            new.append(o.face_line(c3))
        w.replace[li] = new
        out.append({'line': li + 1, 'diagonal': d, 'planar': flat})
    return w, {'triangulated': out, 'uv / colours': 'kept (same v / vt references)',
               'normals': 'planar quads keep their normal; non-planar quads: each triangle its own plane'}


def op_subdivide(o, faces):
    """each selected face -> 4 (quad: edge midpoints + centre; triangle: edge midpoints). An edge shared with an UNSELECTED face is
    refused (it would open a crack / T-junction there)."""
    fl = face_list(o, faces)
    sel = set(fl)
    use = o.edge_use()
    for li in fl:
        for e in o.edge_use([li]):
            others = [f for f, _i in use[e] if f != li]
            bad = [f for f in others if f not in sel]
            if bad:
                raise MeshError('face line %d shares an edge with unselected face line %d: subdividing would leave a crack there '
                                '(select it too)' % (li + 1, bad[0] + 1))
    w = Writer(o)
    created = 0

    def mid_v(a, b):
        pa, pb = o.V[a - 1], o.V[b - 1]
        ca, cb = o.VC[a - 1], o.VC[b - 1]
        col = [_fmt((float(x) + float(y)) / 2, 3) for x, y in zip(ca, cb)] if ca and cb else ca
        return w.v([(pa[k] + pb[k]) / 2 for k in range(3)], col)

    def mid_t(a, b):
        ta, tb = o.VT[a - 1], o.VT[b - 1]
        return w.vt([(ta[k] + tb[k]) / 2 for k in range(2)])
    for li in fl:
        cs = o.F[li]
        n = len(cs)
        M = [(mid_v(cs[i][0], cs[(i + 1) % n][0]), mid_t(cs[i][1], cs[(i + 1) % n][1]), cs[i][2]) for i in range(n)]
        if n == 4:
            P = o.pts(li)
            col = o.VC[cs[0][0] - 1]
            cols = [o.VC[c[0] - 1] for c in cs]
            ccol = [_fmt(sum(float(x[k]) for x in cols) / 4, 3) for k in range(len(col))] if all(cols) else col
            cv = w.v([sum(p[k] for p in P) / 4 for k in range(3)], ccol)
            ct = w.vt([sum(o.VT[c[1] - 1][k] for c in cs) / 4 for k in range(2)])
            quads = [[cs[0], M[0], (cv, ct, 0), M[3]], [M[0], cs[1], M[1], (cv, ct, 0)], [(cv, ct, 0), M[1], cs[2], M[2]],
                     [M[3], (cv, ct, 0), M[2], cs[3]]]
            new = []
            for q in quads:
                Pq = [w.vpos(c[0]) for c in q]
                q2, _n = _renormal(o, w, li, q, [[float(_fmt(x, 4)) for x in p] for p in Pq])
                new.append(o.face_line(q2))
            w.replace[li] = new
        else:
            tris = [[cs[0], M[0], M[2]], [M[0], cs[1], M[1]], [M[2], M[1], cs[2]], [M[0], M[1], M[2]]]
            new = []
            for t in tris:
                Pq = [w.vpos(c[0]) for c in t]
                t2, _n = _renormal(o, w, li, t, [[float(_fmt(x, 4)) for x in p] for p in Pq])
                new.append(o.face_line(t2))
            w.replace[li] = new
        created += 4
    return w, {'subdivided': [li + 1 for li in fl], 'faces_after': created,
               'seams': 'midpoints per edge position and colour (a uv / colour seam keeps separate v / vt lines on each side)',
               'normals': 'each new face: the normal of its own plane'}


def op_extrude(o, faces, distance, side_mat=None, tag=None):
    """move a connected face region along its mean normal by `distance` and close the gap with side quads (appended as a new
    tagged face group, material side_mat or the region's). Refused: a non-manifold region boundary, a region of several materials
    without side_mat, |distance| < 0.05 m."""
    fl = face_list(o, faces)
    need(isinstance(distance, (int, float)) and 0.05 <= abs(distance) <= 50, 'distance: 0.05..50 m (negative = inwards)')
    eu = o.edge_use(fl)
    need(all(len(x) <= 2 for x in eu.values()), 'the region has a non-manifold edge (used by more than two selected faces)')
    allu = o.edge_use()
    bnd = [(e, x[0]) for e, x in eu.items() if len(x) == 1]
    need(bnd, 'the region has no boundary (closed): nothing to extrude')
    for e, _x in bnd:
        need(len(allu[e]) <= 2, 'the region boundary edge %s is non-manifold in the mesh' % (e,))
    ns = [newell(o.pts(li)) for li in fl]
    need(all(n is not None for n in ns), 'a selected face is degenerate')
    nm = unit([sum(n[k] for n in ns) for k in range(3)])
    need(nm is not None, 'the region normals cancel out: no extrusion direction')
    mats = {o.mat(li) for li in fl}
    need(side_mat or len(mats) == 1, 'the region has several materials (%s): name the side material' % ', '.join(sorted(mats)))
    sm = side_mat or mats.pop()
    w = Writer(o)
    newv = {}
    for li in fl:
        for v, _t, _n in o.F[li]:
            if v not in newv:
                p = o.V[v - 1]
                newv[v] = w.v([p[k] + nm[k] * distance for k in range(3)], o.VC[v - 1], reuse=False)
    for li in fl:
        w.replace[li] = [o.face_line([(newv[v], t, n) for v, t, n in o.F[li]])]
    cen = [sum(p[k] for li in fl for p in o.pts(li)) / sum(len(o.F[li]) for li in fl) for k in range(3)]
    side = []
    for e, (li, i) in bnd:
        cs = o.F[li]
        a, b = cs[i][0], cs[(i + 1) % len(cs)][0]
        pa, pb = o.V[a - 1], o.V[b - 1]
        qa, qb = w.vpos(newv[a]), w.vpos(newv[b])
        # consistent winding: the old edge a -> b (the outside neighbour runs b -> a), the moved face runs a' -> b', so the side
        # quad is a, b, b', a' (its normal then faces out of an outward extrusion / into an inward pocket)
        P = [[float(_fmt(x, 4)) for x in q] for q in (pa, pb, qb, qa)]
        L = math.dist(pa, pb)
        uvs = [(0, 0), (L / 4, 0), (L / 4, abs(distance) / 4), (0, abs(distance) / 4)]
        n = newell(P)
        need(n is not None, 'a side face would be degenerate')
        vi = [w.v(P[0], o.VC[a - 1]), w.v(P[1], o.VC[b - 1]), w.v(P[2], o.VC[b - 1]), w.v(P[3], o.VC[a - 1])]
        kn = w.vn([round(x, 6) for x in n])
        side.append(('f ' + ' '.join('%d/%d/%d' % (vi[k], w.vt(uvs[k]), kn) for k in range(4))).encode('ascii') + o.eol)
    w.tail = [('usemtl %s' % sm).encode('ascii') + o.eol, tag + o.eol] + side if tag else \
        [('usemtl %s' % sm).encode('ascii') + o.eol] + side
    return w, {'extruded_faces': [li + 1 for li in fl], 'direction': [round(x, 5) for x in nm], 'distance': distance,
               'side_faces': len(side), 'side_material': sm, 'boundary_edges': len(bnd),
               'normals': 'moved faces keep their normals (translation); side faces: their own plane, facing out of the region'}


def ear_clip(P2):
    """simple polygon (x, y pairs, counter-clockwise) -> triangles (index triples); refuses self-intersection"""
    n = len(P2)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            a, b, c, d = P2[i], P2[(i + 1) % n], P2[j], P2[(j + 1) % n]
            o_ = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])  # noqa: E731
            need(not (o_(a, b, c) * o_(a, b, d) < 0 and o_(c, d, a) * o_(c, d, b) < 0), 'the hole loop crosses itself')
    idx = list(range(n))
    out = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        found = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = P2[i0], P2[i1], P2[i2]
            cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cr <= 1e-12:
                continue
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = P2[j]
                d1 = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
                d2 = (c[0] - b[0]) * (p[1] - b[1]) - (c[1] - b[1]) * (p[0] - b[0])
                d3 = (a[0] - c[0]) * (p[1] - c[1]) - (a[1] - c[1]) * (p[0] - c[0])
                if d1 >= 0 and d2 >= 0 and d3 >= 0:
                    inside = True
                    break
            if inside:
                continue
            out.append((i0, i1, i2))
            idx.pop(k)
            found = True
            break
        need(found, 'the hole loop cannot be triangulated (degenerate / collinear corners)')
    out.append(tuple(idx))
    return out


def op_fill(o, loop, mat, tag=None, planar_tol=0.25, uv_m=8.0):
    """fill ONE explicitly given hole: `loop` = v indices in order around an open-edge loop (every consecutive pair an open edge by
    position: used by exactly one face). Winding = opposite to the neighbouring faces along the loop (consistent orientation).
    3 / 4 corners -> one face, more -> ear clipping in the loop's best-fit plane. Refused: not a closed open-edge loop, a loop
    non-planar beyond planar_tol m, a self-crossing loop."""
    need(isinstance(loop, list) and 3 <= len(loop) <= 256 and len(set(loop)) == len(loop), 'loop: 3..256 distinct v indices in order')
    for v in loop:
        need(isinstance(v, int) and 1 <= v <= len(o.V), 'loop vertex %r: 1..%d' % (v, len(o.V)))
    use = o.edge_use()
    K = [pkey(o.V[v - 1]) for v in loop]
    need(len(set(K)) == len(K), 'two loop vertices share one position')
    n = len(K)
    agree = 0
    for i in range(n):
        e = tuple(sorted((K[i], K[(i + 1) % n])))
        need(e in use and len(use[e]) == 1, 'loop edge %d -> %d is not an open edge (used by %d face(s)): explicit open-edge loops only'
             % (loop[i], loop[(i + 1) % n], len(use.get(e, []))))
        li, j = use[e][0]
        cs = o.F[li]
        a = pkey(o.V[cs[j][0] - 1])
        agree += 1 if a == K[i] else -1                  # the neighbour runs K[i] -> K[i+1]: the fill must run the other way
    need(abs(agree) == n, 'the neighbouring faces along the loop disagree on orientation (mixed winding): refused')
    P = [o.V[v - 1] for v in loop]
    if agree > 0:
        P, loop = P[::-1], loop[::-1]
    nrm = newell(P)
    need(nrm is not None, 'the loop encloses no area')
    off = planarity(P)
    need(off <= planar_tol, 'the loop is not planar within %.2f m (%.3f m): fill it in parts (explicit smaller loops)' % (planar_tol, off))
    # 2-D projection onto the plane
    ax = [1, 0, 0] if abs(nrm[0]) < 0.9 else [0, 1, 0]
    u = unit([ax[1] * nrm[2] - ax[2] * nrm[1], ax[2] * nrm[0] - ax[0] * nrm[2], ax[0] * nrm[1] - ax[1] * nrm[0]])
    vv = [nrm[1] * u[2] - nrm[2] * u[1], nrm[2] * u[0] - nrm[0] * u[2], nrm[0] * u[1] - nrm[1] * u[0]]
    P2 = [(sum(p[k] * u[k] for k in range(3)), sum(p[k] * vv[k] for k in range(3))) for p in P]
    tris = [(0, 1, 2)] if len(P) == 3 else ([(0, 1, 2, 3)] if len(P) == 4 and planarity(P) <= 1e-3 and _convex(P2) else ear_clip(P2))
    w = Writer(o)
    fl = []
    for t in tris:
        Q = [P[k] for k in t]
        nn = newell(Q)
        need(nn is not None and sum(a * b for a, b in zip(nn, nrm)) > 0, 'a fill triangle would be degenerate / flipped')
        kn = w.vn([round(x, 6) for x in nn])
        fl.append(('f ' + ' '.join('%d/%d/%d' % (loop[k], w.vt((P[k][0] / uv_m, P[k][2] / uv_m)), kn) for k in t)).encode('ascii') + o.eol)
    w.tail = [('usemtl %s' % mat).encode('ascii') + o.eol] + ([tag + o.eol] if tag else []) + fl
    return w, {'loop': loop, 'faces': len(fl), 'material': mat, 'planarity_m': round(off, 4), 'normal': [round(x, 5) for x in nrm],
               'winding': 'opposite to the neighbouring faces along the loop', 'uv': 'planar (x, z) / %g m' % uv_m}


def _convex(P2):
    s = 0
    n = len(P2)
    for i in range(n):
        a, b, c = P2[i], P2[(i + 1) % n], P2[(i + 2) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) > 1e-12:
            if s and (cr > 0) != (s > 0):
                return False
            s = cr
    return True


def non_manifold(o):
    return sum(1 for x in o.edge_use().values() if len(x) > 2)
