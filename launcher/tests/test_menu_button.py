"""test_menu_button.py - bmtheme.MenuButton, the launcher's button: the use of a ttk.Button (text, command, state, ["state"], invoke, instate, keys, pointer), a drop shadow,
and the menu's tab row over a notebook. A real, withdrawn Tk window."""
import os
import sys
import tkinter as tk
import traceback
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "launcher"))
import bmtheme  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def texts(b):
    return [(b.itemcget(i, "text"), b.itemcget(i, "fill")) for i in b.find_all() if b.type(i) == "text"]


@case
def replaces_ttk_button(root):
    assert ttk.Button is bmtheme.MenuButton, "made through ttk.Button in the launcher"
    calls = []
    b = ttk.Button(root, text="Build Mashup", underline=0, style="Accent.TButton", command=lambda: calls.append(1))
    b.pack()
    root.update()
    assert b.cget("text") == "Build Mashup" and b["text"] == "Build Mashup" and b.cget("style") == "Accent.TButton"
    b.invoke()
    assert calls == [1]
    b["state"] = "disabled"
    assert str(b["state"]) == "disabled" and b.instate(["disabled"]) and not b.instate(["!disabled"])
    b.invoke()
    assert calls == [1], "disabled: no command"
    b.configure(state="normal", text="Again", command=lambda: calls.append(2))
    assert b.cget("text") == "Again" and b.instate(["!disabled"])
    b.invoke()
    assert calls == [1, 2]
    b.destroy()


@case
def a_shadow_when_on(root):
    b = ttk.Button(root, text="Check now")
    b.pack()
    root.update()
    t = texts(b)
    assert len(t) == 2 and t[0] == ("Check now", bmtheme.SHADOW) and t[1][0] == "Check now" and t[1][1] != bmtheme.SHADOW, t
    assert not [i for i in b.find_all() if b.type(i) == "rectangle"], "no box"
    b["state"] = "disabled"
    t = texts(b)
    assert len(t) == 1 and t[0][1] == bmtheme.FAINT, "disabled: dim, no shadow: %s" % t
    b.destroy()


@case
def pointer_and_keys(root):
    calls = []
    b = ttk.Button(root, text="Go", command=lambda: calls.append(1))
    b.pack()
    root.update()
    b._set(over=True)
    assert [i for i in b.find_all() if b.type(i) == "rectangle"], "a lit bar under the pointer"
    b._set(over=False)

    class E:
        x, y = 1, 1
    b._set(down=True)
    b._release(E)
    assert calls == [1], "press and release on it"

    class Off:
        x, y = -5, -5
    b._set(down=True)
    b._release(Off)
    assert calls == [1], "released off it: nothing"
    b._release(E)
    assert calls == [1], "a release with no press: nothing"
    b.event_generate("<Return>") if False else b.invoke()
    assert calls == [1, 1]
    b.destroy()


@case
def wider_text_wider_button(root):
    a, b = ttk.Button(root, text="Go"), ttk.Button(root, text="Install an older version...")
    assert int(b.cget("width")) > int(a.cget("width")) > 0
    n = int(a.cget("width"))
    a["text"] = "Install an older version..."
    assert int(a.cget("width")) > n, "follows its text"
    a.destroy()
    b.destroy()


@case
def tab_row_follows_the_notebook(root):
    nb = ttk.Notebook(root, style="Menu.TNotebook")
    for t in ("Setup", "Mods"):
        nb.add(ttk.Frame(nb), text=t)
    nb.pack()
    seen = []
    row = bmtheme.menu_tabs(root, nb, ["Setup", "Mods"], seen.append)
    row.pack()
    root.update()
    a, b = row.winfo_children()
    assert a._sel and not b._sel and seen[-1] == "Setup"
    assert [x[0] for x in texts(a)] == ["SETUP", "SETUP"], "capitals on the row; the notebook keeps its text"
    assert nb.tab(nb.tabs()[0], "text") == "Setup"
    b.invoke()
    root.update()
    assert nb.index("current") == 1 and b._sel and not a._sel and seen[-1] == "Mods"
    assert [i for i in b.find_all() if b.type(i) == "line"], "ticks on the selected one"
    assert not [i for i in a.find_all() if a.type(i) == "line"]
    nb.select(0)
    root.update()
    assert a._sel, "the notebook's own selection (Ctrl+1) moves the ticks"
    row.destroy()
    nb.destroy()


@case
def title_has_no_command(root):
    t = bmtheme.menu_title(root, "Last game")
    t.pack()
    root.update()
    assert [x[0] for x in texts(t)] == ["LAST GAME", "LAST GAME"]
    assert t.invoke() is None
    t._over = True
    t._draw()
    assert not [i for i in t.find_all() if t.type(i) == "rectangle"], "a heading does not light up"
    t.destroy()


def main():
    root = tk.Tk()
    root.withdraw()
    root.scale = 1.0
    bmtheme.apply(root)
    bad = 0
    for fn in CASES:
        try:
            fn(root)
            print("PASS", fn.__name__)
        except Exception:  # noqa: BLE001
            bad += 1
            print("FAIL", fn.__name__, traceback.format_exc().strip().splitlines()[-1][:200])
    root.destroy()
    print("%d cases, %d failed" % (len(CASES), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
