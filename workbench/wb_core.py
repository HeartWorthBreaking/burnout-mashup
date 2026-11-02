"""wb_core - the non-GUI half of Burnout Mashup Workbench v0.1 (gp\\workbench, 2026-10-28).

A thin layer over two existing tools; it decides nothing itself:
  release pipeline   gp\\release\\release.py   plan (preflight + per-node cache decision, executes nothing) / run / run --resume
  mod validator      kit tools\\bmpack\\bmpack.py   validate ROOT.. --json / verify MOD_DIR
Commands are argument lists (never a shell string) with an explicit working directory; full output goes to a log file under
gp\\workbench\\logs; results are read from the tools' own outputs (release.py runs\\<id>\\summary.json + journal.jsonl,
bmpack's --json report). No game launch, no upload / push, no install into the game, no deletion.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

VERSION = '0.33'          # the Workbench version: window title (workbench.py) and README heading; bump once per milestone
WB = os.path.dirname(os.path.abspath(__file__))
# v0.4: no built-in developer paths. Every tool / data path comes from (highest first) a command-line option, the saved
# workbench.json (Settings tab "Save", or `wb_core.py config ... --save`), or the lookup the kit documents (BMKIT_* environment,
# PATH). discover() lists candidates (the developer workspace among them, labelled) but never applies one by itself.
# GP = the folder holding workbench\; PC = the workspace root only when the script sits at its usual place
# (<PC>\research\native_gameplay_api\platform\gp\workbench), else None (a copy elsewhere).
GP = os.path.dirname(WB)
_GP_SUFFIX = os.sep + r'research\native_gameplay_api\platform\gp'
PC = GP[:-len(_GP_SUFFIX)] if os.path.normcase(GP).endswith(os.path.normcase(_GP_SUFFIX)) else None
CONFIG_KEYS = ['kit', 'cc', 'cmake', 'ninja', 'game_data', 'pipeline']
# v0.29 (release readiness R1, kit mode): a Workbench unpacked from a mod kit (outside the workspace, PC None) that has no
# workbench.json beside it keeps its config, logs, state and bmpack cache per user (%APPDATA%\BurnoutMashup\workbench), so the
# kit folder may be read-only and several kits share nothing by accident. Beside-the-tool workbench.json (the workspace, or a
# portable copy that ships one) keeps working exactly as before.
KIT_MODE = PC is None
USER_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'BurnoutMashup', 'workbench')
_BESIDE = os.path.join(WB, 'workbench.json')


def _writable(d):
    """a real write probe (folder permission bits say little on Windows); removes its probe file"""
    p = os.path.join(d, '.wb_write_probe_%d' % os.getpid())
    try:
        with open(p, 'w') as f:
            f.write('x')
        os.remove(p)
        return True
    except OSError:
        return False


# v0.29 correction (full run c01): a copied / kit Workbench keeps settings beside itself as before; only a Workbench in a folder
# it cannot write (e.g. under Program Files) uses the per-user folder
DATA_DIR = USER_DIR if (KIT_MODE and not os.path.isfile(_BESIDE) and not _writable(WB)) else WB
CONFIG_FILE = os.path.join(DATA_DIR, 'workbench.json')
KIT_BESIDE = os.path.dirname(WB)                          # a kit ships the Workbench as <kit>\workbench
SPEC_SCHEMA = 'bm-release-spec/1'
SPEC_REQUIRED = ['release', 'versions', 'workspace_root', 'toolchains', 'sources', 'policies', 'nodes', 'checks',
                 'runtime_acceptance', 'frozen']
GAME_DATA_FILES = [r'Data\PrgData.bin', r'Data\stagehed.bin', r'Data\Globalus.bin']   # bmpack README: needed by validate
TASKKILL = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'taskkill.exe')
CC_EXE = 'x86_64-w64-mingw32-clang.exe'


def default_config():
    c = {k: '' for k in CONFIG_KEYS}
    c.update({'python': sys.executable, 'protected': [], 'runner': '', 'trackbuild': '',
              'bmpack_cache': os.path.join(DATA_DIR, 'state', 'bmpack_cache'),
              'logs': os.path.join(DATA_DIR, 'logs'), 'state': os.path.join(DATA_DIR, 'state')})
    return c


def env_lookup():
    """the kit's documented lookup (docs\\PREREQUISITES.md): BMKIT_CC > BMKIT_LLVM_MINGW (folder) > PATH for clang; PATH for
    cmake / ninja; BMKIT_GAME_DATA for game data -> {key: (path, source)}"""
    out = {}
    e = os.environ
    if e.get('BMKIT_CC') and os.path.isfile(e['BMKIT_CC']):
        out['cc'] = (e['BMKIT_CC'], 'env BMKIT_CC')
    elif e.get('BMKIT_LLVM_MINGW') and os.path.isfile(os.path.join(e['BMKIT_LLVM_MINGW'], 'bin', CC_EXE)):
        out['cc'] = (os.path.join(e['BMKIT_LLVM_MINGW'], 'bin', CC_EXE), 'env BMKIT_LLVM_MINGW')
    elif shutil.which(CC_EXE):
        out['cc'] = (shutil.which(CC_EXE), 'PATH')
    for k, exe in (('cmake', 'cmake.exe'), ('ninja', 'ninja.exe')):
        if shutil.which(exe):
            out[k] = (shutil.which(exe), 'PATH')
    if e.get('BMKIT_GAME_DATA') and os.path.isdir(e['BMKIT_GAME_DATA']):
        out['game_data'] = (e['BMKIT_GAME_DATA'], 'env BMKIT_GAME_DATA')
    return out


def load_config(path=None, **over):
    """option (keyword, None = keep) > workbench.json (beside this file, or PATH) > env / PATH lookup > not set.
    cfg['_source'][key] says where each value came from; cfg['_config_file'] is the file Save writes."""
    cfg = default_config()
    src = {k: 'not set' for k in CONFIG_KEYS}
    p = path or CONFIG_FILE
    for k, (v, s) in env_lookup().items():
        cfg[k], src[k] = v, s
    if KIT_MODE and kit_marker_ok(KIT_BESIDE):                          # v0.29: the kit this Workbench came with
        cfg['kit'], src['kit'] = KIT_BESIDE, 'the kit this Workbench is in'
    err = ''
    base = os.path.dirname(os.path.abspath(p))
    if os.path.isfile(p):
        try:
            with open(p, encoding='utf-8') as f:
                saved = json.load(f)
            if not isinstance(saved, dict):
                raise ValueError('not a JSON object')
        except (OSError, ValueError) as e:                       # v0.29: a broken file never stops the Workbench
            saved = {}
            err = 'the settings file %s could not be read (%s): defaults are used; fix it or Save new settings' % (p, e)
        for k, v in saved.items():
            if k in cfg and k != 'python' and v not in (None, ''):
                cfg[k] = os.path.join(base, v) if isinstance(v, str) and not os.path.isabs(v) else v   # relative = to the file
                if k in src:
                    src[k] = 'config file'
    for k, v in over.items():
        if v is not None and k in cfg:
            cfg[k] = v
            if k in src:
                src[k] = 'option'
    # every command runs with its own working directory, so relative paths are fixed to absolute ones here
    cfg = {k: os.path.abspath(v) if isinstance(v, str) and v else v for k, v in cfg.items()}
    cfg['protected'] = [os.path.abspath(x) for x in cfg.get('protected') or [] if x]
    cfg['_source'], cfg['_config_file'], cfg['_config_error'] = src, os.path.abspath(p), err
    return cfg


def save_config(cfg, path=None):
    """explicit save (Settings "Save" / `config --save`): the six paths + extra protected folders. Refuses values that are set
    but do not check out (config_status problems); empty values are saved as not set. -> (path, problems)"""
    st = config_status(cfg)
    bad = ['%s: %s' % (k, s['problem']) for k, s in st.items() if cfg.get(k) and s['problem']]
    bad += ['protected folder not found: %s' % x for x in cfg.get('protected') or [] if not os.path.isdir(x)]
    p = path or cfg.get('_config_file') or CONFIG_FILE
    if bad:
        return p, bad
    data = {'schema': 'bm-workbench-config/1'}
    data.update({k: cfg.get(k) or '' for k in CONFIG_KEYS})
    data['protected'] = list(cfg.get('protected') or [])
    if cfg.get('runner'):                                            # v0.6: optional (default: the workspace's)
        data['runner'] = cfg['runner']
    if cfg.get('trackbuild'):                                        # v0.28: optional (default: the kit's tools\trackbuild)
        data['trackbuild'] = cfg['trackbuild']
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)          # v0.29: the per-user folder may not exist yet
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, p)
    return p, []


TB_KIT_DIR = r'tools\trackbuild'


def trackbuild_dir(cfg):
    """v0.28: the trackbuild tree the track editor / track recipes use: the optional setting "trackbuild" (a trackbuild folder
    holding tb.py, e.g. main21's kit\\trackbuild 0.3.0) or, when not set, the kit's own tools\\trackbuild (0.2.1 in kit 0.6.0)"""
    return cfg.get('trackbuild') or os.path.join(cfg.get('kit') or '', TB_KIT_DIR)


def kit_path(cfg, rel):
    """a kit-relative path; paths under tools\\trackbuild resolve into trackbuild_dir(cfg)"""
    r = rel.replace('/', '\\')
    if os.path.normcase(r) == os.path.normcase(TB_KIT_DIR) or os.path.normcase(r).startswith(os.path.normcase(TB_KIT_DIR) + '\\'):
        rest = r[len(TB_KIT_DIR):].lstrip('\\')
        return os.path.join(trackbuild_dir(cfg), rest) if rest else trackbuild_dir(cfg)
    return os.path.join(cfg.get('kit') or '', rel)


def _kit_ok(d):
    return os.path.isfile(os.path.join(d, 'tools', 'bmpack', 'bmpack.py')) and os.path.isfile(os.path.join(d, 'sdk', 'BUILD.md'))


def kit_marker_ok(d):
    """v0.30: the folder around <kit>\\workbench is used as the kit only when it holds the kit marker files
    (HOST_INFO.json + tools\\bmpack + sdk\\BUILD.md); else the kit must be given (option / settings)"""
    # public fork: a source checkout has no HOST_INFO.json until a host is built (build/host_info.py writes it); the fork's own marker
    # host/PINS.json identifies the tree, so the host-independent functions work before the first build
    return bool(d) and _kit_ok(d) and (os.path.isfile(os.path.join(d, 'HOST_INFO.json')) or os.path.isfile(os.path.join(d, 'host', 'PINS.json')))


NEEDED_BY = {'kit': 'every recipe, Mod validation', 'cc': 'SDK plugin recipe, Mod validation', 'cmake': 'SDK plugin recipe',
             'ninja': 'SDK plugin recipe', 'game_data': 'Mod validation, p43 recipe', 'pipeline': 'Release tab'}


def check_value(k, v):
    """-> problem text ('' = fine) for one setting; actionable (what is expected where)"""
    if not v:
        return 'not set (needed by %s): choose it in Settings (Discover lists candidates) and Save, or give --%s' % (
            NEEDED_BY[k], k.replace('_', '-'))
    if k == 'kit':
        return '' if _kit_ok(v) else 'not a mod kit folder (needs tools\\bmpack\\bmpack.py and sdk\\BUILD.md): %s' % v
    if k == 'cc':
        if not os.path.isfile(v):
            return 'file not found: %s' % v
        return '' if os.path.basename(v).lower() == CC_EXE else 'must be llvm-mingw\'s bin\\%s: %s' % (CC_EXE, v)
    if k in ('cmake', 'ninja'):
        return '' if os.path.isfile(v) and os.path.basename(v).lower() == k + '.exe' else '%s.exe not found at %s' % (k, v)
    if k == 'game_data':
        miss = [f for f in GAME_DATA_FILES if not os.path.isfile(os.path.join(v, f))]
        return '' if not miss else 'not a game data folder (missing %s): %s' % (', '.join(miss), v)
    if k == 'pipeline':
        return '' if os.path.isfile(os.path.join(v, 'release.py')) else 'no release.py in %s' % v
    return ''


def config_status(cfg):
    return {k: {'value': cfg.get(k) or '', 'source': (cfg.get('_source') or {}).get(k, '?'),
                'problem': check_value(k, cfg.get(k) or '')} for k in CONFIG_KEYS}


def _find_kits(start, depth=2):
    out = []
    try:
        names = os.listdir(start)
    except OSError:
        return out
    for n in names:
        d = os.path.join(start, n)
        if os.path.isdir(d) and not n.startswith('.') and n not in ('test area', 'test_pipe', 'logs', 'state'):
            if _kit_ok(d):
                out.append(d)
            elif depth > 1:
                out += _find_kits(d, depth - 1)
    return out


def discover():
    """candidates per setting -> {key: [(path, label)]}; nothing is applied (the user picks and saves)"""
    c = {k: [] for k in CONFIG_KEYS}
    for k, (v, s) in env_lookup().items():
        c[k].append((v, s))
    for base in (os.path.dirname(GP), GP):                         # kits copied next to the Workbench folder
        for d in _find_kits(base):
            c['kit'].append((d, 'kit found near the Workbench'))
    if PC:
        k6 = os.path.join(GP, r'alpha_rc\v060\prose_final\kit_unpacked\bmashup-modkit-0.6.0')
        if _kit_ok(k6):
            c['kit'].append((k6, 'developer workspace %s (kit 0.6.0)' % PC))
    if os.path.isfile(os.path.join(GP, 'release', 'release.py')):
        c['pipeline'].append((os.path.join(GP, 'release'), 'release pipeline next to the Workbench'))
    for kit in [v for v, _ in c['kit']]:
        t = os.path.join(kit, 'bmkit.toml')                          # the kit's own optional config
        if os.path.isfile(t):
            try:
                import tomllib
                pth = tomllib.loads(open(t, encoding='utf-8').read()).get('paths', {})
            except Exception:                                        # noqa: BLE001
                pth = {}
            if pth.get('cc'):
                c['cc'].append((pth['cc'], 'kit bmkit.toml'))
            if pth.get('game_data'):
                c['game_data'].append((pth['game_data'], 'kit bmkit.toml'))
    if PC:                                                           # developer workspace: offered, never applied by itself
        lab = 'developer workspace %s' % PC
        for k, rel in (('cc', r'toolchain\llvm-mingw-x\llvm-mingw-20260922-ucrt-x86_64\bin' + os.sep + CC_EXE),
                       ('cmake', r'toolchain\cmake\cmake-4.4.4-windows-x86_64\bin\cmake.exe'),
                       ('ninja', r'toolchain\ninja\ninja.exe'),
                       ('game_data', r'runtime_data\base\Burnout 3 Takedown')):
            if os.path.exists(os.path.join(PC, rel)):
                c[k].append((os.path.join(PC, rel), lab))
    out = {}
    for k, lst in c.items():
        seen, out[k] = set(), []
        for v, lab in lst:
            n = os.path.normcase(os.path.abspath(v))
            if n not in seen and not check_value(k, v):
                seen.add(n)
                out[k].append((os.path.abspath(v), lab))
    return out


def workspace_values():
    """the developer workspace's paths (its labelled candidates) - for the developer's own tests, passed explicitly"""
    out = {}
    for k, lst in discover().items():
        ws = [v for v, lab in lst if lab.startswith('developer workspace') or lab.startswith('release pipeline next')]
        if ws:
            out[k] = ws[0]
    return out


def protected_roots(cfg, project=None):
    """-> [(path, why)] protected from staging: configured roots, the configured / given paths, the owner's fixed locations,
    the developer workspace's data folders when the script is in it. Location-independent markers: wb_stage.check_destination"""
    env = os.environ
    p = [(x, 'configured protected folder') for x in cfg.get('protected') or []]
    p += [(cfg.get('game_data'), 'game data'), (cfg.get('kit'), 'mod kit'), (cfg.get('pipeline'), 'release pipeline'),
          (project, 'source project'), (os.path.join(WB, 'logs'), 'Workbench logs'), (os.path.join(WB, 'state'), 'Workbench state'),
          (cfg.get('logs'), 'Workbench logs'), (cfg.get('state'), 'Workbench state')]
    for v in ('APPDATA', 'LOCALAPPDATA'):
        if env.get(v):
            p.append((os.path.join(env[v], 'Takedawn'), 'Takedawn saves / settings (a separate upstream install)'))
            bm = os.path.join(env[v], 'BurnoutMashup')     # the Burnout Mashup host's saves; its workbench\ sub-folder is ours
            try:
                kids = os.listdir(bm)
            except OSError:
                kids = []
            for k in kids:
                if k.lower() != 'workbench':
                    p.append((os.path.join(bm, k), 'Burnout Mashup saves / settings'))
    # no machine-specific locations are built in: add your own under Settings -> extra protected folders ('protected')
    if PC:
        for rel, why in ((r'runtime_data\base', 'retail data'), (r'runtime_data\runs', 'run records'),
                         (r'runtime_data\modsets', 'launched mod sets'), ('roots', 'game roots'), ('build', 'verified binaries'),
                         (r'research\native_gameplay_api\platform\gp\release', 'frozen releases')):
            p.append((os.path.join(PC, rel), why))
    return [(x, why) for x, why in p if x]


def norm(p):
    return os.path.normcase(os.path.abspath(p))


def pid_alive(pid):
    import ctypes
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259                                              # STILL_ACTIVE


# ---------------------------------------------------------------- release specs
def list_specs(cfg):
    d = cfg['pipeline']
    return sorted(os.path.join(d, f) for f in os.listdir(d) if re.match(r'release_spec.*\.json$', f)) if os.path.isdir(d) else []


def list_caches(cfg):
    d = cfg['pipeline']
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d)
                  if f.startswith('cache') and os.path.isdir(os.path.join(d, f, 'cas')))


