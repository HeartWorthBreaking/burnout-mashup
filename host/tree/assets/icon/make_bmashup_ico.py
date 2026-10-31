"""make_bmashup_ico.py - writes the Burnout Mashup icon (BMASHUP_ICON.md): the launcher's rounded blue tile with two white
speed chevrons, drawn in code (copy of the tester launcher's build_exe.py icon_pixels / ico). Deterministic.

    py -3 -B make_bmashup_ico.py OUT.ico"""
import struct
import sys

ACCENT, WHITE = (0x1A, 0x6B, 0xDF), (0xFF, 0xFF, 0xFF)


def icon_pixels(n):
    """rounded blue tile, two white speed chevrons, as BGRA rows bottom-up, transparent outside the tile"""
    r = n * 0.22
    rows = []
    for y in range(n - 1, -1, -1):
        row = bytearray()
        for x in range(n):
            cx, cy = min(max(x, r), n - 1 - r), min(max(y, r), n - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                row += bytes((0, 0, 0, 0))
                continue
            u, v = x / n, abs(y / n - 0.5)
            chev = any(0 <= (u - off - v) <= 0.13 for off in (0.20, 0.45)) and v < 0.30
            c = WHITE if chev else ACCENT
            row += bytes((c[2], c[1], c[0], 255))
        rows.append(bytes(row))
    return b"".join(rows)


def ico(sizes=(16, 32, 48, 256)):
    imgs = []
    for n in sizes:
        px = icon_pixels(n)
        mask = bytes(((n + 31) // 32) * 4 * n)
        bih = struct.pack("<IiiHHIIiiII", 40, n, 2 * n, 1, 32, 0, len(px) + len(mask), 0, 0, 0, 0)
        imgs.append((n, bih + px + mask))
    out = struct.pack("<HHH", 0, 1, len(imgs))
    off = 6 + 16 * len(imgs)
    for n, data in imgs:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    return out + b"".join(d for _, d in imgs)


if __name__ == "__main__":
    open(sys.argv[1], "wb").write(ico())
