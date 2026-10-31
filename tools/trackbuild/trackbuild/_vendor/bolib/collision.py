"""Collision trees of Burnout 3 and Burnout Revenge (PS2).

One tree per road section, stored in the section's LOD block at [0x90]
(both games; Revenge's crash-junction "K" tracks instead keep a single tree
in STATIC.DAT[0x54]). Layout, established from the fixup code plus the
checks in tests/test_collision.py which pass on every retail tree examined:

header 0x30 bytes
  0x00 vec3 max corner, u32 (0x41D001 in B3 files, 0x422917 in Revenge; tool leftover per the external
       review of 2026-10-12, no reader found here)
  0x10 vec3 min corner, same u32
  0x20 ptr node entries (relative to header)     0x24 ptr leaves
  0x28 u16 leaf count   0x2A u16 internal node count   0x2C u32 = 1
node entries come in pairs (pair p = entries 2p, 2p+1); the root is pair 0.
  Burnout 3, 8 bytes:  float plane,              u16 index, u8 axis, u8 kind
  Revenge,  12 bytes:  float plane, float outer, u16 index, u8 axis, u8 kind
  kind 0xFF: index = child pair;  kind 0x01: index = leaf.
  First entry of a pair: everything below it has coord[axis] <= plane.
  Second entry: coord[axis] >= plane. Children may overlap.
  Revenge's extra float is the child's other bound on that axis.
leaf 16 bytes
  0x00 ptr quad records, 0x04 ptr vertices (both relative to the leaf)
  0x08 u16 data size  0x0A s8 cell x, y, z  0x0D u8 record size (14)
  0x0E u8 quad count  0x0F u8 vertex count
quad record 14 bytes: 4 x u8 vertex index in triangle-strip order (0xFF in the 4th = triangle),
  u16 surface word (0x0001 under every start-grid slot checked; no value above 0x25 in any local file),
  4 x u16 = lighting record index per corner (docs/collision_format.md)
Criterion names (external review 2026-10-12): tree = CGtCollisionKDTree, node = CNodeDetail,
leaf = CGtPolygonSoup16, lighting table = mpaIrradianceData.
vertex 6 bytes: 3 x u16;  world = cell * 500 + value * 1000 / 65536
"""
import math
import struct

CELL = 500.0
SCALE = 1000.0 / 65536.0
REV_TAG = 0x00422917


class CollisionError(Exception):
    pass


class Leaf:
    __slots__ = ("cell", "quads", "verts")

    def __init__(self, cell, quads, verts):
        self.cell, self.quads, self.verts = cell, quads, verts   # verts are world-space tuples


class Tree:
    def __init__(self):
        self.max = self.min = None
        self.tags = (0, 0)
        self.entries = []      # (plane, outer or None, index, axis, kind)
        self.leaves = []
        self.flag = 1


def _s8(b):
    return b - 256 if b > 127 else b


def parse(data, off, game):
    """Parse the tree whose header starts at `off`."""
    nsize = 8 if game == "b3" else 12
    t = Tree()
    a = struct.unpack_from("<3fI", data, off)
    b = struct.unpack_from("<3fI", data, off + 0x10)
    t.max, t.min, t.tags = a[:3], b[:3], (a[3], b[3])
    pn, pl, nleaf, nint, t.flag = struct.unpack_from("<IIHHI", data, off + 0x20)
    if pl - pn != nsize * 2 * nint:
        raise CollisionError("node table size does not match %d-byte entries" % nsize)
    for i in range(2 * nint):
        o = off + pn + nsize * i
        plane = struct.unpack_from("<f", data, o)[0]
        outer = struct.unpack_from("<f", data, o + 4)[0] if nsize == 12 else None
        idx, axis, kind = struct.unpack_from("<HBB", data, o + nsize - 4)
        if axis > 2 or kind not in (0x01, 0xFF):
            raise CollisionError("unexpected node entry %d (axis %d kind 0x%02X)" % (i, axis, kind))
        t.entries.append((plane, outer, idx, axis, kind))
    for i in range(nleaf):
        o = off + pl + 16 * i
        pa, pb, size, cx, cy, cz, rs, nq, nv = struct.unpack_from("<IIH3b3B", data, o)
        if rs != 14:
            raise CollisionError("leaf %d: record size %d" % (i, rs))
        quads = [data[o + pa + 14 * k:o + pa + 14 * k + 14] for k in range(nq)]
        verts = []
        for k in range(nv):
            u = struct.unpack_from("<3H", data, o + pb + 6 * k)
            verts.append(tuple(c * CELL + v * SCALE for c, v in zip((cx, cy, cz), u)))
        for q in quads:
            if max(q[:4]) >= nv and max(q[:4]) != 0xFF:
                raise CollisionError("leaf %d: quad references vertex %d of %d" % (i, max(q[:4]), nv))
        t.leaves.append(Leaf((cx, cy, cz), quads, verts))
    return t


