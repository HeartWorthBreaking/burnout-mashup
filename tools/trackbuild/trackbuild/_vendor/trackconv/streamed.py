"""trackconv.streamed - Revenge (Xbox) streamed.dat -> Burnout 3 (Xbox) layout, and back (derived from
motorcity\\mc1\\mc1_convert.py = whitemountain\\wm1\\wm1_convert.py + the MC-1 extensions; functions copied, track
constants removed; DERIVATION.json records the source hashes).

MESH block (Rev -> B3): 0x00..0x6F copied; +0x54 VB data -= 0x10; +0x5C records 0xC50 -> 0xC40; B3 0x70 = 0, B3 0x71..0x7F =
Rev 0x70..0x7E; Rev 0x12A..0x13F (22 B constant) dropped; PVS 17 x 0xA9 moved 0x140 -> 0x12A; records / vertices / indices
copied from Rev 0xCA0 to B3 0xC90; the Revenge mesh object list (Rev +0xC90 header, 12-B records + 64-B matrices) DROPPED.
LOD block: lighting table 0xC0 -> 0xB0, Rev +0xB0 emitter pointer dropped, collision tree 12-B nodes -> 8-B nodes (the
'outer' float dropped), tag 0x0041CB14 -> 0x00417831, the emitter list(s) at the tree end DROPPED, LOD tail copied.
Every rule is strict (need()): a block that does not follow it is refused, never guessed."""
import hashlib
import struct

from .common import TCError, al, lastnz, need, u32, s16
from ..bolib import collision as _bolib_collision   # vendored: no trackconv.deps (workspace)

REV_TAG, B3_TAG = 0x0041CB14, 0x00417831
REV_CONST22 = b"\x00" + b"\xFF" * 8 + b"\x00" * 13
NCHUNK, CHUNK = 17, 0xA9
B3_REC, REV_REC = 0xC90, 0xCA0
B3_PVS, REV_PVS = 0x12A, 0x140
MESH_SLOT, LOD_SLOT = 0x28000, 0x18000      # retail streaming pool layout 1: 10 x 0x28000 / 18 x 0x18000
MOBJ_HDR = 0xC90                            # Revenge mesh-block object list header


def K():
    return _bolib_collision


# ----------------------------------------------------------------------------------------------- unit tables
def units(static, game):
    """[(mesh off, lod off, mesh size, lod size)]; Revenge: +0x58 count / +0x5C table, B3: +0x54 / +0x58"""
    n, ut = (s16(static, 0x58), u32(static, 0x5C)) if game == "rev" else (s16(static, 0x54), u32(static, 0x58))
    return [struct.unpack_from("<4I", static, ut + 16 * i) for i in range(n)]


def nprop_of(static):
    return s16(static, 0x34)        # instance-model count (LOD tail arrays); same field in both games


# ----------------------------------------------------------------------------------------------- shared span helpers
def records_span(b):
    """(ma, vb, nrec, idx_end) of the records / vertices / index runs of a block"""
    n = s16(b, 0x60)
    need(n > 0, "block without records")
    ma, vb = 0x50 + u32(b, 0x5C), 0x50 + u32(b, 0x54)
    need(vb == al(ma + 0x90 * n, 16), "vertices not at align16(records end)")
    end = vb
    for i in range(n):
        r = ma + 0x90 * i
        prim, cnt, rel = struct.unpack_from("<3I", b, r + 0x80)
        end = max(end, r + rel + 2 * cnt)
        need(r + rel >= vb, "index run before the vertex buffer")
    return ma, vb, n, end


def tail_parts(b, idx_end, nprop):
    """LOD tail -> (per-instance bytes, entries rel to blob start or None, blob)"""
    a8, ac = u32(b, 0xA8), u32(b, 0xAC)
    need(a8 and ac, "LOD block without a tail")
    need(0xA8 + a8 == idx_end, "tail not at the end of the indices")
    arr = 0xA8 + ac
    need(arr == al(idx_end + nprop, 4), "pointer array not at align4(tail + nprop)")
    need(not any(b[idx_end + nprop:arr]), "non-zero pad before the pointer array")
    ents = struct.unpack_from("<%dI" % nprop, b, arr)
    blob0 = al(arr + 4 * nprop, 16)
    need(not any(b[arr + 4 * nprop:blob0]), "non-zero pad before the instance records")
    end = max(lastnz(b), blob0)
    rel = []
    for e in ents:
        if e:
            need(blob0 <= 0xA8 + e < end, "instance pointer outside the instance area")
            rel.append(0xA8 + e - blob0)
        else:
            rel.append(None)
    return b[idx_end:idx_end + nprop], rel, b[blob0:end]


