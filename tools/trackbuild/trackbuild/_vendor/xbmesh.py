"""xbmesh - READ-ONLY parser / exporter for Burnout 3 Takedown (Xbox, NTSC-U) track render meshes (B3-PC-3 Gate 6).

Every field below carries a label: XD = verified on the data, SRC = read in the recompiled game code (sub_<VA>, Takedawn
src/game/recomp/gen), HYP = hypothesis. Full write-up: ../MESH_FORMAT.md.

  STATIC.DAT (whole file is relocated in place by sub_0019B4E0, SRC):
    +0x08 u32 material table (0x28 B records), +0x0C s16 count               SRC sub_0019B4E0 / sub_001AD510 ([0x7397B4]+8)
    +0x16 s16 texture count, +0x18 u32 texture-record pointer array          SRC sub_0019B4E0, XD (xbtex.py)
    +0x54 s16 unit count, +0x58 u32 unit table (16 B: mesh off, lod off, mesh size, lod size)   SRC sub_0019CC60, XD
    material +0x00 u32 shader type (switch 1..10 in sub_000393C0), +0x0C texture-pointer array (rel. material),
             +0x11 s8 texture count, entries rel. material -> texture record                       SRC sub_0019B4E0
    texture record (0x100 B Xbox D3D pixel container): +0x0C format word, +0x48 char[32] name    XD
  STREAMED.DAT block (mesh = full detail, lod = low detail + collision), relocated by sub_0019B440(block+0x50):
    +0x50 D3DVertexBuffer {Common, Data rel +0x50, Lock}; SetStreamSource(0, block+0x50, 0x1C)   SRC sub_0019B440, sub_001AD7A0
    +0x5C u32 mesh array (rel +0x50), +0x60 s16 mesh count                                       SRC sub_0019B440
    mesh record 0x90 B: +0x00 8 x {f32 x,y,z, u32 pad} box corners, +0x80 u32 primitive (NV2A/D3DPT, 6 = strip),
      +0x84 u32 index count, +0x88 u32 index data (rel. MESH START), +0x8C s8 next mesh in chain   SRC sub_001AD510, sub_0019B440, sub_00350000
    vertex 28 B: f32 pos[3], u32 normal 11:11:10 signed, u32 D3DCOLOR, f32 uv[2]                 SRC stride; XD layout
  mesh-block PVS / material rows (camera unit's block, [view+0x1C4]):
    +0x71 s8 rows total, +0x73 s8 rows of the first (opaque) pass, +0x84 s16[83] material per row        SRC sub_001AD7A0 / sub_001ADD60 / sub_001AD510
    +0x12A 17 chunks x 0xA9: s8 rel unit, u8 flag, u8 ?, s8 rowsA[83] (+3), s8 rowsB[83] (+0x56)        SRC sub_0019D100 / sub_001AD510 / sub_001AD5E0
    rowsA head -> mesh block of unit (cam+rel) when |rel| <= 4 else its LOD block; rowsB -> LOD block   XD (this tool, 0 conflicts)
"""
import base64, json, math, struct, sys, zlib, hashlib
from collections import defaultdict, Counter
from pathlib import Path

sys.dont_write_bytecode = True
BASE = None   # vendored copy: no retail folder (trackbuild passes bytes; its tests take --game-data)
OUT = None
NROWS, NCHUNK, CHUNK = 83, 17, 0xA9
NEAR = 4          # SRC: the "4" at 0x19D244 (docs/draw-distance.md); XD: only this threshold gives 0 chain conflicts

u8 = lambda b, o: b[o]
s8 = lambda b, o: struct.unpack_from("<b", b, o)[0]
s16 = lambda b, o: struct.unpack_from("<h", b, o)[0]
u16 = lambda b, o: struct.unpack_from("<H", b, o)[0]
u32 = lambda b, o: struct.unpack_from("<I", b, o)[0]
f32 = lambda b, o: struct.unpack_from("<f", b, o)[0]


def read_ro(p):
    with open(p, "rb") as fh:          # read-only access
        return fh.read()


# ------------------------------------------------------------------------------------------------ STATIC
class Static:
    def __init__(self, data):
        self.d = d = data
        self.version = u32(d, 0)
        self.nunit, ut = s16(d, 0x54), u32(d, 0x58)
        self.units = [struct.unpack_from("<4I", d, ut + 16 * i) for i in range(self.nunit)]
        ta, nt = u32(d, 0x18), s16(d, 0x16)
        self.tex = []
        self.tex_by_off = {}
        for i in range(nt):
            o = u32(d, ta + 4 * i)
            fmt = u32(d, o + 0x0C)
            name = d[o + 0x48:o + 0x68].split(b"\0")[0].decode("ascii", "replace")
            t = {"i": i, "rec": o, "common": u32(d, o), "data": o + u32(d, o + 4), "fmt_word": fmt, "format": (fmt >> 8) & 0xFF,
                 "mips": (fmt >> 16) & 0xF, "w": 1 << ((fmt >> 20) & 0xF), "h": 1 << ((fmt >> 24) & 0xF), "name": name}
            self.tex.append(t)
            self.tex_by_off[o] = i
        mt, nm = u32(d, 0x08), s16(d, 0x0C)
        self.mat = []
        for i in range(nm):
            r = mt + 0x28 * i
            arr, cnt = u32(d, r + 0x0C), s8(d, r + 0x11)
            refs = []
            if arr:
                for k in range(max(0, cnt)):
                    to = (u32(d, r + arr + 4 * k) + r) & 0xFFFFFFFF
                    refs.append(self.tex_by_off.get(to, "0x%X?" % to))
            self.mat.append({"i": i, "rec": r, "type": u32(d, r), "f04": f32(d, r + 4), "f08": f32(d, r + 8), "b10": u8(d, r + 0x10),
                             "ntex": cnt, "tex": refs, "raw": d[r:r + 0x28].hex()})


