"""wb_trackedit - Workbench v0.14: track editor, FIRST SLICE (gp\\workbench, 2026-10-29). Not a complete editor.

Authority = the editable track SOURCE of a track project (wb_track.py): the trackbuild description <name>.track.json, its OBJ and
PNG textures. Compiled game files (static.dat, streamed.dat, Gamedata.bgd) are never read or written here; they come only from
Build -> Validate -> Stage (the v0.13 workflow, wb_stage.StageJob with the kit's trackbuild).

Render / UI integration (v0.14 choice): a Python standard-library HTTP server on 127.0.0.1 (random port + random token) serving ONE
self-contained page (trackedit.html: raw WebGL 1, no library, no CDN) in the installed browser. Why: Tk cannot texture-map, no GL
binding / numpy / PIL is installed and none is added; every Windows 10 / 11 has Edge with WebGL; the page holds no state that
matters (every edit is a server call on the source bytes), so the model below is testable without a browser.

What the slice does:
- textured 3D view of the OBJ (per material, its PNG), orbit / pan / zoom / fly navigation, click selection
- layer toggles: collision (collide materials, by surface word), streaming bounds (units), routes (centre line, lane offsets,
  corners), starts (grid slots, start line, checkpoints); visibility (pvs) and LOD are shown as properties only
- inspector: the selected object's source properties; preserved / unsupported data listed and flagged
- validation: the Workbench input checks + the last Build's failed trackbuild gates, mapped to objects and highlighted
- ONE edit: translate a start object (grid slot pos, checkpoint pos, start_line pos) by (dx, dy, dz), with undo / redo
- save: only the edited number spans of the description change (byte splice); everything else stays byte for byte
- Build / Validate / Stage: the v0.13 job (requires a saved, unmodified state)
v0.15 material edits (authored projects; OBJ face groups = the faces after one `usemtl` statement):
- assign an EXISTING material (defined in the description, with a render row) to a face group, or to every group of its
  material: only the `usemtl` name bytes change
- set the trackbuild vertex colour (`v x y z r g b`, 0..1, the baked light) of a group / of every group of its material:
  vertices used only by those faces get their colour tokens rewritten in place; vertices shared with other faces are
  duplicated (new `v` lines after the last existing one, the target faces re-pointed), so no other face changes colour
- both with live preview, undo / redo, save / reopen; every other OBJ line stays byte for byte
- refused with the reason: new materials, materials without a render row, colours outside 0..1
v0.16 material PROPERTY edits (description): texture (an existing project PNG), surface (16-bit word; documented meanings
shown, others labelled unknown), collide, car_solid - each checked by the kit's own trackbuild rules (preflight.check_desc,
build.texture_record, the build's car-solid rule) before it applies; a material shared by several face groups needs an explicit
confirmation; only that value's bytes change (or one member is added). Save is all-or-nothing (a failed replace restores the
files already replaced). Retail materials are inspection only (render class from +0x24, texture alpha statistics).
v0.15 retail mode (--retail FOLDER): a READ-ONLY view of a retail track folder decoded by wb_retail.py into a separate cache;
no edit, undo, save or build path exists in that mode.
v0.17 geometry (authored projects): translate ONE selected face group by (dx, dy, dz) metres - exactly its own faces, shared
vertices duplicated so no other face moves, exact decimal offsets at the source precision; the kit's trackbuild build_units
regenerates collision / unit bounds / streaming / PVS / LOD from the edited OBJ before the edit applies (refused when it cannot);
grid / start line / checkpoints / route stations on the moved faces are reported for separate adjustment, never moved.
v0.18: several face groups at once (Ctrl-click), offsets optionally snapped to a step, two boundary modes: isolate (corners
shared with unselected faces duplicated: gaps / steps) or keep connected (they move: neighbour faces stretch; needs a preview
of the affected neighbours first; collapse / fold-over / winding-vs-normal refused). Corners shared inside the selection stay
shared in both modes.
v0.19: before a move applies, every face of the edited OBJ goes through the kit's own unit regions and clip (trackbuild.units
make_units / clip, as build_units): a face that would lose area outside the unit regions (or a collision face no unit would
hold) refuses the edit, naming the faces and unit boundaries (highlighted in the viewer); unit regions are never expanded.
The clip check is cross-checked against build_units' own per-unit pieces.
v0.20 selection transforms: yaw rotation (optional angle snapping) and positive uniform scaling of the selected face groups
about a pivot (the selection's bounding-box centre or entered XYZ), in both boundary modes, through the same preview / clip
check / trackbuild regeneration / undo; coordinates rounded to their own source precision; the selected faces' stored normals
turn with the yaw, stretched neighbour faces get their normals recomputed (turned with the face plane) or the edit is refused.
v0.21 boundary inspection + controlled welding: open edges by POSITION (uv / colour seams closed by position are not open),
non-manifold / misoriented edges, gap candidates within an explicit metre tolerance; a weld of two open-edge vertices or two
matching open-edge chains moves corners only (the moving side's v lines get the kept side's / the midpoint's coordinates; every
face keeps its v / vt / vn references, so uv / normal / colour seams stay), needs a preview (pairs, gap distances, affected
faces), refuses ambiguous matches, gaps wider than the tolerance, collapsed / folded / flipped faces and non-manifold results,
then the same exact re-read, clip check, trackbuild regeneration and one undo entry. No gap filling, no new faces.
v0.22 layout construction: duplicate the selected face groups (copies appended at the end of the OBJ as new face groups, new v
lines = byte copies after the last v line, vt / vn references reused: exact uv / normals / colours; the copies become the
selection, then move / turn / scale position them) and bridge two explicitly selected, compatible open-edge chains with new quads
(correspondence fixed by consistent winding with both neighbours, an existing material, documented uv mapping, new face normals;
preview key required; degenerate / sliver / twisted / folded / non-manifold / misoriented / clipped results refused). Each is one
undo entry through the same exact re-read, clip check and trackbuild regeneration. No automatic hole filling.
Refused (with the reason): edits of stations, units, route, new materials, automatic gap filling / other topology edits,
traffic, lod, pvs or anything else (see README "Track editor path").

    py -3 -B wb_trackedit.py PROJECT [--port 0] [--no-browser] [--config FILE]
    py -3 -B wb_trackedit.py --retail FOLDER [--port 0] [--no-browser] [--config FILE]     (read only)
"""
import collections
import decimal
import hashlib
import http.server
import json
import math
import os
import re
import secrets
import shutil
import socketserver
import struct
import tempfile
import zlib
import threading
import urllib.parse
import webbrowser

import wb_core as core
import wb_stage as stg
import wb_retail
import wb_track
import wb_construct as wc

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trackedit.html')
EDITABLE = {'grid': ('grid', 'pos'), 'checkpoint': ('checkpoints', 'pos'), 'start_line': ('start_line', 'pos')}
GEOM_MODES = ('isolate', 'connected')                          # v0.18 boundary modes of a geometry move
MAX_MOVE = 50.0                                                 # metres per edit (a typo guard, not a game rule)
SCALE_RANGE = (0.1, 10.0)                                       # v0.20 uniform scale factor per edit (a typo guard)
PIVOT_MAX = 1e6                                                 # |pivot coordinate| in metres
SLIVER_CROSS2 = 1e-4                                            # = trackbuild blocks: a fan triangle with |cross|^2 <= this is dropped
WELD_TOL_MAX = 1.0                                              # v0.21 weld tolerance, metres (explicit per weld; a typo guard)
WELD_KEEP = ('a', 'b', 'mid')                                   # which side stays: A, B, or both move to the midpoint
WELD_MAX_PAIRS = 4096
BRIDGE_UV_M = 4.0                                               # v0.22 bridge uv: one texture repeat per 4 m (documented mapping)
BRIDGE_FOLD_DOT = -0.5                                          # a new face folding more than 120 degrees against a neighbour is refused
KNOWN_DESC = set(wb_track.DESC_KEYS) | {'format', 'label', 'name', 'generator', 'loop_length', 'closed', 'traffic',
                                        'gamedata_header', 'pvs', 'lod', 'wall_gaps', 'barrier_station'}
NOT_EDITABLE_WHY = {
    'stations': 'stations drive the units, route, collision cut lines and the OBJ itself: moving one needs geometry + collision '
                '+ unit + route regeneration (deferred: road tools)',
    'units': 'units are cut station pairs + lateral bounds; changing them changes streaming, collision split and PVS (deferred)',
    'route': 'route lanes / corners are tied to the station offsets and the S4 planner checks (deferred: route editing)',
    'materials': 'new materials and keys other than texture / surface / collide / car_solid are not supported (trackbuild 0.2 '
                 'materials are opaque, one texture); select a material to edit those four properties',
    'obj': 'only translation of selected face groups is supported (v0.18: isolate or keep connected); rotation, scaling, '
           'welding, gap filling, new / deleted geometry, terrain and road generation are deferred (use a 3-D tool on the OBJ)',
    'traffic': 'traffic lanes depend on stations and floor sampling (V7 gate); deferred',
    'lod': 'LOD is regenerated by trackbuild from the mesh; its settings are read only here',
    'pvs': 'visibility is computed by trackbuild; its settings are read only here',
}
GATE_TARGETS = {                                                # trackbuild gate -> what to highlight (docs\ADVANCED.md s5)
    'V5_grid_on_main_lane': 'grid', 'V5_grid_in_regions': 'grid', 'V5_route': 'route', 'V5_gamedata': 'starts',
    'V7_traffic': 'traffic', 'V2_drivable_coverage': 'collision', 'V2_walls_hold': 'collision', 'V2_tree_check': 'collision',
    'V3_winding': 'mesh', 'V3_pvs_walk': 'units', 'V9_pvs_computed': 'units', 'V4_unit_table_tiles_streamed': 'units',
    'V1_streamed_layout': 'units', 'V1_header_decoded': 'units', 'V4_static_identity': 'mesh', 'V6_budgets': 'mesh',
    'V8_lod': 'mesh', 'V10_chevron_index_in_set': 'units'}


class EditError(Exception):
    detail = None                                               # v0.19: extra JSON fields for the viewer (clipped faces)


def err_json(e, **kw):
    d = {'ok': False, 'error': str(e)}
    d.update(getattr(e, 'detail', None) or {})
    d.update(kw)
    return d


# ---------------------------------------------------------------- v0.16 material properties (trackbuild 0.2 schema)
MAT_PROPS = ('texture', 'surface', 'collide', 'car_solid')      # = trackbuild preflight.MATERIAL_KEYS
UNSUPPORTED_MAT_PROPS = {'alpha', 'alpha_test', 'blend', 'additive', 'transparent', 'opacity', 'shader', 'type', 'flags',
                         'animated', 'animation', 'uv_scroll', 'reflection', 'specular', 'normal_map', 'emissive', 'water',
                         'decal', 'textures', 'lightmap'}      # = trackbuild preflight.UNSUPPORTED_MATERIAL
SURFACE_RE = re.compile(r'^0x[0-9A-Fa-f]{1,4}$')
# documented meanings only (kit trackbuild docs\ADVANCED.md + README; 0x1000 rule: trackbuild build.py, runtime gp_trk_1)
SURFACE_MEANINGS = {0x0001: 'tarmac', 0x0002: 'concrete', 0x000F: 'grass', 0x0018: 'road-facing wall',
                    0x1018: 'back face (flag 0x1000: not solid for cars)'}
CAR_SOLID_NOTE = ('car_solid is a trackbuild CHECK flag: it changes no built byte by itself; it only allows a collide material '
                  'to use a surface word with flag 0x1000 (not solid for cars). The surface word is what reaches the build.')
KIT_MODULES = ('trackbuild/io.py', 'trackbuild/preflight.py', 'trackbuild/build.py', 'trackbuild/units.py')
CLIP_TOL_M2 = 1e-6          # v0.19 clip check: area tolerance (float noise only) + 1e-9 x the face area


def surface_meaning(w):
    if w in SURFACE_MEANINGS:
        return 'documented: %s' % SURFACE_MEANINGS[w]
    if w & 0x1000:
        return ('flag 0x1000 set: not solid for cars (documented); the rest of 0x%04X: UNKNOWN semantics (accepted by trackbuild, '
                'in-game effect not documented)' % w)
    return 'UNKNOWN semantics: a 16-bit word trackbuild accepts; its in-game effect is not documented'


def kit_trackbuild(cfg):
    """the kit's own trackbuild modules (io, preflight, build), after their sha256 matched the kit's SHA256SUMS.txt"""
    wb_retail.readers(cfg)                                      # verifies the vendored readers, puts the kit's trackbuild first
    tb = core.kit_path(cfg, wb_retail.TB_DIR)                  # v0.28: the bound trackbuild tree
    sums = {}
    for ln in open(os.path.join(tb, 'SHA256SUMS.txt'), encoding='utf-8'):
        p = ln.split()
        if len(p) == 2:
            sums[p[1].lstrip('*')] = p[0]
    for rel in KIT_MODULES:
        h = wb_retail.sha_file(os.path.join(tb, *rel.split('/')))
        if sums.get(rel) != h:
            raise EditError('kit %s does not match its SHA256SUMS.txt: material checks refused' % rel)
    import importlib
    import sys
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        return {k: importlib.import_module('trackbuild.' + k) for k in ('io', 'preflight', 'build', 'units')}
    finally:
        sys.dont_write_bytecode = old


def _poly_area(pts):
    """trackbuild's face area (fan of cross products, as units.assign)"""
    a = 0.0
    for i in range(1, len(pts) - 1):
        A, B, C = pts[0], pts[i], pts[i + 1]
        u = (B[0] - A[0], B[1] - A[1], B[2] - A[2])
        v = (C[0] - A[0], C[1] - A[1], C[2] - A[2])
        a += 0.5 * ((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2 + (u[0] * v[1] - u[1] * v[0]) ** 2) ** 0.5
    return a


def _clip_lanes(UN, poly, lanes):
    """the kit's Sutherland-Hodgman clip through several lanes, exactly as units.assign (empty when fewer than 3 points stay)"""
    for lane in lanes:
        poly = UN.clip(poly, lane)
        if len(poly) < 3:
            return []
    return poly


def _union_area(UN, units, fv, idx):
    """area of a face inside the UNION of the unit regions idx (overlapping regions counted once): each unit's piece minus the
    regions of the units before it, cut into convex pieces with the kit's own clip"""
    total = 0.0
    for n, k in enumerate(idx):
        parts = [q for q in [_clip_lanes(UN, fv, units[k].lanes)] if q]
        for j in idx[:n]:
            nxt = []
            for q in parts:
                for a, c, b in units[j].lanes:
                    o = _clip_lanes(UN, q, [(-a, -c, -b)])
                    if o:
                        nxt.append(o)
                    q = _clip_lanes(UN, q, [(a, c, b)])
                    if not q:
                        break
            parts = nxt
            if not parts:
                break
        total += sum(_poly_area([v[0] for v in q]) for q in parts)
    return total


def _yaw_cs(A):
    """Decimal degrees -> (cos, sin) as Decimals; exact for multiples of 90 degrees"""
    q = A % 360
    if q < 0:
        q += 360
    exact = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}
    if q in exact:
        return tuple(decimal.Decimal(x) for x in exact[int(q)])
    r = math.radians(float(A))
    return decimal.Decimal(repr(math.cos(r))), decimal.Decimal(repr(math.sin(r)))


def _xf(p, P, c, s, k):
    """p' = P + k * Ry (p - P); Ry turns +x towards -z for a positive angle (counter-clockwise seen from above)"""
    x, y, z = (p[i] - P[i] for i in range(3))
    return [P[0] + k * (c * x + s * z), P[1] + k * y, P[2] + k * (c * z - s * x)]


def _newell(P):
    n = [0.0, 0.0, 0.0]
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n


def _unit(v):
    L = math.sqrt(sum(x * x for x in v))
    return [x / L for x in v] if L > 0 else None


def _turn(a, b, v):
    """rotate v by the smallest rotation taking unit vector a to unit vector b (Rodrigues; a . b > -1)"""
    c = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    k = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    kv = [k[1] * v[2] - k[2] * v[1], k[2] * v[0] - k[0] * v[2], k[0] * v[1] - k[1] * v[0]]
    kd = k[0] * v[0] + k[1] * v[1] + k[2] * v[2]
    return [v[i] * c + kv[i] + k[i] * kd / (1 + c) for i in range(3)]


def _fan_good(P, n):
    """trackbuild blocks' rule per fan triangle (0, i, i + 1): kept when |cross|^2 > 1e-4 and cross . (first corner normal) > 0"""
    out = []
    for i in range(1, len(P) - 1):
        e1 = [P[i][k] - P[0][k] for k in range(3)]
        e2 = [P[i + 1][k] - P[0][k] for k in range(3)]
        cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        out.append(sum(x * x for x in cr) > SLIVER_CROSS2 and sum(x * y for x, y in zip(cr, n)) > 0)
    return out


def _vn_text(vals, d):
    return [_fmt(decimal.Decimal(repr(x)), d) for x in vals]


def _vn_value(addn, nlines, k, lines):
    """the float value of vn index k (an existing line or one of the lines being added)"""
    r = lines[nlines[k - 1]] if k <= len(nlines) else addn[k - len(nlines) - 1]
    return [float(x) for x in r.split()[1:4]]


def _dec_tokens(raw, n, what, line):
    toks = [t.decode('ascii') for t in raw.split()[1:1 + n]]
    for t in toks:
        if not re.match(r'^[+-]?\d+(\.\d+)?$', t):
            raise EditError('%s line %d: %r is not a plain decimal number: refused (file kept)' % (what, line + 1, t))
    return [decimal.Decimal(t) for t in toks], max(len(t.split('.')[1]) if '.' in t else 0 for t in toks)


def _dstr(x):
    return format(x.normalize(), 'f') if x else '0'


def _fmt(x, d):
    q = decimal.Decimal(1).scaleb(-d)
    v = x.quantize(q, decimal.ROUND_HALF_EVEN)
    return format(abs(v) if v == 0 else v, 'f')


def at1(T, l):
    """a location of a _topo table as '[x, y, z]' (its decimal text)"""
    return '[%s]' % ', '.join(_dstr(x) for x in T['locs'][l]['p'])


def _shape_check(where, P0, P1, N):
    """v0.21 weld: one changed face, corners P0 -> P1 (floats), N = its corners' stored normals (None if absent). Refused:
    area <= 1e-4 m2 (trackbuild degenerate rule), a fan triangle that folds over (its cross product turns), a triangle turning
    against a stored normal it agreed with (V3_winding), a triangle trackbuild keeps today that it would drop (sliver or against
    the first-corner normal). -> the quad non-planarity after (m)"""
    sub = lambda a, b: [a[0] - b[0], a[1] - b[1], a[2] - b[2]]  # noqa: E731
    crs = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]  # noqa: E731
    dt = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]  # noqa: E731
    area = 0.0
    for i in range(1, len(P1) - 1):
        c0 = crs(sub(P0[i], P0[0]), sub(P0[i + 1], P0[0]))
        c1 = crs(sub(P1[i], P1[0]), sub(P1[i + 1], P1[0]))
        area += 0.5 * dt(c1, c1) ** 0.5
        if dt(c0, c0) > 1e-12 and dt(c0, c1) <= 0:
            raise EditError('refused: %s would fold over (a triangle flips) after the weld. Nothing changed' % where)
        for n in N:
            if n is not None and dt(c0, n) > 0 and dt(c1, n) <= 0:
                raise EditError('refused: %s would turn against its stored normal (trackbuild V3_winding) after the weld. '
                                'Nothing changed' % where)
    if area <= 1e-4:
        raise EditError('refused: %s would collapse (area %.6f m2; trackbuild refuses degenerate faces). Nothing changed'
                        % (where, area))
    if N and N[0] is not None:
        for i, (a, b) in enumerate(zip(_fan_good(P0, N[0]), _fan_good(P1, N[0]))):
            if a and not b:
                raise EditError('refused: trackbuild would drop triangle %d of %s after the weld (sliver under 0.005 m2 or '
                                'against its stored normal; Build drops such triangles silently). Nothing changed' % (i + 1, where))
    if len(P1) == 4:
        nrm = crs(sub(P1[1], P1[0]), sub(P1[2], P1[0]))
        L = dt(nrm, nrm) ** 0.5
        if L > 0:
            return abs(dt(sub(P1[3], P1[0]), nrm)) / L
    return 0.0


def kit_check_material(cfg, project, obj, name, m, texture_changed):
    """the edited material through the kit's rules: preflight.check_desc (keys, texture string / PNG / exists / opaque, surface
    hex 0..0xFFFF), build.texture_record (power of two 4..1024, name length) and the build's car-solid rule"""
    K = kit_trackbuild(cfg)
    try:
        K['preflight'].check_desc(project, {'materials': {name: m}, 'rows': [name], 'obj': obj})
        w = int(m['surface'], 16)
        if m.get('collide') and m.get('car_solid', True) and w & 0x1000:
            raise K['io'].SourceError('material %s: surface 0x%04X has flag 0x10 (not solid for cars); use a word without it or set '
                                      'car_solid false (trackbuild build rule)' % (name, w))
        if texture_changed:
            tp = os.path.join(project, *m['texture'].split('/'))
            tw, th, rgb = K['io'].read_png(tp)
            K['build'].texture_record(os.path.splitext(os.path.basename(tp))[0], tw, th, rgb)
    except K['io'].SourceError as e:
        raise EditError('refused by the kit trackbuild rules: %s' % e)
    except (OSError, ValueError, struct.error, zlib.error) as e:
        raise EditError('refused: the kit trackbuild could not read the texture (%s: %s)' % (type(e).__name__, e))


def desc_splice(b, values):
    """v0.23: description bytes with whole top-level values replaced (or appended as new members before the closing brace);
    every other byte - unknown keys, number spellings, order - is kept. Values are written as json.dump(indent=1) at depth 1."""
    sp = json_spans(b)
    edits = []
    tops = [v for k, v in sp.items() if len(k) == 1]
    last = max(e for _s, e in tops) if tops else None
    for key, v in values.items():
        txt = json.dumps(v, indent=1).replace('\n', '\n ').encode('utf-8')
        if (key,) in sp:
            s, e = sp[(key,)]
            edits.append((s, e, txt))
        else:
            if last is None:
                raise EditError('internal: the description has no members; not applied')
            edits.append((last, last, b',\n ' + json.dumps(key).encode('utf-8') + b': ' + txt))
    out = bytearray(b)
    for s, e, t in sorted(edits, key=lambda z: (-z[0], -z[1])):
        out[s:e] = t
    out = bytes(out)
    d = json.loads(out.decode('utf-8'))
    if any(d.get(k) != json.loads(json.dumps(v)) for k, v in values.items()):
        raise EditError('internal: a spliced description value does not read back; not applied')
    return out


# ---------------------------------------------------------------- JSON value spans (byte offsets; nothing is re-serialised)
def json_spans(b):
    """bytes of a JSON document -> {path tuple: (start, end)} for every value (end exclusive). Strict enough for a document
    json.loads already accepted; used only to splice number values in place."""
    out = {}
    n = len(b)
    ws = b' \t\r\n'

    def skip(i):
        while i < n and b[i] in ws:
            i += 1
        return i

    def string(i):                                              # b[i] == '"'
        i += 1
        while True:
            c = b[i]
            if c == 0x5C:
                i += 2
            elif c == 0x22:
                return i + 1
            else:
                i += 1

    def value(i, path):
        i = skip(i)
        s = i
        c = b[i]
        if c == 0x7B:                                           # {
            i = skip(i + 1)
            if b[i] == 0x7D:
                i += 1
            else:
                while True:
                    i = skip(i)
                    ks = i
                    i = string(i)
                    key = json.loads(b[ks:i].decode('utf-8'))
                    i = skip(i)
                    i += 1                                      # ':'
                    i = value(i, path + (key,))
                    i = skip(i)
                    if b[i] == 0x2C:
                        i += 1
                        continue
                    i += 1                                      # '}'
                    break
        elif c == 0x5B:                                         # [
            i = skip(i + 1)
            if b[i] == 0x5D:
                i += 1
            else:
                k = 0
                while True:
                    i = value(i, path + (k,))
                    k += 1
                    i = skip(i)
                    if b[i] == 0x2C:
                        i += 1
                        continue
                    i += 1
                    break
        elif c == 0x22:
            i = string(i)
        else:
            while i < n and b[i] not in b' \t\r\n,]}':
                i += 1
        out[path] = (s, i)
        return i
    value(0, ())
    return out


def fmt_num(x):
    if not math.isfinite(x):
        raise EditError('not a finite number: %r' % x)
    x = round(x, 4)
    return json.dumps(float(x))


