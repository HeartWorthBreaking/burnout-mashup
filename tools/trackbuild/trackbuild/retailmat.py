"""trackbuild.retailmat (0.3.2-rta) - verbatim retail materials: a description material may name
    "retail_material": {"track": "US/C1_V1", "material": 412, "static_sha256": "<sha256 of that track's static.dat>"}
instead of a PNG texture. The 0x28-byte material record (flags word +0x24 included) and every texture it references
(0x40-byte D3D header, tail fields, name and ALL texels / mips) are copied byte for byte from the user's own static.dat
(read only, strict b3static parse). Nothing is re-encoded and no flag bit is set or interpreted by trackbuild.

Draw pass (the only use trackbuild makes of the flags; evidence: tools\\rta3_material_survey.py over all 36 retail tracks,
2,838 mesh blocks): every row after the mesh block's first-pass count +0x73 (18,258 rows) carries bit 0x01 and none lacks it;
alpha-tested cut-outs (bit 0x10, e.g. 0x12 / 0x32 / 0x412) are always first-pass rows. So: bit 0x01 -> pass B (rows after
+0x73), everything else -> pass A. Retail also has 940 first-pass rows with bit 0x01; trackbuild always uses pass B for them
(the majority rule) - recorded as an approximation.

Refused with a reason (never guessed): UV-scroll materials (bit 0x200 or a listed animated material: the +0x10 animated-
material list is not reproduced), Revenge-only bits 0x3000, materials without a texture, texture formats other than DXT1 /
DXT3 / DXT5 (0x0C / 0x0E / 0x0F), a static.dat whose sha256 differs from the description, a bad track name or index.
Products using retail materials contain retail texels: LOCAL ONLY (never share or upload)."""
import hashlib
import os
import re
import struct

from .io import SourceError, need
from ._vendor.trackconv import b3static as S

KEYS = {"track", "material", "static_sha256"}
TRACK_RE = re.compile(r"^[A-Z]{2}/[A-Z][0-9]_V[0-9]$")
FORMATS = {0x0C: "DXT1", 0x0E: "DXT3", 0x0F: "DXT5"}
BLEND, ALPHA_TEST, UV_SCROLL, NO_ZWRITE, REV_ONLY = 0x01, 0x10, 0x200, 0x400, 0x3000
_CACHE = {}


def check_spec(name, spec):
    need(isinstance(spec, dict), "material %s: retail_material must be an object {track, material, static_sha256}" % name)
    extra, missing = sorted(set(spec) - KEYS), sorted(KEYS - set(spec))
    need(not extra and not missing, "material %s: retail_material keys must be exactly track, material, static_sha256 (extra %s, "
         "missing %s)" % (name, extra, missing))
    need(isinstance(spec["track"], str) and TRACK_RE.match(spec["track"]), "material %s: retail_material track %r is not like "
         "US/C1_V1" % (name, spec["track"]))
    need(isinstance(spec["material"], int) and not isinstance(spec["material"], bool) and spec["material"] >= 0,
         "material %s: retail_material material must be a material index (integer >= 0)" % name)
    need(isinstance(spec["static_sha256"], str) and re.match(r"^[0-9a-f]{64}$", spec["static_sha256"]),
         "material %s: retail_material static_sha256 must be 64 lower-case hex digits" % name)


def _static(game_data, track, want_sha):
    from . import donor as DN
    root, _ = DN.resolve(game_data)
    p = os.path.join(root, "Tracks", *track.split("/"), "static.dat")
    need(os.path.isfile(p), "retail_material: %s has no static.dat in your game data (%s)" % (track, p))
    key = (p, os.path.getsize(p), os.path.getmtime(p))
    if key not in _CACHE:
        with open(p, "rb") as f:
            d = f.read()
        _CACHE.clear()
        _CACHE[key] = (hashlib.sha256(d).hexdigest(), d)
    h, d = _CACHE[key]
    need(h == want_sha, "retail_material: %s static.dat is %s, the description expects %s (different game data or a changed "
         "file: refresh the material from YOUR data)" % (track, h[:12], want_sha[:12]))
    try:
        o = S.parse(d, "b3")[0]
    except Exception as e:  # noqa: BLE001
        raise SourceError("retail_material: %s static.dat fails the strict reader: %s" % (track, e))
    return o, p


def resolve(name, spec, game_data):
    """-> {'raw': 0x28 bytes (texture-array pointer zeroed, as the strict reader keeps it), 'textures': [tex dicts verbatim],
    'flags', 'pass', 'formats', 'source'}"""
    check_spec(name, spec)
    o, path = _static(game_data, spec["track"], spec["static_sha256"])
    i = spec["material"]
    need(i < len(o["materials"]), "material %s: %s has %d materials, index %d does not exist" % (name, spec["track"],
                                                                                               len(o["materials"]), i))
    m = o["materials"][i]
    fl = struct.unpack_from("<I", m["raw"], 0x24)[0]
    need(not fl & REV_ONLY, "material %s: flags 0x%X carry the Revenge-only bits 0x3000" % (name, fl))
    need(not fl & UV_SCROLL and i not in o["anim"], "material %s: %s material %d is UV-scrolled / animated (flags 0x%X); the "
         "animated-material list is not reproduced by trackbuild 0.3.2 - refused, pick a still material" % (name, spec["track"], i, fl))
    need(m["tex"], "material %s: %s material %d has no texture" % (name, spec["track"], i))
    texs, fmts = [], []
    for t in m["tex"]:
        tx = o["textures"][t]
        code = (struct.unpack_from("<I", tx["d3d"], 0x0C)[0] >> 8) & 0xFF
        need(code in FORMATS, "material %s: texture %d format 0x%X is not DXT1 / DXT3 / DXT5" % (name, t, code))
        texs.append(dict(tx, _src=(spec["track"], t)))
        fmts.append(FORMATS[code])
    return {"raw": bytes(m["raw"]), "textures": texs, "flags": fl, "pass": "B" if fl & BLEND else "A", "formats": fmts,
            "source": {"track": spec["track"], "material": i, "static_sha256": spec["static_sha256"], "textures": list(m["tex"]),
                       "path": path},
            "kind": kind(fl)}


def kind(fl):
    """descriptive label only (from the decoded bits; never used to choose bytes)"""
    if fl & BLEND:
        return "blended (pass B%s)" % (", no depth write" if fl & NO_ZWRITE else "")
    if fl & ALPHA_TEST:
        return "alpha-tested cut-out (pass A)"
    return "opaque (pass A; other bits copied as is)"
