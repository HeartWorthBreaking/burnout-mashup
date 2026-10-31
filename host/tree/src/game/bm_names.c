/* G8-NM1 EXPERIMENTAL: names of added tracks through the game's own text table (bm_names.h). MUT=n (test builds only)
 * compiles one deliberate defect. G8-TL: MUT 6 the last named-track slot unusable, MUT 7 the region texts one ID low (over
 * the last named-track slot). */
#include "bm_names.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_guest.h"         /* G8-E4: guest access through the runtime's mappings */
#include "bm_tracks.h"
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0
#endif

typedef struct nm_track {
    uint64_t id;
    char text[BO3_NM_KINDS][BO3_NM_NAME_MAX + 1];           /* "" = none */
    uint32_t pva[BO3_NM_KINDS];                              /* G8-E4: a plugin's frozen block (guest VA), 0 = none */
} nm_track;

/* G8-TL: the named-track slots and the region texts never share a host text ID, and every ID stays a small positive index */
_Static_assert(BO3_NM_MAX == BO3_CC_CAP, "every track the track list can hold may be named");
_Static_assert(BO3_NM_REGION_BASE == BO3_NM_BASE + BO3_NM_KINDS * BO3_NM_MAX, "region texts follow the last named slot");
_Static_assert(BO3_NM_REGION_BASE + BO3_CC_REGIONS_MAX <= 0x8000u, "host text IDs below 0x8000");

/* G8-E4: every declared added track (a plugin may name only those), and plugin texts waiting for the table install */
static uint64_t s_decl[BO3_CC_CAP];             /* G8-TL: was 128 */
static uint32_t s_ndecl;
static struct { uint64_t id; uint32_t kind, va; const void *owner; } s_pend[BO3_NM_MAX * BO3_NM_KINDS];
static uint32_t s_npend;
static int s_closed;

static int has_text(const nm_track *t, uint32_t k)
{
    return t->text[k][0] || t->pva[k];
}

static nm_track s_t[BO3_NM_MAX];
static uint32_t s_n;
static bo3_nm_guest s_g;
static int s_have_g;
static uint32_t s_arr, s_str[BO3_NM_MAX][BO3_NM_KINDS];
static uint32_t s_rstr[BO3_CC_REGIONS_MAX], s_need;   /* G8-RG4: region texts; the host array's entries */
static uint32_t s_installs, s_swaps, s_refused;
static uint32_t s_note_lo, s_note_hi;
static int s_noted;

/* PLATFORM-P3 (P-11): the World Tour events' texts (bm_wtour.c registers every declared event) */
_Static_assert(BO3_NM_EVENT_BASE == BO3_NM_REGION_BASE + BO3_CC_REGIONS_MAX, "event texts follow the region texts");
_Static_assert(BO3_NM_EVENT_BASE + 1u + 2u * BO3_NM_EVENTS_MAX <= 0x8000u, "host text IDs below 0x8000");
static struct { char key[112]; char text[2][BO3_NM_EVENT_TEXT]; } s_evt[BO3_NM_EVENTS_MAX];
static uint32_t s_nev, s_nev_inst, s_evstr[BO3_NM_EVENTS_MAX][2], s_evgen;
static int s_ev_closed;

int bo3_nm_event_texts(const char *key, const char *name, const char *help)
{
    if (!key || !*key || strlen(key) >= sizeof s_evt[0].key || (name && strlen(name) >= BO3_NM_EVENT_TEXT) ||
        (help && strlen(help) >= BO3_NM_EVENT_TEXT))
        return 1;
    if (s_ev_closed)
        return 2;
    for (uint32_t j = 0; j < s_nev; j++)
        if (!strcmp(s_evt[j].key, key))
            return 1;
    if (s_nev == BO3_NM_EVENTS_MAX)
        return 3;
    memset(&s_evt[s_nev], 0, sizeof s_evt[0]);
    snprintf(s_evt[s_nev].key, sizeof s_evt[0].key, "%s", key);
    snprintf(s_evt[s_nev].text[0], BO3_NM_EVENT_TEXT, "%s", name ? name : "");
    snprintf(s_evt[s_nev].text[1], BO3_NM_EVENT_TEXT, "%s", help ? help : "");
    s_nev++;
    return 0;
}

void bo3_nm_event_texts_reset(void)
{
    memset(s_evt, 0, sizeof s_evt);
    memset(s_evstr, 0, sizeof s_evstr);
    s_nev = s_nev_inst = s_evgen = 0;
    s_ev_closed = 0;
}

