"""trackbuild.traffic - AUTHORED traffic data: the S3 lane network and one S2 traffic set (CB4TrafficDataStruct), written
from the track description instead of copying the Gamedata donor's.

Formats (PS2 docs/traffic_format.md + bolib.traffic, both games share them; B3 field order):
  S3   u32 0xC, u32 position-list offset, u32 lane count; per lane {ptr A, ptr B, ptr C, 0, node count n}; A = (n+1) x
       (u16, u16) edge position indices, B = n x (f32 running distance, f32 width), C = n x 18 B {6 x u16 node, 6 x u8 lane}
       (slots 2 / 3 = the neighbouring lanes at the same node; slot 1 at a lane's last node / 4 at its first = joins, retail);
       position list = vec4. Retail lanes are OPEN (no loop closure, even on circuits): the authored lanes are open too.
  set  0x28 bytes: 5 special-vehicle IDs (0); +0x28 36 u32: lead 8, T1, T2, roads, points, triggers (ptr, count), 6 vehicle
       lists (ptr, count, total), X1, X2, Z (ptr, count), flags (byte: 1 online / whole track, 2 right-side, 4 crash);
       data from +0xC0, every pointer relative to the set. The shape written is the retail ONLINE shape (flags 3, US/C3_V1
       ONSGRCF): whole-track population (no zones needed), one trigger (index 0, slice 0, lap 0) listing every lane:
       p1 speed / p2 road / p3 lane, p4 flow (u32 0 + six f32 vehicles per minute per class) / p5 / p6, p7 third group
       (3 pointers to 16-byte zero blocks, 0, 1) / p8 / p9, p10 72 B per spawn point (3 x 6 u32 weights) / p11 index,
       p12 / p13 traffic lights (none written: count 0), p0 = p4 (retail trigger 0), p14 unused.
Values with no decoded meaning are written as the retail ONSGRCF set carries them (listed in RETAIL_VALUES)."""
import math
import struct

from .io import need

RETAIL_VALUES = {"lead word": 8, "vehicle record tail": "0a121212121200000100000000000000 (per-variant weights summing to 100, "
                 "u32 1, u32 0)", "p7 record": "3 pointers to 16-byte zero blocks, 0, 1", "p10 weights": "100 x5, 0 in slot 0",
                 "flags": 3}
VEH_TAIL = bytes.fromhex("0a121212121200000100000000000000")


def al(x, a):
    return x + (-x) % a


def build_s3(desc):
    """-> (S3 bytes, lanes info). desc["traffic"]["lanes"]: [{"offset": o (along n+), "width": w}], nodes every
    `node_stations` stations from station `first` to `last` (open lane, race direction)."""
    tr = desc["traffic"]
    st = desc["stations"]
    N = len(st)
    step, first, last = tr["node_stations"], tr["first_station"], tr["last_station"]
    idx = list(range(first, last + 1, step))
    need(len(idx) >= 3, "traffic lane shorter than 3 nodes")
    lanes = tr["lanes"]
    nl = len(lanes)
    need(1 <= nl <= 4, "1..4 authored traffic lanes (one road)")
    pos = []

    def p_at(k, o):
        s_ = st[k % N]
        nx, nz = -s_["t"][1], s_["t"][0]
        pos.append((s_["p"][0] + nx * o, s_["p"][1], s_["p"][2] + nz * o, 0.0))
        return len(pos) - 1
    # edges: lanes sorted by offset; shared edges between neighbours (as retail: lane i+1's second edge = lane i's first)
    order = sorted(range(nl), key=lambda i: lanes[i]["offset"])
    edges = {}
    for k in idx:
        row = []
        bounds = []
        for i in order:
            o, w = lanes[i]["offset"], lanes[i]["width"]
            bounds.append((o - w / 2, o + w / 2))
        # edge positions at every distinct bound
        vals = sorted({round(b, 4) for pr in bounds for b in pr})
        ids = {v: p_at(k, v) for v in vals}
        edges[k] = {i: (ids[round(lanes[i]["offset"] - lanes[i]["width"] / 2, 4)], ids[round(lanes[i]["offset"] + lanes[i]["width"] / 2, 4)])
                    for i in range(nl)}
    n = len(idx) - 1                        # nodes = segments between rungs (retail: n nodes, n + 1 rungs)
    head = 12 + 20 * nl
    out = bytearray(head)
    arrays = []
    for i in range(nl):
        A = b"".join(struct.pack("<2H", *edges[k][i]) for k in idx)
        dist, Bv = 0.0, b""
        for j in range(n):
            a0, b0 = edges[idx[j]][i]
            a1, b1 = edges[idx[j + 1]][i]
            c0 = [(pos[a0][q] + pos[b0][q]) / 2 for q in range(3)]
            c1 = [(pos[a1][q] + pos[b1][q]) / 2 for q in range(3)]
            dist += math.dist(c0, c1)
            Bv += struct.pack("<2f", dist, lanes[i]["width"])
        rank = order.index(i)
        Cv = b""
        for j in range(n):
            nodes = [0xFFFF] * 6
            ln = [0xFF] * 6
            if rank + 1 < nl:                                   # neighbour on the higher-offset side: slot 2
                nodes[2], ln[2] = j, order[rank + 1]
            if rank > 0:                                        # neighbour on the lower-offset side: slot 3
                nodes[3], ln[3] = j, order[rank - 1]
            Cv += struct.pack("<6H6B", *nodes, *ln)
        arrays.append((A, Bv, Cv, n))
    groups = []
    for A, Bv, Cv, cnt in arrays:
        ptrs = []
        for arr in (A, Bv, Cv):
            out += bytes(al(len(out), 16) - len(out))
            ptrs.append(len(out))
            out += arr
        groups.append((ptrs, cnt))
    out += bytes(al(len(out), 16) - len(out))
    p_pos = len(out)
    for p in pos:
        out += struct.pack("<4f", *p)
    struct.pack_into("<3I", out, 0, 0xC, p_pos, nl)
    for i, (ptrs, cnt) in enumerate(groups):
        struct.pack_into("<5I", out, 12 + 20 * i, ptrs[0], ptrs[1], ptrs[2], 0, cnt)
    out += bytes(al(len(out), 0x800) - len(out))
    return bytes(out), {"lanes": nl, "nodes": n, "positions": len(pos), "first_station": first, "last_station": last}


