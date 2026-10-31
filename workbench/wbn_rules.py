"""wbn_rules - offline checks of a data-mod project, every problem linked to a file / line / field / editor object.

What is checked (and from where):
  * mod.toml readable, UTF-8, TOML (wbn_toml scanner + tomllib: line and column);
  * identity: id (namespaced, not reserved), name, version (wb_project.check_mod_id / check_name);
  * [bmashup.tune] = the main21 host's declaration rules (bm_tune.c bo3_tune_apply_decl / slider_parse / sliders_decl, bm_tune.h):
      only the keys version / set / sliders; version 1..3; "Group | Name = number"; the key in the catalogue; a never-read row is
      refused; AI rows and negative values need version 2; sliders need version 3; whole numbers for whole-number rows; the row's
      static bounds; one value per row; slider grammar, decimals <= 6, min < max, max = min + k steps, <= 64 values, |units| <= 1e6,
      inside the row's own bounds, default inside and equal to the set value, label 1..16 printable, one slider a row, <= 8 a mod.
    The kit's bmpack 1.5.0 does NOT check these (probe 2026-10-31: an unknown key, a value out of bounds and a bad
    slider are all ACCEPTED by bmpack; the host refuses them at start with exit 93). bmpack is still run (Test this project) for
    the host's own admission (platform gate, table versions, clashes between mods).
  * compatibility with the host the kit describes (kit HOST_INFO.json) through the tester launcher's own gate (vendor\\bmcompat.py,
    a byte copy of release_readiness candidate tester\\tools\\launcher\\bmcompat.py).
Each problem: {sev: error|warn|info, code, msg, fix, file, line, col, field, row, obj}. obj = "tune-row:<key>" /
"tune-slider:<row>" / "manifest:<key>" - the GUI selects that editor object.
"""
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'vendor'))
import bmcompat  # noqa: E402
import wb_project  # noqa: E402
import wbn_catalogue  # noqa: E402
import wbn_toml  # noqa: E402

SLIDER_STEPS, SLIDERS_PER_MOD, SLIDER_DECIMALS = 64, 8, 6
NUM = re.compile(r'^-?[0-9]+(\.([0-9]+))?$')
TUNE_KEYS = ('version', 'set', 'sliders')


def P(sev, code, msg, fix='', file='mod.toml', line=None, col=None, field=None, row=None, obj=None):
    return {'sev': sev, 'code': code, 'msg': msg, 'fix': fix, 'file': file, 'line': line, 'col': col, 'field': field, 'row': row,
            'obj': obj}


def _dec(t):
    m = NUM.match(t.strip())
    return (len(m.group(2)) if m and m.group(2) else 0) if m else None


def check_value(row, value_text, version):
    """one set value against the host rules -> [(code, msg, fix)] (empty = accepted offline)"""
    out = []
    t = value_text.strip()
    if not NUM.match(t):
        return [('value-not-number', 'the value %r is not a plain number' % t, 'write digits with an optional "-" and "."')]
    v = float(t)
    if row['unread']:
        out.append(('row-never-read', 'the host refuses %s: this game build never reads it (it would change nothing)'
                    % row['key'], 'remove this value'))
    if (row['family'] == 'ai' or v < 0) and (version or 0) < 2:
        out.append(('needs-version-2', '%s = %s needs [bmashup.tune] version = 2 (AI values and negative values)' % (row['key'], t),
                    'set version = 2 (the editor does it when you save)'))
    if row['type'] == 'whole number' and _dec(t):
        out.append(('needs-whole-number', '%s takes whole numbers, not %s' % (row['key'], t), 'remove the decimals'))
    lim = row['limit']
    if v < lim['lo'] or v > lim['hi']:
        wider = lim.get('hi_with_game_value')
        if wider and lim['lo'] <= v <= wider and (v >= 0 or row['signed']):
            out.append(('above-static-limit', '%s = %s is above the limit %g that holds before the game value is read; the host '
                        'accepts up to %g once it reads the ValueDB value at boot' % (row['key'], t, lim['hi'], wider), 'warn'))
        else:
            out.append(('out-of-range', '%s = %s is outside the host limit %g .. %g (%s)' % (row['key'], t, lim['lo'], lim['hi'],
                                                                                         lim['rule']),
                        'choose a value in %g .. %g' % (lim['lo'], lim['hi'])))
    return out


