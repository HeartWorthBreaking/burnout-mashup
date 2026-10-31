"""bmpack - build and validate Burnout Mashup content mods (added tracks, regions, World Tour events) from one declarative
spec. Research tooling of the platform phase (platform\\content\\CONTENT_REPORT.md s2); this is the mod kit 0.1.0 copy
(platform\\kit\\bmashup-modkit-0.1.0\\tools\\bmpack, KIT_REPORT.md), for the platform host p2 (platform 0.1.0). No game is launched, no
git, no network; donor data is read from YOUR game data (read only) and stays local (never upload a built mod).

Mod kit changes (bmpack 1.1): validate also runs the platform gate (bo3_manifest_platform_check) where the host runs it,
so it refuses what host p2 (and p1) refuses (service "platform": that mod alone, the game would start without it); the default host
tree is platform\\host2\\tree_p2 (BMPACK_TREE overrides); the checker cache folder is BMPACK_CACHE (default _build beside
this file) and its key includes the tree's *.inc files; verify resolves the mod folder once, refuses a manifest entry that
is not a relative path inside the mod (an absolute or drive path, "..", a backslash), and reports a folder without
bmpack.json (e.g. a mod SET folder) instead of a traceback.

bmpack 1.2 (platform host p3, platform 0.1.1; host3\\tools\\bmpack, BMPACK_1_2_PATCH_NOTE.md): the default tree is
platform\\host3\\tree_p3; validate runs the host's two-phase admission (bm_admit.c) where modfs.c runs it: the LATER mod of a
cross-mod clash is refused alone (service "admission", the game starts without it, both mods named); [[event]] takes
name / help (-> [bmashup.extra_events] version 2 names / help) and validate shows each event's list row and help-bar text
as the game resolves them (the text table installed over Data\\Globalus.bin); new spec tables [tune] set and [capacity]
(-> [bmashup.tune] / [bmashup.capacity] version 1); validate shows the host's gameplay label. Specs without these keys
build byte-identical mods to 1.1. BMPACK_MUT=11 (tests only): the checker skips the admission (p2's behaviour).

bmpack 1.3 (gp slice deps1, platform 0.1.2; gp\\slices\\deps1\\tools\\bmpack, BMPACK_1_3_PATCH_NOTE.md): the default tree is
gp\\slices\\deps1\\tree; [mod] takes platform (">=X.Y[.Z]"), requires (capabilities: services / tables, "name>=N") and
requires_mods (other mods: "<mod id>" or "<mod id> >= X.Y[.Z]") -> the generated [bmashup] table; validate puts the mods in the
host's dependency order (bo3_admit_order) and runs the dependency rules with the admission (service "admission", kinds
"needs a mod" / "dependency cycle"); the admission reason is kept as the game keeps it (up to 699 characters). Specs without
these keys build byte-identical mods to 1.2.

bmpack 1.3.4 (mod kit 0.4.1, portable): no developer-workspace path. validate compiles the p4.4 host's readers from the kit's
host-readers SOURCE package (tools\\bmpack\\host_readers, HOST_READERS.json; no generated game code: the game's PrgData relocation
is re-implemented in checker\\bmpack_check.c and differentially tested against the original); the C compiler is llvm-mingw clang
found by --cc / BMKIT_CC / BMKIT_LLVM_MINGW / bmkit.toml / PATH; YOUR game data (NTSC-U) by --game-data / BMKIT_GAME_DATA /
bmkit.toml (tools\\_lib\\bmkit_env.py). A missing prerequisite stops with exit 3 and a message saying what to install or give.
The checker cache is --cache DIR / BMPACK_CACHE (default: a "_bmpack_cache" folder in the current directory). Outputs of build
are byte-identical to 1.3.3 (only the validate text names the host-readers package instead of a tree).

    py -3 -B bmpack.py build SPEC.toml OUT_SET --game-data DIR [--with ROOT ...] [--no-validate] [--cc FILE] [--cache DIR]
    py -3 -B bmpack.py validate ROOT [ROOT ...] --game-data DIR [--json] [--cc FILE] [--cache DIR]
    py -3 -B bmpack.py verify MOD_DIR

build     writes OUT_SET\\<folder> (refused if it exists): mod.toml, files\\Tracks\\RR\\NN_VN\\* (every file of the donor's
          folder, byte for byte, except Gamedata.bgd's documented ID fields), bmpack.json (the manifest: spec hash, every
          file's sha256 and size, the donor's hashes, each renamed field). The output is a function of the spec and the donor
          bytes only: two builds are byte-identical. The built mod is validated (as `validate`, the mod alone plus --with
          roots) before it is moved into place; a refused mod is not written.
validate  runs the host's REAL parsers and rules (the tree's modmanifest.c, bm_tracks.c, bm_regions.c, bm_names.c,
          bm_wtour.c, bm_xevents.c compiled with the game's own PrgData relocation code; checker\\bmpack_check.c) over the
          mods as the game would load them: each ROOT is a mod set folder (its subfolders holding a mod.toml) or one mod folder,
          in TAKEDAWN_MODS order; within a root the loader orders by manifest id; a shared id disables every copy. Exit 0 =
          every declaration accepted, 1 = refusals (each named with its service and the host's own reason).
verify    recomputes a built mod's hashes against its bmpack.json.

Spec (TOML):
    [mod]                     id (modfs rule: [a-z0-9] then [a-z0-9._-], <= 64), version, name, description (optional),
                              folder (optional; default: the id's last dot-separated part)
    [[region]]                letter (A-Z, not U / E / A), text (1..17: A-Z a-z 0-9 space - ' . &), dj (DJUS / DJEU / DJAS)
    [[track]]                 id (RR_NN_VN, base-40), donor (a retail track, e.g. US_C1_V1), name (<= 27), location
                              (<= 17), point_to_point (bool, default false)
    [[event]]                 id ([A-Za-z0-9_-], 1..32), track, location (a World Tour race location, e.g. US_C3),
                              stage (optional retail race ID, 12 characters), type (optional, "race")
Gamedata.bgd rule (the CC1 / G8 / TL fixture builders' rule, unchanged): in the per-event records (0x3000 .. 0x3800 + 0x800 *
64, 8-byte aligned) an 8-byte field equal to the donor's base-40 track ID becomes the new ID, and a 12-character race ID
ending in the donor's compact ID gets the new compact ID; every other byte (the header included) is the donor's.
BMPACK_MUT=n (tests only) compiles one deliberate defect into this tool (tests\\test_bmpack.py)."""
import hashlib, json, os, pathlib, re, shutil, struct, subprocess, sys, tomllib

