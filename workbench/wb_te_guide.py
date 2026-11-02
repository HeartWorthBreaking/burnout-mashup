"""wb_te_guide - Workbench 0.33 guidance and the test chain (Workbench 0.33, 2026-11-01), a mixin of wb_trackedit.TrackSource.

- FIX: how to fix each diagnostics check, and which tool helps (the page opens it when a problem is clicked).
- test_chain: Save state check -> Build -> Validate -> Stage (the existing Workbench job and its kit gates) -> Prepare test
  (TEST_PLAN.md + PACKAGE_RECORD.json), every run into its own NEW folder; the last successful output is recorded and never
  replaced by a failed run. Nothing is launched and nothing is approved: a game run stays an owner-present step (runner token).
- walkthrough: the first-track steps with done / to do computed from the project itself, each pointing at its tool.
- guide_section: a section of TRACK_EDITOR_GUIDE.md / TRACK_EDITOR_AUTHORING.md by topic (contextual help in the page).
- starters: ORIGINAL starter recipes (data\\starters\\*.json): a list of editor operations replayed through the normal
  preview -> apply path on a fresh project of the kit's testloop template, as ONE undo step; any refusal rolls everything back.
"""
import hashlib
import json
import os
import re
import time

T = {}
HERE = os.path.dirname(os.path.abspath(__file__))
STARTERS = os.path.join(HERE, 'data', 'starters')

FIX = {
    'open edges': ('Open edges are normal along track borders. To close a real gap: list the loops with "Mesh: faces / open loops", '
                   'then "Mesh: fill ONE explicit hole", or weld / bridge in Construct.', 'mfill'),
    'non-manifold edges': ('An edge is shared by three or more faces (duplicated faces). Undo the edit that made them, or pick the '
                           'extra faces and use "Mesh: delete faces".', 'mdel'),
    'stored normals': ('Re-generate the block from its tool, or pick the faces with "Mesh: move / turn / scale" (any small change '
                       'rewrites their normals from the face plane).', 'mxf'),
    'outside the unit regions': ('Grow a unit region over these faces (Construct -> Unit regions: "include" a rectangle, or '
                                 '"lateral" on one unit), or move the faces inside. Regions are never grown automatically.', None),
    'overlapping floors': ('Two floors at the same height fight. Raise one at least 0.03 m above the other, move it, or delete one '
                           '("Mesh: delete faces").', 'mdel'),
    'route': ('The drivable route\'s floor or walls fail a kit check. Preview "Race layout with profile" again to see the station; '
              'do not delete or move route floor / wall faces.', 'rprof'),
    'input / last build': ('Read the named file / value in the message, fix it, Save, then run "Build, validate, stage + prepare '
                           'test" again.', 'chain'),
    'obj': ('The OBJ could not be read by the kit. Restore the last backup ("Restore a backup") or fix the reported line.', 'bkr'),
}
GATE_HINTS = [('V2', 'drivable floor coverage: a route floor sample is missing or more than 0.05 m from the route height (banking, '
                     'a hole, or geometry over the road)'),
              ('V3', 'visibility (PVS walk): a section cannot see its neighbours - check unit regions and the PVS setting'),
              ('V8', 'LOD: a section\'s LOD exceeds the error bound or its slot - use decimation e_max <= 0.3 or fewer faces'),
              ('V9', 'computed PVS: switch visibility to "all" or fix the reported section'),
              ('V1', 'structure / sizes: a section exceeds a format or slot limit - see the streaming report'),
              ('wall', 'wall probe: a route wall is missing where the kit expects it (declare an outer gap if it is intentional)')]


def E(msg, detail=None):
    e = T['EditError'](msg)
    if detail is not None:
        e.detail = detail
    return e


def fix_for(check):
    key = 'route' if check.startswith('route:') else check
    return FIX.get(key, (None, None))


def _state_dir(src, *parts):
    d = os.path.join(src.cfg['state'], 'test_chain', hashlib.sha256(os.path.normcase(src.project).encode('utf-8')).hexdigest()[:12], *parts)
    return d


def _sections(path):
    try:
        text = open(path, encoding='utf-8').read()
    except OSError:
        return []
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r'^(#{2,3}) (.*)$', line)
        if m:
            cur = {'title': m.group(2).strip(), 'lines': []}
            out.append(cur)
        elif cur is not None:
            cur['lines'].append(line)
    return out


