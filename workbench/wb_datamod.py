"""wb_datamod - Workbench v0.29 (release readiness R1): New data mod - a tuning-values mod (mod.toml [bmashup.tune]) with no
code and no game files, made from the user's own values.

The project is a plain mod folder (mod.toml + README.txt); the Workbench's existing "Import folder -> Validate -> Stage" flow
validates and stages it (no build step: nothing is compiled). Keys come from the tuning catalogue the kit ships
(docs\\TUNING_CATALOGUE.json, written by kit_tools\\make_tune_catalogue.py from the host's own catalogue); without it any
"Group | Name" key may be typed (the validator then decides). Values are checked against the catalogue's limit rule
(0 .. 16 x max(game value, 1)). Nothing is written unless every check passed; an existing non-empty folder is never written.
v0.30 fix: a key the Workbench's editor catalogue knows (data\\EDITOR_CATALOGUE.json, wbn_rules = the developer workflow's
rules) is checked with the host's own row limit (AI rows: from the host's code default, not the kit's placeholder 0; signed
rows -B .. B; never-read rows refused), and mod.toml gets the [bmashup.tune] version its values need (AI rows / negative
values: 2; v0.29 always wrote 1, which the host refuses for AI rows).

    py -3 -B wb_datamod.py FOLDER MOD_ID "NAME" "Group | Name = value" [...]      (CLI; exit 0 created, 3 refused)
"""
import datetime
import json
import os
import re
import shutil
import sys

import wb_core as core
import wb_project

try:                                   # v0.30: the editor catalogue + host rules of the developer workflow
    import wbn_catalogue
    import wbn_rules
    _EROWS = wbn_catalogue.index(wbn_catalogue.load())
except Exception:                      # noqa: BLE001 - without it the v0.29 rule applies
    _EROWS = {}


def editor_row(key):
    """the editor catalogue row of a key (host limits, family, flags) or None"""
    return _EROWS.get(key)


def needed_version(entries):
    """[bmashup.tune] version the values need: 2 for AI rows or negative values, else 1 (sliders are not written here)"""
    v = 1
    for e in entries:
        k, _, val = e.rpartition('=')
        r = editor_row(k.strip())
        if (r and r['family'] == 'ai') or k.strip().startswith('AI/') or val.strip().startswith('-'):
            v = 2
    return v

CATALOGUE_REL = os.path.join('docs', 'TUNING_CATALOGUE.json')
_ENTRY = re.compile(r'^\s*([^|=]+?)\s*\|\s*([^=]+?)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\s*$')


def catalogue(cfg):
    """-> {key: {'type', 'game'}} from the kit's catalogue, or {} when the kit has none"""
    p = os.path.join(cfg.get('kit') or '', CATALOGUE_REL)
    try:
        d = json.load(open(p, encoding='utf-8'))
        return {v['key']: v for v in d.get('values', []) if isinstance(v, dict) and 'key' in v}
    except (OSError, ValueError):
        return {}


def check_entries(entries, cat):
    """-> (normalised ['Group | Name = value'], problems) - each problem names the entry and what to change"""
    out, bad = [], []
    if not entries:
        bad.append('add at least one value ("Group | Name = value"; the picker lists them)')
    for i, e in enumerate(entries, 1):
        m = _ENTRY.match(e or '')
        if not m:
            bad.append('value %d %r: write it as "Group | Name = number"' % (i, e))
            continue
        key, val = '%s | %s' % (m.group(1), m.group(2)), float(m.group(3))
        if cat:
            row = cat.get(key)
            if row is None:
                bad.append('value %d: %r is not in the tuning catalogue (pick it from the list; spelling and spaces count)' % (i, key))
                continue
            er = editor_row(key)
            if row.get('type') == 'whole number' and val != int(val):
                bad.append('value %d (%s): a whole number is needed, not %s' % (i, key, m.group(3)))
            if er:                                                    # v0.30: the host's own row limit
                lo, hi = er['limit']['lo'], er['limit']['hi']
                if er['unread']:
                    bad.append('value %d (%s): the host refuses this row (never read by this game build)' % (i, key))
                elif not lo <= val <= hi:
                    bad.append('value %d (%s): %s is outside %g .. %g (%s)' % (i, key, m.group(3), lo, hi, er['limit']['rule']))
            else:
                lim = 16 * max(float(row.get('game') or 0), 1.0)
                if not (0 <= val <= lim) and not (row.get('host_addition') and -lim <= val <= lim):
                    bad.append('value %d (%s): %s is outside 0 .. %g (16 x the game value %g)' % (i, key, m.group(3), lim,
                                                                                         row.get('game')))
        out.append('%s = %s' % (key, m.group(3)))
    keys = [x.split(' = ')[0] for x in out]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        bad.append('a key is set twice: %s (keep one)' % ', '.join(dup))
    return out, bad


def mod_toml(mod_id, name, entries):
    return ('# made by Burnout Mashup Workbench %s (New data mod): your own tuning values, no game files\n'
            'id = "%s"\nname = "%s"\nversion = "1.0.0"\ndescription = "Tuning values: %d change(s)."\n\n'
            '[bmashup]\nplatform = ">=0.1.9"\nrequires = ["bmashup.tune>=1"]\n\n'
            '[bmashup.tune]\nversion = %d\nset = [\n%s]\n') % (core.VERSION, mod_id, name.replace('"', "'"), len(entries),
                                                             needed_version(entries),
                                                             ''.join('    "%s",\n' % e for e in entries))


def create(cfg, folder, mod_id, name, entries):
    """-> {'ok', 'verdict', 'project', 'problems', 'files'}"""
    cat = catalogue(cfg)
    norm, bad = check_entries(entries, cat)
    bad = [x for x in (wb_project.check_mod_id(mod_id), wb_project.check_name(name)) if x] + bad + \
        wb_project.folder_problems(cfg, folder)
    res = {'kind': 'new-data-mod', 'ok': False, 'project': folder, 'mod_id': mod_id, 'problems': bad,
           'catalogue': 'kit catalogue (%d keys)' % len(cat) if cat else 'no catalogue in this kit: keys not checked here'}
    if bad:
        res['verdict'] = 'NOT CREATED'
        return res
    folder = os.path.abspath(folder)
    files = {'mod.toml': mod_toml(mod_id, name, norm),
             'README.txt': 'A Burnout Mashup data mod made with the Workbench (%s).\nChange the values in mod.toml, then '
                           'Mod validation / Build / stage: Import folder.\n' % datetime.date.today().isoformat()}
    tmp = os.path.join(os.path.dirname(folder), '.%s.wb_new_%s' % (os.path.basename(folder),
                                                                    datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    os.makedirs(tmp)
    try:
        for f, t in files.items():
            with open(os.path.join(tmp, f), 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(t)
        if os.path.isdir(folder):
            if os.listdir(folder):
                raise FileExistsError(folder)
            os.rmdir(folder)
        os.rename(tmp, folder)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        res.update(verdict='NOT CREATED', problems=['could not create the project: %r' % e])
        return res
    res.update(ok=True, verdict='CREATED', project=folder, files=sorted(files))
    return res


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    r = create(core.load_config(), argv[0], argv[1], argv[2], argv[3:])
    print(json.dumps(r, indent=1))
    return 0 if r['ok'] else 3


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
