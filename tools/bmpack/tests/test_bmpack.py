"""bmpack tests (bmpack 1.2, host3; host tree p3 by default; from the mod kit 0.1.0 copy of platform\\content\\bmpack): reproducibility, donor integrity, round trip through the host's REAL parsers,
every refusal, limits, loader order, the manifest, and the tool's own mutants. No game; writes only OUT_DIR.
    py -3 -B test_bmpack.py OUT_DIR             base run + BMPACK_MUT 1..8 (each must fail a check); RESULTS.txt
    py -3 -B test_bmpack.py OUT_DIR --inner N   one configuration (used by the outer run)
Every bmpack call is a subprocess (`py -3 -B bmpack.py ...`) with BMPACK_MUT=N in its environment. Independent checks use
their own decoder (content_count\\scripts\\tlist.py, read only) and Python's tomllib, never bmpack's code.
Mod kit additions: T10 the platform gate (p2 = p1) in validate (a mod refused alone, with the host's reason), T11 verify with
absolute / relative / slash / trailing-separator / \\\\?\\ paths, a set folder, and manifest entries outside the mod;
MUT 9 (the gate not called) and MUT 10 (verify's old path handling). The checker cache goes to OUT_DIR\\checker_cache
(BMPACK_CACHE) so the tool's own folder is never written.
bmpack 1.2: T5 / T7 refusals of a later conflicting mod now come from the admission (refused alone); T10 platform 0.1.1 and a
version-3 table for 'needs a newer platform'; T12 names / help / tune / capacity + the label + 1.1 outputs unchanged; T13 the
admission (alone, state = without it, reversed order); MUT 11 (no admission).
bmpack 1.3 (gp deps1, platform 0.1.2): T10's version texts read 0.1.2 (by design, D3); T14 [mod] platform / requires /
requires_mods -> [bmashup], the dependency order, the dependency refusals (older, missing, cycle), the capability refusal
(bmashup.autopilot >= 2), the admission reason kept whole; MUT 12 (requires_mods left out of mod.toml), MUT 13 (the checker
does not apply the dependency order).
bmpack 1.3.3 (mod kit 0.4.0): T15 [bmashup.world_tour] in a tree with wt4 (p4.3's): the launched 4th-region mod (gp_wt4_set)
validates (ACCEPTED, both events resolved at the declared location); a location the events do not use and a world_tour
region no mod declares are refused; MUT 14 (the checker skips the world_tour parse: the old false events-resolve refusal).
bmpack 1.3.4 (mod kit 0.4.1, portable): no workspace. YOUR game data is given with --game-data DIR (or BMKIT_GAME_DATA /
bmkit.toml) and the compiler with --cc FILE (or BMKIT_CC / BMKIT_LLVM_MINGW / PATH); both reach every bmpack call through the
environment. The independent base-40 decoder is this file's own; T12 compares with the pinned sha256 of the bmpack 1.1
mod.toml; T15 builds the 4th-region example with the kit's examples/content/wt-region/make_wt_region.py from your game data
and validates it with the shipped host readers (p4.4 has wt4). The platform and service versions are NOT typed in this file: they
are read from the shipped host readers (tools/bmpack/host_readers/src/game/bm_platform_table.h, the table the checker is built
from), so T10 reads that platform and T14e dep-cap asks for one version above the host's autopilot service.
    py -3 -B test_bmpack.py OUT_DIR --game-data DIR [--cc FILE]"""
import hashlib, json, os, pathlib, shutil, struct, subprocess, sys, tomllib

HERE = pathlib.Path(__file__).resolve().parent
BMPACK = HERE.parent / 'bmpack.py'
SPECS = HERE.parent / 'specs'
KIT = HERE.parents[2]
sys.path.insert(0, str(KIT / 'tools' / '_lib'))
import bmkit_env  # noqa: E402


def _arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else None


if _arg('--game-data'):
    os.environ['BMKIT_GAME_DATA'] = _arg('--game-data')
if _arg('--cc'):
    os.environ['BMKIT_CC'] = _arg('--cc')
try:
    GAME = pathlib.Path(bmkit_env.game_data(None, need=('Tracks/tlist.bin', 'Tracks/US/C1_V1/Gamedata.bgd'), what='the bmpack tests'))
    os.environ['BMKIT_GAME_DATA'] = str(GAME)
    os.environ['BMKIT_CC'] = bmkit_env.find_cc(None, what='the bmpack tests')
except bmkit_env.BmkitError as e:
    sys.exit(bmkit_env.report_error('test_bmpack', e))
TRACKS = GAME / 'Tracks'


def _host_data():
    """authoritative version data of the host the checker is built from: BO3_PLATFORM_VERSION and the service versions of the shipped
    bm_platform_table.h (host-readers package). Nothing is typed in this test."""
    import re
    t = (pathlib.Path(bmkit_env.host_readers(None)) / 'src' / 'game' / 'bm_platform_table.h').read_text(encoding='utf-8')
    plat = re.search(r'#define BO3_PLATFORM_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"', t).group(1)
    svc = {m.group(1): int(m.group(2)) for m in re.finditer(r'X\("([a-z0-9_.]+)",\s*([0-9]+),', t)}
    assert svc.get('bmashup.autopilot'), 'no bmashup.autopilot service in the platform table'
    return plat, svc


PLAT, SVC = _host_data()
PLAT_NEXT = '.'.join(PLAT.split('.')[:-1] + [str(int(PLAT.split('.')[-1]) + 1)])   # one patch level above the host: must be refused
T12_BMPACK11_MODTOML = '1947286572798eab8c8a9b64c31bd90f0519eb5b24c2197d3be555c0662a0a89'   # content-pack mod.toml of bmpack 1.1


class T:
    """independent base-40 decoder (this test's own; never bmpack's code)"""
    AL = ' -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'

    @staticmethod
    def decode(v):
        s = ''
        for _ in range(12):
            s = T.AL[v % 40] + s
            v //= 40
        return s.strip()

