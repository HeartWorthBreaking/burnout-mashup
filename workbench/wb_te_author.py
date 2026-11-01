"""wb_te_author - track-editor authoring queue (gp\\workbench_te, 2026-11-01): the editor operations of queue stages 1-9 as a
mixin of wb_trackedit.TrackSource. Every operation follows the editor's rules: preview (nothing changes) -> apply with the
preview's key; exact re-read of what was written; the v0.19 clip rule; the kit trackbuild build_units dry run; ONE undo entry;
a refusal leaves both buffers unchanged. Retail data is never edited (RetailSource has none of these).

wb_trackedit calls bind(globals()) once, so this module uses its EditError / obj_index / desc_splice without an import cycle.
"""
import hashlib
import json
import math

import wb_construct as wc
import wb_te_geom as tg

T = {}                                          # wb_trackedit globals (bind)
VERSION = '0.31'                                # the authoring queue's editor version (wb_core.VERSION follows)
# block kinds whose faces may cross unit cuts with the kit clipper's 4-decimal rounding slivers (< 0.00005 m x perimeter,
# reported as cut_rounding_slivers_m2), as terrain / barrier / prefab since v0.26; roads of v0.24 keep the strict rule
ROUND_TOL_KINDS = ('proad', 'hterrain', 'junction', 'join', 'scatter')


def bind(g):
    T.update(g)


def E(msg, detail=None):
    e = T['EditError'](msg)
    if detail is not None:
        e.detail = detail
    return e


def num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


PROVENANCE = 'editor_provenance.json'           # project-level record of imported source files (written at Save)


def _tmpdir(src):
    import os
    import tempfile
    root = os.path.join(src.cfg['state'], 'geomcheck')
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix='tex_', dir=root)


def png_alpha_bytes(src, b):
    """the kit reader's (w, h, rows, min alpha) of PNG bytes (through a temporary file: the kit reads paths)"""
    import os
    import shutil
    K = T['kit_trackbuild'](src.cfg)
    d = _tmpdir(src)
    try:
        p = os.path.join(d, 'x.png')
        with open(p, 'wb') as f:
            f.write(b)
        return K['io'].read_png_alpha(p)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def write_pending(src):
    """Save step 1 (TE stage 5): write the pending imported files (new files only; identical bytes on disk = nothing to do) and
    merge their provenance into PROVENANCE. -> [(rel, path, old bytes or None)] for rollback_pending"""
    import os
    import time
    if not src.pending:
        return []
    for rel, b in src.pending.items():
        p = os.path.join(src.project, *rel.split('/'))
        if os.path.exists(p) and open(p, 'rb').read() != b:
            raise T['EditError']('save refused: %s exists on disk with other bytes (imports never overwrite project files); the '
                                 'project is unchanged, the edits are kept (unsaved)' % rel)
    done = []
    try:
        for rel, b in sorted(src.pending.items()):
            p = os.path.join(src.project, *rel.split('/'))
            if os.path.exists(p):
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p + '.wb_tmp', 'wb') as f:
                f.write(b)
            os.replace(p + '.wb_tmp', p)
            done.append((rel, p, None))
        pp = os.path.join(src.project, PROVENANCE)
        old = open(pp, 'rb').read() if os.path.isfile(pp) else None
        rec = json.loads(old.decode('utf-8')) if old else {'format': 'workbench-provenance 1', 'files': {}}
        for rel in sorted(src.pending):
            if rel in src.pending_meta:
                rec['files'][rel] = dict(src.pending_meta[rel], saved=time.strftime('%Y-%m-%d %H:%M:%S'))
        with open(pp + '.wb_tmp', 'wb') as f:
            f.write(json.dumps(rec, indent=1, sort_keys=True).encode('utf-8') + b'\n')
        os.replace(pp + '.wb_tmp', pp)
        done.append((PROVENANCE, pp, old))
    except OSError as e:
        rollback_pending(src, done)
        raise T['EditError']('save failed while writing an imported file (%s): nothing kept; the edits are kept (unsaved)' % e)
    return done


def rollback_pending(src, done):
    import os
    for _rel, p, old in reversed(done):
        try:
            if old is None:
                os.remove(p)
            else:
                with open(p + '.wb_tmp', 'wb') as f:
                    f.write(old)
                os.replace(p + '.wb_tmp', p)
        except OSError:
            pass


def _backup_root(src):
    import os
    return os.path.join(src.cfg['state'], 'backups', hashlib.sha256(os.path.normcase(src.project).encode('utf-8')).hexdigest()[:12])


