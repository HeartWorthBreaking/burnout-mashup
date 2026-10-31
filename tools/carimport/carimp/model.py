"""Scene (glTF) -> car IR: per LOD body mesh grouped by material class, wheel mesh, texture source.

Node naming (scope of slice 1):
  body, body.*            the body (all such nodes merged) = LOD 3 (highest detail) and, unless overridden, every LOD
  body_lod0/1/2           optional lower-detail bodies for LOD 0 (lowest) .. 2
  wheel                   optional ONE wheel in wheel-local space (axle = X, centred at the origin); the game draws it at
                          each of the donor's wheel matrices (header +0xB80) for the three spin-blur lists L7 / L8 / L9
Any other node that carries a mesh is REFUSED (lights, glass parts, detachable panels, extra hierarchy: not in slice 1).
Coordinates: glTF metres, +Y up, +Z = car front, +X = car left (right-handed) == the game's car frame (retail evidence: strip
winding vs stored normals 146426 / 154; cabin / driver geometry on +X in 64 / 67 race cars; runtime check: the AUTHORED marker
fin). Node transforms are baked; a negative-determinant transform flips the triangle order (never silently mirrored).
Normals: glTF NORMAL, or flat face normals when absent (glTF 2.0 s3.7.2.1 rule), always renormalised.
"""
import math

from .gltf import GltfError, det3, normal_matrix, xform_normal, xform_point

LOD_NAMES = {'body_lod0': 0, 'body_lod1': 1, 'body_lod2': 2}


class Mesh:
    """verts: [(pos, normal, uv)], groups: {cls: [(a, b, c)]} (CCW front = outward in the car frame)."""

    def __init__(self):
        self.verts = []
        self.index = {}
        self.groups = {}

    def vert(self, p, n, uv):
        key = (tuple(round(x, 6) for x in p), tuple(round(x, 5) for x in n), tuple(round(x, 6) for x in uv))
        i = self.index.get(key)
        if i is None:
            i = len(self.verts)
            self.verts.append((tuple(p), tuple(n), tuple(uv)))
            self.index[key] = i
        return i

    def tri_count(self):
        return sum(len(t) for t in self.groups.values())

    def bounds(self):
        if not self.verts:
            return None
        return ([min(v[0][k] for v in self.verts) for k in range(3)], [max(v[0][k] for v in self.verts) for k in range(3)])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / ln, v[1] / ln, v[2] / ln) if ln > 1e-20 else None


def add_node(mesh, node, materials, notes):
    m = node.matrix
    flip = det3(m) < 0
    nm = normal_matrix(m)
    degen = 0
    for pr in node.prims:
        cls = materials[pr.material]['cls']
        pos = [xform_point(m, p) for p in pr.positions]
        nrm = [xform_normal(nm, n) for n in pr.normals] if pr.normals else None
        tris = mesh.groups.setdefault(cls, [])
        for t in pr.tris:
            a, b, c = t if not flip else (t[0], t[2], t[1])
            fn = _norm(_cross(_sub(pos[b], pos[a]), _sub(pos[c], pos[a])))
            if fn is None:
                degen += 1
                continue
            ids = []
            for k in (a, b, c):
                n = nrm[k] if nrm else fn
                ids.append(mesh.vert(pos[k], n, pr.uvs[k]))
            tris.append(tuple(ids))
    if flip:
        notes.append('node "%s": negative-determinant transform baked (triangle order reversed to keep outward faces)'
                     % node.name)
    if degen:
        notes.append('node "%s": %d zero-area triangles skipped (they draw nothing)' % (node.name, degen))