MUTS = {1: 'manifest carries a build timestamp (not reproducible)', 2: 'Gamedata header keys renamed too (outside the documented fields)',
        3: 'validate never runs the real parsers (always accepted)', 4: 'mods not in the loader order (root, then manifest id)',
        5: 'one donor file (enviro.dat) not copied', 6: 'track names left out of mod.toml',
        7: 'event stage donors left out of mod.toml', 8: 'an existing output mod overwritten',
        9: 'validate does not run the platform gate', 10: 'verify joins manifest paths unchecked (absolute / .. keys read outside the mod)',
        11: 'validate skips the two-phase admission (p2: the services refuse the later mod mid-registration)',
        12: 'requires_mods left out of the generated mod.toml', 13: 'validate does not apply the dependency order',
        14: 'the checker skips [bmashup.world_tour] (bmpack 1.3.2: a declared 4th-region location refused)'}


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def tree(root):
    root = pathlib.Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


class Run:
    def __init__(self, out, mut):
        self.out, self.mut, self.n, self.bad, self.log = out, mut, 0, 0, []

    def bm(self, *args, cwd=None):
        env = dict(os.environ, BMPACK_MUT=str(self.mut))
        r = subprocess.run([sys.executable, '-B', str(BMPACK)] + [str(a) for a in args], capture_output=True, text=True, env=env,
                           cwd=cwd)
        return r.returncode, r.stdout + r.stderr

    def check(self, ok, what):
        self.n += 1
        if not ok:
            self.bad += 1
            self.log.append('FAIL %s' % what)
        return ok


def synth_mod(d, mod_id, body, tracks=(), header_from=None):
    """a hand-made mod folder: mod.toml (manifest + body) and the four files the track check needs per track (empty, or a
    donor's 0x800-byte Gamedata header when events must reach the Gamedata check)"""
    d = pathlib.Path(d)
    d.mkdir(parents=True)
    (d / 'mod.toml').write_text('id = "%s"\nname = "test %s"\nversion = "1.0"\n\n%s' % (mod_id, mod_id, body), encoding='utf-8')
    hdr = (TRACKS / header_from[:2] / header_from[3:] / 'Gamedata.bgd').read_bytes()[:0x800] if header_from else b''
    for t in tracks:
        td = d / 'files' / 'Tracks' / t[:2] / t[3:]
        td.mkdir(parents=True)
        for f in ('Gamedata.bgd', 'static.dat', 'streamed.dat', 'enviro.dat'):
            (td / f).write_bytes(hdr if f == 'Gamedata.bgd' else b'')


