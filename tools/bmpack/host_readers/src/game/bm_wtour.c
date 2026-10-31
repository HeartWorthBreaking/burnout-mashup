/* G8-WT1 EXPERIMENTAL: race events added by mods to World Tour locations' event lists (bm_wtour.h). WT_MUT=n (test builds
 * only) compiles one deliberate defect. G8-WT2: + W8 (the track Gamedata header lookup alias). Platform EV: N events from
 * any number of mods (BO3_WT_MAX, the free rows of the 18 race locations), several per location within its 6 rows, W9 (the
 * list's race-ID cell follows the cursor's host row). All guest access goes through bm_guest.c (the runtime's mappings).
 * WT_MUT 1..12 keep G8-WT2's meaning; 13..20 are the EV defects (run_ev_tests.py).
 * GP-WT4 (platform 0.1.5): events at the location of a fourth World Tour region (bm_wt4.h) - region index 3 in this
 * module's tables (s_loc[3][0]), listed while the map page shows that region (bo3_wt4_active); the location's retail count
 * is 0, so its list is all added rows (<= 6). WT_MUT 21: the fourth region's events also listed on the donor map's own
 * first location (W2 without the active test).
 * main21 C3-8 (notes\C3_8_WORLD_TOUR_TYPES_RE.md): the add line's type ": race | faceoff | roadrage | eliminator |
 * burninglap" (k_type: event +0x30, race +0x14, the race-ID letter, the donor of that type, the W8 record); Face-Off,
 * Eliminator and Burning Lap run on their donor's own (retail) track in this phase; Road Rage on an added track with the
 * Single Event record OFFRRGEF as the W8 fallback; ": crash" refused (launch-path audit pending). WT_MUT 22..26 = the C3-8
 * defects (tests\p46\run_wt_types.py). */
#include "bm_wtour.h"
#include "bm_wt4.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_names.h"
#include "bm_regions.h"
#include "bm_tracks.h"
#include "bm_xevents.h"
#include "recomp_cfg.h"

#ifndef WT_MUT
#define WT_MUT 0
#endif

#define WT_PREFIX     "bmashup.extra_events"
#define G_SLOTS       0x0039DF38u           /* u64[73] race IDs; values < 7 = Grand Prix g */
#define G_GP_COUNT    0x0039E778u           /* u32[7] */
#define G_GP_LIST     0x003ED0F8u           /* u32[7] -> u64[] */
#define G_JUNCTIONS   0x0039D870u           /* u64[100] */
#define G_LOC_IDS     0x0039E798u           /* u64[] race location IDs ("US_P1"), region bases 0 / 6 / 0xE */
#define G_STAGE_PTR   0x004D41D4u           /* Data\stagehed.bin's buffer */
#define ST_COUNT      0x260u
#define ST_RECS       0x278u
#define ST_SIZE       0x3E0u
#define ST_TRACK      0x390u
#define ST_RACE       0x398u
#define M_JFLAG       0x00550886u           /* menu +0x8E6: junction list */
#define M_REBUILD     0x00550887u           /* menu +0x8E7: re-render */
#define M_CURSOR      0x005501F0u           /* menu +0x250: the list cursor (u16) */
#define M_REGION      0x005501F4u           /* menu +0x254 */
#define M_VALUE       0x00550204u           /* menu +0x264: the location value */
#define M_TEXTS       0x0055066Cu           /* u32[13] cached row texts */
#define M_ITEMS       0x00550044u           /* item records, 0x10 each; +0xC = the item (slot) */
#define TEXT_UNKNOWN  0x4E9u                /* "Unknown Track" */
#define TEXT_SELECT_EVENT 0xF5u            /* P3 W7: "SELECT EVENT" (retail) when the host texts are not readable */
#define POW40_7       163840000000ull       /* 40^7: a track ID's last 7 base-40 digits */
#define EL_BYTES      0xB0u                 /* 7 x 0x18 element records, rounded to 16 */
#define EV_BYTES      (0x40u + 0x20u + ST_SIZE)   /* per event: event, race, stage copy */
#define MAX_LOCS      8u                    /* race locations per region (6 / 8 / 4; GP-WT4: 1) */
#define M_LOCIDX      0x0055021Cu           /* GP-WT4: menu +0x27C, the map's location index */
#define WT4           3u                    /* GP-WT4: this module's index of the fourth region */

_Static_assert(BO3_WT_MAX <= BO3_XE_MAX, "every added World Tour event is registered with XE1");
_Static_assert(BO3_WT_MAX <= BO3_NM_EVENTS_MAX, "every added World Tour event has its text slots (P3)");
_Static_assert(BO3_WT_HELP_MAX < BO3_NM_EVENT_TEXT && BO3_WT_NAME_MAX < BO3_NM_EVENT_TEXT, "event texts fit (P3)");
_Static_assert(EL_BYTES >= 7u * 0x18u, "the element array: 6 runtime elements + the host element");

static const uint32_t k_loc_base[3] = {0u, 6u, 0xEu}, k_race_locs[4] = {6u, 8u, 4u, BO3_WT4_LOCS};
static const char *const k_region[4] = {"USA", "Europe", "Asia", "fourth World Tour region"};

/* main21 C3-8 (notes\C3_8_WORLD_TOUR_TYPES_RE.md s1 / s4): the event types an added event may have. ev = event +0x30, rt =
 * race +0x14 (the logic sub_0005F0A0 sets up), letter = race-ID character 1 (sub_00158340), xe = the XE1 type.
 * own_track: phase 1, the event runs on its donor's own (retail) track, so its Gamedata record is the donor's own (W8 alias 1
 * = 2 = the donor ID): Eliminator (laps 5), Burning Lap (track-specific targets), Face-Off (2 drivers) have no Single Event
 * record of their type. se = the W8 fallback (3), a Single Event record on every track: race OFFSGRCF, Road Rage OFFRRGEF;
 * NULL = none (the donor's own record or a named stop). Crash (event 0xB, race 6, 'G') is refused at the parse: its launch
 * path (sub_00066C40's jflag-0 branch) and junction record are not audited. */
typedef struct wt_type {
    const char *name, *label;
    uint32_t ev, rt;
    char letter;
    int xe, own_track;
    const char *se;
} wt_type;
enum { WT_RACE = 0, WT_FACEOFF, WT_ROADRAGE, WT_ELIMINATOR, WT_BURNINGLAP, WT_TYPES };
static const wt_type k_type[WT_TYPES] = {
    {"race", "race", 1u, 0u, 'A', BO3_XE_RACE_TYPE, 0, "OFFSGRCF"},
    {"faceoff", "Face-Off", 8u, 0u, 'D', BO3_XE_FACEOFF_TYPE, 1, NULL},
    {"roadrage", "Road Rage", 7u, 3u, 'C', BO3_XE_ROADRAGE_TYPE, 0, "OFFRRGEF"},
    {"eliminator", "Eliminator", 6u, 1u, 'B', BO3_XE_ELIMINATOR_TYPE, 1, NULL},
    {"burninglap", "Burning Lap", 9u, 4u, 'E', BO3_XE_BURNINGLAP_TYPE, 1, NULL},
};

typedef struct wt_ev {
    char mod[BM_PROG_MAX_NS + 1], ver[BM_PROG_MAX_MODVER + 1], local[BM_PROG_MAX_LOCAL + 1];
    char key[BM_PROG_MAX_NS + BM_PROG_MAX_LOCAL + 2];
    char track_s[13], loc_s[13];
    char name[BO3_WT_NAME_MAX + 1], help[BO3_WT_HELP_MAX + 1];   /* P3 (P-11): version 2 texts, "" none */
    uint64_t track, loc, stage_from;
    uint32_t type;                          /* C3-8: k_type index (WT_RACE without a ": type") */
    /* resolved (W1) */
    uint32_t region, value, rank;
    uint64_t id, stage_id;
    uint32_t event, race, stage, stage_buf;
    int registered;
} wt_ev;

typedef struct wt_loc {
    uint32_t k, ev[BO3_WT_ROWS];            /* resolved: the location's events in key order */
    uint32_t n0;                            /* W2: the game's own count (the first host row) */
    int listed;                             /* W2 appended the rows on the current map build */
} wt_loc;

static wt_ev s_ev[BO3_WT_MAX];
static uint32_t s_n;
static wt_loc s_loc[4][MAX_LOCS];          /* GP-WT4: [3] = the fourth region's location(s) */
static bo3_wt_alloc_fn s_alloc;
static bo3_wt_fail_fn s_fail;

