"""wbn_toml - byte-preserving edits of a mod.toml's [bmashup.tune] table (Workbench 0.30 developer workflow).

The editor never re-serialises a file. It scans the text once (a small TOML lexer: tables, keys, strings, arrays, comments),
records where every value and every array element starts and ends, and an edit replaces exactly one span (an element's
number, a version number) or inserts one element / one line. Everything else - comments, unknown keys and tables, blank lines,
key order, quoting, line endings, a UTF-8 BOM - stays byte for byte. Every edited text is parsed again with tomllib before it
may be saved; a text that would not parse is refused.

API (pure functions on text): parse(text) -> Doc; tune_entries(doc) / tune_sliders(doc); set_value(text, key, value_text);
remove_value(text, key); set_version(text, n); set_slider(text, row, line); remove_slider(text, row); diff(old, new);
save(path, new_text, expect_sha256) (atomic; the previous file is kept in .wbn\\history\\).
"""
import datetime
import difflib
import hashlib
import json
import os
import re
import tomllib


class TomlScanError(ValueError):
    def __init__(self, msg, pos, text):
        line = text.count('\n', 0, pos) + 1
        col = pos - (text.rfind('\n', 0, pos) + 1) + 1
        super().__init__('%s (line %d, column %d)' % (msg, line, col))
        self.line, self.col = line, col


class Entry:
    """one key = value; for arrays: elems = [(start, end, decoded string or None)], close = index of ']'"""

    def __init__(self, table, key, ks, vs, ve):
        self.table, self.key, self.ks, self.vs, self.ve = table, key, ks, vs, ve
        self.elems, self.close = [], None

    @property
    def full(self):
        return (self.table + '.' if self.table else '') + self.key


class Doc:
    def __init__(self, text):
        self.text = text
        self.entries = []
        self.tables = []          # (name, header_start, header_line_end)

    def find(self, full):
        for e in self.entries:
            if e.full == full:
                return e
        return None

    def line_of(self, pos):
        return self.text.count('\n', 0, pos) + 1


_WS = ' \t'


def _skip_ws(t, p, nl=False):
    while p < len(t) and (t[p] in _WS or (nl and t[p] in '\r\n')):
        p += 1
    return p


def _skip_comment(t, p):
    if p < len(t) and t[p] == '#':
        while p < len(t) and t[p] not in '\r\n':
            p += 1
    return p


def _string_end(t, p):
    """p at the opening quote -> index after the closing quote"""
    for q in ('"""', "'''"):
        if t.startswith(q, p):
            i = p + 3
            while True:
                j = t.find(q, i)
                if j < 0:
                    raise TomlScanError('unterminated multi-line string', p, t)
                if q == '"""' and _escaped(t, j):
                    i = j + 1
                    continue
                k = j + 3
                while k < len(t) and t[k] == q[0] and k - j < 5:     # up to two extra quotes belong to the string
                    k += 1
                return k
    q = t[p]
    i = p + 1
    while i < len(t):
        c = t[i]
        if c in '\r\n':
            break
        if q == '"' and c == '\\':
            i += 2
            continue
        if c == q:
            return i + 1
        i += 1
    raise TomlScanError('unterminated string', p, t)


def _escaped(t, j):
    n = 0
    while j - 1 - n >= 0 and t[j - 1 - n] == '\\':
        n += 1
    return n % 2 == 1


def _decode(raw):
    if raw.startswith('"') and not raw.startswith('"""'):
        try:
            return json.loads(raw)
        except ValueError:
            return None
    if raw.startswith("'") and not raw.startswith("'''"):
        return raw[1:-1]
    return None


