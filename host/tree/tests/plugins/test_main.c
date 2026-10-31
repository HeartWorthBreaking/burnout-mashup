/* Native plugins (src/game/plugins.c over modfs.c and modmanifest.c): which
 * modules are loaded, approved, started and refused, on mod folders the test
 * makes in the temporary directory, and that the bytes loaded are the bytes
 * approved. The modules are tests/plugins/test_module.c built per kind, and
 * the example plugin; each records its kind in a marker file the moment the
 * system loads it, so "never loaded" is checked directly. No game data, no
 * guest.
 *   plugins_test <folder of the built test modules> <example plugin> [log copy] */
#include "modfs.h"
#include "plugins.h"
#include "plugins_platform.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "bmashup_autopilot.h"
#include "bmashup_boost.h"
#include "bmashup_events.h"
#include "xr_sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <direct.h>
#include <windows.h>
#define EXT ".asi"
#define MKDIR(p) _mkdir(p)
static void set_env(const char *k, const char *v) { _putenv_s(k, v ? v : ""); }
#else
#include <sys/stat.h>
#include <unistd.h>
#if defined(__APPLE__)
#define EXT ".dylib"
#else
#define EXT ".so"
#endif
#define MKDIR(p) mkdir(p, 0755)
static void set_env(const char *k, const char *v) { if (v) setenv(k, v, 1); else unsetenv(k); }
#endif

/* The toolkit's, which modfs.c chains onto (tests/modfs does the same). */
const char *(*xbox_PathRedirectHook)(const char *xbox_path);

static int s_fail, s_pass;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); \
    printf(__VA_ARGS__); putchar('\n'); } } while (0)

static char s_tmp[600], s_modules[600], s_hello[600], s_log[700];

/* A stand-in "takedawn.race" (the real one is tests/race's): what each
 * plugin registers with it is kept, so the test can call them all with
 * snapshots (race_all). */
static struct { td_host *host; td_race_update_fn fn; void *user; } s_race[8];
static int s_nrace;
static int32_t TD_CALL fake_race_get(td_host *host, td_race_snapshot *out)
{
    (void)host;
    (void)out;
    return TD_RACE_UNAVAILABLE;
}
static int32_t TD_CALL fake_race_on_update(td_host *host, td_race_update_fn fn, void *user)
{
    int k;
    for (k = 0; k < s_nrace && s_race[k].host != host; k++)
        ;
    if (k == 8)
        return TD_RACE_BAD_ARG;
    s_race[k].host = host;
    s_race[k].fn = fn;
    s_race[k].user = user;
    if (k == s_nrace)
        s_nrace++;
    return TD_RACE_OK;
}
static const td_race_api s_fake_race = { (uint32_t)sizeof(td_race_api), TD_RACE_VERSION, fake_race_get,
                                         fake_race_on_update };
static void race_all(const td_race_snapshot *r)
{
    for (int k = 0; k < s_nrace; k++)
        if (s_race[k].fn)
            s_race[k].fn(r, s_race[k].user);
}

/* A stand-in "bmashup.autopilot" (the real one is tests/bm_autopilot's):
 * counts the requests, answers what the test sets. */
static int s_bm_engages;
static int32_t s_bm_rc;
static bm_autopilot_status s_bm_st = { (uint32_t)sizeof(bm_autopilot_status), BM_AP_STATE_IDLE, BM_AP_OK, 0, BM_AP_OK, 0 };
static int s_bm_engage2s, s_bm_releases;
static bm_autopilot_request s_bm_req;           /* engage2's last request */
static int32_t TD_CALL fake_bm_engage(td_host *host)
{
    (void)host;
    s_bm_engages++;
    return s_bm_rc;
}
static int32_t TD_CALL fake_bm_engage2(td_host *host, const bm_autopilot_request *req)
{
    (void)host;
    s_bm_engages++;
    s_bm_engage2s++;
    if (req)
        s_bm_req = *req;
    return s_bm_rc;
}
static int32_t TD_CALL fake_bm_release(td_host *host)
{
    (void)host;
    s_bm_releases++;
    return BM_AP_NOT_ENGAGED;
}
static int32_t TD_CALL fake_bm_status(td_host *host, bm_autopilot_status *out)
{
    uint32_t n;
    (void)host;
    if (!out || out->struct_size < 8)
        return BM_AP_BAD_ARG;
    n = out->struct_size < sizeof s_bm_st ? out->struct_size : (uint32_t)sizeof s_bm_st;
    memcpy(out, &s_bm_st, n);
    out->struct_size = n;
    return BM_AP_OK;
}
static const bm_autopilot_api s_fake_bm = { (uint32_t)sizeof(bm_autopilot_api), BM_AUTOPILOT_VERSION, fake_bm_engage,
                                            fake_bm_status, fake_bm_engage2, fake_bm_release };

/* A stand-in "bmashup.boost" (the real one is tests/bm_boost's). */
static int s_bb_fills;
static int32_t s_bb_rc;
static bm_boost_status s_bb_st = { (uint32_t)sizeof(bm_boost_status), BM_BOOST_STATE_IDLE, BM_BOOST_OK, 0, 0, 1,
                                   50.0f, 240.0f, 0, 0.0f, 0.0f };
static int32_t TD_CALL fake_bb_fill(td_host *host)
{
    (void)host;
    s_bb_fills++;
    return s_bb_rc;
}
static int32_t TD_CALL fake_bb_status(td_host *host, bm_boost_status *out)
{
    uint32_t n;
    (void)host;
    if (!out || out->struct_size < 8)
        return BM_BOOST_BAD_ARG;
    n = out->struct_size < sizeof s_bb_st ? out->struct_size : (uint32_t)sizeof s_bb_st;
    memcpy(out, &s_bb_st, n);
    out->struct_size = n;
    return BM_BOOST_OK;
}
static const bm_boost_api s_fake_bb = { (uint32_t)sizeof(bm_boost_api), BM_BOOST_VERSION, fake_bb_fill, fake_bb_status };

/* A stand-in "bmashup.events" (the real one is tests/bm_events'): keeps each
 * subscription, so the test can deliver events. */
static struct { td_host *host; bm_event_fn fn; void *user; } s_ev_sub[8];
static int s_nev_sub;
static int32_t TD_CALL fake_ev_subscribe(td_host *host, uint32_t event, bm_event_fn fn, void *user)
{
    if (!host || !fn)
        return BM_EVENTS_BAD_ARG;
    if (event != BM_EVENT_PLAYER_CAR_UPDATE)
        return BM_EVENTS_UNKNOWN_EVENT;
    for (int k = 0; k < s_nev_sub; k++)
        if (s_ev_sub[k].host == host)
            return BM_EVENTS_ALREADY;
    if (s_nev_sub == 8)
        return BM_EVENTS_FULL;
    s_ev_sub[s_nev_sub].host = host;
    s_ev_sub[s_nev_sub].fn = fn;
    s_ev_sub[s_nev_sub].user = user;
    s_nev_sub++;
    return BM_EVENTS_OK;
}
static int32_t TD_CALL fake_ev_stats(td_host *host, uint32_t event, bm_events_stats *out)
{
    (void)host;
    (void)event;
    if (!out || out->struct_size < 8)
        return BM_EVENTS_BAD_ARG;
    memset(out, 0, out->struct_size < sizeof *out ? out->struct_size : sizeof *out);
    return BM_EVENTS_OK;
}
static const bm_events_api s_fake_ev = { (uint32_t)sizeof(bm_events_api), BM_EVENTS_VERSION, fake_ev_subscribe, fake_ev_stats };
static void ev_all(const bm_event *ev)
{
    for (int k = 0; k < s_nev_sub; k++)
        s_ev_sub[k].fn(ev, s_ev_sub[k].user);
}

static void mkdirs(const char *path)
{
    char p[900];
    snprintf(p, sizeof p, "%s", path);
    for (char *c = p + 1; *c; c++)
        if (*c == '/' || *c == '\\') {
            char k = *c;
            *c = 0;
            MKDIR(p);
            *c = k;
        }
    MKDIR(p);
}

static void write_file(const char *path, const char *text)
{
    FILE *f = fopen(path, "wb");
    if (!f) {
        printf("cannot write %s\n", path);
        exit(2);
    }
    fputs(text, f);
    fclose(f);
}

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    long n;
    char *b;
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    b = malloc((size_t)n + 1);
    if (!b || fread(b, 1, (size_t)n, f) != (size_t)n) {
        fclose(f);
        free(b);
        return NULL;
    }
    b[n] = 0;
    fclose(f);
    return b;
}

/* 1 when copied; 0 when either side could not be opened (a held file). */
static int try_copy(const char *from, const char *to)
{
    FILE *a = fopen(from, "rb"), *b = a ? fopen(to, "wb") : NULL;
    char buf[8192];
    size_t n;
    if (!a || !b) {
        if (a)
            fclose(a);
        return 0;
    }
    while ((n = fread(buf, 1, sizeof buf, a)) > 0)
        fwrite(buf, 1, n, b);
    fclose(a);
    fclose(b);
    return 1;
}