def default_cache(cfg, spec):
    """the cache of the newest run of THIS spec (the pipeline's own run records); else the pipeline's default 'cache'"""
    best = None
    runs = os.path.join(cfg['pipeline'], 'runs')
    if os.path.isdir(runs):
        for r in os.listdir(runs):
            sp = os.path.join(runs, r, 'summary.json')
            try:
                s = json.load(open(sp, encoding='utf-8'))
            except Exception:
                continue
            if norm(s.get('spec', {}).get('path', '')) == norm(spec) and s.get('cache'):
                m = os.path.getmtime(sp)
                if best is None or m > best[0]:
                    best = (m, s['cache'])
    return best[1] if best else os.path.join(cfg['pipeline'], 'cache')


def check_spec(path):
    """structural check before handing the spec to release.py (which does the real preflight).
    -> {'ok', 'issues', 'info'}"""
    issues, info = [], {}
    if not os.path.isfile(path):
        return {'ok': False, 'issues': ['spec file not found: %s' % path], 'info': info}
    try:
        with open(path, 'rb') as f:
            s = json.loads(f.read())
    except ValueError as e:
        return {'ok': False, 'issues': ['not valid JSON: %s' % e], 'info': info}
    if not isinstance(s, dict):
        return {'ok': False, 'issues': ['top level is not a JSON object'], 'info': info}
    if s.get('schema') != SPEC_SCHEMA:
        issues.append('schema is %r, expected %r' % (s.get('schema'), SPEC_SCHEMA))
    for k in SPEC_REQUIRED:
        if k not in s:
            issues.append('missing section: %s' % k)
    nodes = s.get('nodes') if isinstance(s.get('nodes'), list) else []
    checks = s.get('checks') if isinstance(s.get('checks'), list) else []
    if 'nodes' in s and not nodes:
        issues.append('nodes must be a non-empty list')
    ids = [n.get('id') for n in nodes if isinstance(n, dict)]
    if len(ids) != len(set(ids)):
        issues.append('duplicate node ids')
    ws = s.get('workspace_root')
    if ws and not os.path.isdir(ws):
        issues.append('workspace_root does not exist: %s' % ws)
    rel = s.get('release') if isinstance(s.get('release'), dict) else {}
    info = {'release': rel.get('id'), 'name': rel.get('name'), 'status': rel.get('status'),
            'versions': s.get('versions') if isinstance(s.get('versions'), dict) else {},
            'nodes': ids, 'deliverables': [n.get('id') for n in nodes if isinstance(n, dict) and n.get('deliverable')],
            'checks': len(checks), 'gate_checks': sum(1 for c in checks if isinstance(c, dict) and c.get('gate', True))}
    return {'ok': not issues, 'issues': issues, 'info': info}


