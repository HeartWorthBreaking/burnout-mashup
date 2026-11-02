"""wb_te_share - Workbench 0.33 shareable source export (Workbench 0.33, 2026-11-01), a mixin of wb_trackedit.TrackSource.

share_export writes a zip someone else can import (import_sources) and build with their OWN game data:
- every file gets a provenance class: kit template (unchanged output of the kit's own generator), edited kit template, imported
  original file (editor_provenance.json: author + licence), or UNKNOWN;
- excluded by default: UNKNOWN files and anything the kit treats as game / build data (container and audio names / types) -
  retail-derived data never goes into a shareable export; UNKNOWN files can be included only with include_unknown = true AND a
  declared author + licence for them (the user's statement, recorded as such);
- SHARING.md + MANIFEST.json: per-file sha256 / provenance / licence, the donor requirements (what the build reads from the
  receiver's own game data), tool versions (Workbench, trackbuild + its SHA256SUMS hash, kit, python) and the reproduction steps;
- deterministic zip (sorted entries, fixed timestamps): exporting the same saved project twice gives identical bytes.
The existing export_sources (0.31) is unchanged.
"""
import hashlib
import json
import os
import zipfile

T = {}
GAME_NAMES = ('static.dat', 'streamed.dat', 'gamedata.bgd', 'enviro.dat', 'sound.awd', 'music.rws', 'e_djrace.xwb', 'default.xbe')
GAME_EXT = ('.rws', '.awd', '.xwb', '.bgd', '.xbe', '.iso', '.xiso')
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def E(msg, detail=None):
    e = T['EditError'](msg)
    if detail is not None:
        e.detail = detail
    return e


def _is_game(rel):
    b = os.path.basename(rel).lower()
    return b in GAME_NAMES or b.endswith(GAME_EXT) or '/build/' in '/' + rel.lower() or rel.lower().startswith(('staging/', 'build/'))


