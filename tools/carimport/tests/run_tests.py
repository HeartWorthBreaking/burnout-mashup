"""carimport offline tests.  py -3 -B tests\\run_tests.py [--game-data DIR] [--json OUT]

Game data: --game-data DIR or the BMKIT_GAME_DATA environment variable (YOUR prepared game-data folder with default.xbe, read
only, every file hash-checked). Without it only T1, T2 (packing) and T3 run; the rest are reported SKIPPED (not passed).

T1  strips: random triangle sets survive to_strip -> strip_tris (orientation included); parity / join edge cases
T2  normal packing: round trip error bound; decoded retail normals are unit length (all 67 race cars, LOD 3)
T3  swizzle: identical to s6 bgvlib.swizzle / unswizzle (512x256)
T4  demo builds (wedge, coupe): strict s6 reader accepts, bgvlib round trip byte-identical, IR re-decoded from the file
    (positions / UVs bit-exact, normals within packing error, triangles + orientation per material class), VB1 covers all
T5  CONTROL round trip: retail COMP/Car1 LOD 3 -> export-bgv glTF -> import -> build -> decoded whole list = the retail
    whole list (same triangle set by position, same orientation, normals / UVs equal); retail texture -> PNG -> texture.build
    -> the same colour per texel
T6  validator NEGATIVES: each malformed / unsupported input is REFUSED with a message (never dropped)
T7  writer MUTANTS: deliberately broken writer variants must be caught by verify() or the T5 control
T8  determinism: two builds of each demo are byte-identical
"""
import base64
import copy
import json
import os
import random
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
import carimport  # noqa: E402
from carimp import bgvwrite, demo, gamedata, gltf, model, png, texture  # noqa: E402

bgvlib = bgvwrite.bgvlib
GAME = None          # carimp.gamedata.GameData, set in main() from --game-data / BMKIT_GAME_DATA
RES = []


def check(name, ok, detail=''):
    RES.append(dict(test=name, ok=bool(ok), detail=str(detail)[:300]))
    print('%s %s %s' % ('PASS' if ok else 'FAIL', name, ('- ' + str(detail)[:200]) if not ok or detail else ''))
    return ok


def canon(t):
    k = t.index(min(t))
    return t[k:] + t[:k]


# ---------------------------------------------------------------- T1
def t1():
    rnd = random.Random(7)
    for trial in range(300):
        n = rnd.randint(1, 40)
        tris = []
        for _ in range(n):
            a, b, c = rnd.sample(range(30), 3)
            tris.append((a, b, c))
        s = bgvwrite.to_strip(tris)
        back = bgvwrite.strip_tris(s)
        if sorted(canon(t) for t in back) != sorted(canon(t) for t in tris):
            return check('T1 strips random', False, 'trial %d' % trial)
    # adjacency continuation (a quad strip) must not add joins
    q = [(0, 1, 2), (2, 1, 3), (2, 3, 4), (4, 3, 5)]
    s = bgvwrite.to_strip(q)
    check('T1 strips continuation', len(s) == 6 and sorted(canon(t) for t in bgvwrite.strip_tris(s)) == sorted(canon(t) for t in q), s)
    return check('T1 strips random', True, '300 sets')


# ---------------------------------------------------------------- T2
def t2():
    rnd = random.Random(3)
    worst = 0
    for _ in range(20000):
        v = [rnd.uniform(-1, 1) for _ in range(3)]
        ln = sum(x * x for x in v) ** 0.5 or 1
        v = [x / ln for x in v]
        d = bgvwrite.unpack_normal(bgvwrite.pack_normal(v))
        worst = max(worst, max(abs(d[i] - v[i]) for i in range(3)))
    check('T2 normal pack round trip', worst <= 0.5 / 511 + 1e-9, 'max err %.5f' % worst)
    if GAME is None:
        return
    lens = []
    rels = sorted(k for k in gamedata.reference() if k.startswith('pveh/') and k.endswith('.bgv'))
    for rel in rels:
        b = GAME.read(rel)
        m = bgvlib.parse(b)
        L = m.lods[-1]
        for i in range(0, L['nv'], 7):
            n = bgvwrite.unpack_normal(struct.unpack_from('<I', b, L['vb0'] + 24 * i + 12)[0])
            lens.append(sum(x * x for x in n) ** 0.5)
    check('T2 retail normals unit length (67 cars)', lens and min(lens) > 0.99 and max(lens) < 1.01,
          '%d samples %.4f..%.4f' % (len(lens), min(lens), max(lens)))


