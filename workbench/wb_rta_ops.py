r"""wb_rta_ops - editor operations of the Retail-style panel (Workbench 0.33 retail-style authoring, 2026-11-02): asset library, styles, route helpers,
retail extension projects. A mixin of wb_trackedit.TrackSource (shares wb_rta_gen's bound globals and its job runner).
Every operation is read only on game data; writes go to Workbench state (caches, user presets) or to folders the user names.
"""
import base64
import hashlib
import json
import math
import os

import wb_retail
import wb_rta_catalog as CAT
import wb_rta_ext as EXT
import wb_rta_gen as GEN
import wb_rta_geo as GEO
import wb_rta_measure as MEAS
import wb_rta_style as STY
import wb_rta_thumbs as TH

T = GEN.T


def E(msg):
    return T['EditError'](msg)


def _png_uri(path):
    return 'data:image/png;base64,' + base64.b64encode(open(path, 'rb').read()).decode('ascii')


class OpsMixin:
    # ------------------------------------------------------------------ 1 asset library
    def rta_catalogue_status(self):
        gd = self.cfg.get('game_data')
        try:
            found = CAT.discover(gd)
            ferr = None
        except CAT.CatalogError as e:
            found, ferr = [], str(e)
        p = os.path.join(CAT.cat_root(self.cfg), 'INDEX.json')
        idx = None
        if os.path.isfile(p):
            try:
                idx = json.load(open(p, encoding='utf-8'))
            except (OSError, ValueError):
                idx = None
        done = {r['track']: r for r in (idx or {}).get('tracks', [])}
        rows = [{'track': f['track'], 'catalogued': bool(done.get(f['track'], {}).get('ok')), 'error': done.get(f['track'], {}).get('error')}
                for f in found]
        missing = []
        if gd and os.path.isdir(os.path.join(gd, 'Tracks')):
            for rr in sorted(os.listdir(os.path.join(gd, 'Tracks'))):
                rp = os.path.join(gd, 'Tracks', rr)
                if len(rr) == 2 and os.path.isdir(rp):
                    for t in sorted(os.listdir(rp)):
                        if os.path.isdir(os.path.join(rp, t)) and '%s/%s' % (rr, t) not in {f['track'] for f in found}:
                            have = sorted(os.listdir(os.path.join(rp, t)))
                            missing.append({'track': '%s/%s' % (rr, t), 'why': 'not catalogued: needs %s (has %s)' % (
                                ', '.join(n for n in wb_retail.REQUIRED if n not in have), ', '.join(have[:6]))})
        return {'ok': True, 'game_data': gd, 'problem': ferr, 'tracks': rows, 'not_supported': missing,
                'index_built_at': (idx or {}).get('built_at'), 'local_only': True,
                'summary_lines': ['game data %s: %d track(s) found, %d catalogued%s' % (gd, len(rows), sum(r['catalogued'] for r in rows),
                                                                                       '; ' + ferr if ferr else '')]}

    def rta_catalogue_build(self, tracks=None, force=False):
        if tracks is not None and not (isinstance(tracks, list) and all(isinstance(t, str) for t in tracks)):
            raise E('tracks: a list of track ids such as ["US/C1_V1"] (empty = all)')

        def fn(job):
            def prog(f, m):
                job['progress'], job['message'] = f or 0.0, m
                if len(job['lines']) < 400:
                    job['lines'].append('%5.1f%%  %s' % (100 * (f or 0), m))
            try:
                idx = CAT.build(self.cfg, None, tracks or None, bool(force), cancel=lambda: job.get('cancel'), progress=prog)
            except CAT.Cancelled as e:
                raise E('%s; finished tracks stay cached, the previous index stays valid' % e)
            except CAT.CatalogError as e:
                raise E(str(e))
            import wb_rta_objects as OB                  # buildings / structures of every track (segmented render mesh)
            nb = ns = 0
            ok_tracks = [r['track'] for r in idx['tracks'] if r['ok']]
            for i, t in enumerate(ok_tracks):
                if job.get('cancel'):
                    raise E('cancelled while segmenting buildings (%s); finished tracks stay cached' % t)
                prog(0.9 + 0.1 * i / max(1, len(ok_tracks)), '%s: buildings / structures' % t)
                o = OB.build(self.cfg, t)
                nb += o['counts']['buildings']
                ns += o['counts']['structures']
            idx['objects'] = {'buildings': nb, 'structures': ns}
            return {'tracks': len(idx['tracks']), 'failed': [r for r in idx['tracks'] if not r['ok']], 'seconds': idx['seconds'],
                    'objects': idx['objects'],
                    'summary_lines': ['catalogue: %d track(s) in %.1f s (%d reused from the cache), %d failed; %d buildings + %d structures '
                                      'segmented' % (len(idx['tracks']), idx['seconds'], sum(1 for r in idx['tracks'] if r.get('reused')),
                                                     sum(1 for r in idx['tracks'] if not r['ok']), idx['objects']['buildings'],
                                                     idx['objects']['structures'])]}
        return self._rta_job('catalogue', fn)

    def rta_catalogue_search(self, query='', kind=None, role=None, track=None, limit=120):
        try:
            rows = CAT.search(self.cfg, query, kind, role, [track] if track else None, max(1, min(int(limit), 500)))
        except (OSError, ValueError, CAT.CatalogError) as e:
            raise E('no catalogue yet (%s): create the asset library first' % e)
        return {'ok': True, 'rows': rows, 'summary_lines': ['%d asset(s)' % len(rows)]}

    def rta_asset(self, track=None, id=None):  # noqa: A002
        try:
            cat = CAT.load(self.cfg, track)
        except CAT.CatalogError as e:
            raise E(str(e))
        cdir0 = os.path.join(CAT.cat_root(self.cfg), '%s-%s' % (track.replace('/', '_'), cat['cache_key'][:12]))
        if str(id)[:1] in ('B', 'S'):
            import wb_rta_objects as OB
            try:
                p = OB.piece(self.cfg, track, id)
                th = _png_uri(TH.piece_thumb(self.cfg, cat, cdir0, id))
                terr = None
            except Exception as e:  # noqa: BLE001
                return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}
            a = {k: v for k, v in p.items() if k != 'refs'}
            a['kind'] = p['class']
            a['use'] = ('GEOMETRY COPY of the opaque triangles (retail baked light kept; cut-out parts are not in the piece); '
                        'Place in project (position, turn, ground snap, collision keep / none). LOCAL ONLY')
            return {'ok': True, 'track': track, 'asset': a, 'thumbnail': th, 'thumbnail_error': terr, 'local_only': True,
                    'placeable': True, 'thumbnail_note': 'approximate: flat-shaded 3/4 view with each texture\'s mean colour'}
        grp = 'textures' if str(id).startswith('T:') else 'instance_models' if str(id).startswith('I') else 'prop_types'
        a = next((x for x in cat[grp] if x['id'] == id), None)
        if not a:
            raise E('%s has no asset %r' % (track, id))
        cdir = os.path.join(CAT.cat_root(self.cfg), '%s-%s' % (track.replace('/', '_'), cat['cache_key'][:12]))
        thumb, terr = None, None
        try:
            if a.get('thumbnail') and a['thumbnail'][0] == 'tex':
                thumb = _png_uri(TH.texture_thumb(cat, cdir, a['thumbnail'][1]))
            elif a.get('thumbnail'):
                thumb = _png_uri(TH.model_thumb(cat, cdir, a['thumbnail'][1]))
        except Exception as e:  # noqa: BLE001   a thumbnail that cannot be drawn is reported, the asset stays listed
            terr = '%s: %s' % (type(e).__name__, e)
        return {'ok': True, 'track': track, 'asset': a, 'thumbnail': thumb, 'thumbnail_error': terr, 'local_only': True,
                'thumbnail_note': 'approximate: flat-shaded front view (models) / box-filtered preview (textures)'}

    # ------------------------------------------------------------------ 2 styles
    def _rta_place_plan(self, track, id, position, angle, ground, collision, double_sided):  # noqa: A002
        """-> (by_tex like the te2 retail copies, n triangles, kind). Pieces keep their baked light; models get the neutral 0.2."""
        import math
        import re
        if not (isinstance(position, list) and len(position) in (2, 3) and all(GEN.num(v, -1e5, 1e5) for v in position)):
            raise E('position: [x, z] (ground snap) or [x, y, z]')
        if not GEN.num(angle, -360, 360):
            raise E('angle: degrees -360..360')
        if collision not in ('keep', 'none'):
            raise E("collision: 'keep' (solid) or 'none' (decorative)")
        x, z = float(position[0]), float(position[-1])
        if ground or len(position) == 2:
            g = self._ground_y(x, z)
            if g is None:
                raise E('no collision floor under (%.1f, %.1f) in this project: place it on the generated ground / verges, or give y' % (x, z))
            y = g - 0.05
        else:
            y = float(position[1])
        tris = []                                       # (texture name, texture index or None, [(pos, uv, colour)])
        if re.match(r'^[BS][0-9]+$', str(id)):
            import wb_rta_objects as OB
            try:
                tris = OB.piece_triangles(self.cfg, track, id)
            except Exception as e:  # noqa: BLE001
                raise E(str(e))
            kind = 'building / structure piece'
        elif re.match(r'^[IP][0-9]+$', str(id)):
            import sys
            pm = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'format_research', 'props_mesh')
            if pm not in sys.path:
                sys.path.insert(0, pm)
            import fr_propmesh as FP
            try:
                t = FP.load(self._ext_folder(track))
                raw = t.triangles(id[0], int(id[1:]))
            except Exception as e:  # noqa: BLE001
                raise E('%s %s could not be read: %s' % (track, id, e))
            cat = CAT.load(self.cfg, track)
            grp = 'instance_models' if id[0] == 'I' else 'prop_types'
            m = next((q for q in cat[grp] if q['id'] == id), {})
            if m.get('render', 'opaque') != 'opaque':
                raise E('%s %s uses a cut-out / blended texture (%s): a copy would be a solid block - refused' % (track, id, m.get('texture')))
            tris = [(tn, None, [(p, uv, (0.2, 0.2, 0.2)) for p, uv, _c in cs]) for tn, cs in raw]
            kind = 'instance model' if id[0] == 'I' else 'smashable prop type (copied as STATIC scenery: not smashable)'
        else:
            raise E('id: B<n> / S<n> (building / structure), I<n> (instance model) or P<n> (prop type)')
        if not tris:
            raise E('%s %s has no opaque triangles' % (track, id))
        P = [c[0] for _t, _i, cs in tris for c in cs]
        bx = (max(p[0] for p in P) + min(p[0] for p in P)) / 2
        bz = (max(p[2] for p in P) + min(p[2] for p in P)) / 2
        y0 = min(p[1] for p in P)
        if ground or len(position) == 2:                # a flat base (up-facing faces at the bottom) sits ON the ground: the
            for _t, _i, cs in tris:                     # editor refuses floors coplanar with / below existing floors
                pts0 = [c[0] for c in cs]
                _a, nn0, _c0 = GEO.tri_geo(*pts0)
                if abs(nn0[1]) > 0.7 and max(q[1] for q in pts0) < y0 + 0.1:
                    y += 0.09                           # ground - 0.05 + 0.09 = 4 cm above the ground
                    break
        a = math.radians(angle)
        ca, sa = math.cos(a), math.sin(a)
        by_tex = {}
        for tn, ti, cs in tris:
            pts = [(round(x + ca * (q[0] - bx) - sa * (q[2] - bz), 4), round(y + q[1] - y0, 4), round(z + sa * (q[0] - bx) + ca * (q[2] - bz), 4))
                   for q, _uv, _c in cs]
            ar, n, _cc = GEO.tri_geo(*pts)
            if ar < 0.006:
                continue
            e = by_tex.setdefault(tn, {'texture_index': ti, 'faces': []})
            nn = tuple(round(v, 5) for v in n)
            col = [tuple(round(v, 3) for v in c_) for _q, _uv, c_ in cs]
            uvs = [(round(uv[0], 5), round(uv[1], 5)) for _q, uv, _c in cs]
            e['faces'].append([(pts[j], uvs[j], nn, col[j]) for j in range(3)])
            if double_sided:
                rn = tuple(-v for v in nn)
                e['faces'].append([(pts[j], uvs[j], rn, col[j]) for j in (0, 2, 1)])
        return by_tex, sum(len(e['faces']) for e in by_tex.values()), kind

    def rta_place_preview(self, track=None, id=None, position=None, angle=0.0, ground=True, collision='keep', double_sided=None):  # noqa: A002
        ds = (str(id)[:1] in ('I', 'P')) if double_sided is None else bool(double_sided)
        by_tex, n, kind = self._rta_place_plan(track, id, position, angle, ground, collision, ds)
        req = [track, id, position, angle, ground, collision, ds]
        return {'ok': True, 'kind': kind, 'triangles': n, 'textures': sorted(by_tex), 'local_only': True,
                'new_faces': [[list(c[0]) for c in f] for e in by_tex.values() for f in e['faces'][:2000]],
                'preview_key': self._cons_key('rta_place', req),
                'summary_lines': ['place %s %s (%s): %d triangles, %d texture(s), collision %s; preview only, LOCAL ONLY' % (
                    track, id, kind, n, len(by_tex), collision)]}

    def rta_place(self, track=None, id=None, position=None, angle=0.0, ground=True, collision='keep', double_sided=None, preview_key=None):  # noqa: A002
        """copy one catalogued building / structure / instance model / prop into this project (one undo step; LOCAL ONLY)"""
        from wb_te_retail import mat_name
        ds = (str(id)[:1] in ('I', 'P')) if double_sided is None else bool(double_sided)
        req = [track, id, position, angle, ground, collision, ds]
        if preview_key != self._cons_key('rta_place', req):
            raise E('NEEDS PREVIEW: preview this placement first')
        by_tex, n, kind = self._rta_place_plan(track, id, position, angle, ground, collision, ds)
        if str(id)[:1] in ('I', 'P'):
            rows = self._static_tex(track, set(by_tex))
            for tn in by_tex:
                by_tex[tn]['png_rows'] = rows[tn]
            cdir = None
        else:
            cdir = CAT.load(self.cfg, track)['view_cache']
        if collision == 'none':
            for tn in by_tex:
                by_tex[tn]['mat'] = mat_name(tn) + '_nc'
                by_tex[tn]['collide'] = False
        tex = self._region_textures(cdir, by_tex, track)
        meta = {'kind': 'retail_copy', 'id': self._new_id('placed'), 'track': track, 'source_id': id, 'position': position,
                'angle': angle, 'local_only': True, 'what': kind}
        before = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta))
        n0 = len(self.undo_stack)
        r = self._apply_retail(track, by_tex, tex, meta, None, n, 'place %s %s (%s)' % (track, id, kind))
        after = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta))
        del self.undo_stack[n0:]                        # texture files + geometry -> ONE undo entry (buffer 'all')
        self.cur, self.obj_cur = before[0], before[1]
        self.pending, self.pending_meta = dict(before[2]), dict(before[3])
        self._push('all', r['label'], after, kind='rta_place', index=meta['id'])
        return r

    # ------------------------------------------------------------------ trusted asset library (rta2)
    def rta_trust_search(self, track=None, category=None, query='', favourites=False, min_confidence=0.0, facing_road=False, limit=150):
        import wb_rta_assets as AS
        rows = AS.search(self.cfg, [track] if track else None, category or None, query, bool(favourites), float(min_confidence or 0),
                         bool(facing_road), max(1, min(int(limit), 500)))
        slim = [{k: r.get(k) for k in ('track', 'id', 'kind', 'category', 'category_confidence', 'front_confidence', 'favourite', 'height_m',
                                        'footprint_along_front_m', 'triangles', 'warnings', 'override')} for r in rows]
        return {'ok': True, 'rows': slim, 'summary_lines': ['%d asset(s) (measured classifications with confidence; never verified '
                                                            'standalone assets)' % len(slim)]}

    def rta_trust_asset(self, track=None, id=None, yaw=35):  # noqa: A002
        import wb_rta_assets as AS
        a = next((x for x in AS.build(self.cfg, track)['assets'] if x['id'] == id), None)
        if not a:
            raise E('%s has no asset %r' % (track, id))
        e = AS.effective(self.cfg, a)
        cat = CAT.load(self.cfg, track)
        cdir = os.path.join(CAT.cat_root(self.cfg), '%s-%s' % (track.replace('/', '_'), cat['cache_key'][:12]))
        th, terr = None, None
        try:
            if a['kind'] == 'piece':
                th = _png_uri(TH.piece_thumb(self.cfg, cat, cdir, id, 160, int(yaw) % 360))
            else:
                th = _png_uri(TH.model_thumb(cat, cdir, id))
        except Exception as ex:  # noqa: BLE001
            terr = '%s: %s' % (type(ex).__name__, ex)
        return {'ok': True, 'asset': e, 'thumbnail': th, 'thumbnail_error': terr, 'yaw': int(yaw) % 360,
                'labels': {'measured': 'front, facing sectors, shell / roof, footprint, anchor (wb_rta_assets)',
                           'override': 'your corrections (front angle, category, favourite) win; measured values stay listed',
                           'verified': 'nothing here is a verified standalone asset'}}

    def rta_trust_override(self, track=None, id=None, front_deg=None, category=None, favourite=None, note=None, clear=False):  # noqa: A002
        import wb_rta_assets as AS
        try:
            r = AS.set_override(self.cfg, track, id, front_deg, category, favourite, note, bool(clear))
        except ValueError as e:
            raise E(str(e))
        return {'ok': True, 'override': r, 'summary_lines': ['%s %s: %s' % (track, id, 'override cleared' if clear else 'override saved %s' % r)]}

    def rta_style_show(self, style=None):
        try:
            p = STY.load(self.cfg, style)
        except STY.StyleError as e:
            raise E(str(e))
        _c, why = STY.check_source(self.cfg, p)
        return {'ok': True, 'style': p, 'usable': not why, 'why_not': why,
                'sections': {'measured (read only)': p['measured'], 'artistic defaults (editable)': p['defaults'],
                             'palette': p['palette'], 'why each palette entry': p['palette_why'], 'builder limits': p['builder_limits']}}

    def rta_style_derive(self, track=None, id=None, title=None):  # noqa: A002
        if not (isinstance(id, str) and id):
            raise E('id: a new preset id (a-z 0-9 _)')
        try:
            cat = CAT.load(self.cfg, track)
            m = MEAS.measure_track(self.cfg, track)
            p = STY.derive(cat, m, id, title or 'Style measured on %s' % track)
            path = STY.save_user(self.cfg, p)
        except (CAT.CatalogError, STY.StyleError) as e:
            raise E(str(e))
        return {'ok': True, 'style': p['id'], 'kind': p['kind'], 'kind_evidence': p['kind_evidence'], 'file': path,
                'summary_lines': ['preset %s derived from %s (%s: %s)' % (p['id'], track, p['kind'], p['kind_evidence'])]}

    def rta_style_defaults(self, style=None, defaults=None, new_id=None):
        """save a user copy with edited ARTISTIC defaults (measurements and palette stay as derived)"""
        try:
            p = STY.load(self.cfg, style)
        except STY.StyleError as e:
            raise E(str(e))
        if not isinstance(defaults, dict) or set(defaults) - set(STY.DEFAULTS):
            raise E('defaults: keys of %s only' % ', '.join(sorted(STY.DEFAULTS)))
        p = dict(p, defaults=dict(p['defaults'], **defaults), id=new_id or p['id'])
        try:
            path = STY.save_user(self.cfg, p)
        except STY.StyleError as e:
            raise E(str(e))
        return {'ok': True, 'file': path, 'summary_lines': ['saved %s (your copy; the shipped example is unchanged)' % p['id']]}

    def rta_route_current(self):
        C = self.constructs()
        m = (C.get('route_road') or {}).get('meta') or {}
        pts = m.get('points')
        st = self.desc().get('stations') or []
        return {'ok': True, 'points': pts, 'stations': len(st),
                'centre': [round(sum(s['p'][i] for s in st) / len(st), 1) for i in range(3)] if st else [-6000.0, 20.0, -6000.0]}

    # ------------------------------------------------------------------ 5 / 6 retail extension projects
    def _ext_folder(self, track):
        import re
        if not (isinstance(track, str) and re.match(r'^[A-Z]{2}/[A-Z][0-9]_V[0-9]$', track)):
            raise E('track: an id such as US/C1_V1')
        f = os.path.join(self.cfg.get('game_data') or '', 'Tracks', *track.split('/'))
        if not os.path.isfile(os.path.join(f, 'static.dat')):
            raise E('%s not found in your game data (%s)' % (track, self.cfg.get('game_data')))
        return f

    def rta_ext_roundtrip(self, track=None):
        f = self._ext_folder(track)

        def fn(job):
            job['message'] = 'round trip %s' % track
            r = EXT.round_trip(self.cfg, f)
            return {'verdict': r['verdict'], 'files': {n: {k: v[k] for k in ('identical', 'method', 'size')} for n, v in r['files'].items()},
                    'blocks': r['files']['streamed.dat']['blocks'], 'props': r['static_prop_tail_identical'],
                    'summary_lines': ['%s: round trip %s (%d files, %d streamed blocks); editing %s' % (
                        track, r['verdict'], len(r['files']), r['files']['streamed.dat']['blocks'],
                        'allowed' if r['edits_allowed'] else 'BLOCKED')]}
        return self._rta_job('roundtrip', fn)

    def _dest_ok_ext(self, dest):
        if not (isinstance(dest, str) and os.path.isabs(dest)):
            raise E('folder: an absolute path')
        gd = os.path.abspath(self.cfg.get('game_data') or '')
        a = os.path.normcase(os.path.abspath(dest))
        if gd and (a + os.sep).startswith(os.path.normcase(gd) + os.sep):
            raise E('refused: the folder lies inside your game data (retail data is never written)')
        for p in self.cfg.get('protected') or []:
            if (a + os.sep).startswith(os.path.normcase(os.path.abspath(p)) + os.sep):
                raise E('refused: %s is a protected folder' % p)
        return dest

    def rta_ext_create(self, track=None, dest=None, title=None):
        f = self._ext_folder(track)
        self._dest_ok_ext(dest)
        try:
            p = EXT.create_project(self.cfg, f, dest, title)
        except EXT.ExtError as e:
            raise E(str(e))
        return {'ok': True, 'project': dest, 'track': track, 'roundtrip_seconds': p['roundtrip_seconds'],
                'summary_lines': ['extension project %s created for %s (round trip PASS in %.1f s; no retail bytes stored)' % (
                    dest, track, p['roundtrip_seconds'])]}

    def rta_ext_open(self, dest=None):
        try:
            p = EXT.load_project(dest)
        except EXT.ExtError as e:
            raise E(str(e))
        why = EXT.check_source(p)
        try:
            cat = CAT.load(self.cfg, p['track'])
            units = [{'unit': u['unit'], 'mesh_free_bytes': u.get('mesh_free_bytes'), 'records_free': u.get('records_free')}
                     for u in cat['units'] if not u.get('empty')]
        except CAT.CatalogError:
            units = None
        return {'ok': True, 'project': p, 'source_problem': why, 'units': units,
                'summary_lines': ['%s: %d edit(s)%s' % (p['title'], len(p['edits']), '; SOURCE PROBLEM: ' + why if why else '')]}

    def rta_ext_unit(self, dest=None, unit=None):
        p = EXT.load_project(dest)
        try:
            i = EXT.unit_info(self.cfg, p['retail_folder'], unit)
        except EXT.ExtError as e:
            raise E(str(e))
        return {'ok': True, 'unit': i, 'textures': sorted({h['texture'] for h in i['hosts'] if h['strip'] and h['texture']})}

    def _attach_req(self, dest, unit, side, setback, along, width, depth, height, texture, roof_texture):
        p = EXT.load_project(dest)
        why = EXT.check_source(p)
        if why:
            raise E(why)
        for n, v, lo, hi in (('setback', setback, 0, 200), ('along', along, 0, 1), ('width', width, 2, 80), ('depth', depth, 2, 80),
                             ('height', height, 2, 80)):
            if not GEN.num(v, lo, hi):
                raise E('%s %r: %g..%g' % (n, v, lo, hi))
        if side not in (-1, 1):
            raise E('side: -1 (right of the travel direction) or 1 (left)')
        return p, dict(unit=unit, side=side, setback=float(setback), along=float(along), width=float(width), depth=float(depth),
                       height=float(height), texture=texture, roof_texture=roof_texture)

    def rta_ext_attach_preview(self, dest=None, unit=None, side=-1, setback=18.0, along=0.5, width=12.0, depth=9.0, height=10.0,
                               texture=None, roof_texture=None):
        import wb_rta_attach as A
        p, req = self._attach_req(dest, unit, side, setback, along, width, depth, height, texture, roof_texture)
        try:
            plan = A.attachment_plan(self.cfg, p['retail_folder'], **req)
        except EXT.ExtError as e:
            raise E(str(e))
        key = hashlib.sha256(json.dumps([dest, req, len(p['edits'])], sort_keys=True).encode()).hexdigest()[:16]
        svg = self._attach_svg(p, unit, plan)
        return {'ok': True, 'report': plan['report'], 'preview_key': key, 'svg': svg, 'note': 'preview only: the project is unchanged',
                'summary_lines': ['attachment in unit %d: %s, base %.2f m, seam gap %.2f m, region %s, fits %s' % (
                    unit, plan['report']['materials'], plan['report']['base_y'], plan['report']['seam_max_gap_m'],
                    'ok' if plan['report']['region_quad_ok'] else 'OUTSIDE', plan['report']['fits'])]}

    def rta_ext_attach_find(self, dest=None, unit=None, side=-1, along=0.5, width=12.0, depth=9.0, height=10.0, texture=None,
                            roof_texture=None):
        """search the nearest setback / along / side where the piece stands off tarmac, off every AI lane, inside the unit"""
        import wb_rta_attach as A
        p, req = self._attach_req(dest, unit, side, 18.0, along, width, depth, height, texture, roof_texture)
        try:
            plan, tried = A.find_clear(self.cfg, p['retail_folder'], unit, side, along, req['width'], req['depth'], req['height'],
                                       texture, roof_texture)
        except EXT.ExtError as e:
            raise E(str(e))
        if not plan:
            raise E('no clear spot in unit %d (%d tried; first reasons: %s)' % (unit, len(tried), '; '.join(t['why'][:60] for t in tried[:3])))
        r = plan['report']
        return {'ok': True, 'side': -1 if r['side'] == 'right' else 1, 'setback': plan.get('setback'), 'report': r, 'tried': len(tried),
                'summary_lines': ['clear spot after %d tries: side %s, centre %s (press Preview attachment)' % (len(tried), r['side'], r['centre'])]}

    def rta_ext_attach_add(self, dest=None, unit=None, side=-1, setback=18.0, along=0.5, width=12.0, depth=9.0, height=10.0,
                           texture=None, roof_texture=None, preview_key=None):
        import wb_rta_attach as A
        p, req = self._attach_req(dest, unit, side, setback, along, width, depth, height, texture, roof_texture)
        key = hashlib.sha256(json.dumps([dest, req, len(p['edits'])], sort_keys=True).encode()).hexdigest()[:16]
        if preview_key != key:
            raise E('NEEDS PREVIEW: preview this attachment first')
        plan = A.attachment_plan(self.cfg, p['retail_folder'], **req)
        if not plan['report']['fits']:
            raise E('refused: the preview says it does not fit (%s)' % plan['report'].get('problem', 'slot / records'))
        EXT.add_edits(dest, plan['edits'], 'attachment unit %d (%s)' % (unit, texture))
        return {'ok': True, 'summary_lines': ['added %d edit(s) to %s (one history step; Undo last edit removes them)' % (len(plan['edits']), dest)]}

    def rta_ext_undo(self, dest=None):
        try:
            p = EXT.undo_last(dest)
        except EXT.ExtError as e:
            raise E(str(e))
        return {'ok': True, 'summary_lines': ['last edit step removed; %d edit(s) left' % len(p['edits'])]}

    def rta_ext_build(self, dest=None, out=None):
        self._dest_ok_ext(out)

        def fn(job):
            job['message'] = 'building %s' % out
            try:
                rec = EXT.build(self.cfg, dest, out)
            except EXT.ExtError as e:
                raise E(str(e))
            return dict(rec, summary_lines=['extension build %s: changed %s; %d block(s) moved unchanged; %d unchanged in place; static.dat '
                                            '%s bytes changed (unit table only: %s); LOCAL ONLY' % (
                                                rec['verdict'], ', '.join(rec['streamed_blocks']['changed']) or 'nothing',
                                                rec['streamed_blocks']['moved_unchanged_bytes'], rec['streamed_blocks']['unchanged_in_place'],
                                                rec['static_changed_bytes'], rec['static_changes_only_in_unit_table'])])
        return self._rta_job('ext_build', fn)

    def _attach_svg(self, p, unit, plan):
        """top view: unit region, route centre line nearby, the piece, ground samples"""
        v, _cdir, _r = wb_retail.decode(self.cfg, p['retail_folder'])
        u = next((x for x in v['units'] if x['unit'] == unit), None)
        lines, cyc = GEO.route_lines(v)
        R = GEO.RouteIndex(lines, cyc)
        rep = plan['report']
        pts = [c[:3] for c in (u or {}).get('corners', [])]
        if not pts:
            return ''
        xs = [q[0] for q in pts]
        zs = [q[2] for q in pts]
        x0, x1, z0, z1 = min(xs) - 20, max(xs) + 20, min(zs) - 20, max(zs) + 20
        W = 360
        sc = W / max(x1 - x0, z1 - z0)
        f = lambda x, z: '%.1f,%.1f' % ((x - x0) * sc, (z - z0) * sc)  # noqa: E731
        s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" style="background:#f6f6f2">' % (W, W)]
        s.append('<polygon points="%s" fill="#e3ecf7" stroke="#3a6ea5"/>' % ' '.join(f(q[0], q[2]) for q in pts))
        rp = [q for q in R.samples if x0 <= q[0] <= x1 and z0 <= q[2] <= z1 and q[4] == 0]
        s.append('<polyline points="%s" fill="none" stroke="#888" stroke-dasharray="4 3"/>' % ' '.join(f(q[0], q[2]) for q in rp[::2]))
        foot = []
        for e in plan['edits']:
            for t in e['triangles']:
                foot += [(c[0], c[2]) for c in t]
        if foot:
            hx = [a for a, _b in foot]
            hz = [b for _a, b in foot]
            s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" stroke="#c0392b" stroke-width="2"/>' % (
                (min(hx) - x0) * sc, (min(hz) - z0) * sc, (max(hx) - min(hx)) * sc, (max(hz) - min(hz)) * sc))
        c = rep['centre']
        s.append('<circle cx="%.1f" cy="%.1f" r="3" fill="#c0392b"/>' % ((c[0] - x0) * sc, (c[1] - z0) * sc))
        s.append('<text x="4" y="14" font-size="11" fill="#333">unit %d region (blue), route lane 0 (dashed), piece (red)</text>' % unit)
        s.append('</svg>')
        return ''.join(s)

    # ------------------------------------------------------------------ 7 sharing (recipes only)
    def _recipe_of(self, kind, dest, author, licence, title):
        import wb_rta_share as SH
        if kind == 'generation':
            C = self.constructs()
            rec = next((c['meta'].get('gen_record') for c in C.values() if c['meta'].get('gen_record')), None)
            if not rec or 'points' not in rec:
                raise E('no generation record in this project (generate a retail-style layout first)')
            try:
                sty = STY.load(self.cfg, rec['style'])
            except STY.StyleError as e:
                raise E(str(e))
            return SH.from_generation(self.cfg, rec, sty, author, licence, title)
        if kind == 'extension':
            try:
                return SH.from_extension(EXT.load_project(dest), author, licence, title)
            except EXT.ExtError as e:
                raise E(str(e))
        if kind == 'design':
            C = self.constructs()
            rec = next((c['meta'].get('design_record') for c in C.values() if c['meta'].get('design_record')), None)
            if not rec:
                raise E('no design record in this project (apply an environment design first)')
            D = rec['design']
            sids = {g['style'] for g in D['segments']} | {D['road_style']}
            try:
                styles = {sid: STY.load(self.cfg, sid) for sid in sids}
            except STY.StyleError as e:
                raise E(str(e))
            return SH.from_design(D, styles, author, licence, title)
        raise E("kind: 'generation' (this project) or 'extension' (an extension project folder)")

    def rta_recipe_preview(self, kind='generation', dest=None, author=None, licence=None, title=None):
        import wb_rta_share as SH
        r = self._recipe_of(kind, dest, author, licence, title)
        probs = SH.check(r)
        return {'ok': True, 'recipe_bytes': len(json.dumps(r).encode()), 'problems': probs,
                'requires': r['requires'], 'excluded': ['textures / texels', 'retail geometry', 'thumbnails', 'catalogue / view caches',
                                                        'built tracks / packages', 'local paths'],
                'sharing_md': SH.sharing_md(r) if not probs else None,
                'summary_lines': ['recipe (%s): %d bytes, %s' % (kind, len(json.dumps(r).encode()),
                                                                  'valid' if not probs else 'REFUSED: ' + '; '.join(probs[:3]))]}

    def rta_recipe_export(self, kind='generation', dest=None, author=None, licence=None, title=None, out=None):
        import wb_rta_share as SH
        self._dest_ok_ext(out)
        r = self._recipe_of(kind, dest, author, licence, title)
        try:
            res = SH.package(r, out)
        except SH.RecipeError as e:
            raise E(str(e))
        return dict(res, ok=True, summary_lines=['recipe package %s (%d bytes, sha256 %s): recipe.json + SHARING.md only' % (
            out, res['bytes'], res['sha256'][:12])])

    def rta_recipe_check(self, path=None):
        import wb_rta_share as SH
        try:
            r = SH.read(path)
        except SH.RecipeError as e:
            raise E(str(e))
        miss = SH.requirements_met(self.cfg, r)
        return {'ok': True, 'kind': r['kind'], 'title': r['title'], 'author': r['author'], 'licence': r['licence'],
                'can_rebuild': not miss, 'problems': miss,
                'summary_lines': ['%s recipe "%s" by %s: %s' % (r['kind'], r['title'], r['author'],
                                                                 'can be rebuilt from your game data' if not miss else 'CANNOT be rebuilt: ' + '; '.join(miss[:3]))]}

    def rta_recipe_rebuild(self, path=None, dest=None):
        """generation: starts the preview job on THIS project (apply with rta_generate); extension: a NEW extension project"""
        import wb_rta_share as SH
        try:
            r = SH.read(path)
        except SH.RecipeError as e:
            raise E(str(e))
        miss = SH.requirements_met(self.cfg, r)
        if miss:
            raise E('cannot rebuild: %s' % '; '.join(miss[:4]))
        if r['kind'] == 'design':
            d = r['design']
            ids = {}
            for sid, sty in d['styles'].items():            # the recipe's styles become user presets (renamed when they differ)
                try:
                    have = STY.load(self.cfg, sid)
                except STY.StyleError:
                    have = None
                nid = sid
                if have is not None and STY._sha(have) != STY._sha(sty):
                    nid = 'recipe_%s' % STY._sha(sty)[:8]
                if have is None or nid != sid:
                    STY.save_user(self.cfg, dict(sty, id=nid))
                ids[sid] = nid
            q = dict(d['request'])
            q['segments'] = [dict(g, style=ids[g['style']]) for g in q['segments']]
            q['road_style'] = ids[q['road_style']]
            params = {k: q[k] for k in ('road_width_m', 'band_m', 'verge_in_m', 'lamp_density', 'tree_density', 'plinths', 'headroom_pct',
                                        'allow_open_shells', 'objects', 'props') if k in q}   # RTA3: object / prop modes rebuild as recorded
            return self.rta_design_preview(points=q['points'], road_style=q['road_style'], segments=q['segments'], params=params,
                                           parts=q['parts'], exclude=q['exclude'], seed=q['seed'], transition_m=q['transition_m'],
                                           junction_at=q.get('junction_at'))
        if r['kind'] == 'extension':
            x = r['extension']
            f = self._ext_folder(x['track'])
            self._dest_ok_ext(dest)
            try:
                EXT.create_project(self.cfg, f, dest, r['title'])
                EXT.add_edits(dest, x['edits'], 'recipe: %s' % r['title'])
            except EXT.ExtError as e:
                raise E(str(e))
            return {'ok': True, 'project': dest, 'summary_lines': ['extension project %s rebuilt from the recipe (%d edits); Build it '
                                                                   'to get the track (LOCAL ONLY)' % (dest, len(x['edits']))]}
        g = r['generation']
        sty = g['style']
        sid = sty['id']
        try:
            have = STY.load(self.cfg, sid)
        except STY.StyleError:
            have = None
        if have is None or STY._sha(have) != STY._sha(sty):
            if have is not None:
                sid = 'recipe_%s' % STY._sha(sty)[:8]
            STY.save_user(self.cfg, dict(sty, id=sid))
        params = {k: v for k, v in g['params'].items()}
        return self.rta_generate_preview(style=sid, points=g['points'], params=params, parts=g['parts'] or None,
                                         exclude=g['exclude'], seed=g['seed'])

    RTA_OPS_LAYOUT = {k: k for k in ('rta_trust_search', 'rta_trust_asset', 'rta_trust_override', 'rta_place_preview', 'rta_place', 'rta_recipe_preview', 'rta_recipe_export', 'rta_recipe_check', 'rta_recipe_rebuild',
                                     'rta_catalogue_status', 'rta_catalogue_build', 'rta_catalogue_search', 'rta_asset', 'rta_style_show',
                                     'rta_style_derive', 'rta_style_defaults', 'rta_route_current', 'rta_ext_roundtrip', 'rta_ext_create',
                                     'rta_ext_open', 'rta_ext_unit', 'rta_ext_attach_preview', 'rta_ext_attach_add', 'rta_ext_undo',
                                     'rta_ext_attach_find',
                                     'rta_ext_build')}
