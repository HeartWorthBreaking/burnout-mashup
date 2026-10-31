"""wb_stage - Workbench v0.3-v0.6: Build -> Validate -> Stage for verified kit example mods (gp\\workbench, 2026-10-28).

Recipes (RECIPES below): p43-coupe-photo (v0.2, fetex texture pack) and sdk-host-info (v0.3, the SDK's native plugin example (h),
built with the SDK's documented CMake commands). Only verified recipes run; a recipe step is a fixed argument list whose only
placeholders are the configured tools ({python} {fetex} {bmpack} {cmake} {ninja} {llvm_mingw}), the kit's own files and the
attempt's own folders ({src} {build} {toolchain_file}). A project's own build script is never run unless it is byte-identical
to the kit's reviewed one (RECIPES[..]['pinned']). Native code is never approved: STAGE.json records the module's sha256 for the
player's own approval. The source project is never written: the build runs in a fresh COPY
under <destination>\\.wb_stage\\work\\<time>\\<folder>. Only when every step and every validation passed is the result moved into
<destination>\\<folder>; an earlier staged package is first moved to <destination>\\.wb_stage\\previous\\<time>\\<folder> (nothing is
deleted). A failed or cancelled attempt leaves <destination>\\<folder> exactly as it was; its work folder stays for diagnosis.
No game launch, no install into the game, no upload.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import tomllib

import wb_core as core
import wb_kit
import wb_project as proj

# ---------------------------------------------------------------- verified recipes
# p43-coupe-photo: kit README examples\authored (row bm-coupes): "fetex.py pack photo_spec.json art\photo.txd"; the launched
# p4.3 set runtime_data\modsets\gp_p43_examples\p43-coupe-photo = the project files + art\photo.txd built in place.
RECIPES = {
    'p43-coupe-photo': {
        'title': 'BM Coupe garage photo (kit example: authored front-end texture pack, fetex)',
        'example': r'examples\authored\bm-coupes\p43-coupe-photo',     # relative to the kit folder
        'mod_id': 'bmashup.p43-coupe-photo',
        'folder': 'p43-coupe-photo',
        'require': ['mod.toml', 'photo_spec.json'],
        'mkdirs': ['art'],
        'build': [['{python}', '-B', '{fetex}', 'pack', 'photo_spec.json', r'art\photo.txd']],
        'validate': [['{python}', '-B', '{fetex}', 'validate', r'art\photo.txd', '--class', 'frontend']],
        'bmpack_validate': True,
        'outputs': ['art/photo.txd'],
        'reference': {'art/photo.txd': 'a91527d9bed1'},   # sha256 prefix of the launched p4.3 file (gp_p43_examples)
        'reference_label': 'the launched p4.3 file',
    },
    # sdk-host-info: kit sdk\BUILD.md "By hand (CMake)" with "One example alone: -S examples/<name>" (+ -DCMAKE_BUILD_TYPE=Release
    # as build.ps1 passes it). Example (h) changes nothing in the game (it logs the host's version, build and services); no game
    # data is read at build or validation time. The build runs in <attempt>\src\sdk = copies of the kit's sdk\cmake and
    # sdk\include plus the project at sdk\examples\host-info (the layout its CMakeLists.txt includes ../../cmake/bmsdk.cmake from).
    # Verified 2026-10-28: llvm-mingw 20260922 + CMake 4.4.4 + Ninja 1.13.2 give the kit's EXPECTED_BUILD_SHA256.txt bytes.
    'sdk-host-info': {
        'kind': 'sdk-plugin',
        'title': 'SDK example (h) host-info: native plugin module (.asi) built with CMake + Ninja + llvm-mingw; logs host '
                 'info only, changes nothing',
        'example': r'sdk\examples\host-info',
        'mod_id': 'bmashup-sdk.host-info',
        'folder': 'bmashup-sdk-host-info',                  # = MOD_DIR in its CMakeLists.txt = the staged drop-in mod folder
        'require': ['mod.toml', 'CMakeLists.txt', 'bm_sdk_host_info.c'],
        # the project's build script must be the kit's reviewed one (sha256 of sdk\examples\host-info\CMakeLists.txt, kit 0.6.0)
        'pinned': {'CMakeLists.txt': '22804948a908a55d47d708f1c5a95d48cf0a3a095d50b145fd18d93ed7865cf8'},
        'needs': ['cc', 'cmake', 'ninja'],
        'sdk_copy': [r'sdk\cmake', r'sdk\include'],          # from the kit, into <attempt>\src\sdk
        'build': [['{cmake}', '-S', '{src}', '-B', '{build}', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                   '-DCMAKE_MAKE_PROGRAM={ninja}', '-DCMAKE_TOOLCHAIN_FILE={toolchain_file}', '-DLLVM_MINGW_ROOT={llvm_mingw}'],
                  ['{cmake}', '--build', '{build}']],
        'validate': [],                                      # in-process checks: check_plugin_package()
        'bmpack_validate': False,                            # bmpack validate needs game data; a code-only mod has no data to check
        'module': 'bm_sdk_host_info.asi',
        'exports': ['takedawn_plugin_api_version', 'takedawn_plugin_init'],    # takedawn_plugin.h: exported by every plugin
        'outputs': ['bm_sdk_host_info.asi', 'mod.toml'],
        'expected_list': r'sdk\EXPECTED_BUILD_SHA256.txt',  # the kit's reference build (llvm-mingw 20260922)
        'reference_label': "the kit's reference build (sdk\\EXPECTED_BUILD_SHA256.txt)",
    },
    # plugin-project (v0.5): a project made by "New plugin project" (wb_project.py). Identity (mod id, module, folder) comes
    # from the project's workbench-project.json; the build script is the Workbench's own (wb_project.project_cmake), written
    # into the build copy; the steps are the same SDK by-hand CMake steps as sdk-host-info. No reference bytes exist.
    'plugin-project': {
        'kind': 'sdk-plugin',
        'project': True,
        'title': 'a new native plugin project (New plugin project): its declared identity, the Workbench\'s own build steps',
        'example': None, 'mod_id': None, 'folder': None, 'module': None, 'outputs': None,
        'require': ['mod.toml', proj.MARKER],
        'needs': ['cc', 'cmake', 'ninja'],
        'sdk_copy': [r'sdk\cmake', r'sdk\include'],
        'build': [['{cmake}', '-S', '{src}', '-B', '{build}', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                   '-DCMAKE_MAKE_PROGRAM={ninja}', '-DCMAKE_TOOLCHAIN_FILE={toolchain_file}', '-DLLVM_MINGW_ROOT={llvm_mingw}'],
                  ['{cmake}', '--build', '{build}']],
        'validate': [],
        'bmpack_validate': False,
        'exports': ['takedawn_plugin_api_version', 'takedawn_plugin_init'],
        'expected_list': None,
        'reference_label': 'no reference bytes (a new project)',
    },
    # v0.12 cars (wb_car.py): the kit's carimport 0.1.1 + vehtool 0.1.2 with fixed arguments (tools\carimport\README.md s2:
    # "carimport.py validate car.toml --game-data ..." / "package car.toml <set> --game-data ..."; vehtool README "validate
    # MODDIR --game-data ..."), run in <attempt>\src = a copy of the checked inputs only, then bmpack validate of the package.
    'carimport-coupe': {
        'kind': 'car',
        'title': 'kit authored example carimport coupe (COMPCIC1 on donor COMPCAR1): carimport validate + package, vehtool '
                 'validate, bmpack validate; reads the donor from your game data (package LOCAL ONLY)',
        'example': r'examples\authored\carimport\coupe',
        'mod_id': 'bmashup.carimp-coupe',
        'folder': 'carimp-coupe',                                   # = what carimport package writes (mod id's last part)
        'require': ['car.toml'],
        'reference_list': r'tools\carimport\tests\REGRESSION_SHA256.json',     # packages.carimp-coupe (the kit's own bytes)
        'reference_label': "the kit's carimport regression bytes (tools\\carimport\\tests\\REGRESSION_SHA256.json carimp-coupe)",
        'car_validate': ['{python}', '-B', '{carimport}', 'validate', 'car.toml', '--game-data', '{game_data}', '--json'],
        'car_package': ['{python}', '-B', '{carimport}', 'package', 'car.toml', '{out}', '--game-data', '{game_data}', '--json'],
        'car_check': ['{python}', '-B', '{vehtool}', 'validate', '{pkg}', '--game-data', '{game_data}'],
        'bmpack_validate': True,
    },
    'car-project': {
        'kind': 'car',
        'project': True,
        'title': 'a new car project (New car project): its declared identity, the same fixed carimport / vehtool / bmpack steps',
        'example': None, 'mod_id': None, 'folder': None,
        'require': ['car.toml', 'workbench-car.json'],
        'reference_list': None,
        'reference_label': 'no reference bytes (a new car project)',
        'car_validate': ['{python}', '-B', '{carimport}', 'validate', 'car.toml', '--game-data', '{game_data}', '--json'],
        'car_package': ['{python}', '-B', '{carimport}', 'package', 'car.toml', '{out}', '--game-data', '{game_data}', '--json'],
        'car_check': ['{python}', '-B', '{vehtool}', 'validate', '{pkg}', '--game-data', '{game_data}'],
        'bmpack_validate': True,
    },
    # v0.13 tracks (wb_track.py): the kit's trackbuild 0.2.1 with fixed arguments (tools\trackbuild\README.md "Quick start":
    # "tb.py build work\src test_loop.track.json work\build --game-data ...", "validate work\build", "package work\build
    # <toml> work\set"), run in <attempt>\src = a copy of the checked inputs only, then bmpack validate of the mod folder.
    'trackbuild-testloop': {
        'kind': 'track',
        'title': 'kit authored example trackbuild BM Test Loop (EU_T1_V1, tb.py gen-testloop + examples\\test_loop_package.toml): '
                 'tb.py build + validate + package, bmpack validate; DONOR parts from your game data (package LOCAL ONLY)',
        'example': None,                                            # generated by the kit (wb_track.py example FOLDER)
        'mod_id': 'bmashup.trackbuild.test-loop',
        'folder': 'bm-test-loop',                                   # = the example toml's folder
        'require': ['package.toml'],
        'reference_list': r'tools\trackbuild\tests\REFERENCE_0_2_1.json', 'reference_set': 'test_loop',
        'reference_label': "the kit's trackbuild reference bytes (tools\\trackbuild\\tests\\REFERENCE_0_2_1.json test_loop)",
        'track_build': ['{python}', '-B', '{trackbuild}', 'build', '{src}', '{desc}', '{tbuild}', '--game-data', '{game_data}'],
        'track_validate': ['{python}', '-B', '{trackbuild}', 'validate', '{tbuild}'],
        'track_package': ['{python}', '-B', '{trackbuild}', 'package', '{tbuild}', 'package.toml', '{out}'],
        'bmpack_validate': True,
    },
    'track-project': {
        'kind': 'track',
        'project': True,
        'title': 'a new track project (New track project): its declared identity, the same fixed trackbuild / bmpack steps',
        'example': None, 'mod_id': None, 'folder': None,
        'require': ['package.toml', 'workbench-track.json'],
        'reference_list': None,
        'reference_label': 'no reference bytes (a new track project)',
        'track_build': ['{python}', '-B', '{trackbuild}', 'build', '{src}', '{desc}', '{tbuild}', '--game-data', '{game_data}'],
        'track_validate': ['{python}', '-B', '{trackbuild}', 'validate', '{tbuild}'],
        'track_package': ['{python}', '-B', '{trackbuild}', 'package', '{tbuild}', 'package.toml', '{out}'],
        'bmpack_validate': True,
    },
}


# ---------------------------------------------------------------- v0.11: import an existing, finished mod folder
IMPORT_RECIPE = 'import'                     # StageOp(IMPORT_RECIPE, SOURCE_FOLDER, DEST): copied as is, never built
IMPORT_PLUGIN, IMPORT_DATA = 'imported-plugin', 'imported-data'
IMPORT_MAX_FILES, IMPORT_MAX_BYTES = 5000, 2 << 30
REPARSE = 0x400                              # FILE_ATTRIBUTE_REPARSE_POINT (junctions, symlinks, mount points, cloud files)
RUNNABLE_EXT = ('.exe', '.dll', '.asi', '.bat', '.cmd', '.ps1', '.py', '.pyw', '.vbs', '.js', '.sh', '.com', '.scr', '.msi')
PLUGIN_EXPORTS = ['takedawn_plugin_api_version', 'takedawn_plugin_init']   # takedawn_plugin.h (as the SDK recipes check)


def provenance_text(rec):
    """one line: how the staged bytes came to be (a reproducible Workbench build or an import copied as is)"""
    rec = rec or {}
    if rec.get('recipe') == IMPORT_RECIPE:
        p = rec.get('provenance') or {}
        return ('IMPORTED as is from %s at %s (not built by the Workbench, not reproducible from source; exact source file '
                'hashes recorded)' % (p.get('source'), p.get('time')))
    if rec.get('recipe') == 'test-fixture':
        return 'TEST FIXTURE record (not built by the Workbench)'
    return 'BUILT by the Workbench recipe %s from %s (reproducible: the build steps and tool identities are recorded)' % (
        rec.get('recipe'), rec.get('project'))


def _walk_source(src):
    """every entry under src without following links -> (files {rel: (abs, size)}, problems). Read only."""
    files, bad = {}, []
    base = _real(src)

    def attrs(st):
        return getattr(st, 'st_file_attributes', 0) or 0
    try:
        st = os.lstat(src)
    except OSError as e:
        return {}, ['source unreadable: %s' % e]
    if os.path.islink(src) or attrs(st) & REPARSE:
        return {}, ['the source folder is a link / reparse point (junction, symlink, mount point): refused: %s' % src]
    stack = [src]
    total = 0
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError as e:
            bad.append('unreadable folder %s: %s' % (d, e))
            continue
        for e in it:
            rel = os.path.relpath(e.path, src).replace('\\', '/')
            try:
                est = e.stat(follow_symlinks=False)
            except OSError as x:
                bad.append('unreadable %s: %s' % (rel, x))
                continue
            if e.is_symlink() or attrs(est) & REPARSE:
                bad.append('link / reparse point refused (never followed): %s' % rel)
                continue
            if not _inside(_real(e.path), base) or rel.startswith('../') or ':' in rel:
                bad.append('path escapes the source folder: %s' % rel)
                continue
            if e.is_dir(follow_symlinks=False):
                if e.name.lower() == '.wb_stage':
                    bad.append('the source holds a Workbench staging folder (.wb_stage): import a mod folder, not a staging '
                               'folder: %s' % rel)
                    continue
                stack.append(e.path)
            elif e.is_file(follow_symlinks=False):
                files[rel] = (e.path, est.st_size)
                total += est.st_size
            else:
                bad.append('not a regular file (device / pipe / other): %s' % rel)
    if len(files) > IMPORT_MAX_FILES:
        bad.append('more than %d files (%d): not a single mod folder' % (IMPORT_MAX_FILES, len(files)))
    if total > IMPORT_MAX_BYTES:
        bad.append('more than %d bytes (%d)' % (IMPORT_MAX_BYTES, total))
    return dict(sorted(files.items())), bad


def import_check(cfg, src, dest):
    """what Import would copy and why it would refuse -> info {problems, mod_id, kind, folder, module, files, notes, ...}.
    READ ONLY: nothing is executed, built, written or approved. The manifest / host-requirement / native-module checks are the
    ones the recipes and profiles already use (wb_kit.requirements + compat_problems, pe_info + the SDK plugin exports)."""
    info = {'kind': 'import-check', 'source': os.path.abspath(src) if src else src, 'dest': os.path.abspath(dest) if dest else dest,
            'problems': [], 'notes': [], 'checks': []}
    bad = info['problems']

    def c(name, ok, detail):
        info['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
        if not ok:
            bad.append('%s: %s' % (name, detail))
    if not src or not os.path.isdir(src):
        low = (src or '').lower()
        bad.append('source folder not found: %s%s' % (src, ' (archives: deferred - unpack it into a new folder yourself and '
                                                           'import that folder)' if low.endswith(('.zip', '.7z', '.rar')) else ''))
        return info
    src = info['source']
    if not dest:
        bad.append('no staging destination chosen')
        return info
    rs, rd = _real(src), _real(dest)
    if _inside(rd, rs) or _inside(rs, rd):
        bad.append('unsafe overlap: the staging folder %s and the source %s contain one another (the source is never written; '
                   'import into a separate folder)' % (dest, src))
    bad += check_destination(cfg, src, dest)
    files, wbad = _walk_source(src)
    bad += wbad
    info['files'] = {k: v[1] for k, v in files.items()}
    mt = os.path.join(src, 'mod.toml')
    if 'mod.toml' not in files:
        bad.append('no mod.toml at the top of %s: not a mod folder' % src)
        return info
    try:
        t = tomllib.loads(open(mt, encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        c('mod.toml parses', False, str(e))
        return info
    c('mod.toml parses', True, 'ok')
    mid = t.get('id')
    c('mod.toml id (valid mod id)', isinstance(mid, str) and bool(MOD_ID_RE.match(mid)), mid)
    c('mod.toml version', isinstance(t.get('version'), str) and bool(t.get('version').strip()), t.get('version'))
    req, rbad = wb_kit.requirements(mt)
    c('mod.toml requirements ([bmashup] platform / requires)', not rbad, '; '.join(rbad) or 'readable')
    info.update(mod_id=mid if isinstance(mid, str) else None, version=t.get('version'), name=t.get('name'), requirements=req,
                folder=mid if isinstance(mid, str) and MOD_ID_RE.match(mid) else None)
    plugin = isinstance(t.get('plugin'), dict)
    info['package_kind'] = IMPORT_PLUGIN if plugin else IMPORT_DATA
    if plugin:
        pl = t['plugin']
        c('mod.toml [plugin] api = 1', pl.get('api') == 1, pl.get('api'))
        w = pl.get('windows')
        okname = isinstance(w, str) and w and '/' not in w and '\\' not in w and '..' not in w and ':' not in w
        c('mod.toml [plugin] windows = a module file at the top of the folder', okname and w in files, w)
        if okname and w in files:
            info['module'] = w
            try:
                pe = pe_info(files[w][0])
                info['pe'] = pe
                c('native module: PE32+ x86-64 DLL', pe['machine'] == '0x8664' and pe['pe32plus'] and pe['dll'],
                  '%s pe32plus=%s dll=%s' % (pe['machine'], pe['pe32plus'], pe['dll']))
                miss = [x for x in PLUGIN_EXPORTS if x not in pe['exports']]
                c('native module: plugin exports', not miss, 'missing %s' % miss if miss else pe['exports'])
                info['notes'].append('link time stamp %s (%s)' % (pe['time_stamp'], 'reproducible-style 0' if pe['time_stamp'] == 0
                                                                     else 'not 0: recorded, not required for an import'))
            except Exception as e:                                 # noqa: BLE001 - malformed module
                c('native module: PE32+ x86-64 DLL', False, 'unreadable PE: %r' % e)
    run = [k for k in files if k.lower().endswith(RUNNABLE_EXT) and k != info.get('module')]
    if run:
        info['notes'].append('holds script / executable files that the import copies but NEVER runs (and the host does not load '
                             'them as plugins): %s' % ', '.join(run[:10]))
    k = wb_kit.kit_identity(cfg.get('kit')) if cfg.get('kit') else None
    if not k:
        bad.append('kit: ' + core.check_value('kit', ''))
    elif req and not rbad:
        cp = wb_kit.compat_problems(req, k['platform'], k['services'], plugin=plugin, tables=k.get('tables'))
        c('host requirements vs the kit\'s reference host (platform %s, offered services / tables)' % k['platform'], not cp,
          '; '.join(cp) or 'met')
    bad += core.bmpack_prereqs(cfg, need_game=True)
    if info.get('folder'):
        bad += import_collisions(dest, info['folder'], mid, src)
    return info


def import_collisions(dest, folder, mod_id, src):
    """<dest>\\<mod id> may only be replaced by a new import of the same mod id from the same source folder; no other staged
    package in <dest> may have this mod id (duplicate ids)"""
    out = []
    pk = os.path.join(dest, '.wb_stage', 'packages')
    for n in sorted(os.listdir(pk)) if os.path.isdir(pk) else []:
        try:
            m = json.load(open(os.path.join(pk, n), encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if m.get('mod_id') == mod_id and os.path.normcase(m.get('folder') or '') != os.path.normcase(folder) and \
                os.path.exists(m.get('package') or ''):
            out.append('duplicate mod id %s: %s already holds it (staged folder %s, %s); a staging folder holds each mod id once'
                       % (mod_id, dest, m.get('folder'), provenance_text(m)))
    final = os.path.join(dest, folder)
    if os.path.exists(final):
        m = package_record(dest, folder)
        if not m:
            out.append('%s exists but the Workbench has no record of staging it: not replaced' % final)
        elif m.get('mod_id') != mod_id:
            out.append('%s holds a different mod (%s): not replaced' % (final, m.get('mod_id')))
        elif m.get('recipe') != IMPORT_RECIPE:
            out.append('%s is a reproducible Workbench build (%s): an import never replaces it (stage into another folder)'
                       % (final, m.get('recipe')))
        elif os.path.normcase(os.path.abspath((m.get('provenance') or {}).get('source') or '')) != os.path.normcase(os.path.abspath(src)):
            out.append('%s was imported from another source (%s) with the same mod id %s: not replaced'
                       % (final, (m.get('provenance') or {}).get('source'), mod_id))
    return out


def recipe(rid, project=None):
    """the recipe for one project: kit recipes as they are; plugin-project filled from the project's declared identity
    (mod id = staged folder, <module>.asi + mod.toml = outputs); None values when the identity is unreadable"""
    if rid == IMPORT_RECIPE:                                    # v0.11
        return {'title': 'import an existing mod folder (copied as is)', 'folder': None, 'mod_id': None}
    rec = dict(RECIPES[rid])
    if rec.get('project') and rec.get('kind') == 'track':                # v0.13: identity from workbench-track.json
        import wb_track
        ident, _ = wb_track.read_project(project) if project else (None, None)
        if ident:
            rec.update(mod_id=ident['mod_id'], folder=ident['folder'], identity=ident)
        return rec
    if rec.get('project') and rec.get('kind') == 'car':                  # v0.12: identity from workbench-car.json
        import wb_car
        ident, _ = wb_car.read_project(project) if project else (None, None)
        if ident:
            rec.update(mod_id=ident['mod_id'], folder=ident['folder'], identity=ident)
        return rec
    if rec.get('project'):
        ident, _ = proj.read_project(project) if project else (None, None)
        if ident:
            rec.update(mod_id=ident['mod_id'], folder=ident['folder'], module=ident['module'] + '.asi',
                       outputs=sorted([ident['module'] + '.asi', 'mod.toml']), sources=ident['sources'],
                       identity=ident, example=r'sdk\examples\%s' % ident['folder'])
    return rec


def plugin_prereqs(cfg, rid, project):
    """what keeps an SDK plugin recipe from starting (the job and the GUI make the same checks)"""
    rec = RECIPES[rid]
    bad = []
    if rec.get('project'):
        _, bad = proj.read_project(project)
        bad = list(bad)
        if not bad and cfg.get('kit'):                       # v0.6: never build a project with a kit it is not bound to
            st = proj.kit_status(cfg, project)
            if st['state'] != 'same':
                bad.append('kit binding: ' + st['text'])
    else:
        bad += pinned_problems(project, rec)
    bad += tool_prereqs(cfg, rec)
    if not cfg.get('kit'):
        bad.append('kit: ' + core.check_value('kit', ''))
    else:
        for d in rec['sdk_copy'] + ([rec['expected_list']] if rec.get('expected_list') else []):
            if not os.path.exists(os.path.join(cfg['kit'], d)):
                bad.append('kit file missing: %s (is %s the mod kit 0.6.0 folder?)' % (d, cfg['kit']))
    return bad


def package_record(dest, folder):
    """the Workbench's record of the package staged as <dest>\\<folder> (v0.5 per-package record, else STAGE.json)"""
    st = os.path.join(dest, '.wb_stage')
    for f in (os.path.join(st, 'packages', folder + '.json'), os.path.join(st, 'STAGE.json')):
        try:
            m = json.load(open(f, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if os.path.normcase(os.path.basename(m.get('package') or '')) == os.path.normcase(folder):
            return m
    return None


def collision_problems(dest, rec, project):
    """plugin projects: <dest>\\<mod id> may only replace a package of the same mod id staged from the same project"""
    final = os.path.join(dest, rec['folder'])
    if not os.path.exists(final):
        return []
    m = package_record(dest, rec['folder'])
    if not m:
        return ['%s exists but the Workbench has no record of staging it: not replaced (choose another staging folder)' % final]
    if m.get('mod_id') != rec['mod_id']:
        return ['%s holds a different mod (%s), not %s: not replaced' % (final, m.get('mod_id'), rec['mod_id'])]
    if os.path.normcase(os.path.abspath(m.get('project') or '')) != os.path.normcase(os.path.abspath(project)):
        return ['%s was staged from another project (%s) with the same mod id %s: not replaced (two projects may not share a '
                'mod id in one staging folder)' % (final, m.get('project'), rec['mod_id'])]
    return []

# what to install when a tool is missing (kit docs\PREREQUISITES.md / sdk\BUILD.md)
TOOL_HELP = {
    'cc': ('llvm-mingw clang (x86_64-w64-mingw32-clang.exe)', 'Settings "C compiler" or --cc FILE (or env BMKIT_LLVM_MINGW = the llvm-mingw folder, or '
           'its bin folder on PATH)', 'llvm-mingw-20260922-ucrt-x86_64.zip from https://github.com/mstorsjo/llvm-mingw/releases/'
           'tag/20260922 (sha256 e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666)'),
    'cmake': ('CMake 3.20 or later (cmake.exe)', 'Settings "CMake" or --cmake FILE (or cmake.exe on PATH)', 'cmake-4.4.4-windows-x86_64.zip from '
              'https://github.com/Kitware/CMake/releases/tag/v4.4.4 (sha256 bace36e94b31c68ab6fa295f26dfa11219e0701cf7c94b0284a7d1cb13dac536)'),
    'ninja': ('Ninja (ninja.exe)', 'Settings "Ninja" or --ninja FILE (or ninja.exe on PATH)', 'ninja-win.zip 1.13.2 from https://github.com/'
              'ninja-build/ninja/releases/tag/v1.13.2 (sha256 07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65)'),
}
TOOL_PLACEHOLDERS = ('python', 'fetex', 'bmpack', 'cmake', 'ninja', 'llvm_mingw', 'carimport', 'vehtool', 'game_data',
                     'trackbuild')
PATH_PLACEHOLDERS = ('src', 'build', 'toolchain_file', 'out', 'pkg', 'tbuild', 'desc')   # desc: the checked <name>.track.json


def tools(cfg):
    k = cfg['kit']
    cc = cfg.get('cc') or ''
    return {'python': cfg['python'], 'fetex': os.path.join(k, 'tools', 'fetex', 'fetex.py'),
            'carimport': os.path.join(k, 'tools', 'carimport', 'carimport.py'),      # v0.12
            'vehtool': os.path.join(k, 'tools', 'vehtool', 'vehtool.py'), 'game_data': cfg.get('game_data') or '',
            'trackbuild': core.kit_path(cfg, r'tools\trackbuild\tb.py'),         # v0.13; v0.28 setting "trackbuild"
            'bmpack': os.path.join(k, 'tools', 'bmpack', 'bmpack.py'),
            'cmake': cfg.get('cmake') or '', 'ninja': cfg.get('ninja') or '',
            'llvm_mingw': os.path.dirname(os.path.dirname(cc)) if cc else ''}   # <llvm-mingw>\bin\x86_64-w64-mingw32-clang.exe


def expand(argv, cfg, paths=None):
    """recipe argv -> real argv. An argument is a literal, '{tool}', or '-DNAME={tool or path}' (CMake cache values get forward
    slashes, as sdk\\build.ps1 passes them); any other placeholder is refused."""
    t = tools(cfg)
    paths = paths or {}
    out = []
    for a in argv:
        m = re.fullmatch(r'(-D[A-Z_]+=)?\{(\w+)\}', a)
        if m:
            k = m.group(2)
            if k in TOOL_PLACEHOLDERS:
                v = t[k]
            elif k in PATH_PLACEHOLDERS:
                v = paths[k]                              # KeyError = this recipe kind has no such folder
            else:
                raise KeyError(k)                         # not a known tool: refused by construction
            out.append(m.group(1) + v.replace('\\', '/') if m.group(1) else v)
        elif '{' in a:
            raise ValueError('recipe argument with an unknown placeholder: %r' % a)
        else:
            out.append(a)
    return out


def example_project(cfg, rid='p43-coupe-photo'):
    return os.path.join(cfg['kit'], RECIPES[rid]['example'])


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def tool_prereqs(cfg, rec):
    """missing build tools for a recipe -> actionable messages (what, how to give it, where to get it)"""
    miss = []
    for k in rec.get('needs', []):
        p = cfg.get(k) or ''
        what, how, get = TOOL_HELP[k]
        if not p or not os.path.isfile(p):
            miss.append('%s not found%s: give %s; install %s' % (what, (' at %s' % p) if p else '', how, get))
        elif k == 'cc' and os.path.basename(p).lower() != 'x86_64-w64-mingw32-clang.exe':
            miss.append('--cc must be llvm-mingw\'s bin\\x86_64-w64-mingw32-clang.exe (the SDK toolchain file finds the compiler '
                        'as <llvm-mingw>\\bin\\x86_64-w64-mingw32-clang.exe): %s' % p)
    return miss


def pinned_problems(project, rec):
    out = []
    for f, h in rec.get('pinned', {}).items():
        p = os.path.join(project, f)
        if os.path.isfile(p) and sha256_file(p) != h:
            out.append('%s differs from the kit\'s reviewed build script (sha256 %s, expected %s): the Workbench runs only the '
                       'kit\'s own build steps; restore the kit\'s %s or build this project by hand'
                       % (f, sha256_file(p)[:12], h[:12], f))
    return out


# ---------------------------------------------------------------- native plugin checks (in-process, no command runs)
def pe_info(path):
    """minimal PE reader: machine, PE32+, DLL flag, link time stamp, export names, imported DLLs"""
    import struct
    b = open(path, 'rb').read()
    if b[:2] != b'MZ':
        raise ValueError('not a PE file (no MZ header)')
    pe = struct.unpack_from('<I', b, 0x3c)[0]
    if b[pe:pe + 4] != b'PE\0\0':
        raise ValueError('not a PE file (no PE signature)')
    machine, nsec, stamp = struct.unpack_from('<HHI', b, pe + 4)
    opt_size, chars = struct.unpack_from('<HH', b, pe + 20)
    opt = pe + 24
    magic = struct.unpack_from('<H', b, opt)[0]
    dd = opt + (112 if magic == 0x20b else 96)
    secs = []
    so = opt + opt_size
    for i in range(nsec):
        vsize, va, rsize, raw = struct.unpack_from('<IIII', b, so + i * 40 + 8)
        secs.append((va, max(vsize, rsize), raw))

    def off(rva):
        for va, sz, raw in secs:
            if va <= rva < va + sz:
                return rva - va + raw
        raise ValueError('RVA %#x outside the sections' % rva)

    def cstr(o):
        return b[o:b.index(b'\0', o)].decode('ascii', 'replace')

    exports, imports = [], []
    erva, esz = struct.unpack_from('<II', b, dd)
    if erva:
        e = off(erva)
        n_names, names_rva = struct.unpack_from('<I', b, e + 24)[0], struct.unpack_from('<I', b, e + 32)[0]
        for i in range(n_names):
            exports.append(cstr(off(struct.unpack_from('<I', b, off(names_rva) + 4 * i)[0])))
    irva = struct.unpack_from('<I', b, dd + 8)[0]
    if irva:
        o = off(irva)
        while True:
            name_rva = struct.unpack_from('<I', b, o + 12)[0]
            if not name_rva:
                break
            imports.append(cstr(off(name_rva)))
            o += 20
    return {'machine': '%#x' % machine, 'pe32plus': magic == 0x20b, 'dll': bool(chars & 0x2000), 'time_stamp': stamp,
            'exports': sorted(exports), 'imports': sorted(imports, key=str.lower)}


def expected_hashes(cfg, rec):
    """the kit's reference list for this recipe's mod folder -> {file in the package: sha256}"""
    out = {}
    if not rec.get('expected_list'):
        return out
    p = os.path.join(cfg['kit'], rec['expected_list'])
    if os.path.isfile(p):
        for line in open(p, encoding='utf-8'):
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and not line.startswith('#') and parts[1].startswith(rec['folder'] + '/'):
                out[parts[1][len(rec['folder']) + 1:]] = parts[0].lower()
    return out


MOD_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def check_plugin_package(cfg, rec, pkg, project, mode='reference'):
    """-> (checks list of {check, ok, detail}, module info, reference match, expected). A failed check refuses staging.
    mode 'reference' (the project is the kit's example): the output must be the kit's expected bytes (EXPECTED_BUILD_SHA256).
    mode 'custom' (changed sources, same pinned build script): other bytes are allowed; the comparison is only recorded.
    These are structural checks; they are no proof that the code is safe (the player reviews and approves native code)."""
    checks = []

    def c(name, ok, detail):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})

    files = sorted(os.listdir(pkg))
    c('package files', files == sorted(rec['outputs']), files)
    mt = os.path.join(pkg, 'mod.toml')
    try:
        t = tomllib.loads(open(mt, encoding='utf-8').read())
    except Exception as e:                                         # noqa: BLE001 - any parse problem is a refusal
        t = {}
        c('mod.toml parses', False, str(e))
    plug = t.get('plugin') if isinstance(t.get('plugin'), dict) else {}
    if mode == 'reference':
        c('mod.toml id', t.get('id') == rec['mod_id'], t.get('id'))
    elif mode == 'project':
        idn = rec['identity']
        c('identity: mod.toml id / name = the declared ones', t.get('id') == idn['mod_id'] and t.get('name') == idn['name'],
          '%s / %s' % (t.get('id'), t.get('name')))
        c('identity: package folder = the mod id', os.path.basename(pkg) == idn['folder'], os.path.basename(pkg))
    else:
        pid = _id_of(project)
        c('mod.toml id (custom: the project id, valid)', bool(t.get('id')) and t.get('id') == pid and
          bool(MOD_ID_RE.match(str(t.get('id')))), t.get('id'))
    c('mod.toml [plugin] api = 1', plug.get('api') == 1, plug.get('api'))
    c('mod.toml [plugin] windows = the built module', plug.get('windows') == rec['module'], plug.get('windows'))
    c('mod.toml = the project\'s mod.toml', os.path.isfile(mt) and sha256_file(mt) == sha256_file(os.path.join(project, 'mod.toml')),
      'copied by the SDK build (POST_BUILD copy_if_different)')
    mod = os.path.join(pkg, rec['module'])
    info = None
    try:
        info = pe_info(mod)
        c('PE32+ x86-64 DLL', info['machine'] == '0x8664' and info['pe32plus'] and info['dll'],
          '%s pe32plus=%s dll=%s' % (info['machine'], info['pe32plus'], info['dll']))
        miss = [x for x in rec['exports'] if x not in info['exports']]
        c('plugin exports', not miss, 'missing %s' % miss if miss else info['exports'])
        c('no link time stamp (reproducible bytes)', info['time_stamp'] == 0, info['time_stamp'])
    except Exception as e:                                         # noqa: BLE001 - truncated / malformed file
        c('PE32+ x86-64 DLL', False, 'unreadable PE: %r' % e)
    exp = expected_hashes(cfg, rec)
    got = {f: sha256_file(os.path.join(pkg, f)) for f in rec['outputs'] if os.path.isfile(os.path.join(pkg, f))}
    ref = {f: (f in exp and got.get(f) == exp[f]) for f in rec['outputs']}
    if mode == 'reference':
        c('reference bytes = the kit expected sha256 (reference mode)', all(ref.values()),
          {f: (got.get(f, '')[:12], exp.get(f, '')[:12]) for f in rec['outputs']})
    return checks, info, ref, exp


