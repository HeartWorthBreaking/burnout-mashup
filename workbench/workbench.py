"""Burnout Mashup Workbench (version: wb_core.VERSION) - a small Windows window over the release pipeline (release.py), the mod validator (bmpack)
and the verified example recipes (wb_stage). Paths: Settings tab (Discover / Check / Save -> workbench.json), or options:

    py -3 -B workbench.py [--pipeline DIR] [--kit DIR] [--game-data DIR] [--cc FILE] [--cmake FILE] [--ninja FILE] [--config FILE]

Python standard library only (tkinter). All work is done by wb_core (the same backend as `wb_core.py` on the command line).
No game launch except the Test profile tab's explicit Launch (v0.8: one guarded g_run boot, owner present; v0.9: headless or visible preset); no upload / push, no install into the game, no free command entry. Usage: README.md.
"""
import argparse
import getpass
import os
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wb_car  # noqa: E402
import wb_core as core  # noqa: E402
import wb_datamod  # noqa: E402
import wb_kit  # noqa: E402
import wb_profile  # noqa: E402
import wb_project  # noqa: E402
import wb_stage  # noqa: E402
import wb_theme  # noqa: E402
import wb_track  # noqa: E402

VERSION = core.VERSION                                   # one constant (wb_core.VERSION): the title cannot drift again
HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR_TITLE = 'Burnout Mashup track editor'
GUIDE = 'TRACK_EDITOR_GUIDE.md'


def console_python(exe=None):
    """the console Python beside the running one: the Workbench runs under pythonw.exe (no window), the editor needs a window"""
    exe = exe or sys.executable
    d, n = os.path.split(exe)
    if n.lower() == 'pythonw.exe' and os.path.isfile(os.path.join(d, 'python.exe')):
        return os.path.join(d, 'python.exe')
    return exe


def track_editor_command(project, config=None, python=None):
    """v0.32: the command line of the editor's own console window. Through cmd.exe so the window has a title and, when the editor
    stops with an error, stays open (pause) so the reason can be read; Ctrl+C or closing the window stops the editor. A path with
    a character cmd.exe would expand or split (% or ") starts Python directly instead (a window too, without the pause)."""
    argv = [console_python(python), os.path.join(HERE, 'wb_trackedit.py'), project]
    if config:
        argv += ['--config', config]
    line = subprocess.list2cmdline(argv)
    if '%' in line or '"' in project or (config and '"' in config):
        return argv
    comspec = os.environ.get('ComSpec') or 'cmd.exe'
    return '%s /s /c "title %s & %s || pause"' % (subprocess.list2cmdline([comspec]), EDITOR_TITLE, line)


