"""Traffic data in GAMEDATA.BGD (docs/traffic_format.md).

Three things work together:
  * the event record (0x800 bytes per ID) ends with a directory that tells
    the game which layout, traffic set, lane network (S3), route section (S4)
    and S5 to use for that event;
  * the lane network S3: lanes as node lists with positions and links
    (byte-compatible between Burnout 3 and Revenge);
  * a traffic set: roads grouping lanes, per-lane speeds, spawn points with
    vehicle-class weights, vehicle lists. One set per event (often shared).

Traffic set header, u32 words from +0x28 (pointers relative to the set):
  Burnout 3: lead, T1, T2, roads, points, networks, 6 x vehicle list,
             X1, X2, Z, type                (each table = ptr, count)
  Revenge:   lead, T1, T2, roads, points, networks, T6, 6 x vehicle list,
             X1, X2, Z, type
  vehicle list = ptr, record count, u32 (sum of the records' u32 at +0x10)
Road, 16 bytes: ptr A, ptr B, lane count, flag. A = lane's S3 group per
  lane (u32 each), B = u32 per lane (not understood).
Point, 8 bytes: u32 S3 group, u32 node.
Network, 0x58 bytes: 14 pointers p0..p13, a null, 0, three copies of the
  lane count, 0, 0, then Burnout 3: u8 point count, u8 T2 count, u16 0
                         Revenge:   u16 0, u8 point count, u8 T2 count
  p0/p4 28 bytes per lane, p1 float speed per lane, p2/p5/p8 road index per
  lane, p3/p6/p9 lane index within its road, p7 20 bytes per lane (three
  pointers to 16-byte blocks, 0, 1), p10 72 bytes per point (3 slots of 6
  u32 weights), p11 u8 per point, p12/p13 Revenge: 48 bytes per lane, zero.
Vehicle record, 0x18 bytes: u64 vehicle ID, 8 bytes, u32, u32.
Z: 0x20-byte records (vec3 position, vec3 direction).
"""
import struct

import re

from . import gtid
from . import lanes as LN
from . import routes as RT


class TrafficError(Exception):
    pass


REV_DIR, B3_DIR = 0x3B8, 0x3BC          # in an event record: layout size, layout ptr, set size, set ptr, S3 size, S3 ptr, ...


def event_records(bgd, game):
    """[(index, record offset)] for every ID in the file."""
    if game == "rev":
        n = struct.unpack_from("<I", bgd, 0x968)[0]
        return [(i, struct.unpack_from("<I", bgd, 0x648 + 4 * i)[0]) for i in range(n)]
    n = struct.unpack_from("<I", bgd, 0x260)[0]
    first = struct.unpack_from("<I", bgd, 0x264)[0]
    return [(i, first + 0x800 * i) for i in range(n)]


def b3_event_index(b3_bgd, key):
    """Record number of a Burnout 3 event given its number or its ID text
    (e.g. "ONSGRCF"). The order of the records differs between tracks:
    ONSGRCF is record 1 in US/C3_V1 and record 5 in AS/M1_V1."""
    recs = event_records(b3_bgd, "b3")
    if isinstance(key, int):
        if not 0 <= key < len(recs):
            raise TrafficError("Burnout 3 event %d does not exist (%d records)" % (key, len(recs)))
        return key
    names = [gtid.decode(struct.unpack_from("<Q", b3_bgd, 8 + 8 * i)[0]) for i, _ in recs]
    hits = [i for i, n in enumerate(names) if n == key]
    if len(hits) != 1:
        raise TrafficError("Burnout 3 event %s found %d times among %s" % (key, len(hits), ", ".join(names)))
    return hits[0]


def directory(bgd, rec, game):
    v = struct.unpack_from("<8I", bgd, rec + (REV_DIR if game == "rev" else B3_DIR))
    return {"layout_size": v[0], "layout": v[1], "set_size": v[2], "set": v[3],
            "s3_size": v[4], "s3": v[5], "s4_size": v[6], "s4": v[7]}