def _id_of(project):
    try:
        return tomllib.loads(open(os.path.join(project, 'mod.toml'), encoding='utf-8').read()).get('id')
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def detect(project):
    """-> (recipe id, None) or (None, reason). A recipe's project: its required files + the mod id, or (v0.4, custom-source SDK
    plugins) any mod id when the project's build script is byte-identical to the recipe's pinned, reviewed one."""
    if not project or not os.path.isdir(project):
        return None, 'project folder not found: %s' % project
    names = os.listdir(project)                                     # v0.13: package.toml + *.track.json, no mod.toml (no import:
    if 'package.toml' in names and 'mod.toml' not in names and any(n.endswith('.track.json') for n in names):   # = wb_track.looks_like_track)
        if os.path.isfile(os.path.join(project, 'workbench-track.json')):
            return 'track-project', None
        try:
            p = tomllib.loads(open(os.path.join(project, 'package.toml'), encoding='utf-8').read()).get('package') or {}
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            return None, 'package.toml is not valid TOML: %s' % e
        for rid, r in RECIPES.items():
            if r.get('kind') == 'track' and r['mod_id'] and isinstance(p, dict) and p.get('mod_id') == r['mod_id']:
                return rid, None
        return None, ('a track description + package.toml without workbench-track.json and not the kit example (mod_id %r): make '
                      'it with New track project (or wb_track.py example FOLDER for the kit example)' % (p.get('mod_id') if isinstance(p, dict) else None))
    if os.path.isfile(os.path.join(project, 'car.toml')) and not os.path.isfile(os.path.join(project, 'mod.toml')):   # v0.12
        if os.path.isfile(os.path.join(project, 'workbench-car.json')):
            return 'car-project', None
        try:
            cid = (tomllib.loads(open(os.path.join(project, 'car.toml'), encoding='utf-8').read()).get('car') or {}).get('mod_id')
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError, AttributeError) as e:
            return None, 'car.toml is not valid TOML: %s' % e
        for rid, r in RECIPES.items():
            if r.get('kind') == 'car' and r['mod_id'] and cid == r['mod_id']:
                return rid, None
        return None, ('a car.toml without workbench-car.json and not the kit example (mod_id %r): make it with New car project '
                      '(or use the kit example carimport-coupe)' % cid)
    mt = os.path.join(project, 'mod.toml')
    if not os.path.isfile(mt):
        return None, 'not a mod project: no mod.toml in %s' % project
    try:
        mid = tomllib.loads(open(mt, encoding='utf-8').read()).get('id')
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, 'mod.toml is not valid TOML: %s' % e
    if proj.is_project(project):                                    # v0.5: a New plugin project (declared identity)
        return 'plugin-project', None
    for rid, r in RECIPES.items():
        if r['mod_id'] and mid == r['mod_id']:
            miss = [f for f in r['require'] if not os.path.isfile(os.path.join(project, f))]
            if miss:
                return None, 'project %s (%s) misses %s' % (project, mid, ', '.join(miss))
            return rid, None
    for rid, r in RECIPES.items():                                   # custom source on a pinned build script
        pins = r.get('pinned') or {}
        if pins and all(os.path.isfile(os.path.join(project, f)) and sha256_file(os.path.join(project, f)) == h
                        for f, h in pins.items()):
            miss = [f for f in r['require'] if not os.path.isfile(os.path.join(project, f))]
            if miss:
                return None, 'project %s (%s) misses %s' % (project, mid, ', '.join(miss))
            return rid, None
    if os.path.isfile(os.path.join(project, 'CMakeLists.txt')):
        return None, ('no verified recipe for mod id %r: its CMakeLists.txt is not the kit\'s reviewed SDK example build script '
                      '(the Workbench never configures a project\'s own build script; supported: %s)'
                      % (mid, ', '.join(r['mod_id'] for r in RECIPES.values() if r['mod_id'])))
    return None, ('no verified recipe for mod id %r (supported: %s, or a project made with New plugin project)'
                  % (mid, ', '.join(r['mod_id'] for r in RECIPES.values() if r['mod_id'])))


