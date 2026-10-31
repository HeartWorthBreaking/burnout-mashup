"""wb_track - Workbench v0.13: New track project -> Build -> Validate -> Stage (gp\\workbench, 2026-10-29).

A track project is the kit's own trackbuild input (0.2.1 in kit 0.6.0; v0.28 binds trackbuild 0.3.0 through the setting
"trackbuild" = main21 patch 66, sloped routes; flat tracks build byte-identical), nothing new (tools\\trackbuild\\README.md, docs\\ADVANCED.md s3):
    <name>.track.json         the track description (format trackbuild.track/1: materials, rows, obj, stations, units, route,
                              grid, start_line, checkpoints, optional traffic / lod / pvs / wall_gaps)
    <name>.obj / .mtl         the OBJ mesh (`v x y z r g b`, vt, vn, usemtl, tri / quad faces); the .mtl is NOT read by trackbuild
    textures\\*.png           the material textures (8-bit RGB / opaque RGBA, power of two 4..1024)
    package.toml              trackbuild's package decisions ([package] table, the kit's examples\\my_track_package.toml keys)
    workbench-track.json      the declared identity (mod id + track id), the template's provenance, the donor dependency
    README.txt
The template sources are written by the KIT's own generator (`tb.py gen-testloop`, the authored demo the kit README names) into
a Workbench temp folder and copied byte for byte. Nothing from the project is ever executed.
Build = the Workbench-owned recipes 'track-project' / 'trackbuild-testloop' (wb_stage.RECIPES): fixed argument lists for the
kit's tb.py build / validate / package, then the kit's bmpack validate of the mod folder, run in an isolated COPY of the
checked inputs only (description, OBJ, textures, package.toml) under <staging>\\.wb_stage\\work\\<time>.
Before anything runs, input_check() refuses (read only): links / reparse points, scripts / executables / build files, a
malformed description / package.toml, missing OBJ / textures, references that leave the project ('..', absolute, drive, UNC,
scheme), identity mismatches, reserved / retail / malformed ids. Unsupported features: trackbuild's own refusals (exit 4).
DONOR DEPENDENCY: trackbuild does not make a whole track. The Gamedata header / event records, enviro.dat (sky, light) and the
audio (SOUND.AWD, CRASH1..3.RWS, E_DJRACE.xwb, MUSIC.RWS) are copies of retail EU/M1_V1 from YOUR game data (hash-pinned by
trackbuild): the package is LOCAL ONLY.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import tomllib

import wb_car
import wb_core as core
import wb_kit
import wb_project as proj
import wb_stage as stg

SCHEMA = 'bm-workbench-track-project/1'
MARKER = 'workbench-track.json'
TB = r'tools\trackbuild\tb.py'
TB_REFERENCE = r'tools\trackbuild\tests\REFERENCE_0_2_1.json'
TB_EXAMPLE_TOML = r'tools\trackbuild\examples\test_loop_package.toml'
TEMPLATES = {'testloop': None, 'canyon': 'canyon',           # tb.py gen-testloop [--variant canyon] (kit README "Quick start")
             'hill': 'hill'}                                  # v0.28: trackbuild 0.3.0 sloped demo (+8 m hill; 0.2.1 refuses it)
DESC_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}\.track\.json$')
TRACK_ID_RE = re.compile(r'^(EU|US|AS)_[A-Z0-9]{2}_V[0-9]$')     # retail regions only (no region declaration: deferred)
TEXT_RE = re.compile(r"^[A-Za-z0-9 \-'.&]+$")
VERSION_RE = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+$')
DESC_KEYS = ('obj', 'materials', 'rows', 'stations', 'units', 'route', 'grid', 'start_line', 'checkpoints', 'stations_per_slice')
PKG_KEYS = ('set', 'folder', 'track_id', 'track_name', 'track_location', 'mod_id', 'mod_name', 'version', 'author')
SET = 'workbench'                                               # package.toml set of a track project (staged folder = mod id)
DONOR_HOST = 'EU/M1_V1'
DONOR_FILES = ('Gamedata.bgd', 'enviro.dat', 'SOUND.AWD', 'CRASH1.RWS', 'CRASH2.RWS', 'CRASH3.RWS', 'E_DJRACE.xwb', 'MUSIC.RWS')
TRACK_FILES = ('static.dat', 'streamed.dat', 'Gamedata.bgd', 'enviro.dat', 'SOUND.AWD', 'CRASH1.RWS', 'CRASH2.RWS', 'CRASH3.RWS',
               'E_DJRACE.xwb', 'MUSIC.RWS')                    # trackconv package.FILES
SUPPORTED = {                                                   # docs\ADVANCED.md s3 / s4 (what trackbuild 0.2.1 / 0.3.0 builds)
    'geometry / materials': 'OBJ (tri / quad, uv + normal, vertex colour) + opaque DXT1 PNG textures, <= 83 material rows',
    'collision': 'per material: surface word, collide, car_solid -> KD trees per unit (AUTHORED)',
    'routes': 'stations (centre line, tangents, lane offsets; trackbuild 0.3.0: each station\'s own height, so a route may '
              'climb / descend), route lanes + corners -> S4 route (AUTHORED)',
    'starts': 'grid (6 slots), start_line, checkpoints 1..12 -> S1 page (AUTHORED)',
    'streaming': 'units (cut station pairs + lateral bounds) -> streamed units, 4..162 units (AUTHORED)',
    'visibility': 'pvs.mode all (<= 17 units) | computed (<= 162 units) (AUTHORED)',
    'LOD': 'lod.mode identity | decimate (e_max <= 0.3 m) (AUTHORED)',
    'traffic': 'optional: one road, 1..4 same-way lanes, one set (AUTHORED); without it DONOR traffic'}
DEFERRED = [
    'interactive 3D editing beyond the v0.22 slice (wb_trackedit.py: start moves, material assignment, vertex colour, material '
    'texture / surface / collide / car_solid, translating / turning / scaling selected face groups isolated or connected, '
    'boundary inspection and welding of open-edge vertices / chains, duplicating face groups, bridging two selected open-edge '
    'chains with new faces): automatic gap / hole filling, other topology edits, stations, units, routes, new materials are '
    'not editable',
    'own region / region declaration ([bmashup.regions]): track ids use a retail region EU / US / AS',
    'point-to-point tracks (trackbuild 0.2.1 / 0.3.0 build closed circuits only)',
    'alpha / additive / animated / reflective / water materials, props, instances, backdrops (trackbuild refuses them)',
    'own sky / lighting (enviro.dat), own audio, own event header: DONOR copies of EU/M1_V1',
    'another donor host (--host / --unpinned-donor): the Workbench builds with the pinned default host only',
    'off-track reset: UNTESTED by the kit (never triggered in its runs)',
    'more than one track per project']


def _say_text(v, what, n):
    if not isinstance(v, str) or not 1 <= len(v) <= n or v != v.strip() or not TEXT_RE.match(v):
        return '%s %r: 1..%d characters A-Z a-z 0-9 space - \' . & (no quotes / backslashes), no leading / trailing spaces' % (
            what, v, n)
    return None


# ---------------------------------------------------------------- identity checks
def retail_tracks(cfg):
    """retail track ids RR_NN_VN from YOUR game data's Tracks folder (read only listing)"""
    t = os.path.join(cfg.get('game_data') or '', 'Tracks')
    out = set()
    try:
        for r in os.listdir(t):
            if re.fullmatch(r'[A-Z]{2}', r) and os.path.isdir(os.path.join(t, r)):
                out |= {'%s_%s' % (r, n) for n in os.listdir(os.path.join(t, r)) if re.fullmatch(r'[A-Z0-9]{2}_V[0-9]', n)}
    except OSError:
        pass
    return out


