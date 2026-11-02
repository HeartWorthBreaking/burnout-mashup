"""trackconv.package - a converted / authored track as a Burnout Mashup mod: mod.toml, bmpack.json (the bmpack 1 format:
files with sha256 / size, track sources, Gamedata rename), files\\Tracks\\<RR>\\<NN_VN>\\ with the donor's file names, and a
SHA256SUMS.txt beside the set (sha256sum format, paths relative to the output root). Derived from whitemountain\\wm4\\
wm4_package.py / wm6b_package.py and motorcity\\mc4\\mc4_package.py; every decision is a profile parameter.

Platform rules checked here (CONVERSION_PLAYBOOK s6): track ID RR_NN_VN (A-Z 0-9, base-40), a declared region letter not
U / E / A, region text <= 17, track name <= 27, location <= 17, mod id <= 64, description <= 1024; lanes > 64 need
[bmashup.capacity] lanes (<= 255). Validation with the real host readers is bmpack 1.2 verify / validate (optional)."""
import json
import os
import re
import shutil

from .common import TCError, need, sha
from .. import bmpack_min as _bmpack   # vendored: bmpack 1.2 rename / verify (pure Python)

FILES = ("static.dat", "streamed.dat", "Gamedata.bgd", "enviro.dat", "SOUND.AWD", "CRASH1.RWS", "CRASH2.RWS", "CRASH3.RWS",
         "E_DJRACE.xwb", "MUSIC.RWS")
CAPACITY_KEYS = ("lanes", "low_unit_bytes", "full_unit_bytes", "static_bytes", "gamedata_bytes")   # mod.toml order (trackbuild 0.3.4)
GAMEDATA_RULE = ("per-event records 0x3000 .. 0x3800 + 0x800 * 64 (8-byte aligned): the donor track ID and race IDs "
                 "ending in the donor compact ID renamed; every other byte the donor's")


