"""RTA phase 3 - retail materials and retail objects in authored projects (needs the bound trackbuild >= 0.3.2-rta,
trackbuild 0.3.3). Everything here only WRITES the documented kit description keys:
  materials.<name>.retail_material = {track, material, static_sha256}     (verbatim retail material; the kit copies it)
  retail_objects = [{family, track, index, static_sha256, placements}]      (verbatim instance models / prop types)
and editor-side previews (RGBA PNG per retail texture under the project's textures\\rta_retail\\, an object mesh layer for the
3-D view built with the kit's own placement-matrix rule). Retail-derived: LOCAL ONLY. Nothing is guessed: render classes in the
preview come from the material flags exactly as the te2 retail viewer draws them (wb_retail.render_class; preview APPROXIMATE:
no sky / fog / lighting, blended surfaces sorted by centre).
Kinds of objects (labels shown to the user):
  instance  decoration drawn by the game's instance renderer; NO collision (cars pass through, as retail lamps / trees / signs)
  prop      retail prop type: the game makes a collision body per placement; hit props break (retail behaviour, copied
            verbatim; RUNTIME-UNVERIFIED in authored tracks)
  static    static-mesh copies (phase 1 / 2 'geometry copies'): drawn as track geometry, collision only when the material says so;
            never called smashable"""
import hashlib
import importlib
import json
import math
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = {'instance': 'decoration (no collision; instance renderer)', 'prop': 'retail prop: collision body, breaks when hit '
         '(retail behaviour copied; runtime-unverified here)', 'static': 'static mesh copy (track geometry; never smashable)'}
_SHA = {}
_FP = {}


def kit(cfg):
    """the bound trackbuild package (import from cfg['trackbuild']) -> module, version tuple"""
    tb = cfg['trackbuild']
    if tb not in sys.path:
        sys.path.insert(0, tb)
    m = importlib.import_module('trackbuild')
    v = tuple(int(x) for x in m.VERSION.split('.')[:3])
    return m, v


def supported(cfg):
    try:
        return kit(cfg)[1] >= (0, 3, 2)
    except Exception:  # noqa: BLE001
        return False


def static_path(cfg, track):
    return os.path.join(cfg['game_data'], 'Tracks', *track.split('/'), 'static.dat')


def static_sha(cfg, track):
    p = static_path(cfg, track)
    k = (p, os.path.getsize(p), os.path.getmtime(p))
    if k not in _SHA:
        with open(p, 'rb') as f:
            _SHA[k] = hashlib.sha256(f.read()).hexdigest()
    return _SHA[k]


def material_spec(cfg, track, mi):
    return {'track': track, 'material': int(mi), 'static_sha256': static_sha(cfg, track)}


def _fp(cfg, track):
    pm = os.path.join(HERE, 'format_research', 'props_mesh')
    if pm not in sys.path:
        sys.path.insert(0, pm)
    import fr_propmesh as FP
    folder = os.path.dirname(static_path(cfg, track))
    key = (track, _file_key(static_path(cfg, track)))
    if key not in _FP:
        if len(_FP) > 4:
            _FP.clear()
        _FP[key] = FP.load(folder)
    return _FP[key]


