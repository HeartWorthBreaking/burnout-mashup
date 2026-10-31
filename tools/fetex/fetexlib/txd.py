"""fetex: Criterion texture dictionary (Burnout 3 Xbox Data/*.txd) - strict reader, writer, front-end capability check.

Layout (proven by round trip of the retail Frontend.txd, 218 entries, byte for byte; the game's fixup = sub_001BEEF0 +
sub_001C8E20, gp\\slices\\fetex1\\TRACE.md):
  header 0x10: u32 magic 0x543C0000, u32 tag (opaque; retail Frontend 0xBCDEED81), u32 count, u32 table offset (0x10)
  table: count x {u32 index (1-based), u32 0, u32 entry offset, u32 0}; zero padding up to the first entry
  entry (0x80-aligned): 0x80-byte texture header
    +0x00 D3D Common 0x00040001 (texture), +0x04 Data = 0x80 (texels, relative to the entry), +0x08 Lock 0,
    +0x0C Format = 0x29 | fmt << 8 | 1 << 16 | log2(w) << 20 | log2(h) << 24 (1 mip), +0x10 Size 0,
    +0x14 u32[8] palette header offsets (relative to the entry; 0 unused), +0x34 u32 fmt, +0x38 u32 w, +0x3C u32 h,
    +0x40 u32 bits (P8: 8, or 4 = a 16-colour palette; DXT: 32), +0x44 0, +0x48 name[32] (NUL-terminated),
    +0x68 u8 1, +0x69 u8 palette count, rest 0
  texels (P8: w*h swizzled; DXT1: w*h/2; DXT5: w*h), then per palette a 0x40 header {Common 0x00030001 (| 0xC0000000 for
  the 16-colour form, D3D size 32), Data = header + 0x40 (relative to the entry), 0...} + 4 << bits bytes BGRA;
  zero padding to the next 0x80.
Anything else (a nonzero byte outside these fields, overlap, a field off this layout) is refused by parse().
"""
import struct

MAGIC = 0x543C0000
FMT_P8, FMT_DXT1, FMT_DXT5 = 0x0B, 0x0C, 0x0F
FMT_ARGB = 0x06                 # swizzled A8R8G8B8 (main21 patch 128: the host takes it for [bmashup.textures] class "global" only)
FMT_NAMES = {FMT_P8: 'P8', FMT_DXT1: 'DXT1', FMT_DXT5: 'DXT5', FMT_ARGB: 'A8R8G8B8'}
NAME_MAX = 31

# Front-end capability list v1 (CONTRACTS_CONTENT s2; INTERFACE.md s1) - the host checks the same (bm_fetex_parse.inc)
CAP_FRONTEND = dict(formats=(FMT_P8, FMT_DXT1, FMT_DXT5), min_side=4, max_side=1024, mips=1, max_palettes=8,
                    p8_bits=8, max_entries=64, max_entry_bytes=1 << 20)
NAME_CHARS = set('abcdefghijklmnopqrstuvwxyz0123456789_.-')


class TxdError(ValueError):
    pass