static int s_resolved, s_installed;
static uint32_t s_block, s_elems, s_root;
static uint32_t s_stats[BO3_WT_STATS];
static uint32_t s_logged, s_loc_logged;

/* ---------------------------------------------------------------- guest access (bm_guest.c) */
static int rd32(uint32_t va, uint32_t *v) { return bo3_guest_rd32(va, v); }
static int rd64(uint32_t va, uint64_t *v) { return bo3_guest_read(va, v, 8); }
static int rd8(uint32_t va, uint8_t *v) { return bo3_guest_read(va, v, 1); }
static int rd16(uint32_t va, uint16_t *v) { return bo3_guest_read(va, v, 2); }
static int wr32(uint32_t va, uint32_t v) { return bo3_guest_wr32(va, v); }

static void once(uint32_t bit, const char *fmt, const char *a, unsigned b)
{
    if (s_logged & bit)
        return;
    s_logged |= bit;
    fprintf(stderr, fmt, a, b);
}

static void fail(int code, const char *why)
{
    s_stats[BO3_WT_ST_REFUSED]++;
    fprintf(stderr, "[WT] refused (code %d): %s\n", code, why);
    if (s_fail)
        s_fail(code, why);
}

void bo3_wt_set_alloc(bo3_wt_alloc_fn fn) { s_alloc = fn; }
void bo3_wt_set_fail(bo3_wt_fail_fn fn) { s_fail = fn; }

void bo3_wt_reset(void)
{
    memset(s_ev, 0, sizeof s_ev);
    memset(s_loc, 0, sizeof s_loc);
    s_n = 0;
    s_resolved = s_installed = 0;
    s_block = s_elems = s_root = 0;
    s_logged = s_loc_logged = 0;
    memset(s_stats, 0, sizeof s_stats);
    bo3_nm_event_texts_reset();                 /* P3: the event texts are registered by the parse */
}

uint32_t bo3_wt_count(void) { return s_n; }
uint64_t bo3_wt_race_id_at(uint32_t i) { return s_resolved && i < s_n ? s_ev[i].id : 0; }
uint32_t bo3_wt_event_va_at(uint32_t i) { return s_installed && i < s_n ? s_ev[i].event : 0; }
uint32_t bo3_wt_stage_va_at(uint32_t i) { return i < s_n && s_ev[i].stage_buf ? s_ev[i].stage : 0; }
const char *bo3_wt_key_at(uint32_t i) { return i < s_n ? s_ev[i].key : ""; }
const char *bo3_wt_location_at(uint32_t i) { return i < s_n ? s_ev[i].loc_s : ""; }
const char *bo3_wt_name_at(uint32_t i) { return i < s_n ? s_ev[i].name : ""; }
const char *bo3_wt_help_at(uint32_t i) { return i < s_n ? s_ev[i].help : ""; }
int bo3_wt_row_at(uint32_t i)
{
    const wt_loc *L;
    if (!s_resolved || i >= s_n)
        return -1;
    L = &s_loc[s_ev[i].region][s_ev[i].value];
    return L->listed ? (int)(L->n0 + s_ev[i].rank) : -1;
}
uint64_t bo3_wt_race_id(void) { return bo3_wt_race_id_at(0); }
uint32_t bo3_wt_event_va(void) { return bo3_wt_event_va_at(0); }
uint32_t bo3_wt_stage_va(void) { return bo3_wt_stage_va_at(0); }
uint32_t bo3_wt_elements_va(void) { return s_installed ? s_elems : 0; }
int bo3_wt_installed(void) { return s_installed; }
uint32_t bo3_wt_stats(uint32_t which) { return which < BO3_WT_STATS ? s_stats[which] : 0; }

/* ---------------------------------------------------------------- declaration */
static char *trim(char *s)
{
    char *e;
    while (*s == ' ')
        s++;
    for (e = s + strlen(s); e > s && e[-1] == ' ';)
        *--e = 0;
    return s;
}

static int location_ok(const char *s, uint64_t *out)
{
    /* GP-WT4: any two letters (a fourth region's location, e.g. OC_L1, is checked against [bmashup.world_tour] at the load) */
    if (strlen(s) != 5 || s[2] != '_' || !(s[0] >= 'A' && s[0] <= 'Z') || !(s[1] >= 'A' && s[1] <= 'Z'))
        return 0;
    for (int i = 3; i < 5; i++)
        if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9')))
            return 0;
    return bo3_cc_encode(s, out);
}

static int region_of_letters(const char *s)
{
    return !strncmp(s, "US", 2) ? 0 : !strncmp(s, "EU", 2) ? 1 : !strncmp(s, "AS", 2) ? 2 :
           bo3_wt4_location_known(s) ? (int)WT4 : -1;
}

/* C3-8: the k_type index of an add line's type word, WT_TYPES when it is not one */
static uint32_t type_of_name(const char *ty)
{
    for (uint32_t t = 0; t < WT_TYPES; t++)
        if (!strcmp(ty, k_type[t].name))
            return t;
    return WT_TYPES;
}

static int find_key(const char *mod, const char *local, uint32_t upto)
{
    for (uint32_t i = 0; i < upto; i++)
        if (!strcmp(s_ev[i].mod, mod) && !strcmp(s_ev[i].local, local))
            return (int)i;
    return -1;
}