def release_prereqs(cfg, spec, cache):
    miss = []
    if not os.path.isfile(cfg['python']):
        miss.append('python not found: %s' % cfg['python'])
    if not os.path.isfile(os.path.join(cfg['pipeline'], 'release.py')):
        miss.append('release.py not found in %s' % cfg['pipeline'])
    if not os.path.isfile(spec):
        miss.append('spec not found: %s' % spec)
    lk = os.path.join(cache, 'state', 'LOCK')
    if os.path.isfile(lk):
        try:
            pid = int(open(lk).read().split()[0])
        except Exception:
            pid = 0
        if pid and pid_alive(pid):
            miss.append('cache %s is in use by pid %d (another release run)' % (cache, pid))
    return miss


def build_blockers(cfg, spec):
    """known limits of the EXISTING pipeline that make a build fail later; checked before a build starts"""
    out = []
    try:
        nodes = json.load(open(spec, encoding='utf-8')).get('nodes', [])
    except Exception:
        nodes = []
    if ' ' in cfg['pipeline'] and any(isinstance(n, dict) and n.get('kind') == 'host_build' for n in nodes):
        out.append('the pipeline folder path contains a space (%s): its host build recipe (recipes\\host_build.py) passes the '
                   'sandbox tree path unquoted in BO3_GEN_OPT ("-include <tree>/..."), so the host compile fails; use a '
                   'pipeline folder without spaces (specs, caches, mods and game data may contain spaces)' % cfg['pipeline'])
    return out


