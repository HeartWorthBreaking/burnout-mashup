"""test_build_now.py - the Build Mashup button (bmbuild_gui.BuildWindow.build_all): game, tools, build on one click, over stand-in steps, game checks and
tool states in a real (withdrawn) Tk window; no network, no compile. BMBUILD_NOW_DIR: a folder searched first (mutated copies)."""
import json
import os
import queue
import shutil
import sys
import tempfile
import tkinter as tk
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmbuild  # noqa: E402
import bmimage  # noqa: E402
import bmtools  # noqa: E402
if os.environ.get("BMBUILD_NOW_DIR"):
    sys.path.insert(0, os.environ["BMBUILD_NOW_DIR"])
import bmbuild_gui as G  # noqa: E402

SPEC = bmtools.spec()
TOOLS = list(SPEC)
NEEDY = next((t for t in TOOLS if SPEC[t]["needs"]), None)


class World:
    def __init__(self, missing=(), answer=True, fail=None, stays_missing=False):
        self.missing, self.answer, self.fail, self.stays = set(missing), answer, dict(fail or {}), stays_missing
        self.ran, self.asked = [], []

    def check(self, lay):
        return {t: {"ok": t not in self.missing, "found": "x", "path": "p", "want": "x", "where": "w", "problem": ""} for t in TOOLS}

    def step(self, args):
        self.ran.append(args)
        if self.fail.get(args[0]):
            return 1, {"ev": "result", "rc": 1, "cls": args[0], "message": args[0] + " failed", "recovery": "try again"}
        if args[0] == "download" and not self.stays:
            self.missing -= set(args[1:])
        return 0, {"ev": "result", "rc": 0, "cls": "ok", "message": "ok"}

    def kinds(self):
        return [a[0] for a in self.ran]


def make(world, tmp, game="", good=True):
    class FakeStep:
        cancelled = False

        def __init__(self, name, args, root=None, **kw):
            self.lines = queue.Queue()
            self.rc, ev = world.step(args)
            self.lines.put("@@ " + json.dumps(ev))
            self.lines.put(None)

        def running(self):
            return not self.lines.empty()

        def cancel(self):
            pass
    bmtools.check = world.check

    def inspect(p, sha=None):
        if not good or os.path.basename(p) == "bad":
            raise bmimage.Refused("not the supported game")
        if not os.path.isfile(os.path.join(p, "default.xbe")) and not p.endswith("picked"):
            raise bmimage.Refused("no game here")
        return {"supported": True, "kind": "folder", "reason": "ok", "facts": {"title": "t"}}
    bmimage.inspect = inspect
    root = tk.Tk()
    root.withdraw()

    def ask(title, text, parent=None):
        world.asked.append(text)
        return world.answer
    w = G.BuildWindow(root, launcher=tmp, step_factory=FakeStep, ask=ask)
    w.withdraw()
    w.v_input.set(game)
    w.v_tools.set(os.path.join(tmp, "tools"))
    w.v_bd.set(os.path.join(tmp, "bd"))
    w.ask_game = lambda: (_ for _ in ()).throw(AssertionError("the game was asked for"))
    return root, w


def settle(root, w):
    for _ in range(400):
        root.update()
        if str(w.build_btn["state"]) == "normal" and not w.auto:
            return
        root.after(5)
    raise AssertionError("did not settle")


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def game(tmp, name="g"):
    d = os.path.join(tmp, name)
    os.makedirs(d)
    open(os.path.join(d, "default.xbe"), "wb").close()
    return d


@case
def all_there_only_builds(tmp):
    W = World()
    r, w = make(W, tmp, game(tmp))
    assert w.build_all()
    settle(r, w)
    assert W.kinds() == ["build"] and not W.asked, W.ran
    assert "--events" in W.ran[0] and "--input" in W.ran[0]
    r.destroy()


@case
def missing_tools_one_question_then_build(tmp):
    W = World(missing=TOOLS[:3])
    r, w = make(W, tmp, game(tmp))
    assert w.build_all()
    settle(r, w)
    assert W.kinds() == ["download", "build"], W.ran
    assert len(W.asked) == 1, "one question for all tools: %d" % len(W.asked)
    for t in TOOLS[:3]:
        assert t in W.ran[0] and SPEC[t]["licence"] in W.asked[0] and SPEC[t]["url"] in W.asked[0], t
    assert "--yes" in W.ran[0]
    r.destroy()


@case
def a_tools_needs_come_first(tmp):
    if not NEEDY:
        return
    W = World(missing=[NEEDY] + SPEC[NEEDY]["needs"])
    I = W.check
    W.check = lambda lay: dict(sorted(I(lay).items(), key=lambda kv: kv[0] != NEEDY))    # the tool first: its needs must still go before it
    r, w = make(W, tmp, game(tmp))
    w.build_all()
    settle(r, w)
    a = W.ran[0]
    assert a.index(SPEC[NEEDY]["needs"][0]) < a.index(NEEDY), a
    r.destroy()


