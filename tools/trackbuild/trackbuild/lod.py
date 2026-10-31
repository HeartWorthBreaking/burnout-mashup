"""trackbuild.lod - LOD decimation: a simplified far mesh per unit for the LOD block (drawn by the game for |rel| 5..8 and the
reflection pass), with a bounded geometric error and preserved silhouettes / material and unit borders.

Method: per material, vertices are welded by (position, uv) (a uv seam stays a border), triangles are simplified by greedy
half-edge collapses ordered by quadric error (Garland-Heckbert planes, area weighted) plus a strong border-plane term:
  - a collapse u -> v is allowed only if its quadric cost <= e_max^2 and the measured distance check below holds;
  - border vertices (on an edge used by one triangle: unit cuts, material borders, silhouettes, uv seams) may only slide
    ALONG a border onto a collinear neighbour (deviation <= e_border), corners never move -> no cracks between units /
    materials, outlines kept;
  - no triangle may flip or degenerate (normal dot > 0.2 against its original face normal, area > 1e-4 m2);
  - link condition (manifold-preserving).
Attributes (uv, colour) are those of the kept vertex: exact on planar affine regions (roads, walls, pads), approximated where
the source uv is not affine (curved arcs). Normals are recomputed per face (flat). Collision is NOT decimated (the LOD block
keeps the full collision tree; only its render records are simplified)."""
import heapq
import math

from .io import need


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _quad_add(q, r, w=1.0):
    for i in range(10):
        q[i] += r[i] * w


def _plane_quadric(n, d):
    a, b, c = n
    return [a * a, a * b, a * c, a * d, b * b, b * c, b * d, c * c, c * d, d * d]


def _quad_eval(q, p):
    x, y, z = p
    return (q[0] * x * x + 2 * q[1] * x * y + 2 * q[2] * x * z + 2 * q[3] * x + q[4] * y * y + 2 * q[5] * y * z + 2 * q[6] * y
            + q[7] * z * z + 2 * q[8] * z + q[9])


def _pt_seg_dist(p, a, b):
    ab = _sub(b, a)
    L2 = _dot(ab, ab)
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L2))
    c = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return _norm(_sub(p, c))


def pt_tri_dist(p, a, b, c):
    """exact point-triangle distance"""
    n = _cross(_sub(b, a), _sub(c, a))
    nn = _norm(n)
    if nn < 1e-12:
        return min(_pt_seg_dist(p, a, b), _pt_seg_dist(p, b, c), _pt_seg_dist(p, c, a))
    n = (n[0] / nn, n[1] / nn, n[2] / nn)
    d = _dot(_sub(p, a), n)
    q = (p[0] - n[0] * d, p[1] - n[1] * d, p[2] - n[2] * d)
    inside = all(_dot(_cross(_sub(v1, v0), _sub(q, v0)), n) >= -1e-9 for v0, v1 in ((a, b), (b, c), (c, a)))
    if inside:
        return abs(d)
    return min(_pt_seg_dist(p, a, b), _pt_seg_dist(p, b, c), _pt_seg_dist(p, c, a))


class Mesh:
    def __init__(self, tris, verts):
        self.verts = verts          # [(pos, uv, nrm, rgb)]
        self.tris = tris            # [[i, j, k]]


def _weld(polys_of_mat):
    vid, verts, tris = {}, [], []
    for poly in polys_of_mat:
        ids = []
        for pos, uv, nrm, rgb in poly:
            key = (tuple(round(c, 4) for c in pos), tuple(round(c, 5) for c in uv))
            if key not in vid:
                vid[key] = len(verts)
                verts.append((tuple(pos), tuple(uv), tuple(nrm), tuple(rgb)))
            ids.append(vid[key])
        for i in range(1, len(ids) - 1):
            t = [ids[0], ids[i], ids[i + 1]]
            if len(set(t)) == 3:
                tris.append(t)
    return Mesh(tris, verts)