int bo3_wt_parse(const char *mod_id, const char *mod_version, const char *text, size_t n, char *why, size_t wn)
{
    char err[200];
    size_t plen = strlen(WT_PREFIX), na = 0, ns;
    recomp_cfg *cfg;
    char *buf;
    int ok = 1, present = 0;
    long long ver = 0;
    uint32_t first = s_n, cnt = s_n;
    bm_prog_key k;

    if (s_resolved) {
        snprintf(why, wn, "the World Tour events were already resolved (a declaration after the game's PrgData load)");
        return 0;
    }
    buf = (char *)malloc(n + 1);
    if (!buf) {
        snprintf(why, wn, "no memory");
        return 0;
    }
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    if (!cfg) {
        snprintf(why, wn, "mod.toml: %s", err);
        return 0;
    }
    for (size_t i = 0; ok && i < recomp_cfg_count(cfg); i++) {
        const char *key = recomp_cfg_key_at(cfg, i);
        if (strncmp(key, WT_PREFIX, plen) != 0 || (key[plen] != 0 && key[plen] != '.'))
            continue;
        present = 1;
        if (key[plen] == 0 || (strcmp(key, WT_PREFIX ".version") && strcmp(key, WT_PREFIX ".add") &&
                               strcmp(key, WT_PREFIX ".stage") && strcmp(key, WT_PREFIX ".names") &&
                               strcmp(key, WT_PREFIX ".help"))) {
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 2: version, add, stage, names, help)", key,
                     WT_PREFIX);
            ok = 0;
        }
    }
    if (!ok || !present) {
        recomp_cfg_free(cfg);
        return ok;
    }
    ver = recomp_cfg_type_of(cfg, WT_PREFIX ".version") == RCFG_INT ? recomp_cfg_int(cfg, WT_PREFIX ".version", 0) : -1;
    if (ver != 1 && ver != 2) {                 /* P3: version 2 = + names, help */
        snprintf(why, wn, "%s.version is not one this build reads (versions 1 and 2; 2 adds names and help)", WT_PREFIX);
        ok = 0;
    } else if (ver == 1 && (recomp_cfg_type_of(cfg, WT_PREFIX ".names") != RCFG_NONE ||
                            recomp_cfg_type_of(cfg, WT_PREFIX ".help") != RCFG_NONE)) {
        snprintf(why, wn, "%s.names and %s.help need version = 2 (version 1 reads version, add, stage)", WT_PREFIX,
                 WT_PREFIX);
        ok = 0;
    } else if (recomp_cfg_type_of(cfg, WT_PREFIX ".add") != RCFG_ARRAY || (na = recomp_cfg_array_len(cfg, WT_PREFIX ".add")) == 0) {
        snprintf(why, wn, "%s.add must be a list of \"<event id> = <track> @ <location>\"", WT_PREFIX);
        ok = 0;
    } else if (s_n + na > BO3_WT_MAX) {
        snprintf(why, wn, "%u World Tour events in all mods (this mod adds %u): at most %u fit - the 18 race locations' event "
                 "lists have %u free rows (6 rows per list, the retail events included)", (unsigned)(s_n + na), (unsigned)na,
                 (unsigned)BO3_WT_MAX, (unsigned)BO3_WT_MAX);
        ok = 0;
    }
    for (size_t e = 0; ok && e < na; e++) {
        char line[200], *eq, *at, *colon, *id, *tr, *lo, *ty = NULL;
        const char *s = recomp_cfg_array_type(cfg, WT_PREFIX ".add", e) == RCFG_STRING ?
                        recomp_cfg_array_string(cfg, WT_PREFIX ".add", e, NULL) : NULL;
        wt_ev d;
        memset(&d, 0, sizeof d);
        if (!s || strlen(s) >= sizeof line || !(eq = strchr(strcpy(line, s), '=')) || !(at = strchr(eq, '@'))) {
            snprintf(why, wn, "%s.add[%u] is not \"<event id> = <track> @ <location>\"", WT_PREFIX, (unsigned)e);
            ok = 0;
            break;
        }
        *eq = 0;
        *at = 0;
        if ((colon = strchr(at + 1, ':')) != NULL) {
            *colon = 0;
            ty = trim(colon + 1);
        }
        id = trim(line);
        tr = trim(eq + 1);
        lo = trim(at + 1);
        if (bm_prog_key_make(&k, BM_PROG_EVENT, mod_id, id) != BM_PROG_OK) {
            snprintf(why, wn, "\"%s\" / \"%s\" is not a valid event key (mod id; event id [A-Za-z0-9_-], 1..32)",
                     mod_id ? mod_id : "", id);
            ok = 0;
        } else if (find_key(mod_id, id, cnt) >= 0) {
            snprintf(why, wn, "event %s/%s is declared twice (%s)", mod_id, id,
                     find_key(mod_id, id, first) >= 0 ? "another mod with the same id declares it" : "twice in this mod");
            ok = 0;
        } else if (!bo3_cc_id_ok(tr, why, wn)) {
            ok = 0;
        } else if (!location_ok(lo, &d.loc)) {
            snprintf(why, wn, "event %s: \"%s\" is not a location (RR_XN, e.g. US_C3)", id, lo);
            ok = 0;
        } else if (ty && !strcmp(ty, "crash")) {
            snprintf(why, wn, "event %s: Crash-type events cannot be added yet - only race-type, faceoff, roadrage, "
                     "eliminator and burninglap events (the Crash launch-path audit is pending: sub_00066C40's non-junction "
                     "branch and the junction record)", id);
            ok = 0;
        } else if (ty && (d.type = type_of_name(ty)) >= WT_TYPES) {
            snprintf(why, wn, "event %s: type \"%s\" is not supported (race, faceoff, roadrage, eliminator, burninglap)", id,
                     ty);
            ok = 0;
        } else {
            snprintf(d.mod, sizeof d.mod, "%s", mod_id);
            snprintf(d.ver, sizeof d.ver, "%s", mod_version && *mod_version ? mod_version : "0");
            snprintf(d.local, sizeof d.local, "%s", id);
            snprintf(d.key, sizeof d.key, "%s/%s", mod_id, id);
            snprintf(d.track_s, sizeof d.track_s, "%s", tr);
            snprintf(d.loc_s, sizeof d.loc_s, "%s", lo);
            bo3_cc_encode(tr, &d.track);
            s_ev[cnt++] = d;
        }
    }
    if (ok && recomp_cfg_type_of(cfg, WT_PREFIX ".stage") != RCFG_NONE) {
        if (recomp_cfg_type_of(cfg, WT_PREFIX ".stage") != RCFG_ARRAY) {
            snprintf(why, wn, "%s.stage must be a list of \"<event id> = <retail race ID>\"", WT_PREFIX);
            ok = 0;
        }
        ns = ok ? recomp_cfg_array_len(cfg, WT_PREFIX ".stage") : 0;
        for (size_t i = 0; ok && i < ns; i++) {
            char line[200], *eq, *id, *rid;
            int j;
            const char *s = recomp_cfg_array_type(cfg, WT_PREFIX ".stage", i) == RCFG_STRING ?
                            recomp_cfg_array_string(cfg, WT_PREFIX ".stage", i, NULL) : NULL;
            if (!s || strlen(s) >= sizeof line || !(eq = strchr(strcpy(line, s), '='))) {
                snprintf(why, wn, "%s.stage[%u] is not \"<event id> = <retail race ID>\"", WT_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            *eq = 0;
            id = trim(line);
            rid = trim(eq + 1);
            j = -1;
            for (uint32_t q = first; q < cnt; q++)
                if (!strcmp(s_ev[q].local, id))
                    j = (int)q;
            if (j < 0) {
                snprintf(why, wn, "%s.stage names \"%s\", which is not in add", WT_PREFIX, id);
                ok = 0;
            } else if (s_ev[j].stage_from) {
                snprintf(why, wn, "%s.stage gives %s a second donor", WT_PREFIX, id);
                ok = 0;
            } else if (strlen(rid) != 12 || !bo3_cc_encode(rid, &s_ev[j].stage_from)) {
                snprintf(why, wn, "%s.stage: \"%s\" is not a 12-character race ID", WT_PREFIX, rid);
                ok = 0;
            }
        }
    }
    for (int kind = 0; ok && kind < 2; kind++) {   /* PLATFORM-P3 (P-11): version 2 names / help */
        const char *lk = kind ? WT_PREFIX ".help" : WT_PREFIX ".names";
        size_t nt, max = kind ? BO3_WT_HELP_MAX : BO3_WT_NAME_MAX;
        if (recomp_cfg_type_of(cfg, lk) == RCFG_NONE)
            continue;
        if (recomp_cfg_type_of(cfg, lk) != RCFG_ARRAY) {
            snprintf(why, wn, "%s must be a list of \"<event id> = <text>\"", lk);
            ok = 0;
            break;
        }
        nt = recomp_cfg_array_len(cfg, lk);
        for (size_t i = 0; ok && i < nt; i++) {
            char line[300], *eq, *id, *tx, *dst;
            size_t len;
            int j = -1;
            const char *s = recomp_cfg_array_type(cfg, lk, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, lk, i, NULL) : NULL;
            if (!s || strlen(s) >= sizeof line || !(eq = strchr(strcpy(line, s), '='))) {
                snprintf(why, wn, "%s[%u] is not \"<event id> = <text>\"", lk, (unsigned)i);
                ok = 0;
                break;
            }
            *eq = 0;
            id = trim(line);
            tx = trim(eq + 1);
            for (uint32_t q = first; q < cnt; q++)
                if (!strcmp(s_ev[q].local, id))
                    j = (int)q;
            len = strlen(tx);
            if (j < 0) {
                snprintf(why, wn, "%s names \"%s\", which is not in add", lk, id);
                ok = 0;
            } else if ((dst = kind ? s_ev[j].help : s_ev[j].name)[0]) {
                snprintf(why, wn, "%s gives %s a second text", lk, id);
                ok = 0;
            } else if (len == 0 || len > max) {
                snprintf(why, wn, "%s: the text for %s has %u characters; 1 .. %u fit the %s (the longest retail text "
                         "there)", lk, id, (unsigned)len, (unsigned)max, kind ? "help bar" : "event list row");
                ok = 0;
            } else {
                for (size_t c = 0; ok && c < len; c++) {
                    char ch = tx[c];
                    if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == ' ' ||
                          ch == '-' || ch == '\'' || ch == '.' || ch == '&' || (kind && ch == '!'))) {
                        snprintf(why, wn, "%s: the text for %s has the character '%c'; use A-Z a-z 0-9, space and - ' . &%s",
                                 lk, id, ch, kind ? " !" : "");
                        ok = 0;
                    }
                }
                for (size_t c = 0; ok && c <= len; c++)
                    dst[c] = kind ? (char)toupper((unsigned char)tx[c]) : tx[c];   /* help: upper case, as the game's */
            }
        }
    }
    recomp_cfg_free(cfg);
    if (ok)
        s_n = cnt;
    else
        memset(&s_ev[first], 0, sizeof(wt_ev) * (BO3_WT_MAX - first));   /* nothing of this mod kept */
    for (uint32_t q = first; ok && q < cnt; q++) {   /* P3: every event joins the text table (texts or not) */
        int rc = bo3_nm_event_texts(s_ev[q].key, s_ev[q].name, s_ev[q].help);
        if (rc && (s_ev[q].name[0] || s_ev[q].help[0]))
            fprintf(stderr, "[WT] event %s: its name / help text is not shown (%s): the track's name and the generic help "
                    "instead\n", s_ev[q].key, rc == 2 ? "declared after the text table's install" : "no text slot");
    }
    return ok;
}