# ---------------------------------------------------------------- T3
def t3():
    rnd = random.Random(5)
    lin = bytes(rnd.randrange(256) for _ in range(512 * 256))
    a = texture.swizzle(lin)
    b = bgvlib.swizzle(lin, 512, 256)
    check('T3 swizzle = s6 bgvlib', a == b and texture.unswizzle(a) == lin == bgvlib.unswizzle(b, 512, 256))


# ---------------------------------------------------------------- T4 / T8
def build_demo(which, root):
    d = os.path.join(root, which)
    carimport.cmd_demo(which, d)
    cfg = carimport.load_config(os.path.join(d, 'car.toml'))
    sc, ir, tex = carimport.stage_import(cfg)
    out, rep, ir2, dp = carimport.stage_build(cfg, ir, tex, GAME)
    return d, cfg, out, rep, ir2


def t4(root):
    outs = {}
    for which in ('wedge', 'coupe'):
        d, cfg, out, rep, ir2 = build_demo(which, root)
        m = bgvlib.parse(out)
        ok = bgvlib.build(m) == out and all(L['nd'] == L['nv'] for L in m.lods)
        chk = bgvwrite.verify(out, ir2)
        check('T4 %s strict reader + round trip + IR decode' % which, ok and chk.get('ir_checked'),
              'size %d free %d pal %d' % (len(out), rep['slot_free'], rep['palettes']))
        # paints: ramp entries differ between palettes, every other entry identical
        pals = [texture.pal_from_bytes(out[P['data']:P['data'] + 0x400]) for P in m.tex['pals']]
        diff = sorted({k for p in pals[1:] for k in range(256) if p[k] != pals[0][k]})
        check('T4 %s paints only recolour the ramp 64..127' % which, len(pals) == 6 and diff and min(diff) >= 64 and
              max(diff) <= 127, 'palettes %d, differing entries %d..%d' % (len(pals), min(diff), max(diff)))
        outs[which] = out
        # T8 determinism
        out2 = build_demo(which, os.path.join(root, 'again'))[2]
        check('T8 %s deterministic' % which, out2 == out)
    return outs


# ---------------------------------------------------------------- T5 control
def decoded_whole(b, lod=3):
    m = bgvlib.parse(b)
    L = m.lods[lod]
    V = [struct.unpack_from('<3fI2f', b, L['vb0'] + 24 * i) for i in range(L['nv'])]
    out = {}
    for d in L['whole']['draws']:
        cls = d['flags'] & 0xFFFF
        if cls not in (1, 2, 0x100):
            continue
        ix = list(struct.unpack_from('<%dH' % d['n'], b, d['off']))
        for t in bgvwrite.strip_tris(ix):
            key = tuple(V[i][:3] for i in t)
            k = key.index(min(key))
            key = key[k:] + key[:k]
            out.setdefault({1: 'paint', 2: 'plain', 0x100: 'glass'}[cls], []).append(
                (key, tuple(tuple(round(c, 3) for c in bgvwrite.unpack_normal(V[i][3])) for i in t[k:] + t[:k]),
                 tuple(V[i][4:] for i in t[k:] + t[:k])))
    return {c: sorted(v) for c, v in out.items()}


