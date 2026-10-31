"""test_isolation.py - the launcher never reads or writes a separate Takedawn install's folders.

    py -3 -B tests\\test_isolation.py OUT.json

A FAKE %APPDATA%\\Takedawn and %LOCALAPPDATA%\\Takedawn are made in temporary folders (the real ones are never used: the test process
and every child get APPDATA / LOCALAPPDATA pointing at the fake environment) and filled with files that carry sentinel strings:
plugin approvals (one stale, one for a mod that is installed), plugin settings, a mod list that disables the test plugin, saves,
settings, a log that says the plugin is running, a game folder, shader cache. Then every launcher operation runs against a
temporary bundle: prepare (status / data / auto / preflight), play.cmd --print-env, remove.cmd and tools\\uninstall.py (list, backup,
verify, upgrade, repair, clean), diag.cmd and tools\\bmdiag.py, and the mod operations (preview, import of a folder and of a zip,
list, stale-profile check, results, turn off / on). For each:
  - the whole fake environment is byte-identical afterwards (names, sizes, sha256, modification times) and no BurnoutMashup folder
    was created in it;
  - the Python tools run under audited.py: not one open / listdir / scandir / remove / rename / mkdir / copy of a path below a
    fake Takedawn folder was logged (the cmd entry points run without the hook; their effect is covered by the snapshot);
  - no sentinel string appears in any output, diagnostics zip or file the operation produced;
  - the operations use the bundle's OWN approvals / mod list (profile\\Roaming\\BurnoutMashup): the Takedawn approvals are not consulted
    (the stale check is empty, the plugin is not shown as disabled or running).
The detector itself is tested first (a tool that does read the fake approvals IS caught). Nothing is launched; no game files."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402

SRC = pubfix.SRC
AUDITED = os.path.join(HERE, "audited.py")
OPS = os.path.join(HERE, "isolation_ops.py")
SENT = "TAKEDAWN-SENTINEL"
RES = {}


def case(fn):
    try:
        fn()
        RES[fn.__name__] = "PASS"
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, traceback.format_exc().splitlines()[-3].strip())
    return fn


# ------------------------------------------------------------------------------------------------------ fake Takedawn environment
class Fake:
    def __init__(self):
        self.base = tempfile.mkdtemp(prefix="bm fake env ")
        self.roaming = os.path.join(self.base, "Roaming")
        self.local = os.path.join(self.base, "Local")
        self.td_r = os.path.join(self.roaming, "Takedawn")
        self.td_l = os.path.join(self.local, "Takedawn")
        s = lambda tag: "# %s-%s\n" % (SENT, tag)
        files = {
            (self.td_r, "plugin-approvals.toml"): 'approved = ["a.plug sha256:%s", "a.gone sha256:%s"]\n' % ("2" * 64, "3" * 64) + s("APPROVALS"),
            (self.td_r, "plugin-settings.toml"): 'values = [\n "a.gone/x = on",\n]\n' + s("PSETTINGS"),
            (self.td_r, "mod-list.toml"): 'disabled = ["a.plug"]\n' + s("MODLIST"),
            (self.td_r, "settings.toml"): "x = 1\n" + s("SETTINGS"),
            (self.td_r, os.path.join("UDATA", "4541005b", "save.xbx")): (SENT + "-SAVE").encode() * 40,
            (self.td_r, os.path.join("logs", "run.log")): "[PLUGIN] a.plug: running (plugin API 1)\n[MOD] mod a.plug 1.0: x\n" + s("LOG"),
            (self.td_l, os.path.join("Game", "Burnout 3 Takedown", "default.xbe")): b"XBEH " + (SENT + "-GAME").encode(),
            (self.td_l, os.path.join("Game", ".complete")): "xr-install 1\n" + s("COMPLETE"),
            (self.td_l, os.path.join("shaders", "upscale", "x.glsl")): s("SHADER"),
            (self.td_l, os.path.join("cache", "c.bin")): (SENT + "-CACHE").encode(),
        }
        for (root, rel), data in files.items():
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(data if isinstance(data, bytes) else data.encode("utf-8"))
        self.before = self.snapshot()

    def snapshot(self):
        out = {}
        for dp, dn, fn in os.walk(self.base):
            for d in dn:
                out[os.path.relpath(os.path.join(dp, d), self.base) + "\\"] = "dir"
            for f in fn:
                p = os.path.join(dp, f)
                st = os.stat(p)
                out[os.path.relpath(p, self.base)] = (st.st_size, st.st_mtime_ns, hashlib.sha256(open(p, "rb").read()).hexdigest())
        return out

    def unchanged(self):
        now = self.snapshot()
        diff = sorted(k for k in set(now) | set(self.before) if now.get(k) != self.before.get(k))
        assert not diff, "the fake Takedawn environment changed: %s" % diff[:8]
        assert not os.path.exists(os.path.join(self.roaming, "BurnoutMashup")) and not os.path.exists(os.path.join(self.local, "BurnoutMashup")), \
            "a BurnoutMashup folder was created in %APPDATA% / %LOCALAPPDATA%"

    def env(self, log):
        e = {k: v for k, v in os.environ.items() if not k.upper().startswith(("TAKEDAWN_", "BMASHUP_", "RECOMP_", "BO3_"))}
        e.update(APPDATA=self.roaming, LOCALAPPDATA=self.local, BM_AUDIT_LOG=log, PYTHONDONTWRITEBYTECODE="1")
        e.pop("PYTHONPATH", None)
        return e

    def violations(self, log):
        fk = [os.path.normcase(os.path.abspath(p)) for p in (self.td_r, self.td_l)]
        bad = []
        if os.path.isfile(log):
            for ln in open(log, encoding="utf-8", errors="replace"):
                ev, _, p = ln.rstrip("\n").partition("\t")
                n = os.path.normcase(os.path.abspath(p))
                if any(n == f or n.startswith(f + os.sep) for f in fk):
                    bad.append(ln.strip())
        return bad


# ------------------------------------------------------------------------------------------------------ bundles
def bundle(tag, with_data=True):
    root = os.path.join(tempfile.mkdtemp(prefix="bm iso "), "Bündel mit Leerzeichen %s" % tag)
    os.makedirs(os.path.join(root, "host"))
    open(os.path.join(root, "host", "burnout3_bmashup.exe"), "wb").write(b"MZ stand-in")
    shutil.copy2(pubfix.INFO, os.path.join(root, "host", "HOST_INFO.json"))
    shutil.copytree(os.path.join(SRC, "tools"), os.path.join(root, "tools"))
    for f in os.listdir(SRC):
        if f.lower().endswith(".cmd"):
            shutil.copy2(os.path.join(SRC, f), root)
    os.makedirs(os.path.join(root, "gamedata"))
    open(os.path.join(root, "gamedata", ".complete"), "w").write("xr-install 1\n")
    open(os.path.join(root, "BUNDLE.json"), "w").write('{"bundle": "test"}')
    shipped = {"README.txt": b"readme", os.path.join("docs", "A.md"): b"doc a"}
    for rel, data in shipped.items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)) or root, exist_ok=True)
        open(os.path.join(root, rel), "wb").write(data)
    with open(os.path.join(root, "SHA256SUMS.txt"), "w") as f:
        for rel, data in sorted(shipped.items()):
            f.write("%s  %s\n" % (hashlib.sha256(data).hexdigest(), rel.replace(os.sep, "/")))
    mod = os.path.join(root, "mods", "user", "a.plug")
    os.makedirs(mod)
    open(os.path.join(mod, "mod.toml"), "w").write('id = "a.plug"\nname = "a.plug"\nversion = "1.0.0"\n[plugin]\napi = 1\nwindows = "p.asi"\n')
    open(os.path.join(mod, "p.asi"), "wb").write(b"MZ v1")
    if with_data:
        t = os.path.join(root, "profile", "Roaming", pubfix.IDENT)
        os.makedirs(os.path.join(t, "UDATA", "4541005b"))
        open(os.path.join(t, "UDATA", "4541005b", "save.xbx"), "wb").write(b"SAVE" * 100)
        open(os.path.join(t, "settings.toml"), "w").write("x = 1\n")
        os.makedirs(os.path.join(root, "work"))
        open(os.path.join(root, "work", "f.bin"), "wb").write(b"x")
    return root


def stub_game():
    src = os.path.join(tempfile.mkdtemp(prefix="bm src "), "Installed Game")
    os.makedirs(os.path.join(src, "Burnout 3 Takedown", "Data"))
    open(os.path.join(src, "Burnout 3 Takedown", "default.xbe"), "wb").write(b"XBEH" + b"\0" * 100)
    open(os.path.join(src, "Burnout 3 Takedown", "Data", "a.bin"), "wb").write(b"x" * 1000)
    open(os.path.join(src, ".complete"), "w").write("xr-install 1\nmanifest 81dc20fd647fb0b1\n")
    return src


def new_mod_sources():
    t = tempfile.mkdtemp(prefix="bm modsrc ")
    f = os.path.join(t, "My Mod ä")
    os.makedirs(f)
    open(os.path.join(f, "mod.toml"), "w", encoding="utf-8").write('id = "a.two"\nname = "a.two"\nversion = "1.0.0"\n')
    z = os.path.join(t, "mod.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a-two/mod.toml", 'id = "a.two"\nname = "a.two"\nversion = "2.0.0"\n')
    return f, z


# ------------------------------------------------------------------------------------------------------ runners
def decode_console(b):
    """cmd.exe's echo writes in the console's code page: UTF-8 only when the caller's console is set to 65001. A process without a
    console (a detached / hidden test driver) gets a new console with the OEM code page (e.g. 850), so a non-ASCII folder name arrives
    in that code page (phase 13/14 finding E17). Decode as UTF-8 when the bytes are valid UTF-8, else with the console / OEM code page."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetConsoleOutputCP() or ctypes.windll.kernel32.GetOEMCP()
        return b.decode("cp%d" % cp, "replace")
    except (AttributeError, OSError, LookupError):
        return b.decode("utf-8", "replace")


