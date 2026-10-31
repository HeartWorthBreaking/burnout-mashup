r"""make_veh1_packs.py - the veh1 example packages (contract s6), each standalone on the veh1 host (no per-pack exe):
    py -3 -B make_veh1_packs.py OUT_DIR        (refuses an existing OUT_DIR; OUT_DIR is required)
  bm-veh-neon        AUTHORED  a new series "Neon" (BMNE): 6 cars on donor models (model = donor), names, 12 authored ramp paints
                               (defaults), 3 cars AI-eligible
  bm-veh-dust        AUTHORED  a new series "Dust Runners" (BMDU): 4 cars, unlock rules (open / cars:30 / car:SUPRCAR1), no AI car
                               (the series' ai_class MSCL races against it), 4 authored paints
  bm-veh-retail-paints AUTHORED paints on retail CONTROL cars: COMPCAR1 3 ramps + 1 authored file palette, SPRTCAR1 2 ramps
  bm-veh-cross       AUTHORED  requires bm-veh-neon: a paint on bmashup.veh-neon/bmnec01 (cross-mod reference)
  bm-veh-fixture-21 / -512 / -917  FIXTURE  registry stress tiers (generated, model = donor; not distinct vehicles)
  bm-veh-bad-dup     NEGATIVE  declares BMNEC01 again (with bm-veh-neon: refused whole, rolled back)
  bm-veh-bad-missing NEGATIVE  an own-files car without its files (refused whole)
Every file is written by this script (no game data); bmpack.json per package (vehtool package)."""
import os
import pathlib
import subprocess
import sys

S = pathlib.Path(__file__).resolve().parents[1]
VT = S.parents[1] / 'tools' / 'vehtool' / 'vehtool.py'

NEON = '''# AUTHORED example (gp veh1): a new car series. Cars use their donors' models / audio (model = donor): no game data in
# this package; names, series, paints and colours are original.
id = "bmashup.veh-neon"
name = "Neon Series (veh1 example)"
version = "1.0.0"
description = "A new car series Neon: six cars with authored neon paints; three of them race as AI opponents."

[bmashup]
platform = ">=0.1.5"

[bmashup.series]
version = 1
add = ["neon = BMNE"]
names = ["neon = Neon"]
ai_class = ["neon = SPRT"]

[bmashup.cars]
version = 2
add = ["BMNEC01 = SPRTCAR1", "BMNEC02 = SPRTCAR4", "BMNEC03 = SUPRCAR2", "BMNEC04 = CUPECAR3", "BMNEC05 = MSCLCAR2",
       "BMNEC06 = SUPRCAR5"]
names = ["BMNEC01 = Neon Dart", "BMNEC02 = Neon Arc", "BMNEC03 = Neon Pulse", "BMNEC04 = Neon Halo", "BMNEC05 = Neon Volt",
         "BMNEC06 = Neon Flux"]
model = ["BMNEC01 = donor", "BMNEC02 = donor", "BMNEC03 = donor", "BMNEC04 = donor", "BMNEC05 = donor", "BMNEC06 = donor"]
ai = ["BMNEC01", "BMNEC02", "BMNEC03"]

[bmashup.paints]
version = 1
add = ["dart-magenta = BMNEC01 | ramp FF30E0 300020", "dart-cyan = BMNEC01 | ramp 30FFF0 003040",
       "arc-lime = BMNEC02 | ramp C0FF20 203000", "arc-violet = BMNEC02 | ramp B060FF 200040",
       "pulse-orange = BMNEC03 | ramp FFA020 401000", "pulse-teal = BMNEC03 | ramp 20FFC0 003020",
       "halo-pink = BMNEC04 | ramp FF80C0 400020", "halo-blue = BMNEC04 | ramp 4080FF 001040",
       "volt-yellow = BMNEC05 | ramp FFF020 302800", "volt-green = BMNEC05 | ramp 40FF60 003010",
       "flux-red = BMNEC06 | ramp FF3030 300000", "flux-white = BMNEC06 | ramp FFFFFF 303040"]
default = ["BMNEC01 = dart-magenta", "BMNEC02 = arc-lime", "BMNEC03 = pulse-orange", "BMNEC04 = halo-pink",
           "BMNEC05 = volt-yellow", "BMNEC06 = flux-red"]
'''

DUST = '''# AUTHORED example (gp veh1): a second new series with progression (unlock rules read from the game's own open-car state).
id = "bmashup.veh-dust"
name = "Dust Runners Series (veh1 example)"
version = "1.0.0"
description = "A new car series Dust Runners: four cars, two opened by progress; Muscle cars race against it."

[bmashup]
platform = ">=0.1.5"

[bmashup.series]
version = 1
add = ["dust = BMDU"]
names = ["dust = Dust Runners"]
unlock = ["dust = open"]
ai_class = ["dust = MSCL"]

[bmashup.cars]
version = 2
add = ["BMDUC01 = MSCLCAR3", "BMDUC02 = HEVYCAR2", "BMDUC03 = MSCLCAR7", "BMDUC04 = SUPRCAR6"]
names = ["BMDUC01 = Dust Rover", "BMDUC02 = Dust Hauler", "BMDUC03 = Dust Storm", "BMDUC04 = Dust Comet"]
model = ["BMDUC01 = donor", "BMDUC02 = donor", "BMDUC03 = donor", "BMDUC04 = donor"]
unlock = ["BMDUC03 = cars:30", "BMDUC04 = car:SUPRCAR1"]

[bmashup.paints]
version = 1
add = ["rover-sand = BMDUC01 | ramp E0C080 403010", "hauler-rust = BMDUC02 | ramp D06020 301000",
       "storm-slate = BMDUC03 | ramp A0B0C0 202830", "comet-ochre = BMDUC04 | ramp FFC040 403000"]
default = ["BMDUC01 = rover-sand", "BMDUC02 = hauler-rust", "BMDUC03 = storm-slate", "BMDUC04 = comet-ochre"]
'''

