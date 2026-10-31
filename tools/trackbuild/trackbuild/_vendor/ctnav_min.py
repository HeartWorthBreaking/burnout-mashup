"""ctnav_min - the route checks trackbuild's validator uses: camera_hazards / planner_hazards (ctnav.camera) and the
start-grid search model assign / slots (ctnav.grid). Functions copied VERBATIM (provenance in VENDOR.json); camera_hazards
needs only the segment length, so ctnav.checks -> e2_steer_model.Geo is replaced by the same Geo class (copied verbatim,
renamed _Geo). Model results, not runtime proof."""
import math
import struct


class _Geo:
    def __init__(self, route):
        self.r = route

    def lane(self, L):
        return self.r.lanes[L]

    def count(self, L):
        return len(self.r.lanes[L]["segs"])

    def cyclic(self, L):
        return bool(self.r.lanes[L]["flags"] & 1)

    def nodes(self, L, g):
        a, b = self.r.lanes[L]["rungs"][g]
        return self.r.pos[a][:3], self.r.pos[b][:3], a == b

    def xzw(self, L, g):
        n0, n1, _ = self.nodes(L, g)
        return math.hypot(n1[0] - n0[0], n1[2] - n0[2])

    def cum(self, L, k):
        return self.r.lanes[L]["dims"][k][0] if k >= 0 else 0.0

    def Lx(self, L, x):
        """sub_00174BE0's L(x): interpolated cumulative length at fractional rung position x (clamped to count)"""
        n = self.count(L)
        f = min(int(math.floor(x)), n)
        base = self.cum(L, f - 1) if f - 1 >= 0 else 0.0
        if f < n:
            return base + (self.cum(L, f) - base) * (x - f)
        return base

    def dir3(self, L, s):
        """sub_00174740: sum of rungs s+2, s+3 nodes minus rungs s, s+1 (non-cyclic ends use rung count)"""
        n = self.count(L)
        R = self.r.lanes[L]["rungs"]

        def s4(g):
            a, b = R[g]
            return add(self.r.pos[a][:3], self.r.pos[b][:3])
        if self.cyclic(L):
            ah = add(s4((s + 2) % n), s4((s + 3) % n))
        elif s < n - 2:
            ah = add(s4(s + 2), s4(min(s + 3, n)))
        else:
            ah = add(s4(n), s4(n))
        return sub(ah, add(s4(s), s4(s + 1)))

    def seglen(self, L, s):
        return self.cum(L, s) - (self.cum(L, s - 1) if s > 0 else 0.0)

    def t_of(self, L, s, car):
        """sub_00175860 (via sub_001782B0); sub_001792F0 then clamps to [0, 1]"""
        n0, _, _ = self.nodes(L, s)
        sl = self.seglen(L, s) or 1e-9
        t = min(1.0, dot(sub(car, n0), unit(self.dir3(L, s))) / sl)
        return max(0.0, min(1.0, t))

    def lateral(self, L, g, p):
        """sub_00175930 (margin 0): dot3(p - node0, unit3(node1 - node0)) / xz width; zero-width rung -> 0.5"""
        n0, n1, z = self.nodes(L, g)
        if z:
            return 0.5
        w = self.xzw(L, g)
        return dot(sub(p, n0), unit(sub(n1, n0))) / w if w else 0.5

    def cp(self, L, g, lam):
        """sub_00178AD0 (zero-width rung -> node0)"""
        n0, n1, z = self.nodes(L, g)
        if z:
            return list(n0)
        return add(n0, mul(unit(sub(n1, n0)), self.xzw(L, g) * lam))

    def window(self, L, s):
        """sub_00178D20 -> 6 rung indices, or None if count < 6"""
        n = self.count(L)
        if n < 6:
            return None
        if self.cyclic(L):
            return [(s + k) % n for k in range(-1, 5)]
        sp = max(1, min(s, n - 5))
        return [sp + k for k in range(-1, 5)]

    def edge_point(self, L, g, side, margin):
        """sub_001778C0 / sub_00177B90 base: side 1 -> node0 moved toward node1, else node1 moved toward node0"""
        n0, n1, z = self.nodes(L, g)
        if side == 1:
            return add(n0, mul(unit(sub(n1, n0)), margin))
        return add(n1, mul(unit(sub(n0, n1)), margin))


