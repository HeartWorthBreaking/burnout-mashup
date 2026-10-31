"""bmdiag 0.1.0 - Burnout Mashup diagnostic export (alpha). Stand-alone, Python 3.8+ standard library only, no network.

Collects what a bug report needs and nothing personal:
  versions / hashes   bmdiag, Python, Windows, the host folder's .exe / .dll (sha256, size), the bundle's MANIFEST / VERSION files
  system summary      GPU name + driver (Windows CIM, best effort), the Vulkan loader (vulkan-1.dll present, size / sha256)
  mods                every mod folder in the mods folders: id / version / name / label lines of mod.toml, its file NAMES with
                      sha256 and size (never the files themselves)
  logs                the host log(s) (<profile>\\Roaming\\BurnoutMashup\\logs\\*.log): the key lines ([PLATFORM] [ADMIT] [DEPS] [MOD]
                      [PLUGIN] [VEH] [CARS] [FETEX] FATAL GUEST error ...) + the last 400 lines; redacted
  preflight           the preflight output if present (<bundle>\\diag\\preflight*.txt or --preflight FILE); redacted
  game data           ONLY whether it is present and the sha256 of default.xbe (the NTSC-U check); no game file is copied
EXCLUDED always: saves and progress (UDATA, TDATA, SaveMeta.xbx, "Profile N", *.bmprog, *.sav), game data / extracted assets,
mod file contents, environment values (only the NAMES of TAKEDAWN_ / BMASHUP_ / RECOMP_ / BO3_ variables are listed).
REDACTED always: your user name, home folder, computer name, e-mail addresses, the bundle path (-> <user>, <home>, <computer>,
<email>, <bundle>).
--include-more (opt-in): the WHOLE logs (still redacted, each capped at 8 MiB), the text of each mod's mod.toml (redacted), the
settings / approvals TOML files of the profile (redacted). Saves, progress and game data stay excluded.

    py -3 -B bmdiag.py --bundle <root> [--profile <dir>] [--data <game data root>] [--mods <dir>;<dir>] [--log FILE]
                       [--preflight FILE] [--include-more] --out <file.zip | folder>
Prints every file put into the export; exit 0 written, 2 usage error (nothing written)."""
import argparse
import datetime
import getpass
import hashlib
import io
import json
import os
import platform
import re
import socket
import subprocess
import sys
import zipfile

VERSION = '0.1.0'
KEY = re.compile(r'(\[(PLATFORM|ADMIT|DEPS|MOD|MODS|PLUGIN|VEH|CARS|FETEX|SERIES|PAINTS|TRACKS|WT|WT4|XEVENTS|MUSIC|TUNE|SETTINGS|'
                 r'CAMERA|AUTOPILOT|CC|NAMES|REGIONS|PROGRESS|ENGINE|STREAM)\]|FATAL|GUEST|error|failed|refused|exception)', re.I)
SAVE_NAME = re.compile(r'^(UDATA|TDATA|SaveMeta\.xbx|Profile \d+.*|.*\.bmprog|.*\.sav|save-before-import)$', re.I)
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
USERS_PATH = re.compile(r'([A-Za-z]:[\\/]+Users[\\/]+)(?!Public\b)([^\\/\s"\']+)', re.I)
ENV_PREFIX = ('TAKEDAWN_', 'BMASHUP_', 'RECOMP_', 'BO3_', 'BMKIT_')
LOG_TAIL = 400
CAP = 8 << 20


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