RETAIL = '''# AUTHORED paints on retail CONTROL cars (gp veh1): only authored colours ship; the retail models / palettes are untouched
# (a ramp paint recolours the car's own paint-ramp entries in memory; the file paint is an authored gradient).
id = "bmashup.veh-retail-paints"
name = "Extra Paints for Compact Type 1 and Sports Type 1 (veh1 example)"
version = "1.0.0"
description = "Adds paints beyond the retail ones: Compact Type 1 gets sunset, ice, moss and a chrome gradient; Sports Type 1 two more."

[bmashup]
platform = ">=0.1.5"

[bmashup.paints]
version = 1
add = ["comp-sunset = COMPCAR1 | ramp FF8800 301000", "comp-ice = COMPCAR1 | ramp E0F0FF 102040",
       "comp-moss = COMPCAR1 | ramp 80FF40 103000", "comp-chrome = COMPCAR1 | file paints/chrome.bmpal",
       "sprt-gold = SPRTCAR1 | ramp FFD040 402800", "sprt-ink = SPRTCAR1 | ramp 4050A0 000010"]
'''

CROSS = '''# AUTHORED (gp veh1): a paint for another mod's car (cross-mod reference: that mod must be required).
id = "bmashup.veh-cross"
name = "Gold paint for Neon Dart (veh1 example)"
version = "1.0.0"
description = "Adds a gold paint to the Neon Series' Neon Dart."

[bmashup]
platform = ">=0.1.5"
requires_mods = ["bmashup.veh-neon >= 1.0"]

[bmashup.paints]
version = 1
add = ["dart-gold = bmashup.veh-neon/bmnec01 | ramp FFE060 403000"]
'''

BADDUP = '''# NEGATIVE fixture (gp veh1): declares BMNEC01, which bm-veh-neon adds: with both installed this whole mod is refused and
# rolled back (its series, cars, paints, texts); bm-veh-neon is unaffected.
id = "bmashup.veh-bad-dup"
name = "veh1 negative fixture: duplicate vehicle ID"
version = "1.0.0"
description = "Must be refused when bm-veh-neon is installed."

[bmashup]
platform = ">=0.1.5"

[bmashup.series]
version = 1
add = ["dupe = BMDP"]
names = ["dupe = Duplicate"]
ai_class = ["dupe = COMP"]

[bmashup.cars]
version = 2
add = ["BMDPC01 = COMPCAR1", "BMNEC01 = SPRTCAR1"]
model = ["BMDPC01 = donor", "BMNEC01 = donor"]
'''

BADMISS = '''# NEGATIVE fixture (gp veh1): a car with its own model files that are not shipped: the whole mod is refused.
id = "bmashup.veh-bad-missing"
name = "veh1 negative fixture: missing model files"
version = "1.0.0"
description = "Must be refused (files/pveh/COMP/MS01.bgv is missing)."

[bmashup]
platform = ">=0.1.5"

[bmashup.cars]
version = 2
add = ["COMPMS01 = COMPCAR1"]
names = ["COMPMS01 = Missing Model"]
'''


def write(d, toml):
    d.mkdir(parents=True)
    (d / 'mod.toml').write_text(toml, encoding='utf-8', newline='\n')


def vt(*a):
    r = subprocess.run([sys.executable, '-B', str(VT)] + [str(x) for x in a], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('vehtool %s: %s %s' % (a, r.stdout, r.stderr))
    return r.stdout.strip()


def main(argv):
    if len(argv) < 2:   # kit copy (mod kit 0.4.0): an explicit NEW output folder is required
        sys.exit(__doc__)
    out = pathlib.Path(argv[1])
    if out.exists():
        raise SystemExit('exists: %s' % out)
    log = []
    write(out / 'bm-veh-neon', NEON)
    write(out / 'bm-veh-dust', DUST)
    write(out / 'bm-veh-retail-paints', RETAIL)
    log.append(vt('palette', out / 'bm-veh-retail-paints' / 'files' / 'paints' / 'chrome.bmpal', '--gradient', 'F0F4FF', '202830'))
    write(out / 'bm-veh-cross', CROSS)
    write(out / 'bm-veh-bad-dup', BADDUP)
    write(out / 'bm-veh-bad-missing', BADMISS)
    for p, label in (('bm-veh-neon', 'AUTHORED'), ('bm-veh-dust', 'AUTHORED'), ('bm-veh-retail-paints', 'AUTHORED'),
                     ('bm-veh-cross', 'AUTHORED'), ('bm-veh-bad-dup', 'FIXTURE'), ('bm-veh-bad-missing', 'FIXTURE')):
        log.append(vt('package', out / p, '--label', label))
    for n in (21, 512, 917):
        log.append(vt('fixture', out / ('bm-veh-fixture-%d' % n), '--cars', n, '--id', 'bmashup.veh-fixture-%d' % n))
    (out / 'README.txt').write_text(__doc__, encoding='utf-8', newline='\n')
    print('\n'.join(log))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
