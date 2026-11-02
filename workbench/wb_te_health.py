"""wb_te_health - Workbench 0.33 project health (Workbench 0.33, 2026-11-01): explicit OBJ compaction and optional backup
retention, as a mixin of wb_trackedit.TrackSource (through wb_te_author.AuthorMixin).

Compaction removes v / vt / vn lines that no face uses (old lines left behind by re-generated blocks, terrain strokes and mesh
edits) and renumbers the f lines. Everything else stays byte for byte: comments, construction tags, usemtl / face order, the
whitespace of each f line. Equivalence is proven three ways before Apply: every face corner resolves to the SAME v / vt / vn text
as before, every non-record line is unchanged, and the kit's build_units dry run gives identical per-unit streamed blocks
(sha256 of mesh + LOD + collision + PVS bytes). A backup of the editor buffers is written first; Apply is one undo step.

Backup retention is OFF by default: nothing is deleted unless the user previews a rule (keep the newest N and / or only those older
than D days), then confirms that exact list. Only backup folders the editor wrote for THIS project (manifest format, project path,
listed files only) are candidates; the newest backup is always kept. Deletion cannot be undone (stated in the preview).
"""
import hashlib
import json
import os
import re
import shutil
import time

T = {}                                          # wb_trackedit globals (wb_te_author.bind forwards them)
RECORD = (b'v', b'vt', b'vn')
IDX_STATEMENTS = (b'l', b'p', b'curv', b'curv2', b'surf')   # would reference indices too; trackbuild refuses them anyway
TOKEN = re.compile(rb'(?<![\S])(\d+)/(\d+)/(\d+)(?![\S])')
BACKUP_NAME = re.compile(r'^(\d{8})_(\d{6})_\d{6}$')


class CompactError(Exception):
    pass


def _kw(raw):
    s = raw.split(b'#', 1)[0].split()
    return s[0] if s else None


def compact_obj(b):
    """OBJ bytes -> (compacted bytes, report). Pure; raises CompactError for a layout it does not handle (nothing changes)."""
    lines = b.splitlines(keepends=True)
    rec = {k: [] for k in RECORD}                   # kind -> [line index]
    faces = []
    for li, raw in enumerate(lines):
        k = _kw(raw)
        if k in rec:
            rec[k].append(li)
        elif k == b'f':
            faces.append(li)
        elif k in IDX_STATEMENTS:
            raise CompactError('line %d: a %r statement references vertices too; compaction handles f lines only' % (li + 1, k.decode()))
    used = {k: set() for k in RECORD}
    parsed = {}
    for li in faces:
        body = lines[li].split(b'#', 1)[0]
        toks = body.split()[1:]
        m = [TOKEN.fullmatch(t) for t in toks]
        if not toks or not all(m):
            raise CompactError('line %d: face corners must all be v/vt/vn with positive indices (trackbuild\'s form)' % (li + 1))
        cs = [tuple(int(x) for x in q.groups()) for q in m]
        for v, t, n in cs:
            if v > len(rec[b'v']) or t > len(rec[b'vt']) or n > len(rec[b'vn']):
                raise CompactError('line %d: index beyond the existing records' % (li + 1))
            used[b'v'].add(v)
            used[b'vt'].add(t)
            used[b'vn'].add(n)
        parsed[li] = cs
    keep, newidx, removed = {}, {}, {}
    for k in RECORD:
        km, nm, r = set(), {}, 0
        for i, li in enumerate(rec[k], 1):
            if i in used[k] or b'#' in lines[li]:       # a commented record is kept (unknown data is never dropped)
                km.add(li)
                nm[i] = len(nm) + 1
            else:
                r += 1
        keep[k], newidx[k], removed[k] = km, nm, r
    drop = {li for k in RECORD for li in rec[k] if li not in keep[k]}
    out = []
    for li, raw in enumerate(lines):
        if li in drop:
            continue
        if li in parsed:
            body, sep, rest = raw.partition(b'#')
            nb = TOKEN.sub(lambda q: b'%d/%d/%d' % (newidx[b'v'][int(q.group(1))], newidx[b'vt'][int(q.group(2))],
                                                    newidx[b'vn'][int(q.group(3))]), body)
            out.append(nb + sep + rest)
        else:
            out.append(raw)
    after = b''.join(out)
    _verify(b, after)
    rep = {'records_before': {k.decode(): len(rec[k]) for k in RECORD},
           'records_removed': {k.decode(): removed[k] for k in RECORD},
           'records_after': {k.decode(): len(rec[k]) - removed[k] for k in RECORD},
           'faces': len(faces), 'bytes_before': len(b), 'bytes_after': len(after),
           'saved_bytes': len(b) - len(after), 'saved_pct': round(100.0 * (len(b) - len(after)) / max(1, len(b)), 1),
           'commented_records_kept': sum(1 for k in RECORD for li in keep[k] if b'#' in lines[li])}
    return after, rep