# ---------------------------------------------------------------- the source model
class TrackSource:
    """one opened track project; edits are byte splices of the description, kept in undo / redo stacks"""

    def __init__(self, cfg, project):
        self.cfg, self.project = cfg, os.path.abspath(project)
        rid, why = stg.detect(self.project)
        if rid not in ('track-project', 'trackbuild-testloop'):
            hint = ''
            if os.path.isdir(self.project) and all(os.path.isfile(os.path.join(self.project, n)) for n in wb_retail.REQUIRED):
                hint = ' This looks like a RETAIL track folder: open it read only with --retail (never as an editable project).'
            raise EditError((why or 'not a track project (recipe %s): open a folder made by New track project' % rid) + hint)
        self.rid = rid
        self.ident = wb_track.read_project(self.project)[0] if rid == 'track-project' else None
        self.check = wb_track.input_check(cfg, self.project, rid)
        descs = [k for k in (self.check.get('inputs') or {}) if k.endswith('.track.json')]
        self.desc_rel = (self.ident or {}).get('desc') or (descs[0] if descs else None)
        if not self.desc_rel:
            raise EditError('no readable track description: %s' % '; '.join(self.check['problems'][:4]))
        self.desc_path = os.path.join(self.project, self.desc_rel)
        self.saved = open(self.desc_path, 'rb').read()
        self.opened = self.saved
        self.cur = self.saved
        self.undo_stack, self.redo_stack = [], []
        # v0.15: the OBJ is a second editable buffer (material assignment / vertex colour), only when it passed the input check
        orel = str(self.desc().get('obj', '')).replace('\\', '/')
        self.obj_rel = orel if orel and orel in (self.check.get('inputs') or {}) else None
        self.obj_path = os.path.join(self.project, *orel.split('/')) if self.obj_rel else None
        self.obj_saved = open(self.obj_path, 'rb').read() if self.obj_rel else None
        self.obj_cur = self.obj_saved
        self.others0 = self._others()
        self.last_build = None

    # ---------------- state
    def _others(self):
        return {k: v for k, v in stg.tree_hashes(self.project).items() if k not in (self.desc_rel, self.obj_rel)}

    def desc(self):
        return json.loads(self.cur.decode('utf-8'))

    def dirty(self):
        return self.cur != self.saved or self.obj_cur != self.obj_saved

    def content_sha(self):
        return hashlib.sha256(hashlib.sha256(self.cur).digest() + hashlib.sha256(self.obj_cur or b'').digest()).hexdigest()

    def state(self):
        return {'mode': 'authored', 'project': self.project, 'desc': self.desc_rel, 'obj': self.obj_rel, 'dirty': self.dirty(),
                'undo': [u['label'] for u in self.undo_stack], 'redo': [u['label'] for u in self.redo_stack],
                'sha256': hashlib.sha256(self.cur).hexdigest(), 'saved_sha256': hashlib.sha256(self.saved).hexdigest(),
                'obj_sha256': hashlib.sha256(self.obj_cur).hexdigest() if self.obj_cur is not None else None,
                'content_sha256': self.content_sha()}

    def _buf(self, f):
        if f == 'both':                                     # v0.23: one undo entry for a description + OBJ edit
            return (self.cur, self.obj_cur)
        return self.cur if f == 'desc' else self.obj_cur

    def _setbuf(self, f, b):
        if f == 'both':
            self.cur, self.obj_cur = b
        elif f == 'desc':
            self.cur = b
        else:
            self.obj_cur = b

    def _push(self, f, label, after, **extra):
        self.undo_stack.append(dict(extra, label=label, file=f, before=self._buf(f), after=after))
        self.redo_stack.clear()
        self._setbuf(f, after)

    # ---------------- edits
    def _target(self, kind, index):
        if kind not in EDITABLE:
            top = {'station': 'stations', 'unit': 'units', 'corner': 'route', 'lane': 'route', 'material': 'materials',
                   'mesh': 'obj', 'traffic': 'traffic', 'lod': 'lod', 'pvs': 'pvs'}.get(kind, kind)
            raise EditError('edit of %r refused: %s' % (kind, NOT_EDITABLE_WHY.get(top, 'not editable in this first slice '
                                                                                         '(supported: move grid slot / checkpoint / start line)')))
        key, field = EDITABLE[kind]
        d = self.desc()
        if kind == 'start_line':
            path = (key, field)
            obj = d.get(key)
        else:
            arr = d.get(key)
            if not isinstance(index, int) or not isinstance(arr, list) or not 0 <= index < len(arr):
                raise EditError('%s %r does not exist (0..%d)' % (kind, index, len(arr or []) - 1))
            path = (key, index, field)
            obj = arr[index]
        if not isinstance(obj, dict) or not (isinstance(obj.get(field), list) and len(obj[field]) == 3 and
                                             all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in obj[field])):
            raise EditError('%s %r has no [x, y, z] %s in the source: refused (data kept as is)' % (kind, index, field))
        return path, obj[field]

    def move(self, kind, index, delta):
        if not (isinstance(delta, (list, tuple)) and len(delta) == 3):
            raise EditError('delta must be [dx, dy, dz] in metres')
        try:
            delta = [float(x) for x in delta]
        except (TypeError, ValueError):
            raise EditError('delta must be numbers')
        if not all(math.isfinite(x) for x in delta) or max(abs(x) for x in delta) > MAX_MOVE:
            raise EditError('delta %r refused: finite, at most %.0f m per axis per edit' % (delta, MAX_MOVE))
        if not any(delta):
            raise EditError('delta is zero: nothing to edit')
        path, old = self._target(kind, index)
        sp = json_spans(self.cur)
        splices = []
        for i in range(3):
            s, e = sp[path + (i,)]
            splices.append((s, e, fmt_num(old[i] + delta[i]).encode('ascii')))
        before = self.cur
        b = bytearray(self.cur)
        for s, e, new in sorted(splices, reverse=True):
            b[s:e] = new
        after = bytes(b)
        json.loads(after.decode('utf-8'))                                   # still the same document shape
        label = 'move %s %s by %s' % (kind, '' if index is None else index, delta)
        self._push('desc', label, after, kind=kind, index=index)
        return {'ok': True, 'label': label, 'new': [old[i] + delta[i] for i in range(3)]}

    # ---------------- v0.15 material edits (OBJ face groups)
    def _groups_for(self, group, scope):
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: material edits need a readable OBJ (%s)' %
                            '; '.join(self.check['problems'][:3]))
        lines, groups, vlines = obj_index(self.obj_cur)
        if not isinstance(group, int) or isinstance(group, bool) or not 0 <= group < len(groups):
            raise EditError('face group %r does not exist (0..%d)' % (group, len(groups) - 1))
        if scope not in ('group', 'material'):
            raise EditError('scope %r refused: "group" (this usemtl block) or "material" (every block of its material)' % (scope,))
        g = groups[group]
        return lines, groups, vlines, g, ([g] if scope == 'group' else [x for x in groups if x['mat'] == g['mat']])

    def assign_material(self, group, material, scope='group'):
        """assign an EXISTING material to a face group (or every group of its material): only usemtl name bytes change"""
        lines, groups, vlines, g, targets = self._groups_for(group, scope)
        d = self.desc()
        mats = d.get('materials') or {}
        if not isinstance(material, str) or material not in mats:
            raise EditError('material %r refused: only existing materials of the description can be assigned (%s); creating '
                            'materials is not supported' % (material, ', '.join(sorted(mats))))
        if material not in (d.get('rows') or []):
            raise EditError('material %r has no render row in "rows": trackbuild refuses it; not assignable' % material)
        extra = sorted(set(mats[material]) - {'texture', 'surface', 'collide', 'car_solid'})
        if extra:
            raise EditError('material %r has keys trackbuild refuses (%s): not assignable' % (material, ', '.join(extra)))
        targets = [x for x in targets if x['mat'] != material]
        if not targets:
            raise EditError('group %d already uses %s: nothing to edit' % (group, material))
        new = list(lines)
        for x in targets:
            m = re.match(rb'^(\s*usemtl\s+)(\S+)', new[x['line']])
            if not m:
                raise EditError('internal: line %d is not a usemtl statement' % (x['line'] + 1))
            new[x['line']] = m.group(1) + material.encode('ascii') + new[x['line']][m.end(2):]
        label = 'assign %s to %s %d (%s, %d block(s))' % (material, scope, group, g['mat'], len(targets))
        self._push('obj', label, b''.join(new), kind='assign', index=group)
        return {'ok': True, 'label': label, 'groups': [x['i'] for x in targets]}

    def set_colour(self, group, rgb, scope='group'):
        """trackbuild vertex colour (v x y z r g b, 0..1) of the faces of a group / of every group of its material"""
        if not (isinstance(rgb, (list, tuple)) and len(rgb) == 3 and
                all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in rgb)):
            raise EditError('colour must be [r, g, b] numbers')
        rgb = [float(c) for c in rgb]
        if not all(math.isfinite(c) and 0.0 <= c <= 1.0 for c in rgb):
            raise EditError('colour %r refused: each channel 0..1 (trackbuild clamps above 1.0; the editor keeps the stored '
                            'value what the game gets)' % (rgb,))
        lines, groups, vlines, g, targets = self._groups_for(group, scope)
        F = set(li for x in targets for li in x['faces'])
        if not F:
            raise EditError('group %d has no faces: nothing to colour' % group)
        use_in, use_out, faces = set(), set(), {}
        for x in groups:
            for li in x['faces']:
                toks = list(re.finditer(rb'\S+', lines[li]))[1:]
                vis = []
                for t in toks:
                    try:
                        vi = int(t.group().split(b'/')[0])
                    except ValueError:
                        raise EditError('line %d: face token %r is not v/vt/vn: refused (file kept)' % (li + 1, t.group()))
                    if not 0 < vi <= len(vlines):
                        raise EditError('line %d: vertex index %d outside 1..%d: refused (file kept)' % (li + 1, vi, len(vlines)))
                    vis.append((t, vi))
                if li in F:
                    faces[li] = vis
                    use_in.update(v for _, v in vis)
                else:
                    use_out.update(v for _, v in vis)
        shared = sorted(use_in & use_out)
        if shared and min(F) < vlines[-1]:
            raise EditError('faces of this group come before the last vertex line: duplicating its shared vertices would need '
                            'renumbering (unsupported OBJ layout; file kept)')
        dec = 3
        for li in vlines:
            t = lines[li].split()
            if len(t) == 7 and b'.' in t[4]:
                dec = len(t[4].split(b'.')[1])
                break
        col = b' '.join(('%.*f' % (dec, c)).encode('ascii') for c in rgb)

        def has_col(vi):
            t = lines[vlines[vi - 1]].split()
            try:
                return len(t) == 7 and all(round(float(a), dec) == round(c, dec) for a, c in zip(t[4:7], rgb))
            except ValueError:
                return False
        if all(has_col(vi) for vi in use_in):
            raise EditError('group %d already has colour %s: nothing to edit' % (group, col.decode()))
        new = list(lines)

        def recolour(raw):
            toks = list(re.finditer(rb'\S+', raw))
            if len(toks) == 7:
                return raw[:toks[4].start()] + col + raw[toks[6].end():]
            if len(toks) == 4:
                return raw[:toks[3].end()] + b' ' + col + raw[toks[3].end():]
            raise EditError('vertex line %r is not v x y z [r g b]: refused (file kept)' % raw[:60])
        changed = 0
        for vi in sorted(use_in - use_out):
            li = vlines[vi - 1]
            nl = recolour(lines[li])
            changed += nl != lines[li]
            new[li] = nl
        remap, add = {}, []
        last = lines[vlines[-1]]
        eol = last[len(last.rstrip(b'\r\n')):] or b'\n'
        for vi in shared:
            t = lines[vlines[vi - 1]].split()
            add.append(b'v ' + b' '.join(t[1:4]) + b' ' + col + eol)
            remap[vi] = len(vlines) + len(add)
        for li, vis in faces.items():
            raw = new[li]
            for t, vi in sorted(vis, key=lambda z: -z[0].start()):
                if vi in remap:
                    rest = t.group().split(b'/', 1)
                    tok = str(remap[vi]).encode('ascii') + (b'/' + rest[1] if len(rest) > 1 else b'')
                    raw = raw[:t.start()] + tok + raw[t.end():]
            new[li] = raw
        if not changed and not add:
            raise EditError('group %d already has colour %s: nothing to edit' % (group, col.decode()))
        if add and not new[vlines[-1]].endswith((b'\n', b'\r')):        # (cannot happen: faces follow the last v line)
            raise EditError('internal: the last vertex line has no line end')
        new[vlines[-1] + 1:vlines[-1] + 1] = add
        label = 'colour %s %d (%s) = %s' % (scope, group, g['mat'], col.decode())
        self._push('obj', label, b''.join(new), kind='colour', index=group)
        return {'ok': True, 'label': label, 'recoloured_in_place': changed, 'duplicated_shared_vertices': len(add)}

    # ---------------- v0.17 / v0.18 geometry: translate selected face groups (faces after one usemtl statement each)
    def translate_group(self, group, delta):
        """v0.17 call: one face group, isolate mode"""
        return self.translate_groups([group], delta, 'isolate')

    def _selection(self, groups):
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: geometry edits need a readable OBJ (%s)' %
                            '; '.join(self.check['problems'][:3]))
        lines, gall, vlines = obj_index(self.obj_cur)
        if not isinstance(groups, (list, tuple)) or not groups:
            raise EditError('the selection is empty: select one or more face groups (click; Ctrl-click adds / removes)')
        sel = []
        for g in groups:
            if not isinstance(g, int) or isinstance(g, bool) or not 0 <= g < len(gall):
                raise EditError('face group %r does not exist (0..%d)' % (g, len(gall) - 1))
            if g in sel:
                raise EditError('face group %d is selected twice' % g)
            sel.append(g)
        sel.sort()
        F = set(li for g in sel for li in gall[g]['faces'])
        if not F:
            raise EditError('the selected face group(s) have no faces: nothing to move')
        use_in, use_out, faces, others = self._face_use(lines, gall, vlines, F)
        gof = {li: x['i'] for x in gall for li in x['faces']}
        nb = sorted(li for li, vis in others.items() if any(vi in use_in for _, vi in vis))
        return {'lines': lines, 'groups': gall, 'vlines': vlines, 'sel': sel, 'F': F, 'use_in': use_in, 'use_out': use_out,
                'faces': faces, 'others': others, 'gof': gof, 'nb': nb}

    def _preview_key(self, sel, mode):
        return hashlib.sha256(('%s|%s|%s' % (self.content_sha(), ','.join(map(str, sel)), mode)).encode()).hexdigest()[:16]

    def preview_translation(self, groups, mode='isolate'):
        """what a move of the selection would touch, WITHOUT changing anything: selected faces / corners, corners shared inside
        the selection (kept shared), boundary corners shared with unselected faces, and those neighbour faces (isolate: gaps /
        steps open along them; connected: they stretch). The returned preview_key must accompany a connected-mode move."""
        if mode not in GEOM_MODES:
            raise EditError('boundary mode %r refused: %s' % (mode, ' or '.join(GEOM_MODES)))
        X = self._selection(groups)
        cnt = collections.Counter(vi for vis in X['faces'].values() for _, vi in vis)
        bnd = X['use_in'] & X['use_out']
        ng = sorted({X['gof'][li] for li in X['nb']})
        return {'ok': True, 'mode': mode, 'groups': X['sel'], 'faces': len(X['F']), 'corners': len(X['use_in']),
                'shared_inside_selection': sum(1 for v, c in cnt.items() if c > 1), 'boundary_corners': len(bnd),
                'neighbour_faces': len(X['nb']), 'neighbour_groups': ng,
                'effect': ('%d boundary corner(s) would be duplicated: gaps / steps open along %d neighbour face(s) in %d group(s)'
                           % (len(bnd), len(X['nb']), len(ng)) if mode == 'isolate' else
                           '%d boundary corner(s) would move with the selection: %d neighbour face(s) in %d group(s) stretch'
                           % (len(bnd), len(X['nb']), len(ng))) if bnd else 'no boundary corners: nothing else is affected',
                'preview_key': self._preview_key(X['sel'], mode)}

    def translate_groups(self, groups, delta, mode='isolate', snap=None, preview_key=None):
        """move the selected face groups (each = exactly the `f` lines after its usemtl statement; never other groups of the same
        material) by delta = [dx, dy, dz] metres, optionally snapped to a multiple of `snap` metres per axis. Corners shared
        between selected faces stay shared (moved once). Corners shared with unselected faces:
        - isolate: duplicated (new `v` lines after the last one, the selected faces re-pointed): no other face moves, gaps /
          steps open along the boundary;
        - connected: moved in place, so the neighbour faces using them stretch (needs the preview_key of a preview of this
          exact selection + mode + buffer; the stretched faces are checked: no collapse, fold-over or winding / stored-normal
          disagreement).
        Corner tokens are rewritten as exact decimal sums at their own precision; vt / vn / colours / every other line stay
        byte for byte. The kit's trackbuild build_units then regenerates collision, bounds, streaming, PVS and LOD from the
        edited OBJ (dry run); any refusal refuses the edit."""
        if mode not in GEOM_MODES:
            raise EditError('boundary mode %r refused: %s' % (mode, ' or '.join(GEOM_MODES)))
        req = self._delta(delta)
        D = [decimal.Decimal(repr(x)) for x in req]
        snapped = None
        if snap is not None:
            if not isinstance(snap, (int, float)) or isinstance(snap, bool) or not math.isfinite(snap) or not 0 < snap <= MAX_MOVE:
                raise EditError('snap %r refused: a step in metres, 0 < step <= %.0f (or none)' % (snap, MAX_MOVE))
            S = decimal.Decimal(repr(float(snap)))
            D = [(x / S).to_integral_value(decimal.ROUND_HALF_UP) * S for x in D]
            if not any(D):
                raise EditError('offset %s snaps to zero with a %s m step: nothing to edit' % (req, S))
            if max(abs(x) for x in D) > MAX_MOVE:
                raise EditError('snapped offset %s refused: at most %.0f m per axis per edit' % ([str(x) for x in D], MAX_MOVE))
            snapped = {'step_m': str(S), 'requested': req, 'snapped': [str(x.normalize()) if x else '0' for x in D]}
        X = self._selection(groups)
        lines, vlines, F, use_in, use_out, faces = X['lines'], X['vlines'], X['F'], X['use_in'], X['use_out'], X['faces']
        bnd = use_in & use_out
        if mode == 'connected' and bnd and preview_key != self._preview_key(X['sel'], mode):
            raise EditError('NEEDS PREVIEW: connected mode stretches %d neighbour face(s); preview this selection in connected mode '
                            'first (the preview highlights them) and apply with its preview_key' % len(X['nb']))
        dup = sorted(bnd) if mode == 'isolate' else []
        inplace = use_in - set(dup)
        if dup and min(F) < vlines[-1]:
            raise EditError('selected faces come before the last vertex line: duplicating their shared corners would need '
                            'renumbering (unsupported OBJ layout; file kept); connected mode does not duplicate')

        def moved_tokens(vi):
            raw = lines[vlines[vi - 1]]
            toks = list(re.finditer(rb'\S+', raw))
            if len(toks) not in (4, 7):
                raise EditError('vertex line %d is not v x y z [r g b]: refused (file kept)' % (vlines[vi - 1] + 1))
            out = []
            for k in range(3):
                t = toks[1 + k].group().decode('ascii')
                if not re.match(r'^[+-]?\d+(\.\d+)?$', t):
                    raise EditError('vertex line %d: %r is not a plain decimal number: refused (file kept)' % (vlines[vi - 1] + 1, t))
                old = decimal.Decimal(t)
                q = decimal.Decimal(1).scaleb(-(len(t.split('.')[1]) if '.' in t else 0))
                if D[k] != D[k].quantize(q):
                    raise EditError('offset %s on %s is finer than the source precision of vertex %d (%s m): not exactly '
                                    'representable, refused' % (D[k], 'xyz'[k], vi, q))
                out.append(format((old + D[k]).quantize(q), 'f').encode('ascii'))
            return raw, toks, out
        new = list(lines)
        for vi in sorted(inplace):
            raw, toks, xyz = moved_tokens(vi)
            new[vlines[vi - 1]] = raw[:toks[1].start()] + b' '.join(xyz) + raw[toks[3].end():]
        remap, add = {}, []
        last = lines[vlines[-1]]
        eol = last[len(last.rstrip(b'\r\n')):] or b'\n'
        for vi in dup:
            raw, toks, xyz = moved_tokens(vi)
            add.append(b'v ' + b' '.join(xyz) + b''.join(b' ' + t.group() for t in toks[4:]) + eol)
            remap[vi] = len(vlines) + len(add)
        for li, vis in faces.items():
            raw = new[li]
            for t, vi in sorted(vis, key=lambda z: -z[0].start()):
                if vi in remap:
                    rest = t.group().split(b'/', 1)
                    raw = raw[:t.start()] + str(remap[vi]).encode('ascii') + (b'/' + rest[1] if len(rest) > 1 else b'') + raw[t.end():]
            new[li] = raw
        allowed = set(F) | {vlines[vi - 1] for vi in inplace}
        if any(new[i] != lines[i] for i in range(len(lines)) if i not in allowed):
            raise EditError('internal: the edit touched a line outside the selection; not applied')
        new[vlines[-1] + 1:vlines[-1] + 1] = add
        after = b''.join(new)
        stretch = self._check_stretch(X, D) if mode == 'connected' else None
        exact = self._check_translation(after, set(X['sel']), D, use_in if mode == 'connected' else set())
        clip = self._clip_check(self.obj_cur, after, X, mode)  # v0.19: refuses any face trackbuild would clip (more)
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(after)                      # kit trackbuild on the edited OBJ: refuses -> EditError
        foot = dict(faces)
        if mode == 'connected':
            foot.update({li: X['others'][li] for li in X['nb']})
        adjust = self._needs_adjustment(lines, vlines, foot, [float(x) for x in D],
                                        sorted({X['groups'][g]['mat'] for g in X['sel']}), use_in if mode == 'connected' else None)
        mats = sorted({X['groups'][g]['mat'] for g in X['sel']})
        label = 'move %d group(s) (%s, %d face(s), %s) by [%s]' % (len(X['sel']), '/'.join(mats), len(F), mode,
                                                                    ', '.join(str(x.normalize()) if x else '0' for x in D))
        self._push('obj', label, after, kind='translate', index=X['sel'][0] if len(X['sel']) == 1 else X['sel'])
        if base is None:                                    # the source did not regenerate before the edit: no comparison
            base = {'streamed_sha256': None, 'units': [None] * len(regen['units'])}
        changed = [k for k in range(len(regen['units'])) if regen['units'][k] != base['units'][k]]
        ng = sorted({X['gof'][li] for li in X['nb']})
        warn = []
        if mode == 'isolate' and dup:
            warn.append('%d boundary corner(s) duplicated: gaps / steps now open between the selection and %d neighbour face(s) '
                        'in %d group(s) (no welding / gap filling)' % (len(dup), len(X['nb']), len(ng)))
        if stretch and stretch['faces']:
            warn.append('%d neighbour face(s) in %d group(s) stretched: their uv and normal references are kept (texture '
                        'stretches; lighting normals are not recomputed); max quad non-planarity %.4f m' % (
                            stretch['faces'], len(ng), stretch['max_nonplanar_m']))
        if clip['pre_existing']:
            warn.append('%d selected / neighbour face(s) were already partly outside the unit regions before this edit and lose '
                        'no more area (%s); highlighted' % (len(clip['pre_existing']), ', '.join(
                            'line %d: %.6f m2' % (x['line'], x['lost_m2']) for x in clip['pre_existing'][:4])))
        return {'ok': True, 'label': label, 'mode': mode, 'groups': X['sel'], 'offset': [str(x.normalize()) if x else '0' for x in D],
                'snap': snapped, 'faces': sorted(F), 'faces_moved': len(F), 'moved_in_place': len(inplace),
                'duplicated_shared_vertices': len(add), 'shared_inside_selection_kept': exact['shared_inside_selection'],
                'neighbour_faces': len(X['nb']), 'neighbour_groups': ng, 'stretched': stretch, 'warnings': warn, 'exact': exact,
                'clipping': clip,
                'regenerated': {'by': 'kit trackbuild build_units (dry run on the edited OBJ; Build regenerates the same from the '
                                      'saved source)',
                                'what': 'collision trees, unit bounds (culling prism), streamed mesh / LOD blocks, PVS (mode %s), '
                                        'LOD (mode %s)' % (regen['pvs_mode'], regen['lod_mode']),
                                'streamed_sha256': [base['streamed_sha256'], regen['streamed_sha256']],
                                'changed_units': [dict(unit=k, before=base['units'][k], after=regen['units'][k]) for k in changed]},
                'needs_adjustment': adjust,
                'not_moved': 'routes, stations, grid slots, start line, checkpoints, traffic lanes and unit regions are NOT moved '
                             'by a geometry edit'}

    def _check_stretch(self, X, D, newpos=None, winding=True):
        """connected mode: every neighbour face that uses a moved corner keeps a valid shape: area > 1e-4 m2 (trackbuild's
        degenerate-face rule), no fan triangle folds over, no triangle's winding turns against a stored normal it agreed with
        (trackbuild's V3_winding gate). Refused with the face's line otherwise."""
        lines, vlines = X['lines'], X['vlines']
        vn = [[float(t) for t in raw.split()[1:4]] for raw in lines if raw.split()[:1] == [b'vn']]
        d = [float(x) for x in D] if D is not None else [0.0, 0.0, 0.0]
        sub = lambda a, b: [a[0] - b[0], a[1] - b[1], a[2] - b[2]]  # noqa: E731
        crs = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]  # noqa: E731
        dt = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]  # noqa: E731
        worst = 0.0
        for li in X['nb']:
            vis = X['others'][li]
            P0 = [[float(x) for x in lines[vlines[vi - 1]].split()[1:4]] for _, vi in vis]
            P1 = [list(newpos[vi]) if newpos is not None and vi in newpos else
                  [p[k] + (d[k] if newpos is None and vi in X['use_in'] else 0.0) for k in range(3)] for p, (_, vi) in zip(P0, vis)]
            N = []
            for t, _vi in vis:
                parts = t.group().split(b'/')
                try:
                    N.append(vn[int(parts[2]) - 1])
                except (IndexError, ValueError):
                    N.append(None)
            where = 'neighbour face line %d (group %d)' % (li + 1, X['gof'][li])
            area = 0.0
            for i in range(1, len(P1) - 1):
                c0 = crs(sub(P0[i], P0[0]), sub(P0[i + 1], P0[0]))
                c1 = crs(sub(P1[i], P1[0]), sub(P1[i + 1], P1[0]))
                area += 0.5 * dt(c1, c1) ** 0.5
                if dt(c0, c0) > 1e-12 and dt(c0, c1) <= 0:
                    raise EditError('refused: %s would fold over (a triangle flips) in connected mode; use isolate mode or a '
                                    'smaller offset / transform. Nothing changed' % where)
                for n in (N if winding else []):
                    if n is not None and dt(c0, n) > 0 and dt(c1, n) <= 0:
                        raise EditError('refused: %s would turn against its stored normal (trackbuild V3_winding) in connected '
                                        'mode. Nothing changed' % where)
            if area <= 1e-4:
                raise EditError('refused: %s would collapse (area %.6f m2; trackbuild refuses degenerate faces). Nothing changed'
                                % (where, area))
            if len(P1) == 4:
                nrm = crs(sub(P1[1], P1[0]), sub(P1[2], P1[0]))
                L = dt(nrm, nrm) ** 0.5
                if L > 0:
                    worst = max(worst, abs(dt(sub(P1[3], P1[0]), nrm)) / L)
        return {'faces': len(X['nb']), 'max_nonplanar_m': round(worst, 4),
                'checked': 'area, fold-over' + (', winding vs stored normal' if winding else ' (normals recomputed)')}

    # ---------------- v0.20 selection transforms: yaw rotation + positive uniform scale about a pivot
    def _angle(self, angle, step):
        if not isinstance(angle, (int, float)) or isinstance(angle, bool) or not math.isfinite(angle) or abs(angle) > 360:
            raise EditError('angle %r refused: degrees, -360..360 (positive = counter-clockwise seen from above)' % (angle,))
        A = decimal.Decimal(repr(float(angle)))
        snapped = None
        if step is not None:
            if not isinstance(step, (int, float)) or isinstance(step, bool) or not math.isfinite(step) or not 0 < step <= 180:
                raise EditError('angle snap %r refused: a step in degrees, 0 < step <= 180 (or none)' % (step,))
            S = decimal.Decimal(repr(float(step)))
            A2 = (A / S).to_integral_value(decimal.ROUND_HALF_UP) * S
            snapped = {'step_deg': _dstr(S), 'requested': _dstr(A), 'snapped': _dstr(A2)}
            A = A2
        return A, snapped

    def _pivot(self, pivot, P):
        """'bbox' -> the centre of the selection's bounding box (exact decimal, from its corners), or [x, y, z] metres"""
        if pivot == 'bbox':
            return [(min(q[k] for q in P) + max(q[k] for q in P)) / 2 for k in range(3)], 'bbox'
        if not (isinstance(pivot, (list, tuple)) and len(pivot) == 3 and
                all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and abs(x) <= PIVOT_MAX
                    for x in pivot)):
            raise EditError('pivot %r refused: "bbox" (the selection\'s bounding-box centre) or [x, y, z] metres (|x| <= %.0f)'
                            % (pivot, PIVOT_MAX))
        return [decimal.Decimal(repr(float(x))) for x in pivot], 'xyz'

    def transform_groups(self, groups, angle=0, scale=1, pivot='bbox', mode='isolate', angle_snap=None, preview_key=None):
        """v0.20: turn the selected face groups about the vertical axis by `angle` degrees (positive = counter-clockwise seen
        from above: +x turns towards -z) and / or scale them uniformly by `scale` (> 0) about a pivot: 'bbox' (the centre of the
        selection's bounding box) or [x, y, z] metres:  p' = pivot + scale * Ry(angle) (p - pivot), every coordinate rounded to
        its own token precision (error <= half a unit of its last decimal). Boundary modes, the connected-mode preview, the clip
        check, the kit's regeneration and undo are those of translate_groups. Normals: the selected faces' stored normals turn
        with the yaw (a positive uniform scale keeps their direction); in keep-connected mode each stretched neighbour face's
        stored normals are turned by the rotation that takes its old face plane to its new one. A changed normal points to an
        existing identical `vn` line or a new one after the last `vn` line; unsupported layouts / degenerate faces are refused.
        Texture coordinates (vt refs), vertex colours and every other line stay byte for byte."""
        if mode not in GEOM_MODES:
            raise EditError('boundary mode %r refused: %s' % (mode, ' or '.join(GEOM_MODES)))
        A, snapped = self._angle(angle, angle_snap)
        if not isinstance(scale, (int, float)) or isinstance(scale, bool) or not math.isfinite(scale) or scale <= 0:
            raise EditError('scale %r refused: positive uniform scaling only (a factor > 0; mirroring, flattening and per-axis '
                            'scaling are not supported)' % (scale,))
        if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
            raise EditError('scale %r refused: %g .. %g per edit' % (scale, SCALE_RANGE[0], SCALE_RANGE[1]))
        K = decimal.Decimal(repr(float(scale)))
        turn = A % 360 != 0
        if not turn and K == 1:
            raise EditError('the transform is the identity (angle %s, scale 1): nothing to edit' % _dstr(A))
        c, sn = _yaw_cs(A) if turn else (decimal.Decimal(1), decimal.Decimal(0))
        X = self._selection(groups)
        lines, vlines, F, use_in, use_out, faces = X['lines'], X['vlines'], X['F'], X['use_in'], X['use_out'], X['faces']
        bnd = use_in & use_out
        if mode == 'connected' and bnd and preview_key != self._preview_key(X['sel'], mode):
            raise EditError('NEEDS PREVIEW: connected mode stretches %d neighbour face(s); preview this selection in connected mode '
                            'first (the preview highlights them) and apply with its preview_key' % len(X['nb']))
        dup = sorted(bnd) if mode == 'isolate' else []
        inplace = use_in - set(dup)
        if dup and min(F) < vlines[-1]:
            raise EditError('selected faces come before the last vertex line: duplicating their shared corners would need '
                            'renumbering (unsupported OBJ layout; file kept); connected mode does not duplicate')
        V = {}
        for vi in use_in:
            raw = lines[vlines[vi - 1]]
            toks = list(re.finditer(rb'\S+', raw))
            if len(toks) not in (4, 7):
                raise EditError('vertex line %d is not v x y z [r g b]: refused (file kept)' % (vlines[vi - 1] + 1))
            xyz, _d = _dec_tokens(raw, 3, 'vertex', vlines[vi - 1])
            dec = [len(t.group().split(b'.')[1]) if b'.' in t.group() else 0 for t in toks[1:4]]
            V[vi] = (raw, toks, xyz, dec)
        P, pmode = self._pivot(pivot, [V[vi][2] for vi in use_in])
        NP, err, far = {}, 0.0, 0.0
        for vi, (raw, toks, xyz, dec) in V.items():
            ex = _xf(xyz, P, c, sn, K)
            q = [decimal.Decimal(_fmt(ex[k], dec[k])) for k in range(3)]
            err = max(err, max(abs(float(q[k] - ex[k])) for k in range(3)))
            far = max(far, max(abs(float(q[k] - xyz[k])) for k in range(3)))
            NP[vi] = q
        if far > MAX_MOVE:
            raise EditError('transform refused: a corner would move %.2f m (at most %.0f m per axis per edit; use a pivot nearer '
                            'the selection or a smaller angle / scale)' % (far, MAX_MOVE))
        newf = {vi: [float(x) for x in q] for vi, q in NP.items()}
        # ---- normals
        nlines = [li for li, r in enumerate(lines) if r.split(b'#', 1)[0].split()[:1] == [b'vn']]
        VN = {}

        def vn(ni):
            if ni not in VN:
                if not 0 < ni <= len(nlines):
                    raise EditError('normal index %d outside 1..%d: refused (file kept)' % (ni, len(nlines)))
                VN[ni] = _dec_tokens(lines[nlines[ni - 1]], 3, 'vn', nlines[ni - 1])
            return VN[ni]
        known = {}
        for i in range(len(nlines)):
            try:
                known.setdefault(tuple(_dec_tokens(lines[nlines[i]], 3, 'vn', nlines[i])[0]), i + 1)
            except EditError:
                pass
        addn, made = [], {}
        last_n = lines[nlines[-1]] if nlines else b''
        eol_n = last_n[len(last_n.rstrip(b'\r\n')):] or b'\n'

        def ref_for(vals, d):
            txt = [_fmt(decimal.Decimal(repr(x)), d) for x in vals]
            key = tuple(decimal.Decimal(t) for t in txt)
            if key in known:
                return known[key]
            if key not in made:
                addn.append(('vn ' + ' '.join(txt)).encode('ascii') + eol_n)
                made[key] = len(nlines) + len(addn)
            return made[key]
        fl_all = sorted(li for x in X['groups'] for li in x['faces'])
        nref, stretched_n, rot_n = {}, 0, 0                       # (face line, corner) -> new vn index
        cf, sf = float(c), float(sn)
        for li, vis in faces.items():
            if not turn:
                break
            for j, (t, _vi) in enumerate(vis):
                ni = int(t.group().split(b'/')[2])
                m, d = vn(ni)
                m = [float(x) for x in m]
                r = _unit([cf * m[0] + sf * m[2], m[1], cf * m[2] - sf * m[0]])
                if r is None:
                    raise EditError('face line %d: stored normal %d is zero: cannot rotate it; refused (file kept)' % (li + 1, ni))
                if tuple(VN[ni][0]) != tuple(decimal.Decimal(x) for x in _vn_text(r, d)):
                    nref[(li, j)] = ref_for(r, d)
                    rot_n += 1
        stretch = None
        if mode == 'connected' and X['nb']:
            stretch = self._check_stretch(X, None, newpos=newf, winding=False)
            for li in X['nb']:
                vis = X['others'][li]
                P0 = [[float(x) for x in lines[vlines[vi - 1]].split()[1:4]] for _, vi in vis]
                P1 = [newf.get(vi, P0[j]) for j, (_, vi) in enumerate(vis)]
                n0, n1 = _unit(_newell(P0)), _unit(_newell(P1))
                if n0 is None or n1 is None:
                    raise EditError('refused: neighbour face line %d (group %d) has no face plane (zero area) %s, so its stored '
                                    'normals cannot be recomputed for the stretch; use isolate mode. Nothing changed' % (
                                        li + 1, X['gof'][li], 'before' if n0 is None else 'after'))
                if sum(a * b for a, b in zip(n0, n1)) <= 1e-6:
                    raise EditError('refused: neighbour face line %d (group %d) would turn over (its face plane turns by 90 '
                                    'degrees or more), so its normals cannot be recomputed; use isolate mode or a smaller '
                                    'transform. Nothing changed' % (li + 1, X['gof'][li]))
                for j, (t, _vi) in enumerate(vis):
                    ni = int(t.group().split(b'/')[2])
                    m, d = vn(ni)
                    r = _unit(_turn(n0, n1, [float(x) for x in m]))
                    if r is None:
                        raise EditError('neighbour face line %d: stored normal %d is zero: cannot recompute it; refused '
                                        '(file kept)' % (li + 1, ni))
                    if tuple(VN[ni][0]) != tuple(decimal.Decimal(x) for x in _vn_text(r, d)):
                        nref[(li, j)] = ref_for(r, d)
                        stretched_n += 1
        if addn and (not nlines or fl_all[0] < nlines[-1]):
            raise EditError('refused: the changed normals need new vn lines after the last one, but faces come before it '
                            '(unsupported OBJ layout; renumbering is not supported). Nothing changed')
        # ---- rewrite: in-place corners, duplicated boundary corners, face refs
        new = list(lines)
        for vi in sorted(inplace):
            raw, toks, _xyz, dec = V[vi]
            new[vlines[vi - 1]] = (raw[:toks[1].start()] + b' '.join(_fmt(NP[vi][k], dec[k]).encode('ascii') for k in range(3)) +
                                   raw[toks[3].end():])
        remap, addv = {}, []
        last = lines[vlines[-1]]
        eol = last[len(last.rstrip(b'\r\n')):] or b'\n'
        for vi in dup:
            raw, toks, _xyz, dec = V[vi]
            addv.append(b'v ' + b' '.join(_fmt(NP[vi][k], dec[k]).encode('ascii') for k in range(3)) +
                        b''.join(b' ' + t.group() for t in toks[4:]) + eol)
            remap[vi] = len(vlines) + len(addv)
        touched = set(F) | ({li for li in X['nb']} if mode == 'connected' else set())
        for li in touched:
            vis = faces[li] if li in faces else X['others'][li]
            r = new[li]
            for j in sorted(range(len(vis)), key=lambda j: -vis[j][0].start()):
                t, vi = vis[j]
                parts = t.group().split(b'/')
                if li in faces and vi in remap:
                    parts[0] = str(remap[vi]).encode('ascii')
                if (li, j) in nref:
                    parts[2] = str(nref[(li, j)]).encode('ascii')
                r = r[:t.start()] + b'/'.join(parts) + r[t.end():]
            new[li] = r
        allowed = touched | {vlines[vi - 1] for vi in inplace}
        if any(new[i] != lines[i] for i in range(len(lines)) if i not in allowed):
            raise EditError('internal: the edit touched a line outside the selection; not applied')
        for at, block in sorted([(vlines[-1] + 1, addv), ((nlines[-1] + 1) if nlines else 0, addn)], key=lambda z: -z[0]):
            new[at:at] = block
        after = b''.join(new)
        # ---- trackbuild's triangle rule on every changed face (slivers / winding against the first corner's normal are dropped)
        self._check_kept_triangles(X, mode, newf, nref, vn, ref_vals=lambda k: (_vn_value(addn, nlines, k, lines)))
        exact = self._check_transform(after, X, mode, P, c, sn, K)
        clip = self._clip_check(self.obj_cur, after, X, mode)
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(after)
        foot = dict(faces)
        if mode == 'connected':
            foot.update({li: X['others'][li] for li in X['nb']})
        mats = sorted({X['groups'][g]['mat'] for g in X['sel']})
        adjust = self._needs_adjustment(lines, vlines, foot, None, mats, None, newpos=newf)
        Ps = [_fmt(x, 4) for x in P]
        what = ' + '.join((['turn %s deg' % _dstr(A)] if turn else []) + (['scale %s' % _dstr(K)] if K != 1 else []))
        label = '%s about [%s] (%s) %d group(s) (%s, %d face(s), %s)' % (
            what, ', '.join(Ps), 'bbox centre' if pmode == 'bbox' else 'entered pivot', len(X['sel']), '/'.join(mats), len(F), mode)
        self._push('obj', label, after, kind='transform', index=X['sel'][0] if len(X['sel']) == 1 else X['sel'])
        if base is None:
            base = {'streamed_sha256': None, 'units': [None] * len(regen['units'])}
        changed = [k for k in range(len(regen['units'])) if regen['units'][k] != base['units'][k]]
        ng = sorted({X['gof'][li] for li in X['nb']})
        warn = []
        if mode == 'isolate' and dup:
            warn.append('%d boundary corner(s) duplicated: gaps / steps now open between the selection and %d neighbour face(s) '
                        'in %d group(s) (no welding / gap filling)' % (len(dup), len(X['nb']), len(ng)))
        if stretch and stretch['faces']:
            warn.append('%d neighbour face(s) in %d group(s) stretched: their uv references are kept (texture stretches); %d '
                        'stored normal reference(s) recomputed (turned with the face plane); max quad non-planarity %.4f m' % (
                            stretch['faces'], len(ng), stretched_n, stretch['max_nonplanar_m']))
        if K != 1:
            warn.append('uv coordinates are kept: the texture scales with the faces (x%s)' % _dstr(K))
        if clip['pre_existing']:
            warn.append('%d selected / neighbour face(s) were already partly outside the unit regions before this edit and lose '
                        'no more area (%s); highlighted' % (len(clip['pre_existing']), ', '.join(
                            'line %d: %.6f m2' % (x['line'], x['lost_m2']) for x in clip['pre_existing'][:4])))
        return {'ok': True, 'label': label, 'op': 'transform', 'mode': mode, 'groups': X['sel'],
                'transform': {'angle_deg': _dstr(A), 'angle_snap': snapped, 'scale': _dstr(K),
                              'pivot': [_dstr(x) for x in P], 'pivot_mode': pmode,
                              'formula': "p' = pivot + scale * Ry(angle) (p - pivot); positive angle = counter-clockwise seen "
                                         "from above (+x towards -z)"},
                'precision': {'max_position_error_m': round(err, 9), 'bound_m': 'half a unit of each coordinate\'s last source '
                                                                                 'decimal (0.00005 m for 4 decimals)'},
                'normals': {'selected_turned': rot_n, 'stretched_recomputed': stretched_n, 'vn_lines_added': len(addn)},
                'faces': sorted(F), 'faces_moved': len(F), 'moved_in_place': len(inplace), 'duplicated_shared_vertices': len(addv),
                'shared_inside_selection_kept': exact['shared_inside_selection'], 'neighbour_faces': len(X['nb']),
                'neighbour_groups': ng, 'stretched': stretch, 'warnings': warn, 'exact': exact, 'clipping': clip,
                'regenerated': {'by': 'kit trackbuild build_units (dry run on the edited OBJ; Build regenerates the same from the '
                                      'saved source)',
                                'what': 'collision trees, unit bounds (culling prism), streamed mesh / LOD blocks, PVS (mode %s), '
                                        'LOD (mode %s)' % (regen['pvs_mode'], regen['lod_mode']),
                                'streamed_sha256': [base['streamed_sha256'], regen['streamed_sha256']],
                                'changed_units': [dict(unit=k, before=base['units'][k], after=regen['units'][k]) for k in changed]},
                'needs_adjustment': adjust,
                'not_moved': 'routes, stations, grid slots, start line, checkpoints, traffic lanes and unit regions are NOT moved '
                             'by a geometry edit'}

    def _check_kept_triangles(self, X, mode, newf, nref, vn, ref_vals):
        """every fan triangle of a changed face that trackbuild keeps today (blocks: |cross|^2 > 1e-4 and cross . first-corner
        normal > 0) must stay kept after the transform; otherwise the build would silently drop it"""
        lines, vlines = X['lines'], X['vlines']
        todo = [(li, X['faces'][li], 'selected') for li in X['F']]
        if mode == 'connected':
            todo += [(li, X['others'][li], 'neighbour') for li in X['nb']]
        for li, vis, role in sorted(todo):
            P0 = [[float(x) for x in lines[vlines[vi - 1]].split()[1:4]] for _, vi in vis]
            P1 = [newf.get(vi, P0[j]) for j, (_, vi) in enumerate(vis)]
            n0i = int(vis[0][0].group().split(b'/')[2])
            n0 = [float(x) for x in vn(n0i)[0]]
            n1 = ref_vals(nref[(li, 0)]) if (li, 0) in nref else n0
            g0, g1 = _fan_good(P0, n0), _fan_good(P1, n1)
            for i, (a, b) in enumerate(zip(g0, g1)):
                if a and not b:
                    raise EditError('refused: trackbuild would drop triangle %d of %s face line %d (group %d): it would become a '
                                    'sliver (under 0.005 m2) or wind against its stored normal, and Build drops such triangles '
                                    'silently. Use a larger scale / different transform. Nothing changed' % (
                                        i + 1, role, li + 1, X['gof'][li]))

    def _check_transform(self, after, X, mode, P, c, sn, K):
        """independent re-read of both buffers: every selected corner (and, connected, every stretched neighbour's moved
        corner) is within half a unit of its last decimal of p' = P + K Ry (p - P) (float recomputation); every other corner,
        vt reference and vertex colour unchanged; corners shared inside the selection still shared; the selected faces' normals
        = their old normals turned by the yaw (within the vn precision); unchanged faces keep their vn references"""
        def table(b):
            lines, groups, vlines = obj_index(b)
            V = [lines[li].split()[1:] for li in vlines]
            NV = [r.split()[1:4] for r in lines if r.split(b'#', 1)[0].split()[:1] == [b'vn']]
            out = []
            for x in groups:
                for li in x['faces']:
                    out.append((x['i'], [(int(t.split(b'/')[0]), V[int(t.split(b'/')[0]) - 1], t.split(b'/')[1],
                                          NV[int(t.split(b'/')[2]) - 1], int(t.split(b'/')[2])) for t in lines[li].split()[1:]]))
            return out
        t0, t1 = table(self.obj_cur), table(after)
        if len(t0) != len(t1):
            raise EditError('internal: the edit changed the face count; not applied')
        sel = set(X['sel'])
        Pf, cf, sf, kf = [float(x) for x in P], float(c), float(sn), float(K)
        moved = stretched = same = 0
        perr = nerr = 0.0
        pairs = collections.defaultdict(set)
        for (g0, f0), (g1, f1) in zip(t0, t1):
            if g0 != g1 or len(f0) != len(f1):
                raise EditError('internal: face of group %d changed shape / group; not applied' % g0)
            nb = mode == 'connected' and g0 not in sel and any(i in X['use_in'] for i, *_ in f0)
            for (i0, v0, vt0, n0, r0), (i1, v1, vt1, n1, r1) in zip(f0, f1):
                if vt0 != vt1 or v0[3:] != v1[3:]:
                    raise EditError('internal: a uv reference / vertex colour changed; not applied')
                mv = g0 in sel or (nb and i0 in X['use_in'])
                if not mv:
                    if v1[:3] != v0[:3] or (not nb and (i1 != i0 or r1 != r0)):
                        raise EditError('internal: a face of group %d outside the transform changed; not applied' % g0)
                    same += 0 if nb else 1
                    continue
                p = [float(x) - Pf[k] for k, x in enumerate(v0[:3])]
                want = [Pf[0] + kf * (cf * p[0] + sf * p[2]), Pf[1] + kf * p[1], Pf[2] + kf * (cf * p[2] - sf * p[0])]
                for k in range(3):
                    tok = v1[k].decode()
                    half = 0.5 * 10 ** -(len(tok.split('.')[1]) if '.' in tok else 0)
                    e = abs(float(tok) - want[k])
                    if e > half + 1e-9:
                        raise EditError('internal: a transformed corner is %.6f m off (bound %.6f); not applied' % (e, half))
                    perr = max(perr, e)
                if g0 in sel:
                    moved += 1
                    pairs[i0].add(i1)
                    m = [float(x) for x in n0]
                    w = _unit([cf * m[0] + sf * m[2], m[1], cf * m[2] - sf * m[0]])
                    got = [float(x) for x in n1]
                    q = 10 ** -min(len(x.decode().split('.')[1]) if b'.' in x else 0 for x in n1)
                    e = max(abs(a - b) for a, b in zip(w, got))
                    if e > q:
                        raise EditError('internal: a selected face normal is not its old normal turned by the yaw (%.6f); not '
                                        'applied' % e)
                    nerr = max(nerr, e)
                else:
                    stretched += 1
            if nb:                                          # stretched neighbour: normals turned with the face plane
                A0 = _unit(_newell([[float(x) for x in v[:3]] for _i, v, *_ in f0]))
                A1 = _unit(_newell([[float(x) for x in v[:3]] for _i, v, *_ in f1]))
                for (_i0, _v0, _t0, n0, _r0), (_i1, _v1, _t1, n1, _r1) in zip(f0, f1):
                    w = _unit(_turn(A0, A1, [float(x) for x in n0]))
                    q = 10 ** -min(len(x.decode().split('.')[1]) if b'.' in x else 0 for x in n1)
                    e = max(abs(a - float(b)) for a, b in zip(w, n1))
                    if e > q:
                        raise EditError('internal: a stretched neighbour normal is not recomputed (%.6f); not applied' % e)
                    nerr = max(nerr, e)
        if any(len(v) != 1 for v in pairs.values()):
            raise EditError('internal: a corner shared inside the selection was split; not applied')
        cnt = collections.Counter(i for g, f in t0 if g in sel for i, *_ in f)
        return {'face_corners_transformed': moved, 'neighbour_corners_transformed': stretched,
                'other_face_corners_unchanged': same, 'uv_refs_and_colours_unchanged': True,
                'max_position_error_m': round(perr, 9), 'max_normal_error': round(nerr, 9),
                'shared_inside_selection': sum(1 for v in cnt.values() if v > 1)}

    def _delta(self, delta):
        if not (isinstance(delta, (list, tuple)) and len(delta) == 3 and
                all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in delta)):
            raise EditError('offset must be [dx, dy, dz] numbers in metres')
        delta = [float(x) for x in delta]
        if not all(math.isfinite(x) for x in delta) or max(abs(x) for x in delta) > MAX_MOVE:
            raise EditError('offset %r refused: finite, at most %.0f m per axis per edit' % (delta, MAX_MOVE))
        if not any(delta):
            raise EditError('offset is zero: nothing to edit')
        return delta

    @staticmethod
    def _face_use(lines, groups, vlines, F):
        use_in, use_out, faces, others = set(), set(), {}, {}
        for x in groups:
            for li in x['faces']:
                vis = []
                for t in list(re.finditer(rb'\S+', lines[li]))[1:]:
                    try:
                        vi = int(t.group().split(b'/')[0])
                    except ValueError:
                        raise EditError('line %d: face token %r is not v/vt/vn: refused (file kept)' % (li + 1, t.group()))
                    if not 0 < vi <= len(vlines):
                        raise EditError('line %d: vertex index %d outside 1..%d: refused (file kept)' % (li + 1, vi, len(vlines)))
                    vis.append((t, vi))
                if li in F:
                    faces[li] = vis
                    use_in.update(v for _, v in vis)
                else:
                    others[li] = vis
                    use_out.update(v for _, v in vis)
        return use_in, use_out, faces, others

    def _check_translation(self, after, sel, D, moved_shared):
        """independent re-read of both buffers: the selected faces' corners moved by exactly D (decimal); in connected mode the
        unselected faces' corners that are moved corners also moved by D, all their other corners unchanged; vt / vn refs
        unchanged; corners shared inside the selection still shared"""
        def corners(b):
            lines, groups, vlines = obj_index(b)
            V = [[decimal.Decimal(x.decode()) for x in lines[li].split()[1:4]] for li in vlines]
            out = []
            for x in groups:
                for li in x['faces']:
                    out.append((x['i'], [(int(t.split(b'/')[0]), V[int(t.split(b'/')[0]) - 1], t.split(b'/', 1)[1:])
                                         for t in lines[li].split()[1:]]))
            return out, lines, vlines
        c0, l0, v0 = corners(self.obj_cur)
        c1, l1, v1 = corners(after)
        if len(c0) != len(c1) or len(l1) != len(l0) + len(v1) - len(v0):
            raise EditError('internal: the edit changed the face / line count; not applied')
        moved = stretched = same = 0
        pairs = collections.defaultdict(set)
        for (g0, f0), (g1, f1) in zip(c0, c1):
            for (i0, p0, r0), (i1, p1, r1) in zip(f0, f1):
                mv = g0 in sel or i0 in moved_shared
                want = [p0[k] + D[k] for k in range(3)] if mv else p0
                if g0 != g1 or r0 != r1 or p1 != want:
                    raise EditError('internal: a face of group %d is not where expected after the move; not applied' % g0)
                if g0 in sel:
                    moved += 1
                    pairs[i0].add(i1)
                elif mv:
                    stretched += 1
                else:
                    same += 1
        if any(len(v) != 1 for v in pairs.values()):
            raise EditError('internal: a corner shared inside the selection was split; not applied')
        cnt = collections.Counter(i for g, f in c0 if g in sel for i, _p, _r in f)
        return {'face_corners_moved_exactly': moved, 'neighbour_corners_moved_exactly': stretched,
                'other_face_corners_unchanged': same, 'uv_normal_refs_unchanged': True,
                'shared_inside_selection': sum(1 for c in cnt.values() if c > 1)}

    def coverage(self, obj_bytes, desc_bytes=None):
        """v0.19: every face of OBJ bytes through the kit's own unit regions and clip (trackbuild.units make_units / clip, the
        functions build_units uses): per face its points, area, area inside the union of the unit regions (what Build keeps;
        overlapping regions counted once) and its piece in each unit. v0.23: desc_bytes = a candidate description (default: the
        current buffer)"""
        db = self.cur if desc_bytes is None else desc_bytes
        key = hashlib.sha256(obj_bytes + b'\0' + db).hexdigest()
        cache = self.__dict__.setdefault('_cover', {})
        if key in cache:
            return cache[key]
        K = kit_trackbuild(self.cfg)
        UN = K['units']
        d = json.loads(db.decode('utf-8'))
        root = os.path.join(self.cfg['state'], 'geomcheck')
        os.makedirs(root, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='clip_', dir=root)
        try:
            p = os.path.join(tmp, 'edited.obj')
            with open(p, 'wb') as f:
                f.write(obj_bytes)
            try:
                obj = K['io'].read_obj(p)
                units = UN.make_units(d)
            except K['io'].SourceError as e:
                raise EditError('refused: trackbuild cannot read the edited geometry / unit regions (%s). Nothing changed' % e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        faces = []
        for mat, fv in obj['faces']:
            pieces = {}
            for u in units:
                q = _clip_lanes(UN, fv, u.lanes)
                if q:
                    pieces[u.k] = q
            faces.append({'mat': mat, 'pts': [v[0] for v in fv], 'area': _poly_area([v[0] for v in fv]),
                          'kept': _union_area(UN, units, fv, sorted(pieces)) if pieces else 0.0, 'pieces': pieces})
        r = {'faces': faces, 'units': units, 'coll_margin': UN.assign.__defaults__[-1]}
        if len(cache) > 8:
            cache.clear()
        cache[key] = r
        return r

    def _clip_check(self, before, after, X, mode):
        """v0.19: trackbuild clips every render face to the unit regions and silently drops what lies outside all of them; a
        collision face is kept only by units whose region grown by coll_margin holds one of its corners. Every face of the edited
        OBJ is compared with the same clip of the unedited OBJ: a selected / stretched face that would lose area, or a moved
        collision face no unit would hold, refuses the edit with the faces, the unit boundaries they cross and the intended
        corners (viewer highlight). Unit regions are never expanded. Faces clipped already before the edit by at least as much
        are reported (warning + highlight), not refused."""
        c0, c1 = self.coverage(before), self.coverage(after)
        units = c1['units']
        fl = sorted(li for x in X['groups'] for li in x['faces'])
        if not len(fl) == len(c0['faces']) == len(c1['faces']):
            raise EditError('internal: the OBJ index and trackbuild read_obj disagree on the face count; not applied')
        nbs = set(X['nb'])
        desc = self.desc()
        lat = [u.get('lateral') for u in desc['units']]
        bad, pre, changed, split, lost = [], [], 0, 0, 0.0
        for i, (a, b) in enumerate(zip(c0['faces'], c1['faces'])):
            li = fl[i]
            role = 'selected' if li in X['F'] else 'neighbour' if li in nbs else None
            moved = a['pts'] != b['pts']
            if moved and (role is None or (role == 'neighbour' and mode != 'connected')):
                raise EditError('internal: face line %d changed outside the selection / its stretched neighbours; not applied'
                                % (li + 1))
            if role is None:
                continue
            changed += moved
            split += len(b['pieces']) > 1
            l0, l1 = max(0.0, a['area'] - a['kept']), max(0.0, b['area'] - b['kept'])
            tol = CLIP_TOL_M2 + 1e-9 * b['area']
            if l1 - l0 > tol:
                lost += l1 - l0
                bad.append(self._clip_info(li, X, role, b, l0, l1, units, lat, 'render'))
            elif l1 > tol:
                pre.append(self._clip_info(li, X, role, b, l0, l1, units, lat, 'pre-existing'))
            m = desc['materials'].get(b['mat']) or {}
            if moved and m.get('collide') and not any(u.inside(q[0], q[2], c1['coll_margin']) for u in units for q in b['pts']):
                bad.append(self._clip_info(li, X, role, b, l0, l1, units, lat, 'collision', c1['coll_margin']))
        rep = {'checked_faces': len(fl), 'selected_faces': len(X['F']), 'neighbour_faces': len(nbs), 'changed_faces': changed,
               'split_across_units': split, 'lost_m2': round(lost, 6), 'pre_existing': pre,
               'by': 'kit trackbuild.units make_units / clip on every face before and after the edit (area inside the union of '
                     'the unit regions); cross-checked against build_units\' own unit pieces'}
        if bad:
            def say(x):
                if x['kind'] == 'collision':
                    return 'collision face line %d (group %d, %s) would lie more than %.0f m outside every unit region' % (
                        x['line'], x['group'], x['role'], x['margin_m'])
                if not x['units']:
                    return 'face line %d (group %d, %s, %s) would lie wholly outside every unit region (%.4f m2)' % (
                        x['line'], x['group'], x['role'], x['material'], x['area_m2'])
                return 'face line %d (group %d, %s, %s) loses %.4f of %.4f m2 at %s' % (
                    x['line'], x['group'], x['role'], x['material'], x['lost_m2'], x['area_m2'],
                    ', '.join('unit %d %s' % (e['unit'], e['edge']) for e in x['boundaries'][:2]) or 'a unit boundary')
            e = EditError('refused: trackbuild would clip %d face(s) of this move at the unit regions (%.4f m2 of geometry lost; '
                          'Build keeps only what lies inside a unit region): %s%s. Unit regions are authored source data and '
                          'are never expanded automatically: use a smaller or different offset, or change the unit regions '
                          'first. Nothing changed' % (len(bad), lost, '; '.join(say(x) for x in bad[:4]),
                                                      ' (+%d more)' % (len(bad) - 4) if len(bad) > 4 else ''))
            rep.update(refused=True, faces=bad)
            e.detail = {'clipping': rep}
            raise e
        rep.update(refused=False, faces=pre)
        return rep

    @staticmethod
    def _clip_info(li, X, role, f, l0, l1, units, lat, kind, margin=None):
        """one clipped face for the report / viewer: line, group, role, areas, intended corners, units it reaches and the unit
        boundaries (region edges) its outside corners cross, as segments at the face's height"""
        pts = f['pts']
        y = sum(q[1] for q in pts) / len(pts)
        cx, cz = sum(q[0] for q in pts) / len(pts), sum(q[2] for q in pts) / len(pts)
        out = [q for q in pts if not any(u.inside(q[0], q[2], 1e-6) for u in units)] or pts
        near = sorted(f['pieces']) or [min(range(len(units)), key=lambda k: max(b - a * cx - c * cz for a, c, b in units[k].lanes))]
        edges = []
        for k in near:
            u = units[k]
            lo, hi = lat[k] or (None, None)
            names = ['start cut (station %d)' % u.cut_from, 'lateral edge %s m' % hi, 'end cut (station %d)' % u.cut_to,
                     'lateral edge %s m' % lo]
            hit = set()
            for q in out:                                   # the edge a corner is beyond; past a region corner: the lateral one(s)
                viol = [j for j, (a, c, b) in enumerate(u.lanes) if a * q[0] + c * q[2] - b < -1e-6]
                hit.update(viol if len(viol) == 1 else [j for j in viol if j in (1, 3)] or viol)
            for j, (a, c, b) in enumerate(u.lanes):
                if j in hit:
                    ends = [cc for cc in u.corners if abs(a * cc[0] + c * cc[1] - b) < 1e-3][:2]
                    edges.append({'unit': k, 'edge': names[j], 'segment': [[ends[0][0], y, ends[0][1]], [ends[1][0], y, ends[1][1]]]
                                  if len(ends) == 2 else None})
        edges.sort(key=lambda e: 'lateral' not in e['edge'])
        r = {'kind': kind, 'line': li + 1, 'group': X['gof'][li], 'role': role, 'material': f['mat'],
             'area_m2': round(f['area'], 6), 'lost_m2': round(l1, 6), 'lost_before_m2': round(l0, 6), 'units': sorted(f['pieces']),
             'boundaries': edges, 'corners': [list(q) for q in pts]}
        if margin is not None:
            r['margin_m'] = margin
        return r

    def regenerate(self, obj_bytes, desc_bytes=None):
        """the kit's trackbuild build_units (collision, unit bounds, streaming, PVS, LOD) on OBJ bytes + the current
        description (v0.23: or the candidate desc_bytes), in a temporary folder under Workbench state -> per-unit summary read
        back from the produced blocks (+ 'capacity': per unit vertices / records / mesh and LOD bytes against their slots)"""
        db = self.cur if desc_bytes is None else desc_bytes
        key = hashlib.sha256(obj_bytes + b'\0' + db).hexdigest()
        cache = self.__dict__.setdefault('_regen', {})
        if key in cache:
            return cache[key]
        K = kit_trackbuild(self.cfg)
        d = json.loads(db.decode('utf-8'))
        root = os.path.join(self.cfg['state'], 'geomcheck')
        os.makedirs(root, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='regen_', dir=root)
        try:
            rel = str(d.get('obj', '')).replace('\\', '/')
            p = os.path.join(tmp, *rel.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(obj_bytes)
            try:
                streamed, table, units, info = K['build'].build_units(tmp, d)
            except K['io'].SourceError as e:
                raise EditError('refused: trackbuild cannot regenerate the dependent data for this geometry (%s). Nothing '
                                'changed; the unit regions / route are authored source data and are not moved by a geometry '
                                'edit' % e)
            except Exception as e:  # noqa: BLE001   any other kit failure is a refusal too, never a stale result
                raise EditError('refused: trackbuild build_units failed on the edited geometry (%s: %s). Nothing changed' %
                                (type(e).__name__, e))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        cov = self.coverage(obj_bytes, db)                  # v0.19: the clip check = build_units' own unit pieces, exactly
        for k, u in enumerate(units):
            want = [(f['mat'], f['pieces'][k]) for f in cov['faces'] if k in f['pieces']]
            if want != u.polys:
                raise EditError('internal: the clip check disagrees with trackbuild build_units in unit %d (%d / %d pieces); '
                                'not applied' % (k, len(want), len(u.polys)))
        per = []
        for k, (pos, _end, ms, ls) in enumerate(table):
            q0 = struct.unpack_from('<4f', streamed, pos + 0x10)
            per.append({'prism_y': [round(q0[1], 4), round(q0[1] + q0[3] - 0.5, 4)], 'render_polys': len(units[k].polys),
                        'collision_polys': len(units[k].coll), 'mesh_bytes': ms, 'lod_bytes': ls,
                        'blocks_sha256': hashlib.sha256(streamed[pos:pos + ms + ls]).hexdigest()[:16]})
        ms_, ls_ = K['build'].MESH_SLOT, K['build'].LOD_SLOT
        cap = [{'unit': x['unit'], 'vertices': x['vertices'], 'records': x['records'], 'mesh_bytes': x['mesh_bytes'],
                'lod_bytes': x['lod_bytes'], 'mesh_slot_pct': round(100.0 * x['mesh_bytes'] / ms_, 1),
                'lod_slot_pct': round(100.0 * x['lod_bytes'] / ls_, 1), 'vertex_pct': round(100.0 * x['vertices'] / 65536, 1),
                'record_pct': round(100.0 * x['records'] / 127, 1)} for x in info['units']]
        r = {'units': per, 'streamed_sha256': hashlib.sha256(streamed).hexdigest(), 'capacity': cap,
             'slots': {'mesh': ms_, 'lod': ls_, 'vertices': 65536, 'records': 127},
             'pvs_mode': info['pvs']['mode'], 'lod_mode': (d.get('lod') or {'mode': 'identity'})['mode']}
        if len(cache) > 8:
            cache.clear()
        cache[key] = r
        return r

    def _needs_adjustment(self, lines, vlines, faces, delta, mats, moved=None, newpos=None):
        """authored points that stand on the group's footprint (xz, before or after the move): they are NOT moved and may need
        their own adjustment (grid slots, start line, checkpoints, route stations / lane samples, traffic follows the stations)"""
        polys = []
        for li, vis in faces.items():
            P = [[float(x) for x in lines[vlines[vi - 1]].split()[1:4]] for _, vi in vis]
            polys.append(P)
            polys.append([list(newpos[vi]) if newpos is not None and vi in newpos else
                          [p[k] + (delta[k] if newpos is None and (moved is None or vi in moved) else 0.0) for k in range(3)]
                          for p, (_, vi) in zip(P, vis)])

        def on(x, z):
            for P in polys:
                for i in range(1, len(P) - 1):
                    a, b, c = P[0], P[i], P[i + 1]
                    s1 = (b[0] - a[0]) * (z - a[2]) - (b[2] - a[2]) * (x - a[0])
                    s2 = (c[0] - b[0]) * (z - b[2]) - (c[2] - b[2]) * (x - b[0])
                    s3 = (a[0] - c[0]) * (z - c[2]) - (a[2] - c[2]) * (x - c[0])
                    if (s1 >= -1e-9 and s2 >= -1e-9 and s3 >= -1e-9) or (s1 <= 1e-9 and s2 <= 1e-9 and s3 <= 1e-9):
                        return True
            return False
        d = self.desc()
        out = []
        for i, gs in enumerate(d.get('grid') or []):
            p = gs.get('pos') if isinstance(gs, dict) else None
            if isinstance(p, list) and len(p) == 3 and on(p[0], p[2]):
                out.append({'kind': 'grid', 'index': i, 'why': 'grid slot stands on the moved faces (old or new position)'})
        sl = d.get('start_line')
        if isinstance(sl, dict) and isinstance(sl.get('pos'), list) and on(sl['pos'][0], sl['pos'][2]):
            out.append({'kind': 'start_line', 'index': None, 'why': 'start line stands on the moved faces'})
        for i, c in enumerate(d.get('checkpoints') or []):
            p = c.get('pos') if isinstance(c, dict) else None
            if isinstance(p, list) and len(p) == 3 and on(p[0], p[2]):
                out.append({'kind': 'checkpoint', 'index': i, 'why': 'checkpoint stands on the moved faces'})
        st = []
        for i, s in enumerate(d.get('stations') or []):
            try:
                px, pz, tx, tz = s['p'][0], s['p'][2], s['t'][0], s['t'][1]
                pts = [(px, pz)] + [(px - tz * o, pz + tx * o) for o in s.get('offsets') or []]
            except (KeyError, IndexError, TypeError):
                continue
            if any(on(x, z) for x, z in pts):
                st.append(i)
        if st:
            m = {'collide': any(((d.get('materials') or {}).get(x) or {}).get('collide') for x in mats)}
            out.append({'kind': 'route', 'index': st, 'why': 'route stations %s (centre / lane samples) lie on the moved faces: '
                        'the route%s not moved%s' % (_ranges(st), ' and traffic lanes are' if d.get('traffic') else ' is',
                                                        '; this material is collision floor, so the Build\'s drivable-floor / '
                                                        'traffic gates (V2 / V7) check it' if m.get('collide') else '')})
        return out

    # ---------------- v0.21 boundary inspection + controlled welding (positions only: uv / normal / colour seams are kept)
    def _topo(self, b):
        """OBJ bytes -> topology by POSITION. A location = every v line with the same decimal coordinates (a colour split is two
        v lines at one location; uv / normal splits are per-corner references); an edge = two locations consecutive in a face.
        Open edge = used by one face, non-manifold = by more than two; an index-split seam = an edge of two faces that use
        different v lines (closed by position); misoriented = two faces traversing their shared edge the same way."""
        key = hashlib.sha256(b).hexdigest()
        cache = self.__dict__.setdefault('_topo_c', {})
        if key in cache:
            return cache[key]
        lines, groups, vlines = obj_index(b)
        loc, locs, index = [], [], {}
        for li in vlines:
            p, _d = _dec_tokens(lines[li], 3, 'vertex line', li)
            if len(p) != 3:
                raise EditError('vertex line %d is not v x y z [r g b]: refused (file kept)' % (li + 1))
            k = tuple(p)
            if k not in index:
                index[k] = len(locs)
                locs.append({'p': k, 'vis': []})
            locs[index[k]]['vis'].append(len(loc) + 1)
            loc.append(index[k])
        faces, gof, E, lf = {}, {}, collections.defaultdict(list), collections.defaultdict(set)
        for g in groups:
            for li in g['faces']:
                vis = []
                for t in lines[li].split()[1:]:
                    try:
                        vi = int(t.split(b'/')[0])
                    except ValueError:
                        raise EditError('line %d: face token %r is not v/vt/vn: refused (file kept)' % (li + 1, t))
                    if not 0 < vi <= len(loc):
                        raise EditError('line %d: vertex index %d outside 1..%d: refused (file kept)' % (li + 1, vi, len(loc)))
                    vis.append(vi)
                faces[li], gof[li] = vis, g['i']
                L = [loc[v - 1] for v in vis]
                for i in range(len(L)):
                    a, c = L[i], L[(i + 1) % len(L)]
                    lf[a].add(li)
                    if a != c:
                        E[frozenset((a, c))].append((li, a, c, frozenset((vis[i], vis[(i + 1) % len(L)]))))
        opened = set(e for e, u in E.items() if len(u) == 1)
        adj = collections.defaultdict(set)
        for e in opened:
            a, c = tuple(e)
            adj[a].add(c)
            adj[c].add(a)
        r = {'lines': lines, 'groups': groups, 'vlines': vlines, 'loc': loc, 'locs': locs, 'faces': faces, 'gof': gof, 'E': E,
             'open': opened, 'adj': adj, 'loc_faces': lf, 'nonmanifold': [e for e, u in E.items() if len(u) > 2],
             'split_seams': sum(1 for u in E.values() if len(u) == 2 and u[0][3] != u[1][3]),
             'misoriented': [e for e, u in E.items() if len(u) == 2 and u[0][1] == u[1][1]]}
        if len(cache) > 4:
            cache.clear()
        cache[key] = r
        return r

    @staticmethod
    def _tol(tol):
        if not isinstance(tol, (int, float)) or isinstance(tol, bool) or not math.isfinite(tol) or not 0 < tol <= WELD_TOL_MAX:
            raise EditError('weld tolerance %r refused: an explicit distance in metres, 0 < tolerance <= %s' % (tol, WELD_TOL_MAX))
        return float(tol)

    @staticmethod
    def _near(T, tol):
        """every open-edge location -> the other open-edge locations within tol metres (3-D distance), nearest first"""
        pts = {l: [float(x) for x in T['locs'][l]['p']] for l in T['adj']}
        cell = collections.defaultdict(list)
        ck = lambda p: tuple(int(math.floor(x / tol)) for x in p)  # noqa: E731
        for l, p in pts.items():
            cell[ck(p)].append(l)
        out = {}
        for l, p in pts.items():
            k, hits = ck(p), []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for m in cell.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            if m != l:
                                d = math.dist(p, pts[m])
                                if d <= tol:
                                    hits.append((d, m))
            out[l] = sorted(hits)
        return out

    def boundary(self, tol=None):
        """READ ONLY: the open edges (by position; highlighted), non-manifold / misoriented edges and index-split seams; with a
        tolerance also the gap candidates = chains of open-edge locations whose every location has exactly one other open-edge
        location within tol (mutual, not a corner of the same face), joined along open edges on both sides, and the locations
        whose match is ambiguous. Candidates are suggestions only: nothing is welded or filled automatically."""
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: boundary inspection needs a readable OBJ')
        if tol is not None:
            tol = self._tol(tol)
        T = self._topo(self.obj_cur)
        locs = T['locs']
        fp = lambda l: [float(x) for x in locs[l]['p']]  # noqa: E731
        rep = lambda l: locs[l]['vis'][0]  # noqa: E731
        oe = []
        for e in sorted(T['open'], key=sorted):
            a, c = sorted(e)
            li = T['E'][e][0][0]
            oe.append([rep(a), rep(c), li + 1, T['gof'][li]])
        r = {'ok': True, 'open_edges': oe, 'vertices': [[rep(l)] + fp(l) for l in sorted(T['adj'])],
             'counts': {'faces': len(T['faces']), 'v_lines': len(T['loc']), 'locations': len(locs), 'edges': len(T['E']),
                        'open_edges': len(T['open']), 'open_vertices': len(T['adj']), 'index_split_seams': T['split_seams'],
                        'non_manifold_edges': len(T['nonmanifold']), 'misoriented_edges': len(T['misoriented'])},
             'by': 'positions (decimal coordinates): v lines at one location are one corner; uv / normal / colour seams are '
                   'not open edges', 'tolerance_m': tol, 'gaps': [], 'ambiguous': [], 'note': 'inspection only: nothing changed'}
        if tol is None:
            return r
        near = self._near(T, tol)
        mutual = {}
        for l, h in near.items():
            if len(h) == 1:
                m = h[0][1]
                if len(near[m]) == 1 and near[m][0][1] == l and not (T['loc_faces'][l] & T['loc_faces'][m]):
                    mutual[l] = m
                    continue
            if h:
                r['ambiguous'].append({'vertex': rep(l), 'p': fp(l), 'candidates': [rep(m) for _d, m in h[:6]],
                                       'gaps_m': [round(d, 6) for d, _m in h[:6]],
                                       'why': 'several open-edge vertices within the tolerance' if len(h) > 1 else
                                       'corners of one face' if T['loc_faces'][l] & T['loc_faces'][h[0][1]] else
                                       'not mutual (the other vertex has a nearer partner)'})
        seen = set()
        for l0 in sorted(mutual):
            if l0 in seen:
                continue
            comp, todo = {l0}, [l0]
            while todo:                                     # side A: step along open edges whose partners step along one too
                l = todo.pop()
                for n in T['adj'][l]:
                    if n in mutual and n not in comp and n != mutual[l] and mutual[n] in T['adj'][mutual[l]]:
                        comp.add(n)
                        todo.append(n)
            side_b = {mutual[l] for l in comp}
            seen |= comp | side_b
            deg = {l: sum(1 for n in T['adj'][l] if n in comp) for l in comp}
            branching = any(v > 2 for v in deg.values())
            ends = sorted(l for l in comp if deg[l] <= 1)
            chain, closed = [], not ends and len(comp) > 2
            if not branching:
                cur, prev = (ends[0] if ends else min(comp)), None
                while cur is not None:
                    chain.append(cur)
                    nxt = [n for n in T['adj'][cur] if n in comp and n != prev and n not in chain]
                    prev, cur = cur, (min(nxt) if nxt else None)
            else:
                chain = sorted(comp)
            gaps = [math.dist(fp(l), fp(mutual[l])) for l in chain]
            r['gaps'].append({'chain_a': [rep(l) for l in chain], 'chain_b': [rep(mutual[l]) for l in chain],
                              'pa': [fp(l) for l in chain], 'pb': [fp(mutual[l]) for l in chain], 'closed': closed,
                              'branching': branching, 'pairs': len(chain), 'gaps_m': [round(g, 6) for g in gaps],
                              'max_gap_m': round(max(gaps), 6), 'min_gap_m': round(min(gaps), 6),
                              'weld_as': 'vertex pairs (the chain branches)' if branching else 'pair' if len(chain) == 1 else 'chains'})
        r['gaps'].sort(key=lambda g: (-g['pairs'], g['max_gap_m']))
        return r

    def _weld_req(self, pairs, chains, tol, keep):
        tol = self._tol(tol)
        if keep not in WELD_KEEP:
            raise EditError('keep %r refused: "a" (side A stays, B moves onto it), "b", or "mid" (both move to the midpoint)' % (keep,))
        if (pairs is None) == (chains is None):
            raise EditError('a weld needs either vertex pairs [[a, b], ...] or two matching boundary chains [[a1, a2, ...], '
                            '[b1, b2, ...]] (OBJ v indices, 1-based)')
        vi = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
        if pairs is not None:
            if not (isinstance(pairs, list) and 0 < len(pairs) <= WELD_MAX_PAIRS and
                    all(isinstance(p, list) and len(p) == 2 and all(vi(v) for v in p) for p in pairs)):
                raise EditError('pairs must be [[a, b], ...]: 1..%d pairs of OBJ vertex indices' % WELD_MAX_PAIRS)
            return {'pairs': [list(p) for p in pairs], 'tol': tol, 'keep': keep}
        if not (isinstance(chains, list) and len(chains) == 2 and
                all(isinstance(c, list) and 1 < len(c) <= WELD_MAX_PAIRS and all(vi(v) for v in c) for c in chains)):
            raise EditError('chains must be [[a1, a2, ...], [b1, b2, ...]]: two lists of 2..%d OBJ vertex indices along open edges'
                            % WELD_MAX_PAIRS)
        return {'chains': [list(c) for c in chains], 'tol': tol, 'keep': keep}

    def _weld_key(self, req):
        return hashlib.sha256(('%s|weld|%s' % (self.content_sha(), json.dumps(req, sort_keys=True))).encode()).hexdigest()[:16]

    def _weld_plan(self, req):
        """resolve + check a weld WITHOUT changing anything -> the edited bytes and the report. Refused: a vertex that is not on
        an open edge (interior / unsupported topology), chains that do not follow open edges / do not match one to one / do not
        run together, a gap wider than the tolerance, a pair that is already one location or two corners of one face (would
        collapse it), a location in two pairs, another open-edge vertex within the tolerance of either end (AMBIGUOUS), and an
        edited mesh with a collapsed face, a new non-manifold or misoriented (flipped) edge, a folded / sliver triangle or a
        triangle turning against its stored normal."""
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: welding needs a readable OBJ')
        T = self._topo(self.obj_cur)
        tol, keep, locs, loc = req['tol'], req['keep'], T['locs'], T['loc']
        fp = lambda l: [float(x) for x in locs[l]['p']]  # noqa: E731
        rep = lambda l: locs[l]['vis'][0]  # noqa: E731
        at = lambda l: '[%s]' % ', '.join(_dstr(x) for x in locs[l]['p'])  # noqa: E731

        def L(v, what):
            if not 0 < v <= len(loc):
                raise EditError('%s: vertex %d does not exist (1..%d). Nothing changed' % (what, v, len(loc)))
            l = loc[v - 1]
            if l not in T['adj']:
                raise EditError('%s: vertex %d at %s is not on an open edge (every edge there joins two faces): welding interior '
                                'vertices is unsupported topology. Nothing changed' % (what, v, at(l)))
            return l
        if 'pairs' in req:
            P = [(L(a, 'pair %d' % (i + 1)), L(b, 'pair %d' % (i + 1))) for i, (a, b) in enumerate(req['pairs'])]
        else:
            A = [L(v, 'chain A') for v in req['chains'][0]]
            B = [L(v, 'chain B') for v in req['chains'][1]]
            for name, C, raw in (('A', A, req['chains'][0]), ('B', B, req['chains'][1])):
                if len(set(C)) != len(C):
                    raise EditError('chain %s lists one location twice: refused. Nothing changed' % name)
                for i in range(len(C) - 1):
                    if frozenset((C[i], C[i + 1])) not in T['open']:
                        raise EditError('chain %s: vertices %d and %d are not joined by an open edge (a chain follows the boundary). '
                                        'Nothing changed' % (name, raw[i], raw[i + 1]))
            if set(A) & set(B):
                raise EditError('the two chains share a location: refused. Nothing changed')
            if len(A) != len(B):
                raise EditError('the chains do not match: %d vs %d boundary vertices (welding pairs vertices one to one; gaps are '
                                'not filled automatically). Nothing changed' % (len(A), len(B)))
            idx = {l: j for j, l in enumerate(B)}
            match = []
            for i, l in enumerate(A):
                c = [m for m in B if math.dist(fp(l), fp(m)) <= tol]
                if not c:
                    raise EditError('NO MATCH: chain A vertex %d at %s has no chain B vertex within %s m (nearest %.4f m). Nothing '
                                    'changed' % (req['chains'][0][i], at(l), tol, min(math.dist(fp(l), fp(m)) for m in B)))
                if len(c) > 1:
                    raise EditError('AMBIGUOUS: chain A vertex %d at %s has %d chain B vertices within %s m (%s): reduce the '
                                    'tolerance or weld vertex pairs. Nothing changed' % (
                                        req['chains'][0][i], at(l), len(c), tol, ', '.join(str(rep(m)) for m in c[:4])))
                match.append(idx[c[0]])
            if len(set(match)) != len(match):
                raise EditError('AMBIGUOUS: two chain A vertices match the same chain B vertex within %s m. Nothing changed' % tol)
            steps = {match[i + 1] - match[i] for i in range(len(match) - 1)}
            if steps not in ({1}, {-1}):
                raise EditError('the chains do not run together (chain B order of the matches: %s): refused, nothing changed'
                                % match[:12])
            P = [(A[i], B[match[i]]) for i in range(len(A))]
        used = set()
        for a, b in P:
            if a == b:
                raise EditError('vertices %d and %d are already one location %s: nothing to weld' % (rep(a), rep(b), at(a)))
            if a in used or b in used:
                raise EditError('location %s is in more than one weld pair: refused. Nothing changed' % at(a if a in used else b))
            used |= {a, b}
            d = math.dist(fp(a), fp(b))
            if d > tol:
                raise EditError('GAP TOO WIDE: vertices %d %s and %d %s are %.4f m apart, more than the tolerance %s m. Nothing '
                                'changed' % (rep(a), at(a), rep(b), at(b), d, tol))
            both = sorted(T['loc_faces'][a] & T['loc_faces'][b])
            if both:
                raise EditError('refused: vertices %d and %d are corners of the same face (line %d, group %d): welding them would '
                                'collapse it. Nothing changed' % (rep(a), rep(b), both[0] + 1, T['gof'][both[0]]))
        near = self._near(T, tol)
        for a, b in P:
            for x, y in ((a, b), (b, a)):
                other = [(d, m) for d, m in near[x] if m != y]
                if other:
                    raise EditError('AMBIGUOUS: vertex %d at %s has %d other open-edge vertex(es) within %s m besides its partner %d '
                                    '(nearest: vertex %d at %.4f m): reduce the tolerance or weld those first. Nothing changed' % (
                                        rep(x), at(x), len(other), tol, rep(y), rep(other[0][1]), other[0][0]))
        # targets: decimal positions written as exact tokens (keep a / b: the kept location's own text; mid: rounded HALF_EVEN
        # at the finer of the two precisions)
        lines, vlines = T['lines'], T['vlines']

        def toks(vi):
            t = list(re.finditer(rb'\S+', lines[vlines[vi - 1]]))
            if len(t) not in (4, 7):
                raise EditError('vertex line %d is not v x y z [r g b]: refused (file kept)' % (vlines[vi - 1] + 1))
            return t
        newtxt, rows, prec = {}, [], 0.0
        for a, b in P:
            if keep == 'mid':
                dg = [max(len(t.group().split(b'.')[1]) if b'.' in t.group() else 0
                          for vi in locs[a]['vis'] + locs[b]['vis'] for t in toks(vi)[k + 1:k + 2]) for k in range(3)]
                tgt = [_fmt((locs[a]['p'][k] + locs[b]['p'][k]) / 2, dg[k]).encode('ascii') for k in range(3)]
                prec = max(prec, max(0.5 * 10 ** -d for d in dg))
                mv = locs[a]['vis'] + locs[b]['vis']
            else:
                keepl, movel = (a, b) if keep == 'a' else (b, a)
                tgt = [t.group() for t in toks(rep(keepl))[1:4]]
                mv = locs[movel]['vis']
            for vi in mv:
                newtxt[vi] = tgt
            rows.append({'a': rep(a), 'b': rep(b), 'pa': fp(a), 'pb': fp(b), 'gap_m': round(math.dist(fp(a), fp(b)), 6),
                         'to': [float(x) for x in tgt], 'moves': {'a': 'b', 'b': 'a', 'mid': 'both'}[keep]})
        new = list(lines)
        for vi, xyz in newtxt.items():
            raw, t = lines[vlines[vi - 1]], toks(vi)
            new[vlines[vi - 1]] = raw[:t[1].start()] + b' '.join(xyz) + raw[t[3].end():]
        after = b''.join(new)
        newf = {vi: [float(x) for x in xyz] for vi, xyz in newtxt.items()}
        F = sorted({li for l in {loc[vi - 1] for vi in newtxt} for li in T['loc_faces'][l]})
        T1 = self._topo(after)
        for li in F:
            L1 = [T1['loc'][v - 1] for v in T1['faces'][li]]
            if len(set(L1)) < len(L1):
                raise EditError('refused: face line %d (group %d) would collapse (two of its corners welded to one point). Nothing '
                                'changed' % (li + 1, T['gof'][li]))
        new_locs = {T1['loc'][vi - 1] for vi in newtxt}
        for what, k in (('non-manifold (more than two faces at one edge)', 'nonmanifold'),
                        ('misoriented (two faces traverse it the same way: one would be flipped)', 'misoriented')):
            if len(T1[k]) > len(T[k]):
                e = next((e for e in T1[k] if e & new_locs), T1[k][0])
                u = T1['E'][e]
                raise EditError('refused: the weld would make the edge at %s - %s %s: face lines %s. Unsupported topology; nothing '
                                'changed' % (at1(T1, min(e)), at1(T1, max(e)), what, ', '.join(str(x[0] + 1) for x in u[:4])))
        vn = [[float(t) for t in raw.split()[1:4]] for raw in lines if raw.split()[:1] == [b'vn']]
        nonplanar = 0.0
        for li in F:
            vis = T['faces'][li]
            P0 = [fp(loc[v - 1]) for v in vis]
            P1 = [newf.get(v, P0[j]) for j, v in enumerate(vis)]
            N = []
            for t in lines[li].split()[1:]:
                q = t.split(b'/')
                try:
                    N.append(vn[int(q[2]) - 1])
                except (IndexError, ValueError):
                    N.append(None)
            nonplanar = max(nonplanar, _shape_check('face line %d (group %d)' % (li + 1, T['gof'][li]), P0, P1, N))
        gaps = [x['gap_m'] for x in rows]
        rep_faces = [{'line': li + 1, 'group': T['gof'][li],
                      'corners': [newf.get(v, fp(loc[v - 1])) for v in T['faces'][li]]} for li in F[:600]]
        return {'T': T, 'T1': T1, 'after': after, 'P': P, 'newtxt': newtxt, 'newf': newf, 'F': F, 'rows': rows,
                'summary': {'pairs': rows, 'pair_count': len(rows), 'tolerance_m': tol, 'keep': keep,
                            'max_gap_m': max(gaps), 'min_gap_m': min(gaps), 'affected_faces': len(F),
                            'affected_groups': sorted({T['gof'][li] for li in F}), 'faces': rep_faces,
                            'vertex_lines_rewritten': len(newtxt), 'mid_rounding_bound_m': prec if keep == 'mid' else 0.0,
                            'open_edges': [len(T['open']), len(T1['open'])], 'closes_open_edges': len(T['open']) - len(T1['open']),
                            'max_nonplanar_m': round(nonplanar, 4),
                            'checked': 'open-edge vertices, one-to-one unambiguous matches within the tolerance, no collapsed face, '
                                       'no new non-manifold / misoriented edge, no fold-over / sliver / triangle against its '
                                       'stored normal'}}

    def weld_preview(self, pairs=None, chains=None, tol=None, keep='a'):
        """what a weld would do, WITHOUT changing anything: the matched pairs with their gap distances and targets, the
        affected faces (after) and the open-edge count before / after. The preview_key must accompany the weld."""
        req = self._weld_req(pairs, chains, tol, keep)
        plan = self._weld_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._weld_key(req), note='preview only: nothing changed')

    def weld(self, pairs=None, chains=None, tol=None, keep='a', preview_key=None):
        """weld boundary vertices: the moving side's v lines get the target coordinates as exact decimal tokens (its colour
        tokens kept); every face keeps its own v / vt / vn references, so uv, normal and colour seams are preserved and no line is
        added, removed or renumbered. Needs the preview_key of a weld_preview of exactly this request on this buffer. Then the
        independent re-read, the v0.19 clip check and the kit trackbuild regeneration; one undo entry."""
        req = self._weld_req(pairs, chains, tol, keep)
        if preview_key != self._weld_key(req):
            raise EditError('NEEDS PREVIEW: preview this weld first (it shows the matched pairs, gap distances and affected faces) '
                            'and apply it with its preview_key')
        plan = self._weld_plan(req)
        T, after, F = plan['T'], plan['after'], plan['F']
        exact = self._check_weld(self.obj_cur, after, plan)
        X = {'groups': T['groups'], 'F': set(F), 'nb': [], 'gof': T['gof']}
        clip = self._clip_check(self.obj_cur, after, X, 'isolate')
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(after)
        foot = {li: [(None, v) for v in T['faces'][li]] for li in F}
        mats = sorted({T['groups'][T['gof'][li]]['mat'] for li in F})
        adjust = self._needs_adjustment(T['lines'], T['vlines'], foot, [0.0, 0.0, 0.0], mats, newpos=plan['newf'])
        S = plan['summary']
        label = 'weld %d pair(s) (%s, tolerance %s m, keep %s): max gap %.4f m, %d face(s)' % (
            S['pair_count'], 'chains' if 'chains' in req else 'vertices', _dstr(decimal.Decimal(repr(req['tol']))), req['keep'],
            S['max_gap_m'], len(F))
        self._push('obj', label, after, kind='weld', index=S['affected_groups'])
        if base is None:
            base = {'streamed_sha256': None, 'units': [None] * len(regen['units'])}
        changed = [k for k in range(len(regen['units'])) if regen['units'][k] != base['units'][k]]
        warn = ['%d face(s) in %d group(s) stretched by at most %.4f m: their uv and normal references are kept (seams preserved; '
                'lighting normals are not recomputed)' % (len(F), len(S['affected_groups']), S['max_gap_m'])]
        if S['closes_open_edges'] <= 0:
            warn.append('no open edge closed: the welded corners now coincide but their edges do not (vertex pairs only)')
        if clip['pre_existing']:
            warn.append('%d affected face(s) were already partly outside the unit regions before this weld and lose no more area'
                        % len(clip['pre_existing']))
        return dict({k: v for k, v in S.items()}, ok=True, op='weld', label=label, warnings=warn, exact=exact, clipping=clip,
                    regenerated={'by': 'kit trackbuild build_units (dry run on the edited OBJ; Build regenerates the same from the '
                                       'saved source)',
                                 'what': 'collision trees, unit bounds (culling prism), streamed mesh / LOD blocks, PVS (mode %s), '
                                         'LOD (mode %s)' % (regen['pvs_mode'], regen['lod_mode']),
                                 'streamed_sha256': [base['streamed_sha256'], regen['streamed_sha256']],
                                 'changed_units': [dict(unit=k, before=base['units'][k], after=regen['units'][k]) for k in changed]},
                    needs_adjustment=adjust,
                    not_moved='routes, stations, grid slots, start line, checkpoints, traffic lanes and unit regions are NOT moved by '
                              'a weld; no face is added (no gap filling)')

    def _check_weld(self, before, after, plan):
        """independent re-read of both buffers: same line count; every line other than the rewritten v lines byte for byte (so
        every face's v / vt / vn references, vt / vn / usemtl / comment lines); each rewritten v line = 'v' + the target
        coordinates + its own colour tokens; every location of a weld pair now at one position"""
        l0, l1 = before.splitlines(keepends=True), after.splitlines(keepends=True)
        if len(l0) != len(l1):
            raise EditError('internal: the weld changed the line count; not applied')
        vl = [i for i, r in enumerate(l0) if r.split(b'#', 1)[0].split()[:1] == [b'v']]
        moved = {vl[vi - 1]: xyz for vi, xyz in plan['newtxt'].items()}
        same = 0
        for i, (a, b) in enumerate(zip(l0, l1)):
            if i in moved:
                ta, tb = a.split(), b.split()
                if tb[0] != b'v' or ta[4:] != tb[4:] or [decimal.Decimal(x.decode()) for x in tb[1:4]] != \
                        [decimal.Decimal(x.decode()) for x in moved[i]] or a[len(a.rstrip(b'\r\n')):] != b[len(b.rstrip(b'\r\n')):]:
                    raise EditError('internal: rewritten vertex line %d is not the target with its own colour; not applied' % (i + 1))
            elif a != b:
                raise EditError('internal: line %d outside the welded vertex lines changed; not applied' % (i + 1))
            else:
                same += 1
        V = [[decimal.Decimal(x.decode()) for x in l1[i].split()[1:4]] for i in vl]
        T = plan['T']
        for a, b in plan['P']:
            ps = {tuple(V[vi - 1]) for vi in T['locs'][a]['vis'] + T['locs'][b]['vis']}
            if len(ps) != 1:
                raise EditError('internal: a weld pair is not at one position after the weld; not applied')
        return {'vertex_lines_rewritten': len(moved), 'lines_unchanged': same, 'pairs_coincident': len(plan['P']),
                'uv_normal_refs_and_colours_unchanged': True, 'lines_added_or_removed': 0}

    # ---------------- v0.22 layout construction: duplicate face groups, bridge two open-edge chains with new faces
    @staticmethod
    def _layout_guard(lines, groups, after_line, what):
        """new v / vt / vn lines go after the last existing one; trackbuild's reader needs every index defined before the face that
        uses it, so a face before that line would need renumbering (unsupported). The file must end with a line end (new lines
        are appended after it without touching it)."""
        fl = [li for x in groups for li in x['faces']]
        if fl and after_line is not None and min(fl) < after_line:
            raise EditError('refused: faces come before the last %s line (line %d): new %s lines would need renumbering '
                            '(unsupported OBJ layout; file kept). Nothing changed' % (what, after_line + 1, what))
        if lines and not lines[-1].endswith((b'\n', b'\r')):
            raise EditError('refused: the OBJ does not end with a line end: new lines cannot be appended without changing its '
                            'last line (unsupported layout; file kept). Nothing changed')

    def _clip_added(self, before, after, n_old, src, gof, role, kept=None, desc_bytes=None, round_tol=False):
        """v0.19 rule for ADDED faces (appended after every existing face): the existing faces must be unchanged in trackbuild's
        read; an added face that loses more area outside the unit regions than its source face (a copy) / any area (a bridge face),
        or a collision face no unit would hold, refuses the edit. Unit regions are never expanded."""
        c0, c1 = self.coverage(before), self.coverage(after, desc_bytes)
        units = c1['units']
        F0, F1 = c0['faces'], c1['faces']
        kept = list(range(len(F0))) if kept is None else kept      # v0.24: indices of the faces a replaced block keeps
        if len(F1) != n_old + len(src) or len(kept) != n_old or any(F0[i]['pts'] != F1[j]['pts'] for j, i in enumerate(kept)):
            raise EditError('internal: the existing faces changed in trackbuild\'s read, or the added faces are not last; not applied')
        desc = self.desc() if desc_bytes is None else json.loads(desc_bytes.decode('utf-8'))
        lat = [u.get('lateral') for u in desc['units']]
        X = {'gof': gof}
        lines1, groups1, _v1 = obj_index(after)
        fl = sorted(li for x in groups1 for li in x['faces'])
        bad, pre, lost, split, rounding = [], [], 0.0, 0, 0.0
        for k, b in enumerate(F1[n_old:]):
            li = fl[n_old + k]
            l0 = max(0.0, F0[src[k]]['area'] - F0[src[k]]['kept']) if src[k] is not None else 0.0   # src: indices into F0
            l1 = max(0.0, b['area'] - b['kept'])
            tol = CLIP_TOL_M2 + 1e-9 * b['area']
            if round_tol:                                   # v0.25: faces ending ON a unit cut (race layouts): the 4-decimal
                per = sum(math.dist(b['pts'][q], b['pts'][(q + 1) % len(b['pts'])]) for q in range(len(b['pts'])))
                tol += 0.5e-4 * per                         # coordinates may cross the cut by <= 0.00005 m (kit drops that sliver)
                rounding += max(0.0, b['area'] - b['kept'])
            split += len(b['pieces']) > 1
            if l1 - l0 > tol:
                lost += l1 - l0
                bad.append(self._clip_info(li, X, role, b, l0, l1, units, lat, 'render'))
            elif l1 > tol:
                pre.append(self._clip_info(li, X, role, b, l0, l1, units, lat, 'pre-existing'))
            m = desc['materials'].get(b['mat']) or {}
            if m.get('collide') and not any(u.inside(q[0], q[2], c1['coll_margin']) for u in units for q in b['pts']):
                bad.append(self._clip_info(li, X, role, b, l0, l1, units, lat, 'collision', c1['coll_margin']))
        rep = {'checked_faces': len(F1), 'added_faces': len(src), 'split_across_units': split, 'lost_m2': round(lost, 6),
               'cut_rounding_slivers_m2': round(rounding, 7) if round_tol else None,
               'pre_existing': pre, 'changed_faces': len(src),
               'by': 'kit trackbuild.units make_units / clip on every added face (area inside the union of the unit regions); '
                     'existing faces unchanged; cross-checked against build_units\' own unit pieces'}
        if bad:
            e = EditError('refused: trackbuild would clip %d added face(s) at the unit regions (%.4f m2 lost; Build keeps only what '
                          'lies inside a unit region): %s. Unit regions are authored source data and are never expanded '
                          'automatically. Nothing changed' % (len(bad), lost, '; '.join(
                              'face line %d (%s) %s' % (x['line'], x['material'], 'collision outside every region' if x['kind'] ==
                                                        'collision' else 'loses %.4f of %.4f m2' % (x['lost_m2'], x['area_m2']))
                              for x in bad[:4])))
            rep.update(refused=True, faces=bad)
            e.detail = {'clipping': rep}
            raise e
        rep.update(refused=False, faces=pre)
        return rep

    @staticmethod
    def _regen_report(base, regen):
        if base is None:
            base = {'streamed_sha256': None, 'units': [None] * len(regen['units'])}
        bu = list(base['units']) + [None] * max(0, len(regen['units']) - len(base['units']))   # v0.23: unit count may change
        changed = [k for k in range(len(regen['units'])) if regen['units'][k] != bu[k]]
        base = dict(base, units=bu)
        return {'by': 'kit trackbuild build_units (dry run on the edited OBJ; Build regenerates the same from the saved source)',
                'what': 'collision trees, unit bounds (culling prism), streamed mesh / LOD blocks, PVS (mode %s), LOD (mode %s)' % (
                    regen['pvs_mode'], regen['lod_mode']),
                'streamed_sha256': [base['streamed_sha256'], regen['streamed_sha256']],
                'changed_units': [dict(unit=k, before=base['units'][k], after=regen['units'][k]) for k in changed]}

    def duplicate_groups(self, groups, offset=None):
        """v0.22: copy the selected face groups (one undo step). Each copy = a new `usemtl` line (the source group's line, byte for
        byte) + its `f` lines, APPENDED AT THE END of the OBJ in the selection's group order (new face groups len(groups) ..), so
        no existing group index or line changes. Every v line the selection uses gets one new v line after the last existing one:
        its x y z = the original's + `offset` (exact decimal at the token's own precision; [0, 0, 0] / None = in place: the line is
        copied byte for byte) and its colour tokens copied; the copied faces point to those (corners shared inside the selection
        stay shared in the copy; the copy shares no corner with any other face) and keep their own vt / vn references (exact uv and
        normals). Further move / turn / scale of the copy are their own undo steps; the result's `groups` are the copies (the GUI
        selects them). A copy exactly on its original can be refused by trackbuild's LOD decimation (coincident faces): then
        duplicate with an offset."""
        D = self._dup_offset(offset)
        X = self._selection(groups)
        lines, gall, vlines, F, faces = X['lines'], X['groups'], X['vlines'], X['F'], X['faces']
        self._layout_guard(lines, gall, vlines[-1], 'v')
        used = sorted(X['use_in'])
        remap = {vi: len(vlines) + k + 1 for k, vi in enumerate(used)}
        addv = []
        for vi in used:
            raw = lines[vlines[vi - 1]]
            if not raw.endswith((b'\n', b'\r')):
                raise EditError('internal: a copied vertex line has no line end; not applied')
            if not any(D):
                addv.append(raw)
                continue
            toks = list(re.finditer(rb'\S+', raw))
            if len(toks) not in (4, 7):
                raise EditError('vertex line %d is not v x y z [r g b]: refused (file kept)' % (vlines[vi - 1] + 1))
            xyz = []
            for k in range(3):
                t = toks[1 + k].group().decode('ascii')
                if not re.match(r'^[+-]?\d+(\.\d+)?$', t):
                    raise EditError('vertex line %d: %r is not a plain decimal number: refused (file kept)' % (vlines[vi - 1] + 1, t))
                q = decimal.Decimal(1).scaleb(-(len(t.split('.')[1]) if '.' in t else 0))
                if D[k] != D[k].quantize(q):
                    raise EditError('offset %s on %s is finer than the source precision of vertex %d (%s m): not exactly '
                                    'representable, refused' % (D[k], 'xyz'[k], vi, q))
                xyz.append(format((decimal.Decimal(t) + D[k]).quantize(q), 'f').encode('ascii'))
            addv.append(raw[:toks[1].start()] + b' '.join(xyz) + raw[toks[3].end():])
        tail, src_faces, newg = [], [], []
        for g in X['sel']:
            newg.append(len(gall) + len(newg))
            tail.append(lines[gall[g]['line']])
            for li in gall[g]['faces']:
                raw = lines[li]
                for t, vi in sorted(faces[li], key=lambda z: -z[0].start()):
                    rest = t.group().split(b'/', 1)
                    raw = raw[:t.start()] + str(remap[vi]).encode('ascii') + (b'/' + rest[1] if len(rest) > 1 else b'') + raw[t.end():]
                tail.append(raw)
                src_faces.append(li)
        new = list(lines)
        new[vlines[-1] + 1:vlines[-1] + 1] = addv
        after = b''.join(new + tail)
        exact = self._check_duplicate(self.obj_cur, after, X, newg, D)
        fl = sorted(li for x in gall for li in x['faces'])
        fidx = {li: i for i, li in enumerate(fl)}
        n_old = len(fl)
        _l1, g1, _v1 = obj_index(after)
        gof1 = {li: x['i'] for x in g1 for li in x['faces']}
        clip = self._clip_added(self.obj_cur, after, n_old, [fidx[li] for li in src_faces], gof1, 'copy')
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        try:
            regen = self.regenerate(after)
        except EditError as e:
            if any(D):
                raise
            raise EditError('%s. The copy would lie exactly on its original (coincident faces), which trackbuild\'s LOD / '
                            'collision regeneration may not accept: duplicate with an offset' % str(e).rstrip('.'))
        mats = sorted({gall[g]['mat'] for g in X['sel']})
        newpos = {vi: [float(x) for x in addv[k].split()[1:4]] for k, vi in enumerate(used)}
        adjust = self._needs_adjustment(lines, vlines, faces, None, mats, newpos=newpos)
        T1 = self._topo(after)
        offs = [_dstr(x) for x in D]
        label = 'duplicate %d group(s) %s (%s, %d face(s)) %s -> new group(s) %s' % (
            len(X['sel']), _ranges(X['sel']), '/'.join(mats), len(F), 'in place' if not any(D) else 'at offset [%s]' % ', '.join(offs),
            _ranges(newg))
        self._push('obj', label, after, kind='duplicate', index=newg)
        warn = []
        if not any(D):
            warn.append('the copy lies exactly on the original (coincident faces: %d edge(s) shared by more than two faces by '
                        'position, collision doubled) until it is moved / turned / scaled: it is selected now - position it before '
                        'Build' % len(T1['nonmanifold']))
        elif T1['nonmanifold']:
            warn.append('%d edge(s) are now shared by more than two faces by position (the copy touches existing geometry)'
                        % len(T1['nonmanifold']))
        if clip['pre_existing']:
            warn.append('%d copied face(s) were already partly outside the unit regions (as their originals) and lose no more area'
                        % len(clip['pre_existing']))
        return {'ok': True, 'op': 'duplicate', 'label': label, 'groups': newg, 'source_groups': X['sel'], 'faces': len(F),
                'offset': offs, 'face_lines': [li + 1 for li in sorted(gof1) if gof1[li] in set(newg)],
                'vertex_lines_added': len(addv), 'shared_inside_selection': exact['shared_inside_selection'],
                'placement': 'copies appended at the end of the OBJ as new face groups %s (one usemtl + f lines each, in the '
                             'selection\'s group order); %d new v line(s) after the last v line (%s, colour tokens copied); vt / vn '
                             'references reused' % (_ranges(newg), len(addv), 'byte copies' if not any(D) else
                                                    'positions + [%s] exact' % ', '.join(offs)),
                'exact': exact, 'clipping': clip, 'warnings': warn, 'regenerated': self._regen_report(base, regen),
                'needs_adjustment': adjust,
                'not_moved': 'routes, stations, grid slots, start line, checkpoints, traffic lanes and unit regions are NOT '
                             'changed by a duplication'}

    @staticmethod
    def _dup_offset(offset):
        if offset is None:
            return [decimal.Decimal(0)] * 3
        if not (isinstance(offset, (list, tuple)) and len(offset) == 3 and
                all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in offset)):
            raise EditError('copy offset must be [dx, dy, dz] numbers in metres (or none / [0, 0, 0] = in place)')
        if not all(math.isfinite(x) for x in offset) or max(abs(x) for x in offset) > MAX_MOVE:
            raise EditError('copy offset %r refused: finite, at most %.0f m per axis' % (list(offset), MAX_MOVE))
        return [decimal.Decimal(repr(float(x))) for x in offset]

    def _check_duplicate(self, before, after, X, newg, D):
        """independent re-read: the original lines byte for byte (new v lines only after the last v line, the copies only after
        the last line); each copy group = its source's usemtl line, same face count and, per corner, the same decimal position,
        colour tokens and vt / vn references through FRESH v lines (used by no other face) with the source's sharing pattern; each
        copied position = the original's + the offset D (exact decimal)"""
        l0, l1 = before.splitlines(keepends=True), after.splitlines(keepends=True)
        _a, g0, v0 = obj_index(before)
        _b, g1, v1 = obj_index(after)
        nv = len(v1) - len(v0)
        cut = v0[-1] + 1
        if l1[:cut] != l0[:cut] or l1[cut + nv:cut + nv + len(l0) - cut] != l0[cut:]:
            raise EditError('internal: an original OBJ line changed or moved; not applied')
        if len(g1) != len(g0) + len(newg) or [x['i'] for x in g1[len(g0):]] != newg:
            raise EditError('internal: the copies are not the new last face groups; not applied')

        def corner(lines, vl, t):
            q = t.split(b'/')
            vi = int(q[0])
            v = lines[vl[vi - 1]].split()
            return vi, tuple(decimal.Decimal(x.decode()) for x in v[1:4]), v[4:], b'/'.join(q[1:])
        m, corners = {}, 0
        for k, g in enumerate(X['sel']):
            a, b = g0[g], g1[len(g0) + k]
            if l0[a['line']] != l1[b['line']] or len(a['faces']) != len(b['faces']):
                raise EditError('internal: copy of group %d differs in its usemtl line / face count; not applied' % g)
            for la, lb in zip(a['faces'], b['faces']):
                ta, tb = l0[la].split()[1:], l1[lb].split()[1:]
                if len(ta) != len(tb):
                    raise EditError('internal: a copied face has another corner count; not applied')
                for x, y in zip(ta, tb):
                    ca, cb = corner(l0, v0, x), corner(l1, v1, y)
                    want = tuple(ca[1][k] + D[k] for k in range(3))
                    if (want,) + ca[2:] != cb[1:] or cb[0] <= len(v0) or m.setdefault(ca[0], cb[0]) != cb[0]:
                        raise EditError('internal: a copied corner differs from its original (position / colour / uv / normal / '
                                        'sharing); not applied')
                    corners += 1
        if len(set(m.values())) != len(m) or len(m) != nv:
            raise EditError('internal: the copy does not use exactly one fresh v line per original corner; not applied')
        cnt = collections.Counter(int(t.split(b'/')[0]) for g in X['sel'] for li in g0[g]['faces'] for t in l0[li].split()[1:])
        return {'corners_copied': corners, 'vertex_lines_added': nv, 'original_lines_unchanged': len(l0),
                'uv_normal_refs_colours_positions_equal': True, 'shared_inside_selection': sum(1 for c in cnt.values() if c > 1)}

    # bridge: chains of open-edge vertices -> one quad per chain edge
    def _bridge_req(self, chains, material, closed):
        vi = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
        if not isinstance(closed, bool):
            raise EditError('closed must be true (both chains are closed loops) or false')
        lo = 3 if closed else 2
        if not (isinstance(chains, list) and len(chains) == 2 and
                all(isinstance(c, list) and lo <= len(c) <= WELD_MAX_PAIRS and all(vi(v) for v in c) for c in chains)):
            raise EditError('chains must be [[a1, a2, ...], [b1, b2, ...]]: two lists of %d..%d OBJ vertex indices along open edges '
                            '(explicitly selected; nothing is chosen automatically)' % (lo, WELD_MAX_PAIRS))
        d = self.desc()
        ok = [n for n in (d.get('rows') or []) if n in (d.get('materials') or {}) and
              not set(d['materials'][n]) - {'texture', 'surface', 'collide', 'car_solid'}]
        if not isinstance(material, str) or material not in ok:
            raise EditError('material %r refused: choose an EXISTING material with a render row (%s); new materials are not '
                            'created here' % (material, ', '.join(ok)))
        return {'chains': [list(c) for c in chains], 'material': material, 'closed': closed}

    def _bridge_key(self, req):
        return hashlib.sha256(('%s|bridge|%s' % (self.content_sha(), json.dumps(req, sort_keys=True))).encode()).hexdigest()[:16]

    def _bridge_plan(self, req):
        """resolve + check a bridge WITHOUT changing anything. Correspondence: the existing face on each chain edge fixes the
        direction its boundary runs; new faces must run each chain edge the other way (consistent winding with both neighbours),
        which pairs chain A with chain B in opposite boundary directions; a closed loop also needs the starting pair: the shift
        with the smallest total pair distance, refused when another shift is within 10 % (AMBIGUOUS). Refused: chains not along
        open edges / sharing a location / unequal / winding inconsistently along themselves, a winding-consistent pairing that is
        geometrically crossed (the chains face the same way), a pair at one location / farther than 50 m / corners of one face,
        and new faces that are degenerate, slivers trackbuild would drop, twisted (folded), folding back over a neighbour face
        (more than 120 degrees), or a result with a new non-manifold / misoriented edge."""
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: bridging needs a readable OBJ')
        T = self._topo(self.obj_cur)
        locs, loc, lines, vlines, groups = T['locs'], T['loc'], T['lines'], T['vlines'], T['groups']
        fp = lambda l: [float(x) for x in locs[l]['p']]  # noqa: E731
        rep = lambda l: locs[l]['vis'][0]  # noqa: E731
        at = lambda l: '[%s]' % ', '.join(_dstr(x) for x in locs[l]['p'])  # noqa: E731
        closed = req['closed']
        C = []
        for name, raw in zip('AB', req['chains']):
            L = []
            for v in raw:
                if not 0 < v <= len(loc):
                    raise EditError('chain %s: vertex %d does not exist (1..%d). Nothing changed' % (name, v, len(loc)))
                l = loc[v - 1]
                if l not in T['adj']:
                    raise EditError('chain %s: vertex %d at %s is not on an open edge: a bridge joins boundary chains only '
                                    '(unsupported topology). Nothing changed' % (name, v, at(l)))
                L.append(l)
            if len(set(L)) != len(L):
                raise EditError('chain %s lists one location twice: refused. Nothing changed' % name)
            for i in range(len(L) - (0 if closed else 1)):
                if frozenset((L[i], L[(i + 1) % len(L)])) not in T['open']:
                    raise EditError('chain %s: vertices %d and %d are not joined by an open edge (a chain follows the boundary%s). '
                                    'Nothing changed' % (name, raw[i], raw[(i + 1) % len(L)], '; closed: last back to first'
                                                         if closed and i == len(L) - 1 else ''))
            C.append(L)
        A, B = C
        if set(A) & set(B):
            raise EditError('the two chains share a location: refused (triangles at a shared end are not made). Nothing changed')
        if len(A) != len(B):
            raise EditError('the chains are not compatible: %d vs %d boundary vertices (a bridge makes one quad per chain edge and '
                            'pairs the vertices one to one; no automatic triangulation or hole filling). Nothing changed' % (len(A), len(B)))
        n = len(A)
        ne = n if closed else n - 1

        def run(L, name):                                   # -> L ordered the way its existing faces traverse it + edge owners
            dirs, own = set(), []
            for i in range(ne):
                a, c = L[i], L[(i + 1) % n]
                (li, x, _y, _vp), = T['E'][frozenset((a, c))]
                dirs.add(x == a)
                own.append(li)
            if len(dirs) != 1:
                raise EditError('chain %s: its boundary faces wind inconsistently along the chain (the boundary changes direction): '
                                'the winding of a bridge would be ambiguous. Nothing changed' % name)
            if dirs == {True}:
                return list(L), own
            return (list(reversed(L)), list(reversed(own))) if not closed else ([L[0]] + list(reversed(L[1:])),
                                                                              [own[-1]] + list(reversed(own[:-1])))
        At, ownA = run(A, 'A')
        Bt, ownB = run(B, 'B')
        Br = list(reversed(Bt))
        dist = lambda a, b: math.dist(fp(a), fp(b))  # noqa: E731
        if closed:
            tot = sorted((sum(dist(At[i], Br[(i + s) % n]) for i in range(n)), s) for s in range(n))
            best, s = tot[0]
            if len(tot) > 1 and tot[1][0] <= best * 1.10 + 1e-9:
                raise EditError('AMBIGUOUS: the closed chains can be paired with several starting vertices at nearly the same total '
                                'distance (%.4f vs %.4f m): refused, nothing changed' % (best, tot[1][0]))
            Bp = [Br[(i + s) % n] for i in range(n)]
        else:
            Bp = Br
            alt = sum(dist(At[i], Bt[i]) for i in range(n))
            if alt < sum(dist(At[i], Bp[i]) for i in range(n)):
                raise EditError('refused: the chains face the same way: the correspondence that keeps the winding consistent with '
                                'both neighbours (A %d with B %d, ...) crosses over, the nearer one (A %d with B %d) would flip '
                                'the new faces against a neighbour. Select the chains so their boundaries run opposite. Nothing '
                                'changed' % (rep(At[0]), rep(Bp[0]), rep(At[0]), rep(Bt[0])))
        pairs = []
        for a, b in zip(At, Bp):
            d = dist(a, b)
            if d == 0:
                raise EditError('refused: vertices %d and %d are already one location %s: the bridge face would be degenerate '
                                '(weld instead). Nothing changed' % (rep(a), rep(b), at(a)))
            if d > MAX_MOVE:
                raise EditError('refused: vertices %d and %d are %.2f m apart (at most %.0f m per bridge pair: a typo guard). '
                                'Nothing changed' % (rep(a), rep(b), d, MAX_MOVE))
            both = sorted(T['loc_faces'][a] & T['loc_faces'][b])
            if both:
                raise EditError('refused: vertices %d and %d are corners of the same face (line %d, group %d): a bridge face '
                                'there would overlap it. Nothing changed' % (rep(a), rep(b), both[0] + 1, T['gof'][both[0]]))
            pairs.append((a, b, d))
        # owning faces: chain edge i of At / of Bp (Bp runs the chain B edges against their existing direction)
        ownB_of = {frozenset((Bt[i], Bt[(i + 1) % n])): ownB[i] for i in range(ne)}
        vin = lambda li, l: next(v for v in T['faces'][li] if loc[v - 1] == l)  # noqa: E731
        vn = [[float(t) for t in r.split()[1:4]] for r in lines if r.split(b'#', 1)[0].split()[:1] == [b'vn']]
        fnorm = lambda li: _unit(_newell([fp(loc[v - 1]) for v in T['faces'][li]]))  # noqa: E731
        sA = [0.0]
        for i in range(ne):
            sA.append(sA[-1] + dist(At[i], At[(i + 1) % n]))
        quads, worst = [], 0.0
        sub = lambda a, b: [a[0] - b[0], a[1] - b[1], a[2] - b[2]]  # noqa: E731
        crs = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]  # noqa: E731
        dt = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]  # noqa: E731
        for i in range(ne):
            j = (i + 1) % n
            la, lb = ownA[i], ownB_of[frozenset((Bp[i], Bp[j]))]
            Lq = [At[j], At[i], Bp[i], Bp[j]]
            V = [vin(la, At[j]), vin(la, At[i]), vin(lb, Bp[i]), vin(lb, Bp[j])]
            P = [fp(l) for l in Lq]
            where = 'new face %d (A %d-%d, B %d-%d)' % (i + 1, V[1], V[0], V[2], V[3])
            nrm = _unit(_newell(P))
            area = _poly_area(P)
            if nrm is None or area <= 1e-4:
                raise EditError('refused: %s would be degenerate (area %.6f m2; trackbuild refuses degenerate faces). Nothing '
                                'changed' % (where, area))
            nt = [float(x) for x in _vn_text(nrm, 5)]
            c1, c2 = crs(sub(P[1], P[0]), sub(P[2], P[0])), crs(sub(P[2], P[0]), sub(P[3], P[0]))
            if dt(c1, c2) <= 0:
                raise EditError('refused: %s would be twisted (its two triangles fold against each other: the chains cross '
                                'there). Nothing changed' % where)
            if not all(_fan_good(P, nt)):
                raise EditError('refused: trackbuild would drop a triangle of %s (a sliver under 0.005 m2 or against its normal; '
                                'Build drops such triangles silently). Nothing changed' % where)
            for li in (la, lb):
                m = fnorm(li)
                if m is not None and dt(nrm, m) < BRIDGE_FOLD_DOT:
                    raise EditError('refused: %s would fold back over its neighbour face line %d (group %d; more than 120 degrees '
                                    'between their planes). Nothing changed' % (where, li + 1, T['gof'][li]))
            if quads and dt(nrm, quads[-1]['n']) < BRIDGE_FOLD_DOT:
                raise EditError('refused: %s folds back over the previous new face (more than 120 degrees). Nothing changed' % where)
            nrmP = crs(sub(P[1], P[0]), sub(P[2], P[0]))
            Ln = dt(nrmP, nrmP) ** 0.5
            worst = max(worst, abs(dt(sub(P[3], P[0]), nrmP)) / Ln if Ln else 0.0)
            u = [sA[i + 1], sA[i], sA[i], sA[i + 1]]
            w = [0.0, 0.0, pairs[i][2], pairs[j][2]]
            quads.append({'locs': Lq, 'v': V, 'P': P, 'n': nrm, 'nt': nt, 'uv': [[u[k] / BRIDGE_UV_M, w[k] / BRIDGE_UV_M]
                                                                                   for k in range(4)],
                          'neighbours': [la + 1, lb + 1]})
        if closed and n > 2 and dt(quads[0]['n'], quads[-1]['n']) < BRIDGE_FOLD_DOT:
            raise EditError('refused: the first and last new faces fold back over each other (more than 120 degrees). Nothing changed')
        # ---- bytes: vt / vn lines (existing identical ones reused) + usemtl + f lines appended at the end
        vtl = [li for li, r in enumerate(lines) if r.split(b'#', 1)[0].split()[:1] == [b'vt']]
        vnl = [li for li, r in enumerate(lines) if r.split(b'#', 1)[0].split()[:1] == [b'vn']]

        def known(idx, k):
            out = {}
            for i, li in enumerate(idx):
                t = lines[li].split(b'#', 1)[0].split()[1:]
                if len(t) == k:
                    try:
                        out.setdefault(tuple(decimal.Decimal(x.decode()) for x in t), i + 1)
                    except decimal.InvalidOperation:
                        pass
            return out
        kt, kn = known(vtl, 2), known(vnl, 3)
        addt, addn = [], []
        eol = lines[-1][len(lines[-1].rstrip(b'\r\n')):] or b'\n'

        def ref(vals, K, add, base, word):
            txt = [_fmt(decimal.Decimal(repr(float(x))), 5) for x in vals]
            key = tuple(decimal.Decimal(t) for t in txt)
            if key not in K:
                add.append(('%s %s' % (word, ' '.join(txt))).encode('ascii') + eol)
                K[key] = base + len(add)
            return K[key]
        flines = []
        for q in quads:
            q['vt'] = [ref(uv, kt, addt, len(vtl), 'vt') for uv in q['uv']]
            q['vn'] = ref(q['n'], kn, addn, len(vnl), 'vn')
            flines.append(('f ' + ' '.join('%d/%d/%d' % (q['v'][k], q['vt'][k], q['vn']) for k in range(4))).encode('ascii') + eol)
        self._layout_guard(lines, groups, vlines[-1], 'v')
        if addt:
            self._layout_guard(lines, groups, vtl[-1] if vtl else None, 'vt')
        if addn:
            self._layout_guard(lines, groups, vnl[-1] if vnl else None, 'vn')
        if (addt and not vtl) or (addn and not vnl):
            raise EditError('refused: the OBJ has no vt / vn block to append to (unsupported layout). Nothing changed')
        new = list(lines)
        for at_, block in sorted([((vtl[-1] + 1) if vtl else 0, addt), ((vnl[-1] + 1) if vnl else 0, addn)], key=lambda z: -z[0]):
            new[at_:at_] = block
        tail = [('usemtl %s' % req['material']).encode('ascii') + eol] + flines
        after = b''.join(new + tail)
        T1 = self._topo(after)
        if len(T1['nonmanifold']) > len(T['nonmanifold']) or len(T1['misoriented']) > len(T['misoriented']):
            k = 'nonmanifold' if len(T1['nonmanifold']) > len(T['nonmanifold']) else 'misoriented'
            e = next(e for e in T1[k] if e not in set(T[k]))
            raise EditError('refused: the bridge would make the edge at %s - %s %s (face lines %s). Unsupported topology; nothing '
                            'changed' % (at1(T1, min(e)), at1(T1, max(e)), 'non-manifold (more than two faces)' if k == 'nonmanifold'
                                         else 'misoriented (two faces run it the same way)',
                                         ', '.join(str(x[0] + 1) for x in T1['E'][e][:4])))
        chain_edges = [frozenset((At[i], At[(i + 1) % n])) for i in range(ne)] + [frozenset((Bt[i], Bt[(i + 1) % n])) for i in range(ne)]
        if any(e in T1['open'] for e in chain_edges):
            raise EditError('internal: a chain edge is still open after the bridge; not applied')
        new_open = sorted(T1['open'] - T['open'], key=sorted)
        newg = len(groups)
        return {'T': T, 'T1': T1, 'after': after, 'quads': quads, 'addt': addt, 'addn': addn, 'newg': newg, 'tail': tail,
                'cut': {'vt': (vtl[-1] + 1) if vtl else None, 'vn': (vnl[-1] + 1) if vnl else None},
                'summary': {'pairs': [{'a': rep(a), 'b': rep(b), 'pa': fp(a), 'pb': fp(b), 'gap_m': round(d, 6)} for a, b, d in pairs],
                            'pair_count': len(pairs), 'closed': closed, 'material': req['material'], 'new_faces': len(quads),
                            'new_group': newg, 'faces': [{'corners': q['P'], 'normal': [round(x, 5) for x in q['n']],
                                                          'uv': q['uv'], 'neighbours': q['neighbours']} for q in quads],
                            'winding': 'consistent with both neighbours: every new face runs its chain A edge and its chain B edge '
                                       'opposite to the existing face on that edge (A faces: lines %s; B faces: lines %s)' % (
                                           _ranges(sorted({x + 1 for x in ownA})), _ranges(sorted({x + 1 for x in ownB}))),
                            'correspondence': 'chain A vertex k with chain B vertex %s (boundary directions opposite%s)' % (
                                'n-1-k' if not closed else 'paired from the nearest start', '' if not closed else
                                '; nearest of %d starts' % n),
                            'uv_mapping': 'u = distance along chain A from its first bridged vertex / %g m (a chain B corner takes '
                                          'its partner\'s u), v = 0 on chain A and the pair distance / %g m on chain B (one '
                                          'texture repeat per %g m, not stretched along the chain)' % (BRIDGE_UV_M, BRIDGE_UV_M, BRIDGE_UV_M),
                            'normals': 'one new face normal per new face (its Newell normal, 5 decimals; flat shading)',
                            'colours': 'each new corner uses the v line of the neighbour face on that chain edge (its colour)',
                            'vt_lines_added': len(addt), 'vn_lines_added': len(addn), 'v_lines_added': 0,
                            'open_edges': [len(T['open']), len(T1['open'])], 'closes_open_edges': 2 * ne,
                            'new_open_edges': len(new_open), 'max_nonplanar_m': round(worst, 4),
                            'checked': 'chains along open edges, equal length, consistent winding, unambiguous correspondence, no '
                                       'degenerate / twisted / sliver / folded face, no new non-manifold or misoriented edge'}}

    def bridge_preview(self, chains=None, material=None, closed=False):
        """what a bridge would add, WITHOUT changing anything: the correspondence (pairs), winding, new faces (corners, normals,
        uv), open edges before / after. The preview_key must accompany the bridge."""
        req = self._bridge_req(chains, material, closed)
        plan = self._bridge_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._bridge_key(req), note='preview only: nothing changed')

    def bridge(self, chains=None, material=None, closed=False, preview_key=None):
        """v0.22: bridge two explicitly selected, compatible open-edge chains with new quads (one per chain edge), one undo step.
        New faces: a new face group (`usemtl MATERIAL` + f lines) appended at the end of the OBJ; corners = the existing v lines
        of the neighbour faces (no v line added or moved); new vt / vn lines after the last existing ones (identical existing
        lines reused). Needs the preview_key of a bridge_preview of exactly this request on this buffer; then the independent
        re-read, the v0.19 clip check for the new faces and the kit trackbuild regeneration."""
        req = self._bridge_req(chains, material, closed)
        if preview_key != self._bridge_key(req):
            raise EditError('NEEDS PREVIEW: preview this bridge first (it shows the correspondence, winding and new faces) and '
                            'apply it with its preview_key')
        plan = self._bridge_plan(req)
        T, after = plan['T'], plan['after']
        exact = self._check_bridge(self.obj_cur, after, plan)
        n_old = len(T['faces'])
        _l1, g1, _v1 = obj_index(after)
        gof1 = {li: x['i'] for x in g1 for li in x['faces']}
        clip = self._clip_added(self.obj_cur, after, n_old, [None] * len(plan['quads']), gof1, 'bridge')
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(after)
        S = plan['summary']
        lines1, _g, vl1 = obj_index(after)
        foot = {li: [(None, int(t.split(b'/')[0])) for t in lines1[li].split()[1:]] for li in g1[-1]['faces']}
        adjust = self._needs_adjustment(lines1, vl1, foot, [0.0, 0.0, 0.0], [req['material']])
        label = 'bridge %d pair(s) (%s chains, %s): %d new face(s) -> group %d' % (
            S['pair_count'], 'closed' if req['closed'] else 'open', req['material'], S['new_faces'], plan['newg'])
        self._push('obj', label, after, kind='bridge', index=[plan['newg']])
        warn = []
        if S['new_open_edges']:
            warn.append('%d new open edge(s): the bridge\'s end rungs border no other face (open chains)' % S['new_open_edges'])
        warn.append('new faces use material %s with the documented uv mapping (u along chain A, v across, %g m per repeat)'
                    % (req['material'], BRIDGE_UV_M))
        return dict(S, ok=True, op='bridge', label=label, groups=[plan['newg']], warnings=warn, exact=exact, clipping=clip,
                    regenerated=self._regen_report(base, regen), needs_adjustment=adjust,
                    not_moved='routes, stations, grid slots, start line, checkpoints, traffic lanes and unit regions are NOT '
                              'changed by a bridge; no hole is filled automatically')

    def _check_bridge(self, before, after, plan):
        """independent re-read: the original lines byte for byte (new vt / vn lines only right after the last ones, the new group
        only after the last line); the new faces = 'usemtl MATERIAL' + one quad per pair step, corners on EXISTING v lines at the
        chain positions, every chain edge now used by two faces running it in opposite directions (by position)"""
        l0, l1 = before.splitlines(keepends=True), after.splitlines(keepends=True)
        na, nn = len(plan['addt']), len(plan['addn'])
        rest = list(l1)
        cuts = sorted([(plan['cut']['vt'], na), (plan['cut']['vn'], nn)], key=lambda z: -(z[0] or 0))   # later insertion first
        for at_, m in cuts:
            if m:
                at2 = at_ + sum(mm for a2, mm in cuts if a2 is not None and a2 < at_)
                rest[at2:at2 + m] = []
        tail = len(plan['tail'])
        if rest[:len(rest) - tail] != l0 or rest[len(rest) - tail:] != plan['tail']:
            raise EditError('internal: an original OBJ line changed or the new lines are not where planned; not applied')
        _a, g0, v0 = obj_index(before)
        lines1, g1, v1 = obj_index(after)
        if len(v1) != len(v0) or len(g1) != len(g0) + 1:
            raise EditError('internal: the bridge added v lines or more than one face group; not applied')
        V = [tuple(decimal.Decimal(x.decode()) for x in lines1[li].split()[1:4]) for li in v1]
        E = collections.defaultdict(list)
        for x in g1:
            for li in x['faces']:
                P = [V[int(t.split(b'/')[0]) - 1] for t in lines1[li].split()[1:]]
                for i in range(len(P)):
                    E[frozenset((P[i], P[(i + 1) % len(P)]))].append((P[i], li))
        T = plan['T']
        closedn = 0
        for q in plan['quads']:
            for e in ((q['locs'][0], q['locs'][1]), (q['locs'][2], q['locs'][3])):
                k = frozenset(T['locs'][l]['p'] for l in e)
                u = E[k]
                if len(u) != 2 or u[0][0] == u[1][0]:
                    raise EditError('internal: a chain edge is not closed with opposite winding after the bridge; not applied')
                closedn += 1
        return {'original_lines_unchanged': len(l0), 'vt_lines_added': na, 'vn_lines_added': nn, 'v_lines_added': 0,
                'faces_added': len(plan['quads']), 'chain_edges_closed_opposite_winding': closedn}

    # ---------------- v0.24 construction blocks: generated faces appended as tagged face groups (roads; v0.26 walls, terrain,
    # prefabs). A block = one or more face groups, each `usemtl MATERIAL` + the tag line `# wb-construct {"kind", "id", ...}`
    # (its parameters, ASCII JSON; comments are ignored by trackbuild) + its f lines, appended at the end of the OBJ; new v / vt /
    # vn lines after the last existing ones (identical existing vt / vn lines reused). Re-generating a block removes only its own
    # usemtl / tag / f lines (its old v / vt / vn lines stay, unused) and appends the new one.
    TAG = b'# wb-construct '

    def constructs(self, b=None):
        """the tagged construction blocks of OBJ bytes -> {id: {'meta', 'groups': [group indices], 'faces'}}"""
        b = self.obj_cur if b is None else b
        if b is None:
            return {}
        lines, groups, _v = obj_index(b)
        out = {}
        for x in groups:
            nxt = x['line'] + 1
            if nxt < len(lines) and lines[nxt].startswith(self.TAG):
                try:
                    meta = json.loads(lines[nxt][len(self.TAG):].decode('ascii'))
                except ValueError:
                    continue
                if isinstance(meta, dict) and isinstance(meta.get('id'), str):
                    e = out.setdefault(meta['id'], {'meta': meta, 'groups': [], 'faces': 0})
                    e['groups'].append(x['i'])
                    e['faces'] += len(x['faces'])
        return out

    def _new_id(self, kind):
        C = self.constructs()
        k = 1
        while '%s%d' % (kind, k) in C:
            k += 1
        return '%s%d' % (kind, k)

    def _block_bytes(self, faces, meta, replace=(), parts=None):
        """generated faces [(material, [(pos, uv, normal, colour)])] -> the edited OBJ bytes (see above) + the plan. Every face
        is checked as WRITTEN (4 / 5 decimals): area > 1e-4 m2 and every fan triangle kept by trackbuild (no sliver, winding with
        its normal). `replace` = group indices whose usemtl / tag / f lines are removed (a re-generated block)."""
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: construction needs a readable OBJ')
        lines, groups, vlines = obj_index(self.obj_cur)
        kw = lambda r: r.split(b'#', 1)[0].split()[:1]  # noqa: E731
        vtl = [li for li, r in enumerate(lines) if kw(r) == [b'vt']]
        vnl = [li for li, r in enumerate(lines) if kw(r) == [b'vn']]
        if not vtl or not vnl:
            raise EditError('refused: the OBJ has no vt / vn block to append to (unsupported layout). Nothing changed')
        self._layout_guard(lines, groups, max(vlines[-1], vtl[-1], vnl[-1]), 'v / vt / vn')
        rm, removed = set(), 0
        for g in replace:
            x = groups[g]
            rm |= {x['line']} | set(x['faces'])
            if x['line'] + 1 < len(lines) and lines[x['line'] + 1].startswith(self.TAG):
                rm.add(x['line'] + 1)
            removed += len(x['faces'])

        def known(idx, k):
            out = {}
            for i, li in enumerate(idx):
                t = lines[li].split(b'#', 1)[0].split()[1:]
                if len(t) == k:
                    try:
                        out.setdefault(tuple(decimal.Decimal(x.decode()) for x in t), i + 1)
                    except decimal.InvalidOperation:
                        pass
            return out
        kt, kn = known(vtl, 2), known(vnl, 3)
        eol = lines[-1][len(lines[-1].rstrip(b'\r\n')):] or b'\n'
        addv, addt, addn, vmap = [], [], [], {}

        def ref(txt, K, add, base, word):
            key = tuple(decimal.Decimal(t) for t in txt)
            if key not in K:
                add.append(('%s %s' % (word, ' '.join(txt))).encode('ascii') + eol)
                K[key] = base + len(add)
            return K[key]
        blocks, written = [], []
        flat = [(fi, mat, cs, pi) for pi, (pf, _pm) in enumerate(parts or [(faces, meta)]) for fi, (mat, cs) in enumerate(pf)]
        metas = [pm for _pf, pm in (parts or [(faces, meta)])]
        for fi, mat, cs, pi in flat:
            if len(cs) not in (3, 4):
                raise EditError('internal: a generated face has %d corners' % len(cs))
            toks, P, N = [], [], None
            for p, uv, n, col in cs:
                vt_ = ['%.4f' % x for x in p] + ['%.3f' % x for x in col]
                vt_ = [_fmt(decimal.Decimal(x), 4 if i < 3 else 3) for i, x in enumerate(vt_)]
                key = ' '.join(vt_)
                if key not in vmap:
                    addv.append(('v ' + key).encode('ascii') + eol)
                    vmap[key] = len(vlines) + len(addv)
                tt_ = [_fmt(decimal.Decimal(repr(float(x))), 5) for x in uv]
                nt_ = [_fmt(decimal.Decimal(repr(float(x))), 5) for x in n]
                toks.append('%d/%d/%d' % (vmap[key], ref(tt_, kt, addt, len(vtl), 'vt'), ref(nt_, kn, addn, len(vnl), 'vn')))
                P.append([float(x) for x in vt_[:3]])
                N = N or [float(x) for x in nt_]
            area = _poly_area(P)
            if area <= 1e-4:
                raise EditError('refused: generated %s face %d is degenerate as written (area %.6f m2). Nothing changed' % (mat, fi, area))
            if not all(_fan_good(P, N)):
                raise EditError('refused: trackbuild would drop a triangle of generated %s face %d (a sliver under 0.005 m2 or '
                                'against its normal): use larger steps / widths. Nothing changed' % (mat, fi))
            if not blocks or blocks[-1][0] != mat or blocks[-1][2] != pi:
                blocks.append((mat, [], pi))
            blocks[-1][1].append(('f ' + ' '.join(toks)).encode('ascii') + eol)
            written.append(P)
        tags = [self.TAG + json.dumps(m, sort_keys=True, separators=(',', ':')).encode('ascii') + eol for m in metas]
        tail = []
        for mat, fl, pi in blocks:                          # v0.25: several tagged parts (e.g. road + walls + verges) in one edit
            tail += [('usemtl %s' % mat).encode('ascii') + eol, tags[pi]] + fl
        ins = sorted([(vlines[-1] + 1, addv), (vtl[-1] + 1, addt), (vnl[-1] + 1, addn)], key=lambda z: -z[0])
        if rm and min(rm) < ins[0][0]:
            raise EditError('internal: a removed line precedes the inserted lines; not applied')
        new = [ln for i, ln in enumerate(lines) if i not in rm]
        for at_, blk in ins:
            new[at_:at_] = blk
        after = b''.join(new + tail)
        return after, {'faces': written, 'tail': tail, 'rm': sorted(rm), 'ins': [(a, len(b)) for a, b in ins], 'removed_faces': removed,
                       'v_added': len(addv), 'vt_added': len(addt), 'vn_added': len(addn), 'groups_added': len(blocks),
                       'n_old_groups': len(groups), 'replace': list(replace)}

    def _check_block(self, before, after, plan, planned):
        """independent re-read: every kept original line byte for byte and in order (new v / vt / vn lines only right after the last
        existing ones, the block only at the end, only the replaced block's usemtl / tag / f lines removed); the kit reader's
        faces of the block = the planned faces (positions within 0.00005 m, uv / normals within 0.000005, materials)"""
        l0, l1 = before.splitlines(keepends=True), after.splitlines(keepends=True)
        keep0 = [ln for i, ln in enumerate(l0) if i not in set(plan['rm'])]
        rest = list(l1)
        cuts = sorted(plan['ins'], key=lambda z: z[0])
        off, spans = 0, []
        for at_, m in cuts:
            spans.append((at_ + off, m))
            off += m
        for at_, m in sorted(spans, key=lambda z: -z[0]):
            rest[at_:at_ + m] = []
        tail = len(plan['tail'])
        if rest[:len(rest) - tail] != keep0 or rest[len(rest) - tail:] != plan['tail']:
            raise EditError('internal: an original OBJ line changed or the new lines are not where planned; not applied')
        K = kit_trackbuild(self.cfg)
        root = os.path.join(self.cfg['state'], 'geomcheck')
        os.makedirs(root, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='blk_', dir=root)
        try:
            p = os.path.join(tmp, 'edited.obj')
            with open(p, 'wb') as f:
                f.write(after)
            obj = K['io'].read_obj(p)
        except K['io'].SourceError as e:
            raise EditError('refused: trackbuild cannot read the edited OBJ (%s). Nothing changed' % e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        got = obj['faces'][len(obj['faces']) - len(planned):]
        perr = terr = 0.0
        for (m0, cs0), (m1, cs1) in zip(planned, got):
            if m0 != m1 or len(cs0) != len(cs1):
                raise EditError('internal: a written face has another material / corner count; not applied')
            for (p, uv, n, _c), (p1, uv1, n1, _c1) in zip(cs0, cs1):
                perr = max(perr, max(abs(a - b) for a, b in zip(p, p1)))
                terr = max(terr, max(abs(a - b) for a, b in zip(list(uv) + list(n), list(uv1) + list(n1))))
        if perr > 0.5e-4 + 1e-9 or terr > 0.5e-5 + 1e-9:
            raise EditError('internal: written faces differ from the plan (%.6f m / %.7f); not applied' % (perr, terr))
        return {'original_lines_kept': len(keep0), 'lines_removed': len(plan['rm']), 'v_added': plan['v_added'],
                'vt_added': plan['vt_added'], 'vn_added': plan['vn_added'], 'faces_added': len(planned),
                'max_position_rounding_m': round(perr, 7), 'max_uv_normal_rounding': round(terr, 8)}

    def _route_floor_warnings(self, faces_written):
        """V2_drivable_coverage (kit validator): every route sample wall to wall needs a floor within 0.05 m of the route height
        there (trackbuild 0.3.0: the stations' own y, interpolated; 0.2.1 used station 0's height, the same for a flat route),
        the HIGHEST floor under it counts. A generated face over a route sample at another height makes Build -> Validate fail."""
        d = self.desc()
        st = d.get('stations') or []
        if not st:
            return []
        y0 = st[0]['p'][1]
        hit = 0
        for x, z, _i, ry in wc.route_samples(st):
            for P in faces_written:
                xs, zs = [q[0] for q in P], [q[2] for q in P]
                if not (min(xs) <= x <= max(xs) and min(zs) <= z <= max(zs)):
                    continue
                for i in range(1, len(P) - 1):
                    a, b, c = P[0], P[i], P[i + 1]
                    det = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
                    if abs(det) < 1e-12:
                        continue
                    l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / det
                    l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / det
                    if l1 >= 0 and l2 >= 0 and l1 + l2 <= 1:
                        y = l1 * a[1] + l2 * b[1] + (1 - l1 - l2) * c[1]
                        hit += abs(y - ry) > 0.05 and y > ry
                        break
        return (['%d route drivable sample(s) lie under new faces higher than the route floor (the route height there; station 0 '
                 'y %s): the kit\'s V2_drivable_coverage gate will refuse Build -> Validate (the drivable floor must follow the '
                 'route height)' % (hit, y0)]
                if hit else [])

    def _apply_block(self, plan, label, kind, n_planned):
        """the exact re-read, the v0.19 clip rule for the new faces, the kit's build_units dry run, the adjustment report and one
        undo entry for a construction block"""
        after = plan['after']
        exact = self._check_block(self.obj_cur, after, plan['blk'], plan['planned'])
        cov0 = self.coverage(self.obj_cur)
        lines0, groups0, _v0 = obj_index(self.obj_cur)
        fl0 = sorted(li for x in groups0 for li in x['faces'])
        rmset = set(plan['blk']['rm'])
        kept = [i for i, li in enumerate(fl0) if li not in rmset]
        lines1, groups1, vl1 = obj_index(after)
        gof1 = {li: x['i'] for x in groups1 for li in x['faces']}
        # v0.26: scenery faces (terrain cells, barrier steps, prefab copies) may cross a unit cut; the kit clipper loses the same
        # 4-decimal rounding slivers there as on race layouts (reported as cut_rounding_slivers_m2). Roads keep the strict rule.
        clip = self._clip_added(self.obj_cur, after, len(kept), [None] * n_planned, gof1, kind, kept=kept,
                                round_tol=kind in ('terrain', 'barrier', 'prefab'))
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(after)
        newg = [x['i'] for x in groups1[len(groups1) - plan['blk']['groups_added']:]]
        foot = {li: [(None, int(t.split(b'/')[0])) for t in lines1[li].split()[1:]] for g in newg for li in groups1[g]['faces']}
        adjust = self._needs_adjustment(lines1, vl1, foot, [0.0, 0.0, 0.0], sorted({groups1[g]['mat'] for g in newg}))
        self._push('obj', label, after, kind=kind, index=newg)
        return {'ok': True, 'label': label, 'groups': newg, 'exact': exact, 'clipping': clip,
                'regenerated': self._regen_report(base, regen), 'needs_adjustment': adjust,
                'new_faces': [[list(q) for q in P] for P in plan['blk']['faces'][:3000]]}

    # roads
    def _road_req(self, points, closed, width, material, uv_len, step, road):
        if not isinstance(closed, bool):
            raise EditError('closed must be true or false')
        try:
            P = wc.check_points(points, closed)
        except wc.ConstructError as e:
            raise EditError('road refused: %s' % e)
        num = lambda v, lo, hi: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi  # noqa: E731
        if not num(width, 2, 60):
            raise EditError('road width %r refused: 2..60 m' % (width,))
        if not num(uv_len, 0.5, 200):
            raise EditError('uv length %r refused: 0.5..200 m per texture repeat' % (uv_len,))
        if not num(step, 0.5, 20):
            raise EditError('step %r refused: 0.5..20 m between cross-sections' % (step,))
        d = self.desc()
        ok = [n for n in (d.get('rows') or []) if n in (d.get('materials') or {}) and
              not set(d['materials'][n]) - {'texture', 'surface', 'collide', 'car_solid'}]
        if material not in ok:
            raise EditError('material %r refused: an EXISTING material with a render row (%s)' % (material, ', '.join(ok)))
        if road is not None:
            C = self.constructs()
            if road not in C or C[road]['meta'].get('kind') != 'road':
                raise EditError('road %r does not exist (roads: %s)' % (road, ', '.join(k for k, v in C.items() if v['meta'].get('kind') == 'road') or 'none'))
        return {'points': P, 'closed': closed, 'width': float(width), 'material': material, 'uv_len': float(uv_len),
                'step': float(step), 'road': road}

    def _road_plan(self, req):
        try:
            S, L = wc.sample(req['points'], req['closed'], step=req['step'])
            T = wc.tangents(S, req['closed'])
            faces, length = wc.road_strip(S, T, req['closed'], req['width'], req['material'], req['uv_len'])
        except wc.ConstructError as e:
            raise EditError('road refused: %s. Nothing changed' % e)
        rid = req['road'] or self._new_id('road')
        meta = {'kind': 'road', 'id': rid, 'points': req['points'], 'closed': req['closed'], 'width': req['width'],
                'material': req['material'], 'uv_len': req['uv_len'], 'step': req['step']}
        repl = self.constructs()[req['road']]['groups'] if req['road'] else []
        after, blk = self._block_bytes(faces, meta, repl)
        ys = [p[1] for p in S]
        warn = self._route_floor_warnings(blk['faces'])
        slope = max((abs(S[i + 1][1] - S[i][1]) / max(1e-9, math.dist(S[i], S[i + 1])) for i in range(len(S) - 1)), default=0.0)
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'road': rid, 'replaces': req['road'], 'samples': len(S), 'length_m': round(length, 3), 'faces': len(faces),
                            'closed': req['closed'], 'width_m': req['width'], 'material': req['material'],
                            'elevation_m': [round(min(ys), 3), round(max(ys), 3)], 'max_slope_pct': round(100 * slope, 2),
                            'min_radius_m': round(wc.min_radius(S, req['closed'])[0], 2),
                            'v_added': blk['v_added'], 'vt_added': blk['vt_added'], 'vn_added': blk['vn_added'],
                            'removed_faces': blk['removed_faces'], 'warnings': warn,
                            'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]], 'markers': req['points'],
                            'uv_mapping': 'u 0 (n- edge) .. 1 (n+ edge) across, v = distance along / %g m' % req['uv_len'],
                            'normals': 'each quad\'s Newell normal (5 decimals; faces up)',
                            'checked': 'control points, curve radius >= 1.25 x half width (no folded inner edge), no self-crossing, '
                                       'every face as written (area, trackbuild triangle rule)'}}

    def road_preview(self, points=None, closed=False, width=12.0, material=None, uv_len=14.0, step=4.0, road=None):
        """v0.24: a road strip from control points (a centripetal Catmull-Rom curve through them, cross-sections every `step` m,
        `width` m wide, elevation = the points' y), WITHOUT changing anything; `road` = an existing road id to re-generate"""
        req = self._road_req(points, closed, width, material, uv_len, step, road)
        plan = self._road_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('road', req), note='preview only: nothing changed')

    def road(self, points=None, closed=False, width=12.0, material=None, uv_len=14.0, step=4.0, road=None, preview_key=None):
        """v0.24: apply a previewed road strip: a tagged construction block (one face group, existing material) appended at the end
        of the OBJ; re-generating an existing road replaces its block. One undo entry; clip rule + trackbuild dry run."""
        req = self._road_req(points, closed, width, material, uv_len, step, road)
        if preview_key != self._cons_key('road', req):
            raise EditError('NEEDS PREVIEW: preview this road first and apply it with its preview_key')
        plan = self._road_plan(req)
        S = plan['summary']
        label = '%s %s (%s, %.1f m wide, %.1f m, %d faces)' % ('re-generate road' if road else 'new road', plan['id'],
                                                             req['material'], req['width'], S['length_m'], S['faces'])
        r = self._apply_block(plan, label, 'road', S['faces'])
        return dict(S, **r)

    def _cons_key(self, kind, req):
        return hashlib.sha256(('%s|%s|%s' % (self.content_sha(), kind, json.dumps(req, sort_keys=True))).encode()).hexdigest()[:16]

    # ---------------- v0.25 race layout: structural checks, a route-carrying layout from closed control points, checkpoints
    RUNTIME_NOTE = ('STRUCTURAL checks only (offline re-implementation of the kit validator\'s sampling + layout rules; the kit gates '
                    'at Build -> Validate decide). NOT proven: AI drivers following the route, lap / checkpoint counting, respawn, '
                    'streaming and collision in the game - they need an in-game run (README "Runtime acceptance plan")')

    def race_check_view(self):
        return self.race_check()

    def race_check(self, obj_bytes=None, desc_bytes=None):
        """READ ONLY: structural validation of the race layout (connectivity, direction, drivable coverage + floor, walls, lap
        order, grid) on the current (or candidate) source"""
        ob = self.obj_cur if obj_bytes is None else obj_bytes
        db = self.cur if desc_bytes is None else desc_bytes
        if ob is None:
            raise EditError('the OBJ did not pass the input check: race checks need a readable OBJ')
        d = json.loads(db.decode('utf-8'))
        cov = self.coverage(ob, db)
        mats = d.get('materials') or {}
        faces = [(int(mats[f['mat']]['surface'], 16) if (mats.get(f['mat']) or {}).get('collide') else None, f['pts'])
                 for f in cov['faces']]
        checks = wc.race_checks(d, faces, cov['units'])
        st = d.get('stations') or []
        lines = []
        if st:
            y0 = st[0]['p'][1]
            lines = [[[s_['p'][0], y0 + 0.3, s_['p'][2]], [st[(i + 1) % len(st)]['p'][0], y0 + 0.3, st[(i + 1) % len(st)]['p'][2]]]
                     for i, s_ in enumerate(st)]
        marks = [g['pos'] for g in d.get('grid') or []] + [c['pos'] for c in d.get('checkpoints') or []]
        return {'ok': True, 'structural': checks, 'structural_ok': all(c['ok'] for c in checks), 'runtime': self.RUNTIME_NOTE,
                'route_lines': lines, 'markers': marks,
                'summary_lines': ['STRUCTURAL %s: ' % ('PASS' if all(c['ok'] for c in checks) else 'FAIL') +
                                  ', '.join('%s %s' % (c['check'], 'ok' if c['ok'] else 'FAILED') for c in checks),
                                  'RUNTIME: ' + self.RUNTIME_NOTE]}

    def _race_req(self, points, width, material, wall_height, wall_thick, wall_mat, back_mat, verge_out, verge_in, verge_mat,
                  n_units, checkpoints, traffic, replace):
        num = lambda v, lo, hi: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi  # noqa: E731
        try:
            P = wc.check_points(points, True)
        except wc.ConstructError as e:
            raise EditError('race layout refused: %s' % e)
        if len({p[1] for p in P}) != 1:
            raise EditError('race layout refused: every control point needs the same y - this generator builds a route at one height '
                            '(walls / verges / stations level; trackbuild 0.3.0 accepts sloped routes, sloped generation is not in the '
                            'editor yet)')
        for name, v, lo, hi in (('width', width, 6, 40), ('wall height', wall_height, 0.5, 20), ('wall thickness', wall_thick, 0.2, 3),
                                ('outer verge', verge_out, 0, 60), ('inner verge', verge_in, 0, 60)):
            if not num(v, lo, hi):
                raise EditError('%s %r refused: %g..%g m' % (name, v, lo, hi))
        ii = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
        if not ii(n_units) or n_units != 17:
            raise EditError('units %r refused: a race layout uses 17 units - with pvs "all" the kit\'s validator (V3_pvs_walk) accepts '
                            'exactly 17: every unit lists 17 relative units (-8..+8), so fewer units repeat a target (kit fact, '
                            'trackbuild.blocks.pvs_chunks)' % (n_units,))
        if not ii(checkpoints) or not 1 <= checkpoints <= 12:
            raise EditError('checkpoints %r refused: 1..12 (S1 cap)' % (checkpoints,))
        if not isinstance(traffic, bool):
            raise EditError('traffic must be true (authored traffic in the demo\'s shape) or false (donor traffic)')
        if replace not in ('all', 'route'):
            raise EditError('replace %r refused: "all" (every face group of the OBJ is replaced: an explicit choice) or "route" '
                            '(only the blocks of an earlier race layout; other geometry is kept)' % (replace,))
        d = self.desc()
        mats = d.get('materials') or {}
        ok = [n for n in (d.get('rows') or []) if n in mats and not set(mats[n]) - {'texture', 'surface', 'collide', 'car_solid'}]
        for role, m in (('road', material), ('wall', wall_mat), ('wall back', back_mat), ('verge', verge_mat)):
            if m not in ok:
                raise EditError('%s material %r refused: an EXISTING material with a render row (%s)' % (role, m, ', '.join(ok)))
        w = lambda m: int(mats[m]['surface'], 16)  # noqa: E731
        if not mats[material].get('collide') or (w(material) & 0xFF) > 20:
            raise EditError('road material %s refused: it must be a collide FLOOR word (low byte <= 20, e.g. 0x0001 tarmac) - the kit '
                            'validator only counts those as drivable floor' % material)
        if not mats[wall_mat].get('collide') or (w(wall_mat) & 0xFF) < 21 or w(wall_mat) & 0x1000 or mats[wall_mat].get('car_solid') is False:
            raise EditError('wall material %s refused: it must be a car-solid collide WALL word (low byte >= 21, no flag 0x10, e.g. '
                            '0x0018) - V2_walls_hold probes only those' % wall_mat)
        if replace == 'route' and not any(c['meta'].get('route') for c in self.constructs().values()):
            raise EditError('replace "route" refused: there is no earlier race layout block to replace (use "all" for a new layout)')
        return {'points': P, 'width': float(width), 'material': material, 'wall_height': float(wall_height),
                'wall_thick': float(wall_thick), 'wall_mat': wall_mat, 'back_mat': back_mat, 'verge_out': float(verge_out),
                'verge_in': float(verge_in), 'verge_mat': verge_mat, 'n_units': n_units, 'checkpoints': checkpoints,
                'traffic': traffic, 'replace': replace}

    def _race_plan(self, req):
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: a race layout needs a readable OBJ')
        P, hw, t = req['points'], req['width'] / 2, req['wall_thick']
        y0 = P[0][1]
        sps = 3
        try:
            _S, L = wc.sample(P, True, step=2.0)
            spu = sps * max(1, int(round(L / (req['n_units'] * 2.0 * sps))))
            n = req['n_units'] * spu
            S, L = wc.sample(P, True, count=n)
            S = [[p[0], y0, p[2]] for p in S]
            T = wc.tangents(S, True)
            road, _len = wc.road_strip(S, T, True, req['width'], req['material'], 14.0)
            reach = [(-(hw + t + req['verge_out'])), hw + t + req['verge_in']]
            for o in reach:                                 # an offset edge running backwards = a folded strip
                for i in range(n):
                    a, b = wc.offset_pt(S[i], T[i], o), wc.offset_pt(S[(i + 1) % n], T[(i + 1) % n], o)
                    if (b[0] - a[0]) * T[i][0] + (b[2] - a[2]) * T[i][1] <= 0:
                        raise wc.ConstructError('the strip edge at lateral %.1f m folds over at station %d (the curve radius there is '
                                                'smaller than that offset): use smaller verges / width or a wider curve' % (o, i))
                x = wc.self_intersections([list(wc.offset_pt(S[i], T[i], o)) for i in range(n)], True)
                if x:
                    raise wc.ConstructError('the strip edge at lateral %.1f m crosses itself (segments %s): the verges of opposite sides '
                                            'would overlap - use smaller verges or move the control points apart' % (o, x[:2]))
            walls = (wc.wall_strip(S, T, True, -hw, -1, req['wall_height'], t, req['wall_mat'], req['back_mat'], y=y0) +
                     wc.wall_strip(S, T, True, hw, 1, req['wall_height'], t, req['wall_mat'], req['back_mat'], y=y0))
            verges = []
            if req['verge_out'] > 0:
                verges += wc.verge_strip(S, T, True, -(hw + t + req['verge_out']), -(hw + t), req['verge_mat'], y=y0)
            if req['verge_in'] > 0:
                verges += wc.verge_strip(S, T, True, hw + t, hw + t + req['verge_in'], req['verge_mat'], y=y0)
            stations = wc.stations_from(S, T, hw, t, req['verge_out'], req['verge_in'], y0)
            corners = wc.heading_corners(S, T, sps, n // sps)
            start, grid, cps = wc.start_objects(S, L, y0, req['checkpoints'])
            per = collections.defaultdict(list)             # plan points of the generated faces per station step (unit fitting)
            for i, (_m, cs) in enumerate(road):
                per[i] += [(c[0][0], c[0][2]) for c in cs]
            half = len(walls) // 2
            for j, (_m, cs) in enumerate(walls):
                per[(j % half) // 3] += [(c[0][0], c[0][2]) for c in cs]
            nv = len(verges)
            for j, (_m, cs) in enumerate(verges):
                per[j % n if nv else 0] += [(c[0][0], c[0][2]) for c in cs]
            units = []
            for k in range(req['n_units']):
                a, b = k * spu, ((k + 1) * spu) % n
                pts = [q for i in range(a, a + spu) for q in per[i]]
                lat, m = wc.fit_lateral(stations, a, b, pts)
                units.append({'cut_from': a, 'cut_to': b, 'lateral': lat, 'chord_normal': m})
        except wc.ConstructError as e:
            raise EditError('race layout refused: %s. Nothing changed' % e)
        d = self.desc()
        values = {'stations': stations, 'stations_per_slice': sps, 'units': units, 'route': {'lanes': wc.LANES, 'corners': corners},
                  'grid': grid, 'start_line': start, 'checkpoints': cps,
                  'traffic': wc.traffic_for(n, hw) if req['traffic'] else None, 'loop_length': round(L, 4), 'closed': True,
                  'wall_gaps': [], 'pvs': {'mode': 'all'}}
        newdesc = desc_splice(self.cur, values)
        C = self.constructs()
        _l, groups, _v = obj_index(self.obj_cur)
        replace = [x['i'] for x in groups] if req['replace'] == 'all' else sorted(g for c in C.values() if c['meta'].get('route')
                                                                                  for g in c['groups'])
        rid = 'route'
        meta = dict(req, kind='race', id=rid + '_road', route=True)
        del meta['replace']
        parts = [(road, meta), (walls, {'kind': 'wall', 'id': rid + '_walls', 'route': True}),
                 (verges, {'kind': 'verge', 'id': rid + '_verges', 'route': True})]
        parts = [x for x in parts if x[0]]
        after, blk = self._block_bytes(None, None, replace, parts=parts)
        planned = [f for pf, _m in parts for f in pf]
        # kept geometry (replace "route") must keep its area inside the NEW unit regions
        cov0, cov1 = self.coverage(self.obj_cur), self.coverage(after, newdesc)
        lines0, groups0, _v0 = obj_index(self.obj_cur)
        fl0 = sorted(li for x in groups0 for li in x['faces'])
        rmset = set(blk['rm'])
        kept = [i for i, li in enumerate(fl0) if li not in rmset]
        lost = []
        for j, i in enumerate(kept):
            f0, f1 = cov0['faces'][i], cov1['faces'][j]
            if f1['kept'] < f0['kept'] - (CLIP_TOL_M2 + 1e-9 * f0['area']):
                lost.append({'line': fl0[i] + 1, 'material': f0['mat'], 'kept_before_m2': round(f0['kept'], 4),
                             'kept_after_m2': round(f1['kept'], 4), 'corners': [list(p) for p in f0['pts']]})
        if lost:
            e = EditError('refused: %d kept face(s) would lie outside the new unit regions (Build would drop them): %s. Move / delete '
                          'that geometry or keep the layout. Nothing changed' % (len(lost), '; '.join(
                              'face line %d (%s) keeps %.3f of %.3f m2' % (x['line'], x['material'], x['kept_after_m2'],
                                                                          x['kept_before_m2']) for x in lost[:4])))
            e.detail = {'lost_faces': lost[:200]}
            raise e
        rc = self.race_check(after, newdesc)
        if not rc['structural_ok']:
            bad = [c for c in rc['structural'] if not c['ok']]
            e = EditError('refused: the generated layout fails structural check(s) %s: %s. Nothing changed' % (
                ', '.join(c['check'] for c in bad), json.dumps(bad[0]['detail'])[:300]))
            e.detail = {'structural': rc['structural'], 'route_lines': rc['route_lines']}
            raise e
        y = y0 + 0.6
        regions = [{'unit': u.k, 'corners': [[c[0], y, c[1]] for c in u.corners], 'changed': True} for u in cov1['units']]
        summary = {'race': True, 'replace': req['replace'], 'replaced_groups': len(replace), 'kept_faces': len(kept),
                   'loop_length_m': round(L, 2), 'stations': n, 'stations_per_unit': spu, 'units': req['n_units'],
                   'corners': corners, 'faces': {'road': len(road), 'walls': len(walls), 'verges': len(verges)},
                   'start_line': start, 'grid': grid, 'checkpoints': cps, 'traffic': 'authored (demo shape)' if req['traffic'] else 'donor',
                   'structural': rc['structural'], 'runtime': self.RUNTIME_NOTE, 'regions': regions,
                   'route_lines': rc['route_lines'], 'markers': rc['markers'],
                   'new_faces': [[list(q) for q in Pf] for Pf in blk['faces'][:3000]],
                   'summary_lines': ['race layout: %.1f m loop, %d stations, %d units of %d stations, %d corner record(s), road %d / wall '
                                     '%d / verge %d faces; replaces %d face group(s), keeps %d face(s)' % (
                                         L, n, req['n_units'], spu, len(corners), len(road), len(walls), len(verges), len(replace),
                                         len(kept))] + rc['summary_lines']}
        return {'after': after, 'blk': blk, 'planned': planned, 'newdesc': newdesc, 'keys': set(values), 'kept': kept,
                'summary': summary}

    def race_layout_preview(self, points=None, width=14.0, material='asphalt', wall_height=1.5, wall_thick=0.6, wall_mat='wall',
                            back_mat='wallback', verge_out=10.0, verge_in=8.0, verge_mat='grass', n_units=17, checkpoints=6,
                            traffic=True, replace='route'):
        """v0.25: a race layout from closed control points (one height): road + walls on both sides + verges, and the route
        (stations, corners, 5 lanes), units, grid, start line, checkpoints, traffic - WITHOUT changing anything"""
        req = self._race_req(points, width, material, wall_height, wall_thick, wall_mat, back_mat, verge_out, verge_in, verge_mat,
                             n_units, checkpoints, traffic, replace)
        plan = self._race_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('race', req), note='preview only: nothing changed')

    def race_layout(self, points=None, width=14.0, material='asphalt', wall_height=1.5, wall_thick=0.6, wall_mat='wall',
                    back_mat='wallback', verge_out=10.0, verge_in=8.0, verge_mat='grass', n_units=17, checkpoints=6, traffic=True,
                    replace='route', preview_key=None):
        """v0.25: apply a previewed race layout: the OBJ blocks (replace "all": every face group; "route": the earlier layout's
        blocks) and the description's route values change in ONE undo entry (description + OBJ); exact re-reads of both, the
        clip rule for the new faces, the kit's build_units dry run on the new pair"""
        req = self._race_req(points, width, material, wall_height, wall_thick, wall_mat, back_mat, verge_out, verge_in, verge_mat,
                             n_units, checkpoints, traffic, replace)
        if preview_key != self._cons_key('race', req):
            raise EditError('NEEDS PREVIEW: preview this race layout first (route, units, structural checks) and apply it with its '
                            'preview_key')
        plan = self._race_plan(req)
        after, nd = plan['after'], plan['newdesc']
        exact = self._check_block(self.obj_cur, after, plan['blk'], plan['planned'])
        exact_d = self._check_desc_splice(self.cur, nd, plan['keys'])
        lines1, groups1, vl1 = obj_index(after)
        gof1 = {li: x['i'] for x in groups1 for li in x['faces']}
        clip = self._clip_added(self.obj_cur, after, len(plan['kept']), [None] * len(plan['planned']), gof1, 'race',
                                kept=plan['kept'], desc_bytes=nd, round_tol=True)
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(after, nd)
        S = plan['summary']
        newg = [x['i'] for x in groups1[len(groups1) - plan['blk']['groups_added']:]]
        label = 'race layout (%s): %.1f m loop, %d units, %d checkpoints' % (req['replace'], S['loop_length_m'], S['units'],
                                                                            req['checkpoints'])
        self._push('both', label, (nd, after), kind='race', index=newg)
        warn = []
        d = self.desc()
        if 'generator' in d:
            warn.append('the description\'s "generator" block still describes the demo it was made from (preserved; trackbuild does '
                        'not read it)')
        return dict(S, ok=True, label=label, groups=newg, exact=exact, exact_desc=exact_d, clipping=clip, warnings=warn,
                    regenerated=self._regen_report(base, regen))

    def _points_req(self, checkpoints):
        st = self.desc().get('stations') or []
        n = len(st)
        if not (isinstance(checkpoints, list) and 1 <= len(checkpoints) <= 12 and
                all(isinstance(i, int) and not isinstance(i, bool) and 0 < i < n for i in checkpoints)):
            raise EditError('checkpoints must be a list of 1..12 station indices (1..%d; station 0 = the start line)' % (n - 1))
        return {'checkpoints': list(checkpoints)}

    def _points_plan(self, req):
        d = self.desc()
        st = d['stations']
        old = d.get('checkpoints') or []
        width = old[0]['width'] if old and isinstance(old[0], dict) and 'width' in old[0] else 45.0
        cps = [{'pos': [round(st[i]['p'][0], 3), st[i]['p'][1], round(st[i]['p'][2], 3)], 'normal': [st[i]['t'][0], 0.0, st[i]['t'][1]],
                'width': width} for i in req['checkpoints']]
        nd = desc_splice(self.cur, {'checkpoints': cps})
        rc = self.race_check(self.obj_cur, nd)
        lap = next(c for c in rc['structural'] if c['check'] == 'lap order')
        if not lap['ok']:
            e = EditError('refused: the checkpoints are not in lap order (start line, then increasing route order, >= 10 stations '
                          'apart): %s. Nothing changed' % json.dumps(lap['detail'])[:240])
            e.detail = {'structural': rc['structural']}
            raise e
        return {'newdesc': nd, 'summary': {'checkpoints': cps, 'structural': rc['structural'], 'runtime': self.RUNTIME_NOTE,
                                            'markers': [c['pos'] for c in cps], 'route_lines': rc['route_lines'],
                                            'summary_lines': ['checkpoints at stations %s (lap order ok)' % req['checkpoints']] +
                                            rc['summary_lines']}}

    def race_points_preview(self, checkpoints=None):
        """v0.25: checkpoints at the given stations (lap order checked), WITHOUT changing anything"""
        req = self._points_req(checkpoints)
        plan = self._points_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('points', req), note='preview only: nothing changed')

    def race_points(self, checkpoints=None, preview_key=None):
        """v0.25: apply previewed checkpoints: only the description's "checkpoints" value changes; one undo entry. The start line
        stays at the route origin (station 0); grid slots / start line / single checkpoints move with the v0.14 start edit."""
        req = self._points_req(checkpoints)
        if preview_key != self._cons_key('points', req):
            raise EditError('NEEDS PREVIEW: preview these checkpoints first and apply them with the preview_key')
        plan = self._points_plan(req)
        exact = self._check_desc_splice(self.cur, plan['newdesc'], {'checkpoints'})
        label = 'checkpoints at stations %s' % req['checkpoints']
        self._push('desc', label, plan['newdesc'], kind='points', index=None)
        return dict(plan['summary'], ok=True, label=label, exact=exact)

    # ---------------- v0.26 terrain / scenery: terrain patches, barriers, reusable geometry (prefabs) as construction blocks
    def _mat_ok(self, m, role):
        d = self.desc()
        ok = [n for n in (d.get('rows') or []) if n in (d.get('materials') or {}) and
              not set(d['materials'][n]) - {'texture', 'surface', 'collide', 'car_solid'}]
        if m not in ok:
            raise EditError('%s material %r refused: an EXISTING material with a render row (%s)' % (role, m, ', '.join(ok)))
        return m

    SCENERY_KEYS = {'terrain': {'rect', 'heights', 'cell', 'material', 'id'},
                    'barrier': {'points', 'closed', 'height', 'thick', 'step', 'side', 'front', 'back', 'id'},
                    'prefab': {'name', 'position', 'angle', 'id'}}

    def _scenery_req(self, kind, a):
        if kind in self.SCENERY_KEYS and set(a) - self.SCENERY_KEYS[kind]:
            raise EditError('%s: unknown argument(s) %s' % (kind, ', '.join(sorted(set(a) - self.SCENERY_KEYS[kind]))))
        num = lambda v, lo, hi: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi  # noqa: E731
        if kind == 'terrain':
            r = a.get('rect')
            if not (isinstance(r, list) and len(r) == 4 and all(num(v, -1e6, 1e6) for v in r)):
                raise EditError('terrain rect must be [x0, z0, x1, z1] metres')
            h = a.get('heights')
            if not (num(h, -1e5, 1e5) or (isinstance(h, list) and len(h) == 4 and all(num(v, -1e5, 1e5) for v in h))):
                raise EditError('terrain heights: one height or four corner heights [x0z0, x1z0, x1z1, x0z1] (metres)')
            if not num(a.get('cell', 10.0), 1, 100):
                raise EditError('terrain cell %r refused: 1..100 m' % (a.get('cell'),))
            return {'kind': kind, 'rect': [float(v) for v in r], 'heights': h if isinstance(h, list) else float(h),
                    'cell': float(a.get('cell', 10.0)), 'material': self._mat_ok(a.get('material'), 'terrain'), 'id': a.get('id')}
        if kind == 'barrier':
            if not isinstance(a.get('closed', False), bool):
                raise EditError('closed must be true or false')
            try:
                P = wc.check_points(a.get('points'), a.get('closed', False))
            except wc.ConstructError as e:
                raise EditError('barrier refused: %s' % e)
            for name, v, lo, hi in (('height', a.get('height', 1.5), 0.3, 30), ('thickness', a.get('thick', 0.6), 0.1, 5),
                                    ('step', a.get('step', 2.0), 0.5, 20)):
                if not num(v, lo, hi):
                    raise EditError('barrier %s %r refused: %g..%g m' % (name, v, lo, hi))
            if a.get('side', 1) not in (1, -1):
                raise EditError('barrier side must be 1 (the body extends towards n+) or -1')
            return {'kind': kind, 'points': P, 'closed': a.get('closed', False), 'height': float(a.get('height', 1.5)),
                    'thick': float(a.get('thick', 0.6)), 'step': float(a.get('step', 2.0)), 'side': a.get('side', 1),
                    'front': self._mat_ok(a.get('front', 'wall'), 'barrier front'), 'back': self._mat_ok(a.get('back', 'wallback'), 'barrier back'),
                    'id': a.get('id')}
        if kind == 'prefab':
            name = a.get('name')
            if not (isinstance(name, str) and re.match(r'^[A-Za-z0-9_-]{1,40}$', name)):
                raise EditError('prefab name %r: 1..40 letters, digits, _ or -' % (name,))
            pos = a.get('position')
            if not (isinstance(pos, list) and len(pos) == 3 and all(num(v, -1e6, 1e6) for v in pos)):
                raise EditError('prefab position must be [x, y, z] metres')
            if not num(a.get('angle', 0.0), -360, 360):
                raise EditError('prefab angle: -360..360 degrees')
            pf = self._prefab_read(name)
            for m in sorted({f[0] for f in pf['faces']}):
                self._mat_ok(m, 'prefab')
            return {'kind': kind, 'name': name, 'position': [float(v) for v in pos], 'angle': float(a.get('angle', 0.0)),
                    'prefab_sha256': pf['sha256'], 'id': a.get('id')}
        raise EditError('scenery kind %r refused: terrain / barrier / prefab' % (kind,))

    def _scenery_faces(self, req):
        try:
            if req['kind'] == 'terrain':
                x0, z0, x1, z1 = req['rect']
                return wc.terrain_patch(x0, z0, x1, z1, req['heights'], req['cell'], req['material'])
            if req['kind'] == 'barrier':
                S, _L = wc.sample(req['points'], req['closed'], step=req['step'])
                T = wc.tangents(S, req['closed'])
                if req['closed']:
                    r, at = wc.min_radius(S, True)
                    if r < req['thick'] * 1.5:
                        raise wc.ConstructError('the barrier turns tighter (radius %.2f m at sample %d) than its thickness allows' % (r, at))
                x = wc.self_intersections(S, req['closed'])
                if x:
                    raise wc.ConstructError('the barrier crosses itself (segments %s)' % x[:2])
                return wc.wall_strip(S, T, req['closed'], 0.0, req['side'], req['height'], req['thick'], req['front'], req['back'])
            pf = self._prefab_read(req['name'])
            faces = [(m, [(tuple(p), tuple(uv), tuple(n), tuple(c)) for p, uv, n, c in cs]) for m, cs in pf['faces']]
            return wc.transform_faces(faces, req['position'], req['angle'], (0.0, 0.0, 0.0))
        except wc.ConstructError as e:
            raise EditError('%s refused: %s. Nothing changed' % (req['kind'], e))

    def _scenery_plan(self, req):
        faces = self._scenery_faces(req)
        C = self.constructs()
        if req.get('id') is not None and (req['id'] not in C or C[req['id']]['meta'].get('kind') != req['kind']):
            raise EditError('%s %r does not exist (to re-generate one, give its id)' % (req['kind'], req['id']))
        rid = req.get('id') or self._new_id(req['kind'])
        meta = dict({k: v for k, v in req.items() if k != 'id'}, id=rid)
        repl = C[req['id']]['groups'] if req.get('id') else []
        after, blk = self._block_bytes(faces, meta, repl)
        warn = self._route_floor_warnings(blk['faces'])
        return {'after': after, 'blk': blk, 'planned': faces, 'id': rid,
                'summary': {'scenery': req['kind'], 'id': rid, 'faces': len(faces), 'replaces': req.get('id'),
                            'v_added': blk['v_added'], 'vt_added': blk['vt_added'], 'vn_added': blk['vn_added'],
                            'removed_faces': blk['removed_faces'], 'warnings': warn,
                            'new_faces': [[list(q) for q in P] for P in blk['faces'][:3000]],
                            'summary_lines': ['%s %s: %d faces%s; %d v + %d vt + %d vn lines added' % (
                                req['kind'], rid, len(faces), ' (re-generated)' if req.get('id') else '', blk['v_added'],
                                blk['vt_added'], blk['vn_added'])] + ['WARNING: ' + w for w in warn]}}

    def scenery_preview(self, kind=None, **a):
        """v0.26: a terrain patch / barrier / prefab copy as a construction block, WITHOUT changing anything"""
        req = self._scenery_req(kind, a)
        plan = self._scenery_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._cons_key('scenery', req), note='preview only: nothing changed')

    def scenery(self, kind=None, preview_key=None, **a):
        """v0.26: apply a previewed terrain patch / barrier / prefab copy: a tagged block appended at the end of the OBJ (an existing
        id re-generates its block); exact re-read, clip rule, trackbuild dry run, one undo entry"""
        req = self._scenery_req(kind, a)
        if preview_key != self._cons_key('scenery', req):
            raise EditError('NEEDS PREVIEW: preview this %s first and apply it with its preview_key' % kind)
        plan = self._scenery_plan(req)
        S = plan['summary']
        label = '%s %s %s (%d faces)' % ('re-generate' if req.get('id') else 'new', kind, plan['id'], S['faces'])
        r = self._apply_block(plan, label, kind, S['faces'])
        return dict(S, **r)

    # prefabs: files in Workbench state (never inside a project; reusable across projects); positions relative to their centre
    def _prefab_dir(self):
        return self.cfg.get('prefabs') or os.path.join(self.cfg['state'], 'prefabs')   # tests pass their own folder

    def _prefab_read(self, name):
        p = os.path.join(self._prefab_dir(), name + '.prefab.json')
        if not os.path.isfile(p):
            raise EditError('prefab %r does not exist (%s)' % (name, ', '.join(self.prefabs()['prefabs']) or 'none saved yet'))
        raw = open(p, 'rb').read()
        try:
            d = json.loads(raw.decode('utf-8'))
            assert d.get('format') == 'workbench-prefab 1' and isinstance(d.get('faces'), list) and d['faces']
            for m, cs in d['faces']:
                assert isinstance(m, str) and len(cs) in (3, 4) and all(len(c) == 4 and len(c[0]) == 3 and len(c[1]) == 2 and
                                                                        len(c[2]) == 3 and len(c[3]) == 3 for c in cs)
        except (ValueError, AssertionError, TypeError):
            raise EditError('prefab %r is not a valid workbench-prefab 1 file: refused' % name)
        return dict(d, sha256=hashlib.sha256(raw).hexdigest())

    def prefabs(self):
        p = self._prefab_dir()
        return {'ok': True, 'prefabs': sorted(f[:-len('.prefab.json')] for f in os.listdir(p) if f.endswith('.prefab.json')) if os.path.isdir(p) else [],
                'folder': p}

    def prefab_save(self, groups=None, name=None, overwrite=False):
        """v0.26: save the selected face groups as a reusable prefab (Workbench state; the project is not changed): every face with
        its material, positions relative to the bounding-box centre of the selection (x, z) and its lowest point (y), uv,
        normals, colours, as the kit reader reads them"""
        if not (isinstance(name, str) and re.match(r'^[A-Za-z0-9_-]{1,40}$', name)):
            raise EditError('prefab name %r: 1..40 letters, digits, _ or -' % (name,))
        X = self._selection(groups)
        K = kit_trackbuild(self.cfg)
        root = os.path.join(self.cfg['state'], 'geomcheck')
        os.makedirs(root, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='pf_', dir=root)
        try:
            p = os.path.join(tmp, 'src.obj')
            with open(p, 'wb') as f:
                f.write(self.obj_cur)
            obj = K['io'].read_obj(p)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        fl = sorted(li for x in X['groups'] for li in x['faces'])
        faces = [obj['faces'][i] for i, li in enumerate(fl) if li in X['F']]
        P = [q[0] for _m, fv in faces for q in fv]
        c = [(min(q[0] for q in P) + max(q[0] for q in P)) / 2, min(q[1] for q in P), (min(q[2] for q in P) + max(q[2] for q in P)) / 2]
        out = {'format': 'workbench-prefab 1', 'name': name, 'from': {'project': self.project, 'groups': X['sel']},
               'origin': c, 'faces': [[m, [[[q[0][k] - c[k] for k in range(3)], list(q[1]), list(q[2]), list(q[3])] for q in fv]]
                                      for m, fv in faces]}
        os.makedirs(self._prefab_dir(), exist_ok=True)
        dst = os.path.join(self._prefab_dir(), name + '.prefab.json')
        if os.path.exists(dst) and overwrite is not True:
            raise EditError('prefab %r exists: choose another name or overwrite explicitly' % name)
        with open(dst + '.wb_tmp', 'w', encoding='utf-8') as f:
            json.dump(out, f)
        os.replace(dst + '.wb_tmp', dst)
        return {'ok': True, 'prefab': name, 'faces': len(faces), 'materials': sorted({m for m, _ in faces}), 'origin': c, 'file': dst,
                'note': 'saved in Workbench state (not in the project); insert copies with the prefab tool'}

    # ---------------- v0.23+ construction dispatcher (server /api/layout): {op, ...named arguments}
    LAYOUT = {'units_preview': 'units_preview', 'units': 'units_edit', 'road_preview': 'road_preview', 'road': 'road',
              'race_check': 'race_check_view', 'race_layout_preview': 'race_layout_preview', 'race_layout': 'race_layout',
              'race_points_preview': 'race_points_preview', 'race_points': 'race_points',
              'scenery_preview': 'scenery_preview', 'scenery': 'scenery', 'prefab_save': 'prefab_save', 'prefabs': 'prefabs'}

    def layout(self, body):
        if not isinstance(body, dict) or body.get('op') not in self.LAYOUT:
            raise EditError('layout op %r refused: %s' % ((body or {}).get('op') if isinstance(body, dict) else body,
                                                           ' / '.join(sorted(self.LAYOUT))))
        fn = getattr(self, self.LAYOUT[body['op']])
        import inspect
        sig = inspect.signature(fn).parameters
        names = set(sig)
        extra = sorted(set(body) - names - {'op'})
        if extra and not any(x.kind == inspect.Parameter.VAR_KEYWORD for x in sig.values()):
            raise EditError('layout op %s: unknown argument(s) %s' % (body['op'], ', '.join(extra)))
        return fn(**{k: v for k, v in body.items() if k != 'op'})

    # ---------------- v0.23 unit regions: edit lateral bounds, fit, split (add), merge, move a cut; coverage + capacity preview
    UNIT_OPS = ('lateral', 'fit', 'split', 'merge', 'cut', 'include')

    def _units_req(self, op, unit, lateral=None, station=None, rect=None):
        d = self.desc()
        U, n = d.get('units') or [], len(d.get('stations') or [])
        ii = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
        if op not in self.UNIT_OPS:
            raise EditError('unit operation %r refused: %s' % (op, ' / '.join(self.UNIT_OPS)))
        if op == 'include':                                 # v0.26: grow the units whose cuts span part of a plan rectangle
            if not (isinstance(rect, list) and len(rect) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                                                                      math.isfinite(v) for v in rect) and rect[0] < rect[2] and rect[1] < rect[3]):
                raise EditError('include needs rect [x0, z0, x1, z1] metres (x0 < x1, z0 < z1)')
            if (rect[2] - rect[0]) * (rect[3] - rect[1]) > 4e6:
                raise EditError('include rect larger than 4 km2: refused')
            return {'op': op, 'unit': 0, 'rect': [float(v) for v in rect]}
        if not ii(unit) or not 0 <= unit < len(U):
            raise EditError('unit %r does not exist (0..%d)' % (unit, len(U) - 1))
        req = {'op': op, 'unit': unit}
        if op == 'lateral':
            if not (isinstance(lateral, list) and len(lateral) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                                            and math.isfinite(v) and abs(v) <= 5000 for v in lateral)
                    and lateral[0] < lateral[1]):
                raise EditError('lateral bounds must be [lo, hi] metres along the unit chord normal, lo < hi, |value| <= 5000')
            req['lateral'] = [float(v) for v in lateral]
        if op in ('split', 'cut'):
            if not ii(station) or not 0 <= station < n:
                raise EditError('station %r does not exist (0..%d)' % (station, n - 1))
            req['station'] = station
        if op in ('merge', 'cut') and unit == len(U) - 1:
            raise EditError('unit %d is the last unit: merge / move the cut with its predecessor (unit %d) instead - the unit list '
                            'starts at unit 0 (the start cut stays)' % (unit, unit - 1))
        return req

    def _units_key(self, req):
        return hashlib.sha256(('%s|units|%s' % (self.content_sha(), json.dumps(req, sort_keys=True))).encode()).hexdigest()[:16]

    def _units_plan(self, req):
        """resolve + check a unit-region edit WITHOUT changing anything. Split / merge / cut / fit recompute the chord normal
        (the generator's rule) and fit the lateral bounds to the route corridor and the geometry the affected old units hold
        (clipped between the new cuts) + 0.25 m. Refused: a unit count outside the kit's range (4..17 pvs all, 4..162 computed),
        a region the kit cannot build (not convex / cuts not shared), ANY face keeping less area inside the union of the unit
        regions than before (unintended geometry loss: Build would drop it silently), a drivable sample of the kit validator
        (V2_drivable_coverage) not in exactly one unit, a grid slot not in exactly one unit, and anything build_units refuses
        (slots, LOD, PVS ring)."""
        if self.obj_cur is None:
            raise EditError('the OBJ did not pass the input check: unit edits need a readable OBJ (coverage)')
        K = kit_trackbuild(self.cfg)
        UN = K['units']
        d = self.desc()
        st, U0 = d['stations'], d['units']
        n, k = len(st), req['unit']
        U = json.loads(json.dumps(U0))
        cov0 = self.coverage(self.obj_cur)

        def span_len(a, b):
            return (b - a) % n or n

        def inner(m, a, b):
            return 0 < (m - a) % n < span_len(a, b)

        def lane_start(a):
            t, p = st[a]['t'], st[a]['p']
            L = math.hypot(t[0], t[1])
            return (t[0] / L, t[1] / L, (t[0] * p[0] + t[1] * p[2]) / L)

        def lane_end(b):
            a, c, w = lane_start(b)
            return (-a, -c, -w)

        def pts_of(old, a, b):
            out = []
            for f in cov0['faces']:
                for kk in old:
                    q = f['pieces'].get(kk)
                    if q:
                        q = _clip_lanes(UN, q, [lane_start(a), lane_end(b)])
                        out += [(v[0][0], v[0][2]) for v in q]
            return out

        def refit(u, old):
            u['lateral'], u['chord_normal'] = wc.fit_lateral(st, u['cut_from'], u['cut_to'], pts_of(old, u['cut_from'], u['cut_to']))
        op = req['op']
        try:
            if op == 'lateral':
                U[k]['lateral'] = req['lateral']
            elif op == 'fit':
                refit(U[k], [k])
            elif op == 'include':
                x0, z0, x1, z1 = req['rect']
                rpoly = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]

                def halfclip(P, h):
                    # exact clip of a convex polygon by the half plane h[0] x + h[1] z - h[2] >= 0 (Sutherland-Hodgman)
                    out = []
                    for i in range(len(P)):
                        p, q = P[i], P[(i + 1) % len(P)]
                        fp, fq = h[0] * p[0] + h[1] * p[1] - h[2], h[0] * q[0] + h[1] * q[1] - h[2]
                        if fp >= 0:
                            out.append(p)
                        if (fp >= 0) != (fq >= 0):
                            t = fp / (fp - fq)
                            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
                    return out
                grown = []
                for kk, u in enumerate(U):
                    a, b = lane_start(u['cut_from']), lane_end(u['cut_to'])
                    # v0.27: the exact part of the rectangle between this unit's cuts (v0.26 sampled a 1 m grid and missed
                    # wedges thinner than the grid: found by test_trackedit_v27 w01, one terrain cell losing 0.25 m2).
                    # The lateral extremes of a convex polygon lie at its vertices.
                    pts = halfclip(halfclip(rpoly, a), b)
                    if len(pts) < 3:
                        continue
                    A = st[u['cut_from']]['p']
                    m = u['chord_normal']
                    dd = [(q[0] - A[0]) * m[0] + (q[1] - A[2]) * m[1] for q in pts]
                    lo, hi = min(dd) - 0.25, max(dd) + 0.25
                    det = a[0] * b[1] - a[1] * b[0]
                    if abs(det) > 1e-12:                    # the cut lines meet at an apex: the region quad stays convex only
                        X = ((a[2] * b[1] - a[1] * b[2]) / det, (a[0] * b[2] - a[2] * b[0]) / det)   # short of it (kit rule)
                        dap = (X[0] - A[0]) * m[0] + (X[1] - A[2]) * m[1]
                        if dap >= max(dd) - 1e-9:
                            hi = min(hi, dap - 1e-3)
                        elif dap <= min(dd) + 1e-9:
                            lo = max(lo, dap + 1e-3)
                    lo, hi = min(u['lateral'][0], math.floor(lo * 1e4) / 1e4 if lo < u['lateral'][0] else lo), \
                        max(u['lateral'][1], math.ceil(hi * 1e4) / 1e4 if hi > u['lateral'][1] else hi)
                    if [lo, hi] != u['lateral']:
                        u['lateral'] = [lo, hi]
                        grown.append(kk)
                if not grown:
                    raise EditError('include: every unit whose cuts span the rectangle already holds it - nothing to edit')
            elif op == 'split':
                a, b, m = U[k]['cut_from'], U[k]['cut_to'], req['station']
                if not inner(m, a, b):
                    raise EditError('station %d is not strictly inside unit %d (stations %d .. %d): a split needs a station between '
                                    'its cuts' % (m, k, a, b))
                u1, u2 = dict(U[k], cut_to=m), dict(U[k], cut_from=m)
                refit(u1, [k])
                refit(u2, [k])
                U[k:k + 1] = [u1, u2]
            elif op == 'merge':
                u = dict(U[k], cut_to=U[k + 1]['cut_to'])
                refit(u, [k, k + 1])
                U[k:k + 2] = [u]
            else:
                a, b, m = U[k]['cut_from'], U[k + 1]['cut_to'], req['station']
                if not inner(m, a, b) or m == U[k]['cut_to']:
                    raise EditError('station %d is not a new cut strictly between station %d and station %d (units %d / %d)' % (
                        m, a, b, k, k + 1))
                U[k]['cut_to'] = U[k + 1]['cut_from'] = m
                refit(U[k], [k, k + 1])
                refit(U[k + 1], [k, k + 1])
        except wc.ConstructError as e:
            raise EditError('refused: %s. Nothing changed' % e)
        pvs = (d.get('pvs') or {'mode': 'all'})['mode']
        lim = (4, 17) if pvs == 'all' else (4, 162)
        if not lim[0] <= len(U) <= lim[1]:
            raise EditError('refused: %d units; the kit builds %d..%d units with pvs %s (capacity). Nothing changed' % (
                len(U), lim[0], lim[1], pvs))
        after = desc_splice(self.cur, {'units': U})
        cov1 = self.coverage(self.obj_cur, after)
        lines, groups, _vl = obj_index(self.obj_cur)
        fl = sorted(li for x in groups for li in x['faces'])
        gof = {li: x['i'] for x in groups for li in x['faces']}
        lost, gained = [], 0
        for i, (f0, f1) in enumerate(zip(cov0['faces'], cov1['faces'])):
            tol = CLIP_TOL_M2 + 1e-9 * f0['area']
            if f1['kept'] < f0['kept'] - tol:
                lost.append({'line': fl[i] + 1, 'group': gof[fl[i]], 'material': f0['mat'], 'area_m2': round(f0['area'], 4),
                             'kept_before_m2': round(f0['kept'], 4), 'kept_after_m2': round(f1['kept'], 4),
                             'corners': [list(p) for p in f0['pts']], 'units': sorted(f1['pieces'])})
            elif f1['kept'] > f0['kept'] + tol:
                gained += 1
        units1 = cov1['units']
        y0 = st[0]['p'][1]
        regions = [{'unit': u.k, 'corners': [[c[0], y0 + 0.6, c[1]] for c in u.corners],
                    'changed': u.k >= len(U0) or json.dumps(U[u.k], sort_keys=True) != json.dumps(U0[u.k], sort_keys=True)}
                   for u in units1]
        detail = {'lost_faces': lost[:200], 'regions': regions}
        if lost:
            e = EditError('refused: unintended geometry loss - %d face(s) would keep less area inside the unit regions (Build drops '
                          'what lies outside every region, silently): %s. Widen the lateral bounds or choose other cuts. Nothing '
                          'changed' % (len(lost), '; '.join('face line %d (group %d, %s) keeps %.3f of %.3f m2' % (
                              x['line'], x['group'], x['material'], x['kept_after_m2'], x['kept_before_m2']) for x in lost[:4])))
            e.detail = detail
            raise e
        bad = []
        for x, z, i in wc.drivable_samples(st):
            h = [u.k for u in units1 if u.inside(x, z)]
            if len(h) != 1:
                bad.append({'station': i, 'p': [round(x, 2), y0, round(z, 2)], 'units': h})
        if bad:
            e = EditError('refused: %d drivable sample(s) of the kit validator (V2_drivable_coverage) would not lie in exactly one '
                          'unit (first: station %d at [%s, %s] in units %s). Nothing changed' % (
                              len(bad), bad[0]['station'], bad[0]['p'][0], bad[0]['p'][2], bad[0]['units']))
            detail['samples'] = bad[:50]
            e.detail = detail
            raise e
        for gi, g in enumerate(d.get('grid') or []):
            h = [u.k for u in units1 if u.inside(g['pos'][0], g['pos'][2])]
            if len(h) != 1:
                raise EditError('refused: grid slot %d would lie in %d unit regions (the kit needs exactly one: its start unit). '
                                'Nothing changed' % (gi, len(h)))
        try:
            base = self.regenerate(self.obj_cur)
        except EditError:
            base = None
        regen = self.regenerate(self.obj_cur, after)
        cap = regen['capacity']
        worst = max(max(c['mesh_slot_pct'], c['lod_slot_pct'], c['vertex_pct'], c['record_pct']) for c in cap)
        nsamp = len(wc.drivable_samples(st))
        summary = {'op': op, 'unit': k, 'units_before': len(U0), 'units_after': len(U), 'pvs': pvs,
                   'units': [dict(unit=i, cut_from=u['cut_from'], cut_to=u['cut_to'], lateral=u['lateral'],
                                  chord_normal=[round(x, 6) for x in u['chord_normal']]) for i, u in enumerate(U)],
                   'changed_units': [r['unit'] for r in regions if r['changed']], 'regions': regions,
                   'coverage': {'faces': len(cov0['faces']), 'faces_losing_area': 0, 'faces_gaining_area': gained,
                                'kept_m2': [round(sum(f['kept'] for f in cov0['faces']), 3), round(sum(f['kept'] for f in cov1['faces']), 3)],
                                'drivable_samples_in_one_unit': nsamp, 'grid_slots_in_one_unit': len(d.get('grid') or [])},
                   'capacity': cap, 'capacity_worst_pct': worst, 'slots': regen['slots'],
                   'checked': 'kit make_units (convex, shared cuts), unit count %d..%d (pvs %s), no face loses area, the kit '
                              'validator\'s drivable samples and every grid slot in exactly one unit, build_units dry run '
                              '(slots, LOD, PVS)' % (lim[0], lim[1], pvs)}
        return {'after': after, 'regen': regen, 'base': base, 'summary': summary}

    def units_preview(self, unit_op=None, unit=None, lateral=None, station=None, rect=None):
        """what a unit-region edit would do, WITHOUT changing anything (regions, coverage, capacity); its preview_key must
        accompany units_edit"""
        req = self._units_req(unit_op, unit, lateral, station, rect)
        plan = self._units_plan(req)
        return dict(plan['summary'], ok=True, preview_key=self._units_key(req), note='preview only: nothing changed')

    def units_edit(self, unit_op=None, unit=None, lateral=None, station=None, rect=None, preview_key=None):
        """v0.23: apply a previewed unit-region edit: only the description's "units" value changes (spliced; every other byte
        kept); one undo entry; the kit regenerates streaming / collision copies / bounds / PVS / LOD from it at Build"""
        req = self._units_req(unit_op, unit, lateral, station, rect)
        if preview_key != self._units_key(req):
            raise EditError('NEEDS PREVIEW: preview this unit edit first (regions, coverage, capacity) and apply it with its '
                            'preview_key')
        plan = self._units_plan(req)
        S = plan['summary']
        exact = self._check_desc_splice(self.cur, plan['after'], {'units'})
        label = 'units: %s unit %d%s (%d -> %d units)' % (
            req['op'], req['unit'], ' at station %d' % req['station'] if 'station' in req else
            ' lateral [%s, %s]' % tuple(_dstr(decimal.Decimal(repr(v))) for v in req['lateral']) if 'lateral' in req else
            ' rect %s' % req['rect'] if 'rect' in req else '',
            S['units_before'], S['units_after'])
        self._push('desc', label, plan['after'], kind='units', index=S['changed_units'])
        warn = []
        if S['units_after'] != 17 and S.get('pvs') == 'all':
            warn.append('%d units with pvs all: Build -> Validate refuses V3_pvs_walk until the count is 17 again (the kit lists 17 '
                        'relative units per unit; fewer repeat a target)' % S['units_after'])
        if S['capacity_worst_pct'] > 80:
            warn.append('a unit uses %.0f %% of a block slot / vertex / record limit' % S['capacity_worst_pct'])
        if S['units_after'] != S['units_before']:
            warn.append('unit indices after unit %d shift: the grid start units are recomputed by trackbuild at Build' % req['unit'])
        return dict(S, ok=True, label=label, exact=exact, warnings=warn, regenerated=self._regen_report(plan['base'], plan['regen']),
                    not_moved='geometry, route, starts and checkpoints are NOT changed by a unit edit')

    @staticmethod
    def _check_desc_splice(before, after, keys):
        """independent re-read: only the named top-level values differ (as JSON); every byte outside their spans is unchanged"""
        a, b = json.loads(before.decode('utf-8')), json.loads(after.decode('utf-8'))
        if {k for k in set(a) | set(b) if a.get(k, None) != b.get(k, None) or (k in a) != (k in b)} - set(keys):
            raise EditError('internal: a description value outside %s changed; not applied' % sorted(keys))
        sa, sb = json_spans(before), json_spans(after)
        cut_a = sorted(sa[(k,)] for k in keys if (k,) in sa)
        cut_b = []
        for k in keys:
            if (k,) not in sb:
                continue
            s, e = sb[(k,)]
            if (k,) in sa:
                cut_b.append((s, e))
            else:                                           # an inserted member: remove from its comma to the value's end
                q = after.rfind(json.dumps(k).encode('utf-8'), 0, s)
                c = after.rfind(b',', 0, q)
                if q < 0 or c < 0 or after[c + 1:q].strip():
                    raise EditError('internal: an inserted description member is not where expected; not applied')
                cut_b.append((c, e))

        def rest(buf, cuts):
            out, p = [], 0
            for s, e in sorted(cuts):
                out.append(buf[p:s])
                p = e
            out.append(buf[p:])
            return b'\0'.join(out)
        ra, rb = rest(before, cut_a), rest(after, [x for x in cut_b])
        if ra.replace(b'\0', b'') != rb.replace(b'\0', b''):
            raise EditError('internal: description bytes outside the edited values changed; not applied')
        return {'values_changed': sorted(k for k in keys if a.get(k) != b.get(k)), 'other_bytes_unchanged': True}

    # ---------------- v0.16 material PROPERTY edits (description; trackbuild 0.2 keys only, checked by the kit's own rules)
    def material_groups(self, material):
        if self.obj_cur is None:
            return 0
        return sum(1 for g in obj_index(self.obj_cur)[1] if g['mat'] == material)

    def material_property(self, material, prop, value=None, confirm=False):
        """set texture (an existing project PNG) / surface (16-bit word) / collide / car_solid of an EXISTING material.
        Only that value's bytes change (or one member is added when the key is absent); the edited material is checked by
        the kit's trackbuild preflight.check_desc + build.texture_record + the build's car-solid rule before it is applied."""
        d = self.desc()
        mats = d.get('materials') or {}
        if not isinstance(material, str) or material not in mats or not isinstance(mats[material], dict):
            raise EditError('material %r refused: only existing materials of the description (%s); creating materials is not '
                            'supported' % (material, ', '.join(sorted(mats))))
        m = mats[material]
        extra = sorted(set(m) - set(MAT_PROPS))
        if extra:
            raise EditError('material %s has keys trackbuild refuses (%s): fix the description first; not edited' % (material, ', '.join(extra)))
        if prop not in MAT_PROPS:
            raise EditError('property %r refused: trackbuild 0.2 materials have only %s (%s)' % (
                prop, ', '.join(MAT_PROPS), 'alpha / blend / shader / flags / animation are not supported by trackbuild'
                if prop in UNSUPPORTED_MAT_PROPS else 'not a trackbuild key'))
        if material not in (d.get('rows') or []):
            raise EditError('material %s has no render row: no OBJ face can use it (trackbuild needs a row for every OBJ '
                            'material), so its properties have no effect; not edited' % material)
        if prop == 'texture':
            if not isinstance(value, str) or not value:
                raise EditError('texture must be a project PNG path such as "textures/bm_grass.png"')
            new = value.replace('\\', '/')
            why = wb_track.wb_car.rel_problem(new, 'texture')
            if why:
                raise EditError('texture %r refused: %s' % (value, why))
            if not new.lower().endswith('.png'):
                raise EditError('texture %r refused: trackbuild reads PNG only' % value)
            if new not in stg.tree_hashes(self.project):
                raise EditError('texture %r refused: not an existing file of this project (only existing PNGs can be referenced; '
                                'adding textures is not supported here)' % value)
            p = os.path.join(self.project, *new.split('/'))
            if os.path.islink(p) or (getattr(os.lstat(p), 'st_file_attributes', 0) & stg.REPARSE):
                raise EditError('texture %r is a link: refused' % value)
            old = m.get('texture')
            same = isinstance(old, str) and old.replace('\\', '/') == new
        elif prop == 'surface':
            if not isinstance(value, str) or not SURFACE_RE.match(value.strip()):
                raise EditError('surface %r refused: a 16-bit hex word such as "0x0001" (trackbuild: hex string, 0..0xFFFF)' % (value,))
            new = '0x%04X' % int(value.strip(), 16)
            old = m.get('surface')
            try:
                same = int(old, 16) == int(new, 16)
            except (TypeError, ValueError):
                same = False
        else:
            if not isinstance(value, bool):
                raise EditError('%s must be true or false (got %r)' % (prop, value))
            new = value
            old = m.get(prop, True if prop == 'car_solid' else None)
            same = bool(old) == new                            # absent collide = false, absent car_solid = true (trackbuild)
        if same:
            raise EditError('%s.%s is already %s: nothing to edit' % (material, prop, json.dumps(new)))
        n = self.material_groups(material)
        if n > 1 and confirm is not True:
            raise EditError('NEEDS CONFIRMATION: material %s is shared by %d face groups; changing %s changes all of them. '
                            'Confirm to apply (or assign another existing material to one group first)' % (material, n, prop))
        m2 = dict(m, **{prop: new})
        kit_check_material(self.cfg, self.project, d.get('obj'), material, m2, prop == 'texture')
        sp = json_spans(self.cur)
        val = json.dumps(new).encode('ascii')
        path = ('materials', material, prop)
        b = bytearray(self.cur)
        if path in sp:
            s, e = sp[path]
            b[s:e] = val
        else:                                                  # key absent: one member appended to this material object
            e = max(sp[('materials', material, k)][1] for k in m)
            b[e:e] = b', ' + json.dumps(prop).encode('ascii') + b': ' + val
        after = bytes(b)
        d2 = json.loads(after.decode('utf-8'))
        if d2['materials'][material] != m2 or {k: v for k, v in d2.items() if k != 'materials'} != {k: v for k, v in d.items() if k != 'materials'} \
                or {k: v for k, v in d2['materials'].items() if k != material} != {k: v for k, v in mats.items() if k != material}:
            raise EditError('internal: the splice changed more than %s.%s; not applied' % (material, prop))
        label = 'set %s.%s = %s' % (material, prop, json.dumps(new))
        self._push('desc', label, after, kind='material', index=material)
        r = {'ok': True, 'label': label, 'affected_groups': n, 'added_key': path not in sp}
        if prop == 'surface':
            r['meaning'] = surface_meaning(int(new, 16))
        if n > 1:
            r['warning'] = 'shared material: %d face groups changed' % n
        if prop == 'car_solid':
            r['note'] = CAR_SOLID_NOTE
        return r

    def undo(self):
        if not self.undo_stack:
            raise EditError('nothing to undo')
        u = self.undo_stack[-1]
        f = u.get('file', 'desc')
        if self._buf(f) != u['after']:
            raise EditError('internal: the buffer is not the state after %s' % u['label'])
        self.undo_stack.pop()
        self._setbuf(f, u['before'])
        self.redo_stack.append(u)
        return {'ok': True, 'undone': u['label']}

    def redo(self):
        if not self.redo_stack:
            raise EditError('nothing to redo')
        u = self.redo_stack[-1]
        f = u.get('file', 'desc')
        if self._buf(f) != u['before']:
            raise EditError('internal: the buffer is not the state before %s' % u['label'])
        self.redo_stack.pop()
        self._setbuf(f, u['after'])
        self.undo_stack.append(u)
        return {'ok': True, 'redone': u['label']}

    def save(self):
        """writes the description / OBJ only when changed (temp file + atomic replace each); other files must be untouched"""
        if open(self.desc_path, 'rb').read() != self.saved:
            raise EditError('%s changed on disk since it was opened / saved: not overwritten (reopen the project)' % self.desc_rel)
        if self.obj_rel and open(self.obj_path, 'rb').read() != self.obj_saved:
            raise EditError('%s changed on disk since it was opened / saved: not overwritten (reopen the project)' % self.obj_rel)
        if self._others() != self.others0:
            raise EditError('other project files changed on disk since the editor opened them: not saved (reopen the project)')
        if not self.dirty():
            return {'ok': True, 'written': False, 'note': 'no changes: nothing written'}
        # v0.16: all-or-nothing. Every temp file is written first; a failed replace restores the files already replaced to
        # their saved bytes, so a failed save leaves the project as it was on disk and the edits unsaved in the editor.
        plan = [(path, cur, old, rel) for path, cur, old, rel in ((self.obj_path, self.obj_cur, self.obj_saved, self.obj_rel),
                                                                  (self.desc_path, self.cur, self.saved, self.desc_rel))
                if path and cur != old]
        tmps = []
        try:
            for path, cur, old, rel in plan:
                tmps.append(path + '.wb_tmp')
                with open(tmps[-1], 'wb') as f:
                    f.write(cur)
        except OSError as e:
            for t in tmps:
                if os.path.exists(t):
                    os.remove(t)
            raise EditError('save failed while writing a temporary file (%s): nothing replaced, the project is unchanged; '
                            'the edits are kept (unsaved)' % e)
        written = []
        try:
            for (path, cur, old, rel), tmp in zip(plan, tmps):
                os.replace(tmp, path)
                written.append((path, old, rel))
        except OSError as e:
            restored = []
            for path, old, rel in written:
                with open(path + '.wb_tmp', 'wb') as f:
                    f.write(old)
                os.replace(path + '.wb_tmp', path)
                restored.append(rel)
            for t in tmps:
                if os.path.exists(t):
                    os.remove(t)
            raise EditError('save failed (%s): %s; the project files are as before the save%s; the edits are kept (unsaved)' % (
                e, 'nothing was replaced' if not restored else 'restored %s' % ', '.join(restored),
                '' if not restored else ' (written back from the saved bytes)'))
        written = [rel for path, old, rel in written]
        changed = [i for i in range(min(len(self.saved), len(self.cur))) if self.saved[i] != self.cur[i]]
        self.saved = self.cur
        self.obj_saved = self.obj_cur
        self.check = wb_track.input_check(self.cfg, self.project, self.rid)
        return {'ok': True, 'written': True, 'files': written, 'bytes': len(self.cur),
                'first_changed_offset': changed[0] if changed else None}

    # ---------------- scene (read only view data)
    def scene(self):
        d = self.desc()
        mats, flags = {}, []
        mesh = {'materials': {}, 'unsupported_statements': {}, 'groups': []}
        if self.obj_cur is not None:
            mesh = read_obj_view(self.obj_cur)                     # the CURRENT buffer: live preview of unsaved edits
        for name, m in (d.get('materials') or {}).items():
            tex = m.get('texture')
            ok = isinstance(tex, str) and tex.replace('\\', '/') in (self.check.get('inputs') or {}) or (
                isinstance(tex, str) and not any(('material %s ' % name) in p for p in self.check['problems']))
            try:
                sm = surface_meaning(int(m.get('surface'), 16))
            except (TypeError, ValueError):
                sm = 'not a hex word (trackbuild refuses it)'
            mats[name] = {'texture': tex, 'texture_ok': bool(ok), 'surface': m.get('surface'), 'collide': m.get('collide'),
                          'car_solid': m.get('car_solid', True), 'extra_keys': sorted(set(m) - {'texture', 'surface', 'collide', 'car_solid'}),
                          'surface_meaning': sm, 'groups': self.material_groups(name), 'in_rows': name in (d.get('rows') or []),
                          'tex_v': hashlib.sha256(str(tex).encode()).hexdigest()[:8]}
        for k in d:
            if k not in KNOWN_DESC:
                flags.append({'key': k, 'flag': 'UNSUPPORTED (not a documented trackbuild key): preserved byte for byte, not shown'})
        for k in ('traffic', 'lod', 'pvs', 'wall_gaps', 'gamedata_header', 'barrier_station', 'generator', 'label'):
            if k in d:
                flags.append({'key': k, 'flag': 'preserved, read only in this slice', 'value_summary': summarize(d[k])})
        for st, c in mesh.get('unsupported_statements', {}).items():
            flags.append({'key': 'OBJ %s' % st, 'flag': '%d line(s) trackbuild refuses; shown nowhere, file preserved' % c})
        return {'state': self.state(), 'materials': mats, 'mesh': mesh, 'rows': d.get('rows'), 'constructs': self.constructs(),
                'stations': [{'p': s.get('p'), 't': s.get('t'), 'offsets': s.get('offsets')} for s in d.get('stations') or []],
                'units': d.get('units') or [], 'route': d.get('route') or {}, 'grid': d.get('grid') or [],
                'start_line': d.get('start_line'), 'checkpoints': d.get('checkpoints') or [],
                'pvs': d.get('pvs') or {'mode': 'all'}, 'lod': d.get('lod') or {'mode': 'identity'}, 'flags': flags,
                'editable': dict({k: 'move by (dx, dy, dz)' for k in EDITABLE},
                                 material='set texture (existing project PNG) / surface word / collide / car_solid',
                                 **({'group': 'assign an existing material; set the vertex colour (0..1); move the selected '
                                              'groups by (dx, dy, dz) metres (snap, isolate / keep connected); turn / scale; '
                                              'duplicate the selected groups'} if self.obj_cur is not None else {})),
                'textures_available': self.textures_available(),
                'surface_words': [{'word': '0x%04X' % w, 'meaning': surface_meaning(w)} for w in sorted(SURFACE_MEANINGS)],
                'car_solid_note': CAR_SOLID_NOTE,
                'assignable': [n for n in (d.get('rows') or []) if n in (d.get('materials') or {}) and
                               not set(d['materials'][n]) - {'texture', 'surface', 'collide', 'car_solid'}],
                'not_editable': NOT_EDITABLE_WHY, 'validation': self.validation()}

    def textures_available(self):
        """the project's PNG files a material may reference, each with the kit reader's verdict (opaque, size)"""
        cache = self.__dict__.setdefault('_texinfo', {})
        out = []
        for rel, h in sorted(stg.tree_hashes(self.project).items()):
            if not rel.lower().endswith('.png'):
                continue
            if (rel, h) not in cache:
                try:
                    K = kit_trackbuild(self.cfg)
                    w, hh, _rows, amin = K['io'].read_png_alpha(os.path.join(self.project, *rel.split('/')))
                    p2 = lambda x: 4 <= x <= 1024 and x & (x - 1) == 0  # noqa: E731
                    why = None if amin == 255 and p2(w) and p2(hh) else (
                        'transparent pixels (trackbuild 0.2 writes opaque DXT1)' if amin != 255 else '%dx%d is not a power of two 4..1024' % (w, hh))
                    cache[(rel, h)] = {'path': rel, 'size': [w, hh], 'ok': why is None, 'why': why}
                except Exception as e:  # noqa: BLE001   reported, never interpreted
                    cache[(rel, h)] = {'path': rel, 'ok': False, 'why': 'not readable by the kit (%s)' % e}
            out.append(cache[(rel, h)])
        return out

    def validation(self):
        """input-check problems + the last build's failed gates -> [{source, text, targets [(kind, index|None)]}]"""
        out = []
        for p in self.check['problems']:
            t = []
            for name in (self.desc().get('materials') or {}):
                if ('material %s ' % name) in p:
                    t.append(['material', name])
            if 'obj' in p.lower():
                t.append(['mesh', None])
            out.append({'source': 'Workbench input check', 'text': p, 'targets': t})
        b = self.last_build or {}
        for g, det in (b.get('gates') or {}).items():
            tgt = GATE_TARGETS.get(g, 'mesh')
            t = [[tgt, None]]
            if tgt == 'grid':
                t = [['grid', i] for i in range(len(self.desc().get('grid') or []))]
            out.append({'source': 'trackbuild gate %s (last Build)' % g, 'text': json.dumps(det)[:600], 'targets': t})
        if b.get('verdict') and not b.get('ok') and not b.get('gates'):
            out.append({'source': 'last Build', 'text': '%s: %s' % (b['verdict'], ' | '.join(b.get('excerpt') or [])[:600]),
                        'targets': []})
        return out

    def texture_bytes(self, material):
        m = (self.desc().get('materials') or {}).get(material) or {}
        tex = m.get('texture')
        if not isinstance(tex, str) or wb_track.wb_car.rel_problem(tex, 'texture') or not tex.lower().endswith('.png'):
            raise EditError('material %s texture is not a checked project file' % material)
        files = stg.tree_hashes(self.project)
        rel = tex.replace('\\', '/')
        if rel not in files:
            raise EditError('material %s texture %s missing' % (material, tex))
        p = os.path.join(self.project, *rel.split('/'))
        if os.path.islink(p) or (getattr(os.lstat(p), 'st_file_attributes', 0) & stg.REPARSE):
            raise EditError('texture is a link: refused')
        return open(p, 'rb').read()

    # ---------------- Build / Validate / Stage (the v0.13 job)
    def stage(self, dest, timeout=900):
        if self.dirty():
            raise EditError('unsaved edits: Save first (the build reads the saved source only)')
        lock = core.OpLock(self.cfg)
        why = lock.acquire('track editor stage %s' % self.project)
        if why:
            raise EditError(why)
        try:
            job = stg.StageJob(self.cfg, stg.StageOp(self.rid, self.project, dest)).start()
            if not job.wait(timeout):
                job.cancel()
                job.wait(60)
            r = job.result_dict
        finally:
            lock.release()
        gates = {}
        vp = os.path.join(r.get('attempt') or '', 'build', 'VALIDATION.json')
        if os.path.isfile(vp):
            try:
                v = json.load(open(vp, encoding='utf-8'))
                gates = {g: v[g].get('detail') for g in v.get('summary', {}).get('failed', [])}
            except (OSError, ValueError, KeyError):
                pass
        self.last_build = {'ok': r.get('ok'), 'verdict': r.get('verdict'), 'staged': r.get('staged'), 'gates': gates,
                           'excerpt': r.get('excerpt'), 'log': r.get('log')}
        return dict(self.last_build, summary=stg.summarize(r))


    def recheck(self):
        self.check = wb_track.input_check(self.cfg, self.project, self.rid)
        return {'ok': not self.check['problems'], 'validation': self.validation()}


