"""demacro.py - 1:1 back-mapping proof between the macro form and the original form (LOCAL; reads the original-form anchors).

    py -3 -B demacro.py --macro-gen DIR --accepted-gen DIR [--anchors ..\\anchors.json] [--original ..\\local\\anchors_original.local.json]

Checks: (1) both anchor files hold the same marks with the same anchors / delete / context hashes / switches - only the insert
text (and its form) differs; (2) every insert line pair is token-equivalent after expanding our macros (bm_rewrite.expand);
(3) replacing, in the macro-form gen files, each macro line by its original line (located through the mark positions) gives the
accepted marked files byte for byte. Then um.py audit / genchk (text checks of the original notation) on the accepted tree
apply to the macro form unchanged. Prints one JSON line; writes logs\\DEMACRO_marks.json.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MK = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bm_rewrite  # noqa: E402
import eqcheck  # noqa: E402


def main(av):
    def opt(n, d=None):
        return av[av.index(n) + 1] if n in av else d
    A = json.load(open(opt("--anchors", os.path.join(MK, "anchors.json")), encoding="utf-8"))
    O = json.load(open(opt("--original", os.path.join(MK, "local", "anchors_original.local.json")), encoding="utf-8"))
    keys = ("id", "file", "function_addr", "anchor", "delete_sha256", "context_sha256", "switches")
    same_struct = len(A["marks"]) == len(O["marks"]) and all(all(a[k] == o[k] for k in keys) for a, o in zip(A["marks"], O["marks"]))
    pairs, bad = 0, []
    for a, o in zip(A["marks"], O["marks"]):
        if len(a["insert"]) != len(o["insert"]):
            bad.append(a["id"])
            continue
        for x, y in zip(o["insert"], a["insert"]):
            if x != y:
                pairs += 1
                if not bm_rewrite.line_equivalent(x, y):
                    bad.append(a["id"])
    files = {}
    for f in A["result"]:
        cur = open(os.path.join(opt("--macro-gen"), f), "rb").read().splitlines(keepends=True)
        ml = eqcheck.mark_lines(A, f)
        for a, o in zip(A["marks"], O["marks"]):
            if a["file"] != f:
                continue
            s, _ = ml[a["id"]]
            for k, (x, y) in enumerate(zip(o["insert"], a["insert"])):
                if cur[s - 1 + k] != y.encode("utf-8"):
                    bad.append(a["id"] + ":pos")
                cur[s - 1 + k] = x.encode("utf-8")
        acc = open(os.path.join(opt("--accepted-gen"), f), "rb").read()
        files[f] = b"".join(cur) == acc
    R = {"same_marks_anchors_hashes": same_struct, "changed_line_pairs": pairs, "pairs_token_equivalent": not bad,
         "bad": bad, "view_equals_accepted": files, "all_ok": same_struct and not bad and all(files.values())}
    open(os.path.join(MK, "logs", "DEMACRO_marks.json"), "w", encoding="utf-8").write(json.dumps(R, indent=1) + "\n")
    print(json.dumps(R))
    return 0 if R["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
