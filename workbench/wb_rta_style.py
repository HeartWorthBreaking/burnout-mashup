r"""wb_rta_style - style presets for retail-style track authoring (Workbench 0.33 retail-style authoring, 2026-11-01).

A preset = a palette of assets from ONE retail track of the user's own game data (referenced by track id + texture name / model
id, never bytes) + the MEASURED numbers it was derived from (wb_rta_measure) + ARTISTIC defaults kept in a separate section.
Presets are derived, not hand-picked: every palette choice names the measurement that selected it. A preset never claims that
the assets make a coherent style by themselves; 'kind' is only given where the measured composition supports it:
  city         tall vertical surfaces (facades / cliffs) >= 20 % of the surface within 60 m of the route
  countryside  tall vertical surfaces < 6 % and ground / verge / foliage >= 45 %
  mixed        anything else
'waterfront' is a NAME from the Workbench retail guide (US/C1_V1 = US Waterfront), not a measured property: water itself is
neither measured nor generated.

Stored presets: <Workbench>\data\rta_styles\*.json (shipped examples: references + numbers only) and <state>\rta_styles\*.json
(the user's own / edited). Built-in preset files hold no retail bytes, but applying them needs the referenced game data.
"""
import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = 'bm-rta-style/1'
BUILTIN = os.path.join(HERE, 'data', 'rta_styles')

# Builder restrictions that cap what a preset can ask for (facts from the te2 work; repeated in every preset)
BUILDER_LIMITS = [
    'route road width: 14 m default - an 18 m road (2 x 6 m lanes + 2 x 3 m edges) failed the kit walls-hold check on the test '
    'loop (earlier retail-look tests): wider retail carriageways are NOT reproduced',
    'route banking <= ~0.3 deg (kit gate V2); start stretch level (grid written level)',
    'closed circuits only (trackbuild); one AI route with 5 cyclic lanes; junctions / side roads are geometry only',
    'materials opaque only: retail cut-out foliage / fences / signs cannot be used; trees are generated low-poly opaque shapes',
    'scenery = geometry copies (no prop / instance writer): every lamp / building / tree counts in the unit slots '
    '(game defaults mesh 0x28000, LOD 0x18000 incl. full collision; capacity auto declares more, up to the host ceiling)',
    '83 material rows per track; sky / fog / lighting = the donor track\'s enviro.dat unchanged',
]

DEFAULTS = {  # ARTISTIC defaults (not measured); the generator's own sensible values
    'road_width_m': 14.0, 'edge_width_m': 3.0, 'verge_out_m': 10.0, 'verge_in_m': 20.0, 'wall_height_m': 1.5,
    'band_m': 45.0,       # = the outer verge width (ground for scenery), <= 60 m (race layout limit)
    'building_density': 1.0, 'building_height_scale': 0.35, 'building_depth_m': [10.0, 18.0],
    'building_width_m': [12.0, 26.0], 'building_gap_m': [4.0, 14.0], 'doorways': True, 'tree_density': 1.0,
    'lamp_density': 1.0, 'variation': 0.25, 'seed': 1, 'curve_clearance_m': 6.0,
}


class StyleError(Exception):
    pass


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def classify(comp):
    b = comp.get('tall vertical surface (facade / cliff)', 0.0)
    nat = comp.get('ground / terrain', 0.0) + comp.get('pavement / verge', 0.0) + \
        comp.get('cut-out / blended card (foliage, fence, sign: shown with transparency)', 0.0)
    if b >= 0.20:
        return 'city', ('tall vertical surfaces %.0f %% of the surface within 60 m (>= 20 %%); NOTE: facades and cliffs / rock '
                        'walls measure alike - check the source track before calling it a city' % (100 * b))
    if b < 0.06 and nat >= 0.45:
        return 'countryside', 'tall vertical surfaces %.0f %% (< 6 %%), ground / verge / foliage %.0f %% (>= 45 %%)' % (100 * b, 100 * nat)
    return 'mixed', 'tall vertical surfaces %.0f %%, ground / verge / foliage %.0f %%' % (100 * b, 100 * nat)


def _tex(cat, name):
    return next((t for t in cat['textures'] if t['texture'] == name), None)


