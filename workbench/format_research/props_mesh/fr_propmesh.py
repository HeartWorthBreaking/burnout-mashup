"""fr_propmesh - read-only extractor for Burnout 3 Xbox STATIC.DAT model records (instance models and prop types):
render triangles (local positions, UVs, normals where present, texture per triangle) and every placement's world matrix.

Pure Python 3 stdlib, bounded, read only (retail files are opened "rb" and never written). Labels: CODE = read in the
Takedawn generated code (main19 fresh11 tree, via tools\\xref), DATA = measured on the retail files, HYP = hypothesis.

Two record families share ONE 0x70-byte record format (wm2_static.py, byte-identical 37/37; KB XBOX_TRACK_FORMATS):
  STATIC +0x34 s16 / +0x38 -> instance models  (static roadside scenery: lamp posts, trees, signs, traffic lights ...)
  STATIC +0x36 s16 / +0x3C -> prop types       (smashable props: boxes, cones, road works, market barriers ...)
Record (0x70):
  +0x00 f32[3] bbox max (local), +0x0C u32 raw (not a float; kept raw) | +0x10 f32[3] bbox min, +0x1C u32 raw     DATA
  +0x20 / +0x34 / +0x48 LOD0 / LOD1 / LOD2 struct (0x14 B): {u32 Common = 1, u32 vertex data rel struct, u32 Lock = 0,
        u32 index count, u32 index data rel struct}; LOD1 present when +0x62 bit 0, LOD2 when bit 1          (wm2, CODE)
  +0x5C / +0x5E / +0x60 s16 material index per LOD (STATIC +0x08 table, 0x28 B each)                       CODE
  +0x62 u8 LOD flags | +0x64 f32 LOD switch distance | +0x68 f32 draw distance (both squared by the draw)    CODE
  everything else kept raw.
Draw path (CODE): sub_001ADD60 -> sub_001ACE00 (prop types: STATIC +0x3C, distances +0x64 / +0x68, material +0x5C,
  vertex stream = record + 0x20) -> SetStreamSource(0, vb, stride) with stride = 0x18 when the material's shader type
  (material +0x00) is 9, else 0x14 -> sub_0003A840 per placement -> sub_001D7D10(6 = TRIANGLE STRIP, LOD +0x0C index
  count, LOD +0x10 index data). sub_001ADA40 / sub_001ADD60 also call sub_0003A840 (instance models).
Vertex formats (CODE stride + DATA layout):
  stride 20 (shader type != 9; every instance model with type 8 and props with type 8): f32 x, y, z, f32 u, v  - NO
           normal, NO vertex colour
  stride 24 (shader type 9): f32 x, y, z, u32 normal 11:11:10 (unit length, DATA), f32 u, v - NO vertex colour
  vertex count = (index data - vertex data) / stride (exact on every LOD, DATA); some LODs carry unused trailing vertices.
Placements:
  prop types: STATIC +0x48 matrices via fr_props (per-unit lists).                                             DATA/CODE
  instance models: STREAMED LOD block tail (xbtopo): [+0xA8] (rel +0xA8) -> u8[STATIC +0x34] per-type counts;
           [+0xAC] (rel +0xA8) -> u32[STATIC +0x34] per-type pointers (rel +0xA8, 0 = none) -> count x 0x40-B matrices
           (16-aligned, consecutive in type order).                                                          DATA (this file)
  matrix (both): f32[16]; rows 0-2 = local x / y / z axes (may be scaled: palms 0.72), row 3 (12-14) = position;
           world = local . M  (x' = x*m0 + y*m4 + z*m8 + m12 ...; D3D row-vector convention; DATA check below picks it).
           m3 / m7 / m11 / m15: sub_0003A840 copies them into a 4-vector passed to sub_0034E9A0 (register-combiner
           set-up) and then zeroes the column and sets m15 := 1.0 before the transform (CODE). HYP: per-placement light
           colour (r, g, b, a); values ~0.36-0.65. Reported as "inst_rgba", raw.
Strip -> triangles: standard parity by position, degenerates dropped (KB MESH_AND_COLLISION 1, xbmesh.triangles).

CLI:
  py -3 -B fr_propmesh.py list   TRACK_DIR                 -> JSON: types, counts, bbox, textures
  py -3 -B fr_propmesh.py mesh   TRACK_DIR (I|P)INDEX [LOD] -> JSON: triangles [(texture, [(pos, uv, rgb)] * 3)]
  py -3 -B fr_propmesh.py place  TRACK_DIR (I|P)INDEX       -> JSON: placements with world matrices
  py -3 -B fr_propmesh.py check  TRACK_DIR                 -> JSON: consistency / round-trip verdict
  py -3 -B fr_propmesh.py obj    TRACK_DIR (I|P)INDEX OUT.obj [--world]  (OUT must be a new path; quick look in Blender)
Python: from fr_propmesh import load; t = load(dir); t.triangles("I", 31); t.placements("I", 31)
rgb in the triangle tuples is (1, 1, 1): the vertex formats carry NO vertex colour (see above); use inst_rgba (HYP).
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from fr_common import read_ro, need, FormatError  # noqa: E402
import fr_props  # noqa: E402

LOD_AT = (0x20, 0x34, 0x48)
REC = 0x70
MAX_VERTS = 65536


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def s16(d, o):
    return struct.unpack_from("<h", d, o)[0]


def dec_normal(n):
    x = n & 0x7FF
    x -= 0x800 if x & 0x400 else 0
    y = (n >> 11) & 0x7FF
    y -= 0x800 if y & 0x400 else 0
    z = (n >> 22) & 0x3FF
    z -= 0x400 if z & 0x200 else 0
    return (x / 1023.0, y / 1023.0, z / 511.0)


def strip_tris(idx):
    tris = []
    for i in range(len(idx) - 2):
        a, b, c = idx[i], idx[i + 1], idx[i + 2]
        if a == b or b == c or a == c:
            continue
        tris.append((b, a, c) if i & 1 else (a, b, c))
    return tris


def xform(m, p):
    """world = local . M (row vector); m = 16 floats; the w column is NOT used (the game zeroes it, CODE)"""
    x, y, z = p
    return (x * m[0] + y * m[4] + z * m[8] + m[12], x * m[1] + y * m[5] + z * m[9] + m[13], x * m[2] + y * m[6] + z * m[10] + m[14])


def xform_colmajor(m, p):
    """the transposed reading (control for the convention check only)"""
    x, y, z = p
    return (x * m[0] + y * m[1] + z * m[2] + m[12], x * m[4] + y * m[5] + z * m[6] + m[13], x * m[8] + y * m[9] + z * m[10] + m[14])


class Track:
    def __init__(self, folder):
        self.folder = folder
        self.st = d = read_ro(os.path.join(folder, "static.dat"))
        need(u32(d, 0) == 0x27 and u32(d, 4) == len(d), "not a B3 Xbox STATIC.DAT (version / size)")
        # textures (+0x16 count, +0x18 offsets; name char[32] at +0x48) and materials (+0x08, +0x0C count)
        nt, ta = s16(d, 0x16), u32(d, 0x18)
        self.tex_by_off = {}
        self.tex = []
        for i in range(nt):
            o = u32(d, ta + 4 * i)
            self.tex.append(d[o + 0x48:o + 0x68].split(b"\0")[0].decode("ascii", "replace"))
            self.tex_by_off[o] = i
        mt, nm = u32(d, 0x08), s16(d, 0x0C)
        self.mat = []
        for i in range(nm):
            r = mt + 0x28 * i
            arr, cnt = u32(d, r + 0x0C), struct.unpack_from("<b", d, r + 0x11)[0]
            ti = [self.tex_by_off.get((u32(d, r + arr + 4 * k) + r) & 0xFFFFFFFF) for k in range(max(0, cnt))] if arr else []
            self.mat.append({"shader": u32(d, r), "tex_idx": ti, "tex": [self.tex[t] if t is not None else None for t in ti],
                             "flags_24": u32(d, r + 0x24)})
        self.families = {}
        for fam, cnt_f, arr_f in (("I", 0x34, 0x38), ("P", 0x36, 0x3C)):
            n, a = s16(d, cnt_f), u32(d, arr_f)
            need(0 <= n <= 4096 and (n == 0 or 0x60 <= a and a + REC * n <= len(d)), "%s record array" % fam)
            self.families[fam] = [self._record(fam, k, a + REC * k) for k in range(n)]
        self._inst = None
        self._props = None

    # ------------------------------------------------------------------------------------------- records
    def _record(self, fam, k, ro):
        d = self.st
        raw = d[ro:ro + REC]
        fl = raw[0x62]
        mats = struct.unpack_from("<3h", raw, 0x5C)
        need(0 <= mats[0] < len(self.mat), "%s%d: LOD0 material %d" % (fam, k, mats[0]))
        stride = 24 if self.mat[mats[0]]["shader"] == 9 else 20          # CODE sub_001ACE00
        lods = []
        for li, lo in enumerate(LOD_AT):
            if not (li == 0 or (li == 1 and fl & 1) or (li == 2 and fl & 2)):
                continue
            s = ro + lo
            com, dat, lock, cnt, ip = struct.unpack_from("<5I", d, s)
            need(com == 1 and lock == 0, "%s%d LOD%d header" % (fam, k, li))
            vb, ib = s + dat, s + ip
            need(vb < ib <= len(d) and ib + 2 * cnt <= len(d), "%s%d LOD%d bounds" % (fam, k, li))
            span = ib - vb
            need(span % stride == 0, "%s%d LOD%d: vertex span %d not a multiple of stride %d" % (fam, k, li, span, stride))
            nv = span // stride
            need(nv <= MAX_VERTS, "vertex bound")
            idx = struct.unpack_from("<%dH" % cnt, d, ib)
            need(cnt == 0 or max(idx) < nv, "%s%d LOD%d: index %d >= %d vertices" % (fam, k, li, max(idx) if idx else -1, nv))
            m = mats[li]
            need(0 <= m < len(self.mat), "%s%d LOD%d material %d" % (fam, k, li, m))
            lods.append({"lod": li, "struct": s, "vb": vb, "ib": ib, "nv": nv, "nidx": cnt, "material": m,
                         "shader": self.mat[m]["shader"]})
        f = struct.unpack_from("<3f", raw, 0)
        g = struct.unpack_from("<3f", raw, 0x10)
        return {"fam": fam, "index": k, "rec": ro, "raw": raw, "flags": fl, "mats": mats, "stride": stride, "lods": lods,
                "bbox_max": f, "bbox_min": g, "switch_dist": struct.unpack_from("<f", raw, 0x64)[0],
                "draw_dist": struct.unpack_from("<f", raw, 0x68)[0]}

    def record(self, fam, k):
        need(fam in self.families and 0 <= k < len(self.families[fam]), "no record %s%s" % (fam, k))
        return self.families[fam][k]

    def vertices(self, fam, k, lod=0):
        r = self.record(fam, k)
        L = r["lods"][lod]
        d, st = self.st, r["stride"]
        out = []
        for v in range(L["nv"]):
            o = L["vb"] + st * v
            x, y, z = struct.unpack_from("<3f", d, o)
            if st == 24:
                n = u32(d, o + 12)
                u, w = struct.unpack_from("<2f", d, o + 16)
                out.append({"pos": (x, y, z), "normal": dec_normal(n), "nraw": n, "uv": (u, w)})
            else:
                u, w = struct.unpack_from("<2f", d, o + 12)
                out.append({"pos": (x, y, z), "normal": None, "nraw": None, "uv": (u, w)})
        return out

    def indices(self, fam, k, lod=0):
        L = self.record(fam, k)["lods"][lod]
        return struct.unpack_from("<%dH" % L["nidx"], self.st, L["ib"])

    def texture_of(self, fam, k, lod=0):
        m = self.mat[self.record(fam, k)["lods"][lod]["material"]]
        return m["tex"][0] if m["tex"] else None

    def triangles(self, fam, k, lod=0):
        """[(texture_name, [(pos, uv, rgb)] * 3)]; rgb = (1, 1, 1) - no vertex colour in these formats"""
        vs = self.vertices(fam, k, lod)
        tn = self.texture_of(fam, k, lod)
        return [(tn, [(vs[i]["pos"], vs[i]["uv"], (1.0, 1.0, 1.0)) for i in t]) for t in strip_tris(self.indices(fam, k, lod))]

    def serialize_lod(self, fam, k, lod=0):
        """re-encode vertices + indices from the decoded values (round-trip proof of the vertex layout)"""
        r = self.record(fam, k)
        out = bytearray()
        for v in self.vertices(fam, k, lod):
            out += struct.pack("<3f", *v["pos"])
            if r["stride"] == 24:
                out += struct.pack("<I", v["nraw"])
            out += struct.pack("<2f", *v["uv"])
        idx = self.indices(fam, k, lod)
        return bytes(out), struct.pack("<%dH" % len(idx), *idx)

    # ------------------------------------------------------------------------------------------- placements
    def instance_placements(self):
        """{type: [{unit, matrix(16)}]} from the STREAMED LOD block tails"""
        if self._inst is not None:
            return self._inst
        d = self.st
        n = len(self.families["I"])
        nunit, ut = s16(d, 0x54), u32(d, 0x58)
        sm = read_ro(os.path.join(self.folder, "streamed.dat"))
        res = {k: [] for k in range(n)}
        self.tail_checks = {"units": 0, "layout_ok": 0, "problems": []}
        for u in range(nunit):
            mo, lo, ms, ls = struct.unpack_from("<4I", d, ut + 16 * u)
            if ms == 0 or ls == 0 or n == 0:
                continue
            need(lo + ls <= len(sm), "unit %d LOD block outside STREAMED" % u)
            b = sm[lo:lo + ls]
            a8, ac = u32(b, 0xA8), u32(b, 0xAC)
            self.tail_checks["units"] += 1
            if not a8 or not ac:
                continue
            counts = b[0xA8 + a8:0xA8 + a8 + n]
            ents = struct.unpack_from("<%dI" % n, b, 0xA8 + ac)
            cur = None
            ok = True
            for k in range(n):
                c, e = counts[k], ents[k]
                if (c == 0) != (e == 0):
                    ok = False
                    self.tail_checks["problems"].append("unit %d type %d: count %d pointer 0x%X" % (u, k, c, e))
                    continue
                if not c:
                    continue
                o = 0xA8 + e
                need(o % 16 == 0 and o + 0x40 * c <= len(b), "unit %d type %d matrices" % (u, k))
                if cur is not None and o != cur:
                    ok = False
                    self.tail_checks["problems"].append("unit %d type %d at 0x%X, expected 0x%X" % (u, k, o, cur))
                cur = o + 0x40 * c
                for j in range(c):
                    res[k].append({"unit": u, "matrix": struct.unpack_from("<16f", b, o + 0x40 * j)})
            self.tail_checks["layout_ok"] += ok
        self._inst = res
        return res

    def prop_placements(self):
        if self._props is not None:
            return self._props
        o = fr_props.parse(self.st)
        res = {k: [] for k in range(len(self.families["P"]))}
        for i in fr_props.instances(o):
            res[i["type"]].append({"unit": i["unit"], "matrix": o["matrices"][i["matrix"]], "matrix_index": i["matrix"]})
        self._props = res
        return res

    def placements(self, fam, k):
        p = (self.instance_placements() if fam == "I" else self.prop_placements())[k]
        return [{"unit": x["unit"], "matrix": list(x["matrix"]), "position": list(x["matrix"][12:15]),
                 "inst_rgba": [x["matrix"][3], x["matrix"][7], x["matrix"][11], x["matrix"][15]]} for x in p]

    # ------------------------------------------------------------------------------------------- summaries
    def type_summary(self, fam, k):
        r = self.record(fam, k)
        L0 = r["lods"][0]
        vs = self.vertices(fam, k, 0)
        used = sorted(set(self.indices(fam, k, 0)))
        ps = [vs[i]["pos"] for i in used]
        lo = [min(p[a] for p in ps) for a in range(3)]
        hi = [max(p[a] for p in ps) for a in range(3)]
        return {"id": "%s%d" % (fam, k), "family": "instance" if fam == "I" else "prop", "index": k,
                "class_byte": (self.prop_class[k] if fam == "P" else None),
                "placements": len(self.placements(fam, k)), "stride": r["stride"],
                "lods": [{"lod": L["lod"], "vertices": L["nv"], "indices": L["nidx"],
                          "triangles": len(strip_tris(self.indices(fam, k, i))), "material": L["material"],
                          "shader": L["shader"], "textures": self.mat[L["material"]]["tex"]} for i, L in enumerate(r["lods"])],
                "size_xyz": [round(hi[a] - lo[a], 3) for a in range(3)], "mesh_min": [round(x, 3) for x in lo],
                "mesh_max": [round(x, 3) for x in hi], "rec_bbox_min": [round(x, 3) for x in r["bbox_min"]],
                "rec_bbox_max": [round(x, 3) for x in r["bbox_max"]],
                "switch_dist": r["switch_dist"], "draw_dist": r["draw_dist"], "texture": self.texture_of(fam, k, 0),
                "lod0_vertices": L0["nv"]}

    @property
    def prop_class(self):
        d = self.st
        return list(d[u32(d, 0x44):u32(d, 0x44) + len(self.families["P"])])

    def listing(self):
        return {"folder": self.folder, "textures": len(self.tex), "materials": len(self.mat),
                "instance_models": [self.type_summary("I", k) for k in range(len(self.families["I"]))],
                "prop_types": [self.type_summary("P", k) for k in range(len(self.families["P"]))]}

    def check(self):
        """consistency + round trip: (1) every LOD's vertex span is an exact multiple of the code stride and every index
        is in range (asserted while parsing); (2) vertices / indices re-encoded from the decoded values equal the file
        bytes; (3) the record arrays + their LOD data tile the region up to the next structure with 4-aligned vertex
        starts (wm2 layout rule); (4) the mesh bbox equals the record bbox (+0x00 / +0x10); (5) stride-24 normals are
        unit length and agree with the strip winding; (6) instance tails: count / pointer null-ness agree, matrices
        consecutive in type order; (7) prop placements via fr_props (byte-identical round trip)."""
        d = self.st
        res = {"lods": 0, "reencode_identical": 0, "bbox_match": 0, "bbox_rule": {}, "records": 0, "problems": []}
        tiling = []
        normals_ok = normals = wind_agree = wind_total = 0
        for fam in ("I", "P"):
            for k, r in enumerate(self.families[fam]):
                res["records"] += 1
                for li, L in enumerate(r["lods"]):
                    res["lods"] += 1
                    vb, ib = self.serialize_lod(fam, k, li)
                    if vb == d[L["vb"]:L["ib"]] and ib == d[L["ib"]:L["ib"] + 2 * L["nidx"]]:
                        res["reencode_identical"] += 1
                    else:
                        res["problems"].append("%s%d LOD%d re-encode differs" % (fam, k, li))
                    tiling.append((L["vb"], L["ib"] + 2 * L["nidx"], "%s%d LOD%d" % (fam, k, li)))
                    if r["stride"] == 24:
                        vs = self.vertices(fam, k, li)
                        for v in vs:
                            n = v["normal"]
                            normals += 1
                            normals_ok += abs((n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 - 1.0) < 0.01
                        for t in strip_tris(self.indices(fam, k, li)):
                            a, b, c = (vs[i]["pos"] for i in t)
                            u = [b[q] - a[q] for q in range(3)]
                            w = [c[q] - a[q] for q in range(3)]
                            cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
                            nn = [sum(vs[i]["normal"][q] for i in t) for q in range(3)]
                            dot = sum(cr[q] * nn[q] for q in range(3))
                            if abs(dot) > 1e-9:
                                wind_total += 1
                                wind_agree += dot > 0
                s = self.type_summary(fam, k)
                allp = [v["pos"] for li in range(len(r["lods"])) for v in self.vertices(fam, k, li)]
                ulo = [min(p[a] for p in allp) for a in range(3)]
                uhi = [max(p[a] for p in allp) for a in range(3)]

                def same(lo, hi):
                    return all(abs(lo[a] - r["bbox_min"][a]) < 2e-3 and abs(hi[a] - r["bbox_max"][a]) < 2e-3 for a in range(3))
                if same(s["mesh_min"], s["mesh_max"]):
                    res["bbox_match"] += 1
                    res["bbox_rule"][fam + "_lod0"] = res["bbox_rule"].get(fam + "_lod0", 0) + 1
                elif same(ulo, uhi):
                    res["bbox_match"] += 1
                    res["bbox_rule"][fam + "_all_lods"] = res["bbox_rule"].get(fam + "_all_lods", 0) + 1
                else:
                    res["problems"].append("%s%d record bbox matches neither LOD0 nor all LODs" % (fam, k))
        # tiling: data blocks after each record array must be contiguous (4-aligned starts), ending at +0x44
        tiling.sort()
        gaps = []
        for (a0, e0, n0), (a1, e1, n1) in zip(tiling, tiling[1:]):
            if a1 != e0 + (-e0) % 4:
                gaps.append((n0, n1, e0, a1))
        arrays = sorted(((u32(d, 0x38), s16(d, 0x34)), (u32(d, 0x3C), s16(d, 0x36))))
        # a gap is expected only where the next record array sits (16-aligned) between two families' data
        # a gap is legal only where a record array sits: e0 <= a (16-aligned), and the next data starts 4-aligned after it
        bad_gaps = [g for g in gaps if not any(n and g[2] <= a and a == g[2] + (-g[2]) % 16 and
                                                g[3] == a + REC * n + (-(a + REC * n)) % 4 for a, n in arrays)]
        if tiling:
            first = tiling[0][0]
            a0, n0 = arrays[0] if arrays[0][1] else arrays[1]
            if first != a0 + REC * n0 + (-(a0 + REC * n0)) % 4:
                bad_gaps.append(("record array", "first data", a0 + REC * n0, first))
        last_end = tiling[-1][1] if tiling else None
        res["tiling"] = {"blocks": len(tiling), "gaps_between_blocks": len(gaps), "unexplained_gaps": [
            "%s -> %s: 0x%X..0x%X" % g for g in bad_gaps][:5],
            "data_end": hex(last_end) if last_end else None, "p44": hex(u32(d, 0x44)),
            "data_end_equals_p44": (last_end == u32(d, 0x44)) if tiling else "n/a (no records)"}
        res["normals_unit_length"] = "%d/%d" % (normals_ok, normals)
        res["winding_cross_along_normal"] = "%d/%d" % (wind_agree, wind_total)
        ip = self.instance_placements()
        res["instance_tails"] = dict(self.tail_checks, placements=sum(len(v) for v in ip.values()))
        pp = self.prop_placements()
        res["prop_placements"] = sum(len(v) for v in pp.values())
        res["props_fr_props_identical"] = fr_props.serialize(fr_props.parse(d)) == d
        res["verdict"] = "PASS" if (not res["problems"] and res["reencode_identical"] == res["lods"]
                                    and not bad_gaps and res["tiling"]["data_end_equals_p44"]
                                    and not self.tail_checks["problems"] and res["props_fr_props_identical"]) else "FAIL"
        return res


def load(folder):
    return Track(folder)


def _parse_id(s):
    need(s[:1] in ("I", "P") and s[1:].isdigit(), "type id must be I<n> or P<n>")
    return s[0], int(s[1:])


def write_obj(t, fam, k, out, world=False):
    need(not os.path.exists(out), "%s exists: refusing to overwrite" % out)
    tris = t.triangles(fam, k, 0)
    places = t.placements(fam, k) if world else [{"matrix": None}]
    lines = ["# fr_propmesh %s%d %s (%s); game frame (Y up); game-derived: LOCAL ONLY" % (fam, k, t.texture_of(fam, k), "world" if world else "local")]
    vi = 1
    for p in places:
        for tn, vs in tris:
            for pos, uv, _ in vs:
                q = xform(p["matrix"], pos) if p["matrix"] else pos
                lines.append("v %.5f %.5f %.5f" % q)
                lines.append("vt %.6f %.6f" % (uv[0], 1.0 - uv[1]))
            lines.append("f %d/%d %d/%d %d/%d" % (vi, vi, vi + 1, vi + 1, vi + 2, vi + 2))
            vi += 3
    with open(out, "x", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")
    return {"obj": out, "triangles": len(tris) * len(places), "placements": len(places)}


def main(argv):
    need(len(argv) >= 2, __doc__.split("CLI:")[1].split("Python:")[0])
    cmd, folder = argv[0], argv[1]
    t = load(folder)
    if cmd == "list":
        o = t.listing()
    elif cmd == "mesh":
        fam, k = _parse_id(argv[2])
        lod = int(argv[3]) if len(argv) > 3 else 0
        o = {"id": argv[2], "lod": lod, "texture": t.texture_of(fam, k, lod), "triangles": t.triangles(fam, k, lod)}
    elif cmd == "place":
        fam, k = _parse_id(argv[2])
        o = {"id": argv[2], "convention": "world = local . M (row vector, rows 0-2 axes, row 3 position)",
             "placements": t.placements(fam, k)}
    elif cmd == "check":
        o = t.check()
    elif cmd == "obj":
        fam, k = _parse_id(argv[2])
        o = write_obj(t, fam, k, argv[3], "--world" in argv)
    else:
        raise FormatError("unknown command %s" % cmd)
    print(json.dumps(o, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