def t5(root):
    rb = GAME.read('pveh/COMP/Car1.bgv')          # hash-checked
    src = GAME.path('pveh/COMP/Car1.bgv')
    d = os.path.join(root, 'control_comp1')
    carimport.cmd_export(src, d)
    # retail draws with other flags (lights 0x4..0x80, 0x10002 second texture slot) are not classes of slice 1: the
    # control compares the classes it can carry (flags 1 / 2 / 0x100 with slot 0 / 0 / 2 - see the note in the report)
    with open(os.path.join(d, 'car.toml'), 'w') as f:
        f.write('[car]\nid = "COMPCTL1"\ndonor = "COMPCAR1"\nname = "Control"\nmodel = "control.gltf"\ndeform = "transfer"\n')
    cfg = carimport.load_config(os.path.join(d, 'car.toml'))
    sc, ir, tex = carimport.stage_import(cfg)
    out, rep, ir2, dp = carimport.stage_build(cfg, ir, tex, GAME)
    ok = True
    det = []
    for lod, c in [(k, c) for k in range(4) for c in ('paint', 'plain', 'glass')]:
        A = decoded_whole(rb, lod)
        B = decoded_whole(out, lod)
        a = [x for x in A.get(c, [])]
        b = [x for x in B.get(c, [])]
        pa = sorted(x[0] for x in a)
        pb = sorted(x[0] for x in b)
        same_pos = pa == pb
        na = {x[0]: x[1] for x in a}
        nb = {x[0]: x[1] for x in b}
        nerr = max([max(abs(na[k][j][i] - nb[k][j][i]) for j in range(3) for i in range(3)) for k in na if k in nb] or [0])
        ua = {x[0]: x[2] for x in a}
        ub = {x[0]: x[2] for x in b}
        uv_same = all(ua[k] == ub[k] for k in ua if k in ub)
        det.append('L%d %s %d/%d pos=%s nerr %.4f uv=%s' % (lod, c, len(pa), len(pb), same_pos, nerr, uv_same))
        ok &= same_pos and nerr <= 0.004 and uv_same
    check('T5 CONTROL retail COMP/Car1 LODs 0-3 -> glTF -> .bgv: same triangles / winding / normals / UVs', ok, '; '.join(det))
    # texture control: palette 0 colours per texel preserved
    m0 = bgvlib.parse(rb)
    m1 = bgvlib.parse(out)

    def cols(b, m):
        T = m.tex
        lin = texture.unswizzle(b[T['texels']:T['texels'] + 0x20000])
        pal = texture.pal_from_bytes(b[T['pals'][0]['data']:T['pals'][0]['data'] + 0x400])
        return [pal[i][:3] for i in lin]
    check('T5 CONTROL texture colours per texel preserved (palette 0)', cols(rb, m0) == cols(out, m1))
    return rb, out


