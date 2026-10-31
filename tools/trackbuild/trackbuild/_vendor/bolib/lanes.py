"""Geometry of traffic lanes relative to the race direction
(docs/traffic_format.md, section 6).

Used to tell lanes that run WITH the race from oncoming lanes, which is the
difference between Revenge's Traffic Attack traffic sets and its race sets.

Sources, both in GAMEDATA.BGD:
  * lane network S3: per lane a list of node edge pairs into a position
    list, and per node (running distance, width)             [data + in-game]
  * route section S4: groups with flag 1 are full-lap lines. Their first
    array holds edge pairs (u16, u16) into the S4 position list, in lap
    order. The first dozen or so entries of the array, and a few later
    ones, are of another kind (not understood) and give points far from
    their neighbours; only steps of 1..15 m between consecutive entries
    are used (US/L2_V2: 1142 of 1174 in the first line).            [data]
The lap order of those lines is taken as the race direction. Evidence: on
Revenge US/L2_V2 every main lane classified "same way" has more traffic in
the Traffic Attack sets than in the race set, every "oncoming" lane has
less or the same; on US/L2_V1 (the same road raced the other way) every
class flips.
"""
import struct

from . import routes as RT


class LaneError(Exception):
    pass


SAME, ONCOMING, OTHER = "same", "oncoming", "other"
CELL = 25.0


def _sections(bgd, game):
    return RT.rev_sections(bgd) if game == "rev" else RT.b3_sections(bgd)


def lane_network(bgd, game, s3=None):
    """[(centre points [(x,y,z)], running distances [float])] per S3 lane."""
    if s3 is None:
        s = _sections(bgd, game)
        s3 = bgd[s[3]:s[4]]
    ver, pos_at, n = struct.unpack_from("<3I", s3, 0)
    if ver != 0xC:
        raise LaneError("unexpected lane network header")
    npos = (len(s3) - pos_at) // 16
    out = []
    for i in range(n):
        a, b, c, z, cnt = struct.unpack_from("<5I", s3, 12 + 20 * i)
        pts = []
        for k in range(cnt + 1):
            e0, e1 = struct.unpack_from("<HH", s3, a + 4 * k)
            if max(e0, e1) >= npos:
                raise LaneError("lane %d node %d: position index outside the list" % (i, k))
            p0 = struct.unpack_from("<3f", s3, pos_at + 16 * e0)
            p1 = struct.unpack_from("<3f", s3, pos_at + 16 * e1)
            pts.append(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2))
        dist = [struct.unpack_from("<f", s3, b + 8 * k)[0] for k in range(cnt)]
        out.append((pts, dist))
    return out


def lap_steps(bgd, game):
    """[(position, unit direction)] for every clean step of the full-lap
    route lines, plus [(group, clean steps, nodes)]."""
    s = _sections(bgd, game)
    blob = bgd[s[4]:s[5]] if len(s) > 5 and s[5] > s[4] else bgd[s[4]:]
    r = RT.parse(blob, game)
    h = struct.unpack_from("<13I" if game == "rev" else "<9I", blob, 0)
    o_g, o_p = (h[7], h[12]) if game == "rev" else (h[5], h[8])
    npos = (o_g - o_p) // 16
    steps, used = [], []
    for i in range(r["groups"]):
        a, b, c, n, flags = RT.group_arrays(r, i)          # entry-relative pointers (corrected 2026-10-12)
        if not flags & 1:
            continue
        prev, good = None, 0
        for k in range(n + 1):
            e0, e1 = struct.unpack_from("<HH", blob, o_g + a + 4 * k)
            if max(e0, e1) >= npos or e0 + e1 == 0:
                prev = None
                continue
            p0 = struct.unpack_from("<3f", blob, o_p + 16 * e0)
            p1 = struct.unpack_from("<3f", blob, o_p + 16 * e1)
            cur = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2)
            if prev is not None:
                v = (cur[0] - prev[0], cur[1] - prev[1], cur[2] - prev[2])
                ln = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
                if 1.0 < ln < 15.0:
                    steps.append((prev, (v[0] / ln, v[1] / ln, v[2] / ln)))
                    good += 1
            prev = cur
        used.append((i, good, n))
    if len(steps) < 100:
        raise LaneError("no usable full-lap route line (%d clean steps)" % len(steps))
    return steps, used


