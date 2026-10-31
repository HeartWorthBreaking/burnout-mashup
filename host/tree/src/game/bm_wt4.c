/* GP-WT4 EXPERIMENTAL: a fourth World Tour map region (bm_wt4.h). WT4_MUT=n (test builds only) compiles one deliberate
 * defect (run_wt4_tests.py): 1 the cursor wraps at 3 (G5: region unreachable); 2 G2 writes count 4 into the state but the
 * widget keeps the game's 3-entry array (G3 off: entry 3 read from the next object); 3 M1 passes 3 on (no donor: +0x254 = 3);
 * 4 the location count is not changed (M2 off: the donor's 9 / 12 / 7 markers); 5 the retail events of the donor location
 * stay (M3 / M4 off); 6 the texture guard is off (T returns 3); 7 the return from a 4th-region race goes to the donor map
 * (G1 off); 8 the region is shown without events (fail-closed rule off); 9 the globe is given 3 (G8 / G9 off); 10 G4's v2 rule (a host flag instead of the widget's cursor); 11 G4's v3 rule (the cursor only while the globe holds the donor). */
#include "bm_wt4.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_names.h"
#include "bm_regions.h"
#include "bm_tracks.h"
#include "bm_wtour.h"
#include "recomp_cfg.h"

#ifndef WT4_MUT
#define WT4_MUT 0
#endif

#define WT4_PREFIX "bmashup.world_tour"
#define TEXT_TABLE 0x004D532Cu               /* [[0x4D532C] + 0xC][id] = the UTF-16 string pointer of text id */
#define ENTRY_SIZE 8u
#define BLOCK_SIZE 32u                       /* 4 entries */

static const char *const k_map[3] = {"USA", "EUROPE", "ASIA"};

static struct {
    char mod[80], loc_s[6], letter;
    uint32_t donor;
    uint64_t loc;
    int declared;
} s_d;
static int s_resolved, s_active, s_v4, s_pending, s_block_ok;
static uint32_t s_k, s_code, s_events, s_block, s_logged;
static uint32_t s_stats[BO3_WT4_STATS];
static bo3_wt4_alloc_fn s_alloc;

void bo3_wt4_set_alloc(bo3_wt4_alloc_fn fn) { s_alloc = fn; }

void bo3_wt4_reset(void)
{
    memset(&s_d, 0, sizeof s_d);
    s_resolved = s_active = s_v4 = s_pending = s_block_ok = 0;
    s_k = s_code = s_events = s_block = s_logged = 0;
    memset(s_stats, 0, sizeof s_stats);
}

static void once(uint32_t bit, const char *fmt, const char *a, unsigned b)
{
    if (s_logged & bit)
        return;
    s_logged |= bit;
    fprintf(stderr, fmt, a, b);
}

uint32_t bo3_wt4_stats(uint32_t which) { return which < BO3_WT4_STATS ? s_stats[which] : 0; }
uint32_t bo3_wt4_block_va(void) { return s_block_ok ? s_block : 0; }
int bo3_wt4_declared(void) { return s_d.declared; }
uint32_t bo3_wt4_region_code(void) { return s_resolved ? s_code : 0; }
uint32_t bo3_wt4_donor(void) { return s_d.donor; }
const char *bo3_wt4_location_text(void) { return s_d.declared ? s_d.loc_s : ""; }
int bo3_wt4_active(void) { return s_active; }
void bo3_wt4_set_events(uint32_t n) { s_events = n; }

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

static int loc_form(const char *s, char letter)
{
    if (strlen(s) != 5 || s[0] != letter || s[2] != '_' || !(s[1] >= 'A' && s[1] <= 'Z'))
        return 0;
    if (!strncmp(s, "US", 2) || !strncmp(s, "EU", 2) || !strncmp(s, "AS", 2))
        return 0;
    for (int i = 3; i < 5; i++)
        if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9')))
            return 0;
    return 1;
}