class Redactor:
    def __init__(self, bundle):
        self.pairs = []
        for val, tag in ((bundle, '<bundle>'), (os.path.expanduser('~'), '<home>')):
            if val and len(val) > 3:
                self.pairs.append((os.path.normpath(val), tag))
        names = set()
        for f in (getpass.getuser, lambda: os.environ.get('USERNAME', ''), lambda: os.environ.get('USER', '')):
            try:
                n = f()
            except Exception:  # noqa: BLE001
                n = ''
            if n and len(n) > 1:
                names.add(n)
        self.users = sorted(names, key=len, reverse=True)
        comp = set()
        for f in (socket.gethostname, lambda: os.environ.get('COMPUTERNAME', ''), platform.node):
            try:
                n = f()
            except Exception:  # noqa: BLE001
                n = ''
            if n and len(n) > 1:
                comp.add(n)
        self.computers = sorted(comp, key=len, reverse=True)

    def __call__(self, text):
        for val, tag in sorted(self.pairs, key=lambda p: len(p[0]), reverse=True):
            for v in {val, val.replace('\\', '/'), val.replace('\\', '\\\\')}:
                text = re.sub(re.escape(v), tag, text, flags=re.I)
        text = USERS_PATH.sub(lambda m: m.group(1) + '<user>', text)
        text = EMAIL.sub('<email>', text)
        for n in self.users:
            text = re.sub(r'(?<![A-Za-z0-9])%s(?![A-Za-z0-9])' % re.escape(n), '<user>', text, flags=re.I)
        for n in self.computers:
            text = re.sub(r'(?<![A-Za-z0-9])%s(?![A-Za-z0-9])' % re.escape(n), '<computer>', text, flags=re.I)
        return text


def is_save(path):
    return any(SAVE_NAME.match(part) for part in re.split(r'[\\/]', path))


def read_text(path, cap=CAP):
    with open(path, 'rb') as f:
        b = f.read(cap + 1)
    t = b[:cap].decode('utf-8', 'replace')
    if len(b) > cap:
        t += '\n[bmdiag: cut at %d bytes]\n' % cap
    return t


def mod_info(d, red, more):
    info = {'folder': red(os.path.basename(d)), 'files': []}
    mt = os.path.join(d, 'mod.toml')
    if os.path.isfile(mt):
        t = read_text(mt, 256 << 10)
        for k in ('id', 'version', 'name', 'label'):
            m = re.search(r'^\s*%s\s*=\s*"([^"]*)"' % k, t, re.M)
            if m:
                info[k] = red(m.group(1))
        if more:
            info['mod_toml'] = red(t)
    for root, dirs, files in os.walk(d):
        dirs[:] = sorted(x for x in dirs if not is_save(x))
        for n in sorted(files):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, d).replace('\\', '/')
            if is_save(rel):
                continue
            try:
                info['files'].append({'name': red(rel), 'size': os.path.getsize(p), 'sha256': sha256(p)})
            except OSError as e:
                info['files'].append({'name': red(rel), 'error': str(e)})
    return info


def gpu_summary():
    if os.name != 'nt':
        return {'note': 'not Windows'}
    out = {}
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                            'Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion | ConvertTo-Json -Compress'],
                           capture_output=True, text=True, timeout=30)
        out['gpus'] = json.loads(r.stdout) if r.stdout.strip() else []
    except Exception as e:  # noqa: BLE001
        out['gpus_error'] = type(e).__name__
    vk = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'vulkan-1.dll')
    out['vulkan_loader'] = {'present': os.path.isfile(vk)}
    if os.path.isfile(vk):
        out['vulkan_loader'].update(size=os.path.getsize(vk), sha256=sha256(vk))
    return out


