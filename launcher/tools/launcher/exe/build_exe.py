"""build_exe.py - builds "Burnout Mashup.exe" (the launcher starter, bmstart.c) with llvm-mingw, deterministic (no timestamp,
stripped), with the Burnout Mashup icon (drawn here: the launcher's blue tile with two white chevrons; no image file).

    py -3 -B build_exe.py OUT.exe [--cc PATH_TO x86_64-w64-mingw32-clang.exe]   (default: llvm-mingw on PATH)

Writes OUT.exe and prints its sha256. Two builds of the same source give the same bytes (checked by tests\\test_exe.py)."""
import hashlib
import os
import struct
import subprocess
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_CC = "x86_64-w64-mingw32-clang.exe"         # llvm-mingw on PATH, or --cc FULL_PATH
BG, ACCENT, WHITE = (0x0B, 0x0F, 0x17), (0x1A, 0x6B, 0xDF), (0xFF, 0xFF, 0xFF)


def icon_pixels(n):
    """the bmtheme icon (rounded blue tile, two white speed chevrons) as BGRA rows bottom-up, transparent outside the tile"""
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


def main():
    out = os.path.abspath(sys.argv[1])
    cc = sys.argv[sys.argv.index("--cc") + 1] if "--cc" in sys.argv else DEF_CC
    if not os.path.isabs(cc):
        cc = shutil.which(cc) or cc
    windres = os.path.join(os.path.dirname(cc), "llvm-windres.exe")
    with tempfile.TemporaryDirectory(prefix="bmstart_") as t:
        icof = os.path.join(t, "bm.ico")
        open(icof, "wb").write(ico())
        rc = os.path.join(t, "bmstart.rc")
        open(rc, "w", encoding="ascii").write(
            '1 ICON "bm.ico"\n'
            '1 VERSIONINFO FILEVERSION 1,0,0,0 PRODUCTVERSION 1,0,0,0\nBEGIN\n BLOCK "StringFileInfo"\n BEGIN\n'
            '  BLOCK "040904B0"\n  BEGIN\n   VALUE "FileDescription", "Burnout Mashup launcher"\n'
            '   VALUE "ProductName", "Burnout Mashup"\n   VALUE "FileVersion", "1.0.0"\n   VALUE "OriginalFilename", '
            '"Burnout Mashup.exe"\n  END\n END\n BLOCK "VarFileInfo"\n BEGIN\n  VALUE "Translation", 0x409, 1200\n END\nEND\n')
        res = os.path.join(t, "bmstart.res.o")
        subprocess.run([windres, rc, "-O", "coff", "-o", res], check=True, cwd=t)
        subprocess.run([cc, "-O2", "-municode", "-mwindows", "-s", "-Wall", "-Wextra", "-Werror", "-Wl,--no-insert-timestamp",
                        "-ffile-prefix-map=%s=." % HERE, os.path.join(HERE, "bmstart.c"), res, "-o", out,
                        "-lshell32"], check=True)
    print("built %s sha256 %s" % (out, hashlib.sha256(open(out, "rb").read()).hexdigest()))


if __name__ == "__main__":
    main()
