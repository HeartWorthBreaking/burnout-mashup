"""bmmods.py - Burnout Mashup player mod management for one bundle folder (release readiness R1; standard library only).

What it does (and never does):
  - lists the mods in mods\\demo, mods\\generated, mods\\user with their mod.toml facts and the compatibility gate (bmcompat)
  - turns mods on / off in the player's mod list (profile\\Roaming\\BurnoutMashup\\mod-list.toml, `disabled = [...]`, the file the
    game's MODS page writes) - written whole to a temporary file then renamed, the previous file kept as mod-list.toml.bak
  - imports a mod folder or .zip into mods\\user (copied; zip entries checked: no absolute / '..' / drive paths, size and count
    limits); a mod that is already there is replaced only on request and the old copy is kept in mods\\.backup\\
  - finds stale profile entries: approvals / settings naming mods that are gone, approvals whose module changed (the game will
    ask again); removing stale entries only ever DELETES lines (backup first)
  - reads the last game's results from the profile log (admitted / refused mods with reasons, plugins run / not run, FATAL)
  - NEVER runs anything from a mod, NEVER writes an approval (native code is approved only in the game's MODS page).

    py -3 -B bmmods.py BUNDLE list | on ID | off ID | import PATH [--replace] | stale | results
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bmcompat  # noqa: E402
import bmpaths  # noqa: E402  (0.2.0 layout 2: mods\\user / mods\\generated in <install>\\gamedata\\mods)

MOD_DIRS = ("demo", "generated", "user")
ZIP_MAX_FILES = 20000
ZIP_MAX_BYTES = 4 * 1024 ** 3
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class ModError(Exception):
    """A refusal with the reason and what to do (shown to the player as it is)."""


class Bundle:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.settings_dir = os.path.join(self.root, "profile", "Roaming", "BurnoutMashup")
        self.mod_list = os.path.join(self.settings_dir, "mod-list.toml")
        self.approvals = os.path.join(self.settings_dir, "plugin-approvals.toml")
        self.plugin_settings = os.path.join(self.settings_dir, "plugin-settings.toml")
        self.log = os.path.join(self.settings_dir, "logs", "run.log")
        self.host_info_path = None
        for d in ("host-local", "host"):
            p = os.path.join(self.root, d, "HOST_INFO.json")
            if (os.path.isfile(os.path.join(self.root, d, "BurnoutMashup.exe")) or os.path.isfile(os.path.join(self.root, d, "burnout3_bmashup.exe"))) \
                    and os.path.isfile(p):
                self.host_info_path = p
                break

    def host_info(self):
        """the installed host's HOST_INFO.json, looked up on every call: a host that Build Mashup installs after this Bundle was made
        counts at once (phase 15 finding D5)"""
        self.host_info_path = None
        for d in ("host-local", "host"):
            p = os.path.join(self.root, d, "HOST_INFO.json")
            if (os.path.isfile(os.path.join(self.root, d, "BurnoutMashup.exe")) or os.path.isfile(os.path.join(self.root, d, "burnout3_bmashup.exe"))) \
                    and os.path.isfile(p):
                self.host_info_path = p
                break
        return bmcompat.load_host_info(self.host_info_path) if self.host_info_path else None

    # ---- the mod list ----
    def disabled(self):
        if not os.path.isfile(self.mod_list):
            return []
        txt = open(self.mod_list, encoding="utf-8", errors="replace").read()
        m = re.search(r"disabled\s*=\s*\[(.*?)\]", txt, re.S)
        return re.findall(r'"([^"]*)"', m.group(1)) if m else []

    def set_enabled(self, mod_id, on):
        if not _ID.match(mod_id):
            raise ModError("not a mod id: %r" % mod_id)
        off = [x for x in self.disabled() if x != mod_id] + ([] if on else [mod_id])
        os.makedirs(self.settings_dir, exist_ok=True)
        body = "# Burnout Mashup mod list (written by the launcher; the game's MODS page writes the same file)\n" \
               "disabled = [%s]\n" % ", ".join('"%s"' % x for x in off)
        atomic_write(self.mod_list, body, backup=True)
        return off

    # ---- listing ----
    def mods(self):
        found = []
        for d in MOD_DIRS:
            base = bmpaths.mods_dir(self.root, d)
            if not os.path.isdir(base):
                continue
            for name in sorted(os.listdir(base)):
                folder = os.path.join(base, name)
                if os.path.isdir(folder) and os.path.isfile(os.path.join(folder, "mod.toml")):
                    found.append((d, folder))
        info = self.host_info()
        installed = {}
        rows = []
        for d, folder in found:
            man, _ = bmcompat.read_mod(folder)
            if man and man.get("id"):
                installed[str(man["id"])] = str(man.get("version", ""))
        off = set(self.disabled())
        for d, folder in found:
            if info:
                r = bmcompat.check_mod(info, folder, installed)
            else:
                r = {"folder": folder, "id": "", "name": os.path.basename(folder), "version": "", "level": bmcompat.WARN,
                     "reasons": ["needs a built host: compatibility with your host is checked after Build Mashup (not assumed meanwhile)"], "native_code": False,
                     "plugin_file": ""}
                man, why = bmcompat.read_mod(folder)
                if man:
                    r.update(id=str(man.get("id", "")), name=str(man.get("name", "")), version=str(man.get("version", "")),
                             native_code=isinstance(man.get("plugin"), dict))
            r["source"] = d
            r["enabled"] = r["id"] not in off
            rows.append(r)
        ids = [r["id"] for r in rows if r["id"]]
        for r in rows:
            if r["id"] and ids.count(r["id"]) > 1:
                r["level"] = bmcompat.BLOCKED
                r["reasons"].append("the id %s is in more than one mod folder: remove one copy" % r["id"])
        return rows

    # ---- import ----
    def preview(self, src):
        """Facts about a folder / zip BEFORE import (nothing copied): dict(id, name, version, files, bytes, native_code, ...)."""
        with _staged(src) as folder:
            man, why = bmcompat.read_mod(folder)
            if man is None:
                raise ModError(why + " - a mod is a folder with mod.toml at its top")
            files, size, exe = 0, 0, []
            for dp, _, fn in os.walk(folder):
                for f in fn:
                    files += 1
                    size += os.path.getsize(os.path.join(dp, f))
                    if f.lower().endswith((".asi", ".dll", ".exe", ".bat", ".cmd", ".ps1", ".py", ".vbs", ".js")):
                        exe.append(os.path.relpath(os.path.join(dp, f), folder))
            info = self.host_info()
            chk = bmcompat.check_mod(info, folder) if info else {"level": bmcompat.WARN, "reasons": ["needs a built host (Build Mashup first): compatibility not checked"]}
            return {"id": str(man.get("id", "")), "name": str(man.get("name", "")), "version": str(man.get("version", "")),
                    "description": str(man.get("description", "")), "files": files, "bytes": size,
                    "native_code": isinstance(man.get("plugin"), dict), "executable_files": exe,
                    "level": chk["level"], "reasons": chk["reasons"]}

    def import_mod(self, src, replace=False):
        with _staged(src) as folder:
            man, why = bmcompat.read_mod(folder)
            if man is None:
                raise ModError(why)
            mid = str(man.get("id", ""))
            if not _ID.match(mid):
                raise ModError("mod.toml id %r is not a valid mod id ([a-z0-9] then [a-z0-9._-], at most 64)" % mid)
            user = bmpaths.mods_dir(self.root, "user")
            os.makedirs(user, exist_ok=True)
            for r in self.mods():
                if r["id"] == mid and r["source"] != "user":
                    raise ModError("%s is already installed in mods\\%s (shipped / generated): it is not replaced" %
                                   (mid, r["source"]))
            dest = os.path.join(user, mid)
            if os.path.exists(dest) and not replace:
                raise ModError("%s is already installed: choose Replace (the old copy is kept in mods\\.backup)" % mid)
            tmp = dest + ".importing"
            if os.path.exists(tmp):
                shutil.rmtree(tmp)
            shutil.copytree(folder, tmp)
            if os.path.exists(dest):
                bk = os.path.join(os.path.dirname(user), ".backup", "%s-%s" % (mid, _stamp()))
                os.makedirs(os.path.dirname(bk), exist_ok=True)
                os.replace(dest, bk)
            os.replace(tmp, dest)
            return dest

    # ---- stale profile ----
    def stale(self):
        rows = {r["id"]: r for r in self.mods() if r["id"]}
        out = []
        if os.path.isfile(self.approvals):
            for mid, digest in re.findall(r'"([a-z0-9][a-z0-9._-]*) sha256:([0-9a-f]{64})"', open(self.approvals, encoding="utf-8",
                                                                                              errors="replace").read()):
                r = rows.get(mid)
                if r is None:
                    out.append({"file": "plugin-approvals.toml", "id": mid, "why": "approval for a mod that is not installed"})
                elif r.get("plugin_file"):
                    p = os.path.join(r["folder"], r["plugin_file"])
                    if os.path.isfile(p) and _sha(p) != digest:
                        out.append({"file": "plugin-approvals.toml", "id": mid,
                                    "why": "the module changed since you approved it: the game will ask again"})
        if os.path.isfile(self.plugin_settings):
            for mid in sorted(set(re.findall(r'"([a-z0-9][a-z0-9._-]*)/[a-z0-9_]+ = ', open(self.plugin_settings, encoding="utf-8",
                                                                                         errors="replace").read()))):
                if mid not in rows and mid != "bmashup.host":
                    out.append({"file": "plugin-settings.toml", "id": mid, "why": "settings of a mod that is not installed"})
        return out

    # ---- results ----
    def results(self, log=None):
        p = log or self.log
        res = {"log": p, "found": os.path.isfile(p), "admitted": None, "refused": [], "plugins_running": [],
               "plugins_not_run": [], "fatal": [], "mods_loaded": 0, "loaded": []}
        if not res["found"]:
            return res
        with open(p, encoding="utf-8", errors="replace") as f:
            for ln in f:
                if ln.startswith("[ADMIT] mod ") and " refused" in ln:
                    res["refused"].append(ln.strip()[8:])
                elif ln.startswith("[ADMIT] ") and "admitted" in ln:
                    m = re.search(r"(\d+) admitted, (\d+) refused", ln)
                    if m:
                        res["admitted"] = int(m.group(1))
                elif ln.startswith("[MOD] mod "):
                    res["mods_loaded"] += 1
                    res["loaded"].append(ln[10:].split(":", 1)[0].strip())
                elif ln.startswith("[PLUGIN] ") and ": running (plugin API" in ln:
                    res["plugins_running"].append(ln[9:].split(":", 1)[0])
                elif ln.startswith("[PLUGIN] ") and (": not run:" in ln or ": not started:" in ln):
                    res["plugins_not_run"].append(ln[9:].strip())
                elif "FATAL" in ln and len(res["fatal"]) < 5:
                    res["fatal"].append(ln.strip()[:300])
        return res


def atomic_write(path, text, backup=False):
    """Write to a temporary file in the same folder, flush, then rename over path (the old file kept as .bak)."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if backup and os.path.isfile(path):
            shutil.copy2(path, path + ".bak")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


