"""wb_retail - Workbench v0.15: READ-ONLY view of a locally supplied retail track folder (gp\\workbench, 2026-10-29).

Explicit mode (wb_trackedit.py --retail FOLDER). The folder is YOUR game data's Tracks\\RR\\NN_VN (static.dat, streamed.dat,
Gamedata.bgd). It is only read (read-only opens; sha256 + size + mtime are compared before / after every decode). The decode
goes into a separate cache, <Workbench state>\\retail_cache\\<id>-<hash12>\\, never into the source folder; the cache is a
Workbench-protected folder (never a staging destination) and nothing in it is packaged, staged or uploaded. Retail data is never
converted into an authored project: retail mode has no edit, save or build path.

Decoders: ONLY the verified readers the mod kit's trackbuild 0.2.1 already ships in tools\\trackbuild\\trackbuild\\_vendor (their
vendored sha256 is checked against the kit's VENDOR.json before import; a mismatch refuses the decode):
  xbmesh      static.dat materials / textures (DXT1 / DXT3 / DXT5 -> PNG preview), streamed.dat mesh blocks, PVS material map
  bolib.collision   per-unit collision trees (quads + surface words)
  ct2_gamedata / ct2_route   Gamedata.bgd model and its S4 AI route (lanes, rungs, node positions)
  ctnav_min.slots   start-grid slots per event
What no kit reader decodes is LISTED (UNSUPPORTED / NOT DECODED), never guessed: checkpoints / lap lines (Gamedata S1), traffic,
props, enviro.dat, audio, LOD display, PVS display.
v0.16: texture previews keep the decoded RGBA; each material's render class (opaque / cut-out / blended, depth write) comes
from its +0x24 flags as the game's state setup reads them (never from texture names), cross-checked against the PVS pass split.

    py -3 -B wb_retail.py check FOLDER        -> JSON (read-only checks, no decode)
    py -3 -B wb_retail.py decode FOLDER       -> JSON (decode into the cache, or reuse a matching cache)
"""
import hashlib
import importlib
import json
import os
import re
import shutil
import stat as _stat
import struct
import sys
import time

import wb_core as core

SCHEMA = 'bm-workbench-retail-view/2'                 # /2 (v0.16): texture alpha kept, render classes, blended chunks
TB_DIR = r'tools\trackbuild'
REQUIRED = ('static.dat', 'streamed.dat', 'Gamedata.bgd')
READERS = ('_vendor/xbmesh.py', '_vendor/bolib/collision.py', '_vendor/bolib/__init__.py', '_vendor/ct2_gamedata.py',
           '_vendor/ct2_route.py', '_vendor/ct2_s4.py', '_vendor/ctnav_min.py', '_vendor/__init__.py')
