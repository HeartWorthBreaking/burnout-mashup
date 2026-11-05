"""bmtheme.py - the Burnout Mashup look for tkinter windows (launcher and Workbench; Python standard library only).
The Workbench ships the same file as wb_theme.py (byte-identical; checked by the candidate test_launcher).

A very dark theme on ttk's "clam" engine after Burnout 3's menus: steel-tinted surfaces, a thin arc, the page's name top right, buttons and tabs as slanted
pale-blue words with a drop shadow and no box (MenuButton; white ticks around the selected tab); green / yellow / red only for states. Text: Roboto Condensed (launcher\\fonts, SIL OFL), else the system's. root.bm_art_dir (optional): a folder with logo_<height>.png: the band
shows that title (a rendered picture: no game art and no font file ships). Purely visual: no widget is added, removed or renamed.

    import bmtheme
    bmtheme.apply(root)          # before building widgets: ttk styles, fonts, tk option defaults
    ...build the window...
    bmtheme.finish(root)         # after building: plain tk widgets + hard-coded label colours, dark title bar, icon

Styles: Accent.TButton (main action), Card.TFrame / Card.TLabel / CardMuted.TLabel / CardTitle.TLabel (step cards),
Muted.TLabel, Title.TLabel, Header.TFrame / HeaderTitle.TLabel / HeaderSub.TLabel, Status.TLabel, Accent.TFrame (thin bar).
Colours: state_colour("ok" | "warn" | "bad" | "idle").
"""
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#05080e"        # window, status bar
PAGE = "#0a0f17"      # tab pages
CARD = "#101823"      # cards, lists, text areas
RAISED = "#16202d"    # fields and the like: barely off the surface
HOVER = "#1b2838"     # a button under the pointer
BORDER = "#1c2736"    # the faint outline
MENU = "#c4dcf5"      # a menu word (pale blue)
SHADOW = "#000000"
TEXT = "#e9edf3"
MUTED = "#98a3b1"
FAINT = "#667180"
ACCENT = "#2a6cb0"    # progress, thin lines
ACCENT_HOVER = "#3a80c8"
ACCENT_HI = "#8fc3f2"  # the main action's text, the selected tab
ACCENT_LO = "#1b3350"  # selection
BAND_TOP = "#16222f"  # the header band
BAND_LOW = "#05080e"
STRIPE = "#1b2a3d"
ARC = "#2f6fb0"
PAGE_NAME = "#7f9fbf"
ON_ACCENT = "#ffffff"
OK = "#5ad19a"
WARN = "#e8d27a"
BAD = "#f07f7f"

_STATE = {"ok": OK, "warn": WARN, "bad": BAD, "idle": MUTED}
# hard-coded label colours from before the theme (light background) -> readable ones on the dark theme
_REMAP = {"#555": MUTED, "#555555": MUTED, "#444": MUTED, "#444444": MUTED, "#333": MUTED, "#333333": MUTED, "#666": MUTED, "#666666": MUTED,
          "#777": MUTED, "#888": MUTED, "gray": MUTED, "grey": MUTED, "#1a5": OK, "#11aa55": OK, "#264": OK, "#226644": OK, "green": OK,
          "#060": OK, "#070": OK, "#080": OK, "darkgreen": OK, "#b00020": BAD, "#b00": BAD, "#c00": BAD, "red": BAD,
          "#a00": BAD, "darkred": BAD, "#8a5a00": WARN, "#a60": WARN, "#b60": WARN, "orange": WARN, "#c60": WARN,
          "blue": ACCENT_HI, "#00f": ACCENT_HI, "#06c": ACCENT_HI, "#0645ad": ACCENT_HI, "#a22": BAD, "#262": OK, "black": TEXT, "#000": TEXT}


def state_colour(state):
    return _STATE.get(state, MUTED)


_FONT_KEEP = []     # (handle, buffer) of the font in memory: kept for the life of the process, nothing on disk is held open


