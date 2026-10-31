"""ps2look: build the "PS2 look: shadows and sparks" mod from the user's OWN Burnout 3 PS2 disc (local conversion only).

  py -3 -B ps2look.py --ps2-global PATH\\GLOBAL.TXD --out MOD_DIR
  py -3 -B ps2look.py --ps2-root EXTRACTED_DISC_DIR --out MOD_DIR      (finds DATA\\GLOBAL.TXD case-insensitively)
  options: --previews DIR (PNG previews of the decoded textures), --xbox-global PATH (adds the Xbox DXT5 versions to the
           previews for comparison), --force (overwrite an existing global_ps2.txd / mod.toml in MOD_DIR)

Decodes blobbyshadow (64x64 PSMT8, 256-colour CLUT), fxspark (32x8 CT32), fxscrape (64x64 PSMT4, 16-colour CLUT) and
fxpopcornspark (8x8 CT32) exactly (ps2tex.py), writes MOD_DIR\\global_ps2.txd (Xbox Criterion TXD, the four textures under the
same names as P8 = 8-bit index + 256 A8R8G8B8 palette, 1 mip, lossless: every texture has <= 256 colours) and MOD_DIR\\mod.toml
([bmashup.textures] class "global"). The TXD is checked by fetexlib's strict reader (the same layout as the host's
bm_fetex_parse.inc) and decoded back pixel for pixel before anything is written.

The output is the user's own game art (EA's): it is built on the user's PC from their own disc and must stay there - never
copy it into a package, a repository or an upload. Pure Python 3 (standard library + gp\\tools\\fetex\\fetexlib)."""
import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'fetex')]
import dxt5best                                # noqa: E402
import ps2tex                                  # noqa: E402
from fetexlib import codec, png, txd           # noqa: E402

NAMES = ('blobbyshadow', 'fxspark', 'fxscrape', 'fxpopcornspark')
TXD_NAME = 'global_ps2.txd'
MOD_TOML = '''# PS2 look: shadows and sparks - built LOCALLY by gp\\tools\\ps2look from your own Burnout 3 PS2 disc.
# global_ps2.txd holds your own disc's PS2 art: keep it on this PC (never share, upload or package it).
id = "bmashup.ps2-look"
name = "PS2 look: shadows and sparks"
version = "1.0.0"
description = "The PS2 versions of the car shadow (blobbyshadow) and the spark / scrape textures (fxspark, fxscrape, fxpopcornspark), converted on your PC from your own PS2 disc. Nothing of EA's is shipped with this mod."

[bmashup]
platform = ">=0.1.9"
requires = ["bmashup.textures>=1", "bmashup.tune>=1"]

[bmashup.textures]
version = 1
txd = "global_ps2.txd"
class = "global"

# the one spark value the PS2 version differs in (fx record 0 +0x58: PS2 0.017, Xbox 0.012; host patch 123), and the car shadow's
# alpha test: the PS2 draws every shadow pixel (TEST_1 ATST = ALWAYS), the Xbox turns the alpha test on and inherits its reference
# (0x40, GREATER: the soft rim is cut) from the previous draw (a harder, tighter shadow; host patch 129).
#
# SHADOW SETTINGS - change them in the game: MODS > this mod > MOD SETTINGS (the "sliders" below; the value you choose is saved in
# plugin-settings.toml and wins over the "set" default; the shadow rows change at once, the next frame):
#   Effects/Shadow | Alpha Test  OFF = draw the whole soft shadow (PS2), ON = the Xbox cut          (slider "Shadow Alpha Cut")
#   Effects/Shadow | Soft Edge   0.05 .. 0.45 share of the shadow's length that fades out (game 0.1875)
#   Effects/Shadow | Width       0.5 .. 2 x the car's shadow width (game 1)
#   Effects/Shadow | Length      0.5 .. 2 x the car's shadow length (game 1)
#   Effects/Shadow | Opacity     0 .. 1 (Xbox 0.7, PS2 0.703)
#   Effects/Sparks | Size        0.012 (Xbox) .. 0.025 (PS2 0.017)
# The "set" line holds the defaults (the --shadow preset this mod was built with; a slider's default is the same value). Presets
# tried in game (2026-10-31; ps2look --shadow NAME builds them):
#   soft:   set = ["Effects/Sparks | Size = 0.017", "Effects/Shadow | Alpha Test = 0", "Effects/Shadow | Soft Edge = 0.30", "Effects/Shadow | Width = 1.15", "Effects/Shadow | Length = 1.12", "Effects/Shadow | Opacity = 0.703"]
#   softer: set = ["Effects/Sparks | Size = 0.017", "Effects/Shadow | Alpha Test = 0", "Effects/Shadow | Soft Edge = 0.40", "Effects/Shadow | Width = 1.25", "Effects/Shadow | Length = 1.20", "Effects/Shadow | Opacity = 0.65"]
# version 3 = + sliders (host patch 130); a host without sliders refuses this mod alone ("needs a newer platform").
[bmashup.tune]
version = 3
set = [%SET%]
sliders = [
%SLIDERS%
]
'''
SHADOW_PRESETS = {
    'ps2': ['"Effects/Shadow | Alpha Test = 0"'],
    'soft': ['"Effects/Shadow | Alpha Test = 0"', '"Effects/Shadow | Soft Edge = 0.30"', '"Effects/Shadow | Width = 1.15"',
             '"Effects/Shadow | Length = 1.12"', '"Effects/Shadow | Opacity = 0.703"'],
    'softer': ['"Effects/Shadow | Alpha Test = 0"', '"Effects/Shadow | Soft Edge = 0.40"', '"Effects/Shadow | Width = 1.25"',
               '"Effects/Shadow | Length = 1.20"', '"Effects/Shadow | Opacity = 0.65"'],
    'xbox': [],
}