/* ---------------------------------------------------------------- the game's tables */
static uint32_t prg_root(void)
{
    uint32_t r = 0;
    return rd32(BO3_WT_ROOT_PTR, &r) ? r : 0;
}

/* every race of every PrgData event: fn(race VA, user) returns 1 to stop; -1 when the data cannot be read */
typedef int (*race_fn)(uint32_t race, void *user);
static int walk_races(race_fn fn, void *user)
{
    uint32_t root = prg_root(), groups, gn;
    if (!root || !rd32(root + 4u, &groups) || !rd32(root + 8u, &gn) || gn > 16u)
        return -1;
    for (uint32_t g = 0; g < gn; g++) {
        uint32_t el, en;
        if (!rd32(groups + 8u * g, &el) || !rd32(groups + 8u * g + 4u, &en) || en > 64u)
            return -1;
        for (uint32_t e = 0; e < en; e++) {
            uint32_t ev, evn;
            if (!rd32(el + 0x18u * e + 0x10u, &ev) || !rd32(el + 0x18u * e + 0x14u, &evn) || evn > 64u)
                return -1;
            for (uint32_t k = 0; k < evn; k++) {
                uint32_t rs, rn;
                if (!rd32(ev + 0x40u * k + 0x34u, &rs) || !rd32(ev + 0x40u * k + 0x38u, &rn) || rn > 8u)
                    return -1;
                for (uint32_t r = 0; r < rn; r++)
                    if (fn(rs + 0x20u * r, user))
                        return 1;
            }
        }
    }
    return 0;
}

typedef struct find_ctx { uint64_t id; uint32_t race; int bad; } find_ctx;
static int find_cb(uint32_t race, void *user)
{
    find_ctx *c = (find_ctx *)user;
    uint64_t v;
    if (!rd64(race + 8u, &v)) {
        c->bad = 1;
        return 1;
    }
    if (v == c->id) {
        c->race = race;
        return 1;
    }
    return 0;
}

/* the PrgData race with this ID: its VA, 0 none, 0xFFFFFFFF unreadable */
static uint32_t find_race(uint64_t id)
{
    find_ctx c = {id, 0, 0};
    int r = walk_races(find_cb, &c);
    return r < 0 || c.bad ? 0xFFFFFFFFu : c.race;
}

/* slot s's race ID as the game resolves it (a Grand Prix value: its first race) */
static int slot_id(uint32_t s, uint64_t *id)
{
    uint64_t v;
    uint32_t lst;
    if (!rd64(G_SLOTS + 8u * s, &v))
        return 0;
    if (v < 7u) {
        if (!rd32(G_GP_LIST + 4u * (uint32_t)v, &lst) || !rd64(lst, &v))
            return 0;
    }
    *id = v;
    return 1;
}

int bo3_wt_known(uint64_t id)
{
#if WT_MUT == 8
    (void)id;
    return 0;                                   /* defect: uniqueness unchecked */
#else
    uint32_t r;
    for (uint32_t s = 0; s < 73u; s++) {
        uint64_t v;
        if (!rd64(G_SLOTS + 8u * s, &v))
            return 1;
        if (v < 7u) {
            uint32_t cnt, lst;
            if (!rd32(G_GP_COUNT + 4u * (uint32_t)v, &cnt) || !rd32(G_GP_LIST + 4u * (uint32_t)v, &lst))
                return 1;
            for (uint32_t j = 0; (int32_t)cnt > 0 && j < cnt && j < 64u; j++) {
                uint64_t w;
                if (!rd64(lst + 8u * j, &w))
                    return 1;
                if (w == id)
                    return 1;
            }
        } else if (v == id) {
            return 1;
        }
    }
    for (uint32_t j = 0; j < 100u; j++) {
        uint64_t v;
        if (!rd64(G_JUNCTIONS + 8u * j, &v) || v == id)
            return 1;
    }
    r = find_race(id);
    return r != 0;                              /* found, or the races cannot be read */
#endif
}

/* the track of a race ID as sub_001582D0 builds it (characters 6..11 -> "RR_NN_VN") */
static int track_of(uint64_t id, uint64_t *track)
{
    char s[13], t[9];
    bo3_cc_decode(id, s);
    if (strlen(s) != 12)
        return 0;
    t[0] = s[6]; t[1] = s[7]; t[2] = '_'; t[3] = s[8]; t[4] = s[9]; t[5] = '_'; t[6] = s[10]; t[7] = s[11]; t[8] = 0;
    return bo3_cc_encode(t, track);
}

static int at_location(uint64_t id, uint64_t loc)
{
    uint64_t t;
    return track_of(id, &t) && t - t % POW40_7 == loc;
}

int bo3_wt_location_events(uint32_t region, uint32_t value)
{
    uint64_t loc;
    int n = 0;
    if (region == WT4)                          /* GP-WT4: the fourth region's location has no retail event */
        return value < BO3_WT4_LOCS && bo3_wt4_declared() ? 0 : -1;
    if (region > 2u || value >= k_race_locs[region] || !rd64(G_LOC_IDS + 8u * (k_loc_base[region] + value), &loc))
        return -1;
    for (uint32_t s = 0; s < 73u; s++) {
        uint64_t id;
        if (!slot_id(s, &id))
            return -1;
        n += at_location(id, loc);
    }
    return n;
}

/* ---------------------------------------------------------------- W1 */
static int rule_open(void)
{
    return 1;                                   /* always available (no host rule in this build) */
}

static int key_cmp(const void *a, const void *b)
{
    const wt_ev *x = (const wt_ev *)a, *y = (const wt_ev *)b;
    int c = strcmp(x->mod, y->mod);
    return c ? c : strcmp(x->local, y->local);
}

static int id_taken(uint64_t id, uint32_t upto)
{
#if WT_MUT == 16
    (void)id; (void)upto;
    return 0;                                   /* defect: another added event's race ID not avoided */
#else
    for (uint32_t i = 0; i < upto; i++)
        if (s_ev[i].id == id)
            return 1;
    return 0;
#endif
}

