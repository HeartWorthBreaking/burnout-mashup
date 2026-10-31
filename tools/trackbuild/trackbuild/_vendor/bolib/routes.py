"""Route data in GAMEDATA.BGD: the section this project calls S4.

Layout established by comparing Burnout 3 US/C3_V1 with five Revenge files
(docs/gamedata_bgd.md). Names are descriptive guesses; the structure is
checked by `check()` on every file available.

Revenge (version word 7), 13-word header:
  0 version  1 group count  2 node count of the full-lap lines
  3 count of 0x18-byte records in chunk E (2 in every file)
  4 count of 12-byte corner records in chunk G  5 zone count (max 8)
  6 entry count of chunk F  7 ptr groups  8 ptr distances  9 ptr E
  10 ptr G  11 ptr F  12 ptr positions (0xC0)
  then 8 zone slots (float length, float, float, u32 first node) + 3 words
Burnout 3 (version word 3), 9-word header:
  0 version  1 group count  2 node count  3 corner count  4 zone count
  5 ptr groups  6 ptr distances  7 ptr corners  8 ptr positions (0xB0)
  then the same 8 zone slots + 3 words
Chunks, same content in both games:
  positions  vec4 world positions
  groups     16-byte entries (ptr A, ptr B, ptr C, u32 n | flags<<16), then
             per group A: u32 per node, B: 8 bytes per node, C: 10 bytes per node
  distances  per node (float running distance, u32)
  corners    12 bytes: u16 first/middle/last node, u16, u8 line, u8, u16
Revenge only: chunk E and chunk F (empty on the crash-junction tracks examined).
  Chunk E = CB4SliceEnvironmentStruct (name from the external review of
  2026-10-12): 0x18-byte records, +0 u32 first slice, +4..+0x13 values,
  +0x14 flags; read per AI slice at 0x0015CAD8 [code]. Every local file has
  two records, for slices 0 and 1, with identical values, so the host's
  chunk is valid for any slice count and is kept as it is.
  Chunk F = CB4AICrossoverSliceStruct; written empty by the converter.
The last word of the Revenge section table equals the file size in the
files here; the review reports files where further (detour) sections
follow, so nothing may assume it in general (tests/test_review.py).
Criterion names: this section = CB4AILanesDataStruct, S3 =
CB4TrafficLanesStruct, S2 = CB4TrafficDataStruct, zone slots = AI
checkpoints, ramp bytes = mn8ColourOccluded / mn8ColourVisible.
"""
import struct


class RouteError(Exception):
    pass


def rev_sections(bgd):
    return list(struct.unpack_from("<7I", bgd, 0x96C))


def b3_sections(bgd):
    count = struct.unpack_from("<I", bgd, 0x260)[0]
    secs = list(struct.unpack_from("<5I", bgd, 0x264))
    if not (0 < count <= 200 and secs == sorted(secs) and secs[-1] < len(bgd)):
        raise RouteError("unexpected Burnout 3 GAMEDATA.BGD header")
    return secs + [len(bgd)]


def parse(blob, game):
    """Split one S4 section into its header fields and chunks."""
    if game == "rev":
        h = struct.unpack_from("<13I", blob, 0)
        ver, ngroups, nodes, ne, ncorner, nzone, nf, o_g, o_d, o_e, o_c, o_f, o_p = h
        zone_at = 0x34
    else:
        h = struct.unpack_from("<9I", blob, 0)
        ver, ngroups, nodes, ncorner, nzone, o_g, o_d, o_c, o_p = h
        ne = nf = 0
        o_e = o_f = o_c
        zone_at = 0x24
    if ver != (7 if game == "rev" else 3):
        raise RouteError("route section version %d" % ver)
    if not (o_p == zone_at + 0x8C and o_p < o_g < o_d <= o_e <= o_f <= o_c <= len(blob)) or nzone > 8:
        raise RouteError("route section chunks out of order")
    return {"game": game, "groups": ngroups, "nodes": nodes, "corners": ncorner, "zones": nzone,
            "e_count": ne, "f_count": nf,
            "zone_slots": blob[zone_at:zone_at + 0x8C],
            "positions": blob[o_p:o_g], "group_chunk": blob[o_g:o_d], "distances": blob[o_d:o_e],
            "e": blob[o_e:o_f], "f": blob[o_f:o_c], "corner_chunk": blob[o_c:]}