SPARK_SET = '"Effects/Sparks | Size = 0.017"'
# host patch 130 sliders: (row, the game's own value = the default when the preset sets none, "min .. max step s", label <= 16)
SLIDERS = [
    ('Effects/Shadow | Alpha Test', '1', '0 .. 1', 'Shadow Alpha Cut'),
    ('Effects/Shadow | Soft Edge', '0.1875', '0.05 .. 0.45 step 0.025', 'Shadow Soft Edge'),
    ('Effects/Shadow | Width', '1.0', '0.5 .. 2.0 step 0.05', 'Shadow Width'),
    ('Effects/Shadow | Length', '1.0', '0.5 .. 2.0 step 0.05', 'Shadow Length'),
    ('Effects/Shadow | Opacity', '0.7', '0 .. 1 step 0.05', 'Shadow Opacity'),
    ('Effects/Sparks | Size', '0.012', '0.012 .. 0.025 step 0.001', 'Spark Size'),
]


def set_values(shadow='ps2'):
    """{row: value text} of the mod's set = [...] line for this preset"""
    out = {}
    for e in [SPARK_SET] + SHADOW_PRESETS[shadow]:
        row, val = e.strip('"').rsplit('=', 1)
        out[row.strip()] = val.strip()
    return out


def slider_lines(shadow='ps2'):
    """the sliders = [...] entries: each row's default = the preset's set value (else the game's own value)"""
    sv = set_values(shadow)
    return ['"%s = %s : %s label %s"' % (row, sv.get(row, game), rng, label) for row, game, rng, label in SLIDERS]


def mod_toml(shadow='ps2'):
    """the mod.toml text; shadow = one of SHADOW_PRESETS (default 'ps2' = the alpha test off only, the owner's choice)"""
    return MOD_TOML.replace('%SET%', ', '.join([SPARK_SET] + SHADOW_PRESETS[shadow])).replace(
        '%SLIDERS%', ',\n'.join('    ' + s for s in slider_lines(shadow)))


class Ps2LookError(Exception):
    pass


def find_global(root):
    """DATA/GLOBAL.TXD under an extracted PS2 disc folder, case-insensitive"""
    root = Path(root)
    if not root.is_dir():
        raise Ps2LookError('--ps2-root %s is not a folder' % root)
    dirs = [root] if root.name.lower() == 'data' else []
    dirs += sorted(p for p in root.iterdir() if p.is_dir() and p.name.lower() == 'data')
    for d in dirs:
        for f in sorted(d.iterdir()):
            if f.is_file() and f.name.lower() == 'global.txd':
                return f
    raise Ps2LookError('no DATA\\GLOBAL.TXD under %s' % root)


def argb_texels(px, w, h):
    """RGBA texels (raster order) -> swizzled A8R8G8B8 (B, G, R, A bytes per texel, the Xbox Morton order of fetexlib)"""
    order = codec._morton(w, h)
    out = bytearray(w * h * 4)
    for i, (r, g, b, a) in enumerate(px):
        o = 4 * order[i]
        out[o:o + 4] = bytes((b, g, r, a))
    return bytes(out)


def argb_decode(texels, w, h):
    order = codec._morton(w, h)
    return [(texels[4 * order[i] + 2], texels[4 * order[i] + 1], texels[4 * order[i]], texels[4 * order[i] + 3]) for i in range(w * h)]