# ---------------------------------------------------------------- v0.15 retail mode (READ ONLY)
RETAIL_READ_ONLY = ('retail mode is READ ONLY: retail data is never edited, saved, built or converted into an authored project '
                    '(make your own track with New track project)')


class RetailSource:
    """a retail track folder decoded by wb_retail into its cache; every write path raises"""
    mode = 'retail'

    def __init__(self, cfg, folder, force=False):
        self.cfg = cfg
        if isinstance(folder, str) and os.path.isdir(folder) and stg.detect(os.path.abspath(folder))[0]:
            raise EditError('%s is a Workbench project, not a retail track folder: open it without --retail' % folder)
        try:
            self.view, self.cache, self.reused = wb_retail.decode(cfg, folder, force)
        except wb_retail.RetailError as e:
            raise EditError('retail folder refused: %s' % e)
        self.project = self.view['folder']
        self.dirty = lambda: False

    def state(self):
        h = hashlib.sha256(json.dumps(self.view['source']['required_sha256'], sort_keys=True).encode()).hexdigest()
        return {'mode': 'retail', 'project': self.project, 'desc': None, 'dirty': False, 'undo': [], 'redo': [],
                'sha256': h, 'content_sha256': h, 'read_only': RETAIL_READ_ONLY, 'cache': self.cache}

    def scene(self):
        v = self.view
        val = [{'source': 'kit reader %s' % c['reader'], 'text': p, 'targets': []} for c in v['checks'] for p in c['problems']]
        flags = [{'key': 'preview vs the game renderer', 'flag': n} for n in v.get('render_notes', [])]
        flags += [{'key': x['what'], 'flag': x['status']} for x in v['not_decoded']]
        flags += [{'key': 'texture %s' % t['name'], 'flag': t['why']} for t in v['textures_skipped']]
        return {'mode': 'retail', 'state': self.state(), 'title': '%s %s' % (v['track_id'] or '', v.get('name') or ''),
                'counts': v['counts'], 'mesh': v['mesh'], 'lit_scale': v['lit_scale'], 'collision': v['collision'],
                'units': v['units'], 'route': v['route'], 'starts': v['starts'], 'materials_retail': v['materials'],
                'texture_alpha': v.get('texture_alpha', {}), 'render_classes': v.get('render_classes', {}),
                'readers': v['readers'], 'source': v['source'], 'flags': flags, 'validation': val, 'editable': {},
                'read_only': RETAIL_READ_ONLY, 'not_editable': {}}

    def texture_bytes(self, ti):
        try:
            ti = int(ti)
        except (TypeError, ValueError):
            raise EditError('texture index %r' % ti)
        p = os.path.join(self.cache, 'tex', 't%03d.png' % ti)
        if not os.path.isfile(p):
            raise EditError('texture %d was not previewed' % ti)
        return open(p, 'rb').read()

    def bin(self, name):
        if name not in ('mesh', 'coll'):
            raise EditError('no such buffer %r' % name)
        return open(os.path.join(self.cache, name + '.bin'), 'rb').read()

    def recheck(self):
        return {'ok': True, 'validation': self.scene()['validation'], 'note': 'retail checks are the kit readers\' own'}

    def _ro(self, *a, **k):
        raise EditError(RETAIL_READ_ONLY)

    move = assign_material = set_colour = material_property = translate_group = translate_groups = transform_groups = preview_translation = undo = redo = save = stage = _ro
    weld = weld_preview = boundary = _ro                # v0.21: boundary inspection / welding work on authored OBJ sources only
    duplicate_groups = bridge = bridge_preview = _ro    # v0.22: layout construction on authored OBJ sources only
    layout = _ro                                        # v0.23+: unit regions, roads, race layout, scenery: authored sources only


