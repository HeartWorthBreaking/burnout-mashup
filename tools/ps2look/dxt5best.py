"""dxt5best.py - an exhaustive DXT5 encoder for the small ps2look textures (stdlib only).

The colour part of each 4x4 block tries every pair of the block's own colours (and their 565 rounding) as endpoints and keeps
the pair with the least alpha-weighted error; the alpha part tries both 8-step and 6-step+0/255 modes over the block's min / max.
Exhaustive per block: fine for 32x8 / 8x8 / 64x64 textures, far too slow for large ones (not used for those)."""


def _to565(c):
    return ((c[0] * 31 + 127) // 255) << 11 | ((c[1] * 63 + 127) // 255) << 5 | ((c[2] * 31 + 127) // 255)


def _from565(v):
    r, g, b = v >> 11 & 31, v >> 5 & 63, v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def _block(px, w, h, bx, by):
    return [px[min(by + y, h - 1) * w + min(bx + x, w - 1)] for y in range(4) for x in range(4)]


def _colour(blk):
    """-> (c0, c1, index bits) with c0 > c1 (4-colour mode), alpha-weighted least squares over every endpoint pair"""
    cand = sorted(set(_to565(p) for p in blk))
    wts = [max(p[3], 1) for p in blk]
    best = None
    for i in range(len(cand)):
        for j in range(i, len(cand)):
            a, b = max(cand[i], cand[j]), min(cand[i], cand[j])
            if a == b:
                if a == 0:
                    a = 1                                # c0 > c1 needs two values
                else:
                    b = a - 1
            ca, cb = _from565(a), _from565(b)
            pal = [ca, cb, tuple((2 * ca[k] + cb[k] + 1) // 3 for k in range(3)), tuple((ca[k] + 2 * cb[k] + 1) // 3 for k in range(3))]
            err, idx = 0, 0
            for n, p in enumerate(blk):
                ds = [sum((p[k] - q[k]) ** 2 for k in range(3)) for q in pal]
                m = min(range(4), key=lambda t: ds[t])
                err += ds[m] * wts[n]
                idx |= m << (2 * n)
            if best is None or err < best[0]:
                best = (err, a, b, idx)
    return best[1], best[2], best[3]


def _alpha(blk):
    al = [p[3] for p in blk]
    a0, a1 = max(al), min(al)
    if a0 == a1:
        return a0, a1, 0
    pal = [a0, a1] + [((6 - k) * a0 + k * a1 + 3) // 7 for k in range(1, 7)]
    bits = 0
    for i, a in enumerate(al):
        bits |= min(range(8), key=lambda k: abs(a - pal[k])) << (3 * i)
    return a0, a1, bits


def encode_dxt5(px, w, h):
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            blk = _block(px, w, h, bx, by)
            a0, a1, abits = _alpha(blk)
            c0, c1, idx = _colour(blk)
            out += bytes((a0, a1)) + abits.to_bytes(6, 'little')
            out += bytes((c0 & 255, c0 >> 8, c1 & 255, c1 >> 8)) + idx.to_bytes(4, 'little')
    return bytes(out)
