r"""wb_rta_design - GUIDED ENVIRONMENT DESIGNER (Workbench 0.33 retail-style authoring, 2026-11-02). A mixin of wb_trackedit.TrackSource.

Route -> neighbourhood SEGMENTS (each a style preset, with controlled transitions) -> a believable, editable environment:
  road style      one preset decides road / edge / wall / verge materials of the whole route (race-layout materials are global)
  segments        [{from, to (fractions of the loop), style, landmark, open_space, density}]; transition_m blends neighbouring
                  segments slot by slot (deterministic, seeded) - no hard seams, no random sprinkling
  variation       smooth 1-D value noise along the route modulates building gaps / tree density; open spaces leave gaps
  buildings       generated (facades of the segment's style) or retail pieces (asset library: measured / overridden front turned
                  to the road; low-confidence or open-shell pieces only when allowed); landmark = one taller building per segment
  posts           the segment style's measured post models (two types: one per side) placed in that segment only, arm to the road
  signs           sign-shaped models of the segment's track (measured: 3..9 m tall, <= 3 m wide, <= 1.2 m thick, opaque) on the
                  outer side 40..70 m BEFORE bends of radius < 150 m and at segment starts
  trees           generated low-poly (opaque); denser in open spaces
  background      tall generated silhouettes at the far edge of the ground band (big: kept by the far LOD's drop_below rule)
  junction        a VISUAL side-road stub beyond the closed wall (geometry only: no wall gap, no AI / traffic link)
  slopes          ground spread > 0.5 m under a footprint: a plinth (foundation block) when plinths are on, else refused
Every refusal carries a REMEDY. A QUICK preview (no geometry, no kit dry run; stations approximated from the control points)
returns markers / footprints / counts in about a second; the full preview runs the editor's operations on a clone (job) and
applies as ONE undo step. Each category is its own block (rta_d_<category>) -> per-category regenerate / lock.
"""
import hashlib
import json
import math
import random

import wb_rta_gen as GEN
import wb_rta_style as STY

T = GEN.T
CATS = ('buildings', 'posts', 'signs', 'trees', 'background', 'junction')
REMEDY = {
    'road clearance': 'larger setback for this segment, or a wider verge',
    'inside of a curve': 'kept clear for the sightline: lower curve_clearance_m or accept fewer buildings on inner sides',
    'outside the generated ground': 'raise band_m (outer verge, <= 60 m) or reduce building depth',
    'inside an exclusion area': 'remove or shrink the exclusion area',
    'overlaps': 'raise building_gap_m or lower density',
    'no collision floor': 'the spot has no ground: keep scenery on the verges, or add terrain there first',
    'ground under the corners differs': 'turn plinths on (foundation block), flatten the terrain, or move the building',
    'no ground under the whole crown': 'trees need ground under the crown: smaller radius or further from the verge edge',
    'not opaque': 'cut-out / blended models need cut-out material support (not available: see the capability matrix)',
    'no sign-shaped model': 'this track has no measured sign-shaped model: add signs from another track (posts list) or skip',
}


def remedy(why):
    for k, v in REMEDY.items():
        if k in why:
            return v
    return 'see the reason; change the setting it names'


def noise1d(s, seed, wavelength=120.0):
    """smooth value noise in [0, 1] along the route (cosine-interpolated lattice every `wavelength` m)"""
    i = math.floor(s / wavelength)
    f = s / wavelength - i
    a = random.Random('n%d|%d' % (seed, i)).random()
    b = random.Random('n%d|%d' % (seed, i + 1)).random()
    t = (1 - math.cos(math.pi * f)) / 2
    return a * (1 - t) + b * t


def approx_stations(points, step=2.5, offsets=(-52.6, -7.6, -7.0, 7.0, 7.6, 15.6)):
    """QUICK preview stations from the closed control polyline (no race layout): positions, tangents, approximate offsets"""
    pts = [p for p in points]
    out = []
    n = len(pts)
    for k in range(n):
        a, b = pts[k], pts[(k + 1) % n]
        dx, dz = b[0] - a[0], b[2] - a[2]
        L = math.hypot(dx, dz)
        if L < 1e-6:
            continue
        m = max(1, int(L / step))
        for i in range(m):
            f = i / m
            out.append({'p': [a[0] + dx * f, a[1] + (b[1] - a[1]) * f, a[2] + dz * f], 't': [dx / L, dz / L], 'offsets': list(offsets)})
    return out


