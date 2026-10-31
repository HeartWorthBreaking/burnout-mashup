"""Writer: car IR + donor model -> a NEW .bgv (Burnout 3 race-car model container, magic 0x17).

What is AUTHORED (written from the IR): every LOD's vertex buffer (VB0: pos f32x3, NORMPACKED3 normal, uv f32x2), the
deformation stream (VB1), all draw lists / draw records / triangle-strip index streams, the whole-car lists, the texture
texels + palettes, the bounds (+0xE80 AABB, +0x14 radius).
What is carried from the DONOR (structural data the slice cannot author yet; never art): the header's matrices, wheel and
locator tables, collision hull (+0x1060), crush-rig tables, emitter tables (light / exhaust / smoke points) and the engine-sound
descriptors (+0x16DC / +0x16E0). The output therefore stays LOCAL (it embeds retail structural bytes), labelled DERIVED for
those blocks; the geometry and texture are AUTHORED.

Render facts used (SRC: the game's car render routines sub_000303D0 / 00031E10 / 00031E70 / 00031AB0 / 000300A0 / 000315C0):
  * undamaged car: the whole-car list (LOD +0x60) with the rigid shader; damaged (+0x101B): L0 skinned with 8 crush
    matrices + parts L1..L<locators> each with its own matrix; wheels: L7 / L8 / L9 by wheel spin at each wheel matrix.
  * stream 0 = VB0 stride 24, stream 1 = VB1 stride 8 (u16 boneA*3, u16 boneB*3, u16 wA, u16 wB, wA + wB = 255).
  * draw record: +0x10 u16 index count, D3D primitive 6 = TRIANGLESTRIP; +0x18 u16 flags (1 paint shader, 2 plain shader,
    0x100 glass pass), +0x1A u8 texture slot (0 = the car's own texture, 2 = the global glass texture), +0x14 u32 'kind';
    list aux = index of the glass draw (glass break state, sub_000300A0) or 0xFF.
Material classes: paint -> flags 1 / slot 0; plain -> flags 2 / slot 0; glass -> flags 0x100 / slot 2, alpha 0.4118 (retail).
Neutral equivalents (documented, never silent): detachable parts L1..L<locators> = one zero-area draw each (no visible
debris); a zero-area glass draw when the body has no glass (keeps the whole list's aux valid as in all retail files).
"""
import hashlib
import math
import os
import struct

from . import texture
from . import bgvlib   # vendored copy of the s6 strict reader (byte-identical; PROVENANCE.md)

BGVLIB_DIR = os.path.dirname(os.path.abspath(__file__))
BGVLIB_SHA = 'b5df11b92d4a9fff8bc3ba5f5e5bdb3566b7a390710616d0cdb1ec2f8ca80a61'   # the vendored file (checked by the tests)

HDR = 0x16F0
SLOT_LIMIT = 0x9D800
CLS_FLAGS = {'paint': (1, 0, 1.0, 0.0), 'plain': (2, 0, 1.0, 0.0), 'glass': (0x100, 2, 0.4117647111415863, 0.4117647111415863)}
CLS_ORDER = ('paint', 'plain', 'glass')


class BuildError(Exception):
    pass


def bgvlib_sha():
    return hashlib.sha256(open(os.path.join(BGVLIB_DIR, 'bgvlib.py'), 'rb').read()).hexdigest()


# ---------------------------------------------------------------- vertex packing
def pack_normal(n):
    x = max(-1023, min(1023, int(round(n[0] * 1023.0))))
    y = max(-1023, min(1023, int(round(n[1] * 1023.0))))
    z = max(-511, min(511, int(round(n[2] * 511.0))))
    return (x & 0x7FF) | ((y & 0x7FF) << 11) | ((z & 0x3FF) << 22)


def unpack_normal(p):
    x = p & 0x7FF
    y = (p >> 11) & 0x7FF
    z = (p >> 22) & 0x3FF
    if x & 0x400:
        x -= 0x800
    if y & 0x400:
        y -= 0x800
    if z & 0x200:
        z -= 0x400
    return (x / 1023.0, y / 1023.0, z / 511.0)


# ---------------------------------------------------------------- strips
def to_strip(tris):
    """Triangles (CCW front) -> one D3D triangle strip (odd triangles reversed by the GPU) joined by degenerates.
    Continues the current strip when the next triangle shares the last edge with the right parity."""
    s = []
    for a, b, c in tris:
        if not s:
            s = [a, b, c]
            continue
        t = len(s) - 2
        p, q = s[-2], s[-1]
        done = False
        for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
            if (t % 2 == 0 and (u, v) == (p, q)) or (t % 2 == 1 and (u, v) == (q, p)):
                s.append(w)
                done = True
                break
        if done:
            continue
        s += [s[-1], a]
        if len(s) % 2:
            s.append(a)
        s += [a, b, c]
    return s


