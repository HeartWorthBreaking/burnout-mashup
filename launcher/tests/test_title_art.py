"""test_title_art.py - the shipped title: pictures only (every height the header may ask for, with clear around), no font file anywhere in the launcher, the licence of the font it does ship."""
import os
import struct
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = []
art = os.path.join(SRC, "art")
for th in (32, 48, 64, 80, 96, 128, 160, 192):
    p = os.path.join(art, "logo_%d.png" % th)
    if not os.path.isfile(p):
        bad.append("missing " + p)
        continue
    b = open(p, "rb").read()
    w, h, depth, kind = struct.unpack(">IIBB", b[16:26])
    if b[:8] != b"\x89PNG\r\n\x1a\n" or h != th or kind != 6 or w < 2 * h:
        bad.append("not the title: %s %s" % (p, (w, h, kind)))
for dp, _, fs in os.walk(SRC):
    for f in fs:
        if f.lower().endswith((".otf", ".ttf")) and "kenyan" in f.lower():
            bad.append("the licensed font must not ship: " + f)
b = open(os.path.join(SRC, "fonts", "RobotoCondensed-Medium.ttf"), "rb").read()
if b[:4] != bytes((0, 1, 0, 0)) or "Open Font License" not in open(os.path.join(SRC, "fonts", "OFL.txt"), encoding="utf-8").read():
    bad.append("Roboto or its licence")
print("\n".join(["FAIL " + x for x in bad] + ["title art: %d problem(s)" % len(bad)]))
sys.exit(1 if bad else 0)
