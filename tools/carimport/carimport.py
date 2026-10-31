"""carimport - author / import NEW car geometry for Burnout 3 (Takedawn + BurnoutMashup host, [bmashup.cars]).

  py -3 -B carimport.py demo {wedge|coupe} OUT_DIR          write an ORIGINAL procedural test car (glTF + texture + mask + car.toml)
  py -3 -B carimport.py inspect FILE                        summary of a .gltf / .glb / .bgv / .btv
  py -3 -B carimport.py validate CAR.toml                   strict checks of the source (glTF, texture, config, donor, budget)
  py -3 -B carimport.py import CAR.toml OUT.ir.json         glTF -> car IR (game frame, per-LOD meshes by material class)
  py -3 -B carimport.py build CAR.toml OUT.bgv [--ir IR]    IR (or the glTF) + donor -> .bgv, verified by re-reading
  py -3 -B carimport.py package CAR.toml OUT_SET_DIR        mod folder for [bmashup.cars] (model + donor engine audio)
  py -3 -B carimport.py export-bgv IN.bgv OUT_DIR           CONTROL: a .bgv (e.g. retail) -> glTF (local only, labelled)
  py -3 -B carimport.py preview IN.bgv OUT.png [PAINT]      offline 4-view render of what the .bgv file contains
  py -3 -B carimport.py version                             tool version, package stamp, Python
Options: --game-data DIR (YOUR prepared game-data folder, the one with default.xbe; else the BMKIT_GAME_DATA environment
variable, in the mod kit also bmkit.toml; needed by validate / build / package; no default), --json (machine-readable report).
Exit codes (mod kit 0.4.1 convention): 0 ok, 1 refused (every problem listed), 2 usage, 3 cannot run (prerequisite missing:
Python, tool files, game data), 4 internal failure. (carimport 0.1.0 used 3 for refused.)
"""
import sys

if sys.version_info < (3, 11):
    sys.stderr.write('carimport: CANNOT RUN: Python %d.%d found; carimport needs Python 3.11 or later (it reads car.toml with '
                     'the standard tomllib module). Install it from python.org and run "py -3.12 -B carimport.py ...".\n'
                     % sys.version_info[:2])
    sys.exit(3)

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import struct  # noqa: E402
import tomllib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from carimp import bgvwrite, demo, gamedata, gltf, model, png, texture  # noqa: E402
except ImportError as _e:   # an incomplete copy of the tool folder
    sys.stderr.write('carimport: CANNOT RUN: installation incomplete (%s). Copy the whole carimport folder (every file listed '
                     'in SHA256SUMS.txt, including carimp\\*.py and GAMEDATA_SHA256.json) and run it from there.\n' % _e)
    sys.exit(3)

TOOL_VERSION = '0.1.1'      # portable successor of 0.1.0 (no workspace paths, explicit game data, actionable errors)
PACKAGE_STAMP = '0.1.0'     # written into mod.toml / carimport.json: the OUTPUT format, unchanged (packages byte-identical)
ALNUM = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
CLASSES = ('COMP', 'MSCL', 'CUPE', 'SPRT', 'SUPR', 'HSPC', 'HEVY')


class Refused(Exception):
    def __init__(self, problems):
        self.problems = problems if isinstance(problems, list) else [problems]
        Exception.__init__(self, '; '.join(self.problems))


class Prereq(Exception):
    """a prerequisite is missing (game data, tool files): exit 3, 'carimport: CANNOT RUN: ...'"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def game_data(game):
    """GameData from an explicit value (str / None -> option, environment, kit configuration) or an existing GameData"""
    if isinstance(game, gamedata.GameData):
        return game
    try:
        return gamedata.resolve(game, what='carimport (donor parts)')
    except gamedata.GameDataError as e:
        raise Prereq(str(e))


def donor_rel(donor):
    """relative game-data paths of a donor's model / engine audio (None when the file is absent)"""
    return {ext: 'pveh/%s/%s.%s' % (donor[:4], donor[4:], ext) for ext in ('bgv', 'hwd', 'lwd')}


def read_game(gd, rel):
    try:
        return gd.read(rel)
    except gamedata.GameDataError as e:
        raise Prereq(str(e))


