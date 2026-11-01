"""bmgui.py - the Burnout Mashup launcher window (release readiness R1; Python 3.11+ standard library: tkinter).

One window, four tabs, everything inside the bundle folder:
  Setup  - the steps in order with their state: 1 game data (Browse folder / Browse disc image / drop it on the window or on
           "Burnout Mashup.cmd"), 2 check this PC (preflight), 3 build the demo mods; progress, Cancel, a log, a plain-language
           result line per step (the tools' own "refused: reason + fix" lines are shown as they are)
  Mods   - every mod with on / off, compatibility (OK / WARN / BLOCKED + reasons), native code marked; Import folder / zip
           (preview first, then copy into mods\\user; never run, never approved), stale profile entries
  Play   - Play (play.cmd: profile, saves and settings stay in this folder), then the results of the last game
  Help   - quickstart, troubleshooting, diagnostic export (diag.cmd: versions + redacted log, no game data), backup of the profile
Keyboard: Ctrl+1..4 tabs, F5 refresh, Esc cancel the running step, Alt+underlined letters on buttons. Resizable; DPI aware.
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmcompat  # noqa: E402
import bmmods  # noqa: E402
import bmops  # noqa: E402
import bmtheme  # noqa: E402
import bmhost  # noqa: E402  (BUILD MASHUP: the installed host and the Play rule)
import bmpaths  # noqa: E402  (0.2.0 layout 2: game copy + your mods in <install>\\gamedata)

ROOT = bmops.ROOT
TITLE = "Burnout Mashup"
LEVEL_TAG = {bmcompat.OK: "ok", bmcompat.WARN: "warn", bmcompat.BLOCKED: "blocked"}


def dpi_aware():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def bundle_state(root=ROOT):
    """What is prepared: dict for the Setup tab (reads files only)."""
    ps = bmhost.play_state(root)        # BUILD MASHUP: a host counts only as a verified build with a consistent HOST_INFO.json
    host = ps["host_kind"] if ps["host_ok"] else None
    gen = bmpaths.mods_dir(root, "generated")
    return {"host": host, "host_problems": ps["problems"], "data": os.path.isfile(os.path.join(bmpaths.gamedata(root), ".complete")),
            "demos": os.path.isdir(gen) and any(os.path.isfile(os.path.join(gen, d, "mod.toml")) for d in os.listdir(gen)),
            "preflight": _read(os.path.join(root, "diag", "preflight_last.txt"))}


def versions_line(root=ROOT):
    """'Package X | host Y (platform Z)' for bug reports (BUNDLE.json + the host's HOST_INFO.json; '?' when missing)."""
    import json
    try:
        b = json.load(open(os.path.join(root, "BUNDLE.json"), encoding="utf-8")).get("bundle", "?")
        pkg = "%s %s" % (b.get("name", "?"), b.get("version", "?")) if isinstance(b, dict) else str(b)
    except (OSError, ValueError, AttributeError):
        try:
            v = json.load(open(os.path.join(root, "VERSION.json"), encoding="utf-8"))
            pkg = "%s %s (source tree)" % (v.get("product", "?"), v.get("release", "?"))
        except (OSError, ValueError, AttributeError):
            pkg = "?"
    host = "no host built yet"
    for d in ("host-local", "host"):
        p = os.path.join(root, d, "HOST_INFO.json")
        if bmhost.exe_name(os.path.join(root, d)):
            try:
                i = json.load(open(p, encoding="utf-8"))
                host = "%s %s (platform %s)" % (d, i.get("identity") or i.get("host_name") or "?", i.get("platform", "?"))
            except (OSError, ValueError):
                host = "%s (no HOST_INFO.json: compatibility not checked)" % d
            break
    return "Package: %s   |   Host: %s   |   Python %d.%d" % ((pkg, host) + tuple(sys.version_info[:2]))


def _read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


class Launcher(tk.Tk):
    def __init__(self, dropped=None, dpi=None, screen=None):
        """dpi / screen (tests only): pretend a display (e.g. 96 / 120 / 144 dpi on 1920x1080 or 2560x1440)"""
        super().__init__()
        self.title(TITLE)
        if dpi:
            self.tk.call("tk", "scaling", dpi / 72.0)
        # sizes in "96-dpi pixels" scaled to this display (the window is DPI aware: 125-300 % scaling keeps the layout),
        # never larger than the screen's work area (taskbar ~ 5 %)
        self.scale = max(1.0, (dpi or self.winfo_fpixels("1i")) / 96.0)
        sw, sh = screen or (self.winfo_screenwidth(), self.winfo_screenheight())
        self.screen = (sw, sh)
        mw, mh = min(int(760 * self.scale), int(sw * 0.9)), min(int(600 * self.scale), int(sh * 0.85))
        self.minsize(mw, mh)
        self.geometry("%dx%d" % (max(mw, min(int(1000 * self.scale), int(sw * 0.92))),
                                 max(mh, min(int(720 * self.scale), int(sh * 0.85)))))
        self.bundle = bmmods.Bundle(ROOT)
        self.step = None
        self.step_tail = []
        st = bmtheme.apply(self)                                        # dark theme; Treeview rows follow the font size
        st.configure("Play.Accent.TButton", font=self.fonts["h2"], padding=(36, 12))
        self.wraps = []                                                 # labels whose wrap width follows the window
        bar = ttk.Frame(self, style="Header.TFrame", padding=(18, 4, 18, 8))
        bar.pack(side="bottom", fill="x")                               # first: never pushed out of a small window
        self.status = ttk.Label(bar, anchor="w", text="Bundle: " + ROOT, style="Status.TLabel")
        self.status.pack(fill="x")
        bmtheme.header(self, TITLE, "launcher").pack(side="top", fill="x")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self._setup_tab()
        self._mods_tab()
        self._play_tab()
        self._help_tab()
        for w in self.wraps:                                            # until the first resize: never wider than the minimum
            w.configure(wraplength=int(560 * self.scale))
        for i in range(4):
            self.bind("<Control-Key-%d>" % (i + 1), lambda e, i=i: self.nb.select(i))
        self.bind("<F5>", lambda e: self.refresh())
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        _enable_drop(self, self.on_drop)
        bmtheme.finish(self)
        self.refresh()
        if dropped:
            self.after(300, lambda: self.on_drop(dropped))

    # ---------------- Setup ----------------
    def _setup_tab(self):
        f = ttk.Frame(self.nb, padding=(16, 12))
        self.nb.add(f, text="Setup")
        self.setup_rows = {}
        steps = [("host", "Host program", "Build Mashup builds it on this PC from this source tree and YOUR game (verified against "
                                          "the reference build, installed into host-local; the previous build is kept)."),
                 ("data", "1. Your game data", "Your own NTSC-U Burnout 3 copy: the installed Takedawn data folder or a disc "
                                               "image / folder. It is copied (read only) into gamedata\\."),
                 ("preflight", "2. Check this PC", "Windows, Vulkan driver, host, game data, mods - every problem with its fix."),
                 ("demos", "3. Demo mods", "Builds the demo car / tracks from YOUR data into mods\\generated (stays on this PC).")]
        buttons = {"host": (("Build Mashup...", 0, self.open_build), ("Previous build", 0, self.switch_back_build)),
                   "data": (("Browse folder...", 7, self.browse_folder), ("Browse disc image...", 7, self.browse_image)),
                   "preflight": (("Check now", 0, lambda: self.run_step("preflight")),),
                   "demos": (("Build demos", 6, lambda: self.run_step("demos")),)}
        for key, label, help_text in steps:                            # one card per step, top to bottom
            card = ttk.Frame(f, style="Card.TFrame", padding=(14, 6))
            card.pack(fill="x", pady=(0, 5))
            row = ttk.Frame(card, style="Card.TFrame")
            row.pack(fill="x")
            for text, ul, cmd in reversed(buttons.get(key, ())):   # packed first: a long state text never pushes a button out
                ttk.Button(row, text=text, underline=ul, command=cmd,
                           style="Accent.TButton" if key == "preflight" else "TButton").pack(side="right", padx=(6, 0))
            ttk.Label(row, text=label, style="CardTitle.TLabel").pack(side="left")
            s = ttk.Label(row, text="...", style="Card.TLabel", font=self.fonts["bold"])
            s.pack(side="left", padx=(12, 0))
            self.setup_rows[key] = s
            h = ttk.Label(card, text=help_text, style="CardMuted.TLabel", justify="left")
            h.pack(fill="x", pady=(2, 0))
            self.wraps.append(h)
        self.bind("<Alt-b>", lambda e: self.open_build())
        self.bind("<Alt-f>", lambda e: self.browse_folder())
        self.bind("<Alt-d>", lambda e: self.browse_image())
        self.bind("<Alt-c>", lambda e: self.run_step("preflight"))
        self.bind("<Alt-m>", lambda e: self.run_step("demos"))
        pf = ttk.Frame(f)
        pf.pack(fill="x", pady=(6, 4))
        self.progress = ttk.Progressbar(pf, mode="determinate", value=0)   # idle: empty bar
        self.progress.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ttk.Button(pf, text="Cancel (Esc)", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.result = ttk.Label(f, text="Drop your game folder or disc image on this window, or use Browse.", justify="left",
                                font=self.fonts["bold"])
        self.result.pack(fill="x", pady=(2, 0))
        self.wraps.append(self.result)
        lf = ttk.Frame(f)
        lf.pack(fill="both", expand=True, pady=(6, 0))
        self.log = tk.Text(lf, height=3, wrap="word", state="disabled")
        bmtheme.text_style(self.log, mono=True, pad=8)
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log["yscrollcommand"] = sb.set
        self.nb.bind("<Configure>", lambda e: [w.configure(wraplength=max(200, e.width - int(80 * self.scale)))
                                               for w in self.wraps])

    def browse_folder(self):
        p = filedialog.askdirectory(title="Your installed game data or game folder")
        if p:
            self.run_step("data_auto", [p])

    def browse_image(self):
        p = filedialog.askopenfilename(title="Your disc image", filetypes=[("Disc images", "*.iso *.xiso"), ("All files", "*.*")])
        if p:
            self.run_step("data_auto", [p])

    def on_drop(self, paths):
        p = paths[0] if isinstance(paths, (list, tuple)) else paths
        if not p:
            return
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "mod.toml")) or p.lower().endswith(".zip"):
            self.nb.select(1)
            self.import_mod(p)
        else:
            self.nb.select(0)
            self.run_step("data_auto", [p])

    def run_step(self, name, extra=()):
        if self.step and self.step.running():
            messagebox.showinfo(TITLE, "A step is still running: wait for it or press Cancel.")
            return
        self._log_clear()
        self._log("> " + name + (" " + " ".join(extra) if extra else ""))
        try:
            self.step = bmops.Step(name, extra)
        except OSError as e:
            self.result["text"] = "Could not start the step: %s" % e
            self.result["foreground"] = bmtheme.BAD
            return
        self.step_tail = []
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.cancel_btn["state"] = "normal"
        self.result["text"] = "Running... (Esc or Cancel stops it)"
        self.result["foreground"] = bmtheme.ACCENT_HI
        self.after(100, self._poll)

    def _poll(self):
        done = False
        try:
            while True:
                ln = self.step.lines.get_nowait()
                if ln is None:
                    done = True
                    break
                self.step_tail = (self.step_tail + [ln])[-40:]
                self._log(ln)
        except Exception:     # queue.Empty
            pass
        if not done:
            self.after(100, self._poll)
            return
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.cancel_btn["state"] = "disabled"
        self.result["text"] = bmops.explain(self.step.name, self.step.rc, self.step.cancelled, self.step_tail)
        self.result["foreground"] = bmtheme.state_colour("ok" if self.step.rc == 0 and not self.step.cancelled
                                                         else "warn" if self.step.cancelled else "bad")
        self.refresh()

    def cancel(self):
        if self.step and self.step.running():
            self.step.cancel()
            self._log("... cancelling")

    def _log(self, text):
        self.log["state"] = "normal"
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log["state"] = "disabled"

    def _log_clear(self):
        self.log["state"] = "normal"
        self.log.delete("1.0", "end")
        self.log["state"] = "disabled"

    def open_build(self):
        """the Build Mashup window (tools/launcher/bmbuild_gui.py; the same build as build-mashup.cmd)"""
        import bmbuild_gui
        return bmbuild_gui.open_window(self, on_change=self.refresh)

    def switch_back_build(self):
        try:
            r = bmhost.switch_back(ROOT, log=self._log)
            self.result["text"] = "Switched back: host-local now holds %s (the other build is kept as the previous one)." % r["now"]
        except bmhost.InstallError as e:
            self.result["text"] = "Not switched: %s" % e
        self.refresh()

    # ---------------- Mods ----------------
    def _mods_tab(self):
        f = ttk.Frame(self.nb, padding=(16, 12))
        self.nb.add(f, text="Mods")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="Import folder...", underline=0, style="Accent.TButton", command=lambda: self.import_mod(
            filedialog.askdirectory(title="A mod folder (it holds mod.toml)"))).pack(side="left")
        ttk.Button(bar, text="Import zip...", underline=7, command=lambda: self.import_mod(filedialog.askopenfilename(
            title="A mod .zip", filetypes=[("Zip", "*.zip")]))).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Turn on / off", underline=0, command=self.toggle).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Check profile", underline=7, command=self.show_stale).pack(side="left", padx=(6, 0))
        # the underlined letters work with Alt (ttk draws them only; the keys are bound here)
        self.bind("<Alt-i>", lambda e: self.import_mod(filedialog.askdirectory(title="A mod folder (it holds mod.toml)")))
        self.bind("<Alt-z>", lambda e: self.import_mod(filedialog.askopenfilename(title="A mod .zip", filetypes=[("Zip", "*.zip")])))
        self.bind("<Alt-t>", lambda e: self.toggle())
        self.bind("<Alt-r>", lambda e: self.show_stale())
        self.bind("<Alt-l>", lambda e: self.show_results())
        hint = ttk.Label(f, text="Native-code mods are approved only in the game (MODS page): never here.", style="Muted.TLabel")
        hint.pack(fill="x", pady=(8, 0))
        self.wraps.append(hint)
        cols = ("on", "check", "id", "version", "where", "code")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse", height=5)
        for c, w in zip(cols, [int(x * self.scale) for x in (50, 120, 260, 80, 90, 110)]):
            self.tree.heading(c, text=c.upper() if c != "check" else "COMPATIBILITY", anchor="w")
            self.tree.column(c, width=w, stretch=c == "id", anchor="w")
        self.tree.tag_configure("ok", foreground=bmtheme.TEXT)
        self.tree.tag_configure("blocked", foreground=bmtheme.BAD)
        self.tree.tag_configure("warn", foreground=bmtheme.WARN)
        self.tree.tag_configure("off", foreground=bmtheme.FAINT)
        self.mod_detail = tk.Text(f, height=4, wrap="word", state="disabled")
        bmtheme.text_style(self.mod_detail)
        self.mod_detail.pack(side="bottom", fill="x")                  # before the list: keeps its lines in a small window
        self.tree.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_mod())
        self.tree.bind("<space>", lambda e: self.toggle())
        self.rows = {}

    def refresh(self):
        s = bundle_state()
        pf = "pass" if "RESULT PASS" in s["preflight"] else "fail" if "RESULT FAIL" in s["preflight"] else ""
        for key, text, state in (("host", s["host"] or ("NOT USABLE - needs a built host: Build Mashup again" if s.get("host_problems") and "no host built yet" not in s["host_problems"][0] else "none yet - needs a built host: Build Mashup first"), "ok" if s["host"] else "bad"),
                                 ("data", "ready" if s["data"] else "not yet", "ok" if s["data"] else "idle"),
                                 ("preflight", {"pass": "PASS", "fail": "FAIL - see the log"}.get(pf, "not run yet"),
                                  {"pass": "ok", "fail": "bad"}.get(pf, "idle")),
                                 ("demos", "built" if s["demos"] else "not yet (optional)", "ok" if s["demos"] else "idle")):
            self.setup_rows[key].configure(text=("●  " if state == "ok" else "○  ") + text,
                                           foreground=bmtheme.state_colour(state))
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        try:
            mods = self.bundle.mods()
        except Exception as e:  # a broken profile must not stop the window
            mods = []
            self.status["text"] = "Mods could not be listed: %s" % e
        for r in mods:
            iid = self.tree.insert("", "end", values=("on" if r["enabled"] else "off", r["level"], r["id"] or r["name"],
                                                      r["version"], r["source"], "native code" if r["native_code"] else ""),
                                   tags=(LEVEL_TAG.get(r["level"], ""),) + (() if r["enabled"] else ("off",)))
            self.rows[iid] = r
        self.play_btn["state"] = "normal" if s["host"] and s["data"] else "disabled"
        if not s["host"] and s.get("host_problems") and "no host built yet" not in s["host_problems"][0]:
            self.status["text"] = "Host not usable: %s" % "; ".join(s["host_problems"])      # why Play is off (Build Mashup repairs it)
        self.play_hint["text"] = ("" if s["host"] and s["data"] else "Play needs a built host and your game data (Setup tab): Build Mashup first, then prepare your game data.")
        if getattr(self, "ver_lbl", None) is not None:                 # the Help tab's Package | Host line follows a new build
            self.ver_lbl.configure(text=versions_line())

    def show_mod(self):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.rows[sel[0]]
        tag = {"blocked": "bad", "warn": "warn"}.get(LEVEL_TAG.get(r["level"], ""), "ok")
        self.mod_detail["state"] = "normal"
        self.mod_detail.delete("1.0", "end")
        self.mod_detail.insert("end", "%s  %s" % (r["name"], r["version"]), "bold")
        self.mod_detail.insert("end", "   %s\n" % r["folder"], "muted")
        self.mod_detail.insert("end", "\n".join("- " + x for x in r["reasons"]) or "- no problems", tag)
        self.mod_detail["state"] = "disabled"

    def toggle(self):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.rows[sel[0]]
        if not r["id"]:
            return
        try:
            self.bundle.set_enabled(r["id"], not r["enabled"])
        except (bmmods.ModError, OSError) as e:
            messagebox.showerror(TITLE, str(e))
        self.refresh()

    def import_mod(self, path):
        if not path:
            return
        try:
            pv = self.bundle.preview(path)
        except bmmods.ModError as e:
            messagebox.showerror(TITLE, "Not imported: %s" % e)
            return
        msg = ("%s %s (%s)\n%s\n\n%d files, %.1f MB\nCompatibility: %s\n%s\n%s\nImport it into mods\\user?" % (
            pv["name"], pv["version"], pv["id"], pv["description"], pv["files"], pv["bytes"] / 1e6, pv["level"],
            "\n".join("- " + x for x in pv["reasons"]),
            "NATIVE CODE: it runs with your permissions. The game asks you to approve it; this launcher never does."
            if pv["native_code"] else ""))
        if not messagebox.askyesno(TITLE, msg):
            return
        try:
            dest = self.bundle.import_mod(path)
        except bmmods.ModError as e:
            if "already installed" in str(e) and messagebox.askyesno(TITLE, str(e) + "\n\nReplace it?"):
                try:
                    dest = self.bundle.import_mod(path, replace=True)
                except (bmmods.ModError, OSError) as e2:
                    messagebox.showerror(TITLE, "Not imported: %s" % e2)
                    return
            else:
                messagebox.showerror(TITLE, "Not imported: %s" % e)
                return
        self.status["text"] = "Imported to " + dest
        self.refresh()

    def show_stale(self):
        st = self.bundle.stale()
        messagebox.showinfo(TITLE, "\n".join("%s: %s - %s" % (x["file"], x["id"], x["why"]) for x in st)
                            or "The profile has no stale entries.")

    # ---------------- Play ----------------
    def _play_tab(self):
        f = ttk.Frame(self.nb, padding=(16, 12))
        self.nb.add(f, text="Play")
        card = ttk.Frame(f, style="Card.TFrame", padding=(16, 14))
        card.pack(fill="x")
        self.play_btn = ttk.Button(card, text="Play", underline=0, command=self.play, style="Play.Accent.TButton")
        self.play_btn.pack(side="left")
        self.bind("<Alt-p>", lambda e: self.play())
        side = ttk.Frame(card, style="Card.TFrame")
        side.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.play_hint = ttk.Label(side, text="", style="Card.TLabel", foreground=bmtheme.BAD)
        self.play_hint.pack(anchor="w")
        keep = ttk.Label(side, text="Your saves, settings, mod list and approvals stay in this folder (profile\\); your normal "
                                    "Burnout Mashup folders are not touched.", justify="left", style="CardMuted.TLabel")
        keep.pack(fill="x")
        keep.configure(wraplength=int(360 * self.scale))                # follows the space beside the Play button
        side.bind("<Configure>", lambda e: keep.configure(wraplength=max(150, e.width - 4)))
        head = ttk.Frame(f)
        head.pack(fill="x", pady=(14, 6))
        ttk.Label(head, text="Last game", style="Title.TLabel").pack(side="left")
        ttk.Button(head, text="Show last results", underline=5, command=self.show_results).pack(side="right")
        self.results = tk.Text(f, height=6, wrap="word", state="disabled")
        bmtheme.text_style(self.results, pad=12)
        self.results.pack(fill="both", expand=True)

    def play(self):
        if str(self.play_btn["state"]) == "disabled":
            return
        if getattr(self, "game", None) is not None and self.game.poll() is None:
            messagebox.showinfo(TITLE, "The game is already running.")
            return
        blocked = [r for r in self.bundle.mods() if r["enabled"] and r["level"] == bmcompat.BLOCKED]
        if blocked and not messagebox.askyesno(TITLE, "These mods will be refused by the game:\n%s\n\nPlay anyway?" %
                                               "\n".join("- " + (r["id"] or r["name"]) for r in blocked)):
            return
        self.status["text"] = "Game running... (results appear here after it ends)"
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        p = self.game = subprocess.Popen(["cmd", "/c", os.path.join(ROOT, "play.cmd")], cwd=ROOT, creationflags=flags)
        self.after(1000, lambda: self._wait_game(p))

    def _wait_game(self, p):
        if p.poll() is None:
            self.after(1000, lambda: self._wait_game(p))
            return
        self.status["text"] = "The game ended (exit status %s)." % p.returncode
        self.nb.select(2)
        self.show_results()

    def show_results(self):
        r = self.bundle.results()
        parts = []                                                       # (text, tag)
        if not r["found"]:
            parts.append(("No game log yet (it appears after the first game: profile\\Roaming\\BurnoutMashup\\logs\\run.log).",
                          "muted"))
        else:
            parts.append(("Mods loaded: %d   admitted: %s\n" % (r["mods_loaded"], r["admitted"]), "bold"))
            parts += [("  loaded %s\n" % x, "ok") for x in r["loaded"]]
            parts += [("REFUSED %s\n" % x, "bad") for x in r["refused"]]
            parts.append(("Plugins running: %s\n" % (", ".join(r["plugins_running"]) or "none"), ""))
            parts += [("NOT RUN %s\n" % x, "warn") for x in r["plugins_not_run"]]
            parts += [("FATAL %s\n" % x, "bad") for x in r["fatal"]] or [("No FATAL line.\n", "ok")]
            parts.append(("\nFull log: %s" % r["log"], "muted"))
        self.results["state"] = "normal"
        self.results.delete("1.0", "end")
        for text, tag in parts:
            self.results.insert("end", text, tag)
        self.results["state"] = "disabled"

    # ---------------- Help ----------------
    def _help_tab(self):
        f = ttk.Frame(self.nb, padding=(16, 12))
        self.nb.add(f, text="Help")
        ver = self.ver_lbl = ttk.Label(f, text=versions_line(), style="Muted.TLabel")
        ver.pack(fill="x", pady=(0, 8))
        self.wraps.append(ver)

        def card(title, note=""):
            c = ttk.Frame(f, style="Card.TFrame", padding=(14, 8))
            c.pack(fill="x", pady=(0, 6))
            ttk.Label(c, text=title, style="CardTitle.TLabel").pack(anchor="w")
            if note:
                n = ttk.Label(c, text=note, style="CardMuted.TLabel", justify="left")
                n.pack(fill="x")
                self.wraps.append(n)
            row = ttk.Frame(c, style="Card.TFrame")
            row.pack(fill="x", pady=(6, 0))
            return c, row
        _, row = card("Documents")
        for label, rel in (("Quickstart", "docs\\QUICKSTART.md"), ("Troubleshooting", "docs\\TROUBLESHOOTING.md"),
                           ("Known limitations", "docs\\KNOWN_LIMITATIONS.md"), ("Report a bug", "docs\\BUGS_AND_CONTRIBUTING.md")):
            ttk.Button(row, text=label, command=lambda rel=rel: _open(os.path.join(ROOT, rel))).pack(side="left", padx=(0, 6))
        _, row = card("Diagnostics and backup",
                      "Diagnostics: versions, file hashes and a redacted log; no game data, no saves, no mod contents.")
        ttk.Button(row, text="Export diagnostics (zip)...", command=self.export_diag).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Back up my profile...", command=self.backup).pack(side="left")
        c, row = card("Update / repair / remove")
        row.destroy()
        for text, cmd in (("Check for updates...", self.open_updates),
                          ("Bring my data from an older Burnout Mashup folder...", self.upgrade),
                          ("Verify the shipped files", lambda: self._run_in_setup("verify")),
                          ("Repair from a fresh copy of this version...", self.repair),
                          ("Remove re-creatable files (keeps saves and my mods)...", self.clean)):
            ttk.Button(c, text=text, command=cmd).pack(anchor="w", pady=(4, 0))

    def open_updates(self):
        """the Updates window (tools/launcher/bmupdate_gui.py): opening it contacts nothing; each step runs only when pressed there"""
        import bmupdate_gui
        return bmupdate_gui.open_window(self, launcher=ROOT, on_change=self.refresh)

    def _run_in_setup(self, name, extra=()):
        self.nb.select(0)
        self.run_step(name, list(extra))

    def upgrade(self):
        p = filedialog.askdirectory(title="Your OLDER Burnout Mashup folder (it is only read)")
        if p:
            self._run_in_setup("upgrade", [p])

    def repair(self):
        p = filedialog.askdirectory(title="A freshly unpacked copy of THIS version")
        if p:
            self._run_in_setup("repair", [p])

    def clean(self):
        if messagebox.askyesno(TITLE, "Delete the copy of your game data, the generated demos and work files from this folder?\n"
                                      "Your saves, settings and imported mods are kept. You can prepare everything again later."):
            self._run_in_setup("clean")

    def export_diag(self):
        p = filedialog.asksaveasfilename(title="Diagnostics zip", defaultextension=".zip", initialfile="bmashup-diag.zip")
        if p:
            self.nb.select(0)
            self.run_step("diag", [p])

    def backup(self):
        p = filedialog.askdirectory(title="Folder for the backup")
        if p:
            self.nb.select(0)
            self.run_step("backup", [p])

    def on_close(self):
        if self.step and self.step.running():
            if not messagebox.askyesno(TITLE, "A step is still running. Cancel it and close?"):
                return
            self.step.cancel()
        self.destroy()


