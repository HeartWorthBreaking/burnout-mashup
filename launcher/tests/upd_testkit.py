"""upd_testkit.py - BMUPD-TEST-ONLY helpers for the updater tests: TEST signing keys, an Ed25519 / SSHSIG signer, a local mock update
channel (127.0.0.1, HTTP Range), synthetic source trees and host builds. Everything here exists ONLY for tests: the TEST keys are
EPHEMERAL - made from random bytes when a test process starts and never written anywhere - so no test private key exists in this
tree and none can be trusted by a shipped configuration (the release gate, pf_assemble.py "update_channel", also refuses any key the
maintainers have not approved and the TEST marker outside launcher\\tests). Never copy anything from this file into a shipped
configuration. Original code (MIT)."""
import base64
import hashlib
import http.server
import io
import json
import os
import shutil
import socketserver
import struct
import sys
import threading
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SRC, "tools", "launcher"))
import bmed25519 as E  # noqa: E402
import bmhost  # noqa: E402

MARK = "BMUPD-TEST-ONLY"


# ------------------------------------------------------------------------------------------------------------------ Ed25519 signing (tests)
def _expand(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_of(seed):
    return E._compress(E._mul(_expand(seed)[0], E.G))


def sign(seed, msg):
    """RFC 8032 Ed25519 sign (5.1.6), test use only"""
    a, prefix = _expand(seed)
    pub = E._compress(E._mul(a, E.G))
    r = E._h(prefix + msg)
    rs = E._compress(E._mul(r, E.G))
    s = (r + E._h(rs + pub + msg) * a) % E.L
    return rs + int.to_bytes(s, 32, "little")


class Key:
    def __init__(self, phrase):
        self.phrase = phrase
        self.seed = os.urandom(32)                       # ephemeral: a new key in every test process, never stored
        self.pub = public_of(self.seed)
        self.blob = E._string(b"ssh-ed25519") + E._string(self.pub)
        self.line = "ssh-ed25519 %s %s" % (base64.b64encode(self.blob).decode("ascii"), MARK)
        self.fp = E.fingerprint(self.blob)

    def sshsig(self, msg, namespace=E.NAMESPACE, hash_alg=b"sha512"):
        sd = E.signed_data(namespace.encode("ascii"), b"", hash_alg, msg)
        sig = E._string(b"ssh-ed25519") + E._string(sign(self.seed, sd))
        b = b"SSHSIG" + struct.pack(">I", 1) + E._string(self.blob) + E._string(namespace.encode("ascii")) + E._string(b"") + \
            E._string(hash_alg) + E._string(sig)
        t = base64.b64encode(b).decode("ascii")
        return ("-----BEGIN SSH SIGNATURE-----\n" + "\n".join(t[i:i + 70] for i in range(0, len(t), 70)) + "\n-----END SSH SIGNATURE-----\n").encode("ascii")


TEST_KEY = Key("release key 1")
OTHER_KEY = Key("unknown key 2")
assert TEST_KEY.pub != OTHER_KEY.pub


# ------------------------------------------------------------------------------------------------------------------ mock channel
class Channel:
    """routes {path: (mode, bytes)}; modes: ok, 404, cut (first GET sends half and closes), slow (64 KB per 0.05 s), norange (ignores
    Range). .hits = [(path, Range header)]."""

    def __init__(self):
        self.routes, self.hits, self.cut_done = {}, [], set()
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.hits.append((self.path, self.headers.get("Range")))
                mode, data = outer.routes.get(self.path, ("404", b""))
                if mode == "404":
                    self.send_error(404, "Not Found")
                    return
                start = 0
                rg = self.headers.get("Range")
                if rg and mode != "norange" and rg.startswith("bytes=") and rg.endswith("-"):
                    start = int(rg[6:-1])
                    self.send_response(206)
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, len(data) - 1, len(data)))
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    if mode == "cut" and self.path not in outer.cut_done:
                        outer.cut_done.add(self.path)
                        self.wfile.write(body[:len(body) // 2])
                        self.wfile.flush()
                        self.connection.shutdown(2)
                        return
                    if mode == "slow":
                        for i in range(0, len(body), 1 << 16):
                            self.wfile.write(body[i:i + (1 << 16)])
                            self.wfile.flush()
                            time.sleep(0.05)
                        return
                    self.wfile.write(body)
                except OSError:
                    pass

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.httpd = S(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d/" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def publish(self, manifest_bytes, sig_bytes, path="bmashup-release.json"):
        self.routes["/" + path] = ("ok", manifest_bytes)
        self.routes["/" + path + ".sig"] = ("ok", sig_bytes)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def closed_port_url():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d/" % port


# ------------------------------------------------------------------------------------------------------------------ trees and builds
def synthetic_exe(identity, salt):
    return b"MZ" + b"\0" * 62 + ("%s synthetic test host %s" % (MARK, salt)).encode("ascii") + b"\0" + identity.encode("ascii") + b"\0" * 64


def host_folder(d, identity, salt, platform="0.1.9"):
    """a consistent, 'verified' host folder (synthetic; for flow tests only) -> exe sha256"""
    os.makedirs(os.path.join(d, "shaders"), exist_ok=True)
    os.makedirs(os.path.join(d, "licenses"), exist_ok=True)
    exe = synthetic_exe(identity, salt)
    open(os.path.join(d, bmhost.EXE), "wb").write(exe)
    open(os.path.join(d, "SDL2.dll"), "wb").write(b"synthetic")
    open(os.path.join(d, "shaders", "x.spv"), "wb").write(b"synthetic")
    open(os.path.join(d, "licenses", "x.txt"), "w").write("synthetic\n")
    sha = hashlib.sha256(exe).hexdigest()
    json.dump({"exe_sha256": sha, "identity": identity, "platform": platform, "services": {}, "tables": {}, "profile": "release"},
              open(os.path.join(d, "HOST_INFO.json"), "w"))
    json.dump({"sha256": sha, "verified": True, "identity": identity}, open(os.path.join(d, "BUILD_RESULT.json"), "w"))
    return sha


def mini_source(d, version, identity, salt, kit="0.7.0", launcher="1.0.0", application="Burnout Mashup"):
    """a minimal 'source tree' with what the updater checks (flow tests; the real tree is used by test_update_real.py)"""
    def w(rel, text):
        p = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(text.encode("utf-8") if isinstance(text, str) else text)
    exe = synthetic_exe(identity, salt)
    w("host/PINS.json", json.dumps({"identity": {"application": application, "release_exe": "BurnoutMashup.exe"}}))
    w("build/verify.py", "# synthetic\n")
    w("build/EXPECTED.json", json.dumps({"build_release": {"exe_sha256": hashlib.sha256(exe).hexdigest(), "identity": identity}}))
    w("build/synthetic_exe.bin", exe)
    w("launcher/VERSION.json", json.dumps({"format": "bm-version 1", "product": "BurnoutMashup", "release": version, "launcher": launcher}))
    w("launcher/tools/launcher/bmbuild.py", "# synthetic\n")
    w("tools/_lib/bmkit_env.py", "KIT_VERSION = '%s'\n" % kit)
    w("README.md", "synthetic source %s %s\n" % (version, MARK))
    return hashlib.sha256(exe).hexdigest()


def zip_tree(src, zpath, top, extra=None):
    """git-archive-like zip: one top folder, sorted entries, fixed times. extra: [(name, bytes)] added as given (tests of bad archives)"""
    os.makedirs(os.path.dirname(zpath), exist_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dn, fn in os.walk(src):
            dn.sort()
            for f in sorted(fn):
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, src).replace(os.sep, "/")
                zi = zipfile.ZipInfo(top + "/" + rel, (2026, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, open(p, "rb").read())
        for name, data in extra or ():
            z.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), data)
    return zpath


def fake_build(argv, out):
    """stands in for bmbuild.main in flow tests: installs the synthetic exe of --repo's build/ into --launcher's host-local through
    bmhost.install (the same atomic install). BMUPD_FAKE_RC=N returns N without installing (failure / cancel cases)."""
    rc = int(os.environ.get("BMUPD_FAKE_RC", "0"))
    out("@@ " + json.dumps({"ev": "step", "name": "build", "status": "running"}))
    if rc:
        return rc
    repo, launcher = argv[argv.index("--repo") + 1], argv[argv.index("--launcher") + 1]
    exp = json.load(open(os.path.join(repo, "build", "EXPECTED.json")))["build_release"]
    st = os.path.join(os.path.dirname(launcher), "stage-fake")
    shutil.rmtree(st, ignore_errors=True)
    os.makedirs(os.path.join(st, "shaders"))
    os.makedirs(os.path.join(st, "licenses"))
    exe = open(os.path.join(repo, "build", "synthetic_exe.bin"), "rb").read()
    open(os.path.join(st, bmhost.EXE), "wb").write(exe)
    open(os.path.join(st, "SDL2.dll"), "wb").write(b"synthetic")
    open(os.path.join(st, "shaders", "x.spv"), "wb").write(b"synthetic")
    open(os.path.join(st, "licenses", "x.txt"), "w").write("synthetic\n")
    json.dump({"exe_sha256": exp["exe_sha256"], "identity": exp["identity"], "platform": "0.1.9"}, open(os.path.join(st, "HOST_INFO.json"), "w"))
    json.dump({"sha256": exp["exe_sha256"], "verified": True}, open(os.path.join(st, "BUILD_RESULT.json"), "w"))
    bmhost.install(st, launcher, log=out)
    shutil.rmtree(st, ignore_errors=True)
    return 0


def make_release(updmod, zpath, version, serial, channel_id, key=TEST_KEY, url=None, **over):
    """manifest bytes + signature for a zip (bmupdate.make_manifest, then signed with a TEST key). over: fields to override (after
    make-manifest, before signing: e.g. requires / provides / channel)."""
    out = zpath + ".manifest.json"
    a = {"zip": zpath, "version": version, "serial": serial, "channel": channel_id, "tag": "v" + version, "commit": "0" * 40,
         "url": [url or os.path.basename(zpath)], "out": out, "created": "2026-11-01T12:00:00Z", "notes_url": ""}
    updmod.make_manifest(a)
    m = json.load(open(out, encoding="utf-8"))
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            m[k].update(v)
        else:
            m[k] = v
    data = (json.dumps(m, indent=1, sort_keys=True) + "\n").encode("utf-8")
    return data, key.sshsig(data)


def channel_config(launcher, url, cid="bm-test", keys=(TEST_KEY,), minimum=None, repo=""):
    cfg = {"format": "bm-update-channel 1", "note": "%s configuration written by a test" % MARK,
           "channel": {"id": cid, "url": url, "github_repo": repo}, "trusted_keys": [{"key": k.line, "label": MARK} for k in keys],
           "minimum": minimum if minimum is not None else {"launcher": "1.0.0", "kit": "0.7.0", "platform": "0.1.9"}, "namespace": "bmashup-update"}
    open(os.path.join(launcher, "update_channel.json"), "w", encoding="utf-8").write(json.dumps(cfg, indent=1))
    return cfg


def zip_bytes(entries):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in entries:
            z.writestr(n, d)
    return b.getvalue()
