"""trackbuild.lanegraph (0.3.3-rta) - the S4 lateral lane graph: reader views, retail-rule checks and the strip-insertion writer.

Decoded from retail data (tools\\rta4_lane_graph.py + this module's `retail_rules`, 36 / 36 tracks, the user's game data):
  * At every slice the lanes present form ONE left-to-right sequence: the leftmost lane has left link NONE, each lane's right
    link is the next lane (symmetric: that lane's left link points back, same slice), the rightmost has right link NONE.
  * Neighbours share their edge: lane A's right rung node == lane B's left rung node (both rungs of the segment).
  * A non-cyclic lane (strip) is INSERTED between two lanes A | B: its first and last rungs have zero width (both nodes = the
    node A and B share there), its left edge reuses A's right-edge nodes and its right edge B's left-edge nodes while it is
    narrow, A's right links and B's left links point to the strip over its span, and its end segments keep both links
    (KB R2). No zero-width rung inside a lane (KB R1). Strips nest (a median strip inserted inside a strip).
  * A route branch is such a strip: an alternate racing lane (type 0x41) that widens away from its neighbour, separated
    from the main route by a median made of inserted edge (kind 4) / corridor (kind 5) strips (US/C2_V1 lane 1: 202 slices,
    up to 27.8 m, median of 10 islands; EU/C4_V1: cyclic alternate lane 10 beside main 9 with nested median strips).
Labels: rules = DATA (retail census); AI choice of a branch, respawn and lap progress on an authored branch = RUNTIME-UNVERIFIED.
Nothing here guesses neighbour changes: the writer derives every link from the lateral sequence it builds."""
import math

NONE = 0xFF


def seg_at(l, sl, slices):
    if l["flags"] & 1:
        return sl if sl < len(l["segs"]) and l["segs"][sl][0] == sl else None
    k = (sl - l["segs"][0][0]) % slices
    return k if k < len(l["segs"]) and l["segs"][k][0] == sl else None


def present(r, sl):
    """[(lane, seg)] of the lanes that have a segment at slice sl"""
    out = []
    for i, l in enumerate(r.lanes):
        k = seg_at(l, sl, r.slices)
        if k is not None:
            out.append((i, k))
    return out


def lateral_order(r, sl):
    """-> (order [lane ...] left to right, problems []) built by walking right links from the lane whose left link is NONE"""
    pr = dict(present(r, sl))
    probs = []
    starts = [i for i, k in pr.items() if r.lanes[i]["segs"][k][3] == NONE]
    if len(starts) != 1:
        return [], ["slice %d: %d lanes without a left neighbour (%s)" % (sl, len(starts), starts[:6])]
    order, cur, seen = [], starts[0], set()
    while cur != NONE:
        if cur in seen or cur not in pr:
            probs.append("slice %d: right-link chain breaks at lane %d" % (sl, cur))
            break
        seen.add(cur)
        order.append(cur)
        cur = r.lanes[cur]["segs"][pr[cur]][4]
    missing = sorted(set(pr) - seen)
    if missing:
        probs.append("slice %d: lanes %s present but not in the lateral sequence (detached)" % (sl, missing[:6]))
    return order, probs