def q(s):
    need("\n" not in s and "\r" not in s, "a mod.toml string with a line break")
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def check_decisions(p):
    tid = p["track_id"]
    need(re.fullmatch(r"[A-Z0-9]{2}_[A-Z0-9]{2}_[A-Z0-9]{2}", tid) is not None, "track ID %s is not RR_NN_VN (A-Z 0-9)" % tid)
    reg = p.get("region")
    if reg:
        need(re.fullmatch(r"[A-Z]", reg["letter"]) and reg["letter"] not in "UEA", "region letter %s: A-Z other than U / E / A" % reg["letter"])
        need(tid[0] == reg["letter"], "track ID %s is not in region %s" % (tid, reg["letter"]))
        need(1 <= len(reg["text"]) <= 17, "region text longer than 17 characters")
        need(reg["dj"] in ("DJUS", "DJEU", "DJAS"), "DJ bank must be DJUS / DJEU / DJAS (a retail placeholder)")
    else:
        need(tid[0] in "UEA", "track ID %s needs a declared region (letter %s)" % (tid, tid[0]))
    need(1 <= len(p["track_name"]) <= 27, "track name 1..27 characters")
    need(1 <= len(p["track_location"]) <= 17, "track location 1..17 characters")
    need(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", p["mod_id"]) is not None, "mod id: [a-z0-9] then [a-z0-9._-], <= 64")
    need(len(p.get("description", "")) <= 1024, "description longer than 1024 characters")
    lanes = p.get("lanes")
    need(lanes is None or 64 < lanes <= 255, "lanes: omit for <= 64 route lanes, else 65..255")
    for k, v in (p.get("capacity_decl") or {}).items():          # trackbuild 0.3.4: the merged [bmashup.capacity] keys
        need(k in CAPACITY_KEYS and isinstance(v, int) and 0 < v, "[bmashup.capacity] %s = %r: not a key / value the host reads" % (k, v))
        need(k == "lanes" or v % 0x1000 == 0, "[bmashup.capacity] %s = 0x%X is not a page multiple (0x1000)" % (k, v))


def mod_toml(p):
    c = p.get("comments", {})
    reg = p.get("region")
    t = p["track_id"]
    s = c.get("header", "# %s, a Burnout 3 track mod made with trackconv. Game-derived content: LOCAL ONLY.\n" % p["track_name"])
    s += "id = %s\nname = %s\nversion = %s\nauthor = %s\ndescription = %s\n\n" % (
        q(p["mod_id"]), q(p["mod_name"]), q(p["version"]), q(p["author"]), q(p.get("description", "")))
    s += "[bmashup]\nplatform = %s\n" % q(p.get("platform", ">=0.1"))
    if reg:
        s += "\n" + c.get("regions", "")
        s += "[bmashup.regions]\nversion = 1\nadd = [%s]\ndj = [%s]\n" % (q("%s = %s" % (reg["letter"], reg["text"])),
                                                                         q("%s = %s" % (reg["letter"], reg["dj"])))
    s += "\n" + c.get("tracks", "")
    s += "[bmashup.tracks]\nversion = 1\nadd = [%s]\nnames = [%s]\nlocations = [%s]\n" % (
        q(t), q("%s = %s" % (t, p["track_name"])), q("%s = %s" % (t, p["track_location"])))
    if p.get("point_to_point"):
        s += "point_to_point = [%s]\n" % q(t)
    cap = p.get("capacity_decl") or ({"lanes": p["lanes"]} if p.get("lanes") else None)
    if cap:
        s += "\n" + c.get("capacity", "")
        s += "[bmashup.capacity]\nversion = 1\n"
        for k in CAPACITY_KEYS:
            if k in cap:
                s += ("%s = %d\n" if k == "lanes" else "%s = 0x%X\n") % (k, cap[k])
    need(all(ord(ch) < 128 for ch in s), "mod.toml must be ASCII")
    return s


def package(out_root, p, products, donor_id, cache_dir, validate=False):
    """out_root: OutRoot of the output; p: the [package] decisions; products: {file name: bytes} (the 10 files; Gamedata
    NOT yet renamed); donor_id 'EU_M1_V1'. -> {set dir, mod dir, files, renamed, sums}"""
    check_decisions(p)
    need(sorted(products) == sorted(FILES), "products must be exactly the 10 track files: %s" % sorted(products))
    BP = _bmpack   # cache_dir unused (no compiled checker in the vendored subset)
    set_rel, folder = p["set"], p["folder"]
    mod_rel = "%s/%s" % (set_rel, folder)
    mod_dir = out_root.path(*mod_rel.split("/"))
    need(not os.path.exists(mod_dir), "%s exists: never overwritten" % mod_dir)
    tid = p["track_id"]
    rel_t = "files/Tracks/%s/%s" % (tid[:2], tid[3:])
    out_root.write("%s/mod.toml" % mod_rel, mod_toml(p).encode("ascii"))
    prov = p.get("provenance", {})
    from_map = prov.get("sources_from", {})
    renamed, sources = [], {}
    for name in FILES:
        data = products[name]
        sources[name] = {"from": from_map.get(name, "trackconv/%s" % name), "sha256": sha(data), "size": len(data)}
        if name == "Gamedata.bgd":
            gd = bytearray(data)
            renamed = BP.rename_gamedata(gd, donor_id, tid)
            data = bytes(gd)
        out_root.write("%s/%s/%s" % (mod_rel, rel_t, name), data)
    files = {}
    for root, _, fs in os.walk(mod_dir):
        for fn in fs:
            fp = os.path.join(root, fn)
            files[os.path.relpath(fp, mod_dir).replace(os.sep, "/")] = {"sha256": sha(open(fp, "rb").read()), "size": os.path.getsize(fp)}
    j = {"bmpack": BP.VERSION,
         "packaged_by": prov.get("packaged_by", "gp\\tools\\trackconv (bmpack %s rename_gamedata)" % BP.TOOL_VERSION),
         "mod": {"id": p["mod_id"], "version": p["version"], "name": p["mod_name"], "author": p["author"]}, "folder": folder,
         "tracks": [{"id": tid, "donor": donor_id, "donor_note": prov.get("donor_note", "Gamedata host / audio donor (the converted "
                     "files are not the donor's)"), "folder": rel_t, "sources": sources, "renamed": renamed}],
         "regions": [{"letter": p["region"]["letter"], "text": p["region"]["text"], "dj": p["region"]["dj"]}] if p.get("region") else [],
         "events": [], "files": dict(sorted(files.items())), "gamedata_rule": GAMEDATA_RULE}
    out_root.write("%s/bmpack.json" % mod_rel, (json.dumps(j, indent=1, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8"))
    bad = BP.verify(mod_dir)
    need(not bad, "packaged mod does not verify: %s" % bad)
    rep = None
    if validate:   # host-reader validation is an explicit, optional step in trackbuild 0.2.0 (tb.py package --bmpack)
        rep = BP.validate([out_root.path(*set_rel.split("/"))])
        need(rep["ok"], "the host's readers refuse the mod:\n" + BP.format_refusals(rep))
    rels = []
    for root, _, fs in os.walk(out_root.path(*set_rel.split("/"))):
        for fn in fs:
            rels.append(os.path.relpath(os.path.join(root, fn), out_root.root).replace(os.sep, "/"))
    return {"set": out_root.path(*set_rel.split("/")), "mod": mod_dir, "files": len(files), "renamed": len(renamed), "rels": rels,
            "validate": None if rep is None else {"ok": rep["ok"], "rc": rep["rc"]}}


def file_override_mod(out_root, set_rel, folder, mod, files, note=""):
    """a plain file-replacement mod (no [bmashup] table): files {"Tracks/US/C5_V1/static.dat": bytes}. For authored
    edits of RETAIL tracks (the host serves the mod's file instead of the game's)."""
    need(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", mod["id"]) is not None, "mod id")
    mod_rel = "%s/%s" % (set_rel, folder)
    need(not os.path.exists(out_root.path(*mod_rel.split("/"))), "%s exists: never overwritten" % mod_rel)
    s = "# %s\nid = %s\nname = %s\nversion = %s\nauthor = %s\ndescription = %s\n" % (
        note or "A trackconv authoring fixture. Game-derived content: LOCAL ONLY.", q(mod["id"]), q(mod["name"]),
        q(mod["version"]), q(mod["author"]), q(mod.get("description", "")))
    out_root.write("%s/mod.toml" % mod_rel, s.encode("ascii"))
    for rel, data in sorted(files.items()):
        need(re.fullmatch(r"Tracks/[A-Z]{2}/[A-Z0-9]{2}_V[0-9]/[A-Za-z0-9_.]+", rel) is not None, "file path %s" % rel)
        out_root.write("%s/files/%s" % (mod_rel, rel), data)
    return out_root.path(*mod_rel.split("/"))


def write_sums(out_root, rels, name="SHA256SUMS.txt"):
    from .common import sums_text
    return out_root.write(name, sums_text(out_root.root, rels).encode())


__all__ = ["package", "mod_toml", "check_decisions", "file_override_mod", "write_sums", "FILES", "TCError", "shutil"]
