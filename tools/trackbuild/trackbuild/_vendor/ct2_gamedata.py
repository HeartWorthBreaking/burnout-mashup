"""ct2_gamedata - CUSTOM-TRACK-2: Burnout 3 (Xbox) GAMEDATA.BGD file model, deterministic writer and route-section resizer.

Layout (XD: all 36 tracks; XC: the loader state machine sub_0018B250, LAYOUT.md in this workspace):
  0x0000 .. 0x3000   header, read as 0x800 + 0x2800 (loader states 2..4):
                       +0x008 + 8k   event id pairs {u32, u32}, k < count (matched against the requested event)
                       +0x198 + 4k   event record file offset (0x3000 + 0x800 k on every retail track)
                       +0x260        u32 event count
                       +0x264..+0x274 5 u32 section starts: events, S1, S2 base, S3, S4 (informative; the loader does
                                     not read them: it seeks through each event record)
                       +0x2810 / +0x2834 / +0x2840  per-variant S1 counts / S2 sizes / S2 offsets (used when the
                                     loader flag +0x58B is set; they never describe S3 or S4)
                       every other header byte is build-tool memory carried as is
  event records      count x 0x800 at their table offsets; section references {offset, size}:
                       S1 (+0x3C0, +0x3BC)  S2 (+0x3C8, +0x3C4)  S3 (+0x3D0, +0x3CC)  S4 route (+0x3D8, +0x3D4)
  sections           S1 / S2 / S3 / S4 at those offsets, 0x800-aligned; S4 ends at the end of the file
Loader memory (XC): one buffer from pool slot 0x003FA004 (0x003FA4C4 when [0x003FA644] = 2), base [+0xC]; header
0x3000, record 0x800, then S1, S2, S3, S4 back to back (sizes from the record); no size check in the loader.
Need = 0x3800 + S1 + S2 + S3 + S4 (the largest retail need, US/M1_V1, is 0x167800).

Functions: parse / build (identity), check (references, alignment, overlap, the S4-is-last rule), resize_s4 (append
bytes to S4 and rewrite the size field of every record that refers to it).
   py -3 -B ct2_gamedata.py identity            every retail track: parse -> build byte-identical, check clean
   py -3 -B ct2_gamedata.py map TRACK           the layout map (JSON on stdout)
   py -3 -B ct2_gamedata.py negatives           malformed-offset / length / overlap controls must be rejected"""
import json
import struct
import sys
from pathlib import Path

BASE = None   # vendored copy: no retail folder (the research CLI functions are not used by trackbuild)
PAGE = 0x800
HEADER = 0x3000
RECORD = 0x800
REFS = {"S1": (0x3C0, 0x3BC), "S2": (0x3C8, 0x3C4), "S3": (0x3D0, 0x3CC), "S4": (0x3D8, 0x3D4)}
RETAIL_MAX_NEED = 0x167800          # US/M1_V1 (logs/G8_buffer_needs.txt); the pool slot holds at least this


class GamedataError(Exception):
    pass


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


class Gamedata:
    @classmethod
    def parse(cls, b):
        g = cls()
        if len(b) < HEADER or len(b) % PAGE:
            raise GamedataError("file size 0x%X: not a whole number of 0x800 pages above the header" % len(b))
        g.header = bytearray(b[:HEADER])
        g.count = u32(b, 0x260)
        if not 1 <= g.count <= 64:
            raise GamedataError("event count %d" % g.count)
        g.rec_off = [u32(b, 0x198 + 4 * k) for k in range(g.count)]
        g.records = []
        for k, o in enumerate(g.rec_off):
            if o % PAGE or o < HEADER or o + RECORD > len(b):
                raise GamedataError("event %d record offset 0x%X" % (k, o))
            g.records.append(bytearray(b[o:o + RECORD]))
        # sections: distinct {offset, size} referenced by any record
        g.sections = {}
        for k, r in enumerate(g.records):
            for name, (fo, fs) in REFS.items():
                off, size = u32(r, fo), u32(r, fs)
                if off % PAGE or size % PAGE or size == 0 or off < HEADER or off + size > len(b):
                    raise GamedataError("event %d %s {0x%X, 0x%X}: unaligned or outside the file" % (k, name, off, size))
                g.sections.setdefault((off, size), set()).add((k, name))
        g.blob = bytes(b)
        return g

    def s4(self):
        refs = {(u32(r, REFS["S4"][0]), u32(r, REFS["S4"][1])) for r in self.records}
        if len(refs) != 1:
            raise GamedataError("events refer to %d different route sections" % len(refs))
        return refs.pop()

    def build(self):
        """the file from the model: header, records at their offsets, every section's bytes from the blob"""
        out = bytearray(self.blob)
        out[:HEADER] = self.header
        for o, r in zip(self.rec_off, self.records):
            out[o:o + RECORD] = r
        return bytes(out)