def strip_tris(s):
    """Inverse for checks: the non-degenerate triangles of a strip, in CCW-front order."""
    out = []
    for i in range(len(s) - 2):
        a, b, c = s[i], s[i + 1], s[i + 2]
        if a == b or b == c or a == c:
            continue
        out.append((b, a, c) if i % 2 else (a, b, c))
    return out


def _canon(t):
    k = t.index(min(t))
    return t[k:] + t[:k]


# ---------------------------------------------------------------- deformation (VB1)
class Skinner:
    """Per-vertex crush skin. mode 'transfer': nearest donor LOD3 L0 vertex after mapping the authored body AABB onto the
    donor's (copies its two bones / weights); mode 'rigid': every body vertex on crush bone 3 (index 9, the donor's
    mid-body bone) with weight 255. Wheels: bone 0, 255 (as every retail wheel vertex)."""

    def __init__(self, donor, mode, body_bounds):
        self.mode = mode
        if mode not in ('transfer', 'rigid'):
            raise BuildError('deform mode %r (transfer | rigid)' % mode)
        if mode == 'rigid':
            return
        b = donor.raw
        L = donor.lods[-1]
        s = set()
        for d in L['lists'][0]['draws']:
            s |= set(struct.unpack_from('<%dH' % d['n'], b, d['off']))
        self.src = []
        for i in sorted(s):
            if i < L['nd']:
                p = struct.unpack_from('<3f', b, L['vb0'] + 24 * i)
                self.src.append((p, struct.unpack_from('<4H', b, L['vb1'] + 8 * i)))
        dmin = [min(p[k] for p, _ in self.src) for k in range(3)]
        dmax = [max(p[k] for p, _ in self.src) for k in range(3)]
        amin, amax = body_bounds
        self.map = [(dmin[k], (dmax[k] - dmin[k]) / max(1e-6, amax[k] - amin[k]), amin[k]) for k in range(3)]
        self.cell = 0.25
        self.grid = {}
        for p, sk in self.src:
            self.grid.setdefault(tuple(int(math.floor(p[k] / self.cell)) for k in range(3)), []).append((p, sk))

    def skin(self, p):
        if self.mode == 'rigid':
            return (9, 9, 255, 0)
        q = [self.map[k][0] + (p[k] - self.map[k][2]) * self.map[k][1] for k in range(3)]
        c = [int(math.floor(q[k] / self.cell)) for k in range(3)]
        best = None
        r = 0
        while best is None or r <= 2:
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        if max(abs(dx), abs(dy), abs(dz)) != r:
                            continue
                        for sp, sk in self.grid.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                            d = sum((sp[k] - q[k]) ** 2 for k in range(3))
                            if best is None or d < best[0]:
                                best = (d, sk)
            r += 1
            if r > 40:
                break
        return best[1]


# ---------------------------------------------------------------- the writer
class Out:
    def __init__(self, size_hint=0):
        self.b = bytearray()

    def align(self, a):
        while len(self.b) % a:
            self.b.append(0)
        return len(self.b)

    def put(self, data):
        o = len(self.b)
        self.b += data
        return o

    def u32(self, o, v):
        struct.pack_into('<I', self.b, o, v & 0xFFFFFFFF)


def _draws_for(mesh_groups, base, aux_glass, split=60000):
    """[(cls, strip)] in class order; a strip longer than `split` indices is cut into several draws."""
    out = []
    for cls in CLS_ORDER:
        tris = mesh_groups.get(cls)
        if not tris:
            continue
        chunk = []
        for t in tris:
            chunk.append(tuple(i + base for i in t))
            if len(chunk) >= split // 4:
                out.append((cls, to_strip(chunk)))
                chunk = []
        if chunk:
            out.append((cls, to_strip(chunk)))
    if aux_glass is not None and not any(c == 'glass' for c, _ in out):
        out.append(('glass', [aux_glass] * 3))       # neutral zero-area glass draw (keeps aux valid)
    return out


def _emit_list(o, at_hdr, draws, inline=False):
    """Writes the draw records (right after the list header, or after the inline header) and returns the record offsets.
    List header: u8 count, u8 aux, u16 0, u32 records rel header, u32 0, u32 0."""
    if len(draws) > 255:
        raise BuildError('more than 255 draws in one list')
    aux = 0xFF
    for i, (cls, _) in enumerate(draws):
        if cls == 'glass':
            aux = i
    o.b[at_hdr] = len(draws)
    o.b[at_hdr + 1] = aux
    recs = o.align(4)
    o.put(bytes(0x1C * len(draws)))
    o.u32(at_hdr + 4, recs - at_hdr)
    return recs


