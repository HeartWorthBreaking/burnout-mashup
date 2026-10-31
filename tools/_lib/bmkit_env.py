"""bmkit_env - mod kit 0.4.1: explicit configuration and prerequisite discovery shared by every kit tool.

Nothing here falls back to a developer workspace. Every location is either package-relative (the kit's own folders) or given
by the user, in this order (first match wins):
  1. the tool's command-line option            (--game-data DIR, --cc FILE, ...)
  2. an environment variable                   (BMKIT_GAME_DATA, BMKIT_CC, BMKIT_LLVM_MINGW)
  3. the kit configuration file                (BMKIT_CONFIG=<file>, else <kit>\\bmkit.toml when it exists; see bmkit.example.toml)
  4. for programs only: the PATH               (x86_64-w64-mingw32-clang.exe)
When none gives a value the tool stops with an error that says what is missing and how to provide it (BmkitError).

Game data: YOUR OWN prepared Burnout 3: Takedown, North America (NTSC-U) retail Xbox data, as Takedawn installs it (docs\\GAME_DATA.md).
The tools only ever READ it. It is recognised by the SHA-256 of default.xbe (the value Takedawn's setup checks)."""
import hashlib
import os
import shutil
import sys

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(KIT_ROOT, 'tools')
VENDOR = os.path.join(TOOLS, '_vendor')
HOST_READERS = os.path.join(TOOLS, 'bmpack', 'host_readers')
KIT_VERSION = '0.7.0'
MIN_PYTHON = (3, 11)

NTSC_U_XBE_SHA256 = '9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9'
DOC_GAME_DATA = r'docs\GAME_DATA.md'
DOC_PREREQ = r'docs\PREREQUISITES.md'
LLVM_MINGW_HINT = ('llvm-mingw 20260922 (UCRT, x86_64): https://github.com/mstorsjo/llvm-mingw/releases/tag/20260922, file '
                   'llvm-mingw-20260922-ucrt-x86_64.zip (sha256 e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666)')


class BmkitError(Exception):
    """a configuration / prerequisite problem: the message says what is wrong and what to do"""


def add_vendor_path():
    """put the kit's vendored readers (tools\\_vendor) first on sys.path - package-relative, never a workspace"""
    if VENDOR not in sys.path:
        sys.path.insert(0, VENDOR)


def check_python(version=None):
    v = tuple(version or sys.version_info[:2])
    if v < MIN_PYTHON:
        raise BmkitError('Python %d.%d found; the kit tools need Python %d.%d or later (tomllib). Install it from python.org and run '
                         'the tool with that interpreter (py -3.12 ...). See %s.' % (v[0], v[1], MIN_PYTHON[0], MIN_PYTHON[1], DOC_PREREQ))


# ------------------------------------------------------------------------------------------------------------- config file
_CFG = None


def config_path(env=None):
    env = os.environ if env is None else env
    p = env.get('BMKIT_CONFIG')
    if p:
        if not os.path.isfile(p):
            raise BmkitError('BMKIT_CONFIG names %s, which is not a file. Fix the variable or remove it.' % p)
        return p
    p = os.path.join(KIT_ROOT, 'bmkit.toml')
    return p if os.path.isfile(p) else None


def config(env=None, reload=False):
    global _CFG
    if _CFG is not None and not reload and env is None:
        return _CFG
    import tomllib
    p = config_path(env)
    c = {}
    if p:
        try:
            with open(p, 'rb') as f:
                c = tomllib.load(f).get('paths', {})
        except (OSError, ValueError) as e:
            raise BmkitError('cannot read the kit configuration %s: %s. Fix the file (see bmkit.example.toml) or remove it.' % (p, e))
        if not isinstance(c, dict):
            raise BmkitError('%s: [paths] must be a table (see bmkit.example.toml)' % p)
    if env is None:
        _CFG = c
    return c


def _pick(cli, env_name, cfg_key, env=None):
    env = os.environ if env is None else env
    if cli:
        return cli, 'the command line'
    if env.get(env_name):
        return env[env_name], 'the environment variable %s' % env_name
    c = config(env if env is not os.environ else None)
    if c.get(cfg_key):
        return str(c[cfg_key]), 'the kit configuration (%s, [paths] %s)' % (config_path(env), cfg_key)
    return None, None


# --------------------------------------------------------------------------------------------------------------- game data
_VERIFIED = {}