def _load_fonts():
    """Windows: the shipped font for this process only (nothing is installed). The file is read and CLOSED, and the bytes are handed to
    AddFontMemResourceEx (a private font of this process): no handle to anything under app\\launcher stays open, so Update now and
    Switch back can rename that folder while the launcher runs (AddFontResourceExW kept the file open: WinError 5). If it fails, the
    system's font is used, without an error. Elsewhere: the system's, by name."""
    if os.name != "nt" or _FONT_KEEP:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "..", "..", "fonts"), os.path.join(here, "..", "launcher", "fonts"), os.path.join(here, "..", "app", "launcher", "fonts")):
        p = os.path.normpath(os.path.join(d, "RobotoCondensed-Medium.ttf"))
        if os.path.isfile(p):
            try:
                import ctypes
                from ctypes import wintypes
                with open(p, "rb") as fh:
                    data = fh.read()
                buf = ctypes.create_string_buffer(data, len(data))
                gdi = ctypes.WinDLL("gdi32", use_last_error=True)       # own copy: ctypes.windll's argtypes stay untouched
                gdi.AddFontMemResourceEx.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
                gdi.AddFontMemResourceEx.restype = wintypes.HANDLE
                n = wintypes.DWORD(0)
                h = gdi.AddFontMemResourceEx(ctypes.cast(buf, ctypes.c_void_p), len(data), None, ctypes.byref(n))
                if h:
                    _FONT_KEEP.append((h, buf))
            except Exception:
                pass
            return


def _family(root, *names):
    have = set(tkfont.families(root))
    for n in names:
        if n in have:
            return n
        # a font loaded from memory (_load_fonts) is not in Tk's list of families, but Tk resolves it by name
        try:
            if tkfont.Font(root=root, family=n, size=10).actual("family").lower() == n.lower():
                return n
        except tk.TclError:
            pass
    return None


