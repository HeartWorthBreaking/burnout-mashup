r"""carimport regression: this version rebuilds the content-phase outputs byte for byte.

  py -3 -B tests\test_regression.py OUT_DIR [--game-data DIR]

R1 the vendored strict reader carimp\bgvlib.py is the s6 original (sha256 pinned)
R2 `demo coupe` / `demo wedge` regenerate the shipped examples\ (glTF, .bin, PNGs, car.toml) byte for byte, and both equal
   the content-phase demo sources (tests\REGRESSION_SHA256.json "demo")
R3 [data] `package examples\coupe\car.toml` and `examples\wedge\car.toml` = the content-phase packages carimp-coupe /
   carimp-wedge, every file byte for byte (REGRESSION_SHA256.json "packages"; needs the same donor data: COMPCAR1)
OUT_DIR must not exist; the packages written there are DERIVED (donor parts): LOCAL ONLY, delete them after the check.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
from carimp import bgvwrite, gamedata  # noqa: E402

REF = json.load(open(os.path.join(HERE, 'REGRESSION_SHA256.json'), encoding='utf-8'))
RES = []


def check(name, ok, detail=''):
    RES.append((name, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + str(detail)[:300]) if detail else ''), flush=True)


def tree(d):
    out = {}
    for root, _, fs in os.walk(d):
        for n in fs:
            p = os.path.join(root, n)
            out[os.path.relpath(p, d).replace('\\', '/')] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    return out


def diff(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def run(*a):
    r = subprocess.run([sys.executable, '-B', os.path.join(TOOL, 'carimport.py')] + [str(x) for x in a],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


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
        print('SKIP (game data) for R3: %s' % e)
    h = hashlib.sha256(open(os.path.join(TOOL, 'carimp', 'bgvlib.py'), 'rb').read()).hexdigest()
    check('R1 vendored bgvlib.py = s6 original', h == bgvwrite.BGVLIB_SHA == bgvwrite.bgvlib_sha(), h)
    for car in ('coupe', 'wedge'):
        d = os.path.join(out, 'demo_' + car)
        rc, o = run('demo', car, d)
        t = tree(d)
        dd = diff(t, tree(os.path.join(TOOL, 'examples', car)))
        dr = diff(t, REF['demo'][car])
        check('R2 demo %s = shipped examples\\%s = content-phase sources' % (car, car), rc == 0 and not dd and not dr,
              'rc %d differ shipped %s content %s' % (rc, dd, dr) if (rc or dd or dr) else '%d files' % len(t))
    if gd is None:
        print('SKIP R3 [data] (2 packages)')
        skipped = 2
    else:
        skipped = 0
        st = os.path.join(out, 'set')
        for car in ('coupe', 'wedge'):
            rc, o = run('package', os.path.join(TOOL, 'examples', car, 'car.toml'), st, '--game-data', gd.root)
            t = tree(os.path.join(st, 'carimp-' + car))
            dr = diff(t, REF['packages']['carimp-' + car])
            check('R3 package %s = content-phase carimp-%s byte for byte [data]' % (car, car), rc == 0 and not dr,
                  ('rc %d %s differ %s' % (rc, o[-300:], dr)) if (rc or dr) else '%d files, %s' % (
                      len(t), ', '.join('%s %s' % (k.split('/')[-1], v[:12]) for k, v in sorted(t.items()) if k.endswith('.bgv'))))
    good = sum(1 for _, ok in RES if ok)
    print('carimport regression: %d / %d PASS%s' % (good, len(RES), (', %d SKIPPED (no game data)' % skipped) if skipped else ''))
    return 0 if good == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
