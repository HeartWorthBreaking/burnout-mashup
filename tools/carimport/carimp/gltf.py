"""Strict glTF 2.0 reader / small writer for carimport (pure Python).

load(path) -> Scene         .gltf (JSON + external / data-URI buffers) or .glb (binary container)
    Scene.nodes: [SceneMesh(name, matrix(16, column-major), prims=[Prim])] for every scene node that carries a mesh
    Prim: positions [(x,y,z)], normals [(x,y,z)] or None, uvs [(u,v)], tris [(a,b,c)], material (index or None)
    Scene.materials: [dict(name, cls, image, notes)]
    Scene.images: [dict(name, png bytes)]
    Scene.notes: what was accepted but is not represented in the car format (always reported, never silent)
Anything the car format cannot carry is REFUSED with GltfError (one message per problem, all collected):
    extensions (used or required), skins, animations, cameras, morph targets, sparse accessors, attributes other than
    POSITION / NORMAL / TEXCOORD_0, primitive modes other than TRIANGLES, non-float vertex data, texCoord sets other
    than 0, baseColorFactor other than white, normal / occlusion / emissive textures, non-PNG images, meshes outside the
    active scene.
write(path_gltf, nodes, materials, image_files) -> writes .gltf + .bin (geometry in one buffer)
"""
import base64
import json
import math
import os
import struct

COMP_FMT = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
ALLOWED_ATTR = ('POSITION', 'NORMAL', 'TEXCOORD_0')
CLASSES = ('paint', 'plain', 'glass')


class GltfError(Exception):
    def __init__(self, problems):
        self.problems = problems if isinstance(problems, list) else [problems]
        Exception.__init__(self, '; '.join(self.problems))


class Prim:
    def __init__(self):
        self.positions = []
        self.normals = None
        self.uvs = []
        self.tris = []
        self.material = None


class SceneMesh:
    def __init__(self, name, matrix, prims):
        self.name, self.matrix, self.prims = name, matrix, prims


class Scene:
    def __init__(self):
        self.nodes = []
        self.materials = []
        self.images = []
        self.notes = []
        self.source = ''


# ---------------------------------------------------------------- matrices (column-major 4x4, glTF convention)
IDENT = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mat_mul(a, b):
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def trs(node):
    if 'matrix' in node:
        return [float(x) for x in node['matrix']]
    t = node.get('translation', [0, 0, 0])
    q = node.get('rotation', [0, 0, 0, 1])
    s = node.get('scale', [1, 1, 1])
    x, y, z, w = q
    rm = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0,
          2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0,
          2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0,
          0, 0, 0, 1]
    for c in range(3):
        for r in range(3):
            rm[c * 4 + r] *= s[c]
    rm[12], rm[13], rm[14] = t
    return rm


def xform_point(m, p):
    return tuple(m[r] * p[0] + m[4 + r] * p[1] + m[8 + r] * p[2] + m[12 + r] for r in range(3))


def det3(m):
    a, b, c = m[0], m[4], m[8]
    d, e, f = m[1], m[5], m[9]
    g, h, i = m[2], m[6], m[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def normal_matrix(m):
    """Inverse transpose of the upper 3x3 (column-major in, row-major 3x3 out)."""
    a, b, c = m[0], m[4], m[8]
    d, e, f = m[1], m[5], m[9]
    g, h, i = m[2], m[6], m[10]
    D = det3(m)
    if abs(D) < 1e-12:
        raise GltfError('node transform is singular (zero scale)')
    inv = [(e * i - f * h) / D, (c * h - b * i) / D, (b * f - c * e) / D,
           (f * g - d * i) / D, (a * i - c * g) / D, (c * d - a * f) / D,
           (d * h - e * g) / D, (b * g - a * h) / D, (a * e - b * d) / D]
    # transpose
    return [inv[0], inv[3], inv[6], inv[1], inv[4], inv[7], inv[2], inv[5], inv[8]]


def xform_normal(nm, n):
    v = (nm[0] * n[0] + nm[1] * n[1] + nm[2] * n[2], nm[3] * n[0] + nm[4] * n[1] + nm[5] * n[2],
         nm[6] * n[0] + nm[7] * n[1] + nm[8] * n[2])
    ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / ln, v[1] / ln, v[2] / ln) if ln > 1e-20 else (0.0, 1.0, 0.0)


