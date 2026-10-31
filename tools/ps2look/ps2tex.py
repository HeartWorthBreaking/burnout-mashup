"""ps2look: read-only decoder for Burnout 3 PS2 texture dictionaries (DATA/GLOBAL.TXD of the user's own disc).
Pure Python 3 (standard library only). Writes nothing.

TEXDIC (PS2 FE-X2b inventory_b3.py / map_codec.py): u32 count at +8, u32 table offset at +0xC, 16-byte rows with the record
offset at row +8. Record (offsets self-relative): +4 pixel data, +8 palette data, +0xC width, +0x10 height, +0x14 bpp,
+0x3C TEX0 (u64), +0xA8 name (NUL-terminated). Each pixel block is preceded by its GIF upload packet (A+D tag NLOOP 3 at
pix-0x50: TRXPOS, TRXREG (w, h at pix-0x30), TRXDIR, then the IMAGE tag at pix-0x10); the decoder checks it so another disc layout fails loudly.

Formats handled (the four C3.9 textures; others are refused):
  PSMCT32 (TEX0 PSM 0x00, bpp 32): uploaded as CT32 w x h -> raster order, bytes R, G, B, A.
  PSMT8 (0x13, bpp 8): uploaded as CT32 (w/2) x (h/2); unswizzle = map_codec.unswizzle8 (PS2 fe_x2b, runtime-verified in
    B3C-1c); CLUT 256 x CT32 in CSM1 order (index bits 3 / 4 swapped).
  PSMT4 (0x14, bpp 4): uploaded as CT16 (w/2) x (h/2), sampled as T4 through the GS memory model (tables = gsmem.py of
    PS2 retex_2026_10_19, the standard GS block / column tables); CLUT 16 x CT32, CSM1 8 x 2 = linear order.
Alpha: the PS2 stores 0..0x80 (0x80 = 1.0); converted by the project's established rule a8 = min(255, 2 * a)
(map_codec.py / texdecode.view / C3.9 c3_9_compare.py). RGB 0..255 as stored (texture RGB is not 0x80-scaled)."""
import struct

TEX_MAGIC = 0x543C0000
ALPHA_RULE = 'a8 = min(255, 2 * a_ps2)  (PS2 alpha 0..0x80; map_codec.py / texdecode.view rule)'


class Ps2TexError(ValueError):
    pass


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def alpha8(a):
    return min(255, 2 * a)


# ----------------------------------------------------------------------------------------------- swizzle tables

def _psmt8_map(w, h):
    """linear y*w+x -> byte position in the CT32-uploaded PSMT8 buffer (= map_codec._swz_map)"""
    m = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            block = (y & ~0xF) * w + (x & ~0xF) * 2
            swap = (((y + 2) >> 2) & 1) * 4
            py = (((y & ~3) >> 1) + (y & 1)) & 7
            col = py * w * 2 + ((x + swap) & 7) * 4
            byte = ((y >> 1) & 1) + ((x >> 2) & 2)
            m[y * w + x] = block + col + byte
    return m


def csm1(i):
    return (i & 0xE7) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)


BLOCK16 = [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15], [16, 18, 24, 26], [17, 19, 25, 27], [20, 22, 28, 30],
           [21, 23, 29, 31]]
BLOCK4 = BLOCK16
COL16 = [[0, 2, 8, 10, 16, 18, 24, 26, 1, 3, 9, 11, 17, 19, 25, 27], [4, 6, 12, 14, 20, 22, 28, 30, 5, 7, 13, 15, 21, 23, 29, 31],
         [32, 34, 40, 42, 48, 50, 56, 58, 33, 35, 41, 43, 49, 51, 57, 59], [36, 38, 44, 46, 52, 54, 60, 62, 37, 39, 45, 47, 53, 55, 61, 63],
         [64, 66, 72, 74, 80, 82, 88, 90, 65, 67, 73, 75, 81, 83, 89, 91], [68, 70, 76, 78, 84, 86, 92, 94, 69, 71, 77, 79, 85, 87, 93, 95],
         [96, 98, 104, 106, 112, 114, 120, 122, 97, 99, 105, 107, 113, 115, 121, 123],
         [100, 102, 108, 110, 116, 118, 124, 126, 101, 103, 109, 111, 117, 119, 125, 127]]
