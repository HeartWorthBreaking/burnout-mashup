"""xbtopo - CUSTOM-TRACK-1 native Xbox track TOPOLOGY writer (Burnout 3 Takedown NTSC-U, STREAMED.DAT mesh + LOD blocks).

Models a block as parsed values, lets records / vertices / collision leaves be added or replaced, and re-serialises the
block from layout rules (no copied offsets). The rules are checked by `identity` on every block of every track: an
unedited model must re-serialise byte-identically (mesh 2,838 / 2,838; LOD 2,838 / 2,838 including the collision tree,
the lighting table and the prop-instance tail).

Labels: XD = verified on the retail data, SRC = read in the recompiled game code (Takedawn src/game/recomp/gen), HYP.

MESH block (B3-PC-3 MESH_FORMAT.md 1.3-1.7, XD 2,838 / 2,838):
  0x00 hdr {1, unit, size, 0} | 0x10 prism (4 x f32[4], h = +0x1C) | 0x50 VB {1, data rel +0x50, 0} | 0x5C records rel +0x50
  | 0x60 s16 count | 0x70..0xC62 rows / PVS | pad | 0xC90 records (0x90 each) | vertices (16-aligned, 28 B)
  | u16 index runs in record order, each 4-aligned | zero pad to the next 0x1000
LOD block (this tool, XD; fixups SRC sub_0019D7A0 / sub_001B02B0 / sub_0019D760):
  0x00..0x6F as mesh | 0x70 region quad A[4], 0x80 C[4], 0x90 B[4] (inside: A*x + C*z - B >= 0 on all 4 lanes; XD: every
  point in one unit, consecutive units share one negated lane 36 / 36) | 0xA0 tree (block rel) | 0xA4 lighting table (block
  rel, 0xB0) | 0xA8 u32 tail struct (rel +0xA8) | 0xAC u32 prop-instance pointer array (rel +0xA8; STATIC +0x34 entries,
  each rel +0xA8, 0 = none) | 0xB0 lighting table (9-byte records) .. tree | tree | records (16-aligned after the tree) |
  vertices | index runs | tail (at the end of the indices: [+0xA8] struct, the pointer array, 16-aligned instance records)
  Tree pointers are relative (tree +0x20 nodes, +0x24 leaves; leaf +0 quads, +4 vertices rel. the leaf: SRC sub_001B02B0),
  so the tree is re-serialised in place and everything after it moves; the tail moves by a multiple of 16 (its instance
  records are 16-aligned, read with movaps: HYP from the alignment) and [+0xA8], [+0xAC], every non-zero [+0xAC] entry follow.
Collision ray / box queries (SRC sub_001AF980): per node pair, child 0 is visited when the query reaches coord <= plane0,
  child 1 when it reaches coord >= plane1, both when it spans both: overlapping children are legal. New leaves therefore go
  under a NEW root pair {old root, new subtree} without refitting the retail tree; the header box grows to contain them.
Collision unit (data, matches the PS2 code 0x00251740 / 0x001C5080): the car's tree is the unit whose LOD region quad holds
  the car's (x, z); a new collision piece goes into the tree of every unit whose region it overlaps."""
import math
import struct
import sys
from pathlib import Path

from . import xbmesh as X  # noqa: E402   (vendored: package-relative imports)
from .bolib import collision as C  # noqa: E402

VTX = struct.Struct("<3fII2f")
NCHUNK, CHUNK = 17, 0xA9


class TopoError(Exception):
    pass


def align(x, a):
    return x + (-x) % a


def last_nonzero(b):
    k = len(b)
    while k and b[k - 1] == 0:
        k -= 1
    return k


# --------------------------------------------------------------------------------------------- vertices / normals
def pack_normal(n):
    """inverse of xbmesh.dec_normal: 11:11:10 signed, /1023, /1023, /511"""
    l = math.sqrt(sum(c * c for c in n)) or 1.0
    x, y, z = (c / l for c in n)
    xi = max(-1023, min(1023, int(round(x * 1023)))) & 0x7FF
    yi = max(-1023, min(1023, int(round(y * 1023)))) & 0x7FF
    zi = max(-511, min(511, int(round(z * 511)))) & 0x3FF
    return xi | (yi << 11) | (zi << 22)


# --------------------------------------------------------------------------------------------- strips
def _same_tri(t, u):
    return t in (u, (u[1], u[2], u[0]), (u[2], u[0], u[1]))


