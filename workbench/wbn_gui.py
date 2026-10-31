"""wbn_gui.py - Workbench window (Workbench 0.30): New project -> Tune -> Test this project (plan only, never launches).
Every action calls the same functions as the CLI (wbn.py); the GUI only shows them. Python standard library (tkinter).

    py -3 -B wbn_gui.py [--settings FILE] [--project FOLDER] [--kit KIT]
"""
import argparse
import hashlib
import json
import os
import queue
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wb_core as core  # noqa: E402
import wb_theme  # noqa: E402
import wbn_catalogue  # noqa: E402
import wbn_editor  # noqa: E402
import wbn_flow  # noqa: E402
import wbn_rules  # noqa: E402
import wbn_templates  # noqa: E402

TITLE = 'Burnout Mashup Workbench %s - developer workflow' % core.VERSION


def _h(t):
    return hashlib.sha256((t or '').encode('utf-8')).hexdigest()


class App:
    def __init__(self, root, settings=None, project=None, kit=None):
        self.root = root
        self.cat = wbn_catalogue.load()
        self.settings_path = tk.StringVar(value=settings or '')
        self.project = tk.StringVar(value=project or '')
        self.kit = tk.StringVar(value=kit or wbn_flow.kit_beside() or '')
        self.q = queue.Queue()
        self.flow = None
        self.session = None
        self.previewed = None             # sha of the pending text the user last previewed (Save needs it)
        self.cur_key = None
        self.last_result = None
        root.title(TITLE)
        s = max(1.0, root.winfo_fpixels('1i') / 96.0)
        root.geometry('%dx%d' % (min(int(1100 * s), int(root.winfo_screenwidth() * 0.92)),
                                 min(int(760 * s), int(root.winfo_screenheight() * 0.85))))
        wb_theme.apply(root, compact=True)
        top = ttk.Frame(root, padding=(8, 6))
        top.pack(fill='x')
        ttk.Label(top, text='Project').pack(side='left')
        ttk.Entry(top, textvariable=self.project, width=70).pack(side='left', padx=4, fill='x', expand=True)
        ttk.Button(top, text='Browse', command=self.browse_project).pack(side='left')
        ttk.Button(top, text='Open', command=lambda: self.open_project()).pack(side='left', padx=4)
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill='both', expand=True, padx=6, pady=4)
        self.tab_new, self.tab_tune, self.tab_test = (ttk.Frame(self.nb, padding=8) for _ in range(3))
        self.nb.add(self.tab_new, text='1 New project')
        self.nb.add(self.tab_tune, text='2 Tune')
        self.nb.add(self.tab_test, text='3 Test this project')
        self._build_new(self.tab_new)
        self._build_tune(self.tab_tune)
        self._build_test(self.tab_test)
        self.status = ttk.Label(root, text='Ready.' if self.cat else 'NO EDITOR CATALOGUE (data\\EDITOR_CATALOGUE.json)', padding=(8, 2))
        self.status.pack(fill='x')
        root.bind('<Escape>', lambda e: self.cancel_test())
        wb_theme.finish(root)
        root.after(100, self.poll)
        if project:
            self.open_project(project)

    # ------------------------------------------------------------------ 1 new project
    def _build_new(self, f):
        g = ttk.Frame(f)
        g.pack(fill='x')
        self.tpl = tk.StringVar(value='tune-data')
        self.n_folder, self.n_id, self.n_name = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.n_module, self.n_density = tk.StringVar(), tk.StringVar(value='0.5')
        rows = [('Mod kit folder', self.kit), ('Template', None), ('New project folder', self.n_folder), ('Mod id', self.n_id),
                ('Display name', self.n_name), ('Module name (plugins)', self.n_module), ('Traffic density 0.0 .. 2.0', self.n_density)]
        for i, (lab, var) in enumerate(rows):
            ttk.Label(g, text=lab).grid(row=i, column=0, sticky='w', pady=2)
            if var is None:
                self.tpl_cb = ttk.Combobox(g, textvariable=self.tpl, values=list(wbn_templates.TEMPLATES), state='readonly', width=30)
                self.tpl_cb.grid(row=i, column=1, sticky='w')
                self.tpl_cb.bind('<<ComboboxSelected>>', lambda e: self.show_template())
            else:
                ttk.Entry(g, textvariable=var, width=80).grid(row=i, column=1, sticky='we')
        g.columnconfigure(1, weight=1)
        b = ttk.Frame(f)
        b.pack(fill='x', pady=6)
        ttk.Button(b, text='Show requirements', command=self.show_template).pack(side='left')
        ttk.Button(b, text='Create project', command=self.create_project).pack(side='left', padx=6)
        self.new_out = tk.Text(f, height=16, wrap='word', font=('Consolas', 9))
        self.new_out.pack(fill='both', expand=True)

    def show_template(self):
        lst = {t['id']: t for t in wbn_templates.list_templates(self.kit.get())}
        t = lst.get(self.tpl.get())
        self._text(self.new_out, json.dumps(t, indent=1) if t else 'unknown template')
        return t

    def create_project(self, **over):
        r = wbn_templates.create(over.get('kit', self.kit.get()), over.get('template', self.tpl.get()),
                                 over.get('folder', self.n_folder.get().strip()), over.get('mod_id', self.n_id.get().strip()),
                                 over.get('name', self.n_name.get()), over.get('module', self.n_module.get().strip() or None),
                                 over.get('density', self.n_density.get().strip() or None), over.get('entries'), self.cat)
        self._text(self.new_out, '%s %s\n%s' % (r['verdict'], r.get('project'), '\n'.join('  ' + x for x in r['problems'] +
                                                                                           ['note: ' + w for w in r.get('warnings', [])])))
        if r['ok']:
            self.project.set(r['project'])
            self.open_project(r['project'])
        return r

    # ------------------------------------------------------------------ 2 tune
    def _build_tune(self, f):
        left = ttk.Frame(f)
        left.pack(side='left', fill='both', expand=True)
        sf = ttk.Frame(left)
        sf.pack(fill='x')
        ttk.Label(sf, text='Search').pack(side='left')
        self.search = tk.StringVar()
        e = ttk.Entry(sf, textvariable=self.search)
        e.pack(side='left', fill='x', expand=True, padx=4)
        self.search.trace_add('write', lambda *a: self.refresh_rows())
        self.only_set = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text='only rows in this mod', variable=self.only_set, command=self.refresh_rows).pack(side='left')
        cols = ('value', 'default', 'limit', 'slider')
        self.tree = ttk.Treeview(left, columns=cols, height=14)
        self.tree.heading('#0', text='Row (Group | Name)')
        for c, w in zip(cols, (80, 170, 130, 70)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, stretch=False)
        self.tree.column('#0', width=420)
        self.tree.pack(fill='both', expand=True, pady=4)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.on_select())
        pf = ttk.Frame(left)
        pf.pack(fill='both', expand=True)
        ttk.Label(pf, text='Problems (double-click: go to the row / line)').pack(anchor='w')
        self.ptree = ttk.Treeview(pf, columns=('where', 'msg'), show='headings', height=6)
        self.ptree.heading('where', text='file:line [field]')
        self.ptree.heading('msg', text='problem -> fix')
        self.ptree.column('where', width=230, stretch=False)
        self.ptree.column('msg', width=640)
        self.ptree.pack(fill='both', expand=True)
        self.ptree.bind('<Double-1>', lambda e: self.goto_problem(self.ptree, self._tune_probs))
        self._tune_probs = []
        right = ttk.Frame(f, padding=(8, 0))
        right.pack(side='left', fill='both')
        self.detail = tk.Text(right, height=11, width=58, wrap='word', font=('Segoe UI', 9))
        self.detail.pack(fill='x')
        vf = ttk.LabelFrame(right, text='Value', padding=6)
        vf.pack(fill='x', pady=4)
        self.val = tk.StringVar()
        self.scale = ttk.Scale(vf, orient='horizontal', command=self.on_scale)
        self.scale.pack(fill='x')
        self.no_slider = ttk.Label(vf, text='', foreground=wb_theme.MUTED, wraplength=380)
        self.no_slider.pack(fill='x')
        ef = ttk.Frame(vf)
        ef.pack(fill='x')
        ttk.Entry(ef, textvariable=self.val, width=16).pack(side='left')
        ttk.Button(ef, text='Set value', command=lambda: self.do_set()).pack(side='left', padx=4)
        ttk.Button(ef, text='Remove value', command=self.do_remove).pack(side='left')
        sl = ttk.LabelFrame(right, text='MODS-page slider (rows with a verified range only)', padding=6)
        sl.pack(fill='x')
        self.s_def, self.s_min, self.s_max, self.s_step, self.s_label = (tk.StringVar() for _ in range(5))
        for i, (lab, var) in enumerate((('default', self.s_def), ('min', self.s_min), ('max', self.s_max), ('step', self.s_step),
                                        ('label', self.s_label))):
            ttk.Label(sl, text=lab).grid(row=0, column=2 * i, sticky='w')
            ttk.Entry(sl, textvariable=var, width=8 if lab != 'label' else 14).grid(row=0, column=2 * i + 1, padx=2)
        self.btn_slider = ttk.Button(sl, text='Declare slider', command=lambda: self.do_slider())
        self.btn_slider.grid(row=1, column=0, columnspan=4, sticky='w', pady=2)
        ttk.Button(sl, text='Remove slider', command=self.do_remove_slider).grid(row=1, column=4, columnspan=4, sticky='w')
        bf = ttk.Frame(right)
        bf.pack(fill='x', pady=4)
        ttk.Button(bf, text='Preview changes', command=self.do_preview).pack(side='left')
        self.btn_save = ttk.Button(bf, text='Save', command=lambda: self.do_save(), state='disabled')
        self.btn_save.pack(side='left', padx=4)
        ttk.Button(bf, text='Discard', command=self.do_discard).pack(side='left')
        ttk.Button(bf, text='Validate project', command=lambda: self.validate_project()).pack(side='left', padx=4)
        self.view = tk.Text(right, height=14, width=58, wrap='none', font=('Consolas', 8))
        self.view.pack(fill='both', expand=True)
        self.view.tag_configure('hit', background='#fff2a8')

    def browse_project(self):
        p = filedialog.askdirectory(title='Project folder (holds mod.toml)')
        if p:
            self.project.set(os.path.normpath(p))
            self.open_project()

    def open_project(self, path=None):
        p = path or self.project.get().strip()
        if not p or not os.path.isfile(os.path.join(p, 'mod.toml')):
            self.status['text'] = 'no mod.toml in %s' % p
            return False
        self.project.set(os.path.abspath(p))
        self.session = wbn_editor.TuneSession(p, self.cat)
        self.previewed = None
        self.refresh_rows()
        self.refresh_view()
        self.status['text'] = 'opened %s' % p
        return True

    def refresh_rows(self):
        self.tree.delete(*self.tree.get_children())
        if not self.session:
            return
        rows, unknown = self.session.rows(self.search.get())
        for r in rows:
            if self.only_set.get() and r['value'] is None:
                continue
            self.tree.insert('', 'end', iid=r['key'], text=r['key'], values=(r['value'] if r['value'] is not None else '',
                                                                            r['default'][:40], r['limit'],
                                                                            'yes' if r['slider_allowed'] else 'no'))
        for u in unknown:
            iid = 'unknown:%d' % u['index']
            self.tree.insert('', 'end', iid=iid, text='UNKNOWN (kept as written): %s' % u['key'],
                             values=(u['value'], '', '', 'no'))
        self.rows_shown = [i for i in self.tree.get_children()]

    def refresh_view(self, line=None):
        t = self.session.text if self.session else ''
        self._text(self.view, t)
        self.check_pending()
        if line:
            self.view.tag_add('hit', '%d.0' % line, '%d.end' % line)
            self.view.see('%d.0' % line)

    def check_pending(self):
        if not self.session:
            return
        r = self.session.check()
        self._tune_probs = r['problems']
        self._fill_probs(self.ptree, self._tune_probs)
        self.btn_save['state'] = 'normal' if (self.session.dirty and self.previewed == _h(self.session.text)) else 'disabled'

    def _fill_probs(self, tree, probs):
        tree.delete(*tree.get_children())
        for i, p in enumerate(probs):
            where = '%s%s%s' % (p.get('file') or '', ':%d' % p['line'] if p.get('line') else '',
                                ' [%s]' % p['field'] if p.get('field') else '')
            tree.insert('', 'end', iid=str(i), values=(where, '%s: %s%s' % (p['sev'].upper(), p['msg'],
                                                                           ('  -> ' + p['fix']) if p.get('fix') else '')))

    def select_row(self, key):
        self.search.set('')
        self.only_set.set(False)
        self.refresh_rows()
        if self.tree.exists(key):
            self.tree.selection_set(key)
            self.tree.see(key)
            self.on_select()
            return True
        return False

    def on_select(self):
        sel = self.tree.selection()
        if not sel or not self.session or sel[0].startswith('unknown:'):
            self.cur_key = None
            return
        key = sel[0]
        self.cur_key = key
        r = wbn_catalogue.index(self.cat)[key]
        v = self.session.row_view(r, self.session.values().get(key), self.session.sliders().get(key))
        txt = ['%s' % key, 'type: %s   unit: %s' % (v['type'], v['unit'] or 'none in the row name'),
               'description: %s%s' % (v['description'], (' (%s)' % r['description']['source']) if r['description'] else ''),
               'default: %s  (%s)' % (v['default'], r['default']['source']),
               'host limit: %s  - %s (%s)' % (v['limit'], r['limit']['rule'], r['limit']['source']),
               'applies: %s' % v['applies'], 'needs [bmashup.tune] version >= %d' % v['needs_version'],
               'this mod: %s%s' % (v['value'] if v['value'] is not None else 'not set',
                                  ' (line %d)' % v['line'] if v['line'] else ''),
               'MODS-page slider in this mod: %s' % (v['mod_slider'] or 'none')]
        if r['limit'].get('note'):
            txt.append(r['limit']['note'])
        self._text(self.detail, '\n'.join(txt))
        self.val.set(v['value'] if v['value'] is not None else (r['default']['text'] if r['default']['value'] is not None else ''))
        self.slider_shown = v['slider_allowed']
        if v['slider_allowed']:
            lo, hi = v['slider_range']
            self.scale.configure(from_=lo, to=hi, state='normal')
            try:
                self.scale.set(float(self.val.get()))
            except ValueError:
                self.scale.set(lo)
            self.scale.pack(fill='x', before=self.no_slider)
            self.no_slider['text'] = 'verified range %g .. %g (%s)' % (lo, hi, r['verified_range']['source'])
            self.btn_slider['state'] = 'normal'
            self.s_def.set(self.val.get())
            self.s_min.set('%g' % lo)
            self.s_max.set('%g' % hi)
        else:
            self.scale.pack_forget()
            self.no_slider['text'] = 'No slider: ' + v['why_no_slider']
            self.btn_slider['state'] = 'disabled'
        if v['line']:
            self.refresh_view(v['line'])

    def on_scale(self, x):
        if not self.cur_key:
            return
        r = wbn_catalogue.index(self.cat)[self.cur_key]
        v = float(x)
        self.val.set(str(int(round(v))) if r['type'] == 'whole number' else ('%.3f' % v).rstrip('0').rstrip('.'))

    def _after_edit(self, probs, what):
        if probs:
            messagebox.showwarning('Not changed', '\n'.join(probs)) if not getattr(self, 'quiet', False) else None
            self.status['text'] = 'REFUSED: ' + probs[0]
        else:
            self.status['text'] = '%s (pending: Preview changes, then Save)%s' % (what, ('; ' + '; '.join(self.session.notes))
                                                                                  if self.session.notes else '')
        self.previewed = None
        self.refresh_rows()
        if self.cur_key and self.tree.exists(self.cur_key):
            self.tree.selection_set(self.cur_key)
        self.refresh_view()
        return probs

    def do_set(self, value=None):
        if not (self.session and self.cur_key):
            return ['select a row first']
        return self._after_edit(self.session.set(self.cur_key, value if value is not None else self.val.get()), 'value set')

    def do_remove(self):
        if self.session and self.cur_key:
            return self._after_edit(self.session.remove(self.cur_key), 'value removed')

    def do_slider(self):
        if not (self.session and self.cur_key):
            return ['select a row first']
        return self._after_edit(self.session.set_slider(self.cur_key, self.s_def.get().strip(), self.s_min.get().strip(),
                                                        self.s_max.get().strip(), self.s_step.get().strip() or None,
                                                        self.s_label.get().strip() or None), 'slider declared')

    def do_remove_slider(self):
        if self.session and self.cur_key:
            return self._after_edit(self.session.remove_slider(self.cur_key), 'slider removed')

    def do_preview(self):
        if not self.session:
            return ''
        d = self.session.preview()
        self._text(self.view, d or '(no pending change)')
        self.previewed = _h(self.session.text) if d else None
        self.btn_save['state'] = 'normal' if d else 'disabled'
        self.status['text'] = 'PREVIEW of the pending change: Save writes exactly this' if d else 'nothing pending'
        return d

    def do_save(self):
        if not self.session or self.previewed != _h(self.session.text):
            self.status['text'] = 'Preview the changes first (Save writes only a previewed change)'
            return False, self.status['text']
        ok, msg = self.session.save()
        self.status['text'] = msg
        self.previewed = None
        self.refresh_rows()
        self.refresh_view()
        return ok, msg

    def do_discard(self):
        if self.session:
            self.session.reload()
            self.previewed = None
            self.refresh_rows()
            self.refresh_view()

    def validate_project(self):
        if not self.session:
            return None
        info = wbn_templates.host_info(self.kit.get()) if self.kit.get() else None
        r = wbn_rules.validate_project(self.project.get(), self.cat, info)
        self._tune_probs = r['problems']
        self._fill_probs(self.ptree, self._tune_probs)
        self.status['text'] = ('VALID' if r['ok'] else 'NOT VALID') + ' (the file on disk; pending edits are not saved)'
        return {'ok': r['ok'], 'problems': r['problems']}

    def goto_problem(self, tree, probs, index=None):
        sel = [index] if index is not None else [int(i) for i in tree.selection()]
        if not sel:
            return None
        p = probs[sel[0]]
        self.nb.select(self.tab_tune)
        obj = p.get('obj') or ''
        target = None
        if obj.startswith(('tune-row:', 'tune-slider:')):
            target = obj.split(':', 1)[1]
            self.select_row(target)
        if p.get('line'):
            self.refresh_view(p['line'])
        self.status['text'] = 'problem: %s' % p['msg']
        return {'row': target, 'line': p.get('line'), 'field': p.get('field')}

    # ------------------------------------------------------------------ 3 test
    def _build_test(self, f):
        g = ttk.Frame(f)
        g.pack(fill='x')
        ttk.Label(g, text='Settings file').pack(side='left')
        ttk.Entry(g, textvariable=self.settings_path, width=80).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(g, text='Browse', command=self.browse_settings).pack(side='left')
        b = ttk.Frame(f)
        b.pack(fill='x', pady=4)
        self.btn_run = ttk.Button(b, text='Test this project (plan only)', command=lambda: self.run_test())
        self.btn_run.pack(side='left')
        self.btn_cancel = ttk.Button(b, text='Cancel', command=self.cancel_test, state='disabled')
        self.btn_cancel.pack(side='left', padx=4)
        ttk.Button(b, text='Last successful output', command=self.show_last).pack(side='left')
        self.prog = ttk.Progressbar(b, length=260, mode='determinate', maximum=len(wbn_flow.STEPS))
        self.prog.pack(side='left', padx=8)
        self.step_lbl = ttk.Label(b, text='')
        self.step_lbl.pack(side='left')
        self.steps_tree = ttk.Treeview(f, columns=('state', 'msg'), show='headings', height=len(wbn_flow.STEPS))
        for c, w in (('state', 90), ('msg', 760)):
            self.steps_tree.heading(c, text=c)
            self.steps_tree.column(c, width=w)
        self.steps_tree.pack(fill='x')
        ttk.Label(f, text='Problems (double-click: go to the row / line in the Tune tab)').pack(anchor='w')
        self.tptree = ttk.Treeview(f, columns=('where', 'msg'), show='headings', height=4)
        self.tptree.heading('where', text='file:line [field]')
        self.tptree.heading('msg', text='problem')
        self.tptree.column('where', width=230, stretch=False)
        self.tptree.pack(fill='x')
        self.tptree.bind('<Double-1>', lambda e: self.goto_problem(self.tptree, self._test_probs))
        self._test_probs = []
        self.test_out = tk.Text(f, height=14, wrap='none', font=('Consolas', 8))
        self.test_out.pack(fill='both', expand=True)

    def browse_settings(self):
        p = filedialog.askopenfilename(title='Workbench settings', filetypes=[('JSON', '*.json')])
        if p:
            self.settings_path.set(os.path.normpath(p))

    def run_test(self, wait=False):
        if self.flow and not self.flow.done.is_set():
            self.status['text'] = 'a test is already running'
            return None
        if self.session and self.session.dirty:
            self.status['text'] = 'unsaved edits: Preview + Save (or Discard) first - the test uses the file on disk'
            return None
        s, bad = wbn_flow.load_settings(self.settings_path.get().strip() or None, kit=self.kit.get().strip() or None)
        if bad:
            self._text(self.test_out, '\n'.join(bad))
            return None
        self.steps_tree.delete(*self.steps_tree.get_children())
        for st in wbn_flow.STEPS:
            self.steps_tree.insert('', 'end', iid=st, values=('pending', st))
        self.prog['value'] = 0
        self._text(self.test_out, '')
        self.flow = wbn_flow.Flow(self.project.get().strip(), s, on_event=self.q.put)
        self.btn_run['state'], self.btn_cancel['state'] = 'disabled', 'normal'
        self.flow.start()
        if wait:
            self.flow.wait()
            self.poll(once=True)
        return self.flow

    def cancel_test(self):
        if self.flow and not self.flow.done.is_set():
            self.flow.cancel()
            self.status['text'] = 'cancelling (stopping the running tool)...'

    def poll(self, once=False):
        n = 0
        while n < 400:
            try:
                e = self.q.get_nowait()
            except queue.Empty:
                break
            n += 1
            if 'log' in e:
                self.test_out.insert('end', e['log'] + '\n')
                continue
            st = e.get('step')
            if st in wbn_flow.STEPS:
                self.steps_tree.item(st, values=(e['state'], e.get('msg') or st))
                self.step_lbl['text'] = '%s: %s' % (st, e['state'])
                if e['state'] in ('done', 'skipped'):
                    self.prog['value'] = e.get('n', 0)
        if self.flow and self.flow.done.is_set() and str(self.btn_cancel['state']) != 'disabled':
            self.finish_test()
        if not once:
            self.root.after(150, self.poll)

    def finish_test(self):
        r = self.flow.result
        self.last_result = r
        self.btn_run['state'], self.btn_cancel['state'] = 'normal', 'disabled'
        self._test_probs = r['problems']
        self._fill_probs(self.tptree, self._test_probs)
        self._text(self.test_out, wbn_flow.summary(r))
        self.status['text'] = 'Test this project: %s' % r['verdict']

    def show_last(self):
        s, _ = wbn_flow.load_settings(self.settings_path.get().strip() or None, kit=self.kit.get().strip() or None)
        _, mod_id = wbn_flow.project_kind(self.project.get().strip())
        r = wbn_flow.last_success(s, mod_id) if mod_id else None
        self._text(self.test_out, json.dumps(r, indent=1) if r else 'no successful run recorded for %s' % mod_id)
        return r

    # ------------------------------------------------------------------ helpers
    def _text(self, w, t):
        w.configure(state='normal')
        w.delete('1.0', 'end')
        w.insert('end', t)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--settings')
    ap.add_argument('--project')
    ap.add_argument('--kit')
    a = ap.parse_args(argv)
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root, a.settings, a.project, a.kit)
    root.mainloop()


if __name__ == '__main__':
    main()
