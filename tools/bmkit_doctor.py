"""bmkit_doctor 0.1.0 (mod kit 0.4.1) - prerequisite report: what is installed, what is missing, and what to do about it.
Read only; starts no game. Configuration as every kit tool (tools\\_lib\\bmkit_env.py): options > BMKIT_* variables > bmkit.toml > PATH.

    py -3 -B tools\\bmkit_doctor.py [--game-data DIR] [--cc FILE] [--cmake FILE] [--ninja FILE] [--host DIR] [--for WHAT]
--for  all (default) | plugins (SDK build: llvm-mingw, cmake, ninja) | tools (python, game data, llvm-mingw for bmpack validate)
       | host (a host folder: exe, SDL2.dll, the Vulkan loader)
Exit 0 = everything needed for --for is present; 3 = something is missing (each MISSING line says how to fix it)."""
import argparse
import hashlib
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '_lib'))
import bmkit_env as E  # noqa: E402

VERSION = '0.1.0'
SDL2_HINT = 'SDL2.dll 2.32.10 (x64) must sit beside the host exe: it comes with the tester bundle, or SDL2-devel-2.32.10-mingw.tar.gz ' \
            '(x86_64-w64-mingw32\\bin\\SDL2.dll) from https://github.com/libsdl-org/SDL/releases/tag/release-2.32.10'
VULKAN_HINT = 'the Vulkan loader (vulkan-1.dll in Windows\\System32) comes with your GPU driver: install / update the AMD, NVIDIA or ' \
              'Intel driver (Vulkan 1.2 or later)'


def check(rows, need, name, fn):
    try:
        rows.append(('OK', name, fn(), None))
    except E.BmkitError as e:
        rows.append(('MISSING' if need else 'NOT SET', name, None, str(e)))


def find_prog(cli, exe, hint):
    if cli:
        if not os.path.isfile(cli):
            raise E.BmkitError('%s does not exist; %s' % (cli, hint))
        return os.path.abspath(cli)
    p = shutil.which(exe)
    if not p:
        raise E.BmkitError('%s is not on PATH; %s' % (exe, hint))
    return p


def host_folder(d, system32=None):
    if not d or not os.path.isdir(d):
        raise E.BmkitError('%s is not a folder: give the folder holding the host exe' % d)
    exes = sorted(n for n in os.listdir(d) if n.lower().startswith('burnout3') and n.lower().endswith('.exe'))
    if not exes:
        raise E.BmkitError('no burnout3*.exe in %s: give the host folder of the tester bundle (host\\)' % d)
    if not os.path.isfile(os.path.join(d, 'SDL2.dll')):
        raise E.BmkitError('SDL2.dll is missing in %s. %s' % (d, SDL2_HINT))
    s32 = system32 or os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    if not os.path.isfile(os.path.join(s32, 'vulkan-1.dll')):
        raise E.BmkitError('no Vulkan loader (%s\\vulkan-1.dll): %s' % (s32, VULKAN_HINT))
    h = hashlib.sha256(open(os.path.join(d, exes[0]), 'rb').read()).hexdigest()
    return '%s (sha256 %s), SDL2.dll present, Vulkan loader present' % (exes[0], h[:12])


def main(argv=None):
    ap = argparse.ArgumentParser(prog='bmkit_doctor')
    ap.add_argument('--game-data'); ap.add_argument('--cc'); ap.add_argument('--cmake'); ap.add_argument('--ninja')
    ap.add_argument('--host'); ap.add_argument('--system32', help=argparse.SUPPRESS)
    ap.add_argument('--for', dest='what', default='all', choices=('all', 'plugins', 'tools', 'host'))
    a = ap.parse_args(argv)
    w = a.what
    rows = []
    check(rows, True, 'python', lambda: (E.check_python(), '%d.%d.%d at %s' % (sys.version_info[:3] + (sys.executable,)))[1])
    if w in ('all', 'plugins', 'tools'):
        check(rows, True, 'llvm-mingw clang', lambda: E.find_cc(a.cc, what='plugin builds and bmpack validate'))
    if w in ('all', 'plugins'):
        check(rows, True, 'cmake', lambda: find_prog(a.cmake, 'cmake.exe', 'install CMake 3.20+ (4.4.4 used) and put it on PATH or give --cmake'))
        check(rows, True, 'ninja', lambda: find_prog(a.ninja, 'ninja.exe', 'install Ninja (1.13.2 used) and put it on PATH or give --ninja'))
    if w in ('all', 'tools'):
        given = a.game_data or os.environ.get('BMKIT_GAME_DATA') or E.config().get('game_data')
        check(rows, w == 'tools' or bool(given), 'game data (NTSC-U)',
              lambda: E.game_data(a.game_data, need=('Tracks/tlist.bin', 'Data/PrgData.bin', 'pveh/vlist.bin'), what='the kit tools'))
    if w in ('all', 'host') and (a.host or w == 'host'):
        check(rows, True, 'host folder', lambda: host_folder(a.host, a.system32))
    print('bmkit_doctor %s (mod kit %s), checking for: %s' % (VERSION, E.KIT_VERSION, w))
    for st, name, val, why in rows:
        print('%-8s %-20s %s' % (st, name, val if st == 'OK' else why))
    missing = [r for r in rows if r[0] == 'MISSING']
    print('RESULT %s' % ('READY' if not missing else 'MISSING %d (see the lines above; docs\\PREREQUISITES.md)' % len(missing)))
    return 3 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