class Ctx:
    """one fake environment + audit log + collected outputs for one case"""

    def __init__(self):
        self.fake = Fake()
        self.log = os.path.join(tempfile.mkdtemp(prefix="bm audit "), "audit.log")
        self.out = []          # (label, rc, text)

    def py(self, script_and_args, cwd, label):
        r = subprocess.run([sys.executable, "-B", AUDITED] + [str(a) for a in script_and_args], capture_output=True, env=self.fake.env(self.log),
                           cwd=cwd, timeout=300)
        txt = (r.stdout + b"\n" + r.stderr).decode("utf-8", "replace")
        self.out.append((label, r.returncode, txt))
        return r.returncode, txt

    def cmd(self, cmdfile, args, cwd, label):
        r = subprocess.run('"%s" %s' % (cmdfile, args), shell=True, capture_output=True, env=self.fake.env(self.log), cwd=cwd, timeout=300)
        txt = decode_console(r.stdout + b"\n" + r.stderr)
        self.out.append((label, r.returncode, txt))
        return r.returncode, txt

    def finish(self, roots=()):
        """the common assertions of every operation case"""
        self.fake.unchanged()
        bad = self.fake.violations(self.log)
        assert not bad, "a tool touched a fake Takedawn path: %s" % bad[:5]
        assert os.path.isfile(self.log) and os.path.getsize(self.log) > 0 or not any(lbl.startswith("py:") for lbl, _, _ in self.out), "audit log is empty"
        for label, rc, txt in self.out:
            assert SENT not in txt, "sentinel of the fake Takedawn folders in the output of %s" % label
        for root in roots:
            for dp, dn, fn in os.walk(root):
                for f in fn:
                    p = os.path.join(dp, f)
                    if os.path.getsize(p) < 5_000_000:
                        data = open(p, "rb").read()
                        assert SENT.encode() not in data, "sentinel copied into %s" % p
                        if f.lower().endswith(".zip"):
                            with zipfile.ZipFile(p) as z:
                                for n in z.namelist():
                                    assert SENT.encode() not in z.read(n), "sentinel in %s!%s" % (p, n)


