r"""make_packs.py - the fetex example texture packs (portable successor of the fetex1 demo script).

  py -3 -B make_packs.py OUT_SET [--cars2-files DIR] [--art DIR]

OUT_SET must not exist. Steps: gen_art.py writes the AUTHORED art (PNG + pack specs) into --art DIR (default OUT_SET\..\
<OUT_SET name>_art, a NEW folder beside the set, so the set holds only mod folders); fetex.py packs photo.txd / oceania.txd;
the packs are written as mod folders (labels in LABELS.txt; per-file sha256 in SHA256SUMS.txt):
  fetex-photo        bmashup.fetex-photo        AUTHORED  one P8 128x64 garage photo with 8 paint palettes (gen_art.py)
  fetex-oceania-art  bmashup.fetex-oceania-art  AUTHORED  OCEANIA map art (6 tiles, overview, area, city layers 1-4), a new map
                                                marker (icon / pulse / hollow), place name + ticker; requires_mods the wt4
                                                region mod (bmashup.wt4-oceania)
  fetex-car-photo    bmashup.fetex-car-photo    DERIVED, LOCAL ONLY, optional: written only with --cars2-files DIR = the
                                                folder holding pveh\COMP\BM01.bgv / .hwd / .lwd of the cars2 example car
                                                COMPBM01 (made from YOUR game data; hash-checked against the content-phase
                                                files); binds the photo: requires_mods fetex-photo. Never upload it.
Everything else is computed here: no game data is read. The fetex tool used is the one in this kit (..\..\fetex.py).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

D = os.path.dirname(os.path.abspath(__file__))
FETEX = os.path.normpath(os.path.join(D, '..', '..'))
TOOL = os.path.join(FETEX, 'fetex.py')
GEN = os.path.join(D, 'gen_art.py')
REF = os.path.join(FETEX, 'tests', 'REGRESSION_SHA256.json')

PHOTO_TOML = '''# GP-FETEX1 example: a front-end texture pack (AUTHORED art: gp\\slices\\fetex1\\demo\\gen_art.py). Data only.
id = "bmashup.fetex-photo"
name = "Front-end textures: Compact Mashup garage photo"
version = "1.0.0"
description = "Registers bmashup.fetex-photo/compbm01_photo (P8 128x64, 8 paint palettes). Registration only: a car mod binds it."

[bmashup]
platform = ">=0.1.5"
requires = ["bmashup.textures>=1"]

[bmashup.textures]
version = 1
txd = "art/photo.txd"
class = "frontend"
'''

CAR_TOML = '''# GP-FETEX1 example: cars2's added car COMPBM01 with its OWN garage photo from the texture pack bmashup.fetex-photo.
# DERIVED: the model / engine audio are gp_cars2_set's (retail-derived). Local only, never upload.
id = "bmashup.fetex-car-photo"
name = "Compact Mashup with its own garage photo"
version = "1.0.0"
description = "COMPBM01 Compact Mashup (cars2) + its garage photo bound from bmashup.fetex-photo."

[bmashup]
platform = ">=0.1.5"
requires = ["bmashup.textures>=1"]
requires_mods = ["bmashup.fetex-photo >= 1.0"]

[bmashup.cars]
version = 1
add = ["COMPBM01 = COMPCAR1"]
names = ["COMPBM01 = Compact Mashup"]
photos = ["COMPBM01 = bmashup.fetex-photo/compbm01_photo"]
'''

OCEANIA_TOML = '''# GP-FETEX1 example: OCEANIA's own map page for the wt4 4th region (AUTHORED art + texts). Data only.
# The region, its location and events stay the wt4 mod's ([bmashup.world_tour] / [bmashup.extra_events]); this pack only binds
# art to the donor map's texture slots and corrects the map texts while the OCEANIA map is shown.
id = "bmashup.fetex-oceania-art"
name = "World Tour: OCEANIA map art"
version = "1.0.0"
description = "OCEANIA's own satellite map, overview, marker, place name and ticker (shown only on the OCEANIA map page)."

[bmashup]
platform = ">=0.1.5"
requires = ["bmashup.textures>=1", "bmashup.wt_map_art>=1"]
requires_mods = ["bmashup.wt4-oceania"]

[bmashup.textures]
version = 1
txd = "art/oceania.txd"
class = "frontend"

[bmashup.wt_map_art]
version = 1
region = "O"
art = ["SatMapU1_1 = oceania_tile_1_1", "SatMapU2_1 = oceania_tile_2_1", "SatMapU3_1 = oceania_tile_3_1",
       "SatMapU1_2 = oceania_tile_1_2", "SatMapU2_2 = oceania_tile_2_2", "SatMapU3_2 = oceania_tile_3_2",
       "USA1 = oceania_overview", "US_LSat = oceania_area",
       "SatMapU_L1 = oceania_city_l1", "SatMapU_L2 = oceania_city_l2", "SatMapU_L3 = oceania_city_l3", "SatMapU_L4 = oceania_city_l4",
       "RaceIcon = oceania_marker", "RacePulse = oceania_marker_pulse", "RaceHollow = oceania_marker_hollow"]
place = "Harbour City"
ticker = "WELCOME TO OCEANIA...    PLEASE SELECT A LOCATION"
'''


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def write_pack(out, name, toml, files, label):
    d = os.path.join(out, name)
    os.makedirs(d)
    open(os.path.join(d, 'mod.toml'), 'w', encoding='utf-8', newline='\n').write(toml)
    for rel, src in files:
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copyfile(src, p)
    open(os.path.join(d, 'LABELS.txt'), 'w', encoding='utf-8', newline='\n').write(label)
    rows = []
    for root, _, fs in os.walk(d):
        for f in sorted(fs):
            if f == 'SHA256SUMS.txt':
                continue
            p = os.path.join(root, f)
            rows.append('%s  %s' % (sha(p), os.path.relpath(p, d).replace('\\', '/')))
    open(os.path.join(d, 'SHA256SUMS.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(sorted(rows, key=lambda r: r[66:])) + '\n')
    print(name, len(rows), 'files')


def run(args, what):
    r = subprocess.run([sys.executable, '-B'] + [str(a) for a in args], capture_output=True, text=True)
    if r.returncode:
        sys.exit('FAILED: %s (exit %d):\n%s%s' % (what, r.returncode, r.stdout, r.stderr))
    return r.stdout


def opt(argv, name):
    if name in argv:
        i = argv.index(name)
        if i + 1 >= len(argv):
            sys.exit('%s needs a value\n%s' % (name, __doc__))
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return None


def main(argv):
    argv = list(argv)
    cars2 = opt(argv, '--cars2-files')
    art = opt(argv, '--art')
    if len(argv) != 2:
        sys.exit(__doc__)
    out = os.path.abspath(argv[1])
    if os.path.exists(out):
        sys.exit('exists: %s (give a NEW folder; packs are never overwritten)' % out)
    if not os.path.isdir(os.path.dirname(out)):
        sys.exit('the folder %s does not exist (create it first)' % os.path.dirname(out))
    for need in (TOOL, GEN):
        if not os.path.isfile(need):
            sys.exit('installation incomplete: %s missing (copy the whole fetex folder)' % need)
    car_files = None
    if cars2:
        ref = json.load(open(REF, encoding='utf-8'))['packs']['fetex-car-photo']
        car_files = []
        for e in ('bgv', 'hwd', 'lwd'):
            rel = 'files/pveh/COMP/BM01.%s' % e
            p = os.path.join(cars2, 'pveh', 'COMP', 'BM01.%s' % e)
            if not os.path.isfile(p):
                sys.exit('--cars2-files %s: %s missing (the folder must hold pveh\\COMP\\BM01.bgv / .hwd / .lwd of the cars2 '
                         'example car)' % (cars2, p))
            if sha(p) != ref[rel]:
                sys.exit('--cars2-files: %s differs from the content-phase cars2 file (sha256 %s, expected %s): rebuild the '
                         'cars2 example from unmodified game data' % (p, sha(p)[:16], ref[rel][:16]))
            car_files.append((rel, p))
    art = os.path.abspath(art) if art else out + '_art'
    if os.path.exists(art):
        sys.exit('exists: %s (the art folder must be new)' % art)
    run([GEN, art], 'gen_art.py')
    for spec, txd in (('photo.json', 'photo.txd'), ('oceania.json', 'oceania.txd')):
        run([TOOL, 'pack', os.path.join(art, spec), os.path.join(art, txd)], 'fetex pack %s' % spec)
    os.makedirs(out)
    write_pack(out, 'fetex-photo', PHOTO_TOML, [('art/photo.txd', os.path.join(art, 'photo.txd'))],
               'AUTHORED: art/photo.txd (gp\\slices\\fetex1\\demo\\gen_art.py, every pixel computed; no retail input)\n')
    if car_files:
        write_pack(out, 'fetex-car-photo', CAR_TOML, car_files,
                   'DERIVED (local only, never upload): files/pveh/COMP/BM01.* = gp_cars2_set (cars2: retail COMPCAR1 recoloured)\n'
                   'The garage photo is AUTHORED and lives in bmashup.fetex-photo.\n')
    else:
        print('fetex-car-photo skipped (DERIVED, optional: pass --cars2-files DIR)')
    write_pack(out, 'fetex-oceania-art', OCEANIA_TOML, [('art/oceania.txd', os.path.join(art, 'oceania.txd'))],
               'AUTHORED: art/oceania.txd (gp\\slices\\fetex1\\demo\\gen_art.py: procedural map, overview, city layers, marker)\n'
               'Texts AUTHORED (mod.toml place / ticker).\n')
    print('art (sources + TXDs):', art)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