/* GP-CARS2: texts of cars added by mods (bm_cars.c registers every declared car) */
_Static_assert(BO3_NM_CAR_BASE == BO3_NM_EVENT_BASE + 1u + 2u * BO3_NM_EVENTS_MAX, "car texts follow the event texts");
_Static_assert(BO3_NM_CAR_BASE + 1u + 2u * BO3_NM_CARS_MAX <= 0x8000u, "host text IDs below 0x8000");
static struct { uint64_t id; char text[2][BO3_NM_CAR_TEXT]; uint8_t dropped; } s_car[BO3_NM_CARS_MAX];
static uint32_t s_ncar, s_ncar_inst, s_carstr[BO3_NM_CARS_MAX][2], s_cargen;
static int s_car_closed;
/* GP-VEH1: series titles */
_Static_assert(BO3_NM_SERIES_BASE + BO3_NM_SERIES_MAX <= 0x8000u, "host text IDs below 0x8000");
static struct { char text[BO3_NM_CAR_TEXT]; uint8_t set; } s_ser[BO3_NM_SERIES_MAX];
static uint32_t s_nser, s_nser_inst, s_serstr[BO3_NM_SERIES_MAX];

void bo3_nm_car_texts_drop(uint64_t id)
{
    for (uint32_t j = 0; j < s_ncar; j++)
        if (s_car[j].id == id)
            s_car[j].dropped = 1;
}

int bo3_nm_series_texts(uint32_t k, const char *title)
{
    size_t len = title ? strlen(title) : 0;
    if (k >= BO3_NM_SERIES_MAX || !len || len >= BO3_NM_CAR_TEXT)
        return k >= BO3_NM_SERIES_MAX ? 3 : 1;
    if (s_car_closed)
        return 2;
    memset(&s_ser[k], 0, sizeof s_ser[k]);
    for (size_t c = 0; c < len; c++)
        s_ser[k].text[c] = (char)toupper((unsigned char)title[c]);
    s_ser[k].set = 1;
    if (k + 1u > s_nser)
        s_nser = k + 1u;
    return 0;
}

int bo3_nm_car_texts(uint64_t id, const char *name)
{
    size_t len = name ? strlen(name) : 0;
    if (!id || len >= BO3_NM_CAR_TEXT)
        return 1;
    if (s_car_closed)
        return 2;
    for (uint32_t j = 0; j < s_ncar; j++)
        if (s_car[j].id == id)
            return 1;
    if (s_ncar == BO3_NM_CARS_MAX)
        return 3;
    memset(&s_car[s_ncar], 0, sizeof s_car[0]);
    s_car[s_ncar].id = id;
    for (size_t k = 0; k < len; k++) {
        s_car[s_ncar].text[BO3_NM_CAR_UPPER][k] = (char)toupper((unsigned char)name[k]);
        s_car[s_ncar].text[BO3_NM_CAR_MIXED][k] = name[k];
    }
    s_ncar++;
    return 0;
}

void bo3_nm_car_texts_reset(void)
{
    memset(s_car, 0, sizeof s_car);
    memset(s_carstr, 0, sizeof s_carstr);
    s_ncar = s_ncar_inst = s_cargen = 0;
    s_car_closed = 0;
    memset(s_ser, 0, sizeof s_ser);
    memset(s_serstr, 0, sizeof s_serstr);
    s_nser = s_nser_inst = 0;
}

/* GP-FETEX1: the 4th World Tour region's map-page texts (bm_fetex.c registers them); GP-P4.3 R1: after the series titles */
_Static_assert(BO3_NM_MAP_BASE == BO3_NM_SERIES_BASE + BO3_NM_SERIES_MAX, "map texts follow the series titles");
_Static_assert(BO3_NM_MAP_BASE + 2u <= 0x8000u, "host text IDs below 0x8000");
static char s_map[2][BO3_NM_MAP_TEXT];
static uint32_t s_nmap, s_nmap_inst, s_mapstr[2];
static int s_map_closed;

int bo3_nm_map_texts(const char *place, const char *ticker)
{
    if ((!place || !*place) && (!ticker || !*ticker))
        return 1;
    if ((place && strlen(place) >= BO3_NM_MAP_TEXT) || (ticker && strlen(ticker) >= BO3_NM_MAP_TEXT))
        return 1;
    if (s_map_closed)
        return 2;
    if (s_nmap)
        return 3;
    snprintf(s_map[0], BO3_NM_MAP_TEXT, "%s", place ? place : "");
    snprintf(s_map[1], BO3_NM_MAP_TEXT, "%s", ticker ? ticker : "");
    for (char *p = s_map[0]; *p; p++)
        *p = (char)toupper((unsigned char)*p);         /* the map page shows place names in upper case (retail "SILVER LAKE") */
    s_nmap = 2;
    return 0;
}

void bo3_nm_map_texts_reset(void)
{
    memset(s_map, 0, sizeof s_map);
    memset(s_mapstr, 0, sizeof s_mapstr);
    s_nmap = s_nmap_inst = 0;
    s_map_closed = 0;
}

