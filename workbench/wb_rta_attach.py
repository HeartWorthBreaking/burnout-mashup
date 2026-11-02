r"""wb_rta_attach - the ONE attachment-point workflow for retail track extensions (Workbench 0.33 retail-style authoring, 2026-11-01).

Attachment point = (unit, side, setback, along): a point beside the retail AI route inside the unit's region quad. The piece is
a simple retail-style building (box with a flat roof, the editor's building_faces generator) textured with a material that unit
ALREADY draws, standing on the retail collision floor (ground sampled at every footprint corner; the largest gap between the
walls' base and the ground is reported as the seam). Output: an `append_decor` edit for wb_rta_ext plus a preview report:
  width / depth / height / base elevation, material + host record, seam gaps, region quad check, mesh slot / record budget,
  LOD (not in the far LOD), visibility (drawn with the host record), collision (none: decorative), changed sections.
Everything is read only on game data; the decoded view cache (wb_retail) supplies the collision floor and route.
"""
import json
import math
import os
import struct

import wb_retail
import wb_rta_ext as X
import wb_rta_geo as G
import wb_te_bldg as tb


def _view(cfg, folder):
    v, cdir, _r = wb_retail.decode(cfg, folder)
    return v, cdir


_GRID = {}


def _floor_grid(cfg, folder, cell=16.0):
    """up-facing retail collision triangles binned in a plan grid (cached per decoded view)"""
    v, cdir = _view(cfg, folder)
    if cdir in _GRID:
        return _GRID[cdir]
    blob = open(os.path.join(cdir, 'coll.bin'), 'rb').read()
    grid = {}
    for c in v['collision']:
        n = c['vertices']
        P = struct.unpack_from('<%df' % (3 * n), blob, c['off'])
        for t in range(0, n - 2, 3):
            a, b, d = P[3 * t:3 * t + 3], P[3 * t + 3:3 * t + 6], P[3 * t + 6:3 * t + 9]
            _ar, nrm, _c = G.tri_geo(a, b, d)
            if abs(nrm[1]) < 0.7:
                continue
            x0, x1 = int(min(a[0], b[0], d[0]) // cell), int(max(a[0], b[0], d[0]) // cell)
            z0, z1 = int(min(a[2], b[2], d[2]) // cell), int(max(a[2], b[2], d[2]) // cell)
            for i in range(x0, x1 + 1):
                for k in range(z0, z1 + 1):
                    grid.setdefault((i, k), []).append((a, b, d, c['surface']))
    _GRID[cdir] = (cell, grid)
    return _GRID[cdir]


def ground_at(cfg, folder, x, z, near_y=None):
    """highest retail collision floor (up-facing triangle) under (x, z), or the one nearest near_y -> (y, surface) or None"""
    cell, grid = _floor_grid(cfg, folder)
    best = []
    for a, b, d, sf in grid.get((int(x // cell), int(z // cell)), ()):
        den = (b[2] - d[2]) * (a[0] - d[0]) + (d[0] - b[0]) * (a[2] - d[2])
        if abs(den) < 1e-9:
            continue
        l1 = ((b[2] - d[2]) * (x - d[0]) + (d[0] - b[0]) * (z - d[2])) / den
        l2 = ((d[2] - a[2]) * (x - d[0]) + (a[0] - d[0]) * (z - d[2])) / den
        l3 = 1 - l1 - l2
        if min(l1, l2, l3) < -1e-6:
            continue
        best.append((l1 * a[1] + l2 * b[1] + l3 * d[1], sf))
    if not best:
        return None
    if near_y is not None:
        return min(best, key=lambda t: abs(t[0] - near_y))
    return max(best)


def attachment_plan(cfg, folder, unit, side=-1, setback=18.0, along=0.5, width=14.0, depth=10.0, height=9.0, texture=None,
                    roof_texture=None, uv_m=6.0):
    info = X.unit_info(cfg, folder, unit)
    v, cdir = _view(cfg, folder)
    lines, cyc = G.route_lines(v)
    region = info['region']
    # the route samples inside this unit's region quad; the attachment sits at fraction `along` of them
    R = G.RouteIndex(lines, cyc)
    inside = [p for p in R.samples if p[4] == 0 and X.in_region(region, p[0], p[2])]
    if not inside:
        raise X.ExtError('unit %d: no route centre line inside its region quad' % unit)
    p = inside[max(0, min(len(inside) - 1, int(along * (len(inside) - 1))))]
    tx, tz = p[5], p[6]
    nx, nz = -tz, tx
    cx, cz = p[0] + side * nx * (setback + depth / 2), p[2] + side * nz * (setback + depth / 2)
    hw, hd = width / 2, depth / 2
    P = [(cx - tx * hw - nx * hd, cz - tz * hw - nz * hd), (cx + tx * hw - nx * hd, cz + tz * hw - nz * hd),
         (cx + tx * hw + nx * hd, cz + tz * hw + nz * hd), (cx - tx * hw + nx * hd, cz - tz * hw + nz * hd)]
    if sum(P[i][0] * P[(i + 1) % 4][1] - P[(i + 1) % 4][0] * P[i][1] for i in range(4)) < 0:
        P.reverse()
    texs = [h['texture'] for h in info['hosts'] if h['strip'] and h['texture']]
    if texture is None or texture not in texs:
        raise X.ExtError('texture %r: unit %d draws these (an extension reuses one of them): %s' % (texture, unit, ', '.join(sorted(set(texs)))))
    roof_texture = roof_texture if roof_texture in texs else texture
    gs = [ground_at(cfg, folder, x, z, p[1]) for x, z in P]
    if any(g is None for g in gs):
        raise X.ExtError('no retail collision floor under every corner (corners %s): move the attachment' % (
            [[round(x, 1), round(z, 1)] for x, z in P]))
    ys = [g[0] for g in gs]
    base = min(ys) - 0.05
    seam = max(ys) - base
    out_corners = [c for c in P if not X.in_region(region, c[0], c[1])]
    # what the piece stands on (MEASURED from the retail collision): a 5 x 5 grid over the footprint grown by 1 m; any sample on
    # tarmac (surface 0x0001) = the piece would stand on a drivable road (found by the demo B screenshots, 2026-11-02)
    on_road = []
    for i in range(5):
        for k in range(5):
            fx, fz = -1 + 2 * i / 4.0, -1 + 2 * k / 4.0
            x = cx + tx * fx * (hw + 1) + nx * fz * (hd + 1)
            z = cz + tz * fx * (hw + 1) + nz * fz * (hd + 1)
            g = ground_at(cfg, folder, x, z, p[1])
            if g and (int(g[1], 16) & 0xFF) == 0x01:
                on_road.append([round(x, 1), round(z, 1)])
    # every AI lane centre line (all lanes, not only the main ones) must stay outside the footprint + 2 m
    lanes_in = 0
    for ln in (v.get('route') or {}).get('lanes') or []:
        for q in ln.get('centre') or []:
            lx, lz = q[0] - cx, q[2] - cz
            if abs(lx * tx + lz * tz) <= hw + 2 and abs(lx * nx + lz * nz) <= hd + 2:
                lanes_in += 1
    faces, _binfo = tb.building_faces(P, base, height, texture, roof_texture, 'flat', 2.0, [], 0.0, uv_m)
    by_tex = {}
    for mat, corners in faces:                                # fan-triangulate every face, grouped by material
        pts = [(c[0], c[1]) for c in corners]                 # (position, uv)
        for k in range(1, len(pts) - 1):
            tri = [pts[0], pts[k], pts[k + 1]]
            by_tex.setdefault(mat, []).append([[float(q[0][0]), float(q[0][1]), float(q[0][2]), float(q[1][0]), float(q[1][1])]
                                               for q in tri])
    edits = [{'op': 'append_decor', 'unit': unit, 'texture': tex, 'triangles': by_tex[tex]} for tex in sorted(by_tex)]
    est = 0x90 * len(edits) + sum(len(e['triangles']) * 3 * 28 + len(e['triangles']) * 6 for e in edits)
    report = {'unit': unit, 'side': 'left' if side > 0 else 'right', 'centre': [round(cx, 2), round(cz, 2)],
              'width_m': width, 'depth_m': depth, 'height_m': height, 'base_y': round(base, 3),
              'ground': [{'y': round(g[0], 3), 'surface': g[1]} for g in gs], 'seam_max_gap_m': round(seam, 3),
              'materials': {k: len(v) for k, v in by_tex.items()}, 'region_quad_ok': not out_corners, 'route_y_here': round(p[1], 3),
              'mesh_free_bytes': info['mesh_free_bytes'], 'records_free': info['records_free'], 'estimated_bytes': est,
              'stands_on_tarmac_samples': on_road, 'ai_lane_points_inside': lanes_in,
              'fits': (not out_corners) and not on_road and not lanes_in and est + 0x1000 <= info['mesh_free_bytes']
                      and len(edits) <= info['records_free'],
              'lod': 'NOT in the far LOD: drawn only where this unit\'s full mesh is drawn (|rel| <= 4); pops out beyond',
              'visibility': 'drawn with its host record (same material, every camera that draws the host)',
              'collision': 'NONE (decorative; cars pass through it)',
              'changes': ['streamed.dat: unit %d mesh block (records appended; may grow by pages); later blocks move unchanged' % unit,
                          'static.dat: unit-table entries only (offsets / sizes)', 'every other file byte-identical'],
              'evidence': 'append rule = KB MESH_AND_COLLISION s4 (CT1, runtime-proven for a road ramp); this building use: OFFLINE only'}
    probs = []
    if out_corners:
        probs.append('corners outside unit %d region quad: smaller setback / size' % unit)
    if on_road:
        probs.append('%d footprint sample(s) stand on tarmac (a drivable road): larger setback or the other side' % len(on_road))
    if lanes_in:
        probs.append('%d AI lane point(s) pass through the footprint: move it off the racing / traffic lanes' % lanes_in)
    if probs:
        report['problem'] = '; '.join(probs)
    report['setback_m'], report['along'] = setback, along
    return {'edits': edits, 'report': report, 'setback': setback, 'along': along}



def find_clear(cfg, folder, unit, side=-1, along=0.5, width=12.0, depth=9.0, height=10.0, texture=None, roof_texture=None,
               setbacks=(10, 14, 18, 22, 26, 30, 36, 42, 50, 60), alongs=None):
    """the nearest setback (then other along positions, then the other side) where the piece fits: inside the region quad, off
    tarmac, off every AI lane. -> (plan or None, tried list)"""
    tried = []
    alongs = alongs or [along] + [a for a in (0.2, 0.35, 0.5, 0.65, 0.8) if a != along]
    for sd in (side, -side):
        for al in alongs:
            for sb in setbacks:
                try:
                    pl = attachment_plan(cfg, folder, unit, sd, float(sb), al, width, depth, height, texture, roof_texture)
                except X.ExtError as e:
                    tried.append({'side': sd, 'along': al, 'setback': sb, 'why': str(e)[:120]})
                    continue
                if pl['report']['fits'] and pl['report']['seam_max_gap_m'] < 1.0:
                    return pl, tried
                tried.append({'side': sd, 'along': al, 'setback': sb, 'why': pl['report'].get('problem') or 'seam %.2f m' % pl['report']['seam_max_gap_m']})
    return None, tried
