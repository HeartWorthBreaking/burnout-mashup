"""wb_car - Workbench v0.12: New car project -> Build -> Validate -> Stage (gp\\workbench, 2026-10-29).

A car project is the kit's own carimport input, nothing new:
    car.toml                  carimport's car definition ([car] + [[paint]], the kit tool's schema; tools\\carimport\\README.md)
    <model>.gltf / .bin       the glTF 2.0 body (copied byte for byte from the kit's authored example coupe / wedge)
    texture.png, paint_mask.png   the 512 x 256 texture + paint mask carimport reads
    workbench-car.json        the declared identity (mod id + vehicle id), the template's provenance, the donor dependency
    README.txt
Build = a Workbench-owned recipe (wb_stage.RECIPES 'car-project' / 'carimport-coupe'): fixed argument lists for the kit's
carimport (validate, package) and vehtool (validate), then the kit's bmpack validate - run in an isolated COPY of the approved
inputs only (car.toml, the model, its buffers / images, the paint mask) under <staging>\\.wb_stage\\work\\<time>. Nothing from the
project is ever executed; scripts / executables / build files in a car project are refused.
Before anything runs, input_check() refuses (read only): links / reparse points, a malformed glTF, missing assets, any
reference that leaves the project (car.toml model / paint_mask, glTF buffer / image uri: '..', absolute, drive, UNC, scheme,
backslash or %-escapes other than %20, which carimport would read differently), unknown donors / classes, identity mismatches.
Unsupported glTF features are refused by carimport's own checks (its validate step).
DONOR DEPENDENCY: carimport does not make a whole car. The donor (a retail race car of the same class from YOUR game data)
gives the collision hull, wheels, locators, crush tables, emitters and engine audio (DERIVED copies in the package: local
only, never upload) and, in the game, the physics / handling and the garage photo. The record lists each donor file read.
Deferred (recorded, not implemented): interactive 3D preview, own series / class prefix, registered paints ([bmashup.paints]),
own garage photo, physics_scale / unlock / ai declarations ([bmashup.cars] v2): carimport 0.1.1 packages [bmashup.cars] v1.
"""
import datetime
import hashlib
import json
import os
import posixpath
import re
import shutil
import struct
import tomllib

import wb_core as core
import wb_kit
import wb_project as proj
import wb_stage as stg

SCHEMA = 'bm-workbench-car-project/1'
MARKER = 'workbench-car.json'
TEMPLATES = {'coupe': r'examples\authored\carimport\coupe', 'wedge': r'examples\authored\carimport\wedge'}
CARIMPORT = r'tools\carimport\carimport.py'
VEHTOOL = r'tools\vehtool\vehtool.py'
GAMEDATA_REF = r'tools\carimport\GAMEDATA_SHA256.json'
REGRESSION = r'tools\carimport\tests\REGRESSION_SHA256.json'
CLASSES = ('COMP', 'MSCL', 'CUPE', 'SPRT', 'SUPR', 'HSPC', 'HEVY')          # carimport.CLASSES (retail classes)
CAR_ID_RE = re.compile(r'^(%s)[A-Z0-9]{1,8}$' % '|'.join(CLASSES))
CAR_NAME_RE = re.compile(r"^[A-Za-z0-9 \-'.&]{1,21}$")                      # docs\services\CARS.md names rule (cars2)
PAINT_RE = re.compile(r'^[a-z0-9_.-]{1,40}$')                               # carimport load_config
COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')
VERSION_RE = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+$')
TEXNAME_RE = re.compile(r'^[a-z0-9_]{1,23}$')
CAR_KEYS = ('id', 'donor', 'name', 'model', 'paint_mask', 'texture_name', 'deform', 'mod_id', 'mod_name', 'mod_version',
            'wheel_uv')                                                    # carimport load_config 'known'