def source_mode(cfg, rid, project):
    """-> ('reference' | 'custom', changed files vs the kit's example). Reference = the project is file-for-file the kit's example."""
    ex = example_project(cfg, rid)
    a = tree_hashes(project) if os.path.isdir(project) else {}
    b = tree_hashes(ex) if cfg.get('kit') and os.path.isdir(ex) else {}
    diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return ('reference' if a and not diff else 'custom'), diff


# ---------------------------------------------------------------- destination guard
def protected_paths(cfg, project):
    """v0.4: configured / given / discovered roots (wb_core.protected_roots); no fixed workspace path"""
    return [p for p, _ in core.protected_roots(cfg, project)]


# files that mark a folder as one the Workbench must never stage into or below (checked on the destination and every ancestor,
# wherever it is - also outside the original workspace)
MARKERS = [
    (re.compile(r'^default\.xbe$', re.I), 'retail game data (default.xbe)'),
    (re.compile(r'^(burnout3|takedawn).*\.exe$', re.I), 'a game / host executable folder'),
    (re.compile(r'^plugin-approvals\.toml$', re.I), 'Burnout Mashup / Takedawn settings / approvals (saves)'),
    (re.compile(r'^(release\.py|RELEASE_MANIFEST\.json|PUBLISH_PLAN\.json)$', re.I), 'a release pipeline or release output'),
    (re.compile(r'^FROZEN\.md$', re.I), 'a frozen baseline'),
]