def check_track_id(v, cfg=None):
    if not isinstance(v, str) or not TRACK_ID_RE.match(v):
        return ('track id %r: RR_NN_VN with a retail region EU / US / AS (e.g. EU_T7_V1); own regions are deferred' % (v,))
    if cfg is not None:
        rt = retail_tracks(cfg)
        if not rt:
            return 'no retail track list: game data %r has no Tracks folder (set Game data in Settings)' % cfg.get('game_data')
        if v in rt:
            return 'track id %s is a retail track (the host refuses a duplicate track id): choose your own' % v
    return None


def check_identity(cfg, mod_id, track_id, name, location, mod_name, version, author):
    bad = [proj.check_mod_id(mod_id), check_track_id(track_id, cfg), _say_text(name, 'track name', 27),
           _say_text(location, 'track location', 17), proj.check_name(mod_name), _say_text(author, 'author', 64),
           None if isinstance(version, str) and VERSION_RE.match(version) else 'version %r: MAJOR.MINOR.PATCH (e.g. 1.0.0)' % (version,)]
    return [b for b in bad if b]


def donor_dependency(track_id=None):
    return {'host': DONOR_HOST, 'label': 'DONOR DEPENDENCY: not authored, not project content - YOUR retail game data',
            'read_at_build': ['Tracks/EU/M1_V1/%s' % f for f in DONOR_FILES],
            'verified': 'sha256 + size pinned by trackbuild (trackbuild\\donor.py DONOR_PINS); a mismatch stops the build (exit 3)',
            'in_package': {'Gamedata.bgd': 'DONOR header + event records (+ S2 / S3 when the description has no traffic); '
                                           'AUTHORED S1 page + S4 route (+ traffic); donor id renamed to %s' % (track_id or 'the track id'),
                           'enviro.dat': 'DONOR (unchanged copy: sky, clouds, lighting)',
                           'SOUND.AWD, CRASH1..3.RWS, E_DJRACE.xwb, MUSIC.RWS': 'DONOR (unchanged copies: audio)'},
            'authored': ['static.dat', 'streamed.dat (render, collision, units, LOD, PVS)', 'Gamedata.bgd S1 page + S4 route'],
            'local_only': True, 'note': 'the built package contains retail game data: local only, never upload or ship it'}


# ---------------------------------------------------------------- templates (the kit's own generator, run in a temp folder)
def kit_tb(cfg):
    return core.kit_path(cfg, TB)                  # v0.28: the bound trackbuild tree (setting "trackbuild", else the kit's)


def generate_template(cfg, template, out_dir):
    """`tb.py gen-testloop OUT [--variant canyon]` (the kit's authored demo sources) -> (files {rel: sha256}, problem)"""
    argv = [cfg['python'], '-B', kit_tb(cfg), 'gen-testloop', out_dir] + (['--variant', TEMPLATES[template]] if TEMPLATES[template] else [])
    p = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300,
                       creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        return None, 'the kit generator failed (exit %s): %s' % (p.returncode, (p.stderr or p.stdout).strip()[-400:])
    return stg.tree_hashes(out_dir), None


def package_toml(t):
    """package.toml from validated values only (no quotes / backslashes / line breaks are possible)"""
    q = lambda s: '"%s"' % s                                                 # noqa: E731
    L = ['# trackbuild package decisions (tb.py package BUILD_DIR this.toml SET_ROOT) - made by the Burnout Mashup Workbench',
         '# (New track project, template "%s"). Keys: the kit\'s tools\\trackbuild\\examples\\my_track_package.toml.' % t['template'],
         '# Keep mod_id, track_id, set and folder equal to workbench-track.json. Names may be edited.',
         '[package]']
    for k in ('set', 'folder', 'track_id', 'track_name', 'track_location', 'mod_id', 'mod_name', 'version', 'author', 'description',
              'platform'):
        L.append('%s = %s' % (k, q(t[k])))
    L += ['', '[package.comments]',
          'header = "# %s - ORIGINAL geometry, collision, route and start grid built with trackbuild (Burnout Mashup Workbench).\\n'
          '# DONOR DEPENDENCY: Gamedata header / event records, enviro.dat and audio come from retail EU_M1_V1 (your game data): '
          'LOCAL ONLY.\\n"' % t['track_name'],
          'tracks = "# Added to the retail %s region (no region declaration needed). A circuit: no point_to_point entry.\\n"'
          % {'EU': 'Europe', 'US': 'USA', 'AS': 'Asia'}[t['track_id'][:2]],
          '', '[package.provenance]',
          'packaged_by = "trackbuild (trackconv package, bmpack rename_gamedata) via the Burnout Mashup Workbench"',
          'donor_note = "EU_M1_V1 = Gamedata host (header, event records) and enviro / audio donor; static.dat, streamed.dat, the S1 '
          'page and the S4 route are authored"']
    return '\n'.join(L) + '\n'