def check_graph(r, limit=40):
    """retail lateral-graph rules (see the module doc) -> problems [] (empty = the graph is a consistent lateral sequence)"""
    p = []
    for sl in range(r.slices):
        order, pr = lateral_order(r, sl)
        p += pr
        segs = dict(present(r, sl))
        for a, b in zip(order, order[1:]):
            sa, sb = r.lanes[a]["segs"][segs[a]], r.lanes[b]["segs"][segs[b]]
            if sb[3] != a or sa[6] != segs[b] or sb[5] != segs[a]:
                p.append("slice %d: link %d|%d not symmetric" % (sl, a, b))
            ra, rb = r.lanes[a]["rungs"], r.lanes[b]["rungs"]
            for d in (0, 1):
                if ra[segs[a] + d][1] != rb[segs[b] + d][0]:
                    p.append("slice %d: lanes %d|%d do not share their edge node (rung %d)" % (sl, a, b, d))
                    break
        if len(p) >= limit:
            break
    for i, l in enumerate(r.lanes):
        if l["flags"] & 1:
            continue
        w = [_w(r, rg) for rg in l["rungs"]]
        f_, l_ = l["segs"][0][0], l["segs"][-1][0]
        open_end = (w[0] > 0.01 and f_ != 0) or (w[-1] > 0.01 and l_ != r.slices - 1)   # track ends: point-to-point routes
        if open_end:
            p.append("strip lane %d: does not open / close on a zero-width rung (%.2f / %.2f m)" % (i, w[0], w[-1]))
        if any(x < 0.01 for x in w[1:-1]):
            p.append("strip lane %d: zero-width rung inside the lane (KB R1)" % i)
        for j, wj in ((0, w[0]), (len(l["segs"]) - 1, w[-1])):
            s = l["segs"][j]
            if wj < 0.01 and (s[3] == NONE or s[4] == NONE):     # R2: an end on a zero-width rung keeps both links
                p.append("strip lane %d: end segment %d lacks a lateral link (KB R2)" % (i, j))
    return p[:limit]


def _w(r, rg):
    return math.dist(r.pos[rg[0]][:3], r.pos[rg[1]][:3])


def retail_rules(r):
    """census counters for one retail route (used by the survey to prove the rules on every track)"""
    c = {"slices": r.slices, "slice_problems": 0, "strips": 0, "strip_problems": 0}
    probs = check_graph(r, limit=10 ** 9)
    c["slice_problems"] = sum(1 for x in probs if x.startswith("slice"))
    c["strip_problems"] = sum(1 for x in probs if x.startswith("strip"))
    c["strips"] = sum(1 for l in r.lanes if not l["flags"] & 1)
    c["examples"] = probs[:3]
    return c


# ------------------------------------------------------------------------------------------------- AI-model checks (MODEL)
def nav_r(r):
    """KB AI s7 NAV-R on the lateral-sequence model: the follower fallback 0x00175DC2 reads the racing lane's segment at the
    POSITION (corridor) segment index without a bound check; it runs only when the corridor is NOT in the racing segment's
    left / right chains. In a consistent lateral sequence every corridor present at the racing slice is in the chain, so the
    reachable non-chain corridors are those present at the neighbouring slices only (strips opening / closing next to it).
    Rule checked: for every segment s of a non-cyclic racing lane (kind 0-3) at slice t, every corridor segment present at
    t - 1 or t + 1 but not at t has index < the racing lane's segment count. -> violations []"""
    out = []
    for X, L in enumerate(r.lanes):
        if L["flags"] & 1 or (L["segs"][0][2] & 7) not in (0, 1, 2, 3):
            continue
        n = len(L["segs"])
        for s, g in enumerate(L["segs"]):
            t = g[0]
            here = {i for i, _ in present(r, t)}
            for tt in ((t - 1) % r.slices, (t + 1) % r.slices):
                for Y, j in present(r, tt):
                    if Y in here or (r.lanes[Y]["segs"][j][2] & 7) != 5:
                        continue
                    if j >= n:
                        out.append((X, s, Y, j))
    return out


def strip_report(r):
    """per non-cyclic lane: span, kind, neighbours at entry / exit, max width (editor diagnostics)"""
    out = []
    for i, l in enumerate(r.lanes):
        if l["flags"] & 1:
            continue
        w = [_w(r, rg) for rg in l["rungs"]]
        s0, s1 = l["segs"][0], l["segs"][-1]
        out.append({"lane": i, "type": "0x%02X" % s0[2], "kind": s0[2] & 7, "slices": [s0[0], s1[0]], "segments": len(l["segs"]),
                    "width_max_m": round(max(w), 2), "entry_between": [s0[3], s0[4]], "exit_between": [s1[3], s1[4]]})
    return out
