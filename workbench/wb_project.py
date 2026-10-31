"""wb_project - Workbench v0.5: "New plugin project" (gp\\workbench, 2026-10-28).

create_project() writes a minimal native plugin project from the kit's SDK example (h) host-info template, under a declared
identity: a namespaced mod id, a display name and a module name. The project holds
    mod.toml                  id / name / [plugin] windows = "<module>.asi"
    <module>.c                a minimal plugin (init + shutdown log lines; the SDK's API version export)
    workbench-project.json    the declared identity + where the template came from (sha256 of the kit files)
    README.txt
and NO build script: the Workbench builds it with its own fixed CMakeLists.txt (project_cmake(), written into the build copy,
never into the project), from validated names only. A project that adds CMakeLists.txt / *.cmake is refused, not configured.
Staged folder = the mod id; module = <module>.asi; source = <module>.c; mod.toml id / name = the declared ones.
An existing non-empty folder is never written; the project appears in one rename (created complete or not at all).
Nothing here builds, installs, approves or launches anything.
v0.6: the marker records the exact kit identity (wb_kit) the project is bound to. A kit change never migrates a project:
kit_status() reports it, the build refuses it, and rebind_project() (an explicit user action) moves the binding to the current
kit, keeping the previous binding in kit_history. Projects made before v0.6 have no binding ("unbound"): bind them the same way.
"""
import datetime
import json
import os
import re
import shutil
import tomllib

import wb_core as core
import wb_kit

SCHEMA = 'bm-workbench-project/1'
MARKER = 'workbench-project.json'
TEMPLATE = r'sdk\examples\host-info'                  # the kit's reviewed SDK example the template follows
TEMPLATE_FILES = ('CMakeLists.txt', 'bm_sdk_host_info.c', 'mod.toml')
TEMPLATE_PIN = '22804948a908a55d47d708f1c5a95d48cf0a3a095d50b145fd18d93ed7865cf8'   # its CMakeLists.txt (kit 0.6.0)
SDK_NEEDS = (r'sdk\cmake\bmsdk.cmake', r'sdk\cmake\llvm-mingw-x86_64.cmake', r'sdk\include\bmashup_sdk.h',
             r'sdk\include\takedawn_plugin.h')

MOD_ID_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)+$')
MODULE_RE = re.compile(r'^[a-z][a-z0-9_]{1,39}$')
SOURCE_RE = re.compile(r'^[A-Za-z0-9_]+\.c$')
RESERVED_NS = ('bmashup', 'bmashup-sdk', 'takedawn', 'bm', 'sdk', 'kit', 'example', 'examples')
WIN_DEVICES = {'con', 'prn', 'aux', 'nul'} | {'com%d' % i for i in range(10)} | {'lpt%d' % i for i in range(10)}
CMAKE_RESERVED = {'all', 'clean', 'help', 'install', 'test', 'package', 'package_source', 'edit_cache', 'rebuild_cache',
                  'list_install_components', 'install_strip', 'install_local', 'cmake'}
KIT_MODULES = {'bm_sdk_host_info'}
FORBIDDEN_BUILD_FILES = re.compile(r'^(CMakeLists\.txt|.*\.cmake|CMakePresets\.json|CMakeUserPresets\.json|Makefile|'
                                   r'build\.ninja|.*\.(ps1|bat|cmd|sh))$', re.I)


# ---------------------------------------------------------------- names
def check_mod_id(v):
    if not v:
        return 'mod id is empty: give a namespaced id such as yourname.my-plugin (lower case)'
    if len(v) > 64:
        return 'mod id is longer than 64 characters: %r' % v
    if not MOD_ID_RE.match(v):
        return ('mod id %r is not a namespaced id: lower-case letters, digits and "-", at least two parts joined by "." '
                '(such as yourname.my-plugin); no spaces, "/", "\\", ".." or upper case' % v)
    ns = v.split('.')[0]
    if ns in RESERVED_NS:
        return 'mod id %r uses the reserved namespace "%s." (the kit and the platform use it): choose your own' % (v, ns)
    if ns in WIN_DEVICES:
        return 'mod id %r starts with the Windows device name "%s" (the staged folder could not be made)' % (v, ns)
    return None


