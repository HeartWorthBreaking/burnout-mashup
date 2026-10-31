r"""vehtool - vehicles / series / paints as BurnoutMashup data mods (car, series and paint packs; guide docs\VEH_PACKS.md).

  py -3 -B vehtool.py inspect --game-data DIR                    the retail vehicle list: classes, listed rows, headroom
  py -3 -B vehtool.py inspect-car ID --game-data DIR             a retail car's palettes: count, paint-ramp entries (ramp-ready?)
  py -3 -B vehtool.py validate MODDIR [MODDIR ...] --game-data DIR   check mods as the host admits them (limits, refs, files)
  py -3 -B vehtool.py palette OUT.bmpal --gradient RRGGBB RRGGBB [--alpha 255]   an authored 256 x BGRA palette (1024 B)
  py -3 -B vehtool.py fixture OUTDIR --cars N [--series S] [--id ID]  a registry stress fixture (model = donor; FIXTURE)
  py -3 -B vehtool.py package MODDIR [--label AUTHORED|CONTROL|DERIVED|FIXTURE]   write bmpack.json (sha256 of every file)
  py -3 -B vehtool.py version

--game-data DIR = YOUR prepared "Burnout 3 Takedown" folder (read only, hash-checked; --game is the old spelling), else the
BMKIT_GAME_DATA environment variable (in the mod kit also bmkit.toml); no default. palette / fixture / package need no game
data.
The host (bm_cars.c / bm_veh.c / bm_vpaint.c) is authoritative; validate mirrors its stage-1 / stage-2 rules so a mod is
checked before a launch. Deterministic output; no game data is written into a mod by this tool.
Exit codes (mod kit 0.4.1 convention): 0 ok, 1 refused (validate / inspect-car) or invalid input / path, 2 usage, 3 cannot run
(prerequisite missing: Python 3.11, tool files, game data), 4 internal error.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys

try:
    import tomllib
except ImportError:                      # Python < 3.11
    tomllib = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import gamedata  # noqa: E402
except ImportError as _e:
    sys.stderr.write('vehtool: CANNOT RUN: installation incomplete (%s). Copy the whole vehtool folder (vehtool.py, '
                     'gamedata.py, GAMEDATA_SHA256.json; SHA256SUMS.txt lists every file) and run it from there.\n' % _e)
    sys.exit(3)

AL = ' -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'
RETAIL = ['COMP', 'MSCL', 'CUPE', 'SPRT', 'SUPR', 'HSPC', 'HEVY']
LITERALS = RETAIL + ['TRAF', 'TSPC']
VEH_CAP, RETAIL_N, ROWS, SERIES_MAX, PAINT_PER_CAR, PAINT_DECL_MAX = 1024, 107, 20, 64, 56, 4096
MODEL_MAX = 0x9D800
LOCAL = re.compile(r'^[a-z0-9_.-]{1,40}$')
TITLE = re.compile(r"^[A-Za-z0-9 \-'.&]{1,21}$")
TOOL_VERSION = '0.1.2'           # 0.1.2: portable (explicit hash-checked game data, actionable errors); outputs = 0.1.1
PACKAGE_STAMP = '0.1.1'          # written into bmpack.json / fixture mod.toml: the OUTPUT identity (unchanged bytes)
#                                  0.1.1: the manifest limit 65536 (p4.3), fixture parts of 40 series


class Problem(Exception):
    """invalid input or path (exit 1)"""


class Prereq(Exception):
    """a prerequisite is missing: Python 3.11 for TOML, game data, tool files (exit 3, 'vehtool: CANNOT RUN: ...')"""


def need_toml():
    if tomllib is None:
        raise Prereq('Python %d.%d found; this command reads mod.toml and needs Python 3.11 or later (standard module tomllib). '
                     'Install it from python.org and run "py -3.12 -B vehtool.py ..."' % sys.version_info[:2])


def enc(s):
    v = 0
    for i in range(12):
        c = s[i] if i < len(s) else ' '
        v = v * 40 + AL.index(c)
    return v


def dec(v):
    s = ''
    for _ in range(12):
        s = AL[v % 40] + s
        v //= 40
    return s.rstrip()


def game_data(arg):
    if isinstance(arg, gamedata.GameData):
        return arg
    try:
        return gamedata.resolve(arg, need=('pveh/vlist.bin',), what='vehtool (the retail vehicle list)')
    except gamedata.GameDataError as e:
        raise Prereq(str(e))


def gread(gd, rel):
    try:
        return gd.read(rel)
    except gamedata.GameDataError as e:
        raise Prereq(str(e))


def read_vlist(game):
    d = gread(game_data(game), 'pveh/vlist.bin')
    n = struct.unpack_from('<I', d, 4)[0]
    out = []
    for i in range(n):
        a = struct.unpack_from('<I', d, 8 + 4 * i)[0]
        idv = struct.unpack_from('<Q', d, 0x408 + 8 * i)[0]
        out.append((dec(idv), a))
    return out


def retail_race_ids(game):
    return {i for i, a in read_vlist(game) if a == 1 and i[:4] in RETAIL}


def cmd_inspect(a):
    vl = read_vlist(a.game)
    rows = {c: [0, 0] for c in LITERALS}
    for i, fa in vl:
        if i[:4] in rows:
            rows[i[:4]][0] += 1
            rows[i[:4]][1] += fa
    print('vehicle list: %d entries (retail format capacity 128; veh1 host capacity %d -> %d addable)' %
          (len(vl), VEH_CAP, VEH_CAP - len(vl)))
    for c in LITERALS:
        e, l = rows[c]
        head = ROWS - l if c in RETAIL else 0
        print('  %-4s entries %3d  listed %2d  rows free %2d' % (c, e, l, head))
    print('series: up to %d new ones (class codes 10..%d), %d rows each' % (SERIES_MAX, 9 + SERIES_MAX, ROWS))
    return 0


def bgv_palettes(gd, rel):
    """palette count + the 256-entry palettes of a .bgv (texture block at +0x60, rel offsets; bgvlib layout)"""
    b = gread(gd, rel)
    t = struct.unpack_from('<I', b, 0x60)[0]
    n = b[t + 0x69]
    pals = []
    for k in range(n):
        off = struct.unpack_from('<I', b, t + 0x14 + 4 * k)[0]
        data = t + off + 0x40
        pals.append(struct.unpack_from('<256I', b, data))
    return n, pals


def car_rel(cid):
    return 'pveh/%s/%s.bgv' % (cid[:4], cid[4:].capitalize())


def cmd_inspect_car(a):
    gd = game_data(a.game)
    rel = car_rel(a.id)
    if not gd.exists(rel):
        print('no model %s in the game data %s (ID = class + rest, e.g. COMPCAR1)' % (rel, gd.root))
        return 1
    n, pals = bgv_palettes(gd, rel)
    ramp = [i for i in range(256) if n > 1 and any(pals[k][i] != pals[0][i] for k in range(1, n))]
    print('%s: %d palettes; paint ramp %d entries%s; registered paints allowed %d (index %d..%d)' %
          (a.id, n, len(ramp), (' (%d..%d)' % (ramp[0], ramp[-1])) if ramp else '', PAINT_PER_CAR, n, n + PAINT_PER_CAR - 1))
    print('  ramp paints: %s' % ('OK' if len(ramp) else 'NOT POSSIBLE (one palette: use a file paint)'))
    return 0


def load_toml(path):
    need_toml()
    txt = open(path, 'rb').read()
    return tomllib.loads(txt.decode('utf-8'))


def split(s, sep):
    if not isinstance(s, str) or sep not in s:
        return None
    a, b = s.split(sep, 1)
    a, b = a.strip(), b.strip()
    return (a, b) if a and b else None


def rule_ok(s):
    if s == 'open':
        return True
    m = re.match(r'^cars:(\d+)$', s)
    if m:
        return 1 <= int(m.group(1)) <= 67
    m = re.match(r'^car:([A-Z0-9]{5,12})$', s)
    if m:
        return m.group(1)[:4] in RETAIL
    m = re.match(r'^series:([A-Z]{4})$', s)
    return bool(m) and m.group(1) in RETAIL


def check_moddir(md):
    if not os.path.isdir(md):
        raise Problem('mod folder %s: no such folder (give the folder that holds mod.toml)' % md)
    if not os.path.isfile(os.path.join(md, 'mod.toml')):
        raise Problem('mod folder %s has no mod.toml (give the mod folder itself, not the mod set)' % md)


def validate_mods(mods, game):
    """returns (report lines, refused set): stage 1 (declarations, refs, files) + stage 2 (rows, capacity) in list order"""
    need_toml()
    for md in mods:
        check_moddir(md)
    gd = game_data(game)
    race = retail_race_ids(gd)
    vl = read_vlist(gd)
    vl_ids = {i for i, _ in vl}
    listed = {c: sum(1 for i, a in vl if i[:4] == c and a) for c in RETAIL}
    out, refused = [], set()
    series = {}            # prefix -> mod id
    cars = {}              # vehicle id -> mod id
    total = 0
    count = len(vl)
    for md in mods:
        if os.path.getsize(os.path.join(md, 'mod.toml')) > MANIFEST_MAX:
            refused.add(md)
            out.append('REFUSED %s: mod.toml has %d bytes; the host ignores a manifest larger than %d (split the mod)' %
                       (md, os.path.getsize(os.path.join(md, 'mod.toml')), MANIFEST_MAX))
            continue
        try:
            t = load_toml(os.path.join(md, 'mod.toml'))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            refused.add(md)
            out.append('REFUSED %s: mod.toml is not valid TOML (%s); the host would ignore this mod' % (md, e))
            continue
        mid = t.get('id', '?')
        req = [str(r).split('>=')[0].strip() for r in t.get('bmashup', {}).get('requires_mods', [])]
        bm = t.get('bmashup', {})
        errs = []
        s_here = {}
        ser = bm.get('series')
        if ser:
            if ser.get('version') != 1:
                errs.append('[bmashup.series] version must be 1')
            aic = {}
            for e in ser.get('ai_class', []):
                p = split(e, '=')
                if p:
                    aic[p[0]] = p[1]
            for e in ser.get('add', []):
                p = split(e, '=')
                if not p or not LOCAL.match(p[0]) or not re.match(r'^[A-Z]{4}$', p[1]) or p[1] in LITERALS:
                    errs.append('series add %r' % e)
                    continue
                if p[1] in series or p[1] in s_here:
                    errs.append('series prefix %s taken' % p[1])
                if aic.get(p[0]) not in RETAIL:
                    errs.append('series %s: ai_class required (a retail class)' % p[0])
                s_here[p[1]] = p[0]
            for e in ser.get('names', []):
                p = split(e, '=')
                if not p or not TITLE.match(p[1]):
                    errs.append('series name %r' % e)
            for e in ser.get('unlock', []):
                p = split(e, '=')
                if not p or not rule_ok(p[1]):
                    errs.append('series unlock %r' % e)
        if len(series) + len(s_here) > SERIES_MAX:
            errs.append('more than %d series' % SERIES_MAX)
        c = bm.get('cars')
        c_here = []
        if c:
            ver = c.get('version')
            if ver not in (1, 2):
                errs.append('[bmashup.cars] version 1 or 2')
            donor_of = {}
            for e in c.get('add', []):
                p = split(e, '=')
                if not p or not re.match(r'^[A-Z0-9]{5,12}$', p[0]) or p[1] not in race:
                    errs.append('cars add %r (donor must be a retail race car)' % e)
                    continue
                cid, don = p
                pre = cid[:4]
                if pre in RETAIL:
                    if pre != don[:4]:
                        errs.append('%s: class differs from its donor %s' % (cid, don))
                elif ver != 2 or pre in LITERALS:
                    errs.append('%s: not a retail class (series prefixes need version 2)' % cid)
                elif pre not in s_here and not (pre in series and series[pre] in req):
                    errs.append('%s: series %s not declared here nor by a required mod' % (cid, pre))
                if cid in vl_ids or cid in cars or cid in donor_of:
                    errs.append('%s: vehicle ID exists (retail or another mod)' % cid)
                donor_of[cid] = don
            model_donor = set()
            for e in c.get('model', []):
                p = split(e, '=')
                if not p or p[1] != 'donor' or p[0] not in donor_of:
                    errs.append('cars model %r' % e)
                else:
                    model_donor.add(p[0])
            for e in c.get('unlock', []):
                p = split(e, '=')
                if not p or p[0] not in donor_of or not rule_ok(p[1]):
                    errs.append('cars unlock %r' % e)
            for e in c.get('ai', []):
                if e not in donor_of:
                    errs.append('cars ai %r' % e)
            for e in c.get('names', []):
                p = split(e, '=')
                if not p or p[0] not in donor_of or not TITLE.match(p[1]):
                    errs.append('cars name %r' % e)
            for cid in donor_of:
                if cid in model_donor:
                    continue
                for ext in ('bgv', 'hwd', 'lwd'):
                    f = os.path.join(md, 'files', 'pveh', cid[:4], cid[4:] + '.' + ext)
                    if not os.path.exists(f):
                        errs.append('%s: missing files/pveh/%s/%s.%s (or model = donor)' % (cid, cid[:4], cid[4:], ext))
                    elif ext == 'bgv' and (os.path.getsize(f) > MODEL_MAX or os.path.getsize(f) % 0x800):
                        errs.append('%s: model size %d' % (cid, os.path.getsize(f)))
            c_here = list(donor_of)
        if total + len(c_here) > VEH_CAP - RETAIL_N:
            errs.append('more than %d added cars' % (VEH_CAP - RETAIL_N))
        # rows per class / series
        rows_add = {}
        for cid in c_here:
            rows_add[cid[:4]] = rows_add.get(cid[:4], 0) + 1
        for k, v in rows_add.items():
            if listed.get(k, 0) + v > ROWS:
                errs.append('class / series %s would list %d cars (max %d)' % (k, listed.get(k, 0) + v, ROWS))
        pt = bm.get('paints')
        npaint = {}
        if pt:
            if pt.get('version') != 1:
                errs.append('[bmashup.paints] version must be 1')
            names = set()
            for e in pt.get('add', []):
                p = split(e, '=')
                q = split(p[1], '|') if p else None
                if not p or not q or not LOCAL.match(p[0]) or p[0] in names:
                    errs.append('paint add %r' % e)
                    continue
                names.add(p[0])
                ref, d = q
                owner = None
                if '/' in ref:
                    owner, carid = ref.split('/', 1)
                    carid = carid.upper()
                    if owner == 'retail':
                        owner = None
                else:
                    carid = ref
                if owner and owner != mid and owner not in req:
                    errs.append('paint %s: car of %s not in requires_mods' % (p[0], owner))
                if carid not in race and carid not in c_here and carid not in cars:
                    errs.append('paint %s: unknown car %s' % (p[0], ref))
                if carid in cars and cars[carid] != mid and not owner:
                    errs.append('paint %s: another mod\'s car: use <mod-id>/<car>' % p[0])
                if d.startswith('ramp '):
                    if not re.match(r'^ramp [0-9A-Fa-f]{6} [0-9A-Fa-f]{6}$', d):
                        errs.append('paint %s: ramp RRGGBB RRGGBB' % p[0])
                    elif carid in race and gd.exists(car_rel(carid)) and bgv_palettes(gd, car_rel(carid))[0] < 2:
                        out.append('  note: paint %s on %s: one palette, no ramp: the host shows paint 0' % (p[0], carid))
                elif d.startswith('file '):
                    f = os.path.join(md, 'files', d[5:].strip())
                    if '..' in d or not os.path.exists(f) or os.path.getsize(f) != 1024:
                        errs.append('paint %s: file must be 1024 bytes in files/' % p[0])
                else:
                    errs.append('paint %s: ramp or file (texel liveries are not paint v1)' % p[0])
                npaint[carid] = npaint.get(carid, 0) + 1
            for k, v in npaint.items():
                if v > PAINT_PER_CAR:
                    errs.append('car %s: %d paints (max %d registered)' % (k, v, PAINT_PER_CAR))
        if errs:
            refused.add(mid)
            out.append('REFUSED %s (%s): %s' % (mid, md, '; '.join(errs[:6]) + (' ...' if len(errs) > 6 else '')))
            continue
        for p_, n_ in s_here.items():
            series[p_] = mid
        for cid in c_here:
            cars[cid] = mid
            listed[cid[:4]] = listed.get(cid[:4], 0) + 1
        total += len(c_here)
        count += len(c_here)
        out.append('ok %s: %d series, %d cars, %d paints' % (mid, len(s_here), len(c_here), sum(npaint.values())))
    out.append('vehicle list after the admitted mods: %d entries (host capacity %d), %d series' % (count, VEH_CAP, len(series)))
    return out, refused


def cmd_validate(a):
    lines, refused = validate_mods(a.mods, a.game)
    print('\n'.join(lines))
    return 1 if refused else 0


def cmd_palette(a):
    for v in a.gradient:
        if not re.match(r'^[0-9A-Fa-f]{6}$', v):
            raise Problem('--gradient %r: two colours RRGGBB RRGGBB (hex), e.g. --gradient F0F4FF 202830' % v)
    if not 0 <= a.alpha <= 255:
        raise Problem('--alpha %d: 0..255' % a.alpha)
    if os.path.isdir(a.out):
        raise Problem('palette output %s is an existing folder; give a file name (.bmpal)' % a.out)
    hi, lo = int(a.gradient[0], 16), int(a.gradient[1], 16)
    out = bytearray()
    for i in range(256):
        t = i / 255.0
        r = round(((lo >> 16) & 255) * (1 - t) + ((hi >> 16) & 255) * t)
        g = round(((lo >> 8) & 255) * (1 - t) + ((hi >> 8) & 255) * t)
        b = round((lo & 255) * (1 - t) + (hi & 255) * t)
        out += bytes((b, g, r, a.alpha))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'wb').write(bytes(out))
    print('%s: 1024 bytes (authored gradient %s -> %s), sha256 %s' % (a.out, a.gradient[1], a.gradient[0],
                                                                       hashlib.sha256(out).hexdigest()))
    return 0


MANIFEST_MAX = 65536           # modmanifest.h BO3_MANIFEST_MAX_BYTES (p4.3 decision; was 8192): a larger mod.toml is refused
SERIES_PER_PART = 40           # 800 cars: ~36 KB of mod.toml (the 917-car tier = 2 mods; the size guard below stays)


def fixture_toml(mod_id, cars, series_n, donors, k0=0):
    """series of 20 cars (series k0 .. k0 + series_n - 1)"""
    lines = ['# FIXTURE (registry stress test, generated by vehtool %s): not distinct authored vehicles.' % PACKAGE_STAMP,
             'id = "%s"' % mod_id, 'name = "veh1 registry fixture (%d cars)"' % cars, 'version = "1.0.0"',
             'description = "Generated registry stress fixture: %d cars on donor models, %d series."' % (cars, series_n),
             '', '[bmashup]', 'platform = ">=0.1.5"', '']
    adds, models, snames, sadd, sai = [], [], [], [], []
    ids = []
    for k in range(k0, k0 + series_n):
        p = 'F' + chr(65 + k // 26) + chr(65 + k % 26) + 'X'
        sadd.append('"f%02d = %s"' % (k, p))
        snames.append('"f%02d = Fixture %02d"' % (k, k))
        sai.append('"f%02d = SPRT"' % k)
        for j in range(ROWS):
            if len(ids) == cars:
                break
            ids.append((p + 'C%02d' % j, donors[len(ids) % len(donors)]))
    if len(ids) < cars:
        raise Problem('%d series hold %d cars, %d asked (give more --series or fewer --cars)' % (series_n, len(ids), cars))
    lines += ['[bmashup.series]', 'version = 1', 'add = [%s]' % ', '.join(sadd), 'names = [%s]' % ', '.join(snames),
              'ai_class = [%s]' % ', '.join(sai), '']
    for cid, d in ids:
        adds.append('"%s = %s"' % (cid, d))
        models.append('"%s = donor"' % cid)
    lines += ['[bmashup.cars]', 'version = 2', 'add = [%s]' % ', '.join(adds), 'model = [%s]' % ', '.join(models), '']
    return '\n'.join(lines), ids


def cmd_fixture(a):
    """OUTDIR = a mod FOLDER holding parts (one mod each, <= SERIES_PER_PART series so that every mod.toml stays within the
    host's 65536-byte manifest limit)"""
    need_toml()
    if not 1 <= a.cars <= VEH_CAP - RETAIL_N:
        raise Problem('--cars %d: 1..%d (the host adds at most %d cars)' % (a.cars, VEH_CAP - RETAIL_N, VEH_CAP - RETAIL_N))
    if a.series is not None and not 1 <= a.series <= SERIES_MAX:
        raise Problem('--series %d: 1..%d' % (a.series, SERIES_MAX))
    if os.path.exists(a.outdir):
        raise Problem('fixture output %s exists (give a NEW folder; fixtures are never overwritten)' % a.outdir)
    series_n = a.series or (a.cars + ROWS - 1) // ROWS
    if a.cars > series_n * ROWS:     # 0.1.1 failed late here with an IndexError after writing part00
        raise Problem('%d series hold %d cars, %d asked (give more --series or fewer --cars)' % (series_n, series_n * ROWS,
                                                                                                 a.cars))
    donors =['SPRTCAR1', 'SUPRCAR1', 'MSCLCAR1', 'CUPECAR1', 'COMPCAR1']
    os.makedirs(a.outdir, exist_ok=False)
    left, k, part, first, last = a.cars, 0, 0, None, None
    while left > 0:
        sn = min(SERIES_PER_PART, series_n - k)
        n = min(left, sn * ROWS)
        txt, ids = fixture_toml('%s-p%02d' % (a.id, part), n, (n + ROWS - 1) // ROWS, donors, k)
        if len(txt.encode()) > MANIFEST_MAX:
            raise Problem('part %d: mod.toml %d bytes > %d' % (part, len(txt.encode()), MANIFEST_MAX))
        d = os.path.join(a.outdir, 'part%02d' % part)
        os.makedirs(d)
        open(os.path.join(d, 'mod.toml'), 'w', newline='\n').write(txt)
        write_pack(d, 'FIXTURE')
        first = first or ids[0][0]
        last = ids[-1][0]
        left -= n
        k += (n + ROWS - 1) // ROWS
        part += 1
    print('%s: %d cars in %d series, %d mods (first %s, last %s)' % (a.outdir, a.cars, k, part, first, last))
    return 0


def write_pack(md, label):
    need_toml()
    try:
        t = load_toml(os.path.join(md, 'mod.toml'))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise Problem('%s: mod.toml is not valid TOML (%s); fix it before packaging' % (md, e))
    files = {}
    for root, _, fs in os.walk(md):
        for n in sorted(fs):
            if n == 'bmpack.json':
                continue
            p = os.path.join(root, n)
            rel = os.path.relpath(p, md).replace('\\', '/')
            b = open(p, 'rb').read()
            files[rel] = {'sha256': hashlib.sha256(b).hexdigest(), 'size': len(b)}
    pack = {'bmpack': '1', 'folder': os.path.basename(os.path.abspath(md)), 'label': label,
            'mod': {k: t.get(k) for k in ('id', 'name', 'version')}, 'files': dict(sorted(files.items())),
            'packaged_by': 'gp\\tools\\vehtool %s' % PACKAGE_STAMP}
    open(os.path.join(md, 'bmpack.json'), 'w', newline='\n').write(json.dumps(pack, indent=1, sort_keys=True) + '\n')
    return pack


def cmd_package(a):
    check_moddir(a.moddir)
    pack = write_pack(a.moddir, a.label)
    print('%s: %d files, label %s' % (a.moddir, len(pack['files']), a.label))
    return 0


def cmd_version(a):
    print('vehtool %s (package stamp %s, Python %s, game data: --game-data or %s)' % (
        TOOL_VERSION, PACKAGE_STAMP, sys.version.split()[0], gamedata.ENV))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog='vehtool')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def game_opt(p):
        p.add_argument('--game-data', '--game', dest='game', default=None,
                       help='YOUR prepared "Burnout 3 Takedown" folder (else %s)' % gamedata.ENV)
    p = sub.add_parser('inspect'); game_opt(p); p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser('inspect-car'); p.add_argument('id'); game_opt(p); p.set_defaults(fn=cmd_inspect_car)
    p = sub.add_parser('validate'); p.add_argument('mods', nargs='+'); game_opt(p); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser('palette'); p.add_argument('out'); p.add_argument('--gradient', nargs=2, required=True)
    p.add_argument('--alpha', type=int, default=255); p.set_defaults(fn=cmd_palette)
    p = sub.add_parser('fixture'); p.add_argument('outdir'); p.add_argument('--cars', type=int, required=True)
    p.add_argument('--series', type=int); p.add_argument('--id', default='bmashup.veh-fixture'); p.set_defaults(fn=cmd_fixture)
    p = sub.add_parser('package'); p.add_argument('moddir'); p.add_argument('--label', default='AUTHORED',
                                                                           choices=['AUTHORED', 'CONTROL', 'DERIVED', 'FIXTURE'])
    p.set_defaults(fn=cmd_package)
    p = sub.add_parser('version'); p.set_defaults(fn=cmd_version)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except Problem as e:
        print('REFUSED: %s' % e)
        return 1
    except Prereq as e:
        sys.stderr.write('vehtool: CANNOT RUN: %s\n' % e)
        return 3
    except OSError as e:
        print('ERROR: file system: %s (check the path, that the folder exists and is writable, and free disk space)' % e)
        return 1
    except Exception as e:  # noqa: BLE001 - never a bare traceback for a user
        import traceback
        print('INTERNAL ERROR in vehtool %s (%s: %s). Please report it with the command line and this text:' %
              (TOOL_VERSION, type(e).__name__, e))
        traceback.print_exc(file=sys.stdout)
        return 4


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
