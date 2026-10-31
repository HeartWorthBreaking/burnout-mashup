"""fetex - front-end texture tool for BurnoutMashup ([bmashup.textures]; guide: docs\\TEXTURE_PACKS.md).

Commands (py -3 -B fetex.py <cmd> ...):
  inspect  TXD [--json]                     list entries (name, format, size, palettes, bytes)
  validate TXD [--class frontend]           strict structure + the front-end capability list (exit 1 on a violation)
  extract  TXD OUTDIR [--name REGEX] [--all-palettes]   decode entries to PNG (local only for retail data)
  rebuild  TXD OUT                          parse + re-emit; reports whether the output is byte-identical
  pack     SPEC.json OUT.txd                build a TXD from PNGs (spec below), then validate it
  version                                   tool version and Python

pack spec (JSON): {"tag": 0, "entries": [{"name": "my_photo", "png": "photo.png", "format": "P8" | "DXT1" | "DXT5",
                   "palettes": ["tint_a.png", ...]   # P8 only, optional: extra PNGs of the SAME picture, one per palette
                  }, ...]}   paths relative to the spec file.
P8: the first PNG is quantised to 256 colours (deterministic median cut); each extra palette PNG must map 1:1 onto the same
indices (pixels that share an index in the first picture must share a colour in the others), else it is refused.
Exit codes (mod kit 0.4.1 convention): 0 ok, 1 refused / invalid input (the message says what to change), 2 usage,
3 cannot run (prerequisite missing: Python, tool files), 4 internal error.
"""
import sys

if sys.version_info < (3, 8):
    sys.stderr.write('fetex: CANNOT RUN: Python %d.%d found; fetex needs Python 3.8 or later. Install it from python.org and '
                     'run "py -3 -B fetex.py ...".\n' % sys.version_info[:2])
    sys.exit(3)

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import struct  # noqa: E402
import zlib  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from fetexlib import codec, png, txd  # noqa: E402
except ImportError as _e:
    sys.stderr.write('fetex: CANNOT RUN: installation incomplete (%s). Copy the whole fetex folder (every file listed in '
                     'SHA256SUMS.txt, including fetexlib\\*.py) and run it from there.\n' % _e)
    sys.exit(3)

TOOL_VERSION = '0.2.0'     # first versioned release: portable successor of the content-phase fetex (outputs unchanged)
FORMATS = {'P8': txd.FMT_P8, 'DXT1': txd.FMT_DXT1, 'DXT5': txd.FMT_DXT5}


class PackError(Exception):
    """an input cannot be used; the message names the entry / file and what to change"""


def need_file(path, what):
    if not os.path.exists(path):
        raise PackError('%s %s: no such file (check the path)' % (what, path))
    if os.path.isdir(path):
        raise PackError('%s %s is a folder, not a file' % (what, path))


def out_file(path, what):
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        raise PackError('%s %s: the folder %s does not exist (create it first)' % (what, path, d))
    if os.path.isdir(path):
        raise PackError('%s %s is an existing folder; give a file name' % (what, path))


def read_png(path, entry):
    need_file(path, 'entry %s: picture' % entry)
    try:
        return png.read(path)
    except (ValueError, KeyError, IndexError, TypeError, struct.error, zlib.error) as e:
        raise PackError('entry %s: picture %s cannot be read (%s: %s). fetex reads 8-bit, non-interlaced PNG (RGB, RGBA, '
                        'grey or palette); re-save it as an 8-bit RGBA PNG.' % (entry, path, type(e).__name__, e))


def load(path):
    need_file(path, 'texture dictionary')
    return txd.parse(open(path, 'rb').read())


def decode(e, pal=0):
    if e.fmt == txd.FMT_P8:
        return codec.decode_p8(e.texels, e.palettes[pal], e.w, e.h)
    return codec.decode_dxt(e.texels, e.w, e.h, e.fmt == txd.FMT_DXT5)


