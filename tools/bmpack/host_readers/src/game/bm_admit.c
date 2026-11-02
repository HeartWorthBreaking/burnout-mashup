/* bm_admit.c - PLATFORM-P3 EXPERIMENTAL: two-phase admission of the mods' [bmashup.*] declarations (P-9) and the gameplay
 * labels of data mods (P-4); bm_admit.h describes both. ADMIT_MUT=n (test builds only) compiles one deliberate defect:
 *   1 the EARLIER mod of a clash is refused (wrong mod); 2 a clash refuses nobody (no diagnostic; the services stop the
 *   start as in p2); 3 the validate phase registers into a real service (bo3_cc_regions_parse: partial registration);
 *   4 a clash is found but only the clashing table is dropped (the mod's other tables stay: partial admission);
 *   5 the diagnostic names only the refused mod; 6 the event location capacity is not compared across mods;
 *   7 the dependency on a refused mod is not followed; 8 the tune clash is not compared; GP-MUSIC1: 9 the music soundtrack
 *   name is not compared; 10 a music replace of a track no earlier mod adds is admitted.
 * GP-DEPS1 (platform 0.1.2): [bmashup] requires_mods - the dependency order (bo3_admit_order) and the dependency refusals (in
 * bo3_admit_run_deps' fixpoint). DEPS_MUT=n (test builds only): 2 the required version is not compared; 3 a dependency refused
 * by a clash does not refuse its dependants; 4 a cycle is not found; 5 the order is not changed; 7 a mod refused for a
 * dependency still holds its keys in the clash pass (a later mod clashing only with it would be refused). */
#include "bm_admit.h"
#include "bm_modreq.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_tune_catalog.h"
#include "bm_tune_ai.h"                     /* GP-AITUNE1 */
#include "recomp_cfg.h"
#include "bm_music.h"
#include "bm_music_parse.inc"                  /* GP-MUSIC1: the [bmashup.music] reader, the game's own (no link dependency) */
#include "bm_fetex_parse.inc"                  /* GP-FETEX1: the [bmashup.textures] reader + registry, the service's own */
#if defined(ADMIT_MUT) && ADMIT_MUT == 3
#include "bm_tracks.h"
#endif

#ifndef ADMIT_MUT
#define ADMIT_MUT 0
#endif
#ifndef DEPS_MUT
#define DEPS_MUT 0
#endif
#define AD_REQS 16u                         /* = BO3_PLATFORM_MAX_REQUIRES_MODS (the platform gate checks the count) */

#define AD_TRACKS_PER_MOD 383u             /* BO3_CC_MAX_DECL */
#define AD_EVENTS_PER_MOD 35u              /* BO3_WT_MAX */
#define AD_REGIONS        23u              /* BO3_CC_REGIONS_MAX */
#define AD_TUNE           ((unsigned)BM_TUNE_CATALOG_N)
enum { AD_CAP_LANES = 1u, AD_CAP_LOW = 2u, AD_CAP_STATIC = 4u, AD_CAP_FULL = 8u /* patch 131 */ };   /* = bm_capdecl.h BO3_CAPDECL_* (its reader is not linked here) */
typedef struct ad_cap { int present; uint32_t have, lanes, low_unit_bytes, static_bytes, full_unit_bytes; } ad_cap;  /* patch 131: full */

/* the 18 retail race locations and their free rows for added events (6 - retail events; default.xbe, CONTENT_REPORT s3.2;
 * checked against the real sub_00158080 slot rule in tests\test_p3_admit.c through bm_wtour.c's bo3_wt_location_events) */
static const struct { const char *loc; int free_rows; } k_loc[] = {
    {"US_C3", 2}, {"US_M1", 2}, {"US_C1", 2}, {"US_P2", 2}, {"US_P1", 3}, {"US_C2", 0},
    {"EU_C1", 3}, {"EU_M1", 4}, {"EU_C2", 2}, {"EU_P2", 1}, {"EU_P1", 4}, {"EU_C3", 2}, {"EU_M2", 2}, {"EU_C4", 0},
    {"AS_C3", 2}, {"AS_M1", 1}, {"AS_C1", 2}, {"AS_C2", 1}};
#define AD_NLOC ((int)(sizeof k_loc / sizeof k_loc[0]))

int bo3_admit_location_free(const char *loc)
{
    for (int i = 0; loc && i < AD_NLOC; i++)
        if (!strcmp(k_loc[i].loc, loc))
            return k_loc[i].free_rows;
    return -1;
}

const char *bo3_admit_kind_name(int k)
{
    static const char *const n[BO3_AK_COUNT] = {"none", "track id", "track name", "track location", "region letter",
                                                "event key", "event location capacity", "track list capacity",
                                                "tuning value", "needs a track", "needs a region", "needs a mod",
                                                "dependency cycle", "music declaration", "music soundtrack", "music track",
                                                "music capacity", "front-end textures", "front-end texture registry"};
    return k >= 0 && k < BO3_AK_COUNT ? n[k] : "?";
}

/* ---------------------------------------------------------------- phase 1: one mod's tables, read the readers' way */
typedef struct ad_ev {
    char local[33], track[9], loc[6];
} ad_ev;

typedef struct ad_mod {
    unsigned tables, bad;                  /* BO3_AT_* declared / not decidable here */
    uint32_t nreg;
    struct { char letter; char text[18]; unsigned dj; } reg[AD_REGIONS];
    uint32_t ntr;
    char tr[AD_TRACKS_PER_MOD][9];
    unsigned char named[AD_TRACKS_PER_MOD], located[AD_TRACKS_PER_MOD];
    uint32_t nev;
    ad_ev ev[AD_EVENTS_PER_MOD];
    uint32_t ntune;
    struct { uint32_t idx; double v; } tune[AD_TUNE];
    ad_cap cap;
    uint32_t nreq;                         /* GP-DEPS1: [bmashup] requires_mods */
    bo3_modreq req[AD_REQS];
    char req_bad[200];                     /* "" or why an entry cannot be read (the gate refuses it first) */
    bo3_music_decl music;                  /* GP-MUSIC1: [bmashup.music] as the game reads it */
    char music_bad[400];                   /* "" or why the declaration is refused (MUSIC_DECL) */
    fx_decl fx;                            /* GP-FETEX1: the declarations as the service reads them */
    char fx_bad[400];                      /* "" or why they are refused (TEX_DECL) */
} ad_mod;

static recomp_cfg *load(const char *text, size_t n)
{
    char err[200], *buf = (char *)malloc(n + 1);
    recomp_cfg *cfg;
    if (!buf)
        return NULL;
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    return cfg;
}

/* the keys of [prefix] present (1) and all among `keys` (space separated); 0 when absent; -1 an unknown key */
static int table_keys(recomp_cfg *cfg, const char *prefix, const char *keys)
{
    size_t pl = strlen(prefix);
    int present = 0;
    for (size_t i = 0; i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i), *p = keys;
        int known = 0;
        if (strncmp(k, prefix, pl) != 0 || (k[pl] != 0 && k[pl] != '.'))
            continue;
        present = 1;
        if (k[pl] == 0)
            return -1;
        while (*p && !known) {
            size_t w = strcspn(p, " ");
            known = strlen(k + pl + 1) == w && !strncmp(k + pl + 1, p, w);
            p += w;
            while (*p == ' ')
                p++;
        }
        if (!known)
            return -1;
    }
    return present;
}

static const char *arr_str(recomp_cfg *cfg, const char *key, size_t i)
{
    return recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
}

/* "A = B" with spaces trimmed (the readers' rule): 1, else 0 */
static int split_eq(const char *s, char *a, size_t an, char *b, size_t bn, size_t linemax)
{
    char line[400], *eq, *x, *y, *e;
    if (!s || strlen(s) >= linemax || strlen(s) >= sizeof line)
        return 0;
    strcpy(line, s);
    if (!(eq = strchr(line, '=')))
        return 0;
    *eq = 0;
    for (x = line; *x == ' '; x++)
        ;
    for (e = x + strlen(x); e > x && e[-1] == ' ';)
        *--e = 0;
    for (y = eq + 1; *y == ' '; y++)
        ;
    for (e = y + strlen(y); e > y && e[-1] == ' ';)
        *--e = 0;
    if (strlen(x) >= an || strlen(y) >= bn)
        return 0;
    strcpy(a, x);
    strcpy(b, y);
    return 1;
}

static int text_char(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '-' || c == '\'' ||
           c == '.' || c == '&';
}

static int text_ok(const char *s, size_t max)
{
    size_t n = strlen(s);
    if (!n || n > max)
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!text_char(s[i]))
            return 0;
    return 1;
}

