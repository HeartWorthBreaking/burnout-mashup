"""test_update.py - the launcher's updater (tools/launcher/bmupdate.py, bmed25519.py, bmupdate_gui.py) without a real build: a local
mock update channel (127.0.0.1), the TEST keys of upd_testkit.py, synthetic source trees and host builds (BUILD MASHUP is replaced by
upd_testkit.fake_build, which installs through the same bmhost.install). test_update_real.py runs the same flow with real builds.

    py -3 -B launcher\\tests\\test_update.py OUT.json [--work NEW_FOLDER] [--only a,b]
NEW_FOLDER (default: a new temporary folder named with spaces and non-ASCII characters) must be outside this checkout. Exit 0 = all PASS.
Cases: rfc8032 vectors, sshsig interop with OpenSSH's ssh-keygen (SKIP when it is not installed), no channel configured (the shipped
update_channel.json), good update end to end + switch back and forward (user data untouched), tampered archive, unknown key, bad
signatures, downgrade refused + install-older, replay refused, incompatible minimum, interrupted download continued (Range) / restarted,
download failure, cancel during download, failed and cancelled build (version in use untouched), offline, upstream Takedawn refused,
unsafe archives / changed tree, no network access unless a command asks for it (socket audit hook), isolation from a fake Takedawn
install (audited.py), the Update window, and the shipped configuration trusting no key."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import upd_testkit as K  # noqa: E402
import bmed25519 as E  # noqa: E402
import bmhost  # noqa: E402
import bmupdate as U  # noqa: E402

BMU = os.path.join(SRC, "tools", "launcher", "bmupdate.py")
AUDITED = os.path.join(HERE, "audited.py")
RES = {}
W = {}
CH = None


def arg(name, default=None):
    v = sys.argv[1:]
    return v[v.index(name) + 1] if name in v else default


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def run_case(fn):
    only = arg("--only")
    if only and fn.__name__ not in only.split(","):
        return
    t0 = time.time()
    try:
        r = fn()
        RES[fn.__name__] = ("PASS" if r is None else r) + " (%.1f s)" % (time.time() - t0)
    except Exception as e:  # noqa: BLE001
        RES[fn.__name__] = "FAIL: %s | %s" % (e, " / ".join(x.strip() for x in traceback.format_exc().splitlines()[-4:-1]))
    print("%-28s %s" % (fn.__name__, RES[fn.__name__][:300]), flush=True)


class Net:
    def __enter__(self):
        U.NET["allowed"] = True

    def __exit__(self, *a):
        U.NET["allowed"] = False


def refused(cls, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except U.Refused as e:
        assert e.cls == cls, "expected %s, got %s: %s" % (cls, e.cls, e)
        return e
    raise AssertionError("not refused (expected %s)" % cls)


def tree_digest(d):
    return hashlib.sha256(U.tree_sums(U.dir_files(d)).encode()).hexdigest()


class Inst:
    """an installation: a (mini) source checkout with launcher\\ (update_channel.json, VERSION.json, host-local with a synthetic verified
    build, user data), its own update cache and its own channel paths"""

    def __init__(self, name, version="0.1.0-dev", salt="old", url=None, config=True, minimum=None):
        self.base = os.path.join(W["base"], name)
        shutil.rmtree(self.base, ignore_errors=True)
        self.repo = os.path.join(self.base, "Mashup inst \u00e9")
        self.old_identity = "bmp-0.1.9+%012x" % (abs(hash(salt)) % (1 << 48))
        K.mini_source(self.repo, version, self.old_identity, salt)
        self.L = os.path.join(self.repo, "launcher")
        self.old_sha = K.host_folder(os.path.join(self.L, "host-local"), self.old_identity, salt)
        shutil.copy2(os.path.join(self.L, "host-local", "HOST_INFO.json"), os.path.join(self.repo, "HOST_INFO.json"))
        for rel, data in (("profile/Roaming/BurnoutMashup/plugin-approvals.toml", "approved = []\n"), ("profile/Roaming/BurnoutMashup/saves/s.bin", "save"),
                          ("mods/user/m/mod.toml", "id = 'm'\n"), ("gamedata/.complete", "ok"), ("settings.toml", "x = 1\n")):
            p = os.path.join(self.L, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(data)
        self.user = self.user_digest()
        self.upd = os.path.join(self.base, "upd cache")
        self.prefix = name.replace(" ", "_") + "/"
        if config:
            K.channel_config(self.L, url or (CH.url + self.prefix), minimum=minimum)

    def user_digest(self):
        out = {}
        for sub in ("profile", "mods", "gamedata"):
            d = os.path.join(self.L, sub)
            out.update({sub + "/" + k: v for k, v in U.dir_files(d).items()})
        out["settings.toml"] = U.sha_f(os.path.join(self.L, "settings.toml"))
        return out

    def u(self, **kw):
        self.log = []
        return U.Updater(self.L, self.upd, out=self.log.append, build_fn=K.fake_build, **kw)

    def release(self, version, serial, salt, route_mode="ok", path=None, key=K.TEST_KEY, application="Burnout Mashup", pad=0, **over):
        """a new version source tree -> zip -> signed manifest, published on this installation's channel paths"""
        src = os.path.join(self.base, "rel src %s %s" % (version, serial))
        shutil.rmtree(src, ignore_errors=True)
        ident = "bmp-0.1.9+%012x" % (abs(hash(salt)) % (1 << 48))
        K.mini_source(src, version, ident, salt, application=application)
        if pad:
            open(os.path.join(src, "pad.bin"), "wb").write(os.urandom(pad))
        z = K.zip_tree(src, os.path.join(self.base, "zips", "BurnoutMashup-%s-%d-source.zip" % (version, serial)), "BurnoutMashup-%s" % version)
        data, sig = K.make_release(U, z, version, serial, "bm-test", key=key, **over)
        sub = os.path.dirname(path) + "/" if path and "/" in path else ""
        CH.routes["/" + self.prefix + sub + os.path.basename(z)] = (route_mode, open(z, "rb").read())
        CH.publish(data, sig, self.prefix + (path or "bmashup-release.json"))
        return {"zip": z, "data": data, "sig": sig, "identity": ident, "src": src,
                "sha": json.load(open(os.path.join(src, "build", "EXPECTED.json")))["build_release"]["exe_sha256"]}


