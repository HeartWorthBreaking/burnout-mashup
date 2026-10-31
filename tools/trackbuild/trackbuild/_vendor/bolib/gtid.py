"""GtID: Criterion's 8-byte packed string (<=12 chars, base-40 alphabet).
Algorithm from EdnessP/scripts burnout/GtID.py (reimplementation of the
games' GtIDCompress / GtIDUnCompress)."""
CHARS = " -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"


def decode(value, length=12):
    s = ""
    for _ in range(length):
        s += CHARS[value % 40]
        value //= 40
    return s[::-1].strip()


def encode(text, length=12):
    res = 0
    for i, ch in enumerate(text.upper().ljust(length)[::-1]):
        res += CHARS.index(ch) * 40 ** i
    return res


def plausible(value):
    """Heuristic: does this u64 look like a real GtID name?"""
    if value == 0 or value >= 40 ** 12:
        return None
    s = decode(value)
    if len(s) < 2 or "  " in s or not any(c.isalpha() for c in s):
        return None
    return s