def _value_end(t, p, entry=None):
    if p >= len(t):
        raise TomlScanError('a value is missing', p, t)
    c = t[p]
    if c in '"\'':
        return _string_end(t, p)
    if c == '[':
        i = p + 1
        while True:
            i = _skip_ws(t, i, nl=True)
            i = _skip_comment(t, i)
            if i < len(t) and t[i] in '\r\n':
                continue
            if i >= len(t):
                raise TomlScanError('unterminated array', p, t)
            if t[i] == ']':
                if entry is not None:
                    entry.close = i
                return i + 1
            if t[i] == ',':
                raise TomlScanError('an array element is missing', i, t)
            s = i
            i = _value_end(t, i)
            if entry is not None:
                entry.elems.append((s, i, _decode(t[s:i])))
            i = _skip_ws(t, i, nl=True)
            while i < len(t) and t[i] == '#':
                i = _skip_ws(t, _skip_comment(t, i), nl=True)
            if i < len(t) and t[i] == ',':
                i += 1
            elif i < len(t) and t[i] != ']':
                raise TomlScanError('expected "," or "]" in an array', i, t)
    if c == '{':
        i, depth = p, 0
        while i < len(t):
            if t[i] in '"\'':
                i = _string_end(t, i)
                continue
            if t[i] == '{':
                depth += 1
            elif t[i] == '}':
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise TomlScanError('unterminated inline table', p, t)
    i = p
    while i < len(t) and t[i] not in ' \t\r\n,]}#':
        i += 1
    if i == p:
        raise TomlScanError('a value is missing', p, t)
    return i


def _key_text(raw):
    parts, cur, i = [], '', 0
    while i < len(raw):
        c = raw[i]
        if c in '"\'':
            e = raw.find(c, i + 1)
            cur += raw[i + 1:e]
            i = e + 1
            continue
        if c == '.':
            parts.append(cur.strip())
            cur = ''
        else:
            cur += c
        i += 1
    parts.append(cur.strip())
    return '.'.join(x for x in parts)


def parse(text):
    """-> Doc (raises TomlScanError with line / column)"""
    d = Doc(text)
    t, p, table = text, 0, ''
    if t.startswith('﻿'):
        p = 1
    while p < len(t):
        p = _skip_ws(t, p, nl=True)
        if p >= len(t):
            break
        c = t[p]
        if c == '#':
            p = _skip_comment(t, p)
            continue
        if c == '[':
            arr = t.startswith('[[', p)
            e = t.find(']]' if arr else ']', p)
            nl = min([x for x in (t.find('\n', p), len(t)) if x >= 0])
            if e < 0 or e > nl:
                raise TomlScanError('a table header is not closed on its line', p, t)
            table = _key_text(t[p + (2 if arr else 1):e])
            le = t.find('\n', e)
            d.tables.append((table, p, len(t) if le < 0 else le + 1))
            p = e + (2 if arr else 1)
            p = _skip_comment(t, _skip_ws(t, p))
            continue
        ks = p
        eq = p
        while eq < len(t) and t[eq] not in '=\r\n':
            if t[eq] in '"\'':
                eq = _string_end(t, eq)
                continue
            eq += 1
        if eq >= len(t) or t[eq] != '=':
            raise TomlScanError('expected "key = value"', p, t)
        key = _key_text(t[ks:eq])
        vs = _skip_ws(t, eq + 1)
        en = Entry(table, key, ks, vs, None)
        en.ve = _value_end(t, vs, en)
        d.entries.append(en)
        p = _skip_comment(t, _skip_ws(t, en.ve))
        if p < len(t) and t[p] not in '\r\n':
            raise TomlScanError('unexpected text after a value', p, t)
    return d


# ------------------------------------------------------------------------------------------------ tune view
def split_set(s):
    """'Group | Name = 1.5' -> (key, value text) like the host (last '='), or None"""
    if not isinstance(s, str) or '=' not in s:
        return None
    k, v = s.rsplit('=', 1)
    return k.strip(), v.strip()


def slider_row(s):
    """the row of a slider line ('ROW = DEF : MIN .. MAX [step S] [label T]'), host order: label cut first, then the last '='"""
    if not isinstance(s, str):
        return None
    line = s.split(' label ', 1)[0]
    if '=' not in line:
        return None
    return line.rsplit('=', 1)[0].strip()


def tune_entries(doc):
    e = doc.find('bmashup.tune.set')
    out = []
    for i, (s, en, v) in enumerate(e.elems if e else []):
        kv = split_set(v)
        out.append({'index': i, 'start': s, 'end': en, 'line': doc.line_of(s), 'raw': doc.text[s:en], 'text': v,
                    'key': kv[0] if kv else None, 'value': kv[1] if kv else None})
    return out