def _ranges(xs):
    out, s = [], None
    for i, x in enumerate(xs):
        if s is None:
            s = x
        if i + 1 == len(xs) or xs[i + 1] != x + 1:
            out.append(str(s) if s == x else '%d..%d' % (s, x))
            s = None
    return ', '.join(out)


def summarize(v):
    if isinstance(v, dict):
        return {k: (summarize(x) if not isinstance(x, (list, dict)) else '%s(%d)' % (type(x).__name__, len(x))) for k, x in v.items()}
    if isinstance(v, list):
        return 'list(%d)' % len(v)
    return v


def obj_index(b):
    """OBJ bytes -> (lines with their line ends, face groups [{i, line, mat, faces [line idx]}], v line indices). A face
    group = the faces after one usemtl statement (the unit of material assignment / colour)."""
    lines = b.splitlines(keepends=True)
    groups, vlines = [], []
    for li, raw in enumerate(lines):
        s = raw.split(b'#', 1)[0].split()
        if not s:
            continue
        if s[0] == b'v':
            vlines.append(li)
        elif s[0] == b'usemtl' and len(s) == 2:
            groups.append({'i': len(groups), 'line': li, 'mat': s[1].decode('ascii', 'replace'), 'faces': []})
        elif s[0] == b'f' and groups:
            groups[-1]['faces'].append(li)
    return lines, groups, vlines


