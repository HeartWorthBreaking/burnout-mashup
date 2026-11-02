r"""wb_rta_ext - retail track EXTENSION foundation (Workbench 0.33 retail-style authoring, 2026-11-01). LOCAL ONLY products.

1. round_trip(track folder): proves an UNTOUCHED retail track is reproduced exactly by the verified readers / writers before any
   edit is allowed. Every file gets a verdict:
     static.dat     trackconv.b3static strict parse (0 rule mismatches, 0 unclaimed spans) and build() == input
     streamed.dat   every unit's mesh block (xbtopo.MeshModel) and LOD block (xbtopo.LodModel incl. collision tree, lighting
                    table, prop-instance tail) re-serialise byte-identically; the blocks tile the file (offsets from the STATIC
                    unit table, gaps recorded) and the file re-assembled from re-serialised blocks == input
     Gamedata.bgd   format_research fr_routes parse_gamedata -> serialize == input (S1 / S2 / S3 / S4 kept, undecoded bytes raw)
     enviro.dat     fr_enviro parse -> serialize == input
     STATIC props   fr_props parse -> serialize == input (prop tail)
     other files    audio / music: NOT decoded; preserved as opaque bytes (sha256 recorded, copied unchanged)
   All readers are the kit trackbuild's VENDORED copies (sha256 checked against VENDOR.json) + the te2 format_research parsers.
   Never the lossy authored-track generator.
2. Extension projects: a folder with extension.json that REFERENCES the retail track (id, folder, sha256 of every file, the
   round-trip report hash) - no retail bytes are copied into the project. Edits are a list of explicit operations.
3. Supported edit (v1): APPEND decorative render geometry to one unit's mesh block. Rule (KB MESH_AND_COLLISION s4, CT1,
   runtime-proven): a new record linked after a host record (host.next = new) is drawn wherever the host is drawn, with the
   host's material; neighbour rows need no change. Consequences, stated with every build: the geometry uses a material that
   unit already has; it has NO collision (decorative); it is not in the far LOD (drawn only where the unit's full mesh is
   drawn, |rel| <= 4); it must lie inside the unit's region quad. The block may grow by whole pages up to the slot (0x28000);
   STREAMED.DAT is then re-tiled and ONLY the STATIC unit-table entries change (strictly re-checked).
   BLOCKED (exact blockers in RTA_CAPABILITY_MATRIX.md): drivable additions (collision leaves exist in xbtopo, but far-LOD /
   region / AI-route consistency is unverified for extensions), new materials / textures in a retail track, new units,
   prop instances, route / checkpoint changes.
4. build(): applies the edit list to in-memory copies, re-verifies every output strictly, writes the complete track folder
   into a NEW output folder (retail-derived, LOCAL ONLY) + EXTENSION_BUILD.json listing every changed / moved / unchanged
   section. Deterministic: same project -> same bytes.
"""
import hashlib
import json
import math
import os
import shutil
import struct
import sys
import time

import wb_core as core
import wb_retail

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = 'bm-rta-extension/1'
MESH_SLOT, LOD_SLOT = 0x28000, 0x18000      # the GAME's default slots (kit trackbuild.capacity TABLE ... ["game"]). RTA5: an
# extension output is a plain track folder with no mod.toml, so it cannot declare [bmashup.capacity]: extensions keep the game's
# slots (raising them needs a capacity declaration in the mod that ships the extension; not done here)
EXT_CAP_NOTE = ('retail extensions keep the game\'s slot sizes: the extension output has no mod.toml [bmashup.capacity] '
                'declaration (a larger block would need %s = 0x%X on a Burnout Mashup host that supports it)')
EXTRA = ('_vendor/xbtopo.py', '_vendor/trackconv/__init__.py', '_vendor/trackconv/b3static.py', '_vendor/trackconv/common.py',
         '_vendor/bolib/collision.py')


