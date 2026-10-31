/* bm_tracks_progress.c - G8-CC1.2 EXPERIMENTAL: saved results for tracks added by mods (bm_tracks.h), kept in the progress
 * sidecar (content_count\sidecar: bm_progress), never in the game's save.
 *
 * Every added track gets a SHADOW: a 0x230-byte per-track record in guest memory (the game's own record layout, initialised
 * as the game initialises a fresh one) and the three per-track profile values the game keeps (+0x170 total, +0x20C and
 * +0x2A0 maxima). Wherever the game would address record -1 / profile slot -1 for the raced added track, the generated
 * code is pointed at that track's shadow instead (bo3_cc_gen_record) or the value is captured here (bo3_cc_gen_best /
 * bo3_cc_gen_total): the game's own code inserts results into the shadow and its own comparisons (the RECORD flags, the HUD
 * best lap, the race-end messages) read it. Retail tracks never reach any of this (their index is 0..35).
 *
 * Which added track: the race's track ID (0x73A190, read by the HUD / race-end readers) or the last raced track
 * (0x45B9B0, set by sub_0001EE80, read by the results flags).
 *
 * Persistence: <save dir>/bmashup/progress/<save folder>/Profile 1.bmprog (bm_progress), key (TRACK, the declaring mod's id,
 * the track ID), committed on the game's thread each time a result changes. Opened when the profile folder exists (at the
 * track list's load, or later at the first result). A sidecar that cannot be used (FAILED / NEWER / another profile / locked)
 * leaves the shadows fresh and nothing is written (logged once).
 *
 * cand2 (D1): the table holds every track the track list can hold (BO3_CC_CAP = 383, G8-TL; was 16): a host table
 * (static, BO3_CC_CAP x sizeof(cp_track)), no guest memory. A track beyond it (unreachable through bo3_cc_append, which
 * refuses more than BO3_CC_CAP entries including the 36 retail ones) is refused: logged once, counted (stats 4); its
 * results are not saved and the game's insert is skipped as before. MUT=n (test builds only): 41 the old 16-entry table,
 * 42 refused silently, 43 logged on every refusal, 44 the refusal not counted. */
#include "bm_tracks.h"
#include "bm_progress.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#endif

#ifndef MUT
#define MUT 0
#endif

#if defined(BO3_CC_PROGRESS_TEST_MAX)  /* tests only: a smaller table, to reach the refusal */
#define CP_MAX         ((uint32_t)(BO3_CC_PROGRESS_TEST_MAX))
#elif MUT == 41
#define CP_MAX         16u               /* defect: the old table (added tracks 17+ get no progress) */
#else
#define CP_MAX         BO3_CC_CAP        /* cand2 (D1): every track the track list can hold (383) */
#endif
_Static_assert(CP_MAX >= 1u && CP_MAX <= BO3_CC_CAP, "the progress table holds at most the track list's tracks");
#define CP_RACE_TRACK  0x0073A190u       /* the race's track ID (u64) */
#define CP_LAST_TRACK  0x0045B9B0u       /* the last raced track ID (u64), written by sub_0001EE80 */
#define CP_FRESH_TIME  0x003B172Cu       /* the fresh record's category-0 time (sub_0001F450) */

extern ptrdiff_t g_xbox_mem_offset;

typedef struct cp_track {
    uint64_t id;
    char ns[BM_PROG_MAX_NS + 1], local[BM_PROG_MAX_LOCAL + 1], modver[BM_PROG_MAX_MODVER + 1];
    uint32_t shadow_va;
    bm_prog_track rec;                   /* races, total_170, max_20c, max_2a0 (shadow bytes copied at commit) */
    int loaded;
} cp_track;

static cp_track s_t[CP_MAX];
static uint32_t s_n;
static char s_save_dir[1024];
static bm_prog *s_store;
static int s_store_failed;
static uint32_t s_redirects, s_captures, s_commits, s_commit_errors, s_refused;