int bo3_wt4_parse(const char *mod_id, const char *text, size_t n, char *why, size_t wn)
{
    char err[200], *buf, line[64];
    size_t plen = strlen(WT4_PREFIX);
    recomp_cfg *cfg;
    int ok = 1, present = 0;
    const char *s;
    uint64_t enc = 0;
    struct { char letter, loc_s[6]; uint32_t donor; uint64_t loc; } d;

    memset(&d, 0, sizeof d);
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
        if (strncmp(key, WT4_PREFIX, plen) != 0 || (key[plen] != 0 && key[plen] != '.'))
            continue;
        present = 1;
        if (key[plen] == 0 || (strcmp(key, WT4_PREFIX ".version") && strcmp(key, WT4_PREFIX ".region") &&
                               strcmp(key, WT4_PREFIX ".map") && strcmp(key, WT4_PREFIX ".location"))) {
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 1: version, region, map, location)", key,
                     WT4_PREFIX);
            ok = 0;
        }
    }
    if (!ok || !present) {
        recomp_cfg_free(cfg);
        return ok;
    }
    if (recomp_cfg_type_of(cfg, WT4_PREFIX ".version") != RCFG_INT || recomp_cfg_int(cfg, WT4_PREFIX ".version", 0) != 1) {
        snprintf(why, wn, "%s.version must be 1", WT4_PREFIX);
        ok = 0;
    } else if (s_d.declared) {
        snprintf(why, wn, "a second World Tour region (mod %s declares region %c): this build shows one fourth region",
                 s_d.mod, s_d.letter);
        ok = 0;
    }
    if (ok) {
        s = recomp_cfg_type_of(cfg, WT4_PREFIX ".region") == RCFG_STRING ? recomp_cfg_string(cfg, WT4_PREFIX ".region", "") : "";
        if (strlen(s) != 1 || !(s[0] >= 'A' && s[0] <= 'Z') || s[0] == 'U' || s[0] == 'E' || s[0] == 'A') {
            snprintf(why, wn, "%s.region must be one region letter A-Z other than U / E / A (a region of [bmashup.regions])",
                     WT4_PREFIX);
            ok = 0;
        } else {
            d.letter = s[0];
        }
    }
    if (ok) {
        int m = -1;
        s = recomp_cfg_type_of(cfg, WT4_PREFIX ".map") == RCFG_STRING ? recomp_cfg_string(cfg, WT4_PREFIX ".map", "") : "";
        snprintf(line, sizeof line, "%s", s);
        for (char *p = line; *p; p++)
            *p = (char)toupper((unsigned char)*p);
        for (int i = 0; i < 3; i++)
            if (!strcmp(trim(line), k_map[i]))
                m = i;
        if (m < 0) {
            snprintf(why, wn, "%s.map must be USA, EUROPE or ASIA (the retail map the region borrows)", WT4_PREFIX);
            ok = 0;
        } else {
            d.donor = (uint32_t)m;
        }
    }
    if (ok) {
        s = recomp_cfg_type_of(cfg, WT4_PREFIX ".location") == RCFG_STRING ?
            recomp_cfg_string(cfg, WT4_PREFIX ".location", "") : "";
        snprintf(line, sizeof line, "%s", s);
        if (!loc_form(trim(line), d.letter) || !bo3_cc_encode(trim(line), &enc)) {
            snprintf(why, wn, "%s.location \"%s\" is not \"%c?_XN\" (5 characters, the region letter first, not US / EU / AS)",
                     WT4_PREFIX, line, d.letter);
            ok = 0;
        } else {
            snprintf(d.loc_s, sizeof d.loc_s, "%s", trim(line));
            d.loc = enc;
        }
    }
    recomp_cfg_free(cfg);
    if (!ok)
        return 0;                              /* nothing of this mod kept (an earlier declaration stays) */
    snprintf(s_d.mod, sizeof s_d.mod, "%s", mod_id ? mod_id : "");
    snprintf(s_d.loc_s, sizeof s_d.loc_s, "%s", d.loc_s);
    s_d.letter = d.letter;
    s_d.donor = d.donor;
    s_d.loc = d.loc;
    s_d.declared = 1;
    return 1;
}