static int char_ok(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '-' ||
           c == '\'' || c == '.' || c == '&';
}

static nm_track *find(uint64_t id)
{
    for (uint32_t i = 0; i < s_n; i++)
        if (s_t[i].id == id)
            return &s_t[i];
    return NULL;
}

/* one list ("names" / "locations"): "ID = text" entries */
static int parse_list(recomp_cfg *cfg, const char *key, uint32_t kind, uint32_t max, const bo3_cc_decl *d, char *why,
                      size_t wn)
{
    size_t cnt;
    if (recomp_cfg_type_of(cfg, key) == RCFG_NONE)
        return 1;
    if (recomp_cfg_type_of(cfg, key) != RCFG_ARRAY) {
        snprintf(why, wn, "%s must be a list of \"ID = text\"", key);
        return 0;
    }
    cnt = recomp_cfg_array_len(cfg, key);
    for (size_t i = 0; i < cnt; i++) {
        char line[160], *eq, *a, *b;
        const char *s = recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
        uint64_t id;
        uint32_t j;
        nm_track *t;
        size_t len;
        if (!s || strlen(s) >= sizeof line || !(eq = strchr(strcpy(line, s), '='))) {
            snprintf(why, wn, "%s[%u] is not \"ID = text\"", key, (unsigned)i);
            return 0;
        }
        *eq = 0;
        for (a = line; *a == ' '; a++)
            ;
        for (char *e = a + strlen(a); e > a && e[-1] == ' ';)
            *--e = 0;
        for (b = eq + 1; *b == ' '; b++)
            ;
        for (char *e = b + strlen(b); e > b && e[-1] == ' ';)
            *--e = 0;
        if (!bo3_cc_encode(a, &id)) {
            snprintf(why, wn, "%s: \"%s\" is not a track ID", key, a);
            return 0;
        }
        for (j = 0; j < d->n && d->id[j] != id; j++)
            ;
        if (j == d->n) {
            snprintf(why, wn, "%s names %s, which is not in this mod's add list", key, a);
            return 0;
        }
        len = strlen(b);
#if MUT != 3
        if (len == 0 || len > max) {
            snprintf(why, wn, "%s: the text for %s has %u characters; 1 .. %u fit the game's menus", key, a, (unsigned)len,
                     (unsigned)max);
            return 0;
        }
#else
        (void)max;
        if (len > BO3_NM_NAME_MAX)
            len = BO3_NM_NAME_MAX;              /* defect: only the buffer bound, not the game's limit */
        b[len] = 0;
#endif
        for (size_t k = 0; k < len; k++)
            if (!char_ok(b[k])) {
                snprintf(why, wn, "%s: the text for %s has the character '%c'; use A-Z a-z 0-9, space and - ' . &", key, a, b[k]);
                return 0;
            }
        t = find(id);
        if (!t) {
#if MUT != 6
            if (s_n == BO3_NM_MAX) {
#else
            if (s_n + 1u == BO3_NM_MAX) {       /* defect (G8-TL): the last named-track slot unusable */
#endif
                snprintf(why, wn, "more than %u named tracks (every track the track list can hold)", (unsigned)BO3_NM_MAX);
                return 0;
            }
            t = &s_t[s_n++];
            memset(t, 0, sizeof *t);
            t->id = id;
        }
        if (t->text[kind][0]) {
            snprintf(why, wn, "%s gives %s a second text", key, a);
            return 0;
        }
        memcpy(t->text[kind], b, len + 1);
        if (kind == BO3_NM_NAME)
            for (size_t k = 0; k <= len; k++)
                t->text[BO3_NM_UPPER][k] = (char)toupper((unsigned char)b[k]);
    }
    return 1;
}

int bo3_nm_parse(const char *text, size_t n, char *why, size_t wn)
{
    char err[200];
    bo3_cc_decl d;
    recomp_cfg *cfg;
    char *buf;
    int ok;
    uint32_t keep = s_n;
    if (!bo3_cc_parse(text, n, &d, why, wn))
        return 0;
    if (!d.present)
        return 1;
    for (uint32_t i = 0; i < d.n && s_ndecl < sizeof s_decl / sizeof s_decl[0]; i++)
        s_decl[s_ndecl++] = d.id[i];           /* G8-E4: declared added tracks */
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
    ok = parse_list(cfg, "bmashup.tracks.names", BO3_NM_NAME, BO3_NM_NAME_MAX, &d, why, wn) &&
         parse_list(cfg, "bmashup.tracks.locations", BO3_NM_LOCATION, BO3_NM_LOC_MAX, &d, why, wn);
    recomp_cfg_free(cfg);
    if (!ok)
        s_n = keep;                             /* nothing of a refused mod stays */
    return ok;
}

uint32_t bo3_nm_count(void)
{
    return s_n;
}

const char *bo3_nm_get(uint64_t id, uint32_t kind)
{
    nm_track *t = kind < BO3_NM_KINDS ? find(id) : NULL;
    return t && t->text[kind][0] ? t->text[kind] : NULL;   /* (a plugin's text lives in guest memory only) */
}

void bo3_nm_set_guest(const bo3_nm_guest *g)
{
    s_g = *g;
    s_have_g = 1;
}

#ifdef BO3_NAMES_GAME
static int s_loaded;
static void load_once(void)
{
    if (!s_loaded) {
        s_loaded = 1;
        bo3_nm_game_load();
    }
}
#else
static void load_once(void) {}
#endif

/* G8-E4: a plugin's text (bmashup.names): the block's contents are checked here (UTF-16LE, NUL-terminated inside the block,
 * 1 .. max characters, the same character set as mod.toml names); applied at the table install, if the track is a declared
 * added track and no mod named that kind. BM-style codes: 0 ok, 1 bad argument / text, 2 closed (the table is installed),
 * 3 conflict (another plugin named it first). */
int bo3_nm_plugin_text(const void *owner, uint64_t id, uint32_t kind, uint32_t va, uint32_t size)
{
    uint32_t max = kind == BO3_NM_LOCATION ? BO3_NM_LOC_MAX : BO3_NM_NAME_MAX, len = 0;
    if (kind >= BO3_NM_KINDS || !owner)
        return 1;
    if (s_closed)
        return 2;
    for (;; len++) {
        uint16_t ch;
        if (2u * len + 2u > size || !bo3_guest_read(va + 2u * len, &ch, 2))
            return 1;                           /* no terminator inside the block */
        if (!ch)
            break;
#if MUT != 5
        if (ch > 0x7Fu || !char_ok((char)ch))
            return 1;
#endif
        if (len + 1u > max)
            return 1;
    }
    if (!len)
        return 1;
    for (uint32_t i = 0; i < s_npend; i++)
        if (s_pend[i].id == id && s_pend[i].kind == kind)
            return 3;
    if (s_npend == BO3_NM_MAX * BO3_NM_KINDS)
        return 1;
    s_pend[s_npend].id = id;
    s_pend[s_npend].kind = kind;
    s_pend[s_npend].va = va;
    s_pend[s_npend].owner = owner;
    s_npend++;
    return 0;
}

static void apply_pending(void)
{
    if (s_closed)
        return;
    s_closed = 1;
    for (uint32_t i = 0; i < s_npend; i++) {
        uint32_t k, j;
        nm_track *t;
        char name[13];
        bo3_cc_decode(s_pend[i].id, name);
        for (j = 0; j < s_ndecl && s_decl[j] != s_pend[i].id; j++)
            ;
        if (j == s_ndecl) {
            fprintf(stderr, "[NAMES] a plugin's text for %s ignored: not a track a mod adds\n", name);
            continue;
        }
        t = find(s_pend[i].id);
        if (!t) {
            if (s_n == BO3_NM_MAX)
                continue;
            t = &s_t[s_n++];
            memset(t, 0, sizeof *t);
            t->id = s_pend[i].id;
        }
        k = s_pend[i].kind;
        if (t->text[k][0]) {
            fprintf(stderr, "[NAMES] a plugin's text for %s ignored: its mod names that already\n", name);
            continue;
        }
        t->pva[k] = s_pend[i].va;
        fprintf(stderr, "[NAMES] %s: kind %u from a plugin's block 0x%08X\n", name, (unsigned)k, (unsigned)s_pend[i].va);
    }
}

/* after the game relocated its language table: point it at the host's larger copy (once per table) */
void bo3_nm_gen_table_ready(void)
{
    uint32_t blob, n, old, need, nreg;
    load_once();
    apply_pending();
    nreg = bo3_cc_region_count();               /* G8-RG4: a declared region's text also needs the host array */
    if (!s_have_g || (!s_n && !nreg && !s_nev && !s_ncar && !s_nser && !s_nmap))   /* P3: World Tour event texts (GP-CARS2:
                                                                           * car texts; GP-VEH1: series titles; GP-FETEX1: map texts) too */
        return;
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!blob)
        return;
    old = s_g.rd32(s_g.user, blob + 0xCu);
    n = s_g.rd32(s_g.user, blob + 8u);
#if MUT != 2
    if (s_arr && old == s_arr)
        return;                                 /* already ours: a second call changes nothing */
#endif
    if (n == 0 || n > BO3_NM_BASE) {
        s_refused++;
        fprintf(stderr, "[NAMES] the game's text table (0x%08X, pointers 0x%08X) has %u strings (host IDs start at %u): "
                "added-track names off\n", (unsigned)blob, (unsigned)old, (unsigned)n, (unsigned)BO3_NM_BASE);
        return;
    }
    need = s_nmap ? BO3_NM_MAP_BASE + 2u :                                    /* GP-FETEX1 (GP-P4.3 R1: the highest range) */
           s_nser ? BO3_NM_SERIES_BASE + s_nser :                              /* GP-VEH1 */
           s_ncar ? BO3_NM_CAR_BASE + 1u + 2u * s_ncar :                       /* GP-CARS2 */
           s_nev ? BO3_NM_EVENT_BASE + 1u + 2u * s_nev :                       /* P3 (P-11) */
           nreg ? BO3_NM_REGION_BASE + nreg : BO3_NM_BASE + BO3_NM_KINDS * s_n;
    if (s_arr && need != s_need)
        need = s_need;                          /* the array was sized at its first install (declarations are fixed by then) */
    if (!s_arr) {
        s_need = need;
        s_arr = s_g.alloc(s_g.user, need * 4u);
        for (uint32_t k = 0; s_arr && k < nreg && k < BO3_CC_REGIONS_MAX; k++) {   /* G8-RG4: the region texts */
            const char *t = bo3_cc_region_at(k)->text;
            size_t len = strlen(t);
            s_rstr[k] = s_g.alloc(s_g.user, (uint32_t)(2u * (len + 1u)));
            if (!s_rstr[k]) {
                s_arr = 0;
                break;
            }
            for (size_t c = 0; c <= len; c++)
                s_g.wr16(s_g.user, s_rstr[k] + 2u * (uint32_t)c, (uint16_t)(unsigned char)t[c]);
        }
        for (uint32_t i = 0; s_arr && i < s_n; i++)
            for (uint32_t k = 0; k < BO3_NM_KINDS; k++) {
                const char *t = s_t[i].text[k];
                size_t len = strlen(t);
                s_str[i][k] = s_t[i].pva[k];   /* G8-E4: a plugin's frozen block is used as it is */
                if (s_str[i][k])
                    continue;
                if (!len)
                    continue;
                s_str[i][k] = s_g.alloc(s_g.user, (uint32_t)(2u * (len + 1u)));
                if (!s_str[i][k]) {
                    s_arr = 0;
                    break;
                }
                for (size_t c = 0; c <= len; c++)
                    s_g.wr16(s_g.user, s_str[i][k] + 2u * (uint32_t)c, (uint16_t)(unsigned char)t[c]);
            }
        if (s_arr && s_nev) {                   /* PLATFORM-P3 (P-11): the generic help, then each event's name / help */
            s_ev_closed = 1;
            s_nev_inst = s_nev;
            for (uint32_t j = 0; s_arr && j <= 2u * s_nev; j++) {
                const char *t = j ? s_evt[(j - 1u) / 2u].text[(j - 1u) % 2u] : BO3_NM_EVENT_HELP_DEFAULT;
                size_t len = strlen(t);
                uint32_t va;
                if (!len)
                    continue;
                va = s_g.alloc(s_g.user, (uint32_t)(2u * (len + 1u)));
                if (!va) {
                    s_arr = 0;
                    break;
                }
                for (size_t c = 0; c <= len; c++)
                    s_g.wr16(s_g.user, va + 2u * (uint32_t)c, (uint16_t)(unsigned char)t[c]);
                if (j)
                    s_evstr[(j - 1u) / 2u][(j - 1u) % 2u] = va;
                else
                    s_evgen = va;
            }
        }
        if (s_arr && s_ncar) {                  /* GP-CARS2: the generic award text, then each car's two names */
            s_car_closed = 1;
            s_ncar_inst = s_ncar;
            for (uint32_t j = 0; s_arr && j <= 2u * s_ncar; j++) {
                const char *t = j ? s_car[(j - 1u) / 2u].text[(j - 1u) % 2u] : BO3_NM_CAR_AWARD;
                size_t len = strlen(t);
                uint32_t va;
                if (!len)
                    continue;
                va = s_g.alloc(s_g.user, (uint32_t)(2u * (len + 1u)));
                if (!va) {
                    s_arr = 0;
                    break;
                }
                for (size_t c = 0; c <= len; c++)
                    s_g.wr16(s_g.user, va + 2u * (uint32_t)c, (uint16_t)(unsigned char)t[c]);
                if (j)
                    s_carstr[(j - 1u) / 2u][(j - 1u) % 2u] = va;
                else
                    s_cargen = va;
            }
        }
        if (s_arr && s_nser) {                  /* GP-VEH1: the series titles */
            s_car_closed = 1;
            s_nser_inst = s_nser;
            for (uint32_t k = 0; s_arr && k < s_nser; k++) {
                size_t len = strlen(s_ser[k].text);
                uint32_t va;
                if (!s_ser[k].set || !len)
                    continue;
                va = s_g.alloc(s_g.user, (uint32_t)(2u * (len + 1u)));
                if (!va) {
                    s_arr = 0;
                    break;
                }
                for (size_t c = 0; c <= len; c++)
                    s_g.wr16(s_g.user, va + 2u * (uint32_t)c, (uint16_t)(unsigned char)s_ser[k].text[c]);
                s_serstr[k] = va;
            }
        }
        if (s_arr && s_nmap) {                  /* GP-FETEX1: the map page's place name and ticker */
            s_map_closed = 1;
            s_nmap_inst = s_nmap;
            for (uint32_t j = 0; s_arr && j < 2u; j++) {
                size_t len = strlen(s_map[j]);
                uint32_t va;
                if (!len)
                    continue;
                va = s_g.alloc(s_g.user, (uint32_t)(2u * (len + 1u)));
                if (!va) {
                    s_arr = 0;
                    break;
                }
                for (size_t c = 0; c <= len; c++)
                    s_g.wr16(s_g.user, va + 2u * (uint32_t)c, (uint16_t)(unsigned char)s_map[j][c]);
                s_mapstr[j] = va;
            }
        }
        if (!s_arr) {
            s_refused++;
            fprintf(stderr, "[NAMES] no guest memory for the text table copy: added-track names off\n");
            return;
        }
    }
    {
        uint32_t unknown = s_g.rd32(s_g.user, old + 4u * BO3_NM_UNKNOWN);
        for (uint32_t i = 0; i < n; i++)
            s_g.wr32(s_g.user, s_arr + 4u * i, s_g.rd32(s_g.user, old + 4u * i));
        for (uint32_t i = n; i < BO3_NM_BASE; i++)
            s_g.wr32(s_g.user, s_arr + 4u * i, unknown);
        for (uint32_t i = 0; i < s_n; i++)
            for (uint32_t k = 0; k < BO3_NM_KINDS; k++)
                s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_BASE + BO3_NM_KINDS * i + k), s_str[i][k] ? s_str[i][k] : unknown);
        for (uint32_t i = BO3_NM_BASE + BO3_NM_KINDS * s_n; i < need; i++)   /* G8-RG4: the unused named-track slots */
            s_g.wr32(s_g.user, s_arr + 4u * i, unknown);
        for (uint32_t k = 0; k < nreg && k < BO3_CC_REGIONS_MAX && BO3_NM_REGION_BASE + k < need; k++)
