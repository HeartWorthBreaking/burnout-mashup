"""wbn.py - Workbench command line (choose feature -> configure -> build / validate / stage -> guarded test PLAN).
The GUI (wbn_gui.py) calls the same functions; `--json` prints the same records the GUI shows. Nothing here launches the game,
approves a plugin, or writes outside the project, the staging folder and the state folder you name.

  wbn.py templates --kit KIT                                            the templates, their requirements and capabilities
  wbn.py new TEMPLATE FOLDER --kit KIT --id ID --name NAME [--module M] [--density D] [--set "Group | Name = v" ...]
  wbn.py catalogue search [TEXT] | show KEY [--catalogue FILE]          the editor catalogue (descriptions / units / limits)
  wbn.py tune list PROJECT [--filter TEXT]                              rows with the project's values (slider yes / no + why)
  wbn.py tune set PROJECT KEY VALUE [--save]                            preview (unified diff); --save writes it (atomic)
  wbn.py tune remove PROJECT KEY [--save]
  wbn.py tune slider PROJECT ROW DEFAULT MIN MAX [--step S] [--label T] [--save]   only rows with a verified range
  wbn.py validate PROJECT [--kit KIT] [--json]                          offline checks, each linked to file:line [field]
  wbn.py test PROJECT --settings FILE [--json] [--KEY VALUE ...]        validate -> build -> stage -> launch PLAN (no launch)
  wbn.py last PROJECT --settings FILE                                   the last successful output of this project
  wbn.py settings-template FILE                                         writes an empty settings file to fill in
Exit: 0 ok, 1 refused / failed (problems printed), 2 usage, 3 settings missing.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wbn_catalogue  # noqa: E402
import wbn_editor  # noqa: E402
import wbn_flow  # noqa: E402
import wbn_rules  # noqa: E402
import wbn_templates  # noqa: E402


def _out(obj, as_json, text=None):
    if as_json or text is None:
        print(json.dumps(obj, indent=1, default=str))
    else:
        print(text)


def cmd_tune(a, cat):
    s = wbn_editor.TuneSession(a.project, cat)
    if a.action == 'list':
        rows, unknown = s.rows(a.filter or '')
        res = {'version': s.version(), 'rows': rows, 'unknown_entries': [{'key': u['key'], 'line': u['line']} for u in unknown]}
        if a.json:
            _out(res, True)
        else:
            for r in rows:
                if a.filter or r['value'] is not None:
                    print('%-70s value %-8s default %-26s limit %-16s %s' % (r['key'][:70], r['value'] if r['value'] is not None
                                                                             else '-', r['default'][:26], r['limit'],
                                                                             'slider %g..%g' % r['slider_range']
                                                                             if r['slider_allowed'] else 'numeric entry only'))
            for u in unknown:
                print('UNKNOWN ROW (kept as written) line %d: %s' % (u['line'], u['key']))
        return 0
    if a.action == 'set':
        probs = s.set(a.key, a.value)
    elif a.action == 'remove':
        probs = s.remove(a.key)
    else:
        probs = s.set_slider(a.key, a.value, a.min, a.max, a.step, a.label)
    res = {'ok': not probs, 'problems': probs, 'notes': s.notes, 'preview': s.preview(), 'saved': False}
    if not probs and a.save:
        ok, msg = s.save()
        res.update(saved=ok, save_message=msg, ok=ok)
    if a.json:
        _out(res, True)
    else:
        print('\n'.join(['REFUSED: ' + p for p in probs] + s.notes))
        print(res['preview'] or '(no change)')
        if a.save:
            print(res.get('save_message'))
        elif not probs:
            print('PREVIEW ONLY: add --save to write it')
    return 0 if res['ok'] else 1


def main(argv):
    ap = argparse.ArgumentParser(description='Workbench CLI')
    ap.add_argument('cmd', choices=['templates', 'new', 'catalogue', 'tune', 'validate', 'test', 'last', 'settings-template'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--kit')
    ap.add_argument('--id', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--module')
    ap.add_argument('--density')
    ap.add_argument('--set', action='append', default=[])
    ap.add_argument('--catalogue')
    ap.add_argument('--filter')
    ap.add_argument('--step')
    ap.add_argument('--label')
    ap.add_argument('--save', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--settings')
    for k in wbn_flow.SETTING_KEYS:
        if k not in ('kit', 'catalogue'):
            ap.add_argument('--' + k.replace('_', '-'), dest='s_' + k)
    a = ap.parse_args(argv)
    cat = wbn_catalogue.load(a.catalogue)
    if not a.kit and a.cmd in ('templates', 'new', 'validate'):
        a.kit = wbn_flow.kit_beside()             # a kit folder around <kit>\workbench only (marker files)
    if a.cmd == 'templates':
        _out(wbn_templates.list_templates(a.kit), True)
        return 0
    if a.cmd == 'new':
        if len(a.args) != 2 or not a.kit:
            print(__doc__)
            return 2
        r = wbn_templates.create(a.kit, a.args[0], a.args[1], a.id, a.name, a.module, a.density, a.set, cat)
        _out(r, a.json, '%s %s\n%s' % (r['verdict'], r.get('project'), '\n'.join('  ' + x for x in r['problems'] +
                                                                              ['note: ' + w for w in r.get('warnings', [])])))
        return 0 if r['ok'] else 1
    if a.cmd == 'catalogue':
        if not a.args:
            print(__doc__)
            return 2
        if a.args[0] == 'show':
            r = wbn_catalogue.index(cat).get(' '.join(a.args[1:]))
            _out(r or {'ok': False, 'why': 'not a catalogue key'}, True)
            return 0 if r else 1
        rows = wbn_catalogue.search(cat, ' '.join(a.args[1:]))
        _out([{'key': r['key'], 'type': r['type'], 'unit': (r['unit'] or {}).get('text'), 'default': r['default']['text'],
               'limit': [r['limit']['lo'], r['limit']['hi']], 'slider': bool(r['verified_range'])} for r in rows], True)
        return 0
    if a.cmd == 'tune':
        if len(a.args) < 2:
            print(__doc__)
            return 2
        a.action, a.project = a.args[0], a.args[1]
        rest = a.args[2:]
        need = {'list': 0, 'set': 2, 'remove': 1, 'slider': 4}.get(a.action)
        if need is None or len(rest) != need:
            print(__doc__)
            return 2
        a.key = rest[0] if rest else None
        a.value = rest[1] if len(rest) > 1 else None
        a.min, a.max = (rest[2], rest[3]) if len(rest) == 4 else (None, None)
        return cmd_tune(a, cat)
    if a.cmd == 'settings-template':
        if len(a.args) != 1 or os.path.exists(a.args[0]):
            print('give one NEW file name')
            return 2
        d = {'schema': wbn_flow.SETTINGS_SCHEMA, 'note': 'paths may be relative to this file; empty = not set'}
        d.update({k: '' for k in wbn_flow.SETTING_KEYS})
        d['run_preflight'] = False
        with open(a.args[0], 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=1)
        print(a.args[0])
        return 0
    if len(a.args) != 1:
        print(__doc__)
        return 2
    project = a.args[0]
    over = {k: getattr(a, 's_' + k, None) for k in wbn_flow.SETTING_KEYS if k not in ('kit', 'catalogue')}
    over['kit'] = a.kit
    if not a.kit and not a.settings and wbn_flow.kit_beside():
        a.kit = wbn_flow.kit_beside()
    if over.get('run_preflight') is not None:
        over['run_preflight'] = over['run_preflight'].lower() in ('1', 'true', 'yes')
    s, bad = wbn_flow.load_settings(a.settings, **over)
    if a.cmd == 'validate':
        info = None
        if s.get('kit'):
            info = wbn_templates.host_info(s['kit'])
        r = wbn_rules.validate_project(project, cat, info)
        r = {'ok': r['ok'], 'problems': r['problems']}
        _out(r, a.json, ('VALID' if r['ok'] else 'NOT VALID') + ''.join('\n  ' + wbn_rules.format_problem(p) for p in r['problems']))
        return 0 if r['ok'] else 1
    if bad:
        _out({'ok': False, 'problems': bad}, a.json, '\n'.join(bad))
        return 3
    if a.cmd == 'last':
        kind, mod_id = wbn_flow.project_kind(project)
        r = wbn_flow.last_success(s, mod_id) if mod_id else None
        _out(r or {'ok': False, 'why': 'no successful run recorded for %s' % mod_id}, True)
        return 0 if r else 1
    r = wbn_flow.run_sync(project, s, on_event=(lambda e: print('[%s] %s %s' % (e.get('step'), e.get('state'), e.get('msg') or ''),
                                                                   flush=True) if 'step' in e else None) if not a.json else None)
    _out(r, a.json, wbn_flow.summary(r))
    return 0 if r['ok'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