MAX_PAINTS = 8                                                             # carimport README s3 ("up to 8")
NON_INPUT_OK = ('.txt', '.md', '.blend', '.blend1', '.json')               # kept in the project, never copied into the build
DEFERRED = [
    'interactive 3D preview (offline: carimport "preview MODEL.bgv OUT.png" by hand; not run by the Workbench)',
    'own series / class prefix ([bmashup.series]): carimport ids use a retail class; the car joins that retail series',
    'registered paints ([bmashup.paints]); paints here = carimport [[paint]] = in-file palettes of the model (max 8, garage shows 6)',
    'own garage photo ([bmashup.cars] photos, fetex): the donor\'s photo is shown',
    '[bmashup.cars] v2 declarations (physics_scale, unlock, ai, model = donor): carimport 0.1.1 packages version 1 (add + names)',
    'more than one car per project; texel liveries per paint (v1 refuses them)',
]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- donors (the kit's own game-data reference table)
def donors(cfg):
    """{DONOR_ID: {class, files {bgv|hwd|lwd: {rel, sha256, size}}}} from the kit's carimport GAMEDATA_SHA256.json (read only):
    retail race cars of the carimport classes with model + engine audio"""
    p = os.path.join(cfg.get('kit') or '', GAMEDATA_REF)
    try:
        ref = json.load(open(p, encoding='utf-8'))['files']
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for k, v in ref.items():
        parts = k.split('/')
        if len(parts) != 3 or parts[0] != 'pveh' or '.' not in parts[2]:
            continue
        rest, ext = parts[2].rsplit('.', 1)
        cls = parts[1].upper()
        if cls not in CLASSES or ext not in ('bgv', 'hwd', 'lwd'):
            continue
        d = out.setdefault(cls + rest.upper(), {'class': cls, 'files': {}})
        d['files'][ext] = {'rel': 'pveh/%s/%s.%s' % (cls, rest.upper(), ext), 'sha256': v['sha256'], 'size': v['size']}
    return {k: v for k, v in sorted(out.items()) if set(v['files']) == {'bgv', 'hwd', 'lwd'}}


def donor_dependency(cfg, donor, car_id):
    """the donor dependency of one car, labelled (what is read, what the package holds, what the game takes from the donor)"""
    d = donors(cfg).get(donor) or {'files': {}}
    cls, rest = car_id[:4], car_id[4:]
    return {'donor': donor, 'label': 'DONOR DEPENDENCY: not authored, not project content - YOUR retail game data',
            'read_at_build': [dict(f, verified='sha256 + size checked by carimport against the kit\'s GAMEDATA_SHA256.json')
                              for _, f in sorted(d['files'].items())],
            'derived_in_package': {
                'files/pveh/%s/%s.bgv' % (cls, rest): 'AUTHORED geometry + texture; DERIVED donor structural blocks (collision '
                                                      'hull, wheel / locator / crush tables, emitters, engine-sound descriptors)',
                'files/pveh/%s/%s.hwd' % (cls, rest): 'DERIVED: byte copy of the donor engine audio',
                'files/pveh/%s/%s.lwd' % (cls, rest): 'DERIVED: byte copy of the donor engine audio'},
            'in_game_from_donor': ['physics / handling ([bmashup.cars] add "%s = %s")' % (car_id, donor),
                                   'garage photo (no own photo declared)', 'the donor must exist in the player\'s game data'],
            'local_only': True, 'note': 'the built package contains DERIVED retail data: local only, never upload or ship it'}


# ---------------------------------------------------------------- identity checks
def check_car_id(v, cfg=None):
    if not isinstance(v, str) or not CAR_ID_RE.match(v):
        return ('vehicle id %r: a retail class (%s) + 1..8 of A-Z 0-9, upper case (e.g. COMPMY1); own series prefixes are '
                'deferred (carimport uses the retail classes)' % (v, ' '.join(CLASSES)))
    if cfg is not None and v in donors(cfg):
        return 'vehicle id %s is a retail car (the host refuses a duplicate vehicle id): choose your own' % v
    return None


def check_donor(cfg, donor, car_id):
    ds = donors(cfg)
    if not ds:
        return 'no donor list: the kit\'s %s is missing or unreadable (is the kit set?)' % GAMEDATA_REF
    if not isinstance(donor, str) or donor not in ds:
        cls = (car_id or '')[:4]
        return ('donor %r is not a retail race car of the supported release (same class %s: %s)'
                % (donor, cls or '?', ', '.join(k for k in ds if k.startswith(cls))[:300] if cls else ', '.join(ds)[:300]))
    if isinstance(car_id, str) and donor[:4] != car_id[:4]:
        return 'donor %s is class %s, the car %s is class %s: carimport needs a donor of the same class' % (
            donor, donor[:4], car_id, car_id[:4])
    return None


def check_car_name(v):
    if not isinstance(v, str) or not CAR_NAME_RE.match(v) or v != v.strip():
        return ('car name %r: 1..21 characters A-Z a-z 0-9 space - \' . & (the garage name rule, docs\\services\\CARS.md), '
                'no leading / trailing spaces' % (v,))
    return None


def check_paints(paints):
    out = []
    if not paints:
        return ['at least one paint (name + #RRGGBB)']
    if len(paints) > MAX_PAINTS:
        out.append('%d paints: carimport takes up to %d (the garage shows 6)' % (len(paints), MAX_PAINTS))
    for n, c in paints:
        if not isinstance(n, str) or not PAINT_RE.match(n):
            out.append('paint name %r: [a-z0-9_.-]{1,40}' % (n,))
        if not isinstance(c, str) or not COLOR_RE.match(c):
            out.append('paint %r colour %r: #RRGGBB' % (n, c))
    if len({n for n, _ in paints}) != len(paints):
        out.append('duplicate paint names')
    return out


def check_identity(cfg, mod_id, car_id, donor, name, mod_name, version, paints, deform):
    bad = [proj.check_mod_id(mod_id), check_car_id(car_id, cfg), check_donor(cfg, donor, car_id), check_car_name(name),
           proj.check_name(mod_name), None if isinstance(version, str) and VERSION_RE.match(version) else
           'version %r: MAJOR.MINOR.PATCH (e.g. 1.0.0)' % (version,),
           None if deform in ('transfer', 'rigid') else 'deform %r: transfer | rigid (carimport)' % (deform,)]
    return [b for b in bad if b] + check_paints(paints)


# ---------------------------------------------------------------- templates (kit files copied; car.toml from validated values)
def template_files(cfg, template):
    d = os.path.join(cfg.get('kit') or '', TEMPLATES.get(template, '?'))
    if not os.path.isdir(d):
        return None, None
    names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)))
    return d, names


def template_car(cfg, template):
    d, _ = template_files(cfg, template)
    t = tomllib.loads(open(os.path.join(d, 'car.toml'), encoding='utf-8').read())
    return t['car'], [(p['name'], p['color']) for p in t.get('paint', [])]