def need_file(path, what):
    if not os.path.exists(path):
        raise Refused('%s %s: no such file (check the path; relative paths are resolved from %s)' % (what, path, os.getcwd()))
    if os.path.isdir(path):
        raise Refused('%s %s is a folder, not a file' % (what, path))


def out_file(path, what):
    """the parent folder of an output file must exist; the output must not be a folder"""
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        raise Refused('%s %s: the folder %s does not exist (create it first)' % (what, path, d))
    if os.path.isdir(path):
        raise Refused('%s %s is an existing folder; give a file name' % (what, path))


# ---------------------------------------------------------------- config
def load_config(path):
    probs = []
    need_file(path, 'car definition')
    try:
        cfg = tomllib.load(open(path, 'rb'))
    except Exception as e:  # noqa: BLE001
        raise Refused('config %s: %s' % (path, e))
    base = os.path.dirname(os.path.abspath(path))
    car = cfg.get('car', {})
    known = {'id', 'donor', 'name', 'model', 'paint_mask', 'texture_name', 'deform', 'mod_id', 'mod_name', 'mod_version',
             'wheel_uv'}
    for k in car:
        if k not in known:
            probs.append('[car] key %r unknown' % k)
    for k in cfg:
        if k not in ('car', 'paint'):
            probs.append('table [%s] unknown' % k)
    cid = str(car.get('id', '')).upper()
    donor = str(car.get('donor', '')).upper()
    if not (5 <= len(cid) <= 12 and cid[:4] in CLASSES and set(cid[4:]) <= ALNUM):
        probs.append('car.id %r: the class (COMP MSCL CUPE SPRT SUPR HSPC HEVY) + 1..8 of A-Z 0-9' % cid)
    if donor[:4] != cid[:4]:
        probs.append('car.donor %r must be a retail race car of the same class as %r' % (donor, cid))
    paints = []
    for p in cfg.get('paint', []):
        c = str(p.get('color', ''))
        if len(c) != 7 or c[0] != '#':
            probs.append('paint %r: color must be #RRGGBB' % p)
            continue
        nm = str(p.get('name', ''))
        if not nm or not all(ch.isalnum() or ch in '_.-' for ch in nm) or nm.lower() != nm or len(nm) > 40:
            probs.append('paint name %r: [a-z0-9_.-]{1,40}' % nm)
        paints.append((nm, tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))))
    if len({n for n, _ in paints}) != len(paints):
        probs.append('duplicate paint names')
    deform = car.get('deform', 'transfer')
    if deform not in ('transfer', 'rigid'):
        probs.append('car.deform %r (transfer | rigid)' % deform)
    wuv = car.get('wheel_uv', [0.0, 0.0, 0.0625, 0.125])
    if not (isinstance(wuv, list) and len(wuv) == 4 and all(0 <= float(x) <= 1 for x in wuv)):
        probs.append('car.wheel_uv must be [u0, v0, u1, v1] in 0..1')
    tn = str(car.get('texture_name', cid.lower()))
    if not tn.isascii() or len(tn) > 23:
        probs.append('car.texture_name: ASCII, <= 23 characters')
    name = str(car.get('name', ''))
    if not (1 <= len(name) <= 21) or not name.isascii():
        probs.append('car.name %r: 1..21 ASCII characters (garage name, cars2 rule)' % name)
    if 'model' not in car:
        probs.append('car.model missing (the .gltf / .glb file)')
    else:
        mp = os.path.join(base, car['model'])
        if not os.path.isfile(mp):
            probs.append('car.model %r: file %s not found (paths in car.toml are relative to the car.toml folder)'
                         % (car['model'], mp))
    if car.get('paint_mask') and not os.path.isfile(os.path.join(base, car['paint_mask'])):
        probs.append('car.paint_mask %r: file %s not found' % (car['paint_mask'], os.path.join(base, car['paint_mask'])))
    if probs:
        raise Refused(probs)
    return dict(id=cid, donor=donor, name=name, model=os.path.join(base, car['model']),
                mask=os.path.join(base, car['paint_mask']) if car.get('paint_mask') else None,
                texture_name=tn, deform=deform, paints=paints, wheel_uv=[float(x) for x in wuv],
                mod_id=car.get('mod_id', 'bmashup.carimp-' + cid.lower()),
                mod_name=car.get('mod_name', 'carimport: ' + name), mod_version=car.get('mod_version', '1.0.0'),
                path=os.path.abspath(path))


