"""test_update_now.py - Help -> Update now (bmupdate_gui.UpdateWindow.update_now): every step in turn on one click, over stand-in steps and a
stand-in update state in a real (withdrawn) Tk window; no network, no install. BMUPDATE_NOW_DIR: a folder searched first (mutated copies)."""
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
if os.environ.get("BMUPDATE_NOW_DIR"):
    sys.path.insert(0, os.environ["BMUPDATE_NOW_DIR"])
import bmupdate  # noqa: E402
if os.environ.get("BMUPDATE_NOW_DIR"):
    sys.path.insert(0, os.environ["BMUPDATE_NOW_DIR"])   # again: bmupdate puts its own folder first
import bmupdate_gui as G  # noqa: E402
assert not os.environ.get("BMUPDATE_NOW_DIR") or os.path.dirname(os.path.abspath(G.__file__)) == os.path.abspath(os.environ["BMUPDATE_NOW_DIR"]) or "bmupdate.py" in os.listdir(os.environ["BMUPDATE_NOW_DIR"])

PKG = {"configured": True, "layout": 2, "version": "1.0", "pending": None, "next_step": None}


class World:
    """the update state as the real steps leave it, and what each step answers"""
    def __init__(self, layout=2, available=True, fail=None, rebuild=False):
        self.layout, self.available, self.fail, self.rebuild = layout, available, dict(fail or {}), rebuild
        self.ran, self.pending, self.configured = [], None, True

    def status(self):
        p = self.pending
        nxt = None
        if p:
            nxt = "build" if p.get("prepared") else "prepare" if p.get("archive") else "download"
            if self.layout == 2 and p.get("prepared") and not p.get("installed"):
                nxt = "install"
        return {"configured": self.configured, "layout": self.layout, "version": "1.0", "pending": p, "next_step": nxt, "why": "no channel",
                "channel": "c", "where": "w", "trusted_keys": []}

    def step(self, args):
        cmd = args[0]
        self.ran.append(cmd)
        if self.fail.get(cmd):
            self.fail[cmd] -= 1
            return 1, {"ev": "result", "rc": 1, "cls": "install", "message": cmd + " failed", "recovery": "close the game"}
        if cmd == "check":
            if not self.available:
                return 0, {"ev": "result", "rc": 0, "cls": "up_to_date", "message": "up to date"}
            self.pending = {"version": "2.0"}
            return 0, {"ev": "result", "rc": 0, "cls": "available", "message": "available"}
        if cmd == "download":
            self.pending["archive"] = "a"
        elif cmd == "prepare":
            self.pending["prepared"] = "p"
        elif cmd == "install":
            self.pending = dict(self.pending, installed=True) if self.rebuild else None
            return 0, {"ev": "result", "rc": 0, "cls": "installed", "message": "installed", "restart": True}
        elif cmd == "build":
            self.pending = None
        return 0, {"ev": "result", "rc": 0, "cls": cmd, "message": cmd + " done"}


def make(world, tmp, game="C:/game"):
    class FakeUpdater:
        def __init__(self, *a, **k):
            pass

        def status(self):
            return world.status()

    class FakeStep:
        def __init__(self, name, args, root=None, **kw):
            self.lines, self.rc = queue.Queue(), None
            self.rc, ev = world.step(args)
            self.lines.put("@@ " + json.dumps(ev))
            self.lines.put(None)

        def running(self):
            return not self.lines.empty()

        def cancel(self):
            pass
    bmupdate.Updater = FakeUpdater
    root = tk.Tk()
    root.withdraw()
    w = G.UpdateWindow(root, launcher=tmp, step_factory=FakeStep, ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError("a question was asked")))
    w.withdraw()
    w.v_input.set(game)
    w.restarted = []
    w.restart = lambda msg, quiet=False: w.restarted.append(quiet)
    return root, w


def settle(root, w):
    for _ in range(400):
        root.update()
        if not (w.job and w.job.running()) and not w.job:
            root.update()
            if not w.job:
                return
        root.after(5)
    raise AssertionError("did not settle: %s" % w.job_kind)


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def mark(tmp):
    return os.path.exists(G.resume_mark(tmp))


@case
def full_package(tmp):
    W = World()
    r, w = make(W, tmp)
    assert w.update_now()
    settle(r, w)
    assert W.ran == ["check", "download", "prepare", "install"], W.ran
    assert w.restarted == [True], "restart without a popup: %s" % w.restarted
    assert mark(tmp), "the mark stays for the new version"
    r.destroy()


@case
def up_to_date(tmp):
    W = World(available=False)
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert W.ran == ["check"] and not w.restarted and not mark(tmp) and not w.auto, W.ran
    assert "up to date" in w.result["text"]
    r.destroy()


@case
def failed_download_stops_then_goes_on(tmp):
    W = World(fail={"download": 1})
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert W.ran == ["check", "download"] and not w.auto, W.ran
    assert "close the game" in w.result["text"], w.result["text"]
    w.update_now()
    settle(r, w)
    assert W.ran == ["check", "download", "check", "download", "prepare", "install"], W.ran
    r.destroy()


