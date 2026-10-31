"""s6 cars: STRICT reader / writer for Burnout 3 vehicle model files (.bgv racer / .btv traffic; same container).

Structure = exactly what the game's loader relocates (sub_000310F0 and its helpers sub_00031010, sub_00030120,
sub_001C8E20, sub_00157190 layout, sub_00159470), plus sizes derived from the data (index counts, vertex counts).

parse(bytes) -> Model     raises BgvError on anything that does not fit (strict)
build(Model) -> bytes     re-emits every pointer from the region graph and places every region at its offset;
                          unknown bytes (gaps) are carried verbatim and reported, never invented.

Region kinds (all offsets file-absolute; 'rel' = how the game relocates the pointer):
  header        0x16F0 bytes, fixed (pointer fields listed in HDR_PTRS, the rest opaque bytes)
  lod_head      0x70 bytes per LOD: 18 list pointers (+0x00..+0x44, rel LOD), VB0 resource +0x48 (Common, Data rel LOD
                masked, Lock), VB1 resource +0x54, inline list +0x60 (u8 count, u8 aux, u16 0, u32 rel)
  list_hdr      0x10 bytes: u8 count, 3 bytes, u32 offset (rel list header), u32, u32
  draws         count x 0x1C draw records: u32, f32 a, f32 b, u32 off (rel record) -> index stream, u32 n, u32 kind, u32 flags
  idx           n x u16 triangle-strip indices (+ the stream's zero pad to 4)
  vb0           v x 24 bytes (v = 1 + max index of the LOD's draws)              [vertex layout: HYPOTHESIS, not decoded]
  vb1           d x 8 bytes (d = 1 + max index of part lists 1..17 / 0)       [damage stream: HYPOTHESIS]
  tex_hdr       0x80: D3D texture (Common, Data rel tex, Lock, Format, Size) + palette offsets (rel tex) + w/h/name/+0x69 count
  texels        w*h bytes (P8, swizzled)
  pal_hdr       0x40 per palette: D3D palette (Common 0x00030001, Data rel tex, Lock) + zeros
  pal_data      0x400 = 256 x D3DCOLOR (BGRA)
  extra list    header +0x64 / +0x68: list_hdr + draws + idx (no own vertex buffer pointer)
  emitters      18 tables (header +0x1664.., stride 0x18 per group of 6), u8 counts at +0x16AC, entries 0x30 bytes
  deform        header +0x16DC / +0x16E0: object with table at +0x3C (rel object), u8 count +0x40, records 0x10
                (+8 rel record -> u8 count +0xC entries of 8 bytes, +0 rel entry); blob up to the next region (opaque)
  gap           anything else: kept verbatim; classified zero / nonzero
"""
import struct

HDR_SIZE = 0x16F0
REC = 0x1C
VB0_STRIDE = 24
VB1_STRIDE = 8
PAL_HDR = 0x40
PAL_DATA = 0x400


class BgvError(Exception):
    pass


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def s32(b, o):
    return struct.unpack_from('<i', b, o)[0]


class Region:
    __slots__ = ('kind', 'off', 'size', 'owner')

    def __init__(self, kind, off, size, owner=''):
        self.kind, self.off, self.size, self.owner = kind, off, size, owner

    def __repr__(self):
        return '%s@%X+%X(%s)' % (self.kind, self.off, self.size, self.owner)


class Model:
    """Parsed model. Pointer values are recomputed by build() from the region offsets kept here."""

    def __init__(self):
        self.size = 0
        self.header = b''
        self.lods = []          # dicts
        self.tex = None         # dict
        self.extra = {}         # 0x64 / 0x68 -> list dict
        self.emitters = []      # (group, slot, off, count)
        self.deform = {}        # 0x16DC / 0x16E0 -> dict
        self.regions = []
        self.gaps = []          # (off, bytes)
        self.raw = b''


def _need(cond, msg):
    if not cond:
        raise BgvError(msg)


