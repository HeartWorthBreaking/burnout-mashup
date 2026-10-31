"""test_resolutions.py - release readiness R1 stage 4: the launcher at common displays (owner 2026-10-30: "1080p and 1440p").

    py -3 -B tests\\test_resolutions.py OUT_DIR

Simulated displays (the launcher's dpi / screen arguments; this PC's own panel is 4K at 300 %, so each window is drawn at its
real pixel size): 1920x1080 and 2560x1440 at 100 / 125 / 150 % (96 / 120 / 144 dpi). Per display: the window must fit the
screen's work area (<= 92 % x 85 %), every tab's content must fit the default window and the MINIMUM window (requested size
<= actual size, i.e. nothing cut off), the mod list rows must be at least the font's line height; screenshots of the Setup
and Mods tabs at the default size and Mods at the minimum size (OUT_DIR\\<display>_*.png). OUT_DIR\\RESOLUTIONS.json; exit 0 = all fit.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shot_launcher as sl  # noqa: E402

DISPLAYS = [(1920, 1080, 96), (1920, 1080, 120), (1920, 1080, 144), (2560, 1440, 96), (2560, 1440, 120), (2560, 1440, 144)]


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def fits(app):
    """per tab: every button / label / list / progress bar is shown and lies wholly inside the tab; every text pane keeps at
    least 2 lines; lists keep at least 3 rows. -> {tab: {'fits', 'cut': [widget texts cut off]}}"""
    from tkinter import font as tkfont, ttk
    import tkinter as tk
    line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
    app.update_idletasks()
    app.update()
    out = {}
    for i in range(len(app.nb.tabs())):
        app.nb.select(i)
        app.update()
        tab = app.nametowidget(app.nb.tabs()[i])
        tx, ty, tw, th = tab.winfo_rootx(), tab.winfo_rooty(), tab.winfo_width(), tab.winfo_height()
        cut = []
        for w in _walk(tab):
            if not isinstance(w, (ttk.Button, ttk.Label, ttk.Treeview, ttk.Progressbar, tk.Text)):
                continue
            name = w.cget("text") if isinstance(w, (ttk.Button, ttk.Label)) else w.winfo_class()
            if not w.winfo_ismapped():
                cut.append("not shown: %s" % str(name)[:40])
                continue
            x, y, ww, wh = w.winfo_rootx() - tx, w.winfo_rooty() - ty, w.winfo_width(), w.winfo_height()
            if x < 0 or y < 0 or x + ww > tw + 1 or y + wh > th + 1:
                cut.append("outside: %s (%d,%d %dx%d in %dx%d)" % (str(name)[:40], x, y, ww, wh, tw, th))
            if isinstance(w, tk.Text) and wh < 2 * line:
                cut.append("text pane under 2 lines")
            if isinstance(w, ttk.Treeview) and wh < 4 * line:
                cut.append("list under 3 rows")
        out[app.nb.tab(i, "text")] = {"fits": not cut, "cut": cut[:6]}
    return out


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    if "--one" not in sys.argv:                  # one process per display: Tk / font state never leaks between them
        import subprocess
        res, ok = [], True
        for sw, sh, dpi in DISPLAYS:
            p = subprocess.run([sys.executable, "-B", os.path.abspath(__file__), out, "--one", "%d,%d,%d" % (sw, sh, dpi)],
                               capture_output=True, text=True, timeout=300)
            print(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr[-300:])
            one = os.path.join(out, "one_%d_%d_%d.json" % (sw, sh, dpi))
            r = json.load(open(one)) if os.path.isfile(one) else [{"display": "%dx%d_%d" % (sw, sh, dpi), "ok": False}]
            res += r
            ok &= all(x["ok"] for x in r)
        json.dump(res, open(os.path.join(out, "RESOLUTIONS.json"), "w"), indent=1)
        return 0 if ok else 1
    displays = [tuple(int(x) for x in sys.argv[sys.argv.index("--one") + 1].split(","))]
    root = sl.demo_bundle()
    sys.path.insert(0, os.path.join(root, "tools", "launcher"))
    import bmgui
    from tkinter import font as tkfont
    bmgui.dpi_aware()
    bmgui.ROOT = root
    bmgui.bmops.ROOT = root
    res, ok = [], True
    for sw, sh, dpi in (DISPLAYS if "--one" not in sys.argv else displays):
        name = "%dx%d_%d" % (sw, sh, round(dpi / 96 * 100))
        app = bmgui.Launcher(dpi=dpi, screen=(sw, sh))
        app.bundle = bmgui.bmmods.Bundle(root)
        app.refresh()
        hwnd = sl.ctypes.windll.user32.GetParent(app.winfo_id())
        app.update()
        r = {"display": name, "window": [app.winfo_width(), app.winfo_height()],
             "window_fits_screen": app.winfo_width() <= sw * 0.92 + 1 and app.winfo_height() <= sh * 0.85 + 1}
        line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        r["row_height_ok"] = int(str(bmgui.ttk.Style(app).lookup("Treeview", "rowheight") or 0)) >= line
        r["default"] = fits(app)
        for tab, fn in ((0, "setup"), (1, "mods")):
            app.nb.select(tab)
            app.update()
            sl.capture(hwnd, os.path.join(out, "%s_%s.png" % (name, fn)), step=1) if "step" in sl.capture.__code__.co_varnames \
                else sl.capture(hwnd, os.path.join(out, "%s_%s.png" % (name, fn)))
        mw, mh = app.minsize()
        app.geometry("%dx%d" % (mw, mh))
        app.update()
        r["minimum"] = fits(app)
        r["minimum_size"] = [mw, mh]
        app.nb.select(1)
        app.update()
        sl.capture(hwnd, os.path.join(out, "%s_mods_min.png" % name), step=1)
        app.destroy()
        r["ok"] = r["window_fits_screen"] and r["row_height_ok"] and all(v["fits"] for v in r["default"].values()) and \
            all(v["fits"] for v in r["minimum"].values())
        ok &= r["ok"]
        res.append(r)
        print(name, "OK" if r["ok"] else "PROBLEM", r["window"], {k: v["fits"] for k, v in r["minimum"].items()})
    json.dump(res, open(os.path.join(out, "one_%d_%d_%d.json" % displays[0]), "w"), indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
