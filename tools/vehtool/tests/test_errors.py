r"""vehtool actionable-error tests (alpha distribution readiness).

  py -3 -B tests\test_errors.py OUT_DIR [--game-data DIR]

OUT_DIR must not exist. Each case runs vehtool.py as a user would and checks the exit code, that the message names the
problem / what to do, and that no Python traceback reaches the user. Cases marked [data] need YOUR game data (--game-data or
BMKIT_GAME_DATA) and are SKIPPED without it; the others use generated files only.
Groups: missing dependencies (D), invalid paths (P), unsupported input (U), absent / wrong game data (G), failed builds (B).
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
VT = os.path.join(TOOL, 'vehtool.py')
sys.path.insert(0, TOOL)
import gamedata  # noqa: E402

RES = []

NEON_MIN = '''id = "bmashup.err-series"
name = "error test series"
version = "1.0.0"

[bmashup.series]
version = 1
add = ["err = BMER"]
names = ["err = Error Test"]
ai_class = ["err = SPRT"]

[bmashup.cars]
version = 2
add = ["BMERC01 = SPRTCAR1"]
model = ["BMERC01 = donor"]
'''

OWN_FILES = '''id = "bmashup.err-own"
name = "own files without files"
version = "1.0.0"

[bmashup.cars]
version = 2
add = ["COMPER01 = COMPCAR1"]
'''


def check(name, ok, detail=''):
    RES.append((name, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + detail[:220].replace('\n', ' | ')) if detail else ''),
          flush=True)


def run(args, tool=VT, pre=None, env_extra=None):
    env = dict(os.environ)
    env.pop(gamedata.ENV, None)
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
    miss = [n for n in needles if n.lower() not in o.lower()]
    check(name, rc == rc_want and not miss and 'Traceback' not in o,
          'rc %d (want %d)%s; %s' % (rc, rc_want, (' missing %s' % miss) if miss else '', o.strip()))


def mod(out, name, text):
    d = os.path.join(out, name)
    os.makedirs(d)
    with open(os.path.join(d, 'mod.toml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return d


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = os.path.abspath(argv[1])
    os.makedirs(out)
    try:
        gd = gamedata.resolve(argv[argv.index('--game-data') + 1] if '--game-data' in argv else None)
    except gamedata.GameDataError as e:
        gd = None
        print('SKIP (game data) for the [data] cases: %s' % e)
    good = mod(out, 'good', NEON_MIN)
    badtoml = mod(out, 'badtoml', NEON_MIN + '\n[bmashup.cars\n')
    own = mod(out, 'ownfiles', OWN_FILES)
    fake_noxbe = os.path.join(out, 'fake_noxbe')
    os.makedirs(os.path.join(fake_noxbe, 'pveh'))
    fake_pal = os.path.join(out, 'fake_pal')
    os.makedirs(os.path.join(fake_pal, 'pveh'))
    with open(os.path.join(fake_pal, 'default.xbe'), 'wb') as f:
        f.write(b'XBEH not the retail executable')

    # D
    expect('D1 Python without tomllib (< 3.11): package says how to get 3.11',
           run(['package', good], pre='import sys\nsys.modules["tomllib"] = None'), 3, 'CANNOT RUN', 'Python 3.11')
    broken = os.path.join(out, 'broken_tool')
    shutil.copytree(TOOL, broken, ignore=shutil.ignore_patterns('tests', 'examples', 'docs', '__pycache__'))
    os.remove(os.path.join(broken, 'gamedata.py'))
    expect('D2 gamedata.py missing -> copy the whole folder', run(['version'], tool=os.path.join(broken, 'vehtool.py')), 3,
           'CANNOT RUN', 'installation incomplete', 'SHA256SUMS')
    # P
    expect('P1 validate a folder that does not exist', run(['validate', os.path.join(out, 'nope')]), 1, 'no such folder')
    expect('P2 validate the mod SET instead of a mod folder', run(['validate', out]), 1, 'no mod.toml', 'mod folder itself')
    expect('P3 package a folder that does not exist', run(['package', os.path.join(out, 'nope')]), 1, 'no such folder')
    expect('P4 fixture into an existing folder', run(['fixture', good, '--cars', '3']), 1, 'exists', 'NEW folder')
    expect('P5 palette output is a folder', run(['palette', out, '--gradient', 'FFFFFF', '000000']), 1, 'existing folder')
    # U
    expect('U1 palette colour not RRGGBB', run(['palette', os.path.join(out, 'p.bmpal'), '--gradient', 'white', '000000']), 1,
           'RRGGBB')
    expect('U2 package a mod whose mod.toml is not TOML', run(['package', badtoml]), 1, 'not valid TOML')
    expect('U3 fixture --cars 0', run(['fixture', os.path.join(out, 'fx0'), '--cars', '0']), 1, '--cars 0', '1..917')
    # G
    expect('G1 validate without --game-data / BMKIT_GAME_DATA', run(['validate', good]), 3, 'CANNOT RUN', 'none was given',
           gamedata.ENV)
    expect('G2 --game-data folder does not exist', run(['inspect', '--game-data', os.path.join(out, 'nothing')]), 3,
           'does not exist or is not a folder')
    expect('G3 --game-data without default.xbe', run(['inspect', '--game-data', fake_noxbe]), 3, 'has no default.xbe')
    expect('G4 default.xbe of another release / patched', run(['inspect', '--game-data', fake_pal]), 3, 'NTSC-U')
    expect('G5 old spelling --game works the same', run(['inspect', '--game', fake_pal]), 3, 'NTSC-U')
    expect('G6 BMKIT_GAME_DATA names a wrong folder', run(['inspect'], env_extra={gamedata.ENV: fake_noxbe}), 3,
           gamedata.ENV, 'has no default.xbe')
    # B / [data]
    data_cases = ['U4 validate a mod whose mod.toml is not TOML [data]', 'G7 inspect-car of an unknown car [data]',
                  'B1 own-files car without its files is refused with the files named [data]',
                  'B2 validate of a valid series (positive control) [data]',
                  'G8 modified pveh\\vlist.bin (per-file hash check) [data]']
    if gd is None:
        for n in data_cases:
            print('SKIP %s' % n)
            RES.append((n, None))
    else:
        rc, o = run(['validate', badtoml, '--game-data', gd.root])
        check(data_cases[0], rc == 1 and 'not valid TOML' in o and 'Traceback' not in o, o.strip())
        expect(data_cases[1], run(['inspect-car', 'COMPZZ99', '--game-data', gd.root]), 1, 'no model', 'COMPCAR1')
        rc, o = run(['validate', own, '--game-data', gd.root])
        check(data_cases[2], rc == 1 and 'missing files/pveh/COMP/ER01.bgv' in o and 'Traceback' not in o, o.strip())
        rc, o = run(['validate', good, '--game-data', gd.root])
        check(data_cases[3], rc == 0 and 'ok bmashup.err-series' in o, o.strip())
        fake = os.path.join(out, 'fake_mod')
        os.makedirs(os.path.join(fake, 'pveh'))
        shutil.copyfile(gd.path('default.xbe'), os.path.join(fake, 'default.xbe'))
        with open(os.path.join(fake, 'pveh', 'vlist.bin'), 'wb') as f:
            f.write(b'modified vehicle list')
        try:
            expect(data_cases[4], run(['inspect', '--game-data', fake]), 3, 'differs from the supported release')
        finally:
            shutil.rmtree(fake, ignore_errors=True)
    expect('B3 fixture: more cars than the series hold', run(['fixture', os.path.join(out, 'fx1'), '--cars', '30', '--series', '1']),
           1, 'series hold')
    ran = [r for r in RES if r[1] is not None]
    n_ok = sum(1 for r in ran if r[1])
    skipped = len(RES) - len(ran)
    print('vehtool error tests: %d / %d PASS%s' % (n_ok, len(ran), (', %d SKIPPED (no game data)' % skipped) if skipped else ''))
    return 0 if n_ok == len(ran) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
