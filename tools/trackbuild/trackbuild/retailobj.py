"""trackbuild.retailobj (0.3.2-rta) - verbatim retail instance models and prop types placed in an authored track.

Description key (optional):
  "retail_objects": [{"family": "instance" | "prop", "track": "US/C1_V1", "index": 31,
                      "static_sha256": "<sha256 of that track's static.dat>",
                      "placements": [{"pos": [x, y, z], "yaw_deg": 90.0}, ...]}]

family "instance" = STATIC +0x34 / +0x38 instance models (retail lamps, trees, signs, traffic lights; drawn by the game's instance
renderer; NO collision - decoration). Placements go into the LOD block tail of the unit holding them ([+0xA8] u8 counts per type,
[+0xAC] u32 pointers rel +0xA8 -> 0x40-byte matrices; layout rule verified on 2,838 / 2,838 retail blocks).
family "prop" = STATIC +0x36 / +0x3C prop types (the game builds a collision BODY per placement from the type record (sub_00110420
/ sub_00114270): hit props break and are drawn per section; a smashable object as retail has it). Placements: +0x48 matrices,
+0x4C per-unit u8 counts (never null), +0x50 per-unit per-type lists of words (class << 16) | matrix index, +0x44 class byte per
type (all as retail; KB XBOX_TRACK_FORMATS / external review A6).

Copied byte for byte from the user's static.dat: the 0x70 record (except the three material indices +0x5C / +0x5E / +0x60, s16 or
-1, remapped to the copies), every LOD's vertices and indices, every referenced material record + texture (trackbuild.retailmat
rules: no UV-scroll / animated materials, DXT1 / 3 / 5 only), the prop class byte.
Matrix per placement: the source's FIRST placement of that type (its 3 x 3 rotation / scale turned about the world Y axis so its
local +Z heads `yaw_deg` (degrees from +Z toward +X), position replaced, elements 3 / 7 / 11 / 15 kept: retail values vary per
placement and look like a light colour - meaning UNKNOWN, so the copied value is APPROXIMATE).
Capacity: never above the retail maxima measured on the user's data (tools\\rta3_placement_survey.py): instance types 81,
instance placements 5,433 per track / 120 per unit, prop types 32, prop placements 741 per track / 66 per unit. The game's pool
sizes are unknown; the maxima are evidence, not a guarantee. Products: LOCAL ONLY."""
import math
import struct

from .io import need
from . import retailmat as RM

KEYS = {"family", "track", "index", "static_sha256", "placements"}
MAX = {"instance_types": 81, "instance_placements": 5433, "instances_per_unit": 120,
       "prop_types": 32, "prop_placements": 741, "props_per_unit": 66}
MAT_AT = (0x5C, 0x5E, 0x60)
EDGE_M = 0.05          # a placement must lie this far inside its unit region (float32 region lines; V12 checks them exactly)


def check_entries(entries):
    need(isinstance(entries, list), "retail_objects must be a list")
    for k, e in enumerate(entries):
        need(isinstance(e, dict) and set(e) == KEYS, "retail_objects[%d]: keys must be exactly %s" % (k, sorted(KEYS)))
        need(e["family"] in ("instance", "prop"), "retail_objects[%d]: family must be instance or prop" % k)
        RM.check_spec("retail_objects[%d]" % k, {"track": e["track"], "material": e["index"], "static_sha256": e["static_sha256"]})
        need(isinstance(e["placements"], list) and e["placements"], "retail_objects[%d]: placements must be a non-empty list" % k)
        for j, p in enumerate(e["placements"]):
            need(isinstance(p, dict) and set(p) <= {"pos", "yaw_deg"} and "pos" in p, "retail_objects[%d] placement %d: {pos, yaw_deg}" % (k, j))
            need(isinstance(p["pos"], list) and len(p["pos"]) == 3 and all(isinstance(v, (int, float)) and math.isfinite(v)
                                                                            for v in p["pos"]),
                 "retail_objects[%d] placement %d: pos must be 3 finite numbers" % (k, j))
            y = p.get("yaw_deg", 0.0)
            need(isinstance(y, (int, float)) and math.isfinite(y), "retail_objects[%d] placement %d: yaw_deg must be a number" % (k, j))


def _first_matrix(o, sm, family, index):
    """the source track's first placement matrix of that type (unit order) -> 64 bytes, or None"""
    if family == "prop":
        for lists in o["ulists"]:
            L = (lists or [None] * (index + 1))[index] if lists and index < len(lists) else None
            if L:
                return o["matrices"][struct.unpack_from("<I", L, 0)[0] & 0xFFFF]
        return None
    ni = len(o["instances"])
    for e in o["units"]:
        lo, ls = e[1], e[3]
        b = sm[lo:lo + ls]
        a8, ac = struct.unpack_from("<2I", b, 0xA8)
        if b[0xA8 + a8 + index]:
            return bytes(b[0xA8 + struct.unpack_from("<I", b, 0xA8 + ac + 4 * index)[0]:][:0x40])
    return None