int bo3_wt4_location_index(uint64_t loc)
{
    return s_d.declared && loc == s_d.loc ? 0 : -1;
}

int bo3_wt4_location_known(const char *loc)
{
    return s_d.declared && loc && !strcmp(loc, s_d.loc_s);
}

int bo3_wt4_resolve(char *why, size_t wn)
{
    int k;
    if (!s_d.declared)
        return 1;
    if (s_resolved)
        return 1;
    k = bo3_cc_region_of_letter(s_d.letter);
    if (k < 0) {
        snprintf(why, wn, "mod %s: [%s] region %c is not a region any mod declares in [bmashup.regions]", s_d.mod, WT4_PREFIX,
                 s_d.letter);
        return 0;
    }
    s_k = (uint32_t)k;
    s_code = BO3_RG4_CODE0 + s_k;
    s_resolved = 1;
    fprintf(stderr, "[WT4] mod %s declares World Tour region %c (%s, code %u) on the %s map, location %s\n", s_d.mod, s_d.letter,
            bo3_cc_region_at(s_k) ? bo3_cc_region_at(s_k)->text : "?", (unsigned)s_code, k_map[s_d.donor], s_d.loc_s);
    return 1;
}

/* ---------------------------------------------------------------- shown */
static uint32_t region_text_ptr(void)
{
    uint32_t id, blob = 0, arr = 0, p = 0;
    if (!s_resolved || !(id = bo3_nm_region_text_id(s_k)))
        return 0;
    if (!bo3_guest_rd32(TEXT_TABLE, &blob) || !blob || !bo3_guest_rd32(blob + 0xCu, &arr) || !arr ||
        !bo3_guest_rd32(arr + 4u * id, &p))
        return 0;
    return p;
}

int bo3_wt4_shown(void)
{
#if WT4_MUT == 8
    return s_resolved && region_text_ptr() != 0;           /* defect: shown without events */
#else
    return s_resolved && s_events > 0 && bo3_wt_installed() && region_text_ptr() != 0;
#endif
}

static int page_ok(void) { return bo3_wt4_shown() && s_block_ok; }

static void hidden_reason(void)
{
    if (!s_d.declared || (s_logged & 0x100u))
        return;
    s_logged |= 0x100u;
    s_stats[BO3_WT4_ST_HIDDEN]++;
    fprintf(stderr, "[WT4] World Tour region %c is not shown (%s): the region page stays USA / Europe / Asia\n", s_d.letter,
            !s_resolved ? "declaration not resolved" : !s_events || !bo3_wt_installed() ? "no event of [bmashup.extra_events] "
            "at its location is installed" : !region_text_ptr() ? "its region text does not resolve in the game's text table" :
            "no guest memory for the region entries");
}

/* ---------------------------------------------------------------- region page */
uint32_t bo3_wt4_gen_enter(uint32_t region, uint32_t mode)
{
    int pend = s_pending;
    (void)mode;
    s_pending = 0;
#if WT4_MUT == 7
    pend = 0;                                               /* defect: the return goes to the donor map */
#endif
    if (pend && page_ok() && region == s_d.donor) {
        s_stats[BO3_WT4_ST_RETURNS]++;
        fprintf(stderr, "[WT4] return from a race of region %c: World Tour region %u -> %u\n", s_d.letter, (unsigned)region,
                (unsigned)BO3_WT4_REGION);
        return BO3_WT4_REGION;
    }
    if (region >= BO3_WT4_REGION && !page_ok())
        return 0;                                           /* never a region 3 without the page (fail closed: USA) */
    return region;
}