def cli(*args, env=None, launcher=None, timeout=120):
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    e.update(env or {})
    r = subprocess.run([sys.executable, "-B", BMU] + list(args) + (["--launcher", launcher] if launcher else []), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=e, timeout=timeout, stdin=subprocess.DEVNULL)
    last = None
    for ln in (r.stdout + r.stderr).splitlines():
        if ln.startswith("{"):
            try:
                last = json.loads(ln)
            except ValueError:
                pass
    return r.returncode, last, r.stdout + r.stderr


# ======================================================================================================================== cases
@case
def rfc8032_vectors():
    vec = [("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
           ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
           ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7", "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
            "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a")]
    for sk, pk, msg, sig in vec:
        sk, pk, msg, sig = (bytes.fromhex(x) for x in (sk, pk, msg, sig))
        assert K.public_of(sk) == pk, "public key"
        assert K.sign(sk, msg) == sig, "signature"
        assert E.verify(pk, msg, sig), "verify"
        assert not E.verify(pk, msg + b"x", sig), "changed message accepted"
        bad = bytearray(sig)
        bad[5] ^= 1
        assert not E.verify(pk, msg, bytes(bad)), "changed R accepted"
        s = int.from_bytes(sig[32:], "little") + E.L                   # s + L: same point equation, non-canonical -> must be refused
        assert s < (1 << 256) and not E.verify(pk, msg, sig[:32] + s.to_bytes(32, "little")), "s >= L accepted"
    assert not E.verify(b"\xff" * 32, b"", b"\0" * 64) and not E.verify(b"", b"", b"")
    return "PASS 3 RFC 8032 vectors (sign + verify), mutations refused"


@case
def sshsig_interop():
    kg = shutil.which("ssh-keygen") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH", "ssh-keygen.exe")
    if not os.path.isfile(kg):
        return "SKIP (no ssh-keygen on this PC)"
    d = tempfile.mkdtemp(prefix="bm sshsig ")
    try:
        k = os.path.join(d, "k")
        subprocess.run([kg, "-q", "-t", "ed25519", "-N", "", "-C", "interop", "-f", k], check=True, capture_output=True, stdin=subprocess.DEVNULL)
        msg = os.path.join(d, "bmashup-release.json")
        open(msg, "wb").write(b'{"x": 1}\n')
        subprocess.run([kg, "-Y", "sign", "-f", k, "-n", "bmashup-update", msg], check=True, capture_output=True, stdin=subprocess.DEVNULL)
        pub = open(k + ".pub").read().strip()
        fp = E.verify_sshsig(open(msg + ".sig").read(), open(msg, "rb").read(), "bmashup-update", [pub])
        lf = subprocess.run([kg, "-l", "-f", k + ".pub"], capture_output=True, text=True).stdout.split()[1]
        assert fp == lf, (fp, lf)
        try:
            E.verify_sshsig(open(msg + ".sig").read(), b'{"x": 2}\n', "bmashup-update", [pub])
            raise AssertionError("changed file accepted")
        except E.SignatureError:
            pass
        try:
            E.verify_sshsig(open(msg + ".sig").read(), open(msg, "rb").read(), "file", [pub])
            raise AssertionError("other namespace accepted")
        except E.SignatureError:
            pass
        # our signer -> ssh-keygen accepts it (format compatibility both ways)
        open(msg + ".sig", "wb").write(K.TEST_KEY.sshsig(open(msg, "rb").read()))
        r = subprocess.run([kg, "-Y", "check-novalidate", "-n", "bmashup-update", "-s", msg + ".sig"], input=open(msg, "rb").read(), capture_output=True)
        assert r.returncode == 0, r.stdout + r.stderr
        return "PASS ssh-keygen signs -> bmed25519 verifies (fingerprint %s = ssh-keygen -l); test signer -> ssh-keygen -Y check-novalidate OK" % fp[:16]
    finally:
        shutil.rmtree(d, ignore_errors=True)


