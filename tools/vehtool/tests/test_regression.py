r"""vehtool regression: this version rebuilds the content-phase veh example packs byte for byte.

  py -3 -B tests\test_regression.py OUT_DIR [--game-data DIR]

R1 examples\make_veh_packs.py OUT_DIR\veh = the content-phase packs (kit 0.4.0 staging, vehtool 0.1.1): every file of every
   pack (neon, dust, retail paints, cross, the 21 / 512 / 917 fixtures, the two negative fixtures, README.txt) byte for byte
R2 [data] vehtool validate: the 4 AUTHORED packs together are admitted; the negatives are refused for their reason
   (bad-dup with neon: the duplicate vehicle ID; bad-missing: the missing model files)
No game data is needed for R1 (the packs use model = donor); R2 is SKIPPED without it.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
import gamedata  # noqa: E402

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


def run(args):
    r = subprocess.run([sys.executable, '-B'] + [str(a) for a in args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = os.path.abspath(argv[1])
    os.makedirs(out)
    veh = os.path.join(out, 'veh')
    rc, o = run([os.path.join(TOOL, 'examples', 'make_veh_packs.py'), veh])
    t = tree(veh) if os.path.isdir(veh) else {}
    d = sorted(k for k in set(t) | set(REF['packs']) if t.get(k) != REF['packs'].get(k))
    check('R1 make_veh_packs.py: %d files = content-phase packs byte for byte' % len(REF['packs']), rc == 0 and not d,
          'rc %d differ %s %s' % (rc, d[:8], o[-200:]) if (rc or d) else '')
    try:
        gd = gamedata.resolve(argv[argv.index('--game-data') + 1] if '--game-data' in argv else None)
    except gamedata.GameDataError as e:
        gd = None
        print('SKIP R2 [data]: %s' % e)
    skipped = 0
    if gd is None:
        skipped = 3
    else:
        vt = os.path.join(TOOL, 'vehtool.py')
        authored = [os.path.join(veh, p) for p in ('bm-veh-neon', 'bm-veh-dust', 'bm-veh-retail-paints', 'bm-veh-cross')]
        rc, o = run([vt, 'validate'] + authored + ['--game-data', gd.root])
        check('R2 validate the 4 AUTHORED packs together: admitted [data]', rc == 0 and 'REFUSED' not in o,
              o.strip().splitlines()[-1] if o.strip() else '')
        rc, o = run([vt, 'validate', os.path.join(veh, 'bm-veh-neon'), os.path.join(veh, 'bm-veh-bad-dup'), '--game-data', gd.root])
        check('R2 bad-dup after neon: refused for the duplicate vehicle ID [data]', rc == 1 and 'vehicle ID exists' in o,
              [l for l in o.splitlines() if 'REFUSED' in l][:1])
        rc, o = run([vt, 'validate', os.path.join(veh, 'bm-veh-bad-missing'), '--game-data', gd.root])
        check('R2 bad-missing: refused for the missing model files [data]', rc == 1 and 'missing files/pveh/COMP/MS01.bgv' in o,
              [l for l in o.splitlines() if 'REFUSED' in l][:1])
    good = sum(1 for _, ok in RES if ok)
    print('vehtool regression: %d / %d PASS%s' % (good, len(RES), (', %d SKIPPED (no game data)' % skipped) if skipped else ''))
    return 0 if good == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
