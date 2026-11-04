"""apply_layers.py - apply the Burnout Mashup host layers (host/tree, host/tree.patch, host/toolkit/*.patch) onto the fetched upstream.

    py -3 -B apply_layers.py host --takedawn DIR --xboxrecomp DIR [--host host] [--expected build/EXPECTED.json]

Strict unique-anchor rule: a patch hunk applies ONLY if its old block (context + removed lines) occurs EXACTLY ONCE in the
current text of its file; a missing block, an ambiguous block (2+ matches), a pre-image whose sha256 is not the pinned base,
a hunk-count change, a collision with an existing file, a CRLF-converted patch or a result that is not the pinned one is a
REFUSAL: exit 2 and NOTHING is written (everything is computed in memory first, then written). There is no nearest-line
guess and no fuzz. Hunk position numbers in the patch are informational only.
    host/tree/**            -> added to the Takedawn checkout at the same relative paths (a file that exists already is a collision)
    host/tree.patch         -> modifies Takedawn files (paths 'tree/<file>')
    host/toolkit/toolkit.patch + host/toolkit/lgpl/apu_core.patch -> modify xboxrecomp files (paths 'toolkit/<file>')
    host/toolkit/added/**   -> added to the xboxrecomp checkout at the same relative paths (a file that exists already is a collision)
Run it ONCE per fresh checkout; a second run is refused (pre-image differs). Original code (MIT); the logic is a port of the
unique-anchor rule of the project's layer tool, so this tree is self-contained.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmb_common as C  # noqa: E402


# ---------------------------------------------------------------------------------------------------------------- patch text
def parse_patch(text, label):
    """-> [ {path, hunks: [(hint, old_lines, new_lines)]} ]  (unified-diff text, '#' description lines before the first file)"""
    files, cur, hunk = [], None, None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if cur is None and ln.startswith("#"):
            i += 1
            continue
        if ln.startswith("--- "):
            a = ln[4:]
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise C.Refused("%s: malformed patch at line %d" % (label, i + 1))
            b = lines[i + 1][4:]
            if a == "/dev/null" or b == "/dev/null":
                raise C.Refused("%s: file creation / deletion is not part of a host patch (line %d)" % (label, i + 1))
            cur = {"path": b[2:], "hunks": []}
            files.append(cur)
            hunk = None
            i += 2
            continue
        if cur is None:
            raise C.Refused("%s: text before the first file header (line %d)" % (label, i + 1))
        if ln.startswith("@@"):
            try:
                hint = int(ln.split()[1].split(",")[0][1:])
            except (IndexError, ValueError):
                raise C.Refused("%s: malformed hunk header at line %d" % (label, i + 1))
            hunk = (hint, [], [])
            cur["hunks"].append(hunk)
        elif hunk is None:
            raise C.Refused("%s: unexpected line before a hunk (line %d)" % (label, i + 1))
        elif ln.startswith(" "):
            hunk[1].append(ln[1:])
            hunk[2].append(ln[1:])
        elif ln.startswith("-"):
            hunk[1].append(ln[1:])
        elif ln.startswith("+"):
            hunk[2].append(ln[1:])
        elif ln == "":
            hunk[1].append("")
            hunk[2].append("")
        else:
            raise C.Refused("%s: bad patch line %d" % (label, i + 1))
        i += 1
    return files


def read_lines(path):
    """-> (lines without EOL, eol, ends_with_eol); mixed line ends are refused"""
    t = open(path, "rb").read().decode("utf-8")
    crlf, lf = t.count("\r\n"), t.count("\n")
    if crlf and crlf != lf:
        raise C.Refused("%s has mixed line ends (%d CRLF of %d)" % (path, crlf, lf))
    eol = "\r\n" if crlf else "\n"
    end = t.endswith(eol)
    body = t[:-len(eol)] if end else t
    return (body.split(eol) if t else []), eol, end


def join_lines(lines, eol, end):
    return (eol.join(lines) + (eol if end and lines else "")).encode("utf-8")


def find_unique(lines, block, label):
    """index of the ONLY occurrence of block in lines; Refused when missing or ambiguous (never a nearest pick)"""
    n = len(block)
    if n == 0:
        if not lines:
            return 0
        raise C.Refused("%s: empty anchor on a non-empty file" % label)
    first = block[0]
    hits = [k for k in range(len(lines) - n + 1) if lines[k] == first and lines[k:k + n] == block]
    if not hits:
        raise C.Refused("%s: MISSING anchor (0 matches)" % label)
    if len(hits) > 1:
        raise C.Refused("%s: AMBIGUOUS anchor (%d matches, lines %s)" % (label, len(hits), [h + 1 for h in hits[:5]]))
    return hits[0]


def apply_hunks(lines, hunks, label):
    """apply [(hint, old, new)] in order; each old block must be unique in the CURRENT text -> new lines"""
    out = list(lines)
    for i, (hint, old, new) in enumerate(hunks):
        k = find_unique(out, old, "%s hunk %d/%d (@%d)" % (label, i + 1, len(hunks), hint))
        out[k:k + len(old)] = new
    return out


# ---------------------------------------------------------------------------------------------------------------- host layer
def load_patch(path, label):
    b = open(path, "rb").read()
    if b"\r" in b:
        raise C.Refused("%s contains carriage returns: the checkout converted its line ends (use git -c core.autocrlf=false "
                        "or keep .gitattributes); the layers need the bytes as published" % label)
    return parse_patch(b.decode("utf-8"), label)


def stage_patch(files, prefix, target, want_mod, pre, label):
    """-> {relpath: bytes} for every file of a patch; pre-image / hunk counts / uniqueness checked"""
    staged = {}
    for f in files:
        if not f["path"].startswith(prefix + "/"):
            raise C.Refused("%s: path %s is not under %s/" % (label, f["path"], prefix))
        rel = f["path"][len(prefix) + 1:]
        if rel not in want_mod:
            raise C.Refused("%s: %s is not listed in host/LAYERS.json" % (label, rel))
        if rel in staged:
            raise C.Refused("%s: %s appears twice" % (label, rel))
        p = os.path.join(target, *rel.split("/"))
        if not os.path.isfile(p):
            raise C.Refused("%s: MISSING file %s" % (label, rel))
        if C.sha_f(p) != want_mod[rel]["base_sha256"]:
            raise C.Refused("%s: pre-image sha256 of %s differs from the pinned base (wrong upstream, already patched, or "
                            "line ends changed)" % (label, rel))
        if len(f["hunks"]) != want_mod[rel]["hunks"]:
            raise C.Refused("%s: %s has %d hunks, expected %d (patch tampered)" % (label, rel, len(f["hunks"]), want_mod[rel]["hunks"]))
        lines, eol, end = read_lines(p)
        staged[rel] = join_lines(apply_hunks(lines, f["hunks"], "%s/%s" % (label, rel)), eol, end)
    return staged


def run(argv):
    if not argv or argv[0] != "host":
        raise SystemExit(__doc__)
    td = os.path.abspath(C.arg_value(argv, "--takedawn", required=True))
    xr = os.path.abspath(C.arg_value(argv, "--xboxrecomp", required=True))
    host = os.path.abspath(C.arg_value(argv, "--host", os.path.join(C.ROOT, "host")))
    exp = C.load_expected(C.arg_value(argv, "--expected"))["host_layers"]
    lay = C.jload(os.path.join(host, "LAYERS.json"))
    for d in (td, xr):
        if not os.path.isdir(d):
            raise SystemExit("usage: %s is not a folder" % d)
    # ---- the layer files themselves (CRLF-converted or edited checkouts are caught here)
    tree_dir = os.path.join(host, "tree")
    added_man = C.dir_manifest(tree_dir)
    if len(added_man) != exp["tree_added_files"] or C.digest(added_man) != exp["tree_added_digest"]:
        raise C.Refused("host/tree is not the published one (%d files, digest %s; expected %d, %s): edited, or a checkout that "
                        "converted line ends" % (len(added_man), C.digest(added_man)[:12], exp["tree_added_files"], exp["tree_added_digest"][:12]))
    x_added_dir = os.path.join(host, "toolkit", "added")
    x_added = C.dir_manifest(x_added_dir)
    if len(x_added) != exp["toolkit_added_files"] or C.digest(x_added) != exp["toolkit_added_digest"]:
        raise C.Refused("host/toolkit/added is not the published one (%d files, digest %s; expected %d, %s): edited, or a checkout that "
                        "converted line ends" % (len(x_added), C.digest(x_added)[:12], exp["toolkit_added_files"], exp["toolkit_added_digest"][:12]))
    t_files = load_patch(os.path.join(host, "tree.patch"), "tree.patch")
    x_files = load_patch(os.path.join(host, "toolkit", "toolkit.patch"), "toolkit.patch")
    l_files = load_patch(os.path.join(host, "toolkit", "lgpl", "apu_core.patch"), "apu_core.patch")
    lg = lay["toolkit"]["lgpl_file"]
    if [f["path"] for f in l_files] != ["toolkit/" + lg] or any(f["path"] == "toolkit/" + lg for f in x_files):
        raise C.Refused("the LGPL file's hunks must be only in host/toolkit/lgpl/apu_core.patch")
    # ---- stage everything in memory
    st_t = stage_patch(t_files, "tree", td, lay["tree"]["modified"], True, "tree.patch")
    st_x = stage_patch(x_files, "toolkit", xr, lay["toolkit"]["modified"], True, "toolkit.patch")
    st_l = stage_patch(l_files, "toolkit", xr, lay["toolkit"]["modified"], True, "apu_core.patch")
    st_x.update(st_l)
    if sorted(st_t) != sorted(lay["tree"]["modified"]):
        raise C.Refused("tree.patch does not cover exactly the files of host/LAYERS.json")
    if sorted(st_x) != sorted(lay["toolkit"]["modified"]):
        raise C.Refused("toolkit patches do not cover exactly the files of host/LAYERS.json")
    for rel in added_man:
        dst = os.path.join(td, *rel.split("/"))
        if os.path.exists(dst):
            raise C.Refused("COLLISION: upstream already has host/tree/%s" % rel)
        if rel in st_t:
            raise C.Refused("host/tree/%s is added and patched at once" % rel)
    for rel in x_added:
        if os.path.exists(os.path.join(xr, *rel.split("/"))):
            raise C.Refused("COLLISION: upstream already has host/toolkit/added/%s" % rel)
        if rel in st_x:
            raise C.Refused("host/toolkit/added/%s is added and patched at once" % rel)
    # ---- results must be the pinned ones (in memory)
    res = {}
    for root, st in (("tree", st_t), ("toolkit", st_x)):
        for rel, data in st.items():
            h = C.sha_b(data)
            if h != exp["modified_result_sha256"][root + "/" + rel]:
                raise C.Refused("%s/%s: result sha256 %s differs from the pinned %s" % (root, rel, h[:12], exp["modified_result_sha256"][root + "/" + rel][:12]))
            res[root + "/" + rel] = h
    same_as_private = sum(1 for k, v in res.items() if v == (lay["tree"]["modified"] if k.startswith("tree/") else lay["toolkit"]["modified"])[k.split("/", 1)[1]]["result_sha256"])
    # ---- write (everything checked)
    for root, st, base in (("tree", st_t, td), ("toolkit", st_x, xr)):
        for rel, data in st.items():
            with open(os.path.join(base, *rel.split("/")), "wb") as f:
                f.write(data)
    for rel in added_man:
        dst = os.path.join(td, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(open(os.path.join(tree_dir, *rel.split("/")), "rb").read())
    for rel in x_added:
        dst = os.path.join(xr, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(open(os.path.join(x_added_dir, *rel.split("/")), "rb").read())
    C.say("host layers applied: %d Takedawn files patched (%d hunks), %d added, %d xboxrecomp files patched, %d added"
          % (len(st_t), sum(len(f["hunks"]) for f in t_files), len(added_man), len(st_x), len(x_added)))
    return {"ok": True, "tree_patched": len(st_t), "tree_added": len(added_man), "toolkit_patched": len(st_x), "toolkit_added": len(x_added),
            "hunks": sum(len(f["hunks"]) for f in t_files + x_files + l_files),
            "results_equal_private_reference_sha": same_as_private, "results_checked": len(res)}


if __name__ == "__main__":
    sys.exit(C.main_wrapper(run))