@case
def install_in_use_keeps_nothing_behind(tmp):
    W = World(fail={"install": 1})
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert W.ran[-1] == "install" and not w.restarted and not mark(tmp) and not w.auto, (W.ran, mark(tmp))
    w.update_now()
    settle(r, w)
    assert w.restarted == [True] and W.ran.count("install") == 2
    r.destroy()


@case
def source_checkout_builds(tmp):
    W = World(layout=1)
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert W.ran == ["check", "download", "prepare", "build"] and not w.restarted and not w.auto, W.ran
    r.destroy()


@case
def build_without_a_game_asks(tmp):
    W = World(layout=1)
    r, w = make(W, tmp, game="")
    w.update_now()
    settle(r, w)
    assert W.ran == ["check", "download", "prepare"] and "give your game" in w.result["text"] and not w.auto, W.ran
    assert w.adv.winfo_manager() == "pack", "the game field must be in view"
    r.destroy()


@case
def resume_builds_after_restart(tmp):
    W = World(rebuild=True)
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert mark(tmp) and W.pending.get("installed")
    r.destroy()
    r2, w2 = make(W, tmp)
    W.ran.clear()
    assert w2.resume()
    settle(r2, w2)
    assert W.ran == ["build"] and not mark(tmp) and not w2.auto, (W.ran, mark(tmp))
    r2.destroy()


@case
def resume_with_nothing_left_only_clears(tmp):
    W = World()
    r, w = make(W, tmp)
    os.makedirs(os.path.dirname(G.resume_mark(tmp)), exist_ok=True)
    open(G.resume_mark(tmp), "w").close()
    assert not w.resume()
    assert W.ran == [] and not mark(tmp)
    r.destroy()


@case
def pressing_after_install_only_builds(tmp):
    W = World(rebuild=True)
    W.pending = {"version": "2.0", "archive": "a", "prepared": "p", "installed": True}
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert W.ran == ["build"], W.ran
    r.destroy()


@case
def up_to_date_with_an_old_pending_stops(tmp):
    W = World(available=False)
    W.pending = {"version": "1.5"}
    r, w = make(W, tmp)
    w.update_now()
    settle(r, w)
    assert W.ran == ["check"], W.ran
    r.destroy()


@case
def build_is_the_last_step(tmp):
    W = World(layout=1)
    W.pending = {"version": "2.0", "archive": "a", "prepared": "p"}
    I = W.step

    def step(args):
        rc, ev = I(args)
        if args[0] == "build":
            W.pending = {"version": "2.0", "archive": "a", "prepared": "p"}   # whatever the state says: no second build
        return rc, ev
    W.step = step
    W.available = False
    r, w = make(W, tmp)
    w.auto = True
    w.run("build", [])
    settle(r, w)
    assert W.ran == ["build"] and not w.auto, W.ran
    r.destroy()


@case
def no_channel_runs_nothing(tmp):
    W = World()
    W.configured = False
    r, w = make(W, tmp)
    assert not w.update_now() and W.ran == [] and "no channel" in w.result["text"]
    assert str(w.btn["update"]["state"]) == "disabled"
    r.destroy()


@case
def opening_runs_nothing(tmp):
    W = World()
    r, w = make(W, tmp)
    r.update()
    assert W.ran == [] and not w.auto and not mark(tmp)
    assert not w.adv.winfo_manager(), "the single steps stay under Advanced options"
    w.toggle_advanced()
    assert w.adv.winfo_manager() == "pack"
    w.toggle_advanced()
    assert not w.adv.winfo_manager()
    r.destroy()


@case
def cancel_stops_the_chain(tmp):
    W = World()
    r, w = make(W, tmp)
    w.update_now()
    orig = w.job.running
    w.job.running = lambda: True
    w.after = lambda *a, **k: None if False else tk.Toplevel.after(w, *a, **k)
    w.cancel()
    w.job.running = orig
    settle(r, w)
    assert W.ran == ["check"] and not w.auto and not mark(tmp), W.ran
    r.destroy()


def main():
    bad = 0
    orig = bmupdate.Updater
    for fn in CASES:
        tmp = tempfile.mkdtemp(prefix="updnow")
        try:
            fn(tmp)
            print("PASS", fn.__name__)
        except Exception:  # noqa: BLE001
            bad += 1
            print("FAIL", fn.__name__, traceback.format_exc().strip().splitlines()[-1])
        finally:
            bmupdate.Updater = orig
            shutil.rmtree(tmp, ignore_errors=True)
    # the real CLI hands the restart to the window (the 0.2.0 window never restarted: the event lacked it)
    out = []
    I = orig.install
    orig.install = lambda self: {"version": "2", "carried": 1, "previous_version": "1", "rebuild_needed": False, "restart": True}
    orig.status = orig.status
    d = tempfile.mkdtemp(prefix="updnow")
    rc = bmupdate.main(["install", "--launcher", d, "--events"], out=out.append)
    orig.install = I
    shutil.rmtree(d, ignore_errors=True)
    ev = [json.loads(x[3:]) for x in out if x.startswith("@@ ") and '"result"' in x]
    if rc == 0 and ev and ev[-1].get("restart") is True:
        print("PASS install_event_carries_restart")
    else:
        bad += 1
        print("FAIL install_event_carries_restart", rc, ev)
    print("%d cases, %d failed" % (len(CASES) + 1, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