static void copy_file(const char *from, const char *to)
{
    if (!try_copy(from, to)) {
        printf("cannot copy %s -> %s\n", from, to);
        exit(2);
    }
}

static void sha_of(const char *path, char hex[65])
{
    FILE *f = fopen(path, "rb");
    unsigned char buf[8192], d[32];
    xr_sha256 s;
    size_t n;
    xr_sha256_init(&s);
    while (f && (n = fread(buf, 1, sizeof buf, f)) > 0)
        xr_sha256_update(&s, buf, n);
    if (f)
        fclose(f);
    xr_sha256_final(&s, d);
    xr_sha256_hex(d, hex);
}

static void module_path(char *out, size_t n, const char *kind)
{
    snprintf(out, n, "%s/%s" EXT, s_modules, kind);
}

/* TAKEDAWN_PLUGINS as a player has it: unset; on macOS, where plugins load only
 * with TAKEDAWN_PLUGINS=1, that. */
static void plugins_default(void)
{
#if defined(__APPLE__)
    set_env("TAKEDAWN_PLUGINS", "1");
#else
    set_env("TAKEDAWN_PLUGINS", NULL);
#endif
}

/* ---- a scenario: <tmp>/<name>/{mods,markers}, a mod list, approvals ---- */

static char s_dir[700], s_approvals[8192];

static void scenario(const char *name)
{
    char p[800];
    snprintf(s_dir, sizeof s_dir, "%s/%s", s_tmp, name);
    snprintf(p, sizeof p, "%s/mods", s_dir);
    mkdirs(p);
    snprintf(p, sizeof p, "%s/markers", s_dir);
    mkdirs(p);
    set_env("TP_MARKER_DIR", p);
    set_env("TAKEDAWN_MODS", NULL);
    plugins_default();
    s_approvals[0] = 0;
}

static void approve(const char *id, const char *hex)
{
    size_t n = strlen(s_approvals);
    snprintf(s_approvals + n, sizeof s_approvals - n, "%s\"%s sha256:%s\"", n ? ", " : "", id, hex);
}

/* A mod <id> in folder <sub>: its mod.toml has body after the id and name;
 * kind (a built test module, "hello", or NULL) is copied to rel; approve: 1
 * for its real hash, 2 for a wrong one. */
static void mod(const char *sub, const char *id, const char *body, const char *kind, const char *rel, int how)
{
    char dir[800], p[1000], t[1500], hex[65];
    snprintf(dir, sizeof dir, "%s/mods/%s", s_dir, sub);
    mkdirs(dir);
    snprintf(t, sizeof t, "id = \"%s\"\nname = \"%s\"\n%s", id, id, body);
    snprintf(p, sizeof p, "%s/mod.toml", dir);
    write_file(p, t);
    if (kind) {
        char from[800], parent[1000], *e;
        snprintf(p, sizeof p, "%s/%s", dir, rel);
        snprintf(parent, sizeof parent, "%s", p);
        e = strrchr(parent, '/');
        if (e) {
            *e = 0;
            mkdirs(parent);
        }
        if (!strcmp(kind, "hello"))
            snprintf(from, sizeof from, "%s", s_hello);
        else
            module_path(from, sizeof from, kind);
        copy_file(from, p);
        sha_of(p, hex);
        if (how)
            approve(id, how == 1 ? hex : "0000000000000000000000000000000000000000000000000000000000000000");
    }
}

/* Writes the approvals (unless own is given, or none when no_file), the mod
 * list, and starts. */
static void start(const char *disabled, const char *own_approvals, int no_file)
{
    char p[800], t[8400];
    snprintf(p, sizeof p, "%s/mods", s_dir);
    set_env("TAKEDAWN_MODS", p);
    snprintf(p, sizeof p, "%s/mod-list.toml", s_dir);
    snprintf(t, sizeof t, "disabled = [%s]\n", disabled ? disabled : "");
    write_file(p, t);
    bo3_modfs_state_file(p);
    bo3_modfs_init();
    snprintf(p, sizeof p, "%s/approvals.toml", s_dir);
    if (!no_file) {
        if (own_approvals)
            snprintf(t, sizeof t, "%s", own_approvals);
        else
            snprintf(t, sizeof t, "# test\napproved = [%s]\n", s_approvals);
        write_file(p, t);
    }
    bo3_plugins_approval_file(p);
    fflush(stderr);
    bo3_plugins_init("9.9.9-test");
    fflush(stderr);
}

static int index_of(const char *id)
{
    for (int i = 0; i < bo3_modfs_mod_count(); i++)
        if (!strcmp(bo3_modfs_mod(i)->manifest.id, id))
            return i;
    return -1;
}

static bo3_plugin_state state(const char *id, char *why)
{
    return bo3_plugins_state(index_of(id), why, 200, NULL, 0);
}

/* 1 when a module of this kind was loaded in this scenario. */
static int loaded(const char *kind)
{
    char p[800], want[64], *t;
    int hit;
    snprintf(p, sizeof p, "%s/markers/loaded", s_dir);
    t = read_file(p);
    if (!t)
        return 0;
    snprintf(want, sizeof want, "kind=%s ", kind);
    hit = strstr(t, want) != NULL;
    free(t);
    return hit;
}

static char *marker(const char *name)
{
    char p[800];
    snprintf(p, sizeof p, "%s/markers/%s", s_dir, name);
    return read_file(p);
}

static const char *plat(void)
{
    return bo3_manifest_platform();
}

/* The first "copy=<address>" of an init marker: which loaded copy ran it. */
static void copy_of(const char *name, char *out, size_t n)
{
    char *t = marker(name), *c = t ? strstr(t, "copy=") : NULL;
    size_t k = 0;
    out[0] = 0;
    if (c) {
        c += 5;
        while (c[k] && c[k] != '\n' && k + 1 < n)
            k++;
        memcpy(out, c, k);
        out[k] = 0;
    }
    free(t);
}

/* Every line of an init marker says inits=1: each init ran in a copy of its own. */
static int all_first_inits(const char *name, int *lines)
{
    char *t = marker(name), *p = t;
    int ok = t != NULL;
    *lines = 0;
    while (p && *p) {
        char *e = strchr(p, '\n');
        (*lines)++;
        if (!strstr(p, "inits=1") || (e && strstr(p, "inits=1") > e))
            ok = 0;
        p = e ? e + 1 : NULL;
    }
    free(t);
    return ok;
}

/* At exit, after the plugins' own on_shutdown (registered later, so run
 * first): each running plugin of the last start shut down, newest first. */
static void check_shutdown(void)
{
    char *t, *good, *hello;
    fflush(stderr);
    t = read_file(s_log);
    good = t ? strstr(t, "[PLUGIN t.good] shutdown") : NULL;
    hello = t ? strstr(t, "[PLUGIN example.hello-plugin] goodbye") : NULL;
    if (good && hello && good < hello) {
        printf("shutdown: t.good, then example.hello-plugin (newest first): ok\n");
    } else {
        printf("FAIL shutdown: t.good %s, example.hello-plugin %s, order %s\n", good ? "ran" : "missing",
               hello ? "ran" : "missing", good && hello ? "wrong" : "-");
        fflush(stdout);
        free(t);
        _exit(1);
    }
    free(t);
}

#if defined(__linux__)
#include <dirent.h>
/* Open descriptors of this process. */
static int open_fds(void)
{
    DIR *d = opendir("/proc/self/fd");
    struct dirent *e;
    int n = 0;
    while (d && (e = readdir(d)) != NULL)
        n += e->d_name[0] != '.';
    if (d)
        closedir(d);
    return n;
}
#endif

static void declare(char *out, size_t n, int api, const char *rel)
{
    snprintf(out, n, "[plugin]\napi = %d\n%s = \"%s\"\n", api, plat(), rel);
}

/* The API version a loaded module says it was built for (its export). */
static unsigned module_version(void *lib)
{
    td_plugin_api_version_fn fn = (td_plugin_api_version_fn)bo3_plugin_sys_symbol(lib, TD_PLUGIN_API_VERSION_SYMBOL);
    return fn ? (unsigned)fn() : 0;
}

#if defined(_WIN32)
static void to_backslash(char *p)
{
    for (; *p; p++)
        if (*p == '/')
            *p = '\\';
}

/* F1 (review): what is loaded is the file that was hashed, before its
 * start-up code runs, even when a junction on the way is pointed elsewhere
 * after the hash; the file and every folder of its real path cannot be
 * renamed, replaced or written while held. */
