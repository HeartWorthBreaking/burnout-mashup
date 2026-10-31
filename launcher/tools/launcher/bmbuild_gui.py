"""bmbuild_gui.py - the launcher's "Build Mashup" window (tkinter). Everything it does runs through bmbuild.py (the same CLI as
build-mashup.cmd) as a child process: progress per step, a live log, Cancel (the build stops its own child processes; if it does not
answer within 20 s the whole process tree is ended), and nothing is downloaded without a confirmation per tool that shows the licence
notice, URL, size and sha256 first. Play (in the main window) is enabled only after a verified build is installed. Original code (MIT)."""
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmbuild  # noqa: E402
import bmhost  # noqa: E402
import bmimage  # noqa: E402
import bmops  # noqa: E402
import bmtools  # noqa: E402

bmops.STEPS.setdefault("build_mashup", (os.path.join("launcher", "bmbuild.py"), []))
TITLE = "Build Mashup"
STEP_TEXT = {"fetch": "1 Get the pinned upstream sources", "layers": "2 Apply the Mashup host layers", "regen": "3 Recompile YOUR game (upstream recompiler)",
             "marks": "4 Apply the hook marks", "build": "5 Compile the host program", "verify": "6 Verify: identical to the reference",
             "host_info": "7 Write HOST_INFO.json", "install": "8 Install into host-local (previous kept)"}
SOURCES = (("github", "GitHub (network): the pinned upstream repositories"), ("local", "Local clones (folders, read only)"),
           ("remote", "Git remote URL (also file:///... of a local repository)"))


