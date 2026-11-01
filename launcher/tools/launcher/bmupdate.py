"""bmupdate.py - "Check for updates" for the Burnout Mashup launcher (CLI; the launcher's Update window runs exactly this). Python 3.8+,
standard library. Windows x64. Original code (MIT).

POLICY. Nothing here runs by itself: no check at start, no background or scheduled check, no silent download, build or install. Every
network access is one command you give (or one button you press): check, download, install-older. The host program's own update row
stays off. Only the Mashup channel named in launcher\\update_channel.json is used - an upstream Takedawn repository is refused, and a
release must be a Burnout Mashup source (its host/PINS.json names Burnout Mashup) built through BUILD MASHUP. Your profile, saves, mods,
plugin approvals and game data are never read or changed by an update; new plugin bytes still need your approval in the game.

    update.cmd status                       what is configured, the version in use, the previous one, the next step (no network)
    update.cmd check                        fetch the channel's signed release manifest, verify it, show what is new and what will happen
    update.cmd download                     download the new source archive (sha256 + size checked; an interrupted download continues)
    update.cmd prepare                      unpack it into a NEW folder (never over the version in use) and verify every file
    update.cmd install                      (Windows package, layout 2) install the prepared package: the program folder app\\ and the two
                                            exes are replaced in one transaction (rename only, undone on any error), your data is
                                            carried over, the version in use is kept for Switch back; then start the launcher again
    update.cmd build [BUILD OPTIONS]        BUILD MASHUP from the new source (bmbuild.py: its cache and pinned tools), compare the exe with
                                            the manifest's reference, install (the previous build and source are kept); in the package
                                            layout only when the new release has another reference host than the build in use
    update.cmd switch-back                  use the previous version again (package: program + exes; source layout: source and build
                                            together); again = forward
    update.cmd install-older VERSION --yes  the same steps for an OLDER signed release of the channel (only when you ask for it)
    update.cmd discard [--yes]              forget the pending update (its download and its unpacked folder, never the version in use)
    update.cmd cancel                       stop a running download or build
    update.cmd make-manifest ...            (maintainers) write a release manifest for a source zip; docs\\OWNER_UPDATE_CHANNEL.md
    update.cmd verify-manifest FILE [SIG]   (maintainers) check a manifest + signature against update_channel.json (no network)

BUILD OPTIONS are passed to bmbuild.py (--input, --build-dir, --toolchain, --source, --takedawn-src, --xboxrecomp-src, ...); when left
out, --input and the upstream source come from the last build (BUILD_STATE.json of the build folder). --updates DIR: the download cache
(default %LOCALAPPDATA%\\BurnoutMashup\\updates). --sources-dir DIR: where the new source folder is made (default: beside the current
source). --events: machine-readable progress ("@@ {json}" lines).

Two layouts (bmpaths.py): the Windows PACKAGE (layout 2: Burnout Mashup.exe, Burnout Mashup Workbench.exe, gamedata\\, app\\) updates
by the release's package (check, download, prepare, install); a source checkout (layout 1) updates by the source archive as in 0.1.0
(check, download, prepare into a new folder beside it, build). Launcher 1.1.0.

Release manifest (bm-release-manifest 1, docs\\UPDATES.md) is verified BEFORE any field is used: an OpenSSH Ed25519 signature
(ssh-keygen -Y sign, namespace bmashup-update; bmed25519.py) by a key listed in update_channel.json. Refused: no channel / no trusted key,
an unknown key, a bad signature, another product or channel, an older version than the one in use (unless install-older), an older
manifest than one seen before (replay), a release that needs a newer launcher or provides less than update_channel.json's minimum.
Exit: 0 done (also "up to date"), 1 usage, 2 refused (nothing changed), 3 failed (the version in use is unchanged), 5 cancelled
(a partial download is kept and continued next time), 6 no update channel configured, 7 the channel cannot be reached (offline)."""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmed25519  # noqa: E402
import bmhost  # noqa: E402
import bmlayout  # noqa: E402  (rel020: transactional install / switch back / recover, layout 2)
import bmpaths  # noqa: E402

LAUNCHER = bmhost.LAUNCHER
CONFIG = "update_channel.json"
VERSION = "VERSION.json"
ASSET = "bmashup-release.json"
PRODUCT = "BurnoutMashup"
FORMAT = "bm-release-manifest 1"
UA = "BurnoutMashup-launcher/1.1 (update check on request)"
LAYOUT2 = "bm-layout 2"
PACKAGE_EXES = (bmpaths.EXE, bmpaths.WB_EXE)
UPSTREAM_OWNERS = ("xenophobentx",)
RC_OK, RC_USAGE, RC_REFUSED, RC_FAILED, RC_CANCELLED, RC_NOCHANNEL, RC_OFFLINE = 0, 1, 2, 3, 5, 6, 7
HEX64 = re.compile(r"^[0-9a-f]{64}$")
VER_RE = re.compile(r"^[0-9]+(\.[0-9]+){0,3}(-[0-9A-Za-z.]{1,32})?(\+[0-9A-Za-z.]{1,32})?$")
IDENT_RE = re.compile(r"^bmp-[0-9]+\.[0-9]+\.[0-9]+\+[0-9a-f]{12}$")
NET = {"allowed": False}            # set only by the commands that the user gave (check / download / install-older)
NO_CHANNEL = ("No update channel configured. This copy of Burnout Mashup does not know where official releases are published, so it "
              "cannot check for updates (nothing is contacted). The maintainer fills launcher\\update_channel.json (the channel and the "
              "trusted signing key) for published releases (docs\\UPDATES.md). Until then: get new versions by hand from the project page.")
RECOVERY = {
    "no_channel": NO_CHANNEL,
    "config": "launcher\\update_channel.json is not valid: restore it from a fresh copy of this release (docs\\UPDATES.md shows its fields).",
    "channel": "The channel answered, but not with a usable release manifest: try again later, or get the release by hand.",
    "offline": "The update channel cannot be reached (no network, or the server is down): nothing was changed. Try again later.",
    "signature": "The release manifest is NOT trusted (signature): nothing was downloaded or changed. Do not install it; report it to the "
                 "maintainers (SECURITY.md).",
    "manifest": "The release manifest is not a valid Burnout Mashup manifest: nothing was changed. Report it to the maintainers.",
    "upstream": "Burnout Mashup only updates from its own channel: an upstream Takedawn repository or release is never used.",
    "downgrade": "That release is OLDER than the version in use: nothing was changed. To go back on purpose use install-older VERSION "
                 "(or 'Install an older version...'), or 'Switch back' for the previous version.",
    "replay": "The channel served an OLDER release manifest than one already seen here (a stale mirror, or someone replaying an old "
              "file): nothing was changed. Try again later; report it if it persists.",
    "incompatible": "This release needs a newer launcher or does not provide what this installation needs: nothing was changed. Get the "
                    "new release by hand (fresh folder) and use 'Bring my data from an older Burnout Mashup folder'.",
    "up_to_date": "",
    "pending": "Run the steps in order: check, download, prepare, build (each one when you choose).",
    "download": "The download did not complete. Run download again: it continues where it stopped (the part file is checked at the end).",
    "integrity": "The downloaded archive is NOT the one the signed manifest names (sha256 / size): it was deleted and not used. Try again "
                 "later; report it if it persists.",
    "space": "Not enough free disk space: free some space (or choose --updates / --sources-dir on another drive) and run the step again.",
    "archive": "The source archive is not a valid release archive: it was not unpacked. Report it to the maintainers.",
    "source": "The unpacked source does not match the signed manifest or is not a Burnout Mashup source: it is not used. Run discard "
              "and start again with check; report it if it persists.",
    "folder": "The new source folder cannot be made there: choose another place with --sources-dir (a writable folder).",
    "build": "BUILD MASHUP did not finish: the version in use is unchanged (host-local and its source). See the Build log; fix the reason "
             "shown and run build again (completed steps are reused).",
    "switch": "Not switched: the installed builds no longer match the recorded versions (another build was installed meanwhile). Use "
              "'Previous build' in the Setup tab to swap the two builds.",
    "cancelled": "Cancelled. Nothing was changed; a partial download is kept and continues next time.",
    "older": "install-older needs --yes (you choose to install an older version on purpose).",
    "package": "The downloaded package does not match the signed manifest or is not a Burnout Mashup package: it is not used. Run discard "
               "and start again with check; report it if it persists.",
    "install": "The install did not finish and was UNDONE: the version in use is unchanged (program, exes and your data). Close the game, "
               "the Workbench and any window showing a file of this folder, then run install again.",
    "broken": "The install stopped and could not be fully undone. Nothing was deleted: do not move files by hand; start Burnout Mashup.exe "
              "again (it finishes or undoes the change from app\\.update\\JOURNAL.json) and report it (SECURITY.md / issues).",
}


