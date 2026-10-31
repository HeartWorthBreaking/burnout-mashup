"""wbn_catalogue - Workbench tuning editor catalogue (Workbench 0.30, 2026-10-31).

The AUTHORITATIVE list of rows is the kit's docs\\TUNING_CATALOGUE.json (kit 0.7.0, 203 rows: key, type, game value,
host_addition). It carries no descriptions, no units and only one generic limit rule. This module adds, per row, ONLY facts the
main21 host declares in its own source, each with its source named:

  limit           the host's static row bounds (bm_tune.c row_bounds): Effects/Shadow rows k_sh_bounds; every other row
                  0 .. B (signed AI rows -B .. B), B = 16 x max(|the program's value|, 1). The program's value = the kit's game
                  value, for AI rows the code default (bm_tune_ai.h vdefault). This is the ADMISSION limit, not a tested range.
  verified_range  only where the host declares a row range of its own (k_sh_bounds, the 5 Effects/Shadow rows). Every other row
                  has none -> numeric entry only, no slider, and the editor says so.
  default         the kit's game value; AI rows: the host's code default + the game's ValueDB value (bm_tune_ai.h); camera / Air
                  Ram / spark rows: no static value (the host takes the game's value while running) -> "not known offline".
  unit            only the parenthesised suffix of the game's own row name, e.g. "(Seconds)"; else none.
  description     none in the catalogue. The 5 shadow rows + the spark row: the kit's own text (tools\\ps2look\\ps2look.py
                  comment). Nothing is invented.
  applies, signed, unread, needs_version   bm_tune.c t_info / bm_tune_ai.h flags; "AI rows need version 2" (bm_tune.c decl).

    py -3 -B wbn_catalogue.py build --kit KIT [--host-tree TREE] [--out FILE]  (regenerates data\\EDITOR_CATALOGUE.json)
      The kit alone is enough when its tools\\bmpack\\host_readers\\src\\game holds bm_tune_ai.h and every
      bm_tune_catalog_*.inc (kit 0.7.0 as first packaged lacks four of them: the build names them and stops). The shadow
      rows' own bounds are not in the kit's readers (host bm_tune.c k_sh_bounds): SH_BOUNDS below holds the main21 values;
      with --host-tree they are read from bm_tune.c and must agree.
    py -3 -B wbn_catalogue.py search TEXT [--catalogue FILE]                  (one JSON line per match)
    py -3 -B wbn_catalogue.py show KEY [--catalogue FILE]
The runtime reads only the JSON (keys + numbers already public in the kit docs); it needs neither the host tree nor game data.
"""
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(HERE, 'data', 'EDITOR_CATALOGUE.json')
SCHEMA = 'bm-workbench-next-tune-catalogue/1'      # the format name of the editor catalogue (kept stable)
SH_BOUNDS = [(0.0, 1.0), (0.0, 1.0), (0.5, 2.0), (0.5, 2.0), (0.05, 0.45)]   # main21 bm_tune.c k_sh_bounds (Alpha Test,
#   Opacity, Width, Length, Soft Edge = the order of bm_tune_catalog_shadow.inc)
N_SH, N_FX, N_CAM, N_CAD = 5, 1, 32, 7
AI_SIGNED, AI_SETUP, AI_UNREAD = 1, 2, 4
# a parenthesised suffix counts as a unit only when it is one of these measurement words (e.g. '(when drifting)' is not)
UNIT_WORDS = {'seconds', 'boost units', 'metres', 'meters', 'mph', 'boost units per second', 'counts', 'degrees', 'miles'}
_UNIT = re.compile(r'\(([^()]{1,40})\)\s*$')
# kit tools\ps2look\ps2look.py, the "SHADOW SETTINGS" comment (kit 0.7.0) - quoted, not paraphrased into new meaning
PS2LOOK_TEXT = {
    'Effects/Shadow | Alpha Test': 'OFF = draw the whole soft shadow (PS2), ON = the Xbox cut',
    'Effects/Shadow | Soft Edge': 'share of the shadow\'s length that fades out (game 0.1875)',
    'Effects/Shadow | Width': 'x the car\'s shadow width (game 1)',
    'Effects/Shadow | Length': 'x the car\'s shadow length (game 1)',
    'Effects/Shadow | Opacity': 'opacity (Xbox 0.7, PS2 0.703)',
    'Effects/Sparks | Size': 'the spark effect\'s size (Xbox 0.012, PS2 0.017)',
}


