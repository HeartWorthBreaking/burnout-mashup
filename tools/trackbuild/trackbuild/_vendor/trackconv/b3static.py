"""wm2_static - strict reader + layout writer for Xbox STATIC.DAT.

Games: "b3"  = Burnout 3 Takedown Xbox (version 0x27, 0x60-byte header)
       "rev" = Burnout Revenge Xbox (version 0x34, 0x64-byte header; its prop section is kept as an opaque, separately
               decoded block, because it has no B3 counterpart - see WM2_REPORT.md)

The reader decodes EVERY structure the game's relocation routine sub_0019B4E0 visits (Takedawn recompiled code, read only:
<generated code>, sub_0019B4E0 / sub_0019B4A0 / sub_0019B440, <generated code> sub_001C8E20) plus the data those pointers lead
to, into a game-neutral object (pointer fields removed, every other byte kept). The writer `build()` lays the object out
again from layout RULES only (offsets recomputed, never copied). A file is accepted when
  (1) every structural check passes (pointers inside the file, constants as in retail, no two structures overlap), and
  (2) build(parse(file)) == file byte for byte; bytes that no structure claims must be zero, except a recorded list of
      non-zero pad bytes (retail exporter garbage; counted and reported; build() writes them back only into its own pads).

Layout (both games, in file order; [x] = a pointer field of the header):
  header | [+0x18] u32 texture-record offsets | texture records at 0x80 multiples: 0x80-byte D3D record + texel chain
  (DXT1 8 B / DXT3, DXT5 16 B per 4x4 block, every mip level) | [+0x08] materials 0x28 B | their texture-offset arrays
  (u32, relative to the material) in material order | [+0x10] s16[+0x0E] (null when 0) | model-group sets in the order
  [+0x24] backdrop, [+0x2C], [+0x30], [+0x28] (entry arrays {s16 n, u16, u32 models rel entry}; models 0x60 B;
  per model: s16 material index per record, 0x90-B records, vertex block, u16 index runs) | [+0x38] instance models 0x70 B
  (LOD structs at +0x20 / +0x34 / +0x48 per flag byte +0x62 bit 0 / 1: {Common, Data rel struct, Lock, u32 index count,
  u32 index data rel struct}) and their vertex / index data | B3: [+0x3C] prop types (same record), [+0x44] u8[prop types],
  [+0x48] 0x40-B placement matrices x [+0x40], [+0x4C] per-unit u8[prop types] lists, [+0x50] per-unit u32[prop types]
  arrays of 4-B placement entries | [unit table] 16 B per unit | [afterUnits] | zero pad to the next 0x8000.

Game-specific bytes the object does NOT carry (written by build() per game):
  texture record tail  B3: +0x40 u32 0x20, +0x44 u32 (f32), +0x48 name[32], +0x68 u32 mip count, +0x6C..+0x7F 0
                       Rev: +0x40 u32 (f32), +0x44 name[32], +0x64 u32 (mips << 8 | bits per pixel), +0x68..+0x7F 0
  model +0x54 material-index pointer base: B3 the group entry, Rev the model (sub_0019B4A0; bolib.loaderfmt note)
Converted output is game-derived: LOCAL ONLY."""
import hashlib
import struct

B3_VER, REV_VER = 0x27, 0x34
TEX_BLOCK = {0x0C: 8, 0x0E: 16, 0x0F: 16}           # DXT1, DXT3, DXT5 (bytes per 4x4 block)
TEX_NAME = {0x0C: "DXT1", 0x0E: "DXT3", 0x0F: "DXT5"}
SET_ORDER = (0x24, 0x2C, 0x30, 0x28)                   # fixup order of sub_0019B4E0 = file order
SET_COUNT = {0x24: 0x1C, 0x28: 0x1E, 0x2C: 0x20, 0x30: 0x22}
SET_NAME = {0x24: "backdrop", 0x28: "chevron", 0x2C: "water", 0x30: "reflection"}
LOD_AT = (0x20, 0x34, 0x48)
REV_ONLY_MAT_BITS = 0x3000                             # material +0x24 bits Revenge sets, B3 retail never does


class StrictError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise StrictError(msg)