def texel_bytes(fmt, w, h, bits=8):
    if fmt == FMT_P8:
        return w * h        # one byte per texel, also for the 16-colour form (retail 'Blocked' etc.: 32x32 -> 0x400)
    if fmt == FMT_DXT1:
        return max(1, w // 4) * max(1, h // 4) * 8
    if fmt == FMT_DXT5:
        return max(1, w // 4) * max(1, h // 4) * 16
    if fmt == FMT_ARGB:
        return w * h * 4
    raise TxdError('format 0x%02X not supported' % fmt)


def format_word(fmt, w, h):
    return 0x29 | fmt << 8 | 1 << 16 | (w.bit_length() - 1) << 20 | (h.bit_length() - 1) << 24


def _pow2(v):
    return v > 0 and v & (v - 1) == 0


class Entry:
    def __init__(self, name, fmt, w, h, texels, palettes=(), bits=None, opaque=None):
        self.name, self.fmt, self.w, self.h = name, fmt, w, h
        self.texels = bytes(texels)
        self.palettes = [bytes(p) for p in palettes]
        self.bits = bits if bits is not None else (8 if fmt == FMT_P8 else 32)
        self.opaque = opaque          # reserved: unknown header bytes (always None for files parse() accepts)

    def size(self):
        return entry_size(self.fmt, self.w, self.h, len(self.palettes), self.bits)

    def info(self):
        return dict(name=self.name, format=FMT_NAMES.get(self.fmt, hex(self.fmt)), fmt=self.fmt, w=self.w, h=self.h,
                    palettes=len(self.palettes), bits=self.bits, bytes=self.size())


def pal_block(bits):
    return (0x40 + (4 << bits) + 0x7F) & ~0x7F      # header + data, 0x80-aligned (retail: 0x480 / 0x80)


def entry_size(fmt, w, h, npal, bits):
    end = 0x80 + texel_bytes(fmt, w, h, bits) + (npal * pal_block(bits) if fmt == FMT_P8 else 0)
    return (end + 0x7F) & ~0x7F


class Txd:
    def __init__(self, entries, tag=0):
        self.entries = list(entries)
        self.tag = tag

    def find(self, name):
        for e in self.entries:
            if e.name.lower() == name.lower():
                return e
        return None


def parse(b):
    """strict reader: returns Txd, raises TxdError naming the first violation"""
    b = bytes(b)
    if len(b) < 0x10:
        raise TxdError('truncated header')
    magic, tag, n, tbl = struct.unpack_from('<4I', b, 0)
    if magic != MAGIC:
        raise TxdError('magic %08X is not a Criterion TXD (543C0000)' % magic)
    if tbl != 0x10:
        raise TxdError('table offset %X (expected 0x10)' % tbl)
    if n == 0 or n > 4096:
        raise TxdError('entry count %d out of range 1..4096' % n)
    if 0x10 + 16 * n > len(b):
        raise TxdError('table runs past the file')
    covered = bytearray(len(b))

    def cover(a, z, what):
        if a < 0 or z > len(b) or a > z:
            raise TxdError('%s out of the file (%X..%X)' % (what, a, z))
        if any(covered[a:z]):
            raise TxdError('%s overlaps another region (%X..%X)' % (what, a, z))
        covered[a:z] = b'\1' * (z - a)

    cover(0, 0x10 + 16 * n, 'header + table')
    ents = []
    prev = 0
    for i in range(n):
        idx, z1, off, z2 = struct.unpack_from('<4I', b, 0x10 + 16 * i)
        if idx != i + 1 or z1 or z2:
            raise TxdError('table row %d malformed' % i)
        if off % 0x80 or off <= prev and i:
            raise TxdError('entry %d offset %X not 0x80-aligned / not ascending' % (i, off))
        prev = off
        if off + 0x80 > len(b):
            raise TxdError('entry %d header past the file' % i)
        common, data, lock, fw, size = struct.unpack_from('<5I', b, off)
        pals = struct.unpack_from('<8I', b, off + 0x14)
        fmt, w, h, bits, z44 = struct.unpack_from('<5I', b, off + 0x34)
        raw = b[off + 0x48:off + 0x68]
        name = raw.split(b'\0')[0]
        one, npal = b[off + 0x68], b[off + 0x69]
        if common != 0x00040001 or data != 0x80 or lock or size or z44:
            raise TxdError('entry %d: D3D texture header fields off the layout' % i)
        if fmt not in FMT_NAMES:
            raise TxdError('entry %d: format 0x%02X not supported by this reader' % (i, fmt))
        if not (_pow2(w) and _pow2(h)) or w > 4096 or h > 4096:
            raise TxdError('entry %d: size %dx%d not powers of two' % (i, w, h))
        if fw != format_word(fmt, w, h):
            raise TxdError('entry %d: format word %08X != %08X (1 mip, 2D)' % (i, fw, format_word(fmt, w, h)))
        if (fmt == FMT_P8 and bits not in (4, 8)) or (fmt != FMT_P8 and bits != 32):
            raise TxdError('entry %d: bits %d off the layout' % (i, bits))
        if one != 1 or npal > 8 or (fmt != FMT_P8 and npal) or (fmt == FMT_P8 and not npal):
            raise TxdError('entry %d: palette count %d / flag %d off the layout' % (i, npal, one))
        if len(name) == 0 or len(name) > NAME_MAX or any(raw[len(name):]):
            raise TxdError('entry %d: name field malformed' % i)
        if any(b[off + 0x6A:off + 0x80]):
            raise TxdError('entry %d: nonzero bytes in the reserved header tail' % i)
        cover(off, off + 0x80, 'entry %d header' % i)
        tb = texel_bytes(fmt, w, h, bits)
        cover(off + 0x80, off + 0x80 + tb, 'entry %d texels' % i)
        texels = b[off + 0x80:off + 0x80 + tb]
        palettes = []
        pdata = 4 << bits if fmt == FMT_P8 else 0
        for k in range(8):
            po = pals[k]
            if k >= npal:
                if po:
                    raise TxdError('entry %d: palette offset %d set beyond the count' % (i, k))
                continue
            expect = 0x80 + tb + k * pal_block(bits)
            if po != expect:
                raise TxdError('entry %d: palette %d at %X (expected %X)' % (i, k, po, expect))
            pc, pd = struct.unpack_from('<2I', b, off + po)
            want = 0x00030001 | (0xC0000000 if bits == 4 else 0)
            if pc != want or pd != po + 0x40 or any(b[off + po + 8:off + po + 0x40]):
                raise TxdError('entry %d: palette %d header off the layout' % (i, k))
            cover(off + po, off + po + 0x40 + pdata, 'entry %d palette %d' % (i, k))
            palettes.append(b[off + po + 0x40:off + po + 0x40 + pdata])
        ents.append(Entry(name.decode('ascii'), fmt, w, h, texels, palettes, bits))
    for a in range(len(b)):
        if not covered[a] and b[a]:
            raise TxdError('nonzero byte at %X outside every typed region' % a)
    names = [e.name.lower() for e in ents]
    if len(set(names)) != len(names):
        raise TxdError('a name twice (case-insensitive)')
    return Txd(ents, tag)


def build(t):
    """writer: the layout above; parse(build(parse(x))) == x for every file parse accepts"""
    n = len(t.entries)
    if not n:
        raise TxdError('no entries')
    out = bytearray(struct.pack('<4I', MAGIC, t.tag, n, 0x10))
    first = (0x10 + 16 * n + 0x7F) & ~0x7F
    offs, o = [], first
    for e in t.entries:
        offs.append(o)
        o += e.size()
    for i, off in enumerate(offs):
        out += struct.pack('<4I', i + 1, 0, off, 0)
    out += bytes(first - len(out))
    for e, off in zip(t.entries, offs):
        tb = texel_bytes(e.fmt, e.w, e.h, e.bits)
        if len(e.texels) != tb:
            raise TxdError('%s: %d texel bytes, expected %d' % (e.name, len(e.texels), tb))
        pdata = 4 << e.bits if e.fmt == FMT_P8 else 0
        nm = e.name.encode('ascii')
        if not nm or len(nm) > NAME_MAX:
            raise TxdError('%s: name length' % e.name)
        h = bytearray(0x80)
        struct.pack_into('<5I', h, 0, 0x00040001, 0x80, 0, format_word(e.fmt, e.w, e.h), 0)
        for k in range(len(e.palettes)):
            struct.pack_into('<I', h, 0x14 + 4 * k, 0x80 + tb + k * pal_block(e.bits))
        struct.pack_into('<5I', h, 0x34, e.fmt, e.w, e.h, e.bits, 0)
        h[0x48:0x48 + len(nm)] = nm
        h[0x68], h[0x69] = 1, len(e.palettes)
        body = bytearray(h) + e.texels
        for k, p in enumerate(e.palettes):
            if len(p) != pdata:
                raise TxdError('%s: palette %d has %d bytes, expected %d' % (e.name, k, len(p), pdata))
            po = 0x80 + tb + k * pal_block(e.bits)
            ph = bytearray(0x40)
            struct.pack_into('<2I', ph, 0, 0x00030001 | (0xC0000000 if e.bits == 4 else 0), po + 0x40)
            body += ph + p + bytes(pal_block(e.bits) - 0x40 - pdata)
        body += bytes(e.size() - len(body))
        assert len(out) == off
        out += body
    return bytes(out)


def check_frontend(t, cap=CAP_FRONTEND):
    """the front-end capability list v1 (the host's admission rules); returns a list of violations ('' = none)"""
    bad = []
    if len(t.entries) > cap['max_entries']:
        bad.append('%d entries; at most %d per mod' % (len(t.entries), cap['max_entries']))
    for e in t.entries:
        if e.name != e.name.lower() or not set(e.name) <= NAME_CHARS:
            bad.append('%s: name must be [a-z0-9_.-]{1,31}' % e.name)
        if e.fmt not in cap['formats']:
            bad.append('%s: format 0x%02X not in the front-end list (P8, DXT1, DXT5)' % (e.name, e.fmt))
        if not (cap['min_side'] <= e.w <= cap['max_side'] and cap['min_side'] <= e.h <= cap['max_side']):
            bad.append('%s: %dx%d outside %d..%d' % (e.name, e.w, e.h, cap['min_side'], cap['max_side']))
        if e.fmt == FMT_P8 and e.bits != cap['p8_bits']:
            bad.append('%s: P8 with a 16-colour palette (bits 4) is not in the list' % e.name)
        if e.size() > cap['max_entry_bytes']:
            bad.append('%s: %d bytes > %d' % (e.name, e.size(), cap['max_entry_bytes']))
    return bad