#if MUT != 7
            s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_REGION_BASE + k), s_rstr[k] ? s_rstr[k] : unknown);
#else
            s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_REGION_BASE + k - 1u), s_rstr[k] ? s_rstr[k] : unknown);   /* defect */
#endif
        if (s_nev_inst && BO3_NM_EVENT_BASE < need) {   /* PLATFORM-P3 (P-11): the event texts */
            s_g.wr32(s_g.user, s_arr + 4u * BO3_NM_EVENT_BASE, s_evgen ? s_evgen : unknown);
            for (uint32_t j = 0; j < s_nev_inst; j++)
                for (uint32_t k = 0; k < 2u; k++)
                    if (BO3_NM_EVENT_BASE + 1u + 2u * j + k < need)
                        s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_EVENT_BASE + 1u + 2u * j + k), s_evstr[j][k] ? s_evstr[j][k] : unknown);
        }
        if (s_ncar_inst && BO3_NM_CAR_BASE < need) {   /* GP-CARS2: the car texts */
#if MUT != 8
            s_g.wr32(s_g.user, s_arr + 4u * BO3_NM_CAR_BASE, s_cargen ? s_cargen : unknown);
#endif
            for (uint32_t j = 0; j < s_ncar_inst; j++)
                for (uint32_t k = 0; k < 2u; k++)
                    if (BO3_NM_CAR_BASE + 1u + 2u * j + k < need)
                        s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_CAR_BASE + 1u + 2u * j + k), s_carstr[j][k] ? s_carstr[j][k] : unknown);
        }
        for (uint32_t k = 0; k < s_nser_inst && BO3_NM_SERIES_BASE + k < need; k++)   /* GP-VEH1: series titles */
            s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_SERIES_BASE + k), s_serstr[k] ? s_serstr[k] : unknown);
    }
    if (s_nmap_inst && BO3_NM_MAP_BASE + 1u < need) {     /* GP-FETEX1: the map texts (every ID before them is filled above) */
        uint32_t unknown = s_g.rd32(s_g.user, old + 4u * BO3_NM_UNKNOWN);
        for (uint32_t j = 0; j < 2u; j++)
            s_g.wr32(s_g.user, s_arr + 4u * (BO3_NM_MAP_BASE + j), s_mapstr[j] ? s_mapstr[j] : unknown);
    }
    s_g.wr32(s_g.user, blob + 0xCu, s_arr);
    s_installs++;
    fprintf(stderr, "[NAMES] text table 0x%08X: %u game strings + %u added-track texts (IDs from 0x%X), pointers at 0x%08X\n",
            (unsigned)blob, (unsigned)n, (unsigned)(BO3_NM_KINDS * s_n), (unsigned)BO3_NM_BASE, (unsigned)s_arr);
    if (nreg)
        fprintf(stderr, "[NAMES] + %u region text(s) at 0x%X (G8-RG4)\n", (unsigned)nreg, (unsigned)BO3_NM_REGION_BASE);
    if (s_nev_inst)
        fprintf(stderr, "[NAMES] + World Tour event texts at 0x%X: the generic help + %u event(s) (P3 P-11)\n",
                (unsigned)BO3_NM_EVENT_BASE, (unsigned)s_nev_inst);
    if (s_ncar_inst)
        fprintf(stderr, "[NAMES] + added-car texts at 0x%X: the award text + %u car(s) (GP-CARS2)\n", (unsigned)BO3_NM_CAR_BASE,
                (unsigned)s_ncar_inst);
}