def backup_before_save(src):
    """Save step 0 (TE stage 9): copy the description / OBJ as they are ON DISK now (the previous save) into Workbench state
    (backups/<project id>/<time>/ + MANIFEST.json). Never inside the project; never deleted by the editor."""
    import os
    import time
    root = _backup_root(src)
    stamp = time.strftime('%Y%m%d_%H%M%S') + '_%06d' % int((time.time() % 1) * 1e6)
    d = os.path.join(root, stamp)
    os.makedirs(d, exist_ok=False)
    files = {}
    for rel, path in ((src.desc_rel, src.desc_path), (src.obj_rel, src.obj_path)):
        if rel and path and os.path.isfile(path):
            b = open(path, 'rb').read()
            dst = os.path.join(d, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as f:
                f.write(b)
            files[rel] = hashlib.sha256(b).hexdigest()
    with open(os.path.join(d, 'MANIFEST.json'), 'wb') as f:
        f.write(json.dumps({'format': 'workbench-backup 1', 'project': src.project, 'time': stamp, 'reason': 'before save',
                            'files': files}, indent=1, sort_keys=True).encode('utf-8'))
    return d


class AuthorMixin:
    # ================================================================== stage 1: road design
    START_FLAT_BACK, START_FLAT_AHEAD = 45.0, 30.0       # the grid (12..32 m back) + rolling start must stay level (kit 0.3.0 README)

    def _race_geom_profile(self, req):
        """the race layout of a profile request: sloped centre line (the curve's y), per-control-point widths, banks limited to the
        kit's V2 tolerance, declared outer-wall gaps -> the same tuple as the v0.25 geometry"""
        P, t = req['points'], req['wall_thick']
        pr = req['profile']
        if pr['sloped'] and len({p[1] for p in P}) > 1 and self.tb_version() < (0, 3, 0):
            raise wc.ConstructError('a sloped route needs trackbuild 0.3.0 or later (the bound trackbuild is %s: its V2 gates compare '
                                    'every floor sample and wall probe with the height of station 0). Bind 0.3.0 (Workbench setting '
                                    '"trackbuild") or keep the control points at one height' % '.'.join(map(str, self.tb_version())))
        sps = 3
        _S, L = wc.sample(P, True, step=2.0)
        spu = sps * max(1, int(round(L / (req['n_units'] * 2.0 * sps))))
        n = req['n_units'] * spu
        S, pars, L = tg.sample_param(P, True, count=n)
        if not pr['sloped']:
            S = [[p[0], P[0][1], p[2]] for p in S]
        else:                                               # monotone elevation: no overshoot of the control heights
            S = [[p[0], y, p[2]] for p, y in zip(S, tg.monotone_y(P, True, pars))]
        S = [[p[0], round(p[1], 4), p[2]] for p in S]
        T_ = wc.tangents(S, True)
        hws = [w / 2 for w in tg.interp_profile(pr['widths'], pars, True, 'widths')] if pr['widths'] else [req['width'] / 2] * n
        banks = tg.interp_profile(pr['banks'], pars, True, 'banks') if pr['banks'] else [0.0] * n
        # start stretch level (the start grid is written level; kit 0.3.0 README)
        y0 = S[0][1]
        ds = L / n
        bad = [i for i in range(n) if (i * ds <= self.START_FLAT_AHEAD or (n - i) * ds <= self.START_FLAT_BACK) and
               (abs(S[i][1] - y0) > 1e-4 or abs(banks[i]) > 1e-9)]
        if bad:
            raise wc.ConstructError('the start stretch must be level and unbanked (%.0f m before .. %.0f m after control point 0: the '
                                    'grid and start line are written level - kit 0.3.0 README); station(s) %s differ: keep the '
                                    'control points near point 0 at one height and bank 0' % (self.START_FLAT_BACK,
                                                                                               self.START_FLAT_AHEAD, bad[:6]))
        # banks: the kit's V2 gate (floor within 0.05 m of the route height wall to wall) bounds a drivable route's bank
        lim = [tg.v2_bank_limit(-hws[i], hws[i]) for i in range(n)]
        over = [i for i in range(n) if abs(banks[i]) > lim[i] + 1e-9]
        if over:
            i = max(over, key=lambda k: abs(banks[k]) - lim[k])
            raise wc.ConstructError('bank %.2f deg at station %d exceeds what the kit gate V2_drivable_coverage accepts on a drivable '
                                    'route of %.1f m (about %.2f deg: every floor sample wall to wall must stay within 0.05 m of the '
                                    'route height; the editor keeps 0.04 m). Bank off-route roads with the road tool, or keep the route '
                                    'within the limit (gate not loosened)' % (banks[i], i, 2 * hws[i], lim[i]))
        road, _len = tg.profiled_strip(S, T_, True, hws, banks, req['material'], 14.0)
        reach = [[-(h + t + req['verge_out']) for h in hws], [h + t + req['verge_in'] for h in hws]]
        for offs in reach:
            for i in range(n):
                a, b = wc.offset_pt(S[i], T_[i], offs[i]), wc.offset_pt(S[(i + 1) % n], T_[(i + 1) % n], offs[(i + 1) % n])
                if (b[0] - a[0]) * T_[i][0] + (b[2] - a[2]) * T_[i][1] <= 0:
                    raise wc.ConstructError('the strip edge at lateral %.1f m folds over at station %d: use smaller verges / width or '
                                            'a wider curve' % (offs[i], i))
            x = wc.self_intersections([list(wc.offset_pt(S[i], T_[i], offs[i])) for i in range(n)], True)
            if x:
                raise wc.ConstructError('a strip edge crosses itself (segments %s): smaller verges or control points further apart' % x[:2])
        gaps = pr['outer_gaps']
        for a, b in gaps:
            if b >= n:
                raise wc.ConstructError('outer gap [%d, %d]: stations 0..%d' % (a, b, n - 1))
            if a * ds <= self.START_FLAT_AHEAD or (n - b) * ds <= self.START_FLAT_BACK:
                raise wc.ConstructError('outer gap [%d, %d] lies in the start stretch: refused' % (a, b))
        # the wall opens over the steps a .. b-1 (station a to station b); the kit skips its probes at stations a-1 .. b, so every
        # probe outside lands inside a wall face (a probe exactly on a wall's end edge can miss: found by test_te32 j01)
        ingap = lambda i: any(a <= i < b for a, b in gaps)  # noqa: E731
        wl = tg.wall_strip_var(S, T_, True, [-h for h in hws], -1, req['wall_height'], t, req['wall_mat'], req['back_mat'], banks)
        wr = tg.wall_strip_var(S, T_, True, list(hws), 1, req['wall_height'], t, req['wall_mat'], req['back_mat'], banks)
        walls, wstep = [], []
        for j, f in enumerate(wl):
            if not ingap(j // 3):
                walls.append(f)
                wstep.append(j // 3)
        for j, f in enumerate(wr):
            walls.append(f)
            wstep.append(j // 3)
        verges, vstep = [], []
        if req['verge_out'] > 0:
            for i, f in enumerate(tg.verge_strip_var(S, T_, True, [-(h + t + req['verge_out']) for h in hws], [-(h + t) for h in hws],
                                                     req['verge_mat'], banks)):
                if not ingap(i):
                    verges.append(f)
                    vstep.append(i)
        if req['verge_in'] > 0:
            for i, f in enumerate(tg.verge_strip_var(S, T_, True, [h + t for h in hws], [h + t + req['verge_in'] for h in hws],
                                                     req['verge_mat'], banks)):
                verges.append(f)
                vstep.append(i)
        stations = []
        for i in range(n):
            h = hws[i]
            offs = [round(-(h + t + req['verge_out']), 4), round(-h, 4), round(-(h - 1.0), 4), round(h - 1.0, 4), round(h, 4),
                    round(h + t + req['verge_in'], 4)]
            stations.append({'p': [round(S[i][0], 4), S[i][1], round(S[i][2], 4)], 't': [round(T_[i][0], 6), round(T_[i][1], 6)],
                             'offsets': offs})
        corners = wc.heading_corners(S, T_, sps, n // sps)
        start, grid, cps = wc.start_objects(S, L, y0, req['checkpoints'])
        for c in cps:                                       # checkpoints at their station's own height (sloped route)
            i = min(range(n), key=lambda k: (S[k][0] - c['pos'][0]) ** 2 + (S[k][2] - c['pos'][2]) ** 2)
            c['pos'][1] = S[i][1]
        import collections
        per = collections.defaultdict(list)
        for i, (_m, cs) in enumerate(road):
            per[i] += [(c[0][0], c[0][2]) for c in cs]
        for st_, (_m, cs) in zip(wstep, walls):
            per[st_] += [(c[0][0], c[0][2]) for c in cs]
        for st_, (_m, cs) in zip(vstep, verges):
            per[st_] += [(c[0][0], c[0][2]) for c in cs]
        units = []
        for k in range(req['n_units']):
            a, b = k * spu, ((k + 1) * spu) % n
            pts = [q for i in range(a, a + spu) for q in per[i]]
            lat, m = wc.fit_lateral(stations, a, b, pts)
            units.append({'cut_from': a, 'cut_to': b, 'lateral': lat, 'chord_normal': m})
        xs = tg.cross_sections(S, T_, hws, banks, True)
        warns, worst = tg.continuity_warnings(xs, True)
        self._prof_info = {'profile': {'sloped': pr['sloped'], 'widths': pr['widths'], 'banks': pr['banks'], 'outer_gaps': gaps},
                           'elevation_m': [round(min(p[1] for p in S), 3), round(max(p[1] for p in S), 3)],
                           'width_m': [round(2 * min(hws), 3), round(2 * max(hws), 3)],
                           'bank_deg': [round(min(banks), 3), round(max(banks), 3)],
                           'v2_bank_limit_deg': round(min(lim), 3), 'continuity': worst, 'continuity_warnings': warns,
                           'cross_sections': xs[::max(1, len(xs) // 120)], 'min_half_width': min(hws)}
        return S, T_, road, walls, verges, stations, corners, start, grid, cps, units, L, n, spu

    def _race_values_profile(self, req, values, stations):
        v = dict(values)
        v['wall_gaps'] = [list(g) for g in req['profile']['outer_gaps']]
        if req['traffic']:                                  # traffic lanes must fit the narrowest road
            v['traffic'] = wc.traffic_for(len(stations), self._prof_info['min_half_width'])
        return v

    def _race_profile_summary(self, req):
        i = dict(self._prof_info)
        i.pop('min_half_width', None)
        lines = ['profile: elevation %s m, width %s m, bank %s deg (V2 route bank limit %.2f deg), outer wall gaps %s' % (
            i['elevation_m'], i['width_m'], i['bank_deg'], i['v2_bank_limit_deg'], i['profile']['outer_gaps'] or 'none')]
        lines += ['WARNING: ' + w for w in i['continuity_warnings']]
        if i['profile']['outer_gaps']:
            lines.append('outer wall gaps are DECLARED in wall_gaps (the kit skips its wall probe there; trackbuild calls it the '
                         'crash-test variant): cars can leave the route there - runtime behaviour unproven')
        return dict(i, profile_lines=lines)

    def tb_version(self):
        """the bound trackbuild tree's VERSION (trackbuild/__init__.py, read as text; never imported here)"""
        import os
        import re
        import wb_core as core
        p = os.path.join(core.trackbuild_dir(self.cfg), 'trackbuild', '__init__.py')
        try:
            m = re.search(r'^VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', open(p, encoding='utf-8').read(), re.M)
        except OSError:
            m = None
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

    # ---------------- profiled roads (off-route or decorative; any bank)
    def _proad_req(self, points, closed, widths, banks, material, uv_len, step, road):
        if not isinstance(closed, bool):
            raise E('closed must be true or false')
        try:
            P = wc.check_points(points, closed)
            W = tg.check_profile(widths, len(P), 'widths', 2, 60)
            B = tg.check_profile(banks if banks is not None else [0.0] * len(P), len(P), 'banks', -45, 45)
        except wc.ConstructError as e:
            raise E('road refused: %s' % e)
        if not num(uv_len, 0.5, 200):
            raise E('uv length %r refused: 0.5..200 m per texture repeat' % (uv_len,))
        if not num(step, 0.5, 20):
            raise E('step %r refused: 0.5..20 m between cross-sections' % (step,))
        self._mat_ok(material, 'road')
        if road is not None:
            C = self.constructs()
            if road not in C or C[road]['meta'].get('kind') != 'road':
                raise E('road %r does not exist (roads: %s)' % (road, ', '.join(k for k, v in C.items() if v['meta'].get('kind') == 'road')
                                                                 or 'none'))
        return {'points': P, 'closed': closed, 'widths': W, 'banks': B, 'material': material, 'uv_len': float(uv_len),
                'step': float(step), 'road': road}

    def _proad_geom(self, req):
        S, pars, L = tg.sample_param(req['points'], req['closed'], step=req['step'])
        S = [[p[0], y, p[2]] for p, y in zip(S, tg.monotone_y(req['points'], req['closed'], pars))]
        T_ = wc.tangents(S, req['closed'])
        hws = [w / 2 for w in tg.interp_profile(req['widths'], pars, req['closed'], 'widths')]
        banks = tg.interp_profile(req['banks'], pars, req['closed'], 'banks')
        faces, length = tg.profiled_strip(S, T_, req['closed'], hws, banks, req['material'], req['uv_len'])
        return S, T_, hws, banks, faces, length

    def _proad_plan(self, req):
        try:
            S, T_, hws, banks, faces, length = self._proad_geom(req)
        except wc.ConstructError as e:
            raise E('road refused: %s. Nothing changed' % e)
        rid = req['road'] or self._new_id('road')
        meta = {'kind': 'road', 'id': rid, 'profile': True, 'points': req['points'], 'closed': req['closed'], 'widths': req['widths'],
                'banks': req['banks'], 'material': req['material'], 'uv_len': req['uv_len'], 'step': req['step']}
        repl = self.constructs()[req['road']]['groups'] if req['road'] else []
        ov = self._overlap_check(faces, set(repl), 'road faces')
        after, blk = self._block_bytes(faces, meta, repl)
        xs = tg.cross_sections(S, T_, hws, banks, req['closed'])
        warns, worst = tg.continuity_warnings(xs, req['closed'])
        warns = self._route_floor_warnings(blk['faces']) + warns
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'road': rid, 'profile': True, 'replaces': req['road'], 'samples': len(S), 'length_m': round(length, 3),
                            'faces': len(faces), 'closed': req['closed'], 'material': req['material'],
                            'width_m': [round(2 * min(hws), 3), round(2 * max(hws), 3)],
                            'bank_deg': [round(min(banks), 3), round(max(banks), 3)],
                            'elevation_m': [round(min(p[1] for p in S), 3), round(max(p[1] for p in S), 3)],
                            'continuity': worst, 'warnings': warns, 'cross_sections': xs[::max(1, len(xs) // 200)], 'overlap': ov,
                            'v_added': blk['v_added'], 'vt_added': blk['vt_added'], 'vn_added': blk['vn_added'],
                            'removed_faces': blk['removed_faces'], 'markers': req['points'],
                            'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]],
                            'uv_mapping': 'u 0 (n- edge) .. 1 (n+ edge) across at any width, v = centre-line distance / %g m '
                                          '(continuous along)' % req['uv_len'],
                            'normals': 'each quad\'s Newell normal (5 decimals; banked quads tilt with the bank)',
                            'collision': 'from the material (%s) - generated by trackbuild at Build' % req['material'],
                            'summary_lines': ['profiled road %s: %.1f m, %d faces, width %s m, bank %s deg, elevation %s m' % (
                                rid, length, len(faces), [round(2 * min(hws), 2), round(2 * max(hws), 2)],
                                [round(min(banks), 2), round(max(banks), 2)], [round(min(p[1] for p in S), 2), round(max(p[1] for p in S), 2)])]
                            + ['WARNING: ' + w for w in warns]}}

    def road_profile_preview(self, points=None, closed=False, widths=None, banks=None, material=None, uv_len=14.0, step=4.0, road=None):
        """TE stage 1: a road with per-control-point widths and banks (smooth transitions), elevation from the points, cross-sections
        and continuity warnings, WITHOUT changing anything"""
        req = self._proad_req(points, closed, widths, banks, material, uv_len, step, road)
        plan = self._proad_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('proad', req), note='preview only: nothing changed')

    def road_profile(self, points=None, closed=False, widths=None, banks=None, material=None, uv_len=14.0, step=4.0, road=None,
                     preview_key=None):
        req = self._proad_req(points, closed, widths, banks, material, uv_len, step, road)
        if preview_key != self._cons_key('proad', req):
            raise E('NEEDS PREVIEW: preview this road first and apply it with its preview_key')
        plan = self._proad_plan(req)
        S = plan['summary']
        label = '%s profiled road %s (%.1f m, %d faces)' % ('re-generate' if road else 'new', plan['id'], S['length_m'], S['faces'])
        r = self._apply_block(plan, label, 'proad', S['faces'])
        return dict(S, **r)

    def cross_section_view(self, road=None):
        """read only: the cross-sections of an existing profiled road block or of the route stations"""
        if road is None:
            d = self.desc()
            st = d.get('stations') or []
            if not st:
                raise E('no route stations')
            out = [{'i': i, 'centre': s['p'], 'offsets': s['offsets'],
                    'grade_pct': round(100 * (st[(i + 1) % len(st)]['p'][1] - s['p'][1]) /
                                       max(1e-9, math.hypot(st[(i + 1) % len(st)]['p'][0] - s['p'][0],
                                                            st[(i + 1) % len(st)]['p'][2] - s['p'][2])), 3)}
                   for i, s in enumerate(st)]
            return {'ok': True, 'route': True, 'sections': out[::max(1, len(out) // 200)], 'count': len(out)}
        C = self.constructs()
        if road not in C or C[road]['meta'].get('kind') != 'road':
            raise E('road %r does not exist' % (road,))
        m = C[road]['meta']
        req = {'points': m['points'], 'closed': m['closed'], 'widths': m.get('widths') or [m['width']] * len(m['points']),
               'banks': m.get('banks') or [0.0] * len(m['points']), 'material': m['material'], 'uv_len': m['uv_len'], 'step': m['step']}
        S, T_, hws, banks, _f, _l = self._proad_geom(req)
        xs = tg.cross_sections(S, T_, hws, banks, req['closed'])
        warns, worst = tg.continuity_warnings(xs, req['closed'])
        return {'ok': True, 'road': road, 'sections': xs, 'count': len(xs), 'continuity': worst, 'warnings': warns}

    # ================================================================== stage 2: junctions, joins, routing
    def _floor_faces(self, exclude_groups=()):
        """existing collide FLOOR faces (low byte <= 20) of the current OBJ as corner lists (kit reader), excluding some groups"""
        d = self.desc()
        mats = d.get('materials') or {}
        cov = self.coverage(self.obj_cur)
        lines, groups, _v = T['obj_index'](self.obj_cur)
        fl = sorted((li, x['i']) for x in groups for li in x['faces'])
        out = []
        for (li, g), f in zip(fl, cov['faces']):
            m = mats.get(f['mat']) or {}
            try:
                w = int(m.get('surface'), 16)
            except (TypeError, ValueError):
                continue
            if g in exclude_groups or not m.get('collide') or (w & 0xFF) > 20:
                continue
            out.append({'pts': f['pts'], 'line': li + 1, 'group': g, 'mat': f['mat']})
        return out

    def _overlap_check(self, faces, exclude_groups=(), what='new faces'):
        # terrain lies under roads by design (its own check: _terrain_through); it is not an overlapping floor
        terr = {g for c in self.constructs().values() if c['meta'].get('kind') in ('terrain', 'hterrain') for g in c['groups']}
        old = self._floor_faces(set(exclude_groups) | terr)
        new = [[c[0] for c in cs] for _m, cs in faces]
        allv = tg.floor_overlaps(new, [o['pts'] for o in old])
        ov = [x for x in allv if x[3] < tg.LAYER_DY]           # coplanar (z-fighting, ambiguous collision) or below an existing floor
        on_top = [x for x in allv if x[3] >= tg.LAYER_DY]
        if ov:
            det = [{'new_face': i, 'existing_line': old[j]['line'], 'existing_group': old[j]['group'], 'material': old[j]['mat'],
                    'overlap_m2': a, 'dy_m': dy, 'corners': [list(p) for p in old[j]['pts']]} for i, j, a, dy in ov[:200]]
            raise E('refused: %d of the %s overlap existing collision floor at the same height or below it (%.2f m2 in total; first: '
                    'existing face line %d, %s, %.2f m2, %+.3f m) - coplanar floors z-fight and give ambiguous collision, a floor below '
                    'another is hidden. Raise it above (>= %.2f m: it then lies on top), move it, or remove the other geometry first '
                    '(more than 1.5 m apart in height: bridges / tunnels are allowed). Nothing changed' % (
                        len(ov), what, sum(x[2] for x in ov), det[0]['existing_line'], det[0]['material'], det[0]['overlap_m2'],
                        det[0]['dy_m'], tg.LAYER_DY), {'overlaps': det, 'lost_faces': [{'corners': x['corners']} for x in det]})
        return {'checked_against': len(old), 'overlaps': 0, 'on_top_of_existing_floor': len(on_top),
                'rule': 'plan overlap > 0.01 m2 with a collide floor within 1.5 m in height is refused unless the new face lies at '
                        'least %.2f m above it at the overlap (layered: the highest floor is the car / V2 floor)' % tg.LAYER_DY}

    def _road_geom_of(self, meta):
        """the cross-section samples of an existing road block (v0.24 plain or TE profiled) -> (S, T, hws, banks, length, uv_len)"""
        if meta.get('profile'):
            req = {'points': meta['points'], 'closed': meta['closed'], 'widths': meta['widths'], 'banks': meta['banks'],
                   'material': meta['material'], 'uv_len': meta['uv_len'], 'step': meta['step']}
            S, T_, hws, banks, _f, length = self._proad_geom(req)
        else:
            S, _L = wc.sample(meta['points'], meta['closed'], step=meta['step'])
            T_ = wc.tangents(S, meta['closed'])
            hws, banks = [meta['width'] / 2] * len(S), [0.0] * len(S)
            length = sum(math.dist(S[i - 1], S[i]) for i in range(1, len(S)))
        return S, T_, hws, banks, length, meta['uv_len']

    def road_ends(self):
        """read only: every open road end (roads: start / end; junction arms) as {ref, centre, t (pointing out), width, bank (along
        t), v (texture v at the end), corners}"""
        out = []
        for cid, c in sorted(self.constructs().items()):
            m = c['meta']
            if m.get('kind') == 'road' and not m.get('closed'):
                S, T_, hws, banks, length, uvl = self._road_geom_of(m)
                out.append({'ref': cid + ':start', 'centre': S[0], 't': [-T_[0][0], -T_[0][1]], 'width': 2 * hws[0], 'bank': -banks[0],
                            'v': 0.0, 'u_flipped': True})
                out.append({'ref': cid + ':end', 'centre': S[-1], 't': list(T_[-1]), 'width': 2 * hws[-1], 'bank': banks[-1],
                            'v': length / uvl, 'u_flipped': False})
            elif m.get('kind') == 'junction':
                for e in m['ends']:
                    out.append(dict(e, ref='%s:arm%d' % (cid, e['arm']), u_flipped=False))
            elif m.get('kind') == 'join':
                pass                                        # a connector's ends are taken
        taken = {r for c in self.constructs().values() if c['meta'].get('kind') == 'join' for r in (c['meta']['a'], c['meta']['b'])}
        for e in out:
            e['taken'] = e['ref'] in taken
            e['corners'] = [[round(v, 4) for v in tg.edge_pt(e['centre'], e['t'], s * e['width'] / 2, e['bank'])] for s in (-1, 1)]
        return out

    def road_ends_view(self):
        E_ = self.road_ends()
        return {'ok': True, 'ends': E_, 'markers': [e['centre'] for e in E_],
                'summary_lines': ['%d open road end(s): %s' % (len(E_), ', '.join('%s%s (%.1f m wide)' % (e['ref'], ' [joined]' if e['taken']
                                                                                                            else '', e['width'])
                                                                              for e in E_) or 'none')]}

    def _junction_req(self, centre, heading, arms, material, uv_len, id_):
        if not (isinstance(centre, list) and len(centre) == 3 and all(num(v, -1e6, 1e6) for v in centre)):
            raise E('centre must be [x, y, z] metres')
        if not num(heading, -360, 360):
            raise E('heading: -360..360 degrees')
        if not num(uv_len, 0.5, 200):
            raise E('uv length: 0.5..200 m')
        self._mat_ok(material, 'junction')
        if id_ is not None:
            C = self.constructs()
            if id_ not in C or C[id_]['meta'].get('kind') != 'junction':
                raise E('junction %r does not exist' % (id_,))
        return {'centre': [float(v) for v in centre], 'heading': float(heading), 'arms': arms, 'material': material,
                'uv_len': float(uv_len), 'id': id_}

    def _junction_plan(self, req):
        try:
            faces, ends = tg.junction_faces(req['centre'], req['heading'], req['arms'], req['material'], req['uv_len'])
        except wc.ConstructError as e:
            raise E('junction refused: %s. Nothing changed' % e)
        C = self.constructs()
        repl = C[req['id']]['groups'] if req['id'] else []
        taken = [r for c in C.values() if c['meta'].get('kind') == 'join' for r in (c['meta']['a'], c['meta']['b'])
                 if req['id'] and r.startswith(req['id'] + ':')]
        if taken:
            raise E('junction %s has joined arms (%s): remove / re-generate those joins first (a re-generated junction may move its arm '
                    'ends). Nothing changed' % (req['id'], ', '.join(taken)))
        ov = self._overlap_check(faces, set(repl), 'junction faces')
        rid = req['id'] or self._new_id('junction')
        meta = {'kind': 'junction', 'id': rid, 'centre': req['centre'], 'heading': req['heading'], 'arms': req['arms'],
                'material': req['material'], 'uv_len': req['uv_len'],
                'ends': [{k: ([round(x, 6) for x in v] if isinstance(v, list) else v) for k, v in e.items()} for e in ends]}
        after, blk = self._block_bytes(faces, meta, repl)
        warn = self._route_floor_warnings(blk['faces'])
        kind = {3: 'T / Y', 4: 'cross'}.get(len(req['arms']), '%d-way' % len(req['arms']))
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'junction': rid, 'type': kind, 'faces': len(faces), 'ends': meta['ends'], 'overlap': ov, 'warnings': warn,
                            'markers': [e['centre'] for e in ends], 'v_added': blk['v_added'], 'vt_added': blk['vt_added'],
                            'vn_added': blk['vn_added'], 'removed_faces': blk['removed_faces'],
                            'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]],
                            'routing': 'GEOMETRIC junction only: the AI route and traffic network are not changed (trackbuild writes one '
                                       'closed route with 5 cyclic lanes and one traffic road; branching navigation is not expressible)',
                            'uv_mapping': 'hub planar (plan / 8 m; a texture seam at the hub edges), arms u 0..1 across, v along / %g m' % req['uv_len'],
                            'summary_lines': ['%s junction %s: %d arms, %d faces, level at y %.3f; arm ends %s' % (
                                kind, rid, len(req['arms']), len(faces), req['centre'][1],
                                ', '.join('arm%d %.1f m wide' % (e['arm'], e['width']) for e in ends))] + ['WARNING: ' + w for w in warn] +
                            ['routing: geometric only - not part of the AI route / traffic network']}}

    def junction_preview(self, centre=None, heading=0.0, arms=None, material=None, uv_len=14.0, id=None):  # noqa: A002
        """TE stage 2: a level T / Y / cross (3..6 arms) junction piece, WITHOUT changing anything"""
        req = self._junction_req(centre, heading, arms, material, uv_len, id)
        plan = self._junction_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('junction', req), note='preview only: nothing changed')

    def junction(self, centre=None, heading=0.0, arms=None, material=None, uv_len=14.0, id=None, preview_key=None):  # noqa: A002
        req = self._junction_req(centre, heading, arms, material, uv_len, id)
        if preview_key != self._cons_key('junction', req):
            raise E('NEEDS PREVIEW: preview this junction first and apply it with its preview_key')
        plan = self._junction_plan(req)
        S = plan['summary']
        label = '%s junction %s (%s, %d faces)' % ('re-generate' if id else 'new', plan['id'], S['type'], S['faces'])
        r = self._apply_block(plan, label, 'junction', S['faces'])
        return dict(S, **r)

    def _join_req(self, a, b, material, step, uv_len, id_):
        ends = {e['ref']: e for e in self.road_ends()}
        for nm, r in (('a', a), ('b', b)):
            if r not in ends:
                raise E('end %s %r does not exist (open ends: %s)' % (nm, r, ', '.join(sorted(ends)) or 'none'))
        if a == b or a.split(':')[0] == b.split(':')[0] and not a.split(':')[0].startswith('junction'):
            raise E('join refused: the two ends must belong to different roads (or two arms of junctions)')
        C = self.constructs()
        own = C[id_]['meta'] if id_ is not None and id_ in C and C[id_]['meta'].get('kind') == 'join' else None
        if id_ is not None and own is None:
            raise E('join %r does not exist' % (id_,))
        for r in (a, b):
            if ends[r]['taken'] and not (own and r in (own['a'], own['b'])):
                raise E('end %s is already joined: one connector per road end' % r)
        if not num(step, 0.5, 20) or not num(uv_len, 0.5, 200):
            raise E('step 0.5..20 m, uv length 0.5..200 m')
        self._mat_ok(material, 'join')
        return {'a': a, 'b': b, 'ea': ends[a], 'eb': ends[b], 'material': material, 'step': float(step), 'uv_len': float(uv_len),
                'id': id_}

    def _join_plan(self, req):
        ea, eb = req['ea'], req['eb']
        try:
            faces, S, info = tg.join_faces(ea, eb, req['material'], req['step'], req['uv_len'])
        except wc.ConstructError as e:
            raise E('join refused: %s. Nothing changed' % e)
        C = self.constructs()
        repl = C[req['id']]['groups'] if req['id'] else []
        ov = self._overlap_check(faces, set(repl), 'connector faces')
        rid = req['id'] or self._new_id('join')
        meta = {'kind': 'join', 'id': rid, 'a': req['a'], 'b': req['b'], 'material': req['material'], 'step': req['step'],
                'uv_len': req['uv_len']}
        after, blk = self._block_bytes(faces, meta, repl)
        # the connector's end corners must be EXACTLY the road ends' corners (as written, 4 decimals): continuity by position
        first, last = blk['faces'][0], blk['faces'][-1]
        want_a = sorted(tuple(c) for c in ea['corners'])
        want_b = sorted(tuple(c) for c in eb['corners'])
        got_a = sorted(tuple(round(v, 4) for v in p) for p in (first[0], first[3]))
        got_b = sorted(tuple(round(v, 4) for v in p) for p in (last[1], last[2]))
        if got_a != want_a or got_b != want_b:
            raise E('internal: the connector end corners do not coincide with the road ends (%s / %s vs %s / %s); not applied' % (
                got_a, got_b, want_a, want_b))
        seams = []
        if ea['u_flipped']:
            seams.append('u mirrored at %s (the connector leaves a road START: its n- edge is that road\'s n+ edge)' % req['a'])
        if not eb['u_flipped']:
            seams.append('u mirrored at %s (the connector arrives at a road END / junction arm against its direction)' % req['b'])
        vb_conn = info['v_from'] + info['length_m'] / req['uv_len']
        if abs((vb_conn - eb['v']) % 1.0) > 1e-3 and abs((vb_conn - eb['v']) % 1.0 - 1) > 1e-3:
            seams.append('v offset %.3f texture repeats at %s (v continues from %s; a texture seam, geometry continuous)' % (
                (vb_conn - eb['v']) % 1.0, req['b'], req['a']))
        warn = self._route_floor_warnings(blk['faces'])
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': dict(info, join=rid, a=req['a'], b=req['b'], faces=len(faces), overlap=ov, warnings=warn, uv_seams=seams,
                                continuity={'corners_at_a': 'exact (%s)' % want_a, 'corners_at_b': 'exact (%s)' % want_b},
                                markers=[ea['centre'], eb['centre']], v_added=blk['v_added'], vt_added=blk['vt_added'],
                                vn_added=blk['vn_added'], removed_faces=blk['removed_faces'],
                                new_faces=[[list(q) for q in P] for P in blk['faces'][:3000]],
                                routing='geometric connection only (no AI / traffic link)',
                                summary_lines=['join %s: %s -> %s, %.1f m, %d faces, max grade %.1f %%; end corners coincide exactly' % (
                                    rid, req['a'], req['b'], info['length_m'], len(faces), info['max_grade_pct'])] +
                                ['UV SEAM: ' + s_ for s_ in seams] + ['WARNING: ' + w for w in warn])}

    def join_preview(self, a=None, b=None, material=None, step=4.0, uv_len=14.0, id=None):  # noqa: A002
        """TE stage 2: a connector between two open road / junction-arm ends (their end cross-sections exactly), WITHOUT changes"""
        req = self._join_req(a, b, material, step, uv_len, id)
        plan = self._join_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('join', {k: v for k, v in req.items() if k not in ('ea', 'eb')}),
                    note='preview only: nothing changed')

    def join(self, a=None, b=None, material=None, step=4.0, uv_len=14.0, id=None, preview_key=None):  # noqa: A002
        req = self._join_req(a, b, material, step, uv_len, id)
        if preview_key != self._cons_key('join', {k: v for k, v in req.items() if k not in ('ea', 'eb')}):
            raise E('NEEDS PREVIEW: preview this join first and apply it with its preview_key')
        plan = self._join_plan(req)
        S = plan['summary']
        label = '%s join %s (%s -> %s, %d faces)' % ('re-generate' if id else 'new', plan['id'], a, b, S['faces'])
        r = self._apply_block(plan, label, 'join', S['faces'])
        return dict(S, **r)

    def routing(self):
        """read only: what the route / traffic / starts express, and which geometry is navigation-relevant vs geometric only"""
        d = self.desc()
        st = d.get('stations') or []
        rt = d.get('route') or {}
        tr = d.get('traffic')
        C = self.constructs()
        geo = sorted(k for k, c in C.items() if c['meta'].get('kind') in ('junction', 'join', 'road'))
        gaps = d.get('wall_gaps') or []
        n = len(st)
        length = sum(math.dist(st[i]['p'], st[(i + 1) % n]['p']) for i in range(n)) if n else 0
        near = []
        for g in gaps:                                      # geometry reaching the route through a declared outer gap
            a, b = g
            pts = [wc.offset_pt(st[i]['p'], st[i]['t'], st[i]['offsets'][1]) for i in range(max(0, a), min(n, b + 1))]
            for cid in geo:
                for e in self.road_ends():
                    if e['ref'].split(':')[0] == cid and pts and min(math.hypot(e['centre'][0] - p[0], e['centre'][2] - p[2]) for p in pts) < 3:
                        near.append({'gap': g, 'end': e['ref']})
        rep = {'ok': True,
               'route': {'closed': d.get('closed', True), 'stations': n, 'length_m': round(length, 2),
                         'direction': 'station order (station 0 -> 1 -> ...); start tangent %s' % (st[0]['t'] if st else None),
                         'lanes': [x.get('name') for x in rt.get('lanes') or []], 'corner_records': len(rt.get('corners') or []),
                         'navigation': 'AI drivers use this one closed route (S4: 5 cyclic lanes)'},
               'starts': {'grid_slots': len(d.get('grid') or []), 'start_line': bool(d.get('start_line')),
                          'checkpoints': len(d.get('checkpoints') or [])},
               'traffic': ({'mode': 'authored', 'lanes': len(tr.get('lanes') or []), 'node_stations': tr.get('node_stations'),
                            'spans_stations': [tr.get('first_station'), tr.get('last_station')]} if tr else
                           {'mode': 'donor (retail EU/M1_V1 S2 / S3, positioned far from this track)'}),
               'wall_gaps': gaps, 'geometry_reaching_route_through_gaps': near,
               'geometric_only': geo,
               'not_expressible': ['AI branching / alternative routes (one closed S4 route)',
                                   'traffic on side roads (one authored traffic road along the route)',
                                   'checkpoints or starts off the route'],
               'runtime': 'NOT proven offline: AI following, lap / checkpoint counting, traffic behaviour and driving through gaps / '
                          'junctions need an in-game run'}
        rep['summary_lines'] = ['route: %d stations, %.1f m closed loop, %d lanes, %d corner records; starts %d grid / %s / %d checkpoints; '
                                'traffic %s' % (n, length, len(rep['route']['lanes']), rep['route']['corner_records'], rep['starts']['grid_slots'],
                                                'start line' if rep['starts']['start_line'] else 'NO start line', rep['starts']['checkpoints'],
                                                rep['traffic']['mode']),
                                'geometric only (not navigation): %s' % (', '.join(geo) or 'none'),
                                'outer wall gaps: %s; geometry reaching the route there: %s' % (gaps or 'none', near or 'none'),
                                'runtime: ' + rep['runtime']]
        return rep

    # ================================================================== stage 3: height-grid terrain
    def _hgrid(self, id_):
        C = self.constructs()
        if id_ not in C or C[id_]['meta'].get('kind') != 'hterrain':
            raise E('height terrain %r does not exist (%s)' % (id_, ', '.join(k for k, c in C.items() if c['meta'].get('kind') == 'hterrain')
                                                               or 'none yet: create one first'))
        return C[id_]

    def _terrain_through(self, m, exclude_groups):
        """floor faces of other blocks that the terrain surface AS GENERATED covers (probe points: corners, edge points, centroid)"""
        terr = {g for c in self.constructs().values() if c['meta'].get('kind') in ('terrain', 'hterrain') for g in c['groups']}
        x0, z0 = m['origin']
        x1, z1 = x0 + m['nx'] * m['cell'], z0 + m['nz'] * m['cell']
        hits = []
        for f in self._floor_faces(set(exclude_groups) | terr):
            if max(p[0] for p in f['pts']) < x0 or min(p[0] for p in f['pts']) > x1 or max(p[2] for p in f['pts']) < z0 or                     min(p[2] for p in f['pts']) > z1:
                continue
            for at, h in tg.terrain_above(m['origin'], m['cell'], m['nx'], m['nz'], m['heights'], [f['pts']], 0.0):
                hits.append({'line': f['line'], 'material': f['mat'], 'at': list(at), 'terrain_y': h})
        return hits

    def _hterrain_plan(self, meta, repl, label_kind):
        try:
            faces = tg.hgrid_faces(meta['origin'], meta['cell'], meta['nx'], meta['nz'], meta['heights'], meta['material'], meta['uv_m'])
        except wc.ConstructError as e:
            raise E('terrain refused: %s. Nothing changed' % e)
        after, blk = self._block_bytes(faces, meta, repl)
        warn = self._route_floor_warnings(blk['faces'])
        poke = self._terrain_through(meta, repl)
        if poke:
            warn.append('the terrain lies ABOVE %d existing floor corner(s) (first: face line %d %s at %s, terrain %.3f m): it would cover '
                        'them - lower it there or use the road-edge blend' % (len(poke), poke[0]['line'], poke[0]['material'],
                                                                             poke[0]['at'], poke[0]['terrain_y']))
        H = meta['heights']
        return {'after': after, 'blk': blk, 'planned': faces, 'id': meta['id'],
                'summary': {'terrain': meta['id'], 'kind': label_kind, 'grid': [meta['nx'], meta['nz']], 'cell_m': meta['cell'],
                            'faces': len(faces), 'triangles_for_non_planar_cells': sum(1 for _m, cs in faces if len(cs) == 3),
                            'height_m': [round(min(H), 3), round(max(H), 3)], 'warnings': warn, 'covers_floor': poke[:50],
                            'capacity': 'grid %d x %d = %d of %d cells per block; the kit per-unit capacity is checked on apply' % (
                                meta['nx'], meta['nz'], meta['nx'] * meta['nz'], tg.HGRID_MAX_CELLS),
                            'v_added': blk['v_added'], 'vt_added': blk['vt_added'], 'vn_added': blk['vn_added'],
                            'removed_faces': blk['removed_faces'], 'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]],
                            'summary_lines': ['%s %s: %d x %d cells of %g m, %d faces, heights %s m' % (
                                label_kind, meta['id'], meta['nx'], meta['nz'], meta['cell'], len(faces),
                                [round(min(H), 3), round(max(H), 3)])] + ['WARNING: ' + w for w in warn]}}

    def _hterrain_req(self, rect, cell, height, material, id_):
        if not (isinstance(rect, list) and len(rect) == 4 and all(num(v, -1e6, 1e6) for v in rect) and rect[2] > rect[0] and rect[3] > rect[1]):
            raise E('terrain rect must be [x0, z0, x1, z1] metres (x0 < x1, z0 < z1)')
        if not num(cell, 1, 50):
            raise E('cell %r: 1..50 m' % (cell,))
        if not (num(height, -1e5, 1e5) or (isinstance(height, list) and len(height) == 4 and all(num(h, -1e5, 1e5) for h in height))):
            raise E('height: one number or four corner heights [x0z0, x1z0, x1z1, x0z1]')
        self._mat_ok(material, 'terrain')
        if id_ is not None:
            self._hgrid(id_)
        nx, nz = max(1, int(round((rect[2] - rect[0]) / cell))), max(1, int(round((rect[3] - rect[1]) / cell)))
        if nx * nz > tg.HGRID_MAX_CELLS or nx > 128 or nz > 128:
            raise E('terrain of %d x %d cells refused: at most 128 x 128 and %d cells per block (use a larger cell or several blocks)' % (
                nx, nz, tg.HGRID_MAX_CELLS))
        h4 = [float(height)] * 4 if not isinstance(height, list) else [float(h) for h in height]
        H = []
        for k in range(nz + 1):
            for i in range(nx + 1):
                u, v = i / nx, k / nz
                H.append(round(h4[0] * (1 - u) * (1 - v) + h4[1] * u * (1 - v) + h4[2] * u * v + h4[3] * (1 - u) * v, 4))
        return {'origin': [float(rect[0]), float(rect[1])], 'cell': float(cell), 'nx': nx, 'nz': nz, 'heights': H,
                'material': material, 'uv_m': 8.0, 'id': id_}

    def hterrain_preview(self, rect=None, cell=10.0, height=None, material=None, id=None):  # noqa: A002
        """TE stage 3: a new (or re-generated) height-grid terrain block, WITHOUT changing anything"""
        req = self._hterrain_req(rect, cell, height, material, id)
        meta = dict(req, kind='hterrain', id=id or self._new_id('hterrain'))
        repl = self.constructs()[id]['groups'] if id else []
        plan = self._hterrain_plan(meta, repl, 'height terrain')
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('hterrain', req), note='preview only: nothing changed')

    def hterrain(self, rect=None, cell=10.0, height=None, material=None, id=None, preview_key=None):  # noqa: A002
        req = self._hterrain_req(rect, cell, height, material, id)
        if preview_key != self._cons_key('hterrain', req):
            raise E('NEEDS PREVIEW: preview this terrain first and apply it with its preview_key')
        meta = dict(req, kind='hterrain', id=id or self._new_id('hterrain'))
        repl = self.constructs()[id]['groups'] if id else []
        plan = self._hterrain_plan(meta, repl, 'height terrain')
        S = plan['summary']
        label = '%s height terrain %s (%d x %d cells)' % ('re-generate' if id else 'new', meta['id'], meta['nx'], meta['nz'])
        return dict(S, **self._apply_block(plan, label, 'hterrain', S['faces']))

    def _brush_req(self, id_, mode, centre, radius, strength, target, points, road, drop):
        c = self._hgrid(id_)
        m = c['meta']
        polys = None
        if mode == 'blend':
            C = self.constructs()
            if road not in C or C[road]['meta'].get('kind') in ('hterrain', 'terrain'):
                raise E('blend needs `road` = an existing road / junction / join / race block id (not terrain): %s' % (
                    ', '.join(k for k, v in C.items() if v['meta'].get('kind') in ('road', 'junction', 'join', 'race')) or 'none'))
            polys = [f['pts'] for f in self._floor_faces() if f['group'] in set(C[road]['groups'])]
            if not polys:
                raise E('block %s has no collision floor faces to blend to' % road)
        try:
            H, changed = tg.brush(m['origin'], m['cell'], m['nx'], m['nz'], m['heights'], mode, centre, radius, strength, target, points,
                                  polys, 0.05 if drop is None else drop)
        except wc.ConstructError as e:
            raise E('brush refused: %s. Nothing changed' % e)
        if not changed:
            raise E('the brush changes no grid vertex (outside the grid / radius, or already at the target): nothing to apply')
        req = {'id': id_, 'mode': mode, 'centre': centre, 'radius': radius, 'strength': strength, 'target': target, 'points': points,
               'road': road, 'drop': drop}
        return req, dict(m, heights=H), c['groups'], changed

    def terrain_brush_preview(self, id=None, mode=None, centre=None, radius=None, strength=None, target=None, points=None,  # noqa: A002
                              road=None, drop=None):
        """TE stage 3: one brush stroke on a height terrain (raise / lower / flatten / smooth / set / blend to a road), WITHOUT
        changing anything; the road is never moved"""
        req, meta, groups, changed = self._brush_req(id, mode, centre, radius, strength, target, points, road, drop)
        plan = self._hterrain_plan(meta, groups, 'brush %s on' % mode)
        old = self._hgrid(id)['meta']['heights']
        return dict(plan['summary'], ok=True, changed_vertices=len(changed),
                    max_change_m=round(max(abs(meta['heights'][j] - old[j]) for j in changed), 4),
                    preview_key=self._cons_key('brush', req), note='preview only: nothing changed')

    def terrain_brush(self, id=None, mode=None, centre=None, radius=None, strength=None, target=None, points=None, road=None,  # noqa: A002
                      drop=None, preview_key=None):
        req, meta, groups, changed = self._brush_req(id, mode, centre, radius, strength, target, points, road, drop)
        if preview_key != self._cons_key('brush', req):
            raise E('NEEDS PREVIEW: preview this brush stroke first and apply it with its preview_key')
        plan = self._hterrain_plan(meta, groups, 'brush %s on' % mode)
        S = plan['summary']
        label = 'terrain brush %s on %s (%d vertices)' % (mode, id, len(changed))
        r = self._apply_block(plan, label, 'hterrain', S['faces'])
        out = dict(S, **r)
        out['changed_vertices'] = len(changed)
        if mode == 'blend':
            out['road_unchanged'] = 'the road block %s keeps its faces (only the terrain block was re-generated)' % road
        return out

    # ================================================================== stage 4: mesh editing
    MESH_OPS = ('transform', 'delete', 'triangulate', 'subdivide', 'extrude', 'fill')

    def _kit_read(self, b):
        import os
        import shutil
        import tempfile
        K = T['kit_trackbuild'](self.cfg)
        root = os.path.join(self.cfg['state'], 'geomcheck')
        os.makedirs(root, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='mesh_', dir=root)
        try:
            p = os.path.join(tmp, 'edited.obj')
            with open(p, 'wb') as f:
                f.write(b)
            return K['io'].read_obj(p)
        except K['io'].SourceError as e:
            raise E('refused: trackbuild cannot read the edited OBJ (%s). Nothing changed' % e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _bad_faces(obj):
        """faces trackbuild would refuse / drop: area <= 1e-4 m2 or a fan triangle failing the kit rule -> [index]"""
        out = []
        for i, (_m, fv) in enumerate(obj['faces']):
            P = [q[0] for q in fv]
            if T['_poly_area'](P) <= 1e-4 or not all(T['_fan_good'](P, fv[0][2])):
                out.append(i)
        return out

    def _mesh_plan(self, op, a):
        import wb_te_mesh as tm
        if self.obj_cur is None:
            raise E('the OBJ did not pass the input check: mesh editing needs a readable OBJ')
        if op not in self.MESH_OPS:
            raise E('mesh op %r refused: %s' % (op, ' / '.join(self.MESH_OPS)))
        allowed = {'transform': {'verts', 'edges', 'faces', 'delta', 'angle', 'scale', 'pivot', 'axis'}, 'delete': {'faces'},
                   'triangulate': {'faces', 'diagonal'}, 'subdivide': {'faces'}, 'extrude': {'faces', 'distance', 'side_material'},
                   'fill': {'loop', 'material'}}[op]
        if set(a) - allowed:
            raise E('mesh %s: unknown argument(s) %s (allowed: %s)' % (op, ', '.join(sorted(set(a) - allowed)), ', '.join(sorted(allowed))))
        o = tm.Obj(self.obj_cur)
        try:
            if op == 'transform':
                keys = tm.sel_vertices(o, a.get('verts'), a.get('edges'), a.get('faces'))
                piv = a.get('pivot')
                if piv is not None and not (isinstance(piv, list) and len(piv) == 3 and all(num(v, -1e6, 1e6) for v in piv)):
                    raise E('pivot: [x, y, z] or omitted (the selection bounding-box centre / lowest point)')
                w, rep = tm.op_transform(o, keys, a.get('delta') or [0, 0, 0], a.get('angle') or 0.0, a.get('scale', 1.0), piv, a.get('axis'))
            elif op == 'delete':
                w, rep = tm.op_delete(o, a.get('faces'))
            elif op == 'triangulate':
                w, rep = tm.op_triangulate(o, a.get('faces'), a.get('diagonal', 'short'))
            elif op == 'subdivide':
                w, rep = tm.op_subdivide(o, a.get('faces'))
            elif op == 'extrude':
                if a.get('side_material') is not None:
                    self._mat_ok(a['side_material'], 'side')
                cid = self._new_id('extrude')
                tag = self.TAG + json.dumps({'kind': 'mesh', 'id': cid, 'op': 'extrude', 'faces': a.get('faces'),
                                             'distance': a.get('distance')}, sort_keys=True, separators=(',', ':')).encode('ascii')
                w, rep = tm.op_extrude(o, a.get('faces'), a.get('distance'), a.get('side_material'), tag)
            else:
                self._mat_ok(a.get('material'), 'fill')
                cid = self._new_id('fill')
                tag = self.TAG + json.dumps({'kind': 'mesh', 'id': cid, 'op': 'fill', 'loop': a.get('loop')}, sort_keys=True,
                                            separators=(',', ':')).encode('ascii')
                w, rep = tm.op_fill(o, a.get('loop'), a.get('material'), tag)
            after = w.build()
            for k in ('affected_faces', 'extruded_faces', 'subdivided'):     # report line numbers of the EDITED file
                if k in rep:
                    rep[k] = [w.map[li - 1] + 1 for li in rep[k]]
            for x in rep.get('triangulated', []):
                x['line'] = w.map[x['line'] - 1] + 1
            rep['line_numbers'] = 'after the edit (new v / vt / vn lines shift later lines); deleted_faces: before the edit'
        except tm.MeshError as e:
            raise E('mesh %s refused: %s. Nothing changed' % (op, e))
        obj1 = self._kit_read(after)
        o1 = tm.Obj(after)
        bad0 = len(self._bad_faces(self._kit_read(self.obj_cur)))
        bad1 = self._bad_faces(obj1)
        if len(bad1) > bad0:
            fl1 = sorted(o1.F)
            raise E('mesh %s refused: %d face(s) would be degenerate or dropped by trackbuild (sliver / against its normal; first: line '
                    '%d). No automatic repair. Nothing changed' % (op, len(bad1) - bad0, fl1[bad1[0]] + 1),
                    {'lost_faces': [{'corners': [list(q[0]) for q in obj1['faces'][i][1]]} for i in bad1[:100]]})
        changed = [li for li in sorted(o1.F) if o1.lines[li] not in set(self.obj_cur.splitlines(keepends=True))]
        hl = [[list(map(float, o1.V[v - 1])) for v, _t, _n in o1.F[li]] for li in changed[:3000]]
        touched = sorted({cid for cid, c in self.constructs().items() for g in c['groups'] for li in o.groups[g]['faces']
                          if li not in o1.F or o.lines[li] != (o1.lines[w.map[li]] if li in w.map and w.map[li] < len(o1.lines) else None)})
        if touched:
            rep['warnings'] = ['faces of construction block(s) %s were edited by hand: re-generating such a block from its tool '
                               'replaces its faces and discards these edits' % ', '.join(touched)]
        rep.update(faces_before=len(o.F), faces_after=len(o1.F), changed_or_new_faces=len(changed),
                   max_nonplanarity_m=round(max([tm.planarity(o1.pts(li)) for li in changed] or [0.0]), 4))
        return after, rep, hl

    def _mesh_key(self, op, a):
        return self._cons_key('mesh:' + op, a)

    def mesh_preview(self, op=None, **a):
        """TE stage 4: a mesh edit (transform / delete / triangulate / subdivide / extrude / fill) WITHOUT changing anything. Light
        checks only (kit re-read, trackbuild's face rule); Apply adds the clip rule, structural route checks, the non-manifold
        count and the kit dry run."""
        after, rep, hl = self._mesh_plan(op, a)
        return dict(rep, ok=True, op=op, new_faces=hl, preview_key=self._mesh_key(op, a), note='preview only: nothing changed',
                    summary_lines=['mesh %s: %d -> %d faces, %d changed / new face(s), max non-planarity %.4f m' % (
                        op, rep['faces_before'], rep['faces_after'], rep['changed_or_new_faces'], rep['max_nonplanarity_m'])])

    def mesh(self, op=None, preview_key=None, **a):
        import wb_te_mesh as tm
        if preview_key != self._mesh_key(op, a):
            raise E('NEEDS PREVIEW: preview this mesh edit first and apply it with its preview_key')
        after, rep, hl = self._mesh_plan(op, a)
        before = self.obj_cur
        # clip rule on every face: no face may lose more area outside the unit regions than the same face did before
        c0, c1 = self.coverage(before), self.coverage(after)
        # measured in PLAN (x, z): the unit regions cut vertically, and a non-planar quad's 3-D fan area differs from the sum of its
        # clipped pieces' fan areas (a false "loss" on a pure vertical move: found by test_te34 m02)
        UN = T['kit_trackbuild'](self.cfg)['units']

        def plan_loss(f, units):
            fv = [((p[0], 0.0, p[2]), (0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 1.0)) for p in f['pts']]
            area = T['_poly_area']([v[0] for v in fv])
            kept = T['_union_area'](UN, units, fv, sorted(f['pieces'])) if f['pieces'] else 0.0
            return max(0.0, area - kept)
        loss0 = {}
        old_keys = set()
        for f in c0['faces']:
            old_keys.add((f['mat'], tuple(map(tuple, f['pts']))))
        bad = []
        for f in c1['faces']:
            key = (f['mat'], tuple(map(tuple, f['pts'])))
            if key in old_keys:
                continue                                    # an unchanged face: unchanged clip
            l1 = plan_loss(f, c1['units'])
            if l1 > T['CLIP_TOL_M2'] + 0.5e-4 * sum(math.dist(f['pts'][q], f['pts'][(q + 1) % len(f['pts'])]) for q in range(len(f['pts']))):
                bad.append({'corners': [list(p) for p in f['pts']], 'lost_m2': round(l1, 5), 'material': f['mat']})
        if bad:
            raise E('mesh %s refused: %d face(s) would lie (partly) outside the unit regions (Build would drop %.4f m2); unit regions '
                    'are never expanded automatically. Nothing changed' % (op, len(bad), sum(x['lost_m2'] for x in bad)),
                    {'lost_faces': bad[:200]})
        nm0, nm1 = tm.non_manifold(tm.Obj(before)), tm.non_manifold(tm.Obj(after))
        if nm1 > nm0:
            raise E('mesh %s refused: the result has %d more non-manifold edge(s) (an edge used by more than two faces). Nothing '
                    'changed' % (op, nm1 - nm0))
        structural = None
        if self.desc().get('stations'):
            r0, r1 = self.race_check(before), self.race_check(after)
            ok0 = {c['check']: c['ok'] for c in r0['structural']}
            newly = [c for c in r1['structural'] if not c['ok'] and ok0.get(c['check'], False)]
            if newly:
                raise E('mesh %s refused: the route\'s structural check(s) %s would fail (e.g. the drivable floor or a wall the kit '
                        'gates probe was edited away): %s. Nothing changed' % (op, ', '.join(c['check'] for c in newly),
                                                                             json.dumps(newly[0]['detail'])[:300]),
                        {'structural': r1['structural']})
            structural = 'route structural checks unchanged (%s)' % ', '.join('%s %s' % (c['check'], 'ok' if c['ok'] else 'FAILED')
                                                                               for c in r1['structural'])
        try:
            base = self.regenerate(before)
        except T['EditError']:
            base = None
        regen = self.regenerate(after)
        label = 'mesh %s (%d -> %d faces)' % (op, rep['faces_before'], rep['faces_after'])
        self._push('obj', label, after, kind='mesh', index=None)
        return dict(rep, ok=True, op=op, label=label, new_faces=hl, structural_checks=structural, non_manifold_edges=[nm0, nm1],
                    clipping={'refused': False, 'faces_checked': len(c1['faces'])}, regenerated=self._regen_report(base, regen),
                    summary_lines=[label, 'checks: kit re-read, face rule, clip rule (%d faces), non-manifold edges %d -> %d, %s, kit dry run'
                                   % (len(c1['faces']), nm0, nm1, structural or 'no route')])

    def mesh_preview_api(self, mesh_op=None, **a):
        return self.mesh_preview(mesh_op, **a)

    def mesh_api(self, mesh_op=None, preview_key=None, **a):
        return self.mesh(mesh_op, preview_key, **a)

    def mesh_info(self, groups=None, open_loops=False):
        """read only: the faces of the given face groups (line, material, v / vt / vn per corner, positions) and, on request, the
        open-edge loops (by position) as v index lists for an explicit hole fill"""
        import wb_te_mesh as tm
        o = tm.Obj(self.obj_cur)
        if not isinstance(groups, list) or not all(isinstance(g, int) and 0 <= g < len(o.groups) for g in groups):
            raise E('groups: a list of face group indices (0..%d)' % (len(o.groups) - 1))
        if sum(len(o.groups[g]['faces']) for g in groups) > 5000:
            raise E('more than 5000 faces selected: select fewer face groups')
        faces = [{'line': li + 1, 'group': g, 'material': o.groups[g]['mat'], 'corners': [list(c) for c in o.F[li]],
                  'pts': [o.V[v - 1] for v, _t, _n in o.F[li]]} for g in groups for li in o.groups[g]['faces']]
        out = {'ok': True, 'faces': faces, 'count': len(faces)}
        if open_loops:
            sel = [li for g in groups for li in o.groups[g]['faces']]
            use = o.edge_use()
            nxt = {}
            for li in sel:
                cs = o.F[li]
                for i in range(len(cs)):
                    a, b = cs[i][0], cs[(i + 1) % len(cs)][0]
                    e = tuple(sorted((tm.pkey(o.V[a - 1]), tm.pkey(o.V[b - 1]))))
                    if len(use.get(e, [])) == 1:
                        nxt[tm.pkey(o.V[b - 1])] = (tm.pkey(o.V[a - 1]), a)   # walk against the face winding
            loops, seen = [], set()
            for start in list(nxt):
                if start in seen:
                    continue
                cur, lp = start, []
                while cur in nxt and cur not in seen:
                    seen.add(cur)
                    k, v = nxt[cur]
                    lp.append(v)
                    cur = k
                if cur == start and len(lp) >= 3:
                    loops.append(lp[::-1])
            out['open_loops'] = loops[:50]
            out['open_loop_count'] = len(loops)
        return out

    # ================================================================== stage 5: materials and textures
    MAX_TEXTURE_BYTES = 8 * 1024 * 1024

    def _protected_source(self, path):
        import os
        n = os.path.normcase(os.path.abspath(path))
        for k in ('game_data', 'kit'):
            r = self.cfg.get(k)
            if r and (n + os.sep).startswith(os.path.normcase(os.path.abspath(r)) + os.sep):
                return '%s folder (%s)' % (k.replace('_', ' '), r)
        if (n + os.sep).startswith(os.path.normcase(self.project) + os.sep):
            return 'this project (reference project PNGs directly)'
        return None

    def _texture_req(self, source, name, author, licence, note):
        import os
        import re
        if not (isinstance(source, str) and os.path.isabs(source) and source.lower().endswith('.png')):
            raise E('source: an absolute path of an ORIGINAL .png file (your own artwork)')
        if not os.path.isfile(source) or os.path.islink(source):
            raise E('source %r is not a regular file' % source)
        why = self._protected_source(source)
        if why:
            raise E('source refused: it lies in the %s - import only your own original textures; retail / kit data is never '
                    'imported' % why)
        if not (isinstance(name, str) and re.match(r'^[a-z0-9_]{1,24}$', name)):
            raise E('name %r: 1..24 lower-case letters, digits or _ (the file becomes textures/<name>.png)' % (name,))
        for k, v in (('author', author), ('licence', licence)):
            if not (isinstance(v, str) and 1 <= len(v.strip()) <= 200):
                raise E('%s: required (1..200 characters) - the provenance record of an imported texture' % k)
        rel = 'textures/%s.png' % name
        import wb_stage as stg
        if rel in stg.tree_hashes(self.project) or rel in self.pending:
            raise E('%s exists already: choose another name (imports never overwrite)' % rel)
        b = open(source, 'rb').read()
        if len(b) > self.MAX_TEXTURE_BYTES:
            raise E('source is %d bytes: at most %d' % (len(b), self.MAX_TEXTURE_BYTES))
        K = T['kit_trackbuild'](self.cfg)
        try:
            w, h, _rows, amin = png_alpha_bytes(self, b)
        except Exception as e:  # noqa: BLE001   the kit reader's refusal (format), reported
            raise E('texture refused by the kit PNG reader (8-bit RGB / RGBA, non-interlaced): %s' % e)
        if amin != 255:
            raise E('texture refused: it has transparent pixels (min alpha %d) - trackbuild materials are opaque (DXT1)' % amin)
        try:
            d = _tmpdir(self)
            import shutil
            try:
                p = os.path.join(d, name + '.png')
                open(p, 'wb').write(b)
                tw, th, rgb = K['io'].read_png(p)
                K['build'].texture_record(name, tw, th, rgb)
            finally:
                shutil.rmtree(d, ignore_errors=True)
        except K['io'].SourceError as e:
            raise E('texture refused by the kit rules: %s' % e)
        import hashlib as hl
        return {'source': source, 'rel': rel, 'bytes': b, 'size': [w, h],
                'meta': {'source_path': source, 'source_sha256': hl.sha256(b).hexdigest(), 'bytes': len(b), 'size': [w, h],
                         'author': author.strip(), 'licence': licence.strip(), 'note': (note or '').strip()[:300],
                         'kind': 'ORIGINAL texture imported by the user (not retail-derived)'}}

    def texture_import_preview(self, source=None, name=None, author=None, licence=None, note=None):
        """TE stage 5: check an original PNG for import (kit PNG rules, opaque, power of two 4..1024), WITHOUT changing anything"""
        r = self._texture_req(source, name, author, licence, note)
        key = self._cons_key('tex', {k: v for k, v in r.items() if k != 'bytes'})
        return {'ok': True, 'texture': r['rel'], 'size': r['size'], 'provenance': r['meta'], 'preview_key': key,
                'note': 'preview only: nothing changed; Apply keeps the file in the editor until Save writes it into the project '
                        '(the source file is only read)',
                'summary_lines': ['import %s (%d x %d) from %s; author %s, licence %s' % (r['rel'], r['size'][0], r['size'][1], source,
                                                                                       r['meta']['author'], r['meta']['licence'])]}

    def texture_import(self, source=None, name=None, author=None, licence=None, note=None, preview_key=None):
        r = self._texture_req(source, name, author, licence, note)
        if preview_key != self._cons_key('tex', {k: v for k, v in r.items() if k != 'bytes'}):
            raise E('NEEDS PREVIEW: preview this import first and apply it with its preview_key')
        label = 'import texture %s (%d x %d)' % (r['rel'], r['size'][0], r['size'][1])
        self.pending_meta[r['rel']] = r['meta']
        self._push('file:' + r['rel'], label, r['bytes'], kind='texture', index=r['rel'])
        return {'ok': True, 'label': label, 'texture': r['rel'], 'provenance': r['meta'],
                'note': 'held in the editor (undoable); Save writes it into the project with the provenance record %s' % PROVENANCE}

    def _material_req(self, name, texture, surface, collide, car_solid, like):
        import re
        d = self.desc()
        mats = d.get('materials') or {}
        rows = d.get('rows') or []
        if not (isinstance(name, str) and re.match(r'^[A-Za-z0-9_]{1,32}$', name)):
            raise E('material name %r: 1..32 letters, digits or _' % (name,))
        if name in mats:
            raise E('material %s exists already' % name)
        if len(rows) >= 83:
            raise E('the description has %d render rows: trackbuild allows at most 83' % len(rows))
        if like is not None:
            if like not in mats:
                raise E('material %r to duplicate does not exist' % (like,))
            m = dict(mats[like])
        else:
            m = {}
        for k, v in (('texture', texture), ('surface', surface), ('collide', collide), ('car_solid', car_solid)):
            if v is not None:
                m[k] = v
        if not isinstance(m.get('texture'), str):
            raise E('texture: a project PNG (e.g. textures/bm_grass.png) or an imported one')
        m['texture'] = m['texture'].replace('\\', '/')
        if not isinstance(m.get('surface'), str) or not re.match(r'^0x[0-9A-Fa-f]{1,4}$', m['surface'].strip()):
            raise E('surface: a hex word such as "0x0001" (documented meanings in the material panel; unknown words are labelled '
                    'unknown, never interpreted)')
        m['surface'] = '0x%04X' % int(m['surface'], 16)
        for k in ('collide', 'car_solid'):
            if k in m and not isinstance(m[k], bool):
                raise E('%s must be true or false' % k)
        extra = set(m) - {'texture', 'surface', 'collide', 'car_solid'}
        if extra:
            raise E('keys %s refused: trackbuild materials have only texture / surface / collide / car_solid (alpha, blend, shaders '
                    'and animation are not supported by the format)' % ', '.join(sorted(extra)))
        import wb_stage as stg
        if m['texture'] not in stg.tree_hashes(self.project) and m['texture'] not in self.pending:
            raise E('texture %s is neither a project file nor an imported texture' % m['texture'])
        # the kit's own rules on the new material (texture through a temporary copy when it is still pending)
        import os
        import shutil
        K = T['kit_trackbuild'](self.cfg)
        dtmp = _tmpdir(self)
        try:
            tp = os.path.join(dtmp, *m['texture'].split('/'))
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            with open(tp, 'wb') as f:
                f.write(self.pending.get(m['texture']) or open(os.path.join(self.project, *m['texture'].split('/')), 'rb').read())
            op_ = os.path.join(dtmp, *str(d.get('obj', '')).replace('\\', '/').split('/'))     # preflight checks the OBJ exists
            os.makedirs(os.path.dirname(op_), exist_ok=True)
            with open(op_, 'wb') as f:
                f.write(self.obj_cur or b'')
            K['preflight'].check_desc(dtmp, {'materials': {name: m}, 'rows': [name], 'obj': d.get('obj')})
            w = int(m['surface'], 16)
            if m.get('collide') and m.get('car_solid', True) and w & 0x1000:
                raise K['io'].SourceError('surface 0x%04X has flag 0x10 (not solid for cars): use car_solid false' % w)
            tw, th, rgb = K['io'].read_png(tp)
            K['build'].texture_record(os.path.splitext(os.path.basename(tp))[0], tw, th, rgb)
        except K['io'].SourceError as e:
            raise E('material refused by the kit trackbuild rules: %s' % e)
        finally:
            shutil.rmtree(dtmp, ignore_errors=True)
        return {'name': name, 'm': m, 'like': like}

    def _material_after(self, req):
        sp = T['json_spans'](self.cur)
        d = self.desc()
        mats, rows = d.get('materials') or {}, d.get('rows') or []
        b = bytearray(self.cur)
        ins = []
        mm = json.dumps(req['m'], sort_keys=True).encode('ascii')
        if mats:
            e = sp[('materials', list(mats)[-1])][1]
            ins.append((e, b', ' + json.dumps(req['name']).encode('ascii') + b': ' + mm))
        else:
            s_, e = sp[('materials',)]
            ins.append((e - 1, json.dumps(req['name']).encode('ascii') + b': ' + mm))
        if rows:
            e = sp[('rows', len(rows) - 1)][1]
            ins.append((e, b', ' + json.dumps(req['name']).encode('ascii')))
        else:
            s_, e = sp[('rows',)]
            ins.append((e - 1, json.dumps(req['name']).encode('ascii')))
        for at, x in sorted(ins, key=lambda z: -z[0]):
            b[at:at] = x
        after = bytes(b)
        d2 = json.loads(after.decode('utf-8'))
        want = dict(d, materials=dict(mats, **{req['name']: req['m']}), rows=rows + [req['name']])
        if d2 != want:
            raise E('internal: the material splice changed more than the new material / row; not applied')
        return after

    def material_create_preview(self, name=None, texture=None, surface=None, collide=None, car_solid=None, like=None):
        """TE stage 5: a new material (or a duplicate of `like` with changes) + its render row, checked by the kit rules, WITHOUT
        changing anything"""
        req = self._material_req(name, texture, surface, collide, car_solid, like)
        self._material_after(req)
        return {'ok': True, 'material': req['name'], 'properties': req['m'], 'duplicate_of': like,
                'preview_key': self._cons_key('mat', req), 'note': 'preview only: nothing changed',
                'summary_lines': ['new material %s%s: %s (one render row appended)' % (req['name'], ' (copy of %s)' % like if like else '',
                                                                                      json.dumps(req['m']))]}

    def material_create(self, name=None, texture=None, surface=None, collide=None, car_solid=None, like=None, preview_key=None):
        req = self._material_req(name, texture, surface, collide, car_solid, like)
        if preview_key != self._cons_key('mat', req):
            raise E('NEEDS PREVIEW: preview this material first and apply it with its preview_key')
        after = self._material_after(req)
        label = 'new material %s%s' % (req['name'], ' (copy of %s)' % like if like else '')
        self._push('desc', label, after, kind='material', index=req['name'])
        return {'ok': True, 'label': label, 'material': req['name'], 'properties': req['m'],
                'note': 'assign it to face groups with the material tools (existing materials only there)'}

    def _uv_plan(self, groups, scale, offset, rotate):
        import wb_te_mesh as tm
        o = tm.Obj(self.obj_cur)
        if not (isinstance(groups, list) and groups and all(isinstance(g, int) and 0 <= g < len(o.groups) for g in groups)):
            raise E('groups: face group indices (0..%d)' % (len(o.groups) - 1))
        sc = scale if scale is not None else [1, 1]
        of = offset if offset is not None else [0, 0]
        if not (isinstance(sc, list) and len(sc) == 2 and all(num(v, 0.01, 100) for v in sc)):
            raise E('scale: [su, sv], each 0.01..100')
        if not (isinstance(of, list) and len(of) == 2 and all(num(v, -1000, 1000) for v in of)):
            raise E('offset: [ou, ov], each -1000..1000')
        if not num(rotate, -360, 360):
            raise E('rotate: -360..360 degrees')
        if sc == [1, 1] and of == [0, 0] and not rotate:
            raise E('nothing to do (scale 1, offset 0, rotation 0)')
        a = math.radians(rotate)
        c, s = math.cos(a), math.sin(a)
        w = tm.Writer(o)
        n = 0
        for g in groups:
            for li in o.groups[g]['faces']:
                cs = []
                for v, t, nn in o.F[li]:
                    u0, v0 = o.VT[t - 1]
                    u1, v1 = u0 * sc[0], v0 * sc[1]
                    cs.append((v, w.vt((c * u1 - s * v1 + of[0], s * u1 + c * v1 + of[1])), nn))
                w.replace[li] = [o.face_line(cs)]
                n += 1
        try:
            after = w.build()
        except tm.MeshError as e:
            raise E('uv edit refused: %s. Nothing changed' % e)
        return after, {'faces': n, 'groups': groups, 'scale': sc, 'offset': of, 'rotate': rotate,
                       'rule': "u' = R(rotate) (su u, sv v) + offset; new vt lines appended (shared vt lines of other faces untouched)"}

    def uv_transform_preview(self, groups=None, scale=None, offset=None, rotate=0.0):
        after, rep = self._uv_plan(groups, scale, offset, rotate)
        self._kit_read(after)
        return dict(rep, ok=True, preview_key=self._cons_key('uv', [groups, scale, offset, rotate]), note='preview only: nothing changed',
                    summary_lines=['uv transform of %d face(s): scale %s, offset %s, rotate %s deg' % (rep['faces'], rep['scale'], rep['offset'], rotate)])

    def uv_transform(self, groups=None, scale=None, offset=None, rotate=0.0, preview_key=None):
        if preview_key != self._cons_key('uv', [groups, scale, offset, rotate]):
            raise E('NEEDS PREVIEW: preview this uv edit first and apply it with its preview_key')
        after, rep = self._uv_plan(groups, scale, offset, rotate)
        self._kit_read(after)
        base = self.regenerate(self.obj_cur)
        regen = self.regenerate(after)
        label = 'uv transform of %d face(s)' % rep['faces']
        self._push('obj', label, after, kind='uv', index=groups)
        return dict(rep, ok=True, label=label, regenerated=self._regen_report(base, regen))

    def _paint_plan(self, groups, centre, radius, colour, strength):
        import wb_te_mesh as tm
        o = tm.Obj(self.obj_cur)
        if not (isinstance(groups, list) and groups and all(isinstance(g, int) and 0 <= g < len(o.groups) for g in groups)):
            raise E('groups: face group indices to paint (0..%d)' % (len(o.groups) - 1))
        if not (isinstance(centre, list) and len(centre) in (2, 3) and all(num(v, -1e6, 1e6) for v in centre)):
            raise E('centre: [x, z] or [x, y, z] (plan distance is used)')
        cx, cz = (centre[0], centre[-1])
        if not num(radius, 0.1, 500):
            raise E('radius: 0.1..500 m')
        if not (isinstance(colour, list) and len(colour) == 3 and all(num(v, 0, 1) for v in colour)):
            raise E('colour: [r, g, b], each 0..1 (the baked vertex light; 0.2 = the demo neutral)')
        if not num(strength, 0.01, 1):
            raise E('strength: 0.01..1')
        target = {li for g in groups for li in o.groups[g]['faces']}
        users = {}
        for li, cs in o.F.items():
            for v, _t, _n in cs:
                users.setdefault(v, set()).add(li)
        w = tm.Writer(o)
        newcol, dup, rewritten = {}, {}, set()
        for li in sorted(target):
            for v, _t, _n in o.F[li]:
                if v in newcol:
                    continue
                p = o.V[v - 1]
                d = math.hypot(p[0] - cx, p[2] - cz)
                if d >= radius:
                    continue
                if len(o.VC[v - 1]) != 3:
                    raise E('vertex %d has no baked colour tokens: set a group colour first (the material tools) - the editor does '
                            'not guess a default' % v)
                f = tg.smooth(1 - d / radius) * strength
                cur = [float(x) for x in o.VC[v - 1]]
                newcol[v] = [tm._fmt(cur[k] + (colour[k] - cur[k]) * f, 3) for k in range(3)]
        if not newcol:
            raise E('no vertex of the given groups lies within the radius: nothing to paint')
        for v, col in newcol.items():
            if users[v] <= target:                          # used only by painted faces: its colour tokens change in place
                w.replace[o.vl[v - 1]] = [('v ' + ' '.join([tm._fmt(x, 4) for x in o.V[v - 1]] + col)).encode('ascii') + o.eol]
            else:                                           # shared with unpainted faces: a painted copy for the painted faces
                dup[v] = w.v(o.V[v - 1], col, reuse=False)
        for li in sorted(target):
            if any(v in dup for v, _t, _n in o.F[li]):
                w.replace[li] = [o.face_line([(dup.get(v, v), t, n) for v, t, n in o.F[li]])]
                rewritten.add(li)
        try:
            after = w.build()
        except tm.MeshError as e:
            raise E('paint refused: %s. Nothing changed' % e)
        return after, {'painted_vertices': len(newcol), 'copied_shared_vertices': len(dup), 'faces_repointed': len(rewritten),
                       'colour': colour, 'strength': strength, 'radius': radius,
                       'rule': 'colour += (target - colour) x strength x smoothstep(1 - d / radius); vertices shared with unpainted '
                               'faces are copied so no other face changes colour'}

    def paint_preview(self, groups=None, centre=None, radius=5.0, colour=None, strength=1.0):
        after, rep = self._paint_plan(groups, centre, radius, colour, strength)
        return dict(rep, ok=True, preview_key=self._cons_key('paint', [groups, centre, radius, colour, strength]),
                    note='preview only: nothing changed', summary_lines=['paint %d vertex colour(s) (%d shared copied)' % (
                        rep['painted_vertices'], rep['copied_shared_vertices'])])

    def paint(self, groups=None, centre=None, radius=5.0, colour=None, strength=1.0, preview_key=None):
        if preview_key != self._cons_key('paint', [groups, centre, radius, colour, strength]):
            raise E('NEEDS PREVIEW: preview this paint stroke first and apply it with its preview_key')
        after, rep = self._paint_plan(groups, centre, radius, colour, strength)
        self._kit_read(after)
        base = self.regenerate(self.obj_cur)
        regen = self.regenerate(after)
        label = 'paint %d vertex colour(s)' % rep['painted_vertices']
        self._push('obj', label, after, kind='paint', index=groups)
        return dict(rep, ok=True, label=label, regenerated=self._regen_report(base, regen))

    # ================================================================== stage 6: scenery
    COPY_NOTE = ('trackbuild has no instances / props: every placement is a GEOMETRY COPY in the OBJ (counted in the unit capacity). '
                 'The editor remembers which prefab (name + sha256) each block came from, so "refresh copies" re-generates the copies '
                 'of a changed prefab on request - never automatically')

    def _prefab_svg(self, faces):
        """a small top + side view of prefab faces (SVG text; plan x-z left, elevation x-y right)"""
        P = [c[0] for _m, cs in faces for c in cs]
        if not P:
            return ''
        x0, x1 = min(p[0] for p in P), max(p[0] for p in P)
        y0, y1 = min(p[1] for p in P), max(p[1] for p in P)
        z0, z1 = min(p[2] for p in P), max(p[2] for p in P)
        sc = 52.0 / max(x1 - x0, z1 - z0, y1 - y0, 1e-6)
        cols = {}
        out = ['<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">',
               '<rect width="120" height="60" fill="#e8e8e4"/>']
        for m, cs in faces:
            col = cols.setdefault(m, '#%06x' % (int(hashlib.sha256(m.encode()).hexdigest()[:6], 16) & 0x7f7f7f))
            top = ' '.join('%.1f,%.1f' % (4 + (c[0][0] - x0) * sc, 4 + (c[0][2] - z0) * sc) for c in cs)
            side = ' '.join('%.1f,%.1f' % (64 + (c[0][0] - x0) * sc, 56 - (c[0][1] - y0) * sc) for c in cs)
            out.append('<polygon points="%s" fill="%s" fill-opacity="0.5" stroke="%s" stroke-width="0.3"/>' % (top, col, col))
            out.append('<polygon points="%s" fill="%s" fill-opacity="0.35" stroke="%s" stroke-width="0.3"/>' % (side, col, col))
        out.append('</svg>')
        return ''.join(out)

    def prefab_library(self, query=None):
        """read only: the saved prefabs with size, materials, faces, origin project and a generated top / side preview; `query`
        filters by name or material (case-insensitive)"""
        out = []
        q = (query or '').strip().lower()
        mats = self.desc().get('materials') or {}
        for name in self.prefabs()['prefabs']:
            try:
                pf = self._prefab_read(name)
            except T['EditError'] as e:
                out.append({'name': name, 'ok': False, 'why': str(e)})
                continue
            fm = sorted({m for m, _cs in pf['faces']})
            if q and q not in name.lower() and not any(q in m.lower() for m in fm):
                continue
            P = [c[0] for _m, cs in pf['faces'] for c in cs]
            out.append({'name': name, 'ok': True, 'faces': len(pf['faces']), 'materials': fm,
                        'missing_materials_here': [m for m in fm if m not in mats],
                        'size_m': [round(max(p[k] for p in P) - min(p[k] for p in P), 3) for k in range(3)],
                        'from_project': (pf.get('from') or {}).get('project'), 'sha256': pf['sha256'][:16],
                        'preview_svg': self._prefab_svg(pf['faces'])})
        return {'ok': True, 'prefabs': out, 'folder': self.prefabs()['folder'], 'copies': self.COPY_NOTE,
                'summary_lines': ['%d prefab(s)%s: %s' % (len(out), ' matching %r' % q if q else '', ', '.join(
                    '%s (%d faces, %s m)' % (x['name'], x.get('faces', 0), x.get('size_m')) for x in out[:12]))]}

    def _ground_y(self, x, z, exclude_groups=()):
        ys = [y for f in self._floor_faces(set(exclude_groups)) for y in [tg._poly_y(f['pts'], x, z)] if y is not None]
        return max(ys) if ys else None

    def _collision_map(self, mats, collision):
        """'keep' = the prefab's materials; 'none' = each material's existing non-colliding twin <name>_nc (create it with
        "New / duplicate material": duplicate, collide false) - never created automatically"""
        if collision == 'keep':
            return {m: m for m in mats}
        if collision != 'none':
            raise E("collision: 'keep' (the prefab's materials) or 'none' (each material's <name>_nc twin without collision)")
        d = self.desc().get('materials') or {}
        out, missing = {}, []
        for m in mats:
            tw = m + '_nc'
            if tw in d and d[tw].get('collide') is False and tw in (self.desc().get('rows') or []):
                out[m] = tw
            else:
                missing.append(tw)
        if missing:
            raise E('collision "none" needs the non-colliding twin material(s) %s (duplicate the material with collide false using '
                    '"New / duplicate material"); not created automatically' % ', '.join(missing))
        return out

    def _placed_faces(self, pf, position, angle, cmap):
        faces = [(cmap[m], [(tuple(p), tuple(uv), tuple(n), tuple(c)) for p, uv, n, c in cs]) for m, cs in pf['faces']]
        return wc.transform_faces(faces, position, angle, (0.0, 0.0, 0.0))

    def _place_req(self, name, position, angle, snap, angle_snap, ground, collision, id_):
        import re
        if not (isinstance(name, str) and re.match(r'^[A-Za-z0-9_-]{1,40}$', name)):
            raise E('prefab name %r' % (name,))
        pf = self._prefab_read(name)
        if not (isinstance(position, list) and len(position) == 3 and all(num(v, -1e6, 1e6) for v in position)):
            raise E('position: [x, y, z] metres')
        if not num(angle, -360, 360):
            raise E('angle: -360..360 degrees')
        if snap is not None and not num(snap, 0.01, 100):
            raise E('snap: a grid step 0.01..100 m (or empty)')
        if angle_snap is not None and not num(angle_snap, 1, 180):
            raise E('angle_snap: 1..180 degrees (or empty)')
        if not isinstance(ground, bool):
            raise E('ground must be true (drop onto the highest collision floor below) or false')
        cmap = self._collision_map(sorted({m for m, _cs in pf['faces']}), collision)
        for m in cmap.values():
            self._mat_ok(m, 'prefab')
        pos = [round(round(v / snap) * snap, 6) if snap else float(v) for v in position]
        ang = round(round(angle / angle_snap) * angle_snap, 6) if angle_snap else float(angle)
        if ground:
            g = self._ground_y(pos[0], pos[2], self.constructs()[id_]['groups'] if id_ else ())
            if g is None:
                raise E('ground: no collision floor below (%.2f, %.2f)' % (pos[0], pos[2]))
            pos[1] = round(g, 4)
        if id_ is not None:
            C = self.constructs()
            if id_ not in C or C[id_]['meta'].get('kind') != 'placed':
                raise E('placed copy %r does not exist' % (id_,))
        return {'name': name, 'position': pos, 'angle': ang, 'collision': collision, 'snap': snap, 'angle_snap': angle_snap,
                'ground': ground, 'prefab_sha256': pf['sha256'], 'id': id_, 'requested': [list(position), angle]}

    def _place_plan(self, req):
        pf = self._prefab_read(req['name'])
        cmap = self._collision_map(sorted({m for m, _cs in pf['faces']}), req['collision'])
        try:
            faces = self._placed_faces(pf, req['position'], req['angle'], cmap)
        except wc.ConstructError as e:
            raise E('placement refused: %s' % e)
        C = self.constructs()
        repl = C[req['id']]['groups'] if req['id'] else []
        rid = req['id'] or self._new_id('placed')
        meta = {'kind': 'placed', 'id': rid, 'name': req['name'], 'position': req['position'], 'angle': req['angle'],
                'collision': req['collision'], 'prefab_sha256': req['prefab_sha256']}
        after, blk = self._block_bytes(faces, meta, repl)
        warn = self._route_floor_warnings(blk['faces'])
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'placed': rid, 'prefab': req['name'], 'position': req['position'], 'angle': req['angle'],
                            'snapped_from': req['requested'], 'collision': req['collision'], 'materials': sorted(set(cmap.values())),
                            'faces': len(faces), 'copies': self.COPY_NOTE, 'warnings': warn, 'markers': [req['position']],
                            'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]], 'v_added': blk['v_added'],
                            'vt_added': blk['vt_added'], 'vn_added': blk['vn_added'], 'removed_faces': blk['removed_faces'],
                            'summary_lines': ['copy of prefab %s at %s turned %s deg (requested %s), collision %s, %d faces' % (
                                req['name'], req['position'], req['angle'], req['requested'], req['collision'], len(faces))] +
                            ['WARNING: ' + w for w in warn]}}

    def prefab_place_preview(self, name=None, position=None, angle=0.0, snap=None, angle_snap=None, ground=False, collision='keep',
                             id=None):  # noqa: A002
        """TE stage 6: one prefab COPY with grid / angle snapping, optional drop to the floor below and a collision option,
        WITHOUT changing anything"""
        req = self._place_req(name, position, angle, snap, angle_snap, ground, collision, id)
        plan = self._place_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('place', req), note='preview only: nothing changed')

    def prefab_place(self, name=None, position=None, angle=0.0, snap=None, angle_snap=None, ground=False, collision='keep', id=None,  # noqa: A002
                     preview_key=None):
        req = self._place_req(name, position, angle, snap, angle_snap, ground, collision, id)
        if preview_key != self._cons_key('place', req):
            raise E('NEEDS PREVIEW: preview this placement first and apply it with its preview_key')
        plan = self._place_plan(req)
        S = plan['summary']
        label = '%s copy %s of prefab %s (%d faces)' % ('re-generate' if id else 'place', plan['id'], name, S['faces'])
        return dict(S, **self._apply_block(plan, label, 'prefab', S['faces']))

    def _scatter_req(self, name, points, closed, spacing, offset, align, angle, start, ground, collision, max_count, id_):
        pf = self._prefab_read(name) if isinstance(name, str) else None
        if pf is None:
            raise E('name: a saved prefab')
        try:
            P = wc.check_points(points, closed)
        except wc.ConstructError as e:
            raise E('path refused: %s' % e)
        for k, v, lo, hi in (('spacing', spacing, 0.5, 500), ('offset', offset, -200, 200), ('angle', angle, -360, 360),
                             ('start', start, 0, 500)):
            if not num(v, lo, hi):
                raise E('%s %r: %g..%g' % (k, v, lo, hi))
        if not isinstance(align, bool) or not isinstance(ground, bool) or not isinstance(closed, bool):
            raise E('align / ground / closed must be true or false')
        if not (isinstance(max_count, int) and 1 <= max_count <= 500):
            raise E('max_count: 1..500 copies')
        self._collision_map(sorted({m for m, _cs in pf['faces']}), collision)
        if id_ is not None:
            C = self.constructs()
            if id_ not in C or C[id_]['meta'].get('kind') != 'scatter':
                raise E('scatter %r does not exist' % (id_,))
        return {'name': name, 'points': P, 'closed': closed, 'spacing': float(spacing), 'offset': float(offset), 'align': align,
                'angle': float(angle), 'start': float(start), 'ground': ground, 'collision': collision, 'max_count': max_count,
                'prefab_sha256': pf['sha256'], 'id': id_}

    def _scatter_plan(self, req):
        pf = self._prefab_read(req['name'])
        cmap = self._collision_map(sorted({m for m, _cs in pf['faces']}), req['collision'])
        try:
            S, L = wc.sample(req['points'], req['closed'], step=0.25)
        except wc.ConstructError as e:
            raise E('path refused: %s' % e)
        acc = [0.0]
        for i in range(1, len(S)):
            acc.append(acc[-1] + math.dist(S[i - 1], S[i]))
        C = self.constructs()
        excl = C[req['id']]['groups'] if req['id'] else []
        spots, faces = [], []
        s_ = req['start']
        k = 0
        while s_ <= acc[-1] + 1e-9 and len(spots) < req['max_count']:
            while k + 1 < len(acc) - 1 and acc[k + 1] < s_:
                k += 1
            f = 0.0 if acc[k + 1] == acc[k] else (s_ - acc[k]) / (acc[k + 1] - acc[k])
            p = [S[k][j] + (S[k + 1][j] - S[k][j]) * f for j in range(3)]
            tx, tz = S[k + 1][0] - S[k][0], S[k + 1][2] - S[k][2]
            ln = math.hypot(tx, tz) or 1.0
            tx, tz = tx / ln, tz / ln
            p = [p[0] - tz * req['offset'], p[1], p[2] + tx * req['offset']]   # lateral offset along n+ = (-tz, tx)
            # yaw: the editor's convention (+ = counter-clockwise seen from above: +x towards -z); align = face along the path
            ang = (math.degrees(math.atan2(-tz, tx)) if req['align'] else 0.0) + req['angle']
            if req['ground']:
                g = self._ground_y(p[0], p[2], excl)
                if g is None:
                    raise E('ground: no collision floor below copy %d at (%.2f, %.2f)' % (len(spots), p[0], p[2]))
                p[1] = g
            p = [round(v, 4) for v in p]
            spots.append({'s': round(s_, 3), 'position': p, 'angle': round(ang, 4)})
            faces += self._placed_faces(pf, p, ang, cmap)
            s_ += req['spacing']
        if not spots:
            raise E('the path is shorter than the start distance: no copy')
        rid = req['id'] or self._new_id('scatter')
        meta = {k: v for k, v in req.items() if k != 'id'}
        meta.update(kind='scatter', id=rid, copies=len(spots))
        after, blk = self._block_bytes(faces, meta, excl)
        warn = self._route_floor_warnings(blk['faces'])
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'scatter': rid, 'prefab': req['name'], 'copies': len(spots), 'spots': spots[:200], 'faces': len(faces),
                            'path_m': round(acc[-1], 3), 'collision': req['collision'], 'copies_note': self.COPY_NOTE,
                            'warnings': warn, 'markers': [x['position'] for x in spots[:500]],
                            'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]], 'v_added': blk['v_added'],
                            'vt_added': blk['vt_added'], 'vn_added': blk['vn_added'], 'removed_faces': blk['removed_faces'],
                            'summary_lines': ['%d copies of %s along %.1f m every %g m (offset %g m, %s), %d faces, collision %s' % (
                                len(spots), req['name'], acc[-1], req['spacing'], req['offset'],
                                'aligned to the path' if req['align'] else 'fixed angle', len(faces), req['collision'])] +
                            ['WARNING: ' + w for w in warn]}}

    def prefab_scatter_preview(self, name=None, points=None, closed=False, spacing=10.0, offset=0.0, align=True, angle=0.0,  # noqa: A002
                               start=0.0, ground=False, collision='keep', max_count=100, id=None):  # noqa: A002
        """TE stage 6: repeated prefab COPIES along a path (spacing, lateral offset, aligned to the path or fixed, optional drop
        to the floor), one block, WITHOUT changing anything"""
        req = self._scatter_req(name, points, closed, spacing, offset, align, angle, start, ground, collision, max_count, id)
        plan = self._scatter_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('scatter', req), note='preview only: nothing changed')

    def prefab_scatter(self, name=None, points=None, closed=False, spacing=10.0, offset=0.0, align=True, angle=0.0, start=0.0,
                       ground=False, collision='keep', max_count=100, id=None, preview_key=None):  # noqa: A002
        req = self._scatter_req(name, points, closed, spacing, offset, align, angle, start, ground, collision, max_count, id)
        if preview_key != self._cons_key('scatter', req):
            raise E('NEEDS PREVIEW: preview this scatter first and apply it with its preview_key')
        plan = self._scatter_plan(req)
        S = plan['summary']
        label = '%s scatter %s (%d copies of %s)' % ('re-generate' if id else 'new', plan['id'], S['copies'], name)
        return dict(S, **self._apply_block(plan, label, 'scatter', S['faces']))

    def _refresh_plan(self, name):
        pf = self._prefab_read(name)
        C = self.constructs()
        stale = sorted(cid for cid, c in C.items() if c['meta'].get('kind') in ('placed', 'scatter', 'prefab')
                       and c['meta'].get('name') == name and c['meta'].get('prefab_sha256') != pf['sha256'])
        if not stale:
            raise E('no copy of prefab %s is out of date (every block records the prefab sha256 it was made from)' % name)
        faces_all, parts, repl = [], [], []
        for cid in stale:
            m = C[cid]['meta']
            repl += C[cid]['groups']
            if m['kind'] == 'scatter':
                req = dict({k: m[k] for k in ('name', 'points', 'closed', 'spacing', 'offset', 'align', 'angle', 'start', 'ground',
                                              'collision', 'max_count')}, prefab_sha256=pf['sha256'], id=None)
                sub = self._scatter_plan(req)
                meta = dict(m, prefab_sha256=pf['sha256'], copies=sub['summary']['copies'])
                parts.append((sub['planned'], meta))
            else:
                cmap = self._collision_map(sorted({x for x, _cs in pf['faces']}), m.get('collision', 'keep'))
                meta = dict(m, prefab_sha256=pf['sha256'])
                parts.append((self._placed_faces(pf, m['position'], m['angle'], cmap), meta))
            faces_all += parts[-1][0]
        after, blk = self._block_bytes(None, None, sorted(repl), parts=parts)
        return {'after': after, 'blk': blk, 'planned': faces_all, 'stale': stale}

    def prefab_refresh_preview(self, name=None):
        """TE stage 6: which copies of prefab `name` were made from an older version of it (sha256), WITHOUT changing anything"""
        plan = self._refresh_plan(name)
        return {'ok': True, 'prefab': name, 'stale_blocks': plan['stale'], 'faces': len(plan['planned']),
                'new_faces': [[list(q) for q in P] for P in plan['blk']['faces'][:3000]],
                'preview_key': self._cons_key('refresh', [name, plan['stale']]), 'note': 'preview only: nothing changed',
                'summary_lines': ['refresh copies of %s: %s (re-generated from the current prefab file, same positions / angles)' % (
                    name, ', '.join(plan['stale']))]}

    def prefab_refresh(self, name=None, preview_key=None):
        plan = self._refresh_plan(name)
        if preview_key != self._cons_key('refresh', [name, plan['stale']]):
            raise E('NEEDS PREVIEW: preview the refresh first and apply it with its preview_key')
        label = 'refresh %d copy block(s) of prefab %s' % (len(plan['stale']), name)
        r = self._apply_block(plan, label, 'scatter', len(plan['planned']))
        return dict(r, stale_blocks=plan['stale'], faces=len(plan['planned']))

    # ================================================================== stage 7: streaming, LOD, visibility
    LIMITS = [
        # (name, value, class, evidence, what raising it would take)
        ('mesh block per unit', '0x28000 bytes', 'HOST ceiling', 'trackbuild/_vendor/trackconv/streamed.py:22 "retail streaming pool '
         'layout 1: 10 x 0x28000"; build.py:142; validate.py V6_budgets', 'host work: a larger streaming pool / slot layout (the SDK '
         'capacity example relocates the track pool) - separate host checkpoint, not editor work'),
        ('LOD block per unit', '0x18000 bytes', 'HOST ceiling', 'streamed.py:22 "18 x 0x18000"; build.py:143', 'as above (host)'),
        ('static.dat', '0xD00000 bytes', 'HOST ceiling', 'validate.py:391 V6_budgets', 'host pool size (host work)'),
        ('Gamedata need', '0x176000 bytes', 'HOST ceiling', 'validate.py:391 V6_budgets', 'host pool size (host work)'),
        ('records per block', '127', 'FORMAT ceiling', 'xbtopo.py:134 "s8 chain index"; blocks.py:127', 'none (s8 field)'),
        ('vertices per block', '65,536', 'FORMAT ceiling', 'xbtopo.py:136; blocks.py:117 (u16 indices)', 'none (u16 field)'),
        ('material rows', '83', 'FORMAT ceiling', 'blocks.py:24 / xbmesh.py:20 "s16[83] material per row"; preflight.py:13', 'none'),
        ('PVS window', '17 chunks (-8..+8)', 'FORMAT ceiling', 'blocks.py:8 "17 PVS chunks x 0xA9"', 'none'),
        ('units with pvs "all"', '4..17 (validator: exactly 17)', 'TOOL-configured', 'build.py:99; validate V3_pvs_walk (pvs_chunks '
         'lists 17 relative units)', 'use pvs "computed" (4..162 units) - editor setting below'),
        ('units with pvs "computed"', '4..162', 'TOOL-configured (retail range)', 'build.py:101 "retail STATIC unit range"',
         'research: whether the host accepts more units (unknown; not tried)'),
        ('LOD decimation error', 'e_max <= 0.3 m', 'TOOL-configured (runtime-validated bound)', 'README "bounded decimation (e_max 0.3 '
         'm)"; validate V8_lod', 'an in-game check of a larger bound (owner-present run)'),
        ('collision extent', '+-128 cells of 1000 m', 'FORMAT ceiling', 'blocks.py:227 "s8 cell"', 'none'),
        ('height terrain block', '4096 cells', 'EDITOR-configured', 'wb_te_geom.HGRID_MAX_CELLS', 'several blocks / larger cells'),
    ]

    def _build_full(self, obj_bytes=None, desc_bytes=None):
        """the kit build_units on the current (or candidate) source -> (streamed, table, units, info), cached by content"""
        import os
        import shutil
        import tempfile
        ob = self.obj_cur if obj_bytes is None else obj_bytes
        db = self.cur if desc_bytes is None else desc_bytes
        key = hashlib.sha256(ob + b'\0' + db).hexdigest()
        cache = self.__dict__.setdefault('_full', {})
        if key in cache:
            return cache[key]
        K = T['kit_trackbuild'](self.cfg)
        d = json.loads(db.decode('utf-8'))
        root = os.path.join(self.cfg['state'], 'geomcheck')
        os.makedirs(root, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='full_', dir=root)
        try:
            p = os.path.join(tmp, *str(d.get('obj', '')).replace('\\', '/').split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(ob)
            r = K['build'].build_units(tmp, d)
        except K['io'].SourceError as e:
            raise E('refused by the kit build_units: %s. Nothing changed' % e)
        except Exception as e:  # noqa: BLE001
            raise E('the kit build_units failed (%s: %s). Nothing changed' % (type(e).__name__, e))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        cache.clear()
        cache[key] = r
        return r

    def streaming_report(self):
        """read only: per section (streamed unit) its coverage, memory against the slots, LOD and visibility, plus the limits with
        their source (format / host / tool / editor)"""
        streamed, table, units, info = self._build_full()
        d = self.desc()
        K = T['kit_trackbuild'](self.cfg)
        MS, LS = K['build'].MESH_SLOT, K['build'].LOD_SLOT
        samp = wc.route_samples(d.get('stations') or [])
        per = []
        for k, (u, x) in enumerate(zip(units, info['units'])):
            c = u.corners
            area = abs(sum(c[i][0] * c[(i + 1) % len(c)][1] - c[(i + 1) % len(c)][0] * c[i][1] for i in range(len(c)))) / 2
            dv = d['units'][k]
            per.append({'unit': k, 'stations': [dv['cut_from'], dv['cut_to']], 'lateral': dv['lateral'], 'region_m2': round(area, 1),
                        'drivable_samples': sum(1 for sx, sz, _i, _y in samp if u.inside(sx, sz)),
                        'render_polys': x['render_polys'], 'collision_polys': x['collision_polys'], 'vertices': x['vertices'],
                        'records': x['records'], 'mesh_bytes': x['mesh_bytes'], 'lod_bytes': x['lod_bytes'],
                        'mesh_pct': round(100.0 * x['mesh_bytes'] / MS, 1), 'lod_pct': round(100.0 * x['lod_bytes'] / LS, 1),
                        'vertex_pct': round(100.0 * x['vertices'] / 65536, 1), 'record_pct': round(100.0 * x['records'] / 127, 1),
                        'dropped_slivers': x['dropped_slivers'], 'region_corners': x['region_corners']})
        worst = max(per, key=lambda r: max(r['mesh_pct'], r['lod_pct'], r['vertex_pct'], r['record_pct']))
        wp = max(worst['mesh_pct'], worst['lod_pct'], worst['vertex_pct'], worst['record_pct'])
        pv = info['pvs']
        vis = ({'mode': 'all', 'note': 'every unit draws all 17 units of its +-8 window: the whole track stays resident (17 units)'}
               if pv['mode'] == 'all' else
               {'mode': 'computed', 'visible_per_unit': pv['computed']['visible_per_unit'], 'max_ahead': pv['computed']['max_ahead'],
                'ahead_beyond_4': pv['computed']['ahead_beyond_4'], 'matrix': pv['computed']['matrix']})
        lod = info['lod'] or {'mode': 'identity', 'note': 'LOD records = the full-detail mesh (no decimation)'}
        warn = ['unit %d at %.1f %% of a slot / vertex / record limit' % (r['unit'], max(r['mesh_pct'], r['lod_pct'], r['vertex_pct'],
                                                                                        r['record_pct'])) for r in per
                if max(r['mesh_pct'], r['lod_pct'], r['vertex_pct'], r['record_pct']) >= 80]
        y = (d.get('stations') or [{'p': [0, 0, 0]}])[0]['p'][1] + 0.6
        return {'ok': True, 'units': per, 'streamed_bytes': len(streamed), 'worst_unit': worst['unit'], 'worst_pct': wp,
                'visibility': vis, 'lod': {k: v for k, v in lod.items() if k != 'per_unit'}, 'lod_per_unit': lod.get('per_unit'),
                'limits': [{'limit': a, 'value': b, 'class': c, 'evidence': e_, 'to_raise': f} for a, b, c, e_, f in self.LIMITS],
                'warnings': warn, 'regions': [{'unit': r['unit'], 'corners': [[c[0], y, c[1]] for c in r['region_corners']],
                                               'changed': r['unit'] == worst['unit']} for r in per],
                'summary_lines': ['%d sections, %d streamed bytes; worst unit %d at %.1f %% of a limit; pvs %s; lod %s' % (
                    len(per), len(streamed), worst['unit'], wp, pv['mode'], lod['mode'])] +
                ['unit %2d: stations %s, %d render / %d collision polys, mesh %.1f %%, LOD %.1f %%, %d drivable samples' % (
                    r['unit'], r['stations'], r['render_polys'], r['collision_polys'], r['mesh_pct'], r['lod_pct'], r['drivable_samples'])
                 for r in per[:40]] + ['WARNING: ' + w for w in warn] +
                ['limit %s = %s: %s (%s)' % (a, b, c, e_.split(';')[0]) for a, b, c, e_, _f in self.LIMITS]}

    def lod_preview(self, unit=None):
        """read only: one unit's LOD geometry as the kit builds it (identity = the full mesh; decimate = trackbuild.lod) with the
        triangle counts and error"""
        streamed, table, units, info = self._build_full()
        if not (isinstance(unit, int) and 0 <= unit < len(units)):
            raise E('unit: 0..%d' % (len(units) - 1))
        lodd = self.desc().get('lod') or {'mode': 'identity'}
        u = units[unit]
        if lodd['mode'] == 'decimate':
            import importlib
            LD = importlib.import_module('trackbuild.lod')
            polys, st = LD.decimate(u.polys, lodd.get('e_max', 0.3), lodd.get('e_border', 0.05))
        else:
            polys, st = u.polys, {'tris_in': sum(len(p) - 2 for _m, p in u.polys), 'tris_out': sum(len(p) - 2 for _m, p in u.polys),
                                  'max_err': 0.0}
        return {'ok': True, 'unit': unit, 'mode': lodd['mode'], 'stats': st, 'mesh_polys': len(u.polys), 'lod_polys': len(polys),
                'new_faces': [[list(v[0]) for v in p] for _m, p in polys[:3000]],
                'summary_lines': ['unit %d LOD (%s): %d -> %d polygons, %s' % (unit, lodd['mode'], len(u.polys), len(polys),
                                                                              json.dumps(st)[:200])]}

    def _settings_req(self, lod_mode, e_max, pvs_mode):
        if lod_mode not in ('identity', 'decimate'):
            raise E("lod_mode: 'identity' (full detail) or 'decimate' (trackbuild.lod)")
        if lod_mode == 'decimate' and not num(e_max, 0.01, 0.3):
            raise E('e_max %r: 0.01..0.3 m (0.3 m = the runtime-validated bound; larger bounds are unverified and not offered)' % (e_max,))
        if pvs_mode not in ('all', 'computed'):
            raise E("pvs_mode: 'all' (exactly 17 units) or 'computed' (4..162 units, conservative visibility)")
        d = self.desc()
        lod = dict(d.get('lod') or {}, mode=lod_mode)          # other keys (e_border, debug_tint, unknown ones) are kept
        if lod_mode == 'decimate':
            lod['e_max'] = float(e_max)
        return {'lod': lod, 'pvs': dict(d.get('pvs') or {}, mode=pvs_mode)}

    def streaming_settings_preview(self, lod_mode=None, e_max=None, pvs_mode=None):
        """TE stage 7: LOD / visibility settings of the description, checked by the kit build_units dry run, WITHOUT changing"""
        req = self._settings_req(lod_mode, e_max, pvs_mode)
        nd = T['desc_splice'](self.cur, req)
        streamed, table, units, info = self._build_full(self.obj_cur, nd)
        return {'ok': True, 'settings': req, 'units': len(units), 'streamed_bytes': len(streamed), 'lod': info['lod'] and
                {k: v for k, v in info['lod'].items() if k != 'per_unit'}, 'pvs': info['pvs']['mode'],
                'preview_key': self._cons_key('stream', req), 'note': 'preview only: nothing changed',
                'summary_lines': ['settings %s: build_units ok, %d units, %d streamed bytes' % (json.dumps(req), len(units), len(streamed))]}

    def streaming_settings(self, lod_mode=None, e_max=None, pvs_mode=None, preview_key=None):
        req = self._settings_req(lod_mode, e_max, pvs_mode)
        if preview_key != self._cons_key('stream', req):
            raise E('NEEDS PREVIEW: preview these settings first and apply them with the preview_key')
        nd = T['desc_splice'](self.cur, req)
        self._build_full(self.obj_cur, nd)
        exact = self._check_desc_splice(self.cur, nd, set(req))
        label = 'streaming settings lod %s / pvs %s' % (req['lod']['mode'], req['pvs']['mode'])
        self._push('desc', label, nd, kind='settings', index=None)
        return {'ok': True, 'label': label, 'settings': req, 'exact': exact,
                'note': 'the kit gates decide at Build -> Validate (V8_lod, V9_pvs_computed / V3_pvs_walk)'}

    # ================================================================== stage 8 / 9: diagnostics (clickable validation)
    def diagnostics(self):
        """read only: geometry / collision / route checks of the CURRENT source, each with the faces to highlight and a focus point"""
        import wb_te_mesh as tm
        items = []

        def add(check, ok, text, faces=(), extra=None):
            faces = [[list(map(float, p)) for p in f] for f in list(faces)[:200]]
            focus = [sum(p[k] for p in faces[0]) / len(faces[0]) for k in range(3)] if faces else None
            items.append(dict({'check': check, 'ok': bool(ok), 'text': text, 'faces': faces, 'focus': focus}, **(extra or {})))
        if self.obj_cur is None:
            return {'ok': True, 'items': [{'check': 'obj', 'ok': False, 'text': 'the OBJ did not pass the input check', 'faces': []}]}
        o = tm.Obj(self.obj_cur)
        use = o.edge_use()
        open_e = [e for e, x in use.items() if len(x) == 1]
        nonm = [e for e, x in use.items() if len(x) > 2]
        add('open edges', True, '%d open edge(s) by position (normal at track borders; gaps show up here - weld / bridge / fill '
            'explicitly)' % len(open_e), [[list(e[0]), list(e[1]), list(e[0])] for e in open_e[:200]])
        add('non-manifold edges', not nonm, '%d edge(s) used by more than two faces' % len(nonm),
            [o.pts(li) for e in nonm[:60] for li, _i in use[e]])
        bad_n = []
        for li, cs in o.F.items():
            n = o.VN[cs[0][2] - 1] if 0 < cs[0][2] <= len(o.VN) else None
            g = tm.newell(o.pts(li))
            if n is None or g is None or sum(a * b for a, b in zip(n, g)) < 0.9:
                bad_n.append(li)
        add('stored normals', not bad_n, '%d face(s) whose stored normal disagrees with the face plane by more than 25 deg '
            '(trackbuild uses the stored normal for its winding rule)' % len(bad_n), [o.pts(li) for li in bad_n])
        cov = self.coverage(self.obj_cur)
        out_f = [f for f in cov['faces'] if f['area'] - f['kept'] > 0.01]
        add('outside the unit regions', not out_f, '%d face(s) lose more than 0.01 m2 outside every unit region (Build drops that '
            'part)' % len(out_f), [f['pts'] for f in out_f])
        terr = {g for c in self.constructs().values() if c['meta'].get('kind') in ('terrain', 'hterrain') for g in c['groups']}
        fl = [f for f in self._floor_faces(terr)]
        ov = [(i, j, a) for i, j, a, dy in tg.floor_overlaps([f['pts'] for f in fl], [f['pts'] for f in fl]) if i < j and
              fl[i]['group'] != fl[j]['group'] and abs(dy) < tg.LAYER_DY]
        add('overlapping floors', not ov, '%d pair(s) of collision floors of different face groups overlap at the same height '
            '(within %.2f m: z-fighting / ambiguous collision; %.2f m2)' % (len(ov), tg.LAYER_DY, sum(a for _i, _j, a in ov)),
            [fl[i]['pts'] for i, _j, _a in ov] + [fl[j]['pts'] for _i, j, _a in ov])
        if self.desc().get('stations'):
            rc = self.race_check()
            for c in rc['structural']:
                add('route: ' + c['check'], c['ok'], json.dumps(c['detail'])[:240])
        for v in self.validation():
            add('input / last build', False, '%s: %s' % (v['source'], v['text'][:240]))
        bad = sum(1 for x in items if not x['ok'])
        return {'ok': True, 'items': items, 'summary_lines': ['%d check(s), %d to look at: %s' % (
            len(items), bad, ', '.join(x['check'] for x in items if not x['ok']) or 'none')]}

    # ================================================================== stage 9: project workflow
    def backups(self):
        import os
        root = _backup_root(self)
        out = []
        if os.path.isdir(root):
            for n in sorted(os.listdir(root), reverse=True):
                mp = os.path.join(root, n, 'MANIFEST.json')
                try:
                    m = json.load(open(mp, encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                out.append({'name': n, 'files': m['files'], 'reason': m.get('reason')})
        return {'ok': True, 'backups': out, 'folder': root, 'note': 'a copy of the description / OBJ is taken before every Save (in '
                'Workbench state, never inside the project; the editor never deletes them)',
                'summary_lines': ['%d backup(s) of this project in %s' % (len(out), root)] + ['  %s: %s' % (
                    x['name'], ', '.join(sorted(x['files']))) for x in out[:20]]}

    def _backup_read(self, name):
        import os
        import re
        if not (isinstance(name, str) and re.match(r'^\d{8}_\d{6}_\d{6}$', name)):
            raise E('backup name: as listed (YYYYmmdd_HHMMSS_micro)')
        d = os.path.join(_backup_root(self), name)
        try:
            m = json.load(open(os.path.join(d, 'MANIFEST.json'), encoding='utf-8'))
        except (OSError, ValueError):
            raise E('backup %s does not exist / has no readable manifest' % name)
        if set(m['files']) != {self.desc_rel, self.obj_rel} - {None}:
            raise E('backup %s holds %s, not this project\'s %s / %s' % (name, sorted(m['files']), self.desc_rel, self.obj_rel))
        data = {}
        for rel, h in m['files'].items():
            b = open(os.path.join(d, *rel.split('/')), 'rb').read()
            if hashlib.sha256(b).hexdigest() != h:
                raise E('backup %s: %s does not match its manifest sha256 (damaged): refused' % (name, rel))
            data[rel] = b
        return data

    def backup_restore_preview(self, name=None):
        data = self._backup_read(name)
        d, o = data[self.desc_rel], data.get(self.obj_rel, self.obj_cur)
        return {'ok': True, 'backup': name, 'desc_changes': d != self.cur, 'obj_changes': o != self.obj_cur,
                'preview_key': self._cons_key('restore', name), 'note': 'preview only: nothing changed',
                'summary_lines': ['restore backup %s into the editor (one undo step; Save writes it)' % name]}

    def backup_restore(self, name=None, preview_key=None):
        if preview_key != self._cons_key('restore', name):
            raise E('NEEDS PREVIEW: preview the restore first and apply it with its preview_key')
        data = self._backup_read(name)
        d, o = data[self.desc_rel], data.get(self.obj_rel, self.obj_cur)
        if (d, o) == (self.cur, self.obj_cur):
            raise E('the editor already holds exactly that backup: nothing to restore')
        label = 'restore backup %s' % name
        self._push('both', label, (d, o), kind='restore', index=name)
        return {'ok': True, 'label': label, 'note': 'restored into the editor buffers (undoable); Save writes it into the project'}

    def versions(self):
        import os
        import sys
        import wb_core as core
        tb = core.trackbuild_dir(self.cfg)
        sums = os.path.join(tb, 'SHA256SUMS.txt')
        kitv = None
        try:
            kitv = json.load(open(os.path.join(self.cfg.get('kit') or '', 'HOST_INFO.json'), encoding='utf-8')).get('kit_version')
        except (OSError, ValueError):
            pass
        return {'ok': True, 'editor': 'Workbench %s track editor + TE authoring queue %s' % (core.VERSION, VERSION),
                'trackbuild': {'path': tb, 'version': '.'.join(map(str, self.tb_version())),
                               'sha256sums_sha256': hashlib.sha256(open(sums, 'rb').read()).hexdigest() if os.path.isfile(sums) else None},
                'kit': {'path': self.cfg.get('kit'), 'version': kitv}, 'python': sys.version.split()[0],
                'project': {'desc': self.desc_rel, 'obj': self.obj_rel,
                            'desc_sha256': hashlib.sha256(self.saved).hexdigest(),
                            'obj_sha256': hashlib.sha256(self.obj_saved).hexdigest() if self.obj_saved else None}}

    def _dest_ok(self, dest, what):
        import os
        import wb_core as core
        if not (isinstance(dest, str) and os.path.isabs(dest)):
            raise E('%s: an absolute path' % what)
        n = os.path.normcase(os.path.abspath(dest))
        if (n + os.sep).startswith(os.path.normcase(self.project) + os.sep):
            raise E('%s inside the project refused' % what)
        for p, why in core.protected_roots(self.cfg, self.project):
            if p and (n + os.sep).startswith(os.path.normcase(os.path.abspath(p)) + os.sep):
                raise E('%s refused: %s is protected (%s)' % (what, p, why))
        if os.path.exists(dest):
            raise E('%s %s exists: choose a new path (nothing is overwritten)' % (what, dest))
        if not os.path.isdir(os.path.dirname(os.path.abspath(dest))):
            raise E('%s: the parent folder does not exist' % what)

    def export_sources(self, dest=None):
        """the project's ORIGINAL SOURCES (description, OBJ / MTL, textures, provenance, project files) as a zip with MANIFEST.json
        (sha256 per file + versions). Never build output, staged packages or donor game files."""
        import os
        import zipfile
        import wb_stage as stg
        if self.dirty():
            raise E('unsaved edits: Save first (the export holds the saved sources)')
        if not (isinstance(dest, str) and dest.lower().endswith('.zip')):
            raise E('dest: a new .zip path')
        self._dest_ok(dest, 'export destination')
        files = {rel: h for rel, h in stg.tree_hashes(self.project).items() if not rel.endswith('.wb_tmp')}
        donor = [rel for rel in files if os.path.basename(rel).lower() in ('static.dat', 'streamed.dat', 'gamedata.bgd', 'enviro.dat',
                                                                             'sound.awd', 'music.rws', 'e_djrace.xwb')
                 or rel.lower().endswith(('.rws', '.awd', '.xwb'))]
        if donor:
            raise E('the project folder holds game / build files %s: they are never exported (move them out of the project)' % donor[:5])
        man = {'format': 'workbench-track-sources 1', 'files': files, 'versions': self.versions(),
               'note': 'original sources only; build with the Workbench (Build -> Validate -> Stage) against your own game data'}
        tmp = dest + '.wb_tmp'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            for rel in sorted(files):
                z.write(os.path.join(self.project, *rel.split('/')), 'sources/' + rel)
            z.writestr('MANIFEST.json', json.dumps(man, indent=1, sort_keys=True))
        os.replace(tmp, dest)
        return {'ok': True, 'zip': dest, 'files': len(files), 'bytes': os.path.getsize(dest),
                'sha256': hashlib.sha256(open(dest, 'rb').read()).hexdigest(),
                'summary_lines': ['exported %d source file(s) to %s (MANIFEST.json: sha256 + versions)' % (len(files), dest)]}

    def import_sources(self, zip=None, dest=None):  # noqa: A002
        """a source zip (export_sources) -> a NEW project folder `dest` (verified against its manifest, only listed relative paths);
        the open project is not touched"""
        import os
        import zipfile
        import wb_stage as stg
        if not (isinstance(zip, str) and os.path.isfile(zip)):
            raise E('zip: an existing source zip')
        self._dest_ok(dest, 'import destination')
        try:
            z = zipfile.ZipFile(zip)
            man = json.loads(z.read('MANIFEST.json').decode('utf-8'))
        except (zipfile.BadZipFile, KeyError, ValueError) as e:
            raise E('not a source zip with MANIFEST.json (%s)' % e)
        if man.get('format') != 'workbench-track-sources 1':
            raise E('unknown manifest format %r' % man.get('format'))
        names = set(z.namelist()) - {'MANIFEST.json'}
        want = {'sources/' + r for r in man['files']}
        if names != want:
            raise E('the zip and its manifest disagree (%d extra, %d missing): refused' % (len(names - want), len(want - names)))
        for rel in man['files']:
            parts = rel.split('/')
            if rel.startswith(('/', '\\')) or '..' in parts or ':' in rel or '\\' in rel:
                raise E('unsafe path %r in the zip: refused' % rel)
        data = {}
        for rel, h in man['files'].items():
            b = z.read('sources/' + rel)
            if hashlib.sha256(b).hexdigest() != h:
                raise E('%s does not match its manifest sha256: refused' % rel)
            data[rel] = b
        tmp = dest + '.wb_tmp'
        os.makedirs(tmp)
        for rel, b in data.items():
            p = os.path.join(tmp, *rel.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(b)
        os.replace(tmp, dest)
        got = stg.tree_hashes(dest)
        if got != man['files']:
            raise E('internal: the imported folder differs from the manifest')
        return {'ok': True, 'project': dest, 'files': len(got), 'versions_recorded': man.get('versions', {}).get('trackbuild'),
                'summary_lines': ['imported %d file(s) into the new project %s (manifest verified)' % (len(got), dest)]}

    def prepare_test(self, dest=None):
        """after a STAGED build: a test-preparation folder (NEW) with the package record (sha256 of every staged file), the
        project's acceptance checks and the exact run steps through the existing guarded runner. Nothing is launched."""
        import os
        import time
        b = self.last_build or {}
        if not (b.get('ok') and b.get('verdict') == 'STAGED' and b.get('staged')):
            raise E('no STAGED build in this editor session: Build -> Validate -> Stage first')
        if self.dirty():
            raise E('unsaved edits since the build: Save and Stage again first')
        self._dest_ok(dest, 'test folder')
        staged = b['staged']
        if not os.path.isdir(staged):
            raise E('the staged folder %s is gone' % staged)
        rec = {}
        for root, _ds, fs in os.walk(staged):
            for f in fs:
                p = os.path.join(root, f)
                rec[os.path.relpath(p, staged).replace('\\', '/')] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
        d = self.desc()
        C = self.constructs()
        kinds = {}
        for c in C.values():
            kinds[c['meta'].get('kind')] = kinds.get(c['meta'].get('kind'), 0) + 1
        checks = [('R1 load', 'select the track in a single race', 'race starts; no FATAL / hang'),
                  ('R2 streaming', 'one full lap', 'no holes / fall-through at the %d unit cuts' % len(d.get('units') or [])),
                  ('R3 surface', 'drive edge to edge incl. cuts%s' % (' and the sloped parts' if len({s['p'][1] for s in d.get('stations') or []}) > 1 else ''),
                   'car stays on the road'),
                  ('R4 walls', 'hit both walls', 'car never passes through')]
        if d.get('wall_gaps'):
            checks.append(('R4b wall gaps', 'drive out through the declared gap(s) %s and back' % d['wall_gaps'],
                           'car can leave / re-enter; AI never takes the gap'))
        if kinds.get('junction') or kinds.get('join'):
            checks.append(('R5 junctions', 'drive the side roads / junctions', 'surfaces continuous at the joints; GEOMETRIC only: AI / '
                           'traffic stay on the route'))
        if kinds.get('hterrain') or kinds.get('terrain'):
            checks.append(('R6 terrain', 'drive / crash onto the terrain if reachable', 'collision as rendered; no z-fighting with roads'))
        if kinds.get('placed') or kinds.get('scatter') or kinds.get('prefab'):
            checks.append(('R7 scenery', 'hit placed copies', 'colliding copies stop the car; "none" copies are drive-through'))
        checks += [('R8 laps', 'two laps in order; skip a checkpoint', '%d checkpoints count only in order' % len(d.get('checkpoints') or [])),
                   ('R9 AI', 'race with AI', 'AI follow the route and finish'), ('R10 respawn', 'crash / reset', 'respawn on the route'),
                   ('R11 LOD', 'watch far geometry', 'LOD mode %s: no gaps / popping' % (d.get('lod') or {'mode': 'identity'})['mode'])]
        os.makedirs(dest)
        with open(os.path.join(dest, 'PACKAGE_RECORD.json'), 'wb') as f:
            f.write(json.dumps({'staged': staged, 'files': rec, 'versions': self.versions(), 'prepared': time.strftime('%Y-%m-%d %H:%M:%S')},
                               indent=1, sort_keys=True).encode('utf-8'))
        lines = ['# Test preparation - %s (NOT executed)' % os.path.basename(self.project), '',
                 'Prepared by the track editor after a STAGED build. Nothing was launched. Offline gates prove structure only.', '',
                 '## Package', '- staged folder: `%s` (%d files; sha256 in PACKAGE_RECORD.json)' % (staged, len(rec)), '',
                 '## Run (owner present)', '1. Build a test profile with this package (Workbench Test profile tab; Prepare -> Preflight -> '
                 'dry run).', '2. The owner gives the runner token (`--authorize-runtime RUN:sha12`); one bounded run per authorisation, '
                 'fresh disposable root, new run folder (PC CLAUDE.md, tools\\runners\\g_run.py).',
                 '3. Stop once stuck or the evidence is complete (operator stop).', '', '## Checks (PASS / FAIL / NOT REACHED + evidence)',
                 '| # | Do | Pass |', '|---|---|---|'] + ['| %s | %s | %s |' % c for c in checks] + [
                 '', '## Content', '- blocks: %s' % ', '.join('%s x%d' % kv for kv in sorted(kinds.items(), key=lambda z: str(z[0]))),
                 '- units %d, pvs %s, lod %s' % (len(d.get('units') or []), (d.get('pvs') or {'mode': 'all'})['mode'],
                                                  (d.get('lod') or {'mode': 'identity'})['mode'])]
        with open(os.path.join(dest, 'TEST_PLAN.md'), 'wb') as f:
            f.write(('\n'.join(lines) + '\n').encode('utf-8'))
        return {'ok': True, 'folder': dest, 'files': ['TEST_PLAN.md', 'PACKAGE_RECORD.json'], 'checks': len(checks),
                'launched': False, 'summary_lines': ['test preparation written to %s (%d checks; nothing launched)' % (dest, len(checks))]}

    TE_LAYOUT = {'backups': 'backups', 'backup_restore_preview': 'backup_restore_preview', 'backup_restore': 'backup_restore',
                 'versions': 'versions', 'export_sources': 'export_sources', 'import_sources': 'import_sources',
                 'prepare_test': 'prepare_test', 'diagnostics': 'diagnostics', 'streaming_report': 'streaming_report', 'lod_preview': 'lod_preview',
                 'streaming_settings_preview': 'streaming_settings_preview', 'streaming_settings': 'streaming_settings',
                 'prefab_library': 'prefab_library', 'prefab_place_preview': 'prefab_place_preview', 'prefab_place': 'prefab_place',
                 'prefab_scatter_preview': 'prefab_scatter_preview', 'prefab_scatter': 'prefab_scatter',
                 'prefab_refresh_preview': 'prefab_refresh_preview', 'prefab_refresh': 'prefab_refresh',
                 'texture_import_preview': 'texture_import_preview', 'texture_import': 'texture_import',
                 'material_create_preview': 'material_create_preview', 'material_create': 'material_create',
                 'uv_transform_preview': 'uv_transform_preview', 'uv_transform': 'uv_transform',
                 'paint_preview': 'paint_preview', 'paint': 'paint',
                 'road_profile_preview': 'road_profile_preview', 'road_profile': 'road_profile', 'cross_sections': 'cross_section_view',
                 'mesh_preview': 'mesh_preview_api', 'mesh': 'mesh_api', 'mesh_info': 'mesh_info',
                 'road_ends': 'road_ends_view', 'junction_preview': 'junction_preview', 'junction': 'junction',
                 'join_preview': 'join_preview', 'join': 'join', 'routing': 'routing',
                 'hterrain_preview': 'hterrain_preview', 'hterrain': 'hterrain',
                 'terrain_brush_preview': 'terrain_brush_preview', 'terrain_brush': 'terrain_brush'}

    def _cons_key_any(self, kind, req):
        return hashlib.sha256(('%s|%s|%s' % (self.content_sha(), kind, json.dumps(req, sort_keys=True))).encode()).hexdigest()[:16]