def group_arrays(r, i):
    """Offsets inside the group chunk of group i's three arrays, its segment
    count and flags. The three pointers are relative to the group's OWN
    16-byte entry, not to the chunk: the game's fixup adds the entry's
    address (0x00256FC8, called per entry by 0x00257000) [code]. Read that
    way every group of every local file decodes (rung node indices inside the
    node list, segment slice indices inside the slice count); read relative
    to the chunk, 3 to 37 groups per file do not. Corrected 2026-10-12 after
    the second external review; earlier tools read them chunk-relative, which
    is right for group 0 only. The converter copies the chunk unchanged, so
    its output was never affected.
    -> (rungs, segment dimensions, segments, segment count, flags); rungs hold
    count + 1 node pairs."""
    a, b, c, n = struct.unpack_from("<4I", r["group_chunk"], 16 * i)
    return a + 16 * i, b + 16 * i, c + 16 * i, n & 0xFFFF, n >> 16


def check(r):
    """Structural checks; returns a list of problems."""
    p = []
    npos = len(r["positions"]) // 16
    g = r["group_chunk"]
    if r["groups"] * 16 > len(g):
        return ["group table overruns its chunk"]
    full = 0
    for i in range(r["groups"]):
        a, b, c, n = (x + 16 * i if k < 3 else x for k, x in enumerate(struct.unpack_from("<4I", g, 16 * i)))
        n, flags = n & 0xFFFF, n >> 16          # pointers are relative to the group's own entry (see group_arrays)
        if not (r["groups"] * 16 <= a < b < c and c + 10 * n <= len(g) and b - a >= 4 * (n + 1) and c - b >= 8 * n):
            p.append("group %d: arrays out of order or too small" % i)
            continue
        if flags & 1:
            full += 1
            if n != r["nodes"]:
                p.append("group %d: full-lap line with %d nodes, header says %d" % (i, n, r["nodes"]))
    if len(r["distances"]) < 8 * r["nodes"]:
        p.append("distance table shorter than the node count")
    else:
        d = [struct.unpack_from("<f", r["distances"], 8 * k)[0] for k in range(r["nodes"])]
        if any(y < x for x, y in zip(d, d[1:])):
            p.append("running distance decreases")
    for k in range(r["zones"]):
        ln, _, _, first = struct.unpack_from("<3fI", r["zone_slots"], 16 * k)
        if first >= max(r["nodes"], 1) or not ln >= 0:
            p.append("zone %d starts at node %d of %d" % (k, first, r["nodes"]))
    if 12 * r["corners"] > len(r["corner_chunk"]):
        p.append("corner table overruns its chunk")
    else:
        for k in range(r["corners"]):
            a, b, c = struct.unpack_from("<3H", r["corner_chunk"], 12 * k)
            if max(a, b, c) >= max(r["nodes"], 1):
                p.append("corner %d refers to node %d of %d" % (k, max(a, b, c), r["nodes"]))
                break
    if any(r["corner_chunk"][12 * r["corners"]:]):
        p.append("data after the last corner record")
    r["full_lap_lines"], r["position_count"] = full, npos
    return p


def b3_to_rev(b3_blob, host_blob, size, ramp_bytes=False):
    """Burnout 3 S4 -> Revenge S4 of exactly `size` bytes. Chunk E, which
    Burnout 3 lacks and whose meaning is unknown, is taken from the host
    file; chunk F is left empty, as on Revenge's crash-junction tracks."""
    r, host = parse(b3_blob, "b3"), parse(host_blob, "rev")
    bad = check(r)
    if bad:
        raise RouteError("Burnout 3 route data: %s" % bad[0])
    if host["e_count"] != 2 or len(host["e"]) != 0x30:
        raise RouteError("host route data has an unexpected chunk E")

    def pad(x):
        return x + bytes(-len(x) % 16)
    pos, grp = pad(r["positions"]), pad(r["group_chunk"])
    dist = pad(r["distances"])
    corners = pad(r["corner_chunk"][:12 * r["corners"]] + bytes(12))
    o_p = 0xC0
    o_g = o_p + len(pos)
    o_d = o_g + len(grp)
    o_e = o_d + len(dist)
    o_f = o_e + len(host["e"])
    o_c = o_f
    out = struct.pack("<13I", 7, r["groups"], r["nodes"], 2, r["corners"], r["zones"], 0,
                      o_g, o_d, o_e, o_c, o_f, o_p)
    zones = bytearray(r["zone_slots"])
    if ramp_bytes:
        # Revenge 0x13CBB8 reads the bytes at section +0xB4 / +0xB5 (the first two
        # bytes after the eight zone slots) as the ends of a 256-step ramp. Every
        # Revenge file examined has 0x80, 0x80; Burnout 3 has 0, 0 there.
        zones[0x80:0x82] = host["zone_slots"][0x80:0x82] if ramp_bytes is True else bytes(ramp_bytes)
    out += bytes(zones) + pos + grp + dist + host["e"] + corners
    if len(out) > size:
        raise RouteError("converted route data (%d bytes) does not fit the host's section (%d)" % (len(out), size))
    out += bytes(size - len(out))
    chk = parse(out, "rev")
    bad = check(chk)
    if bad:
        raise RouteError("converted route data: %s" % bad[0])
    if chk["f_count"] != 0 or chk["e"] != host["e"]:
        raise RouteError("chunk E / F not as intended")
    for k in ("positions", "group_chunk", "distances"):
        if chk[k].rstrip(b"\0") != r[k].rstrip(b"\0"):
            raise RouteError("chunk %s changed during conversion" % k)
    return out, {"groups": r["groups"], "nodes": r["nodes"], "zones": r["zones"], "corners": r["corners"],
                 "full_lap_lines": r["full_lap_lines"], "positions": r["position_count"],
                 "lap_length": round(struct.unpack_from("<f", r["distances"], 8 * (r["nodes"] - 1))[0], 1),
                 "bytes_used": len(out.rstrip(b"\0")), "section_size": size}


