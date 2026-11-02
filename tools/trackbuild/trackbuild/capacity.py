"""trackbuild.capacity - 0.3.4: the ONE table of the game's capacities and the Burnout Mashup host's ceilings, and the
mod.toml [bmashup.capacity] declaration a built track needs.

Modes (track description "capacity" and package [package] capacity; default "auto"):
  auto  a track may exceed the game's default sizes up to the host's ceiling; the package declares exactly the capacity the
        track needs (page-rounded) in mod.toml [bmashup.capacity] (version = 1). Nothing is written when the track fits the
        game's defaults (the package bytes are then those of 0.3.3).
  game  the 0.3.3 behaviour: refused above the game's defaults (for tracks meant for hosts without capacity declarations).

Host facts (main21 host source, src\\game): bm_unitslots.h BO3_US_FULL_RETAIL / BO3_US_LOW_RETAIL / BO3_US_LOW_MAX,
bm_static.h BO3_ST_L1_GAME / BO3_ST_MAX (0x20C4000: the 64 MiB window), bm_gdslot.h BO3_GDS_GAME / BO3_GDS_MAX,
bm_lanes.h BO3_LANE_LEGACY_MAX / BO3_LANE_TOTAL_MAX, bm_capdecl.c (keys; an unknown key stops the start: exit 91).
Ceilings = the host of Burnout Mashup 0.2.0-alpha.2 (main21 patch 131, 2026-11-02): full / low unit 0x200000
(2 MiB), STATIC 0x4000000 (the 256 MiB-window build), Gamedata 0x800000, lanes 255. Each key records the minimum host per value range (TIERS).
Split screen keeps the game's STATIC size (0xA00000; bm_static.h BO3_ST_L2_GAME): a declared static_bytes applies to
single-screen races only.
Material rows per centre block (ROWS, info only): game 83 (retail arrays); the host reads up to 255 with the BMRX row extension
(host bm_rowx.c; 255 needs patch 131, 127 before; extension rows E <= 172). trackbuild 0.3.4 writes NO extension, so it keeps the
83 rule in every mode; the editor shows the host figure (tools\\wm_rowx.py in the Workbench reads / writes the extension)."""
from .io import SourceError

PAGE = 0x1000
HOST_CAPDECL = "a Burnout Mashup host that reads mod.toml [bmashup.capacity] version 1 (main21+)"
HOST_P131 = "a Burnout Mashup host with patch 131+"

# key (= the mod.toml key): game default, host ceiling, unit ("bytes" page multiples | "count"), what it limits,
# tiers [(highest value, minimum host)] in ascending order (the last tier's value is the ceiling)
TABLE = {
    "full_unit_bytes": {"game": 0x28000, "ceiling": 0x200000, "unit": "bytes", "what": "full-detail unit (mesh) block",
                        "tiers": [(0x200000, HOST_P131)]},
    "low_unit_bytes": {"game": 0x18000, "ceiling": 0x200000, "unit": "bytes", "what": "low-detail unit (LOD + collision) block",
                       "tiers": [(0x30000, HOST_CAPDECL), (0x200000, HOST_P131)]},
    "static_bytes": {"game": 0xD00000, "ceiling": 0x4000000, "unit": "bytes", "what": "STATIC pool (static.dat)",
                     "tiers": [(0x20C4000, HOST_CAPDECL), (0x4000000, HOST_P131 + " (256 MiB window build)")]},
    "gamedata_bytes": {"game": 0x176000, "ceiling": 0x800000, "unit": "bytes", "what": "GAMEDATA slot (Gamedata.bgd route data)",
                       "tiers": [(0x800000, HOST_CAPDECL)]},
    "lanes": {"game": 64, "ceiling": 255, "unit": "count", "what": "AI route lanes", "tiers": [(255, HOST_CAPDECL)]},
}
ORDER = ("lanes", "low_unit_bytes", "full_unit_bytes", "static_bytes", "gamedata_bytes")   # mod.toml key order
ROWS = {"game": 83, "ceiling": 255, "ceiling_before_p131": 127, "extension_rows_max": 172, "what": "material rows per centre block",
        "host": HOST_P131 + " and the BMRX row extension in the mesh block", "written_by_trackbuild": False}
# records per mesh block: 127 enforced (retail s8 chain links / row heads). Host patch 132 (includes 131) reads 255 when the
# block opts in (pad +0xC70 b"BMRC", +0xC74 u8 version 1: next links and row heads read unsigned, 0xFF = none). trackbuild
# 0.3.4 does NOT write the BMRC flag (its writer and the vendored validators are s8): info only, 127 stays enforced.
RECORDS = {"game": 127, "enforced": 127, "host_planned": 255, "host_planned_by": "a Burnout Mashup host with patch 132 (block flag BMRC)",
           "what": "records per block", "written_by_trackbuild": False}


