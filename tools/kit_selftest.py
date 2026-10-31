"""kit_selftest 0.1.0 (mod kit 0.4.1) - run every test suite of the kit FROM the kit, with your prerequisites. Read only except
OUT_DIR. Replaces kit 0.4.0's stage_verify.py (which compared against the developer workspace).

    py -3 -B tools\\kit_selftest.py OUT_DIR [--game-data DIR] [--cc FILE] [--quick]
                                   [--sdk --llvm-mingw DIR --cmake EXE --ninja EXE]
Suites: every tools\\<tool>\\tests\\SELFTEST.json ({"suites": [{"name", "command": [...], "needs": [...], "slow": bool}]}; command
tokens {py} {out} {game} {cc} {kit} {tool} are filled in; needs: "game_data", "cc"). A suite whose needs are not met is SKIPPED with
the reason (never counted as passed). --quick skips suites marked slow. --sdk rebuilds the SDK examples with sdk\\build.ps1 into
OUT_DIR\\sdk_build and compares every output with sdk\\EXPECTED_BUILD_SHA256.txt (another toolchain version may differ: reported).
Static checks: SHA256SUMS_kit.txt (when present) matches every file.
Exit 0 = everything that ran passed; 1 = a failure; 3 = a prerequisite given on the command line is wrong."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, '_lib'))
import bmkit_env as E  # noqa: E402

VERSION = '0.1.0'


def opt(argv, name):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else None
    return None


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sums_check():
    p = os.path.join(KIT, 'SHA256SUMS_kit.txt')
    if not os.path.isfile(p):
        return 'SKIPPED', 'no SHA256SUMS_kit.txt (a source checkout, not the kit zip)'
    bad = []
    n = 0
    for ln in open(p, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if not ln or ln.startswith('#'):
            continue
        h, rel = ln.split('  ', 1)
        n += 1
        f = os.path.join(KIT, *rel.split('/'))
        if not os.path.isfile(f) or sha(f) != h:
            bad.append(rel)
    return ('PASS' if not bad else 'FAIL'), '%d files, %d differ %s' % (n, len(bad), bad[:5])


def main(argv):
    if not argv or argv[0].startswith('--'):
        print(__doc__)
        return 2
    out = os.path.abspath(argv[0])
    if os.path.exists(out) and os.listdir(out):
        print('kit_selftest: %s exists and is not empty: give a new folder' % out)
        return 2
    os.makedirs(out, exist_ok=True)
    have = {}
    try:
        E.check_python()
        if opt(argv, '--game-data') or os.environ.get('BMKIT_GAME_DATA') or E.config().get('game_data'):
            have['game'] = E.game_data(opt(argv, '--game-data'), what='kit_selftest')
        try:
            have['cc'] = E.find_cc(opt(argv, '--cc'), what='kit_selftest')
        except E.BmkitError as e:
            if opt(argv, '--cc'):
                raise
            have['cc_why'] = str(e)
    except E.BmkitError as e:
        return E.report_error('kit_selftest', e)
    rows = [('static', 'SHA256SUMS_kit') + sums_check()]
    quick = '--quick' in argv
    for tool in sorted(os.listdir(HERE)):
        sj = os.path.join(HERE, tool, 'tests', 'SELFTEST.json')
        if tool.startswith('_') and tool != '_lib':
            continue
        if not os.path.isfile(sj):
            if os.path.isdir(os.path.join(HERE, tool, 'tests')):
                rows.append(('suite', tool, 'SKIPPED', 'no tests\\SELFTEST.json: run its tests by hand (README)'))
            continue
        for s in json.load(open(sj, encoding='utf-8'))['suites']:
            name = '%s:%s' % (tool, s['name'])
            miss = [n for n in s.get('needs', []) if not have.get({'game_data': 'game', 'cc': 'cc'}[n])]
            if miss:
                rows.append(('suite', name, 'SKIPPED', 'needs %s (give %s)' % (', '.join(miss), ', '.join(
                    {'game_data': '--game-data', 'cc': '--cc or llvm-mingw on PATH'}[m] for m in miss))))
                continue
            if quick and s.get('slow'):
                rows.append(('suite', name, 'SKIPPED', '--quick (slow suite)'))
                continue
            sout = os.path.join(out, re.sub(r'[^A-Za-z0-9._-]+', '_', name)[:60])
            cmd = [t.format(py=sys.executable, out=sout, game=have.get('game', ''), cc=have.get('cc', ''), kit=KIT,
                            tool=os.path.join(HERE, tool)) for t in s['command']]
            t0 = time.time()
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.join(HERE, tool))
            with open(sout + '.log', 'w', encoding='utf-8') as f:
                f.write(' '.join(cmd) + '\n' + r.stdout + r.stderr)
            last = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()][-1:] or ['']
            rows.append(('suite', name, 'PASS' if r.returncode == 0 else 'FAIL', '%s (%.0f s, rc %d)' % (last[0][:150], time.time() - t0, r.returncode)))
    if '--sdk' in argv:
        bd = os.path.join(out, 'sdk_build')
        cmd = ['powershell', '-NoProfile', '-File', os.path.join(KIT, 'sdk', 'build.ps1'), '-BuildDir', bd]
        for o, p in (('--llvm-mingw', '-LlvmMingw'), ('--cmake', '-CMake'), ('--ninja', '-Ninja')):
            if opt(argv, o):
                cmd += [p, opt(argv, o)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        with open(os.path.join(out, 'sdk_build.log'), 'w', encoding='utf-8') as f:
            f.write(r.stdout + r.stderr)
        if r.returncode == 3:
            rows.append(('sdk', 'build', 'SKIPPED', 'prerequisite missing: %s' % r.stderr.strip()[-200:]))
        elif r.returncode:
            rows.append(('sdk', 'build', 'FAIL', 'rc %d (sdk_build.log)' % r.returncode))
        else:
            exp = {}
            for ln in open(os.path.join(KIT, 'sdk', 'EXPECTED_BUILD_SHA256.txt'), encoding='utf-8'):
                if ln.strip() and not ln.startswith('#'):
                    h, rel = ln.split(None, 1)
                    exp[rel.strip().replace('\\', '/')] = h
            got = {}
            od = os.path.join(bd, 'out')
            for root, _, fs in os.walk(od):
                for n in fs:
                    if n.endswith(('.asi', '.toml')):
                        got[os.path.relpath(os.path.join(root, n), od).replace('\\', '/')] = sha(os.path.join(root, n))
            same = sorted(k for k in exp if got.get(k) == exp[k])
            diff = sorted(k for k in exp if k in got and got[k] != exp[k])
            miss = sorted(k for k in exp if k not in got)
            rows.append(('sdk', 'build = EXPECTED_BUILD_SHA256', 'PASS' if not diff and not miss else 'FAIL',
                         '%d / %d identical, %d differ %s, %d missing %s' % (len(same), len(exp), len(diff), diff[:4], len(miss), miss[:4])))
    fails = [r for r in rows if r[2] == 'FAIL']
    lines = ['kit_selftest %s (mod kit %s) at %s' % (VERSION, E.KIT_VERSION, '<kit>')]
    lines += ['%-7s %-44s %-8s %s' % r for r in rows]
    lines.append('RESULT %s (%d ran, %d skipped, %d failed)' % ('PASS' if not fails else 'FAIL',
                 sum(1 for r in rows if r[2] in ('PASS', 'FAIL')), sum(1 for r in rows if r[2] == 'SKIPPED'), len(fails)))
    with open(os.path.join(out, 'SELFTEST.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
