"""bm_rewrite.py - rewrite the Mashup's OWN inserted mark text into calls of our accessor macros (include/bm_gen_access.h).

Our insert lines (um layer marks) are written in the recompiler's notation: `R = MEM32(a);`, `MEM32(a) = v;`, `PUSH32(esp, v);`,
`g_ebp = ebp;` ... - the statement shapes of the generated code. This module rewrites each such shape into one of our macros whose
expansion is the IDENTICAL token sequence (no added parentheses, no reordering), so the preprocessed translation unit is
token-identical and every line keeps its line number (one input line -> one output line, never joined or split).

Input = our insert lines only (never generated text). Pure functions; no I/O.

Rules (token level; comments / strings / whitespace kept verbatim; preprocessor lines untouched):
  R1 store    MEMw ( A ) = V ;                                -> BM_STw ( A , V ) ;        (w = 8 16 32 F)
  R2 load     <stmt> R = MEMw ( A ) ;                         -> BM_LDw ( R , A ) ;        (R = identifier or xmmN.f[k])
  R3 read     MEMw ( A )   (any other use)                    -> BM_RDw ( A )
  R4 call     PUSH32 ( esp , V ) ; RECOMP_ABI_CALL ( A , F )  -> BM_GUEST_CALL ( V , A , F )
  R5 push     PUSH32 ( esp , V )                              -> BM_PUSH ( V )
  R6 frame    <stmt> g_ebp = ebp                              -> BM_FRAME_EBP ( )
              <stmt> g_seh_ebp = ebp                          -> BM_FRAME_SEH ( )
  R7 return   <stmt> esp += N ; return                        -> BM_GUEST_RET ( N )
  R8 esp add  <stmt> esp = esp + N                            -> BM_ESP_ADD ( N )
  R9 compare  <stmt> _fa = ( uint32_t ) ( X ) & 0xFFFFFFFFu ; _fb = ( uint32_t ) ( Y ) & 0xFFFFFFFFu
                                                              -> BM_CMP32 ( X , Y )
<stmt> = a statement start: line start, after ; { } or after the ) closing an if / while / for header.
"""
import re

MEMW = {"MEM8": "8", "MEM16": "16", "MEM32": "32", "MEMF": "F"}
NUM = re.compile(r"[0-9]+u?|0x[0-9A-Fa-f]+u?")
IDENT = re.compile(r"[A-Za-z_]\w*")
_TOK = re.compile(r"""(?P<ws>[ \t]+)|(?P<cm>/\*.*?\*/|//.*$)|(?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|"""
                  r"""(?P<num>\.?[0-9](?:[eEpP][+-]|[0-9A-Za-z_.])*)|(?P<id>[A-Za-z_]\w*)|"""
                  r"""(?P<op><<=|>>=|\+\+|--|->|<<|>>|<=|>=|==|!=|&&|\|\||[-+*/%&|^]=|.)""", re.S)


class RewriteError(Exception):
    pass


def tokenize(s):
    out, pos = [], 0
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m:
            raise RewriteError("untokenizable text")
        out.append((m.lastgroup, m.group(0)))
        pos = m.end()
    return out


class _Line:
    def __init__(self, body):
        self.t = tokenize(body)
        self.s = [i for i, t in enumerate(self.t) if t[0] not in ("ws", "cm")]
        self.v = [self.t[i][1] for i in self.s]
        self.hdr = set()
        for j, x in enumerate(self.v):
            if x in ("if", "while", "for") and j + 1 < len(self.v) and self.v[j + 1] == "(":
                self.hdr.add(self.close(j + 1))

    def at(self, j):
        return self.v[j] if 0 <= j < len(self.v) else None

    def close(self, k):
        """sig index of the ')' matching the '(' at k"""
        d = 0
        for j in range(k, len(self.v)):
            if self.v[j] == "(":
                d += 1
            elif self.v[j] == ")":
                d -= 1
                if d == 0:
                    return j
        raise RewriteError("unbalanced parentheses")

    def top(self, a, b, sep):
        d, out = 0, []
        for j in range(a, b):
            x = self.v[j]
            if x in ("(", "[", "{"):
                d += 1
            elif x in (")", "]", "}"):
                d -= 1
            elif x == sep and d == 0:
                out.append(j)
        return out

    def gap(self, p, q):
        """source text between sig tokens p and q (whitespace / comments)"""
        return "".join(t[1] for t in self.t[self.s[p] + 1:self.s[q]])

    def stmt(self, j):
        if j == 0:
            return True
        p = self.v[j - 1]
        return p in (";", "{", "}") or (p == ")" and (j - 1) in self.hdr)


