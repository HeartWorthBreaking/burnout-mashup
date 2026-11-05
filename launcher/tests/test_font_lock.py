"""test_font_lock.py - the launcher must not hold a file under app\\launcher open (alpha.4: bmtheme._load_fonts used AddFontResourceExW, which keeps the font file open for the life of
the process, so Update now / Switch back failed with WinError 5 when they renamed app\\launcher). A real, withdrawn Tk root in THIS process:
  family     with the theme applied the theme resolves 'Roboto Condensed Medium' and Tk renders it (a font in memory is not in families(); that is reported, not required)
  rename     a copy of the launcher folder (tools\\launcher\\bmtheme.py + fonts\\) whose theme was loaded and applied in this process can be renamed and renamed back,
             and so can its fonts folder and the font file itself, while the process lives
  fallback   if the in-memory load raises, _load_fonts returns without an error (the system font is used)
    py -3 -B test_font_lock.py                       the launcher's own bmtheme (beside tests\\)
    py -3 -B test_font_lock.py --expect-lock FILE    the same with FILE as bmtheme.py (alpha.4's): the MUTANT, passes only if the rename FAILS (exit 0 = the test can tell)
Windows only (elsewhere: skipped, exit 0). Work folder beside this file (never %TEMP%), removed at the end."""
import importlib.util
import os
import shutil
import sys
import tkinter as tk
import traceback
from tkinter import font as tkfont

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.dirname(HERE)
WORK = os.path.join(HERE, "work_font_lock")
FONT = "RobotoCondensed-Medium.ttf"


def main():
    if os.name != "nt":
        print("test_font_lock: skipped (Windows only)")
        return 0
    a = sys.argv[1:]
    mutant = a[a.index("--expect-lock") + 1] if "--expect-lock" in a else None
    bm_src = os.path.abspath(mutant) if mutant else os.path.join(LAUNCHER, "tools", "launcher", "bmtheme.py")
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    lay = os.path.join(WORK, "launcher")
    os.makedirs(os.path.join(lay, "tools", "launcher"))
    os.makedirs(os.path.join(lay, "fonts"))
    shutil.copyfile(bm_src, os.path.join(lay, "tools", "launcher", "bmtheme.py"))
    shutil.copyfile(os.path.join(LAUNCHER, "fonts", FONT), os.path.join(lay, "fonts", FONT))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("bmtheme_under_test", os.path.join(lay, "tools", "launcher", "bmtheme.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    res, failed = {}, []
    root = tk.Tk()
    root.withdraw()
    try:
        bt.apply(root)
        root.update()
        res["the theme resolves the family"] = bt._family(root, "Roboto Condensed Medium") == "Roboto Condensed Medium"
        res["Tk renders it (actual family)"] = tkfont.Font(root=root, family="Roboto Condensed Medium", size=12).actual("family") == "Roboto Condensed Medium"
        res["info: in Tk's families() list"] = "Roboto Condensed Medium" in tkfont.families(root)      # a memory font is usually not listed: not a failure
        chosen = root.fonts["body"][0] if hasattr(root, "fonts") else None
        res["theme chose it"] = bool(chosen) and chosen.lower().startswith("roboto condensed")
        locked = False
        try:
            os.rename(lay, lay + ".moved")
            os.rename(lay + ".moved", lay)
            os.rename(os.path.join(lay, "fonts"), os.path.join(lay, "fonts.moved"))
            os.rename(os.path.join(lay, "fonts.moved"), os.path.join(lay, "fonts"))
            os.rename(os.path.join(lay, "fonts", FONT), os.path.join(lay, "fonts", FONT + ".moved"))
            os.rename(os.path.join(lay, "fonts", FONT + ".moved"), os.path.join(lay, "fonts", FONT))
        except OSError as e:
            locked = True
            res["rename error"] = "%s" % e
            if os.path.isdir(lay + ".moved") and not os.path.isdir(lay):
                os.rename(lay + ".moved", lay)
        if mutant:
            res["MUTANT: rename fails (the test can tell)"] = locked
        else:
            res["folder renamed and back, fonts folder and font file too"] = not locked
        # the fallback: a failing load is silent
        saved = list(bt._FONT_KEEP) if hasattr(bt, "_FONT_KEEP") else []
        if hasattr(bt, "_FONT_KEEP"):
            del bt._FONT_KEEP[:]
            import ctypes
            real = ctypes.WinDLL

            def boom(*x, **k):
                raise OSError("simulated")
            ctypes.WinDLL = boom
            try:
                bt._load_fonts()
                res["a failing load is silent"] = True
            except Exception:
                res["a failing load is silent"] = False
            finally:
                ctypes.WinDLL = real
                bt._FONT_KEEP.extend(saved)
        elif not mutant:
            res["a failing load is silent"] = False
    except Exception:
        traceback.print_exc()
        res["exception"] = False
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    shutil.rmtree(WORK, ignore_errors=True)
    if mutant:
        failed = [k for k, v in res.items() if v is False and k != "a failing load is silent"]
        ok = res.get("MUTANT: rename fails (the test can tell)") is True
        print("MUTANT %s: %s" % ("caught" if ok else "NOT caught", res))
        return 0 if ok else 1
    failed = [k for k, v in res.items() if v is False and not k.startswith("info")]
    print("%d cases, %d failed %s %s" % (len(res), len(failed), failed, {k: v for k, v in res.items() if isinstance(v, str)}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
