"""trackbuild.visibility - a conservative per-unit visibility (PVS) generator for tracks of any unit count.

B3's PVS (KB STREAMING_AND_VISIBILITY s3, sub_0019D100): every full (mesh) block lists 17 entries, rel 0, -1..-8, +1..+8 from
that unit; the draw takes the CENTRE unit's 17 entries and keeps an entry only if the CAMERA unit's block lists the same unit
with flag 1; |rel| <= 4 from the centre draws the target's mesh block, 5..8 its LOD block. Units further than +-8 can never be
drawn (the low ring holds +-8). So a generated PVS must (1) flag every unit a camera in unit k can see, and (2) be satisfiable:
everything visible from k must lie inside k's +-8 window (else it would pop in / be missing).

Model (2.5-D, conservative for occlusion): occluders are the near-vertical faces of the authored render geometry (walls,
barriers, buildings) as xz segments with a bottom / top height; floors / terrain never occlude (ignoring them only adds
visibility). Camera samples: road positions of the unit (stations x lateral offsets) at several heights (chase camera up to
6 m). Target samples: every vertex and face centre of the target unit's render polygons (sub-sampled). A target unit is
visible from camera unit k if ANY camera sample sees ANY target sample (a ray whose xz projection crosses no occluder segment
below the ray's height there). Rays end 0.1 m before the target so a sample on a wall is not hidden by its own wall."""
import math
import random

from .io import need

CELL = 10.0


class Occluders:
    def __init__(self, segs):
        self.segs = segs                                     # [(x0, z0, x1, z1, ybot, ytop)]
        self.grid = {}
        for i, (x0, z0, x1, z1, yb, yt) in enumerate(segs):
            for cx in range(int(math.floor(min(x0, x1) / CELL)), int(math.floor(max(x0, x1) / CELL)) + 1):
                for cz in range(int(math.floor(min(z0, z1) / CELL)), int(math.floor(max(z0, z1) / CELL)) + 1):
                    self.grid.setdefault((cx, cz), []).append(i)

    def blocked(self, p, q):
        """segment p -> q (3-D) blocked by an occluder?"""
        x0, y0, z0 = p
        x1, y1, z1 = q
        dx, dz = x1 - x0, z1 - z0
        L = math.hypot(dx, dz)
        if L < 1e-6:
            return False
        tend = max(0.0, 1.0 - 0.1 / L)
        seen = set()
        # DDA over the grid cells the xz segment crosses
        cx, cz = int(math.floor(x0 / CELL)), int(math.floor(z0 / CELL))
        ex, ez = int(math.floor(x1 / CELL)), int(math.floor(z1 / CELL))
        sx = 1 if dx > 0 else -1
        sz = 1 if dz > 0 else -1
        tmx = ((cx + (sx > 0)) * CELL - x0) / dx if dx else float("inf")
        tmz = ((cz + (sz > 0)) * CELL - z0) / dz if dz else float("inf")
        tdx = CELL / abs(dx) if dx else float("inf")
        tdz = CELL / abs(dz) if dz else float("inf")
        for _ in range(100000):
            for i in self.grid.get((cx, cz), ()):
                if i in seen:
                    continue
                seen.add(i)
                ax, az, bx, bz, yb, yt = self.segs[i]
                ex_, ez_ = bx - ax, bz - az
                den = dx * ez_ - dz * ex_
                if abs(den) < 1e-12:
                    continue
                t = ((ax - x0) * ez_ - (az - z0) * ex_) / den
                u = ((ax - x0) * dz - (az - z0) * dx) / den
                if 1e-4 < t < tend and -1e-6 <= u <= 1 + 1e-6:
                    y = y0 + (y1 - y0) * t
                    if yb - 0.05 <= y <= yt:
                        return True
            if cx == ex and cz == ez:
                break
            if tmx < tmz:
                if tmx > 1:
                    break
                cx += sx
                tmx += tdx
            else:
                if tmz > 1:
                    break
                cz += sz
                tmz += tdz
        return False


