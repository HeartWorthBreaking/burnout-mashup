"""anchors.py - "bm-anchors 1": the Mashup's generated-code hook marks as ADDRESS ANCHOR + HASHES + OUR insertion text.

The file carries no generated text: each mark is located in the user's locally generated file by the guest address of the
nearest unique label (`loc_%08X: ;`) or function head (`void sub_%08X(void)`), regenerated from the number, or (for the
toolkit header recomp_types.h) by the sha256 of a unique line; then an offset, the sha256 of the generated span between the
landmark and the mark, the sha256 of the two neighbour lines and of every generated line the mark deletes. Only the inserted
text (ours) is stored as text. Every generated file's pristine and result sha256 are pinned.

    py -3 -B anchors.py emit --form macro|original --out FILE [--keep-file JSON]   # from upstream_maint layers\\gen_marks.json
    py -3 -B anchors.py apply --anchors FILE --pristine GEN_DIR --out NEW_DIR [--structural]
    py -3 -B anchors.py check --anchors FILE --pristine GEN_DIR [--structural]    # apply without writing
    py -3 -B anchors.py selftest                                                   # header == rewrite table, line equivalence

apply = exact-anchor refusal: a missing or ambiguous (duplicate) landmark, a landmark hash that does not match its number, a
changed span, a deleted-line hash or a neighbour-line hash that differs, overlapping marks, a pristine file that is not the pinned
one, or a result that is not the pinned result -> REFUSED (exit 2), nothing is written. Marks are never relocated approximately.
--structural (a regenerated pristine of another revision) skips only the whole-file pristine / result pins; every per-mark check
stays. Exit 0 ok, 2 refused, 1 usage.

Forms: "macro" = our insert lines rewritten into include/bm_gen_access.h calls (bm_rewrite.py; token-identical expansion);
"original" = the insert lines exactly as in the accepted tree (LOCAL proof input: some lines repeat generated statement shapes).
This is a representation of our changes; it does not decide any copyright question (Q7 / Q8 stay open).
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARKS = os.path.normpath(os.path.join(HERE, ".."))
GP = os.path.normpath(os.path.join(MARKS, "..", ".."))
UM_DIR = os.path.join(GP, "upstream_maint")
sys.path.insert(0, HERE)
import bm_rewrite  # noqa: E402

HEADER = os.path.join(MARKS, "include", "bm_gen_access.h")
FORMAT = "bm-anchors 1"
LABEL_FMT = "loc_%08X: ;"
FUNC_FMT = "void sub_%08X(void)"


class Refused(Exception):
    def __init__(self, code, msg):
        Exception.__init__(self, "%s: %s" % (code, msg))
        self.code = code


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def sha_t(s):
    return sha_b(s.encode("utf-8"))


def um():
    sys.path.insert(0, UM_DIR)
    import um as _um  # noqa: E402  (read-only: constants and helpers; nothing in upstream_maint is written)
    return _um


def lines_of(b):
    return b.splitlines(keepends=True)


def strip_eol(x):
    return x.rstrip(b"\r\n")


# ---- emit (author side; reads the LOCAL um layer, writes hashes + our text) ---------------------------------------------
def emit(form, out, keep_ids=()):
    U = um()
    G = json.load(open(os.path.join(U.LAYERS, "gen_marks.json"), encoding="utf-8"))
    if G["pristine_gen_tree_hash"] != U.GEN_TREE:
        raise Refused("FORMAT", "um layer pins another pristine gen")
    pr = U.PRISTINE_GEN
    files = {f: U.sha_f(os.path.join(pr, f)) for f in sorted(os.listdir(pr)) if f.startswith("recomp_")}
    if U.gen_tree_hash(pr) != U.GEN_TREE:
        raise Refused("PRISTINE", "pristine gen folder is not gen_tree_hash %s" % U.GEN_TREE[:12])
    marks, n, stats = [], 0, {"marks": 0, "macro": 0, "original": 0, "lines_rewritten": 0, "rules": {}}
    for f in sorted(G["files"]):
        e = G["files"][f]
        pb = lines_of(open(os.path.join(pr, f), "rb").read())
        if sha_b(b"".join(pb)) != e["pristine_sha256"]:
            raise Refused("PRISTINE", f)
        for c in e["changes"]:
            n += 1
            mid = "m%03d" % n
            at, k = c["at"], len(c["remove_sha256"])
            lt = c["landmark"]["text"]
            lm_at = at - c["landmark"]["offset"]
            if strip_eol(pb[lm_at]).decode("utf-8") != lt:
                raise Refused("FORMAT", "%s: landmark line differs from the layer" % mid)
            m = re.fullmatch(r"loc_([0-9A-F]{8}): ;", lt)
            mf = re.fullmatch(r"void sub_([0-9A-F]{8})\(void\)", lt)
            if m:
                anc = {"kind": "label", "addr": "0x" + m.group(1)}
            elif mf:
                anc = {"kind": "function", "addr": "0x" + mf.group(1)}
            else:
                anc = {"kind": "line"}
            anc.update({"line_sha256": sha_t(lt), "offset": c["landmark"]["offset"], "span_sha256": c["landmark"]["span_sha256"],
                        "line": lm_at + 1})
            ins = list(c["insert"])
            fm = "original"
            if form == "macro" and mid not in keep_ids:
                new = []
                for x in ins:
                    y, rules = bm_rewrite.rewrite_line(x)
                    if rules:
                        if not bm_rewrite.line_equivalent(x, y):
                            raise Refused("REWRITE", "%s: rewrite not token-equivalent" % mid)
                        stats["lines_rewritten"] += 1
                        for r in rules:
                            stats["rules"][r] = stats["rules"].get(r, 0) + 1
                        fm = "macro"
                    new.append(y)
                ins = new
            stats[fm] += 1
            fa = c.get("function")
            marks.append({"id": mid, "file": f, "function_addr": ("0x" + fa[4:]) if fa else None, "anchor": anc,
                          "delete_sha256": list(c["remove_sha256"]),
                          "context_sha256": {"before": sha_b(pb[at - 1]) if at > 0 else sha_b(b""),
                                             "after": sha_b(pb[at + k]) if at + k < len(pb) else sha_b(b"")},
                          "insert": ins, "switches": c.get("switches", []), "form": fm})
    stats["marks"] = len(marks)
    A = {"format": FORMAT,
         "note": "Hook marks of Burnout Mashup for the user's locally generated code (xboxrecomp output of the user's own disc). "
                 "Anchors are guest addresses + sha256 only; 'insert' is Mashup text. No generated code is contained. "
                 "A representation of our changes; it does not decide any copyright question.",
         "pristine": {"gen_tree_hash": U.GEN_TREE, "xboxrecomp": U.XR_COMMIT, "takedawn": U.TD_COMMIT, "files": files},
         "header": {"path": "include/bm_gen_access.h", "sha256": sha_b(open(HEADER, "rb").read()),
                    "required": stats["macro"] > 0},
         "added": dict(G.get("added", {})),
         "result": {}, "form": form, "stats": stats, "marks": marks}
    res = apply_mem(A, pr, structural=True)
    A["result"] = {f: sha_b(b) for f, b in sorted(res.items()) if f in G["files"]}
    if form == "original":
        for f, e in G["files"].items():
            if A["result"][f] != e["marked_sha256"]:
                raise Refused("RESULT", "%s: original form does not reproduce the accepted marked file" % f)
    open(out, "w", encoding="utf-8", newline="\n").write(json.dumps(A, indent=1) + "\n")
    return A


# ---- apply (user side; pristine gen + anchors -> marked gen) -----------------------------------------------------------
def landmark_text(anc):
    if anc["kind"] == "label":
        return LABEL_FMT % int(anc["addr"], 16)
    if anc["kind"] == "function":
        return FUNC_FMT % int(anc["addr"], 16)
    return None


def apply_mem(A, pristine, structural=False):
    """-> {file: marked bytes} for every pristine file (unchanged ones as read). Raises Refused; never partial."""
    if A.get("format") != FORMAT:
        raise Refused("FORMAT", "not a %s file" % FORMAT)
    ids = [m["id"] for m in A["marks"]]
    if len(set(ids)) != len(ids):
        raise Refused("FORMAT", "duplicate mark id")
    out = {}
    for f, want in A["pristine"]["files"].items():
        if isinstance(pristine, dict):          # in-memory pristine (tests)
            if f not in pristine:
                raise Refused("MISSING_FILE", f)
            b = pristine[f]
        else:
            p = os.path.join(pristine, f)
            if not os.path.isfile(p):
                raise Refused("MISSING_FILE", f)
            b = open(p, "rb").read()
        if not structural and sha_b(b) != want:
            raise Refused("PRISTINE", "%s is not the pinned pristine file (sha256 %s)" % (f, want[:12]))
        out[f] = b
    byfile = {}
    for m in A["marks"]:
        if m["file"] not in out:
            raise Refused("FORMAT", "%s: file %s not pinned" % (m["id"], m["file"]))
        byfile.setdefault(m["file"], []).append(m)
    for f, rows in byfile.items():
        pb = lines_of(out[f])
        txt = [strip_eol(x) for x in pb]
        index = {}
        for i, x in enumerate(txt):
            index.setdefault(sha_b(x), []).append(i)
        pos = []
        for m in rows:
            a = m["anchor"]
            lt = landmark_text(a)
            if lt is not None and sha_t(lt) != a["line_sha256"]:
                raise Refused("FORMAT", "%s: landmark hash does not match its address %s" % (m["id"], a["addr"]))
            hits = index.get(a["line_sha256"], [])
            what = "%s %s" % (a["kind"], a.get("addr", a["line_sha256"][:12]))
            if not hits:
                raise Refused("MISSING_ANCHOR", "%s (%s): %s not found in %s" % (m["id"], m.get("function_addr"), what, f))
            if len(hits) > 1:
                raise Refused("AMBIGUOUS_ANCHOR", "%s: %s occurs %d times in %s (duplicate label)" % (m["id"], what, len(hits), f))
            lm = hits[0]
            at = lm + a["offset"]
            k = len(m["delete_sha256"])
            if at > len(pb) or at + k > len(pb):
                raise Refused("SPAN", "%s: mark beyond the end of %s" % (m["id"], f))
            if sha_b(b"".join(pb[lm:min(len(pb), at + k + 1)])) != a["span_sha256"]:
                raise Refused("SPAN", "%s: the generated code between %s and the mark changed (%s)" % (m["id"], what, f))
            if [sha_b(x) for x in pb[at:at + k]] != m["delete_sha256"]:
                raise Refused("DELETE", "%s: a line to delete differs (%s line %d)" % (m["id"], f, at + 1))
            cb = sha_b(pb[at - 1]) if at > 0 else sha_b(b"")
            ca = sha_b(pb[at + k]) if at + k < len(pb) else sha_b(b"")
            if cb != m["context_sha256"]["before"] or ca != m["context_sha256"]["after"]:
                raise Refused("CONTEXT", "%s: a neighbour line differs (%s line %d)" % (m["id"], f, at + 1))
            pos.append((at, k, m))
        pos.sort(key=lambda x: (x[0], x[1]))
        for (a1, k1, m1), (a2, k2, m2) in zip(pos, pos[1:]):
            if a2 < a1 + k1 or (a2 == a1):
                raise Refused("OVERLAP", "%s and %s overlap in %s" % (m1["id"], m2["id"], f))
        res = list(pb)
        for at, k, m in sorted(pos, key=lambda x: -x[0]):
            res[at:at + k] = [x.encode("utf-8") for x in m["insert"]]
        out[f] = b"".join(res)
    if not structural:
        for f, want in A["result"].items():
            if sha_b(out[f]) != want:
                raise Refused("RESULT", "%s: result sha256 %s differs from the pinned %s" % (f, sha_b(out[f])[:12], want[:12]))
    return out


def apply_dir(anchors, pristine, dest, structural=False):
    A = json.load(open(anchors, encoding="utf-8"))
    if os.path.exists(dest):
        raise Refused("DEST", "destination exists: %s" % dest)
    out = apply_mem(A, pristine, structural)
    os.makedirs(dest)
    for f, b in out.items():
        open(os.path.join(dest, f), "wb").write(b)
    return {"files": len(out), "marks": len(A["marks"]),
            "marked": {f: sha_b(out[f])[:12] for f in A["result"]}}


# ---- selftest ------------------------------------------------------------------------------------------------------------
def header_macros():
    out = {}
    for ln in open(HEADER, encoding="utf-8").read().splitlines():
        m = re.match(r"#define (BM_\w+)\(([^)]*)\) (.*?)\s*(/\*.*)?$", ln)
        if m:
            params = [p.strip() for p in m.group(2).split(",") if p.strip()]
            out[m.group(1)] = (params, m.group(3).strip())
    return out


def selftest():
    H = header_macros()
    T = bm_rewrite.MACROS
    ok = set(H) == set(T) and all(H[k][0] == T[k][0] and bm_rewrite.sigtoks(H[k][1]) == bm_rewrite.sigtoks(T[k][1]) for k in T)
    return {"header_equals_rewrite_table": ok, "macros": len(H)}


def main(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv else d
    if not argv:
        print(__doc__)
        return 1
    try:
        if argv[0] == "emit":
            keep = set()
            if opt("--keep-file"):
                keep = set(json.load(open(opt("--keep-file"), encoding="utf-8"))["keep_ids"])
            A = emit(opt("--form", "macro"), opt("--out"), keep)
            print(json.dumps({"emitted": opt("--out"), "form": A["form"], "stats": A["stats"],
                              "result": {f: s[:12] for f, s in A["result"].items()}}))
        elif argv[0] == "apply":
            print(json.dumps({"applied": True, **apply_dir(opt("--anchors"), opt("--pristine"), opt("--out"), "--structural" in argv)}))
        elif argv[0] == "check":
            A = json.load(open(opt("--anchors"), encoding="utf-8"))
            out = apply_mem(A, opt("--pristine"), "--structural" in argv)
            print(json.dumps({"check": "ok", "marks": len(A["marks"]), "files": len(out)}))
        elif argv[0] == "selftest":
            r = selftest()
            print(json.dumps(r))
            return 0 if r["header_equals_rewrite_table"] else 2
        else:
            print(__doc__)
            return 1
    except Refused as e:
        print(json.dumps({"refused": True, "code": e.code, "reason": str(e)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