class ShareMixin:
    def _share_plan(self, include_unknown=False, unknown_author=None, unknown_licence=None):
        import wb_stage as stg
        if not isinstance(include_unknown, bool):
            raise E('include_unknown: true or false')
        files = {rel: h for rel, h in stg.tree_hashes(self.project).items() if not rel.endswith('.wb_tmp')}
        try:
            ident = json.load(open(os.path.join(self.project, 'workbench-track.json'), encoding='utf-8'))
        except (OSError, ValueError):
            ident = {}
        tmpl = ident.get('template') if isinstance(ident.get('template'), dict) else {}
        tfiles = tmpl.get('files') or {}
        try:
            prov = json.load(open(os.path.join(self.project, 'editor_provenance.json'), encoding='utf-8'))
        except (OSError, ValueError):
            prov = {}
        prov_files = prov.get('files', prov) if isinstance(prov, dict) else {}
        retail_blocks = sorted(k for k, c in self.constructs().items() if c['meta'].get('kind') == 'retail_copy' or c['meta'].get('local_only'))
        retail_tex = sorted(r for r, p in (prov_files.items() if isinstance(prov_files, dict) else []) if isinstance(p, dict) and p.get('origin') == 'retail')
        if retail_blocks or retail_tex:
            raise E('LOCAL ONLY: this project holds retail-derived content (blocks %s, textures %s) copied from your own game data; it '
                    'cannot be exported for sharing. Share a copy of the project without those blocks / textures instead' % (
                        retail_blocks[:6] or 'none', retail_tex[:6] or 'none'))
        rows, excluded = {}, []
        own = {'workbench-track.json', 'package.toml', 'README.txt', 'editor_provenance.json'}
        for rel, h in sorted(files.items()):
            if _is_game(rel):
                excluded.append({'file': rel, 'why': 'game / build data (never shared; the receiver uses their own game data)'})
                continue
            if rel in tfiles and tfiles[rel] == h:
                rows[rel] = {'sha256': h, 'provenance': 'kit template (unchanged output of %s)' % tmpl.get('generator', 'the kit generator'),
                             'licence': 'the modding kit\'s licence (generator output)'}
            elif rel in tfiles:
                rows[rel] = {'sha256': h, 'provenance': 'kit template edited in the Workbench (author: the project owner)',
                             'licence': 'kit licence for the template part; the owner\'s choice for the edits'}
            elif isinstance(prov_files, dict) and rel in prov_files and isinstance(prov_files[rel], dict):
                p = prov_files[rel]
                rows[rel] = {'sha256': h, 'provenance': 'imported original file (editor_provenance.json)', 'author': p.get('author'),
                             'licence': p.get('licence'), 'note': p.get('note')}
            elif rel in own or rel == ident.get('desc'):
                rows[rel] = {'sha256': h, 'provenance': 'project file written by the Workbench / editor', 'licence': 'the project owner\'s'}
            else:
                if include_unknown:
                    if not (isinstance(unknown_author, str) and unknown_author.strip() and isinstance(unknown_licence, str) and unknown_licence.strip()):
                        raise E('include_unknown needs unknown_author and unknown_licence (your statement for those files)')
                    rows[rel] = {'sha256': h, 'provenance': 'UNKNOWN to the editor; included on the exporter\'s statement',
                                 'author': unknown_author, 'licence': unknown_licence}
                else:
                    excluded.append({'file': rel, 'why': 'unknown provenance (not a kit template file, not an imported file with a '
                                                         'provenance record): excluded; include it only with include_unknown + author + licence'})
        if not any(r.endswith('.obj') for r in rows):
            raise E('nothing buildable would be exported (no OBJ among the shareable files): %s' % [x['file'] for x in excluded][:5])
        return files, rows, excluded, ident

    def share_export_preview(self, dest=None, include_unknown=False, unknown_author=None, unknown_licence=None):
        if self.dirty():
            raise E('unsaved edits: Save first (the export holds the saved sources)')
        _f, rows, excluded, ident = self._share_plan(include_unknown, unknown_author, unknown_licence)
        return {'ok': True, 'include': rows, 'exclude': excluded, 'donor_dependency': ident.get('donor_dependency'),
                'preview_key': self._cons_key('share', {'d': dest, 'u': include_unknown, 'a': unknown_author, 'l': unknown_licence}),
                'note': 'preview only: nothing written',
                'summary_lines': ['shareable export: %d file(s) included, %d excluded' % (len(rows), len(excluded))] +
                ['  exclude %s: %s' % (x['file'], x['why'][:90]) for x in excluded[:20]]}

    def share_export(self, dest=None, include_unknown=False, unknown_author=None, unknown_licence=None, preview_key=None):
        if self.dirty():
            raise E('unsaved edits: Save first (the export holds the saved sources)')
        if preview_key != self._cons_key('share', {'d': dest, 'u': include_unknown, 'a': unknown_author, 'l': unknown_licence}):
            raise E('NEEDS PREVIEW: preview the export first and apply it with its preview_key')
        if not (isinstance(dest, str) and dest.lower().endswith('.zip')):
            raise E('dest: a new .zip path')
        self._dest_ok(dest, 'export destination')
        _f, rows, excluded, ident = self._share_plan(include_unknown, unknown_author, unknown_licence)
        v0 = self.versions()                                # no local paths in a shared file (privacy; they mean nothing elsewhere)
        ver = {'editor': v0.get('editor'), 'python': v0.get('python'),
               'trackbuild': {k: (v0.get('trackbuild') or {}).get(k) for k in ('version', 'sha256sums_sha256')},
               'kit': {'version': (v0.get('kit') or {}).get('version')},
               'project': {k: v for k, v in (v0.get('project') or {}).items()}}
        man = {'format': 'workbench-track-sources 1', 'share': 'workbench-share 1', 'files': {r: x['sha256'] for r, x in rows.items()},
               'provenance': rows, 'excluded': excluded, 'versions': ver, 'donor_dependency': ident.get('donor_dependency'),
               'identity': {k: ident.get(k) for k in ('mod_id', 'track_id', 'desc')},
               'note': 'original sources only; build with the Workbench (Build -> Validate -> Stage) against your own game data'}
        sharing = self._sharing_md(rows, excluded, ident, ver)
        tmp = dest + '.wb_tmp'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            def put(name, data):
                zi = zipfile.ZipInfo(name, FIXED_TIME)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                z.writestr(zi, data)
            for rel in sorted(rows):
                put('sources/' + rel, open(os.path.join(self.project, *rel.split('/')), 'rb').read())
            put('MANIFEST.json', json.dumps(man, indent=1, sort_keys=True))
            put('SHARING.md', sharing)
        os.replace(tmp, dest)
        return {'ok': True, 'zip': dest, 'files': len(rows), 'excluded': excluded, 'bytes': os.path.getsize(dest),
                'sha256': hashlib.sha256(open(dest, 'rb').read()).hexdigest(),
                'summary_lines': ['shareable export %s: %d file(s), %d excluded; SHARING.md + MANIFEST.json (provenance, licences, donor '
                                  'requirements, versions)' % (dest, len(rows), len(excluded))]}

    def _sharing_md(self, rows, excluded, ident, ver):
        dd = ident.get('donor_dependency') or {}
        L = ['# %s - shareable track sources' % (ident.get('mod_id') or 'track'), '',
             'Made with the Burnout Mashup Workbench track editor. These are ORIGINAL sources only: no game data, no retail-derived '
             'files and no build output.', '', '## What the build needs from you (donor requirements)',
             'The build reads parts of YOUR OWN legally obtained game data at build time; nothing of it is in this zip.']
        for k in sorted(dd):
            L.append('- %s: %s' % (k, dd[k]))
        L += ['- sky / lighting (enviro), audio and the event header are copied from the donor track at build time (the editor cannot '
              'author them yet); the result is therefore NOT independent of the donor.',
              '- a BUILT package contains retail game data: keep it local; share this source zip, never a built / staged package.', '',
              '## Reproduce the build', '1. Install the %s (or later) and its modding kit; trackbuild %s.' % (
                  ver.get('editor') or 'Workbench', (ver.get('trackbuild') or {}).get('version') or '?'),
              '2. Track editor -> "9 Import a source zip as a NEW project" (or Workbench -> import) -> pick this zip; the manifest is verified.',
              '3. Open it, then "Build, validate, stage + prepare test". The kit gates decide; nothing is launched.',
              '4. Compare: MANIFEST.json lists the sha256 of every source file and the tool versions used here.', '',
              '## Files and licences', '| file | provenance | author | licence |', '|---|---|---|---|']
        for rel, x in sorted(rows.items()):
            L.append('| %s | %s | %s | %s |' % (rel, x['provenance'], x.get('author') or '-', x.get('licence') or '-'))
        L += ['', '## Not included']
        L += ['- %s: %s' % (x['file'], x['why']) for x in excluded] or ['- nothing']
        L += ['', '## Tool versions', '```', json.dumps(ver, indent=1, sort_keys=True, default=str)[:4000], '```', '']
        return '\n'.join(L)

    SHARE_LAYOUT = {'share_export_preview': 'share_export_preview', 'share_export': 'share_export'}
