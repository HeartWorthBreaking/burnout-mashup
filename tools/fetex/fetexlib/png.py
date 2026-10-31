"""fetex: minimal PNG reader / writer (8-bit RGB / RGBA / grey / palette, non-interlaced), zlib only."""
import struct
import zlib


def write(path, w, h, px):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for r, g, b, a in px[y * w:(y + 1) * w]:
            raw += bytes((r, g, b, a))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(data)


def read(path):
    b = open(path, 'rb').read()
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('%s: not a PNG' % path)
    o, idat, plte, trns = 8, b'', None, None
    w = h = depth = ctype = 0
    while o < len(b):
        n, t = struct.unpack_from('>I4s', b, o)
        d = b[o + 8:o + 8 + n]
        if t == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', d)
            if depth != 8 or inter:
                raise ValueError('%s: only 8-bit non-interlaced PNG' % path)
        elif t == b'PLTE':
            plte = d
        elif t == b'tRNS':
            trns = d
        elif t == b'IDAT':
            idat += d
        o += 12 + n
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * ch
    prev = bytearray(stride)
    px = []
    p = 0
    for y in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            up = prev[i]
            c = prev[i - ch] if i >= ch else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + up) & 255
            elif f == 3:
                line[i] = (line[i] + (a + up) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                pr = a if pa <= pb and pa <= pc else up if pb <= pc else c
                line[i] = (line[i] + pr) & 255
        prev = line
        for x in range(w):
            q = line[x * ch:(x + 1) * ch]
            if ctype == 6:
                px.append(tuple(q))
            elif ctype == 2:
                px.append((q[0], q[1], q[2], 255))
            elif ctype == 0:
                px.append((q[0], q[0], q[0], 255))
            elif ctype == 4:
                px.append((q[0], q[0], q[0], q[1]))
            else:
                i = q[0]
                px.append((plte[3 * i], plte[3 * i + 1], plte[3 * i + 2], trns[i] if trns and i < len(trns) else 255))
    return w, h, px
