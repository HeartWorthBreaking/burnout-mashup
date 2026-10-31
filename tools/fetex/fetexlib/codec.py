"""fetex: pixel codecs - NV2A swizzle (P8), DXT1 / DXT5 decode + encode, palette helpers. Pure Python, deterministic.
Pixels are lists of (r, g, b, a) tuples, row-major."""

_MT = {}


def _morton(w, h):
    # NV2A swizzle: interleave x / y bits while both have bits left, then the larger dimension's bits (atlas bgvlib.py,
    # verified visually on car liveries by s6 and here on the retail garage photos)
    t = _MT.get((w, h))
    if t:
        return t
    t = []
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
            t.append(o)
    _MT[(w, h)] = t
    return t


def unswizzle(data, w, h):
    t = _morton(w, h)
    return bytes(data[t[i]] for i in range(w * h))


def swizzle(lin, w, h):
    t = _morton(w, h)
    out = bytearray(w * h)
    for i in range(w * h):
        out[t[i]] = lin[i]
    return bytes(out)


def palette_rgba(pal):
    """256 x BGRA bytes -> list of (r, g, b, a)"""
    return [(pal[4 * i + 2], pal[4 * i + 1], pal[4 * i], pal[4 * i + 3]) for i in range(len(pal) // 4)]


def palette_bytes(cols):
    out = bytearray()
    for r, g, b, a in cols:
        out += bytes((b, g, r, a))
    return bytes(out)


def decode_p8(texels, pal, w, h):
    cols = palette_rgba(pal)
    idx = unswizzle(texels, w, h)
    return [cols[i] if i < len(cols) else (0, 0, 0, 0) for i in idx]


def _c565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def _to565(c):
    r, g, b = c[:3]
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _dxt1_colors(c0, c1, force4):
    a, b = _c565(c0), _c565(c1)
    if c0 > c1 or force4:
        return [a + (255,), b + (255,), tuple((2 * x + y + 1) // 3 for x, y in zip(a, b)) + (255,),
                tuple((x + 2 * y + 1) // 3 for x, y in zip(a, b)) + (255,)]
    return [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]


def decode_dxt(data, w, h, fmt5):
    px = [(0, 0, 0, 0)] * (w * h)
    bs = 16 if fmt5 else 8
    o = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            alpha = None
            if fmt5:
                a0, a1 = data[o], data[o + 1]
                bits = int.from_bytes(data[o + 2:o + 8], 'little')
                if a0 > a1:
                    al = [a0, a1] + [((6 - k) * a0 + k * a1 + 3) // 7 for k in range(1, 7)]
                else:
                    al = [a0, a1] + [((4 - k) * a0 + k * a1 + 2) // 5 for k in range(1, 5)] + [0, 255]
                alpha = [al[(bits >> (3 * i)) & 7] for i in range(16)]
                co = o + 8
            else:
                co = o
            c0 = data[co] | data[co + 1] << 8
            c1 = data[co + 2] | data[co + 3] << 8
            idx = int.from_bytes(data[co + 4:co + 8], 'little')
            cols = _dxt1_colors(c0, c1, fmt5)
            for i in range(16):
                x, y = bx + (i & 3), by + (i >> 2)
                if x < w and y < h:
                    c = cols[(idx >> (2 * i)) & 3]
                    if alpha is not None:
                        c = c[:3] + (alpha[i],)
                    px[y * w + x] = c
            o += bs
    return px


def _block(px, w, h, bx, by):
    return [px[min(by + (i >> 2), h - 1) * w + min(bx + (i & 3), w - 1)] for i in range(16)]


def _encode_color(blk):
    """endpoints = the extremes along the block's principal luminance axis (deterministic range fit), 4-colour mode"""
    def lum(c):
        return 2 * c[0] + 4 * c[1] + c[2]
    lo = min(blk, key=lum)
    hi = max(blk, key=lum)
    c0, c1 = _to565(hi), _to565(lo)
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return c0, c1, 0
    cols = _dxt1_colors(c0, c1, True)
    idx = 0
    for i, p in enumerate(blk):
        best = min(range(4), key=lambda k: sum((p[j] - cols[k][j]) ** 2 for j in range(3)))
        idx |= best << (2 * i)
    return c0, c1, idx


def encode_dxt1(px, w, h):
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            c0, c1, idx = _encode_color(_block(px, w, h, bx, by))
            out += bytes((c0 & 255, c0 >> 8, c1 & 255, c1 >> 8)) + idx.to_bytes(4, 'little')
    return bytes(out)


def encode_dxt5(px, w, h):
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            blk = _block(px, w, h, bx, by)
            al = [p[3] for p in blk]
            a0, a1 = max(al), min(al)
            if a0 == a1:
                bits = 0
            else:
                pal = [a0, a1] + [((6 - k) * a0 + k * a1 + 3) // 7 for k in range(1, 7)]
                bits = 0
                for i, a in enumerate(al):
                    bits |= min(range(8), key=lambda k: abs(a - pal[k])) << (3 * i)
            c0, c1, idx = _encode_color(blk)
            out += bytes((a0, a1)) + bits.to_bytes(6, 'little')
            out += bytes((c0 & 255, c0 >> 8, c1 & 255, c1 >> 8)) + idx.to_bytes(4, 'little')
    return bytes(out)


def quantize(px, ncol=256):
    """deterministic median-cut palette for P8: returns (palette [(r,g,b,a)] * 256, indices)"""
    uniq = sorted(set(px))
    if len(uniq) <= ncol:
        pal = uniq + [(0, 0, 0, 0)] * (ncol - len(uniq))
        m = {c: i for i, c in enumerate(uniq)}
        return pal, [m[c] for c in px]
    boxes = [uniq]
    while len(boxes) < ncol:
        boxes.sort(key=lambda bx: -len(bx))
        bx = boxes.pop(0)
        if len(bx) < 2:
            boxes.append(bx)
            break
        ch = max(range(4), key=lambda k: max(c[k] for c in bx) - min(c[k] for c in bx))
        bx = sorted(bx, key=lambda c: (c[ch], c))
        boxes += [bx[:len(bx) // 2], bx[len(bx) // 2:]]
    boxes.sort(key=lambda bx: bx[0])
    pal = [tuple(sum(c[k] for c in bx) // len(bx) for k in range(4)) for bx in boxes]
    m = {}
    for i, bx in enumerate(boxes):
        for c in bx:
            m[c] = i
    pal += [(0, 0, 0, 0)] * (ncol - len(pal))
    return pal, [m[c] for c in px]
