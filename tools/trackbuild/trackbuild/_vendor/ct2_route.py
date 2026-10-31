"""ct2_route - Burnout 3 S4 (AI route, version 3) model + deterministic writer + validator (CUSTOM-TRACK-2).

Model (all decoded; nothing copied except the zone block's unknown words and the corner records' unknown fields, which are
carried as values): header counts, zones, node positions (vec4), lanes {flags, rungs, dims, segments}, distances, corners.
Layout rules (verified by `identity` on every track): header 0x24 | zones 0x8C | positions at 0xB0 | lane entries | per lane
rungs, dims, segments, each array 16-aligned | distances 16-aligned | corners 16-aligned | zero padding to the section size.
Validator `check(model)`: every rule a writer must keep (see VALIDATION in NAV_FORMAT.md).
   py -3 -B ct2_route.py identity [TRACK ...]"""
import math
import struct
import sys
from pathlib import Path

from . import ct2_s4 as S  # noqa: E402   (vendored: package-relative import)

NONE = 0xFF
# PS2 (TKB) said 63 (route-lane table), but retail EU/P1_V1 / V2 have 64 lanes [XD], so 63 is not the limit; the Xbox
# table capacity is taken from the code (NAV_FORMAT.md). Until then the retail maximum is the ceiling a writer may use.
MAX_LANES = 64


class RouteError(Exception):
    pass


def al16(x):
    return x + (-x) % 16


class Route:
    @classmethod
    def parse(cls, b):
        r = cls()
        h = S.header(b)
        if h["version"] != 3:
            raise RouteError("S4 version %d (Burnout 3 is 3)" % h["version"])
        r.size = len(b)
        r.zones_raw = b[0x24:0xB0]
        r.nzones = h["zones"]
        r.slices = h["slices"]
        npos = (h["p_lanes"] - h["p_pos"]) // 16
        r.pos = [list(struct.unpack_from("<4f", b, h["p_pos"] + 16 * k)) for k in range(npos)]
        r.lanes = []
        for l in S.lanes(b, h):
            n = l["n"]
            r.lanes.append({"flags": l["flags"],
                            "rungs": [list(struct.unpack_from("<2H", b, l["rungs"] + 4 * k)) for k in range(n + 1)],
                            "dims": [list(struct.unpack_from("<2f", b, l["dims"] + 8 * k)) for k in range(n)],
                            "segs": [list(struct.unpack_from("<hBBBBHH", b, l["segs"] + 10 * k)) for k in range(n)]})
        r.dist = [list(struct.unpack_from("<fI", b, h["p_dist"] + 8 * k)) for k in range(h["slices"])]
        r.corners = [b[h["p_corners"] + 12 * k:h["p_corners"] + 12 * k + 12] for k in range(h["corners"])]
        return r

    def serialize(self, size=None, grow=False):
        """size: the slot (default: the parsed section's size); grow=True: the smallest 0x800 multiple >= max(slot, need)"""
        size = size or self.size
        out = bytearray()
        out += bytes(0x24) + self.zones_raw
        assert len(out) == 0xB0
        p_pos = len(out)
        for p in self.pos:
            out += struct.pack("<4f", *p)
        p_lanes = len(out)
        n = len(self.lanes)
        out += bytes(16 * n)
        for i, l in enumerate(self.lanes):
            k = len(l["segs"])
            if len(l["rungs"]) != k + 1 or len(l["dims"]) != k:
                raise RouteError("lane %d: rungs / dims / segments counts disagree" % i)
            offs = []
            for arr, fmt in ((l["rungs"], "<2H"), (l["dims"], "<2f"), (l["segs"], "<hBBBBHH")):
                out += bytes(-len(out) % 16)
                offs.append(len(out))
                for v in arr:
                    out += struct.pack(fmt, *v)
            e = p_lanes + 16 * i
            if k > 0xFFFF or l["flags"] > 0xFFFF:
                raise RouteError("lane %d: count / flags out of range" % i)
            struct.pack_into("<4I", out, e, offs[0] - e, offs[1] - e, offs[2] - e, k | (l["flags"] << 16))
        out += bytes(-len(out) % 16)
        p_dist = len(out)
        for d in self.dist:
            out += struct.pack("<fI", *d)
        out += bytes(-len(out) % 16)
        p_corners = len(out)
        for c in self.corners:
            out += c
        if grow and len(out) > size:
            size = len(out) + (-len(out)) % 0x800
        if len(out) > size:
            raise RouteError("route section needs 0x%X bytes, slot is 0x%X" % (len(out), size))
        struct.pack_into("<9I", out, 0, 3, n, self.slices, len(self.corners), self.nzones, p_lanes, p_dist, p_corners, p_pos)
        out += bytes(size - len(out))
        return bytes(out)


