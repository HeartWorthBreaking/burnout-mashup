"""wbn_flow - "Test this project" (Workbench 0.30 developer workflow): validate -> [build] -> stage -> launch plan. NEVER launches.

Steps (one Flow, a thread; progress events; cancel stops the running child process tree):
  1 settings   explicit settings only (a settings JSON and / or options; relative paths = relative to that file). Nothing is taken
               from the developer workspace: the guarded-runner plan appears only when `runner` is set.
  2 validate   wbn_rules (host tune rules, manifest, compatibility with the kit's HOST_INFO.json) - every problem names its
               file / line / field / editor object; any error stops here.
  3 build      plugins only: the kit SDK's CMake + Ninja + llvm-mingw in a NEW work folder (<state>\\wbn\\work\\<time>), from a
               build script the Workbench writes from validated names (the project's own CMakeLists.txt is never run).
  4 package    the clean mod folder (mod.toml [+ files\\] [+ the module]) into <state>\\wbn\\pkgsrc\\<mod id> (a fixed path, so a
               later run re-imports "the same source").
  5 stage      the EXISTING Workbench import staging (wb_stage.StageOp('import')): copy, checks, the kit's bmpack validate (the
               host's own admission; host readers from `host_readers` when set - kit 0.7.0 needs the fixed copy), then one
               rename into <staging>\\<mod id>; an earlier package is MOVED to <staging>\\.wb_stage\\previous\\<time>\\ (never
               deleted). Failed or cancelled: the staged package, STAGE.json and the last successful output stay as they were.
  6 compat     the tester launcher's gate (vendor\\bmcompat.py) over the STAGED folder vs the kit's HOST_INFO.json (and the
               bundle's host\\HOST_INFO.json when a bundle is set).
  7 approvals  native code only: is "<mod id> sha256:<module sha256>" in the approvals file you named? REPORTED, never written.
  8 plan       the launch plan, not executed: (a) a tester bundle (play.cmd's own profile inside the bundle: what it would set,
               the copy into mods\\user\\ you would do, the bundle's preflight command [run only with run_preflight and never in a
               protected folder]); (b) the guarded workspace runner (wb_profile check of the staged package against host_exe +
               the exact draft / prepare / preflight / dryrun / launch-plan commands; a changed project = a successor profile).
On success <state>\\wbn\\last\\<mod id>.json (the last successful output) is replaced atomically; never on failure / cancel.

    py -3 -B wbn.py test PROJECT --settings FILE [--json]
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'vendor'))
import bmcompat  # noqa: E402
import wb_core as core  # noqa: E402
import wb_profile  # noqa: E402
import wb_project  # noqa: E402
import wb_stage  # noqa: E402
import wbn_catalogue  # noqa: E402
import wbn_rules  # noqa: E402
import wbn_templates  # noqa: E402

SETTINGS_SCHEMA = 'bm-workbench-next-settings/1'
SETTING_KEYS = ('kit', 'game_data', 'cc', 'cmake', 'ninja', 'host_readers', 'staging', 'state', 'bundle', 'run_preflight',
                'runner', 'host_exe', 'approvals', 'profile_name', 'predecessor', 'catalogue')
STEPS = ['settings', 'validate', 'build', 'package', 'stage', 'compat', 'approvals', 'plan']
TASKKILL = core.TASKKILL


class Cancelled(Exception):
    pass


def load_settings(path=None, **over):
    """-> (settings dict, problems). Relative paths resolve against the settings file; options win."""
    s, bad = {k: None for k in SETTING_KEYS}, []
    if path:
        try:
            d = json.load(open(path, encoding='utf-8'))
            if not isinstance(d, dict):
                raise ValueError('not a JSON object')
        except (OSError, ValueError) as e:
            return s, ['settings file %s: %s' % (path, e)]
        base = os.path.dirname(os.path.abspath(path))
        for k, v in d.items():
            if k in SETTING_KEYS:
                s[k] = os.path.normpath(os.path.join(base, v)) if isinstance(v, str) and v and not os.path.isabs(v) and \
                    k not in ('profile_name',) else v
            elif k not in ('schema', 'note'):
                bad.append('settings file: unknown key %r (known: %s)' % (k, ', '.join(SETTING_KEYS)))
    for k, v in over.items():
        if v is not None and k in s:
            s[k] = v
    if not s['kit']:
        s['kit'] = kit_beside()                    # only a real kit folder around <kit>\workbench (marker files)
        if s['kit']:
            s['_kit_source'] = 'the kit this Workbench is in'
    if not s['state']:
        s['state'] = os.path.join(core.DATA_DIR, 'state', 'devflow')
    s['_file'] = os.path.abspath(path) if path else None
    return s, bad


def kit_beside():
    """<kit>\\workbench\\ -> <kit>, ONLY when that folder holds the kit marker files (wb_core.kit_marker_ok: HOST_INFO.json,
    tools\\bmpack\\bmpack.py, sdk\\BUILD.md); otherwise None and the kit must be given (--kit / settings)"""
    d = os.path.dirname(HERE)
    return d if core.kit_marker_ok(d) else None


def settings_problems(s, plugin):
    bad = []
    need = ['kit', 'game_data', 'cc', 'staging'] + (['cmake', 'ninja'] if plugin else [])
    for k in need:
        if not s.get(k):
            bad.append('setting "%s" is not set (settings file or --%s)' % (k, k.replace('_', '-')))
    for k in ('kit', 'game_data', 'host_readers', 'bundle'):
        if s.get(k) and not os.path.isdir(s[k]):
            bad.append('setting "%s": folder not found: %s' % (k, s[k]))
    for k in ('cc', 'cmake', 'ninja', 'runner', 'host_exe', 'approvals'):
        if s.get(k) and not os.path.isfile(s[k]):
            bad.append('setting "%s": file not found: %s' % (k, s[k]))
    if s.get('kit') and not os.path.isfile(os.path.join(s['kit'], 'HOST_INFO.json')):
        bad.append('setting "kit": %s has no HOST_INFO.json - the Test step needs a built host: run Build Mashup first (the build writes '
                   'HOST_INFO.json); projects, the tuning editor and validation without the host check work before' % s['kit'])
    return bad


def wb_cfg(s):
    """the existing Workbench configuration for the staging / profile code, from these settings only"""
    cfg = core.load_config(os.path.join(s['state'], 'no-settings-file.json'), kit=s['kit'], game_data=s['game_data'], cc=s['cc'],
                           cmake=s.get('cmake'), ninja=s.get('ninja'))
    cfg.update(logs=os.path.join(s['state'], 'logs'), state=os.path.join(s['state'], 'wbstate'),
               bmpack_cache=os.path.join(s['state'], 'bmpack_cache'), runner=s.get('runner') or '')
    return cfg


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _write_json_atomic(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)
    os.replace(p + '.tmp', p)


def last_success(s, mod_id):
    try:
        return json.load(open(os.path.join(s['state'], 'wbn', 'last', '%s.json' % mod_id), encoding='utf-8'))
    except (OSError, ValueError):
        return None


def project_kind(project):
    try:
        t = tomllib.loads(open(os.path.join(project, 'mod.toml'), encoding='utf-8').read().lstrip('﻿'))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None, None
    return ('plugin' if isinstance(t.get('plugin'), dict) else 'data'), t.get('id')


# ------------------------------------------------------------------------------------------------ plan helpers
def bundle_dirs(b):
    r"""0.2.0 (launcher bmpaths.py, same rule): in the Windows package (layout 2: <install>\app\launcher with
    <install>\Burnout Mashup.exe) the game copy and mods\user / mods\generated live in <install>\gamedata; else in the launcher folder.
    -> (gamedata, mods\generated, mods\user)"""
    t = os.path.dirname(os.path.abspath(b))
    inst = os.path.dirname(t)
    if os.path.basename(t).lower() == 'app' and os.path.isfile(os.path.join(inst, 'Burnout Mashup.exe')):
        gd = os.path.join(inst, 'gamedata')
        return gd, os.path.join(gd, 'mods', 'generated'), os.path.join(gd, 'mods', 'user')
    return os.path.join(b, 'gamedata'), os.path.join(b, 'mods', 'generated'), os.path.join(b, 'mods', 'user')


def bundle_plan(s, staged, mod_id, kind):
    """play.cmd (tester package 0.3.0) logic, re-done read only: which host, which profile folders, which mod folders"""
    b = s['bundle']
    root = b.rstrip('\\') + '\\'
    sel = None
    loc = os.path.join(b, 'host-local', 'burnout3_bmashup.exe')
    hostdir = os.path.join(b, 'host-local') if os.path.isfile(loc) else os.path.join(b, 'host')
    kindtxt = 'local build (host-local holds a host)' if os.path.isfile(loc) else 'prebuilt host (host-local is empty)'
    exe = os.path.join(hostdir, 'burnout3_bmashup.exe')
    gd, mgen, muser = bundle_dirs(b)
    mods = ';'.join((root + r'mods\demo', mgen, muser))
    plan = {'bundle': b, 'is_bundle': os.path.isfile(os.path.join(b, 'play.cmd')) and os.path.isfile(os.path.join(b, 'BUNDLE.json')),
            'host': kindtxt, 'exe': exe, 'exe_present': os.path.isfile(exe),
            'gamedata_ready': os.path.isfile(os.path.join(gd, '.complete')),
            'env': {'APPDATA': root + r'profile\Roaming', 'LOCALAPPDATA': root + r'profile\Local',
                    'BMASHUP_DATA': gd, 'TAKEDAWN_DATA': gd, 'BMASHUP_MODS': mods, 'TAKEDAWN_MODS': mods},
            'install_step': 'copy the folder "%s" to "%s" (not done by the Workbench)' % (staged, os.path.join(muser, mod_id)),
            'already_installed': os.path.isdir(os.path.join(muser, mod_id)),
            'start_command': '"%s"' % os.path.join(b, 'play.cmd'), 'source': 'play.cmd (read, not run); BMASHUP_HOST unset',
            'approvals_file_of_this_profile': os.path.join(b, 'profile', 'Roaming', 'BurnoutMashup', 'plugin-approvals.toml')}
    hi = os.path.join(hostdir, 'HOST_INFO.json')
    if os.path.isfile(hi):
        try:
            info = bmcompat.load_host_info(hi)
            r = bmcompat.check_mod(info, staged)
            plan['compat_bundle_host'] = {'level': r['level'], 'reasons': r['reasons'], 'host': info.get('identity')}
        except (OSError, ValueError) as e:
            plan['compat_bundle_host'] = {'level': 'UNKNOWN', 'reasons': ['host\\HOST_INFO.json unreadable: %s' % e]}
    else:
        plan['compat_bundle_host'] = {'level': 'UNKNOWN', 'reasons': ['the bundle has no host\\HOST_INFO.json (no host yet)']}
    blockers = []
    if not plan['is_bundle']:
        blockers.append('not a tester bundle (play.cmd / BUNDLE.json missing): %s' % b)
    if not plan['exe_present']:
        blockers.append('no host in the bundle: %s (prebuilt: unpack the package again; own build: build-host.cmd)' % exe)
    if not plan['gamedata_ready']:
        blockers.append('no checked game data in the bundle: prepare.cmd data --copy-from <your game data> (then preflight.cmd)')
    plan['blockers'] = blockers
    plan['preflight_command'] = 'py -3 -B "%s" --dir "%s"' % (os.path.join(b, 'tools', 'preflight.py'), b)
    return plan


def preflight_refusals(cfg, bundle):
    """preflight.py writes diag\\preflight_last.txt into the bundle: never in a protected place (the Workbench's protected roots,
    the release and release-readiness folders of the workspace, a sealed research folder is not a bundle)"""
    gp = os.path.dirname(HERE)
    prot = [(p, w) for p, w in core.protected_roots(cfg)] + [(os.path.join(gp, 'release'), 'frozen releases'),
                                                            (os.path.join(gp, 'release_readiness'), 'release candidate')]
    out = []
    b = os.path.normcase(os.path.realpath(bundle))
    for p, w in prot:
        r = os.path.normcase(os.path.realpath(p))
        if b == r or b.startswith(r.rstrip('\\') + '\\') or r.startswith(b.rstrip('\\') + '\\'):
            out.append('the bundle overlaps a protected location (%s: %s)' % (w, p))
    return out


def guarded_plan(s, cfg, staged, mod_id):
    name = s.get('profile_name') or ('wbp_' + ''.join(c if c.isalnum() or c in '_-' else '-' for c in mod_id.lower())[:36])
    rp = wb_profile.runner_paths(cfg)
    dest = os.path.join(rp['modsets'], name) if rp else '<runtime_data\\modsets>\\' + name
    wbp = os.path.join(HERE, 'wb_profile.py')
    appr = s.get('approvals') or '<your approvals file>'
    cmds = ['py -3 -B "%s" check "%s" "%s" "%s" --approvals "%s"' % (wbp, staged, s.get('host_exe') or '<host exe under build\\>',
                                                                  dest, appr),
            'py -3 -B "%s" prepare "%s" "%s" "%s" --approvals "%s"%s' % (wbp, staged, s.get('host_exe') or '<host exe>', dest, appr,
                                                                     (' --predecessor "%s"' % s['predecessor'])
                                                                     if s.get('predecessor') else ''),
            'py -3 -B "%s" preflight "%s"' % (wbp, dest), 'py -3 -B "%s" dryrun "%s"' % (wbp, dest),
            'py -3 -B "%s" launch-plan "%s"' % (wbp, dest)]
    out = {'profile': dest, 'commands': cmds, 'writes_when_run': 'prepare: runtime_data\\modsets\\<profile> + a new data root '
           '(g_run make-root); preflight / dryrun: results inside the profile; NONE of these were run here',
           'launch': 'only with the owner present: wb_profile.py launch PROFILE --authorize-runtime RUN:SHA12 (the token comes '
                     'from the dry run). NOT run.',
           'successor': 'a changed project = a successor profile: wb_profile.py successor OLD_PROFILE --dest NEW_PROFILE'}
    if s.get('host_exe'):
        info = wb_profile.inspect(cfg, [staged], s['host_exe'], dest, s.get('approvals'), predecessor=s.get('predecessor'))
        out['check'] = {'problems': info.get('problems'), 'host': (info.get('host') or {}).get('sha256'),
                        'host_described_by': info.get('host_described_by'),
                        'admission_ok': (info.get('admission') or {}).get('ok'),
                        'members': [{k: m.get(k) for k in ('mod_id', 'kind', 'module_sha256', 'approval')}
                                    for m in info.get('members') or []]}
    else:
        out['check'] = {'problems': ['host_exe not set: the profile check (host bytes, the host\'s admission) was not run']}
    return out


# ------------------------------------------------------------------------------------------------ the flow
class Flow:
    """one "Test this project" run. on_event(dict) gets {'step', 'state': start|done|failed|skipped, 'n', 'of', 'msg'} and log
    lines {'log': text}. result: the report dict (also <state>\\wbn\\runs\\<time>.json)."""

    def __init__(self, project, settings, on_event=None):
        self.project, self.s, self.on_event = os.path.abspath(project), settings, on_event
        self.cancelled = False
        self.proc = None
        self.stage_job = None
        self.done = threading.Event()
        self.result = None
        self._lk = threading.Lock()
        self.ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')

    def ev(self, **k):
        if self.on_event:
            try:
                self.on_event(k)
            except Exception:
                pass

    def cancel(self):
        with self._lk:
            self.cancelled = True
            p, j = self.proc, self.stage_job
        if j:
            j.cancel()
        if p and p.poll() is None:
            subprocess.run([TASKKILL, '/PID', str(p.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def _check_cancel(self):
        if self.cancelled:
            raise Cancelled()

    def _run(self, argv, cwd, log):
        with self._lk:
            if self.cancelled:
                raise Cancelled()
            self.proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        with open(log, 'a', encoding='utf-8') as f:
            f.write('## %s\n' % json.dumps(argv))
            for raw in iter(self.proc.stdout.readline, b''):
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                f.write(line + '\n')
                self.ev(log=line)
        rc = self.proc.wait()
        self._check_cancel()
        return rc

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()
        return self

    def wait(self, timeout=None):
        return self.done.wait(timeout)

    def run(self):
        r = {'schema': 'bm-workbench-next-test/1', 'project': self.project, 'time': self.ts, 'steps': [], 'ok': False,
             'launched': False, 'verdict': None, 'problems': []}
        cur = None
        try:
            self._flow(r, lambda st: None)
        except Cancelled:
            r['verdict'] = 'CANCELLED'
            r['problems'].append({'sev': 'error', 'msg': 'cancelled by the user: the sources, the staged package and the last '
                                  'successful output are unchanged', 'code': 'cancelled'})
        except Exception as e:  # noqa: BLE001
            import traceback
            r['verdict'] = 'INTERNAL ERROR'
            r['problems'].append({'sev': 'error', 'code': 'internal', 'msg': '%r' % e, 'trace': traceback.format_exc()[-1500:]})
        r['cancelled'] = self.cancelled
        for st in r['steps']:
            if st['state'] == 'start':
                st['state'] = 'cancelled' if self.cancelled else 'failed'
                cur = st['step']
        r['stopped_at'] = cur
        try:
            _write_json_atomic(os.path.join(self.s['state'], 'wbn', 'runs', '%s.json' % self.ts), r)
        except OSError:
            pass
        self.result = r
        self.ev(step='end', state='done' if r['ok'] else 'failed', msg=r['verdict'])
        self.done.set()
        return r

    def _step(self, r, name, msg=''):
        self._check_cancel()
        r['steps'].append({'step': name, 'state': 'start', 'msg': msg})
        self.ev(step=name, state='start', n=STEPS.index(name) + 1, of=len(STEPS), msg=msg)

    def _end(self, r, state='done', msg=''):
        st = r['steps'][-1]
        st.update(state=state, msg=msg or st['msg'])
        self.ev(step=st['step'], state=state, n=STEPS.index(st['step']) + 1, of=len(STEPS), msg=st['msg'])

    def _fail(self, r, verdict, problems):
        self._end(r, 'failed', verdict)
        r['verdict'] = verdict
        r['problems'] += problems
        return r

    def _flow(self, r, _):
        s, project = self.s, self.project
        self._step(r, 'settings')
        kind, mod_id = project_kind(project)
        r.update(kind=kind, mod_id=mod_id)
        bad = settings_problems(s, kind == 'plugin')
        if not os.path.isdir(project):
            bad.insert(0, 'project folder not found: %s' % project)
        if bad:
            return self._fail(r, 'SETTINGS INCOMPLETE', [{'sev': 'error', 'code': 'settings', 'msg': b,
                                                           'file': s.get('_file') or '(options)'} for b in bad])
        cat = wbn_catalogue.load(s.get('catalogue'))
        info = json.load(open(os.path.join(s['kit'], 'HOST_INFO.json'), encoding='utf-8'))
        r['host_kit'] = {'host': info.get('host_name'), 'identity': info.get('identity'), 'platform': info.get('platform'),
                         'exe_sha256': info.get('exe_sha256')}
        if s.get('host_readers'):
            os.environ['BMKIT_HOST_READERS'] = s['host_readers']      # bmpack's own documented setting (bmkit_env.host_readers)
        else:
            os.environ.pop('BMKIT_HOST_READERS', None)
        r['settings'] = {k: s.get(k) for k in SETTING_KEYS}
        self._end(r)

        self._step(r, 'validate')
        v = wbn_rules.validate_project(project, cat, info)
        r['validation'] = {'ok': v['ok'], 'problems': v['problems']}
        if not v['ok']:
            return self._fail(r, 'VALIDATION FAILED', [p for p in v['problems'] if p['sev'] == 'error'])
        self._end(r, msg='%d warning(s)' % sum(p['sev'] == 'warn' for p in v['problems']))
        prev = last_success(s, mod_id)
        work = os.path.join(s['state'], 'wbn', 'work', self.ts)
        os.makedirs(work)
        log = os.path.join(work, 'flow.log')
        r['log'] = log
        module = None

        self._step(r, 'build')
        if kind != 'plugin':
            self._end(r, 'skipped', 'data mod: nothing to build')
        else:
            mk = wbn_templates.read_marker(project)
            t = tomllib.loads(open(os.path.join(project, 'mod.toml'), encoding='utf-8').read())
            win = (t.get('plugin') or {}).get('windows') or ''
            module = win[:-4] if win.endswith('.asi') else None
            why = wb_project.check_module(module or '')
            srcs = sorted(f for f in os.listdir(project) if wb_project.SOURCE_RE.match(f))
            if why or not srcs or not mk:
                return self._fail(r, 'BUILD NOT POSSIBLE', [{'sev': 'error', 'code': 'build', 'file': 'mod.toml',
                                                             'msg': why or ('no C source in the project' if not srcs else
                                                                            'no wbn-project.json (not a Workbench template project)')}])
            src = os.path.join(work, 'src')
            os.makedirs(src)
            for f in srcs + ['mod.toml']:
                shutil.copyfile(os.path.join(project, f), os.path.join(src, f))
            tpl = wbn_templates.TEMPLATES.get(mk.get('template')) or {}
            defines = []
            if tpl.get('param') and tpl['param']['name'] in (mk.get('params') or {}):
                pv = float(mk['params'][tpl['param']['name']])
                if not tpl['param']['lo'] <= pv <= tpl['param']['hi']:
                    return self._fail(r, 'BUILD NOT POSSIBLE', [{'sev': 'error', 'code': 'param', 'file': wbn_templates.MARKER,
                                                                 'field': 'params.' + tpl['param']['name'],
                                                                 'msg': '%s %g outside %g .. %g' % (tpl['param']['name'], pv,
                                                                                                     tpl['param']['lo'],
                                                                                                     tpl['param']['hi'])}])
                defines.append('%s=%s' % (tpl['param']['define'], repr(pv)))
            cm = wbn_templates.plugin_cmake(module, mod_id, srcs[0], defines)
            with open(os.path.join(src, 'CMakeLists.txt'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(cm)
            own = os.path.join(project, 'CMakeLists.txt')
            r['build_note'] = ('the project\'s CMakeLists.txt is not used (the Workbench writes its own from validated names)%s'
                               % ('' if not os.path.isfile(own) else
                                  '; it %s the template\'s' % ('equals' if open(own, encoding='utf-8').read() == cm else 'differs from')))
            llvm = os.path.dirname(os.path.dirname(s['cc']))
            bdir = os.path.join(work, 'build')
            argv = [s['cmake'], '-S', src, '-B', bdir, '-G', 'Ninja', '-DCMAKE_MAKE_PROGRAM=' + s['ninja'],
                    '-DCMAKE_TOOLCHAIN_FILE=' + os.path.join(s['kit'], 'sdk', 'cmake', 'llvm-mingw-x86_64.cmake'),
                    '-DLLVM_MINGW_ROOT=' + llvm, '-DBMSDK_DIR=' + os.path.join(s['kit'], 'sdk'), '-DCMAKE_BUILD_TYPE=Release']
            if self._run(argv, work, log) != 0 or self._run([s['cmake'], '--build', bdir], work, log) != 0:
                return self._fail(r, 'BUILD FAILED', [{'sev': 'error', 'code': 'build', 'file': srcs[0],
                                                       'msg': 'the build failed: the compiler messages are in %s' % log,
                                                       'log': log}])
            out = os.path.join(bdir, 'out', mod_id)
            if not os.path.isfile(os.path.join(out, module + '.asi')):
                return self._fail(r, 'BUILD FAILED', [{'sev': 'error', 'code': 'build', 'msg': 'no %s.asi in %s' % (module, out)}])
            r['module'] = {'file': module + '.asi', 'sha256': sha_file(os.path.join(out, module + '.asi'))}
            self._end(r, msg='%s.asi sha256 %s' % (module, r['module']['sha256'][:12]))

        self._step(r, 'package')
        pkgsrc = os.path.join(s['state'], 'wbn', 'pkgsrc', mod_id)
        tmp = pkgsrc + '.tmp_' + self.ts
        os.makedirs(tmp)
        shutil.copyfile(os.path.join(project, 'mod.toml'), os.path.join(tmp, 'mod.toml'))
        if os.path.isdir(os.path.join(project, 'files')):
            shutil.copytree(os.path.join(project, 'files'), os.path.join(tmp, 'files'))
        if module:
            shutil.copyfile(os.path.join(work, 'build', 'out', mod_id, module + '.asi'), os.path.join(tmp, module + '.asi'))
        if os.path.isdir(pkgsrc):
            os.rename(pkgsrc, os.path.join(work, 'pkgsrc_before'))      # kept in this attempt's work folder (not deleted)
        os.rename(tmp, pkgsrc)
        self._end(r, msg=pkgsrc)

        self._step(r, 'stage')
        cfg = wb_cfg(s)
        os.makedirs(s['staging'], exist_ok=True)
        op = wb_stage.StageOp(wb_stage.IMPORT_RECIPE, pkgsrc, s['staging'])
        job = wb_stage.StageJob(cfg, op, on_line=lambda ln: self.ev(log=ln))
        with self._lk:
            if self.cancelled:
                raise Cancelled()
            self.stage_job = job
        job.start()
        job.wait()
        with self._lk:
            self.stage_job = None
        sr = job.result_dict or {}
        r['stage'] = {k: sr.get(k) for k in ('verdict', 'staged', 'mod_id', 'bmpack', 'log', 'attempt', 'excerpt', 'ok')}
        if not sr.get('ok'):
            self._check_cancel()
        elif self.cancelled:                  # the commit happened before the cancel: finish the read-only steps consistently
            r['cancel_after_commit'] = True
            self.cancelled = False
        if not sr.get('ok'):
            probs = [{'sev': 'error', 'code': 'stage', 'msg': x, 'file': 'mod.toml'} for x in (sr.get('excerpt') or [sr.get('verdict')])]
            for f in (sr.get('bmpack') or {}).get('refusals') or []:
                probs.append({'sev': 'error', 'code': 'bmpack-' + str(f.get('service')), 'file': 'mod.toml', 'obj': 'compat',
                              'msg': 'host admission (bmpack) [%s]: %s' % (f.get('service'), f.get('why'))})
            return self._fail(r, 'STAGING FAILED (%s)' % sr.get('verdict'), probs)
        staged = sr['staged']
        self._end(r, msg=staged)

        self._step(r, 'compat')
        c = bmcompat.check_mod(info, staged)
        r['compat'] = {'level': c['level'], 'reasons': c['reasons'], 'host': info.get('identity')}
        self._end(r, msg=c['level'])

        self._step(r, 'approvals')
        if module:
            line = '%s sha256:%s' % (mod_id, r['module']['sha256'])
            if s.get('approvals'):
                ok, _, detail = wb_profile.approval_status(s['approvals'], mod_id, r['module']['sha256'])
            else:
                ok, detail = False, 'no approvals file named (setting "approvals"): coverage unknown'
            r['approvals'] = {'needed': True, 'covered': ok, 'line': line, 'file': s.get('approvals'), 'detail': detail,
                              'note': 'reported only; the Workbench never writes or changes an approval'}
            self._end(r, msg='covered' if ok else 'NOT covered')
        else:
            r['approvals'] = {'needed': False, 'covered': True, 'detail': 'data only, no native code'}
            self._end(r, 'skipped', 'data mod: no approval needed')

        self._step(r, 'plan')
        plan = {'launched': False, 'launch': 'NOT LAUNCHED: this is a plan; nothing was started', 'staged': staged,
                'mod_id': mod_id, 'kind': kind, 'module': r.get('module'), 'compat': r['compat'], 'approvals': r['approvals']}
        if s.get('bundle'):
            plan['bundle'] = bundle_plan(s, staged, mod_id, kind)
            if s.get('run_preflight'):
                bad = preflight_refusals(cfg, s['bundle'])
                if bad:
                    plan['bundle']['preflight'] = {'run': False, 'why': 'refused: ' + '; '.join(bad)}
                else:
                    pl = os.path.join(work, 'preflight.log')
                    rc = self._run([sys.executable, '-B', os.path.join(s['bundle'], 'tools', 'preflight.py'), '--dir', s['bundle']],
                                   s['bundle'], pl)
                    tail = [x for x in open(pl, encoding='utf-8', errors='replace').read().splitlines() if x.strip()]
                    plan['bundle']['preflight'] = {'run': True, 'rc': rc, 'result': next((x for x in reversed(tail)
                                                                                         if x.startswith('RESULT')), None),
                                                   'fails': [x for x in tail if x.startswith('FAIL')][:20], 'log': pl}
            else:
                plan['bundle']['preflight'] = {'run': False, 'why': 'run_preflight not set (it writes diag\\preflight_last.txt '
                                                                     'into the bundle)'}
        else:
            plan['bundle'] = None
        plan['guarded'] = guarded_plan(s, cfg, staged, mod_id) if s.get('runner') else None
        r['plan'] = plan
        self._end(r)
        rec = {'mod_id': mod_id, 'project': project, 'time': self.ts, 'staged': staged, 'stage_log': sr.get('log'),
               'package_files': wb_stage.tree_hashes(staged), 'module': r.get('module'), 'plan': plan,
               'previous_success': (prev or {}).get('time')}
        _write_json_atomic(os.path.join(s['state'], 'wbn', 'last', '%s.json' % mod_id), rec)
        r['last_success'] = os.path.join(s['state'], 'wbn', 'last', '%s.json' % mod_id)
        r['ok'] = True
        r['verdict'] = 'READY TO TEST (plan only, not launched)'
        return r


def run_sync(project, settings, on_event=None, timeout=3600):
    f = Flow(project, settings, on_event)
    f.run()
    return f.result


def summary(r):
    L = ['TEST THIS PROJECT: %s' % r.get('verdict'), 'project %s (%s %s)' % (r['project'], r.get('kind'), r.get('mod_id'))]
    for st in r['steps']:
        L.append('  %-9s %-9s %s' % (st['step'], st['state'], st.get('msg') or ''))
    for p in r['problems']:
        L.append('  ' + wbn_rules.format_problem(dict({'file': '', 'line': None, 'col': None, 'field': None, 'fix': ''}, **p)))
    pl = r.get('plan')
    if pl:
        L.append('LAUNCH PLAN (not launched): staged %s' % pl['staged'])
        L.append('  compat with %s: %s %s' % (pl['compat']['host'], pl['compat']['level'], '; '.join(pl['compat']['reasons'])))
        L.append('  approvals: %s' % pl['approvals']['detail'])
        if pl.get('bundle'):
            b = pl['bundle']
            L.append('  bundle %s: host %s (%s); blockers: %s' % (b['bundle'], b['exe'], 'present' if b['exe_present'] else 'MISSING',
                                                                 '; '.join(b['blockers']) or 'none'))
            L.append('    install: ' + b['install_step'])
            L.append('    start:   %s   (preflight: %s)' % (b['start_command'], b['preflight'].get('result') or b['preflight'].get('why')))
        if pl.get('guarded'):
            g = pl['guarded']
            L.append('  guarded runner profile %s; check problems: %s' % (g['profile'], '; '.join(g['check']['problems']) or 'none'))
            L += ['    ' + c for c in g['commands']]
    return '\n'.join(L)
