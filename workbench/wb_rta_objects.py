r"""wb_rta_objects - catalogue of the BUILDINGS and OBJECTS baked into each retail track's render mesh (Workbench 0.33 retail-style authoring, 2026-11-02).

Retail buildings are not separate records in the data: they are part of each section's render mesh. This module splits a track's
OPAQUE render triangles (wb_retail's decoded view) into connected pieces: triangles that share a vertex position (2 cm grid)
belong together, across materials (a facade, its roof and its trims form one piece). The road / ground network (one huge
connected piece) and pieces larger than 150 m are left out and counted. Each piece is MEASURED: footprint, height, triangles,
textures, up / vertical area, distance from the AI route, memory estimate; class:
  building   height >= 5 m, footprint 4..150 m, vertical area >= 35 %
  structure  everything else in 2..150 m (walls, kiosks, bridges, barriers, platforms, ...)
Cut-out / blended triangles (railings, foliage, glass) are not in any piece (they cannot be authored materials).
Instance models (posts, trees, signs, cars, benches) and smashable prop types come from wb_rta_catalog (fr_propmesh).

Cache: <catalogue dir>\objects.json (pieces + their triangle references into the view cache), keyed by the catalogue key.
Everything here is decoded from YOUR game data: LOCAL ONLY. Placing a piece in a project = a GEOMETRY COPY.
"""
import json
import os
import struct
import time

import wb_retail
import wb_rta_catalog as CAT
import wb_rta_geo as G

SCHEMA = 'bm-rta-objects/1'
Q = 0.02                    # vertex position grid (m) for connectivity
MAX_SIDE = 150.0


def _cdir(cfg, cat):
    return os.path.join(CAT.cat_root(cfg), '%s-%s' % (cat['track'].replace('/', '_'), cat['cache_key'][:12]))