# ---------------------------------------------------------------- T6 negatives
def t6(root):
    base = os.path.join(root, 'neg_base')
    carimport.cmd_demo('wedge', base)
    js0 = json.load(open(os.path.join(base, 'wedge.gltf')))
    cases = []

    def case(name, mut_js=None, mut_cfg=None, files=None, expect=''):
        cases.append((name, mut_js, mut_cfg, files, expect))

    def add_attr(js, attr, n=None):
        acc = js['meshes'][0]['primitives'][0]['attributes']['POSITION']
        js['meshes'][0]['primitives'][0]['attributes'][attr] = acc
    case('vertex colours COLOR_0', lambda js: add_attr(js, 'COLOR_0'), expect='COLOR_0')
    case('skin weights JOINTS_0', lambda js: add_attr(js, 'JOINTS_0'), expect='JOINTS_0')
    case('second UV set', lambda js: add_attr(js, 'TEXCOORD_1'), expect='TEXCOORD_1')
    case('skins present', lambda js: js.__setitem__('skins', [dict(joints=[0])]), expect='skins')
    case('animations present', lambda js: js.__setitem__('animations', [dict(channels=[], samplers=[])]), expect='animations')
    case('camera present', lambda js: js.__setitem__('cameras', [dict(type='perspective')]), expect='cameras')
    case('extension required', lambda js: js.__setitem__('extensionsRequired', ['KHR_draco_mesh_compression']), expect='extension')
    case('extension used (lights)', lambda js: js.__setitem__('extensionsUsed', ['KHR_lights_punctual']), expect='extension')
    case('line primitives', lambda js: js['meshes'][0]['primitives'][0].__setitem__('mode', 1), expect='mode 1')
    case('morph targets', lambda js: js['meshes'][0]['primitives'][0].__setitem__('targets', [{}]), expect='morph')
    case('no UVs', lambda js: js['meshes'][0]['primitives'][0]['attributes'].pop('TEXCOORD_0'), expect='TEXCOORD_0')
    case('unknown material class', lambda js: (js['materials'][0].__setitem__('extras', dict(bm_class='chrome'))), expect='class')
    case('baseColorFactor', lambda js: js['materials'][0]['pbrMetallicRoughness'].__setitem__('baseColorFactor', [1, 0, 0, 1]), expect='baseColorFactor')
    case('emissive (lights)', lambda js: js['materials'][0].__setitem__('emissiveFactor', [1, 1, 0]), expect='emissive')
    case('normal map', lambda js: js['materials'][0].__setitem__('normalTexture', dict(index=0)), expect='normalTexture')
    case('unknown mesh node (door)', lambda js: js['nodes'][0].__setitem__('name', 'door_left'), expect='not supported')
    case('mesh not in the scene', lambda js: js['meshes'].append(copy.deepcopy(js['meshes'][0])), expect='not instantiated')
    case('two textures', lambda js: (js['images'].append(dict(uri='texture2.png', mimeType='image/png')),
                                     js['textures'].append(dict(source=1)),
                                     js['materials'][1]['pbrMetallicRoughness']['baseColorTexture'].__setitem__('index', 1)),
         files={'texture2.png': 'texture.png'}, expect='different images')
    case('jpeg image', lambda js: js['images'][0].__setitem__('mimeType', 'image/jpeg'), expect='not PNG')
    case('body scaled x2 (envelope)', lambda js: js['nodes'][0].__setitem__('scale', [2, 2, 2]), expect='differs from the donor')
    case('bad car id', mut_cfg=lambda s: s.replace('id = "COMPCIW1"', 'id = "COMP-X"'), expect='car.id')
    case('donor of another class', mut_cfg=lambda s: s.replace('donor = "COMPCAR1"', 'donor = "SPRTCAR1"'), expect='same class')
    case('paints without a mask', mut_cfg=lambda s: s.replace('paint_mask = "paint_mask.png"\n', ''), expect='no paint mask')
    case('nine paints', mut_cfg=lambda s: s + ''.join('\n[[paint]]\nname = "x%d"\ncolor = "#102030"\n' % i for i in range(3)), expect='at most 8')
    case('unknown config key', mut_cfg=lambda s: s.replace('[car]\n', '[car]\nlights = true\n'), expect='unknown')
    case('name too long', mut_cfg=lambda s: s.replace('name = "Compact Wedge"', 'name = "A very long car name here"'), expect='1..21')
    case('texture wrong size', files={'texture.png': ('size', 256, 256)}, expect='512x256')
    case('wheel not centred', lambda js: (js['nodes'].append(dict(name='wheel', mesh=0, translation=[0.8, 0, 1.2])),
                                          js['scenes'][0]['nodes'].append(len(js['nodes']) - 1)), expect='not centred')
    for name, mj, mc, files, expect in cases:
        d = os.path.join(root, 'neg_' + ''.join(ch if ch.isalnum() else '_' for ch in name))
        shutil.copytree(base, d)
        js = copy.deepcopy(js0)
        if mj:
            mj(js)
        json.dump(js, open(os.path.join(d, 'wedge.gltf'), 'w'))
        if mc:
            s = open(os.path.join(d, 'car.toml')).read()
            open(os.path.join(d, 'car.toml'), 'w').write(mc(s))
        for fn, how in (files or {}).items():
            if isinstance(how, tuple):
                png.write_rgba(os.path.join(d, fn), how[1], how[2], [(128, 128, 128, 255)] * (how[1] * how[2]))
            else:
                shutil.copy(os.path.join(d, how), os.path.join(d, fn))
        try:
            carimport.cmd_validate(os.path.join(d, 'car.toml'), GAME)
            check('T6 refuse: %s' % name, False, 'ACCEPTED')
        except carimport.Refused as e:
            msg = ' | '.join(e.problems)
            check('T6 refuse: %s' % name, expect.lower() in msg.lower(), msg)
    # positive control: the unmodified base validates
    try:
        carimport.cmd_validate(os.path.join(base, 'car.toml'), GAME)
        check('T6 positive control (unmodified wedge validates)', True)
    except carimport.Refused as e:
        check('T6 positive control (unmodified wedge validates)', False, e.problems)


