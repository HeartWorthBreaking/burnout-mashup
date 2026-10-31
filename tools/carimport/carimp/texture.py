"""Car texture: authored RGBA image (+ optional paint mask) -> the car's single P8 texture + 1..8 palettes (paints).

Format facts (atlas CARS.md s1.2 / s2, retail survey): one 512x256 P8 texture per car, NV2A-swizzled texels, 1..8 palettes of
256 x D3DCOLOR (stored B, G, R, A); a paint = one palette; retail palettes differ only in a ramp of entries (COMPCAR1: 64..136)
used by the body paint, so decals in fixed entries keep their colours under every paint. The garage offers paints
0..min(count, 6)-1 (sub_000BE140); paints 7 / 8 only with the p4.1 GARAGE PAINT 7-8 setting.

Authoring rule (carimport):
  * texture = the glTF base-colour PNG, exactly 512 x 256 (refused otherwise - no silent resampling).
  * optional paint mask PNG (same size): texels with mask luminance >= 128 are PAINT texels. They are quantised to a
    64-entry luminance ramp at palette indices 64..127 (RAMP); every other texel is quantised (exact when <= free entries,
    else median cut) into the remaining entries 0..63 and 128..255.
  * paints = [(name, (r, g, b))]: palette p's ramp entry k = colour_p * level_k (level = the paint texels' luminance bucket);
    non-ramp entries are identical in every palette. Without a mask there is no ramp and exactly one palette.
  * alpha: the image alpha is copied into the palette (retail alpha varies per entry; its shader meaning is HYP).
"""
from . import png

W, H = 512, 256
RAMP0, RAMPN = 64, 64


class TexError(Exception):
    pass


def lum(c):
    return (299 * c[0] + 587 * c[1] + 114 * c[2]) // 1000


