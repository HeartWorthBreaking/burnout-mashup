"""bmcompat.py - Burnout Mashup compatibility gate: does a mod fit THIS host? (release readiness R1; standard library only)

The host describes itself in host\\HOST_INFO.json (written at packaging by kit_tools\\make_host_info.py from the host's own
platform table: platform version, services + versions, mod.toml tables + the newest version each reader takes, plugin api).
check_mod() compares one mod.toml with it, using the host's own rules (bm_modreq.h: only ">=", versions compare by their
leading numbers, "-prerelease" ranks below the same numbers). It is an EARLY warning for players and developers before
install / build / play; the host's admission at start remains the final word and is shown in the results after a game.

    py -3 -B bmcompat.py HOST_INFO.json MOD_FOLDER...      one line per mod: OK / WARN / BLOCKED + reasons; exit 0 / 1
"""
import json
import os
import re
import sys

try:
    import tomllib
except ImportError:          # Python < 3.11: the launcher refuses earlier with an install hint
    tomllib = None

OK, WARN, BLOCKED = "OK", "WARN", "BLOCKED"
OWN_KEYS = ("platform", "requires", "requires_mods")         # BO3_PLATFORM_OWN_KEYS
_SVC = re.compile(r"^([a-z0-9._-]{1,64}?) *(?:>= *([0-9]+) *)?$")  # bm_platform_gate.inc px_require
_REQ = re.compile(r"^\s*([a-z0-9][a-z0-9._-]{0,63})\s*(?:>=\s*([0-9A-Za-z][0-9A-Za-z.+-]*))?\s*$")


def version_key(text):
    """bm_modreq.h's order: leading numeric dotted parts (4, missing = 0), '+build' ignored, '-pre' below release.
    None when the text does not start with a number (cannot be compared)."""
    if not text:
        return None
    t = text.split("+", 1)[0]
    pre = "-" in t
    t = t.split("-", 1)[0]
    m = re.match(r"^([0-9]+(?:\.[0-9]+){0,3})", t)
    if not m:
        return None
    parts = [int(x) for x in m.group(1).split(".")] + [0, 0, 0]
    return tuple(parts[:4]), 0 if pre else 1


def meets(have, want):
    """have >= want in the host's sense (a prerelease meets >= V only when its numbers are strictly greater)."""
    h, w = version_key(have), version_key(want)
    if h is None or w is None:
        return False
    return h[0] > w[0] or (h[0] == w[0] and h[1] >= w[1])


def load_host_info(path):
    with open(path, encoding="utf-8") as f:
        info = json.load(f)
    for k in ("platform", "services", "tables"):
        if k not in info:
            raise ValueError("HOST_INFO.json has no '%s'" % k)
    return info


def read_mod(folder):
    """(manifest dict, None) or (None, reason)."""
    p = os.path.join(folder, "mod.toml")
    if not os.path.isfile(p):
        return None, "no mod.toml in %s" % folder
    if tomllib is None:
        return None, "Python 3.11 or newer is needed to read mod.toml"
    try:
        with open(p, "rb") as f:
            return tomllib.load(f), None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, "mod.toml is not valid TOML: %s" % e