def parse_slider(line):
    """host grammar 'ROW = DEFAULT : MIN .. MAX [step S] [label T]' -> (dict, None) or (None, why)"""
    if not isinstance(line, str) or len(line) >= 300:
        return None, 'a slider is not "Group | Name = default : min .. max [step s] [label text]"'
    lab = None
    if ' label ' in line:
        line, lab = line.split(' label ', 1)
        lab = lab.strip(' \t')
    if '=' not in line:
        return None, 'slider "%s" is not "Group | Name = default : min .. max [step s] [label text]"' % line[:80]
    row, rhs = line.rsplit('=', 1)
    if ':' not in rhs or '..' not in rhs.split(':', 1)[1]:
        return None, 'slider "%s" is not "Group | Name = default : min .. max [step s] [label text]"' % line[:80]
    d, rng = rhs.split(':', 1)
    lo, hi = rng.split('..', 1)
    st = None
    if 'step' in hi:
        hi, st = hi.split('step', 1)
    toks = [d, lo, hi] + ([st] if st is not None else [])
    if any(not NUM.match(x.strip()) or len(x.strip()) > 20 for x in toks):
        return None, 'slider "%s": default, min, max and step must be numbers ([-]D[.D])' % row.strip()
    return {'row': row.strip(), 'default': d.strip(), 'min': lo.strip(), 'max': hi.strip(),
            'step': st.strip() if st is not None else None, 'label': lab}, None


