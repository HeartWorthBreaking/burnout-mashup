"""wb_profile - isolated test profiles for Burnout Mashup Workbench v0.7 (gp\\workbench, 2026-10-28).

A test profile = one or more staged packages (Workbench STAGE records: native plugins and data-only mods), one compatible
host exe, the player's own approval of every plugin module's exact bytes, prepared for the workspace's EXISTING guarded
runner (tools\\runners\\g_run.py) - nothing parallel:
  Check      every member's identity (mod id, version, hashes, requirements, approval), the host (which kit describes it,
             its offered services), and the host's OWN admission over the whole combination: the kit's `bmpack validate`
             (bmpack.configure + bmpack.validate with the describing kit's host readers: modfs order, shared ids, the mod cap,
             the platform gate, requires_mods order / missing / cycles, cross-mod clashes). The Workbench has no admission
             rules of its own. Writes nothing.
  Prepare    the same checks, then the profile folder is assembled in a temporary folder, the host's admission runs again on
             exactly that folder, then `g_run.py make-root <name>` (or, for a successor, explicitly adopting the predecessor's
             still-unused verified root), and one rename makes runtime_data\\modsets\\<name>\\  PROFILE.json,
             plugins\\<mod id>\\<package files>, state\\mod-list.toml, state\\plugin-approvals.toml (only the player's lines for
             these plugin bytes, copied from the one file the player chose; data-only mods need none).
  Preflight  the prelaunch checks: profile record, membership and every member's bytes = the recorded ones, staged packages
             unchanged, approvals, host bytes, compatibility and the host's admission rechecked with the current kit, root
             unused, no game running -> PREFLIGHT.json + results\\preflight_<time>.json.
  Dry run    needs a valid preflight; `g_run.py run td_run --dry-run` -> DRYRUN.json + results\\dryrun_<time>.json.
A change of membership, bytes, host or kit makes the affected results STALE; they are kept as history and shown as stale.
A prepared profile is never changed (only its history.jsonl grows): a different combination is a SUCCESSOR profile (new
name, `predecessor` + `changes` recorded, preflight / dry run start again; the predecessor's results are listed as stale
history). The Workbench never approves code. Profiles from v0.6 (schema /1, one plugin) are read.
v0.8 Launch -> Stop -> Results (one REAL boot of a prepared profile, owner present):
  Launch plan  read only: the exact profile, host sha256 / build identity, every member's id / version / hashes / approval,
             preflight + dry-run state, the token from the dry run's WOULD_LAUNCH (RUN = <profile>_run1, SHA12 = the host's),
             the exact g_run argv; every refusal (stale / changed / unapproved / used root / run folder exists / game running).
  Launch     with the plan's token only: rechecked immediately before the start (under the operation lock + a per-profile
             results\\LAUNCH.lock), then `g_run.py run td_run --authorize-runtime RUN:SHA12 ...` (nothing parallel).
  Stop       ends only the process tree this launch owns: the game pid from OUR session's guard POPEN event, verified as a
             descendant of our g_run pid with that image, TerminateProcess(STOP_EXIT_CODE); after a grace the runner's tree by
             pid (taskkill /PID /T /F). Never by image name. Who stopped is recorded.
  Results    results\\launch_<time>.json + LAUNCH.json: normal exit / runner boot-window end / operator stop / timeout / host
             (probe) STOP / crash / runner refused / unresolved, with the run folder, session, log.txt, result.json, guard events.
             Visual correctness is never claimed from log lines.

    py -3 -B wb_profile.py check|prepare PACKAGE [PACKAGE ...] HOST_EXE PROFILE_DIR --approvals FILE [--predecessor DIR] [--new-root]
    py -3 -B wb_profile.py check|prepare --draft FILE
    py -3 -B wb_profile.py draft FILE [--add PACKAGE ...] [--remove MOD_ID|PACKAGE ...] [--host EXE] [--approvals FILE]
                                      [--dest DIR] [--from-profile DIR] [--predecessor DIR] [--new-root]
    py -3 -B wb_profile.py status|preflight|dryrun PROFILE_DIR          (all: [--config FILE] [--kit DIR])
    py -3 -B wb_profile.py launch-plan|results PROFILE_DIR
    py -3 -B wb_profile.py launch PROFILE_DIR --authorize-runtime RUN:SHA12 [--plan-id ID]   (REAL run: owner present; Ctrl+C = Stop)
       launch-plan / launch: [--preset boot|visible] [--secs N] [--dump-flips a,b,c] [--capture-every S]        (v0.9)
    py -3 -B wb_profile.py successor PROFILE_DIR --dest NEW_PROFILE_DIR [--approvals FILE] [--check]   (v0.9: always a NEW root)
v0.10 mod-installation preview + draft actions:
    py -3 -B wb_profile.py preview MOD_FOLDER [--draft FILE|PROFILE_DIR] [--host EXE] [--approvals FILE] [--json]   (read only)
    py -3 -B wb_profile.py draft FILE [--add PACKAGE] [--enable|--disable|--remove MOD_ID|PACKAGE] ... [--even-if-required]
  preview = DECLARED metadata (mod.toml, staging record) vs VERIFIED bytes (sha256 now) vs HOST READERS (bmpack validate of
  the draft's enabled members with / without the mod); labels are not a code-safety assessment. Draft actions are computed
  in memory and written in one atomic replace (a refusal or failure leaves the draft file byte for byte); a switched-off
  package stays in the draft (`disabled`), Prepare copies it and writes state\\mod-list.toml `disabled = [ids]` (the host's
  own switch: modfs enabled=0, skipped by the host's admission), and admission runs over the enabled members only.
v0.9: a "visible manual test" preset (td_run --window + optional --dump-flips, Workbench window captures of the OWNED game pid
via wb_capture.py), the game's own exit code from a handle the launch keeps on it, and an explicit successor with a new root.
"""
import getpass
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wb_core as core  # noqa: E402
import wb_kit  # noqa: E402
import wb_stage  # noqa: E402

SCHEMA = 'bm-workbench-profile/2'                  # v0.7: members
SCHEMA_V1 = 'bm-workbench-profile/1'               # v0.6: one plugin (still read)
DRAFT_SCHEMA = 'bm-workbench-profile-draft/2'      # v0.10: + disabled (package folders kept but switched off)
DRAFT_SCHEMA_V1 = 'bm-workbench-profile-draft/1'   # v0.7-v0.9 drafts (still read: every package on)
NAME_RE = re.compile(r'^wbp_[a-z0-9][a-z0-9_-]{1,38}$')
MODS = 'plugins'                                   # TAKEDAWN_MODS root inside a profile (v0.6 name kept; holds data mods too)
LAUNCHER = 'td_run'                                # g_run's registered boot-scene launcher (tools\runners\README.md "boot-only check")
BOOT_SECS = '20'
GAME_PROC = re.compile(r'^"(burnout3[^"]*|takedawn[^"]*)"', re.I)
# the kit's own bmpack validate, called the way bmpack.py main calls it for `validate --json` (configure + validate); the mod
# folders come from a JSON file because 256+ folders do not fit on a Windows command line
BMPACK_DRIVER = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import bmpack
q = json.load(open(sys.argv[2], encoding='utf-8'))
try:
    getattr(bmpack.bmkit_env, 'check_python', lambda: None)()
    bmpack.configure(game_data=q['game_data'], cc=q['cc'], cache=q['cache'])
    rep = bmpack.validate(q['roots'])
except bmpack.BmpackError as e:
    print(json.dumps({'error': 'bmpack: REFUSED: %s' % e}))
    sys.exit(1)
except bmpack.bmkit_env.BmkitError as e:
    print(json.dumps({'error': 'bmpack: CANNOT RUN: %s' % e}))
    sys.exit(3)
