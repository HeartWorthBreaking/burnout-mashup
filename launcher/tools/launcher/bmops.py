"""bmops.py - long-running bundle steps for the launcher: run one bundle tool as a child process, stream its lines, cancel it.

Only the bundle's OWN tools run (tools\\*.py named here, with the same Python as the launcher) - never anything from a mod or a
dropped file. A cancelled step stops the child process tree (taskkill /T on Windows); every tool used here writes into a work
folder first and keeps the previous result until it succeeds (prepare.py: work\\ then a rename; checked by the R1 tests).
"""
import os
import queue
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)

STEPS = {   # name -> (tool, fixed arguments); user paths are appended as separate arguments (never through a shell)
    "preflight": ("preflight.py", []),
    "data_copy": ("prepare.py", ["data", "--copy-from"]),
    "data_install": ("prepare.py", ["data", "--install-from"]),
    "data_auto": ("prepare.py", ["auto"]),
    "demos": ("prepare.py", ["demos"]),
    "status": ("prepare.py", ["status"]),
    "diag": ("bmdiag.py", ["--bundle", ROOT, "--out"]),
    "backup": ("uninstall.py", ["backup", "--to"]),
    "upgrade": ("uninstall.py", ["upgrade", "--from"]),
    "verify": ("uninstall.py", ["verify"]),
    "repair": ("uninstall.py", ["repair", "--from"]),
    "clean": ("uninstall.py", ["clean", "--yes"]),
}


class Step:
    """One running tool: lines arrive on .lines (None = finished); .rc after the end; .cancel() stops it."""

    def __init__(self, name, extra=(), root=ROOT, cwd=None):
        tool, fixed = STEPS[name]
        self.name = name
        self.cmd = [sys.executable, "-B", os.path.join(root, "tools", tool)] + fixed + [str(x) for x in extra]
        self.lines = queue.Queue()
        self.rc = None
        self.cancelled = False
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # rel020: an install / switch back renames folders of app\; its child runs in the install folder (cwd=), never inside app\
        self.p = subprocess.Popen(self.cmd, cwd=cwd or root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  env=env, creationflags=flags, text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for ln in self.p.stdout:
            self.lines.put(ln.rstrip("\r\n"))
        self.rc = self.p.wait()
        self.lines.put(None)

    def cancel(self):
        if self.p.poll() is not None:
            return
        self.cancelled = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.p.pid), "/T", "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            self.p.terminate()

    def running(self):
        return self.p.poll() is None


def explain(name, rc, cancelled, tail):
    """A short, actionable sentence for the end of a step (the tool's own 'refused: reason + fix' lines stay in the log)."""
    if cancelled:
        return "Cancelled. Nothing half-done was kept; the previous result (if any) is unchanged. You can run the step again."
    if rc == 0:
        return "Done."
    hint = next((ln for ln in reversed(tail) if ln.lower().startswith(("refused", "fix", "  fix", "error", "fail"))), "")
    base = {2: "The step was called the wrong way (usage).", 3: "Refused - the reason and the fix are in the log above.",
            4: "A bundled tool failed - see the log above; a diagnostic export (Help tab) helps a bug report.",
            9: "Python 3.11 or newer is needed: install it from python.org (tick 'Add to PATH') and start the launcher again.",
            1: "Check found a problem - every FAIL line above names its fix."}.get(rc, "Ended with exit status %s." % rc)
    return base + ((" " + hint.strip()) if hint else "")
