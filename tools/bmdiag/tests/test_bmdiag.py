"""bmdiag tests: the exclusions and redactions are proven on a synthetic bundle that carries MARKER bytes in every place that must
not leave the machine (saves, progress, game data, mod file contents, environment values, user / computer names, e-mail).
    py -3 -B test_bmdiag.py OUT_DIR          (OUT_DIR must not exist; writes only there)   exit 0 = all checks passed
Python 3.8+, standard library only."""
import getpass
import io
import json
import os
import socket
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), 'bmdiag.py')
M = {k: ('BMDIAGMARK_%s_7f3a' % k).encode() for k in ('SAVE', 'PROG', 'GAME', 'MODFILE', 'ENV', 'SETTINGS_SAVE')}
USER = 'zz_tester_name'
EMAIL = 'someone.private@example.org'
COMPUTER = os.environ.get('COMPUTERNAME') or socket.gethostname()


def login():
    """the real login name, also in a minimal environment without USERNAME (getpass raises there)"""
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        p = os.path.expanduser('~')
        return os.path.basename(p) if p and p != '~' else 'nobody-known'


def w(p, b):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(b if isinstance(b, bytes) else b.encode('utf-8'))


def make_bundle(root):
    real_user = login()
    w(os.path.join(root, 'host', 'burnout3_gp_p4_4.exe'), b'MZ fake host')
    w(os.path.join(root, 'host', 'SDL2.dll'), b'MZ fake sdl')
    w(os.path.join(root, 'MANIFEST.json'), json.dumps({'bundle': 'test', 'path': 'C:\\Users\\%s\\Desktop\\b' % USER}))
    prof = os.path.join(root, 'profile', 'Roaming', 'BurnoutMashup')
    log = ['boot line %d' % i for i in range(600)]
    log[5] = '[PLATFORM] bmp-0.1.6 platform 0.1.6, 20 services'
    log[6] = '[ADMIT] bmashup.test refused: data at C:\\Users\\%s\\AppData\\Local\\x and C:\\Users\\%s\\y' % (USER, real_user)
    log[7] = '[MOD] mail %s on %s' % (EMAIL, COMPUTER)
    log[8] = 'FATAL something broke in %s' % os.path.join(root, 'host')
    w(os.path.join(prof, 'logs', 'run.log'), '\n'.join(log) + '\n')
    w(os.path.join(prof, 'UDATA', '4541005b', '0000000001', 'Profile 1'), M['SAVE'])
    w(os.path.join(prof, 'UDATA', '4541005b', '0000000001', 'SaveMeta.xbx'), M['SAVE'])
    w(os.path.join(prof, 'progress', 'bm.bmprog'), M['PROG'])
    w(os.path.join(prof, 'settings.toml'), 'graphics = 1\nuser_dir = "C:\\\\Users\\\\%s\\\\Documents"\n' % USER)
    w(os.path.join(prof, 'TDATA', 'x', 'settings.toml'), M['SETTINGS_SAVE'])
    gd = os.path.join(root, 'gamedata')
    w(os.path.join(gd, 'Burnout 3 Takedown', 'default.xbe'), M['GAME'] + b'xbe')
    w(os.path.join(gd, 'Burnout 3 Takedown', 'Tracks', 'tlist.bin'), M['GAME'])
    w(os.path.join(gd, '.complete'), b'ok')
    mod = os.path.join(root, 'mods', 'user', 'my-mod')
    w(os.path.join(mod, 'mod.toml'), 'id = "bmashup.my-mod"\nversion = "1.2.3"\nname = "My Mod"\n# author %s\n' % EMAIL)
    w(os.path.join(mod, 'files', 'Tracks', 'EU', 'T1_V1', 'static.dat'), M['MODFILE'])
    w(os.path.join(mod, 'state', 'UDATA', 'Profile 1'), M['SAVE'])          # a save copied into a mod folder: name never listed
    w(os.path.join(prof, 'logs', 'Profile 2.log'), M['SAVE'])             # a save-named file in the logs folder: never read
    w(os.path.join(root, 'diag', 'preflight.txt'), 'PASS python\nFAIL gpu at C:\\Users\\%s\\x\n' % USER)


def run_tool(args, extra_env=None):
    env = dict(os.environ, BMASHUP_SECRET_VALUE=M['ENV'].decode(), USERNAME=USER)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, '-B', TOOL] + args, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def zip_texts(p):
    with zipfile.ZipFile(p) as z:
        return {n: z.read(n) for n in z.namelist()}