static uint8_t *G(uint32_t va) { return (uint8_t *)((uintptr_t)g_xbox_mem_offset + va); }
static uint64_t rd64(uint32_t va) { uint64_t v; memcpy(&v, G(va), 8); return v; }

void bo3_cc_fresh_record(uint8_t *rec, uint32_t fresh_time_bits)
{
    static const uint8_t k_marker[10] = {'#', 0, '@', 0, '|', 0, '^', 0, 0, 0};   /* L"#@|^" */
    memset(rec, 0, BO3_CC_RECORD_SIZE);
    for (uint32_t mode = 0; mode < 4u; mode++)
        for (uint32_t k = 0; k < 5u; k++) {
            uint8_t *e = rec + mode * 0x8Cu + k * 0x1Cu;
            memcpy(e, k_marker, sizeof k_marker);
            e[0x14] = 0xFF;              /* owner: none (the game's reset value) */
            e[0x15] = 0xFF;
            if (mode == 0)
                memcpy(e + 0x18, &fresh_time_bits, 4);
        }
}

void bo3_cc_set_save_dir(const char *dir)
{
    snprintf(s_save_dir, sizeof s_save_dir, "%s", dir ? dir : "");
}

/* the first save folder holding "Profile 1" under <save dir>/UDATA/4541005b */
static int profile_folder(char *out, size_t n)
{
#ifdef _WIN32
    char pat[1200];
    WIN32_FIND_DATAA fd;
    HANDLE h;
    int found = 0;
    snprintf(pat, sizeof pat, "%s/UDATA/4541005b/*", s_save_dir);
    h = FindFirstFileA(pat, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    do {
        char prof[1400];
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || fd.cFileName[0] == '.')
            continue;
        snprintf(prof, sizeof prof, "%s/UDATA/4541005b/%s/Profile 1", s_save_dir, fd.cFileName);
        if (GetFileAttributesA(prof) != INVALID_FILE_ATTRIBUTES) {
            snprintf(out, n, "%s", fd.cFileName);
            found = 1;
        }
    } while (!found && FindNextFileA(h, &fd));
    FindClose(h);
    return found;
#else
    (void)out; (void)n;
    return 0;
#endif
}

static void load_into_shadows(void)
{
    for (uint32_t i = 0; i < s_n; i++) {
        bm_prog_key k;
        bm_prog_track t;
        if (bm_prog_key_make(&k, BM_PROG_TRACK, s_t[i].ns, s_t[i].local) != BM_PROG_OK)
            continue;
        if (bm_prog_get_track(s_store, &k, &t) == BM_PROG_OK) {
            s_t[i].rec = t;
            if (t.shadow_len == BO3_CC_RECORD_SIZE)
                memcpy(G(s_t[i].shadow_va), t.shadow, BO3_CC_RECORD_SIZE);
            s_t[i].loaded = 1;
            fprintf(stderr, "[TRACKS] saved results of %s loaded from the progress sidecar: %u races, total %u, maxima %.2f / %.2f\n",
                    s_t[i].local, (unsigned)t.races, (unsigned)t.total_170, (double)t.max_20c, (double)t.max_2a0);
        }
    }
}

/* GP-VEH1: the progress folder and profile id the track sidecar uses (created as open_store creates them), for the paint
 * sidecar "Profile 1 veh.bmprog" next to it. 1 ok, 0 no save dir / profile folder yet. */