def _emit_records(o, recs, draws):
    for i, (cls, strip) in enumerate(draws):
        if len(strip) > 0xFFFF:
            raise BuildError('strip of %d indices' % len(strip))
        ix = o.align(4)
        o.put(struct.pack('<%dH' % len(strip), *strip))
        flags, slot, fa, fb = CLS_FLAGS[cls]
        r = recs + 0x1C * i
        struct.pack_into('<IffIIII', o.b, r, 0, fa, fb, ix - r, len(strip), 0, flags | (slot << 16))


def build(ir, donor_bytes, *, deform='transfer', tex=None, tex_name='carimport', wheel_mesh=None):
    """ir: dict(lods=[Mesh x4], wheel=Mesh). tex: texture.build() result. Returns (bytes, report)."""
    donor = bgvlib.parse(donor_bytes)
    if len(donor.lods) != 4:
        raise BuildError('donor has %d LODs: a race car (.bgv, 4 LODs) is required' % len(donor.lods))
    if donor.attach:
        raise BuildError('donor has an attachment table (not supported)')
    db = donor.raw
    nloc = db[0xC]
    nwheel = db[0xD]
    wheel = ir.get('wheel') or wheel_mesh
    if wheel is None:
        raise BuildError('no wheel mesh')
    rep = dict(donor_locators=nloc, donor_wheels=nwheel, lods=[], deform=deform, notes=[])
    o = Out()
    o.put(db[:HDR])
    body3 = ir['lods'][3]
    bb = body3.bounds()
    sk = Skinner(donor, deform, bb)
    lod_offs = []
    for k in range(4):
        body = ir['lods'][k]
        nb = len(body.verts)
        nv = nb + len(wheel.verts)
        if nv > 0xFFFF:
            raise BuildError('LOD %d: %d vertices (16-bit indices: max 65535)' % (k, nv))
        lo = o.align(0x10)
        lod_offs.append(lo)
        o.put(bytes(0x70))
        anchor = nb                                   # first wheel vertex (bone 0, weight 255)
        lists = {}
        lists[0] = _draws_for(body.groups, 0, anchor)
        for j in range(1, nloc + 1):
            lists[j] = [('plain', [anchor] * 3)]      # neutral part: zero area (detachable panels not authored)
        for j in (7, 8, 9):
            lists[j] = _draws_for(wheel.groups, nb, None)
        rec_at = {}
        for j in sorted(lists):
            h = o.align(4)
            o.put(bytes(0x10))
            o.u32(lo + 4 * j, h - lo)
            rec_at[j] = _emit_list(o, h, lists[j])
        for j in sorted(lists):
            _emit_records(o, rec_at[j], lists[j])
        vb0 = o.align(0x10)
        for p, n, uv in body.verts + wheel.verts:
            o.put(struct.pack('<3fI2f', p[0], p[1], p[2], pack_normal(n), uv[0], uv[1]))
        vb1 = o.align(0x10)
        for i, (p, n, uv) in enumerate(body.verts):
            a, b2, wa, wb = sk.skin(p)
            o.put(struct.pack('<4H', a, b2, wa, wb))
        o.put(struct.pack('<4H', 0, 0, 255, 0) * len(wheel.verts))
        struct.pack_into('<III', o.b, lo + 0x48, 1, vb0 - lo, 0)
        struct.pack_into('<III', o.b, lo + 0x54, 1, vb1 - lo, 0)
        whole = _draws_for(body.groups, 0, anchor)
        recs = _emit_list(o, lo + 0x60, whole, inline=True)
        _emit_records(o, recs, whole)
        rep['lods'].append(dict(lod=k, vertices=nv, body_vertices=nb, body_triangles=body.tri_count(),
                                indices=sum(len(s) for _, s in whole)))
    # texture block
    t = o.align(0x80)
    th = bytearray(db[donor.tex['off']:donor.tex['off'] + 0x80])
    o.put(bytes(th))
    texels = o.put(texture.swizzle(bytes(tex['texels'])))
    if texels - t != 0x80:
        raise BuildError('texel alignment')
    npal = len(tex['palettes'])
    pal_offs = []
    for i, p in enumerate(tex['palettes']):
        ph = o.align(0x80)
        o.put(struct.pack('<III', 0x00030001, ph + 0x40 - t, 0) + bytes(0x40 - 0xC))
        o.put(texture.pal_bytes(p))
        pal_offs.append(ph)
    o.u32(t + 4, 0x80)
    for i in range(8):
        o.u32(t + 0x14 + 4 * i, (pal_offs[i] - t) if i < npal else 0)
    nm = tex_name.encode('ascii')[:23]
    o.b[t + 0x48:t + 0x60] = nm + bytes(0x18 - len(nm))
    o.b[t + 0x69] = npal
    o.u32(0x60, t)
    o.u32(0x64, 0)
    o.u32(0x68, 0)
    # emitters (donor structural data)
    for g in range(3):
        for s in range(6):
            o.u32(0x1664 + 0x18 * g + 4 * s, 0)
            o.b[0x16AC + 6 * g + s] = 0
    for g, s, p, c in donor.emitters:
        e = o.align(0x10)
        o.put(db[p:p + 0x30 * c])
        o.u32(0x1664 + 0x18 * g + 4 * s, e)
        o.b[0x16AC + 6 * g + s] = c
    # engine-sound descriptors (relative-pointer objects, copied whole)
    for at in (0x16DC, 0x16E0):
        o.u32(at, 0)
    for at in sorted(donor.deform, key=lambda a: donor.deform[a]['off']):
        D = donor.deform[at]
        e = o.align(0x10)
        o.put(db[D['off']:D['end']])
        o.u32(at, e)
    # header: LODs, bounds, radius
    for k in range(5):
        o.u32(0x4C + 4 * k, lod_offs[k] if k < 4 else 0)
    o.u32(0x10, 3)
    mn, mx = bb
    struct.pack_into('<8f', o.b, 0xE80, mx[0], mx[1], mx[2], 0.0, mn[0], mn[1], mn[2], mx[2])
    r_auth = max(math.sqrt(sum(c * c for c in v[0])) for v in body3.verts)
    d_r = struct.unpack_from('<f', db, 0x14)[0]
    L3 = donor.lods[-1]
    d_geo = max(math.sqrt(sum(c * c for c in struct.unpack_from('<3f', db, L3['vb0'] + 24 * i))) for i in range(L3['nv']))
    radius = max(r_auth, d_r * r_auth / d_geo)
    struct.pack_into('<f', o.b, 0x14, radius)
    end = o.align(0x800)
    if end == len(o.b) and len(o.b) % 0x800 == 0:
        pass
    o.u32(8, len(o.b))
    out = bytes(o.b)
    rep.update(size=len(out), slot_limit=SLOT_LIMIT, slot_free=SLOT_LIMIT - len(out), radius=radius,
               donor_radius=d_r, aabb=dict(min=mn, max=mx),
               donor_aabb=dict(max=struct.unpack_from('<3f', db, 0xE80), min=struct.unpack_from('<3f', db, 0xE90)),
               palettes=npal, texture_name=tex_name)
    if len(out) > SLOT_LIMIT:
        raise BuildError('model is %d bytes; the race-car slot holds %d (0x9D800): reduce LOD 0..2 detail' %
                         (len(out), SLOT_LIMIT))
    return out, rep