def read_obj_view(src):
    """OBJ (path or bytes) -> per material {pos [..], uv [..], col [..], grp [face group per triangle]} for DISPLAY only
    (trackbuild's reader stays the authority) + the face groups. Statements trackbuild refuses are counted, never interpreted."""
    if isinstance(src, (bytes, bytearray)):
        text = bytes(src).decode('ascii', 'replace').splitlines()
    else:
        with open(src, 'r', encoding='ascii', errors='replace') as fh:
            text = fh.read().splitlines()
    V, VT, VN, mat, grp = [], [], [], None, -1
    out, bad, groups = {}, {}, []
    for ln, line in enumerate(text, 1):
        s = line.split('#', 1)[0].strip()
        if not s:
            continue
        k, *a = s.split()
        try:
            if k == 'v':
                f = [float(x) for x in a]
                V.append((f[:3], f[3:6] if len(f) == 6 else [0.5, 0.5, 0.5]))
            elif k == 'vt':
                VT.append((float(a[0]), float(a[1])))
            elif k == 'vn':
                VN.append(a)
            elif k == 'usemtl':
                mat = a[0]
                grp = len(groups)
                groups.append({'i': grp, 'line': ln, 'mat': mat, 'faces': 0, 'colours': {}})
            elif k == 'f':
                idx = [[int(q) for q in x.split('/')] for x in a]
                m = out.setdefault(mat, {'pos': [], 'uv': [], 'col': [], 'grp': [], 'faces': 0})
                m['faces'] += 1
                if grp >= 0:
                    groups[grp]['faces'] += 1
                for tri in ((0, 1, 2), (0, 2, 3)) if len(idx) == 4 else ((0, 1, 2),):
                    m['grp'].append(grp)
                    for j in tri:
                        vi, ti = idx[j][0], idx[j][1]
                        p, c = V[vi - 1]
                        m['pos'] += [round(p[0], 3), round(p[1], 3), round(p[2], 3)]
                        m['uv'] += [round(VT[ti - 1][0], 4), round(1.0 - VT[ti - 1][1], 4)]
                        m['col'] += [round(c[0], 3), round(c[1], 3), round(c[2], 3)]
                        if grp >= 0:
                            key = '%.3f %.3f %.3f' % tuple(c)
                            groups[grp]['colours'][key] = groups[grp]['colours'].get(key, 0) + 1
            elif k in ('mtllib', 'o', 'g', 's'):
                pass
            else:
                bad[k] = bad.get(k, 0) + 1
        except (ValueError, IndexError):
            bad['malformed ' + k] = bad.get('malformed ' + k, 0) + 1
    return {'materials': out, 'unsupported_statements': bad, 'vertices': len(V), 'groups': groups}


