r"""wb_rta_share - recipe-only sharing for retail-style authoring (Workbench 0.33 retail-style authoring, 2026-11-02).

A RECIPE is instructions, not content: the style preset (asset REFERENCES by track id + texture name / model id, and measured
numbers), the route control points, parameters, seed, parts, exclusion areas, extension edits (generated triangles + texture
NAMES), the sha256 of every game-data file it needs, and tool versions. It never contains texels, retail geometry, thumbnails,
caches or built tracks. A recipient rebuilds it from THEIR OWN game data; refused when their files differ.

Package (deterministic zip): recipe.json + SHARING.md. Validation refuses unknown keys, embedded binary / base64 payloads, file
contents, paths of the author's PC, a missing author / licence statement, and anything above 4 MB.
Legal note (written into SHARING.md): a recipe references assets of the game's publisher by name; a local reconstruction from
your own copy is NOT legal clearance. The project's distribution questions Q1-Q9 stay open and are not changed by this tool
(gp\HANDOFF_NEXT_SESSION.md; gp\public_fork records).
"""
import hashlib
import io
import json
import os
import re
import zipfile

SCHEMA = 'bm-rta-recipe/1'
VERSION = 'Workbench 0.33 retail-style authoring 0.1'
MAX_BYTES = 4 * 1024 * 1024
TOP = {'schema', 'kind', 'title', 'author', 'licence', 'created_with', 'requires', 'generation', 'extension', 'design', 'notes'}
DESIGN_KEYS = {'request', 'styles'}
GEN_KEYS = {'style', 'points', 'params', 'seed', 'parts', 'exclude'}
EXT_KEYS = {'track', 'edits'}
LEGAL = ('A recipe is instructions plus REFERENCES (track ids, texture names, model ids, numbers, file hashes). It contains no '
         'game data. Rebuilding it needs the recipient\'s own legally obtained game data, and the result is retail-derived: keep it on '
         'your PC. A local reconstruction is not legal clearance. The Burnout Mashup distribution questions Q1-Q9 remain open.')


class RecipeError(Exception):
    pass


def _walk(o, path='$'):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, '%s.%s' % (path, k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, '%s[%d]' % (path, i))
    else:
        yield path, o


def check(r):
    """-> list of problems (empty = valid)"""
    P = []
    if not isinstance(r, dict) or r.get('schema') != SCHEMA:
        return ['not a %s recipe' % SCHEMA]
    extra = set(r) - TOP
    if extra:
        P.append('unknown top-level keys: %s' % ', '.join(sorted(extra)))
    if r.get('kind') not in ('generation', 'extension', 'design'):
        P.append("kind: 'generation', 'extension' or 'design'")
    if r.get('kind') == 'design' and set(r.get('design') or {}) - DESIGN_KEYS:
        P.append('design: unknown keys %s' % sorted(set(r['design']) - DESIGN_KEYS))
    for k in ('author', 'licence'):
        if not (isinstance(r.get(k), str) and r[k].strip()):
            P.append('%s: required (who made the recipe and under which licence the INSTRUCTIONS are shared)' % k)
    if r.get('kind') == 'generation' and set(r.get('generation') or {}) - GEN_KEYS:
        P.append('generation: unknown keys %s' % sorted(set(r['generation']) - GEN_KEYS))
    if r.get('kind') == 'extension' and set(r.get('extension') or {}) - EXT_KEYS:
        P.append('extension: unknown keys %s' % sorted(set(r['extension']) - EXT_KEYS))
    for path, v in _walk(r):
        if isinstance(v, str):
            if len(v) > 600:
                P.append('%s: a %d-character string (no embedded payloads)' % (path, len(v)))
            elif re.fullmatch(r'[A-Za-z0-9+/=]{120,}', v) or v.startswith('data:'):
                P.append('%s: looks like an embedded binary / base64 payload' % path)
            elif re.match(r'^[A-Za-z]:[\\/]', v) or v.startswith('\\\\'):
                P.append('%s: a local file path (%s...) - recipes hold no paths of your PC' % (path, v[:24]))
        elif isinstance(v, (bytes, bytearray)):
            P.append('%s: binary data' % path)
    for path, v in _walk(r):
        last = path.rsplit('.', 1)[-1]
        if last in ('png', 'png_rows', 'texels', 'rgba', 'bytes', 'thumbnail', 'cache', 'view_cache', 'data_uri'):
            P.append('%s: content keys are never shared' % path)
    n = len(json.dumps(r, sort_keys=True).encode())
    if n > MAX_BYTES:
        P.append('recipe is %d bytes > %d' % (n, MAX_BYTES))
    return P


def _strip_style(s):
    """the style preset without local paths (source folder) - references and numbers only"""
    s = json.loads(json.dumps(s))
    src = s.get('source') or {}
    s['source'] = {k: v for k, v in src.items() if k in ('track', 'catalogue_key', 'source_sha256', 'note')}
    return s