def _try(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001  (a window must not die on a probe)
        return default


class BuildWindow(tk.Toplevel):
    def __init__(self, master, launcher=None, on_change=None, step_factory=None, ask=None):
        super().__init__(master)
        self.title(TITLE)
        self.launcher = launcher or bmhost.LAUNCHER
        self.on_change = on_change or (lambda: None)
        self.Step = step_factory or bmops.Step
        self.ask = ask or messagebox.askyesno
        self.job = None
        self.job_kind = None
        self.cancel_at = None
        self.last_result = None
        self.tool_rows = {}
        sc = getattr(master, "scale", 1.0)
        self.geometry("%dx%d" % (int(900 * sc), int(760 * sc)))
        self.minsize(int(640 * sc), int(560 * sc))
        st = bmbuild.jload(os.path.join(bmbuild.default_build_dir(), "BUILD_STATE.json"), {}) or {}
        self.v_input = tk.StringVar(value=(st.get("input") or {}).get("path", ""))
        self.v_src = tk.StringVar(value=(st.get("sources") or {}).get("mode", "github"))
        self.v_td = tk.StringVar(value=(st.get("sources") or {}).get("takedawn", "") if self.v_src.get() != "github" else "")
        self.v_xr = tk.StringVar(value=(st.get("sources") or {}).get("xboxrecomp", "") if self.v_src.get() != "github" else "")
        self.v_bd = tk.StringVar(value=bmbuild.default_build_dir())
        self.v_tools = tk.StringVar(value=bmtools.default_tools_dir())
        self.v_tc = tk.StringVar(value="")
        self._build()
        self.recheck_tools()
        self.update_estimate()
        if self.v_input.get():
            self.check_input()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------------------------------------------------------- layout
    def _row(self, parent, label):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=(4, 0))
        ttk.Label(f, text=label, width=16).pack(side="left")
        return f

    def _build(self):
        f = ttk.Frame(self, padding=(14, 10))
        f.pack(fill="both", expand=True)
        r = self._row(f, "Your game")
        ttk.Entry(r, textvariable=self.v_input).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Game folder...", command=self.pick_folder).pack(side="left", padx=(6, 0))
        ttk.Button(r, text="Disc image...", command=self.pick_image).pack(side="left", padx=(6, 0))
        ttk.Button(r, text="Check", command=self.check_input).pack(side="left", padx=(6, 0))
        self.input_lbl = ttk.Label(f, text="Supported: the retail North American (NTSC-U) Burnout 3: Takedown (installed game data folder, "
                                           "extracted disc folder or disc image). It is read in place.", wraplength=820, justify="left")
        self.input_lbl.pack(fill="x", pady=(2, 4))
        r = self._row(f, "Upstream source")
        self.src_box = ttk.Combobox(r, state="readonly", values=[t for k, t in SOURCES], width=56)
        self.src_box.current([k for k, t in SOURCES].index(self.v_src.get()) if self.v_src.get() in [k for k, t in SOURCES] else 0)
        self.src_box.bind("<<ComboboxSelected>>", lambda e: self.v_src.set(SOURCES[self.src_box.current()][0]))
        self.src_box.pack(side="left")
        r = self._row(f, "  Takedawn / xboxrecomp")
        ttk.Entry(r, textvariable=self.v_td).pack(side="left", fill="x", expand=True)
        ttk.Entry(r, textvariable=self.v_xr).pack(side="left", fill="x", expand=True, padx=(6, 0))
        tf = ttk.LabelFrame(f, text="Tools (pinned versions; nothing is installed system-wide)", padding=(8, 4))
        tf.pack(fill="x", pady=(6, 0))
        cols = ("tool", "status", "found", "where")
        self.tools_tv = ttk.Treeview(tf, columns=cols, show="headings", height=6, selectmode="extended")
        for c, w in zip(cols, (110, 70, 230, 380)):
            self.tools_tv.heading(c, text=c.upper(), anchor="w")
            self.tools_tv.column(c, width=w, anchor="w", stretch=c == "where")
        self.tools_tv.tag_configure("bad", foreground="#d9534f")
        self.tools_tv.pack(fill="x")
        b = ttk.Frame(tf)
        b.pack(fill="x", pady=(4, 0))
        ttk.Button(b, text="Use existing toolchain folder...", command=self.pick_toolchain).pack(side="left")
        ttk.Button(b, text="Download selected (asks per tool)...", command=self.download_selected).pack(side="left", padx=(6, 0))
        ttk.Button(b, text="Check again", command=self.recheck_tools).pack(side="left", padx=(6, 0))
        ttk.Label(b, text="Tools folder:").pack(side="left", padx=(12, 4))
        ttk.Entry(b, textvariable=self.v_tools, width=40).pack(side="left", fill="x", expand=True)
        r = self._row(f, "Build folder")
        ttk.Entry(r, textvariable=self.v_bd).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Browse...", command=self.pick_build_dir).pack(side="left", padx=(6, 0))
        self.est_lbl = ttk.Label(f, text="", wraplength=820, justify="left")
        self.est_lbl.pack(fill="x", pady=(2, 4))
        bb = ttk.Frame(f)
        bb.pack(fill="x", pady=(4, 4))
        self.build_btn = ttk.Button(bb, text="Build Mashup", command=self.start_build, style="Accent.TButton")
        self.build_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bb, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(6, 0))
        self.back_btn = ttk.Button(bb, text="Switch back to previous build", command=self.switch_back)
        self.back_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bb, text="Open build folder", command=lambda: _try(lambda: os.startfile(self.v_bd.get()))).pack(side="left", padx=(6, 0))
        self.progress = ttk.Progressbar(f, mode="determinate", maximum=len(bmbuild.STEPS))
        self.progress.pack(fill="x", pady=(2, 2))
        cols = ("step", "status", "seconds", "disk")
        self.steps_tv = ttk.Treeview(f, columns=cols, show="headings", height=8)
        for c, w in zip(cols, (360, 220, 90, 90)):
            self.steps_tv.heading(c, text=c.upper(), anchor="w")
            self.steps_tv.column(c, width=w, anchor="w", stretch=c == "step")
        for s in bmbuild.STEPS:
            self.steps_tv.insert("", "end", iid=s, values=(STEP_TEXT[s], "", "", ""))
        self.steps_tv.pack(fill="x")
        self.result = ttk.Label(f, text="", wraplength=820, justify="left", font=("Segoe UI", 10, "bold"))
        self.result.pack(fill="x", pady=(4, 2))
        lf = ttk.Frame(f)
        lf.pack(fill="both", expand=True)
        self.log = tk.Text(lf, height=8, wrap="none", state="disabled", font=("Consolas", 9))
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log["yscrollcommand"] = sb.set
        self.back_btn["state"] = "normal" if os.path.isdir(os.path.join(self.launcher, "host-local.prev")) else "disabled"

    # ---------------------------------------------------------------- inputs
    def pick_folder(self):
        p = filedialog.askdirectory(parent=self, title="Your installed game data folder or extracted disc folder")
        if p:
            self.v_input.set(os.path.normpath(p))
            self.check_input()

    def pick_image(self):
        p = filedialog.askopenfilename(parent=self, title="Your disc image", filetypes=[("Disc images", "*.iso *.xiso"), ("All files", "*.*")])
        if p:
            self.v_input.set(os.path.normpath(p))
            self.check_input()

    def pick_toolchain(self):
        p = filedialog.askdirectory(parent=self, title="A folder that already holds the pinned toolchain")
        if p:
            self.v_tc.set(os.path.normpath(p))
            self.recheck_tools()

    def pick_build_dir(self):
        p = filedialog.askdirectory(parent=self, title="Build folder (needs about 0.6 GB free)")
        if p:
            self.v_bd.set(os.path.normpath(p))
            self.update_estimate()

    def check_input(self):
        exp = bmbuild.jload(os.path.join(bmhost.active_source(self.launcher) or "", "build", "EXPECTED.json"), {}) or {}
        try:
            info = bmimage.inspect(self.v_input.get(), (exp.get("regen") or {}).get("xbe_sha256"))
            ok, txt = info["supported"], "%s: %s - %s" % (info["kind"], info["reason"], info["facts"]["title"])
        except bmimage.Refused as e:
            ok, txt = False, "Not usable: %s" % e
        self.input_ok = ok
        self.input_lbl.configure(text=("OK  " if ok else "REFUSED  ") + txt + ("" if ok else "\n" + bmbuild.RECOVERY["input"]),
                                 foreground="#3fb950" if ok else "#d9534f")
        return ok

    def tool_args(self):
        a = ["--tools", self.v_tools.get()]
        if self.v_tc.get():
            a += ["--toolchain", self.v_tc.get()]
        return a

    def recheck_tools(self):
        lay = bmtools.layout(self.v_tools.get(), self.v_tc.get() or None)
        res = _try(lambda: bmtools.check(lay), {}) or {}
        self.tools_res = res
        self.tools_tv.delete(*self.tools_tv.get_children())
        for k, v in res.items():
            self.tools_tv.insert("", "end", iid=k, values=(k, "OK" if v["ok"] else "MISSING", v["found"], v["path"]),
                                 tags=() if v["ok"] else ("bad",))
        return res

    def update_estimate(self):
        est = bmbuild.jload(bmbuild.EST_PATH, {}) or {}
        bd = self.v_bd.get()
        probe = bd
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        free = _try(lambda: __import__("shutil").disk_usage(probe).free / 1e9, None)
        self.est_lbl.configure(text="Default build folder: %s (outside the source checkout). A clean build takes about %d min and %.1f GB; a "
                                    "rebuild with nothing changed about %d s. Free on that drive: %s." % (
                                        bmbuild.default_build_dir(), round((est.get("clean_total_s") or 180) / 60.0),
                                        ((est.get("clean_total_mb") or 600) + 500) / 1000.0, est.get("warm_total_s") or 10,
                                        "%.1f GB" % free if free is not None else "?"))

    # ---------------------------------------------------------------- downloads
    def download_selected(self):
        sel = [i for i in self.tools_tv.selection() if i in bmtools.spec()] or [k for k, v in (self.tools_res or {}).items()
                                                                                if not v["ok"] and k in bmtools.spec()]
        if not sel:
            messagebox.showinfo(TITLE, "Nothing to download: select a MISSING tool.", parent=self)
            return []
        S = bmtools.spec()
        order = []

        def add(t):
            for n in S[t]["needs"]:
                if not (self.tools_res.get(n) or {}).get("ok"):
                    add(n)
            if t not in order:
                order.append(t)
        for t in sel:
            add(t)
        yes = []
        for t in order:
            p = bmtools.plan_download(t, self.v_tools.get())
            if self.ask(TITLE, "%s\n\nDownload and unpack it now?" % bmtools.notice_text(p), parent=self):
                yes.append(t)
            else:
                self._log("not downloaded: %s (not confirmed)" % t)
        if yes:
            self._start(["download"] + yes + ["--yes", "--events"] + self.tool_args(), "download")
        return yes

    # ---------------------------------------------------------------- build
    def build_args(self):
        a = ["build", "--input", self.v_input.get(), "--build-dir", self.v_bd.get(), "--source", self.v_src.get(), "--events"] + self.tool_args()
        if self.v_src.get() != "github":
            a += ["--takedawn-src", self.v_td.get(), "--xboxrecomp-src", self.v_xr.get()]
        return a

    def start_build(self):
        if self.job and self.job.running():
            messagebox.showinfo(TITLE, "A build is running: wait for it or press Cancel.", parent=self)
            return False
        if not self.check_input():
            return False
        for s in bmbuild.STEPS:
            self.steps_tv.item(s, values=(STEP_TEXT[s], "", "", ""))
        self.progress.configure(value=0)
        self._start(self.build_args(), "build")
        return True

    def _start(self, args, kind):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._log("> bmbuild " + " ".join(('"%s"' % x if " " in x else x) for x in args))
        self.job = self.Step("build_mashup", args, root=self.launcher)
        self.job_kind = kind
        self.last_result = None
        self.cancel_at = None
        self.build_btn["state"] = "disabled"
        self.cancel_btn["state"] = "normal"
        self.result.configure(text="Running... (Cancel stops it; completed steps are kept)", foreground="#58a6ff")
        self.after(100, self._poll)

    def _poll(self):
        done = False
        try:
            while True:
                ln = self.job.lines.get_nowait()
                if ln is None:
                    done = True
                    break
                self._line(ln)
        except Exception:  # noqa: BLE001  (queue.Empty)
            pass
        if self.cancel_at and not done and self.job.running() and self._now() - self.cancel_at > 20:
            self._log("... the build did not stop within 20 s: ending its process tree")
            self.job.cancel()
            self.cancel_at = None
        if not done:
            self.after(100, self._poll)
            return
        self._finished(self.job.rc)

    def _now(self):
        import time
        return time.time()

    def _line(self, ln):
        if ln.startswith("@@ "):
            ev = _try(lambda: json.loads(ln[3:]), {}) or {}
            if ev.get("ev") == "step" and ev.get("name") in bmbuild.STEPS:
                s = ev["name"]
                txt = {"running": "running" + (" (%s)" % ev.get("why") if ev.get("why") else ""), "reused": "reused (verified)",
                       "done": "done", "failed": "FAILED", "cancelled": "cancelled"}.get(ev["status"], ev["status"])
                self.steps_tv.item(s, values=(STEP_TEXT[s], txt, "" if ev.get("seconds") is None else "%.0f s" % ev["seconds"],
                                              "" if ev.get("disk_mb") is None else "%.0f MB" % ev["disk_mb"]))
                if ev["status"] in ("done", "reused"):
                    self.progress.configure(value=bmbuild.STEPS.index(s) + 1)
            elif ev.get("ev") == "result":
                self.last_result = ev
            elif ev.get("ev") == "download":
                self.result.configure(text="Downloading %s: %.1f / %.1f MB" % (ev["tool"], ev["bytes"] / 1e6, (ev.get("total") or 0) / 1e6))
            elif ev.get("ev") == "plan":
                self._log("free %s MB, this run needs about %s MB" % (ev.get("free_mb"), ev.get("need_mb")))
            return
        self._log(ln)

    def _finished(self, rc):
        self.build_btn["state"] = "normal"
        self.cancel_btn["state"] = "disabled"
        r = self.last_result or {}
        if self.job_kind == "download":
            msg = "Downloads finished." if rc == 0 else "A download did not complete (see the log); nothing unverified was kept."
            self.recheck_tools()
        elif rc == bmbuild.RC_OK:
            msg = "DONE: the verified build is installed in host-local (the previous one is kept). Play is enabled when your game data is prepared."
        elif rc == bmbuild.RC_CANCELLED or self.job.cancelled:
            msg = bmbuild.RECOVERY["cancelled"]
        else:
            msg = "%s\nWhat to do: %s" % (r.get("message") or "the build ended with status %s" % rc, r.get("recovery") or "see the log")
        self.result.configure(text=msg, foreground="#3fb950" if rc == 0 else "#d29922" if rc == bmbuild.RC_CANCELLED else "#d9534f")
        self.back_btn["state"] = "normal" if os.path.isdir(os.path.join(self.launcher, "host-local.prev")) else "disabled"
        self.on_change()

    def cancel(self):
        if not (self.job and self.job.running()):
            return
        self._log("... cancelling (the build stops its child processes)")
        if self.job_kind == "build":
            _try(lambda: open(os.path.join(self.v_bd.get(), "CANCEL"), "w").close())
            self.cancel_at = self._now()
        else:
            self.job.cancel()

    def switch_back(self):
        if self.job and self.job.running():
            return None
        try:
            r = bmhost.switch_back(self.launcher, log=self._log)
            self.result.configure(text="Switched: host-local now holds %s (the other build is kept as the previous one)." % r["now"], foreground="#3fb950")
        except bmhost.InstallError as e:
            r = None
            self.result.configure(text="Not switched: %s" % e, foreground="#d9534f")
        self.on_change()
        return r

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_close(self):
        if self.job and self.job.running():
            if not messagebox.askyesno(TITLE, "A build is running. Cancel it and close?", parent=self):
                return
            self.cancel()
            self.job.cancel()
        self.destroy()


def open_window(master, launcher=None, on_change=None):
    w = getattr(master, "_build_window", None)
    if w is not None and _try(lambda: w.winfo_exists(), False):
        w.lift()
        return w
    w = BuildWindow(master, launcher=launcher, on_change=on_change)
    master._build_window = w
    return w