def build(cfg, track, force=False):
    cat = CAT.load(cfg, track)
    out = os.path.join(_cdir(cfg, cat), 'objects.json')
    if not force and os.path.isfile(out):
        try:
            o = json.load(open(out, encoding='utf-8'))
            if o.get('schema') == SCHEMA and o.get('catalogue_key') == cat['cache_key']:
                return o
        except (OSError, ValueError):
            pass
    t0 = time.time()
    v = json.load(open(os.path.join(cat['view_cache'], 'view.json'), encoding='utf-8'))
    blob = open(os.path.join(cat['view_cache'], 'mesh.bin'), 'rb').read()
    par = {}

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    tris = []
    for gi, e in enumerate(v['mesh']):
        if e['render'] != 'opaque' or not e['texture_name']:
            continue
        P = struct.unpack_from('<%df' % (3 * e['vertices']), blob, e['off_pos'])
        idx = struct.unpack_from('<%dI' % e['indices'], blob, e['off_idx'])
        for k in range(0, len(idx) - 2, 3):
            keys = []
            for j in idx[k:k + 3]:
                key = (round(P[3 * j] / Q), round(P[3 * j + 1] / Q), round(P[3 * j + 2] / Q))
                par.setdefault(key, key)
                keys.append(key)
            a = find(keys[0])
            for kk in keys[1:]:
                b = find(kk)
                if a != b:
                    par[b] = a
            tris.append((gi, k // 3, keys[0], [P[3 * j:3 * j + 3] for j in idx[k:k + 3]], e['texture_name']))
    comp = {}
    for gi, ti, k0, pts, tn in tris:
        c = find(k0)
        d = comp.setdefault(c, {'n': 0, 'mn': [1e18] * 3, 'mx': [-1e18] * 3, 'refs': {}, 'tex': {}, 'up': 0.0, 'vert': 0.0, 'area': 0.0})
        d['n'] += 1
        d['refs'].setdefault(gi, []).append(ti)
        d['tex'][tn] = d['tex'].get(tn, 0) + 1
        ar, n, _c = G.tri_geo(*pts)
        d['area'] += ar
        if abs(n[1]) >= 0.85:
            d['up'] += ar
        elif abs(n[1]) <= 0.3:
            d['vert'] += ar
        for p in pts:
            for i in range(3):
                d['mn'][i] = min(d['mn'][i], p[i])
                d['mx'][i] = max(d['mx'][i], p[i])
    lines, cyc = G.route_lines(v)
    R = G.RouteIndex(lines, cyc) if lines else None
    pieces, skipped = [], {'too_large (road / ground network, terrain)': 0, 'too_small (< 2 m or < 8 triangles)': 0}
    for d in comp.values():
        sx, sy, sz = (d['mx'][i] - d['mn'][i] for i in range(3))
        side = max(sx, sz)
        if side > MAX_SIDE:
            skipped['too_large (road / ground network, terrain)'] += d['n']
            continue
        if side < 2.0 or d['n'] < 8:
            skipped['too_small (< 2 m or < 8 triangles)'] += d['n']
            continue
        a = d['area'] or 1e-9
        vf, uf = d['vert'] / a, d['up'] / a
        cls = 'building' if sy >= 5.0 and side >= 4.0 and vf >= 0.35 else 'structure'
        cx, cz = (d['mn'][0] + d['mx'][0]) / 2, (d['mn'][2] + d['mx'][2]) / 2
        pr = R.project(cx, d['mn'][1], cz, 600.0) if R else None
        pieces.append({'class': cls, 'centre': [round(cx, 2), round(d['mn'][1], 2), round(cz, 2)],
                       'bmin': [round(x, 2) for x in d['mn']], 'bmax': [round(x, 2) for x in d['mx']],
                       'footprint_m': [round(sx, 1), round(sz, 1)], 'height_m': round(sy, 1), 'triangles': d['n'],
                       'textures': dict(sorted(d['tex'].items(), key=lambda kv: -kv[1])), 'vertical_fraction': round(vf, 2),
                       'up_fraction': round(uf, 2), 'route_distance_m': round(pr['dist'], 1) if pr else None,
                       'memory_bytes_est': int(d['n'] * (cat['cost'].get('mesh_bytes_per_triangle_measured') or 52.0)),
                       'refs': {str(k): v_ for k, v_ in sorted(d['refs'].items())}})
    pieces.sort(key=lambda p: (0 if p['class'] == 'building' else 1, -p['triangles'], p['centre']))
    for i, p in enumerate(pieces):
        p['id'] = 'B%d' % i if p['class'] == 'building' else 'S%d' % i
    o = {'schema': SCHEMA, 'track': track, 'catalogue_key': cat['cache_key'], 'pieces': pieces, 'skipped_triangles': skipped,
         'counts': {'buildings': sum(1 for p in pieces if p['class'] == 'building'),
                    'structures': sum(1 for p in pieces if p['class'] == 'structure'), 'opaque_triangles': len(tris)},
         'method': 'connected opaque render triangles (shared vertex positions, %.2f m grid), classes by measured size / facing' % Q,
         'local_only': True, 'seconds': round(time.time() - t0, 2)}
    with open(out + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(o, f)
    os.replace(out + '.tmp', out)
    return o


def piece(cfg, track, pid):
    o = build(cfg, track)
    p = next((x for x in o['pieces'] if x['id'] == pid), None)
    if not p:
        raise CAT.CatalogError('%s has no building / structure %s' % (track, pid))
    return p


_VIEW = {}


def _view_blob(cat):
    """the decoded view + mesh blob of a track, cached per view cache folder (read once, reused for every piece)"""
    k = cat['view_cache']
    if k not in _VIEW:
        if len(_VIEW) > 4:
            _VIEW.clear()
        _VIEW[k] = (json.load(open(os.path.join(k, 'view.json'), encoding='utf-8')), open(os.path.join(k, 'mesh.bin'), 'rb').read())
    return _VIEW[k]


def piece_triangles(cfg, track, pid, cat=None, p=None):
    """-> [(texture name, texture index, [(pos, uv, colour) x 3])] of one piece, world positions as in the retail track"""
    cat = cat or CAT.load(cfg, track)
    p = p or piece(cfg, track, pid)
    v, blob = _view_blob(cat)
    out = []
    for gs, tis in p['refs'].items():
        e = v['mesh'][int(gs)]
        nv = e['vertices']
        P = struct.unpack_from('<%df' % (3 * nv), blob, e['off_pos'])
        UV = struct.unpack_from('<%df' % (2 * nv), blob, e['off_uv'])
        C = struct.unpack_from('<%df' % (3 * nv), blob, e['off_col'])
        idx = struct.unpack_from('<%dI' % e['indices'], blob, e['off_idx'])
        for ti in tis:
            corners = [(tuple(P[3 * i:3 * i + 3]), (UV[2 * i], UV[2 * i + 1]), tuple(C[3 * i:3 * i + 3])) for i in idx[3 * ti:3 * ti + 3]]
            out.append((e['texture_name'], e['texture'], corners))
    return out


def all_rows(cfg, tracks=None, progress=None):
    """every catalogued track's pieces (built on first use) -> flat rows for search"""
    idx = json.load(open(os.path.join(CAT.cat_root(cfg), 'INDEX.json'), encoding='utf-8'))
    rows = []
    good = [r for r in idx['tracks'] if r.get('ok') and (not tracks or r['track'] in tracks)]
    for i, r in enumerate(good):
        if progress:
            progress(i / max(1, len(good)), r['track'])
        o = build(cfg, r['track'])
        for p in o['pieces']:
            rows.append({'track': r['track'], 'id': p['id'], 'kind': p['class'], 'size_m': p['footprint_m'] + [p['height_m']],
                         'triangles': p['triangles'], 'textures': list(p['textures'])[:4], 'route_distance_m': p['route_distance_m']})
    return rows
