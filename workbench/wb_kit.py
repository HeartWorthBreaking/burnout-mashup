"""wb_kit - kit identity, host identity and host / service compatibility for Burnout Mashup Workbench v0.6 (gp\\workbench).

Two different questions, kept apart on purpose:
  kit identity    WHICH kit a project was generated / bound with, a package was built with, a profile was checked with:
                  version + sha256 of the kit's MANIFEST.json (every kit file's hash) + sha256 of the SDK headers / CMake files
                  the build copies. Recorded; a change marks results stale and needs an explicit rebind - never a migration.
  compatibility   CAN this package run on this host: the mod.toml [bmashup] platform / requires and [plugin] api against the
                  host's platform version and offered services. Decided by the host's own service table, never by "same kit
                  version": a host is described by a kit whose reference host it is (MANIFEST.json reference_host sha256 +
                  tools\\bmpack\\host_readers\\...\\bm_platform_table.h). A host no known kit describes is refused (its services
                  are unknown), not guessed.
Read only: this module never writes a kit, a host or a project.

    py -3 -B wb_kit.py identity [KIT]       py -3 -B wb_kit.py host EXE [--kit KIT ...]
"""
import hashlib
import json
import os
import re
import sys
import tomllib

SCHEMA = 'bm-kit-identity/1'
TABLE = r'tools\bmpack\host_readers\src\game\bm_platform_table.h'
SDK_PARTS = (r'sdk\include', r'sdk\cmake', r'sdk\examples\host-info')     # what a plugin build copies / follows
BUILD_ID_RE = re.compile(rb'bmp-(\d+\.\d+\.\d+)\+([0-9a-f]{12})')
REQ_RE = re.compile(r'^\s*([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)\s*>=\s*(\d+)\s*$')
PLAT_RE = re.compile(r'^\s*>=\s*(\d+(?:\.\d+){0,2})\s*$')
_cache = {}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _tree_digest(root, parts):
    h, n = hashlib.sha256(), 0
    for part in parts:
        base = os.path.join(root, part)
        for dp, dns, fns in os.walk(base):
            dns.sort()
            for fn in sorted(fns):
                p = os.path.join(dp, fn)
                h.update(os.path.relpath(p, root).replace('\\', '/').encode() + b'\0' + sha256_file(p).encode() + b'\n')
                n += 1
    return h.hexdigest(), n


def vtuple(v):
    try:
        t = tuple(int(x) for x in str(v).split('.'))
    except ValueError:
        return None
    return t + (0,) * (3 - len(t)) if 0 < len(t) <= 3 else None


def parse_table(path):
    """the host-readers platform table -> (platform version, {service: version}) or (None, {})"""
    try:
        s = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return None, {}
    m = re.search(r'#define\s+BO3_PLATFORM_VERSION\s+"([0-9.]+)"', s)
    return (m.group(1) if m else None), {n: int(v) for n, v in re.findall(r'X\("([a-z0-9_.]+)",\s*(\d+)\s*,', s)}


def parse_tables(path):
    """v0.7: the mod.toml tables the host reads (T(table, version, keys)) -> {'bmashup.<table>': version}. A [bmashup]
    requires entry names a capability = a service OR such a table (bm_platform_table.h)."""
    try:
        s = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return {}
    return {'bmashup.' + n: int(v) for n, v in re.findall(r'\bT\("([a-z0-9_]+)",\s*(\d+)\s*,', s)}


