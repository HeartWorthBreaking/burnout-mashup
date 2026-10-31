r"""fetex tool tests (portable fetex 0.2.0; suite of mod kit 0.4.0 d1): write only OUT_DIR (new).
    py -3 -B test_fetex.py OUT_DIR [--game-data "<game-data>\Burnout 3 Takedown"]     (--game is accepted too)
Game data: --game-data DIR or the BMKIT_GAME_DATA environment variable; Data\Frontend.txd is hash-checked first. Without
game data F1 / F2 are reported SKIPPED (not passed).
F1 rebuild of YOUR retail Data\Frontend.txd: BYTE-IDENTICAL (the strict reader / writer accounts for every byte; read only)
F2 inspect --json of the retail file lists its entries (count > 0, names, formats)
F3 pack: an authored spec (generated here: P8 with 2 palettes, DXT1, DXT5) -> TXD; validate --class frontend PASS; inspect
   shows the 3 entries; packing twice is byte-identical; rebuild of the packed file BYTE-IDENTICAL
F4 extract of the packed TXD decodes every entry to PNG
F5 negatives: a non-power-of-two PNG, an unknown format (DXT3), a bad entry name, a palette picture that is not the same
   picture are REFUSED (exit != 0) with a message; nothing written
Exit 0 = all PASS."""
import json, os, pathlib, struct, subprocess, sys, zlib

HERE = pathlib.Path(__file__).resolve().parent
TOOL = HERE.parent / 'fetex.py'
args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
OUT = pathlib.Path(args[0]).resolve()
sys.path.insert(0, str(HERE.parent))
from fetexlib import gamedata  # noqa: E402
_ga = next((args[args.index(o) + 1] for o in ('--game-data', '--game') if o in args), None)
try:
    GD = gamedata.resolve(_ga, need=('Data/Frontend.txd',), what='the fetex retail check (F1 / F2)')
except gamedata.GameDataError as _e:
    GD = None
    print('SKIP (game data) for F1 / F2: %s' % _e)
OUT.mkdir(parents=True, exist_ok=False)
res = []
skipped = 0