rep['host_readers'] = bmpack.host_readers_id()
rep['bmpack_version'] = bmpack.TOOL_VERSION
print(json.dumps(rep))
sys.exit(0 if rep.get('ok') else 1)
'''


# ------------------------------------------------------------------------------------------------ places
def runner_paths(cfg):
    """the guarded runner and the folders its guard allows -> dict or None"""
    g = cfg.get('runner') or (os.path.join(core.PC, 'tools', 'runners', 'g_run.py') if core.PC else '')
    if not g or not os.path.isfile(g):
        return None
    pc = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(g))))
    rt = os.path.join(pc, 'runtime_data')
    return {'g_run': os.path.abspath(g), 'pc': pc, 'rt': rt, 'modsets': os.path.join(rt, 'modsets'),
            'roots': os.path.join(rt, 'roots'), 'runs': os.path.join(rt, 'runs'), 'base': os.path.join(rt, 'base'),
            'build': os.path.join(pc, 'build')}


def runner_problems(rp):
    if not rp:
        return ['guarded runner not found (tools\\runners\\g_run.py of the workspace; Settings "runner" in workbench.json)']
    return ['runner folder missing: %s' % rp[k] for k in ('modsets', 'roots', 'runs', 'base', 'build') if not os.path.isdir(rp[k])]


def _under(p, d):
    p, d = os.path.normcase(os.path.realpath(p)), os.path.normcase(os.path.realpath(d))
    return p.startswith(d.rstrip('\\') + '\\')


def _same_path(a, b):
    return bool(a and b) and os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def dest_problems(rp, dest):
    if not dest or not os.path.isabs(dest):
        return ['profile folder: give a full path runtime_data\\modsets\\wbp_<name> (got %r)' % dest]
    if '..' in dest.replace('/', '\\').split('\\'):
        return ['profile folder: ".." is not allowed: %s' % dest]
    dest = os.path.normpath(dest)
    name = os.path.basename(dest)
    out = []
    if os.path.normcase(os.path.realpath(os.path.dirname(dest))) != os.path.normcase(os.path.realpath(rp['modsets'])):
        out.append('profile folder must be directly inside %s (the only place the guarded runner loads mods and approvals '
                   'from); refused: %s' % (rp['modsets'], dest))
    if not NAME_RE.match(name):
        out.append('profile name %r: "wbp_" then lower-case letters, digits, "_" or "-" (3-40 characters)' % name)
    for p in (dest, os.path.join(rp['roots'], name), os.path.join(rp['runs'], name + '_dry')):
        if os.path.exists(p):
            out.append('exists, never reused or overwritten: %s (prepared profiles are immutable: choose a new profile '
                       'name; a changed combination is a successor profile)' % p)
    return out


def files_digest(files):
    """one sha256 over a {relative path: sha256} map (a package's or a profile copy's identity)"""
    return hashlib.sha256(json.dumps(files or {}, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------ inputs
def read_package(cfg, pkg):
    """a staged package folder <dest>\\<folder> (plugin or data-only) -> (info, problems); bytes must equal its STAGE record"""
    if not pkg or not os.path.isdir(pkg):
        return None, ['staged package folder not found: %s' % pkg]
    pkg = os.path.abspath(pkg)
    rec = wb_stage.package_record(os.path.dirname(pkg), os.path.basename(pkg))
    if not rec:
        return None, ['%s has no Workbench staging record (.wb_stage beside it): stage it with the Workbench first' % pkg]
    plugin = rec.get('kind') in ('sdk-plugin', wb_stage.IMPORT_PLUGIN)      # v0.11: an imported plugin too
    bad = []
    cur = wb_stage.tree_hashes(pkg)
    mod = (rec.get('module') or {}) if plugin else {}
    if plugin:
        mpath = os.path.join(pkg, mod.get('file') or '?')
        if not os.path.isfile(mpath):
            bad.append('module %s missing in %s' % (mod.get('file'), pkg))
        elif cur.get(mod['file']) != mod.get('sha256'):
            bad.append('module bytes changed since staging: %s is %s, the record says %s (stage again)'
                       % (mod['file'], (cur.get(mod['file']) or '')[:12], (mod.get('sha256') or '')[:12]))
    if cur != rec.get('package_files'):
        bad.append('package files differ from the staging record (%s): stage again' %
                   ', '.join(sorted(k for k in set(cur) | set(rec.get('package_files') or {})
                                    if cur.get(k) != (rec.get('package_files') or {}).get(k)))[:200])
    if plugin:
        if not all(c.get('ok') for c in rec.get('validation') or [{}]):
            bad.append('the staging record has failed checks')
        if (rec.get('native_code') or {}).get('approved') is not False:
            bad.append('the staging record must say native_code.approved false (the Workbench never approves)')
    elif rec.get('bmpack') is not None and not (rec.get('bmpack') or {}).get('ok'):
        bad.append('the staging record says bmpack validate refused this data package')
    req, rbad = wb_kit.requirements(os.path.join(pkg, 'mod.toml'))
    bad += rbad
    mod_id = rec.get('mod_id')
    if req and req.get('id') != mod_id:
        bad.append('mod.toml id %r != the record\'s mod id %r' % (req.get('id'), mod_id))
    if req and not plugin and req.get('has_plugin'):
        bad.append('mod.toml declares [plugin] (native code) but the staging record is a data package: stage it as a plugin')
    rp_ = os.path.join(os.path.dirname(pkg), '.wb_stage', 'packages', os.path.basename(pkg) + '.json')
    rp_ = rp_ if os.path.isfile(rp_) else None
    return {'package': pkg, 'record': rec, 'record_path': rp_, 'provenance': wb_stage.provenance_text(rec),
            'record_sha256': wb_kit.sha256_file(rp_) if rp_ else None, 'recipe': rec.get('recipe'),
            'mod_id': mod_id, 'version': (req or {}).get('version'), 'name': (req or {}).get('name'),
            'kind': 'plugin' if plugin else 'data', 'module': mod.get('file'), 'module_sha256': mod.get('sha256'),
            'requirements': req, 'kit_identity': rec.get('kit_identity'), 'files': cur, 'digest': files_digest(cur)}, bad


def host_problems(rp, host):
    if not host:
        return ['host exe not found']
    out = []
    if not _under(host['path'], rp['build']):
        out.append('host must be under %s (the guarded runner only starts hosts from there; the game installation is never '
                   'used): %s' % (rp['build'], host['path']))
    if not host['sdl2']:
        out.append('no SDL2.dll beside the host exe (a host folder: exe + SDL2.dll + shaders): %s' % host['path'])
    if not host.get('build_identity'):
        out.append('no Burnout Mashup platform build identity in the host (found %s): not a platform host'
                   % (host.get('build_identities_found') or 'none'))
    return out


def known_kits(cfg, pkg_kits=()):
    """kits that may describe hosts: the current kit, and the kits the packages were built with (if still there unchanged)"""
    out = [wb_kit.kit_identity(cfg.get('kit'))]
    for pk in pkg_kits:
        pk = pk or {}
        if pk.get('path') and os.path.isdir(pk['path']):
            k = wb_kit.kit_identity(pk['path'])
            if k and k['id'] == pk.get('id') and not any(wb_kit.same(k, x) for x in out):
                out.append(k)
    return [k for k in out if k]


def member_compat(k, host, members):
    """host / service compatibility of every member (offered services, never kit version equality) -> problems"""
    bad = []
    for m in members:
        req = m.get('requirements') or {}
        bad += ['%s: %s' % (m['mod_id'], b) for b in wb_kit.compat_problems(req, k['platform'], k['services'],
                                                                             plugin=m.get('kind') == 'plugin',
                                                                             tables=k.get('tables'))]
    if host.get('platform') and host['platform'] != k['platform']:
        bad.append('host build says platform %s, its service table says %s' % (host['platform'], k['platform']))
    return ['incompatible: ' + b for b in bad]


def approval_status(path, mod_id, sha):
    """the player's own approvals file (plugin-approvals.toml format) -> (ok, line, detail). Read only."""
    line = '%s sha256:%s' % (mod_id, sha)
    if not path:
        return False, line, 'no approvals file given'
    try:
        t = tomllib.loads(open(path, encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return False, line, 'approvals file unreadable: %s' % e
    lst = t.get('approved') if isinstance(t.get('approved'), list) else []
    if line in lst:
        return True, line, 'approved by the player in %s' % path
    other = [x for x in lst if isinstance(x, str) and x.startswith(mod_id + ' ')]
    return False, line, ('the approvals file approves other bytes of %s (%s), not these' % (mod_id, ', '.join(x[-64:][:12] for x in other))
                         if other else 'no approval for %s in %s' % (mod_id, path))


def admission(cfg, kit, roots, log=None):
    """the host's own admission over mod folders / one mod set folder: the describing kit's bmpack validate (its host readers)
    -> {ok, kit, order [{id, version, usable, why}], refusals, dependency_moved, readers, bmpack, error}"""
    out = {'ok': False, 'kit': (kit or {}).get('id'), 'roots': len(roots), 'order': [], 'refusals': [], 'error': None}
    if not kit:
        out['error'] = 'no kit describes the host: its admission rules are unknown'
        return out
    bdir = os.path.join(kit['path'], 'tools', 'bmpack')
    miss = core.bmpack_prereqs(dict(cfg, kit=kit['path']), need_game=True)
    if miss:
        out['error'] = 'host admission cannot run (bmpack validate): ' + '; '.join(miss)
        return out
    qd = os.path.join(cfg['state'], 'admission')
    os.makedirs(qd, exist_ok=True)
    qf = os.path.join(qd, 'roots_%d_%d.json' % (os.getpid(), threading.get_ident()))
    with open(qf, 'w', encoding='utf-8') as f:
        json.dump({'roots': [os.path.abspath(r) for r in roots], 'game_data': cfg['game_data'], 'cc': cfg['cc'],
                   'cache': cfg['bmpack_cache']}, f)
    argv = [cfg['python'], '-B', '-c', BMPACK_DRIVER, bdir, qf]
    if log:
        log('# host admission: %s bmpack validate (%s host readers) over %d folder(s)' % (kit['id'], bdir, len(roots)))
    try:
        p = subprocess.run(argv, capture_output=True, text=True, cwd=bdir, timeout=1800, encoding='utf-8', errors='replace',
                           creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        try:
            os.remove(qf)
        except OSError:
            pass
    js = [l for l in p.stdout.splitlines() if l.startswith('{')]
    try:
        rep = json.loads(js[-1])
    except (IndexError, ValueError):
        out['error'] = 'bmpack validate gave no report (exit %s): %s %s' % (p.returncode, p.stdout[-300:], p.stderr[-300:])
        return out
    if rep.get('error'):
        out['error'] = rep['error']
        return out
    out.update(ok=bool(rep.get('ok')) and p.returncode == 0, rc=p.returncode, readers=rep.get('host_readers'),
               bmpack=rep.get('bmpack_version'), dependency_moved=rep.get('dependency_moved', 0),
               order=[{'id': m.get('id'), 'version': m.get('version'), 'usable': bool(m.get('usable')),
                       'dir': m.get('dir'), 'why': m.get('needs') or ''}
                      for m in sorted(rep.get('mods') or [], key=lambda m: m.get('order', 0))],
               refusals=[{'service': f.get('service'), 'mod': f.get('mod'), 'why': f.get('why')}
                         for f in rep.get('refusals') or []])
    if log:
        log('# host admission: %s; order %s; refusals %s' % ('ACCEPTED' if out['ok'] else 'REFUSED',
                                                             [(m['id'], m['version'], m['usable']) for m in out['order']],
                                                             out['refusals']))
    return out


def admission_problems(a):
    if a.get('error'):
        return ['host admission: ' + a['error']]
    if a.get('ok'):
        return []
    return ['host admission (%s readers, bmpack validate) refuses [%s] %s: %s' % (a['kit'], f['service'], f['mod'] or '-', f['why'])
            for f in a['refusals']] or ['host admission (%s readers) refused the combination' % a['kit']]


def game_processes():
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=30,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return ['(tasklist failed)']
    return [m.group(1) for m in (GAME_PROC.match(l) for l in out.splitlines()) if m]


def _pkgs(packages):
    if not packages:
        return []
    return [packages] if isinstance(packages, str) else [p for p in packages if p]


def _member_public(m):
    return {k: v for k, v in m.items() if k != 'record'}


def changes_between(old_members, new_members, old_host, new_host, old_kit, new_kit):
    o = {m['mod_id']: m.get('digest') for m in old_members}
    n = {m['mod_id']: m.get('digest') for m in new_members}
    out = {'added': sorted(set(n) - set(o)), 'removed': sorted(set(o) - set(n)),
           'changed_bytes': sorted(i for i in set(o) & set(n) if o[i] != n[i]),
           'host_changed': (old_host or {}).get('sha256') != (new_host or {}).get('sha256'),
           'kit_changed': not wb_kit.same(old_kit, new_kit)}
    oo = {m['mod_id'] for m in old_members if m.get('enabled', True)}       # v0.10: switch changes (keys only when any)
    no = {m['mod_id'] for m in new_members if m.get('enabled', True)}
    if sorted((oo - no) & set(n)):
        out['switched_off'] = sorted((oo - no) & set(n))
    if sorted((no - oo) & set(o)):
        out['switched_on'] = sorted((no - oo) & set(o))
    return out


def changes_text(c):
    if not c:
        return 'none'
    p = ['added %s' % ', '.join(c['added'])] if c['added'] else []
    p += ['removed %s' % ', '.join(c['removed'])] if c['removed'] else []
    p += ['other bytes: %s' % ', '.join(c['changed_bytes'])] if c['changed_bytes'] else []
    p += ['switched off %s' % ', '.join(c['switched_off'])] if c.get('switched_off') else []
    p += ['switched on %s' % ', '.join(c['switched_on'])] if c.get('switched_on') else []
    p += ['host changed'] if c['host_changed'] else []
    p += ['kit changed'] if c['kit_changed'] else []
    return '; '.join(p) or 'same composition (a new profile with the same members)'


def root_marker(root):
    try:
        return json.load(open(os.path.join(root, '.g_disposable.json'), encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None


def _off_set(disabled):
    return {os.path.normcase(os.path.abspath(p)) for p in disabled or () if p}


def is_off(pkg, disabled):
    """v0.10: a draft's package switched off (draft 'disabled' = package folders)"""
    return bool(pkg) and os.path.normcase(os.path.abspath(pkg)) in _off_set(disabled)


def admission_roots(members, folder_of=lambda m: m['package']):
    """v0.10: the folders the host admits = the ENABLED members in mod-id order (modfs: one root, by id). The host's modfs marks
    mod-list.toml `disabled` ids enabled=0 and its admission (bm_admit.c admit_cb) skips them (a dependant names them
    "switched off"); the kit's bmpack validate does not read mod-list.toml, so the switched-off folders are left out here."""
    on = [m for m in members if m.get('enabled', True)]
    return [folder_of(m) for m in sorted(on, key=lambda m: (m['mod_id'] or '', os.path.normcase(folder_of(m))))]


NOT_INSTALLED_RE = re.compile(r'requires_mods "([^"]+)": not installed')
NEED_NOT_INSTALLED_RE = re.compile(r'needs (.+): not installed$')


def admission_switched(cfg, kit, members, folder_of=lambda m: m['package'], log=None):
    """v0.11: the host's admission of a set with switched-off members, as the host does it. The kit's checker cannot mark a
    folder switched off (bmpack_check.c takes ROOT=i DIR pairs only), so:
      1. the ENABLED folders (mod-id order) -> admission, order, clashes, dependencies (as v0.10);
      2. a dependency the enabled pass calls "not installed" but that is a switched-off member gets the host's own text
         (bm_admit.c: 'requires_mods "<rq>": installed but switched off: mod <id> <version> (<folder>)', need "switched off");
      3. ALL folders (enabled + switched off) -> only the loader's own modfs refusals are taken from this pass: the mod cap
         ("more than N mods: the loader ignores it", modfs find_mods counts every folder) and shared ids ("is also used by",
         modfs refuses a shared id before the mod-list switch). Without switched-off members this is plain admission()."""
    off = [m for m in members if not m.get('enabled', True)]
    on_roots = admission_roots(members, folder_of)
    if not off:
        return admission(cfg, kit, on_roots, log)
    a = admission(cfg, kit, on_roots, log) if on_roots else {'ok': False, 'kit': (kit or {}).get('id'), 'order': [],
                                                             'refusals': [], 'error': 'every mod is switched off'}
    par = {'switched_off': sorted(m['mod_id'] for m in off), 'rewritten': [], 'loader_refusals': []}
    offs = {m['mod_id']: m for m in off}
    for f in a.get('refusals') or []:
        mt = NOT_INSTALLED_RE.search(f.get('why') or '')
        if mt and mod_ref_id(mt.group(1)) in offs:
            o = offs[mod_ref_id(mt.group(1))]
            f['why'] = f['why'][:mt.start()] + 'requires_mods "%s": installed but switched off: mod %s %s (%s)' % (
                mt.group(1), o['mod_id'], o.get('version') or '-', folder_of(o)) + f['why'][mt.end():]
            par['rewritten'].append(f.get('mod'))
    for x in a.get('order') or []:
        mt = NEED_NOT_INSTALLED_RE.search(x.get('why') or '')
        if mt and mod_ref_id(mt.group(1)) in offs:
            x['why'] = 'needs %s: switched off' % mt.group(1)
    if not a.get('error'):
        allr = [folder_of(m) for m in sorted(members, key=lambda m: (m['mod_id'] or '', os.path.normcase(folder_of(m))))]
        b = admission(cfg, kit, allr, log)
        if b.get('error'):
            a['error'] = 'the loader pass over every folder (switched off included) could not run: %s' % b['error']
        else:
            seen = {(f.get('service'), f.get('mod'), f.get('why')) for f in a['refusals']}
            for f in b.get('refusals') or []:
                w = f.get('why') or ''
                if f.get('service') == 'modfs' and ('mods: the loader ignores it' in w or 'is also used by' in w) and \
                        (f.get('service'), f.get('mod'), w) not in seen:
                    a['refusals'].append(dict(f, pass_='every folder (switched-off ones count for the loader)'))
                    par['loader_refusals'].append(f.get('mod'))
                    a['ok'] = False
    a['parity'] = par
    if log:
        log('# admission parity: switched off %s; reasons rewritten %s; loader refusals from every folder %s'
            % (par['switched_off'], par['rewritten'], par['loader_refusals']))
    return a


def inspect(cfg, packages, host_exe, dest, approvals, predecessor=None, reuse_root=True, disabled=()):
    """what Prepare would do and why it would refuse -> {problems, members, host, admission, ...}. Writes nothing.
    v0.10: `disabled` = package folders kept in the profile but switched off (mod-list.toml `disabled`, the host's switch)."""
    rp = runner_paths(cfg)
    bad = runner_problems(rp)
    pk = _pkgs(packages)
    ck = wb_kit.kit_identity(cfg.get('kit'))
    off = [p for p in _pkgs(disabled)]
    info = {'kind': 'profile-check', 'packages': pk, 'host_exe': host_exe, 'dest': dest, 'approvals': approvals,
            'predecessor': predecessor or None, 'kit_identity': wb_kit.stamp(ck), 'disabled': off}
    if bad:
        return dict(info, problems=bad)
    if not cfg.get('kit'):
        bad.append('kit: ' + core.check_value('kit', ''))
    bad += dest_problems(rp, dest)
    if not pk:
        bad.append('no staged package selected: add at least one')
    members, readable = [], True
    seen = {}
    for p in pk:
        m, pbad = read_package(cfg, p)
        bad += ['%s: %s' % (os.path.basename(os.path.normpath(p)), x) for x in pbad]
        if not m:
            readable = False
            continue
        key = os.path.normcase(m['package'])
        if key in seen:
            bad.append('%s is listed twice' % m['package'])
            continue
        seen[key] = 1
        m['enabled'] = not is_off(m['package'], off)
        members.append(m)
    for p in off:
        if os.path.normcase(os.path.abspath(p)) not in {os.path.normcase(os.path.abspath(x)) for x in pk}:
            bad.append('switched off but not in the list: %s (a draft switches off its own packages only)' % p)
    if members and not any(m['enabled'] for m in members):
        bad.append('every mod is switched off: enable at least one (nothing would be admitted or tested)')
    ids = [m['mod_id'] for m in members]
    for i in sorted(set(x for x in ids if ids.count(x) > 1)):
        bad.append('duplicate mod id %s (%s): a profile holds each mod id once (%s\\<mod id>), and the host refuses a shared '
                   'id' % (i, ', '.join(m['package'] for m in members if m['mod_id'] == i), MODS))
    host = wb_kit.host_identity(host_exe)
    bad += host_problems(rp, host) if host else ['host exe not found: %s' % host_exe]
    info.update(members=[_member_public(m) for m in members], host=host)
    k = None
    if host:
        k, why = wb_kit.describe_host(host, known_kits(cfg, [m.get('kit_identity') for m in members]))
        info['host_why'] = why
        if not k:
            bad.append('incompatible host: ' + why)
        else:
            info.update(host_described_by=k['id'], host_services=k['services'], host_kit=k)
            bad += member_compat(k, host, [m for m in members if m['enabled']])
            offc = member_compat(k, host, [m for m in members if not m['enabled']]) if len(members) > sum(
                m['enabled'] for m in members) else []
            info['disabled_notes'] = ['switched off (not admitted, so not refused): ' + x for x in offc]
    plugins = [m for m in members if m['kind'] == 'plugin' and m['enabled']]
    for m in members:
        if m['kind'] != 'plugin':
            m['approval'] = {'needed': False, 'ok': True, 'line': None, 'detail': 'data only, no native code'}
            continue
        ok, line, detail = approval_status(approvals, m['mod_id'], m['module_sha256'])
        if not m['enabled']:                                  # v0.10: the host never loads a switched-off plugin
            m['approval'] = {'needed': False, 'ok': ok, 'line': line, 'file': approvals,
                             'detail': 'switched off: not loaded, so no approval needed now (%s); its line is NOT copied into '
                                       'the profile - switching it on is a successor that needs your approval' % detail}
            continue
        m['approval'] = {'needed': True, 'ok': ok, 'line': line, 'detail': detail, 'file': approvals}
        if not ok:
            bad.append('missing approval: %s. The Workbench never approves code: review the module, then add the line "%s" '
                       'to your approvals file yourself (or approve it on the game\'s MODS page) and choose that file'
                       % (detail, line))
    if approvals and plugins and not os.path.isfile(approvals):
        bad.append('approvals file not found: %s' % approvals)
    info['members'] = [_member_public(m) for m in members]
    notes = []
    for m in members:
        pkk = m.get('kit_identity')
        notes.append('%s built with the current kit %s' % (m['mod_id'], ck['id']) if wb_kit.same(pkk, ck) else
                     '%s built with kit %s, current kit %s: allowed when the host offers what mod.toml needs (checked '
                     'above); the kit version itself is not required to match' % (m['mod_id'], (pkk or {}).get('id'), (ck or {}).get('id')))
    info['kit_note'] = '; '.join(notes)
    if members and readable and k and any(m['enabled'] for m in members):
        a = admission_switched(cfg, k, members)                  # modfs: one root, by id; switched off: v0.11 parity
        info['admission'] = a
        bad += admission_problems(a)
    elif members:
        info['admission'] = {'ok': False, 'error': 'not run (a package is unreadable or no kit describes the host)'}
    if predecessor:
        pp, pbad = load_profile(predecessor)
        if not pp:
            bad += ['predecessor: ' + x for x in pbad]
        elif _same_path(predecessor, dest):
            bad.append('the successor must be a new profile folder (a prepared profile is never changed)')
        else:
            info['changes'] = changes_between(pp['members'], members, pp['host'], host, pp.get('kit_identity'), ck)
            info['predecessor_name'] = pp.get('name')
            mk = root_marker(pp.get('root'))
            if not reuse_root:
                info['root_plan'] = 'new (g_run make-root): requested'
            elif mk and mk.get('used_by') is None and mk.get('verified_sha256'):
                info['adopt_root'] = pp['root']
                info['root_plan'] = 'adopt the predecessor\'s unused verified root %s (no 2.4 GB copy)' % pp['root']
            else:                                               # v0.8: never a silent fallback - a new root is explicit
                info['root_plan'] = 'none: the predecessor\'s root %s is %s' % (
                    pp.get('root'), 'used by %s' % mk.get('used_by') if mk else 'missing / unreadable')
                bad.append('the predecessor\'s data root %s is %s: a used root is never reused or repaired; prepare this '
                           'successor with a NEW root explicitly (untick "reuse the predecessor\'s data root", CLI --new-root)'
                           % (pp.get('root'), 'used by %s' % mk.get('used_by') if mk else 'missing / unreadable'))
    else:
        info['root_plan'] = 'new (g_run make-root)'
    info['problems'] = bad
    return info


# ------------------------------------------------------------------------------------------------ profile records
def _v1_members(d):
    files = d.get('package_files') or {}
    return [{'mod_id': d.get('mod_id'), 'version': (d.get('requirements') or {}).get('version'), 'kind': 'plugin',
             'package': d.get('package'), 'package_record': d.get('package_record'), 'folder': '%s/%s' % (MODS, d.get('mod_id')),
             'files': files, 'digest': files_digest(files), 'module': d.get('module'), 'module_sha256': d.get('module_sha256'),
             'requirements': d.get('requirements'), 'package_kit_identity': d.get('package_kit_identity'),
             'approval': {'needed': True, 'line': (d.get('approval') or {}).get('line'),
                          'source': (d.get('approval') or {}).get('source')}}]


def load_profile(dest):
    """PROFILE.json of a v0.7 (schema /2) or v0.6 (schema /1, one plugin) profile -> (profile with 'members', problems)"""
    try:
        d = json.load(open(os.path.join(dest, 'PROFILE.json'), encoding='utf-8'))
    except (OSError, ValueError, TypeError) as e:
        return None, ['not a Workbench test profile (PROFILE.json): %s' % e]
    if d.get('schema') == SCHEMA_V1:
        d['members'] = _v1_members(d)
    elif d.get('schema') != SCHEMA:
        return None, ['PROFILE.json schema is not %s or %s' % (SCHEMA, SCHEMA_V1)]
    return d, []


def _write_json(path, data):
    tmp = path + '.wb_tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except BaseException:                                          # v0.10: the old file stays as it was, no temp left
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _history(dest, entry):
    with open(os.path.join(dest, 'history.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def read_history(dest):
    out = []
    try:
        for l in open(os.path.join(dest, 'history.jsonl'), encoding='utf-8'):
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def read_mod_list(path):
    """v0.10: a profile's state\\mod-list.toml -> (sorted disabled ids, problem or None). Read only. (The host treats an
    unreadable list as "every mod on"; a profile's list must be exactly the recorded one.)"""
    try:
        t = tomllib.loads(open(path, encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, 'mod list unreadable: %s' % e
    d = t.get('disabled', [])
    if not isinstance(d, list) or not all(isinstance(x, str) for x in d):
        return None, 'mod list: disabled must be a list of ids'
    return sorted(set(d)), None


def composition_now(dest, prof):
    """what the profile holds NOW: {members: {folder: digest of its files}, host_sha256, disabled (v0.10)}"""
    mods = os.path.join(dest, MODS)
    names = sorted(n for n in os.listdir(mods) if os.path.isdir(os.path.join(mods, n))) if os.path.isdir(mods) else []
    hp = prof['host']['path']
    off, bad = read_mod_list(os.path.join(dest, 'state', 'mod-list.toml'))
    return {'members': {n: files_digest(wb_stage.tree_hashes(os.path.join(mods, n))) for n in names},
            'host_sha256': wb_kit.sha256_file(hp) if os.path.isfile(hp) else None,
            'disabled': off if not bad else ['(unreadable)']}


def stale_why(rec, what, prof, dest, now, ck):
    """why a recorded preflight / dry run no longer describes the profile ([] = still valid). Kit first."""
    why = []
    if not wb_kit.same(rec.get('kit_identity'), ck):
        why.append('kit changed since the %s (%s -> %s): run Preflight again' % (what, (rec.get('kit_identity') or {}).get('id'),
                                                                               (ck or {}).get('id')))
    c = rec.get('composition')
    if c is None:                                               # a v0.6 record: one module + the host
        m = prof['members'][0]
        mp = os.path.join(dest, MODS, m['mod_id'], m['module'] or '?')
        if not os.path.isfile(mp) or wb_kit.sha256_file(mp) != rec.get('module_sha256'):
            why.append('module bytes changed since the %s' % what)
        if set(now['members']) != {m['mod_id']}:
            why.append('membership changed since the %s: %s holds %s' % (what, MODS, sorted(now['members'])))
    else:
        a, b = set(c['members']), set(now['members'])
        if a != b:
            why.append('membership changed since the %s: %s' % (what, '; '.join(
                (['added %s' % ', '.join(sorted(b - a))] if b - a else []) + (['removed %s' % ', '.join(sorted(a - b))] if a - b else []))))
        ch = sorted(i for i in a & b if c['members'][i] != now['members'][i])
        if ch:
            why.append('files changed since the %s: %s' % (what, ', '.join(ch)))
        if 'disabled' in c and c['disabled'] != now.get('disabled'):          # v0.10 records only
            why.append('mod list (switched off) changed since the %s: %s -> %s' % (what, c['disabled'], now.get('disabled')))
    if (c or rec).get('host_sha256') != now['host_sha256']:
        why.append('host bytes changed since the %s' % what)
    return why


def results(dest):
    """every recorded preflight / dry run of a profile, oldest first (results\\ from v0.7; v0.6 profiles: the two files)"""
    out = []
    rd = os.path.join(dest, 'results')
    if os.path.isdir(rd):
        for n in sorted(os.listdir(rd)):
            m = re.match(r'^(preflight|dryrun)_.*\.json$', n)
            if m:
                try:
                    out.append((m.group(1), os.path.join(rd, n), json.load(open(os.path.join(rd, n), encoding='utf-8'))))
                except (OSError, ValueError):
                    pass
    seen = {(k, r.get('time')) for k, _, r in out}
    for kind, f in (('preflight', 'PREFLIGHT.json'), ('dryrun', 'DRYRUN.json')):     # v0.6 records (no results\ copy)
        try:
            r = json.load(open(os.path.join(dest, f), encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (kind, r.get('time')) not in seen:
            out.append((kind, os.path.join(dest, f), r))
    return sorted(out, key=lambda x: (x[2].get('time') or '', x[0] == 'dryrun'))


def profile_record_problems(dest, prof):
    """a v0.7 profile's PROFILE.json must still have the bytes Prepare wrote (its history says which)"""
    if prof.get('schema') != SCHEMA:
        return []
    ent = [h for h in read_history(dest) if h.get('action') == 'prepare' and h.get('profile_sha256')]
    if not ent:
        return ['no prepare entry with the PROFILE.json sha256 in history.jsonl']
    cur = wb_kit.sha256_file(os.path.join(dest, 'PROFILE.json'))
    return [] if cur == ent[0]['profile_sha256'] else ['PROFILE.json changed since Prepare (%s, prepared %s)' % (cur[:12], ent[0]['profile_sha256'][:12])]


def preflight_checks(cfg, dest):
    """-> (profile, checks [{check, ok, detail}]). Read only."""
    prof, bad = load_profile(dest)
    if not prof:
        return None, [{'check': 'profile', 'ok': False, 'detail': bad[0]}]
    rp = runner_paths(cfg)
    C = []

    def add(name, ok, detail):
        C.append({'check': name, 'ok': bool(ok), 'detail': detail})
    rb = runner_problems(rp)
    add('guarded runner', not rb, '; '.join(rb) or rp['g_run'])
    if rb:
        return prof, C
    if prof.get('schema') == SCHEMA:
        pr = profile_record_problems(dest, prof)
        add('profile record unchanged', not pr, '; '.join(pr) or 'PROFILE.json = the bytes Prepare wrote')
    members = prof['members']
    mods = os.path.join(dest, MODS)
    present = sorted(n for n in os.listdir(mods) if os.path.isdir(os.path.join(mods, n))) if os.path.isdir(mods) else []
    want = sorted(m['mod_id'] for m in members)
    add('membership = the profile\'s', present == want, '%s holds %s (recorded %s)' % (MODS, present, want))
    v1 = prof.get('schema') == SCHEMA_V1
    for m in members:
        d = os.path.join(mods, m['mod_id'])
        cur = wb_stage.tree_hashes(d) if os.path.isdir(d) else {}
        if m['kind'] == 'plugin':
            s = cur.get(m['module'])
            add('module bytes = the profile\'s (%s)' % m['mod_id'], s == m['module_sha256'],
                '%s %s (recorded %s)' % (m['module'], (s or 'missing')[:12], (m['module_sha256'] or '')[:12]))
        if not v1:
            add('files = the profile\'s (%s)' % m['mod_id'], files_digest(cur) == m['digest'],
                '%d files, digest %s (recorded %s)' % (len(cur), files_digest(cur)[:12], m['digest'][:12]))
        pkg, pbad = read_package(cfg, m['package'])
        add('staged package unchanged (%s)' % m['mod_id'],
            not pbad and pkg and pkg['digest'] == m['digest'] and pkg.get('module_sha256') == m.get('module_sha256'),
            '; '.join(pbad) or ('%s digest %s (recorded %s)' % (m['package'], (pkg or {}).get('digest', '')[:12], m['digest'][:12])))
    hp = prof['host']['path']
    hcur = wb_kit.sha256_file(hp) if os.path.isfile(hp) else None
    add('host bytes = the profile\'s', hcur == prof['host']['sha256'], '%s %s (recorded %s)' % (hp, (hcur or 'missing')[:12],
                                                                                          prof['host']['sha256'][:12]))
    appr = os.path.join(dest, 'state', 'plugin-approvals.toml')
    for m in members:
        if m['kind'] == 'plugin' and m.get('enabled', True):         # v0.10: a switched-off plugin is not loaded
            ok, line, detail = approval_status(appr, m['mod_id'], m['module_sha256'])
            add('approval of these exact bytes (%s)' % m['mod_id'], ok, detail)
    host = wb_kit.host_identity(hp)
    k = None
    if host:
        k, why = wb_kit.describe_host(host, known_kits(cfg, [m.get('package_kit_identity') for m in members]))
        cb = member_compat(k, host, [m for m in members if m.get('enabled', True)]) if k else ['incompatible host: ' + why]
        add('host / service compatibility', not cb, '; '.join(cb) or why)
    else:
        add('host / service compatibility', False, 'host missing')
    want_off = sorted(prof.get('disabled') or [])                 # v0.10 (absent: every mod on)
    have_off, mlbad = read_mod_list(os.path.join(dest, 'state', 'mod-list.toml'))
    add('mod list = the profile\'s (switched off)', not mlbad and have_off == want_off,
        mlbad or 'disabled %s (recorded %s)' % (have_off, want_off))
    if not (k and os.path.isdir(mods)):
        a = {'ok': False, 'error': 'not run (no host description / no %s folder)' % MODS}
    elif not want_off:
        a = admission(cfg, k, [mods])
    else:                                                           # v0.11: the host's parity with switched-off members
        a = admission_switched(cfg, k, [dict(m, enabled=m['mod_id'] not in want_off) for m in members],
                               lambda m: os.path.join(mods, m['mod_id']))
    add('host admission (bmpack validate%s)' % (', %s readers' % k['id'] if k else ''), a.get('ok'),
        '; '.join(admission_problems(a)) or 'ACCEPTED; load order %s' % ', '.join('%s %s' % (x['id'], x['version']) for x in a['order']))
    mk = root_marker(prof['root'])
    if mk is not None:
        add('data root unused', mk.get('used_by') is None and mk.get('verified_sha256'), '%s used_by %s%s' % (
            prof['root'], mk.get('used_by'), '' if mk.get('used_by') is None else
            ' (never reused or repaired: prepare a successor with a NEW root - Successor (new root) button / wb_profile.py successor PROFILE --dest NEW)'))
    else:
        add('data root unused', False, 'root marker unreadable: %s' % prof['root'])
    procs = game_processes()
    add('no game running', not procs, ', '.join(procs) or 'none')
    ck = wb_kit.kit_identity(cfg.get('kit'))
    add('current kit', bool(ck), wb_kit.short(ck))
    return prof, C


def next_dry(rp, name):
    d, k = name + '_dry', 2
    while os.path.exists(os.path.join(rp['runs'], d)):
        d, k = '%s_dry%d' % (name, k), k + 1
    return d


# ------------------------------------------------------------------------------------------------ launch (v0.8)
RUN_SUFFIX = '_run1'                                 # one real run per profile root: <profile>_run1
STOP_EXIT_CODE = 0x5770                              # TerminateProcess code of a Workbench stop (22384; td_run's own end is 1)
LAUNCH_MAX_WALL = 150.0                              # s: g_run start + boot 20 + td_run stop (wait <= 15) + margin
STOP_GRACE = 50.0                                    # s after the game is stopped before the runner's own tree is ended
LAUNCH_SCHEMA = 'bm-workbench-launch/1'
# the host's documented deliberate start stops (sdk060 docs LIMITS_AND_BEHAVIOURS.md "What still stops the start")
HOST_STOP_CODES = {88: 'track route data too large', 89: 'unit slots', 90: 'STATIC truncation', 91: 'capacity declaration',
                   92: 'content declaration / host out of memory', 93: 'tune', 94: 'added track in an unsupported mode',
                   95: 'World Tour launch', 96: 'World Tour data', 97: 'more lanes than the capacity'}
NTSTATUS = {0xC0000005: 'access violation', 0xC0000409: 'stack buffer overrun / fail fast', 0xC00000FD: 'stack overflow',
            0xC000001D: 'illegal instruction', 0xC0000374: 'heap corruption', 0xC0000135: 'DLL not found',
            0xC0000142: 'DLL initialisation failed', 0xC0000094: 'integer divide by zero', 0x80000003: 'breakpoint',
            0xC000013A: 'console control (Ctrl+C / close)'}
# v0.9 launch presets: both are td_run's boot scene (sleep N s, alive(), terminate()) - the visible one adds td_run's own
# --window (no --headless / RECOMP_HEADLESS) and optional --dump-flips (the host's RECOMP_FB_DUMP fb_NNN.bmp guest frames);
# window captures are the Workbench's (wb_capture.py, PrintWindow of the OWNED game pid). No host or runner change.
PRESETS = {
    'boot': {'label': 'headless boot smoke', 'window': False, 'secs': 20, 'dump_flips': '', 'capture_every': 0},
    'visible': {'label': 'visible manual test', 'window': True, 'secs': 300, 'dump_flips': '600,1800,3600', 'capture_every': 30},
}
WALL_MARGIN = 130.0                                  # wall limit = duration + this (g_run start, td_run stop wait 15 s, margin)
EARLY_EXIT_GRACE = 10.0                              # s: the game ended by itself, the runner still sleeping -> end its tree
RESULT_CLASSES = {'normal_exit': 'normal exit', 'runner_stop_boot_window': 'runner stop (boot-window end)',
                  'operator_stop': 'manual stop (operator)', 'timeout': 'timeout', 'probe_stop': 'probe / host STOP', 'crash': 'crash',
                  'runner_refused': 'runner refused (not launched)', 'unresolved': 'UNRESOLVED'}
VISUAL_NOTE = ('visual correctness NOT verified by the Workbench: log lines such as "[FETEX] ... texture(s) registered" or '
               '"[PLUGIN] ... running" show loading / registration only; window captures and frame dumps (if any) show what was '
               'drawn at those moments and must be looked at - a mod\'s art is shown only if its screen was reached')
CAPTURE_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wb_capture.py')
_W = {}


def _win():
    """kernel32 entry points (Toolhelp snapshot, process times / image / terminate), declared once"""
    if _W:
        return _W
    import ctypes
    from ctypes import wintypes as wt

    class PE(ctypes.Structure):
        _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wt.DWORD), ('cntThreads', wt.DWORD),
                    ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', ctypes.c_long), ('dwFlags', wt.DWORD),
                    ('szExeFile', ctypes.c_wchar * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.restype, k.CreateToolhelp32Snapshot.argtypes = wt.HANDLE, [wt.DWORD, wt.DWORD]
    for f in (k.Process32FirstW, k.Process32NextW):
        f.restype, f.argtypes = wt.BOOL, [wt.HANDLE, ctypes.POINTER(PE)]
    k.OpenProcess.restype, k.OpenProcess.argtypes = wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]
    k.CloseHandle.argtypes = [wt.HANDLE]
    k.QueryFullProcessImageNameW.restype = wt.BOOL
    k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    k.TerminateProcess.restype, k.TerminateProcess.argtypes = wt.BOOL, [wt.HANDLE, wt.UINT]
    k.GetProcessTimes.restype = wt.BOOL
    k.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
    k.GetExitCodeProcess.restype, k.GetExitCodeProcess.argtypes = wt.BOOL, [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    _W.update(ct=ctypes, wt=wt, PE=PE, k=k)
    return _W


def _watch(pid):
    """a handle on the owned game (query + synchronize) kept for the whole launch: its exit code even if the runner is ended"""
    return _win()['k'].OpenProcess(0x1000 | 0x00100000, False, int(pid)) or None


def _exit_code(h):
    """None while running (STILL_ACTIVE 259), else the process exit code (unsigned)"""
    w = _win()
    c = w['wt'].DWORD()
    if not w['k'].GetExitCodeProcess(h, w['ct'].byref(c)):
        return None
    return None if c.value == 259 else int(c.value)


def process_table():
    """{pid: (parent pid, exe name)} from one Toolhelp snapshot"""
    w = _win()
    ct, k = w['ct'], w['k']
    h = k.CreateToolhelp32Snapshot(2, 0)                             # TH32CS_SNAPPROCESS
    if not h or h == ct.c_void_p(-1).value:
        return {}
    out, e = {}, w['PE']()
    e.dwSize = ct.sizeof(w['PE'])
    try:
        ok = k.Process32FirstW(h, ct.byref(e))
        while ok:
            out[int(e.th32ProcessID)] = (int(e.th32ParentProcessID), e.szExeFile)
            ok = k.Process32NextW(h, ct.byref(e))
    finally:
        k.CloseHandle(h)
    return out


def _created(pid):
    w = _win()
    h = w['k'].OpenProcess(0x1000, False, int(pid))                  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        t = [w['wt'].FILETIME() for _ in range(4)]
        if not w['k'].GetProcessTimes(h, *[w['ct'].byref(x) for x in t]):
            return None
        return (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
    finally:
        w['k'].CloseHandle(h)


def _image(h):
    w = _win()
    buf, n = w['ct'].create_unicode_buffer(32768), w['wt'].DWORD(32768)
    return buf.value if w['k'].QueryFullProcessImageNameW(h, 0, buf, w['ct'].byref(n)) else None


def owned_tree(root_pid):
    """the processes an operation owns: root_pid and its descendants -> {pid: exe name}. A parent link is followed only when
    the child was created after the parent (a reused parent pid is not followed)."""
    tab = process_table()
    if root_pid not in tab:
        return {}
    born = {root_pid: _created(root_pid)}
    out, todo = {root_pid: tab[root_pid][1]}, [root_pid]
    while todo:
        p = todo.pop()
        for c, (pp, name) in tab.items():
            if pp == p and c not in out and c != p:
                cb = _created(c)
                if cb is None or born.get(p) is None or cb < born[p]:
                    continue
                born[c], out[c] = cb, name
                todo.append(c)
    return out


def terminate_owned(pid, root_pid, expect_image=None, code=STOP_EXIT_CODE):
    """TerminateProcess(pid, code) only if pid is in root_pid's tree (checked before AND after opening the handle, which pins
    the pid) and its image is expect_image -> (ok, detail)"""
    if pid == root_pid or pid not in owned_tree(root_pid):
        return False, 'pid %s is not a process this launch owns (not a descendant of the runner pid %s)' % (pid, root_pid)
    w = _win()
    h = w['k'].OpenProcess(0x0001 | 0x1000 | 0x00100000, False, int(pid))   # TERMINATE | QUERY_LIMITED | SYNCHRONIZE
    if not h:
        return False, 'pid %s could not be opened (already gone?)' % pid
    try:
        img = _image(h)
        if expect_image and not _same_path(img, expect_image):
            return False, 'pid %s is %s, not the launched image %s: not stopped' % (pid, img, expect_image)
        if pid not in owned_tree(root_pid):
            return False, 'pid %s left the runner\'s tree before the stop: not stopped' % pid
        ok = bool(w['k'].TerminateProcess(h, code))
        return ok, 'TerminateProcess(pid %s %s, exit code %d = 0x%X)%s' % (pid, img, code, code, '' if ok else ' FAILED')
    finally:
        w['k'].CloseHandle(h)


def guard_events(session):
    out = []
    try:
        for l in open(os.path.join(session, 'guard_events.jsonl'), encoding='utf-8'):
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    except (OSError, TypeError):
        pass
    return out


def game_launch(session):
    """the game process the runner started in this session: {pid, image} from its POPEN (cls game) event, or None"""
    for e in guard_events(session):
        if e.get('kind') == 'POPEN' and e.get('cls') == 'game' and e.get('pid'):
            return {'pid': int(e['pid']), 'image': (e.get('args') or [None])[0]}
    return None


def find_session(rp, run_folder, since):
    """the runner session folder whose guard_config names run_folder (g_run prints it only at the end)"""
    sd, best = os.path.join(rp['rt'], 'sessions'), None
    for n in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        p = os.path.join(sd, n)
        try:
            if os.path.getmtime(p) < since - 5:
                continue
            c = json.load(open(os.path.join(p, 'guard_config.json'), encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if any(isinstance(a, str) and os.path.isabs(a) and _same_path(a, run_folder) for a in c.get('args') or []):
            best = p
    return best


def dryrun_token(prof, dr):
    """the token a real run needs, from what the RUNNER validated in the dry run (its WOULD_LAUNCH event) -> (token, problems)"""
    s = (dr or {}).get('session')
    if not s or not os.path.isdir(s):
        return None, ['the dry run has no runner session folder (%s): run Dry run again' % s]
    ev = [e for e in guard_events(s) if e.get('kind') == 'WOULD_LAUNCH']
    if len(ev) != 1:
        return None, ['dry-run session %s has %d WOULD_LAUNCH events (exactly 1 needed)' % (s, len(ev))]
    e, bad = ev[0], []
    sha = (e.get('exe_sha256') or '').lower()
    if not _same_path(e.get('exe'), prof['host']['path']):
        bad.append('the dry run validated another exe (%s, profile %s)' % (e.get('exe'), prof['host']['path']))
    if sha != prof['host']['sha256'].lower():
        bad.append('the dry run validated other host bytes (%s, profile %s)' % (sha[:12], prof['host']['sha256'][:12]))
    if not _same_path(e.get('data_root'), prof['root']):
        bad.append('the dry run validated another data root (%s, profile %s)' % (e.get('data_root'), prof['root']))
    return (None if bad else '%s%s:%s' % (prof['name'], RUN_SUFFIX, sha[:12])), bad


def launches(dest):
    """every launch record of a profile, oldest first"""
    rd, out = os.path.join(dest, 'results'), []
    for n in sorted(os.listdir(rd)) if os.path.isdir(rd) else []:
        if re.match(r'^launch_.*\.json$', n):
            try:
                out.append(dict(json.load(open(os.path.join(rd, n), encoding='utf-8')), file=os.path.join(rd, n)))
            except (OSError, ValueError):
                pass
    return out


def state_hashes(dest):
    d = os.path.join(dest, 'state')
    return wb_stage.tree_hashes(d) if os.path.isdir(d) else {}


def preset_config(preset='boot', secs=None, max_wall=None, dump_flips=None, capture_every=None):
    """a launch preset with the operator's values -> (config, problems)"""
    if preset not in PRESETS:
        return {}, ['unknown preset %r (%s)' % (preset, ', '.join(PRESETS))]
    p, bad = PRESETS[preset], []
    c = {'preset': preset, 'label': p['label'], 'window': p['window']}
    try:
        s = float(p['secs'] if secs in (None, '') else secs)
    except (TypeError, ValueError):
        s, bad = 0, bad + ['duration %r is not a number' % secs]
    lo, hi = (1, 300) if preset == 'boot' else (10, 1800)
    if not lo <= s <= hi:
        bad.append('duration %s s outside %d-%d s for the %s' % (secs, lo, hi, p['label']))
    c['secs'] = ('%d' % s) if s == int(s) else ('%g' % s)
    df = p['dump_flips'] if dump_flips is None else str(dump_flips).replace(' ', '')
    if df:
        try:
            fl = [int(x) for x in df.split(',')]
            if fl != sorted(set(fl)) or fl[0] < 1 or len(fl) > 20:
                bad.append('frame dumps: 1-20 increasing flip numbers (got %s)' % df)
        except ValueError:
            bad.append('frame dumps: comma-separated flip numbers (got %r)' % df)
    c['dump_flips'] = df
    try:
        ce = float(p['capture_every'] if capture_every in (None, '') else capture_every)
    except (TypeError, ValueError):
        ce, bad = 0, bad + ['capture interval %r is not a number' % capture_every]
    if ce and (ce < 5 or not p['window']):
        bad.append('window captures: every >= 5 s, visible preset only (got %s)' % capture_every)
    c['capture_every'] = ce
    c['max_wall'] = float(max_wall) if max_wall else (LAUNCH_MAX_WALL if preset == 'boot' and s <= 20 else s + WALL_MARGIN)
    if c['max_wall'] < s and not max_wall:
        bad.append('wall limit below the duration')
    c['stop'] = ('Stop (or Cancel / closing the window / CLI Ctrl+C) ends only this launch\'s game pid (TerminateProcess 0x%X), '
                 'then the runner\'s own tree by pid if it does not end within %.0f s; at %s s the runner itself ends the game '
                 '(exit 1, "runner stop"); wall limit %.0f s ("timeout"); if the game ends by itself the runner\'s tree is '
                 'ended %.0f s later' % (STOP_EXIT_CODE, STOP_GRACE, c['secs'], c['max_wall'], EARLY_EXIT_GRACE))
    c['evidence'] = (['log.txt, result.json, scene.txt, frametime / vkframe csv (run folder); guard_events + summary (session)'] +
                     (['guest frame dumps fb_NNN.bmp at flips %s (the host\'s RECOMP_FB_DUMP; the game\'s own frame, no overlay; '
                       '~60 flips per s)' % df] if df else []) +
                     (['window captures (PrintWindow of the owned game window) every %g s and just before a Stop, into the '
                       'profile\'s results\\launch_<time>_captures\\' % ce] if ce else []) +
                     (['visible window: the owner can play (keyboard / pad) during the run'] if p['window'] else []))
    return c, bad


def launch_plan(cfg, dest, boot_secs=None, max_wall=None, preset='boot', dump_flips=None, capture_every=None):
    """everything a real launch of this profile would use, and every reason it is refused -> plan. Read only (hashes)."""
    rp = runner_paths(cfg)
    pc, pbad = preset_config(preset, boot_secs, max_wall, dump_flips, capture_every)
    P = {'kind': 'launch-plan', 'profile': dest, 'problems': list(pbad), 'boot_secs': pc.get('secs'),
         'max_wall': pc.get('max_wall'), 'preset': pc}
    bad = P['problems']
    if bad:
        return P
    bad += runner_problems(rp)
    if bad:
        return P
    st = profile_status(cfg, dest)
    if not st.get('ok'):
        bad += st['problems']
        return P
    prof, _ = load_profile(dest)
    name, root = prof['name'], prof['root']
    P.update(name=name, schema=prof.get('schema'), host=dict(prof['host']), host_described_by=prof.get('host_described_by'),
             kit_at_prepare=(prof.get('kit_identity') or {}).get('id'), root=root, env=prof.get('env'),
             load_order=prof.get('load_order'), approvals=prof.get('approvals') or prof.get('approval'),
             profile_sha256=wb_kit.sha256_file(os.path.join(dest, 'PROFILE.json')),
             members=[{'mod_id': m['mod_id'], 'version': m.get('version'), 'kind': m['kind'], 'module': m.get('module'),
                       'module_sha256': m.get('module_sha256'), 'digest': m.get('digest'), 'files': len(m.get('files') or {}),
                       'approval': ((m.get('approval') or {}).get('line') if m.get('enabled', True) else
                                    'not needed: switched off (not loaded)') if m['kind'] == 'plugin' else 'not needed (data only)',
                       **({} if m.get('enabled', True) else {'enabled': False})}
                      for m in prof['members']])
    d = st.get('dryrun') or {}
    pfs = [h for h in st['results'] if h['kind'] == 'preflight']
    P['preflight'] = {'state': st['preflight'], 'why': st['preflight_why'], 'time': pfs[-1]['time'] if pfs else None}
    P['dryrun'] = {'state': st['dryrun_state'], 'why': st['dryrun_why'], 'time': d.get('time'), 'ok': d.get('ok'),
                   'session': d.get('session'), 'run_folder': d.get('run_folder'), 'summary': d.get('summary')}
    if st['preflight'] != 'valid':
        bad.append('latest preflight %s: %s (Preflight, then Dry run, again)' % (st['preflight'], '; '.join(st['preflight_why'])))
    if st['dryrun_state'] != 'valid' or not d.get('ok'):
        bad.append('dry run %s: %s (Dry run again)' % (st['dryrun_state'], '; '.join(st['dryrun_why'])))
    _, checks = preflight_checks(cfg, dest)                       # bytes, approvals, admission, root, no game: NOW
    P['checks'] = checks
    bad += ['%s: %s' % (c['check'], c['detail']) for c in checks if not c['ok']]
    tok, tbad = dryrun_token(prof, d)
    bad += tbad
    if tok and d.get('real_run', {}).get('example_token') not in (None, tok):
        bad.append('the dry-run record\'s token %s differs from the runner-validated %s' % (d['real_run']['example_token'], tok))
    runf = os.path.join(rp['runs'], name + RUN_SUFFIX)
    if os.path.exists(runf):
        bad.append('run folder exists: %s - this profile was launched already (one real launch per profile root): prepare a '
                   'successor with a NEW root (wb_profile.py successor PROFILE --dest NEW) for another launch' % runf)
    prior = launches(dest)
    if prior:
        bad.append('this profile already has %d launch record(s) (latest %s, %s): one launch per profile; prepare a successor '
                   'with a NEW root' % (len(prior), prior[-1].get('time'), prior[-1].get('class')))
    P['root_marker'] = root_marker(root)
    host_now = next((c for c in checks if c['check'] == 'host bytes = the profile\'s'), None)
    P.update(token=tok, run_folder=runf, host_check=host_now and host_now['detail'],
             argv=[cfg['python'], '-B', rp['g_run'], 'run', LAUNCHER, '--authorize-runtime', tok or '<refused>', '--data-root',
                   root, '--', runf, '--data', root, '--scene', 'boot', '--boot-secs', pc['secs'], '--exe',
                   prof['host']['path'], '--saves', 'empty', '--timeout', '300']
             + (['--window'] if pc['window'] else []) + (['--dump-flips', pc['dump_flips']] if pc['dump_flips'] else [])
             + sum((['--env', '%s=%s' % kv] for kv in (prof.get('env') or {}).items()), []))
    P['plan_id'] = hashlib.sha256(json.dumps({k: P.get(k) for k in ('name', 'host', 'members', 'token', 'run_folder', 'root',
                                                                     'argv', 'profile_sha256', 'preset')}
                                             | {'pf': P['preflight']['time'], 'dr': P['dryrun']['time']},
                                             sort_keys=True, default=str).encode()).hexdigest()[:12]
    return P


def launch_plan_text(P):
    L = ['LAUNCH PLAN %s: %s' % (P.get('name') or P.get('profile'), 'READY - a REAL launch (owner present)' if not P['problems']
                                 else 'REFUSED (nothing is started)')]
    if P.get('host'):
        h = P['host']
        L += ['  profile      %s (%s; PROFILE.json %s)' % (P['profile'], P.get('schema'), (P.get('profile_sha256') or '')[:12]),
              '  host         %s' % h['path'],
              '               sha256 %s' % h['sha256'],
              '               build %s, platform %s, described by %s; now: %s' % (h.get('build_identity'), h.get('platform'),
                                                                                 P.get('host_described_by'), P.get('host_check'))]
        for m in P['members']:
            L.append('  mod %-6s %s %s%s' % (m['kind'], m['mod_id'], m['version'] or '',
                                             '' if m.get('enabled', True) else ' (OFF: mod-list.toml disabled)'))
            L.append('               %s; files %d digest %s' % (('module %s sha256 %s' % (m['module'], m['module_sha256']))
                                                                if m['kind'] == 'plugin' else 'data only', m['files'], m['digest']))
            L.append('               approval: %s' % m['approval'])
        a = P.get('approvals') or {}
        L.append('  approvals    source %s (sha256 %s), by %s' % (a.get('source'), (a.get('source_sha256') or '')[:12], a.get('by')))
        L.append('  load order   %s' % ', '.join('%s %s' % (x['id'], x['version']) for x in P.get('load_order') or []))
        pf, dr = P['preflight'], P['dryrun']
        L.append('  preflight    %s %s %s' % (pf['state'], pf['time'], '; '.join(pf['why'])))
        L.append('  dry run      %s %s %s; session %s' % (dr['state'], dr['time'], '; '.join(dr['why']), dr['session']))
        mk = P.get('root_marker') or {}
        L.append('  data root    %s (used_by %s, verified %s)' % (P['root'], mk.get('used_by'), mk.get('verified_sha256')))
        L.append('  run folder   %s' % P['run_folder'])
        L.append('  token        %s (RUN = the new run folder; SHA12 = the host the runner validated in the dry run)' % P.get('token'))
        pc = P.get('preset') or {}
        L.append('  preset       %s: %s, duration %s s (--scene boot --boot-secs %s%s --saves empty), wall limit %.0f s' % (
            pc.get('preset'), pc.get('label'), P['boot_secs'], P['boot_secs'], ' --window' if pc.get('window') else ' headless',
            P['max_wall']))
        for x in pc.get('evidence') or []:
            L.append('  evidence     %s' % x)
        L.append('  stop         %s' % pc.get('stop'))
        L.append('  command      %s' % subprocess.list2cmdline(P['argv']))
        L.append('  plan id      %s' % P.get('plan_id'))
        for c in P.get('checks') or []:
            L.append('  check %-40s %s  %s' % (c['check'], 'ok' if c['ok'] else 'FAILED', c['detail']))
    L += ['  REFUSED: ' + x for x in P['problems']]
    return '\n'.join(L)


def scan_game_log(path, cap=1 << 30):
    """streamed (never loaded whole): FATAL lines, last flip, registration line count"""
    d = {'path': path, 'exists': os.path.isfile(path)}
    if not d['exists']:
        return d
    fatal, first, flip, ms, reg, n, cut = 0, None, None, None, 0, 0, False
    fr = re.compile(rb'^\[GPU\] flip ([0-9]+) ([0-9]+) ms')
    with open(path, 'rb') as f:
        for raw in f:
            n += 1
            if b'FATAL' in raw:
                fatal += 1
                first = first or raw[:300].decode('utf-8', 'replace').rstrip()
            elif b'registered' in raw:
                reg += 1
            m = fr.match(raw)
            if m:
                flip, ms = int(m.group(1)), int(m.group(2))
            if f.tell() > cap:
                cut = True
                break
    d.update(size=os.path.getsize(path), lines=n, fatal_lines=fatal, first_fatal=first, last_flip=flip, last_flip_ms=ms,
             registration_lines=reg, truncated_scan=cut)
    return d


def classify_launch(e):
    """e: wb_stop, summary, result, scene, log -> (class, detail). Order: our own stop record; the runner; td_run's result."""
    s, res, st = e.get('summary'), e.get('result'), e.get('wb_stop')
    fat = (e.get('log') or {}).get('fatal_lines') or 0
    err = (res or {}).get('error') or ''
    m = re.search(r'game exited \(code (-?\d+)\)', err)
    code = int(m.group(1)) if m else None
    gx = e.get('game_exit')
    if st and not st.get('game_terminated') and gx is not None and gx != STOP_EXIT_CODE:
        st = None                                               # v0.9: the game had ended by itself before the stop
    if st:
        own = code == STOP_EXIT_CODE or gx == STOP_EXIT_CODE
        if st.get('game_terminated') or own or st.get('tree_killed') or code is None:
            c = 'timeout' if st['reason'] == 'timeout' else 'operator_stop'
            return c, '%s by %s at %.1f s; %s; td_run result: %s' % (
                'Workbench wall limit' if c == 'timeout' else 'stopped', st.get('by'), st.get('at_s') or 0,
                '; '.join(st.get('actions') or []) or 'no action needed',
                ('game ended with the Workbench stop code %d%s' % (STOP_EXIT_CODE, '' if code == STOP_EXIT_CODE else
                                                                   ' (read from the Workbench\'s handle; no td_run result.json)'))
                if own else (err or 'none / %s' % (res or {}).get('exit_code')))
        st = None                                               # the game had ended by itself before the stop: classify that
    if not s or s.get('LAUNCH') != 1:
        return 'runner_refused', 'the runner did not launch the game (runner exit %s, REFUSED %s, error %s)' % (
            e.get('runner_rc'), (s or {}).get('REFUSED'), (s or {}).get('error') or (e.get('runner_tail') or '-'))
    via = ''
    if res is None:
        if e.get('game_exit') is None:
            return 'unresolved', 'no result.json in the run folder (runner exit %s, summary %s)' % (e.get('runner_rc'), s)
        code, res = e['game_exit'], {}                              # v0.9: the Workbench's own handle on the owned game
        via = ' (exit code from the Workbench\'s handle on the game; the runner was ended early, so td_run wrote no result.json)'
    ec = res.get('exit_code')
    if res.get('ok') and code is None:
        if e.get('scene') == 'boot' and ec == 1:
            if fat:
                return 'unresolved', 'alive at the end of the boot window, but %d FATAL line(s) in log.txt' % fat
            return 'runner_stop_boot_window', ('td_run ended the %s s boot window: alive() saw the game running, then '
                                               'Popen.terminate() = TerminateProcess(game, 1) -> exit 1 (workbench CHECKPOINT '
                                               'v0.8 step 1)' % ((res.get('args') or {}).get('boot_secs')))
        return 'unresolved', 'td_run ok with exit code %s (not the boot-window pattern)' % ec
    if code is None:
        if 'timeout' in err:
            return 'timeout', 'td_run\'s own --timeout: %s' % err
        return 'unresolved', 'td_run error %s, exit code %s' % (err or '-', ec)
    u = code & 0xFFFFFFFF
    if code == 0:
        return ('normal_exit', 'the game exited by itself with code 0 (e.g. closed by the player)' + via) if not fat else (
            'crash', 'exit code 0 but %d FATAL line(s): %s%s' % (fat, (e.get('log') or {}).get('first_fatal'), via))
    if code in HOST_STOP_CODES:
        return 'probe_stop', 'host STOP: exit %d = %s (a documented deliberate stop of the start)%s' % (code, HOST_STOP_CODES[code], via)
    if code == STOP_EXIT_CODE:
        return 'unresolved', 'the game ended with the Workbench stop code %d but this launch has no stop record' % code
    return 'crash', 'the game exited by itself with %s%s%s' % (
        ('0x%08X (%s)' % (u, NTSTATUS.get(u, 'exception status'))) if u >= 0x80000000 else 'code %d (not 0, not a host stop code)' % code,
        '; %d FATAL line(s): %s' % (fat, (e.get('log') or {}).get('first_fatal')) if fat else '', via)


def launch_text(d):
    L = ['LAUNCH RESULT %s: %s' % (d.get('profile_name'), RESULT_CLASSES.get(d.get('class'), d.get('class'))),
         '  %s' % d.get('detail')]
    if d.get('stopped_by'):
        L.append('  stopped by   %s' % d['stopped_by'])
    L += ['  token        %s   plan %s   time %s' % (d.get('token'), d.get('plan_id'), d.get('time')),
          '  runner       exit %s  %s' % (d.get('runner_rc'), json.dumps(d.get('summary'))),
          '  game         pid %s  exit_code %s  seconds %s  last flip %s' % ((d.get('game') or {}).get('pid'),
                                                                              (d.get('result') or {}).get('exit_code'),
                                                                              (d.get('result') or {}).get('seconds'),
                                                                              (d.get('log') or {}).get('last_flip')),
          '  log.txt      %s (%s FATAL lines)' % ((d.get('log') or {}).get('path'), (d.get('log') or {}).get('fatal_lines')),
          '  result.json  %s' % d.get('result_json'), '  guard events %s' % d.get('guard_events'),
          '  session      %s' % d.get('session'), '  run folder   %s' % d.get('run_folder'),
          '  state files  %s' % ('unchanged' if d.get('state_unchanged') else 'CHANGED by the run: %s' % d.get('state_after'))]
    pc = d.get('preset') or {}
    if pc:
        L.insert(2, '  preset       %s (%s s%s)' % (pc.get('label'), pc.get('secs'), ', visible window' if pc.get('window') else ''))
    if d.get('early_exit'):
        L.append('  game ended   by itself at %s s, exit %s; %s' % (d['early_exit']['at_s'], d['early_exit']['game_exit'],
                                                                 '; '.join(d['early_exit'].get('actions') or []) or 'runner ended normally'))
    for c in d.get('captures') or []:
        L.append('  capture      %s %s s: %s' % (c.get('why'), c.get('at_s'), c.get('path') if c.get('ok') else
                                                  'FAILED %s' % (c.get('why_failed') or c.get('why'))) +
                 ('  (%sx%s, mean luminance %s, lit %s)' % (c['width'], c['height'], c['stats']['mean_luminance'],
                                                           c['stats']['lit_share']) if c.get('ok') else ''))
    for f in d.get('frame_dumps') or []:
        L.append('  frame dump   %s (%d bytes)' % (f['path'], f['bytes']))
    L += ['  %s' % VISUAL_NOTE, '  record       %s' % d.get('record')]
    return '\n'.join(L)


def results_text(dest):
    ls = launches(dest)
    if not ls:
        return 'LAUNCH RESULTS %s: none' % dest
    return '\n\n'.join(launch_text(d) for d in ls)


def _profile_launch_lock(dest):
    """results\\LAUNCH.lock (pid) -> (path, None) or (None, why): one launch of a profile at a time, across windows"""
    rd = os.path.join(dest, 'results')
    os.makedirs(rd, exist_ok=True)
    p = os.path.join(rd, 'LAUNCH.lock')
    if os.path.exists(p):
        try:
            pid = int(open(p).read().split()[0])
        except (OSError, ValueError, IndexError):
            pid = 0
        if pid and core.pid_alive(pid):
            return None, 'another launch of this profile is running (pid %d, %s)' % (pid, p)
        os.remove(p)                                            # a dead Workbench's lock; the run folder check still applies
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None, 'another launch of this profile just started'
    os.write(fd, ('%d %s\n' % (os.getpid(), time.strftime('%H:%M:%S'))).encode())
    os.close(fd)
    return p, None


def profile_status(cfg, dest):
    """-> {members, preflight / dry run: none | valid | stale (+why), every recorded result (stale marked), predecessor,
    successors} without running anything heavy (hashes only)"""
    prof, bad = load_profile(dest)
    if not prof:
        return {'ok': False, 'problems': bad}
    ck = wb_kit.kit_identity(cfg.get('kit'))
    now = composition_now(dest, prof)
    rec_problems = profile_record_problems(dest, prof)
    out = {'ok': True, 'profile': dest, 'schema': prof.get('schema'), 'name': prof.get('name'),
           'members': [dict({k: m.get(k) for k in ('mod_id', 'version', 'kind', 'module', 'module_sha256', 'digest')},
                            enabled=m.get('enabled', True)) for m in prof['members']],
           'disabled': prof.get('disabled') or [],
           'host': prof['host'], 'kit_at_prepare': prof.get('kit_identity'),
           'package_kit': prof.get('package_kit_identity') or (prof['members'][0].get('package_kit_identity')
                                                                if len(prof['members']) == 1 else None),
           'package_kits': sorted({(m.get('package_kit_identity') or {}).get('id') or '?' for m in prof['members']}),
           'load_order': prof.get('load_order'), 'root': prof.get('root'), 'root_mode': prof.get('root_mode'),
           'profile_record': rec_problems or 'unchanged'}
    if len(prof['members']) == 1:                               # v0.6 fields (one mod)
        out.update(mod_id=prof['members'][0]['mod_id'], module_sha256=prof['members'][0]['module_sha256'])
    res = results(dest)
    hist = []
    for kind, f, r in res:
        w = stale_why(r, 'preflight' if kind == 'preflight' else 'dry run', prof, dest, now, ck)
        if rec_problems:
            w = w + rec_problems
        hist.append({'kind': kind, 'time': r.get('time'), 'ok': r.get('ok'), 'file': f,
                     'state': 'valid' if not w else 'STALE', 'why': w})
    state = {}
    for kind, label in (('preflight', 'preflight'), ('dryrun', 'dry run')):
        last = [h for h in hist if h['kind'] == kind]
        state[kind] = (('none', ['no %s yet' % label]) if not last else
                       ('valid' if last[-1]['state'] == 'valid' else 'stale', last[-1]['why']))
    out['preflight'], out['preflight_why'] = state['preflight']
    out['dryrun_state'], out['dryrun_why'] = state['dryrun']
    try:
        out['dryrun'] = json.load(open(os.path.join(dest, 'DRYRUN.json'), encoding='utf-8'))
    except (OSError, ValueError):
        out['dryrun'] = None
    if out['dryrun_state'] == 'valid' and out['preflight'] != 'valid':
        out['dryrun_state'] = 'stale'
        out['dryrun_why'] = ['its preflight is no longer valid']
    out['results'] = hist
    pred = prof.get('predecessor')
    if pred:
        pp = []
        for kind, f, r in results(pred['path']) if os.path.isdir(pred.get('path') or '') else []:
            pp.append({'kind': kind, 'time': r.get('time'), 'ok': r.get('ok'), 'file': f, 'state': 'STALE',
                       'why': ['a result of the predecessor %s (other composition: %s)' % (pred.get('name'),
                                                                                         changes_text(prof.get('changes')))]})
        out['predecessor'] = {'path': pred['path'], 'name': pred.get('name'), 'changes': prof.get('changes'), 'results': pp}
    out['superseded_by'] = [h.get('by') for h in read_history(dest) if h.get('action') == 'superseded']
    out['launches'] = [{k: x.get(k) for k in ('time', 'class', 'detail', 'stopped_by', 'run_folder', 'session', 'file')}
                       for x in launches(dest)]
    mk = root_marker(prof.get('root')) or {}
    out['root_used_by'] = mk.get('used_by')
    return out


# ------------------------------------------------------------------------------------------------ drafts (GUI / CLI save + reload)
def new_draft():
    return {'schema': DRAFT_SCHEMA, 'packages': [], 'host': '', 'approvals': '', 'dest': '', 'predecessor': '', 'reuse_root': True,
            'disabled': []}


def load_draft(path):
    """a draft file, or a profile folder / its PROFILE.json (-> a draft for a successor of it) -> (draft, problems)"""
    if path and os.path.isdir(path) or os.path.basename(path or '').upper() == 'PROFILE.JSON':
        return draft_from_profile(path if os.path.isdir(path) else os.path.dirname(path))
    try:
        d = json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError, TypeError) as e:
        return None, ['draft unreadable: %s' % e]
    if d.get('schema') not in (DRAFT_SCHEMA, DRAFT_SCHEMA_V1):
        return None, ['not a Workbench profile draft (%s): %s' % (DRAFT_SCHEMA, path)]
    out = new_draft()
    out.update({k: d.get(k, out[k]) for k in out if k != 'schema'})
    if not isinstance(out['packages'], list) or not all(isinstance(x, str) for x in out['packages']):
        return None, ['draft packages must be a list of folders']
    if not isinstance(out['disabled'], list) or not all(isinstance(x, str) for x in out['disabled']):
        return None, ['draft disabled must be a list of package folders']
    return out, []


def save_draft(path, d):
    d = dict(new_draft(), **{k: v for k, v in d.items() if k in new_draft()})
    d['schema'] = DRAFT_SCHEMA
    d['saved'] = datetime.datetime.now().isoformat(timespec='seconds')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _write_json(path, d)
    return d


def draft_from_profile(dest):
    """a prepared (v0.6 or v0.7) profile -> a draft for its SUCCESSOR: same packages / host / approvals source, no destination"""
    prof, bad = load_profile(dest)
    if not prof:
        return None, bad
    srcs = sorted({(m.get('approval') or {}).get('source') for m in prof['members']} - {None}) or \
        ([(prof.get('approvals') or {}).get('source')] if (prof.get('approvals') or {}).get('source') else [])
    d = new_draft()
    d.update(packages=[m['package'] for m in prof['members']], host=prof['host']['path'], approvals=srcs[0] if srcs else '',
             predecessor=os.path.abspath(dest), disabled=[m['package'] for m in prof['members'] if not m.get('enabled', True)])
    return d, []


def successor_draft(pred, dest, approvals=None):
    """v0.9: an EXPLICIT successor of a prepared profile with a NEW data root (g_run make-root) - never the predecessor's root,
    used or not. Same members / host / approvals source (or the file given); the predecessor stays unchanged."""
    d, bad = draft_from_profile(pred)
    if bad:
        return None, bad
    d.update(dest=os.path.abspath(dest) if dest else '', reuse_root=False)
    if approvals:
        d['approvals'] = os.path.abspath(approvals)
    return d, []


def draft_edit(d, add=(), remove=()):
    """add packages (no duplicates by folder), remove by mod id or folder -> (draft, notes)"""
    notes = []
    for p in add:
        p = os.path.abspath(p)
        if any(_same_path(p, x) for x in d['packages']):
            notes.append('already in the list: %s' % p)
        else:
            d['packages'].append(p)
            notes.append('added %s' % p)
    for x in remove:
        keep = []
        for p in d['packages']:
            rec = wb_stage.package_record(os.path.dirname(p), os.path.basename(p)) if os.path.isdir(p) else None
            if _same_path(p, x) or (rec and rec.get('mod_id') == x):
                notes.append('removed %s' % p)
            else:
                keep.append(p)
        if len(keep) == len(d['packages']):
            notes.append('not in the list: %s' % x)
        d['packages'] = keep
    if 'disabled' in d:                                            # v0.10: a removed package is no longer switched off either
        d['disabled'] = [p for p in d['disabled'] if any(_same_path(p, x) for x in d['packages'])]
    return d, notes


# ------------------------------------------------------------------------------------------------ v0.10 draft actions
DRAFT_ACTIONS = ('add', 'enable', 'disable', 'remove')


def _draft_ids(d):
    """{package folder: (mod id, requires_mods ids, version)} from DECLARED metadata (record / mod.toml), read only"""
    out = {}
    for p in d['packages']:
        rec = wb_stage.package_record(os.path.dirname(p), os.path.basename(p)) if os.path.isdir(p) else None
        req, _ = wb_kit.requirements(os.path.join(p, 'mod.toml')) if os.path.isfile(os.path.join(p, 'mod.toml')) else (None, [])
        mid = (rec or {}).get('mod_id') or (req or {}).get('id')
        out[p] = (mid, [mod_ref_id(x) for x in (req or {}).get('requires_mods') or []], (req or {}).get('version'))
    return out


def mod_ref_id(ref):
    """a requires_mods entry ("id", "id >= 1.2") -> the id (declared text; the host's admission decides what it means)"""
    return re.split(r'[\s<>=!~^]', ref.strip(), 1)[0] if isinstance(ref, str) else repr(ref)


def _resolve(d, target):
    t = (target or '').strip()
    hits = [p for p in d['packages'] if _same_path(p, t)]
    if not hits:
        ids = _draft_ids(d)
        hits = [p for p in d['packages'] if ids[p][0] == t]
    return hits


def dependents(d, mod_id, ids=None):
    """the ENABLED draft members whose DECLARED requires_mods names mod_id -> [(mod id, package)]"""
    ids = ids or _draft_ids(d)
    return [(ids[p][0], p) for p in d['packages']
            if not is_off(p, d.get('disabled')) and ids[p][0] != mod_id and mod_id in ids[p][1]]


def draft_apply(d, action, target, even_if_required=False):
    """ONE explicit action on a draft -> (new draft or None, report). Never changes the draft given (a copy is returned), never
    touches a package folder, a staging record, an approvals file or a prepared profile, never enables / removes another mod.
    report: {ok, action, target, packages, notes, dependents, needs, refused}. Disabling / removing a mod that ENABLED members
    require is refused unless even_if_required (then the dependents are named and left exactly as they are)."""
    if action not in DRAFT_ACTIONS:
        return None, {'ok': False, 'action': action, 'target': target, 'refused': ['unknown action %r (%s)' % (action, ', '.join(DRAFT_ACTIONS))]}
    n = json.loads(json.dumps(dict(new_draft(), **{k: v for k, v in d.items() if k in new_draft()})))
    n['disabled'] = [p for p in n.get('disabled') or [] if any(_same_path(p, x) for x in n['packages'])]
    rep = {'ok': False, 'action': action, 'target': target, 'packages': [], 'notes': [], 'dependents': [], 'needs': [],
           'refused': []}
    if action == 'add':
        p = os.path.abspath(target) if target else ''
        if not p or not os.path.isdir(p):
            rep['refused'].append('not a folder: %r' % target)
            return None, rep
        if any(_same_path(p, x) for x in n['packages']):
            rep['refused'].append('already in the list: %s' % p)
            return None, rep
        n['packages'].append(p)
        rep['packages'] = [p]
        m, bad = read_package_any(p)
        rep['notes'] += ['added %s (%s)' % (p, (m or {}).get('mod_id') or '?')] + ['problem (Check will refuse): ' + b for b in bad]
        ids = _draft_ids(n)
        mid = ids[p][0]
        rep['needs'] = _needs(n, p, ids)
        return n, dict(rep, ok=True)
    hits = _resolve(n, target)
    if not hits:
        rep['refused'].append('not in the draft: %s (nothing changed)' % target)
        return None, rep
    rep['packages'] = hits
    ids = _draft_ids(n)
    if action == 'enable':
        for p in hits:
            if not is_off(p, n['disabled']):
                rep['notes'].append('already on: %s' % (ids[p][0] or p))
            else:
                n['disabled'] = [x for x in n['disabled'] if not _same_path(x, p)]
                rep['notes'].append('switched on %s (%s)' % (ids[p][0], p))
            rep['needs'] += _needs(n, p, ids)
        return n, dict(rep, ok=True)
    # disable / remove: who (enabled) depends on it?
    deps = []
    for p in hits:
        if action == 'disable' and is_off(p, n['disabled']):
            continue
        deps += [(ids[p][0], x, y) for x, y in dependents(n, ids[p][0], ids) if not any(_same_path(y, h) for h in hits)]
    rep['dependents'] = [{'mod_id': x, 'requires': mid, 'package': y} for mid, x, y in deps]
    if deps and not even_if_required:
        rep['refused'].append('%s required by %s: nothing changed. Those mods stay as they are (never switched off or removed '
                              'for you); %s them yourself first, or confirm to %s anyway (then Check refuses them until '
                              'their requirement is met)' % (', '.join(sorted({d_[0] for d_ in deps})),
                                                              ', '.join('%s (needs %s)' % (x, mid) for mid, x, _ in deps),
                                                              'disable / remove', action))
        return None, rep
    for p in hits:
        if action == 'disable':
            if is_off(p, n['disabled']):
                rep['notes'].append('already off: %s' % (ids[p][0] or p))
            else:
                n['disabled'].append(p)
                rep['notes'].append('switched off %s (%s): kept in the draft; Prepare copies it and writes mod-list.toml '
                                    'disabled = ["%s"] (the host\'s own switch)' % (ids[p][0], p, ids[p][0]))
        else:
            n['packages'] = [x for x in n['packages'] if not _same_path(x, p)]
            n['disabled'] = [x for x in n['disabled'] if not _same_path(x, p)]
            rep['notes'].append('removed %s (%s) from the draft; the folder itself is untouched' % (ids[p][0], p))
    if deps:
        rep['notes'].append('left as they are (they now lack %s; Check will refuse them): %s' % (
            ', '.join(sorted({d_[0] for d_ in deps})), ', '.join(sorted({x for _, x, _ in deps}))))
    return n, dict(rep, ok=True)


def _needs(n, p, ids):
    """what an (enabled) package declares it needs that the draft lacks or has switched off -> notes (nothing is enabled)"""
    out = []
    if is_off(p, n.get('disabled')):
        return out
    have = {ids[x][0]: x for x in n['packages']}
    for need in ids[p][1]:
        if need not in have:
            out.append('%s declares it needs %s, which is not in the draft (add it yourself; Check will refuse until then)'
                       % (ids[p][0], need))
        elif is_off(have[need], n.get('disabled')):
            out.append('%s declares it needs %s, which is switched off in the draft (enable it yourself; Check will refuse '
                       'until then)' % (ids[p][0], need))
    return out


def _is_profile_path(p):
    return bool(p) and (os.path.isdir(p) or os.path.basename(p).upper() == 'PROFILE.JSON' or
                        os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(p)), 'PROFILE.json')))


def draft_compute(src, actions, out=None, even_if_required=False):
    """the draft that applying actions [(action, target)] to src gives, computed in memory (nothing written). src = a draft
    file, a prepared profile folder (-> the draft of a SUCCESSOR of it; the profile is never written) or None / a missing file
    (a new draft). -> (draft or None, reports, problems)"""
    from_profile = bool(src) and (os.path.isdir(src) or os.path.basename(src).upper() == 'PROFILE.JSON')
    if from_profile and not out:
        return None, [], ['a prepared profile is never changed: give a new draft file for its successor']
    out = out or src
    if _is_profile_path(out):
        return None, [], ['refused: %s is (inside) a prepared profile; drafts are written elsewhere' % out]
    if src and (from_profile or os.path.isfile(src)):
        d, bad = load_draft(src)
    else:
        d, bad = new_draft(), []
    if bad:
        return None, [], bad
    reps = []
    for act, tgt in actions:
        nd, rep = draft_apply(d, act, tgt, even_if_required)
        reps.append(rep)
        if nd is None:
            return None, reps, rep['refused']
        d = nd
    if from_profile:
        reps.append({'ok': True, 'action': 'successor', 'notes': [
            'a draft for a SUCCESSOR of %s (the profile is unchanged): Check -> Prepare (new profile folder) -> Preflight -> '
            'Dry run start again' % d['predecessor']]})
    return d, reps, []


def draft_file_apply(src, actions, out=None, even_if_required=False):
    """draft_compute, then ONE atomic write of out (default src). Transactional: every action is computed in memory first;
    on any refusal or error nothing is written and an existing out file keeps its bytes. -> (draft or None, reports, problems)"""
    d, reps, bad = draft_compute(src, actions, out, even_if_required)
    if bad:
        return None, reps, bad
    try:
        save_draft(out or src, d)                                  # tmp file + os.replace: the old file stays until then
    except OSError as e:
        return None, reps, ['draft not written (the previous file is unchanged): %s' % e]
    return d, reps, []


def member_rows(cfg, packages, approvals, disabled=()):
    """for a list: one row per package {package, mod_id, version, kind, sha, requires, approval, on, problems}. Read only.
    v0.10: `on` = 'on' / 'OFF' (draft `disabled`)."""
    rows = []
    for p in _pkgs(packages):
        on = 'OFF' if is_off(p, disabled) else 'on'
        m, bad = read_package(cfg, p)
        if not m:
            rows.append({'package': p, 'mod_id': '?', 'version': '', 'kind': '?', 'sha': '', 'requires': '', 'approval': '',
                         'on': on, 'problems': bad})
            continue
        q = m['requirements'] or {}
        if m['kind'] == 'plugin':
            ok, _, detail = approval_status(approvals, m['mod_id'], m['module_sha256'])
            ap = ('approved' if ok else 'NOT approved') + (' (off: not needed now)' if on == 'OFF' else '')
        else:
            ap = 'not needed (data)'
        rows.append({'package': m['package'], 'mod_id': m['mod_id'], 'version': m['version'] or '', 'kind': m['kind'],
                     'sha': (('module %s' % m['module_sha256'][:12]) if m['kind'] == 'plugin' else 'files %s' % m['digest'][:12])
                     + (' (imported)' if m.get('recipe') == wb_stage.IMPORT_RECIPE else ''),
                     'requires': req_text(q), 'approval': ap, 'on': on, 'problems': bad,
                     'source': 'imported' if m.get('recipe') == wb_stage.IMPORT_RECIPE else 'built'})
    return rows


# ------------------------------------------------------------------------------------------------ v0.10 mod preview (read only)
LABEL_NOTE = ('DECLARED = what the mod\'s own mod.toml (and, for a staged package, the Workbench staging record) says; VERIFIED = '
              'what the Workbench computed from the bytes now (sha256 of every file, compared with the staging record); HOST '
              'READERS = the result of the kit\'s bmpack validate (the host\'s own admission code). These labels are NOT a '
              'code-safety assessment: nothing here says what a native module does or that it is safe - approving its exact '
              'bytes is your decision.')
ARCHIVES = 'deferred: no verified archive extraction exists in the Workbench or the kit (bmpack reads folders only); unpack ' \
           'an archive yourself into a new folder and preview that folder'


def read_package_any(pkg):
    """a staged package (Workbench record) or a PLAIN mod folder (a mod.toml bmpack can read) -> (info, problems). Read only.
    info: mod_id, version, kind, module, module_sha256 (VERIFIED: hashed now), files (sha256 now), digest, requirements,
    source 'staged' | 'plain', record (staged only)."""
    if not pkg or not os.path.isdir(pkg):
        low = (pkg or '').lower()
        if low.endswith(('.zip', '.7z', '.rar', '.tar', '.gz')):
            return None, ['%s: archive %s' % (pkg, ARCHIVES)]
        return None, ['mod folder not found: %s' % pkg]
    pkg = os.path.abspath(pkg)
    if wb_stage.package_record(os.path.dirname(pkg), os.path.basename(pkg)):
        m, bad = read_package(None, pkg)
        if m:
            m['source'] = 'staged'
            if m['kind'] == 'plugin':
                m['module_sha256_now'] = m['files'].get(m['module'] or '?')
        return m, bad
    mt = os.path.join(pkg, 'mod.toml')
    if not os.path.isfile(mt):
        return None, ['%s has no mod.toml: not a mod folder bmpack can read' % pkg]
    req, bad = wb_kit.requirements(mt)
    if not req:
        return None, bad
    cur = wb_stage.tree_hashes(pkg)
    plugin = bool(req.get('has_plugin'))
    mod = req.get('windows') if plugin else None
    if plugin and (not isinstance(mod, str) or mod not in cur):
        bad.append('[plugin] windows = %r: that module file is not in the folder' % (mod,))
    bad.append('not staged (no Workbench staging record): it can be previewed, but a profile takes staged packages only '
               '(their bytes are recorded at staging); Check refuses it')
    return {'package': pkg, 'record': None, 'record_path': None, 'record_sha256': None, 'recipe': None, 'source': 'plain',
            'mod_id': req.get('id'), 'version': req.get('version'), 'name': req.get('name'),
            'kind': 'plugin' if plugin else 'data', 'module': mod, 'module_sha256': cur.get(mod) if mod else None,
            'module_sha256_now': cur.get(mod) if mod else None, 'requirements': req, 'kit_identity': None,
            'files': cur, 'digest': files_digest(cur)}, bad


def declared_content(pkg):
    """mod.toml -> {description, kinds [...], changes [(table, text)]} (DECLARED metadata, read only)"""
    try:
        t = tomllib.loads(open(os.path.join(pkg, 'mod.toml'), encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return {'description': None, 'kinds': [], 'changes': [], 'error': str(e)}
    kinds, changes = [], []
    if isinstance(t.get('plugin'), dict):
        pl = t['plugin']
        kinds.append('native plugin (Windows module %s, plugin api %s)' % (pl.get('windows'), pl.get('api')))
        changes.append(('plugin', 'native code: what it changes is NOT declared in a form the host checks; only its '
                                  'description says (see above)'))
    bm = t.get('bmashup') if isinstance(t.get('bmashup'), dict) else {}
    for k in sorted(bm):
        v = bm[k]
        if isinstance(v, dict):
            kinds.append('data: [bmashup.%s]' % k)
            for kk in sorted(v):
                if kk == 'version':
                    continue
                vv = v[kk]
                if isinstance(vv, list):
                    for x in vv[:20]:
                        changes.append(('bmashup.%s' % k, '%s: %s' % (kk, json.dumps(x, ensure_ascii=False, default=str)[:160])))
                    if len(vv) > 20:
                        changes.append(('bmashup.%s' % k, '%s: ... %d more' % (kk, len(vv) - 20)))
                else:
                    changes.append(('bmashup.%s' % k, '%s = %s' % (kk, json.dumps(vv, ensure_ascii=False, default=str)[:160])))
    for k in sorted(t):
        if k not in ('id', 'name', 'version', 'description', 'bmashup', 'plugin', 'author', 'authors', 'license'):
            kinds.append('other [%s] (%s)' % (k, type(t[k]).__name__))
    return {'description': t.get('description'), 'kinds': kinds or ['none declared (mod.toml only)'], 'changes': changes}


def preview(cfg, folder, draft=None):
    """v0.10: one mod folder against a profile draft. READ ONLY: no draft, configuration, profile, package or approvals file is
    written (the host admission uses a temporary roots file under the Workbench's own state\\admission, as Check does).
    -> {mod, declared, verified, host, admission (with / without the mod), dependencies, dependents, approval, can_join, ...}"""
    d = dict(new_draft(), **(draft or {}))
    P = {'kind': 'mod-preview', 'folder': os.path.abspath(folder) if folder else folder, 'problems': [], 'label_note': LABEL_NOTE,
         'archives': ARCHIVES, 'draft': {k: d.get(k) for k in ('packages', 'disabled', 'host', 'approvals')}}
    m, bad = read_package_any(folder)
    P['problems'] += bad
    if not m:
        P['can_join'] = False
        return P
    q = m['requirements'] or {}
    rec = m.get('record') or {}
    P['mod'] = {'mod_id': m['mod_id'], 'version': m['version'], 'name': m.get('name'), 'kind': m['kind'], 'source': m['source']}
    P['declared'] = dict(declared_content(m['package']), requirements={
        'platform': q.get('platform'), 'services_tables': ['%s>=%d' % x for x in q.get('requires') or []],
        'plugin_api': q.get('api') if q.get('has_plugin') else None, 'requires_mods': q.get('requires_mods') or []},
        record=None if m['source'] != 'staged' else {
            'path': m.get('record_path'), 'sha256': m.get('record_sha256'), 'recipe': rec.get('recipe'), 'kind': rec.get('kind'),
            'module': (rec.get('module') or {}).get('file'), 'module_sha256': (rec.get('module') or {}).get('sha256'),
            'built_with': (rec.get('kit_identity') or {}).get('id'), 'provenance': wb_stage.provenance_text(rec),
            'native_code_approved': (rec.get('native_code') or {}).get('approved') if m['kind'] == 'plugin' else None})
    exts = {}
    for rel in m['files']:
        e = os.path.splitext(rel)[1].lower() or '(none)'
        exts[e] = exts.get(e, 0) + 1
    rec_files = rec.get('package_files') if m['source'] == 'staged' else None
    P['verified'] = {'files': len(m['files']), 'by_extension': dict(sorted(exts.items())), 'digest': m['digest'],
                     'file_sha256': dict(sorted(m['files'].items())),
                     'matches_record': None if rec_files is None else rec_files == m['files'],
                     'module': m.get('module'), 'module_sha256': m.get('module_sha256_now'),
                     'module_matches_record': None if m['kind'] != 'plugin' or m['source'] != 'staged' else
                     m.get('module_sha256_now') == (rec.get('module') or {}).get('sha256')}
    # approval (plugins): the player's file of the draft, exact bytes hashed NOW
    if m['kind'] == 'plugin':
        sha = m.get('module_sha256_now')
        ok, line, detail = approval_status(d.get('approvals'), m['mod_id'], sha) if sha else (False, None, 'no module file')
        P['approval'] = {'needed': True, 'ok': ok, 'line': line, 'detail': detail, 'file': d.get('approvals') or None}
    else:
        P['approval'] = {'needed': False, 'ok': True, 'line': None, 'detail': 'data only, no native code'}
    # draft context (DECLARED ids / requires_mods of the draft's packages)
    ids = _draft_ids(d)
    in_draft = [p for p in d['packages'] if _same_path(p, m['package'])]
    P['in_draft'] = {'listed': bool(in_draft), 'enabled': bool(in_draft) and not is_off(in_draft[0], d.get('disabled'))}
    have = {ids[p][0]: p for p in d['packages'] if not _same_path(p, m['package'])}
    P['dependencies'] = [{'requires': r, 'id': mod_ref_id(r),
                          'in_draft': ('switched off' if is_off(have[mod_ref_id(r)], d.get('disabled')) else 'on')
                          if mod_ref_id(r) in have else 'not in the draft'} for r in q.get('requires_mods') or []]
    P['dependents'] = [{'mod_id': x, 'package': y} for x, y in
                       dependents(dict(d, packages=[p for p in d['packages'] if not _same_path(p, m['package'])]), m['mod_id'])]
    P['same_id_in_draft'] = [p for i, p in have.items() if i == m['mod_id']]
    # host: compatibility + the host's own admission with / without this mod
    host = wb_kit.host_identity(d.get('host')) if d.get('host') else None
    P['host'] = {'path': d.get('host') or None, 'sha256': (host or {}).get('sha256'), 'build': (host or {}).get('build_identity'),
                 'described_by': None, 'compat': [], 'why': None if host else ('no host in the draft' if not d.get('host')
                                                                                else 'host exe not found: %s' % d.get('host'))}
    others, offs = [], []                                    # v0.11: switched-off members take part as the host's loader sees them
    for p in d['packages']:
        if _same_path(p, m['package']):
            continue
        om, _ = read_package_any(p)
        if om:
            om['enabled'] = not is_off(p, d.get('disabled'))
            (others if om['enabled'] else offs).append(om)
    m = dict(m, enabled=True)
    k = None
    if host:
        k, why = wb_kit.describe_host(host, known_kits(cfg, [m.get('kit_identity')] + [o.get('kit_identity') for o in others]))
        P['host'].update(described_by=k and k['id'], why=why)
        if k:
            P['host']['compat'] = member_compat(k, host, [m])
    P['admission'] = {'with': None, 'without': None, 'new_refusals': [], 'note': None}
    if k:
        a1 = admission_switched(cfg, k, others + [m] + offs)
        a0 = admission_switched(cfg, k, others + offs) if others else None
        key = lambda f: (f.get('service'), f.get('mod'), f.get('why'))   # noqa: E731
        old = {key(f) for f in (a0 or {}).get('refusals') or []}
        P['admission'] = {'with': a1, 'without': a0, 'new_refusals': [f for f in a1.get('refusals') or [] if key(f) not in old],
                          'note': 'the draft\'s enabled members + this mod, in mod-id order (switched-off members are not '
                                  'admitted but count for the loader, as the host does)'}
    else:
        P['admission']['note'] = 'not run: %s' % (P['host']['why'] or 'no kit describes the draft\'s host')
    P['can_join'] = m['source'] == 'staged' and not bad
    return P


def preview_text(P):
    L = ['MOD PREVIEW %s (read only: nothing was written)' % P.get('folder')]
    if not P.get('mod'):
        L += ['  problem: ' + x for x in P['problems']]
        L.append('  archives: ' + P['archives'])
        return '\n'.join(L)
    mo, de, ve = P['mod'], P['declared'], P['verified']
    L.append('  %s %s  %s  (%s; %s)' % (mo['mod_id'], mo['version'], mo.get('name') or '', mo['kind'],
                                        'staged package' if mo['source'] == 'staged' else 'PLAIN folder, not staged'))
    L.append('DECLARED (mod.toml%s):' % (' + staging record' if mo['source'] == 'staged' else ''))
    L.append('  description   %s' % (de.get('description') or '-'))
    L.append('  content kinds %s' % '; '.join(de['kinds']))
    for t, x in de['changes'] or [('-', 'no gameplay change declared')]:
        L.append('  change        [%s] %s' % (t, x))
    rq = de['requirements']
    L.append('  requires      platform %s; services / tables %s; plugin api %s; mods %s' % (
        rq['platform'] or '-', ', '.join(rq['services_tables']) or 'none', rq['plugin_api'] if rq['plugin_api'] is not None else '-',
        ', '.join(rq['requires_mods']) or 'none'))
    r = de.get('record')
    if r:
        L.append('  record        %s (sha256 %s): recipe %s, built with %s%s' % (
            r['path'], (r['sha256'] or '')[:12], r['recipe'], r['built_with'],
            '; module %s sha256 %s, native_code.approved %s' % (r['module'], r['module_sha256'], r['native_code_approved'])
            if mo['kind'] == 'plugin' else ''))
        L.append('  provenance    %s' % r.get('provenance'))
    L.append('VERIFIED (bytes hashed now):')
    L.append('  files         %d (%s), digest %s%s' % (ve['files'], ', '.join('%s %d' % kv for kv in ve['by_extension'].items()),
                                                      ve['digest'][:12], '' if ve['matches_record'] is None else
                                                      '; = the staging record' if ve['matches_record'] else
                                                      '; DIFFERENT from the staging record'))
    for rel, sha in list(ve['file_sha256'].items())[:12]:
        L.append('                %s  %s' % (sha[:12], rel))
    if len(ve['file_sha256']) > 12:
        L.append('                ... %d more files' % (len(ve['file_sha256']) - 12))
    if mo['kind'] == 'plugin':
        L.append('  native module %s sha256 %s%s' % (ve['module'], ve['module_sha256'], '' if ve['module_matches_record'] is None
                                                     else ' (= the record)' if ve['module_matches_record'] else ' (NOT the record\'s bytes)'))
    a = P['approval']
    L.append('APPROVAL        %s' % ('not needed (data only)' if not a['needed'] else
                                     '%s: %s' % ('APPROVED by the player' if a['ok'] else 'NOT APPROVED', a['detail'])))
    if a['needed'] and a.get('line'):
        L.append('                line for these bytes: "%s" (the Workbench never writes it)' % a['line'])
    h = P['host']
    L.append('HOST            %s%s' % (h['path'] or '-', '  sha256 %s build %s, %s' % ((h['sha256'] or '')[:12], h['build'], h['why'])
                                       if h['sha256'] else '  (%s)' % h['why']))
    for x in h['compat']:
        L.append('                %s' % x)
    if h['sha256'] and h.get('described_by') and not h['compat']:
        L.append('                requirements met by the host\'s offered services / tables')
    ind = P['in_draft']
    L.append('DRAFT           %s; dependencies %s; required by %s%s' % (
        ('listed, %s' % ('on' if ind['enabled'] else 'switched off')) if ind['listed'] else 'not listed (Add to include it)',
        ', '.join('%s (%s)' % (x['requires'], x['in_draft']) for x in P['dependencies']) or 'none declared',
        ', '.join(x['mod_id'] for x in P['dependents']) or 'no enabled member',
        '; SAME mod id as %s' % ', '.join(P['same_id_in_draft']) if P['same_id_in_draft'] else ''))
    ad = P['admission']
    if ad.get('with'):
        w = ad['with']
        L.append('HOST READERS    %s with this mod (%s readers, bmpack %s; %s)' % (
            'ACCEPTED' if w.get('ok') else 'REFUSED' if not w.get('error') else 'NOT CHECKED: ' + w['error'],
            w.get('kit'), w.get('bmpack'), ad['note']))
        L.append('  load order    %s%s' % (', '.join('%s %s%s' % (x['id'], x['version'], '' if x['usable'] else ' (refused)')
                                                    for x in w.get('order') or []) or '-',
                                         ' (dependency order: %d moved)' % w['dependency_moved'] if w.get('dependency_moved') else ''))
        wo = ad.get('without')
        if wo is not None:
            L.append('  without it    %s' % ('ACCEPTED' if wo.get('ok') else 'REFUSED (%d refusal(s) already)' % len(wo.get('refusals') or [])))
        for f in w.get('refusals') or []:
            L.append('  %s [%s] %s: %s' % ('NEW  ' if f in ad['new_refusals'] else 'had  ', f['service'], f['mod'] or '-', f['why']))
    else:
        L.append('HOST READERS    %s' % ad.get('note'))
    L.append('JOIN            %s' % ('can be added: Check / Prepare decide for the whole draft' if P['can_join'] else
                                     'cannot join a profile as it is (see problems)'))
    L += ['  problem: ' + x for x in P['problems']]
    L.append('NOTE            ' + P['label_note'])
    return '\n'.join(L)


def req_text(q):
    return 'platform %s; services %s; plugin api %s; mods %s' % (
        q.get('platform'), ', '.join('%s>=%d' % x for x in q.get('requires') or []) or 'none',
        q.get('api') if q.get('has_plugin') or q.get('api') is not None else '-', ', '.join(q.get('requires_mods') or []) or 'none')


# ------------------------------------------------------------------------------------------------ the job
class ProfileOp:
    kind = 'profile'

    def __init__(self, action, dest, package=None, host=None, approvals=None, predecessor=None, reuse_root=True,
                 authorize=None, plan_id=None, boot_secs=None, max_wall=None, stop_grace=STOP_GRACE, preset='boot',
                 dump_flips=None, capture_every=None, early_exit_grace=EARLY_EXIT_GRACE, disabled=()):
        assert action in ('prepare', 'preflight', 'dryrun', 'launch')
        self.disabled = _pkgs(disabled)                                               # v0.10: switched-off packages
        self.action, self.dest = action, os.path.abspath(dest) if dest and os.path.isabs(dest) else dest
        self.packages, self.host, self.approvals = _pkgs(package), host, approvals
        self.package = self.packages[0] if len(self.packages) == 1 else None          # v0.6 attribute
        self.predecessor, self.reuse_root = predecessor or None, reuse_root
        self.authorize, self.plan_id = authorize, plan_id                             # v0.8 launch
        self.boot_secs, self.max_wall, self.stop_grace = boot_secs, max_wall, float(stop_grace)
        self.preset, self.dump_flips, self.capture_every = preset, dump_flips, capture_every          # v0.9
        self.early_exit_grace = float(early_exit_grace)
        self.title = '%s test profile %s' % ({'dryrun': 'dry run', 'launch': 'REAL LAUNCH of'}.get(action, action),
                                             os.path.basename(dest or '?'))


class _Refused(Exception):
    pass


class ProfileJob:
    """the same interface as wb_stage.StageJob (start / wait / cancel / done / log_path / tail / result_dict)"""

    def __init__(self, cfg, op, on_line=None):
        self.cfg, self.op, self.on_line = cfg, op, on_line
        os.makedirs(cfg['logs'], exist_ok=True)
        self.ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        self.log_path = os.path.join(cfg['logs'], '%s_profile_%s.log' % (self.ts, op.action))
        self.proc, self.rc, self.cancelled, self.result_dict = None, None, False, None
        self.stop_req = None                                       # v0.8 launch: {'by', 'time'} once Stop is pressed
        self.capture_req = 0                                       # v0.9: "Capture now" presses not yet served
        self.captures = []
        self.started = self.ended = None
        self.done = threading.Event()
        self.tail = []
        self._lk = threading.Lock()

    def log(self, line):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        self.tail = (self.tail + [line])[-400:]
        if self.on_line:
            try:
                self.on_line(line)
            except Exception:                                      # noqa: BLE001
                pass

    def start(self):
        self.started = time.time()
        threading.Thread(target=self._main, daemon=True).start()
        return self

    def wait(self, timeout=None):
        return self.done.wait(timeout)

    def cancel(self, by=None):
        if self.op.action == 'launch':                             # the launch loop stops ONLY the tree it owns, and records who
            with self._lk:
                self.cancelled = True
                if not self.stop_req:
                    self.stop_req = {'by': by or 'operator %s (Workbench Cancel, pid %d)' % (getpass.getuser(), os.getpid()),
                                     'time': datetime.datetime.now().isoformat(timespec='seconds')}
            return
        with self._lk:
            self.cancelled = True
            p = self.proc
        if p and p.poll() is None:
            subprocess.run([core.TASKKILL, '/PID', str(p.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def output(self):
        with open(self.log_path, encoding='utf-8', errors='replace') as f:
            return f.read()

    def _run(self, argv, cwd):
        self.log('## %s\n# cwd: %s\n# argv: %s' % (argv[3] if len(argv) > 3 else '', cwd, json.dumps(argv)))
        with self._lk:
            if self.cancelled:
                return None, ''
            self.proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1'),
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        buf = []
        for raw in iter(self.proc.stdout.readline, b''):
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            buf.append(line)
            self.log(line)
        rc = self.proc.wait()
        self.log('# exit %s' % rc)
        return rc, '\n'.join(buf)

    def _main(self):
        r = {'kind': 'profile', 'action': self.op.action, 'profile': self.op.dest, 'log': self.log_path, 'ok': False}
        try:
            getattr(self, '_' + self.op.action)(r)
        except Exception as e:                                     # noqa: BLE001
            import traceback
            self.log('INTERNAL ERROR %r\n%s' % (e, traceback.format_exc()))
            r.update(verdict='INTERNAL ERROR (%s)' % e, excerpt=self.tail[-12:])
        if self.cancelled and not r.get('ok') and self.op.action != 'launch':     # a launch reports its own class
            r['verdict'] = 'CANCELLED'
        self.rc = 0 if r.get('ok') else 1
        self.result_dict = r
        self.ended = time.time()
        self.log('# result %s after %.1f s' % (r.get('verdict'), self.ended - self.started))
        self.done.set()

    def _refuse(self, r, bad, verdict='NOT STARTED'):
        for b in bad:
            self.log('REFUSED: ' + b)
        r.update(verdict=verdict, problems=bad)

    # -------------------------------------------------------------- prepare
    def _prepare(self, r):
        cfg, op = self.cfg, self.op
        info = inspect(cfg, op.packages, op.host, op.dest, op.approvals, op.predecessor, op.reuse_root, op.disabled)
        r['check'] = {k: v for k, v in info.items() if k != 'host_kit'}
        for l in check_text(info).splitlines():
            self.log('# ' + l)
        if info['problems']:
            return self._refuse(r, info['problems'])
        rp = runner_paths(cfg)
        dest, name = os.path.normpath(op.dest), os.path.basename(os.path.normpath(op.dest))
        members, host, k = info['members'], info['host'], info['host_kit']
        tmp = os.path.join(rp['modsets'], '.%s.wbp_new_%s' % (name, self.ts))
        mods = os.path.join(tmp, MODS)
        root = info.get('adopt_root') or os.path.join(rp['roots'], name)
        made_root = False
        os.makedirs(mods)
        os.makedirs(os.path.join(tmp, 'state'))
        try:
            for m in members:
                d = os.path.join(mods, m['mod_id'])
                for rel, sha in m['files'].items():
                    dst = os.path.join(d, *rel.split('/'))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(os.path.join(m['package'], *rel.split('/')), dst)
                    if wb_kit.sha256_file(dst) != sha:
                        raise RuntimeError('copy of %s / %s does not match the package' % (m['mod_id'], rel))
                m['folder'] = '%s/%s' % (MODS, m['mod_id'])
            off_ids = sorted(m['mod_id'] for m in members if not m.get('enabled', True))
            with open(os.path.join(tmp, 'state', 'mod-list.toml'), 'w', encoding='utf-8', newline='\n') as f:
                if off_ids:                                      # v0.10: the host's own switch (modfs mod list)
                    f.write('# Workbench test profile %s: these mods in %s\\ are switched off (the host reads this list at the '
                            'start); the others are on (the host orders them: id, then requires_mods)\ndisabled = [%s]\n'
                            % (name, MODS, ', '.join('"%s"' % x for x in off_ids)))
                else:
                    f.write('# Workbench test profile %s: every mod in %s\\ on (the host orders them: id, then requires_mods)\n'
                            'disabled = []\n' % (name, MODS))
            lines = [m['approval']['line'] for m in members if m['kind'] == 'plugin' and m.get('enabled', True)]
            src = op.approvals if lines else None
            with open(os.path.join(tmp, 'state', 'plugin-approvals.toml'), 'w', encoding='utf-8', newline='\n') as f:
                if lines:
                    f.write('# Workbench test profile %s: the player\'s own approvals, copied from %s (sha256 %s).\n'
                            '# The Workbench did not approve anything; it only copies the lines for the plugin modules in this '
                            'profile.\napproved = [%s]\n' % (name, src, wb_kit.sha256_file(src)[:12], ', '.join('"%s"' % x for x in lines)))
                else:
                    f.write('# Workbench test profile %s: data-only mods, no native code: nothing to approve.\napproved = []\n' % name)
            self.log('# profile files written to %s' % tmp)
            a = admission(cfg, k, [mods], self.log) if not off_ids else \
                admission_switched(cfg, k, members, lambda m: os.path.join(mods, m['mod_id']), self.log)   # v0.11 parity
            if not a['ok']:
                raise _Refused('; '.join(admission_problems(a)))
            if self.cancelled:
                raise _Refused('cancelled')
            if info.get('adopt_root'):
                mk = root_marker(root)
                if not mk or mk.get('used_by') is not None or not mk.get('verified_sha256'):
                    raise _Refused('the predecessor\'s root %s is no longer unused / verified: prepare with a new root' % root)
                self.log('# data root: adopting the predecessor\'s unused verified root %s (no copy)' % root)
                marker = mk
            else:
                self.log('# preparing the data root with the runner: g_run.py make-root %s (copies and verifies runtime_data\\base)' % name)
                rc, out = self._run([cfg['python'], '-B', rp['g_run'], 'make-root', name], rp['pc'])
                mk = os.path.join(root, '.g_disposable.json')
                made_root = os.path.isfile(mk)
                if self.cancelled or rc != 0 or not made_root:
                    raise RuntimeError('g_run make-root %s failed (exit %s): %s' % (name, rc, (out.strip().splitlines() or [''])[-1]))
                marker = json.load(open(mk, encoding='utf-8'))
            env = {'BMASHUP_MODS': os.path.join(dest, MODS),
                   'BMASHUP_MOD_LIST': os.path.join(dest, 'state', 'mod-list.toml'),
                   'BMASHUP_PLUGIN_APPROVALS': os.path.join(dest, 'state', 'plugin-approvals.toml'),
                   'TAKEDAWN_MODS': os.path.join(dest, MODS),
                   'TAKEDAWN_MOD_LIST': os.path.join(dest, 'state', 'mod-list.toml'),
                   'TAKEDAWN_PLUGIN_APPROVALS': os.path.join(dest, 'state', 'plugin-approvals.toml')}
            pred = None
            if op.predecessor:
                pp, _ = load_profile(op.predecessor)
                pred = {'path': os.path.abspath(op.predecessor), 'name': pp.get('name'), 'schema': pp.get('schema'),
                        'profile_sha256': wb_kit.sha256_file(os.path.join(op.predecessor, 'PROFILE.json')),
                        'members': {m['mod_id']: m.get('digest') for m in pp['members']}, 'host_sha256': pp['host']['sha256']}
            mem = []
            for m in members:
                mem.append({'mod_id': m['mod_id'], 'version': m['version'], 'name': m['name'], 'kind': m['kind'],
                            'package': m['package'], 'package_record': m['record_path'], 'record_sha256': m['record_sha256'],
                            'recipe': m['recipe'], 'folder': m['folder'], 'files': m['files'], 'digest': m['digest'],
                            'module': m['module'], 'module_sha256': m['module_sha256'], 'requirements': m['requirements'],
                            'package_kit_identity': m['kit_identity'],
                            'approval': {'needed': m['kind'] == 'plugin' and m.get('enabled', True), 'line': m['approval']['line'],
                                         'source': src if m['kind'] == 'plugin' and m.get('enabled', True) else None}})
                if not m.get('enabled', True):                   # v0.10: kept, switched off (no key = on: v0.7 profiles)
                    mem[-1]['enabled'] = False
            prof = {'schema': SCHEMA, 'name': name, 'created': datetime.datetime.now().isoformat(timespec='seconds'),
                    'host': {kk: host[kk] for kk in ('path', 'sha256', 'size', 'build_identity', 'platform')},
                    'host_described_by': k['id'], 'members': mem,
                    'load_order': [{kk: x[kk] for kk in ('id', 'version', 'usable')} for x in a['order']],
                    'admission': {kk: a.get(kk) for kk in ('ok', 'kit', 'readers', 'bmpack', 'dependency_moved', 'refusals')},
                    'kit_identity': info['kit_identity'],
                    'approvals': {'source': src, 'source_sha256': wb_kit.sha256_file(src) if src else None, 'lines': lines,
                                  'by': 'the player (copied, not created, by the Workbench)' if lines else 'nothing to approve (data only)'},
                    'native_code': {'approved_by_workbench': False},
                    'predecessor': pred, 'changes': info.get('changes'),
                    'progress': ('a new profile: no preflight / dry run yet' if not pred else
                                 'successor of %s: preflight and dry run start again here; the predecessor and its results are '
                                 'kept unchanged (shown here as stale history)' % pred['name']),
                    'root': root, 'root_mode': ('adopted (unused, verified) from %s' % pred['name']) if info.get('adopt_root') else 'g_run make-root',
                    'root_marker': {kk: marker.get(kk) for kk in ('files', 'bytes', 'verified_sha256', 'used_by', 'session')},
                    'runner': {'g_run': rp['g_run'], 'launcher': LAUNCHER}, 'env': env, 'prepare_log': self.log_path}
            if off_ids:
                prof['disabled'] = off_ids                       # v0.10 = state\mod-list.toml `disabled`
            if len(mem) == 1 and mem[0]['kind'] == 'plugin':      # the v0.6 fields of a one-plugin profile
                m = mem[0]
                prof.update(package=m['package'], package_record=m['package_record'], mod_id=m['mod_id'], module=m['module'],
                            module_sha256=m['module_sha256'], requirements=m['requirements'], package_files=m['files'],
                            package_kit_identity=m['package_kit_identity'],
                            approval={'source': src, 'source_sha256': prof['approvals']['source_sha256'], 'line': m['approval']['line'],
                                      'by': 'the player (copied, not created, by the Workbench)'})
            _write_json(os.path.join(tmp, 'PROFILE.json'), prof)
            psha = wb_kit.sha256_file(os.path.join(tmp, 'PROFILE.json'))
            if os.path.exists(dest):
                raise FileExistsError(dest)                          # appeared meanwhile: never overwrite
            os.rename(tmp, dest)
        except Exception as e:                                     # noqa: BLE001
            shutil.rmtree(tmp, ignore_errors=True)                 # our own unfinished temp folder only
            v = 'PREPARE REFUSED' if isinstance(e, _Refused) else 'PREPARE FAILED'
            return self._refuse(r, ['%s' % e], '%s (no profile was made%s)' % (
                v, '; the runner\'s root %s is left as the runner made it' % root if made_root else ''))
        _history(dest, {'time': prof['created'], 'action': 'prepare', 'ok': True, 'log': self.log_path, 'profile_sha256': psha,
                        'predecessor': pred and pred['path']})
        if pred:
            _history(pred['path'], {'time': prof['created'], 'action': 'superseded', 'by': dest,
                                    'changes': changes_text(info.get('changes')), 'note': 'this profile is unchanged'})
        r.update(ok=True, verdict='PREPARED', profile_record=os.path.join(dest, 'PROFILE.json'), root=root, profile_data=prof)

    # -------------------------------------------------------------- preflight
    def _preflight(self, r):
        prof, checks = preflight_checks(self.cfg, self.op.dest)
        r['checks'] = checks
        for c in checks:
            self.log('# check %-44s %s  %s' % (c['check'], 'ok' if c['ok'] else 'FAILED', c['detail']))
        ok = prof is not None and all(c['ok'] for c in checks)
        now = datetime.datetime.now().isoformat(timespec='seconds')
        if prof:
            _history(self.op.dest, {'time': now, 'action': 'preflight', 'ok': ok, 'log': self.log_path,
                                    'failed': [c['check'] for c in checks if not c['ok']]})
        if not ok:
            r.update(verdict='PREFLIGHT FAILED (the previous preflight records are kept)',
                     problems=['%s: %s' % (c['check'], c['detail']) for c in checks if not c['ok']])
            return
        ck = wb_kit.kit_identity(self.cfg.get('kit'))
        comp = composition_now(self.op.dest, prof)
        pf = {'time': now, 'ok': True, 'checks': checks, 'kit_identity': wb_kit.stamp(ck), 'composition': comp,
              'host_sha256': prof['host']['sha256'], 'log': self.log_path}
        if len(prof['members']) == 1:
            pf['module_sha256'] = prof['members'][0]['module_sha256']
        self._record(pf, 'preflight', 'PREFLIGHT.json')
        r.update(ok=True, verdict='PREFLIGHT OK', preflight=pf)

    def _record(self, data, kind, latest):
        rd = os.path.join(self.op.dest, 'results')
        os.makedirs(rd, exist_ok=True)
        _write_json(os.path.join(rd, '%s_%s.json' % (kind, self.ts)), data)
        _write_json(os.path.join(self.op.dest, latest), data)

    # -------------------------------------------------------------- dry run
    def _dryrun(self, r):
        cfg, dest = self.cfg, self.op.dest
        st = profile_status(cfg, dest)
        if not st.get('ok'):
            return self._refuse(r, st['problems'])
        if st['preflight'] != 'valid':
            return self._refuse(r, ['preflight %s: %s' % (st['preflight'], '; '.join(st['preflight_why']))])
        prof, checks = preflight_checks(cfg, dest)              # re-checked now, not trusted from the file
        bad = ['%s: %s' % (c['check'], c['detail']) for c in checks if not c['ok']]
        if bad:
            return self._refuse(r, bad)
        rp = runner_paths(cfg)
        run = next_dry(rp, prof['name'])
        runf = os.path.join(rp['runs'], run)
        argv = [cfg['python'], '-B', rp['g_run'], 'run', LAUNCHER, '--dry-run', '--data-root', prof['root'], '--',
                runf, '--data', prof['root'], '--scene', 'boot', '--boot-secs', BOOT_SECS, '--exe', prof['host']['path'],
                '--saves', 'empty', '--timeout', '300'] + sum((['--env', '%s=%s' % kv] for kv in prof['env'].items()), [])
        rc, out = self._run(argv, rp['pc'])
        m = re.search(r'\[g_run\] session (.+)', out)
        s = re.search(r'\[g_run\] (\{.*\})', out)
        summ = json.loads(s.group(1)) if s else {}
        mk = root_marker(prof['root'])
        used = mk.get('used_by') if mk else 'unreadable'
        ok = (rc == 0 and summ.get('REFUSED') == 0 and summ.get('WOULD_LAUNCH') == 1 and summ.get('LAUNCH') == 0
              and used is None and not self.cancelled)
        token = '%s:%s' % (prof['name'] + '_run1', prof['host']['sha256'][:12])
        d = {'time': datetime.datetime.now().isoformat(timespec='seconds'), 'ok': ok, 'rc': rc, 'summary': summ,
             'session': m.group(1).strip() if m else None, 'run_folder': runf, 'root_used_by_after': used,
             'kit_identity': wb_kit.stamp(wb_kit.kit_identity(cfg.get('kit'))), 'composition': composition_now(dest, prof),
             'members': [(x['mod_id'], x['version'], x['kind']) for x in prof['members']],
             'host_sha256': prof['host']['sha256'], 'log': self.log_path, 'env': prof['env'],
             'real_run': {'note': 'NOT done by the Workbench: a real launch needs the owner present and authorising it',
                          'token_format': 'RUN:SHA12', 'example_token': token, 'launcher': LAUNCHER}}
        if len(prof['members']) == 1:
            d['module_sha256'] = prof['members'][0]['module_sha256']
        _history(dest, {'time': d['time'], 'action': 'dryrun', 'ok': ok, 'log': self.log_path, 'summary': summ})
        if not ok:
            r.update(verdict='DRY RUN FAILED (the previous dry-run records are kept)', dryrun=d,
                     problems=['g_run exit %s, summary %s, root used_by %s' % (rc, summ, used)], excerpt=out.splitlines()[-12:])
            return
        self._record(d, 'dryrun', 'DRYRUN.json')
        r.update(ok=True, verdict='DRY RUN OK (game not executed)', dryrun=d)

    # -------------------------------------------------------------- launch (v0.8: REAL run, owner present)
    def _launch(self, r):
        op, dest = self.op, self.op.dest
        lockp, why = _profile_launch_lock(dest) if os.path.isfile(os.path.join(dest or '', 'PROFILE.json')) else (None, None)
        if why:
            return self._refuse(r, [why], 'LAUNCH REFUSED (nothing started)')
        try:
            plan = launch_plan(self.cfg, dest, op.boot_secs, op.max_wall, op.preset, op.dump_flips,
                               op.capture_every)                       # rechecked NOW, under both locks
            r['plan'] = plan
            for l in launch_plan_text(plan).splitlines():
                self.log('# ' + l)
            bad = list(plan['problems'])
            if not bad and op.authorize != plan['token']:
                bad.append('authorisation %r is not this profile\'s token %s (from its dry run: RUN = the new run folder, '
                           'SHA12 = the host the runner validated)' % (op.authorize, plan['token']))
            if not bad and op.plan_id and op.plan_id != plan['plan_id']:
                bad.append('the profile / host / results changed after the launch plan was shown (plan %s, now %s): review '
                           'the plan again' % (op.plan_id, plan['plan_id']))
            if not bad and self.cancelled:
                bad.append('stopped before the start by %s' % (self.stop_req or {}).get('by'))
            if bad:
                return self._refuse(r, bad, 'LAUNCH REFUSED (nothing started)')
            self._launch_run(r, plan)
        finally:
            if lockp:
                try:
                    os.remove(lockp)
                except OSError:
                    pass

    def _stop_owned(self, stop, plan, t0):
        """stop the game this launch owns (by pid, verified), else the runner's tree by pid"""
        rp = runner_paths(self.cfg)
        sess = find_session(rp, plan['run_folder'], t0)
        g = game_launch(sess) if sess else None
        stop.update(session=sess, game=g)
        if g:
            ok, det = terminate_owned(g['pid'], self.proc.pid, g['image'])
            stop['actions'].append(det)
            stop['game_terminated'] = ok
            self.log('# STOP (%s, by %s): %s' % (stop['reason'], stop['by'], det))
            if ok:
                return
        else:
            stop['actions'].append('no game process recorded in the session yet')
        self._kill_tree(stop)

    def _capture(self, pid, why, t0, cdir):
        """one PrintWindow capture of the owned game window (wb_capture.py in its own DPI-aware process)"""
        el = time.time() - t0
        out = os.path.join(cdir, 'cap_%03d_%04ds_%s.png' % (len(self.captures) + 1, int(el), why))
        try:
            p = subprocess.run([self.cfg['python'], '-B', CAPTURE_PY, str(pid), out], capture_output=True, text=True, timeout=30,
                               cwd=os.path.dirname(CAPTURE_PY), creationflags=subprocess.CREATE_NO_WINDOW)
            res = json.loads((p.stdout.strip().splitlines() or ['{}'])[-1])
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            res = {'ok': False, 'why': repr(e)}
        res.update(why=why, at_s=round(el, 1))
        self.captures.append(res)
        self.log('# CAPTURE %s at %.1f s: %s' % (why, el, json.dumps(res)[:300]))

    def capture_now(self):
        with self._lk:
            self.capture_req += 1

    def _kill_tree(self, stop):
        p = subprocess.run([core.TASKKILL, '/PID', str(self.proc.pid), '/T', '/F'], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        det = 'taskkill /PID %d /T /F (the runner\'s own tree) -> exit %s %s' % (self.proc.pid, p.returncode,
                                                                                (p.stdout or p.stderr or '').strip()[:200])
        stop['actions'].append(det)
        stop['tree_killed'] = True
        self.log('# STOP: ' + det)

    def _launch_run(self, r, plan):
        cfg, dest, op = self.cfg, self.op.dest, self.op
        rp = runner_paths(cfg)
        state0 = state_hashes(dest)
        _history(dest, {'time': datetime.datetime.now().isoformat(timespec='seconds'), 'action': 'launch-start',
                        'token': plan['token'], 'plan_id': plan['plan_id'], 'run_folder': plan['run_folder'], 'log': self.log_path,
                        'by': getpass.getuser()})
        self.log('## g_run.py run %s --authorize-runtime %s (REAL launch)\n# cwd: %s\n# argv: %s'
                 % (LAUNCHER, plan['token'], rp['pc'], json.dumps(plan['argv'])))
        t0 = time.time()
        with self._lk:
            self.proc = subprocess.Popen(plan['argv'], cwd=rp['pc'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL,
                                         env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1'),
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        buf = []

        def reader():
            for raw in iter(self.proc.stdout.readline, b''):
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                buf.append(line)
                self.log(line)
        th = threading.Thread(target=reader, daemon=True)
        th.start()
        pc, wall = plan['preset'], plan['max_wall']
        ce = pc.get('capture_every') or 0
        cdir = os.path.join(dest, 'results', 'launch_%s_captures' % self.ts) if pc.get('window') else None
        stop = early = game = gh = None
        next_cap = next_look = 0
        while self.proc.poll() is None:
            time.sleep(0.2)
            now_t = time.time()
            el = now_t - t0
            if game is None and now_t >= next_look:              # the game this launch owns, once the runner recorded it
                next_look = now_t + 1.0
                s = find_session(rp, plan['run_folder'], t0)
                g = s and game_launch(s)
                if g and g['pid'] in owned_tree(self.proc.pid):
                    game, gh = g, _watch(g['pid'])
                    next_cap = now_t + ce if ce else 0
                    self.log('# game pid %d (owned: a descendant of the runner pid %d)' % (g['pid'], self.proc.pid))
            if gh and early is None and stop is None:
                code = _exit_code(gh)
                if code is not None:
                    early = {'game_exit': code, 'at_s': round(el, 1), 't': now_t, 'actions': []}
                    self.log('# the game ended by itself at %.1f s with exit code %d (0x%X)' % (el, code, code & 0xFFFFFFFF))
            if early and stop is None and not early.get('tree_killed') and now_t - early['t'] > op.early_exit_grace:
                early['actions'].append('the runner was still running %.0f s after the game ended' % op.early_exit_grace)
                self._kill_tree(early)
            if cdir and game and stop is None and early is None:
                with self._lk:
                    want = self.capture_req
                    self.capture_req = 0
                if want or (ce and now_t >= next_cap):
                    self._capture(game['pid'], 'requested' if want else 'every_%gs' % ce, t0, cdir)
                    next_cap = time.time() + ce if ce else 0
            if stop is None:
                with self._lk:
                    req = self.stop_req
                if req or el > wall:
                    if cdir and game and early is None:
                        self._capture(game['pid'], 'before_stop', t0, cdir)
                    stop = {'reason': 'operator' if req else 'timeout', 'at_s': round(el, 1), 'actions': [], 't': time.time(),
                            'by': req['by'] if req else 'the Workbench (wall limit %.0f s exceeded)' % wall,
                            'requested': req['time'] if req else datetime.datetime.now().isoformat(timespec='seconds')}
                    # td_run's boot scene notices a stopped game only when its sleep ends: wait for its result.json only
                    # if that is within the stop grace, else end its tree after the short grace (no result.json then)
                    left = float(pc['secs']) - el
                    stop['grace'] = op.stop_grace if left <= op.stop_grace else min(op.stop_grace, op.early_exit_grace)
                    if stop['grace'] < op.stop_grace:
                        stop['actions'].append('td_run sleeps %.0f s more (window %s s): its tree is ended %.0f s after the '
                                               'stop; td_run writes no result.json then' % (left, pc['secs'], stop['grace']))
                    if early:
                        stop['actions'].append('the game had already ended (exit %s at %s s)' % (early['game_exit'], early['at_s']))
                        self._kill_tree(stop)
                    else:
                        self._stop_owned(stop, plan, t0)
            elif not stop.get('tree_killed') and time.time() - stop['t'] > stop['grace']:
                stop['actions'].append('the runner did not end %.0f s after the stop' % stop['grace'])
                self._kill_tree(stop)
        game_exit = _exit_code(gh) if gh else None
        if gh:
            _win()['k'].CloseHandle(gh)
        if early:
            early.pop('t', None)
        th.join(15)
        rc = self.proc.returncode
        out = '\n'.join(buf)
        self.log('# runner exit %s after %.1f s' % (rc, time.time() - t0))
        m = re.search(r'\[g_run\] session (.+)', out)
        sess = m.group(1).strip() if m else find_session(rp, plan['run_folder'], t0)
        summ, summ_src = None, None
        for p in ([os.path.join(sess, 'summary.json')] if sess else []):
            try:
                summ, summ_src = json.load(open(p, encoding='utf-8')), 'summary.json'
            except (OSError, ValueError):
                pass
        if summ is None and sess:                                 # the runner's tree was ended: count its guard events
            ev = guard_events(sess)
            if ev:
                summ = {k: sum(1 for x in ev if x.get('kind') == k) for k in ('REFUSED', 'WOULD_LAUNCH', 'LAUNCH', 'POPEN')}
                summ_src = 'guard_events.jsonl (no summary.json: the runner was ended by the Workbench)'
        runf = plan['run_folder']
        res = None
        try:
            res = json.load(open(os.path.join(runf, 'result.json'), encoding='utf-8'))
        except (OSError, ValueError):
            pass
        scan = scan_game_log(os.path.join(runf, 'log.txt'))
        g = game_launch(sess) if sess else None
        if stop:
            stop.pop('t', None)
        e = {'wb_stop': stop, 'summary': summ, 'result': res, 'scene': 'boot', 'log': scan, 'runner_rc': rc,
             'runner_tail': ' | '.join(buf[-3:]), 'game_exit': game_exit}
        cls, detail = classify_launch(e)
        # the host writes fb_flip_<flip>.bmp for each requested flip and numbered fb_NNN.bmp files (v0.9 real run: 3 + 9)
        dumps = sorted(os.path.join(runf, n) for n in os.listdir(runf) if re.match(r'^fb_.+\.bmp$', n)) if os.path.isdir(runf) else []
        state1 = state_hashes(dest)
        now = datetime.datetime.now().isoformat(timespec='seconds')
        rec_path = os.path.join(dest, 'results', 'launch_%s.json' % self.ts)
        d = {'schema': LAUNCH_SCHEMA, 'time': now, 'profile': dest, 'profile_name': plan['name'], 'class': cls,
             'class_label': RESULT_CLASSES[cls], 'detail': detail, 'stopped_by': stop and stop['by'], 'stop': stop,
             'token': plan['token'], 'plan_id': plan['plan_id'], 'argv': plan['argv'], 'runner_rc': rc, 'summary': summ,
             'result': res, 'game': g, 'log': scan, 'run_folder': runf, 'session': sess,
             'result_json': os.path.join(runf, 'result.json'), 'game_log': os.path.join(runf, 'log.txt'),
             'guard_events': sess and os.path.join(sess, 'guard_events.jsonl'),
             'summary_json': sess and os.path.join(sess, 'summary.json'), 'workbench_log': self.log_path,
             'root': plan['root'], 'root_used_by_after': (root_marker(plan['root']) or {}).get('used_by'),
             'host_sha256': plan['host']['sha256'], 'members': [(x['mod_id'], x['version'], x['kind']) for x in plan['members']],
             'state_before': state0, 'state_after': state1, 'state_unchanged': state0 == state1,
             'visual': VISUAL_NOTE, 'record': rec_path, 'seconds': round(time.time() - t0, 1),
             'preset': pc, 'summary_source': summ_src, 'game_exit_code': game_exit, 'early_exit': early,
             'captures': self.captures, 'captures_folder': cdir if self.captures else None,
             'frame_dumps': [{'path': x, 'bytes': os.path.getsize(x)} for x in dumps]}
        _write_json(rec_path, d)
        _write_json(os.path.join(dest, 'LAUNCH.json'), d)
        _history(dest, {'time': now, 'action': 'launch', 'class': cls, 'stopped_by': d['stopped_by'], 'run_folder': runf,
                        'session': sess, 'record': rec_path, 'log': self.log_path})
        r.update(ok=cls in ('runner_stop_boot_window', 'normal_exit'), verdict='LAUNCH %s' % RESULT_CLASSES[cls].upper(),
                 launch=d, run_dir=runf, session=sess, summary=d['summary_json'], game_log=d['game_log'],
                 result_json=d['result_json'], guard_events=d['guard_events'], record=rec_path,
                 captures=d['captures_folder'])


def summarize(r):
    if r.get('kind') == 'profile-check':
        return check_text(r)
    L = ['TEST PROFILE %s: %s' % (r.get('action', '').upper(), r.get('verdict'))]
    for c in r.get('checks') or []:
        L.append('  %-44s %s  %s' % (c['check'], 'ok' if c['ok'] else 'FAILED', c['detail']))
    if r.get('action') == 'prepare' and r.get('check'):
        L.append(check_text(r['check']))
    if r.get('ok') and r.get('action') == 'prepare':
        p = r['profile_data']
        L += ['profile: %s (%d mods)' % (r['profile'], len(p['members'])),
              'data root (%s, verified): %s (%s files)' % (p['root_mode'], r['root'], p['root_marker']['files']),
              'next: Preflight, then Dry run']
    if r.get('action') == 'launch' and r.get('plan') and not r.get('launch'):
        L.append(launch_plan_text(r['plan']))
    if r.get('launch'):
        L.append(launch_text(r['launch']))
    if r.get('dryrun'):
        d = r['dryrun']
        L += ['g_run: %s' % json.dumps(d['summary']), 'session: %s' % d['session'], 'run folder: %s' % d['run_folder'],
              'root used_by after: %s' % d['root_used_by_after'],
              'a REAL run is not done here: it needs the owner present and the token %s (see tools\\runners\\README.md)'
              % d['real_run']['example_token']]
    for p in r.get('problems') or []:
        L.append('  ' + p)
    L.append('full log: %s' % r.get('log'))
    return '\n'.join(L)


def check_text(i):
    L = ['TEST PROFILE CHECK: %s' % ('OK - Prepare can run' if not i['problems'] else 'NOT OK')]
    ms = i.get('members') or []
    if ms:
        L.append('  mods        %d (%d plugin, %d data only)%s' % (len(ms), sum(m['kind'] == 'plugin' for m in ms),
                                                                 sum(m['kind'] == 'data' for m in ms),
                                                                 '; switched off: %s' % ', '.join(m['mod_id'] for m in ms if not m.get('enabled', True))
                                                                 if not all(m.get('enabled', True) for m in ms) else ''))
    for n, p in enumerate(ms, 1):
        q = p.get('requirements') or {}
        L.append('  [%d] %-6s %s %s%s  package %s' % (n, p['kind'], p.get('mod_id'), p.get('version') or '',
                                                     '' if p.get('enabled', True) else ' (OFF: mod-list.toml disabled)', p.get('package')))
        if p['kind'] == 'plugin':
            L.append('       module %s sha256 %s' % (p.get('module'), p.get('module_sha256')))
        L += ['       files %d, digest %s; record %s (sha256 %s)' % (len(p.get('files') or {}), (p.get('digest') or '')[:12],
                                                                     p.get('record_path'), (p.get('record_sha256') or '')[:12]),
              '       requires    %s' % req_text(q),
              '       built with  %s' % ((p.get('kit_identity') or {}).get('id'))
              if p.get('recipe') != wb_stage.IMPORT_RECIPE else
              '       IMPORTED    %s; validated with %s' % (p.get('provenance'), (p.get('kit_identity') or {}).get('id'))]
        a = p.get('approval') or {}
        if a:
            L.append('       approval    %s (%s)' % ('not needed' if not a.get('needed') else
                                                     'APPROVED by the player' if a['ok'] else 'NOT APPROVED', a['detail']))
    h = i.get('host') or {}
    if h:
        L.append('  host        %s  sha256 %s  build %s  platform %s' % (h['path'], h['sha256'][:12], h.get('build_identity'), h.get('platform')))
        if i.get('host_why'):
            L.append('              %s%s' % (i['host_why'], ' (%d services)' % len(i['host_services']) if i.get('host_services') else ''))
    a = i.get('admission')
    if a:
        if a.get('error'):
            L.append('  admission   NOT CHECKED: %s' % a['error'])
        else:
            L.append('  admission   %s by the host\'s own readers (%s, bmpack %s, readers %s)' % (
                'ACCEPTED' if a['ok'] else 'REFUSED', a['kit'], a.get('bmpack'), a.get('readers')))
            L.append('              load order: %s%s' % (', '.join('%s %s%s' % (x['id'], x['version'], '' if x['usable'] else ' (refused)')
                                                               for x in a['order']) or '-',
                                                     ' (dependency order: %d moved)' % a['dependency_moved'] if a.get('dependency_moved') else ''))
            for f in a.get('refusals') or []:
                L.append('              [%s] %s: %s' % (f['service'], f['mod'] or '-', f['why']))
    if i.get('predecessor'):
        L.append('  successor of %s: %s' % (i.get('predecessor_name') or i['predecessor'], changes_text(i.get('changes'))))
    if i.get('root_plan'):
        L.append('  data root   %s' % i['root_plan'])
    if i.get('kit_note'):
        L.append('  kit         %s' % i['kit_note'])
    L += ['  note: ' + x for x in i.get('disabled_notes') or []]
    L += ['  problem: ' + x for x in i['problems']]
    return '\n'.join(L)


def status_text(st, current_kit=None):
    if not st.get('ok'):
        return 'PROFILE STATUS: ' + '; '.join(st['problems'])
    d = st.get('dryrun') or {}
    L = ['PROFILE STATUS %s (%s)' % (st['profile'], st['schema'])]
    for m in st['members']:
        L.append('  %-6s %s %s%s  %s' % (m['kind'], m['mod_id'], m['version'] or '', '' if m.get('enabled', True) else ' (OFF)',
                                         ('module sha256 %s' % m['module_sha256'])
                                         if m['kind'] == 'plugin' else 'files digest %s' % (m['digest'] or '')[:12]))
    if st.get('load_order'):
        L.append('  load order (host admission at prepare): %s' % ', '.join('%s %s' % (x['id'], x['version']) for x in st['load_order']))
    L += ['  host %s (%s)' % (st['host']['path'], st['host']['build_identity']),
          '  kit at prepare %s; packages built with %s; current %s' % ((st['kit_at_prepare'] or {}).get('id'),
                                                                      ', '.join(st['package_kits']), (current_kit or {}).get('id')),
          '  data root %s (%s)' % (st.get('root'), st.get('root_mode') or 'g_run make-root'),
          '  profile record: %s' % (st['profile_record'] if isinstance(st['profile_record'], str) else '; '.join(st['profile_record'])),
          '  preflight: %s %s' % (st['preflight'], '; '.join(st['preflight_why'])),
          '  last dry run: %s' % (('OK %s (%s)' % (d.get('time'), st['dryrun_state'])) if d.get('ok') else 'none')]
    if st['results']:
        L.append('  results (oldest first):')
        for h in st['results']:
            L.append('    %-9s %s  %s%s' % (h['kind'], h['time'], h['state'], (': ' + '; '.join(h['why'])) if h['why'] else ''))
    if st.get('predecessor'):
        p = st['predecessor']
        L.append('  successor of %s: %s' % (p['name'], changes_text(p.get('changes'))))
        for h in p['results']:
            L.append('    %-9s %s  STALE: %s' % (h['kind'], h['time'], '; '.join(h['why'])))
    for s in st.get('superseded_by') or []:
        L.append('  superseded by %s (this profile is unchanged)' % s)
    if st.get('root_used_by'):
        L.append('  data root USED by %s: no further launch from this profile (successor with a NEW root)' % st['root_used_by'])
    for x in st.get('launches') or []:
        L.append('  launch %s  %s: %s%s' % (x['time'], RESULT_CLASSES.get(x['class'], x['class']), x['detail'],
                                           ' (stopped by %s)' % x['stopped_by'] if x.get('stopped_by') else ''))
        L.append('         run %s; session %s' % (x['run_folder'], x['session']))
    return '\n'.join(L)


def run_sync(cfg, op, timeout=None):
    lock = core.OpLock(cfg)
    why = lock.acquire(op.title)
    if why:
        raise RuntimeError(why)
    try:
        job = ProfileJob(cfg, op).start()
        try:
            if not job.wait(timeout):
                job.cancel()
                job.wait(60)
        except KeyboardInterrupt:                                  # CLI Ctrl+C = Stop (the launch's own tree only)
            job.cancel(by='operator %s (CLI Ctrl+C, pid %d)' % (getpass.getuser(), os.getpid()))
            job.wait(op.stop_grace + 60 if op.action == 'launch' else 60)
        return job, job.result_dict
    finally:
        lock.release()


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['check', 'prepare', 'status', 'preflight', 'dryrun', 'draft', 'launch-plan', 'launch',
                                    'results', 'successor', 'preview'])

    class _Op(argparse.Action):                                    # v0.10: --add / --enable / --disable / --remove in order
        def __call__(self, parser, ns, values, option_string=None):
            ns.ops = (getattr(ns, 'ops', None) or []) + [(self.dest, values)]
    for o in DRAFT_ACTIONS:
        ap.add_argument('--' + o, action=_Op, dest=o, default=None)
    ap.add_argument('--even-if-required', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--authorize-runtime')
    ap.add_argument('--plan-id')
    ap.add_argument('--preset', default='boot', choices=sorted(PRESETS))
    ap.add_argument('--secs')
    ap.add_argument('--dump-flips')
    ap.add_argument('--capture-every')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--approvals')
    ap.add_argument('--config')
    ap.add_argument('--kit')
    ap.add_argument('--draft')
    ap.add_argument('--predecessor')
    ap.add_argument('--new-root', action='store_true')
    ap.add_argument('--host')
    ap.add_argument('--dest')
    ap.add_argument('--from-profile')
    a = ap.parse_args(argv)
    ops = getattr(a, 'ops', None) or []
    cfg = core.load_config(a.config, kit=a.kit)
    if a.cmd == 'preview':
        if len(a.args) != 1:
            ap.error('preview MOD_FOLDER [--draft FILE | PROFILE_DIR] [--host EXE] [--approvals FILE] [--json]  (read only)')
        d = new_draft()
        if a.draft:
            d, bad = load_draft(a.draft)
            if bad:
                print('\n'.join(bad))
                return 3
        for k, v in (('host', a.host), ('approvals', a.approvals)):
            if v is not None:
                d[k] = os.path.abspath(v) if v else ''
        P = preview(cfg, a.args[0], d)
        print(json.dumps(P, indent=1, default=str) if a.json else preview_text(P))
        return 0 if P.get('mod') else 3
    if a.cmd == 'draft':
        if len(a.args) != 1:
            ap.error('draft FILE [--add PACKAGE] [--enable|--disable|--remove MOD_ID|PACKAGE] [--even-if-required] [--host EXE] '
                     '[--approvals FILE] [--dest DIR] [--from-profile DIR] [--predecessor DIR] [--new-root]')
        f = a.args[0]
        if _is_profile_path(f):
            print('refused: %s is (inside) a prepared profile: a prepared profile is never changed; write the draft elsewhere '
                  '(--from-profile DIR makes a successor draft)' % f)
            return 3
        d, reps, bad = draft_compute(a.from_profile or f, ops, f, a.even_if_required)      # in memory: nothing written yet
        if bad:
            print(json.dumps({'draft': f, 'written': False, 'refused': bad, 'reports': reps,
                              'note': 'nothing changed (the draft file, if any, keeps its bytes)'}, indent=1))
            return 3
        for k, v in (('host', a.host), ('approvals', a.approvals), ('dest', a.dest), ('predecessor', a.predecessor)):
            if v is not None:
                d[k] = os.path.abspath(v) if v else ''
        if a.new_root:
            d['reuse_root'] = False
        try:
            save_draft(f, d)
        except OSError as e:
            print(json.dumps({'draft': f, 'written': False, 'refused': ['draft not written (unchanged): %s' % e]}, indent=1))
            return 3
        rows = member_rows(cfg, d['packages'], d['approvals'], d['disabled'])
        print(json.dumps({'draft': f, 'written': True, 'notes': sum((r.get('notes') or [] for r in reps), []),
                          'dependents': sum((r.get('dependents') or [] for r in reps), []),
                          'needs': sum((r.get('needs') or [] for r in reps), []), 'host': d['host'], 'approvals': d['approvals'],
                          'dest': d['dest'], 'predecessor': d['predecessor'], 'reuse_root': d['reuse_root'],
                          'disabled': d['disabled'], 'members': rows}, indent=1))
        return 0
    if a.cmd in ('check', 'prepare'):
        if a.draft:
            d, bad = load_draft(a.draft)
            if bad:
                print('\n'.join(bad))
                return 3
            pkgs, host, dest, appr, pred, reuse = (d['packages'], d['host'], d['dest'], d['approvals'], d['predecessor'] or None,
                                                   d['reuse_root'])
            off = d['disabled']
        else:
            if len(a.args) < 3:
                ap.error('%s PACKAGE [PACKAGE ...] HOST_EXE PROFILE_DIR --approvals FILE (or --draft FILE)' % a.cmd)
            pkgs, host, dest = a.args[:-2], a.args[-2], a.args[-1]
            appr, pred, reuse, off = a.approvals, a.predecessor, not a.new_root, []
        if a.cmd == 'check':
            i = inspect(cfg, pkgs, host, dest, appr, pred, reuse, off)
            print(check_text(i))
            return 0 if not i['problems'] else 3
        _, r = run_sync(cfg, ProfileOp('prepare', dest, pkgs, host, appr, pred, reuse, disabled=off))
    elif a.cmd == 'status':
        if len(a.args) != 1:
            ap.error('status PROFILE_DIR')
        print(json.dumps(profile_status(cfg, a.args[0]), indent=1))
        return 0
    elif a.cmd in ('launch-plan', 'results'):
        if len(a.args) != 1:
            ap.error('%s PROFILE_DIR' % a.cmd)
        if a.cmd == 'results':
            print(results_text(os.path.abspath(a.args[0])))
            return 0
        P = launch_plan(cfg, os.path.abspath(a.args[0]), a.secs, None, a.preset, a.dump_flips, a.capture_every)
        print(launch_plan_text(P))
        return 0 if not P['problems'] else 3
    elif a.cmd == 'successor':
        if len(a.args) != 1 or not a.dest:
            ap.error('successor PROFILE_DIR --dest NEW_PROFILE_DIR [--approvals FILE] [--check]  (always a NEW data root)')
        d, bad = successor_draft(a.args[0], a.dest, a.approvals)
        if bad:
            print('\n'.join(bad))
            return 3
        i = inspect(cfg, d['packages'], d['host'], d['dest'], d['approvals'], d['predecessor'], False, d['disabled'])
        print(check_text(i))
        if a.check or i['problems']:
            return 0 if not i['problems'] else 3
        _, r = run_sync(cfg, ProfileOp('prepare', d['dest'], d['packages'], d['host'], d['approvals'], d['predecessor'], False,
                                       disabled=d['disabled']))
    elif a.cmd == 'launch':
        if len(a.args) != 1 or not a.authorize_runtime:
            ap.error('launch PROFILE_DIR --authorize-runtime RUN:SHA12 (the token launch-plan prints; owner present)')
        _, r = run_sync(cfg, ProfileOp('launch', os.path.abspath(a.args[0]), authorize=a.authorize_runtime, plan_id=a.plan_id,
                                       boot_secs=a.secs, preset=a.preset, dump_flips=a.dump_flips, capture_every=a.capture_every))
    else:
        if len(a.args) != 1:
            ap.error('%s PROFILE_DIR' % a.cmd)
        _, r = run_sync(cfg, ProfileOp(a.cmd, a.args[0]))
    print(summarize(r))
    return 0 if r.get('ok') else 3


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