def _markers(folder, names, is_dest):
    out = []
    for rx, why in MARKERS:
        hit = [n for n in names if rx.match(n)]
        if hit:
            out.append('%s: %s holds %s' % (why, folder, hit[0]))
    if os.path.isfile(os.path.join(folder, 'Data', 'PrgData.bin')):
        out.append('retail game data: %s holds Data\\PrgData.bin' % folder)
    if core._kit_ok(folder):
        out.append('a mod kit folder: %s' % folder)
    for n in names:                                   # a folder that holds a game data copy one level down (runtime_data\base)
        c = os.path.join(folder, n)
        if (os.path.isfile(os.path.join(c, 'default.xbe')) or os.path.isfile(os.path.join(c, 'Data', 'PrgData.bin'))) and \
                os.path.isdir(c):
            out.append('holds a game data folder: %s' % c)
            break
    if not is_dest and 'mod.toml' in [n.lower() for n in names]:
        out.append('inside a mod project / mod folder: %s holds mod.toml' % folder)
    return out


def _real(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p))).rstrip('\\/')


def _inside(a, b):
    """a == b or a below b"""
    return a == b or a.startswith(b + os.sep)


def check_destination(cfg, project, dest):
    """-> list of reasons the destination is refused (empty = usable)"""
    why = []
    if not dest:
        return ['no staging destination chosen']
    d = _real(dest)
    if os.path.splitdrive(d)[1] in ('', '\\', '/'):
        why.append('a drive root cannot be a staging destination: %s' % dest)
    if os.path.isfile(dest):
        why.append('the destination is a file: %s' % dest)
    for p, w in core.protected_roots(cfg, project):
        r = _real(p)
        if _inside(d, r) or _inside(r, d):
            why.append('overlaps a protected location (%s: %s): %s' % (w, p, dest))
    a = d
    sealed = False
    while True:          # every ancestor: sealed lists (SHA256SUMS*.txt naming files there) and protection markers
        try:
            names = os.listdir(a)
        except OSError:
            names = []
        why += ['refused, %s' % m for m in _markers(a, names, a == d)]
        sums = [f for f in names if f.upper().startswith('SHA256SUMS') and f.lower().endswith('.txt')]
        if sums and not sealed:
            first = os.path.relpath(d, a).split(os.sep)[0].lower() if d != a else ''
            listed = set()
            for s in sums:
                try:
                    for line in open(os.path.join(a, s), encoding='utf-8', errors='replace'):
                        parts = line.strip().split(None, 1)
                        if len(parts) == 2:
                            listed.add(parts[1].lstrip('*').replace('\\', '/').lower())
                except OSError:
                    pass
            if not first or any(n == first or n.startswith(first + '/') for n in listed):
                why.append('inside a sealed folder (%s: %s lists files there)' % (a, sums[0]))
                sealed = True
        n = os.path.dirname(a)
        if n == a:
            break
        a = n
    if os.path.isdir(dest) and os.listdir(dest) and not os.path.isdir(os.path.join(dest, '.wb_stage')):
        why.append('the destination is a non-empty folder not made by the Workbench (choose an empty or new folder): %s' % dest)
    return why