def bmpack_prereqs(cfg, need_game=True):
    miss = []
    if not os.path.isfile(cfg['python']):
        miss.append('python not found: %s' % cfg['python'])
    if not os.path.isfile(bmpack_py(cfg)):
        miss.append('bmpack.py not found under the kit folder %s' % cfg['kit'])
    if need_game and not cfg['game_data']:
        miss.append('no game data folder set (give --game-data DIR: your own NTSC-U data, read only; kit docs\\GAME_DATA.md)')
    elif need_game:
        for f in GAME_DATA_FILES:
            if not os.path.isfile(os.path.join(cfg['game_data'], f)):
                miss.append('game data file missing: %s' % os.path.join(cfg['game_data'], f))
        if not os.path.isfile(cfg['cc']):
            miss.append('C compiler (llvm-mingw clang) not found: %s' % cfg['cc'])
    return miss


def bmpack_py(cfg):
    return os.path.join(cfg['kit'], 'tools', 'bmpack', 'bmpack.py')


# ---------------------------------------------------------------- operations (argument lists, explicit cwd)
class Op:
    def __init__(self, kind, argv, cwd, title, **meta):
        self.kind, self.argv, self.cwd, self.title, self.meta = kind, argv, cwd, title, meta


def op_plan(cfg, spec, cache):
    spec, cache = os.path.abspath(spec), os.path.abspath(cache)
    rel = os.path.join(cfg['pipeline'], 'release.py')
    return Op('plan', [cfg['python'], '-B', rel, 'plan', '--spec', spec, '--cache', cache], cfg['pipeline'],
              'preflight (release.py plan)', spec=spec, cache=cache)