def readme(t):
    return ('%(track_name)s (%(track_id)s, mod %(mod_id)s)\n\nA track project made by the Burnout Mashup Workbench (New track project) '
            'for the kit\'s trackbuild.\n\n'
            '  %(desc)s   the track description (trackbuild.track/1; kit docs\\ADVANCED.md s3)\n'
            '  %(obj)s, textures\\*.png   the OBJ mesh and its textures (Y up, metres, game frame)\n'
            '  package.toml          trackbuild\'s package decisions (names, version; keep mod_id / track_id / set / folder)\n'
            '  workbench-track.json  the declared identity, the template\'s provenance and the donor dependency\n\n'
            'DONOR DEPENDENCY: the Gamedata header / event records, enviro.dat and the audio are retail EU/M1_V1 copies from YOUR\n'
            'game data. The built package contains retail data: local only, never upload it.\n\n'
            'Build / validate / stage: Workbench -> Build / stage tab -> this folder -> a staging folder. The Workbench runs the kit\'s\n'
            'tb.py build / validate / package and bmpack with its own fixed arguments on a copy of the inputs; nothing here is run.\n'
            'OBJ and texture paths in the description must stay inside this folder. Edit: wb_trackedit.py (first slice).\n') % t


def folder_problems(cfg, folder):
    return proj.folder_problems(cfg, folder)


def _write_tree(tmp, folder):
    if os.path.isdir(folder):
        if os.listdir(folder):
            raise FileExistsError(folder)
        os.rmdir(folder)
    os.rename(tmp, folder)