def _resolve(b):
    """OBJ bytes -> (non-record lines in order, [(face line text without indices, [(v text, vt text, vn text)])])"""
    lines = b.splitlines(keepends=True)
    R = {k: [] for k in RECORD}
    other, faces = [], []
    for raw in lines:
        k = _kw(raw)
        if k in R:
            R[k].append(raw.split(b'#', 1)[0].split()[1:])
    for raw in lines:
        k = _kw(raw)
        if k in R:
            continue
        if k == b'f':
            body, sep, rest = raw.partition(b'#')
            cs = [tuple(int(x) for x in q.groups()) for q in TOKEN.finditer(body)]
            faces.append((TOKEN.sub(b'#', body) + sep + rest, [(tuple(R[b'v'][v - 1]), tuple(R[b'vt'][t - 1]), tuple(R[b'vn'][n - 1]))
                                                              for v, t, n in cs]))
        else:
            other.append(raw)
    return other, faces


def _verify(before, after):
    o0, f0 = _resolve(before)
    o1, f1 = _resolve(after)
    if o0 != o1:
        raise CompactError('internal: a non-record line changed; not applied')
    if f0 != f1:
        bad = next(i for i, (a, c) in enumerate(zip(f0, f1)) if a != c) if len(f0) == len(f1) else min(len(f0), len(f1))
        raise CompactError('internal: face %d resolves to different records after renumbering; not applied' % bad)


def _bk_root(src):
    return os.path.join(src.cfg['state'], 'backups', hashlib.sha256(os.path.normcase(src.project).encode('utf-8')).hexdigest()[:12])


