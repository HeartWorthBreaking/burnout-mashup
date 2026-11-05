"""regen.py - run upstream's recompiler on YOUR OWN default.xbe and check the result is the pinned pristine generated tree.

    py -3 -B regen.py --takedawn DIR --xboxrecomp DIR --xbe PATH_TO_YOUR_default.xbe --python PYTHON_WITH_CAPSTONE \\
                      --work WORKDIR [--pins host/PINS.json] [--expected build/EXPECTED.json]

Run it AFTER apply_layers.py (the Mashup host layer changes config/patches.json, an input of the recompiler). It runs the same
five steps as upstream's regen.sh / tools/release/gen.sh with the patches and spin waits of the checkout on:
xbe_parser, disasm, func_id, abi_analysis, recomp. The generated C goes to WORKDIR/gen_pristine (NOT into the Takedawn tree: the
hook marks are applied by apply_marks.py, which puts the marked files into the tree). Needs Python with capstone 5.0.7.
Checks (REFUSED, exit 2): the xbe sha256 equals the one in tools/install/supported.json of the checkout (the retail NTSC-U
default.xbe; any other build is refused, not tried); capstone has the pinned version; after the run the generated tree hash
equals the pinned pristine_gen_tree_hash (else the generated files are deleted again) and the recompiler's patch report is the
pinned one. Also writes WORKDIR/gen_pristine/regen.stamp (the upstream stamp format) which apply_marks.py checks by sha256.
The executable is only READ (never copied, never written). The generated files are produced on your PC and must stay there.
Original code (MIT); it runs upstream's recompiler and contains no game code.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmb_common as C  # noqa: E402


def steps(py, xbe, tree, out, gen):
    cfg = os.path.join(tree, "config")
    return [
        ("xbe_parser", py + ["-m", "tools.xbe_parser", xbe, "--json", os.path.join(out, "analysis.json"), "--quiet"]),
        ("disasm", py + ["-m", "tools.disasm", xbe, "--analysis-json", os.path.join(out, "analysis.json"),
                         "--seed-functions", os.path.join(cfg, "seed_functions.json"), "-o", os.path.join(out, "disasm"), "-v"]),
        ("func_id", py + ["-m", "tools.func_id", xbe, "--functions", os.path.join(out, "disasm", "functions.json"),
                          "--strings", os.path.join(out, "disasm", "strings.json"), "--xrefs", os.path.join(out, "disasm", "xrefs.json"),
                          "-o", os.path.join(out, "func_id")]),
        ("abi_analysis", py + ["-m", "tools.abi_analysis", xbe, "--functions", os.path.join(out, "disasm", "functions.json"),
                               "--identified", os.path.join(out, "func_id", "identified_functions.json"),
                               "--output-dir", os.path.join(out, "abi")]),
        ("recomp", py + ["-m", "tools.recomp", xbe, "--all", "--split", "1000", "--disasm-dir", os.path.join(out, "disasm"),
                         "--func-id-dir", os.path.join(out, "func_id"), "--abi-dir", os.path.join(out, "abi"),
                         "--exclude-manual", os.path.join(tree, "src", "game", "recomp", "recomp_manual.c"),
                         "--spin-waits", os.path.join(cfg, "spin_waits.json"), "--patches", os.path.join(cfg, "patches.json"),
                         "--mem-order", os.path.join(cfg, "mem_order.json"),
                         "--gen-dir", gen, "-o", os.path.join(out, "recomp")]),
    ]


def run(argv):
    tree = os.path.abspath(C.arg_value(argv, "--takedawn", required=True))
    xr = os.path.abspath(C.arg_value(argv, "--xboxrecomp", required=True))
    xbe = os.path.abspath(C.arg_value(argv, "--xbe", required=True))
    pyexe = os.path.abspath(C.arg_value(argv, "--python", required=True))
    work = os.path.abspath(C.arg_value(argv, "--work", required=True))
    pins = C.load_pins(C.arg_value(argv, "--pins"))
    exp = C.load_expected(C.arg_value(argv, "--expected"))["regen"]
    for p in (xbe, pyexe):
        if not os.path.isfile(p):
            raise SystemExit("usage: %s is not a file" % p)
    gen = os.path.join(work, "gen_pristine")
    out = os.path.join(work, "xr")
    for d in (gen, out):
        if os.path.exists(d):
            raise C.Refused("%s exists: use a new work folder" % d)
    # ---- the executable must be the supported retail build (read only)
    sup = open(os.path.join(tree, "tools", "install", "supported.json"), encoding="utf-8").read()
    m = re.search(r'"sha256":\s*"([0-9a-f]{64})"', sup)
    have = C.sha_f(xbe)
    if not m or have != m.group(1):
        raise C.Refused("%s is not the supported retail default.xbe (sha256 %s..., supported build %s...): the recompiler's seeds and "
                        "patch sites are addresses in that exact executable" % (xbe, have[:12], (m.group(1) if m else "?")[:12]))
    if not have.startswith(exp["xbe_sha256_prefix"]) or not pins["xbe_signature"].startswith(exp["xbe_sha256_prefix"]):
        raise C.Refused("the supported build in this checkout is not the one the Mashup layers were made for (%s)" % exp["xbe_sha256_prefix"])
    # ---- python + capstone
    r = subprocess.run([pyexe, "-c", "import capstone;print(capstone.__version__)"], capture_output=True, text=True)
    ver = r.stdout.strip()
    if r.returncode or ver != exp["capstone"]:
        raise C.Refused("%s needs capstone %s (found %r): pip install capstone==%s" % (pyexe, exp["capstone"], ver or r.stderr.strip()[-80:], exp["capstone"]))
    os.makedirs(out)
    os.makedirs(gen)
    env = dict(os.environ)
    for k in ("TRACE_FUNCS", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(k, None)
    t_all = time.time()
    for name, cmd in steps([pyexe, "-B"], xbe, tree, out, gen):
        t0 = time.time()
        with open(os.path.join(out, name + ".log"), "w", encoding="utf-8", errors="replace") as lf:
            rr = subprocess.run(cmd, cwd=xr, stdout=lf, stderr=subprocess.STDOUT, env=env)
        C.say("==> %s rc %d (%.0f s)" % (name, rr.returncode, time.time() - t0))
        if rr.returncode:
            shutil.rmtree(gen, ignore_errors=True)
            raise SystemExit("regen: %s failed (rc %d), see %s" % (name, rr.returncode, os.path.join(out, name + ".log")))
    # ---- the result must be the pinned pristine tree
    tree_hash = C.gen_tree_hash(gen)
    files = sorted(f for f in os.listdir(gen) if f.startswith("recomp_"))
    if tree_hash != pins["pristine_gen_tree_hash"]:
        shutil.rmtree(gen, ignore_errors=True)
        raise C.Refused("the generated code differs from the pinned one (tree %s..., pinned %s...): another default.xbe build, "
                        "recompiler or toolkit revision, or capstone version" % (tree_hash[:12], pins["pristine_gen_tree_hash"][:12]))
    rep = C.jload(os.path.join(out, "recomp", "patches.json"))
    patches = "%d/%d" % (rep["patched_sites"], len(rep["sites"]))
    spins = sum(sum(1 for ln in open(os.path.join(gen, f), "rb") if b"RECOMP_SPIN_WAIT" in ln) for f in files if re.match(r"recomp_0", f))
    if patches != exp["patches"] or spins != exp["spin_waits"] or len(files) != exp["files"]:
        shutil.rmtree(gen, ignore_errors=True)
        raise C.Refused("recompiler report differs: patches %s (pinned %s), spin waits %d (%d), files %d (%d)"
                        % (patches, exp["patches"], spins, exp["spin_waits"], len(files), exp["files"]))
    stamp = "key %s\ntree %s\nfiles %d\npatches %s\nspin_waits %d\n" % (exp["stamp_key"], tree_hash, len(files), patches, spins)
    with open(os.path.join(gen, "regen.stamp"), "w", encoding="utf-8", newline="\n") as f:
        f.write(stamp)
    res = {"ok": True, "gen_tree_hash": tree_hash, "files": len(files), "patches": patches, "spin_waits": spins,
           "gen_pristine": gen, "seconds": round(time.time() - t_all)}
    C.jdump(res, os.path.join(out, "regen_result.json"))
    C.say("regen ok: generated tree %s (%d files), %d s" % (tree_hash[:12], len(files), res["seconds"]))
    return res


if __name__ == "__main__":
    sys.exit(C.main_wrapper(run))