TRACK_ID_RE = re.compile(r'^[A-Z]{2}/[A-Z0-9]{2}_V[0-9]$')
REPARSE = getattr(_stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
MAX_FILE = 256 * 1024 * 1024                        # a typo guard: retail track files are < 32 MB
# retail track names (display only; from the format digest's track table, the same ids as YOUR game data)
NAMES = {'US/P1_V1': 'Kings of the Road'}
NOT_DECODED = [
    ('checkpoints / lap lines (Gamedata S1)', 'NOT DECODED: no verified reader in the kit (trackbuild only writes S1 for its own '
                                              'tracks); not shown'),
    ('start line', 'NOT DECODED: part of Gamedata S1 (see checkpoints); the grid slots are shown'),
    ('traffic (Gamedata S2 / S3)', 'not shown in this slice (the kit vendors bolib.traffic for build checks only)'),
    ('route corners', 'listed as a count only: the corner record fields are only partly decoded'),
    ('LOD blocks', 'decoded for collision only; the low-detail render mesh is not drawn'),
    ('visibility (PVS rows)', 'used to assign materials to meshes; not drawn'),
    ('props / prop instances', 'not decoded for display'),
    ('enviro.dat (sky / environment)', 'UNSUPPORTED: no reader in the kit'),
    ('audio (*.RWS, *.xwb, SOUND.AWD)', 'UNSUPPORTED: not part of the track view'),
    ('line records (primitive 2)', 'skipped in the mesh view'),
]
SURFACES = {0x0001: 'tarmac', 0x0002: 'concrete', 0x000F: 'grass', 0x0018: 'road-facing wall'}
# v0.16 transparency preview. Material +0x24 bits as B3's state setup sub_000393C0 reads them (SRC, KB GAMEPLAY_SYSTEMS_MAP /
# whitemountain wm5 DIAG_REPORT): 0x01 blending on, 0x10 alpha test on, 0x400 z-write off. Nothing here looks at texture names.
F_BLEND, F_ATEST, F_NOZWRITE = 0x01, 0x10, 0x400
RENDER_NOTES = [
    'render class from material +0x24 (SRC sub_000393C0): bit 0x01 = blended (drawn after opaque and cut-out geometry, far '
    'to near per section), bit 0x10 = alpha test (cut-out), neither = opaque (texture alpha ignored); bit 0x400 = no depth '
    'write. Cross-checked against the game\'s own pass split (mesh-block PVS rows: first = opaque pass, rest = translucent pass)',
    'blend factors: drawn as source-alpha / one-minus-source-alpha. The game\'s blend state indices are known, their D3D '
    'factor names are NOT decoded (HYP); no retail Burnout 3 material is additive',
    'alpha-test reference value: NOT decoded; the preview discards texels with alpha < 0.5 (DXT1 cut-outs are 0 / 255, so the '
    'value only matters for DXT3 / DXT5 cut-outs)',
    'vertex alpha is NOT applied: the game\'s texture combiner setup is not decoded, and on Kings of the Road many tree-card '
    'vertices carry vertex alpha 0 (a texture x vertex product would hide cards the game shows; HYP that the game ignores it '
    'for these materials). Counts per material: view.json materials[].vertex_alpha',
    'blended surfaces get a small depth offset in the preview so a decal does not flicker against the road under it; the '
    'game\'s depth bias is not decoded',
    'sorting: far to near by section centre (the game draws its translucent rows in PVS row order, not decoded per frame)',
    'not reproduced: fog, sky / enviro.dat, reflections (type 8 / 9 second pass), UV scroll (bit 0x200), lighting beyond the '
    'baked vertex colour, mip / LOD bias, anisotropy, the host renderer\'s settings',
]


def render_class(f24):
    """material +0x24 -> (mode, depth write); mode opaque | cutout | blend | blend+test"""
    b, t = bool(f24 & F_BLEND), bool(f24 & F_ATEST)
    return ('blend+test' if b and t else 'blend' if b else 'cutout' if t else 'opaque'), not (f24 & F_NOZWRITE)


class RetailError(Exception):
    pass


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def source_state(folder):
    """{name: {sha256, size, mtime_ns}} of every regular top-level file (read-only)"""
    out = {}
    for n in sorted(os.listdir(folder)):
        p = os.path.join(folder, n)
        st = os.lstat(p)
        if _stat.S_ISREG(st.st_mode):
            out[n] = {'sha256': sha_file(p), 'size': st.st_size, 'mtime_ns': st.st_mtime_ns}
    return out


def _inside(child, parent):
    c, p = core.norm(child), core.norm(parent)
    return c == p or c.startswith(p.rstrip('\\/') + os.sep)


def cache_root(cfg):
    return os.path.join(cfg['state'], 'retail_cache')


def track_id_of(folder):
    parts = os.path.normpath(folder).split(os.sep)
    tid = '/'.join(parts[-2:]) if len(parts) >= 2 else ''
    return tid if TRACK_ID_RE.match(tid) else None


def check_folder(cfg, folder):
    """read-only checks before anything is decoded -> (info, problems)"""
    probs = []
    if not isinstance(folder, str) or not folder.strip():
        return {}, ['no retail track folder given']
    folder = os.path.abspath(folder)
    info = {'folder': folder, 'track_id': track_id_of(folder)}
    info['name'] = NAMES.get(info['track_id'])
    if not os.path.exists(folder):
        return info, ['%s does not exist' % folder]
    if not os.path.isdir(folder):
        return info, ['%s is a file, not a track folder (give the Tracks\\RR\\NN_VN folder)' % folder]
    if getattr(os.lstat(folder), 'st_file_attributes', 0) & REPARSE or os.path.islink(folder):
        probs.append('the folder is a link / junction: refused (give the real folder)')
    names = os.listdir(folder)
    if 'workbench-track.json' in names or any(n.endswith('.track.json') for n in names):
        probs.append('this is an authored track project, not a retail folder: open it without --retail (authored mode)')
    for n in REQUIRED:
        p = os.path.join(folder, n)
        if not os.path.isfile(p):
            probs.append('%s missing (a retail track folder holds %s)' % (n, ', '.join(REQUIRED)))
            continue
        st = os.lstat(p)
        if getattr(st, 'st_file_attributes', 0) & REPARSE or os.path.islink(p):
            probs.append('%s is a link: refused' % n)
        elif st.st_size > MAX_FILE:
            probs.append('%s is %d bytes: larger than any retail track file' % (n, st.st_size))
        elif st.st_size == 0 and n != 'streamed.dat':
            probs.append('%s is empty' % n)
    cr = cache_root(cfg)
    if _inside(folder, cr) or _inside(folder, cfg['state']):
        probs.append('the folder is inside the Workbench state / retail cache: give the game data folder itself')
    if _inside(cr, folder):
        probs.append('the retail cache would be inside the source folder: refused (the source is never written)')
    if not info['track_id']:
        info['track_id_note'] = 'folder is not named Tracks\\RR\\NN_VN: shown without a track id'
    return info, probs


# ---------------------------------------------------------------- kit readers (verified copies only)
def readers(cfg):
    tb = core.kit_path(cfg, TB_DIR)                             # v0.28: the bound trackbuild tree
    pkg = os.path.join(tb, 'trackbuild')
    vj = os.path.join(pkg, '_vendor', 'VENDOR.json')
    if not os.path.isfile(vj):
        raise RetailError('mod kit trackbuild readers not found (%s): set the kit in the Workbench configuration' % vj)
    want = {f['file']: f['vendored_sha256'] for f in json.load(open(vj, encoding='utf-8'))['files']}
    used = {}
    for rel in READERS:
        p = os.path.join(pkg, *rel.split('/'))
        if rel not in want or not os.path.isfile(p):
            raise RetailError('kit reader %s missing from VENDOR.json / the kit' % rel)
        h = sha_file(p)
        if h != want[rel]:
            raise RetailError('kit reader %s does not match VENDOR.json (sha256 %s, expected %s): refused' % (rel, h[:12], want[rel][:12]))
        used[rel] = h
    if tb not in sys.path:
        sys.path.insert(0, tb)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True                                   # never write __pycache__ into the kit
    try:
        mods = {k: importlib.import_module('trackbuild._vendor.' + k) for k in
                ('xbmesh', 'ct2_gamedata', 'ct2_route', 'ctnav_min', 'bolib.collision')}
    finally:
        sys.dont_write_bytecode = old
    loaded = os.path.normcase(os.path.abspath(mods['xbmesh'].__file__))
    if not loaded.startswith(os.path.normcase(os.path.abspath(pkg))):
        raise RetailError('a different trackbuild package is already imported (%s): run the editor in its own process' % loaded)
    return mods, used


def read_ro(p):
    with open(p, 'rb') as f:                                          # read-only access
        return f.read()


# ---------------------------------------------------------------- decode -> cache
def _decode(cfg, folder, info, out):
    R, used = readers(cfg)
    X, C, GD, CR, CN = R['xbmesh'], R['bolib.collision'], R['ct2_gamedata'], R['ct2_route'], R['ctnav_min']
    st = X.Static(read_ro(os.path.join(folder, 'static.dat')))
    if st.version != 0x27:                                           # b3static B3_VER (every retail Burnout 3 track: 0x27)
        raise RetailError('static.dat version 0x%X is not Burnout 3 (0x27): not a Burnout 3 track folder' % st.version)
    if st.nunit <= 0:
        raise RetailError('static.dat has no streamed units: nothing to show')
    sm = read_ro(os.path.join(folder, 'streamed.dat'))
    gd = read_ro(os.path.join(folder, 'Gamedata.bgd'))
    trk = X.Track.__new__(X.Track)                                    # xbmesh.Track without its retail-folder constant
    trk.tid, trk.st, trk.sm, trk.blocks, trk.empty_units = info['track_id'] or 'track', st, sm, {}, []
    for u, (mo, lo, ms, ls) in enumerate(st.units):
        if ms == 0 or ls == 0:
            trk.empty_units.append(u)
            continue
        trk.blocks[(u, 'mesh')] = X.Block(sm, mo, ms, 'mesh', u)
        trk.blocks[(u, 'lod')] = X.Block(sm, lo, ls, 'lod', u)
    mm, walk = trk.material_map()
    checks = []
    # ---- material render classes (+0x24, SRC) and the game's own pass split (xbmesh material_map: A1 opaque, A2 translucent)
    f24 = {m['i']: struct.unpack_from('<I', st.d, m['rec'] + 0x24)[0] for m in st.mat}
    cls = {i: render_class(f) for i, f in f24.items()}
    passes = {}
    for (u, kind, k), ms in mm.items():
        if kind == 'mesh':
            for mat, tags in ms.items():
                passes.setdefault(mat, set()).update(t for t in tags if t[0] == 'A')
    pass_prob = []
    for mat, tags in sorted(passes.items()):
        want = 'A2' if f24.get(mat, 0) & F_BLEND else 'A1'
        if tags != {want}:
            pass_prob.append('material %d (+0x24 0x%X, %s): drawn in passes %s, expected only %s' % (
                mat, f24.get(mat, 0), cls.get(mat, ('?',))[0], sorted(tags), want))
    checks.append({'reader': 'material +0x24 blend bit vs the PVS pass split (xbmesh material_map)', 'problems': pass_prob,
                   'materials_checked': len(passes)})
    # ---- render mesh (full-detail blocks), grouped by material; blended materials also by section (far-to-near sorting)
    groups = {}
    lines_skipped = unmapped = deg = 0
    lum = []
    valpha = {}
    for (u, kind), b in sorted(trk.blocks.items()):
        if kind != 'mesh':
            continue
        local = {}
        for m in b.meshes:
            mats = mm.get((u, 'mesh', m['i']), {})
            if not mats:
                unmapped += 1
            mat = min(mats) if mats else -1
            if m['prim'] == 2:
                lines_skipped += 1
                continue
            tris, d = X.triangles(m['prim'], m['idx'])
            deg += d
            gk = (mat, u) if cls.get(mat, ('opaque',))[0].startswith('blend') else (mat, None)
            g = groups.setdefault(gk, {'pos': [], 'uv': [], 'col': [], 'idx': []})
            lm = local.setdefault(gk, {})
            va = valpha.setdefault(mat, {})
            for t in tris:
                for k in t:
                    j = lm.get(k)
                    if j is None:
                        v = b.verts[k]
                        j = lm[k] = len(g['pos']) // 3
                        g['pos'] += v[:3]
                        g['uv'] += v[5:7]
                        c = v[4]
                        a = str(c >> 24) if (c >> 24) in (0, 255) else 'other'
                        va[a] = va.get(a, 0) + 1
                        rgb = (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)
                        g['col'] += rgb
                        if len(lum) < 200000:
                            lum.append(sum(rgb) / 3)
                    g['idx'].append(j)
    mean = sum(lum) / len(lum) if lum else 0.5
    lit = max(1.0, min(4.0, 0.5 / mean)) if mean > 0 else 1.0       # display only: scale baked light to a mid grey
    blob = bytearray()
    mesh = []
    order = {'opaque': 0, 'cutout': 1, 'blend+test': 2, 'blend': 2}
    for gk in sorted(groups, key=lambda k: (order[cls.get(k[0], ('opaque',))[0]], k[0], -1 if k[1] is None else k[1])):
        mat, unit = gk
        g = groups[gk]
        rec = st.mat[mat] if 0 <= mat < len(st.mat) else None
        ti = rec['tex'][0] if rec and rec['tex'] and isinstance(rec['tex'][0], int) else None
        mode, zw = cls.get(mat, ('opaque', True))
        n = len(g['pos']) // 3
        e = {'material': mat, 'texture': ti, 'texture_name': st.tex[ti]['name'] if ti is not None else None,
             'shader_type': rec['type'] if rec else None, 'vertices': n, 'indices': len(g['idx']),
             'flags_24': '0x%X' % f24.get(mat, 0), 'render': mode, 'depth_write': zw, 'unit': unit,
             'centre': [round(sum(g['pos'][i::3]) / n, 3) for i in range(3)] if n else None}
        for key, fmt in (('pos', 'f'), ('uv', 'f'), ('col', 'f'), ('idx', 'I')):
            while len(blob) % 4:
                blob.append(0)
            e['off_' + key] = len(blob)
            blob += struct.pack('<%d%s' % (len(g[key]), fmt), *g[key])
        mesh.append(e)
    with open(os.path.join(out, 'mesh.bin'), 'wb') as f:
        f.write(blob)
    # ---- textures (PNG previews of mip 0, decoded RGBA kept: alpha is used by cut-out / blended materials)
    os.makedirs(os.path.join(out, 'tex'))
    used_tex = sorted({e['texture'] for e in mesh if e['texture'] is not None})
    tex_skipped, tex_alpha = [], {}
    for ti in used_tex:
        t = st.tex[ti]
        if t['format'] not in (0x0C, 0x0E, 0x0F):
            tex_skipped.append({'texture': ti, 'name': t['name'], 'why': 'format 0x%02X has no decoder in xbmesh' % t['format']})
            continue
        rgba = bytes(X.decode_dxt(st.d, t['data'], t['w'], t['h'], t['format']))
        a = rgba[3::4]
        tex_alpha[ti] = {'w': t['w'], 'h': t['h'], 'format': '0x%02X' % t['format'], 'alpha0': a.count(0), 'alpha255': a.count(255),
                         'texels': len(a), 'rgba_sha256': hashlib.sha256(rgba).hexdigest()}
        X.write_png(os.path.join(out, 'tex', 't%03d.png' % ti), t['w'], t['h'], rgba)
    # ---- collision (LOD blocks' trees), triangles grouped by surface word
    coll, cprob, nquad = {}, [], 0
    for (u, kind), b in sorted(trk.blocks.items()):
        if kind != 'lod':
            continue
        try:
            t = C.parse(b.b, b.tree, 'b3')
        except Exception as ex:  # noqa: BLE001
            cprob.append('unit %d: collision tree not parsed: %s' % (u, ex))
            continue
        p = C.check(t)
        if p:
            cprob.append('unit %d: %s' % (u, '; '.join(map(str, p[:2]))))
        for lf in t.leaves:
            for q in lf.quads:
                nquad += 1
                sw = struct.unpack_from('<H', q, 4)[0]
                vi = list(q[:4])
                tris = [(0, 1, 2)] if vi[3] == 0xFF else [(0, 1, 2), (1, 3, 2)]
                arr = coll.setdefault(sw, [])
                for tr in tris:
                    for k in tr:
                        arr += lf.verts[vi[k]]
    cblob = bytearray()
    collision = []
    for sw in sorted(coll):
        collision.append({'surface': '0x%04X' % sw, 'name': SURFACES.get(sw), 'vertices': len(coll[sw]) // 3, 'off': len(cblob)})
        cblob += struct.pack('<%df' % len(coll[sw]), *coll[sw])
    with open(os.path.join(out, 'coll.bin'), 'wb') as f:
        f.write(cblob)
    checks.append({'reader': 'bolib.collision check', 'problems': cprob})
    # ---- sections (streamed units) and their streaming bounds (region prism)
    units = []
    for u, (mo, lo, ms, ls) in enumerate(st.units):
        b = trk.blocks.get((u, 'mesh'))
        if not b:
            units.append({'unit': u, 'empty': True})
            continue
        q = b.quad
        units.append({'unit': u, 'corners': [list(c[:3]) for c in q], 'height': q[0][3], 'mesh_bytes': ms, 'lod_bytes': ls,
                      'records': b.nmesh, 'vertices': b.nvert, 'lod_records': trk.blocks[(u, 'lod')].nmesh})
    # ---- Gamedata: events, AI route, start grid
    route, starts, gprob = {}, [], []
    try:
        g = GD.Gamedata.parse(gd)
        gp = GD.check(g)
        if gp:
            gprob += ['Gamedata: %s' % x for x in gp[:6]]
        o4, s4 = g.s4()
        r = CR.Route.parse(gd[o4:o4 + s4])
        rc = CR.check(r)
        if rc:
            gprob += ['route: %s' % x for x in rc[:6]]
        lanes = []
        for i, ln in enumerate(r.lanes):
            pts = []
            for a, bb in ln['rungs']:
                if a < len(r.pos) and bb < len(r.pos):
                    pa, pb = r.pos[a], r.pos[bb]
                    pts.append([round((pa[0] + pb[0]) / 2, 3), round((pa[1] + pb[1]) / 2, 3), round((pa[2] + pb[2]) / 2, 3)])
            lanes.append({'lane': i, 'flags': ln['flags'], 'segments': len(ln['segs']), 'centre': pts})
        route = {'events': g.count, 'lanes': lanes, 'slices': r.slices, 'corners': len(r.corners), 'nodes': len(r.pos),
                 'zones': r.nzones, 'identity': r.serialize(s4) == gd[o4:o4 + s4]}
        seen = {}
        for e, page, k, p in CN.slots(gd):
            key = tuple(round(x, 3) for x in p)
            if key in seen:
                seen[key]['events'].append(e)
                continue
            seen[key] = {'slot': k, 'events': [e], 'pos': list(key)}
            starts.append(seen[key])
    except Exception as ex:  # noqa: BLE001
        gprob.append('Gamedata / route not decoded: %s' % ex)
    checks.append({'reader': 'ct2_gamedata / ct2_route check', 'problems': gprob})
    view = {'schema': SCHEMA, 'folder': folder, 'track_id': info['track_id'], 'name': info.get('name'),
            'readers': {'kit': cfg.get('kit'), 'trackbuild_vendor_sha256': used},
            'counts': {'units': st.nunit, 'empty_units': trk.empty_units, 'materials': len(st.mat), 'textures': len(st.tex),
                       'textures_previewed': len(used_tex) - len(tex_skipped), 'mesh_triangles': sum(e['indices'] for e in mesh) // 3,
                       'mesh_vertices': sum(e['vertices'] for e in mesh), 'collision_quads': nquad,
                       'collision_triangles': sum(c['vertices'] for c in collision) // 3, 'route_lanes': len(route.get('lanes') or []),
                       'start_slots': len(starts), 'line_records_skipped': lines_skipped, 'unmapped_mesh_records': unmapped,
                       'degenerate_strip_triangles_dropped': deg, 'pvs_walk': dict(walk)},
            'mesh': mesh, 'lit_scale': round(lit, 3), 'textures_skipped': tex_skipped, 'collision': collision, 'units': units,
            'route': route, 'starts': starts, 'checks': checks,
            'materials': [{'material': m['i'], 'shader_type': m['type'], 'textures': [st.tex[t]['name'] if isinstance(t, int) else t
                                                                                       for t in m['tex']],
                           'flags_24': '0x%X' % f24[m['i']], 'render': cls[m['i']][0], 'depth_write': cls[m['i']][1],
                           'passes': sorted(passes.get(m['i'], ())), 'vertex_alpha': valpha.get(m['i'], {})} for m in st.mat],
            'texture_alpha': {str(k): v for k, v in tex_alpha.items()},
            'render_classes': {c: sum(1 for i in passes if cls[i][0] == c) for c in ('opaque', 'cutout', 'blend', 'blend+test')},
            'render_notes': RENDER_NOTES,
            'not_decoded': [{'what': a, 'status': b} for a, b in NOT_DECODED]}
    return view


def decode(cfg, folder, force=False):
    """-> (view dict, cache dir, reused). The source folder is compared before / after; the cache is written atomically."""
    info, probs = check_folder(cfg, folder)
    if probs:
        raise RetailError('; '.join(probs))
    folder = info['folder']
    before = source_state(folder)
    key = hashlib.sha256(json.dumps({n: before[n]['sha256'] for n in REQUIRED if n in before}, sort_keys=True).encode()).hexdigest()[:12]
    cdir = os.path.join(cache_root(cfg), '%s-%s' % ((info['track_id'] or 'track').replace('/', '_'), key))
    vp = os.path.join(cdir, 'view.json')
    if not force and os.path.isfile(vp):
        try:
            v = json.load(open(vp, encoding='utf-8'))
            if v.get('schema') == SCHEMA and v.get('source', {}).get('required_sha256') == {n: before[n]['sha256'] for n in REQUIRED}:
                return v, cdir, True
        except (OSError, ValueError):
            pass
    os.makedirs(cache_root(cfg), exist_ok=True)
    tmp = cdir + '.tmp-%d-%d' % (os.getpid(), int(time.time() * 1000))
    os.makedirs(tmp)
    try:
        view = _decode(cfg, folder, info, tmp)
        after = source_state(folder)
        if after != before:
            raise RetailError('the retail folder changed while it was read (before / after differ): cache discarded')
        view['source'] = {'files': before, 'required_sha256': {n: before[n]['sha256'] for n in REQUIRED},
                          'unchanged_after_decode': True}
        view['cache'] = cdir
        view['decoded_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(os.path.join(tmp, 'view.json'), 'w', encoding='utf-8') as f:
            json.dump(view, f)
        with open(os.path.join(tmp, 'README.txt'), 'w', encoding='utf-8') as f:
            f.write('Workbench retail VIEW cache (decoded previews of YOUR game data). Local only: never package, stage, share or\n'
                    'upload. Safe to delete; it is rebuilt when the track is opened again.\n')
        if os.path.isdir(cdir):
            shutil.rmtree(cdir)
        os.replace(tmp, cdir)
    except RetailError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001   a kit reader refused the data: report it, keep no partial cache
        shutil.rmtree(tmp, ignore_errors=True)
        raise RetailError('the kit readers could not decode this folder (%s: %s); nothing cached' % (type(e).__name__, e))
    return view, cdir, False


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description='Workbench read-only retail track view (decode cache)')
    ap.add_argument('cmd', choices=['check', 'decode'])
    ap.add_argument('folder')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--config')
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config)
    if a.cmd == 'check':
        info, probs = check_folder(cfg, a.folder)
        print(json.dumps({'ok': not probs, 'info': info, 'problems': probs}))
        return 0 if not probs else 1
    try:
        v, cdir, reused = decode(cfg, a.folder, a.force)
    except RetailError as e:
        print(json.dumps({'ok': False, 'error': str(e)}))
        return 1
    print(json.dumps({'ok': True, 'cache': cdir, 'reused': reused, 'track_id': v['track_id'], 'name': v.get('name'),
                      'counts': v['counts'], 'checks': v['checks']}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
