"""fr_props - read-only parser for the Burnout 3 Xbox STATIC.DAT prop section (prop types, placements, per-unit lists).
Unknown bytes are kept; serialize() rebuilds the whole file byte for byte (the prop tail is RE-LAID OUT from the decoded
records by the retail layout rules, header pointers recomputed and compared with the file).

Header (0x60 B, version 0x27; KB XBOX_TRACK_FORMATS s4, WM2 wm2_static.py):
  +0x04 file size | +0x36 s16 prop-type count T | +0x3C -> T x 0x70-B prop-type records (+ their LOD vertex / index data,
  kept raw) | +0x40 u32 placement count P | +0x44 -> u8[T] per-type class byte | +0x48 -> P x 0x40-B matrices (16-aligned)
  | +0x4C -> u32[U] -> per unit u8[T] counts | +0x50 -> u32[U] (4-aligned) -> per unit u32[T] -> per (unit, type) list of
  count u32 entries | +0x54 s16 unit count U | +0x58 unit table 16 B x U (4-aligned) | +0x5C after-units | zero pad.
Consumer (Takedawn generated code, read only): sub_0018CBC0 (called from the track system set-up sub_001AA100 at 0x1AA41B
with eax = track system + 0x128C74) copies these into a run-time prop table: matrices (count read as u16 from +0x40),
class bytes (count read as u8 from +0x36), per-unit counts, per-unit lists; each run-time entry = file u16 matrix index,
byte 2 := the TYPE INDEX (the list it sits in), byte 3 := 0. The upper 16 bits of a file entry are NOT read.
"""
import struct

from fr_common import Reader, need, place, al

VERSION = 0x27
HDR = 0x60
MAX_TYPES, MAX_PLACE, MAX_UNITS = 255, 0xFFFF, 4096


def parse(d):
    r = Reader(d)
    need(len(d) >= HDR and len(d) % 0x8000 == 0, "STATIC size 0x%X" % len(d))
    need(r.u32(0) == VERSION and r.u32(4) == len(d), "STATIC version / size field")
    hdr = d[0:HDR]
    npt, nunit = r.s16(0x36), r.s16(0x54)
    p3c, nplace, p44, p48, p4c, p50, ut, after = (r.u32(o) for o in (0x3C, 0x40, 0x44, 0x48, 0x4C, 0x50, 0x58, 0x5C))
    need(0 <= npt <= MAX_TYPES and 0 <= nplace <= MAX_PLACE and 0 < nunit <= MAX_UNITS, "STATIC prop counts (%d, %d, %d)" % (npt, nplace, nunit))
    need(p44 >= HDR and p44 + npt <= len(d), "+0x44 pointer")
    types = []
    if npt:
        need(HDR <= p3c and p3c + 0x70 * npt <= p44, "+0x3C prop-type array")
        for i in range(npt):
            raw = r.take(p3c + 0x70 * i, 0x70, "prop type", claim=False)
            types.append(decode_type(raw))
    pbytes = r.take(p44, npt, "+0x44 class bytes")
    cur = p44 + npt
    rules = []

    def rule(ok, msg):
        if not ok:
            rules.append(msg)
    rule(p48 == al(cur, 16), "+0x48 at 0x%X, rule 0x%X" % (p48, al(cur, 16)))
    mats = [r.unpack("<16f", p48 + 0x40 * i, "matrix") for i in range(nplace)]
    cur = p48 + 0x40 * nplace
    rule(p4c == cur, "+0x4C at 0x%X, rule 0x%X" % (p4c, cur))
    q4c = r.unpack("<%dI" % nunit, p4c, "+0x4C array")
    cur = p4c + 4 * nunit
    counts = []
    for u, q in enumerate(q4c):
        if q == 0:
            counts.append(None)
            continue
        rule(q == cur, "+0x4C[%d] at 0x%X, rule 0x%X" % (u, q, cur))
        counts.append(list(r.take(q, npt, "+0x4C counts")))
        cur = q + npt
    rule(p50 == al(cur, 4), "+0x50 at 0x%X, rule 0x%X" % (p50, al(cur, 4)))
    q50 = r.unpack("<%dI" % nunit, p50, "+0x50 array")
    cur = p50 + 4 * nunit
    lists = []
    for u, q in enumerate(q50):
        if q == 0:
            need(counts[u] is None or not any(counts[u]), "+0x50[%d] null with counts" % u)
            lists.append(None)
            continue
        rule(q == cur, "+0x50[%d] at 0x%X, rule 0x%X" % (u, q, cur))
        sub = r.unpack("<%dI" % npt, q, "+0x50 sub-array") if npt else ()
        cur = q + 4 * npt
        per = []
        for k, x in enumerate(sub):
            c = counts[u][k] if counts[u] is not None else 0
            if x == 0:
                need(c == 0, "+0x50[%d][%d] null with count %d" % (u, k, c))
                per.append(None)
                continue
            need(c > 0, "+0x50[%d][%d] list with count 0" % (u, k))
            rule(x == cur, "+0x50[%d][%d] at 0x%X, rule 0x%X" % (u, k, x, cur))
            ent = r.unpack("<%dI" % c, x, "+0x50 list")
            per.append(list(ent))
            cur = x + 4 * c
        lists.append(per)
    rule(ut == al(cur, 4), "unit table at 0x%X, rule 0x%X" % (ut, al(cur, 4)))
    need(rules == [], "prop tail is not in the retail layout: %s" % rules[:3])
    need(ut + 16 * nunit == after <= len(d), "unit table / after-units")
    # semantic checks (data): every matrix listed once; entry low 16 bits = matrix index; upper bits = class byte << 16
    seen = [0] * nplace
    upper_eq_class = upper_total = 0
    for u, per in enumerate(lists):
        if per is None:
            continue
        for k, ent in enumerate(per):
            for e in ent or ():
                need((e & 0xFFFF) < nplace, "unit %d type %d: matrix %d >= %d" % (u, k, e & 0xFFFF, nplace))
                seen[e & 0xFFFF] += 1
                upper_total += 1
                upper_eq_class += (e >> 16) == pbytes[k]
    o = {"size": len(d), "prefix": d[0:p44], "types": types, "pbytes": pbytes, "matrices": mats, "counts": counts,
         "lists": lists, "suffix_at": ut, "suffix": d[ut:], "nunit": nunit,
         "check": {"matrices_listed_once": seen.count(1) == nplace, "entries": upper_total,
                   "upper16_equals_class_byte": upper_eq_class, "class_byte_equals_type_index":
                   sum(1 for k, b in enumerate(pbytes) if b == k)}}
    return o


