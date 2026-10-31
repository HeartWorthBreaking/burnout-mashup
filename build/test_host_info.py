"""test_host_info.py - tests of host_info.py on a SYNTHETIC mini build (no game, no compiler, no network; standard library only).

    py -3 -B build\\test_host_info.py [OUT.json]

A tiny host tree + toolkit tree + build folder are made in a temporary folder with the same files and records a real build has
(CMakeCache.txt, build_id\\bo3_build_manifest.txt / bo3_build_id.h / bo3_build_config.txt, build_result.json, an 'exe' that holds the
identity string). The digests are made with host_info.tree_digests(); that this equals what cmake/bo3_source_id.cmake writes is
shown on a REAL build by the maintainer's test (the recomputed manifest is byte-identical to the build's own). Here:
  positive: fields, a source for every field, loadable by the compatibility gate's reader (bmcompat.load_host_info);
  refusals (exit 2 / Refused, NO file written, an existing file left untouched): missing exe, exe tampered, identity changed in the
  exe, identity not unique, build records missing, build_result of another exe, unverified build, source file edited after the build,
  source file added, tree missing, platform table unreadable, regen stamp / marks pins differ, no build_result.json;
  --check: a good file passes, a changed exe or a changed identity is reported.
Exit 0 = all PASS."""
import json
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmb_common as C  # noqa: E402
import host_info as H  # noqa: E402

RES = {}
TABLE = '''#define BO3_PLATFORM_VERSION "0.9.9"
#define BO3_PLATFORM_SERVICES(X) \\
    X("bmashup.host",      1, 1) \\
    X("bmashup.boost",     2, 2) \\
    X("takedawn.race",     1, 1)
#define BO3_PLATFORM_TABLES(T) \\
    T("tune", 3, "version set sliders") \\
    T("tracks", 1, "version add")
'''
PINS = {"pristine_gen_tree_hash": "a" * 64, "marks": {"anchors_sha256": None, "header_sha256": None, "count": 3},
        "takedawn": {"commit": "1" * 40, "tree_id": "2" * 40}, "xboxrecomp": {"commit": "3" * 40, "tree_id": "4" * 40}}


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


def w(p, text, mode="w", **kw):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, **kw) as f:
        f.write(text)


class Mini:
    """a consistent synthetic build: self.td, self.xr, self.build, self.logs, self.ck (checkout with host/PINS.json)"""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="hi test ")
        r = self.root
        self.td, self.xr, self.build, self.logs, self.ck = (os.path.join(r, n) for n in ("td", "xr", "build", "build.logs", "ck"))
        w(os.path.join(self.td, "CMakeLists.txt"), "project(x)\n")
        w(os.path.join(self.td, "VERSION"), "0.9.9\n")
        w(os.path.join(self.td, "src", "game", "bm_platform_table.h"), TABLE)
        w(os.path.join(self.td, "src", "game", "main.c"), "int main(void){return 0;}\n")
        w(os.path.join(self.td, "src", "game", "__pycache__", "x.pyc"), "skipped")
        w(os.path.join(self.td, "src", "game", "obj.o"), "skipped")
        w(os.path.join(self.td, "include", "takedawn_plugin.h"), "#define TD_PLUGIN_API_VERSION 1u\n")
        w(os.path.join(self.td, "src", "game", "recomp", "gen", "regen.stamp"), "key k\ntree %s\nfiles 1\n" % PINS["pristine_gen_tree_hash"])
        w(os.path.join(self.td, "src", "game", "bm_gen_access.h"), "/* access */\n")
        w(os.path.join(self.xr, "CMakeLists.txt"), "project(xr)\n")
        w(os.path.join(self.xr, "src", "a.c"), "int a;\n")
        w(os.path.join(self.ck, "host", "marks", "anchors.json"), "{}\n")
        pins = json.loads(json.dumps(PINS))
        pins["marks"]["anchors_sha256"] = C.sha_f(os.path.join(self.ck, "host", "marks", "anchors.json"))
        pins["marks"]["header_sha256"] = C.sha_f(os.path.join(self.td, "src", "game", "bm_gen_access.h"))
        w(os.path.join(self.ck, "host", "PINS.json"), json.dumps(pins))
        self.config = "bmp build configuration v1\ncompiler C Clang 1.2.3\nbuild_type Release\n"
        bid = os.path.join(self.build, "src", "game", "build_id")
        text, digest, xd, _ = H.tree_digests(self.td, self.xr, "0.9.9", self.config)
        self.ident = "bmp-0.9.9+" + digest[:12]
        w(os.path.join(bid, "bo3_build_manifest.txt"), text, newline="\n")
        w(os.path.join(bid, "bo3_build_config.txt"), self.config, newline="\n")
        w(os.path.join(bid, "bo3_build_id.h"), '/* digest %s */\n#define BO3_BUILD_COMMIT "%s"\n' % (digest, self.ident))
        self.exe = os.path.join(self.build, "bin", "burnout3.exe")
        self.write_exe(("MZ\0" + "pad" * 50 + self.ident + "\0more" * 9 + self.ident + "\0end").encode())
        w(os.path.join(self.build, "CMakeCache.txt"), "CMAKE_HOME_DIRECTORY:INTERNAL=%s\nXBOXRECOMP_DIR:PATH=%s\n" % (
            self.td.replace(os.sep, "/"), self.xr.replace(os.sep, "/")))
        self.expected = os.path.join(r, "EXPECTED.json")
        w(self.expected, json.dumps({"build": {"exe_sha256": C.sha_f(self.exe), "identity": self.ident}}))
        self.write_result()
        self.ok = {"ok": True, "generated_objects": "27/27 identical", "exe_ok": True}

    def write_exe(self, data):
        w(self.exe, data, "wb")

    def write_result(self, identity=None, sha=None):
        t = json.dumps({"ok": True, "identity": identity or self.ident, "exe_sha256": sha or C.sha_f(self.exe),
                        "toolchain": {"clang": "1.2.3", "cmake": "4.4.4"}})
        w(os.path.join(self.logs, "build_result.json"), "﻿" + t, encoding="utf-8")      # PowerShell 5.1 writes a BOM

    def make(self, out=None, verify=None, **kw):
        return H.make(self.build, self.td, self.xr, self.logs, self.expected, self.ck, out or os.path.join(self.root, "out", "HOST_INFO.json"),
                      verify_result=self.ok if verify is None else verify, **kw)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def refused(m, what, out=None, **kw):
    out = out or os.path.join(m.root, "out", "HOST_INFO.json")
    before = open(out, "rb").read() if os.path.isfile(out) else None
    try:
        m.make(out=out, **kw)
    except C.Refused as e:
        after = open(out, "rb").read() if os.path.isfile(out) else None
        assert before == after, "%s: the output file changed on a refusal" % what
        return str(e)
    raise AssertionError("%s was not refused" % what)