def records_note(n):
    """refusal text for a block with n records"""
    return ("%d records in one block: the game reads at most %d (s8 chain links). A Burnout Mashup host with patch 132 reads up "
            "to %d when the block carries the BMRC flag, but trackbuild 0.3.4 does not write it yet: split the unit (more, "
            "shorter units) or merge materials / simplify geometry" % (n, RECORDS["enforced"], RECORDS["host_planned"]))
# units (sections) per track: pvs "all" exactly 17 (4..17 build); pvs "computed" 4..162 (162 = the largest retail track, proven);
# above 162: refused (untested in the game). Visibility rule unchanged: no unit sees beyond +-8 units.
UNITS = {"all": (4, 17), "computed": (4, 162), "largest_retail": 162,
         "above_why": "above the largest retail track (162 units); untested in the game"}
MODES = ("auto", "game")
DEFAULT_MODE = "auto"


class CapacityError(SourceError):
    """a track needs more than the mode allows (above the host ceiling, or above the game default in mode game)"""


def fmt(key, v):
    return "%d" % v if TABLE[key]["unit"] == "count" else "0x%X" % v


def page(v):
    return (int(v) + PAGE - 1) & ~(PAGE - 1)


def mode_of(obj):
    """the capacity mode of a track description / package decisions (dict) or a plain value; refused if unknown"""
    m = obj.get("capacity", DEFAULT_MODE) if isinstance(obj, dict) else (obj or DEFAULT_MODE)
    if m not in MODES:
        raise SourceError("capacity %r: use \"auto\" (declare what the track needs in mod.toml, up to the Burnout Mashup host's "
                          "ceilings) or \"game\" (refuse anything above the game's default sizes)" % (m,))
    return m


def limit(key, mode):
    """the largest value a build accepts for `key` in `mode` (auto = the host ceiling, game = the game's default)"""
    return TABLE[key]["ceiling"] if mode == "auto" else TABLE[key]["game"]


def requirement(key, v):
    """the minimum host for value v of key (None = the game's default is enough)"""
    t = TABLE[key]
    if v <= t["game"]:
        return None
    for top, host in t["tiers"]:
        if v <= top:
            return host
    return None


def explain(key, v, subject=None, mode=DEFAULT_MODE):
    """one sentence about value v of key against the game's default and the host's ceiling"""
    t = TABLE[key]
    s = "%s %s" % (subject or t["what"], fmt(key, v))
    if v <= t["game"]:
        return "%s - within the game's %s" % (s, fmt(key, t["game"]))
    d = v if t["unit"] == "count" else page(v)
    if v > t["ceiling"]:
        return "%s - above the Burnout Mashup host's ceiling %s (%s); nothing can declare it" % (s, fmt(key, t["ceiling"]), key)
    if mode == "game":
        return ("%s - above the game's %s (capacity \"game\" refuses it; capacity \"auto\" would declare %s = %s, needs %s)"
                % (s, fmt(key, t["game"]), key, fmt(key, d), requirement(key, d)))
    return "%s - above the game's %s, declared %s %s (needs %s)" % (s, fmt(key, t["game"]), key, fmt(key, d), requirement(key, d))


def check_value(key, v, mode, subject=None):
    """refuse v when above the mode's limit (CapacityError with the explanation and what to do)"""
    if v <= limit(key, mode):
        return
    t = TABLE[key]
    if v > t["ceiling"]:
        raise CapacityError("%s. Make it smaller (shorter units / fewer details / smaller textures)." % explain(key, v, subject, mode))
    raise CapacityError("%s. Set \"capacity\": \"auto\" to declare it for a Burnout Mashup host, or make it smaller."
                        % explain(key, v, subject, mode))


def needed_capacity(build):
    """BUILD_REPORT (dict) -> {key: needed value} (bytes page-rounded, lanes counted): the largest mesh / LOD block of all units,
    static.dat size, the Gamedata route-data need, the route lane count"""
    units = build.get("units") or {}
    ul = units.get("units") if isinstance(units, dict) else units
    ul = ul or []
    n = {}
    if ul:
        n["full_unit_bytes"] = page(max(u["mesh_bytes"] for u in ul))
        n["low_unit_bytes"] = page(max(u["lod_bytes"] for u in ul))
    if build.get("static", {}).get("bytes") is not None:
        n["static_bytes"] = page(build["static"]["bytes"])
    gd = (build.get("gamedata") or {}).get("need")
    if gd is not None:
        n["gamedata_bytes"] = page(int(gd, 16) if isinstance(gd, str) else gd)
    lanes = (build.get("route") or {}).get("lanes")
    if lanes is not None:
        n["lanes"] = int(lanes)
    return n


def declaration(needed, mode=DEFAULT_MODE):
    """{key: value} to declare: only keys whose need is above the game's default; refused above the mode's limit"""
    out = {}
    for k in ORDER:
        if k not in needed:
            continue
        check_value(k, needed[k], mode)
        if needed[k] > TABLE[k]["game"]:
            out[k] = needed[k]
    return out