def main(out):
    os.makedirs(out)
    bundle = os.path.join(out, 'bundle')
    make_bundle(bundle)
    res, n = [], 0

    def check(ok, what):
        res.append(('PASS ' if ok else 'FAIL ') + what)
        return ok

    for tag, extra in (('default', []), ('include-more', ['--include-more'])):
        z = os.path.join(out, 'export_%s.zip' % tag)
        rc, o = run_tool(['--bundle', bundle, '--data', os.path.join(bundle, 'gamedata'), '--out', z] + extra)
        check(rc == 0 and os.path.isfile(z), '%s: written (rc %d) %s' % (tag, rc, o[-200:] if rc else ''))
        if rc:
            continue
        T = zip_texts(z)
        blob = b'\n'.join(list(T.values()) + [k.encode() for k in T])
        for k, v in M.items():
            check(v not in blob, '%s: marker %s absent (saves / progress / game data / mod files / env values never exported)' % (tag, k))
        check(not any(x in n_.lower() for n_ in T for x in ('udata', 'tdata', 'savemeta', 'profile 1', '.bmprog')),
              '%s: no save / progress file name in the export' % tag)
        low = blob.lower()
        check(b'udata' not in low and b'profile 1' not in low and b'profile 2' not in low,
              '%s: no save file name inside any exported text (mod file lists, log list)' % tag)
        check(USER.encode().lower() not in low, '%s: the user name is redacted' % tag)
        check(login().encode().lower() not in low or len(login()) < 2, '%s: the real login name is redacted' % tag)
        check(EMAIL.encode() not in blob, '%s: the e-mail address is redacted' % tag)
        check(COMPUTER.encode().lower() not in low, '%s: the computer name is redacted' % tag)
        check(os.path.abspath(bundle).encode().lower() not in low, '%s: the bundle path is replaced by <bundle>' % tag)
        d = json.loads(T['diag.json'])
        check(d['env_names_set'] and 'BMASHUP_SECRET_VALUE' in d['env_names_set'], '%s: env variable NAMES listed (values not)' % tag)
        check(d['game_data']['default_xbe_found'] and not d['game_data']['ntsc_u'], '%s: game data reported by hash only' % tag)
        mods = [m for r in d['mods'] for m in r.get('mods', [])]
        check(len(mods) == 1 and mods[0].get('id') == 'bmashup.my-mod' and mods[0]['files'] and
              all('sha256' in f for f in mods[0]['files']), '%s: the mod listed with id, file names and hashes' % tag)
        key = [k for k in T if k.endswith('.key.txt')]
        kt = T[key[0]].decode() if key else ''
        check('[PLATFORM]' in kt and '[ADMIT]' in kt and 'FATAL' in kt and '<user>' in kt and '<email>' in kt,
              '%s: key log lines kept, redacted' % tag)
        check(any(k.startswith('preflight/') for k in T), '%s: preflight output included' % tag)
        full = [k for k in T if k.endswith('.full.txt')]
        check(bool(full) == (tag == 'include-more'), '%s: the whole log only with --include-more' % tag)
        prof = [k for k in T if k.startswith('profile/')]
        check((tag == 'include-more') == bool(prof) and not any('tdata' in k.lower() for k in prof),
              '%s: profile settings only with --include-more, never from a save folder' % tag)
    # usage errors write nothing
    rc, o = run_tool(['--out', os.path.join(out, 'x.zip')])
    check(rc == 2 and not os.path.exists(os.path.join(out, 'x.zip')), 'usage error without --bundle: exit 2, nothing written')
    rc, o = run_tool(['--bundle', os.path.join(out, 'nope'), '--out', os.path.join(out, 'y.zip')])
    check(rc == 2 and 'not a folder' in o, 'a missing bundle folder: exit 2 with the reason')
    rc, o = run_tool(['--bundle', bundle, '--out', os.path.join(out, 'export_default.zip')])
    check(rc == 2 and 'exists' in o, 'an existing output is never overwritten')
    fails = sum(1 for r in res if r.startswith('FAIL'))
    res.append('RESULT %s (%d checks, %d failed)' % ('PASS' if not fails else 'FAIL', len(res), fails))
    with io.open(os.path.join(out, 'RESULTS.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(res) + '\n')
    print('\n'.join(res))
    return 1 if fails else 0


MUTANTS = [   # each deliberate defect in a COPY of bmdiag.py must make the base checks fail
    ('saves not excluded', 'def is_save(path):\n    return any(', 'def is_save(path):\n    return False and any('),
    ('no redaction', '    def __call__(self, text):\n', '    def __call__(self, text):\n        return text\n'),
    ('mod files copied', "                info['files'].append({'name': red(rel), 'size'",
     "                info.setdefault('raw', []).append(open(p, 'rb').read().decode('latin-1'))\n"
     "                info['files'].append({'name': red(rel), 'size'"),
    ('environment values exported', "    rep['env_names_set'] = sorted(k for k in os.environ if k.upper().startswith(ENV_PREFIX))",
     "    rep['env_names_set'] = sorted(k + '=' + os.environ[k] for k in os.environ if k.upper().startswith(ENV_PREFIX))"),
]


def mutants(out):
    global TOOL
    orig, lines, ok = TOOL, [], True
    src = io.open(orig, encoding='utf-8').read()
    for i, (name, old, new) in enumerate(MUTANTS):
        assert src.count(old) == 1, name
        d = os.path.join(out, 'mut%d' % i)
        os.makedirs(d)
        TOOL = os.path.join(d, 'bmdiag.py')
        with io.open(TOOL, 'w', encoding='utf-8', newline='\n') as f:
            f.write(src.replace(old, new))
        with open(os.devnull, 'w') as dn:
            so = sys.stdout
            sys.stdout = dn
            try:
                rc = main(os.path.join(d, 'run'))
            finally:
                sys.stdout = so
        lines.append('MUT %d (%s): %s' % (i, name, 'CAUGHT' if rc else 'NOT CAUGHT'))
        ok &= rc != 0
    TOOL = orig
    lines.append('MUTANTS %s' % ('PASS' if ok else 'FAIL'))
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    rc = main(sys.argv[1])
    if '--mutants' in sys.argv:
        rc |= mutants(os.path.join(sys.argv[1], 'mutants'))
    sys.exit(rc)
