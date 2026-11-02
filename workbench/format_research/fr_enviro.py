"""fr_enviro - read-only parser for Burnout 3 Xbox ENVIRO.DAT (sky / fog / sun environment). Unknown bytes are kept;
serialize() rebuilds the file byte for byte.

Layout (WM-3 wm3_convert.parse_enviro, KB XBOX_TRACK_FORMATS "enviro.dat"; 36 / 36 retail folders that have the file):
  0x00..0xB0 header (44 words, see FIELDS) | 4 texture records at the pointers +0x98 / +0x9C / +0xA0 / +0xA4 (file
  offsets, 0x80-aligned): 0x80-B D3D record (+0x00 Common 0x00040001, +0x04 Data 0x80, +0x0C format word, +0x34 code /
  w / h, B3 tail +0x40 u32, +0x44 f32, +0x48 name[32], +0x68 mips (| 0x100 for P8)) + texels (+ for P8 code 0x0B a
  0x40-B palette record and 0x400 B of entries) | zero pad. +0xA8 = 0x45440002, +0xAC = file size.

Consumer (Takedawn generated code, read only): loader sub_001888F0 (string "enviro.dat", object at 0x60E040, called from
sub_00014860 and the track system set-up sub_001AA100) reads the file, rebases the 4 texture pointers (sub_00188880) and
copies the 0xB0 header verbatim into the object (sub_00188C00). See FINDINGS.md for which fields have consumers.
"""
import struct

from fr_common import Reader, need, place

VERSION = 0x45440002
PTRS = (0x98, 0x9C, 0xA0, 0xA4)
SLOT = {0x98: "sky gradient (names *SkyGradient*; -> global 0x45BC10, bound by the sky-dome draw sub_001891F0)",
        0x9C: "clouds (names *Sky_Clouds*; -> global 0x45D11C)", 0xA0: "cloud env map (envmapclouds; -> global 0x45D118)",
        0xA4: "sun sprite, P8 (names *Sun*; the loader tests this pointer)"}
P8 = 0x0B
DXT_BLOCK = {0x0C: 8, 0x0E: 16, 0x0F: 16}

# header fields: (offset, format, name, evidence). Names are working labels; "CODE" = consumer read in generated code.
FIELDS = [
    (0x00, "<4f", "colour_a_rgb0", "copied to per-view copy +0x10; consumer not traced (HYP fog / ambient colour)"),
    (0x10, "<f", "distance_a", "CODE sub_00188D70: written every frame to view struct 0x4D6170+0x260 (+0xA0 per view); HYP fog distance"),
    (0x14, "<3f", "w14_w18_w1c", "copied into the per-view copy; values 0.15..0.6 / 0 / 0.6..1.1; consumer not traced"),
    (0x20, "<4f", "w20_vec", "CODE: copy +0x30 (= +0x20) passed with the sun draw (sub_00189040 / sub_00188EE0 / sub_00189150)"),
    (0x30, "<4f", "colour_b_rgb0", "non-zero only on EU/M2 (second fog / haze colour, HYP); consumer not traced"),
    (0x40, "<4f", "w40_vec", "EU/M2: 80, 1, 0, 0.6 (HYP haze distance / strength); consumer not traced"),
    (0x50, "<4f", "w50_vec", "1, 0, 0, 1 on every track seen; consumer not traced"),
    (0x60, "<4f", "light_colour_rgb0", "CODE: read absolute 0x60E0A0 by sub_000393C0 (track material render states), sub_0003A3C0 "
     "(reflective material set-up), sub_00031AB0 (vehicle draw), sub_0017EE00"),
    (0x70, "<4f", "sun_colour_rgb0", "CODE: +0x70..+0x78 passed to the sun / flare draw (sub_00189040, sub_00188EE0, sub_00188F80, sub_00189150)"),
    (0x80, "<4f", "sun_direction", "CODE: normalised at load (sub_00011570) and used as the sun direction by the sky / sun draw; w = 0x0012FB40 stamp"),
    (0x90, "<f", "sun_size", "CODE: multiplied at load by the int at 0x4D6170, then passed with 12.0 to sub_00032DC0"),
    (0x94, "<I", "w94", "0 on every track seen"),
]


