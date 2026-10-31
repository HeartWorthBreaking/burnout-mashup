"""apply_marks.py - put the Burnout Mashup hook marks into YOUR locally generated game code (exact-anchor refusal).

    py -3 -B apply_marks.py --takedawn DIR --pristine WORKDIR/gen_pristine [--host host] [--release]

Reads host/marks/anchors.json ("bm-anchors 1": guest-address anchors + sha256 of the generated lines + Mashup text) and applies it
to the pristine generated files made by regen.py, with host/marks/tools/anchors.py (apply_mem). REFUSED (exit 2, nothing written)
when: anchors.json or bm_gen_access.h is not the pinned file (host/PINS.json); a generated file is not the pinned pristine file;
an anchor is missing or ambiguous; a span, a deleted line or a neighbour line differs; the result of any marked file is not the
pinned result sha256; regen.stamp is not the pinned one; or the tree already has generated files. Marks are never relocated
approximately. On success the 29 marked generated files + regen.stamp are written to DIR/src/game/recomp/gen and the accessor
header is written to DIR/src/game/bm_gen_access.h (it is force-included by build.ps1).
--release (for the release-named build, build.ps1 -Release / BO3_RELEASE): the release configuration refuses generated files that differ
from their stamp, and the marked files do differ from the pristine ones. With --release the stamp written to the tree therefore names the
MARKED tree (line "tree", recomputed here from the files just written, after every marked file matched its pinned sha256) and keeps the
pinned pristine tree in a line "pristine" plus "marks <count> <anchors.json sha256>"; key, files, patches and spin_waits are unchanged.
Without --release the pinned stamp is copied byte for byte (the development reference build). Use a fresh tree per profile.
This changes YOUR generated code on YOUR PC only; the result is a local build input and must not be shared.
Original code (MIT).
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmb_common as C  # noqa: E402

GEN_REL = ("src", "game", "recomp", "gen")


def load_anchors_module(host):
    p = os.path.join(host, "marks", "tools", "anchors.py")
    sys.path.insert(0, os.path.dirname(p))          # anchors.py imports its sibling bm_rewrite.py
    spec = importlib.util.spec_from_file_location("bm_anchors", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(argv):
    td = os.path.abspath(C.arg_value(argv, "--takedawn", required=True))
    pristine = os.path.abspath(C.arg_value(argv, "--pristine", required=True))
    host = os.path.abspath(C.arg_value(argv, "--host", os.path.join(C.ROOT, "host")))
    pins = C.load_pins(C.arg_value(argv, "--pins"))
    mk = pins["marks"]
    apath = os.path.join(host, "marks", "anchors.json")
    hpath = os.path.join(host, "marks", "include", "bm_gen_access.h")
    if C.sha_f(apath) != mk["anchors_sha256"]:
        raise C.Refused("host/marks/anchors.json is not the pinned file")
    if C.sha_f(hpath) != mk["header_sha256"]:
        raise C.Refused("host/marks/include/bm_gen_access.h is not the pinned file")
    gen_dst = os.path.join(td, *GEN_REL)
    hdr_dst = os.path.join(td, "src", "game", "bm_gen_access.h")
    if os.path.isdir(gen_dst) and any(f.startswith("recomp_") or f == "regen.stamp" for f in os.listdir(gen_dst)):
        raise C.Refused("DEST: %s already has generated files (use a fresh checkout)" % gen_dst)
    if os.path.exists(hdr_dst):
        raise C.Refused("DEST: %s exists" % hdr_dst)
    A = C.jload(apath)
    if A["pristine"]["gen_tree_hash"] != pins["pristine_gen_tree_hash"] or len(A["marks"]) != mk["count"]:
        raise C.Refused("anchors.json is not for the pinned pristine tree / mark count")
    if not os.path.isdir(pristine):
        raise SystemExit("usage: %s is not a folder" % pristine)
    if C.gen_tree_hash(pristine) != pins["pristine_gen_tree_hash"]:
        raise C.Refused("%s is not the pinned pristine generated tree" % pristine)
    stamp_p = os.path.join(pristine, "regen.stamp")
    want_stamp = A.get("added", {}).get("regen.stamp")
    if not os.path.isfile(stamp_p) or C.sha_f(stamp_p) != want_stamp:
        raise C.Refused("regen.stamp is missing or not the pinned one")
    mod = load_anchors_module(host)
    try:
        out = mod.apply_mem(A, pristine, structural=False)
    except mod.Refused as e:
        raise C.Refused("%s" % e)
    # ---- write (everything checked)
    os.makedirs(gen_dst, exist_ok=True)
    changed = sorted(f for f, b in out.items() if C.sha_b(b) != A["pristine"]["files"][f])
    for f, b in sorted(out.items()):
        with open(os.path.join(gen_dst, f), "wb") as fh:
            fh.write(b)
    stamp = open(stamp_p, "rb").read()
    release = "--release" in argv
    if release:
        marked_tree = C.gen_tree_hash(gen_dst)
        lines = []
        for ln in stamp.decode("utf-8").splitlines():
            if ln.startswith("tree "):
                lines += ["tree " + marked_tree, "pristine " + ln[5:].strip(), "marks %d %s" % (len(A["marks"]), mk["anchors_sha256"])]
            else:
                lines.append(ln)
        if not any(ln.startswith("pristine ") for ln in lines):
            raise C.Refused("the pinned regen.stamp has no tree line")
        stamp = ("\n".join(lines) + "\n").encode("utf-8")
    with open(os.path.join(gen_dst, "regen.stamp"), "wb") as fh:
        fh.write(stamp)
    with open(hdr_dst, "wb") as fh:
        fh.write(open(hpath, "rb").read())
    C.say("marks applied: %d marks, %d generated files written (%d of them marked)%s" % (
        len(A["marks"]), len(out), len(changed), "; release stamp (marked tree)" if release else ""))
    res = {"ok": True, "marks": len(A["marks"]), "files": len(out), "marked_files": changed,
           "marked_sha12": {f: C.sha_b(out[f])[:12] for f in changed}}
    if release:
        res["release_stamp"] = {"tree": marked_tree, "pristine": pins["pristine_gen_tree_hash"]}
    return res


if __name__ == "__main__":
    sys.exit(C.main_wrapper(run))
