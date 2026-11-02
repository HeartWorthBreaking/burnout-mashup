r"""wb_rta_measure - MEASURED style facts of a retail track (Workbench 0.33 retail-style authoring, 2026-11-01). LOCAL ONLY output.

Inputs: the track's asset catalogue (wb_rta_catalog) and wb_retail's decoded view cache (mesh.bin, route lanes). Read only.
Every number carries how it was measured; nothing here is an artistic default (those live in the style presets, separately).

Measurements
- lanes: the cyclic main AI lanes (S4, ct2_route lane flag 1) are sampled every 20 m along lane 0; the other lanes' lateral
  offsets give the lane spacing (median gap) and the lane-line spread. Road width estimate = spread + one spacing. These are AI
  lane lines, not painted lanes.
- paved width: lateral extent (p2 .. p98, about the lanes' middle) of the triangles of textures measured as 'road surface'.
- texture repeats: per triangle, plan-space gradients of u and v (solved from its corners); metres per repeat = 1 / |gradient|;
  the axis whose gradient is most parallel to the route tangent is 'along' (earlier retail-look tests method, generalised).
- roadside: per instance model with >= 8 placements: setback from the nearest main lane line, spacing along it, side split.
- buildings / barriers / pavements: area-weighted distance from the route of the textures of that measured role; heights.
- composition: area share per role within 60 m of the route (what the roadside is MADE of; used to support / refuse a style).
- environment: fr_enviro summary (sun / light colours CODE-traced; fog HYP).
"""
import json
import math
import os
import struct

import wb_rta_geo as G


def _lanes(view):
    lanes = [ln for ln in (view.get('route') or {}).get('lanes') or [] if ln.get('flags') == 1 and len(ln.get('centre') or []) >= 4]
    return [ln['centre'] for ln in lanes]


def lane_profile(view, step=20.0):
    L = _lanes(view)
    if len(L) < 1:
        return {'status': 'no cyclic main lanes (point-to-point track or undecoded): lane widths not measured'}, None, None
    base = G.RouteIndex([L[0]], [True])
    others = [G.RouteIndex([ln], [True]) for ln in L[1:]]
    profiles, spreads, mids = [], [], {}
    last = -1e9
    for smp in base.samples:
        if smp[3] - last < step:
            continue
        last = smp[3]
        x, z, tx, tz = smp[0], smp[2], smp[5], smp[6]
        lats = [0.0]
        for o in others:
            d, p = o.nearest(x, z, 80.0)
            if p is None:
                continue
            lats.append((p[0] - x) * (-tz) + (p[2] - z) * tx)
        lats.sort()
        if len(lats) == len(L):
            profiles.append([lats[i + 1] - lats[i] for i in range(len(lats) - 1)])
            spreads.append(lats[-1] - lats[0])
        mids[round(smp[3], 1)] = (lats[0] + lats[-1]) / 2
    gap_profile = [G.stats([pr[i] for pr in profiles], 2) for i in range(len(L) - 1)] if profiles else []
    out = {'main_lanes': len(L), 'samples': len(profiles),
           'lateral_gap_profile_m': gap_profile,
           'lane_line_spread_m': G.stats(spreads, 2),
           'meaning': 'UNKNOWN which main lanes are driving lines and which are limits: reported as measured (sorted '
                      'left to right, gap i = lane i+1 minus lane i)',
           'method': 'AI main-lane lines (S4, flag 1) sampled every %.0f m along lane 0' % step}
    return out, base, mids


def _mid_of(mids, s):
    if not mids:
        return 0.0
    k = min(mids, key=lambda m: abs(m - s))
    return mids[k]


def _paved(paved):
    by = {}
    for b, lat in paved:
        by.setdefault(b, []).append(lat)
    w = [max(v) - min(v) for v in by.values() if len(v) >= 6]
    if len(w) < 10:
        return {'status': 'not measured (too few road-surface samples near lane 0)'}
    return {'width_per_20m_section': G.stats(w, 2), 'sections': len(w),
            'method': "per 20 m of lane 0: lateral extent of sampled 'road surface' triangle centroids (the median is the "
                      "typical carriageway incl. its lanes; junction mouths / slip roads raise p90)"}