# ------------------------------------------------------------------------------------------------------ cases
@case
def detector_catches_a_read():
    """self-test: the audit hook and the snapshot DO notice a read / a change of the fake folders"""
    c = Ctx()
    probe = os.path.join(tempfile.mkdtemp(prefix="bm probe "), "probe.py")
    open(probe, "w").write("import os, sys\nopen(os.path.join(os.environ['APPDATA'], 'Takedawn', 'plugin-approvals.toml'), 'rb').read()\n"
                           "os.listdir(os.path.join(os.environ['LOCALAPPDATA'], 'Takedawn'))\n")
    rc, _ = c.py([probe], tempfile.gettempdir(), "py:probe")
    v = c.fake.violations(c.log)
    assert rc == 0 and len(v) >= 2 and any(x.startswith("open") for x in v) and any(x.startswith("os.listdir") for x in v), v
    p = os.path.join(c.fake.td_r, "settings.toml")
    open(p, "a").write("x")
    try:
        c.fake.unchanged()
        raise AssertionError("a change of the fake folders was not detected")
    except AssertionError as e:
        assert "changed" in str(e), e


@case
def prepare_leaves_takedawn_alone():
    c = Ctx()
    root = bundle("prep", with_data=False)
    src = stub_game()
    c.py([os.path.join(root, "tools", "prepare.py"), "status"], root, "py:prepare status")
    c.py([os.path.join(root, "tools", "prepare.py"), "data", "--copy-from", src], root, "py:prepare data --copy-from")
    c.py([os.path.join(root, "tools", "prepare.py"), "auto", src], root, "py:prepare auto")
    c.py([os.path.join(root, "tools", "preflight.py")], root, "py:preflight")
    c.cmd(os.path.join(root, "prepare.cmd"), "status", root, "cmd:prepare.cmd status")
    assert c.out[0][1] == 0, c.out[0]
    c.finish([root])