def _list(b, m, at, tag, owner):
    """A list header at `at`: returns dict(count, aux, at, recs_off, draws=[...])."""
    _need(0 <= at and at + 0x10 <= len(b), '%s: list header %X out of file' % (tag, at))
    cnt = b[at]
    rel = u32(b, at + 4)
    tgt = at + rel
    _need(cnt > 0, '%s: empty list' % tag)
    _need(tgt + cnt * REC <= len(b), '%s: draws out of file' % tag)
    draws = []
    for i in range(cnt):
        r = tgt + REC * i
        w0, fa, fb, off, n, kind, flags = struct.unpack_from('<IffIIII', b, r)
        s = r + off
        _need(n > 0 and s + 2 * n <= len(b), '%s draw %d: index stream out of file' % (tag, i))
        _need(w0 == 0, '%s draw %d: word 0 = %X (expected 0 on disc)' % (tag, i, w0))
        draws.append(dict(rec=r, off=s, n=n, fa=fa, fb=fb, kind=kind, flags=flags))
    return dict(at=at, count=cnt, aux=b[at + 1], recs=tgt, draws=draws, tag=tag, owner=owner)


def _maxidx(b, draws):
    mx = -1
    for d in draws:
        mx = max(mx, max(struct.unpack_from('<%dH' % d['n'], b, d['off'])))
    return mx


