"""wb_capture - window capture of ONE process, chosen by pid (Burnout Mashup Workbench v0.9, 2026-10-28).

v0.21 display scaling: the capture is taken in the window's OWN pixel space (coords(): a window that is not per-monitor aware
is captured at physical * window_dpi / monitor_dpi, read back with the thread in the window's awareness context; the JSON
reports 'dpi': awareness, both DPIs, scale, physical and own sizes). Before, a DPI-unaware window at 300 % gave a 3x bitmap
with its content in the top-left ninth. Never upscaled.

The technique of the existing gp\\modsmenu\\runtime\\tools\\winshot.ps1 (PrintWindow flag 3 = client area, full content, DPI
aware), but the window is found by the pid of the game a launch OWNS (EnumWindows + GetWindowThreadProcessId), never by image
name (winshot.ps1 selects `^burnout3_gp_main20m`, so it cannot see other hosts). Read only on the game. Writes one PNG.

    py -3 -B wb_capture.py PID OUT.png          -> one JSON line {ok, path, width, height, title, stats}
    py -3 -B wb_capture.py --png IN.bmp OUT.png -> a PNG copy of an uncompressed 24 / 32-bit BMP (e.g. the runner's fb_NNN.bmp)

stats (sampled every 4th pixel): mean luminance 0-255, the share of pixels brighter than 16, distinct colours (capped) - a
first "is anything drawn" check; they say nothing about WHAT is shown.
"""
import ctypes
import json
import os
import struct
import sys
import zlib
from ctypes import wintypes as wt