# ---------------------------------------------------------------- pipeline
def stage_import(cfg):
    try:
        sc = gltf.load(cfg['model'])
        ir = model.build_ir(sc)
    except gltf.GltfError as e:
        raise Refused(e.problems)
    mask = open(cfg['mask'], 'rb').read() if cfg['mask'] else None
    try:
        tex = texture.build(ir['image_png'], mask, cfg['paints'])
    except (texture.TexError, png.PngError) as e:
        raise Refused(['texture: %s' % e])
    return sc, ir, tex


def stage_build(cfg, ir, tex, game):
    gd = game_data(game)
    dp = donor_rel(cfg['donor'])
    if not gd.exists(dp['bgv']):
        raise Refused('donor model %s not found in your game data %s: car.donor must name a retail race car of the class '
                      '(e.g. %sCAR1)' % (dp['bgv'], gd.root, cfg['donor'][:4]))
    db = read_game(gd, dp['bgv'])
    wheel = ir['wheel']
    if wheel is None:
        r = struct.unpack_from('<f', db, 0x18)[0]
        wheel = model.gen_wheel(r, uv_box=tuple(cfg['wheel_uv']))
        ir['notes'].append('wheel: generated neutral cylinder (radius = donor wheel radius %.3f m, texture box %s)'
                           % (r, cfg['wheel_uv']))
    ir2 = dict(ir)
    ir2['wheel'] = wheel
    try:
        out, rep = bgvwrite.build(ir2, db, deform=cfg['deform'], tex=tex, tex_name=cfg['texture_name'])
        chk = bgvwrite.verify(out, ir2)
    except bgvwrite.BuildError as e:
        raise Refused(['build: %s' % e])
    rep['verify'] = chk
    rep['donor'] = dict(id=cfg['donor'], bgv_sha256=sha(db))
    # envelope report: the donor's hull / wheels / emitters are kept, so the authored body is compared with the donor's
    dmax = rep['donor_aabb']['max']
    dmin = rep['donor_aabb']['min']
    env = []
    for k, ax in enumerate('xyz'):
        ad = rep['aabb']['max'][k] - rep['aabb']['min'][k]
        dd = dmax[k] - dmin[k]
        env.append(dict(axis=ax, authored=ad, donor=dd, ratio=ad / dd))
    rep['envelope'] = env
    bad = [e for e in env if not 0.7 <= e['ratio'] <= 1.3]
    if bad:
        raise Refused(['body extent %s differs from the donor by more than 30 %% (the donor collision hull, wheels and '
                       'emitters are kept: scale the model or pick another donor)' % ['%s %.2f' % (e['axis'], e['ratio'])
                                                                                     for e in bad]])
    dpe = {k: (v if gd.exists(v) else None) for k, v in dp.items()}
    return out, rep, ir2, dict(dpe, gd=gd)


def ir_to_json(ir):
    def mesh(m):
        return dict(verts=[[list(p), list(n), list(uv)] for p, n, uv in m.verts],
                    groups={k: [list(t) for t in v] for k, v in m.groups.items()})
    return dict(format='carimport-ir', version=1, frame='car: metres, +Y up, +Z front, +X left',
                lods=[mesh(m) for m in ir['lods']], wheel=mesh(ir['wheel']) if ir['wheel'] else None, notes=ir['notes'])


def ir_from_json(js):
    def mesh(d):
        m = model.Mesh()
        for p, n, uv in d['verts']:
            m.verts.append((tuple(p), tuple(n), tuple(uv)))
        m.groups = {k: [tuple(t) for t in v] for k, v in d['groups'].items()}
        return m
    if not isinstance(js, dict) or js.get('format') != 'carimport-ir' or js.get('version') != 1:
        raise Refused('not a carimport IR v1 file')
    try:
        return dict(lods=[mesh(d) for d in js['lods']], wheel=mesh(js['wheel']) if js['wheel'] else None,
                    notes=js['notes'])
    except (KeyError, TypeError, ValueError) as e:
        raise Refused('carimport IR file damaged (%r): write it again with "carimport.py import"' % e)


