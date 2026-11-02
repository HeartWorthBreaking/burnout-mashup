"""fr_routes - read-only parser for Burnout 3 Xbox GAMEDATA.BGD route data (S4 AI racer routes v3, S3 traffic lanes),
with the event records' section directory. Unknown bytes are kept; serialize() rebuilds the file byte for byte.

Layouts (KB XBOX_TRACK_FORMATS.md s2, AI_NAVIGATION.md s1, trackbuild/traffic.py docstring; re-verified here on 37 tracks):
  file      header 0x3000 (event ids +0x08 {u32,u32} x k, record offsets +0x198 u32 x k, count +0x260) | event records
            0x800 each | S1 / S2 pages | S3 | S4 (last). Record directory (record-relative): +0x3B4 s32 drivers,
            +0x3B8 s32 laps, {size, offset} pairs S1 +0x3BC, S2 +0x3C4, S3 +0x3CC, S4 +0x3D4 (offsets absolute in the file).
  S4 (v3)   header 9 x u32 {3, lanes, slices, corners, zones, p_lanes, p_dist, p_corners, p_pos} (pointers relative to S4);
            +0x24..+0xB0 zone block (kept raw); positions vec4 at p_pos; lane entries 16 B {rungs, dims, segs (relative to
            the entry), u32 count | flags << 16} (flag 1 = cyclic); rungs (n+1) x {u16 left node, u16 right node};
            dims n x {f32 cumulative length, f32 width}; segs n x 10 B {s16 slice, u8 corner, u8 type, u8 left lane,
            u8 right lane, u16 left seg, u16 right seg}; distances slices x {f32 race distance, u32}; corners 12 B.
  S3        u32 0xC, u32 p_pos, u32 lanes; per lane 20 B {p_A, p_B, p_C, u32 0, u32 n} (pointers relative to S3);
            A (n+1) x {u16, u16} edge position indices; B n x {f32 running distance, f32 width};
            C n x 18 B {6 x u16 node, 6 x u8 lane}; positions vec4 from p_pos to the end of the used area.

serialize(): every decoded structure is re-encoded from its fields at its parsed offset; undecoded non-zero bytes are
kept as gaps; nothing is copied wholesale except the Gamedata header, records and S1 / S2 pages (kept raw by design:
route research does not decode them).
"""
import struct

from fr_common import Reader, need, place, al, FormatError

NONE8, NONE16 = 0xFF, 0xFFFF
MAX_EVENTS, MAX_LANES_FIELD, MAX_SEGS, MAX_SLICES, MAX_POS = 64, 255, 0xFFFF, 0x7FFF, 0x10000
KIND = {0: "racing", 1: "racing", 4: "edge", 5: "corridor"}
DIR = {"S1": 0x3BC, "S2": 0x3C4, "S3": 0x3CC, "S4": 0x3D4}


