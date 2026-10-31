"""fetch_upstream.py - obtain upstream Takedawn and xboxrecomp at the PINNED commits, verified, into a new work folder.

    py -3 -B fetch_upstream.py --git GIT.EXE --work NEWDIR --takedawn SRC --xboxrecomp SRC [--pins host/PINS.json]

SRC = a git URL (cloned bare into NEWDIR/_git, nothing else is downloaded) or a local clone (used read-only: only
`git rev-parse` and `git archive`; no fetch, no checkout, no change to its configuration). Result:
    NEWDIR/takedawn      git archive of the pinned Takedawn commit (core.autocrlf=false, as host/PINS.json says)
    NEWDIR/xboxrecomp    git archive of the pinned xboxrecomp commit (core.autocrlf=true: Windows line ends, as pinned)
Checks (REFUSED, exit 2, and the half-made folders are removed): the pinned commit exists in the source; its tree id equals the
pinned tree id; the extracted files (count and one sha256 over every path + file hash) equal the pinned archive digest. The line-end
mode is passed explicitly to git (`-c core.autocrlf=...`) so the global git configuration of this PC cannot change the bytes.
Original code (MIT). It fetches upstream source only; no game file is involved.
"""
import io
import os
import shutil
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmb_common as C  # noqa: E402


def is_url(s):
    return "://" in s or s.startswith("git@")


def source_repo(gitexe, src, name, work):
    """-> path of a git repository to read from (the local clone itself, or a fresh bare clone of the URL)"""
    if not is_url(src):
        if not os.path.isdir(src):
            raise C.Refused("%s: source %r is neither a git URL nor a folder" % (name, src))
        return os.path.abspath(src)
    dest = os.path.join(work, "_git", name + ".git")
    C.say("cloning %s -> %s (bare)" % (src, dest))
    C.git(gitexe, ["clone", "--bare", "--quiet", src, dest])
    return dest


def extract(data, dest):
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for m in t.getmembers():
            if m.issym() or m.islnk():
                raise C.Refused("archive has a link: %s" % m.name)
            if m.isdir() or m.type in (tarfile.XGLTYPE, tarfile.XHDTYPE):
                continue
            p = os.path.normpath(os.path.join(dest, m.name))
            if not p.startswith(os.path.normpath(dest) + os.sep):
                raise C.Refused("archive path escapes the folder: %s" % m.name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(t.extractfile(m).read())


def fetch_one(gitexe, name, pin, src, work):
    commit = pin["commit"]
    autocrlf = pin.get("autocrlf") or ("true" if "autocrlf=true" in pin.get("archive", "") else "false")
    repo = source_repo(gitexe, src, name, work)
    got = C.git(gitexe, ["-C", repo, "rev-parse", "--verify", commit + "^{commit}"], autocrlf).strip()
    if got != commit:
        raise C.Refused("%s: commit %s is not the pinned %s" % (name, got, commit))
    tree = C.git(gitexe, ["-C", repo, "rev-parse", "--verify", commit + "^{tree}"], autocrlf).strip()
    if tree != pin["tree_id"]:
        raise C.Refused("%s: tree id %s differs from the pinned %s" % (name, tree, pin["tree_id"]))
    dest = os.path.join(work, name)
    tmp = dest + ".partial"
    for d in (dest, tmp):
        if os.path.exists(d):
            raise C.Refused("%s exists: use a new work folder" % d)
    try:
        data = C.git(gitexe, ["-C", repo, "archive", "--format=tar", commit], autocrlf, binary=True)
        os.makedirs(tmp)
        extract(data, tmp)
        man = C.dir_manifest(tmp)
        dg = C.digest(man)
        want_dg, want_n = pin.get("archive_digest"), pin.get("files")
        if want_dg is None:
            raise C.Refused("%s: PINS.json has no archive_digest" % name)
        if len(man) != want_n or dg != want_dg:
            raise C.Refused("%s: extracted files (%d, digest %s) differ from the pinned archive (%d, digest %s); "
                            "line-end mode %s" % (name, len(man), dg[:12], want_n, want_dg[:12], autocrlf))
        os.rename(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return {"path": dest, "commit": commit, "tree_id": tree, "autocrlf": autocrlf, "files": len(man), "archive_digest": dg}


def run(argv):
    gitexe = C.arg_value(argv, "--git", required=True)
    work = os.path.abspath(C.arg_value(argv, "--work", required=True))
    pins = C.load_pins(C.arg_value(argv, "--pins"))
    srcs = {"takedawn": C.arg_value(argv, "--takedawn", required=True), "xboxrecomp": C.arg_value(argv, "--xboxrecomp", required=True)}
    if not os.path.isfile(gitexe):
        raise SystemExit("usage: --git %s is not a file" % gitexe)
    os.makedirs(work, exist_ok=True)
    out = {}
    made = []
    try:
        for name in ("takedawn", "xboxrecomp"):
            out[name] = fetch_one(gitexe, name, pins[name], srcs[name], work)
            made.append(out[name]["path"])
    except BaseException:
        for p in made:
            shutil.rmtree(p, ignore_errors=True)
        raise
    shutil.rmtree(os.path.join(work, "_git"), ignore_errors=True) if any(is_url(s) for s in srcs.values()) else None
    C.say("fetched takedawn %s and xboxrecomp %s" % (out["takedawn"]["commit"][:12], out["xboxrecomp"]["commit"][:12]))
    return {"ok": True, "fetched": out}


if __name__ == "__main__":
    sys.exit(C.main_wrapper(run))