def place_matrix(src, pos, yaw_deg):
    m = list(struct.unpack("<16f", src))
    h0 = math.atan2(m[8], m[10])                    # heading of the local +Z row
    d = math.radians(yaw_deg) - h0
    c, s = math.cos(d), math.sin(d)
    for r in (0, 4, 8):                             # row r . Ry (row vectors): x' = x c + z s, z' = -x s + z c
        x, z = m[r], m[r + 2]
        m[r], m[r + 2] = x * c + z * s, -x * s + z * c
    m[12], m[13], m[14] = pos
    return struct.pack("<16f", *m)


def resolve(entries, game_data):
    """-> list of resolved objects {family, record (raw, lods), materials [(src index, retailmat dict)], class, matrices, ...}"""
    import os
    check_entries(entries)
    out = []
    for k, e in enumerate(entries):
        o, path = RM._static(game_data, e["track"], e["static_sha256"])
        fam = e["family"]
        recs = o["instances"] if fam == "instance" else o["proptypes"]
        need(e["index"] < len(recs), "retail_objects[%d]: %s has %d %s types, index %d does not exist"
             % (k, e["track"], len(recs), fam, e["index"]))
        rec = recs[e["index"]]
        mats = []
        for at in MAT_AT:
            mi = struct.unpack_from("<h", rec["raw"], at)[0]
            if mi < 0:
                mats.append(None)
                continue
            mats.append((mi, RM.resolve("retail_objects[%d] material +0x%X" % (k, at),
                                        {"track": e["track"], "material": mi, "static_sha256": e["static_sha256"]}, game_data)))
        sm_path = os.path.join(os.path.dirname(path), "streamed.dat")
        sm = open(sm_path, "rb").read() if fam == "instance" else b""
        src = _first_matrix(o, sm, fam, e["index"])
        need(src is not None, "retail_objects[%d]: %s %s %d has no placement in that track to take its matrix from (refused: "
             "the scale / light elements would be guessed)" % (k, e["track"], fam, e["index"]))
        out.append({"k": k, "family": fam, "track": e["track"], "index": e["index"], "static_sha256": e["static_sha256"],
                    "record": rec, "materials": mats, "class": o["pbytes"][e["index"]] if fam == "prop" else None,
                    "source_matrix": src,
                    "matrices": [place_matrix(src, p["pos"], p.get("yaw_deg", 0.0)) for p in e["placements"]],
                    "positions": [list(p["pos"]) for p in e["placements"]]})
    return out


def assign_units(objs, units):
    """each placement -> the ONE unit region holding it (refused otherwise); capacity vs the retail maxima"""
    per_unit_inst, per_unit_prop = {}, {}
    for ob in objs:
        ob["units"] = []
        for j, (x, _y, z) in enumerate(ob["positions"]):
            hold = [u.k for u in units if u.inside(x, z, grow=-EDGE_M)]
            need(len(hold) == 1, "retail_objects[%d] placement %d at (%.2f, %.2f) is not at least %.2f m inside exactly one unit region "
                 "(%d hold it): move it inside the track's sections, >= 0.1 m from a section boundary (the region is stored as "
                 "float32, so a point on the line is ambiguous)" % (ob["k"], j, x, z, EDGE_M, len(hold)))
            ob["units"].append(hold[0])
            d = per_unit_inst if ob["family"] == "instance" else per_unit_prop
            d[hold[0]] = d.get(hold[0], 0) + 1
    ni = len({(o_["track"], o_["index"]) for o_ in objs if o_["family"] == "instance"})
    npt = len({(o_["track"], o_["index"]) for o_ in objs if o_["family"] == "prop"})
    tot_i = sum(per_unit_inst.values())
    tot_p = sum(per_unit_prop.values())
    cap = {"instance_types": ni, "instance_placements": tot_i, "instances_per_unit": max(per_unit_inst.values() or [0]),
           "prop_types": npt, "prop_placements": tot_p, "props_per_unit": max(per_unit_prop.values() or [0])}
    over = {k: (v, MAX[k]) for k, v in cap.items() if v > MAX[k]}
    need(not over, "retail_objects exceed the retail maxima (the game's pool sizes are unknown; nothing above what retail tracks "
         "carry is written): %s" % ", ".join("%s %d > %d" % (k, a, b) for k, (a, b) in over.items()))
    return dict(cap, retail_maxima=MAX)
