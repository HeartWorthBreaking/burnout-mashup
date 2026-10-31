"""gen_art.py - GP-FETEX1 demo art, AUTHORED: every pixel is computed here from code (no retail or third-party image is read).

Outputs (deterministic; PNG + fetex pack specs) under demo\\art\\:
  photo\\compbm01_paint<k>.png   garage photo of the added car COMPBM01 (128x64, one picture per paint, same index layout)
  oceania\\*.png                 OCEANIA map art for the wt4 4th region: 6 map tiles (768x512 harbour city "Harbour Ring"),
                                overview 512x512, area view 256x256, city strips 64x32 / 128x64 / 256x128 / 512x256
  marker\\*.png                  the region's map marker: icon 64x64, pulse 256x256, hollow outline 64x64
  photo.json / oceania.json    fetex pack specs
Usage: py -3 -B gen_art.py [OUTDIR]
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'tools', 'fetex'))
from fetexlib import png  # noqa: E402

SEED = 0x0CEA


# ---------------------------------------------------------------- tiny raster helpers
def lerp(a, b, t):
    return a + (b - a) * t


def mix(c0, c1, t):
    return tuple(int(round(lerp(c0[i], c1[i], t))) for i in range(len(c0)))


def clamp(v, lo=0, hi=255):
    return lo if v < lo else hi if v > hi else v


def hash2(x, y, s=SEED):
    h = (x * 374761393 + y * 668265263 + s * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def vnoise(x, y, s=SEED):
    xi, yi = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - xi, y - yi
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = hash2(xi, yi, s), hash2(xi + 1, yi, s)
    c, d = hash2(xi, yi + 1, s), hash2(xi + 1, yi + 1, s)
    return lerp(lerp(a, b, fx), lerp(c, d, fx), fy)


def fbm(x, y, oct=5, s=SEED):
    v, amp, f, tot = 0.0, 1.0, 1.0, 0.0
    for o in range(oct):
        v += amp * vnoise(x * f, y * f, s + o * 101)
        tot += amp
        amp *= 0.5
        f *= 2.0
    return v / tot


def in_poly(x, y, pts):
    ins = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            ins = not ins
        j = i
    return ins


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy + 1e-12)
    t = 0 if t < 0 else 1 if t > 1 else t
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def poly_dist(px, py, pts, closed=True):
    n = len(pts)
    m = 1e9
    for i in range(n if closed else n - 1):
        m = min(m, seg_dist(px, py, pts[i], pts[(i + 1) % n]))
    return m


# ---------------------------------------------------------------- 1. garage photo (P8, 8 paints)
PAINTS = [(214, 40, 170), (120, 220, 40), (200, 30, 30), (30, 70, 200), (240, 130, 20), (235, 235, 240), (35, 35, 40),
          (240, 210, 30)]                                  # magenta (the COMPBM01 model), lime, red, blue, orange, white, black, yellow
SHADES = 24


def photo_layout():
    """per pixel: ('body', shade 0..SHADES-1) | ('rgba', colour) on a 128x64 canvas, 4x supersampled coverage"""
    W, H = 128, 64
    body = [(10, 44), (14, 34), (34, 30), (50, 18), (86, 16), (104, 28), (118, 31), (121, 42), (117, 47), (12, 48)]
    glass = [(52, 21), (84, 19), (98, 29), (44, 30)]
    pillar = [(70, 19), (73, 19), (72, 30), (68, 30)]
    stripe_y = (35.5, 38.0)
    wheels = [(33, 46, 9.0), (98, 46, 9.0)]
    out = []
    for y in range(H):
        for x in range(W):
            cov = {}
            for sy in range(4):
                for sx in range(4):
                    fx, fy = x + (sx + 0.5) / 4, y + (sy + 0.5) / 4
                    k = None
                    for cx, cy, r in wheels:
                        d = math.hypot(fx - cx, fy - cy)
                        if d < r:
                            k = ('rgba', (20, 20, 22, 255)) if d > r * 0.62 else \
                                ('rgba', (175, 178, 185, 255)) if d > r * 0.2 and int((math.atan2(fy - cy, fx - cx) + 7) * 5 / math.pi) % 2 \
                                else ('rgba', (120, 122, 128, 255))
                            break
                    if k is None and in_poly(fx, fy, glass) and not in_poly(fx, fy, pillar):
                        g = int(lerp(70, 150, (fx - 44) / 56.0))
                        k = ('rgba', (g // 2, g // 2 + 10, g, 255))
                    if k is None and in_poly(fx, fy, body):
                        if stripe_y[0] <= fy <= stripe_y[1]:
                            k = ('rgba', (245, 245, 245, 255))
                        elif 112 < fx < 118 and 33 < fy < 37:
                            k = ('rgba', (255, 240, 170, 255))          # head light
                        elif 11 < fx < 15 and 36 < fy < 40:
                            k = ('rgba', (200, 20, 20, 255))            # tail light
                        else:
                            light = 1.0 - (fy - 16) / 34.0 + 0.15 * math.sin(fx / 11.0)
                            if 40 < fy < 47:
                                light -= 0.35
                            k = ('body', int(clamp(int(light * (SHADES - 1)), 0, SHADES - 1)))
                    if k is None and 44 <= fy <= 51 and in_poly(fx, 47.5, [(8, 0), (124, 0), (124, 99), (8, 99)]):
                        k = ('rgba', (0, 0, 0, 110))                    # ground shadow
                    if k is not None:
                        cov[k] = cov.get(k, 0) + 1
            if not cov:
                out.append(('rgba', (0, 0, 0, 0)))
            else:
                k = max(sorted(cov), key=lambda q: cov[q])
                if sum(cov.values()) < 8 and k[0] == 'rgba':
                    k = ('rgba', k[1][:3] + (k[1][3] * sum(cov.values()) // 16,))
                out.append(k)
    return W, H, out


def paint_colour(p, shade):
    t = shade / (SHADES - 1.0)
    dark = tuple(int(c * 0.25) for c in p)
    hi = tuple(min(255, int(c * 0.6 + 110)) for c in p)
    c = mix(dark, p, t * 1.4) if t < 0.7 else mix(p, hi, (t - 0.7) / 0.3)
    return c + (255,)


def gen_photo(out):
    W, H, lay = photo_layout()
    os.makedirs(os.path.join(out, 'photo'), exist_ok=True)
    names = []
    fixed = sorted({c for k, c in lay if k == 'rgba'})
    for k, p in enumerate(PAINTS):
        px = []
        for kind, v in lay:
            if kind == 'body':
                c = paint_colour(p, v)
                if k == 0 and c in fixed:          # keep body shades distinct from fixed colours in the index picture
                    c = (c[0], c[1], c[2] ^ 1, 255)
                px.append(c)
            else:
                px.append(v)
        f = 'compbm01_paint%d.png' % k
        png.write(os.path.join(out, 'photo', f), W, H, px)
        names.append('photo/' + f)
    spec = dict(tag=0, entries=[dict(name='compbm01_photo', png=names[0], format='P8', palettes=names[1:])])
    json.dump(spec, open(os.path.join(out, 'photo.json'), 'w'), indent=1)


# ---------------------------------------------------------------- 2. OCEANIA map art (DXT1)
SEA_D, SEA_S = (14, 38, 72), (40, 96, 128)
SAND = (196, 182, 140)
GRASS_A, GRASS_B = (52, 92, 46), (104, 120, 64)
ROOF = [(150, 146, 140), (120, 110, 104), (176, 170, 160), (110, 120, 130), (160, 120, 96)]


def harbour_world(x, y):
    """the 768x512 map in map units: returns rgb. Coast = noise-bent line; a ring road round the harbour."""
    land_h = fbm(x / 180.0, y / 180.0, 5) - 0.5 + (0.55 - y / 512.0) * 0.9 + (x / 768.0 - 0.3) * 0.25
    hx, hy = 250.0, 300.0                                   # harbour basin
    d_h = math.hypot((x - hx) / 1.3, y - hy)
    land_h -= max(0.0, 0.55 - d_h / 220.0)
    if land_h < 0:
        dep = clamp(int(-land_h * 400), 0, 255) / 255.0
        c = mix(SEA_S, SEA_D, min(1.0, dep * 1.5))
        n = fbm(x / 9.0, y / 9.0, 2, SEED + 7) - 0.5
        return tuple(clamp(int(v + n * 18)) for v in c)
    if land_h < 0.03:
        return SAND
    g = fbm(x / 40.0, y / 40.0, 4, SEED + 3)
    c = mix(GRASS_A, GRASS_B, g)
    city = math.exp(-((x - 430) ** 2 + (y - 210) ** 2) / (2 * 150.0 ** 2)) * 1.4
    if city > 0.35 and land_h > 0.06:
        bx, by = int(x // 14), int(y // 11)
        if (x % 14) < 2 or (y % 11) < 2:
            c = (70, 70, 74)                                # streets
        elif hash2(bx, by, SEED + 11) < city:
            r = ROOF[int(hash2(bx, by, SEED + 12) * len(ROOF))]
            c = mix(r, (255, 255, 255), 0.15 * hash2(int(x // 3), int(y // 3), SEED + 13))
    # ring road ("Harbour Ring", the region's race) + one arterial
    rd = abs(math.hypot((x - hx) / 1.25, (y - hy) / 0.95) - 205.0)
    if rd < 3.2 and land_h > 0.0:
        return (232, 214, 120) if rd < 1.2 else (60, 60, 64)
    if seg_dist(x, y, (430, 210), (760, 40)) < 2.5 and land_h > 0.0:
        return (210, 210, 200)
    n = fbm(x / 6.0, y / 6.0, 2, SEED + 21) - 0.5
    return tuple(clamp(int(v + n * 20)) for v in c)


def gen_oceania(out):
    d = os.path.join(out, 'oceania')
    os.makedirs(d, exist_ok=True)
    W, H = 768, 512
    world = [harbour_world(x + 0.5, y + 0.5) + (255,) for y in range(H) for x in range(W)]
    ent = []
    for c in (1, 2, 3):
        for r in (1, 2):
            px = [world[(y + (r - 1) * 256) * W + x + (c - 1) * 256] for y in range(256) for x in range(256)]
            f = 'oceania_tile_%d_%d.png' % (c, r)
            png.write(os.path.join(d, f), 256, 256, px)
            ent.append(dict(name='oceania_tile_%d_%d' % (c, r), png='oceania/' + f, format='DXT1'))

    def sample(sx, sy, sw, sh, w, h, fn=None):
        px = []
        for y in range(h):
            for x in range(w):
                wx, wy = sx + (x + 0.5) * sw / w, sy + (y + 0.5) * sh / h
                px.append((fn or harbour_world)(wx, wy) + (255,))
        return px

    def continent(x, y):                                   # the overview: a fictional southern continent + islands
        u, v = x / 512.0, y / 512.0
        h = fbm(u * 3.2, v * 3.2, 6, SEED + 40) - 0.5 + 0.35 - math.hypot(u - 0.48, v - 0.55) * 1.1
        h += max(0.0, 0.18 - math.hypot(u - 0.86, v - 0.82) * 1.6)
        if h < 0:
            return mix((50, 110, 150), (10, 30, 70), min(1.0, -h * 4))
        dry = fbm(u * 6, v * 6, 4, SEED + 41)
        return mix((70, 120, 50), (190, 150, 90), clamp(int((dry + (0.55 - v) * 0.6) * 255), 0, 255) / 255.0)
    ov = sample(0, 0, 512, 512, 512, 512, continent)
    for y in range(512):                                   # the region frame marker on the coast
        for x in range(512):
            if abs(max(abs(x - 330), abs(y - 300)) - 22) < 1.5:
                ov[y * 512 + x] = (240, 230, 90, 255)
    png.write(os.path.join(d, 'oceania_overview.png'), 512, 512, ov)
    ent.append(dict(name='oceania_overview', png='oceania/oceania_overview.png', format='DXT1'))
    png.write(os.path.join(d, 'oceania_area.png'), 256, 256, sample(40, 40, 600, 600, 256, 256))
    ent.append(dict(name='oceania_area', png='oceania/oceania_area.png', format='DXT1'))
    for k, (w, h) in enumerate([(64, 32), (128, 64), (256, 128), (512, 256)]):
        f = 'oceania_city_l%d.png' % (k + 1)
        png.write(os.path.join(d, f), w, h, sample(300, 140, 260, 130, w, h))
        ent.append(dict(name='oceania_city_l%d' % (k + 1), png='oceania/' + f, format='DXT1'))
    return ent


# ---------------------------------------------------------------- 3. marker (DXT5): a rounded badge with a wave and sun
TEAL, ORANGE, WHITE = (20, 170, 170), (250, 150, 40), (250, 250, 245)


def badge_sdf(x, y, cx, cy, r, rr):
    qx, qy = abs(x - cx) - (r - rr), abs(y - cy) - (r - rr)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - rr


def marker_icon(n):
    s = n / 64.0
    px = []
    for y in range(n):
        for x in range(n):
            acc = [0, 0, 0, 0]
            for sy in range(3):
                for sx in range(3):
                    fx, fy = (x + (sx + 0.5) / 3) / s, (y + (sy + 0.5) / 3) / s
                    d = badge_sdf(fx, fy, 32, 30, 25, 8)
                    c = None
                    if d < -3:
                        c = TEAL
                        if math.hypot(fx - 40, fy - 22) < 7:
                            c = ORANGE
                        wave = 34 + 3.2 * math.sin(fx / 4.2)
                        if wave < fy < wave + 3.4 or wave + 7 < fy < wave + 10:
                            c = WHITE
                    elif d < 0:
                        c = WHITE
                    elif d < 3 and fy > 31:
                        c = (0, 0, 0)                   # drop shadow
                    if c:
                        a = 255 if d < 0 else 120
                        acc = [acc[0] + c[0] * a, acc[1] + c[1] * a, acc[2] + c[2] * a, acc[3] + a]
            if acc[3]:
                px.append((acc[0] // acc[3], acc[1] // acc[3], acc[2] // acc[3], acc[3] // 9))
            else:
                px.append((0, 0, 0, 0))
    return px


def marker_hollow(n):
    px = []
    for y in range(n):
        for x in range(n):
            a = 0
            for sy in range(3):
                for sx in range(3):
                    d = badge_sdf(x + (sx + 0.5) / 3, y + (sy + 0.5) / 3, 32, 30, 25, 8)
                    a += 255 if -4 < d < 0 else 90 if 0 <= d < 3 and y > 31 else 0
            px.append((WHITE + (a // 9,)) if a else (0, 0, 0, 0))
    return px


def marker_pulse(n):
    px = []
    for y in range(n):
        for x in range(n):
            d = badge_sdf(x + 0.5, y + 0.5, 128, 122, 100, 32)
            a = max(0.0, 1.0 - abs(d + 6) / 14.0) if d > -20 else 0.0
            px.append(TEAL + (int(255 * a),) if a > 0 else (0, 0, 0, 0))
    return px


def gen_marker(out):
    d = os.path.join(out, 'marker')
    os.makedirs(d, exist_ok=True)
    png.write(os.path.join(d, 'oceania_marker.png'), 64, 64, marker_icon(64))
    png.write(os.path.join(d, 'oceania_marker_hollow.png'), 64, 64, marker_hollow(64))
    png.write(os.path.join(d, 'oceania_marker_pulse.png'), 256, 256, marker_pulse(256))
    return [dict(name='oceania_marker', png='marker/oceania_marker.png', format='DXT5'),
            dict(name='oceania_marker_hollow', png='marker/oceania_marker_hollow.png', format='DXT5'),
            dict(name='oceania_marker_pulse', png='marker/oceania_marker_pulse.png', format='DXT5')]


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art')
    os.makedirs(out, exist_ok=True)
    gen_photo(out)
    ent = gen_oceania(out) + gen_marker(out)
    json.dump(dict(tag=0, entries=ent), open(os.path.join(out, 'oceania.json'), 'w'), indent=1)
    print('art written to', out)


if __name__ == '__main__':
    main(sys.argv)
