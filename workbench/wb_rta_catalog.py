r"""wb_rta_catalog - LOCAL asset library: a read-only, cached catalogue of the user's own Burnout 3 game data
(Workbench 0.33 retail-style authoring, retail-style track authoring, 2026-11-01).

What it does
- Finds the track folders of a user-selected game data folder (Tracks\RR\NN_VN with static.dat, streamed.dat, Gamedata.bgd).
- Per track, through the EXISTING verified readers only (no new parser):
    wb_retail.decode      textures / materials / render classes (+0x24 flags) / mesh groups / collision / route / units
    fr_propmesh           instance models (lamps, trees, signs, ...) and smashable prop types, with placements
    fr_enviro             enviro.dat (sky slots, sun / light colours; fog HYP)
  and measures, against the track's own AI route centre line: area, facing (up / vertical), distance from the route and height
  above it per texture; setback, spacing and size per instance model; free capacity per unit.
- Roles ("road surface", "barrier / wall", "building facade", ...) are MEASURED geometry classes with their numbers, never
  game semantics; anything that fits no class is "unclassified". Texture names are shown, never used to decide a role.
- Cache: <state>\rta_catalogue\<RR_NN_VN>-<key12>\catalogue.json, key = sha256 of the catalogue schema + every source file's
  sha256 (static, streamed, Gamedata, enviro). The source folder is compared (sha256 / size / mtime) before and after; source
  data is never written; no imported script is ever executed (the readers parse bytes only).
- Labels: every asset says whether using it in an authored track is a GEOMETRY COPY (counts in the unit slots) or would be a REAL
  INSTANCE (not supported: no instance writer); smashable props are READ ONLY (no prop writer).
- LOCAL ONLY: the cache holds decoded retail data (thumbnails, measurements). Never package, share or upload it.

CLI (developer use; the editor exposes the same through its Retail-style panel):
    py -3 -B wb_rta_catalog.py build  [GAME_DATA] [--tracks US/C1_V1,EU/M1_V1] [--force]
    py -3 -B wb_rta_catalog.py show   US/C1_V1
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
import wb_rta_geo as G

SCHEMA = 'bm-rta-catalogue/2'   # /2: facade role renamed (cliffs measure the same)
HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, 'format_research')
MESH_SLOT, LOD_SLOT = 0x28000, 0x18000        # the GAME's default slots (retail pool layout); RTA5: the host can raise them per mod
                                               # (kit trackbuild.capacity); the catalogue reports free bytes of RETAIL units vs the game
BYTES_PER_TRI = 52.0                          # MEASURED below per track (mesh bytes / triangles); this is only the fallback
ROLE_NOTE = ('roles are MEASURED geometry classes (facing, distance from the AI route centre line, height above it), not '
             'game semantics; names are shown, never used to decide')


class CatalogError(Exception):
    pass


class Cancelled(Exception):
    pass


def _fr():
    for p in (FR, os.path.join(FR, 'props_mesh')):
        if p not in sys.path:
            sys.path.insert(0, p)
    import fr_propmesh
    import fr_enviro
    return fr_propmesh, fr_enviro


def cat_root(cfg):
    return os.path.join(cfg.get('state') or os.path.join(HERE, 'state'), 'rta_catalogue')


def discover(game_data):
    """-> list of {'track': 'US/C1_V1', 'folder': ...} for every Tracks\\RR\\NN_VN holding the three required files"""
    root = os.path.join(game_data or '', 'Tracks')
    if not os.path.isdir(root):
        raise CatalogError('no Tracks folder in %r: choose the folder that holds your Burnout 3 game data (it has Tracks\\US, '
                           'Tracks\\EU, ...)' % game_data)
    out = []
    for rr in sorted(os.listdir(root)):
        rp = os.path.join(root, rr)
        if not os.path.isdir(rp) or len(rr) != 2:
            continue
        for t in sorted(os.listdir(rp)):
            tp = os.path.join(rp, t)
            if os.path.isdir(tp) and all(os.path.isfile(os.path.join(tp, n)) for n in wb_retail.REQUIRED):
                out.append({'track': '%s/%s' % (rr, t), 'folder': tp})
    return out


def _key(state):
    blob = json.dumps({'schema': SCHEMA, 'files': {n: v['sha256'] for n, v in sorted(state.items())}}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _full_state(folder):
    st = wb_retail.source_state(folder)
    for n in ('enviro.dat',):
        p = os.path.join(folder, n)
        if os.path.isfile(p) and n not in st:
            s = os.stat(p)
            st[n] = {'sha256': wb_retail.sha_file(p), 'size': s.st_size, 'mtime_ns': s.st_mtime_ns}
    return st


def _role(up, vert, dist, dy, render):
    """measured class from area fractions (up-facing |ny| >= 0.85, vertical |ny| <= 0.3), median plan distance from the route
    centre line and median height above it. Thresholds are this tool's (stated in the catalogue), not the game's."""
    if render in ('cutout', 'blend', 'blend+test'):
        if vert >= 0.5:
            return 'cut-out / blended card (foliage, fence, sign: shown with transparency)'
        return 'cut-out / blended surface (decal, shadow, glass)'
    if dist is None:
        return 'unclassified (no route nearby)'
    if up >= 0.75 and dist <= 9 and abs(dy) <= 1.5:
        return 'road surface'
    if up >= 0.75 and dist <= 30 and -1.0 <= dy <= 2.5:
        return 'pavement / verge'
    if up >= 0.6 and dy > 3.0:
        return 'roof / raised surface'
    if up >= 0.6 and dist > 30:
        return 'ground / terrain'
    if vert >= 0.6 and dist <= 16 and dy <= 4.0:
        return 'barrier / wall'
    if vert >= 0.5 and dist > 8 and dy > 2.0:
        return 'tall vertical surface (facade / cliff)'
    if up >= 0.6:
        return 'ground / terrain'
    return 'unclassified'


def _model_role(size, render):
    x, y, z = size
    plan = max(x, z)
    if render in ('cutout', 'blend', 'blend+test') and y >= 3:
        return 'tree / foliage (cut-out: a copy would be an opaque block)'
    if y >= 4.5 and plan <= 6.0 and min(x, z) <= 1.2:
        return 'post / pole (lamp, light, pylon)'
    if y >= 4.5:
        return 'tall structure'
    if y < 2.5 and plan <= 3:
        return 'small street furniture'
    return 'object'


def build_track(cfg, folder, track_id=None, force=False, cancel=None, progress=None):
    """-> (catalogue dict, cache dir, reused). Raises CatalogError (nothing cached) or Cancelled (nothing cached)."""
    def chk(msg, f=None):
        if cancel and cancel():
            raise Cancelled('cancelled at: %s' % msg)
        if progress:
            progress(f, msg)

    before = _full_state(folder)
    key = _key(before)
    tid = track_id or wb_retail.track_id_of(folder) or os.path.basename(folder)
    cdir = os.path.join(cat_root(cfg), '%s-%s' % (tid.replace('/', '_'), key[:12]))
    cp = os.path.join(cdir, 'catalogue.json')
    if not force and os.path.isfile(cp):
        try:
            c = json.load(open(cp, encoding='utf-8'))
            if c.get('schema') == SCHEMA and c.get('cache_key') == key:
                return c, cdir, True
        except (OSError, ValueError):
            pass
    t0 = time.time()
    chk('decode %s (verified kit readers)' % tid, 0.05)
    try:
        view, vdir, _ = wb_retail.decode(cfg, folder)
    except wb_retail.RetailError as e:
        raise CatalogError('%s: %s' % (tid, e))
    fr_propmesh, fr_enviro = _fr()
    lines, cyc = G.route_lines(view)
    R = G.RouteIndex(lines, cyc) if lines else None
    blob = open(os.path.join(vdir, 'mesh.bin'), 'rb').read()
    chk('measure textures against the route', 0.3)
    tex = {}
    tris_total = 0
    for e in view['mesh']:
        nm = e['texture_name'] or '(no texture)'
        nv, ni = e['vertices'], e['indices']
        P = struct.unpack_from('<%df' % (3 * nv), blob, e['off_pos'])
        idx = struct.unpack_from('<%dI' % ni, blob, e['off_idx'])
        t = tex.setdefault(nm, {'texture': nm, 'texture_index': e['texture'], 'materials': set(), 'render': set(), 'area': 0.0,
                                'up': 0.0, 'vert': 0.0, 'tris': 0, 'd': [], 'dy': [], 'lat': [], 'units': set(),
                                'bmin': [1e18] * 3, 'bmax': [-1e18] * 3})
        t['materials'].add(e['material'])
        t['render'].add(e['render'])
        step = max(1, (ni // 3) // 400)                     # at most ~400 route samples per group (bounded time)
        for k in range(0, ni - 2, 3):
            a, b, c = idx[k], idx[k + 1], idx[k + 2]
            pa, pb, pc = P[3 * a:3 * a + 3], P[3 * b:3 * b + 3], P[3 * c:3 * c + 3]
            ar, n, cen = G.tri_geo(pa, pb, pc)
            t['area'] += ar
            t['tris'] += 1
            if abs(n[1]) >= 0.85:
                t['up'] += ar
            elif abs(n[1]) <= 0.3:
                t['vert'] += ar
            for i in range(3):
                t['bmin'][i] = min(t['bmin'][i], cen[i])
                t['bmax'][i] = max(t['bmax'][i], cen[i])
            if R and (k // 3) % step == 0 and ar > 0.05:
                pr = R.project(*cen)
                if pr:
                    t['d'].append(pr['dist'])
                    t['dy'].append(pr['dy'])
        tris_total += ni // 3
    alpha = view.get('texture_alpha') or {}
    textures = []
    for nm, t in sorted(tex.items(), key=lambda kv: -kv[1]['area']):
        a = t['area'] or 1e-9
        up, vert = t['up'] / a, t['vert'] / a
        dmed, dymed = G.pct(t['d'], 50), G.pct(t['dy'], 50)
        render = sorted(t['render'])
        ti = t['texture_index']
        ta = alpha.get(str(ti)) if ti is not None else None
        mem = None
        if ta:
            bpp = {'0x0C': 4, '0x0E': 8, '0x0F': 8}.get(ta['format'], 32)
            mem = int(ta['w'] * ta['h'] * bpp / 8 * 4 / 3)
        textures.append({
            'id': 'T:%s' % nm, 'texture': nm, 'texture_index': ti, 'materials': sorted(t['materials']), 'render': render,
            'size': [ta['w'], ta['h']] if ta else None, 'format': ta['format'] if ta else None,
            'memory_bytes_est': mem, 'area_m2': round(t['area'], 1), 'triangles': t['tris'],
            'facing': {'up': round(up, 3), 'vertical': round(vert, 3)},
            'route_distance_m': G.stats(t['d'], 1), 'height_above_route_m': G.stats(t['dy'], 1),
            'role': _role(up, vert, dmed, dymed if dymed is not None else 0.0, render[0] if len(render) == 1 else 'opaque'),
            'thumbnail': ('tex', ti) if ti is not None and os.path.isfile(os.path.join(vdir, 'tex', 't%03d.png' % ti)) else None,
            'uses': ['retail_texture (material for authored roads / walls / ground: copy of the texels)',
                     'retail_region (part of a geometry copy)'] if render == ['opaque'] else
                    ['not usable as an authored material (trackbuild materials are opaque); visible only inside retail data'],
            'kind': 'texture'})
    chk('instance models and props', 0.65)
    try:
        trk = fr_propmesh.load(folder)
        listing = trk.listing()
    except Exception as e:  # noqa: BLE001   a reader refusal is reported, not hidden
        trk, listing = None, {'error': '%s: %s' % (type(e).__name__, e)}
    render_of_tex = {}
    for m in view.get('materials') or []:
        for tn in m.get('textures') or []:
            if isinstance(tn, str):
                render_of_tex.setdefault(tn, m['render'])
    models = []
    for rec in (listing.get('instance_models') or []) if trk else []:
        fam, k = 'I', rec['index']
        try:
            pl = trk.placements(fam, k)
        except Exception:  # noqa: BLE001
            pl = []
        setb, side, s_list, base_dy = [], [], [], []
        for p in pl:
            m = p.get('matrix')
            if not m or not R:
                continue
            pos = (m[12], m[13], m[14]) if len(m) >= 15 else None
            if pos is None:
                continue
            pr = R.project(*pos)
            if pr:
                setb.append(abs(pr['lateral']))
                side.append(1 if pr['lateral'] > 0 else -1)
                s_list.append((pr['line'], pr['s']))
                base_dy.append(pr['dy'])
        gaps = []
        s_list.sort()
        for i in range(1, len(s_list)):
            if s_list[i][0] == s_list[i - 1][0]:
                g = s_list[i][1] - s_list[i - 1][1]
                if 0.5 < g < 400:
                    gaps.append(g)
        size = rec.get('size_xyz') or [0, 0, 0]
        texn = rec.get('texture')
        mi = (rec.get('lods') or [{}])[0].get('material')
        mats = view.get('materials') or []
        rnd = mats[mi]['render'] if isinstance(mi, int) and 0 <= mi < len(mats) else render_of_tex.get(texn, 'opaque')
        models.append({
            'id': 'I%d' % k, 'kind': 'instance model', 'texture': texn, 'render': rnd, 'size_m': size,
            'triangles_lod0': (rec.get('lods') or [{}])[0].get('triangles'), 'lods': len(rec.get('lods') or []),
            'draw_distance_m': rec.get('draw_dist'), 'placements': rec.get('placements'),
            'setback_m': G.stats(setb, 1), 'spacing_m': G.stats(gaps, 1), 'base_above_route_m': G.stats(base_dy, 1),
            'left_fraction': round(sum(1 for s in side if s > 0) / len(side), 2) if side else None,
            'role': _model_role(size, rnd),
            'use': 'GEOMETRY COPY along a route (retail_lamps: double-sided, no vertex colour, collision none); a REAL instance '
                   'would need the instance writer (not built)' + ('; CUT-OUT texture -> the copy would be an opaque block: '
                                                                  'not offered' if rnd != 'opaque' else ''),
            'thumbnail': ('model', 'I%d' % k)})
    props = []
    for rec in (listing.get('prop_types') or []) if trk else []:
        props.append({'id': 'P%d' % rec['index'], 'kind': 'smashable prop type', 'texture': rec.get('texture'),
                      'size_m': rec.get('size_xyz'), 'placements': rec.get('placements'), 'class_byte': rec.get('class_byte'),
                      'use': 'READ ONLY: placements are decoded (format_research 2) but no prop writer exists and the run-time '
                             'prop pool size is unknown',
                      'thumbnail': ('model', 'P%d' % rec['index'])})
    chk('environment and dependencies', 0.85)
    env = {'status': 'no enviro.dat'}
    ep = os.path.join(folder, 'enviro.dat')
    if os.path.isfile(ep):
        try:
            with open(ep, 'rb') as f:
                eo = fr_enviro.parse(f.read())
            env = {'summary': fr_enviro.summary(eo),
                   'evidence': 'fr_enviro (byte-identical round trip 37/37); sky slots + sun / light consumers CODE; fog fields HYP',
                   'use': 'a build copies the DONOR enviro.dat unchanged; no editing (no verified writer / no in-game check)'}
        except Exception as e:  # noqa: BLE001
            env = {'error': '%s: %s' % (type(e).__name__, e)}
    deps = []
    for n in sorted(os.listdir(folder)):
        p = os.path.join(folder, n)
        if os.path.isfile(p) and n not in wb_retail.REQUIRED and n != 'enviro.dat':
            deps.append({'file': n, 'size': os.path.getsize(p), 'use': 'audio / music: copied unchanged from the donor by a build; '
                                                                       'not decoded'})
    units = []
    mesh_b = lod_b = 0
    for u in view.get('units') or []:
        if u.get('empty'):
            units.append({'unit': u['unit'], 'empty': True})
            continue
        mesh_b += u['mesh_bytes']
        lod_b += u['lod_bytes']
        units.append({'unit': u['unit'], 'records': u['records'], 'vertices': u['vertices'],
                      'mesh_bytes': u['mesh_bytes'], 'lod_bytes': u['lod_bytes'],
                      'mesh_free_bytes': MESH_SLOT - u['mesh_bytes'], 'lod_free_bytes': LOD_SLOT - u['lod_bytes'],
                      'records_free': 127 - u['records'], 'corners': [[round(c[0], 1), round(c[2], 1)] for c in u['corners']]})
    after = _full_state(folder)
    if after != before:
        raise CatalogError('%s: the source folder changed while it was read; nothing cached' % tid)
    cat = {'schema': SCHEMA, 'cache_key': key, 'track': tid, 'name': view.get('name'),
           'source': {'folder': folder, 'files': {n: {'sha256': v['sha256'], 'size': v['size']} for n, v in sorted(before.items())},
                      'unchanged_after_read': True},
           'view_cache': vdir, 'local_only': True,
           'notes': {'roles': ROLE_NOTE,
                     'copies': 'every asset used in an authored track is a GEOMETRY / TEXEL COPY from your own game data '
                               '(retail-derived, LOCAL ONLY); real instances and props have no writer',
                     'unknown': 'not decoded: S1 checkpoints / finish, S3 C slots 0 / 5, prop pool size, enviro fog fields, '
                                'audio contents'},
           'route': {'lines': len(lines), 'cyclic': any(cyc), 'lengths_m': R.lengths if R else []},
           'counts': {'textures': len(textures), 'instance_models': len(models), 'prop_types': len(props),
                      'mesh_triangles': tris_total, 'units': len(units)},
           'cost': {'mesh_bytes_per_triangle_measured': round(mesh_b / tris_total, 1) if tris_total else BYTES_PER_TRI,
                    'mesh_bytes_total': mesh_b, 'lod_bytes_total': lod_b},
           'textures': textures, 'instance_models': models, 'prop_types': props, 'environment': env,
           'dependencies': deps, 'units': units,
           'reader_checks': view.get('checks'), 'not_decoded': view.get('not_decoded'),
           'built_seconds': round(time.time() - t0, 2)}
    if listing.get('error'):
        cat['reader_problems'] = [listing['error']]
    os.makedirs(cat_root(cfg), exist_ok=True)
    tmp = cdir + '.tmp-%d' % os.getpid()
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    with open(os.path.join(tmp, 'catalogue.json'), 'w', encoding='utf-8') as f:
        json.dump(cat, f, indent=0, default=sorted)
    with open(os.path.join(tmp, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write('Retail-style authoring asset catalogue of YOUR game data (decoded measurements, thumbnails). LOCAL ONLY: never '
                'package, share or upload. Safe to delete; rebuilt on demand.\n')
    if os.path.isdir(cdir):
        shutil.rmtree(cdir)
    os.replace(tmp, cdir)
    chk('done', 1.0)
    return json.load(open(cp, encoding='utf-8')), cdir, False


def build(cfg, game_data=None, tracks=None, force=False, cancel=None, progress=None):
    """catalogue every (or the listed) track(s); -> index dict, also written to <cat_root>\\INDEX.json.
    A track that fails is listed with its error (others continue); a cancel stops between / inside tracks: finished tracks
    stay cached, the index is NOT rewritten (the previous index stays valid)."""
    gd = game_data or cfg.get('game_data')
    found = discover(gd)
    if tracks:
        want = set(tracks)
        missing = sorted(want - {f['track'] for f in found})
        found = [f for f in found if f['track'] in want]
        if missing:
            raise CatalogError('not found in this game data: %s' % ', '.join(missing))
    rows = []
    t0 = time.time()
    for i, f in enumerate(found):
        def prog(frac, msg, i=i, f=f):
            if progress:
                progress((i + (frac or 0)) / max(1, len(found)), '%s: %s' % (f['track'], msg))
        try:
            c, cdir, reused = build_track(cfg, f['folder'], f['track'], force, cancel, prog)
            rows.append({'track': f['track'], 'ok': True, 'cache': cdir, 'reused': reused, 'counts': c['counts'],
                         'seconds': c['built_seconds'], 'key': c['cache_key'][:12]})
        except Cancelled:
            raise
        except CatalogError as e:
            rows.append({'track': f['track'], 'ok': False, 'error': str(e)})
    idx = {'schema': SCHEMA + '-index', 'game_data': gd, 'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
           'seconds': round(time.time() - t0, 1), 'tracks': rows, 'local_only': True}
    os.makedirs(cat_root(cfg), exist_ok=True)
    p = os.path.join(cat_root(cfg), 'INDEX.json')
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(idx, f, indent=1)
    os.replace(p + '.tmp', p)
    return idx


def load(cfg, track):
    """the cached catalogue of one track (by id) from INDEX.json, verifying the source files' hashes again"""
    p = os.path.join(cat_root(cfg), 'INDEX.json')
    try:
        idx = json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        raise CatalogError('no catalogue yet: create it first (Retail-style -> 1 Asset library)')
    row = next((r for r in idx['tracks'] if r['track'] == track and r.get('ok')), None)
    if not row:
        raise CatalogError('%s is not in the catalogue (create / refresh the asset library)' % track)
    c = json.load(open(os.path.join(row['cache'], 'catalogue.json'), encoding='utf-8'))
    now = _full_state(c['source']['folder'])
    if {n: v['sha256'] for n, v in now.items()} != {n: v['sha256'] for n, v in c['source']['files'].items()}:
        raise CatalogError('%s: your game data changed since the catalogue was made: refresh the asset library' % track)
    try:                                                    # RTA3: what the BOUND kit can do with them (display only)
        import wb_rta_world as RW
        if RW.supported(cfg):
            for m in c.get('instance_models') or []:
                m['support'] = ('placeable as a REAL retail instance (trackbuild 0.3.2 retail_objects): decoration, NO collision '
                                '(as retail); material copied verbatim (%s); LOCAL ONLY' % m.get('render', '?'))
            for m in c.get('prop_types') or []:
                m['support'] = ('placeable as a REAL retail prop (trackbuild 0.3.2 retail_objects): the game makes a collision body '
                                'and the prop breaks when hit (retail record copied verbatim; RUNTIME-UNVERIFIED in authored tracks); '
                                'capacity <= retail maxima (741 / track, 66 / unit)')
                m['use'] = m['support']
    except Exception:  # noqa: BLE001   the catalogue stays usable without the kit
        pass
    return c


