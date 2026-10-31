r"""fetex actionable-error tests (alpha distribution readiness).

  py -3 -B tests\test_errors.py OUT_DIR [--game-data DIR]

OUT_DIR must not exist. Each case runs fetex.py (or an example script) as a user would and checks the exit code (mod kit 0.4.1
convention: 1 refused, 3 cannot run), that the message names the problem / what to do, and that no Python traceback reaches
the user. Generated inputs only, except the [data] case: a fake folder around a copy of YOUR default.xbe (deleted afterwards).
Groups: missing dependencies (D), invalid paths (P), unsupported input (U), absent / wrong game data for the retail check (G),
failed builds (B).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
FETEX = os.path.join(TOOL, 'fetex.py')
sys.path.insert(0, TOOL)
from fetexlib import gamedata  # noqa: E402
ENV = gamedata.ENV
RES = []


def check(name, ok, detail=''):
    RES.append((name, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + detail[:220].replace('\n', ' | ')) if detail else ''),
          flush=True)


def run(args, tool=FETEX, pre=None, env_extra=None):
    env = dict(os.environ)
    env.pop(ENV, None)
    env.update(env_extra or {})
    if pre:
        cmd = [sys.executable, '-B', '-c', pre + '\nimport runpy, sys\nsys.argv = %r\nrunpy.run_path(%r, run_name="__main__")'
               % ([tool] + [str(a) for a in args], tool)]
    else:
        cmd = [sys.executable, '-B', tool] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def expect(name, rc_o, rc_want, *needles, absent=None):
    rc, o = rc_o
    miss = [n for n in needles if n.lower() not in o.lower()]
    extra = absent and os.path.exists(absent)
    check(name, rc == rc_want and not miss and 'Traceback' not in o and not extra,
          'rc %d (want %d)%s%s; %s' % (rc, rc_want, (' missing %s' % miss) if miss else '',
                                       ' OUTPUT WRITTEN' if extra else '', o.strip()))


def png(path, w, h, fn, depth=8):
    rows = b''.join(b'\0' + bytes(c for x in range(w) for c in fn(x, y)) for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, depth, 6, 0, 0, 0)) +
                chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def spec(out, name, entries):
    p = os.path.join(out, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump({'tag': 0, 'entries': entries}, f)
    return p


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = os.path.abspath(argv[1])
    os.makedirs(out)
    png(os.path.join(out, 'ok.png'), 16, 16, lambda x, y: (x * 16, y * 16, 0, 255))
    png(os.path.join(out, 'npot.png'), 48, 32, lambda x, y: (1, 2, 3, 255))
    png(os.path.join(out, 'big.png'), 2048, 4, lambda x, y: (9, 9, 9, 255))
    png(os.path.join(out, 'other.png'), 16, 16, lambda x, y: (x * 7 & 255, 0, y, 255))
    png(os.path.join(out, 'blocks.png'), 16, 16, lambda x, y: ((x // 8) * 200, (y // 8) * 200, 40, 255))   # 4 colours
    with open(os.path.join(out, 'deep.png'), 'wb') as f:          # a 16-bit PNG header (fetex reads 8-bit only)
        f.write(open(os.path.join(out, 'ok.png'), 'rb').read()[:24] + b'\x10' + open(os.path.join(out, 'ok.png'), 'rb').read()[25:])
    good = spec(out, 'good.json', [{'name': 'ok', 'png': 'ok.png', 'format': 'DXT1'}])

    # D: missing dependencies
    expect('D1 Python older than 3.8 -> install Python 3', run(['version'], pre='import sys\nsys.version_info = (3, 7, 9)'), 3,
           'CANNOT RUN', 'Python 3.8')
    broken = os.path.join(out, 'broken_tool')
    shutil.copytree(TOOL, broken, ignore=shutil.ignore_patterns('tests', 'examples', 'docs', '__pycache__'))
    os.remove(os.path.join(broken, 'fetexlib', 'txd.py'))
    expect('D2 tool module missing (fetexlib\\txd.py) -> copy the whole folder', run(['version'], tool=os.path.join(broken, 'fetex.py')),
           3, 'CANNOT RUN', 'installation incomplete', 'SHA256SUMS')

    # P: invalid paths
    expect('P1 inspect of a missing file', run(['inspect', os.path.join(out, 'none.txd')]), 1, 'no such file')
    expect('P2 pack into a folder that does not exist', run(['pack', good, os.path.join(out, 'no', 'x.txd')]), 1, 'does not exist')
    expect('P3 pack spec missing', run(['pack', os.path.join(out, 'none.json'), os.path.join(out, 'p3.txd')]), 1, 'no such file',
           absent=os.path.join(out, 'p3.txd'))
    rc, o = run(['pack', good, os.path.join(out, 'good.txd')])
    check('P4 setup: a valid pack', rc == 0, o.strip())
    open(os.path.join(out, 'afile'), 'w').write('x')
    expect('P4 extract into a path that is a file', run(['extract', os.path.join(out, 'good.txd'), os.path.join(out, 'afile')]), 1,
           'is a file')
    expect('P5 entry picture missing', run(['pack', spec(out, 'p5.json', [{'name': 'a', 'png': 'gone.png', 'format': 'DXT1'}]),
                                            os.path.join(out, 'p5.txd')]), 1, 'gone.png', 'no such file',
           absent=os.path.join(out, 'p5.txd'))

    # U: unsupported input
    expect('U1 DXT3 refused with the supported formats (was a raw KeyError)',
           run(['pack', spec(out, 'u1.json', [{'name': 'a', 'png': 'ok.png', 'format': 'DXT3'}]), os.path.join(out, 'u1.txd')]),
           1, 'DXT3', 'not supported', 'P8', 'DXT1', 'DXT5', absent=os.path.join(out, 'u1.txd'))
    with open(os.path.join(out, 'junk.txd'), 'wb') as f:
        f.write(b'not a texture dictionary at all')
    expect('U2 inspect of a file that is not a TXD', run(['inspect', os.path.join(out, 'junk.txd')]), 1, 'INVALID texture dictionary',
           'magic')
    expect('U3 16-bit PNG -> re-save as 8-bit', run(['pack', spec(out, 'u3.json', [{'name': 'a', 'png': 'deep.png', 'format': 'DXT1'}]),
                                                    os.path.join(out, 'u3.txd')]), 1, '8-bit', absent=os.path.join(out, 'u3.txd'))
    with open(os.path.join(out, 'u4.json'), 'w') as f:
        f.write('{"entries": [')
    expect('U4 pack spec is not JSON', run(['pack', os.path.join(out, 'u4.json'), os.path.join(out, 'u4.txd')]), 1, 'not valid JSON')
    expect('U5 spec entry without a format', run(['pack', spec(out, 'u5.json', [{'name': 'a', 'png': 'ok.png'}]),
                                                  os.path.join(out, 'u5.txd')]), 1, 'missing format')
    expect('U6 non-power-of-two picture', run(['pack', spec(out, 'u6.json', [{'name': 'a', 'png': 'npot.png', 'format': 'DXT1'}]),
                                               os.path.join(out, 'u6.txd')]), 1, 'powers of two', '48x32',
           absent=os.path.join(out, 'u6.txd'))
    expect('U7 invalid --name expression', run(['extract', os.path.join(out, 'good.txd'), os.path.join(out, 'x'), '--name', '(']),
           1, 'regular expression')

    # G: game data for the retail check of the test suite
    rc, o = run([os.path.join(out, 'g1')], tool=os.path.join(HERE, 'test_fetex.py'))
    check('G1 suite without game data: F1 / F2 SKIPPED with instructions, rest PASS', rc == 0 and 'SKIPPED' in o and ENV in o,
          o.strip().splitlines()[-1] if o.strip() else '')
    rc, o = run([os.path.join(out, 'g3'), '--game-data', os.path.join(out, 'nothing')], tool=os.path.join(HERE, 'test_fetex.py'))
    check('G2 --game-data folder missing: SKIP with the reason', rc == 0 and 'does not exist or is not a folder' in o,
          o.strip().splitlines()[0])
    noxbe = os.path.join(out, 'fake_noxbe', 'Data')
    os.makedirs(noxbe)
    rc, o = run([os.path.join(out, 'g4'), '--game-data', os.path.dirname(noxbe)], tool=os.path.join(HERE, 'test_fetex.py'))
    check('G3 --game-data without default.xbe: SKIP with the reason', rc == 0 and 'has no default.xbe' in o,
          o.strip().splitlines()[0])
    try:
        gd = gamedata.resolve(argv[argv.index('--game-data') + 1] if '--game-data' in argv else None)
    except gamedata.GameDataError:
        gd = None
    name = 'G4 modified Data\\Frontend.txd refused by the per-file hash check (suite FAILS, says why) [data]'
    if gd is None:
        print('SKIP %s' % name)
        RES.append((name, None))
    else:
        fake = os.path.join(out, 'fake_mod')
        os.makedirs(os.path.join(fake, 'Data'))
        shutil.copyfile(gd.path('default.xbe'), os.path.join(fake, 'default.xbe'))
        with open(os.path.join(fake, 'Data', 'Frontend.txd'), 'wb') as f:
            f.write(b'modified')
        try:
            rc, o = run([os.path.join(out, 'g5'), '--game-data', fake], tool=os.path.join(HERE, 'test_fetex.py'))
        finally:
            shutil.rmtree(fake, ignore_errors=True)
        check(name, rc == 1 and 'differs from the supported release' in o, str([l for l in o.splitlines() if 'F0' in l][:1]))

    # B: failed builds
    expect('B1 palette picture is another picture: refused, nothing written',
           run(['pack', spec(out, 'b1.json', [{'name': 'a', 'png': 'blocks.png', 'format': 'P8', 'palettes': ['other.png']}]),
                os.path.join(out, 'b1.txd')]), 1, 'does not map 1:1', absent=os.path.join(out, 'b1.txd'))
    expect('B2 entry larger than the front-end list: refused, nothing written',
           run(['pack', spec(out, 'b2.json', [{'name': 'a', 'png': 'big.png', 'format': 'DXT1'}]), os.path.join(out, 'b2.txd')]),
           1, 'outside 4..1024', absent=os.path.join(out, 'b2.txd'))
    os.makedirs(os.path.join(out, 'b3set'))
    expect('B3 make_packs into an existing folder', run([os.path.join(out, 'b3set')],
                                                        tool=os.path.join(TOOL, 'examples', 'fetex-art', 'make_packs.py')), 1,
           'exists', 'NEW folder')
    expect('B4 make_packs --cars2-files without the cars2 files', run([os.path.join(out, 'b4set'), '--cars2-files', out],
                                                                      tool=os.path.join(TOOL, 'examples', 'fetex-art', 'make_packs.py')),
           1, 'BM01.bgv', absent=os.path.join(out, 'b4set'))
    ran = [r for r in RES if r[1] is not None]
    good_n = sum(1 for r in ran if r[1])
    skipped = len(RES) - len(ran)
    print('fetex error tests: %d / %d PASS%s' % (good_n, len(ran), (', %d SKIPPED (no game data)' % skipped) if skipped else ''))
    return 0 if good_n == len(ran) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