def png_rgba(w, h, rgba):
    raw = b''.join(b'\x00' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + \
        chunk(b'IEND', b'')


def material_info(cfg, track, mi):
    """-> {flags, render, depth_write, texture (name), w, h, rgba} of a retail material (read only)"""
    import wb_retail
    R = wb_retail.readers(cfg)[0]
    X = R['xbmesh']
    st = X.Static(wb_retail.read_ro(static_path(cfg, track)))
    m = st.mat[mi]
    f24 = struct.unpack_from('<I', st.d, m['rec'] + 0x24)[0]
    render, zw = wb_retail.render_class(f24)
    out = {'flags': '0x%X' % f24, 'render': render, 'depth_write': zw, 'texture': None}
    if m['tex'] and isinstance(m['tex'][0], int):
        t = st.tex[m['tex'][0]]
        rgba = bytes(X.decode_dxt(st.d, t['data'], t['w'], t['h'], t['format']))
        out.update(texture=t['name'], w=t['w'], h=t['h'], rgba=rgba)
    return out


def preview_png(cfg, project_root, track, mi):
    """write textures\\rta_retail\\<RR_NN_VN>_m<mi>.png (RGBA, preview only; the kit copies the texels verbatim) -> rel path"""
    info = material_info(cfg, track, mi)
    if info['texture'] is None:
        return None, info
    rel = 'textures/rta_retail/%s_m%d.png' % (track.replace('/', '_'), mi)
    p = os.path.join(project_root, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    b = png_rgba(info['w'], info['h'], info['rgba'])
    if not os.path.isfile(p) or open(p, 'rb').read() != b:
        with open(p, 'wb') as f:
            f.write(b)
    return rel, info


def object_types(cfg, track, family):
    """[(index, texture name, material flags, render, placements in the source)] of one family"""
    t = _fp(cfg, track)
    fam = 'I' if family == 'instance' else 'P'
    out = []
    for k in range(len(t.families[fam])):
        mi = t.record(fam, k)['lods'][0]['material']
        out.append({'index': k, 'texture': t.texture_of(fam, k, 0), 'flags': '0x%X' % t.mat[mi]['flags_24'],
                    'placements_in_source': len(t.placements(fam, k))})
    return out


_SRCM, _PARSED, _MESH = {}, {}, {}


def _file_key(p):
    return (p, os.path.getsize(p), os.path.getmtime(p))


def source_matrix(cfg, track, family, index):
    """the kit's own rule (trackbuild.retailobj._first_matrix): the first placement of that type in the source track. Cached by
    the source files' identity (path, size, mtime): one strict parse per track, one lookup per type (RTA3 bench: uncached, the
    preview layer of demo A took 155 s)"""
    _m, _v = kit(cfg)
    RO = importlib.import_module('trackbuild.retailobj')
    p = static_path(cfg, track)
    sp = os.path.join(os.path.dirname(p), 'streamed.dat')
    key = (_file_key(p), _file_key(sp), family, index)
    if key not in _SRCM:
        pk = (_file_key(p), _file_key(sp))
        if pk not in _PARSED:
            S = importlib.import_module('trackbuild._vendor.trackconv.b3static')
            if len(_PARSED) > 4:
                _PARSED.clear()
            _PARSED[pk] = (S.parse(open(p, 'rb').read(), 'b3')[0], open(sp, 'rb').read())
        o, sm = _PARSED[pk]
        _SRCM[key] = RO._first_matrix(o, sm if family == 'instance' else b'', family, index)
    return _SRCM[key], RO


def local_mesh(cfg, track, family, index):
    """LOD0 triangles in model space [(texture, [(pos, uv)] * 3)] (cached per source file identity and type)"""
    key = (_file_key(static_path(cfg, track)), family, index)
    if key not in _MESH:
        t = _fp(cfg, track)
        _MESH[key] = [(tn, [(p, uv) for p, uv, _c in cs]) for tn, cs in t.triangles('I' if family == 'instance' else 'P', index, 0)]
    return _MESH[key]


def fit_on_ground(cfg, track, family, index, pos_xz, ground_y, yaw_deg):
    """placement so the model's BASE (vertices within 0.5 m of its lowest point, after the kit's matrix) is centred on pos_xz and
    its lowest vertex sits 5 cm into the ground. Some retail models are modelled away from their origin (RTA3 screenshot: a bush
    on the road), so the origin itself is never assumed to be the base."""
    src, RO = source_matrix(cfg, track, family, index)
    if src is None:
        return None
    M = struct.unpack('<16f', RO.place_matrix(src, (0.0, 0.0, 0.0), yaw_deg))
    W = [(p[0] * M[0] + p[1] * M[4] + p[2] * M[8], p[0] * M[1] + p[1] * M[5] + p[2] * M[9], p[0] * M[2] + p[1] * M[6] + p[2] * M[10])
         for _tn, cs in local_mesh(cfg, track, family, index) for p, _uv in cs]
    ymin = min(w[1] for w in W)
    base = [w for w in W if w[1] < ymin + 0.5] or W
    cx, cz = sum(w[0] for w in base) / len(base), sum(w[2] for w in base) / len(base)
    return [round(pos_xz[0] - cx, 3), round(ground_y - ymin - 0.05, 3), round(pos_xz[1] - cz, 3)]


def base_offset(cfg, track, family, index):
    """distance (m) of the model's base centre from its origin - reported for transparency"""
    p = fit_on_ground(cfg, track, family, index, (0.0, 0.0), 0.0, 0.0)
    return None if p is None else round(math.hypot(p[0], p[2]), 2)


def heading_offset(cfg, track, family, index, local_dir):
    """the world heading (deg, from +Z toward +X) that the model's LOCAL direction (x, z) gets for yaw_deg = 0 under the kit's
    rule; so yaw = wanted heading - this"""
    src, RO = source_matrix(cfg, track, family, index)
    M = struct.unpack('<16f', RO.place_matrix(src, (0.0, 0.0, 0.0), 0.0))
    wx = local_dir[0] * M[0] + local_dir[1] * M[8]
    wz = local_dir[0] * M[2] + local_dir[1] * M[10]
    return math.degrees(math.atan2(wx, wz))


def object_layer(cfg, desc):
    """3-D preview of desc['retail_objects'] -> {meshes: [{key, texture key, render, depth_write, pos, uv, col, centre}], counts,
    problems}. Uses the kit's matrix rule, so the preview shows what the build writes (positions / turns exact; looks APPROXIMATE)."""
    import wb_retail
    out, problems, counts = {}, [], {'instance': 0, 'prop': 0}
    for k, e in enumerate(desc.get('retail_objects') or []):
        try:
            src, RO = source_matrix(cfg, e['track'], e['family'], e['index'])
            tris = local_mesh(cfg, e['track'], e['family'], e['index'])
        except Exception as ex:  # noqa: BLE001
            problems.append('retail_objects[%d]: %s' % (k, str(ex)[:160]))
            continue
        if src is None:
            problems.append('retail_objects[%d]: no source placement' % k)
            continue
        fam = 'I' if e['family'] == 'instance' else 'P'
        try:
            t = _fp(cfg, e['track'])
            f24 = t.mat[t.record(fam, e['index'])['lods'][0]['material']]['flags_24']
        except Exception:  # noqa: BLE001
            f24 = 0
        for pl in e.get('placements') or []:
            M = struct.unpack('<16f', RO.place_matrix(src, pl['pos'], pl.get('yaw_deg', 0.0)))
            counts[e['family']] = counts.get(e['family'], 0) + 1
            for tn, cs in tris:
                key = '%s|%s' % (e['track'], tn)
                m = out.setdefault(key, {'key': key, 'track': e['track'], 'texture': tn, 'pos': [], 'uv': [], 'col': [],
                                         'family': e['family'], 'f24': f24})
                for p, uv in cs:
                    m['pos'] += [round(p[0] * M[0] + p[1] * M[4] + p[2] * M[8] + M[12], 3),
                                 round(p[0] * M[1] + p[1] * M[5] + p[2] * M[9] + M[13], 3),
                                 round(p[0] * M[2] + p[1] * M[6] + p[2] * M[10] + M[14], 3)]
                    m['uv'] += [round(uv[0], 5), round(uv[1], 5)]
                    m['col'] += [0.5, 0.5, 0.5]
    # render class per texture from the material that uses it
    for m in out.values():
        m['render'], m['depth_write'] = wb_retail.render_class(m.pop('f24'))
        n = len(m['pos']) // 3
        m['centre'] = [sum(m['pos'][i::3]) / max(1, n) for i in range(3)]
    return {'meshes': list(out.values()), 'counts': counts, 'problems': problems, 'kinds': KINDS,
            'label': 'preview: positions / turns follow the kit rule exactly; looks APPROXIMATE (no lighting / fog)'}


def folder_instance_layer(cfg, folder, max_placements=4000):
    """RTA4: preview of a retail-format track folder's OWN instance placements (every unit's LOD tail: [+0xA8] u8 counts per
    type, [+0xAC] u32 pointers -> 0x40-byte matrices) drawn with the folder's own instance models (read only). Same mesh format as
    object_layer; texture keys '<folder>|<texture>'."""
    import wb_retail
    fp = _fp_folder(folder)
    st = open(os.path.join(folder, 'static.dat'), 'rb').read()
    sm = open(os.path.join(folder, 'streamed.dat'), 'rb').read()
    n_inst = struct.unpack_from('<h', st, 0x34)[0]
    tbl, nu = struct.unpack_from('<I', st, 0x58)[0], struct.unpack_from('<h', st, 0x54)[0]
    out, counts, cache = {}, {'instance': 0}, {}
    for u in range(nu):
        mo, lo, ms, ls = struct.unpack_from('<4I', st, tbl + 16 * u)
        if not ls:
            continue
        a8, ac = struct.unpack_from('<2I', sm, lo + 0xA8)
        for t in range(n_inst):
            c = sm[lo + 0xA8 + a8 + t]
            if not c:
                continue
            if t not in cache:
                try:
                    tris = [(tn, [(p, uv) for p, uv, _c in cs]) for tn, cs in fp.triangles('I', t, 0)]
                    f24 = fp.mat[fp.record('I', t)['lods'][0]['material']]['flags_24']
                except Exception:  # noqa: BLE001
                    tris, f24 = [], 0
                cache[t] = (tris, f24)
            tris, f24 = cache[t]
            ptr = struct.unpack_from('<I', sm, lo + 0xA8 + ac + 4 * t)[0]
            for j in range(c):
                if counts['instance'] >= max_placements:
                    break
                M = struct.unpack_from('<16f', sm, lo + 0xA8 + ptr + 0x40 * j)
                counts['instance'] += 1
                for tn, cs in tris:
                    key = '%s|%s' % (folder, tn)
                    m = out.setdefault(key, {'key': key, 'track': folder, 'texture': tn, 'pos': [], 'uv': [], 'col': [],
                                             'family': 'instance', 'f24': f24})
                    for pp, uv in cs:
                        m['pos'] += [round(pp[0] * M[0] + pp[1] * M[4] + pp[2] * M[8] + M[12], 3),
                                     round(pp[0] * M[1] + pp[1] * M[5] + pp[2] * M[9] + M[13], 3),
                                     round(pp[0] * M[2] + pp[1] * M[6] + pp[2] * M[10] + M[14], 3)]
                        m['uv'] += [round(uv[0], 5), round(uv[1], 5)]
                        m['col'] += [0.5, 0.5, 0.5]
    for m in out.values():
        m['render'], m['depth_write'] = wb_retail.render_class(m.pop('f24'))
        n = len(m['pos']) // 3
        m['centre'] = [sum(m['pos'][i::3]) / max(1, n) for i in range(3)]
    return {'meshes': list(out.values()), 'counts': counts, 'problems': [],
            'label': 'preview of this folder\'s own instance placements (LOD tails); looks APPROXIMATE (no lighting / fog)'}


def _fp_folder(folder):
    pm = os.path.join(HERE, 'format_research', 'props_mesh')
    if pm not in sys.path:
        sys.path.insert(0, pm)
    import fr_propmesh as FP
    key = ('folder', folder, _file_key(os.path.join(folder, 'static.dat')))
    if key not in _FP:
        if len(_FP) > 4:
            _FP.clear()
        _FP[key] = FP.load(folder)
    return _FP[key]


def object_texture(cfg, key):
    """'<track>|<texture name>' -> RGBA PNG bytes (preview only); RTA4: '<track folder>|<texture>' for a folder layer"""
    import wb_retail
    track, tn = key.split('|', 1)
    R = wb_retail.readers(cfg)[0]
    X = R['xbmesh']
    sp = os.path.join(track, 'static.dat') if os.path.isabs(track) and os.path.isdir(track) else static_path(cfg, track)
    st = X.Static(wb_retail.read_ro(sp))
    t = next(x for x in st.tex if x['name'] == tn)                 # first texture of that name (as the reader lists them)
    return png_rgba(t['w'], t['h'], bytes(X.decode_dxt(st.d, t['data'], t['w'], t['h'], t['format'])))


def desc_with_objects(desc, owner_entries, keep_others=True):
    """replace the entries a designer category owns (matched by identity dicts) - helper for regenerate"""
    cur = list(desc.get('retail_objects') or [])
    own = [json.dumps(x, sort_keys=True) for x in owner_entries.get('old', [])]
    kept = [x for x in cur if json.dumps(x, sort_keys=True) not in own] if keep_others else []
    return kept + owner_entries.get('new', [])