def _median_cut(colors, n):
    """colors: {rgba: count}; returns a list of <= n representative colours (deterministic)."""
    boxes = [sorted(colors.items())]
    while len(boxes) < n:
        best = None
        for i, bx in enumerate(boxes):
            if len(bx) < 2:
                continue
            rng = [max(c[0][k] for c in bx) - min(c[0][k] for c in bx) for k in range(4)]
            r = max(rng)
            if best is None or r > best[0]:
                best = (r, i, rng.index(r))
        if best is None or best[0] == 0:
            break
        _, i, ch = best
        bx = sorted(boxes[i], key=lambda c: (c[0][ch], c[0]))
        tot = sum(c[1] for c in bx)
        acc = 0
        cut = 1
        for j, c in enumerate(bx):
            acc += c[1]
            if acc * 2 >= tot:
                cut = max(1, min(len(bx) - 1, j + 1))
                break
        boxes[i:i + 1] = [bx[:cut], bx[cut:]]
    out = []
    for bx in boxes:
        tot = sum(c[1] for c in bx)
        out.append(tuple((sum(c[0][k] * c[1] for c in bx) + tot // 2) // tot for k in range(4)))
    return out


def _nearest(pal, c):
    best = None
    for i, p in pal:
        d = sum((p[k] - c[k]) ** 2 for k in range(4))
        if best is None or d < best[0]:
            best = (d, i)
    return best[1]


def build(image_png, mask_png=None, paints=None):
    """Returns dict(texels_linear (w*h indices), palettes [[(r,g,b,a)]*256], ramp=(first, count) or None, stats)."""
    w, h, mode, px, pal = png.read(image_png)
    if (w, h) != (W, H):
        raise TexError('texture is %dx%d; the car texture must be exactly %dx%d (resample it in the authoring tool)'
                       % (w, h, W, H))
    if mode == 'P':
        px = [pal[i] for i in px]
    mask = None
    if mask_png is not None:
        mw, mh, mm, mpx, mpal = png.read(mask_png)
        if (mw, mh) != (W, H):
            raise TexError('paint mask is %dx%d (must match the texture)' % (mw, mh))
        if mm == 'P':
            mpx = [mpal[i] for i in mpx]
        mask = [lum(c) >= 128 for c in mpx]
    paints = paints or []
    if mask is None and len(paints) > 1:
        raise TexError('%d paints declared but no paint mask: paints recolour only the masked ramp' % len(paints))
    if len(paints) > 8:
        raise TexError('%d paints: the format holds at most 8 palettes' % len(paints))
    if mask is not None and not paints:
        raise TexError('paint mask given but no paints declared')
    if mask is not None and not any(mask):
        raise TexError('paint mask selects no texel')
    # fixed (non-paint) colours
    fixed_idx = [i for i in range(256) if mask is None or not (RAMP0 <= i < RAMP0 + RAMPN)]
    counts = {}
    for i, c in enumerate(px):
        if mask is None or not mask[i]:
            counts[c] = counts.get(c, 0) + 1
    if len(counts) <= len(fixed_idx):
        reps = sorted(counts)
        exact = True
    else:
        reps = _median_cut(counts, len(fixed_idx))
        exact = False
    rep_slots = list(zip(fixed_idx, reps))
    lut = {}
    for c in counts:
        lut[c] = _nearest(rep_slots, c) if not exact else fixed_idx[reps.index(c)]
    base = [(0, 0, 0, 255)] * 256
    for i, c in rep_slots:
        base[i] = c
    tex = [0] * (W * H)
    ramp_alpha = [255] * RAMPN
    if mask is not None:
        acc = [[0, 0] for _ in range(RAMPN)]
        for i, c in enumerate(px):
            if mask[i]:
                k = lum(c) * RAMPN // 256
                tex[i] = RAMP0 + k
                acc[k][0] += c[3]
                acc[k][1] += 1
            else:
                tex[i] = lut[c]
        ramp_alpha = [(a // n if n else 255) for a, n in acc]
    else:
        for i, c in enumerate(px):
            tex[i] = lut[c]
    pals = []
    for name, rgb in (paints or [('base', None)]):
        p = list(base)
        if mask is not None:
            for k in range(RAMPN):
                lv = (k * 256 + 128) / (RAMPN * 256.0)      # bucket centre luminance 0..1
                p[RAMP0 + k] = tuple(min(255, int(round(rgb[j] * lv * 1.0))) for j in range(3)) + (ramp_alpha[k],)
        pals.append(p)
    err = 0
    for i, c in enumerate(px):
        if mask is None or not mask[i]:
            q = base[tex[i]]
            err = max(err, max(abs(q[k] - c[k]) for k in range(4)))
    return dict(texels=tex, palettes=pals, ramp=(RAMP0, RAMPN) if mask is not None else None,
                stats=dict(fixed_colours=len(counts), fixed_slots=len(fixed_idx), exact=exact, max_fixed_error=err,
                           paint_texels=sum(1 for m in (mask or []) if m), palettes=len(pals)))


def pal_bytes(p):
    """256 x (r, g, b, a) -> 0x400 bytes D3DCOLOR (B, G, R, A in memory)."""
    return bytes(v for c in p for v in (c[2], c[1], c[0], c[3]))


def pal_from_bytes(b):
    return [(b[4 * k + 2], b[4 * k + 1], b[4 * k], b[4 * k + 3]) for k in range(256)]


# ---------------------------------------------------------------- NV2A swizzle (Morton; same rule as s6 bgvlib, re-implemented)
_MT = {}


def _table(w, h):
    if (w, h) in _MT:
        return _MT[(w, h)]
    tbl = []
    for y in range(h):
        for x in range(w):
            o = bit = xb = yb = 0
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
    _MT[(w, h)] = tbl
    return tbl


def swizzle(lin, w=W, h=H):
    t = _table(w, h)
    out = bytearray(w * h)
    for i in range(w * h):
        out[t[i]] = lin[i]
    return bytes(out)


def unswizzle(data, w=W, h=H):
    t = _table(w, h)
    return bytes(data[t[i]] for i in range(w * h))