def car_toml(template, car, paints):
    q = lambda s: '"%s"' % s                                                 # noqa: E731 - validated values only (no " or \)
    cls, rest = car['id'][:4], car['id'][4:]
    L = ['# carimport car definition - made by the Burnout Mashup Workbench (New car project) from the kit example "%s".'
         % template,
         '# AUTHORED (yours): the glTF model %s with its buffer, texture and paint mask; the names and paint colours below.'
         % car['model'],
         '# DONOR DEPENDENCY (not your content, not in this project): donor = %s, a retail race car from YOUR game data.'
         % car['donor'],
         '#   Build: carimport reads pveh\\%s\\%s.bgv / .hwd / .lwd (hash-checked); the package holds DERIVED copies of its'
         % (car['donor'][:4], car['donor'][4:]),
         '#   collision hull, wheels, locators, crush tables, emitters and engine audio -> the package is LOCAL ONLY.',
         '#   Game: physics / handling and the garage photo are the donor\'s. New car: %s (pveh\\%s\\%s.*).' % (car['id'], cls, rest),
         '# Keep id and mod_id equal to workbench-car.json. Paths are relative to this folder: no "..", drive or absolute paths.',
         '[car]']
    for k in ('id', 'donor', 'name', 'model', 'paint_mask', 'texture_name', 'deform', 'mod_id', 'mod_name', 'mod_version'):
        L.append('%s = %s' % (k, q(car[k])))
    for n, c in paints:
        L += ['', '[[paint]]', 'name = %s' % q(n), 'color = %s' % q(c.upper())]
    return '\n'.join(L) + '\n'


def readme(car):
    return ('%(name)s (%(id)s, mod %(mod_id)s)\n\nA car project made by the Burnout Mashup Workbench (New car project) for the kit\'s '
            'carimport.\n\n  car.toml            carimport\'s car definition (edit the name, paints, donor, deform; keep id / mod_id)\n'
            '  %(model)s          the glTF 2.0 body (metres, +Y up, +Z front, +X left; materials paint.* / plain.* / glass.*)\n'
            '  texture.png, paint_mask.png   512 x 256 texture and paint mask\n'
            '  workbench-car.json  the declared identity, the template\'s provenance and the donor dependency\n\n'
            'DONOR DEPENDENCY: %(donor)s (a retail car from YOUR game data) gives the collision hull, wheels, emitters, engine\n'
            'audio, physics and garage photo. The built package contains DERIVED retail data: local only, never upload it.\n\n'
            'Build / validate / stage: Workbench -> Build / stage tab -> this folder -> a staging folder. The Workbench runs the kit\'s\n'
            'carimport / vehtool / bmpack with its own fixed arguments on a copy of the inputs; nothing in this folder is run.\n'
            'Model and texture paths (car.toml, glTF uri) must stay inside this folder.\n') % car


def folder_problems(cfg, folder):
    return proj.folder_problems(cfg, folder)