# ---------------------------------------------------------------- verification of a written file
def verify(data, ir=None):
    """Strict re-read (s6 bgvlib.parse + build round trip) + geometry decode checks against the IR."""
    m = bgvlib.parse(data)
    if bgvlib.build(m) != data:
        raise BuildError('bgvlib round trip differs')
    res = dict(lods=len(m.lods), regions=len(m.regions), gaps_nonzero=sum(1 for _, g in m.gaps if any(g)))
    if ir is not None:
        for k, L in enumerate(m.lods):
            body = ir['lods'][k]
            nb = len(body.verts)
            for i, (p, n, uv) in enumerate(body.verts):
                q = struct.unpack_from('<3fI2f', data, L['vb0'] + 24 * i)
                if q[:3] != tuple(struct.unpack('<3f', struct.pack('<3f', *p))) or \
                        q[4:] != tuple(struct.unpack('<2f', struct.pack('<2f', *uv))):
                    raise BuildError('LOD %d vertex %d differs' % (k, i))
                dn = unpack_normal(q[3])
                if sum((dn[j] - n[j]) ** 2 for j in range(3)) > (2.5 / 511) ** 2 * 3:
                    raise BuildError('LOD %d vertex %d normal error' % (k, i))
            want = {}
            for cls, tris in body.groups.items():
                want[cls] = sorted(_canon(t) for t in tris)
            got = {}
            for d in L['whole']['draws']:
                ix = list(struct.unpack_from('<%dH' % d['n'], data, d['off']))
                cls = {1: 'paint', 2: 'plain', 0x100: 'glass'}[d['flags'] & 0xFFFF]
                got.setdefault(cls, []).extend(_canon(t) for t in strip_tris(ix))
            for cls in got:
                got[cls] = sorted(got[cls])
            if {c: v for c, v in got.items() if v} != {c: v for c, v in want.items() if v}:
                raise BuildError('LOD %d: whole-list triangles differ from the IR' % k)
            if L['nd'] != L['nv']:
                raise BuildError('LOD %d: VB1 does not cover every vertex' % k)
        res['ir_checked'] = True
    return res