def put_tail(out, at, bytes_, rel, blob):
    nprop = len(rel)
    arr = al(at + nprop, 4)
    blob0 = al(arr + 4 * nprop, 16)
    end = blob0 + len(blob)
    if len(out) < end:
        out.extend(bytes(end - len(out)))
    out[at:at + nprop] = bytes_
    struct.pack_into("<II", out, 0xA8, at - 0xA8, arr - 0xA8)
    for i, r in enumerate(rel):
        struct.pack_into("<I", out, arr + 4 * i, 0 if r is None else blob0 + r - 0xA8)
    out[blob0:end] = blob
    return end


def finish(out, struct_end=0):
    size = al(max(lastnz(out), struct_end, 1), 0x1000)
    out = bytearray(bytes(out[:size]).ljust(size, b"\0"))
    struct.pack_into("<I", out, 0x08, size)
    return bytes(out)


def max_light_index(t):
    return max((max(struct.unpack_from("<4H", q, 6)[:3 if q[3] == 0xFF else 4]) for lf in t.leaves for q in lf.quads), default=-1)


# ----------------------------------------------------------------------------------------------- MESH
def rev_mesh_objects(r, end):
    """Rev mesh +0xC90 {0, A, B, N}: N x 12-B records at A = align4(last index byte), N x 64-B matrices at B; dropped."""
    w0, a, b, n = struct.unpack_from("<4I", r, MOBJ_HDR)
    if not (w0 or a or b or n):
        need(not any(r[end:]), "Rev mesh: non-zero bytes after the last index run")
        return 0, b""
    need(w0 == 0 and n > 0, "Rev mesh object list header +0xC90 / +0xC9C")
    need(a == al(end, 4) and not any(r[end:a]), "Rev mesh object records not at align4(last index byte)")
    need(b == al(a + 12 * n, 16) and not any(r[a + 12 * n:b]), "Rev mesh object matrices not at align16(records end)")
    e = b + 64 * n
    need(e <= len(r) and not any(r[e:]), "Rev mesh: non-zero bytes after the object matrices")
    return n, r[a:e]


def rev_mesh_to_b3(r, info=None):
    need(u32(r, 0x5C) == REV_REC - 0x50, "Rev mesh records not at 0xCA0")
    need(r[0x7F] == 0, "Rev mesh +0x7F not 0")
    need(r[0x12A:0x140] == REV_CONST22, "Rev-only 22 bytes at +0x12A are not the known constant")
    need(not any(r[REV_PVS + NCHUNK * CHUNK:MOBJ_HDR]), "Rev mesh pad after the PVS not zero")
    ma, vb, n, end = records_span(r)
    nobj, objs = rev_mesh_objects(r, end)
    if info is not None:
        info.update(mesh_objects=nobj, mesh_objects_bytes=len(objs),
                    mesh_objects_sha256=hashlib.sha256(objs).hexdigest() if nobj else None)
    out = bytearray(B3_REC)
    out[0:0x70] = r[0:0x70]
    out[0x70] = 0
    out[0x71:0x80] = r[0x70:0x7F]
    out[0x80:B3_PVS] = r[0x80:0x12A]
    out[B3_PVS:B3_PVS + NCHUNK * CHUNK] = r[REV_PVS:REV_PVS + NCHUNK * CHUNK]
    out += r[REV_REC:end]
    struct.pack_into("<I", out, 0x54, u32(r, 0x54) - (REV_REC - B3_REC))
    struct.pack_into("<I", out, 0x5C, B3_REC - 0x50)
    return finish(out)


def b3_mesh_to_rev(b):
    need(u32(b, 0x5C) == B3_REC - 0x50, "B3 mesh records not at 0xC90")
    need(b[0x70] == 0, "B3 mesh +0x70 not 0 (no Revenge slot for it)")
    need(not any(b[B3_PVS + NCHUNK * CHUNK:B3_REC]), "B3 mesh pad after the PVS not zero")
    ma, vb, n, end = records_span(b)
    need(not any(b[end:]), "B3 mesh: non-zero bytes after the last index run")
    out = bytearray(REV_REC)
    out[0:0x70] = b[0:0x70]
    out[0x70:0x7F] = b[0x71:0x80]
    out[0x7F] = 0
    out[0x80:0x12A] = b[0x80:B3_PVS]
    out[0x12A:0x140] = REV_CONST22
    out[REV_PVS:REV_PVS + NCHUNK * CHUNK] = b[B3_PVS:B3_PVS + NCHUNK * CHUNK]
    out += b[B3_REC:end]
    struct.pack_into("<I", out, 0x54, u32(b, 0x54) + (REV_REC - B3_REC))
    struct.pack_into("<I", out, 0x5C, REV_REC - 0x50)
    return finish(out)


