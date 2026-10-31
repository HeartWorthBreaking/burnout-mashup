"""bmtheme.py - the Burnout Mashup look for tkinter windows (launcher and Workbench; Python standard library only).
The Workbench ships the same file as wb_theme.py (byte-identical; checked by the candidate test_launcher).

A dark, flat theme on ttk's "clam" engine: navy surfaces, one electric-blue accent for the main action, green / amber / red only
for states. Purely visual: no widget is added, removed or renamed.

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

BG = "#0b0f17"        # window, header, status bar, unselected tabs (deep navy)
PAGE = "#111826"      # tab pages
CARD = "#182133"      # cards, lists, text areas
RAISED = "#212d44"    # buttons
HOVER = "#2b3a57"
BORDER = "#26324a"
TEXT = "#e8eef8"
MUTED = "#93a1b8"
FAINT = "#5b6880"
ACCENT = "#1a6bdf"    # electric blue (inspired by Burnout 3's menus; not a copy)
ACCENT_HOVER = "#3486f5"
ACCENT_HI = "#5aa9ff"  # accent as text on dark surfaces
ACCENT_LO = "#173a6b"  # selection
ON_ACCENT = "#ffffff"
OK = "#46d68c"
WARN = "#ffb84d"
BAD = "#ff6b6b"

_STATE = {"ok": OK, "warn": WARN, "bad": BAD, "idle": MUTED}
# hard-coded label colours from before the theme (light background) -> readable ones on the dark theme
_REMAP = {"#555": MUTED, "#555555": MUTED, "#444": MUTED, "#444444": MUTED, "#333": MUTED, "#333333": MUTED, "#666": MUTED, "#666666": MUTED,
          "#777": MUTED, "#888": MUTED, "gray": MUTED, "grey": MUTED, "#1a5": OK, "#11aa55": OK, "#264": OK, "#226644": OK, "green": OK,
          "#060": OK, "#070": OK, "#080": OK, "darkgreen": OK, "#b00020": BAD, "#b00": BAD, "#c00": BAD, "red": BAD,
          "#a00": BAD, "darkred": BAD, "#8a5a00": WARN, "#a60": WARN, "#b60": WARN, "orange": WARN, "#c60": WARN,
          "blue": ACCENT_HI, "#00f": ACCENT_HI, "#06c": ACCENT_HI, "#0645ad": ACCENT_HI, "#a22": BAD, "#262": OK, "black": TEXT, "#000": TEXT}


def state_colour(state):
    return _STATE.get(state, MUTED)


def _family(root, *names):
    have = set(tkfont.families(root))
    for n in names:
        if n in have:
            return n
    return None


def apply(root, compact=False):
    """Styles, fonts and tk option defaults. Call once, before the widgets are built. compact=True: tighter padding and
    plain tab labels for dense tool windows (the Workbench); same colours."""
    root.compact = compact
    root.configure(background=BG)
    ui = _family(root, "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "DejaVu Sans")
    mono = _family(root, "Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkTooltipFont"):
        try:
            f = tkfont.nametofont(name, root=root)
        except tk.TclError:
            continue
        if ui:
            f.configure(family=ui)
        f.configure(size=9 if compact else 10, weight="bold" if name == "TkHeadingFont" else "normal")
    if mono:
        tkfont.nametofont("TkFixedFont", root=root).configure(family=mono, size=9)
    base = tkfont.nametofont("TkDefaultFont", root=root).actual()
    fam = base["family"]
    root.fonts = {"title": (fam, 12 if compact else 15, "bold"), "sub": (fam, 9), "h2": (fam, 10 if compact else 11, "bold"),
                  "bold": (fam, 9 if compact else 10, "bold"),
                  "body": (fam, 10), "mono": "TkFixedFont"}

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
    st.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT, bordercolor=ACCENT, lightcolor=ACCENT,
                 darkcolor=ACCENT, focuscolor=ACCENT, font=root.fonts["bold"], padding=(10, 2) if compact else (18, 7))
    st.map("Accent.TButton", background=[("disabled", RAISED), ("pressed", ACCENT), ("active", ACCENT_HOVER)],
           lightcolor=[("disabled", RAISED), ("active", ACCENT_HOVER)], darkcolor=[("disabled", RAISED), ("active", ACCENT_HOVER)],
           bordercolor=[("disabled", BORDER), ("focus", ACCENT_HI), ("active", ACCENT_HOVER)],
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

    st.configure("TNotebook", background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG, tabmargins=(6, 2, 6, 0) if compact else (12, 6, 12, 0))
    st.configure("TNotebook.Tab", background=BG, foreground=MUTED, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                 padding=(8, 3) if compact else (18, 8),
                 font="TkDefaultFont" if compact else root.fonts["bold"])
    st.map("TNotebook.Tab", background=[("selected", PAGE), ("active", CARD)],
           foreground=[("selected", ACCENT_HI), ("active", TEXT)], lightcolor=[("selected", PAGE)],
           bordercolor=[("selected", PAGE)], expand=[("selected", (0, 0, 0, 0))])
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
        root._bm_icons = [_icon_image(root, 32), _icon_image(root, 16)]
        root.iconphoto(True, *root._bm_icons)
    except tk.TclError:
        pass


def header(parent, title, subtitle=""):
    """The top bar: title, subtitle, a thin accent line."""
    h = ttk.Frame(parent, style="Header.TFrame",
                  padding=(12, 6, 12, 2) if getattr(parent.winfo_toplevel(), "compact", False) else (18, 10, 18, 6))
    ttk.Frame(h, style="Accent.TFrame", width=5).pack(side="left", fill="y", padx=(0, 10))
    ttk.Label(h, text=title.upper(), style="HeaderTitle.TLabel").pack(side="left")
    if subtitle:
        ttk.Label(h, text=subtitle, style="HeaderSub.TLabel").pack(side="left", padx=(12, 0), pady=(5, 0))
    return h
