r"""fetex regression: this version rebuilds the content-phase art packs byte for byte (no game data needed).

  py -3 -B tests\test_regression.py OUT_DIR [--cars2-files DIR]

R1 examples\fetex-art\make_packs.py OUT_DIR\set: gen_art.py art (every PNG) = the content-phase art; photo.txd / oceania.txd =
   the runtime-validated TXDs; the packs fetex-photo and fetex-oceania-art = the content-phase packs, every file byte for byte
R2 fetex pack examples\p43-coupe-photo\photo_spec.json = the p4.3 coupe photo TXD
R3 (optional, --cars2-files DIR) the DERIVED fetex-car-photo pack = the content-phase pack (local only)
OUT_DIR must not exist. References: tests\REGRESSION_SHA256.json.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REF = json.load(open(os.path.join(HERE, 'REGRESSION_SHA256.json'), encoding='utf-8'))
RES = []


def check(name, ok, detail=''):
    RES.append((name, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + str(detail)[:300]) if detail else ''), flush=True)


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def tree(d, skip=()):
    out = {}
    for root, _, fs in os.walk(d):
        for n in fs:
            rel = os.path.relpath(os.path.join(root, n), d).replace('\\', '/')
            if rel not in skip:
                out[rel] = sha(os.path.join(root, n))
    return out


def diff(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def run(args):
    r = subprocess.run([sys.executable, '-B'] + [str(a) for a in args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = os.path.abspath(argv[1])
    os.makedirs(out)
    cars2 = argv[argv.index('--cars2-files') + 1] if '--cars2-files' in argv else None
    st, art = os.path.join(out, 'set'), os.path.join(out, 'art')
    args = [os.path.join(TOOL, 'examples', 'fetex-art', 'make_packs.py'), st, '--art', art]
    if cars2:
        args += ['--cars2-files', cars2]
    rc, o = run(args)
    check('R1 make_packs.py ran', rc == 0, o.strip().splitlines()[-1] if o.strip() else '')
    d = diff(tree(art, skip=('photo.txd', 'oceania.txd', 'photo.json', 'oceania.json')), REF['art'])
    check('R1 gen_art: %d AUTHORED PNGs = content-phase art byte for byte' % len(REF['art']), not d, d[:6])
    for t in ('photo.txd', 'oceania.txd'):
        p = os.path.join(art, t)
        check('R1 %s = content-phase TXD' % t, os.path.isfile(p) and sha(p) == REF['txd'][t], sha(p)[:16] if os.path.isfile(p) else 'missing')
    for k in ('fetex-photo', 'fetex-oceania-art'):
        d = diff(tree(os.path.join(st, k)), REF['packs'][k])
        check('R1 pack %s = content-phase pack (every file)' % k, not d, d)
    p43 = os.path.join(out, 'p43_photo.txd')
    rc, o = run([os.path.join(TOOL, 'fetex.py'), 'pack', os.path.join(TOOL, 'examples', 'p43-coupe-photo', 'photo_spec.json'), p43])
    check('R2 p43 coupe photo TXD = content-phase TXD', rc == 0 and os.path.isfile(p43) and sha(p43) == REF['txd']['p43_photo.txd'],
          o.strip())
    if cars2:
        d = diff(tree(os.path.join(st, 'fetex-car-photo')), REF['packs']['fetex-car-photo'])
        check('R3 DERIVED pack fetex-car-photo = content-phase pack (local only)', not d, d)
    else:
        print('SKIP R3 (optional: --cars2-files DIR)')
    good = sum(1 for _, ok in RES if ok)
    print('fetex regression: %d / %d PASS' % (good, len(RES)))
    return 0 if good == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