def check(g):
    """rules a rewritten file must keep -> problems (empty = valid)"""
    p = []
    n = len(g.blob)
    if u32(g.header, 0x260) != g.count:
        p.append("header count changed")
    spans = sorted([(o, o + RECORD, "record %d" % k) for k, o in enumerate(g.rec_off)] +
                   [(o, o + s, "/".join(sorted({nm for _, nm in who}))) for (o, s), who in g.sections.items()])
    # records must not overlap anything; distinct sections of the same kind may overlap only if identical (shared)
    for (a0, a1, an), (b0, b1, bn) in zip(spans, spans[1:]):
        if b0 < a1 and not (an == bn and (a0, a1) == (b0, b1)) and ("record" in an or "record" in bn):
            p.append("%s 0x%X..0x%X overlaps %s 0x%X..0x%X" % (an, a0, a1, bn, b0, b1))
    try:
        o4, s4 = g.s4()
        if o4 + s4 != n:
            p.append("route section 0x%X + 0x%X does not end the file (0x%X)" % (o4, s4, n))
        for (o, s), who in g.sections.items():
            if (o, s) != (o4, s4) and o + s > o4:
                p.append("%s 0x%X..0x%X reaches into the route section" % (sorted(who)[0], o, o + s))
        if u32(g.header, 0x274) != o4:
            p.append("header section table +0x274 (0x%X) is not the route section (0x%X)" % (u32(g.header, 0x274), o4))
    except GamedataError as e:
        p.append(str(e))
    need = max(0x3800 + sum(u32(r, REFS[nm][1]) for nm in REFS) for r in g.records)
    if need > RETAIL_MAX_NEED:
        p.append("loader buffer need 0x%X above the largest retail need 0x%X" % (need, RETAIL_MAX_NEED))
    return p


def resize_s4(b, new_s4):
    """b with its route section replaced by new_s4 (any length, padded with zeros to a page multiple); every event record's
    S4 size field rewritten; nothing else changes"""
    g = Gamedata.parse(b)
    o4, s4 = g.s4()
    if o4 + s4 != len(b):
        raise GamedataError("route section is not last")
    size = len(new_s4) + (-len(new_s4)) % PAGE
    if size < s4:
        raise GamedataError("shrinking the route section is not supported")
    out = bytearray(b[:o4]) + new_s4 + bytes(size - len(new_s4))
    for o in g.rec_off:
        struct.pack_into("<I", out, o + REFS["S4"][1], size)
    g2 = Gamedata.parse(bytes(out))
    probs = check(g2)
    if probs:
        raise GamedataError("resized file invalid: %s" % probs)
    return bytes(out), {"s4_offset": o4, "s4_size_old": s4, "s4_size_new": size, "file_old": len(b), "file_new": len(out),
                        "changed_fields": [o + REFS["S4"][1] for o in g.rec_off],
                        "need_new": max(0x3800 + sum(u32(out, o + REFS[nm][1]) for nm in REFS) for o in g.rec_off)}