class _staged:
    """A folder to read a mod from: the folder itself, or a zip checked and extracted into a temporary folder."""

    def __init__(self, src):
        self.src = os.path.abspath(src)
        self.tmp = None

    def __enter__(self):
        if os.path.isdir(self.src):
            return _mod_root(self.src)
        if not (os.path.isfile(self.src) and zipfile.is_zipfile(self.src)):
            raise ModError("%s is neither a folder nor a .zip file" % self.src)
        self.tmp = tempfile.mkdtemp(prefix="bm-import-")
        with zipfile.ZipFile(self.src) as z:
            infos = z.infolist()
            if len(infos) > ZIP_MAX_FILES:
                raise ModError("the zip holds %d entries (limit %d)" % (len(infos), ZIP_MAX_FILES))
            if sum(i.file_size for i in infos) > ZIP_MAX_BYTES:
                raise ModError("the zip unpacks to more than 4 GB")
            for i in infos:
                n = i.filename.replace("\\", "/")
                if n.startswith("/") or re.match(r"^[A-Za-z]:", n) or ".." in n.split("/"):
                    raise ModError("unsafe path inside the zip: %r (refused, nothing imported)" % i.filename)
                if (i.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ModError("the zip contains a link: %r (refused)" % i.filename)
            z.extractall(self.tmp)
        return _mod_root(self.tmp)

    def __exit__(self, *a):
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def _mod_root(folder):
    if os.path.isfile(os.path.join(folder, "mod.toml")):
        return folder
    subs = [os.path.join(folder, d) for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
    hits = [s for s in subs if os.path.isfile(os.path.join(s, "mod.toml"))]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ModError("more than one mod inside (%s): import them one at a time" % ", ".join(os.path.basename(h) for h in hits))
    raise ModError("no mod.toml at the top or one folder down: this is not a Burnout Mashup mod")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    b, cmd, rest = Bundle(argv[0]), argv[1], argv[2:]
    try:
        if cmd == "list":
            for r in b.mods():
                print("%-3s %-8s %-36s %-8s %s%s" % ("on" if r["enabled"] else "off", r["level"], r["id"], r["version"], r["source"],
                                                    "  native code" if r["native_code"] else ""))
                for x in r["reasons"]:
                    print("      - " + x)
        elif cmd in ("on", "off"):
            print("disabled now:", b.set_enabled(rest[0], cmd == "on"))
        elif cmd == "import":
            print(json.dumps(b.preview(rest[0]), indent=1))
            print("imported to", b.import_mod(rest[0], replace="--replace" in rest))
        elif cmd == "stale":
            print(json.dumps(b.stale(), indent=1))
        elif cmd == "results":
            print(json.dumps(b.results(rest[0] if rest else None), indent=1))
        else:
            print(__doc__)
            return 2
    except ModError as e:
        print("refused: %s" % e)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