TOPICS = {'start': ['1. Start', '2. Open the editor'], 'basics': ['3. Find your way around', '4. The golden rule'],
          'first': ['5. Your first own track'], 'test': ['6. Build it and try it'], 'problems': ['When something goes wrong'],
          'race': ['Tutorial', 'Known limitations'], 'roads': ['Tutorial', 'Known limitations'], 'terrain': ['Tutorial'],
          'buildings': ['Buildings and scenery'], 'materials': ['Tutorial'], 'mesh': ['Tutorial'], 'streaming': ['Known limitations'],
          'project': ['Project health', 'Sharing'], 'limits': ['Capability matrix', 'Known limitations']}


class GuideMixin:
    # ------------------------------------------------------------------ contextual guide
    def guide_section(self, topic=None):
        if topic not in TOPICS:
            raise E('guide topic: %s' % ' / '.join(sorted(TOPICS)))
        secs = _sections(os.path.join(HERE, 'TRACK_EDITOR_GUIDE.md')) + _sections(os.path.join(HERE, 'TRACK_EDITOR_AUTHORING.md'))
        got = [s for want in TOPICS[topic] for s in secs if s['title'].startswith(want)]
        seen, text = set(), []
        for s in got:
            if s['title'] in seen:
                continue
            seen.add(s['title'])
            text += ['## ' + s['title']] + s['lines'][:80] + ['']
        return {'ok': True, 'topic': topic, 'sections': [s['title'] for s in got], 'text': '\n'.join(text).strip()[:12000],
                'summary_lines': ['guide: %s' % ', '.join(seen) if seen else 'guide: no section found for %s' % topic]}

    # ------------------------------------------------------------------ walkthrough
    def walkthrough(self):
        """the first-track steps, done / to do from the project itself (read only)"""
        C = self.constructs()
        kinds = {}
        for c in C.values():
            kinds[c['meta'].get('kind')] = kinds.get(c['meta'].get('kind'), 0) + 1
        d = self.desc()
        last = self._last_good()
        diag_bad = None
        try:
            diag_bad = [x['check'] for x in self.diagnostics()['items'] if not x['ok']]
        except T['EditError']:
            diag_bad = ['diagnostics could not run']
        b = self.last_build or {}
        steps = [
            ('route', 'Lay out the race route', bool(d.get('stations')) and ('race' in kinds or 'route_road' in kinds or bool(d.get('stations'))),
             'rprof', 'race', 'Click control points round a closed loop; keep the start stretch level. Preview, then Apply (replace all '
             'the first time).'),
            ('room', 'Make room for scenery (unit regions)', 'outside the unit regions' not in (diag_bad or []) and
             any(k in kinds for k in ('hterrain', 'terrain', 'building', 'placed', 'scatter', 'tree', 'road', 'junction')),
             None, 'race', 'Construct -> Unit regions: include a rectangle (infield) or lateral (outside). Geometry outside a region is '
             'refused, never clipped.'),
            ('terrain', 'Add terrain', any(k in kinds for k in ('hterrain', 'terrain')), 'hterr', 'terrain',
             'Height terrain a little below the road, then shape it with the brush (raise / smooth / blend to a road).'),
            ('roads', 'Add a side road or junction (optional)', any(k in kinds for k in ('road', 'junction', 'join')), 'proad', 'roads',
             'Profiled road (width / bank per point), junction piece, join two road ends. Geometric only: AI never uses them.'),
            ('scenery', 'Add buildings or scenery', any(k in kinds for k in ('building', 'tree', 'placed', 'scatter', 'barrier')), 'bldg',
             'buildings', 'Building generator (footprint, height, roof, openings), trees, prefab copies along a path.'),
            ('check', 'Fix what diagnostics finds', diag_bad == [], 'diag', 'problems',
             'Click a problem to see its faces, read how to fix it, open the suggested tool.'),
            ('save', 'Save', not self.dirty(), None, 'basics', 'Ctrl+S. A backup of the previous save is kept.'),
            ('build', 'Build, validate, stage + prepare test', bool(last) or (b.get('verdict') == 'STAGED'), 'chain', 'test',
             'Runs the kit gates and writes a test plan + package record. Nothing is launched.'),
        ]
        out = [{'step': s, 'title': t, 'done': bool(dn), 'tool': tool, 'guide': g, 'help': h} for s, t, dn, tool, g, h in steps]
        nxt = next((x for x in out if not x['done']), None)
        return {'ok': True, 'steps': out, 'next': nxt['step'] if nxt else None, 'diagnostics_open': diag_bad,
                'summary_lines': ['walkthrough: %d of %d steps done%s' % (sum(x['done'] for x in out), len(out),
                                                                         ('; next: ' + nxt['title']) if nxt else ' - ready for an owner-present test')]}

    # ------------------------------------------------------------------ Build -> Validate -> Stage -> Prepare test
    def _last_good(self):
        p = _state_dir(self, 'LAST_GOOD.json')
        try:
            r = json.load(open(p, encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return r if os.path.isdir(r.get('staged') or '') else None

    def test_chain(self, dest=None):
        """one step: Build -> Validate -> Stage (kit gates) -> Prepare test, into a NEW folder (default: "test builds" beside the project). The
        previous successful output is kept and recorded (LAST_GOOD.json); a failure never replaces it. Nothing is launched."""
        if self.dirty():
            raise E('unsaved edits: Save first (Build reads the saved project only). Nothing was built')
        stamp = time.strftime('%Y%m%d_%H%M%S')
        if dest is None:                                    # beside the project (Workbench state is protected for outputs)
            parent = os.path.join(os.path.dirname(os.path.abspath(self.project)), 'test builds')
            os.makedirs(parent, exist_ok=True)
            dest = os.path.join(parent, stamp)
        # the Workbench stage job writes <dest>\staging\.wb_stage\work\<attempt>\out\<set>\<mod>\files\Tracks\<R>\<T>_V1\<file>:
        # about 105 characters + the mod id below dest. The kit's package check cannot open paths past the Windows limit (260):
        # found by test_te44 g05 (a deep default folder made bmpack report "no Gamedata.bgd" although the file was there)
        try:
            mod = json.load(open(os.path.join(self.project, 'workbench-track.json'), encoding='utf-8')).get('mod_id') or ''
        except (OSError, ValueError):
            mod = ''
        need = len(os.path.abspath(dest)) + 105 + len(mod)
        if need > 255:
            raise E('test chain folder %s is too deep: the build would write paths of about %d characters (Windows limit 260; the kit\'s '
                    'package check cannot open them). Choose a shorter folder, e.g. near the drive root. Nothing was built' % (dest, need))
        self._dest_ok(dest, 'test chain folder')
        os.makedirs(dest)
        prev = self._last_good()
        t0 = time.time()
        st = self.stage(os.path.join(dest, 'staging'))
        steps = [{'step': 'build + validate + stage', 'ok': bool(st.get('ok') and st.get('verdict') == 'STAGED'),
                  'verdict': st.get('verdict'), 'seconds': round(time.time() - t0, 1)}]
        if not steps[0]['ok']:
            gates = st.get('gates') or {}
            hints = []
            for g, det in gates.items():
                h = next((txt for k, txt in GATE_HINTS if g.startswith(k) or k in g), 'see VALIDATION.json for the detail')
                hints.append({'gate': g, 'detail': str(det)[:300], 'how_to_fix': h})
            if not gates:                                   # failed outside the kit gates (package / host admission check, ...)
                txt = (st.get('summary') or '') + '\n' + (st.get('excerpt') or '')
                bad = [ln.strip('# ').strip() for ln in txt.splitlines() if 'FAILED' in ln][:3] or [str(st.get('verdict'))]
                for ln in bad:
                    h = ('a file the build made could not be opened: usually a path past the Windows limit (choose a shorter '
                         'folder) or a file locked by another program' if 'has no' in ln else
                         'read the step in the build log (log path above); fix it, Save, run the chain again')
                    hints.append({'gate': 'build step', 'detail': ln[:300], 'how_to_fix': h})
            return {'ok': True, 'passed': False, 'folder': dest, 'steps': steps, 'failed_gates': hints, 'log': st.get('log'),
                    'excerpt': (st.get('excerpt') or '')[-1500:], 'previous_good': prev, 'launched': False,
                    'summary_lines': ['TEST CHAIN STOPPED at build / validate / stage: %s' % st.get('verdict')] +
                    ['  %s: %s -> %s' % (h['gate'], h['detail'][:120], h['how_to_fix']) for h in hints[:10]] +
                    ['previous successful output kept: %s' % (prev['folder'] if prev else 'none yet')]}
        pt = self.prepare_test(os.path.join(dest, 'test_plan'))
        steps.append({'step': 'prepare test', 'ok': True, 'files': pt['files']})
        rec = {'time': stamp, 'folder': dest, 'staged': st.get('staged'), 'test_plan': os.path.join(dest, 'test_plan'),
               'content_sha256': self.content_sha()}
        os.makedirs(_state_dir(self), exist_ok=True)
        tmp = _state_dir(self, 'LAST_GOOD.json.tmp')
        with open(tmp, 'wb') as f:
            f.write(json.dumps(rec, indent=1).encode('utf-8'))
        os.replace(tmp, _state_dir(self, 'LAST_GOOD.json'))
        return {'ok': True, 'passed': True, 'folder': dest, 'steps': steps, 'staged': st.get('staged'), 'test_plan': rec['test_plan'],
                'previous_good': prev, 'launched': False,
                'summary_lines': ['TEST CHAIN PASSED: staged %s; test plan + package record in %s' % (st.get('staged'), rec['test_plan']),
                                  'nothing launched: an in-game run needs the owner present and the runner token (see TEST_PLAN.md)']}

    # ------------------------------------------------------------------ original starter recipes
    def starters(self):
        out = []
        if os.path.isdir(STARTERS):
            for n in sorted(os.listdir(STARTERS)):
                if n.endswith('.json'):
                    try:
                        r = json.load(open(os.path.join(STARTERS, n), encoding='utf-8'))
                    except (OSError, ValueError):
                        continue
                    out.append({'name': n[:-5], 'title': r.get('title'), 'about': r.get('about'), 'template': r.get('template'),
                                'operations': len(r.get('ops', [])), 'licence': r.get('licence')})
        return {'ok': True, 'starters': out, 'summary_lines': ['%d starter(s): %s' % (len(out), ', '.join(x['name'] for x in out))]}

    def _starter_read(self, name):
        if not (isinstance(name, str) and re.match(r'^[a-z0-9_]{1,40}$', name)):
            raise E('starter name: as listed')
        p = os.path.join(STARTERS, name + '.json')
        try:
            r = json.load(open(p, encoding='utf-8'))
        except (OSError, ValueError):
            raise E('starter %s does not exist' % name)
        try:
            ident = json.load(open(os.path.join(self.project, 'workbench-track.json'), encoding='utf-8'))
        except (OSError, ValueError):
            ident = {}
        tmpl = (ident.get('template') or {}).get('name') if isinstance(ident.get('template'), dict) else ident.get('template')
        if r.get('template') and tmpl != r['template']:
            raise E('starter %s fits a project made from the %s template (this one: %s)' % (name, r['template'], tmpl))
        return r

    def starter_apply_preview(self, name=None):
        r = self._starter_read(name)
        return {'ok': True, 'starter': name, 'title': r.get('title'), 'operations': [o.get('op') for o in r['ops']],
                'replaces_all': any(o.get('replace') == 'all' for o in r['ops']), 'preview_key': self._cons_key('starter', name),
                'note': 'preview only: nothing changed. Apply replays every operation through its own preview -> apply (all checks) '
                        'as ONE undo step; any refusal rolls everything back.',
                'summary_lines': ['starter %s: %d operation(s) (%s); REPLACES the current geometry' % (
                    name, len(r['ops']), ', '.join(o.get('op') for o in r['ops']))]}

    def starter_apply(self, name=None, preview_key=None):
        if preview_key != self._cons_key('starter', name):
            raise E('NEEDS PREVIEW: preview the starter first and apply it with its preview_key')
        r = self._starter_read(name)
        before = (self.cur, self.obj_cur, dict(getattr(self, 'pending', {})))
        n0 = len(self.undo_stack)
        done = []
        try:
            for o in r['ops']:
                kw = {k: v for k, v in o.items() if k != 'op'}
                if o['op'].endswith('_preview') or o['op'] in ('prefab_library', 'routing', 'diagnostics', 'retail_textures'):
                    raise E('starter %s: operation %s is not an edit' % (name, o['op']))
                pv = self.layout(dict(kw, op=o['op'] + '_preview'))
                self.layout(dict(kw, op=o['op'], preview_key=pv['preview_key']))
                done.append(o['op'])
        except T['EditError'] as e:
            del self.undo_stack[n0:]
            self.cur, self.obj_cur = before[0], before[1]
            self.pending = before[2]
            raise E('starter %s refused at operation %d (%s): %s. Everything rolled back' % (name, len(done) + 1, r['ops'][len(done)]['op'], e))
        steps = self.undo_stack[n0:]
        files = [s for s in steps if s['file'].startswith('file:')]         # imported textures stay their own undo steps
        after = (self.cur, self.obj_cur)
        del self.undo_stack[n0:]
        self.undo_stack.extend(files)
        self.cur, self.obj_cur = before[0], before[1]
        label = 'starter %s (%d operations)' % (name, len(steps))
        self._push('both', label, after, kind='starter', index=name)
        return {'ok': True, 'label': label, 'operations': done,
                'summary_lines': [label + ': applied as one undo step; Save writes it. Everything in it is editable like your own work.']}

    # ------------------------------------------------------------------ donor environment (read only, verified reader)
    def environment_view(self):
        """the donor track's enviro.dat (sky / sun / light) decoded READ ONLY with format_research\\fr_enviro (byte-identical round
        trip on 37 / 37 retail files); each field labelled with its evidence. The build copies this file unchanged: no editing
        until a writer and an in-game check exist."""
        import math
        import sys
        fr = os.path.join(HERE, 'format_research')
        if fr not in sys.path:
            sys.path.insert(0, fr)
        import fr_common
        import fr_enviro
        try:
            ident = json.load(open(os.path.join(self.project, 'workbench-track.json'), encoding='utf-8'))
        except (OSError, ValueError):
            ident = {}
        dd = ident.get('donor_dependency') or {}
        rel = next((r for r in dd.get('read_at_build') or [] if r.lower().endswith('enviro.dat')), None)
        gd = self.cfg.get('game_data')
        if not (rel and gd):
            raise E('environment view needs the donor dependency (workbench-track.json) and the game data folder (Workbench setting '
                    '"game_data"); found %s / %s' % (rel, gd))
        path = os.path.join(gd, *rel.split('/'))
        try:
            d = fr_common.read_ro(path)
            o = fr_enviro.parse(d)
        except (OSError, fr_common.FormatError) as e:
            raise E('donor enviro.dat could not be read (%s): %s' % (path, e))
        same = fr_enviro.serialize(o) == d
        f = o['fields']
        ev = {name: (('CODE consumer found; meaning HYP' if 'HYP' in text else 'CODE') if text.startswith('CODE') else 'NOT TRACED / HYP')
              for _off, _fmt, name, text in fr_enviro.FIELDS}
        sd = f['sun_direction'][:3]
        m = math.sqrt(sum(x * x for x in sd)) or 1.0
        el = math.degrees(math.asin(max(-1.0, min(1.0, sd[1] / m))))
        az = math.degrees(math.atan2(sd[2], sd[0]))
        r4 = lambda v: [round(x, 4) for x in v] if isinstance(v, tuple) else round(v, 4)  # noqa: E731
        return {'ok': True, 'donor': dd.get('host'), 'file': rel, 'sha256': fr_common.sha256(d), 'round_trip_identical': same,
                'fields': {k: {'value': r4(v), 'evidence': ev[k]} for k, v in f.items()},
                'textures': [{'slot': fr_enviro.SLOT[t['slot']], 'name': t['name'], 'size': [t['w'], t['h']], 'format': '0x%02X' % t['code']}
                             for t in o['tex']],
                'sun': {'elevation_deg': round(el, 2), 'azimuth_deg': round(az, 2), 'evidence': 'CODE (normalised at load, sun draw)'},
                'editable': False,
                'note': 'read only: the build copies the donor enviro.dat unchanged (donor default). Fog fields are hypotheses; no '
                        'writer exists (read-only format notes)',
                'summary_lines': ['donor %s enviro.dat: sun elevation %.1f deg, azimuth %.1f deg; light colour %s; %d sky textures (%s); '
                                  'round trip %s; READ ONLY' % (dd.get('host'), el, az, r4(f['light_colour_rgb0'])[:3], len(o['tex']),
                                                                 ', '.join(t['name'] for t in o['tex']), 'identical' if same else 'DIFFERS')]}

    GUIDE_LAYOUT = {'guide_section': 'guide_section', 'walkthrough': 'walkthrough', 'test_chain': 'test_chain',
                    'starters': 'starters', 'starter_apply_preview': 'starter_apply_preview', 'starter_apply': 'starter_apply',
                    'environment_view': 'environment_view'}


def _final(steps, which, default):
    """the buffer content after the last step that touched `which` ('desc' / 'obj')"""
    v = default
    for s in steps:
        if s['file'] == which:
            v = s['after']
        elif s['file'] == 'both':
            v = s['after'][0] if which == 'desc' else s['after'][1]
    return v