def kit_identity(kit):
    """-> identity dict (None when KIT is not a folder). Content-based: a copy of the same kit has the same id."""
    if not kit or not os.path.isdir(kit):
        return None
    kit = os.path.abspath(kit)
    man_p = os.path.join(kit, 'MANIFEST.json')
    key = (os.path.normcase(kit), os.path.getmtime(man_p) if os.path.isfile(man_p) else 0,
           os.path.getmtime(os.path.join(kit, TABLE)) if os.path.isfile(os.path.join(kit, TABLE)) else 0)
    sdk, nsdk = _tree_digest(kit, SDK_PARTS)
    if key in _cache and _cache[key]['sdk_sha256'] == sdk:
        return dict(_cache[key])
    man, man_sha = {}, None
    if os.path.isfile(man_p):
        man_sha = sha256_file(man_p)
        try:
            man = json.load(open(man_p, encoding='utf-8'))
        except ValueError:
            man = {}
    m = re.match(r'bmashup-modkit-(\d+\.\d+\.\d+)', os.path.basename(kit))
    version = man.get('kit') or (m.group(1) if m else None)
    ref = {}
    rh = os.path.join(kit, 'tools', 'reference_host.json')
    if os.path.isfile(rh):
        try:
            ref = json.load(open(rh, encoding='utf-8'))
        except ValueError:
            ref = {}
    ref = dict(ref, **(man.get('reference_host') or {}))           # MANIFEST.json (hashed into the id) wins
    plat, services = parse_table(os.path.join(kit, TABLE))
    ident = {'schema': SCHEMA, 'id': 'kit-%s+%s' % (version or 'unknown', (man_sha or sdk)[:12]), 'version': version,
             'path': kit, 'manifest_sha256': man_sha, 'sdk_sha256': sdk, 'sdk_files': nsdk,
             'sdk_version': (man.get('tools') or {}).get('sdk'),
             'reference_host': {k: ref.get(k) for k in ('name', 'exe', 'identity', 'platform', 'sha256') if ref.get(k)},
             'platform': plat, 'services': services, 'tables': parse_tables(os.path.join(kit, TABLE))}
    _cache[key] = ident
    return dict(ident)


def short(ident):
    if not ident:
        return '(no kit)'
    r = ident.get('reference_host') or {}
    return '%s (kit %s, SDK %s; reference host %s %s, platform %s, %d services)' % (
        ident['id'], ident.get('version'), ident.get('sdk_version'), r.get('name', '?'), r.get('identity', '?'),
        ident.get('platform'), len(ident.get('services') or {}))


def same(a, b):
    return bool(a and b and a.get('id') == b.get('id') and a.get('sdk_sha256') == b.get('sdk_sha256'))


def stamp(ident):
    """the part of an identity that is recorded in projects / packages / profiles"""
    return {k: ident.get(k) for k in ('schema', 'id', 'version', 'path', 'manifest_sha256', 'sdk_sha256', 'sdk_version',
                                      'reference_host', 'platform')} if ident else None


def diff(a, b):
    """-> lines saying how kit identity a differs from b ([] = same)"""
    if same(a, b):
        return []
    if not a or not b:
        return ['kit %s -> %s' % ((a or {}).get('id'), (b or {}).get('id'))]
    out = ['kit %s -> %s' % (a.get('id'), b.get('id'))]
    for k, lab in (('version', 'kit version'), ('sdk_version', 'SDK version'), ('manifest_sha256', 'MANIFEST.json'),
                   ('sdk_sha256', 'SDK headers / CMake files'), ('platform', 'reference platform')):
        if a.get(k) != b.get(k):
            out.append('  %s: %s -> %s' % (lab, str(a.get(k))[:16], str(b.get(k))[:16]))
    ra, rb = (a.get('reference_host') or {}), (b.get('reference_host') or {})
    if ra.get('sha256') != rb.get('sha256'):
        out.append('  reference host: %s %s -> %s %s' % (ra.get('name'), ra.get('identity'), rb.get('name'), rb.get('identity')))
    return out


# ------------------------------------------------------------------------------------------------------ hosts
def host_identity(exe):
    """-> {path, sha256, size, build_identity, platform, sdl2} (read only); None when EXE is not a file"""
    if not exe or not os.path.isfile(exe):
        return None
    exe = os.path.abspath(exe)
    with open(exe, 'rb') as f:
        data = f.read()
    ids = sorted({m.group(0).decode() for m in BUILD_ID_RE.finditer(data)})
    return {'path': exe, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
            'build_identity': ids[0] if len(ids) == 1 else None, 'build_identities_found': ids,
            'platform': ids[0][4:].split('+')[0] if len(ids) == 1 else None,
            'sdl2': os.path.isfile(os.path.join(os.path.dirname(exe), 'SDL2.dll'))}


