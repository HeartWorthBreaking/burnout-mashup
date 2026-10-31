"""trackbuild.dxt - a small deterministic DXT1 encoder (opaque, 4-colour mode) + box-filter mip chain, and the PNG / RGBA
helpers the procedural texture generator uses. Pure Python; quality is adequate for test textures (endpoints = the two
pixels farthest apart along the block's luminance axis, then refined once by least squares on the chosen indices)."""
import struct


def c565(r, g, b):
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def d565(c):
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def _palette(c0, c1):
    a, b = d565(c0), d565(c1)
    return [a, b, tuple((2 * x + y + 1) // 3 for x, y in zip(a, b)), tuple((x + 2 * y + 1) // 3 for x, y in zip(a, b))]


def _err(p, q):
    return sum((x - y) * (x - y) for x, y in zip(p, q))


def encode_block(px):
    """px: 16 (r, g, b) -> 8 bytes DXT1 (4-colour mode: c0 > c1 always)"""
    lum = [(0.299 * r + 0.587 * g + 0.114 * b, i) for i, (r, g, b) in enumerate(px)]
    lo, hi = px[min(lum)[1]], px[max(lum)[1]]
    c0, c1 = c565(*hi), c565(*lo)
    if c0 == c1:                                   # flat block: any c1 < c0, all indices 0
        if c0 == 0:
            return struct.pack("<HHI", 1, 0, 0x55555555)  # c0=1 > c1=0, index 1 = black
        return struct.pack("<HHI", c0, c0 - 1 if c0 else 0, 0)
    if c0 < c1:
        c0, c1 = c1, c0
    pal = _palette(c0, c1)
    idx = [min(range(4), key=lambda k: _err(p, pal[k])) for p in px]
    bits = 0
    for i, k in enumerate(idx):
        bits |= k << (2 * i)
    return struct.pack("<HHI", c0, c1, bits)


def encode(w, h, rgb):
    """rgb: list of h rows of w (r, g, b) -> DXT1 bytes of one level (w, h multiples of 4 or < 4)"""
    out = bytearray()
    for by in range(0, max(h, 4), 4):
        for bx in range(0, max(w, 4), 4):
            blk = []
            for y in range(4):
                for x in range(4):
                    blk.append(rgb[min(by + y, h - 1)][min(bx + x, w - 1)])
            out += encode_block(blk)
    return bytes(out)


def downsample(w, h, rgb):
    nw, nh = max(1, w // 2), max(1, h // 2)
    out = []
    for y in range(nh):
        row = []
        for x in range(nw):
            ps = [rgb[min(2 * y + dy, h - 1)][min(2 * x + dx, w - 1)] for dy in (0, 1) for dx in (0, 1)]
            row.append(tuple(sum(p[k] for p in ps) // 4 for k in range(3)))
        out.append(row)
    return nw, nh, out


def chain(w, h, rgb, mips=None):
    """-> (texels of every level, mip count); full chain down to 1x1 unless mips is given"""
    n = 0
    s = max(w, h)
    while s:
        n += 1
        s //= 2
    mips = mips or n
    data = bytearray()
    for _ in range(mips):
        data += encode(w, h, rgb)
        w, h, rgb = downsample(w, h, rgb)
    return bytes(data), mips


def write_png(path, w, h, rgb):
    import zlib
    raw = b"".join(b"\0" + bytes(c for p in row for c in p) for row in rgb)

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