def estimate_verge(D):
    """the outer verge the race layout is expected to accept: the ladder value that stays inside the tightest curve radius of
    the control polyline (the layout refuses a strip edge folding over at radius < offset). Approximate."""
    P = D['points']
    n = len(P)
    rmin = 1e9
    for k in range(n):                              # radius of the circle through three consecutive control points
        a, b, c = P[k - 1], P[k], P[(k + 1) % n]
        ab, bc, ca = (math.hypot(b[0] - a[0], b[2] - a[2]), math.hypot(c[0] - b[0], c[2] - b[2]), math.hypot(a[0] - c[0], a[2] - c[2]))
        area2 = abs((b[0] - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (b[2] - a[2]))
        if area2 > 1e-6:
            rmin = min(rmin, ab * bc * ca / (2 * area2))
    half = D['road_width_m'] / 2 + 0.6
    for vo in (min(60.0, D['band_m']), 35.0, 25.0, 15.0):
        if vo <= min(60.0, D['band_m']) and half + vo < rmin:
            return vo
    return 15.0


def layout_stations(D):
    """the race layout's OWN geometry (wb_construct: Catmull-Rom sample, tangents, the same fold / self-crossing rules and the
    same verge step-down ladder as the full run) -> (stations, outer verge, inner verge, refused rungs). Level routes only; a
    sloped route uses the control-polyline approximation."""
    import wb_construct as wc
    P = [list(p) for p in D['points']]
    y0 = P[0][1]
    hw, t = D['road_width_m'] / 2.0, 0.6
    _S, L = wc.sample(P, True, step=2.0)
    spu = 3 * max(1, int(round(L / (17 * 2.0 * 3))))
    n = 17 * spu
    S, L = wc.sample(P, True, count=n)
    S = [[q[0], y0, q[2]] for q in S]
    T = wc.tangents(S, True)
    refused = []
    vo0 = min(60.0, D['band_m'])
    for vo, vi in ((vo0, D['verge_in_m']), (vo0, 8.0), (min(vo0, 35.0), 8.0), (min(vo0, 25.0), 8.0), (15.0, 8.0)):
        bad = None
        for o in (-(hw + t + vo), hw + t + vi):
            for i in range(n):
                a, b = wc.offset_pt(S[i], T[i], o), wc.offset_pt(S[(i + 1) % n], T[(i + 1) % n], o)
                if (b[0] - a[0]) * T[i][0] + (b[2] - a[2]) * T[i][1] <= 0:
                    bad = 'folds at station %d (lateral %.1f m)' % (i, o)
                    break
            if not bad and wc.self_intersections([list(wc.offset_pt(S[i], T[i], o)) for i in range(n)], True):
                bad = 'crosses itself (lateral %.1f m)' % o
            if bad:
                break
        if not bad:
            return wc.stations_from(S, T, hw, t, vo, vi, y0), vo, vi, refused
        refused.append('outer %.0f / inner %.0f m: %s' % (vo, vi, bad))
    return wc.stations_from(S, T, hw, t, 15.0, 8.0, y0), 15.0, 8.0, refused


class Segments:
    """arc-length lookup of neighbourhood segments with seeded transitions"""

    def __init__(self, stations, segs, transition_m, seed):
        self.seg = segs
        self.T = transition_m
        self.seed = seed
        self.cum = [0.0]
        n = len(stations)
        for k in range(1, n + 1):
            a, b = stations[k - 1]['p'], stations[k % n]['p']
            self.cum.append(self.cum[-1] + math.hypot(b[0] - a[0], b[2] - a[2]))
        self.L = self.cum[-1]

    def index(self, s):
        f = (s % self.L) / self.L
        for i, g in enumerate(self.seg):
            if g['from'] <= f < g['to']:
                return i
        return len(self.seg) - 1

    def at(self, s, key=''):
        """segment index for a placement at arc s; inside a transition zone the neighbour is chosen with a ramped probability"""
        i = self.index(s)
        g = self.seg[i]
        a, b = g['from'] * self.L, g['to'] * self.L
        rnd = random.Random('tr%d|%s|%.1f' % (self.seed, key, s)).random()
        if s - a < self.T / 2 and len(self.seg) > 1:
            p = 0.5 - (s - a) / self.T
            if rnd < p:
                return (i - 1) % len(self.seg)
        if b - s < self.T / 2 and len(self.seg) > 1:
            p = 0.5 - (b - s) / self.T
            if rnd < p:
                return (i + 1) % len(self.seg)
        return i

    def station_at(self, s):
        s = s % self.L
        k = next((i for i in range(len(self.cum) - 1) if self.cum[i + 1] >= s), len(self.cum) - 2)
        return k


def plan_design(stations, D, styles, seed, area, log):
    """PURE planning of every category (no geometry): -> dict category -> list of placements (with segment / style)."""
    R = GEN.Route(stations)
    SG = Segments(stations, D['segments'], D['transition_m'], seed)
    L = SG.L
    half = D['road_width_m'] / 2.0
    clear = half + 0.6 + 3.0
    out = {c: [] for c in CATS}
    feet = []
    rnd = random.Random('d%d' % seed)

    def seg_params(i):
        st = styles[D['segments'][i]['style']]
        m = st['measured']
        return st, m

    def ok_spot(corners, cx, cz, what):
        if any(R.dist(x, z) < clear for x, z in corners):
            return 'closer than %.1f m to the route centre line (road clearance)' % clear
        if any(not GEN._in_rect(x, z, area) for x, z in corners):
            return 'outside the generated ground / unit area'
        if any(GEN._in_rect(cx, cz, r) or any(GEN._in_rect(x, z, r) for x, z in corners) for r in D['exclude']):
            return 'inside an exclusion area'
        if what == 'building' and any(not GEN._sep(corners, f, 2.0) for f in feet):
            return 'overlaps another building'
        return None

    def skip(cat, at, why):
        log.append({'part': cat, 'at': [round(at[0], 1), round(at[1], 1)], 'skipped': why, 'remedy': remedy(why)})

    # ---- buildings (+ one landmark per segment that asks for it)
    if D['parts']['buildings']:
        for side in (-1, 1):
            s = rnd.uniform(0, 15)
            while s < L - 10:
                i = SG.at(s, 'b%d' % side)
                g = D['segments'][i]
                st, m = seg_params(i)
                dens = g.get('density', 1.0) * (0.55 + 0.9 * noise1d(s, seed))
                w = rnd.uniform(*st['defaults']['building_width_m'])
                d = rnd.uniform(*st['defaults']['building_depth_m'])
                gap = rnd.uniform(*st['defaults']['building_gap_m']) / max(0.05, dens)
                if g.get('open_space'):
                    s += w + gap + 25
                    continue
                k = SG.station_at(s + w / 2)
                stn = stations[k]
                tx, tz = stn['t']
                nx, nz = -tz, tx
                setb = max(clear, (m.get('building_setback_m') or {}).get('p10') or 12.0)
                ground = abs(stn['offsets'][0 if side < 0 else 5]) - 1.0          # the ground strip on this side (verge edge)
                extra = rnd.uniform(0, st['defaults']['variation'] * 10)
                if setb + extra + d > ground:                                     # fit the depth to the ground first
                    d = max(6.0, ground - setb - extra)
                    if setb + extra + d > ground:
                        extra = max(0.0, ground - setb - d)
                off = setb + d / 2 + extra
                cx, cz = stn['p'][0] + side * nx * off, stn['p'][2] + side * nz * off
                kap = R.curvature(k)
                inner = (kap > 0 and side > 0) or (kap < 0 and side < 0)
                corners = GEN._rect_corners(cx, cz, tx, tz, w, d)
                why = None
                if inner and abs(kap) > 1.0 / 90.0 and off - d / 2 < clear + st['defaults']['curve_clearance_m'] * 2:
                    why = 'inside of a curve (radius %.0f m): kept clear for the sightline' % (1 / abs(kap))
                why = why or ok_spot(corners, cx, cz, 'building')
                if why:
                    skip('buildings', (cx, cz), why)
                else:
                    hp = (m.get('building_height_p90_m') or 12.0) * st['defaults']['building_height_scale']
                    h = max(4.0, min(40.0, hp * rnd.uniform(0.75, 1.25)))
                    out['buildings'].append({'footprint': [[round(x, 3), round(z, 3)] for x, z in corners], 'height': round(h, 2),
                                             'segment': i, 'style': g['style'], 'centre': [round(cx, 2), round(cz, 2)], 'side': side,
                                             'tangent': [tx, tz], 'road_dir': [-side * nx, -side * nz], 'landmark': False})
                    feet.append(corners)
                s += w + gap
        for i, g in enumerate(D['segments']):
            if not g.get('landmark'):
                continue
            st, m = seg_params(i)
            s = (g['from'] + g['to']) / 2 * L
            k = SG.station_at(s)
            stn = stations[k]
            tx, tz = stn['t']
            nx, nz = -tz, tx
            placed = False
            for side in (-1, 1):
                w, d = 22.0, 18.0
                setb = max(clear, (m.get('building_setback_m') or {}).get('p10') or 12.0) + 4
                cx, cz = stn['p'][0] + side * nx * (setb + d / 2), stn['p'][2] + side * nz * (setb + d / 2)
                corners = GEN._rect_corners(cx, cz, tx, tz, w, d)
                feet_wo = [f for f, b in zip(feet, out['buildings']) if not GEN._sep(corners, f, 2.0)]
                if ok_spot(corners, cx, cz, 'landmark'):
                    continue
                # the landmark wins its spot: ordinary buildings it overlaps are dropped (listed, not silent)
                for b in list(out['buildings']):
                    if not GEN._sep(corners, [tuple(p) for p in b['footprint']], 2.0):
                        out['buildings'].remove(b)
                        skip('buildings', b['centre'], 'overlaps another building (the segment landmark)')
                del feet_wo
                hp = (m.get('building_height_p90_m') or 20.0)
                out['buildings'].append({'footprint': [[round(x, 3), round(z, 3)] for x, z in corners], 'height': round(max(18.0, min(60.0, hp * 0.9)), 1),
                                         'segment': i, 'style': g['style'], 'centre': [round(cx, 2), round(cz, 2)], 'side': side,
                                         'tangent': [tx, tz], 'road_dir': [-side * nx, -side * nz], 'landmark': True})
                placed = True
                break
            if not placed:
                skip('buildings', (stn['p'][0], stn['p'][2]), 'landmark: no free spot beside the middle of segment %d (road clearance / ground)' % i)
    # ---- posts (per segment, its own measured types: first outer, second inner)
    if D['parts']['posts']:
        for i, g in enumerate(D['segments']):
            st, m = seg_params(i)
            posts = st['palette'].get('posts') or []
            for pj, pst in enumerate(posts[:2]):
                sides = (-1,) if len(posts) > 1 and pj == 0 else (1,) if len(posts) > 1 else (-1, 1)
                sp = max(15.0, (pst.get('spacing_m') or 40.0) / max(0.1, D['lamp_density']))
                s = g['from'] * L + 8 + pj * sp / 2
                while s < g['to'] * L - 4:
                    k = SG.station_at(s)
                    stn = stations[k]
                    for sd in sides:
                        out['posts'].append({'segment': i, 'track': st['source']['track'], 'model': pst['model'], 'station': k,
                                             'side': sd, 'setback_m': pst.get('setback_m') or 6.0, 's': round(s, 1)})
                    s += sp
    # ---- signs before bends (outer side) and at segment starts
    if D['parts']['signs']:
        bends = []
        last = -1e9
        for k in range(R.n):
            kap = R.curvature(k)
            if abs(kap) > 1.0 / 150.0 and SG.cum[k] - last > 120:
                bends.append((k, kap))
                last = SG.cum[k]
        for k, kap in bends:
            s = SG.cum[k] - rnd.uniform(40, 70)
            i = SG.at(s, 'sign')
            out['signs'].append({'segment': i, 's': round(s % L, 1), 'station': SG.station_at(s), 'side': -1 if kap > 0 else 1,
                                 'reason': 'bend of radius %.0f m ahead' % (1 / abs(kap))})
        for i, g in enumerate(D['segments']):
            out['signs'].append({'segment': i, 's': round(g['from'] * L + 15, 1), 'station': SG.station_at(g['from'] * L + 15),
                                 'side': -1, 'reason': 'segment start'})
    # ---- trees
    if D['parts']['trees']:
        for i, g in enumerate(D['segments']):
            st, m = seg_params(i)
            per_km = (m.get('tree_models_per_km') or 0.0) * D['tree_density'] * (2.0 if g.get('open_space') else 1.0)
            n = int(round((g['to'] - g['from']) * L / 1000.0 * per_km))
            for j in range(min(n, 200)):
                s = (g['from'] + (g['to'] - g['from']) * (j + rnd.random()) / max(1, n)) * L
                if rnd.random() > 0.35 + 0.65 * noise1d(s, seed + 7):
                    continue
                k = SG.station_at(s)
                stn = stations[k]
                tx, tz = stn['t']
                side = 1 if rnd.random() < 0.5 else -1
                setb = max(clear + 2.0, (m.get('tree_setback_m') or 12.0) * rnd.uniform(0.75, 1.25))
                rad = rnd.uniform(1.6, 3.0)
                ground = abs(stn['offsets'][0 if side < 0 else 5])          # the crown must stay over the ground strip
                if setb + rad + 1.0 > ground:
                    setb = ground - rad - 1.0
                if setb < clear + 2.0:
                    skip('trees', (stn['p'][0], stn['p'][2]), 'no ground under the whole crown (ground strip %.1f m on this side)' % ground)
                    continue
                x, z = stn['p'][0] - tz * side * setb, stn['p'][2] + tx * side * setb
                me = GEN._rect_corners(x, z, 1.0, 0.0, 2 * rad, 2 * rad)
                why = ok_spot(me, x, z, 'tree') or (None if all(GEN._sep(me, f, 1.0) for f in feet) else 'overlaps a building')
                if why:
                    skip('trees', (x, z), why)
                    continue
                out['trees'].append({'segment': i, 'position': [round(x, 3), stn['p'][1], round(z, 3)], 'height': round(rnd.uniform(5, 10), 2),
                                     'radius': round(rad, 2), 'sides': 6})
    # ---- background silhouettes at the far edge of the ground band
    if D['parts']['background'] and D['band_m'] >= 35:   # silhouettes need room beyond the buildings
        band = D['band_m']
        for side in (-1,):                              # the outer side (inner side is the infield: usually too narrow)
            s = rnd.uniform(0, 30)
            while s < L:
                i = SG.at(s, 'bg')
                g = D['segments'][i]
                st, m = seg_params(i)
                if (m.get('composition_within_60m') or {}).get('tall vertical surface (facade / cliff)', 0) < 0.06 or g.get('open_space'):
                    s += 80
                    continue
                k = SG.station_at(s)
                stn = stations[k]
                tx, tz = stn['t']
                nx, nz = -tz, tx
                w, d = rnd.uniform(18, 30), rnd.uniform(10, 16)
                off = abs(stn['offsets'][0]) - d / 2 - 2.0
                cx, cz = stn['p'][0] + side * nx * off, stn['p'][2] + side * nz * off
                corners = GEN._rect_corners(cx, cz, tx, tz, w, d)
                why = ok_spot(corners, cx, cz, 'building')
                if why:
                    skip('background', (cx, cz), why)
                else:
                    out['background'].append({'footprint': [[round(x, 3), round(z, 3)] for x, z in corners],
                                              'height': round(rnd.uniform(24, 45), 1), 'segment': i, 'style': g['style'],
                                              'centre': [round(cx, 2), round(cz, 2)], 'side': side, 'tangent': [tx, tz],
                                              'road_dir': [-side * nx, -side * nz], 'landmark': False, 'background': True})
                    feet.append(corners)
                s += w + rnd.uniform(25, 70)
    # ---- visual junction stub
    if D['parts']['junction'] and D.get('junction_at') is not None:
        s = D['junction_at'] * L
        k = SG.station_at(s)
        out['junction'].append({'station': k, 's': round(s, 1), 'length_m': max(6.0, min(40.0, D['band_m'] - 6)), 'width_m': 8.0,
                                'note': 'VISUAL ONLY: the wall stays closed; no AI / traffic link'})
    return out


# ====================================================================================================== editor operations
def _tree_models(cat):
    """tree-shaped CUT-OUT instance models of a track (measured shape + the material's alpha-test flag, never the name): tall
    (4..25 m) and wide (crown >= 2 m), most placed first"""
    rows = [m for m in cat['instance_models'] if m['render'] in ('cutout', 'blend+test') and 4.0 <= m['size_m'][1] <= 25.0
            and max(m['size_m'][0], m['size_m'][2]) >= 2.0 and (m['placements'] or 0) >= 2]
    rows.sort(key=lambda m: -(m['placements'] or 0))
    return rows


def _entry_sha(e):
    import hashlib
    return hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest()[:16]


def _sign_models(cat):
    """sign-shaped opaque instance models of a track (measured shape), most placed first"""
    rows = []
    for m in cat['instance_models']:
        s = m['size_m']
        if m['render'] == 'opaque' and 3.0 <= s[1] <= 9.0 and max(s[0], s[2]) <= 3.0 and min(s[0], s[2]) <= 1.2 and (m['placements'] or 0) >= 4:
            rows.append(m)
    rows.sort(key=lambda m: -(m['placements'] or 0))
    return rows


class DesignMixin:
    def _design_req(self, points=None, road_style=None, segments=None, params=None, parts=None, exclude=None, seed=1,
                    transition_m=40.0, junction_at=None):
        keep = (params or {}).get('route') == 'keep'          # RTA4: dress the project's EXISTING route (branch / bridge fixtures)
        if keep and points is None:
            st0 = self.desc().get('stations') or []
            step_ = max(1, len(st0) // 48)
            points = [list(st0[i]['p']) for i in range(0, len(st0), step_)][:64]
        if not (isinstance(points, list) and 4 <= len(points) <= 64):
            raise GEN.E('route: 4..64 closed control points [[x, y, z], ...]')
        pts = [[float(p[0]), float(p[1] if p[1] is not None else 20.0), float(p[2])] for p in points]
        if not (isinstance(segments, list) and 1 <= len(segments) <= 12):
            raise GEN.E('segments: 1..12 [{from, to, style, landmark?, open_space?, density?}] covering 0..1 of the loop')
        segs, styles = [], {}
        prev = 0.0
        for i, g in enumerate(segments):
            if not (isinstance(g, dict) and GEN.num(g.get('from'), 0, 1) and GEN.num(g.get('to'), 0, 1) and g['to'] > g['from']):
                raise GEN.E('segment %d: from < to, both 0..1' % i)
            if abs(g['from'] - prev) > 1e-6:
                raise GEN.E('segment %d starts at %.3f but the previous one ends at %.3f: segments must be contiguous' % (i, g['from'], prev))
            prev = g['to']
            sid = g.get('style')
            if sid not in styles:
                try:
                    styles[sid] = STY.load(self.cfg, sid)
                except STY.StyleError as e:
                    raise GEN.E('segment %d style: %s' % (i, e))
                _c, why = STY.check_source(self.cfg, styles[sid]) if (styles[sid].get('source') or {}).get('track') else (None, None)
                if why:
                    raise GEN.E('segment %d style %s: %s' % (i, sid, why))
            bad = set(g) - {'from', 'to', 'style', 'landmark', 'open_space', 'density', 'buildings'}
            if bad:
                raise GEN.E('segment %d: unknown keys %s' % (i, sorted(bad)))
            if g.get('buildings', 'generated') not in ('generated', 'retail'):
                raise GEN.E("segment %d buildings: 'generated' or 'retail'" % i)
            segs.append({'from': float(g['from']), 'to': float(g['to']), 'style': sid, 'landmark': bool(g.get('landmark')),
                         'open_space': bool(g.get('open_space')), 'density': float(g.get('density', 1.0)),
                         'buildings': g.get('buildings', 'generated')})
        if abs(prev - 1.0) > 1e-6:
            raise GEN.E('segments end at %.3f: they must cover the whole loop (last to = 1)' % prev)
        rs = road_style or segs[0]['style']
        if rs not in styles:
            styles[rs] = STY.load(self.cfg, rs)
        D = {'road_style': rs, 'segments': segs, 'transition_m': float(transition_m), 'seed': int(seed), 'points': pts,
             'exclude': [[float(v) for v in r] for r in (exclude or [])], 'junction_at': junction_at,
             'parts': {c: True for c in CATS}, 'road_width_m': 14.0, 'band_m': 45.0, 'verge_in_m': 20.0, 'lamp_density': 1.0,
             'tree_density': 1.0, 'plinths': True, 'headroom_pct': 10.0, 'allow_open_shells': False,
             'objects': None, 'props': 'none'}
        for k, v in (parts or {}).items():
            if k not in D['parts'] or not isinstance(v, bool):
                raise GEN.E('parts: %s (true / false)' % ', '.join(CATS))
            D['parts'][k] = v
        for k, v in (params or {}).items():
            if k not in ('road_width_m', 'band_m', 'verge_in_m', 'lamp_density', 'tree_density', 'plinths', 'headroom_pct',
                         'allow_open_shells', 'objects', 'props', 'route', 'units'):
                raise GEN.E('params: unknown key %r' % k)
            D[k] = v
        if not (GEN.num(D['headroom_pct'], 0, 50) and GEN.num(D['band_m'], 10, 60) and GEN.num(D['road_width_m'], 8, 30)):
            raise GEN.E('params: headroom_pct 0..50, band_m 10..60, road_width_m 8..30')
        if junction_at is not None and not GEN.num(junction_at, 0, 1):
            raise GEN.E('junction_at: a fraction 0..1 of the loop')
        import wb_rta_world as RW
        if D['objects'] is None:                        # RTA3 default: real retail instances when the bound kit writes them
            D['objects'] = 'instances' if RW.supported(self.cfg) else 'geometry'
        if D['props'] not in ('none', 'roadworks'):
            raise GEN.E("params.props: 'none' or 'roadworks' (retail cones before bends: real smashable props, kit 0.3.2)")
        if D['props'] != 'none' and not RW.supported(self.cfg):
            raise GEN.E("params.props needs trackbuild >= 0.3.2 (real retail props)")
        if D['objects'] not in ('instances', 'geometry'):
            raise GEN.E("params.objects: 'instances' (retail instance models, kit 0.3.2) or 'geometry' (static copies)")
        if D['objects'] == 'instances' and not RW.supported(self.cfg):
            raise GEN.E("params.objects 'instances' needs trackbuild >= 0.3.2 (bound: %s); use 'geometry'" % (RW.kit(self.cfg)[1],))
        return D, styles

    def rta_design_quick(self, **kw):
        """FAST preview: approximate stations from the control points, pure planning only (no geometry, no kit dry run)"""
        import time
        t0 = time.time()
        D, styles = self._design_req(**kw)
        st, vo, vi, ladder = layout_stations(D)
        D = dict(D, band_m=vo, verge_in_m=vi)
        xs, zs = [q['p'][0] for q in st], [q['p'][2] for q in st]
        area = [min(xs) - D['band_m'], min(zs) - D['band_m'], max(xs) + D['band_m'], max(zs) + D['band_m']]
        log = []
        plan = plan_design(st, D, styles, D['seed'], area, log)
        per_seg = {}
        for c, rows in plan.items():
            for r in rows:
                per_seg.setdefault(r.get('segment', 0), {}).setdefault(c, 0)
                per_seg[r.get('segment', 0)][c] += 1
        markers = {c: [(r.get('centre') or (r.get('position') or [0, 0, 0])[::2] if c != 'posts' and c != 'signs' and c != 'junction'
                        else [st[r['station']]['p'][0], st[r['station']]['p'][2]]) for r in rows][:500] for c, rows in plan.items()}
        missing = []
        for i, g in enumerate(D['segments']):
            got = per_seg.get(i, {})
            for c in ('buildings', 'posts', 'signs', 'trees'):
                if D['parts'][c] and not got.get(c) and not (c == 'buildings' and g['open_space']):
                    missing.append('segment %d (%s): no %s planned' % (i, g['style'], c))
        return {'ok': True, 'approximate': 'stations from the control polyline; ground, materials and capacity NOT checked',
                'counts': {c: len(r) for c, r in plan.items()}, 'per_segment': per_seg, 'completeness_gaps': missing,
                'verges': {'outer_m': vo, 'inner_m': vi, 'refused': ladder},
                'skipped': log[:400], 'skipped_by_reason': _count(log), 'markers': markers,
                'footprints': [b['footprint'] for b in plan['buildings'] + plan['background']][:600],
                'seconds': round(time.time() - t0, 3),
                'summary_lines': ['QUICK preview (approximate, %.2f s): %s; %d placement(s) skipped; %d completeness gap(s)' % (
                    time.time() - t0, ', '.join('%s %d' % (c, len(r)) for c, r in plan.items()), len(log), len(missing))]}

    def rta_design_preview(self, **kw):
        """FULL preview: the editor's operations on a clone in a background job (progress / cancel); apply = one undo step"""
        D, styles = self._design_req(**kw)
        base = self.content_sha()

        def fn(job):
            clone, rep = self._design_run(D, styles, job)
            key = hashlib.sha256(('%s|%s' % (base, json.dumps(D, sort_keys=True))).encode()).hexdigest()[:16]
            job['clone'], job['key'] = clone, key
            return dict(rep, preview_key=key, base=base, design=D)
        return self._rta_job('design', fn)

    def rta_design_apply(self, job=None, preview_key=None):
        j = self._rta_jobs().get(job)
        if not j or j.get('state') != 'done' or j.get('kind') != 'design':
            raise GEN.E('NEEDS PREVIEW: run the full design preview to the end first')
        if preview_key != j.get('key'):
            raise GEN.E('preview_key does not match that job')
        if self.content_sha() != j['result']['base']:
            raise GEN.E('the project changed after the preview: preview again (nothing changed)')
        if j['result']['problems']:
            raise GEN.E('refused: the preview has problems (%s)' % '; '.join(j['result']['problems']))
        c = j.pop('clone')
        label = 'environment design (%d segment(s), seed %d)' % (len(j['result']['design']['segments']), j['result']['design']['seed'])
        self._push('all', label, (c.cur, c.obj_cur, dict(c.pending), dict(c.pending_meta)), kind='rta_design', index=label)
        j['state'] = 'applied'
        return {'ok': True, 'label': label, 'summary_lines': [label + ': ONE undo step; every category is its own editable block']}

    # ------------------------------------------------------------------ RTA4: route 'keep' (dress an existing route)
    KEEP_MAP = (('asphalt', 'road'), ('pad', 'edge'), ('wall', 'wall'), ('wallback', 'wallback'), ('grass', 'ground'))

    def _design_keep_road_uv(self, road, edge, u_m=6.2, v_m=6.0):
        """RTA4 keep mode: the kept faces of the road / edge materials get UVs in the retail road convention used by road_lanes
        (lane tiles u_m along (u), v_m across (v); measured on US/C1_V1): each corner projected on the station path -> arc length s
        and lateral offset o; u = s / u_m, v = o / v_m. New vt lines are appended; positions / normals / colours untouched."""
        import re as _re
        mats_ = {m for m in (road, edge) if m}
        if not mats_:
            return 0
        st = self.desc()['stations']
        n = len(st)
        acc = [0.0]
        for i in range(1, n + 1):
            a, b = st[i - 1]['p'], st[i % n]['p']
            acc.append(acc[-1] + math.hypot(b[0] - a[0], b[2] - a[2]))
        cell = {}
        for i, q in enumerate(st):
            cell.setdefault((int(q['p'][0] // 20), int(q['p'][2] // 20)), []).append(i)
        lines = self.obj_cur.split(b'\n')
        V = [ln for ln in lines if ln.startswith(b'v ')]
        nvt = sum(1 for ln in lines if ln.startswith(b'vt '))
        cur, out_faces, new_vt, done = None, {}, [], 0
        for li, ln in enumerate(lines):
            if ln.startswith(b'usemtl'):
                cur = ln.split()[1].decode('ascii', 'replace')
            elif ln.startswith(b'f ') and cur in mats_:
                parts = ln.split()[1:]
                rew = []
                for c in parts:
                    f = c.split(b'/')
                    x, _y, z = (float(t) for t in V[int(f[0]) - 1].split()[1:4])
                    cx, cz = int(x // 20), int(z // 20)
                    cand = [i for dx in (-1, 0, 1) for dz in (-1, 0, 1) for i in cell.get((cx + dx, cz + dz), ())] or range(n)
                    i = min(cand, key=lambda k: (st[k]['p'][0] - x) ** 2 + (st[k]['p'][2] - z) ** 2)
                    tx, tz = st[i]['t']
                    dx_, dz_ = x - st[i]['p'][0], z - st[i]['p'][2]
                    s_ = acc[i] + dx_ * tx + dz_ * tz
                    o_ = dx_ * (-tz) + dz_ * tx
                    new_vt.append(b'vt %.5f %.5f' % (s_ / u_m, o_ / v_m))
                    f = list(f) + [b''] * (3 - len(f))
                    f[1] = str(nvt + len(new_vt)).encode()
                    rew.append(b'/'.join(f[:3]))
                out_faces[li] = b'f ' + b' '.join(rew) + (b'\r' if ln.endswith(b'\r') else b'')
                done += 1
        if not done:
            return 0
        lines = [out_faces.get(i, ln) for i, ln in enumerate(lines)]
        last_vt = max(i for i, ln in enumerate(lines) if ln.startswith(b'vt '))
        eol = b'\r' if lines[last_vt].endswith(b'\r') else b''
        lines[last_vt + 1:last_vt + 1] = [x + eol for x in new_vt]
        self._push('obj', 'route keep: retail road UV layout (%d faces)' % done, b'\n'.join(lines), kind='rta_keep_uv', index=0)
        return done

    def _design_keep(self, D, mats, log, steps, step):
        """keep the project's route geometry (branch / bridge fixtures): the fixture's road / wall / ground materials are
        re-assigned to the style's retail materials (usemtl names only; surface words come from the 'like' material, so
        solid stays solid), and exclusion zones keep generated objects off (a) stations whose outer road edge is widened (a
        branch / bypass) and (b) elevated stations (> 0.3 m above the lowest station: ramps, decks) and their surroundings."""
        step('route kept: retail materials on the existing faces', 0.15)
        _l, groups, _v = T['obj_index'](self.obj_cur)
        done = []
        for old, role in self.KEEP_MAP:
            new = mats.get(role)
            g = next((x['i'] for x in groups if x['mat'] == old), None)
            if not new or g is None or new == old:
                continue
            try:
                self.assign_material(g, new, scope='material')
                done.append('%s -> %s' % (old, new))
            except T['EditError'] as ex:
                log.append({'part': 'route', 'skipped': 'material %s kept (%s)' % (old, str(ex)[:120]), 'remedy': 'none needed'})
        steps.append('route kept; materials %s' % ', '.join(done))
        nuv = self._design_keep_road_uv(mats.get('road'), mats.get('edge'))
        if nuv:
            steps.append('road UVs laid out retail-style on %d kept road faces (u along / v across)' % nuv)
        if 'route_road' not in self.constructs():       # the block that owns retail objects (locks / regenerate), as a race layout has
            import json as _j
            lines, groups, _v = T['obj_index'](self.obj_cur)
            road = mats.get('road') or 'asphalt'
            g = next((x for x in groups if x['mat'] == road), None) or next((x for x in groups if x['mat'] == 'asphalt'), None)
            if g is None:
                raise GEN.E('route keep: no road face group to own the retail objects')
            meta = {'id': 'route_road', 'kind': 'race', 'kept_fixture': True, 'route': False}
            ln = list(lines)
            end = ln[g['line']][len(ln[g['line']].rstrip(b'\r\n')):] or b'\n'
            ln.insert(g['line'] + 1, self.TAG + _j.dumps(meta, separators=(',', ':'), sort_keys=True).encode('ascii') + end)
            self._push('obj', 'route keep: road block route_road (owner of retail objects)', b''.join(ln), kind='rta_keep_tag', index=g['i'])
            steps.append('route_road block tagged on the kept road (comment line; the kit ignores it)')
        st = self.desc()['stations']
        y0 = min(q['p'][1] for q in st)
        o1 = [q['offsets'][1] for q in st]
        base = sorted(o1)[len(o1) // 2]                 # the usual outer road edge
        ex, exs = [], set()
        for k, q in enumerate(st):
            wide = q['offsets'][1] < base - 0.5
            high = q['p'][1] > y0 + 0.3
            if wide or high:
                exs.update(range(k - 6, k + 7))
                r = max(abs(q['offsets'][0]), abs(q['offsets'][-1])) + (10.0 if wide else 22.0)
                ex.append([q['p'][0] - r, q['p'][2] - r, q['p'][0] + r, q['p'][2] + r])
        if ex:
            log.append({'part': 'route', 'skipped': 'keep mode: %d exclusion zones around widened / elevated stations (branch, ramps, deck)' % len(ex),
                        'remedy': 'none needed: objects stay off the bypass and the bridge surroundings'})
        vo = abs(st[0]['offsets'][0] - st[0]['offsets'][1]) - 0.6
        vi = abs(st[0]['offsets'][-1] - st[0]['offsets'][-2]) - 0.6
        n = len(st)
        return {'verge_out': max(4.0, round(vo, 1)), 'verge_in': max(4.0, round(vi, 1)), 'exclude': ex,
                'ex_stations': sorted(k % n for k in exs)}

    # ------------------------------------------------------------------ the run
    def _design_run(self, D, styles, job):
        s = self._rta_clone()
        log, steps = [], []

        def step(label, frac):
            if job.get('cancel'):
                raise GEN.E('cancelled before: %s (nothing changed)' % label)
            job['progress'], job['message'] = frac, label
            job['lines'].append('%5.1f%%  %s' % (100 * frac, label))
        rs = styles[D['road_style']]
        tr = (rs.get('source') or {}).get('track')
        have = set(s.desc().get('materials') or {})

        def tex(sty, role, name, like, idx=None):
            ent = sty['palette'].get(role)
            if isinstance(ent, list):
                ent = ent[idx] if ent and idx is not None and idx < len(ent) else None
            if not ent:
                return None
            if ent.get('material'):
                return ent['material']
            if name not in have:
                step('material %s <- %s %s' % (name, sty['source']['track'], ent['texture']), 0.05)
                self._rta_op(s, 'retail_texture', track=sty['source']['track'], texture=ent['texture'], name=name, like=like)
                have.add(name)
            return name
        mats = {r: tex(rs, r, n, like) for r, (n, like) in GEN.MAT.items()}
        mats['edge'] = mats.get('edge') or mats['road']
        mats['ground'] = mats.get('ground') or mats['verge']
        seg_mats = {}
        for k, sid in enumerate(sorted({g['style'] for g in D['segments']})):
            sty = styles[sid]
            fac = [m for m in (tex(sty, 'facades', 'rs%d_facade%d' % (k, j + 1), 'wall', j) for j in range(3)) if m]
            seg_mats[sid] = {'facades': fac or [mats['wall']], 'roof': tex(sty, 'roof', 'rs%d_roof' % k, 'wall') or mats.get('roof') or mats['wall'],
                             'foliage': tex(sty, 'foliage', 'rs%d_foliage' % k, 'grass') or mats.get('foliage') or mats['verge'],
                             'trunk': mats['wallback']}
        if D.get('route') == 'keep':                    # RTA4: dress the EXISTING route (no race layout, lanes or streaming change)
            kw = s._design_keep(D, mats, log, steps, step)
        else:
            step('route (race layout)', 0.15)
            kw = dict(points=D['points'], replace='all', checkpoints=4, n_units=int(D.get('units') or 17),   # RTA5: 18..162 = pvs computed
                      width=D['road_width_m'], material=mats['road'], wall_mat=mats['wall'],
                      back_mat=mats['wallback'], verge_mat=mats['ground'], verge_out=min(60.0, D['band_m']), verge_in=D['verge_in_m'])
            if len({round(p[1], 3) for p in D['points']}) > 1:
                kw['profile'] = {'sloped': True, 'widths': [D['road_width_m']] * len(D['points'])}
            for k, (vo, vi) in enumerate([(kw['verge_out'], kw['verge_in']), (kw['verge_out'], 8.0), (min(kw['verge_out'], 35.0), 8.0),
                                          (min(kw['verge_out'], 25.0), 8.0), (15.0, 8.0)]):
                kw['verge_out'], kw['verge_in'] = vo, vi
                try:
                    self._rta_op(s, 'race_layout', **kw)
                    break
                except T['EditError'] as ex:
                    if k == 4:
                        raise
                    log.append({'part': 'route', 'skipped': 'verges outer %.0f / inner %.0f m refused (%s)' % (vo, vi, str(ex)[:150]),
                                'remedy': 'wider curves keep wider verges; the generator steps down automatically'})
            steps.append('race_layout (verges %.0f / %.0f m)' % (kw['verge_out'], kw['verge_in']))
            pal = rs['palette']
            e = pal.get('edge') or {}
            step('road lanes', 0.2)
            self._rta_op(s, 'road_lanes', edge_material=mats['edge'], edge_width=min(3.0, D['road_width_m'] / 4),
                         main_u_m=round(pal['road'].get('along_m', 6.2), 2), main_v_m=round(pal['road'].get('across_m', 6.0), 2),
                         edge_u_m=round(e.get('along_m') or pal['road'].get('along_m', 6.2), 2))
            try:
                self._rta_op(s, 'streaming_settings', lod_mode='decimate', e_max=0.3, pvs_mode='all' if int(D.get('units') or 17) == 17 else 'computed',
                             drop_below=12.0)
            except T['EditError'] as ex:
                log.append({'part': 'streaming', 'skipped': str(ex)[:200], 'remedy': 'identity LOD kept'})
        st = s.desc()['stations']
        D = dict(D, band_m=kw['verge_out'], verge_in_m=kw['verge_in'])      # plan on the ground that really exists
        if kw.get('exclude'):
            D['exclude'] = list(D.get('exclude') or []) + kw['exclude']
        xs, zs = [q['p'][0] for q in st], [q['p'][2] for q in st]
        area = [min(xs) - D['band_m'], min(zs) - D['band_m'], max(xs) + D['band_m'], max(zs) + D['band_m']]
        step('planning', 0.3)
        plan = plan_design(st, D, styles, D['seed'], area, log)
        if kw.get('ex_stations') or kw.get('exclude'):  # RTA4 keep: objects stay off branches / ramps / decks as buildings do
            exs = set(kw.get('ex_stations') or [])
            before = {c: len(plan[c]) for c in ('posts', 'signs', 'trees')}
            plan['posts'] = [g for g in plan['posts'] if g.get('station') not in exs]
            plan['signs'] = [g for g in plan['signs'] if g.get('station') not in exs]
            plan['trees'] = [g for g in plan['trees'] if not any(GEN._in_rect(g['position'][0], g['position'][2], r) for r in D['exclude'])]
            log.append({'part': 'route', 'skipped': 'keep mode: not placed in exclusion zones %s' % {c: before[c] - len(plan[c]) for c in before},
                        'remedy': 'none needed (branch / ramps / deck kept clear)'})
        uses_game_data = any((styles[sid].get('source') or {}).get('track') for sid in styles) or \
            any(g['buildings'] == 'retail' for g in D['segments'])
        rec = {'design': D, 'area': area, 'seg_mats': seg_mats, 'local_only': bool(uses_game_data)}
        made = {}
        pieces = {}
        for i, g in enumerate(D['segments']):
            if g['buildings'] == 'retail' and g['style'] not in pieces:
                pieces[g['style']] = s._design_pick_pieces(styles[g['style']], D, log)
                for pc in pieces[g['style']]:
                    for tn in pc['textures']:
                        mn = 'rp_' + ''.join(ch for ch in tn.lower() if ch.isalnum() or ch == '_')[:21]
                        pc.setdefault('mats', {})[tn] = mn
                        if mn not in have:
                            self._rta_op(s, 'retail_texture', track=pc['track'], texture=tn, name=mn, like='wall')
                            have.add(mn)
        D = dict(D, _pieces=pieces)
        if plan['buildings'] or plan['background']:
            step('buildings + background (%d + %d)' % (len(plan['buildings']), len(plan['background'])), 0.4)
            made['buildings'] = s._design_buildings(plan['buildings'] + plan['background'], seg_mats, styles, D, log, rec)
        inst = D.get('objects') == 'instances'
        if plan['trees']:
            step('trees (%d)' % len(plan['trees']), 0.55)
            if inst:
                made['trees'] = s._design_objects_apply('trees', s._design_tree_entries(plan['trees'], styles, D, log), D, rec, log)
                gen = [t for t in plan['trees'] if t.get('_generated')]
                if gen:
                    made['trees (generated, original styles)'] = s._design_trees(gen, seg_mats, D, log, rec)
            else:
                made['trees'] = s._design_trees(plan['trees'], seg_mats, D, log, rec)
        if plan['posts']:
            step('posts (%d)' % len(plan['posts']), 0.65)
            made['posts'] = (s._design_objects_apply('posts', s._design_object_entries('posts', plan['posts'], st, D, log), D, rec, log)
                             if inst else s._design_instances('posts', plan['posts'], st, D, log, rec))
        if plan['signs']:
            step('signs (%d)' % len(plan['signs']), 0.75)
            sp = []
            for g in plan['signs']:
                sty = styles[D['segments'][g['segment']]['style']]
                trk = (sty.get('source') or {}).get('track')
                if not trk:
                    log.append({'part': 'signs', 'skipped': 'original style: no retail sign model', 'remedy': REMEDY['no sign-shaped model']})
                    continue
                import wb_rta_catalog as CAT
                ms = _sign_models(CAT.load(self.cfg, trk))
                rtrk = (rs.get('source') or {}).get('track')
                if not ms and rtrk and rtrk != trk:     # this neighbourhood's track has none: the road style's sign (stated)
                    ms = _sign_models(CAT.load(self.cfg, rtrk))
                    trk = rtrk if ms else trk
                if not ms:
                    log.append({'part': 'signs', 'skipped': 'no sign-shaped model in %s' % trk, 'remedy': REMEDY['no sign-shaped model']})
                    continue
                sp.append(dict(g, track=trk, model=ms[0]['id'], setback_m=None, sign=True))
            if sp:
                made['signs'] = (s._design_objects_apply('signs', s._design_object_entries('signs', sp, st, D, log), D, rec, log)
                                 if inst else s._design_instances('signs', sp, st, D, log, rec))
        if D.get('props') == 'roadworks' and plan['signs']:
            step('roadworks props', 0.8)
            made['props'] = s._design_objects_apply('props', s._design_prop_entries(plan['signs'], st, styles, D, log), D, rec, log)
        if plan['junction']:
            step('visual junction stub', 0.82)
            made['junction'] = s._design_junction(plan['junction'][0], st, mats, log)
        step('capacity report (kit dry run)', 0.9)
        regen = s.regenerate(s.obj_cur)
        cap = regen.get('capacity') or []
        wm = max((c['mesh_slot_pct'] for c in cap), default=0)
        wl = max((c['lod_slot_pct'] for c in cap), default=0)
        lim = 100.0 - D['headroom_pct']
        # RTA5: headroom is measured against the GAME's slot; a block above the game's slot that fits the host ceiling under
        # capacity auto is INFO (declared in mod.toml), not a warning; problems = above the effective limit (auto: host ceiling)
        auto = regen.get('capacity_mode') == 'auto'
        declared = lambda c: auto and 'declared' in (c.get('mesh_state'), c.get('lod_state')) and 'over' not in (  # noqa: E731
            c.get('mesh_state'), c.get('lod_state'))
        warn = ['unit %d: mesh %.1f %% / LOD %.1f %% - above your headroom limit %.0f %%' % (c['unit'] if 'unit' in c else i, c['mesh_slot_pct'],
                                                                                             c['lod_slot_pct'], lim)
                for i, c in enumerate(cap) if max(c['mesh_slot_pct'], c['lod_slot_pct']) > lim and not declared(c)]
        problems = []
        if max((c.get('mesh_limit_pct', c['mesh_slot_pct']) for c in cap), default=0) > 100 or \
                max((c.get('lod_limit_pct', c['lod_slot_pct']) for c in cap), default=0) > 100:
            problems.append('a unit exceeds its %s (kit refuses the build)' % ('host ceiling' if auto else 'slot'))
        rows = len(s.desc().get('rows') or [])
        if rows > 83:
            import wb_rta_gen as _g
            problems.append('%d material rows > 83 (format limit: one material-table entry per row in every centre block; '
                            'capacity auto does not raise it) - %s' % (rows, _g._rows_note(s, rows)))
        cinfo = regen.get('capacity_info', [])
        per_seg = {}
        for c, rr in plan.items():
            for r in rr:
                per_seg.setdefault(r.get('segment', 0), {}).setdefault(c, 0)
                per_seg[r.get('segment', 0)][c] += 1
        R = GEN.Route(st)
        bands = {'near (<= 20 m)': 0, 'middle (20..40 m)': 0, 'far (> 40 m)': 0}
        for c in ('buildings', 'background', 'trees'):
            for r in plan[c]:
                x, z = (r['centre'] if 'centre' in r else (r['position'][0], r['position'][2]))
                d = R.dist(x, z)
                bands['near (<= 20 m)' if d <= 20 else 'middle (20..40 m)' if d <= 40 else 'far (> 40 m)'] += 1
        lod_note = ('far LOD: decimated by the kit (e_max 0.3 m); pieces smaller than 12 m (drop_below) leave the far mesh - posts, '
                    'signs, small trees; buildings / landmarks / background silhouettes stay. Collision is never decimated. Check '
                    'Streaming -> LOD preview per section.')
        job['progress'] = 1.0
        return s, {'detail_bands': bands, 'lod_note': lod_note,
                   'steps': steps + ['%s: %s' % kv for kv in made.items()], 'skipped': log, 'skipped_by_reason': _count(log),
                   'capacity': cap, 'worst_mesh_slot_pct': wm, 'worst_lod_slot_pct': wl, 'headroom_pct': D['headroom_pct'],
                   'capacity_warnings': warn, 'rows': rows, 'problems': problems, 'per_segment': per_seg,
                   'capacity_mode': regen.get('capacity_mode', 'game'), 'capacity_info': cinfo,
                   'capacity_declare': regen.get('capacity_declare', {}), 'capacity_requires': regen.get('capacity_requires', []),
                   'summary_lines': ['design preview: %s; worst unit mesh %.1f %% / LOD %.1f %% (headroom limit %.0f %%: %d unit(s) above); '
                                     '%d skipped' % (', '.join('%s %s' % kv for kv in made.items()), wm, wl, lim, len(warn), len(log))]
                   + ['PROBLEM: ' + p for p in problems] + ['INFO: ' + n for n in cinfo]}

    # ------------------------------------------------------------------ category blocks
    def _design_block(self, bid, faces, kind, meta_extra):
        C = self.constructs()
        repl = C[bid]['groups'] if bid in C else []
        meta = dict({'kind': 'rta_d_' + kind, 'id': bid, 'locked': False, 'faces_sha': 'pending',
                     'local_only': (meta_extra.get('design_record') or {}).get('local_only', True)}, **meta_extra)
        after, blk = self._block_bytes(faces, meta, repl)
        r = self._apply_block({'after': after, 'blk': blk, 'planned': faces}, '%s %s (%d faces)' % ('regenerate' if repl else 'generate', bid, len(faces)),
                              'building' if kind in ('buildings', 'background') else 'tree', len(faces))
        u = self.undo_stack[-1]
        new = self._rta_tag_rewrite(bid, {'faces_sha': self._rta_block_sha(self.obj_cur, bid)})
        u['after'] = new
        self.obj_cur = new
        return r

    def _design_buildings(self, rows, seg_mats, styles, D, log, rec):
        import wb_te_bldg as tb
        faces, kept = [], 0
        excl = set(self.constructs().get('rta_d_buildings', {}).get('groups', []))
        for b in rows:
            cx, cz = b['centre']
            gys = [self._ground_y(x + 0.06 * (x - cx), z + 0.06 * (z - cz), excl) for x, z in b['footprint']]
            if any(g is None for g in gys):
                why = 'no collision floor under every corner'
                log.append({'part': 'buildings', 'at': b['centre'], 'skipped': why, 'remedy': remedy(why)})
                continue
            spread = max(gys) - min(gys)
            base = min(gys) - 0.05
            plinth = []
            if spread > 0.5:
                if not D['plinths']:
                    why = 'ground under the corners differs by %.2f m (> 0.5)' % spread
                    log.append({'part': 'buildings', 'at': b['centre'], 'skipped': why, 'remedy': remedy(why)})
                    continue
                base = max(gys) - 0.05                    # the building stands on the high side; a plinth fills down to the low side
                m = seg_mats[b['style']]
                try:
                    pf, _i = tb.building_faces([tuple(p) for p in b['footprint']], min(gys) - 0.05, base - min(gys) + 0.05,
                                               m['facades'][0], m['roof'], 'none', 0.0, [], 0.0, 4.0)
                    plinth = pf
                except Exception as ex:  # noqa: BLE001
                    log.append({'part': 'buildings', 'at': b['centre'], 'skipped': 'plinth refused: %s' % ex, 'remedy': 'flatten the terrain'})
                    continue
            seg = D['segments'][b['segment']]
            pl = (D.get('_pieces') or {}).get(b['style']) or []
            if seg['buildings'] == 'retail' and pl and not b.get('background'):
                fw = math.hypot(b['footprint'][1][0] - b['footprint'][0][0], b['footprint'][1][1] - b['footprint'][0][1])
                fd = math.hypot(b['footprint'][2][0] - b['footprint'][1][0], b['footprint'][2][1] - b['footprint'][1][1])
                fit = [pc for pc in pl if pc['width'] <= fw + 4 and pc['depth'] <= fd + 4]
                if fit:
                    pc = fit[(kept * 7 + b['segment']) % len(fit)]
                    faces += plinth + self._design_piece_faces(pc, b, base)
                    kept += 1
                    rec.setdefault('retail_pieces', []).append({'id': pc['id'], 'track': pc['track'], 'at': b['centre'],
                                                                 'front_confidence': pc['conf'], 'front_source': pc['front_source']})
                    continue
                log.append({'part': 'buildings', 'at': b['centre'], 'skipped': 'no retail piece fits this slot (%.0f x %.0f m): a generated '
                            'building is used instead' % (fw, fd), 'remedy': 'lower the density / widen gaps, or allow more pieces'})
            m = seg_mats[b['style']]
            fac = m['facades'][(kept + (1 if b.get('landmark') else 0)) % len(m['facades'])]
            # doorway on the edge facing the road (generated buildings): the edge whose outward normal is closest to road_dir
            P = [tuple(p) for p in b['footprint']]
            best, door = -2, None
            for i in range(len(P)):
                ex_, ez_ = P[(i + 1) % len(P)][0] - P[i][0], P[(i + 1) % len(P)][1] - P[i][1]
                ln = math.hypot(ex_, ez_) or 1.0
                onx, onz = ez_ / ln, -ex_ / ln              # CCW polygon: outward normal
                d = onx * b['road_dir'][0] + onz * b['road_dir'][1]
                if d > best:
                    best, door = d, i
            ops = [] if b.get('background') else [{'edge': door, 'width': 3.2, 'height': 2.8}]
            try:
                req = self._bldg_req(b['footprint'], round(base, 4), False, b['height'], fac, m['roof'], 'flat', 2.0, ops, 0.0, 6.0, 'keep', None)
                f, _i = tb.building_faces(P, req['base'], req['height'], req['wall_material'], req['roof_material'], 'flat', 2.0,
                                          req['openings'], 0.0, 6.0)
            except Exception as ex:  # noqa: BLE001
                log.append({'part': 'buildings', 'at': b['centre'], 'skipped': 'refused: %s' % str(ex)[:160], 'remedy': 'see the reason'})
                continue
            faces += plinth + f
            kept += 1
        if not faces:
            return 0
        self._design_block('rta_d_buildings', faces, 'buildings', {'items': kept, 'design_record': rec})
        return kept

    def _design_pick_pieces(self, sty, D, log, limit=8, tex_max=18):
        """building pieces of the style's track the asset library trusts to have a front: measured confidence >= 0.6 (or a user
        override of the front), roadside origin, 6..40 m wide, >= 6 m high, <= 1500 triangles; texture budget tex_max"""
        import wb_rta_assets as AS
        trk = (sty.get('source') or {}).get('track')
        if not trk:
            return []
        rows = []
        for a in AS.build(self.cfg, trk)['assets']:
            if a['kind'] != 'piece':
                continue
            e = AS.effective(self.cfg, a)
            if e['category'] not in ('intact building', 'building shell / facade') or e['category'] == 'exclude':
                continue
            ov = e.get('override') or {}
            conf = 1.0 if 'front_deg' in ov else e['front_confidence']
            if conf < 0.6 or (e['back_missing'] and not D['allow_open_shells'] and 'front_deg' not in ov and conf < 0.8):
                continue
            fw = e['footprint_along_front_m']['width']
            if not (6 <= fw <= 40 and e['height_m'] >= 6 and e['triangles'] <= 1500 and (e.get('original_road') or {}).get('distance_m', 99) <= 60):
                continue
            rows.append({'id': e['id'], 'track': trk, 'front_deg': e['front_deg'], 'width': fw, 'depth': e['footprint_along_front_m']['depth'],
                         'textures': sorted(e['textures']), 'anchor': e['anchor'], 'conf': conf, 'shell': e['back_missing'],
                         'front_source': 'override' if 'front_deg' in ov else 'measured'})
        rows.sort(key=lambda r: (-r['conf'], r['id']))
        out, tex = [], set()
        for r in rows:
            if len(tex | set(r['textures'])) > tex_max:
                continue
            tex |= set(r['textures'])
            out.append(r)
            if len(out) >= limit:
                break
        if not out:
            log.append({'part': 'buildings', 'skipped': 'no trusted retail building piece in %s (confidence >= 0.6, size rules)' % trk,
                        'remedy': 'set fronts by hand in the asset library (override), allow open shells, or use generated buildings'})
        return out

    def _design_piece_faces(self, pc, b, base):
        """a retail piece placed so its (measured / overridden) front faces the road: rotate front_deg onto road_dir"""
        import wb_rta_objects as OB
        tris = OB.piece_triangles(self.cfg, pc['track'], pc['id'])
        ax, ay, az = pc['anchor']
        want = math.atan2(b['road_dir'][1], b['road_dir'][0])
        a = want - math.radians(pc['front_deg'])
        ca, sa = math.cos(a), math.sin(a)
        cx, cz = b['centre']
        faces = []
        for tn, _ti, cs in tris:
            pts = [(round(cx + ca * (q[0] - ax) - sa * (q[2] - az), 4), round(base + q[1] - ay, 4), round(cz + sa * (q[0] - ax) + ca * (q[2] - az), 4))
                   for q, _uv, _c in cs]
            ar, nn, _x = GEN._tri(pts)
            if ar < 0.006:
                continue
            faces.append((pc['mats'][tn], [(pts[j], (round(cs[j][1][0], 5), round(cs[j][1][1], 5)), tuple(round(v, 5) for v in nn),
                                            tuple(round(v, 3) for v in cs[j][2])) for j in range(3)]))
        return faces

    def _design_trees(self, rows, seg_mats, D, log, rec):
        import wb_te_bldg as tb
        faces, kept = [], 0
        for t in rows:
            x, z = t['position'][0], t['position'][2]
            g = self._ground_y(x, z)
            rr = t['radius'] + 0.75
            rim = [self._ground_y(x + dx, z + dz) for dx, dz in ((rr, 0), (-rr, 0), (0, rr), (0, -rr))]
            if g is None or any(y is None for y in rim):
                why = 'no ground under the whole crown'
                log.append({'part': 'trees', 'at': [x, z], 'skipped': why, 'remedy': remedy(why)})
                continue
            m = seg_mats[D['segments'][t['segment']]['style']]
            faces += tb.tree_faces([x, round(g - 0.05, 4), z], t['height'], t['radius'], t['sides'], m['trunk'], m['foliage'], 4.0)
            kept += 1
        if not faces:
            return 0
        self._design_block('rta_d_trees', faces, 'trees', {'items': kept, 'design_record': rec,
                                                          'note': 'generated low-poly OPAQUE trees (cut-out trees need cut-out materials)'})
        return kept

    def _design_instances(self, cat, rows, st, D, log, rec):
        """posts / signs: instance-model GEOMETRY COPIES, one block per model, arm / face turned to the road"""
        import sys
        import os
        from wb_te_retail import mat_name
        pm = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'format_research', 'props_mesh')
        if pm not in sys.path:
            sys.path.insert(0, pm)
        import fr_propmesh as FP
        by_model = {}
        for r in rows:
            by_model.setdefault((r['track'], r['model']), []).append(r)
        half = D['road_width_m'] / 2.0
        n_all = 0
        for k, ((trk, mid), rr) in enumerate(sorted(by_model.items())):
            t = FP.load(self._ext_folder(trk))
            raw = t.triangles('I', int(mid[1:]))
            P = [p for _tn, cs in raw for p, _uv, _c in cs]
            ymin = min(p[1] for p in P)
            base = [p for p in P if p[1] < ymin + 0.5] or P
            bx, bz = sum(p[0] for p in base) / len(base), sum(p[2] for p in base) / len(base)
            top = [p for p in P if p[1] > ymin + 0.8 * (max(q[1] for q in P) - ymin)] or P
            ax, az = sum(p[0] for p in top) / len(top) - bx, sum(p[2] for p in top) / len(top) - bz
            arm = math.atan2(az, ax) if math.hypot(ax, az) > 0.2 else 0.0
            if cat == 'signs':                            # face the oncoming traffic: the thin axis along the road
                xs_, zs_ = [p[0] for p in P], [p[2] for p in P]
                arm = 0.0 if (max(xs_) - min(xs_)) < (max(zs_) - min(zs_)) else math.pi / 2
            by_tex = {}
            for r in rr:
                stn = st[r['station']]
                tx, tz = stn['t']
                sd = r['side']
                nx, nz = -tz * sd, tx * sd
                dist = max(half + 1.4, abs(stn['offsets'][1 if sd < 0 else 4]) + 0.6 + 1.0) if r.get('sign') else \
                    max(half + 1.4, abs(stn['offsets'][1 if sd < 0 else 4]) + 0.6 + max(0.5, (r.get('setback_m') or 6) - half - 0.6))
                pos = (stn['p'][0] + nx * dist, stn['p'][1], stn['p'][2] + nz * dist)
                g = self._ground_y(pos[0], pos[2])
                if g is None:
                    log.append({'part': cat, 'at': [pos[0], pos[2]], 'skipped': 'no collision floor below', 'remedy': remedy('no collision floor')})
                    continue
                towards = math.atan2(-nz, -nx) if cat == 'posts' else math.atan2(tz, tx)
                rot = towards - arm
                cr, sr = math.cos(rot), math.sin(rot)
                for tn, cs in raw:
                    pts = [(round(pos[0] + cr * (q[0] - bx) - sr * (q[2] - bz), 4), round(g - 0.05 + q[1] - ymin, 4),
                            round(pos[2] + sr * (q[0] - bx) + cr * (q[2] - bz), 4)) for q, _uv, _c in cs]
                    ar, nn, _x = GEN._tri(pts)
                    if ar < 0.006:
                        continue
                    e = by_tex.setdefault(tn, {'faces': []})
                    nn = tuple(round(v, 5) for v in nn)
                    uvs = [(round(uv[0], 5), round(uv[1], 5)) for _q, uv, _c in cs]
                    e['faces'].append([(pts[j], uvs[j], nn, (0.2, 0.2, 0.2)) for j in range(3)])
                    e['faces'].append([(pts[j], uvs[j], tuple(-v for v in nn), (0.2, 0.2, 0.2)) for j in (0, 2, 1)])
                n_all += 1
            if not by_tex:
                continue
            rows_png = self._static_tex(trk, set(by_tex))
            for tn in by_tex:
                by_tex[tn]['png_rows'] = rows_png[tn]
                by_tex[tn]['mat'] = mat_name(tn) + '_nc'
                by_tex[tn]['collide'] = False
            texs = self._region_textures(None, by_tex, trk)
            bid = 'rta_d_%s%d' % (cat, k + 1)
            meta = {'kind': 'rta_d_' + cat, 'id': bid, 'track': trk, 'model': mid, 'items': len(rr), 'local_only': True,
                    'design_record': rec, 'locked': False}
            C = self.constructs()
            self._apply_retail(trk, by_tex, texs, meta, bid if bid in C else None, sum(len(x['faces']) for x in by_tex.values()),
                               '%s %s %s' % (cat, trk, mid))
        return n_all

    # ------------------------------------------------------------------ RTA3: real retail instance models (kit 0.3.2)
    def _design_object_entries(self, cat, rows, st, D, log):
        """posts / signs -> retail_objects entries (family instance): the model's arm (posts) or face (signs) turned with the
        kit's own matrix rule; base 5 cm into the measured ground. Decoration: no collision (as retail)."""
        import wb_rta_world as RW
        half = D['road_width_m'] / 2.0
        by_model = {}
        for r in rows:
            by_model.setdefault((r['track'], r['model']), []).append(r)
        out = []
        for (trk, mid), rr in sorted(by_model.items()):
            idx = int(mid[1:])
            tris = RW.local_mesh(self.cfg, trk, 'instance', idx)
            P = [p for _tn, cs in tris for p, _uv in cs]
            ymin = min(p[1] for p in P)
            base = [p for p in P if p[1] < ymin + 0.5] or P
            bx, bz = sum(p[0] for p in base) / len(base), sum(p[2] for p in base) / len(base)
            top = [p for p in P if p[1] > ymin + 0.8 * (max(q[1] for q in P) - ymin)] or P
            ax, az = sum(p[0] for p in top) / len(top) - bx, sum(p[2] for p in top) / len(top) - bz
            if cat == 'signs':
                xs_, zs_ = [p[0] for p in P], [p[2] for p in P]
                local = (1.0, 0.0) if (max(xs_) - min(xs_)) < (max(zs_) - min(zs_)) else (0.0, 1.0)   # the face normal = thin axis
            else:
                local = (ax, az) if math.hypot(ax, az) > 0.2 else None
                if local is None:                       # RTA4: symmetric head (double-arm lamp): principal axis of the arm span
                    cx_, cz_ = sum(p[0] for p in top) / len(top), sum(p[2] for p in top) / len(top)
                    sxx = sum((p[0] - cx_) ** 2 for p in top)
                    szz = sum((p[2] - cz_) ** 2 for p in top)
                    sxz = sum((p[0] - cx_) * (p[2] - cz_) for p in top)
                    th = 0.5 * math.atan2(2 * sxz, sxx - szz)
                    local = (math.cos(th), math.sin(th)) if max(sxx, szz) > 0.05 * len(top) else (0.0, 1.0)
                    log.append({'part': cat, 'skipped': 'model %s %s has a symmetric head: its arm span axis is turned across the road'
                                % (trk, mid), 'remedy': 'none needed'})
            off = RW.heading_offset(self.cfg, trk, 'instance', idx, local)
            pl = []
            for r in rr:
                stn = st[r['station']]
                tx, tz = stn['t']
                sd = r['side']
                nx, nz = -tz * sd, tx * sd
                dist = max(half + 1.4, abs(stn['offsets'][1 if sd < 0 else 4]) + 0.6 + 1.0) if r.get('sign') else \
                    max(half + 1.4, abs(stn['offsets'][1 if sd < 0 else 4]) + 0.6 + max(0.5, (r.get('setback_m') or 6) - half - 0.6))
                x, z = stn['p'][0] + nx * dist, stn['p'][2] + nz * dist
                g = self._ground_y(x, z)
                if g is None:
                    log.append({'part': cat, 'at': [x, z], 'skipped': 'no collision floor below', 'remedy': remedy('no collision floor')})
                    continue
                want = math.degrees(math.atan2(-nx, -nz)) if cat == 'posts' else math.degrees(math.atan2(-tx, -tz))
                yaw = round((want - off + 180.0) % 360.0 - 180.0, 3)
                pos = RW.fit_on_ground(self.cfg, trk, 'instance', idx, (x, z), g, yaw)
                if pos is None:
                    log.append({'part': cat, 'at': [x, z], 'skipped': '%s %s has no source placement' % (trk, mid), 'remedy': 'another model'})
                    break
                pl.append({'pos': pos, 'yaw_deg': yaw})
            if pl:
                out.append({'family': 'instance', 'track': trk, 'index': idx, 'static_sha256': RW.static_sha(self.cfg, trk), 'placements': pl})
        return out

    def _design_prop_entries(self, sign_rows, st, styles, D, log):
        """roadworks: 3 retail cones (the road style track's cone-shaped prop type: measured 0.15..0.6 m wide, 0.5..1.5 m tall, the
        most placed one) on the road edge 0.9 m inside the wall, 4 m apart, before each bend that has a warning sign. REAL props:
        the game makes a collision body per placement and they break when hit (retail record verbatim; runtime-unverified here)."""
        import wb_rta_catalog as CAT
        import wb_rta_world as RW
        trk = (styles[D['road_style']].get('source') or {}).get('track')
        if not trk:
            log.append({'part': 'props', 'skipped': 'original road style: no retail prop source', 'remedy': 'use a retail road style'})
            return []
        cones = [m for m in CAT.load(self.cfg, trk).get('prop_types') or []
                 if 0.15 <= max(m['size_m'][0], m['size_m'][2]) <= 0.6 and 0.5 <= m['size_m'][1] <= 1.5]
        cones.sort(key=lambda m: -(m['placements'] or 0))
        if not cones:
            log.append({'part': 'props', 'skipped': 'no cone-shaped prop type in %s' % trk, 'remedy': 'another road style'})
            return []
        idx = int(cones[0]['id'][1:])
        n = len(st)
        pl = []
        for g in sign_rows:
            if g.get('reason', '').startswith('segment'):
                continue
            k0 = g['station']
            for j in range(3):
                stn = st[(k0 + j * 2) % n]                    # stations about 2 m apart in a race layout (count = L / 2)
                tx, tz = stn['t']
                sd = g['side']
                nx, nz = -tz * sd, tx * sd
                wall = abs(stn['offsets'][1 if sd < 0 else 4])
                x, z = stn['p'][0] + nx * (wall - 0.9), stn['p'][2] + nz * (wall - 0.9)
                gy = self._ground_y(x, z)
                if gy is None:
                    log.append({'part': 'props', 'at': [x, z], 'skipped': 'no collision floor below', 'remedy': remedy('no collision floor')})
                    continue
                pos = RW.fit_on_ground(self.cfg, trk, 'prop', idx, (x, z), gy + 0.05, 0.0)
                if pos:
                    pl.append({'pos': pos, 'yaw_deg': 0.0})
        if not pl:
            return []
        return [{'family': 'prop', 'track': trk, 'index': idx, 'static_sha256': RW.static_sha(self.cfg, trk), 'placements': pl}]

    def _design_tree_entries(self, rows, styles, D, log):
        """trees -> CUT-OUT retail tree instances of each segment's source track (shape + alpha-test flag; seeded choice and turn).
        Segments of original styles (no source track) keep generated trees (rows marked _generated)."""
        import random
        import wb_rta_catalog as CAT
        import wb_rta_world as RW
        rnd = random.Random(D['seed'] * 7919 + 11)
        by = {}
        models = {}
        for t in rows:
            trk = (styles[D['segments'][t['segment']]['style']].get('source') or {}).get('track')
            if trk and trk not in models:
                models[trk] = _tree_models(CAT.load(self.cfg, trk))[:4]
            if not trk or not models.get(trk):
                t['_generated'] = True
                if trk:
                    log.append({'part': 'trees', 'at': [t['position'][0], t['position'][2]], 'skipped': 'no cut-out tree model in %s' % trk,
                                'remedy': 'generated tree used instead'})
                continue
            x, z = t['position'][0], t['position'][2]
            g = self._ground_y(x, z)
            rr = min(3.0, t['radius'])
            rim = [self._ground_y(x + dx, z + dz) for dx, dz in ((rr, 0), (-rr, 0), (0, rr), (0, -rr))]
            if g is None or any(y is None for y in rim):
                log.append({'part': 'trees', 'at': [x, z], 'skipped': 'no ground under the crown', 'remedy': remedy('no ground under the whole crown')})
                continue
            m = models[trk][rnd.randrange(len(models[trk]))]
            idx = int(m['id'][1:])
            yaw = round(rnd.uniform(-180, 180), 2)
            pos = RW.fit_on_ground(self.cfg, trk, 'instance', idx, (x, z), g, yaw)
            if pos is None:
                continue
            by.setdefault((trk, idx), []).append({'pos': pos, 'yaw_deg': yaw})
        return [{'family': 'instance', 'track': k[0], 'index': k[1], 'static_sha256': RW.static_sha(self.cfg, k[0]), 'placements': v}
                for k, v in sorted(by.items())]

    def _obj_nudge(self, pos, log, cat):
        """a placement at least 0.1 m inside exactly ONE unit region (kit rule EDGE_M 0.05 m, float32 region lines): unchanged when it
        already is, else moved up to 0.6 m (8 directions); None when no such spot (skipped with the reason)"""
        key = hashlib.sha256(self.cur).hexdigest()
        cache = self.__dict__.setdefault('_unit_cache', {})
        if key not in cache:
            cache.clear()
            K = T['kit_trackbuild'](self.cfg)
            cache[key] = K['units'].make_units(self.desc()) if 'units' in K else self.coverage(self.obj_cur)['units']
        units = cache[key]
        for r in (0.0, 0.15, 0.3, 0.6):
            for a in range(8 if r else 1):
                x = pos[0] + r * math.cos(a * math.pi / 4)
                z = pos[2] + r * math.sin(a * math.pi / 4)
                if sum(1 for u in units if u.inside(x, z, grow=-0.1)) == 1:
                    return [round(x, 3), pos[1], round(z, 3)]
        log.append({'part': cat, 'at': [pos[0], pos[2]], 'skipped': 'on a section boundary (no spot 0.1 m inside one section)',
                    'remedy': 'move it a little along the road'})
        return None

    def _design_objects_apply(self, cat, entries, D, rec, log, locked=False):
        """write the category's entries into desc retail_objects (replacing the ones this category owned) + the ownership record
        in the route block's tag (route_road meta rta_objects); one undo entry here (the design apply / regenerate collapses its
        steps into ONE). -> placements written"""
        C = self.constructs()
        if 'route_road' not in C:
            raise GEN.E('retail objects need the race layout block route_road (apply a race layout first)')
        own = dict(C['route_road']['meta'].get('rta_objects') or {})
        old = set((own.get(cat) or {}).get('entries_sha') or [])
        cur = [e for e in (self.desc().get('retail_objects') or []) if _entry_sha(e) not in old]
        for e in entries:                                # RTA3: every placement clear of the section boundaries (kit EDGE_M)
            e['placements'] = [dict(p, pos=q) for p in e['placements'] for q in [self._obj_nudge(p['pos'], log, cat)] if q is not None]
        entries = [e for e in entries if e['placements']]
        new_list = cur + entries
        new_cur = T['desc_splice'](self.cur, {'retail_objects': new_list})
        n = sum(len(e['placements']) for e in entries)
        own[cat] = {'entries_sha': [_entry_sha(e) for e in entries], 'items': n, 'seed': D['seed'], 'locked': bool(locked),
                    'types': ['%s %s%d' % (e['track'], 'P' if e['family'] == 'prop' else 'I', e['index']) for e in entries],
                    'kind': ('retail PROPS (the game makes collision bodies; they break when hit - runtime-unverified here; LOCAL ONLY)'
                             if any(e['family'] == 'prop' for e in entries) else
                             'retail instance models (decoration, no collision; LOCAL ONLY)')}
        new_obj = self._rta_tag_rewrite('route_road', {'rta_objects': own})
        self._push('all', 'design %s: %d retail object placement(s)' % (cat, n), (new_cur, new_obj, dict(self.pending), dict(self.pending_meta)),
                   kind='rta_objects', index=cat)
        return n

    def _design_junction(self, j, st, mats, log):
        stn = st[j['station']]
        tx, tz = stn['t']
        nx, nz = tz, -tx                                  # the outer (n-) side
        start = abs(stn['offsets'][1]) + 0.7
        y = stn['p'][1] + 0.06
        pts = [[round(stn['p'][0] + nx * (start + d), 2), round(y, 3), round(stn['p'][2] + nz * (start + d), 2)] for d in (0, j['length_m'] / 2, j['length_m'])]
        try:
            self._rta_op(self, 'road_profile', points=pts, closed=False, widths=[j['width_m']] * 3, banks=[0, 0, 0], material=mats['road'])
            return 'visual stub %.0f m (wall closed, no AI link)' % j['length_m']
        except T['EditError'] as ex:
            log.append({'part': 'junction', 'skipped': str(ex)[:200], 'remedy': 'move junction_at to a straight with ground beyond the wall'})
            return 0

    # ------------------------------------------------------------------ per-category regenerate / lock / facing check
    def rta_design_parts(self):
        out = []
        for bid, c in self.constructs().items():
            m = c['meta']
            if not str(m.get('kind', '')).startswith('rta_d_'):
                continue
            edited = m.get('faces_sha') not in (None, 'pending') and self._rta_faces_sha(c) != m.get('faces_sha')
            out.append({'id': bid, 'category': m['kind'][6:], 'items': m.get('items'), 'locked': bool(m.get('locked')),
                        'manually_edited': edited, 'seed': (m.get('design_record') or {}).get('design', {}).get('seed')})
        C = self.constructs()
        own = (C.get('route_road') or {}).get('meta', {}).get('rta_objects') or {}
        cur = {_entry_sha(e) for e in (self.desc().get('retail_objects') or [])}
        for cat, o in sorted(own.items()):                   # RTA3: retail instance categories (kit retail_objects)
            out.append({'id': 'objects:' + cat, 'category': cat, 'items': o.get('items'), 'locked': bool(o.get('locked')),
                        'manually_edited': not set(o.get('entries_sha') or []) <= cur, 'seed': o.get('seed'), 'kind': o.get('kind'),
                        'types': o.get('types')})
        return {'ok': True, 'parts': out, 'summary_lines': ['%d design part(s)' % len(out)]}

    def rta_design_lock(self, part=None, locked=True):
        C = self.constructs()
        if isinstance(part, str) and part.startswith('objects:'):
            own = dict((C.get('route_road') or {}).get('meta', {}).get('rta_objects') or {})
            cat = part[8:]
            if cat not in own:
                raise GEN.E('part %r is not a design part (rta_design_parts lists them)' % (part,))
            own[cat] = dict(own[cat], locked=bool(locked))
            after = self._rta_tag_rewrite('route_road', {'rta_objects': own})
            self._push('obj', '%s %s' % ('lock' if locked else 'unlock', part), after, kind='rta_lock', index=part)
            return {'ok': True, 'summary_lines': ['%s %s (one undo step)' % ('locked' if locked else 'unlocked', part)]}
        if part not in C or not str(C[part]['meta'].get('kind', '')).startswith('rta_d_'):
            raise GEN.E('part %r is not a design part (rta_design_parts lists them)' % (part,))
        after = self._rta_tag_rewrite(part, {'locked': bool(locked)})
        self._push('obj', '%s %s' % ('lock' if locked else 'unlock', part), after, kind='rta_lock', index=part)
        return {'ok': True, 'summary_lines': ['%s %s (one undo step)' % ('locked' if locked else 'unlocked', part)]}

    def rta_design_regenerate(self, category=None, seed=None, confirm=False):
        """regenerate ONE category (buildings / trees / posts / signs) with a new seed; other blocks untouched; locked parts refused;
        hand-edited parts need confirm; ONE undo step"""
        if category not in ('buildings', 'trees', 'posts', 'signs'):
            raise GEN.E('category: buildings, trees, posts or signs')
        C = self.constructs()
        own = (C.get('route_road') or {}).get('meta', {}).get('rta_objects') or {}
        if category in own and category in ('posts', 'signs', 'trees'):
            return self._design_regen_objects(category, seed, confirm, own)
        mine = [b for b, c in C.items() if str(c['meta'].get('kind', '')) == 'rta_d_' + category]
        if not mine:
            raise GEN.E('no %s design part in this project' % category)
        for b in mine:
            m = C[b]['meta']
            if m.get('locked'):
                raise GEN.E('%s is LOCKED: unlock it first (nothing changed)' % b)
            if m.get('faces_sha') not in (None, 'pending') and self._rta_faces_sha(C[b]) != m['faces_sha'] and confirm is not True:
                raise GEN.E('%s was edited by hand: repeat with confirm: true to replace those edits (nothing changed)' % b)
        rec = next(C[b]['meta'].get('design_record') for b in mine if C[b]['meta'].get('design_record'))
        D = dict(rec['design'])
        if seed is not None:
            if not (isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < 2 ** 31):
                raise GEN.E('seed: an integer 0..2^31-1')
            D['seed'] = seed
        styles = {g['style']: STY.load(self.cfg, g['style']) for g in D['segments']}
        styles.setdefault(D['road_style'], STY.load(self.cfg, D['road_style']))
        st = self.desc()['stations']
        log = []
        Dp = dict(D, parts={c: c == category for c in CATS})
        plan = plan_design(st, Dp, styles, D['seed'], rec['area'], log)
        before = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta))
        n0 = len(self.undo_stack)
        try:
            if category in ('posts', 'signs'):         # every block of the category is rebuilt (one per model)
                rows = plan[category]
                if category == 'signs':
                    import wb_rta_catalog as CAT
                    rows2 = []
                    for g in rows:
                        trk = styles[D['segments'][g['segment']]['style']]['source'].get('track') or styles[D['road_style']]['source'].get('track')
                        ms = _sign_models(CAT.load(self.cfg, trk)) or _sign_models(CAT.load(self.cfg, styles[D['road_style']]['source']['track']))
                        if ms:
                            rows2.append(dict(g, track=trk, model=ms[0]['id'], setback_m=None, sign=True))
                    rows = rows2
                n = self._design_instances(category, rows, st, D, log, dict(rec, design=D))
            else:
                seg_mats = rec.get('seg_mats') or {}
                if not seg_mats:
                    raise GEN.E('this design part has no material record: regenerate the whole design instead')
                if category == 'buildings':
                    pieces = {}
                    have = set(self.desc().get('materials') or {})
                    for g in D['segments']:
                        if g['buildings'] == 'retail' and g['style'] not in pieces:
                            pieces[g['style']] = self._design_pick_pieces(styles[g['style']], D, log)
                            for pc in pieces[g['style']]:
                                for tn in pc['textures']:
                                    mn = 'rp_' + ''.join(ch for ch in tn.lower() if ch.isalnum() or ch == '_')[:21]
                                    pc.setdefault('mats', {})[tn] = mn
                                    if mn not in have:
                                        self._rta_op(self, 'retail_texture', track=pc['track'], texture=tn, name=mn, like='wall')
                                        have.add(mn)
                    n = self._design_buildings(plan['buildings'] + plan['background'], seg_mats, styles, dict(D, _pieces=pieces), log,
                                               dict(rec, design=D))
                else:
                    n = self._design_trees(plan['trees'], seg_mats, D, log, dict(rec, design=D))
        except Exception:
            self.cur, self.obj_cur = before[0], before[1]
            self.pending, self.pending_meta = dict(before[2]), dict(before[3])
            del self.undo_stack[n0:]
            raise
        after = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta))
        del self.undo_stack[n0:]
        self.cur, self.obj_cur = before[0], before[1]
        self.pending, self.pending_meta = dict(before[2]), dict(before[3])
        label = 'regenerate %s (seed %d, %s items)' % (category, D['seed'], n)
        self._push('all', label, after, kind='rta_design_regen', index=category)
        return {'ok': True, 'label': label, 'skipped': log, 'summary_lines': [label + ': ONE undo step; other categories untouched']}

    def _design_regen_objects(self, category, seed, confirm, own):
        o = own[category]
        if o.get('locked'):
            raise GEN.E('objects:%s is LOCKED: unlock it first (nothing changed)' % category)
        cur = {_entry_sha(e) for e in (self.desc().get('retail_objects') or [])}
        if not set(o.get('entries_sha') or []) <= cur and confirm is not True:
            raise GEN.E('objects:%s was edited by hand: repeat with confirm: true to replace those edits (nothing changed)' % category)
        rec = next((c['meta'].get('design_record') for c in self.constructs().values() if c['meta'].get('design_record')), None)
        if not rec:
            raise GEN.E('no design record in this project: regenerate the whole design instead')
        D = dict(rec['design'])
        if seed is not None:
            if not (isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < 2 ** 31):
                raise GEN.E('seed: an integer 0..2^31-1')
            D['seed'] = seed
        styles = {g['style']: STY.load(self.cfg, g['style']) for g in D['segments']}
        styles.setdefault(D['road_style'], STY.load(self.cfg, D['road_style']))
        st = self.desc()['stations']
        log = []
        plan = plan_design(st, dict(D, parts={c: c == category for c in CATS}), styles, D['seed'], rec['area'], log)
        before = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta))
        n0 = len(self.undo_stack)
        try:
            if category == 'trees':
                ents = self._design_tree_entries(plan['trees'], styles, D, log)
            elif category == 'signs':
                import wb_rta_catalog as CAT
                rows = []
                for g in plan['signs']:
                    trk = styles[D['segments'][g['segment']]['style']]['source'].get('track') or styles[D['road_style']]['source'].get('track')
                    ms = _sign_models(CAT.load(self.cfg, trk)) if trk else []
                    if ms:
                        rows.append(dict(g, track=trk, model=ms[0]['id'], setback_m=None, sign=True))
                ents = self._design_object_entries('signs', rows, st, D, log)
            else:
                ents = self._design_object_entries('posts', plan['posts'], st, D, log)
            n = self._design_objects_apply(category, ents, D, rec, log)
        except Exception:
            self.cur, self.obj_cur = before[0], before[1]
            self.pending, self.pending_meta = dict(before[2]), dict(before[3])
            del self.undo_stack[n0:]
            raise
        after = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta))
        del self.undo_stack[n0:]
        self.cur, self.obj_cur = before[0], before[1]
        self.pending, self.pending_meta = dict(before[2]), dict(before[3])
        label = 'regenerate objects:%s (seed %d, %d placements)' % (category, D['seed'], n)
        self._push('all', label, after, kind='rta_design_regen', index=category)
        return {'ok': True, 'label': label, 'skipped': log, 'summary_lines': [label + ': ONE undo step; other categories untouched']}

    DESIGN_LAYOUT = {'rta_design_quick': 'rta_design_quick', 'rta_design_preview': 'rta_design_preview', 'rta_design_apply': 'rta_design_apply',
                     'rta_design_parts': 'rta_design_parts', 'rta_design_lock': 'rta_design_lock', 'rta_design_regenerate': 'rta_design_regenerate'}


def facing_check(faces, centre, road_dir):
    """the placed piece's measured front (wb_rta_assets.analyse_piece on the placed faces) vs the direction to the road ->
    angle in degrees (0 = facing the road). Used to catch reversed shells."""
    import wb_rta_assets as AS
    tris = [(m, None, [(c[0], c[1], c[3]) for c in cs]) for m, cs in faces]
    f = AS.analyse_piece(tris, None)
    want = math.degrees(math.atan2(road_dir[1], road_dir[0])) % 360
    return abs((f['front_deg'] - want + 180) % 360 - 180)


def _count(log):
    out = {}
    for x in log:
        k = x['part'] + ': ' + x['skipped'].split('(')[0].strip()[:80]
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