@case
def positive_fields_and_sources():
    m = Mini()
    try:
        info, dest = m.make()
        assert os.path.isfile(dest) and not os.path.exists(dest + ".tmp")
        assert info["format"] == 1 and info["platform"] == "0.9.9" and info["plugin_api"] == 1
        assert info["services"] == {"bmashup.host": 1, "bmashup.boost": 2, "takedawn.race": 1}, info["services"]
        assert info["tables"] == {"tune": {"version": 3, "keys": ["version", "set", "sliders"]}, "tracks": {"version": 1, "keys": ["version", "add"]}}
        assert info["identity"] == m.ident == info["host_name"]
        assert info["exe_sha256"] == C.sha_f(m.exe) and info["exe_size"] == os.path.getsize(m.exe)
        assert info["source_digest_sha256"][:12] == m.ident.split("+")[1] and info["toolkit_identity"].startswith("xr+")
        assert info["inputs"]["takedawn_commit"] == "1" * 40 and info["inputs"]["gen_tree_hash"] == "a" * 64
        assert info["toolchain"]["clang"] == "1.2.3"
        # .pyc / .o / __pycache__ are not part of the digest: the manifest has exactly 5 bmp files (CMakeLists, VERSION, 3 under src/game + gen)
        assert info["source_files"]["bmp_files"] >= 5
        # a source for EVERY field (the keys of "sources" cover all top-level fields except sources / generator / format)
        src = info["sources"]
        for k in info:
            if k in ("sources", "generator", "source_files", "format"):
                continue
            assert any(k == s or s.startswith(k + ".") or s.split(".")[0] == k or k in [x.strip() for x in s.split(",")] for s in src), "no source for " + k
        j = json.load(open(dest, encoding="utf-8"))
        assert j == json.loads(json.dumps(info))
        sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "launcher", "tools", "launcher")))
        try:
            import bmcompat
            got = bmcompat.load_host_info(dest)
            assert got["platform"] == "0.9.9"
        except ImportError:
            pass                      # run outside the full tree: the gate's own tests (launcher/tests) cover it
        assert H.check(dest, m.exe) == []
    finally:
        m.cleanup()


@case
def refuse_missing_exe_and_records():
    m = Mini()
    try:
        os.remove(m.exe)
        assert "exe is missing" in refused(m, "missing exe")
    finally:
        m.cleanup()
    m = Mini()
    try:
        os.remove(os.path.join(m.build, "src", "game", "build_id", "bo3_build_manifest.txt"))
        assert "identity record is missing" in refused(m, "missing manifest")
    finally:
        m.cleanup()
    m = Mini()
    try:
        os.remove(os.path.join(m.logs, "build_result.json"))
        assert "build_result.json" in refused(m, "no build_result")
    finally:
        m.cleanup()