# ---------------------------------------------------------------- loading
def _load_container(path):
    raw = open(path, 'rb').read()
    if raw[:4] == b'glTF':
        ver, length = struct.unpack_from('<II', raw, 4)
        if ver != 2 or length != len(raw):
            raise GltfError('GLB header: version %d length %d (file %d)' % (ver, length, len(raw)))
        o = 12
        js = None
        binc = None
        while o < len(raw):
            n, t = struct.unpack_from('<II', raw, o)
            d = raw[o + 8:o + 8 + n]
            if t == 0x4E4F534A:
                js = json.loads(d.decode('utf-8'))
            elif t == 0x004E4942:
                binc = d
            o += 8 + n
        if js is None:
            raise GltfError('GLB without JSON chunk')
        return js, binc
    return json.loads(raw.decode('utf-8')), None


def _buffer_bytes(js, i, base, binc):
    buf = js['buffers'][i]
    uri = buf.get('uri')
    if uri is None:
        if binc is None:
            raise GltfError('buffer %d has no uri and there is no GLB BIN chunk' % i)
        return binc
    if uri.startswith('data:'):
        return base64.b64decode(uri.split(',', 1)[1])
    p = os.path.normpath(os.path.join(base, uri.replace('%20', ' ')))
    return open(p, 'rb').read()