# ----------------------------------------------------------------------------------------------- LOD
def _tree_common(b, tree, game):
    k = K()
    t = k.parse(b, tree, game)
    nsize = 8 if game == "b3" else 12
    pn, pl, nleaf, nint = struct.unpack_from("<IIHH", b, tree + 0x20)
    need(pn == 0x30 and pl == 0x30 + nsize * 2 * nint, "tree node / leaf pointers not in the packed layout")
    data0 = pl + 16 * nleaf
    ext = k.extent(b, tree, game)
    for i in range(nleaf):
        o = tree + pl + 16 * i
        pa, pb = struct.unpack_from("<II", b, o)
        need(o + pa >= tree + data0 and o + pb >= tree + data0, "leaf data inside the leaf table")
    return t, pl, nleaf, ext


def rev_lod_to_b3(r, nprop):
    """-> (B3 LOD block bytes, info dict)"""
    tree, light, a8, ac, b0 = struct.unpack_from("<5I", r, 0xA0)
    need(light == 0xC0, "Rev lighting table not at 0xC0")
    need(not any(r[0xB4:0xC0]), "Rev LOD 0xB4..0xBF not zero")
    t, pl, nleaf, ext = _tree_common(r, tree, "rev")
    need(t.tags == (REV_TAG, REV_TAG), "unexpected Rev tree tags")
    llen = 9 * (max_light_index(t) + 1)
    need(tree == al(0xC0 + llen, 16) and not any(r[0xC0 + llen:tree]), "Rev lighting table length / pad rule")
    need(b0 == ext, "Rev emitter list not at the tree end")
    need(not any(r[b0:b0 + 0x10]), "Rev emitter header words not zero")
    eoff, ecnt = struct.unpack_from("<II", r, b0 + 0x10)
    if ecnt:
        e0 = b0 + 0x10 + eoff
        need(e0 == al(b0 + 0x20, 16) and not any(r[b0 + 0x20:e0]), "Rev emitter records not at align16(header end)")
        eend = e0 + 0x30 * ecnt
    else:
        need(eoff == 0, "Rev empty emitter list with an offset")
        e0 = eend = al(b0 + 0x20, 16)
    emitters = r[e0:eend]
    off2, cnt2 = struct.unpack_from("<II", r, b0 + 0x18)
    if cnt2:
        need(b0 + 0x18 + off2 == eend, "Rev second emitter list not right after the first")
        eend2 = eend + 0x30 * cnt2
    else:
        need(off2 == 0, "Rev empty second emitter list with an offset")
        eend2 = eend
    emitters2 = r[eend:eend2]
    ma, vb, n, idx_end = records_span(r)
    need(ma == eend2, "Rev LOD records not right after the emitter list(s)")
    tb, tr, blob = tail_parts(r, idx_end, nprop)
    out = bytearray(r[0:0xA0])
    out += bytes(0x10)
    out += r[0xC0:0xC0 + llen]
    tree_b = al(len(out), 16)
    out += bytes(tree_b - len(out))
    head = bytearray(r[tree:tree + 0x30])
    struct.pack_into("<I", head, 0x0C, B3_TAG)
    struct.pack_into("<I", head, 0x1C, B3_TAG)
    nent = len(t.entries)
    struct.pack_into("<II", head, 0x20, 0x30, 0x30 + 8 * nent)
    nodes = b"".join(r[tree + 0x30 + 12 * i:tree + 0x30 + 12 * i + 4] + r[tree + 0x30 + 12 * i + 8:tree + 0x30 + 12 * i + 12]
                     for i in range(nent))
    leafdata = r[tree + pl:ext]
    out += head + nodes + leafdata
    ma_b = al(len(out), 16)
    out += bytes(ma_b - len(out))
    out += r[ma:idx_end]
    struct.pack_into("<4I", out, 0xA0, tree_b, 0xB0, 0, 0)
    struct.pack_into("<I", out, 0x54, vb - ma + ma_b - 0x50)
    struct.pack_into("<I", out, 0x5C, ma_b - 0x50)
    tend = put_tail(out, ma_b + (idx_end - ma), tb, tr, blob)
    info = {"emitters": ecnt, "emitter_bytes_sha256": hashlib.sha256(emitters).hexdigest() if ecnt else None,
            "emitters2": cnt2, "emitter2_bytes_sha256": hashlib.sha256(emitters2).hexdigest() if cnt2 else None,
            "outer_floats_dropped": nent}
    return finish(out, tend), info