def occluders_from_polys(polys, max_ny=0.3):
    """one occluder per (convex) near-vertical polygon: its xz footprint segment between the extreme projections along the
    polygon's horizontal direction, bottom = its lowest point, top = the LOWER of the column tops at the two footprint ends
    (a trapezoid or sloped edge occludes only up to its lower end: conservative)"""
    segs = []
    for mat, poly in polys:
        pts = [q[0] for q in poly]
        n = [0.0, 0.0, 0.0]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            n[0] += (a[1] - b[1]) * (a[2] + b[2])
            n[1] += (a[2] - b[2]) * (a[0] + b[0])
            n[2] += (a[0] - b[0]) * (a[1] + b[1])
        L = math.sqrt(sum(x * x for x in n))
        if L < 1e-9 or abs(n[1]) / L > max_ny:
            continue
        hx, hz = -n[2], n[0]                                  # horizontal direction inside the polygon plane
        hl = math.hypot(hx, hz)
        if hl < 1e-9:
            continue
        hx, hz = hx / hl, hz / hl
        proj = [(p[0] * hx + p[2] * hz, p[1], p) for p in pts]
        lo = min(s for s, _, _ in proj)
        hi = max(s for s, _, _ in proj)
        if hi - lo < 0.05:
            continue
        m = len(proj)

        def extent(s):
            """vertical extent (bottom, top) of the polygon's section at horizontal position s"""
            ys = []
            for i in range(m):
                s0, y0_, _ = proj[i]
                s1, y1_, _ = proj[(i + 1) % m]
                if abs(s1 - s0) < 1e-9:
                    if abs(s - s0) < 1e-6:
                        ys += [y0_, y1_]
                    continue
                t = (s - s0) / (s1 - s0)
                if -1e-9 <= t <= 1 + 1e-9:
                    ys.append(y0_ + (y1_ - y0_) * t)
            return (min(ys), max(ys)) if ys else (0.0, -1.0)

        # the largest rectangle [sa, sb] x [bottom, top] inside the polygon among a few spans (full span for a wall quad,
        # the middle part for a triangle): the occluder never covers more than the polygon does (conservative)
        best = None
        for fa in (0.0, 0.25, 0.5):
            for fb in (0.0, 0.25, 0.5):
                sa, sb = lo + (hi - lo) * fa, hi - (hi - lo) * fb
                if sb - sa < 0.05:
                    continue
                samples = [sa, sb] + [s for s, _, _ in proj if sa < s < sb]
                ext = [extent(s) for s in samples]
                bot, top = max(e[0] for e in ext), min(e[1] for e in ext)
                if top - bot >= 0.3 and (best is None or (sb - sa) * (top - bot) > best[0]):
                    best = ((sb - sa) * (top - bot), sa, sb, bot, top)
        if best is None:
            continue
        _, sa, sb, bot, top = best
        # footprint points: the plane's horizontal line through the polygon (s along (hx, hz), offset along the normal)
        nx_, nz_ = n[0] / math.hypot(n[0], n[2]), n[2] / math.hypot(n[0], n[2])
        off = sum(p[0] * nx_ + p[2] * nz_ for p in pts) / m
        ax, az = hx * sa + nx_ * off, hz * sa + nz_ * off
        bx, bz = hx * sb + nx_ * off, hz * sb + nz_ * off
        # close the sub-millimetre joints between neighbouring wall pieces (OBJ coordinates are rounded to 0.1 mm): each
        # full-span footprint is extended by 2 cm at both ends (the only non-conservative step; 2 cm of a wall)
        L = math.hypot(bx - ax, bz - az)
        ex = (bx - ax) / L * 0.02 if sa == lo else 0.0
        ez = (bz - az) / L * 0.02 if sa == lo else 0.0
        fx = (bx - ax) / L * 0.02 if sb == hi else 0.0
        fz = (bz - az) / L * 0.02 if sb == hi else 0.0
        segs.append((ax - ex, az - ez, bx + fx, bz + fz, bot, top))
    return segs


