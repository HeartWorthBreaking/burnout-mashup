"""trackbuild.donor - the DONOR parts of a built track, read from YOUR OWN prepared game data (0.2.0).

trackbuild authors the geometry, collision, textures, unit table, PVS, LOD, route (S4), start grid (S1 page) and, when the
description asks for it, the traffic (S2 / S3). It does NOT author the Gamedata header / event records, enviro.dat (sky,
clouds, lighting environment) or the six audio files: those are copied from a retail "host" track, by default EU/M1_V1.

Where the game data comes from (first match wins; there is NO other fallback, in particular no developer workspace):
  1. the command-line option   --game-data DIR
  2. the environment variable  TRACKBUILD_GAME_DATA
  3. the environment variable  BMKIT_GAME_DATA        (the mod kit 0.4.1 setting, so one value serves every kit tool)
DIR is the folder of the prepared Burnout 3: Takedown (North America / NTSC-U, Xbox) data, the one that holds `Tracks`
(and normally default.xbe). Every donor file is checked against the SHA-256 below before anything is built, so a wrong
region / version, a modified file or a mod's replacement file is refused with the file named."""
import hashlib
import os

HOST_DEFAULT = "EU/M1_V1"
DONOR_FILES = ("enviro.dat", "SOUND.AWD", "CRASH1.RWS", "CRASH2.RWS", "CRASH3.RWS", "E_DJRACE.xwb", "MUSIC.RWS")
ENV_VARS = ("TRACKBUILD_GAME_DATA", "BMKIT_GAME_DATA")
NTSC_U_XBE_SHA256 = "9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9"   # the value Takedawn's setup checks

# retail NTSC-U files (sha256, size). The donor files are copied (Gamedata.bgd: header / records); the control files are
# read only by the retail-control tests (tests/test_trackbuild.py T3).
DONOR_PINS = {
    "EU/M1_V1": {
        "Gamedata.bgd": ("023da293b0bca9de01bcfe3d566aaef8abe9957262738e111515515ce0007a71", 2631680),
        "enviro.dat": ("124423cb1838a8f29d2eb38c888d5cef7101ebb963d51333dfb93c0d1938125b", 315392),
        "SOUND.AWD": ("ff61a7c908890977b3b08736a85c4739bf29eaa36c90ebbf5405f7df4f168b90", 575488),
        "CRASH1.RWS": ("cc94f4ecab7077e4df6b72a37455e556298e39af0d10ed2babffc4b1534371d1", 7735296),
        "CRASH2.RWS": ("1a4d2283fe0509822a672b8b0d4764a9bf93d6b4214482afa251efe86c40c098", 7735296),
        "CRASH3.RWS": ("e26e286fed4ac5255dc73a735839bc58c76abfb2573d2351f6479dfd47da0194", 14682112),
        "E_DJRACE.xwb": ("d49694b9bd68ffec7414f60465416f12c92e4dd30d49fe055148e3f9c0f8e2ac", 7919616),
        "MUSIC.RWS": ("9396c110f7c90c4804e5a89357281f4a41f1b3d0667faca2e4f3822faefc5696", 124),
    },
}
CONTROL_PINS = {
    "US/C3_V1": {"static.dat": ("7b21bd8ef3124e11d0d0ab7f85dcdd6cfbc955276238af8b3f58c89464a49045", 7503872),
                 "streamed.dat": ("dbb972af7c380d49aec7aa8fc582b3ebd3a0d0b6805cc90c514dd41352cdea3f", 5799936)},
    "EU/M1_V1": {"static.dat": ("9ae19a3b3791c1a57dcc749cbadf7545eed0256dc7bd789051ee1603702182c6", 12517376),
                 "streamed.dat": ("bfbae2c2a21750d986cf0d3277a904941bbc38a16c604376253bc2fa746f203d", 20254720)},
}
DOC = "docs/ADVANCED.md section 'Game data'"


class DonorError(Exception):
    """the game data is missing, incomplete or not the expected bytes; the message says what to do"""