def describe_host(host, kits):
    """-> (kit identity describing this exact host or None, why). A kit describes a host when its reference host sha256 is
    the host's sha256 AND the kit ships the platform table (the offered services)."""
    for k in kits:
        if not k:
            continue
        r = k.get('reference_host') or {}
        if host and r.get('sha256') == host['sha256']:
            if not k.get('services'):
                return None, 'kit %s names this host but has no service table (%s)' % (k['id'], TABLE)
            return k, 'reference host of %s' % k['id']
    return None, ('no known kit describes this host (sha256 %s, build %s): its services are unknown. Known: %s' % (
        host['sha256'][:12], host.get('build_identity'), ', '.join('%s = %s %s' % (k['id'], (k.get('reference_host') or {}).get('name'),
                                                                                  ((k.get('reference_host') or {}).get('sha256') or '')[:12])
                                                                  for k in kits if k) or 'none'))


def requirements(mod_toml):
    """mod.toml -> ({platform, requires [(service, min)], api, windows, raw_requires}, problems)"""
    try:
        t = tomllib.loads(open(mod_toml, encoding='utf-8').read())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, ['mod.toml: %s' % e]
    bm = t.get('bmashup') if isinstance(t.get('bmashup'), dict) else {}
    pl = t.get('plugin') if isinstance(t.get('plugin'), dict) else {}
    bad, req = [], []
    raw = bm.get('requires', [])
    if not isinstance(raw, list):
        bad.append('[bmashup] requires must be a list')
        raw = []
    for x in raw:
        m = REQ_RE.match(x) if isinstance(x, str) else None
        if not m:
            bad.append('[bmashup] requires entry %r: expected "service>=N"' % (x,))
        else:
            req.append((m.group(1), int(m.group(2))))
    plat = bm.get('platform')
    if plat is not None and not (isinstance(plat, str) and PLAT_RE.match(plat)):
        bad.append('[bmashup] platform %r: the Workbench checks ">=X.Y[.Z]" only' % (plat,))
    rm = bm.get('requires_mods', [])                               # v0.7: shown only; the host's admission decides (bmpack)
    return {'id': t.get('id'), 'version': t.get('version'), 'name': t.get('name'), 'platform': plat, 'requires': req,
            'raw_requires': raw, 'requires_mods': rm if isinstance(rm, list) else [repr(rm)],
            'has_plugin': isinstance(t.get('plugin'), dict), 'api': pl.get('api'), 'windows': pl.get('windows')}, bad


def compat_problems(req, platform, services, plugin=True, tables=None):
    """requirements vs a host's platform version + offered capabilities -> problems ([] = compatible). plugin=False (v0.7): a
    data-only mod has no [plugin] table, so no plugin API is needed. tables (v0.7): the [bmashup.<table>] readers, which
    `requires` may name as well as services."""
    out = []
    services = dict(tables or {}, **(services or {}))
    if plugin and req.get('api') != 1:
        out.append('[plugin] api %r: hosts offer plugin API 1' % (req.get('api'),))
    if req.get('platform'):
        need = vtuple(PLAT_RE.match(req['platform']).group(1)) if PLAT_RE.match(req['platform']) else None
        have = vtuple(platform)
        if not need or not have or have < need:
            out.append('needs platform %s; this host is platform %s' % (req['platform'], platform))
    for svc, v in req.get('requires') or []:
        if svc not in services:
            out.append('needs %s >= %d; this host (platform %s) does not offer %s' % (svc, v, platform, svc))
        elif services[svc] < v:
            out.append('needs %s >= %d; this host (platform %s) offers version %d' % (svc, v, platform, services[svc]))
    return out


def main(argv):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import wb_core as core
    if argv[:1] == ['identity']:
        kit = argv[1] if len(argv) > 1 else core.load_config().get('kit')
        i = kit_identity(kit)
        print(json.dumps(i, indent=1) if i else 'not a folder: %s' % kit)
        return 0 if i else 3
    if argv[:1] == ['host'] and len(argv) > 1:
        kits = [argv[i + 1] for i, a in enumerate(argv) if a == '--kit' and i + 1 < len(argv)] or [core.load_config().get('kit')]
        h = host_identity(argv[1])
        if not h:
            print('not a file: %s' % argv[1])
            return 3
        k, why = describe_host(h, [kit_identity(x) for x in kits])
        h['described_by'] = k['id'] if k else None
        h['why'] = why
        h['services'] = k['services'] if k else None
        print(json.dumps(h, indent=1))
        return 0 if k else 3
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