RELEASE_FP = "SHA256:tQRHolv3k/JYwlk5b3rS8fkZ3LbHWdOfyl+5eXUHnGg"


def empty_channel(launcher):
    """an update_channel.json without channel and key (what 0.1.0 shipped): 'no update channel configured'"""
    c = json.load(open(os.path.join(SRC, "update_channel.json"), encoding="utf-8"))
    c["channel"] = {"id": "", "github_repo": "", "url": ""}
    c["trusted_keys"] = []
    open(os.path.join(launcher, "update_channel.json"), "w", encoding="utf-8").write(json.dumps(c, indent=1))

@case
def no_channel():
    i = Inst("no channel", config=False)
    empty_channel(i.L)
    hits = len(CH.hits)
    rc, v, out = cli("status", launcher=i.L, env={"LOCALAPPDATA": i.base})
    assert rc == 0 and "No update channel configured" in out and v["configured"] is False and v["automatic_checks"] is False, out[-600:]
    rc, v, out = cli("check", launcher=i.L, env={"LOCALAPPDATA": i.base})
    assert rc == U.RC_NOCHANNEL and v["cls"] == "no_channel" and "update_channel.json" in v["recovery"], (rc, out[-600:])
    for c in ("download", "prepare", "build"):
        rc, v, out = cli(c, launcher=i.L, env={"LOCALAPPDATA": i.base})
        assert rc == U.RC_NOCHANNEL, (c, rc, out[-300:])
    assert len(CH.hits) == hits
    assert not os.path.exists(os.path.join(i.base, "BurnoutMashup", "updates")), "nothing may be written without a channel"
    return "PASS status / check / download / prepare / build: 'no update channel configured' (exit 6), nothing contacted or written"


@case
def good_update_flow():
    i = Inst("good flow")
    r = i.release("0.2.0", 1, "new")
    old_src = {k: v for k, v in U.dir_files(i.repo).items() if not k.startswith(("launcher/host-local", "launcher/update-state", "HOST_INFO.json"))}
    u = i.u()
    assert U.Updater(i.L, i.upd).status()["next_step"] is None
    with Net():
        c = u.check()
        assert c["verdict"] == "available" and c["version"] == "0.2.0" and c["current"] == "0.1.0-dev" and c["signer"] == K.TEST_KEY.fp, c
        assert len(c["what_happens"]) == 5 and "not touched" in c["what_happens"][-1]
        d = u.download()
    assert U.sha_f(d["archive"]) == hashlib.sha256(open(r["zip"], "rb").read()).hexdigest()
    p = u.prepare()
    assert os.path.dirname(p["source"]) == i.base and os.path.basename(p["source"]) == "BurnoutMashup-0.2.0", p
    b = u.build(["--input", "x"])
    assert b["exe_sha256"] == r["sha"] and b["host_changed"] and b["previous_version"] == "0.1.0-dev", b
    loc = os.path.join(i.L, "host-local")
    assert bmhost.folder_state(loc)["sha256"] == r["sha"] and bmhost.folder_state(loc + ".prev")["sha256"] == i.old_sha
    assert bmhost.active_source(i.L) == p["source"] and bmhost.play_state(i.L)["host_ok"], bmhost.play_state(i.L)["problems"]
    st = U.Updater(i.L, i.upd).status()
    assert st["version"] == "0.2.0" and st["previous"] == "0.1.0-dev" and st["pending"] is None, st
    s = u.switch_back()
    assert s["now"] == "0.1.0-dev" and bmhost.folder_state(loc)["sha256"] == i.old_sha and bmhost.active_source(i.L) == i.repo, s
    assert bmhost.play_state(i.L)["host_ok"]
    s = u.switch_back()
    assert s["now"] == "0.2.0" and bmhost.folder_state(loc)["sha256"] == r["sha"] and bmhost.active_source(i.L) == p["source"]
    # the launcher's own "Previous build" (bmhost.switch_back) keeps the recorded source in step too
    bmhost.switch_back(i.L, log=lambda s: None)
    assert bmhost.active_source(i.L) == i.repo and U.Updater(i.L, i.upd).status()["version"] == "0.1.0-dev"
    bmhost.switch_back(i.L, log=lambda s: None)
    assert bmhost.active_source(i.L) == p["source"]
    assert i.user_digest() == i.user, "user data changed"
    assert tree_digest(p["source"]) == json.loads(r["data"])["source"]["tree_sha256"]
    keep = ("launcher/host-local", "launcher/update-state", "HOST_INFO.json")
    assert {k: v for k, v in U.dir_files(i.repo).items() if not k.startswith(keep)} == old_src, "the old source changed"
    # check again: up to date, nothing pending
    with Net():
        assert u.check()["verdict"] == "up_to_date"
    return "PASS check -> download -> prepare (new sibling folder) -> build/install (previous kept) -> switch back -> forward; Previous build follows; user data untouched"