def launch_track_editor(project, config=None, python=None):
    """starts the editor in a new console window; its working folder is the project (never the program folder, which an update
    renames)"""
    return subprocess.Popen(track_editor_command(project, config, python), cwd=project,
                            creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
LABELS = {'kit': 'Mod kit', 'cc': 'C compiler', 'cmake': 'CMake', 'ninja': 'Ninja', 'game_data': 'Game data',
          'pipeline': 'Release pipeline'}
FILE_KEYS = ('cc', 'cmake', 'ninja')


class App:
    def __init__(self, root, cfg, config_path=None):
        self.root, self.cfg = root, cfg
        self.config_path = config_path or cfg.get('_config_file') or core.CONFIG_FILE
        self.q = queue.Queue()
        self.job = None
        self.result = None
        self.lock = core.OpLock(cfg)
        self.spec_info = {}
        root.title('Burnout Mashup Workbench %s' % VERSION)
        # v0.29: sizes in 96-dpi pixels scaled to the display (DPI aware), never larger than the screen's work area
        s = max(1.0, root.winfo_fpixels('1i') / 96.0)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        mw, mh = min(int(760 * s), int(sw * 0.9)), min(int(560 * s), int(sh * 0.85))
        root.minsize(mw, mh)
        root.geometry('%dx%d' % (max(mw, min(int(1000 * s), int(sw * 0.92))), max(mh, min(int(720 * s), int(sh * 0.85)))))
        root.protocol('WM_DELETE_WINDOW', self.on_close)
        wb_theme.apply(root, compact=True)                       # v0.29 polish: the launcher's look, compact
        nb = ttk.Notebook(root)
        self.nb = nb
        nb.pack(fill='both', expand=True, pady=(2, 0))            # v0.29: grows with the window
        self.tab_set = ttk.Frame(nb, padding=8)
        nb.add(self.tab_set, text='Settings')
        self.tab_rel = ttk.Frame(nb, padding=8)
        self.tab_mod = ttk.Frame(nb, padding=8)
        nb.add(self.tab_rel, text='Release')
        nb.add(self.tab_mod, text='Mod validation')
        self.tab_new = ttk.Frame(nb, padding=8)
        nb.add(self.tab_new, text='New plugin project')
        self.tab_car = ttk.Frame(nb, padding=8)                 # v0.12
        nb.add(self.tab_car, text='New car project')
        self.tab_trk = ttk.Frame(nb, padding=8)                 # v0.13
        nb.add(self.tab_trk, text='New track project')
        self.tab_dat = ttk.Frame(nb, padding=8)                 # v0.29 (release readiness R1)
        nb.add(self.tab_dat, text='New data mod')
        self.tab_stg = ttk.Frame(nb, padding=8)
        nb.add(self.tab_stg, text='Build / stage')
        self.tab_prof = ttk.Frame(nb, padding=8)
        nb.add(self.tab_prof, text='Test profile')
        self.kit_ident = wb_kit.kit_identity(cfg.get('kit'))
        self.kit_notice, self.kit_events, self.prof_last = '', [], None
        self._build_settings(self.tab_set)
        self._build_release(self.tab_rel)
        self._build_mod(self.tab_mod)
        self._build_new(self.tab_new)
        self._build_car(self.tab_car)
        self._build_track(self.tab_trk)
        self._build_datamod(self.tab_dat)
        self._build_stage(self.tab_stg)
        self._build_profile(self.tab_prof)
        self._build_bottom(root)
        # v0.29 (kit mode): the release pipeline and the guarded test-profile runner are workspace tools; a Workbench from a
        # mod kit hides their tabs instead of showing errors (Settings still accepts a pipeline / runner path)
        if core.KIT_MODE and not cfg.get('pipeline'):
            nb.hide(self.tab_rel)
        if core.KIT_MODE and not cfg.get('runner'):
            nb.hide(self.tab_prof)
        root.bind('<Escape>', lambda e: self.do_cancel() if str(self.btn_cancel['state']) != 'disabled' else None)
        for i in range(9):
            root.bind('<Control-Key-%d>' % (i + 1), lambda e, i=i: nb.select(i) if i < len(nb.tabs()) else None)
        wb_theme.finish(root)
        self.live.configure(foreground=wb_theme.MUTED)               # the live tail stays quieter than the result
        if cfg.get('_config_error'):
            self.status['text'] = cfg['_config_error'][:160]
            messagebox.showwarning('Workbench', cfg['_config_error'])
        self.refresh_specs()
        self.do_check_settings(startup=True)
        root.after(100, self.poll)

    # ------------------------------------------------------------ settings (v0.4)
    def _build_settings(self, f):
        f.columnconfigure(1, weight=1)
        self.set_vars, self.set_cbs, self.set_status = {}, {}, {}
        for r, k in enumerate(core.CONFIG_KEYS):
            ttk.Label(f, text=LABELS[k]).grid(row=r, column=0, sticky='w')
            v = tk.StringVar(value=self.cfg.get(k) or '')
            cb = ttk.Combobox(f, textvariable=v)
            cb.grid(row=r, column=1, sticky='ew', padx=4, pady=1)
            ttk.Button(f, text='Browse...', command=lambda k=k: self.browse_setting(k)).grid(row=r, column=2)
            st = ttk.Label(f, text='', width=48, foreground='#444')
            st.grid(row=r, column=3, sticky='w', padx=4)
            self.set_vars[k], self.set_cbs[k], self.set_status[k] = v, cb, st
        n = len(core.CONFIG_KEYS)
        ttk.Label(f, text='Extra protected\nfolders (one per line)').grid(row=n, column=0, sticky='nw')
        self.prot_txt = tk.Text(f, height=3, width=60)
        self.prot_txt.grid(row=n, column=1, sticky='ew', padx=4, pady=2)
        self.prot_txt.insert('1.0', '\n'.join(self.cfg.get('protected') or []))
        b = ttk.Frame(f)
        b.grid(row=n + 1, column=0, columnspan=4, sticky='w', pady=4)
        self.btn_discover = ttk.Button(b, text='Discover', command=self.do_discover)
        self.btn_setcheck = ttk.Button(b, text='Check', command=self.do_check_settings)
        self.btn_save = ttk.Button(b, text='Save', command=self.do_save)
        for w in (self.btn_discover, self.btn_setcheck, self.btn_save):
            w.pack(side='left', padx=(0, 6))
        self.set_lbl = ttk.Label(f, text='Saved to: %s. Discover only lists candidates (pick one in a field); nothing is used '
                                 'until it is in a field, and nothing is kept until Save.' % self.config_path,
                                 foreground='#444', wraplength=900, justify='left')
        self.set_lbl.grid(row=n + 2, column=0, columnspan=4, sticky='w')
        self.kit_lbl = ttk.Label(f, text='Kit identity: ' + wb_kit.short(self.kit_ident), foreground='#264', wraplength=900,
                                 justify='left')
        self.kit_lbl.grid(row=n + 3, column=0, columnspan=4, sticky='w')

    def browse_setting(self, k):
        cur = self.set_vars[k].get()
        if k in FILE_KEYS:
            p = filedialog.askopenfilename(title=LABELS[k], initialdir=os.path.dirname(cur) if cur else None,
                                           filetypes=[('programs', '*.exe')])
        else:
            p = filedialog.askdirectory(title=LABELS[k], initialdir=cur or None)
        if p:
            self.set_vars[k].set(os.path.normpath(p))

    def apply_settings(self):
        # the Settings fields -> the running configuration (not saved)
        for k in core.CONFIG_KEYS:
            v = self.set_vars[k].get().strip()
            v = os.path.abspath(v) if v else ''
            if v != (self.cfg.get(k) or ''):
                self.cfg[k] = v
                self.cfg.setdefault('_source', {})[k] = 'Settings field' if v else 'not set'
        self.cfg['protected'] = [os.path.abspath(x.strip()) for x in self.prot_txt.get('1.0', 'end').splitlines() if x.strip()]
        self.check_kit_change()

    def check_kit_change(self):
        # v0.6: a different kit (by identity, not by path) clears every cached result of this window and says what is stale;
        # projects, staged packages and profiles keep their recorded kit (never migrated: Rebind / Preflight again)
        new = wb_kit.kit_identity(self.cfg.get('kit'))
        if wb_kit.same(new, self.kit_ident) or (new is None and self.kit_ident is None):
            return []
        lines = wb_kit.diff(self.kit_ident, new)
        self.kit_ident = new
        self.result, self.new_last, self.prof_last = None, None, None
        if hasattr(self, 'btn_new_use'):
            self.btn_new_use['state'] = 'disabled'
        for w in getattr(self, 'link_btns', {}).values():
            w['state'] = 'disabled'
        self.kit_lbl['text'] = 'Kit identity: ' + wb_kit.short(new)
        lines += ['  cleared: the last result, the last created project, the last profile check (cached in this window)',
                  '  stale until checked again: test-profile preflights made with the old kit (Preflight again); projects '
                  'bound to another kit are not built until you Rebind them (Build / stage tab); staged packages keep the '
                  'kit they were built with (shown, and allowed on a host whose services fit)',
                  '  the bmpack checker cache is keyed by the host-reader sources it compiles (a kit change selects another entry)']
        self.kit_events.append(lines)
        self.kit_notice = 'KIT CHANGED:\n' + '\n'.join(lines)
        if hasattr(self, 'status'):
            self.status['text'] = 'Kit changed to %s' % ((new or {}).get('id'))
        return lines

    def do_discover(self):
        d = core.discover()
        L = ['DISCOVER: candidates (nothing applied; pick one in the field, then Save)']
        for k in core.CONFIG_KEYS:
            self.set_cbs[k]['values'] = [p for p, _ in d.get(k, [])]
            L.append('%s:' % LABELS[k])
            L += ['  %s   [%s]' % (p, lab) for p, lab in d.get(k, [])] or ['  (none found)']
        self.show('\n'.join(L))
        return d

    def do_check_settings(self, startup=False):
        self.apply_settings()
        st = core.config_status(self.cfg)
        bad = 0
        for k, s in st.items():
            self.set_status[k]['text'] = ('OK (%s)' % s['source']) if not s['problem'] else s['problem'][:60]
            self.set_status[k]['foreground'] = wb_theme.OK if not s['problem'] else wb_theme.BAD
            bad += bool(s['problem'])
        L = ['SETTINGS: %s (%s)' % ('all set' if not bad else '%d not usable' % bad, self.config_path)]
        L += ['  %-16s %s' % (LABELS[k], ('OK  %s  [%s]' % (s['value'], s['source'])) if not s['problem'] else s['problem'])
              for k, s in st.items()]
        L.append('protected (never staged into): ' + '; '.join(p for p, _ in core.protected_roots(self.cfg))[:900])
        L.append('kit identity: ' + wb_kit.short(self.kit_ident))
        if not startup or bad:
            self.show('\n'.join(L))
        if startup and bad:
            self.status['text'] = 'Settings incomplete: %d not usable (Settings tab)' % bad
        self.refresh_specs()
        return st

    def do_save(self):
        self.apply_settings()
        path, bad = core.save_config(self.cfg, self.config_path)
        if bad:
            self.show('NOT SAVED - fix these settings first (empty fields are allowed):\n' + '\n'.join('  ' + x for x in bad))
            return False
        self.cfg['_config_file'] = path
        self.show('SAVED: %s' % path)
        self.do_check_settings(startup=True)
        return True

    # ------------------------------------------------------------ layout
    def _build_release(self, f):
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Release spec').grid(row=0, column=0, sticky='w')
        self.spec_var = tk.StringVar()
        self.spec_cb = ttk.Combobox(f, textvariable=self.spec_var)
        self.spec_cb.grid(row=0, column=1, sticky='ew', padx=4)
        self.spec_cb.bind('<<ComboboxSelected>>', lambda e: self.on_spec())
        ttk.Button(f, text='Browse...', command=self.browse_spec).grid(row=0, column=2)
        ttk.Label(f, text='Cache').grid(row=1, column=0, sticky='w')
        self.cache_var = tk.StringVar()
        self.cache_cb = ttk.Combobox(f, textvariable=self.cache_var)
        self.cache_cb.grid(row=1, column=1, sticky='ew', padx=4, pady=2)
        opts = ttk.Frame(f)
        opts.grid(row=1, column=2, sticky='w')
        ttk.Label(opts, text='jobs').pack(side='left')
        self.jobs_var = tk.IntVar(value=4)
        ttk.Spinbox(opts, from_=1, to=8, width=3, textvariable=self.jobs_var).pack(side='left')
        self.publish_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text='Publish outputs into the pipeline\'s out\\<run> folder (local only; never uploads)',
                        variable=self.publish_var).grid(row=2, column=1, sticky='w')
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_check = ttk.Button(b, text='Check spec', command=self.do_check)
        self.btn_plan = ttk.Button(b, text='Preflight', command=self.do_plan)
        self.btn_run = ttk.Button(b, text='Build release', command=self.do_run)
        self.btn_resume = ttk.Button(b, text='Resume', command=self.do_resume, state='disabled')
        for w in (self.btn_check, self.btn_plan, self.btn_run, self.btn_resume):
            w.pack(side='left', padx=(0, 6))
        self.spec_lbl = ttk.Label(f, text='', foreground='#444', wraplength=900, justify='left')
        self.spec_lbl.grid(row=4, column=0, columnspan=3, sticky='w')

    def _build_mod(self, f):
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Mod folders / mod sets\n(game load order)').grid(row=0, column=0, sticky='nw')
        self.roots = tk.Listbox(f, height=4, selectmode='browse')
        self.roots.grid(row=0, column=1, sticky='ew', padx=4)
        rb = ttk.Frame(f)
        rb.grid(row=0, column=2, sticky='n')
        ttk.Button(rb, text='Add folder...', command=self.add_root).pack(fill='x')
        ttk.Button(rb, text='Remove', command=lambda: [self.roots.delete(i) for i in self.roots.curselection()]).pack(fill='x')
        ttk.Label(f, text='Game data, C compiler and mod kit: Settings tab.', foreground='#444').grid(
            row=1, column=0, columnspan=3, sticky='w')
        b = ttk.Frame(f)
        b.grid(row=4, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_val = ttk.Button(b, text='Validate (bmpack validate)', command=self.do_validate)
        self.btn_ver = ttk.Button(b, text='Check files of selected mod (bmpack verify)', command=self.do_verify)
        self.btn_val.pack(side='left', padx=(0, 6))
        self.btn_ver.pack(side='left')

    # ------------------------------------------------------------ new plugin project (v0.5)
    def _build_new(self, f):
        f.columnconfigure(1, weight=1)
        self.new_folder = tk.StringVar()
        self.new_id = tk.StringVar()
        self.new_name = tk.StringVar()
        self.new_module = tk.StringVar()
        rows = (('Project folder (new or empty)', self.new_folder, self.browse_new_folder),
                ('Mod id (namespaced, e.g. yourname.my-plugin)', self.new_id, None),
                ('Display name', self.new_name, None),
                ('Module name (e.g. my_plugin -> my_plugin.c / .asi)', self.new_module, None))
        for r, (lab, var, cmd) in enumerate(rows):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky='w')
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky='ew', padx=4, pady=1)
            if cmd:
                ttk.Button(f, text='Browse...', command=cmd).grid(row=r, column=2)
        bf = ttk.Frame(f)
        bf.grid(row=4, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_new_check = ttk.Button(bf, text='Check', command=self.do_new_check)
        self.btn_new_check.pack(side='left', padx=(0, 6))
        self.btn_new_create = ttk.Button(bf, text='Create project', command=self.do_new_create)
        self.btn_new_create.pack(side='left', padx=(0, 6))
        self.btn_new_use = ttk.Button(bf, text='Use in Build / stage', command=self.do_new_use, state='disabled')
        self.btn_new_use.pack(side='left')
        ttk.Label(f, text='Makes a minimal native plugin from the kit\'s SDK example (h) host-info template: mod.toml, <module>.c, '
                          'workbench-project.json, README.txt - and no build script (the Workbench builds it with its own fixed '
                          'steps). Staged folder = the mod id, module = <module>.asi. An existing non-empty folder is never '
                          'written. Nothing is built, approved or installed here.',
                  foreground='#444', wraplength=900, justify='left').grid(row=5, column=0, columnspan=3, sticky='w')
        self.new_last = None

    # ------------------------------------------------------------ new data mod (v0.29)
    def _build_datamod(self, f):
        f.columnconfigure(1, weight=1)
        self.dm_folder, self.dm_id, self.dm_name = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for r, (lab, var) in enumerate((('Project folder (new or empty) *', self.dm_folder), ('Mod id (yourname.my-mod) *', self.dm_id),
                                        ('Display name *', self.dm_name))):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky='w')
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky='ew', padx=4, pady=1)
        ttk.Button(f, text='Browse...', command=lambda: self.dm_folder.set(os.path.normpath(
            filedialog.askdirectory(title='Folder for the new data mod') or self.dm_folder.get() or ''))).grid(row=0, column=2)
        ttk.Label(f, text='Value to change *').grid(row=3, column=0, sticky='w')
        self.dm_key = tk.StringVar()
        self.dm_val = tk.StringVar()
        self.dm_keys = ttk.Combobox(f, textvariable=self.dm_key)
        self.dm_keys.grid(row=3, column=1, sticky='ew', padx=4)
        self.dm_keys.bind('<<ComboboxSelected>>', lambda e: self._dm_hint())
        vf = ttk.Frame(f)
        vf.grid(row=3, column=2, sticky='w')
        ttk.Entry(vf, textvariable=self.dm_val, width=10).pack(side='left')
        ttk.Button(vf, text='Add', command=self._dm_add).pack(side='left', padx=4)
        self.dm_hint = ttk.Label(f, text='', foreground='#444')
        self.dm_hint.grid(row=4, column=1, sticky='w')
        self.dm_list = tk.Listbox(f, height=6)
        self.dm_list.grid(row=5, column=0, columnspan=3, sticky='nsew', pady=4)
        self.dm_list.bind('<Delete>', lambda e: [self.dm_list.delete(i) for i in reversed(self.dm_list.curselection())])
        bf = ttk.Frame(f)
        bf.grid(row=6, column=0, columnspan=3, sticky='w')
        ttk.Button(bf, text='Create data mod', command=self.do_dm_create).pack(side='left')
        ttk.Label(f, text='* required. A data mod changes game values with your own numbers: mod.toml [bmashup.tune], no code, '
                          'no game files. Pick a value from the list (the kit tuning catalogue: game value and limit shown), '
                          'type the new number, Add (Delete removes a row). Then Mod validation or Build / stage > Import folder '
                          'validates and stages it. An existing non-empty folder is never written.',
                  foreground='#444', wraplength=900, justify='left').grid(row=7, column=0, columnspan=3, sticky='w', pady=4)
        f.rowconfigure(5, weight=1)
        self._dm_fill()

    def _dm_fill(self):
        self.dm_cat = wb_datamod.catalogue(self.cfg)
        self.dm_keys['values'] = sorted(self.dm_cat)
        self.dm_hint['text'] = ('' if self.dm_cat else 'This kit has no tuning catalogue: type "Group | Name" exactly; '
                                'the validator checks it.')

    def _dm_hint(self):
        row = self.dm_cat.get(self.dm_key.get())
        if row:
            er = wb_datamod.editor_row(self.dm_key.get())                # v0.30: the host's own limit and default
            if er:
                self.dm_hint['text'] = '%s, default %s, allowed %g .. %g (%s)%s' % (
                    row['type'], er['default']['text'], er['limit']['lo'], er['limit']['hi'], er['limit']['rule'],
                    '; needs [bmashup.tune] version 2 (written for you)' if er['needs_version'] > 1 else '')
            else:
                self.dm_hint['text'] = '%s, game value %g, allowed 0 .. %g' % (row['type'], row['game'], 16 * max(row['game'], 1))

    def _dm_add(self):
        e = '%s = %s' % (self.dm_key.get().strip(), self.dm_val.get().strip())
        norm, bad = wb_datamod.check_entries([e], self.dm_cat)
        if bad:
            messagebox.showerror('Workbench', '\n'.join(bad))
            return
        self.dm_list.insert('end', norm[0])

    def do_dm_create(self):
        self.apply_settings()
        r = wb_datamod.create(self.cfg, self.dm_folder.get().strip(), self.dm_id.get().strip(), self.dm_name.get(),
                              list(self.dm_list.get(0, 'end')))
        self.show('NEW DATA MOD: %s %s\n%s' % (r['verdict'], r['project'], '\n'.join('  ' + x for x in r['problems'])))
        if r['ok']:
            self.status['text'] = 'Created data mod %s' % r['mod_id']

    def browse_new_folder(self):
        p = filedialog.askdirectory(title='Folder for the new project (the folder you pick, or type a new name below it)')
        if p:
            mod = self.new_module.get().strip()
            p = os.path.normpath(p)
            if os.path.isdir(p) and os.listdir(p) and mod:
                p = os.path.join(p, mod)                        # a parent was picked: the project goes into a new folder
            self.new_folder.set(p)

    def _new_values(self):
        return (self.new_folder.get().strip(), self.new_id.get().strip(), self.new_name.get(), self.new_module.get().strip())

    def do_new_check(self):
        self.apply_settings()
        folder, mid, name, mod = self._new_values()
        bad = wb_project.check_identity(mid, name, mod) + wb_project.kit_problems(self.cfg) + \
            wb_project.folder_problems(self.cfg, folder)
        warn = wb_stage.tool_prereqs(self.cfg, wb_stage.RECIPES['plugin-project'])
        self.new_last = None                                    # the values changed: "Use" waits for the next Create
        self.btn_new_use['state'] = 'disabled'
        self.show(('NEW PROJECT CHECK: OK - %s can be created' % folder if not bad else
                   'NEW PROJECT CHECK: NOT OK\n' + '\n'.join('  ' + x for x in bad)) +
                  ('\nneeded later to build (not to create):\n' + '\n'.join('  ' + x for x in warn) if warn else ''))
        return not bad

    def do_new_create(self):
        self.apply_settings()
        folder, mid, name, mod = self._new_values()
        r = wb_project.create_project(self.cfg, folder, mid, name, mod)
        self.new_last = r
        if r['ok']:
            L = ['NEW PROJECT: CREATED %s' % r['project'], '  mod id %s, name "%s", module %s.asi, source %s.c, staged folder %s'
                 % (mid, name, mod, mod, mid), '  files: ' + ', '.join(r['files']),
                 'Next: "Use in Build / stage", choose a staging folder, Build -> Validate -> Stage.']
            if r.get('warnings'):
                L += ['needed to build:'] + ['  ' + x for x in r['warnings']]
            self.btn_new_use['state'] = 'normal'
            self.status['text'] = 'Created project %s' % mid
        else:
            L = ['NEW PROJECT: NOT CREATED (nothing was written)'] + ['  ' + x for x in r['problems']]
            self.btn_new_use['state'] = 'disabled'
        self.show('\n'.join(L))
        return r

    def do_new_use(self):
        if self.new_last and self.new_last.get('ok'):
            self.proj_var.set(self.new_last['project'])
            self.mode_var.set('auto')
            self.nb.select(self.tab_stg)

    # ------------------------------------------------------------ new car project (v0.12, wb_car)
    def _build_car(self, f):
        f.columnconfigure(1, weight=1)
        self.car_vars = {k: tk.StringVar(value=v) for k, v in (('folder', ''), ('template', 'coupe'), ('mod_id', ''),
                                                                ('mod_name', ''), ('version', '1.0.0'), ('car_id', ''),
                                                                ('donor', ''), ('name', ''), ('deform', 'transfer'))}
        rows = (('Project folder (new or empty)', 'folder', 'browse'), ('Template (kit authored carimport example)', 'template',
                                                                        list(wb_car.TEMPLATES)),
                ('Mod id (namespaced, e.g. yourname.my-car)', 'mod_id', None), ('Mod display name (empty = car name)', 'mod_name', None),
                ('Mod version', 'version', None), ('Vehicle id (retail class + 1..8 A-Z 0-9, e.g. COMPMY1)', 'car_id', None),
                ('Donor (DONOR DEPENDENCY: a retail car of the same class from your game data)', 'donor', 'donors'),
                ('Car name (garage, 1..21)', 'name', None), ('Deform', 'deform', ['transfer', 'rigid']))
        for r, (lab, k, kind) in enumerate(rows):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky='w')
            if isinstance(kind, list) or kind == 'donors':
                vals = kind if isinstance(kind, list) else list(wb_car.donors(self.cfg))
                w = ttk.Combobox(f, textvariable=self.car_vars[k], values=vals, state='readonly' if isinstance(kind, list) else 'normal')
                if kind == 'donors':
                    self.car_donor_cb = w
            else:
                w = ttk.Entry(f, textvariable=self.car_vars[k])
            w.grid(row=r, column=1, sticky='ew', padx=4, pady=1)
            if kind == 'browse':
                ttk.Button(f, text='Browse...', command=self.browse_car_folder).grid(row=r, column=2)
        n = len(rows)
        ttk.Label(f, text='Paints (one per line: name #RRGGBB; empty = the template\'s six; max 8)').grid(row=n, column=0, sticky='nw')
        self.car_paints = tk.Text(f, height=4, width=40)
        self.car_paints.grid(row=n, column=1, sticky='ew', padx=4, pady=1)
        bf = ttk.Frame(f)
        bf.grid(row=n + 1, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_car_check = ttk.Button(bf, text='Check', command=self.do_car_check)
        self.btn_car_check.pack(side='left', padx=(0, 6))
        self.btn_car_create = ttk.Button(bf, text='Create car project', command=self.do_car_create)
        self.btn_car_create.pack(side='left', padx=(0, 6))
        self.btn_car_use = ttk.Button(bf, text='Use in Build / stage', command=self.do_car_use, state='disabled')
        self.btn_car_use.pack(side='left')
        ttk.Label(f, text='Makes a carimport project: car.toml (the kit tool\'s schema), the template\'s glTF + buffer + texture + '
                          'paint mask (kit files, copied), workbench-car.json, README.txt. The DONOR is a dependency, not your '
                          'content: its hull, wheels, emitters, engine audio, physics and garage photo come from YOUR game data; '
                          'a built package is LOCAL ONLY. Build: the kit\'s carimport / vehtool / bmpack with fixed arguments on a '
                          'copy of the inputs. Deferred: 3D preview, own series, registered paints, own photo.',
                  foreground='#444', wraplength=900, justify='left').grid(row=n + 2, column=0, columnspan=3, sticky='w')
        self.car_last = None

    def browse_car_folder(self):
        p = filedialog.askdirectory(title='Folder for the new car project')
        if p:
            self.car_vars['folder'].set(os.path.normpath(p))

    def _car_values(self):
        v = {k: x.get().strip() for k, x in self.car_vars.items()}
        v['name'] = self.car_vars['name'].get()
        paints = []
        for line in self.car_paints.get('1.0', 'end').splitlines():
            if line.strip():
                parts = line.split()
                paints.append((parts[0], parts[1] if len(parts) > 1 else ''))
        return v, paints

    def _car_args(self):
        v, paints = self._car_values()
        return dict(folder=v['folder'], mod_id=v['mod_id'], car_id=v['car_id'], donor=v['donor'], name=v['name'],
                    mod_name=v['mod_name'] or None, version=v['version'], template=v['template'], paints=paints or None,
                    deform=v['deform'])

    def do_car_check(self):
        self.apply_settings()
        a = self._car_args()
        paints = a['paints'] or (wb_car.template_car(self.cfg, a['template'])[1] if wb_car.template_files(self.cfg, a['template'])[0]
                                 else [])
        bad = wb_car.check_identity(self.cfg, a['mod_id'], a['car_id'], a['donor'], a['name'], a['mod_name'] or a['name'],
                                    a['version'], paints, a['deform']) + wb_car.folder_problems(self.cfg, a['folder'])
        self.car_last = None
        self.btn_car_use['state'] = 'disabled'
        self.show('NEW CAR PROJECT CHECK: OK - %s can be created' % a['folder'] if not bad else
                  'NEW CAR PROJECT CHECK: NOT OK\n' + '\n'.join('  ' + x for x in bad))
        return bad

    def do_car_create(self):
        self.apply_settings()
        r = wb_car.create_project(self.cfg, **self._car_args())
        self.car_last = r
        if r['ok']:
            c = r['car']
            L = ['NEW CAR PROJECT: CREATED %s' % r['project'],
                 '  mod %s (%s %s), car %s "%s", template %s, staged folder %s' % (c['mod_id'], c['mod_name'], c['mod_version'],
                                                                                c['id'], c['name'], self.car_vars['template'].get(),
                                                                                c['mod_id']),
                 '  paints: ' + ', '.join('%s %s' % p for p in r['paints']),
                 '  DONOR DEPENDENCY %s (not your content; from your game data; package LOCAL ONLY)' % c['donor'],
                 '  files: ' + ', '.join(r['files']),
                 'Next: "Use in Build / stage", choose a staging folder, Build -> Validate -> Stage.']
            self.btn_car_use['state'] = 'normal'
            self.status['text'] = 'Created car project %s' % c['mod_id']
        else:
            L = ['NEW CAR PROJECT: NOT CREATED (nothing was written)'] + ['  ' + x for x in r['problems']]
            self.btn_car_use['state'] = 'disabled'
        self.show('\n'.join(L))
        return r

    def do_car_use(self):
        if self.car_last and self.car_last.get('ok'):
            self.proj_var.set(self.car_last['project'])
            self.mode_var.set('auto')
            self.nb.select(self.tab_stg)

    # ------------------------------------------------------------ new track project (v0.13, wb_track)
    def _build_track(self, f):
        f.columnconfigure(1, weight=1)
        self.trk_vars = {k: tk.StringVar(value=v) for k, v in (('folder', ''), ('template', 'testloop'), ('mod_id', ''),
                                                                ('mod_name', ''), ('version', '1.0.0'), ('track_id', ''),
                                                                ('name', ''), ('location', 'MY TRACKS'), ('author', 'Workbench user'))}
        rows = (('Project folder (new or empty)', 'folder', 'browse'),
                ('Template (the kit\'s trackbuild demo: tb.py gen-testloop)', 'template', list(wb_track.TEMPLATES)),
                ('Mod id (namespaced, e.g. yourname.my-track)', 'mod_id', None), ('Mod display name (empty = track name)', 'mod_name', None),
                ('Mod version', 'version', None), ('Track id (RR_NN_VN, region EU / US / AS, not retail, e.g. EU_T7_V1)', 'track_id', None),
                ('Track name (1..27)', 'name', None), ('Track location (1..17)', 'location', None), ('Author', 'author', None))
        for r, (lab, k, kind) in enumerate(rows):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky='w')
            w = (ttk.Combobox(f, textvariable=self.trk_vars[k], values=kind, state='readonly') if isinstance(kind, list)
                 else ttk.Entry(f, textvariable=self.trk_vars[k]))
            w.grid(row=r, column=1, sticky='ew', padx=4, pady=1)
            if kind == 'browse':
                ttk.Button(f, text='Browse...', command=self.browse_trk_folder).grid(row=r, column=2)
        n = len(rows)
        bf = ttk.Frame(f)
        bf.grid(row=n, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_trk_check = ttk.Button(bf, text='Check', command=self.do_trk_check)
        self.btn_trk_check.pack(side='left', padx=(0, 6))
        self.btn_trk_create = ttk.Button(bf, text='Create track project', command=self.do_trk_create)
        self.btn_trk_create.pack(side='left', padx=(0, 6))
        self.btn_trk_use = ttk.Button(bf, text='Use in Build / stage', command=self.do_trk_use, state='disabled')
        self.btn_trk_use.pack(side='left', padx=(0, 6))
        # v0.32: the track editor opens from here (before: a command line only)
        self.btn_trk_edit = ttk.Button(bf, text='Open in track editor...', command=self.do_trk_edit)
        self.btn_trk_edit.pack(side='left', padx=(0, 6))
        self.btn_trk_guide = ttk.Button(bf, text='Track editor guide', command=self.do_trk_guide)
        self.btn_trk_guide.pack(side='left')
        ttk.Label(f, text='Makes a trackbuild project: the kit\'s demo sources (description .track.json, OBJ, PNG textures; written by '
                          'the kit\'s own generator, copied unchanged), package.toml (trackbuild\'s package keys), workbench-track.json, '
                          'README.txt. Supported: geometry / materials, collision, routes, starts, streaming units, visibility (PVS), LOD, '
                          'authored traffic. DONOR DEPENDENCY: Gamedata header / events, sky (enviro) and audio are retail EU/M1_V1 '
                          'copies from YOUR game data - a built package is LOCAL ONLY. Build: the kit\'s tb.py build / validate / '
                          'package + bmpack with fixed arguments on a copy of the inputs. Deferred: own region, point-to-point, '
                          'special materials / props, own sky / audio. Edit: "Open in track editor..." (the project just created, '
                          'else the folder above if it is a track project, else you pick one); "Track editor guide" explains it.',
                  foreground='#444', wraplength=900, justify='left').grid(row=n + 1, column=0, columnspan=3, sticky='w')
        self.trk_last = None

    def browse_trk_folder(self):
        p = filedialog.askdirectory(title='Folder for the new track project')
        if p:
            self.trk_vars['folder'].set(os.path.normpath(p))

    def _trk_args(self):
        v = {k: x.get().strip() for k, x in self.trk_vars.items()}
        v['name'] = self.trk_vars['name'].get()
        return dict(folder=v['folder'], mod_id=v['mod_id'], track_id=v['track_id'], name=v['name'], location=v['location'],
                    mod_name=v['mod_name'] or None, version=v['version'], author=v['author'], template=v['template'])

    def do_trk_check(self):
        self.apply_settings()
        a = self._trk_args()
        bad = wb_track.check_identity(self.cfg, a['mod_id'], a['track_id'], a['name'], a['location'], a['mod_name'] or a['name'],
                                      a['version'], a['author']) + wb_track.folder_problems(self.cfg, a['folder'])
        self.trk_last = None
        self.btn_trk_use['state'] = 'disabled'
        self.show('NEW TRACK PROJECT CHECK: OK - %s can be created' % a['folder'] if not bad else
                  'NEW TRACK PROJECT CHECK: NOT OK\n' + '\n'.join('  ' + x for x in bad))
        return bad

    def do_trk_create(self):
        self.apply_settings()
        r = wb_track.create_project(self.cfg, **self._trk_args())
        self.trk_last = r
        if r['ok']:
            t = r['track']
            L = ['NEW TRACK PROJECT: CREATED %s' % r['project'],
                 '  mod %s (%s %s), track %s "%s" (%s), template %s, staged folder %s' % (
                     t['mod_id'], t['mod_name'], t['version'], t['track_id'], t['track_name'], t['track_location'],
                     self.trk_vars['template'].get(), t['mod_id']),
                 '  DONOR DEPENDENCY EU/M1_V1 (Gamedata header / events, enviro, audio; from your game data; package LOCAL ONLY)',
                 '  files: ' + ', '.join(r['files']),
                 'Next: "Use in Build / stage", choose a staging folder, Build -> Validate -> Stage.']
            self.btn_trk_use['state'] = 'normal'
            self.status['text'] = 'Created track project %s' % t['mod_id']
        else:
            L = ['NEW TRACK PROJECT: NOT CREATED (nothing was written)'] + ['  ' + x for x in r['problems']]
            self.btn_trk_use['state'] = 'disabled'
        self.show('\n'.join(L))
        return r

    def do_trk_use(self):
        if self.trk_last and self.trk_last.get('ok'):
            self.proj_var.set(self.trk_last['project'])
            self.mode_var.set('auto')
            self.nb.select(self.tab_stg)

    def trk_editor_project(self, ask=True):
        """v0.32: which project the editor opens: the one just created, else the folder field if it is a track project, else a
        folder the user picks (None = cancelled)"""
        if self.trk_last and self.trk_last.get('ok'):
            return self.trk_last['project']
        f = self.trk_vars['folder'].get().strip()
        if f and wb_track.is_track_project(f):
            return os.path.normpath(f)
        if not ask:
            return None
        p = filedialog.askdirectory(title='Open a track project in the track editor')
        return os.path.normpath(p) if p else None

    def do_trk_edit(self):
        p = self.trk_editor_project()
        if not p:
            return None
        if not wb_track.is_track_project(p):
            messagebox.showwarning('Track editor', '%s is not a track project (it has no %s).\n\nCreate one on this tab first '
                                   '("Create track project"), or pick the folder of a track project.' % (p, wb_track.MARKER))
            return None
        cfgf = self.config_path if self.config_path and os.path.isfile(self.config_path) else None
        try:
            proc = launch_track_editor(p, cfgf)
        except OSError as e:
            messagebox.showerror('Track editor', 'The track editor could not be started: %s' % e)
            return None
        self.show('TRACK EDITOR: STARTED for %s\n'
                  '  It opens in your web browser in a few seconds (a page on this PC only, 127.0.0.1).\n'
                  '  A window titled "%s" keeps it running. When you are done: Save in the editor, then close that window.\n'
                  '  Unsaved edits are lost when it closes. If the browser page does not appear, the address is in that window.\n'
                  '  Help: "Track editor guide" on this tab.' % (p, EDITOR_TITLE))
        self.status['text'] = 'Track editor started for %s' % os.path.basename(p)
        return proc

    def do_trk_guide(self):
        path = os.path.join(HERE, GUIDE)
        try:
            os.startfile(path)                                    # the program Windows uses for .md files
        except OSError:
            subprocess.Popen(['notepad.exe', path])               # no program set for .md: Notepad shows it as text

    def _build_stage(self, f):
        f.columnconfigure(1, weight=1)
        self.proj_var = tk.StringVar(value=wb_stage.example_project(self.cfg) if self.cfg.get('kit') else '')
        self.dest_var = tk.StringVar()
        self.mode_var = tk.StringVar(value='auto')
        for r, (lab, var, cmd) in enumerate((('Project (kit example or New plugin project)', self.proj_var, self.browse_project),
                                             ('Staging folder', self.dest_var, self.browse_dest))):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky='w')
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky='ew', padx=4, pady=1)
            ttk.Button(f, text='Browse...', command=cmd).grid(row=r, column=2)
        bf = ttk.Frame(f)
        bf.grid(row=2, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_stage = ttk.Button(bf, text='Build -> Validate -> Stage', command=self.do_stage)
        self.btn_stage.pack(side='left', padx=(0, 6))
        self.btn_rebind = ttk.Button(bf, text='Rebind project to current kit', command=self.do_rebind)
        self.btn_rebind.pack(side='left', padx=(0, 12))
        ib = ttk.Frame(f)                                    # v0.11: import a finished mod folder (no build)
        ib.grid(row=4, column=0, columnspan=3, sticky='w', pady=(6, 0))
        self.btn_import = ttk.Button(ib, text='Import folder -> Validate -> Stage', command=self.do_import)
        self.btn_import.pack(side='left', padx=(0, 6))
        self.btn_imp_add = ttk.Button(ib, text='Add imported package to the profile draft', command=self.do_import_add,
                                      state='disabled')
        self.btn_imp_add.pack(side='left', padx=(0, 6))
        self.last_import = None
        ttk.Label(ib, text='Import = the folder in "Project" is a FINISHED mod: copied as is into a fresh attempt, validated '
                           '(manifest, host requirements, native module structure, bmpack), staged (previous package kept); '
                           'never built, no package script run, nothing installed or approved. Marked IMPORTED (not '
                           'reproducible from source).', foreground='#444', wraplength=640, justify='left').pack(side='left')
        ttk.Label(bf, text='Kit example:').pack(side='left')
        self.preset_btns = {}
        for rid in [k for k, v in wb_stage.RECIPES.items() if v.get('example')]:
            w = ttk.Button(bf, text=rid, command=lambda rid=rid: self.preset_project(rid))
            w.pack(side='left', padx=(2, 2))
            self.preset_btns[rid] = w
        ttk.Label(bf, text='  plugin mode').pack(side='left')
        self.mode_cb = ttk.Combobox(bf, textvariable=self.mode_var, values=['auto', 'reference', 'custom'], width=10,
                                    state='readonly')
        self.mode_cb.pack(side='left', padx=4)
        self.stage_lbl = ttk.Label(f, text='Recipes: ' + '; '.join('%s = %s' % (k, v['title']) for k, v in wb_stage.RECIPES.items()) +
                                   '. Paths from the Settings tab. Plugin mode: reference = the kit example, its expected bytes '
                                   'required; custom = changed sources on the same reviewed build script, other bytes allowed; '
                                   'auto = reference when the project equals the kit example (a New plugin project always '
                                   'builds in mode project). Native code is never approved.',
                                   foreground='#444', wraplength=900, justify='left')
        self.stage_lbl.grid(row=3, column=0, columnspan=3, sticky='w')

    def browse_project(self):
        p = filedialog.askdirectory(title='Example mod project', initialdir=self.proj_var.get())
        if p:
            self.proj_var.set(os.path.normpath(p))

    def browse_dest(self):
        p = filedialog.askdirectory(title='Staging folder (new or empty, or one the Workbench staged before)')
        if p:
            self.dest_var.set(os.path.normpath(p))

    def preset_project(self, rid):
        self.apply_settings()
        if not self.cfg.get('kit'):
            self.show('NOT SET - Mod kit: ' + core.check_value('kit', ''))
            return
        self.proj_var.set(wb_stage.example_project(self.cfg, rid))

    def do_stage(self):
        self.apply_settings()
        proj, dest = self.proj_var.get(), self.dest_var.get()
        rid, why = wb_stage.detect(proj)
        bad = [why] if why else wb_stage.check_destination(self.cfg, proj, dest)
        if not bad and wb_stage.RECIPES[rid].get('kind') == 'car':             # v0.12: the job's own start checks
            bad = wb_car.start_problems(self.cfg, rid, proj, dest)[0]
        elif not bad and wb_stage.RECIPES[rid].get('kind') == 'track':         # v0.13: the job's own start checks
            bad = wb_track.start_problems(self.cfg, rid, proj, dest)[0]
        elif not bad and wb_stage.RECIPES[rid].get('kind') == 'sdk-plugin':      # same checks the job makes, shown at once
            bad = wb_stage.plugin_prereqs(self.cfg, rid, proj)
            if not bad and wb_stage.RECIPES[rid].get('project'):
                bad = wb_stage.collision_problems(dest, wb_stage.recipe(rid, proj), proj)
        if bad:
            self.show('NOT STARTED:\n' + '\n'.join('  ' + x for x in bad))
            self.stage_last_refusal = bad
            return False
        self.stage_last_refusal = None
        return self.start(wb_stage.StageOp(rid, proj, dest, self.mode_var.get()))

    def do_import(self):
        """v0.11: Import folder -> Validate -> Stage (the job shows Preview when it is staged). Same checks as the CLI."""
        self.apply_settings()
        src, dest = self.proj_var.get().strip(), self.dest_var.get().strip()
        i = wb_stage.import_check(self.cfg, src, dest)
        self.import_last_check = i
        if i['problems']:
            self.show('IMPORT NOT STARTED:\n' + '\n'.join('  ' + x for x in i['problems']))
            return False
        return self.start(wb_stage.StageOp(wb_stage.IMPORT_RECIPE, src, dest))

    def do_import_add(self):
        """the last imported package -> the Test profile draft (the existing Add action)"""
        if not self.last_import:
            self.show('ADD: nothing imported in this window yet')
            return None
        return self.pf_apply('add', self.last_import)

    def do_rebind(self):
        self.apply_settings()
        proj = self.proj_var.get()
        car = wb_car.is_car_project(proj)                          # v0.12: car projects bind the same way
        trk = wb_track.is_track_project(proj)                      # v0.13: track projects too
        st = (wb_car.kit_status(self.cfg, proj) if car else wb_track.kit_status(self.cfg, proj) if trk else
              wb_project.kit_status(self.cfg, proj) if wb_project.is_project(proj) else None)
        r = (wb_car.rebind_project(self.cfg, proj) if car else wb_track.rebind_project(self.cfg, proj) if trk else
             wb_project.rebind_project(self.cfg, proj))
        if r['ok']:
            self.show('REBOUND %s\n' % proj + '\n'.join('  ' + x for x in r['diff']) +
                      '\n  only workbench-project.json changed (previous binding kept in kit_history); earlier staged outputs '
                      'are kept - the next Stage moves the old package to .wb_stage\\previous')
        else:
            self.show('NOT REBOUND:\n' + '\n'.join('  ' + x for x in r['problems']) +
                      ('\n  kit status: ' + st['text'] if st else ''))
        return r

    # ------------------------------------------------------------ test profile (v0.6; v0.7: several mods)
    def _build_profile(self, f):
        f.columnconfigure(1, weight=1)
        self.pf_pkg, self.pf_host, self.pf_appr, self.pf_dest = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.pf_pred, self.pf_reuse = tk.StringVar(), tk.BooleanVar(value=True)
        self.pf_members, self.pf_rows = [], []               # staged package folders (v0.7); empty = the single field (v0.6)
        self.pf_disabled = []                                # v0.10: members kept but switched off (draft `disabled`)
        ttk.Label(f, text='Staged package (<staging folder>\\<mod id>)').grid(row=0, column=0, sticky='w')
        ttk.Entry(f, textvariable=self.pf_pkg).grid(row=0, column=1, sticky='ew', padx=4, pady=1)
        pb = ttk.Frame(f)
        pb.grid(row=0, column=2, sticky='w')
        ttk.Button(pb, text='Browse...', command=lambda: self.browse_pf(self.pf_pkg, 'dir')).pack(side='left')
        self.btn_pf_add = ttk.Button(pb, text='Add', command=self.pf_add)
        self.btn_pf_add.pack(side='left', padx=(4, 0))
        lf = ttk.Frame(f)
        lf.grid(row=1, column=0, columnspan=3, sticky='ew', pady=2)
        lf.columnconfigure(0, weight=1)
        cols = ('on', 'mod_id', 'version', 'kind', 'sha', 'requires', 'approval')
        self.pf_tree = ttk.Treeview(lf, columns=cols, show='headings', height=5, selectmode='extended')
        for c, w, t in (('on', 36, 'On'), ('mod_id', 190, 'Mod ID'), ('version', 60, 'Version'), ('kind', 55, 'Kind'),
                        ('sha', 150, 'Hash'), ('requires', 300, 'Requirements'), ('approval', 120, 'Approval')):
            self.pf_tree.heading(c, text=t)
            self.pf_tree.column(c, width=w, stretch=c == 'requires')
        self.pf_tree.grid(row=0, column=0, sticky='ew')
        lb = ttk.Frame(lf)
        lb.grid(row=0, column=1, sticky='n', padx=(4, 0))
        self.btn_pf_preview = ttk.Button(lb, text='Preview...', command=self.pf_preview)                 # v0.10
        self.btn_pf_enable = ttk.Button(lb, text='Enable selected', command=lambda: self.pf_action('enable'))
        self.btn_pf_disable = ttk.Button(lb, text='Disable selected', command=lambda: self.pf_action('disable'))
        self.btn_pf_remove = ttk.Button(lb, text='Remove selected', command=self.pf_remove)
        self.btn_pf_load = ttk.Button(lb, text='Load draft / profile...', command=self.pf_load)
        self.btn_pf_save = ttk.Button(lb, text='Save draft...', command=self.pf_save)
        for w in (self.btn_pf_preview, self.btn_pf_enable, self.btn_pf_disable, self.btn_pf_remove, self.btn_pf_load,
                  self.btn_pf_save):
            w.pack(fill='x', pady=1)
        rows = (('Host exe (a host folder under the workspace build\\)', self.pf_host, 'exe'),
                ('Your approvals file (plugin-approvals.toml)', self.pf_appr, 'toml'),
                ('New profile folder (runtime_data\\modsets\\wbp_<name>)', self.pf_dest, 'dir'),
                ('Successor of (a prepared profile; optional)', self.pf_pred, 'dir'))
        for r, (lab, var, kind) in enumerate(rows, 2):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky='w')
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky='ew', padx=4, pady=1)
            ttk.Button(f, text='Browse...', command=lambda v=var, k=kind: self.browse_pf(v, k)).grid(row=r, column=2, sticky='w')
        ttk.Checkbutton(f, text='Successor: reuse the predecessor\'s data root while it is unused (no new 2.4 GB copy)',
                        variable=self.pf_reuse).grid(row=6, column=1, sticky='w')
        bf = ttk.Frame(f)
        bf.grid(row=7, column=0, columnspan=3, sticky='w', pady=4)
        self.btn_pf_check = ttk.Button(bf, text='Check', command=self.do_pf_check)
        self.btn_pf_prep = ttk.Button(bf, text='Prepare', command=lambda: self.do_pf('prepare'))
        self.btn_pf_pre = ttk.Button(bf, text='Preflight', command=lambda: self.do_pf('preflight'))
        self.btn_pf_dry = ttk.Button(bf, text='Dry run', command=lambda: self.do_pf('dryrun'))
        self.btn_pf_stat = ttk.Button(bf, text='Profile status', command=self.do_pf_status)
        self.btn_pf_launch = ttk.Button(bf, text='Launch...', command=self.do_pf_launch)              # v0.8
        self.btn_pf_stop = ttk.Button(bf, text='Stop', command=self.do_pf_stop, state='disabled')
        self.btn_pf_res = ttk.Button(bf, text='Results', command=self.do_pf_results)
        self.btn_pf_cap = ttk.Button(bf, text='Capture now', command=self.do_pf_capture, state='disabled')     # v0.9
        self.btn_pf_succ = ttk.Button(bf, text='Successor (new root)...', command=self.do_pf_successor)
        for w in (self.btn_pf_check, self.btn_pf_prep, self.btn_pf_pre, self.btn_pf_dry, self.btn_pf_stat, self.btn_pf_launch,
                  self.btn_pf_stop, self.btn_pf_cap, self.btn_pf_res, self.btn_pf_succ):
            w.pack(side='left', padx=(0, 6))
        lp = ttk.Frame(f)                                       # v0.9 launch preset
        lp.grid(row=9, column=0, columnspan=3, sticky='w', pady=(4, 0))
        self.pf_preset = tk.StringVar(value='boot')
        self.pf_secs, self.pf_dumps, self.pf_capev = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(lp, text='Launch preset').pack(side='left')
        cb = ttk.Combobox(lp, textvariable=self.pf_preset, values=sorted(wb_profile.PRESETS), width=8, state='readonly')
        cb.pack(side='left', padx=4)
        cb.bind('<<ComboboxSelected>>', lambda e: self.pf_preset_defaults())
        for lab, var, w in (('duration s', self.pf_secs, 6), ('frame dumps at flips', self.pf_dumps, 16),
                            ('window capture every s', self.pf_capev, 5)):
            ttk.Label(lp, text=lab).pack(side='left', padx=(8, 2))
            ttk.Entry(lp, textvariable=var, width=w).pack(side='left')
        self.pf_preset_lbl = ttk.Label(lp, text='', foreground='#444')
        self.pf_preset_lbl.pack(side='left', padx=8)
        self.pf_preset_defaults()
        ttk.Label(f, text='Check = every mod\'s identity, hashes, requirements and approval, the host\'s services and the host\'s '
                          'own admission of the whole combination (the kit\'s bmpack validate: order, dependencies, conflicts, '
                          'duplicate ids, capacity). Prepare = the runner\'s disposable data root (g_run.py make-root) + the '
                          'profile folder. Preflight = the prelaunch checks. Dry run = g_run.py run td_run --dry-run (the game is '
                          'NOT executed). A prepared profile never changes: another combination is a new (successor) profile. '
                          'The Workbench never approves code. Launch... = ONE real 20 s boot of the profile in the folder field '
                          '(owner present): the exact plan is shown first, then you confirm its token; everything is rechecked '
                          'just before the start. Stop ends only the processes this launch owns. Results = the launch records. '
                          'Preview... = a read-only look at a mod folder against this draft (DECLARED mod.toml / record vs '
                          'VERIFIED bytes vs the host readers; not a code-safety assessment). Enable / Disable selected = the '
                          'host\'s own switch (Prepare writes mod-list.toml disabled = [...]); nothing is deleted or approved.',
                  foreground='#444', wraplength=900, justify='left').grid(row=8, column=0, columnspan=3, sticky='w')

    def browse_pf(self, var, kind):
        if kind == 'dir':
            p = filedialog.askdirectory(title='Folder')
        else:
            p = filedialog.askopenfilename(title='File', filetypes=[('programs', '*.exe')] if kind == 'exe' else [('TOML', '*.toml')])
        if p:
            var.set(os.path.normpath(p))

    def pf_packages(self):
        """the profile's members: the list (v0.7) or, while it is empty, the single package field (v0.6)"""
        if self.pf_members:
            return list(self.pf_members)
        p = self.pf_pkg.get().strip()
        return [p] if p else []

    def pf_refresh(self):
        self.pf_tree.delete(*self.pf_tree.get_children())
        self.pf_rows = wb_profile.member_rows(self.cfg, self.pf_members, self.pf_appr.get().strip(), self.pf_disabled)
        for i, r in enumerate(self.pf_rows):
            self.pf_tree.insert('', 'end', iid=str(i), values=(r['on'], r['mod_id'], r['version'], r['kind'], r['sha'], r['requires'],
                                                              r['approval'] if not r['problems'] else 'PROBLEM: ' + r['problems'][0]))
        return self.pf_rows

    def _pf_rows_text(self, head):
        rows = self.pf_rows
        return '\n'.join([head] + ['  %-3s %-6s %s %s  %s  %s  %s%s' % (r['on'], r['kind'], r['mod_id'], r['version'], r['sha'],
                                                                      r['requires'], r['approval'],
                                                                      ('  PROBLEM: ' + '; '.join(r['problems'])) if r['problems'] else '')
                                  for r in rows])

    def pf_apply(self, action, target, confirm=None):
        """v0.10: ONE draft action through wb_profile.draft_apply (the CLI's code). The window's draft changes only when it
        succeeds; a mod that enabled members require is disabled / removed only after an explicit Yes (confirm(report) -> bool
        replaces the dialog in scripted tests). -> report"""
        d = self._pf_list_draft()
        nd, rep = wb_profile.draft_apply(d, action, target)
        if nd is None and rep.get('dependents'):
            text = ('%s %s: these enabled mods declare they need it and are left exactly as they are:\n%s\n\n%s anyway? (Check '
                    'will refuse them until their requirement is met)' % (action.upper(), target, '\n'.join(
                        '  %s (needs %s)' % (x['mod_id'], x['requires']) for x in rep['dependents']), action.capitalize()))
            ok = confirm(rep) if confirm else messagebox.askyesno('Workbench - %s' % action, text)
            if ok:
                nd, rep = wb_profile.draft_apply(d, action, target, even_if_required=True)
            else:
                rep = dict(rep, refused=rep['refused'] + ['not confirmed: nothing changed'])
        if nd is None:
            self.show('NOT CHANGED (%s %s): %s' % (action, target, '; '.join(rep['refused'])))
            return rep
        self.pf_members, self.pf_disabled = list(nd['packages']), list(nd['disabled'])
        if action == 'add':
            self.pf_pkg.set('')
        self.pf_refresh()
        self.show(self._pf_rows_text('PROFILE MEMBERS (%d): %s' % (len(self.pf_rows), '; '.join(rep['notes'] + rep['needs']))))
        return rep

    def _pf_selected(self, mod_id_or_index=None):
        if mod_id_or_index is None:
            sel = [int(x) for x in self.pf_tree.selection()]
        elif isinstance(mod_id_or_index, int):
            sel = [mod_id_or_index]
        else:
            return [mod_id_or_index]
        return [self.pf_members[i] for i in sel if 0 <= i < len(self.pf_members)]

    def pf_action(self, action, mod_id_or_index=None, confirm=None):
        """Enable / Disable / Remove selected (or the given mod id / row): one draft_apply per package -> reports"""
        targets = self._pf_selected(mod_id_or_index)
        if not targets:
            self.show('%s: select a row first' % action.upper())
            return []
        return [self.pf_apply(action, t, confirm) for t in targets]

    def pf_preview(self, path=None):
        """v0.10: read-only preview of a mod folder (the package field, else the selected row) against this window's draft"""
        self.apply_settings()
        p = (path or self.pf_pkg.get().strip() or (self._pf_selected() or [''])[0]).strip()
        if not p:
            self.show('PREVIEW: choose a mod folder (package field) or select a row first')
            return None
        P = wb_profile.preview(self.cfg, p, self._pf_list_draft())
        self.prof_preview = P
        self.show(wb_profile.preview_text(P))
        return P

    def pf_add(self, path=None):
        p = (path or self.pf_pkg.get()).strip()
        if not p:
            self.show('ADD: choose a staged package folder first')
            return False
        rep = self.pf_apply('add', p)
        if not rep['ok'] and any('already in the list' in x for x in rep['refused']):
            self.show(self._pf_rows_text('PROFILE MEMBERS (%d): already in the list: %s (nothing changed)' % (len(self.pf_rows), p)))
        return rep['ok'] or any('already in the list' in x for x in rep['refused'])

    def pf_remove(self, mod_id_or_index=None, confirm=None):
        targets = self._pf_selected(mod_id_or_index)
        before = list(self.pf_members)
        if not targets:
            self.show('PROFILE MEMBERS (%d): removed nothing (select a row)' % len(self.pf_members))
            return []
        for t in targets:
            self.pf_apply('remove', t, confirm)
        return [p for p in before if p not in self.pf_members]

    def _pf_draft(self):
        d = wb_profile.new_draft()
        d.update(packages=self.pf_packages(), host=self.pf_host.get().strip(), approvals=self.pf_appr.get().strip(),
                 dest=self.pf_dest.get().strip(), predecessor=self.pf_pred.get().strip(), reuse_root=bool(self.pf_reuse.get()),
                 disabled=[p for p in self.pf_disabled if p in self.pf_members])
        return d

    def _pf_list_draft(self):
        """the draft of the member LIST only (v0.10 actions / preview; not the v0.6 single-field fallback)"""
        return dict(self._pf_draft(), packages=list(self.pf_members))

    def pf_save(self, path=None):
        path = path or filedialog.asksaveasfilename(title='Save profile draft', defaultextension='.json',
                                                    filetypes=[('profile draft', '*.json')])
        if not path:
            return None
        d = wb_profile.save_draft(path, self._pf_draft())
        self.show('DRAFT SAVED %s (%d packages)' % (path, len(d['packages'])))
        return path

    def pf_load(self, path=None):
        """a saved draft, or a prepared profile folder (-> the draft of a successor of it: same members, no destination)"""
        path = path or filedialog.askopenfilename(title='Load profile draft or PROFILE.json', filetypes=[('JSON', '*.json')])
        if not path:
            return None
        d, bad = wb_profile.load_draft(path)
        if bad:
            self.show('NOT LOADED: ' + '; '.join(bad))
            return None
        self.pf_members = list(d['packages'])
        self.pf_disabled = list(d.get('disabled') or [])
        self.pf_pkg.set('')
        for var, k in ((self.pf_host, 'host'), (self.pf_appr, 'approvals'), (self.pf_dest, 'dest'), (self.pf_pred, 'predecessor')):
            var.set(d.get(k) or '')
        self.pf_reuse.set(bool(d.get('reuse_root', True)))
        rows = self.pf_refresh()
        self.show('LOADED %s: %d packages%s\n%s' % (path, len(rows), ('; successor of %s (choose a new profile folder)' % d['predecessor'])
                                                    if d.get('predecessor') else '',
                                                    '\n'.join('  %-6s %s %s  %s' % (r['kind'], r['mod_id'], r['version'], r['sha'])
                                                              for r in rows)))
        return d

    def _pf_args(self):
        d = self._pf_draft()
        return d['packages'], d['host'], d['dest'], d['approvals'], d['predecessor'] or None, d['reuse_root']

    def do_pf_check(self):
        self.apply_settings()
        pk, host, dest, appr, pred, reuse = self._pf_args()
        i = wb_profile.inspect(self.cfg, pk, host, dest, appr, pred, reuse, self._pf_draft()['disabled'])
        self.prof_last = i
        if self.pf_members:
            self.pf_refresh()
        self.show(wb_profile.check_text(i))
        return i

    def do_pf(self, action):
        self.apply_settings()
        pk, host, dest, appr, pred, reuse = self._pf_args()
        off = self._pf_draft()['disabled']
        if action == 'prepare':
            i = wb_profile.inspect(self.cfg, pk, host, dest, appr, pred, reuse, off)
            self.prof_last = i
            if i['problems']:
                self.show('NOT STARTED\n' + wb_profile.check_text(i))
                return False
        elif action == 'dryrun':
            st = wb_profile.profile_status(self.cfg, dest)
            if not st.get('ok') or st['preflight'] != 'valid':
                self.show('NOT STARTED: ' + '; '.join(st.get('problems') or ['preflight %s: %s' % (st['preflight'],
                                                                                                    '; '.join(st['preflight_why']))]))
                return False
        return self.start(wb_profile.ProfileOp(action, dest, pk, host, appr, pred, reuse, disabled=off))

    def do_pf_status(self):
        self.apply_settings()
        st = wb_profile.profile_status(self.cfg, self.pf_dest.get().strip())
        self.show(wb_profile.status_text(st, self.kit_ident))
        return st

    # v0.8: Launch -> Stop -> Results
    def pf_preset_defaults(self):
        p = wb_profile.PRESETS[self.pf_preset.get()]
        self.pf_secs.set(str(p['secs']))
        self.pf_dumps.set(p['dump_flips'])
        self.pf_capev.set(str(p['capture_every']) if p['capture_every'] else '')
        self.pf_preset_lbl['text'] = '%s%s' % (p['label'], ' (game window shown; you can play; Stop any time)' if p['window'] else '')

    def pf_launch_opts(self):
        return {'preset': self.pf_preset.get(), 'boot_secs': self.pf_secs.get().strip() or None,
                'dump_flips': self.pf_dumps.get().strip(), 'capture_every': self.pf_capev.get().strip() or 0}

    def do_pf_capture(self):
        j = self.job
        if j and j.op.kind == 'profile' and j.op.action == 'launch' and (j.op.preset or 'boot') == 'visible':
            j.capture_now()
            self.status['text'] = 'Window capture requested'
            return True
        self.show('CAPTURE: no visible launch is running in this window')
        return False

    def do_pf_successor(self, name=None, confirm=None):
        """explicit successor of the profile in the folder field with a NEW data root (g_run make-root); Check shown first"""
        self.apply_settings()
        if self.busy():
            self.show('NOT STARTED - an operation is already running')
            return False
        pred = os.path.abspath(self.pf_dest.get().strip()) if self.pf_dest.get().strip() else ''
        if not os.path.isfile(os.path.join(pred, 'PROFILE.json')):
            self.show('SUCCESSOR: put a prepared profile folder in "New profile folder" first')
            return False
        if name is None:
            from tkinter import simpledialog
            name = simpledialog.askstring('Workbench - successor', 'New profile name (wbp_...); it gets a NEW data root:',
                                          initialvalue=os.path.basename(pred) + '_s2')
        if not name:
            return False
        dest = name if os.path.isabs(name) else os.path.join(os.path.dirname(pred), name)
        d, bad = wb_profile.successor_draft(pred, dest)
        if bad:
            self.show('SUCCESSOR NOT POSSIBLE: ' + '; '.join(bad))
            return False
        i = wb_profile.inspect(self.cfg, d['packages'], d['host'], d['dest'], d['approvals'], d['predecessor'], False, d['disabled'])
        text = wb_profile.check_text(i)
        self.show(text)
        if i['problems']:
            return False
        ok = confirm(i) if confirm else messagebox.askyesno(
            'Workbench - successor', 'Prepare %s as a successor of %s with a NEW data root (g_run make-root, about 2.4 GB)?\n'
            'The predecessor and its history stay unchanged.' % (os.path.basename(dest), os.path.basename(pred)))
        if not ok:
            self.show(text + '\nNOT PREPARED (not confirmed)')
            return False
        self.pf_members = list(d['packages'])
        self.pf_disabled = list(d['disabled'])
        self.pf_host.set(d['host'])
        self.pf_appr.set(d['approvals'])
        self.pf_pred.set(pred)
        self.pf_reuse.set(False)
        self.pf_dest.set(d['dest'])
        self.pf_refresh()
        return self.start(wb_profile.ProfileOp('prepare', d['dest'], d['packages'], d['host'], d['approvals'], pred, False,
                                               disabled=d['disabled']))

    def do_pf_launch(self, confirm=None, **opts):
        """show the exact launch plan, then ask; confirm(plan) -> bool replaces the dialog (scripted tests). Options default to
        the preset fields; keyword options (preset, boot_secs, max_wall, dump_flips, capture_every, ...) override them."""
        self.apply_settings()
        if self.busy():
            self.show('NOT STARTED - an operation is already running')
            return False
        dest = os.path.abspath(self.pf_dest.get().strip()) if self.pf_dest.get().strip() else ''
        opts = dict(self.pf_launch_opts(), **opts)
        plan = wb_profile.launch_plan(self.cfg, dest, **{k: v for k, v in opts.items()
                                                         if k in ('boot_secs', 'max_wall', 'preset', 'dump_flips', 'capture_every')})
        self.pf_plan = plan
        text = wb_profile.launch_plan_text(plan)
        self.show(text)
        if plan['problems']:
            self.status['text'] = 'Launch refused: %s' % plan['problems'][0][:120]
            return False
        pc = plan['preset']
        ask = ('REAL LAUNCH of %s (owner present): %s\n\nhost %s\nsha256 %s\nmods: %s\n\n%s for %s s (--saves empty), then the '
               'runner ends it; wall limit %.0f s.\nEvidence: %s\nStop: ends only this launch\'s game, any time.\nToken: %s\n'
               'Plan: %s\n\nLaunch now?' % (
                   plan['name'], pc['label'], plan['host']['path'], plan['host']['sha256'],
                   ', '.join('%s %s' % (m['mod_id'], m['version']) for m in plan['members']),
                   'The game WINDOW is shown' if pc['window'] else 'The game boots headless', plan['boot_secs'],
                   plan['max_wall'], '; '.join(x.split(' (')[0] for x in pc['evidence']), plan['token'], plan['plan_id']))
        ok = confirm(plan) if confirm else messagebox.askyesno('Workbench - REAL launch', ask)
        if not ok:
            self.show(text + '\nNOT LAUNCHED (not confirmed)')
            return False
        return self.start(wb_profile.ProfileOp('launch', dest, authorize=plan['token'], plan_id=plan['plan_id'], **opts))

    def do_pf_stop(self, by=None):
        j = self.job
        if not (j and j.op.kind == 'profile' and j.op.action == 'launch'):
            self.show('STOP: no launch is running in this window')
            return False
        j.cancel(by=by or 'operator %s (Workbench Stop button, window pid %d)' % (getpass.getuser(), os.getpid()))
        self.status['text'] = 'Stopping the launch (only the processes it owns)...'
        return True

    def do_pf_results(self):
        self.apply_settings()
        dest = self.pf_dest.get().strip()
        self.show(wb_profile.results_text(os.path.abspath(dest)) if dest else 'RESULTS: choose a profile folder')

    def _build_bottom(self, root):
        bar = ttk.Frame(root, padding=(8, 4))
        bar.pack(fill='x')
        self.status = ttk.Label(bar, text='Ready.')
        self.status.pack(side='left')
        self.btn_cancel = ttk.Button(bar, text='Cancel', command=self.do_cancel, state='disabled')
        self.btn_cancel.pack(side='right')
        self.btn_devflow = ttk.Button(bar, text='Developer workflow', command=self.open_devflow)     # v0.30
        self.btn_devflow.pack(side='right', padx=(0, 6))
        self.prog = ttk.Progressbar(bar, length=220, mode='determinate')
        self.prog.pack(side='right', padx=6)
        links = ttk.Frame(root, padding=(8, 0))
        links.pack(fill='x')
        self.link_btns = {}
        for key, text in (('log', 'Full log'), ('run_dir', 'Run folder'), ('summary', 'summary.json'), ('out_dir', 'Output folder'),
                          ('release_manifest', 'RELEASE_MANIFEST'), ('publish_plan', 'PUBLISH_PLAN'),
                          ('staged', 'Staged package'), ('manifest', 'STAGE.json'), ('work', 'Attempt folder'),
                          ('game_log', 'log.txt'), ('result_json', 'result.json'), ('guard_events', 'Guard events'),
                          ('session', 'Session folder'), ('captures', 'Captures')):
            w = ttk.Button(links, text=text, state='disabled', command=lambda k=key: self.open_link(k))
            w.pack(side='left', padx=(0, 4))
            self.link_btns[key] = w
        pw = ttk.PanedWindow(root, orient='vertical')
        pw.pack(fill='both', expand=True, padx=8, pady=8)
        self.out = tk.Text(pw, height=12, wrap='none', font=('Consolas', 9), padx=8, pady=6)
        self.live = tk.Text(pw, height=8, wrap='none', font=('Consolas', 8), foreground='#555', padx=8, pady=6)
        pw.add(self.out, weight=3)
        pw.add(self.live, weight=2)

    # ------------------------------------------------------------ spec / cache
    def refresh_specs(self):
        specs = core.list_specs(self.cfg)
        self.spec_cb['values'] = specs
        self.cache_cb['values'] = core.list_caches(self.cfg)
        if specs and not self.spec_var.get():
            pref = [s for s in specs if os.path.basename(s) == 'release_spec.json']
            self.spec_var.set(pref[0] if pref else specs[0])
            self.on_spec()

    def browse_spec(self):
        p = filedialog.askopenfilename(title='Release spec', initialdir=self.cfg['pipeline'], filetypes=[('JSON', '*.json')])
        if p:
            self.spec_var.set(os.path.normpath(p))
            self.on_spec()

    def on_spec(self):
        spec = self.spec_var.get()
        self.cache_var.set(core.default_cache(self.cfg, spec))
        r = core.check_spec(spec)
        self.spec_info = r['info']
        i = r['info']
        if r['ok']:
            self.spec_lbl['text'] = 'release %s (%s) - %d nodes, deliverables %s, %d checks (%d gate); versions %s' % (
                i['release'], i['status'], len(i['nodes']), ', '.join(i['deliverables']), i['checks'], i['gate_checks'],
                ', '.join('%s %s' % kv for kv in list(i['versions'].items())[:6]))
        else:
            self.spec_lbl['text'] = 'SPEC PROBLEM: ' + '; '.join(r['issues'])
        if r['ok']:
            blk = core.build_blockers(self.cfg, spec)
            if blk:
                self.spec_lbl['text'] += '\nBUILD NOT POSSIBLE HERE: ' + blk[0]
        return r

    # ------------------------------------------------------------ actions
    def busy(self):
        return self.job is not None

    def do_check(self):
        r = self.on_spec()
        self.show(('CHECK SPEC: %s\n' % ('OK' if r['ok'] else 'PROBLEMS')) + '\n'.join('  ' + x for x in r['issues']) +
                  ('\n(structure only; "Preflight" runs the pipeline\'s own preflight)' if r['ok'] else ''))

    def _release_op(self, make, build=False):
        spec, cache = self.spec_var.get(), self.cache_var.get()
        r = core.check_spec(spec)
        if not r['ok']:
            self.show('NOT STARTED - spec problems:\n' + '\n'.join('  ' + x for x in r['issues']))
            return
        miss = core.release_prereqs(self.cfg, spec, cache) + (core.build_blockers(self.cfg, spec) if build else [])
        if miss:
            self.show('NOT STARTED - missing prerequisites:\n' + '\n'.join('  ' + x for x in miss))
            return
        self.spec_info = r['info']
        self.start(make(spec, cache))

    def do_plan(self):
        self._release_op(lambda s, c: core.op_plan(self.cfg, s, c))

    def do_run(self):
        self._release_op(lambda s, c: core.op_run(self.cfg, s, c, self.jobs_var.get(), self.publish_var.get()), build=True)

    def do_resume(self):
        rid = (self.result or {}).get('run_id')
        if rid:
            self._release_op(lambda s, c: core.op_run(self.cfg, s, c, self.jobs_var.get(), self.publish_var.get(), resume=rid),
                             build=True)

    def add_root(self):
        p = filedialog.askdirectory(title='Mod folder or mod set folder')
        if p:
            self.roots.insert('end', os.path.normpath(p))

    def _mod_cfg(self):
        self.apply_settings()

    def do_validate(self):
        self._mod_cfg()
        roots = list(self.roots.get(0, 'end'))
        if not roots:
            self.show('NOT STARTED - add at least one mod folder or mod set folder')
            return
        miss = core.bmpack_prereqs(self.cfg) + ['folder not found: %s' % r for r in roots if not os.path.isdir(r)]
        if miss:
            self.show('NOT STARTED - missing prerequisites:\n' + '\n'.join('  ' + x for x in miss))
            return
        self.start(core.op_validate(self.cfg, roots))

    def do_verify(self):
        self._mod_cfg()
        sel = self.roots.curselection()
        if not sel:
            self.show('NOT STARTED - select one mod folder in the list')
            return
        mod = self.roots.get(sel[0])
        miss = core.bmpack_prereqs(self.cfg, need_game=False) + ([] if os.path.isdir(mod) else ['folder not found: %s' % mod])
        if miss:
            self.show('NOT STARTED - missing prerequisites:\n' + '\n'.join('  ' + x for x in miss))
            return
        self.start(core.op_verify(self.cfg, mod))

    def start(self, op):
        if self.busy():
            self.show('NOT STARTED - an operation is already running')
            return False
        why = self.lock.acquire(op.title)
        if why:
            self.show('NOT STARTED - ' + why)
            return False
        self.result = None
        self.live.delete('1.0', 'end')
        self.out.delete('1.0', 'end')
        self.out.insert('end', 'Running %s ...\n' % op.title)
        for w in self.link_btns.values():
            w['state'] = 'disabled'
        cls = wb_stage.StageJob if op.kind == 'stage' else wb_profile.ProfileJob if op.kind == 'profile' else core.Job
        self.job = cls(self.cfg, op, on_line=self.q.put).start()
        self.link_btns['log']['state'] = 'normal'
        self.set_running(True)
        self.status['text'] = 'Running %s' % op.title
        return True

    def do_cancel(self):
        if self.job:
            self.status['text'] = 'Cancelling (stopping the process tree)...'
            self.job.cancel()

    def set_running(self, on):
        st = 'disabled' if on else 'normal'
        for w in (self.btn_check, self.btn_plan, self.btn_run, self.btn_val, self.btn_ver, self.btn_stage, self.btn_save,
                  self.btn_new_create, self.btn_rebind, self.btn_pf_prep, self.btn_pf_pre, self.btn_pf_dry,
                  self.btn_pf_add, self.btn_pf_remove, self.btn_pf_load, self.btn_pf_launch, self.btn_pf_enable,
                  self.btn_pf_disable, self.btn_pf_preview, self.btn_import):
            w['state'] = st
        self.btn_cancel['state'] = 'normal' if on else 'disabled'
        j = self.job
        la = on and j and j.op.kind == 'profile' and j.op.action == 'launch'
        self.btn_pf_stop['state'] = 'normal' if la else 'disabled'
        self.btn_pf_cap['state'] = 'normal' if la and (j.op.preset or 'boot') == 'visible' else 'disabled'
        self.btn_pf_succ['state'] = 'disabled' if on else 'normal'
        if on:
            self.btn_resume['state'] = 'disabled'
            self.prog.configure(mode='indeterminate')
            self.prog.start(15)
        else:
            self.prog.stop()
            self.prog.configure(mode='determinate', value=0)

    # ------------------------------------------------------------ polling (UI thread)
    def poll(self):
        n = 0
        while n < 500:
            try:
                line = self.q.get_nowait()
            except queue.Empty:
                break
            self.live.insert('end', line + '\n')
            n += 1
        if n:
            if int(self.live.index('end-1c').split('.')[0]) > 2000:
                self.live.delete('1.0', '500.0')
            self.live.see('end')
        j = self.job
        if j and j.op.kind == 'run' and not j.done.is_set():
            p = core.run_progress(self.cfg, j.op, self.spec_info)
            if p and p[1]:
                if str(self.prog['mode']) != 'determinate':
                    self.prog.stop()
                    self.prog.configure(mode='determinate', maximum=p[1])
                self.prog['value'] = p[0]
                self.status['text'] = 'Building: %d / %d nodes done' % p
        if j and j.done.is_set():
            self.finish()
        self.root.after(150, self.poll)

    def finish(self):
        j, self.job = self.job, None
        self.lock.release()
        self.set_running(False)
        try:
            res = core.parse(self.cfg, j)
        except Exception as e:
            res = {'kind': j.op.kind, 'rc': j.rc, 'ok': False, 'verdict': 'RESULT UNREADABLE (%s)' % e, 'log': j.log_path,
                   'excerpt': j.tail[-12:], 'cancelled': j.cancelled}
        self.result = res
        text = core.summarize(res)
        if res.get('kind') == 'stage' and res.get('ok') and (res.get('recipe') == wb_stage.IMPORT_RECIPE or
                                                              (wb_stage.RECIPES.get(res.get('recipe')) or {}).get('kind') in ('car', 'track')):
            # v0.11 import / v0.12 car: -> Preview + "Add ... to the profile draft" (the existing Add action)
            self.last_import = res['staged']
            self.btn_imp_add['state'] = 'normal'
            text += '\n\n' + wb_profile.preview_text(wb_profile.preview(self.cfg, res['staged'], self._pf_list_draft()))
        self.show(text)
        self.status['text'] = '%s: %s' % (j.op.title, res['verdict'])
        for k, w in self.link_btns.items():
            w['state'] = 'normal' if res.get(k) else 'disabled'
        if res.get('kind') == 'run' and res.get('resumable'):
            self.btn_resume['state'] = 'normal'

    def show(self, text):
        if self.kit_notice:                                   # v0.6: a kit change is reported once, above the next result
            text, self.kit_notice = self.kit_notice + '\n\n' + text, ''
        self.out.delete('1.0', 'end')
        self.out.insert('end', text + '\n')

    def open_link(self, key):
        p = (self.result or {}).get(key) or (self.job.log_path if key == 'log' and self.job else None)
        if p and os.path.exists(p):
            os.startfile(p)
        else:
            messagebox.showinfo('Workbench', 'Not available: %s' % (p or key))

    def open_devflow(self, popen=None):
        """v0.30: the developer workflow window (wbn_gui.py: template -> tune -> test plan) as its own process, with this
        window's kit when one is set. Returns the argv it started."""
        argv = [self.cfg.get('python') or sys.executable, '-B', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wbn_gui.py')]
        if self.cfg.get('kit'):
            argv += ['--kit', self.cfg['kit']]
        (popen or subprocess.Popen)(argv, cwd=os.path.dirname(os.path.abspath(__file__)))
        self.status['text'] = 'Developer workflow window started'
        return argv

    def on_close(self):
        if self.job and not messagebox.askyesno('Workbench', 'An operation is running. Cancel it and close?'):
            return
        if self.job:
            launch = self.job.op.kind == 'profile' and self.job.op.action == 'launch'
            if launch:
                self.job.cancel(by='operator %s (Workbench window closed, pid %d)' % (getpass.getuser(), os.getpid()))
            else:
                self.job.cancel()
            self.job.wait(self.job.op.stop_grace + 60 if launch else 30)
            self.lock.release()
        self.root.destroy()


def main(argv=None):
    ap = argparse.ArgumentParser(description='Burnout Mashup Workbench %s' % VERSION)
    ap.add_argument('--pipeline')
    ap.add_argument('--kit')
    ap.add_argument('--game-data')
    ap.add_argument('--cc')
    ap.add_argument('--cmake')
    ap.add_argument('--ninja')
    ap.add_argument('--config')
    ap.add_argument('dropped', nargs='*', help='v0.30: paths dropped onto Burnout Mashup Workbench.exe (named in the status line; '
                    'nothing is opened or changed automatically)')
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config, pipeline=a.pipeline, kit=a.kit, game_data=a.game_data, cc=a.cc, cmake=a.cmake, ninja=a.ninja)
    if os.name == 'nt':                                                  # v0.29: sharp text at 125-200 % scaling
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    app = App(root, cfg, cfg['_config_file'])
    if a.dropped:
        app.status['text'] = 'Dropped onto the Workbench: %s (choose what to do with it in a tab)' % '; '.join(a.dropped)[:200]
    root.mainloop()


if __name__ == '__main__':
    main()