def check_name(v):
    if not v or not v.strip():
        return 'display name is empty'
    if v != v.strip():
        return 'display name starts or ends with spaces: %r' % v
    if len(v) > 64:
        return 'display name is longer than 64 characters'
    if any(ord(c) < 32 or ord(c) == 127 for c in v) or '"' in v or '\\' in v:
        return 'display name may not contain quotes, backslashes, tabs or line breaks: %r' % v
    return None


def check_module(v):
    if not v:
        return 'module name is empty: give a C-style name such as my_plugin (becomes my_plugin.asi and my_plugin.c)'
    if not MODULE_RE.match(v):
        return ('module name %r: 2-40 characters, lower-case letters, digits and "_", starting with a letter (it becomes the '
                'file names <module>.c and <module>.asi); no ".", "-", spaces or path separators' % v)
    if v in WIN_DEVICES or v in CMAKE_RESERVED or v.startswith('cmake'):
        return 'module name %r is reserved (Windows device name or build-system target)' % v
    if v in KIT_MODULES or v.startswith('takedawn'):
        return 'module name %r is used by the kit / the host; choose your own' % v
    return None


def check_identity(mod_id, name, module):
    return [x for x in (check_mod_id(mod_id), check_name(name), check_module(module)) if x]


# ---------------------------------------------------------------- templates (Workbench-owned; only validated names go in)
def mod_toml(mod_id, name, module):
    return ('# Generated by the Burnout Mashup Workbench from the SDK example (h) host-info template. Keep id, name and\n'
            '# [plugin] windows equal to workbench-project.json (the Workbench checks them before every build).\n'
            'id = "%s"\nname = "%s"\nversion = "0.1.0"\n'
            'description = "A native plugin made with the Workbench (logs one line when loaded and one at shutdown)."\n\n'
            '[bmashup]\nplatform = ">=0.1"\n\n'
            '[plugin]\napi = 1\nwindows = "%s.asi"\n# Only Windows x64 is built and tested by this SDK.\n') % (mod_id, name, module)


def plugin_c(mod_id, module):
    return ('/*\n'
            ' * %(m)s.c - native plugin %(id)s, generated by the Burnout Mashup Workbench from the SDK example (h)\n'
            ' * host-info template. It changes nothing in the game: it logs one line when the host loads it and one at shutdown.\n'
            ' * Add your code here. Build: the Workbench (Build / stage tab), which uses its own build steps; this project has no\n'
            ' * build script of its own. The player reviews and approves the module bytes before the host runs them.\n'
            ' */\n'
            '#include "bmashup_sdk.h"\n\n'
            '#define TAG "%(m)s"\n\n'
            'static const td_host_api *s_api;\n\n'
            'static void TD_CALL on_shutdown(void *user)\n'
            '{\n'
            '    (void)user;\n'
            '    bmsdk_log(s_api, TD_LOG_INFO, TAG ": shutdown");\n'
            '}\n\n'
            'BMSDK_DEFINE_API_VERSION()\n\n'
            'TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)\n'
            '{\n'
            '    s_api = api;\n'
            '    if (info && info->struct_size >= BMSDK_FIELD_END(td_plugin_info, user)) {\n'
            '        info->on_shutdown = on_shutdown;\n'
            '        info->user = NULL;\n'
            '    }\n'
            '    bmsdk_log(api, TD_LOG_INFO, TAG ": loaded (%(id)s, bmashup-sdk %%s)", BMSDK_VERSION_STRING);\n'
            '    return TD_OK;\n'
            '}\n') % {'m': module, 'id': mod_id}


def readme(mod_id, name, module):
    return ('%s (%s)\n\nA native plugin project made by the Burnout Mashup Workbench (New plugin project) from the kit\'s SDK\n'
            'example (h) host-info template.\n\n  %s.c                  the plugin source (edit it; more .c / .h files beside it are built too)\n'
            '  mod.toml              the manifest (id, name and [plugin] windows must stay as declared)\n'
            '  workbench-project.json  the declared identity and the template\'s provenance\n\n'
            'Build / validate / stage: Workbench -> Build / stage tab -> this folder -> a staging folder. The Workbench uses its own\n'
            'build steps (a CMakeLists.txt or other build script in this folder is refused). The staged folder is named %s and\n'
            'holds %s.asi + mod.toml. Native code is never approved by the Workbench: review the source and approve the\n'
            'recorded sha256 yourself (kit docs\\INSTALL.md).\n') % (name, mod_id, module, mod_id, module)