VERSION = '1'           # the bmpack.json / generated mod.toml format (unchanged: outputs stay byte-identical)
TOOL_VERSION = '1.5.0'  # 1.5.0 (mod kit 0.7.0): main19 readers (platform 0.1.9); 1.4.0 (mod kit 0.5.0): main18 readers, the loader's mod cap; 1.3: gp deps1 host (platform 0.1.2); 1.3.1 / 1.3.2: p4.2 / p4.3 copies; 1.3.3 (mod kit 0.4.0): world_tour;
#                         1.3.4 (mod kit 0.4.1): portable (host-readers package, explicit game data / compiler, no generated code)
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / '_lib'))
import bmkit_env  # noqa: E402  (the kit's configuration / prerequisite module)

MUT = int(os.environ.get('BMPACK_MUT', '0') or 0)
B40 = ' -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'
# set by configure() (or main's options): the user's game data, the compiler, the checker cache, the host-readers package
_CFG = {'game_data': None, 'cc': None, 'cache': None, 'host_readers': None}
NEED_BUILD = ('Tracks/tlist.bin',)
NEED_VALIDATE = ('Tracks/tlist.bin', 'Data/PrgData.bin', 'Data/stagehed.bin', 'Data/Globalus.bin')


def configure(game_data=None, cc=None, cache=None, host_readers=None):
    """set the explicit configuration (a value None = resolve later through bmkit_env: env / bmkit.toml / PATH)"""
    _CFG.update(game_data=game_data, cc=cc, cache=cache, host_readers=host_readers)


def _game(need, what):
    return pathlib.Path(bmkit_env.game_data(_CFG['game_data'], need=need, what=what))


def _hr():
    return pathlib.Path(bmkit_env.host_readers(_CFG['host_readers']))


def _cache():
    return pathlib.Path(_CFG['cache'] or os.environ.get('BMPACK_CACHE', '') or (pathlib.Path.cwd() / '_bmpack_cache'))


HOST = ['modmanifest.c', 'bm_admit.c', 'bm_tracks_progress.c', 'bm_tracks.c', 'bm_regions.c', 'bm_names.c', 'bm_wtour.c', 'bm_xevents.c',
        'bm_progress.c', 'bm_progress_io.c', 'bm_guest.c']
# 1.3.1: bm_wtour.c calls bm_wt4.c in hosts with wt4 (platform 0.1.5); 1.3.2: bm_admit.c includes fetex1's parser and calls
# bm_fetex.c (platform 0.1.6): linked when the host-readers package has them. 1.3.3: with wt4 the checker parses every usable
# mod's [bmashup.world_tour] with the host's own reader BEFORE the World Tour events (as the game does).
OPTIONAL_HOST = ['bm_wt4.c', 'bm_fetex.c']


