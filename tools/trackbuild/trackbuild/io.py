"""trackbuild.io - source readers: OBJ (with the `v x y z r g b` colour extension), PNG (8-bit RGB / RGBA, non-interlaced),
track description JSON. Unsupported input is REFUSED with a reason, never silently dropped."""
import json
import struct
import zlib


class SourceError(Exception):
    pass


def need(c, msg):
    if not c:
        raise SourceError(msg)


def read_obj(path):
    """-> {"faces": [(material, [(pos, uv, normal, rgb)])], "materials_used": [...], "counts": {...}}"""
    V, VT, VN = [], [], []
    faces = []
    mat = None
    with open(path, "r", encoding="ascii") as fh:
        for ln, line in enumerate(fh, 1):
            s = line.split("#", 1)[0].strip()
            if not s:
                continue
            k, *a = s.split()
            if k == "v":
                need(len(a) in (3, 6), "line %d: v needs 3 or 6 numbers" % ln)
                f = [float(x) for x in a]
                V.append((tuple(f[:3]), tuple(f[3:6]) if len(f) == 6 else (0.5, 0.5, 0.5)))
            elif k == "vt":
                need(len(a) >= 2, "line %d: vt needs u v" % ln)
                VT.append((float(a[0]), float(a[1])))
            elif k == "vn":
                need(len(a) == 3, "line %d: vn needs 3 numbers" % ln)
                VN.append(tuple(float(x) for x in a))
            elif k == "usemtl":
                need(len(a) == 1, "line %d: usemtl NAME" % ln)
                mat = a[0]
            elif k == "f":
                need(mat is not None, "line %d: face before any usemtl" % ln)
                need(3 <= len(a) <= 4, "line %d: only triangles and quads are supported (got %d vertices)" % (ln, len(a)))
                fv = []
                for x in a:
                    parts = x.split("/")
                    need(len(parts) == 3 and all(parts), "line %d: faces must be v/vt/vn (uv and normal required)" % ln)
                    vi, ti, ni = (int(q) for q in parts)
                    need(vi > 0 and ti > 0 and ni > 0, "line %d: negative / zero indices are not supported" % ln)
                    need(vi <= len(V) and ti <= len(VT) and ni <= len(VN), "line %d: index out of range" % ln)
                    pos, rgb = V[vi - 1]
                    fv.append((pos, VT[ti - 1], VN[ni - 1], rgb))
                faces.append((mat, fv))
            elif k in ("mtllib", "o", "g", "s"):
                pass
            else:
                raise SourceError("line %d: unsupported OBJ statement %r (supported: v vt vn f usemtl mtllib o g s)" % (ln, k))
    return {"faces": faces, "materials_used": sorted({m for m, _ in faces}),
            "counts": {"v": len(V), "vt": len(VT), "vn": len(VN), "f": len(faces)}}


def read_png(path):
    """-> (w, h, rows of (r, g, b))"""
    w, h, rows, _ = read_png_alpha(path)
    return w, h, rows


def read_png_alpha(path):
    """-> (w, h, rows of (r, g, b), minimum alpha (255 for RGB)) - 0.2.0: the alpha minimum lets the importer refuse
    transparent textures (0.1 materials are opaque DXT1; alpha was silently ignored before)"""
    b = open(path, "rb").read()
    need(b[:8] == b"\x89PNG\r\n\x1a\n", "%s: not a PNG" % path)
    o, idat, ihdr = 8, b"", None
    while o < len(b):
        n, t = struct.unpack_from(">I4s", b, o)
        d = b[o + 8:o + 8 + n]
        if t == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", d)
        elif t == b"IDAT":
            idat += d
        o += 12 + n
    need(ihdr is not None, "%s: no IHDR" % path)
    w, h, depth, ctype, _, _, inter = ihdr
    need(depth == 8 and ctype in (2, 6) and inter == 0, "%s: only 8-bit RGB / RGBA non-interlaced PNG is supported" % path)
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev = [], bytearray(stride)
    amin = 255
    p = 0
    for _ in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            up = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + up) & 255
            elif ft == 3:
                line[i] = (line[i] + (a + up) // 2) & 255
            elif ft == 4:
                pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                pr = a if pa <= pb and pa <= pc else (up if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
            else:
                need(ft == 0, "%s: bad PNG filter %d" % (path, ft))
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
        if bpp == 4:
            amin = min(amin, min(line[3::4]))
        prev = line
    return w, h, rows, amin


def read_desc(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except OSError as e:
        raise SourceError("cannot read the track description %s: %s" % (path, e.strerror or e))
    except ValueError as e:
        raise SourceError("%s is not valid JSON (UTF-8): %s" % (path, e))
    need(isinstance(d, dict), "%s: the description must be a JSON object" % path)
    need(d.get("format") == "trackbuild.track/1", "%s: format must be trackbuild.track/1" % path)
    for k in ("obj", "materials", "rows", "stations", "units", "route", "grid", "start_line", "checkpoints", "stations_per_slice"):
        need(k in d, "%s: missing key %s" % (path, k))
    need(d.get("closed") is True, "only closed (circuit) tracks are supported in trackbuild 0.1")
    return d