# ------------------------------------------------------------------------------------------------ STREAMED block
MESH_FMT = "<32f4I"        # used only for floats view; raw corner words are kept for round trip
VTX = struct.Struct("<3fII2f")


def dec_normal(n):
    x = n & 0x7FF; x -= 0x800 if x & 0x400 else 0
    y = (n >> 11) & 0x7FF; y -= 0x800 if y & 0x400 else 0
    z = (n >> 22) & 0x3FF; z -= 0x400 if z & 0x200 else 0
    return x / 1023.0, y / 1023.0, z / 511.0


class Block:
    def __init__(self, sm, off, size, kind, unit):
        self.off, self.size, self.kind, self.unit = off, size, kind, unit
        self.b = b = sm[off:off + size]
        self.hdr = struct.unpack_from("<4I", b, 0)
        self.quad = [struct.unpack_from("<4f", b, 0x10 + 16 * k) for k in range(4)]
        self.vb_common, self.vb_data_rel, self.vb_lock, self.mesh_rel = struct.unpack_from("<4I", b, 0x50)
        self.nmesh, self.w62 = s16(b, 0x60), u16(b, 0x62)
        self.w64, self.w68, self.w6C = struct.unpack_from("<3I", b, 0x64)
        self.vb = 0x50 + self.vb_data_rel
        self.ma = 0x50 + self.mesh_rel
        self.meshes = []
        for i in range(self.nmesh):
            m = self.ma + 0x90 * i
            corners = [struct.unpack_from("<3fI", b, m + 16 * k) for k in range(8)]
            prim, nidx, rel = struct.unpack_from("<3I", b, m + 0x80)
            nxt = s8(b, m + 0x8C)
            ip = m + rel
            idx = list(struct.unpack_from("<%dH" % nidx, b, ip))
            self.meshes.append({"i": i, "rec": m, "corners": corners, "prim": prim, "nidx": nidx, "idx_rel": rel, "next": nxt,
                                "tail": b[m + 0x8D:m + 0x90], "ip": ip, "idx": idx})
        self.ib = min(x["ip"] for x in self.meshes) if self.meshes else self.vb
        self.nvert_gap = (self.ib - self.vb) / 28.0
        self.maxidx = max((max(x["idx"]) for x in self.meshes if x["idx"]), default=-1)
        self.nvert = self.maxidx + 1
        self.verts = [VTX.unpack_from(b, self.vb + 28 * k) for k in range(self.nvert)]
        if kind == "mesh":
            self.b70, self.rows_total, self.b72, self.rows_first = b[0x70], s8(b, 0x71), b[0x72], s8(b, 0x73)
            self.groups = [s8(b, 0x74 + k) for k in range(8)]
            self.w7C, self.bd0, self.bd1, self.f80 = u16(b, 0x7C), s8(b, 0x7E), s8(b, 0x7F), f32(b, 0x80)
            self.mats = list(struct.unpack_from("<83h", b, 0x84))
            self.chunks = []
            for s in range(NCHUNK):
                c = 0x12A + CHUNK * s
                self.chunks.append({"rel": s8(b, c), "flag": b[c + 1], "b2": b[c + 2],
                                    "rowsA": list(struct.unpack_from("<83b", b, c + 3)),
                                    "rowsB": list(struct.unpack_from("<83b", b, c + 0x56))})
        else:
            self.lod_f70 = struct.unpack_from("<12f", b, 0x70)
            self.tree, self.ptrA4 = u32(b, 0xA0), u32(b, 0xA4)

    # -------------------------------------------------------------- identity round trip of the decoded structures
    def serialize_regions(self):
        """Re-serialize every decoded structure from the parsed values. Returns list of (start, bytes, name)."""
        out = []
        h = struct.pack("<4I", *self.hdr) + b"".join(struct.pack("<4f", *q) for q in self.quad)
        h += struct.pack("<4I", self.vb_common, self.vb_data_rel, self.vb_lock, self.mesh_rel)
        h += struct.pack("<hH3I", self.nmesh, self.w62, self.w64, self.w68, self.w6C)
        out.append((0, h, "header 0x00-0x6F"))
        if self.kind == "mesh":
            p = bytes([self.b70]) + struct.pack("<b", self.rows_total) + bytes([self.b72]) + struct.pack("<b", self.rows_first)
            p += struct.pack("<8b", *self.groups) + struct.pack("<Hbbf", self.w7C, self.bd0, self.bd1, self.f80)
            p += struct.pack("<83h", *self.mats)
            for c in self.chunks:
                p += struct.pack("<bBB", c["rel"], c["flag"], c["b2"]) + struct.pack("<83b", *c["rowsA"]) + struct.pack("<83b", *c["rowsB"])
            out.append((0x70, p, "PVS/material rows 0x70-0xC62"))
        else:
            out.append((0x70, struct.pack("<12f2I", *self.lod_f70, self.tree, self.ptrA4), "LOD header 0x70-0xA7"))
        mr = b""
        for m in self.meshes:
            mr += b"".join(struct.pack("<3fI", *c) for c in m["corners"])
            mr += struct.pack("<3Ib", m["prim"], m["nidx"], m["idx_rel"], m["next"]) + m["tail"]
        out.append((self.ma, mr, "mesh records"))
        out.append((self.vb, b"".join(VTX.pack(*v) for v in self.verts), "vertices"))
        for m in sorted(self.meshes, key=lambda x: x["ip"]):
            out.append((m["ip"], struct.pack("<%dH" % m["nidx"], *m["idx"]), "indices"))
        return out

    def roundtrip(self):
        regs = self.serialize_regions()
        cover = bytearray(len(self.b))
        bad = []
        for st_, data, name in regs:
            if self.b[st_:st_ + len(data)] != data:
                bad.append(name)
            for k in range(st_, st_ + len(data)):
                cover[k] = 1
        # bytes not covered by any decoded structure
        unc = [k for k in range(len(self.b)) if not cover[k]]
        unc_nz = [k for k in unc if self.b[k]]
        # describe uncovered non-zero spans
        spans = []
        for k in unc_nz:
            if spans and k == spans[-1][1]:
                spans[-1][1] = k + 1
            else:
                spans.append([k, k + 1])
        return {"regions": len(regs), "mismatched_regions": sorted(set(bad)), "decoded_bytes": len(self.b) - len(unc),
                "uncovered_bytes": len(unc), "uncovered_nonzero_bytes": len(unc_nz),
                "uncovered_nonzero_spans": [("0x%X" % a, "0x%X" % e) for a, e in spans[:12]], "n_spans": len(spans)}