def create_project(cfg, folder, mod_id, car_id, donor, name, mod_name=None, version='1.0.0', template='coupe',
                   paints=None, deform=None):
    """-> {'ok', 'verdict', 'project', 'problems', 'files', 'identity'}; writes nothing unless every check passed; one rename"""
    res = {'kind': 'new-car-project', 'ok': False, 'project': os.path.abspath(folder) if folder and os.path.isabs(folder) else folder,
           'mod_id': mod_id, 'car_id': car_id, 'verdict': 'NOT CREATED'}
    bad = []
    if template not in TEMPLATES:
        bad.append('template %r: %s' % (template, ' | '.join(TEMPLATES)))
    tdir, tnames = template_files(cfg, template) if not bad else (None, None)
    if not bad and (not tdir or 'car.toml' not in tnames):
        bad.append('kit template missing: %s (is the kit set to the mod kit 0.6.0 folder?)' % TEMPLATES[template])
    tcar, tpaints = template_car(cfg, template) if not bad else ({}, [])
    paints = [tuple(p) for p in paints] if paints else tpaints
    deform = deform or tcar.get('deform', 'transfer')
    mod_name = mod_name if mod_name is not None else name
    bad += check_identity(cfg, mod_id, car_id, donor, name, mod_name, version, paints, deform)
    if not os.path.isfile(os.path.join(cfg.get('kit') or '', CARIMPORT)):
        bad.append('kit file missing: %s' % CARIMPORT)
    bad += folder_problems(cfg, folder)
    res['problems'] = bad
    if bad:
        return res
    folder = os.path.abspath(folder)
    car = {'id': car_id, 'donor': donor, 'name': name, 'model': tcar['model'], 'paint_mask': tcar['paint_mask'],
           'texture_name': car_id.lower(), 'deform': deform, 'mod_id': mod_id, 'mod_name': mod_name, 'mod_version': version}
    texts = {'car.toml': car_toml(template, car, paints), 'README.txt': readme(car)}
    copies = [n for n in tnames if n != 'car.toml']
    ident = {'schema': SCHEMA, 'mod_id': mod_id, 'car_id': car_id, 'folder': mod_id,
             'created': datetime.datetime.now().isoformat(timespec='seconds'),
             'template': {'kit': cfg['kit'], 'example': TEMPLATES[template], 'name': template,
                          'files': {n: wb_kit.sha256_file(os.path.join(tdir, n)) for n in tnames},
                          'generator': 'Workbench wb_car.py (v0.12)'},
             'kit': wb_kit.stamp(wb_kit.kit_identity(cfg['kit'])), 'kit_history': [],
             'created_files': dict({n: sha256_bytes(t.encode('utf-8')) for n, t in texts.items()},
                                   **{n: wb_kit.sha256_file(os.path.join(tdir, n)) for n in copies}),
             'donor_dependency': donor_dependency(cfg, donor, car_id),
             'build': 'Workbench-owned recipe car-project (kit carimport validate + package, vehtool validate, bmpack validate)',
             'deferred': DEFERRED}
    tmp = os.path.join(os.path.dirname(folder), '.%s.wb_new_%s' % (os.path.basename(folder),
                                                                    datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    os.makedirs(tmp)
    try:
        for n, t in texts.items():
            with open(os.path.join(tmp, n), 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(t)
        for n in copies:
            shutil.copyfile(os.path.join(tdir, n), os.path.join(tmp, n))
        with open(os.path.join(tmp, MARKER), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(ident, fh, indent=1)
        if os.path.isdir(folder):
            if os.listdir(folder):
                raise FileExistsError(folder)
            os.rmdir(folder)
        os.rename(tmp, folder)
    except Exception as e:                                                  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)                              # our own half-written temp folder only
        res.update(problems=['could not create the project: %r' % e])
        return res
    res.update(ok=True, verdict='CREATED', project=folder, files=sorted(list(texts) + copies + [MARKER]), identity=ident,
               car=car, paints=paints)
    return res


# ---------------------------------------------------------------- reading a project / kit binding
def is_car_project(project):
    return bool(project) and os.path.isfile(os.path.join(project, MARKER))


def _marker(project):
    try:
        d = json.load(open(os.path.join(project, MARKER), encoding='utf-8'))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def read_project(project):
    """-> (identity {mod_id, car_id, folder}, problems) from workbench-car.json (re-checked)"""
    d = _marker(project)
    if not d or d.get('schema') != SCHEMA:
        return None, ['%s unreadable or schema is not %s' % (MARKER, SCHEMA)]
    bad = [x for x in (proj.check_mod_id(d.get('mod_id') if isinstance(d.get('mod_id'), str) else ''),
                       check_car_id(d.get('car_id'))) if x]
    if d.get('folder', d.get('mod_id')) != d.get('mod_id'):
        bad.append('%s: folder must equal the mod id' % MARKER)
    if bad:
        return None, ['%s: %s' % (MARKER, b) for b in bad]
    return {'mod_id': d['mod_id'], 'car_id': d['car_id'], 'folder': d['mod_id']}, []


def kit_status(cfg, project):
    d = _marker(project) or {}
    cur = wb_kit.kit_identity(cfg.get('kit'))
    rec = d.get('kit') if isinstance(d.get('kit'), dict) else None
    if not rec:
        return {'state': 'unbound', 'text': 'the car project has no kit binding', 'recorded': None, 'current': wb_kit.stamp(cur)}
    if wb_kit.same(rec, cur):
        return {'state': 'same', 'text': 'bound to the current kit %s' % rec.get('id'), 'recorded': rec, 'current': wb_kit.stamp(cur)}
    return {'state': 'different', 'recorded': rec, 'current': wb_kit.stamp(cur), 'diff': wb_kit.diff(rec, cur),
            'text': 'bound to kit %s, the current kit is %s: not migrated. Rebind explicitly to build with the current kit '
                    '(earlier staged outputs are kept), or switch the kit back' % (rec.get('id'), (cur or {}).get('id'))}


def rebind_project(cfg, project):
    """explicit user action: bind the car project to the current kit (only workbench-car.json changes, atomic replace)"""
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
def rel_problem(v, what, uri=False):
    """a reference that must name a plain file inside the project -> problem text or None"""
    if not isinstance(v, str) or not v:
        return '%s must be a file name inside the project (got %r)' % (what, v)
    if v != v.strip() or any(ord(c) < 32 for c in v):
        return '%s %r: leading / trailing spaces or control characters' % (what, v)
    if v.startswith(('/', '\\')) or os.path.isabs(v) or ':' in v:
        return ('%s %r leaves the approved project inputs (absolute path, drive, UNC or URI scheme): only paths relative to '
                'the project are used' % (what, v))
    if uri and '\\' in v:
        return '%s %r: a glTF uri uses "/" (a backslash is not a portable glTF reference)' % (what, v)
    if uri and ('?' in v or '#' in v or re.search(r'%(?!20)', v)):
        return ('%s %r: query / fragment / %%-escapes other than %%20 are refused (carimport decodes only %%20, so the file it '
                'opens would differ from what other tools read)' % (what, v))
    parts = re.split(r'[\\/]', v)
    if '..' in parts:
        return '%s %r leaves the approved project inputs ("..")' % (what, v)
    if any(p in ('', '.') for p in parts):
        return '%s %r: empty or "." path segment' % (what, v)
    return None


def _resolve(project, files_ci, rel, what):
    """-> (project-relative path as listed, problem)"""
    rel = rel.replace('\\', '/')
    hit = files_ci.get(rel.lower())
    if hit:
        return hit, None
    p = os.path.join(project, *rel.split('/'))
    if os.path.lexists(p):
        return None, '%s %s is not a plain file of the project (link / reparse point / folder): refused, never followed' % (what, rel)
    return None, 'missing asset: %s %s not found in the project' % (what, rel)


def gltf_json(path):
    """the glTF JSON of a .gltf / .glb file -> (dict, problem). Structure only; carimport's own checks do the rest."""
    try:
        raw = open(path, 'rb').read()
    except OSError as e:
        return None, 'unreadable: %s' % e
    if path.lower().endswith('.glb'):
        if len(raw) < 20 or raw[:4] != b'glTF':
            return None, 'malformed glTF: %s is not a GLB container (no "glTF" header)' % os.path.basename(path)
        ver, length = struct.unpack_from('<II', raw, 4)
        clen, ctype = struct.unpack_from('<II', raw, 12)
        if ver != 2 or length != len(raw) or ctype != 0x4E4F534A or 20 + clen > len(raw):
            return None, 'malformed glTF: GLB header / JSON chunk (version %d, length %d of %d bytes)' % (ver, length, len(raw))
        raw = raw[20:20 + clen]
    try:
        js = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as e:
        return None, 'malformed glTF: %s is not valid JSON (%s)' % (os.path.basename(path), e)
    if not isinstance(js, dict) or not isinstance(js.get('asset'), dict):
        return None, 'malformed glTF: %s has no "asset" object (not a glTF 2.0 file)' % os.path.basename(path)
    for k in ('buffers', 'images'):
        if k in js and not (isinstance(js[k], list) and all(isinstance(x, dict) for x in js[k])):
            return None, 'malformed glTF: "%s" is not a list of objects' % k
    return js, None


def input_check(cfg, project, rid, ident=None):
    """what the build would read and why it would refuse -> info {problems, checks, notes, inputs {rel: sha256}, car}.
    READ ONLY: nothing is executed or written."""
    info = {'kind': 'car-input-check', 'project': os.path.abspath(project) if project else project, 'recipe': rid,
            'problems': [], 'checks': [], 'notes': [], 'inputs': {}, 'car': None}
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
            bad.append('%s: a script / executable / build file in a car project is refused (the Workbench never runs project '
                       'files; it runs only the kit\'s carimport, vehtool and bmpack): remove it' % rel)
    if 'car.toml' not in files:
        bad.append('no car.toml at the top of %s: not a car project' % project)
        return info
    try:
        t = tomllib.loads(open(os.path.join(project, 'car.toml'), encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        c('car.toml parses (TOML)', False, str(e))
        return info
    c('car.toml parses (TOML)', True, 'ok')
    car = t.get('car') if isinstance(t.get('car'), dict) else None
    if not c('car.toml [car] table', car is not None, 'present' if car is not None else 'missing'):
        return info
    paints = [p for p in t.get('paint', []) if isinstance(p, dict)] if isinstance(t.get('paint', []), list) else []
    cid, donor = str(car.get('id', '')).upper(), str(car.get('donor', '')).upper()
    info['car'] = {'id': cid, 'donor': donor, 'class': cid[:4], 'name': car.get('name'), 'mod_id': car.get('mod_id'),
                   'mod_name': car.get('mod_name'), 'mod_version': car.get('mod_version', '1.0.0'),
                   'deform': car.get('deform', 'transfer'), 'texture_name': car.get('texture_name'),
                   'model': car.get('model'), 'paint_mask': car.get('paint_mask'),
                   'paints': [{'name': p.get('name'), 'color': p.get('color')} for p in paints]}
    inputs = ['car.toml']
    m = car.get('model')
    why = rel_problem(m, 'car.model')
    model_rel = None
    if c('car.model inside the project', not why, why or m):
        if not str(m).lower().endswith(('.gltf', '.glb')):
            c('car.model is glTF 2.0 (.gltf / .glb)', False, 'unsupported model format %r (carimport reads .gltf / .glb)' % m)
        else:
            model_rel, why = _resolve(project, files_ci, m, 'car.model')
            if c('car.model file present', model_rel, why or model_rel):
                inputs.append(model_rel)
    pm = car.get('paint_mask')
    if pm is not None:
        why = rel_problem(pm, 'car.paint_mask')
        if c('car.paint_mask inside the project', not why, why or pm):
            if not str(pm).lower().endswith('.png'):
                c('car.paint_mask is PNG', False, 'unsupported paint mask format %r (carimport reads PNG)' % pm)
            else:
                r_, why = _resolve(project, files_ci, pm, 'car.paint_mask')
                if c('car.paint_mask file present', r_, why or r_):
                    inputs.append(r_)
    if model_rel:
        js, why = gltf_json(os.path.join(project, *model_rel.split('/')))
        if c('glTF readable (structure)', js is not None, why or 'ok'):
            base = posixpath.dirname(model_rel)
            refs = [('buffer', i, b.get('uri')) for i, b in enumerate(js.get('buffers', []))] + \
                   [('image', i, im.get('uri')) for i, im in enumerate(js.get('images', []))]
            okrefs = []
            for kind, i, uri in refs:
                if uri is None:
                    continue                                                # GLB BIN chunk / bufferView image
                if not isinstance(uri, str):
                    c('glTF %s %d uri' % (kind, i), False, 'malformed glTF: uri is not a string')
                    continue
                if uri.startswith('data:'):
                    okrefs.append('%s %d: inline data' % (kind, i))
                    continue
                why = rel_problem(uri, 'glTF %s %d uri' % (kind, i), uri=True)
                if not c('glTF %s %d uri inside the project' % (kind, i), not why, why or uri):
                    continue
                target = posixpath.normpath(posixpath.join(base, uri.replace('%20', ' ')))
                if target.startswith('../') or target == '..':
                    c('glTF %s %d uri inside the project' % (kind, i), False, '%r leaves the project' % uri)
                    continue
                r_, why = _resolve(project, files_ci, target, 'glTF %s %d' % (kind, i))
                if c('glTF %s %d file present' % (kind, i), r_, why or r_):
                    inputs.append(r_)
                    okrefs.append('%s %d: %s' % (kind, i, r_))
            info['gltf_refs'] = okrefs
    # identity
    rec = stg.RECIPES.get(rid) or {}
    if rec.get('project'):
        ident = ident or read_project(project)[0]
        if ident:
            c('car.toml mod_id = workbench-car.json', car.get('mod_id') == ident['mod_id'], '%r (declared %r)'
              % (car.get('mod_id'), ident['mod_id']))
            c('car.toml id = workbench-car.json', cid == ident['car_id'] and car.get('id') == cid,
              '%r (declared %r)' % (car.get('id'), ident['car_id']))
            why = proj.check_mod_id(car.get('mod_id') or '')
            c('mod id (own namespace)', not why, why or car.get('mod_id'))
    elif rec.get('mod_id'):
        c('car.toml mod_id = the kit example\'s', car.get('mod_id') == rec['mod_id'], car.get('mod_id'))
    why = check_car_id(cid, cfg)
    c('vehicle id', not why, why or cid)
    why = check_donor(cfg, donor, cid)
    c('donor (retail race car of the same class, kit reference table)', not why, why or donor)
    for k in car:
        if k not in CAR_KEYS:
            info['notes'].append('car.toml [car] key %r is not a carimport key: carimport validate will refuse it' % k)
    for rel in sorted(files):
        if rel not in inputs and rel != MARKER:
            info['notes'].append('not an input (stays in the project, not copied into the build): %s' % rel)
    if not bad:
        info['inputs'] = {rel: wb_kit.sha256_file(os.path.join(project, *rel.split('/'))) for rel in dict.fromkeys(inputs)}
    return info


def prereqs(cfg, rid, project):
    """what keeps a car recipe from starting (the job and the GUI make the same checks)"""
    bad = []
    k = cfg.get('kit') or ''
    if not k:
        return ['kit: ' + core.check_value('kit', '')]
    for f in (CARIMPORT, VEHTOOL, GAMEDATA_REF):
        if not os.path.isfile(os.path.join(k, f)):
            bad.append('kit file missing: %s (is %s the mod kit 0.6.0 folder?)' % (f, k))
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
    """every refusal before an attempt folder exists -> (problems, input info)"""
    rec = stg.recipe(rid, project)
    bad = stg.check_destination(cfg, project, dest) + prereqs(cfg, rid, project)
    info = None
    if not bad:
        bad += stg.collision_problems(dest, rec, project)
        info = input_check(cfg, project, rid)
        bad += info['problems']
    return bad, info


# ---------------------------------------------------------------- the build (inside wb_stage.StageJob)
def _json_out(out):
    i = out.find('{')
    if i < 0:
        return None
    try:
        return json.loads(out[i:])
    except ValueError:
        return None


def stage(job, r, rec):
    """StageJob._stage for kind 'car': checks -> isolated copy of the inputs -> kit tools (fixed argv) -> checks -> commit"""
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


def build(job, r, rec, attempt, info):
    cfg, op = job.cfg, job.op
    car = info['car']
    src, out = os.path.join(attempt, 'src'), os.path.join(attempt, 'out')
    for rel in info['inputs']:                                              # the approved inputs only (plain files)
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
    for name, key in (('carimport', 'carimport'), ('vehtool', 'vehtool')):
        rc, o = job._run('identify %s' % name, [t['python'], '-B', t[key], 'version'], attempt)
        if job.cancelled:
            r.update(verdict='CANCELLED')
            return None
        tree = os.path.dirname(t[key])
        ident[name] = {'path': t[key], 'sha256': wb_kit.sha256_file(t[key]), 'version': _json_out(o), 'rc': rc,
                       'tree_sha256': sha256_bytes(json.dumps(stg.tree_hashes(tree), sort_keys=True).encode())}
        if rc != 0:
            r.update(verdict='BUILD FAILED', excerpt=['%s version: exit %s (cannot run the kit tool)' % (name, rc)] +
                     [l for l in o.splitlines() if l.strip()][-6:])
            return None
    ident['python']['version'] = ((ident['carimport']['version'] or {}).get('python'))
    r['tools'] = ident
    r['mode'] = 'project' if rec.get('project') else stg.source_mode(cfg, op.rid, op.project)[0]
    paths = {'out': out}
    checks = []
    for name, argv, cwd in (('carimport validate', rec['car_validate'], src), ('carimport package', rec['car_package'], src)):
        rc, o = job._run(name, stg.expand(argv, cfg, paths), cwd)
        r['steps'].append({'step': name, 'rc': rc})
        js = _json_out(o)
        if job.cancelled:
            r.update(verdict='CANCELLED')
            return None
        if rc != 0:
            why = (js or {}).get('refused') or [(js or {}).get('cannot_run')] if js else None
            why = [w for w in (why or []) if w] or [l for l in o.splitlines() if l.strip()][-12:]
            checks.append({'check': '%s (the kit tool\'s own checks)' % name, 'ok': False, 'detail': '; '.join(why)[:2000]})
            r['checks'] = checks
            r.update(verdict='VALIDATION FAILED' if rc == 1 else 'BUILD FAILED',
                     excerpt=['%s exit %s%s:' % (name, rc, ' (refused)' if rc == 1 else ' (cannot run)' if rc == 3 else '')] +
                     ['  ' + w for w in why])
            return None
        if name == 'carimport validate':
            checks.append({'check': 'carimport validate (glTF, texture, config, donor, budget)', 'ok': bool(js and js.get('ok')),
                           'detail': 'ok, bgv sha256 %s' % (js or {}).get('bgv_sha256', '?')[:12]})
            r['carimport_validate'] = {k: (js or {}).get(k) for k in ('car', 'donor', 'notes', 'texture', 'bgv_sha256')}
        else:
            r['carimport_package'] = js
    work = os.path.join(out, car['mod_id'].split('.')[-1])                 # carimport package writes <set>\<last id part>
    r['work'] = work
    cls, rest = car['id'][:4], car['id'][4:]
    want = ['mod.toml', 'carimport.json', 'LABELS.txt', 'SHA256SUMS.txt'] + ['files/pveh/%s/%s.%s' % (cls, rest, e)
                                                                              for e in ('bgv', 'hwd', 'lwd')]
    files = stg.tree_hashes(work) if os.path.isdir(work) else {}
    miss = [w for w in want if w not in files]
    extra = sorted(set(files) - set(want))
    checks.append({'check': 'package = carimport\'s documented layout', 'ok': not miss and not extra,
                   'detail': 'missing %s, unexpected %s' % (miss, extra) if miss or extra else '%d files' % len(files)})
    sums_ok, sums = False, {}
    try:
        for line in open(os.path.join(work, 'SHA256SUMS.txt'), encoding='utf-8'):
            h, n = line.rstrip('\n').split('  ', 1)
            sums[n] = h
        sums_ok = sums == {k: v for k, v in files.items() if k != 'SHA256SUMS.txt'}
    except (OSError, ValueError):
        pass
    checks.append({'check': 'SHA256SUMS.txt (the tool\'s own list) = the files', 'ok': sums_ok, 'detail': '%d entries' % len(sums)})
    dep = donor_dependency(cfg, car['donor'], car['id'])
    ds = {f['rel'].rsplit('.', 1)[1]: f['sha256'] for f in dep['read_at_build']}
    aud = all(files.get('files/pveh/%s/%s.%s' % (cls, rest, e)) == ds.get(e) for e in ('hwd', 'lwd'))
    checks.append({'check': 'engine audio = the donor\'s bytes (DERIVED copy, reference table)', 'ok': aud,
                   'detail': 'hwd / lwd = %s %s' % (car['donor'], 'reference sha256' if aud else 'DIFFERENT')})
    if miss:
        r.update(checks=checks, verdict='BUILD FAILED', excerpt=['expected output missing: %s' % ', '.join(miss)])
        return None
    vargv = stg.expand(rec['car_check'], cfg, {'pkg': work})
    rc, o = job._run('vehtool validate', vargv, attempt)
    r['steps'].append({'step': 'vehtool validate', 'rc': rc})
    if job.cancelled:
        r.update(verdict='CANCELLED')
        return None
    checks.append({'check': 'vehtool validate (cars / series / paints admission mirror)', 'ok': rc == 0,
                   'detail': ' | '.join(l for l in o.splitlines() if l.strip())[:600]})
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
    rep = _json_out(o) if rc in (0, 1) else None
    r['bmpack'] = {'ok': bool(rep and rep.get('ok')), 'rc': rc,
                   'refusals': [{'service': f.get('service'), 'mod': f.get('mod'), 'why': f.get('why')}
                                for f in (rep or {}).get('refusals', [])],
                   'mods': [{'id': m.get('id'), 'version': m.get('version'), 'usable': m.get('usable')}
                            for m in (rep or {}).get('mods', [])]}
    checks.append({'check': 'host admission of the package (bmpack validate, kit host readers)', 'ok': r['bmpack']['ok'],
                   'detail': '; '.join('[%s] %s' % (f['service'], f['why']) for f in r['bmpack']['refusals']) or
                   ('ACCEPTED' if r['bmpack']['ok'] else 'exit %s' % rc)})
    ref, exp = {}, None
    if rec.get('reference_list'):
        try:
            exp = json.load(open(os.path.join(cfg['kit'], rec['reference_list']), encoding='utf-8'))['packages'][rec['folder']]
        except (OSError, ValueError, KeyError):
            exp = None
        ref = {f: files.get(f) == h for f, h in sorted((exp or {}).items())}
        if r['mode'] == 'reference':
            checks.append({'check': 'reference mode: = %s' % rec['reference_label'], 'ok': bool(exp) and ref and all(ref.values())
                           and set(exp) == set(files), 'detail': ref or 'reference list unreadable'})
    r['reference_match'], r['reference_expected'] = ref, exp
    r['checks'] = checks
    for ch in checks:
        job.log('# check %-55s %s  %s' % (ch['check'], 'ok' if ch['ok'] else 'FAILED', str(ch['detail'])[:300]))
    if job.cancelled:
        r.update(verdict='CANCELLED')
        return None
    if not all(ch['ok'] for ch in checks):
        r.update(verdict='VALIDATION FAILED', excerpt=['%s: %s' % (ch['check'], ch['detail']) for ch in checks if not ch['ok']])
        return None
    shown = {'out': '<attempt>/out', 'pkg': '<attempt>/out/' + work.rsplit(os.sep, 1)[-1]}
    labels = {}
    try:
        labels = json.load(open(os.path.join(work, 'carimport.json'), encoding='utf-8')).get('labels') or {}
    except (OSError, ValueError):
        pass
    r['car_record'] = {
        'kind': 'car', 'mode': r['mode'], 'car': car, 'inputs': info['inputs'], 'input_refs': info.get('gltf_refs'),
        'tools': ident, 'game_data': cfg['game_data'],
        'build_steps': [stg.expand(a, cfg, shown) for a in (rec['car_validate'], rec['car_package'], rec['car_check'])] +
                       [['<python>', '-B', '<kit>/tools/bmpack/bmpack.py', 'validate', '<package>', '--game-data', '<game data>',
                         '--cc', '<cc>', '--cache', '<bmpack cache>', '--json']],
        'build_copy': 'only the checked inputs, under <attempt>/src (cwd of carimport); package written to <attempt>/out',
        'validation': checks, 'requirements': req, 'donor_dependencies': dep, 'labels': labels,
        'local_only': 'the package holds DERIVED retail data (donor structural blocks + engine audio): local only, never upload',
        'deferred': DEFERRED, 'notes': info['notes'] + (r.get('carimport_validate') or {}).get('notes', []),
        'reference_expected': exp,
        'not_verified': 'offline construction only: no game was launched; not a visual or gameplay acceptance'}
    return work


def summary_lines(r):
    """car-specific lines for wb_stage.summarize"""
    L = []
    c = (r.get('input_check') or {}).get('car') or {}
    if c:
        L.append('car %s "%s" (class %s) on donor %s; mod %s %s; paints %s; deform %s' % (
            c.get('id'), c.get('name'), c.get('class'), c.get('donor'), c.get('mod_id'), c.get('mod_version'),
            ', '.join('%s %s' % (p['name'], p['color']) for p in c.get('paints') or []), c.get('deform')))
    if r.get('ok'):
        cr = r.get('car_record_summary') or {}
        L.append('DONOR DEPENDENCY %s (not your content): read from your game data %s; DERIVED in the package: structural '
                 'blocks + engine audio; in game: physics / handling, garage photo' % (c.get('donor'), ', '.join(cr.get('donor_files') or [])))
        L.append('LOCAL ONLY: the package holds DERIVED retail data - never upload or ship it')
        L.append('requirements: %s' % cr.get('requirements'))
        L.append('deferred (not supported here): interactive 3D preview, own series, registered paints, own photo, cars v2 options')
        L.append('offline construction only (no game launched): not a visual or gameplay acceptance')
    return L


# ---------------------------------------------------------------- CLI
def main(argv):
    """wb_car.py new FOLDER --id MOD_ID --car CAR_ID --donor DONOR --name NAME [--mod-name T] [--version V]
                  [--template coupe|wedge] [--deform transfer|rigid] [--paint NAME=#RRGGBB ...]   (exit 0 created, 3 not)
       wb_car.py check PROJECT [DEST]      input checks only (read only; exit 0 ok, 3 refused)
       wb_car.py donors [--class COMP]     the retail donors of the kit's reference table
       wb_car.py status|rebind PROJECT     kit binding
    Build -> Validate -> Stage: wb_stage.py PROJECT DEST (the same job as the GUI)."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['new', 'check', 'donors', 'status', 'rebind'])
    ap.add_argument('folder', nargs='?')
    ap.add_argument('dest', nargs='?')
    for o in ('--id', '--car', '--donor', '--name', '--mod-name', '--kit', '--config', '--game-data', '--class'):
        ap.add_argument(o)
    ap.add_argument('--version', default='1.0.0')
    ap.add_argument('--template', default='coupe')
    ap.add_argument('--deform')
    ap.add_argument('--paint', action='append', default=[])
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config, kit=a.kit, game_data=a.game_data)
    if a.cmd == 'donors':
        ds = donors(cfg)
        print(json.dumps({k: v['class'] for k, v in ds.items() if not a.__dict__['class'] or v['class'] == a.__dict__['class'].upper()},
                         indent=1))
        return 0 if ds else 3
    if a.cmd == 'new':
        paints = []
        for p in a.paint:
            n, _, col = p.partition('=')
            paints.append((n, col))
        r = create_project(cfg, a.folder, a.id, a.car, a.donor, a.name, a.mod_name, a.version, a.template, paints or None,
                           a.deform)
        print(json.dumps({k: v for k, v in r.items() if k != 'identity'}, indent=1, default=str))
        return 0 if r['ok'] else 3
    if a.cmd == 'check':
        rid, why = stg.detect(a.folder)
        if not rid or (stg.RECIPES.get(rid) or {}).get('kind') != 'car':
            print(json.dumps({'problems': [why or 'not a car project (recipe %s)' % rid]}, indent=1))
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