def measure(cat, view, blob):
    lanes, base, mids = lane_profile(view)
    lines, cyc = G.route_lines(view)
    R = G.RouteIndex(lines, cyc) if lines else None
    roles = {t['texture']: t['role'] for t in cat['textures']}
    paved = []
    rep = {}
    comp = {}
    for e in view['mesh']:
        nm = e['texture_name']
        role = roles.get(nm, 'unclassified')
        nv, ni = e['vertices'], e['indices']
        P = struct.unpack_from('<%df' % (3 * nv), blob, e['off_pos'])
        UV = struct.unpack_from('<%df' % (2 * nv), blob, e['off_uv'])
        idx = struct.unpack_from('<%dI' % ni, blob, e['off_idx'])
        step = max(1, (ni // 3) // 600)
        for k in range(0, ni - 2, 3 * step):
            a, b, c = idx[k], idx[k + 1], idx[k + 2]
            pa, pb, pc = P[3 * a:3 * a + 3], P[3 * b:3 * b + 3], P[3 * c:3 * c + 3]
            ar, n, cen = G.tri_geo(pa, pb, pc)
            if ar < 0.05 or not R:
                continue
            pr = R.project(*cen, max_r=60.0)
            if pr:
                comp[role] = comp.get(role, 0.0) + ar * step
            if role == 'road surface' and base is not None:
                bp = base.project(*cen, max_r=40.0)
                if bp:
                    paved.append((int(bp['s'] // 20), bp['lateral'] - _mid_of(mids, round(bp['s'], 1))))
            vert_role = role in ('barrier / wall', 'tall vertical surface (facade / cliff)')
            if role in ('road surface', 'pavement / verge', 'barrier / wall', 'tall vertical surface (facade / cliff)') and pr and (
                    abs(n[1]) <= 0.3 if vert_role else abs(n[1]) >= 0.85):
                # plan gradients of u, v over the triangle (te2 method); vertical walls use the (along, height) plane
                ua, va = UV[2 * a:2 * a + 2], UV[2 * b:2 * b + 2]
                ub, vb2 = UV[2 * c:2 * c + 2], None
                del vb2
                if vert_role:                                   # the face's own (horizontal, height) plane
                    hl = math.hypot(n[0], n[2]) or 1.0
                    hx, hz = -n[2] / hl, n[0] / hl
                    h = lambda p, hx=hx, hz=hz: (p[0] * hx + p[2] * hz, p[1])   # noqa: E731
                else:
                    h = lambda p: (p[0], p[2])                            # noqa: E731
                smp = R.nearest(cen[0], cen[2], 60.0)[1]
                pr_t = (smp[5], smp[6])
                q = [h(pa), h(pb), h(pc)]
                d1 = (q[1][0] - q[0][0], q[1][1] - q[0][1])
                d2 = (q[2][0] - q[0][0], q[2][1] - q[0][1])
                det = d1[0] * d2[1] - d1[1] * d2[0]
                if abs(det) < 1e-6:
                    continue
                grads = []
                for comp_i in (0, 1):
                    f0, f1, f2 = ua[comp_i], va[comp_i], ub[comp_i]
                    e1, e2 = f1 - f0, f2 - f0
                    gx = (e1 * d2[1] - e2 * d1[1]) / det
                    gz = (e2 * d1[0] - e1 * d2[0]) / det
                    grads.append((gx, gz))
                r = rep.setdefault(nm, {'role': role, 'u_m': [], 'v_m': [], 'u_along': 0, 'v_along': 0})
                for nmk, (gx, gz) in zip(('u', 'v'), grads):
                    gl = math.hypot(gx, gz)
                    if gl > 1e-6:
                        r[nmk + '_m'].append(1.0 / gl)
                        if not vert_role:
                            along = abs(gx * pr_t[0] + gz * pr_t[1]) / gl
                        else:
                            along = abs(gx) / gl
                        if along > 0.7:
                            r[nmk + '_along'] += 1
    repeats = {}
    for nm, r in rep.items():
        if len(r['u_m']) < 10:
            continue
        repeats[nm] = {'role': r['role'], 'u_m_per_repeat': G.stats(r['u_m'], 2), 'v_m_per_repeat': G.stats(r['v_m'], 2),
                       'along_axis': 'u' if r['u_along'] >= r['v_along'] else 'v',
                       'tight_axis': 'u' if ((G.pct(r['u_m'], 90) or 0) - (G.pct(r['u_m'], 10) or 0)) <=
                                            ((G.pct(r['v_m'], 90) or 0) - (G.pct(r['v_m'], 10) or 0)) else 'v'}
    tot = sum(comp.values()) or 1.0
    composition = {k: round(v / tot, 3) for k, v in sorted(comp.items(), key=lambda kv: -kv[1])}

    def by_role(role):
        rows = [t for t in cat['textures'] if t['role'] == role and t['route_distance_m'].get('n')]
        rows.sort(key=lambda t: -t['area_m2'])
        return rows

    def wavg(rows, key, field):
        num = sum(t['area_m2'] * (t[key].get(field) or 0) for t in rows)
        den = sum(t['area_m2'] for t in rows) or 1.0
        return round(num / den, 2)
    bld = by_role('tall vertical surface (facade / cliff)')
    bar = by_role('barrier / wall')
    pav = by_role('pavement / verge')
    road = by_role('road surface')
    roadside = []
    for m in cat['instance_models']:
        if (m.get('placements') or 0) >= 8 and m['setback_m'].get('n'):
            roadside.append({'id': m['id'], 'texture': m['texture'], 'role': m['role'], 'render': m['render'],
                             'size_m': m['size_m'], 'placements': m['placements'], 'setback_m': m['setback_m'],
                             'spacing_m': m['spacing_m'], 'left_fraction': m['left_fraction'],
                             'per_km': round(1000.0 * m['placements'] / max(1.0, max(cat['route']['lengths_m'] or [1.0])), 2)})
    roadside.sort(key=lambda r: -r['placements'])
    return {
        'track': cat['track'], 'catalogue_key': cat['cache_key'][:12],
        'lanes': lanes,
        'paved_width_m': _paved(paved),
        'texture_repeats': repeats,
        'roads': [{'texture': t['texture'], 'area_m2': t['area_m2']} for t in road[:6]],
        'pavements': {'textures': [t['texture'] for t in pav[:5]], 'distance_m_area_weighted': wavg(pav, 'route_distance_m', 'median')
                      if pav else None},
        'barriers': {'textures': [t['texture'] for t in bar[:5]], 'distance_m_area_weighted': wavg(bar, 'route_distance_m', 'median')
                     if bar else None, 'height_m_area_weighted': wavg(bar, 'height_above_route_m', 'p90') if bar else None},
        'buildings': {'textures': [t['texture'] for t in bld[:8]],
                      'setback_m_p10_area_weighted': wavg(bld, 'route_distance_m', 'p10') if bld else None,
                      'setback_m_median_area_weighted': wavg(bld, 'route_distance_m', 'median') if bld else None,
                      'height_m_p90_area_weighted': wavg(bld, 'height_above_route_m', 'p90') if bld else None,
                      'facade_area_m2': round(sum(t['area_m2'] for t in bld), 0)},
        'roadside_models': roadside[:20],
        'composition_within_60m': composition,
        'environment': (cat.get('environment') or {}).get('summary'),
        'evidence': 'MEASURED on the user\'s own game data (wb_rta_measure); roles = wb_rta_catalog geometry classes',
    }


def measure_track(cfg, track):
    import wb_rta_catalog as C
    cat = C.load(cfg, track)
    view = json.load(open(os.path.join(cat['view_cache'], 'view.json'), encoding='utf-8'))
    blob = open(os.path.join(cat['view_cache'], 'mesh.bin'), 'rb').read()
    m = measure(cat, view, blob)
    p = os.path.join(C.cat_root(cfg), '%s-%s' % (track.replace('/', '_'), cat['cache_key'][:12]), 'measure.json')
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(m, f, indent=1)
    os.replace(p + '.tmp', p)
    return m


if __name__ == '__main__':
    import sys
    import wb_core as core
    cfg = core.load_config()
    for t in sys.argv[1:]:
        m = measure_track(cfg, t)
        print(json.dumps({k: m[k] for k in ('track', 'lanes', 'paved_width_m', 'buildings', 'composition_within_60m')}, indent=1)[:3000])