static void identity_windows(void)
{
    char a[900], b[900], sub[900], file[1000], cmd[3000], from[800], x[1000], y[1100];
    uint8_t sha[32];
    char why[200], hex[65], hex2[65];
    bo3_plugin_file *f;
    void *lib;

    scenario("f1");
    snprintf(a, sizeof a, "%s/A", s_dir);
    snprintf(b, sizeof b, "%s/B", s_dir);
    snprintf(sub, sizeof sub, "%s/mod/sub", s_dir);
    mkdirs(a);
    mkdirs(b);
    snprintf(x, sizeof x, "%s/mod", s_dir);
    mkdirs(x);
    snprintf(file, sizeof file, "%s/p" EXT, a);
    module_path(from, sizeof from, "good");
    copy_file(from, file);
    sha_of(file, hex);
    snprintf(file, sizeof file, "%s/p" EXT, b);
    module_path(from, sizeof from, "newversion");
    copy_file(from, file);
    to_backslash(a);
    to_backslash(b);
    to_backslash(sub);
    snprintf(cmd, sizeof cmd, "mklink /J \"%s\" \"%s\" >NUL", sub, a);
    if (system(cmd) != 0) {
        printf("SKIP: identity (mklink /J failed)\n");
        return;
    }
    snprintf(file, sizeof file, "%s\\p" EXT, sub);
    f = bo3_plugin_sys_hold(file, sha, why, sizeof why);
    CHECK(f != NULL, "f1: hold through the junction: %s", why);
    if (!f)
        return;
    xr_sha256_hex(sha, hex2);
    CHECK(!strcmp(hex, hex2), "f1: the hash is the file's");
    /* point the junction elsewhere after the hash (the review's C1) */
    snprintf(cmd, sizeof cmd, "rmdir \"%s\" && mklink /J \"%s\" \"%s\" >NUL", sub, sub, b);
    CHECK(system(cmd) == 0, "f1: the junction could be pointed elsewhere (it is not on the real path)");
    /* the held file and its real folders cannot be written, renamed or replaced */
    snprintf(x, sizeof x, "%s\\p" EXT, a);
    module_path(from, sizeof from, "newversion");
    CHECK(!try_copy(from, x), "f1: the held module cannot be overwritten");
    snprintf(y, sizeof y, "%s\\p_old" EXT, a);
    CHECK(!MoveFileA(x, y), "f1: the held module cannot be renamed");
    snprintf(y, sizeof y, "%s_old", a);
    CHECK(!MoveFileA(a, y), "f1: its folder cannot be renamed");
    snprintf(x, sizeof x, "%s", s_dir);
    to_backslash(x);
    snprintf(y, sizeof y, "%s_old", x);
    CHECK(!MoveFileA(x, y), "f1: a folder above it cannot be renamed");
    lib = bo3_plugin_sys_load(f, why, sizeof why);
    bo3_plugin_sys_release(f);
    CHECK(lib != NULL, "f1: load: %s", why);
    if (lib) {
        char got[MAX_PATH + 1];
        DWORD n = GetModuleFileNameA((HMODULE)lib, got, MAX_PATH);
        got[n < MAX_PATH ? n : MAX_PATH] = 0;
        CHECK(module_version(lib) == 1, "f1: the module mapped is the hashed one (good, API 1), not the other (API 2): %u",
              module_version(lib));
        CHECK(strstr(got, "\\A\\p" EXT) != NULL, "f1: mapped from the real place A: %s", got);
    }
    CHECK(!loaded("newversion"), "f1: the other module's start-up code never ran");
    /* after release, the folder can be renamed again (nothing stays pinned) */
    snprintf(y, sizeof y, "%s_old", b);
    CHECK(MoveFileA(b, y) != 0, "f1: an unrelated folder is free");
}
#endif

/* Replacing the module after it was hashed (writing it in place where the
 * system lets that happen) never changes what is loaded. */
static void replace_after_hold(void)
{
    char dir[800], file[1000], from[800], why[200];
    uint8_t sha[32];
    bo3_plugin_file *f;
    void *lib;

    scenario("replace");
    snprintf(dir, sizeof dir, "%s/m", s_dir);
    mkdirs(dir);
    snprintf(file, sizeof file, "%s/r" EXT, dir);
    module_path(from, sizeof from, "good");
    copy_file(from, file);
    f = bo3_plugin_sys_hold(file, sha, why, sizeof why);
    CHECK(f != NULL, "replace: hold: %s", why);
    if (!f)
        return;
    module_path(from, sizeof from, "newversion");
#if defined(_WIN32)
    CHECK(!try_copy(from, file), "replace: Windows refuses to write the held module");
#else
    CHECK(try_copy(from, file), "replace: the source file was rewritten in place after the hash");
#endif
    lib = bo3_plugin_sys_load(f, why, sizeof why);
    bo3_plugin_sys_release(f);
    CHECK(lib && module_version(lib) == 1, "replace: the hashed bytes are what loaded (API 1), not the rewrite: %s",
          lib ? "loaded" : why);
    CHECK(!loaded("newversion"), "replace: the rewritten bytes never ran");
}