def collect(a):
    bundle = os.path.abspath(a.bundle) if a.bundle else ''
    red = Redactor(bundle)
    files = {}          # name in the export -> text
    rep = {'bmdiag': VERSION, 'created_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'include_more': bool(a.include_more), 'python': platform.python_version(),
           'os': red('%s %s (%s)' % (platform.system(), platform.version(), platform.machine()))}
    # versions / hashes
    rep['host_files'] = []
    for hdn in ('host', 'host-local'):
        host = os.path.join(bundle, hdn) if bundle else None
        if host and os.path.isdir(host):
            for n in sorted(os.listdir(host)):
                p = os.path.join(host, n)
                if os.path.isfile(p) and n.lower().endswith(('.exe', '.dll')):
                    rep['host_files'].append({'name': hdn + '\\' + n, 'size': os.path.getsize(p), 'sha256': sha256(p)})
    rep['host_selector'] = os.environ.get('BMASHUP_HOST', '') if os.environ.get('BMASHUP_HOST', '').lower() in ('', 'prebuilt', 'local') else 'invalid'
    rep['bundle_files'] = {}
    if bundle and os.path.isdir(bundle):
        for n in sorted(os.listdir(bundle)):
            p = os.path.join(bundle, n)
            if os.path.isfile(p) and re.match(r'^(MANIFEST.*\.json|VERSION.*|SHA256SUMS.*\.txt)$', n, re.I):
                rep['bundle_files'][n] = {'size': os.path.getsize(p), 'sha256': sha256(p)}
                if os.path.getsize(p) <= (512 << 10):
                    files['bundle/' + n] = red(read_text(p))
    rep['system'] = gpu_summary()
    rep['env_names_set'] = sorted(k for k in os.environ if k.upper().startswith(ENV_PREFIX))
    # game data: presence + default.xbe hash only
    if a.data:
        d = a.data
        xbe = None
        for cand in (os.path.join(d, 'default.xbe'), os.path.join(d, 'Burnout 3 Takedown', 'default.xbe')):
            if os.path.isfile(cand):
                xbe = cand
                break
        rep['game_data'] = {'given': True, 'default_xbe_found': bool(xbe), 'complete_marker': os.path.isfile(os.path.join(d, '.complete'))}
        if xbe:
            h = sha256(xbe)
            rep['game_data'].update(default_xbe_sha256=h,
                                    ntsc_u=h == '9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9')
    # mods
    mods_dirs = [m for m in (a.mods.split(';') if a.mods else []) if m]
    if not mods_dirs and bundle:
        mods_dirs = [os.path.join(bundle, 'mods', x) for x in ('demo', 'generated', 'user')]
    rep['mods'] = []
    for md in mods_dirs:
        if not os.path.isdir(md):
            rep['mods'].append({'root': red(md), 'missing': True})
            continue
        entry = {'root': red(md), 'mods': []}
        for n in sorted(os.listdir(md)):
            p = os.path.join(md, n)
            if os.path.isdir(p) and not is_save(n):
                entry['mods'].append(mod_info(p, red, a.include_more))
        rep['mods'].append(entry)
    # logs
    profile = a.profile or (os.path.join(bundle, 'profile') if bundle else None)
    logs = list(a.log or [])
    if profile:
        ld = os.path.join(profile, 'Roaming', 'BurnoutMashup', 'logs')
        if os.path.isdir(ld):
            logs += [os.path.join(ld, n) for n in sorted(os.listdir(ld)) if n.lower().endswith(('.log', '.txt'))]
    rep['logs'] = []
    for i, lp in enumerate(logs):
        if is_save(lp):
            rep['logs'].append({'name': '<a save-named file>', 'skipped': 'save / progress names are never read'})
            continue
        if not os.path.isfile(lp):
            rep['logs'].append({'name': red(lp), 'skipped': 'missing'})
            continue
        t = red(read_text(lp))
        lines = t.splitlines()
        key = [ln for ln in lines if KEY.search(ln)]
        base = 'logs/%02d_%s' % (i, re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(lp)))
        files[base + '.key.txt'] = '\n'.join(key) + '\n'
        files[base + '.tail.txt'] = '\n'.join(lines[-LOG_TAIL:]) + '\n'
        if a.include_more:
            files[base + '.full.txt'] = t
        rep['logs'].append({'name': red(lp), 'lines': len(lines), 'key_lines': len(key), 'sha256': sha256(lp)})
    # preflight
    pf = list(a.preflight or [])
    if bundle and os.path.isdir(os.path.join(bundle, 'diag')):
        pf += [os.path.join(bundle, 'diag', n) for n in sorted(os.listdir(os.path.join(bundle, 'diag')))
               if n.lower().startswith('preflight') and n.lower().endswith(('.txt', '.log', '.json'))]
    for i, p in enumerate(pf):
        if os.path.isfile(p) and not is_save(p):
            files['preflight/%02d_%s' % (i, re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(p)))] = red(read_text(p, 2 << 20))
    # opt-in: profile settings / approvals (TOML / INI / JSON text only, never saves)
    if a.include_more and profile and os.path.isdir(profile):
        for root, dirs, fs in os.walk(profile):
            dirs[:] = sorted(x for x in dirs if not is_save(x) and x.lower() not in ('logs', 'shadercache', 'cache'))
            for n in sorted(fs):
                rel = os.path.relpath(os.path.join(root, n), profile).replace('\\', '/')
                if is_save(rel) or not n.lower().endswith(('.toml', '.ini', '.cfg', '.json', '.txt')):
                    continue
                if os.path.getsize(os.path.join(root, n)) <= (1 << 20):
                    files['profile/' + red(rel)] = red(read_text(os.path.join(root, n)))
    files['diag.json'] = json.dumps(rep, indent=1, sort_keys=True) + '\n'
    summary = ['bmdiag %s export (%s)' % (VERSION, rep['created_utc']), 'python %s, %s' % (rep['python'], rep['os']),
               'host files: %s' % ', '.join('%s %s' % (h['name'], h['sha256'][:12]) for h in rep['host_files']) or 'host files: none found',
               'mods: %d folders' % sum(len(m.get('mods', [])) for m in rep['mods']),
               'logs: %d' % len(rep['logs']), 'game data: %s' % json.dumps(rep.get('game_data', {'given': False})),
               'EXCLUDED: saves, progress, game data, mod file contents, environment values. Redacted: user name, home, computer, e-mail, bundle path.']
    files['README.txt'] = '\n'.join(summary) + '\n'
    return files