int bo3_cc_progress_location(char *dir, size_t dn, char *prof, size_t pn)
{
    char folder[260];
    if (!s_save_dir[0] || !profile_folder(folder, sizeof folder))
        return 0;
#ifdef _WIN32
    {
        const char *alt = getenv("BMASHUP_PROGRESS_DIR");
        if (alt && *alt) {
            snprintf(dir, dn, "%s", alt);
        } else {
            snprintf(dir, dn, "%s/bmashup", s_save_dir);
            CreateDirectoryA(dir, NULL);
            snprintf(dir, dn, "%s/bmashup/progress", s_save_dir);
        }
        CreateDirectoryA(dir, NULL);
        snprintf(dir + strlen(dir), dn - strlen(dir), "/%s", folder);
        CreateDirectoryA(dir, NULL);
    }
#else
    snprintf(dir, dn, "%s/bmashup/progress/%s", s_save_dir, folder);
#endif
    snprintf(prof, pn, "4541005b/%s/Profile 1", folder);
    return 1;
}

static int open_store(void)
{
    char folder[260], dir[1400], prof[400];
    bm_prog_report r;
    if (s_store)
        return 1;
    if (s_store_failed || !s_save_dir[0] || !profile_folder(folder, sizeof folder))
        return 0;
#ifdef _WIN32
    {   /* BMASHUP_PROGRESS_DIR (opt-in, tests): the progress folder somewhere else than <save dir>/bmashup/progress, so a
         * later process with a fresh copy of the save sees the same sidecar */
        const char *alt = getenv("BMASHUP_PROGRESS_DIR");
        if (alt && *alt) {
            snprintf(dir, sizeof dir, "%s", alt);
        } else {
            snprintf(dir, sizeof dir, "%s/bmashup", s_save_dir);
            CreateDirectoryA(dir, NULL);
            snprintf(dir, sizeof dir, "%s/bmashup/progress", s_save_dir);
        }
        CreateDirectoryA(dir, NULL);
        snprintf(dir + strlen(dir), sizeof dir - strlen(dir), "/%s", folder);
        CreateDirectoryA(dir, NULL);
    }
#endif
    snprintf(prof, sizeof prof, "4541005b/%s/Profile 1", folder);
    bm_prog_open(bm_prog_io_native(), dir, "Profile 1", prof, 0, &s_store, &r);
    fprintf(stderr, "[TRACKS] progress sidecar %s/Profile 1.bmprog: %s (generation %llu, %u records%s%s)\n", dir,
            bm_prog_status_name(r.status), (unsigned long long)r.generation, (unsigned)r.records, r.why[0] ? "; " : "", r.why);
    if (!s_store || !bm_prog_writable(s_store)) {
        /* not usable: results of added tracks are not saved this session (the files are left as they are) */
        if (s_store && (r.status == BM_PROG_LOCKED || r.status == BM_PROG_NEWER || r.status == BM_PROG_FAILED ||
                        r.status == BM_PROG_PROFILE_MISMATCH))
            load_into_shadows();         /* a readable store still shows its results; nothing is written */
        s_store_failed = 1;
        return 0;
    }
    load_into_shadows();
    return 1;
}

void bo3_cc_progress_add(const char *mod_id, const char *mod_ver, uint64_t id, const char *id_text, uint32_t shadow_va)
{
    cp_track *t;
    uint32_t fresh;
    if (!g_xbox_mem_offset)
        return;
    if (s_n >= CP_MAX) {                 /* cand2 (D1): refused, logged once, counted (stats 4) */
        static int logged;
#if MUT != 44
        s_refused++;
#endif
#if MUT == 42
        (void)logged;                    /* defect: refused silently */
#elif MUT == 43
        (void)logged;                    /* defect: logged on every refusal */
        fprintf(stderr, "[TRACKS] progress: track %s of mod %s not tracked (limit %u): its results are not saved\n",
                id_text, mod_id, (unsigned)CP_MAX);
#else
        if (!logged++)
            fprintf(stderr, "[TRACKS] progress: track %s of mod %s not tracked (limit %u): its results are not saved; "
                    "further refusals are counted, not logged\n", id_text, mod_id, (unsigned)CP_MAX);
#endif
        return;
    }
    t = &s_t[s_n++];
    memset(t, 0, sizeof *t);
    t->id = id;
    snprintf(t->ns, sizeof t->ns, "%s", mod_id);
    snprintf(t->local, sizeof t->local, "%s", id_text);
    snprintf(t->modver, sizeof t->modver, "%s", mod_ver && *mod_ver ? mod_ver : "0");
    t->shadow_va = shadow_va;
    t->rec.best_car = 0xFFFF;
    memcpy(&fresh, G(CP_FRESH_TIME), 4);
    bo3_cc_fresh_record(G(shadow_va), fresh);
}

