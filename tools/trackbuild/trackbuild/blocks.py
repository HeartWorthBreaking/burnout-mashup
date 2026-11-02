"""trackbuild.blocks - writers for the B3 Xbox streamed.dat unit blocks (mesh = full detail render; LOD = low detail render +
region quad + collision tree + lighting table + prop tail) and the per-block PVS / material rows.

Layout rules (KB MESH_AND_COLLISION s1-s2, xbtopo.py identity 2,838 / 2,838; strict rules of trackconv.streamed):
  MESH  0x00 {1, unit, size, 0} | 0x10 prism 4 x {x, y, z, w} (y = floor, corner 0 w = height) | 0x50 VB {1, vb - 0x50, 0,
        records - 0x50} | 0x60 s16 record count, 0x62..0x6F 0 | 0x70 u8 0, 0x71 s8 rows, 0x72 u8 rows, 0x73 s8 first-pass
        rows, 0x74 s8[8] backdrop groups (-1), 0x7C u8 0, 0x7D s8 chevron set index (-1 = none; 0.2.1), 0x7E/0x7F s8 backdrop pair (-1), 0x80 f32 0, 0x84 s16[83] material
        per row | 0x12A 17 PVS chunks x 0xA9 {s8 rel, u8 flag, u8 0, s8 rowsA[83], s8 rowsB[83]} (order 0, -1..-8, +1..+8)
        | 0xC90 records 0x90 {8 x (f32 x, y, z, u32 w), u32 prim 6, u32 index count, u32 index offset rel record, s8 next, FF FF
        FF} | vertices (28 B) | u16 index runs, each 4-aligned | zero pad to 0x1000
  LOD   0x00..0x6F as mesh | 0x70 region A[4], C[4], B[4] | 0xA0 tree, 0xA4 0xB0, 0xA8 tail rel +0xA8, 0xAC pointer array rel
        +0xA8 | 0xB0 lighting table (9-B records) | tree at align16 | records at align16(tree end) | vertices | index runs |
        tail: u8[nprop], pad 4, u32[nprop], 16-aligned instance records (nprop = 0 here: no instance models)
  Collision tree (bolib.collision 'b3'): header 0x30 {max, tag 0x00417831, min, tag, nodes 0x30, leaves, u16 leaves, u16 pairs,
        u32 1}; node pairs 8 B {f32 plane, u16 index, u8 axis, u8 kind 0xFF pair / 0x01 leaf}; leaves 16 B; per leaf quads 14 B
        {4 x u8 vertex (strip order, tris 0-1-2 and 1-3-2; 0xFF = triangle), u16 surface word, 4 x u16 lighting index} padded
        to 4, then vertices 3 x u16 (cell * 500 + q * 1000 / 65536) padded to 4.
Values without a known reader that retail always carries are written as the retail constant and listed in RETAIL_CONSTANTS."""
import math
import struct

from .io import need

NROWS, NCHUNK, CHUNK = 83, 17, 0xA9
CHEVRON_NONE = -1                                   # mesh +0x7D: no chevron set entry (trackbuild writes no chevron set)
REC0 = 0xC90
B3_TAG = 0x00417831
CELL, SCALE = 500.0, 1000.0 / 65536.0
CORNER_ORDER = ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))
# retail constants without a known reader (XD: retail_facts.py on US/C3_V1, EU/M1_V1, AS/C2_V1)
CORNER_W = (0x0012BFF4,) + (0xDEFE2650,) * 7      # 3,319 / 9,835 records: corner 0 0x12BFF4, others one repeated word
REC_TAIL = b"\xff\xff\xff"                          # 9,835 / 9,835
LIGHT_RECORD = bytes.fromhex("102912fdf92315fbed")  # one retail lighting record (US/C3_V1 unit 5 record 8); meaning undecoded
RETAIL_CONSTANTS = {"record corner w words": [hex(x) for x in CORNER_W], "record tail": REC_TAIL.hex(),
                    "lighting record (all collision corners)": LIGHT_RECORD.hex(), "tree tag": hex(B3_TAG), "tree flag": 1}