def write(files, out):
    names = sorted(files)
    if out.lower().endswith('.zip'):
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for n in names:
                zi = zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, files[n].encode('utf-8'))
    else:
        for n in names:
            p = os.path.join(out, *n.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
                f.write(files[n])
    return names


def main(argv=None):
    ap = argparse.ArgumentParser(prog='bmdiag', description='Burnout Mashup diagnostic export (no saves, no game data, no personal data)')
    ap.add_argument('--bundle', help='the tester bundle root (host\\, profile\\, mods\\, diag\\)')
    ap.add_argument('--profile', help='the profile folder (default <bundle>\\profile; holds Roaming\\BurnoutMashup\\logs)')
    ap.add_argument('--data', help='the game data root (only default.xbe is hashed; nothing is copied)')
    ap.add_argument('--mods', help='mods folders separated by ";" (default <bundle>\\mods\\demo;generated;user)')
    ap.add_argument('--log', action='append', help='an extra log file (repeatable)')
    ap.add_argument('--preflight', action='append', help='a preflight output file (repeatable)')
    ap.add_argument('--include-more', action='store_true', help='opt-in: whole logs, mod.toml texts, profile settings (still redacted)')
    ap.add_argument('--out', required=True, help='a .zip file or a NEW folder')
    a = ap.parse_args(argv)
    if not a.bundle and not a.profile and not a.log:
        ap.error('give --bundle, or --profile / --log')
    if a.bundle and not os.path.isdir(a.bundle):
        ap.error('--bundle %s is not a folder' % a.bundle)
    if os.path.exists(a.out) and (not os.path.isdir(a.out) or os.listdir(a.out)):
        ap.error('%s exists: give a new file or an empty folder (nothing is overwritten)' % a.out)
    names = write(collect(a), a.out)
    print('bmdiag %s: wrote %s with %d files:' % (VERSION, a.out, len(names)))
    for n in names:
        print('  ' + n)
    print('Check the files before you send them. Excluded: saves, progress, game data, mod file contents, environment values.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