# ---------------------------------------------------------------- commands
def cmd_demo(which, out):
    if which not in ('wedge', 'coupe'):
        raise Refused('demo: wedge | coupe')
    if os.path.isfile(out):
        raise Refused('demo output %s is a file; give a folder' % out)
    p = demo.write_demo(out, which)
    names = {'wedge': ('COMPCIW1', 'Compact Wedge', 'ciwedge', 'rigid'), 'coupe': ('COMPCIC1', 'Compact Coupe BM', 'cicoupe', 'transfer')}
    cid, nm, tn, dm = names[which]
    with open(os.path.join(out, 'car.toml'), 'w', newline='\n') as f:
        f.write('# carimport car definition (ORIGINAL procedural demo "%s"; AUTHORED geometry and texture)\n' % which)
        f.write('[car]\nid = "%s"\ndonor = "COMPCAR1"\nname = "%s"\nmodel = "%s.gltf"\npaint_mask = "paint_mask.png"\n'
                'texture_name = "%s"\ndeform = "%s"\nmod_id = "bmashup.carimp-%s"\nmod_name = "carimport demo: %s"\n'
                'mod_version = "1.0.0"\n' % (cid, nm, which, tn, dm, which, nm))
        for pn, col in (('teal', '#1FA8A0'), ('orange', '#F07818'), ('violet', '#7A3CC8'), ('white', '#F0F0F0'),
                        ('black', '#303030'), ('lime', '#90D020')):
            f.write('\n[[paint]]\nname = "%s"\ncolor = "%s"\n' % (pn, col))
    return dict(written=p, config=os.path.join(out, 'car.toml'))


def cmd_inspect(path):
    need_file(path, 'input')
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.gltf', '.glb'):
        try:
            sc = gltf.load(path)
        except gltf.GltfError as e:
            return dict(file=path, refused=e.problems)
        res = dict(file=path, nodes=[], materials=[dict(name=m['name'], cls=m['cls']) for m in sc.materials],
                   images=[dict(name=i['name'], size=len(i['png'])) for i in sc.images], notes=sc.notes)
        for nd in sc.nodes:
            res['nodes'].append(dict(name=nd.name, prims=[dict(vertices=len(p.positions), triangles=len(p.tris),
                                                               material=p.material, normals=p.normals is not None)
                                                          for p in nd.prims]))
        return res
    if ext not in ('.bgv', '.btv'):
        raise Refused('inspect %s: unsupported file type %r (.gltf, .glb, .bgv, .btv)' % (path, ext))
    b = open(path, 'rb').read()
    m = parse_bgv(b, path)
    return dict(file=path, sha256=sha(b), size=len(b), locators=b[0xC], wheels=b[0xD],
                radius=struct.unpack_from('<f', b, 0x14)[0], wheel_radius=struct.unpack_from('<f', b, 0x18)[0],
                aabb_max=struct.unpack_from('<3f', b, 0xE80), aabb_min=struct.unpack_from('<3f', b, 0xE90),
                lods=[dict(vertices=L['nv'], vb1=L['nd'], lists=sorted(L['lists']),
                           whole=[dict(n=d['n'], flags=hex(d['flags']), kind=d['kind']) for d in L['whole']['draws']])
                      for L in m.lods],
                texture=dict(name=m.tex['name'], w=m.tex['w'], h=m.tex['h'], palettes=m.tex['npal']),
                emitters=len(m.emitters), sound_blocks=len(m.deform), extra_lists=sorted(hex(k) for k in m.extra),
                slot_free=bgvwrite.SLOT_LIMIT - len(b))


def parse_bgv(b, path):
    try:
        return bgvwrite.bgvlib.parse(b)
    except Exception as e:  # noqa: BLE001 - the strict reader raises BgvError / struct.error on foreign input
        raise Refused('%s is not a Burnout 3 vehicle model (.bgv / .btv) the strict reader accepts: %s' % (path, e))


