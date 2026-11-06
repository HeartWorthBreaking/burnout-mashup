"""test_build_readonly.py - BUILD MASHUP removes read-only files: a second fetch in one build folder must not fail on the read-only pack files git
leaves (exit 3 after an update in 0.3.0-alpha.1). Offline; no game. py -3 -B test_build_readonly.py"""
import os
import shutil
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "launcher"))
import bmbuild  # noqa: E402


def tree(root):
    p = os.path.join(root, "_git", "objects", "pack")
    os.makedirs(p)
    for n in ("pack-1.idx", "pack-1.pack"):
        f = os.path.join(p, n)
        open(f, "wb").write(b"x")
        os.chmod(f, stat.S_IREAD)
    return root


def main():
    t = tempfile.mkdtemp(prefix="bm_ro_")
    try:
        a = tree(os.path.join(t, "a"))
        bmbuild.rm_tree(a)
        assert not os.path.exists(a), "rm_tree left the folder"
        b = tree(os.path.join(t, "b"))
        bmbuild.rm_tree(b, ignore_errors=True)
        assert not os.path.exists(b), "rm_tree(ignore_errors) left the folder"
        bmbuild.rm_tree(os.path.join(t, "missing"), ignore_errors=True)
        try:
            bmbuild.rm_tree(os.path.join(t, "missing"))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("a missing folder must still be an error")
        src = open(bmbuild.__file__, encoding="utf-8").read()
        assert src.count("shutil.rmtree(") == 1, "every delete in bmbuild.py goes through rm_tree"
    finally:
        for dp, dn, fn in os.walk(t):
            for f in fn:
                os.chmod(os.path.join(dp, f), stat.S_IWRITE)
        shutil.rmtree(t, ignore_errors=True)
    print("PASS test_build_readonly")


if __name__ == "__main__":
    main()