void bo3_cc_progress_start(void)
{
    if (s_n)
        open_store();
}

static cp_track *current(void)
{
    uint64_t a, b;
    if (!g_xbox_mem_offset || !s_n)
        return NULL;
    a = rd64(CP_RACE_TRACK);
    b = rd64(CP_LAST_TRACK);
    for (uint32_t i = 0; i < s_n; i++)
        if (s_t[i].id == a)
            return &s_t[i];
    for (uint32_t i = 0; i < s_n; i++)
        if (s_t[i].id == b)
            return &s_t[i];
    return NULL;
}

uint32_t bo3_cc_current_shadow(void)
{
    cp_track *t = current();
    if (t && !s_redirects++)
        fprintf(stderr, "[TRACKS] the game's per-track record of %s is its shadow at 0x%08X (not record -1)\n", t->local,
                (unsigned)t->shadow_va);
    return t ? t->shadow_va : 0;
}

/* G8-CC1.3: the records screen (sub_000EAC60) names the track it shows (its own ID, not the raced one): record -1 of THAT
 * track, when it is an added one, is its shadow; anything else as bo3_cc_gen_record */
uint32_t bo3_cc_gen_record_for(uint32_t rec_va, uint32_t id_lo, uint32_t id_hi)
{
    uint64_t id = (uint64_t)id_lo | (uint64_t)id_hi << 32;
#if MUT != 10
    if (rec_va == BO3_CC_RECORD_MINUS1)
        for (uint32_t i = 0; i < s_n; i++)
            if (s_t[i].id == id)
                return s_t[i].shadow_va;
#else
    (void)id;
#endif
    return bo3_cc_gen_record(rec_va);
}
static void commit(cp_track *t, const char *why)
{
    bm_prog_key k;
    if (!open_store())
        return;
    if (bm_prog_key_make(&k, BM_PROG_TRACK, t->ns, t->local) != BM_PROG_OK)
        return;
    t->rec.shadow_len = BO3_CC_RECORD_SIZE;
    memcpy(t->rec.shadow, G(t->shadow_va), BO3_CC_RECORD_SIZE);
    if (bm_prog_put_track(s_store, &k, t->modver, &t->rec) != BM_PROG_OK || bm_prog_commit(s_store, 0) != BM_PROG_OK) {
        if (!s_commit_errors++)
            fprintf(stderr, "[TRACKS] progress sidecar: the results of %s could not be saved (%s)\n", t->local, why);
        return;
    }
    s_commits++;
    fprintf(stderr, "[TRACKS] progress sidecar: results of %s saved (%s; %u races, total %u, maxima %.2f / %.2f)\n", t->local, why,
            (unsigned)t->rec.races, (unsigned)t->rec.total_170, (double)t->rec.max_20c, (double)t->rec.max_2a0);
}

/* sub_0001BA00 (site 0, +0x20C) / sub_0001BAF0 (site 1, +0x2A0): the game keeps the larger value; for an added track the
 * same comparison on its shadow cell (C: `v > cell` is false for NaN, as the game's jbe). 1 = the game must not write. */