def check(name, ok, detail=''):
    res.append((name, bool(ok)))
    print('%-4s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + detail) if detail else ''), flush=True)


def fx(*a):
    r = subprocess.run([sys.executable, '-B', str(TOOL)] + [str(x) for x in a], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def png(path, w, h, fn):
    rows = b''.join(b'\0' + bytes(c for x in range(w) for c in fn(x, y)) for y in range(h))
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


# F1 / F2 retail (read only)
if GD is None:
    skipped = 2
    print('SKIP F1 / F2 (no game data)')
else:
    try:
        GD.read('Data/Frontend.txd')                              # hash check: the supported release, unmodified
        fe = GD.path('Data/Frontend.txd')
    except gamedata.GameDataError as _e:
        fe = None
        check('F0 game data Data\\Frontend.txd is the supported release', False, str(_e))
    if fe:
        rc, o = fx('rebuild', fe, OUT / 'retail_rebuilt.txd')
        check('F1 retail Frontend.txd rebuild', rc == 0 and 'BYTE-IDENTICAL' in o, o.strip().splitlines()[-1] if o.strip() else 'rc %d' % rc)
        (OUT / 'retail_rebuilt.txd').unlink(missing_ok=True)          # retail-derived bytes are not kept
        rc, o = fx('inspect', fe, '--json')
        try:
            j = json.loads(o[o.index('{') if '{' in o else o.index('['):])
            n = len(j['entries'] if isinstance(j, dict) else j)
        except Exception:
            n = 0
        check('F2 inspect --json of the retail file', rc == 0 and n > 0, '%d entries' % n)

# F3 / F4 authored pack
src = OUT / 'src'
src.mkdir()
C0 = [(20, 20, 20, 255), (200, 40, 40, 255), (40, 200, 40, 255), (40, 40, 200, 255)]
C1 = [(20, 20, 20, 255), (250, 200, 0, 255), (0, 200, 250, 255), (250, 250, 250, 255)]   # the same picture, other colours
cls = lambda x, y: (x // 8 + 2 * (y // 8)) % 4
png(src / 'p0.png', 64, 32, lambda x, y: C0[cls(x, y)])
png(src / 'p1.png', 64, 32, lambda x, y: C1[cls(x, y)])
png(src / 'd1.png', 32, 32, lambda x, y: (x * 8, y * 8, 64, 255))
png(src / 'd5.png', 16, 16, lambda x, y: (255, 255, 255, (x * 16) & 255))
spec = {'tag': 0, 'entries': [{'name': 'kit_p8', 'png': 'src/p0.png', 'format': 'P8', 'palettes': ['src/p1.png']},
                              {'name': 'kit_dxt1', 'png': 'src/d1.png', 'format': 'DXT1'},
                              {'name': 'kit_dxt5', 'png': 'src/d5.png', 'format': 'DXT5'}]}
(OUT / 'spec.json').write_text(json.dumps(spec), encoding='utf-8')
rc1, o1 = fx('pack', OUT / 'spec.json', OUT / 'a.txd')
rc2, o2 = fx('pack', OUT / 'spec.json', OUT / 'b.txd')
same = (OUT / 'a.txd').is_file() and (OUT / 'b.txd').is_file() and (OUT / 'a.txd').read_bytes() == (OUT / 'b.txd').read_bytes()
check('F3 pack twice (deterministic)', rc1 == 0 and rc2 == 0 and same, (o1.strip().splitlines() or [''])[-1])
rc, o = fx('validate', OUT / 'a.txd', '--class', 'frontend')
check('F3 validate --class frontend', rc == 0, (o.strip().splitlines() or [''])[-1])
rc, o = fx('inspect', OUT / 'a.txd')
check('F3 inspect lists the 3 entries', rc == 0 and all(k in o for k in ('kit_p8', 'kit_dxt1', 'kit_dxt5')), '')
rc, o = fx('rebuild', OUT / 'a.txd', OUT / 'a_rebuilt.txd')
check('F3 rebuild of the packed file', rc == 0 and 'BYTE-IDENTICAL' in o, (o.strip().splitlines() or [''])[-1])
rc, o = fx('extract', OUT / 'a.txd', OUT / 'x')
pngs = sorted(p.name for p in (OUT / 'x').glob('*.png')) if (OUT / 'x').is_dir() else []
check('F4 extract decodes every entry', rc == 0 and len(pngs) >= 3, str(pngs))

# F5 negatives
png(src / 'npot.png', 48, 32, lambda x, y: (1, 2, 3, 255))
png(src / 'other.png', 64, 32, lambda x, y: (x * 4, 0, 0, 255))
negs = [('non-power-of-two side', {'name': 'bad_npot', 'png': 'src/npot.png', 'format': 'DXT1'}),
        ('unknown format DXT3', {'name': 'bad_fmt', 'png': 'src/d1.png', 'format': 'DXT3'}),
        ('bad entry name', {'name': 'Bad Name!', 'png': 'src/d1.png', 'format': 'DXT1'}),
        ('palette picture is another picture', {'name': 'bad_pal', 'png': 'src/p0.png', 'format': 'P8', 'palettes': ['src/other.png']})]
for i, (what, e) in enumerate(negs):
    sp = OUT / ('neg%d.json' % i)
    sp.write_text(json.dumps({'tag': 0, 'entries': [e]}), encoding='utf-8')
    rc, o = fx('pack', sp, OUT / ('neg%d.txd' % i))
    check('F5 refused: %s' % what, rc != 0 and not (OUT / ('neg%d.txd' % i)).exists() and o.strip() != '', (o.strip().splitlines() or [''])[-1][:120])
ok = all(r for _, r in res)
summary = 'fetex tests: %d / %d PASS' % (sum(r for _, r in res), len(res)) + (
    ', %d SKIPPED (no game data: pass --game-data DIR or set %s)' % (skipped, gamedata.ENV) if skipped else '')
print(summary)
(OUT / 'RESULTS.txt').write_text('\n'.join('%s %s' % ('PASS' if r else 'FAIL', n) for n, r in res) + '\n' + summary + '\n', encoding='utf-8')
sys.exit(0 if ok else 1)