def to_entry(t):
    """Ps2Tex -> fetexlib A8R8G8B8 Entry: the exact PS2 pixels (owner 2026-10-31: "as close as it can get to the PS2"). These
    Global.txd entries are drawn without a palette (P8 drew with a stray one, run m21_c3_r2v2), so the host takes A8R8G8B8 / DXT for
    class "global" (patch 128). Lossless; 4 bytes a texel (64x64 = 16 KiB)."""
    return txd.Entry(t.name.lower(), txd.FMT_ARGB, t.w, t.h, argb_texels(list(t.rgba), t.w, t.h))


def to_entry_dxt5(t):
    """(the lossy alternative, kept: exhaustive DXT5 from the PS2 decode)"" These four Global.txd entries are drawn by code that never binds a palette (the retail ones
    are DXT5): a P8 replacement drew with whatever palette was bound last (C3 run m21_c3_r2v2: red / white kerb stripes), so the
    host refuses P8 for class "global" (patch 128) and this writes DXT5 from the exact PS2 decode (lossy like retail, but from the
    PS2 art, not from the Xbox re-encode)."""
    return txd.Entry(t.name.lower(), txd.FMT_DXT5, t.w, t.h, dxt5best.encode_dxt5(list(t.rgba), t.w, t.h))


def to_entry_p8(t):
    """(kept for reference: the lossless P8 form - NOT usable for these entries, see to_entry)"""
    if t.palette is not None:
        pal = list(t.palette) + [(0, 0, 0, 0)] * (256 - len(t.palette))
        idx = t.indices
    else:
        if len(set(t.rgba)) > 256:
            raise Ps2LookError('%s has %d colours (> 256): not losslessly P8' % (t.name, len(set(t.rgba))))
        pal, idx = codec.quantize(t.rgba, 256)
    if [pal[i] for i in idx] != list(t.rgba):
        raise Ps2LookError('%s: P8 mapping is not lossless' % t.name)
    return txd.Entry(t.name.lower(), txd.FMT_P8, t.w, t.h, codec.swizzle(bytes(idx), t.w, t.h), [codec.palette_bytes(pal)])


def dxt5_error(got, ref):
    """mean abs error: RGB over the visible texels (alpha > 8; colour under a transparent texel never shows), alpha over all"""
    rgb = [abs(p[c] - q[c]) for p, q in zip(got, ref) for c in range(3) if q[3] > 8]
    a = [abs(p[3] - q[3]) for p, q in zip(got, ref)]
    return sum(rgb) / max(1, len(rgb)), sum(a) / max(1, len(a))


def decode_txd_entry(e):
    if e.fmt == txd.FMT_ARGB:
        return argb_decode(e.texels, e.w, e.h)
    if e.fmt == txd.FMT_P8:
        return codec.decode_p8(e.texels, e.palettes[0], e.w, e.h)
    return codec.decode_dxt(e.texels, e.w, e.h, e.fmt == txd.FMT_DXT5)


def build(ps2_bytes):
    """-> (txd bytes, {name: Ps2Tex}); the TXD is parsed back strictly and compared pixel for pixel"""
    texs = ps2tex.decode(ps2_bytes, NAMES)
    t = txd.Txd([to_entry(texs[n]) for n in NAMES], tag=0)
    out = txd.build(t)
    back = txd.parse(out)
    bad = txd.check_frontend(back, cap=dict(txd.CAP_FRONTEND, formats=(txd.FMT_DXT1, txd.FMT_DXT5, txd.FMT_ARGB)))   # class global
    if bad:
        raise Ps2LookError('written TXD fails the capability list: %s' % '; '.join(bad))
    for n in NAMES:
        e = back.find(n)
        if e is None:
            raise Ps2LookError('%s: missing after the round trip' % n)
        got, ref = decode_txd_entry(e), list(texs[n].rgba)
        err_rgb, err_a = dxt5_error(got, ref)
        if len(got) != len(ref) or got != ref:          # A8R8G8B8: the exact PS2 pixels
            raise Ps2LookError('%s: DXT5 round trip error rgb %.2f alpha %.2f' % (n, err_rgb, err_a))
    return out, texs


def xbox_level0(b, name):
    """lenient read of the retail Xbox Global.txd (mips allowed): (w, h, rgba) of mip 0, or None"""
    n = struct.unpack_from('<I', b, 8)[0]
    for i in range(n):
        off = struct.unpack_from('<I', b, 0x10 + 16 * i + 8)[0]
        if b[off + 0x48:off + 0x68].split(b'\0')[0].decode('ascii', 'replace').lower() != name.lower():
            continue
        fmt, w, h = struct.unpack_from('<3I', b, off + 0x34)
        data = struct.unpack_from('<I', b, off + 4)[0]
        if fmt in (txd.FMT_DXT1, txd.FMT_DXT5):
            return w, h, codec.decode_dxt(b[off + data:], w, h, fmt == txd.FMT_DXT5)
        return None
    return None