def merge_coplanar_pairs(tris, tol=0.01):
    """triangle soup [(a, b, c)] -> polygons: two triangles sharing an edge and lying in one plane become one quad (so the
    occluder of a wall made of strips covers the full wall, not two half-triangles)"""
    def key(p):
        return tuple(round(x, 3) for x in p)
    norms = []
    for a, b, c in tris:
        n = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
             (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        L = math.sqrt(sum(x * x for x in n)) or 1.0
        norms.append((n[0] / L, n[1] / L, n[2] / L))
    edge = {}
    for i, t in enumerate(tris):
        for e in ((0, 1), (1, 2), (2, 0)):
            k = tuple(sorted((key(t[e[0]]), key(t[e[1]]))))
            edge.setdefault(k, []).append((i, e))
    used = [False] * len(tris)
    out = []
    for i, t in enumerate(tris):
        if used[i]:
            continue
        merged = False
        for e in ((0, 1), (1, 2), (2, 0)):
            k = tuple(sorted((key(t[e[0]]), key(t[e[1]]))))
            for j, e2 in edge.get(k, ()):
                if j == i or used[j]:
                    continue
                ni, nj = norms[i], norms[j]
                if abs(sum(x * y for x, y in zip(ni, nj))) < 0.999:
                    continue
                other = [p for p in tris[j] if key(p) not in k]
                if len(other) != 1:
                    continue
                d = sum((other[0][q] - t[0][q]) * ni[q] for q in range(3))
                if abs(d) > tol:
                    continue
                apex = t[3 - e[0] - e[1]]
                out.append([apex, t[e[0]], other[0], t[e[1]]])
                used[i] = used[j] = True
                merged = True
                break
            if merged:
                break
        if not merged:
            used[i] = True
            out.append(list(t))
    return out


def compute(units, desc, cam_heights=(1.5, 3.5, 6.0), target_max=150, seed=1, dilate=1):
    """-> (vis[k] = set of units visible from camera unit k, stats)"""
    U = len(units)
    allp = [p for u in units for p in u.polys]
    occ = Occluders(occluders_from_polys(allp))
    st = desc["stations"]
    rng = random.Random(seed)
    cams = []
    for u in units:
        cs = []
        k = u.cut_from
        idxs = []
        while True:
            idxs.append(k % len(st))
            if k % len(st) == u.cut_to:
                break
            k += 1
        for i in idxs[::3] + [idxs[-1]]:
            s_ = st[i]
            nx, nz = -s_["t"][1], s_["t"][0]
            lo, hi = s_["offsets"][1] + 1.0, s_["offsets"][4] - 1.0
            for o in (lo, (lo + hi) / 2, hi):
                for h in cam_heights:
                    p = (s_["p"][0] + nx * o, s_["p"][1] + h, s_["p"][2] + nz * o)
                    if u.inside(p[0], p[2], 0.01):
                        cs.append(p)
        cams.append(cs)
    targets = []
    for u in units:
        pts = set()
        for mat, poly in u.polys:
            for q in poly:
                pts.add(tuple(round(c, 3) for c in q[0]))
            c = tuple(sum(q[0][k] for q in poly) / len(poly) for k in range(3))
            pts.add(tuple(round(x, 3) for x in c))
        pts = sorted(pts)
        if len(pts) > target_max:
            pts = rng.sample(pts, target_max)
        targets.append(pts)
    vis = [set() for _ in range(U)]
    rays = 0
    for k in range(U):
        for j in range(U):
            d = min((j - k) % U, (k - j) % U)
            if d <= 1:
                vis[k].add(j)
                continue
            found = False
            for c in cams[k]:
                for t in targets[j]:
                    rays += 1
                    if not occ.blocked(c, t):
                        found = True
                        break
                if found:
                    break
            if found:
                vis[k].add(j)
    raw = [set(v) for v in vis]
    if dilate:                                  # sampling safety margin: the neighbours of every visible unit (inside +-8)
        for k in range(U):
            extra = set()
            for j in raw[k]:
                for d in range(-dilate, dilate + 1):
                    t = (j + d) % U
                    fwd, back = (t - k) % U, (k - t) % U
                    if min(fwd, back) <= 8:
                        extra.add(t)
            vis[k] |= extra
    return vis, {"occluder_segments": len(occ.segs), "rays": rays, "cameras": sum(map(len, cams)),
                 "targets": sum(map(len, targets)), "dilate": dilate,
                 "added_by_dilation": sum(len(vis[k] - raw[k]) for k in range(U))}


def ring_check(vis, U, ahead_warn=4):
    """-> (errors, warnings): a visible unit outside the camera unit's +-8 window = error (never drawable); beyond +4 ahead
    = warning (drawable only while the ring centre keeps up with the camera)"""
    errs, warns = [], []
    for k in range(U):
        for j in vis[k]:
            fwd, back = (j - k) % U, (k - j) % U
            rel = fwd if fwd <= back else -back
            if abs(rel) > 8:
                errs.append((k, j, rel))
            elif rel > ahead_warn:
                warns.append((k, j, rel))
    return errs, warns
