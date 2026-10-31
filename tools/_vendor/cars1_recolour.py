"""cars1 recolour (paint 1 lime / magenta + stripe livery of a P8 car model), the build_bgv part of the atlas script
make_cars1_mod.py, vendored into the mod kit 0.4.1 for examples/content/added-car (only luma / recolour / paint_entries /
build_bgv; the original's pinned-input readers are not needed: the example checks its own input hash)."""
import bgvlib

LIME = (120, 255, 40)            # RGB at full luminance
MOD_ID = 'bmashup.gp-cars1'
MOD_TOML = '''# gp cars1 slice (s6): replacement paint + livery for COMPCAR1 (Compact Type 1). Data only, no code.
# Contains retail game data (modified copies): local only, never upload.
id = "%s"
name = "GP cars1 livery (COMPCAR1)"
version = "1.0.0"
description = "Compact Type 1: paint 1 = BM lime, stripes livery (all paints), garage photo paint 1."

[bmashup]
platform = ">=0.1"
''' % MOD_ID


def luma(b, g, r):
    return 0.299 * r + 0.587 * g + 0.114 * b


def recolour(pal_bytes, entries, ref_max):
    out = bytearray(pal_bytes)
    for k in entries:
        b, g, r, a = out[4 * k:4 * k + 4]
        f = min(1.0, luma(b, g, r) / ref_max) if ref_max else 0.0
        f = 0.35 + 0.65 * f            # lifted floor: a vivid, clearly non-retail paint in screenshots
        nr, ng, nb = (int(round(c * f)) for c in LIME)
        out[4 * k:4 * k + 4] = bytes((nb, ng, nr, a))
    return bytes(out)


def paint_entries(pals):
    return [k for k in range(256) if len(set(p[k] for p in pals)) > 1]


def build_bgv(b):
    m = bgvlib.parse(b)
    T = m.tex
    pals = [bytes(b[P['data']:P['data'] + bgvlib.PAL_DATA]) for P in T['pals']]
    ents = paint_entries([[p[4 * k:4 * k + 4] for k in range(256)] for p in pals])
    p0 = pals[0]
    ref = max(luma(*p0[4 * k:4 * k + 3]) for k in ents)
    new_p0 = recolour(p0, ents, ref)
    # livery stripes: body half, paint texels only, decal index = brightest non-paint entry used in the body half
    w, h = T['w'], T['h']
    lin = bytearray(bgvlib.unswizzle(bgvlib.texels(m), w, h))
    eset = set(ents)
    used = set(lin[y * w + x] for y in range(h) for x in range(w // 2, w))
    cand = [k for k in used if k not in eset and p0[4 * k + 3] == 255]
    white = max(cand, key=lambda k: (luma(*p0[4 * k:4 * k + 3]), -k))
    for y in range(h):
        for x in range(w // 2, w):
            if lin[y * w + x] in eset and ((x + y) // 12) % 4 == 0:
                lin[y * w + x] = white
    new_tex = bgvlib.swizzle(bytes(lin), w, h)
    out = bgvlib.replace(m, texels_new=new_tex, palettes_new=[new_p0] + pals[1:])
    return out, dict(paint_entries=len(ents), decal_index=white, ref_luma=round(ref, 3))