int bo3_cc_gen_best(uint32_t site, uint32_t index, float v)
{
    cp_track *t;
    float *cell;
    if ((int32_t)index >= 0)
        return 0;
    t = current();
    if (!t)
        return bo3_cc_gen_skip(site, index);
    cell = site == 0 ? &t->rec.max_20c : &t->rec.max_2a0;
#if MUT != 7
    if (v > *cell) {
#else
    if (v != *cell) {                    /* defect: the cell is overwritten by any value, not kept at the maximum */
#endif
        *cell = v;
        s_captures++;
        commit(t, site == 0 ? "maximum +0x20C" : "maximum +0x2A0");
    }
    return 1;
}

/* sub_0001B820 (+0x170): the game skips slot -1 itself; for an added track the amount is added to its shadow total */
void bo3_cc_gen_total(uint32_t index, uint32_t add)
{
    cp_track *t;
    if ((int32_t)index >= 0 || !(t = current()) || !add)
        return;
    t->rec.total_170 += add;
    s_captures++;
    commit(t, "total +0x170");
}

/* sub_0001EE80's insert path: 1 = skip (an added track without a shadow), 0 = insert into the shadow */
int bo3_cc_gen_insert_skip(uint32_t index)
{
    if ((int32_t)index >= 0)
        return 0;
    if (current())
        return 0;
    return bo3_cc_gen_skip(2u, index);
}

/* after sub_0001F680 (the game resets every record's owner bytes to 0xFF at race end): the same for every shadow */
void bo3_cc_gen_race_end_reset(void)
{
#if MUT != 8
    for (uint32_t i = 0; i < s_n; i++)
        for (uint32_t e = 0; e < 20u; e++)
            G(s_t[i].shadow_va)[(e / 5u) * 0x8Cu + (e % 5u) * 0x1Cu + 0x14u] = 0xFF;   /* category e/5, entry e%5: owner */
#endif
}

/* sub_0001EE80's record pointer just before the game's insert (sub_0001ECE0): record -1 of the raced added track becomes its
 * shadow, and the result is marked to be saved when the function ends */
static cp_track *s_pending;

uint32_t bo3_cc_gen_insert_record(uint32_t rec_va)
{
    cp_track *t;
#if MUT == 9
    (void)t;
    return rec_va;                       /* defect: the insert goes to record -1 */
#else
    if (rec_va != BO3_CC_RECORD_MINUS1 || !(t = current()))
        return rec_va;
    s_pending = t;
    return t->shadow_va;
#endif
}

/* the end of sub_0001EE80 (every call, retail too): saves an added track's result inserted in this call */
void bo3_cc_gen_recorded(void)
{
    cp_track *t = s_pending;
    if (!t)
        return;
    s_pending = NULL;
    t->rec.races++;
    commit(t, "race recorded");
}

uint32_t bo3_cc_progress_stats(uint32_t which)
{
    return which == 0 ? s_redirects : which == 1 ? s_captures : which == 2 ? s_commits : which == 4 ? s_refused :
           s_commit_errors;
}

/* G8-WT1: the sidecar store this module opens (on demand; NULL when there is none, a read-only store when it cannot be
 * written): ONE store for the results of added tracks and the medals of added events (bm_xevents.c's store provider) */
bm_prog *bo3_cc_progress_store(void)
{
    open_store();
    return s_store;
}

#ifdef BO3_TRACKS_GAME
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

/* fail closed instead of a path the game itself cannot run: 1 = World Tour / career found no stage record for the track
 * (sub_0005F0A0 would use page 0), 2 = an online / system-link track list with no track of the class (sub_0009ADB0 would
 * divide by zero). Retail data never reaches either; an added track can. */
void bo3_cc_gen_unsupported(uint32_t what)
{
    const char *m = what == 1 ? "World Tour / career found no stage record for the selected track (an added track is not "
                                "supported there)" :
                                "an online / system-link track list has no track of the selected region (an added track is "
                                "not supported there)";
    fprintf(stderr, "[TRACKS] FATAL: %s; stopping instead of using invalid data (code 94)\n", m);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: this mode does not support an added track", "%s.\n\nChoose the track in Single Event Race.", m);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(94);
}
#endif