def project_cmake(ident, sources):
    """the Workbench's own build script for a project (written into the build copy, never into the project)"""
    src = '\n'.join('        ${CMAKE_CURRENT_LIST_DIR}/%s' % s for s in sources)
    return ('# Generated by the Burnout Mashup Workbench (wb_project.project_cmake) for %(id)s. Not the project\'s file: the\n'
            '# Workbench never runs a project\'s own build script. Follows the kit\'s sdk\\examples\\host-info\\CMakeLists.txt.\n'
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(%(m)s LANGUAGES C)\n'
            'include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)\n'
            'bmsdk_add_plugin(%(m)s\n'
            '    SOURCES\n%(src)s\n'
            '    MOD_DIR %(folder)s\n'
            '    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)\n') % {'id': ident['mod_id'], 'm': ident['module'],
                                                                   'src': src, 'folder': ident['folder']}


# ---------------------------------------------------------------- prerequisites / guards
def kit_problems(cfg):
    kit = cfg.get('kit') or ''
    if not kit:
        return ['kit: ' + core.check_value('kit', '')]
    out = []
    for f in [os.path.join(TEMPLATE, x) for x in TEMPLATE_FILES] + list(SDK_NEEDS):
        if not os.path.isfile(os.path.join(kit, f)):
            out.append('kit file missing: %s (is %s a mod kit folder with the SDK?)' % (f, kit))
    cm = os.path.join(kit, TEMPLATE, 'CMakeLists.txt')
    if os.path.isfile(cm) and core_sha(cm) != TEMPLATE_PIN:
        out.append('the kit\'s %s\\CMakeLists.txt is not the reviewed one (sha256 %s, expected %s)'
                   % (TEMPLATE, core_sha(cm)[:12], TEMPLATE_PIN[:12]))
    return out


