"""trackconv.common - shared helpers: errors, hashing, alignment, a guarded writer.

Every trackconv operation writes only below an explicit output root (OutRoot). Inputs are opened read only."""
import hashlib
import os
import struct

u16 = lambda b, o: struct.unpack_from("<H", b, o)[0]  # noqa: E731
u32 = lambda b, o: struct.unpack_from("<I", b, o)[0]  # noqa: E731
s16 = lambda b, o: struct.unpack_from("<h", b, o)[0]  # noqa: E731


class TCError(Exception):
    """a refused input or a broken rule (the message says which)"""


def need(cond, msg):
    if not cond:
        raise TCError(msg)


def al(x, a):
    return x + (-x) % a


def lastnz(b):
    k = len(b)
    while k and b[k - 1] == 0:
        k -= 1
    return k


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()


def rd(p):
    with open(p, "rb") as f:
        return f.read()


class OutRoot:
    """a write guard: every path written must lie inside `root` (created on first use)."""

    def __init__(self, root):
        self.root = os.path.abspath(root)

    def path(self, *parts):
        p = os.path.abspath(os.path.join(self.root, *parts))
        need(os.path.commonpath([p, self.root]) == self.root, "refusing to write outside %s: %s" % (self.root, p))
        return p

    def write(self, rel, data):
        p = self.path(*rel.replace("\\", "/").split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return sha(data)

    def write_text(self, rel, text):
        return self.write(rel, text.encode("utf-8"))


def sums_text(root, files):
    """sha256sum-format lines ("<hash> *<rel>") for the given relative paths under root, sorted"""
    lines = []
    for rel in sorted(files):
        lines.append("%s *%s" % (sha_file(os.path.join(root, *rel.split("/"))), rel))
    return "\n".join(lines) + "\n"


def verify_sums(root, name="SHA256SUMS.txt"):
    """every file listed in root/name -> (ok, n, bad)"""
    bad, n = [], 0
    with open(os.path.join(root, name), encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            h, p = line.strip().split(" *", 1)
            n += 1
            fp = os.path.join(root, *p.split("/"))
            if not os.path.exists(fp) or sha_file(fp) != h:
                bad.append(p)
    return not bad and n > 0, n, bad
