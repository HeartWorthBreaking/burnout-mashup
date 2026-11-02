r"""wb_rta_assets - TRUSTED asset library on top of the object catalogue (Workbench 0.33 retail-style authoring, 2026-11-02). LOCAL ONLY.

For every building / structure piece (wb_rta_objects) and instance model / prop type (wb_rta_catalog), MEASURED facts:
  facing     area of vertical faces per 45-degree sector of their outward normal (retail faces are ONE-SIDED: back-face culled);
             front = the sector with the most textured vertical area; covered sectors -> supported viewing angles
  road side  the direction from the piece to the nearest point of its ORIGINAL track's AI route; front_vs_road = angle
             between the front and that direction (small = the piece was built to face the road)
  shell      'open shell' when sectors opposite the front have no faces (back missing), 'no roof' when no up-facing area in the
             top 20 % of its height
  anchor     ground anchor = centre of the footprint at the lowest vertex height; footprint measured ALONG the front direction
  materials  textures, render class (pieces hold only opaque triangles; cut-out parts of the same building are not in the piece)
  LOD / collision  a COPY has no retail far-LOD (the authored build decimates it); retail collision is not copied - the copy gets
             collision from its faces (keep) or none
  category   intact building (closed: >= 6 of 8 sectors + roof) | building shell / facade | scenery fragment | structure |
             static mesh (instance model) | prop (smashable prop type; placed as STATIC mesh unless a prop writer exists)
  confidence a number 0..1 from how clear the measurement is, plus the reasons - never 'verified'
Overrides (user corrections: front angle, category, favourite, note) live in <state>\rta_asset_overrides.json and always win;
the measured values stay visible next to them. Cache: <catalogue dir>\assets.json, key = catalogue key + TOOL_VERSION + settings.
"""
import hashlib
import json
import math
import os
import time

import wb_rta_catalog as CAT
import wb_rta_geo as GEO
import wb_rta_objects as OB

TOOL_VERSION = 'rta-assets/1'
SETTINGS = {'sectors': 8, 'roof_band': 0.2, 'closed_sectors': 6, 'shell_min_area_frac': 0.04}


def _key(cat):
    return hashlib.sha256(json.dumps({'cat': cat['cache_key'], 'tool': TOOL_VERSION, 'settings': SETTINGS}, sort_keys=True).encode()).hexdigest()


def _cdir(cfg, cat):
    return os.path.join(CAT.cat_root(cfg), '%s-%s' % (cat['track'].replace('/', '_'), cat['cache_key'][:12]))