def decode_tris(idx):
    return X.triangles(6, idx)[0]


def stripify(tris):
    """oriented triangles -> one strip (prim 6) whose decode (standard parity, degenerates dropped; xbmesh.triangles)
    gives exactly these triangles with this orientation, each once. Greedy continuation, degenerate joins otherwise."""
    left = [tuple(t) for t in tris]
    for t in left:
        if len(set(t)) != 3:
            raise TopoError("degenerate triangle %s" % (t,))
    s = []
    while left:
        t = left.pop(0)
        if not s:
            s = list(t)
        else:
            # join with degenerates: .., x, y, y, a, a [, a], b, c -> (x y y) (y y a) (y a a) (a a b) all degenerate; the real
            # triangle (a, b, c) starts at the last a, which must be an even position (odd positions decode swapped).
            s += [s[-1], t[0], t[0]]
            if (len(s) - 1) % 2:
                s.append(t[0])
            s += [t[1], t[2]]
        grown = True
        while grown and left:
            grown = False
            i = len(s) - 2                                        # a new vertex v makes triangle at position i
            a, b = s[i], s[i + 1]
            for k, u in enumerate(left):
                for v in u:
                    cand = (b, a, v) if i % 2 else (a, b, v)
                    if len(set(cand)) == 3 and _same_tri(cand, u):
                        s.append(v)
                        left.pop(k)
                        grown = True
                        break
                if grown:
                    break
    canon = lambda t: min((t, (t[1], t[2], t[0]), (t[2], t[0], t[1])))  # noqa: E731
    if sorted(canon(g) for g in decode_tris(s)) != sorted(canon(tuple(t)) for t in tris):
        raise TopoError("strip encoding check failed")
    return s


# --------------------------------------------------------------------------------------------- MESH block model
class MeshModel:
    def __init__(self, b):
        self.orig = bytes(b)
        self.size = len(b)
        blk = X.Block(b, 0, len(b), "mesh", 0)
        self.hdr = list(blk.hdr)
        self.quad = [list(q) for q in blk.quad]
        self.vb_common, self.vb_lock = blk.vb_common, blk.vb_lock
        self.w62, self.w64, self.w68, self.w6C = blk.w62, blk.w64, blk.w68, blk.w6C
        self.pvs = b[0x70:0xC63]
        self.recs = [{"corners": [list(c) for c in m["corners"]], "prim": m["prim"], "idx": list(m["idx"]),
                      "next": m["next"], "tail": m["tail"]} for m in blk.meshes]
        self.verts = [list(v) for v in blk.verts]

    def serialize(self, size=None, grow=False):
        """size: the slot to fill (default: the minimum). grow=True: a block that no longer fits `size` takes the next page
        multiple instead of being refused (the caller re-tiles STREAMED.DAT and the STATIC unit table)."""
        n = len(self.recs)
        if n > 127:
            raise TopoError("more than 127 records (s8 chain index)")
        if len(self.verts) > 65536:
            raise TopoError("more than 65,536 vertices (u16 indices)")
        ma = 0xC90
        vb = align(ma + 0x90 * n, 16)
        pos = vb + 28 * len(self.verts)
        ips = []
        for r in self.recs:
            pos = align(pos, 4)
            ips.append(pos)
            pos += 2 * len(r["idx"])
        need = align(pos, 0x1000)
        size = size or need
        if need > size:
            if not grow:
                raise TopoError("mesh block needs 0x%X bytes, slot is 0x%X" % (need, size))
            size = need
        out = bytearray(size)
        hdr = list(self.hdr)
        hdr[2] = size
        struct.pack_into("<4I", out, 0, *hdr)
        for k, q in enumerate(self.quad):
            struct.pack_into("<4f", out, 0x10 + 16 * k, *q)
        struct.pack_into("<4I", out, 0x50, self.vb_common, vb - 0x50, self.vb_lock, ma - 0x50)
        struct.pack_into("<hH3I", out, 0x60, n, self.w62, self.w64, self.w68, self.w6C)
        out[0x70:0xC63] = self.pvs
        for i, (r, ip) in enumerate(zip(self.recs, ips)):
            o = ma + 0x90 * i
            for k, c in enumerate(r["corners"]):
                struct.pack_into("<3fI", out, o + 16 * k, *c)
            struct.pack_into("<3Ib", out, o + 0x80, r["prim"], len(r["idx"]), ip - o, r["next"])
            out[o + 0x8D:o + 0x90] = r["tail"]
            struct.pack_into("<%dH" % len(r["idx"]), out, ip, *r["idx"])
        for k, v in enumerate(self.verts):
            VTX.pack_into(out, vb + 28 * k, *v)
        return bytes(out)