@case
def play_print_env_uses_bundle_profile():
    c = Ctx()
    root = bundle("play")
    rc, txt = c.cmd(os.path.join(root, "play.cmd"), "--print-env", root, "cmd:play.cmd --print-env")
    assert rc == 0, txt
    env = dict(ln.split("=", 1) for ln in txt.splitlines() if "=" in ln)
    prof = os.path.normcase(os.path.join(root, "profile"))
    assert os.path.normcase(env["APPDATA"]).startswith(prof) and os.path.normcase(env["LOCALAPPDATA"]).startswith(prof), env
    assert pubfix.IDENT in env["LOG"] and "Takedawn" not in env["LOG"], env["LOG"]
    assert env["BMASHUP_DATA"].startswith(root) and all(x.startswith(root) for x in env["BMASHUP_MODS"].split(";")), env
    for k in ("APPDATA", "LOCALAPPDATA", "BMASHUP_DATA", "BMASHUP_MODS", "LOG", "EXE", "CWD"):
        assert c.fake.base not in env[k], (k, env[k])
    c.finish([root])


@case
def remove_and_uninstall_leave_takedawn_alone():
    c = Ctx()
    root, old, new = bundle("rm"), bundle("old"), bundle("new", with_data=False)
    inv = os.path.join(root, "tools", "uninstall.py")
    bk = tempfile.mkdtemp(prefix="bm bk ")
    bk2 = tempfile.mkdtemp(prefix="bm bk2 ")      # phase 9: a backup folder is named by the SECOND (bmashup-backup-YYYYMMDD-HHMMSS): two backups into one folder
                                                  # within one second collide (the tool refuses, nothing changes). The clean step therefore uses its own folder.
    c.py([inv, "list"], root, "py:uninstall list")
    c.py([inv, "backup", "--to", bk], root, "py:uninstall backup")
    c.py([inv, "verify"], root, "py:uninstall verify")
    c.py([os.path.join(new, "tools", "uninstall.py"), "upgrade", "--from", old], new, "py:uninstall upgrade")
    c.py([inv, "repair", "--from", new], root, "py:uninstall repair")
    c.cmd(os.path.join(root, "remove.cmd"), "list", root, "cmd:remove.cmd list")
    rc, txt = c.py([inv, "clean", "--yes"], root, "py:uninstall clean")
    assert rc == 0, txt
    assert os.path.isfile(os.path.join(root, "profile", "Roaming", pubfix.IDENT, "UDATA", "4541005b", "save.xbx")), "my data must stay"
    rc, txt = c.py([inv, "clean", "--yes", "--remove-my-data", "--backup-to", bk2], root, "py:uninstall clean --remove-my-data")
    assert rc == 0, txt
    c.finish([root, old, new, bk, bk2])


