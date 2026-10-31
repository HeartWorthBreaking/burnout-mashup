"""trackbuild.accessguard - an opt-in file-access monitor used to PROVE that trackbuild reads nothing outside the folders it
was given (isolation test of the portable 0.2.0 tool; README "Isolation check").

Enabled by two environment variables (nothing happens without them):
  TRACKBUILD_ACCESS_LOG = <file>                  every path the process touches is appended to it (tab-separated)
  TRACKBUILD_FORBID     = <prefix>[;<prefix>...]  paths under any of these prefixes are counted as FORBIDDEN
What is seen: Python audit events with a path (open, os.listdir / scandir / mkdir / remove / rename / rmdir / chdir,
shutil.*, glob, subprocess.Popen, import) plus os.stat / os.lstat / os.path.exists / isfile / isdir / lexists (wrapped,
they raise no audit event). At exit it writes SUMMARY lines: totals, forbidden accesses, and every sys.path entry or
loaded module file under a forbidden prefix. Native code that opens files without Python (none in trackbuild) is not seen.
The guard never blocks: it records (the test then requires FORBIDDEN 0)."""
import atexit
import os
import sys

_STATE = {}
PATH_EVENTS = {"open": 0, "os.listdir": 0, "os.scandir": 0, "os.mkdir": 0, "os.remove": 0, "os.rename": 0, "os.rmdir": 0,
               "os.chdir": 0, "os.truncate": 0, "os.utime": 0, "os.chmod": 0, "shutil.copyfile": 0, "shutil.copymode": 0,
               "shutil.copystat": 0, "shutil.copytree": 0, "shutil.rmtree": 0, "shutil.move": 0, "glob.glob": 0,
               "subprocess.Popen": 1, "os.startfile": 0, "os.link": 0, "os.symlink": 0}


def _norm(p):
    try:
        if isinstance(p, int):
            return None
        p = os.fsdecode(p)
    except TypeError:
        return None
    try:
        return os.path.normcase(os.path.abspath(p)) if p else None
    except (ValueError, TypeError):
        return None


def _forbidden(n):
    return n is not None and any(n == f or n.startswith(f.rstrip("\\/") + os.sep) for f in _STATE["forbid"])


def _emit(event, path):
    n = _norm(path)
    if n is None or n == _STATE["log_norm"]:
        return
    bad = _forbidden(n)
    _STATE["total"] += 1
    if bad:
        _STATE["forbidden"] += 1
    os.write(_STATE["fd"], ("%s\t%s\t%s\n" % ("FORBIDDEN" if bad else "ok", event, n)).encode("utf-8", "replace"))


def _hook(event, args):
    if _STATE.get("busy"):
        return
    try:
        _STATE["busy"] = True
        if event in PATH_EVENTS and args:
            a = args[PATH_EVENTS[event]] if len(args) > PATH_EVENTS[event] else args[0]
            if event == "subprocess.Popen" and isinstance(a, (list, tuple)):
                for x in a:
                    if isinstance(x, (str, bytes, os.PathLike)) and (os.sep in os.fsdecode(x) or "/" in os.fsdecode(x)):
                        _emit(event, x)
            elif isinstance(a, (str, bytes, os.PathLike)):
                _emit(event, a)
            if event in ("os.rename", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.link", "os.symlink") and len(args) > 1:
                if isinstance(args[1], (str, bytes, os.PathLike)):
                    _emit(event + "(dst)", args[1])
        elif event == "import" and len(args) > 1 and args[1]:
            _emit("import", args[1])
    finally:
        _STATE["busy"] = False


def _wrap(mod, name):
    f = getattr(mod, name)

    def w(path, *a, **k):
        if not _STATE.get("busy"):
            try:
                _STATE["busy"] = True
                if isinstance(path, (str, bytes, os.PathLike)):
                    _emit(mod.__name__ + "." + name, path)
            finally:
                _STATE["busy"] = False
        return f(path, *a, **k)
    w.__wrapped__ = f
    setattr(mod, name, w)


def _summary():
    bad_path = [p for p in sys.path if _forbidden(_norm(p))]
    bad_mod = sorted({getattr(m, "__file__", None) for m in list(sys.modules.values())
                      if getattr(m, "__file__", None) and _forbidden(_norm(m.__file__))})
    lines = ["SUMMARY\tpid %d\targv %s" % (os.getpid(), " ".join(sys.argv[:3])),
             "SUMMARY\taccesses %d\tforbidden %d" % (_STATE["total"], _STATE["forbidden"]),
             "SUMMARY\tsys.path under a forbidden prefix %d %s" % (len(bad_path), bad_path[:3]),
             "SUMMARY\tloaded modules under a forbidden prefix %d %s" % (len(bad_mod), bad_mod[:3])]
    os.write(_STATE["fd"], ("\n".join(lines) + "\n").encode("utf-8", "replace"))
    os.close(_STATE["fd"])


def install_from_env(env=None):
    env = os.environ if env is None else env
    log = env.get("TRACKBUILD_ACCESS_LOG")
    if not log or _STATE:
        return False
    forbid = [os.path.normcase(os.path.abspath(x.strip())) for x in env.get("TRACKBUILD_FORBID", "").split(";") if x.strip()]
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0))
    _STATE.update(fd=fd, forbid=forbid, total=0, forbidden=0, log_norm=os.path.normcase(os.path.abspath(log)))
    os.write(fd, ("START\tforbid %s\n" % ";".join(forbid)).encode("utf-8", "replace"))
    for p in sys.path:                                   # what was on the path before the guard started
        _emit("sys.path(start)", p)
    sys.addaudithook(_hook)
    import ntpath
    import genericpath
    for mod, names in ((os, ("stat", "lstat")), (ntpath, ("exists", "isfile", "isdir", "lexists")),
                       (genericpath, ("exists", "isfile", "isdir"))):
        for n in names:
            if hasattr(mod, n):
                _wrap(mod, n)
    atexit.register(_summary)
    return True