def _rw(L, a, b, rules):
    out, j = [], a
    while j < b:
        r = _construct(L, j, b, rules)
        if r is None:
            piece, end = L.v[j], j + 1
        else:
            piece, end = r
        out.append(piece)
        if end < b:
            out.append(L.gap(end - 1, end))
        j = end
    return "".join(out)


def _construct(L, j, b, rules):
    v, x, st = L.v, L.v[j], L.stmt(j)
    # R9
    if st and x == "_fa" and v[j + 1:j + 6] == ["=", "(", "uint32_t", ")", "("]:
        c1 = L.close(j + 5)
        if v[c1 + 1:c1 + 10] == ["&", "0xFFFFFFFFu", ";", "_fb", "=", "(", "uint32_t", ")", "("]:
            c2 = L.close(c1 + 9)
            if v[c2 + 1:c2 + 3] == ["&", "0xFFFFFFFFu"] and c2 + 3 <= b:
                X, Y = _rw(L, j + 6, c1, rules), _rw(L, c1 + 10, c2, rules)
                rules.append("R9")
                return "BM_CMP32(%s, %s)" % (X, Y), c2 + 3
    # R7
    if st and x == "esp" and L.at(j + 1) == "+=" and L.at(j + 2) and NUM.fullmatch(L.at(j + 2)) and \
            L.at(j + 3) == ";" and L.at(j + 4) == "return" and j + 5 <= b:
        rules.append("R7")
        return "BM_GUEST_RET(%s)" % v[j + 2], j + 5
    # R8
    if st and x == "esp" and v[j + 1:j + 4] == ["=", "esp", "+"] and L.at(j + 4) and NUM.fullmatch(L.at(j + 4)) and \
            L.at(j + 5) == ";" and j + 5 <= b:
        rules.append("R8")
        return "BM_ESP_ADD(%s)" % v[j + 4], j + 5
    # R6
    if st and x in ("g_ebp", "g_seh_ebp") and v[j + 1:j + 4] == ["=", "ebp", ";"] and j + 3 <= b:
        rules.append("R6")
        return ("BM_FRAME_EBP()" if x == "g_ebp" else "BM_FRAME_SEH()"), j + 3
    # R4 / R5
    if x == "PUSH32" and v[j + 1:j + 4] == ["(", "esp", ","]:
        c = L.close(j + 1)
        if c + 1 <= b:
            V = _rw(L, j + 4, c, rules).strip()
            if v[c + 1:c + 4] == [";", "RECOMP_ABI_CALL", "("]:
                c2 = L.close(c + 3)
                cm = L.top(c + 4, c2, ",")
                if len(cm) == 1 and c2 + 1 <= b:
                    A = _rw(L, c + 4, cm[0], rules).strip()
                    F = _rw(L, cm[0] + 1, c2, rules).strip()
                    rules.append("R4")
                    return "BM_GUEST_CALL(%s, %s, %s)" % (V, A, F), c2 + 1
            rules.append("R5")
            return "BM_PUSH(%s)" % V, c + 1
    # R2
    if st and IDENT.fullmatch(x) and x not in MEMW:
        lv = j + 1
        if re.fullmatch(r"xmm[0-9]+", x) and v[j + 1:j + 4] == [".", "f", "["] and L.at(j + 5) == "]":
            lv = j + 6
        if L.at(lv) == "=" and L.at(lv + 1) in MEMW and L.at(lv + 2) == "(":
            c = L.close(lv + 2)
            if L.at(c + 1) == ";" and c + 1 <= b:
                R = "".join(v[k] if k == lv - 1 else v[k] + L.gap(k, k + 1) for k in range(j, lv))
                A = _rw(L, lv + 3, c, rules)
                rules.append("R2")
                return "BM_LD%s(%s, %s)" % (MEMW[v[lv + 1]], R, A), c + 1
    # R1 / R3
    if x in MEMW and L.at(j + 1) == "(":
        c = L.close(j + 1)
        w = MEMW[x]
        if L.at(c + 1) == "=":
            semis = L.top(c + 2, len(v), ";")
            if not semis or semis[0] >= b:
                raise RewriteError("store without a terminating ;")
            A = _rw(L, j + 2, c, rules)
            V = _rw(L, c + 2, semis[0], rules).strip()
            rules.append("R1")
            return "BM_ST%s(%s, %s)" % (w, A, V), semis[0]
        if c + 1 <= b:
            A = _rw(L, j + 2, c, rules)
            rules.append("R3")
            return "BM_RD%s(%s)" % (w, A), c + 1
    return None


