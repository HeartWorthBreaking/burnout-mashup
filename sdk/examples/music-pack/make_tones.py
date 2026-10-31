r"""make_tones.py - bmashup-sdk example (q): write the two music-pack mods with their audio, generated here.
    py -3 -B make_tones.py <out folder>        (the folder must not exist)
Writes <out>\bmashup-test-tones\{mod.toml, music\tone_440.wav, music\tone_1000.wav} and
<out>\bmashup-test-tones-remix\{mod.toml, music\tone_523.wav}. Original synthetic sine tones - no recorded audio: 90 s,
44.1 kHz, 16-bit stereo PCM, -9 dBFS peak, 20 ms fade in / out. Deterministic (the same bytes every run; the generator is the
gp music1 slice's make_music1_pack.py tone function, unchanged). The mod.toml files are copied from tones\ and remix\.
"""
import hashlib, math, pathlib, struct, sys

RATE, SECS, AMP = 44100, 90, 10 ** (-9 / 20)
HERE = pathlib.Path(__file__).resolve().parent


def tone(freq):
    n = RATE * SECS
    fade = int(RATE * 0.02)
    frames = bytearray()
    for i in range(n):
        g = min(1.0, i / fade, (n - 1 - i) / fade)
        v = int(round(32767 * AMP * g * math.sin(2 * math.pi * freq * i / RATE)))
        frames += struct.pack('<hh', v, v)
    hdr = b'RIFF' + struct.pack('<I', 36 + len(frames)) + b'WAVE' + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 2, RATE, RATE * 4, 4, 16)
    return hdr + b'data' + struct.pack('<I', len(frames)) + bytes(frames)


if len(sys.argv) != 2:
    sys.exit(__doc__)
out = pathlib.Path(sys.argv[1]).resolve()
if out.exists():
    sys.exit('%s exists: give a NEW folder' % out)
files = {
    'bmashup-test-tones/mod.toml': (HERE / 'tones' / 'mod.toml').read_bytes(),
    'bmashup-test-tones/music/tone_440.wav': tone(440.0),
    'bmashup-test-tones/music/tone_1000.wav': tone(1000.0),
    'bmashup-test-tones-remix/mod.toml': (HERE / 'remix' / 'mod.toml').read_bytes(),
    'bmashup-test-tones-remix/music/tone_523.wav': tone(523.25),
}
for rel, b in files.items():
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    print(hashlib.sha256(b).hexdigest(), len(b), rel)