/* a track ID's form RR_NN_VN (upper-case letters and digits), as bo3_cc_id_ok before its region rule */
static int track_form(const char *s)
{
    if (strlen(s) != 8 || s[2] != '_' || s[5] != '_')
        return 0;
    for (int i = 0; i < 8; i++)
        if (i != 2 && i != 5 && !((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9')))
            return 0;
    return 1;
}

static int retail_region(const char *t)
{
    return !strncmp(t, "US", 2) || !strncmp(t, "EU", 2) || !strncmp(t, "AS", 2);
}

static int event_id_ok(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > 32)
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!(isalnum((unsigned char)s[i]) || s[i] == '_' || s[i] == '-'))
            return 0;
    return 1;
}

static void read_regions(recomp_cfg *cfg, ad_mod *d)
{
    char a[64], b[64];
    size_t na;
    int r = table_keys(cfg, "bmashup.regions", "version add dj");
    if (!r)
        return;
    d->tables |= BO3_AT_REGIONS;
    if (r < 0 || recomp_cfg_type_of(cfg, "bmashup.regions.version") != RCFG_INT ||
        recomp_cfg_int(cfg, "bmashup.regions.version", 0) != 1 || recomp_cfg_type_of(cfg, "bmashup.regions.add") != RCFG_ARRAY ||
        !(na = recomp_cfg_array_len(cfg, "bmashup.regions.add")) || na > AD_REGIONS)
        goto bad;
    for (size_t i = 0; i < na; i++) {
        if (!split_eq(arr_str(cfg, "bmashup.regions.add", i), a, sizeof a, b, sizeof b, 160) || strlen(a) != 1 ||
            a[0] < 'A' || a[0] > 'Z' || a[0] == 'U' || a[0] == 'E' || a[0] == 'A' || !text_ok(b, 17))
            goto bad;
        for (uint32_t k = 0; k < d->nreg; k++)
            if (d->reg[k].letter == a[0])
                goto bad;
        d->reg[d->nreg].letter = a[0];
        snprintf(d->reg[d->nreg].text, sizeof d->reg[d->nreg].text, "%s", b);
        d->reg[d->nreg++].dj = 0;
    }
    if (recomp_cfg_type_of(cfg, "bmashup.regions.dj") != RCFG_NONE) {
        size_t nd;
        if (recomp_cfg_type_of(cfg, "bmashup.regions.dj") != RCFG_ARRAY)
            goto bad;
        nd = recomp_cfg_array_len(cfg, "bmashup.regions.dj");
        for (size_t i = 0; i < nd; i++) {
            uint32_t k;
            if (!split_eq(arr_str(cfg, "bmashup.regions.dj", i), a, sizeof a, b, sizeof b, 160))
                goto bad;
            for (k = 0; k < d->nreg && !(strlen(a) == 1 && d->reg[k].letter == a[0]); k++)
                ;
            if (k == d->nreg)
                goto bad;
            if (!strcmp(b, "DJUS"))
                d->reg[k].dj = 0;
            else if (!strcmp(b, "DJEU"))
                d->reg[k].dj = 1;
            else if (!strcmp(b, "DJAS"))
                d->reg[k].dj = 2;
            else
                goto bad;
        }
    }
    return;
bad:
    d->nreg = 0;
    d->bad |= BO3_AT_REGIONS;
}

static int track_index(const ad_mod *d, const char *id)
{
    for (uint32_t k = 0; k < d->ntr; k++)
        if (!strcmp(d->tr[k], id))
            return (int)k;
    return -1;
}

static int read_names(recomp_cfg *cfg, ad_mod *d, const char *key, unsigned char *mark, size_t max)
{
    char a[64], b[160];
    size_t cnt;
    if (recomp_cfg_type_of(cfg, key) == RCFG_NONE)
        return 1;
    if (recomp_cfg_type_of(cfg, key) != RCFG_ARRAY)
        return 0;
    cnt = recomp_cfg_array_len(cfg, key);
    for (size_t i = 0; i < cnt; i++) {
        int k;
        if (!split_eq(arr_str(cfg, key, i), a, sizeof a, b, sizeof b, 160) || (k = track_index(d, a)) < 0 || !text_ok(b, max) ||
            mark[k])
            return 0;
        mark[k] = 1;
    }
    return 1;
}

static void read_tracks(recomp_cfg *cfg, ad_mod *d)
{
    size_t na;
    int r = table_keys(cfg, "bmashup.tracks", "version add point_to_point names locations");
    if (!r)
        return;
    d->tables |= BO3_AT_TRACKS;
    if (r < 0 || recomp_cfg_type_of(cfg, "bmashup.tracks.version") != RCFG_INT ||
        recomp_cfg_int(cfg, "bmashup.tracks.version", 0) != 1 || recomp_cfg_type_of(cfg, "bmashup.tracks.add") != RCFG_ARRAY ||
        (na = recomp_cfg_array_len(cfg, "bmashup.tracks.add")) > AD_TRACKS_PER_MOD)
        goto bad;
    for (size_t i = 0; i < na; i++) {
        const char *s = arr_str(cfg, "bmashup.tracks.add", i);
        if (!s || !track_form(s) || track_index(d, s) >= 0)
            goto bad;
        snprintf(d->tr[d->ntr++], sizeof d->tr[0], "%s", s);
    }
    if (recomp_cfg_type_of(cfg, "bmashup.tracks.names") != RCFG_NONE ||
        recomp_cfg_type_of(cfg, "bmashup.tracks.locations") != RCFG_NONE)
        d->tables |= BO3_AT_NAMES;
    if (!read_names(cfg, d, "bmashup.tracks.names", d->named, 27) ||
        !read_names(cfg, d, "bmashup.tracks.locations", d->located, 17)) {
        memset(d->named, 0, sizeof d->named);
        memset(d->located, 0, sizeof d->located);
        d->bad |= BO3_AT_NAMES;
    }
    return;
bad:
    d->ntr = 0;
    memset(d->named, 0, sizeof d->named);
    memset(d->located, 0, sizeof d->located);
    d->bad |= BO3_AT_TRACKS | BO3_AT_NAMES;
}

static void read_events(recomp_cfg *cfg, ad_mod *d)
{
    size_t na;
    long long ver;
    int r = table_keys(cfg, "bmashup.extra_events", "version add stage names help");
    if (!r)
        return;
    d->tables |= BO3_AT_EVENTS;
    ver = recomp_cfg_type_of(cfg, "bmashup.extra_events.version") == RCFG_INT ?
          recomp_cfg_int(cfg, "bmashup.extra_events.version", 0) : 0;
    if (r < 0 || (ver != 1 && ver != 2) ||
        (ver == 1 && (recomp_cfg_type_of(cfg, "bmashup.extra_events.names") != RCFG_NONE ||
                      recomp_cfg_type_of(cfg, "bmashup.extra_events.help") != RCFG_NONE)) ||
        recomp_cfg_type_of(cfg, "bmashup.extra_events.add") != RCFG_ARRAY ||
        !(na = recomp_cfg_array_len(cfg, "bmashup.extra_events.add")) || na > AD_EVENTS_PER_MOD)
        goto bad;
    for (size_t i = 0; i < na; i++) {
        char line[200], *eq, *at, *colon, *id, *tr, *lo, *ty = NULL, *e;
        const char *s = arr_str(cfg, "bmashup.extra_events.add", i);
        ad_ev *v = &d->ev[d->nev];
        if (!s || strlen(s) >= sizeof line || !(eq = strchr(strcpy(line, s), '=')) || !(at = strchr(eq, '@')))
            goto bad;
        *eq = 0;
        *at = 0;
        if ((colon = strchr(at + 1, ':')) != NULL) {
            *colon = 0;
            ty = colon + 1;
        }
        for (char **p = (char *[]){line, eq + 1, at + 1, ty}, **q = p + 4; p < q; p++) {   /* trim */
            if (!*p)
                continue;
            while (**p == ' ')
                (*p)++;
            for (e = *p + strlen(*p); e > *p && e[-1] == ' ';)
                *--e = 0;
        }
        for (id = line; *id == ' '; id++)
            ;
        for (tr = eq + 1; *tr == ' '; tr++)
            ;
        for (lo = at + 1; *lo == ' '; lo++)
            ;
        if (ty)
            while (*ty == ' ')
                ty++;
        if (!event_id_ok(id) || !track_form(tr) || bo3_admit_location_free(lo) < 0 || (ty && strcmp(ty, "race")))
            goto bad;
        for (uint32_t k = 0; k < d->nev; k++)
            if (!strcmp(d->ev[k].local, id))
                goto bad;
        snprintf(v->local, sizeof v->local, "%s", id);
        snprintf(v->track, sizeof v->track, "%s", tr);
        snprintf(v->loc, sizeof v->loc, "%s", lo);
        d->nev++;
    }
    return;
bad:
    d->nev = 0;
    d->bad |= BO3_AT_EVENTS;
}

static int tune_index(const char *name)
{
    for (uint32_t i = 0; i < AD_TUNE; i++)
        if (!strcmp(name, k_bm_tune_catalog[i].full))
            return (int)i;
    return -1;
}

static void read_tune(recomp_cfg *cfg, ad_mod *d)
{
    size_t cnt;
    int r = table_keys(cfg, "bmashup.tune", "version set");
    if (!r)
        return;
    d->tables |= BO3_AT_TUNE;
    if (r < 0)
        goto bad;
    if (recomp_cfg_type_of(cfg, "bmashup.tune.set") == RCFG_NONE)
        return;                             /* the reader: nothing to set (the version is checked only with a set) */
    if (recomp_cfg_type_of(cfg, "bmashup.tune.version") != RCFG_INT ||
        (recomp_cfg_int(cfg, "bmashup.tune.version", 0) != 1 && recomp_cfg_int(cfg, "bmashup.tune.version", 0) != 2))
        goto bad;                           /* GP-AITUNE1: version 2 = + the AI values and signed values */
    cnt = recomp_cfg_array_len(cfg, "bmashup.tune.set");
    for (size_t k = 0; k < cnt; k++) {
        char line[300], *eq, *end, *a, *e;
        const char *s = arr_str(cfg, "bmashup.tune.set", k);
        double v;
        int idx;
        uint32_t j;
        if (!s || strlen(s) >= sizeof line || !(eq = strrchr(strcpy(line, s), '=')))
            goto bad;
        *eq = 0;
        for (a = line; *a == ' ' || *a == '\t'; a++)
            ;
        for (e = a + strlen(a); e > a && (e[-1] == ' ' || e[-1] == '\t');)
            *--e = 0;
        for (eq++; *eq == ' ' || *eq == '\t'; eq++)
            ;
        for (e = eq + strlen(eq); e > eq && (e[-1] == ' ' || e[-1] == '\t');)
            *--e = 0;
        v = strtod(eq, &end);
        if (end == eq || *end || (idx = tune_index(a)) < 0)
            goto bad;
        if (recomp_cfg_int(cfg, "bmashup.tune.version", 0) < 2 && ((uint32_t)idx >= AD_TUNE - BM_TUNE_AI_N || v < 0.0))
            goto bad;                       /* GP-AITUNE1: the reader refuses it (needs version 2): decided there */
        for (j = 0; j < d->ntune && d->tune[j].idx != (uint32_t)idx; j++)
            ;
        if (j == d->ntune) {
            if (d->ntune == AD_TUNE)
                goto bad;
            d->ntune++;
        }
        d->tune[j].idx = (uint32_t)idx;
        d->tune[j].v = v;                    /* the reader sets in order: the last value of a name is the one used */
    }
    return;
bad:
    d->ntune = 0;
    d->bad |= BO3_AT_TUNE;
}

static void read_capacity(recomp_cfg *cfg, ad_cap *c, ad_mod *d);

/* GP-DEPS1: [bmashup] requires_mods, the gate's way (bm_modreq.h); an entry it cannot read: req_bad (fail closed: refused) */
static void read_reqs(recomp_cfg *cfg, ad_mod *d)
{
    size_t cnt;
    if (recomp_cfg_type_of(cfg, "bmashup.requires_mods") == RCFG_NONE)
        return;
    d->tables |= BO3_AT_MODS;
    if (recomp_cfg_type_of(cfg, "bmashup.requires_mods") != RCFG_ARRAY ||
        (cnt = recomp_cfg_array_len(cfg, "bmashup.requires_mods")) > AD_REQS) {
        snprintf(d->req_bad, sizeof d->req_bad, "bmashup.requires_mods is not a list of at most %u entries", AD_REQS);
        return;
    }
    for (size_t i = 0; i < cnt; i++)
        if (!bo3_modreq_parse(arr_str(cfg, "bmashup.requires_mods", i), &d->req[d->nreq], d->req_bad, sizeof d->req_bad)) {
            d->nreq = 0;
            return;
        } else {
            d->nreq++;
        }
}

/* only the requires_mods of a mod.toml (the order needs no other table) */
static void read_reqs_only(const bo3_admit_mod *m, ad_mod *d)
{
    recomp_cfg *cfg;
    if (!m->text || !m->n || !(cfg = load(m->text, m->n)))
        return;
    read_reqs(cfg, d);
    recomp_cfg_free(cfg);
}

/* GP-MUSIC1: [bmashup.music] through the game's reader; a replace must name a mod of the mod's requires_mods (the dependency
 * order then puts the target's mod first, and its refusal refuses this one) */
static void read_music(const bo3_admit_mod *m, ad_mod *d)
{
    const char *ids[AD_REQS];
    if (!m->text || !m->n || !strstr(m->text, "bmashup.music"))
        return;                            /* (the reader is not run on a mod.toml that cannot hold the table) */
    if (!mu_parse(m->text, m->n, m->id ? m->id : "", &d->music, d->music_bad, sizeof d->music_bad)) {
        if (!d->music_bad[0])
            snprintf(d->music_bad, sizeof d->music_bad, "[bmashup.music] cannot be read");
        d->tables |= BO3_AT_MUSIC;
        return;
    }
    if (!d->music.present)
        return;
    d->tables |= BO3_AT_MUSIC;
    for (uint32_t k = 0; k < d->nreq && k < AD_REQS; k++)
        ids[k] = d->req[k].id;
    for (uint32_t k = 0; k < d->music.n; k++)
        if (d->music.e[k].replace && !mu_replace_listed(d->music.e[k].key, ids, (int)d->nreq)) {
            snprintf(d->music_bad, sizeof d->music_bad, "bmashup.music.replace %s: the mod %.*s must be in [bmashup] "
                     "requires_mods (it is the mod whose track is replaced)", d->music.e[k].key,
                     (int)(strchr(d->music.e[k].key, '/') - d->music.e[k].key), d->music.e[k].key);
            memset(&d->music, 0, sizeof d->music);
            d->music.present = 1;
            return;
        }
}

/* GP-FETEX1: the mod's TXD file from its folder ("/" or "\\" separators; no ".." / absolute paths: the reader refuses them) */
static void read_fetex(const bo3_admit_mod *m, ad_mod *d)
{
    char rel[160], path[1200];
    const char *ids[AD_REQS];
    uint8_t *b = NULL;
    size_t n = 0;
    int have = 0;
    if (!m->text || !m->n || (!strstr(m->text, "bmashup.textures") && !strstr(m->text, "bmashup.wt_map_art") &&
                              !strstr(m->text, "photos")))
        return;
    fx_txd_path(m->text, m->n, rel, sizeof rel);
    if (rel[0] && m->folder && !strstr(rel, "..") && strlen(m->folder) + strlen(rel) + 2 < sizeof path) {
        FILE *f;
        snprintf(path, sizeof path, "%s/%s", m->folder, rel);
        if ((f = fopen(path, "rb")) != NULL) {
            long len;
            if (!fseek(f, 0, SEEK_END) && (len = ftell(f)) > 0 && len <= (long)BO3_FETEX_POOL_MAX && !fseek(f, 0, SEEK_SET) &&
                (b = (uint8_t *)malloc((size_t)len)) != NULL && fread(b, 1, (size_t)len, f) == (size_t)len) {
                n = (size_t)len;
                have = 1;
            }
            fclose(f);
        }
    }
    for (uint32_t k = 0; k < d->nreq && k < AD_REQS; k++)
        ids[k] = d->req[k].id;
    if (!fx_parse(m->id ? m->id : "", ids, (int)(d->nreq < AD_REQS ? d->nreq : AD_REQS), m->text, m->n, have ? b : NULL, n,
                  have, &d->fx, d->fx_bad, sizeof d->fx_bad) && !d->fx_bad[0])
        snprintf(d->fx_bad, sizeof d->fx_bad, "the front-end texture declarations cannot be read");
    if (d->fx_bad[0] || d->fx.has_tex || d->fx.has_map || d->fx.has_photos)
        d->tables |= BO3_AT_TEXTURES;
    free(b);
}

static void read_mod(const bo3_admit_mod *m, ad_mod *d)
{
    recomp_cfg *cfg;
    char why[300];
    (void)why;
    if (!m->text || !m->n)
        return;
    cfg = load(m->text, m->n);
    if (!cfg) {
        d->bad = BO3_AT_REGIONS | BO3_AT_TRACKS | BO3_AT_NAMES | BO3_AT_EVENTS | BO3_AT_TUNE | BO3_AT_CAPACITY;
        return;
    }
#if ADMIT_MUT == 3
    bo3_cc_regions_parse(m->text, m->n, why, sizeof why);   /* defect: a real service registers during the validate phase */
#endif
    read_regions(cfg, d);
    read_tracks(cfg, d);
    read_events(cfg, d);
    read_tune(cfg, d);
    read_capacity(cfg, &d->cap, d);
    read_reqs(cfg, d);
    recomp_cfg_free(cfg);
    read_music(m, d);
    read_fetex(m, d);                      /* GP-FETEX1 (after read_reqs: cross-mod targets need requires_mods) */
}

/* [bmashup.capacity] the way bm_capdecl.c bo3_capdecl_parse reads it (version 1: lanes, low_unit_bytes, static_bytes, whole
 * numbers 0 .. 0xFFFFFFFF); the services' range checks stay theirs (exit 91 at commit) */
static void read_capacity(recomp_cfg *cfg, ad_cap *c, ad_mod *d)
{
    static const struct { const char *key; uint32_t bit; } f[4] = {{"bmashup.capacity.lanes", AD_CAP_LANES},
        {"bmashup.capacity.low_unit_bytes", AD_CAP_LOW}, {"bmashup.capacity.static_bytes", AD_CAP_STATIC},
        {"bmashup.capacity.full_unit_bytes", AD_CAP_FULL}};                  /* patch 131 */
    int r = table_keys(cfg, "bmashup.capacity", "version lanes low_unit_bytes static_bytes gamedata_bytes full_unit_bytes");
    if (!r)
        return;
    d->tables |= BO3_AT_CAPACITY;
    if (r < 0 || recomp_cfg_type_of(cfg, "bmashup.capacity.version") != RCFG_INT ||
        recomp_cfg_int(cfg, "bmashup.capacity.version", -1) != 1)
        goto bad;
    c->present = 1;
    for (int k = 0; k < 4; k++) {
        long long v;
        if (recomp_cfg_type_of(cfg, f[k].key) == RCFG_NONE)
            continue;
        v = recomp_cfg_int(cfg, f[k].key, -1);
        if (recomp_cfg_type_of(cfg, f[k].key) != RCFG_INT || v < 0 || v > 0xFFFFFFFFll)
            goto bad;
        c->have |= f[k].bit;
        if (k == 0)
            c->lanes = (uint32_t)v;
        else if (k == 1)
            c->low_unit_bytes = (uint32_t)v;
        else if (k == 3)
            c->full_unit_bytes = (uint32_t)v;
        else
            c->static_bytes = (uint32_t)v;
    }
    return;
bad:
    memset(c, 0, sizeof *c);
    d->bad |= BO3_AT_CAPACITY;
}

/* ---------------------------------------------------------------- phase 1: the clashes, in the mod list's order */
typedef struct ad_reg {                    /* what the admitted earlier mods hold */
    int track_owner_n;
    struct { char id[9]; int owner, named, located; } *tr;
    uint32_t ntr, cap;
    struct { char letter; char text[18]; unsigned dj; int owner; } reg[AD_REGIONS];
    uint32_t nreg;
    int loc_n[AD_NLOC], loc_last[AD_NLOC];
    int tune_owner[AD_TUNE];
    uint32_t added_tracks;
    int last_tracks;                       /* the last admitted mod that adds tracks */
    uint32_t nmst, nmk;                    /* GP-MUSIC1: soundtracks and tracks of the admitted earlier mods */
    struct { char name[BO3_MUSIC_TEXT_MAX + 1]; int owner; } mst[BO3_MUSIC_MAX_MODS];
    struct { char key[sizeof ((bo3_music_entry *)0)->key]; char title[BO3_MUSIC_TEXT_MAX + 1]; int owner, by, st; }
        mk[BO3_MUSIC_MAX_TRACKS];
    int last_music;
    fx_reg fx;                             /* GP-FETEX1: the admitted earlier mods' texture registry */
} ad_reg;

static int reg_track(const ad_reg *g, const char *id)
{
    for (uint32_t k = 0; k < g->ntr; k++)
        if (!strcmp(g->tr[k].id, id))
            return (int)k;
    return -1;
}

static int loc_index(const char *loc)
{
    for (int i = 0; i < AD_NLOC; i++)
        if (!strcmp(k_loc[i].loc, loc))
            return i;
    return -1;
}

static const char *bank(unsigned dj)
{
    return dj == 1 ? "DJEU" : dj == 2 ? "DJAS" : "DJUS";
}

typedef struct ad_ctx {
    const bo3_admit_mod *m;
    bo3_admit_res *r;
} ad_ctx;

/* one clash of mod i with mod o: the first one decides kind / key / other; every one is named in why */
static void clash(ad_ctx *c, int i, int kind, const char *key, int o, const char *fmt, ...)
{
    bo3_admit_res *r = &c->r[i];
    char text[400];
    va_list ap;
    size_t used = strlen(r->why);
    va_start(ap, fmt);
    vsnprintf(text, sizeof text, fmt, ap);
    va_end(ap);
    if (!r->nclash++) {
        r->kind = kind;
        r->other = o;
        snprintf(r->key, sizeof r->key, "%s", key);
    }
    if (used + 8 >= sizeof r->why)
        return;
#if ADMIT_MUT == 5
    snprintf(r->why + used, sizeof r->why - used, "%s%s %s", used ? "; " : "", bo3_admit_kind_name(kind), key);
    (void)text;
#else
    if (o >= 0)
        snprintf(r->why + used, sizeof r->why - used, "%s%s %s: %s mod %s %s (%s)", used ? "; " : "", bo3_admit_kind_name(kind),
                 key, text, c->m[o].id ? c->m[o].id : "?", c->m[o].version && *c->m[o].version ? c->m[o].version : "-",
                 c->m[o].folder ? c->m[o].folder : "?");
    else
        snprintf(r->why + used, sizeof r->why - used, "%s%s %s: %s", used ? "; " : "", bo3_admit_kind_name(kind), key, text);
#endif
}

static int ensure(ad_reg *g, uint32_t more)
{
    if (g->ntr + more <= g->cap)
        return 1;
    {
        uint32_t nc = (g->ntr + more) * 2u + 16u;
        void *p = realloc(g->tr, nc * sizeof *g->tr);
        if (!p)
            return 0;
        g->tr = p;
        g->cap = nc;
    }
    return 1;
}

/* mod i against the registry: 1 = no clash (then registered), 0 = refused (r[i] says why), -1 = out of host memory */
static int check_one(ad_ctx *c, ad_reg *g, const ad_mod *d, int i)
{
    bo3_admit_res *r = &c->r[i];
    char key[80];
    int before = r->nclash;
    /* region letters: the same letter must say the same */
    for (uint32_t k = 0; k < d->nreg; k++)
        for (uint32_t q = 0; q < g->nreg; q++)
            if (g->reg[q].letter == d->reg[k].letter &&
                (strcmp(g->reg[q].text, d->reg[k].text) || g->reg[q].dj != d->reg[k].dj)) {
                snprintf(key, sizeof key, "%c", d->reg[k].letter);
                clash(c, i, BO3_AK_REGION, key, g->reg[q].owner, "this mod says \"%s\" (bank %s), already declared as \"%s\" "
                      "(bank %s) by", d->reg[k].text, bank(d->reg[k].dj), g->reg[q].text, bank(g->reg[q].dj));
            }
    /* tracks, their names and locations */
    for (uint32_t k = 0; k < d->ntr; k++) {
        int t = reg_track(g, d->tr[k]);
        if (t < 0)
            continue;
        clash(c, i, BO3_AK_TRACK_ID, d->tr[k], g->tr[t].owner, "already added by");
        if (d->named[k] && g->tr[t].named)
            clash(c, i, BO3_AK_TRACK_NAME, d->tr[k], g->tr[t].owner, "already named by");
        if (d->located[k] && g->tr[t].located)
            clash(c, i, BO3_AK_TRACK_LOCATION, d->tr[k], g->tr[t].owner, "already given a location text by");
    }
    if (d->ntr && g->added_tracks + d->ntr > BO3_ADMIT_TRACKS && g->added_tracks) {
        snprintf(key, sizeof key, "%u + %u", (unsigned)g->added_tracks, (unsigned)d->ntr);
        clash(c, i, BO3_AK_TRACK_CAPACITY, key, g->last_tracks, "the track list holds %u added tracks (383 - 36 retail); the "
              "earlier mods add %u, this mod %u; the last earlier one is", (unsigned)BO3_ADMIT_TRACKS, (unsigned)g->added_tracks,
              (unsigned)d->ntr);
    }
    /* events: the key (mod/event) and the location lists */
    for (uint32_t k = 0; k < d->nev; k++)
        for (int o = 0; o < i; o++)
            if (!c->r[o].refused && c->m[o].id && c->m[i].id && !strcmp(c->m[o].id, c->m[i].id)) {
                snprintf(key, sizeof key, "%.40s/%.32s", c->m[i].id, d->ev[k].local);
                clash(c, i, BO3_AK_EVENT_KEY, key, o, "already declared by");
                break;
            }
#if ADMIT_MUT != 6
    for (int l = 0; l < AD_NLOC; l++) {
        int mine = 0;
        for (uint32_t k = 0; k < d->nev; k++)
            mine += !strcmp(d->ev[k].loc, k_loc[l].loc);
        if (mine && g->loc_n[l] && mine <= k_loc[l].free_rows && g->loc_n[l] + mine > k_loc[l].free_rows)
            clash(c, i, BO3_AK_EVENT_LOCATION, k_loc[l].loc, g->loc_last[l], "its list shows 6 rows: %d retail event(s) + "
                  "%d added by earlier mods; this mod adds %d; the last earlier one is", 6 - k_loc[l].free_rows, g->loc_n[l], mine);
    }
#endif
#if ADMIT_MUT != 8
    for (uint32_t k = 0; k < d->ntune; k++)
        if (g->tune_owner[d->tune[k].idx] >= 0) {
            snprintf(key, sizeof key, "\"%.76s\"", k_bm_tune_catalog[d->tune[k].idx].full);
            clash(c, i, BO3_AK_TUNE, key, g->tune_owner[d->tune[k].idx], "already set by");
        }
#endif
    /* GP-MUSIC1: [bmashup.music] */
    if (d->music_bad[0])
        clash(c, i, BO3_AK_MUSIC_DECL, "[bmashup.music]", -1, "%s", d->music_bad);
    else if (d->music.present) {
        uint32_t adds = 0;
        for (uint32_t k = 0; k < d->music.n; k++)
            adds += !d->music.e[k].replace;
        if (d->music.soundtrack[0]) {
#if ADMIT_MUT != 9
            for (uint32_t q = 0; q < g->nmst; q++)
#else
            for (uint32_t q = g->nmst; q < g->nmst; q++)   /* defect: the soundtrack name is not compared */
#endif
                if (mu_eq_nocase(g->mst[q].name, d->music.soundtrack))
                    clash(c, i, BO3_AK_MUSIC_SOUNDTRACK, d->music.soundtrack, g->mst[q].owner, "the soundtrack name is "
                          "already used by");
            if (g->nmst >= BO3_MUSIC_MAX_MODS)
                clash(c, i, BO3_AK_MUSIC_CAPACITY, d->music.soundtrack, g->last_music, "EA GAMES TRAX takes %u mod "
                      "soundtracks; the earlier mods have them all; the last earlier one is", BO3_MUSIC_MAX_MODS);
        }
        if (adds && g->nmk + adds > BO3_MUSIC_MAX_TRACKS) {
            snprintf(key, sizeof key, "%u + %u", (unsigned)g->nmk, (unsigned)adds);
            clash(c, i, BO3_AK_MUSIC_CAPACITY, key, g->last_music, "the mods' music holds %u tracks; the earlier mods add "
                  "%u, this mod %u; the last earlier one is", BO3_MUSIC_MAX_TRACKS, (unsigned)g->nmk, (unsigned)adds);
        }
        for (uint32_t k = 0; k < d->music.n; k++) {
            const bo3_music_entry *e = &d->music.e[k];
            uint32_t q;
            if (!e->replace)
                continue;
            for (q = 0; q < g->nmk && strcmp(g->mk[q].key, e->key); q++)
                ;
            if (q == g->nmk) {
                int dep_refused = 0;           /* the target's mod is refused itself: the dependency rule names that */
                for (int o = 0; o < i; o++)
                    if (c->m[o].id && !strncmp(c->m[o].id, e->key, strcspn(e->key, "/")) &&
                        strlen(c->m[o].id) == strcspn(e->key, "/") && c->r[o].refused)
                        dep_refused = 1;
                if (dep_refused)
                    continue;
#if ADMIT_MUT != 10
                clash(c, i, BO3_AK_MUSIC_TRACK, e->key, -1, "replaces a track that no admitted earlier mod adds");
#endif                                                     /* MUT 10, defect: a replace of nothing is admitted */
                continue;
            }
            if (g->mk[q].by >= 0) {
                clash(c, i, BO3_AK_MUSIC_TRACK, e->key, g->mk[q].by, "the track is already replaced by");
                continue;
            }
            for (uint32_t o = 0; o < g->nmk; o++)
                if (o != q && g->mk[o].st == g->mk[q].st && mu_eq_nocase(g->mk[o].title, e->title)) {
                    clash(c, i, BO3_AK_MUSIC_TRACK, e->key, g->mk[o].by >= 0 ? g->mk[o].by : g->mk[o].owner, "the new title "
                          "\"%s\" is already a title of that soundtrack (its file names are the titles), given by", e->title);
                    break;
                }
        }
    }
    /* GP-FETEX1: last, so that its registry joins only for a mod nothing else refuses */
    if (d->fx_bad[0])
        clash(c, i, BO3_AK_TEX_DECL, "[bmashup.textures]", -1, "%s", d->fx_bad);
    else if (r->nclash == before && (d->fx.has_tex || d->fx.has_map || d->fx.has_photos)) {
        char why[400];
        if (!fx_reg_add(&g->fx, c->m[i].id ? c->m[i].id : "", &d->fx, why, sizeof why))
            clash(c, i, BO3_AK_TEX_REG, "[bmashup.textures]", -1, "%s", why);
    }
    if (r->nclash > before)
        return 0;
    /* GP-MUSIC1: mod i's soundtrack and tracks join the registry */
    if (d->music.present && !d->music_bad[0]) {
        int st = -1;
        if (d->music.soundtrack[0] && g->nmst < BO3_MUSIC_MAX_MODS) {
            st = (int)g->nmst++;
            snprintf(g->mst[st].name, sizeof g->mst[st].name, "%s", d->music.soundtrack);
            g->mst[st].owner = i;
        }
        for (uint32_t k = 0; k < d->music.n; k++) {
            const bo3_music_entry *e = &d->music.e[k];
            if (!e->replace && st >= 0 && g->nmk < BO3_MUSIC_MAX_TRACKS) {
                snprintf(g->mk[g->nmk].key, sizeof g->mk[0].key, "%s", e->key);
                snprintf(g->mk[g->nmk].title, sizeof g->mk[0].title, "%s", e->title);
                g->mk[g->nmk].owner = i;
                g->mk[g->nmk].by = -1;
                g->mk[g->nmk++].st = st;
            } else if (e->replace) {
                for (uint32_t q = 0; q < g->nmk; q++)
                    if (!strcmp(g->mk[q].key, e->key)) {
                        g->mk[q].by = i;
                        snprintf(g->mk[q].title, sizeof g->mk[0].title, "%s", e->title);
                    }
            }
        }
        g->last_music = i;
    }
    /* no clash: mod i's keys join the registry */
    for (uint32_t k = 0; k < d->nreg; k++) {
        uint32_t q;
        for (q = 0; q < g->nreg && g->reg[q].letter != d->reg[k].letter; q++)
            ;
        if (q == g->nreg && g->nreg < AD_REGIONS) {
            g->reg[g->nreg].letter = d->reg[k].letter;
            memcpy(g->reg[g->nreg].text, d->reg[k].text, sizeof g->reg[0].text);
            g->reg[g->nreg].dj = d->reg[k].dj;
            g->reg[g->nreg++].owner = i;
        }
    }
    if (!ensure(g, d->ntr))
        return -1;
    for (uint32_t k = 0; k < d->ntr; k++) {
        memcpy(g->tr[g->ntr].id, d->tr[k], 9);
        g->tr[g->ntr].owner = i;
        g->tr[g->ntr].named = d->named[k];
        g->tr[g->ntr++].located = d->located[k];
    }
    if (d->ntr) {
        g->added_tracks += d->ntr;
        g->last_tracks = i;
    }
    for (uint32_t k = 0; k < d->nev; k++) {
        int l = loc_index(d->ev[k].loc);
        if (l >= 0) {
            g->loc_n[l]++;
            g->loc_last[l] = i;
        }
    }
    for (uint32_t k = 0; k < d->ntune; k++)
        g->tune_owner[d->tune[k].idx] = i;
    return 1;
}

static const char *sys_of(uint32_t idx)
{
    const char *f = k_bm_tune_catalog[idx].full;
    if (!strncmp(f, "AI/", 3))
        return "ai";                        /* GP-AITUNE1 */
    if (!strncmp(f, "Score/Burnout Points", 20) || !strncmp(f, "Score/BP Categories", 19) || !strncmp(f, "Score/Distance", 14))
        return "scoring";
    return "boost";
}

static double shipped(uint32_t idx)
{
    uint32_t raw = k_bm_tune_catalog[idx].shipped;
    float f;
    if (idx >= AD_TUNE - BM_TUNE_AI_N)
        return k_bm_tune_ai[idx - (AD_TUNE - BM_TUNE_AI_N)].vdefault;   /* GP-AITUNE1: the code default (BSS before) */
    if (k_bm_tune_catalog[idx].type == 1u)   /* BM_TUNE_INT */
        return (double)raw;
    memcpy(&f, &raw, 4);
    return (double)f;
}

static void make_label(const ad_mod *d, bo3_admit_res *r)
{
    static const char *const sys[3] = {"boost", "scoring", "ai"};   /* GP-AITUNE1: + ai */
    size_t o = 0;
    char page[96] = "CHANGES GAMEPLAY:";
    int first_sys = 1;
    r->label[0] = r->page[0] = 0;
    if (!d->ntune && !(d->cap.present && d->cap.have))
        return;
    r->gameplay = 1;
    o += (size_t)snprintf(r->label + o, sizeof r->label - o, "changes gameplay:");
    for (int s = 0; s < 3; s++) {
        int any = 0;
        for (uint32_t k = 0; k < d->ntune; k++) {
            if (strcmp(sys_of(d->tune[k].idx), sys[s]))
                continue;
            if (!any && o < sizeof r->label)
                o += (size_t)snprintf(r->label + o, sizeof r->label - o, "%s%s (", first_sys ? " " : ", ", sys[s]);
            else if (o < sizeof r->label)
                o += (size_t)snprintf(r->label + o, sizeof r->label - o, ", ");
            if (o < sizeof r->label)
                o += (size_t)snprintf(r->label + o, sizeof r->label - o, "%s %g -> %g", k_bm_tune_catalog[d->tune[k].idx].name,
                                      shipped(d->tune[k].idx), d->tune[k].v);
            any = 1;
            first_sys = 0;
        }
        if (any) {
            if (o < sizeof r->label)
                o += (size_t)snprintf(r->label + o, sizeof r->label - o, ")");
            snprintf(page + strlen(page), sizeof page - strlen(page), "%s %s", strcmp(page, "CHANGES GAMEPLAY:") ? "," : "",
                     s == 2 ? "AI" : s ? "SCORING" : "BOOST");
        }
    }
    if (d->cap.present && d->cap.have) {
        int any = 0;
        if (o < sizeof r->label)
            o += (size_t)snprintf(r->label + o, sizeof r->label - o, "%scapacity (", first_sys ? " " : ", ");
        if ((d->cap.have & AD_CAP_LANES) && o < sizeof r->label) {
            o += (size_t)snprintf(r->label + o, sizeof r->label - o, "AI route lanes %u", (unsigned)d->cap.lanes);
            any = 1;
        }
        if ((d->cap.have & AD_CAP_LOW) && o < sizeof r->label) {
            o += (size_t)snprintf(r->label + o, sizeof r->label - o, "%slow-detail unit slot 0x%X bytes", any ? ", " : "",
                                  (unsigned)d->cap.low_unit_bytes);
            any = 1;
        }
        if ((d->cap.have & AD_CAP_STATIC) && o < sizeof r->label) {
            o += (size_t)snprintf(r->label + o, sizeof r->label - o, "%sSTATIC track pool 0x%X bytes", any ? ", " : "",
                                  (unsigned)d->cap.static_bytes);
            any = 1;
        }
        if ((d->cap.have & AD_CAP_FULL) && o < sizeof r->label)          /* patch 131 */
            o += (size_t)snprintf(r->label + o, sizeof r->label - o, "%sfull-detail unit slot 0x%X bytes", any ? ", " : "",
                                  (unsigned)d->cap.full_unit_bytes);
        if (o < sizeof r->label)
            o += (size_t)snprintf(r->label + o, sizeof r->label - o, ")");
        snprintf(page + strlen(page), sizeof page - strlen(page), "%s CAPACITY", strcmp(page, "CHANGES GAMEPLAY:") ? "," : "");
    }
    snprintf(r->page, sizeof r->page, "%s", page);
}

/* ---------------------------------------------------------------- GP-DEPS1: requires_mods (order, reasons, cycles) */
typedef int ad_edges[AD_REQS];             /* per mod: the index each requires_mods entry names, -1 none / not decided */

/* the one mod of m with this id; -1 none, or more than one (a shared id: modfs makes every copy unusable) */
static int find_id(const bo3_admit_mod *m, int n, const char *id)
{
    int at = -1;
    for (int j = 0; j < n; j++)
        if (m[j].id && !strcmp(m[j].id, id)) {
            if (at >= 0)
                return -1;
            at = j;
        }
    return at;
}

static void req_text(const bo3_modreq *q, char *out, size_t n)
{
    if (q->has_ver)
        snprintf(out, n, "%s >= %s", q->id, q->text);
    else
        snprintf(out, n, "%s", q->id);
}

/* a path a -> ... -> b of one edge or more */
static int reach(const ad_edges *e, int a, int b, unsigned char *seen)
{
    for (unsigned k = 0; k < AD_REQS; k++) {
        int t = e[a][k];
        if (t < 0 || seen[t])
            continue;
        if (t == b)
            return 1;
        seen[t] = 1;
        if (reach(e, t, b, seen))
            return 1;
    }
    return 0;
}

/* cyc[i] = 1 when mod i lies on a cycle of e */
static void find_cycles(const ad_edges *e, int n, unsigned char *cyc, unsigned char *seen)
{
    for (int i = 0; i < n; i++) {
        memset(seen, 0, (size_t)n);
#if DEPS_MUT != 4
        cyc[i] = (unsigned char)reach(e, i, i, seen);
#else
        (void)reach;
        (void)e;
        cyc[i] = 0;                                        /* defect: cycles are not found */
#endif
    }
}

/* "a -> b -> a": the shortest cycle through i (breadth first; ids from m) */
static void cycle_text(const ad_edges *e, int n, int i, const bo3_admit_mod *m, char *out, size_t on)
{
    int *par = (int *)malloc((size_t)n * sizeof *par), *qu = (int *)malloc((size_t)n * sizeof *qu), h = 0, t = 0, end = -1;
    out[0] = 0;
    if (!par || !qu) {
        free(par);
        free(qu);
        snprintf(out, on, "%s -> ... -> %s", m[i].id, m[i].id);
        return;
    }
    for (int j = 0; j < n; j++)
        par[j] = -2;
    for (unsigned k = 0; k < AD_REQS; k++)
        if (e[i][k] >= 0 && par[e[i][k]] == -2) {
            par[e[i][k]] = -1;
            qu[t++] = e[i][k];
        }
    while (h < t && end < 0) {
        int a = qu[h++];
        if (a == i) {
            end = a;
            break;
        }
        for (unsigned k = 0; k < AD_REQS; k++)
            if (e[a][k] >= 0 && par[e[a][k]] == -2) {
                par[e[a][k]] = a;
                qu[t++] = e[a][k];
            }
    }
    if (end < 0) {
        snprintf(out, on, "%s -> ... -> %s", m[i].id, m[i].id);
    } else {                                               /* walk back from i to the first step, then print forwards */
        int path[BO3_ADMIT_MAX * 4 + 1], np = 0;
        size_t o;
        for (int a = end; a >= 0 && np < (int)(sizeof path / sizeof path[0]); a = par[a])
            path[np++] = a;
        o = (size_t)snprintf(out, on, "%s", m[i].id);
        for (int j = np - 1; j >= 0 && o < on; j--)
            o += (size_t)snprintf(out + o, on - o, " -> %s", m[path[j]].id);
    }
    free(par);
    free(qu);
}

int bo3_admit_order(const bo3_admit_mod *m, int n, int *perm)
{
    ad_mod *d;
    ad_edges *e;
    unsigned char *placed, *cyc, *seen;
    int moved = 0;
    if (!perm || n < 0 || n > (int)BO3_ADMIT_MAX * 4)
        return -1;
    for (int j = 0; j < n; j++)
        perm[j] = j;
    if (!m)
        return -1;
    if (!n)
        return 0;
    d = (ad_mod *)calloc((size_t)n, sizeof *d);
    e = (ad_edges *)malloc((size_t)n * sizeof *e);
    placed = (unsigned char *)calloc((size_t)n, 1);
    cyc = (unsigned char *)calloc((size_t)n, 1);
    seen = (unsigned char *)calloc((size_t)n, 1);
    if (!d || !e || !placed || !cyc || !seen) {
        free(d);
        free(e);
        free(placed);
        free(cyc);
        free(seen);
        return -1;
    }
    for (int i = 0; i < n; i++) {
        read_reqs_only(&m[i], &d[i]);
        for (unsigned k = 0; k < AD_REQS; k++) {
            e[i][k] = k < d[i].nreq ? find_id(m, n, d[i].req[k].id) : -1;
            if (e[i][k] == i)
                e[i][k] = -1;
        }
    }
    find_cycles(e, n, cyc, seen);
#if DEPS_MUT != 5
    for (int j = 0; j < n; j++) {
        int pick = -1;
        for (int i = 0; i < n && pick < 0; i++) {          /* the earliest mod whose required mods are all placed */
            int ready = !placed[i];
            for (unsigned k = 0; ready && k < AD_REQS; k++)
                if (e[i][k] >= 0 && !placed[e[i][k]])
                    ready = 0;
            if (ready)
                pick = i;
        }
        for (int i = 0; i < n && pick < 0; i++)            /* only cycles are left: break the earliest one */
            if (!placed[i] && cyc[i])
                pick = i;
        for (int i = 0; i < n && pick < 0; i++)
            if (!placed[i])
                pick = i;
        placed[pick] = 1;
        perm[j] = pick;
    }
#endif
    for (int j = 0; j < n; j++)
        moved += perm[j] != j;
    free(d);
    free(e);
    free(placed);
    free(cyc);
    free(seen);
    return moved;
}

int bo3_admit_run(const bo3_admit_mod *m, int n, bo3_admit_res *r)
{
    return bo3_admit_run_deps(m, n, NULL, 0, r);
}

/* the static dependency reasons (before any clash is known): absent / off / unusable / older / incomparable / unreadable,
 * then the cycles; e receives the met edges */
static void deps_static(ad_ctx *c, const ad_mod *d, int n, const bo3_admit_known *kn, int nk, ad_edges *e, unsigned char *forced)
{
    const bo3_admit_mod *m = c->m;
    bo3_admit_res *r = c->r;
    for (int i = 0; i < n; i++)
        for (unsigned k = 0; k < AD_REQS; k++)
            e[i][k] = -1;
    for (int i = 0; i < n; i++) {
        if (d[i].req_bad[0]) {
            clash(c, i, BO3_AK_NEEDS_MOD, "requires_mods", -1, "%s", d[i].req_bad);
            snprintf(r[i].need, sizeof r[i].need, "requires_mods not readable");
            forced[i] = 1;
            continue;
        }
        for (uint32_t k = 0; k < d[i].nreq && !forced[i]; k++) {
            const bo3_modreq *q = &d[i].req[k];
            char rq[100];
            int t = find_id(m, n, q->id), met;
            req_text(q, rq, sizeof rq);
            if (t == i)
                continue;                                  /* (the gate refuses a mod that requires itself) */
            if (t >= 0) {
                met = bo3_modreq_met(q, m[t].version);
#if DEPS_MUT == 2
                met = 1;                                   /* defect: the required version is not compared */
#endif
                if (met > 0) {
                    e[i][k] = t;
                    continue;
                }
                if (met < 0) {
                    clash(c, i, BO3_AK_NEEDS_MOD, q->id, t, "requires_mods \"%s\": the installed version \"%s\" cannot be "
                          "compared with %s:", rq, m[t].version ? m[t].version : "", q->text);
                    snprintf(r[i].need, sizeof r[i].need, "needs %.60s: version not comparable", rq);
                } else {
                    clash(c, i, BO3_AK_NEEDS_MOD, q->id, t, "requires_mods \"%s\": the installed version %s is older:", rq,
                          m[t].version);
                    snprintf(r[i].need, sizeof r[i].need, "needs %.60s: has %.16s", rq, m[t].version);
                }
            } else {
                int kk = -1;
                for (int j = 0; j < nk && kk < 0; j++)
                    if (kn[j].id && !strcmp(kn[j].id, q->id))
                        kk = j;
                if (kk >= 0 && kn[kk].state && !strcmp(kn[kk].state, "switched off")) {
                    clash(c, i, BO3_AK_NEEDS_MOD, q->id, -1, "requires_mods \"%s\": installed but switched off: mod %s %s (%s)",
                          rq, kn[kk].id, kn[kk].version && *kn[kk].version ? kn[kk].version : "-",
                          kn[kk].folder ? kn[kk].folder : "?");
                    snprintf(r[i].need, sizeof r[i].need, "needs %.60s: switched off", rq);
                } else if (kk >= 0) {
                    clash(c, i, BO3_AK_NEEDS_MOD, q->id, -1, "requires_mods \"%s\": installed but not usable (%.160s): mod %s "
                          "%s (%s)", rq, kn[kk].state ? kn[kk].state : "?", kn[kk].id,
                          kn[kk].version && *kn[kk].version ? kn[kk].version : "-", kn[kk].folder ? kn[kk].folder : "?");
                    snprintf(r[i].need, sizeof r[i].need, "needs %.60s: not usable", rq);
                } else {
                    clash(c, i, BO3_AK_NEEDS_MOD, q->id, -1, "requires_mods \"%s\": not installed", rq);
                    snprintf(r[i].need, sizeof r[i].need, "needs %.60s: not installed", rq);
                }
            }
            forced[i] = 1;
        }
    }
    {
        unsigned char cyc[BO3_ADMIT_MAX], seen[BO3_ADMIT_MAX];
        find_cycles(e, n, cyc, seen);
        for (int i = 0; i < n; i++) {
            char path[300];
            if (!cyc[i] || forced[i])
                continue;
            cycle_text(e, n, i, m, path, sizeof path);
            clash(c, i, BO3_AK_MOD_CYCLE, m[i].id ? m[i].id : "?", -1, "the mods' requires_mods form a cycle: %s", path);
            snprintf(r[i].need, sizeof r[i].need, "dependency cycle: %.70s", path);
            forced[i] = 1;
        }
    }
    for (int i = 0; i < n; i++)
        if (forced[i])
            r[i].refused = 1;
}

int bo3_admit_run_deps(const bo3_admit_mod *m, int n, const bo3_admit_known *kn, int nk, bo3_admit_res *r)
{
    ad_mod *d;
    static ad_reg g;                       /* GP-P4.3 M4: off the stack (fx_reg grew with the p4.3 texture limits); the mod
                                            * list is admitted on one thread, one call at a time; every use memsets it */
    ad_ctx c = {m, r};
    unsigned char forced[BO3_ADMIT_MAX], sforced[BO3_ADMIT_MAX];
    ad_edges *e;
    int nref = 0;
    if (!m || !r || n < 0 || n > (int)BO3_ADMIT_MAX || nk < 0 || (nk && !kn))
        return -1;
    d = (ad_mod *)calloc((size_t)(n ? n : 1), sizeof *d);
    e = (ad_edges *)malloc((size_t)(n ? n : 1) * sizeof *e);
    if (!d || !e) {
        free(d);
        free(e);
        return -1;
    }
    memset(&g, 0, sizeof g);
    memset(forced, 0, sizeof forced);
    for (int i = 0; i < n; i++)
        read_mod(&m[i], &d[i]);
    for (int i = 0; i < n; i++) {
        memset(&r[i], 0, sizeof r[i]);
        r[i].other = -1;
    }
    deps_static(&c, d, n, kn, nk, e, forced);              /* GP-DEPS1: these mods take no part in the clashes */
    memcpy(sforced, forced, sizeof sforced);
    (void)sforced;
    for (int pass = 0; pass <= n; pass++) {             /* refusals only grow: at most n passes */
        int more = 0;
        free(g.tr);
        memset(&g, 0, sizeof g);
        for (int t = 0; t < (int)AD_TUNE; t++)
            g.tune_owner[t] = -1;
        g.last_tracks = -1;
        g.last_music = -1;                                 /* GP-MUSIC1 */
        for (int i = 0; i < n; i++) {
            if (forced[i]) {
#if DEPS_MUT == 7
                if (sforced[i]) {                          /* defect: a mod refused for a dependency still holds its keys */
                    bo3_admit_res keep = r[i];
                    if (check_one(&c, &g, &d[i], i) < 0) {
                        free(g.tr);
                        free(d);
                        free(e);
                        return -1;
                    }
                    r[i] = keep;
                }
#endif
                continue;                                  /* r[i] already says why (a dependency, below) */
            }
            memset(&r[i], 0, sizeof r[i]);
            r[i].other = -1;
            {
                int k = check_one(&c, &g, &d[i], i);
                if (k < 0) {
                    free(g.tr);
                    free(d);
                    free(e);
                    return -1;
                }
#if ADMIT_MUT == 2
                if (!k) {                                  /* defect: the clash refuses nobody, says nothing */
                    memset(&r[i], 0, sizeof r[i]);
                    r[i].other = -1;
                    k = 1;
                }
#endif
                r[i].refused = !k;
            }
        }
#if ADMIT_MUT != 7
        /* dependencies: an admitted mod that needs content only refused mods declare is refused too */
        for (int i = 0; i < n; i++) {
            if (r[i].refused || forced[i])
                continue;
            for (uint32_t k = 0; k < d[i].nev && !forced[i]; k++) {
                int have = 0, by = -1;
                for (int o = 0; o < n && !have; o++)
                    if (track_index(&d[o], d[i].ev[k].track) >= 0) {
                        if (!r[o].refused && !forced[o])
                            have = 1;
                        else if (by < 0)
                            by = o;
                    }
                if (!have && by >= 0) {
                    char key[80];
                    snprintf(key, sizeof key, "%.40s/%.32s", m[i].id ? m[i].id : "?", d[i].ev[k].local);
                    memset(&r[i], 0, sizeof r[i]);
                    r[i].other = -1;
                    clash(&c, i, BO3_AK_NEEDS_TRACK, key, by, "is on track %s, which only a refused mod adds:", d[i].ev[k].track);
                    forced[i] = 1;
                    r[i].refused = 1;
                    more = 1;
                }
            }
            for (uint32_t k = 0; k < d[i].ntr && !forced[i]; k++) {
                int have = 0, by = -1;
                if (retail_region(d[i].tr[k]))
                    continue;
                for (int o = 0; o < n && !have; o++)
                    for (uint32_t q = 0; q < d[o].nreg; q++)
                        if (d[o].reg[q].letter == d[i].tr[k][0]) {
                            if (!r[o].refused && !forced[o])
                                have = 1;
                            else if (by < 0)
                                by = o;
                        }
                if (!have && by >= 0) {
                    memset(&r[i], 0, sizeof r[i]);
                    r[i].other = -1;
                    clash(&c, i, BO3_AK_NEEDS_REGION, d[i].tr[k], by, "is in region letter %c, which only a refused mod "
                          "declares:", d[i].tr[k][0]);
                    forced[i] = 1;
                    r[i].refused = 1;
                    more = 1;
                }
            }
        }
#else
        (void)retail_region;                       /* (MUT 7: the dependencies are not followed) */
#endif
#if DEPS_MUT != 3
        /* GP-DEPS1: a mod whose required mod is refused (a clash, or its own dependency) is refused too */
        for (int i = 0; i < n; i++) {
            if (r[i].refused || forced[i])
                continue;
            for (unsigned k = 0; k < AD_REQS && !forced[i]; k++) {
                int t = e[i][k];
                char rq[100];
                if (t < 0 || !(r[t].refused || forced[t]))
                    continue;
                req_text(&d[i].req[k], rq, sizeof rq);
                memset(&r[i], 0, sizeof r[i]);
                r[i].other = -1;
                clash(&c, i, BO3_AK_NEEDS_MOD, d[i].req[k].id, t, "requires_mods \"%s\": that mod is refused (%s %s):", rq,
                      bo3_admit_kind_name(r[t].kind), r[t].key);
                snprintf(r[i].need, sizeof r[i].need, "needs %.60s: refused", rq);
                forced[i] = 1;
                r[i].refused = 1;
                more = 1;
            }
        }
#endif
        if (!more)
            break;
    }
    for (int i = 0; i < n; i++) {
        if (forced[i])
            r[i].refused = 1;
#if ADMIT_MUT == 1
        if (r[i].refused && r[i].other >= 0 && r[i].kind != BO3_AK_NEEDS_TRACK && r[i].kind != BO3_AK_NEEDS_REGION &&
            r[i].kind != BO3_AK_NEEDS_MOD && r[i].kind != BO3_AK_MOD_CYCLE) {
            int o = r[i].other;                            /* defect: the EARLIER mod is refused instead */
            r[o] = r[i];
            r[o].other = i;
            memset(&r[i], 0, sizeof r[i]);
            r[i].other = -1;
        }
#endif
    }
    for (int i = 0; i < n; i++) {
        r[i].tables = d[i].tables;
        r[i].undecided = d[i].bad;
#if ADMIT_MUT == 4
        if (r[i].refused && r[i].kind != BO3_AK_NEEDS_TRACK && r[i].kind != BO3_AK_NEEDS_REGION &&
            r[i].kind != BO3_AK_NEEDS_MOD && r[i].kind != BO3_AK_MOD_CYCLE) {
            r[i].refused = 0;                              /* defect: only the clashing table would be dropped */
            r[i].why[0] = 0;
        }
#endif
        if (!r[i].refused)
            make_label(&d[i], &r[i]);
        nref += r[i].refused;
    }
    free(g.tr);
    free(d);
    free(e);
    return nref;
}

/* ---------------------------------------------------------------- the game: modfs's list_mods calls admit_cb */
#ifdef BO3_ADMIT_GAME
#include "bm_platform_table.h"
#include "modfs.h"

_Static_assert(BO3_ADMIT_MAX == BO3_MODFS_MAX_MODS, "main18: the admission takes every mod the mod list can hold");

/* GP-DEPS1: the dependency order, applied to modfs's own array before anything else reads it (the [MOD] lines, the sources,
 * the services and plugins all follow it). Only usable mods' mod.toml files are read (one read each). */
static void order_cb(bo3_mod *mods, int n)
{
    bo3_admit_mod all[BO3_MODFS_MAX_MODS];
    char *txt[BO3_MODFS_MAX_MODS];
    int perm[BO3_MODFS_MAX_MODS], moved, declared = 0;
    bo3_mod *copy;
    if (n <= 1 || n > BO3_MODFS_MAX_MODS)
        return;
    for (int i = 0; i < n; i++) {
        char path[BO3_MODFS_PATH_MAX + 16];
        size_t len = 0;
        txt[i] = NULL;
        if (mods[i].usable && (!bo3_modfs_mod_file(&mods[i], "mod.toml", path, sizeof path) ||
                               bo3_modfs_read_whole(path, &txt[i], &len) != 1)) {
            free(txt[i]);
            txt[i] = NULL;
            len = 0;
        }
        all[i].id = mods[i].manifest.id[0] ? mods[i].manifest.id : NULL;
        all[i].version = mods[i].manifest.version;
        all[i].folder = mods[i].folder;
        all[i].text = txt[i];
        all[i].n = len;
        declared += txt[i] && strstr(txt[i], "requires_mods") != NULL;
    }
    moved = declared ? bo3_admit_order(all, n, perm) : 0;
    if (moved > 0 && (copy = (bo3_mod *)malloc((size_t)n * sizeof *copy)) != NULL) {
        memcpy(copy, mods, (size_t)n * sizeof *copy);
        for (int j = 0; j < n; j++)
            mods[j] = copy[perm[j]];
        free(copy);
        fprintf(stderr, "[DEPS] the mod list in dependency order (%d mod%s placed after the mods they require):", moved,
                moved == 1 ? "" : "s");
        for (int j = 0; j < n; j++)
            fprintf(stderr, "%s %s", j ? "," : "", mods[j].manifest.id[0] ? mods[j].manifest.id : "(no id)");
        fprintf(stderr, "\n");
    } else if (moved < 0) {
        fprintf(stderr, "[DEPS] the dependency order was not made (out of host memory): the mod list keeps its order\n");
    }
    for (int i = 0; i < n; i++)
        free(txt[i]);
}

static void admit_cb(bo3_mod *mods, int n)
{
    bo3_admit_mod in[BO3_ADMIT_MAX];
    bo3_admit_known kn[BO3_MODFS_MAX_MODS];
    int map[BO3_ADMIT_MAX], k = 0, nk = 0, nref, any = 0, nlab = 0;
    char *txt[BO3_ADMIT_MAX];
    bo3_admit_res *res;
    order_cb(mods, n);                                 /* GP-DEPS1 */
    for (int i = 0; i < n && k < (int)BO3_ADMIT_MAX; i++) {
        char path[BO3_MODFS_PATH_MAX + 16];
        size_t len = 0;
        if (!mods[i].usable || !mods[i].enabled) {
            if (nk < BO3_MODFS_MAX_MODS && mods[i].manifest.id[0]) {   /* GP-DEPS1: named in a dependant's reason */
                kn[nk].id = mods[i].manifest.id;
                kn[nk].version = mods[i].manifest.version;
                kn[nk].folder = mods[i].folder;
                kn[nk++].state = mods[i].usable ? "switched off" : mods[i].problem;
            }
            continue;
        }
        txt[k] = NULL;
        if (!bo3_modfs_mod_file(&mods[i], "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &txt[k], &len) != 1) {
            free(txt[k]);
            txt[k] = NULL;
            len = 0;
        }
        in[k].id = mods[i].manifest.id;
        in[k].version = mods[i].manifest.version;
        in[k].folder = mods[i].folder;
        in[k].text = txt[k];
        in[k].n = len;
        map[k++] = i;
    }
    if (!k)
        return;
    res = (bo3_admit_res *)calloc((size_t)k, sizeof *res);
    nref = res ? bo3_admit_run_deps(in, k, kn, nk, res) : -1;
    if (nref < 0) {
        fprintf(stderr, "[ADMIT] the mods' [bmashup.*] declarations were not checked together (out of host memory): each "
                "service checks them alone, a clash between two mods stops the start (exit 92 / 93)\n");
    } else {
        for (int j = 0; j < k; j++)
            any |= res[j].tables != 0;
        for (int j = 0; j < k; j++) {
            bo3_mod *m = &mods[map[j]];
            if (!res[j].refused)
                continue;
            m->usable = 0;
            m->conflict = 1;
            if (res[j].kind == BO3_AK_NEEDS_MOD || res[j].kind == BO3_AK_MOD_CYCLE) {   /* GP-DEPS1 */
                m->needs = 1;
                snprintf(m->problem, sizeof m->problem, "%s", res[j].need);
            } else if (res[j].other >= 0) {
                snprintf(m->problem, sizeof m->problem, "conflict with %.60s: %.24s %.60s", in[res[j].other].id,
                         bo3_admit_kind_name(res[j].kind), res[j].key);
            } else {
                snprintf(m->problem, sizeof m->problem, "conflict: %.24s %.100s", bo3_admit_kind_name(res[j].kind), res[j].key);
            }
            fprintf(stderr, "[ADMIT] mod %s%s%s (%s) refused, the game starts without it: %s\n", m->manifest.id,
                    m->manifest.version[0] ? " " : "", m->manifest.version, m->folder, res[j].why);
        }
        if (any)
            fprintf(stderr, "[ADMIT] %d mod%s' [bmashup.*] declarations checked together before any is used (platform %s): "
                    "%d admitted, %d refused\n", k, k == 1 ? "" : "s", BO3_PLATFORM_VERSION, k - nref, nref);
        for (int j = 0; j < k; j++) {
            bo3_mod *m = &mods[map[j]];
            if (res[j].refused || !res[j].gameplay)
                continue;
            nlab++;
            snprintf(m->gameplay, sizeof m->gameplay, "%s", res[j].page);
            fprintf(stderr, "[MODS] %s%s%s %s\n", m->manifest.id, m->manifest.version[0] ? " " : "", m->manifest.version,
                    res[j].label);
        }
        if (nlab)
            fprintf(stderr, "[MODS] %d data mod%s change%s gameplay values (informational: no approval is asked; native code "
                    "approval is separate, per sha256)\n", nlab, nlab == 1 ? "" : "s", nlab == 1 ? "s" : "");
    }
    for (int j = 0; j < k; j++)
        free(txt[j]);
    free(res);
    fflush(stderr);
}

void bo3_admit_game_install(void)
{
    bo3_modfs_set_admit(admit_cb);
}
#endif
