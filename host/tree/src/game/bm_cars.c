/* bm_cars.c - GP-CARS2 + GP-VEH1 EXPERIMENTAL: cars added by data mods (bm_cars.h). MUT=n (test builds only) compiles one
 * deliberate defect:
 *   1 the class-row bound (20) not checked          2 the hidden 10th-entry slot not refused (cars2; now logged only)
 *   3 flag A of the added entry left 0             4 the donor's value D not copied (0)
 *   5 the physics alias returns the added ID        6 a scale applied to every block (the last added car's scales)
 *   7 the photo fallback for any missed name        8 the index map also changes a valid (>= 0) index
 *   9 (bm_names.c) the other kind's text            10 a scale out of bounds accepted
 *   11 the image capacity not checked               12 the model size bound not checked
 *   13 (veh1) a refused append leaves the earlier cars of the mod registered (no rollback)
 *   14 (veh1) the registry hash ignores the high word (finds the wrong car)
 *   15 (veh1) model = donor: the files are still required
 *   16 (veh1) the series rows counted by the retail class only (a series' 21st car accepted) */
#include "bm_cars.h"
#include "bm_veh.h"

#include <ctype.h>
#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_names.h"
#include "bm_vphys_catalog.h"
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0
#endif

#define CAR_PREFIX "bmashup.cars"
_Static_assert(BO3_NM_CARS_MAX >= BO3_CAR_MAX_DECL, "every declared car may carry texts");

static const char *const k_class[7] = {"COMP", "MSCL", "CUPE", "SPRT", "SUPR", "HSPC", "HEVY"};
static const char k_al[] = " -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_";

typedef struct car_reg {
    bo3_car_entry e;
    int donor_sidx;
    int mod;
} car_reg;
static car_reg s_cars[BO3_VEH_CAP];
static uint32_t s_ncars;
#define HASH_N 2048u                                 /* > 2 x BO3_VEH_CAP: open addressing, k + 1 (0 = empty) */
static uint16_t s_hash[HASH_N];
static _Atomic uint32_t s_stat[8];
static uint8_t s_logged[BO3_VEH_CAP];