# ============================================================================================ S4 (AI racer routes)
def parse_s4(b):
    r = Reader(b)
    h = r.unpack("<9I", 0, "S4 header")
    ver, nl, nsl, nco, nzo, p_lanes, p_dist, p_corn, p_pos = h
    need(ver == 3, "S4 version %d (Burnout 3 = 3)" % ver)
    need(0 < nl <= MAX_LANES_FIELD and 0 < nsl <= MAX_SLICES and nco <= 0x10000 and nzo <= 8, "S4 counts out of range")
    need(p_pos == 0xB0 and p_pos < p_lanes < len(b) and p_dist < len(b) and p_corn < len(b), "S4 pointers out of range")
    zones_raw = r.take(0x24, 0x8C, "S4 zone block")
    npos = (p_lanes - p_pos) // 16
    need(npos * 16 == p_lanes - p_pos and npos <= MAX_POS, "S4 positions block size")
    pos = [r.unpack("<4f", p_pos + 16 * k, "S4 position") for k in range(npos)]
    lanes = []
    for i in range(nl):
        e = p_lanes + 16 * i
        pr, pd, ps, cf = r.unpack("<4I", e, "S4 lane entry")
        n, flags = cf & 0xFFFF, cf >> 16
        need(0 < n <= MAX_SEGS, "S4 lane %d: %d segments" % (i, n))
        rungs = [r.unpack("<2H", e + pr + 4 * k, "S4 rung") for k in range(n + 1)]
        dims = [r.unpack("<2f", e + pd + 8 * k, "S4 dims") for k in range(n)]
        segs = [r.unpack("<hBBBBHH", e + ps + 10 * k, "S4 segment") for k in range(n)]
        for (a, c) in rungs:
            need(a < npos and c < npos, "S4 lane %d: rung node outside the positions" % i)
        lanes.append({"flags": flags, "rel": (pr, pd, ps), "rungs": rungs, "dims": dims, "segs": segs})
    dist = [r.unpack("<fI", p_dist + 8 * k, "S4 distance") for k in range(nsl)]
    corners = [r.unpack("<4H4B", p_corn + 12 * k, "S4 corner") for k in range(nco)]
    o = {"size": len(b), "header": h, "zones_raw": zones_raw, "pos": pos, "lanes": lanes, "dist": dist,
         "corners": corners, "gaps": r.gaps(), "claimed": r.claimed()}
    for i, l in enumerate(o["lanes"]):
        for s in l["segs"]:
            for ln, sg in ((s[3], s[5]), (s[4], s[6])):
                if ln != NONE8:
                    need(ln < nl and sg < len(o["lanes"][ln]["segs"]), "S4 lane %d: link to lane %d seg %d out of range" % (i, ln, sg))
    return o


def serialize_s4(o):
    h = o["header"]
    ver, nl, nsl, nco, nzo, p_lanes, p_dist, p_corn, p_pos = h
    need(len(o["lanes"]) == nl and len(o["dist"]) == nsl and len(o["corners"]) == nco, "S4 counts vs header")
    pieces = [(0, struct.pack("<9I", *h)), (0x24, o["zones_raw"]),
              (p_pos, b"".join(struct.pack("<4f", *p) for p in o["pos"]))]
    for i, l in enumerate(o["lanes"]):
        e = p_lanes + 16 * i
        pr, pd, ps = l["rel"]
        n = len(l["segs"])
        need(len(l["rungs"]) == n + 1 and len(l["dims"]) == n, "S4 lane %d array lengths" % i)
        pieces.append((e, struct.pack("<4I", pr, pd, ps, n | (l["flags"] << 16))))
        pieces.append((e + pr, b"".join(struct.pack("<2H", *x) for x in l["rungs"])))
        pieces.append((e + pd, b"".join(struct.pack("<2f", *x) for x in l["dims"])))
        pieces.append((e + ps, b"".join(struct.pack("<hBBBBHH", *x) for x in l["segs"])))
    pieces.append((p_dist, b"".join(struct.pack("<fI", *x) for x in o["dist"])))
    if o["corners"]:
        pieces.append((p_corn, b"".join(struct.pack("<4H4B", *x) for x in o["corners"])))
    pieces += o["gaps"]
    return place(o["size"], pieces)


def analyse_s4(o):
    """route topology summary: lane kinds, cyclic vs partial lanes, alternate routes (branches) and their links"""
    nl, nsl = o["header"][1], o["header"][2]
    out = {"lanes": nl, "slices": nsl, "corners": o["header"][3], "positions": len(o["pos"]), "cyclic": 0,
           "kinds": {}, "alternates": [], "partial_racing": [], "point_to_point": None}
    for i, l in enumerate(o["lanes"]):
        types = sorted({s[2] for s in l["segs"]})
        kind = types[0] & 7
        name = KIND.get(kind, "kind%d" % kind)
        out["kinds"][name] = out["kinds"].get(name, 0) + 1
        cyc = bool(l["flags"] & 1)
        out["cyclic"] += cyc
        sl = [s[0] for s in l["segs"]]
        z0 = l["rungs"][0][0] == l["rungs"][0][1]
        z1 = l["rungs"][-1][0] == l["rungs"][-1][1]
        racing = kind in (0, 1)
        alt = any(t & 0x40 for t in types)
        if racing and (alt or not cyc):
            links = sum(1 for s in l["segs"] if s[3] != NONE8 or s[4] != NONE8)
            ends = []
            for s in (l["segs"][0], l["segs"][-1]):
                ends.append([None if s[3] == NONE8 else s[3], None if s[4] == NONE8 else s[4]])
            rec = {"lane": i, "types": types, "segs": len(l["segs"]), "slice_first": sl[0], "slice_last": sl[-1],
                   "cyclic": cyc, "zero_width_ends": [z0, z1], "segments_with_links": links,
                   "entry_links_LR": ends[0], "exit_links_LR": ends[1]}
            (out["alternates"] if alt else out["partial_racing"]).append(rec)
    out["point_to_point"] = out["cyclic"] == 0
    return out


