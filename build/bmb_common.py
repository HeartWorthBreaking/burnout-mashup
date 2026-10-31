"""bmb_common.py - helpers shared by the Burnout Mashup build scripts (build/*.py). Original code, MIT.

Python 3.8+, standard library only. Exit codes of every script: 0 ok, 1 usage or tool failure, 2 REFUSED (an input is not the
pinned one; nothing was written). Every script prints ONE json line on stdout (the verdict) and human text on stderr.
"""
import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))          # the checkout root (build/ lives directly under it)


class Refused(Exception):
    """an input is not the pinned one: exit 2, nothing written"""


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def sha_f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def digest(man):
    """one sha256 over a {path: sha256} manifest: lines 'sha  path' sorted by path"""
    return sha_b("".join("%s  %s\n" % (v, k) for k, v in sorted(man.items())).encode())


def dir_manifest(d, skip=(".git", "__pycache__")):
    out = {}
    for dp, dn, fn in os.walk(d):
        dn[:] = sorted(x for x in dn if x not in skip)
        for f in sorted(fn):
            p = os.path.join(dp, f)
            out[os.path.relpath(p, d).replace(os.sep, "/")] = sha_f(p)
    return dict(sorted(out.items()))


def gen_tree_hash(gen):
    """sha256 of `sha256sum recomp_* | LC_ALL=C sort -k2` (upstream tools/release/common.sh gen_tree_hash)"""
    lines = ["%s  %s\n" % (sha_f(os.path.join(gen, f)), f) for f in sorted(os.listdir(gen)) if f.startswith("recomp_")]
    return sha_b("".join(sorted(lines, key=lambda l: l.split("  ", 1)[1].encode())).encode())


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jdump(obj, p):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def load_pins(path=None):
    return jload(path or os.path.join(ROOT, "host", "PINS.json"))


def load_expected(path=None):
    return jload(path or os.path.join(HERE, "EXPECTED.json"))


def say(msg):
    print(msg, file=sys.stderr, flush=True)


def git_env():
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def git(gitexe, args, autocrlf="false", binary=False, cwd=None):
    """run git read-only with an EXPLICIT core.autocrlf (never reads or changes the user's configuration)"""
    cmd = [gitexe, "-c", "core.autocrlf=" + autocrlf, "-c", "advice.detachedHead=false"] + list(args)
    r = subprocess.run(cmd, capture_output=True, env=git_env(), cwd=cwd)
    if r.returncode:
        raise Refused("git %s failed: %s" % (" ".join(args[:3]), r.stderr.decode("utf-8", "replace").strip()[:300]))
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def main_wrapper(fn):
    """run fn(argv) -> dict verdict; Refused -> {"refused": true, ...} exit 2"""
    try:
        res = fn(sys.argv[1:])
    except Refused as e:
        print(json.dumps({"refused": True, "reason": str(e)}))
        say("REFUSED: %s" % e)
        return 2
    except SystemExit:
        raise
    print(json.dumps(res, sort_keys=True))
    return 0


def arg_value(argv, name, default=None, required=False):
    if name in argv:
        i = argv.index(name)
        if i + 1 >= len(argv):
            raise SystemExit("usage: %s needs a value" % name)
        return argv[i + 1]
    if required:
        raise SystemExit("usage: %s is required" % name)
    return default