# --------------------------------------------------------------------------------------------- LOD block model
class LodModel:
    def __init__(self, b, nprop):
        self.orig = bytes(b)
        self.size = len(b)
        self.nprop = nprop
        blk = X.Block(b, 0, len(b), "lod", 0)
        self.hdr = list(blk.hdr)
        self.quad = [list(q) for q in blk.quad]
        self.vb_common, self.vb_lock = blk.vb_common, blk.vb_lock
        self.w62, self.w64, self.w68, self.w6C = blk.w62, blk.w64, blk.w68, blk.w6C
        self.region = list(blk.lod_f70)
        self.tree_off, self.light_off, a8, ac = struct.unpack_from("<4I", b, 0xA0)
        if self.light_off != 0xB0 or not 0xB0 <= self.tree_off < len(b):
            raise TopoError("unexpected LOD header (+0xA4 0x%X, tree 0x%X)" % (self.light_off, self.tree_off))
        self.light = b[0xB0:self.tree_off]
        self.tree = C.parse(b, self.tree_off, "b3")
        self.tree_pn, self.tree_pl = struct.unpack_from("<II", b, self.tree_off + 0x20)
        self.tree_end = C.extent(b, self.tree_off, "b3")
        self.recs = [{"corners": [list(c) for c in m["corners"]], "prim": m["prim"], "idx": list(m["idx"]),
                      "next": m["next"], "tail": m["tail"]} for m in blk.meshes]
        self.verts = [list(v) for v in blk.verts]
        self.idx_end = max(blk.ma + 0x90 * blk.nmesh, *(m["ip"] + 2 * m["nidx"] for m in blk.meshes)) if blk.meshes else blk.vb
        self.ma0, self.vb0 = blk.ma, blk.vb
        # tail: [+0xA8] struct .. last non-zero byte; pointers relative to block + 0xA8
        self.a8, self.ac = a8, ac
        self.tail_start = 0xA8 + a8 if a8 else None
        end = last_nonzero(b)
        self.tail = b[self.tail_start:end] if a8 else b""
        self.ac_entries = list(struct.unpack_from("<%dI" % nprop, b, 0xA8 + ac)) if ac else []

    def tree_bytes(self):
        """the tree re-serialised in Burnout 3's layout (xbcoll identity writer, extended to grown trees)"""
        t = self.tree
        pn = self.tree_pn
        nodes = b"".join(struct.pack("<fHBB", plane, idx, axis, kind) for plane, _, idx, axis, kind in t.entries)
        pl = max(self.tree_pl, pn + len(nodes)) if not getattr(self, "tree_grown", False) else pn + len(nodes)
        data_at = pl + 16 * len(t.leaves)
        leaves, blob = b"", b""
        for i, lf in enumerate(t.leaves):
            quads = b"".join(lf.quads)
            quads += bytes(-len(quads) % 4)
            raw = b""
            for v in lf.verts:
                u = [int(round((v[k] - lf.cell[k] * C.CELL) / C.SCALE)) for k in range(3)]
                if not all(0 <= c <= 65535 for c in u):
                    raise TopoError("leaf %d vertex %s outside its cell %s" % (i, v, lf.cell))
                raw += struct.pack("<3H", *u)
            raw += bytes(-len(raw) % 4)
            if len(lf.quads) > 255 or len(lf.verts) > 255:
                raise TopoError("leaf %d: more than 255 quads / vertices" % i)
            here = pl + 16 * i
            pa = data_at + len(blob) - here
            leaves += struct.pack("<IIH3b3B", pa, pa + len(quads), len(quads) + len(raw), *lf.cell, 14, len(lf.quads), len(lf.verts))
            blob += quads + raw
        head = struct.pack("<3fI3fI", *t.max, t.tags[0], *t.min, t.tags[1]) + struct.pack("<IIHHI", pn, pl, len(t.leaves), len(t.entries) // 2, t.flag)
        return head + bytes(pn - 0x30) + nodes + bytes(pl - pn - len(nodes)) + leaves + blob

    def serialize(self, size=None, grow=False):
        size = size or self.size
        n = len(self.recs)
        if n > 127:
            raise TopoError("more than 127 records")
        tb = self.tree_bytes()
        ma = align(self.tree_off + len(tb), 16)
        vb = ma + 0x90 * n
        pos = vb + 28 * len(self.verts)
        ips = []
        for r in self.recs:
            pos = align(pos, 4)
            ips.append(pos)
            pos += 2 * len(r["idx"])
        idx_end = pos
        tail_at = None
        if self.tail_start is not None:
            dg = idx_end - self.idx_end
            tail_at = self.tail_start + align(dg, 16) if dg > 0 else self.tail_start + dg
            if dg < 0:                         # shrinking keeps the tail's 16-byte phase too
                tail_at = self.tail_start - ((-dg) // 16) * 16
            if tail_at < idx_end:
                raise TopoError("tail would overlap the indices")
            margin = 16 if tail_at != self.tail_start else 0          # a moved tail keeps 16 zero bytes after it
            if tail_at + len(self.tail) > size - margin:
                if not grow:
                    raise TopoError("LOD block needs 0x%X bytes (+16 margin), slot is 0x%X" % (tail_at + len(self.tail) + 16, size))
                size = align(tail_at + len(self.tail) + margin, 0x1000)
        elif idx_end > size:
            if not grow:
                raise TopoError("LOD block too small")
            size = align(idx_end, 0x1000)
        out = bytearray(size)
        hdr = list(self.hdr)
        hdr[2] = size
        struct.pack_into("<4I", out, 0, *hdr)
        for k, q in enumerate(self.quad):
            struct.pack_into("<4f", out, 0x10 + 16 * k, *q)
        struct.pack_into("<4I", out, 0x50, self.vb_common, vb - 0x50, self.vb_lock, ma - 0x50)
        struct.pack_into("<hH3I", out, 0x60, n, self.w62, self.w64, self.w68, self.w6C)
        struct.pack_into("<12f", out, 0x70, *self.region)
        d = (tail_at - self.tail_start) if tail_at is not None else 0
        a8 = self.a8 + d if self.a8 else 0
        ac = self.ac + d if self.ac else 0
        struct.pack_into("<4I", out, 0xA0, self.tree_off, self.light_off, a8, ac)
        out[0xB0:self.tree_off] = self.light
        out[self.tree_off:self.tree_off + len(tb)] = tb
        for i, (r, ip) in enumerate(zip(self.recs, ips)):
            o = ma + 0x90 * i
            for k, c in enumerate(r["corners"]):
                struct.pack_into("<3fI", out, o + 16 * k, *c)
            struct.pack_into("<3Ib", out, o + 0x80, r["prim"], len(r["idx"]), ip - o, r["next"])
            out[o + 0x8D:o + 0x90] = r["tail"]
            struct.pack_into("<%dH" % len(r["idx"]), out, ip, *r["idx"])
        for k, v in enumerate(self.verts):
            VTX.pack_into(out, vb + 28 * k, *v)
        if tail_at is not None:
            out[tail_at:tail_at + len(self.tail)] = self.tail
            if ac:
                for i, e in enumerate(self.ac_entries):
                    struct.pack_into("<I", out, 0xA8 + ac + 4 * i, e + d if e else 0)
        return bytes(out)


# --------------------------------------------------------------------------------------------- record helpers
def corners_of(pts, w_words):
    """8 box corners in the retail order (XD, corner_order()) with the retail w words kept"""
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    out = []
    for k, (sx, sy, sz) in enumerate(CORNER_ORDER):
        out.append([hi[0] if sx else lo[0], hi[1] if sy else lo[1], hi[2] if sz else lo[2], w_words[k]])
    return out


# XD (ct1_g1facts, C3_V1): the most common axis-aligned pattern (287 records; the others are rotated boxes): bottom face
# (x0 z0, x0 z1, x1 z1, x1 z0) then the top face in the same order. 1 = max, 0 = min on (x, y, z).
CORNER_ORDER = ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))