def resolve(cli=None, env=None):
    """-> (absolute folder, where the value came from). Refuses with an actionable message; never guesses a location."""
    env = os.environ if env is None else env
    d, src = None, None
    if cli:
        d, src = cli, "--game-data"
    else:
        for k in ENV_VARS:
            if env.get(k):
                d, src = env[k], "the environment variable %s" % k
                break
    if not d:
        raise DonorError("this command needs YOUR OWN prepared game data (Burnout 3: Takedown, North America / NTSC-U, Xbox) for the "
                         "DONOR parts (Gamedata header / event records, enviro.dat, audio), and none was given. Give --game-data <folder> "
                         "(the folder that holds Tracks and default.xbe), or set TRACKBUILD_GAME_DATA (or the mod kit's "
                         "BMKIT_GAME_DATA). See %s." % DOC)
    d = os.path.abspath(os.path.expandvars(os.path.expanduser(d)))
    if not os.path.isdir(d):
        raise DonorError("the game-data folder %s (from %s) does not exist or is not a folder. Check the path (quote it if it has "
                         "spaces). See %s." % (d, src, DOC))
    if not os.path.isdir(os.path.join(d, "Tracks")):
        hint = ""
        try:
            subs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x, "Tracks")))
        except OSError:
            subs = []
        if subs:
            hint = " It has a subfolder %r that holds Tracks: give that folder instead." % subs[0]
        elif os.path.basename(d).lower() == "tracks":
            hint = " This looks like the Tracks folder itself: give its PARENT folder."
        raise DonorError("%s (from %s) has no Tracks folder, so it is not a prepared game-data folder.%s See %s." % (d, src, hint, DOC))
    xbe = os.path.join(d, "default.xbe")
    if os.path.isfile(xbe):
        h = _sha_file(xbe)
        if h != NTSC_U_XBE_SHA256:
            raise DonorError("%s has sha256 %s, not the North America (NTSC-U) retail default.xbe (%s). trackbuild, like Takedawn, "
                             "supports only that version; PAL / Japanese / patched data is refused. See %s." % (xbe, h, NTSC_U_XBE_SHA256, DOC))
    return d, src


def _sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _track_dir(root, tid):
    parts = tid.split("/")
    if len(parts) != 2 or not all(parts):
        raise DonorError("host %r is not a retail track ID of the form RR/NN_VN (e.g. EU/M1_V1)" % tid)
    return os.path.join(root, "Tracks", *parts)


def check_files(root, tid, pins, names, src="--game-data"):
    """-> {name: bytes}; every file present and (when pinned) equal to its pin"""
    tdir = _track_dir(root, tid)
    if not os.path.isdir(tdir):
        raise DonorError("the game data %s has no track folder Tracks\\%s, which trackbuild reads for %s. The data looks incomplete: "
                         "prepare it again (see %s)." % (root, tid.replace("/", "\\"), tid, DOC))
    out, bad = {}, []
    for n in names:
        p = os.path.join(tdir, n)
        if not os.path.isfile(p):
            bad.append("%s is missing" % n)
            continue
        b = open(p, "rb").read()
        pin = (pins or {}).get(n)
        if pin is not None:
            h = hashlib.sha256(b).hexdigest()
            if (h, len(b)) != pin:
                bad.append("%s has sha256 %s (%d bytes), expected %s (%d bytes)" % (n, h, len(b), pin[0], pin[1]))
                continue
        out[n] = b
    if bad:
        raise DonorError("the donor track %s in %s (from %s) is not the expected retail NTSC-U data: %s. Use the unmodified "
                         "North America data (no mod or patch applied to that folder); see %s." % (tid, root, src, "; ".join(bad), DOC))
    return out


def load_donor(game_data, host=HOST_DEFAULT, unpinned=False, env=None):
    """-> {"Gamedata.bgd": bytes, <DONOR_FILES>: bytes} of the host track, hash-checked"""
    root, src = resolve(game_data, env)
    pins = DONOR_PINS.get(host)
    if pins is None and not unpinned:
        raise DonorError("host %s has no pinned donor hashes in trackbuild %s (pinned: %s). Use the default host, or pass "
                         "--unpinned-donor to accept that track's files unchecked (labelled UNPINNED in BUILD_REPORT.json)."
                         % (host, _version(), ", ".join(sorted(DONOR_PINS))))
    return check_files(root, host, pins, ("Gamedata.bgd",) + DONOR_FILES, src)


def load_control(game_data, tid, env=None):
    root, src = resolve(game_data, env)
    return check_files(root, tid, CONTROL_PINS[tid], ("static.dat", "streamed.dat"), src)


def _version():
    from . import VERSION
    return VERSION