def check(r):
    """structural + semantic rules a route writer must keep -> list of problems (empty = valid)"""
    p = []
    n = len(r.lanes)
    if not 1 <= n <= MAX_LANES:
        p.append("%d lanes (1..%d: the route-lane table)" % (n, MAX_LANES))
    npos = len(r.pos)
    for i, l in enumerate(r.lanes):
        k = len(l["segs"])
        if k == 0:
            p.append("lane %d has no segments" % i)
            continue
        if any(max(rg) >= npos for rg in l["rungs"]):
            p.append("lane %d: rung node outside the %d positions" % (i, npos))
        if any(not (0 <= s[0] < r.slices) for s in l["segs"]):
            p.append("lane %d: segment slice outside 0..%d" % (i, r.slices - 1))
        sl = [s[0] for s in l["segs"]]
        if any(not (b == a + 1 or (a == r.slices - 1 and b == 0)) for a, b in zip(sl, sl[1:])):
            p.append("lane %d: segment slices not consecutive (direction / continuity)" % i)
        if l["flags"] & 1 and k != r.slices:
            p.append("lane %d: cyclic lane with %d segments, %d slices" % (i, k, r.slices))
        for j, s in enumerate(l["segs"]):
            for side, lane_i, seg_i in ((0, s[3], s[5]), (1, s[4], s[6])):
                if lane_i == NONE:
                    continue
                if lane_i >= n or lane_i == i:
                    p.append("lane %d seg %d: link to lane %d" % (i, j, lane_i))
                    break
                o = r.lanes[lane_i]
                if seg_i >= len(o["segs"]):
                    p.append("lane %d seg %d: link to lane %d segment %d of %d" % (i, j, lane_i, seg_i, len(o["segs"])))
                    break
                if o["segs"][seg_i][0] != s[0]:
                    p.append("lane %d seg %d: linked segment is at slice %d, not %d" % (i, j, o["segs"][seg_i][0], s[0]))
                    break
        for j, d in enumerate(l["dims"]):
            if not (math.isfinite(d[0]) and math.isfinite(d[1]) and d[1] > 0):
                p.append("lane %d dim %d: width %r" % (i, j, d[1]))
                break
        cum = [d[0] for d in l["dims"]]
        if any(b < a for a, b in zip(cum, cum[1:])):
            p.append("lane %d: cumulative length decreases" % i)
    if r.nzones > 8:
        p.append("%d zones (8 slots)" % r.nzones)
    if not all(math.isfinite(c) for q in r.pos for c in q[:3]):
        p.append("a node position is not finite")
    d = [x[0] for x in r.dist]
    if any(b < a for a, b in zip(d, d[1:])):
        p.append("race distance decreases")
    for z in range(r.nzones):
        first = struct.unpack_from("<I", r.zones_raw, 16 * z + 12)[0]
        if first >= r.slices:
            p.append("zone %d starts at slice %d of %d" % (z, first, r.slices))
    for k, c in enumerate(r.corners):
        a, m, z, _, lane, _, _ = struct.unpack("<4HBBH", c)
        if lane >= n or max(a, m, z) > len(r.lanes[lane]["segs"]):
            p.append("corner %d: lane %d / segments %d..%d out of range" % (k, lane, a, z))
            break
    return p[:30]


def lint(r):
    """retail conventions that are not format rules (every retail lane keeps them [XD]; the validators do not require them):
    a segment has a neighbour on at least one side; a non-cyclic lane's first and last segments have a neighbour (its
    continuation: PS2 0x00147180 takes the end segment's left link, the right when left is NONE). The PS2 note 'the end
    index must exist on the continuation lane' is violated by about 20 retail lanes, so it is not checked."""
    w = []
    for i, l in enumerate(r.lanes):
        lone = [j for j, s in enumerate(l["segs"]) if s[3] == NONE and s[4] == NONE]
        if lone:
            w.append("lane %d: %d segments without a neighbour (first %d)" % (i, len(lone), lone[0]))
        if not l["flags"] & 1:
            for end, j in (("end", len(l["segs"]) - 1), ("start", 0)):
                s = l["segs"][j]
                if s[3] == NONE and s[4] == NONE:
                    w.append("lane %d %s: no continuation lane" % (i, end))
    return w


def identity(tids=None):
    tids = tids or sorted(p.parent.relative_to(S.BASE).as_posix() for p in S.BASE.glob("*/*/Gamedata.bgd"))
    ok = fails = 0
    probs = {}
    for tid in tids:
        bgd = (S.BASE / tid / "Gamedata.bgd").read_bytes()
        lo, hi = S.s4_of(bgd)
        b = bgd[lo:hi]
        try:
            r = Route.parse(b)
            same = r.serialize(hi - lo) == b
            pr = check(r)
        except (RouteError, struct.error) as e:
            same, pr = False, [repr(e)]
        ok += same
        fails += not same
        if pr:
            probs[tid] = pr[:3]
        print("%-10s lanes %2d slices %4d identical %s check %s" % (tid, len(r.lanes) if same else -1, r.slices if same else -1, same, "OK" if not pr else pr[:2]))
    print("IDENTITY %d / %d" % (ok, ok + fails))
    return ok, fails, probs


if __name__ == "__main__":
    if sys.argv[1] == "identity":
        ok, fails, probs = identity(sys.argv[2:] or None)
        sys.exit(1 if fails else 0)
