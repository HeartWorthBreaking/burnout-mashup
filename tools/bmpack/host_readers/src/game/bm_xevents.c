/* G8-XE1 EXPERIMENTAL: medals of added events in the progress sidecar (bm_xevents.h). MUT=n (test builds only) compiles one
 * deliberate defect. G8-WT1: + bo3_xe_race_id_wt (the World Tour race-ID form) and bo3_xe_best (the list's medal icon). */
#include "bm_xevents.h"

#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

typedef struct xe {
    uint64_t id;
    bm_prog_key key;
    char modver[BM_PROG_MAX_MODVER + 1];
} xe;

static xe s_xe[BO3_XE_MAX];
static uint32_t s_n;
static bo3_xe_store_fn s_store;
static _Atomic uint32_t s_stats[3];

void bo3_xe_set_store(bo3_xe_store_fn fn)
{
    s_store = fn;
}

void bo3_xe_reset(void)
{
    s_n = 0;
    memset(s_stats, 0, sizeof s_stats);
}

uint64_t bo3_xe_race_id(const char *mod_id, const char *local_id)
{
    uint64_t h = 0xCBF29CE484222325ull;
    const char *parts[4] = {"bmashup.xevent/", mod_id, "/", local_id};
    for (int k = 0; k < 4; k++)
        for (const char *c = parts[k]; c && *c; c++) {
            h ^= (uint8_t)*c;
            h *= 0x100000001B3ull;
        }
    return (h & 0x00FFFFFFFFFFFFFFull) | 0xB300000000000000ull;
}

int bo3_xe_register(const char *mod_id, const char *mod_version, const char *local_id, uint64_t race_id, int type,
                    bo3_xe_known_fn known, char *why, size_t wn)
{
    xe e;
    memset(&e, 0, sizeof e);
    if (bm_prog_key_make(&e.key, BM_PROG_EVENT, mod_id, local_id) != BM_PROG_OK) {
        snprintf(why, wn, "\"%s\" / \"%s\" is not a valid event key (mod id; event id [A-Za-z0-9_-], 1..32)",
                 mod_id ? mod_id : "", local_id ? local_id : "");
        return 0;
    }
    if (type == BO3_XE_CRASH_TYPE) {
        snprintf(why, wn, "event %s: Crash-type events cannot be added; race-type, Face-Off, Road Rage, Eliminator and "
                 "Burning Lap events can (a Crash-type event's launch path is not audited, its junction record index at race "
                 "end, sub_0001EE80, is only guarded)", local_id);
        return 0;
    }
    if (type != BO3_XE_RACE_TYPE && type != BO3_XE_FACEOFF_TYPE && type != BO3_XE_ROADRAGE_TYPE &&
        type != BO3_XE_ELIMINATOR_TYPE && type != BO3_XE_BURNINGLAP_TYPE) {   /* C3-8 */
        snprintf(why, wn, "event %s: type %d is not one this build adds", local_id, type);
        return 0;
    }
    if (!known || known(race_id)) {
        snprintf(why, wn, "event %s: its race ID 0x%016llX is one the game already knows (or cannot be checked)", local_id,
                 (unsigned long long)race_id);
        return 0;
    }
    for (uint32_t i = 0; i < s_n; i++)
        if (s_xe[i].id == race_id || (!strcmp(s_xe[i].key.ns, e.key.ns) && !strcmp(s_xe[i].key.local, e.key.local))) {
            snprintf(why, wn, "event %s: its ID or its key is registered twice", local_id);
            return 0;
        }
    if (s_n == BO3_XE_MAX) {
        snprintf(why, wn, "more than %u added events", (unsigned)BO3_XE_MAX);
        return 0;
    }
    e.id = race_id;
    snprintf(e.modver, sizeof e.modver, "%s", mod_version ? mod_version : "");
    s_xe[s_n++] = e;
    return 1;
}

