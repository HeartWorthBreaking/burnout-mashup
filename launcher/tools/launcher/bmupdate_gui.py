"""bmupdate_gui.py - the launcher's "Updates" window (tkinter; Help tab -> "Check for updates..."). Every button runs ONE step of
tools/launcher/bmupdate.py (the same CLI as update.cmd) as a child process: Check for updates, Download, Prepare, Build and install,
Switch back, Install an older version, Discard, Cancel; in the Windows package (layout 2) also Install (the prepared package
replaces the program in one undoable step; the launcher then starts again). "Update now" runs those steps one after the other on one
click, stopping at the first that fails (pressing it again goes on from there). Opening the window contacts nothing (it reads update_channel.json and the
local update state only); there is no automatic, background or scheduled check. Without a configured channel the window says so and
explains how the maintainer sets one. Original code (MIT)."""
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmhost  # noqa: E402
import bmops  # noqa: E402
import bmpaths  # noqa: E402
import bmupdate  # noqa: E402

bmops.STEPS.setdefault("update", (os.path.join("launcher", "bmupdate.py"), []))
TITLE = "Burnout Mashup updates"
STEPS = ("check", "download", "prepare", "build")
RESUME_MARK = "UPDATE_NOW.json"     # launcher\update-state (carried over by an install): Update now goes on after the restart


def auto_next(done, cls, status):
    """Update now: the step after `done` ended well (None: the click itself); "" = finished. Only the steps' own state decides."""
    s = status or {}
    if done is None:
        return "build" if (s.get("pending") or {}).get("installed") else "check"
    if done in ("install", "build") or (done == "check" and cls == "up_to_date"):
        return ""
    return s.get("next_step") or ""


def resume_mark(launcher):
    return os.path.join(launcher, "update-state", RESUME_MARK)