int main(int argc, char **argv)
{
    char why[200], b[400], *t;

    if (argc < 3) {
        printf("usage: plugins_test <modules folder> <example plugin> [log copy]\n");
        return 2;
    }
    snprintf(s_modules, sizeof s_modules, "%s", argv[1]);
    snprintf(s_hello, sizeof s_hello, "%s", argv[2]);
#if defined(_WIN32)
    {
        char base[MAX_PATH];
        GetTempPathA(sizeof base, base);
        snprintf(s_tmp, sizeof s_tmp, "%sbo3_plugins_%lu_%lu", base, (unsigned long)GetCurrentProcessId(),
                 (unsigned long)GetTickCount());
        for (char *c = s_tmp; *c; c++)
            if (*c == '\\')
                *c = '/';
    }
#else
    snprintf(s_tmp, sizeof s_tmp, "/tmp/bo3_plugins_XXXXXX");
    if (!mkdtemp(s_tmp))
        return 2;
#endif
    mkdirs(s_tmp);
    snprintf(s_log, sizeof s_log, "%s/log.txt", s_tmp);
    if (!freopen(s_log, "w", stderr)) {
        printf("cannot redirect stderr\n");
        return 2;
    }
    atexit(check_shutdown);         /* before any plugin: it runs after their on_shutdown */
    set_env("TAKEDAWN_MOD_LIST", NULL);

    /* s0: installed mods without native code: nothing is said, nothing runs */
    scenario("s0");
    mod("asset", "a.asset", "", NULL, NULL, 0);
    start(NULL, NULL, 0);
    CHECK(bo3_plugins_running() == 0 && state("a.asset", why) == BO3_PLUGIN_NONE, "s0: a data mod has no plugin");
    t = read_file(s_log);
    CHECK(t && !strstr(t, "[PLUGIN"), "s0: no [PLUGIN] line without a declared plugin");
    free(t);

    /* s1: the main matrix. "marker" modules must never load. */
    scenario("s1");
    mod("asset", "a.asset", "", NULL, NULL, 0);
    declare(b, sizeof b, 1, "bin/good" EXT);
    mod("good", "t.good", b, "good", "bin/good" EXT, 1);
    mod("notapproved", "t.notapproved", b, "marker", "bin/good" EXT, 0);
    mod("wronghash", "t.wronghash", b, "marker", "bin/good" EXT, 2);
    {
        char p[900];
        mod("disabled", "t.disabled", b, "marker", "bin/good" EXT, 1);
        snprintf(p, sizeof p, "%s/mods/disabled/files", s_dir);
        mkdirs(p);
        strcat(p, "/x.dat");
        write_file(p, "data");
    }
    mod("stray", "t.stray", b, "good", "bin/good" EXT, 1);
    {
        char p[900], src[700];
        module_path(src, sizeof src, "marker");          /* undeclared modules: must never load */
        snprintf(p, sizeof p, "%s/mods/stray/stray" EXT, s_dir);
        copy_file(src, p);
        snprintf(p, sizeof p, "%s/mods/stray/files", s_dir);
        mkdirs(p);
        strcat(p, "/evil" EXT);
        copy_file(src, p);
        snprintf(p, sizeof p, "%s/mods/stray/bin/other" EXT, s_dir);
        copy_file(src, p);
    }
    mod("noinit", "t.noinit", b, "noinit", "bin/good" EXT, 1);
    mod("noversion", "t.noversion", b, "noversion", "bin/good" EXT, 1);
    mod("newversion", "t.newversion", b, "newversion", "bin/good" EXT, 1);
    {
        char b2[400];
        declare(b2, sizeof b2, 2, "bin/good" EXT);
        mod("api2", "t.api2", b2, "marker", "bin/good" EXT, 1);
    }
    mod("initfail", "t.initfail", b, "initfail", "bin/good" EXT, 1);
    {
        char p[900];
        snprintf(p, sizeof p, "%s/mods/initfail/files", s_dir);
        mkdirs(p);
        strcat(p, "/y.dat");
        write_file(p, "data");
    }
    {
        char b2[400], dirp[1000];
        declare(b2, sizeof b2, 1, "bin/none" EXT);
        mod("missing", "t.missing", b2, NULL, NULL, 0);
        declare(b2, sizeof b2, 1, "bin/dir" EXT);
        mod("dirmod", "t.dirmod", b2, NULL, NULL, 0);
        snprintf(dirp, sizeof dirp, "%s/mods/dirmod/bin/dir" EXT, s_dir);
        mkdirs(dirp);
    }
    mod("order_b", "t.order.b", b, "order_b", "bin/good" EXT, 1);
    mod("order_a", "t.order.a", b, "order_a", "bin/good" EXT, 1);
    mod("biginfo", "t.biginfo", b, "biginfo", "bin/good" EXT, 1);
    mod("changed", "t.changed", b, "marker", "bin/good" EXT, 1);
    {
        char p[900];
        FILE *f;
        snprintf(p, sizeof p, "%s/mods/changed/bin/good" EXT, s_dir);
        f = fopen(p, "ab");              /* the bytes change after the approval */
        if (f) {
            fputc(0, f);
            fclose(f);
        }
    }
    mod("otheros", "t.otheros", "[plugin]\napi = 1\nandroid = \"lib/x.so\"\n", NULL, NULL, 0);
    if (!strcmp(plat(), "android"))
        mod("otheros", "t.otheros", "[plugin]\napi = 1\nmacos = \"lib/x.dylib\"\n", NULL, NULL, 0);
    mod("invalid", "t.invalid", "[plugin]\napi = 1\nwindows = \"../good.asi\"\n", NULL, NULL, 0);
    mod("device", "t.device", "[plugin]\napi = 1\nwindows = \"NUL.asi\"\n", NULL, NULL, 0);
    {
        char b2[400];
        declare(b2, sizeof b2, 1, "hello" EXT);
        mod("hello", "example.hello-plugin", b2, "hello", "hello" EXT, 1);
    }
    start("\"t.disabled\"", NULL, 0);

    CHECK(state("a.asset", why) == BO3_PLUGIN_NONE, "asset-only mod: no plugin");
    CHECK(bo3_modfs_mod(index_of("a.asset"))->usable && bo3_modfs_mod(index_of("a.asset"))->enabled, "asset-only mod on");
    CHECK(state("t.good", why) == BO3_PLUGIN_RUNNING && loaded("good"), "approved plugin runs: %s", why);
    t = marker("init.t.good");
    CHECK(t && strstr(t, "id=t.good api=1") && strstr(t, "version=9.9.9-test"), "init got its mod id, API 1, host version: %s",
          t ? t : "(no marker)");
    {
        char want[32];
        snprintf(want, sizeof want, "info=%u ", (unsigned)sizeof(td_plugin_info));
        CHECK(t && strstr(t, want), "F3: init is told the room it has in info (%s): %s", want, t ? t : "(no marker)");
    }
    free(t);
    CHECK(state("t.notapproved", why) == BO3_PLUGIN_NOT_APPROVED, "not approved");
    CHECK(state("t.wronghash", why) == BO3_PLUGIN_NOT_APPROVED, "approved for other bytes");
    CHECK(state("t.disabled", why) == BO3_PLUGIN_OFF && !bo3_modfs_mod(index_of("t.disabled"))->enabled,
          "a mixed mod that is off: off");
    CHECK(state("t.stray", why) == BO3_PLUGIN_RUNNING, "declared module of the stray mod runs: %s", why);
    CHECK(state("t.api2", why) == BO3_PLUGIN_REFUSED && strstr(why, "needs plugin API 2"), "a newer plugin.api: refused (%s)", why);
    CHECK(state("t.changed", why) == BO3_PLUGIN_NOT_APPROVED, "changed bytes need a new approval");
    CHECK(!loaded("marker"), "not approved, other bytes, changed bytes, mod off, a newer api, undeclared modules beside, "
          "in bin and in files: none of them was ever loaded");
    CHECK(state("t.noinit", why) == BO3_PLUGIN_REFUSED && strstr(why, "takedawn_plugin_init"), "no init export: refused (%s)", why);
    CHECK(loaded("noinit"), "no init export: the library was loaded (its start-up code ran) - documented");
    CHECK(state("t.noversion", why) == BO3_PLUGIN_REFUSED && strstr(why, "takedawn_plugin_api_version"), "no version export: %s", why);
    CHECK(state("t.newversion", why) == BO3_PLUGIN_REFUSED && strstr(why, "built for plugin API 2"), "version mismatch: %s", why);
    t = marker("init.t.newversion");
    CHECK(!t, "version mismatch: init never called");
    free(t);
    CHECK(state("t.initfail", why) == BO3_PLUGIN_FAILED && strstr(why, "returned 1"), "init failure: %s", why);
    CHECK(bo3_modfs_mod(index_of("t.initfail"))->usable && bo3_modfs_mod(index_of("t.initfail"))->enabled,
          "init failure: the mod's files are still in use");
    CHECK(state("t.missing", why) == BO3_PLUGIN_REFUSED && strstr(why, "not a regular file"), "missing module: %s", why);
    CHECK(state("t.dirmod", why) == BO3_PLUGIN_REFUSED, "a folder named like a module: refused (%s)", why);
    t = marker("order");
    CHECK(t && !strcmp(t, "AB"), "load order is the mods' order (by id): %s", t ? t : "(none)");
    free(t);
    CHECK(state("t.biginfo", why) == BO3_PLUGIN_RUNNING, "F3: a plugin that says it filled a larger info runs: %s", why);
    CHECK(state("t.otheros", why) == BO3_PLUGIN_NO_MODULE && bo3_modfs_mod(index_of("t.otheros"))->usable,
          "a module only for another system: no module here, the mod still works");
    CHECK(index_of("t.invalid") < 0, "an unsafe module path makes the mod invalid");
    CHECK(index_of("t.device") < 0, "F6: a device name as the module makes the mod invalid");
    CHECK(state("example.hello-plugin", why) == BO3_PLUGIN_RUNNING, "the example plugin runs: %s", why);
    CHECK(bo3_plugins_running() == 6, "running: good, stray, order a, order b, biginfo, hello (%d)", bo3_plugins_running());
    /* every plugin ran its own module: the right kind, a copy of its own (init ran once in it) */
    {
        static const char *const want[][2] = {
            { "init.t.good", "kind=good inits=1" }, { "init.t.stray", "kind=good inits=1" },
            { "init.t.order.a", "kind=order_a inits=1" }, { "init.t.order.b", "kind=order_b inits=1" },
            { "init.t.biginfo", "kind=biginfo inits=1" }, { "init.t.initfail", "kind=initfail inits=1" } };
        char ca[64], cb[64];
        for (size_t k = 0; k < sizeof want / sizeof want[0]; k++) {
            t = marker(want[k][0]);
            CHECK(t && strstr(t, want[k][1]), "identity: %s is from its own module (%s): %s", want[k][0], want[k][1], t ? t : "(none)");
            free(t);
        }
        copy_of("init.t.good", ca, sizeof ca);
        copy_of("init.t.stray", cb, sizeof cb);
        CHECK(ca[0] && cb[0] && strcmp(ca, cb), "identity: two mods with the same module bytes ran two loaded copies (%s, %s)", ca, cb);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN example.hello-plugin] hello from API 1") && strstr(t, "[PLUGIN t.good] test module started")
              && strstr(t, "[PLUGIN t.order.b] test module started"), "identity: each plugin's lines carry its own mod id");
        free(t);
    }
    {
        char sha[65];
        bo3_plugins_state(index_of("t.notapproved"), NULL, 0, sha, sizeof sha);
        CHECK(strlen(sha) == 64, "the hash of a refused module is kept for the approval line");
    }
    /* F4: starting again and again keeps every table in bounds and the count right */
    for (int k = 0; k < 80; k++)
        bo3_plugins_init("again");
    CHECK(bo3_plugins_running() == 6 && state("t.order.a", why) == BO3_PLUGIN_RUNNING,
          "F4: 80 more starts: the same plugins, no table overrun (%d)", bo3_plugins_running());
    {
        int lines, first = all_first_inits("init.t.good", &lines);
#if defined(_WIN32)
        /* Windows loads the mod folder's file itself, and nothing is unloaded: a
         * restart starts the module it already has (the same path, the same bytes). */
        (void)first;
        CHECK(lines == 81, "81 starts of t.good (%d lines)", lines);
#else
        CHECK(first && lines == 81, "identity: 81 starts of t.good, each in a newly loaded copy (%d lines)", lines);
#endif
    }

    /* s2: TAKEDAWN_PLUGINS=0 */
    scenario("s2");
    declare(b, sizeof b, 1, "bin/good" EXT);
    mod("good", "t.good", b, "marker", "bin/good" EXT, 1);
    set_env("TAKEDAWN_PLUGINS", "0");
    start(NULL, NULL, 0);
    CHECK(state("t.good", why) == BO3_PLUGIN_DISABLED && !loaded("marker") && bo3_plugins_running() == 0,
          "TAKEDAWN_PLUGINS=0: nothing loaded (%s)", why);
    plugins_default();

    /* s3: an approval file that is not a list approves nothing */
    scenario("s3");
    mod("good", "t.good", b, "marker", "bin/good" EXT, 1);
    start(NULL, "approved = 5\n", 0);
    CHECK(state("t.good", why) == BO3_PLUGIN_NOT_APPROVED && !loaded("marker"), "a bad approval file approves nothing");

    /* s4: no approval file, an empty approvals path, a path too long to use */
    scenario("s4");
    mod("good", "t.good", b, "marker", "bin/good" EXT, 1);
    start(NULL, NULL, 1);
    CHECK(state("t.good", why) == BO3_PLUGIN_NOT_APPROVED && !loaded("marker"), "no approval file: not approved");
    bo3_plugins_approval_file("");
    bo3_plugins_init("x");
    CHECK(state("t.good", why) == BO3_PLUGIN_NOT_APPROVED && !loaded("marker"), "approvals off: not approved");
    {
        char longp[1300];
        memset(longp, 'a', sizeof longp - 1);
        longp[sizeof longp - 1] = 0;
        memcpy(longp, s_dir, strlen(s_dir));           /* a real prefix: cut short, it would name a real place */
        bo3_plugins_approval_file(longp);
        bo3_plugins_init("x");
        CHECK(state("t.good", why) == BO3_PLUGIN_NOT_APPROVED && !loaded("marker"),
              "F5: an approvals path too long: none (never cut short)");
    }

    /* s6: F7 - the hex digits in either case; entries that are not used are reported */
    scenario("s6");
    {
        char p[900], hex[65], own[2000];
        mod("good", "t.good", b, "good", "bin/good" EXT, 0);
        snprintf(p, sizeof p, "%s/mods/good/bin/good" EXT, s_dir);
        sha_of(p, hex);
        for (char *c = hex; *c; c++)
            if (*c >= 'a' && *c <= 'f')
                *c = (char)(*c - ('a' - 'A'));
        snprintf(own, sizeof own, "approved = [\"t.good sha256:%s\", 7, \"%0300d\"]\n", hex, 0);
        start(NULL, own, 0);
        CHECK(state("t.good", why) == BO3_PLUGIN_RUNNING, "F7: upper-case digits approve: %s", why);
    }