def cmd_inspect(a):
    t = load(a.txd)
    rows = [e.info() for e in t.entries]
    if a.json:
        print(json.dumps(dict(tag=t.tag, entries=rows), indent=1))
        return 0
    print('tag %08X, %d entries' % (t.tag, len(rows)))
    for i, r in enumerate(rows):
        print('%4d %-31s %-4s %4dx%-4d pal %d bits %2d %8d B' % (i + 1, r['name'], r['format'], r['w'], r['h'],
                                                               r['palettes'], r['bits'], r['bytes']))
    return 0


def cmd_validate(a):
    try:
        t = load(a.txd)
    except txd.TxdError as ex:
        print('INVALID structure: %s' % ex)
        return 1
    bad = txd.check_frontend(t) if a.cls == 'frontend' else ['class %s has no external textures in v1 (in-file only)' % a.cls]
    for m in bad:
        print('REFUSED: %s' % m)
    if not bad:
        print('OK: %d entries, %d bytes, class %s' % (len(t.entries), sum(e.size() for e in t.entries), a.cls))
    return 1 if bad else 0


def cmd_extract(a):
    t = load(a.txd)
    try:
        rx = re.compile(a.name, re.I) if a.name else None
    except re.error as e:
        raise PackError('--name %r is not a valid regular expression (%s)' % (a.name, e))
    if os.path.isfile(a.outdir):
        raise PackError('extract output %s is a file; give a folder' % a.outdir)
    os.makedirs(a.outdir, exist_ok=True)
    n = 0
    for e in t.entries:
        if rx and not rx.search(e.name):
            continue
        pals = range(len(e.palettes)) if (a.all_palettes and e.palettes) else [0]
        for k in pals:
            suffix = '_pal%d' % k if len(pals) > 1 else ''
            png.write(os.path.join(a.outdir, '%s%s.png' % (e.name, suffix)), e.w, e.h, decode(e, k))
            n += 1
    print('%d PNG written to %s' % (n, a.outdir))
    return 0


def cmd_rebuild(a):
    need_file(a.txd, 'texture dictionary')
    out_file(a.out, 'rebuild output')
    src = open(a.txd, 'rb').read()
    out = txd.build(txd.parse(src))
    open(a.out, 'wb').write(out)
    same = out == src
    print('rebuilt %d bytes: %s' % (len(out), 'BYTE-IDENTICAL' if same else 'DIFFERENT'))
    return 0 if same else 1


def make_entry(spec, base):
    if not isinstance(spec, dict):
        raise PackError('pack spec: each entry must be an object {"name", "png", "format"}, got %r' % (spec,))
    miss = [k for k in ('name', 'png', 'format') if k not in spec]
    if miss:
        raise PackError('pack spec entry %r: missing %s' % (spec.get('name', '?'), ', '.join(miss)))
    name = spec['name']
    if spec['format'] not in FORMATS:
        raise PackError('entry %s: format %r is not supported. Use "P8" (paletted, 1..8 palettes), "DXT1" (opaque) or '
                        '"DXT5" (alpha) - the front-end capability list v1; DXT3, ARGB, 16-colour P8, mips, cube and '
                        'volume textures are refused by the host.' % (name, spec['format']))
    fmt = FORMATS[spec['format']]
    w, h, px = read_png(os.path.join(base, spec['png']), name)
    if not (w & (w - 1) == 0 and h & (h - 1) == 0 and w >= 4 and h >= 4):
        raise PackError('entry %s: picture %s is %dx%d; both sides must be powers of two, 4..1024 (resize it, e.g. to '
                        '%dx%d)' % (name, spec['png'], w, h, max(4, 1 << (w - 1).bit_length()),
                                    max(4, 1 << (h - 1).bit_length())))
    if fmt == txd.FMT_DXT1:
        return txd.Entry(name, fmt, w, h, codec.encode_dxt1(px, w, h))
    if fmt == txd.FMT_DXT5:
        return txd.Entry(name, fmt, w, h, codec.encode_dxt5(px, w, h))
    pal, idx = codec.quantize(px)
    palettes = [codec.palette_bytes(pal)]
    for extra in spec.get('palettes', []):
        w2, h2, px2 = read_png(os.path.join(base, extra), name)
        if (w2, h2) != (w, h):
            raise PackError('%s: palette picture %s has another size' % (name, extra))
        cols = [None] * 256
        for i, c in zip(idx, px2):
            if cols[i] is None:
                cols[i] = c
            elif cols[i] != c:
                raise PackError('%s: palette picture %s does not map 1:1 onto the indices of %s' % (name, extra, spec['png']))
        palettes.append(codec.palette_bytes([c or (0, 0, 0, 0) for c in cols]))
    return txd.Entry(name, fmt, w, h, codec.swizzle(bytes(idx), w, h), palettes)