def tune_sliders(doc):
    e = doc.find('bmashup.tune.sliders')
    return [{'index': i, 'start': s, 'end': en, 'line': doc.line_of(s), 'raw': doc.text[s:en], 'text': v, 'row': slider_row(v)}
            for i, (s, en, v) in enumerate(e.elems if e else [])]


def _nl(text):
    return '\r\n' if '\r\n' in text else '\n'


def _quote(s):
    return json.dumps(s, ensure_ascii=False)


def _line_start(t, p):
    return t.rfind('\n', 0, p) + 1


def _indent_at(t, p):
    ls = _line_start(t, p)
    i = ls
    while i < len(t) and t[i] in _WS:
        i += 1
    return t[ls:i]


def _insert_elem(text, e, s):
    """add the string s as a new last element of array entry e"""
    t, nl = text, _nl(text)
    if not e.elems:
        inner = t[e.vs + 1:e.close]
        if '\n' in inner:
            return t[:e.vs + 1] + nl + '    ' + _quote(s) + ',' + t[e.vs + 1:]
        return t[:e.vs + 1] + _quote(s) + t[e.vs + 1:]
    multiline = '\n' in t[e.vs:e.close]
    ls, le, _ = e.elems[-1]
    after = _skip_ws(t, le)
    if multiline:
        ind = _indent_at(t, ls)
        if after < len(t) and t[after] == ',':
            return t[:after + 1] + nl + ind + _quote(s) + ',' + t[after + 1:]
        return t[:le] + ',' + nl + ind + _quote(s) + t[le:]
    if after < len(t) and t[after] == ',':
        return t[:after + 1] + ' ' + _quote(s) + ',' + t[after + 1:]
    return t[:le] + ', ' + _quote(s) + t[le:]


def _remove_elem(text, e, k):
    t = text
    s, en, _ = e.elems[k]
    a = _skip_ws(t, en)
    if a < len(t) and t[a] == ',':
        en = a + 1
    elif k > 0:                                     # the last element without a trailing comma: take the comma before it
        prev_end = e.elems[k - 1][1]
        c = t.find(',', prev_end, s)
        if c >= 0:
            s = c
    ls = _line_start(t, s)
    le = t.find('\n', en)
    rest = t[en:le if le >= 0 else len(t)]
    if t[ls:s].strip() == '' and rest.strip() == '' and le >= 0:     # the element had its own line: drop the line
        return t[:ls] + t[le + 1:]
    if t[en - 1] == ',':                            # inline: 'a, b' -> drop the element, its comma and the space after it
        en = _skip_ws(t, en)
    return t[:s] + t[en:]


def _tune_table(doc):
    for name, hs, he in doc.tables:
        if name == 'bmashup.tune':
            return hs, he
    return None


def _ensure_key(text, key, value_src):
    """add 'key = value' to [bmashup.tune] (after its version line, else after the header); a new table at the end if none"""
    d = parse(text)
    nl = _nl(text)
    tb = _tune_table(d)
    if tb is None:
        if d.find('bmashup.tune.version') or d.find('bmashup.tune.set') or d.find('bmashup.tune.sliders'):
            raise ValueError('[bmashup.tune] is written with dotted keys or an inline table here: edit that file by hand')
        sep = '' if text.endswith(('\n',)) or not text else nl
        add = '%s%s[bmashup.tune]%sversion = 1%s' % (sep, nl if text.strip() else '', nl, nl)
        text = text + add
        d = parse(text)
        tb = _tune_table(d)
    ver = d.find('bmashup.tune.version')
    if ver is not None:
        le = text.find('\n', ver.ve)
        pos = len(text) if le < 0 else le + 1
    else:
        pos = tb[1]
    line = '%s = %s%s' % (key, value_src, nl)
    if pos == len(text) and text and not text.endswith('\n'):
        line = nl + line
    return text[:pos] + line + text[pos:]


