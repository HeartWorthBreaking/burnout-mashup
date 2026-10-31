"""audited.py - run a Python file as __main__ with an audit hook that logs every path the process touches.

    py -3 -B audited.py SCRIPT [ARGS...]        (environment: BM_AUDIT_LOG = the log file, appended)

One line per event: "<event>\\t<absolute path>". Events: open, listdir, scandir, remove, rename, rmdir, mkdir, chmod, utime, rmtree, copyfile,
copytree, move. Used by test_isolation.py to prove that a launcher tool never opens, lists, writes or deletes anything below a
fake Takedawn folder. The log file is written with os.write on a descriptor opened before the hook starts (no recursion)."""
import os
import runpy
import sys

LOG = os.environ["BM_AUDIT_LOG"]
FD = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
EVENTS = {"open", "os.listdir", "os.scandir", "os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "os.truncate",
          "shutil.rmtree", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.link", "os.symlink"}


def hook(event, args):
    if event not in EVENTS:
        return
    for a in args[:2]:
        if isinstance(a, (str, bytes, os.PathLike)):
            try:
                p = os.path.abspath(os.fsdecode(a))
            except (OSError, ValueError):
                continue
            os.write(FD, ("%s\t%s\n" % (event, p)).encode("utf-8", "replace"))


sys.addaudithook(hook)
script = os.path.abspath(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name="__main__")