def parse(b):
    b = bytes(b)
    m = Model()
    m.raw = b
    m.size = len(b)
    _need(len(b) >= HDR_SIZE, 'shorter than the header')
    _need(u32(b, 0) == 0x17, 'magic %X != 0x17' % u32(b, 0))
    _need(u32(b, 8) == len(b), 'size field %X != file size %X' % (u32(b, 8), len(b)))
    _need(len(b) % 0x800 == 0, 'file size not a multiple of 0x800')
    nlod = u32(b, 0x10) + 1          # +0x10 = index of the last LOD (3 racers, 2 traffic)
    _need(nlod in (3, 4), 'LOD count %d' % nlod)
    regs = [Region('header', 0, HDR_SIZE)]
    m.header = b[:HDR_SIZE]
    # ---- LODs
    for k in range(5):
        lo = u32(b, 0x4C + 4 * k)
        if k < nlod:
            _need(lo, 'LOD %d missing' % k)
        else:
            _need(lo == 0, 'LOD %d present beyond count' % k)
            continue
        _need(HDR_SIZE <= lo and lo + 0x70 <= len(b), 'LOD %d head out of file' % k)
        L = dict(off=lo, lists={}, k=k)
        regs.append(Region('lod_head', lo, 0x70, 'lod%d' % k))
        for j in range(18):
            p = u32(b, lo + 4 * j)
            if p:
                li = _list(b, lo, lo + p, 'lod%d.L%d' % (k, j), 'lod%d' % k)
                L['lists'][j] = li
        # inline list +0x60
        li = _list(b, lo, lo + 0x60, 'lod%d.L60' % k, 'lod%d' % k)
        _need(li['aux'] < li['count'], 'lod%d.L60 aux %d >= count' % (k, li['aux']))
        L['whole'] = li
        for nm, at in (('vb0', 0x48), ('vb1', 0x54)):
            common, data, lock = struct.unpack_from('<III', b, lo + at)
            _need(common == 1 and lock == 0, 'lod%d %s resource %X/%X' % (k, nm, common, lock))
            L[nm] = lo + data
        _need(u32(b, lo + 0x68) == 0 and u32(b, lo + 0x6C) == 0, 'lod%d head tail not zero' % k)
        _need(b[lo + 0x62:lo + 0x64] == b'\0\0', 'lod%d L60 pad' % k)
        alld = [d for li in L['lists'].values() for d in li['draws']] + L['whole']['draws']
        parts = [d for j, li in L['lists'].items() for d in li['draws'] if j != 0]
        L['nv'] = _maxidx(b, alld) + 1
        # vb1 entry count: 1 + max index of the part lists (1..17); without part lists it covers every vertex
        L['nd'] = (_maxidx(b, parts) + 1) if parts else L['nv']
        regs.append(Region('vb0', L['vb0'], L['nv'] * VB0_STRIDE, 'lod%d' % k))
        if L['nd']:
            regs.append(Region('vb1', L['vb1'], L['nd'] * VB1_STRIDE, 'lod%d' % k))
        m.lods.append(L)
    # ---- texture block
    t = u32(b, 0x60)
    _need(t and t + 0x80 <= len(b), 'texture block missing')
    common, data, lock, fmt, size = struct.unpack_from('<5I', b, t)
    _need(common == 0x00040001 and lock == 0 and size == 0, 'texture resource %X' % common)
    _need((fmt >> 8) & 0xFF == 0x0B, 'texture format %X is not P8' % fmt)
    w = 1 << ((fmt >> 20) & 0xF)
    h = 1 << ((fmt >> 24) & 0xF)
    _need((fmt >> 16) & 0xF == 1, 'mip levels %d' % ((fmt >> 16) & 0xF))
    _need(u32(b, t + 0x34) == 0x0B and u32(b, t + 0x38) == w and u32(b, t + 0x3C) == h, 'texture w/h fields')
    npal = b[t + 0x69]
    _need(1 <= npal <= 8, 'palette count %d' % npal)
    name = b[t + 0x48:t + 0x60].split(b'\0')[0].decode('ascii')
    T = dict(off=t, fmt=fmt, w=w, h=h, npal=npal, name=name, texels=t + data, pals=[])
    regs.append(Region('tex_hdr', t, 0x80))
    regs.append(Region('texels', t + data, w * h))
    for i in range(8):
        p = u32(b, t + 0x14 + 4 * i)
        if i >= npal:
            _need(p == 0, 'palette slot %d used beyond count' % i)
            continue
        pc, pd, pl = struct.unpack_from('<3I', b, t + p)
        _need(pc == 0x00030001 and pl == 0, 'palette %d resource %X' % (i, pc))
        _need(pd == p + PAL_HDR, 'palette %d data not right after its header' % i)
        _need(b[t + p + 0xC:t + p + PAL_HDR] == bytes(PAL_HDR - 0xC), 'palette %d header tail not zero' % i)
        T['pals'].append(dict(hdr=t + p, data=t + pd))
        regs.append(Region('pal_hdr', t + p, PAL_HDR, 'pal%d' % i))
        regs.append(Region('pal_data', t + pd, PAL_DATA, 'pal%d' % i))
    m.tex = T
    # ---- extra lists +0x64 / +0x68
    for at in (0x64, 0x68):
        p = u32(b, at)
        if p:
            m.extra[at] = _list(b, 0, p, 'extra%X' % at, 'extra')
    # ---- emitters
    for g in range(3):
        for s in range(6):
            o = 0x1664 + 0x18 * g + 4 * s
            p = u32(b, o)
            c = b[0x16AC + 6 * g + s]
            if p:
                _need(c > 0 and p + 0x30 * c <= len(b), 'emitter table %d.%d' % (g, s))
                m.emitters.append((g, s, p, c))
                regs.append(Region('emitters', p, 0x30 * c, '%d.%d' % (g, s)))
            else:
                _need(c == 0, 'emitter count without table %d.%d' % (g, s))
    # ---- attachment table (+0x16C0 table, +0x16C4 first data, u8 count +0x16C8; only HEVY/Car27.btv in retail)
    at_tbl, at_first, at_n = u32(b, 0x16C0), u32(b, 0x16C4), b[0x16C8]
    m.attach = []
    m.attach_tbl = at_tbl
    if at_tbl or at_first or at_n:
        _need(at_tbl and at_n and at_tbl + 0xC * at_n <= len(b), 'attachment table')
        regs.append(Region('attach_tbl', at_tbl, 0xC * at_n))
        for i in range(at_n):
            cnt, z, data = struct.unpack_from('<3I', b, at_tbl + 0xC * i)
            _need(z == 0 and data and data + 0x50 * cnt <= len(b), 'attachment record %d' % i)
            if i == 0:
                _need(data == at_first, 'attachment +0x16C4 != first record data')
            m.attach.append((cnt, data))
            regs.append(Region('attach', data, 0x50 * cnt, '%d' % i))
    # ---- deform objects (blob extents decided after the other regions are known)
    for at in (0x16DC, 0x16E0):
        p = u32(b, at)
        if p:
            m.deform[at] = dict(off=p)
    # ---- lists -> regions
    for li in _all_lists(m):
        if li['at'] >= HDR_SIZE and not (li['tag'].endswith('L60')):
            regs.append(Region('list_hdr', li['at'], 0x10, li['tag']))
        regs.append(Region('draws', li['recs'], li['count'] * REC, li['tag']))
    # index streams may be shared by two draws of two lists (same offset, same n): one region per distinct stream
    seen = {}
    for li in _all_lists(m):
        for d in li['draws']:
            key = d['off']
            ln = 2 * d['n']
            if key in seen:
                _need(seen[key] == ln, 'index stream %X shared with different lengths' % key)
                continue
            seen[key] = ln
            regs.append(Region('idx', key, ln, li['tag']))
    # ---- deform blobs: from the object to the next region start (or the end of file)
    starts = sorted(r.off for r in regs)
    for at, D in m.deform.items():
        p = D['off']
        nxt = min([s for s in starts if s > p] + [o['off'] for o in m.deform.values() if o['off'] > p] + [len(b)])
        D['end'] = nxt
        _check_deform(b, p, nxt)
        regs.append(Region('deform', p, nxt - p, '%X' % at))
    # ---- coverage
    regs.sort(key=lambda r: (r.off, r.size))
    pos = 0
    gaps = []
    for r in regs:
        _need(r.off + r.size <= len(b), 'region %r beyond the file' % r)
        if r.off < pos:
            raise BgvError('overlap: %r starts before %X' % (r, pos))
        if r.off > pos:
            gaps.append((pos, b[pos:r.off]))
        pos = r.off + r.size
    if pos < len(b):
        gaps.append((pos, b[pos:]))
    for o, g in gaps:   # strict: every byte outside a typed region must be alignment padding (zero)
        _need(not any(g), 'nonzero bytes outside every known region at %X (%d bytes)' % (o, len(g)))
    m.regions = regs
    m.gaps = gaps
    return m