/* GP-CARS2: only while the host array is the one the game reads and holds that text */
uint32_t bo3_nm_car_text_id(uint64_t id, uint32_t kind, uint32_t dflt)
{
    uint32_t blob;
    if (kind > BO3_NM_CAR_AWARD_KIND || !s_have_g || !s_arr || !s_ncar_inst)
        return dflt;
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!blob || s_g.rd32(s_g.user, blob + 0xCu) != s_arr)
        return dflt;                            /* never an ID the table the game reads cannot resolve */
    for (uint32_t j = 0; j < s_ncar_inst; j++)
        if (s_car[j].id == id) {
            if (s_car[j].dropped)
                return dflt;                    /* GP-VEH1: a refused mod's car */
            if (kind == BO3_NM_CAR_AWARD_KIND)
                return s_cargen ? (s_swaps++, BO3_NM_CAR_BASE) : dflt;
#if MUT == 9
            if (s_carstr[j][kind ^ 1u])         /* defect: the other kind's text */
                return s_swaps++, BO3_NM_CAR_BASE + 1u + 2u * j + (kind ^ 1u);
#else
            if (s_carstr[j][kind])
                return s_swaps++, BO3_NM_CAR_BASE + 1u + 2u * j + kind;
#endif
            return dflt;
        }
    return dflt;
}