def build_set(desc, s3_nodes):
    """-> (set bytes, info): the online whole-track shape (flags 3), one road holding every authored lane"""
    from .build import _gtid  # late import (bolib through deps)
    tr = desc["traffic"]
    lanes = tr["lanes"]
    nl = len(lanes)
    pts = tr["spawn_points"]                            # [(lane, node)]
    need(1 <= len(pts) <= 255, "1..255 spawn points")
    need(all(0 <= l < nl and 0 <= nd < s3_nodes for l, nd in pts), "spawn point outside the authored lanes")
    vlists = tr["vehicles"]                             # 6 lists of vehicle ID strings (classes 0..5)
    need(len(vlists) == 6, "six vehicle class lists")
    b = bytearray(0xC0)
    cur = 0xC0

    def put(data, align=16):
        nonlocal cur
        cur = al(cur, align)
        if len(b) < cur:
            b.extend(bytes(cur - len(b)))
        at = cur
        b.extend(data)
        cur = len(b)
        return at
    # road (one, all lanes), its A (S3 lane index per lane) / B (start node 0) arrays
    road_A = put(struct.pack("<%dI" % nl, *range(nl)))
    road_B = put(struct.pack("<%dI" % nl, *([0] * nl)))
    roads = put(struct.pack("<4I", road_A, road_B, nl, 1))
    points = put(b"".join(struct.pack("<2I", l, nd) for l, nd in pts))
    # trigger 0 arrays
    p1 = put(struct.pack("<%df" % nl, *[float(l["speed"]) for l in lanes]))
    p2 = put(bytes([0] * nl))
    p3 = put(bytes(range(nl)))
    p4 = put(b"".join(struct.pack("<I6f", 0, *[float(x) for x in l["flow"]]) for l in lanes))
    p5 = put(bytes([0] * nl))
    p6 = put(bytes(range(nl)))
    zero_blocks = [put(bytes(16)) for _ in range(3 * nl)]
    p7 = put(b"".join(struct.pack("<5I", zero_blocks[3 * i], zero_blocks[3 * i + 1], zero_blocks[3 * i + 2], 0, 1) for i in range(nl)))
    p8 = put(bytes([0] * nl))
    p9 = put(bytes(range(nl)))
    p10 = put(b"".join(struct.pack("<18I", *([100] * 5 + [0] * 13)) for _ in pts))
    p11 = put(bytes(range(len(pts))))
    p12 = put(b"")
    p13 = put(bytes(16))                                 # T2 index bytes (none), padded to 16 as retail
    trig = bytearray(0x58)
    struct.pack_into("<15I", trig, 0, p4, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, 0)
    struct.pack_into("<4I", trig, 0x3C, 0, nl, nl, nl)
    struct.pack_into("<fHB", trig, 0x4C, 0.0, 0, 0)
    trig[0x53], trig[0x54], trig[0x55] = 0, len(pts), 0
    trigs = put(bytes(trig))
    vl = []
    for ids in vlists:
        recs = b"".join(struct.pack("<Q", _gtid(v)) + VEH_TAIL for v in ids)
        at = put(recs) if ids else al(cur, 16)
        vl.append((at, len(ids), len(ids)))
    words = [8, 0, 0, 0, 0, roads, 1, points, len(pts), trigs, 1]
    for at, n, t in vl:
        words += [at, n, t]
    words += [0, 0, 0, 0, 0, 0, 3]
    need(len(words) == 36, "set header word count")
    struct.pack_into("<36I", b, 0x28, *words)
    b.extend(bytes(al(len(b), 0x800) - len(b)))
    return bytes(b), {"lanes": nl, "points": len(pts), "vehicles": [len(v) for v in vlists], "flags": 3, "bytes": len(b)}