def derive(cat, meas, pid=None, title=None, name_note=None):
    """a preset from one track's catalogue + measurement. Raises StyleError when a required palette role is missing."""
    opaque = lambda t: t and t['render'] == ['opaque']  # noqa: E731
    rep = meas.get('texture_repeats') or {}
    roads = [t for t in cat['textures'] if t['role'] == 'road surface' and opaque(t)]
    roads.sort(key=lambda t: -t['area_m2'])
    pal, why = {}, {}
    # road: the largest road-surface texture with a measured repeat
    road = next((t for t in roads if t['texture'] in rep), None)
    if not road:
        raise StyleError('%s: no opaque road-surface texture with a measured repeat' % cat['track'])
    r = rep[road['texture']]
    along = r['along_axis']
    across = 'v' if along == 'u' else 'u'
    pal['road'] = {'texture': road['texture'], 'along_m': r['%s_m_per_repeat' % along]['median'],
                   'across_m': r['%s_m_per_repeat' % across]['median']}
    why['road'] = 'largest opaque road-surface area (%.0f m2) with a measured repeat' % road['area_m2']
    # edge strip: a road-surface texture whose across repeat is about half the road's (retail edge strips: 3 m vs 6 m lanes)
    half = pal['road']['across_m'] / 2.0
    edge = None
    for t in roads[1:]:
        q = rep.get(t['texture'])
        if not q:
            continue
        ax = 'v' if q['along_axis'] == 'u' else 'u'
        w = q['%s_m_per_repeat' % ax]['median']
        if abs(w - half) <= 0.6:
            edge = (t, q, w)
            break
    if edge:
        pal['edge'] = {'texture': edge[0]['texture'], 'across_m': edge[2],
                       'along_m': edge[1]['%s_m_per_repeat' % edge[1]['along_axis']]['median']}
        why['edge'] = 'road-surface texture with an across repeat of %.2f m (about half the lane repeat)' % edge[2]
    else:
        why['edge'] = 'none measured: the edge strip uses the road texture'

    def pick(role, n=1, exclude=()):
        rows = [t for t in cat['textures'] if t['role'] == role and opaque(t) and t['texture'] not in exclude]
        rows.sort(key=lambda t: -t['area_m2'])
        return rows[:n]
    w = pick('barrier / wall', 2)
    if w:
        pal['wall'] = {'texture': w[0]['texture']}
        pal['wallback'] = {'texture': (w[1] if len(w) > 1 else w[0])['texture']}
        why['wall'] = 'largest opaque barrier / wall areas'
    v = pick('pavement / verge', 4)
    if pal.get('road') and v:
        v = [t for t in v if t['texture'] not in (pal['road']['texture'], (pal.get('edge') or {}).get('texture'))] or v
    if v:
        pal['verge'] = {'texture': v[0]['texture']}
        why['verge'] = 'largest opaque pavement / verge area'
    g = pick('ground / terrain', 1) or v[1:2] or v[:1]
    if g:
        pal['ground'] = {'texture': g[0]['texture']}
        why['ground'] = 'largest opaque ground / terrain area (else the second verge texture)'
    f = pick('tall vertical surface (facade / cliff)', 4)
    if f:
        pal['facades'] = []
        for t in f:
            q = rep.get(t['texture']) or {}
            um, vm = (q.get('u_m_per_repeat') or {}).get('median'), (q.get('v_m_per_repeat') or {}).get('median')
            r = round(min(40.0, max(1.0, (um + vm) / 2)), 2) if um and vm else None
            pal['facades'].append({'texture': t['texture'], 'size': t['size'], 'repeat_m': r})
        why['facades'] = ('the 4 largest opaque tall-vertical areas; repeat_m = mean of the measured u / v metres per repeat on '
                          'vertical faces (None = not measured: 6 m used)')
    # foliage for generated trees: the greenest opaque ground-like texture by its MEASURED mean colour (thumbnail preview)
    try:
        import wb_rta_thumbs as TH
        cands = [t for t in cat['textures'] if opaque(t) and t['role'] in ('pavement / verge', 'ground / terrain', 'road surface')
                 and t['area_m2'] > 500][:40]
        best = None
        for t in cands:
            c = TH._mean_colour(cat, t['texture'])
            if c and c[1] > 1.05 * c[0] and c[1] > 1.2 * c[2]:      # green must dominate red and blue
                g = c[1] - (c[0] + c[2]) / 2
                if best is None or g > best[0]:
                    best = (g, t['texture'], [round(x, 3) for x in c])
        if best and best[0] > 0.02:
            pal['foliage'] = {'texture': best[1], 'mean_rgb': best[2]}
            why['foliage'] = 'greenest opaque ground-like texture by measured mean colour (g - (r + b) / 2 = %.3f)' % best[0]
        else:
            if pal.get('ground'):
                pal['foliage'] = {'texture': pal['ground']['texture']}
            why['foliage'] = 'no clearly green opaque ground texture measured: trees use the ground texture'
    except Exception as e:  # noqa: BLE001
        why['foliage'] = 'colour not measured (%s)' % e
    rf = pick('roof / raised surface', 1)
    if rf:
        pal['roof'] = {'texture': rf[0]['texture']}
    for k in ('wall', 'verge'):
        if k not in pal:
            raise StyleError('%s: no opaque %s texture measured' % (cat['track'], k))
    lamps = [m for m in meas.get('roadside_models') or [] if m['render'] == 'opaque' and m['size_m'][1] >= 4.5
             and min(m['size_m'][0], m['size_m'][2]) <= 1.6 and m['per_km'] >= 2.0 and (m['spacing_m'].get('median') or 0) >= 8]
    lamps.sort(key=lambda m: -m['per_km'])
    pal['posts'] = [{'model': m['id'], 'texture': m['texture'], 'spacing_m': m['spacing_m']['median'],
                     'setback_m': m['setback_m']['median'], 'left_fraction': m['left_fraction'], 'per_km': m['per_km'],
                     'size_m': m['size_m']} for m in lamps[:2]]
    why['posts'] = ('opaque tall thin roadside instance models (>= 4.5 m, <= 1.6 m thick) by placements per km; WHAT they are '
                    '(lamp, tram post, pylon) is not decoded - check the thumbnail')
    trees = [m for m in meas.get('roadside_models') or [] if 'tree' in m['role']]
    tree_km = sum(m['per_km'] for m in trees)
    tree_setback = None
    if trees:
        tot = sum(m['placements'] for m in trees)
        tree_setback = round(sum(m['setback_m']['median'] * m['placements'] for m in trees) / tot, 1)
    kind, kind_why = classify(meas.get('composition_within_60m') or {})
    b = meas.get('buildings') or {}
    measured = {
        'road_texture_repeat_m': {'along': pal['road']['along_m'], 'across': pal['road']['across_m']},
        'edge_strip_repeat_m': pal.get('edge'),
        'paved_width_per_20m_m': (meas.get('paved_width_m') or {}).get('width_per_20m_section'),
        'ai_lane_gap_profile_m': [x.get('median') for x in (meas.get('lanes') or {}).get('lateral_gap_profile_m') or []],
        'barrier_distance_m': (meas.get('barriers') or {}).get('distance_m_area_weighted'),
        'pavement_distance_m': (meas.get('pavements') or {}).get('distance_m_area_weighted'),
        'building_setback_m': {'p10': b.get('setback_m_p10_area_weighted'), 'median': b.get('setback_m_median_area_weighted')},
        'building_height_p90_m': b.get('height_m_p90_area_weighted'),
        'post_spacing_m': [p['spacing_m'] for p in pal['posts']], 'post_setback_m': [p['setback_m'] for p in pal['posts']],
        'tree_models_per_km': round(tree_km, 2), 'tree_setback_m': tree_setback,
        'composition_within_60m': meas.get('composition_within_60m'),
    }
    p = {'schema': SCHEMA, 'id': pid or 'style_%s' % cat['track'].replace('/', '_').lower(),
         'title': title or 'Style measured on %s' % cat['track'], 'kind': kind, 'kind_evidence': kind_why,
         'name_note': name_note,
         'source': {'track': cat['track'], 'catalogue_key': cat['cache_key'][:12],
                    'source_sha256': {n: v['sha256'] for n, v in cat['source']['files'].items()}},
         'palette': pal, 'palette_why': why, 'measured': measured, 'defaults': dict(DEFAULTS), 'builder_limits': BUILDER_LIMITS,
         'trees': {'how': 'generated low-poly OPAQUE trees (retail trees are cut-out cards: not copyable)', 'per_km_measured': tree_km,
                   'setback_m_measured': tree_setback, 'approximation': True},
         'local_only_when_applied': True}
    p['measured_sha256'] = _sha(measured)
    return p