def rewrite_line(line):
    """-> (new_line, [rules]). EOL kept. Preprocessor lines / lines without code are returned unchanged (rules [])."""
    body = line.rstrip("\r\n")
    eol = line[len(body):]
    if body.lstrip().startswith("#"):
        return line, []
    L = _Line(body)
    if not L.v:
        return line, []
    rules = []
    mid = _rw(L, 0, len(L.v), rules)
    if not rules:
        return line, []
    lead = "".join(t[1] for t in L.t[:L.s[0]])
    tail = "".join(t[1] for t in L.t[L.s[-1] + 1:])
    return lead + mid + tail + eol, rules


# ---- token equivalence of one line (a cheap self-check; the real proof is clang -E of the whole translation unit) --------
MACROS = {
    # name: (params, replacement tokens as text) - MUST equal include/bm_gen_access.h (checked by anchors.py selftest)
    "BM_RD8": (["a"], "MEM8(a)"), "BM_RD16": (["a"], "MEM16(a)"), "BM_RD32": (["a"], "MEM32(a)"), "BM_RDF": (["a"], "MEMF(a)"),
    "BM_LD8": (["r", "a"], "r = MEM8(a)"), "BM_LD16": (["r", "a"], "r = MEM16(a)"), "BM_LD32": (["r", "a"], "r = MEM32(a)"),
    "BM_LDF": (["r", "a"], "r = MEMF(a)"),
    "BM_ST8": (["a", "v"], "MEM8(a) = v"), "BM_ST16": (["a", "v"], "MEM16(a) = v"), "BM_ST32": (["a", "v"], "MEM32(a) = v"),
    "BM_STF": (["a", "v"], "MEMF(a) = v"),
    "BM_PUSH": (["v"], "PUSH32(esp, v)"),
    "BM_GUEST_CALL": (["r", "a", "f"], "PUSH32(esp, r); RECOMP_ABI_CALL(a, f)"),
    "BM_GUEST_RET": (["n"], "esp += n; return"),
    "BM_ESP_ADD": (["n"], "esp = esp + n"),
    "BM_FRAME_EBP": ([], "g_ebp = ebp"), "BM_FRAME_SEH": ([], "g_seh_ebp = ebp"),
    "BM_CMP32": (["x", "y"], "_fa = (uint32_t)(x) & 0xFFFFFFFFu; _fb = (uint32_t)(y) & 0xFFFFFFFFu"),
}


def sigtoks(s):
    return [t[1] for t in tokenize(s) if t[0] not in ("ws", "cm")]


def expand(toks):
    """expand our BM_ macros (function-like, recursively) in a significant-token list"""
    out, i = [], 0
    while i < len(toks):
        x = toks[i]
        if x in MACROS and i + 1 < len(toks) and toks[i + 1] == "(":
            d, j, args, cur = 0, i + 1, [], []
            while True:
                y = toks[j]
                if y == "(":
                    d += 1
                    if d > 1:
                        cur.append(y)
                elif y == ")":
                    d -= 1
                    if d == 0:
                        break
                    cur.append(y)
                elif y == "," and d == 1:
                    args.append(cur)
                    cur = []
                else:
                    cur.append(y)
                j += 1
            if cur or args:
                args.append(cur)
            params, rep = MACROS[x]
            if len(args) != len(params):
                raise RewriteError("macro %s: %d args" % (x, len(args)))
            env = {p: expand(a) for p, a in zip(params, args)}
            for t in sigtoks(rep):
                out.extend(env.get(t, [t]))
            i = j + 1
        else:
            out.append(x)
            i += 1
    return out


def line_equivalent(old, new):
    return sigtoks(old.rstrip("\r\n")) == expand(sigtoks(new.rstrip("\r\n")))