def new_label():
    return 'wb' + datetime.datetime.now().strftime('%H%M%S%f')[:9]


def op_run(cfg, spec, cache, jobs=4, publish=True, label=None, resume=None):
    spec, cache = os.path.abspath(spec), os.path.abspath(cache)
    rel = os.path.join(cfg['pipeline'], 'release.py')
    argv = [cfg['python'], '-B', rel, 'run', '--spec', spec, '--cache', cache, '--jobs', str(int(jobs))]
    if resume:
        argv += ['--resume', resume]
        label = None
    else:
        label = label or new_label()
        argv += ['--label', label]
    if not publish:
        argv.append('--no-publish')
    return Op('run', argv, cfg['pipeline'], 'release build (release.py run%s)' % (' --resume' if resume else ''),
              spec=spec, cache=cache, label=label, resume=resume)


def op_validate(cfg, roots):
    roots = [os.path.abspath(r) for r in roots]
    argv = [cfg['python'], '-B', bmpack_py(cfg), 'validate'] + list(roots) + [
        '--game-data', cfg['game_data'], '--cc', cfg['cc'], '--cache', cfg['bmpack_cache'], '--json']
    return Op('validate', argv, os.path.dirname(bmpack_py(cfg)), 'mod validation (bmpack validate)', roots=list(roots))


def op_verify(cfg, mod):
    mod = os.path.abspath(mod)
    argv = [cfg['python'], '-B', bmpack_py(cfg), 'verify', mod]
    return Op('verify', argv, os.path.dirname(bmpack_py(cfg)), 'mod manifest check (bmpack verify)', mod=mod)


# ---------------------------------------------------------------- one-at-a-time lock (across Workbench windows)
class OpLock:
    def __init__(self, cfg):
        self.path = os.path.join(cfg['state'], 'OPERATION.lock')

    def acquire(self, title):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if os.path.exists(self.path):
            try:
                pid = int(open(self.path).read().split()[0])
            except Exception:
                pid = 0
            if pid and pid_alive(pid):
                return 'another Workbench operation is running (pid %d): %s' % (pid, open(self.path).read().strip())
            os.remove(self.path)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return 'another Workbench operation just started'
        os.write(fd, ('%d %s %s\n' % (os.getpid(), time.strftime('%H:%M:%S'), title)).encode())
        os.close(fd)
        return None

    def release(self):
        try:
            os.remove(self.path)
        except OSError:
            pass


