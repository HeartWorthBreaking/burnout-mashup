"""bmupdate_gui.py - the launcher's "Updates" window (tkinter; Help tab -> "Check for updates..."). Every button runs ONE step of
tools/launcher/bmupdate.py (the same CLI as update.cmd) as a child process: Check for updates, Download, Prepare, Build and install,
Switch back, Install an older version, Discard, Cancel. Opening the window contacts nothing (it reads update_channel.json and the
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
import bmupdate  # noqa: E402

bmops.STEPS.setdefault("update", (os.path.join("launcher", "bmupdate.py"), []))
TITLE = "Burnout Mashup updates"
STEPS = ("check", "download", "prepare", "build")


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

    def _build(self):
        f = ttk.Frame(self, padding=(14, 10))
        f.pack(fill="both", expand=True)
        self.channel_lbl = ttk.Label(f, text="", wraplength=800, justify="left", font=("Segoe UI", 10, "bold"))
        self.channel_lbl.pack(fill="x")
        self.version_lbl = ttk.Label(f, text="", wraplength=800, justify="left")
        self.version_lbl.pack(fill="x", pady=(4, 2))
        ttk.Label(f, text="Nothing is checked or downloaded by itself: each button below is one step, run only when you press it. Your "
                          "profile, saves, mods, plugin approvals and game data are never touched; new plugins still need your approval.",
                  wraplength=800, justify="left").pack(fill="x", pady=(0, 6))
        bb = ttk.Frame(f)
        bb.pack(fill="x", pady=(2, 2))
        self.btn = {}
        for key, text, cmd in (("check", "Check for updates", lambda: self.run("check")), ("download", "Download", lambda: self.run("download")),
                               ("prepare", "Prepare (unpack + verify)", lambda: self.run("prepare")),
                               ("build", "Build and install", self.build)):
            b = ttk.Button(bb, text=text, command=cmd, style="Accent.TButton" if key == "check" else "TButton")
            b.pack(side="left", padx=(0, 6))
            self.btn[key] = b
        self.cancel_btn = ttk.Button(bb, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left")
        b2 = ttk.Frame(f)
        b2.pack(fill="x", pady=(2, 6))
        self.btn["switch"] = ttk.Button(b2, text="Switch back to previous version", command=lambda: self.run("switch-back"))
        self.btn["switch"].pack(side="left", padx=(0, 6))
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

    # ---------------------------------------------------------------- state (local files only, no network)
    def refresh(self):
        s = _try(lambda: bmupdate.Updater(self.launcher).status(), {}) or {}
        self.state = s
        if s.get("configured"):
            self.channel_lbl.configure(text="Update channel: %s (%s). Trusted signing key(s): %s" % (s["channel"], s["where"], ", ".join(s["trusted_keys"])))
        else:
            self.channel_lbl.configure(text=s.get("why") or bmupdate.NO_CHANNEL)
        self.version_lbl.configure(text="Version in use: %s (source %s)   |   previous: %s   |   pending: %s" % (
            s.get("version", "?"), s.get("source") or "-", s.get("previous") or "-",
            ("%s, next step: %s" % ((s.get("pending") or {}).get("version"), s.get("next_step"))) if s.get("pending") else "-"))
        busy = bool(self.job and self.job.running())
        nxt = s.get("next_step")
        on = {"check": s.get("configured"), "download": nxt == "download", "prepare": nxt == "prepare", "build": nxt == "build",
              "switch": bool(s.get("previous")), "older": s.get("configured"), "discard": bool(s.get("pending"))}
        for k, b in self.btn.items():
            b["state"] = "normal" if on.get(k) and not busy else "disabled"
        self.cancel_btn["state"] = "normal" if busy else "disabled"

    # ---------------------------------------------------------------- steps (each one only on a click)
    def run(self, cmd, extra=()):
        if self.job and self.job.running():
            return False
        args = [cmd, "--launcher", self.launcher, "--events"] + list(extra)
        self._log("> update " + " ".join(('"%s"' % x if " " in x else x) for x in args))
        self.job = self.Step("update", args, root=bmhost.LAUNCHER)     # the program of this launcher; --launcher names the installation
        self.job_kind, self.last_result = cmd, None
        self.progress.configure(value=0)
        self.result.configure(text="Running %s... (Cancel stops it)" % cmd, foreground="#58a6ff")
        self.refresh()
        self.after(100, self._poll)
        return True

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
        self.job = None
        self.refresh()
        self.on_change()

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