def core_sha(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def folder_problems(cfg, folder, raw=None):
    """where a new project may go: an absolute path, no '..', parent exists, the folder new or empty, not in a protected
    location, a kit, game data, a release, a sealed / frozen folder, another mod or a Workbench staging folder"""
    import wb_stage
    raw = raw if raw is not None else folder
    if not raw or not raw.strip():
        return ['no project folder chosen']
    if not os.path.isabs(raw):
        return ['the project folder must be a full path (such as D:\\mods\\my plugin): %s' % raw]
    if any(p == '..' for p in re.split(r'[\\/]+', raw)):
        return ['the project folder may not contain ".." (path traversal): %s' % raw]
    folder = os.path.abspath(raw)
    out = []
    parent = os.path.dirname(folder)
    if not os.path.isdir(parent):
        out.append('the parent folder does not exist: %s' % parent)
    if os.path.isfile(folder):
        out.append('a file has this name: %s' % folder)
    elif os.path.isdir(folder) and os.listdir(folder):
        out.append('the folder already exists and is not empty (the Workbench never overwrites a project; choose a new '
                   'folder): %s' % folder)
    for w in wb_stage.check_destination(cfg, None, folder):
        if 'non-empty folder not made by the Workbench' not in w:
            out.append(w)
    a = folder
    while True:
        if os.path.isdir(os.path.join(a, '.wb_stage')):
            out.append('inside a Workbench staging folder (%s): put projects elsewhere' % a)
            break
        n = os.path.dirname(a)
        if n == a:
            break
        a = n
    return out


# ---------------------------------------------------------------- create / read
def create_project(cfg, folder, mod_id, name, module):
    """-> {'ok', 'verdict', 'project', 'problems', 'warnings', 'files'}; writes nothing unless every check passed"""
    folder_raw = folder
    bad = check_identity(mod_id, name, module) + kit_problems(cfg) + folder_problems(cfg, folder, folder_raw)
    res = {'kind': 'new-project', 'ok': False, 'project': os.path.abspath(folder) if folder and os.path.isabs(folder) else folder,
           'mod_id': mod_id, 'name': name, 'module': module, 'problems': bad}
    if bad:
        res['verdict'] = 'NOT CREATED'
        return res
    import wb_stage
    folder = os.path.abspath(folder)
    res['warnings'] = wb_stage.tool_prereqs(cfg, wb_stage.RECIPES['plugin-project'])   # needed to build, not to create
    kit = cfg['kit']
    files = {'mod.toml': mod_toml(mod_id, name, module), module + '.c': plugin_c(mod_id, module),
             'README.txt': readme(mod_id, name, module)}
    ident = {'schema': SCHEMA, 'mod_id': mod_id, 'name': name, 'module': module, 'folder': mod_id,
             'created': datetime.datetime.now().isoformat(timespec='seconds'),
             'template': {'kit': kit, 'example': TEMPLATE,
                          'files': {f: core_sha(os.path.join(kit, TEMPLATE, f)) for f in TEMPLATE_FILES},
                          'generator': 'Workbench wb_project.py (v0.6)'},
             'kit': wb_kit.stamp(wb_kit.kit_identity(kit)), 'kit_history': [],
             'created_files': {f: _sha_text(t) for f, t in files.items()},
             'build': 'Workbench-owned (wb_project.project_cmake + the SDK by-hand CMake steps); no project build script'}
    tmp = os.path.join(os.path.dirname(folder), '.%s.wb_new_%s' % (os.path.basename(folder),
                                                                    datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    os.makedirs(tmp)
    try:
        for f, t in files.items():
            with open(os.path.join(tmp, f), 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(t)
        with open(os.path.join(tmp, MARKER), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(ident, fh, indent=1)
        if os.path.isdir(folder):
            if os.listdir(folder):                                 # appeared meanwhile: never overwrite
                raise FileExistsError(folder)
            os.rmdir(folder)                                       # empty folder: replaced by the complete project
        os.rename(tmp, folder)
    except Exception as e:                                         # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)                     # our own half-written temp folder only
        res.update(verdict='NOT CREATED', problems=['could not create the project: %r' % e])
        return res
    res.update(ok=True, verdict='CREATED', project=folder, files=sorted(list(files) + [MARKER]), identity=ident)
    return res


def _sha_text(t):
    import hashlib
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def is_project(project):
    return bool(project) and os.path.isfile(os.path.join(project, MARKER))


def read_project(project):
    """-> (identity {mod_id, name, module, folder, sources}, problems). Re-checks the declared names and that mod.toml, the
    source and the module agree with them; refuses any build script in the project."""
    try:
        d = json.load(open(os.path.join(project, MARKER), encoding='utf-8'))
    except (OSError, ValueError) as e:
        return None, ['%s is unreadable: %s' % (MARKER, e)]
    if not isinstance(d, dict) or d.get('schema') != SCHEMA:
        return None, ['%s: schema is not %s' % (MARKER, SCHEMA)]
    mod_id, name, module = d.get('mod_id'), d.get('name'), d.get('module')
    bad = check_identity(mod_id if isinstance(mod_id, str) else '', name if isinstance(name, str) else '',
                         module if isinstance(module, str) else '')
    if bad:
        return None, ['%s: %s' % (MARKER, b) for b in bad]
    if d.get('folder', mod_id) != mod_id:
        bad.append('%s: folder %r must equal the mod id %r' % (MARKER, d.get('folder'), mod_id))
    try:
        t = tomllib.loads(open(os.path.join(project, 'mod.toml'), encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, bad + ['mod.toml: %s' % e]
    plug = t.get('plugin') if isinstance(t.get('plugin'), dict) else {}
    for k, want, got in (('id', mod_id, t.get('id')), ('name', name, t.get('name')),
                         ('[plugin] windows', module + '.asi', plug.get('windows')), ('[plugin] api', 1, plug.get('api'))):
        if got != want:
            bad.append('mod.toml %s is %r, the declared identity says %r (keep them equal, or make a new project)' % (k, got, want))
    names = sorted(os.listdir(project))
    if module + '.c' not in names:
        bad.append('the source %s.c is missing (the module name decides the source and .asi names)' % module)
    for n in names:
        if FORBIDDEN_BUILD_FILES.match(n):
            bad.append('%s: a project build script is never used or run; the Workbench owns the build (remove it)' % n)
        elif n.lower().endswith('.c') and not SOURCE_RE.match(n):
            bad.append('source file name %r: letters, digits and "_" only' % n)
    sources = [n for n in names if SOURCE_RE.match(n)]
    return {'mod_id': mod_id, 'name': name, 'module': module, 'folder': mod_id, 'sources': sources}, bad


def _marker(project):
    try:
        return json.load(open(os.path.join(project, MARKER), encoding='utf-8'))
    except (OSError, ValueError):
        return None


def kit_status(cfg, project):
    """-> {state: same | different | unbound | unreadable, recorded, current, diff, text}. Read only."""
    d = _marker(project)
    cur = wb_kit.kit_identity(cfg.get('kit'))
    if not isinstance(d, dict):
        return {'state': 'unreadable', 'recorded': None, 'current': wb_kit.stamp(cur), 'diff': [],
                'text': '%s is unreadable' % MARKER}
    rec = d.get('kit') if isinstance(d.get('kit'), dict) else None
    if not rec:
        st, txt = 'unbound', ('the project has no kit binding (made before Workbench v0.6): bind it to the current kit %s '
                              'explicitly (Rebind), then build' % (cur or {}).get('id'))
    elif wb_kit.same(rec, cur):
        st, txt = 'same', 'bound to the current kit %s' % rec.get('id')
    else:
        st, txt = 'different', ('bound to kit %s, the current kit is %s: not migrated. Rebind explicitly to build with the '
                                'current kit (earlier staged outputs are kept), or switch the kit back'
                                % (rec.get('id'), (cur or {}).get('id')))
    return {'state': st, 'recorded': rec, 'current': wb_kit.stamp(cur), 'diff': wb_kit.diff(rec, cur) if rec else [],
            'text': txt, 'history': d.get('kit_history') or []}


def rebind_project(cfg, project):
    """explicit user action: bind the project to the current kit. Writes only workbench-project.json (atomic replace); the
    previous binding goes to kit_history. Refused when the project or the kit does not check out, or nothing would change."""
    res = {'kind': 'rebind', 'ok': False, 'project': project, 'verdict': 'NOT REBOUND'}
    _, bad = read_project(project) if is_project(project) else (None, ['not a Workbench plugin project (no %s)' % MARKER])
    bad = list(bad) + kit_problems(cfg)
    st = kit_status(cfg, project)
    if not bad and st['state'] == 'same':
        bad.append('already bound to the current kit %s' % st['recorded']['id'])
    res['problems'] = bad
    if bad:
        return res
    d = _marker(project)
    hist = list(d.get('kit_history') or [])
    hist.append({'kit': st['recorded'], 'until': datetime.datetime.now().isoformat(timespec='seconds'),
                 'reason': 'rebound by the user to %s' % st['current']['id']})
    d['kit'], d['kit_history'] = st['current'], hist
    p = os.path.join(project, MARKER)
    tmp = p + '.wb_tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(d, fh, indent=1)
    os.replace(tmp, p)
    res.update(ok=True, verdict='REBOUND', previous=st['recorded'], kit=st['current'], diff=st['diff'])
    return res


def main(argv):
    """wb_project.py new FOLDER --id MOD_ID --name NAME --module MODULE [--kit DIR] [--config FILE] -> one JSON line
    (exit 0 created, 3 not created); wb_project.py status|rebind FOLDER [--kit DIR] [--config FILE]"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['new', 'check', 'status', 'rebind'])
    ap.add_argument('folder')
    ap.add_argument('--id', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--module', default='')
    ap.add_argument('--kit')
    ap.add_argument('--config')
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config, kit=a.kit)
    if a.cmd == 'check':
        bad = check_identity(a.id, a.name, a.module) + kit_problems(cfg) + folder_problems(cfg, a.folder)
        print(json.dumps({'verdict': 'OK' if not bad else 'NOT OK', 'problems': bad}))
        return 0 if not bad else 3
    if a.cmd == 'status':
        st = kit_status(cfg, a.folder)
        print(json.dumps({'state': st['state'], 'text': st['text'], 'diff': st['diff']}))
        return 0 if st['state'] == 'same' else 3
    if a.cmd == 'rebind':
        r = rebind_project(cfg, a.folder)
        print(json.dumps({k: r.get(k) for k in ('verdict', 'problems', 'diff')}))
        return 0 if r['ok'] else 3
    r = create_project(cfg, a.folder, a.id, a.name, a.module)
    print(json.dumps({k: v for k, v in r.items() if k != 'identity'}))
    return 0 if r['ok'] else 3


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