def merge(*decls):
    """several declarations (e.g. the package's own keys and the build's) -> the largest value per key"""
    out = {}
    for d in decls:
        for k, v in (d or {}).items():
            if k not in TABLE:
                raise SourceError("[bmashup.capacity] key %r is not one the host reads (%s)" % (k, ", ".join(ORDER)))
            out[k] = max(out.get(k, 0), int(v))
    return {k: out[k] for k in ORDER if k in out}


def requires(decl):
    """declared keys -> [one line per key with its minimum host], plus the overall minimum host (or None)"""
    lines, hosts = [], []
    for k in ORDER:
        if k in decl:
            h = requirement(k, decl[k])
            lines.append("%s = %s: requires %s" % (k, fmt(k, decl[k]), h))
            hosts.append(h)
    overall = HOST_P131 if any(h and h.startswith(HOST_P131) for h in hosts) else (HOST_CAPDECL if hosts else None)
    return lines, overall


def summary(needed, mode=DEFAULT_MODE):
    """the build report / LABELS section: {mode, needed, declared, requires, min_host} (hex strings for bytes)"""
    decl = declaration(needed, mode) if mode == "auto" else {}
    if mode == "game":
        for k, v in needed.items():
            check_value(k, v, "game")
    lines, overall = requires(decl)
    return {"mode": mode, "needed": {k: fmt(k, needed[k]) for k in ORDER if k in needed},
            "declared": {k: fmt(k, decl[k]) for k in decl}, "requires": lines, "min_host": overall}


def parse_declared(d):
    """the summary's declared {key: "0x..." | "80"} -> ints"""
    return {k: (int(v, 0) if isinstance(v, str) else int(v)) for k, v in (d or {}).items()}


def toml_section(decl):
    """[bmashup.capacity] text (version = 1, ORDER, lanes decimal, bytes hex) for a non-empty declaration"""
    s = "[bmashup.capacity]\nversion = 1\n"
    for k in ORDER:
        if k in decl:
            s += "%s = %s\n" % (k, fmt(k, decl[k]))
    return s


def rows_note(n):
    """one sentence about n material rows against the game's 83 and the host's BMRX ceiling (info; trackbuild refuses > 83)"""
    if n <= ROWS["game"]:
        return "rows %d / %d (the game's retail arrays)" % (n, ROWS["game"])
    if n <= ROWS["ceiling"]:
        return ("rows %d / %d: above the game's %d - would use the host's BMRX row extension (needs %s; up to 127 rows before patch "
                "131); trackbuild writes no row extension, so merge materials to %d rows" % (n, ROWS["ceiling"], ROWS["game"],
                                                                                            HOST_P131, ROWS["game"]))
    return "rows %d: above the host's BMRX ceiling %d and the game's %d - merge materials" % (n, ROWS["ceiling"], ROWS["game"])


def units_check(n, pvs_mode):
    """unit count against the kit's range for the visibility mode -> None or the refusal text"""
    lo, hi = UNITS["computed" if pvs_mode == "computed" else "all"]
    if pvs_mode == "computed":
        if n < lo:
            return "pvs mode computed: %d units, at least %d" % (n, lo)
        if n > hi:
            return "pvs mode computed: %d units - %s (4..%d)" % (n, UNITS["above_why"], hi)
        return None
    return None if lo <= n <= hi else "pvs mode all: %d units, 4..17 (the validator needs exactly 17)" % n


def table_json():
    """the table for the Workbench / track editor (no Python needed in the page)"""
    return {"page": PAGE, "order": list(ORDER), "modes": list(MODES), "default_mode": DEFAULT_MODE,
            "keys": {k: {"game": v["game"], "ceiling": v["ceiling"], "unit": v["unit"], "what": v["what"],
                         "tiers": [[a, b] for a, b in v["tiers"]]} for k, v in TABLE.items()},
            "rows": dict(ROWS), "records": dict(RECORDS), "units": {k: list(v) if isinstance(v, tuple) else v for k, v in UNITS.items()}}


def unit_usage(unit_infos, mode=DEFAULT_MODE):
    """per unit mesh / LOD usage against the game default and the host ceiling ->
    [{unit, mesh, lod, mesh_state, lod_state, note}] with states "ok" | "declared" (above the game, fits the host) | "over" """
    out = []
    for u in unit_infos:
        row = {"unit": u["unit"], "mesh": u["mesh_bytes"], "lod": u["lod_bytes"], "notes": []}
        for key, field, tag in (("full_unit_bytes", "mesh_bytes", "mesh"), ("low_unit_bytes", "lod_bytes", "lod")):
            v = u[field]
            t = TABLE[key]
            st = "ok" if v <= t["game"] else ("over" if v > limit(key, mode) else "declared")
            row[tag + "_state"] = st
            if st != "ok":
                row["notes"].append(explain(key, v, "unit %d %s" % (u["unit"], "mesh" if tag == "mesh" else "LOD"), mode))
        out.append(row)
    return out