def check_slider(sl, row, set_value):
    """the host's slider rules for one parsed slider -> [(code, msg, fix)]"""
    out = []
    toks = [sl['default'], sl['min'], sl['max']] + ([sl['step']] if sl['step'] else [])
    d = max(_dec(x) for x in toks)
    if d > SLIDER_DECIMALS:
        return [('slider-decimals', 'slider "%s": at most 6 decimals' % row['key'], 'round the numbers')]
    if d and row['type'] == 'whole number':
        return [('slider-whole', 'slider "%s": this row takes whole numbers' % row['key'], 'remove the decimals')]
    p = 10 ** d
    u = [round(float(x) * p) for x in toks]
    if not sl['step']:
        u.append(1)
    if (u[3] < 1 or u[1] >= u[2] or (u[2] - u[1]) % u[3] or (u[2] - u[1]) // u[3] + 1 > SLIDER_STEPS or abs(u[1]) > 1000000
            or abs(u[2]) > 1000000):
        out.append(('slider-grid', 'slider "%s": min < max, max = min + a whole number of steps (step > 0), at most %d values, at '
                    'most 1000000 units of the finest decimal' % (row['key'], SLIDER_STEPS),
                    'e.g. a larger step (now %d values)' % ((u[2] - u[1]) // max(u[3], 1) + 1)))
        return out
    lim = row['limit']
    if float(sl['min']) < lim['lo'] or float(sl['max']) > lim['hi']:
        out.append(('slider-bounds', 'slider "%s": %s .. %s is outside the row\'s own bounds %g .. %g' %
                    (row['key'], sl['min'], sl['max'], lim['lo'], lim['hi']), 'keep the range inside %g .. %g' % (lim['lo'], lim['hi'])))
    if u[0] < u[1] or u[0] > u[2]:
        out.append(('slider-default', 'slider "%s": the default %s is not in %s .. %s' % (row['key'], sl['default'], sl['min'],
                                                                                          sl['max']), 'move the default inside'))
    if set_value is not None and NUM.match(set_value) and abs(float(set_value) * p - u[0]) > 1e-6:
        out.append(('slider-default-differs', 'slider "%s": the default %s differs from the mod\'s set value %s (the set value is '
                    'the default)' % (row['key'], sl['default'], set_value), 'make them equal'))
    lab = sl['label'] if sl['label'] is not None else row['name']
    if not (1 <= len(lab) <= 16) or any(ord(c) < 0x20 or ord(c) > 0x7E or c in '"\\' for c in lab):
        out.append(('slider-label', 'slider "%s": %s' % (row['key'], 'the label must be 1..16 printable characters (no " or \\)'
                                                         if sl['label'] is not None else
                                                         'the row\'s name is longer than 16 characters: add "label TEXT"'),
                    'give a label of at most 16 characters'))
    return out


def validate_text(text, cat, host_info=None, folder=None, fname='mod.toml'):
    """-> {'ok', 'problems', 'version', 'entries', 'sliders', 'needed_version'}"""
    probs = []
    idx = wbn_catalogue.index(cat)
    try:
        doc = wbn_toml.parse(text)
    except wbn_toml.TomlScanError as e:
        return {'ok': False, 'problems': [P('error', 'toml-syntax', 'mod.toml is not valid TOML: %s' % e, 'fix the line', fname,
                                            e.line, e.col)], 'entries': [], 'sliders': []}
    try:
        man = tomllib.loads(text.lstrip('﻿'))
    except tomllib.TOMLDecodeError as e:
        m = re.search(r'line (\d+), column (\d+)', str(e))
        return {'ok': False, 'problems': [P('error', 'toml-syntax', 'mod.toml is not valid TOML: %s' % e, 'fix the line', fname,
                                            int(m.group(1)) if m else None, int(m.group(2)) if m else None)],
                'entries': [], 'sliders': []}

    def at(full):
        e = doc.find(full)
        return doc.line_of(e.ks) if e else None
    for k, chk in (('id', wb_project.check_mod_id), ('name', wb_project.check_name)):
        v = man.get(k)
        why = chk(v if isinstance(v, str) else '')
        if why:
            probs.append(P('error', 'manifest-' + k, why, 'edit %s in mod.toml' % k, fname, at(k), field=k, obj='manifest:' + k))
    if not isinstance(man.get('version'), str) or not man.get('version'):
        probs.append(P('error', 'manifest-version', 'mod.toml has no version string', 'add version = "1.0.0"', fname,
                       at('version'), field='version', obj='manifest:version'))
    tune = (man.get('bmashup') or {}).get('tune') if isinstance(man.get('bmashup'), dict) else None
    entries = wbn_toml.tune_entries(doc)
    sliders = wbn_toml.tune_sliders(doc)
    ver = tune.get('version') if isinstance(tune, dict) else None
    needed = 1
    if isinstance(tune, dict):
        for k in tune:
            if k not in TUNE_KEYS:
                probs.append(P('error', 'tune-unknown-key', 'bmashup.tune.%s is not a key the host reads (version, set, sliders)'
                               % k, 'remove it or move it to a comment (it is kept as written until you do)', fname,
                               at('bmashup.tune.' + k), field='bmashup.tune.' + k))
        if not isinstance(ver, int) or not 1 <= ver <= 3:
            probs.append(P('error', 'tune-version', 'bmashup.tune.version must be 1, 2 or 3 (it is %r)' % (ver,),
                           'set version = 1 (2 for AI / negative values, 3 for sliders)', fname, at('bmashup.tune.version'),
                           field='bmashup.tune.version', obj='tune-version'))
        if 'set' in tune and not isinstance(tune['set'], list):
            probs.append(P('error', 'tune-set-type', 'bmashup.tune.set must be a list of strings', '', fname, at('bmashup.tune.set')))
    seen = {}
    setvals = {}
    for en in entries:
        f = 'bmashup.tune.set[%d]' % en['index']
        if en['key'] is None:
            probs.append(P('error', 'tune-entry-format', 'bmashup.tune.set entry %d is not "Group | Name = value"' % en['index'],
                           'write "Group | Name = number"', fname, en['line'], field=f))
            continue
        row = idx.get(en['key'])
        if row is None:
            probs.append(P('error', 'tune-unknown-row', '"%s" is not a tuning value the host knows (not in the catalogue)'
                           % en['key'], 'pick the row in the editor (spelling and spaces count)', fname, en['line'], field=f,
                           row=en['key'], obj='tune-entry:%d' % en['index']))
            continue
        if en['key'] in seen:
            probs.append(P('error', 'tune-duplicate', '%s is set twice (lines %d and %d)' % (en['key'], seen[en['key']], en['line']),
                           'keep one', fname, en['line'], field=f, row=en['key'], obj='tune-row:' + en['key']))
        seen[en['key']] = en['line']
        setvals[en['key']] = en['value']
        if row['family'] == 'ai' or (NUM.match(en['value'] or '') and float(en['value']) < 0):
            needed = max(needed, 2)
        for code, msg, fix in check_value(row, en['value'], ver if isinstance(ver, int) else None):
            sev = 'warn' if fix == 'warn' else 'error'
            probs.append(P(sev, code, msg, '' if fix == 'warn' else fix, fname, en['line'], field=f, row=en['key'],
                           obj='tune-row:' + en['key']))
    if sliders:
        needed = 3
        if ver != 3:
            probs.append(P('error', 'sliders-need-version-3', 'bmashup.tune.sliders needs [bmashup.tune] version = 3', 'set version = 3',
                           fname, at('bmashup.tune.version') or at('bmashup.tune.sliders'), field='bmashup.tune.version',
                           obj='tune-version'))
    srows = {}
    for sl in sliders:
        f = 'bmashup.tune.sliders[%d]' % sl['index']
        ps, why = parse_slider(sl['text'])
        if not ps:
            probs.append(P('error', 'slider-format', why, 'write "Group | Name = default : min .. max [step s] [label text]"',
                           fname, sl['line'], field=f))
            continue
        row = idx.get(ps['row'])
        if row is None:
            probs.append(P('error', 'slider-unknown-row', 'slider "%s" is not a tuning value the host knows' % ps['row'], '', fname,
                           sl['line'], field=f, row=ps['row']))
            continue
        if ps['row'] in srows:
            probs.append(P('error', 'slider-duplicate', 'slider "%s": the row has a slider already' % ps['row'], 'keep one', fname,
                           sl['line'], field=f, row=ps['row'], obj='tune-slider:' + ps['row']))
        srows[ps['row']] = sl['line']
        if not row['verified_range']:
            probs.append(P('warn', 'slider-no-verified-range', 'slider "%s": the row has no verified range (only the host\'s '
                           'admission limit %g .. %g); the editor shows no slider for it' % (ps['row'], row['limit']['lo'],
                                                                                             row['limit']['hi']),
                           'keep it only if you tested the range yourself', fname, sl['line'], field=f, row=ps['row'],
                           obj='tune-slider:' + ps['row']))
        for code, msg, fix in check_slider(ps, row, setvals.get(ps['row'])):
            probs.append(P('error', code, msg, fix, fname, sl['line'], field=f, row=ps['row'], obj='tune-slider:' + ps['row']))
    if len(sliders) > SLIDERS_PER_MOD:
        probs.append(P('error', 'sliders-too-many', 'at most %d sliders a mod (%d here)' % (SLIDERS_PER_MOD, len(sliders)), '',
                       fname, at('bmashup.tune.sliders'), field='bmashup.tune.sliders'))
    if isinstance(ver, int) and 1 <= ver <= 3 and ver > needed:
        probs.append(P('info', 'tune-version-higher', 'version %d is higher than needed (%d): an older host refuses the mod alone'
                       % (ver, needed), 'lower it to %d to reach older hosts' % needed, fname, at('bmashup.tune.version'),
                       field='bmashup.tune.version', obj='tune-version'))
    if host_info and folder:
        r = bmcompat.check_mod(host_info, folder)
        for x in r['reasons']:
            if 'is missing from the mod folder' in x or x.startswith('contains native code'):
                probs.append(P('info', 'compat-module', 'host %s: %s (a source project: the Test step builds the module and checks '
                               'the staged folder again)' % (host_info.get('host_name'), x), '', fname, None, obj='compat'))
                continue
            probs.append(P('error' if r['level'] == bmcompat.BLOCKED else 'warn', 'compat', 'host %s (platform %s): %s'
                           % (host_info.get('host_name'), host_info.get('platform'), x), 'see the reason', fname, None,
                           obj='compat'))
    elif folder:
        probs.append(P('info', 'compat-unchecked', 'compatibility with a host was not checked: needs a built host (Build Mashup first; the check '
                       'reads the HOST_INFO.json of your build)', 'build the host, then validate again', fname, None, obj='compat'))
    return {'ok': not any(p['sev'] == 'error' for p in probs), 'problems': probs, 'version': ver, 'needed_version': needed,
            'entries': entries, 'sliders': sliders}


def validate_project(folder, cat, host_info=None):
    p = os.path.join(folder, 'mod.toml')
    if not os.path.isfile(p):
        return {'ok': False, 'problems': [P('error', 'no-mod-toml', 'no mod.toml in %s' % folder,
                                            'make a project from a template first', 'mod.toml')], 'entries': [], 'sliders': []}
    try:
        text, _ = wbn_toml.read(p)
    except UnicodeDecodeError as e:
        return {'ok': False, 'problems': [P('error', 'not-utf8', 'mod.toml is not UTF-8: %s' % e, 'save it as UTF-8')],
                'entries': [], 'sliders': []}
    r = validate_text(text, cat, host_info, folder)
    try:
        plug = tomllib.loads(text.lstrip('﻿')).get('plugin')
    except tomllib.TOMLDecodeError:
        plug = None
    if isinstance(plug, dict):
        r['problems'].append(P('info', 'has-plugin', 'mod.toml declares [plugin] (native code): this is not a data-only mod',
                               'use the plugin workflow', 'mod.toml', field='plugin'))
    return r


def format_problem(p):
    loc = p['file'] + (':%d' % p['line'] if p.get('line') else '') + (':%d' % p['col'] if p.get('col') else '')
    return '%-5s %s  %s%s%s' % (p['sev'].upper(), loc, p['msg'], (' [%s]' % p['field']) if p.get('field') else '',
                                ('  -> ' + p['fix']) if p.get('fix') else '')
