"""wb_te_retail - Workbench 0.33 LOCAL-ONLY copies from the user's own retail tracks (Workbench 0.33, 2026-11-01), a mixin of
wb_trackedit.TrackSource. Added at the owner's explicit request ("copy whatever you need from retail tracks").

retail_region: copies the OPAQUE render triangles of a plan rectangle of a retail track (decoded read only by wb_retail from the
user's game data; the retail folder is never written) into the project: one tagged construction block (kind 'retail_copy'),
positions moved / turned to a target, UVs and baked vertex colours exactly as retail (trackbuild writes both unchanged), normals
from each triangle's own winding (the winding is kept as retail). Every texture used becomes an imported PNG (RGB, alpha dropped:
the materials are opaque) + a material r_<name> (floor-like textures copy 'asphalt', others 'wall' for surface / collision).

LOCAL ONLY: every copied texture's provenance says origin retail / local_only, the block's tag says the same, share_export refuses
a project holding either, and nothing retail is stored in the Workbench itself (the starter names track + rectangle only).
Not copied: cut-out / blended retail materials (railings, tree cards, hedges: trackbuild materials are opaque), prop instances
(lampposts that are props: prop meshes are not decoded), retail collision (the kit builds collision from the copied faces).
All editor checks apply: unit regions (never grown), the floor-overlap rule, the kit dry run (per-unit slots), <= 83 materials;
a refusal changes nothing; Apply = the texture imports (one undo step each) + one undo step for materials + geometry.
"""
import hashlib
import json
import math
import os
import re
import struct
import zlib

T = {}
MAX_TRIS = 40000
MAX_NEW_MATERIALS = 40


def E(msg, detail=None):
    e = T['EditError'](msg)
    if detail is not None:
        e.detail = detail
    return e


def num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


def png_read_rgba(b):
    """8-bit RGBA / RGB non-interlaced PNG -> (w, h, rows of RGBA bytes)"""
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    p, idat, w = 8, b'', 0
    while p < len(b):
        n, typ = struct.unpack('>I4s', b[p:p + 8])
        data = b[p + 8:p + 8 + n]
        if typ == b'IHDR':
            w, h, depth, ctype, _c, _f, inter = struct.unpack('>IIBBBBB', data)
            if depth != 8 or ctype not in (2, 6) or inter:
                raise ValueError('unsupported PNG (depth %d, colour type %d, interlace %d)' % (depth, ctype, inter))
            bpp = 4 if ctype == 6 else 3
        elif typ == b'IDAT':
            idat += data
        p += 12 + n
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        cur = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = cur[i - bpp] if i >= bpp else 0
            up = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                cur[i] = (cur[i] + a) & 255
            elif f == 2:
                cur[i] = (cur[i] + up) & 255
            elif f == 3:
                cur[i] = (cur[i] + ((a + up) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else up if pb <= pc else c)) & 255
        rows.append(bytes(cur) if bpp == 4 else bytes(x for i in range(w) for x in (cur[3 * i], cur[3 * i + 1], cur[3 * i + 2], 255)))
        prev = cur
    return w, h, rows


def png_write_rgb(w, h, rows_rgba):
    raw = b''.join(b'\x00' + bytes(r[i] for j in range(w) for i in (4 * j, 4 * j + 1, 4 * j + 2)) for r in rows_rgba)

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