def classify(lanes, steps, max_dist=100.0):
    """Per lane: {'class', 'forward' (share of nodes heading with the lap),
    'alignment' (mean cosine between lane and lap direction),
    'distance' (median distance to the lap line), 'cover' (share of nodes
    within max_dist of it), 'length'}."""
    grid = {}
    for p, d in steps:
        grid.setdefault((int(p[0] // CELL), int(p[2] // CELL)), []).append((p, d))
    reach = int(max_dist // CELL) + 1
    out = []
    for pts, dist in lanes:
        fwd = tot = 0
        dots = 0.0
        ds = []
        for k in range(len(pts) - 1):
            p, q = pts[k], pts[k + 1]
            v = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
            if v[0] * v[0] + v[1] * v[1] + v[2] * v[2] < 1e-6:
                continue
            cx, cz = int(p[0] // CELL), int(p[2] // CELL)
            best, bd = None, max_dist * max_dist
            for r in range(reach + 1):
                for gx in range(cx - r, cx + r + 1):
                    for gz in range(cz - r, cz + r + 1):
                        if max(abs(gx - cx), abs(gz - cz)) != r:
                            continue
                        for sp, sd in grid.get((gx, gz), ()):
                            dd = (sp[0] - p[0]) ** 2 + (sp[1] - p[1]) ** 2 + (sp[2] - p[2]) ** 2
                            if dd < bd:
                                best, bd = sd, dd
                if best is not None and bd <= ((r) * CELL) ** 2:
                    break                      # nothing nearer can be in an outer ring
            if best is None:
                continue
            tot += 1
            ds.append(bd ** 0.5)
            dot = (v[0] * best[0] + v[1] * best[1] + v[2] * best[2]) / (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
            dots += dot
            if dot > 0:
                fwd += 1
        steps_n = max(1, len(pts) - 1)
        share = fwd / tot if tot else 0.5
        cover = tot / steps_n
        mean = dots / tot if tot else 0.0
        cls = OTHER
        if cover >= 0.2 and abs(mean) >= 0.6:      # crossing roads have |mean| below 0.5 in the files examined
            cls = SAME if share >= 0.9 else ONCOMING if share <= 0.1 else OTHER
        ds.sort()
        out.append({"class": cls, "forward": round(share, 3), "alignment": round(mean, 3), "cover": round(cover, 3),
                    "distance": round(ds[len(ds) // 2], 1) if ds else None,
                    "length": abs(dist[-1] - dist[0]) if dist else 0.0})
    return out


def lane_classes(bgd, game):
    """Classes of the lanes of the file's own lane network against its own
    lap lines. -> (list of dicts as classify(), lanes)."""
    lanes = lane_network(bgd, game)
    steps, used = lap_steps(bgd, game)
    return classify(lanes, steps), lanes


def driving_side(lanes, reach=30.0):
    """Which side traffic drives on, from the lane network alone: for each
    lane step, where the nearest lane running the opposite way lies.
    -> ('right' | 'left' | None, votes for right, votes for left).
    Checked against the set flag 0x2 (right-side driving in Revenge, external
    review 2026-10-12): every Revenge US file here votes right and has the
    flag, Revenge AS/K1_V2 votes left and lacks it. Burnout 3 does not use
    the flag that way (AS/M1_V1 votes left and has it)."""
    pts = []
    for li, (p, _dist) in enumerate(lanes):
        for k in range(0, len(p) - 1, 3):
            a, b = p[k], p[k + 1]
            vx, vz = b[0] - a[0], b[2] - a[2]
            n = (vx * vx + vz * vz) ** 0.5
            if n > 1e-3:
                pts.append((li, a, vx / n, vz / n))
    grid = {}
    for q in pts:
        grid.setdefault((int(q[1][0] // reach), int(q[1][2] // reach)), []).append(q)
    right = left = 0
    for li, a, vx, vz in pts:
        best, bd = None, reach * reach
        cx, cz = int(a[0] // reach), int(a[2] // reach)
        for gx in (cx - 1, cx, cx + 1):
            for gz in (cz - 1, cz, cz + 1):
                for lj, b, wx, wz in grid.get((gx, gz), ()):
                    if lj == li or vx * wx + vz * wz > -0.8 or abs(a[1] - b[1]) > 3:
                        continue
                    dd = (a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2
                    if 4 < dd < bd:
                        best, bd = b, dd
        if best is not None:
            if vx * (best[2] - a[2]) - vz * (best[0] - a[0]) < 0:
                right += 1                  # the oncoming lane is on the driver's left
            else:
                left += 1
    total = right + left
    if total < 20 or max(right, left) < 0.9 * total:
        return None, right, left
    return ("right" if right > left else "left"), right, left