def inner(out, mut):
    R = Run(out, mut)
    W = out
    # ---- T1 reproducibility: two builds of one spec, byte-identical; verify OK
    rc1, o1 = R.bm('build', SPECS / 'bmp_content_pack.toml', W / 'r1')
    rc2, o2 = R.bm('build', SPECS / 'bmp_content_pack.toml', W / 'r2')
    R.check(rc1 == 0 and rc2 == 0, 'T1 builds: %s / %s' % (o1.strip()[-200:], o2.strip()[-200:]))
    m1, m2 = W / 'r1' / 'content-pack', W / 'r2' / 'content-pack'
    t1 = tree(m1) if m1.is_dir() else {}
    t2 = tree(m2) if m2.is_dir() else {}
    R.check(t1 and t1 == t2, 'T1 two builds byte-identical (%d / %d files)' % (len(t1), len(t2)))
    rc, o = R.bm('verify', m1)
    R.check(rc == 0, 'T1 verify: %s' % o.strip())
    # ---- T2 donor integrity (independent): every file but Gamedata = the donor's; Gamedata differs only in the manifest's
    # renamed 8-byte fields, all at or after 0x3000, each decoding to the new value; the header (0 .. 0x3000) = the donor's
    if m1.is_dir():
        j = json.loads((m1 / 'bmpack.json').read_text(encoding='utf-8'))
        src = TRACKS / 'US' / 'C1_V1'
        dst = m1 / 'files' / 'Tracks' / 'US' / 'C8_V1'
        names = sorted(p.name for p in src.iterdir() if p.is_file())
        R.check(sorted(p.name for p in dst.iterdir()) == names, 'T2 the donor folder\'s file set copied (%d files)' % len(names))
        R.check(all(sha(dst / n) == sha(src / n) for n in names if n != 'Gamedata.bgd' and (dst / n).is_file()),
                'T2 non-Gamedata files byte-identical to the donor')
        a, b = (src / 'Gamedata.bgd').read_bytes(), (dst / 'Gamedata.bgd').read_bytes()
        fields = [int(f['offset'], 16) for f in j['tracks'][0]['renamed']]
        allowed = set()
        for o_ in fields:
            allowed.update(range(o_, o_ + 8))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        R.check(len(a) == len(b) and diff and set(diff) <= allowed and min(fields) >= 0x3000 and a[:0x3000] == b[:0x3000],
                'T2 Gamedata differs only in %d documented fields (%d bytes differ)' % (len(fields), len(diff)))
        R.check(all(T.decode(struct.unpack_from('<Q', b, o_)[0]) in ('US_C8_V1',) or
                    T.decode(struct.unpack_from('<Q', b, o_)[0]).endswith('USC8V1') for o_ in fields), 'T2 each field reads the new ID')
        R.check(j['files'].keys() == {k for k in t1 if k != 'bmpack.json'} and
                all(j['files'][k]['sha256'] == t1[k] for k in j['files']), 'T2 the manifest lists every file with its hash')
    # ---- T3 round trip: the built mod through the real parsers (manifest, tracks, names, events + W1 resolve, W5, W8)
    rc, o = R.bm('validate', W / 'r1', '--json')
    try:
        rep = json.loads(o[o.index('{'):])
    except ValueError:
        rep = {}
    spec = tomllib.loads((SPECS / 'bmp_content_pack.toml').read_text(encoding='utf-8'))
    R.check(rc == 0 and rep.get('ok') is True, 'T3 accepted by the host: %s' % o[-300:])
    mods = rep.get('mods', [])
    R.check(len(mods) == 1 and mods[0]['id'] == spec['mod']['id'] and mods[0]['version'] == spec['mod']['version'] and
            mods[0]['name'] == spec['mod']['name'], 'T3 manifest read back by modmanifest.c')
    tr = rep.get('added_tracks', [])
    R.check(len(tr) == 1 and tr[0]['id'] == 'US_C8_V1' and tr[0]['entry'] == 36 and tr[0]['region'] == 0 and
            tr[0]['name'] == 'Harbour Lights' and tr[0]['upper'] == 'HARBOUR LIGHTS' and tr[0]['location'] == 'HARBOUR',
            'T3 track + names through bm_tracks.c / bm_names.c: %s' % tr)
    ev = rep.get('events', [])
    R.check([(e['key'], e['location'], e['row'], e['gamedata_record']) for e in ev] ==
            [('bmashup.bmp-content-pack/harbour-night', 'US_C3', 4, 0x3000), ('bmashup.bmp-content-pack/harbour-sprint', 'US_C3', 5, 0x5800)],
            'T3 events through bm_wtour.c (key order rows 4 / 5, W8 records 0x3000 / 0x5800): %s' % ev)
    if m1.is_dir():
        mt = tomllib.loads((m1 / 'mod.toml').read_text(encoding='utf-8'))
        bm = mt.get('bmashup', {})
        R.check(bm.get('extra_events', {}).get('stage') == ['harbour-sprint = 020006USC1V1'] and
                bm.get('tracks', {}).get('names') == ['US_C8_V1 = Harbour Lights'], 'T3 mod.toml carries the stage donor and the name')
    # ---- T4 two independent mods coexist; T5 the conflicting variant is refused with the host's reason
    rc, o = R.bm('build', SPECS / 'bmp_track_pack.toml', W / 'r3')
    R.check(rc == 0, 'T4 build track pack: %s' % o[-200:])
    rc, o = R.bm('build', SPECS / 'bmp_conflict_pack.toml', W / 'r4')
    R.check(rc == 0, 'T5 the conflict pack alone is valid (built): %s' % o[-200:])
    rc, o = R.bm('validate', W / 'r1', W / 'r3', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    R.check(rc == 0 and rep.get('ok') and [t['id'] for t in rep['added_tracks']] == ['US_C8_V1', 'EU_C8_V1'] and len(rep['events']) == 3,
            'T4 both mods accepted together (2 tracks, 3 events)')
    rc, o = R.bm('validate', W / 'r1', W / 'r3', W / 'r4')
    R.check(rc == 1 and '[admission] bmashup.bmp-conflict-pack: mod bmashup.bmp-conflict-pack 1.0.0' in o and 'refused, the game starts without it: track id US_C8_V1: already added by mod bmashup.bmp-content-pack 1.0.0' in o,
            'T5 (1.2) conflict: the later mod refused ALONE by the admission, both mods named: %s' % o[-300:])
    # ---- T6 refusals (hand-made mods through validate; a few through build)
    S = W / 'synth'
    cases = [
        ('bad-id', 'bmashup.t-badid', '[bmashup.tracks]\nversion = 1\nadd = ["US-C8-V1"]\n', ['US_C8_V1'], None, '[tracks]'),
        ('bad-region', 'bmashup.t-badregion', '[bmashup.tracks]\nversion = 1\nadd = ["XX_C8_V1"]\n', ['XX_C8_V1'], None, '[tracks]'),
        ('region-u', 'bmashup.t-regionu', '[bmashup.regions]\nversion = 1\nadd = ["U = UTOPIA"]\n', [], None, '[regions]'),
        ('region-text', 'bmashup.t-regiontext', '[bmashup.regions]\nversion = 1\nadd = ["O = OCEANIA AND BEYOND"]\n', [], None, '[regions]'),
        ('region-twice', 'bmashup.t-regiontwice', '[bmashup.regions]\nversion = 1\nadd = ["O = OCEANIA", "O = ORIENT"]\n', [], None, '[regions]'),
        ('name-long', 'bmashup.t-namelong', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\nnames = ["US_C8_V1 = A Name Of Twenty-Eight Chars"]\n',
         ['US_C8_V1'], None, '[names]'),
        ('loc-long', 'bmashup.t-loclong', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\nlocations = ["US_C8_V1 = EIGHTEEN CHARACTER"]\n',
         ['US_C8_V1'], None, '[names]'),
        ('name-char', 'bmashup.t-namechar', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\nnames = ["US_C8_V1 = Harbour!"]\n',
         ['US_C8_V1'], None, '[names]'),
        ('retail-id', 'bmashup.t-retail', '[bmashup.tracks]\nversion = 1\nadd = ["US_C1_V1"]\n', ['US_C1_V1'], None, 'already a track'),
        ('no-files', 'bmashup.t-nofiles', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n', [], None, '[tracks]'),
        ('ev-full-retail', 'bmashup.t-evc2', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_C2"]\n', ['US_C8_V1'], 'US_C1_V1', '6 retail events'),
        ('ev-crash', 'bmashup.t-evcrash', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_C3 : crash"]\n', ['US_C8_V1'], 'US_C1_V1', 'race-type'),
        ('ev-region', 'bmashup.t-evregion', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ EU_C1"]\n', ['US_C8_V1'], 'US_C1_V1', 'not in the region'),
        ('ev-full', 'bmashup.t-evfull', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_C3", "e2 = US_C8_V1 @ US_C3", "e3 = US_C8_V1 @ US_C3"]\n', ['US_C8_V1'], 'US_C1_V1', 'is full'),
        ('ev-notrack', 'bmashup.t-evnotrack', '[bmashup.extra_events]\nversion = 1\nadd = ["e1 = US_C9_V1 @ US_C3"]\n', [], None,
         'not a track a mod adds'),
        ('ev-twice', 'bmashup.t-evtwice', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_C3", "e1 = US_C8_V1 @ US_P1"]\n', ['US_C8_V1'], 'US_C1_V1', 'declared twice'),
        ('ev-location', 'bmashup.t-evloc', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_Q9"]\n', ['US_C8_V1'], 'US_C1_V1', 'not a race location'),
        ('ev-stage', 'bmashup.t-evstage', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_C3"]\nstage = ["e1 = 0E0001USC1V1"]\n', ['US_C8_V1'], 'US_C1_V1', 'not a race-type race'),
        ('ev-gamedata', 'bmashup.t-evgd', '[bmashup.tracks]\nversion = 1\nadd = ["US_C8_V1"]\n\n[bmashup.extra_events]\nversion = 1\n'
         'add = ["e1 = US_C8_V1 @ US_C3"]\n', ['US_C8_V1'], None, '[events-gamedata]'),
        ('manifest-id', 'Bmashup.T-Upper', '', [], None, '[modfs]'),
    ]
    for name, mid, body, trs, hdr, want in cases:
        synth_mod(S / name / 'm', mid, body, trs, hdr)
        rc, o = R.bm('validate', S / name)
        R.check(rc == 1 and want in o, 'T6 refusal %s (want %r): rc %d %s' % (name, want, rc, o.strip().splitlines()[-1:] if o else ''))
    # a mod id used twice (two folders): modfs disables both
    synth_mod(S / 'twice' / 'a', 'bmashup.t-same', '', [])
    synth_mod(S / 'twice' / 'b', 'bmashup.t-same', '', [])
    rc, o = R.bm('validate', S / 'twice')
    R.check(rc == 1 and '[modfs]' in o and 'is also used by' in o, 'T6 refusal shared mod id')
    # build-level refusals: a spec error, a missing donor, a host refusal during build (no folder left), an existing output
    bad = W / 'badspec'
    bad.mkdir()
    base = (SPECS / 'bmp_content_pack.toml').read_text(encoding='utf-8')
    for name, text, want in [
            ('unknown-key', base.replace('location = "HARBOUR"', 'location = "HARBOUR"\nlaps = "3"'), "unknown key 'laps'"),
            ('no-donor', base.replace('donor = "US_C1_V1"', 'donor = "US_C9_V1"'), 'has no folder'),
            ('host-refuses', base.replace('location = "US_C3"\nstage', 'location = "US_C2"\nstage'), '6 retail events')]:
        (bad / (name + '.toml')).write_text(text, encoding='utf-8')
        rc, o = R.bm('build', bad / (name + '.toml'), W / ('b_' + name))
        R.check(rc == 1 and want in o and not (W / ('b_' + name) / 'content-pack').exists() and
                not (W / ('b_' + name) / 'content-pack.bmpack-tmp').exists(), 'T6 build refusal %s: %s' % (name, o.strip()[-200:]))
    rc, o = R.bm('build', SPECS / 'bmp_content_pack.toml', W / 'r1')
    R.check(rc == 1 and 'exists' in o and tree(m1) == t1, 'T6 an existing output is never overwritten')
    # ---- T7 limits: 347 added tracks (36 + 347 = 383) accepted, one more refused; 23 regions; 35 events, one more refused
    ids, k = [], 0
    retail = {p.parent.name + '_' + p.name for p in TRACKS.glob('*/*') if p.is_dir()}
    al = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    while len(ids) < 348:
        t = 'US_%s%s_V1' % (al[k // 36], al[k % 36])
        k += 1
        if t not in retail:
            ids.append(t)
    synth_mod(S / 'cap347' / 'm', 'bmashup.t-cap', '[bmashup.tracks]\nversion = 1\nadd = [%s]\n' % ', '.join('"%s"' % i for i in ids[:347]), ids[:347])
    rc, o = R.bm('validate', S / 'cap347', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    R.check(rc == 0 and rep.get('tlist_count') == 383, 'T7 347 added tracks accepted (383 entries): rc %d' % rc)
    synth_mod(S / 'cap348' / 'm', 'bmashup.t-cap', '[bmashup.tracks]\nversion = 1\nadd = [%s]\n' % ', '.join('"%s"' % i for i in ids[:347]), ids[:347])
    synth_mod(S / 'cap348' / 'n', 'bmashup.t-cap2', '[bmashup.tracks]\nversion = 1\nadd = ["%s"]\n' % ids[347], ids[347:])
    rc, o = R.bm('validate', S / 'cap348')
    R.check(rc == 1 and '[admission] bmashup.t-cap2' in o and 'track list capacity' in o and '383' in o, 'T7 the 348th added track refused (383, by the admission): %s' % o.strip()[-200:])
    letters = [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c not in 'UEA']
    synth_mod(S / 'reg23' / 'm', 'bmashup.t-reg', '[bmashup.regions]\nversion = 1\nadd = [%s]\n' % ', '.join('"%s = REGION %s"' % (c, c) for c in letters))
    rc, o = R.bm('validate', S / 'reg23', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    R.check(rc == 0 and len(rep.get('regions', [])) == 23, 'T7 23 regions accepted')
    synth_mod(S / 'reg24' / 'm', 'bmashup.t-reg', '[bmashup.regions]\nversion = 1\nadd = [%s]\n' % ', '.join('"%s = REGION %s"' % (c, c) for c in letters))
    synth_mod(S / 'reg24' / 'n', 'bmashup.t-reg2', '[bmashup.regions]\nversion = 1\nadd = ["A = ATLANTIS"]\n')
    rc, o = R.bm('validate', S / 'reg24')
    R.check(rc == 1 and '[regions] bmashup.t-reg2' in o, 'T7 a 24th region (only U / E / A left) refused')
    free = {'US': [('C3', 2), ('M1', 2), ('C1', 2), ('P2', 2), ('P1', 3)], 'EU': [('C1', 3), ('M1', 4), ('C2', 2), ('P2', 1), ('P1', 4), ('C3', 2), ('M2', 2)],
            'AS': [('C3', 2), ('M1', 1), ('C1', 2), ('C2', 1)]}
    evs = ['"%s-%s-%d = %s_C9_V1 @ %s_%s"' % (r.lower(), l.lower(), i, r, r, l) for r, ls in free.items() for l, n in ls for i in range(n)]
    tr3 = ['US_C9_V1', 'EU_C9_V1', 'AS_C9_V1']
    body = '[bmashup.tracks]\nversion = 1\nadd = [%s]\n\n[bmashup.extra_events]\nversion = 1\nadd = [%s]\n' % (
        ', '.join('"%s"' % t for t in tr3), ', '.join(evs))
    synth_mod(S / 'ev35' / 'm', 'bmashup.t-ev', body, tr3, 'US_C1_V1')
    rc, o = R.bm('validate', S / 'ev35', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    R.check(rc == 0 and len(rep.get('events', [])) == 35 and len({e['race_id'] for e in rep['events']}) == 35,
            'T7 35 events (every free row) accepted, 35 distinct race IDs: rc %d %s' % (rc, o.strip()[-200:]))
    synth_mod(S / 'ev36' / 'm', 'bmashup.t-ev', body, tr3, 'US_C1_V1')
    synth_mod(S / 'ev36' / 'n', 'bmashup.t-ev2', '[bmashup.extra_events]\nversion = 1\nadd = ["one-more = US_C9_V1 @ US_C3"]\n')
    rc, o = R.bm('validate', S / 'ev36')
    R.check(rc == 1 and '[admission] bmashup.t-ev2' in o and 'event location capacity US_C3' in o, 'T7 a 36th event refused (its location is full, by the admission): %s' % o.strip()[-200:])
    # ---- T8 loader order: roots in TAKEDAWN_MODS order, then manifest id within a root
    rc, o = R.bm('validate', W / 'r3', W / 'r1', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    R.check(rc == 0 and [t['id'] for t in rep.get('added_tracks', [])] == ['EU_C8_V1', 'US_C8_V1'], 'T8 root order decides first')
    both = W / 'both'
    both.mkdir()
    if (W / 'r3' / 'track-pack').is_dir() and m1.is_dir():
        shutil.copytree(W / 'r3' / 'track-pack', both / 'a-track-pack')     # folder names opposite to the ids' order
        shutil.copytree(m1, both / 'z-content-pack')
        rc, o = R.bm('validate', both, '--json')
        rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    else:
        rc, rep = 1, {}
    R.check(rc == 0 and [m['id'] for m in rep.get('mods', [])] == ['bmashup.bmp-content-pack', 'bmashup.bmp-track-pack'] and
            [t['id'] for t in rep.get('added_tracks', [])] == ['US_C8_V1', 'EU_C8_V1'], 'T8 within a root: manifest id order')
    # ---- T9 verify detects a changed file
    if m2.is_dir():
        p = m2 / 'files' / 'Tracks' / 'US' / 'C8_V1' / 'MUSIC.RWS'
        b = bytearray(p.read_bytes())
        b[0] ^= 1
        p.write_bytes(bytes(b))
        rc, o = R.bm('verify', m2)
        R.check(rc == 1 and 'changed files/Tracks/US/C8_V1/MUSIC.RWS' in o, 'T9 verify reports a changed file')
    # ---- T10 (mod kit) the platform gate: validate refuses what host p2 refuses, the mod ALONE, with the host's reason
    gate = [('g-platform', 'bmashup.t-gplatform', '[bmashup]\nplatform = ">=0.2"\n', 'needs platform >=0.2'),
            ('g-newer', 'bmashup.t-gnewer', '[bmashup.extra_events]\nversion = 3\nadd = []\n', 'needs a newer platform'),
            ('g-typo', 'bmashup.t-gtypo', '[bmashup.tracks]\nversion = 1\nnmes = ["US_C8_V1 = X"]\n', 'is not a key of [bmashup.tracks] version 1 (keys: version add point_to_point names locations): misspelt, or the mod needs a newer platform (this host'),
            ('g-requires', 'bmashup.t-greq', '[bmashup]\nrequires = ["bmashup.weather>=1"]\n', 'bmashup.weather'),
            ('g-unknown', 'bmashup.t-gunk', '[bmashup.weather]\nversion = 1\n', 'needs a newer platform')]
    for name, mid, body, want in gate:
        synth_mod(S / name / 'm', mid, body)
        rc, o = R.bm('validate', S / name)
        R.check(rc == 1 and ('[platform] %s:' % mid) in o and 'the game starts without it' in o and want in o and
                ('Burnout Mashup platform ' + PLAT) in o, 'T10 gate refusal %s (want %r): rc %d %s' % (name, want, rc, o.strip().splitlines()[-1:]))
    synth_mod(S / 'g-ok' / 'm', 'bmashup.t-gok', '[bmashup]\nplatform = ">=0.1"\nrequires = ["bmashup.events>=5", "bmashup.tracks", "bmashup.host"]\n')
    rc, o = R.bm('validate', S / 'g-ok')
    R.check(rc == 0 and 'ACCEPTED' in o, 'T10 a mod whose [bmashup] needs p2 meets is accepted: rc %d' % rc)
    # derived from the host's own platform version (never typed): exactly the host's platform is met, one patch level above is refused
    synth_mod(S / 'g-eq' / 'm', 'bmashup.t-geq', '[bmashup]\nplatform = ">=%s"\n' % PLAT)
    rc, o = R.bm('validate', S / 'g-eq')
    R.check(rc == 0 and 'ACCEPTED' in o, 'T10 a mod that needs exactly the host platform %s is accepted: rc %d' % (PLAT, rc))
    synth_mod(S / 'g-next' / 'm', 'bmashup.t-gnext', '[bmashup]\nplatform = ">=%s"\n' % PLAT_NEXT)
    rc, o = R.bm('validate', S / 'g-next')
    R.check(rc == 1 and '[platform] bmashup.t-gnext:' in o and ('needs platform >=%s' % PLAT_NEXT) in o and 'the game starts without it' in o and
            ('Burnout Mashup platform ' + PLAT) in o, 'T10 a mod that needs platform %s (host %s) is refused alone: rc %d %s' % (PLAT_NEXT, PLAT, rc, o.strip().splitlines()[-1:]))
    ref = KIT / 'tools' / 'reference_host.json'
    if ref.is_file():
        R.check(json.loads(ref.read_text(encoding='utf-8')).get('platform') == PLAT, 'T10 tools/reference_host.json platform equals the host readers table (%s)' % PLAT)
    rc, o = R.bm('validate', W / 'r1', S / 'g-platform', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    refs = rep.get('refusals', [])
    mods = {m['id']: m for m in rep.get('mods', [])}
    R.check(rc == 1 and [r['service'] for r in refs] == ['platform'] and [t['id'] for t in rep.get('added_tracks', [])] == ['US_C8_V1'] and
            len(rep.get('events', [])) == 2 and mods.get('bmashup.t-gplatform', {}).get('platform_refused') == 1 and
            mods.get('bmashup.bmp-content-pack', {}).get('usable') == 1,
            'T10 refused alone: the content pack still reads (1 track, 2 events), only [platform] refused: %s' % refs)
    # ---- T12 (bmpack 1.2) event names / help, tune / capacity tables, the label; 1.1 outputs unchanged
    sp = W / 'spec12'
    sp.mkdir()
    ev12 = base_spec = (SPECS / 'bmp_content_pack.toml').read_text(encoding='utf-8')
    ev12 = ev12.replace('location = "US_C3"\nstage = "020006USC1V1"', 'location = "US_C3"\nstage = "020006USC1V1"\nname = "Harbour Sprint"\nhelp = "Sprint the harbour!"')
    ev12 = ev12.replace('[[event]]\nid = "harbour-night"', '[[event]]\nid = "harbour-night"\nname = "Harbour Night"')
    ev12 = ev12.replace('folder = "content-pack"', 'folder = "content-12"') + '\n[tune]\nset = ["Score/Burnout Points | Takedown BP = 2000"]\n\n[capacity]\nlanes = 80\n'
    (sp / 'ev12.toml').write_text(ev12, encoding='utf-8')
    rc, o = R.bm('build', sp / 'ev12.toml', W / 'r12')
    R.check(rc == 0, 'T12 build with names / help / tune / capacity: %s' % o[-200:])
    m12 = W / 'r12' / 'content-12' / 'mod.toml'
    mt = tomllib.loads(m12.read_text(encoding='utf-8')) if m12.is_file() else {}
    ee = mt.get('bmashup', {}).get('extra_events', {})
    R.check(ee.get('version') == 2 and ee.get('names') == ['harbour-sprint = Harbour Sprint', 'harbour-night = Harbour Night'] and
            ee.get('help') == ['harbour-sprint = Sprint the harbour!'] and mt.get('bmashup', {}).get('tune', {}).get('set') ==
            ['Score/Burnout Points | Takedown BP = 2000'] and mt.get('bmashup', {}).get('capacity') == {'version': 1, 'lanes': 80},
            'T12 mod.toml: [bmashup.extra_events] version 2 with names / help, [bmashup.tune], [bmashup.capacity]')
    rc, o = R.bm('validate', W / 'r12', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    tx = sorted((e['key'].split('/')[-1], e['row_text'], e['help_text']) for e in rep.get('events', []))
    R.check(rc == 0 and tx == [('harbour-night', 'Harbour Night', 'AN EVENT ADDED BY A MOD.'),
                               ('harbour-sprint', 'Harbour Sprint', 'SPRINT THE HARBOUR!')],
            'T12 validate: each event row / help-bar text as the game resolves it: %s' % tx)
    R.check([m.get('label') for m in rep.get('mods', [])] == ['changes gameplay: scoring (Takedown BP 1000 -> 2000), capacity (AI route lanes 80)'],
            'T12 validate: the host\'s gameplay label')
    (sp / 'long.toml').write_text(ev12.replace('Harbour Night', 'Harbour Night Express').replace('content-12', 'long-12'), encoding='utf-8')
    rc, o = R.bm('build', sp / 'long.toml', W / 'r12b')
    R.check(rc == 1 and '[events]' in o and 'has 21 characters; 1 .. 19' in o and not (W / 'r12b' / 'long-12').exists(),
            'T12 a 21-character row name refused at build (the row widget\'s longest retail text is 19): %s' % o.strip()[-160:])
    R.check(m1.is_dir() and sha(m1 / 'mod.toml') == T12_BMPACK11_MODTOML,
            'T12 a 1.1 spec builds the same mod.toml as bmpack 1.1 did (sha256 %s)' % T12_BMPACK11_MODTOML[:12])
    # ---- T13 (bmpack 1.2) the admission: the later mod refused alone, the earlier one reads as alone; reversed order
    rc, o = R.bm('validate', W / 'r1', W / 'r4', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    adm = [a for a in rep.get('admission', []) if a['refused']]
    R.check(rc == 1 and [r['service'] for r in rep.get('refusals', [])] == ['admission'] and len(adm) == 1 and
            adm[0]['id'] == 'bmashup.bmp-conflict-pack' and adm[0]['other'] == 'bmashup.bmp-content-pack' and
            str(W / 'r1') in adm[0]['why'] and [t['id'] for t in rep.get('added_tracks', [])] == ['US_C8_V1'] and
            [t['name'] for t in rep.get('added_tracks', [])] == ['Harbour Lights'] and len(rep.get('events', [])) == 2,
            'T13 the conflict pack refused alone; the content pack reads as alone (its name, 2 events); the earlier folder named')
    rc2, o2 = R.bm('validate', W / 'r1', '--json')
    rep2 = json.loads(o2[o2.index('{'):]) if '{' in o2 else {}
    R.check(all(rep.get(k) == rep2.get(k) for k in ('added_tracks', 'events', 'regions', 'guest_fnv64', 'tlist_fnv64', 'heap_used')),
            'T13 state with the refused later mod = state without it (guest image FNV %s / %s)' % (rep.get('guest_fnv64'), rep2.get('guest_fnv64')))
    rc, o = R.bm('validate', W / 'r4', W / 'r1', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    adm = [a for a in rep.get('admission', []) if a['refused']]
    R.check(rc == 1 and len(adm) == 1 and adm[0]['id'] == 'bmashup.bmp-content-pack' and [t['name'] for t in rep.get('added_tracks', [])] == ['Harbour Clash'],
            'T13 reversed roots: the content pack (now later) refused, the conflict pack kept')
    # ---- T14 (bmpack 1.3) mod-to-mod dependencies and capability requirements
    sp13 = W / 'spec13'
    sp13.mkdir()
    TUNE_A = '[tune]\nset = ["Score/Boost/Aggressive | Trading Paint Boost value (Boost units) = 6"]\n'
    TUNE_B = '[tune]\nset = ["Score/Burnout Points | Takedown BP = 1500"]\n'

    def spec13(name, mid, ver, extra, tune):
        (sp13 / (name + '.toml')).write_text('[mod]\nid = "%s"\nversion = "%s"\nname = "T14 %s"\nfolder = "%s"\n%s\n%s' % (
            mid, ver, name, name, extra, tune), encoding='utf-8')
        return sp13 / (name + '.toml')
    rc, o = R.bm('build', spec13('dep-addon', 'gp.t14-addon', '1.0.0', 'platform = ">=0.1.2"\nrequires = ["bmashup.events >= 5"]\n'
                                 'requires_mods = ["gp.t14-base >= 1.0.2"]', TUNE_A), W / 'r14', '--no-validate')
    rc2, o2 = R.bm('build', spec13('dep-base', 'gp.t14-base', '1.0.2', '', TUNE_B), W / 'r14', '--no-validate')
    mt = tomllib.loads((W / 'r14' / 'dep-addon' / 'mod.toml').read_text(encoding='utf-8')) if rc == 0 else {}
    R.check(rc == 0 and rc2 == 0 and mt.get('bmashup', {}).get('platform') == '>=0.1.2' and
            mt.get('bmashup', {}).get('requires') == ['bmashup.events >= 5'] and
            mt.get('bmashup', {}).get('requires_mods') == ['gp.t14-base >= 1.0.2'], 'T14a [mod] platform / requires / requires_mods '
            '-> [bmashup] in mod.toml: %s' % mt.get('bmashup'))
    j14 = json.loads((W / 'r14' / 'dep-addon' / 'bmpack.json').read_text(encoding='utf-8')) if rc == 0 else {}
    R.check(j14.get('mod', {}).get('requires_mods') == ['gp.t14-base >= 1.0.2'], 'T14a bmpack.json records the requirements')
    rc, o = R.bm('build', spec13('dep-bad', 'gp.t14-bad', '1.0', 'requires_mods = "gp.t14-base"', TUNE_A), W / 'r14x')
    R.check(rc == 1 and 'requires_mods must be a list of strings' in o, 'T14b a spec requires_mods not a list: refused: %s' % o.strip()[-120:])
    rc, o = R.bm('validate', W / 'r14', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    R.check(rc == 0 and rep.get('ok') and [m['id'] for m in rep.get('mods', [])] == ['gp.t14-base', 'gp.t14-addon'] and
            rep.get('dependency_moved') == 2, 'T14c the dependency order: base before addon (ids sort the other way), moved %s' %
            rep.get('dependency_moved'))
    R.check([m.get('label') for m in rep.get('mods', [])] == ['changes gameplay: scoring (Takedown BP 1000 -> 1500)',
            'changes gameplay: boost (Trading Paint Boost value (Boost units) 3 -> 6)'], 'T14c both admitted, labelled')
    rc, o = R.bm('build', spec13('dep-newer', 'gp.t14-newer', '1.0', 'requires_mods = ["gp.t14-base >= 1.1"]', ''), W / 'r14n',
                 '--no-validate')
    rc, o = R.bm('validate', W / 'r14', W / 'r14n', '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    adm = [a for a in rep.get('admission', []) if a['refused']]
    refs = rep.get('refusals', [])
    mods = {m['id']: m for m in rep.get('mods', [])}
    R.check(rc == 1 and len(adm) == 1 and adm[0]['id'] == 'gp.t14-newer' and adm[0]['kind'] == 'needs a mod' and
            adm[0]['other'] == 'gp.t14-base' and 'the installed version 1.0.2 is older' in adm[0]['why'] and
            mods.get('gp.t14-newer', {}).get('needs') == 'needs gp.t14-base >= 1.1: has 1.0.2' and
            mods.get('gp.t14-addon', {}).get('usable') == 1, 'T14d an older dependency: the dependant refused alone (needs a mod), '
            'the others admitted: %s' % adm)
    R.check(len(refs) == 1 and refs[0]['service'] == 'admission' and refs[0]['why'].endswith(adm[0]['why'] if adm else '?'),
            'T14h the admission reason kept whole in the refusal')
    rc, o = R.bm('validate', W / 'r14', W / 'r14n')
    R.check(rc == 1 and '(REFUSED ALONE by the admission: needs gp.t14-base >= 1.1: has 1.0.2)' in o and
            'dependency order: 2 moved' in o, 'T14d the summary names the reason: %s' % o.strip().splitlines()[:1])
    for name, extra, want, svc in [
            ('dep-missing', 'requires_mods = ["gp.t14-absent >= 2.0"]', 'requires_mods "gp.t14-absent >= 2.0": not installed', 'admission'),
            ('dep-cap', 'requires = ["bmashup.autopilot >= %d"]' % (SVC['bmashup.autopilot'] + 1),
             'needs bmashup.autopilot >= %d; this host (platform %s) offers version %d' % (SVC['bmashup.autopilot'] + 1, PLAT, SVC['bmashup.autopilot']),
             'platform'),
            ('dep-modreq', 'requires = ["gp.t14-base>=1.0.2"]', 'another mod goes in [bmashup] requires_mods', 'platform'),
            ('dep-form', 'requires_mods = ["gp.t14-base == 1.0"]', 'the only version condition', 'platform')]:
        rc, o = R.bm('build', spec13(name, 'gp.t14-' + name[4:], '1.0', extra, ''), W / ('r14_' + name), '--no-validate')
        rc, o = R.bm('validate', W / 'r14', W / ('r14_' + name), '--json')
        rep = json.loads(o[o.index('{'):]) if '{' in o else {}
        refs = rep.get('refusals', [])
        R.check(rc == 1 and len(refs) == 1 and refs[0]['service'] == svc and want in refs[0]['why'],
                'T14e %s refused alone by [%s]: %s' % (name, svc, [r['why'][-160:] for r in refs]))
    cyc = W / 'r14c'
    rc, o = R.bm('build', spec13('dep-cyc-a', 'gp.t14-cyc-a', '1.0', 'requires_mods = ["gp.t14-cyc-b"]', ''), cyc, '--no-validate')
    rc, o = R.bm('build', spec13('dep-cyc-b', 'gp.t14-cyc-b', '1.0', 'requires_mods = ["gp.t14-cyc-a"]', ''), cyc, '--no-validate')
    rc, o = R.bm('validate', cyc, '--json')
    rep = json.loads(o[o.index('{'):]) if '{' in o else {}
    adm = [a for a in rep.get('admission', []) if a['refused']]
    R.check(rc == 1 and [a['kind'] for a in adm] == ['dependency cycle', 'dependency cycle'] and
            'gp.t14-cyc-a -> gp.t14-cyc-b -> gp.t14-cyc-a' in adm[0]['why'], 'T14f a cycle: both refused: %s' % [a['why'] for a in adm])
    # ---- T11 (mod kit) verify: path forms, a set folder, manifest entries outside the mod
    if m1.is_dir():
        forms = [('absolute', str(m1), None), ('absolute, forward slashes', m1.as_posix(), None),
                 ('absolute, trailing separator', str(m1) + '\\', None), ('extended-length', '\\\\?\\' + str(m1), None),
                 ('relative, backslashes, cwd = OUT', 'r1\\content-pack', W), ('relative, forward slashes, cwd = OUT', 'r1/content-pack', W),
                 ('relative with .., cwd = a subfolder', '..\\r1\\content-pack', W / 'synth')]
        for what, arg, cwd in forms:
            rc, o = R.bm('verify', arg, cwd=cwd)
            R.check(rc == 0 and 'OK: every file matches' in o, 'T11 verify %s: rc %d %s' % (what, rc, o.strip()[-160:]))
    rc, o = R.bm('verify', W / 'r1')
    R.check(rc == 1 and 'has no bmpack.json' in o and 'content-pack' in o and 'Traceback' not in o,
            'T11 verify of a mod SET folder: a clear refusal naming the built mod, no traceback: %s' % o.strip()[-200:])
    v = S / 'vfy'
    synth_mod(v / 'm', 'bmashup.t-vfy', '')
    (v / 'm' / 'a.txt').write_bytes(b'inside\n')
    (v / 'outside.txt').write_bytes(b'outside the mod\n')
    base_files = {'mod.toml': {'sha256': sha(v / 'm' / 'mod.toml')}, 'a.txt': {'sha256': sha(v / 'm' / 'a.txt')}}

    def manifest_with(extra):
        (v / 'm' / 'bmpack.json').write_text(json.dumps({'bmpack': '1', 'files': dict(base_files, **extra)}), encoding='utf-8')
    manifest_with({})
    rc, o = R.bm('verify', v / 'm')
    R.check(rc == 0, 'T11 a hand-made manifest verifies: %s' % o.strip()[-120:])
    out_sha = {'sha256': sha(v / 'outside.txt')}
    for what, key in [('absolute', str((v / 'outside.txt').resolve())), ('absolute, forward slashes', (v / 'outside.txt').resolve().as_posix()),
                      ('parent (..)', '../outside.txt'), ('backslash ..', '..\\outside.txt')]:
        manifest_with({key: out_sha})
        rc, o = R.bm('verify', v / 'm')
        R.check(rc == 1 and 'not a relative path inside the mod' in o,
                'T11 a manifest entry outside the mod (%s) is refused, never read: rc %d %s' % (what, rc, o.strip()[-160:]))
    # ---- T15 (bmpack 1.3.3; 1.3.4: the kit's example generator + the shipped p4.4 readers) [bmashup.world_tour]
    gen = subprocess.run([sys.executable, '-B', str(KIT / 'examples' / 'content' / 'wt-region' / 'make_wt_region.py'), '--data',
                          str(GAME), '--out', str(W / 't15_wt')], capture_output=True, text=True)
    wt = W / 't15_wt' / 'bmashup-wt4-oceania'
    if gen.returncode == 0 and wt.is_dir():
        rc, o = R.bm('validate', wt, '--json')
        rep = json.loads(o[o.index('{'):]) if '{' in o else {}
        evs = [e.get('key') or e.get('id') for e in rep.get('events', [])]
        R.check(rc == 0 and rep.get('ok') and len(rep.get('events', [])) == 2,
                'T15a the World Tour region example (= the launched gp_wt4_set mod) validates on p4.4: rc %d ok %s events %s refusals %s' % (
                    rc, rep.get('ok'), evs, [r.get('why', '')[:120] for r in rep.get('refusals', [])]))
        body = (wt / 'mod.toml').read_text(encoding='utf-8')
        body = body[body.index('[bmashup]'):]
        for name, old, new, svc, why in [
                ('wt-loc', 'location = "OC_L1"', 'location = "OC_L2"', 'events-resolve', 'OC_L1 is not a race location'),
                ('wt-region', 'region = "O"', 'region = "Q"', 'world_tour', '')]:
            d = S / ('t15_' + name)
            synth_mod(d, 'bmashup.t15-' + name, body.replace(old, new), tracks=('OC_C1_V1',), header_from='US_C1_V1')
            rc, o = R.bm('validate', d, '--json')
            rep = json.loads(o[o.index('{'):]) if '{' in o else {}
            refs = rep.get('refusals', [])
            R.check(rc == 1 and any(r.get('service') == svc and why in r.get('why', '') for r in refs),
                    'T15b %s: refused by [%s]: %s' % (name, svc, [(r.get('service'), r.get('why', '')[:120]) for r in refs]))
    else:
        R.check(False, 'T15 the example generator failed: %s' % (gen.stdout + gen.stderr)[-300:])
    return R


def main():
    out = pathlib.Path(sys.argv[1]).resolve()
    if '--inner' in sys.argv:
        mut = int(sys.argv[sys.argv.index('--inner') + 1])
        out.mkdir(parents=True, exist_ok=False)
        R = inner(out, mut)
        print('\n'.join(R.log))
        print('bmpack tests MUT %d: %d / %d checks passed' % (mut, R.n - R.bad, R.n))
        return 0 if R.bad == 0 else 1
    out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('BMPACK_CACHE', str(out / 'checker_cache'))      # never the tool's own folder
    log, ok = [], True
    for mut in [0] + sorted(MUTS):
        w = out / ('mut%d' % mut)
        r = subprocess.run([sys.executable, '-B', __file__, str(w), '--inner', str(mut)], capture_output=True, text=True)
        (out / ('mut%d.txt' % mut)).write_text(r.stdout + r.stderr, encoding='utf-8')
        line = [l for l in r.stdout.splitlines() if 'checks passed' in l]
        if mut == 0:
            good = r.returncode == 0
            log.append('base: %s -> %s' % (line, 'PASS' if good else 'FAIL'))
        else:
            good = r.returncode != 0
            log.append('MUT %d (%s): %s -> %s' % (mut, MUTS[mut], line, 'CAUGHT' if good else 'NOT CAUGHT'))
        ok &= good
        shutil.rmtree(w, ignore_errors=True)            # the built mods (~60 MB each); the logs stay
    log.append('RESULT %s' % ('PASS' if ok else 'FAIL'))
    (out / 'RESULTS.txt').write_text('\n'.join(log) + '\n', encoding='utf-8')
    print('\n'.join(log))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
