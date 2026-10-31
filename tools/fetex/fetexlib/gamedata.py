"""bmgamedata 2 - where carimport / fetex / vehtool read YOUR prepared game data from (one file, byte-identical in all three).

Location (never a default, never a search of other folders):
  * inside mod kit 0.4.1 (the tool at <kit>\\tools\\<tool>\\): the kit's shared resolver tools\\_lib\\bmkit_env.py decides -
    --game-data DIR > environment variable BMKIT_GAME_DATA > <kit>\\bmkit.toml [paths] game_data (or BMKIT_CONFIG); the folder
    must hold the North America (NTSC-U) default.xbe;
  * a tool folder used on its own: the same rules without the kit configuration file (--game-data DIR > BMKIT_GAME_DATA).
Every file is then read through GameData.read(), which checks its sha256 and size against GAMEDATA_SHA256.json (shipped beside
the tool): a missing, modified or other-release file is refused with a message that says what to do. Nothing is written.
Pure Python 3 standard library.
"""
import hashlib
import importlib.util
import json
import os

ENV = 'BMKIT_GAME_DATA'
REF_NAME = 'GAMEDATA_SHA256.json'
DOC = 'the README section "Game data" (kit: docs\\GAME_DATA.md)'
GIVE = ('Give --game-data <folder> (the folder with default.xbe, Data and pveh) or set %s (in the mod kit also game_data in '
        'bmkit.toml). How to prepare it: %s.' % (ENV, DOC))


class GameDataError(Exception):
    """missing / wrong / modified game data, or an incomplete tool installation; the message says what to do"""


_HERE = os.path.dirname(os.path.abspath(__file__))
_REF = None
_KIT = []


def _ref_path():
    for d in (_HERE, os.path.dirname(_HERE)):
        p = os.path.join(d, REF_NAME)
        if os.path.isfile(p):
            return p
    return None


def reference():
    global _REF
    if _REF is None:
        p = _ref_path()
        if not p:
            raise GameDataError('installation incomplete: %s is missing beside the tool. Copy the whole tool folder again '
                                '(SHA256SUMS.txt lists every file).' % REF_NAME)
        try:
            with open(p, 'rb') as f:
                _REF = json.loads(f.read().decode('utf-8'))['files']
        except (OSError, ValueError, KeyError) as e:
            raise GameDataError('installation damaged: %s unreadable (%s). Copy the tool folder again.' % (p, e))
    return _REF


def kit_env():
    """the mod kit's bmkit_env module when this tool sits in <kit>\\tools\\<tool>\\ (package-relative), else None"""
    if not _KIT:
        mod = None
        for d in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
            p = os.path.join(d, '_lib', 'bmkit_env.py')
            if os.path.isfile(p):
                spec = importlib.util.spec_from_file_location('bmkit_env', p)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                break
        _KIT.append(mod)
    return _KIT[0]


def _child_ci(d, name):
    try:
        names = os.listdir(d)
    except OSError:
        return None
    for n in names:
        if n.lower() == name.lower():
            return os.path.join(d, n)
    return None


def _find_ci(root, rel):
    p = root
    for part in rel.replace('\\', '/').split('/'):
        p = _child_ci(p, part)
        if p is None:
            return None
    return p


class GameData:
    def __init__(self, root, source):
        self.root = root
        self.source = source

    def path(self, rel):
        """actual path of a game-data file (case-insensitive lookup) or None; does not check the hash"""
        p = _find_ci(self.root, rel)
        return p if p and os.path.isfile(p) else None

    def exists(self, rel):
        return self.path(rel) is not None

    def read(self, rel):
        """the file's bytes, verified against the reference table; GameDataError otherwise"""
        key = rel.replace('\\', '/').lower()
        ref = reference().get(key)
        p = self.path(rel)
        if p is None:
            raise GameDataError('the game data %s lacks %s. The preparation looks incomplete: prepare it again (every file is '
                                'checked) or check the folder; see %s.' % (self.root, rel, DOC))
        if ref is None:
            raise GameDataError('%s is not a file of the supported game release (not in %s)' % (rel, REF_NAME))
        with open(p, 'rb') as f:
            b = f.read()
        h = hashlib.sha256(b).hexdigest()
        if len(b) != ref['size'] or h != ref['sha256']:
            raise GameDataError('game data file %s differs from the supported release (sha256 %s..., %d bytes; expected %s..., '
                                '%d bytes). Use an unmodified preparation of Burnout 3: Takedown, North America (NTSC-U) Xbox; '
                                'never install mods into the game data folder. See %s.' % (p, h[:16], len(b), ref['sha256'][:16],
                                                                                          ref['size'], DOC))
        return b

    def describe(self):
        return '%s (from %s)' % (self.root, self.source)


def resolve(arg=None, need=(), what='this command'):
    """GameData from the kit resolver (in a kit) or the same rules stand-alone; GameDataError with instructions otherwise"""
    reference()
    kit = kit_env()
    if kit is not None:
        try:
            root = kit.game_data(arg, need=need, what=what)
        except kit.BmkitError as e:
            raise GameDataError(str(e))
        return GameData(root, 'the mod kit configuration (tools\\_lib\\bmkit_env.py)')
    src = 'the command line'
    if not arg:
        arg = os.environ.get(ENV, '')
        src = 'the environment variable %s' % ENV
    if not arg:
        raise GameDataError('%s needs YOUR OWN prepared game data (Burnout 3: Takedown, NTSC-U Xbox), and none was given. %s'
                            % (what, GIVE))
    root = os.path.abspath(os.path.expandvars(os.path.expanduser(arg)))
    if not os.path.isdir(root):
        raise GameDataError('the game-data folder %s (from %s) does not exist or is not a folder. Check the path; see %s.'
                            % (root, src, DOC))
    if not os.path.isfile(os.path.join(root, 'default.xbe')):
        hint = ''
        for sub in ('Burnout 3 Takedown', 'Game'):
            if os.path.isfile(os.path.join(root, sub, 'default.xbe')):
                hint = ' It has a subfolder "%s" with default.xbe: give that folder instead.' % sub
        raise GameDataError('%s (from %s) has no default.xbe, so it is not a prepared game-data folder.%s See %s.'
                            % (root, src, hint, DOC))
    gd = GameData(root, src)
    try:
        gd.read('default.xbe')
    except GameDataError:
        raise GameDataError('%s\\default.xbe is not the North America (NTSC-U) retail one. The tools, like Takedawn, support '
                            'only that version; PAL / Japanese / patched data is refused. See %s.' % (root, DOC))
    missing = [n for n in need if not gd.exists(n)]
    if missing:
        raise GameDataError('the game data %s lacks %s, which %s reads. The preparation looks incomplete; see %s.'
                            % (root, ', '.join(missing), what, DOC))
    return gd