PVS_ORDER = [0] + [-k for k in range(1, 9)] + [k for k in range(1, 9)]
NEAR = 4


def al(x, a):
    return x + (-x) % a


def pack_normal(n):
    l = math.sqrt(sum(c * c for c in n)) or 1.0
    x, y, z = (c / l for c in n)
    xi = max(-1023, min(1023, int(round(x * 1023)))) & 0x7FF
    yi = max(-1023, min(1023, int(round(y * 1023)))) & 0x7FF
    zi = max(-511, min(511, int(round(z * 511)))) & 0x3FF
    return xi | (yi << 11) | (zi << 22)


def argb(rgb, a=255):
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in rgb)
    return (a << 24) | (r << 16) | (g << 8) | b


def strip_of(tris):
    """triangles (index triples, already wound) -> one strip whose standard-parity decode gives exactly these triangles
    (each joined by degenerates; KB: 'degenerates y, a, a (+1 a for parity)')"""
    s = []
    for t in tris:
        if not s:
            s = list(t)
            continue
        s += [s[-1], t[0], t[0]]
        if (len(s) - 1) % 2:
            s.append(t[0])
        s += [t[1], t[2]]
    return s


def decode_strip(s):
    out = []
    for i in range(len(s) - 2):
        a, b, c = s[i], s[i + 1], s[i + 2]
        if a == b or b == c or a == c:
            continue
        out.append((b, a, c) if i & 1 else (a, b, c))
    return out


class BlockGeom:
    """one unit's render geometry: vertices + one record (strip) per material row present"""

    def __init__(self, polys, rows):
        self.verts, vi = [], {}
        per = {}
        self.dropped_slivers, self.dropped_area = 0, 0.0
        for mat, poly in polys:
            ids = []
            for pos, uv, nrm, rgb in poly:
                key = (tuple(round(c, 4) for c in pos), tuple(round(c, 5) for c in uv), pack_normal(nrm), argb(rgb))
                if key not in vi:
                    vi[key] = len(self.verts)
                    self.verts.append(key)
                ids.append(vi[key])
            for a, b, c in [(0, i, i + 1) for i in range(1, len(poly) - 1)]:
                t = (ids[a], ids[b], ids[c])
                pa, pb, pc = (self.verts[i][0] for i in t)
                e1 = [pb[k] - pa[k] for k in range(3)]
                e2 = [pc[k] - pa[k] for k in range(3)]
                cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                nv = poly[a][2]
                good = len(set(t)) == 3 and sum(x * x for x in cr) > 1e-4 and sum(x * y for x, y in zip(cr, nv)) > 0
                if not good:                      # slivers (< 0.005 m2) / rounding-flipped slivers of clip pieces: dropped
                    self.dropped_slivers += 1
                    self.dropped_area += 0.5 * sum(x * x for x in cr) ** 0.5
                    continue
                if True:
                    per.setdefault(mat, []).append(t)
        # compact: keep only vertices some triangle uses (sliver triangles of clipped pieces are dropped above)
        used = sorted({i for ts in per.values() for t in ts for i in t})
        remap = {o: n_ for n_, o in enumerate(used)}
        self.verts = [self.verts[o] for o in used]
        per = {m: [tuple(remap[i] for i in t) for t in ts] for m, ts in per.items()}
        need(len(self.verts) <= 65536, "more than 65,536 vertices in one block")
        self.recs = []                       # (row index, material, strip, bbox)
        for r, mat in enumerate(rows):
            if mat in per:
                s = strip_of(per[mat])
                need(sorted(decode_strip(s)) == sorted(per[mat]), "strip encoding check failed")
                pts = [self.verts[i][0] for i in set(s)]
                lo = [min(p[k] for p in pts) for k in range(3)]
                hi = [max(p[k] for p in pts) for k in range(3)]
                self.recs.append((r, mat, s, (lo, hi)))
        if len(self.recs) > 127:                                  # 0.3.4: the message names the host patch 132 figure
            from .capacity import records_note
            need(False, records_note(len(self.recs)))
        need(1 <= len(self.recs) <= 127, "a block needs 1..127 records")
        self.row_rec = {r: i for i, (r, _, _, _) in enumerate(self.recs)}

    def records_bytes(self, base):
        """-> (records + vertices + index runs placed at `base` (= the record array offset), end offset)"""
        n = len(self.recs)
        vb = al(base + 0x90 * n, 16)
        pos = vb + 28 * len(self.verts)
        out = bytearray(pos - base)
        ips = []
        for _, _, s, _ in self.recs:
            pos = al(pos, 4)
            ips.append(pos)
            pos += 2 * len(s)
        out.extend(bytes(pos - base - len(out)))
        for i, ((_, _, s, (lo, hi)), ip) in enumerate(zip(self.recs, ips)):
            o = 0x90 * i
            for k, (sx, sy, sz) in enumerate(CORNER_ORDER):
                struct.pack_into("<3fI", out, o + 16 * k, hi[0] if sx else lo[0], hi[1] if sy else lo[1], hi[2] if sz else lo[2], CORNER_W[k])
            struct.pack_into("<3Ib", out, o + 0x80, 6, len(s), ip - (base + o), -1)
            out[o + 0x8D:o + 0x90] = REC_TAIL
            struct.pack_into("<%dH" % len(s), out, ip - base, *s)
        for k, (p, uv, nrm, col) in enumerate(self.verts):
            struct.pack_into("<3fII2f", out, vb - base + 28 * k, p[0], p[1], p[2], nrm, col, uv[0], uv[1])
        return bytes(out), vb - 0x50, base + len(out)


