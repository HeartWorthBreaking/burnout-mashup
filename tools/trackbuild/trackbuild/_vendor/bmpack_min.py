"""bmpack_min - the pure-Python subset of bmpack 1.2 that trackconv.package needs (base-40 IDs, the documented Gamedata
rename rule, the manifest verify). Functions copied VERBATIM (provenance in VENDOR.json); the mutation switch of the
test build is fixed at 0 (no mutation). The compiled host-reader checker (validate) is NOT part of it: run the mod kit's
bmpack validate on a packaged set (tb.py package --bmpack FILE does that for you)."""
import hashlib, json, pathlib, struct

MUT = 0


VERSION = '1'


TOOL_VERSION = '1.2'


B40 = ' -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'


class BmpackError(Exception):
    pass


def enc(s):
    if not 0 < len(s) <= 12 or any(c not in B40 for c in s):
        raise BmpackError('%r is not a base-40 ID (characters %s, at most 12)' % (s, B40.strip()))
    v = 0
    for c in s.ljust(12):
        v = v * 40 + B40.index(c)
    return v


def dec(v):
    s = ''
    for _ in range(12):
        s = B40[v % 40] + s
        v //= 40
    return s.rstrip()


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def rename_gamedata(gd, donor, new):
    """the documented rule; returns the list of renamed fields"""
    old_id, new_id = enc(donor), enc(new)
    oc, nc = donor.replace('_', ''), new.replace('_', '')
    changed = []
    lo = 0x3000 if MUT != 2 else 0x8               # MUT 2: the header's keys renamed too (outside the documented fields)
    for o in range(lo, min(len(gd), 0x3800 + 0x800 * 64), 8):
        v = struct.unpack_from('<Q', gd, o)[0]
        if v == old_id:
            struct.pack_into('<Q', gd, o, new_id)
            changed.append({'offset': '0x%X' % o, 'from': donor, 'to': new})
        elif v and v < 40 ** 12:
            s = dec(v)
            if len(s) == 12 and s.endswith(oc):
                ns = s[:6] + nc
                struct.pack_into('<Q', gd, o, enc(ns))
                changed.append({'offset': '0x%X' % o, 'from': s, 'to': ns})
    return changed


def _inside(rel):
    """a manifest key is a relative POSIX path inside the mod: no drive / root, no '..', no backslash (pathlib would join an
    absolute key by DROPPING the mod folder, so verify would read a file outside the mod)"""
    if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel or rel.startswith('/'):
        return False
    parts = rel.split('/')
    return all(x not in ('', '.', '..') for x in parts)


def verify(mod_dir):
    mod_dir = pathlib.Path(mod_dir)
    if MUT != 10:
        mod_dir = mod_dir.resolve()                 # one absolute form for every join and relative_to below
        if not mod_dir.is_dir():
            raise BmpackError('%s is not a folder' % mod_dir)
        if not (mod_dir / 'bmpack.json').is_file():
            subs = sorted(d.name for d in mod_dir.iterdir() if d.is_dir() and (d / 'bmpack.json').is_file())
            raise BmpackError('%s has no bmpack.json (not a mod built by bmpack)%s' % (
                mod_dir, '; it holds built mods - verify each: %s' % ', '.join(subs) if subs else ''))
    try:
        j = json.loads((mod_dir / 'bmpack.json').read_text(encoding='utf-8'))
        files = j['files']
        assert isinstance(files, dict)
    except (ValueError, KeyError, AssertionError) as e:
        raise BmpackError('%s: bmpack.json is not a bmpack manifest (%s)' % (mod_dir, e))
    bad = []
    have = {p.relative_to(mod_dir).as_posix() for p in mod_dir.rglob('*') if p.is_file() and p.name != 'bmpack.json'}
    for rel, d in files.items():
        if MUT != 10 and not _inside(rel):
            bad.append('not a relative path inside the mod: %s' % rel)
            continue
        p = mod_dir / rel
        if not p.is_file():
            bad.append('missing %s' % rel)
        elif sha(p) != d['sha256']:
            bad.append('changed %s' % rel)
    bad += ['not in the manifest: %s' % r for r in sorted(have - set(files))]
    return bad


def validate(roots):
    raise BmpackError("host-reader validation is not vendored: run the mod kit's bmpack validate (tb.py package --bmpack FILE)")