def corner_order(trk_blocks):
    """the (x, y, z) max/min pattern of the 8 corners, read from retail records (must be one pattern everywhere)"""
    pats = {}
    for blk in trk_blocks:
        for m in blk.meshes:
            cs = m["corners"]
            lo = [min(c[k] for c in cs) for k in range(3)]
            hi = [max(c[k] for c in cs) for k in range(3)]
            if any(hi[k] - lo[k] < 0.01 for k in range(3)):
                continue
            p = tuple(tuple(int(abs(c[k] - hi[k]) < abs(c[k] - lo[k])) for k in range(3)) for c in cs)
            pats[p] = pats.get(p, 0) + 1
    return pats


def add_record(model, verts, tris, host, w_words=None):
    """append one strip record with NEW vertices (positions + normal + ARGB + uv tuples) and these oriented triangles (indices
    into `verts`); link it into the material chain right after record `host` (same block), so every camera that draws the
    host draws it with the host's material. Returns the new record index."""
    if not 0 <= host < len(model.recs):
        raise TopoError("host record %d outside the block" % host)
    if model.recs[host]["prim"] != 6:
        raise TopoError("host record is not a strip record")
    base = len(model.verts)
    for v in verts:
        if len(v) != 7 or not all(math.isfinite(float(c)) for c in v[:3] + v[5:7]):
            raise TopoError("bad vertex %r" % (v,))
    strip = [base + i for i in stripify(tris)]
    model.verts += [list(v) for v in verts]
    hc = model.recs[host]["corners"]
    rec = {"corners": corners_of([v[:3] for v in verts], w_words or [c[3] for c in hc]), "prim": 6, "idx": strip,
           "next": model.recs[host]["next"], "tail": model.recs[host]["tail"]}
    model.recs.append(rec)
    k = len(model.recs) - 1
    model.recs[host]["next"] = k
    return k