def cmd_validate(cfgp, game):
    cfg = load_config(cfgp)
    sc, ir, tex = stage_import(cfg)
    out, rep, ir2, dp = stage_build(cfg, ir, tex, game)
    missing = [k for k in ('hwd', 'lwd') if not dp[k]]
    if missing:
        raise Refused('donor engine audio %s missing' % missing)
    return dict(ok=True, car=cfg['id'], donor=cfg['donor'], notes=ir2['notes'], texture=tex['stats'], build=rep,
                bgv_sha256=sha(out))


def cmd_import(cfgp, outp):
    cfg = load_config(cfgp)
    out_file(outp, 'IR output')
    sc, ir, tex = stage_import(cfg)
    js = ir_to_json(ir)
    with open(outp, 'w', newline='\n') as f:
        json.dump(js, f, separators=(',', ':'))
    return dict(ir=outp, lods=[dict(vertices=len(m.verts), triangles=m.tri_count()) for m in ir['lods']],
                wheel='authored' if ir['wheel'] else 'generated at build', texture=tex['stats'], notes=ir['notes'])


def cmd_build(cfgp, outp, game, irp=None):
    cfg = load_config(cfgp)
    out_file(outp, 'model output')
    sc, ir, tex = stage_import(cfg)
    if irp:
        need_file(irp, 'IR file')
        try:
            js = json.load(open(irp))
        except ValueError as e:
            raise Refused('IR file %s is not JSON (%s)' % (irp, e))
        ir = ir_from_json(js)
    out, rep, ir2, dp = stage_build(cfg, ir, tex, game)
    with open(outp, 'wb') as f:
        f.write(out)
    rep['bgv'] = outp
    rep['bgv_sha256'] = sha(out)
    rep['notes'] = ir2['notes']
    rep['texture'] = tex['stats']
    return rep


MOD_TOML = '''# %(mod_name)s - generated by carimport %(tool)s (gp tools\\carimport).
# AUTHORED: the model geometry and texture (%(model)s). DERIVED (local only, never upload): the model's structural blocks
# (collision hull, wheel / locator / crush tables, emitters, engine-sound descriptors) and the engine audio files are the
# donor's (%(donor)s). Labels: LABELS.txt.
id = "%(mod_id)s"
name = "%(mod_name)s"
version = "%(mod_version)s"
description = "Adds %(id)s %(name)s (newly authored body geometry, carimport) to the %(cls)s series; donor %(donor)s."

[bmashup]
platform = ">=0.1.5"

[bmashup.cars]
version = 1
add = ["%(id)s = %(donor)s"]
names = ["%(id)s = %(name)s"]
'''


