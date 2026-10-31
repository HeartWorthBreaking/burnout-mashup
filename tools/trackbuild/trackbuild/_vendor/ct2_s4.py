"""ct2_s4 - Burnout 3 (Xbox) GAMEDATA.BGD route section S4 (CB4AILanesDataStruct, version 3): parser, layout probe and
(after the probe) identity writer. Field names follow the PS2 project's bolib.routes / racing_line (read only) and are
re-verified here on the Xbox files.
  header 9 u32: version 3, lane count, slice count, corner count, zone count, ptr lanes, ptr distances, ptr corners, ptr positions
  0x24 zone slots: 8 x 16 B (+0 f32, +4 f32, +8 f32, +12 u32 first slice) + 12 B
  positions: vec4 node positions (rung ends)
  lanes: n x 16 B {ptr rungs, ptr dims, ptr segments (each relative to the ENTRY), u32 count | flags << 16} + arrays:
         rungs (count + 1) x {u16 node, u16 node}; dims count x {f32 cumulative length, f32 width};
         segments count x {s16 slice, u8 corner, u8 type, u8 left lane, u8 right lane, u16 left seg, u16 right seg}
  distances: slice count x {f32 running distance, u32}
  corners: corner count x 12 B {u16 first, u16 middle, u16 last, u16, u8 lane, u8, u16}
   py -3 -B ct2_s4.py probe US/C3_V1     (layout of the arrays inside the lane chunk)"""
import struct
import sys
from pathlib import Path

BASE = None   # vendored copy: no retail folder (the research CLI functions are not used by trackbuild)


def sections(bgd):
    n = struct.unpack_from("<I", bgd, 0x260)[0]
    secs = list(struct.unpack_from("<5I", bgd, 0x264))
    return n, secs + [len(bgd)]


def s4_of(bgd):
    n, secs = sections(bgd)
    return secs[4], secs[5]


def header(b):
    return dict(zip(("version", "lanes", "slices", "corners", "zones", "p_lanes", "p_dist", "p_corners", "p_pos"), struct.unpack_from("<9I", b, 0)))


def lanes(b, h):
    out = []
    for i in range(h["lanes"]):
        e = h["p_lanes"] + 16 * i
        a, d, s, nf = struct.unpack_from("<4I", b, e)
        out.append({"i": i, "entry": e, "rungs": e + a, "dims": e + d, "segs": e + s, "n": nf & 0xFFFF, "flags": nf >> 16})
    return out


def probe(tid):
    bgd = (BASE / tid / "Gamedata.bgd").read_bytes()
    lo, hi = s4_of(bgd)
    b = bgd[lo:hi]
    h = header(b)
    print(tid, "S4 at 0x%X size 0x%X" % (lo, hi - lo), h)
    L = lanes(b, h)
    for l in L[:8]:
        print("  lane %2d n %4d flags 0x%04X rungs 0x%X dims 0x%X segs 0x%X ends 0x%X" % (
            l["i"], l["n"], l["flags"], l["rungs"], l["dims"], l["segs"], l["segs"] + 10 * l["n"]))
    ends = sorted([(l["rungs"], "R", l["i"], 4 * (l["n"] + 1)) for l in L] + [(l["dims"], "D", l["i"], 8 * l["n"]) for l in L] +
                  [(l["segs"], "S", l["i"], 10 * l["n"]) for l in L])
    gaps = []
    prev = h["p_lanes"] + 16 * h["lanes"]
    for off, k, i, ln in ends:
        gaps.append((k, i, off - prev))
        prev = off + ln
    print("  array order (first 12):", [(k, i, g) for k, i, g in gaps[:12]])
    print("  gap histogram:", sorted({g for _, _, g in gaps}))
    print("  lanes end 0x%X, distances 0x%X, corners 0x%X, positions 0x%X..0x%X" % (prev, h["p_dist"], h["p_corners"], h["p_pos"], h["p_lanes"]))
    print("  trailing after corners:", len(b) - (h["p_corners"] + 12 * h["corners"]), "nonzero", any(b[h["p_corners"] + 12 * h["corners"]:]))


if __name__ == "__main__":
    if sys.argv[1] == "probe":
        probe(sys.argv[2])
