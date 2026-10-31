"""Error-path tests of the mod kit 0.4.1 shared configuration (bmkit_env), bmkit_doctor and bmpack 1.3.4: every missing
prerequisite, invalid path, unsupported input and absent / wrong game data must stop with an ACTIONABLE message (what is wrong,
what to do) and the documented exit code (3 = configuration / prerequisite, 1 = refused input, 2 = usage). No game data needed
(fake folders); with --game-data DIR the real-data cases run too.
    py -3 -B test_errors.py OUT_DIR [--game-data DIR]"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(TOOLS, '_lib'))
import bmkit_env as E  # noqa: E402

RES = []


def check(ok, what):
    RES.append(('PASS ' if ok else 'FAIL ') + what)


def raises(fn, *needles):
    try:
        fn()
    except E.BmkitError as e:
        m = str(e)
        return all(n.lower() in m.lower() for n in needles), m
    return False, 'no error raised'


def w(p, b=b''):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(b)


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('BMKIT_', 'BMPACK_', 'TAKEDAWN', 'BMASHUP'))}
    env['PATH'] = os.path.dirname(sys.executable) + os.pathsep + os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    env.update(extra)
    return env


def run(args, env):
    r = subprocess.run([sys.executable, '-B'] + args, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def main(out, real_game=None):
    os.makedirs(out)
    fake = os.path.join(out, 'fake_game')
    w(os.path.join(fake, 'default.xbe'), b'not the retail xbe')
    w(os.path.join(fake, 'Tracks', 'tlist.bin'), b'x')
    nested = os.path.join(out, 'nested')
    w(os.path.join(nested, 'Burnout 3 Takedown', 'default.xbe'), b'not the retail xbe')
    env0 = {}                                     # an empty environment for the in-process cases
    # ---- Python
    ok, m = raises(lambda: E.check_python((3, 8)), '3.11', 'python.org')
    check(ok, 'python 3.8 refused with the version needed and where to get it: %s' % m[:120])
    check(E.check_python((3, 11)) is None, 'python 3.11 accepted')
    # ---- game data
    ok, m = raises(lambda: E.game_data(None, env=env0), '--game-data', 'GAME_DATA.md')
    check(ok, 'no game data given: says how to give it and where the preparation is documented')
    ok, m = raises(lambda: E.game_data(os.path.join(out, 'nope'), env=env0), 'does not exist')
    check(ok, 'a game-data path that does not exist is named')
    ok, m = raises(lambda: E.game_data(os.path.join(out), env=env0), 'no default.xbe')
    check(ok, 'a folder without default.xbe is refused')
    ok, m = raises(lambda: E.game_data(nested, env=env0), 'Burnout 3 Takedown', 'give that folder')
    check(ok, 'the parent of "Burnout 3 Takedown" given: the message points at the right folder')
    ok, m = raises(lambda: E.game_data(fake, env=env0), 'NTSC-U', E.NTSC_U_XBE_SHA256[:12])
    check(ok, 'non-NTSC-U / patched default.xbe refused with both hashes')
    saved = E.NTSC_U_XBE_SHA256
    E.NTSC_U_XBE_SHA256 = hashlib.sha256(b'not the retail xbe').hexdigest()     # accept the fake for the next cases
    E._VERIFIED.clear()
    try:
        check(E.game_data(fake, env=env0) == os.path.abspath(fake), 'an accepted game-data folder is returned absolute')
        ok, m = raises(lambda: E.game_data(fake, need=('Data/PrgData.bin',), env=env0, what='bmpack validate'), 'Data/PrgData.bin',
                       'bmpack validate', 'setup again')
        check(ok, 'a file the command reads is missing: named, with the command and the fix')
        check(E.game_data(None, env={'BMKIT_GAME_DATA': fake}) == os.path.abspath(fake), 'BMKIT_GAME_DATA is used when no option')
        cfg = os.path.join(out, 'cfg.toml')
        w(cfg, ('[paths]\ngame_data = %r\n' % fake).replace("'", '"').replace('\\', '\\\\').encode())
        check(E.game_data(None, env={'BMKIT_CONFIG': cfg}) == os.path.abspath(fake), 'bmkit.toml [paths] game_data is used')
    finally:
        E.NTSC_U_XBE_SHA256 = saved
        E._VERIFIED.clear()
    ok, m = raises(lambda: E.config(env={'BMKIT_CONFIG': os.path.join(out, 'missing.toml')}), 'not a file')
    check(ok, 'BMKIT_CONFIG naming a missing file is refused')
    bad = os.path.join(out, 'bad.toml')
    w(bad, b'[paths\ngame_data = 1\n')
    ok, m = raises(lambda: E.config(env={'BMKIT_CONFIG': bad}), 'cannot read', 'bmkit.example.toml')
    check(ok, 'a malformed bmkit.toml is refused with the file named')
    # ---- toolchain
    ok, m = raises(lambda: E.find_cc(None, env={'PATH': out}), 'llvm-mingw', 'releases', '--cc')
    check(ok, 'no compiler anywhere: says what to download (URL + sha256) and how to point at it')
    ok, m = raises(lambda: E.find_cc(os.path.join(out, 'clang.exe'), env={}), 'does not exist')
    check(ok, 'a --cc file that does not exist is refused')
    ok, m = raises(lambda: E.find_cc(None, env={'BMKIT_LLVM_MINGW': out, 'PATH': ''}), 'not an llvm-mingw folder')
    check(ok, 'BMKIT_LLVM_MINGW naming a non-llvm-mingw folder is refused')
    ok, m = raises(lambda: E.host_readers(out, env={}), 'HOST_READERS.json', 'unpack')
    check(ok, 'a missing host-readers package is refused with the fix')
    # ---- bmkit_doctor (subprocess, minimal PATH)
    doc = os.path.join(TOOLS, 'bmkit_doctor.py')
    rc, o = run([doc, '--for', 'plugins'], clean_env())
    check(rc == 3 and 'MISSING' in o and 'llvm-mingw' in o and 'cmake' in o.lower(), 'doctor --for plugins without a toolchain: exit 3, '
          'each missing tool named: rc %d' % rc)
    host = os.path.join(out, 'host')
    w(os.path.join(host, 'burnout3_gp_p4_4.exe'), b'MZ')
    rc, o = run([doc, '--for', 'host', '--host', host], clean_env())
    check(rc == 3 and 'SDL2.dll is missing' in o and 'release-2.32.10' in o, 'doctor: SDL2.dll missing beside the host exe named with its source')
    w(os.path.join(host, 'SDL2.dll'), b'MZ')
    s32 = os.path.join(out, 'sys32')
    os.makedirs(s32)
    rc, o = run([doc, '--for', 'host', '--host', host, '--system32', s32], clean_env())
    check(rc == 3 and 'Vulkan loader' in o and 'driver' in o, 'doctor: no Vulkan loader -> the GPU driver is named as the fix')
    w(os.path.join(s32, 'vulkan-1.dll'), b'MZ')
    rc, o = run([doc, '--for', 'host', '--host', host, '--system32', s32], clean_env())
    check(rc == 0 and 'READY' in o, 'doctor: a complete host folder is READY')
    rc, o = run([doc, '--for', 'tools', '--game-data', fake], clean_env())
    check(rc == 3 and 'NTSC-U' in o, 'doctor --for tools with wrong game data: exit 3, the version problem named')
    # ---- bmpack 1.3.4 (subprocess, minimal PATH, no configuration)
    bm = os.path.join(TOOLS, 'bmpack', 'bmpack.py')
    mod = os.path.join(out, 'mods', 'm1')
    w(os.path.join(mod, 'mod.toml'), b'id = "bmashup.t-err"\nname = "t"\nversion = "1.0"\n')
    rc, o = run([bm, 'validate', os.path.dirname(mod)], clean_env())
    check(rc == 3 and 'CANNOT RUN' in o and '--game-data' in o, 'bmpack validate without game data: exit 3, says how to give it')
    rc, o = run([bm, 'validate', os.path.dirname(mod), '--game-data', fake], clean_env())
    check(rc == 3 and 'NTSC-U' in o, 'bmpack validate with non-NTSC-U data: exit 3')
    rc, o = run([bm, 'validate', os.path.join(out, 'no_such_root'), '--game-data', fake], clean_env())
    check(rc == 1 and 'is not a folder' in o, 'bmpack validate of a missing folder: refused, the folder named')
    rc, o = run([bm, 'validate', '--game-data'], clean_env())
    check(rc == 2 and 'needs a value' in o, 'bmpack: an option without its value is a usage error')
    spec = os.path.join(out, 'bad_spec.toml')
    w(spec, b'[mod]\nid = "bmashup.t-bad"\nversion = "1.0"\nname = "bad"\n\n[[track]]\nid = "US-C8-V1"\ndonor = "US_C1_V1"\nname = "x"\nlocation = "X"\n')
    rc, o = run([bm, 'build', spec, os.path.join(out, 'bad_out'), '--no-validate'], clean_env())
    check(rc == 1 and 'REFUSED' in o and 'US-C8-V1' in o, 'bmpack build of an unsupported track id: refused with the id named')
    rc, o = run([bm, 'verify', os.path.join(out, 'mods')], clean_env())
    check(rc == 1 and 'bmpack.json' in o, 'bmpack verify of a folder without bmpack.json: refused, not a traceback')
    if real_game:
        rc, o = run([bm, 'validate', os.path.dirname(mod), '--game-data', real_game], clean_env())
        check(rc == 3 and 'llvm-mingw' in o and 'releases' in o, 'bmpack validate with real data but no compiler: exit 3, download named')
        sp2 = os.path.join(out, 'nodonor.toml')
        w(sp2, b'[mod]\nid = "bmashup.t-nodonor"\nversion = "1.0"\nname = "nd"\n\n[[track]]\nid = "US_C8_V1"\ndonor = "US_Z9_V1"\nname = "x"\nlocation = "X"\n')
        rc, o = run([bm, 'build', sp2, os.path.join(out, 'nd_out'), '--no-validate', '--game-data', real_game], clean_env())
        check(rc == 1 and 'US_Z9_V1' in o and 'retail track' in o, 'bmpack build with a donor track not in the game data: the asset is named')
    fails = sum(1 for r in RES if r.startswith('FAIL'))
    RES.append('RESULT %s (%d checks, %d failed)' % ('PASS' if not fails else 'FAIL', len(RES), fails))
    with open(os.path.join(out, 'RESULTS.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(RES) + '\n')
    print('\n'.join(RES))
    return 1 if fails else 0


if __name__ == '__main__':
    g = sys.argv[sys.argv.index('--game-data') + 1] if '--game-data' in sys.argv else None
    sys.exit(main(sys.argv[1], g))