def set_value(text, key, value_text):
    """set 'key = value' in [bmashup.tune] set = [...]: changes only the number of an existing element; else appends one"""
    d = parse(text)
    for en in tune_entries(d):
        if en['key'] == key:
            raw, cur = en['raw'], en['text']
            i = cur.rfind('=')
            tail = cur[i + 1:]
            lead = tail[:len(tail) - len(tail.lstrip())]
            trail = tail[len(tail.rstrip()):]
            new = cur[:i + 1] + lead + value_text + trail             # the spacing around '=' stays as written
            if raw[1:-1] == cur and raw[0] in '"\'' and '\\' not in new and raw[0] not in new:
                newraw = raw[0] + new + raw[0]
            else:
                newraw = _quote(new)
            return text[:en['start']] + newraw + text[en['end']:]
    e = d.find('bmashup.tune.set')
    s = '%s = %s' % (key, value_text)
    if e is None:
        return _ensure_key(text, 'set', '[%s]' % _quote(s))
    if e.close is None:
        raise ValueError('bmashup.tune.set is not an array')
    return _insert_elem(text, e, s)


def remove_value(text, key):
    d = parse(text)
    e = d.find('bmashup.tune.set')
    for en in tune_entries(d):
        if en['key'] == key:
            return _remove_elem(text, e, en['index'])
    return text


def set_version(text, n):
    d = parse(text)
    e = d.find('bmashup.tune.version')
    if e is None:
        return _ensure_key(text, 'version', str(int(n))) if _tune_table(d) else text
    return text[:e.vs] + str(int(n)) + text[e.ve:]


def set_slider(text, row, line):
    d = parse(text)
    e = d.find('bmashup.tune.sliders')
    for sl in tune_sliders(d):
        if sl['row'] == row:
            return text[:sl['start']] + _quote(line) + text[sl['end']:]
    if e is None:
        return _ensure_key(text, 'sliders', '[%s]' % _quote(line))
    return _insert_elem(text, e, line)


def remove_slider(text, row):
    d = parse(text)
    e = d.find('bmashup.tune.sliders')
    for sl in tune_sliders(d):
        if sl['row'] == row:
            return _remove_elem(text, e, sl['index'])
    return text


# ------------------------------------------------------------------------------------------------ preview / save
def check_parses(text):
    """-> None or the tomllib error with its line"""
    try:
        tomllib.loads(text.lstrip('﻿'))
        return None
    except tomllib.TOMLDecodeError as e:
        return str(e)


def diff(old, new, name='mod.toml'):
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), 'before/' + name, 'after/' + name, n=1))


def read(path):
    """-> (text, sha256 of the bytes); keeps \\r\\n and a BOM exactly (newline='')"""
    with open(path, 'rb') as f:
        b = f.read()
    return b.decode('utf-8'), hashlib.sha256(b).hexdigest()


def save(path, new_text, expect_sha256):
    """atomic replace; refused when the file changed since it was read or the new text does not parse. The previous bytes go
    to <project>\\.wbn\\history\\<time>_mod.toml. -> (ok, message)"""
    bad = check_parses(new_text)
    if bad:
        return False, 'not saved: the edited text would not parse (%s)' % bad
    with open(path, 'rb') as f:
        cur = f.read()
    if hashlib.sha256(cur).hexdigest() != expect_sha256:
        return False, 'not saved: %s changed on disk since it was opened (reload it first)' % path
    hist = os.path.join(os.path.dirname(path), '.wbn', 'history')
    os.makedirs(hist, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    with open(os.path.join(hist, '%s_%s' % (stamp, os.path.basename(path))), 'wb') as f:
        f.write(cur)
    tmp = path + '.wbn_tmp'
    with open(tmp, 'wb') as f:
        f.write(new_text.encode('utf-8'))
    os.replace(tmp, path)
    return True, 'saved %s (previous version kept in %s)' % (path, hist)


def tune_version(doc):
    e = doc.find('bmashup.tune.version')
    if not e:
        return None
    try:
        return int(doc.text[e.vs:e.ve])
    except ValueError:
        return None


NUM = re.compile(r'^-?[0-9]+(\.[0-9]+)?$')