def analyse_piece(tris, route):
    """tris = [(texture, index, [(pos, uv, colour) x 3])] in the track's own frame -> measured facts"""
    n_sec = SETTINGS['sectors']
    sec = [0.0] * n_sec
    up_top = 0.0
    P = [c[0] for _t, _i, cs in tris for c in cs]
    y0, y1 = min(p[1] for p in P), max(p[1] for p in P)
    h = y1 - y0
    tot = 0.0
    for _t, _i, cs in tris:
        ar, n, cen = GEO.tri_geo(*[c[0] for c in cs])
        tot += ar
        if abs(n[1]) <= 0.3:
            ang = math.atan2(n[2], n[0])
            sec[int(((ang + 2 * math.pi) % (2 * math.pi)) / (2 * math.pi) * n_sec) % n_sec] += ar
        elif n[1] > 0.7 and cen[1] >= y1 - SETTINGS['roof_band'] * max(h, 1e-6):
            up_top += ar
    vert = sum(sec) or 1e-9
    front_s = max(range(n_sec), key=lambda i: sec[i])
    front_deg = (front_s + 0.5) * 360.0 / n_sec
    covered = [i for i in range(n_sec) if sec[i] >= SETTINGS['shell_min_area_frac'] * vert]
    opposite = [(front_s + n_sec // 2 + d) % n_sec for d in (-1, 0, 1)]
    back_missing = not any(i in covered for i in opposite)
    cx = (max(p[0] for p in P) + min(p[0] for p in P)) / 2
    cz = (max(p[2] for p in P) + min(p[2] for p in P)) / 2
    road = None
    if route is not None:
        d, smp = route.nearest(cx, cz, 400.0)
        if smp is not None:
            rd = math.degrees(math.atan2(smp[2] - cz, smp[0] - cx)) % 360
            diff = abs((front_deg - rd + 180) % 360 - 180)
            road = {'distance_m': round(d, 1), 'road_direction_deg': round(rd, 1), 'front_vs_road_deg': round(diff, 1)}
    # footprint along the front direction
    fr = math.radians(front_deg)
    fx, fz = math.cos(fr), math.sin(fr)
    a = [(p[0] - cx) * fx + (p[2] - cz) * fz for p in P]
    b = [-(p[0] - cx) * fz + (p[2] - cz) * fx for p in P]
    depth, width = max(a) - min(a), max(b) - min(b)
    closed = len(covered) >= SETTINGS['closed_sectors'] and up_top > 0
    reasons, conf = [], 1.0
    share = sec[front_s] / vert
    if share < 0.3:
        conf -= 0.3
        reasons.append('no dominant facade (front sector holds %.0f %% of the wall area)' % (100 * share))
    if road and road['front_vs_road_deg'] > 60:
        conf -= 0.2
        reasons.append('the measured front does not face its original road (%.0f deg off)' % road['front_vs_road_deg'])
    if not road:
        conf -= 0.2
        reasons.append('no AI route within 400 m to check the road side')
    return {'front_deg': round(front_deg, 1), 'facing_area_by_sector_m2': [round(x, 1) for x in sec],
            'supported_view_sectors': covered, 'one_sided': True, 'back_missing': back_missing, 'roof': up_top > 0,
            'closed': closed, 'anchor': [round(cx, 2), round(y0, 2), round(cz, 2)], 'height_m': round(h, 1),
            'footprint_along_front_m': {'width': round(width, 1), 'depth': round(depth, 1)}, 'original_road': road,
            'front_confidence': round(max(0.0, conf), 2), 'confidence_reasons': reasons, 'wall_area_m2': round(vert, 1),
            'total_area_m2': round(tot, 1)}


def _category(p, f):
    if p['class'] == 'building':
        if f['closed']:
            return 'intact building', 0.7
        return 'building shell / facade', 0.75 if f['back_missing'] or not f['roof'] else 0.5
    side = max(p['footprint_m'])
    if side < 6 and p['height_m'] < 4:
        return 'scenery fragment', 0.6
    return 'structure', 0.5


def build(cfg, track, force=False):
    cat = CAT.load(cfg, track)
    key = _key(cat)
    out = os.path.join(_cdir(cfg, cat), 'assets.json')
    if not force and os.path.isfile(out):
        try:
            a = json.load(open(out, encoding='utf-8'))
            if a.get('key') == key:
                return a
        except (OSError, ValueError):
            pass
    t0 = time.time()
    o = OB.build(cfg, track)
    v = json.load(open(os.path.join(cat['view_cache'], 'view.json'), encoding='utf-8'))
    lines, cyc = GEO.route_lines(v)
    route = GEO.RouteIndex(lines, cyc) if lines else None
    rows = []
    for p in o['pieces']:
        tris = OB.piece_triangles(cfg, track, p['id'], cat, p)
        f = analyse_piece(tris, route)
        c, cc = _category(p, f)
        warn = []
        if f['back_missing']:
            warn.append('OPEN SHELL: no faces on the side opposite the front - looks hollow from behind')
        if not f['roof']:
            warn.append('no roof: hollow from above')
        warn.append('one-sided faces (retail): invisible from inside / behind each face')
        rows.append({'id': p['id'], 'track': track, 'kind': 'piece', 'category': c, 'category_confidence': cc,
                     'class_measured': p['class'], 'textures': p['textures'], 'triangles': p['triangles'],
                     'render': 'opaque only (cut-out / blended parts of the same building are NOT in the piece)',
                     'far_lod': 'none in a copy (the authored build decimates it); retail LOD of the piece is not identified',
                     'collision': 'not copied from retail; copy: from its faces (keep) or none', 'warnings': warn,
                     'extraction': 'connected opaque render triangles (wb_rta_objects, 2 cm grid)', **f})
    for grp, kind in (('instance_models', 'static mesh (instance model)'), ('prop_types', 'prop (smashable prop type)')):
        for m in cat[grp]:
            rows.append({'id': m['id'], 'track': track, 'kind': kind, 'category': kind, 'category_confidence': 0.9,
                         'texture': m.get('texture'), 'render': m.get('render', 'opaque'), 'size_m': m.get('size_m'),
                         'placements': m.get('placements'),
                         'collision': 'instance models: none in retail draws (collision is in the unit) - copy: keep / none'
                                      if grp == 'instance_models' else 'props: the game handles them as smashables; a copy is STATIC',
                         'far_lod': 'retail LOD1 / LOD2 records: %s' % (m.get('lods') or 'see catalogue'),
                         'placeable': m.get('render', 'opaque') == 'opaque',
                         'warnings': [] if m.get('render', 'opaque') == 'opaque' else
                         ['cut-out / blended texture: placement refused until cut-out materials are supported'],
                         'extraction': 'fr_propmesh record (verified reader)'})
    a = {'schema': TOOL_VERSION, 'key': key, 'track': track, 'settings': SETTINGS, 'assets': rows,
         'counts': {c: sum(1 for r in rows if r['category'] == c) for c in sorted({r['category'] for r in rows})},
         'note': 'MEASURED classifications with confidence; never verified standalone assets. LOCAL ONLY.',
         'seconds': round(time.time() - t0, 1)}
    with open(out + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(a, f)
    os.replace(out + '.tmp', out)
    return a


# ------------------------------------------------------------------ overrides / favourites
def _ov_path(cfg):
    if cfg.get('rta_overrides'):                     # an explicit file (tests keep their corrections apart)
        return cfg['rta_overrides']
    return os.path.join(cfg.get('state') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state'), 'rta_asset_overrides.json')


def overrides(cfg):
    try:
        return json.load(open(_ov_path(cfg), encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def set_override(cfg, track, aid, front_deg=None, category=None, favourite=None, note=None, clear=False):
    ov = overrides(cfg)
    k = '%s|%s' % (track, aid)
    if clear:
        ov.pop(k, None)
    else:
        e = dict(ov.get(k) or {})
        if front_deg is not None:
            if not (isinstance(front_deg, (int, float)) and -360 <= front_deg <= 360):
                raise ValueError('front_deg: -360..360')
            e['front_deg'] = round(float(front_deg) % 360, 1)
        if category is not None:
            if category not in ('intact building', 'building shell / facade', 'scenery fragment', 'structure', 'exclude'):
                raise ValueError('category: intact building / building shell / facade / scenery fragment / structure / exclude')
            e['category'] = category
        if favourite is not None:
            e['favourite'] = bool(favourite)
        if note is not None:
            e['note'] = str(note)[:300]
        e['time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        ov[k] = e
    p = _ov_path(cfg)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(ov, f, indent=1, sort_keys=True)
    os.replace(p + '.tmp', p)
    return ov.get(k)


def effective(cfg, row):
    """the asset row with the user's override applied (front / category); measured values kept under 'measured'"""
    ov = overrides(cfg).get('%s|%s' % (row['track'], row['id']))
    if not ov:
        return dict(row, override=None)
    r = dict(row, override=ov, measured={'front_deg': row.get('front_deg'), 'category': row.get('category')})
    if 'front_deg' in ov:
        r['front_deg'] = ov['front_deg']
    if 'category' in ov:
        r['category'] = ov['category']
    r['favourite'] = ov.get('favourite', False)
    return r


def search(cfg, tracks=None, category=None, query='', favourites=False, min_confidence=0.0, facing_road=False, limit=200):
    idx = json.load(open(os.path.join(CAT.cat_root(cfg), 'INDEX.json'), encoding='utf-8'))
    out = []
    q = (query or '').lower()
    for r in idx['tracks']:
        if not r.get('ok') or (tracks and r['track'] not in tracks):
            continue
        for a in build(cfg, r['track'])['assets']:
            e = effective(cfg, a)
            if category and e['category'] != category:
                continue
            if favourites and not e.get('favourite'):
                continue
            conf = e.get('front_confidence') if e.get('kind') == 'piece' else e.get('category_confidence', 0)
            if 'front_deg' in (e.get('override') or {}):
                conf = 1.0                                   # a front set by hand is trusted
            if (conf or 0) < min_confidence:
                continue
            if facing_road and not ((e.get('original_road') or {}).get('front_vs_road_deg', 999) <= 45):
                continue
            tx = ' '.join(list(e.get('textures') or []) + [e.get('texture') or ''])
            if q and q not in tx.lower() and q not in e['id'].lower() and q not in e['category']:
                continue
            out.append(e)
            if len(out) >= limit:
                return out
    return out