def apply(root, compact=False):
    """Styles, fonts and tk option defaults. Call once, before the widgets are built. compact=True: tighter padding and
    plain tab labels for dense tool windows (the Workbench); same colours."""
    root.compact = compact
    root.configure(background=BG)
    _load_fonts()
    ui = _family(root, "Roboto Condensed Medium", "Roboto Condensed", "Roboto", "Segoe UI", "Helvetica Neue", "DejaVu Sans")
    head = ui
    mono = _family(root, "Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkTooltipFont"):
        try:
            f = tkfont.nametofont(name, root=root)
        except tk.TclError:
            continue
        if ui:
            f.configure(family=ui)
        f.configure(size=10, weight="bold" if name == "TkHeadingFont" else "normal")
    if mono:
        tkfont.nametofont("TkFixedFont", root=root).configure(family=mono, size=9)
    base = tkfont.nametofont("TkDefaultFont", root=root).actual()
    fam = base["family"]
    root.fonts = {"title": (head or fam, 13 if compact else 20), "sub": (fam, 10), "h2": (head or fam, 11 if compact else 14),
                  "bold": (fam, 10 if compact else 11),
                  "tab": (head or fam, 10 if compact else 13, "italic"),
                  "btn": (head or fam, 10 if compact else 11, "italic"),
                  "cardtitle": (head or fam, 11 if compact else 13, "italic"),
                  "play": (head or fam, 12 if compact else 24, "italic"),
                  "page": (head or fam, 12 if compact else 24, "italic"),
                  "body": (fam, 11), "mono": "TkFixedFont"}

    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=PAGE, foreground=TEXT, fieldbackground=CARD, bordercolor=BORDER, lightcolor=PAGE,
                 darkcolor=PAGE, troughcolor=CARD, focuscolor=ACCENT, selectbackground=ACCENT_LO, selectforeground=TEXT,
                 insertcolor=TEXT, font="TkDefaultFont")
    st.map(".", foreground=[("disabled", FAINT)])
    st.configure("TFrame", background=PAGE)
    st.configure("TLabel", background=PAGE, foreground=TEXT)
    st.configure("Muted.TLabel", foreground=MUTED)
    st.configure("Title.TLabel", font=root.fonts["h2"])
    st.configure("Card.TFrame", background=CARD)
    st.configure("Card.TLabel", background=CARD, foreground=TEXT)
    st.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=root.fonts["h2"])
    st.configure("CardMuted.TLabel", background=CARD, foreground=MUTED)
    st.configure("Header.TFrame", background=BG)
    st.configure("HeaderTitle.TLabel", background=BG, foreground=TEXT, font=root.fonts["title"])
    st.configure("HeaderSub.TLabel", background=BG, foreground=MUTED, font=root.fonts["sub"])
    st.configure("Status.TLabel", background=BG, foreground=MUTED, font=root.fonts["sub"])
    st.configure("Accent.TFrame", background=ACCENT)
    st.configure("TLabelframe", background=PAGE, bordercolor=BORDER, lightcolor=PAGE, darkcolor=PAGE)
    st.configure("TLabelframe.Label", background=PAGE, foreground=MUTED, font=root.fonts["bold"])

    st.configure("TButton", background=RAISED, foreground=TEXT, bordercolor=BORDER, lightcolor=RAISED, darkcolor=RAISED,
                 focuscolor=RAISED, padding=(8, 2) if compact else (14, 6), relief="flat")
    st.map("TButton", background=[("disabled", CARD), ("pressed", BORDER), ("active", HOVER)],
           lightcolor=[("disabled", CARD), ("pressed", BORDER), ("active", HOVER)],
           darkcolor=[("disabled", CARD), ("pressed", BORDER), ("active", HOVER)],
           bordercolor=[("focus", ACCENT), ("disabled", BORDER)], foreground=[("disabled", FAINT)])
    st.configure("Accent.TButton", background=RAISED, foreground=ACCENT_HI, bordercolor=ACCENT_LO, lightcolor=RAISED,
                 darkcolor=RAISED, focuscolor=RAISED, padding=(10, 2) if compact else (18, 6))
    st.map("Accent.TButton", background=[("disabled", RAISED), ("pressed", BORDER), ("active", HOVER)],
           lightcolor=[("disabled", RAISED), ("active", HOVER)], darkcolor=[("disabled", RAISED), ("active", HOVER)],
           bordercolor=[("disabled", BORDER), ("focus", ACCENT), ("active", ACCENT)],
           foreground=[("disabled", FAINT)])

    for w in ("TCheckbutton", "TRadiobutton"):
        st.configure(w, background=PAGE, foreground=TEXT, indicatorbackground=CARD, indicatorforeground=ACCENT,
                     indicatormargin=4, focuscolor=PAGE)
        st.map(w, background=[("active", PAGE)], indicatorbackground=[("selected", CARD), ("pressed", RAISED)],
               foreground=[("disabled", FAINT)])
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=CARD, foreground=TEXT, bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD,
                     insertcolor=TEXT, arrowcolor=MUTED, background=RAISED, padding=1 if compact else 4)
        st.map(w, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", CARD)],
               fieldbackground=[("readonly", CARD), ("disabled", PAGE)], foreground=[("disabled", FAINT)])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_LO)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    ttk.Button = MenuButton                                  # every ttk.Button made from now on (the launcher, the Workbench)
    st.configure("Menu.TNotebook", background=PAGE, bordercolor=PAGE, lightcolor=PAGE, darkcolor=PAGE, tabmargins=0, padding=0)
    try:
        st.layout("Menu.TNotebook.Tab", [])                  # no tab strip of ttk's: menu_tabs draws its own
    except tk.TclError:
        pass
    if not hasattr(root, "scale"):
        root.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    if not getattr(root, "bm_art_dir", None):
        here = os.path.dirname(os.path.abspath(__file__))
        for d in (os.path.join(here, "..", "..", "art"), os.path.join(here, "..", "launcher", "art"), os.path.join(here, "..", "app", "launcher", "art")):
            if os.path.isdir(d):
                root.bm_art_dir = os.path.normpath(d)
                break
    st.configure("TNotebook", background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG, tabmargins=(6, 2, 6, 0) if compact else (12, 6, 12, 0))
    st.configure("TNotebook.Tab", background=BG, foreground=MUTED, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                 padding=(8, 3) if compact else (18, 8),
                 font=root.fonts["tab"])
    st.map("TNotebook.Tab", background=[("selected", PAGE), ("active", PAGE)],
           foreground=[("selected", ACCENT_HI), ("active", TEXT)], lightcolor=[("selected", PAGE)],
           bordercolor=[("selected", PAGE)], expand=[("selected", (0, 0, 0, 0))],
           padding=[("selected", (8, 3) if compact else (18, 8))])
    try:                                                     # flat tabs: no focus ring around the selected tab's text
        st.layout("TNotebook.Tab", [("Notebook.tab", {"sticky": "nswe", "children": [
            ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
                ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
    except tk.TclError:
        pass

    line = tkfont.nametofont("TkDefaultFont", root=root).metrics("linespace")
    st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, bordercolor=BORDER, lightcolor=CARD,
                 darkcolor=CARD, rowheight=int(line * 1.7))
    st.map("Treeview", background=[("selected", ACCENT_LO)], foreground=[("selected", TEXT)])
    st.configure("Treeview.Heading", background=BG, foreground=MUTED, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                 relief="flat", font=root.fonts["sub"], padding=(8, 6))
    st.map("Treeview.Heading", background=[("active", CARD)], foreground=[("active", TEXT)])

    st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=CARD, bordercolor=CARD, lightcolor=ACCENT,
                 darkcolor=ACCENT, thickness=max(6, line // 3))
    for o in ("Vertical", "Horizontal"):
        st.configure(o + ".TScrollbar", background=RAISED, troughcolor=PAGE, bordercolor=PAGE, lightcolor=RAISED,
                     darkcolor=RAISED, arrowcolor=MUTED, gripcount=0)
        st.map(o + ".TScrollbar", background=[("active", HOVER), ("pressed", HOVER)])
    st.configure("TSeparator", background=BORDER)
    st.configure("TPanedwindow", background=BG)
    st.configure("Sash", sashthickness=6, background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG)
    st.configure("TScale", background=RAISED, troughcolor=CARD, bordercolor=BORDER)

    # plain tk widgets created from now on
    for cls, opts in (("Text", dict(background=CARD, foreground=TEXT, insertBackground=TEXT, selectBackground=ACCENT_LO,
                                    selectForeground=TEXT, relief="flat", borderWidth=0, highlightThickness=0)),
                      ("Listbox", dict(background=CARD, foreground=TEXT, selectBackground=ACCENT_LO, selectForeground=TEXT,
                                       relief="flat", borderWidth=0, highlightThickness=0)),
                      ("Entry", dict(background=CARD, foreground=TEXT, insertBackground=TEXT, relief="flat")),
                      ("Menu", dict(background=CARD, foreground=TEXT, activeBackground=ACCENT_LO, activeForeground=TEXT)),
                      ("Toplevel", dict(background=BG)), ("Frame", dict(background=PAGE)),
                      ("Label", dict(background=PAGE, foreground=TEXT))):
        for k, v in opts.items():
            root.option_add("*%s.%s" % (cls, k), v)
    return st


def finish(root):
    """After the widgets exist: recolour plain tk widgets made with explicit colours and ttk labels that carry a colour
    meant for a light background; dark title bar and window icon (best effort)."""
    _walk(root)
    dark_titlebar(root)
    set_icon(root)


def _walk(w):
    for c in w.winfo_children():
        try:
            if isinstance(c, ttk.Label):
                fg = str(c.cget("foreground") or "").lower()
                if fg in _REMAP:
                    c.configure(foreground=_REMAP[fg])
            elif isinstance(c, (tk.Text, tk.Listbox)):
                c.configure(background=CARD, foreground=TEXT, selectbackground=ACCENT_LO, selectforeground=TEXT,
                            relief="flat", borderwidth=0, highlightthickness=0)
                if isinstance(c, tk.Text):
                    c.configure(insertbackground=TEXT)
            elif isinstance(c, tk.Label):
                fg = str(c.cget("foreground") or "").lower()
                c.configure(background=PAGE, foreground=_REMAP.get(fg, TEXT))
            elif isinstance(c, tk.Frame) and not isinstance(c, ttk.Frame):
                c.configure(background=PAGE)
        except tk.TclError:
            pass
        _walk(c)


def text_style(widget, mono=False, pad=10):
    """A themed read-only text area (log, details, results)."""
    root = widget.winfo_toplevel()
    widget.configure(background=CARD, foreground=TEXT, relief="flat", borderwidth=0, highlightthickness=0, padx=pad, pady=pad,
                     font="TkFixedFont" if mono else root.fonts["body"], selectbackground=ACCENT_LO, insertbackground=TEXT,
                     spacing1=1, spacing3=1)
    for tag, col in (("ok", OK), ("warn", WARN), ("bad", BAD), ("muted", MUTED), ("accent", ACCENT_HI)):
        widget.tag_configure(tag, foreground=col)
    widget.tag_configure("bold", font=root.fonts["bold"])


def dark_titlebar(root):
    """Windows 10 2004+ / 11: dark caption (and the theme's colour on 11). Ignored elsewhere."""
    if os.name != "nt":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        on = ctypes.c_int(1)
        for attr in (20, 19):                      # DWMWA_USE_IMMERSIVE_DARK_MODE (new id, old id)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        rgb = int(BG[1:3], 16) | int(BG[3:5], 16) << 8 | int(BG[5:7], 16) << 16
        col = ctypes.c_int(rgb)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(col), ctypes.sizeof(col))   # DWMWA_CAPTION_COLOR
    except Exception:
        pass


def _icon_image(root, n=32):
    """A small drawn mark: a blue rounded tile with two white speed chevrons (no image file needed)."""
    img = tk.PhotoImage(master=root, width=n, height=n)
    r = n * 0.22
    rows = []
    for y in range(n):
        row = []
        for x in range(n):
            cx, cy = min(max(x, r), n - 1 - r), min(max(y, r), n - 1 - r)
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            if not inside:
                row.append(BG)
                continue
            u, v = x / n, abs(y / n - 0.5)
            chev = any(0 <= (u - off - v) <= 0.13 for off in (0.20, 0.45)) and v < 0.30
            row.append(ON_ACCENT if chev else ACCENT)
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    return img


def set_icon(root):
    try:
        d = getattr(root, "bm_art_dir", None)
        if d and os.path.isfile(os.path.join(d, "icon_32.png")):
            root._bm_icons = [tk.PhotoImage(master=root, file=os.path.join(d, "icon_%d.png" % n)) for n in (48, 32, 16)]
        else:
            root._bm_icons = [_icon_image(root, 32), _icon_image(root, 16)]
        root.iconphoto(True, *root._bm_icons)
    except tk.TclError:
        pass


def _surface(w):
    """the colour behind a widget"""
    try:
        if isinstance(w, ttk.Widget):
            return ttk.Style(w).lookup(str(w.cget("style")) or w.winfo_class(), "background") or PAGE
        return str(w.cget("background"))
    except tk.TclError:
        return PAGE


class MenuButton(tk.Canvas):
    """A button as the game's menu has them: a slanted word with a drop shadow, no box; a soft lit bar under the pointer, ticks when selected. Same use as
    ttk.Button (text, command, state, style, invoke, instate, ["state"]); a tk.Canvas because ttk cannot draw a shadow behind its text."""
    _own = ("text", "command", "state", "style", "underline")

    def __init__(self, parent, text="", command=None, state="normal", style="TButton", underline=-1, width=None, kind=None, **kw):
        kw.pop("padding", None)
        kw.pop("compound", None)
        kw.pop("image", None)
        root = parent.winfo_toplevel()
        while root is not None and not hasattr(root, "fonts"):
            root = getattr(root, "master", None)
        self._fonts = root.fonts if root is not None else {}
        self._scale = getattr(root, "scale", 1.0) if root is not None else 1.0
        self._bg = _surface(parent)
        super().__init__(parent, background=self._bg, highlightthickness=0, borderwidth=0, takefocus=kind != "title", **kw)
        self._o = {"text": text, "command": command, "state": str(state), "style": style, "underline": underline}
        self._kind, self._over, self._down, self._sel = kind, False, False, False
        self._min = width
        if kind != "title":
            self.bind("<Enter>", lambda e: self._set(over=True))
            self.bind("<Leave>", lambda e: self._set(over=False, down=False))
            self.bind("<ButtonPress-1>", lambda e: self._set(down=True))
            self.bind("<ButtonRelease-1>", self._release)
            self.bind("<Return>", lambda e: self.invoke())
            self.bind("<space>", lambda e: self.invoke())
            self.bind("<FocusIn>", lambda e: self._draw())
            self.bind("<FocusOut>", lambda e: self._draw())
        self.bind("<Configure>", lambda e: self._draw())
        self._size()

    def _font(self):
        st = str(self._o["style"])
        k = "tab" if self._kind == "tab" else "cardtitle" if self._kind == "title" else "play" if "Play" in st else "btn"
        return self._fonts.get(k, "TkDefaultFont")

    def _shown(self):
        t = str(self._o["text"])
        return t.upper() if self._kind in ("tab", "title") or "Play" in str(self._o["style"]) else t

    def _size(self):
        s = self._scale
        f = tkfont.Font(root=self, font=self._font())
        tw, lh = f.measure(self._shown()), f.metrics("linespace")
        compact = getattr(self.winfo_toplevel(), "compact", False)
        pad = 0 if self._kind == "title" else int((14 if compact else 22) * s) if self._kind == "tab" else int((7 if compact else 12) * s)
        w = tw + 2 * pad + int(5 * s)
        if self._min and isinstance(self._min, int):
            w = max(w, self._min * f.measure("0"))
        tk.Canvas.configure(self, width=w, height=lh + int((2 if self._kind == "title" else 4) * s))
        self._draw()

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        s, off = self._scale, self._o["state"] == "disabled"
        w, h = max(self.winfo_width(), int(self.cget("width"))), max(self.winfo_height(), int(self.cget("height")))
        if self._over and not off and self._kind != "title":
            self.create_rectangle(0, 0, w, h, fill=HOVER, outline="")
        st = str(self._o["style"])
        col = FAINT if off else TEXT if self._sel or self._kind == "title" or self._down else "#ffffff" if self._over else ACCENT_HI if st.startswith(("Accent", "Play")) else MENU
        if self._kind == "tab" and not self._sel and not self._over:
            col = PAGE_NAME
        x, y, f = (0 if self._kind == "title" else w // 2), h // 2, self._font()
        anc = "w" if self._kind == "title" else "center"
        if not off:
            d = max(1, int(1.5 * s))
            self.create_text(x + d, y + d, text=self._shown(), anchor=anc, font=f, fill=SHADOW)
        self.create_text(x, y, text=self._shown(), anchor=anc, font=f, fill=col)
        if self._sel:
            # the menu's ticks: a short bar and a line out from it, each side
            t, a, b = max(1, int(2 * s)), int(6 * s), int(4 * s)
            self.create_line(a, y - b, a, y + b, fill="#ffffff", width=t)
            self.create_line(0, y, a, y, fill="#ffffff", width=t)
            self.create_line(w - a, y - b, w - a, y + b, fill="#ffffff", width=t)
            self.create_line(w - a, y, w, y, fill="#ffffff", width=t)
        elif self.focus_displayof() is self and not off and self._kind != "title":
            self.create_line(int(4 * s), h - 1, w - int(4 * s), h - 1, fill=ARC)

    def _set(self, over=None, down=None):
        if over is not None:
            self._over = over
        if down is not None:
            self._down = down
        self._draw()

    def _release(self, e):
        hit = self._down and 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        self._set(down=False)
        if hit:
            self.invoke()

    def select(self, on):
        self._sel = bool(on)
        self._draw()

    def invoke(self):
        if self._o["state"] != "disabled" and self._o["command"]:
            return self._o["command"]()

    def instate(self, spec):
        off = self._o["state"] == "disabled"
        return all((("disabled" == x and off) or ("!disabled" == x and not off)) for x in spec)

    def cget(self, key):
        if key in self._own:
            return self._o[key]
        return super().cget(key)

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        again = False
        for k in self._own:
            if k in kw:
                v = kw.pop(k)
                self._o[k] = str(v) if k == "state" else v
                again = True
        for k in ("padding", "compound", "image"):
            kw.pop(k, None)
        if kw:
            super().configure(**kw)
        if again and getattr(self, "_o", None):
            self._size()

    config = configure

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})


def menu_tabs(root, nb, tabs, on_change=None):
    """The menu's tab row above a Menu.TNotebook: tabs [(page's name)]; ticks on the selected one; nb stays the owner of the pages and of the selection"""
    row = ttk.Frame(root, style="Header.TFrame", padding=(int(10 * getattr(root, "scale", 1.0)), int(2 * getattr(root, "scale", 1.0))))
    btns = []
    gap = int(4 * getattr(root, "scale", 1.0))
    for i, t in enumerate(tabs):
        btns.append(MenuButton(row, text=t, kind="tab", command=lambda i=i: nb.select(i)))
    shown = [None]

    def flow(e=None):
        """as many on a row as the window has room for: a narrow window takes a second row"""
        room = max(row.winfo_width() - 2 * int(10 * getattr(root, "scale", 1.0)), 1)
        place, r, c, used = [], 0, 0, 0
        for b in btns:
            w = int(b.cget("width")) + gap
            if c and used + w > room:
                r, c, used = r + 1, 0, 0
            place.append((r, c))
            c, used = c + 1, used + w
        if place != shown[0]:
            shown[0] = place
            for b in btns:
                b.grid_forget()
            for b, (r, c) in zip(btns, place):
                b.grid(row=r, column=c, padx=(0, gap), sticky="w")
    row.bind("<Configure>", flow, add="+")
    for i, b in enumerate(btns):
        b.grid(row=0, column=i, padx=(0, gap), sticky="w")

    def changed(e=None):
        cur = nb.index("current")
        for i, b in enumerate(btns):
            b.select(i == cur)
        if on_change:
            on_change(tabs[cur])
    nb.bind("<<NotebookTabChanged>>", changed, add="+")
    changed()
    return row


def menu_title(parent, text, **kw):
    """A heading in the menu's words: slanted capitals with a drop shadow"""
    return MenuButton(parent, text=text, kind="title", **kw)


def _mix(a, b, t):
    return "#%02x%02x%02x" % tuple(int(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t) for i in (1, 3, 5))


def _art_image(c, kind, target):
    """the largest kept height of this picture that fits the target, or None (no art made, or a file Tk cannot read)"""
    d = getattr(c.winfo_toplevel(), "bm_art_dir", None)
    if not d or not os.path.isdir(d):
        return None
    sizes = []
    for n in os.listdir(d):
        if n.startswith(kind + "_") and n.endswith(".png") and n[len(kind) + 1:-4].isdigit():
            sizes.append(int(n[len(kind) + 1:-4]))
    fit = [z for z in sizes if z <= target]
    if not fit:
        return None
    key = (kind, max(fit))
    cache = c.__dict__.setdefault("_art", {})
    if key not in cache:
        try:
            cache[key] = tk.PhotoImage(master=c, file=os.path.join(d, "%s_%d.png" % key))
        except tk.TclError:
            cache[key] = None
    return cache[key]


def _band(c, title, subtitle, sc):
    """The header band, drawn for its width: a dark fade, the logo or the title, a hairline."""
    c.delete("all")
    w, h = max(c.winfo_width(), 2), int(c.cget("height"))
    for y in range(h):
        c.create_line(0, y, w, y, fill=_mix(BAND_TOP, BAND_LOW, y / max(h - 1, 1)))
    s = sc * 1.0
    f = c.winfo_toplevel().fonts
    c.create_line(0, h * 0.86, w * 0.16, h * 0.30, w * 0.34, h * 0.06, w * 0.62, -h * 0.20, smooth=True, width=max(1, int(2 * s)), fill=ARC)
    x, y = int(18 * s), int(h * 0.46)
    logo = _art_image(c, "logo", int(h * 0.94))
    if logo:
        c.create_image(x, y, image=logo, anchor="w")
        right = x + logo.width() + int(10 * s)
        word = _art_image(c, "word", int(h * 0.42))
        if word:
            c.create_image(right, y + int(h * 0.04), image=word, anchor="w")
            right += word.width()
    else:
        t = c.create_text(x, y, text=title.upper(), anchor="w", font=f["title"], fill=TEXT)
        right = c.bbox(t)[2]
    if subtitle:
        c.create_text(right + int(14 * s), y + int(4 * s), text=subtitle, anchor="w", font=f["sub"], fill=MUTED)
    page = getattr(c, "page", "")
    if page:
        px, py = w - int(26 * s), int(h * 0.46)
        c.create_text(px + int(2 * s), py + int(2 * s), text=page.upper(), anchor="e", font=f["page"], fill=SHADOW)
        c.create_text(px, py, text=page.upper(), anchor="e", font=f["page"], fill=PAGE_NAME)
    c.create_rectangle(0, h - max(1, int(1 * s)), w, h, fill=STRIPE, outline="")


def header(parent, title, subtitle=""):
    """The top bar: the band with the title; shallower in a dense tool window (compact)."""
    root = parent.winfo_toplevel()
    sc = getattr(root, "scale", 1.0)
    c = tk.Canvas(parent, height=int((64 if getattr(root, "compact", False) else 84) * sc), highlightthickness=0, borderwidth=0, background=BG)
    c.redraw = lambda: _band(c, title, subtitle, sc)
    c.bind("<Configure>", lambda e: c.redraw())
    return c