def _sha(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def _rows_of_inc(text):
    return re.findall(r'^\s*\{"([^"]+)",', text, re.M)


def build(kit, tree=None):
    """-> the editor catalogue dict (raises ValueError when the kit and the host disagree or a host file is missing)"""
    kc = os.path.join(kit, 'docs', 'TUNING_CATALOGUE.json')
    game = os.path.join(tree, 'src', 'game') if tree else os.path.join(kit, 'tools', 'bmpack', 'host_readers', 'src', 'game')
    base = tree if tree else kit
    need = ['bm_tune_ai.h'] + ['bm_tune_catalog_%s.inc' % x for x in ('ai', 'shadow', 'fx', 'cam', 'cad')]
    miss = [f for f in need if not os.path.isfile(os.path.join(game, f))]
    if miss:
        raise ValueError('%s lacks %s: use a kit whose host readers ship them, or --host-tree <the host source tree>'
                         % (game, ', '.join(miss)))
    src = {'kit_catalogue': kc, 'bm_tune_ai.h': os.path.join(game, 'bm_tune_ai.h'),
           'bm_tune_catalog_ai.inc': os.path.join(game, 'bm_tune_catalog_ai.inc'),
           'ps2look.py': os.path.join(kit, 'tools', 'ps2look', 'ps2look.py')}
    kd = json.load(open(kc, encoding='utf-8'))
    vals = kd['values']
    sh = list(SH_BOUNDS)
    if tree:
        src['bm_tune.c'] = os.path.join(game, 'bm_tune.c')
        ctext = open(src['bm_tune.c'], encoding='utf-8', errors='replace').read()
        m = re.search(r'k_sh_bounds\[BM_TUNE_SH_N\]\s*=\s*\{(.*?)\};', ctext, re.S)
        got = [(float(a), float(b)) for a, b in re.findall(r'\{\s*([-0-9.]+)\s*,\s*([-0-9.]+)\s*\}', m.group(1))]
        if got != sh:
            raise ValueError('bm_tune.c k_sh_bounds %s differs from SH_BOUNDS %s: update SH_BOUNDS' % (got, sh))
    ai_keys = _rows_of_inc(open(src['bm_tune_catalog_ai.inc'], encoding='utf-8').read())
    ai_meta = re.findall(r'^\s*\{([A-Z_0-9|\s]+?),\s*([-0-9.e]+),\s*([-0-9.e]+)\},', open(src['bm_tune_ai.h'], encoding='utf-8').read(),
                         re.M)
    fam_of = {}
    for fam, inc in (('shadow', 'shadow'), ('fx', 'fx'), ('camera', 'cam'), ('cad', 'cad'), ('ai', 'ai')):
        p = os.path.join(game, 'bm_tune_catalog_%s.inc' % inc)
        src['bm_tune_catalog_%s.inc' % inc] = p
        for k in _rows_of_inc(open(p, encoding='utf-8').read()):
            fam_of[k] = fam
    sh_keys = [k for k, f in fam_of.items() if f == 'shadow']
    keys = [v['key'] for v in vals]
    if len(sh) != N_SH or len(sh_keys) != N_SH or len(ai_meta) != len(ai_keys) or not set(fam_of) <= set(keys):
        raise ValueError('the kit catalogue and the host source disagree (shadow / AI / added rows)')
    rows = []
    for v in vals:
        key = v['key']
        group, name = key.split(' | ', 1)
        r = {'key': key, 'group': group, 'name': name, 'type': v['type'], 'kit_game': v['game'],
             'host_addition': bool(v.get('host_addition')), 'family': fam_of.get(key, 'valuedb')}
        flags, vdef, vdb = 0, None, None
        if r['family'] == 'ai':
            fl, vdef, vdb = ai_meta[ai_keys.index(key)]
            flags = sum({'BM_TUNE_AI_SIGNED': 1, 'BM_TUNE_AI_SETUP': 2, 'BM_TUNE_AI_UNREAD': 4}.get(x.strip(), 0)
                        for x in fl.split('|') if x.strip() != '0')
            vdef, vdb = float(vdef), float(vdb)
        program = vdef if r['family'] == 'ai' else float(v['game'])
        signed = bool(flags & AI_SIGNED)
        if r['family'] == 'shadow':
            lo, hi = sh[sh_keys.index(key)]
            r['limit'] = {'lo': lo, 'hi': hi, 'rule': 'the row\'s own bounds', 'source': 'host bm_tune.c k_sh_bounds'}
            r['verified_range'] = {'lo': lo, 'hi': hi, 'source': 'host bm_tune.c k_sh_bounds (the row\'s own range)'}
        else:
            b = 16.0 * max(abs(program), 1.0)
            r['limit'] = {'lo': -b if signed else 0.0, 'hi': b,
                          'rule': '%s16 x max(|program value %g|, 1)' % ('-16 .. ' if signed else '0 .. ', program),
                          'source': 'host bm_tune.c row_bounds (admission limit, not a tested range)'}
            if r['family'] == 'ai':
                gb = 16.0 * max(abs(vdef), abs(vdb), 1.0)
                r['limit']['hi_with_game_value'] = gb
                r['limit']['note'] = ('the host widens the limit to 16 x max(|code default|, |ValueDB value|, 1) = %g once the '
                                      'game\'s value is read at boot (bm_tune.c bound())' % gb)
            r['verified_range'] = None
        if r['family'] == 'ai':
            r['default'] = {'value': vdb, 'text': 'ValueDB %g (code default %g)' % (vdb, vdef),
                            'source': 'host bm_tune_ai.h (vdb, vdefault); the kit catalogue lists 0 (the block is empty before boot)'}
        elif r['family'] in ('cad', 'camera', 'fx'):
            r['default'] = {'value': None, 'text': 'not known offline: the host takes the game\'s value while it runs',
                            'source': 'host bm_tune_catalog_%s.inc comment' % {'cad': 'cad', 'camera': 'cam', 'fx': 'fx'}[r['family']]}
        else:
            r['default'] = {'value': float(v['game']), 'text': '%g' % v['game'], 'source': 'kit TUNING_CATALOGUE.json game value'}
        mu = _UNIT.search(name)
        r['unit'] = ({'text': mu.group(1), 'source': 'the row\'s own name'}
                     if mu and mu.group(1).lower() in UNIT_WORDS else None)
        r['description'] = ({'text': PS2LOOK_TEXT[key], 'source': 'kit tools\\ps2look\\ps2look.py (SHADOW SETTINGS comment)'}
                            if key in PS2LOOK_TEXT else None)
        r['signed'] = signed
        r['unread'] = bool(flags & AI_UNREAD)
        r['applies'] = ('never (never read by this game build: the host refuses it)' if r['unread'] else
                        'from the next race' if (flags & AI_SETUP) or r['family'] == 'camera' else 'at the next use')
        r['needs_version'] = 2 if r['family'] == 'ai' else 1
        rows.append(r)
    return {'schema': SCHEMA, 'rows': rows, 'count': len(rows),
            'sources': {k: {'path': os.path.relpath(p, base if k != 'kit_catalogue' and k != 'ps2look.py' else kit)
                                    .replace(os.sep, '/'), 'from': 'host tree' if tree and k not in ('kit_catalogue', 'ps2look.py')
                            else 'kit', 'sha256': _sha(p)} for k, p in src.items()},
            'shadow_bounds': {'values': sh, 'source': 'host bm_tune.c k_sh_bounds (%s)' % ('read from the host tree' if tree
                                                                                      else 'main21 values in SH_BOUNDS')},
            'kit_catalogue_sha256': _sha(kc),
            'notes': ['no row carries a description or tested range in the kit catalogue; nothing is invented',
                      'the host checks every row against the running game at start ("verified on this game build"); offline '
                      'checks cannot know that result',
                      'set values: negative values and AI rows need [bmashup.tune] version 2; sliders need version 3']}


def load(path=None):
    """-> catalogue dict, or None when missing / unreadable"""
    try:
        d = json.load(open(path or DEFAULT_FILE, encoding='utf-8'))
        return d if d.get('schema') == SCHEMA else None
    except (OSError, ValueError):
        return None


def index(cat):
    return {r['key']: r for r in (cat or {}).get('rows', [])}


def check_against_kit(cat, kit):
    """the editor catalogue must describe the user's kit: same keys, types and game values. -> problems"""
    p = os.path.join(kit or '', 'docs', 'TUNING_CATALOGUE.json')
    try:
        kd = json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError) as e:
        return ['the kit has no readable docs\\TUNING_CATALOGUE.json (%s): the editor cannot check keys' % e]
    a = [(v['key'], v['type'], v['game']) for v in kd.get('values', [])]
    b = [(r['key'], r['type'], r['kit_game']) for r in cat.get('rows', [])]
    if a != b:
        miss = sorted(set(x[0] for x in a) ^ set(x[0] for x in b))[:5]
        return ['the kit\'s TUNING_CATALOGUE.json differs from the editor catalogue (made for kit 0.7.0); differing keys: %s. '
                'Sliders are switched off and only the kit\'s keys are offered' % (miss or 'types / game values')]
    return []