def patch_routes(host_bgd, b3_bgd, ramp_bytes=False):
    """Replace the host's S4 with the Burnout 3 track's, in place."""
    hs, bs = rev_sections(host_bgd), b3_sections(b3_bgd)
    h4, h5 = hs[4], hs[5]
    blob, rep = b3_to_rev(b3_bgd[bs[4]:bs[5]], host_bgd[h4:h5], h5 - h4, ramp_bytes)
    rep["ramp_bytes"] = blob[0xB4:0xB6].hex()
    return host_bgd[:h4] + blob + host_bgd[h5:], rep


def append_routes(host_bgd, b3_bgd, ramp_bytes=False):
    """Append the converted Burnout 3 route section to the end of a Revenge
    GAMEDATA.BGD and point every event record that used the host's section
    at it (size at record +0x3D0, offset at +0x3D4). For tracks whose route
    data is larger than the template's section. The loader takes both words
    from the event record [code 0x002C59D0..0x002C5A64], the same mechanism
    that is verified in PCSX2 for an appended lane network and traffic set
    (docs/gamedata_loader.md). An appended ROUTE section has not been run in
    the game. The host's own section stays in the file, unused."""
    hs, bs = rev_sections(host_bgd), b3_sections(b3_bgd)
    h4, h5 = hs[4], hs[5]
    src = b3_bgd[bs[4]:bs[5]]
    probe, rep = b3_to_rev(src, host_bgd[h4:h5], len(src) + 0x10000, ramp_bytes)
    size = (rep["bytes_used"] + 0x7FF) & ~0x7FF
    blob, rep = b3_to_rev(src, host_bgd[h4:h5], size, ramp_bytes)
    out = bytearray(host_bgd)
    out += bytes(-len(out) % 0x800)
    at = len(out)
    out += blob
    count = struct.unpack_from("<I", host_bgd, 0x968)[0]
    moved = []
    for i in range(count):
        rec = struct.unpack_from("<I", host_bgd, 0x648 + 4 * i)[0]
        old_size, old_at = struct.unpack_from("<II", host_bgd, rec + 0x3D0)
        if old_at == h4 and old_size:
            struct.pack_into("<II", out, rec + 0x3D0, size, at)
            moved.append(i)
    if not moved:
        raise RouteError("no event record uses the host's route section")
    rep.update({"ramp_bytes": blob[0xB4:0xB6].hex(), "mode": "appended", "offset": at, "section_size": size,
                "events_repointed": moved, "file_growth": len(out) - len(host_bgd)})
    return bytes(out), rep


def event_data_bytes(bgd):
    """Bytes each event of a Revenge GAMEDATA.BGD puts into the game's event
    data pool: header 0x1000 + single-race block 0x2800 + record 0x800 +
    layout + traffic set + lane network + route section, read back to back
    [code 0x002C5468; measured: US/L2_V2 T1USL220TFLR fills exactly 913,408
    bytes of the pool in a save state]. S5 is not loaded into this pool.
    -> {record number: bytes}."""
    out = {}
    count = struct.unpack_from("<I", bgd, 0x968)[0]
    for i in range(count):
        rec = struct.unpack_from("<I", bgd, 0x648 + 4 * i)[0]
        lay, _, st, _, s3, _, s4, _ = struct.unpack_from("<8I", bgd, rec + 0x3B8)
        out[i] = 0x1000 + 0x2800 + 0x800 + lay + st + (s3 if st else 0) + s4
    return out