def load(path):
    js, binc = _load_container(path)
    base = os.path.dirname(os.path.abspath(path))
    probs = []
    sc = Scene()
    sc.source = path
    if js.get('asset', {}).get('version') != '2.0':
        probs.append('asset.version %r (2.0 required)' % js.get('asset', {}).get('version'))
    for key in ('extensionsRequired', 'extensionsUsed'):
        if js.get(key):
            probs.append('%s %s: no glTF extension is supported (its data would be lost)' % (key, js[key]))
    for key in ('skins', 'animations', 'cameras'):
        if js.get(key):
            probs.append('%s present (%d): not representable in the car model (unsupported in slice 1)' % (key, len(js[key])))
    bufs = {}

    def buf(i):
        if i not in bufs:
            bufs[i] = _buffer_bytes(js, i, base, binc)
        return bufs[i]

    def accessor(i, want_float=None):
        a = js['accessors'][i]
        if 'sparse' in a:
            raise GltfError('accessor %d is sparse (not supported)' % i)
        if 'bufferView' not in a:
            raise GltfError('accessor %d has no bufferView' % i)
        bv = js['bufferViews'][a['bufferView']]
        ct = a['componentType']
        if ct not in COMP_FMT:
            raise GltfError('accessor %d component type %d' % (i, ct))
        if want_float and ct != 5126:
            raise GltfError('accessor %d: %s must be FLOAT (normalised / quantised data needs an extension)' % (i, want_float))
        nc = NCOMP[a['type']]
        fmt = COMP_FMT[ct]
        es = struct.calcsize(fmt) * nc
        stride = bv.get('byteStride') or es
        data = buf(bv['buffer'])
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        cnt = a['count']
        if off + stride * (cnt - 1) + es > bv.get('byteOffset', 0) + bv['byteLength'] or \
                bv.get('byteOffset', 0) + bv['byteLength'] > len(data):
            raise GltfError('accessor %d out of its buffer view / buffer' % i)
        out = []
        for k in range(cnt):
            v = struct.unpack_from('<%d%s' % (nc, fmt), data, off + k * stride)
            out.append(v if nc > 1 else v[0])
        return out

    # images
    for ii, im in enumerate(js.get('images', [])):
        mime = im.get('mimeType', '')
        if 'uri' in im:
            uri = im['uri']
            if uri.startswith('data:'):
                head, b64 = uri.split(',', 1)
                data = base64.b64decode(b64)
                mime = mime or head[5:].split(';')[0]
            else:
                p = os.path.normpath(os.path.join(base, uri.replace('%20', ' ')))
                data = open(p, 'rb').read()
                if not mime:
                    mime = 'image/png' if uri.lower().endswith('.png') else 'image/?'
        else:
            bv = js['bufferViews'][im['bufferView']]
            data = buf(bv['buffer'])[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
        if mime != 'image/png' or data[:8] != b'\x89PNG\r\n\x1a\n':
            probs.append('image %d (%s) is not PNG' % (ii, im.get('name', im.get('uri', ''))))
        sc.images.append(dict(name=im.get('name', im.get('uri', 'image%d' % ii)), png=data))
    # materials
    for mi, m in enumerate(js.get('materials', [])):
        name = m.get('name', 'material%d' % mi)
        cls = (m.get('extras') or {}).get('bm_class') or name.split('.')[0].split('_')[0].lower()
        notes = []
        if cls not in CLASSES:
            probs.append('material %d "%s": class %r unknown (paint | plain | glass via extras.bm_class or a name '
                         'prefix "paint." / "plain." / "glass.")' % (mi, name, cls))
        pbr = m.get('pbrMetallicRoughness', {})
        bct = pbr.get('baseColorTexture')
        image = None
        if bct is None:
            probs.append('material %d "%s": no baseColorTexture (every car material samples the one car texture)' % (mi, name))
        else:
            if bct.get('texCoord', 0) != 0:
                probs.append('material %d "%s": texCoord %d (only TEXCOORD_0)' % (mi, name, bct['texCoord']))
            if bct.get('extensions'):
                probs.append('material %d "%s": texture transform / extensions not supported' % (mi, name))
            tex = js['textures'][bct['index']]
            image = tex.get('source')
            if image is None:
                probs.append('material %d "%s": texture without source' % (mi, name))
        if [float(x) for x in pbr.get('baseColorFactor', [1, 1, 1, 1])] != [1.0, 1.0, 1.0, 1.0]:
            probs.append('material %d "%s": baseColorFactor %s (the format has no material colour; bake it into the '
                         'texture)' % (mi, name, pbr['baseColorFactor']))
        for k in ('normalTexture', 'occlusionTexture', 'emissiveTexture', 'metallicRoughnessTexture'):
            if k in m or k in pbr:
                probs.append('material %d "%s": %s not representable' % (mi, name, k))
        if [float(x) for x in m.get('emissiveFactor', [0, 0, 0])] != [0.0, 0.0, 0.0]:
            probs.append('material %d "%s": emissiveFactor not representable (car lights are not supported in slice 1)'
                         % (mi, name))
        if m.get('extensions'):
            probs.append('material %d "%s": material extensions not supported' % (mi, name))
        am = m.get('alphaMode', 'OPAQUE')
        if am != 'OPAQUE' and cls != 'glass':
            probs.append('material %d "%s": alphaMode %s only allowed for class glass' % (mi, name, am))
        if 'metallicFactor' in pbr or 'roughnessFactor' in pbr:
            notes.append('metallic / roughness factors are not represented: the game shader is fixed by the class "%s"' % cls)
        if m.get('doubleSided'):
            notes.append('doubleSided is not represented (the triangles are written one-sided)')
        sc.materials.append(dict(name=name, cls=cls, image=None if image is None else
                                 js['textures'][bct['index']]['source'], notes=notes))
        for n in notes:
            sc.notes.append('material "%s": %s' % (name, n))
    # scene graph
    scenes = js.get('scenes', [])
    si = js.get('scene', 0)
    if not scenes:
        probs.append('no scene')
        raise GltfError(probs)
    used_mesh = set()
    nodes = js.get('nodes', [])

    def walk(ni, parent, depth):
        if depth > 64:
            raise GltfError('node hierarchy too deep / cyclic')
        n = nodes[ni]
        m = mat_mul(parent, trs(n))
        if 'mesh' in n:
            used_mesh.add(n['mesh'])
            if 'skin' in n:
                probs.append('node "%s" is skinned' % n.get('name', ni))
            if n.get('weights') or js['meshes'][n['mesh']].get('weights'):
                probs.append('node "%s": morph weights' % n.get('name', ni))
            prims = []
            for pi, p in enumerate(js['meshes'][n['mesh']]['primitives']):
                tag = 'node "%s" prim %d' % (n.get('name', ni), pi)
                extra = [k for k in p.get('attributes', {}) if k not in ALLOWED_ATTR]
                if extra:
                    probs.append('%s: attributes %s not representable (the vertex is position + normal + one UV; vertex '
                                 'colours, tangents, extra UV sets and skin weights are refused)' % (tag, extra))
                if p.get('targets'):
                    probs.append('%s: morph targets' % tag)
                if p.get('mode', 4) != 4:
                    probs.append('%s: mode %d (TRIANGLES only)' % (tag, p['mode']))
                    continue
                if p.get('extensions'):
                    probs.append('%s: primitive extensions (e.g. Draco) not supported' % tag)
                    continue
                at = p.get('attributes', {})
                if 'POSITION' not in at:
                    probs.append('%s: no POSITION' % tag)
                    continue
                if 'TEXCOORD_0' not in at:
                    probs.append('%s: no TEXCOORD_0 (the car texture needs UVs)' % tag)
                    continue
                pr = Prim()
                try:
                    pr.positions = accessor(at['POSITION'], 'POSITION')
                    pr.uvs = accessor(at['TEXCOORD_0'], 'TEXCOORD_0')
                    if 'NORMAL' in at:
                        pr.normals = accessor(at['NORMAL'], 'NORMAL')
                    if 'indices' in p:
                        ix = accessor(p['indices'])
                        if js['accessors'][p['indices']]['componentType'] not in (5121, 5123, 5125):
                            raise GltfError('%s: index type' % tag)
                    else:
                        ix = list(range(len(pr.positions)))
                except GltfError as e:
                    probs.extend(e.problems)
                    continue
                if len(ix) % 3:
                    probs.append('%s: index count %d not a multiple of 3' % (tag, len(ix)))
                    continue
                if ix and max(ix) >= len(pr.positions):
                    probs.append('%s: index beyond the vertex count' % tag)
                    continue
                pr.tris = [tuple(ix[k:k + 3]) for k in range(0, len(ix), 3)]
                pr.material = p.get('material')
                if pr.material is None:
                    probs.append('%s: no material' % tag)
                prims.append(pr)
            sc.nodes.append(SceneMesh(n.get('name', 'node%d' % ni), m, prims))
        for c in n.get('children', []):
            walk(c, m, depth + 1)

    for ni in scenes[si].get('nodes', []):
        walk(ni, IDENT, 0)
    for mi in range(len(js.get('meshes', []))):
        if mi not in used_mesh:
            probs.append('mesh %d "%s" is not instantiated by the active scene (its data would be dropped)'
                         % (mi, js['meshes'][mi].get('name', '')))
    if probs:
        raise GltfError(probs)
    return sc


# ---------------------------------------------------------------- writing (demo meshes, controls)
def write(path, nodes, materials, images, generator='carimport'):
    """nodes: [dict(name, prims=[dict(positions, normals, uvs, tris, material)], translation=None, children=[])]
    materials: [dict(name, image, bm_class)], images: [relative png file name]. Writes PATH (.gltf) and PATH.bin."""
    blob = bytearray()
    views = []
    accs = []

    def add(data, fmt, nc, target, typ, ct, minmax=False):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        for v in data:
            blob.extend(struct.pack('<' + fmt * nc, *(v if nc > 1 else (v,))))
        views.append(dict(buffer=0, byteOffset=off, byteLength=len(blob) - off, target=target))
        a = dict(bufferView=len(views) - 1, componentType=ct, count=len(data), type=typ)
        if minmax:
            a['min'] = [min(v[k] for v in data) for k in range(nc)]
            a['max'] = [max(v[k] for v in data) for k in range(nc)]
        accs.append(a)
        return len(accs) - 1

    meshes = []
    jn = []

    def node(nd):
        prims = []
        for p in nd.get('prims', []):
            at = dict(POSITION=add(p['positions'], 'f', 3, 34962, 'VEC3', 5126, True))
            if p.get('normals'):
                at['NORMAL'] = add(p['normals'], 'f', 3, 34962, 'VEC3', 5126)
            at['TEXCOORD_0'] = add(p['uvs'], 'f', 2, 34962, 'VEC2', 5126)
            flat = [i for t in p['tris'] for i in t]
            big = max(flat) > 65535
            ia = add(flat, 'I' if big else 'H', 1, 34963, 'SCALAR', 5125 if big else 5123)
            prims.append(dict(attributes=at, indices=ia, material=p['material'], mode=4))
        j = dict(name=nd['name'])
        if prims:
            meshes.append(dict(name=nd['name'], primitives=prims))
            j['mesh'] = len(meshes) - 1
        if nd.get('translation'):
            j['translation'] = list(nd['translation'])
        jn.append(j)
        me = len(jn) - 1
        kids = [node(c) for c in nd.get('children', [])]
        if kids:
            jn[me]['children'] = kids
        return me

    roots = [node(n) for n in nodes]
    binname = os.path.splitext(os.path.basename(path))[0] + '.bin'
    js = dict(asset=dict(version='2.0', generator=generator), scene=0, scenes=[dict(nodes=roots)], nodes=jn,
              meshes=meshes, accessors=accs, bufferViews=views,
              buffers=[dict(uri=binname, byteLength=len(blob))],
              materials=[dict(name=m['name'], extras=dict(bm_class=m['bm_class']),
                              pbrMetallicRoughness=dict(baseColorTexture=dict(index=m['image'])))
                         for m in materials],
              textures=[dict(source=i) for i in range(len(images))],
              images=[dict(uri=u, mimeType='image/png') for u in images])
    with open(os.path.join(os.path.dirname(os.path.abspath(path)), binname), 'wb') as f:
        f.write(bytes(blob))
    with open(path, 'w', newline='\n') as f:
        json.dump(js, f, indent=1, sort_keys=True)
