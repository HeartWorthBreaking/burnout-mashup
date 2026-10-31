r"""carimport actionable-error tests (alpha distribution readiness).

  py -3 -B tests\test_errors.py OUT_DIR [--game-data DIR]

OUT_DIR must not exist. Every case runs carimport.py as a user would (a subprocess) and checks the exit code (mod kit 0.4.1
convention: 1 refused, 2 usage, 3 cannot run), that the message names the problem and what to do, and that no Python traceback
reaches the user. Cases marked [data] need YOUR game data (--game-data or BMKIT_GAME_DATA) and are reported SKIPPED without it;
they build small fake game-data folders around a copy of your default.xbe and delete them afterwards. All other cases use only
generated files (no game bytes).
Groups: missing dependencies (D), invalid paths (P), unsupported input (U), absent / wrong game data (G), failed builds (B).
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
CARIMPORT = os.path.join(TOOL, 'carimport.py')
sys.path.insert(0, TOOL)
from carimp import gamedata  # noqa: E402

RES = []


def check(name, ok, detail=''):
    RES.append((name, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + detail[:220].replace('\n', ' | ')) if detail else ''),
          flush=True)


def run(args, env_extra=None, tool=CARIMPORT, pre=None):
    env = dict(os.environ)
    env.pop(gamedata.ENV, None)
    env.pop('BMKIT_CONFIG', None)
    env.update(env_extra or {})
    if pre:
        cmd = [sys.executable, '-B', '-c', pre + '\nimport runpy, sys\nsys.argv = %r\nrunpy.run_path(%r, run_name="__main__")'
               % ([tool] + [str(a) for a in args], tool)]
    else:
        cmd = [sys.executable, '-B', tool] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def expect(name, rc_o, rc_want, *needles):
    rc, o = rc_o
    low = o.lower()
    miss = [n for n in needles if n.lower() not in low]
    check(name, rc == rc_want and not miss and 'Traceback' not in o,
          'rc %d (want %d)%s; %s' % (rc, rc_want, (' missing %s' % miss) if miss else '', o.strip()))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = os.path.abspath(argv[1])
    os.makedirs(out)
    gd_arg = argv[argv.index('--game-data') + 1] if '--game-data' in argv else None
    try:
        gd = gamedata.resolve(gd_arg)
    except gamedata.GameDataError as e:
        gd = None
        print('SKIP (game data) for the [data] cases: %s' % e)
    demo = os.path.join(out, 'wedge')
    rc, o = run(['demo', 'wedge', demo])
    check('setup: demo wedge written', rc == 0, o if rc else '')
    car = os.path.join(demo, 'car.toml')

    # fake game-data folders without game bytes
    fake_noxbe = os.path.join(out, 'fake_noxbe')
    os.makedirs(os.path.join(fake_noxbe, 'pveh'))
    fake_parent = os.path.join(out, 'fake_parent')
    os.makedirs(os.path.join(fake_parent, 'Burnout 3 Takedown'))
    with open(os.path.join(fake_parent, 'Burnout 3 Takedown', 'default.xbe'), 'wb') as f:
        f.write(b'XBEH not the retail executable')
    fake_pal = os.path.join(fake_parent, 'Burnout 3 Takedown')

    # D: missing dependencies
    expect('D1 Python older than 3.11 -> how to get 3.11', run(['version'], pre='import sys\nsys.version_info = (3, 10, 4)'),
           3, 'CANNOT RUN', 'Python 3.11')
    broken = os.path.join(out, 'broken_tool')
    shutil.copytree(TOOL, broken, ignore=shutil.ignore_patterns('tests', 'examples', 'docs', '__pycache__'))
    os.remove(os.path.join(broken, 'carimp', 'bgvlib.py'))
    expect('D2 tool module missing (carimp\\bgvlib.py) -> copy the whole folder',
           run(['inspect', car], tool=os.path.join(broken, 'carimport.py')), 3, 'CANNOT RUN', 'installation incomplete',
           'SHA256SUMS')
    broken2 = os.path.join(out, 'broken_tool2')
    shutil.copytree(TOOL, broken2, ignore=shutil.ignore_patterns('tests', 'examples', 'docs', '__pycache__'))
    os.remove(os.path.join(broken2, 'GAMEDATA_SHA256.json'))
    expect('D3 GAMEDATA_SHA256.json missing -> installation incomplete',
           run(['validate', car, '--game-data', fake_pal], tool=os.path.join(broken2, 'carimport.py')), 3,
           'installation incomplete', 'GAMEDATA_SHA256.json')

    # P: invalid paths
    expect('P1 car.toml does not exist', run(['validate', os.path.join(out, 'nope', 'car.toml'), '--game-data', fake_pal]),
           1, 'no such file')
    bad_model = os.path.join(out, 'badmodel')
    shutil.copytree(demo, bad_model)
    with open(os.path.join(bad_model, 'car.toml'), encoding='utf-8') as f:
        s = f.read()
    with open(os.path.join(bad_model, 'car.toml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(s.replace('model = "wedge.gltf"', 'model = "missing.gltf"'))
    expect('P2 car.model names a missing file', run(['import', os.path.join(bad_model, 'car.toml'), os.path.join(out, 'x.json')]),
           1, 'missing.gltf', 'not found')
    expect('P3 output folder does not exist', run(['import', car, os.path.join(out, 'no_dir', 'x.ir.json')]), 1,
           'does not exist')
    expect('P4 output is an existing folder', run(['import', car, out]), 1, 'existing folder')
    with open(os.path.join(out, 'notes.txt'), 'w') as f:
        f.write('text')
    expect('P5 inspect of an unsupported file type', run(['inspect', os.path.join(out, 'notes.txt')]), 1, 'unsupported file type')
    expect('P6 --game-data without a value', run(['validate', car, '--game-data']), 2, 'needs a value')

    # U: unsupported input
    ext = os.path.join(out, 'draco')
    shutil.copytree(demo, ext)
    js = json.load(open(os.path.join(ext, 'wedge.gltf')))
    js['extensionsRequired'] = ['KHR_draco_mesh_compression']
    json.dump(js, open(os.path.join(ext, 'wedge.gltf'), 'w'))
    expect('U1 glTF extension (Draco) refused with the reason', run(['import', os.path.join(ext, 'car.toml'),
                                                                     os.path.join(out, 'u1.json')]), 1, 'extension')
    with open(os.path.join(out, 'junk.bgv'), 'wb') as f:
        f.write(b'\x17' + bytes(100))
    expect('U2 a .bgv that is not a vehicle model', run(['inspect', os.path.join(out, 'junk.bgv')]), 1,
           'not a Burnout 3 vehicle model')
    badtoml = os.path.join(out, 'badtoml')
    shutil.copytree(demo, badtoml)
    with open(os.path.join(badtoml, 'car.toml'), 'a') as f:
        f.write('\n[car\n')
    expect('U3 car.toml is not valid TOML', run(['import', os.path.join(badtoml, 'car.toml'), os.path.join(out, 'u3.json')]),
           1, 'config')
    badtex = os.path.join(out, 'badtex')
    shutil.copytree(demo, badtex)
    with open(os.path.join(badtex, 'texture.png'), 'r+b') as f:
        f.truncate(60)
    expect('U4 damaged texture PNG', run(['import', os.path.join(badtex, 'car.toml'), os.path.join(out, 'u4.json')]), 1,
           'texture')
    irbad = os.path.join(out, 'bad.ir.json')
    with open(irbad, 'w') as f:
        f.write('{"format": "something else"}')
    expect('U5 --ir file of another format', run(['build', car, os.path.join(out, 'u5.bgv'), '--ir', irbad,
                                                  '--game-data', fake_pal]), 1, 'not a carimport IR')

    # G: absent / wrong game data
    expect('G1 no --game-data and no BMKIT_GAME_DATA', run(['validate', car]), 3, 'CANNOT RUN', 'none was given', '--game-data',
           gamedata.ENV)
    expect('G2 --game-data folder does not exist', run(['validate', car, '--game-data', os.path.join(out, 'nothing')]), 3,
           'does not exist or is not a folder')
    expect('G3 --game-data without default.xbe', run(['validate', car, '--game-data', fake_noxbe]), 3, 'has no default.xbe')
    expect('G4 --game-data = the parent folder -> hint', run(['validate', car, '--game-data', fake_parent]), 3,
           'give that folder instead')
    expect('G5 default.xbe of another release / patched', run(['validate', car, '--game-data', fake_pal]), 3, 'NTSC-U')
    expect('G6 BMKIT_GAME_DATA names a wrong folder', run(['validate', car], env_extra={gamedata.ENV: fake_noxbe}), 3,
           gamedata.ENV, 'has no default.xbe')

    # [data]: fake folders around a copy of YOUR default.xbe (removed at the end)
    data_cases = ['G7 donor absent from the game data [data]', 'G8 modified donor file (per-file hash check) [data]',
                  'B0 package of the wedge (positive control) [data]', 'B1 package never overwrites an existing package [data]',
                  'B2 body outside the donor envelope [data]', 'B3 build into a folder path [data]']
    if gd is None:
        for n in data_cases:
            print('SKIP %s' % n)
            RES.append((n, None))
    else:
        fakes = []
        for nm in ('fake_nocar', 'fake_moddonor'):
            d = os.path.join(out, nm)
            os.makedirs(os.path.join(d, 'pveh', 'COMP'))
            shutil.copyfile(gd.path('default.xbe'), os.path.join(d, 'default.xbe'))
            fakes.append(d)
        with open(os.path.join(fakes[1], 'pveh', 'COMP', 'Car1.bgv'), 'wb') as f:
            f.write(b'not the retail model')
        try:
            expect(data_cases[0], run(['validate', car, '--game-data', fakes[0]]), 1, 'not found in your game data',
                   'retail race car')
            expect(data_cases[1], run(['validate', car, '--game-data', fakes[1]]), 3, 'differs from the supported release',
                   'unmodified')
        finally:
            for d in fakes:
                shutil.rmtree(d, ignore_errors=True)
        st = os.path.join(out, 'set')
        rc, o = run(['package', car, st, '--game-data', gd.root])
        check(data_cases[2], rc == 0, '' if rc == 0 else o)
        expect(data_cases[3], run(['package', car, st, '--game-data', gd.root]), 1, 'never overwritten')
        big = os.path.join(out, 'big')
        shutil.copytree(demo, big)
        js = json.load(open(os.path.join(big, 'wedge.gltf')))
        js['nodes'][0]['scale'] = [2, 2, 2]
        json.dump(js, open(os.path.join(big, 'wedge.gltf'), 'w'))
        expect(data_cases[4], run(['validate', os.path.join(big, 'car.toml'), '--game-data', gd.root]), 1,
               'differs from the donor', 'scale the model')
        os.makedirs(os.path.join(out, 'folder.bgv'))
        expect(data_cases[5], run(['build', car, os.path.join(out, 'folder.bgv'), '--game-data', gd.root]), 1, 'existing folder')
    ran = [r for r in RES if r[1] is not None]
    skipped = len(RES) - len(ran)
    good = sum(1 for r in ran if r[1])
    print('carimport error tests: %d / %d PASS%s' % (good, len(ran), (', %d SKIPPED (no game data)' % skipped)
                                                    if skipped else ''))
    return 0 if good == len(ran) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