# ---------------------------------------------------------------- tree helpers
def tree_hashes(root):
    out = {}
    for r, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x != '.wb_stage']
        for f in fs:
            p = os.path.join(r, f)
            h = hashlib.sha256()
            with open(p, 'rb') as fh:
                for b in iter(lambda: fh.read(1 << 20), b''):
                    h.update(b)
            out[os.path.relpath(p, root).replace('\\', '/')] = h.hexdigest()
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- the staging job (same interface as core.Job for the GUI)
class StageOp:
    kind = 'stage'

    def __init__(self, rid, project, dest, mode='auto'):
        self.rid, self.project, self.dest = rid, os.path.abspath(project), os.path.abspath(dest)
        self.mode = mode                                           # sdk-plugin: auto | reference | custom
        self.title = ('import, validate and stage %s' % os.path.basename(self.project) if rid == IMPORT_RECIPE else
                      'build, validate and stage %s' % (recipe(rid, self.project).get('folder') or os.path.basename(self.project)))
        self.meta = {'recipe': rid, 'project': self.project, 'dest': self.dest, 'mode': mode}


class StageJob:
    def __init__(self, cfg, op, on_line=None):
        self.cfg, self.op, self.on_line = cfg, op, on_line
        os.makedirs(cfg['logs'], exist_ok=True)
        self.ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        self.log_path = os.path.join(cfg['logs'], '%s_stage.log' % self.ts)
        self.proc = None
        self.rc = None
        self.cancelled = False
        self.started = self.ended = None
        self.done = threading.Event()
        self.tail = []
        self.result_dict = None
        self._lk = threading.Lock()

    def log(self, line):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        self.tail = (self.tail + [line])[-400:]
        if self.on_line:
            try:
                self.on_line(line)
            except Exception:
                pass

    def start(self):
        self.started = time.time()
        threading.Thread(target=self._main, daemon=True).start()
        return self

    def cancel(self):
        with self._lk:
            self.cancelled = True
            p = self.proc
        if p and p.poll() is None:
            subprocess.run([core.TASKKILL, '/PID', str(p.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def wait(self, timeout=None):
        return self.done.wait(timeout)

    def output(self):
        with open(self.log_path, encoding='utf-8', errors='replace') as f:
            return f.read()

    def _run(self, name, argv, cwd):
        self.log('## step %s\n# cwd: %s\n# argv: %s' % (name, cwd, json.dumps(argv)))
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
        r = {'kind': 'stage', 'recipe': self.op.rid, 'project': self.op.project, 'dest': self.op.dest, 'log': self.log_path,
             'steps': [], 'ok': False, 'cancelled': False}
        try:
            self._stage(r)
        except Exception as e:                                    # never leave the GUI without a result
            import traceback
            self.log('INTERNAL ERROR %r\n%s' % (e, traceback.format_exc()))
            r.update(verdict='INTERNAL ERROR (%s)' % e, excerpt=self.tail[-12:])
        r['cancelled'] = self.cancelled
        if self.cancelled and not r.get('staged'):
            r['verdict'] = 'CANCELLED'
        if r.get('attempt') and os.path.isdir(r['attempt']) and not r.get('ok'):
            with open(os.path.join(r['attempt'], 'ATTEMPT.json'), 'w', encoding='utf-8') as f:
                json.dump({k: v for k, v in r.items() if k != 'excerpt'}, f, indent=1)
        self.rc = 0 if r.get('ok') else 1
        self.result_dict = r
        self.ended = time.time()
        self.log('# result %s after %.1f s' % (r.get('verdict'), self.ended - self.started))
        self.done.set()

    def _import(self, r):
        """v0.11 Import folder -> Validate -> Stage: copy a finished mod into a fresh attempt, validate the COPY (manifest, host
        requirements, native module structure, the kit's bmpack validate), commit like every recipe (previous package moved to
        .wb_stage\\previous, nothing deleted). Nothing is executed from the package, built, installed or approved."""
        cfg, op = self.cfg, self.op
        self.log('# %s\n# source %s, destination %s' % (op.title, op.project, op.dest))
        info = import_check(cfg, op.project, op.dest)
        r.update(import_check={k: v for k, v in info.items() if k not in ('pe', 'files')}, mod_id=info.get('mod_id'))
        for ch in info['checks']:
            self.log('# check %-45s %s  %s' % (ch['check'], 'ok' if ch['ok'] else 'FAILED', ch['detail']))
        for n in info['notes']:
            self.log('# note: ' + n)
        if info['problems']:
            for b in info['problems']:
                self.log('REFUSED: ' + b)
            r.update(verdict='NOT STARTED', excerpt=info['problems'])
            return
        src_before = tree_hashes(op.project)
        st = os.path.join(op.dest, '.wb_stage')
        attempt = os.path.join(st, 'work', self.ts)
        work = os.path.join(attempt, info['folder'])
        r.update(attempt=attempt, work=work)
        for rel in info['files']:                                  # plain file copies (links were refused above)
            d = os.path.join(work, *rel.split('/'))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(os.path.join(op.project, *rel.split('/')), d)
        copied = tree_hashes(work)
        r['steps'].append({'step': 'copy', 'rc': 0 if copied == src_before else 1})
        if copied != src_before:
            r.update(verdict='COPY FAILED (not staged)', excerpt=['the copy differs from the source (changed while copying?)'])
            return
        self.log('# copied %d files into %s (sha256 = the source)' % (len(copied), work))
        checks = list(info['checks'])
        if info['package_kind'] == IMPORT_PLUGIN:                  # the module in the COPY is the one staged
            pe = pe_info(os.path.join(work, info['module']))
            checks.append({'check': 'native module of the copy = the checked bytes', 'ok':
                           copied[info['module']] == sha256_file(os.path.join(op.project, info['module'])),
                           'detail': copied[info['module']]})
            r['module'] = {'file': info['module'], 'sha256': copied[info['module']], 'exports': pe['exports'],
                           'imports': pe['imports'], 'time_stamp': pe['time_stamp']}
        vop = core.op_validate(cfg, [work])
        rc, out = self._run('bmpack validate', vop.argv, vop.cwd)
        r['steps'].append({'step': 'bmpack validate', 'rc': rc})
        rep = None
        i = out.find('{')
        if rc in (0, 1) and i >= 0:
            try:
                rep = json.loads(out[i:])
            except ValueError:
                rep = None
        r['bmpack'] = {'ok': bool(rep and rep.get('ok')), 'rc': rc,
                       'refusals': [{'service': f.get('service'), 'mod': f.get('mod'), 'why': f.get('why')}
                                    for f in (rep or {}).get('refusals', [])],
                       'mods': [{'id': m.get('id'), 'version': m.get('version'), 'usable': m.get('usable')}
                                for m in (rep or {}).get('mods', [])]}
        checks.append({'check': 'host admission of the mod alone (bmpack validate, kit host readers)', 'ok': r['bmpack']['ok'],
                       'detail': '; '.join('[%s] %s' % (f['service'], f['why']) for f in r['bmpack']['refusals']) or 'ACCEPTED'})
        r['checks'] = checks
        if self.cancelled or not all(ch['ok'] for ch in checks):
            r.update(verdict='CANCELLED' if self.cancelled else 'VALIDATION FAILED',
                     excerpt=['%s: %s' % (ch['check'], ch['detail']) for ch in checks if not ch['ok']])
            return
        if tree_hashes(op.project) != src_before:
            r.update(verdict='SOURCE CHANGED DURING THE IMPORT (not staged)', excerpt=['the source files changed; import again'])
            return
        with self._lk:
            if self.cancelled:
                r.update(verdict='CANCELLED')
                return
            self.committing = True
        final = os.path.join(op.dest, info['folder'])
        prev = None
        if os.path.exists(final):
            prev = os.path.join(st, 'previous', self.ts, info['folder'])
            os.makedirs(os.path.dirname(prev))
            os.rename(final, prev)
        try:
            os.rename(work, final)
        except OSError:
            if prev:
                os.rename(prev, final)                            # roll back: the previous package stays staged
            raise
        now = datetime.datetime.now().isoformat(timespec='seconds')
        man = {'schema': 'bm-workbench-stage/1', 'recipe': IMPORT_RECIPE, 'kind': info['package_kind'], 'mod_id': info['mod_id'],
               'folder': info['folder'], 'project': None, 'package': final, 'package_files': copied,
               'previous_moved_to': prev, 'log': self.log_path, 'time': now,
               'kit_identity': wb_kit.stamp(wb_kit.kit_identity(cfg['kit'])),
               'provenance': {'type': 'imported', 'reproducible_build': False, 'source': op.project, 'time': now,
                              'source_files': src_before, 'source_sizes': info['files'],
                              'note': 'copied as is: nothing was built or executed; the Workbench cannot rebuild these bytes '
                                      'from source (a Workbench project / kit recipe build records its build instead)'},
               'notes': info['notes'], 'validation': checks, 'bmpack': r['bmpack'], 'reference': 'none (imported)',
               'reference_match': {}}
        if info['package_kind'] == IMPORT_PLUGIN:
            m = r['module']
            man.update(module={'file': m['file'], 'sha256': m['sha256'], 'exports': m['exports'], 'imports': m['imports'],
                               'time_stamp': m['time_stamp']},
                       native_code={'approved': False, 'sha256': m['sha256'],
                                    'note': 'The Workbench never approves native code. An imported module was not built here: '
                                            'review it, then approve these exact bytes yourself (the line "%s sha256:%s" in '
                                            'your plugin-approvals.toml, or the MODS page). Nothing was installed.'
                                            % (info['mod_id'], m['sha256'])})
        with open(os.path.join(st, 'STAGE.json'), 'w', encoding='utf-8') as f:
            json.dump(man, f, indent=1)
        os.makedirs(os.path.join(st, 'packages'), exist_ok=True)
        with open(os.path.join(st, 'packages', info['folder'] + '.json'), 'w', encoding='utf-8') as f:
            json.dump(man, f, indent=1)
        with open(os.path.join(st, 'history.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps({k: man[k] for k in ('time', 'recipe', 'package', 'previous_moved_to', 'log')}) + '\n')
        r.update(ok=True, verdict='STAGED (IMPORTED)', staged=final, previous=prev, manifest=os.path.join(st, 'STAGE.json'),
                 package_manifest=os.path.join(st, 'packages', info['folder'] + '.json'), kit_identity=man['kit_identity'],
                 package_files={k: v[:12] for k, v in copied.items()}, reference_match={}, work=None,
                 provenance=provenance_text(man), notes=info['notes'])
        if info['package_kind'] == IMPORT_PLUGIN:
            r['native_code'] = {'approved': False, 'sha256': r['module']['sha256']}

    def _stage(self, r):
        cfg, op = self.cfg, self.op
        if op.rid == IMPORT_RECIPE:                                # v0.11
            return self._import(r)
        rec = recipe(op.rid, op.project)
        self.rec = rec
        if rec.get('kind') == 'car':                               # v0.12 (wb_car.stage: checks, isolated copy, kit tools)
            import wb_car
            return wb_car.stage(self, r, rec)
        if rec.get('kind') == 'track':                             # v0.13 (wb_track.stage: same pattern, kit trackbuild)
            import wb_track
            return wb_track.stage(self, r, rec)
        self.log('# %s\n# recipe %s, project %s, destination %s' % (op.title, op.rid, op.project, op.dest))
        rid, why = detect(op.project)
        bad = ([why] if why else ([] if rid == op.rid else ['the project is not a %s project' % op.rid]))
        bad += check_destination(cfg, op.project, op.dest)
        plugin = rec.get('kind') == 'sdk-plugin'
        if plugin:
            bad += plugin_prereqs(cfg, op.rid, op.project)
            if rec.get('project') and not bad:
                bad += collision_problems(op.dest, rec, op.project)
                if op.mode == 'reference':
                    bad.append('reference mode needs the kit example; a new project has no reference bytes (use auto)')
            if not bad and rec.get('project'):
                r['mode'], r['source_changes'] = 'project', None
                r['identity'] = rec['identity']
                self.log('# mode project: %s (%s), module %s, staged folder %s'
                         % (rec['mod_id'], rec['identity']['name'], rec['module'], rec['folder']))
            elif not bad:
                mode, changed = source_mode(cfg, op.rid, op.project)
                if op.mode not in ('auto', 'reference', 'custom'):
                    bad.append('unknown mode %r (auto, reference, custom)' % op.mode)
                elif op.mode == 'reference' and mode != 'reference':
                    bad.append('reference mode needs the kit example unchanged; these files differ: %s (use mode custom)'
                               % ', '.join(changed[:8]))
                r['mode'] = 'custom' if op.mode == 'custom' else mode
                r['source_changes'] = changed
                self.log('# mode %s (requested %s); files that differ from the kit example: %s' % (r['mode'], op.mode, changed))
        else:
            bad += [m for m in core.bmpack_prereqs(cfg, need_game=rec['bmpack_validate'])]
            if not os.path.isfile(tools(cfg)['fetex']):
                bad.append('fetex.py not found under the kit folder %s' % cfg['kit'])
        if bad:
            for b in bad:
                self.log('REFUSED: ' + b)
            r.update(verdict='NOT STARTED', excerpt=bad)
            return
        src_before = tree_hashes(op.project)
        st = os.path.join(op.dest, '.wb_stage')
        attempt = os.path.join(st, 'work', self.ts)
        r['attempt'] = attempt
        if plugin:
            work = self._build_plugin(r, rec, attempt)
            if not work:
                return
        else:
            work = self._build_fetex(r, rec, attempt)
            if not work:
                return
        self._commit(r, rec, st, work, src_before)

    def _build_plugin(self, r, rec, attempt):
        """the SDK's documented by-hand build of one example in a fresh copy -> the built drop-in mod folder, or None"""
        cfg, op = self.cfg, self.op
        sdk = os.path.join(attempt, 'src', 'sdk')
        src = os.path.join(sdk, rec['example'].split('\\', 1)[1])          # sdk\examples\host-info -> examples\host-info
        if rec.get('project'):
            src = os.path.join(sdk, 'examples', rec['folder'])
        for d in rec['sdk_copy']:
            shutil.copytree(os.path.join(cfg['kit'], d), os.path.join(sdk, d.split('\\', 1)[1]))
        shutil.copytree(op.project, src, ignore=shutil.ignore_patterns('.wb_stage', '__pycache__'))
        if rec.get('project'):                    # the Workbench's own build script (validated names only), in the copy
            text = proj.project_cmake(rec['identity'], rec['sources'])
            with open(os.path.join(src, 'CMakeLists.txt'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            r['build_script'] = {'owner': 'Workbench (wb_project.project_cmake)', 'file': 'CMakeLists.txt',
                                 'sha256': sha256_file(os.path.join(src, 'CMakeLists.txt')), 'sources': rec['sources']}
            self.log('# generated build script (sha256 %s):\n%s' % (r['build_script']['sha256'], text))
        build = os.path.join(attempt, 'build')
        r['sdk_files'] = {d.split('\\', 1)[1]: tree_hashes(os.path.join(sdk, d.split('\\', 1)[1])) for d in rec['sdk_copy']}
        t = tools(cfg)
        ident = {}
        for k, exe in (('cc', cfg['cc']), ('cmake', t['cmake']), ('ninja', t['ninja'])):
            rc, out = self._run('identify %s' % k, [exe, '--version'], attempt)
            if self.cancelled:
                r.update(verdict='CANCELLED')
                return None
            ident[k] = {'path': exe, 'sha256': sha256_file(exe), 'version': (out.strip().splitlines() or [''])[0], 'rc': rc}
        ident['llvm_mingw'] = {'path': t['llvm_mingw']}
        r['tools'] = ident
        paths = {'src': src, 'build': build, 'toolchain_file': os.path.join(sdk, 'cmake', 'llvm-mingw-x86_64.cmake')}
        for i, argv in enumerate(rec['build']):
            rc, out = self._run('build %d' % (i + 1), expand(argv, cfg, paths), attempt)
            r['steps'].append({'step': 'build %d' % (i + 1), 'rc': rc})
            if self.cancelled or rc != 0:
                r.update(verdict='BUILD FAILED' if not self.cancelled else 'CANCELLED',
                         excerpt=[l for l in out.splitlines() if l.strip()][-12:])
                return None
        work = os.path.join(build, 'out', rec['folder'])
        r['work'] = work
        for o in rec['outputs']:
            if not os.path.isfile(os.path.join(work, o)):
                r.update(verdict='BUILD FAILED', excerpt=['expected output missing: %s' % o])
                return None
        checks, info, ref, exp = check_plugin_package(cfg, rec, work, op.project, r['mode'])
        for ch in checks:
            self.log('# check %-45s %s  %s' % (ch['check'], 'ok' if ch['ok'] else 'FAILED', ch['detail']))
        r['steps'].append({'step': 'plugin checks', 'rc': 0 if all(ch['ok'] for ch in checks) else 1})
        r['checks'] = checks
        r['module'] = {'file': rec['module'], 'sha256': sha256_file(os.path.join(work, rec['module'])),
                       'exports': (info or {}).get('exports'), 'imports': (info or {}).get('imports')}
        r['reference_match'] = ref
        r['reference_expected'] = exp
        if not all(ch['ok'] for ch in checks):
            r.update(verdict='VALIDATION FAILED', excerpt=['%s: %s' % (ch['check'], ch['detail']) for ch in checks if not ch['ok']])
            return None
        if self.cancelled:
            r.update(verdict='CANCELLED')
            return None
        return work

    def _build_fetex(self, r, rec, attempt):
        cfg, op = self.cfg, self.op
        work = os.path.join(attempt, rec['folder'])
        r['work'] = work
        shutil.copytree(op.project, work, ignore=shutil.ignore_patterns('.wb_stage', '__pycache__'))
        for d in rec['mkdirs']:
            os.makedirs(os.path.join(work, d), exist_ok=True)
        for i, argv in enumerate(rec['build']):
            rc, out = self._run('build %d' % (i + 1), expand(argv, cfg), work)
            r['steps'].append({'step': 'build %d' % (i + 1), 'rc': rc})
            if self.cancelled or rc != 0:
                r.update(verdict='BUILD FAILED' if not self.cancelled else 'CANCELLED',
                         excerpt=[l for l in out.splitlines() if l.strip()][-12:])
                return None
        for o in rec['outputs']:
            if not os.path.isfile(os.path.join(work, o)):
                r.update(verdict='BUILD FAILED', excerpt=['expected output missing: %s' % o])
                return None
        for i, argv in enumerate(rec['validate']):
            rc, out = self._run('validate %d' % (i + 1), expand(argv, cfg), work)
            r['steps'].append({'step': 'validate %d' % (i + 1), 'rc': rc})
            if self.cancelled or rc != 0:
                r.update(verdict='VALIDATION FAILED' if not self.cancelled else 'CANCELLED',
                         excerpt=[l for l in out.splitlines() if l.strip()][-12:])
                return None
        if rec['bmpack_validate']:
            vop = core.op_validate(cfg, [work])
            rc, out = self._run('bmpack validate', vop.argv, vop.cwd)
            r['steps'].append({'step': 'bmpack validate', 'rc': rc})
            rep = None
            i = out.find('{')
            if rc in (0, 1) and i >= 0:
                try:
                    rep = json.loads(out[i:])
                except ValueError:
                    rep = None
            r['bmpack'] = {'ok': bool(rep and rep.get('ok')), 'rc': rc,
                           'refusals': [{'service': f.get('service'), 'mod': f.get('mod'), 'why': f.get('why')}
                                        for f in (rep or {}).get('refusals', [])],
                           'mods': [{'id': m.get('id'), 'version': m.get('version'), 'usable': m.get('usable')}
                                    for m in (rep or {}).get('mods', [])]}
            if self.cancelled or rc != 0 or not r['bmpack']['ok']:
                r.update(verdict='CANCELLED' if self.cancelled else 'VALIDATION FAILED',
                         excerpt=['[%s] %s: %s' % (f['service'], f['mod'], f['why']) for f in r['bmpack']['refusals']] or
                         [l for l in out.splitlines() if l.strip()][-12:])
                return None
        return work

    def _commit(self, r, rec, st, work, src_before):
        op = self.op
        if tree_hashes(op.project) != src_before:
            r.update(verdict='SOURCE CHANGED DURING THE BUILD (not staged)', excerpt=['the project files changed; stage again'])
            return
        with self._lk:                                            # past this point the attempt is committed, not cancellable
            if self.cancelled:
                r.update(verdict='CANCELLED')
                return
            self.committing = True
        files = tree_hashes(work)
        final = os.path.join(op.dest, rec['folder'])
        prev = None
        if os.path.exists(final):
            prev = os.path.join(st, 'previous', self.ts, rec['folder'])
            os.makedirs(os.path.dirname(prev))
            os.rename(final, prev)
        try:
            os.rename(work, final)
        except OSError:
            if prev:
                os.rename(prev, final)                            # roll back: the previous package stays staged
            raise
        man = {'schema': 'bm-workbench-stage/1', 'recipe': op.rid, 'mod_id': rec['mod_id'], 'project': op.project,
               'folder': rec['folder'], 'kit_identity': wb_kit.stamp(wb_kit.kit_identity(self.cfg['kit'])),
               'source_files': src_before, 'package': final, 'package_files': files, 'previous_moved_to': prev,
               'log': self.log_path, 'time': datetime.datetime.now().isoformat(timespec='seconds'),
               'reference_match': r['reference_match'] if 'reference_match' in r else
               {o: files.get(o, '')[:len(h)] == h for o, h in rec.get('reference', {}).items()},
               'reference': rec.get('reference_label'),
               'bmpack': r.get('bmpack')}
        if rec.get('kind') == 'sdk-plugin':          # v0.3: source + tool identities, validation, native-code approval state
            m = r['module']
            if rec.get('project'):
                man.update(identity={k: rec['identity'][k] for k in ('mod_id', 'name', 'module', 'folder', 'sources')},
                           build_script=r.get('build_script'))
            shown = {'src': '<attempt>/src/' + rec['example'].replace('\\', '/'), 'build': '<attempt>/build',
                     'toolchain_file': '<attempt>/src/sdk/cmake/llvm-mingw-x86_64.cmake'}
            man.update(kind='sdk-plugin', mode=r['mode'], reference_required=r['mode'] == 'reference',
                       source_changes=r.get('source_changes'), output_files=files, kit=self.cfg['kit'], sdk_files=r.get('sdk_files'), tools=r.get('tools'),
                       build_steps=[expand(a, self.cfg, shown) for a in rec['build']],
                       validation=r.get('checks'), reference_expected=r.get('reference_expected'),
                       module={'file': m['file'], 'sha256': m['sha256'], 'exports': m['exports'], 'imports': m['imports']},
                       native_code={'approved': False, 'sha256': m['sha256'],
                                    'note': 'The Workbench never approves native code. Before use the player reviews and '
                                            'approves these exact bytes (MODS page APPROVE CODE, or the line "%s sha256:%s" in '
                                            'plugin-approvals.toml; kit docs\\INSTALL.md). Nothing was installed.'
                                            % (rec['mod_id'], m['sha256'])})
        if rec.get('kind') == 'car':                  # v0.12: car, inputs, tools, checks, requirements, donor dependency
            man.update(r['car_record'])
            man['kit'] = self.cfg['kit']
        if rec.get('kind') == 'track':                # v0.13: track, inputs, tools, gates, donor dependency, evidence
            man.update(r['track_record'])
            man['kit'] = self.cfg['kit']
        with open(os.path.join(st, 'STAGE.json'), 'w', encoding='utf-8') as f:
            json.dump(man, f, indent=1)
        os.makedirs(os.path.join(st, 'packages'), exist_ok=True)      # v0.5: one record per staged package folder
        with open(os.path.join(st, 'packages', rec['folder'] + '.json'), 'w', encoding='utf-8') as f:
            json.dump(man, f, indent=1)
        with open(os.path.join(st, 'history.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps({k: man[k] for k in ('time', 'recipe', 'package', 'previous_moved_to', 'log')}) + '\n')
        r.update(ok=True, verdict='STAGED', staged=final, previous=prev, manifest=os.path.join(st, 'STAGE.json'),
                 package_manifest=os.path.join(st, 'packages', rec['folder'] + '.json'), mod_id=rec['mod_id'],
                 kit_identity=man['kit_identity'],
                 package_files={k: v[:12] for k, v in files.items()}, reference_match=man['reference_match'], work=None)
        if rec.get('kind') == 'sdk-plugin':
            r['native_code'] = {'approved': False, 'sha256': r['module']['sha256']}
            r['package_sha256'] = files
        if rec.get('kind') == 'car':
            cr = r['car_record']
            r['package_sha256'] = files
            r['car_record_summary'] = {'donor_files': [f['rel'] for f in cr['donor_dependencies']['read_at_build']],
                                       'requirements': {k: v for k, v in (cr['requirements'] or {}).items()
                                                        if k in ('platform', 'tables', 'services', 'requires_mods')}}
            del r['car_record']                                   # in the record files; the result keeps a summary
        if rec.get('kind') == 'track':
            tr = r.pop('track_record')
            r['package_sha256'] = files
            r['track_record_summary'] = {'gates': '%d / %d ok' % (sum(tr['trackbuild_gates'].values()), len(tr['trackbuild_gates'])),
                                         'donor': tr['donor_dependencies']['host'], 'set_files': tr['set_files'],
                                         'requirements': {k: v for k, v in (tr['requirements'] or {}).items()
                                                          if k in ('platform', 'tables', 'services', 'requires_mods')}}


def summarize(r):
    L = ['STAGE: %s' % r.get('verdict')]
    if (RECIPES.get(r.get('recipe')) or {}).get('kind') == 'car':          # v0.12
        import wb_car
        L += wb_car.summary_lines(r)
    if (RECIPES.get(r.get('recipe')) or {}).get('kind') == 'track':        # v0.13
        import wb_track
        L += wb_track.summary_lines(r)
    if r.get('recipe') == IMPORT_RECIPE:
        L.append('import of %s (copied as is: no build, no package script run, nothing installed or approved)' % r.get('project'))
        for c in (r.get('import_check') or {}).get('checks') or []:
            L.append('  check %-55s %s  %s' % (c['check'], 'ok' if c['ok'] else 'FAILED', str(c['detail'])[:160]))
    for s in r.get('steps', []):
        L.append('  %-16s exit %s' % (s['step'], s['rc']))
    for c in r.get('checks') or []:
        if not c['ok']:
            L.append('  check %s FAILED: %s' % (c['check'], c['detail']))
    if r.get('bmpack'):
        b = r['bmpack']
        L.append('bmpack validate: %s; mods %s' % ('ACCEPTED' if b['ok'] else 'REFUSED',
                                                  ', '.join('%s %s' % (m['id'], m['version']) for m in b['mods'])))
    if r.get('ok'):
        L.append('staged package: %s' % r['staged'])
        if r.get('kit_identity'):
            L.append('built with kit %s' % r['kit_identity']['id'])
        for k, v in r['package_files'].items():
            L.append('  %-28s %s' % (k, v))
        if r.get('recipe') == IMPORT_RECIPE:
            L.append('provenance: %s' % r.get('provenance'))
            for n in r.get('notes') or []:
                L.append('note: %s' % n)
        elif (RECIPES.get(r.get('recipe')) or {}).get('kind') in ('car', 'track'):
            L.append('%s recipe' % RECIPES[r['recipe']]['kind'] + ' %s, mode %s; matches %s: %s' % (r['recipe'], r.get('mode'),
                     RECIPES[r['recipe']]['reference_label'], (('%d / %d files identical' % (sum(r['reference_match'].values()),
                     len(r['reference_match']))) if r.get('reference_match') and RECIPES[r['recipe']]['kind'] == 'track'
                     else r.get('reference_match') or 'n/a')))
        elif r.get('mode') == 'project':
            i = r['identity']
            L.append('plugin mode: project (identity %s "%s", module %s.asi, staged folder %s; no reference bytes)'
                     % (i['mod_id'], i['name'], i['module'], i['folder']))
        else:
            L.append('matches %s: %s' % (RECIPES[r['recipe']].get('reference_label', 'the reference'), r['reference_match']))
        if r.get('mode') and r['mode'] != 'project' and (RECIPES.get(r.get('recipe')) or {}).get('kind') not in ('car', 'track'):
            L.append('plugin mode: %s%s' % (r['mode'], ' (the kit expected bytes were required)' if r['mode'] == 'reference'
                                            else ' (changed sources: %s; other bytes allowed)' % ', '.join(r.get('source_changes') or [])))
        if r.get('native_code'):
            L.append('  (the checks above are structural; they are no proof that the code is safe)')
            L.append('native code: NOT approved (the player approves sha256 %s; see STAGE.json native_code)'
                     % r['native_code']['sha256'])
        if r.get('previous'):
            L.append('previous package moved to: %s' % r['previous'])
    else:
        L.append('the staged package (if any) was NOT changed')
        if r.get('attempt') and os.path.isdir(r['attempt']):
            L.append('attempt folder (for diagnosis): %s' % r['attempt'])
        for l in r.get('excerpt') or []:
            L.append('  ' + l)
    L.append('full log: %s' % r['log'])
    return '\n'.join(L)


def run_sync(cfg, op, timeout=None, on_line=None):
    lock = core.OpLock(cfg)
    why = lock.acquire(op.title)
    if why:
        raise RuntimeError(why)
    try:
        job = StageJob(cfg, op, on_line).start()
        if not job.wait(timeout):
            job.cancel()
            job.wait(60)
        return job, job.result_dict
    finally:
        lock.release()


def main(argv):
    """wb_stage.py PROJECT DEST [--kit DIR] [--game-data DIR] [--cc FILE] [--cmake FILE] [--ninja FILE] [--config FILE]
    -> summary + one JSON line"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('dest')
    ap.add_argument('--kit')
    ap.add_argument('--game-data')
    ap.add_argument('--cc')
    ap.add_argument('--cmake')
    ap.add_argument('--ninja')
    ap.add_argument('--config')
    ap.add_argument('--mode', default='auto', choices=['auto', 'reference', 'custom'],
                    help='SDK plugin recipe: reference = the kit example, its expected bytes required; custom = changed sources')
    ap.add_argument('--import', dest='imp', action='store_true',
                    help='v0.11: PROJECT is a finished mod folder: copy it as is, validate the copy, stage it (no build)')
    ap.add_argument('--check', action='store_true', help='--import: the checks only (writes nothing)')
    ap.add_argument('--draft', help='--import or a car project: preview the staged result against this profile draft (read only)')
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config, kit=a.kit, game_data=a.game_data, cc=a.cc, cmake=a.cmake, ninja=a.ninja)
    if a.imp:
        if a.check:
            i = import_check(cfg, a.project, a.dest)
            print(json.dumps({k: v for k, v in i.items() if k != 'pe'}, indent=1, default=str))
            return 0 if not i['problems'] else 3
        try:
            job, r = run_sync(cfg, StageOp(IMPORT_RECIPE, a.project, a.dest))
        except RuntimeError as e:
            print(json.dumps({'verdict': 'NOT STARTED', 'busy': str(e)}))
            return 4
        print(summarize(r))
        if r['ok']:
            import wb_profile
            d = wb_profile.new_draft()
            if a.draft:
                d, bad = wb_profile.load_draft(a.draft)
                if bad:
                    print('\n'.join(bad))
                    return 3
            print(wb_profile.preview_text(wb_profile.preview(cfg, r['staged'], d)))
        print(json.dumps({k: v for k, v in r.items() if k != 'excerpt'} if r['ok'] else r, default=str))
        return 0 if r['ok'] else (3 if r.get('verdict') == 'NOT STARTED' else 1)
    rid, why = detect(a.project)
    if not rid:
        print(json.dumps({'verdict': 'NOT STARTED', 'reason': why}))
        return 3
    try:
        job, r = run_sync(cfg, StageOp(rid, a.project, a.dest, a.mode))
    except RuntimeError as e:
        print(json.dumps({'verdict': 'NOT STARTED', 'busy': str(e)}))
        return 4
    print(summarize(r))
    if r['ok'] and RECIPES[rid].get('kind') in ('car', 'track'):            # v0.12 / v0.13: Preview, as after an import
        import wb_profile
        d, bad = wb_profile.load_draft(a.draft) if a.draft else (wb_profile.new_draft(), [])
        print('\n'.join(bad) if bad else wb_profile.preview_text(wb_profile.preview(cfg, r['staged'], d)))
    print(json.dumps({k: v for k, v in r.items() if k != 'excerpt'} if r['ok'] else r))
    return 0 if r['ok'] else (3 if r.get('verdict') == 'NOT STARTED' else 1)


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