def grow_prism(model, pts):
    """the unit prism must hold the new vertices: XZ inside the quad (refused otherwise), y in [y0, y0 + h] (h grown)"""
    q = model.quad
    xz = [(c[0], c[2]) for c in q]
    for p in pts:
        sgn = []
        for i in range(4):
            a, b = xz[i], xz[(i + 1) % 4]
            sgn.append((b[0] - a[0]) * (p[2] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
        if not (all(s >= -1e-3 for s in sgn) or all(s <= 1e-3 for s in sgn)):
            raise TopoError("vertex %s outside the unit prism quad" % (tuple(round(c, 2) for c in p),))
    y0 = min(c[1] for c in q)
    top = max(p[1] for p in pts)
    if min(p[1] for p in pts) < y0 - 1e-3:
        raise TopoError("vertex below the unit prism")
    if top > y0 + q[0][3]:
        q[0][3] = top - y0 + 0.01


# --------------------------------------------------------------------------------------------- collision
def leaf_cell(pts):
    cell = []
    for k in range(3):
        lo, hi = min(p[k] for p in pts), max(p[k] for p in pts)
        c = math.floor(lo / C.CELL)
        if hi - c * C.CELL >= 1000.0 - C.SCALE or not -128 <= c <= 127:
            raise TopoError("collision leaf does not fit one 1000 m cell on axis %d" % k)
        cell.append(c)
    return tuple(cell)


def quantise(pts, cell):
    return [tuple(cell[k] * C.CELL + int(round((p[k] - cell[k] * C.CELL) / C.SCALE)) * C.SCALE for k in range(3)) for p in pts]


def make_leaf(pts, quads):
    """pts: world vertices; quads: [(i0, i1, i2, i3 or 0xFF, surface, (l0, l1, l2, l3))] strip order (tris 0-1-2, 1-3-2)"""
    if not 1 <= len(pts) <= 255 or not 1 <= len(quads) <= 255:
        raise TopoError("a leaf holds 1..255 vertices and quads")
    cell = leaf_cell(pts)
    recs = []
    for q in quads:
        i = list(q[:4])
        if any(not (0 <= a < len(pts)) for a in i[:3]) or not (i[3] == 0xFF or 0 <= i[3] < len(pts)):
            raise TopoError("quad vertex index out of range")
        recs.append(struct.pack("<4BH4H", *i, q[4], *q[5]))
    return C.Leaf(cell, recs, quantise(pts, cell))


def add_leaves(model, leaves):
    """put new leaves under a new root pair {old root, new subtree}; header box grown. Overlap is legal (sub_001AF980)."""
    t = model.tree
    if not leaves:
        return
    first = len(t.leaves)
    t.leaves += leaves
    ent = [list(e) for e in t.entries]
    pairs = [ent[2 * p:2 * p + 2] for p in range(len(ent) // 2)]
    if not pairs:
        raise TopoError("tree without nodes")

    def box(idxs):
        vs = [v for i in idxs for v in t.leaves[i].verts]
        return [min(v[k] for v in vs) for k in range(3)], [max(v[k] for v in vs) for k in range(3)]

    def build(idxs):
        """-> entry (plane unused here, idx, kind) referencing a subtree over leaf indices idxs; pairs appended"""
        if len(idxs) == 1:
            return ("leaf", idxs[0])
        lo, hi = box(idxs)
        ax = max(range(3), key=lambda k: hi[k] - lo[k])
        s = sorted(idxs, key=lambda i: sum(v[ax] for v in t.leaves[i].verts) / len(t.leaves[i].verts))
        a, b = s[:len(s) // 2], s[len(s) // 2:]
        ea, eb = build(a), build(b)
        pairs.append(None)
        me = len(pairs) - 1
        pairs[me] = [entry(ea, box(a), ax, 0), entry(eb, box(b), ax, 1)]
        return ("pair", me)

    def entry(e, bx, ax, side):
        plane = bx[1][ax] if side == 0 else bx[0][ax]
        return [plane, None, e[1], ax, 0x01 if e[0] == "leaf" else 0xFF]

    new = list(range(first, len(t.leaves)))
    sub = build(new)
    old_root = pairs[0]
    pairs.append(old_root)
    old_at = len(pairs) - 1
    lo_o, hi_o = [list(t.min), list(t.max)]
    lo_n, hi_n = box(new)
    ax = max(range(3), key=lambda k: max(0.0, lo_n[k] - hi_o[k]) + max(0.0, lo_o[k] - hi_n[k]) + (0.001 if k != 1 else 0))
    pairs[0] = [[hi_o[ax], None, old_at, ax, 0xFF], entry(sub, (lo_n, hi_n), ax, 1)]
    if len(pairs) > 0xFFFF or len(t.leaves) > 0xFFFF:
        raise TopoError("tree too large")
    t.entries = [tuple(e) for p in pairs for e in p]
    t.min = tuple(min(a, b) for a, b in zip(t.min, lo_n))
    t.max = tuple(max(a, b) for a, b in zip(t.max, hi_n))
    model.tree_grown = True
    probs = C.check(t)
    if probs:
        raise TopoError("grown tree fails check: %s" % probs[0])


# --------------------------------------------------------------------------------------------- identity survey
def identity(tids=None):
    base = X.BASE
    tids = tids or sorted(p.parent.relative_to(base).as_posix() for p in base.glob("*/*/static.dat"))
    tot = {"mesh": 0, "mesh_ok": 0, "lod": 0, "lod_ok": 0}
    fails = []
    for tid in tids:
        st = X.read_ro(base / tid / "static.dat")
        smp = base / tid / "streamed.dat"
        sm = X.read_ro(smp) if smp.exists() else b""
        nprop = struct.unpack_from("<h", st, 0x34)[0]
        n = struct.unpack_from("<h", st, 0x54)[0]
        ut = struct.unpack_from("<I", st, 0x58)[0]
        for u in range(n):
            mo, lo, ms, ls = struct.unpack_from("<4I", st, ut + 16 * u)
            if not ms or not ls:
                continue
            for kind, off, size in (("mesh", mo, ms), ("lod", lo, ls)):
                b = sm[off:off + size]
                tot[kind] += 1
                try:
                    m = MeshModel(b) if kind == "mesh" else LodModel(b, nprop)
                    out = m.serialize(size)
                    ok = out == b
                except (TopoError, C.CollisionError) as e:
                    ok, out = False, repr(e)
                if ok:
                    tot[kind + "_ok"] += 1
                elif len(fails) < 12:
                    k = next((i for i in range(min(len(b), len(out))) if b[i] != out[i]), None) if isinstance(out, bytes) else out
                    fails.append((tid, u, kind, k))
        print(tid, tot)
    return tot, fails


if __name__ == "__main__":
    if sys.argv[1:2] == ["identity"]:
        tot, fails = identity(sys.argv[2:] or None)
        print("TOTAL", tot)
        for f in fails:
            print("FAIL", f)
        sys.exit(0 if tot["mesh"] == tot["mesh_ok"] and tot["lod"] == tot["lod_ok"] else 1)