def b3_lod_to_rev(b, nprop):
    tree, light, a8, ac = struct.unpack_from("<4I", b, 0xA0)
    need(light == 0xB0, "B3 lighting table not at 0xB0")
    t, pl, nleaf, ext = _tree_common(b, tree, "b3")
    need(t.tags == (B3_TAG, B3_TAG), "unexpected B3 tree tags")
    llen = 9 * (max_light_index(t) + 1)
    need(tree == al(0xB0 + llen, 16) and not any(b[0xB0 + llen:tree]), "B3 lighting table length / pad rule")
    ma, vb, n, idx_end = records_span(b)
    need(ma == al(ext, 16) and not any(b[ext:ma]), "B3 LOD records not at align16(tree end)")
    tb, tr, blob = tail_parts(b, idx_end, nprop)
    sub = K()._subtree_bounds(t)
    out = bytearray(b[0:0xA0])
    out += bytes(0x20)
    out += b[0xB0:0xB0 + llen]
    tree_r = al(len(out), 16)
    out += bytes(tree_r - len(out))
    head = bytearray(b[tree:tree + 0x30])
    struct.pack_into("<I", head, 0x0C, REV_TAG)
    struct.pack_into("<I", head, 0x1C, REV_TAG)
    nent = len(t.entries)
    struct.pack_into("<II", head, 0x20, 0x30, 0x30 + 12 * nent)
    nodes = b""
    for i, (plane, _, idx, axis, kind) in enumerate(t.entries):
        lo, hi = sub[i]
        outer = lo[axis] if i % 2 == 0 else hi[axis]
        raw = b[tree + 0x30 + 8 * i:tree + 0x30 + 8 * i + 8]
        nodes += raw[0:4] + struct.pack("<f", outer) + raw[4:8]
    out += head + nodes + b[tree + pl:ext]
    b0 = len(out)
    out += bytes(0x20)
    ma_r = al(len(out), 16)
    out += bytes(ma_r - len(out))
    out += b[ma:idx_end]
    struct.pack_into("<5I", out, 0xA0, tree_r, 0xC0, 0, 0, b0)
    struct.pack_into("<I", out, 0x54, vb - ma + ma_r - 0x50)
    struct.pack_into("<I", out, 0x5C, ma_r - 0x50)
    tend = put_tail(out, ma_r + (idx_end - ma), tb, tr, blob)
    return finish(out, tend)


# ----------------------------------------------------------------------------------------------- track
def convert_track(static, streamed):
    """Revenge static + streamed -> (B3 streamed.dat bytes, B3 unit table bytes, per-unit info list)"""
    U = units(static, "rev")
    nprop = nprop_of(static)
    pos = 0
    for so, lo, ss, ls in U:
        need(so == pos and lo == so + ss, "Rev streamed.dat not tiled mesh, LOD, mesh, ...")
        pos = lo + ls
    need(pos == len(streamed), "Rev unit table does not cover streamed.dat")
    parts, table, info, pos = [], [], [], 0
    for u, (so, lo, ss, ls) in enumerate(U):
        mi = {}
        m = rev_mesh_to_b3(streamed[so:so + ss], mi)
        l, li = rev_lod_to_b3(streamed[lo:lo + ls], nprop)
        li = dict(li, **mi)
        table.append((pos, pos + len(m), len(m), len(l)))
        pos += len(m) + len(l)
        parts += [m, l]
        info.append(dict(unit=u, rev_mesh_size=ss, rev_lod_size=ls, mesh_size=len(m), lod_size=len(l), **li))
    ut = b"".join(struct.pack("<4I", *e) for e in table)
    return b"".join(parts), ut, info


def slot_report(info):
    """budget check of a converted track: the mesh slot has no capacity option; the LOD slot can grow (low_unit_bytes)"""
    mm = max(i["mesh_size"] for i in info)
    ml = max(i["lod_size"] for i in info)
    return {"max_mesh": mm, "max_lod": ml, "mesh_ok": mm <= MESH_SLOT, "lod_ok": ml <= LOD_SLOT,
            "mesh_margin": MESH_SLOT - mm, "lod_margin": LOD_SLOT - ml,
            "emitters_dropped": sum(i["emitters"] for i in info), "emitters2_dropped": sum(i["emitters2"] for i in info),
            "mesh_objects_dropped": sum(i["mesh_objects"] for i in info)}


__all__ = ["TCError", "convert_track", "units", "nprop_of", "rev_mesh_to_b3", "b3_mesh_to_rev", "rev_lod_to_b3", "b3_lod_to_rev",
           "records_span", "slot_report"]