def tex_size(fw):
    code, mips = (fw >> 8) & 0xFF, (fw >> 16) & 0xF
    lw, lh = (fw >> 20) & 0xF, (fw >> 24) & 0xF
    n = 0
    for m in range(mips):
        w, h = max(1, (1 << lw) >> m), max(1, (1 << lh) >> m)
        if code == P8:
            n += w * h
        else:
            need(code in DXT_BLOCK, "texture format 0x%02X" % code)
            n += max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * DXT_BLOCK[code]
    return n


def parse(d):
    need(0x1000 <= len(d) <= 0x200000 and len(d) % 0x1000 == 0, "enviro size 0x%X" % len(d))
    r = Reader(d)
    need(r.u32(0xA8) == VERSION and r.u32(0xAC) == len(d), "enviro +0xA8 / +0xAC")
    hdr = r.take(0, 0xB0, "header")
    fields = {}
    for off, fmt, name, _ in FIELDS:
        v = struct.unpack_from(fmt, hdr, off)
        fields[name] = v if len(v) > 1 else v[0]
    tex = []
    for p in PTRS:
        t = struct.unpack_from("<I", hdr, p)[0]
        need(t % 0x80 == 0 and 0xB0 <= t and t + 0x80 <= len(d), "texture pointer 0x%X" % t)
        h = r.take(t, 0x80, "texture record")
        common, data, lock, fw = struct.unpack_from("<4I", h, 0)
        need(common == 0x00040001 and data == 0x80, "texture 0x%X header" % t)
        code, mips = (fw >> 8) & 0xFF, (fw >> 16) & 0xF
        size = tex_size(fw)
        body_n = size + (0x440 if code == P8 else 0)
        body = r.take(t + 0x80, body_n, "texels")
        tex.append({"slot": p, "at": t, "rec": h, "body": body, "code": code, "mips": mips,
                    "w": 1 << ((fw >> 20) & 0xF), "h": 1 << ((fw >> 24) & 0xF),
                    "name": h[0x48:0x68].split(b"\0")[0].decode("ascii", "replace"),
                    "tail_f44": struct.unpack_from("<f", h, 0x44)[0]})
    return {"size": len(d), "header": hdr, "fields": fields, "tex": tex, "gaps": r.gaps(), "claimed": r.claimed()}


def serialize(o):
    hdr = bytearray(o["header"])
    for off, fmt, name, _ in FIELDS:          # decoded fields win over the raw header copy
        v = o["fields"][name]
        struct.pack_into(fmt, hdr, off, *(v if isinstance(v, tuple) else (v,)))
    pieces = [(0, bytes(hdr))]
    for t in o["tex"]:
        pieces.append((t["at"], t["rec"]))
        pieces.append((t["at"] + 0x80, t["body"]))
    pieces += o["gaps"]
    return place(o["size"], pieces)


def summary(o):
    f = o["fields"]
    r4 = lambda v: [round(x, 4) for x in v] if isinstance(v, tuple) else round(v, 4)
    return {"fields": {k: r4(v) for k, v in f.items()}, "textures": [{"slot": "0x%X" % t["slot"], "code": "0x%02X" % t["code"],
            "w": t["w"], "h": t["h"], "mips": t["mips"], "name": t["name"]} for t in o["tex"]], "gaps": len(o["gaps"]),
            "records": 1 + len(o["tex"])}


if __name__ == "__main__":
    import json
    import sys
    from fr_common import read_ro
    d = read_ro(sys.argv[1])
    o = parse(d)
    print(json.dumps(summary(o), indent=1))
    print("identical:", serialize(o) == d)