class Refused(Exception):
    def __init__(self, cls, msg, rc=RC_REFUSED):
        super().__init__(msg)
        self.cls, self.rc = cls, rc


class Cancelled(Exception):
    pass


# ------------------------------------------------------------------------------------------------------------------ small helpers
def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def sha_f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def jload(p, default=None):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def jsave(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, p)


def version_key(text):
    """numeric dotted parts (4, missing = 0); '-pre' ranks below the same numbers; '+build' ignored (bmcompat's order)"""
    if not isinstance(text, str) or not VER_RE.match(text):
        return None
    t = text.split("+", 1)[0]
    pre = "-" in t
    nums = [int(x) for x in t.split("-", 1)[0].split(".")] + [0, 0, 0]
    return (tuple(nums[:4]), 0 if pre else 1, t.split("-", 1)[1] if pre else "")


def vcmp(a, b):
    ka, kb = version_key(a), version_key(b)
    if ka is None or kb is None:
        raise ValueError("not a version: %r / %r" % (a, b))
    return (ka > kb) - (ka < kb)


def tree_sums(files):
    """files {posix path: sha256} -> the SHA256SUMS text ("<sha256>  <path>" per line, sorted by path)"""
    return "".join("%s  %s\n" % (files[p], p) for p in sorted(files))


def dir_files(d):
    out = {}
    for dp, dn, fn in os.walk(d):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            out[os.path.relpath(p, d).replace(os.sep, "/")] = sha_f(p)
    return out


def default_updates_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "BurnoutMashup", "updates")


def free_mb(d):
    if os.environ.get("BMUPDATE_FREE_MB"):            # tests: a simulated free-space value
        return float(os.environ["BMUPDATE_FREE_MB"])
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    return shutil.disk_usage(d).free / 1e6


# ------------------------------------------------------------------------------------------------------------------ versions
def version_info(launcher):
    """this launcher's VERSION.json -> {release, launcher}"""
    v = jload(os.path.join(launcher, VERSION), {}) or {}
    return {"release": v.get("release") or "0.0.0", "launcher": v.get("launcher") or "0.0.0"}


def source_versions(src):
    """the versions a source tree provides: release (launcher/VERSION.json), launcher, kit (tools/_lib/bmkit_env.py KIT_VERSION),
    platform (build/EXPECTED.json build_release identity bmp-<platform>+...)"""
    v = version_info(os.path.join(src, "launcher"))
    kit = None
    try:
        m = re.search(r"""^KIT_VERSION\s*=\s*['"]([^'"]+)['"]""", open(os.path.join(src, "tools", "_lib", "bmkit_env.py"), encoding="utf-8").read(), re.M)
        kit = m.group(1) if m else None
    except OSError:
        pass
    ident = ((jload(os.path.join(src, "build", "EXPECTED.json"), {}) or {}).get("build_release") or {}).get("identity") or ""
    m = re.match(r"^bmp-([0-9.]+)\+", ident)
    return {"release": v["release"], "launcher": v["launcher"], "kit": kit, "platform": m.group(1) if m else None}


# ------------------------------------------------------------------------------------------------------------------ channel config
def _bad_upstream(*texts):
    for t in texts:
        low = (t or "").lower()
        if any(("/%s/" % o) in low or low.startswith(o + "/") or ("%s." % o) in low for o in UPSTREAM_OWNERS):
            return t
        if re.search(r"(^|[/:])takedawn(\.git)?/?$", low.split("?")[0].rstrip("/")) or re.search(r"/takedawn/releases", low):
            return t
    return None


def check_url(u, what="channel"):
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        raise Refused("config", "%s URL %r is not a URL" % (what, u))
    loop = (p.hostname or "") in ("127.0.0.1", "localhost", "::1")
    if p.scheme != "https" and not (p.scheme == "http" and loop):
        raise Refused("config", "%s URL %s: only https:// is used (http only on this PC, for tests)" % (what, u))
    if not p.hostname:
        raise Refused("config", "%s URL %s has no host" % (what, u))
    if _bad_upstream(u):
        raise Refused("upstream", "%s URL %s names the upstream Takedawn project: refused (not a Burnout Mashup channel)" % (what, u))