def _write_backup(src, data, reason):
    root = _bk_root(src)
    stamp = time.strftime('%Y%m%d_%H%M%S') + '_%06d' % int((time.time() % 1) * 1e6)
    d = os.path.join(root, stamp)
    os.makedirs(d, exist_ok=False)
    files = {}
    for rel, b in data.items():
        dst = os.path.join(d, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as f:
            f.write(b)
        files[rel] = hashlib.sha256(b).hexdigest()
    with open(os.path.join(d, 'MANIFEST.json'), 'wb') as f:
        f.write(json.dumps({'format': 'workbench-backup 1', 'project': src.project, 'time': stamp, 'reason': reason,
                            'files': files}, indent=1, sort_keys=True).encode('utf-8'))
    return stamp


def _dir_bytes(d):
    n = 0
    for r, _ds, fs in os.walk(d):
        for f in fs:
            try:
                n += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return n


class HealthMixin:
    # ------------------------------------------------------------------ OBJ compaction
    def _compact_plan(self):
        E = T['EditError']
        if self.obj_cur is None:
            raise E('compaction needs a readable OBJ (the input check failed)')
        try:
            after, rep = compact_obj(self.obj_cur)
        except CompactError as e:
            raise E('compaction refused: %s. Nothing changed' % e)
        return after, rep

    def compact_preview(self):
        """explicit OBJ compaction WITHOUT changing anything: the unused v / vt / vn lines and the saving"""
        after, rep = self._compact_plan()
        n = sum(rep['records_removed'].values())
        lines = ['compaction: %d unused record(s) (v %d, vt %d, vn %d) -> %s smaller (%.1f %%); %d faces renumbered, every other line '
                 'unchanged' % (n, rep['records_removed']['v'], rep['records_removed']['vt'], rep['records_removed']['vn'],
                                _size(rep['saved_bytes']), rep['saved_pct'], rep['faces'])]
        if not n:
            lines = ['compaction: nothing to remove (every v / vt / vn line is used)']
        return dict(rep, ok=True, nothing_to_do=not n, preview_key=self._cons_key('compact', {}),
                    note='preview only: nothing changed. Apply backs up the editor buffers first, then verifies equivalence with the '
                         'kit dry run (identical per-unit streamed blocks) and is one undo step; Save writes it.',
                    summary_lines=lines)

    def compact(self, preview_key=None):
        E = T['EditError']
        if preview_key != self._cons_key('compact', {}):
            raise E('NEEDS PREVIEW: preview the compaction first and apply it with its preview_key')
        before = self.obj_cur
        after, rep = self._compact_plan()
        if after == before:
            raise E('nothing to compact: every v / vt / vn line is used')
        try:
            r0 = self.regenerate(before)
        except E as e:
            raise E('compaction refused: the kit cannot build the current geometry, so equivalence cannot be proven (%s). Fix that '
                    'first. Nothing changed' % e)
        r1 = self.regenerate(after)
        h0 = [u['blocks_sha256'] for u in r0['units']]
        h1 = [u['blocks_sha256'] for u in r1['units']]
        if h0 != h1:
            raise E('compaction refused: the kit dry run differs after renumbering (units %s); not applied' %
                    [i for i, (a, b) in enumerate(zip(h0, h1)) if a != b][:8])
        if self.constructs(before) != self.constructs(after):
            raise E('internal: construction blocks differ after compaction; not applied')
        data = {self.desc_rel: self.cur}
        if self.obj_rel:
            data[self.obj_rel] = before
        stamp = _write_backup(self, data, 'before compaction (editor buffers)')
        label = 'compact OBJ (-%d records, -%s)' % (sum(rep['records_removed'].values()), _size(rep['saved_bytes']))
        self._push('obj', label, after, kind='compact', index=None)
        return dict(rep, ok=True, label=label, backup=stamp,
                    equivalence={'face_corners': 'identical v / vt / vn text for all %d faces' % rep['faces'],
                                 'other_lines': 'byte-identical', 'kit_units': '%d / %d streamed unit blocks identical (sha256)' % (
                                     len(h1), len(h0)), 'construction_blocks': 'identical'},
                    summary_lines=[label, 'backup %s written first; equivalence: faces, other lines, %d kit unit blocks identical' % (
                        stamp, len(h1)), 'Save writes the compacted OBJ (one undo step until then)'])

    # ------------------------------------------------------------------ backup retention (optional, never automatic)
    def _prune_candidates(self, keep_last, older_than_days):
        E = T['EditError']
        if keep_last is None and older_than_days is None:
            raise E('backup retention needs a rule: keep_last (>= 1) and / or older_than_days (> 0). Nothing is deleted by default')
        if keep_last is not None and not (isinstance(keep_last, int) and not isinstance(keep_last, bool) and 1 <= keep_last <= 10000):
            raise E('keep_last: a whole number 1..10000 (the newest backups kept)')
        if older_than_days is not None and not (isinstance(older_than_days, (int, float)) and not isinstance(older_than_days, bool)
                                                and 0 < older_than_days <= 36500):
            raise E('older_than_days: a number of days > 0')
        root = _bk_root(self)
        rows, skipped = [], []
        if os.path.isdir(root):
            for n in sorted(os.listdir(root), reverse=True):        # newest first (names are timestamps)
                d = os.path.join(root, n)
                m_ = BACKUP_NAME.match(n)
                if not (m_ and os.path.isdir(d)):
                    continue
                try:
                    m = json.load(open(os.path.join(d, 'MANIFEST.json'), encoding='utf-8'))
                except (OSError, ValueError):
                    skipped.append({'name': n, 'why': 'no readable manifest: kept'})
                    continue
                if m.get('format') != 'workbench-backup 1' or os.path.normcase(str(m.get('project'))) != os.path.normcase(self.project):
                    skipped.append({'name': n, 'why': 'not an editor backup of this project: kept'})
                    continue
                listed = {os.path.normcase(os.path.join(d, *r.split('/'))) for r in m.get('files', {})} | \
                    {os.path.normcase(os.path.join(d, 'MANIFEST.json'))}
                extra = [os.path.join(r, f) for r, _ds, fs in os.walk(d) for f in fs if os.path.normcase(os.path.join(r, f)) not in listed]
                if extra:
                    skipped.append({'name': n, 'why': 'holds files the editor did not write (%d): kept' % len(extra)})
                    continue
                t = time.mktime(time.strptime(m_.group(1) + m_.group(2), '%Y%m%d%H%M%S'))
                rows.append({'name': n, 'reason': m.get('reason'), 'age_days': round((time.time() - t) / 86400.0, 2),
                             'bytes': _dir_bytes(d)})
        dele = []
        for i, r in enumerate(rows):
            if i == 0:
                continue                                            # the newest is always kept
            if keep_last is not None and i < keep_last:
                continue
            if older_than_days is not None and r['age_days'] <= older_than_days:
                continue
            dele.append(r)
        return root, rows, dele, skipped

    def backup_prune_preview(self, keep_last=None, older_than_days=None, confirm=None):  # confirm: ignored here (the page sends the form)
        """optional backup retention WITHOUT deleting anything: which backups the rule would delete"""
        root, rows, dele, skipped = self._prune_candidates(keep_last, older_than_days)
        key = self._cons_key('prune', {'k': keep_last, 'd': older_than_days, 'n': [r['name'] for r in dele]})
        return {'ok': True, 'folder': root, 'backups': len(rows), 'delete': dele, 'keep': len(rows) - len(dele), 'skipped': skipped,
                'frees_bytes': sum(r['bytes'] for r in dele), 'preview_key': key,
                'note': 'preview only: nothing deleted. Apply needs confirm = true and deletes exactly this list; it CANNOT be undone. '
                        'The newest backup is always kept; folders the editor did not write are never touched.',
                'summary_lines': ['backup retention: %d of %d backup(s) would be deleted (%s), %d kept, %d skipped' % (
                    len(dele), len(rows), _size(sum(r['bytes'] for r in dele)), len(rows) - len(dele), len(skipped))] +
                ['  delete %s (%.1f days, %s)' % (r['name'], r['age_days'], r['reason']) for r in dele[:30]]}

    def backup_prune(self, keep_last=None, older_than_days=None, preview_key=None, confirm=False):
        E = T['EditError']
        root, rows, dele, skipped = self._prune_candidates(keep_last, older_than_days)
        key = self._cons_key('prune', {'k': keep_last, 'd': older_than_days, 'n': [r['name'] for r in dele]})
        if preview_key != key:
            raise E('NEEDS PREVIEW: preview the retention rule first (the list changed or was not previewed); nothing deleted')
        if confirm is not True:
            raise E('backup deletion needs confirm = true (it cannot be undone); nothing deleted')
        done = []
        for r in dele:
            d = os.path.join(root, r['name'])
            if os.path.dirname(os.path.normcase(os.path.abspath(d))) != os.path.normcase(os.path.abspath(root)):
                raise E('internal: %s is outside the backup folder; stopped' % d)
            shutil.rmtree(d)
            done.append(r['name'])
        with open(os.path.join(root, 'RETENTION_LOG.jsonl'), 'ab') as f:
            f.write((json.dumps({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'keep_last': keep_last,
                                 'older_than_days': older_than_days, 'deleted': done}) + '\n').encode('utf-8'))
        return {'ok': True, 'deleted': done, 'kept': len(rows) - len(done), 'log': os.path.join(root, 'RETENTION_LOG.jsonl'),
                'summary_lines': ['deleted %d backup(s); %d kept; logged in RETENTION_LOG.jsonl' % (len(done), len(rows) - len(done))]}

    HEALTH_LAYOUT = {'compact_preview': 'compact_preview', 'compact': 'compact',
                     'backup_prune_preview': 'backup_prune_preview', 'backup_prune': 'backup_prune'}


def _size(n):
    return '%.1f MB' % (n / 1048576.0) if n >= 1048576 else '%.1f KB' % (n / 1024.0)
