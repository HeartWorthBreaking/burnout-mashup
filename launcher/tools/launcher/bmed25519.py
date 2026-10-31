"""bmed25519.py - Ed25519 signature VERIFICATION (RFC 8032, section 5.1.7, the reference algorithm) and the OpenSSH signature format
("ssh-keygen -Y sign", SSHSIG, PROTOCOL.sshsig) for the launcher's update check. Python 3.8+, standard library only (hashlib, base64):
the launcher needs no new runtime dependency. Original code (MIT).

Why this format: every Windows 10 / 11 PC has OpenSSH's ssh-keygen (C:\\Windows\\System32\\OpenSSH), so the maintainer signs a release
manifest with a standard tool and no extra install:
    ssh-keygen -Y sign -f <private key> -n bmashup-update latest.json          -> latest.json.sig
and anyone can check it with
    ssh-keygen -Y check-novalidate -n bmashup-update -f <public key file> -s latest.json.sig < latest.json
This module checks the same signature in Python. Only verification lives here (the launcher never signs); verification is strict:
a 32-byte public key that decodes to a curve point (canonical y < p), a canonical R, s < L, and the cofactorless equation
[s]B = R + [k]A compared as points. Speed: a few hundredths of a second per signature (pure Python big integers).

    verify(public_key_32, message, signature_64) -> bool
    parse_public_key("ssh-ed25519 AAAA... comment") -> (raw 32-byte key, "SHA256:..." fingerprint)
    verify_sshsig(armored_text, message, namespace, trusted) -> fingerprint of the trusted key that signed it; raises SignatureError
"""
import base64
import hashlib
import struct

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)
NAMESPACE = "bmashup-update"


class SignatureError(Exception):
    pass


def _inv(x):
    return pow(x, P - 2, P)


def _add(p1, p2):
    a = (p1[1] - p1[0]) * (p2[1] - p2[0]) % P
    b = (p1[1] + p1[0]) * (p2[1] + p2[0]) % P
    c = 2 * p1[3] * p2[3] * D % P
    d = 2 * p1[2] * p2[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _equal(p1, p2):
    return (p1[0] * p2[2] - p2[0] * p1[2]) % P == 0 and (p1[1] * p2[2] - p2[1] * p1[2]) % P == 0


def _recover_x(y, sign):
    if y >= P:
        return None
    x2 = (y * y - 1) * _inv(D * y * y + 1) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_GY = 4 * _inv(5) % P
_GX = _recover_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % P)


def _compress(pt):
    zi = _inv(pt[2])
    x, y = pt[0] * zi % P, pt[1] * zi % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little") % L


def verify(public, msg, sig):
    """RFC 8032 Ed25519 verify -> True / False (never raises for malformed input)"""
    if not isinstance(public, bytes) or not isinstance(sig, bytes) or len(public) != 32 or len(sig) != 64:
        return False
    a = _decompress(public)
    if a is None:
        return False
    rs = sig[:32]
    r = _decompress(rs)
    if r is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= L:
        return False
    k = _h(rs + public + msg)
    return _equal(_mul(s, G), _add(r, _mul(k, a)))


# ------------------------------------------------------------------------------------------------------------------ OpenSSH formats
def _read_string(b, i):
    if i + 4 > len(b):
        raise SignatureError("truncated")
    n = struct.unpack(">I", b[i:i + 4])[0]
    if i + 4 + n > len(b):
        raise SignatureError("truncated")
    return b[i + 4:i + 4 + n], i + 4 + n


def _string(x):
    return struct.pack(">I", len(x)) + x


def _ed25519_blob(blob):
    kt, i = _read_string(blob, 0)
    key, i = _read_string(blob, i) if kt == b"ssh-ed25519" else (b"", i)
    if kt != b"ssh-ed25519" or len(key) != 32 or i != len(blob):
        raise SignatureError("not an ssh-ed25519 public key")
    return key