void bo3_wt4_gen_regions(uint32_t state)
{
    uint8_t blk[BLOCK_SIZE];
    uint32_t p, four = 4u;
    if (!bo3_wt4_shown()) {
        s_block_ok = 0;
        hidden_reason();
        return;
    }
    if (!s_block)
        s_block = s_alloc ? s_alloc(BLOCK_SIZE, 16u) : 0u;
    p = region_text_ptr();
    memset(blk, 0, sizeof blk);
    if (!s_block || !p || state != BO3_WT4_STATE || !bo3_guest_read(state + 0x18u, blk, 3u * ENTRY_SIZE)) {
        s_block_ok = 0;
        hidden_reason();
        return;
    }
    memcpy(blk + 3u * ENTRY_SIZE, &p, 4);                   /* entry 3: the region's text, not locked, no flag */
    if (!bo3_guest_write(s_block, blk, sizeof blk) || !bo3_guest_write(state + 0x16u, &four, 2)) {
        s_block_ok = 0;
        return;
    }
    s_block_ok = 1;
    s_stats[BO3_WT4_ST_PAGES]++;
    once(1u, "[WT4] region page: 4 regions, entry 3 = %s (entries in host block 0x%08X)\n",
         bo3_cc_region_at(s_k) ? bo3_cc_region_at(s_k)->text : "?", (unsigned)s_block);
}

uint32_t bo3_wt4_gen_entries(uint32_t entries)
{
#if WT4_MUT == 2
    return entries;                                         /* defect: the widget reads the 3-entry array */
#else
    uint8_t blk[3u * ENTRY_SIZE];
    if (!page_ok() || entries != BO3_WT4_STATE + 0x18u)
        return entries;
    if (bo3_guest_read(entries, blk, sizeof blk))           /* the game's 3 entries as they are now */
        bo3_guest_write(s_block, blk, sizeof blk);
    return s_block;
#endif
}

uint32_t bo3_wt4_gen_page_region(uint32_t region, uint32_t page)
{
    /* v3 (runtime gp_wt4_1): the entry widget's cursor (+0x14) is what the page shows; after the map's way back the globe
     * (+0x58) holds the donor and no globe call says "3" again, so a host flag alone lost the 4th region there */
    uint16_t cur = 0;
    /* v4 (runtime gp_wt4_4): after a race the globe's +0x58 is not the donor (left from OCEANIA went to USA through the locked
     * 1 / 2, right stayed: the state said 2); the widget's cursor alone decides */
#if WT4_MUT == 10
    if (page == 0u && s_v4 && page_ok() && region == s_d.donor)   /* defect: v2's flag rule */
        return BO3_WT4_REGION;
    (void)cur;
#elif WT4_MUT == 11
    if (page == 0u && page_ok() && region == s_d.donor && bo3_guest_read(BO3_WT4_STATE + 0x14u, &cur, 2) &&
        cur == BO3_WT4_REGION)                                   /* defect: v3's rule (only when the globe holds the donor) */
        return BO3_WT4_REGION;
#else
    if (page == 0u && page_ok() && bo3_guest_read(BO3_WT4_STATE + 0x14u, &cur, 2) && cur == BO3_WT4_REGION)
        return BO3_WT4_REGION;                                   /* whatever the globe holds (region) */
#endif
    return region;
}

uint32_t bo3_wt4_gen_right(uint32_t wrapped, uint32_t next)
{
#if WT4_MUT == 1
    (void)next;
    return wrapped;                                         /* defect: wraps at 3 */
#else
    if (page_ok() && next == BO3_WT4_REGION)
        return BO3_WT4_REGION;
    return wrapped;
#endif
}

uint32_t bo3_wt4_gen_left(uint32_t wrapped)
{
#if WT4_MUT == 1
    return wrapped;
#else
    return page_ok() ? BO3_WT4_REGION : wrapped;
#endif
}

int bo3_wt4_gen_avail(uint32_t region)
{
    if (region == BO3_WT4_REGION && page_ok())
        return 1;
    return -1;
}

uint32_t bo3_wt4_gen_globe(uint32_t region)
{
    if (region == BO3_WT4_REGION && page_ok()) {
        s_v4 = 1;
#if WT4_MUT == 9
        return region;                                      /* defect: the globe gets 3 */
#else
        return s_d.donor;
#endif
    }
    s_v4 = 0;
    return region;
}