EDGE, CORRIDOR, NONE = 4, 5, 0xFF


def _kind(r, L, s):
    return r.lanes[L]["segs"][s][2] & 7


def walk(r, L, s, side):
    """sub_001752A0 with flag 1: (result (lane, seg) or None, hazard text or None)"""
    li, si = (3, 5) if side == 0 else (4, 6)
    g = r.lanes[L]["segs"][s]
    if g[li] == NONE:
        return (L, s), None
    for _ in range(64):
        Y, j = g[li], g[si]
        if Y >= len(r.lanes) or j >= len(r.lanes[Y]["segs"]):
            return None, "walk to (%d, %d) out of range" % (Y, j)
        if _kind(r, Y, j) in (EDGE, CORRIDOR):
            return (Y, j), None
        g = r.lanes[Y]["segs"][j]
        if g[li] == NONE:
            return None, "walk side %d arrives on (%d, %d): unchecked NONE (0x001752FE)" % (side, Y, j)
    return None, "walk does not stop in 64 hops"


def camera_hazards(r, reach=50.0):
    geo = _Geo(r)
    tails, out = {}, []
    for X, L in enumerate(r.lanes):
        for s in range(len(L["segs"])):
            for side in (0, 1):
                res, hz = walk(r, X, s, side)
                if hz:
                    out.append(("walk", (X, s, side, hz)))
                    continue
                Y, j = res
                if r.lanes[Y]["flags"] & 0xFF:
                    continue
                n = len(r.lanes[Y]["segs"])
                if Y not in tails:
                    t = [0.0] * (n + 1)
                    for k in range(n - 1, -1, -1):
                        t[k] = t[k + 1] + geo.seglen(Y, k)
                    tails[Y] = t
                if tails[Y][j] > reach:
                    continue
                li = 3 if side == 0 else 4
                if r.lanes[Y]["segs"][n - 1][li] == NONE:
                    out.append(("lane_end", (X, s, side, Y, "unchecked NONE at the end of non-cyclic lane %d (0x0016353E)" % Y)))
    return out


def planner_hazards(r):
    return [(L, s, side, g[si], g[li]) for L, lane in enumerate(r.lanes) for s, g in enumerate(lane["segs"])
            if _kind(r, L, s) != CORRIDOR for side, (li, si) in ((0, (3, 5)), (1, (4, 6))) if g[si] >= 0xFFF8]


def _centres(r, box=None):
    out = []
    for li, L in enumerate(r.lanes):
        for k in range(len(L["segs"])):
            a0, b0 = L["rungs"][k]
            a1, b1 = L["rungs"][k + 1]
            c = [0.25 * (r.pos[a0][i] + r.pos[b0][i] + r.pos[a1][i] + r.pos[b1][i]) for i in range(3)]
            if box is None or (box[0] <= c[0] <= box[1] and box[2] <= c[2] <= box[3]):
                out.append((c, li, k, L["segs"][k][0]))
    return out


class Assigner:
    """sub_00174CF0 over all lanes (optionally restricted to centres inside a box that must contain every candidate
    nearer than the reference winner - the caller's box is padded by `pad` metres)"""

    def __init__(self, r, points=None, pad=150.0):
        box = None
        if points:
            xs, zs = [p[0] for p in points], [p[2] for p in points]
            box = (min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad)
        self.c = _centres(r, box)

    def assign(self, p):
        best = None
        for c, li, k, sl in self.c:                  # lane order then segment order = the game's order: strict minimum
            d = (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 + (c[2] - p[2]) ** 2
            if best is None or d < best[0]:
                best = (d, li, k, sl)
        return best[1], best[2], best[3], math.sqrt(best[0])


def assign(r, p):
    return Assigner(r).assign(p)


def slots(b):
    n = struct.unpack_from("<I", b, 0x260)[0]
    out = []
    for e in range(n):
        o = struct.unpack_from("<I", b, 0x198 + 4 * e)[0]
        page = struct.unpack_from("<I", b, o + 0x3C0)[0]
        for k in range(6):
            p = struct.unpack_from("<3f", b, page + 0x30 + 0x50 * k)
            if all(math.isfinite(x) for x in p) and any(x != 0 for x in p):
                out.append((e, page, k, p))
    return out