static int resolve_one(uint32_t i, char *why, size_t wn)
{
    wt_ev *d = &s_ev[i];
    const wt_type *T = &k_type[d->type < WT_TYPES ? d->type : WT_RACE];
    int r = region_of_letters(d->loc_s), tr = bo3_rg_region_of(d->track), cnt;
    uint32_t v, race;
    uint64_t loc;
    wt_loc *L;
    if (r < 0) {                                /* GP-WT4: not US / EU / AS and not a declared fourth-region location */
        snprintf(why, wn, "event %s: %s is not a race location of the USA / Europe / Asia maps nor the location of a World "
                 "Tour region a mod declares ([bmashup.world_tour])", d->key, d->loc_s);
        return 0;
    }
    if (tr < 0 && T->own_track)                 /* C3-8: a retail track (checked = the donor's track below) */
        tr = !strncmp(d->track_s, "US", 2) ? 0 : !strncmp(d->track_s, "EU", 2) ? 1 : !strncmp(d->track_s, "AS", 2) ? 2 : -1;
    if (tr < 0) {
        snprintf(why, wn, "event %s: %s is not a track a mod adds ([bmashup.tracks])", d->key, d->track_s);
        return 0;
    }
    if ((r == (int)WT4 && (uint32_t)tr != bo3_wt4_region_code()) || (r != (int)WT4 && tr != r)) {
        snprintf(why, wn, "event %s: track %s is not in the region of location %s", d->key, d->track_s, d->loc_s);
        return 0;
    }
    if (r == (int)WT4) {
        v = (uint32_t)bo3_wt4_location_index(d->loc);
    } else {
        for (v = 0; v < k_race_locs[r]; v++)
            if (rd64(G_LOC_IDS + 8u * (k_loc_base[r] + v), &loc) && loc == d->loc)
                break;
    }
    if (v >= k_race_locs[r]) {
        snprintf(why, wn, "event %s: %s is not a race location of the %s map", d->key, d->loc_s, k_region[r]);
        return 0;
    }
    cnt = bo3_wt_location_events((uint32_t)r, v);
    L = &s_loc[r][v];
#if WT_MUT == 5
    (void)cnt;                                  /* defect: a full location accepted */
    if (L->k >= BO3_WT_ROWS) {
        snprintf(why, wn, "event %s: no room in the host table", d->key);
        return 0;
    }
#else
    if (cnt < 0 || (uint32_t)cnt >= BO3_WT_ROWS) {
        snprintf(why, wn, "event %s: location %s has %d retail events; its list shows %u rows (at most %u retail events)",
                 d->key, d->loc_s, cnt, (unsigned)BO3_WT_ROWS, (unsigned)(BO3_WT_ROWS - 1u));
        return 0;
    }
#if WT_MUT == 14
    if (L->k >= BO3_WT_ROWS) {                  /* defect: the added events already there not counted */
#else
    if ((uint32_t)cnt + L->k >= BO3_WT_ROWS) {
#endif
        char held[300];
        size_t o = 0;
        held[0] = 0;
        for (uint32_t q = 0; q < L->k && o < sizeof held; q++)
            o += (size_t)snprintf(held + o, sizeof held - o, "%s%s", q ? ", " : "", s_ev[L->ev[q]].key);
        snprintf(why, wn, "event %s: location %s is full - its list shows %u rows: %d retail event(s) + %u added event(s) (%s); "
                 "move the event to another race location of the %s map or remove one", d->key, d->loc_s,
                 (unsigned)BO3_WT_ROWS, cnt, (unsigned)L->k, held, k_region[r]);
        return 0;
    }
#endif
    {
#if WT_MUT == 24
        char letter = 'A';                      /* defect: every type's race ID carries the race letter */
#else
        char letter = T->letter;                /* C3-8: the type's letter (sub_00158340; the rows' type, s2) */
#endif
        for (uint32_t nn = 0;; nn++) {
            if (!bo3_xe_race_id_wt_type(d->track_s, letter, nn, &d->id)) {
                snprintf(why, wn, "event %s: no free race ID of the form 0%c07NN%c%c%c%c%c%c", d->key, letter, d->track_s[0],
                         d->track_s[1], d->track_s[3], d->track_s[4], d->track_s[6], d->track_s[7]);
                return 0;
            }
            if (!bo3_wt_known(d->id) && !id_taken(d->id, i))
                break;
        }
    }
    d->stage_id = d->stage_from;
    /* default: the location's first retail event of the type (race: type A) in slot order; EV: else the region's first
     * (US_C1, US_P2, EU_M1 and EU_C3 have no type-A event). C3-8: the type's letter and race +0x14 */
    for (int pass = 0; pass < 2 && !d->stage_id; pass++) {
        uint64_t locid;
        uint32_t sr = r == (int)WT4 ? bo3_wt4_donor() : (uint32_t)r, sv = r == (int)WT4 ? 0u : v;
        char rl[3] = {0};
        /* GP-WT4: a fourth-region location borrows the donor map's first location (its first type-A race, else the
         * donor region's first) */
        rd64(G_LOC_IDS + 8u * (k_loc_base[sr] + sv), &locid);
        rl[0] = sr == 0 ? 'U' : sr == 1 ? 'E' : 'A';
        rl[1] = sr == 0 ? 'S' : sr == 1 ? 'U' : 'S';
        for (uint32_t s = 0; s < 73u && !d->stage_id; s++) {
            uint64_t id;
            uint32_t ty;
            char cs[13];
            if (!slot_id(s, &id))
                continue;
            bo3_cc_decode(id, cs);
            if (cs[1] != T->letter || (pass == 0 && !at_location(id, locid)) || (pass == 1 && strncmp(cs + 6, rl, 2)))
                continue;
            race = find_race(id);
            if (race && race != 0xFFFFFFFFu && rd32(race + 0x14u, &ty) && ty == T->rt)
                d->stage_id = id;
        }
    }
    race = d->stage_id ? find_race(d->stage_id) : 0;
    {
        uint32_t ty = 0xFFFFFFFFu;
        uint64_t dtrack = 0;
        char sid[13];
        bo3_cc_decode(d->stage_id, sid);
        /* the donor's race +0x14 is the type's; C3-8: for a type other than race also its ID letter (Face-Off shares race
         * type 0 with race) */
        if (!race || race == 0xFFFFFFFFu || !rd32(race + 0x14u, &ty) || ty != T->rt ||
            (d->type != WT_RACE && sid[1] != T->letter)) {
            snprintf(why, wn, "event %s: the stage donor %s is not a %s-type race of the game", d->key,
                     d->stage_id ? sid : "(none at the location)", T->name);
            return 0;
        }
#if WT_MUT != 25
        if (T->own_track && (!rd64(race, &dtrack) || dtrack != d->track)) {
#else
        if (0) {                                /* defect: the phase-1 own-track rule not checked */
#endif
            char dt[13];
            bo3_cc_decode(dtrack, dt);
            snprintf(why, wn, "event %s: %s events run on their donor's own track in this build (the type's Gamedata "
                     "record - laps / drivers / targets - exists only there): the donor %s is on %s, the event on %s; declare "
                     "the event on %s, or name a retail %s race on %s as its donor (%s.stage)", d->key, T->label, sid, dt,
                     d->track_s, dt, T->label, d->track_s, WT_PREFIX);
            return 0;
        }
    }
    if (!d->registered) {
        char w2[300];
        if (!bo3_xe_register(d->mod, d->ver, d->local, d->id, T->xe, bo3_wt_known, w2, sizeof w2)) {
            snprintf(why, wn, "%s/%s", d->mod, w2);
            return 0;
        }
        d->registered = 1;
    }
    {   /* C3-8: the type, the donor and the Gamedata record W8 will use (alias (1) / (2) / the type's Single Event record) */
        char sid[13], rid[13], c1[13];
        bo3_cc_decode(d->stage_id, sid);
        bo3_cc_decode(d->id, rid);
        memcpy(c1, sid, sizeof c1);             /* W8 alias (1): the donor's ID with the event track's six characters */
        c1[6] = d->track_s[0]; c1[7] = d->track_s[1]; c1[8] = d->track_s[3]; c1[9] = d->track_s[4];
        c1[10] = d->track_s[6]; c1[11] = d->track_s[7]; c1[12] = 0;
        if (T->se)
            fprintf(stderr, "[WT] added event %s: type %s, donor %s, record %s / %s / %s (race ID %s, event +0x30 %u, race "
                    "+0x14 %u)\n", d->key, T->name, sid, c1, sid, T->se, rid, (unsigned)T->ev, (unsigned)T->rt);
        else
            fprintf(stderr, "[WT] added event %s: type %s, donor %s, record %s (the donor's own) (race ID %s, event +0x30 %u, "
                    "race +0x14 %u)\n", d->key, T->name, sid, sid, rid, (unsigned)T->ev, (unsigned)T->rt);
    }
    d->region = (uint32_t)r;
    d->value = v;
    d->rank = L->k;
    L->ev[L->k++] = i;
    return 1;
}

static int resolve(char *why, size_t wn)
{
#if WT_MUT != 18
    qsort(s_ev, s_n, sizeof(wt_ev), key_cmp);   /* key order: independent of the mod list's order */
#else
    (void)key_cmp;                              /* defect: the mod list's order */
#endif
    memset(s_loc, 0, sizeof s_loc);
    for (uint32_t i = 0; i < s_n; i++)
        if (!resolve_one(i, why, wn))
            return 0;
    return 1;
}

static int install(uint32_t root)
{
    uint32_t groups, gn, g0, g0n, donor_ev;
    uint8_t el[7 * 0x18], ev0[0x40];
    uint32_t pair[2];
    if (!rd32(root + 4u, &groups) || !rd32(root + 8u, &gn) || gn < 1u || !rd32(groups, &g0) || !rd32(groups + 4u, &g0n))
        return 0;
    if (s_elems && g0 == s_elems && g0n == 7u)
        return 2;                               /* already ours (the same load) */
    if (g0n != 6u) {
        once(1u, "[WT] PrgData group 0 has %s%u elements (6 expected after the loader's cut): events not added\n", "", g0n);
        return 0;
    }
    if (!s_block) {
        uint32_t size = EL_BYTES + s_n * EV_BYTES;
        s_block = s_alloc ? s_alloc(size, 16u) : 0u;
        if (!s_block) {
            once(2u, "[WT] no guest memory for the events (%s%u bytes): events not added\n", "", size);
            return 0;
        }
        s_elems = s_block;
        for (uint32_t i = 0; i < s_n; i++) {    /* events, then races, then stage copies (N = 1: G8-WT1's layout) */
            s_ev[i].event = s_block + EL_BYTES + 0x40u * i;
            s_ev[i].race = s_block + EL_BYTES + 0x40u * s_n + 0x20u * i;
            s_ev[i].stage = s_block + EL_BYTES + 0x60u * s_n + ST_SIZE * i;
        }
    }
    if (!bo3_guest_read(g0, el, 6u * 0x18u) || !rd32(g0 + 0x10u, &donor_ev) || !bo3_guest_read(donor_ev, ev0, 0x40u))
        return 0;
    memset(el + 6u * 0x18u, 0, 0x18u);         /* element header zero (as the game's elements 5 / 6) */
    memcpy(el + 6u * 0x18u + 0x10u, &s_ev[0].event, 4);
    memcpy(el + 6u * 0x18u + 0x14u, &s_n, 4);
    for (uint32_t i = 0; i < s_n; i++) {
        wt_ev *d = &s_ev[i];
        uint8_t ev[0x40], rc[0x20];
        uint32_t donor_race_idx = 0, race_ref;
        /* the event: a copy of group 0 element 0 event 0 (car bytes +0, +8 = 1, +0x18 kept), then its own fields */
        memcpy(ev, ev0, sizeof ev);
        memset(ev + 0x0C, 0, 4);
        memset(ev + 0x10, 0, 8);                /* no reward car (non-zero draws a reward icon; C3-8: Face-Off's won car is
                                                 * granted only by the slot-based unlock rebuild - never for an added event) */
        memset(ev + 0x1C, 0, 4);
        memset(ev + 0x20, 0xFF, 4);
        memset(ev + 0x24, 0xFF, 4);             /* no prerequisites */
        pair[0] = 0x1000u + i;                  /* event number: compared only, never an index (EVENT_AUDIT s3) */
        memcpy(ev + 0x28, &pair[0], 4);
        memset(ev + 0x2C, 0, 4);
#if WT_MUT == 22
        pair[0] = 1u;                           /* defect: every type's event is a race event */
#else
        pair[0] = k_type[d->type].ev;           /* C3-8: the event type (1 race, 6 / 7 / 8 / 9; sub_0005F0A0, sub_00061FC0) */
#endif
        memcpy(ev + 0x30, &pair[0], 4);
        memcpy(ev + 0x34, &d->race, 4);
        pair[0] = 1u;
        memcpy(ev + 0x38, &pair[0], 4);         /* 1 race */
        memset(ev + 0x3C, 0, 4);
        race_ref = find_race(d->stage_id);
        if (race_ref && race_ref != 0xFFFFFFFFu)
            rd32(race_ref + 0x10u, &donor_race_idx);
        memset(rc, 0, sizeof rc);
        memcpy(rc + 0x00, &d->track, 8);
        memcpy(rc + 0x08, &d->id, 8);
        memcpy(rc + 0x10, &donor_race_idx, 4);
#if WT_MUT != 23
        memcpy(rc + 0x14, &k_type[d->type].rt, 4);   /* C3-8: the race (logic) type: 0 race / Face-Off, 1, 3, 4 */
#endif
        pair[0] = d->track_s[7] == '1' ? 1u : 0u;   /* V1 variants carry 1 (the game's data) */
        memcpy(rc + 0x18, &pair[0], 4);
        if (!bo3_guest_write(d->event, ev, sizeof ev) || !bo3_guest_write(d->race, rc, sizeof rc))
            return 0;
    }
    if (!bo3_guest_write(s_elems, el, sizeof el))
        return 0;
    pair[0] = s_elems;
    pair[1] = 7u;
    if (!bo3_guest_write(groups, pair, 8))
        return 0;
#if WT_MUT != 3
    if (!bo3_guest_write(BO3_WT_CELL, &s_ev[0].id, 8))   /* only after the append; W9 follows the cursor */
        return 0;
#endif
    s_root = root;
    return 1;
}

#ifdef BO3_WTOUR_GAME
static void game_load_once(void);
#else
static void game_load_once(void) {}
#endif

void bo3_wt_gen_prg_loaded(void)
{
    uint32_t root;
    char why[600];
    game_load_once();
    if (!s_n)
        return;
    root = prg_root();
    if (!root)
        return;
    if (!s_resolved) {
        if (!bo3_wt4_resolve(why, sizeof why) || !resolve(why, sizeof why)) {   /* GP-WT4: the region first */
            s_n = 0;
            fail(BO3_WT_EXIT_DECL, why);
            return;
        }
        s_resolved = 1;
    }
    {
        int r = install(root);
        s_installed = r != 0;
        bo3_wt4_set_events(s_installed ? s_loc[WT4][0].k : 0u);   /* GP-WT4: the fourth region is shown only with events */
        if (r != 1)
            return;
    }
    for (uint32_t r = 0; r < 4u; r++)
        for (uint32_t v = 0; v < MAX_LOCS; v++)
            s_loc[r][v].listed = 0;
    s_stats[BO3_WT_ST_INSTALLS]++;
    fprintf(stderr, "[WT] prg: group0 6->7: %u added event(s) in host element 0x%08X (events 0x%08X..), cell 0x%08X\n",
            (unsigned)s_n, (unsigned)(s_elems + 6u * 0x18u), (unsigned)s_ev[0].event, (unsigned)BO3_WT_CELL);
    for (uint32_t i = 0; i < s_n; i++) {
        char id[13];
        bo3_cc_decode(s_ev[i].id, id);
        fprintf(stderr, "[WT] event %u: %s ID %s (0x%016llX) event=0x%08X race=0x%08X on %s at %s (%s value %u, added row %u)\n",
                (unsigned)i, s_ev[i].key, id, (unsigned long long)s_ev[i].id, (unsigned)s_ev[i].event, (unsigned)s_ev[i].race,
                s_ev[i].track_s, s_ev[i].loc_s, k_region[s_ev[i].region], (unsigned)s_ev[i].value, (unsigned)s_ev[i].rank);
    }
}

/* ---------------------------------------------------------------- W2 .. W6, W9 */
static uint32_t best_medal(uint32_t i)
{
    uint32_t m = 0, a = 0;
    bo3_xe_best(s_ev[i].id, &m, &a);
    return m;
}

void bo3_wt_gen_loc(uint32_t menu, uint32_t region, uint32_t loc, uint32_t value)
{
    uint32_t n0, c;
    wt_loc *L;
    if (!s_installed || region > 2u)
        return;
#if WT_MUT == 21
    if (bo3_wt4_active() || (region == bo3_wt4_donor() && loc == 0u)) {   /* defect: also on the donor's own map */
#else
    if (bo3_wt4_active()) {                     /* GP-WT4: the map shows the fourth region: its location, by index */
#endif
        if (region != bo3_wt4_donor())
            return;
        region = WT4;
        value = loc;
    }
#if WT_MUT == 9
    (void)value;                                /* defect: every location of the region gets the first one's rows */
    for (value = 0; value < k_race_locs[region] && !s_loc[region][value].k; value++)
        ;
#endif
    if (value >= k_race_locs[region])
        return;
    L = &s_loc[region][value];
    L->listed = 0;
    if (!L->k || loc >= 12u || !rule_open() || !rd32(menu + 0x78Cu + 4u * loc, &n0))
        return;
#if WT_MUT != 5
    if (n0 + L->k > BO3_WT_ROWS) {
        once(4u, "[WT] the location list already has %s%u rows (6 shown): its added events are not listed\n", "", n0);
        return;
    }
#endif
    if (n0 + L->k > 12u)
        return;
    for (uint32_t q = 0; q < L->k; q++) {
#if WT_MUT == 1
        if (!wr32(menu + 0x304u + 4u * (loc * 12u + n0 + q), 0u))        /* defect: slot 0, not item -1 */
#else
        if (!wr32(menu + 0x304u + 4u * (loc * 12u + n0 + q), 0xFFFFFFFFu))
#endif
            return;
    }
    wr32(menu + 0x78Cu + 4u * loc, n0 + L->k);
    if (rd32(menu + 0x71Cu + 4u * loc, &c))
        wr32(menu + 0x71Cu + 4u * loc, c + L->k);
    for (uint32_t q = 0; q < L->k; q++)
        if (best_medal(L->ev[q]) == 3u && rd32(menu + 0x7FCu + 4u * loc, &c))
            wr32(menu + 0x7FCu + 4u * loc, c + 1u);
    L->n0 = n0;
    L->listed = 1;
    s_stats[BO3_WT_ST_LOCS]++;
    if (!(s_loc_logged & (1u << (region * MAX_LOCS + value)))) {
        s_loc_logged |= 1u << (region * MAX_LOCS + value);
        fprintf(stderr, "[WT] loc: %s: %u added event(s) appended as rows %u..%u (after the %u retail rows)\n",
                s_ev[L->ev[0]].loc_s, (unsigned)L->k, (unsigned)n0, (unsigned)(n0 + L->k - 1u), (unsigned)n0);
    }
}

/* the current list's location when W2 listed added events there, else NULL */
static wt_loc *host_list(void)
{
    uint8_t jf = 1;
    uint32_t r = 0xFFFFFFFFu, v = 0xFFFFFFFFu;
    if (!s_installed || !rd8(M_JFLAG, &jf) || jf != 0 || !rd32(M_REGION, &r) || r > 2u)
        return NULL;
    if (bo3_wt4_active()) {                     /* GP-WT4: the fourth region's location (by the map's location index) */
        if (r != bo3_wt4_donor() || !rd32(M_LOCIDX, &v))
            return NULL;
        r = WT4;
    } else if (!rd32(M_VALUE, &v)) {
        return NULL;
    }
    if (v >= k_race_locs[r] || !s_loc[r][v].listed)
        return NULL;
    return &s_loc[r][v];
}

/* the event index of list row `row` (host rows only), or -1 */
static int row_event(const wt_loc *L, uint32_t row)
{
    if (!L || row < L->n0 || row >= L->n0 + L->k)
        return -1;
#if WT_MUT == 15
    return (int)L->ev[0];                       /* defect: every host row is the location's first event */
#else
    return (int)L->ev[row - L->n0];
#endif
}

int bo3_wt_gen_row(uint32_t item, uint32_t row, uint32_t esp)
{
    uint8_t rb = 1;
    uint32_t text;
    wt_loc *L;
    int e;
#if WT_MUT == 2
    (void)item; (void)row; (void)esp; (void)rb; (void)text; (void)L; (void)e;
    return 0;                                   /* defect: no host row */
#else
    L = host_list();
    e = row_event(L, row);
    if (e < 0 || !rd8(M_REBUILD, &rb) || rb != 0 || item != M_ITEMS + 0x10u * row || row > 12u)
        return 0;
#if WT_MUT == 6
    if (rule_open())                            /* defect: the rule evaluated differently than W2 did */
        return 0;
#else
    if (!rule_open())
        return 0;
#endif
    text = bo3_nm_gen_text(TEXT_UNKNOWN, BO3_NM_NAME, (uint32_t)s_ev[e].track, (uint32_t)(s_ev[e].track >> 32));
    text = bo3_nm_event_text_id(s_ev[e].key, BO3_NM_EV_NAME, text);   /* P3 (P-11): the event's own name, if it has one */
    if (!wr32(item + 0xCu, 0xFFFFFFFFu) || !wr32(M_TEXTS + 4u * row, text) || !wr32(esp + 0x18u, text))
        return 0;
    s_stats[BO3_WT_ST_ROWS]++;
    once(16u, "[WT] row: %s = an added event (item -1)\n", s_ev[e].key, 0);
    return 1;
#endif
}

uint32_t bo3_wt_gen_icon(uint32_t item, uint32_t medal)
{
    uint32_t it = 0, row;
    wt_loc *L;
    int e;
#if WT_MUT == 7
    (void)item; (void)it; (void)row; (void)L; (void)e;
    return medal;                               /* defect: the game's fixed gold */
#else
    if (item < M_ITEMS || (item - M_ITEMS) % 0x10u)
        return medal;
    row = (item - M_ITEMS) / 0x10u;
    L = host_list();
    e = row_event(L, row);
    if (e < 0 || !rd32(item + 0xCu, &it) || it != 0xFFFFFFFFu)
        return medal;
    s_stats[BO3_WT_ST_ICONS]++;
#if WT_MUT == 17
    return best_medal(L->ev[0]);                /* defect: the first event's medal on every host row */
#else
    return best_medal((uint32_t)e);
#endif
#endif
}

void bo3_wt_gen_cell(uint32_t item)
{
    uint16_t cur = 0;
    int e;
#if WT_MUT == 13
    (void)item; (void)cur; (void)e; (void)rd16;
    return;                                     /* defect: the cell keeps the first event's ID */
#else
    if (item != 0xFFFFFFFFu || !rd16(M_CURSOR, &cur))
        return;
    e = row_event(host_list(), cur);
    if (e < 0)
        return;
    if (bo3_guest_write(BO3_WT_CELL, &s_ev[e].id, 8))
        s_stats[BO3_WT_ST_CELL]++;
#endif
}

/* PLATFORM-P3 (P-11) W7: sub_00074750 mode 4 (the event list's help bar) loc_0007486A, text = sub_001585F0's text ID
 * (item -1 reads the text id 0x21 that the game stores at guest address 0x39E340, "SELECT FRIEND"). For a host row under the cursor (item -1 on a list W2
 * listed): the event's own help, else the generic help of an added event (host texts, bm_names.c; "SELECT EVENT" when
 * the host array is not the one the game reads). Any other row or list: the game's ID unchanged. */
static uint32_t s_help;

uint32_t bo3_wt_gen_help(uint32_t text)
{
    uint16_t cur = 0;
    uint32_t item = 0;
    int e;
    wt_loc *L = host_list();
    if (!L || !rd16(M_CURSOR, &cur) || cur > 12u || !rd32(M_ITEMS + 0xCu + 0x10u * cur, &item) || item != 0xFFFFFFFFu)
        return text;
    e = row_event(L, cur);
    if (e < 0)
        return text;
    s_help++;
    return bo3_nm_event_text_id(s_ev[e].key, BO3_NM_EV_HELP, TEXT_SELECT_EVENT);
}

uint32_t bo3_wt_help_count(void) { return s_help; }

static int event_of_id(uint64_t id)
{
    for (uint32_t i = 0; i < s_n; i++)
        if (s_ev[i].id == id)
            return (int)i;
    return -1;
}

uint32_t bo3_wt_gen_stage(uint32_t race)
{
    uint64_t id;
    uint32_t buf, n;
    int e;
    wt_ev *d;
    if (!s_installed || !rd64(race + 8u, &id) || (e = event_of_id(id)) < 0)
        return 0;
#if WT_MUT == 4
    return 0;                                   /* defect: no stage record */
#endif
#if WT_MUT == 19
    e = 0;                                      /* defect: the first event's record for every added race */
#endif
    d = &s_ev[e];
    if (!rd32(G_STAGE_PTR, &buf) || !buf)
        return 0;
    if (buf != d->stage_buf) {
        uint8_t rec[ST_SIZE];
        uint32_t i;
        if (!rd32(buf + ST_COUNT, &n) || n > 4096u)
            n = 0;
        for (i = 0; i < n; i++) {
            uint64_t v;
            if (rd64(buf + ST_RECS + ST_SIZE * i + ST_RACE, &v) && v == d->stage_id)
                break;
        }
        if (i == n || !bo3_guest_read(buf + ST_RECS + ST_SIZE * i, rec, ST_SIZE)) {
            char why[300], sid[13];
            bo3_cc_decode(d->stage_id, sid);
            snprintf(why, sizeof why, "World Tour event %s: Data\\stagehed.bin has no stage record %s (the event's stage "
                     "donor); stopping instead of a NULL record", d->key, sid);
            fail(BO3_WT_EXIT_LAUNCH, why);
            return 0;
        }
        memcpy(rec + ST_TRACK, &d->track, 8);
        memcpy(rec + ST_RACE, &d->id, 8);
        if (!bo3_guest_write(d->stage, rec, ST_SIZE))
            return 0;
        d->stage_buf = buf;
        fprintf(stderr, "[WT] stage: %s: record %u of 0x%08X copied to 0x%08X (track / race keys of the added event)\n",
                d->key, (unsigned)i, (unsigned)buf, (unsigned)d->stage);
    }
    s_stats[BO3_WT_ST_STAGE]++;
    return d->stage;
}

void bo3_wt_gen_launch(uint32_t lo, uint32_t hi)
{
    uint64_t id = (uint64_t)hi << 32 | lo;
    uint32_t root, groups, g0 = 0, g0n = 0;
    char why[400];
    int e;
    e = s_resolved ? event_of_id(id) : -1;
    bo3_wt4_note_launch(e >= 0 && s_ev[e].region == WT4);   /* GP-WT4: the return path re-enters the fourth region */
    if (e < 0)
        return;
    root = prg_root();
    if (s_installed && root && rd32(root + 4u, &groups) && rd32(groups, &g0) && rd32(groups + 4u, &g0n) && g0 == s_elems &&
        g0n == 7u) {
        /* C3-8: the type fields as the set-up (sub_0005F0A0, after this mark) will read them; the logic object 0x4D4788 and
         * the AI count 0x4D467C are set later, there (the probe reads them; not seen here) */
        uint32_t et = 0, rt = 0;
        rd32(s_ev[e].event + 0x30u, &et);
        rd32(s_ev[e].race + 0x14u, &rt);
        fprintf(stderr, "[WT] launch %s: type %s, event +0x30 %u, race +0x14 %u\n", s_ev[e].key, k_type[s_ev[e].type].name,
                (unsigned)et, (unsigned)rt);
        /* (C3-8 s6) a plugin mode row in World Tour (an added Eliminator-type event + bo3_rules_mode_race(owner) here, the
         * owner cleared on the return path) would go here: NOT in this build - blocked until the Eliminator type passes its
         * probe and the owner lifts the main19 "no World Tour mode rows" policy */
        return;
    }
    snprintf(why, sizeof why, "World Tour event %s selected, but its event is not in the loaded PrgData (group 0 = "
             "0x%08X x %u); stopping instead of the launch walk's out-of-array read", s_ev[e].key, (unsigned)g0,
             (unsigned)g0n);
    fail(BO3_WT_EXIT_LAUNCH, why);
}

/* ---------------------------------------------------------------- W8 (G8-WT2): the track Gamedata header lookup */
#define GD_KEYS   0x8u                      /* u64 race keys */
#define GD_OFFS   0x198u                    /* u32 record offsets */
#define GD_COUNT  0x260u
#define GD_MAX    50u                       /* (0x198 - 8) / 8 key slots */
static uint32_t s_gd_alias;

uint32_t bo3_wt_gd_alias(void) { return s_gd_alias; }

static uint32_t gd_find(uint32_t hdr, uint32_t n, uint64_t key, int *bad)
{
    for (uint32_t i = 0; i < n; i++) {
        uint64_t v;
        uint32_t o;
        if (!rd64(hdr + GD_KEYS + 8u * i, &v) || !rd32(hdr + GD_OFFS + 4u * i, &o)) {
            *bad = 1;
            return 0;
        }
        if (v == key)
            return o;
    }
    return 0;
}

uint32_t bo3_wt_gen_gd_key(uint32_t hdr, uint32_t lo, uint32_t hi, uint32_t off)
{
    uint64_t id = (uint64_t)hi << 32 | lo, cand[3];
    uint32_t n = 0;
    int bad = 0, e;
    char s[13], why[500], a1[13], a2[13];
    wt_ev *d;
#if WT_MUT != 11
    if (!s_resolved || (e = event_of_id(id)) < 0)
        return off;                             /* every other key: the game's own result */
#else
    (void)id;                                   /* defect: every miss is aliased */
    e = 0;
    if (!s_resolved || !s_n)
        return off;
#endif
#if WT_MUT == 10
    return off;                                 /* defect: no alias (the runtime failure) */
#endif
#if WT_MUT == 20
    e = 0;                                      /* defect: the first event's alias for every added race */
#endif
    d = &s_ev[e];
    bo3_cc_decode(d->stage_id, s);              /* (1) the donor's ID with the added track's six characters */
    s[6] = d->track_s[0]; s[7] = d->track_s[1]; s[8] = d->track_s[3]; s[9] = d->track_s[4];
    s[10] = d->track_s[6]; s[11] = d->track_s[7]; s[12] = 0;
    cand[0] = 0;
    bo3_cc_encode(s, &cand[0]);
    cand[1] = d->stage_id;                      /* (2) the donor's ID as it is */
    cand[2] = 0;
#if WT_MUT == 26
    bo3_cc_encode("OFFSGRCF", &cand[2]);        /* defect: the race record for every type */
#else
    if (k_type[d->type].se)                     /* (3) the type's Single Event record (C3-8: race OFFSGRCF, Road Rage */
        bo3_cc_encode(k_type[d->type].se, &cand[2]);   /* OFFRRGEF; none for the own-track types) */
#endif
    if (!rd32(hdr + GD_COUNT, &n) || n > GD_MAX)
        n = 0;
    s_gd_alias = 0;
    for (uint32_t k = 0; k < 3u; k++) {
        uint32_t o = cand[k] ? gd_find(hdr, n, cand[k], &bad) : 0;
        if (o) {
            char c[13];
            s_gd_alias = k + 1u;
            s_stats[BO3_WT_ST_GD]++;
            bo3_cc_decode(cand[k], c);
            fprintf(stderr, "[WT] gamedata: %s has no record %s in its header: record %s (alias %u) at 0x%X (%s, type %s)\n",
                    d->track_s, "of the added race ID", c, (unsigned)(k + 1u), (unsigned)o, d->key, k_type[d->type].name);
            return o;
        }
    }
#if WT_MUT == 12
    return off;                                 /* defect: the miss goes on (offset 0: the header read as a record) */
#endif
    bo3_cc_decode(cand[0], a1);
    bo3_cc_decode(cand[1], a2);
    if (k_type[d->type].se)
        snprintf(why, sizeof why, "World Tour event %s: the Gamedata.bgd of %s has no %s record for its race ID, %s, %s or "
                 "the Single Event record %s%s; stopping instead of reading the file header as a record", d->key,
                 d->track_s, k_type[d->type].name, a1, a2, k_type[d->type].se, bad ? " (header unreadable)" : "");
    else
        snprintf(why, sizeof why, "World Tour event %s: the Gamedata.bgd of %s has no %s record for its race ID or its "
                 "donor's %s (a %s event needs its donor's own record; no Single Event record of the type exists)%s; "
                 "stopping instead of reading the file header as a record", d->key, d->track_s, k_type[d->type].name, a2,
                 k_type[d->type].label, bad ? " (header unreadable)" : "");
    fail(BO3_WT_EXIT_GAMEDATA, why);
    return off;
}

/* ---------------------------------------------------------------- the game build */
#ifdef BO3_WTOUR_GAME
#include "modfs.h"

extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t alignment);
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

static void game_fail(int code, const char *why)
{
    fprintf(stderr, "[WT] FATAL: %s (code %d)\n", why, code);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: a mod's World Tour event cannot be used",
              "%s.\n\nTurn the mod off, or fix its [bmashup.extra_events] declaration.", why);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(code);
}

static void game_load_once(void)
{
    static int done;
    if (done)
        return;
    done = 1;
    bo3_wt4_game_declare();                     /* GP-WT4: [bmashup.world_tour] before the events (their locations) */
    s_alloc = xbox_HeapAlloc;
    s_fail = game_fail;
    bo3_xe_set_store(bo3_cc_progress_store);    /* the CC1.2 sidecar store (one store for tracks and events) */
    for (int i = 0; i < bo3_modfs_mod_count(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[400], msg[500];
        char *text = NULL;
        size_t n = 0;
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!bo3_wt_parse(m->manifest.id, m->manifest.version, text, n, why, sizeof why)) {
            free(text);
            snprintf(msg, sizeof msg, "mod %s: %s", m->manifest.id, why);
            game_fail(BO3_WT_EXIT_DECL, msg);
        }
        free(text);
    }
    for (uint32_t i = 0; i < s_n; i++)
        fprintf(stderr, "[WT] mod %s declares World Tour event %s: %s at %s%s%s%s%s%s%s\n", s_ev[i].mod, s_ev[i].key,
                s_ev[i].track_s, s_ev[i].loc_s, s_ev[i].name[0] ? ", row \"" : "", s_ev[i].name, s_ev[i].name[0] ? "\"" : "",
                s_ev[i].help[0] ? ", help \"" : "", s_ev[i].help, s_ev[i].help[0] ? "\"" : "");
}

/* PLATFORM-P3 (P-11): bm_names.c calls this before its first table install, so the events' texts are in it */
void bo3_wt_game_declare(void)
{
    game_load_once();
}
#endif