def cmd_package(cfgp, out_set, game):
    cfg = load_config(cfgp)
    if os.path.isfile(out_set):
        raise Refused('package output %s is a file; give a mod-set folder' % out_set)
    folder = cfg['mod_id'].split('.')[-1]
    mod = os.path.join(out_set, folder)
    if os.path.exists(mod):
        raise Refused('exists: %s (packages are never overwritten)' % mod)
    sc, ir, tex = stage_import(cfg)
    out, rep, ir2, dp = stage_build(cfg, ir, tex, game)
    if not dp['hwd'] or not dp['lwd']:
        raise Refused('donor engine audio missing')
    gd = dp['gd']
    cls, rest = cfg['id'][:4], cfg['id'][4:]
    files = {'files/pveh/%s/%s.bgv' % (cls, rest): out,
             'files/pveh/%s/%s.hwd' % (cls, rest): read_game(gd, dp['hwd']),
             'files/pveh/%s/%s.lwd' % (cls, rest): read_game(gd, dp['lwd'])}
    for rel, data in files.items():
        p = os.path.join(mod, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
    d = dict(cfg, tool=PACKAGE_STAMP, cls=cls, model=os.path.basename(cfg['model']))
    with open(os.path.join(mod, 'mod.toml'), 'w', newline='\n') as f:
        f.write(MOD_TOML % d)
    paints = [dict(name=n, palette=i, color='#%02X%02X%02X' % c, id='%s/%s' % (cfg['mod_id'], n))
              for i, (n, c) in enumerate(cfg['paints'] or [('base', (0, 0, 0))])]
    man = dict(format='carimport-package', version=1, tool=PACKAGE_STAMP, car=cfg['id'], donor=cfg['donor'],
               canonical_car='%s/%s' % (cfg['mod_id'], cfg['id'].lower()),
               paints=paints, paint_rule='paint i = palette i of the model (in-file P8 palettes; garage offers 0..min(n,6)-1)',
               texture='in-file (P8 512x256, %d palettes) - no external texture reference' % len(tex['palettes']),
               source=dict(model=os.path.basename(cfg['model']), model_sha256=sha(open(cfg['model'], 'rb').read())),
               labels={'files/pveh/%s/%s.bgv' % (cls, rest): 'AUTHORED geometry + texture; DERIVED donor structural blocks',
                       'files/pveh/%s/%s.hwd' % (cls, rest): 'DERIVED (byte copy of the donor engine audio)',
                       'files/pveh/%s/%s.lwd' % (cls, rest): 'DERIVED (byte copy of the donor engine audio)'},
               build=dict((k, v) for k, v in rep.items() if k not in ('lods',)), lods=rep['lods'], notes=ir2['notes'])
    with open(os.path.join(mod, 'carimport.json'), 'w', newline='\n') as f:
        json.dump(man, f, indent=1, sort_keys=True, default=list)
    with open(os.path.join(mod, 'LABELS.txt'), 'w', newline='\n') as f:
        for k, v in sorted(man['labels'].items()):
            f.write('%s: %s\n' % (k, v))
        f.write('LOCAL ONLY: contains donor (retail) structural data and audio - never upload or ship in a kit.\n')
    sums = []
    for root, _, fs in os.walk(mod):
        for n in sorted(fs):
            if n == 'SHA256SUMS.txt':
                continue
            p = os.path.join(root, n)
            sums.append('%s  %s' % (sha(open(p, 'rb').read()), os.path.relpath(p, mod).replace('\\', '/')))
    with open(os.path.join(mod, 'SHA256SUMS.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(sorted(sums, key=lambda s: s[66:])) + '\n')
    return dict(mod=mod, bgv_sha256=sha(out), size=len(out), files=sorted(files), paints=len(paints))


def cmd_export(inp, out_dir):
    """CONTROL ONLY: every LOD's whole list (body = LOD 3, body_lod0..2) + wheel list L7 of LOD 3 -> glTF (+ palette 0
    texture). Draws of classes slice 1 does not carry (light groups 0x4..0x80, 0x10002 = plain on texture slot 1) are
    exported as plain / their nearest class only where flags 1 / 2 / 0x100 are set. Local, labelled."""
    need_file(inp, 'model')
    b = open(inp, 'rb').read()
    m = parse_bgv(b, inp)
    if os.path.isfile(out_dir):
        raise Refused('export output %s is a file; give a folder' % out_dir)
    os.makedirs(out_dir, exist_ok=True)

    def prims(draws, L):
        V = [struct.unpack_from('<3fI2f', b, L['vb0'] + 24 * i) for i in range(L['nv'])]
        out = []
        for cls_flag, cls_mat in ((1, 0), (2, 1), (0x100, 2)):
            tris = []
            for d in draws:
                if d['flags'] & 0xFFFF & cls_flag:
                    ix = list(struct.unpack_from('<%dH' % d['n'], b, d['off']))
                    tris += bgvwrite.strip_tris(ix)
            if not tris:
                continue
            used = sorted({i for t in tris for i in t})
            remap = {o: k for k, o in enumerate(used)}
            out.append(dict(positions=[V[i][:3] for i in used],
                            normals=[bgvwrite.unpack_normal(V[i][3]) for i in used],
                            uvs=[V[i][4:] for i in used], tris=[tuple(remap[i] for i in t) for t in tris],
                            material=cls_mat))
        return out
    T = m.tex
    lin = texture.unswizzle(b[T['texels']:T['texels'] + T['w'] * T['h']], T['w'], T['h'])
    pal = texture.pal_from_bytes(b[T['pals'][0]['data']:T['pals'][0]['data'] + 0x400])
    png.write_rgba(os.path.join(out_dir, 'texture.png'), T['w'], T['h'], [pal[i][:3] + (255,) for i in lin])
    L = m.lods[-1]
    nodes = [dict(name='body', prims=prims(L['whole']['draws'], L)), dict(name='wheel', prims=prims(L['lists'][7]['draws'], L))]
    for k in range(len(m.lods) - 1):
        nodes.append(dict(name='body_lod%d' % k, prims=prims(m.lods[k]['whole']['draws'], m.lods[k])))
    p = os.path.join(out_dir, 'control.gltf')
    gltf.write(p, nodes, demo.MATERIALS, ['texture.png'], generator='carimport export-bgv CONTROL (local only; source %s)'
               % sha(b)[:12])
    with open(os.path.join(out_dir, 'LABEL.txt'), 'w', newline='\n') as f:
        f.write('CONTROL export of %s (sha256 %s): retail-derived, LOCAL ONLY, never a demo asset.\n' % (inp, sha(b)))
    return dict(gltf=p, source_sha256=sha(b))


def cmd_preview(inp, outp, paint):
    need_file(inp, 'model')
    out_file(outp, 'preview output')
    b = open(inp, 'rb').read()
    parse_bgv(b, inp)
    try:
        paint = int(paint)
    except ValueError:
        raise Refused('preview PAINT %r: a palette number (0, 1, ...)' % paint)
    from carimp import preview
    return preview.sheet(b, outp, paint=paint)


def cmd_version():
    return dict(tool='carimport', version=TOOL_VERSION, package_stamp=PACKAGE_STAMP, python=sys.version.split()[0],
                bgvlib_sha256=bgvwrite.bgvlib_sha(), game_data_env=gamedata.ENV,
                game_data_resolver='mod kit bmkit_env' if gamedata.kit_env() else 'stand-alone (option / environment)')


def main(argv):
    js = '--json' in argv
    argv = [a for a in argv if a != '--json']
    game = None
    for opt in ('--game-data', '--ir'):
        if opt in argv and argv.index(opt) + 1 >= len(argv):
            print('%s needs a value' % opt)
            print(__doc__)
            return 2
    if '--game-data' in argv:
        i = argv.index('--game-data')
        game = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    irp = None
    if '--ir' in argv:
        i = argv.index('--ir')
        irp = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, args = argv[1], argv[2:]
    try:
        if cmd == 'demo' and len(args) == 2:
            res = cmd_demo(*args)
        elif cmd == 'inspect' and len(args) == 1:
            res = cmd_inspect(args[0])
        elif cmd == 'validate' and len(args) == 1:
            res = cmd_validate(args[0], game)
        elif cmd == 'import' and len(args) == 2:
            res = cmd_import(*args)
        elif cmd == 'build' and len(args) == 2:
            res = cmd_build(args[0], args[1], game, irp)
        elif cmd == 'package' and len(args) == 2:
            res = cmd_package(args[0], args[1], game)
        elif cmd == 'export-bgv' and len(args) == 2:
            res = cmd_export(*args)
        elif cmd == 'preview' and len(args) in (2, 3):
            res = cmd_preview(args[0], args[1], args[2] if len(args) == 3 else 0)
        elif cmd == 'version' and not args:
            res = cmd_version()
        else:
            print(__doc__)
            return 2
    except Refused as e:
        if js:
            print(json.dumps(dict(refused=e.problems), indent=1))
        else:
            print('REFUSED:')
            for p in e.problems:
                print('  - ' + p)
        return 1
    except Prereq as e:
        if js:
            print(json.dumps(dict(cannot_run=str(e)), indent=1))
        sys.stderr.write('carimport: CANNOT RUN: %s\n' % e)
        return 3
    except OSError as e:
        msg = 'file system: %s (check the path, that the folder exists and is writable, and free disk space)' % e
        if js:
            print(json.dumps(dict(refused=[msg]), indent=1))
        else:
            print('REFUSED:\n  - ' + msg)
        return 1
    except Exception as e:  # noqa: BLE001 - last resort: never a bare traceback for a user
        import traceback
        print('INTERNAL ERROR in carimport %s (%s: %s). Please report it with the command line and this text:' %
              (TOOL_VERSION, type(e).__name__, e))
        traceback.print_exc(file=sys.stdout)
        return 4
    print(json.dumps(res, indent=1, sort_keys=True, default=list))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