def validate(p):
    probs = []
    if not isinstance(p, dict) or p.get('schema') != SCHEMA:
        return ['not a %s preset' % SCHEMA]
    if not re.match(r'^[a-z0-9_]{1,48}$', str(p.get('id'))):
        probs.append('id: 1..48 of a-z 0-9 _')
    pal = p.get('palette') or {}
    for k in ('road', 'wall', 'verge'):
        e = pal.get(k) or {}
        if not (e.get('texture') or e.get('material')):
            probs.append('palette.%s: texture (retail, from your game data) or material (original, in the project) missing' % k)
    if p.get('original_only'):
        for k, e in pal.items():
            for x in (e if isinstance(e, list) else [e]):
                if x.get('texture') or x.get('model'):
                    probs.append('original_only preset references a retail asset in palette.%s' % k)
    d = p.get('defaults') or {}
    rng = {'road_width_m': (8, 30), 'edge_width_m': (0.5, 6), 'verge_out_m': (2, 40), 'verge_in_m': (2, 40), 'band_m': (10, 60),
           'building_density': (0, 3), 'tree_density': (0, 3), 'lamp_density': (0, 3), 'variation': (0, 1),
           'building_height_scale': (0.05, 1.5), 'curve_clearance_m': (0, 40)}
    for k, (lo, hi) in rng.items():
        v = d.get(k)
        if v is not None and not (isinstance(v, (int, float)) and lo <= v <= hi):
            probs.append('defaults.%s must be %s..%s' % (k, lo, hi))
    if 'measured_sha256' in p and p['measured_sha256'] != _sha(p.get('measured')):
        probs.append('measured values were edited: measurements are read-only in a preset (change defaults instead, or re-derive)')
    return probs