def _check_deform(b, p, end):
    """The game's sub_00159470 walk, bounds-checked inside [p, end)."""
    _need(p + 0x44 <= end, 'deform object %X too small' % p)
    tb = u32(b, p + 0x3C)
    n = b[p + 0x40]
    if not tb:
        return
    tbl = p + tb
    _need(p <= tbl and tbl + 0x10 * n <= end, 'deform %X table out of object' % p)
    for i in range(n):
        r = tbl + 0x10 * i
        ro = s32(b, r + 8)              # the game adds mod 2^32: negative offsets point before the table
        if not ro:
            continue
        e = r + ro
        c = b[r + 0xC]
        _need(p <= e and e + 8 * c <= end, 'deform %X record %d entries out of object' % (p, i))
        for j in range(c):
            eo = s32(b, e + 8 * j)
            if eo:
                _need(p <= e + 8 * j + eo < end, 'deform %X record %d entry %d target out of object' % (p, i, j))


def _all_lists(m):
    for L in m.lods:
        for j in sorted(L['lists']):
            yield L['lists'][j]
        yield L['whole']
    for at in sorted(m.extra):
        yield m.extra[at]


def build(m):
    """Re-emit the file from the parsed graph: header bytes with every pointer field recomputed from the regions,
    every region's bytes, gaps verbatim. Returns bytes; parse(build(m)) must equal m structurally."""
    b = m.raw
    out = bytearray(m.size)
    # regions carry their bytes from the source (contents are leaf data); pointers are rewritten below
    for r in m.regions:
        out[r.off:r.off + r.size] = b[r.off:r.off + r.size]
    for off, gb in m.gaps:
        out[off:off + len(gb)] = gb

    def put(o, v):
        struct.pack_into('<I', out, o, v)
    put(8, m.size)
    for k in range(5):
        put(0x4C + 4 * k, m.lods[k]['off'] if k < len(m.lods) else 0)
    for L in m.lods:
        lo = L['off']
        for j in range(18):
            li = L['lists'].get(j)
            put(lo + 4 * j, (li['at'] - lo) if li else 0)
        for nm, at in (('vb0', 0x48), ('vb1', 0x54)):
            put(lo + at + 4, L[nm] - lo)
    for li in _all_lists(m):
        out[li['at']] = li['count']
        put(li['at'] + 4, li['recs'] - li['at'])
        for d in li['draws']:
            put(d['rec'] + 0xC, d['off'] - d['rec'])
            put(d['rec'] + 0x10, d['n'])
    T = m.tex
    put(0x60, T['off'])
    put(T['off'] + 4, T['texels'] - T['off'])
    out[T['off'] + 0x69] = T['npal']
    for i in range(8):
        if i < len(T['pals']):
            P = T['pals'][i]
            put(T['off'] + 0x14 + 4 * i, P['hdr'] - T['off'])
            put(P['hdr'] + 4, P['data'] - T['off'])
        else:
            put(T['off'] + 0x14 + 4 * i, 0)
    for at in (0x64, 0x68):
        put(at, m.extra[at]['at'] if at in m.extra else 0)
    for g, s, p, c in m.emitters:
        put(0x1664 + 0x18 * g + 4 * s, p)
        out[0x16AC + 6 * g + s] = c
    for at in (0x16DC, 0x16E0):
        put(at, m.deform[at]['off'] if at in m.deform else 0)
    if m.attach:
        put(0x16C0, m.attach_tbl)
        put(0x16C4, m.attach[0][1])
        out[0x16C8] = len(m.attach)
        for i, (cnt, data) in enumerate(m.attach):
            struct.pack_into('<3I', out, m.attach_tbl + 0xC * i, cnt, 0, data)
    return bytes(out)