def build_ir(scene):
    probs = []
    notes = list(scene.notes)
    bodies = {}
    wheel = None
    images = set()
    for nd in scene.nodes:
        nm = nd.name.lower()
        for pr in nd.prims:
            images.add(scene.materials[pr.material]['image'])
        if nm == 'body' or nm.startswith('body.'):
            add_node(bodies.setdefault(3, Mesh()), nd, scene.materials, notes)
        elif nm in LOD_NAMES:
            add_node(bodies.setdefault(LOD_NAMES[nm], Mesh()), nd, scene.materials, notes)
        elif nm == 'wheel':
            if wheel is not None:
                probs.append('more than one "wheel" node (one wheel mesh, instanced by the game)')
                continue
            wheel = Mesh()
            add_node(wheel, nd, scene.materials, notes)
        else:
            probs.append('mesh node "%s" not supported in slice 1 (allowed: body, body.*, body_lod0..2, wheel)' % nd.name)
    if 3 not in bodies or not bodies[3].tri_count():
        probs.append('no "body" mesh with triangles')
    if len(images) > 1:
        probs.append('materials use %d different images: a car has exactly one texture' % len(images))
    if not images:
        probs.append('no texture image')
    if wheel is not None:
        if 'glass' in wheel.groups:
            probs.append('wheel uses a glass material (not supported)')
        b = wheel.bounds()
        c = [(b[0][k] + b[1][k]) / 2 for k in range(3)]
        if max(abs(x) for x in c) > 0.05:
            probs.append('wheel mesh not centred at the origin (centre %s): model it in wheel-local space' %
                         ['%.3f' % x for x in c])
    if probs:
        raise GltfError(probs)
    lods = [bodies.get(k, bodies[3]) for k in range(4)]
    for k in range(3):
        if k not in bodies:
            notes.append('LOD %d: reuses the LOD 3 body (no body_lod%d node)' % (k, k))
    return dict(lods=lods, wheel=wheel, image=scene.materials[0]['image'] if scene.materials else None,
                image_png=scene.images[list(images)[0]]['png'], notes=notes)


def gen_wheel(radius, width=0.22, segs=16, uv_box=(0.0, 0.0, 0.0625, 0.125)):
    """Neutral generated wheel (when the glTF has no 'wheel' node): a closed cylinder, axle along X, centred at the origin,
    radius = the donor's wheel radius (header +0x18), width 0.22 m (retail wheel lists span x -0.12..0.13). UVs sample the
    texture box uv_box (default: the top-left 32x32 texels). Basis: retail L7 meshes are wheel-local, radius ~ +0x18."""
    m = Mesh()
    u0, v0, u1, v1 = uv_box
    tris = m.groups.setdefault('plain', [])
    hw = width / 2
    ring = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        ring.append((math.cos(a), math.sin(a)))
    for i in range(segs):
        (y0, z0), (y1, z1) = ring[i], ring[(i + 1) % segs]
        uA = u0 + (u1 - u0) * i / segs
        uB = u0 + (u1 - u0) * (i + 1) / segs
        n0 = (0.0, y0, z0)
        n1 = (0.0, y1, z1)
        a = m.vert((-hw, y0 * radius, z0 * radius), n0, (uA, v0))
        b = m.vert((hw, y0 * radius, z0 * radius), n0, (uA, v1))
        c = m.vert((hw, y1 * radius, z1 * radius), n1, (uB, v1))
        d = m.vert((-hw, y1 * radius, z1 * radius), n1, (uB, v0))
        # outward: check with the cross product (CCW front)
        for t in ((a, d, c), (a, c, b)):
            p = [m.verts[k][0] for k in t]
            fn = _cross(_sub(p[1], p[0]), _sub(p[2], p[0]))
            mid = [(p[0][k] + p[1][k] + p[2][k]) / 3 for k in range(3)]
            if fn[1] * mid[1] + fn[2] * mid[2] < 0:
                t = (t[0], t[2], t[1])
            tris.append(t)
    for side, sx in ((-1, -hw), (1, hw)):
        n = (float(side), 0.0, 0.0)
        cidx = m.vert((sx, 0.0, 0.0), n, ((u0 + u1) / 2, (v0 + v1) / 2))
        for i in range(segs):
            (y0, z0), (y1, z1) = ring[i], ring[(i + 1) % segs]
            a = m.vert((sx, y0 * radius, z0 * radius), n, (u0 + (u1 - u0) * (0.5 + 0.5 * y0), v0 + (v1 - v0) * (0.5 + 0.5 * z0)))
            b = m.vert((sx, y1 * radius, z1 * radius), n, (u0 + (u1 - u0) * (0.5 + 0.5 * y1), v0 + (v1 - v0) * (0.5 + 0.5 * z1)))
            t = (cidx, a, b)
            p = [m.verts[k][0] for k in t]
            fn = _cross(_sub(p[1], p[0]), _sub(p[2], p[0]))
            if fn[0] * side < 0:
                t = (cidx, b, a)
            tris.append(t)
    return m