class ExtError(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def readers(cfg):
    """kit-vendored xbtopo / xbmesh / b3static (hash-checked) + format_research parsers"""
    mods, used = wb_retail.readers(cfg)
    tb = core.kit_path(cfg, wb_retail.TB_DIR)
    pkg = os.path.join(tb, 'trackbuild')
    want = {f['file']: f['vendored_sha256'] for f in json.load(open(os.path.join(pkg, '_vendor', 'VENDOR.json'), encoding='utf-8'))['files']}
    for rel in EXTRA:
        p = os.path.join(pkg, *rel.split('/'))
        h = wb_retail.sha_file(p)
        if want.get(rel) != h:
            raise ExtError('kit reader %s does not match VENDOR.json: refused' % rel)
        used[rel] = h
    import importlib
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        mods['xbtopo'] = importlib.import_module('trackbuild._vendor.xbtopo')
        mods['b3static'] = importlib.import_module('trackbuild._vendor.trackconv.b3static')
        mods['collision'] = importlib.import_module('trackbuild._vendor.bolib.collision')
    finally:
        sys.dont_write_bytecode = old
    fr = os.path.join(HERE, 'format_research')
    if fr not in sys.path:
        sys.path.insert(0, fr)
    import fr_routes
    import fr_enviro
    import fr_props
    mods.update(fr_routes=fr_routes, fr_enviro=fr_enviro, fr_props=fr_props)
    return mods, used


def _unit_table(st):
    n = struct.unpack_from('<h', st, 0x54)[0]
    t = struct.unpack_from('<I', st, 0x58)[0]
    return t, [list(struct.unpack_from('<4I', st, t + 16 * u)) for u in range(n)]   # mesh off, lod off, mesh size, lod size


def _read_all(folder):
    out = {}
    for n in sorted(os.listdir(folder)):
        p = os.path.join(folder, n)
        if os.path.isfile(p):
            out[n] = wb_retail.read_ro(p)
    return out


def round_trip(cfg, folder, files=None):
    M, used = readers(cfg)
    F = files if files is not None else _read_all(folder)
    rep = {'schema': SCHEMA + '-roundtrip', 'folder': folder, 'readers_sha256': used, 'files': {}}
    st = F.get('static.dat')
    sm = F.get('streamed.dat')
    if st is None or sm is None:
        raise ExtError('static.dat / streamed.dat missing')
    # static
    o, dg = M['b3static'].parse(st, 'b3')
    st_ok = (not dg.rules) and (not o['garbage']) and M['b3static'].build(o, 'b3') == st
    rep['files']['static.dat'] = {'sha256': sha(st), 'size': len(st), 'identical': st_ok, 'method': 'b3static strict parse + build',
                                  'rules': [str(r) for r in dg.rules[:3]], 'unclaimed': len(o['garbage'])}
    # streamed
    T = M['xbtopo']
    nprop = struct.unpack_from('<h', st, 0x34)[0]
    _t, ut = _unit_table(st)
    blocks = []
    bad = []
    for u, (mo, lo, ms, ls) in enumerate(ut):
        for kind, off, size in (('mesh', mo, ms), ('lod', lo, ls)):
            if not size:
                continue
            b = sm[off:off + size]
            try:
                m = T.MeshModel(b) if kind == 'mesh' else T.LodModel(b, nprop)
                ok = m.serialize(size) == b
            except Exception as e:  # noqa: BLE001
                ok = False
                bad.append('unit %d %s: %s' % (u, kind, e))
            if not ok and len(bad) < 8:
                bad.append('unit %d %s not identical' % (u, kind))
            blocks.append((off, size, u, kind, ok))
    blocks.sort()
    pos, gaps, overlaps = 0, [], []
    for off, size, u, kind, ok in blocks:
        if off > pos:
            gaps.append([pos, off - pos, sha(sm[pos:off])[:12], sm[pos:off].count(0) == off - pos])
        elif off < pos:
            overlaps.append([u, kind])
        pos = max(pos, off + size)
    tail = len(sm) - pos
    rebuilt = bytearray(len(sm))
    for off, size, u, kind, ok in blocks:
        rebuilt[off:off + size] = sm[off:off + size]
    for g in gaps:
        rebuilt[g[0]:g[0] + g[1]] = sm[g[0]:g[0] + g[1]]
    if tail > 0:
        rebuilt[pos:] = sm[pos:]
    rep['files']['streamed.dat'] = {'sha256': sha(sm), 'size': len(sm), 'blocks': len(blocks),
                                    'blocks_identical': sum(1 for b in blocks if b[4]),
                                    'tiling': {'gaps': gaps[:10], 'gap_count': len(gaps), 'overlaps': overlaps, 'tail_bytes': tail},
                                    'identical': all(b[4] for b in blocks) and not overlaps and bytes(rebuilt) == sm,
                                    'method': 'xbtopo MeshModel / LodModel serialize per block + re-tiling by the STATIC unit table',
                                    'problems': bad}
    gd = F.get('Gamedata.bgd')
    if gd is not None:
        try:
            ok = M['fr_routes'].serialize_gamedata(M['fr_routes'].parse_gamedata(gd)) == gd
            err = None
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        rep['files']['Gamedata.bgd'] = {'sha256': sha(gd), 'size': len(gd), 'identical': ok, 'error': err,
                                        'method': 'fr_routes parse_gamedata / serialize_gamedata (S1..S4, undecoded bytes raw)'}
    ev = F.get('enviro.dat')
    if ev is not None:
        try:
            ok = M['fr_enviro'].serialize(M['fr_enviro'].parse(ev)) == ev
            err = None
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        rep['files']['enviro.dat'] = {'sha256': sha(ev), 'size': len(ev), 'identical': ok, 'error': err,
                                      'method': 'fr_enviro parse / serialize'}
    try:
        pok = M['fr_props'].serialize(M['fr_props'].parse(st)) == st
    except Exception:  # noqa: BLE001
        pok = False
    rep['static_prop_tail_identical'] = pok
    for n, b in F.items():
        if n not in rep['files']:
            rep['files'][n] = {'sha256': sha(b), 'size': len(b), 'identical': True, 'method': 'opaque bytes (not decoded): copied unchanged',
                               'decoded': False}
    rep['all_identical'] = all(v['identical'] for v in rep['files'].values()) and pok
    rep['verdict'] = 'PASS' if rep['all_identical'] else 'FAIL'
    rep['edits_allowed'] = rep['all_identical']
    return rep


# ----------------------------------------------------------------------------------------------------- extension projects
def create_project(cfg, track_folder, dest, title=None):
    """a NEW extension project folder (must not exist / be empty) that references the retail track; refuses when the
    untouched track does not round-trip"""
    if os.path.exists(dest) and os.listdir(dest):
        raise ExtError('%s exists and is not empty: choose a new folder' % dest)
    tid = wb_retail.track_id_of(track_folder)
    t0 = time.time()
    rep = round_trip(cfg, track_folder)
    if not rep['edits_allowed']:
        raise ExtError('%s does not round-trip byte-identically with the verified readers: editing is BLOCKED (%s)' % (
            tid, '; '.join('%s %s' % (k, v.get('method')) for k, v in rep['files'].items() if not v['identical'])))
    os.makedirs(dest, exist_ok=True)
    rj = json.dumps(rep, indent=1, sort_keys=True)
    with open(os.path.join(dest, 'ROUNDTRIP.json'), 'w', encoding='utf-8') as f:
        f.write(rj)
    proj = {'schema': SCHEMA, 'title': title or 'Extension of %s' % tid, 'track': tid, 'retail_folder': track_folder,
            'retail_sha256': {n: v['sha256'] for n, v in rep['files'].items()}, 'roundtrip_sha256': sha(rj.encode()),
            'roundtrip_seconds': round(time.time() - t0, 2), 'edits': [], 'local_only': True,
            'note': 'references YOUR retail track; no retail bytes are stored in this project. Builds are retail-derived: LOCAL ONLY.'}
    _save(dest, proj)
    with open(os.path.join(dest, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write('Retail track extension project (Burnout Mashup Workbench, retail-style authoring).\n'
                'extension.json lists the edits; ROUNDTRIP.json proves the untouched track is reproduced exactly.\n'
                'The retail files are only referenced (never copied here). Builds contain retail data: keep them on your PC.\n')
    return proj


def _save(dest, proj):
    p = os.path.join(dest, 'extension.json')
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(proj, f, indent=1, sort_keys=True)
    os.replace(p + '.tmp', p)


def load_project(dest):
    try:
        proj = json.load(open(os.path.join(dest, 'extension.json'), encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise ExtError('not an extension project (%s)' % e)
    if proj.get('schema') != SCHEMA:
        raise ExtError('extension.json schema %r is not %s' % (proj.get('schema'), SCHEMA))
    return proj


def add_edits(dest, edits, label):
    """append checked edits to the project (one history entry); nothing is built here"""
    proj = load_project(dest)
    for e in edits:
        check_edit(e)
    proj['edits'] = list(proj['edits']) + list(edits)
    proj.setdefault('history', []).append({'label': label, 'edits': len(edits), 'time': time.strftime('%Y-%m-%d %H:%M:%S')})
    _save(dest, proj)
    return proj


def undo_last(dest):
    proj = load_project(dest)
    h = proj.get('history') or []
    if not h:
        raise ExtError('nothing to undo')
    n = h[-1]['edits']
    proj['edits'] = proj['edits'][:-n] if n else proj['edits']
    proj['history'] = h[:-1]
    _save(dest, proj)
    return proj


def check_source(proj):
    """the referenced retail files must still be the ones the project was made on"""
    now = {}
    for n in proj['retail_sha256']:
        p = os.path.join(proj['retail_folder'], n)
        if not os.path.isfile(p):
            return 'retail file %s is missing from %s' % (n, proj['retail_folder'])
        now[n] = wb_retail.sha_file(p)
    diff = [n for n in now if now[n] != proj['retail_sha256'][n]]
    return ('retail files changed since the project was made: %s' % ', '.join(diff)) if diff else None


# ----------------------------------------------------------------------------------------------------- unit facts
def unit_info(cfg, folder, unit, files=None):
    M, _u = readers(cfg)
    F = files or {n: wb_retail.read_ro(os.path.join(folder, n)) for n in ('static.dat', 'streamed.dat')}
    st, sm = F['static.dat'], F['streamed.dat']
    _t, ut = _unit_table(st)
    if not 0 <= unit < len(ut):
        raise ExtError('unit %d does not exist (0..%d)' % (unit, len(ut) - 1))
    mo, lo, ms, ls = ut[unit]
    if not ms:
        raise ExtError('unit %d is empty' % unit)
    mb, lb = sm[mo:mo + ms], sm[lo:lo + ls]
    model = M['xbtopo'].MeshModel(mb)
    nprop = struct.unpack_from('<h', st, 0x34)[0]
    lod = M['xbtopo'].LodModel(lb, nprop)
    rows = struct.unpack_from('<b', mb, 0x71)[0]
    mats = list(struct.unpack_from('<83h', mb, 0x84))
    heads = list(struct.unpack_from('<83b', mb, 0x12A + 3))          # chunk 0 = own unit, rowsA
    sobj = M['xbmesh'].Static(st) if hasattr(M['xbmesh'], 'Static') else None
    tex_of = {}
    if sobj is not None:
        for i, m in enumerate(sobj.mat):
            t = m['tex'][0] if m.get('tex') else None
            tex_of[i] = sobj.tex[t]['name'] if isinstance(t, int) else None
    hosts = []
    for r in range(max(0, rows)):
        h = heads[r]
        if h < 0 or h >= len(model.recs):
            continue
        chain = []
        k = h
        while 0 <= k < len(model.recs) and k not in chain:
            chain.append(k)
            k = model.recs[k]['next']
        hosts.append({'row': r, 'material': mats[r], 'texture': tex_of.get(mats[r]), 'head': h, 'chain': chain,
                      'strip': model.recs[h]['prim'] == 6})
    quad = []
    A = struct.unpack_from('<4f', lb, 0x70)
    Cc = struct.unpack_from('<4f', lb, 0x80)
    B = struct.unpack_from('<4f', lb, 0x90)
    quad = [list(A), list(Cc), list(B)]
    return {'unit': unit, 'mesh_size': ms, 'lod_size': ls, 'records': len(model.recs), 'vertices': len(model.verts),
            'rows': rows, 'hosts': hosts, 'region': quad, 'mesh_free_bytes': MESH_SLOT - ms, 'records_free': 127 - len(model.recs),
            'lod_records': len(lod.recs) if hasattr(lod, 'recs') else None}


def in_region(region, x, z, tol=0.0):
    A, Cc, B = region
    return all(A[i] * x + Cc[i] * z - B[i] >= -tol for i in range(4))


# ----------------------------------------------------------------------------------------------------- edits
def _norm(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    ln = math.sqrt(sum(x * x for x in n)) or 1.0
    return [x / ln for x in n]


def check_edit(e):
    if not isinstance(e, dict) or e.get('op') != 'append_decor':
        raise ExtError("edit: only {'op': 'append_decor', ...} is supported (decorative render geometry; see the capability matrix)")
    for k in ('unit', 'texture', 'triangles'):
        if k not in e:
            raise ExtError('append_decor needs %s' % k)
    if 'collision' in e:                                 # RTA3: solid extension (CT1 rule, runtime-proven in CT1 for a ramp)
        c = e['collision']
        if not (isinstance(c, dict) and set(c) <= {'surface'} and
                (c.get('surface', 'auto') == 'auto' or (isinstance(c.get('surface'), str) and _hexword(c['surface']) is not None))):
            raise ExtError("collision: {'surface': 'auto' | '0x0018' ...} (auto = the nearest retail quad of the same kind, CT1 rule)")
    tris = e['triangles']
    if not (isinstance(tris, list) and 1 <= len(tris) <= 20000):
        raise ExtError('triangles: 1..20000 entries [[x, y, z, u, v] x 3]')
    for t in tris:
        if not (isinstance(t, list) and len(t) == 3 and all(isinstance(c, list) and len(c) == 5 and
                                                             all(isinstance(x, (int, float)) and math.isfinite(x) for x in c) for c in t)):
            raise ExtError('triangle: [[x, y, z, u, v], [..], [..]] with finite numbers')
    return e


def _apply_append(M, F, e, notes):
    st, sm = F['static.dat'], F['streamed.dat']
    T = M['xbtopo']
    tbl, ut = _unit_table(st)
    u = e['unit']
    if not (isinstance(u, int) and 0 <= u < len(ut) and ut[u][2]):
        raise ExtError('unit %r: not a non-empty unit of this track' % (u,))
    mo, lo, ms, ls = ut[u]
    mb, lb = sm[mo:mo + ms], sm[lo:lo + ls]
    model = T.MeshModel(mb)
    rows = struct.unpack_from('<b', mb, 0x71)[0]
    mats = list(struct.unpack_from('<83h', mb, 0x84))
    heads = list(struct.unpack_from('<83b', mb, 0x12A + 3))
    sobj = M['xbmesh'].Static(st)
    host = None
    avail = []
    for r in range(max(0, rows)):
        m = mats[r]
        t = sobj.mat[m]['tex'][0] if 0 <= m < len(sobj.mat) and sobj.mat[m].get('tex') else None
        tn = sobj.tex[t]['name'] if isinstance(t, int) else None
        avail.append(tn)
        h = heads[r]
        if tn == e['texture'] and 0 <= h < len(model.recs) and model.recs[h]['prim'] == 6 and host is None:
            k = h
            while model.recs[k]['next'] >= 0:                 # append at the END of the chain (retail chains: length 1)
                k = model.recs[k]['next']
            host = (r, m, k)
    if host is None:
        raise ExtError('unit %d has no strip record with texture %s; materials of this unit: %s (an extension can only reuse '
                       'materials the unit already draws)' % (u, e['texture'], ', '.join(sorted({a for a in avail if a}))))
    region = [list(struct.unpack_from('<4f', lb, 0x70)), list(struct.unpack_from('<4f', lb, 0x80)), list(struct.unpack_from('<4f', lb, 0x90))]
    hv = [model.verts[i] for i in model.recs[host[2]]['idx'][:200] if i < len(model.verts)]
    cols = sorted(v[4] for v in hv) or [0xFF808080]
    colour = e.get('colour') or cols[len(cols) // 2]
    verts, tris = [], []
    outside = 0
    for t in e['triangles']:
        n = _norm(t[0][:3], t[1][:3], t[2][:3])
        base = len(verts)
        for c in t:
            if not in_region(region, c[0], c[2], 0.01):
                outside += 1
            verts.append((float(c[0]), float(c[1]), float(c[2]), T.pack_normal(n), int(colour), float(c[3]), float(c[4])))
        tris.append((base, base + 1, base + 2))
    if outside:
        raise ExtError('%d vertex(es) lie outside unit %d\'s region quad: place the geometry inside the unit (KB writer rule)' % (outside, u))
    k = T.add_record(model, verts, tris, host[2])
    T.grow_prism(model, [v[:3] for v in verts])
    out = model.serialize(ms, grow=True)
    if len(out) > MESH_SLOT:
        raise ExtError('unit %d mesh block would need 0x%X bytes > the game\'s slot 0x%X: smaller extension or another unit (%s)' % (
            u, len(out), MESH_SLOT, EXT_CAP_NOTE % ('full_unit_bytes', (len(out) + 0xFFF) & ~0xFFF)))
    chk = T.MeshModel(out)
    if chk.serialize(len(out)) != out:
        raise ExtError('internal: the edited mesh block does not re-serialise identically')
    notes.append({'unit': u, 'record': k, 'host_record': host[2], 'row': host[0], 'material': host[1], 'texture': e['texture'],
                  'triangles': len(tris), 'vertices': len(verts), 'colour': '0x%08X' % colour, 'mesh_size_before': ms,
                  'mesh_size_after': len(out), 'records_after': len(chk.recs)})
    return u, out


def _hexword(v):
    try:
        w = int(v, 16)
    except (TypeError, ValueError):
        return None
    return w if 0 <= w <= 0xFFFF else None


LEAF_QUADS = 8                                            # retail C3: about 4.8 quads per leaf (CT1)


def _v3(a, b):
    return [b[i] - a[i] for i in range(3)]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(v):
    L = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / L for c in v]


def _apply_collision(M, F, e, notes, u):
    """the edit's triangles also become COLLISION in unit u's LOD tree (xbtopo.add_leaves: the retail tree kept under a new
    root pair). Surface: explicit word, or 'auto' = the nearest retail quad of the same kind (floor if |n.y| >= 0.94, else wall);
    lighting index per corner = the nearest retail collision vertex's (both CT1 rules, CT1 RT: ramp driven 17/17, a control
    without collision drove through). -> new LOD block bytes"""
    T, Cm = M['xbtopo'], M['collision']
    st, sm = F['static.dat'], F['streamed.dat']
    _tbl, ut = _unit_table(st)
    mo, lo, ms, ls = ut[u]
    nprop = struct.unpack_from('<h', st, 0x34)[0]
    lm = T.LodModel(sm[lo:lo + ls], nprop)
    qs = []
    for lf in lm.tree.leaves:
        for q in lf.quads:
            vs = [lf.verts[q[i]] for i in range(4) if q[i] != 0xFF]
            if len(vs) < 3:
                continue
            n = _unit(_cross(_v3(vs[0], vs[1]), _v3(vs[0], vs[2])))
            light = struct.unpack_from('<4H', q, 6)
            qs.append({'floor': abs(n[1]) >= 0.94, 'surf': struct.unpack_from('<H', q, 4)[0],
                       'corners': [(lf.verts[q[i]], light[i]) for i in range(4) if q[i] != 0xFF]})
    if not qs:
        raise ExtError('unit %d has no retail collision quads to take surface / lighting from' % u)
    req = (e.get('collision') or {}).get('surface', 'auto')
    recs = []
    for t in e['triangles']:
        vs = [tuple(float(x) for x in c[:3]) for c in t]
        n = _unit(_cross(_v3(vs[0], vs[1]), _v3(vs[0], vs[2])))
        floor = abs(n[1]) >= 0.94
        if req == 'auto':
            cen = [sum(v[k] for v in vs) / 3 for k in range(3)]
            best, bd = None, 1e30
            for q in qs:
                # only CAR-SOLID retail words (no 0x1000: the car's collision query skips those - kit RT gp_trk_1: cars passed
                # through 0x181C walls), for walls AND floors (a roof with 0x1000 would let a landing car fall through)
                if q['floor'] != floor or q['surf'] & 0x1000:
                    continue
                for v, _li in q['corners']:
                    d = sum((v[k] - cen[k]) ** 2 for k in range(3))
                    if d < bd:
                        best, bd = q, d
            if best is None:
                raise ExtError('unit %d has no retail %s quad to take a surface word from: give collision.surface' % (u, 'floor' if floor else 'car-solid wall'))
            surf = best['surf']
        else:
            surf = _hexword(req)
            if surf & 0x1000:
                raise ExtError('collision.surface 0x%04X has flag 0x1000 (the car collision query skips it): not solid' % surf)
        light = []
        for p in vs:
            li, bd = 0, 1e30
            for q in qs:
                for v, l_ in q['corners']:
                    d = sum((v[k] - p[k]) ** 2 for k in range(3))
                    if d < bd:
                        li, bd = l_, d
            light.append(li)
        recs.append((vs, surf, light + [0], floor))
    groups, done = [recs], []
    while groups:
        g = groups.pop()
        if len(g) <= LEAF_QUADS:
            done.append(g)
            continue
        cs = [[sum(v[k] for v in r[0]) / 3 for k in range(3)] for r in g]
        ax = max(range(3), key=lambda k: max(c[k] for c in cs) - min(c[k] for c in cs))
        order = sorted(range(len(g)), key=lambda j: cs[j][ax])
        h = len(g) // 2
        groups += [[g[j] for j in order[:h]], [g[j] for j in order[h:]]]
    leaves = []
    ntab = (lm.tree_off - 0xB0) // 9
    for g in sorted(done, key=lambda g: min(min(v for v in r[0]) for r in g)):
        pts, idx = [], {}
        lq = []
        for vs, surf, light, _f in g:
            ii = []
            for p in vs:
                if p not in idx:
                    idx[p] = len(pts)
                    pts.append(p)
                ii.append(idx[p])
            if max(light) >= ntab:
                raise ExtError('lighting index outside unit %d\'s table' % u)
            lq.append((ii[0], ii[1], ii[2], 0xFF, surf, tuple(light)))
        try:
            leaves.append(T.make_leaf(pts, lq))
        except T.TopoError as ex:
            raise ExtError('unit %d collision leaf: %s' % (u, ex))
    n_before = len(lm.tree.leaves)
    try:
        T.add_leaves(lm, leaves)
    except T.TopoError as ex:
        raise ExtError('unit %d collision tree: %s' % (u, ex))
    out = lm.serialize(ls, grow=True)
    if len(out) > LOD_SLOT:
        raise ExtError('unit %d LOD block would need 0x%X bytes > the game\'s slot 0x%X (it holds the far mesh AND the full collision; %s)' % (
            u, len(out), LOD_SLOT, EXT_CAP_NOTE % ('low_unit_bytes', (len(out) + 0xFFF) & ~0xFFF)))
    chk = T.LodModel(out, nprop)
    if chk.serialize(len(out)) != out or Cm.check(chk.tree):
        raise ExtError('internal: the grown LOD block does not re-serialise identically / its tree fails the check')
    # offline hit probe: every new triangle is found by a short segment through its centre along its normal (all leaves)
    tri_all = []
    for lf in chk.tree.leaves[n_before:]:
        for q in lf.quads:
            v = [lf.verts[q[i]] for i in range(3)]
            tri_all.append(v)
    hits = 0
    for vs, _s, _l, _f in recs:
        cen = [sum(v[k] for v in vs) / 3 for k in range(3)]
        n = _unit(_cross(_v3(vs[0], vs[1]), _v3(vs[0], vs[2])))
        p0 = [cen[k] + 0.3 * n[k] for k in range(3)]
        d = [-0.6 * n[k] for k in range(3)]
        if any(_seg_hits(p0, d, t) for t in tri_all):
            hits += 1
    notes.append({'unit': u, 'collision': {'triangles': len(recs), 'leaves_added': len(leaves), 'leaves_before': n_before,
                                           'surfaces': sorted({'0x%04X' % r[1] for r in recs}),
                                           'floors': sum(1 for r in recs if r[3]), 'walls': sum(1 for r in recs if not r[3]),
                                           'probe_hits': '%d / %d' % (hits, len(recs)), 'lod_size_before': ls, 'lod_size_after': len(out),
                                           'non_solid_wall_words': sorted({'0x%04X' % r[1] for r in recs if r[1] & 0x1000}),
                                           'rule': 'CT1: surface auto = nearest retail quad of the same kind (car-solid words only, no '
                                                   '0x1000); lighting = nearest retail vertex'}})
    if hits != len(recs):
        raise ExtError('collision probe: %d of %d new faces not found in the grown tree' % (len(recs) - hits, len(recs)))
    return out


def _seg_hits(p0, d, t):
    a, b, c = t
    e1, e2 = _v3(a, b), _v3(a, c)
    h = _cross(d, e2)
    det = sum(e1[k] * h[k] for k in range(3))
    if abs(det) < 1e-12:
        return False
    f = 1 / det
    sv = _v3(a, p0)
    uu = f * sum(sv[k] * h[k] for k in range(3))
    if uu < -1e-6 or uu > 1 + 1e-6:
        return False
    q = _cross(sv, e1)
    vv = f * sum(d[k] * q[k] for k in range(3))
    if vv < -1e-6 or uu + vv > 1 + 1e-6:
        return False
    return -1e-6 <= f * sum(e2[k] * q[k] for k in range(3)) <= 1 + 1e-6


def build(cfg, proj_dir, out_dir):
    """apply the project's edits -> a complete track folder in out_dir (NEW) + EXTENSION_BUILD.json"""
    proj = load_project(proj_dir)
    why = check_source(proj)
    if why:
        raise ExtError(why)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise ExtError('%s exists and is not empty' % out_dir)
    M, used = readers(cfg)
    F = _read_all(proj['retail_folder'])
    orig = dict(F)
    notes = []
    new_blocks = {}
    for e in proj['edits']:
        check_edit(e)
        F2 = dict(F)
        u, blk = _apply_append(M, F2, e, notes)
        nb = {(u, 'mesh'): blk}
        if 'collision' in e:
            nb[(u, 'lod')] = _apply_collision(M, F, e, notes, u)
        F = _retile(M, F, nb)
        new_blocks = {}
    # strict re-check of every output
    rep = round_trip(cfg, proj['retail_folder'], F)
    st0, st1 = orig['static.dat'], F['static.dat']
    diff = [i for i in range(len(st0)) if st0[i] != st1[i]] if len(st0) == len(st1) else None
    tbl, ut = _unit_table(st1)
    in_table = diff is not None and all(tbl <= i < tbl + 16 * len(ut) for i in diff)
    _t0, ut0 = _unit_table(st0)
    changed, moved, same = [], [], []
    for uu, (a, b) in enumerate(zip(ut0, ut)):
        for kind, i_off, i_size in (('mesh', 0, 2), ('lod', 1, 3)):
            ob = orig['streamed.dat'][a[i_off]:a[i_off] + a[i_size]]
            nb = F['streamed.dat'][b[i_off]:b[i_off] + b[i_size]]
            if ob != nb:
                changed.append('unit %d %s' % (uu, kind))
            elif a[i_off] != b[i_off]:
                moved.append('unit %d %s' % (uu, kind))
            else:
                same.append('unit %d %s' % (uu, kind))
    files = {}
    for n in sorted(F):
        files[n] = {'sha256': sha(F[n]), 'size': len(F[n]), 'changed': F[n] != orig[n]}
    ok = rep['all_identical'] and (diff is not None) and in_table
    os.makedirs(out_dir, exist_ok=True)
    for n, b in F.items():
        with open(os.path.join(out_dir, n), 'wb') as f:
            f.write(b)
    rec = {'schema': SCHEMA + '-build', 'project': proj['title'], 'track': proj['track'], 'edits': len(proj['edits']),
           'verdict': 'PASS' if ok else 'FAIL', 'strict_recheck_of_outputs': rep['verdict'],
           'static_changed_bytes': len(diff) if diff is not None else 'size changed', 'static_changes_only_in_unit_table': in_table,
           'streamed_blocks': {'changed': changed, 'moved_unchanged_bytes': len(moved), 'unchanged_in_place': len(same)},
           'files': files, 'edit_notes': notes, 'readers_sha256': used, 'local_only': True,
           'semantics': ['appended records are drawn wherever their host record is drawn, with the host material (KB s4, CT1 RT)',
                         ('collision: %d edit(s) also add COLLISION leaves to their unit\'s tree (xbtopo.add_leaves, CT1 rule; '
                          'RUNTIME-UNVERIFIED for this use)' % sum(1 for e in proj['edits'] if 'collision' in e))
                         if any('collision' in e for e in proj['edits']) else 'decorative only: NO collision',
                         'not in the far LOD (drawn where the unit full mesh is drawn, |rel| <= 4)',
                         'untouched sections are byte-identical (unchanged in place) or byte-identical at a new offset (moved)'],
           'runtime': 'NOT RUN: offline acceptance is not gameplay proof'}
    with open(os.path.join(out_dir, 'EXTENSION_BUILD.json'), 'w', encoding='utf-8') as f:
        json.dump(rec, f, indent=1, sort_keys=True)
    if not ok:
        raise ExtError('build output failed the strict re-check (see %s)' % os.path.join(out_dir, 'EXTENSION_BUILD.json'))
    return rec


def _retile(M, F, new_blocks):
    """STREAMED.DAT with replaced blocks laid out in the original order (later blocks move by whole pages), STATIC unit table
    entries updated in place (no other STATIC byte)"""
    st, sm = bytearray(F['static.dat']), F['streamed.dat']
    tbl, ut = _unit_table(bytes(st))
    order = []
    for u, (mo, lo, ms, ls) in enumerate(ut):
        if ms:
            order.append((mo, u, 'mesh', ms))
        if ls:
            order.append((lo, u, 'lod', ls))
    order.sort()
    out = bytearray()
    pos = 0
    for off, u, kind, size in order:
        if off > pos:                                   # a retail gap between blocks: kept as it is
            out += sm[pos:off]
        elif off < pos:
            raise ExtError('blocks overlap in streamed.dat: re-tiling refused')
        b = new_blocks[(u, kind)] if (u, kind) in new_blocks else sm[off:off + size]
        new_off = len(out)
        out += b
        e = ut[u]
        if kind == 'mesh':
            e[0], e[2] = new_off, len(b)
        else:
            e[1], e[3] = new_off, len(b)
        pos = off + size
    out += sm[pos:]
    for u, e in enumerate(ut):
        struct.pack_into('<4I', st, tbl + 16 * u, *e)
    G = dict(F)
    G['static.dat'] = bytes(st)
    G['streamed.dat'] = bytes(out)
    o, dg = M['b3static'].parse(G['static.dat'], 'b3')
    if dg.rules or o['garbage'] or M['b3static'].build(o, 'b3') != G['static.dat']:
        raise ExtError('the re-tiled static.dat is not strict (unit table rewrite refused)')
    return G