int bo3_xe_gen_medal(uint32_t lo, uint32_t hi, uint32_t medal, uint32_t profile)
{
    uint64_t id = (uint64_t)hi << 32 | lo;
    bm_prog *p = s_store ? s_store() : NULL;
    bm_prog_event ev;
    const xe *e = NULL;
    (void)profile;                              /* never written: the game's save keeps its layout */
    for (uint32_t i = 0; i < s_n; i++)
        if (s_xe[i].id == id)
            e = &s_xe[i];
#if MUT == 2
    if (!e && s_n)
        e = &s_xe[0];                           /* defect: any unknown ID is taken for an added event */
#endif
    if (!e) {
        atomic_fetch_add(&s_stats[1], 1);
        return 0;
    }
    if (medal > 3u)
        medal = 0;
    memset(&ev, 0, sizeof ev);
    if (p) {
        int g = bm_prog_get_event(p, &e->key, &ev);
        if (g == BM_PROG_NOT_FOUND)
            memset(&ev, 0, sizeof ev);          /* the first result of this event */
        else if (g != BM_PROG_OK)
            p = NULL;                           /* e.g. OPAQUE: a newer data version is never overwritten */
    }
    if (!p || !bm_prog_writable(p)) {
        atomic_fetch_add(&s_stats[2], 1);
        fprintf(stderr, "[XEVENTS] %s/%s: medal %u not recorded (no writable progress store)\n", e->key.ns, e->key.local,
                (unsigned)medal);
        return 0;
    }
    ev.attempts++;
#if MUT == 3
    ev.medal = (uint8_t)medal;                  /* defect: the last medal, not the best */
#else
    if (medal > ev.medal)
        ev.medal = (uint8_t)medal;
#endif
    if (ev.medal)
        ev.completed = 1;
#if MUT == 1
    if (bm_prog_put_event(p, &e->key, e->modver, &ev) != BM_PROG_OK) {   /* defect: put, never committed */
#else
    if (bm_prog_put_event(p, &e->key, e->modver, &ev) != BM_PROG_OK || bm_prog_commit(p, 0) != BM_PROG_OK) {
#endif
        atomic_fetch_add(&s_stats[2], 1);
        fprintf(stderr, "[XEVENTS] %s/%s: medal %u not recorded (the progress store refused the write)\n", e->key.ns,
                e->key.local, (unsigned)medal);
        return 0;
    }
    atomic_fetch_add(&s_stats[0], 1);
    fprintf(stderr, "[XEVENTS] %s/%s: medal %u recorded (best %u, attempts %u)\n", e->key.ns, e->key.local, (unsigned)medal,
            (unsigned)ev.medal, (unsigned)ev.attempts);
    return 1;
}

uint32_t bo3_xe_stats(uint32_t which)
{
    return which < 3 ? atomic_load(&s_stats[which]) : 0;
}

/* G8-WT1: base-40 as the game's sub_001AEAA0 (" -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_", 12 characters, space-padded) */
static int b40(const char *s, uint64_t *out)
{
    static const char k_al[] = " -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_";
    uint64_t v = 0;
    size_t n = strlen(s);
    if (n == 0 || n > 12)
        return 0;
    for (size_t i = 0; i < 12; i++) {
        char c = i < n ? s[i] : ' ';
        const char *p = c ? strchr(k_al, c) : NULL;
        if (!p)
            return 0;
        v = v * 40u + (uint64_t)(p - k_al);
    }
    *out = v;
    return 1;
}

int bo3_xe_race_id_wt(const char *track_id, uint32_t nn, uint64_t *out)
{
    return bo3_xe_race_id_wt_type(track_id, 'A', nn, out);
}

int bo3_xe_race_id_wt_type(const char *track_id, char letter, uint32_t nn, uint64_t *out)
{
    static const char k_d[] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    char s[13];
    if (!track_id || strlen(track_id) != 8 || track_id[2] != '_' || track_id[5] != '_' || nn >= 36u * 36u)
        return 0;
    if (letter != 'A' && letter != 'B' && letter != 'C' && letter != 'D' && letter != 'E')
        return 0;                               /* C3-8: race / Eliminator / Road Rage / Face-Off / Burning Lap only */
    for (int i = 0; i < 8; i++)
        if (i != 2 && i != 5 && !((track_id[i] >= 'A' && track_id[i] <= 'Z') || (track_id[i] >= '0' && track_id[i] <= '9')))
            return 0;
    s[0] = '0';
    s[1] = letter;                              /* the type letter (sub_00158340 reads character 1; 'A' race) */
    s[2] = '0';
    s[3] = '7';                                 /* element 07: none of the game's (its last one, 06, is cut at load) */
    s[4] = k_d[nn / 36u];
    s[5] = k_d[nn % 36u];
    s[6] = track_id[0];
    s[7] = track_id[1];
    s[8] = track_id[3];
    s[9] = track_id[4];
    s[10] = track_id[6];
    s[11] = track_id[7];
    s[12] = 0;
    return b40(s, out);
}

int bo3_xe_best(uint64_t race_id, uint32_t *medal, uint32_t *attempts)
{
    bm_prog *p = s_store ? s_store() : NULL;
    bm_prog_event ev;
    *medal = 0;
    *attempts = 0;
    for (uint32_t i = 0; i < s_n; i++)
        if (s_xe[i].id == race_id) {
            memset(&ev, 0, sizeof ev);
            if (!p || bm_prog_get_event(p, &s_xe[i].key, &ev) != BM_PROG_OK)
                return 0;
            *medal = ev.medal <= 3u ? ev.medal : 0u;
            *attempts = ev.attempts;
            return 1;
        }
    return 0;
}