def from_generation(cfg, gen_record, style, author, licence, title=None):
    req_tracks = []
    if (style.get('source') or {}).get('track'):
        req_tracks.append({'track': style['source']['track'], 'files': style['source']['source_sha256']})
    for t, files in sorted((gen_record.get('post_sources') or {}).items()):     # posts copied from other tracks
        if t not in [x['track'] for x in req_tracks]:
            req_tracks.append({'track': t, 'files': files})
    r = {'schema': SCHEMA, 'kind': 'generation', 'title': title or 'Retail-style track (%s)' % style['id'], 'author': author,
         'licence': licence, 'created_with': {'tool': VERSION, 'catalogue': 'bm-rta-catalogue/2', 'style_schema': style.get('schema')},
         'requires': {'game_data': req_tracks},
         'generation': {'style': _strip_style(style), 'points': gen_record['points'], 'params': gen_record['params'],
                        'seed': gen_record['seed'], 'parts': gen_record.get('parts') or {}, 'exclude': gen_record.get('exclude') or []},
         'notes': LEGAL}
    return r


def from_design(design, styles, author, licence, title=None):
    """a designer recipe: the request (route, segments, seed, parts, params) + every style used (references and numbers)"""
    req = {k: v for k, v in design.items() if not k.startswith('_')}
    tracks = {}
    for sid, st in sorted(styles.items()):
        src = st.get('source') or {}
        if src.get('track'):
            tracks[src['track']] = src['source_sha256']
    r = {'schema': SCHEMA, 'kind': 'design', 'title': title or 'Environment design (%d segment(s))' % len(req.get('segments') or []),
         'author': author, 'licence': licence,
         'created_with': {'tool': VERSION + ' / designer', 'catalogue': 'bm-rta-catalogue/2'},
         'requires': {'game_data': [{'track': t, 'files': f} for t, f in sorted(tracks.items())]},
         'design': {'request': req, 'styles': {sid: _strip_style(st) for sid, st in sorted(styles.items())}}, 'notes': LEGAL}
    return r


def from_extension(proj, author, licence, title=None):
    r = {'schema': SCHEMA, 'kind': 'extension', 'title': title or proj['title'], 'author': author, 'licence': licence,
         'created_with': {'tool': VERSION, 'extension_schema': 'bm-rta-extension/1'},
         'requires': {'game_data': [{'track': proj['track'], 'files': proj['retail_sha256']}]},
         'extension': {'track': proj['track'], 'edits': proj['edits']}, 'notes': LEGAL}
    return r


def sharing_md(r):
    req = r['requires']['game_data']
    lines = ['# %s' % r['title'], '', 'Recipe (%s) by %s. Licence of these instructions: %s.' % (r['kind'], r['author'], r['licence']), '',
             '## What you need', '']
    if req:
        for t in req:
            lines.append('- your own Burnout 3 game data with track %s; files must match these sha256 (else the recipe is refused):' % t['track'])
            for n, h in sorted(t['files'].items()):
                lines.append('  - %s `%s`' % (n, h))
    else:
        lines.append('- nothing from any game: this recipe uses original assets only')
    lines += ['', '## How to rebuild', '', 'Burnout Mashup Workbench (retail-style authoring) -> Retail-style panel -> 7 Share -> '
              'Open a recipe -> Check -> Rebuild. Generation recipes run on a new track project (testloop template); extension '
              'recipes create a new extension project from your copy of the track.', '', '## Legal', '', LEGAL, '',
              'Created with %s.' % r['created_with']['tool'], '']
    return '\n'.join(lines)


def package(r, out_zip):
    probs = check(r)
    if probs:
        raise RecipeError('recipe refused: %s' % '; '.join(probs[:6]))
    if os.path.exists(out_zip):
        raise RecipeError('%s exists: choose a new file name' % out_zip)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in (('recipe.json', json.dumps(r, indent=1, sort_keys=True).encode('utf-8')),
                           ('SHARING.md', sharing_md(r).encode('utf-8'))):
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    b = buf.getvalue()
    with open(out_zip + '.tmp', 'wb') as f:
        f.write(b)
    os.replace(out_zip + '.tmp', out_zip)
    return {'zip': out_zip, 'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b), 'files': ['recipe.json', 'SHARING.md']}


def read(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if set(names) != {'recipe.json', 'SHARING.md'}:
                raise RecipeError('a recipe package holds exactly recipe.json + SHARING.md (found %s)' % ', '.join(names[:8]))
            info = z.getinfo('recipe.json')
            if info.file_size > MAX_BYTES:
                raise RecipeError('recipe.json too large')
            r = json.loads(z.read('recipe.json').decode('utf-8'))
    except (OSError, zipfile.BadZipFile, ValueError) as e:
        raise RecipeError('not a readable recipe package (%s)' % e)
    probs = check(r)
    if probs:
        raise RecipeError('recipe refused: %s' % '; '.join(probs[:6]))
    return r


def requirements_met(cfg, r):
    """-> list of problems with the recipient's game data (empty = can rebuild)"""
    out = []
    for t in r['requires']['game_data']:
        f = os.path.join(cfg.get('game_data') or '', 'Tracks', *t['track'].split('/'))
        for n, h in sorted(t['files'].items()):
            p = os.path.join(f, n)
            if not os.path.isfile(p):
                out.append('%s: %s missing in your game data' % (t['track'], n))
                continue
            import wb_retail
            if wb_retail.sha_file(p) != h:
                out.append('%s: your %s differs from the author\'s (another version / region): the recipe cannot be rebuilt exactly' % (t['track'], n))
    return out