@case
def cli_flow():
    """the same steps through update.cmd's program (separate processes), --events"""
    i = Inst("cli flow")
    i.release("0.2.0", 1, "new cli")
    env = {"LOCALAPPDATA": i.base}
    for c in ("check", "download", "prepare"):
        rc, v, out = cli(c, "--updates", i.upd, "--events", launcher=i.L, env=env)
        assert rc == 0 and v["ok"], (c, out[-800:])
    rc, v, out = cli("status", "--updates", i.upd, launcher=i.L, env=env)
    assert v["next_step"] == "build" and v["pending"]["version"] == "0.2.0", v
    rc, v, out = cli("install-older", "0.1.0", launcher=i.L, env=env)
    assert rc == U.RC_REFUSED and v["cls"] == "older", out[-300:]
    rc, v, out = cli("discard", "--yes", "--updates", i.upd, launcher=i.L, env=env)
    assert rc == 0 and v["discarded"] and not os.path.exists(os.path.join(i.base, "BurnoutMashup-0.2.0")), out[-400:]
    assert os.path.isdir(i.repo) and bmhost.folder_state(os.path.join(i.L, "host-local"))["sha256"] == i.old_sha
    return "PASS check / download / prepare / status / install-older (unconfirmed refused) / discard as commands"


@case
def tampered_archive():
    i = Inst("tampered")
    r = i.release("0.2.0", 1, "t")
    data = bytearray(open(r["zip"], "rb").read())
    data[len(data) // 2] ^= 0xFF
    CH.routes["/" + i.prefix + os.path.basename(r["zip"])] = ("ok", bytes(data))
    u = i.u()
    with Net():
        u.check()
        refused("integrity", u.download)
    dl = os.path.join(i.upd, "downloads")
    assert not [f for f in os.listdir(dl) if not f.endswith(".json")], os.listdir(dl)
    assert not (u.state().get("pending") or {}).get("archive")
    refused("pending", u.prepare)
    assert bmhost.folder_state(os.path.join(i.L, "host-local"))["sha256"] == i.old_sha
    return "PASS sha256 mismatch: deleted, not used; prepare refused; version in use unchanged"


@case
def unknown_key():
    i = Inst("unknown key")
    i.release("0.2.0", 1, "u", key=K.OTHER_KEY)
    u = i.u()
    with Net():
        e = refused("signature", u.check)
    assert "UNKNOWN key" in str(e) and not u.state().get("pending") and not u.state().get("seen")
    return "PASS manifest signed by a key not in update_channel.json refused (%s)" % str(e)[:80]


@case
def bad_signature():
    i = Inst("bad sig")
    r = i.release("0.2.0", 1, "b")
    u = i.u()
    path = "/" + i.prefix + "bmashup-release.json"
    variants = {"changed after signing": (r["data"].replace(b'"0.2.0"', b'"0.2.1"'), r["sig"]),
                "signature of another file": (r["data"], K.TEST_KEY.sshsig(b"other")),
                "other namespace": (r["data"], K.TEST_KEY.sshsig(r["data"], namespace="file")),
                "garbage": (r["data"], b"-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n"),
                "no signature": (r["data"], b"")}
    for name, (d, s) in variants.items():
        CH.routes[path] = ("ok", d)
        CH.routes[path + ".sig"] = ("ok", s)
        with Net():
            refused("signature", u.check)
        assert not u.state().get("pending"), name
    # a valid signature over a manifest that is not JSON / not ours: refused after the signature, before use
    for d, cls in ((b"not json", "manifest"), (json.dumps({"format": "x"}).encode(), "manifest"),
                   (r["data"].replace(b'"BurnoutMashup"', b'"Takedawn"'), "upstream")):
        CH.routes[path] = ("ok", d)
        CH.routes[path + ".sig"] = ("ok", K.TEST_KEY.sshsig(d))
        with Net():
            refused(cls, u.check)
    return "PASS changed manifest, signature of another file, other namespace, garbage, missing; signed non-manifest / other product"


@case
def invalid_manifest_fields():
    """a CORRECTLY signed manifest (TEST key) with one required field missing / malformed: refused as 'manifest' before any use"""
    i = Inst("bad fields")
    r = i.release("0.2.0", 1, "f")
    u = i.u()
    path = "/" + i.prefix + "bmashup-release.json"
    good = json.loads(r["data"].decode("utf-8"))

    def mut(fn):
        m = json.loads(json.dumps(good))
        fn(m)
        return json.dumps(m, indent=1, sort_keys=True).encode("utf-8")
    cases = {
        "no version": lambda m: m.pop("version"), "bad version": lambda m: m.update(version="latest"),
        "serial 0": lambda m: m.update(serial=0), "serial bool": lambda m: m.update(serial=True),
        "created local time": lambda m: m.update(created="2026-11-01 12:00"),
        "archive not .zip": lambda m: m["source"]["archive"].update(name="BurnoutMashup.exe"),
        "archive sha256 short": lambda m: m["source"]["archive"].update(sha256="ab" * 10),
        "archive size 0": lambda m: m["source"]["archive"].update(size=0),
        "no archive urls": lambda m: m["source"]["archive"].update(urls=[]),
        "tree digest bad": lambda m: m["source"].update(tree_sha256="x"),
        "files 0": lambda m: m["source"].update(files=0),
        "top folder ..": lambda m: m["source"].update(top_folder=".."),
        "commit short": lambda m: m["source"].update(commit="abc123"),
        "expected json sha bad": lambda m: m["expected"].update(expected_json_sha256=""),
        "exe sha bad": lambda m: m["expected"].update(exe_sha256="0"),
        "identity bad": lambda m: m["expected"].update(identity="takedawn-1"),
        "other exe": lambda m: m["expected"].update(exe="burnout3.exe"),
        "dev profile": lambda m: m["expected"].update(profile="dev"),
        "provides.release differs": lambda m: m["provides"].update(release="9.9.9"),
        "other channel": lambda m: m.update(channel="someone-else"),
    }
    for name, fn in cases.items():
        d = mut(fn)
        CH.routes[path] = ("ok", d)
        CH.routes[path + ".sig"] = ("ok", K.TEST_KEY.sshsig(d))
        with Net():
            refused("manifest", u.check)
        assert not u.state().get("pending"), name
    return "PASS %d signed manifests with one bad field each refused as 'manifest' (nothing pending)" % len(cases)


@case
def downgrade_and_older():
    i = Inst("downgrade", version="0.3.0")
    i.release("0.2.0", 7, "d")
    u = i.u()
    with Net():
        e = refused("downgrade", u.check)
    assert not u.state().get("pending")
    i.release("0.2.0", 7, "d", path="releases/0.2.0/bmashup-release.json")
    with Net():
        c = u.check(version="0.2.0", older=True)
        assert c["verdict"] == "older"
        u.download()
    u.prepare()
    b = u.build(["--input", "x"])
    assert b["version"] == "0.2.0" and b["previous_version"] == "0.3.0"
    return "PASS older release refused by check (%s); install-older (explicit) installed 0.2.0, 0.3.0 kept as previous" % str(e)[:60]


@case
def replay_refused():
    i = Inst("replay")
    u = i.u()
    i.release("0.2.0", 5, "r5")
    with Net():
        assert u.check()["verdict"] == "available"
    old = i.release("0.2.1", 4, "r4")
    with Net():
        e1 = refused("replay", u.check)
    i.release("0.2.0", 5, "r5-other")                       # same serial, other bytes
    with Net():
        refused("replay", u.check)
    i.release("0.2.2", 6, "r6")
    with Net():
        assert u.check()["version"] == "0.2.2"
    CH.publish(old["data"], old["sig"], i.prefix + "bmashup-release.json")
    with Net():
        refused("replay", u.check)
    assert u.state()["seen"]["bm-test"]["serial"] == 6
    return "PASS older serial and same-serial-other-bytes refused; newer accepted; highest serial kept (%s)" % str(e1)[:70]


@case
def incompatible_minimum():
    i = Inst("incompatible")
    u = i.u()
    for over, what in (({"requires": {"launcher": "9.0.0"}}, "launcher"), ({"provides": {"kit": "0.6.0"}}, "kit"),
                       ({"provides": {"platform": "0.1.0"}}, "platform")):
        i.release("0.2.0", 1, "i", **over)
        with Net():
            e = refused("incompatible", u.check)
        assert what in str(e), e
    assert not u.state().get("pending")
    return "PASS needs a newer launcher / provides a lower kit / platform than update_channel.json's minimum: refused"


@case
def interrupted_download():
    i = Inst("interrupted")
    r = i.release("0.2.0", 1, "x", route_mode="cut", pad=600000)
    zr = "/" + i.prefix + os.path.basename(r["zip"])
    u = i.u()
    with Net():
        u.check()
        e = refused("download", u.download)
        assert e.rc == U.RC_FAILED and "part is kept" in str(e), e
        part = [f for f in os.listdir(os.path.join(i.upd, "downloads")) if f.endswith(".part")]
        assert part, os.listdir(os.path.join(i.upd, "downloads"))
        n = os.path.getsize(os.path.join(i.upd, "downloads", part[0]))
        assert 0 < n < len(CH.routes[zr][1])
        CH.routes[zr] = ("ok", CH.routes[zr][1])
        CH.hits.clear()
        u.download()
    assert any(h[0] == zr and h[1] == "bytes=%d-" % n for h in CH.hits), CH.hits
    # a server that ignores Range: the download starts again and still verifies
    j = Inst("interrupted norange")
    r = j.release("0.2.0", 1, "y", route_mode="cut", pad=600000)
    zr = "/" + j.prefix + os.path.basename(r["zip"])
    u = j.u()
    with Net():
        u.check()
        refused("download", u.download)
        CH.routes[zr] = ("norange", CH.routes[zr][1])
        u.download()
    assert any("starting again" in x for x in j.log), j.log
    return "PASS cut at %d bytes -> part kept -> continued with Range bytes=%d- -> verified; server without Range -> restarted" % (n, n)


@case
def download_failure():
    i = Inst("dl failure")
    r = i.release("0.2.0", 1, "f")
    del CH.routes["/" + i.prefix + os.path.basename(r["zip"])]
    u = i.u()
    with Net():
        u.check()
        e = refused("download", u.download)
    assert e.rc == U.RC_FAILED and "404" in str(e)
    assert not (u.state().get("pending") or {}).get("archive")
    return "PASS HTTP 404 -> failed (exit 3), nothing used"


@case
def cancel_download():
    i = Inst("cancel dl")
    r = i.release("0.2.0", 1, "c", route_mode="slow", pad=3000000)
    zr = "/" + i.prefix + os.path.basename(r["zip"])
    u = i.u()
    with Net():
        u.check()
        t = threading.Timer(0.6, lambda: open(os.path.join(i.upd, "CANCEL"), "w").close())
        t.start()
        try:
            u.download()
            raise AssertionError("not cancelled")
        except U.Cancelled:
            pass
        part = os.path.join(i.upd, "downloads", [f for f in os.listdir(os.path.join(i.upd, "downloads")) if f.endswith(".part")][0])
        n = os.path.getsize(part)
        assert 0 < n < len(CH.routes[zr][1]), n
        CH.routes[zr] = ("ok", CH.routes[zr][1])
        u.download()                                          # removes the old CANCEL request, continues
    assert U.sha_f(u.state()["pending"]["archive"]) == hashlib.sha256(CH.routes[zr][1]).hexdigest()
    return "PASS cancelled at %d bytes (part kept), continued and verified" % n


@case
def failed_and_cancelled_build():
    i = Inst("failed build")
    i.release("0.2.0", 1, "fb")
    u = i.u()
    with Net():
        u.check()
        u.download()
    u.prepare()
    st0 = json.dumps(u.state().get("active"))
    for rc, cls in ((3, "build"), (4, "build"), (2, "build"), (5, "cancelled")):
        os.environ["BMUPD_FAKE_RC"] = str(rc)
        try:
            e = refused(cls, u.build, ["--input", "x"])
        finally:
            os.environ.pop("BMUPD_FAKE_RC", None)
        assert "unchanged" in str(e), e
        assert bmhost.folder_state(os.path.join(i.L, "host-local"))["sha256"] == i.old_sha
        assert json.dumps(u.state().get("active")) == st0 and u.state()["pending"]["prepared"]
        assert bmhost.active_source(i.L) == i.repo
    # a tampered prepared tree is refused before the build
    p = u.state()["pending"]["prepared"]
    open(os.path.join(p, "README.md"), "a").write("changed\n")
    refused("source", u.build, ["--input", "x"])
    return "PASS build exit 3 / 4 / 2 / 5 -> version in use unchanged (host-local, source, state); changed prepared tree refused"


@case
def offline():
    i = Inst("offline", url=K.closed_port_url())
    u = i.u()
    with Net():
        e = refused("offline", u.check)
    assert e.rc == U.RC_OFFLINE
    rc, v, out = cli("check", launcher=i.L, env={"LOCALAPPDATA": i.base})
    assert rc == U.RC_OFFLINE and v["cls"] == "offline", out[-300:]
    return "PASS channel not reachable -> exit 7, nothing changed"


@case
def upstream_refused():
    i = Inst("upstream", config=False)
    for repo, url, cid in (("xenophobentx/takedawn", "", "bm-test"), ("someone/takedawn", "", "bm-test"), ("xenophobentx/other", "", "bm-test"),
                           ("", "https://github.com/xenophobentx/takedawn/releases/", "bm-test"), ("", "https://example.org/x/", "takedawn-stable")):
        K.channel_config(i.L, url, cid=cid, repo=repo)
        refused("upstream", U.load_config, i.L)
    K.channel_config(i.L, "http://example.org/x/")
    refused("config", U.load_config, i.L)                          # plain http to another host
    K.channel_config(i.L, CH.url + i.prefix, keys=())
    refused("config", U.load_config, i.L)                          # a channel without a trusted key
    K.channel_config(i.L, CH.url + i.prefix)
    u = i.u()
    r = i.release("0.2.0", 1, "up2")
    m = json.loads(r["data"])
    m["source"]["archive"]["urls"] = ["https://github.com/xenophobentx/takedawn/archive/refs/heads/main.zip"]
    d = (json.dumps(m) + "\n").encode()
    CH.publish(d, K.TEST_KEY.sshsig(d), i.prefix + "bmashup-release.json")
    with Net():
        refused("upstream", u.check)
    i.release("0.2.0", 2, "up3", application="Takedawn")
    with Net():
        u.check()
        u.download()
    refused("upstream", u.prepare)
    return "PASS upstream repo / owner / URL / channel id, manifest archive URL and a non-Mashup source refused; http and keyless channels refused"


@case
def archive_safety():
    S = U.Updater.safe_members
    for entries in ([("BurnoutMashup-1/../evil.txt", b"x")], [("../evil.txt", b"x")], [("other/x.txt", b"x")], [("BurnoutMashup-1/C:/x", b"x")],
                    [("BurnoutMashup-1/NUL.txt", b"x")], [("BurnoutMashup-1/a.txt:stream", b"x")], [("BurnoutMashup-1/dir./x.txt", b"x")]):
        z = zipfile.ZipFile(__import__("io").BytesIO(K.zip_bytes(entries)))
        refused("archive", S, z, "BurnoutMashup-1")
    zi = zipfile.ZipInfo("BurnoutMashup-1/link")
    zi.external_attr = (0o120777 << 16)
    import io
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(zi, "target")
    refused("archive", S, zipfile.ZipFile(io.BytesIO(b.getvalue())), "BurnoutMashup-1")
    # an archive that is signed but holds a file more than the tree digest -> refused at prepare (count / digest)
    i = Inst("archive digest")
    r = i.release("0.2.0", 1, "ad")
    m = json.loads(r["data"])
    src = r["src"]
    open(os.path.join(src, "extra.txt"), "w").write("not in the signed tree\n")
    z2 = K.zip_tree(src, r["zip"] + ".2.zip", "BurnoutMashup-0.2.0")
    m["source"]["archive"].update(sha256=U.sha_f(z2), size=os.path.getsize(z2), urls=[os.path.basename(z2)], name=os.path.basename(z2))
    m["source"]["files"] += 1                                     # the count matches, the digest does not
    d = (json.dumps(m) + "\n").encode()
    CH.routes["/" + i.prefix + os.path.basename(z2)] = ("ok", open(z2, "rb").read())
    CH.publish(d, K.TEST_KEY.sshsig(d), i.prefix + "bmashup-release.json")
    u = i.u()
    with Net():
        u.check()
        u.download()
    refused("source", u.prepare)
    assert not [x for x in os.listdir(i.base) if x.startswith("BurnoutMashup-0.2.0")], os.listdir(i.base)
    return "PASS '..', other top folder, drive, device name, backslash, symlink refused; changed tree (digest) refused, nothing left"


HOOK = r'''
import os, sys, json
EV = []
def h(event, args):
    if event.startswith("socket.") or event == "urllib.Request":
        EV.append(event)
sys.addaudithook(h)
src, L, phase = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, os.path.join(src, "tools", "launcher"))
import bmupdate, bmupdate_gui
out = []
bmupdate.main(["status", "--launcher", L], out=out.append)
bmupdate.main(["help"], out=out.append)
gui = "not run"
try:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    w = bmupdate_gui.UpdateWindow(root, launcher=L)
    w.update()
    w.refresh()
    w.update()
    try:
        import bmgui
        lw = bmgui.Launcher()
        lw.update()
        uw = lw.open_updates() if hasattr(lw, "open_updates") else None
        lw.update()
        lw.destroy()
        gui = "update window + launcher window" + (" + its Check for updates window" if uw is not None else "")
    except Exception as e:
        gui = "update window (launcher window: %s)" % e
    root.destroy()
except Exception as e:
    gui = "GUI not available: %s" % e
passive = list(EV)
if phase == "detector":
    bmupdate.main(["check", "--launcher", L, "--updates", sys.argv[4]], out=out.append)
print(json.dumps({"passive_events": passive, "after_check": EV[len(passive):][:5], "after_check_n": len(EV) - len(passive), "gui": gui}))
'''


@case
def no_network_unless_asked():
    i = Inst("no network")
    i.release("0.2.0", 1, "nn")
    hp = os.path.join(W["base"], "net_hook.py")
    open(hp, "w", encoding="utf-8").write(HOOK)
    hits = len(CH.hits)
    r = subprocess.run([sys.executable, "-B", hp, SRC, i.L, "passive"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8", LOCALAPPDATA=i.base), timeout=120, stdin=subprocess.DEVNULL)
    v = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])
    assert v["passive_events"] == [] and len(CH.hits) == hits, (v, r.stderr[-500:])
    r = subprocess.run([sys.executable, "-B", hp, SRC, i.L, "detector", i.upd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8", LOCALAPPDATA=i.base), timeout=120, stdin=subprocess.DEVNULL)
    d = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])
    assert d["passive_events"] == [] and d["after_check_n"] > 0 and len(CH.hits) > hits, d
    return "PASS 0 socket events for status / help / %s with a configured channel; detector: check -> %d events" % (v["gui"], d["after_check_n"])


@case
def isolation():
    sent = "TAKEDAWN-SENTINEL"
    fake = os.path.join(W["base"], "fake env \u00fc")
    shutil.rmtree(fake, ignore_errors=True)
    roam, local = os.path.join(fake, "Roaming"), os.path.join(fake, "Local")
    td = [os.path.join(roam, "Takedawn"), os.path.join(local, "Takedawn")]
    for root, rel in ((td[0], "plugin-approvals.toml"), (td[0], "settings.toml"), (td[1], "Game/default.xbe"), (td[1], "update/x.json")):
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(sent)

    def snap():
        return {os.path.relpath(os.path.join(dp, f), fake): (os.path.getsize(os.path.join(dp, f)), os.path.getmtime(os.path.join(dp, f)),
                                                             U.sha_f(os.path.join(dp, f))) for t in td for dp, dn, fn in os.walk(t) for f in fn}
    before = snap()
    i = Inst("isolation")
    i.release("0.2.0", 1, "iso")
    log = os.path.join(W["base"], "audit.log")
    if os.path.exists(log):
        os.remove(log)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", APPDATA=roam, LOCALAPPDATA=local, BM_AUDIT_LOG=log)
    outs = []
    for c in (["status"], ["check"], ["download"], ["prepare"], ["switch-back"], ["discard", "--yes"], ["help"]):
        r = subprocess.run([sys.executable, "-B", AUDITED, BMU] + c + ["--launcher", i.L], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=120, stdin=subprocess.DEVNULL)
        outs.append(r.stdout + r.stderr)
    lines = open(log, encoding="utf-8").read().splitlines()
    assert len(lines) > 50, len(lines)
    bad = [ln for ln in lines if any(os.path.normcase(ln.split("\t", 1)[1]).startswith(os.path.normcase(t)) for t in td)]
    assert not bad, bad[:5]
    assert snap() == before, "the fake Takedawn environment changed"
    assert not any(sent in o for o in outs)
    assert os.path.isdir(os.path.join(local, "BurnoutMashup", "updates")), "the default cache is %LOCALAPPDATA%\\BurnoutMashup\\updates"
    return "PASS %d audited path events, none below the fake Takedawn folders; fake environment byte-identical" % len(lines)


@case
def gui_window():
    import tkinter as tk
    import bmupdate_gui as G
    root = tk.Tk()
    root.withdraw()
    try:
        i = Inst("gui none", config=False)
        empty_channel(i.L)
        w = G.UpdateWindow(root, launcher=i.L)
        w.update()
        assert w.channel_lbl["text"].startswith("No update channel configured"), w.channel_lbl["text"]
        assert str(w.btn["check"]["state"]) == "disabled" and str(w.btn["download"]["state"]) == "disabled"
        w.destroy()
        j = Inst("gui configured")
        j.release("0.2.0", 1, "g")
        os.environ["LOCALAPPDATA"] = j.base
        w = G.UpdateWindow(root, launcher=j.L)
        w.update()
        assert "bm-test" in w.channel_lbl["text"] and str(w.btn["check"]["state"]) == "normal"
        assert str(w.btn["download"]["state"]) == "disabled"
        hits = len(CH.hits)
        w.update()
        assert len(CH.hits) == hits, "the window contacted the channel by itself"
        assert w.run("check")
        t0 = time.time()
        while w.job is not None and time.time() - t0 < 60:
            w.update()
            time.sleep(0.05)
        assert "available" in w.result["text"], w.result["text"]
        assert str(w.btn["download"]["state"]) == "normal" and "0.2.0" in w.version_lbl["text"]
        w.destroy()
    finally:
        root.destroy()
    return "PASS no channel: explanation shown, steps disabled; configured: nothing contacted until 'Check for updates', then Download enabled"


@case
def shipped_config_trusts_release_key():
    """0.2.0: the shipped configuration names exactly the release channel and the release key (owner decision 2026-11-01)"""
    c = json.load(open(os.path.join(SRC, "update_channel.json"), encoding="utf-8"))
    assert c["channel"] == {"id": "burnoutmashup-stable", "github_repo": "HeartWorthBreaking/burnout-mashup", "url": ""}, c["channel"]
    assert len(c["trusted_keys"]) == 1, c["trusted_keys"]       # checked by fingerprint (no key literal under launcher\tests: the release gate)
    cfg = U.load_config(SRC)
    assert cfg["configured"] is True and cfg["fingerprints"] == [RELEASE_FP] and cfg["namespace"] == "bmashup-update", cfg
    found = []
    for dp, dn, fn in os.walk(SRC):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(HERE)):
            continue
        for f in fn:
            t = open(os.path.join(dp, f), "rb").read()
            for k in (K.TEST_KEY, K.OTHER_KEY):
                if k.line.split()[1].encode() in t or K.MARK.encode() in t:
                    found.append(os.path.join(dp, f))
    assert not found, found
    return "PASS shipped update_channel.json: the release channel and key only (%s); no TEST-ONLY key / marker outside launcher\\tests" % RELEASE_FP


def main():
    global CH
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    base = arg("--work") or tempfile.mkdtemp(prefix="bm upd t\u00e9st \u00dc ")
    if os.path.normcase(os.path.abspath(base)).startswith(os.path.normcase(os.path.dirname(SRC))):
        print("--work must be outside this checkout")
        return 1
    os.makedirs(base, exist_ok=True)
    W["base"] = base
    CH = K.Channel()
    saved = dict(os.environ)
    try:
        for fn in CASES:
            run_case(fn)
    finally:
        CH.stop()
        os.environ.clear()
        os.environ.update(saved)
    ok = all(v.startswith(("PASS", "SKIP")) for v in RES.values())
    json.dump({"results": RES, "work": base, "ok": ok}, open(sys.argv[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("RESULT %s %d/%d" % ("PASS" if ok else "FAIL", sum(v.startswith("PASS") for v in RES.values()), len(RES)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