_COL4_TOP = [
    [0, 8, 32, 40, 64, 72, 96, 104, 2, 10, 34, 42, 66, 74, 98, 106, 4, 12, 36, 44, 68, 76, 100, 108, 6, 14, 38, 46, 70, 78, 102, 110],
    [16, 24, 48, 56, 80, 88, 112, 120, 18, 26, 50, 58, 82, 90, 114, 122, 20, 28, 52, 60, 84, 92, 116, 124, 22, 30, 54, 62, 86, 94, 118, 126],
    [65, 73, 97, 105, 1, 9, 33, 41, 67, 75, 99, 107, 3, 11, 35, 43, 69, 77, 101, 109, 5, 13, 37, 45, 71, 79, 103, 111, 7, 15, 39, 47],
    [81, 89, 113, 121, 17, 25, 49, 57, 83, 91, 115, 123, 19, 27, 51, 59, 85, 93, 117, 125, 21, 29, 53, 61, 87, 95, 119, 127, 23, 31, 55, 63],
    [192, 200, 224, 232, 128, 136, 160, 168, 194, 202, 226, 234, 130, 138, 162, 170, 196, 204, 228, 236, 132, 140, 164, 172, 198, 206, 230,
     238, 134, 142, 166, 174],
    [208, 216, 240, 248, 144, 152, 176, 184, 210, 218, 242, 250, 146, 154, 178, 186, 212, 220, 244, 252, 148, 156, 180, 188, 214, 222, 246,
     254, 150, 158, 182, 190],
    [129, 137, 161, 169, 193, 201, 225, 233, 131, 139, 163, 171, 195, 203, 227, 235, 133, 141, 165, 173, 197, 205, 229, 237, 135, 143, 167,
     175, 199, 207, 231, 239],
    [145, 153, 177, 185, 209, 217, 241, 249, 147, 155, 179, 187, 211, 219, 243, 251, 149, 157, 181, 189, 213, 221, 245, 253, 151, 159, 183,
     191, 215, 223, 247, 255]]
COL4 = _COL4_TOP + [[v + 256 for v in row] for row in _COL4_TOP]


def _a16(bw, x, y):
    """CT16 byte address (bp 0, bw in 64-pixel units)"""
    page = (x >> 6) + (y >> 6) * bw
    blk = page * 32 + BLOCK16[(y >> 3) & 7][(x >> 4) & 3]
    return (blk * 128 + COL16[y & 7][x & 15]) * 2


def _a4(bw, x, y):
    """T4 nibble address (bp 0, bw in 64-pixel units)"""
    page = (x >> 7) + (y >> 7) * (bw >> 1)
    blk = page * 32 + BLOCK4[(y >> 4) & 7][(x >> 5) & 3]
    return blk * 512 + COL4[y & 15][x & 31]