/* GP-VEH1: a series title while the host array is the one the game reads and holds it */
uint32_t bo3_nm_series_text_id(uint32_t k, uint32_t dflt)
{
    uint32_t blob;
    if (k >= s_nser_inst || !s_serstr[k] || !s_have_g || !s_arr)
        return dflt;
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!blob || s_g.rd32(s_g.user, blob + 0xCu) != s_arr)
        return dflt;
    s_swaps++;
    return BO3_NM_SERIES_BASE + k;
}

/* GP-FETEX1: only while the host array is the one the game reads and holds that text */
uint32_t bo3_nm_map_text_id(uint32_t kind, uint32_t dflt)
{
    uint32_t blob;
    if (kind > 1u || !s_have_g || !s_arr || !s_nmap_inst || !s_mapstr[kind])
        return dflt;
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!blob || s_g.rd32(s_g.user, blob + 0xCu) != s_arr)
        return dflt;
    s_swaps++;
    return BO3_NM_MAP_BASE + kind;
}

uint32_t bo3_nm_event_text_id(const char *key, uint32_t kind, uint32_t dflt)
{
    uint32_t blob;
    if (kind > 1u || !key || !s_have_g || !s_arr || !s_nev_inst)
        return dflt;
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!blob || s_g.rd32(s_g.user, blob + 0xCu) != s_arr)
        return dflt;                            /* never an ID the table the game reads cannot resolve */
    for (uint32_t j = 0; j < s_nev_inst; j++)
        if (!strcmp(s_evt[j].key, key)) {
            if (s_evstr[j][kind]) {
                s_swaps++;
                return BO3_NM_EVENT_BASE + 1u + 2u * j + kind;
            }
            break;
        }
    return kind == BO3_NM_EV_HELP && s_evgen ? BO3_NM_EVENT_BASE : dflt;
}