def _norm(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    m = math.sqrt(sum(x * x for x in n))
    return [x / m for x in n] if m > 1e-9 else None


def mat_name(tex):
    s = re.sub(r'[^a-z0-9_]', '_', tex.lower())[:22]
    return 'r_' + s.strip('_')


class RetailMixin:
    def _retail_view(self, track):
        import wb_retail
        if not (isinstance(track, str) and re.match(r'^(EU|US|AS)/[A-Z0-9]{2}_V[0-9]$', track)):
            raise E('track: a retail track id such as US/C1_V1 (region / folder)')
        gd = self.cfg.get('game_data')
        if not gd:
            raise E('the Workbench setting "game_data" (your game data folder) is needed to read a retail track')
        folder = os.path.join(gd, 'Tracks', *track.split('/'))
        try:
            v, cdir, _r = wb_retail.decode(self.cfg, folder)
        except wb_retail.RetailError as e:
            raise E('retail track %s could not be read: %s' % (track, e))
        return v, cdir

    def retail_textures(self, track=None, query=None):
        """read only: the textures a retail track's render mesh uses (name, size, render class, triangles)"""
        v, _c = self._retail_view(track)
        rows = {}
        for e in v['mesh']:
            if e['texture'] is None:
                continue
            r = rows.setdefault(e['texture_name'], {'name': e['texture_name'], 'render': e['render'], 'triangles': 0})
            r['triangles'] += e['indices'] // 3
        q = (query or '').lower()
        out = sorted((r for r in rows.values() if q in r['name'].lower()), key=lambda r: -r['triangles'])
        return {'ok': True, 'track': track, 'textures': out[:300], 'local_only': True,
                'summary_lines': ['%s: %d texture(s)%s (opaque ones can be copied; cut-out / blended cannot)' % (
                    track, len(out), ' matching %r' % query if query else '')]}

    @staticmethod
    def _region_ref_y(v, blob, rect):
        """street level of a retail rect: the median height of its opaque upward-facing triangles"""
        x0, z0, x1, z1 = rect
        ys = []
        for e in v['mesh']:
            if e['render'] != 'opaque' or e['texture_name'] is None:
                continue
            nv = e['vertices']
            P = struct.unpack_from('<%df' % (3 * nv), blob, e['off_pos'])
            idx = struct.unpack_from('<%dI' % e['indices'], blob, e['off_idx'])
            for t in range(0, len(idx), 3):
                pts = [P[3 * i:3 * i + 3] for i in idx[t:t + 3]]
                mx, mz = sum(q[0] for q in pts) / 3, sum(q[2] for q in pts) / 3
                if x0 <= mx <= x1 and z0 <= mz <= z1:
                    n = _norm(*pts)
                    if n and abs(n[1]) > 0.9:
                        ys.append(sum(q[1] for q in pts) / 3)
        if not ys:
            return 0.0
        ys.sort()
        return ys[len(ys) // 2]

    GROUND_ROADS = ('road', 'chev', 'crossing', 'junction', 'tarmac', 'asphalt')
    GROUND_ALL = GROUND_ROADS + ('pave', 'grass', 'ground', 'gravel', 'kerb', 'grnd')

    def _region_req(self, track, rect, target, angle, max_tris, skip, ground='roads'):
        if ground not in ('keep', 'roads', 'all'):
            raise E("ground: 'roads' (leave retail road surfaces out - the track has its own; default), 'all' (also sidewalks / grass) "
                    "or 'keep'")
        if not (isinstance(rect, list) and len(rect) == 4 and all(num(x, -1e6, 1e6) for x in rect) and rect[0] < rect[2] and rect[1] < rect[3]):
            raise E('rect: [x0, z0, x1, z1] in the RETAIL track\'s coordinates (plan)')
        if (rect[2] - rect[0]) * (rect[3] - rect[1]) > 250000:
            raise E('rect larger than 0.25 km2: copy a smaller area (per-unit memory is limited)')
        if not (isinstance(target, list) and len(target) == 3 and all(num(x, -1e6, 1e6) for x in target)):
            raise E('target: [x, y, z] in THIS project - where the rect\'s centre at its street level (median floor height) lands')
        if not num(angle, -360, 360):
            raise E('angle: -360..360 degrees (turn about the vertical)')
        if not (isinstance(max_tris, int) and not isinstance(max_tris, bool) and 1 <= max_tris <= MAX_TRIS):
            raise E('max_tris: 1..%d' % MAX_TRIS)
        if skip is not None and not (isinstance(skip, list) and all(isinstance(s, str) for s in skip)):
            raise E('skip: a list of retail texture names to leave out')
        return {'ground': ground, 'track': track, 'rect': [float(x) for x in rect], 'target': [float(x) for x in target], 'angle': float(angle),
                'max_tris': max_tris, 'skip': sorted(skip or [])}

    def _region_plan(self, req):
        v, cdir = self._retail_view(req['track'])
        blob = open(os.path.join(cdir, 'mesh.bin'), 'rb').read()
        x0, z0, x1, z1 = req['rect']
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        a = math.radians(req['angle'])
        ca, sa = math.cos(a), math.sin(a)
        tx, ty, tz = req['target']
        ref = self._region_ref_y(v, blob, req['rect'])

        def move(p):
            dx, dz = p[0] - cx, p[2] - cz
            return (round(tx + ca * dx - sa * dz, 4), round(ty + p[1] - ref, 4), round(tz + sa * dx + ca * dz, 4))
        by_tex, skipped, n_tris = {}, {}, 0
        for e in v['mesh']:
            name = e['texture_name']
            if name is None:
                continue
            nv = e['vertices']
            P = struct.unpack_from('<%df' % (3 * nv), blob, e['off_pos'])
            idx = struct.unpack_from('<%dI' % e['indices'], blob, e['off_idx'])
            inside = []
            for t in range(0, len(idx), 3):
                i0, i1, i2 = idx[t], idx[t + 1], idx[t + 2]
                mx = (P[3 * i0] + P[3 * i1] + P[3 * i2]) / 3
                mz = (P[3 * i0 + 2] + P[3 * i1 + 2] + P[3 * i2 + 2]) / 3
                if x0 <= mx <= x1 and z0 <= mz <= z1:
                    inside.append((i0, i1, i2))
            if not inside:
                continue
            gl = name.lower()
            gk = self.GROUND_ALL if req['ground'] == 'all' else self.GROUND_ROADS if req['ground'] == 'roads' else ()
            if e['render'] != 'opaque' or name in req['skip'] or any(k in gl for k in gk):
                skipped[name] = skipped.get(name, 0) + len(inside)
                continue
            UV = struct.unpack_from('<%df' % (2 * nv), blob, e['off_uv'])
            C = struct.unpack_from('<%df' % (3 * nv), blob, e['off_col'])
            lst = by_tex.setdefault(name, {'texture_index': e['texture'], 'faces': []})
            for i0, i1, i2 in inside:
                pts = [move(P[3 * i:3 * i + 3]) for i in (i0, i1, i2)]
                n = _norm(*pts)
                if n is None:
                    continue
                if req['ground'] == 'all' and n[1] > 0.5 and min(q[1] for q in pts) < ty + 1.5:
                    skipped['(street-level floors)'] = skipped.get('(street-level floors)', 0) + 1
                    continue                                # the track's own ground carries the buildings
                area = 0.5 * math.sqrt(sum(x * x for x in [(pts[1][1] - pts[0][1]) * (pts[2][2] - pts[0][2]) - (pts[1][2] - pts[0][2]) * (pts[2][1] - pts[0][1]),
                                                         (pts[1][2] - pts[0][2]) * (pts[2][0] - pts[0][0]) - (pts[1][0] - pts[0][0]) * (pts[2][2] - pts[0][2]),
                                                         (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (pts[1][1] - pts[0][1]) * (pts[2][0] - pts[0][0])]))
                if area <= 2e-4:
                    skipped['(tiny triangles)'] = skipped.get('(tiny triangles)', 0) + 1
                    continue
                lst['faces'].append([(pts[k], (round(UV[2 * i], 5), round(UV[2 * i + 1], 5)), tuple(round(x, 5) for x in n),
                                      tuple(round(C[3 * i + j], 3) for j in range(3))) for k, i in enumerate((i0, i1, i2))])
                n_tris += 1
        if not by_tex:
            raise E('nothing opaque to copy in rect %s of %s (skipped: %s)' % (req['rect'], req['track'], skipped or 'none'))
        if n_tris > req['max_tris']:
            raise E('the rect holds %d copyable triangles (> max_tris %d): choose a smaller rect or raise max_tris' % (n_tris, req['max_tris']))
        # collision per material (0.33): retail keeps a separate simplified collision; a copy makes collision from its faces, and
        # collision is never decimated (it fills the LOD slot). Structural materials (large faces: walls, floors) keep collision;
        # decorative ones (small faces: signs, adverts, awnings, trims, lamp parts) are copied without collision.
        if req.get('collision', 'structural') == 'structural':
            for name, x in by_tex.items():
                ar = []
                for f in x['faces']:
                    q = [c[0] for c in f]
                    u_ = [q[1][j] - q[0][j] for j in range(3)]
                    v_ = [q[2][j] - q[0][j] for j in range(3)]
                    ar.append(0.5 * math.sqrt(sum(t * t for t in (u_[1] * v_[2] - u_[2] * v_[1], u_[2] * v_[0] - u_[0] * v_[2], u_[0] * v_[1] - u_[1] * v_[0]))))
                floor = sum(1 for f in x['faces'] if abs(f[0][2][1]) > 0.7) * 2 > len(x['faces'])
                big = sum(a for a in ar if a >= 2.0) / max(1e-9, sum(ar))
                deco = any(k in name.lower() for k in ('sign', 'advert', 'canopy', 'awning', 'lamp', 'detail', 'trim', 'banner', 'shopsign'))
                x['collide'] = bool(floor or (big >= 0.6 and not deco))
        d = self.desc()
        mats = d.get('materials') or {}
        new_m = [mat_name(t) for t in by_tex if mat_name(t) not in mats]
        if len(new_m) > MAX_NEW_MATERIALS or len(d.get('rows') or []) + len(new_m) > 83:
            raise E('this copy needs %d new materials (%d rows exist, trackbuild allows 83): a smaller rect, or skip textures' % (
                len(new_m), len(d.get('rows') or [])))
        return v, cdir, by_tex, skipped, n_tris

    def _region_textures(self, cdir, by_tex, track):
        """per texture: (rel, png bytes, provenance) for textures not in the project yet"""
        import wb_stage as stg
        have = set(stg.tree_hashes(self.project)) | set(self.pending)
        out = []
        for name, x in sorted(by_tex.items()):
            rel = 'textures/%s.png' % mat_name(name)
            if rel in have:
                continue
            if 'png_rows' in x:                             # decoded from static.dat (instance-model textures)
                w, h, rows = x['png_rows']
            else:
                src = os.path.join(cdir, 'tex', 't%03d.png' % x['texture_index'])
                try:
                    w, h, rows = png_read_rgba(open(src, 'rb').read())
                except (OSError, ValueError) as e:
                    raise E('retail texture %s could not be read from the view cache (%s)' % (name, e))
            if w & (w - 1) or h & (h - 1) or not (4 <= w <= 1024 and 4 <= h <= 1024):
                raise E('retail texture %s is %d x %d: trackbuild needs a power of two 4..1024' % (name, w, h))
            b = png_write_rgb(w, h, rows)
            meta = {'origin': 'retail', 'local_only': True, 'retail_track': track, 'retail_texture': name, 'size': [w, h],
                    'source_sha256': hashlib.sha256(b).hexdigest(), 'kind': 'RETAIL-DERIVED texture copied from the user\'s own game '
                    'data at the owner\'s request: LOCAL ONLY - never share, package for others or upload',
                    'author': 'retail game (Criterion / EA)', 'licence': 'none for redistribution: local use only'}
            out.append((rel, b, meta))
        return out

    def retail_region_preview(self, track=None, rect=None, target=None, angle=0.0, max_tris=20000, skip=None, id=None, ground='roads'):  # noqa: A002
        """LOCAL ONLY: copy the opaque render geometry of a retail track's plan rectangle (with its textures) into this project,
        WITHOUT changing anything"""
        req = self._region_req(track, rect, target, angle, max_tris, skip, ground)
        _v, cdir, by_tex, skipped, n = self._region_plan(req)
        tex = self._region_textures(cdir, by_tex, track)
        allp = [p for x in by_tex.values() for f in x['faces'] for p, _uv, _n, _c in f]
        return {'ok': True, 'triangles': n, 'textures': {k: len(x['faces']) for k, x in sorted(by_tex.items(), key=lambda kv: -len(kv[1]['faces']))},
                'new_textures': [t[0] for t in tex], 'skipped': skipped, 'local_only': True,
                'collision': {k: x.get('collide', True) for k, x in by_tex.items()},
                'bounds': [[round(min(p[i] for p in allp), 2) for i in range(3)], [round(max(p[i] for p in allp), 2) for i in range(3)]],
                'new_faces': [[list(p) for p, _uv, _n, _c in f] for x in list(by_tex.values())[:6] for f in x['faces'][:400]],
                'preview_key': self._cons_key('retail_region', req),
                'note': 'preview only: nothing changed. LOCAL ONLY: retail-derived geometry and textures; the project can no longer '
                        'be shared with the shareable export while it holds them.',
                'summary_lines': ['copy from %s rect %s: %d triangles, %d texture(s), %d new texture file(s); skipped %s (cut-out / '
                                  'blended or listed); LOCAL ONLY' % (track, req['rect'], n, len(by_tex), len(tex),
                                                                    ', '.join('%s %d' % kv for kv in sorted(skipped.items())[:8]) or 'none')]}

    def retail_region(self, track=None, rect=None, target=None, angle=0.0, max_tris=20000, skip=None, id=None, ground='roads',  # noqa: A002
                      preview_key=None):
        req = self._region_req(track, rect, target, angle, max_tris, skip, ground)
        if preview_key != self._cons_key('retail_region', req):
            raise E('NEEDS PREVIEW: preview this copy first and apply it with its preview_key')
        _v, cdir, by_tex, skipped, n = self._region_plan(req)
        tex = self._region_textures(cdir, by_tex, track)
        meta = {'kind': 'retail_copy', 'id': id or self._new_id('retail'), 'track': track, 'rect': req['rect'], 'target': req['target'],
                'angle': req['angle'], 'local_only': True, 'triangles': n}
        r = self._apply_retail(track, by_tex, tex, meta, id, n, 'copy retail %s rect %s' % (track, req['rect']))
        r['skipped'] = skipped
        return r

    def _apply_retail(self, track, by_tex, tex, meta, id, n, what):  # noqa: A002
        snap = (self.cur, self.obj_cur, dict(self.pending), dict(self.pending_meta), len(self.undo_stack), list(self.redo_stack))
        try:
            for rel, b, tmeta in tex:
                self.pending_meta[rel] = tmeta
                self._push('file:' + rel, 'copy retail texture %s (local only)' % rel, b, kind='texture', index=rel)
            # materials (one splice each, chained on a working copy of the description)
            work = self.cur
            d = self.desc()
            mats = d.get('materials') or {}
            for name, x in sorted(by_tex.items()):
                mn = x.get('mat') or mat_name(name)
                if mn in mats:
                    continue
                floors = sum(1 for f in x['faces'] if f[0][2][1] > 0.7)
                like = 'asphalt' if floors * 2 > len(x['faces']) and 'asphalt' in mats else ('wall' if 'wall' in mats else None)
                self.cur = work
                mreq = self._material_req(mn, 'textures/%s.png' % mat_name(name), None, x.get('collide'), None, like)
                work = self._material_after(mreq)
                mats = dict(mats, **{mn: mreq['m']})
            desc2 = work
            self.cur = snap[0]
            faces = [(x.get('mat') or mat_name(name), f) for name, x in sorted(by_tex.items()) for f in x['faces']]
            repl = self.constructs()[id]['groups'] if id else []
            self.cur = desc2                                # the new materials exist for the block checks
            ov = self._overlap_check(faces, set(repl), 'copied floor faces')
            obj2, blk = self._block_bytes(faces, meta, repl)
            regen = self.regenerate(obj2, desc2)            # kit dry run: per-unit slots, collision, LOD (raises when it does not fit)
            cov = self.coverage(obj2, desc2)
            lost = [f for f in cov['faces'] if f['area'] - f['kept'] > 0.01 and f['mat'] in {m for m, _f in faces}]
            if lost:
                raise E('%d copied face(s) lie (partly) outside the unit regions (Build would drop %.2f m2): grow a unit region over the '
                        'target first (Construct -> Unit regions: include); never grown automatically' % (
                            len(lost), sum(f['area'] - f['kept'] for f in lost)), {'lost_faces': [{'corners': f['pts']} for f in lost[:200]]})
            self.cur = snap[0]
            label = '%s (%d triangles, %d materials; LOCAL ONLY)' % (what, n, len(by_tex))
            self._push('both', label, (desc2, obj2), kind='retail_copy', index=meta['id'])
        except Exception:
            self.cur, self.obj_cur = snap[0], snap[1]
            self.pending, self.pending_meta = snap[2], snap[3]
            del self.undo_stack[snap[4]:]
            self.redo_stack[:] = snap[5]
            raise
        cap = max((c['mesh_slot_pct'] for c in regen['capacity']), default=0)
        cinfo = regen.get('capacity_info', [])                # RTA5: blocks above the game's slot declared under capacity auto
        return {'ok': True, 'label': label, 'block': meta['id'], 'triangles': n, 'materials': sorted({m for m, _f in faces}),
                'textures_copied': [t[0] for t in tex], 'overlap': ov, 'worst_mesh_slot_pct': cap, 'local_only': True,
                'summary_lines': [label, 'textures copied: %d (provenance: retail, local only); worst unit mesh slot %.1f %%' % (len(tex), cap),
                                  'Save writes it. Never share / upload this project or its builds.'] + ['INFO: ' + n for n in cinfo],
                'capacity_info': cinfo}

    def _rtex_req(self, track, texture, name, like):
        v, cdir = self._retail_view(track)
        ent = [e for e in v['mesh'] if e['texture_name'] == texture]
        if not ent:
            raise E('texture %r is not used by %s\'s render mesh (retail_textures lists them)' % (texture, track))
        if ent[0]['render'] != 'opaque':
            raise E('texture %s is %s in retail: trackbuild materials are opaque, it would show as a solid block' % (texture, ent[0]['render']))
        mn = name or mat_name(texture)
        if not re.match(r'^[a-z0-9_]{1,24}$', mn):
            raise E('name %r: 1..24 lower-case letters, digits or _' % (mn,))
        d = self.desc()
        if mn in (d.get('materials') or {}):
            raise E('material %s exists already' % mn)
        if like not in (d.get('materials') or {}):
            raise E('like: an existing material to copy surface / collision from (%s)' % ', '.join(d.get('materials') or {}))
        return v, cdir, ent[0], mn

    def retail_texture_preview(self, track=None, texture=None, name=None, like='wall'):
        """LOCAL ONLY: one retail texture -> an imported PNG + a material (surface / collision of `like`), WITHOUT changing anything"""
        _v, _c, e, mn = self._rtex_req(track, texture, name, like)
        return {'ok': True, 'material': mn, 'texture': 'textures/%s.png' % mn, 'retail': '%s %s' % (track, texture), 'like': like,
                'local_only': True, 'preview_key': self._cons_key('retail_texture', [track, texture, name, like]),
                'summary_lines': ['retail texture %s of %s -> material %s (like %s); LOCAL ONLY' % (texture, track, mn, like)]}

    def retail_texture(self, track=None, texture=None, name=None, like='wall', preview_key=None):
        if preview_key != self._cons_key('retail_texture', [track, texture, name, like]):
            raise E('NEEDS PREVIEW: preview this texture first and apply it with its preview_key')
        _v, cdir, e, mn = self._rtex_req(track, texture, name, like)
        import wb_stage as stg
        rel = 'textures/%s.png' % mn
        if rel in stg.tree_hashes(self.project) or rel in self.pending:
            raise E('%s exists already' % rel)
        tex = self._region_textures(cdir, {texture: {'texture_index': e['texture'], 'faces': []}}, track)
        snap = (self.cur, dict(self.pending), dict(self.pending_meta), len(self.undo_stack))
        try:
            for r_, b_, meta in tex:                        # the cache PNG name follows the retail name; store under this name
                self.pending_meta[rel] = meta
                self._push('file:' + rel, 'copy retail texture %s (local only)' % rel, b_, kind='texture', index=rel)
            mreq = self._material_req(mn, rel, None, None, None, like)
            after = self._material_after(mreq)
            self._push('desc', 'material %s from retail %s (local only)' % (mn, texture), after, kind='material', index=mn)
        except Exception:
            self.cur, self.pending, self.pending_meta = snap[0], snap[1], snap[2]
            del self.undo_stack[snap[3]:]
            raise
        return {'ok': True, 'material': mn, 'texture': rel, 'local_only': True,
                'summary_lines': ['material %s from retail %s %s (texture copied, LOCAL ONLY)' % (mn, track, texture)]}

    # ---------------- real retail lampposts (static INSTANCE models; format_research\props_mesh, VERIFIED) along the route
    def _static_tex(self, track, names):
        """retail texture name -> (w, h, RGBA rows), decoded from static.dat with the kit's xbmesh reader (read only)"""
        import wb_retail
        R = wb_retail.readers(self.cfg)[0]
        X = R['xbmesh']
        folder = os.path.join(self.cfg['game_data'], 'Tracks', *track.split('/'))
        st = X.Static(wb_retail.read_ro(os.path.join(folder, 'static.dat')))
        out = {}
        for t in st.tex:
            if t['name'] in names and t['format'] in (0x0C, 0x0E, 0x0F):
                rgba = bytes(X.decode_dxt(st.d, t['data'], t['w'], t['h'], t['format']))
                out[t['name']] = (t['w'], t['h'], [rgba[y * t['w'] * 4:(y + 1) * t['w'] * 4] for y in range(t['h'])])
        missing = sorted(set(names) - set(out))
        if missing:
            raise E('retail texture(s) %s not decodable from %s static.dat' % (missing, track))
        return out

    def _lamp_req(self, track, model, spacing, side, offset, start, double_sided, collision='none'):
        if collision not in ('none', 'keep'):
            raise E("collision: 'none' (decorative, no collision: the default) or 'keep' (full collision of every lamp face)")
        if not (isinstance(model, str) and re.match(r'^I[0-9]{1,3}$', model)):
            raise E('model: a retail instance model id such as I31 (format_research\\props_mesh lists them)')
        if not num(spacing, 8, 200):
            raise E('spacing: 8..200 m along the route')
        if side not in ('both', 'outer', 'inner'):
            raise E("side: 'both', 'outer' or 'inner'")
        if not num(offset, 0, 20) or not num(start, 0, 200):
            raise E('offset: 0..20 m beyond the wall; start: 0..200 m')
        if not isinstance(double_sided, bool):
            raise E('double_sided: true / false (retail strip winding is not consistent: true keeps every face visible)')
        if not self.desc().get('stations'):
            raise E('lamps follow the race route: lay out the route first')
        return {'track': track, 'model': model, 'spacing': float(spacing), 'side': side, 'offset': float(offset), 'start': float(start),
                'double_sided': double_sided, 'collision': collision}

    def _lamp_plan(self, req):
        import sys
        pm = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'format_research', 'props_mesh')
        if pm not in sys.path:
            sys.path.insert(0, pm)
        import fr_propmesh as FP
        folder = os.path.join(self.cfg['game_data'], 'Tracks', *req['track'].split('/'))
        t = FP.load(folder)
        k = int(req['model'][1:])
        try:
            tris = t.triangles('I', k)
        except Exception as e:  # noqa: BLE001   a refused / unknown model: reported
            raise E('instance model %s of %s could not be read: %s' % (req['model'], req['track'], e))
        tex = sorted({tn for tn, _cs in tris})
        P = [p for _tn, cs in tris for p, _uv, _c in cs]
        ymin = min(p[1] for p in P)
        top = [p for p in P if p[1] > ymin + 0.8 * (max(q[1] for q in P) - ymin)]
        base = [p for p in P if p[1] < ymin + 0.5]
        bx, bz = sum(p[0] for p in base) / len(base), sum(p[2] for p in base) / len(base)
        ax, az = sum(p[0] for p in top) / len(top) - bx, sum(p[2] for p in top) / len(top) - bz
        arm = math.atan2(az, ax) if math.hypot(ax, az) > 0.2 else 0.0      # the arm's local heading (towards the road in retail)
        d = self.desc()
        st = d['stations']
        n = len(st)
        cum = [0.0]
        for i in range(n):
            a, c = st[i]['p'], st[(i + 1) % n]['p']
            cum.append(cum[-1] + math.hypot(c[0] - a[0], c[2] - a[2]))
        L = cum[-1]
        wall_t = 0.6
        spots = []
        s_ = req['start']
        while s_ < L - 1e-6:
            i = max(j for j in range(n) if cum[j] <= s_)
            f = (s_ - cum[i]) / max(1e-9, cum[i + 1] - cum[i])
            a, c = st[i], st[(i + 1) % n]
            p = [a['p'][j] + f * (c['p'][j] - a['p'][j]) for j in range(3)]
            tx_, tz_ = a['t']
            for sd in ((-1,) if req['side'] == 'outer' else (1,) if req['side'] == 'inner' else (-1, 1)):
                edge = abs(a['offsets'][1 if sd < 0 else 4]) + wall_t + req['offset']   # road edge (wall line) + wall + offset
                nx, nz = -tz_ * sd, tx_ * sd                                       # n+ = (-tz, tx); outer side = n-
                pos = (p[0] + nx * edge, p[1], p[2] + nz * edge)
                towards = math.atan2(-nz, -nx)                                     # heading from the lamp to the road
                spots.append((pos, towards - arm))
            s_ += req['spacing']
        by_tex = {tn: {'faces': []} for tn in tex}
        dropped = [0]
        for pos, rot in spots:
            cr, sr = math.cos(rot), math.sin(rot)
            for tn, cs in tris:
                pts = [(round(pos[0] + cr * (q[0] - bx) - sr * (q[2] - bz), 4), round(pos[1] + q[1] - ymin, 4),
                        round(pos[2] + sr * (q[0] - bx) + cr * (q[2] - bz), 4)) for q, _uv, _c in cs]
                nrm = _norm(*pts)
                u_ = [pts[1][j] - pts[0][j] for j in range(3)]
                v_ = [pts[2][j] - pts[0][j] for j in range(3)]
                area = 0.5 * math.sqrt(sum(x * x for x in (u_[1] * v_[2] - u_[2] * v_[1], u_[2] * v_[0] - u_[0] * v_[2], u_[0] * v_[1] - u_[1] * v_[0])))
                if nrm is None or area < 0.006:          # trackbuild drops slivers < 0.005 m2 (2 of I31's 162 triangles): left out
                    dropped[0] += 1
                    continue
                uvs = [(round(uv[0], 5), round(uv[1], 5)) for _q, uv, _c in cs]
                col = (0.2, 0.2, 0.2)                       # no vertex colour in the instance format: the editor's neutral light
                by_tex[tn]['faces'].append([(pts[j], uvs[j], tuple(round(x, 5) for x in nrm), col) for j in range(3)])
                if req['double_sided']:
                    rn = tuple(-round(x, 5) for x in nrm)
                    by_tex[tn]['faces'].append([(pts[j], uvs[j], rn, col) for j in (0, 2, 1)])
        return by_tex, len(spots), sum(len(x['faces']) for x in by_tex.values())

    def retail_lamps_preview(self, track='US/C1_V1', model='I31', spacing=30.0, side='both', offset=1.0, start=10.0, double_sided=True,
                             collision='none'):
        """LOCAL ONLY: real retail lamppost models (static instance meshes) every `spacing` m along the route, arm towards the road,
        WITHOUT changing anything"""
        req = self._lamp_req(track, model, spacing, side, offset, start, double_sided, collision)
        by_tex, nl, nt = self._lamp_plan(req)
        return {'ok': True, 'lamps': nl, 'triangles': nt, 'textures': sorted(by_tex), 'local_only': True,
                'new_faces': [[list(p) for p, _uv, _n, _c in f] for x in by_tex.values() for f in x['faces'][:3000]],
                'preview_key': self._cons_key('retail_lamps', req),
                'summary_lines': ['%d x retail %s %s lamps every %.0f m (%s side), %d triangles; LOCAL ONLY' % (
                    nl, track, model, req['spacing'], req['side'], nt)]}

    def retail_lamps(self, track='US/C1_V1', model='I31', spacing=30.0, side='both', offset=1.0, start=10.0, double_sided=True,
                     collision='none', preview_key=None):
        req = self._lamp_req(track, model, spacing, side, offset, start, double_sided, collision)
        if preview_key != self._cons_key('retail_lamps', req):
            raise E('NEEDS PREVIEW: preview the lamps first and apply them with their preview_key')
        by_tex, nl, nt = self._lamp_plan(req)
        rows = self._static_tex(track, set(by_tex))
        for tn in by_tex:
            by_tex[tn]['png_rows'] = rows[tn]
            if req['collision'] == 'none':                  # a non-colliding twin material for the lamp faces
                by_tex[tn]['mat'] = mat_name(tn) + '_nc'
                by_tex[tn]['collide'] = False
        tex = self._region_textures(None, by_tex, track)
        meta = {'kind': 'retail_copy', 'id': self._new_id('lamps'), 'track': track, 'model': model, 'lamps': nl, 'local_only': True,
                'spacing': req['spacing'], 'side': req['side']}
        return self._apply_retail(track, by_tex, tex, meta, None, nt, '%d retail %s lamps' % (nl, model))

    RETAIL_LAYOUT = {'retail_lamps_preview': 'retail_lamps_preview', 'retail_lamps': 'retail_lamps', 'retail_texture_preview': 'retail_texture_preview', 'retail_texture': 'retail_texture', 'retail_textures': 'retail_textures', 'retail_region_preview': 'retail_region_preview', 'retail_region': 'retail_region'}