def simplify_mesh(m, e_max=0.3, e_border=0.05):
    V = [list(v[0]) for v in m.verts]
    T = [list(t) for t in m.tris]
    alive = [True] * len(T)
    fnorm0 = []
    for t in T:
        n = _cross(_sub(V[t[1]], V[t[0]]), _sub(V[t[2]], V[t[0]]))
        L = _norm(n) or 1.0
        fnorm0.append((n[0] / L, n[1] / L, n[2] / L))
    vtris = [set() for _ in V]
    for k, t in enumerate(T):
        for i in t:
            vtris[i].add(k)
    edges = {}
    for k, t in enumerate(T):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edges.setdefault((min(a, b), max(a, b)), set()).add(k)
    border_nb = [set() for _ in V]
    for (a, b), ts in edges.items():
        if len(ts) == 1:
            border_nb[a].add(b)
            border_nb[b].add(a)
    Q = [[0.0] * 10 for _ in V]
    for k, t in enumerate(T):
        a, b, c = (V[i] for i in t)
        n = _cross(_sub(b, a), _sub(c, a))
        area = 0.5 * _norm(n)
        if area < 1e-9:
            continue
        nn = fnorm0[k]
        q = _plane_quadric(nn, -_dot(nn, a))
        for i in t:
            _quad_add(Q[i], q, area)
    # border planes (perpendicular to the face through the border edge), heavy weight -> outlines kept
    for (a, b), ts in edges.items():
        if len(ts) != 1:
            continue
        k = next(iter(ts))
        e = _sub(V[b], V[a])
        pn = _cross(e, fnorm0[k])
        L = _norm(pn)
        if L < 1e-9:
            continue
        pn = (pn[0] / L, pn[1] / L, pn[2] / L)
        q = _plane_quadric(pn, -_dot(pn, V[a]))
        w = 100.0 * _norm(e)
        _quad_add(Q[a], q, w)
        _quad_add(Q[b], q, w)
    removed = [False] * len(V)

    def neighbours(u):
        s = set()
        for k in vtris[u]:
            s.update(T[k])
        s.discard(u)
        return s

    def is_corner(u):
        nb = border_nb[u]
        if not nb:
            return False
        if len(nb) != 2:
            return True
        a, b = list(nb)
        return _pt_seg_dist(V[u], V[a], V[b]) > e_border     # a bend of the outline

    def valid(u, v):
        if removed[u] or removed[v]:
            return False
        if border_nb[u]:
            if v not in border_nb[u] or is_corner(u):
                return False
        shared = vtris[u] & vtris[v]
        nu, nv = neighbours(u), neighbours(v)
        opp = set()
        for k in shared:
            opp.update(i for i in T[k] if i not in (u, v))
        if (nu & nv) != opp:
            return False
        pv = V[v]
        for k in vtris[u] - shared:
            t = [pv if i == u else V[i] for i in T[k]]
            n = _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))
            L = _norm(n)
            if L < 2e-4 or _dot(n, fnorm0[k]) / L < 0.2:
                return False
        return True

    def cost(u, v):
        q = [Q[u][i] + Q[v][i] for i in range(10)]
        return max(0.0, _quad_eval(q, V[v]))

    heap = []
    for (a, b) in edges:
        for u, v in ((a, b), (b, a)):
            heapq.heappush(heap, (cost(u, v), u, v))
    lim = e_max * e_max
    collapses = 0
    while heap:
        c, u, v = heapq.heappop(heap)
        if c > lim:
            break
        if removed[u] or removed[v] or v not in neighbours(u):
            continue
        cn = cost(u, v)
        if cn > c + 1e-12:
            heapq.heappush(heap, (cn, u, v))
            continue
        if not valid(u, v):
            continue
        # collapse u -> v
        shared = vtris[u] & vtris[v]
        for k in shared:
            alive[k] = False
            for i in T[k]:
                vtris[i].discard(k)
        for k in list(vtris[u]):
            T[k] = [v if i == u else i for i in T[k]]
            vtris[v].add(k)
        vtris[u] = set()
        removed[u] = True
        _quad_add(Q[v], Q[u])
        for w in border_nb[u]:
            border_nb[w].discard(u)
            if w != v:
                border_nb[w].add(v)
                border_nb[v].add(w)
        border_nb[v].discard(u)
        border_nb[u] = set()
        collapses += 1
        for w in neighbours(v):
            heapq.heappush(heap, (cost(v, w), v, w))
            heapq.heappush(heap, (cost(w, v), w, v))
    out = [T[k] for k in range(len(T)) if alive[k]]
    return out, collapses


def decimate(polys, e_max=0.3, e_border=0.05):
    """polys [(mat, [(pos, uv, nrm, rgb)])] of ONE unit -> (simplified polys (triangles, flat normals), stats). The bound is
    checked by measurement: every source vertex lies within e_max (+ 1 mm) of the simplified surface of its material."""
    by_mat = {}
    for mat, p in polys:
        by_mat.setdefault(mat, []).append(p)
    out, st = [], {"tris_in": 0, "tris_out": 0, "max_err": 0.0, "collapses": 0}
    for mat, ps in sorted(by_mat.items()):
        m = _weld(ps)
        tris, nc = simplify_mesh(m, e_max, e_border)
        st["tris_in"] += len(m.tris)
        st["tris_out"] += len(tris)
        st["collapses"] += nc
        P = [v[0] for v in m.verts]
        # measured error: every source vertex to the simplified surface (same material)
        boxes = []
        for t in tris:
            a, b, c = (P[i] for i in t)
            boxes.append(([min(a[k], b[k], c[k]) for k in range(3)], [max(a[k], b[k], c[k]) for k in range(3)], a, b, c))
        for p in P:
            best = 1e9
            for lo, hi, a, b, c in boxes:
                if any(p[k] < lo[k] - 1.0 or p[k] > hi[k] + 1.0 for k in range(3)):
                    continue
                best = min(best, pt_tri_dist(p, a, b, c))
                if best < 1e-6:
                    break
            st["max_err"] = max(st["max_err"], best)
        # the other direction: simplified surface samples (centroids, edge midpoints) to the source surface
        src = []
        for t in m.tris:
            a, b, c = (P[i] for i in t)
            src.append(([min(a[k], b[k], c[k]) for k in range(3)], [max(a[k], b[k], c[k]) for k in range(3)], a, b, c))
        for t in tris:
            a, b, c = (P[i] for i in t)
            for p in ((tuple((a[k] + b[k] + c[k]) / 3 for k in range(3))), tuple((a[k] + b[k]) / 2 for k in range(3)),
                      tuple((b[k] + c[k]) / 2 for k in range(3)), tuple((c[k] + a[k]) / 2 for k in range(3))):
                best = 1e9
                for lo, hi, x, y, z in src:
                    if any(p[k] < lo[k] - 1.0 or p[k] > hi[k] + 1.0 for k in range(3)):
                        continue
                    best = min(best, pt_tri_dist(p, x, y, z))
                    if best < 1e-6:
                        break
                st["max_err"] = max(st["max_err"], best)
        for t in tris:
            a, b, c = (P[i] for i in t)
            n = _cross(_sub(b, a), _sub(c, a))
            L = _norm(n) or 1.0
            n = (n[0] / L, n[1] / L, n[2] / L)
            out.append((mat, [(m.verts[i][0], m.verts[i][1], n, m.verts[i][3]) for i in t]))
    need(st["max_err"] <= e_max + 1e-3, "LOD decimation error %.3f m above the bound %.3f m" % (st["max_err"], e_max))
    st["max_err"] = round(st["max_err"], 4)
    return out, st