@case
def declined_downloads_nothing(tmp):
    W = World(missing=TOOLS[:2], answer=False)
    r, w = make(W, tmp, game(tmp))
    assert not w.build_all() and W.ran == [] and "Not downloaded" in w.result["text"] and not w.auto
    r.destroy()


@case
def failed_download_no_build(tmp):
    W = World(missing=TOOLS[:2], fail={"download": 1})
    r, w = make(W, tmp, game(tmp))
    w.build_all()
    settle(r, w)
    assert W.kinds() == ["download"] and not w.auto, W.ran
    r.destroy()


@case
def failed_download_with_tools_there_no_build(tmp):
    W = World(missing=TOOLS[:2], fail={"download": 1})
    I = W.step

    def step(args):
        W.missing.clear()
        return I(args)
    W.step = step
    r, w = make(W, tmp, game(tmp))
    w.build_all()
    settle(r, w)
    assert W.kinds() == ["download"], W.ran
    r.destroy()


@case
def still_missing_after_download_no_build(tmp):
    W = World(missing=TOOLS[:2], stays_missing=True)
    r, w = make(W, tmp, game(tmp))
    w.build_all()
    settle(r, w)
    assert W.kinds() == ["download"], W.ran
    r.destroy()


@case
def game_found_in_gamedata(tmp):
    W = World()
    os.makedirs(os.path.join(tmp, "gamedata", "mods"))
    d = game(os.path.join(tmp, "gamedata"), "Burnout 3 Takedown")
    r, w = make(W, tmp)
    assert w.build_all()
    settle(r, w)
    assert w.v_input.get() == d and W.kinds() == ["build"], (w.v_input.get(), W.ran)
    r.destroy()


@case
def no_game_asks_once(tmp):
    W = World()
    r, w = make(W, tmp)
    n = []
    w.ask_game = lambda: n.append(1) or os.path.join(tmp, "picked")
    assert w.build_all()
    settle(r, w)
    assert n == [1] and W.kinds() == ["build"] and w.v_input.get().endswith("picked"), W.ran
    r.destroy()


@case
def no_game_cancelled_runs_nothing(tmp):
    W = World(missing=TOOLS[:1])
    r, w = make(W, tmp)
    w.ask_game = lambda: ""
    assert not w.build_all() and W.ran == [] and not W.asked and "Choose your game" in w.result["text"]
    r.destroy()


@case
def refused_game_runs_nothing(tmp):
    W = World(missing=TOOLS[:1])
    d = game(tmp, "bad")
    r, w = make(W, tmp, d)
    assert not w.build_all() and W.ran == [] and not W.asked, W.ran
    r.destroy()


@case
def failed_build_says_why(tmp):
    W = World(fail={"build": 1})
    r, w = make(W, tmp, game(tmp))
    w.build_all()
    settle(r, w)
    assert W.kinds() == ["build"] and "try again" in w.result["text"], w.result["text"]
    r.destroy()


@case
def cancel_during_download_no_build(tmp):
    W = World(missing=TOOLS[:1])
    r, w = make(W, tmp, game(tmp))
    w.build_all()
    orig = w.job.running
    w.job.running = lambda: True
    w.cancel()
    w.job.running = orig
    assert not w.auto
    settle(r, w)
    assert W.kinds() == ["download"], W.ran
    r.destroy()


@case
def advanced_hidden_until_asked(tmp):
    W = World()
    r, w = make(W, tmp)
    assert not w.adv.winfo_manager()
    w.toggle_advanced()
    assert w.adv.winfo_manager() == "pack"
    w.toggle_advanced()
    assert not w.adv.winfo_manager()
    r.destroy()


@case
def opening_runs_nothing(tmp):
    W = World(missing=TOOLS[:1])
    r, w = make(W, tmp)
    r.update()
    assert W.ran == [] and not W.asked
    r.destroy()


@case
def per_tool_download_kept(tmp):
    W = World(missing=TOOLS[:2], answer=False)
    r, w = make(W, tmp)
    w.recheck_tools()
    assert w.download_selected() == [] and len(W.asked) >= 2, W.asked
    r.destroy()


def main():
    bad = 0
    keep = bmtools.check, bmimage.inspect
    for fn in CASES:
        tmp = tempfile.mkdtemp(prefix="bldnow")
        try:
            fn(tmp)
            print("PASS", fn.__name__)
        except Exception:  # noqa: BLE001
            bad += 1
            print("FAIL", fn.__name__, traceback.format_exc().strip().splitlines()[-1])
        finally:
            bmtools.check, bmimage.inspect = keep
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d cases, %d failed" % (len(CASES), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