def pack(spec_path):
    need_file(spec_path, 'pack spec')
    try:
        spec = json.load(open(spec_path))
    except ValueError as e:
        raise PackError('pack spec %s is not valid JSON (%s)' % (spec_path, e))
    if not isinstance(spec, dict) or not isinstance(spec.get('entries'), list) or not spec['entries']:
        raise PackError('pack spec %s: needs {"entries": [ ... ]} with at least one entry (README: pack spec)' % spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    t = txd.Txd([make_entry(s, base) for s in spec['entries']], spec.get('tag', 0))
    return t, txd.build(t)


def cmd_pack(a):
    out_file(a.out, 'pack output')
    t, b = pack(a.spec)
    bad = txd.check_frontend(t)
    if bad:
        for m in bad:
            print('REFUSED: %s' % m)
        return 1
    if txd.build(txd.parse(b)) != b:
        print('internal error: the packed file does not round-trip')
        return 4
    open(a.out, 'wb').write(b)
    print('packed %d entries, %d bytes -> %s' % (len(t.entries), len(b), a.out))
    return 0


def cmd_version(a):
    print('fetex %s (Python %s)' % (TOOL_VERSION, sys.version.split()[0]))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog='fetex', description=__doc__.split('\n')[0])
    s = p.add_subparsers(dest='cmd', required=True)
    q = s.add_parser('inspect')
    q.add_argument('txd')
    q.add_argument('--json', action='store_true')
    q = s.add_parser('validate')
    q.add_argument('txd')
    q.add_argument('--class', dest='cls', default='frontend', choices=['frontend', 'car', 'track'])
    q = s.add_parser('extract')
    q.add_argument('txd')
    q.add_argument('outdir')
    q.add_argument('--name')
    q.add_argument('--all-palettes', action='store_true')
    q = s.add_parser('rebuild')
    q.add_argument('txd')
    q.add_argument('out')
    q = s.add_parser('pack')
    q.add_argument('spec')
    q.add_argument('out')
    s.add_parser('version')
    a = p.parse_args(argv)
    fn = {'inspect': cmd_inspect, 'validate': cmd_validate, 'extract': cmd_extract, 'rebuild': cmd_rebuild,
          'pack': cmd_pack, 'version': cmd_version}[a.cmd]
    try:
        return fn(a)
    except PackError as e:
        print('REFUSED: %s' % e)
        return 1
    except txd.TxdError as e:
        print('INVALID texture dictionary: %s (fetex reads Burnout 3 Xbox .txd files; this one breaks the layout at the '
              'named place)' % e)
        return 1
    except OSError as e:
        print('ERROR: file system: %s (check the path, that the folder exists and is writable, and free disk space)' % e)
        return 1
    except Exception as e:  # noqa: BLE001 - never a bare traceback for a user
        import traceback
        print('INTERNAL ERROR in fetex %s (%s: %s). Please report it with the command line and this text:' %
              (TOOL_VERSION, type(e).__name__, e))
        traceback.print_exc(file=sys.stdout)
        return 4


if __name__ == '__main__':
    sys.exit(main())