def coverage(m):
    known = sum(r.size for r in m.regions)
    zero = sum(len(g) for o, g in m.gaps if not any(g))
    nonzero = sum(len(g) for o, g in m.gaps if any(g))
    return dict(size=m.size, regions=known, gap_zero=zero, gap_nonzero=nonzero,
                gaps=[(o, len(g), bool(any(g))) for o, g in m.gaps])


# ---------------------------------------------------------------- paint / livery helpers (texture + palettes)
def palettes(m):
    """[(index, 256 x (b, g, r, a))] in file order."""
    out = []
    for i, P in enumerate(m.tex['pals']):
        d = m.raw[P['data']:P['data'] + PAL_DATA]
        out.append((i, [tuple(d[4 * k:4 * k + 4]) for k in range(256)]))
    return out


def texels(m):
    T = m.tex
    return m.raw[T['texels']:T['texels'] + T['w'] * T['h']]


def replace(m, texels_new=None, palettes_new=None):
    """Same-size replacement of the texels (w*h P8 indices, swizzled as stored) and / or palette data (list of
    0x400-byte BGRA blocks, exactly npal of them). Geometry, pointers and every other byte stay identical."""
    out = bytearray(m.raw)
    T = m.tex
    if texels_new is not None:
        if len(texels_new) != T['w'] * T['h']:
            raise BgvError('texels: %d bytes, expected %d' % (len(texels_new), T['w'] * T['h']))
        out[T['texels']:T['texels'] + len(texels_new)] = texels_new
    if palettes_new is not None:
        if len(palettes_new) != len(T['pals']):
            raise BgvError('palettes: %d given, the file has %d (count change is not supported in place)'
                           % (len(palettes_new), len(T['pals'])))
        for P, d in zip(T['pals'], palettes_new):
            if len(d) != PAL_DATA:
                raise BgvError('palette block %d bytes' % len(d))
            out[P['data']:P['data'] + PAL_DATA] = d
    return bytes(out)


# ---------------------------------------------------------------- swizzle (NV2A Morton order for P8)
def _morton_table(w, h):
    # NV2A swizzle: interleave x / y bits while both have bits left, then the remaining bits of the larger dimension
    tbl = []
    for y in range(h):
        for x in range(w):
            o = 0
            bit = 0
            xb = yb = 0
            mw, mh = w - 1, h - 1
            while mw or mh:
                if mw:
                    o |= ((x >> xb) & 1) << bit
                    bit += 1
                    xb += 1
                    mw >>= 1
                if mh:
                    o |= ((y >> yb) & 1) << bit
                    bit += 1
                    yb += 1
                    mh >>= 1
            tbl.append(o)
    return tbl


_MT = {}


def unswizzle(data, w, h):
    t = _MT.get((w, h)) or _MT.setdefault((w, h), _morton_table(w, h))
    return bytes(data[t[i]] for i in range(w * h))


def swizzle(lin, w, h):
    t = _MT.get((w, h)) or _MT.setdefault((w, h), _morton_table(w, h))
    out = bytearray(w * h)
    for i in range(w * h):
        out[t[i]] = lin[i]
    return bytes(out)
