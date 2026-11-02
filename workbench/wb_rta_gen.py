r"""wb_rta_gen - retail-style generation: route + style preset -> an editable track (Workbench 0.33 retail-style authoring, 2026-11-01).
A mixin of wb_trackedit.TrackSource (bound like the other wb_te_* mixins).

Workflow (each step is the editor's OWN operation with its own checks; nothing here writes geometry another way):
  1 retail_texture      the style's palette textures -> materials rs_* (texel copies from YOUR game data, LOCAL ONLY)
  2 race_layout         closed route (control points; equal y, or a sloped profile), width, walls, verges -> route + units
  3 road_lanes          lane band + edge strips at the MEASURED texture repeats
  4 streaming_settings  decimate e_max 0.3, pvs all, drop_below 12 (needs trackbuild 0.3.1-te2: LOD fallback per material)
  (ground) the race layout's own verges are the scenery ground: outer verge = band (<= 60 m), inner verge 20 m (8 m when
                        refused). A bounding-box unit include was tried first and REFUSED by kit gate V2 (drivable samples in
                        two units) - recorded in the workstream log; route-owned verges keep every face inside its unit.
  7 retail_lamps        the style's tall roadside model at the MEASURED spacing / setback (geometry copies)
  8 rta_buildings       ONE construction block: generated buildings (wb_te_bldg.building_faces) with retail facade / roof
                        materials, placed by seed at the MEASURED setback, with road clearance, curve sightlines, doorways,
                        exclusion areas and no overlaps; every refusal is listed
  9 rta_trees           ONE construction block: low-poly OPAQUE trees (wb_te_bldg.tree_faces) at the MEASURED density /
                        setback (retail trees are cut-out cards: approximation, labelled)
The whole run is computed on a CLONE of the editor state in a background job (progress, cancel); Apply swaps the result in as
ONE undo step (buffer 'all': description + OBJ + imported files). Parts 8 / 9 carry their parameters, seed and a face hash in
their block tag (# wb-construct {...}): 'regenerate part' replaces only that block, refuses locked parts, and refuses
manually edited parts unless confirmed. Exclusion areas and asset replacement are part parameters.
"""
import copy
import hashlib
import json
import math
import os
import random
import threading
import time

import wb_te_bldg as tb
import wb_rta_style as STY

T = {}
MAT = {'road': ('rs_road', 'asphalt'), 'edge': ('rs_edge', 'asphalt'), 'wall': ('rs_wall', 'wall'),
       'wallback': ('rs_wallback', 'wallback'), 'verge': ('rs_verge', 'grass'), 'ground': ('rs_ground', 'grass'),
       'roof': ('rs_roof', 'wall'), 'foliage': ('rs_foliage', 'grass')}
PARTS = ('lamps', 'buildings', 'trees')


def E(msg):
    return T['EditError'](msg)


def num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


def parse_route_text(text):
    """'x, z' or 'x, y, z' per line (comma / space / tab separated; # comments) -> points [[x, y, z]]"""
    pts = []
    for ln in str(text).splitlines():
        ln = ln.split('#', 1)[0].replace(',', ' ').replace(';', ' ').split()
        if not ln:
            continue
        try:
            v = [float(x) for x in ln]
        except ValueError:
            raise E('route import: line %r is not 2 or 3 numbers' % ' '.join(ln))
        if len(v) == 2:
            v = [v[0], None, v[1]]
        if len(v) != 3:
            raise E('route import: each line needs x z or x y z')
        pts.append(v)
    return pts


def _tri(pts):
    a, b, c = pts
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    ln = math.sqrt(sum(x * x for x in n))
    if ln == 0:
        return 0.0, (0.0, 1.0, 0.0), None
    return ln / 2, tuple(x / ln for x in n), None


def faces_sha(faces):
    """order-independent hash of (material, corner positions to 1 cm) - detects hand edits of a generated block"""
    rows = sorted('%s|%s' % (mat, ';'.join('%.2f %.2f %.2f' % tuple(c[0]) for c in corners)) for mat, corners in faces)
    return hashlib.sha256('|'.join(rows).encode()).hexdigest()[:16]


def _rect_corners(cx, cz, tx, tz, w, d):
    """rectangle centred (cx, cz), width w along (tx, tz), depth d along the normal -> 4 corners counter-clockwise (x, z)"""
    nx, nz = -tz, tx
    hw, hd = w / 2.0, d / 2.0
    P = [(cx - tx * hw - nx * hd, cz - tz * hw - nz * hd), (cx + tx * hw - nx * hd, cz + tz * hw - nz * hd),
         (cx + tx * hw + nx * hd, cz + tz * hw + nz * hd), (cx - tx * hw + nx * hd, cz - tz * hw + nz * hd)]
    area = sum(P[i][0] * P[(i + 1) % 4][1] - P[(i + 1) % 4][0] * P[i][1] for i in range(4))
    return P if area > 0 else list(reversed(P))


def _sep(A, B, gap=0.0):
    """separating-axis test for two convex polygons (x, z) with an extra gap -> True when they are apart"""
    for P in (A, B):
        for i in range(len(P)):
            ex, ez = P[(i + 1) % len(P)][0] - P[i][0], P[(i + 1) % len(P)][1] - P[i][1]
            nx, nz = -ez, ex
            ln = math.hypot(nx, nz) or 1.0
            nx, nz = nx / ln, nz / ln
            a = [p[0] * nx + p[1] * nz for p in A]
            b = [p[0] * nx + p[1] * nz for p in B]
            if max(a) + gap < min(b) or max(b) + gap < min(a):
                return True
    return False


def _in_rect(x, z, r):
    return r[0] <= x <= r[2] and r[1] <= z <= r[3]


def _rows_note(s, n):
    """RTA5: the kit capacity table's rows figure (game 83, host 255 with the BMRX extension + patch 131), or a plain line"""
    try:
        import wb_trackedit as _te
        return _te.kit_trackbuild(s.cfg)['capacity'].rows_note(n)
    except Exception:  # noqa: BLE001   older kit (no capacity table)
        return 'rows %d / 83' % n