def search(cfg, query='', kind=None, role=None, tracks=None, limit=200):
    """flat search over every catalogued track -> rows (id, track, kind, role, name, size, uses)"""
    p = os.path.join(cat_root(cfg), 'INDEX.json')
    idx = json.load(open(p, encoding='utf-8'))
    q = (query or '').lower()
    out = []
    for r in idx['tracks']:
        if not r.get('ok') or (tracks and r['track'] not in tracks):
            continue
        c = json.load(open(os.path.join(r['cache'], 'catalogue.json'), encoding='utf-8'))
        for grp in ('textures', 'instance_models', 'prop_types'):
            for a in c[grp]:
                k = a['kind']
                if kind and k != kind:
                    continue
                if role and role not in (a.get('role') or ''):
                    continue
                nm = a.get('texture') or ''
                if q and q not in nm.lower() and q not in a['id'].lower() and q not in (a.get('role') or '').lower():
                    continue
                out.append({'track': r['track'], 'id': a['id'], 'kind': k, 'role': a.get('role'), 'name': nm,
                            'size': a.get('size') or a.get('size_m'), 'area_m2': a.get('area_m2'),
                            'placements': a.get('placements')})
                if len(out) >= limit:
                    return out
        op = os.path.join(r['cache'], 'objects.json')          # buildings / structures (wb_rta_objects), once built
        if os.path.isfile(op) and kind in (None, '', 'building', 'structure'):
            for p in json.load(open(op, encoding='utf-8')).get('pieces', []):
                if kind and p['class'] != kind:
                    continue
                tx = ' '.join(p['textures'])
                if q and q not in tx.lower() and q not in p['id'].lower() and q not in p['class']:
                    continue
                out.append({'track': r['track'], 'id': p['id'], 'kind': p['class'], 'role': p['class'], 'name': list(p['textures'])[0],
                            'size': p['footprint_m'] + [p['height_m']], 'triangles': p['triangles']})
                if len(out) >= limit:
                    return out
    return out


def main(argv):
    cfg = core.load_config()
    if not argv or argv[0] not in ('build', 'show'):
        print(__doc__)
        return 2
    if argv[0] == 'build':
        gd = argv[1] if len(argv) > 1 and not argv[1].startswith('--') else None
        tr = argv[argv.index('--tracks') + 1].split(',') if '--tracks' in argv else None
        idx = build(cfg, gd, tr, '--force' in argv,
                    progress=lambda f, m: print('%5.1f%% %s' % (100 * (f or 0), m), file=sys.stderr, flush=True))
        print(json.dumps({'ok': all(r['ok'] for r in idx['tracks']), 'tracks': len(idx['tracks']), 'seconds': idx['seconds'],
                          'failed': [r for r in idx['tracks'] if not r['ok']]}))
        return 0
    c = load(cfg, argv[1])
    print(json.dumps({k: c[k] for k in ('track', 'counts', 'route', 'cost')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