#if defined(_WIN32)
    /* s5: the module reached through a junction is refused by the walk */
    scenario("s5");
    {
        char cmd[2000], real[900], link[900];
        declare(b, sizeof b, 1, "lnk/good" EXT);
        mod("junction", "t.junction", b, "marker", "real/good" EXT, 1);
        snprintf(real, sizeof real, "%s/mods/junction/real", s_dir);
        snprintf(link, sizeof link, "%s/mods/junction/lnk", s_dir);
        to_backslash(real);
        to_backslash(link);
        snprintf(cmd, sizeof cmd, "mklink /J \"%s\" \"%s\" >NUL", link, real);
        if (system(cmd) == 0) {
            start(NULL, NULL, 0);
            CHECK(state("t.junction", why) == BO3_PLUGIN_REFUSED && !loaded("marker"), "a junction on the path: refused (%s)", why);
        } else {
            printf("SKIP: junction (mklink /J failed)\n");
        }
    }
    identity_windows();
#else
    /* s5: the module reached through a symbolic link (a linked folder, a linked file) is refused by the walk */
    scenario("s5");
    {
        char real[900], link[900];
        declare(b, sizeof b, 1, "lnk/good" EXT);
        mod("dirlink", "t.dirlink", b, "marker", "real/good" EXT, 1);
        snprintf(real, sizeof real, "%s/mods/dirlink/real", s_dir);
        snprintf(link, sizeof link, "%s/mods/dirlink/lnk", s_dir);
        CHECK(symlink(real, link) == 0, "s5: a folder link can be made");
        declare(b, sizeof b, 1, "bin/link" EXT);
        mod("filelink", "t.filelink", b, "marker", "bin/real" EXT, 1);
        snprintf(real, sizeof real, "%s/mods/filelink/bin/real" EXT, s_dir);
        snprintf(link, sizeof link, "%s/mods/filelink/bin/link" EXT, s_dir);
        CHECK(symlink(real, link) == 0, "s5: a file link can be made");
        start(NULL, NULL, 0);
        CHECK(state("t.dirlink", why) == BO3_PLUGIN_REFUSED, "a linked folder on the path: refused (%s)", why);
        CHECK(state("t.filelink", why) == BO3_PLUGIN_REFUSED, "a linked module file: refused (%s)", why);
        CHECK(!loaded("marker"), "neither was loaded");
    }