class BmpackError(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------- base-40 IDs
def enc(s):
    if not 0 < len(s) <= 12 or any(c not in B40 for c in s):
        raise BmpackError('%r is not a base-40 ID (characters %s, at most 12)' % (s, B40.strip()))
    v = 0
    for c in s.ljust(12):
        v = v * 40 + B40.index(c)
    return v


def dec(v):
    s = ''
    for _ in range(12):
        s = B40[v % 40] + s
        v //= 40
    return s.rstrip()


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------------------- the spec
SPEC_KEYS = {'mod': {'id', 'version', 'name', 'description', 'folder', 'platform', 'requires', 'requires_mods'},
             'region': {'letter', 'text', 'dj'},
             'track': {'id', 'donor', 'name', 'location', 'point_to_point'},
             'event': {'id', 'track', 'location', 'stage', 'type', 'name', 'help'},
             'tune': {'set'},
             'capacity': {'lanes', 'low_unit_bytes', 'static_bytes'}}
SINGLE = ('mod', 'tune', 'capacity')     # 1.2: one table each; region / track / event are arrays of tables


def load_spec(path):
    """the spec's structure (keys and types); the CONTENT rules are the host's, checked by validate"""
    raw = pathlib.Path(path).read_bytes()
    try:
        s = tomllib.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise BmpackError('spec %s: not TOML: %s' % (path, e))
    for k in s:
        if k not in SPEC_KEYS:
            raise BmpackError('spec: unknown table [%s] (tables: mod, [[region]], [[track]], [[event]], tune, capacity)' % k)
    if not isinstance(s.get('mod'), dict):
        raise BmpackError('spec: [mod] is missing')
    for tab, keys in SPEC_KEYS.items():
        if tab in SINGLE and tab in s and not isinstance(s[tab], dict):
            raise BmpackError('spec: %s must be a table ([%s])' % (tab, tab))
        items = ([s[tab]] if tab in s else []) if tab in SINGLE else s.get(tab, [])
        if tab not in SINGLE and not isinstance(items, list):
            raise BmpackError('spec: %s must be an array of tables ([[%s]])' % (tab, tab))
        for i, it in enumerate(items):
            where = '[%s]' % tab if tab in SINGLE else '[[%s]] #%d' % (tab, i + 1)
            for k, v in it.items():
                if k not in keys:
                    raise BmpackError('spec %s: unknown key %r (keys: %s)' % (where, k, ', '.join(sorted(keys))))
                if tab == 'mod' and k in ('requires', 'requires_mods'):   # 1.3
                    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                        raise BmpackError('spec [mod]: %s must be a list of strings' % k)
                elif k == 'point_to_point':
                    if not isinstance(v, bool):
                        raise BmpackError('spec %s: point_to_point must be true / false' % where)
                elif tab == 'tune':
                    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                        raise BmpackError('spec [tune]: set must be a list of "Group | Name = value" strings')
                elif tab == 'capacity':
                    if not isinstance(v, int) or isinstance(v, bool):
                        raise BmpackError('spec [capacity]: %s must be a whole number' % k)
                elif not isinstance(v, str):
                    raise BmpackError('spec %s: %s must be a string' % (where, k))
    m = s['mod']
    for k in ('id', 'version', 'name'):
        if not m.get(k):
            raise BmpackError('spec [mod]: %s is required' % k)
    for i, t in enumerate(s.get('track', [])):
        for k in ('id', 'donor'):
            if not t.get(k):
                raise BmpackError('spec [[track]] #%d: %s is required' % (i + 1, k))
    for i, e in enumerate(s.get('event', [])):
        for k in ('id', 'track', 'location'):
            if not e.get(k):
                raise BmpackError('spec [[event]] #%d: %s is required' % (i + 1, k))
    for i, r in enumerate(s.get('region', [])):
        for k in ('letter', 'text'):
            if not r.get(k):
                raise BmpackError('spec [[region]] #%d: %s is required' % (i + 1, k))
    folder = m.get('folder') or m['id'].split('.')[-1]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', folder):
        raise BmpackError('spec [mod]: folder %r is not a folder name ([A-Za-z0-9._-])' % folder)
    s['_folder'] = folder
    s['_sha256'] = hashlib.sha256(raw).hexdigest()
    s['_name'] = pathlib.Path(path).name
    return s


def q(s):
    if any(c in s for c in '"\\\n\r'):
        raise BmpackError('%r: quotes, backslashes and line breaks cannot be written into mod.toml' % s)
    return '"%s"' % s


def mod_toml(s):
    m = s['mod']
    L = ['# generated by bmpack %s from %s (sha256 %s); research content: retail data reused under new IDs,' % (
        VERSION, s['_name'], s['_sha256'][:16]),
         '# local only, never upload.',
         'id = %s' % q(m['id']), 'name = %s' % q(m['name']), 'version = %s' % q(m['version'])]
    if m.get('description'):
        L.append('description = %s' % q(m['description']))
    L.append('')
    if m.get('platform') or m.get('requires') or m.get('requires_mods'):    # 1.3: the [bmashup] table (absent: 1.2's bytes)
        L.append('[bmashup]')
        if m.get('platform'):
            L.append('platform = %s' % q(m['platform']))
        for k in ('requires', 'requires_mods'):
            if m.get(k) and not (MUT == 12 and k == 'requires_mods'):
                L.append('%s = [%s]' % (k, ', '.join(q(x) for x in m[k])))
        L.append('')
    regs = s.get('region', [])
    if regs:
        L += ['[bmashup.regions]', 'version = 1', 'add = [%s]' % ', '.join(q('%s = %s' % (r['letter'], r['text'])) for r in regs)]
        dj = [r for r in regs if r.get('dj')]
        if dj:
            L.append('dj = [%s]' % ', '.join(q('%s = %s' % (r['letter'], r['dj'])) for r in dj))
        L.append('')
    trs = s.get('track', [])
    if trs:
        L += ['[bmashup.tracks]', 'version = 1', 'add = [%s]' % ', '.join(q(t['id']) for t in trs)]
        p2p = [t['id'] for t in trs if t.get('point_to_point')]
        if p2p:
            L.append('point_to_point = [%s]' % ', '.join(q(i) for i in p2p))
        nm = [t for t in trs if t.get('name')]
        if nm and MUT != 6:
            L.append('names = [%s]' % ', '.join(q('%s = %s' % (t['id'], t['name'])) for t in nm))
        lo = [t for t in trs if t.get('location')]
        if lo:
            L.append('locations = [%s]' % ', '.join(q('%s = %s' % (t['id'], t['location'])) for t in lo))
        L.append('')
    evs = s.get('event', [])
    if evs:
        v2 = any(e.get('name') or e.get('help') for e in evs)   # 1.2: names / help need version 2
        L += ['[bmashup.extra_events]', 'version = %d' % (2 if v2 else 1),
              'add = [%s]' % ', '.join(q('%s = %s @ %s%s' % (e['id'], e['track'], e['location'],
                                                            ' : %s' % e['type'] if e.get('type') else '')) for e in evs)]
        st = [e for e in evs if e.get('stage')]
        if st and MUT != 7:
            L.append('stage = [%s]' % ', '.join(q('%s = %s' % (e['id'], e['stage'])) for e in st))
        for k in ('name', 'help'):
            nh = [e for e in evs if e.get(k)]
            if nh:
                L.append('%s = [%s]' % ('names' if k == 'name' else 'help', ', '.join(q('%s = %s' % (e['id'], e[k])) for e in nh)))
        L.append('')
    tu = s.get('tune')
    if tu:
        L += ['[bmashup.tune]', 'version = 1', 'set = [%s]' % ', '.join(q(x) for x in tu.get('set', [])), '']
    ca = s.get('capacity')
    if ca:
        L += ['[bmashup.capacity]', 'version = 1'] + ['%s = %d' % (k, ca[k]) for k in ('lanes', 'low_unit_bytes', 'static_bytes')
                                                       if k in ca] + ['']
    return '\n'.join(L)


# ---------------------------------------------------------------------------------------------------------- donor copy
def track_dir(tid):
    if not re.fullmatch(r'[A-Z0-9]{2}_[A-Z0-9]{2}_[A-Z0-9]{2}', tid):
        raise BmpackError('track %r is not RR_NN_VN (A-Z 0-9; the folder Tracks\\RR\\NN_VN is cut from it)' % tid)
    return pathlib.Path('Tracks') / tid[:2] / tid[3:]


def rename_gamedata(gd, donor, new):
    """the documented rule; returns the list of renamed fields"""
    old_id, new_id = enc(donor), enc(new)
    oc, nc = donor.replace('_', ''), new.replace('_', '')
    changed = []
    lo = 0x3000 if MUT != 2 else 0x8               # MUT 2: the header's keys renamed too (outside the documented fields)
    for o in range(lo, min(len(gd), 0x3800 + 0x800 * 64), 8):
        v = struct.unpack_from('<Q', gd, o)[0]
        if v == old_id:
            struct.pack_into('<Q', gd, o, new_id)
            changed.append({'offset': '0x%X' % o, 'from': donor, 'to': new})
        elif v and v < 40 ** 12:
            s = dec(v)
            if len(s) == 12 and s.endswith(oc):
                ns = s[:6] + nc
                struct.pack_into('<Q', gd, o, enc(ns))
                changed.append({'offset': '0x%X' % o, 'from': s, 'to': ns})
    return changed


def copy_track(t, mod_dir):
    track_dir(t['id']), track_dir(t['donor'])          # 1.3.4: the spec's IDs are checked before the game data is needed
    game = _game(NEED_BUILD, 'bmpack build (donor track %s)' % t['donor'])
    src = game / track_dir(t['donor'])
    if not src.is_dir() or not (src / 'Gamedata.bgd').is_file():
        raise BmpackError('track %s: donor %s has no folder %s in your game data (a retail track ID such as US_C1_V1 is '
                          'expected)' % (t['id'], t['donor'], src))
    dst = mod_dir / 'files' / track_dir(t['id'])
    dst.mkdir(parents=True)
    rec = {'id': t['id'], 'donor': t['donor'], 'donor_folder': track_dir(t['donor']).as_posix(), 'donor_files': {}, 'renamed': []}
    for f in sorted(src.iterdir(), key=lambda p: p.name):
        if not f.is_file() or (MUT == 5 and f.name == 'enviro.dat'):
            continue
        rec['donor_files'][f.name] = {'sha256': sha(f), 'size': f.stat().st_size}
        if f.name == 'Gamedata.bgd':
            gd = bytearray(f.read_bytes())
            rec['renamed'] = rename_gamedata(gd, t['donor'], t['id'])
            (dst / f.name).write_bytes(bytes(gd))
        else:
            shutil.copyfile(f, dst / f.name)
    # self check: every other file = the donor's bytes; Gamedata differs only inside the renamed fields, each reads its value
    allowed = set()
    gd_new = (dst / 'Gamedata.bgd').read_bytes()
    for ch in rec['renamed']:
        o = int(ch['offset'], 16)
        allowed.update(range(o, o + 8))
        if dec(struct.unpack_from('<Q', gd_new, o)[0]) != ch['to']:
            raise BmpackError('track %s: Gamedata field %s does not read %s' % (t['id'], ch['offset'], ch['to']))
    gd_old = (src / 'Gamedata.bgd').read_bytes()
    if MUT != 2:
        if len(gd_old) != len(gd_new) or any(gd_old[i] != gd_new[i] for i in range(len(gd_old)) if i not in allowed):
            raise BmpackError('track %s: Gamedata differs from the donor outside the renamed fields' % t['id'])
    for name, d in rec['donor_files'].items():
        if name != 'Gamedata.bgd' and sha(dst / name) != d['sha256']:
            raise BmpackError('track %s: %s differs from the donor' % (t['id'], name))
    if not rec['renamed']:
        raise BmpackError('track %s: no Gamedata field of donor %s was renamed (not a track folder of the expected layout)' % (
            t['id'], t['donor']))
    return rec


def manifest(s, mod_dir, tracks):
    files = {}
    for p in sorted(mod_dir.rglob('*'), key=lambda p: p.relative_to(mod_dir).as_posix()):
        if p.is_file() and p.name != 'bmpack.json':
            files[p.relative_to(mod_dir).as_posix()] = {'sha256': sha(p), 'size': p.stat().st_size}
    j = {'bmpack': VERSION, 'spec': {'file': s['_name'], 'sha256': s['_sha256']},
         'mod': {k: s['mod'][k] for k in ('id', 'version', 'name', 'platform', 'requires', 'requires_mods') if k in s['mod']},
         'folder': s['_folder'],
         'tracks': tracks, 'regions': s.get('region', []), 'events': s.get('event', []), 'files': files,
         'gamedata_rule': 'per-event records 0x3000 .. 0x3800 + 0x800 * 64 (8-byte aligned): the donor track ID and race IDs '
                          'ending in the donor compact ID renamed; every other byte the donor\'s'}
    if MUT == 1:
        import time
        j['built_at'] = time.time()                 # MUT 1: a timestamp (not reproducible)
    return json.dumps(j, indent=1, sort_keys=True, ensure_ascii=True) + '\n'


def build(spec_path, out_set, with_roots=(), do_validate=True):
    s = load_spec(spec_path)
    out_set = pathlib.Path(out_set)
    out = out_set / s['_folder']
    stage = out_set / (s['_folder'] + '.bmpack-tmp')
    if (out.exists() and MUT != 8) or stage.exists():
        raise BmpackError('%s exists: bmpack never overwrites a mod (remove it or choose another OUT_SET)' % (
            out if out.exists() else stage))
    text = mod_toml(s)
    if MUT == 8 and out.exists():
        shutil.rmtree(out)
    stage.mkdir(parents=True)
    try:
        (stage / 'mod.toml').write_bytes(text.encode('utf-8'))
        tracks = [copy_track(t, stage) for t in s.get('track', [])]
        (stage / 'bmpack.json').write_bytes(manifest(s, stage, tracks).encode('utf-8'))
        if do_validate:
            rep = validate([stage] + [pathlib.Path(r) for r in with_roots])
            if not rep['ok']:
                raise BmpackError('the host refuses the built mod:\n' + format_refusals(rep))
        stage.rename(out)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return out


def _inside(rel):
    """a manifest key is a relative POSIX path inside the mod: no drive / root, no '..', no backslash (pathlib would join an
    absolute key by DROPPING the mod folder, so verify would read a file outside the mod)"""
    if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel or rel.startswith('/'):
        return False
    parts = rel.split('/')
    return all(x not in ('', '.', '..') for x in parts)


def verify(mod_dir):
    mod_dir = pathlib.Path(mod_dir)
    if MUT != 10:
        mod_dir = mod_dir.resolve()                 # one absolute form for every join and relative_to below
        if not mod_dir.is_dir():
            raise BmpackError('%s is not a folder' % mod_dir)
        if not (mod_dir / 'bmpack.json').is_file():
            subs = sorted(d.name for d in mod_dir.iterdir() if d.is_dir() and (d / 'bmpack.json').is_file())
            raise BmpackError('%s has no bmpack.json (not a mod built by bmpack)%s' % (
                mod_dir, '; it holds built mods - verify each: %s' % ', '.join(subs) if subs else ''))
    try:
        j = json.loads((mod_dir / 'bmpack.json').read_text(encoding='utf-8'))
        files = j['files']
        assert isinstance(files, dict)
    except (ValueError, KeyError, AssertionError) as e:
        raise BmpackError('%s: bmpack.json is not a bmpack manifest (%s)' % (mod_dir, e))
    bad = []
    have = {p.relative_to(mod_dir).as_posix() for p in mod_dir.rglob('*') if p.is_file() and p.name != 'bmpack.json'}
    for rel, d in files.items():
        if MUT != 10 and not _inside(rel):
            bad.append('not a relative path inside the mod: %s' % rel)
            continue
        p = mod_dir / rel
        if not p.is_file():
            bad.append('missing %s' % rel)
        elif sha(p) != d['sha256']:
            bad.append('changed %s' % rel)
    bad += ['not in the manifest: %s' % r for r in sorted(have - set(files))]
    return bad


# ---------------------------------------------------------------------------------------------------------- the checker
def _hr_sources(hr):
    """-> (game dir, recomp_cfg.c, host .c list, every header / .inc) of the host-readers package"""
    game = hr / 'src' / 'game'
    cfg_c = hr / 'xboxrecomp' / 'src' / 'enhance' / 'recomp_cfg.c'
    host = [game / h for h in HOST] + [game / h for h in OPTIONAL_HOST if (game / h).is_file()]
    missing = [str(p) for p in [cfg_c] + host if not p.is_file()]
    if missing:
        raise BmpackError('the host-readers package %s is incomplete (missing %s): unpack the kit zip again' % (hr, ', '.join(missing)))
    hdrs = sorted(game.glob('*.h')) + sorted(game.glob('*.inc')) + sorted(cfg_c.parent.glob('*.h'))
    return game, cfg_c, host, hdrs


def _checker():
    hr = _hr()
    cc = pathlib.Path(bmkit_env.find_cc(_CFG['cc'], what='bmpack validate (it compiles the host readers)'))
    game, cfg_c, host, hdrs = _hr_sources(hr)
    wt4 = (game / 'bm_wt4.c').is_file()
    if not (game / 'bm_platform_gate.inc').is_file() and MUT != 9:
        raise BmpackError('the host-readers package %s has no platform gate (bm_platform_gate.inc): not a platform host\'s readers' % hr)
    srcs = [HERE / 'checker' / 'bmpack_check.c', cfg_c] + host + hdrs
    h = hashlib.sha256(str(cc).encode() + b'hr1.5.0' + (b'mut%d' % MUT if MUT in (9, 11, 13, 14) else b'') + b'wt4v1')
    for p in srcs:
        h.update(p.name.encode() + b'\0' + p.read_bytes())
    d = _cache() / h.hexdigest()[:16]
    exe = d / 'bmpack_check.exe'
    if exe.is_file():
        return exe
    tmp = d.with_name(d.name + '.tmp%d' % os.getpid())
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        tmp.mkdir(parents=True)
    except OSError as e:
        raise BmpackError('cannot create the checker cache folder %s (%s): give a writable --cache DIR' % (tmp, e))
    inc = ['-I' + str(game), '-I' + str(cfg_c.parent)]
    log = []

    def run(cmd):
        try:
            r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        except OSError as e:
            raise bmkit_env.BmkitError('cannot run %s (%s): check the llvm-mingw installation' % (cmd[0], e))
        log.append(' '.join(str(c) for c in cmd) + '\n' + r.stdout + r.stderr)
        if r.returncode:
            (tmp / 'build.log').write_text('\n'.join(log), encoding='utf-8')
            raise BmpackError('building the checker failed (%s); see %s. Is %s llvm-mingw 20260922 (or compatible)?'
                              % (pathlib.Path(str(cmd[-1])).name, tmp / 'build.log', cc))
    objs = []
    for src in [HERE / 'checker' / 'bmpack_check.c', cfg_c] + host:
        o = tmp / (src.stem + '.o')
        mut = ['-DBMPACK_MUT=%d' % MUT] if MUT in (9, 11, 13, 14) and src.name == 'bmpack_check.c' else []
        if wt4 and src.name == 'bmpack_check.c':
            mut.append('-DBMPACK_WT4=1')
        run([cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-c'] + mut + inc + [src, '-o', o])
        objs.append(o)
    run([cc] + objs + ['-o', tmp / 'bmpack_check.exe'])
    (tmp / 'build.log').write_text('\n'.join(log), encoding='utf-8')
    (tmp / 'inputs.json').write_text(json.dumps({'host_readers': str(hr), 'mut': MUT if MUT in (9, 11, 13, 14) else 0,
                                                 'sources': {p.name: sha(p) for p in srcs}}, indent=1), encoding='utf-8')
    try:
        tmp.rename(d)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)       # another process built it meanwhile
    return exe


def host_readers_id():
    """the host the shipped readers come from (HOST_READERS.json: identity / exe sha256)"""
    try:
        j = json.loads((_hr() / 'HOST_READERS.json').read_text(encoding='utf-8'))
        return '%s (exe %s)' % (j.get('host_identity', '?'), j.get('host_exe_sha256', '?')[:12])
    except (OSError, ValueError, bmkit_env.BmkitError):
        return '?'


def collect(roots):
    """(root index, mod folder) for every mod.toml under the roots, as modfs finds them"""
    out = []
    for i, r in enumerate(roots):
        r = pathlib.Path(r)
        if (r / 'mod.toml').is_file():
            out.append((i, r))
            continue
        if not r.is_dir():
            raise BmpackError('%s is not a folder' % r)
        n0 = len(out)
        for d in sorted(r.iterdir(), key=lambda p: p.name):
            if d.is_dir() and (d / 'mod.toml').is_file():
                out.append((i, d))
        if len(out) == n0:
            raise BmpackError('%s holds no mod (no mod.toml in it or in its subfolders)' % r)
    return out


def validate(roots):
    mods = collect(roots)
    if MUT == 4:
        mods = [(0, d) for _, d in sorted(mods, key=lambda x: x[1].name, reverse=True)]   # MUT 4: not the loader's order
    if MUT == 3:
        return {'ok': True, 'mods': [], 'refusals': [], 'events': [], 'added_tracks': [], 'regions': []}
    base = _game(NEED_VALIDATE, 'bmpack validate')
    exe = _checker()
    args = [exe, base / 'Tracks' / 'tlist.bin', base / 'default.xbe', base / 'Data' / 'PrgData.bin', base / 'Data' / 'stagehed.bin']
    pairs = [('ROOT=%d' % i, str(d.resolve())) for i, d in mods]
    if sum(len(a) + len(b) + 2 for a, b in pairs) > 16000:   # 1.4.0: past the command line's room (256+ mods)
        lf = _cache() / ('modlist_%d.txt' % os.getpid())
        lf.write_text(''.join('%s\t%s\n' % ab for ab in pairs), encoding='utf-8')
        args.append('@' + str(lf))
    else:
        for a, b in pairs:
            args += [a, b]
    env = dict(os.environ, BMPACK_LANG=str(base / 'Data' / 'Globalus.bin'))   # 1.2: the text table's install
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env)
    try:
        rep = json.loads(r.stdout)
    except ValueError:
        raise BmpackError('the checker failed (rc %d): %s %s' % (r.returncode, r.stdout[-400:], r.stderr[-400:]))
    if 'error' in rep:
        raise BmpackError('the checker: %s' % rep['error'])
    rep['rc'] = r.returncode
    return rep


def format_refusals(rep):
    return '\n'.join('  [%s] %s: %s' % (f['service'], f['mod'] or '-', f['why']) for f in rep['refusals'])


def summary(rep):
    L = ['mods (loader order%s): ' % (', dependency order: %d moved' % rep['dependency_moved'] if rep.get('dependency_moved')
                                      else '') + ', '.join('%s %s%s' % (m['id'] or m['dir'], m['version'], '' if m['usable'] else
                                                         ' (REFUSED ALONE by the platform gate)' if m.get('platform_refused') else
                                                         ' (REFUSED ALONE by the admission: %s)' % (m.get('needs') or
                                                         'a clash with an earlier mod') if m.get('admission_refused') else
                                                         ' (UNUSABLE)') for m in rep['mods']),
         'track list: %d entries (%d added)' % (rep['tlist_count'], len(rep['added_tracks'])),
         'host readers: %s (bmpack %s)' % (host_readers_id(), TOOL_VERSION)]
    for t in rep['added_tracks']:
        L.append('  track %s entry %d region %d%s name %s / %s' % (t['id'], t['entry'], t['region'], ' p2p' if t['p2p'] else '',
                                                                   t['name'], t['location']))
    for g in rep['regions']:
        L.append('  region %s = %s (code %d)' % (g['letter'], g['text'], g['code']))
    for e in rep['events']:
        L.append('  event %s: %s at %s, row %d (after %d retail), race ID %s, Gamedata record 0x%X%s' % (
            e['key'], e['track'], e['location'], e['row'], e['retail_rows'], e['race_id'], e['gamedata_record'],
            ' (alias %d)' % e['gamedata_alias'] if e['gamedata_alias'] else ''))
        L.append('    row text %r, help bar %r' % (e.get('row_text', ''), e.get('help_text', '')))
    for m in rep['mods']:
        if m.get('label'):
            L.append('  [MODS] %s %s %s' % (m['id'], m['version'], m['label']))
    L.append('RESULT %s' % ('ACCEPTED' if rep['ok'] else 'REFUSED\n' + format_refusals(rep)))
    return '\n'.join(L)


def _opt(argv, name):
    """remove `name VALUE` from argv -> VALUE (None when absent); a missing value is a usage error"""
    if name not in argv:
        return None
    i = argv.index(name)
    if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
        raise SystemExit('bmpack: %s needs a value (see bmpack.py with no arguments)' % name)
    v = argv[i + 1]
    del argv[i:i + 2]
    return v


def main(argv):
    argv = list(argv)
    try:
        bmkit_env.check_python()
        configure(game_data=_opt(argv, '--game-data'), cc=_opt(argv, '--cc'), cache=_opt(argv, '--cache'),
                  host_readers=_opt(argv, '--host-readers'))
    except SystemExit as e:
        print(e)
        return 2
    except bmkit_env.BmkitError as e:
        return bmkit_env.report_error('bmpack', e)
    if len(argv) < 2 or argv[0] not in ('build', 'validate', 'verify'):
        print(__doc__)
        return 2
    try:
        if argv[0] == 'build':
            rest = argv[1:]
            with_roots = [rest[i + 1] for i, a in enumerate(rest) if a == '--with' and i + 1 < len(rest)]
            pos = [a for i, a in enumerate(rest) if not a.startswith('--') and (i == 0 or rest[i - 1] != '--with')]
            if len(pos) != 2:
                print(__doc__)
                return 2
            out = build(pos[0], pos[1], with_roots, '--no-validate' not in rest)
            j = json.loads((out / 'bmpack.json').read_text(encoding='utf-8'))
            print('built %s (%d files, %d tracks, %d events); manifest %s' % (out, len(j['files']), len(j['tracks']),
                                                                             len(j['events']), out / 'bmpack.json'))
            return 0
        if argv[0] == 'validate':
            rep = validate([a for a in argv[1:] if not a.startswith('--')])
            print(json.dumps(rep, indent=1) if '--json' in argv else summary(rep))
            return 0 if rep['ok'] else 1
        bad = verify(argv[1])
        print('\n'.join(bad) if bad else 'OK: every file matches bmpack.json')
        return 1 if bad else 0
    except BmpackError as e:
        print('bmpack: REFUSED: %s' % e)
        return 1
    except bmkit_env.BmkitError as e:
        return bmkit_env.report_error('bmpack', e)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