def decode_type(raw):
    """0x70-B prop-type record: known fields only (REVIEW CLAIM_MATRIX 5.7, KB s4); everything kept in raw"""
    return {"raw": raw, "lod_flags": raw[0x62], "mat_idx": struct.unpack_from("<3h", raw, 0x5C),
            "switch_dist": struct.unpack_from("<f", raw, 0x64)[0], "draw_dist": struct.unpack_from("<f", raw, 0x68)[0],
            "w6c": struct.unpack_from("<f", raw, 0x6C)[0]}


def build_tail(o, p44):
    """lay out +0x44 .. unit table by the retail rules -> (bytes, pointer dict)"""
    npt = len(o["pbytes"])
    out = bytearray()
    base = p44

    def at():
        return base + len(out)

    def pad(a):
        out.extend(bytes(al(at(), a) - at()))
    out += o["pbytes"]
    pad(16)
    p48 = at()
    for m in o["matrices"]:
        out += struct.pack("<16f", *m)
    p4c = at()
    arr4c = len(out)
    out += bytes(4 * o["nunit"])
    q4c = []
    for c in o["counts"]:
        if c is None:
            q4c.append(0)
            continue
        need(len(c) == npt, "counts length != type count")
        q4c.append(at())
        out += bytes(c)
    struct.pack_into("<%dI" % o["nunit"], out, arr4c, *q4c)
    pad(4)
    p50 = at()
    arr50 = len(out)
    out += bytes(4 * o["nunit"])
    q50 = []
    for u, per in enumerate(o["lists"]):
        if per is None:
            q50.append(0)
            continue
        q50.append(at())
        subpos = len(out)
        out += bytes(4 * npt)
        sub = []
        for k, ent in enumerate(per):
            if ent is None:
                sub.append(0)
                continue
            need(o["counts"][u] is not None and o["counts"][u][k] == len(ent), "list length != count (unit %d type %d)" % (u, k))
            sub.append(at())
            out += struct.pack("<%dI" % len(ent), *ent)
        if npt:
            struct.pack_into("<%dI" % npt, out, subpos, *sub)
    struct.pack_into("<%dI" % o["nunit"], out, arr50, *q50)
    pad(4)
    return bytes(out), {"p48": p48, "p4c": p4c, "p50": p50, "ut": at()}


def serialize(o):
    prefix = bytearray(o["prefix"])
    p44 = struct.unpack_from("<I", prefix, 0x44)[0]
    tail, ptr = build_tail(o, p44)
    need(len(o["matrices"]) <= MAX_PLACE and len(o["pbytes"]) <= MAX_TYPES, "counts above the consumer's field widths")
    struct.pack_into("<I", prefix, 0x40, len(o["matrices"]))
    struct.pack_into("<h", prefix, 0x36, len(o["pbytes"]))
    struct.pack_into("<I", prefix, 0x48, ptr["p48"])
    struct.pack_into("<I", prefix, 0x4C, ptr["p4c"])
    struct.pack_into("<I", prefix, 0x50, ptr["p50"])
    need(ptr["ut"] == o["suffix_at"], "content change moves the unit table (0x%X -> 0x%X): not supported by this "
         "research serializer (no writer)" % (o["suffix_at"], ptr["ut"]))
    return place(o["size"], [(0, bytes(prefix)), (p44, tail), (o["suffix_at"], o["suffix"])])


def instances(o):
    """flat placement list: unit, type, matrix index, position (matrix elements 12..14)"""
    out = []
    for u, per in enumerate(o["lists"]):
        for k, ent in enumerate(per or ()):
            for e in ent or ():
                m = o["matrices"][e & 0xFFFF]
                out.append({"unit": u, "type": k, "matrix": e & 0xFFFF, "pos": m[12:15], "m15": m[15]})
    return out


def summary(o):
    inst = instances(o)
    t = o["types"]
    return {"prop_types": len(t), "placements": len(o["matrices"]), "units": o["nunit"],
            "units_with_props": sum(1 for c in o["counts"] if c and any(c)), "check": o["check"],
            "class_bytes": sorted(set(o["pbytes"])),
            "m15_values": sorted({round(i["m15"], 6) for i in inst}),
            "row_w_values": sorted({round(m[q], 6) for m in o["matrices"] for q in (3, 7, 11)}),
            "draw_dist_range": [min((x["draw_dist"] for x in t), default=None), max((x["draw_dist"] for x in t), default=None)],
            "records": len(t) + len(o["matrices"])}


if __name__ == "__main__":
    import json
    import sys
    from fr_common import read_ro
    d = read_ro(sys.argv[1])
    o = parse(d)
    print(json.dumps(summary(o), indent=1))
    print("identical:", serialize(o) == d)
