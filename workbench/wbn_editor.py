"""wbn_editor - the tuning editor model shared by the CLI (wbn.py tune ...) and the GUI (wbn_gui.py). Nothing here touches the
disk except save().

    s = TuneSession(project, catalogue)
    s.rows(filter_text)                 catalogue rows + the project's value / slider for each, unknown rows of the file
    s.set(key, value_text)              -> problems (refused edits change nothing); the edit is PENDING
    s.remove(key); s.set_slider(row, default, lo, hi, step, label); s.remove_slider(row)
    s.preview()                         unified diff of the pending text against the file as read
    s.save()                            atomic replace, refused when the file changed on disk or the text would not parse
A row without a verified range has no slider in the editor (slider_allowed False + the reason); its value is typed.
Version: an edit that needs a newer [bmashup.tune] version (AI rows / negative values -> 2, sliders -> 3) raises it in the same
pending text and says so; the editor never lowers a version by itself.
"""
import os

import wbn_catalogue
import wbn_rules
import wbn_toml


class TuneSession:
    def __init__(self, project, cat, host_info=None):
        self.project = os.path.abspath(project)
        self.path = os.path.join(self.project, 'mod.toml')
        self.cat, self.idx, self.host_info = cat, wbn_catalogue.index(cat), host_info
        self.reload()

    def reload(self):
        self.orig, self.sha = wbn_toml.read(self.path)
        self.text = self.orig
        self.notes = []

    @property
    def dirty(self):
        return self.text != self.orig

    def _doc(self):
        return wbn_toml.parse(self.text)

    def version(self):
        return wbn_toml.tune_version(self._doc())

    def values(self):
        return {e['key']: e for e in wbn_toml.tune_entries(self._doc()) if e['key']}

    def sliders(self):
        return {s['row']: s for s in wbn_toml.tune_sliders(self._doc()) if s['row']}

    def rows(self, text=''):
        vals, sls = self.values(), self.sliders()
        out = []
        for r in wbn_catalogue.search(self.cat, text):
            out.append(self.row_view(r, vals.get(r['key']), sls.get(r['key'])))
        unknown = [e for k, e in vals.items() if k not in self.idx]
        return out, unknown

    def row_view(self, r, cur=None, sl=None):
        vr = r['verified_range']
        return {'key': r['key'], 'type': r['type'], 'unit': (r['unit'] or {}).get('text'),
                'description': (r['description'] or {}).get('text') or 'no description in the catalogue',
                'default': r['default']['text'], 'limit': '%g .. %g' % (r['limit']['lo'], r['limit']['hi']),
                'limit_rule': r['limit']['rule'], 'value': cur['value'] if cur else None, 'line': cur['line'] if cur else None,
                'slider_allowed': bool(vr) and not r['unread'],
                'slider_range': (vr['lo'], vr['hi']) if vr else None,
                'why_no_slider': None if vr else 'no verified range for this row (only the host\'s admission limit %g .. %g): '
                                                 'type a number' % (r['limit']['lo'], r['limit']['hi']),
                'mod_slider': sl['text'] if sl else None, 'applies': r['applies'], 'unread': r['unread'],
                'needs_version': r['needs_version']}

    def _raise_version(self, need):
        v = self.version()
        if v is None or v < need:
            self.text = wbn_toml.set_version(self.text, need)
            self.notes.append('[bmashup.tune] version raised to %d (needed by this edit)' % need)

    def set(self, key, value_text):
        r = self.idx.get(key)
        if r is None:
            return ['%r is not a catalogue row (pick a row in the editor)' % key]
        value_text = (value_text or '').strip()
        need = 2 if (r['family'] == 'ai' or value_text.startswith('-')) else 1
        probs = [m for c, m, f in wbn_rules.check_value(r, value_text, max(need, self.version() or 1)) if f != 'warn']
        if probs:
            return probs
        new = wbn_toml.set_value(self.text, key, value_text)
        bad = wbn_toml.check_parses(new)
        if bad:
            return ['the edit would not parse (%s): nothing changed' % bad]
        self.text = new
        self._raise_version(need)
        return []

    def remove(self, key):
        self.text = wbn_toml.remove_value(self.text, key)
        return []

    def slider_line(self, row, default, lo, hi, step=None, label=None):
        s = '%s = %s : %s .. %s' % (row, default, lo, hi)
        if step:
            s += ' step %s' % step
        if label:
            s += ' label %s' % label
        return s

    def set_slider(self, row, default, lo, hi, step=None, label=None):
        r = self.idx.get(row)
        if r is None:
            return ['%r is not a catalogue row' % row]
        if not r['verified_range']:
            return ['%s has no verified range: the editor offers no slider for it (type a value instead)' % row]
        line = self.slider_line(row, default, lo, hi, step, label)
        ps, why = wbn_rules.parse_slider(line)
        if not ps:
            return [why]
        cur = self.values().get(row)
        probs = [m for c, m, f in wbn_rules.check_slider(ps, r, cur['value'] if cur else None)]
        if probs:
            return probs
        self.text = wbn_toml.set_slider(self.text, row, line)
        self._raise_version(3)
        return []

    def remove_slider(self, row):
        self.text = wbn_toml.remove_slider(self.text, row)
        return []

    def preview(self):
        return wbn_toml.diff(self.orig, self.text)

    def check(self):
        return wbn_rules.validate_text(self.text, self.cat, None, None)

    def save(self):
        if not self.dirty:
            return False, 'nothing to save'
        ok, msg = wbn_toml.save(self.path, self.text, self.sha)
        if ok:
            self.reload()
        return ok, msg
