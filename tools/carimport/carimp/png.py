"""Minimal PNG reader / writer (pure Python, zlib). 8-bit depth only.

read(path_or_bytes) -> (w, h, mode, pixels, palette)
    mode 'RGBA' : pixels = list of (r, g, b, a) row-major
    mode 'P'    : pixels = list of palette indices, palette = list of (r, g, b, a)
Colour types accepted: 0 (grey), 2 (RGB), 3 (indexed, with optional tRNS), 4 (grey+alpha), 6 (RGBA); bit depth 8 only
(16-bit, sub-byte depths and interlaced files are REFUSED with PngError - never approximated).
write_rgba(path, w, h, pixels) / write_p(path, w, h, indices, palette)
"""
import struct
import zlib


class PngError(Exception):
    pass


SIG = b'\x89PNG\r\n\x1a\n'


def _chunks(b):
    if b[:8] != SIG:
        raise PngError('not a PNG file')
    o = 8
    while o < len(b):
        if o + 8 > len(b):
            raise PngError('truncated chunk header')
        n, t = struct.unpack_from('>I4s', b, o)
        d = b[o + 8:o + 8 + n]
        if len(d) != n:
            raise PngError('truncated chunk %r' % t)
        crc = struct.unpack_from('>I', b, o + 8 + n)[0]
        if zlib.crc32(t + d) & 0xFFFFFFFF != crc:
            raise PngError('CRC mismatch in chunk %r' % t)
        yield t, d
        o += 12 + n
        if t == b'IEND':
            return
    raise PngError('no IEND')


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read(src):
    b = src if isinstance(src, (bytes, bytearray)) else open(src, 'rb').read()
    ihdr = None
    idat = []
    plte = None
    trns = None
    for t, d in _chunks(bytes(b)):
        if t == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', d)
        elif t == b'PLTE':
            plte = d
        elif t == b'tRNS':
            trns = d
        elif t == b'IDAT':
            idat.append(d)
    if ihdr is None:
        raise PngError('no IHDR')
    w, h, depth, ct, comp, filt, inter = ihdr
    if depth != 8:
        raise PngError('bit depth %d not supported (8 only)' % depth)
    if inter != 0:
        raise PngError('interlaced PNG not supported')
    if comp != 0 or filt != 0:
        raise PngError('unknown compression / filter method')
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ct)
    if bpp is None:
        raise PngError('colour type %d not supported' % ct)
    raw = zlib.decompress(b''.join(idat))
    stride = w * bpp
    if len(raw) != h * (stride + 1):
        raise PngError('image data size mismatch')
    out = bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(a, prev[i], c)) & 0xFF
        elif ft != 0:
            raise PngError('bad filter type %d' % ft)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    if ct == 3:
        if plte is None or len(plte) % 3:
            raise PngError('indexed PNG without a valid PLTE')
        n = len(plte) // 3
        pal = []
        for i in range(n):
            a = trns[i] if trns is not None and i < len(trns) else 255
            pal.append((plte[3 * i], plte[3 * i + 1], plte[3 * i + 2], a))
        px = list(out)
        if px and max(px) >= n:
            raise PngError('palette index beyond PLTE')
        return w, h, 'P', px, pal
    px = []
    for i in range(w * h):
        o = i * bpp
        if ct == 0:
            v = out[o]
            px.append((v, v, v, 255))
        elif ct == 4:
            v = out[o]
            px.append((v, v, v, out[o + 1]))
        elif ct == 2:
            px.append((out[o], out[o + 1], out[o + 2], 255))
        else:
            px.append((out[o], out[o + 1], out[o + 2], out[o + 3]))
    return w, h, 'RGBA', px, None


def _chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)


def _write(path, w, h, ct, rows, extra=b''):
    raw = b''.join(b'\0' + r for r in rows)
    data = SIG + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, ct, 0, 0, 0)) + extra + \
        _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b'')
    if path is None:
        return data
    with open(path, 'wb') as f:
        f.write(data)
    return data


def write_rgba(path, w, h, pixels):
    rows = []
    for y in range(h):
        rows.append(bytes(c for p in pixels[y * w:(y + 1) * w] for c in (p[0], p[1], p[2], p[3] if len(p) > 3 else 255)))
    return _write(path, w, h, 6, rows)


def write_p(path, w, h, indices, palette):
    if len(palette) > 256:
        raise PngError('palette > 256')
    plte = b''.join(bytes(p[:3]) for p in palette)
    extra = _chunk(b'PLTE', plte)
    if any(len(p) > 3 and p[3] != 255 for p in palette):
        extra += _chunk(b'tRNS', bytes(p[3] if len(p) > 3 else 255 for p in palette))
    rows = [bytes(indices[y * w:(y + 1) * w]) for y in range(h)]
    return _write(path, w, h, 3, rows, extra)