def _open(path):
    if os.path.exists(path) and os.name == "nt":
        os.startfile(path)   # opens a document from the bundle's own docs folder


def _enable_drop(win, callback):
    """Files dropped on the window (Windows: WM_DROPFILES through ctypes). Best effort: without it, Browse and dropping onto
    'Burnout Mashup.cmd' still work."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        shell32, user32 = ctypes.windll.shell32, ctypes.windll.user32
        shell32.DragAcceptFiles(hwnd, True)
        GWLP_WNDPROC, WM_DROPFILES = -4, 0x0233
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallWindowProcW.restype = ctypes.c_ssize_t
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_wchar_p, wintypes.UINT]
        shell32.DragFinish.argtypes = [ctypes.c_void_p]

        def proc(h, msg, wp, lp):
            if msg == WM_DROPFILES:
                n = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                out = []
                for i in range(n):
                    buf = ctypes.create_unicode_buffer(32768)
                    shell32.DragQueryFileW(wp, i, buf, 32768)
                    out.append(buf.value)
                shell32.DragFinish(wp)
                win.after(10, lambda: callback(out))
                return 0
            return user32.CallWindowProcW(win._old_proc, h, msg, wp, lp)

        win._drop_proc = WNDPROC(proc)                     # kept alive with the window
        win._old_proc = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(win._drop_proc, ctypes.c_void_p))
    except Exception:
        pass


def startup_layout(root=ROOT):
    r"""rel020: in the Windows package (layout 2): work in the install folder (never inside app\, which an update renames), finish or
    undo an interrupted update, and move a Burnout Mashup 0.1.0-alpha.1 folder around app\ into the new layout (bmlayout.py:
    one transaction of renames, undone on any error; nothing is deleted). -> (title, text, error) for a message, or None"""
    inst = bmpaths.install_root(root)
    if not inst:
        return None
    try:
        os.chdir(inst)
    except OSError:
        pass
    import bmlayout
    r = bmlayout.startup(root)
    if r.get("error"):
        return ("Burnout Mashup - not moved", "The move of your older Burnout Mashup folder into the new layout did not happen:\n\n%s\n\n"
                "Nothing was lost; start Burnout Mashup.exe again to retry." % r["error"], True)
    m = r.get("migrated")
    if m:
        txt = ("Your Burnout Mashup %s folder now uses the new layout:\n\n  gamedata\\  your game copy and your mods (mods\\user, "
               "mods\\generated)\n  app\\  the program, with your saves, settings, plugin approvals and builds\n\n"
               "%d item(s) of your data were moved. The old program files are kept in app\\.update\\versions (report: %s)."
               % (m["from"], len(m["moved"]), m.get("report_file")))
        if m.get("changed_shipped"):
            txt += "\n\nFiles of the old version you had changed (kept there, not used): %s" % ", ".join(m["changed_shipped"][:8])
        if m.get("conflicts"):
            txt += "\n\nNot moved (the new version ships a file with that name; kept there): %s" % ", ".join(m["conflicts"][:8])
        return ("Burnout Mashup - moved to the new layout", txt, False)
    if r.get("recovered") == "rolledback":
        return ("Burnout Mashup", "An update was interrupted; it was undone. The version you used before is in use.", False)
    return None


def main(argv):
    dpi_aware()
    note = startup_layout()
    app = Launcher(dropped=[a for a in argv if os.path.exists(a)] or None)
    if note:
        app.after(300, lambda: (messagebox.showerror if note[2] else messagebox.showinfo)(note[0], note[1], parent=app))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