# ============================================================================================ S3 (traffic lane network)
def parse_s3(b):
    r = Reader(b)
    w0, p_pos, nl = r.unpack("<3I", 0, "S3 header")
    need(w0 == 0xC and 0 < nl <= 255 and 12 + 20 * nl <= p_pos < len(b), "S3 header (0x%X, 0x%X, %d)" % (w0, p_pos, nl))
    lanes = []
    max_node = -1
    for i in range(nl):
        pa, pb, pc, z, n = r.unpack("<5I", 12 + 20 * i, "S3 lane entry")
        need(0 < n <= MAX_SEGS, "S3 lane %d: %d nodes" % (i, n))
        A = [r.unpack("<2H", pa + 4 * k, "S3 A") for k in range(n + 1)]
        B = [r.unpack("<2f", pb + 8 * k, "S3 B") for k in range(n)]
        C = [r.unpack("<6H6B", pc + 18 * k, "S3 C") for k in range(n)]
        max_node = max([max_node] + [max(a) for a in A])
        lanes.append({"ptrs": (pa, pb, pc), "z": z, "A": A, "B": B, "C": C})
    npos = max_node + 1
    pos = [r.unpack("<4f", p_pos + 16 * k, "S3 position") for k in range(npos)]
    for i, l in enumerate(lanes):
        for c in l["C"]:
            for s in range(6):
                if c[6 + s] != NONE8:
                    need(c[6 + s] < nl, "S3 lane %d: C slot %d names lane %d" % (i, s, c[6 + s]))
    return {"size": len(b), "p_pos": p_pos, "lanes": lanes, "pos": pos, "gaps": r.gaps(), "claimed": r.claimed()}


def serialize_s3(o):
    nl = len(o["lanes"])
    pieces = [(0, struct.pack("<3I", 0xC, o["p_pos"], nl))]
    for i, l in enumerate(o["lanes"]):
        pa, pb, pc = l["ptrs"]
        n = len(l["B"])
        need(len(l["A"]) == n + 1 and len(l["C"]) == n, "S3 lane %d array lengths" % i)
        pieces.append((12 + 20 * i, struct.pack("<5I", pa, pb, pc, l["z"], n)))
        pieces.append((pa, b"".join(struct.pack("<2H", *x) for x in l["A"])))
        pieces.append((pb, b"".join(struct.pack("<2f", *x) for x in l["B"])))
        pieces.append((pc, b"".join(struct.pack("<6H6B", *x) for x in l["C"])))
    pieces.append((o["p_pos"], b"".join(struct.pack("<4f", *p) for p in o["pos"])))
    pieces += o["gaps"]
    return place(o["size"], pieces)


def analyse_s3(o):
    """traffic topology: per-slot usage of the C records; joins (slot 1 at a lane's last node, slot 4 at its first)"""
    nl = len(o["lanes"])
    slot_use = [0] * 6
    succ, pred = {}, {}
    for i, l in enumerate(o["lanes"]):
        for k, c in enumerate(l["C"]):
            for s in range(6):
                if c[6 + s] != NONE8:
                    slot_use[s] += 1
        last, first = l["C"][-1], l["C"][0]
        if last[7] != NONE8:
            succ.setdefault(i, []).append(last[7])
        if first[10] != NONE8:
            pred.setdefault(i, []).append(first[10])
    into = {}
    for a, bs in succ.items():
        for b_ in bs:
            into.setdefault(b_, []).append(a)
    return {"lanes": nl, "nodes": sum(len(l["B"]) for l in o["lanes"]), "positions": len(o["pos"]),
            "c_slot_use": slot_use, "lanes_with_exit_join": len(succ), "lanes_with_entry_join": len(pred),
            "merge_targets": {str(k): v for k, v in into.items() if len(v) > 1}}