#endif
    replace_after_hold();

    /* refused, before or at loading, again and again: nothing runs, and (Linux)
     * no descriptor stays open */
    scenario("fds");
    {
        declare(b, sizeof b, 1, "bin/good" EXT);
        mod("good", "t.good", b, "marker", "bin/good" EXT, 0);             /* never approved */
        mod("wrong", "t.wrong", b, "marker", "bin/good" EXT, 2);           /* approved for other bytes */
        declare(b, sizeof b, 1, "bin/none" EXT);
        mod("missing", "t.missing", b, NULL, NULL, 0);
        {
            char p[900], hex[65];                                           /* approved, but no library: dlopen fails */
            declare(b, sizeof b, 1, "junk" EXT);
            mod("junk", "t.junk", b, NULL, NULL, 0);
            snprintf(p, sizeof p, "%s/mods/junk/junk" EXT, s_dir);
            write_file(p, "not a library\n");
            sha_of(p, hex);
            approve("t.junk", hex);
        }
        start(NULL, NULL, 0);
        CHECK(state("t.junk", why) != BO3_PLUGIN_RUNNING && strstr(why, "does not load"), "approved bytes that are no library: %s", why);
#if defined(__linux__)
        {
            int before = open_fds(), after;
            for (int k = 0; k < 40; k++)
                bo3_plugins_init("fds");
            after = open_fds();
            CHECK(before == after, "no descriptor left open by 40 refused starts (%d -> %d)", before, after);
        }
#endif
        CHECK(bo3_plugins_running() == 0 && !loaded("marker"), "nothing of the refused mods ran (%d)", bo3_plugins_running());
    }

    /* services (takedawn_services.h): offered once to each plugin that starts
     * and exports takedawn_plugin_service; never to one that does not, or
     * that is not started; malformed offers refused; at most 16 */
    scenario("svc");
    {
        static const uint32_t used[2] = { 8, 3 }, other[2] = { 8, 1 }, again[2] = { 8, 2 };
        char b2[400], name[40];
        int n = 0, added;
        CHECK(!bo3_plugins_service("Test.Upper", 1, used) && !bo3_plugins_service("nodot", 1, used)
              && !bo3_plugins_service("test.used", 0, used) && !bo3_plugins_service("test.used", 1, NULL)
              && !bo3_plugins_service(NULL, 1, used) && !bo3_plugins_service(".test", 1, used)
              && !bo3_plugins_service("test.", 1, used)
              && !bo3_plugins_service("test.a-very-long-name-that-goes-on-and-on-past-sixty-four-bytes-x", 1, used),
              "malformed service offers refused");
        CHECK(bo3_plugins_service("test.used", 1, again) && bo3_plugins_service("test.other", 1, other)
              && bo3_plugins_service("test.used", 3, used), "services offered; the same name again replaces it");
        CHECK(bo3_plugins_service(TD_RACE_SERVICE, TD_RACE_VERSION, &s_fake_race), "a stand-in takedawn.race offered");
        CHECK(bo3_plugins_service(BM_AUTOPILOT_SERVICE, BM_AUTOPILOT_VERSION, &s_fake_bm),
              "a stand-in bmashup.autopilot offered");
        CHECK(bo3_plugins_service(BM_BOOST_SERVICE, BM_BOOST_VERSION, &s_fake_bb), "a stand-in bmashup.boost offered");
        CHECK(bo3_plugins_service(BM_EVENTS_SERVICE, BM_EVENTS_VERSION, &s_fake_ev), "a stand-in bmashup.events offered");
        declare(b2, sizeof b2, 1, "race" EXT);
        mod("race", "t.race", b2, "race_telemetry", "race" EXT, 1);    /* the race telemetry example */
        declare(b2, sizeof b2, 1, "bm" EXT);
        mod("bm", "t.bm", b2, "bm_autopilot_demo", "bm" EXT, 1);       /* the private autopilot demo */
        mod("bmna", "t.bmna", b2, "bm_autopilot_demo", "bm" EXT, 0);   /* the same, not approved: never loaded */
        mod("bb", "t.bb", b2, "bm_boost_demo", "bm" EXT, 1);           /* the private boost demo */
        mod("bbna", "t.bbna", b2, "bm_boost_demo", "bm" EXT, 0);       /* the same, not approved: never loaded */
        mod("eva", "t.eva", b2, "bm_events_demo_a", "bm" EXT, 1);      /* the private events demo, observer A */
        mod("evb", "t.evb", b2, "bm_events_demo_b", "bm" EXT, 1);      /* and observer B: two plugins, one event */
        mod("evna", "t.evna", b2, "bm_events_demo_a", "bm" EXT, 0);    /* A again, not approved: never loaded */
        declare(b, sizeof b, 1, "bin/s" EXT);
        mod("s", "t.svc", b, "service", "bin/s" EXT, 1);
        mod("na", "t.svcna", b, "service", "bin/s" EXT, 0);          /* not approved: never started */
        declare(b2, sizeof b2, 1, "hello" EXT);
        mod("hello", "example.hello-plugin", b2, "hello", "hello" EXT, 1);   /* no export: never asked */
        start(NULL, NULL, 0);
        t = marker("service.t.svc");
        CHECK(t && strstr(t, "name=test.used version=3 table=8,3\n") && strstr(t, "name=test.other version=1 table=8,1\n")
              && strstr(t, "name=takedawn.race version=1\n") == NULL && strstr(t, "name=takedawn.race version=1 ")
              && !strstr(t, "table=8,2"), "a started plugin with the export: each service once, the latest table: %s",
              t ? t : "(none)");
        for (char *p = t; p && *p; p++)
            n += *p == '\n';
        CHECK(n == 6 && strstr(t, "name=bmashup.autopilot version=2 ") && strstr(t, "name=bmashup.boost version=2 ")
              && strstr(t, "name=bmashup.events version=1 "), "six offers, six lines (%d)", n);
        free(t);
        t = marker("service.t.svcna");
        CHECK(!t && state("t.svcna", why) == BO3_PLUGIN_NOT_APPROVED, "not approved: never offered");
        free(t);
        CHECK(state("example.hello-plugin", why) == BO3_PLUGIN_RUNNING, "a plugin without the export runs as before");
        fflush(stderr);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN] t.svc: service test.used 3: used") && strstr(t, "[PLUGIN] t.svc: service test.other 1: not used")
              && !strstr(t, "[PLUGIN] example.hello-plugin: service"), "the log says which were used");
        free(t);
        /* the race telemetry example: it takes takedawn.race, registers its
         * on_update, and logs what it is given */
        CHECK(state("t.race", why) == BO3_PLUGIN_RUNNING && state("t.bm", why) == BO3_PLUGIN_RUNNING
              && state("t.bb", why) == BO3_PLUGIN_RUNNING && s_nrace == 3 && s_race[0].fn && s_race[1].fn && s_race[2].fn
              && s_race[0].host != s_race[1].host && s_race[1].host != s_race[2].host && s_race[0].host != s_race[2].host,
              "the race telemetry example and both demos run, each with its on_update (%s)", why);
        {
            td_race_snapshot r;
            memset(&r, 0, sizeof r);
            r.struct_size = (uint32_t)sizeof r;
            r.state = TD_RACE_FRONTEND;
            race_all(&r);
            r.state = TD_RACE_RACING;
            r.valid = TD_RACE_HAVE_CAR | TD_RACE_HAVE_SPEED;
            r.race_time_s = 0.5f;
            r.place = 4;
            r.cars = 6;
            r.speed_mps = 41.7f;
            r.position[0] = 1.0f;
            r.position[1] = 2.0f;
            r.position[2] = 3.0f;
            race_all(&r);
            r.race_time_s = 0.9f;                                       /* under a second later: no line */
            race_all(&r);
            r.race_time_s = 1.6f;
            r.valid = TD_RACE_HAVE_CAR;                                 /* no speed */
            race_all(&r);
            r.state = TD_RACE_FINISHED;
            r.best_lap_s = 1.25f;
            race_all(&r);
            r.struct_size = 32;                                         /* a snapshot too small for it: ignored */
            r.state = TD_RACE_LOADING;
            race_all(&r);
        }
        fflush(stderr);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN] t.race: service takedawn.race 1: used") && strstr(t, "[PLUGIN] t.race: service test.used 3: not used"),
              "the example takes takedawn.race and declines the others");
        CHECK(t && strstr(t, "[PLUGIN t.race] state FRONTEND") && strstr(t, "[PLUGIN t.race] state RACING")
              && strstr(t, "[PLUGIN t.race] race 0.5 s  lap 0  place 4/6  speed 41.7 m/s (93 mph)  pos 1.0 2.0 3.0")
              && strstr(t, "[PLUGIN t.race] race 1.6 s  lap 0  place 4/6  speed -  pos 1.0 2.0 3.0")
              && !strstr(t, "[PLUGIN t.race] race 0.9 s")
              && strstr(t, "[PLUGIN t.race] finished: place 4/6  time 1.600 s  best lap 1.250 s  laps 0")
              && !strstr(t, "[PLUGIN t.race] state LOADING"),
              "the example's lines: state changes, a line a second of race time, the finish, a short snapshot ignored");
        free(t);
        for (added = 0; added < 20; added++) {
            snprintf(name, sizeof name, "test.fill%02d", added);
            if (!bo3_plugins_service(name, 1, other))
                break;
        }
        /* the private autopilot demo: given bmashup.autopilot and
         * takedawn.race, it asks once at 5 s of race time and logs the
         * answer and each change of the status; not approved, never loaded */
        CHECK(s_bm_engages == 0, "the demo asked nothing in the telemetry snapshots (race time under 5 s)");
        {
            td_race_snapshot r;
            memset(&r, 0, sizeof r);
            r.struct_size = (uint32_t)sizeof r;
            r.state = TD_RACE_PRESTART;
            r.valid = TD_RACE_HAVE_CAR;
            r.race_time_s = 9.0f;
            race_all(&r);                                               /* the countdown: never */
            r.state = TD_RACE_RACING;
            r.valid = 0;
            race_all(&r);                                               /* no car: never */
            r.valid = TD_RACE_HAVE_CAR;
            r.race_time_s = 4.9f;
            race_all(&r);
            CHECK(s_bm_engages == 0 && s_bb_fills == 0,
                  "the demos (autopilot and boost): not in the countdown, not without a car, not before 5 s");
            s_bm_rc = BM_AP_OK;
            s_bb_rc = BM_BOOST_OK;
            r.race_time_s = 5.0f;
            race_all(&r);
            CHECK(s_bm_engages == 1 && s_bm_engage2s == 1 && s_bb_fills == 1 && s_bm_req.struct_size == 12
                  && s_bm_req.policy == BM_AP_POLICY_ONCE_PER_RACE && s_bm_req.race == 0,
                  "the demos: one request each at 5 s; the autopilot demo uses engage2 bound to race 0");
            s_bm_st.state = BM_AP_STATE_PENDING;
            race_all(&r);
            s_bm_st.state = BM_AP_STATE_ENGAGED;
            s_bm_st.engaged_races = 1;
            r.race_time_s = 6.0f;
            race_all(&r);
            race_all(&r);
            s_bm_st.state = BM_AP_STATE_ENDED;
            r.state = TD_RACE_FINISHED;
            race_all(&r);
            CHECK(s_bm_engages == 1 && s_bm_releases == 0, "the demo: one request in race 0, no release (default build)");
            s_bm_st.state = BM_AP_STATE_IDLE;
            s_bm_st.race = 1;
            r.state = TD_RACE_RACING;
            r.race_time_s = 7.0f;
            race_all(&r);
            CHECK(s_bm_engages == 2 && s_bm_req.race == 1, "the next race: one request, bound to race 1 (%d)", s_bm_engages);
        }
        fflush(stderr);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN] t.bm: service bmashup.autopilot 2: used") && strstr(t, "[PLUGIN] t.bm: service takedawn.race 1: used")
              && strstr(t, "[PLUGIN] t.bm: service test.used 3: not used")
              && strstr(t, "[PLUGIN] t.race: service bmashup.autopilot 2: not used"),
              "the demo takes both services; the telemetry example declines bmashup.autopilot");
        CHECK(t && strstr(t, "[PLUGIN t.bm] autopilot demo: bmashup.autopilot 2 found (engage2 / release)")
              && strstr(t, "[PLUGIN t.bm] engage at race 5.0 s (race 0, request 1): OK")
              && strstr(t, "[PLUGIN t.bm] status IDLE (OK), race 0, release OK, engaged races 0")
              && strstr(t, "[PLUGIN t.bm] status PENDING (OK), race 0") && strstr(t, "[PLUGIN t.bm] status ENGAGED (OK), race 0")
              && strstr(t, "[PLUGIN t.bm] engaged in race 0 at 6.0 s (engaged race 1 of this process)")
              && strstr(t, "[PLUGIN t.bm] status ENDED (OK), race 0") && strstr(t, "[PLUGIN t.bm] status IDLE (OK), race 1")
              && strstr(t, "[PLUGIN t.bm] engage at race 7.0 s (race 1, request 1): OK")
              && !strstr(t, "[PLUGIN t.bm] engage at race 6.0 s (race 0")
              && !strstr(t, "[PLUGIN t.bm] release") && !strstr(t, "[PLUGIN t.bm] probe"),
              "the demo's lines: one request a race (bound to it), its answer, retries, each status change");
        CHECK(state("t.bmna", why) == BO3_PLUGIN_NOT_APPROVED && t && !strstr(t, "[PLUGIN t.bmna]")
              && !strstr(t, "[PLUGIN] t.bmna: service"), "the demo not approved: never loaded, never offered anything");
        free(t);
        /* the private boost demo: given bmashup.boost and takedawn.race, it
         * asked once at 5 s of race time (above, beside the autopilot demo);
         * here: the status changes with the bar before / after, the bar once
         * a second of race time, and never a second request; not approved,
         * never loaded */
        {
            td_race_snapshot r;
            memset(&r, 0, sizeof r);
            r.struct_size = (uint32_t)sizeof r;
            r.state = TD_RACE_RACING;
            r.valid = TD_RACE_HAVE_CAR;
            s_bb_st.state = BM_BOOST_STATE_PENDING;
            r.race_time_s = 8.0f;
            race_all(&r);
            s_bb_st.state = BM_BOOST_STATE_DONE;
            s_bb_st.fills = 1;
            s_bb_st.meter_before = 50.0f;
            s_bb_st.meter_after = 240.0f;
            s_bb_st.meter = 240.0f;
            r.race_time_s = 8.5f;
            race_all(&r);                                               /* under a second since the last bar line */
            s_bb_st.boosting = 1;
            s_bb_st.meter = 200.0f;
            r.race_time_s = 9.0f;
            race_all(&r);
            r.race_time_s = 30.0f;
            race_all(&r);
            CHECK(s_bb_fills == 1, "the boost demo: exactly one request (%d)", s_bb_fills);
        }
        fflush(stderr);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN] t.bb: service bmashup.boost 2: used") && strstr(t, "[PLUGIN] t.bb: service takedawn.race 1: used")
              && strstr(t, "[PLUGIN] t.bb: service bmashup.autopilot 2: not used")
              && strstr(t, "[PLUGIN] t.bm: service bmashup.boost 2: not used")
              && strstr(t, "[PLUGIN] t.race: service bmashup.boost 2: not used"),
              "the boost demo takes its two services; the others decline bmashup.boost");
        CHECK(t && strstr(t, "[PLUGIN t.bb] fill at race 5.0 s (bar 50.0 of 240.0): OK")
              && strstr(t, "[PLUGIN t.bb] status PENDING (OK), race 0, top-ups 0")
              && strstr(t, "[PLUGIN t.bb] status DONE (OK), race 0, top-ups 1: bar 50.0 -> 240.0 of 240.0")
              && !strstr(t, "[PLUGIN t.bb] fill at race 6.0") && !strstr(t, "[PLUGIN t.bb] fill at race 30.0"),
              "the boost demo's lines: one request with the bar, each status change");
        CHECK(t && strstr(t, "[PLUGIN t.bb] bar at race 0.5 s: 50.0 of 240.0") && !strstr(t, "[PLUGIN t.bb] bar at race 0.9 s")
              && strstr(t, "[PLUGIN t.bb] bar at race 1.6 s: 50.0 of 240.0") && strstr(t, "[PLUGIN t.bb] bar at race 8.0 s")
              && !strstr(t, "[PLUGIN t.bb] bar at race 8.5 s") && strstr(t, "[PLUGIN t.bb] bar at race 9.0 s: 200.0 of 240.0, boosting")
              && !strstr(t, "[PLUGIN t.bb] bar at race 1.0 s") && !strstr(t, "[PLUGIN t.bb] bar at race 12.0 s"),
              "the boost demo's bar lines: once a second of race time while racing, with boosting");
        /* the autopilot demo, continued (after the boost demo's checks: both read the same snapshots): race 1
         * engaged, race 2 a transient refusal asked again, race 3 a final refusal, race 4 at most 5 requests */
        {
            td_race_snapshot r;
            memset(&r, 0, sizeof r);
            r.struct_size = (uint32_t)sizeof r;
            r.state = TD_RACE_RACING;
            r.valid = TD_RACE_HAVE_CAR;
            s_bm_st.race = 1;
            s_bm_rc = BM_AP_OK;
            s_bm_st.state = BM_AP_STATE_ENGAGED;
            s_bm_st.engaged_races = 2;
            r.race_time_s = 9.0f;
            race_all(&r);
            CHECK(s_bm_engages == 2, "engaged in race 1: no more requests");
            /* race 2: the title's AI still holds the car first (a transient refusal): asked again a second later */
            s_bm_st.state = BM_AP_STATE_IDLE;
            s_bm_st.race = 2;
            s_bm_rc = BM_AP_AI_OWNED;
            r.race_time_s = 5.0f;
            race_all(&r);
            s_bm_st.state = BM_AP_STATE_REFUSED;
            s_bm_st.reason = BM_AP_AI_OWNED;
            r.race_time_s = 5.5f;
            race_all(&r);
            CHECK(s_bm_engages == 3, "race 2: AI_OWNED; not asked again within a second");
            s_bm_rc = BM_AP_OK;
            r.race_time_s = 6.0f;
            race_all(&r);
            CHECK(s_bm_engages == 4 && s_bm_req.race == 2, "race 2: asked again a second later, accepted");
            /* race 3: a refusal the race cannot outgrow: not asked again in that race */
            s_bm_st.state = BM_AP_STATE_IDLE;
            s_bm_st.reason = BM_AP_OK;
            s_bm_st.race = 3;
            s_bm_rc = BM_AP_NOT_IN_RACE;
            r.race_time_s = 5.0f;
            race_all(&r);
            s_bm_st.state = BM_AP_STATE_REFUSED;
            s_bm_st.reason = BM_AP_NOT_IN_RACE;
            for (int k = 6; k < 20; k++) {
                r.race_time_s = (float)k;
                race_all(&r);
            }
            CHECK(s_bm_engages == 5, "race 3: NOT_IN_RACE is not asked again (%d)", s_bm_engages);
            /* race 4: transient refusals: at most 5 requests */
            s_bm_st.state = BM_AP_STATE_IDLE;
            s_bm_st.race = 4;
            s_bm_rc = BM_AP_COUNTDOWN;
            for (int k = 5; k < 30; k++) {
                r.race_time_s = (float)k;
                race_all(&r);
            }
            CHECK(s_bm_engages == 10, "race 4: at most 5 requests a race (%d)", s_bm_engages);
            s_bm_rc = BM_AP_OK;
            s_bm_st.state = BM_AP_STATE_IDLE;
            s_bm_st.reason = BM_AP_OK;
        }
        fflush(stderr);
        free(t);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN t.bm] engaged in race 1 at 9.0 s (engaged race 2 of this process)")
              && strstr(t, "[PLUGIN t.bm] engage at race 5.0 s (race 2, request 1): AI_OWNED")
              && strstr(t, "[PLUGIN t.bm] engage at race 6.0 s (race 2, request 2): OK")
              && strstr(t, "[PLUGIN t.bm] engage at race 5.0 s (race 3, request 1): NOT_IN_RACE")
              && strstr(t, "[PLUGIN t.bm] engage at race 9.0 s (race 4, request 5): COUNTDOWN")
              && !strstr(t, "(race 4, request 6)") && !strstr(t, "(race 3, request 2)") && !strstr(t, "(race 1, request 2)"),
              "the autopilot demo's later races: one takeover a race, transient refusals asked again, at most 5");
        CHECK(state("t.bbna", why) == BO3_PLUGIN_NOT_APPROVED && t && !strstr(t, "[PLUGIN t.bbna]")
              && !strstr(t, "[PLUGIN] t.bbna: service"), "the boost demo not approved: never loaded, never offered anything");
        free(t);
        /* the private events demos: two independently loaded plugins subscribe
         * to the same event while they start; each counts it and logs its
         * count with the event's sequence once a second of race time */
        CHECK(state("t.eva", why) == BO3_PLUGIN_RUNNING && state("t.evb", why) == BO3_PLUGIN_RUNNING && s_nev_sub == 2
              && s_ev_sub[0].host != s_ev_sub[1].host, "both events demos run, each subscribed once (%d)", s_nev_sub);
        {
            bm_event ev;
            memset(&ev, 0, sizeof ev);
            ev.struct_size = (uint32_t)sizeof ev;
            ev.event = BM_EVENT_PLAYER_CAR_UPDATE;
            ev.car_phase = 1;                                           /* before the GO: counted, no line */
            ev.sequence = 7;
            ev_all(&ev);
            ev.car_phase = 2;
            for (int k = 0; k < 90; k++) {                              /* 1.5 s of updates at 60 a second */
                ev.sequence = 8 + (uint32_t)k;
                ev.step = 1000 + (uint32_t)k;
                ev.race_time_s = (float)k / 60.0f;
                ev_all(&ev);
            }
            ev.struct_size = 8;                                         /* too small for them: ignored */
            ev_all(&ev);
        }
        fflush(stderr);
        t = read_file(s_log);
        CHECK(t && strstr(t, "[PLUGIN] t.eva: service bmashup.events 1: used") && strstr(t, "[PLUGIN] t.evb: service bmashup.events 1: used")
              && strstr(t, "[PLUGIN t.eva] events demo A: subscribed to player car updates: 0")
              && strstr(t, "[PLUGIN t.evb] events demo B: subscribed to player car updates: 0")
              && strstr(t, "[PLUGIN] t.race: service bmashup.events 1: not used")
              && strstr(t, "[PLUGIN] t.bb: service bmashup.events 1: not used"),
              "the events demos take bmashup.events; the others decline it");
        CHECK(t && strstr(t, "[PLUGIN t.eva] events demo A: 2 car updates; sequence 8 step 1000 race 0.0 s")
              && strstr(t, "[PLUGIN t.evb] events demo B: 2 car updates; sequence 8 step 1000 race 0.0 s")
              && strstr(t, "[PLUGIN t.eva] events demo A: 62 car updates; sequence 68 step 1060 race 1.0 s")
              && strstr(t, "[PLUGIN t.evb] events demo B: 62 car updates; sequence 68 step 1060 race 1.0 s")
              && !strstr(t, "events demo A: 91") && !strstr(t, "events demo A: 32") && !strstr(t, "events demo A: 1 car"),
              "both demos: the same updates, the same sequence numbers, a line a second of race time");
        CHECK(state("t.evna", why) == BO3_PLUGIN_NOT_APPROVED && t && !strstr(t, "[PLUGIN t.evna]")
              && !strstr(t, "[PLUGIN] t.evna: service"), "an events demo not approved: never loaded, never offered anything");
        free(t);
        for (added = 0; added < 40; added++) {   /* GP-P4: the registry holds 32 (I3) */
            snprintf(name, sizeof name, "test.fill%02d", added);
            if (!bo3_plugins_service(name, 1, other))
                break;
        }
        CHECK(added == 26, "at most 32 services (6 offered, %d more taken)", added);   /* GP-P4 (I3) */
    }

    /* the approval file as the MODS page changes it: a module hashed without
     * loading it; written whole, read back; a file it would not write back
     * left as it is; the next start runs exactly what was approved */
    scenario("appr");
    {
        static char big[64 * 1024];
        char p[900], q[912], hex[65], got[65], w2[200], *before;     /* q: p and ".tmp" */
        static const char *const other = "abababababababababababababababababababababababababababababababab";
        static const char *const other2 = "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd";
        declare(b, sizeof b, 1, "bin/good" EXT);
        mod("m", "t.marker", b, "marker", "bin/good" EXT, 0);
        start(NULL, NULL, 0);                                   /* approvals.toml: approved = [] */
        snprintf(p, sizeof p, "%s/approvals.toml", s_dir);
        snprintf(q, sizeof q, "%s/mods/m/bin/good" EXT, s_dir);
        CHECK(state("t.marker", why) == BO3_PLUGIN_NOT_APPROVED && !loaded("marker"), "not approved, not loaded");
        CHECK(bo3_plugins_hash_module(index_of("t.marker"), hex, w2, sizeof w2) && !loaded("marker"),
              "hashed for an approval, never loaded (its start-up code did not run)");
        sha_of(q, got);
        CHECK(!strcmp(hex, got), "the hash is the module file's: %s", hex);
        CHECK(!bo3_plugins_hash_module(index_of("t.marker") + 99, got, w2, sizeof w2) && !got[0], "no such mod: no hash");
        CHECK(bo3_plugins_approvals() == BO3_APPROVALS_OK, "the file as start() wrote it: OK");
        CHECK(bo3_plugins_set_approval("t.marker", hex) && bo3_plugins_approvals_of("t.marker", got, sizeof got) == 1
              && !strcmp(got, hex) && bo3_plugins_approved_for("t.marker", hex), "approved: one entry, these bytes");
        CHECK(bo3_plugins_set_approval("t.other", other) && bo3_plugins_set_approval("t.marker", other2)
              && bo3_plugins_approvals_of("t.marker", got, sizeof got) == 1 && !strcmp(got, other2)
              && bo3_plugins_approvals_of("t.other", NULL, 0) == 1, "an approval replaces that mod's own, keeps the others");
        CHECK(bo3_plugins_set_approval("t.marker", NULL) && bo3_plugins_approvals_of("t.marker", NULL, 0) == 0
              && bo3_plugins_approvals_of("t.other", NULL, 0) == 1, "removed: only that mod's");
        CHECK(bo3_plugins_set_approval("t.marker", NULL), "removing what is not there: done, nothing to write");
        before = read_file(p);
        CHECK(!bo3_plugins_set_approval("Bad Id", hex) && !bo3_plugins_set_approval("t.marker", "abc")
              && !bo3_plugins_set_approval("t.marker", "ABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABAB")
              && !bo3_plugins_set_approval("t.x\", \"t.y sha256:00", hex) && !bo3_plugins_set_approval(NULL, hex),
              "a malformed id or hash (an entry that would end the string early among them): refused");
        t = read_file(p);
        CHECK(before && t && !strcmp(before, t), "refused: the file as it was");
        free(t);
        /* a write that fails: the file as it was */
        snprintf(q, sizeof q, "%s.tmp", p);
        MKDIR(q);
        CHECK(!bo3_plugins_set_approval("t.marker", hex), "a write that fails (its .tmp is a folder): not done");
        t = read_file(p);
        CHECK(t && !strcmp(before, t), "a failed write: the file as it was");
        free(t);
#if defined(_WIN32)
        _rmdir(q);
#else
        rmdir(q);
#endif
        free(before);
        /* a file the page would not write back, one that is not an approval file, none */
        write_file(p, "approved = [\"t.other sha256:abababababababababababababababababababababababababababababababab\", \"by hand\"]\n");
        CHECK(bo3_plugins_approvals() == BO3_APPROVALS_KEPT && !bo3_plugins_set_approval("t.marker", hex)
              && !bo3_plugins_set_approval("t.other", NULL), "an entry it would not keep: left as it is (KEPT)");
        t = read_file(p);
        CHECK(t && strstr(t, "by hand"), "KEPT: unchanged");
        free(t);
        write_file(p, "approved = [nope\n");
        CHECK(bo3_plugins_approvals() == BO3_APPROVALS_BAD && !bo3_plugins_set_approval("t.marker", hex),
              "not an approval file: left as it is (BAD)");
        t = read_file(p);
        CHECK(t && !strcmp(t, "approved = [nope\n"), "BAD: unchanged");
        free(t);
        bo3_plugins_approval_file("");
        CHECK(bo3_plugins_approvals() == BO3_APPROVALS_NONE && !bo3_plugins_set_approval("t.marker", hex), "no approval file: NONE");
        bo3_plugins_approval_file(p);
        remove(p);
        CHECK(bo3_plugins_approvals() == BO3_APPROVALS_ABSENT && bo3_plugins_set_approval("t.marker", hex)
              && bo3_plugins_approvals() == BO3_APPROVALS_OK, "none yet: made with the approval");
        /* at most 256 approvals */
        {
            size_t n = (size_t)snprintf(big, sizeof big, "approved = [");
            for (int k = 0; k < 256; k++)
                n += (size_t)snprintf(big + n, sizeof big - n, "%s\"t.k%03d sha256:%s\"", k ? ", " : "", k, other);
            snprintf(big + n, sizeof big - n, "]\n");
            write_file(p, big);
            CHECK(bo3_plugins_approvals() == BO3_APPROVALS_OK && !bo3_plugins_set_approval("t.marker", hex)
                  && bo3_plugins_set_approval("t.k000", other2), "256 approvals: no 257th; one replaced");
        }
        /* the next start runs exactly what was approved: other bytes in its
         * place are not run; the approved ones back, they are (a loaded
         * module is never unloaded, so its bytes change before it loads) */
        write_file(p, "approved = []\n");
        CHECK(bo3_plugins_set_approval("t.marker", hex), "approved again");
        snprintf(q, sizeof q, "%s/mods/m/bin/good" EXT, s_dir);
        {
            char from[800];
            module_path(from, sizeof from, "order_a");
            copy_file(from, q);
            start(NULL, NULL, 1);                               /* the file as written above */
            CHECK(state("t.marker", why) == BO3_PLUGIN_NOT_APPROVED && !bo3_plugins_was_approved(index_of("t.marker"))
                  && !loaded("order_a") && !loaded("marker"), "other bytes in its place: not approved, not run");
            module_path(from, sizeof from, "marker");
            copy_file(from, q);
        }
        start(NULL, NULL, 1);
        CHECK(state("t.marker", why) == BO3_PLUGIN_RUNNING && loaded("marker") && bo3_plugins_was_approved(index_of("t.marker")),
              "the approved bytes back: they run (%s)", why);
    }

    /* s7, the last start: two plugins that register on_shutdown (checked at exit) */
    scenario("s7");
    declare(b, sizeof b, 1, "bin/good" EXT);
    mod("good", "t.good", b, "good", "bin/good" EXT, 1);
    {
        char b2[400];
        declare(b2, sizeof b2, 1, "hello" EXT);
        mod("hello", "example.hello-plugin", b2, "hello", "hello" EXT, 1);
    }
    start(NULL, NULL, 0);
    CHECK(state("t.good", why) == BO3_PLUGIN_RUNNING && state("example.hello-plugin", why) == BO3_PLUGIN_RUNNING,
          "s7: both run (%s)", why);

    fflush(stderr);
    t = read_file(s_log);
    CHECK(t && strstr(t, "[PLUGIN example.hello-plugin] hello from API 1"), "the example's line is in the log");
    CHECK(t && strstr(t, "[PLUGIN t.good] warning: a line with?a break and a tab?in it"), "log lines are one line, prefixed, levelled");
    CHECK(t && strstr(t, "add \"t.notapproved sha256:"), "the log names the approval line to add");
    CHECK(t && strstr(t, "approval file not used"), "a bad approval file is reported");
    CHECK(t && strstr(t, "plugins are off (TAKEDAWN_PLUGINS=0)"), "the kill switch is reported");
    CHECK(t && strstr(t, "approval file path too long"), "F5: the too-long approvals path is reported");
    CHECK(t && strstr(t, "2 entries not used"), "F7: unused approval entries are reported");
    if (argc > 3 && t)
        write_file(argv[3], t);
    free(t);
    printf("plugins: %d passed, %d failed (temp %s)\n", s_pass, s_fail, s_tmp);
    return s_fail ? 1 : 0;
}
