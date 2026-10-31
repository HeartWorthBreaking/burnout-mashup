r"""p4.3 fix 1 (item 3): vehtool's mod.toml limit = 65536 bytes (p4.3 decision). Boundary tests into a NEW folder.

  py -3 -B test_vehtool_limit.py OUT_DIR [--game-data DIR] [--vehtool PATH]

Game data (validate reads the retail vehicle list): --game-data DIR or the BMKIT_GAME_DATA environment variable; without it
the suite is SKIPPED with the reason (exit 0, verdict SKIPPED - not a pass). Portable vehtool 0.1.2 (suite of mod kit 0.4.0).

Checks: a valid series mod padded to exactly 65536 bytes is accepted by `validate`, the same mod at 65537 bytes is REFUSED with
the manifest reason, 8193 (refused by 0.1.0) is accepted; `fixture --cars 917` writes 2 parts, each <= 65536 bytes, that
validate together (917 cars, entries 1024). Mutant runs: the same checks against a vehtool copy with the 0.1.0 limit (8192)
and against one with an off-by-one (>=) must FAIL.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

VEHTOOL = pathlib.Path(__file__).resolve().parents[1] / 'vehtool.py'   # the tool beside this test (package-relative)
sys.path.insert(0, str(VEHTOOL.parent))
import gamedata  # noqa: E402
GAME = None                                                            # set in main(): the resolved game-data folder

BASE = '''id = "bmashup.limit-test"
name = "limit test"
version = "1.0.0"

[bmashup]
platform = ">=0.1.5"

[bmashup.series]
version = 1
add = ["lim = BMLT"]
names = ["lim = Limit Test"]
ai_class = ["lim = SPRT"]

[bmashup.cars]
version = 2
add = ["BMLTC01 = SPRTCAR1"]
model = ["BMLTC01 = donor"]
'''


def padded(n):
    b = BASE.encode()
    pad = n - len(b)
    out = b
    while pad > 0:                                   # comment lines of <= 100 bytes
        k = min(pad, 100)
        line = (b'#' + b'x' * (k - 2) + b'\n') if k >= 2 else b'\n'
        out += line
        pad -= len(line)
    assert len(out) == n
    return out


def run(tool, args):
    if args and args[0] == 'validate':
        args = list(args) + ['--game-data', GAME]
    r = subprocess.run([sys.executable, '-B', str(tool)] + [str(a) for a in args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def suite(tool, out):
    res = []

    def check(ok, what):
        res.append(('PASS ' if ok else 'FAIL ') + what)

    for n, want in ((65536, 0), (65537, 1), (8193, 0)):
        d = out / ('m%d' % n)
        d.mkdir()
        (d / 'mod.toml').write_bytes(padded(n))
        rc, txt = run(tool, ['validate', d])
        ref = 'REFUSED' in txt and 'mod.toml has %d bytes' % n in txt and '65536' in txt
        check(rc == want and (ref if want else 'REFUSED' not in txt),
              'validate mod.toml of %d bytes: rc %d (want %d)%s' % (n, rc, want, ' refused for the size' if ref else ''))
    fx = out / 'fixture917'
    rc, txt = run(tool, ['fixture', fx, '--cars', '917', '--id', 'bmashup.limit-fixture'])
    parts = sorted(p for p in fx.iterdir() if p.is_dir()) if fx.exists() else []
    sizes = [(p / 'mod.toml').stat().st_size for p in parts]
    check(rc == 0 and len(parts) == 2 and all(s <= 65536 for s in sizes),
          'fixture 917 cars: rc %d, %d parts, mod.toml sizes %s (each <= 65536)' % (rc, len(parts), sizes))
    if parts:
        rc, txt = run(tool, ['validate'] + parts)
        check(rc == 0 and 'REFUSED' not in txt, 'validate the 917 fixture parts together: rc %d (%s)' %
              (rc, txt.strip().splitlines()[-1] if txt.strip() else ''))
    return res


def main(argv):
    global GAME
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = pathlib.Path(argv[1]).resolve()
    tool = pathlib.Path(argv[argv.index('--vehtool') + 1]) if '--vehtool' in argv else VEHTOOL
    try:
        gd = gamedata.resolve(argv[argv.index('--game-data') + 1] if '--game-data' in argv else None)
        gd.read('pveh/vlist.bin')                                      # hash check before the suite relies on it
        GAME = gd.root
    except gamedata.GameDataError as e:
        print(json.dumps({'vehtool': str(tool), 'verdict': 'SKIPPED', 'reason': str(e)}, indent=1))
        print('vehtool limit tests: SKIPPED (no usable game data: pass --game-data DIR or set %s)' % gamedata.ENV)
        return 0
    out.mkdir(parents=True, exist_ok=False)
    summary = {'vehtool': str(tool)}
    (out / 'base').mkdir()
    base = suite(tool, out / 'base')
    summary['base'] = base
    src = tool.read_text(encoding='utf-8')
    muts = {'M1_limit_8192': src.replace('MANIFEST_MAX = 65536', 'MANIFEST_MAX = 8192', 1),
            'M2_off_by_one': src.replace("'mod.toml')) > MANIFEST_MAX", "'mod.toml')) >= MANIFEST_MAX", 1)}
    caught = 0
    for name, text in muts.items():
        if text == src:
            summary[name] = 'MUTATION NOT APPLIED'
            continue
        mt = out / (name + '_vehtool.py')
        mt.write_text(text, encoding='utf-8')
        for dep in ('gamedata.py', 'GAMEDATA_SHA256.json'):          # the mutant's package-relative dependencies
            if not (out / dep).exists():
                shutil.copyfile(tool.parent / dep, out / dep)
        (out / name).mkdir()
        r = suite(mt, out / name)
        summary[name] = r
        caught += any(x.startswith('FAIL') for x in r)
    ok = all(x.startswith('PASS') for x in base) and caught == len(muts)
    summary['mutants_caught'] = '%d / %d' % (caught, len(muts))
    summary['verdict'] = 'PASS' if ok else 'FAIL'
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    print('vehtool limit tests: %s (%d / %d base checks PASS, mutants caught %s)' % (
        summary['verdict'], sum(x.startswith('PASS') for x in base), len(base), summary['mutants_caught']))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
