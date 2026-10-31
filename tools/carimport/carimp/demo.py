"""ORIGINAL demonstration assets for carimport, generated procedurally (no retail data, no third-party art).

  wedge  : simple test shape - a chamfered box ("wedge") body, paint + plain classes, NO wheel node (the importer's
           generated neutral wheel is used), a left-side marker fin (asymmetry check: glTF +X = car left).
  coupe  : car-like model - a lofted body from 25 cross-sections (hood, windscreen, roof, hatch), cabin windows in the glass
           class, a separate plain under-tray, a left-side marker fin, an authored wheel (tyre + rim + spokes, wheel-local).
Texture (512 x 256, both models): left half = wheel / plain atlas (tyre, rim, dark trim, lights), right half = body paint area
(grey luminance gradient = paint ramp, masked) with fixed-colour decals (a yellow / black chevron band and the letters "BM"),
a red "L" tile only mapped on the marker fin. Paint mask = the paint area minus the decals.
All coordinates in metres, glTF frame (+Y up, +Z front, +X car left), sized to sit on COMPCAR1-class wheels
(track 1.52 m, wheelbase 2.545 m, wheel radius 0.312 m).
"""
import math
import os

from . import gltf, png

W, H = 512, 256

# texture atlas boxes (u0, v0, u1, v1)
UV_TYRE = (0.0, 0.0, 0.25, 0.25)
UV_RIM = (0.25, 0.0, 0.5, 0.25)
UV_TRIM = (0.0, 0.25, 0.25, 0.5)
UV_MARK = (0.25, 0.25, 0.5, 0.5)
UV_LIGHT_F = (0.0, 0.5, 0.25, 0.625)
UV_LIGHT_R = (0.25, 0.5, 0.5, 0.625)
UV_BODY = (0.5, 0.0, 1.0, 1.0)


# ---------------------------------------------------------------- texture
FONT = {  # 5x7 block letters
    'B': ['1111 ', '1   1', '1   1', '1111 ', '1   1', '1   1', '1111 '],
    'M': ['1   1', '11 11', '1 1 1', '1   1', '1   1', '1   1', '1   1'],
    'L': ['1    ', '1    ', '1    ', '1    ', '1    ', '1    ', '11111'],
}