def header(unit, prism):
    h = bytearray(0x70)
    struct.pack_into("<4I", h, 0, 1, unit, 0, 0)
    for k, q in enumerate(prism):
        struct.pack_into("<4f", h, 0x10 + 16 * k, *q)
    return h


def prism_of(unit, geom_y):
    y0, y1 = geom_y
    return [(c[0], y0, c[1], (y1 - y0 + 0.5) if k == 0 else 0.0) for k, c in enumerate(unit.corners)]


def mesh_block(unit_index, prism, geom, rows, pvs, first_pass=None):
    """first_pass (0.3.2): rows before it are drawn in the first pass, the rest (blended retail materials) after it (+0x73;
    retail survey: every row after +0x73 has material bit 0x01). None = every row (0.3.1 bytes)."""
    out = header(unit_index, prism)
    out += bytes(REC0 - len(out))
    recs, vb_rel, end = geom.records_bytes(REC0)
    struct.pack_into("<4I", out, 0x50, 1, vb_rel, 0, REC0 - 0x50)
    struct.pack_into("<h", out, 0x60, len(geom.recs))
    nr = len(rows)
    out[0x70] = 0
    fp = nr if first_pass is None else first_pass
    need(0 <= fp <= nr, "first-pass row count %d outside 0..%d" % (fp, nr))
    struct.pack_into("<bBb", out, 0x71, nr, nr, fp)
    struct.pack_into("<8b", out, 0x74, *([-1] * 8))
    # 0x7C u8 0, 0x7D s8 chevron set index: -1 = none (0.2.1, capdbg T1). The game (sub_001AE200) draws chevron entry
    # [STATIC+0x28][+0x7D] whenever +0x7D >= 0 and never checks it against the set count s16 STATIC[+0x1E]; trackbuild writes
    # that set EMPTY, so 0 (<= 0.2.0) read past it into the relocated per-unit pointer table -> base-dependent garbage loop.
    struct.pack_into("<Bbbbf", out, 0x7C, 0, CHEVRON_NONE, -1, -1, 0.0)
    struct.pack_into("<83h", out, 0x84, *(list(range(nr)) + [0] * (NROWS - nr)))   # material index per row (row r -> material r)
    for s, (rel, flag, rowsA, rowsB) in enumerate(pvs):
        c = 0x12A + CHUNK * s
        struct.pack_into("<bBB", out, c, rel, flag, 0)
        struct.pack_into("<83b", out, c + 3, *rowsA)
        struct.pack_into("<83b", out, c + 0x56, *rowsB)
    out += recs
    size = al(len(out), 0x1000)
    out += bytes(size - len(out))
    struct.pack_into("<I", out, 8, size)
    return bytes(out)