def create_project(cfg, folder, mod_id, track_id, name, location=None, mod_name=None, version='1.0.0', author='Workbench user',
                   template='testloop'):
    """-> {'ok', 'verdict', 'project', 'problems', 'files', 'identity'}; nothing is written unless every check passed"""
    res = {'kind': 'new-track-project', 'ok': False, 'project': os.path.abspath(folder) if folder and os.path.isabs(folder) else folder,
           'mod_id': mod_id, 'track_id': track_id, 'verdict': 'NOT CREATED'}
    location = location if location is not None else 'MY TRACKS'
    mod_name = mod_name if mod_name is not None else name
    bad = []
    if template not in TEMPLATES:
        bad.append('template %r: %s' % (template, ' | '.join(TEMPLATES)))
    if not os.path.isfile(kit_tb(cfg)):
        bad.append('kit file missing: %s (is the kit set to the mod kit 0.6.0 folder?)' % TB)
    bad += check_identity(cfg, mod_id, track_id, name, location, mod_name, version, author)
    bad += folder_problems(cfg, folder)
    res['problems'] = bad
    if bad:
        return res
    folder = os.path.abspath(folder)
    tmp = os.path.join(os.path.dirname(folder), '.%s.wb_new_%s' % (os.path.basename(folder),
                                                                    datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    try:
        gen, why = generate_template(cfg, template, tmp)
        if why:
            raise RuntimeError(why)
        desc = [n for n in gen if '/' not in n and n.endswith('.track.json')]
        obj = json.load(open(os.path.join(tmp, desc[0]), encoding='utf-8'))['obj']
        t = {'template': template, 'set': SET, 'folder': mod_id, 'track_id': track_id, 'track_name': name, 'track_location': location,
             'mod_id': mod_id, 'mod_name': mod_name, 'version': version, 'author': author, 'platform': '>=0.1',
             'description': 'An original track built with trackbuild (Burnout Mashup Workbench). Gamedata header, enviro and audio '
                            'are borrowed from EU_M1_V1 (donor, local only).', 'desc': desc[0], 'obj': obj}
        texts = {'package.toml': package_toml(t), 'README.txt': readme(t)}
        for n, x in texts.items():
            with open(os.path.join(tmp, n), 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(x)
        ident = {'schema': SCHEMA, 'mod_id': mod_id, 'track_id': track_id, 'folder': mod_id, 'set': SET, 'desc': desc[0],
                 'created': datetime.datetime.now().isoformat(timespec='seconds'),
                 'template': {'kit': cfg['kit'], 'generator': 'tb.py gen-testloop' + (' --variant %s' % TEMPLATES[template]
                                                                                      if TEMPLATES[template] else ''),
                              'name': template, 'files': gen, 'by': 'Workbench wb_track.py (v0.13)'},
                 'kit': wb_kit.stamp(wb_kit.kit_identity(cfg['kit'])), 'kit_history': [],
                 'created_files': dict(gen, **{n: wb_car.sha256_bytes(x.encode('utf-8')) for n, x in texts.items()}),
                 'donor_dependency': donor_dependency(track_id), 'supported': SUPPORTED,
                 'build': 'Workbench-owned recipe track-project (kit tb.py build + validate + package, bmpack validate)',
                 'deferred': DEFERRED}
        with open(os.path.join(tmp, MARKER), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(ident, fh, indent=1)
        _write_tree(tmp, folder)
    except Exception as e:                                                  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)                              # our own half-written temp folder only
        res.update(problems=['could not create the project: %s' % e])
        return res
    res.update(ok=True, verdict='CREATED', project=folder, files=sorted(stg.tree_hashes(folder)), identity=ident,
               track={k: t[k] for k in ('track_id', 'track_name', 'track_location', 'mod_id', 'mod_name', 'version', 'author')})
    return res


def create_example(cfg, folder):
    """the kit's own reference input as a project: gen-testloop + a byte copy of examples\\test_loop_package.toml (= package.toml).
    Built by recipe trackbuild-testloop; reference = tests\\REFERENCE_0_2_1.json test_loop."""
    res = {'kind': 'track-kit-example', 'ok': False, 'project': folder, 'verdict': 'NOT CREATED'}
    bad = folder_problems(cfg, folder)
    for f in (TB, TB_EXAMPLE_TOML, TB_REFERENCE):
        if not os.path.isfile(core.kit_path(cfg, f)):
            bad.append('kit file missing: %s' % f)
    res['problems'] = bad
    if bad:
        return res
    folder = os.path.abspath(folder)
    tmp = os.path.join(os.path.dirname(folder), '.%s.wb_new_%s' % (os.path.basename(folder),
                                                                    datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    try:
        _, why = generate_template(cfg, 'testloop', tmp)
        if why:
            raise RuntimeError(why)
        shutil.copyfile(core.kit_path(cfg, TB_EXAMPLE_TOML), os.path.join(tmp, 'package.toml'))
        _write_tree(tmp, folder)
    except Exception as e:                                                  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        res.update(problems=['could not create the example: %s' % e])
        return res
    res.update(ok=True, verdict='CREATED', project=folder, files=sorted(stg.tree_hashes(folder)))
    return res


# ---------------------------------------------------------------- reading a project / kit binding
def is_track_project(project):
    return bool(project) and os.path.isfile(os.path.join(project, MARKER))


def looks_like_track(project):
    """a folder with package.toml + one *.track.json at the top and no mod.toml"""
    try:
        names = os.listdir(project)
    except OSError:
        return False
    return 'package.toml' in names and 'mod.toml' not in names and any(n.endswith('.track.json') for n in names)


def _marker(project):
    try:
        d = json.load(open(os.path.join(project, MARKER), encoding='utf-8'))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def read_project(project):
    """-> (identity {mod_id, track_id, folder, set, desc}, problems) from workbench-track.json (re-checked)"""
    d = _marker(project)
    if not d or d.get('schema') != SCHEMA:
        return None, ['%s unreadable or schema is not %s' % (MARKER, SCHEMA)]
    bad = [x for x in (proj.check_mod_id(d.get('mod_id') if isinstance(d.get('mod_id'), str) else ''), check_track_id(d.get('track_id')))
           if x]
    if d.get('folder') != d.get('mod_id') or d.get('set') != SET:
        bad.append('%s: folder must equal the mod id and set must be %r' % (MARKER, SET))
    if not isinstance(d.get('desc'), str) or not DESC_RE.match(d['desc']):
        bad.append('%s: desc must be a <name>.track.json file name' % MARKER)
    if bad:
        return None, ['%s: %s' % (MARKER, b) for b in bad]
    return {k: d[k] for k in ('mod_id', 'track_id', 'folder', 'set', 'desc')}, []


def kit_status(cfg, project):
    d = _marker(project) or {}
    cur = wb_kit.kit_identity(cfg.get('kit'))
    rec = d.get('kit') if isinstance(d.get('kit'), dict) else None
    if not rec:
        return {'state': 'unbound', 'text': 'the track project has no kit binding', 'recorded': None, 'current': wb_kit.stamp(cur)}
    if wb_kit.same(rec, cur):
        return {'state': 'same', 'text': 'bound to the current kit %s' % rec.get('id'), 'recorded': rec, 'current': wb_kit.stamp(cur)}
    return {'state': 'different', 'recorded': rec, 'current': wb_kit.stamp(cur), 'diff': wb_kit.diff(rec, cur),
            'text': 'bound to kit %s, the current kit is %s: not migrated. Rebind explicitly to build with the current kit '
                    '(earlier staged outputs are kept), or switch the kit back' % (rec.get('id'), (cur or {}).get('id'))}


def rebind_project(cfg, project):
    """explicit user action: bind to the current kit (only workbench-track.json changes, atomic replace)"""
    res = {'kind': 'rebind', 'ok': False, 'project': project, 'verdict': 'NOT REBOUND'}
    _, bad = read_project(project)
    st = kit_status(cfg, project)
    if not bad and st['state'] == 'same':
        bad = ['already bound to the current kit %s' % st['recorded']['id']]
    if not cfg.get('kit') or not wb_kit.kit_identity(cfg.get('kit')):
        bad = list(bad) + ['kit: ' + core.check_value('kit', cfg.get('kit') or '')]
    res['problems'] = bad
    if bad:
        return res
    d = _marker(project)
    d['kit_history'] = list(d.get('kit_history') or []) + [{'kit': st['recorded'], 'until': datetime.datetime.now().isoformat(
        timespec='seconds'), 'reason': 'rebound by the user to %s' % st['current']['id']}]
    d['kit'] = st['current']
    p = os.path.join(project, MARKER)
    with open(p + '.wb_tmp', 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(d, fh, indent=1)
    os.replace(p + '.wb_tmp', p)
    res.update(ok=True, verdict='REBOUND', previous=st['recorded'], kit=st['current'], diff=st.get('diff') or [])
    return res


# ---------------------------------------------------------------- input checks (READ ONLY; nothing runs)
def load_desc(path):
    """-> (description dict, problem); structure the kit's io.read_desc also requires (it re-checks everything)"""
    try:
        d = json.loads(open(path, 'rb').read().decode('utf-8'))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        return None, 'malformed track description: %s is not valid UTF-8 JSON (%s)' % (os.path.basename(path), e)
    if not isinstance(d, dict) or d.get('format') != 'trackbuild.track/1':
        return None, 'malformed track description: %s is not a trackbuild.track/1 object' % os.path.basename(path)
    miss = [k for k in DESC_KEYS if k not in d]
    if miss:
        return None, 'malformed track description: missing key(s) %s' % ', '.join(miss)
    if d.get('closed') is not True:
        return None, 'unsupported: only closed circuits ("closed": true) are built by trackbuild 0.2.1 / 0.3.0'
    if not isinstance(d['materials'], dict) or not all(isinstance(m, dict) for m in d['materials'].values()):
        return None, 'malformed track description: "materials" must be an object of objects'
    return d, None


def input_check(cfg, project, rid, ident=None):
    """what the build would read and why it would refuse -> info {problems, checks, notes, inputs {rel: sha256}, track}.
    READ ONLY: nothing is executed or written."""
    info = {'kind': 'track-input-check', 'project': os.path.abspath(project) if project else project, 'recipe': rid,
            'problems': [], 'checks': [], 'notes': [], 'inputs': {}, 'track': None}
    bad = info['problems']

    def c(name, ok, detail):
        info['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
        if not ok:
            bad.append('%s: %s' % (name, detail))
        return ok
    if not project or not os.path.isdir(project):
        bad.append('project folder not found: %s' % project)
        return info
    project = info['project']
    files, wbad = stg._walk_source(project)
    bad += wbad
    files_ci = {k.lower(): k for k in files}
    for rel in files:
        n = rel.rsplit('/', 1)[-1]
        if proj.FORBIDDEN_BUILD_FILES.match(n) or n.lower().endswith(stg.RUNNABLE_EXT):
            bad.append('%s: a script / executable / build file in a track project is refused (the Workbench never runs project '
                       'files; it runs only the kit\'s trackbuild and bmpack): remove it' % rel)
    descs = sorted(n for n in files if '/' not in n and n.endswith('.track.json'))
    rec = stg.RECIPES.get(rid) or {}
    if rec.get('project'):
        ident = ident or read_project(project)[0]
    want = ident['desc'] if ident else (descs[0] if len(descs) == 1 else None)
    if not c('one track description (<name>.track.json)', want and want in files and DESC_RE.match(want) and
             (len(descs) == 1 or ident), want if want in files else 'found %s' % (descs or 'none')):
        return info
    d, why = load_desc(os.path.join(project, want))
    if not c('track description parses (trackbuild.track/1, required keys, closed)', d is not None, why or want):
        return info
    inputs = [want]
    o = d.get('obj')
    why = wb_car.rel_problem(o, 'description obj')
    if c('description obj inside the project', not why, why or o):
        if not str(o).lower().endswith('.obj'):
            c('description obj is OBJ', False, 'unsupported mesh format %r (trackbuild reads .obj)' % o)
        else:
            r_, why = wb_car._resolve(project, files_ci, o, 'description obj')
            if c('OBJ file present', r_, why or r_):
                inputs.append(r_)
    texs = {}
    for name, m in sorted(d['materials'].items()):
        tp = m.get('texture')
        why = wb_car.rel_problem(tp, 'material %s texture' % name)
        if not c('material %s texture inside the project' % name, not why, why or tp):
            continue
        if not str(tp).lower().endswith('.png'):
            c('material %s texture is PNG' % name, False, 'unsupported texture format %r (trackbuild reads PNG)' % tp)
            continue
        r_, why = wb_car._resolve(project, files_ci, tp, 'material %s texture' % name)
        if c('material %s texture present' % name, r_, why or r_):
            inputs.append(r_)
            texs[name] = r_
    try:
        t = tomllib.loads(open(os.path.join(project, 'package.toml'), encoding='utf-8').read())
        c('package.toml parses (TOML)', True, 'ok')
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        c('package.toml parses (TOML)', False, str(e))
        return info
    p = t.get('package') if isinstance(t.get('package'), dict) else None
    if not c('package.toml [package] table', p is not None and all(k in p for k in PKG_KEYS),
             'ok' if p and all(k in p for k in PKG_KEYS) else 'missing [package] or keys %s' % [k for k in PKG_KEYS if k not in (p or {})]):
        return info
    inputs.append('package.toml')
    info['track'] = {k: p.get(k) for k in PKG_KEYS}
    info['track'].update(desc=want, obj=o, textures=texs, units=len(d.get('units') or []), name_in_desc=d.get('name'),
                         pvs=(d.get('pvs') or {}).get('mode', 'all'), lod=(d.get('lod') or {}).get('mode', 'identity'),
                         traffic='AUTHORED' if d.get('traffic') else 'DONOR')
    for k in ('set', 'folder'):
        why = wb_car.rel_problem(p.get(k), 'package.toml %s' % k)
        c('package.toml %s is one folder name' % k, not why and '/' not in str(p.get(k)) and '\\' not in str(p.get(k)),
          why or p.get(k))
    if rec.get('project'):
        if ident:
            for k in ('mod_id', 'track_id', 'folder', 'set'):
                c('package.toml %s = workbench-track.json' % k, p.get(k) == ident[k], '%r (declared %r)' % (p.get(k), ident[k]))
            why = proj.check_mod_id(p.get('mod_id') or '')
            c('mod id (own namespace)', not why, why or p.get('mod_id'))
    elif rec.get('mod_id'):
        c('package.toml mod_id = the kit example\'s', p.get('mod_id') == rec['mod_id'] and p.get('folder') == rec['folder'],
          '%s / %s' % (p.get('mod_id'), p.get('folder')))
    why = check_track_id(p.get('track_id'), cfg)
    c('track id', not why, why or p.get('track_id'))
    for k, n in (('track_name', 27), ('track_location', 17)):
        why = _say_text(p.get(k), k.replace('_', ' '), n)
        c('package.toml %s' % k, not why, why or p.get(k))
    for k in p:
        if k not in PKG_KEYS + ('description', 'platform', 'comments', 'provenance'):
            info['notes'].append('package.toml key %r is not set by the Workbench (trackbuild / trackconv reads it as is)' % k)
    for k in d:
        if k not in DESC_KEYS + ('format', 'label', 'name', 'generator', 'loop_length', 'closed', 'traffic', 'gamedata_header', 'pvs',
                                 'lod', 'wall_gaps', 'barrier_station'):
            info['notes'].append('description key %r is not a documented trackbuild key: kept as is, trackbuild decides' % k)
    for rel in sorted(files):
        if rel not in inputs and rel != MARKER:
            info['notes'].append('not an input (stays in the project, not copied into the build): %s%s' % (
                rel, ' (trackbuild does not read the .mtl; textures come from the description)' if rel.endswith('.mtl') else ''))
    if not bad:
        info['inputs'] = {rel: wb_kit.sha256_file(os.path.join(project, *rel.split('/'))) for rel in dict.fromkeys(inputs)}
    return info


def prereqs(cfg, rid, project):
    bad = []
    k = cfg.get('kit') or ''
    if not k:
        return ['kit: ' + core.check_value('kit', '')]
    for f in (TB,) + ((TB_REFERENCE,) if not (stg.RECIPES.get(rid) or {}).get('project') else ()):
        if not os.path.isfile(core.kit_path(cfg, f)):
            bad.append('kit file missing: %s (is %s the mod kit 0.6.0 folder / the trackbuild setting %s?)' % (
                f, k, core.trackbuild_dir(cfg)))
    bad += core.bmpack_prereqs(cfg, need_game=True)
    if (stg.RECIPES.get(rid) or {}).get('project'):
        _, b = read_project(project)
        bad += b
        if not b:
            st = kit_status(cfg, project)
            if st['state'] != 'same':
                bad.append('kit binding: ' + st['text'])
    return bad


def start_problems(cfg, rid, project, dest):
    rec = stg.recipe(rid, project)
    bad = stg.check_destination(cfg, project, dest) + prereqs(cfg, rid, project)
    info = None
    if not bad:
        bad += stg.collision_problems(dest, rec, project)
        info = input_check(cfg, project, rid)
        bad += info['problems']
    return bad, info


# ---------------------------------------------------------------- the build (inside wb_stage.StageJob)
def stage(job, r, rec):
    """StageJob._stage for kind 'track': checks -> isolated copy of the inputs -> kit tools (fixed argv) -> checks -> commit"""
    cfg, op = job.cfg, job.op
    job.log('# %s\n# recipe %s, project %s, destination %s' % (op.title, op.rid, op.project, op.dest))
    rid, why = stg.detect(op.project)
    bad = [why] if why else ([] if rid == op.rid else ['the project is not a %s project' % op.rid])
    info = None
    if not bad:
        bad, info = start_problems(cfg, op.rid, op.project, op.dest)
    if info:
        for ch in info['checks']:
            job.log('# check %-55s %s  %s' % (ch['check'], 'ok' if ch['ok'] else 'FAILED', ch['detail']))
        for n in info['notes']:
            job.log('# note: ' + n)
        r['input_check'] = {k: v for k, v in info.items() if k != 'kind'}
    if bad:
        for b in bad:
            job.log('REFUSED: ' + b)
        r.update(verdict='NOT STARTED', excerpt=bad)
        return
    src_before = stg.tree_hashes(op.project)
    st = os.path.join(op.dest, '.wb_stage')
    attempt = os.path.join(st, 'work', job.ts)
    r['attempt'] = attempt
    work = build(job, r, rec, attempt, info)
    if work:
        job._commit(r, rec, st, work, src_before)


def _tb_fail(r, name, rc, o, vpath=None):
    gates = []
    if vpath and os.path.isfile(vpath):
        try:
            gates = json.load(open(vpath, encoding='utf-8'))['summary']['failed']
        except (OSError, ValueError, KeyError):
            pass
    msgs = [l for l in o.splitlines() if l.startswith('trackbuild:')] or [l for l in o.splitlines() if l.strip()][-10:]
    r['failed_gates'] = gates
    r.update(verdict='VALIDATION FAILED' if rc in (1, 4) else 'BUILD FAILED',
             excerpt=['%s exit %s%s:' % (name, rc, {1: ' (gate failed)', 2: ' (usage / path)', 3: ' (missing prerequisite)',
                                                    4: ' (unsupported input, refused)'}.get(rc, ''))] + ['  ' + m for m in msgs] +
             (['  failed gates: %s' % ', '.join(gates)] if gates else []))


def build(job, r, rec, attempt, info):
    cfg, op = job.cfg, job.op
    tr = info['track']
    src, tbuild, out = os.path.join(attempt, 'src'), os.path.join(attempt, 'build'), os.path.join(attempt, 'out')
    for rel in info['inputs']:
        d = os.path.join(src, *rel.split('/'))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(os.path.join(op.project, *rel.split('/')), d)
    copied = stg.tree_hashes(src)
    if copied != info['inputs']:
        r.update(verdict='COPY FAILED (not staged)', excerpt=['the input copy differs from the checked inputs'])
        return None
    job.log('# isolated build copy: %d input files in %s (sha256 = the checked inputs)' % (len(copied), src))
    t = stg.tools(cfg)
    ident = {'python': {'path': t['python']}}
    rc, o = job._run('identify trackbuild', [t['python'], '-B', t['trackbuild'], 'version'], attempt)
    if job.cancelled:
        r.update(verdict='CANCELLED')
        return None
    tree = os.path.dirname(t['trackbuild'])
    ident['trackbuild'] = {'path': t['trackbuild'], 'sha256': wb_kit.sha256_file(t['trackbuild']), 'version': wb_car._json_out(o),
                           'rc': rc, 'tree_sha256': wb_car.sha256_bytes(json.dumps(stg.tree_hashes(tree), sort_keys=True).encode())}
    ident['python']['version'] = (ident['trackbuild']['version'] or {}).get('python')
    if rc != 0:
        r.update(verdict='BUILD FAILED', excerpt=['trackbuild version: exit %s (cannot run the kit tool)' % rc] +
                 [l for l in o.splitlines() if l.strip()][-6:])
        return None
    r['tools'] = ident
    r['mode'] = 'project' if rec.get('project') else 'reference'
    paths = {'src': src, 'tbuild': tbuild, 'out': out, 'desc': tr['desc']}
    checks = []
    for name, key, cwd in (('trackbuild build', 'track_build', src), ('trackbuild validate', 'track_validate', src),
                           ('trackbuild package', 'track_package', src)):
        rc, o = job._run(name, stg.expand(rec[key], cfg, paths), cwd)
        r['steps'].append({'step': name, 'rc': rc})
        if job.cancelled:
            r.update(verdict='CANCELLED')
            return None
        if rc != 0:
            _tb_fail(r, name, rc, o, os.path.join(tbuild, 'VALIDATION.json') if name == 'trackbuild validate' else None)
            checks.append({'check': '%s (the kit tool\'s own checks)' % name, 'ok': False, 'detail': ' | '.join(r['excerpt'])[:2000]})
            r['checks'] = checks
            return None
    val = json.load(open(os.path.join(tbuild, 'VALIDATION.json'), encoding='utf-8'))
    rep = json.load(open(os.path.join(tbuild, 'BUILD_REPORT.json'), encoding='utf-8'))
    gates = {k: bool(v.get('ok')) for k, v in sorted(val.items()) if k != 'summary' and isinstance(v, dict) and 'ok' in v}
    checks.append({'check': 'trackbuild validate gates (independent readers)', 'ok': bool(val['summary']['ok']),
                   'detail': '%d / %d gates ok%s' % (sum(gates.values()), len(gates), '' if val['summary']['ok'] else
                                                     ', failed %s' % val['summary']['failed'])})
    work = os.path.join(out, tr['set'], tr['folder'])
    r['work'] = work
    rel_t = 'files/Tracks/%s/%s' % (tr['track_id'][:2], tr['track_id'][3:])
    want = ['bmpack.json', 'mod.toml'] + ['%s/%s' % (rel_t, f) for f in TRACK_FILES]
    files = stg.tree_hashes(work) if os.path.isdir(work) else {}
    miss = [w for w in want if w not in files]
    extra = sorted(set(files) - set(want))
    checks.append({'check': 'package = trackbuild\'s documented layout', 'ok': not miss and not extra,
                   'detail': 'missing %s, unexpected %s' % (miss, extra) if miss or extra else '%d files' % len(files)})
    setfiles = {k: v for k, v in stg.tree_hashes(out).items() if '/' not in k}
    sums_ok, sums = False, {}
    try:
        for line in open(os.path.join(out, 'SHA256SUMS.txt'), encoding='utf-8'):
            h, n = line.rstrip('\n').split(' ', 1)                         # sha256sum format: "HASH *path" (binary) or "HASH  path"
            sums[n[1:] if n[:1] in ('*', ' ') else n] = h
        allf = stg.tree_hashes(out)
        sums_ok = bool(sums) and all(allf.get(n) == h for n, h in sums.items()) and \
            set(sums) == {k for k in allf if k not in ('SHA256SUMS.txt', 'LABELS.json')}
    except (OSError, ValueError):
        pass
    checks.append({'check': 'SHA256SUMS.txt (the tool\'s own list) = the set files', 'ok': sums_ok, 'detail': '%d entries' % len(sums)})
    bsha = (val.get('trackbuild') or {}).get('build_sha256') or {}
    same_build = all(files.get('%s/%s' % (rel_t, f)) == bsha.get(f) for f in ('static.dat', 'streamed.dat', 'enviro.dat'))
    checks.append({'check': 'packaged AUTHORED files = the validated build (VALIDATION.json build_sha256)', 'ok': same_build,
                   'detail': 'static.dat %s, streamed.dat %s' % (bsha.get('static.dat', '?')[:12], bsha.get('streamed.dat', '?')[:12])})
    don = (rep.get('label') or {}).get('donor') or {}
    don_ok = bool(don) and all(files.get('%s/%s' % (rel_t, f)) == v.get('sha256') for f, v in don.items())
    checks.append({'check': 'DONOR files = unchanged pinned retail copies (BUILD_REPORT labels)', 'ok': don_ok,
                   'detail': '%d donor files from %s, donor pinned %s' % (len(don), rep.get('host'), rep.get('donor_pinned'))})
    if miss:
        r.update(checks=checks, verdict='BUILD FAILED', excerpt=['expected output missing: %s' % ', '.join(miss)])
        return None
    req, rbad = wb_kit.requirements(os.path.join(work, 'mod.toml'))
    checks.append({'check': 'mod.toml requirements readable', 'ok': not rbad, 'detail': '; '.join(rbad) or 'readable'})
    k = wb_kit.kit_identity(cfg['kit'])
    if req and not rbad:
        cp = wb_kit.compat_problems(req, k['platform'], k['services'], plugin=False, tables=k.get('tables'))
        checks.append({'check': 'host requirements vs the kit\'s reference host (platform %s)' % k['platform'], 'ok': not cp,
                       'detail': '; '.join(cp) or 'met'})
    vop = core.op_validate(cfg, [work])
    rc, o = job._run('bmpack validate', vop.argv, vop.cwd)
    r['steps'].append({'step': 'bmpack validate', 'rc': rc})
    rep2 = wb_car._json_out(o) if rc in (0, 1) else None
    r['bmpack'] = {'ok': bool(rep2 and rep2.get('ok')), 'rc': rc,
                   'refusals': [{'service': f.get('service'), 'mod': f.get('mod'), 'why': f.get('why')}
                                for f in (rep2 or {}).get('refusals', [])],
                   'mods': [{'id': m.get('id'), 'version': m.get('version'), 'usable': m.get('usable')}
                            for m in (rep2 or {}).get('mods', [])]}
    checks.append({'check': 'host admission of the package (bmpack validate, kit host readers)', 'ok': r['bmpack']['ok'],
                   'detail': '; '.join('[%s] %s' % (f['service'], f['why']) for f in r['bmpack']['refusals']) or
                   ('ACCEPTED' if r['bmpack']['ok'] else 'exit %s' % rc)})
    ref, exp = {}, None
    if rec.get('reference_list'):
        try:
            exp = json.load(open(core.kit_path(cfg, rec['reference_list']), encoding='utf-8'))['sets'][rec['reference_set']]['files']
        except (OSError, ValueError, KeyError):
            exp = None
        allf = stg.tree_hashes(out)
        ref = {f: allf.get(f) == hs[0] and os.path.getsize(os.path.join(out, *f.split('/'))) == hs[1] if f in allf else False
               for f, hs in sorted((exp or {}).items())}
        checks.append({'check': 'reference mode: = %s' % rec['reference_label'], 'ok': bool(exp) and bool(ref) and all(ref.values())
                       and set(exp) == set(allf), 'detail': '%d / %d files identical' % (sum(ref.values()), len(exp or {}))})
    r['reference_match'], r['reference_expected'] = ref, ({f: v[0] for f, v in exp.items()} if exp else None)
    r['checks'] = checks
    for ch in checks:
        job.log('# check %-55s %s  %s' % (ch['check'], 'ok' if ch['ok'] else 'FAILED', str(ch['detail'])[:300]))
    if job.cancelled:
        r.update(verdict='CANCELLED')
        return None
    if not all(ch['ok'] for ch in checks):
        r.update(verdict='VALIDATION FAILED', excerpt=['%s: %s' % (ch['check'], ch['detail']) for ch in checks if not ch['ok']])
        return None
    labels = {}
    try:
        labels = json.load(open(os.path.join(out, 'LABELS.json'), encoding='utf-8'))
    except (OSError, ValueError):
        pass
    shown = {'src': '<attempt>/src', 'tbuild': '<attempt>/build', 'out': '<attempt>/out', 'desc': tr['desc']}
    r['track_record'] = {
        'kind': 'track', 'mode': r['mode'], 'track': tr, 'inputs': info['inputs'], 'tools': ident, 'game_data': cfg['game_data'],
        'build_steps': [stg.expand(rec[k], cfg, shown) for k in ('track_build', 'track_validate', 'track_package')] +
                       [['<python>', '-B', '<kit>/tools/bmpack/bmpack.py', 'validate', '<package>', '--game-data', '<game data>',
                         '--cc', '<cc>', '--cache', '<bmpack cache>', '--json']],
        'build_copy': 'only the checked inputs, under <attempt>/src (cwd of tb.py); build in <attempt>/build, set in <attempt>/out',
        'set_files': setfiles, 'set_files_kept_in': out, 'labels': labels,
        'validation': checks, 'trackbuild_gates': gates, 'requirements': req, 'donor_dependencies': donor_dependency(tr['track_id']),
        'supported': SUPPORTED, 'deferred': DEFERRED, 'notes': info['notes'],
        'evidence': {'offline': 'this build: %d trackbuild gates + layout / sums / donor / bmpack checks above (structure only)'
                                % len(gates),
                     'runtime': 'none: no game was launched by the Workbench. Kit README (0.1.6 runs, same bytes for the demos): '
                                'load, render, streaming, laps, AI, grid, walls / floor, LOD, PVS, traffic, crash respawn seen in '
                                'game; off-track reset UNTESTED. A new track needs its own in-game check.'},
        'local_only': 'the package holds retail game data (DONOR Gamedata header / events, enviro, audio): local only, never upload',
        'reference_expected': r['reference_expected']}
    return work


def summary_lines(r):
    L = []
    t = (r.get('input_check') or {}).get('track') or {}
    if t:
        L.append('track %s "%s" (%s) mod %s %s; %d units, pvs %s, lod %s, traffic %s' % (
            t.get('track_id'), t.get('track_name'), t.get('track_location'), t.get('mod_id'), t.get('version'), t.get('units') or 0,
            t.get('pvs'), t.get('lod'), t.get('traffic')))
    if r.get('failed_gates'):
        L.append('failed trackbuild gates: %s' % ', '.join(r['failed_gates']))
    if r.get('ok'):
        tr = r.get('track_record_summary') or {}
        L.append('DONOR DEPENDENCY %s (not your content): Gamedata header / event records, enviro.dat, audio from your game data'
                 % DONOR_HOST)
        L.append('LOCAL ONLY: the package holds retail game data - never upload or ship it')
        L.append('trackbuild gates: %s' % tr.get('gates'))
        L.append('deferred (not supported here): own region, point-to-point, special materials / props, own sky / audio, other hosts')
        L.append('offline construction only (no game launched): not a visual or gameplay acceptance')
    return L


# ---------------------------------------------------------------- CLI
def main(argv):
    """wb_track.py new FOLDER --id MOD_ID --track TRACK_ID --name NAME [--location L] [--mod-name T] [--version V]
                    [--author A] [--template testloop|canyon|hill]           (exit 0 created, 3 not; hill: trackbuild 0.3.0)
       wb_track.py example FOLDER        the kit's reference input (gen-testloop + examples\\test_loop_package.toml)
       wb_track.py check PROJECT [DEST]  input checks only (read only; exit 0 ok, 3 refused)
       wb_track.py status|rebind PROJECT kit binding
    Build -> Validate -> Stage: wb_stage.py PROJECT DEST (the same job as the GUI)."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['new', 'example', 'check', 'status', 'rebind'])
    ap.add_argument('folder')
    ap.add_argument('dest', nargs='?')
    for o in ('--id', '--track', '--name', '--location', '--mod-name', '--kit', '--config', '--game-data'):
        ap.add_argument(o)
    ap.add_argument('--version', default='1.0.0')
    ap.add_argument('--author', default='Workbench user')
    ap.add_argument('--template', default='testloop')
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config, kit=a.kit, game_data=a.game_data)
    if a.cmd == 'new':
        r = create_project(cfg, a.folder, a.id, a.track, a.name, a.location, a.mod_name, a.version, a.author, a.template)
        print(json.dumps({k: v for k, v in r.items() if k != 'identity'}, indent=1, default=str))
        return 0 if r['ok'] else 3
    if a.cmd == 'example':
        r = create_example(cfg, a.folder)
        print(json.dumps(r, indent=1, default=str))
        return 0 if r['ok'] else 3
    if a.cmd == 'check':
        rid, why = stg.detect(a.folder)
        if not rid or (stg.RECIPES.get(rid) or {}).get('kind') != 'track':
            print(json.dumps({'problems': [why or 'not a track project (recipe %s)' % rid]}, indent=1))
            return 3
        if a.dest:
            bad, info = start_problems(cfg, rid, a.folder, a.dest)
            info = dict(info or {}, problems=bad)
        else:
            info = input_check(cfg, a.folder, rid)
            info['problems'] = prereqs(cfg, rid, a.folder) + info['problems']
        print(json.dumps(info, indent=1, default=str))
        return 0 if not info['problems'] else 3
    if a.cmd == 'status':
        print(json.dumps(kit_status(cfg, a.folder), indent=1, default=str))
        return 0
    r = rebind_project(cfg, a.folder)
    print(json.dumps(r, indent=1, default=str))
    return 0 if r['ok'] else 3


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