def check_mod(info, folder, installed=None):
    """-> dict(id, name, version, level, reasons[], native_code, plugin_file). installed: {mod id: version} of the other
    mods (for requires_mods)."""
    res = {"folder": folder, "id": "", "name": os.path.basename(folder), "version": "", "level": OK, "reasons": [],
           "native_code": False, "plugin_file": ""}

    def bad(level, text):
        res["reasons"].append(text)
        if level == BLOCKED or (level == WARN and res["level"] == OK):
            res["level"] = level

    man, why = read_mod(folder)
    if man is None:
        bad(BLOCKED, why)
        return res
    res["id"] = str(man.get("id", ""))
    res["name"] = str(man.get("name", res["id"] or res["name"]))
    res["version"] = str(man.get("version", ""))
    if not res["id"]:
        bad(BLOCKED, "mod.toml has no id")
    bm = man.get("bmashup", {}) if isinstance(man.get("bmashup", {}), dict) else {}
    plat = bm.get("platform")
    if isinstance(plat, str) and plat.strip():
        m = re.match(r"^\s*>=\s*(\S+)\s*$", plat)
        if not m:
            bad(BLOCKED, "[bmashup] platform = %r: only \">= X.Y.Z\" is understood" % plat)
        elif not meets(info["platform"], m.group(1)):
            bad(BLOCKED, "needs platform %s or newer; this host is %s - install a newer Burnout Mashup host" %
                (m.group(1), info["platform"]))
    for k, v in bm.items():            # bm_platform_gate.inc step 1: [bmashup] takes only platform / requires / requires_mods
        if not isinstance(v, dict) and k not in OWN_KEYS:
            bad(BLOCKED, "[bmashup] key %r is not known to this host (it takes %s)" % (k, ", ".join(OWN_KEYS)))
    for entry in bm.get("requires", []) if isinstance(bm.get("requires", []), list) else ["?"]:
        m = _SVC.match(str(entry))     # step 5: "name" or "name>=N", a service or a table, N a whole number
        if not m:
            bad(BLOCKED, "requires entry %r is not \"name\" or \"name>=N\" (another mod goes in requires_mods)" % entry)
            continue
        name, want = m.group(1), int(m.group(2) or 1)
        if want < 1:
            bad(BLOCKED, "requires entry %r: the version must be a whole number from 1" % entry)
            continue
        have = info["services"].get(name)
        if have is None and name.startswith("bmashup.") and name[8:] in info["tables"]:
            have = info["tables"][name[8:]]["version"]
        if have is None:
            bad(BLOCKED, "needs %s, which this host (platform %s) does not offer - a newer host may" % (name, info["platform"]))
        elif have < want:
            bad(BLOCKED, "needs %s version %d; this host offers %d - install a newer host or an older version of the mod" %
                (name, want, have))
    for entry in bm.get("requires_mods", []) if isinstance(bm.get("requires_mods", []), list) else ["?"]:
        m = _REQ.match(str(entry))
        if not m:
            bad(BLOCKED, "requires_mods entry %r cannot be read" % entry)
            continue
        mid, want = m.group(1), m.group(2)
        if installed is not None:
            if mid not in installed:
                bad(BLOCKED, "needs the mod %s - install it (or turn it on)" % mid)
            elif want and not meets(installed[mid], want):
                bad(BLOCKED, "needs the mod %s %s or newer (installed: %s)" % (mid, want, installed[mid] or "no version"))
    for tname, tval in bm.items():
        if not isinstance(tval, dict):
            continue
        known = info["tables"].get(tname)
        if known is None:              # steps 1-3: an unknown table, a newer table version or an unknown key refuses the mod
            bad(BLOCKED, "[bmashup.%s] is not read by this host: it needs a newer platform" % tname)
            continue
        v = tval.get("version")
        if isinstance(v, int) and v > known["version"]:
            bad(BLOCKED, "[bmashup.%s] version %d needs a newer platform (this host reads %d)" % (tname, v, known["version"]))
            continue
        extra = sorted(k for k in tval if k not in known["keys"])
        if extra:
            bad(BLOCKED, "[bmashup.%s] keys this host does not take (a typo?): %s" % (tname, ", ".join(extra)))
    pl = man.get("plugin")
    if isinstance(pl, dict):
        res["native_code"] = True
        res["plugin_file"] = str(pl.get("windows", ""))
        api = pl.get("api")
        if api != info.get("plugin_api", 1):
            bad(BLOCKED, "[plugin] api = %r; this host loads api %s" % (api, info.get("plugin_api", 1)))
        if not res["plugin_file"]:
            bad(BLOCKED, "[plugin] has no windows module")
        elif not os.path.isfile(os.path.join(folder, res["plugin_file"])):
            bad(BLOCKED, "the Windows module %s is missing from the mod folder" % res["plugin_file"])
        else:
            bad(WARN, "contains native code (%s): it runs with full rights; the game asks you to approve it on its MODS "
                "page, and the launcher never approves it for you" % res["plugin_file"])
    return res


def _declared(man):
    """what a manifest claims for itself alone: track ids {id}, regions {letter: text and bank}"""
    bm = man.get("bmashup", {}) if isinstance(man, dict) and isinstance(man.get("bmashup", {}), dict) else {}
    tr = bm.get("tracks", {}) if isinstance(bm.get("tracks", {}), dict) else {}
    rg = bm.get("regions", {}) if isinstance(bm.get("regions", {}), dict) else {}
    tracks = [str(x).strip() for x in tr.get("add", [])] if isinstance(tr.get("add", []), list) else []

    def pairs(key):
        out = {}
        for x in rg.get(key, []) if isinstance(rg.get(key, []), list) else []:
            k, _, v = str(x).partition("=")
            if v:
                out[k.strip()] = v.strip()
        return out
    names, banks = pairs("add"), pairs("dj")
    return tracks, {k: (names[k], banks.get(k, "")) for k in names}


def find_clashes(rows):
    """Mods that clash with each other, as the host's admission does it at start (bm_admit.c): in load order (rows as given), the first mod to claim a track id or
    a region keeps it, a later one is refused and "the game starts without it". rows: dict(id, name, enabled, level, manifest). An early warning: the host stays the final word.
    Only mods that would load count. -> {row index: [(True when this mod is the refused one, text)]}"""
    tracks, regions, out = {}, {}, {}
    for i, r in enumerate(rows):
        if not r.get("enabled") or r.get("level") == BLOCKED or not r.get("manifest"):
            continue
        who = r.get("name") or r.get("id")
        tr, rg = _declared(r["manifest"])
        texts = []
        for t in tr:
            if t in tracks:
                texts.append((tracks[t], "both add the track %s" % t))
        for k, v in rg.items():
            if k in regions and regions[k][1] != v:
                texts.append((regions[k][0], "they declare the region %s differently (%s / %s)" % (k, regions[k][1][0], v[0])))
        if texts:
            for owner, what in texts:
                out.setdefault(i, []).append((True, "clashes with %s: %s. The game starts without this mod: turn one of them off" % (rows[owner].get("name") or rows[owner].get("id"), what)))
                out.setdefault(owner, []).append((False, "clashes with %s: %s. The game keeps this one and refuses the other: turn one of them off" % (who, what)))
            continue                     # refused: it claims nothing
        for t in tr:
            tracks[t] = i
        for k, v in rg.items():
            regions.setdefault(k, (i, v))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    info = load_host_info(argv[0])
    rc = 0
    for folder in argv[1:]:
        r = check_mod(info, folder)
        print("%-8s %s %s" % (r["level"], r["id"] or folder, r["version"]))
        for x in r["reasons"]:
            print("         - " + x)
        rc |= r["level"] == BLOCKED
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
