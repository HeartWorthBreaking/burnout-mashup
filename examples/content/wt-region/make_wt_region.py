r"""make_wt_region.py - mod kit 0.3.1 content example: the [bmashup.world_tour] v1 example mod (a 4th World Tour region, OCEANIA,
on the borrowed USA map) built from YOUR OWN retail game data. The kit ships no game file.
    py -3 -B make_wt_region.py --data "<game folder>\Burnout 3 Takedown" --out <NEW folder>
Writes <out>\bmashup-wt4-oceania\{mod.toml, files\Tracks\OC\C1_V1\*}: the added track OC_C1_V1 is a PLACEHOLDER = the retail
US_C1_V1 files copied under the new ID; in Gamedata.bgd the 21 base-40 ID fields that name the donor track / its events are
rewritten to the OC IDs (each checked before it is written). Every input file is checked against its retail sha256 first, and
the output is the runtime-validated set gp_wt4_set (runs gp_wt4_1..5, gp_p42_7) byte for byte (checked at kit release).
The result contains retail game data: LOCAL ONLY, never upload or share it."""
import argparse, hashlib, pathlib, shutil, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
B40 = ' -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'
DONOR = {  # Tracks\US\C1_V1, retail NTSC-U (game signature D0FC2EF4E9B2A86F)
    'CRASH1.RWS': '4afcd4f762b7dc7bd2be6c570b59de3317850b89d1a421e960139feb25469bdc',
    'CRASH2.RWS': '5f27d23e208efd129a41f2c5751d87348e34f6097b1b9460192929fbcf77ffd8',
    'CRASH3.RWS': '724609045039f967e057f2288ca267185ef86cd63278e74f79ebaaf280140eaf',
    'E_DJRACE.xwb': 'ff18ccd17641ba4c79d91a669a92073cb65802b51db3fd30171579056ba834b6',
    'enviro.dat': '7c01695616d8609caf67a3c0dbf789f6dea97d7437354a3933912eaa43fc7ca4',
    'Gamedata.bgd': '2eb45ce64d944958e25951519812dfcdc71ecacdd039e73b0e922146b545ff52',
    'MUSIC.RWS': '9396c110f7c90c4804e5a89357281f4a41f1b3d0667faca2e4f3822faefc5696',
    'SOUND.AWD': '8f86f14cbc5a0e7a0ec78434de353b747e25e772ce8cba54d4796090b22079ab',
    'static.dat': 'ed6d85c2e0144255a6717b1215d8609b22315714204468c954d18a2a1b597c29',
    'streamed.dat': '9b12ab40b8775e94ef08142810650ebe8410b0f9f8fc518ba923c51f070949cd',
}
GAMEDATA_OUT = '63eeb236b5cb485159d6f7473d3eefef5af5d7dc0e8a9b8f9b79539ada956125'
FIELDS = [(0x3390, 'US_C1_V1', 'OC_C1_V1'), (0x3B90, 'US_C1_V1', 'OC_C1_V1'), (0x4390, 'US_C1_V1', 'OC_C1_V1'),
          (0x4B90, 'US_C1_V1', 'OC_C1_V1'), (0x5390, 'US_C1_V1', 'OC_C1_V1'), (0x5B90, 'US_C1_V1', 'OC_C1_V1'),
          (0x5B98, '020006USC1V1', '020006OCC1V1'), (0x6390, 'US_C1_V1', 'OC_C1_V1'), (0x6398, '1G0003USC1V1', '1G0003OCC1V1'),
          (0x6B90, 'US_C1_V1', 'OC_C1_V1'), (0x6B98, '1G0101USC1V1', '1G0101OCC1V1'), (0x7390, 'US_C1_V1', 'OC_C1_V1'),
          (0x7398, '1G0302USC1V1', '1G0302OCC1V1'), (0x7B90, 'US_C1_V1', 'OC_C1_V1'), (0x7B98, '1G0105USC1V1', '1G0105OCC1V1'),
          (0x8390, 'US_C1_V1', 'OC_C1_V1'), (0x8398, '0E0001USC1V1', '0E0001OCC1V1'), (0x8B90, 'US_C1_V1', 'OC_C1_V1'),
          (0x8B98, '0E0601USC1V1', '0E0601OCC1V1'), (0x9390, 'US_C1_V1', 'OC_C1_V1'), (0x9398, '0E0507USC1V1', '0E0507OCC1V1')]


def enc(s):
    """a game ID as the u64 the game stores (base 40, 12 characters, space-padded)"""
    v = 0
    for c in s.ljust(12):
        v = v * 40 + B40.index(c)
    return struct.pack('<Q', v)


def sha(b):
    return hashlib.sha256(b).hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument('--data', required=True, help='the game folder "Burnout 3 Takedown" (holds default.xbe, Tracks)')
ap.add_argument('--out', required=True)
a = ap.parse_args()
src = pathlib.Path(a.data) / 'Tracks' / 'US' / 'C1_V1'
out = pathlib.Path(a.out).resolve()
if out.exists():
    sys.exit('%s exists: give a NEW folder' % out)
data = {}
for name, h in DONOR.items():
    b = (src / name).read_bytes()
    if sha(b) != h:
        sys.exit('REFUSED: %s is not the retail file this example was made for (sha256 %s)' % (src / name, sha(b)))
    data[name] = b
g = bytearray(data['Gamedata.bgd'])
for off, old, new in FIELDS:
    if g[off:off + 8] != enc(old):
        sys.exit('REFUSED: Gamedata.bgd +0x%X does not hold %s' % (off, old))
    g[off:off + 8] = enc(new)
data['Gamedata.bgd'] = bytes(g)
if sha(data['Gamedata.bgd']) != GAMEDATA_OUT:
    sys.exit('REFUSED: the rewritten Gamedata.bgd is not the validated one')
mod = out / 'bmashup-wt4-oceania'
(mod / 'files' / 'Tracks' / 'OC' / 'C1_V1').mkdir(parents=True)
shutil.copyfile(HERE / 'mod.toml', mod / 'mod.toml')
for name, b in sorted(data.items()):
    (mod / 'files' / 'Tracks' / 'OC' / 'C1_V1' / name).write_bytes(b)
    print(sha(b), len(b), name)
print('written %s (LOCAL ONLY: retail data)' % mod)