def rebuild_mesh_block(blk):
    """Writer prototype (identity test): regenerate a whole MESH block from the parsed values using only layout rules
    (offsets recomputed, not copied): header 0x00-0x6F, PVS 0x70-0xC62, zero pad to the mesh array at 0xC90, mesh records,
    vertices (16-aligned start), index runs in mesh order each 4-aligned, zero pad to the next 0x1000. Returns bytes."""
    n = blk.nmesh
    ma = 0xC90
    vb = ma + 0x90 * n
    vb += (-vb) % 16
    ib = vb + 28 * blk.nvert
    ips, pos = [], ib
    for m in blk.meshes:
        pos += (-pos) % 4
        ips.append(pos)
        pos += 2 * m["nidx"]
    size = pos + ((-pos) % 0x1000)
    out = bytearray(size)
    hdr = list(blk.hdr); hdr[2] = size
    struct.pack_into("<4I", out, 0, *hdr)
    for k, q in enumerate(blk.quad):
        struct.pack_into("<4f", out, 0x10 + 16 * k, *q)
    struct.pack_into("<4I", out, 0x50, blk.vb_common, vb - 0x50, blk.vb_lock, ma - 0x50)
    struct.pack_into("<hH3I", out, 0x60, n, blk.w62, blk.w64, blk.w68, blk.w6C)
    regs = blk.serialize_regions()
    pv = [r for r in regs if r[2].startswith("PVS")][0][1]
    out[0x70:0x70 + len(pv)] = pv
    for m, ip in zip(blk.meshes, ips):
        o = ma + 0x90 * m["i"]
        for k, c in enumerate(m["corners"]):
            struct.pack_into("<3fI", out, o + 16 * k, *c)
        struct.pack_into("<3Ib", out, o + 0x80, m["prim"], m["nidx"], ip - o, m["next"])
        out[o + 0x8D:o + 0x90] = m["tail"]
        struct.pack_into("<%dH" % m["nidx"], out, ip, *m["idx"])
    for k, v in enumerate(blk.verts):
        VTX.pack_into(out, vb + 28 * k, *v)
    return bytes(out)


class Track:
    def __init__(self, tid):
        self.tid = tid
        d = BASE / tid
        self.st = Static(read_ro(d / "static.dat"))
        self.sm = read_ro(d / "streamed.dat")
        self.blocks = {}
        self.empty_units = []
        for u, (mo, lo, ms, ls) in enumerate(self.st.units):
            if ms == 0 or ls == 0:          # XD: US/C5_V1 has a 0-byte streamed.dat and an all-zero unit table
                self.empty_units.append(u)
                continue
            self.blocks[(u, "mesh")] = Block(self.sm, mo, ms, "mesh", u)
            self.blocks[(u, "lod")] = Block(self.sm, lo, ls, "lod", u)

    def material_map(self):
        """walk every PVS chain exactly as sub_001AD510 / sub_001AD5E0 do; -> {(unit, kind, mesh): {material: passes}}"""
        mm = defaultdict(lambda: defaultdict(set))
        stats = Counter()
        n = self.st.nunit
        for c in range(n):
            if (c, "mesh") not in self.blocks:
                continue
            cb = self.blocks[(c, "mesh")]
            for ch in cb.chunks:
                tgt = (c + ch["rel"]) % n
                for pname, rows, kind in (("A", ch["rowsA"], "mesh" if abs(ch["rel"]) <= NEAR else "lod"), ("B", ch["rowsB"], "lod")):
                    blk = self.blocks[(tgt, kind)]
                    seen = set()
                    for r in range(NROWS):
                        k = rows[r]
                        while k >= 0:
                            if k >= blk.nmesh:
                                stats["chain_out_of_range"] += 1
                                break
                            if k in seen:
                                stats["chain_cycle_or_dup"] += 1
                                break
                            seen.add(k)
                            tag = pname + ("1" if r < cb.rows_first else "2") if pname == "A" else "B"
                            mm[(tgt, kind, k)][cb.mats[r]].add(tag)
                            stats["visits_" + pname] += 1
                            k = blk.meshes[k]["next"]
                        if pname == "A" and r >= cb.rows_total and rows[r] >= 0:
                            stats["heads_beyond_rows_total"] += 1
        return mm, stats


