r"""make_added_car.py - mod kit 0.3.1 content example: the [bmashup.cars] v1 example mod (COMPBM01 "Compact Mashup" added to the
Compact series on the donor COMPCAR1) built from YOUR OWN retail game data. The kit ships no game file.
    py -3 -B make_added_car.py --data "<game folder>\Burnout 3 Takedown" --out <NEW folder> [--plain]
Writes <out>\gp-cars2\{mod.toml, files\pveh\COMP\BM01.bgv, BM01.hwd, BM01.lwd}:
  BM01.hwd / BM01.lwd  byte copies of the donor's Car1.hwd / Car1.lwd (engine audio)
  BM01.bgv             default: the donor model with paint 1 recoloured magenta + the cars1 stripe livery - the runtime-validated
                       model (gp_cars2_1, gp_p42_1..3), made with the strict BGV reader / writer vendored in the kit
                       (tools\_vendor\bgvlib.py, cars1_recolour.py; kit 0.4.1: no workspace needed);
                       --plain: an unchanged copy of the donor model (needs nothing but this script; the car then looks like
                       Compact Type 1)
The garage photo and the physics are the donor's (the host does that); nothing else is needed. The result contains retail game
data: LOCAL ONLY, never upload or share it. The default output equals the runtime-validated set gp_cars2_set byte for byte (checked at kit release)."""
import argparse, hashlib, os, pathlib, shutil, sys

HERE = pathlib.Path(__file__).resolve().parent
PIN_BGV = 'ff9cbf3ac127222098df7d96bc60388f1cd8d312bb810e09fd4d0390d690900e'   # retail pveh\COMP\Car1.bgv
MAGENTA = (255, 40, 200)


def sha(b):
    return hashlib.sha256(b).hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument('--data', required=True, help='the game folder "Burnout 3 Takedown" (holds default.xbe, pveh)')
ap.add_argument('--out', required=True)
ap.add_argument('--plain', action='store_true', help='copy the donor model unchanged (no workspace modules needed)')
a = ap.parse_args()
pv = pathlib.Path(a.data) / 'pveh' / 'COMP'
out = pathlib.Path(a.out).resolve()
if out.exists():
    sys.exit('%s exists: give a NEW folder' % out)
bgv = (pv / 'Car1.bgv').read_bytes()
if sha(bgv) != PIN_BGV:
    sys.exit('REFUSED: %s is not the retail model this example was made for' % (pv / 'Car1.bgv'))
hwd, lwd = (pv / 'Car1.hwd').read_bytes(), (pv / 'Car1.lwd').read_bytes()
if a.plain:
    nb = bgv
else:
    vendor = HERE.parents[2] / 'tools' / '_vendor'          # the kit's vendored readers (package-relative)
    sys.path.insert(0, str(vendor))
    try:
        import bgvlib, cars1_recolour  # noqa: E401
    except ImportError as e:
        sys.exit('CANNOT RUN: the kit\'s vendored readers are missing (%s, %s): unpack the whole kit zip again, or use --plain' % (vendor, e))
    cars1_recolour.LIME = MAGENTA
    nb, _ = cars1_recolour.build_bgv(bgv)
    if len(nb) != len(bgv) or bgvlib.build(bgvlib.parse(nb)) != nb:
        sys.exit('REFUSED: model round trip failed')
mod = out / 'gp-cars2'
(mod / 'files' / 'pveh' / 'COMP').mkdir(parents=True)
shutil.copyfile(HERE / 'mod.toml', mod / 'mod.toml')
for name, b in (('BM01.bgv', nb), ('BM01.hwd', hwd), ('BM01.lwd', lwd)):
    (mod / 'files' / 'pveh' / 'COMP' / name).write_bytes(b)
    print(sha(b), len(b), name)
print('written %s (%s model; LOCAL ONLY: retail data)' % (mod, 'donor' if a.plain else 'magenta'))
