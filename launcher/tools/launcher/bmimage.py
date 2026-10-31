"""bmimage.py - what a game input for BUILD MASHUP is, and whether it is supported (reads only; Python 3.8+, standard library).

Accepted inputs (all READ ONLY, nothing is copied by inspect()):
  - an installed game data folder (holds "Burnout 3 Takedown\\default.xbe"), or that "Burnout 3 Takedown" folder itself
  - an extracted disc folder (default.xbe at its top)
  - the file default.xbe itself
  - a disc image (.iso / .xiso): an Xbox (XDVDFS) image, plain xiso or a full disc dump (the game partition is found by its
    "MICROSOFT*XBOX*MEDIA" descriptor); default.xbe is read from the image in place
Supported: exactly the retail North American (NTSC-U) Burnout 3: Takedown executable (its sha256 is pinned in build/EXPECTED.json,
regen "xbe_sha256"); the recompiler's seeds and patch sites are addresses in that one file. Everything else is refused with the reason
(another game, another region, another revision or a modified file, a truncated image, not a game folder).
extract_xbe() writes default.xbe of a disc image into a folder you name (BUILD MASHUP: the isolated build folder, never elsewhere).
Original code (MIT)."""
import hashlib
import os
import struct

GAME_DIR = "Burnout 3 Takedown"
TITLE_ID = 0x4541005B                                   # "EA" 0x005B
REGION_NA, REGION_JP, REGION_ROW = 0x1, 0x2, 0x4
IMAGE_EXT = (".iso", ".xiso")
XDVD_MAGIC = b"MICROSOFT*XBOX*MEDIA"
SECTOR = 2048
PARTITIONS = (0, 0x18300000, 0x0FD90000, 0x02080000)    # plain xiso, XGD1, XGD2, XGD3 full-disc dumps


class Refused(Exception):
    """the input is not usable; the message says why and what to give instead"""


def _region_text(r):
    names = [n for bit, n in ((REGION_NA, "North America"), (REGION_JP, "Japan"), (REGION_ROW, "Europe / rest of the world")) if r & bit]
    return " + ".join(names) or "unknown (0x%x)" % r


def xbe_facts(head):
    """title id, title, region, version from the XBE certificate (head = the first 64 KB of the file)"""
    if head[:4] != b"XBEH":
        raise Refused("not an Xbox executable (no XBEH header)")
    base, cert_va = struct.unpack_from("<I", head, 0x104)[0], struct.unpack_from("<I", head, 0x118)[0]
    off = cert_va - base
    if not 0 < off < len(head) - 0xB0:
        raise Refused("the Xbox executable has no readable certificate")
    tid = struct.unpack_from("<I", head, off + 0x8)[0]
    title = head[off + 0xC:off + 0xC + 80].decode("utf-16-le", "replace").split("\x00")[0]
    region = struct.unpack_from("<I", head, off + 0xA0)[0]
    version = struct.unpack_from("<I", head, off + 0xAC)[0]
    return {"title_id": "%08X" % tid, "title": title, "region": _region_text(region), "region_flags": region, "version": version}


def verdict(facts, sha, want_sha):
    """(supported, reason)"""
    if sha == want_sha:
        return True, "supported: the retail North American (NTSC-U) Burnout 3: Takedown executable"
    if facts["title_id"] != "%08X" % TITLE_ID:
        return False, ("not Burnout 3: Takedown (title %r, id %s): only the retail NTSC-U Burnout 3: Takedown is supported"
                       % (facts["title"], facts["title_id"]))
    if not facts["region_flags"] & REGION_NA:
        return False, ("Burnout 3: Takedown for %s: only the retail North American (NTSC-U) release is supported (the recompiler's "
                       "addresses are those of that one executable)" % facts["region"])
    return False, ("Burnout 3: Takedown, North America, but another revision or a modified executable (version %d, sha256 %s...): "
                   "only the retail NTSC-U release (sha256 %s...) is supported; patched files are refused" % (facts["version"], sha[:12], want_sha[:12]))


