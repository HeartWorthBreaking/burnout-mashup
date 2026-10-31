"""build_wbexe.py - builds "Burnout Mashup Workbench.exe" (the Workbench starter, wbstart.c; it sits in the mod kit folder and
starts workbench\\workbench.py) with llvm-mingw, deterministic (no timestamp, stripped), with the Workbench icon (drawn here:
the launcher's blue tile with a white gear ring instead of the chevrons; no image file). Adapted from the tester launcher's
build_exe.py.

    py -3 -B build_wbexe.py OUT.exe --cc PATH_TO\\x86_64-w64-mingw32-clang.exe   (default: llvm-mingw on PATH)

Writes OUT.exe and prints its sha256. Two builds of the same source give the same bytes (tests\\test_wbexe.py)."""
import hashlib
import math
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
    """the Workbench icon (rounded blue tile, a white gear ring: 8 teeth around a ring with a hole) as BGRA rows bottom-up,
    transparent outside the tile"""
    r = n * 0.22
    rows = []
    for y in range(n - 1, -1, -1):
        row = bytearray()
        for x in range(n):
            cx, cy = min(max(x, r), n - 1 - r), min(max(y, r), n - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                row += bytes((0, 0, 0, 0))
                continue
            dx, dy = (x + 0.5) / n - 0.5, (y + 0.5) / n - 0.5
            d = (dx * dx + dy * dy) ** 0.5
            a = (math.atan2(dy, dx) / (2 * math.pi) * 8) % 1.0          # 8 teeth
            gear = (0.12 <= d <= 0.27) or (0.27 < d <= 0.35 and 0.25 <= a <= 0.75)
            c = WHITE if gear else ACCENT
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
    with tempfile.TemporaryDirectory(prefix="wbstart_") as t:
        icof = os.path.join(t, "wb.ico")
        open(icof, "wb").write(ico())
        rc = os.path.join(t, "wbstart.rc")
        open(rc, "w", encoding="ascii").write(
            '1 ICON "wb.ico"\n'
            '1 VERSIONINFO FILEVERSION 1,0,0,0 PRODUCTVERSION 1,0,0,0\nBEGIN\n BLOCK "StringFileInfo"\n BEGIN\n'
            '  BLOCK "040904B0"\n  BEGIN\n   VALUE "FileDescription", "Burnout Mashup Workbench starter"\n'
            '   VALUE "ProductName", "Burnout Mashup Workbench"\n   VALUE "FileVersion", "1.0.0"\n   VALUE "OriginalFilename", '
            '"Burnout Mashup Workbench.exe"\n  END\n END\n BLOCK "VarFileInfo"\n BEGIN\n  VALUE "Translation", 0x409, 1200\n END\nEND\n')
        res = os.path.join(t, "wbstart.res.o")
        subprocess.run([windres, rc, "-O", "coff", "-o", res], check=True, cwd=t)
        subprocess.run([cc, "-O2", "-municode", "-mwindows", "-s", "-Wall", "-Wextra", "-Werror", "-Wl,--no-insert-timestamp",
                        "-ffile-prefix-map=%s=." % HERE, os.path.join(HERE, "wbstart.c"), res, "-o", out,
                        "-lshell32"], check=True)
    print("built %s sha256 %s" % (out, hashlib.sha256(open(out, "rb").read()).hexdigest()))


if __name__ == "__main__":
    main()