# ============================================================================================ GAMEDATA.BGD
def parse_gamedata(d):
    need(len(d) >= 0x3000 and len(d) % 0x800 == 0, "Gamedata size 0x%X" % len(d))
    r = Reader(d)
    nev = r.u32(0x260)
    need(0 < nev <= MAX_EVENTS, "event count %d" % nev)
    recs = []
    sections = {}
    for k in range(nev):
        ro = r.u32(0x198 + 4 * k)
        need(ro % 0x800 == 0 and 0x3000 <= ro and ro + 0x800 <= len(d), "record %d offset 0x%X" % (k, ro))
        drivers, laps = struct.unpack_from("<ii", d, ro + 0x3B4)
        dirs = {}
        for name, fo in DIR.items():
            size, off = struct.unpack_from("<II", d, ro + fo)
            need(off % 0x800 == 0 and size % 0x800 == 0 and off + size <= len(d), "record %d %s (0x%X, 0x%X)" % (k, name, off, size))
            dirs[name] = (off, size)
            if size:
                sections.setdefault((off, size), set()).add(name)
        ids = struct.unpack_from("<II", d, 0x08 + 8 * k)
        recs.append({"index": k, "offset": ro, "ids": ids, "drivers": drivers, "laps": laps, "dirs": dirs})
    s3s = {(o, s) for (o, s), n in sections.items() if "S3" in n}
    s4s = {(o, s) for (o, s), n in sections.items() if "S4" in n}
    need(len(s4s) >= 1 and len(s3s) >= 1, "no S3 / S4 section")
    for key, names in sections.items():
        need(len(names) == 1, "section 0x%X shared by %s" % (key[0], sorted(names)))
    s4 = {k: parse_s4(d[k[0]:k[0] + k[1]]) for k in sorted(s4s)}
    s3 = {k: parse_s3(d[k[0]:k[0] + k[1]]) for k in sorted(s3s)}
    decoded = set(s4) | set(s3)
    # everything not inside a decoded S3 / S4 section is kept raw (header, records, S1 / S2 pages, padding)
    raw, cur = [], 0
    for (o_, s_) in sorted(decoded):
        need(o_ >= cur, "decoded sections overlap")
        if o_ > cur:
            raw.append((cur, d[cur:o_]))
        cur = o_ + s_
    if cur < len(d):
        raw.append((cur, d[cur:]))
    return {"size": len(d), "events": recs, "s4": s4, "s3": s3, "raw": raw}


def serialize_gamedata(g):
    pieces = list(g["raw"])
    for (o_, s_), s in g["s4"].items():
        pieces.append((o_, serialize_s4(s)))
    for (o_, s_), s in g["s3"].items():
        pieces.append((o_, serialize_s3(s)))
    return place(g["size"], pieces)


def summary(g):
    out = {"events": len(g["events"]),
           "laps_drivers": sorted({(e["laps"], e["drivers"]) for e in g["events"]}),
           "s4_sections": len(g["s4"]), "s3_sections": len(g["s3"])}
    (k4, s4), = list(g["s4"].items())[:1]
    out["s4"] = analyse_s4(s4)
    out["s4"]["gaps"] = len(s4["gaps"])
    (k3, s3), = list(g["s3"].items())[:1]
    out["s3"] = analyse_s3(s3)
    out["s3"]["gaps"] = len(s3["gaps"])
    out["records"] = sum(len(l["segs"]) for l in s4["lanes"]) + sum(len(l["B"]) for l in s3["lanes"])
    return out


if __name__ == "__main__":
    import json
    import sys
    from fr_common import read_ro
    d = read_ro(sys.argv[1])
    g = parse_gamedata(d)
    print(json.dumps(summary(g), indent=1, default=list)[:6000])
    print("identical:", serialize_gamedata(g) == d)