def al(x, a):
    return x + (-x) % a


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tex_size(fmt_word):
    """texel chain bytes for an Xbox D3D format word (DXT formats only; anything else is refused)"""
    code, mips = (fmt_word >> 8) & 0xFF, (fmt_word >> 16) & 0xF
    lw, lh = (fmt_word >> 20) & 0xF, (fmt_word >> 24) & 0xF
    bb = TEX_BLOCK.get(code)
    need(bb is not None, "texture format 0x%02X not a DXT format" % code)
    need(mips >= 1, "texture with 0 mip levels")
    n = 0
    for m in range(mips):
        w, h = max(1, (1 << lw) >> m), max(1, (1 << lh) >> m)
        n += ((w + 3) // 4) * ((h + 3) // 4) * bb
    return n


def tex_bpp(code):
    return 4 if code == 0x0C else 8


# ============================================================================================ reader
class _R:
    def __init__(self, d):
        self.d = d
        self.cov = bytearray(len(d))

    def u8(self, o):
        return self.d[o]

    def s16(self, o):
        return struct.unpack_from("<h", self.d, o)[0]

    def u16(self, o):
        return struct.unpack_from("<H", self.d, o)[0]

    def u32(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def take(self, o, n, what):
        need(0 <= o and o + n <= len(self.d), "%s: 0x%X+0x%X outside the file (0x%X)" % (what, o, n, len(self.d)))
        if n:
            need(not any(self.cov[o:o + n]), "%s at 0x%X overlaps another structure" % (what, o))
            self.cov[o:o + n] = b"\x01" * n
        return self.d[o:o + n]


def _zero(raw, *fields):
    b = bytearray(raw)
    for f in fields:
        b[f:f + 4] = bytes(4)
    return bytes(b)


def _parse_texture(r, t, game):
    hdr = r.take(t, 0x80, "texture record")
    common, data, lock, fw = struct.unpack_from("<4I", hdr, 0)
    need(common == 0x00040001, "texture 0x%X: Common 0x%X" % (t, common))
    need(data == 0x80, "texture 0x%X: Data 0x%X (texels not at +0x80)" % (t, data))
    need(lock == 0, "texture 0x%X: Lock not 0" % t)
    code, mips = (fw >> 8) & 0xFF, (fw >> 16) & 0xF
    need(struct.unpack_from("<I", hdr, 0x10)[0] == 0, "texture 0x%X: non-power-of-two Size word" % t)
    need(not any(hdr[0x14:0x34]), "texture 0x%X: sub-surface words +0x14..+0x33 not zero" % t)
    c34, w, h = struct.unpack_from("<3I", hdr, 0x34)
    need(c34 == code and w == 1 << ((fw >> 20) & 0xF) and h == 1 << ((fw >> 24) & 0xF),
         "texture 0x%X: +0x34 / +0x38 / +0x3C disagree with the format word" % t)
    if game == "b3":
        need(struct.unpack_from("<I", hdr, 0x40)[0] == 0x20, "texture 0x%X: B3 tail +0x40 != 0x20" % t)
        f, name = struct.unpack_from("<I", hdr, 0x44)[0], hdr[0x48:0x68]
        need(struct.unpack_from("<I", hdr, 0x68)[0] == mips, "texture 0x%X: B3 tail +0x68 != mip count %d" % (t, mips))
        need(not any(hdr[0x6C:0x80]), "texture 0x%X: B3 tail +0x6C..+0x7F not zero" % t)
    else:
        f, name = struct.unpack_from("<I", hdr, 0x40)[0], hdr[0x44:0x64]
        need(struct.unpack_from("<I", hdr, 0x64)[0] == (mips << 8 | tex_bpp(code)),
             "texture 0x%X: Rev tail +0x64 != mips << 8 | bpp" % t)
        need(not any(hdr[0x68:0x80]), "texture 0x%X: Rev tail +0x68..+0x7F not zero" % t)
    texels = r.take(t + 0x80, tex_size(fw), "texels")
    return {"d3d": _zero(hdr[0:0x40], 0x04), "f": f, "name": bytes(name), "texels": texels}


def _parse_mesh_set(r, base, what):
    """0x60 model at `base`: VB at +0x40, records at +0x4C (rel +0x40), count +0x50; returns (raw, recs, vtx, idx runs)"""
    vbc, vbd, vbl, ro = struct.unpack_from("<4I", r.d, base + 0x40)
    n = r.s16(base + 0x50)
    need(vbc == 1 and vbl == 0, "%s: vertex buffer header {%X, ., %X}" % (what, vbc, vbl))
    need(n > 0, "%s: %d records" % (what, n))
    rs = base + 0x40 + ro
    recs, runs = [], []
    for k in range(n):
        rec = r.take(rs + 0x90 * k, 0x90, what + " record")
        prim, cnt, rel = struct.unpack_from("<3I", rec, 0x80)
        recs.append(_zero(rec, 0x88))
        runs.append((rs + 0x90 * k + rel, cnt))
    vb = base + 0x40 + vbd
    first = min(a for a, c in runs)
    need(first > vb, "%s: index runs before the vertices" % what)
    vtx = r.take(vb, first - vb, what + " vertices")
    idx = [r.take(a, 2 * c, what + " index run") for a, c in runs]
    return rs, vb, recs, vtx, idx, runs


def _parse_lodrec(r, rec_off, what):
    """instance / prop-type record 0x70 -> (raw, lods, starts)"""
    raw = r.take(rec_off, 0x70, what)
    fl = raw[0x62]
    lods, starts = [], []
    zf = []
    for k, lo in enumerate(LOD_AT):
        if k == 0 or (k == 1 and fl & 1) or (k == 2 and fl & 2):
            s = rec_off + lo
            com, dat, lock, cnt, ip = struct.unpack_from("<5I", r.d, s)
            need(com == 1 and lock == 0, "%s LOD%d: vertex buffer header" % (what, k))
            vb, ib = s + dat, s + ip
            need(ib > vb, "%s LOD%d: index data before the vertices" % (what, k))
            vtx = r.take(vb, ib - vb, what + " vertices")
            idx = r.take(ib, 2 * cnt, what + " indices")
            lods.append({"vtx": vtx, "idx": idx})
            starts.append((vb, ib))
            zf += [lo + 4, lo + 0x10]
    return {"raw": _zero(raw, *zf), "lods": lods}, starts


class Diag:
    def __init__(self):
        self.rules = []

    def rule(self, ok, msg):
        if not ok and len(self.rules) < 40:
            self.rules.append(msg)


def parse(d, game):
    """-> (object, diag). Raises StrictError on any structural problem."""
    r = _R(d)
    dg = Diag()
    hsz = 0x60 if game == "b3" else 0x64
    need(len(d) >= hsz, "file too small")
    hdr = r.take(0, hsz, "header")
    u32, s16 = r.u32, r.s16
    ver = u32(0)
    need(ver == (B3_VER if game == "b3" else REV_VER), "version 0x%X is not %s" % (ver, game))
    o = {"game": game, "w14": r.u16(0x14)}
    if game == "b3":
        need(u32(4) == len(d), "B3 size field 0x%X != file size 0x%X" % (u32(4), len(d)))
    else:
        need(u32(4) == 0, "Rev size field not 0")
    cur = hsz
    # ---- textures
    ntex, ta = s16(0x16), u32(0x18)
    need(ntex >= 0, "negative texture count")
    dg.rule(ta == cur, "texture array at 0x%X, rule 0x%X" % (ta, cur))
    offs = struct.unpack_from("<%dI" % ntex, r.take(ta, 4 * ntex, "texture array"), 0) if ntex else ()
    cur = ta + 4 * ntex
    o["textures"] = []
    tex_index = {}
    for i, t in enumerate(offs):
        dg.rule(t == al(cur, 0x80), "texture %d at 0x%X, rule 0x%X" % (i, t, al(cur, 0x80)))
        tex_index[t] = i
        o["textures"].append(_parse_texture(r, t, game))
        cur = t + 0x80 + len(o["textures"][-1]["texels"])
    # ---- materials
    nmat, mt = s16(0xC), u32(0x8)
    dg.rule(mt == cur, "materials at 0x%X, rule 0x%X" % (mt, cur))
    o["materials"] = []
    arrs = []
    for i in range(nmat):
        m = mt + 0x28 * i
        raw = r.take(m, 0x28, "material")
        a, cnt = struct.unpack_from("<I", raw, 0xC)[0], struct.unpack_from("<b", raw, 0x11)[0]
        texs = None
        if game == "b3":
            need(not struct.unpack_from("<I", raw, 0x24)[0] & REV_ONLY_MAT_BITS,
                 "material %d: +0x24 carries the Revenge-only bits 0x3000 (never set in B3 retail)" % i)
        if a:
            need(cnt >= 0, "material %d: negative texture count with an array" % i)
            arrs.append((m + a, cnt))
            texs = []
            for k in range(cnt):
                e = (r.u32(m + a + 4 * k) + m) & 0xFFFFFFFF
                need(e in tex_index, "material %d texture %d: 0x%X is not a texture record" % (i, k, e))
                texs.append(tex_index[e])
        o["materials"].append({"raw": _zero(raw, 0x0C), "tex": texs})
    cur = mt + 0x28 * nmat
    for a, cnt in arrs:
        dg.rule(a == cur, "material texture array at 0x%X, rule 0x%X" % (a, cur))
        r.take(a, 4 * cnt, "material texture array")
        cur = a + 4 * cnt
    # ---- animated-material indices
    nan, an = s16(0xE), u32(0x10)
    need(nan >= 0, "negative +0x0E")
    dg.rule((an == 0) == (nan == 0), "+0x10 null-ness vs +0x0E count")
    if nan:
        dg.rule(an == cur, "+0x10 array at 0x%X, rule 0x%X" % (an, cur))
        o["anim"] = list(struct.unpack_from("<%dh" % nan, r.take(an, 2 * nan, "+0x10 array"), 0))
        cur = an + 2 * nan
    else:
        o["anim"] = []
    # ---- model-group sets
    o["sets"] = {}
    for so in SET_ORDER:
        n, ga = s16(SET_COUNT[so]), u32(so)
        need(n >= 0, "negative set count")
        dg.rule(ga == al(cur, 4), "%s set at 0x%X, rule 0x%X" % (SET_NAME[so], ga, al(cur, 4)))
        need(ga != 0 or n == 0, "%s set null with entries" % SET_NAME[so])
        ents = []
        cur = ga + 8 * n
        ent_raw = r.take(ga, 8 * n, "group entries") if n else b""
        for g in range(n):
            e = ga + 8 * g
            cnt, w2, rel = struct.unpack_from("<hHI", ent_raw, 8 * g)
            need(cnt > 0, "%s entry %d: %d models" % (SET_NAME[so], g, cnt))
            mods = e + rel
            dg.rule(mods == al(cur, 16), "%s entry %d models at 0x%X, rule 0x%X" % (SET_NAME[so], g, mods, al(cur, 16)))
            cur = mods + 0x60 * cnt
            models = []
            raws = r.take(mods, 0x60 * cnt, "models")
            for j in range(cnt):
                m = mods + 0x60 * j
                what = "%s[%d].model[%d]" % (SET_NAME[so], g, j)
                raw = raws[0x60 * j:0x60 * j + 0x60]
                need(not any(raw[0x58:0x60]), what + ": +0x58 / +0x5C not zero")
                need(raw[0x52:0x54] == b"\0\0", what + ": +0x52 not zero")
                nrec = struct.unpack_from("<h", raw, 0x50)[0]
                mp = struct.unpack_from("<I", raw, 0x54)[0]
                mi = None
                if mp:
                    mia = ((e if game == "b3" else m) + mp) & 0xFFFFFFFF
                    rule_mi = al(cur, 4) if j else cur
                    dg.rule(mia == rule_mi, "%s matidx at 0x%X, rule 0x%X" % (what, mia, rule_mi))
                    mi = list(struct.unpack_from("<%dh" % nrec, r.take(mia, 2 * nrec, what + " matidx"), 0))
                    cur = mia + 2 * nrec
                rs, vb, recs, vtx, idx, runs = _parse_mesh_set(r, m, what)
                dg.rule(rs == al(cur, 16), "%s records at 0x%X, rule 0x%X" % (what, rs, al(cur, 16)))
                dg.rule(vb == rs + 0x90 * nrec, "%s vertices not right after the records" % what)
                c = vb + len(vtx)
                for k, (a, cn) in enumerate(runs):
                    rule_a = al(c, 4) if k else c
                    dg.rule(a == rule_a, "%s run %d at 0x%X, rule 0x%X" % (what, k, a, rule_a))
                    c = a + 2 * cn
                cur = c
                models.append({"raw": _zero(raw, 0x44, 0x4C, 0x54), "mi": mi, "recs": recs, "vtx": vtx, "idx": idx})
            ents.append({"w2": w2, "models": models})
        o["sets"][so] = ents
    # ---- instance models (+0x38) and B3 prop types (+0x3C)
    def lodrecs(arr_f, cnt_f, what, cur):
        n, a = s16(cnt_f), u32(arr_f)
        need(n >= 0, "negative %s count" % what)
        dg.rule((a == 0) == (n == 0), "%s pointer null-ness vs count" % what)
        out = []
        if not n:
            return out, cur
        dg.rule(a == al(cur, 16), "%s array at 0x%X, rule 0x%X" % (what, a, al(cur, 16)))
        cur = a + 0x70 * n
        for i in range(n):
            ob, starts = _parse_lodrec(r, a + 0x70 * i, "%s[%d]" % (what, i))
            for k, (vb, ib) in enumerate(starts):
                dg.rule(vb == al(cur, 4), "%s[%d] LOD%d vertices at 0x%X, rule 0x%X" % (what, i, k, vb, al(cur, 4)))
                cur = ib + len(ob["lods"][k]["idx"])
            out.append(ob)
        return out, cur
    o["instances"], cur = lodrecs(0x38, 0x34, "instance", cur)
    if game == "b3":
        o["proptypes"], cur = lodrecs(0x3C, 0x36, "prop type", cur)
        npt, nunit = s16(0x36), s16(0x54)
        need(nunit >= 0, "negative unit count")
        o["w56"] = r.u16(0x56)
        p44 = u32(0x44)
        dg.rule(p44 == cur, "+0x44 at 0x%X, rule 0x%X" % (p44, cur))
        o["pbytes"] = r.take(p44, npt, "+0x44 bytes")
        cur = p44 + npt
        nplace, p48 = u32(0x40), u32(0x48)
        dg.rule(p48 == al(cur, 16), "+0x48 matrices at 0x%X, rule 0x%X" % (p48, al(cur, 16)))
        mats = r.take(p48, 0x40 * nplace, "placement matrices")
        o["matrices"] = [mats[0x40 * i:0x40 * i + 0x40] for i in range(nplace)]
        cur = p48 + 0x40 * nplace
        p4c = u32(0x4C)
        dg.rule(p4c == cur, "+0x4C at 0x%X, rule 0x%X" % (p4c, cur))
        ptrs = struct.unpack_from("<%dI" % nunit, r.take(p4c, 4 * nunit, "+0x4C array"), 0) if nunit else ()
        cur = p4c + 4 * nunit
        o["ucounts"] = []
        for u, q in enumerate(ptrs):
            if q == 0:
                o["ucounts"].append(None)
                continue
            dg.rule(q == cur, "+0x4C[%d] at 0x%X, rule 0x%X" % (u, q, cur))
            o["ucounts"].append(r.take(q, npt, "+0x4C list"))
            cur = q + npt
        p50 = u32(0x50)
        dg.rule(p50 == al(cur, 4), "+0x50 at 0x%X, rule 0x%X" % (p50, al(cur, 4)))
        ptrs = struct.unpack_from("<%dI" % nunit, r.take(p50, 4 * nunit, "+0x50 array"), 0) if nunit else ()
        cur = p50 + 4 * nunit
        o["ulists"] = []
        for u, q in enumerate(ptrs):
            if q == 0:
                o["ulists"].append(None)
                continue
            dg.rule(q == cur, "+0x50[%d] at 0x%X, rule 0x%X" % (u, q, cur))
            sub = struct.unpack_from("<%dI" % npt, r.take(q, 4 * npt, "+0x50 pointer array"), 0) if npt else ()
            cur = q + 4 * npt
            cnts = o["ucounts"][u]
            need(cnts is not None or not any(sub), "+0x50[%d] lists without +0x4C counts" % u)
            lists = []
            for k, x in enumerate(sub):
                if x == 0:
                    need(cnts is None or cnts[k] == 0, "+0x50[%d][%d] null with count %d" % (u, k, cnts[k]))
                    lists.append(None)
                    continue
                need(cnts[k] > 0, "+0x50[%d][%d] list with count 0" % (u, k))
                dg.rule(x == cur, "+0x50[%d][%d] at 0x%X, rule 0x%X" % (u, k, x, cur))
                lists.append(r.take(x, 4 * cnts[k], "+0x50 list"))
                cur = x + 4 * cnts[k]
            o["ulists"].append(lists)
        ut, after = u32(0x58), u32(0x5C)
    else:
        need(s16(0x36) == 0, "Rev +0x36 not 0")
        need(u32(0x50) == 0 and u32(0x54) == 0, "Rev +0x50 / +0x54 (static collision) not 0")
        nunit = s16(0x58)
        o["w56"] = r.u16(0x5A)
        pa, nprops, phys = u32(0x3C), u32(0x40), u32(0x4C)
        o["revprops"] = None
        if pa:
            dg.rule(pa == al(cur, 16), "Rev props at 0x%X, rule 0x%X" % (pa, al(cur, 16)))
            need(phys > pa, "Rev prop physics not after the prop records")
            blob = r.take(pa, phys - pa, "Rev prop records + LOD data")
            ph = r.take(phys, 0xB8 * nprops, "Rev prop physics")
            o["revprops"] = {"nprops": nprops, "w44": u32(0x44), "nspawn": u32(0x48), "blob": blob, "phys": ph,
                             "blob_at": pa}
            cur = phys + 0xB8 * nprops
        else:
            need(nprops == 0 and phys == 0 and u32(0x44) == 0 and u32(0x48) == 0, "Rev prop fields without props")
        ut, after = u32(0x5C), u32(0x60)
    dg.rule(ut == al(cur, 4), "unit table at 0x%X, rule 0x%X" % (ut, al(cur, 4)))
    tab = r.take(ut, 16 * nunit, "unit table")
    o["units"] = [struct.unpack_from("<4I", tab, 16 * i) for i in range(nunit)]
    cur = ut + 16 * nunit
    dg.rule(after == cur, "afterUnits 0x%X, rule 0x%X" % (after, cur))
    dg.rule(len(d) == al(max(after, 1), 0x8000), "file size 0x%X, rule 0x%X" % (len(d), al(after, 0x8000)))
    # bytes no structure claims
    garbage = []
    k, n = 0, len(d)
    cov = r.cov
    while k < n:
        if not cov[k] and d[k]:
            j = k
            while j < n and not cov[j] and d[j]:
                j += 1
            garbage.append((k, d[k:j]))
            k = j
        else:
            k += 1
    o["garbage"] = garbage
    o["claimed"] = sum(cov)
    return o, dg


# ============================================================================================ writer
class _W:
    def __init__(self):
        self.b = bytearray()
        self.cov = bytearray()

    def put(self, off, data):
        end = off + len(data)
        if len(self.b) < end:
            self.b.extend(bytes(end - len(self.b)))
            self.cov.extend(bytes(end - len(self.cov)))
        need(not any(self.cov[off:end]), "writer: overlap at 0x%X" % off)
        self.b[off:end] = data
        self.cov[off:end] = b"\x01" * len(data)

    def p32(self, off, v):
        struct.pack_into("<I", self.b, off, v & 0xFFFFFFFF)


def _tex_record(t, game):
    h = bytearray(0x80)
    h[0:0x40] = t["d3d"]
    struct.pack_into("<I", h, 0x04, 0x80)
    fw = struct.unpack_from("<I", h, 0x0C)[0]
    code, mips = (fw >> 8) & 0xFF, (fw >> 16) & 0xF
    if game == "b3":
        struct.pack_into("<II", h, 0x40, 0x20, t["f"])
        h[0x48:0x68] = t["name"]
        struct.pack_into("<I", h, 0x68, mips)
    else:
        struct.pack_into("<I", h, 0x40, t["f"])
        h[0x44:0x64] = t["name"]
        struct.pack_into("<I", h, 0x64, mips << 8 | tex_bpp(code))
    return bytes(h)


def build(o, game, opts=None):
    """lay the object out by the layout rules -> bytes. `opts` (negative controls only): {"matidx_base": "model"|"entry",
    "tail": "rev"|"b3" (texture-record tail layout)}"""
    opts = opts or {}
    w = _W()
    hsz = 0x60 if game == "b3" else 0x64
    H = bytearray(hsz)
    w.put(0, bytes(hsz))
    cur = hsz
    struct.pack_into("<I", H, 0, B3_VER if game == "b3" else REV_VER)
    struct.pack_into("<H", H, 0x14, o["w14"])
    # textures
    tx = o["textures"]
    struct.pack_into("<hI", H, 0x16, len(tx), cur if tx else 0)
    ta = cur
    cur += 4 * len(tx)
    toff = []
    for t in tx:
        rec = al(cur, 0x80)
        toff.append(rec)
        w.put(rec, _tex_record(t, opts.get("tail", game)))
        w.put(rec + 0x80, t["texels"])
        cur = rec + 0x80 + len(t["texels"])
    if tx:
        w.put(ta, struct.pack("<%dI" % len(tx), *toff))
    # materials
    mt = cur
    struct.pack_into("<IhH", H, 0x08, mt, len(o["materials"]), len(o["anim"]))
    cur = mt + 0x28 * len(o["materials"])
    for i, m in enumerate(o["materials"]):
        raw = bytearray(m["raw"])
        mo = mt + 0x28 * i
        if m["tex"] is not None:
            struct.pack_into("<I", raw, 0x0C, cur - mo)
            w.put(cur, b"".join(struct.pack("<I", (toff[k] - mo) & 0xFFFFFFFF) for k in m["tex"]))
            cur += 4 * len(m["tex"])
        w.put(mo, bytes(raw))
    if o["anim"]:
        struct.pack_into("<I", H, 0x10, cur)
        w.put(cur, struct.pack("<%dh" % len(o["anim"]), *o["anim"]))
        cur += 2 * len(o["anim"])
    # model-group sets
    base_rule = opts.get("matidx_base", "entry" if game == "b3" else "model")
    for so in SET_ORDER:
        ents = o["sets"][so]
        ga = al(cur, 4)
        struct.pack_into("<I", H, so, ga)
        struct.pack_into("<h", H, SET_COUNT[so], len(ents))
        cur = ga + 8 * len(ents)
        etab = bytearray(8 * len(ents))
        for g, ent in enumerate(ents):
            e = ga + 8 * g
            mods = al(cur, 16)
            struct.pack_into("<hHI", etab, 8 * g, len(ent["models"]), ent["w2"], mods - e)
            cur = mods + 0x60 * len(ent["models"])
            for j, md in enumerate(ent["models"]):
                m = mods + 0x60 * j
                raw = bytearray(md["raw"])
                if md["mi"] is not None:
                    mia = al(cur, 4) if j else cur
                    struct.pack_into("<I", raw, 0x54, (mia - (e if base_rule == "entry" else m)) & 0xFFFFFFFF)
                    w.put(mia, struct.pack("<%dh" % len(md["mi"]), *md["mi"]))
                    cur = mia + 2 * len(md["mi"])
                rs = al(cur, 16)
                vb = rs + 0x90 * len(md["recs"])
                struct.pack_into("<I", raw, 0x44, vb - (m + 0x40))
                struct.pack_into("<I", raw, 0x4C, rs - (m + 0x40))
                w.put(vb, md["vtx"])
                c = vb + len(md["vtx"])
                for k, (rec, ix) in enumerate(zip(md["recs"], md["idx"])):
                    a = al(c, 4) if k else c
                    rr = bytearray(rec)
                    struct.pack_into("<I", rr, 0x88, a - (rs + 0x90 * k))
                    w.put(rs + 0x90 * k, bytes(rr))
                    w.put(a, ix)
                    c = a + len(ix)
                cur = c
                w.put(m, bytes(raw))
        if ents:
            w.put(ga, bytes(etab))

    def lodrecs(lst, arr_f, cnt_f, cur):
        struct.pack_into("<h", H, cnt_f, len(lst))
        if not lst:
            struct.pack_into("<I", H, arr_f, 0)
            return cur
        a = al(cur, 16)
        struct.pack_into("<I", H, arr_f, a)
        cur = a + 0x70 * len(lst)
        for i, ob in enumerate(lst):
            ro = a + 0x70 * i
            raw = bytearray(ob["raw"])
            fl = raw[0x62]
            present = [k for k in range(3) if k == 0 or (k == 1 and fl & 1) or (k == 2 and fl & 2)]
            need(len(present) == len(ob["lods"]), "writer: LOD count does not match the flag byte")
            for k, ld in zip(present, ob["lods"]):
                s = ro + LOD_AT[k]
                vb = al(cur, 4)
                ib = vb + len(ld["vtx"])
                struct.pack_into("<I", raw, LOD_AT[k] + 4, vb - s)
                struct.pack_into("<I", raw, LOD_AT[k] + 0x10, ib - s)
                w.put(vb, ld["vtx"])
                w.put(ib, ld["idx"])
                cur = ib + len(ld["idx"])
            w.put(ro, bytes(raw))
        return cur
    cur = lodrecs(o["instances"], 0x38, 0x34, cur)
    if game == "b3":
        cur = lodrecs(o["proptypes"], 0x3C, 0x36, cur)
        npt = len(o["proptypes"])
        need(len(o["pbytes"]) == npt, "writer: +0x44 bytes != prop types")
        nunit = len(o["units"])
        need(len(o["ucounts"]) == nunit and len(o["ulists"]) == nunit, "writer: per-unit lists != unit count")
        struct.pack_into("<I", H, 0x44, cur)
        w.put(cur, o["pbytes"])
        cur += npt
        p48 = al(cur, 16)
        struct.pack_into("<I", H, 0x40, len(o["matrices"]))
        struct.pack_into("<I", H, 0x48, p48)
        w.put(p48, b"".join(o["matrices"]))
        cur = p48 + 0x40 * len(o["matrices"])
        p4c = cur
        struct.pack_into("<I", H, 0x4C, p4c)
        cur += 4 * nunit
        ptrs = []
        for c in o["ucounts"]:
            if c is None:
                ptrs.append(0)
                continue
            need(len(c) == npt, "writer: +0x4C list length != prop types")
            ptrs.append(cur)
            w.put(cur, c)
            cur += npt
        w.put(p4c, struct.pack("<%dI" % nunit, *ptrs))
        p50 = al(cur, 4)
        struct.pack_into("<I", H, 0x50, p50)
        cur = p50 + 4 * nunit
        ptrs = []
        for u, lists in enumerate(o["ulists"]):
            if lists is None:
                ptrs.append(0)
                continue
            q = cur
            ptrs.append(q)
            cur = q + 4 * npt
            sub = []
            for k, lst in enumerate(lists):
                if lst is None:
                    sub.append(0)
                    continue
                sub.append(cur)
                w.put(cur, lst)
                cur += len(lst)
            w.put(q, struct.pack("<%dI" % npt, *sub))
        w.put(p50, struct.pack("<%dI" % nunit, *ptrs))
        struct.pack_into("<hH", H, 0x54, nunit, o["w56"])
        ut_f, after_f = 0x58, 0x5C
    else:
        rp = o.get("revprops")
        if rp:
            pa = al(cur, 16)
            phys = pa + len(rp["blob"])
            struct.pack_into("<5I", H, 0x3C, pa, rp["nprops"], rp["w44"], rp["nspawn"], phys)
            need(rp["blob_at"] == pa, "writer: Rev prop block would move (its internal pointers are not decoded)")
            w.put(pa, rp["blob"])
            w.put(phys, rp["phys"])
            cur = phys + len(rp["phys"])
        struct.pack_into("<hH", H, 0x58, len(o["units"]), o["w56"])
        ut_f, after_f = 0x5C, 0x60
    ut = al(cur, 4)
    w.put(ut, b"".join(struct.pack("<4I", *e) for e in o["units"]))
    cur = ut + 16 * len(o["units"])
    struct.pack_into("<II", H, ut_f, ut, cur)
    size = al(max(cur, 1), 0x8000)
    if game == "b3":
        struct.pack_into("<I", H, 0x04, size)
    w.cov[0:hsz] = bytes(hsz)
    w.put(0, bytes(H))
    if len(w.b) < size:
        w.b.extend(bytes(size - len(w.b)))
        w.cov.extend(bytes(size - len(w.cov)))
    for off, g in o.get("garbage", ()):
        need(off + len(g) <= size and not any(w.cov[off:off + len(g)]), "writer: recorded pad bytes fall on a structure")
        w.b[off:off + len(g)] = g
    need(len(w.b) == size, "writer: data beyond the computed size")
    return bytes(w.b)


def identity(d, game):
    """strict parse + rebuild -> (ok, info dict)"""
    o, dg = parse(d, game)
    out = build(o, game)
    ok = out == d and not dg.rules
    first = next((i for i in range(min(len(out), len(d))) if out[i] != d[i]), None) if out != d else None
    return ok, {"rule_mismatches": dg.rules[:5], "n_rule_mismatches": len(dg.rules), "identical": out == d,
                "first_diff": None if first is None else "0x%X" % first, "garbage_bytes": sum(len(g) for _, g in o["garbage"]),
                "garbage_spans": len(o["garbage"]), "claimed": o["claimed"], "size": len(d)}, o