def _try(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001  (a window must not die on a probe)
        return default


class UpdateWindow(tk.Toplevel):
    def __init__(self, master, launcher=None, on_change=None, step_factory=None, ask=None, ask_string=None):
        super().__init__(master)
        self.title(TITLE)
        self.launcher = os.path.abspath(launcher or bmhost.LAUNCHER)
        self.on_change = on_change or (lambda: None)
        self.Step = step_factory or bmops.Step
        self.ask = ask or messagebox.askyesno
        self.ask_string = ask_string or simpledialog.askstring
        self.job = self.job_kind = self.last_result = None
        self.auto = False
        sc = getattr(master, "scale", 1.0)
        self.geometry("%dx%d" % (int(860 * sc), int(640 * sc)))
        self.minsize(int(620 * sc), int(480 * sc))
        import bmbuild
        bd = bmbuild.default_build_dir()
        st = bmbuild.jload(os.path.join(bd, "BUILD_STATE.json"), {}) or {}
        self.v_input = tk.StringVar(value=(st.get("input") or {}).get("path", ""))
        self.v_bd = tk.StringVar(value=bd)
        self.v_tc = tk.StringVar(value="")
        self._build()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        _try(lambda: __import__("bmtheme").dark_titlebar(self))

    def _build(self):
        f = ttk.Frame(self, padding=(14, 10))
        f.pack(fill="both", expand=True)
        self.channel_lbl = ttk.Label(f, text="", wraplength=800, justify="left", font=("Segoe UI", 10, "bold"))
        self.channel_lbl.pack(fill="x")
        self.version_lbl = ttk.Label(f, text="", wraplength=800, justify="left")
        self.version_lbl.pack(fill="x", pady=(4, 2))
        ttk.Label(f, text="Update now does everything on one click: checks, downloads, verifies, installs and restarts the launcher (close "
                          "the game and the Workbench first). Nothing is checked or downloaded by itself; single steps are under Advanced options. "
                          "Your profile, saves, mods, plugin approvals and game data are never touched; new plugins still need your approval.",
                  wraplength=800, justify="left").pack(fill="x", pady=(0, 6))
        top = ttk.Frame(f)
        top.pack(fill="x", pady=(2, 6))
        self.btn = {}
        self.btn["update"] = ttk.Button(top, text="Update now", command=self.update_now, style="Accent.TButton")
        self.btn["update"].pack(side="left", padx=(0, 6))
        self.cancel_btn = ttk.Button(top, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(0, 6))
        self.btn["switch"] = ttk.Button(top, text="Switch back to previous version", command=lambda: self.run("switch-back"))
        self.btn["switch"].pack(side="left", padx=(0, 6))
        ttk.Button(top, text="Advanced options", command=self.toggle_advanced).pack(side="left")
        self.top_row = top
        self.adv = ttk.Frame(f)          # Advanced options: the single steps; shown on the button's click
        outer, f = f, self.adv
        bb = ttk.Frame(f)
        bb.pack(fill="x", pady=(2, 2))
        for key, text, cmd in (("check", "Check for updates", lambda: self.run("check")), ("download", "Download", lambda: self.run("download")),
                               ("prepare", "Prepare (unpack + verify)", lambda: self.run("prepare")),
                               ("install", "Install (restarts)", self.install),
                               ("build", "Build and install", self.build)):
            b = ttk.Button(bb, text=text, command=cmd)
            b.pack(side="left", padx=(0, 6))
            self.btn[key] = b
        b2 = ttk.Frame(f)
        b2.pack(fill="x", pady=(2, 6))
        self.btn["older"] = ttk.Button(b2, text="Install an older version...", command=self.older)
        self.btn["older"].pack(side="left", padx=(0, 6))
        self.btn["discard"] = ttk.Button(b2, text="Discard pending update", command=self.discard)
        self.btn["discard"].pack(side="left")
        bf = ttk.LabelFrame(f, text="Build settings (as in the Build window)", padding=(8, 4))
        bf.pack(fill="x")
        for label, var in (("Your game", self.v_input), ("Build folder", self.v_bd), ("Toolchain (optional)", self.v_tc)):
            r = ttk.Frame(bf)
            r.pack(fill="x", pady=(2, 0))
            ttk.Label(r, text=label, width=20).pack(side="left")
            ttk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True)
        f = outer
        self.progress = ttk.Progressbar(f, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(6, 2))
        self.result = ttk.Label(f, text="", wraplength=800, justify="left", font=("Segoe UI", 10, "bold"))
        self.result.pack(fill="x", pady=(2, 2))
        lf = ttk.Frame(f)
        lf.pack(fill="both", expand=True)
        self.log = tk.Text(lf, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log["yscrollcommand"] = sb.set

    def toggle_advanced(self, show=None):
        if show is None:
            show = not self.adv.winfo_manager()
        if show and not self.adv.winfo_manager():
            self.adv.pack(fill="x", after=self.top_row)
        elif not show:
            self.adv.pack_forget()

    # ---------------------------------------------------------------- state (local files only, no network)
    def refresh(self):
        s = _try(lambda: bmupdate.Updater(self.launcher).status(), {}) or {}
        self.state = s
        if s.get("configured"):
            self.channel_lbl.configure(text="Update channel: %s (%s). Trusted signing key(s): %s" % (s["channel"], s["where"], ", ".join(s["trusted_keys"])))
        else:
            self.channel_lbl.configure(text=s.get("why") or bmupdate.NO_CHANNEL)
        self.version_lbl.configure(text="Version in use: %s (%s)   |   previous: %s   |   pending: %s" % (
            s.get("version", "?"), ("Windows package" if s.get("layout") == 2 else "source %s" % (s.get("source") or "-")),
            s.get("kept_previous") or s.get("previous") or "-",
            ("%s, next step: %s" % ((s.get("pending") or {}).get("version"), s.get("next_step"))) if s.get("pending") else "-"))
        busy = bool(self.job and self.job.running())
        nxt = s.get("next_step")
        on = {"update": s.get("configured"), "check": s.get("configured"), "download": nxt == "download", "prepare": nxt == "prepare", "build": nxt == "build",
              "install": nxt == "install", "switch": bool(s.get("previous") or s.get("kept_previous")), "older": s.get("configured"), "discard": bool(s.get("pending"))}
        for k, b in self.btn.items():
            b["state"] = "normal" if on.get(k) and not busy else "disabled"
        self.cancel_btn["state"] = "normal" if busy else "disabled"

    # ---------------------------------------------------------------- steps (each one only on a click)
    def run(self, cmd, extra=()):
        if self.job and self.job.running():
            return False
        args = [cmd, "--launcher", self.launcher, "--events"] + list(extra)
        self._log("> update " + " ".join(('"%s"' % x if " " in x else x) for x in args))
        inst = bmpaths.install_root(self.launcher)
        kw = {"cwd": inst} if inst and cmd in ("install", "switch-back") else {}
        self.job = self.Step("update", args, root=bmhost.LAUNCHER, **kw)     # the program of this launcher; --launcher names the installation
        self.job_kind, self.last_result = cmd, None
        self.progress.configure(value=0)
        self.result.configure(text="Running %s... (Cancel stops it)" % cmd, foreground="#58a6ff")
        self.refresh()
        self.after(100, self._poll)
        return True

    def update_now(self):
        """one click: every step in turn. The click is the consent, so no question on the way; Cancel stops it, Switch back undoes it."""
        if self.job and self.job.running():
            return False
        if not self.state.get("configured"):
            self.result.configure(text=self.state.get("why") or bmupdate.NO_CHANNEL, foreground="#d29922")
            return False
        self.auto = True
        return self._auto_step(None, None)

    def _auto_step(self, done, cls):
        self.refresh()
        nxt = auto_next(done, cls, self.state)
        if not nxt:
            self._auto_end()
            return False
        if nxt == "install":
            _try(lambda: bmupdate.jsave(resume_mark(self.launcher), {"from": self.state.get("version")}))
            return self.run("install")
        if nxt == "build":
            if not self.v_input.get():
                self._auto_end()
                self.toggle_advanced(True)
                self.result.configure(text="This update needs a new Build Mashup: give your game under Build settings, then press Update now "
                                           "again.", foreground="#d29922")
                return False
            return self.build()
        return self.run(nxt)

    def _auto_end(self):
        self.auto = False
        _try(lambda: os.remove(resume_mark(self.launcher)))

    def resume(self):
        """the first start after an Update now install: go on when the new release needs a build; no check, no download of a release"""
        self.refresh()
        if (self.state.get("pending") or {}).get("installed") and self.state.get("next_step") == "build":
            self.auto = True
            return self._auto_step(None, None)
        self._auto_end()
        return False

    def install(self):
        if not self.ask(TITLE, "Install the prepared update now?\nThe program folder and the two exes are replaced in one step (undone "
                               "on any error); your game data, mods, saves, settings and builds are carried over. The launcher then "
                               "starts again. Close the game and the Workbench first.", parent=self):
            return False
        return self.run("install")

    def build(self):
        if not self.v_input.get():
            self.result.configure(text="Give your game (the same input as for Build Mashup) first.", foreground="#d9534f")
            return False
        extra = ["--input", self.v_input.get(), "--build-dir", self.v_bd.get()]
        if self.v_tc.get():
            extra += ["--toolchain", self.v_tc.get()]
        return self.run("build", extra)

    def older(self):
        v = self.ask_string(TITLE, "Install which OLDER version of the channel? (for example 0.1.0)", parent=self)
        if not v:
            return False
        if not self.ask(TITLE, "Install the older version %s on purpose?\nThe version in use is kept as the previous one." % v, parent=self):
            return False
        return self.run("install-older", [v.strip(), "--yes"])

    def discard(self):
        if self.ask(TITLE, "Forget the pending update and delete its download and unpacked folder?\nThe version in use is not touched.", parent=self):
            return self.run("discard", ["--yes"])
        return False

    def cancel(self):
        if self.job and self.job.running():
            self.auto = False
            _try(lambda: os.remove(resume_mark(self.launcher)))
            self._log("... cancelling")
            _try(lambda: bmupdate.main(["cancel", self.v_bd.get()], out=lambda s: None))
            self.after(20000, lambda: self.job.cancel() if self.job and self.job.running() else None)

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
        if not done:
            self.after(100, self._poll)
            return
        self._finished(self.job.rc)

    def _line(self, ln):
        if ln.startswith("@@ "):
            ev = _try(lambda: json.loads(ln[3:]), {}) or {}
            if ev.get("ev") == "result":
                self.last_result = ev
            elif ev.get("ev") == "download" and ev.get("total"):
                self.progress.configure(value=100.0 * ev["bytes"] / ev["total"])
                self.result.configure(text="Downloading: %.1f / %.1f MB" % (ev["bytes"] / 1e6, ev["total"] / 1e6))
            elif ev.get("ev") == "step" and ev.get("status") in ("done", "reused"):
                self.result.configure(text="Build Mashup: %s %s" % (ev.get("name"), ev["status"]))
            return
        if ln.startswith("{"):
            return
        self._log(ln)

    def _finished(self, rc):
        r = self.last_result or {}
        msg = r.get("message") or "ended with status %s" % rc
        if r.get("recovery"):
            msg += "\nWhat to do: " + r["recovery"]
        self.result.configure(text=msg, foreground="#3fb950" if rc == 0 else "#d29922" if rc in (bmupdate.RC_CANCELLED, bmupdate.RC_NOCHANNEL) else "#d9534f")
        if rc == 0:
            self.progress.configure(value=100)
        kind, auto = self.job_kind, self.auto
        self.job = None
        if rc == 0 and r.get("restart"):
            self.auto = False              # the mark stays: the new version's resume decides
            self.restart(msg, quiet=auto)
            return
        if auto and rc == 0:
            if self._auto_step(kind, r.get("cls")):
                return
        elif auto:
            self._auto_end()
        self.refresh()
        self.on_change()

    def restart(self, msg, quiet=False):
        r"""after an install / switch back: the program in app\ is the new one - this window's code is the old one; start again"""
        inst = bmpaths.install_root(self.launcher)
        if not quiet:
            _try(lambda: messagebox.showinfo(TITLE, msg + "\n\nThe launcher starts again now.", parent=self))
        exe = os.path.join(inst, bmpaths.EXE) if inst else None
        if exe and os.path.isfile(exe) and not os.environ.get("BMASHUP_NO_RESTART"):
            import subprocess
            _try(lambda: subprocess.Popen([exe], cwd=inst, close_fds=True))
        _try(lambda: self.master.destroy())

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_close(self):
        if self.job and self.job.running():
            if not self.ask(TITLE, "An update step is running. Cancel it and close?", parent=self):
                return
            self.cancel()
            self.job.cancel()
        self.destroy()


def open_window(master, launcher=None, on_change=None):
    w = getattr(master, "_update_window", None)
    if w is not None and _try(lambda: w.winfo_exists(), False):
        w.lift()
        return w
    w = UpdateWindow(master, launcher=launcher, on_change=on_change)
    master._update_window = w
    return w