class Route:
    """the built route's stations: plan distance to the centre line and local curvature"""

    CELL = 20.0

    def __init__(self, stations):
        self.st = stations
        self.n = len(stations)
        self.grid = {}                                  # segment index by plan cell (exact search, rta2 speed-up)
        c = self.CELL
        for k in range(self.n):
            a, b = self.st[k]['p'], self.st[(k + 1) % self.n]['p']
            for i in range(int(min(a[0], b[0]) // c), int(max(a[0], b[0]) // c) + 1):
                for j in range(int(min(a[2], b[2]) // c), int(max(a[2], b[2]) // c) + 1):
                    self.grid.setdefault((i, j), []).append(k)

    def _seg_d2(self, k, x, z):
        a, b = self.st[k]['p'], self.st[(k + 1) % self.n]['p']
        ax, az, bx, bz = a[0], a[2], b[0], b[2]
        dx, dz = bx - ax, bz - az
        L = dx * dx + dz * dz
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L))
        return (x - ax - t * dx) ** 2 + (z - az - t * dz) ** 2

    def dist(self, x, z):
        """exact plan distance to the centre polyline: rings of grid cells until no closer segment can exist"""
        c = self.CELL
        ci, cj = int(x // c), int(z // c)
        best = None
        seen = set()
        r = 0
        while r < 400:
            for i in range(ci - r, ci + r + 1):
                for j in range(cj - r, cj + r + 1):
                    if max(abs(i - ci), abs(j - cj)) != r:
                        continue
                    for k in self.grid.get((i, j), ()):
                        if k in seen:
                            continue
                        seen.add(k)
                        d = self._seg_d2(k, x, z)
                        if best is None or d < best:
                            best = d
            if best is not None and math.sqrt(best) <= r * c:
                break
            r += 1
        if best is None:                                # far from everything: exhaustive
            best = min(self._seg_d2(k, x, z) for k in range(self.n))
        return math.sqrt(best)

    def curvature(self, k, span=4):
        """signed 1 / radius at station k (+ = turning left)"""
        a, b = self.st[(k - span) % self.n], self.st[(k + span) % self.n]
        ang = math.atan2(b['t'][1], b['t'][0]) - math.atan2(a['t'][1], a['t'][0])
        ang = (ang + math.pi) % (2 * math.pi) - math.pi
        ds = sum(math.hypot(self.st[(i + 1) % self.n]['p'][0] - self.st[i % self.n]['p'][0],
                            self.st[(i + 1) % self.n]['p'][2] - self.st[i % self.n]['p'][2]) for i in range(k - span, k + span))
        return ang / ds if ds else 0.0


def plan_buildings(stations, P, facades, seed, exclude, area, log, pieces=None):
    """deterministic building footprints along both sides. P = merged params. pieces = retail building pieces (long side, short
    side): each slot takes one of them at its own size. -> list of dicts"""
    rnd = random.Random('b%d' % seed)
    R = Route(stations)
    half = P['road_width_m'] / 2.0
    clear = half + P['wall_thick_m'] + 3.0          # road edge + wall + 3 m pavement clearance (the verge IS the building ground)
    setback0 = max(clear, P['building_setback_m'])
    out, foot = [], []
    var = P['variation']
    dens = P['building_density']
    if dens <= 0 or not (facades or pieces):
        return out
    seg = [0.0]
    for k in range(1, R.n + 1):
        a, b = stations[k - 1]['p'], stations[k % R.n]['p']
        seg.append(seg[-1] + math.hypot(b[0] - a[0], b[2] - a[2]))
    total = seg[-1]
    for side in (-1, 1):
        s = rnd.uniform(0, 20)
        while s < total - 10:
            w = rnd.uniform(*P['building_width_m'])
            d = rnd.uniform(*P['building_depth_m'])
            pi = None
            if pieces:
                pi = rnd.randrange(len(pieces))
                w, d = pieces[pi]['long'], pieces[pi]['short']
            gap = rnd.uniform(*P['building_gap_m']) / max(0.05, dens)
            sc = s + w / 2
            k = max(0, min(R.n - 1, next((i for i in range(R.n) if seg[i + 1] >= sc), R.n - 1)))
            st = stations[k]
            tx, tz = st['t']
            nx, nz = -tz, tx
            off = setback0 + d / 2 + rnd.uniform(0, var * 10.0)
            cx, cz = st['p'][0] + side * nx * off, st['p'][2] + side * nz * off
            why = None
            kap = R.curvature(k)
            inner = (kap > 0 and side > 0) or (kap < 0 and side < 0)
            if inner and abs(kap) > 1.0 / 90.0 and off - d / 2 < clear + P['curve_clearance_m'] * 2:
                why = 'inside of a curve (radius %.0f m): kept clear for the sightline' % (1 / abs(kap))
            corners = _rect_corners(cx, cz, tx, tz, w, d)
            if not why and any(R.dist(x, z) < clear for x, z in corners):
                why = 'closer than %.1f m to the route centre line (road clearance)' % clear
            if not why and any(not _in_rect(x, z, area) for x, z in corners):
                why = 'outside the generated ground / unit area'
            if not why and any(_in_rect(cx, cz, r) or any(_in_rect(x, z, r) for x, z in corners) for r in exclude):
                why = 'inside an exclusion area'
            if not why and any(not _sep(corners, f, 2.0) for f in foot):
                why = 'overlaps another building'
            if why:
                log.append({'part': 'buildings', 'at': [round(cx, 1), round(cz, 1)], 'skipped': why})
            else:
                h = max(4.0, min(40.0, P['building_height_m'] * rnd.uniform(1 - var, 1 + var)))
                fac = facades[rnd.randrange(len(facades))] if facades else None
                door = None
                if P['doorways'] and w >= 8:
                    # the edge facing the road: the corner list is CCW; pick the edge whose midpoint is nearest the route
                    mids = [((corners[i][0] + corners[(i + 1) % 4][0]) / 2, (corners[i][1] + corners[(i + 1) % 4][1]) / 2) for i in range(4)]
                    door = min(range(4), key=lambda i: R.dist(*mids[i]))
                out.append({'footprint': [[round(x, 3), round(z, 3)] for x, z in corners], 'height': round(h, 2), 'facade': fac,
                            'door_edge': door, 'centre': [round(cx, 2), round(cz, 2)], 'side': side, 'piece': pi,
                            'tangent': [round(tx, 5), round(tz, 5)]})
                foot.append(corners)
            s += w + gap
    return out


def plan_trees(stations, P, seed, exclude, area, buildings, log):
    rnd = random.Random('t%d' % seed)
    R = Route(stations)
    half = P['road_width_m'] / 2.0
    clear = half + P['wall_thick_m'] + 1.5
    seg = [0.0]
    for k in range(1, R.n + 1):
        a, b = stations[k - 1]['p'], stations[k % R.n]['p']
        seg.append(seg[-1] + math.hypot(b[0] - a[0], b[2] - a[2]))
    total = seg[-1]
    n = int(round(total / 1000.0 * P['trees_per_km'] * P['tree_density']))
    n = max(0, min(n, 400))
    out = []
    feet = [b['footprint'] for b in buildings]
    for i in range(n):
        s = (i + rnd.uniform(0, 1)) * total / max(1, n)
        k = max(0, min(R.n - 1, next((j for j in range(R.n) if seg[j + 1] >= s), R.n - 1)))
        st = stations[k]
        tx, tz = st['t']
        side = 1 if rnd.random() < 0.5 else -1
        off = max(clear + 2.0, P['tree_setback_m'] * rnd.uniform(1 - P['variation'], 1 + P['variation']))
        x, z = st['p'][0] - tz * side * off, st['p'][2] + tx * side * off
        rad = rnd.uniform(1.6, 3.0)
        why = None
        if R.dist(x, z) < clear + rad:
            why = 'road clearance'
        elif not _in_rect(x, z, area):
            why = 'outside the generated ground / unit area'
        elif any(_in_rect(x, z, r) for r in exclude):
            why = 'inside an exclusion area'
        else:
            me = _rect_corners(x, z, 1.0, 0.0, 2 * rad, 2 * rad)
            if any(not _sep(me, f, 1.0) for f in feet):
                why = 'overlaps a building'
        if why:
            log.append({'part': 'trees', 'at': [round(x, 1), round(z, 1)], 'skipped': why})
            continue
        out.append({'position': [round(x, 3), st['p'][1], round(z, 3)], 'height': round(rnd.uniform(5.0, 10.0), 2),
                    'radius': round(rad, 2), 'sides': 6})
    return out


class GenMixin:
    # ------------------------------------------------------------------ requests
    def _rta_req(self, style=None, points=None, route_text=None, params=None, parts=None, exclude=None, seed=None):
        cfg = self.cfg
        try:
            sty = STY.load(cfg, style)
        except STY.StyleError as e:
            raise E('style: %s' % e)
        cat, why = STY.check_source(cfg, sty) if (sty.get('source') or {}).get('track') else (None, None)
        if why:
            raise E('style %s cannot be applied to your game data: %s' % (style, why))
        if route_text is not None:
            points = parse_route_text(route_text)
        if not (isinstance(points, list) and 4 <= len(points) <= 64):
            raise E('route: 4..64 closed control points [[x, y, z], ...] (or route_text with one "x z" / "x y z" per line)')
        ys = [p[1] for p in points if p[1] is not None]
        y0 = ys[0] if ys else 20.0
        pts = [[float(p[0]), float(p[1] if p[1] is not None else y0), float(p[2])] for p in points]
        for p in pts:
            if not all(num(v, -1e5, 1e5) for v in p):
                raise E('route: coordinates must be finite numbers within +-100 km')
        P = dict(sty['defaults'])
        m = sty['measured']
        posts = sty['palette'].get('posts') or []
        P.update({'wall_thick_m': 0.6, 'facade_repeat_m': {}, 'buildings_source': 'generated', 'piece_limit': 6, 'piece_textures_max': 20,'building_setback_m': (m.get('building_setback_m') or {}).get('p10') or 12.0,
                  'building_height_m': (m.get('building_height_p90_m') or 12.0) * P['building_height_scale'],
                  'trees_per_km': m.get('tree_models_per_km') or 0.0, 'tree_setback_m': m.get('tree_setback_m') or 12.0,
                  'lamp_model': posts[0]['model'] if posts else None,
                  'lamp_spacing_m': posts[0]['spacing_m'] if posts else None,
                  'lamp_setback_m': posts[0]['setback_m'] if posts else None,
                  'posts': None})
        for k, v in (params or {}).items():
            if k not in P:
                raise E('params: unknown key %r (known: %s)' % (k, ', '.join(sorted(P))))
            P[k] = v
        P['posts'] = self._rta_posts(sty, P.get('posts'))
        probs = STY.validate(dict(sty, defaults={k: P[k] for k in sty['defaults']}))
        if probs:
            raise E('params: %s' % '; '.join(probs))
        sd = P['seed'] if seed is None else seed
        if not (isinstance(sd, int) and not isinstance(sd, bool) and 0 <= sd < 2 ** 31):
            raise E('seed: an integer 0..2^31-1')
        on = {k: True for k in PARTS}
        for k, v in (parts or {}).items():
            if k not in on or not isinstance(v, bool):
                raise E('parts: {lamps, buildings, trees: true / false}')
            on[k] = v
        ex = []
        for r in exclude or []:
            if not (isinstance(r, list) and len(r) == 4 and all(num(v, -1e5, 1e5) for v in r) and r[0] < r[2] and r[1] < r[3]):
                raise E('exclude: rectangles [x0, z0, x1, z1] (x0 < x1, z0 < z1)')
            ex.append([float(v) for v in r])
        return {'style': style, 'style_sha': hashlib.sha256(json.dumps(sty, sort_keys=True).encode()).hexdigest()[:16],
                'points': pts, 'params': P, 'seed': sd, 'parts': on, 'exclude': ex, 'track': (sty.get('source') or {}).get('track')}

    def _rta_posts(self, sty, posts):
        """-> validated post entries [{track, model, side, spacing_m, setback_m, start, texture, source_sha256}].
        None = the style's measured posts: two -> one type per side (outer / inner), one -> both sides. Every entry must be an
        OPAQUE post-shaped instance model (>= 4.5 m tall, <= 1.6 m thick) of a CATALOGUED track of YOUR game data; spacing and
        setback default to that model's own measurement."""
        import re
        import wb_rta_catalog as CAT
        if posts is None:
            pal = sty['palette'].get('posts') or []
            tr = (sty.get('source') or {}).get('track')
            sides = ['outer', 'inner'] if len(pal) >= 2 else ['both']
            posts = [{'track': tr, 'model': p['model'], 'side': sd} for p, sd in zip(pal, sides)] if tr else []
        if not (isinstance(posts, list) and len(posts) <= 8):
            raise E('posts: a list of up to 8 {track, model, side, spacing_m?, setback_m?, start?}')
        out = []
        for i, p in enumerate(posts):
            if not isinstance(p, dict) or set(p) - {'track', 'model', 'side', 'spacing_m', 'setback_m', 'start', 'texture', 'source_sha256'}:
                raise E('posts[%d]: keys track, model, side, spacing_m, setback_m, start' % i)
            if not (isinstance(p.get('track'), str) and re.match(r'^[A-Z]{2}/[A-Z][0-9]_V[0-9]$', p['track'])
                    and isinstance(p.get('model'), str) and re.match(r'^I[0-9]{1,3}$', p['model'])):
                raise E('posts[%d]: track like US/C1_V1 and model like I35' % i)
            if p.get('side', 'both') not in ('both', 'outer', 'inner'):
                raise E("posts[%d]: side 'both', 'outer' or 'inner'" % i)
            try:
                cat = CAT.load(self.cfg, p['track'])
            except CAT.CatalogError as e:
                raise E('posts[%d]: %s' % (i, e))
            m = next((x for x in cat['instance_models'] if x['id'] == p['model']), None)
            if not m:
                raise E('posts[%d]: %s has no instance model %s' % (i, p['track'], p['model']))
            sz = m['size_m']
            if m['render'] != 'opaque' or sz[1] < 4.5 or min(sz[0], sz[2]) > 1.6:
                raise E('posts[%d]: %s %s (%s, %s, %s m) is not an opaque post-shaped model (cut-out models would be solid blocks)' % (
                    i, p['track'], p['model'], m['texture'], m['render'], sz))
            sp = p.get('spacing_m') or m['spacing_m'].get('median') or 40.0
            sb = p.get('setback_m') or m['setback_m'].get('median') or 6.0
            st = p.get('start', 10.0)
            if not (num(sp, 8, 400) and num(sb, 0, 60) and num(st, 0, 200)):
                raise E('posts[%d]: spacing_m 8..400, setback_m 0..60, start 0..200' % i)
            out.append({'track': p['track'], 'model': p['model'], 'side': p.get('side', 'both'), 'spacing_m': round(float(sp), 1),
                        'setback_m': round(float(sb), 1), 'start': float(st), 'texture': m['texture'],
                        'source_sha256': {n: v['sha256'] for n, v in cat['source']['files'].items()}})
        return out

    def rta_post_types(self, tracks=None):
        """every opaque post-shaped instance model of the catalogued tracks (measured size / spacing / setback / placements)"""
        import wb_rta_catalog as CAT
        import os as _os
        idx = json.load(open(_os.path.join(CAT.cat_root(self.cfg), 'INDEX.json'), encoding='utf-8'))
        rows = []
        for r in idx['tracks']:
            if not r.get('ok') or (tracks and r['track'] not in tracks):
                continue
            c = json.load(open(_os.path.join(r['cache'], 'catalogue.json'), encoding='utf-8'))
            for m in c['instance_models']:
                sz = m['size_m']
                if m['render'] == 'opaque' and sz[1] >= 4.5 and min(sz[0], sz[2]) <= 1.6 and (m['placements'] or 0) >= 6:
                    rows.append({'track': r['track'], 'model': m['id'], 'texture': m['texture'], 'size_m': [round(x, 1) for x in sz],
                                 'placements': m['placements'], 'spacing_m': m['spacing_m'].get('median'),
                                 'setback_m': m['setback_m'].get('median'), 'triangles': m['triangles_lod0']})
        return {'ok': True, 'posts': rows, 'note': 'what a model IS (lamp, telegraph pole, sign post) is not decoded: the texture name '
                'and the thumbnail are shown; check before use. Posts from another track are copies from YOUR game data (LOCAL ONLY).',
                'summary_lines': ['%d post-shaped model(s) in %d track(s)' % (len(rows), len({x['track'] for x in rows}))]}

    # ------------------------------------------------------------------ the run (on a clone)
    def _rta_clone(self):
        c = copy.copy(self)
        c.undo_stack, c.redo_stack = [], []
        c.pending, c.pending_meta = dict(self.pending), dict(self.pending_meta)
        return c

    @staticmethod
    def _rta_op(s, opname, **kw):
        pv = s.layout(dict(kw, op=opname + '_preview'))
        return s.layout(dict(kw, op=opname, preview_key=pv['preview_key']))

    def _rta_run(self, req, job):
        sty = STY.load(self.cfg, req['style'])
        pal = sty['palette']
        P = req['params']
        s = self._rta_clone()
        steps, skipped = [], []
        tr = req['track']

        def step(label, frac):
            if job.get('cancel'):
                raise E('cancelled before: %s (nothing changed)' % label)
            job['progress'], job['message'] = frac, label
            job['lines'].append('%5.1f%%  %s' % (100 * frac, label))

        have = set(s.desc().get('materials') or {})
        mats = {}
        for i, (role, (mname, like)) in enumerate(MAT.items()):
            ent = pal.get(role) or (pal.get('verge') if role == 'ground' else None) or (pal.get('wall') if role == 'roof' else None)
            if not ent and role == 'edge':
                ent = pal['road']
            if not ent:
                continue
            if ent.get('material'):                         # ORIGINAL palette: a material of the project itself (no retail copy)
                mats[role] = ent['material']
                continue
            mats[role] = mname
            if mname in have:
                continue
            step('material %s <- %s %s' % (mname, tr, ent['texture']), 0.02 + 0.01 * i)
            self._rta_op(s, 'retail_texture', track=tr, texture=ent['texture'], name=mname, like=like)
            have.add(mname)
        facades = []
        P['facade_repeat_m'] = {}
        for i, f in enumerate((pal.get('facades') or [])[:3]):
            if f.get('material'):
                facades.append(f['material'])
                continue
            mname = 'rs_facade%d' % (i + 1)
            if f.get('repeat_m'):
                P['facade_repeat_m'][mname] = f['repeat_m']
            facades.append(mname)
            if mname not in have:
                step('material %s <- %s %s' % (mname, tr, f['texture']), 0.1)
                self._rta_op(s, 'retail_texture', track=tr, texture=f['texture'], name=mname, like='wall')
                have.add(mname)
        sloped = len({round(p[1], 3) for p in req['points']}) > 1
        step('route (race layout, %d control points, %s)' % (len(req['points']), 'sloped' if sloped else 'level'), 0.15)
        prof = {'sloped': True, 'widths': [P['road_width_m']] * len(req['points'])} if sloped else None
        kw = dict(points=req['points'], replace='all', checkpoints=4, width=P['road_width_m'], material=mats['road'],
                  wall_mat=mats['wall'], back_mat=mats['wallback'], verge_mat=mats.get('ground', mats['verge']),
                  verge_out=min(60.0, P['band_m']), verge_in=P['verge_in_m'], wall_height=P['wall_height_m'])
        if prof:
            kw['profile'] = prof
        ladder = [(kw['verge_out'], kw['verge_in'])] + [(o, i) for o, i in ((kw['verge_out'], 8.0), (min(kw['verge_out'], 35.0), 8.0),
                                                                             (min(kw['verge_out'], 25.0), 8.0), (15.0, 8.0))
                                                         if (o, i) != (kw['verge_out'], kw['verge_in'])]
        for k, (vo, vi) in enumerate(ladder):           # wide verges fold on tight curves: step down, every refusal recorded
            kw['verge_out'], kw['verge_in'] = vo, vi
            try:
                self._rta_op(s, 'race_layout', **kw)
                break
            except T['EditError'] as ex:
                if k == len(ladder) - 1:
                    raise
                skipped.append({'part': 'route', 'skipped': 'verges outer %.0f / inner %.0f m refused (%s); trying smaller verges' % (
                    vo, vi, str(ex)[:160])})
        steps.append('race_layout (ground = verges: outer %.0f m, inner %.0f m)' % (kw['verge_out'], kw['verge_in']))
        e = pal.get('edge') or {}
        step('road lanes (measured repeats: lane %.2f x %.2f m, edge %.2f m)' % (pal['road']['along_m'], pal['road']['across_m'],
                                                                                  e.get('across_m') or P['edge_width_m']), 0.3)
        self._rta_op(s, 'road_lanes', edge_material=mats['edge'], edge_width=min(P['edge_width_m'], P['road_width_m'] / 4),
                     main_u_m=round(pal['road']['along_m'], 2), main_v_m=round(pal['road']['across_m'], 2),
                     edge_u_m=round(e.get('along_m') or pal['road']['along_m'], 2))
        steps.append('road_lanes')
        step('streaming settings (decimate 0.3, drop_below 12)', 0.35)
        try:
            self._rta_op(s, 'streaming_settings', lod_mode='decimate', e_max=0.3, pvs_mode='all', drop_below=12.0)
            steps.append('streaming_settings')
        except T['EditError'] as ex:
            skipped.append({'part': 'streaming', 'skipped': 'decimate settings refused (%s); identity LOD kept' % str(ex)[:160]})
        st = s.desc()['stations']
        xs, zs = [q['p'][0] for q in st], [q['p'][2] for q in st]
        band = P['band_m']
        area = [round(min(xs) - band, 1), round(min(zs) - band, 1), round(max(xs) + band, 1), round(max(zs) + band, 1)]
        lamps_id = []
        if req['parts']['lamps'] and P['lamp_density'] > 0:
            for i, ps in enumerate(P['posts'] or []):
                sp = max(8.0, min(200.0, ps['spacing_m'] / P['lamp_density']))
                off = max(0.5, min(20.0, ps['setback_m'] - P['road_width_m'] / 2 - P['wall_thick_m']))
                step('roadside posts %d: %s %s (%s) on the %s side every %.0f m from %.0f m, %.1f m beyond the wall (measured setback '
                     '%.1f m)' % (i + 1, ps['track'], ps['model'], ps.get('texture'), ps['side'], sp, ps['start'], off, ps['setback_m']),
                     0.5 + 0.02 * i)
                c0 = set(s.constructs())
                try:
                    self._rta_op(s, 'retail_lamps', track=ps['track'], model=ps['model'], spacing=round(sp, 1), side=ps['side'],
                                 offset=round(off, 2), start=float(ps['start']), double_sided=True)
                    lamps_id += sorted(set(s.constructs()) - c0)
                    steps.append('retail_lamps %s %s %s' % (ps['track'], ps['model'], ps['side']))
                except T['EditError'] as ex:
                    skipped.append({'part': 'lamps', 'skipped': 'posts %s %s not placed: %s' % (ps['track'], ps['model'], str(ex)[:260])})
        gen = {'gen': 'g%s' % hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:8], 'style': req['style'],
               'style_sha': req['style_sha'], 'track': tr, 'seed': req['seed'], 'area': area, 'exclude': req['exclude'],
               'te2_blocks': ['route_road', 'route_walls', 'route_verges', 'road_lanes'] + (lamps_id or []),
               'params': {k: P[k] for k in sorted(P)}, 'points': req['points'], 'parts': req['parts'],
               'local_only': bool(tr) or bool(P.get('posts')),
               'post_sources': {ps['track']: ps['source_sha256'] for ps in P.get('posts') or []}}          # an original-only style (no game data) produces shareable parts
        if req['parts']['buildings'] and P.get('buildings_source') == 'retail':
            step('retail building pieces from %s (catalogue)' % tr, 0.6)
            gen['pieces'] = s._rta_pick_pieces(tr, P, req['seed'], skipped)
            for tn in sorted({t for pc in gen['pieces'] for t in pc['textures']}):
                mname = 'rp_' + ''.join(ch for ch in tn.lower() if ch.isalnum() or ch == '_')[:21]
                if mname not in (s.desc().get('materials') or {}):
                    self._rta_op(s, 'retail_texture', track=tr, texture=tn, name=mname, like='wall')
        if req['parts']['buildings']:
            step('buildings (seed %d)' % req['seed'], 0.65)
            try:
                r = s._rta_part(gen, 'buildings', st, facades, mats, area, req['exclude'], skipped, None)
            except T['EditError'] as ex:
                r = None
                skipped.append({'part': 'buildings', 'skipped': 'PART NOT GENERATED: %s' % str(ex)[:400]})
            if r:
                steps.append('rta_buildings')
        if req['parts']['trees']:
            step('trees (seed %d)' % req['seed'], 0.8)
            try:
                r = s._rta_part(gen, 'trees', st, facades, mats, area, req['exclude'], skipped, None)
            except T['EditError'] as ex:
                r = None
                skipped.append({'part': 'trees', 'skipped': 'PART NOT GENERATED: %s' % str(ex)[:400]})
            if r:
                steps.append('rta_trees')
        step('capacity report (kit dry run)', 0.9)
        regen = s.regenerate(s.obj_cur)
        cap = regen.get('capacity') or []
        worst_m = max((c['mesh_slot_pct'] for c in cap), default=0)
        worst_l = max((c['lod_slot_pct'] for c in cap), default=0)
        # RTA5: problems against the EFFECTIVE limit (capacity auto: the host ceiling); blocks above the game's default that fit the
        # host are INFO (the package declares them in mod.toml [bmashup.capacity])
        lm = max((c.get('mesh_limit_pct', c['mesh_slot_pct']) for c in cap), default=0)
        ll = max((c.get('lod_limit_pct', c['lod_slot_pct']) for c in cap), default=0)
        problems = []
        if lm > 95 or ll > 95:
            problems.append('a unit is above 95 %% of its %s (mesh %.1f %%, LOD %.1f %%): lower densities or exclude areas' % (
                'host ceiling' if regen.get('capacity_mode') == 'auto' else 'slot', lm, ll))
        rows = len(s.desc().get('rows') or [])
        if rows > 83:
            problems.append('%d material rows > 83 (format limit: one material-table entry per row in every centre block; '
                            'capacity auto does not raise it) - %s' % (rows, _rows_note(s, rows)))
        job['progress'] = 1.0
        return s, {'steps': steps, 'skipped': skipped, 'gen': gen, 'capacity': cap, 'worst_mesh_slot_pct': worst_m,
                   'worst_lod_slot_pct': worst_l, 'rows': rows, 'problems': problems,
                   'capacity_mode': regen.get('capacity_mode', 'game'), 'capacity_info': regen.get('capacity_info', []),
                   'capacity_declare': regen.get('capacity_declare', {}), 'capacity_requires': regen.get('capacity_requires', []),
                   'parts': {k: c['meta'] for k, c in s.constructs().items() if str(c['meta'].get('kind', '')).startswith('rta_')}}

    def _rta_pick_pieces(self, track, P, seed, log):
        """a small deterministic set of retail building pieces of the style's track: roadside (8..80 m from the route), 8..40 m
        long, 6..40 m high, <= 1500 triangles, union of textures <= piece_textures_max (material rows!)"""
        import wb_rta_objects as OB
        o = OB.build(self.cfg, track)
        cands = [p for p in o['pieces'] if p['class'] == 'building' and 8 <= max(p['footprint_m']) <= 40 and min(p['footprint_m']) >= 4
                 and 6 <= p['height_m'] <= 40 and p['triangles'] <= 1500 and (p['route_distance_m'] or 0) >= 8
                 and (p['route_distance_m'] or 999) <= 80]
        rnd = random.Random('p%d' % seed)
        rnd.shuffle(cands)
        out, tex = [], set()
        for p in cands:
            t = set(p['textures'])
            if len(tex | t) > P['piece_textures_max']:
                continue
            tex |= t
            out.append({'track': track, 'id': p['id'], 'textures': sorted(t), 'long': max(p['footprint_m']), 'short': min(p['footprint_m']),
                        'height': p['height_m'], 'long_axis': 'x' if p['footprint_m'][0] >= p['footprint_m'][1] else 'z'})
            if len(out) >= P['piece_limit']:
                break
        if not out:
            log.append({'part': 'buildings', 'skipped': 'no retail building piece of %s fits the rules: generated buildings used' % track})
        return out

    def _rta_piece_faces(self, pc, b, base, mats_of):
        """one retail piece placed in slot b: long axis along the road tangent, centred, base on the ground (faces for _block_bytes)"""
        import wb_rta_objects as OB
        tris = OB.piece_triangles(self.cfg, pc['track'], pc['id'])
        P = [c[0] for _t, _i, cs in tris for c in cs]
        bx = (max(p[0] for p in P) + min(p[0] for p in P)) / 2
        bz = (max(p[2] for p in P) + min(p[2] for p in P)) / 2
        y0 = min(p[1] for p in P)
        tx, tz = b['tangent']
        a_road = math.atan2(tz, tx)
        a_piece = 0.0 if pc['long_axis'] == 'x' else math.pi / 2
        a = a_road - a_piece
        ca, sa = math.cos(a), math.sin(a)
        cx, cz = b['centre']
        faces = []
        for tn, _ti, cs in tris:
            pts = [(round(cx + ca * (q[0] - bx) - sa * (q[2] - bz), 4), round(base + q[1] - y0, 4), round(cz + sa * (q[0] - bx) + ca * (q[2] - bz), 4))
                   for q, _uv, _c in cs]
            ar, n, _c = _tri(pts)
            if ar < 0.006:
                continue
            nn = tuple(round(v, 5) for v in n)
            faces.append((mats_of[tn], [(pts[j], (round(cs[j][1][0], 5), round(cs[j][1][1], 5)), nn,
                                         tuple(round(v, 3) for v in cs[j][2])) for j in range(3)]))
        return faces

    # ------------------------------------------------------------------ one generated part = one construction block
    def _rta_part(self, gen, part, stations, facades, mats, area, exclude, log, replace_id, overrides=None):
        P = dict(gen['params'], **(overrides or {}))
        seed = P.get('part_seed_%s' % part, gen['seed'])
        if part == 'buildings':
            pieces = gen.get('pieces') if P.get('buildings_source') == 'retail' else None
            plan = plan_buildings(stations, P, facades, seed, exclude, area, log, pieces)
            mats_of = {tn: 'rp_' + ''.join(ch for ch in tn.lower() if ch.isalnum() or ch == '_')[:21]
                       for pc in (pieces or []) for tn in pc['textures']}
            faces = []
            C0 = self.constructs()
            excl = set(C0['rta_buildings']['groups']) if 'rta_buildings' in C0 else set()
            kept = []
            for b in plan:
                ops = [{'edge': b['door_edge'], 'width': 3.2, 'height': 2.8}] if b['door_edge'] is not None else []
                cx_, cz_ = b['centre']
                gys = [self._ground_y(x + 0.06 * (x - cx_), z + 0.06 * (z - cz_), excl) for x, z in b['footprint']]   # ~0.5 m margin
                if any(g is None for g in gys):
                    log.append({'part': 'buildings', 'at': b['centre'], 'skipped': 'no collision floor under every corner'})
                    continue
                if max(gys) - min(gys) > 0.5:
                    log.append({'part': 'buildings', 'at': b['centre'], 'skipped': 'ground under the corners differs by %.2f m (> 0.5)' % (max(gys) - min(gys))})
                    continue
                if b.get('piece') is not None:              # a retail building piece in this slot (geometry copy)
                    faces += self._rta_piece_faces(pieces[b['piece']], b, round(min(gys) - 0.05, 4), mats_of)
                    kept.append(b)
                    continue
                try:
                    req = self._bldg_req(b['footprint'], round(min(gys) - 0.05, 4), False, b['height'], b['facade'],
                                         mats.get('roof', b['facade']), 'flat', 2.0, ops, 0.0, 6.0, 'keep', None)
                    f, _info = tb.building_faces([tuple(p) for p in req['footprint']], req['base'], req['height'], req['wall_material'],
                                                 req['roof_material'], 'flat', 2.0, req['openings'], 0.0,
                                                 float((P.get('facade_repeat_m') or {}).get(b['facade']) or 6.0))
                except T['EditError'] as ex:
                    log.append({'part': 'buildings', 'at': b['centre'], 'skipped': str(ex)[:200]})
                    continue
                except Exception as ex:  # noqa: BLE001   wc.ConstructError
                    log.append({'part': 'buildings', 'at': b['centre'], 'skipped': 'refused: %s' % ex})
                    continue
                faces += f
                kept.append(b)
            plan = kept
            kind, n_items = 'building', len(plan)
        else:
            blds = []
            C = self.constructs()
            bid = 'rta_buildings'
            if bid in C:
                blds = [{'footprint': fp} for fp in C[bid]['meta'].get('footprints', [])]
            plan = plan_trees(stations, P, seed, exclude, area, blds, log)
            faces = []
            trunk, fol = mats.get('wallback', 'rs_wallback'), mats.get('foliage', mats.get('verge'))
            for t in plan:
                g = self._ground_y(t['position'][0], t['position'][2])
                rr = t['radius'] + 0.75
                rim = [self._ground_y(t['position'][0] + dx, t['position'][2] + dz) for dx, dz in ((rr, 0), (-rr, 0), (0, rr), (0, -rr))]
                if g is None or any(y is None for y in rim):
                    log.append({'part': 'trees', 'at': t['position'], 'skipped': 'no ground under the whole crown (edge of the '
                                                                             'generated ground / unit regions)'})
                    continue
                pos = [t['position'][0], round(g - 0.05, 4), t['position'][2]]
                faces += tb.tree_faces(pos, t['height'], t['radius'], t['sides'], trunk, fol, 4.0)
            kind, n_items = 'tree', len(plan)
        if not faces:
            log.append({'part': part, 'skipped': 'nothing to place (density 0, no room, or every candidate refused)'})
            return None
        bid = 'rta_' + part
        C = self.constructs()
        repl = C[bid]['groups'] if bid in C else []
        meta = {'kind': 'rta_' + part, 'id': bid, 'gen': gen['gen'], 'style': gen['style'], 'style_sha': gen['style_sha'],
                'track': gen['track'], 'seed': seed, 'items': n_items, 'locked': False, 'faces_sha': faces_sha(faces),
                'overrides': overrides or {}, 'exclude': exclude, 'local_only': gen.get('local_only', True),
                'note': 'retail-style generated part (wb_rta_gen): regenerate replaces only this block'}
        meta['gen_record'] = gen                         # every generated part carries the generation record (recipes, regenerate)
        if part == 'buildings':
            meta['footprints'] = [b['footprint'] for b in plan]
        meta['faces_sha'] = 'pending'
        after, blk = self._block_bytes(faces, meta, repl)
        label = '%s %s (%d items, %d faces)' % ('regenerate' if repl else 'generate', bid, n_items, len(faces))
        r = self._apply_block({'after': after, 'blk': blk, 'planned': faces}, label, kind, len(faces))
        # the block passed the editor's exact checks as planned; its tag now records the hash of the faces AS WRITTEN, folded
        # into the SAME undo entry (only the tag line changes; faces untouched)
        u = self.undo_stack[-1]
        new = self._rta_tag_rewrite(bid, {'faces_sha': self._rta_block_sha(self.obj_cur, bid)})
        u['after'] = new
        self.obj_cur = new
        return r

    # ------------------------------------------------------------------ jobs (background, cancellable)
    def _rta_jobs(self):
        """background jobs of THIS editor session (a clone shares the dict; only the main object starts jobs)"""
        return self.__dict__.setdefault('_rta_jobs_d', {})

    def _rta_job(self, kind, fn):
        JOBS = self._rta_jobs()
        for j in JOBS.values():
            if j['state'] == 'running':
                raise E('a generation job is already running (%s): wait or cancel it' % j['id'])
        jid = 'j%d' % (len(JOBS) + 1)
        job = {'id': jid, 'kind': kind, 'state': 'running', 'progress': 0.0, 'message': 'starting', 'lines': [], 'started': time.time()}
        JOBS[jid] = job

        def run():
            try:
                job['result'] = fn(job)
                job['state'] = 'done'
            except T['EditError'] as ex:
                job['state'] = 'cancelled' if job.get('cancel') else 'refused'
                job['error'] = str(ex)
            except Exception as ex:  # noqa: BLE001   reported, never hidden
                job['state'] = 'failed'
                job['error'] = '%s: %s' % (type(ex).__name__, ex)
            job['seconds'] = round(time.time() - job['started'], 2)
        th = threading.Thread(target=run, daemon=True)
        job['thread'] = th
        th.start()
        return {'ok': True, 'job': jid}

    def rta_job_status(self, job=None, wait=0.0):
        j = self._rta_jobs().get(job)
        if not j:
            raise E('job %r does not exist' % (job,))
        if wait and j['state'] == 'running':
            j['thread'].join(min(float(wait), 30.0))
        out = {k: v for k, v in j.items() if k not in ('thread', 'clone', 'result', 'state')}
        out['job_state'] = j['state']          # not 'state': the editor server adds its own 'state' to every reply
        if 'result' in j:
            out['result'] = j['result']
        return dict(out, ok=True)

    def rta_job_cancel(self, job=None):
        j = self._rta_jobs().get(job)
        if not j:
            raise E('job %r does not exist' % (job,))
        j['cancel'] = True
        return {'ok': True, 'job': job, 'note': 'cancel requested: the job stops before its next step; nothing is changed'}

    # ------------------------------------------------------------------ public operations
    def rta_styles(self):
        rows = STY.list_presets(self.cfg)
        for r in rows:
            try:
                _c, why = STY.check_source(self.cfg, STY.load(self.cfg, r['id']))
            except STY.StyleError as e:
                why = str(e)
            r['usable'] = not why and not r['problems']
            r['why_not'] = why
        return {'ok': True, 'styles': rows, 'summary_lines': ['%d style preset(s); %d usable with your game data' % (
            len(rows), sum(1 for r in rows if r['usable']))]}

    def rta_generate_preview(self, style=None, points=None, route_text=None, params=None, parts=None, exclude=None, seed=None):
        """starts a background job: the whole generation on a clone; the project is NOT changed. Poll rta_job_status."""
        req = self._rta_req(style, points, route_text, params, parts, exclude, seed)
        base = self.content_sha()

        def fn(job):
            clone, rep = self._rta_run(req, job)
            key = hashlib.sha256(('%s|%s' % (base, json.dumps(req, sort_keys=True))).encode()).hexdigest()[:16]
            job['clone'] = clone
            job['key'] = key
            return dict(rep, preview_key=key, base=base, request=req,
                        summary_lines=['preview: %d steps, %d skipped placements, worst unit mesh %.1f %% / LOD %.1f %%, %d rows%s' % (
                            len(rep['steps']), len(rep['skipped']), rep['worst_mesh_slot_pct'], rep['worst_lod_slot_pct'], rep['rows'],
                            '; PROBLEMS: ' + '; '.join(rep['problems']) if rep['problems'] else '')])
        return self._rta_job('preview', fn)

    def rta_generate(self, job=None, preview_key=None):
        """apply a finished preview job as ONE undo step (buffer 'all')"""
        j = self._rta_jobs().get(job)
        if not j or j.get('state') != 'done' or j.get('kind') != 'preview':
            raise E('NEEDS PREVIEW: run the preview job to the end first')
        if preview_key != j.get('key'):
            raise E('preview_key does not match that job')
        if self.content_sha() != j['result']['base']:
            raise E('the project changed after the preview: preview again (nothing changed)')
        if j['result']['problems']:
            raise E('refused: the preview has problems (%s); change the settings and preview again' % '; '.join(j['result']['problems']))
        c = j.pop('clone')
        after = (c.cur, c.obj_cur, dict(c.pending), dict(c.pending_meta))
        label = 'retail-style generation %s (%s, seed %d, %d steps)' % (j['result']['gen']['gen'], j['result']['gen']['style'],
                                                                         j['result']['gen']['seed'], len(j['result']['steps']))
        self._push('all', label, after, kind='rta_generate', index=j['result']['gen']['gen'])
        j['state'] = 'applied'
        return {'ok': True, 'label': label, 'summary_lines': [label + ': ONE undo step; Save writes it; every part stays editable']}

    def rta_parts(self):
        out = []
        for bid, c in self.constructs().items():
            m = c['meta']
            if not str(m.get('kind', '')).startswith('rta_'):
                continue
            cur = self._rta_faces_sha(c)
            out.append({'id': bid, 'kind': m['kind'], 'items': m.get('items'), 'seed': m.get('seed'), 'locked': m.get('locked'),
                        'style': m.get('style'), 'gen': m.get('gen'), 'faces': c['faces'],
                        'manually_edited': cur != m.get('faces_sha'), 'overrides': m.get('overrides'), 'exclude': m.get('exclude')})
        return {'ok': True, 'parts': out, 'summary_lines': ['%d generated part(s)%s' % (len(out), ''.join(
            '; %s %s%s' % (p['id'], 'LOCKED ' if p['locked'] else '', 'EDITED' if p['manually_edited'] else '') for p in out))]}

    def _rta_faces_sha(self, c):
        return self._rta_block_sha(self.obj_cur, c['meta']['id'])

    def _rta_block_sha(self, obj, bid):
        """order-independent hash of a block's faces as written in OBJ bytes (material + resolved corner positions)"""
        lines, groups, vl = T['obj_index'](obj)
        C = self.constructs(obj)
        vtxt = [lines[li] for li in vl]
        rows = []
        for g in C[bid]['groups']:
            x = groups[g]
            mat = x['mat'].decode() if isinstance(x['mat'], bytes) else str(x['mat'])
            for li in x['faces']:
                cs = []
                for t in lines[li].split()[1:]:
                    k = int(t.split(b'/')[0])
                    xyz = vtxt[k - 1 if k > 0 else len(vtxt) + k].split()[1:4]
                    cs.append(' '.join('%.2f' % float(v) for v in xyz))
                rows.append(mat + '|' + ';'.join(cs))
        return hashlib.sha256('|'.join(sorted(rows)).encode()).hexdigest()[:16]

    def _rta_tag_rewrite(self, bid, changes, obj=None):
        """the block's tag lines rewritten with changed metadata (faces untouched) -> OBJ bytes"""
        obj = self.obj_cur if obj is None else obj
        lines, groups, _v = T['obj_index'](obj)            # lines keep their line ends
        lines = list(lines)
        C = self.constructs(obj)
        meta = dict(C[bid]['meta'], **changes)
        new = self.TAG + json.dumps(meta, separators=(',', ':'), sort_keys=True).encode('ascii')
        for g in C[bid]['groups']:
            li = groups[g]['line'] + 1
            old = lines[li]
            end = old[len(old.rstrip(b'\r\n')):]
            lines[li] = new + end
        return b''.join(lines)

    def rta_part_lock(self, part=None, locked=True):
        C = self.constructs()
        if part not in C or not str(C[part]['meta'].get('kind', '')).startswith('rta_'):
            raise E('part %r is not a generated part (rta_parts lists them)' % (part,))
        if not isinstance(locked, bool):
            raise E('locked: true / false')
        after = self._rta_tag_rewrite(part, {'locked': locked})
        self._push('obj', '%s %s' % ('lock' if locked else 'unlock', part), after, kind='rta_lock', index=part)
        return {'ok': True, 'summary_lines': ['%s %s (one undo step)' % ('locked' if locked else 'unlocked', part)]}

    def rta_part_regenerate(self, part=None, seed=None, overrides=None, exclude=None, confirm=False):
        """regenerate ONE generated part (buildings / trees) with a new seed / overrides / exclusion areas; other parts untouched"""
        C = self.constructs()
        if part not in C or C[part]['meta'].get('kind') not in ('rta_buildings', 'rta_trees'):
            raise E('part %r: rta_buildings or rta_trees' % (part,))
        m = C[part]['meta']
        if m.get('locked'):
            raise E('%s is LOCKED: unlock it first (nothing changed)' % part)
        if self._rta_faces_sha(C[part]) != m.get('faces_sha') and confirm is not True:
            raise E('%s was edited by hand since it was generated: regenerating replaces those edits - repeat with confirm: true '
                    '(nothing changed)' % part)
        rec = m.get('gen_record') or (C.get('rta_buildings') or {}).get('meta', {}).get('gen_record')
        if not rec:
            raise E('no generation record found (rta_buildings carries it): regenerate the whole layout instead')
        ov = dict(m.get('overrides') or {}, **(overrides or {}))
        allowed = set(rec['params']) | {'facades'}
        bad = sorted(k for k in set(ov) - allowed if not k.startswith('part_seed_'))
        if bad:
            raise E('overrides: unknown key(s) %s' % ', '.join(bad))
        if seed is not None:
            if not (isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < 2 ** 31):
                raise E('seed: an integer 0..2^31-1')
            ov['part_seed_%s' % part[4:]] = seed
        ex = m.get('exclude') or [] if exclude is None else exclude
        mats = {r: n for r, (n, _l) in MAT.items() if n in (self.desc().get('materials') or {})}
        facades = ov.pop('facades', None) or sorted(k for k in (self.desc().get('materials') or {}) if k.startswith('rs_facade'))
        log = []
        r = self._rta_part(rec, part[4:], self.desc()['stations'], facades, mats, rec['area'], ex, log, part, ov)
        if r is None:
            raise E('%s: nothing could be placed with these settings (%d refusals); nothing changed' % (part, len(log)))
        return dict(r, skipped=log, summary_lines=['%s regenerated (one undo step); %d placements skipped' % (part, len(log))])

    RTA_LAYOUT = {'rta_post_types': 'rta_post_types', 'rta_styles': 'rta_styles', 'rta_generate_preview': 'rta_generate_preview', 'rta_generate': 'rta_generate',
                  'rta_job_status': 'rta_job_status', 'rta_job_cancel': 'rta_job_cancel', 'rta_parts': 'rta_parts',
                  'rta_part_lock': 'rta_part_lock', 'rta_part_regenerate': 'rta_part_regenerate'}