@case
def diag_leaves_takedawn_alone():
    c = Ctx()
    root = bundle("diag")
    out = os.path.join(tempfile.mkdtemp(prefix="bm dg "), "diag1.zip")
    rc, txt = c.py([os.path.join(root, "tools", "bmdiag.py"), "--bundle", root, "--out", out], root, "py:bmdiag")
    assert rc == 0 and os.path.isfile(out), txt
    out2 = os.path.join(os.path.dirname(out), "diag2.zip")
    rc, txt = c.cmd(os.path.join(root, "diag.cmd"), '--bundle "%s" --out "%s"' % (root, out2), root, "cmd:diag.cmd")
    assert rc == 0 and os.path.isfile(out2), txt
    c.finish([root, os.path.dirname(out)])


@case
def mod_operations_ignore_takedawn_approvals():
    c = Ctx()
    root = bundle("mods")
    folder, z = new_mod_sources()
    rc, txt = c.py([OPS, root, folder, z], root, "py:isolation_ops")
    assert rc == 0, txt
    j = json.loads(txt.strip().splitlines()[-1])
    assert os.path.normcase(j["approvals_path"]).startswith(os.path.normcase(root)) and pubfix.IDENT in j["approvals_path"], j["approvals_path"]
    assert "Takedawn" not in j["approvals_path"] and "Takedawn" not in j["settings_dir"]
    assert j["stale"] == [], "the Takedawn approvals / settings were consulted: %s" % j["stale"]
    assert j["results"]["found"] is False and j["results"]["plugins_running"] == [], j["results"]
    plug = [m for m in j["mods"] if m["id"] == "a.plug"][0]
    assert plug["enabled"] is True and plug["native_code"] is True, plug      # the Takedawn mod list (disabled a.plug) is not applied
    assert j["off"] == ["a.plug"] and j["on"] == [], j
    assert os.path.isfile(os.path.join(root, "profile", "Roaming", pubfix.IDENT, "mod-list.toml"))
    assert [m["id"] for m in j["mods"] if m["id"] == "a.two"] == ["a.two"]
    c.finish([root])


@case
def launcher_sources_name_no_takedawn_folder():
    """text check: no launcher source builds a path below %APPDATA%\\Takedawn / %LOCALAPPDATA%\\Takedawn (messages and the preflight's
    'is the bundle inside it' comparison are allowed: those do not open anything)"""
    bad = []
    for dp, dn, fn in os.walk(os.path.join(SRC, "tools")):
        for f in fn:
            if f.endswith((".py", ".pyw")):
                for i, ln in enumerate(open(os.path.join(dp, f), encoding="utf-8", errors="replace"), 1):
                    s = ln.strip()
                    if s.startswith("#"):
                        continue
                    if ("'Takedawn'" in s or '"Takedawn"' in s) and ("join" in s or "open(" in s) and f != "preflight.py":
                        bad.append("%s:%d: %s" % (f, i, s[:100]))
    assert not bad, bad


def main():
    json.dump(RES, open(sys.argv[1], "w"), indent=1)
    bad = {k: v for k, v in RES.items() if v != "PASS"}
    print(json.dumps({"cases": len(RES), "failed": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