def load_config(launcher):
    """-> {configured: False, why} or {configured: True, id, kind, base, repo, keys [lines], fingerprints, minimum}. Raises Refused."""
    p = os.path.join(launcher, CONFIG)
    c = jload(p)
    if not isinstance(c, dict) or c.get("format") != "bm-update-channel 1":
        raise Refused("config", "%s is missing or not a bm-update-channel 1 file" % p)
    ch = c.get("channel") or {}
    cid, url, repo = (ch.get("id") or "").strip(), (ch.get("url") or "").strip(), (ch.get("github_repo") or "").strip()
    keys = c.get("trusted_keys") or []
    minimum = c.get("minimum") or {}
    for k, v in minimum.items():
        if k not in ("launcher", "kit", "platform") or version_key(v) is None:
            raise Refused("config", "update_channel.json minimum.%s = %r is not a version" % (k, v))
    if not (url or repo):
        return {"configured": False, "why": NO_CHANNEL, "keys": len(keys), "minimum": minimum}
    if url and repo:
        raise Refused("config", "update_channel.json names both channel.url and channel.github_repo: give one")
    if not re.match(r"^[a-z0-9][a-z0-9._-]{0,63}$", cid):
        raise Refused("config", "update_channel.json channel.id must be a short lower-case name (e.g. burnoutmashup-stable)")
    if "takedawn" in cid or _bad_upstream(repo, url):
        raise Refused("upstream", "the configured channel (%s) names the upstream Takedawn project: refused" % (repo or url or cid))
    if repo:
        if not re.match(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$", repo):
            raise Refused("config", "channel.github_repo must be OWNER/NAME")
        owner, name = repo.lower().split("/")
        if owner in UPSTREAM_OWNERS or name in ("takedawn", "takedawn.git"):
            raise Refused("upstream", "channel.github_repo %s is the upstream Takedawn repository (or named like it): refused" % repo)
        base = "https://github.com/%s/releases/" % repo
    else:
        check_url(url)
        base = url if url.endswith("/") else url + "/"
    lines, fps = [], []
    for k in keys:
        line = k.get("key") if isinstance(k, dict) else k
        try:
            raw, fp = bmed25519.parse_public_key(line)
        except bmed25519.SignatureError as e:
            raise Refused("config", "update_channel.json trusted_keys: %s" % e)
        lines.append(line)
        fps.append(fp)
    if not lines:
        raise Refused("config", "update_channel.json names a channel but trusts no signing key: nothing could be verified, so nothing is checked")
    return {"configured": True, "id": cid, "kind": "github" if repo else "url", "base": base, "repo": repo, "keys": lines,
            "fingerprints": fps, "minimum": minimum, "namespace": c.get("namespace") or bmed25519.NAMESPACE}


def manifest_url(cfg, version=None):
    if version is not None and not VER_RE.match(version):
        raise Refused("config", "%r is not a version" % version)
    if cfg["kind"] == "github":
        return cfg["base"] + ("latest/download/" if version is None else "download/v%s/" % version) + ASSET
    return urllib.parse.urljoin(cfg["base"], ASSET if version is None else "releases/%s/%s" % (version, ASSET))


# ------------------------------------------------------------------------------------------------------------------ network (on request only)
def _net(url):
    if not NET["allowed"]:
        raise Refused("policy", "internal: network use without a user request is not allowed (refused)")
    check_url(url, "download")


def http_get(url, limit=1 << 20, timeout=30):
    _net(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            check_url(r.geturl(), "redirect")
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Refused("channel", "%s: not found (HTTP 404) - no release published there (yet)" % url, RC_FAILED)
        raise Refused("channel", "%s: HTTP %d %s" % (url, e.code, e.reason), RC_FAILED)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise Refused("offline", "%s cannot be reached (%s)" % (url, getattr(e, "reason", e)), RC_OFFLINE)
    if len(data) > limit:
        raise Refused("manifest", "%s is larger than %d bytes: not a release manifest" % (url, limit))
    return data


def fetch_resumable(urls, dest, sha, size, progress=None, cancelled=None, log=print, timeout=60):
    """download to dest via dest.part (+ dest.part.json); continues a kept part with an HTTP Range request (a server that does not
    answer 206 sends it again from the start). sha256 + size checked at the end; a wrong file is deleted. -> dest"""
    part, meta = dest + ".part", dest + ".part.json"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    m = jload(meta, {}) or {}
    if os.path.exists(part) and (m.get("sha256") != sha or m.get("size") != size or os.path.getsize(part) > size):
        os.remove(part)
    jsave(meta, {"sha256": sha, "size": size})
    last_err = None
    for url in urls:
        _net(url)
        have = os.path.getsize(part) if os.path.exists(part) else 0
        hdr = {"User-Agent": UA}
        if 0 < have < size:
            hdr["Range"] = "bytes=%d-" % have
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
                check_url(r.geturl(), "redirect")
                code = getattr(r, "status", 200)
                if have and code == 206:
                    cr = r.headers.get("Content-Range") or ""
                    if not cr.startswith("bytes %d-" % have):
                        raise Refused("download", "the server resumed at another position (%s)" % cr, RC_FAILED)
                    mode = "ab"
                    log("continuing the download at %.1f MB" % (have / 1e6))
                else:
                    if have:
                        log("the server does not continue partial downloads: starting again")
                    have, mode = 0, "wb"
                total = r.headers.get("Content-Length")
                if total and have + int(total) != size:
                    os.remove(part) if os.path.exists(part) else None
                    raise Refused("integrity", "the server offers %d bytes, the signed manifest names %d: not the release archive"
                                  % (have + int(total), size))
                with open(part, mode) as f:
                    got, t0 = have, 0
                    while True:
                        if cancelled and cancelled():
                            raise Cancelled()
                        blk = r.read(1 << 18)
                        if not blk:
                            break
                        got += len(blk)
                        if got > size:
                            f.close()
                            os.remove(part)
                            raise Refused("integrity", "the server sent more than the %d bytes the signed manifest names" % size)
                        f.write(blk)
                        if progress and time.time() - t0 > 0.3:
                            progress(got, size)
                            t0 = time.time()
            last_err = None
        except urllib.error.HTTPError as e:
            last_err = Refused("download", "HTTP %d from %s" % (e.code, url), RC_FAILED)
            continue
        except (urllib.error.URLError, OSError, TimeoutError, ConnectionError) as e:
            n = os.path.getsize(part) if os.path.exists(part) else 0
            last_err = Refused("download", "interrupted after %.1f of %.1f MB (%s); the part is kept: download again continues"
                               % (n / 1e6, size / 1e6, getattr(e, "reason", e)), RC_FAILED)
            if isinstance(getattr(e, "reason", None), (ConnectionRefusedError, OSError)) and n == 0:
                last_err = Refused("offline", "%s cannot be reached (%s)" % (url, getattr(e, "reason", e)), RC_OFFLINE)
            continue
        n = os.path.getsize(part)
        if n < size:
            last_err = Refused("download", "the download ended after %.1f of %.1f MB; the part is kept: download again continues"
                               % (n / 1e6, size / 1e6), RC_FAILED)
            continue
        got_sha = sha_f(part)
        if got_sha != sha:
            os.remove(part)
            os.remove(meta)
            raise Refused("integrity", "sha256 of the downloaded archive is %s, the signed manifest names %s: deleted, not used" % (got_sha, sha))
        os.replace(part, dest)
        os.remove(meta)
        return dest
    raise last_err or Refused("download", "no download URL worked", RC_FAILED)


# ------------------------------------------------------------------------------------------------------------------ the manifest
def verify_manifest(cfg, data, sig, url=None):
    """signature FIRST (no field is read before it verified), then the schema. -> manifest dict (+ _sha256, _signer, _url)"""
    try:
        signer = bmed25519.verify_sshsig(sig, data, cfg["namespace"], cfg["keys"])
    except bmed25519.SignatureError as e:
        raise Refused("signature", "release manifest refused: %s" % e)
    try:
        m = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise Refused("manifest", "the signed manifest is not JSON (%s)" % e)

    def need(cond, what):
        if not cond:
            raise Refused("manifest", "the signed manifest is not valid: %s" % what)
    need(isinstance(m, dict) and m.get("format") == FORMAT, "format is not %s" % FORMAT)
    if m.get("product") != PRODUCT:
        raise Refused("upstream", "the manifest is for %r, not %s: refused" % (m.get("product"), PRODUCT))
    need(m.get("channel") == cfg["id"], "channel %r is not the configured channel %r" % (m.get("channel"), cfg["id"]))
    need(version_key(m.get("version")) is not None, "version %r" % m.get("version"))
    need(isinstance(m.get("serial"), int) and not isinstance(m.get("serial"), bool) and m["serial"] >= 1, "serial (a whole number >= 1)")
    need(isinstance(m.get("created"), str) and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", m["created"]), "created (UTC, 2026-11-01T12:00:00Z)")
    s = m.get("source") or {}
    a = s.get("archive") or {}
    need(isinstance(a.get("name"), str) and re.match(r"^[A-Za-z0-9._-]{1,120}\.zip$", a["name"]), "source.archive.name (a .zip file name)")
    need(isinstance(a.get("sha256"), str) and HEX64.match(a["sha256"]), "source.archive.sha256")
    need(isinstance(a.get("size"), int) and 0 < a["size"] <= 4 << 30, "source.archive.size")
    need(isinstance(a.get("urls"), list) and a["urls"] and all(isinstance(u, str) for u in a["urls"]), "source.archive.urls")
    need(isinstance(s.get("tree_sha256"), str) and HEX64.match(s["tree_sha256"]), "source.tree_sha256")
    need(isinstance(s.get("files"), int) and 0 < s["files"] <= 50000, "source.files")
    need(isinstance(s.get("top_folder"), str) and re.match(r"^[A-Za-z0-9._-]{1,80}$", s["top_folder"]) and s["top_folder"] not in (".", ".."), "source.top_folder")
    need(isinstance(s.get("tag"), str) and isinstance(s.get("commit"), str) and re.match(r"^[0-9a-f]{40}$", s["commit"]), "source.tag / source.commit")
    e = m.get("expected") or {}
    need(isinstance(e.get("expected_json_sha256"), str) and HEX64.match(e["expected_json_sha256"]), "expected.expected_json_sha256")
    need(isinstance(e.get("exe_sha256"), str) and HEX64.match(e["exe_sha256"]), "expected.exe_sha256")
    need(isinstance(e.get("identity"), str) and IDENT_RE.match(e["identity"]), "expected.identity")
    need(e.get("exe") == bmhost.EXE and e.get("profile") == "release", "expected.exe / profile (BurnoutMashup.exe, release)")
    for sec in ("provides", "requires"):
        need(isinstance(m.get(sec), dict) and all(k in ("launcher", "kit", "platform", "release") and version_key(v) is not None
                                                  for k, v in m[sec].items()), "%s (versions)" % sec)
    need(m["provides"].get("release") == m["version"], "provides.release = version")
    need(isinstance(m.get("notes_url", ""), str), "notes_url")
    pk = m.get("package")
    if pk is not None:                  # rel020: the Windows package (layout 2)
        need(isinstance(pk, dict) and pk.get("layout") == LAYOUT2 and pk.get("app_folder") == bmpaths.APP, "package.layout / app_folder")
        need(isinstance(pk.get("name"), str) and re.match(r"^[A-Za-z0-9._-]{1,120}\.zip$", pk["name"]), "package.name (a .zip file name)")
        need(isinstance(pk.get("sha256"), str) and HEX64.match(pk["sha256"]), "package.sha256")
        need(isinstance(pk.get("size"), int) and 0 < pk["size"] <= 4 << 30, "package.size")
        need(isinstance(pk.get("urls"), list) and pk["urls"] and all(isinstance(u, str) for u in pk["urls"]), "package.urls")
        need(isinstance(pk.get("files"), int) and 0 < pk["files"] <= 50000, "package.files")
        need(isinstance(pk.get("tree_sha256"), str) and HEX64.match(pk["tree_sha256"]), "package.tree_sha256")
        ex = pk.get("exes")
        need(isinstance(ex, dict) and sorted(ex) == sorted(PACKAGE_EXES) and all(isinstance(v, str) and HEX64.match(v) for v in ex.values()),
             "package.exes (%s)" % ", ".join(PACKAGE_EXES))
    base = url or manifest_url(cfg)
    m["_urls"] = [urllib.parse.urljoin(base, u) for u in a["urls"]]
    m["_pkg_urls"] = [urllib.parse.urljoin(base, u) for u in pk["urls"]] if pk else []
    for u in m["_urls"] + m["_pkg_urls"] + ([m["notes_url"]] if m.get("notes_url") else []):
        check_url(u, "release")
    m["_sha256"], m["_signer"], m["_url"] = sha_b(data), signer, base
    return m


def decide(m, cfg, st, launcher, current, older=False):
    """compatibility, replay and version rules -> "available" | "up_to_date" | "older". Raises Refused."""
    me = version_info(launcher)
    req = m["requires"]
    if req.get("launcher") and vcmp(me["launcher"], req["launcher"]) < 0:
        raise Refused("incompatible", "release %s needs launcher %s or newer; this launcher is %s" % (m["version"], req["launcher"], me["launcher"]))
    for k, low in sorted((cfg.get("minimum") or {}).items()):
        have = m["provides"].get(k)
        if have is None or vcmp(have, low) < 0:
            raise Refused("incompatible", "release %s provides %s %s; this installation needs at least %s (update_channel.json minimum)"
                          % (m["version"], k, have or "nothing", low))
    seen = (st.get("seen") or {}).get(cfg["id"]) or {}
    if not older and seen:
        if m["serial"] < seen.get("serial", 0):
            raise Refused("replay", "the channel served manifest serial %d (version %s); serial %d (version %s) was already seen here"
                          % (m["serial"], m["version"], seen["serial"], seen.get("version")))
        if m["serial"] == seen.get("serial") and m["_sha256"] != seen.get("manifest_sha256"):
            raise Refused("replay", "the channel served a DIFFERENT manifest with the already seen serial %d" % m["serial"])
    c = vcmp(m["version"], current)
    if older:
        if c >= 0:
            raise Refused("downgrade", "install-older: %s is not older than the version in use (%s); use check" % (m["version"], current))
        return "older"
    if c < 0:
        raise Refused("downgrade", "the channel's release %s is OLDER than the version in use (%s)" % (m["version"], current))
    return "up_to_date" if c == 0 else "available"


# ------------------------------------------------------------------------------------------------------------------ the updater
class Updater:
    def __init__(self, launcher=None, updates=None, sources_dir=None, out=print, events=False, build_fn=None, cancelled=None):
        self.launcher = os.path.abspath(launcher or LAUNCHER)
        self.updates = os.path.abspath(updates or default_updates_dir())
        self.sources_dir = os.path.abspath(sources_dir) if sources_dir else None
        self.out, self.events = out, events
        self.build_fn = build_fn or self._bmbuild
        self._cancelled = cancelled
        self.cancel_file = os.path.join(self.updates, "CANCEL")
        self.inst = bmpaths.install_root(self.launcher)       # rel020: the package layout (None: a source checkout)
        self.tree = bmpaths.tree_root(self.launcher)

    def pkg(self, m):
        """the package section when this install is the Windows package (layout 2) and the release has one, else None"""
        return m.get("package") if self.inst else None

    def archive_of(self, m):
        pk = self.pkg(m)
        return (pk, m["_pkg_urls"]) if pk else (m["source"]["archive"], m["_urls"])

    def say(self, s):
        self.out(s)

    def ev(self, **kw):
        if self.events:
            self.out("@@ " + json.dumps(kw, sort_keys=True))

    def cancelled(self):
        return os.path.exists(self.cancel_file) or bool(self._cancelled and self._cancelled())

    def state(self):
        return bmhost.load_update_state(self.launcher)

    def save(self, st):
        bmhost.save_update_state(self.launcher, st)

    def current(self):
        src = bmhost.active_source(self.launcher)
        return src, (source_versions(src)["release"] if src else version_info(self.launcher)["release"])

    def config(self):
        cfg = load_config(self.launcher)
        if not cfg["configured"]:
            raise Refused("no_channel", NO_CHANNEL, RC_NOCHANNEL)
        return cfg

    # ---- status (no network)
    def status(self):
        try:
            cfg = load_config(self.launcher)
        except Refused as e:
            cfg = {"configured": False, "why": "%s (%s)" % (e, e.cls)}
        src, cur = self.current()
        st = self.state()
        hl = bmhost.folder_state(os.path.join(self.launcher, "host-local"))
        p = st.get("pending") or {}
        nxt = None
        if p:
            nxt = "build" if p.get("prepared") else "prepare" if p.get("archive") else "download"
            if self.inst and p.get("prepared") and not p.get("installed"):
                nxt = "install"
        return {"configured": cfg.get("configured", False), "channel": cfg.get("id"), "where": cfg.get("repo") or cfg.get("base"),
                "trusted_keys": cfg.get("fingerprints", []), "why": cfg.get("why"), "version": cur, "source": src,
                "launcher_version": version_info(self.launcher)["launcher"], "host": hl.get("identity") if hl["ok"] else None,
                "previous": (st.get("previous") or {}).get("version"), "previous_source": (st.get("previous") or {}).get("source"),
                "pending": {k: p.get(k) for k in ("version", "older", "archive", "prepared", "installed")} if p else None, "next_step": nxt,
                "automatic_checks": False, "layout": 2 if self.inst else 1,
                "kept_previous": (bmlayout.previous_of(self.inst) or {}).get("version") if self.inst else None}

    # ---- check
    def _get_manifest(self, cfg, version=None):
        url = manifest_url(cfg, version)
        self.say("checking %s (signed release manifest)" % url)
        data = http_get(url)
        sig = http_get(url + ".sig", limit=16 << 10)
        return url, data, sig

    def check(self, version=None, older=False):
        cfg = self.config()
        st = self.state()
        src, cur = self.current()
        url, data, sig = self._get_manifest(cfg, version)
        m = verify_manifest(cfg, data, sig, url)
        verdict = decide(m, cfg, st, self.launcher, cur, older=older)
        if not older:                       # the newest serial seen (replay protection) moves forward only
            seen = st.setdefault("seen", {})
            if m["serial"] >= (seen.get(cfg["id"]) or {}).get("serial", 0):
                seen[cfg["id"]] = {"serial": m["serial"], "version": m["version"], "manifest_sha256": m["_sha256"]}
        res = {"verdict": verdict, "version": m["version"], "current": cur, "created": m["created"], "signer": m["_signer"],
               "size_mb": round(self.archive_of(m)[0]["size"] / 1e6, 1), "package": bool(self.pkg(m)), "notes_url": m.get("notes_url"), "notes": m.get("notes"),
               "tag": m["source"]["tag"], "commit": m["source"]["commit"], "expected_identity": m["expected"]["identity"]}
        if verdict == "up_to_date":
            self.save(st)
            return res
        d = os.path.join(self.updates, "manifests", cfg["id"])
        os.makedirs(d, exist_ok=True)
        mp = os.path.join(d, "%s-%d.json" % (m["version"], m["serial"]))
        with open(mp, "wb") as f:
            f.write(data)
        with open(mp + ".sig", "wb") as f:
            f.write(sig)
        st["pending"] = {"channel": cfg["id"], "version": m["version"], "serial": m["serial"], "older": older, "manifest": mp,
                         "manifest_sha256": m["_sha256"], "url": url, "archive": None, "prepared": None,
                         "checked": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.save(st)
        res["what_happens"] = self.plan_text(m, src)
        return res

    def plan_text(self, m, src):
        pk = self.pkg(m)
        if pk:
            return ["download %s (%.1f MB) into %s (sha256 + size checked)" % (pk["name"], pk["size"] / 1e6, os.path.join(self.updates, "downloads")),
                    "unpack it into app\\.update\\stage (the version in use is not changed) and verify every file and both exes",
                    "install: the program folder app\\ and the two exes are replaced in ONE step that is undone on any error; then the "
                    "launcher starts again (version %s is kept: 'Switch back')" % version_info(self.launcher)["release"],
                    "carried over unchanged: gamedata\\ (your game copy and mods), profile (saves, settings, approvals), your builds "
                    "(host-local), the Workbench's settings and anything else you added",
                    ("the new release uses the same reference host as your build: no rebuild" if self.host_same(m) else
                     "the new release has another reference host: then Build Mashup (about 3 minutes; your build stays until it is replaced)")]
        return ["download %s (%.1f MB) into %s (sha256 + size checked)" % (m["source"]["archive"]["name"], m["source"]["archive"]["size"] / 1e6,
                                                                       os.path.join(self.updates, "downloads")),
                "unpack it into a NEW folder %s (your current source %s is not changed)" % (self.target_dir(m, probe=True), src),
                "BUILD MASHUP from the new source with YOUR game (about 3 minutes clean, less with the build cache); the built "
                "BurnoutMashup.exe must be identical to the release's reference %s" % m["expected"]["exe_sha256"][:12],
                "install it into host-local; the build in use becomes the previous one ('Switch back' restores build and source)",
                "not touched: your profile, saves, settings, mods, plugin approvals and game data"]

    # ---- pending manifest (re-verified at every step)
    def pending(self, need=None):
        cfg = self.config()
        st = self.state()
        p = st.get("pending")
        if not p:
            raise Refused("pending", "no update is pending: run check first")
        if p.get("channel") != cfg["id"]:
            raise Refused("pending", "the pending update is from another channel: run check again")
        try:
            data = open(p["manifest"], "rb").read()
            sig = open(p["manifest"] + ".sig", "rb").read()
        except OSError:
            raise Refused("pending", "the checked manifest is gone from the download cache: run check again")
        m = verify_manifest(cfg, data, sig, p.get("url"))
        if m["_sha256"] != p["manifest_sha256"]:
            raise Refused("signature", "the cached manifest changed since the check: run check again")
        _, cur = self.current()
        decide(m, cfg, st, self.launcher, cur, older=p.get("older", False))
        if need and not p.get(need):
            raise Refused("pending", "run %s first" % {"archive": "download", "prepared": "prepare"}[need])
        return cfg, st, p, m

    def host_same(self, m):
        hl = bmhost.folder_state(os.path.join(self.launcher, "host-local"))
        return bool(hl["ok"] and hl.get("sha256") == m["expected"]["exe_sha256"])

    # ---- download
    def download(self):
        cfg, st, p, m = self.pending()
        a, urls = self.archive_of(m)
        dest = os.path.join(self.updates, "downloads", "%s-%s" % (a["sha256"][:16], a["name"]))
        if os.path.isfile(dest) and os.path.getsize(dest) == a["size"] and sha_f(dest) == a["sha256"]:
            self.say("already downloaded and verified: %s" % dest)
        else:
            have = os.path.getsize(dest + ".part") if os.path.exists(dest + ".part") else 0
            if free_mb(self.updates) < (a["size"] - have) / 1e6 + 50:
                raise Refused("space", "%s needs %.0f MB free" % (self.updates, (a["size"] - have) / 1e6 + 50))
            if os.path.exists(self.cancel_file):
                os.remove(self.cancel_file)
            self.ev(ev="update", step="download", status="running")
            try:
                fetch_resumable(urls, dest, a["sha256"], a["size"], log=self.say, cancelled=self.cancelled,
                                progress=lambda n, t: (self.ev(ev="download", bytes=n, total=t) if self.events else self.say("  %.1f / %.1f MB" % (n / 1e6, t / 1e6))))
            except Cancelled:
                self.ev(ev="update", step="download", status="cancelled")
                raise
        st["pending"]["archive"] = dest
        self.save(st)
        self.ev(ev="update", step="download", status="done")
        return {"archive": dest, "sha256": a["sha256"], "size": a["size"]}

    # ---- prepare
    def target_dir(self, m, probe=False):
        src, _ = self.current()
        base = self.sources_dir or os.path.dirname(src or os.path.dirname(self.launcher))
        name = "BurnoutMashup-%s" % m["version"]
        t, i = os.path.join(base, name), 2
        while os.path.exists(t) or os.path.exists(t + ".partial"):
            if probe:
                break
            t, i = os.path.join(base, "%s-%d" % (name, i)), i + 1
        return t

    def prepare(self):
        cfg, st, p, m = self.pending("archive")
        if self.pkg(m):
            return self.prepare_package(st, p, m)
        a, s = m["source"]["archive"], m["source"]
        if sha_f(p["archive"]) != a["sha256"]:
            raise Refused("integrity", "the downloaded archive changed since the download: run download again")
        if p.get("prepared") and os.path.isdir(p["prepared"]):
            self.verify_source(p["prepared"], m)
            self.say("already prepared and verified: %s" % p["prepared"])
            return {"source": p["prepared"]}
        if os.path.exists(self.cancel_file):
            os.remove(self.cancel_file)
        target = self.target_dir(m)
        part = target + ".partial"
        try:
            z = zipfile.ZipFile(p["archive"])
        except (zipfile.BadZipFile, OSError) as e:
            raise Refused("archive", "the archive cannot be read (%s)" % e)
        with z:
            infos = self.safe_members(z, s["top_folder"])
            total = sum(i.file_size for i in infos)
            if len(infos) != s["files"]:
                raise Refused("source", "the archive holds %d files, the signed manifest names %d" % (len(infos), s["files"]))
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if free_mb(os.path.dirname(target)) < total / 1e6 + 50:
                    raise Refused("space", "%s needs %.0f MB free" % (os.path.dirname(target), total / 1e6 + 50))
                os.makedirs(part)
            except OSError as e:
                raise Refused("folder", "cannot make %s (%s)" % (part, e.strerror or e))
            self.ev(ev="update", step="prepare", status="running")
            try:
                n = len(s["top_folder"]) + 1
                for i in infos:
                    if self.cancelled():
                        raise Cancelled()
                    rel = i.filename[n:]
                    dst = os.path.join(part, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with z.open(i) as r, open(dst, "wb") as w:
                        shutil.copyfileobj(r, w, 1 << 20)
                self.verify_source(part, m)
            except BaseException:
                shutil.rmtree(part, ignore_errors=True)
                raise
        os.rename(part, target)
        st["pending"]["prepared"] = target
        self.save(st)
        self.ev(ev="update", step="prepare", status="done")
        return {"source": target, "files": s["files"]}

    # ---- the Windows package (layout 2, rel020)
    def stage_dir(self, m):
        return os.path.join(bmlayout.update_dir(self.inst), "stage", m["version"])

    @staticmethod
    def safe_package_members(z):
        """the package's entries: exactly the two exes and app/... (+ the empty folders gamedata/, gamedata/mods/); safe paths only"""
        out = []
        bad = re.compile(r"(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.[^/]*)?$", re.I)
        for i in z.infolist():
            n = i.filename
            parts = n.split("/")
            if ("\\" in n or ":" in n or n.startswith("/") or "\x00" in n or ".." in parts or bad.search(n.rstrip("/"))
                    or any(x.endswith((" ", ".")) for x in parts[:-1] + ([parts[-1]] if parts[-1] else []))):
                raise Refused("package", "unsafe path in the package: %r" % n)
            if stat.S_ISLNK(i.external_attr >> 16):
                raise Refused("package", "the package holds a symbolic link (%s): refused" % n)
            if n.endswith("/"):
                if n not in ("gamedata/", "gamedata/mods/") and not n.startswith(bmpaths.APP + "/"):
                    raise Refused("package", "unexpected folder in the package: %r" % n)
                continue
            if n in PACKAGE_EXES or (parts[0] == bmpaths.APP and len(parts) >= 2 and parts[-1]):
                out.append(i)
                continue
            raise Refused("package", "unexpected entry in the package: %r (only the two exes and app/...)" % n)
        if sum(i.file_size for i in out) > 4 << 30:
            raise Refused("package", "the package unpacks to more than 4 GB")
        return out

    def verify_stage(self, d, m):
        """the unpacked package = the signed digest; the exes = the signed sha256; app\\ = the signed SOURCE tree (+ verify_source)"""
        pk = m["package"]
        files = dir_files(d)
        if len(files) != pk["files"] or sha_b(tree_sums(files).encode("utf-8")) != pk["tree_sha256"]:
            raise Refused("package", "the unpacked package is not the signed one (digest differs)")
        for e in PACKAGE_EXES:
            if files.get(e) != pk["exes"][e]:
                raise Refused("package", "%s is not the signed one" % e)
        app = os.path.join(d, bmpaths.APP)
        self.verify_source(app, m)
        sh = bmlayout.read_sums(os.path.join(app, bmlayout.SHIPPED)) if os.path.isfile(os.path.join(app, bmlayout.SHIPPED)) else None
        tree = {k[len(bmpaths.APP) + 1:]: v for k, v in files.items() if k.startswith(bmpaths.APP + "/")}
        tree.pop(bmlayout.SHIPPED, None)
        if sh != tree:
            raise Refused("package", "app\\%s does not list the package's program files" % bmlayout.SHIPPED)
        return files

    def prepare_package(self, st, p, m):
        pk = m["package"]
        if sha_f(p["archive"]) != pk["sha256"]:
            raise Refused("integrity", "the downloaded package changed since the download: run download again")
        target = self.stage_dir(m)
        if p.get("prepared") and os.path.isdir(p["prepared"]):
            self.verify_stage(p["prepared"], m)
            self.say("already prepared and verified: %s" % p["prepared"])
            return {"source": p["prepared"]}
        part = target + ".partial"
        for x in (part, target):
            if os.path.exists(x):
                shutil.rmtree(x)
        try:
            z = zipfile.ZipFile(p["archive"])
        except (zipfile.BadZipFile, OSError) as e:
            raise Refused("package", "the package cannot be read (%s)" % e)
        with z:
            infos = self.safe_package_members(z)
            if len(infos) != pk["files"]:
                raise Refused("package", "the package holds %d files, the signed manifest names %d" % (len(infos), pk["files"]))
            total = sum(i.file_size for i in infos)
            if free_mb(self.inst) < total / 1e6 + 50:
                raise Refused("space", "%s needs %.0f MB free" % (self.inst, total / 1e6 + 50))
            os.makedirs(part)
            self.ev(ev="update", step="prepare", status="running")
            try:
                for i in infos:
                    if self.cancelled():
                        raise Cancelled()
                    dst = os.path.join(part, *i.filename.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with z.open(i) as r, open(dst, "wb") as w:
                        shutil.copyfileobj(r, w, 1 << 20)
                self.verify_stage(part, m)
            except BaseException:
                shutil.rmtree(part, ignore_errors=True)
                raise
        os.rename(part, target)
        st["pending"]["prepared"] = target
        self.save(st)
        self.ev(ev="update", step="prepare", status="done")
        return {"source": target, "files": pk["files"]}

    def install(self, fail_after=None):
        """the prepared package replaces app\\ and the exes (bmlayout: one transaction of renames, undone on any error)"""
        if not self.inst:
            raise Refused("pending", "install is the step of the Windows package; this is a source checkout: use build", RC_USAGE)
        cfg, st, p, m = self.pending("prepared")
        if not self.pkg(m) or p.get("installed"):
            raise Refused("pending", "nothing to install (run check / download / prepare first)")
        stage = p["prepared"]
        self.verify_stage(stage, m)
        os.chdir(self.inst)                     # never work inside app\ (renamed by the install)
        cur = version_info(self.launcher)["release"]
        same = self.host_same(m)
        # the state the NEW version will read (it is carried over with launcher\update-state)
        st.setdefault("seen", {})
        st["package_active"] = {"version": m["version"], "manifest_sha256": m["_sha256"], "serial": m["serial"],
                                "installed": time.strftime("%Y-%m-%d %H:%M:%S")}
        st["package_previous"] = {"version": cur}
        if same:
            st.pop("pending", None)
        else:
            st["pending"] = dict(p, installed=True, prepared=self.tree)
        self.save(st)
        self.ev(ev="update", step="install", status="running")
        try:
            r = bmlayout.apply_update(self.inst, os.path.join(stage, bmpaths.APP), stage, m["version"], out=self.say, fail_after=fail_after)
        except bmlayout.LayoutError as e:
            st = self.state()            # the old version's state is back in place (undone): drop what install wrote
            for k in ("package_active", "package_previous"):
                st.pop(k, None)
            st["pending"] = p
            self.save(st)
            self.ev(ev="update", step="install", status="failed")
            raise Refused("broken" if e.rc == bmlayout.RC_BROKEN else "install", str(e), RC_FAILED)
        shutil.rmtree(stage, ignore_errors=True)            # now empty
        self.ev(ev="update", step="install", status="done")
        return {"version": m["version"], "previous_version": cur, "kept_as": r["kept_as"], "carried": len(r["moved"]),
                "changed_shipped": r["changed_shipped"], "conflicts": r["conflicts"], "rebuild_needed": not same, "restart": True}

    def verify_installed(self, tree):
        """the program files in use = their SHIPPED_FILES.sha256 (your files beside them do not count)"""
        sh = bmlayout.read_sums(os.path.join(tree, bmlayout.SHIPPED))
        for rel, h in sh.items():
            p = os.path.join(tree, *rel.split("/"))
            if not os.path.isfile(p) or sha_f(p) != h:
                raise Refused("source", "the installed program file %s is missing or changed (remove.cmd verify / repair)" % rel)

    @staticmethod
    def safe_members(z, top):
        out = []
        bad = re.compile(r"(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.[^/]*)?$", re.I)
        for i in z.infolist():
            n = i.filename
            parts = n.split("/")
            if ("\\" in n or ":" in n or n.startswith("/") or re.match(r"^[A-Za-z]:", n) or "\x00" in n or ".." in parts or parts[0] != top
                    or bad.search(n.rstrip("/")) or any(x.endswith((" ", ".")) for x in parts[:-1] + ([parts[-1]] if parts[-1] else []))):
                raise Refused("archive", "unsafe or unexpected path in the archive: %r (all files must be below %s/)" % (n, top))
            if stat.S_ISLNK(i.external_attr >> 16):
                raise Refused("archive", "the archive holds a symbolic link (%s): refused" % n)
            if n.endswith("/"):
                continue
            if len(parts) < 2 or not parts[-1]:
                raise Refused("archive", "unexpected entry %r" % n)
            out.append(i)
        if sum(i.file_size for i in out) > 4 << 30:
            raise Refused("archive", "the archive unpacks to more than 4 GB")
        return out

    def verify_source(self, d, m):
        """the unpacked tree = the signed SHA256SUMS digest, and it is a Burnout Mashup source with the manifest's reference build"""
        files = dir_files(d)
        if len(files) != m["source"]["files"] or sha_b(tree_sums(files).encode("utf-8")) != m["source"]["tree_sha256"]:
            raise Refused("source", "the unpacked tree is not the signed one (SHA256SUMS digest differs)")
        pins = jload(os.path.join(d, "host", "PINS.json"), {}) or {}
        ident = pins.get("identity") or {}
        if ident.get("application") != "Burnout Mashup" or ident.get("release_exe") != bmhost.EXE:
            raise Refused("upstream", "the new source is not a Burnout Mashup source (host/PINS.json identity): refused")
        for rel in ("build/verify.py", "build/EXPECTED.json", "launcher/tools/launcher/bmbuild.py", "launcher/" + VERSION):
            if rel not in files:
                raise Refused("source", "the new source lacks %s" % rel)
        if files["build/EXPECTED.json"] != m["expected"]["expected_json_sha256"]:
            raise Refused("source", "build/EXPECTED.json of the new source is not the one the manifest names")
        br = (jload(os.path.join(d, "build", "EXPECTED.json"), {}) or {}).get("build_release") or {}
        if br.get("exe_sha256") != m["expected"]["exe_sha256"] or br.get("identity") != m["expected"]["identity"]:
            raise Refused("source", "the new source's reference build is not the manifest's")
        sv = source_versions(d)
        if sv["release"] != m["version"]:
            raise Refused("source", "the new source says version %s, the manifest %s" % (sv["release"], m["version"]))
        return files

    # ---- build + install
    def _bmbuild(self, argv, out):
        import bmbuild
        return bmbuild.main(argv, out=out)

    def build(self, build_args=()):
        cfg, st, p, m = self.pending("prepared")
        target = p["prepared"]
        if self.inst and self.pkg(m) and not p.get("installed"):
            raise Refused("pending", "run install first (the package replaces the program; then build if the reference host changed)")
        if p.get("installed"):
            self.verify_installed(target)               # the package in use (your files beside it do not count)
        else:
            self.verify_source(target, m)
        src, cur = self.current()
        args = list(build_args)
        if "--input" not in args or "--source" not in args:            # from the last build (BUILD_STATE.json of the build folder)
            bd = args[args.index("--build-dir") + 1] if "--build-dir" in args else None
            if not bd:
                import bmbuild
                bd = bmbuild.default_build_dir()
            last = jload(os.path.join(bd, "BUILD_STATE.json"), {}) or {}
            if "--input" not in args and (last.get("input") or {}).get("path"):
                args += ["--input", last["input"]["path"]]
            srcs = last.get("sources") or {}
            if "--source" not in args and srcs.get("mode"):
                args += ["--source", srcs["mode"]]
                if srcs["mode"] != "github" and "--takedawn-src" not in args:
                    args += ["--takedawn-src", srcs.get("takedawn", ""), "--xboxrecomp-src", srcs.get("xboxrecomp", "")]
        if "--input" not in args:
            raise Refused("pending", "build needs --input YOUR_GAME (no earlier build to take it from)", RC_USAGE)
        for x in ("--repo", "--launcher", "--profile", "--no-install"):
            if x in args:
                raise Refused("pending", "%s is set by the updater" % x, RC_USAGE)
        loc = os.path.join(self.launcher, "host-local")
        before = bmhost.folder_state(loc)
        bsha = before.get("sha256") if before["ok"] else None
        argv = ["build", "--repo", target, "--launcher", self.launcher, "--profile", "release"] + args + (["--events"] if self.events else [])
        self.say("BUILD MASHUP from the new source %s" % target)
        self.ev(ev="update", step="build", status="running")
        lines = []

        def out(s):
            lines.append(s)
            self.out(s)
        rc = self.build_fn(argv, out)
        if rc != 0:
            self.ev(ev="update", step="build", status="cancelled" if rc == RC_CANCELLED else "failed")
            after = bmhost.folder_state(loc)
            unchanged = (after.get("sha256") if after["ok"] else None) == bsha
            if rc == RC_CANCELLED:
                raise Refused("cancelled", "the build was cancelled; the version in use is unchanged%s" % ("" if unchanged else " (CHECK host-local)"), RC_CANCELLED)
            raise Refused("build", "BUILD MASHUP ended with exit %d; the version in use is %s" % (rc, "unchanged" if unchanged else "NOT the same - check host-local"),
                          RC_REFUSED if rc == 2 else RC_FAILED)
        after = bmhost.folder_state(loc)
        if not after["ok"] or after["sha256"] != m["expected"]["exe_sha256"] or after["identity"] != m["expected"]["identity"]:
            if after.get("sha256") and after.get("sha256") != bsha and os.path.isdir(loc + ".prev"):
                bmhost.switch_back(self.launcher, log=self.say)
            raise Refused("build", "the installed program is not the release's reference build (%s): the previous build was restored"
                          % (after.get("sha256") or "none")[:12], RC_FAILED)
        host_changed = after["sha256"] != bsha
        st = self.state()
        if p.get("installed"):                          # the package layout: the program was replaced by install already
            st.pop("pending", None)
            st.setdefault("package_active", {})["host_sha256"] = after["sha256"]
            self.save(st)
            self.ev(ev="update", step="build", status="done")
            return {"version": m["version"], "source": target, "exe_sha256": after["sha256"], "identity": after["identity"],
                    "host_changed": host_changed, "previous_version": (st.get("package_previous") or {}).get("version"),
                    "previous_source": None, "previous_build_kept": os.path.join(self.launcher, "host-local.prev")}
        old = st.get("active") or {"source": src, "version": cur}
        old = dict(old, host_sha256=bsha)
        st["previous"] = old
        st["active"] = {"source": target, "version": m["version"], "host_sha256": after["sha256"], "identity": after["identity"],
                        "manifest_sha256": m["_sha256"], "serial": m["serial"], "installed": time.strftime("%Y-%m-%d %H:%M:%S")}
        st.pop("pending", None)
        self.save(st)
        self.ev(ev="update", step="build", status="done")
        return {"version": m["version"], "source": target, "exe_sha256": after["sha256"], "identity": after["identity"],
                "host_changed": host_changed, "previous_version": old.get("version"), "previous_source": old.get("source"),
                "previous_build_kept": os.path.join(self.launcher, "host-local.prev") if host_changed else "(same program as before)"}

    # ---- switch back / discard
    def switch_back(self, fail_after=None):
        if self.inst and bmlayout.previous_of(self.inst):
            os.chdir(self.inst)
            try:
                r = bmlayout.switch_back(self.inst, out=self.say, fail_after=fail_after)
            except bmlayout.LayoutError as e:
                raise Refused("broken" if e.rc == bmlayout.RC_BROKEN else "switch", str(e), RC_FAILED)
            return {"now": r["to"], "source": self.tree, "previous": r["from"], "restart": True}
        st = self.state()
        a, b = st.get("active"), st.get("previous")
        if not a or not b:
            raise Refused("switch", "there is no previous version recorded (no update was installed here)")
        if not b.get("source") or not bmhost.is_source(b["source"]):
            raise Refused("switch", "the previous source folder %s is gone: not switched" % b.get("source"))
        loc = os.path.join(self.launcher, "host-local")
        cur, prv = bmhost.folder_state(loc), bmhost.folder_state(loc + ".prev")
        if a.get("host_sha256") != b.get("host_sha256"):
            if cur.get("sha256") != a.get("host_sha256") or not prv["ok"] or prv.get("sha256") != b.get("host_sha256"):
                raise Refused("switch", "host-local / host-local.prev do not hold the recorded builds of %s / %s" % (a.get("version"), b.get("version")))
            try:
                bmhost.switch_back(self.launcher, log=self.say)      # swaps the builds AND (bmhost) the recorded sources
            except bmhost.InstallError as e:
                raise Refused("switch", str(e))
        else:
            bmhost.swap_sources(self.launcher)
        st = self.state()
        return {"now": st["active"].get("version"), "source": st["active"].get("source"), "previous": st["previous"].get("version")}

    def discard(self, yes=False):
        st = self.state()
        p = st.get("pending")
        if not p:
            return {"discarded": False, "reason": "nothing pending"}
        keep = {os.path.normcase(os.path.abspath(x)) for x in ((st.get("active") or {}).get("source"), (st.get("previous") or {}).get("source"),
                                                               bmhost.repo_root(self.launcher)) if x}
        gone = []
        if yes:
            for f in (p.get("archive"),):
                if f and os.path.isfile(f):
                    os.remove(f)
                    gone.append(f)
            d = p.get("prepared")
            if p.get("installed"):
                d = None                                   # the program in use: never removed
            if d and os.path.isdir(d) and os.path.normcase(os.path.abspath(d)) not in keep:
                shutil.rmtree(d)
                gone.append(d)
        st.pop("pending", None)
        self.save(st)
        return {"discarded": True, "removed": gone, "kept_files": not yes}


# ------------------------------------------------------------------------------------------------------------------ maintainers
def make_manifest(a):
    """write a release manifest for a source zip (git archive --format=zip --prefix=TOP/ TAG). Offline."""
    zp = a["zip"]
    z = zipfile.ZipFile(zp)
    tops = {i.filename.split("/")[0] for i in z.infolist()}
    if len(tops) != 1:
        raise Refused("archive", "the zip must hold one top folder (git archive --prefix=NAME/)", RC_USAGE)
    top = tops.pop()
    infos = Updater.safe_members(z, top)
    files = {i.filename[len(top) + 1:]: sha_b(z.read(i)) for i in infos}
    rd = lambda rel: z.read(top + "/" + rel)  # noqa: E731
    exp = json.loads(rd("build/EXPECTED.json").decode("utf-8-sig"))["build_release"]
    ver = json.loads(rd("launcher/" + VERSION).decode("utf-8"))
    kit = re.search(r"""^KIT_VERSION\s*=\s*['"]([^'"]+)['"]""", rd("tools/_lib/bmkit_env.py").decode("utf-8"), re.M).group(1)
    if ver.get("release") != a["version"]:
        raise Refused("source", "launcher/VERSION.json in the zip says release %s, not %s: set it before tagging" % (ver.get("release"), a["version"]), RC_USAGE)
    m = {"format": FORMAT, "product": PRODUCT, "channel": a["channel"], "version": a["version"], "serial": int(a["serial"]),
         "created": a.get("created") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "source": {"tag": a["tag"], "commit": a["commit"], "top_folder": top, "files": len(files), "tree_sha256": sha_b(tree_sums(files).encode("utf-8")),
                    "archive": {"name": os.path.basename(zp), "sha256": sha_f(zp), "size": os.path.getsize(zp), "urls": a["url"]}},
         "expected": {"expected_json_sha256": files["build/EXPECTED.json"], "exe": bmhost.EXE, "exe_sha256": exp["exe_sha256"],
                      "identity": exp["identity"], "profile": "release"},
         "provides": {"release": a["version"], "launcher": ver.get("launcher"), "kit": kit, "platform": re.match(r"^bmp-([0-9.]+)\+", exp["identity"]).group(1)},
         "requires": {"launcher": a.get("requires_launcher") or ver.get("launcher")},
         "notes_url": a.get("notes_url") or ""}
    if a.get("notes"):
        m["notes"] = a["notes"]
    if a.get("package"):
        m["package"] = package_section(a["package"], files, a.get("package_url") or [os.path.basename(a["package"])])
        m["requires"]["launcher"] = a.get("requires_launcher") or "1.1.0"
    data = (json.dumps(m, indent=1, sort_keys=True) + "\n").encode("utf-8")
    with open(a["out"], "wb") as f:
        f.write(data)
    if a.get("sums"):
        with open(a["sums"], "w", encoding="utf-8", newline="\n") as f:
            f.write(tree_sums(files))
    return {"manifest": a["out"], "sha256": sha_b(data), "files": len(files), "tree_sha256": m["source"]["tree_sha256"]}


def package_section(zp, source_files, urls):
    """the manifest's package section for a Windows package zip; its app/ must be the source zip's tree byte for byte"""
    z = zipfile.ZipFile(zp)
    infos = Updater.safe_package_members(z)
    files = {i.filename: sha_b(z.read(i)) for i in infos}
    app = {k[len(bmpaths.APP) + 1:]: v for k, v in files.items() if k.startswith(bmpaths.APP + "/")}
    if app != source_files:
        raise Refused("package", "the package's app/ is not the source tree (%d differences)" % len(set(app.items()) ^ set(source_files.items())), RC_USAGE)
    return {"layout": LAYOUT2, "app_folder": bmpaths.APP, "name": os.path.basename(zp), "sha256": sha_f(zp), "size": os.path.getsize(zp),
            "urls": list(urls), "files": len(files), "tree_sha256": sha_b(tree_sums(files).encode("utf-8")),
            "exes": {e: files[e] for e in PACKAGE_EXES}}


# ------------------------------------------------------------------------------------------------------------------ CLI
def parse(argv):
    a = {"cmd": argv[0] if argv else "help", "args": [], "url": [], "build": []}
    flags = {"--yes": "yes", "--events": "events", "--json": "json"}
    own = {"--updates", "--sources-dir", "--launcher", "--zip", "--version", "--serial", "--channel", "--tag", "--commit", "--url",
           "--notes-url", "--notes", "--out", "--sums", "--created", "--requires-launcher", "--package", "--package-url"}
    i = 1
    while i < len(argv):
        x = argv[i]
        if x in flags:
            a[flags[x]] = True
        elif x in own:
            if i + 1 >= len(argv):
                raise SystemExit("usage: %s needs a value" % x)
            if x == "--url":
                a["url"].append(argv[i + 1])
            elif x == "--package-url":
                a.setdefault("package_url", []).append(argv[i + 1])
            else:
                a[x[2:].replace("-", "_")] = argv[i + 1]
            i += 1
        elif x.startswith("--") and a["cmd"] == "build":      # BUILD OPTIONS for bmbuild.py
            a["build"].append(x)
            if x not in ("--download-missing",) and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                a["build"].append(argv[i + 1])
                i += 1
        elif x.startswith("--"):
            raise SystemExit("usage: unknown option %s" % x)
        else:
            a["args"].append(x)
        i += 1
    return a


NETWORK_COMMANDS = ("check", "download", "install-older")


def main(argv=None, out=None):
    argv = sys.argv[1:] if argv is None else argv
    pr = out or (lambda s: print(s, flush=True))
    try:
        a = parse(argv)
    except SystemExit as e:
        pr(str(e))
        return RC_USAGE
    cmd = a["cmd"]
    if cmd in ("help", "-h", "--help"):
        pr(__doc__)
        return RC_OK
    u = Updater(a.get("launcher"), a.get("updates"), a.get("sources_dir"), out=pr, events=a.get("events"))

    def result(rc, cls, msg, rec=None, **kw):
        rec = RECOVERY.get(cls, "") if rec is None else rec
        pr(json.dumps(dict(kw, ok=rc == RC_OK, rc=rc, cls=cls, message=msg, recovery=rec), sort_keys=True))
        u.ev(ev="result", rc=rc, cls=cls, message=msg, recovery=rec)
        return rc
    NET["allowed"] = cmd in NETWORK_COMMANDS          # the one place network use is allowed: a command the user gave
    try:
        if cmd == "status":
            r = u.status()
            pr(json.dumps(r, sort_keys=True))
            pr(("Update channel: %s (%s)" % (r["channel"], r["where"])) if r["configured"] else ("Update channel: none. " + (r["why"] or NO_CHANNEL)))
            pr("Version in use: %s (source %s); previous: %s; next step: %s" % (r["version"], r["source"], r["previous"] or "-", r["next_step"] or "-"))
            return RC_OK
        if cmd == "check":
            r = u.check()
            if r["verdict"] == "up_to_date":
                return result(RC_OK, "up_to_date", "up to date: %s is the newest release of the channel" % r["current"], **r)
            pr("NEW: Burnout Mashup %s (you have %s), %.1f MB, created %s, signed by %s" % (r["version"], r["current"], r["size_mb"], r["created"], r["signer"]))
            if r.get("notes_url"):
                pr("What is new: %s" % r["notes_url"])
            for i, t in enumerate(r["what_happens"], 1):
                pr("  %d. %s" % (i, t))
            return result(RC_OK, "available", "release %s is available; next: download" % r["version"], rec="", **r)
        if cmd == "install-older":
            if not a["args"]:
                pr("usage: install-older VERSION --yes")
                return RC_USAGE
            if not a.get("yes"):
                return result(RC_REFUSED, "older", "install-older %s: not confirmed" % a["args"][0])
            r = u.check(version=a["args"][0], older=True)
            for i, t in enumerate(r["what_happens"], 1):
                pr("  %d. %s" % (i, t))
            return result(RC_OK, "older", "older release %s checked and pending (you chose it); next: download" % r["version"], rec="", **r)
        if cmd == "download":
            r = u.download()
            return result(RC_OK, "downloaded", "downloaded and verified: %s; next: prepare" % r["archive"], rec="", **r)
        if cmd == "prepare":
            r = u.prepare()
            return result(RC_OK, "prepared", "unpacked and verified: %s; next: build" % r["source"], rec="", **r)
        if cmd == "install":
            r = u.install()
            return result(RC_OK, "installed", "Burnout Mashup %s is installed (%d item(s) of your data carried over; %s kept for 'switch-back')%s"
                          % (r["version"], r["carried"], r["previous_version"], "; next: build (the reference host changed)" if r["rebuild_needed"] else ""),
                          rec="", **r)
        if cmd == "build":
            r = u.build(a["build"])
            return result(RC_OK, "installed", "Burnout Mashup %s is installed (%s); 'switch-back' returns to %s" % (r["version"], r["identity"], r["previous_version"]), rec="", **r)
        if cmd == "switch-back":
            r = u.switch_back()
            return result(RC_OK, "switched", "now using %s (source %s); the other version is kept as the previous one" % (r["now"], r["source"]), rec="", **r)
        if cmd == "discard":
            r = u.discard(a.get("yes"))
            return result(RC_OK, "discarded", "pending update forgotten" if r["discarded"] else "nothing pending", rec="", **r)
        if cmd == "cancel":
            os.makedirs(u.updates, exist_ok=True)
            open(u.cancel_file, "w").close()
            import bmbuild
            bd = a["args"][0] if a["args"] else bmbuild.default_build_dir()
            if os.path.isdir(bd):
                open(os.path.join(bd, "CANCEL"), "w").close()
            return result(RC_OK, "cancel", "cancel requested", rec="")
        if cmd == "make-manifest":
            for k in ("zip", "version", "serial", "channel", "tag", "commit", "out"):
                if not a.get(k):
                    pr("usage: make-manifest --zip Z --version V --serial N --channel ID --tag T --commit SHA --url URL [--url URL] --out F "
                       "[--notes-url U] [--sums SHA256SUMS] [--requires-launcher V] [--package WINDOWS_ZIP [--package-url URL]]")
                    return RC_USAGE
            if not a["url"]:
                pr("usage: make-manifest needs at least one --url (where the zip is published; relative to the manifest is allowed)")
                return RC_USAGE
            r = make_manifest(a)
            pr(json.dumps(r, sort_keys=True))
            pr("now sign it:  ssh-keygen -Y sign -f YOUR_KEY -n %s %s" % (bmed25519.NAMESPACE, a["out"]))
            return RC_OK
        if cmd == "verify-manifest":
            if not a["args"]:
                pr("usage: verify-manifest MANIFEST [SIGNATURE]")
                return RC_USAGE
            cfg = u.config()
            mp = a["args"][0]
            m = verify_manifest(cfg, open(mp, "rb").read(), open(a["args"][1] if len(a["args"]) > 1 else mp + ".sig", "rb").read())
            return result(RC_OK, "verified", "signature OK (%s); %s %s serial %d" % (m["_signer"], PRODUCT, m["version"], m["serial"]), rec="")
        pr("usage: unknown command %s (help)" % cmd)
        return RC_USAGE
    except Refused as e:
        return result(e.rc, e.cls, str(e))
    except Cancelled:
        return result(RC_CANCELLED, "cancelled", "cancelled")
    except KeyboardInterrupt:
        return result(RC_CANCELLED, "cancelled", "cancelled")
    finally:
        NET["allowed"] = False
        if cmd in ("download", "prepare") and os.path.exists(u.cancel_file):
            try:
                os.remove(u.cancel_file)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