int bo3_car_enc(const char *s, uint64_t *out)
{
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

void bo3_car_dec(uint64_t v, char out[13])
{
    for (int i = 11; i >= 0; i--) {
        out[i] = k_al[v % 40u];
        v /= 40u;
    }
    out[12] = 0;
    for (int i = 11; i >= 0 && out[i] == ' '; i--)
        out[i] = 0;
}
#define enc bo3_car_enc
#define dec bo3_car_dec

int bo3_car_class_of(const char *id)
{
    for (int c = 0; c < 7; c++)
        if (!strncmp(id, k_class[c], 4))
            return c;
    return -1;
}

static int retail_literal(const char *p)            /* the 9 literals of sub_00157300 */
{
    return bo3_car_class_of(p) >= 0 || !strncmp(p, "TRAF", 4) || !strncmp(p, "TSPC", 4);
}

static int alnum_upper(const char *s)
{
    for (; *s; s++)
        if (!((*s >= 'A' && *s <= 'Z') || (*s >= '0' && *s <= '9')))
            return 0;
    return 1;
}

static int name_char_ok(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '-' ||
           c == '\'' || c == '.' || c == '&';
}

static void trim(char *s)
{
    char *a = s, *e;
    while (*a == ' ')
        a++;
    memmove(s, a, strlen(a) + 1);
    for (e = s + strlen(s); e > s && e[-1] == ' ';)
        *--e = 0;
}

/* "A = B" -> a, b (trimmed); 0 when malformed */
static int split(const char *s, char sep, char *a, size_t an, char *b, size_t bn)
{
    const char *p = s ? strchr(s, sep) : NULL;
    if (!p || (size_t)(p - s) >= an || strlen(p + 1) >= bn)
        return 0;
    memcpy(a, s, (size_t)(p - s));
    a[p - s] = 0;
    strcpy(b, p + 1);
    trim(a);
    trim(b);
    return *a && *b;
}

static const char *arr_str(recomp_cfg *cfg, const char *key, size_t i)
{
    return recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
}

static int find_decl(const bo3_car_decl *d, uint64_t id)
{
    for (uint32_t i = 0; i < d->n; i++)
        if (d->e[i].id == id)
            return (int)i;
    return -1;
}

/* the catalog's writable value whose short name (after "| ") is v */
static const bm_vphys_entry *scale_entry(const char *v)
{
    for (size_t i = 0; i < sizeof k_bm_vphys_catalog / sizeof k_bm_vphys_catalog[0]; i++) {
        const char *p = strstr(k_bm_vphys_catalog[i].full, "| ");
        if (k_bm_vphys_catalog[i].writable && p && !strcmp(p + 2, v))
            return &k_bm_vphys_catalog[i];
    }
    return NULL;
}

void bo3_car_decl_free(bo3_car_decl *d)
{
    if (!d)
        return;
    free(d->e);
    memset(d, 0, sizeof *d);
}

/* a list key: RCFG_NONE -> 0 entries ok; not an array -> -1 */
static long list_len(recomp_cfg *cfg, const char *key)
{
    int t = recomp_cfg_type_of(cfg, key);
    if (t == RCFG_NONE)
        return 0;
    if (t != RCFG_ARRAY)
        return -1;
    return (long)recomp_cfg_array_len(cfg, key);
}

int bo3_car_parse(const char *text, size_t n, bo3_car_decl *out, char *why, size_t wn)
{
    char err[200];
    size_t plen = strlen(CAR_PREFIX);
    recomp_cfg *cfg;
    char *buf;
    int ok = 1, ver = 0;

    memset(out, 0, sizeof *out);
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
    if (recomp_cfg_type_of(cfg, CAR_PREFIX ".version") == RCFG_INT)
        ver = (int)recomp_cfg_int(cfg, CAR_PREFIX ".version", 0);
    for (size_t i = 0; ok && i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i);
        int v1key, v2key;
        if (strncmp(k, CAR_PREFIX, plen) != 0 || (k[plen] != 0 && k[plen] != '.'))
            continue;
        out->present = 1;
        v1key = k[plen] && (!strcmp(k, CAR_PREFIX ".version") || !strcmp(k, CAR_PREFIX ".add") ||
                            !strcmp(k, CAR_PREFIX ".names") || !strcmp(k, CAR_PREFIX ".physics_scale") ||
                            !strcmp(k, CAR_PREFIX ".photos"));     /* fetex1 INTERFACE s2: the garage photo binding */
        v2key = k[plen] && (!strcmp(k, CAR_PREFIX ".model") || !strcmp(k, CAR_PREFIX ".unlock") || !strcmp(k, CAR_PREFIX ".ai"));
        if (!v1key && !(v2key && ver == 2)) {
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 1: version, add, names, physics_scale, photos; "
                     "version 2 also model, unlock, ai)", k, CAR_PREFIX);
            ok = 0;
        }
    }
    if (ok && out->present) {
        if (ver != 1 && ver != 2) {
            snprintf(why, wn, "%s.version must be 1 or 2 (the versions this build reads)", CAR_PREFIX);
            ok = 0;
        } else if (recomp_cfg_type_of(cfg, CAR_PREFIX ".add") != RCFG_ARRAY || !recomp_cfg_array_len(cfg, CAR_PREFIX ".add")) {
            snprintf(why, wn, "%s.add must be a list of \"NEW ID = DONOR ID\"", CAR_PREFIX);
            ok = 0;
        }
    }
    out->version = ver;
    if (ok && out->present) {
        size_t na = recomp_cfg_array_len(cfg, CAR_PREFIX ".add");
        if (na > BO3_CAR_MAX_DECL) {
            snprintf(why, wn, "%s.add lists %u cars; the vehicle registry takes at most %u added cars (capacity %u, %u retail)",
                     CAR_PREFIX, (unsigned)na, (unsigned)BO3_CAR_MAX_DECL, (unsigned)BO3_VEH_CAP, (unsigned)BO3_CAR_RETAIL_N);
            ok = 0;
        } else {
            out->e = (bo3_car_entry *)calloc(na, sizeof *out->e);
            out->cap = (uint32_t)na;
            if (!out->e) {
                snprintf(why, wn, "no memory");
                ok = 0;
            }
        }
        for (size_t i = 0; ok && i < na; i++) {
            char a[64], b[64];
            bo3_car_entry *e = &out->e[i];
            int pre_retail;
            if (!split(arr_str(cfg, CAR_PREFIX ".add", i), '=', a, sizeof a, b, sizeof b)) {
                snprintf(why, wn, "%s.add[%u] is not \"NEW ID = DONOR ID\"", CAR_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            pre_retail = strlen(a) >= 4 && bo3_car_class_of(a) >= 0;
            if (strlen(a) < 5 || strlen(a) > 12 || !alnum_upper(a) || !enc(a, &e->id) ||
                (!pre_retail && (ver < 2 || retail_literal(a)))) {
                snprintf(why, wn, "%s.add: \"%s\" is not a new car ID (a class COMP MSCL CUPE SPRT SUPR HSPC HEVY%s + 1 .. 8 of "
                         "A-Z 0-9)", CAR_PREFIX, a, ver == 2 ? " or a [bmashup.series] prefix" : "");
                ok = 0;
            } else if (strlen(b) < 5 || bo3_car_class_of(b) < 0 || !alnum_upper(b) || !enc(b, &e->donor)) {
                snprintf(why, wn, "%s.add: donor \"%s\" is not a car ID", CAR_PREFIX, b);
                ok = 0;
            } else if (pre_retail && strncmp(a, b, 4)) {
                snprintf(why, wn, "%s.add: %s and its donor %s are of different classes (the car joins its donor's series)",
                         CAR_PREFIX, a, b);
                ok = 0;
            } else if (e->id == e->donor || find_decl(out, e->id) >= 0) {
                snprintf(why, wn, "%s.add lists %s twice (or as its own donor)", CAR_PREFIX, a);
                ok = 0;
            } else {
                e->series_prefix = (uint8_t)!pre_retail;
                out->n = (uint32_t)(i + 1);
            }
        }
    }
    if (ok && out->present) {
        long nn = list_len(cfg, CAR_PREFIX ".names");
        if (nn < 0) {
            snprintf(why, wn, "%s.names must be a list of \"ID = name\"", CAR_PREFIX);
            ok = 0;
        }
        for (long i = 0; ok && i < nn; i++) {
            char a[64], b[64];
            uint64_t id = 0;
            int k;
            size_t len;
            if (!split(arr_str(cfg, CAR_PREFIX ".names", (size_t)i), '=', a, sizeof a, b, sizeof b) || !enc(a, &id) ||
                (k = find_decl(out, id)) < 0) {
                snprintf(why, wn, "%s.names[%u] is not \"ID = name\" for a car of this mod's add list", CAR_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            len = strlen(b);
            if (len > BO3_CAR_NAME_MAX) {
                snprintf(why, wn, "%s.names: the name of %s has %u characters; 1 .. %u fit the garage", CAR_PREFIX, a,
                         (unsigned)len, (unsigned)BO3_CAR_NAME_MAX);
                ok = 0;
                break;
            }
            for (size_t c = 0; c < len; c++)
                if (!name_char_ok(b[c])) {
                    snprintf(why, wn, "%s.names: the name of %s has the character '%c'; use A-Z a-z 0-9, space and - ' . &",
                             CAR_PREFIX, a, b[c]);
                    ok = 0;
                    break;
                }
            if (ok && out->e[k].name[0]) {
                snprintf(why, wn, "%s.names gives %s a second name", CAR_PREFIX, a);
                ok = 0;
            }
            if (ok)
                memcpy(out->e[k].name, b, len + 1);
        }
    }
    if (ok && out->present) {
        long ns = list_len(cfg, CAR_PREFIX ".physics_scale");
        if (ns < 0) {
            snprintf(why, wn, "%s.physics_scale must be a list of \"ID | value = scale\"", CAR_PREFIX);
            ok = 0;
        }
        for (long i = 0; ok && i < ns; i++) {
            char lhs[96], rhs[48], a[64], v[64], *end = NULL;
            uint64_t id = 0;
            int k;
            double s;
            const bm_vphys_entry *ce;
            bo3_car_entry *e;
            if (!split(arr_str(cfg, CAR_PREFIX ".physics_scale", (size_t)i), '=', lhs, sizeof lhs, rhs, sizeof rhs) ||
                !split(lhs, '|', a, sizeof a, v, sizeof v) || !enc(a, &id) || (k = find_decl(out, id)) < 0) {
                snprintf(why, wn, "%s.physics_scale[%u] is not \"ID | value = scale\" for a car of this mod's add list",
                         CAR_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            if (!(ce = scale_entry(v))) {
                snprintf(why, wn, "%s.physics_scale: \"%s\" is not a value this build scales (Drag Coef, Max Speed In Boost = the top-speed limit)",
                         CAR_PREFIX, v);
                ok = 0;
                break;
            }
            s = strtod(rhs, &end);
#if MUT == 10
            if (!end || *end || !isfinite(s)) {             /* defect: the bounds not checked */
#else
            if (!end || *end || !isfinite(s) || s < ce->smin || s > ce->smax) {
#endif
                snprintf(why, wn, "%s.physics_scale: %s %s = \"%s\" is not a scale in %.2f .. %.2f", CAR_PREFIX, a, v, rhs,
                         ce->smin, ce->smax);
                ok = 0;
                break;
            }
            e = &out->e[k];
            for (uint32_t j = 0; j < e->nscale; j++)
                if (e->scale[j].block_off == ce->block_off) {
                    snprintf(why, wn, "%s.physics_scale scales %s %s twice", CAR_PREFIX, a, v);
                    ok = 0;
                }
            if (ok && e->nscale < BO3_CAR_SCALES) {
                e->scale[e->nscale].block_off = ce->block_off;
                e->scale[e->nscale].scale = (float)s;
                e->nscale++;
            }
        }
    }
    if (ok && out->present) {                         /* fetex1 s2: photos = ["ID = <texture>"] - checked here, bound by fetex */
        long np = list_len(cfg, CAR_PREFIX ".photos");
        if (np < 0) {
            snprintf(why, wn, "%s.photos must be a list of \"ID = <texture>\"", CAR_PREFIX);
            ok = 0;
        }
        for (long i = 0; ok && i < np; i++) {
            char a[64], b[112];
            uint64_t id = 0;
            int k;
            if (!split(arr_str(cfg, CAR_PREFIX ".photos", (size_t)i), '=', a, sizeof a, b, sizeof b) || !enc(a, &id) ||
                (k = find_decl(out, id)) < 0 || out->e[k].photo) {
                snprintf(why, wn, "%s.photos[%u] is not \"ID = <texture>\" for a car of this mod's add list (once per car)",
                         CAR_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            out->e[k].photo = 1;
        }
    }
    if (ok && out->present && ver == 2) {             /* veh1: model / unlock / ai */
        long nm = list_len(cfg, CAR_PREFIX ".model"), nu = list_len(cfg, CAR_PREFIX ".unlock"), nai = list_len(cfg, CAR_PREFIX ".ai");
        if (nm < 0 || nu < 0 || nai < 0) {
            snprintf(why, wn, "%s.model / unlock / ai must be lists", CAR_PREFIX);
            ok = 0;
        }
        for (long i = 0; ok && i < nm; i++) {
            char a[64], b[64];
            uint64_t id = 0;
            int k;
            if (!split(arr_str(cfg, CAR_PREFIX ".model", (size_t)i), '=', a, sizeof a, b, sizeof b) || !enc(a, &id) ||
                (k = find_decl(out, id)) < 0 || strcmp(b, "donor")) {
                snprintf(why, wn, "%s.model[%u] is not \"ID = donor\" for a car of this mod's add list (the only model source "
                         "of version 2 besides the car's own files)", CAR_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            out->e[k].model_donor = 1;
        }
        for (long i = 0; ok && i < nu; i++) {
            char a[64], b[64];
            uint64_t id = 0;
            int k;
            if (!split(arr_str(cfg, CAR_PREFIX ".unlock", (size_t)i), '=', a, sizeof a, b, sizeof b) || !enc(a, &id) ||
                (k = find_decl(out, id)) < 0 || !bo3_veh_rule_parse(b, &out->e[k].rule) || out->e[k].has_rule) {
                snprintf(why, wn, "%s.unlock[%u] is not \"ID = open | cars:N | car:<RETAIL ID> | series:<CLASS>\" for a car of "
                         "this mod's add list (once per car)", CAR_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            out->e[k].has_rule = 1;
        }
        for (long i = 0; ok && i < nai; i++) {
            const char *s = arr_str(cfg, CAR_PREFIX ".ai", (size_t)i);
            char a[64];
            uint64_t id = 0;
            int k;
            if (!s || strlen(s) >= sizeof a) {
                ok = 0;
            } else {
                strcpy(a, s);
                trim(a);
                ok = enc(a, &id) && (k = find_decl(out, id)) >= 0 && !out->e[k].ai;
                if (ok)
                    out->e[k].ai = 1;
            }
            if (!ok)
                snprintf(why, wn, "%s.ai[%u] is not an ID of this mod's add list (once per car)", CAR_PREFIX, (unsigned)i);
        }
    }
    recomp_cfg_free(cfg);
    if (!ok)
        bo3_car_decl_free(out);
    return ok;
}

static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void wr32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint64_t rd64(const uint8_t *p) { return (uint64_t)rd32(p) | (uint64_t)rd32(p + 4) << 32; }

static int vl_find(const uint8_t *t, uint32_t cap, uint32_t count, uint64_t id)
{
    for (uint32_t i = 0; i < count && i < cap; i++)
        if (rd64(t + BO3_VL_OFF_ID(cap) + 8u * i) == id)
            return (int)i;
    return -1;
}

/* ---- the registry hash ---- */
static uint32_t hslot(uint64_t id)
{
#if MUT == 14
    uint64_t h = (uint64_t)(uint32_t)id * 0x9E3779B97F4A7C15ull;   /* defect: the high word ignored */
#else
    uint64_t h = id * 0x9E3779B97F4A7C15ull;
#endif
    return (uint32_t)(h >> 40) & (HASH_N - 1u);
}

static void hash_put(uint64_t id, uint32_t k)
{
    uint32_t s = hslot(id);
    while (s_hash[s])
        s = (s + 1u) & (HASH_N - 1u);
    s_hash[s] = (uint16_t)(k + 1u);
}

int bo3_car_find(uint64_t id)
{
    uint32_t s;
    if (!s_ncars)
        return -1;
    s = hslot(id);
    while (s_hash[s]) {
        uint32_t k = s_hash[s] - 1u;
#if MUT == 14
        if ((uint32_t)s_cars[k].e.id == (uint32_t)id)
#else
        if (s_cars[k].e.id == id)
#endif
            return (int)k;
        s = (s + 1u) & (HASH_N - 1u);
    }
    return -1;
}

/* the garage class of an ID in an image (retail literal or an active series; anything else 9) */
static uint32_t img_class(uint64_t id)
{
    return bo3_veh_class_of(id);
}

int bo3_car_append(uint8_t *vlist, uint32_t cap, const uint8_t *static_ids, const bo3_car_decl *d, int mod,
                   bo3_car_files_fn files, void *user, char *why, size_t wn)
{
    uint8_t *t;
    int *sidx;
    uint32_t count, reg0 = s_ncars;
    if (!d->present || !d->n)
        return 1;
    if (cap < BO3_CAR_CAP || cap > BO3_VEH_CAP) {
        snprintf(why, wn, "image capacity %u is not 128 .. %u", (unsigned)cap, (unsigned)BO3_VEH_CAP);
        return 0;
    }
    t = (uint8_t *)malloc(BO3_VL_SIZE(cap));
    sidx = (int *)malloc(sizeof(int) * d->n);
    if (!t || !sidx) {
        free(t);
        free(sidx);
        snprintf(why, wn, "no memory");
        return 0;
    }
    memcpy(t, vlist, BO3_VL_SIZE(cap));
    count = rd32(t + 4);
#define FAIL_ do { free(t); free(sidx); return 0; } while (0)
    if (count > cap) {
        snprintf(why, wn, "the vehicle list holds %u entries (capacity %u)", (unsigned)count, (unsigned)cap);
        FAIL_;
    }
    for (uint32_t k = 0; k < d->n; k++) {
        const bo3_car_entry *e = &d->e[k];
        char ids[13], dons[13], rel[64];
        static const char *const ext[3] = {"bgv", "hwd", "lwd"};
        int di, listed = 0, entries = 0;
        uint32_t cls;
        dec(e->id, ids);
        dec(e->donor, dons);
        cls = img_class(e->id);
        if (cls == 9u || (e->series_prefix && cls < BO3_VEH_SERIES_CODE0)) {
            snprintf(why, wn, "%s: its prefix %.4s is not a retail class nor an active [bmashup.series] prefix", ids, ids);
            FAIL_;
        }
        if (vl_find(t, cap, count, e->id) >= 0 || bo3_car_find(e->id) >= 0) {
            snprintf(why, wn, "%s: the game or another mod already has this vehicle ID", ids);
            FAIL_;
        }
        di = vl_find(t, cap, count, e->donor);
        sidx[k] = -1;
        for (uint32_t j = 0; static_ids && j < BO3_CAR_STATIC_N; j++)
            if (rd64(static_ids + 8u * j) == e->donor)
                sidx[k] = (int)j;
        if (di < 0 || rd32(t + BO3_VL_OFF_A(cap) + 4u * (uint32_t)di) != 1u || sidx[k] < 0) {
            snprintf(why, wn, "%s: donor %s is not a retail race car (it must be in the vehicle list as a race car and in the "
                     "game's 67-car table)", ids, dons);
            FAIL_;
        }
#if MUT != 11
        if (count + 1u > cap) {
            snprintf(why, wn, "%s: the vehicle list is full (%u entries, capacity %u)", ids, (unsigned)cap, (unsigned)cap);
            FAIL_;
        }
#endif
        for (uint32_t j = 0; j < count; j++) {
            uint64_t o = rd64(t + BO3_VL_OFF_ID(cap) + 8u * j);
#if MUT == 16
            char os[13], ns[13];
            dec(o, os);
            dec(e->id, ns);
            if (!strncmp(os, ns, 4) && cls < BO3_VEH_SERIES_CODE0) {
#else
            if (img_class(o) == cls) {
#endif
                entries++;
                if (rd32(t + BO3_VL_OFF_A(cap) + 4u * j))
                    listed++;
            }
        }
#if MUT != 1
        if (listed + 1 > (int)BO3_CAR_ROWS) {
            snprintf(why, wn, "%s: the %.4s series would list %d cars; the garage shows %u per series", ids, ids, listed + 1,
                     (unsigned)BO3_CAR_ROWS);
            FAIL_;
        }
#endif
        if (entries == (int)BO3_CAR_HIDDEN_NTH)   /* GP-P4.2 (M3): told, not refused */
            fprintf(stderr, "[CARS] %s is the %.4s class's 10th vehicle-list entry: the Single Event garage lists it (as the "
                    "retail Dominators); a garage whose list hides the 10th entry (flag +0x265 clear) does not show it\n",
                    ids, ids);
#if MUT == 15
        for (int f = 0; f < 3; f++) {
#else
        for (int f = 0; f < 3 && !e->model_donor; f++) {
#endif
            uint32_t size = 0;
            snprintf(rel, sizeof rel, "pveh\\%.4s\\%s.%s", ids, ids + 4, ext[f]);
            if (!files || !files(user, mod, rel, &size) || !size) {
                snprintf(why, wn, "%s: the mod has no %s", ids, rel);
                FAIL_;
            }
#if MUT != 12
            if (f == 0 && (size > BO3_CAR_MODEL_MAX || (size & 0x7FFu))) {
#else
            if (0) {
#endif
                snprintf(why, wn, "%s: %s has %u bytes; a car model is a multiple of 0x800 bytes up to the race-car slot "
                         "(%u)", ids, rel, (unsigned)size, (unsigned)BO3_CAR_MODEL_MAX);
                FAIL_;
            }
        }
#if MUT == 3
        wr32(t + BO3_VL_OFF_A(cap) + 4u * count, 0u);
#else
        wr32(t + BO3_VL_OFF_A(cap) + 4u * count, 1u);
#endif
        wr32(t + BO3_VL_OFF_B(cap) + 4u * count, rd32(t + BO3_VL_OFF_B(cap) + 4u * (uint32_t)di));
        wr32(t + BO3_VL_OFF_ID(cap) + 8u * count, (uint32_t)e->id);
        wr32(t + BO3_VL_OFF_ID(cap) + 8u * count + 4u, (uint32_t)(e->id >> 32));
        wr32(t + BO3_VL_OFF_C(cap) + 4u * count, rd32(t + BO3_VL_OFF_C(cap) + 4u * (uint32_t)di));
#if MUT == 4
        wr32(t + BO3_VL_OFF_D(cap) + 4u * count, 0u);
#else
        wr32(t + BO3_VL_OFF_D(cap) + 4u * count, rd32(t + BO3_VL_OFF_D(cap) + 4u * (uint32_t)di));
#endif
        count++;
        wr32(t + 4, count);
#if MUT == 13
        if (s_ncars < BO3_VEH_CAP) {             /* defect: registered before the whole mod passed (no rollback) */
            s_cars[s_ncars].e = *e;
            s_cars[s_ncars].donor_sidx = sidx[k];
            s_cars[s_ncars].mod = mod;
            hash_put(e->id, s_ncars);
            s_ncars++;
        }
#endif
    }
#undef FAIL_
    memcpy(vlist, t, BO3_VL_SIZE(cap));
#if MUT != 13
    (void)reg0;
    for (uint32_t k = 0; k < d->n && s_ncars < BO3_VEH_CAP; k++) {
        s_cars[s_ncars].e = d->e[k];
        s_cars[s_ncars].donor_sidx = sidx[k];
        s_cars[s_ncars].mod = mod;
        hash_put(d->e[k].id, s_ncars);
        s_ncars++;
        atomic_fetch_add(&s_stat[0], 1);
    }
#else
    (void)reg0;
#endif
    free(t);
    free(sidx);
    return 1;
}

/* the retail 0x1000-byte image (capacity 128) in the capacity-cap layout: all 128 slots of every array copied (the retail
 * tail behind the count included: the capacity loops of sub_0017D980 / sub_001A2860 read it), slots 128.. zero */
void bo3_vl_relayout(uint8_t *img, uint32_t cap, const uint8_t *retail)
{
    memset(img, 0, BO3_VL_SIZE(cap));
    memcpy(img, retail, 8);
    memcpy(img + BO3_VL_OFF_A(cap), retail + BO3_CAR_OFF_A, 4u * BO3_CAR_CAP);
    memcpy(img + BO3_VL_OFF_B(cap), retail + BO3_CAR_OFF_B, 4u * BO3_CAR_CAP);
    memcpy(img + BO3_VL_OFF_ID(cap), retail + BO3_CAR_OFF_ID, 8u * BO3_CAR_CAP);
    memcpy(img + BO3_VL_OFF_C(cap), retail + BO3_CAR_OFF_C, 4u * BO3_CAR_CAP);
    memcpy(img + BO3_VL_OFF_D(cap), retail + BO3_CAR_OFF_D, 4u * BO3_CAR_CAP);
}

static char s_modname[64][65];
void bo3_car_set_mod_name(int mod, const char *id)
{
    if (mod >= 0 && mod < 64)
        snprintf(s_modname[mod], sizeof s_modname[mod], "%s", id ? id : "");
}
const char *bo3_car_mod_name(int mod)
{
    return mod >= 0 && mod < 64 && s_modname[mod][0] ? s_modname[mod] : "unknown-mod";
}

uint32_t bo3_car_count(void) { return s_ncars; }
const bo3_car_entry *bo3_car_at(uint32_t k) { return k < s_ncars ? &s_cars[k].e : NULL; }
int bo3_car_donor_sidx(uint32_t k) { return k < s_ncars ? s_cars[k].donor_sidx : -1; }
int bo3_car_mod_of(uint32_t k) { return k < s_ncars ? s_cars[k].mod : -1; }

void bo3_cars_reset(void)
{
    memset(s_cars, 0, sizeof s_cars);
    memset(s_logged, 0, sizeof s_logged);
    memset(s_hash, 0, sizeof s_hash);
    s_ncars = 0;
    for (int i = 0; i < 8; i++)
        atomic_store(&s_stat[i], 0);
}

uint32_t bo3_car_stats(uint32_t which)
{
    return which < 8 ? atomic_load(&s_stat[which]) : 0;
}

void bo3_car_stat_add(uint32_t which)
{
    if (which < 8)
        atomic_fetch_add(&s_stat[which], 1);
}

/* one log line per added car and kind (the first time the game takes that path for it) */
static void log_once(int k, unsigned bit, const char *what, uint32_t v)
{
    char ids[13], dons[13];
    if (k < 0 || (uint32_t)k >= s_ncars || (s_logged[k] & bit))
        return;
    s_logged[k] |= (uint8_t)bit;
    dec(s_cars[k].e.id, ids);
    dec(s_cars[k].e.donor, dons);
    fprintf(stderr, "[CARS] %s: %s (donor %s, value 0x%X)\n", ids, what, dons, (unsigned)v);
}

/* ---- the generated-code calls ---- */
uint64_t bo3_car_gen_phys_id(uint32_t lo, uint32_t hi)
{
    uint64_t id = (uint64_t)hi << 32 | lo;
    int k = s_ncars ? bo3_car_find(id) : -1;
    if (k < 0)
        return id;
    atomic_fetch_add(&s_stat[1], 1);
    log_once(k, 1u, "VehiclePhysics ValueDB file = the donor's (garage stats / race block)", 0);
#if MUT == 5
    return id;                                  /* defect: the added ID (no ValueDB file) */
#else
    return s_cars[k].e.donor;
#endif
}

void bo3_car_gen_phys_block(uint32_t block_va)
{
    uint32_t lo = 0, hi = 0;
    int k;
    if (!s_ncars || !bo3_guest_rd32(block_va + 0xB0u, &lo) || !bo3_guest_rd32(block_va + 0xB4u, &hi))
        return;
    k = bo3_car_find((uint64_t)hi << 32 | lo);
#if MUT == 6
    if (k < 0) k = (int)s_ncars - 1;            /* defect: every block gets the last added car's scales */
#else
    if (k < 0)
        return;
#endif
    for (uint32_t j = 0; j < s_cars[k].e.nscale; j++) {
        float v;
        uint32_t off = s_cars[k].e.scale[j].block_off;
        if (bo3_guest_read(block_va + off, &v, 4)) {
            v *= s_cars[k].e.scale[j].scale;
            bo3_guest_write(block_va + off, &v, 4);
            atomic_fetch_add(&s_stat[2], 1);
            log_once(k, 2u, "declared physics scale applied to its block", off);
        }
    }
}

static int read_cstr(uint32_t va, char *out, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        if (!bo3_guest_read(va + (uint32_t)i, &out[i], 1))
            return 0;
        if (!out[i])
            return 1;
    }
    return 0;                                   /* not terminated inside n */
}

static int same_ci(const char *a, const char *b)
{
    for (; *a && *b; a++, b++)
        if (toupper((unsigned char)*a) != toupper((unsigned char)*b))
            return 0;
    return *a == *b;
}

uint32_t bo3_car_gen_photo(uint32_t dict_va, uint32_t name_va)
{
    char name[32], want[13], have[25];
    uint32_t n = 0, arr = 0;
    uint64_t id = 0;
    int k = -1;
    if (!s_ncars || !read_cstr(name_va, name, sizeof name))
        return 0;
    for (char *q = name; *q; q++)             /* GP-P4.3 M7: any case, as cars2 (the base-40 encoder takes upper case) */
        if (*q >= 'a' && *q <= 'z')
            *q = (char)(*q - 'a' + 'A');
    if (strlen(name) <= 12 && enc(name, &id))
        k = bo3_car_find(id);
#if MUT == 7
    if (k < 0) k = 0;                           /* defect: any missed name gets the first car's donor photo */
#else
    if (k < 0)
        return 0;
#endif
    dec(s_cars[k].e.donor, want);
    if (!bo3_guest_rd32(dict_va + 8u, &n) || !bo3_guest_rd32(dict_va + 0xCu, &arr) || n > 4096u)
        return 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t tex = 0;
        if (!bo3_guest_rd32(arr + 16u * i + 8u, &tex) || !bo3_guest_read(tex + 0x48u, have, 24))
            continue;
        have[24] = 0;
        if (same_ci(have, want)) {
            atomic_fetch_add(&s_stat[3], 1);
            log_once(k, 4u, "garage photo = the donor's Frontend.txd entry", tex);
            return tex;
        }
    }
    return 0;
}

uint32_t bo3_car_gen_sidx(uint32_t idx, uint32_t lo, uint32_t hi)
{
    int k;
#if MUT == 8
    if (!s_ncars)
#else
    if (idx != 0xFFFFFFFFu || !s_ncars)
#endif
        return idx;
    k = bo3_car_find((uint64_t)hi << 32 | lo);
    if (k < 0)
        return idx;
    atomic_fetch_add(&s_stat[4], 1);
    log_once(k, 8u, "career index -1 -> the donor's (series code / record / set-up)", (uint32_t)s_cars[k].donor_sidx);
    return (uint32_t)s_cars[k].donor_sidx;
}

uint32_t bo3_car_gen_text(uint32_t dflt, uint32_t kind, uint32_t lo, uint32_t hi)
{
    uint64_t id = (uint64_t)hi << 32 | lo;
    uint32_t r;
    int k = s_ncars ? bo3_car_find(id) : -1;
    if (k < 0)
        return dflt;
    r = bo3_nm_car_text_id(id, kind == BO3_CAR_TEXT_AWARD ? BO3_NM_CAR_AWARD_KIND : BO3_NM_CAR_UPPER, dflt);
    if (r != dflt) {
        atomic_fetch_add(&s_stat[5], 1);
        log_once(k, kind == BO3_CAR_TEXT_AWARD ? 32u : 16u, kind == BO3_CAR_TEXT_AWARD ?
                 "award text = host text ID" : "garage name = host text ID", r);
    }
    return r;
}

/* ---- the game build ---- */
#ifdef BO3_CARS_GAME
#include "modfs.h"
#include "bm_modreq.h"

extern ptrdiff_t g_xbox_mem_offset;
extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t align);

static int game_files(void *user, int mod, const char *rel, uint32_t *size)
{
    const bo3_mod *m = bo3_modfs_mod(mod);
    char path[BO3_MODFS_PATH_MAX + 80];
    FILE *f;
    long l;
    (void)user;
    if (!m)
        return 0;
    snprintf(path, sizeof path, "%s\\files\\%s", m->folder, rel);
    f = fopen(path, "rb");
    if (!f)
        return 0;
    l = fseek(f, 0, SEEK_END) == 0 ? ftell(f) : -1;
    fclose(f);
    if (l < 0 || l > 0x7FFFFFFFL)
        return 0;
    *size = (uint32_t)l;
    return 1;
}

#define GAME_MODS BO3_MODFS_MAX_MODS              /* main18: was its own 64 */
static int s_declared;
static bo3_car_decl s_decl[GAME_MODS];          /* per mod index (BO3_MODFS_MAX_MODS) */
static int s_refused[GAME_MODS];

/* veh1: refuse a whole mod (contracts v0.1 s4): every registration of it is rolled back, the game continues */
static void refuse_mod(int i, const char *mod_id, const char *stage, const char *why)
{
    uint32_t n = s_decl[i].n;
    if (s_refused[i])
        return;
    s_refused[i] = 1;
    for (uint32_t k = 0; k < n; k++) {
        bo3_nm_car_texts_drop(s_decl[i].e[k].id);
        bo3_paint_drop_car(s_decl[i].e[k].id);
    }
    bo3_series_drop_mod(i);
    bo3_paint_drop_mod(i);
    bo3_car_decl_free(&s_decl[i]);
    atomic_fetch_add(&s_stat[6], 1);
    fprintf(stderr, "[VEH] REFUSED mod %s (%s): %s - its cars (%u), series, paints and texts are rolled back; the other mods "
            "continue\n", mod_id, stage, why, (unsigned)n);
}

static char *mod_text(const bo3_mod *m, size_t *n)
{
    char path[BO3_MODFS_PATH_MAX + 16];
    char *text = NULL;
    if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, n) != 1) {
        free(text);
        return NULL;
    }
    return text;
}

/* every usable, enabled mod's [bmashup.series] / [bmashup.cars] / [bmashup.paints], once (stage 1): texts registered with
 * bm_names before its first table install */
void bo3_car_game_declare(void)
{
    uint32_t total = 0;
    int nm = bo3_modfs_mod_count();
    if (s_declared)
        return;
    s_declared = 1;
    if (nm > GAME_MODS)
        nm = GAME_MODS;
    for (int i = 0; i < nm; i++) {               /* phase 0: series (a car of a later mod may name them) */
        const bo3_mod *m = bo3_modfs_mod(i);
        char why[300];
        size_t n = 0;
        char *text;
        if (m)
            bo3_car_set_mod_name(i, m->manifest.id);
        if (!m || !m->usable || !m->enabled || !(text = mod_text(m, &n)))
            continue;
        if (!bo3_veh_game_declare_mod(i, m->manifest.id, text, n, 0, why, sizeof why))
            refuse_mod(i, m->manifest.id, "series", why);
        free(text);
    }
    for (int i = 0; i < nm; i++) {               /* phase 1: cars, then the mod's paints */
        const bo3_mod *m = bo3_modfs_mod(i);
        char why[300];
        size_t n = 0;
        char *text;
        int ok = 1;
        uint32_t added_here = 0;
        if (!m || !m->usable || !m->enabled || s_refused[i] || !(text = mod_text(m, &n)))
            continue;
        if (!bo3_car_parse(text, n, &s_decl[i], why, sizeof why))
            ok = 0;
        for (uint32_t k = 0; ok && k < s_decl[i].n; k++) {
            const bo3_car_entry *e = &s_decl[i].e[k];
            char ids[13];
            dec(e->id, ids);
            if (e->series_prefix) {             /* the series must be this mod's or one it requires */
                int sk = bo3_series_of_prefix(e->id), owner = sk >= 0 ? bo3_series_mod((uint32_t)sk) : -1;
                const bo3_mod *om = owner >= 0 ? bo3_modfs_mod(owner) : NULL;
                if (sk < 0) {
                    snprintf(why, sizeof why, "%s: no active [bmashup.series] has the prefix %.4s", ids, ids);
                    ok = 0;
                } else if (owner != i && !(om && bo3_veh_requires(text, n, om->manifest.id))) {
                    snprintf(why, sizeof why, "%s: the series %.4s belongs to mod %s, which is not in this mod's requires_mods",
                             ids, ids, om ? om->manifest.id : "?");
                    ok = 0;
                }
            }
            for (int j = 0; ok && j < i; j++)       /* a vehicle ID declared by an earlier admitted mod */
                if (!s_refused[j] && find_decl(&s_decl[j], e->id) >= 0) {
                    snprintf(why, sizeof why, "%s is added by an earlier mod too", ids);
                    ok = 0;
                }
            if (ok && total + added_here + 1u > BO3_CAR_MAX_DECL) {
                snprintf(why, sizeof why, "%s: the mods add more than %u cars (registry capacity %u, %u retail)", ids,
                         (unsigned)BO3_CAR_MAX_DECL, (unsigned)BO3_VEH_CAP, (unsigned)BO3_CAR_RETAIL_N);
                ok = 0;
            }
            if (ok) {
                static const char *const ext[3] = {"bgv", "hwd", "lwd"};
                for (int f = 0; ok && f < 3 && !e->model_donor; f++) {
                    char rel[64];
                    uint32_t size = 0;
                    snprintf(rel, sizeof rel, "pveh\\%.4s\\%s.%s", ids, ids + 4, ext[f]);
                    if (!game_files(NULL, i, rel, &size) || !size) {
                        snprintf(why, sizeof why, "%s: the mod has no %s (or declare model = donor)", ids, rel);
                        ok = 0;
                    } else if (f == 0 && (size > BO3_CAR_MODEL_MAX || (size & 0x7FFu))) {
                        snprintf(why, sizeof why, "%s: %s has %u bytes (a multiple of 0x800 up to %u)", ids, rel,
                                 (unsigned)size, (unsigned)BO3_CAR_MODEL_MAX);
                        ok = 0;
                    }
                }
            }
            if (ok)
                added_here++;
        }
        for (uint32_t k = 0; ok && k < s_decl[i].n; k++) {   /* texts: last, so a refusal above registered none */
            int r = bo3_nm_car_texts(s_decl[i].e[k].id, s_decl[i].e[k].name);
            if (r != 0) {
                char ids[13];
                dec(s_decl[i].e[k].id, ids);
                snprintf(why, sizeof why, "%s: its texts cannot be registered (%s)", ids,
                         r == 3 ? "the text table is full" : r == 2 ? "the text table is already installed" : "a duplicate");
                ok = 0;
            }
        }
        if (ok && !bo3_veh_game_declare_mod(i, m->manifest.id, text, n, 1, why, sizeof why))
            ok = 0;                              /* the mod's paints (they may name its own cars) */
        free(text);
        if (!ok) {
            refuse_mod(i, m->manifest.id, "declaration", why);
            continue;
        }
        total += added_here;
    }
    if (total)
        fprintf(stderr, "[CARS] %u added car(s) declared by mods\n", (unsigned)total);
}

/* the mod index declaring id among the admitted (not refused) mods, else -1 (stage 1, for the paints' targets) */
int bo3_car_declared_mod(uint64_t id)
{
    for (int i = 0; i < GAME_MODS; i++)
        if (!s_refused[i] && s_decl[i].e && find_decl(&s_decl[i], id) >= 0)
            return i;
    return -1;
}
int bo3_car_declared(uint64_t id) { return bo3_car_declared_mod(id) >= 0; }

static int s_appended;
static uint8_t *s_after;                        /* the image as the first build left it (host copy) */
static uint32_t s_vl2_va, s_vl2_cap;

/* GP-CARS2 V1 / GP-VEH1: pveh\vlist.bin is read into 0x4D2000 */
void bo3_car_gen_vlist_loaded(void)
{
    uint8_t *retail, *img;
    const uint8_t *st;
    uint32_t total = 0, cap, count;
    int nm;
    if (!g_xbox_mem_offset)
        return;
    bo3_car_game_declare();
    retail = (uint8_t *)((uintptr_t)g_xbox_mem_offset + BO3_CAR_VLIST_VA);
    st = (const uint8_t *)((uintptr_t)g_xbox_mem_offset + BO3_CAR_STATIC_VA);
    if (s_appended) {                           /* the loader passed the mark again: rebuild the same image */
        if (s_vl2_va && s_after) {
            uint8_t *g = (uint8_t *)((uintptr_t)g_xbox_mem_offset + s_vl2_va);
            if (memcmp(g, s_after, BO3_VL_SIZE(s_vl2_cap))) {
                memcpy(g, s_after, BO3_VL_SIZE(s_vl2_cap));
                fprintf(stderr, "[CARS] vehicle list read again: the relocated image (%u added) restored\n", (unsigned)s_ncars);
            }
        }
        return;
    }
    s_appended = 1;
    nm = bo3_modfs_mod_count() < GAME_MODS ? bo3_modfs_mod_count() : GAME_MODS;
    for (int i = 0; i < nm; i++)
        if (!s_refused[i])
            total += s_decl[i].n;
    if (!total)
        return;                                 /* no car mod: the retail image stays the one the game reads */
    count = rd32(retail + 4);
    if (count > BO3_CAR_CAP) {
        fprintf(stderr, "[VEH] the vehicle list holds %u entries (> 128): not the retail format; added cars off\n", (unsigned)count);
        return;
    }
    cap = (count + total + 63u) & ~63u;
    if (cap < BO3_CAR_CAP)
        cap = BO3_CAR_CAP;
    if (cap > BO3_VEH_CAP)
        cap = BO3_VEH_CAP;
    img = (uint8_t *)calloc(1, BO3_VL_SIZE(cap));
    s_vl2_va = img ? xbox_HeapAlloc(BO3_VL_SIZE(cap), 64u) : 0;
    if (!img || !s_vl2_va) {
        free(img);
        s_vl2_va = 0;
        fprintf(stderr, "[VEH] no guest memory for the relocated vehicle list (%u bytes): added cars off, retail list kept\n",
                (unsigned)BO3_VL_SIZE(cap));
        for (int i = 0; i < nm; i++)
            if (s_decl[i].n)
                refuse_mod(i, bo3_modfs_mod(i)->manifest.id, "vehicle list", "no guest memory for the relocated list");
        return;
    }
    bo3_vl_relayout(img, cap, retail);
    bo3_vl_install(s_vl2_va, cap);              /* the class / series answers read the image through bm_veh (host side) */
    for (int i = 0; i < nm; i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char why[300];
        uint32_t before;
        if (!m || s_refused[i] || !s_decl[i].present || !s_decl[i].n)
            continue;
        before = rd32(img + 4);
        memcpy((uint8_t *)((uintptr_t)g_xbox_mem_offset + s_vl2_va), img, BO3_VL_SIZE(cap));   /* host lookups see it */
        if (!bo3_car_append(img, cap, st, &s_decl[i], i, game_files, NULL, why, sizeof why)) {
            refuse_mod(i, m->manifest.id, "vehicle list", why);
            continue;
        }
        for (uint32_t k = 0; k < s_decl[i].n; k++) {
            const bo3_car_entry *e = &s_decl[i].e[k];
            char ids[13], dons[13];
            dec(e->id, ids);
            dec(e->donor, dons);
            fprintf(stderr, "[CARS] mod %s adds %s (vehicle entry %u, class %u, donor %s%s%s%s%s%s%s)\n", m->manifest.id, ids,
                    (unsigned)(before + k), (unsigned)bo3_veh_class_of(e->id), dons, e->model_donor ? ", donor model" : "",
                    e->ai ? ", AI-eligible" : "", e->name[0] ? ", name \"" : "", e->name, e->name[0] ? "\"" : "",
                    e->photo ? ", photo binding for fetex (not in this host: the donor's photo)" : "");
        }
    }
    memcpy((uint8_t *)((uintptr_t)g_xbox_mem_offset + s_vl2_va), img, BO3_VL_SIZE(cap));
    s_after = img;
    s_vl2_cap = cap;
    fprintf(stderr, "[VEH] vehicle list relocated to 0x%08X: %u entries (%u added by mods), capacity %u (configured %u)\n",
            (unsigned)s_vl2_va, (unsigned)rd32(img + 4), (unsigned)s_ncars, (unsigned)cap, (unsigned)BO3_VEH_CAP);
}
#else
void bo3_car_gen_vlist_loaded(void) {}
#endif