def dirs(cfg):
    return [BUILTIN, os.path.join(cfg.get('state') or os.path.join(HERE, 'state'), 'rta_styles')]


def list_presets(cfg):
    out = []
    for d in dirs(cfg):
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            if n.endswith('.json'):
                try:
                    p = json.load(open(os.path.join(d, n), encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                out.append({'id': p.get('id'), 'title': p.get('title'), 'kind': p.get('kind'), 'track': (p.get('source') or {}).get('track'),
                            'builtin': d == BUILTIN, 'problems': validate(p), 'file': os.path.join(d, n)})
    return out


def load(cfg, pid):
    for d in reversed(dirs(cfg)):                    # the user's copy wins over the shipped example of the same id
        p = os.path.join(d, '%s.json' % pid)
        if os.path.isfile(p):
            s = json.load(open(p, encoding='utf-8'))
            pr = validate(s)
            if pr:
                raise StyleError('style %s: %s' % (pid, '; '.join(pr)))
            return s
    raise StyleError('style %s not found' % pid)


def save_user(cfg, p):
    pr = validate(p)
    if pr:
        raise StyleError('; '.join(pr))
    d = dirs(cfg)[1]
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, '%s.json' % p['id'])
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(p, f, indent=1)
    os.replace(path + '.tmp', path)
    return path


def check_source(cfg, p):
    """the preset's source track must exist in the CURRENT catalogue with the same source hashes (else 'refresh / re-derive')"""
    import wb_rta_catalog as C
    if not (p.get('source') or {}).get('track'):
        return None, None                            # original-only preset: nothing from game data to check
    try:
        cat = C.load(cfg, p['source']['track'])
    except C.CatalogError as e:
        return None, str(e)
    if {n: v['sha256'] for n, v in cat['source']['files'].items()} != p['source']['source_sha256']:
        return cat, ('your game data for %s differs from the data this preset was measured on (different files / version): '
                     're-derive the preset from your data' % p['source']['track'])
    return cat, None