def png_bytes(w, h, rows):
    """rows: h byte strings of w*3 RGB bytes -> PNG file bytes"""
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b''.join(b'\0' + r for r in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def stats(w, h, rows):
    n = lit = 0
    tot = 0
    cols = set()
    for y in range(0, h, 4):
        r = rows[y]
        for x in range(0, w, 4):
            R, G, B = r[3 * x], r[3 * x + 1], r[3 * x + 2]
            lum = (299 * R + 587 * G + 114 * B) // 1000
            n += 1
            tot += lum
            lit += lum > 16
            if len(cols) < 4096:
                cols.add((R >> 3, G >> 3, B >> 3))
    return {'mean_luminance': round(tot / max(n, 1), 1), 'lit_share': round(lit / max(n, 1), 3), 'colours': len(cols),
            'sampled': n}


def read_bmp(path):
    b = open(path, 'rb').read()
    if b[:2] != b'BM':
        raise ValueError('not a BMP')
    off, = struct.unpack_from('<I', b, 10)
    w, h, _, bpp, comp = struct.unpack_from('<iiHHI', b, 18)
    if comp not in (0, 3) or bpp not in (24, 32):
        raise ValueError('unsupported BMP (%d bpp, compression %d)' % (bpp, comp))
    bp, top = bpp // 8, h < 0
    h = abs(h)
    stride = (w * bp + 3) & ~3
    rows = []
    for y in range(h):
        s = off + (y if top else h - 1 - y) * stride
        line = b[s:s + w * bp]
        rows.append(bytes(c for x in range(w) for c in (line[bp * x + 2], line[bp * x + 1], line[bp * x])))
    return w, h, rows


AWARENESS = {0: 'unaware', 1: 'system', 2: 'per-monitor'}


def coords(phys_w, phys_h, awareness, window_dpi, monitor_dpi):
    """explicit coordinate mapping (v0.21). This process is per-monitor aware, so GetClientRect gives PHYSICAL pixels. A window
    that is not per-monitor aware draws in its own (logical) pixel space at window_dpi and Windows stretches it by
    monitor_dpi / window_dpi; PrintWindow renders that own space. The capture is therefore taken at the window's own size:
    own = physical * window_dpi / monitor_dpi (identity for per-monitor aware windows or equal DPIs). Never upscaled."""
    if awareness == 2 or not window_dpi or not monitor_dpi or window_dpi == monitor_dpi:
        scale = 1.0
    else:
        scale = monitor_dpi / window_dpi
    return {'awareness': AWARENESS.get(awareness, 'unknown'), 'window_dpi': window_dpi, 'monitor_dpi': monitor_dpi,
            'scale': round(scale, 4), 'physical': [phys_w, phys_h],
            'own': [max(1, int(round(phys_w / scale))), max(1, int(round(phys_h / scale)))]}


def window_dpi_info(u, hw, pw, ph):
    """the window's awareness / DPI and its client size in its OWN coordinates (read with the thread switched to the window's
    awareness context) -> coords() + 'own_measured'. None when the API is missing (Windows before 10 1607)."""
    try:
        u.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
        u.GetWindowDpiAwarenessContext.argtypes = [wt.HWND]
        u.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        u.GetDpiForWindow.argtypes = [wt.HWND]
        u.MonitorFromWindow.restype, u.MonitorFromWindow.argtypes = wt.HMONITOR, [wt.HWND, wt.DWORD]
        ctx = u.GetWindowDpiAwarenessContext(hw)
        aw = u.GetAwarenessFromDpiAwarenessContext(ctx)
        wdpi = u.GetDpiForWindow(hw)
        x, y = wt.UINT(), wt.UINT()
        ctypes.windll.shcore.GetDpiForMonitor(u.MonitorFromWindow(hw, 2), 0, ctypes.byref(x), ctypes.byref(y))
        old = u.SetThreadDpiAwarenessContext(ctx)
        try:
            r = wt.RECT()
            u.GetClientRect(hw, ctypes.byref(r))
        finally:
            u.SetThreadDpiAwarenessContext(old)
    except (AttributeError, OSError):
        return None
    c = coords(pw, ph, aw, wdpi, x.value)
    c['own_measured'] = [r.right, r.bottom]
    return c


def capture(pid, out):
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))      # per-monitor v2: real client pixels
    except (AttributeError, OSError):
        u.SetProcessDPIAware()
    u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    u.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    u.GetDC.restype, u.GetDC.argtypes = wt.HDC, [wt.HWND]
    u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    u.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = wt.HDC, [wt.HDC]
    g.CreateCompatibleBitmap.restype, g.CreateCompatibleBitmap.argtypes = wt.HBITMAP, [wt.HDC, ctypes.c_int, ctypes.c_int]
    g.SelectObject.restype, g.SelectObject.argtypes = wt.HGDIOBJ, [wt.HDC, wt.HGDIOBJ]
    g.DeleteObject.argtypes, g.DeleteDC.argtypes = [wt.HGDIOBJ], [wt.HDC]
    g.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
    found = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hw, _):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(hw):
            r = wt.RECT()
            u.GetClientRect(hw, ctypes.byref(r))
            if r.right > 0 and r.bottom > 0:
                found.append((r.right * r.bottom, hw, r.right, r.bottom))
        return True
    u.EnumWindows(PROC(cb), 0)
    if not found:
        return {'ok': False, 'pid': pid, 'why': 'no visible window of pid %d (headless, not created yet, or minimised)' % pid}
    _, hw, pw, ph = max(found)
    dpi = window_dpi_info(u, hw, pw, ph)
    w, h = pw, ph
    if dpi is not None:
        w, h = dpi['own']
        # the window's own measurement is authoritative when it disagrees with the DPI ratio by more than rounding
        if all(v > 0 for v in dpi['own_measured']) and max(abs(a - b) for a, b in zip(dpi['own'], dpi['own_measured'])) > 1:
            w, h = dpi['own_measured']
    tl = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(hw, tl, 512)
    hdc = u.GetDC(hw)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    old = g.SelectObject(mdc, bmp)
    try:
        pw_ok = bool(u.PrintWindow(hw, mdc, 3))                   # PW_CLIENTONLY | PW_RENDERFULLCONTENT (winshot.ps1 "pw")

        class BIH(ctypes.Structure):
            _fields_ = [('biSize', wt.DWORD), ('biWidth', ctypes.c_long), ('biHeight', ctypes.c_long), ('biPlanes', wt.WORD),
                        ('biBitCount', wt.WORD), ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                        ('biXPelsPerMeter', ctypes.c_long), ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', wt.DWORD),
                        ('biClrImportant', wt.DWORD)]
        bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        got = g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    finally:
        g.SelectObject(mdc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(hw, hdc)
    raw = buf.raw
    rows = []
    for y in range(h):
        line = raw[y * w * 4:(y + 1) * w * 4]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::4], line[1::4], line[0::4]
        rows.append(bytes(rgb))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, 'wb').write(png_bytes(w, h, rows))
    return {'ok': pw_ok and got == h, 'pid': pid, 'path': os.path.abspath(out), 'width': w, 'height': h, 'title': tl.value,
            'printwindow': pw_ok, 'dpi': dpi, 'stats': stats(w, h, rows)}


def bmp_to_png(src, dst):
    w, h, rows = read_bmp(src)
    open(dst, 'wb').write(png_bytes(w, h, rows))
    return {'ok': True, 'path': os.path.abspath(dst), 'width': w, 'height': h, 'stats': stats(w, h, rows), 'source': src}


def main(argv):
    if len(argv) == 3 and argv[0] == '--png':
        r = bmp_to_png(argv[1], argv[2])
    elif len(argv) == 2 and argv[0].isdigit():
        r = capture(int(argv[0]), argv[1])
    else:
        print(__doc__)
        return 2
    print(json.dumps(r))
    return 0 if r.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
