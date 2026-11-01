"""bmpaths.py - where the launcher keeps your game copy and your mods, for both install layouts (Python 3.8+, standard library).
Original code (MIT).

Layout 2 (the Windows package, 0.2.0 and later; detected, not configured): the program tree is a folder named "app" whose parent
holds "Burnout Mashup.exe":

    <install>\\Burnout Mashup.exe, Burnout Mashup Workbench.exe
    <install>\\gamedata\\              the game copy (Burnout 3 Takedown\\..., .complete) and
    <install>\\gamedata\\mods\\user     your mods      <install>\\gamedata\\mods\\generated   demo mods made from your game
    <install>\\app\\                   the program (launcher\\, host\\, build\\, workbench\\, ...); app\\launcher\\mods\\demo ships the demos

Layout 1 (a git clone or an unpacked source zip, as in 0.1.0): everything under launcher\\ (gamedata\\, mods\\user, mods\\generated).
"""
import os

APP = "app"
EXE = "Burnout Mashup.exe"
WB_EXE = "Burnout Mashup Workbench.exe"
GAMEDATA = "gamedata"
MODS = "mods"
MOD_KINDS = ("demo", "generated", "user")


def tree_root(launcher):
    return os.path.dirname(os.path.abspath(launcher))


def install_root(launcher):
    """the layout-2 install folder (parent of app\\), or None in layout 1"""
    t = tree_root(launcher)
    p = os.path.dirname(t)
    if os.path.basename(t).lower() == APP and os.path.isfile(os.path.join(p, EXE)):
        return p
    return None


def layout(launcher):
    return 2 if install_root(launcher) else 1


def gamedata(launcher):
    ir = install_root(launcher)
    return os.path.join(ir, GAMEDATA) if ir else os.path.join(os.path.abspath(launcher), GAMEDATA)


def mods_dir(launcher, kind):
    """demo: shipped with the program (launcher\\mods\\demo); generated / user: in gamedata\\mods (layout 2) or launcher\\mods (layout 1)"""
    if kind not in MOD_KINDS:
        raise ValueError(kind)
    if kind == "demo" or not install_root(launcher):
        return os.path.join(os.path.abspath(launcher), MODS, kind)
    return os.path.join(gamedata(launcher), MODS, kind)


def mod_dirs(launcher):
    return [(k, mods_dir(launcher, k)) for k in MOD_KINDS]


def game_entries(gd):
    """the entries of a gamedata folder that belong to the game copy (everything except mods\\)"""
    try:
        return sorted(n for n in os.listdir(gd) if n.lower() != MODS)
    except OSError:
        return []


def display(launcher, path):
    """a short name for messages: relative to the install (layout 2) or the launcher folder"""
    base = install_root(launcher) or os.path.abspath(launcher)
    try:
        r = os.path.relpath(path, base)
    except ValueError:
        return path
    return path if r.startswith("..") else r
