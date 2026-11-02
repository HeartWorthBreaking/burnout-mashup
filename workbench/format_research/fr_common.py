"""fr_common - shared helpers for the read-only format-research parsers (fr_routes / fr_props / fr_enviro).

Pure Python 3 stdlib. Every parser reads retail files from their ORIGINAL location (read only) and never writes them.
A parser decodes the structures it knows into records, keeps every other byte as raw bytes ("gaps"), and its
serialize() rebuilds the file from those records + gaps; fr_roundtrip.py proves byte identity.
"""
import hashlib
import struct

MAX_FILE = 64 * 1024 * 1024          # bound: no retail track file is near this


class FormatError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise FormatError(msg)


def al(x, a):
    return x + (-x) % a


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def read_ro(path):
    """read a file (read only, bounded)"""
    with open(path, "rb") as f:
        d = f.read(MAX_FILE + 1)
    need(len(d) <= MAX_FILE, "%s: larger than the %d-byte bound" % (path, MAX_FILE))
    return d


class Reader:
    """bounded little-endian reader over a buffer with a coverage map (which bytes a decoded structure claims)"""

    def __init__(self, d, base=0):
        self.d = d
        self.base = base
        self.cov = bytearray(len(d))

    def _chk(self, off, n, what):
        need(isinstance(off, int) and 0 <= off and n >= 0 and off + n <= len(self.d),
             "%s: 0x%X+0x%X outside 0..0x%X" % (what, off if isinstance(off, int) else -1, n, len(self.d)))

    def take(self, off, n, what, claim=True):
        self._chk(off, n, what)
        if claim:
            self.cov[off:off + n] = b"\x01" * n
        return self.d[off:off + n]

    def unpack(self, fmt, off, what, claim=True):
        n = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(off, n, what, claim))

    def u32(self, off, what="u32", claim=False):
        return self.unpack("<I", off, what, claim)[0]

    def s16(self, off, what="s16", claim=False):
        return self.unpack("<h", off, what, claim)[0]

    def u16(self, off, what="u16", claim=False):
        return self.unpack("<H", off, what, claim)[0]

    def gaps(self):
        """runs of bytes that no structure claimed and that are non-zero -> [(offset, bytes)] (kept verbatim)"""
        out, k, n, d, cov = [], 0, len(self.d), self.d, self.cov
        while k < n:
            if not cov[k] and d[k]:
                j = k
                while j < n and not cov[j] and d[j]:
                    j += 1
                out.append((k, bytes(d[k:j])))
                k = j
            else:
                k += 1
        return out

    def claimed(self):
        return sum(self.cov)


def place(size, pieces):
    """build a buffer of `size` zero bytes and write each (offset, bytes) piece; pieces must not overlap"""
    out = bytearray(size)
    used = bytearray(size)
    for off, b in pieces:
        need(0 <= off and off + len(b) <= size, "place: piece 0x%X+0x%X outside 0x%X" % (off, len(b), size))
        need(not any(used[off:off + len(b)]), "place: overlapping piece at 0x%X" % off)
        out[off:off + len(b)] = b
        used[off:off + len(b)] = b"\x01" * len(b)
    return bytes(out)