# ------------------------------------------------------------------------------------------------------------------- XDVDFS
class Image:
    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        self.f = open(path, "rb")
        self.part = None
        for p in PARTITIONS:
            if p + 32 * SECTOR + SECTOR > self.size:
                continue
            self.f.seek(p + 32 * SECTOR)
            vd = self.f.read(SECTOR)
            if vd[:20] == XDVD_MAGIC and vd[0x7EC:0x7EC + 20] == XDVD_MAGIC:
                self.part = p
                self.root_sector, self.root_size = struct.unpack_from("<II", vd, 20)
                break
        if self.part is None:
            self.f.close()
            if self.size < 32 * SECTOR + SECTOR or (self.size < PARTITIONS[1] + 33 * SECTOR and self.size > 0x1000000):
                raise Refused("%s is not a readable Xbox disc image: no XDVDFS volume descriptor (the file may be truncated: %d bytes)"
                              % (path, self.size))
            raise Refused("%s is not an Xbox disc image (no XDVDFS volume descriptor 'MICROSOFT*XBOX*MEDIA')" % path)

    def close(self):
        self.f.close()

    def read(self, offset, n):
        if offset + n > self.size:
            raise Refused("%s is truncated: it ends at byte %d but data is needed up to byte %d (copy or dump the disc again)"
                          % (self.path, self.size, offset + n))
        self.f.seek(offset)
        return self.f.read(n)

    def find_root_file(self, name):
        """(start sector, size) of a file in the root directory (XDVDFS binary tree, names compared case-insensitively)"""
        tbl = self.read(self.part + self.root_sector * SECTOR, self.root_size)
        seen, todo, want = set(), [0], name.lower()
        while todo:
            o = todo.pop()
            if o in seen or o + 14 > len(tbl):
                continue
            seen.add(o)
            left, right, sector, size, attr, nlen = struct.unpack_from("<HHIIBB", tbl, o)
            if left == 0xFFFF and right == 0xFFFF:
                continue
            nm = tbl[o + 14:o + 14 + nlen].decode("latin-1")
            if nm.lower() == want and not attr & 0x10:
                return sector, size
            for nxt in (left, right):
                if nxt and nxt != 0xFFFF:
                    todo.append(nxt * 4)
        return None

    def file_reader(self, sector, size, chunk=1 << 20):
        off = self.part + sector * SECTOR
        self.read(off + size - 1, 1) if size else None          # the whole file must be inside the image
        done = 0
        while done < size:
            n = min(chunk, size - done)
            yield self.read(off + done, n)
            done += n


# ------------------------------------------------------------------------------------------------------------------- inspect
def _find_folder_xbe(p):
    for cand, kind in ((os.path.join(p, GAME_DIR, "default.xbe"), "installed game data folder"),
                       (os.path.join(p, "default.xbe"), "game folder (default.xbe at its top: an extracted disc or the installed '%s' folder)" % GAME_DIR)):
        if os.path.isfile(cand):
            return cand, kind
    return None, None


def inspect(path, want_sha):
    """-> dict: kind, path, xbe (in place) or image entry, sha256, facts, supported, reason. Raises Refused for unusable inputs."""
    p = os.path.abspath(str(path).strip().strip('"'))
    if not os.path.exists(p):
        raise Refused("%s does not exist" % p)
    out = {"input": p}
    if os.path.isdir(p):
        xbe, kind = _find_folder_xbe(p)
        if not xbe:
            raise Refused("%s is not a game folder: it has no default.xbe (looked for '%s' and '%s'). Give your installed game data folder, "
                          "an extracted disc folder or a disc image" % (p, os.path.join(GAME_DIR, "default.xbe"), "default.xbe"))
        out.update(kind=kind, xbe=xbe, source="folder")
        h, head = hashlib.sha256(), b""
        with open(xbe, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                if len(head) < 0x10000:
                    head += blk[:0x10000 - len(head)]
                h.update(blk)
    elif p.lower().endswith(IMAGE_EXT):
        img = Image(p)
        try:
            ent = img.find_root_file("default.xbe")
            if not ent:
                raise Refused("%s is an Xbox disc image without default.xbe in its root folder" % p)
            out.update(kind="disc image (XDVDFS, partition at byte %d)" % img.part, image=p, image_entry=list(ent), source="image")
            h, head = hashlib.sha256(), b""
            for blk in img.file_reader(*ent):
                if len(head) < 0x10000:
                    head += blk[:0x10000 - len(head)]
                h.update(blk)
        finally:
            img.close()
    elif os.path.basename(p).lower() == "default.xbe" or p.lower().endswith(".xbe"):
        out.update(kind="Xbox executable file", xbe=p, source="file")
        with open(p, "rb") as f:
            head = f.read(0x10000)
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
    else:
        raise Refused("%s is a file but not a disc image (.iso / .xiso) or default.xbe. Give your installed game data folder, an extracted "
                      "disc folder or a disc image" % p)
    sha = h.hexdigest()
    facts = xbe_facts(head)
    ok, why = verdict(facts, sha, want_sha)
    out.update(sha256=sha, facts=facts, supported=ok, reason=why)
    return out


def extract_xbe(info, dest_dir):
    """write default.xbe of a disc-image input to dest_dir/default.xbe (via a .partial file, sha256 checked) -> its path"""
    if info.get("source") != "image":
        return info["xbe"]
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "default.xbe")
    if os.path.isfile(dest) and _sha(dest) == info["sha256"]:
        return dest
    tmp = dest + ".partial"
    img = Image(info["image"])
    try:
        h = hashlib.sha256()
        with open(tmp, "wb") as f:
            for blk in img.file_reader(*info["image_entry"]):
                h.update(blk)
                f.write(blk)
    finally:
        img.close()
    if h.hexdigest() != info["sha256"]:
        os.remove(tmp)
        raise Refused("default.xbe read from the image changed while it was read (sha256 differs): the image is being written?")
    os.replace(tmp, dest)
    return dest


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()