# ---------------------------------------------------------------------------------------------- collision
def _items(coll):
    """(surface, pts) -> quads in strip order: polygon (p0, p1, p2, p3) -> (p0, p1, p3, p2): tris (p0 p1 p3), (p1 p2 p3)"""
    out = []
    for surf, pts in coll:
        if len(pts) == 4:
            out.append((surf, [pts[0], pts[1], pts[3], pts[2]]))
        else:
            need(len(pts) == 3, "collision polygon with %d points" % len(pts))
            out.append((surf, list(pts)))
    return out


def _quant(p, cell):
    return tuple(cell[k] * CELL + int(round((p[k] - cell[k] * CELL) / SCALE)) * SCALE for k in range(3))


def collision_tree(coll, max_quads=8):
    """-> (tree bytes, stats). KD tree by centroid median on the longest axis; leaves <= max_quads quads / 255 vertices."""
    items = _items(coll)
    need(len(items) >= 2, "a unit needs at least 2 collision polygons")
    leaves, pairs = [], []

    def box(idx):
        ps = [p for i in idx for p in items[i][1]]
        return [min(p[k] for p in ps) for k in range(3)], [max(p[k] for p in ps) for k in range(3)]

    def make_leaf(idx):
        ps = [p for i in idx for p in items[i][1]]
        cell = []
        for k in range(3):
            lo, hi = min(p[k] for p in ps), max(p[k] for p in ps)
            c = math.floor(lo / CELL)
            need(hi - c * CELL < 1000.0 - SCALE and -128 <= c <= 127, "collision leaf does not fit one 1000 m cell")
            cell.append(c)
        vmap, verts, quads = {}, [], []
        for i in idx:
            surf, pts = items[i]
            ids = []
            for p in pts:
                q = _quant(p, cell)
                if q not in vmap:
                    vmap[q] = len(verts)
                    verts.append(q)
                ids.append(vmap[q])
            if len(ids) == 3:
                ids.append(0xFF)
            quads.append(struct.pack("<4BH4H", *ids, surf, 0, 0, 0, 0))
        need(len(verts) <= 255 and len(quads) <= 255, "leaf over 255 vertices / quads")
        leaves.append((tuple(cell), quads, verts))
        vs = verts
        return ("leaf", len(leaves) - 1, ([min(v[k] for v in vs) for k in range(3)], [max(v[k] for v in vs) for k in range(3)]))

    def build(idx):
        if len(idx) <= max_quads:
            return make_leaf(idx)
        lo, hi = box(idx)
        ax = max(range(3), key=lambda k: hi[k] - lo[k])
        s = sorted(idx, key=lambda i: (sum(p[ax] for p in items[i][1]) / len(items[i][1]), i))
        me = len(pairs)
        pairs.append(None)
        a, b = build(s[:len(s) // 2]), build(s[len(s) // 2:])
        pairs[me] = (ax, a, b)
        bx = ([min(a[2][0][k], b[2][0][k]) for k in range(3)], [max(a[2][1][k], b[2][1][k]) for k in range(3)])
        return ("pair", me, bx)

    root = build(list(range(len(items))))
    need(root[0] == "pair", "tree root must be a node pair")
    nodes = b""
    for ax, a, b in pairs:
        for side, ch in ((0, a), (1, b)):
            plane = ch[2][1][ax] if side == 0 else ch[2][0][ax]
            nodes += struct.pack("<fHBB", plane, ch[1], ax, 0xFF if ch[0] == "pair" else 0x01)
    pn = 0x30
    pl = pn + len(nodes)
    data_at = pl + 16 * len(leaves)
    lrec, blob = b"", b""
    for i, (cell, quads, verts) in enumerate(leaves):
        qb = b"".join(quads)
        qb += bytes(-len(qb) % 4)
        raw = b"".join(struct.pack("<3H", *[int(round((v[k] - cell[k] * CELL) / SCALE)) for k in range(3)]) for v in verts)
        raw += bytes(-len(raw) % 4)
        here = pl + 16 * i
        pa = data_at + len(blob) - here
        lrec += struct.pack("<IIH3b3B", pa, pa + len(qb), len(qb) + len(raw), cell[0], cell[1], cell[2], 14, len(quads), len(verts))
        blob += qb + raw
    lo, hi = root[2]
    head = struct.pack("<3fI3fI", hi[0], hi[1], hi[2], B3_TAG, lo[0], lo[1], lo[2], B3_TAG)
    head += struct.pack("<IIHHI", pn, pl, len(leaves), len(pairs), 1)
    tb = head + nodes + lrec + blob
    return tb, {"leaves": len(leaves), "pairs": len(pairs), "quads": len(items), "max_leaf_quads": max(len(q) for _, q, _ in leaves)}


def lod_block(unit_index, prism, unit, geom, coll, inst=None):
    """inst (0.3.2): (n instance types, {type: [0x40-byte matrices]}) -> tail u8[n] counts at the index end, u32[n] pointers
    (rel +0xA8) at align4, matrix runs 16-aligned in type order (rule of 2,838 / 2,838 retail LOD blocks). None = nprop 0."""
    out = header(unit_index, prism)
    out += bytes(0xB0 - len(out))
    for k, (a, c, b) in enumerate(unit.lanes):
        struct.pack_into("<f", out, 0x70 + 4 * k, a)
        struct.pack_into("<f", out, 0x80 + 4 * k, c)
        struct.pack_into("<f", out, 0x90 + 4 * k, b)
    out += LIGHT_RECORD
    tree = al(len(out), 16)
    out += bytes(tree - len(out))
    tb, tst = collision_tree(coll)
    out += tb
    ma = al(len(out), 16)
    out += bytes(ma - len(out))
    recs, vb_rel, idx_end = geom.records_bytes(ma)
    out += recs
    struct.pack_into("<4I", out, 0x50, 1, vb_rel, 0, ma - 0x50)
    struct.pack_into("<h", out, 0x60, len(geom.recs))
    # tail (nprop = 0): [+0xA8] -> the end of the indices, [+0xAC] -> align4 of it (an empty pointer array)
    ni, runs = inst if inst else (0, {})
    arr = al(idx_end + ni, 4)
    struct.pack_into("<4I", out, 0xA0, tree, 0xB0, idx_end - 0xA8, arr - 0xA8)
    end = arr + 4 * ni
    tail = []
    if ni:
        cur = al(end, 16)
        for ty in range(ni):
            ms = runs.get(ty) or []
            need(len(ms) <= 255, "unit %d: more than 255 placements of instance type %d" % (unit_index, ty))
            tail.append((ty, len(ms), cur if ms else None, ms))
            if ms:
                cur = al(cur + 0x40 * len(ms), 16)
        end = cur
    size = al(max(len(out), al(end, 16)) + 16, 0x1000)
    out += bytes(size - len(out))
    for ty, c, at, ms in tail:
        out[idx_end + ty] = c
        struct.pack_into("<I", out, arr + 4 * ty, (at - 0xA8) if at else 0)
        if ms:
            out[at:at + 0x40 * c] = b"".join(ms)
    struct.pack_into("<I", out, 8, size)
    return bytes(out), tst


def pvs_chunks(c, U, geoms_mesh, geoms_lod, nrows, visible=lambda c, t: True):
    """17 chunks of unit c: rowsA -> the target's mesh record when |rel| <= 4 else its LOD record; rowsB (reflection pass,
    LOD) empty. Flag 1 = the target is visible from c."""
    out = []
    for rel in PVS_ORDER:
        t = (c + rel) % U
        g = geoms_mesh[t] if abs(rel) <= NEAR else geoms_lod[t]
        rowsA = [g.row_rec.get(r, -1) for r in range(nrows)] + [-1] * (NROWS - nrows)
        rowsB = [-1] * NROWS
        out.append((rel, 1 if visible(c, t) else 0, rowsA, rowsB))
    return out
