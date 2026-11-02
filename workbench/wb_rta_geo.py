"""wb_rta_geo - small geometry helpers for retail-style track authoring (Workbench 0.33 retail-style authoring, 2026-11-01).

RouteIndex: nearest point on a retail route centre line (the S4 lanes' rung mid-points as decoded by wb_retail) with arc length
and signed lateral offset; a uniform grid keeps queries O(1)-ish. Pure stdlib; game frame (Y up, plan = x z).
"""
import math


def pct(vals, q):
    """q-th percentile (0..100) of a list, linear interpolation; None for an empty list"""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q / 100.0
    i = int(math.floor(k))
    j = min(i + 1, len(s) - 1)
    return s[i] + (s[j] - s[i]) * (k - i)


def stats(vals, nd=2):
    if not vals:
        return {'n': 0}
    return {'n': len(vals), 'p10': round(pct(vals, 10), nd), 'median': round(pct(vals, 50), nd), 'p90': round(pct(vals, 90), nd),
            'min': round(min(vals), nd), 'max': round(max(vals), nd)}


def tri_geo(a, b, c):
    """-> (area m2, unit normal (x, y, z), centroid)"""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    cen = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3)
    if ln == 0:
        return 0.0, (0.0, 0.0, 0.0), cen
    return ln / 2, (nx / ln, ny / ln, nz / ln), cen


class RouteIndex:
    """polylines (list of point lists, each [x, y, z]); cyclic flags per polyline. Samples every `step` m."""

    def __init__(self, lines, cyclic=None, step=2.0, cell=16.0):
        self.cell = cell
        self.samples = []          # (x, y, z, s, line, tx, tz)
        self.lengths = []
        for li, pts in enumerate(lines):
            cyc = bool(cyclic and cyclic[li])
            seq = list(pts) + ([pts[0]] if cyc and len(pts) > 2 else [])
            s = 0.0
            for k in range(len(seq) - 1):
                a, b = seq[k], seq[k + 1]
                dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                d = math.hypot(dx, dz)
                if d <= 1e-6:
                    continue
                tx, tz = dx / d, dz / d
                n = max(1, int(d / step))
                for i in range(n):
                    f = i / n
                    self.samples.append((a[0] + dx * f, a[1] + dy * f, a[2] + dz * f, s + d * f, li, tx, tz))
                s += d
            self.lengths.append(round(s, 2))
        self.grid = {}
        for i, p in enumerate(self.samples):
            self.grid.setdefault((int(p[0] // cell), int(p[2] // cell)), []).append(i)

    def nearest(self, x, z, max_r=400.0):
        """-> (distance in plan, sample) or (None, None) beyond max_r"""
        c = self.cell
        cx, cz = int(x // c), int(z // c)
        best, bi = None, None
        r = 0
        while r * c <= max_r + c:
            for i in range(cx - r, cx + r + 1):
                for k in range(cz - r, cz + r + 1):
                    if max(abs(i - cx), abs(k - cz)) != r:
                        continue
                    for j in self.grid.get((i, k), ()):
                        p = self.samples[j]
                        d = (p[0] - x) ** 2 + (p[2] - z) ** 2
                        if best is None or d < best:
                            best, bi = d, j
            if best is not None and math.sqrt(best) <= (r - 1) * c:
                break
            r += 1
        if best is None or math.sqrt(best) > max_r:
            return None, None
        return math.sqrt(best), self.samples[bi]

    def project(self, x, y, z, max_r=400.0):
        """-> dict(dist, lateral (+ = left of travel), s, line, dy) or None"""
        d, p = self.nearest(x, z, max_r)
        if p is None:
            return None
        lat = (x - p[0]) * (-p[6]) + (z - p[2]) * p[5]      # left normal (-tz, tx)
        return {'dist': d, 'lateral': lat, 's': p[3], 'line': p[4], 'dy': y - p[1]}


def route_lines(view):
    """main route polylines from a wb_retail view. wb_retail reports the ct2_route lane flag (1 = the cyclic main-line lanes,
    MEASURED on US/C1_V1: 6 lanes x 1119 rungs). Main lanes are used when present (cyclic), else every lane with >= 4 points
    (point-to-point tracks: chained non-cyclic lanes, format_research 1)."""
    lanes = [ln for ln in (view.get('route') or {}).get('lanes') or [] if len(ln.get('centre') or []) >= 4]
    main = [ln for ln in lanes if ln.get('flags') == 1]
    if main:
        return [ln['centre'] for ln in main], [True] * len(main)
    return [ln['centre'] for ln in lanes], [False] * len(lanes)