# ---------------------------------------------------------------- HTTP server (127.0.0.1, token)
class Server:
    def __init__(self, src, port=0):
        self.src, self.token = src, secrets.token_hex(16)
        self.lock = threading.Lock()
        self.selftest = None
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype='application/json'):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def _auth(self, q):
                return q.get('t', [''])[0] == outer.token

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                if not self._auth(q):
                    return self._send(403, {'error': 'token'})
                try:
                    with outer.lock:
                        if u.path == '/':
                            return self._send(200, open(HTML, 'rb').read(), 'text/html; charset=utf-8')
                        if u.path == '/api/scene':
                            return self._send(200, outer.src.scene())
                        if u.path == '/api/state':
                            return self._send(200, outer.src.state())
                        if u.path == '/tex':
                            key = q.get('i', [''])[0] if getattr(outer.src, 'mode', '') == 'retail' else q.get('m', [''])[0]
                            return self._send(200, outer.src.texture_bytes(key), 'image/png')
                        if u.path == '/bin' and getattr(outer.src, 'mode', '') == 'retail':
                            return self._send(200, outer.src.bin(q.get('f', [''])[0]), 'application/octet-stream')
                    return self._send(404, {'error': 'not found'})
                except EditError as e:
                    return self._send(409, err_json(e))

            def do_POST(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                n = int(self.headers.get('Content-Length') or 0)
                raw = self.rfile.read(n) if n else b''          # v0.28: read the body first, also when refused: a reply over
                if not self._auth(q):                           # unread data makes Windows reset the socket (client 10053)
                    return self._send(403, {'error': 'token'})
                try:
                    body = json.loads(raw.decode('utf-8') or '{}') if n else {}
                except ValueError:
                    return self._send(400, {'ok': False, 'error': 'body is not JSON'})
                try:
                    with outer.lock:
                        s = outer.src
                        if u.path == '/api/edit':
                            r = s.move(body.get('kind'), body.get('index'), body.get('delta'))
                        elif u.path == '/api/material':
                            op = body.get('op')
                            if op == 'assign':
                                r = s.assign_material(body.get('group'), body.get('material'), body.get('scope', 'group'))
                            elif op == 'colour':
                                r = s.set_colour(body.get('group'), body.get('rgb'), body.get('scope', 'group'))
                            elif getattr(s, 'mode', '') == 'retail':
                                r = s.material_property()
                            else:
                                r = s.material_property(body.get('material'), body.get('prop') or op, body.get('value'),
                                                        body.get('confirm') is True)
                        elif u.path == '/api/geometry':
                            op = body.get('op')
                            sel = body.get('groups') if 'groups' in body else [body.get('group')]
                            if op == 'translate':
                                r = s.translate_groups(sel, body.get('delta'), body.get('mode', 'isolate'), body.get('snap'),
                                                       body.get('preview_key'))
                            elif op == 'transform':
                                r = s.transform_groups(sel, body.get('angle', 0), body.get('scale', 1), body.get('pivot', 'bbox'),
                                                       body.get('mode', 'isolate'), body.get('angle_snap'), body.get('preview_key'))
                            elif op == 'preview':
                                r = s.preview_translation(sel, body.get('mode', 'isolate'))
                            elif op == 'boundary':
                                r = s.boundary(body.get('tol'))
                            elif op == 'weld_preview':
                                r = s.weld_preview(body.get('pairs'), body.get('chains'), body.get('tol'), body.get('keep', 'a'))
                            elif op == 'weld':
                                r = s.weld(body.get('pairs'), body.get('chains'), body.get('tol'), body.get('keep', 'a'),
                                           body.get('preview_key'))
                            elif op == 'duplicate':
                                r = s.duplicate_groups(sel, body.get('offset'))
                            elif op == 'bridge_preview':
                                r = s.bridge_preview(body.get('chains'), body.get('material'), body.get('closed', False))
                            elif op == 'bridge':
                                r = s.bridge(body.get('chains'), body.get('material'), body.get('closed', False),
                                             body.get('preview_key'))
                            else:
                                raise EditError('geometry op %r refused: only "translate" / "transform" / "preview" / "boundary" / '
                                                '"weld_preview" / "weld" / "duplicate" / "bridge_preview" / "bridge" (automatic '
                                                'gap filling and other topology edits are not supported)' % (op,))
                        elif u.path == '/api/layout':
                            r = s.layout(body)
                        elif u.path == '/api/undo':
                            r = s.undo()
                        elif u.path == '/api/redo':
                            r = s.redo()
                        elif u.path == '/api/save':
                            r = s.save()
                        elif u.path == '/api/check':
                            r = s.recheck()
                        elif u.path == '/api/stage':
                            r = s.stage(body.get('dest') or '')
                        elif u.path == '/api/selftest':
                            outer.selftest = body
                            r = {'ok': True}
                        else:
                            return self._send(404, {'error': 'not found'})
                    r['state'] = s.state()
                    return self._send(200, r)
                except EditError as e:
                    return self._send(409, err_json(e, state=outer.src.state()))

        class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
        self.httpd = TS(('127.0.0.1', port), H)
        self.port = self.httpd.server_address[1]
        self.url = 'http://127.0.0.1:%d/?t=%s' % (self.port, self.token)

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description='Workbench track editor (first slice)')
    ap.add_argument('project', help='an authored track project, or with --retail a retail Tracks\\RR\\NN_VN folder')
    ap.add_argument('--retail', action='store_true', help='READ-ONLY view of a retail track folder (decoded into a cache)')
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--config')
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config)
    try:
        src = RetailSource(cfg, a.project) if a.retail else TrackSource(cfg, a.project)
    except EditError as e:
        print(json.dumps({'ok': False, 'error': str(e)}))
        return 3
    srv = Server(src, a.port).start()
    if a.retail:
        print('track editor - RETAIL VIEW, READ ONLY: %s\nfolder %s (%s %s)\ncache %s (%s; local only, never packaged)\n'
              'Ctrl+C stops the viewer.' % (srv.url, src.project, src.view['track_id'], src.view.get('name') or '', src.cache,
                                            'reused' if src.reused else 'decoded now'), flush=True)
    else:
        print('track editor (first slice, not a complete editor): %s\nproject %s, description %s\nCtrl+C stops the editor; unsaved '
              'edits are discarded.' % (srv.url, src.project, src.desc_rel), flush=True)
    if not a.no_browser:
        webbrowser.open(srv.url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    srv.stop()
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
