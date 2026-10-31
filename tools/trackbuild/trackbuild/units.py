"""trackbuild.units - spatial partitioning into streamed units.

A unit is the region between two cut lines across the route (at stations cut_from / cut_to, normals = the route tangent)
and two lateral lines parallel to the unit chord. This is exactly B3's LOD region quad (LOD +0x70 A[4], +0x80 C[4], +0x90
B[4]; a point (x, z) is inside when A*x + C*z - B >= 0 on all four lanes; consecutive units share one negated lane), and the
mesh block's culling prism uses the quad's four corners (+0x10..+0x4F, y = lowest point, height in corner 0's w).
Render polygons are CLIPPED to their unit (Sutherland-Hodgman, attributes interpolated); collision polygons are copied
whole into every unit whose region, grown by `coll_margin`, they touch (the car queries only its own unit's tree)."""
import math

from .io import SourceError, need


class Unit:
    def __init__(self, k, lanes, corners, cut_from, cut_to):
        self.k, self.lanes, self.corners = k, lanes, corners
        self.cut_from, self.cut_to = cut_from, cut_to
        self.polys = []        # (material, [(pos, uv, nrm, rgb)])
        self.coll = []         # (surface, [pos...]) 3 or 4 points

    def inside(self, x, z, grow=0.0):
        return all(a * x + c * z - b >= -grow for a, c, b in self.lanes)


def _line(nx, nz, px, pz):
    L = math.hypot(nx, nz)
    nx, nz = nx / L, nz / L
    return (nx, nz, nx * px + nz * pz)


def _isect(l1, l2):
    a1, c1, b1 = l1
    a2, c2, b2 = l2
    det = a1 * c2 - a2 * c1
    need(abs(det) > 1e-9, "unit region: parallel boundary lines")
    return ((b1 * c2 - b2 * c1) / det, (a1 * b2 - a2 * b1) / det)


def make_units(desc):
    st = desc["stations"]
    out = []
    for k, u in enumerate(desc["units"]):
        A, B = st[u["cut_from"]], st[u["cut_to"]]
        ax, az = A["p"][0], A["p"][2]
        bx, bz = B["p"][0], B["p"][2]
        start = _line(A["t"][0], A["t"][1], ax, az)                     # forward of the start cut
        end = _line(-B["t"][0], -B["t"][1], bx, bz)                     # behind the end cut
        mx, mz = u["chord_normal"]
        lo, hi = u["lateral"]
        lat_lo = _line(mx, mz, ax + mx * lo, az + mz * lo)               # m . (x - A) >= lo
        lat_hi = _line(-mx, -mz, ax + mx * hi, az + mz * hi)             # m . (x - A) <= hi
        lanes = [start, lat_hi, end, lat_lo]
        cs = [_isect(start, lat_lo), _isect(start, lat_hi), _isect(end, lat_hi), _isect(end, lat_lo)]
        # convexity: every corner inside every lane (tolerance 1 mm)
        for c in cs:
            need(all(a * c[0] + cc * c[1] - b >= -1e-3 for a, cc, b in lanes), "unit %d: region quad is not convex" % k)
        # corner order: anticlockwise in (x, z) as retail (cross of the first two edges > 0)
        e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        if e1[0] * e2[1] - e1[1] * e2[0] < 0:
            cs = cs[::-1]
        out.append(Unit(k, lanes, cs, u["cut_from"], u["cut_to"]))
    # neighbours share one negated lane (retail 36 / 36)
    n = len(out)
    for k in range(n):
        a, b = out[k].lanes[2], out[(k + 1) % n].lanes[0]
        need(all(abs(x + y) < 1e-6 for x, y in zip(a, b)), "units %d / %d do not share a negated cut lane" % (k, (k + 1) % n))
    return out


def clip(poly, lane):
    """Sutherland-Hodgman against one lane (a, c, b): keep a*x + c*z - b >= 0; vertices (pos, uv, nrm, rgb)"""
    a, c, b = lane
    out = []
    m = len(poly)
    for i in range(m):
        P, Q = poly[i], poly[(i + 1) % m]
        dp = a * P[0][0] + c * P[0][2] - b
        dq = a * Q[0][0] + c * Q[0][2] - b
        if dp >= -1e-7:
            out.append(P)
        if (dp >= -1e-7) != (dq >= -1e-7):
            t = dp / (dp - dq)
            lerp = lambda u, v: tuple(x + (y - x) * t for x, y in zip(u, v))  # noqa: E731
            out.append((lerp(P[0], Q[0]), lerp(P[1], Q[1]), P[2] if t < 0.5 else Q[2], lerp(P[3], Q[3])))
    # drop consecutive duplicates
    res = []
    for v in out:
        if not res or max(abs(x - y) for x, y in zip(res[-1][0], v[0])) > 1e-6:
            res.append(v)
    if len(res) > 1 and max(abs(x - y) for x, y in zip(res[0][0], res[-1][0])) <= 1e-6:
        res.pop()
    return res


def assign(units, obj, materials, coll_margin=6.0):
    """render polygons clipped into units; collision polygons copied into every unit they touch (grown region)"""
    stats = {"render_in": len(obj["faces"]), "render_pieces": 0, "render_unassigned": 0, "coll_copies": 0, "coll_unassigned": 0}
    for mat, fv in obj["faces"]:
        need(mat in materials, "OBJ material %r is not described in the track description" % mat)
        pts = [q[0] for q in fv]
        area = 0.0
        for i in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[i], pts[i + 1]
            cr = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
                  (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
                  (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            area += 0.5 * sum(x * x for x in cr) ** 0.5
        need(area > 1e-4, "degenerate (zero-area) %s face at %s: remove it from the source" % (mat, pts[0]))
        placed = False
        for u in units:
            # quick reject: centroid far outside
            p = fv
            for lane in u.lanes:
                p = clip(p, lane)
                if len(p) < 3:
                    break
            if len(p) >= 3:
                u.polys.append((mat, p))
                stats["render_pieces"] += 1
                placed = True
        if not placed:
            stats["render_unassigned"] += 1
        m = materials[mat]
        if m.get("collide"):
            hit = False
            for u in units:
                if any(u.inside(q[0][0], q[0][2], coll_margin) for q in fv):
                    u.coll.append((int(m["surface"], 16), [q[0] for q in fv]))
                    stats["coll_copies"] += 1
                    hit = True
            stats["coll_unassigned"] += not hit
    return stats


def coverage(units, samples):
    """-> list of (point, count of units holding it) for points not held by exactly one unit"""
    bad = []
    for x, z in samples:
        c = sum(1 for u in units if u.inside(x, z))
        if c != 1:
            bad.append(((x, z), c))
    return bad


def fan(poly):
    """polygon -> triangles (index triples into poly), fan from vertex 0 (clipped convex pieces)"""
    return [(0, i, i + 1) for i in range(1, len(poly) - 1)]