def search(cat, text, limit=500):
    """case-insensitive; every word must appear in the key, the unit or the description"""
    words = [w for w in (text or '').lower().split() if w]
    out = []
    for r in cat.get('rows', []):
        hay = ' '.join([r['key'], (r.get('unit') or {}).get('text', ''), (r.get('description') or {}).get('text', ''),
                        r['family']]).lower()
        if all(w in hay for w in words):
            out.append(r)
            if len(out) >= limit:
                break
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'search', 'show'])
    ap.add_argument('text', nargs='?', default='')
    ap.add_argument('--kit')
    ap.add_argument('--host-tree', help='optional: the host source tree (adds the bm_tune.c cross-check)')
    ap.add_argument('--out')
    ap.add_argument('--catalogue')
    a = ap.parse_args(argv)
    if a.cmd == 'build':
        d = build(a.kit, a.host_tree)
        out = a.out or DEFAULT_FILE
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
            json.dump(d, f, indent=1)
        os.replace(out + '.tmp', out)
        print(json.dumps({'ok': True, 'rows': d['count'], 'sliders': sum(1 for r in d['rows'] if r['verified_range']),
                          'out': out, 'sha256': _sha(out)}))
        return 0
    cat = load(a.catalogue)
    if not cat:
        print(json.dumps({'ok': False, 'why': 'no editor catalogue at %s' % (a.catalogue or DEFAULT_FILE)}))
        return 3
    if a.cmd == 'show':
        r = index(cat).get(a.text)
        print(json.dumps(r if r else {'ok': False, 'why': 'not a catalogue key: %r' % a.text}, indent=1))
        return 0 if r else 1
    for r in search(cat, a.text):
        print(json.dumps({'key': r['key'], 'type': r['type'], 'default': r['default']['text'],
                          'slider': bool(r['verified_range'])}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