def _scaled_over_checker(px, w, h, dw, dh):
    out = []
    for y in range(dh):
        sy = y * h // dh
        for x in range(dw):
            sx = x * w // dw
            r, g, b, a = px[sy * w + sx]
            c = 96 if ((x >> 3) + (y >> 3)) & 1 else 160
            out.append(tuple((v * a + c * (255 - a) + 127) // 255 for v in (r, g, b)) + (255,))
    return out


def write_previews(texs, pdir, xbox_bytes=None):
    """PNG per texture (raw RGBA, own size) + compare.png (PS2 left, Xbox right, scaled, over a grey checker)"""
    pdir = Path(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    written = []
    rows = []
    for n in NAMES:
        t = texs[n]
        f = pdir / ('ps2_%s.png' % n)
        png.write(str(f), t.w, t.h, t.rgba)
        written.append(f.name)
        xb = xbox_level0(xbox_bytes, n) if xbox_bytes else None
        if xb:
            f = pdir / ('xbox_%s.png' % n)
            png.write(str(f), xb[0], xb[1], xb[2])
            written.append(f.name)
        dw = 256
        dh = max(8, dw * t.h // t.w)
        rows.append((_scaled_over_checker(t.rgba, t.w, t.h, dw, dh),
                     _scaled_over_checker(xb[2], xb[0], xb[1], dw, dh) if xb else None, dw, dh))
    gap = 8
    W = gap + 2 * (256 + gap)
    H = gap + sum(r[3] + gap for r in rows)
    img = [(24, 24, 24, 255)] * (W * H)
    y0 = gap
    for ps, xb, dw, dh in rows:
        for k, src in enumerate((ps, xb)):
            if src is None:
                continue
            x0 = gap + k * (256 + gap)
            for y in range(dh):
                img[(y0 + y) * W + x0:(y0 + y) * W + x0 + dw] = src[y * dw:(y + 1) * dw]
        y0 += dh + gap
    png.write(str(pdir / 'compare.png'), W, H, img)
    written.append('compare.png')
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--ps2-global', help='your PS2 disc\'s DATA\\GLOBAL.TXD (extracted)')
    src.add_argument('--ps2-root', help='an extracted PS2 disc folder (holds DATA\\GLOBAL.TXD)')
    ap.add_argument('--out', required=True, help='mod folder to write global_ps2.txd + mod.toml into')
    ap.add_argument('--previews', help='folder for PNG previews (your own art: keep it local)')
    ap.add_argument('--xbox-global', help='the Xbox Data\\Global.txd, to add its versions to the previews')
    ap.add_argument('--force', action='store_true', help='overwrite global_ps2.txd / mod.toml if present')
    ap.add_argument('--shadow', choices=sorted(SHADOW_PRESETS), default='ps2',
                    help='car shadow preset: ps2 (default: the whole soft shadow, alpha test off), soft, softer, xbox')
    a = ap.parse_args(argv)
    try:
        f = Path(a.ps2_global) if a.ps2_global else find_global(a.ps2_root)
        if not f.is_file():
            raise Ps2LookError('%s is not a file' % f)
        out = Path(a.out).resolve()
        if out == HERE or HERE in out.parents:
            raise Ps2LookError('--out must not be inside the tool folder (the result is your own art: keep it out of the kit)')
        data, texs = build(f.read_bytes())
        out.mkdir(parents=True, exist_ok=True)
        for nm in (TXD_NAME, 'mod.toml'):
            if (out / nm).exists() and not a.force:
                raise Ps2LookError('%s exists (use --force to overwrite)' % (out / nm))
        (out / TXD_NAME).write_bytes(data)
        (out / 'mod.toml').write_text(mod_toml(a.shadow), encoding='utf-8', newline='\n')
        print('ps2look: %s -> %s (%d bytes) + mod.toml' % (f, out / TXD_NAME, len(data)))
        for n in NAMES:
            t = texs[n]
            print('  %-15s %3dx%-3d PS2 PSM 0x%02X -> A8R8G8B8 (exact)' % (n, t.w, t.h, t.psm))
        print('  alpha rule:', ps2tex.ALPHA_RULE)
        if a.previews:
            xb = Path(a.xbox_global).read_bytes() if a.xbox_global else None
            print('  previews:', ', '.join(write_previews(texs, a.previews, xb)), 'in', a.previews)
        print('  keep this output on your PC: it is your own disc\'s art (never package, commit or upload it)')
        return 0
    except (Ps2LookError, ps2tex.Ps2TexError, txd.TxdError, OSError) as e:
        print('ps2look: refused: %s' % e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