/* G8-RG4: only while the host array is the one the game reads and holds the region's string */
uint32_t bo3_nm_region_text_id(uint32_t k)
{
    uint32_t blob;
    if (!s_have_g || !s_arr || k >= bo3_cc_region_count() || k >= BO3_CC_REGIONS_MAX || !s_rstr[k] ||
        BO3_NM_REGION_BASE + k >= s_need)
        return 0;
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!blob || s_g.rd32(s_g.user, blob + 0xCu) != s_arr)
        return 0;
    return BO3_NM_REGION_BASE + k;
}

uint32_t bo3_nm_gen_text(uint32_t dflt, uint32_t kind, uint32_t lo, uint32_t hi)
{
    uint64_t id = (uint64_t)hi << 32 | lo;
    uint32_t blob;
    nm_track *t;
    if (kind >= BO3_NM_KINDS || !s_have_g || !(t = find(id)) || !has_text(t, kind))
        return dflt;
#if MUT != 1
    blob = s_g.rd32(s_g.user, BO3_NM_TABLE_PTR);
    if (!s_arr || !blob || s_g.rd32(s_g.user, blob + 0xCu) != s_arr)
        return dflt;                            /* the host array is not the one the game reads: never an unresolvable ID */
#else
    (void)blob;
#endif
    s_swaps++;
    return BO3_NM_BASE + BO3_NM_KINDS * (uint32_t)(t - s_t) + kind;
}

