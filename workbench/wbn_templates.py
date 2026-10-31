"""wbn_templates - project templates from the kit's existing examples (Workbench 0.30 developer workflow).

Each template states its REQUIREMENTS (the services / tables / platform the example itself declares, checked against the kit's
HOST_INFO.json) and offers only capabilities the example uses. A project is a plain folder, usable without the Workbench:
mod.toml, the sources, README.md with the exact standalone commands, and wbn-project.json (template, kit identity, parameters).

  tune-data        DATA mod (no code): [bmashup.tune] values from the authoritative catalogue          (kit docs\\TUNING_CATALOGUE.json)
  traffic-density  native plugin: the kit's sdk\\examples\\traffic source, one density 0.0 .. 2.0
                   (docs\\services\\TRAFFIC.md: set_density 0.0 <= d <= 2.0, runtime-validated 0 / 0.5 / 1 / 2)
  events-observer  native plugin: the kit's sdk\\examples\\events-observer source unchanged (observe only)
  events-v2        DATA template: [bmashup.extra_events] version 2 from sdk\\examples\\events-v2 (needs YOUR track files;
                   a starting point to edit, never a mod to enable unchanged - kit release acceptance note)

Nothing is overwritten: a project appears in one rename (complete or not at all) in a new or empty folder. No game data or
extracted game files are ever copied into a project.

    py -3 -B wbn_templates.py list
    py -3 -B wbn_templates.py new TEMPLATE FOLDER --id ID --name NAME [--kit KIT] [--module M] [--density D] [--set "Row = v" ...]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wb_project  # noqa: E402
import wbn_catalogue  # noqa: E402
import wbn_rules  # noqa: E402

SCHEMA = 'bm-workbench-next-project/1'
MARKER = 'wbn-project.json'
MODULE_RE = wb_project.MODULE_RE

TEMPLATES = {
    'tune-data': {
        'title': 'Tuning data mod (no code)', 'kind': 'data', 'source': r'docs\TUNING_CATALOGUE.json',
        'requires': [], 'tables': {'tune': 1}, 'platform': '>=0.1.9',
        'capabilities': ['[bmashup.tune] set: catalogue rows inside the host limits',
                         '[bmashup.tune] sliders (version 3): only rows with a verified range get a slider in the editor'],
        'needs_build': False},
    'traffic-density': {
        'title': 'Traffic density plugin (native code)', 'kind': 'plugin', 'source': r'sdk\examples\traffic',
        'files': ['bm_gp_traffic.c'], 'requires': ['bmashup.traffic>=1'], 'platform': '>=0.1.4',
        'capabilities': ['bmashup.traffic set_density 0.0 .. 2.0 (one owner; a second density mod gets CONFLICT)'],
        'param': {'name': 'density', 'define': 'GP_DENSITY', 'lo': 0.0, 'hi': 2.0, 'default': 0.5,
                  'source': r'docs\services\TRAFFIC.md (0.0 <= d <= 2.0, BM_TRAFFIC_DENSITY_MAX)'},
        'needs_build': True},
    'events-observer': {
        'title': 'Gameplay events observer plugin (native code)', 'kind': 'plugin', 'source': r'sdk\examples\events-observer',
        'files': ['bm_sdk_events_observer.c'], 'requires': ['bmashup.events>=5'], 'platform': '>=0.1',
        'capabilities': ['bmashup.events LOAD_DONE / RACE_EXIT (2), TAKEDOWN / WRECK (3), BOOST_AWARD (4): observe only'],
        'needs_build': True},
    'events-v2': {
        'title': 'World Tour events with names and help (data template)', 'kind': 'data', 'source': r'sdk\examples\events-v2',
        'requires': ['bmashup.tracks>=1', 'bmashup.extra_events>=2'], 'platform': '>=0.1.1',
        'capabilities': ['[bmashup.tracks] add / names / locations', '[bmashup.extra_events] v2 add / stage / names / help'],
        'needs_build': False, 'starting_point': True},
}


def sha_text(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def sha_file(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


NO_HOST = ("needs a built host: this is checked against the HOST_INFO.json of the host you build - run Build Mashup first "
           "(nothing is assumed meanwhile)")


def host_info(kit):
    """the kit's HOST_INFO.json (written by the build, build/host_info.py), or None: no kit, no host built yet, or unreadable"""
    if not kit:
        return None
    try:
        return json.load(open(os.path.join(kit, 'HOST_INFO.json'), encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None


def requirement_problems(tpl, info):
    """the template's own requirements vs the host the kit describes -> problems"""
    if not info:
        return []                      # host-independent: with no host built yet the requirements cannot be checked (reported as NO_HOST)
    out = []
    for r in tpl['requires']:
        name, want = r.split('>=')
        have = info['services'].get(name)
        if have is None and name.startswith('bmashup.') and name[8:] in info.get('tables', {}):
            have = info['tables'][name[8:]]['version']
        if have is None or have < int(want):
            out.append('the kit\'s host (%s, platform %s) does not offer %s' % (info.get('host_name'), info.get('platform'), r))
    for t, v in (tpl.get('tables') or {}).items():
        if (info.get('tables', {}).get(t) or {}).get('version', 0) < v:
            out.append('the kit\'s host does not read [bmashup.%s] version %d' % (t, v))
    return out


def list_templates(kit):
    info = host_info(kit)
    out = []
    for k, t in TEMPLATES.items():
        src = os.path.join(kit or '', t['source'])
        out.append({'id': k, 'title': t['title'], 'kind': t['kind'], 'requires': t['requires'], 'platform': t['platform'],
                    'capabilities': t['capabilities'], 'needs_build': t['needs_build'],
                    'host_checked': bool(info), 'notes': ([] if info else [NO_HOST]),
                    'available': os.path.exists(src) and not requirement_problems(t, info),
                    'problems': ([] if os.path.exists(src) else ['kit file missing: %s' % t['source']]) +
                    requirement_problems(t, info)})
    return out


# ------------------------------------------------------------------------------------------------ file texts
def tune_mod_toml(mod_id, name, entries, version):
    body = ''.join('    "%s",\n' % e for e in entries)
    return ('# Burnout Mashup tuning data mod (no code, no game files). Made from the Workbench template "tune-data".\n'
            '# Every key is a row of the kit\'s docs\\TUNING_CATALOGUE.md ("Group | Name"). The host checks each value at start\n'
            '# (exit 93 with the reason on a refusal). Edit with the Workbench tuning editor or by hand.\n'
            'id = "%s"\nname = "%s"\nversion = "1.0.0"\ndescription = "Tuning values (data only)."\n\n'
            '[bmashup]\nplatform = ">=0.1.9"\n\n'
            '# version 1: set values; 2: + AI rows and negative values; 3: + sliders on the MODS page\n'
            '[bmashup.tune]\nversion = %d\nset = [\n%s]\n') % (mod_id, name, version, body)


def readme(tpl_id, tpl, mod_id, name, extra=''):
    t = ['# %s (%s)\n' % (name, mod_id),
         'Made from the Workbench template **%s** (%s). Source in the kit: `%s`.\n' % (tpl_id, tpl['title'], tpl['source']),
         'Requirements: platform `%s`%s.\n' % (tpl['platform'], (', ' + ', '.join('`%s`' % r for r in tpl['requires']))
                                               if tpl['requires'] else ''),
         'Capabilities used: ' + '; '.join(tpl['capabilities']) + '.\n',
         '## Without the Workbench\n',
         'Validate with the kit\'s own tool (your own game data, read only):\n',
         '```\npy -3 -B <kit>\\tools\\bmpack\\bmpack.py validate "<this folder>" --game-data "<game data>" --cc <clang.exe> '
         '--cache "<new cache folder>" --json\n```\n',
         'If bmpack stops with "bm_tune_catalog_shadow.inc file not found" (kit 0.7.0 as first packaged), use a kit build '
         'that ships those host-reader files, or add `--host-readers "<a complete host-readers folder>"`.\n']
    if tpl['kind'] == 'plugin':
        t += ['Build (pinned toolchain, kit `sdk\\BUILD.md`):\n',
              '```\ncmake -S "<this folder>" -B "<new build folder>" -G Ninja -DCMAKE_MAKE_PROGRAM=<ninja.exe> '
              '-DCMAKE_TOOLCHAIN_FILE=<kit>\\sdk\\cmake\\llvm-mingw-x86_64.cmake -DLLVM_MINGW_ROOT=<llvm-mingw> '
              '-DBMSDK_DIR=<kit>\\sdk\ncmake --build "<new build folder>"\n```\n',
              'The drop-in mod is `<build>\\out\\%s\\`. Native code runs with full rights: the game asks the player to approve the '
              'module\'s exact sha256 on its MODS page; no tool approves it for you.\n' % mod_id]
    if tpl.get('starting_point'):
        t += ['**Starting point, not a finished mod**: it names a track without files. Put YOUR OWN track build into '
              '`files\\Tracks\\...` (README of the kit example) before enabling it; never copy retail game files into a shared '
              'project.\n']
    return '\n'.join(t) + extra


def plugin_cmake(module, mod_id, src, defines):
    d = (' DEFINES ' + ' '.join(defines)) if defines else ''
    return ('# Standalone build of %(id)s (Workbench template). Needs the kit SDK: -DBMSDK_DIR=<kit>\\sdk\n'
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(%(m)s LANGUAGES C)\n'
            'set(BMSDK_DIR "" CACHE PATH "the mod kit\'s sdk folder")\n'
            'if(NOT EXISTS "${BMSDK_DIR}/cmake/bmsdk.cmake")\n'
            '    message(FATAL_ERROR "set -DBMSDK_DIR=<kit>/sdk (the folder holding cmake/bmsdk.cmake)")\n'
            'endif()\n'
            'include("${BMSDK_DIR}/cmake/bmsdk.cmake")\n'
            'bmsdk_add_plugin(%(m)s SOURCES ${CMAKE_CURRENT_LIST_DIR}/%(src)s%(d)s\n'
            '    MOD_DIR %(id)s MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)\n') % {'id': mod_id, 'm': module, 'src': src, 'd': d}


def plugin_mod_toml(tpl, mod_id, name, module, desc):
    return ('# Native plugin made from the Workbench template (kit %s). Runs with full rights: the player approves the\n'
            '# module\'s exact sha256 on the game\'s MODS page; nothing approves it automatically.\n'
            'id = "%s"\nname = "%s"\nversion = "0.1.0"\ndescription = "%s"\n\n'
            '[bmashup]\nplatform = "%s"\nrequires = [%s]\n\n'
            '[plugin]\napi = 1\nwindows = "%s.asi"\n# Only Windows x64 is built and tested.\n') % (
        tpl['source'], mod_id, name, desc, tpl['platform'], ', '.join('"%s"' % r for r in tpl['requires']), module)


# ------------------------------------------------------------------------------------------------ create
def _folder_problems(folder):
    if not folder or not os.path.isabs(folder):
        return ['the project folder must be a full path: %r' % folder]
    if any(p == '..' for p in re.split(r'[\\/]+', folder)):
        return ['".." is not allowed in the project folder']
    if not os.path.isdir(os.path.dirname(os.path.abspath(folder))):
        return ['the parent folder does not exist: %s' % os.path.dirname(folder)]
    if os.path.isfile(folder) or (os.path.isdir(folder) and os.listdir(folder)):
        return ['the folder exists and is not empty (never overwritten): %s' % folder]
    return []


def create(kit, template, folder, mod_id, name, module=None, density=None, entries=None, cat=None):
    """-> {'ok', 'verdict', 'project', 'problems', 'files'}"""
    tpl = TEMPLATES.get(template)
    res = {'kind': 'new-project', 'template': template, 'ok': False, 'project': folder, 'problems': []}
    if not tpl:
        res.update(verdict='NOT CREATED', problems=['unknown template %r (list: %s)' % (template, ', '.join(TEMPLATES))])
        return res
    bad = [x for x in (wb_project.check_mod_id(mod_id), wb_project.check_name(name)) if x] + _folder_problems(folder)
    info = host_info(kit)
    bad += requirement_problems(tpl, info)
    if not info:
        res['warnings'] = [NO_HOST]           # the project is made (a plain folder); its compatibility is checked once a host is built
    src = os.path.join(kit or '', tpl['source'])
    if not os.path.exists(src):
        bad.append('kit file missing: %s (is %s the mod kit folder?)' % (tpl['source'], kit))
    files, params = {}, {}
    if tpl['kind'] == 'plugin':
        module = module or ''
        why = wb_project.check_module(module)
        if why:
            bad.append(why)
    if not bad and template == 'tune-data':
        cat = cat or wbn_catalogue.load()
        if not cat:
            bad.append('no editor catalogue (data\\EDITOR_CATALOGUE.json)')
        else:
            bad += wbn_catalogue.check_against_kit(cat, kit)
            entries = list(entries or [])
            ver = 1
            idx = wbn_catalogue.index(cat)
            for e in entries:
                row = idx.get((e.rsplit('=', 1)[0]).strip()) if '=' in e else None
                if row and row['family'] == 'ai' or (('=' in e) and e.rsplit('=', 1)[1].strip().startswith('-')):
                    ver = 2
            text = tune_mod_toml(mod_id, name, entries, ver)
            r = wbn_rules.validate_text(text, cat)
            bad += [wbn_rules.format_problem(p) for p in r['problems'] if p['sev'] == 'error']
            files['mod.toml'] = text
    elif not bad and tpl['kind'] == 'plugin':
        defines = []
        if tpl.get('param'):
            pr = tpl['param']
            d = pr['default'] if density is None else density
            try:
                d = float(d)
            except (TypeError, ValueError):
                d = None
            if d is None or not pr['lo'] <= d <= pr['hi']:
                bad.append('%s must be a number in %g .. %g (%s)' % (pr['name'], pr['lo'], pr['hi'], pr['source']))
            else:
                defines.append('%s=%s' % (pr['define'], ('%.3f' % d).rstrip('0').rstrip('.') if d != int(d) else '%.1f' % d))
                params[pr['name']] = d
        for f in tpl['files']:
            files[f] = open(os.path.join(src, f), encoding='utf-8', newline='').read()
        files['CMakeLists.txt'] = plugin_cmake(module, mod_id, tpl['files'][0], defines)
        desc = ('Traffic density %s from the next traffic set-up (bmashup.traffic).' % params.get('density')
                if template == 'traffic-density' else 'Logs player 1\'s takedowns, wrecks and boost awards at each race exit.')
        files['mod.toml'] = plugin_mod_toml(tpl, mod_id, name, module, desc)
    elif not bad and template == 'events-v2':
        t = open(os.path.join(src, 'mod.toml'), encoding='utf-8', newline='').read()
        t = re.sub(r'^id = "[^"]*"', 'id = "%s"' % mod_id, t, count=1, flags=re.M)
        t = re.sub(r'^name = "[^"]*"', 'name = "%s"' % name, t, count=1, flags=re.M)
        t = re.sub(r'^version = "[^"]*"', 'version = "0.1.0"', t, count=1, flags=re.M)
        files['mod.toml'] = t
    res['problems'] = bad
    if bad:
        res['verdict'] = 'NOT CREATED'
        return res
    files['README.md'] = readme(template, tpl, mod_id, name)
    folder = os.path.abspath(folder)
    marker = {'schema': SCHEMA, 'template': template, 'title': tpl['title'], 'kind': tpl['kind'], 'mod_id': mod_id, 'name': name,
              'module': module if tpl['kind'] == 'plugin' else None, 'params': params, 'requires': tpl['requires'],
              'platform': tpl['platform'], 'capabilities': tpl['capabilities'],
              'created': datetime.datetime.now().isoformat(timespec='seconds'),
              'kit': {'path': kit, 'host': (info or {}).get('identity'), 'host_info_sha256': sha_file(os.path.join(kit, 'HOST_INFO.json'))
                      if info else None},
              'template_sources': {f: sha_file(os.path.join(src, f)) for f in tpl.get('files', [])},
              'created_files': {f: sha_text(t) for f, t in files.items()}}
    tmp = os.path.join(os.path.dirname(folder), '.%s.wbn_new_%s' % (os.path.basename(folder),
                                                                     datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    os.makedirs(tmp)
    try:
        for f, t in files.items():
            with open(os.path.join(tmp, f), 'w', encoding='utf-8', newline='') as fh:
                fh.write(t if '\r\n' in t else t)
        with open(os.path.join(tmp, MARKER), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(marker, fh, indent=1)
        if os.path.isdir(folder):
            if os.listdir(folder):
                raise FileExistsError(folder)
            os.rmdir(folder)
        os.rename(tmp, folder)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        res.update(verdict='NOT CREATED', problems=['could not create the project: %r' % e])
        return res
    res.update(ok=True, verdict='CREATED', project=folder, files=sorted(list(files) + [MARKER]))
    return res


def read_marker(project):
    try:
        d = json.load(open(os.path.join(project, MARKER), encoding='utf-8'))
        return d if d.get('schema') == SCHEMA else None
    except (OSError, ValueError):
        return None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['list', 'new'])
    ap.add_argument('template', nargs='?')
    ap.add_argument('folder', nargs='?')
    ap.add_argument('--kit', required=True)
    ap.add_argument('--id', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--module')
    ap.add_argument('--density')
    ap.add_argument('--set', action='append', default=[])
    a = ap.parse_args(argv)
    if a.cmd == 'list':
        print(json.dumps(list_templates(a.kit), indent=1))
        return 0
    r = create(a.kit, a.template, a.folder, a.id, a.name, a.module, a.density, a.set)
    print(json.dumps(r))
    return 0 if r['ok'] else 3


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