# ---------------------------------------------------------------- job runner
class Job:
    """runs one Op in the background; full output -> log file; on_line(str) per output line (from the reader thread)"""

    def __init__(self, cfg, op, on_line=None):
        self.cfg, self.op, self.on_line = cfg, op, on_line
        os.makedirs(cfg['logs'], exist_ok=True)
        self.log_path = os.path.join(cfg['logs'], '%s_%s.log' % (datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3], op.kind))
        self.proc = None
        self.rc = None
        self.cancelled = False
        self.started = self.ended = None
        self.done = threading.Event()
        self.tail = []

    def start(self):
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        self.started = time.time()
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write('# %s\n# cwd: %s\n# argv: %s\n' % (self.op.title, self.op.cwd, json.dumps(self.op.argv)))
        self.proc = subprocess.Popen(self.op.argv, cwd=self.op.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                                     | subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._pump, daemon=True).start()
        return self

    def _pump(self):
        with open(self.log_path, 'a', encoding='utf-8', newline='') as f:
            for raw in iter(self.proc.stdout.readline, b''):
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                f.write(line + '\n')
                f.flush()
                self.tail = (self.tail + [line])[-400:]
                if self.on_line:
                    try:
                        self.on_line(line)
                    except Exception:
                        pass
            self.rc = self.proc.wait()
            self.ended = time.time()
            f.write('# exit %s%s after %.1f s\n' % (self.rc, ' (cancelled by the user)' if self.cancelled else '',
                                                   self.ended - self.started))
        self.done.set()

    def cancel(self):
        """hard-stop the whole process tree. release.py's actions run in job objects with kill-on-close, its cache LOCK
        is treated as stale once the pid is gone, and its stale staging is removed by the next run; completed cache
        entries / published out folders are written only after success and are never touched."""
        if self.proc and self.proc.poll() is None:
            self.cancelled = True
            subprocess.run([TASKKILL, '/PID', str(self.proc.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def wait(self, timeout=None):
        return self.done.wait(timeout)

    def output(self):
        with open(self.log_path, encoding='utf-8', errors='replace') as f:
            return f.read()


# ---------------------------------------------------------------- results (read from the tools' own outputs)
def _failure_excerpt(text, n=12):
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith('# ')]
    for i, l in enumerate(lines):
        if 'PREFLIGHT FAILED' in l:
            return lines[i:i + n]
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith('Traceback'):
            return lines[i:][-n:]
    return lines[-n:]


def parse_plan(job):
    text = job.output()
    res = {'kind': 'plan', 'rc': job.rc, 'cancelled': job.cancelled, 'log': job.log_path}
    body = [l for l in text.splitlines() if not l.startswith('# ')]
    j = None
    for i, l in enumerate(body):
        if l.startswith('{'):
            try:
                j = json.loads('\n'.join(body[i:]))
                break
            except ValueError:
                pass
    if job.rc == 0 and j:
        res.update(ok=True, verdict='PREFLIGHT OK', preflight=j.get('preflight'),
                   impact={'level': j.get('impact', {}).get('level'),
                           'conservative_reasons': j.get('impact', {}).get('conservative_reasons')},
                   plan=j.get('plan', []),
                   would_build=[p['node'] for p in j.get('plan', []) if str(p.get('state', '')).startswith('would build')],
                   cached=[p['node'] for p in j.get('plan', []) if p.get('state') == 'cached'])
    else:
        res.update(ok=False, verdict='CANCELLED' if job.cancelled else 'PREFLIGHT FAILED', excerpt=_failure_excerpt(text))
    return res


def find_run_dir(cfg, op):
    runs = os.path.join(cfg['pipeline'], 'runs')
    if op.meta.get('resume'):
        d = os.path.join(runs, op.meta['resume'])
        return d if os.path.isdir(d) else None
    lab = op.meta.get('label')
    if not lab or not os.path.isdir(runs):
        return None
    c = [os.path.join(runs, r) for r in os.listdir(runs) if r.endswith('_' + lab)]
    return max(c, key=os.path.getmtime) if c else None


def run_progress(cfg, op, spec_info):
    """(done, total) from the run's journal (node_done) + checks finished; None before the run folder exists"""
    d = find_run_dir(cfg, op)
    if not d:
        return None
    jp = os.path.join(d, 'journal.jsonl')
    nodes = set()
    try:
        with open(jp, encoding='utf-8') as f:
            for l in f:
                if '"node_done"' in l or '"node_failed"' in l:
                    try:
                        nodes.add(json.loads(l).get('node'))
                    except ValueError:
                        pass
    except OSError:
        pass
    total = len(spec_info.get('nodes', []))
    return len(nodes), total


def parse_run(cfg, job):
    op = job.op
    text = job.output()
    res = {'kind': 'run', 'rc': job.rc, 'cancelled': job.cancelled, 'log': job.log_path, 'label': op.meta.get('label')}
    d = find_run_dir(cfg, op)
    res['run_dir'] = d
    res['run_id'] = os.path.basename(d) if d else None
    sp = os.path.join(d, 'summary.json') if d else None
    s = None
    if sp and os.path.isfile(sp) and (op.meta.get('resume') is None or os.path.getmtime(sp) >= job.started - 1):
        s = json.load(open(sp, encoding='utf-8'))
    if not s:
        res.update(ok=False, verdict='CANCELLED' if job.cancelled else 'FAILED (no run summary)',
                   excerpt=_failure_excerpt(text), summary=None,
                   resumable=bool(d and os.path.isfile(os.path.join(d, 'journal.jsonl'))))
        out = os.path.join(cfg['pipeline'], 'out', res['run_id']) if res['run_id'] else None
        if out and os.path.isdir(out) and not os.path.isfile(os.path.join(out, 'RELEASE_MANIFEST.json')):
            res['incomplete_output'] = out
        return res
    c = s['counts']
    res.update(summary=sp, status=s['status'], ok=s['status'].startswith('COMPLETE'), verdict=s['status'],
               wall_s=s['timing_s']['wall'], counts={k: c[k] for k in ('nodes_built', 'nodes_skipped', 'nodes_failed',
                                                                         'checks_run', 'checks_skipped', 'checks_failed')},
               nodes={n: {'status': v['status'], 'interface': v['interface'], 'reason': v.get('reason')}
                      for n, v in s['nodes'].items()},
               failed_nodes={n: ('%s (%s)' % ((v.get('stats') or {}).get('error'), v.get('reason'))
                                 if (v.get('stats') or {}).get('error') else v.get('reason'))
                             for n, v in s['nodes'].items() if v['status'] == 'failed'},
               failed_checks={cid: {'gate': cid in c['gate_checks_failed'],
                                    'reason': s['checks'][cid].get('reason'),
                                    'issues': ((s['checks'][cid].get('summary') or {}).get('issues') or [])[:5]}
                              for cid in c['gate_checks_failed'] + c['info_checks_failed']},
               runtime_acceptance=s.get('runtime_acceptance', {}).get('status'),
               impact=(s.get('impact') or {}).get('level'))
    od = s.get('published')
    if od:
        res['out_dir'] = od
        for f in ('RELEASE_MANIFEST.json', 'PUBLISH_PLAN.json'):
            if os.path.isfile(os.path.join(od, f)):
                res[f.split('.')[0].lower()] = os.path.join(od, f)
        res['artifacts'] = manifest_artifacts(res.get('release_manifest'))
    if res['failed_nodes']:
        res['excerpt'] = _failure_excerpt(text)
    return res


def manifest_artifacts(path):
    """{name: sha256} from a RELEASE_MANIFEST.json (whatever list / dict shape it has: entries with a sha256)"""
    if not path or not os.path.isfile(path):
        return {}
    m = json.load(open(path, encoding='utf-8'))
    out = {}

    def walk(o, name=None):
        if isinstance(o, dict):
            if isinstance(o.get('sha256'), str) and len(o['sha256']) == 64:
                out[o.get('name') or o.get('file') or o.get('path') or name] = o['sha256']
            for k, v in o.items():
                walk(v, k if isinstance(v, dict) else name)
        elif isinstance(o, list):
            for v in o:
                walk(v, name)
    walk(m.get('artifacts', m))
    return out


def parse_validate(job):
    text = job.output()
    res = {'kind': 'validate', 'rc': job.rc, 'cancelled': job.cancelled, 'log': job.log_path, 'roots': job.op.meta['roots']}
    body = '\n'.join(l for l in text.splitlines() if not l.startswith('# '))
    i = body.find('{')
    rep = None
    if i >= 0 and job.rc in (0, 1):
        try:
            rep = json.loads(body[i:])
        except ValueError:
            rep = None
    if rep is None:
        verdict = ('CANCELLED' if job.cancelled else 'MISSING PREREQUISITE' if job.rc == 3 else
                   'USAGE ERROR' if job.rc == 2 else 'REFUSED' if 'REFUSED' in body else 'FAILED')
        res.update(ok=False, verdict=verdict, excerpt=_failure_excerpt(text), report=None)
        return res
    res.update(ok=bool(rep.get('ok')), verdict='ACCEPTED' if rep.get('ok') else 'REFUSED', report=rep,
               mods=[{'id': m.get('id') or m.get('dir'), 'version': m.get('version'), 'usable': m.get('usable')}
                     for m in rep.get('mods', [])],
               refusals=[{'service': f.get('service'), 'mod': f.get('mod'), 'why': f.get('why')} for f in rep.get('refusals', [])],
               tracks_added=len(rep.get('added_tracks', [])), events=len(rep.get('events', [])))
    return res


def parse_verify(job):
    text = job.output()
    body = [l for l in text.splitlines() if l.strip() and not l.startswith('# ')]
    ok = job.rc == 0 and not job.cancelled
    return {'kind': 'verify', 'rc': job.rc, 'cancelled': job.cancelled, 'log': job.log_path, 'mod': job.op.meta['mod'],
            'ok': ok, 'verdict': 'CANCELLED' if job.cancelled else 'OK' if ok else 'MISMATCH' if job.rc == 1 else 'FAILED',
            'excerpt': body[-12:]}


def parse(cfg, job):
    k = job.op.kind
    if k in ('stage', 'profile'):          # wb_stage.StageJob / wb_profile.ProfileJob build their own result
        return job.result_dict
    return (parse_plan(job) if k == 'plan' else parse_run(cfg, job) if k == 'run' else
            parse_validate(job) if k == 'validate' else parse_verify(job))


def summarize(res):
    """short human text for one result (the GUI shows this; the full log stays in the file)"""
    if res.get('kind') == 'stage':
        import wb_stage
        return wb_stage.summarize(res)
    if res.get('kind') in ('profile', 'profile-check'):
        import wb_profile
        return wb_profile.summarize(res)
    L = ['%s: %s (exit %s)' % (res['kind'].upper(), res['verdict'], res['rc'])]
    if res['kind'] == 'plan' and res.get('ok'):
        pf = res.get('preflight') or {}
        L.append('inputs %s files hashed in %s s; impact %s' % (pf.get('input_files'), pf.get('input_hash_s'), res['impact']['level']))
        for p in res['plan']:
            L.append('  %-16s %s' % (p['node'], p['state']))
    if res['kind'] == 'run' and res.get('summary'):
        c = res['counts']
        L.append('run %s in %s s: nodes built %d, from cache %d, failed %d; checks run %d, cached %d, failed %d' % (
            res['run_id'], res['wall_s'], c['nodes_built'], c['nodes_skipped'], c['nodes_failed'], c['checks_run'],
            c['checks_skipped'], c['checks_failed']))
        L.append('runtime acceptance: %s' % res['runtime_acceptance'])
        for n, v in res['nodes'].items():
            L.append('  %-16s %-7s interface %s' % (n, v['status'], v['interface']))
        for n, why in res['failed_nodes'].items():
            L.append('  NODE FAILED %s: %s' % (n, why))
        for cid, v in res['failed_checks'].items():
            L.append('  CHECK FAILED %s%s: %s' % (cid, '' if v['gate'] else ' (info only)', '; '.join(v['issues']) or v['reason']))
        if res.get('out_dir'):
            L.append('output: %s' % res['out_dir'])
    if res['kind'] == 'run' and not res.get('summary'):
        if res.get('resumable'):
            L.append('run folder %s is incomplete; "Resume" continues it' % res['run_dir'])
        if res.get('incomplete_output'):
            L.append('INCOMPLETE output folder (no RELEASE_MANIFEST.json), do not use: %s' % res['incomplete_output'])
    if res['kind'] == 'validate' and res.get('report'):
        L.append('mods: ' + ', '.join('%s %s%s' % (m['id'], m['version'], '' if m['usable'] else ' (UNUSABLE)') for m in res['mods']))
        L.append('tracks added %d, events %d' % (res['tracks_added'], res['events']))
        for f in res['refusals']:
            L.append('  [%s] %s: %s' % (f['service'], f['mod'] or '-', f['why']))
    if res.get('excerpt') and not res.get('ok'):
        L.append('--- excerpt (full log: %s)' % res['log'])
        L += ['  ' + l for l in res['excerpt']]
    else:
        L.append('full log: %s' % res['log'])
    return '\n'.join(L)


def run_sync(cfg, op, timeout=None):
    """headless helper (tests / CLI): run one op to completion -> (job, result)"""
    lock = OpLock(cfg)
    why = lock.acquire(op.title)
    if why:
        raise RuntimeError(why)
    try:
        job = Job(cfg, op).start()
        if not job.wait(timeout):
            job.cancel()
            job.wait(60)
        return job, parse(cfg, job)
    finally:
        lock.release()


def main(argv):
    """CLI (headless, same backend as the GUI): wb_core.py plan|run|validate|verify ... -> one JSON verdict line"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['specs', 'check', 'plan', 'run', 'validate', 'verify', 'config'])
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--pipeline')
    ap.add_argument('--cache')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--no-publish', action='store_true')
    ap.add_argument('--resume')
    ap.add_argument('--kit')
    ap.add_argument('--game-data')
    ap.add_argument('--cc')
    ap.add_argument('--cmake')
    ap.add_argument('--ninja')
    ap.add_argument('--config')
    ap.add_argument('--protect', action='append', help='config: an extra protected folder (repeatable; replaces the saved list)')
    ap.add_argument('--use-discovered', action='store_true', help='config: fill settings that are not set from the first '
                    'discovered candidate (shown with its label; saved only with --save)')
    ap.add_argument('--save', action='store_true', help='config: write the settings to the config file')
    a = ap.parse_args(argv)
    cfg = load_config(a.config, pipeline=a.pipeline, kit=a.kit, game_data=a.game_data, cc=a.cc, cmake=a.cmake, ninja=a.ninja,
                      protected=a.protect)
    if a.cmd == 'config':
        disc = discover()
        if a.use_discovered:
            for k in CONFIG_KEYS:
                if not cfg.get(k) and disc.get(k):
                    cfg[k] = disc[k][0][0]
                    cfg['_source'][k] = 'discovered: %s' % disc[k][0][1]
        out = {'config_file': cfg['_config_file'], 'workspace_root': PC, 'settings': config_status(cfg),
               'protected': [{'path': p, 'why': w} for p, w in protected_roots(cfg)],
               'discovered': {k: [{'path': p, 'label': l} for p, l in v] for k, v in disc.items()}}
        rc = 0
        if a.save:
            path, bad = save_config(cfg)
            out['saved'] = not bad
            out['save_refused'] = bad
            rc = 1 if bad else 0
        print(json.dumps(out, indent=1))
        return rc
    if a.cmd == 'specs':
        print(json.dumps({'specs': list_specs(cfg), 'caches': list_caches(cfg)}, indent=1))
        return 0
    if a.cmd == 'check':
        r = check_spec(a.paths[0])
        print(json.dumps(r))
        return 0 if r['ok'] else 1
    if a.cmd in ('plan', 'run'):
        spec = a.paths[0]
        cache = a.cache or default_cache(cfg, spec)
        miss = release_prereqs(cfg, spec, cache) + (build_blockers(cfg, spec) if a.cmd == 'run' else [])
        cs = check_spec(spec)
        if miss or not cs['ok']:
            print(json.dumps({'verdict': 'NOT STARTED', 'missing': miss, 'spec_issues': cs['issues']}))
            return 3
        op = op_plan(cfg, spec, cache) if a.cmd == 'plan' else op_run(cfg, spec, cache, a.jobs, not a.no_publish, resume=a.resume)
    else:
        miss = bmpack_prereqs(cfg, need_game=(a.cmd == 'validate'))
        if miss:
            print(json.dumps({'verdict': 'NOT STARTED', 'missing': miss}))
            return 3
        op = op_validate(cfg, a.paths) if a.cmd == 'validate' else op_verify(cfg, a.paths[0])
    try:
        job, res = run_sync(cfg, op)
    except RuntimeError as e:
        print(json.dumps({'verdict': 'NOT STARTED', 'busy': str(e)}))
        return 4
    print(summarize(res))
    print(json.dumps({k: v for k, v in res.items() if k not in ('report', 'plan', 'nodes')}, default=str))
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
