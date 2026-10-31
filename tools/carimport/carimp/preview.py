"""Offline preview: decode a .bgv EXACTLY as written (LOD whole list + wheel list L7 at the header wheel matrices, texture via
palette p) and rasterise four views into one PNG (software z-buffer, nearest texel, Lambert on the decoded normals).
Views: left side (camera on +X looking -X), front (+Z), top (+Y, front up), 3/4 front-left. Back-faces are culled with the
retail winding rule (CCW-front in the car frame), so a wrong winding shows as missing faces.
Evidence of what the file contains - not of what the game renders."""
import math
import struct

from . import bgvwrite, png, texture

VW, VH = 320, 200


def load(data, lod=3, paint=0):
    m = bgvwrite.bgvlib.parse(data)
    L = m.lods[min(lod, len(m.lods) - 1)]
    V = [struct.unpack_from('<3fI2f', data, L['vb0'] + 24 * i) for i in range(L['nv'])]
    T = m.tex
    lin = texture.unswizzle(data[T['texels']:T['texels'] + T['w'] * T['h']], T['w'], T['h'])
    P = T['pals'][min(paint, len(T['pals']) - 1)]
    pal = texture.pal_from_bytes(data[P['data']:P['data'] + 0x400])
    tris = []

    def add(draws, mat):
        for d in draws:
            fl = d['flags'] & 0xFFFF
            ix = list(struct.unpack_from('<%dH' % d['n'], data, d['off']))
            for a, b, c in bgvwrite.strip_tris(ix):
                pts = []
                for i in (a, b, c):
                    p = V[i][:3]
                    n = bgvwrite.unpack_normal(V[i][3])
                    if mat:
                        p = _xf(mat, p)
                        n = _xn(mat, n)
                    pts.append((p, n, V[i][4:]))
                tris.append((pts, fl))
    add(L['whole']['draws'], None)
    for w in range(data[0xD]):
        mat = struct.unpack_from('<16f', data, 0xB80 + 0x40 * w)
        add(L['lists'][7]['draws'], mat)
    return tris, (lin, T['w'], T['h'], pal)


def _xf(m, p):
    return (p[0] * m[0] + p[1] * m[4] + p[2] * m[8] + m[12], p[0] * m[1] + p[1] * m[5] + p[2] * m[9] + m[13],
            p[0] * m[2] + p[1] * m[6] + p[2] * m[10] + m[14])


def _xn(m, n):
    return (n[0] * m[0] + n[1] * m[4] + n[2] * m[8], n[0] * m[1] + n[1] * m[5] + n[2] * m[9], n[0] * m[2] + n[1] * m[6] + n[2] * m[10])


def _view(eye, target):
    f = [target[i] - eye[i] for i in range(3)]
    fl = math.sqrt(sum(x * x for x in f))
    f = [x / fl for x in f]
    up = (0, 1, 0) if abs(f[1]) < 0.95 else (0, 0, 1)
    r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    rl = math.sqrt(sum(x * x for x in r))
    r = [x / rl for x in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    return eye, r, u, f


def render(tris, tex, eye, target, scale):
    lin, tw, th, pal = tex
    img = [(40, 44, 52)] * (VW * VH)
    zb = [1e30] * (VW * VH)
    e, r, u, f = _view(eye, target)
    light = _n((0.4, 0.8, 0.5))
    for pts, fl in tris:
        sp = []
        for p, n, uv in pts:
            d = [p[i] - e[i] for i in range(3)]
            x = sum(d[i] * r[i] for i in range(3))
            y = sum(d[i] * u[i] for i in range(3))
            z = sum(d[i] * f[i] for i in range(3))
            sp.append((VW / 2 + x * scale, VH / 2 - y * scale, z, n, uv))
        # winding in screen space (y down): a face that is counter-clockwise to the viewer has a negative signed area
        ax, ay = sp[1][0] - sp[0][0], sp[1][1] - sp[0][1]
        bx, by = sp[2][0] - sp[0][0], sp[2][1] - sp[0][1]
        area = ax * by - ay * bx
        if area >= 0:
            continue      # back face (or degenerate)
        x0 = max(0, int(min(s[0] for s in sp)))
        x1 = min(VW - 1, int(max(s[0] for s in sp)) + 1)
        y0 = max(0, int(min(s[1] for s in sp)))
        y1 = min(VH - 1, int(max(s[1] for s in sp)) + 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px, py = x + 0.5, y + 0.5
                w0 = ((sp[1][0] - px) * (sp[2][1] - py) - (sp[1][1] - py) * (sp[2][0] - px)) / area
                w1 = ((sp[2][0] - px) * (sp[0][1] - py) - (sp[2][1] - py) * (sp[0][0] - px)) / area
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * sp[0][2] + w1 * sp[1][2] + w2 * sp[2][2]
                k = y * VW + x
                if z >= zb[k]:
                    continue
                zb[k] = z
                uu = w0 * sp[0][4][0] + w1 * sp[1][4][0] + w2 * sp[2][4][0]
                vv = w0 * sp[0][4][1] + w1 * sp[1][4][1] + w2 * sp[2][4][1]
                n = [w0 * sp[0][3][i] + w1 * sp[1][3][i] + w2 * sp[2][3][i] for i in range(3)]
                nl = math.sqrt(sum(c * c for c in n)) or 1
                lam = 0.35 + 0.65 * max(0.0, sum(n[i] / nl * light[i] for i in range(3)))
                if fl & 0x100:
                    c = (120, 160, 190)
                else:
                    tx = min(tw - 1, max(0, int(uu * tw)))
                    ty = min(th - 1, max(0, int(vv * th)))
                    c = pal[lin[ty * tw + tx]][:3]
                img[k] = tuple(min(255, int(ch * lam)) for ch in c)
    return img


def _n(v):
    ln = math.sqrt(sum(x * x for x in v))
    return tuple(x / ln for x in v)


def sheet(data, out_png, lod=3, paint=0):
    tris, tex = load(data, lod, paint)
    views = [((6, 0.5, 0), (0, 0.5, 0), 'left (+X)'), ((0, 0.6, 7), (0, 0.5, 0), 'front (+Z)'),
             ((0, 8, 0.01), (0, 0, 0), 'top'), ((4.5, 2.5, 4.5), (0, 0.4, 0), '3/4 front-left')]
    imgs = [render(tris, tex, e, t, 60 if i < 3 else 52) for i, (e, t, _) in enumerate(views)]
    W, H = VW * 2, VH * 2
    out = []
    for y in range(H):
        for x in range(W):
            v = imgs[(y // VH) * 2 + (x // VW)]
            out.append(v[(y % VH) * VW + (x % VW)] + (255,))
    png.write_rgba(out_png, W, H, out)
    return dict(triangles=len(tris), views=[v[2] for v in views])