def _sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def game_data(cli=None, need=(), env=None, what='this command'):
    """-> the user's prepared game-data folder (absolute). Refuses with an actionable message when it is not given, not a
    folder, not the NTSC-U data, or lacks a file `need` lists (relative paths, case-insensitive on Windows)."""
    d, src = _pick(cli, 'BMKIT_GAME_DATA', 'game_data', env)
    if not d:
        raise BmkitError('%s needs YOUR OWN prepared game data (Burnout 3: Takedown, NTSC-U Xbox), and none was given. Give '
                         '--game-data <folder> (the folder with default.xbe, Tracks, Data, pveh), or set BMKIT_GAME_DATA, or '
                         'game_data in bmkit.toml. How to prepare it: %s.' % (what, DOC_GAME_DATA))
    d = os.path.abspath(os.path.expandvars(os.path.expanduser(d)))
    if not os.path.isdir(d):
        raise BmkitError('the game-data folder %s (from %s) does not exist or is not a folder. Check the path; see %s.' % (d, src, DOC_GAME_DATA))
    xbe = os.path.join(d, 'default.xbe')
    if not os.path.isfile(xbe):
        hint = ''
        for sub in ('Burnout 3 Takedown', 'Game'):
            if os.path.isfile(os.path.join(d, sub, 'default.xbe')):
                hint = ' It has a subfolder "%s" with default.xbe: give that folder instead.' % sub
        raise BmkitError('%s (from %s) has no default.xbe, so it is not a prepared game-data folder.%s See %s.' % (d, src, hint, DOC_GAME_DATA))
    if d not in _VERIFIED:
        h = _sha256(xbe)
        if h != NTSC_U_XBE_SHA256:
            raise BmkitError('%s\\default.xbe has sha256 %s, not the North America (NTSC-U) retail one (%s). The kit, like Takedawn, '
                             'supports only that version; PAL / Japanese / patched data is refused. See %s.' % (d, h, NTSC_U_XBE_SHA256, DOC_GAME_DATA))
        _VERIFIED[d] = h
    missing = [n for n in need if not os.path.exists(os.path.join(d, n))]
    if missing:
        raise BmkitError('the game data %s lacks %s, which %s reads. The install looks incomplete: run Takedawn\'s setup again '
                         '(it checks every file) or check the folder; see %s.' % (d, ', '.join(missing), what, DOC_GAME_DATA))
    return d


# ---------------------------------------------------------------------------------------------------------------- toolchain
CC_NAME = 'x86_64-w64-mingw32-clang.exe' if os.name == 'nt' else 'x86_64-w64-mingw32-clang'


def find_cc(cli=None, env=None, what='this command'):
    """-> path of llvm-mingw's x86_64-w64-mingw32-clang (bmpack validate compiles the host readers with it)"""
    env_ = os.environ if env is None else env
    v, src = _pick(cli, 'BMKIT_CC', 'cc', env)
    if v:
        if not os.path.isfile(v):
            raise BmkitError('the compiler %s (from %s) does not exist. Point it at llvm-mingw\'s bin\\%s; get %s.' % (v, src, CC_NAME, LLVM_MINGW_HINT))
        return os.path.abspath(v)
    root, src = _pick(None, 'BMKIT_LLVM_MINGW', 'llvm_mingw', env)
    if root:
        p = os.path.join(root, 'bin', CC_NAME)
        if not os.path.isfile(p):
            raise BmkitError('%s (from %s) is not an llvm-mingw folder: no bin\\%s in it. Get %s.' % (root, src, CC_NAME, LLVM_MINGW_HINT))
        return os.path.abspath(p)
    p = shutil.which(CC_NAME, path=env_.get('PATH', ''))
    if p:
        return os.path.abspath(p)
    raise BmkitError('%s needs the llvm-mingw C compiler (%s) and none was found: give --cc <file>, or set BMKIT_LLVM_MINGW=<llvm-mingw '
                     'folder>, or add its bin folder to PATH. Get %s. See %s.' % (what, CC_NAME, LLVM_MINGW_HINT, DOC_PREREQ))


def host_readers(cli=None, env=None):
    """-> the host-readers source package (default: <kit>\\tools\\bmpack\\host_readers, shipped with the kit)"""
    v, src = _pick(cli, 'BMKIT_HOST_READERS', 'host_readers', env)
    d = os.path.abspath(v) if v else HOST_READERS
    if not os.path.isfile(os.path.join(d, 'HOST_READERS.json')):
        raise BmkitError('no host-readers package at %s (HOST_READERS.json missing)%s. The kit ships it as <kit>\\tools\\bmpack\\host_readers; '
                         'unpack the whole kit zip again.' % (d, (' (from %s)' % src) if v else ''))
    return d


def report_error(tool, e):
    """the one format every kit tool prints for a BmkitError (exit code 3 = configuration / prerequisite problem)"""
    sys.stderr.write('%s: CANNOT RUN: %s\n' % (tool, e))
    return 3