# ------------------------------------------------------------------------------------------------ geometry
def triangles(prim, idx, reset_on_degenerate=False):
    """-> (tris, dropped_degenerate). prim 6 = strip (standard parity by position), 5 = list, 2 = lines (no tris)."""
    tris, deg = [], 0
    if prim == 6:
        par = 0
        for i in range(len(idx) - 2):
            a, b, c = idx[i], idx[i + 1], idx[i + 2]
            p = (par if reset_on_degenerate else i) & 1
            if a == b or b == c or a == c:
                deg += 1
                if reset_on_degenerate:
                    par = 0 if (a == b) else par + 1
                continue
            tris.append((b, a, c) if p else (a, b, c))
            par += 1
    elif prim == 5:
        for i in range(0, len(idx) - 2, 3):
            a, b, c = idx[i:i + 3]
            if a == b or b == c or a == c:
                deg += 1
                continue
            tris.append((a, b, c))
    return tris, deg


def to_gl(p):                 # game (x, y, z) -> glTF (x, y, -z): mirror Z (HYP: D3D left-handed, Y up; XD: Y is up)
    return (p[0], p[1], -p[2])


def winding_score(verts, tris, mirror=True):
    """fraction of triangles whose right-hand geometric normal (after mirroring) agrees with the averaged vertex normals"""
    agree = tot = 0
    for a, b, c in tris:
        pa, pb, pc = (to_gl(verts[k][:3]) if mirror else verts[k][:3] for k in (a, b, c))
        e1 = [pb[i] - pa[i] for i in range(3)]; e2 = [pc[i] - pa[i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        vn = [0.0, 0.0, 0.0]
        for k in (a, b, c):
            q = dec_normal(verts[k][3])
            q = (q[0], q[1], -q[2]) if mirror else q
            vn = [vn[i] + q[i] for i in range(3)]
        d = sum(n[i] * vn[i] for i in range(3))
        if abs(d) < 1e-9:
            continue
        tot += 1
        agree += d > 0
    return agree, tot


# ------------------------------------------------------------------------------------------------ textures (PNG preview)
def _c565(c):
    return (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)


def decode_dxt(buf, o, w, h, fmt):
    """-> RGBA bytes of mip 0 (DXT1 0x0C, DXT3 0x0E, DXT5 0x0F; linear block order, per xbtex.py)"""
    out = bytearray(w * h * 4)
    bs = 8 if fmt == 0x0C else 16
    p = o
    for by in range((h + 3) // 4):
        for bx in range((w + 3) // 4):
            alpha = [255] * 16
            if fmt == 0x0E:
                a64 = int.from_bytes(buf[p:p + 8], "little")
                alpha = [((a64 >> (4 * k)) & 15) * 17 for k in range(16)]
            elif fmt == 0x0F:
                a0, a1 = buf[p], buf[p + 1]
                bits = int.from_bytes(buf[p + 2:p + 8], "little")
                pal = [a0, a1] + ([((6 - k) * a0 + (k + 1) * a1) // 7 for k in range(6)] if a0 > a1 else
                                  [((4 - k) * a0 + (k + 1) * a1) // 5 for k in range(4)] + [0, 255])
                alpha = [pal[(bits >> (3 * k)) & 7] for k in range(16)]
            q = p + (bs - 8)
            c0, c1, ix = struct.unpack_from("<HHI", buf, q)
            a, b = _c565(c0), _c565(c1)
            if c0 > c1 or fmt != 0x0C:
                pal = [a + (255,), b + (255,), tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,), tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
            else:
                pal = [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]
            for k in range(16):
                x, y = bx * 4 + (k & 3), by * 4 + (k >> 2)
                if x < w and y < h:
                    r_, g_, b_, a_ = pal[(ix >> (2 * k)) & 3]
                    if fmt != 0x0C:
                        a_ = alpha[k]
                    z = (y * w + x) * 4
                    out[z:z + 4] = bytes((r_, g_, b_, a_))
            p += bs
    return out


def write_png(path, w, h, rgba):
    raw = b"".join(b"\0" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


# ------------------------------------------------------------------------------------------------ glTF export
def export_gltf(trk, unit, kind, mm, path, with_textures=True):
    blk = trk.blocks[(unit, kind)]
    V = blk.verts
    pos = [to_gl(v[:3]) for v in V]
    nrm = []
    for v in V:
        x, y, z = dec_normal(v[3]); L = math.sqrt(x * x + y * y + z * z) or 1.0
        nrm.append((x / L, y / L, -z / L))
    col = [((v[4] >> 16) & 255, (v[4] >> 8) & 255, v[4] & 255, (v[4] >> 24) & 255) for v in V]    # D3DCOLOR ARGB -> RGBA
    uv = [(v[5], v[6]) for v in V]
    bin_ = bytearray()
    views, accs = [], []

    def add(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data)} | ({"target": target} if target else {}))
        bin_.extend(data)
        return len(views) - 1

    vp = add(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
    accs.append({"bufferView": vp, "componentType": 5126, "count": len(pos), "type": "VEC3",
                 "min": [min(p[i] for p in pos) for i in range(3)], "max": [max(p[i] for p in pos) for i in range(3)]})
    vn = add(b"".join(struct.pack("<3f", *p) for p in nrm), 34962)
    accs.append({"bufferView": vn, "componentType": 5126, "count": len(nrm), "type": "VEC3"})
    vt = add(b"".join(struct.pack("<2f", *p) for p in uv), 34962)
    accs.append({"bufferView": vt, "componentType": 5126, "count": len(uv), "type": "VEC2"})
    vc = add(b"".join(bytes(c) for c in col), 34962)
    accs.append({"bufferView": vc, "componentType": 5121, "normalized": True, "count": len(col), "type": "VEC4"})
    attrs = {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "COLOR_0": 3}
    # group meshes by material
    groups = defaultdict(lambda: {"tris": [], "lines": [], "meshes": []})
    stats = {"strip_tris": 0, "degenerate_dropped": 0, "line_segments": 0, "unmapped_meshes": [], "per_material": {}}
    for m in blk.meshes:
        mats = mm.get((unit, kind, m["i"]), {})
        mat = min(mats) if mats else -1
        if not mats:
            stats["unmapped_meshes"].append(m["i"])
        g = groups[mat]
        g["meshes"].append(m["i"])
        if m["prim"] == 2:
            g["lines"].extend(m["idx"])
            stats["line_segments"] += len(m["idx"]) // 2
        else:
            t, deg = triangles(m["prim"], m["idx"])
            g["tris"].extend(t)
            stats["strip_tris"] += len(t); stats["degenerate_dropped"] += deg
    # data-driven winding: keep (a,b,c) if most triangles agree with the vertex normals after the mirror, else swap
    alltris = [t for g in groups.values() for t in g["tris"]]
    ag, tot = winding_score(V, alltris)
    flip = ag < tot / 2
    stats["winding_agree_fraction_unflipped"] = round(ag / tot, 4) if tot else None
    stats["winding_swapped_for_gltf"] = flip
    materials, textures, images, samplers = [], [], [], [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
    img_of = {}
    prims = []
    texdir = Path(path).parent / "tex"
    for mat in sorted(groups):
        g = groups[mat]
        mrec = trk.st.mat[mat] if 0 <= mat < len(trk.st.mat) else None
        tname = None
        mj = {"name": "mat%03d" % mat, "doubleSided": True, "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0},
              "extras": {"b3_material": mat}}
        if mrec:
            mj["extras"].update(type=mrec["type"], textures=[trk.st.tex[t]["name"] if isinstance(t, int) else t for t in mrec["tex"]])
            if mrec["tex"] and isinstance(mrec["tex"][0], int):
                ti = mrec["tex"][0]; t = trk.st.tex[ti]; tname = t["name"]
                mj["name"] = "mat%03d_%s" % (mat, tname)
                if with_textures and t["format"] in (0x0C, 0x0E, 0x0F):
                    if ti not in img_of:
                        texdir.mkdir(exist_ok=True)
                        fn = "%s_t%03d_%s.png" % (trk.tid.replace("/", "_").replace("\\", "_"), ti, "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in tname))
                        write_png(texdir / fn, t["w"], t["h"], decode_dxt(trk.st.d, t["data"], t["w"], t["h"], t["format"]))
                        images.append({"uri": "tex/" + fn}); textures.append({"sampler": 0, "source": len(images) - 1})
                        img_of[ti] = len(textures) - 1
                    mj["pbrMetallicRoughness"]["baseColorTexture"] = {"index": img_of[ti]}
                    if t["format"] != 0x0C:
                        mj["alphaMode"] = "MASK"
        materials.append(mj)
        mi = len(materials) - 1
        stats["per_material"][str(mat)] = {"texture": tname, "meshes": g["meshes"], "triangles": len(g["tris"]), "line_segments": len(g["lines"]) // 2}
        if g["tris"]:
            data = b"".join(struct.pack("<3H", *((t[1], t[0], t[2]) if flip else t)) for t in g["tris"])
            iv = add(data, 34963)
            accs.append({"bufferView": iv, "componentType": 5123, "count": 3 * len(g["tris"]), "type": "SCALAR"})
            prims.append({"attributes": attrs, "indices": len(accs) - 1, "material": mi, "mode": 4})
        if g["lines"]:
            iv = add(struct.pack("<%dH" % len(g["lines"]), *g["lines"]), 34963)
            accs.append({"bufferView": iv, "componentType": 5123, "count": len(g["lines"]), "type": "SCALAR"})
            prims.append({"attributes": attrs, "indices": len(accs) - 1, "material": mi, "mode": 1})
    binname = Path(path).with_suffix(".bin").name
    gl = {"asset": {"version": "2.0", "generator": "xbmesh.py (B3-PC-3 Gate 6, read-only research export)"},
          "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"mesh": 0, "name": "%s_unit%d_%s" % (trk.tid, unit, kind)}],
          "meshes": [{"name": "%s_unit%d_%s" % (trk.tid, unit, kind), "primitives": prims}],
          "materials": materials, "accessors": accs, "bufferViews": views,
          "buffers": [{"byteLength": len(bin_), "uri": binname}]}
    if images:
        gl.update(images=images, textures=textures, samplers=samplers)
    Path(path).with_suffix(".bin").write_bytes(bytes(bin_))
    Path(path).write_text(json.dumps(gl, indent=1))
    return stats


def export_obj(trk, unit, kind, mm, path):
    blk = trk.blocks[(unit, kind)]
    lines = ["# xbmesh.py read-only export %s unit %d %s; game coords mirrored z -> -z" % (trk.tid, unit, kind)]
    for v in blk.verts:
        p = to_gl(v[:3]); lines.append("v %.6f %.6f %.6f" % p)
    for v in blk.verts:
        lines.append("vt %.6f %.6f" % (v[5], 1.0 - v[6]))      # OBJ v axis points up
    byg = defaultdict(list)
    for m in blk.meshes:
        mats = mm.get((unit, kind, m["i"]), {})
        byg[min(mats) if mats else -1].append(m)
    alltris = [t for m in blk.meshes for t in triangles(m["prim"], m["idx"])[0]]
    ag, tot = winding_score(blk.verts, alltris)
    flip = ag < tot / 2
    for mat in sorted(byg):
        tn = ""
        if 0 <= mat < len(trk.st.mat) and trk.st.mat[mat]["tex"] and isinstance(trk.st.mat[mat]["tex"][0], int):
            tn = "_" + trk.st.tex[trk.st.mat[mat]["tex"][0]]["name"]
        lines.append("g mat%03d%s" % (mat, tn)); lines.append("usemtl mat%03d%s" % (mat, tn))
        for m in byg[mat]:
            if m["prim"] == 2:
                for i in range(0, len(m["idx"]) - 1, 2):
                    lines.append("l %d %d" % (m["idx"][i] + 1, m["idx"][i + 1] + 1))
                continue
            for t in triangles(m["prim"], m["idx"])[0]:
                a, b, c = (t[1], t[0], t[2]) if flip else t
                lines.append("f %d/%d %d/%d %d/%d" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))
    Path(path).write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------------------------ validation
def bbox(pts):
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def validate_block(trk, unit, kind, mm):
    blk = trk.blocks[(unit, kind)]
    r = {"unit": unit, "kind": kind, "file_offset": "0x%X" % blk.off, "size": blk.size, "hdr": [hex(x) for x in blk.hdr],
         "meshes": blk.nmesh, "vertices": blk.nvert, "vertices_by_gap": blk.nvert_gap,
         "prim_types": dict(Counter(m["prim"] for m in blk.meshes)), "indices": sum(m["nidx"] for m in blk.meshes)}
    vmin, vmax = bbox([v[:3] for v in blk.verts])
    r["vertex_aabb"] = [vmin, vmax]
    # per-mesh: vertices inside the AABB of the 8 record corners
    inside = 0; worst = 0.0; ranges_contig = 0
    for m in blk.meshes:
        cmin, cmax = bbox([c[:3] for c in m["corners"]])
        used = sorted(set(m["idx"]))
        mmn, mmx = bbox([blk.verts[k][:3] for k in used])
        ex = max(max(cmin[i] - mmn[i], mmx[i] - cmax[i]) for i in range(3))
        worst = max(worst, ex)
        inside += ex <= 0.01
        ranges_contig += used == list(range(used[0], used[-1] + 1))
    r["meshes_vertices_within_corner_aabb_eps0.01"] = inside
    r["worst_vertex_outside_corner_aabb"] = worst
    r["meshes_with_contiguous_vertex_range"] = ranges_contig
    qmin, qmax = bbox([q[:3] for q in blk.quad])
    r["header_quad_xz"] = {"min": [qmin[0], qmin[2]], "max": [qmax[0], qmax[2]], "y": qmin[1], "w0": blk.quad[0][3]}
    r["vertices_inside_header_quad_xz_aabb_fraction"] = round(sum(1 for v in blk.verts if qmin[0] - 1e-3 <= v[0] <= qmax[0] + 1e-3 and qmin[2] - 1e-3 <= v[2] <= qmax[2] + 1e-3) / max(1, blk.nvert), 4)
    tris = []; deg = 0; lines = 0
    for m in blk.meshes:
        if m["prim"] == 2:
            lines += m["nidx"] // 2; continue
        t, d = triangles(m["prim"], m["idx"]); tris += t; deg += d
    r["triangles"] = len(tris); r["degenerate_dropped"] = deg; r["line_segments"] = lines
    a, t = winding_score(blk.verts, tris)
    tr, dr = [], 0
    for m in blk.meshes:
        if m["prim"] != 2:
            x, y = triangles(m["prim"], m["idx"], reset_on_degenerate=True); tr += x
    a2, t2 = winding_score(blk.verts, tr)
    r["winding_normal_agreement"] = {"standard_parity": round(a / t, 4) if t else None, "reset_after_degenerate": round(a2 / t2, 4) if t2 else None,
                                     "note": "fraction agreeing with vertex normals in glTF space (z mirrored), before any swap"}
    # long edges (Takedawn note claimed spanning triangles via index 0)
    long_e = 0
    for x, y, z in tris:
        for p, q in ((x, y), (y, z), (z, x)):
            if math.dist(blk.verts[p][:3], blk.verts[q][:3]) > 40.0:
                long_e += 1; break
    r["triangles_with_edge_over_40"] = long_e
    nl = [math.sqrt(sum(c * c for c in dec_normal(v[3]))) for v in blk.verts]
    r["normal_length_min_max"] = [round(min(nl), 4), round(max(nl), 4)]
    r["uv_range"] = [[min(v[5] for v in blk.verts), min(v[6] for v in blk.verts)], [max(v[5] for v in blk.verts), max(v[6] for v in blk.verts)]]
    r["color_alpha_values"] = sorted(Counter(v[4] >> 24 for v in blk.verts))
    r["color_rgb_equal_fraction"] = round(sum(1 for v in blk.verts if (v[4] >> 16) & 255 == (v[4] >> 8) & 255 == v[4] & 255) / max(1, blk.nvert), 4)
    mats = Counter()
    unm = 0; multi = 0
    for m in blk.meshes:
        ms = mm.get((unit, kind, m["i"]), {})
        if not ms: unm += 1
        if len(ms) > 1: multi += 1
        for k in ms: mats[k] += 1
    r["material_assignment"] = {"meshes_unmapped": unm, "meshes_with_conflicting_materials": multi, "distinct_materials": len(mats)}
    r["roundtrip"] = blk.roundtrip()
    if kind == "lod":
        t0 = blk.tree
        if 0 < t0 < blk.size - 0x30:
            a_ = struct.unpack_from("<3f", blk.b, t0); b_ = struct.unpack_from("<3f", blk.b, t0 + 0x10)
            r["collision_tree"] = {"offset": "0x%X" % t0, "header_max": a_, "header_min": b_, "leaves_u16_0x28": u16(blk.b, t0 + 0x28)}
            cv = collision_vertices(blk.b, t0)
            if cv:
                cmin, cmax = bbox(cv)
                r["collision_tree"].update(vertices=len(cv), vertex_aabb=[cmin, cmax])
    return r


def collision_vertices(b, t):
    """Collision vertices of the tree at block offset t. Layout per the PS2 reference parser (<workspace>
    collision.py, 'b3'; B3-PC-1 found the Xbox trees identical): leaves 16 B at t+[t+0x24], u16 count t+0x28;
    leaf +4 = vertex ptr rel. leaf, +0x0A s8 cell xyz, +0x0F u8 vertex count; vertex 3 x u16, world = cell*500 + v*1000/65536."""
    pl, nleaf = u32(b, t + 0x24), u16(b, t + 0x28)
    out = []
    for i in range(nleaf):
        o = t + pl + 16 * i
        pa, pb, size, cx, cy, cz, rs, nq, nv = struct.unpack_from("<IIH3b3B", b, o)
        for k in range(nv):
            q = struct.unpack_from("<3H", b, o + pb + 6 * k)
            out.append(tuple(c * 500.0 + v * 1000.0 / 65536.0 for c, v in zip((cx, cy, cz), q)))
    return out


def road_vs_collision(trk, unit):
    """XD check that render meshes and collision share one coordinate system: for every vertex of meshes whose texture name
    contains 'road', the distance to the nearest collision vertex of the same unit's LOD tree (grid hash)."""
    lod = trk.blocks[(unit, "lod")]
    cv = collision_vertices(lod.b, lod.tree)
    grid = defaultdict(list)
    for p in cv:
        grid[(int(p[0] // 4), int(p[1] // 4), int(p[2] // 4))].append(p)
    mm, _ = trk.material_map()
    blk = trk.blocks[(unit, "mesh")]
    ds = []
    for m in blk.meshes:
        mats = mm.get((unit, "mesh", m["i"]), {})
        if not mats:
            continue
        mr = trk.st.mat[min(mats)]
        if not (mr["tex"] and isinstance(mr["tex"][0], int) and "road" in trk.st.tex[mr["tex"][0]]["name"].lower()):
            continue
        for k in sorted(set(m["idx"])):
            p = blk.verts[k][:3]
            gx, gy, gz = int(p[0] // 4), int(p[1] // 4), int(p[2] // 4)
            best = 1e9
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for q in grid.get((gx + dx, gy + dy, gz + dz), ()):
                            best = min(best, math.dist(p, q))
            ds.append(best)
    ds.sort()
    if not ds:
        return None
    pct = lambda f: round(ds[min(len(ds) - 1, int(f * len(ds)))], 3)
    return {"road_vertices": len(ds), "collision_vertices": len(cv), "nearest_dist_median": pct(0.5), "p90": pct(0.9),
            "within_0.05": sum(d <= 0.05 for d in ds), "within_0.5": sum(d <= 0.5 for d in ds), "beyond_4_or_none": sum(d > 4 for d in ds)}


def survey(tids):
    """every block of every track: decode sanity + round trip + PVS chain consistency"""
    res = {}
    for tid in tids:
        try:
            trk = Track(tid)
        except Exception as e:  # noqa
            res[tid] = {"error": repr(e)}; continue
        mm, stats = trk.material_map()
        agg = Counter(); prims = Counter(); bad = []
        for (u, k), blk in trk.blocks.items():
            agg["blocks"] += 1
            agg["meshes"] += blk.nmesh
            agg["vertices"] += blk.nvert
            prims.update(m["prim"] for m in blk.meshes)
            if abs(blk.nvert_gap - blk.nvert) > 1e-9:
                agg["vertex_gap_mismatch"] += 1
            rt = blk.roundtrip()
            if k == "mesh":
                agg["mesh_block_rebuild_identical"] += rebuild_mesh_block(blk) == blk.b
            if rt["mismatched_regions"]:
                bad.append((u, k, rt["mismatched_regions"]))
            agg["uncovered_nonzero_bytes_" + k] += rt["uncovered_nonzero_bytes"]
            for m in blk.meshes:
                ms = mm.get((u, k, m["i"]), {})
                agg["meshes_unmapped"] += not ms
                agg["meshes_conflict"] += len(ms) > 1
        spans = sorted((b.off, b.size) for b in trk.blocks.values())
        end = 0; gaps = 0
        for o, s in spans:
            gaps += o != end; end = o + s
        agg["streamed_tiled_exactly"] = int(bool(spans) and gaps == 0 and end == len(trk.sm))
        res[tid] = {"units": trk.st.nunit, "empty_units": len(trk.empty_units), "agg": dict(agg), "prim_types": dict(prims), "pvs": dict(stats),
                    "roundtrip_failures": bad[:10], "n_roundtrip_failures": len(bad)}
        print(tid, json.dumps(res[tid]["agg"]), "prims", dict(prims), "rt_fail", len(bad), "pvs", dict(stats))
    return res


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    if argv and argv[0] == "survey":
        tids = [p.parent.relative_to(BASE).as_posix() for p in sorted(BASE.glob("*/*/streamed.dat"))]
        res = survey(tids)
        (OUT / "SURVEY.json").write_text(json.dumps(res, indent=1))
        return
    tid = argv[0] if argv else "US/C3_V1"
    units = [int(x) for x in argv[1].split(",")] if len(argv) > 1 else [5]
    trk = Track(tid)
    mm, stats = trk.material_map()
    val = {"track": tid, "static": {"version": hex(trk.st.version), "units": trk.st.nunit, "materials": len(trk.st.mat), "textures": len(trk.st.tex),
                                    "texture_formats": dict(Counter("0x%02X" % t["format"] for t in trk.st.tex))},
           "pvs_walk": dict(stats), "exports": []}
    for u in units:
        for kind in ("mesh", "lod"):
            base = OUT / ("%s_unit%02d_%s" % (tid.replace("/", "_"), u, kind))
            st_ = export_gltf(trk, u, kind, mm, str(base) + ".gltf")
            export_obj(trk, u, kind, mm, str(base) + ".obj")
            v = validate_block(trk, u, kind, mm)
            v["export"] = {"gltf": str(base) + ".gltf", "obj": str(base) + ".obj", **st_,
                           "gltf_sha256": hashlib.sha256(Path(str(base) + ".gltf").read_bytes()).hexdigest(),
                           "bin_sha256": hashlib.sha256(Path(str(base) + ".bin").read_bytes()).hexdigest()}
            val["exports"].append(v)
            print("unit %d %s: meshes %d verts %d tris %d lines %d deg %d roundtrip %s uncovered-nonzero %d winding %s" % (
                u, kind, v["meshes"], v["vertices"], v["triangles"], v["line_segments"], v["degenerate_dropped"],
                "OK" if not v["roundtrip"]["mismatched_regions"] else v["roundtrip"]["mismatched_regions"],
                v["roundtrip"]["uncovered_nonzero_bytes"], v["winding_normal_agreement"]))
        val.setdefault("road_vs_collision", {})[str(u)] = road_vs_collision(trk, u)
        print("unit %d road vs collision:" % u, val["road_vs_collision"][str(u)])
        val.setdefault("mesh_block_full_rebuild_identical", {})[str(u)] = rebuild_mesh_block(trk.blocks[(u, "mesh")]) == trk.blocks[(u, "mesh")].b
    sp = OUT / "SURVEY.json"
    if sp.exists():
        s = json.loads(sp.read_text())
        tot = Counter(); prim = Counter()
        for tid_, r in s.items():
            if "agg" in r:
                tot.update(r["agg"]); prim.update(r["prim_types"]); tot["tracks"] += 1
                tot["roundtrip_failures"] += r["n_roundtrip_failures"]
                for kk, vv in r["pvs"].items():
                    if not kk.startswith("visits"):
                        tot["pvs_" + kk] += vv
            else:
                tot["tracks_skipped_" + tid_] += 1
        val["survey_all_tracks"] = {"totals": dict(tot), "prim_types": dict(prim), "source": str(sp)}
    (OUT / "VALIDATION.json").write_text(json.dumps(val, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