def fingerprint(blob):
    """the fingerprint ssh-keygen -l prints: SHA256:<base64 without padding>"""
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")


def parse_public_key(line):
    """'ssh-ed25519 AAAA... [comment]' -> (raw 32 bytes, fingerprint). Raises SignatureError."""
    parts = (line or "").strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise SignatureError("a trusted key must be one 'ssh-ed25519 AAAA...' line (the .pub file of the signing key)")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (ValueError, TypeError):
        raise SignatureError("the trusted key is not valid base64")
    key = _ed25519_blob(blob)
    if _decompress(key) is None:
        raise SignatureError("the trusted key is not a valid Ed25519 point")
    return key, fingerprint(blob)


def parse_sshsig(text):
    """armored SSH SIGNATURE -> dict(public_blob, namespace, reserved, hash_alg, sig_raw). Raises SignatureError."""
    if isinstance(text, bytes):
        try:
            text = text.decode("ascii")
        except UnicodeDecodeError:
            raise SignatureError("the signature file is not text")
    lines = [ln.strip() for ln in text.strip().splitlines()]
    if len(lines) < 3 or lines[0] != "-----BEGIN SSH SIGNATURE-----" or lines[-1] != "-----END SSH SIGNATURE-----":
        raise SignatureError("not an OpenSSH signature (ssh-keygen -Y sign)")
    try:
        b = base64.b64decode("".join(lines[1:-1]), validate=True)
    except (ValueError, TypeError):
        raise SignatureError("the signature is not valid base64")
    if b[:6] != b"SSHSIG" or len(b) < 10 or struct.unpack(">I", b[6:10])[0] != 1:
        raise SignatureError("not an SSHSIG version 1 signature")
    i = 10
    pub, i = _read_string(b, i)
    ns, i = _read_string(b, i)
    res, i = _read_string(b, i)
    ha, i = _read_string(b, i)
    sg, i = _read_string(b, i)
    if i != len(b):
        raise SignatureError("trailing bytes after the signature")
    st, j = _read_string(sg, 0)
    raw, j = _read_string(sg, j)
    if st != b"ssh-ed25519" or len(raw) != 64 or j != len(sg):
        raise SignatureError("not an Ed25519 signature")
    return {"public_blob": pub, "namespace": ns, "reserved": res, "hash_alg": ha, "sig_raw": raw}


def signed_data(namespace, reserved, hash_alg, message):
    hf = {b"sha512": hashlib.sha512, b"sha256": hashlib.sha256}.get(hash_alg)
    if hf is None:
        raise SignatureError("unsupported signature hash %r" % hash_alg)
    return b"SSHSIG" + _string(namespace) + _string(reserved) + _string(hash_alg) + _string(hf(message).digest())


def verify_sshsig(text, message, namespace=NAMESPACE, trusted=()):
    """check an ssh-keygen -Y signature of message. trusted: iterable of 'ssh-ed25519 AAAA...' lines. -> the signer's fingerprint.
    Refuses (SignatureError): a malformed signature, another namespace, a key not in trusted, a signature that does not verify."""
    s = parse_sshsig(text)
    if s["namespace"] != namespace.encode("ascii"):
        raise SignatureError("the signature is for another purpose (namespace %r, expected %r)" % (s["namespace"].decode("ascii", "replace"), namespace))
    key = _ed25519_blob(s["public_blob"])
    fp = fingerprint(s["public_blob"])
    keys = {}
    for t in trusted:
        k, f = parse_public_key(t)
        keys[f] = k
    if fp not in keys or keys[fp] != key:
        raise SignatureError("signed by an UNKNOWN key %s (not one of the trusted keys in update_channel.json)" % fp)
    if not verify(key, signed_data(s["namespace"], s["reserved"], s["hash_alg"], message), s["sig_raw"]):
        raise SignatureError("BAD signature: the file was changed after signing, or the signature belongs to another file")
    return fp