def make_texture():
    img = [(0, 0, 0, 255)] * (W * H)
    mask = [(0, 0, 0, 255)] * (W * H)

    def box(uv, col, m=None):
        x0, y0, x1, y1 = int(uv[0] * W), int(uv[1] * H), int(uv[2] * W), int(uv[3] * H)
        for y in range(y0, y1):
            for x in range(x0, x1):
                img[y * W + x] = col(x - x0, y - y0, x1 - x0, y1 - y0) if callable(col) else col
                if m is not None:
                    mask[y * W + x] = m

    def tyre(x, y, w, h):
        g = 28 + (8 if (x // 4 + y // 4) % 2 else 0)
        return (g, g, g + 2, 255)
    box(UV_TYRE, tyre)

    def rim(x, y, w, h):
        cx, cy = w / 2, h / 2
        r = math.hypot(x - cx, y - cy) / (w / 2)
        g = 200 - int(90 * r)
        return (g, g, min(255, g + 15), 255)
    box(UV_RIM, rim)
    box(UV_TRIM, (22, 24, 30, 255))

    def mark(x, y, w, h):
        return (230, 30, 30, 255) if 6 <= x < w - 6 and 6 <= y < h - 6 else (255, 255, 255, 255)
    box(UV_MARK, mark)
    box(UV_LIGHT_F, (250, 245, 200, 255))
    box(UV_LIGHT_R, (200, 10, 10, 255))
    box((0.0, 0.625, 0.5, 1.0), (60, 64, 70, 255))

    def body(x, y, w, h):
        g = 120 + int(120 * (1.0 - abs(y - h / 2) / (h / 2)) * 0.9)
        return (g, g, g, 255)
    box(UV_BODY, body, (255, 255, 255, 255))
    # decal band: yellow / black chevrons across the paint area at v 0.44..0.56 (fixed colours, not paint)
    for y in range(int(0.44 * H), int(0.56 * H)):
        for x in range(W // 2, W):
            c = (250, 200, 20, 255) if ((x + abs(y - H // 2) * 2) // 10) % 2 else (15, 15, 15, 255)
            img[y * W + x] = c
            mask[y * W + x] = (0, 0, 0, 255)
    # letters "BM" (black, 6 px cells) at the paint area's centre-left
    for li, ch in enumerate('BM'):
        for r, row in enumerate(FONT[ch]):
            for c, bit in enumerate(row):
                if bit != '1':
                    continue
                for yy in range(6):
                    for xx in range(6):
                        x = W // 2 + 40 + li * 40 + c * 6 + xx
                        y = int(0.15 * H) + r * 6 + yy
                        img[y * W + x] = (10, 10, 120, 255)
                        mask[y * W + x] = (0, 0, 0, 255)
    # "L" on the marker tile
    for r, row in enumerate(FONT['L']):
        for c, bit in enumerate(row):
            if bit == '1':
                for yy in range(6):
                    for xx in range(6):
                        x = int(UV_MARK[0] * W) + 20 + c * 6 + xx
                        y = int(UV_MARK[1] * H) + 10 + r * 6 + yy
                        img[y * W + x] = (255, 255, 255, 255)
    return img, mask


def uvbox(b, s, t):
    return (b[0] + (b[2] - b[0]) * s, b[1] + (b[3] - b[1]) * t)


# ---------------------------------------------------------------- mesh helpers
class PB:
    """Primitive builder: flat-shaded quads / tris (own vertices per face) or smooth with given normals."""

    def __init__(self, material):
        self.p = dict(positions=[], normals=[], uvs=[], tris=[], material=material)

    def tri(self, a, b, c, uva, uvb, uvc, normals=None):
        if normals is None:
            n = _norm(_cross(_sub(b, a), _sub(c, a)))
            normals = (n, n, n)
        base = len(self.p['positions'])
        self.p['positions'] += [a, b, c]
        self.p['normals'] += list(normals)
        self.p['uvs'] += [uva, uvb, uvc]
        self.p['tris'].append((base, base + 1, base + 2))

    def quad(self, a, b, c, d, uvs, normals=None):
        """a b c d counter-clockwise seen from the front side."""
        na = normals or (None,) * 4
        self.tri(a, b, c, uvs[0], uvs[1], uvs[2], None if normals is None else (na[0], na[1], na[2]))
        self.tri(a, c, d, uvs[0], uvs[2], uvs[3], None if normals is None else (na[0], na[2], na[3]))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    ln = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / ln, v[1] / ln, v[2] / ln)


def box_faces(pb, lo, hi, uv, skip=()):
    """Axis box with outward faces (flat)."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    P = lambda x, y, z: (x, y, z)  # noqa: E731
    U = [uvbox(uv, 0, 0), uvbox(uv, 1, 0), uvbox(uv, 1, 1), uvbox(uv, 0, 1)]
    faces = {
        '+x': (P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)),
        '-x': (P(x0, y0, z1), P(x0, y1, z1), P(x0, y1, z0), P(x0, y0, z0)),
        '+y': (P(x0, y1, z0), P(x0, y1, z1), P(x1, y1, z1), P(x1, y1, z0)),
        '-y': (P(x0, y0, z0), P(x1, y0, z0), P(x1, y0, z1), P(x0, y0, z1)),
        '+z': (P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1), P(x0, y0, z1)),
        '-z': (P(x0, y0, z0), P(x0, y1, z0), P(x1, y1, z0), P(x1, y0, z0)),
    }
    for k, q in faces.items():
        if k in skip:
            continue
        # make sure the winding is outward
        n = _cross(_sub(q[1], q[0]), _sub(q[2], q[0]))
        c = [sum(p[i] for p in q) / 4 - (lo[i] + hi[i]) / 2 for i in range(3)]
        if sum(n[i] * c[i] for i in range(3)) < 0:
            q = (q[0], q[3], q[2], q[1])
        pb.quad(*q, U)


def fin(pb):
    """Left-side (+X) marker fin near the rear: a thin red / white 'L' plate standing out of the body side."""
    box_faces(pb, (0.86, 0.55, -1.75), (1.00, 0.85, -1.25), UV_MARK)


# ---------------------------------------------------------------- wedge (simple test shape)
def wedge_nodes():
    paint = PB(0)
    plain = PB(1)
    xL, xR = 0.85, -0.85
    yb, yt = 0.02, 0.95
    zr, zf = -2.0, 2.0
    zn = 1.0      # nose chamfer starts here (the roof slopes down to the nose)
    yn = 0.45
    A = lambda x, y, z: (x, y, z)  # noqa: E731
    # side panels (paint), roof (paint), nose slope (paint), rear (paint), bottom (plain)
    U = lambda s0, t0, s1, t1: [uvbox(UV_BODY, s0, t0), uvbox(UV_BODY, s1, t0), uvbox(UV_BODY, s1, t1), uvbox(UV_BODY, s0, t1)]  # noqa: E731
    for x, sgn in ((xL, 1), (xR, -1)):
        pts = [A(x, yb, zr), A(x, yb, zf), A(x, yn, zf), A(x, yt, zn), A(x, yt, zr)]
        uvs = [uvbox(UV_BODY, (p[2] - zr) / (zf - zr), 1 - (p[1] - yb) / (yt - yb)) for p in pts]
        for i in (1, 2, 3):
            tri = (pts[0], pts[i], pts[i + 1])
            tu = (uvs[0], uvs[i], uvs[i + 1])
            n = _cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0]))
            if n[0] * sgn < 0:
                tri = (tri[0], tri[2], tri[1])
                tu = (tu[0], tu[2], tu[1])
            paint.tri(*tri, *tu)
    paint.quad(A(xR, yt, zr), A(xR, yt, zn), A(xL, yt, zn), A(xL, yt, zr), U(0.1, 0.2, 0.9, 0.8))     # roof (+y)
    paint.quad(A(xR, yt, zn), A(xR, yn, zf), A(xL, yn, zf), A(xL, yt, zn), U(0.1, 0.3, 0.9, 0.7))     # nose slope
    paint.quad(A(xL, yb, zf), A(xL, yn, zf), A(xR, yn, zf), A(xR, yb, zf), U(0.2, 0.6, 0.8, 0.9))     # front face (+z)
    paint.quad(A(xR, yb, zr), A(xR, yt, zr), A(xL, yt, zr), A(xL, yb, zr), U(0.2, 0.6, 0.8, 0.9))     # rear face (-z)
    plain.quad(A(xL, yb, zr), A(xL, yb, zf), A(xR, yb, zf), A(xR, yb, zr), [uvbox(UV_TRIM, 0, 0), uvbox(UV_TRIM, 1, 0), uvbox(UV_TRIM, 1, 1), uvbox(UV_TRIM, 0, 1)])
    _fix_outward(paint, (0, 0.5, 0))
    _fix_outward(plain, (0, 0.5, 0))
    mk = PB(1)
    fin(mk)
    return [dict(name='body', prims=[paint.p, plain.p, mk.p])]


def _fix_outward(pb, centre):
    """Re-orient every triangle so its face normal points away from `centre` (convex shapes only)."""
    p = pb.p
    for k, (a, b, c) in enumerate(p['tris']):
        A, B, C = p['positions'][a], p['positions'][b], p['positions'][c]
        n = _cross(_sub(B, A), _sub(C, A))
        m = [(A[i] + B[i] + C[i]) / 3 - centre[i] for i in range(3)]
        if sum(n[i] * m[i] for i in range(3)) < 0:
            p['tris'][k] = (a, c, b)
            nn = _norm(_cross(_sub(C, A), _sub(B, A)))
            for i in (a, b, c):
                p['normals'][i] = nn


# ---------------------------------------------------------------- coupe (car-like model)
def _profile(z):
    """(half width at the belt, belt height, roof height, roof half width) along z (front +2.05 .. rear -2.05)."""
    t = (z + 2.05) / 4.1          # 0 rear .. 1 front
    belt = 0.62
    # roof line: rear hatch 0.80 -> roof 1.13 (z -1.3 .. 0.2) -> windscreen down to the hood 0.70 at z 1.0 -> nose 0.55
    if z < -1.3:
        roof = 0.80 + (1.13 - 0.80) * ((z + 2.05) / 0.75) ** 0.7
    elif z < 0.2:
        roof = 1.13
    elif z < 1.0:
        roof = 1.13 - (1.13 - 0.72) * ((z - 0.2) / 0.8)
    else:
        roof = 0.72 - (0.72 - 0.56) * ((z - 1.0) / 1.05) ** 1.5
    hw = 0.90 - 0.10 * abs(2 * t - 1) ** 3
    rw = 0.62 if -1.3 <= z <= 0.2 else hw * 0.92
    return hw, belt, max(roof, belt + 0.05), rw


def coupe_nodes():
    zs = [-2.05 + 4.1 * i / 24 for i in range(25)]
    # cross-section ring, counter-clockwise seen from the front (+z): starts at the bottom centre
    def ring(z):
        hw, belt, roof, rw = _profile(z)
        lowhw = 0.60
        y0 = 0.05
        pts = [  # (x, y, class)  left side = +x
            (0.0, y0), (lowhw, y0), (hw * 0.97, 0.22), (hw, 0.42), (hw, belt), (rw + (hw - rw) * 0.35, belt + 0.10),
            (rw, roof - 0.06), (rw * 0.5, roof), (0.0, roof)]
        right = [(-x, y) for x, y in reversed(pts[1:-1])]
        return pts + right   # bottom centre -> left side -> roof centre -> right side
    rings = [ring(z) for z in zs]
    n = len(rings[0])
    paint = PB(0)
    plain = PB(1)
    glass = PB(2)
    for i in range(len(zs) - 1):
        za, zb = zs[i], zs[i + 1]
        for j in range(n):
            j2 = (j + 1) % n
            a = (rings[i][j][0], rings[i][j][1], za)
            b = (rings[i][j2][0], rings[i][j2][1], za)
            c = (rings[i + 1][j2][0], rings[i + 1][j2][1], zb)
            d = (rings[i + 1][j][0], rings[i + 1][j][1], zb)
            cy = (a[1] + b[1] + c[1] + d[1]) / 4
            _, belt, roof, _ = _profile((za + zb) / 2)
            is_bottom = a[1] < 0.06 and b[1] < 0.06
            cabin = -1.35 <= (za + zb) / 2 <= 0.95
            is_glass = cabin and belt + 0.1 < cy < roof - 0.03 and abs(a[0]) > 0.05
            if (za + zb) / 2 > 0.25 and (za + zb) / 2 < 0.95 and cy > belt + 0.12 and abs(a[0]) <= 0.62:
                is_glass = True   # windscreen
            s0, s1 = j / n, (j + 1) / n
            t0, t1 = 1 - i / 24, 1 - (i + 1) / 24
            uvs = [uvbox(UV_BODY, s0, t0), uvbox(UV_BODY, s1, t0), uvbox(UV_BODY, s1, t1), uvbox(UV_BODY, s0, t1)]
            pb = plain if is_bottom else glass if is_glass else paint
            if is_bottom:
                uvs = [uvbox(UV_TRIM, 0.5, 0.5)] * 4
            # quad a b c d : outward when seen from outside (ring is CCW seen from the front, z grows to the front)
            q = (a, d, c, b)
            pb.quad(*q, [uvs[0], uvs[3], uvs[2], uvs[1]])
    for pb in (paint, plain, glass):
        _fix_outward_axis(pb)
    caps = PB(1)
    # end caps (fans): front (+z) and rear (-z)
    for zi, sgn, uvb in ((len(zs) - 1, 1, UV_LIGHT_F), (0, -1, UV_LIGHT_R)):
        z = zs[zi]
        r = rings[zi]
        cx = sum(p[0] for p in r) / n
        cyy = sum(p[1] for p in r) / n
        for j in range(n):
            j2 = (j + 1) % n
            a, b = (r[j][0], r[j][1], z), (r[j2][0], r[j2][1], z)
            c = (cx, cyy, z)
            uv = lambda p: uvbox(uvb, 0.5 + p[0] / 2.0, 1 - (p[1] / 1.2))  # noqa: E731
            t = (a, b, c)
            nn = _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))
            if nn[2] * sgn < 0:
                t = (a, c, b)
            # lights band (plain) on the caps between y 0.35 and 0.55; the rest paint-coloured trim
            caps.tri(*t, uv(t[0]), uv(t[1]), uv(t[2]))
    _fix_outward(caps, (0.0, 0.55, 0.0))
    # smooth the paint normals per position (shared normals along the loft)
    _smooth(paint)
    mk = PB(1)
    fin(mk)
    body = dict(name='body', prims=[paint.p, plain.p, caps.p, glass.p, mk.p])
    return [body, dict(name='wheel', prims=wheel_prims(0.312))]


def _fix_outward_axis(pb):
    """Loft triangles face away from the body axis (x = 0, y = 0.55) at their own z."""
    p = pb.p
    for k, (a, b, c) in enumerate(p['tris']):
        A, B, C = p['positions'][a], p['positions'][b], p['positions'][c]
        n = _cross(_sub(B, A), _sub(C, A))
        m = ((A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3 - 0.55, 0.0)
        if n[0] * m[0] + n[1] * m[1] < 0:
            p['tris'][k] = (a, c, b)
            nn = _norm(_cross(_sub(C, A), _sub(B, A)))
            for i in (a, b, c):
                p['normals'][i] = nn


def _smooth(pb):
    p = pb.p
    acc = {}
    for a, b, c in p['tris']:
        A, B, C = p['positions'][a], p['positions'][b], p['positions'][c]
        n = _cross(_sub(B, A), _sub(C, A))
        for i in (a, b, c):
            k = tuple(round(x, 5) for x in p['positions'][i])
            s = acc.setdefault(k, [0.0, 0.0, 0.0])
            for j in range(3):
                s[j] += n[j]
    p['normals'] = [_norm(acc[tuple(round(x, 5) for x in q)]) for q in p['positions']]


def wheel_prims(radius, width=0.21, segs=20):
    """Authored wheel: tyre tread + sidewalls (plain, tyre tile) and a rim disc with 5 spokes on both faces (plain, rim tile).
    Wheel-local: axle = X, centred at the origin."""
    tyre = PB(1)
    rim = PB(1)
    hw = width / 2
    rin = radius * 0.68
    ang = [2 * math.pi * i / segs for i in range(segs)]
    for i in range(segs):
        a0, a1 = ang[i], ang[(i + 1) % segs]
        c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
        p = lambda x, r, c, s: (x, r * c, r * s)  # noqa: E731
        u0, u1 = i / segs, (i + 1) / segs
        # tread (outward radial)
        q = (p(-hw, radius, c0, s0), p(-hw, radius, c1, s1), p(hw, radius, c1, s1), p(hw, radius, c0, s0))
        n = _cross(_sub(q[1], q[0]), _sub(q[2], q[0]))
        if n[1] * c0 + n[2] * s0 < 0:
            q = (q[0], q[3], q[2], q[1])
        tyre.quad(*q, [uvbox(UV_TYRE, u0, 0), uvbox(UV_TYRE, u1, 0), uvbox(UV_TYRE, u1, 1), uvbox(UV_TYRE, u0, 1)])
        for side in (-1, 1):
            x = side * hw
            q = (p(x, rin, c0, s0), p(x, radius, c0, s0), p(x, radius, c1, s1), p(x, rin, c1, s1))
            n = _cross(_sub(q[1], q[0]), _sub(q[2], q[0]))
            if n[0] * side < 0:
                q = (q[0], q[3], q[2], q[1])
            tyre.quad(*q, [uvbox(UV_TYRE, u0, 0.2), uvbox(UV_TYRE, u0, 0.8), uvbox(UV_TYRE, u1, 0.8), uvbox(UV_TYRE, u1, 0.2)])
            # rim disc (slightly recessed), centre fan
            xr = side * (hw - 0.02)
            ctr = (xr, 0.0, 0.0)
            spoke = (i * 5 // segs) % 2 == 0
            t = (ctr, p(xr, rin, c0, s0), p(xr, rin, c1, s1))
            n = _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))
            if n[0] * side < 0:
                t = (t[0], t[2], t[1])
            uvc = uvbox(UV_RIM, 0.5, 0.5)
            uvf = lambda pt: uvbox(UV_RIM, 0.5 + 0.5 * pt[1] / rin * (0.9 if spoke else 0.6), 0.5 + 0.5 * pt[2] / rin * (0.9 if spoke else 0.6))  # noqa: E731
            rim.tri(*t, uvc, uvf(t[1]), uvf(t[2]))
    return [tyre.p, rim.p]


# ---------------------------------------------------------------- writing
MATERIALS = [dict(name='paint.body', image=0, bm_class='paint'), dict(name='plain.trim', image=0, bm_class='plain'),
             dict(name='glass.windows', image=0, bm_class='glass')]


def write_demo(out_dir, which):
    os.makedirs(out_dir, exist_ok=True)
    img, mask = make_texture()
    png.write_rgba(os.path.join(out_dir, 'texture.png'), W, H, img)
    png.write_rgba(os.path.join(out_dir, 'paint_mask.png'), W, H, mask)
    nodes = wedge_nodes() if which == 'wedge' else coupe_nodes()
    used = sorted({p['material'] for nd in nodes for p in nd['prims']})
    mats = MATERIALS[:max(used) + 1]
    path = os.path.join(out_dir, which + '.gltf')
    gltf.write(path, nodes, mats, ['texture.png'], generator='carimport demo (original, procedural)')
    return path