/* ---------------------------------------------------------------- map page */
uint32_t bo3_wt4_gen_map(uint32_t region)
{
    if (region == BO3_WT4_REGION && page_ok()) {
        s_active = 1;
        s_v4 = 1;
        s_stats[BO3_WT4_ST_MAPS]++;
        once(2u, "[WT4] map: region %s (the borrowed view: menu region = donor, 1 location)\n", s_d.loc_s, 0);
#if WT4_MUT == 3
        return region;                                      /* defect: +0x254 = 3 */
#else
        return s_d.donor;
#endif
    }
    s_active = 0;
    s_v4 = 0;
    if (region >= BO3_WT4_REGION)
        return 0;                                           /* fail closed: never a map page of region 3 without the page */
    return region;
}

uint32_t bo3_wt4_gen_count(uint32_t count)
{
#if WT4_MUT == 4
    return count;
#else
    if (!s_active)
        return count;
    s_stats[BO3_WT4_ST_COUNTS]++;
    return BO3_WT4_LOCS;
#endif
}

int bo3_wt4_gen_suppress(void)
{
#if WT4_MUT == 5
    return 0;
#else
    if (s_active)
        s_stats[BO3_WT4_ST_SUPPRESS]++;
    return s_active;
#endif
}

int bo3_wt4_gen_focus(uint32_t menu, uint32_t arg)
{
    uint32_t loc = 0, v = 0, m1 = 0xFFFFFFFFu;
    uint8_t z = 0;
    if (!s_active || menu != BO3_WT4_MENU)
        return 0;
    if (arg == 2u && (!bo3_guest_rd32(menu + 0x27Cu, &loc) || loc >= BO3_WT4_LOCS))
        loc = 0;
    if (!bo3_guest_rd32(menu + 0x57Cu + 4u * (s_d.donor * 0x1Cu + loc), &v))
        return 0;
    bo3_guest_wr32(menu + 0x27Cu, loc);
    bo3_guest_wr32(menu + 0x264u, v);
    bo3_guest_write(menu + 0x8E6u, &z, 1);
    if (arg != 2u) {
        bo3_guest_wr32(menu + 0x278u, m1);
        bo3_guest_wr32(menu + 0x25Cu, m1);
    }
    return 1;
}

uint32_t bo3_wt4_gen_marker(uint32_t state, uint32_t loc)
{
    return s_active && loc < BO3_WT4_LOCS ? 1u : state;     /* 1 = an open marker (sub_00158400's values) */
}

uint32_t bo3_wt4_gen_tex(uint32_t region)
{
    if (region <= 2u)
        return region;
    s_stats[BO3_WT4_ST_TEX]++;
    once(4u, "[WT4] a SatMap index table was read with region %s%u: bounded to the donor map\n", "", (unsigned)region);
#if WT4_MUT == 6
    return region;
#else
    return s_d.declared ? s_d.donor : 0u;
#endif
}

void bo3_wt4_note_launch(int is_wt4)
{
    s_pending = is_wt4 && s_active;
}

/* ---------------------------------------------------------------- the game build */
#ifdef BO3_WT4_GAME
#include "modfs.h"
extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t alignment);
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

void bo3_wt4_game_declare(void)
{
    static int done;
    if (done)
        return;
    done = 1;
    s_alloc = xbox_HeapAlloc;
    for (int i = 0; i < bo3_modfs_mod_count(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[400];
        char *text = NULL;
        size_t n = 0;
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!bo3_wt4_parse(m->manifest.id, text, n, why, sizeof why)) {
            free(text);
            fprintf(stderr, "[WT4] FATAL: mod %s: %s (code %d)\n", m->manifest.id, why, BO3_WT4_EXIT_DECL);
            fflush(stderr);
            xbox_crash_log_flush(1000);
            bo3_fatal("Takedawn: a mod's World Tour region cannot be used",
                      "mod %s: %s.\n\nTurn the mod off, or fix its [bmashup.world_tour] declaration.", m->manifest.id, why);
            fflush(stdout);
            fflush(stderr);
            xbox_crash_log_flush(1000);
            _Exit(BO3_WT4_EXIT_DECL);
        }
        free(text);
    }
}
#else
void bo3_wt4_game_declare(void) {}
#endif