# ---------------------------------------------------------------- T7 mutants
def t7(root, control):
    d, cfg, out, rep, ir2 = None, None, None, None, None
    dd = os.path.join(root, 'mut')
    carimport.cmd_demo('coupe', dd)
    cfg = carimport.load_config(os.path.join(dd, 'car.toml'))
    sc, ir, tex = carimport.stage_import(cfg)
    muts = []
    orig_pack = bgvwrite.pack_normal
    orig_strip = bgvwrite.to_strip
    orig_swz = texture.swizzle
    orig_flags = dict(bgvwrite.CLS_FLAGS)

    def m1():
        bgvwrite.pack_normal = lambda n: orig_pack((n[0], n[1], -n[2]))
    def m2():
        def bad(tris):
            return orig_strip([(a, c, b) for a, b, c in tris])
        bgvwrite.to_strip = bad
    def m3():
        def bad(tris):
            s = orig_strip(tris)
            return s[:-1] if len(s) > 4 else s
        bgvwrite.to_strip = bad
    def m4():
        bgvwrite.CLS_FLAGS['paint'] = (2, 0, 1.0, 0.0)
    def m5():
        bgvwrite.pack_normal = lambda n: orig_pack((n[1], n[0], n[2]))
    for name, fn in (('normal z sign', m1), ('triangle winding reversed', m2), ('strip truncated', m3),
                     ('paint class written as plain', m4), ('normal x/y swapped', m5)):
        fn()
        caught = False
        why = ''
        try:
            wheel = model.gen_wheel(0.312)
            ir2 = dict(ir)
            ir2['wheel'] = ir['wheel'] or wheel
            o, r = bgvwrite.build(ir2, GAME.read('pveh/COMP/Car1.bgv'), tex=tex,
                                  deform='rigid')
            bgvwrite.verify(o, ir2)
        except (bgvwrite.BuildError, bgvlib.BgvError, KeyError) as e:
            caught = True
            why = str(e)
        bgvwrite.pack_normal = orig_pack
        bgvwrite.to_strip = orig_strip
        bgvwrite.CLS_FLAGS.clear()
        bgvwrite.CLS_FLAGS.update(orig_flags)
        check('T7 mutant caught: %s' % name, caught, why)
    # swizzle mutant: caught by the texture control (T5 colours) - re-run that part with the mutant
    texture.swizzle = lambda lin, w=512, h=256: bytes(lin)
    try:
        rb, _ = control
        d = os.path.join(root, 'control_comp1')
        cfgc = carimport.load_config(os.path.join(d, 'car.toml'))
        sc2, irc, texc = carimport.stage_import(cfgc)
        outc, _, _, _ = carimport.stage_build(cfgc, irc, texc, GAME)
        m0 = bgvlib.parse(rb)
        m1_ = bgvlib.parse(outc)
        a = texture.unswizzle(rb[m0.tex['texels']:m0.tex['texels'] + 0x20000])
        b = orig_unswz(outc[m1_.tex['texels']:m1_.tex['texels'] + 0x20000])
        pa = texture.pal_from_bytes(rb[m0.tex['pals'][0]['data']:m0.tex['pals'][0]['data'] + 0x400])
        pb = texture.pal_from_bytes(outc[m1_.tex['pals'][0]['data']:m1_.tex['pals'][0]['data'] + 0x400])
        check('T7 mutant caught: texels not swizzled', [pa[i][:3] for i in a] != [pb[i][:3] for i in b])
    finally:
        texture.swizzle = orig_swz


orig_unswz = texture.unswizzle


FULL = 48          # checks of the full run (with game data)


def main(argv):
    global GAME
    try:
        GAME = gamedata.resolve(argv[argv.index('--game-data') + 1] if '--game-data' in argv else None)
    except gamedata.GameDataError as e:
        GAME = None
        print('SKIP (game data): %s' % e)
    root = tempfile.mkdtemp(prefix='carimp_t_', dir=os.environ.get('CARIMP_TMP'))
    try:
        t1()
        t2()
        t3()
        if GAME is not None:
            t4(root)
            control = t5(root)
            t6(root)
            t7(root, control)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    n = len(RES)
    good = sum(r['ok'] for r in RES)
    skipped = 0 if GAME is not None else FULL - n
    print('carimport tests: %d / %d PASS%s' % (good, n, (', %d SKIPPED (no game data: pass --game-data DIR or set %s; '
                                                          'a release check needs all %d)' % (skipped, gamedata.ENV, FULL))
                                               if skipped else ''))
    if '--json' in argv:
        with open(argv[argv.index('--json') + 1], 'w', newline='\n') as f:
            json.dump(dict(passed=good, total=n, skipped=skipped, results=RES), f, indent=1)
    return 0 if good == n else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