void bo3_nm_gen_note(uint32_t lo, uint32_t hi)
{
    s_note_lo = lo;
    s_note_hi = hi;
    s_noted = 1;
}

uint32_t bo3_nm_gen_text_noted(uint32_t id, uint32_t kind)
{
#if MUT != 4
    if (id != 0x4EAu || !s_noted)
        return id;                              /* only the game's own fallback is replaced */
#else
    (void)s_noted;
#endif
    return bo3_nm_gen_text(id, kind, s_note_lo, s_note_hi);
}

uint32_t bo3_nm_stats(uint32_t which)
{
    return which == 0 ? s_installs : which == 1 ? s_swaps : s_refused;
}

/* (Superseded in the game build by bm_guest.c's mapping check, G8-E4; kept for NM1c's tests.)
 * NM1 launches 30 / 31: the language table lives at 0x80182000 (a contiguous-memory address, its own view in the runtime,
 * not a 64 MB mirror of low RAM). The host therefore reaches a guest address exactly as the generated code's MEM32 does:
 * the runtime's offset + the full 32-bit address. Only the first 64 KB (never game data) is refused: 0xFFFFFFFF. */
uint32_t bo3_nm_guest_va(uint32_t va)
{
    return va >= 0x10000u && va <= 0xFFFFFFFCu ? va : 0xFFFFFFFFu;
}

#ifdef BO3_NAMES_GAME
#include "modfs.h"

extern ptrdiff_t g_xbox_mem_offset;
extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t align);
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

/* G8-E4: through bm_guest.c - main RAM up to the mapped size, or inside an allocated contiguous block; else refused (reads
 * give 0, which the table install treats as "no table": names off, the game untouched) */
static uint32_t g_rd32(void *u, uint32_t va)
{
    uint32_t v = 0;
    (void)u;
    return bo3_guest_rd32(va, &v) ? v : 0;
}

static void g_wr32(void *u, uint32_t va, uint32_t v)
{
    (void)u;
    bo3_guest_wr32(va, v);
}

static void g_wr16(void *u, uint32_t va, uint16_t v)
{
    (void)u;
    bo3_guest_write(va, &v, 2);
}

static uint32_t g_alloc(void *u, uint32_t size)
{
    (void)u;
    return xbox_HeapAlloc(size, 16u);
}

void bo3_nm_game_load(void)
{
    static const bo3_nm_guest g = {g_rd32, g_wr32, g_wr16, g_alloc, NULL};
    bo3_cc_regions_game_load();                 /* G8-RG4: the declared letters before the names' IDs are checked */
    bo3_nm_set_guest(&g);
    for (int i = 0; i < bo3_modfs_mod_count(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[300];
        char *text = NULL;
        size_t n = 0;
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!bo3_nm_parse(text, n, why, sizeof why)) {
            free(text);
            fprintf(stderr, "[NAMES] FATAL: mod %s: %s\n", m->manifest.id, why);
            fflush(stderr);
            xbox_crash_log_flush(1000);
            bo3_fatal("Takedawn: a mod's track names cannot be used",
                      "The mod \"%s\" declares in its mod.toml ([bmashup.tracks]) names this build cannot use:\n%s\n\n"
                      "Turn the mod off, or fix its declaration.", m->manifest.id, why);
            fflush(stdout);
            fflush(stderr);
            xbox_crash_log_flush(1000);
            _Exit(92);
        }
        free(text);
    }
    {   /* PLATFORM-P3 (P-11): the World Tour declarations now, so their event texts join this table's first install */
        extern void bo3_wt_game_declare(void);
        bo3_wt_game_declare();
    }
    {   /* GP-CARS2: the added cars' declarations now, so their texts join this table's first install */
        extern void bo3_car_game_declare(void);
        bo3_car_game_declare();
    }
    {   /* GP-FETEX1: front-end textures + map texts now, so the map texts join this table's first install */
        extern void bo3_fetex_game_declare(void);
        bo3_fetex_game_declare();
    }
    if (s_n)
        fprintf(stderr, "[NAMES] %u added track(s) named by mods\n", (unsigned)s_n);
}
#endif