def layout_map(tid):
    b = (BASE / tid / "Gamedata.bgd").read_bytes()
    g = Gamedata.parse(b)
    return {"track": tid, "file_size": len(b), "event_count": g.count,
            "event_ids": [[u32(b, 8 + 8 * k), u32(b, 12 + 8 * k)] for k in range(g.count)],
            "record_offsets": g.rec_off, "header_sections": [u32(b, 0x264 + 4 * i) for i in range(5)],
            "records": [{nm: [u32(r, fo), u32(r, fs)] for nm, (fo, fs) in REFS.items()} for r in g.records],
            "sections": [{"offset": o, "size": s, "end": o + s, "users": sorted("%d:%s" % w for w in who)}
                         for (o, s), who in sorted(g.sections.items())],
            "loader_need": max(0x3800 + sum(u32(r, REFS[nm][1]) for nm in REFS) for r in g.records),
            "check": check(g)}


def identity():
    ok = bad = 0
    for p in sorted(BASE.glob("*/*/Gamedata.bgd")):
        b = p.read_bytes()
        try:
            g = Gamedata.parse(b)
            same = g.build() == b
            pr = check(g)
        except GamedataError as e:
            same, pr = False, [str(e)]
        ok += same and not pr
        bad += not (same and not pr)
        print("%-8s identical %s check %s" % (p.parent.relative_to(BASE).as_posix(), same, pr or "OK"))
    print("IDENTITY %d / %d" % (ok, ok + bad))
    return bad


def negatives(tid="US/C3_V1"):
    b = (BASE / tid / "Gamedata.bgd").read_bytes()
    g = Gamedata.parse(b)
    r0 = g.rec_off[0]
    cases = []

    def mod(fn):
        x = bytearray(b)
        fn(x)
        return bytes(x)
    cases.append(("record offset unaligned", mod(lambda x: struct.pack_into("<I", x, 0x198, 0x3004))))
    cases.append(("record offset outside the file", mod(lambda x: struct.pack_into("<I", x, 0x198, len(b)))))
    cases.append(("S4 size not a page multiple", mod(lambda x: struct.pack_into("<I", x, r0 + 0x3D4, 0x3E810))))
    cases.append(("S4 size past the end of file", mod(lambda x: struct.pack_into("<I", x, r0 + 0x3D4, 0x3F000))))
    cases.append(("S4 shorter (no longer ends the file)", mod(lambda x: struct.pack_into("<I", x, r0 + 0x3D4, 0x3E000))))
    cases.append(("events disagree on S4", mod(lambda x: struct.pack_into("<I", x, r0 + 0x3D8, 0xB0800))))
    cases.append(("S3 overlapping record 13", mod(lambda x: struct.pack_into("<I", x, r0 + 0x3D0, g.rec_off[-1]))))
    cases.append(("S2 reaching into S4", mod(lambda x: struct.pack_into("<I", x, r0 + 0x3C4, 0xA0000))))
    cases.append(("event count 0", mod(lambda x: struct.pack_into("<I", x, 0x260, 0))))
    cases.append(("file truncated by 0x10", b[:-0x10]))
    cases.append(("header +0x274 not the route section", mod(lambda x: struct.pack_into("<I", x, 0x274, 0xB0800))))
    cases.append(("buffer need above the retail maximum", resize_unchecked(b, RETAIL_MAX_NEED)))
    res = []
    for name, data in cases:
        try:
            pr = check(Gamedata.parse(data))
            rej = bool(pr)
            why = pr[:1]
        except GamedataError as e:
            rej, why = True, [str(e)]
        res.append({"case": name, "rejected": rej, "reason": why})
        print("%-4s %-40s %s" % ("PASS" if rej else "FAIL", name, why))
    return res


def resize_unchecked(b, grow):
    """negative-control helper: S4 grown by `grow` bytes with the size fields updated but no check"""
    g = Gamedata.parse(b)
    o4, s4 = g.s4()
    out = bytearray(b) + bytes(grow)
    for o in g.rec_off:
        struct.pack_into("<I", out, o + REFS["S4"][1], s4 + grow)
    return bytes(out)


if __name__ == "__main__":
    if sys.argv[1] == "identity":
        sys.exit(1 if identity() else 0)
    if sys.argv[1] == "map":
        print(json.dumps(layout_map(sys.argv[2]), indent=1))
    if sys.argv[1] == "negatives":
        r = negatives()
        sys.exit(0 if all(x["rejected"] for x in r) else 1)

