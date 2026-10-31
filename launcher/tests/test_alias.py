"""test_alias.py - how BUILD MASHUP reaches a build folder whose path has spaces / non-ASCII characters (E16 fix).

    py -3 -B launcher\\tests\\test_alias.py OUT.json
Fast (no build, no network, nothing launched; writes only temporary folders). Cases: a plain path is used directly; a path with spaces +
non-ASCII characters gets a junction in the first candidate folder where the junction AND folder make / rename / replace / remove
THROUGH it work; a candidate whose probe fails is skipped and its junction removed again; a candidate folder whose parents do not
exist yet is created; an existing junction to the same folder is reused, one to another folder is replaced, a real folder at the junction
name is never touched; a candidate where junctions cannot be made (a file in the way) or where the user may not create folders (an
ACL deny on a test folder) is skipped; all candidates failing -> REFUSED naming each reason, nothing left behind; --alias-root tries only
that folder; remove-build-dir unlinks the build folder's own junction (never its target); no elevation in the launcher code.
Optional BM_TEST_REAL_ALIAS=1: also probe the REAL default candidates of this PC (%LOCALAPPDATA%\\BurnoutMashup\\links,
%ProgramData%\\BurnoutMashup\\links, C:\\BMashup-links) with a temporary build folder and report which one is used (the junction
made is removed again). Exit 0 = all PASS."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

REAL_ENV = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "ProgramData", "SystemDrive", "USERNAME")}
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402  (sandboxed %APPDATA% / %LOCALAPPDATA% for this process)
SRC = pubfix.SRC
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmbuild  # noqa: E402

RES = {}
INFO = {}
NAME = "Build Mashup \u00e9t\u00e9 \u00df"         # spaces + non-ASCII


def case(fn):
    try:
        r = fn()
        RES[fn.__name__] = "PASS" if r is None else r
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def plain_tmp(tag):
    d = tempfile.mkdtemp(prefix="bmal" + tag)
    assert bmbuild.is_plain(d), d
    return d


def target():
    t = os.path.join(tempfile.mkdtemp(prefix="bm alias t "), NAME)
    os.makedirs(t)
    return t


def links_in(root):
    return [os.path.join(root, x) for x in os.listdir(root)] if os.path.isdir(root) else []


@case
def plain_path_is_direct():
    d = plain_tmp("p")
    p, how = bmbuild.ascii_alias(d)
    assert p == d and how == "direct", (p, how)


@case
def junction_in_first_working_root():
    t = target()
    r1, r2 = os.path.join(plain_tmp("a"), "links"), os.path.join(plain_tmp("b"), "links")
    p, how = bmbuild.ascii_alias(t, roots=[r1, r2])
    assert os.path.dirname(p) == r1 and bmbuild.is_link(p), (p, how)
    assert os.path.normcase(os.path.realpath(p)) == os.path.normcase(os.path.realpath(t))
    assert not [x for x in os.listdir(t) if x.startswith("_aliasprobe")], os.listdir(t)
    # the build steps' operations through the junction
    os.makedirs(os.path.join(p, "s1_fetch", "takedawn.partial"))
    os.rename(os.path.join(p, "s1_fetch", "takedawn.partial"), os.path.join(p, "s1_fetch", "takedawn"))
    assert os.path.isdir(os.path.join(t, "s1_fetch", "takedawn"))
    assert links_in(r2) == []


@case
def failing_probe_falls_through_and_cleans():
    t = target()
    r1, r2 = os.path.join(plain_tmp("a"), "links"), os.path.join(plain_tmp("b"), "links")
    os.environ["BMBUILD_FAULT_ALIAS"] = r1
    try:
        p, how = bmbuild.ascii_alias(t, roots=[r1, r2])
    finally:
        del os.environ["BMBUILD_FAULT_ALIAS"]
    assert os.path.dirname(p) == r2, (p, how)
    assert "not usable" in how and r1 in how and "fault injected" in how, how
    assert links_in(r1) == [], links_in(r1)                 # the refused junction was removed
    assert os.path.isdir(t)                                  # its target (the build folder) is untouched


@case
def absent_parent_folders_are_created():
    t = target()
    r = os.path.join(plain_tmp("n"), "not", "yet", "there")
    p, how = bmbuild.ascii_alias(t, roots=[r])
    assert os.path.dirname(p) == r and bmbuild.is_link(p), (p, how)


@case
def existing_junction_same_target_reused():
    t = target()
    r = os.path.join(plain_tmp("e"), "links")
    p1, _ = bmbuild.ascii_alias(t, roots=[r])
    open(os.path.join(t, "marker.txt"), "w").write("kept")
    p2, how = bmbuild.ascii_alias(t, roots=[r])
    assert p1 == p2 and os.path.isfile(os.path.join(p2, "marker.txt")), (p1, p2, how)


@case
def existing_junction_elsewhere_replaced():
    t, other = target(), target()
    r = os.path.join(plain_tmp("x"), "links")
    p, _ = bmbuild.ascii_alias(t, roots=[r])
    os.rmdir(p)
    import _winapi
    _winapi.CreateJunction(other, p)                         # stale: same name, other folder
    open(os.path.join(other, "other.txt"), "w").write("other")
    p2, how = bmbuild.ascii_alias(t, roots=[r])
    assert p2 == p and os.path.normcase(os.path.realpath(p2)) == os.path.normcase(os.path.realpath(t)), (p2, how)
    assert os.path.isfile(os.path.join(other, "other.txt"))  # the other folder is untouched


@case
def real_folder_at_link_name_untouched():
    t = target()
    r1, r2 = os.path.join(plain_tmp("f"), "links"), os.path.join(plain_tmp("g"), "links")
    name = "b-" + bmbuild.sha_b(os.path.normcase(t).encode("utf-8"))[:12]
    os.makedirs(os.path.join(r1, name))
    open(os.path.join(r1, name, "user.txt"), "w").write("mine")
    p, how = bmbuild.ascii_alias(t, roots=[r1, r2])
    assert os.path.dirname(p) == r2, (p, how)
    assert open(os.path.join(r1, name, "user.txt")).read() == "mine" and not bmbuild.is_link(os.path.join(r1, name))
    assert "not a junction" in how, how


@case
def junction_impossible_skipped():
    t = target()
    base = plain_tmp("j")
    r1 = os.path.join(base, "links")
    open(r1, "w").write("a FILE where the folder would be")     # makedirs / CreateJunction cannot work here
    r2 = os.path.join(plain_tmp("k"), "links")
    p, how = bmbuild.ascii_alias(t, roots=[r1, r2])
    assert os.path.dirname(p) == r2 and "junction not made" in how, (p, how)


@case
def no_permission_root_skipped():
    """a folder where this user may not create anything (an explicit ACL deny on a TEST folder; removed afterwards)"""
    t = target()
    base = plain_tmp("q")
    r1 = os.path.join(base, "denied")
    os.makedirs(r1)
    user = REAL_ENV.get("USERNAME") or os.environ.get("USERNAME")
    ic = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icacls.exe")
    rc = subprocess.run([ic, r1, "/deny", "%s:(OI)(CI)(AD,WD)" % user], capture_output=True, text=True).returncode
    if rc:
        return "SKIP: icacls deny not possible here"
    try:
        r2 = os.path.join(plain_tmp("r"), "links")
        p, how = bmbuild.ascii_alias(t, roots=[os.path.join(r1, "links"), r2])
        assert os.path.dirname(p) == r2 and "junction not made" in how, (p, how)
    finally:
        subprocess.run([ic, r1, "/remove:d", user], capture_output=True)


@case
def all_fail_refused_nothing_left():
    t = target()
    r1, r2 = os.path.join(plain_tmp("s"), "links"), os.path.join(plain_tmp("u"), "links")
    os.environ["BMBUILD_FAULT_ALIAS"] = r1 + ";" + r2
    try:
        bmbuild.ascii_alias(t, mode="junction", roots=[r1, r2])
        raise AssertionError("not refused")
    except bmbuild.Refused as e:
        msg = str(e)
        assert r1 in msg and r2 in msg and "--alias-root" in msg, msg
    finally:
        del os.environ["BMBUILD_FAULT_ALIAS"]
    assert links_in(r1) == [] and links_in(r2) == [], (links_in(r1), links_in(r2))
    assert os.listdir(t) == [], os.listdir(t)


@case
def alias_root_only_that_folder():
    t = target()
    r = os.path.join(plain_tmp("v"), "mine")
    os.environ["BMBUILD_FAULT_ALIAS"] = r
    try:
        bmbuild.ascii_alias(t, alias_root=r)
        raise AssertionError("not refused")
    except bmbuild.Refused as e:
        assert r in str(e) and "8.3" not in str(e), str(e)
    finally:
        del os.environ["BMBUILD_FAULT_ALIAS"]
    p, how = bmbuild.ascii_alias(t, alias_root=r)
    assert os.path.dirname(p) == r, (p, how)


@case
def non_plain_root_skipped():
    t = target()
    r1 = os.path.join(tempfile.mkdtemp(prefix="bm al "), "links \u00e9")
    r2 = os.path.join(plain_tmp("w"), "links")
    p, how = bmbuild.ascii_alias(t, roots=[r1, r2])
    assert os.path.dirname(p) == r2 and "not a plain ASCII path" in how, (p, how)


@case
def remove_build_dir_unlinks_own_junction():
    t = target()
    r = os.path.join(plain_tmp("y"), "links")
    p, how = bmbuild.ascii_alias(t, roots=[r])
    keep = target()
    open(os.path.join(keep, "toolchain.txt"), "w").write("tool")
    import _winapi
    _winapi.CreateJunction(keep, os.path.join(t, "toolchain_view"))
    bmbuild.jsave(os.path.join(t, "BUILD_STATE.json"), {"format": "bm-build-state 1", "alias": {"path": p, "how": how}})
    r2 = bmbuild.remove_build_dir(t, yes=True, out=lambda s: None)
    assert r2["removed"] and r2["junctions"] == 2, r2
    assert not os.path.lexists(p) and not os.path.exists(t), (p, t)
    assert open(os.path.join(keep, "toolchain.txt")).read() == "tool"   # a junction's target is never entered


@case
def default_roots_never_temp_and_plain_order():
    roots = bmbuild.alias_roots()
    tmpd = os.path.normcase(tempfile.gettempdir())
    assert len(roots) == 3 and roots[0].endswith(os.path.join("BurnoutMashup", "links")), roots
    assert all(not os.path.normcase(r).startswith(tmpd) or os.path.normcase(r).startswith(os.path.normcase(pubfix.SANDBOX))
               for r in roots), roots


@case
def no_elevation_in_launcher_code():
    hits = []
    for dp, dn, fn in os.walk(os.path.join(SRC, "tools")):
        for f in fn:
            if f.endswith((".py", ".cmd", ".ps1")):
                s = open(os.path.join(dp, f), encoding="utf-8", errors="replace").read()
                for pat in (r"\brunas\b", r"ShellExecute", r"Start-Process[^\n]*-Verb", r"SeCreateSymbolicLink", r"os\.symlink"):
                    if re.search(pat, s, re.I):
                        hits.append("%s: %s" % (f, pat))
    assert not hits, hits


@case
def real_default_candidates_this_pc():
    if os.environ.get("BM_TEST_REAL_ALIAS") != "1":
        return "SKIP: set BM_TEST_REAL_ALIAS=1 to probe the real candidate folders of this PC"
    saved = {k: os.environ.get(k) for k in REAL_ENV}
    for k, v in REAL_ENV.items():
        if v:
            os.environ[k] = v
    t = target()
    try:
        roots = bmbuild.alias_roots()
        per = {}
        for r in roots:
            try:
                p, how = bmbuild.ascii_alias(t, mode="junction", roots=[r])
                per[r] = "usable"
                os.rmdir(p)
            except bmbuild.Refused as e:
                per[r] = "refused: " + str(e).split("(", 1)[-1][:300]
        p, how = bmbuild.ascii_alias(t)
        INFO["real_candidates"] = per
        INFO["real_chosen"] = how
        os.rmdir(p)
        assert any(v == "usable" for v in per.values()), per
        assert os.path.dirname(p) == next(r for r in roots if per[r] == "usable"), (p, per)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    json.dump({"results": RES, "info": INFO}, open(sys.argv[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    bad = {k: v for k, v in RES.items() if not str(v).startswith(("PASS", "SKIP"))}
    print(json.dumps({"cases": len(RES), "failed": bad, "skipped": [k for k, v in RES.items() if str(v).startswith("SKIP")],
                      "info": INFO}, ensure_ascii=True))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
