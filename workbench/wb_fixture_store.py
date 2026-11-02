"""wb_fixture_store - TEST-SESSION store of immutable kit build outputs (RTA4 suite optimisation). OFF unless the environment
variable WB_TEST_FIXTURE_STORE names a folder (set only by tests\\run_tests.py for the suites in test_deps.json "fixture_store";
never by the GUI / CLI). WB_TEST_FIXTURE_COLD=1 forces it off (cold-build / invalidation tests).

What is stored: the files `tb.py build` wrote (static.dat, streamed.dat, Gamedata.bgd, ..., BUILD_REPORT.json with the source
folder replaced by a placeholder). Never stored: validation results, package outputs, verdicts - `tb.py validate` / `package` /
bmpack always run on the restored bytes.
Key = sha256 of: schema, the bound trackbuild TREE hash (every file of the kit tool folder), the Python version the kit reports,
the exact input files (sha256 per relative path), the build argv with the attempt-specific folders replaced, and the sha256 of
every file of the donor track folder the kit reads (game data). Any change -> another key -> a real build.
Restore: every file re-hashed against the entry's MANIFEST; any mismatch -> the entry is moved aside (*.corrupt, kept) and a real
build runs. Entries are written to <key>.tmp_<pid> and renamed (atomic); a racing writer's entry is kept, never overwritten."""
import hashlib
import json
import os
import shutil

SCHEMA = 'wb-fixture-store/1'
SRC_TOKEN = '<WB_FIXTURE_SRC>'


def enabled():
    d = os.environ.get('WB_TEST_FIXTURE_STORE')
    return d if d and os.environ.get('WB_TEST_FIXTURE_COLD') != '1' else None


def _sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def donor_hashes(game_data, host='EU/M1_V1'):
    root = game_data
    for cand in (os.path.join(game_data, 'Tracks', *host.split('/')),):
        if os.path.isdir(cand):
            return {n: _sha(os.path.join(cand, n)) for n in sorted(os.listdir(cand)) if os.path.isfile(os.path.join(cand, n))}
    return {'missing': root}


def usage(store, event, k, note=''):
    """one line per event in <store>/USAGE.jsonl (the runner counts hits / misses per run)"""
    import time
    try:
        os.makedirs(store, exist_ok=True)
        with open(os.path.join(store, 'USAGE.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps({'t': round(time.time(), 3), 'event': event, 'key': k[:16], 'pid': os.getpid(),
                                'suite': os.environ.get('WB_TEST_SUITE'), 'note': note[:200]}) + chr(10))
    except OSError:
        pass


def key(tree_sha, py_version, inputs, argv, donor):
    blob = json.dumps({'schema': SCHEMA, 'trackbuild_tree': tree_sha, 'python': py_version, 'inputs': inputs, 'argv': argv,
                       'donor': donor}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def restore(store, k, tbuild, src):
    """-> (True, note) when the entry exists and verifies (files copied to tbuild, BUILD_REPORT source = src), else (False, note)"""
    e = os.path.join(store, k)
    man = os.path.join(e, 'MANIFEST.json')
    if not os.path.isfile(man):
        usage(store, 'miss', k)
        return False, 'no entry'
    try:
        m = json.load(open(man, encoding='utf-8'))
        for n, h in m['files'].items():
            if _sha(os.path.join(e, n)) != h:
                raise ValueError('hash mismatch %s' % n)
    except (OSError, ValueError, KeyError) as ex:
        bad = e + '.corrupt'
        i = 0
        while os.path.exists(bad):
            i += 1
            bad = '%s.corrupt%d' % (e, i)
        os.rename(e, bad)
        usage(store, 'corrupt', k, str(ex))
        return False, 'entry failed verification (%s): moved to %s' % (ex, os.path.basename(bad))
    os.makedirs(tbuild, exist_ok=True)
    for n in m['files']:
        if n == 'BUILD_REPORT.json':
            t = open(os.path.join(e, n), encoding='utf-8').read().replace(SRC_TOKEN, json.dumps(os.path.abspath(src))[1:-1])
            open(os.path.join(tbuild, n), 'w', encoding='utf-8', newline='\n').write(t)
        else:
            shutil.copyfile(os.path.join(e, n), os.path.join(tbuild, n))
    usage(store, 'hit', k)
    return True, 'reused verified entry %s (%d files)' % (k[:12], len(m['files']))


def save(store, k, tbuild, src, info):
    e = os.path.join(store, k)
    if os.path.exists(e):
        return 'kept existing entry'
    tmp = '%s.tmp_%d' % (e, os.getpid())
    os.makedirs(tmp)
    files = {}
    for n in sorted(os.listdir(tbuild)):
        p = os.path.join(tbuild, n)
        if not os.path.isfile(p) or n == 'VALIDATION.json':
            continue
        if n == 'BUILD_REPORT.json':
            t = open(p, encoding='utf-8').read()
            t = t.replace(json.dumps(os.path.abspath(src))[1:-1], SRC_TOKEN)
            open(os.path.join(tmp, n), 'w', encoding='utf-8', newline='\n').write(t)
        else:
            shutil.copyfile(p, os.path.join(tmp, n))
        files[n] = _sha(os.path.join(tmp, n))
    json.dump({'schema': SCHEMA, 'key': k, 'files': files, 'key_inputs': info}, open(os.path.join(tmp, 'MANIFEST.json'), 'w',
              encoding='utf-8'), indent=1, sort_keys=True)
    try:
        os.rename(tmp, e)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)           # our own temp folder only
        return 'another writer stored it first'
    usage(store, 'store', k)
    return 'stored %s' % k[:12]