def parse_s3(blob):
    ver, pos, n = struct.unpack_from("<3I", blob, 0)
    if ver != 0xC or not 12 + 20 * n <= pos <= len(blob):
        raise TrafficError("unexpected lane network header")
    groups = [struct.unpack_from("<5I", blob, 12 + 20 * i) for i in range(n)]
    return {"groups": [(a, b, c, cnt) for a, b, c, z, cnt in groups], "positions_at": pos,
            "positions": len(blob[pos:].rstrip(b"\0")) // 16 + 1}


def check_s3(blob):
    s = parse_s3(blob)
    p = []
    npos = (len(blob) - s["positions_at"]) // 16
    for i, (a, b, c, cnt) in enumerate(s["groups"]):
        if not (a < b < c and c + 18 * cnt <= s["positions_at"]):
            p.append("lane %d: arrays out of order" % i)
            continue
        for k in range(cnt + 1):
            lo, hi = struct.unpack_from("<2H", blob, a + 4 * k)
            if max(lo, hi) >= npos:
                p.append("lane %d: position index out of range" % i)
                break
        for k in range(cnt):
            r = blob[c + 18 * k:c + 18 * k + 18]
            for j in range(6):
                node, grp = struct.unpack_from("<H", r, 2 * j)[0], r[12 + j]
                if grp != 0xFF and (grp >= len(s["groups"]) or node >= s["groups"][grp][3]):
                    p.append("lane %d node %d: link to lane %d node %d does not exist" % (i, k, grp, node))
                    break
    return p[:10]


def parse_set(b, game):
    w = struct.unpack_from("<38I", b, 0x28)
    # The first 0x28 bytes are five u64 vehicle IDs of special vehicles (helicopter, L-train, tram,
    # monorail, plane; external review 2026-10-12, confirmed here: Burnout 3 AS/M1_V1 holds TSPCCAR2 and
    # TSPCCAR5, Revenge AS/K1_V2 TRAFASCAR12). Zero in most sets. The header proper starts at 0x28.
    it = iter(w)
    r = {"game": game, "lead": next(it), "special_vehicles": struct.unpack_from("<5Q", b, 0)}
    names = ["t1", "t2", "roads", "points", "nets"] + (["t6"] if game == "rev" else [])
    for nm in names:
        r[nm] = (next(it), next(it))
    r["vehicles"] = [(next(it), next(it), next(it)) for _ in range(6)]
    for nm in ("x1", "x2", "z"):
        r[nm] = (next(it), next(it))
    word = next(it)
    r["type"] = word & 0xFF                 # the game reads one byte [code 0x2E1D0C]; some files carry other bytes above it
    r["type_word"] = word
    return r


def check_set(b, game, s3_groups):
    """Structural checks of one traffic set against its lane network.
    s3_groups = node count per S3 group. Returns a list of problems."""
    r = parse_set(b, game)
    p = []

    def inside(ptr, size, what):
        if not 0xC0 <= ptr <= ptr + size <= len(b):
            p.append("%s outside the set" % what)
            return False
        return True
    rp, rn = r["roads"]
    lanes = 0
    if inside(rp, 16 * rn, "road table"):
        for i in range(rn):
            a, bb, nl, fl = struct.unpack_from("<4I", b, rp + 16 * i)
            lanes += nl
            if not (0 < nl <= 4 and not fl & ~0x803 and inside(a, 4 * nl, "road %d lanes" % i) and inside(bb, 4 * nl, "road %d B" % i)):
                p.append("road %d: unexpected fields" % i)
                continue
            for g in struct.unpack_from("<%dI" % nl, b, a):
                if g >= len(s3_groups):
                    p.append("road %d uses lane %d of %d" % (i, g, len(s3_groups)))
    pp, pn = r["points"]
    if inside(pp, 8 * pn, "point table"):
        for i in range(pn):
            g, node = struct.unpack_from("<2I", b, pp + 8 * i)
            if g >= len(s3_groups) or node >= s3_groups[g]:
                p.append("point %d at lane %d node %d does not exist" % (i, g, node))
    np_, nn = r["nets"]
    if nn < 1 or not inside(np_, 0x58 * nn, "network table"):
        p.append("no network")
    else:
        q = struct.unpack_from("<22I", b, np_)
        c = q[16]
        tail = b[np_ + 0x54:np_ + 0x58]
        npts, nt2 = (tail[2], tail[3]) if game == "rev" else (tail[0], tail[1])
        if nt2 != r["t2"][1]:
            p.append("network T2 count %d, header says %d" % (nt2, r["t2"][1]))
        if q[16:19] != (c, c, c) or c != lanes:
            p.append("network lane count %s, roads have %d lanes" % (q[16:19], lanes))
        if npts != pn:
            p.append("network point count %d, table has %d" % (npts, pn))
        sizes = {0: 28 * c, 1: 4 * c, 2: c, 3: c, 5: c, 6: c, 7: 20 * c, 8: c, 9: c, 10: 72 * pn, 11: pn}
        sizes[12] = 16 * nt2
        if game == "rev" and nn == 1:
            sizes[13] = (nt2 + 15) // 16 * 16 + 48 * c         # T2 index bytes, then per-lane state (single-network sets)
        ok = all(inside(q[k], n, "network array p%d" % k) for k, n in sizes.items())
        if ok and c:
            road = b[q[2]:q[2] + c]
            if max(road) != rn - 1 or list(road) != sorted(road):
                p.append("lane -> road table does not cover the roads in order")
            if b[q[8]:q[8] + c] != road or b[q[9]:q[9] + c] != b[q[3]:q[3] + c]:
                p.append("p8/p9 differ from p2/p3")
            for k in range(c):
                x = struct.unpack_from("<5I", b, q[7] + 20 * k)
                if not all(inside(x[j], 16, "lane %d block" % k) for j in range(3)):
                    break
            r["p0_zero"] = not any(b[q[0]:q[0] + 28 * c])
            if list(b[q[13]:q[13] + nt2]) != list(range(nt2)):
                p.append("p13 does not start with the T2 indices")
            if game == "rev" and nt2 == 0 and q[12] != q[13]:
                p.append("p12 differs from p13 although T2 is empty")
            tp = r["t2"][0]
            if nt2 and inside(tp, 24 * nt2, "T2 table"):
                for k in range(nt2):
                    e = struct.unpack_from("<4I8B", b, tp + 24 * k)
                    nl = e[9]
                    if not (0 < nl <= 4 and all(inside(e[j], 4 * nl, "T2 %d block" % k) for j in range(4))):
                        p.append("T2 entry %d: unexpected fields" % k)
                        continue
                    for ln in struct.unpack_from("<%dI" % nl, b, e[3]):
                        if ln >= c:
                            p.append("T2 entry %d names lane %d of %d" % (k, ln, c))
            if list(b[q[11]:q[11] + pn]) != list(range(pn)):
                p.append("p11 is not 0..n-1")
    for i, (vp, vn, vm) in enumerate(r["vehicles"]):
        if vn and inside(vp, 0x18 * vn, "vehicle list %d" % i):
            if sum(struct.unpack_from("<I", b, vp + 0x18 * k + 0x10)[0] for k in range(vn)) != vm:
                p.append("vehicle list %d: total differs" % i)
    zp, zn = r["z"]
    if zn:
        inside(zp, 0x20 * zn, "Z table")
    r["lanes"] = lanes
    return p[:12], r


SPECIAL_TYPE = {0: 6, 1: 7, 2: 8, 3: 9, 4: 10}     # road +0x0D bit -> spawn type (code 0x002E8BB8); same bit = vehicle slot (0x002E8B48)


def special_road_type(fl0d):
    """(type, slot) Revenge selects for a special road's +0x0D byte: the first set bit of 0..4; none -> (0, None)."""
    for bit in range(5):
        if fl0d >> bit & 1:
            return SPECIAL_TYPE[bit], bit
    return 0, None


def unsupported_special_weights(b):
    """GP-1 rule (research/gp1_tropical_drive_stability_2026_10_15/REPORT.md sections 1-3) on ONE Revenge traffic set `b`.
    A road flagged special (+0x0C bit 1) is spawned by 0x002E8478 with class 6 only, gated by the lane's class-6 weight
    (float 6 of the lane's 28-byte record in network table p0/p4). Revenge binds a participant to such a record only for
    special type 8 (0x002E3D48) with a vehicle in the selected slot; any other type, or an empty slot, leaves the
    participant NULL, which 0x002E63D4 passes to F2 unchecked (TLB misses). Returns, for every such road's lane whose
    class-6 weight is > 0: {"offset" (in the set), "value", "road", "net", "lane", "type", "slot"}.
    Retail Revenge AS/L1 roads 127/128 (type 8, slot 2 = TRAFASCAR12) do not match."""
    r = parse_set(b, "rev")
    rp, rn = r["roads"]
    slots = r["special_vehicles"]
    np_, nn = r["nets"]
    out, seen = [], set()
    for i in range(nn):
        q = struct.unpack_from("<14I", b, np_ + 0x58 * i)
        cnt = struct.unpack_from("<I", b, np_ + 0x58 * i + 0x40)[0]
        for lane in range(cnt):
            road = b[q[2] + lane]
            if road >= rn or not b[rp + 16 * road + 12] & 2:
                continue
            typ, slot = special_road_type(b[rp + 16 * road + 13])
            if typ == 8 and slots[slot]:
                continue
            for tab in (q[0], q[4]):                    # p0 / p4 (the same table in the known data; de-duplicated)
                a = tab + 28 * lane + 24
                if a in seen:
                    continue
                seen.add(a)
                v = struct.unpack_from("<f", b, a)[0]
                if v > 0:
                    out.append({"offset": a, "value": v, "road": road, "net": i, "lane": lane, "type": typ, "slot": slot})
    return out


def neutralise_unsupported_special_roads(b):
    """(set bytes, edits): every weight unsupported_special_weights() names set to 0.0. Nothing else changes - the
    roads stay special with their flags and geometry; ordinary roads, other classes and the vehicle lists are untouched.
    Idempotent (a second pass finds nothing)."""
    out = bytearray(b)
    edits = unsupported_special_weights(b)
    for e in edits:
        out[e["offset"]:e["offset"] + 4] = struct.pack("<f", 0.0)
    return bytes(out), edits


def convert_set(b3_set, host_set, s3_groups, zones=False, right_side=True, triggers=False, special_road_guard=False):
    """Burnout 3 traffic set -> Revenge traffic set.
    Kept from Burnout 3, bytes in place: roads, lane tables, speeds, per-lane
    vehicle amounts (p0), T2 and its parameters (p12), spawn points and
    weights, Z. Taken from the host (Revenge) set: the six vehicle lists.
    Dropped: T1, every network after the first, X1, X2.
    New: p13 = T2 index bytes followed by 48 zero bytes per lane.
    zones=False: the set is written as type 3 (spawn mode bit 0: the whole
    track is populated, the mode of online races). This is the verified form.
    zones=True: the Burnout 3 zone table is kept (bytes in place) and the set
    is written as type 2: traffic is spawned on the roads of the zone the
    player is in, as in retail race and Traffic Attack sets. Needs a Burnout
    3 set that has zones (its type 2 sets). Retail has this shape with one
    network: Revenge US/L2_V1 record OFFRRGEF.
    special_road_guard=True (opt-in, GP-1 2026-10-15; default off so the pinned
    outputs stay as they are): class-6 spawn weights of special roads Revenge
    cannot bind are set to 0.0 (neutralise_unsupported_special_roads)."""
    # Set flags (one byte at +0xBC) [code 0x2E1D0C; names from the external review 2026-10-12]:
    #   0x1 online (the whole track is populated), 0x2 right-side driving, 0x4 crash mode.
    # 0x2 is written from `right_side` (measured on the lane network, lanes.driving_side), NOT copied:
    # Burnout 3 sets it on left-hand tracks too. The five special-vehicle IDs at the start of the set
    # name Burnout 3 vehicles and are cleared. triggers=True keeps every Burnout 3 trigger
    # (EXPERIMENT, needs zones=True); otherwise only trigger 0 is written, the verified form.
    if triggers and not zones:
        raise TrafficError("all triggers are only converted together with the traffic hulls (zones)")
    bad, r = check_set(b3_set, "b3", s3_groups)
    if bad:
        raise TrafficError("Burnout 3 traffic set: %s" % bad[0])
    h = parse_set(host_set, "rev")
    null = h["x1"][0] if h["x1"][1] == 0 else 0
    out = bytearray(b3_set)
    special = [gtid.decode(x) for x in struct.unpack_from("<5Q", out, 0) if x]
    out[0:0x28] = bytes(0x28)
    out += bytes(-len(out) % 16)
    np_ = r["nets"][0]
    q = list(struct.unpack_from("<22I", out, np_))
    c, pn, nt2 = q[16], r["points"][1], r["t2"][1]
    if nt2 == 0 or not any(out[q[0]:q[0] + 28 * c]):
        raise TrafficError("this Burnout 3 set puts no vehicles on its lanes (no T2 / all amounts zero)")
    q[13] = len(out)
    out += bytes(range(nt2)) + bytes(-nt2 % 16) + bytes(48 * c)
    out += bytes(-len(out) % 16)
    q[14] = null
    struct.pack_into("<15I", out, np_, *q[:15])
    struct.pack_into("<HBB", out, np_ + 0x54, 0, pn, nt2)
    ntrig = 1
    if triggers:
        b3_tr = parse_triggers(b3_set, "b3")
        if b3_tr[0]["counts"]["kill"]:
            raise TrafficError("Burnout 3 trigger 0 has kill-filler entries; not handled")
        ntrig = len(b3_tr)
        for t in b3_tr[1:]:
            at = np_ + TRIGGER * t["index"]
            ptrs = [x if x < len(b3_set) else null for x in t["pointers"]]      # Burnout 3's null marker -> Revenge's
            struct.pack_into("<15I", out, at, *ptrs)
            cn = t["counts"]
            # Revenge has two more bytes after the lap byte; the three byte counts move from +0x53.. to +0x55..
            out[at + 0x53:at + 0x58] = bytes([0, 0, cn["kill"], cn["splitters"], cn["lights"]])
    vehicles = []
    for vp, vn, vm in h["vehicles"]:
        vehicles.append((len(out), vn, vm))
        out += host_set[vp:vp + 0x18 * vn]
        out += bytes(-len(out) % 16)
    words = [0x10, 0xC0, 0, r["t2"][0], nt2, r["roads"][0], r["roads"][1], r["points"][0], r["points"][1],
             np_, ntrig, vehicles[0][0], 0]        # T1 empty; T6 empty with its pointer as in retail
    for v in vehicles:
        words += list(v)
    if zones:
        if not r["x2"][1]:
            raise TrafficError("this Burnout 3 set has no zone table (it is not a type 2 set)")
        bad = check_zones(b3_set, "b3", s3_groups)
        if bad:
            raise TrafficError("Burnout 3 zone table: %s" % bad[0])
        words += [null, 0, r["x2"][0], r["x2"][1]]
    else:
        words += [null, 0, null, 0]
    words += [r["z"][0], r["z"][1]] if r["z"][1] else [null, 0]
    words += [(2 if right_side else 0) | (0 if zones else 1)]
    struct.pack_into("<38I", out, 0x28, *words)
    out += bytes(-len(out) % 0x800)
    bad, chk = check_set(bytes(out), "rev", s3_groups)
    if not bad:
        bad = check_triggers(bytes(out), "rev")
    if not bad and triggers:
        a_, b_ = parse_triggers(bytes(out), "rev"), parse_triggers(b3_set, "b3")
        if [(x["slice"], x["lap"], x["counts"]) for x in a_[1:]] != [(x["slice"], x["lap"], x["counts"]) for x in b_[1:]]:
            bad = ["later triggers do not read back as in Burnout 3"]
    if not bad and zones:
        bad = check_zones(bytes(out), "rev", s3_groups)
        if not bad and parse_zones(bytes(out), "rev") != parse_zones(b3_set, "b3"):
            bad = ["zone table does not read back as in Burnout 3"]
    if bad:
        raise TrafficError("converted traffic set: %s" % bad[0])
    guard = None
    if special_road_guard:
        # GP-1 (2026-10-15): the IDs cleared above leave Burnout 3's special roads (e.g. Tropical Drive 139/140, type 9)
        # without a vehicle Revenge can bind; their class-6 spawn weights are set to 0.0 (unsupported_special_weights).
        out, guard = neutralise_unsupported_special_roads(bytes(out))
        bad, _ = check_set(out, "rev", s3_groups)
        if bad or unsupported_special_weights(out):
            raise TrafficError("special-road guard: %s" % (bad[0] if bad else "weights left"))
    amounts = [sum(struct.unpack_from("<f", out, q[0] + 28 * k + 4 + 4 * j)[0] for k in range(c)) for j in range(6)]
    return bytes(out), {"roads": r["roads"][1], "lanes": chk["lanes"], "spawn_points": pn, "t2_entries": nt2,
                        "vehicles_per_class": [round(x, 1) for x in amounts],
                        "vehicle_lists": [v[1] for v in vehicles], "z_records": r["z"][1], "bytes": len(out),
                        "type": (2 if right_side else 0) | (0 if zones else 1), "zones": r["x2"][1] if zones else 0,
                        "triggers": ntrig, "right_side_driving": bool(right_side), "special_vehicles_dropped": special,
                        **({"special_road_guard": [{k: e[k] for k in ("offset", "road", "lane", "type", "value")} for e in guard]}
                           if guard is not None else {})}


def b3_right_side(b3_bgd, s3):
    """True for right-hand traffic, measured on the lane network. Raises when the network gives no clear answer."""
    side, r_, l_ = LN.driving_side(LN.lane_network(b3_bgd, "b3", s3))
    if side is None:
        raise TrafficError("driving side not clear from the lane network (%d right, %d left votes)" % (r_, l_))
    return side == "right"


def add_traffic(host_bgd, b3_bgd, b3_event=1, special_road_guard=False):
    """Works in PCSX2 (experiment 8, 2026-10-11). Use when the data does not
    fit the host's slots; add_traffic_in_place is the default because it
    leaves the file size and event records alone.
    Append Burnout 3's lane network and converted traffic sets to a
    Revenge GAMEDATA.BGD and point every event of the file at them (one new
    set per distinct host set, because the vehicle lists come from the host
    set). Nothing already in the file is moved or overwritten except the
    four directory words (set size, set, S3 size, S3) of each event record."""
    hs = RT.rev_sections(host_bgd)
    bs = RT.b3_sections(b3_bgd)
    s3 = b3_bgd[bs[3]:bs[4]]
    bad = check_s3(s3)
    if bad:
        raise TrafficError("Burnout 3 lane network: %s" % bad[0])
    groups = [g[3] for g in parse_s3(s3)["groups"]]
    brec = dict(event_records(b3_bgd, "b3"))[b3_event]
    bd = directory(b3_bgd, brec, "b3")
    if bd["s3"] != bs[3]:
        raise TrafficError("Burnout 3 event %d does not use the lane network at 0x%X" % (b3_event, bs[3]))
    b3_set = b3_bgd[bd["set"]:bd["set"] + bd["set_size"]]
    right = b3_right_side(b3_bgd, s3)
    out = bytearray(host_bgd)
    out += bytes(-len(out) % 0x800)
    s3_at = len(out)
    out += s3
    out += bytes(-len(out) % 0x800)
    changed, cache = [], {}
    for i, rec in event_records(host_bgd, "rev"):
        d = directory(host_bgd, rec, "rev")
        if d["s3"] != hs[3] or not d["set_size"]:
            continue
        key = d["set"]
        if key not in cache:
            host_set = host_bgd[d["set"]:d["set"] + d["set_size"]]
            new, rep = convert_set(b3_set, host_set, groups, right_side=right, special_road_guard=special_road_guard)
            cache[key] = (len(out), len(new), rep)
            out += new
        at, size, rep = cache[key]
        struct.pack_into("<4I", out, rec + REV_DIR + 8, size, at, len(s3), s3_at)
        changed.append(i)
    if not changed:
        raise TrafficError("no event in the host file uses its lane network")
    first = next(iter(cache.values()))[2]
    return bytes(out), {"events_repointed": changed, "lane_network_at": s3_at, "lane_network_bytes": len(s3),
                        "lanes_in_network": len(groups), "sets_written": len(cache), "set": first,
                        "burnout3_event": b3_event, "file_growth": len(out) - len(host_bgd)}


def add_traffic_in_place(host_bgd, b3_bgd, b3_event=1, attack_profile=None, attack_strength=1.0, attack_cap=True,
                         attack_zones_event=None, attack_triggers=False, special_road_guard=False):
    """Same data as add_traffic, but written over the host's lane network and
    over every traffic set an event uses, at their existing offsets. No event
    directory changes and the file keeps its size, so the result does not
    depend on how the game locates these pieces.
    attack_profile: traffic_attack_profile() of the ORIGINAL host file. The
    sets it names (those of Traffic Attack events) get their amounts scaled
    to the host set's density per direction class; every other set is
    written exactly as without the option.
    attack_strength None: amounts are left as in Burnout 3.
    attack_zones_event: number of a Burnout 3 event whose (type 2) set is the
    source for those sets instead, converted with its zone table.
    special_road_guard: passed to convert_set for every set (default off)."""
    hs, bs = RT.rev_sections(host_bgd), RT.b3_sections(b3_bgd)
    s3 = b3_bgd[bs[3]:bs[4]]
    bad = check_s3(s3)
    if bad:
        raise TrafficError("Burnout 3 lane network: %s" % bad[0])
    groups = [g[3] for g in parse_s3(s3)["groups"]]
    bd = directory(b3_bgd, dict(event_records(b3_bgd, "b3"))[b3_event], "b3")
    b3_set = b3_bgd[bd["set"]:bd["set"] + bd["set_size"]]
    right = b3_right_side(b3_bgd, s3)
    out = bytearray(host_bgd)
    if len(s3) > hs[4] - hs[3]:
        raise TrafficError("Burnout 3 lane network does not fit the host's")
    out[hs[3]:hs[4]] = s3 + bytes(hs[4] - hs[3] - len(s3))
    done, events, rep, rep1 = {}, [], None, None
    attack, b3_classes, b3_lanes = [], None, None
    for i, rec in event_records(host_bgd, "rev"):
        d = directory(host_bgd, rec, "rev")
        if not d["set_size"]:
            continue
        if d["s3"] != hs[3]:
            raise TrafficError("event %d uses a lane network at 0x%X" % (i, d["s3"]))
        if d["set"] not in done:
            host_set = host_bgd[d["set"]:d["set"] + d["set_size"]]
            is_attack = bool(attack_profile) and d["set"] in attack_profile
            if is_attack and attack_zones_event is not None:
                zd = directory(b3_bgd, dict(event_records(b3_bgd, "b3"))[attack_zones_event], "b3")
                new, zrep = convert_set(b3_bgd[zd["set"]:zd["set"] + zd["set_size"]], host_set, groups, zones=True,
                                        right_side=right, triggers=attack_triggers, special_road_guard=special_road_guard)
            else:
                new, rep1 = convert_set(b3_set, host_set, groups, right_side=right, special_road_guard=special_road_guard)
                zrep = None
            if is_attack:
                if b3_lanes is None:
                    try:
                        b3_classes, b3_lanes = LN.lane_classes(b3_bgd, "b3")
                    except LN.LaneError as e:
                        raise TrafficError("lane directions of the Burnout 3 track: %s" % e)
                if attack_strength is None:
                    dens, peak = set_density(new, "rev", b3_classes, b3_lanes)
                    arep = {"factors": None, "before": dens, "after": dens, "host": attack_profile[d["set"]]["density"],
                            "strength": None, "peak_lane_amount": peak, "lane_cap": None, "lanes_capped": 0, "capped": []}
                else:
                    new, arep = match_density(new, attack_profile[d["set"]]["density"], b3_classes, b3_lanes, attack_strength,
                                              lane_cap=attack_profile[d["set"]]["peak_lane_amount"] if attack_cap else None)
                arep["zones"] = zrep["zones"] if zrep else 0
                arep["set_type"] = zrep["type"] if zrep else rep1["type"]
                arep["triggers"] = zrep["triggers"] if zrep else 1
                arep["burnout3_event"] = attack_zones_event if zrep else b3_event
                bad, _ = check_set(new, "rev", groups)
                if bad:
                    raise TrafficError("scaled traffic set: %s" % bad[0])
                if special_road_guard and unsupported_special_weights(new):
                    raise TrafficError("scaled traffic set: special-road guard weights reappeared")
                arep["events"] = attack_profile[d["set"]]["events"]
                arep["set_offset"] = d["set"]
                attack.append(arep)
            elif rep is None:
                rep = rep1
            if len(new) > d["set_size"]:
                raise TrafficError("converted set does not fit event %d's set" % i)
            out[d["set"]:d["set"] + d["set_size"]] = new + bytes(d["set_size"] - len(new))
            done[d["set"]] = True
        events.append(i)
    if attack_profile and len(attack) != len(attack_profile):
        raise TrafficError("a Traffic Attack set of the host was not found among the event records")
    report = {"mode": "in place", "events": events, "sets_written": len(done), "lanes_in_network": len(groups),
              "set": rep or rep1, "burnout3_event": b3_event, "file_growth": 0}
    if attack_profile is not None:
        report["traffic_attack_sets"] = attack
        if b3_lanes is not None:
            report["lane_directions"] = "".join({LN.SAME: "+", LN.ONCOMING: "-", LN.OTHER: "."}[c["class"]] for c in b3_classes)
    return bytes(out), report


def control_simple_set(host_bgd, event=9, donor=1):
    """CONTROL on an otherwise retail track: give `event` (and every event
    sharing its set) a copy of `donor`'s traffic set, written in place. With
    US/L2_V2 this puts Revenge's own type-3 single-network set under the
    Eliminator, the shape the converter produces."""
    recs = dict(event_records(host_bgd, "rev"))
    d, s = directory(host_bgd, recs[event], "rev"), directory(host_bgd, recs[donor], "rev")
    src = host_bgd[s["set"]:s["set"] + s["set_size"]]
    a, b = parse_set(host_bgd[d["set"]:d["set"] + d["set_size"]], "rev"), parse_set(src, "rev")
    if s["set_size"] > d["set_size"] or s["set"] == d["set"]:
        raise TrafficError("donor set does not fit or is the same set")
    out = bytearray(host_bgd)
    out[d["set"]:d["set"] + d["set_size"]] = src + bytes(d["set_size"] - len(src))
    shared = [i for i, r in recs.items() if directory(host_bgd, r, "rev")["set"] == d["set"]]
    return bytes(out), {"events_affected": shared, "donor_event": donor,
                        "was": {"type": a["type"], "networks": a["nets"][1], "t2": a["t2"][1], "t6": a["t6"][1], "x2": a["x2"][1]},
                        "now": {"type": b["type"], "networks": b["nets"][1], "t2": b["t2"][1], "t6": b["t6"][1], "x2": b["x2"][1]}}


EXPERIMENTS = ("inside", "tail", "grow", "s3tail", "setsize", "s3size")


def experiment(bgd, kind, event=9):
    """Single-variable loading experiments on top of a WORKING in-place
    traffic file (Phase 5.5, why does appended data not load?).
      inside  the event's traffic set is copied to unused space inside the
              file (after the lane network) and the directory points there;
              the set at the old place gets zero vehicle amounts.
      tail    same, but the copy is placed after the end of the file.
      grow    nothing moves; 0x800 zero bytes are appended.
      s3tail  the lane network is copied after the end of the file and the
              directory points there; the old copy gets lane count 0.
      setsize nothing moves; the set size in the directory is reduced to the
              data present (0x4000 instead of the host's 0xC800).
      s3size  nothing moves; the lane network size in the directory is
              reduced to the data present (0x3E800 instead of 0x5E000).
    In every case the old data is made unable to produce traffic, so seeing
    traffic proves the game used the new location."""
    if kind not in EXPERIMENTS:
        raise TrafficError("unknown experiment %r" % kind)
    hs = RT.rev_sections(bgd)
    recs = dict(event_records(bgd, "rev"))
    d = directory(bgd, recs[event], "rev")
    out = bytearray(bgd)
    rep = {"experiment": kind, "event": event, "old_size": len(bgd)}
    sharing = [i for i, r in recs.items() if directory(bgd, r, "rev")["set"] == d["set"]]
    if kind == "grow":
        out += bytes(0x800)
    elif kind == "setsize":
        # nothing moves; the directory's set size shrinks to the data actually present,
        # so the lane network is loaded closer behind the set in memory
        for i in sharing:
            dd = directory(bgd, recs[i], "rev")
            used = (len(bgd[dd["set"]:dd["set"] + dd["set_size"]].rstrip(b"\0")) + 0x7FF) // 0x800 * 0x800
            struct.pack_into("<I", out, recs[i] + REV_DIR + 8, used)
        rep.update(set_size_was=d["set_size"], set_size_now=struct.unpack_from("<I", out, recs[event] + REV_DIR + 8)[0],
                   events_changed=sharing)
    elif kind == "s3size":
        used = (len(bgd[hs[3]:hs[4]].rstrip(b"\0")) + 0x7FF) // 0x800 * 0x800
        users = [i for i, r in recs.items() if directory(bgd, r, "rev")["s3"] == hs[3]]
        for i in users:
            struct.pack_into("<I", out, recs[i] + REV_DIR + 16, used)
        rep.update(s3_size_was=d["s3_size"], s3_size_now=used, events_changed=users)
    elif kind in ("inside", "tail"):
        st = bytes(out[d["set"]:d["set"] + d["set_size"]])
        used = (len(st.rstrip(b"\0")) + 0x7FF) // 0x800 * 0x800
        if kind == "inside":
            s3 = parse_s3(bytes(out[hs[3]:hs[4]]))
            end = hs[3] + s3["positions_at"] + 16 * s3["positions"]
            at = (end + 0x7FF) // 0x800 * 0x800
            if at + d["set_size"] > hs[4] or any(out[at:at + d["set_size"]]):
                raise TrafficError("no free room after the lane network")
        else:
            at = len(out)
            out += bytes(d["set_size"])
        out[at:at + used] = st[:used]
        r = parse_set(st, "rev")
        q = struct.unpack_from("<22I", st, r["nets"][0])
        out[d["set"] + q[0]:d["set"] + q[0] + 28 * q[16]] = bytes(28 * q[16])     # old set: no vehicles
        for i in sharing:
            struct.pack_into("<I", out, recs[i] + REV_DIR + 12, at)
        rep.update(set_was=d["set"], set_now=at, events_repointed=sharing)
    else:
        s3 = bytes(out[hs[3]:hs[4]])
        at = len(out)
        out += s3
        struct.pack_into("<I", out, hs[3] + 8, 0)                                 # old network: no lanes
        users = [i for i, r in recs.items() if directory(bgd, r, "rev")["s3"] == hs[3]]
        for i in users:
            struct.pack_into("<I", out, recs[i] + REV_DIR + 20, at)
        rep.update(s3_was=hs[3], s3_now=at, events_repointed=users)
    rep["new_size"] = len(out)
    return bytes(out), rep


# ---------------------------------------------------------------------------
# Event-specific density: Traffic Attack (docs/traffic_format.md, section 6)
# ---------------------------------------------------------------------------

TRAFFIC_ATTACK_ID = re.compile(r"^T[0-9A-Z](US|EU|AS)")       # T1USL220TFLR, TAUSL220TFLR
CLASSES = (LN.SAME, LN.ONCOMING, LN.OTHER)


def set_lane_table(b, game):
    """Lanes of the first network of a set:
    [{'group': S3 lane, 'start': first node, 'amounts': offset of six floats}]."""
    r = parse_set(b, game)
    if not r["nets"][1]:
        return []
    q = struct.unpack_from("<22I", b, r["nets"][0])
    out = []
    for l in range(q[16]):
        road, idx = b[q[2] + l], b[q[3] + l]
        ra, rb, rn, rf = struct.unpack_from("<4I", b, r["roads"][0] + 16 * road)
        out.append({"group": struct.unpack_from("<I", b, ra + 4 * idx)[0],
                    "start": struct.unpack_from("<I", b, rb + 4 * idx)[0],
                    "amounts": q[0] + 28 * l + 4})
    return out


def set_density(b, game, classes, lanes):
    """Vehicle amount per kilometre of lane, by direction class, for the
    first network of a set. `classes`/`lanes` from lanes.lane_classes() of
    the lane network the set belongs to. A set lane covers its S3 lane from
    its start node to the next set lane's start on the same S3 lane.
    The unit of "amount" is not established in code; only ratios are used."""
    table = set_lane_table(b, game)
    starts = {}
    for t in table:
        starts.setdefault(t["group"], set()).add(t["start"])
    acc = {c: [0.0, 0.0] for c in CLASSES}
    peak = 0.0
    for t in table:
        dist = lanes[t["group"]][1]
        if not dist:
            continue
        ss = sorted(starts[t["group"]])
        k = ss.index(t["start"])
        end = ss[k + 1] if k + 1 < len(ss) else len(dist) - 1
        length = abs(dist[min(end, len(dist) - 1)] - dist[min(t["start"], len(dist) - 1)])
        amount = sum(struct.unpack_from("<6f", b, t["amounts"]))
        c = classes[t["group"]]["class"]
        acc[c][0] += amount
        acc[c][1] += length
        peak = max(peak, amount)
    return {c: {"amount": round(a, 1), "metres": round(m), "per_km": round(a / m * 1000, 2) if m else 0.0}
            for c, (a, m) in acc.items()}, round(peak, 1)


def traffic_attack_profile(host_bgd):
    """From an ORIGINAL Revenge GAMEDATA.BGD: for every traffic set used by a
    Traffic Attack event, its density per direction class.
    -> {set offset: {'events': [...], 'density': {...}, 'peak_lane_amount': x}}"""
    classes, lanes = LN.lane_classes(host_bgd, "rev")
    out = {}
    for i, rec in event_records(host_bgd, "rev"):
        name = gtid.decode(struct.unpack_from("<Q", host_bgd, 8 + 8 * i)[0])
        d = directory(host_bgd, rec, "rev")
        if not TRAFFIC_ATTACK_ID.match(name) or not d["set_size"]:
            continue
        if d["set"] not in out:
            dens, peak = set_density(host_bgd[d["set"]:d["set"] + d["set_size"]], "rev", classes, lanes)
            out[d["set"]] = {"events": [], "density": dens, "peak_lane_amount": peak}
        out[d["set"]]["events"].append(name)
    return out


def match_density(rev_set, target, classes, lanes, strength=1.0, max_factor=16.0, lane_cap=None):
    """Scale the per-lane vehicle amounts of a converted (Revenge format) set
    so that the amount per kilometre of same-way, oncoming and other lanes
    equals `target` (a 'density' dict from traffic_attack_profile).
    strength scales the result (1.0 = the host's density). lane_cap: no lane
    gets a larger total than this (the largest lane total of the host set, so
    that every value stays inside the range the retail set uses). Only the 6
    floats per lane in p0 change. -> (set, report)"""
    before, _ = set_density(rev_set, "rev", classes, lanes)
    factors = {}
    for c in CLASSES:
        have, want = before[c]["per_km"], target[c]["per_km"] * strength
        f = want / have if have > 0 and target[c]["metres"] > 0 else 1.0
        factors[c] = min(f, max_factor)
    out = bytearray(rev_set)
    capped_lanes = 0
    for t in set_lane_table(rev_set, "rev"):
        f = factors[classes[t["group"]]["class"]]
        vals = [v * f for v in struct.unpack_from("<6f", out, t["amounts"])]
        if lane_cap and sum(vals) > lane_cap:
            g = lane_cap / sum(vals)
            vals = [v * g for v in vals]
            capped_lanes += 1
        struct.pack_into("<6f", out, t["amounts"], *vals)
    out = bytes(out)
    after, peak = set_density(out, "rev", classes, lanes)
    return out, {"factors": {c: round(f, 3) for c, f in factors.items()}, "before": before, "after": after,
                 "host": target, "strength": strength, "peak_lane_amount": peak,
                 "lane_cap": lane_cap, "lanes_capped": capped_lanes,
                 "capped": [c for c in CLASSES if factors[c] == max_factor]}


# ---------------------------------------------------------------------------
# Zones (the table this file used to call X2). docs/traffic_format.md section 7
# ---------------------------------------------------------------------------

ZONE = 0x18


def parse_zones(b, game):
    """Zone table of a set: [{'first','last' (lap line nodes), 'roads': [road],
    'starts': [u16 per road], 'spans': [(node, node, S3 lane, flag)]}].
    Entry (0x18 bytes, same in both games [code: Revenge 0x2E3070, 0x2E4478;
    data: Burnout 3]): +0 ptr spans (6 bytes each), +4 first node, +8 last
    node, +0xC ptr u16 per road, +0x10 ptr road index bytes, +0x14 u8 span
    count, +0x15 u8 road count."""
    r = parse_set(b, game)
    zp, zn = r["x2"]
    out = []
    for i in range(zn):
        e = b[zp + ZONE * i:zp + ZONE * (i + 1)]
        ps, lo, hi, pn, pr = struct.unpack_from("<5I", e, 0)
        ns, nr = e[0x14], e[0x15]
        out.append({"first": lo, "last": hi, "roads": list(b[pr:pr + nr]),
                    "starts": list(struct.unpack_from("<%dH" % nr, b, pn)) if nr else [],
                    "spans": [struct.unpack_from("<HHBB", b, ps + 6 * k) for k in range(ns)],
                    "pointers": (ps, pn, pr), "tail": bytes(e[0x16:])})
    return out


def check_zones(b, game, s3_groups):
    """Problems of the zone table (empty list = consistent)."""
    r = parse_set(b, game)
    zp, zn = r["x2"]
    p = []
    if not zn:
        return p
    if not 0xC0 <= zp <= zp + ZONE * zn <= len(b):
        return ["zone table outside the set"]
    zones = parse_zones(b, game)
    nroads = r["roads"][1]
    expect = 0
    for i, z in enumerate(zones):
        ps, pn, pr = z["pointers"]
        if not all(0xC0 <= q <= len(b) for q in (ps, pn, pr)) or ps + 6 * len(z["spans"]) > len(b):
            p.append("zone %d: pointer outside the set" % i)
            continue
        if z["first"] != expect or z["last"] < z["first"]:
            p.append("zone %d covers nodes %d..%d, expected to start at %d" % (i, z["first"], z["last"], expect))
        expect = z["last"] + 1
        if any(x >= nroads for x in z["roads"]):
            p.append("zone %d names a road beyond %d" % (i, nroads))
        for a, c, lane, flag in z["spans"]:
            if lane >= len(s3_groups) or max(a, c) > s3_groups[lane]:
                p.append("zone %d: span on lane %d nodes %d, %d does not exist" % (i, lane, a, c))
                break
    return p[:8]


# ---------------------------------------------------------------------------
# Triggers (the 0x58-byte records this file used to call networks).
# Criterion: CB4TriggerStruct. docs/traffic_format.md section 8.
# ---------------------------------------------------------------------------

TRIGGER = 0x58
# (pointer word, count field, element size, what)   [code: Revenge 0x2E4FFC]
TRIGGER_ARRAYS = (
    (1, "speeds", 4, "speed per valve lane (float)"),
    (2, "speeds", 1, "road (valve) of each speed entry"),
    (3, "speeds", 1, "lane within the road"),
    (4, "flows", 28, "flow record per lane: u32, six floats (vehicles per 60 clock units, by category)"),
    (5, "flows", 1, "road of each flow entry"),
    (6, "flows", 1, "lane within the road"),
    (7, "third", 20, "20-byte record per lane (three pointers, 0, 1)"),
    (8, "third", 1, "road"),
    (9, "third", 1, "lane within the road"),
    (0, "kill", 6, "6-byte records, read with the count the game keeps at +0x55 (Revenge)"),
    (10, "splitters", 72, "splitter change: three slots of six u32"),
    (11, "splitters", 1, "splitter (point) index"),
    (12, "lights", 16, "light timing: four floats"),
    (13, "lights", 1, "traffic light (T2) index"),
    (14, "p14", 12, "12-byte records (bytes +0xA, +0xB = road, lane)"),
)


def parse_triggers(b, game):
    """Every trigger of a set: counts, activation fields and the 15 pointers.
    Revenge keeps two extra bytes after the lap byte, so its three byte
    counts sit at +0x55..+0x57 and Burnout 3's at +0x53..+0x55."""
    r = parse_set(b, game)
    tp, tn = r["nets"]
    out = []
    for k in range(tn):
        t = b[tp + TRIGGER * k:tp + TRIGGER * (k + 1)]
        w = struct.unpack_from("<19I", t, 0)
        c = 0x55 if game == "rev" else 0x53
        out.append({"index": k, "pointers": list(w[:15]),
                    "counts": {"p14": w[15], "speeds": w[16], "flows": w[17], "third": w[18],
                               "kill": t[c], "splitters": t[c + 1], "lights": t[c + 2]},
                    "time": struct.unpack_from("<f", t, 0x4C)[0], "slice": struct.unpack_from("<H", t, 0x50)[0], "lap": t[0x52],
                    "extra": bytes(t[0x53:0x55]) if game == "rev" else bytes(t[0x56:0x58])})
    return out


def check_triggers(b, game):
    """Bounds and index checks of every trigger of a set."""
    r = parse_set(b, game)
    p = []
    nroads, npoints, nlights = r["roads"][1], r["points"][1], r["t2"][1]
    lanes_of = [struct.unpack_from("<I", b, r["roads"][0] + 16 * i + 8)[0] for i in range(nroads)]
    for t in parse_triggers(b, game):
        for word, cname, size, what in TRIGGER_ARRAYS:
            n, ptr = t["counts"][cname], t["pointers"][word]
            if not n:
                continue
            if not 0xC0 <= ptr <= ptr + size * n <= len(b):
                p.append("trigger %d: %s (pointer %d) outside the set" % (t["index"], cname, word))
                continue
            vals = b[ptr:ptr + n]
            if word in (2, 5, 8) and max(vals) >= nroads:
                p.append("trigger %d: %s names road %d of %d" % (t["index"], cname, max(vals), nroads))
            if word in (3, 6, 9):
                roads = b[t["pointers"][word - 1]:t["pointers"][word - 1] + n]
                if any(rd < nroads and ln >= lanes_of[rd] for rd, ln in zip(roads, vals)):
                    p.append("trigger %d: %s names a lane its road does not have" % (t["index"], cname))
            if word == 11 and max(vals) >= max(npoints, 1):
                p.append("trigger %d: splitter %d of %d" % (t["index"], max(vals), npoints))
            if word == 13 and max(vals) >= max(nlights, 1):
                p.append("trigger %d: light %d of %d" % (t["index"], max(vals), nlights))
    return p[:8]