def extent(data, off, game):
    """Offset just past the last byte the tree at `off` refers to (header,
    node entries, leaf records, quad records and vertices)."""
    pn, pl, nleaf, nint = struct.unpack_from("<IIHH", data, off + 0x20)
    end = max(off + 0x30, off + pn + (8 if game == "b3" else 12) * 2 * nint, off + pl + 16 * nleaf)
    for i in range(nleaf):
        o = off + pl + 16 * i
        pa, pb, size, cx, cy, cz, rs, nq, nv = struct.unpack_from("<IIH3b3B", data, o)
        end = max(end, o + pa + rs * nq, o + pb + 6 * nv, o + min(pa, pb) + size)
    return end


def check(t, tol=0.05):
    """Structural checks. Returns a list of problems (empty = consistent):
    every leaf reachable exactly once, every vertex inside the half-spaces on
    its path and inside the header box."""
    problems, seen = [], [0] * len(t.leaves)
    inf = float("inf")

    def walk(pair, lo, hi, depth):
        if depth > 64 or 2 * pair + 1 >= len(t.entries):
            problems.append("bad pair index %d" % pair)
            return
        for side in (0, 1):
            plane, outer, idx, axis, kind = t.entries[2 * pair + side]
            l2, h2 = list(lo), list(hi)
            if side == 0:
                h2[axis] = min(h2[axis], plane)
            else:
                l2[axis] = max(l2[axis], plane)
            if kind == 0xFF:
                walk(idx, l2, h2, depth + 1)
            elif idx >= len(t.leaves):
                problems.append("leaf index %d out of range" % idx)
            else:
                seen[idx] += 1
                for v in t.leaves[idx].verts:
                    if any(v[k] < l2[k] - tol or v[k] > h2[k] + tol for k in range(3)):
                        problems.append("leaf %d vertex %s outside its node bounds" % (idx, tuple(round(x, 2) for x in v)))
                        break
    if t.entries:
        walk(0, [inf * -1] * 3, [inf] * 3, 0)
    elif len(t.leaves) > 1:
        problems.append("several leaves but no nodes")
    bad = [i for i, n in enumerate(seen) if n != 1] if t.entries else []
    if bad:
        problems.append("%d leaves not reached exactly once (first %d)" % (len(bad), bad[0]))
    for i, lf in enumerate(t.leaves):
        for v in lf.verts:
            if any(v[k] < t.min[k] - tol or v[k] > t.max[k] + tol for k in range(3)):
                problems.append("leaf %d vertex outside the header box" % i)
                break
    return problems[:20]


def bounds(t):
    vs = [v for lf in t.leaves for v in lf.verts]
    return [min(v[k] for v in vs) for k in range(3)], [max(v[k] for v in vs) for k in range(3)]


def translated(t, delta):
    """Copy of a tree moved by `delta` (world units)."""
    n = Tree()
    n.max = tuple(a + d for a, d in zip(t.max, delta))
    n.min = tuple(a + d for a, d in zip(t.min, delta))
    n.tags, n.flag = t.tags, t.flag
    n.entries = [(p + delta[ax], None if o is None else o + delta[ax], idx, ax, kind)
                 for p, o, idx, ax, kind in t.entries]
    n.leaves = [Leaf(lf.cell, lf.quads, [tuple(v[k] + delta[k] for k in range(3)) for v in lf.verts])
                for lf in t.leaves]
    return n


