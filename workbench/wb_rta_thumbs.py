r"""wb_rta_thumbs - on-demand thumbnails for the retail-style asset library (Workbench 0.33 retail-style authoring, 2026-11-01). LOCAL ONLY.

Textures: the decoded preview PNG of wb_retail's view cache, box-filtered to 64 x 64.
Models (instance models I<n>, prop types P<n>): a flat-shaded orthographic front view (x / y plane) of LOD0 from fr_propmesh,
96 x 96, tinted with the model texture's mean colour when its preview exists, else neutral grey (labelled approximate).
Thumbnails are made only when asked for (never all at full detail) and cached beside the catalogue: <catalogue dir>\thumbs\.
"""
import os
import sys

import wb_te_retail as R

HERE = os.path.dirname(os.path.abspath(__file__))


def _cache(cdir, name):
    d = os.path.join(cdir, 'thumbs')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def texture_thumb(cat, cdir, tex_index, size=64):
    out = _cache(cdir, 't%03d.png' % tex_index)
    if os.path.isfile(out):
        return out
    src = os.path.join(cat['view_cache'], 'tex', 't%03d.png' % tex_index)
    w, h, rows = R.png_read_rgba(open(src, 'rb').read())
    rows_out = []
    for y in range(size):
        y0, y1 = y * h // size, max(y * h // size + 1, (y + 1) * h // size)
        row = bytearray()
        for x in range(size):
            x0, x1 = x * w // size, max(x * w // size + 1, (x + 1) * w // size)
            acc = [0, 0, 0]
            n = 0
            sy = max(1, (y1 - y0) // 4)
            sx = max(1, (x1 - x0) // 4)
            for yy in range(y0, y1, sy):
                r = rows[yy]
                for xx in range(x0, x1, sx):
                    o = 4 * xx
                    acc[0] += r[o]
                    acc[1] += r[o + 1]
                    acc[2] += r[o + 2]
                    n += 1
            row += bytes((acc[0] // n, acc[1] // n, acc[2] // n, 255))
        rows_out.append(bytes(row))
    data = R.png_write_rgb(size, size, rows_out)
    with open(out + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(out + '.tmp', out)
    return out


def _mean_colour(cat, tex_name):
    for t in cat.get('textures') or []:
        if t['texture'] == tex_name and t.get('texture_index') is not None:
            p = os.path.join(cat['view_cache'], 'tex', 't%03d.png' % t['texture_index'])
            if os.path.isfile(p):
                w, h, rows = R.png_read_rgba(open(p, 'rb').read())
                acc = [0, 0, 0]
                n = 0
                for y in range(0, h, max(1, h // 16)):
                    for x in range(0, w, max(1, w // 16)):
                        if rows[y][4 * x + 3] > 32:
                            for i in range(3):
                                acc[i] += rows[y][4 * x + i]
                            n += 1
                if n:
                    return [a / n / 255.0 for a in acc]
    return None


def piece_thumb(cfg, cat, cdir, pid, size=96, yaw_deg=35):
    """a building / structure piece: flat-shaded 3/4 view from yaw_deg, per-texture mean colours (approximate)"""
    out = _cache(cdir, '%s.png' % pid if yaw_deg == 35 and size == 96 else '%s_y%d_s%d.png' % (pid, int(yaw_deg) % 360, size))
    if os.path.isfile(out):
        return out
    import math
    import wb_rta_objects as OB
    tris = OB.piece_triangles(cfg, cat['track'], pid)
    cols = {}
    for tn, _ti, _c in tris:
        if tn not in cols:
            cols[tn] = _mean_colour(cat, tn) or [0.6, 0.6, 0.6]
    pts = [c[0] for _t, _i, cs in tris for c in cs]
    cx = (max(p[0] for p in pts) + min(p[0] for p in pts)) / 2
    cy = (max(p[1] for p in pts) + min(p[1] for p in pts)) / 2
    cz = (max(p[2] for p in pts) + min(p[2] for p in pts)) / 2
    yaw, pit = math.radians(yaw_deg), math.radians(25)
    cyw, syw, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pit), math.sin(pit)

    def proj(p):
        x, y, z = p[0] - cx, p[1] - cy, p[2] - cz
        x, z = cyw * x - syw * z, syw * x + cyw * z
        y, z = cp * y - sp * z, sp * y + cp * z
        return x, y, z
    Pr = [[proj(c[0]) for c in cs] for _t, _i, cs in tris]
    span = max(max(abs(q[0]) for t in Pr for q in t), max(abs(q[1]) for t in Pr for q in t)) * 2 or 1.0
    sc = (size - 8) / span
    img = [[(235, 235, 235)] * size for _ in range(size)]
    zb = [[-1e18] * size for _ in range(size)]
    for (tn, _ti, cs), T in zip(tris, Pr):
        a, b, c = [q[0] for q in cs]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1.0
        lit = 0.4 + 0.6 * abs(n[1] * 0.6 + n[0] * 0.5 + n[2] * 0.3) / ln
        base = cols[tn]
        col = tuple(max(0, min(255, int(255 * base[i] * lit))) for i in range(3))
        S = [(q[0] * sc + size / 2, size / 2 - q[1] * sc, q[2]) for q in T]
        (ax, ay, az), (bx, by, bz), (qx, qy, qz) = S
        den = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
        if abs(den) < 1e-9:
            continue
        for y in range(max(0, int(min(ay, by, qy))), min(size - 1, int(max(ay, by, qy)) + 1) + 1):
            for x in range(max(0, int(min(ax, bx, qx))), min(size - 1, int(max(ax, bx, qx)) + 1) + 1):
                l1 = ((by - qy) * (x - qx) + (qx - bx) * (y - qy)) / den
                l2 = ((qy - ay) * (x - qx) + (ax - qx) * (y - qy)) / den
                l3 = 1 - l1 - l2
                if l1 < 0 or l2 < 0 or l3 < 0:
                    continue
                z = -(l1 * az + l2 * bz + l3 * qz)
                if z > zb[y][x]:
                    zb[y][x] = z
                    img[y][x] = col
    rows = [bytes(c for px in r for c in (px[0], px[1], px[2], 255)) for r in img]
    data = R.png_write_rgb(size, size, rows)
    with open(out + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(out + '.tmp', out)
    return out


def model_thumb(cat, cdir, model_id, size=96):
    out = _cache(cdir, '%s.png' % model_id)
    if os.path.isfile(out):
        return out
    pm = os.path.join(HERE, 'format_research', 'props_mesh')
    fr = os.path.join(HERE, 'format_research')
    for p in (fr, pm):
        if p not in sys.path:
            sys.path.insert(0, p)
    import fr_propmesh
    t = fr_propmesh.load(cat['source']['folder'])
    fam, k = model_id[0], int(model_id[1:])
    tris = t.triangles(fam, k, 0)
    pts = [v[0] for _, vs in tris for v in vs]
    if not pts:
        raise ValueError('%s has no LOD0 triangles' % model_id)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    sc = (size - 8) / span
    base = _mean_colour(cat, t.texture_of(fam, k)) or [0.6, 0.6, 0.6]
    img = [[(235, 235, 235)] * size for _ in range(size)]
    zb = [[-1e18] * size for _ in range(size)]
    for _, vs in tris:
        P = [((p[0][0] - cx) * sc + size / 2, size / 2 - (p[0][1] - cy) * sc, p[0][2]) for p in vs]
        a, b, c = [p[0] for p in vs]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1.0
        lit = 0.35 + 0.65 * abs(n[2] * 0.7 + n[1] * 0.5 + n[0] * 0.3) / ln   # double-sided (retail strips: mixed winding)
        col = tuple(max(0, min(255, int(255 * base[i] * lit))) for i in range(3))
        x0, x1 = max(0, int(min(p[0] for p in P))), min(size - 1, int(max(p[0] for p in P)) + 1)
        y0, y1 = max(0, int(min(p[1] for p in P))), min(size - 1, int(max(p[1] for p in P)) + 1)
        (ax, ay, az), (bx, by, bz), (qx, qy, qz) = P
        den = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
        if abs(den) < 1e-9:
            continue
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                l1 = ((by - qy) * (x - qx) + (qx - bx) * (y - qy)) / den
                l2 = ((qy - ay) * (x - qx) + (ax - qx) * (y - qy)) / den
                l3 = 1 - l1 - l2
                if l1 < 0 or l2 < 0 or l3 < 0:
                    continue
                z = l1 * az + l2 * bz + l3 * qz
                if z > zb[y][x]:
                    zb[y][x] = z
                    img[y][x] = col
    rows = [bytes(c for px in r for c in (px[0], px[1], px[2], 255)) for r in img]
    data = R.png_write_rgb(size, size, rows)
    with open(out + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(out + '.tmp', out)
    return out