def psmt4_from_ct16(data, uw, uh, w, h, tbw):
    """replay a CT16 uw x uh host->local upload (DBW 1 page) and sample it as PSMT4 w x h (TBW tbw) -> w*h indices"""
    dbw = max(1, (uw + 63) // 64)
    size = max(_a16(dbw, uw - 1, uh - 1), 0) + 2
    for y in range(h):
        for x in range(w):
            size = max(size, (_a4(max(tbw, 2), x, y) >> 1) + 1)
    mem = bytearray(size)
    p = 0
    for y in range(uh):
        for x in range(uw):
            a = _a16(dbw, x, y)
            mem[a:a + 2] = data[p:p + 2]
            p += 2
    out = []
    for y in range(h):
        for x in range(w):
            n = _a4(max(tbw, 2), x, y)
            v = mem[n >> 1]
            out.append((v >> 4) if n & 1 else (v & 0xF))
    return out


# ----------------------------------------------------------------------------------------------- dictionary

class Ps2Tex:
    """one decoded texture: name, w, h, psm, rgba [(r, g, b, a8)], raw indices + raw palette (CLUT formats)"""

    def __init__(self, name, w, h, psm, rgba, indices=None, palette=None, info=None):
        self.name, self.w, self.h, self.psm, self.rgba = name, w, h, psm, rgba
        self.indices, self.palette, self.info = indices, palette, info or {}


def records(b):
    """-> [(name, record offset)] of a PS2 B3 TEXDIC"""
    if len(b) < 0x10 or u32(b, 0) != TEX_MAGIC:
        raise Ps2TexError('not a PS2 Burnout 3 texture dictionary (magic %08X)' % (u32(b, 0) if len(b) >= 4 else 0))
    n, tb = u32(b, 8), u32(b, 0xC)
    if not 1 <= n <= 4096 or tb + 16 * n > len(b):
        raise Ps2TexError('texture table out of range (count %d at 0x%X)' % (n, tb))
    out = []
    for i in range(n):
        rec = u32(b, tb + 16 * i + 8)
        if rec + 0xE8 > len(b):
            raise Ps2TexError('record %d at 0x%X past the file' % (i, rec))
        end = b.find(b'\0', rec + 0xA8, rec + 0xE8)
        out.append((b[rec + 0xA8:end if end > 0 else rec + 0xE8].decode('latin1'), rec))
    return out


def _upload(b, pix):
    """the GIF A+D upload in front of a pixel block -> (trx w, trx h, image bytes)"""
    ad = struct.unpack_from('<QQ', b, pix - 0x50)
    if (ad[0] & 0x7FFF, ad[1]) != (3, 0xE) or u32(b, pix - 0x38) != 0x51 or u32(b, pix - 0x28) != 0x52 or \
            u32(b, pix - 0x18) != 0x53:
        raise Ps2TexError('no A+D TRXPOS / TRXREG / TRXDIR packet in front of the pixels at 0x%X' % pix)
    tw, th = u32(b, pix - 0x30), u32(b, pix - 0x2C)
    tag = struct.unpack_from('<Q', b, pix - 0x10)[0]
    if (tag >> 58) & 3 != 2:
        raise Ps2TexError('pixels at 0x%X are not behind a GIF IMAGE tag' % pix)
    return tw, th, (tag & 0x7FFF) * 16


def decode_record(b, name, rec):
    w, h, bpp = u32(b, rec + 0xC), u32(b, rec + 0x10), u32(b, rec + 0x14)
    pix, pal = rec + u32(b, rec + 4), rec + u32(b, rec + 8)
    t0 = struct.unpack_from('<Q', b, rec + 0x3C)[0]
    psm, tbw, tcc = (t0 >> 20) & 0x3F, (t0 >> 14) & 0x3F, (t0 >> 34) & 1
    cpsm, csm, csa = (t0 >> 51) & 0xF, (t0 >> 55) & 1, (t0 >> 56) & 0x1F
    if (1 << ((t0 >> 26) & 0xF), 1 << ((t0 >> 30) & 0xF)) != (w, h):
        raise Ps2TexError('%s: TEX0 size != record size %dx%d' % (name, w, h))
    if not tcc:
        raise Ps2TexError('%s: TEX0 TCC 0 (RGB only) not handled' % name)
    npix = w * h * bpp // 8
    if pix + npix > len(b):
        raise Ps2TexError('%s: pixels past the file' % name)
    uw, uh, ubytes = _upload(b, pix)
    info = dict(record=rec, psm=psm, bpp=bpp, tbw=tbw, upload=(uw, uh, ubytes))
    data = b[pix:pix + npix]
    if psm == 0x00 and bpp == 32:
        if (uw, uh, ubytes) != (w, h, npix):
            raise Ps2TexError('%s: CT32 upload %dx%d / %d bytes off the %dx%d layout' % (name, uw, uh, ubytes, w, h))
        raw = [tuple(data[4 * k:4 * k + 4]) for k in range(w * h)]
        if max(p[3] for p in raw) > 0x80:
            raise Ps2TexError('%s: alpha above 0x80' % name)
        return Ps2Tex(name, w, h, psm, [p[:3] + (alpha8(p[3]),) for p in raw], info=info)
    if cpsm != 0 or csm != 0 or csa != 0:
        raise Ps2TexError('%s: CLUT CPSM %d / CSM %d / CSA %d not handled' % (name, cpsm, csm, csa))
    if psm == 0x13 and bpp == 8:
        if (uw, uh, ubytes) != (w // 2, h // 2, npix):
            raise Ps2TexError('%s: PSMT8 upload %dx%d / %d bytes is not CT32 (w/2) x (h/2)' % (name, uw, uh, ubytes))
        m = _psmt8_map(w, h)
        idx = [data[m[i]] for i in range(w * h)]
        rawpal = [tuple(b[pal + 4 * k:pal + 4 * k + 4]) for k in range(256)]
        logical = [rawpal[csm1(i)] for i in range(256)]
    elif psm == 0x14 and bpp == 4:
        if (uw, uh, ubytes) != (w // 2, h // 2, npix):
            raise Ps2TexError('%s: PSMT4 upload %dx%d / %d bytes is not CT16 (w/2) x (h/2)' % (name, uw, uh, ubytes))
        idx = psmt4_from_ct16(data, uw, uh, w, h, tbw)
        logical = [tuple(b[pal + 4 * k:pal + 4 * k + 4]) for k in range(16)]
    else:
        raise Ps2TexError('%s: PSM 0x%02X / %d bpp not handled' % (name, psm, bpp))
    if max(c[3] for c in logical) > 0x80:
        raise Ps2TexError('%s: palette alpha above 0x80' % name)
    pal8 = [c[:3] + (alpha8(c[3]),) for c in logical]
    return Ps2Tex(name, w, h, psm, [pal8[i] for i in idx], indices=idx, palette=pal8, info=info)


def decode(b, names):
    """decode the named textures (case-insensitive) -> {name: Ps2Tex}; raises if one is missing"""
    recs = {n.lower(): (n, r) for n, r in records(b)}
    out = {}
    for nm in names:
        if nm.lower() not in recs:
            raise Ps2TexError('texture %s is not in this dictionary' % nm)
        n, r = recs[nm.lower()]
        out[nm] = decode_record(b, n, r)
    return out