def _subtree_bounds(t):
    """Per-entry (min, max) of everything below each node entry."""
    out = [None] * len(t.entries)

    def leaf_box(i):
        vs = t.leaves[i].verts
        return [min(v[k] for v in vs) for k in range(3)], [max(v[k] for v in vs) for k in range(3)]

    def walk(pair):
        lo, hi = [float("inf")] * 3, [float("-inf")] * 3
        for side in (0, 1):
            e = 2 * pair + side
            _, _, idx, _, kind = t.entries[e]
            b = walk(idx) if kind == 0xFF else leaf_box(idx)
            out[e] = b
            lo = [min(a, c) for a, c in zip(lo, b[0])]
            hi = [max(a, c) for a, c in zip(hi, b[1])]
        return lo, hi
    if t.entries:
        walk(0)
    return out


def serialise_rev(t, tag=REV_TAG):
    """Write a tree in Revenge's layout (12-byte node entries). Planes are
    widened to cover re-quantised vertices; the 'outer' float is the real
    extent of the subtree on the node's axis."""
    # 1. re-quantise leaves
    leaf_blobs, qverts = [], []
    for i, lf in enumerate(t.leaves):
        if not lf.verts:
            raise CollisionError("leaf %d has no vertices" % i)
        cell = []
        for k in range(3):
            lo, hi = min(v[k] for v in lf.verts), max(v[k] for v in lf.verts)
            c = math.floor(lo / CELL)
            if hi - c * CELL >= 1000.0 - SCALE or not -128 <= c <= 127:
                raise CollisionError("leaf %d does not fit a 1000-unit cell on axis %d" % (i, k))
            cell.append(c)
        raw, world = b"", []
        for v in lf.verts:
            u = [max(0, min(65535, int(round((v[k] - cell[k] * CELL) / SCALE)))) for k in range(3)]
            raw += struct.pack("<3H", *u)
            world.append(tuple(cell[k] * CELL + u[k] * SCALE for k in range(3)))
        qverts.append(world)
        quads = b"".join(lf.quads)
        quads += bytes(-len(quads) % 4)
        raw += bytes(-len(raw) % 4)
        leaf_blobs.append((cell, quads, raw, len(lf.quads), len(lf.verts)))
    q = Tree()
    q.entries, q.flag = t.entries, t.flag
    q.leaves = [Leaf(tuple(b[0]), lf.quads, w) for b, lf, w in zip(leaf_blobs, t.leaves, qverts)]
    sub = _subtree_bounds(q)
    # 2. nodes
    nodes = b""
    for e, (plane, _, idx, axis, kind) in enumerate(t.entries):
        lo, hi = sub[e]
        if e % 2 == 0:
            plane, outer = max(plane, hi[axis]), lo[axis]
        else:
            plane, outer = min(plane, lo[axis]), hi[axis]
        nodes += struct.pack("<ffHBB", plane, outer, idx, axis, kind)
    lo, hi = bounds(q)
    pn = 0x30
    pl = pn + len(nodes)
    data_at = pl + 16 * len(q.leaves)
    leaves, blob = b"", b""
    for i, (cell, quads, raw, nq, nv) in enumerate(leaf_blobs):
        here = pl + 16 * i
        pa = data_at + len(blob) - here
        leaves += struct.pack("<IIH3b3B", pa, pa + len(quads), len(quads) + len(raw), cell[0], cell[1], cell[2], 14, nq, nv)
        blob += quads + raw
    head = struct.pack("<3fI3fI", hi[0], hi[1], hi[2], tag, lo[0], lo[1], lo[2], tag)
    head += struct.pack("<IIHHI", pn, pl, len(q.leaves), len(t.entries) // 2, t.flag)
    out = head + nodes + leaves + blob
    return out + bytes(-len(out) % 16)


def stats(t):
    surf = {}
    for lf in t.leaves:
        for qd in lf.quads:
            w = struct.unpack_from("<H", qd, 4)[0]
            surf[w] = surf.get(w, 0) + 1
    lo, hi = bounds(t) if t.leaves else ((0, 0, 0), (0, 0, 0))
    return {"leaves": len(t.leaves), "node_pairs": len(t.entries) // 2,
            "quads": sum(len(lf.quads) for lf in t.leaves), "vertices": sum(len(lf.verts) for lf in t.leaves),
            "min": [round(x, 2) for x in lo], "max": [round(x, 2) for x in hi],
            "surface_words": dict(sorted(surf.items(), key=lambda kv: -kv[1])[:8])}
