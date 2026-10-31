"""shot_launcher.py - release readiness R1: screenshots of the launcher window for the docs ("what you should see") and for the
layout checks (minimum size, 200 % text scaling). Windows only; standard library (tkinter + ctypes PrintWindow).

    py -3 -B tests\\shot_launcher.py OUT_DIR

A temporary demo bundle (host stand-in + HOST_INFO.json, the shipped demo mods, a BLOCKED mod, a native-code mod, the
tutorial mod, a short game log) is shown; each tab is captured at 1000x720, the Mods tab also at the minimum 760x600 and with tk scaling
2.0. Writes OUT_DIR\\*.png + SHOTS.json (each file, size, whether the window content is wider than the window)."""
import ctypes
import json
import os
import shutil
import struct
import sys
import tempfile
import zlib
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402
SRC = pubfix.SRC
INFO = pubfix.INFO


def png(path, w, h, bgra, step=3):
    """1/3 resolution: the display here is scaled 300 %, so this is about what a 100 % screen shows"""
    rows = b"".join(b"\x00" + bytes(c for i in range(0, w, step) for c in (bgra[(y * w + i) * 4 + 2], bgra[(y * w + i) * 4 + 1],
                                                                           bgra[(y * w + i) * 4])) for y in range(0, h, step))
    w, h = len(range(0, w, step)), len(range(0, h, step))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def capture(hwnd, path, step=3):
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u.GetWindowDC(hwnd)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mdc, bmp)
    u.PrintWindow(hwnd, mdc, 2)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]
    bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)
    png(path, w, h, buf.raw, step)
    return w, h


def demo_bundle():
    root = os.path.join(tempfile.mkdtemp(prefix="bm shots "), "Burnout Mashup")
    for d in ("tools", "docs"):
        shutil.copytree(os.path.join(SRC, d), os.path.join(root, d))
    shutil.copytree(pubfix.DEMO, os.path.join(root, "mods", "demo"))
    open(os.path.join(root, "BUNDLE.json"), "w").write('{"bundle": "test"}')
    # a source checkout's first run (phase 14): game data chosen, NO host built yet (no stand-in exe: Play stays off until Build
    # Mashup has made and verified one), the PC check not run yet
    os.makedirs(os.path.join(root, "gamedata"))
    open(os.path.join(root, "gamedata", ".complete"), "w").write("xr-install 1\n")
    u = os.path.join(root, "mods", "user")
    for mid, extra, files in (("me.bigger-takedowns", '[bmashup]\nrequires = ["bmashup.tune>=1"]\n[bmashup.tune]\nversion = 1\n'
                               'set = ["Score/Burnout Points | Takedown BP = 2500"]\n', {}),
                              ("someone.future-mod", '[bmashup]\nplatform = ">=0.2.0"\n', {}),
                              ("someone.headlights", '[plugin]\napi = 1\nwindows = "h.asi"\n', {"h.asi": b"MZ"})):
        d = os.path.join(u, mid)
        os.makedirs(d)
        open(os.path.join(d, "mod.toml"), "w").write('id = "%s"\nname = "%s"\nversion = "1.0.0"\n%s' % (mid, mid, extra))
        for n, b in files.items():
            open(os.path.join(d, n), "wb").write(b)
    lg = os.path.join(root, "profile", "Roaming", pubfix.IDENT, "logs")
    os.makedirs(lg)
    open(os.path.join(lg, "run.log"), "w").write(
        "[ADMIT] mod someone.future-mod 1.0.0 (x) refused, the game starts without it: needs platform 0.2.0\n"
        "[ADMIT] 7 mods' [bmashup.*] declarations checked together before any is used (platform 0.1.9): 6 admitted, 1 refused\n"
        "[MOD] mod me.bigger-takedowns 1.0.0: x\n[MOD] mod bmashup.veh-neon 1.0.0: x\n"
        "[PLUGIN] someone.headlights: not run: not approved. It is native code and runs with your permissions\n")
    return root


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    root = demo_bundle()
    sys.path.insert(0, os.path.join(root, "tools", "launcher"))
    import bmgui
    bmgui.dpi_aware()
    bmgui.ROOT = root
    bmgui.bmops.ROOT = root
    app = bmgui.Launcher()
    app.bundle = bmgui.bmmods.Bundle(root)
    app.refresh()
    shown = r"C:\Games\burnout-mashup\launcher"              # docs never show this PC's user / temp paths (a source checkout's launcher)
    for r in app.rows.values():
        r["folder"] = r["folder"].replace(root, shown)
    app.status["text"] = "Bundle: " + shown
    app.bundle.log = os.path.join(root, "profile", "Roaming", pubfix.IDENT, "logs", "run.log")
    _results = app.bundle.results
    app.bundle.results = lambda log=None: dict(_results(log), log=os.path.join(shown, "profile", "Roaming", pubfix.IDENT, "logs",
                                                                                "run.log"))
    hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
    rec = []

    def snap(name):
        app.update()
        app.after(150)
        app.update()
        w, h = capture(hwnd, os.path.join(out, name + ".png"), max(1, int(round(app.scale))))
        req = app.winfo_reqwidth() > app.winfo_width() + 2 or app.winfo_reqheight() > app.winfo_height() + 2
        rec.append({"file": name + ".png", "size": [w, h], "content_larger_than_window": bool(req)})
    app.geometry("%dx%d" % (int(1000 * app.scale), int(720 * app.scale)))
    for i, n in enumerate(("1_setup", "2_mods", "3_play", "4_help")):
        app.nb.select(i)
        if n == "2_mods":
            first = app.tree.get_children()[0]
            for iid in app.tree.get_children():
                if app.rows[iid]["level"] == "BLOCKED":
                    first = iid
            app.tree.selection_set(first)
            app.show_mod()
        if n == "3_play":
            app.show_results()
        snap(n)
    app.nb.select(1)
    app.geometry("%dx%d" % (int(760 * app.scale), int(600 * app.scale)))
    snap("2_mods_min_760x600")
    rec.append({"display_scale": round(app.scale, 2), "note": "the launcher is DPI aware: this display's own scaling is the "
                "high-DPI case (100 % not available here)"})
    app.destroy()
    json.dump(rec, open(os.path.join(out, "SHOTS.json"), "w"), indent=1)
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