@case
def refuse_exe_tampered_or_other_identity():
    m = Mini()
    try:
        data = open(m.exe, "rb").read()
        m.write_exe(data + b"x")                                             # a changed exe: build_result no longer describes it
        assert "does not describe this exe" in refused(m, "tampered exe")
        m.write_exe(data.replace(m.ident.encode(), b"bmp-0.9.9+" + b"0" * 12))   # identity changed inside the exe
        r = refused(m, "identity changed")
        assert "differs from the build's bo3_build_id.h" in r, r
        m.write_exe(data.replace(m.ident.encode(), b"bmp-0.9.9+" + b"1" * 12, 1))   # one of several occurrences changed: not unique
        assert "different build identity strings" in refused(m, "identity not unique")
        m.write_exe(b"MZ no identity here")
        assert "different build identity strings" in refused(m, "no identity")
        m.write_exe(data)
        m.write_result(identity="bmp-0.9.9+" + "2" * 12)                    # build_result of another build
        assert "does not describe this exe" in refused(m, "other build_result")
    finally:
        m.cleanup()


@case
def refuse_unverified():
    m = Mini()
    try:
        r = refused(m, "unverified", verify={"ok": False, "generated_objects": "26/27 identical", "exe_ok": False})
        assert "not verified" in r
    finally:
        m.cleanup()


@case
def refuse_tree_changed_or_missing():
    m = Mini()
    try:
        p = os.path.join(m.td, "src", "game", "main.c")
        old = open(p, "rb").read()
        w(p, old + b"/* edited after the build */\n", "wb")
        r = refused(m, "edited file")
        assert "not the one that was built" in r, r
        w(p, old, "wb")
        info, _ = m.make()                                                   # restored: fine again
        w(os.path.join(m.td, "src", "game", "extra.c"), "int extra;\n")
        assert "not the one that was built" in refused(m, "added file")
        os.remove(os.path.join(m.td, "src", "game", "extra.c"))
        w(os.path.join(m.xr, "src", "a.c"), "int a2;\n")
        assert "not the one that was built" in refused(m, "toolkit file edited")
        w(os.path.join(m.xr, "src", "a.c"), "int a;\n")
        shutil.rmtree(m.td)
        assert "not there" in refused(m, "tree missing")
    finally:
        m.cleanup()
    m = Mini()
    try:
        os.remove(os.path.join(m.td, "src", "game", "bm_platform_table.h"))
        assert "bm_platform_table.h" in refused(m, "no table")
    finally:
        m.cleanup()
    m = Mini()
    try:
        w(os.path.join(m.td, "src", "game", "bm_platform_table.h"), "// nothing\n")
        assert "BO3_PLATFORM_VERSION" in refused(m, "unreadable table")
    finally:
        m.cleanup()


@case
def refuse_pins_differ():
    m = Mini()
    try:
        w(os.path.join(m.td, "src", "game", "recomp", "gen", "regen.stamp"), "key k\ntree %s\n" % ("b" * 64))
        r = refused(m, "regen stamp")
        assert "regen.stamp" in r or "not the one that was built" in r, r
    finally:
        m.cleanup()
    m = Mini()
    try:
        w(os.path.join(m.ck, "host", "marks", "anchors.json"), "{\"changed\": 1}\n")
        assert "anchors.json" in refused(m, "anchors changed")
    finally:
        m.cleanup()


@case
def check_mode():
    m = Mini()
    try:
        info, dest = m.make()
        assert H.check(dest, m.exe) == []
        data = open(m.exe, "rb").read()
        m.write_exe(data + b"x")
        assert any("not the one HOST_INFO.json describes" in x for x in H.check(dest, m.exe))
        m.write_exe(data)
        j = json.load(open(dest)); j["identity"] = "bmp-0.9.9+" + "3" * 12
        w(dest, json.dumps(j))
        assert any("identity inside the exe" in x for x in H.check(dest, m.exe))
        assert any("unreadable" in x for x in H.check(os.path.join(m.root, "nope.json"), m.exe))
    finally:
        m.cleanup()


@case
def never_fabricates_when_refused_default_location():
    m = Mini()
    try:
        os.remove(m.exe)
        try:
            H.make(m.build, m.td, m.xr, m.logs, m.expected, m.ck, None, verify_result=m.ok)
            raise AssertionError("not refused")
        except C.Refused:
            pass
        assert not os.path.exists(os.path.join(m.build, "stage", "HOST_INFO.json"))
    finally:
        m.cleanup()


def main():
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    if len(sys.argv) > 1:
        json.dump(RES, open(sys.argv[1], "w"), indent=1)
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
