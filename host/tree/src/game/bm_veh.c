/* bm_veh.c - GP-VEH1 EXPERIMENTAL: the relocated vehicle list (vlist2), series, unlock rules, garage navigation, the AI
 * opponent picker for added cars and the model alias (bm_veh.h). Paints: bm_vpaint.c. MUT=n (test builds only) compiles one
 * deliberate defect:
 *   21 bo3_vl_off relocates the track list too (any self)     22 the series code returned for any prefix (9 -> 10)
 *   23 can-right ignores the retail +0x265 / +0x264 limits     24 the left step from a series goes to 9 (the sentinel)
 *   25 a rule CARS:N counts the locked cars                     26 the AI picker ignores "used 3 times"
 *   27 the AI fallback keeps the series code (the game divides by 0)   28 the RNG state not advanced
 *   29 the model alias for every added car (also own files)     30 the capacity bound (cmp 0x80) not relocated */
#include "bm_veh.h"

#include <ctype.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_names.h"
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0
#endif

#define SER_PREFIX "bmashup.series"
#define P40_8 6553600000000ull                   /* 40^8: id / 40^8 = the first four characters */
#define RNG_A 0x004D1FD8u                       /* the game's RNG (sub_00060120 / sub_0005FFD0) */
#define RNG_B 0x004D1FDCu
#define OPEN_BYTES 0x0044CFC8u                  /* u8[67] the derived open-car bytes (VEHICLES.md s3) */

static _Atomic uint32_t s_vstat[14];
static void st(uint32_t w) { atomic_fetch_add(&s_vstat[w], 1); }
uint32_t bo3_vpaint_stats(uint32_t w);           /* bm_vpaint.c: 6..9, 12, 13 */
uint32_t bo3_veh_stats(uint32_t w) { return w < 14 ? atomic_load(&s_vstat[w]) + bo3_vpaint_stats(w) : 0; }

static uint32_t rdg(uint32_t va)
{
    uint32_t v = 0;
    bo3_guest_rd32(va, &v);
    return v;
}

/* ================= vlist2 ================= */
static uint32_t s_vl_va, s_vl_cap = BO3_CAR_CAP;
static uint32_t bo3_vl_cap_layout(void) { return s_vl_va ? s_vl_cap : BO3_CAR_CAP; }   /* the image's real capacity */

int bo3_vl_install(uint32_t va, uint32_t cap)
{
    if (!va || cap < BO3_CAR_CAP || cap > BO3_VEH_CAP)
        return 0;
    s_vl_va = va;
    s_vl_cap = cap;
    return 1;
}

void bo3_vl_reset(void)
{
    s_vl_va = 0;
    s_vl_cap = BO3_CAR_CAP;
}

uint32_t bo3_vl_base(void) { return s_vl_va ? s_vl_va : BO3_CAR_VLIST_VA; }
uint32_t bo3_vl_cap(void)
{
#if MUT == 30
    return BO3_CAR_CAP;                         /* defect: the capacity loops stay at 128 */
#else
    return s_vl_va ? s_vl_cap : BO3_CAR_CAP;
#endif
}
uint32_t bo3_vl_ids(void) { return bo3_vl_base() + BO3_VL_OFF_ID(bo3_vl_cap_layout()); }
uint32_t bo3_vl_fa(void) { return bo3_vl_base() + BO3_VL_OFF_A(bo3_vl_cap_layout()); }
uint32_t bo3_vl_vd(void) { return bo3_vl_base() + BO3_VL_OFF_D(bo3_vl_cap_layout()); }

uint32_t bo3_vl_off(uint32_t self, uint32_t off)
{
#if MUT == 21
    if (!s_vl_va)
#else
    if (!s_vl_va || self != s_vl_va)
#endif
        return off;
    switch (off) {
    case 0x008u: return BO3_VL_OFF_A(s_vl_cap);
    case 0x208u: return BO3_VL_OFF_B(s_vl_cap);
    case 0x408u: return BO3_VL_OFF_ID(s_vl_cap);
    case 0x808u: return BO3_VL_OFF_C(s_vl_cap);
    case 0xA08u: return BO3_VL_OFF_D(s_vl_cap);
    default: return off;
    }
}

uint32_t bo3_vl_count(void) { return rdg(bo3_vl_base() + 4u); }

uint64_t bo3_vl_id_at(uint32_t i)
{
    uint32_t a = bo3_vl_base() + BO3_VL_OFF_ID(bo3_vl_cap_layout()) + 8u * i;
    return (uint64_t)rdg(a) | (uint64_t)rdg(a + 4u) << 32;
}

uint64_t bo3_vl_nth(uint32_t cls, uint32_t n)      /* sub_00157440's rule: every entry of the class, list order */
{
    uint32_t c = bo3_vl_count();
    for (uint32_t i = 0; i < c && i < bo3_vl_cap_layout(); i++) {
        uint64_t id = bo3_vl_id_at(i);
        if (bo3_veh_class_of(id) == cls) {
            if (!n)
                return id;
            n--;
        }
    }
    return 0;
}

/* ================= classes / series ================= */
static const char *const k_lit[9] = {"COMP", "MSCL", "CUPE", "SPRT", "SUPR", "HSPC", "HEVY", "TRAF", "TSPC"};
static uint64_t s_litv[9];
static int s_lit_ready;

static uint64_t prefix_value(const char *p4)
{
    char s[5];
    uint64_t v = 0;
    memcpy(s, p4, 4);
    s[4] = 0;
    bo3_car_enc(s, &v);
    return v / P40_8;
}

static void lit_init(void)
{
    if (s_lit_ready)
        return;
    for (int i = 0; i < 9; i++)
        s_litv[i] = prefix_value(k_lit[i]);
    s_lit_ready = 1;
}

typedef struct ser_reg {
    bo3_series_entry e;
    uint64_t pv;
    int mod;
    int active;
    uint32_t text_id;
} ser_reg;
static ser_reg s_ser[BO3_VEH_SERIES_MAX];
static uint32_t s_nser, s_nser_active;

uint32_t bo3_veh_class_of(uint64_t id)
{
    uint64_t pv;
    lit_init();
    pv = id / P40_8;
    for (uint32_t i = 0; i < 9; i++)
        if (s_litv[i] == pv)
            return i;
    for (uint32_t k = 0; k < s_nser; k++)
        if (s_ser[k].active && s_ser[k].pv == pv)
            return BO3_VEH_SERIES_CODE0 + k;
    return 9u;
}

int bo3_series_of_prefix(uint64_t id)
{
    uint32_t c = bo3_veh_class_of(id);
    return c >= BO3_VEH_SERIES_CODE0 && c < BO3_VEH_SERIES_CODE0 + s_nser ? (int)(c - BO3_VEH_SERIES_CODE0) : -1;
}

uint32_t bo3_series_count(void) { return s_nser; }
const bo3_series_entry *bo3_series_at(uint32_t k) { return k < s_nser ? &s_ser[k].e : NULL; }
int bo3_series_active(uint32_t k) { return k < s_nser && s_ser[k].active; }
int bo3_series_mod(uint32_t k) { return k < s_nser ? s_ser[k].mod : -1; }
void bo3_series_set_text(uint32_t k, uint32_t t) { if (k < s_nser) s_ser[k].text_id = t; }

void bo3_series_drop_mod(int mod)
{
    for (uint32_t k = 0; k < s_nser; k++)
        if (s_ser[k].mod == mod && s_ser[k].active) {
            s_ser[k].active = 0;
            s_nser_active--;
        }
}

int bo3_series_register(const bo3_series_entry *e, int mod, char *why, size_t wn)
{
    uint64_t pv = prefix_value(e->prefix);
    lit_init();
    for (int i = 0; i < 9; i++)
        if (s_litv[i] == pv) {
            snprintf(why, wn, "series %s: %s is a retail class literal", e->name, e->prefix);
            return -1;
        }
    for (uint32_t k = 0; k < s_nser; k++)
        if (s_ser[k].active && s_ser[k].pv == pv) {
            snprintf(why, wn, "series %s: the prefix %s is declared by another series", e->name, e->prefix);
            return -1;
        }
    if (s_nser >= BO3_VEH_SERIES_MAX) {
        snprintf(why, wn, "series %s: more than %u series (class codes 10..%u; format ceiling 127)", e->name,
                 (unsigned)BO3_VEH_SERIES_MAX, (unsigned)(BO3_VEH_SERIES_CODE0 + BO3_VEH_SERIES_MAX - 1));
        return -1;
    }
    memset(&s_ser[s_nser], 0, sizeof s_ser[0]);
    s_ser[s_nser].e = *e;
    s_ser[s_nser].pv = pv;
    s_ser[s_nser].mod = mod;
    s_ser[s_nser].active = 1;
    s_nser_active++;
    return (int)s_nser++;
}

/* ---- rules ---- */
int bo3_veh_rule_parse(const char *s, bo3_veh_rule *r)
{
    char *end = NULL;
    memset(r, 0, sizeof *r);
    if (!s)
        return 0;
    if (!strcmp(s, "open")) {
        r->kind = BO3_RULE_OPEN;
        return 1;
    }
    if (!strncmp(s, "cars:", 5)) {
        long n = strtol(s + 5, &end, 10);
        if (!end || *end || n < 1 || n > (long)BO3_CAR_STATIC_N)
            return 0;
        r->kind = BO3_RULE_CARS;
        r->n = (uint16_t)n;
        return 1;
    }
    if (!strncmp(s, "car:", 4)) {
        if (bo3_car_class_of(s + 4) < 0 || strlen(s + 4) < 5 || !bo3_car_enc(s + 4, &r->id))
            return 0;
        r->kind = BO3_RULE_CAR;
        return 1;
    }
    if (!strncmp(s, "series:", 7)) {
        int c = bo3_car_class_of(s + 7);
        if (c < 0 || strlen(s + 7) != 4)
            return 0;
        r->kind = BO3_RULE_SERIES;
        r->cls = (uint8_t)c;
        return 1;
    }
    return 0;
}

static uint64_t static_id(uint32_t j)
{
    return (uint64_t)rdg(BO3_CAR_STATIC_VA + 8u * j) | (uint64_t)rdg(BO3_CAR_STATIC_VA + 8u * j + 4u) << 32;
}

static int open_byte(uint32_t j)
{
    uint8_t b = 0;
    bo3_guest_read(OPEN_BYTES + j, &b, 1);
    return b != 0;
}

int bo3_veh_rule_open(const bo3_veh_rule *r)
{
    switch (r->kind) {
    case BO3_RULE_OPEN:
        return 1;
    case BO3_RULE_CARS: {
        uint32_t n = 0;
        for (uint32_t j = 0; j < BO3_CAR_STATIC_N; j++)
#if MUT == 25
            n++;                                /* defect: the locked cars counted */
#else
            n += (uint32_t)open_byte(j);
#endif
        return n >= r->n;
    }
    case BO3_RULE_CAR:
        for (uint32_t j = 0; j < BO3_CAR_STATIC_N; j++)
            if (static_id(j) == r->id)
                return open_byte(j);
        return 0;
    case BO3_RULE_SERIES:
        for (uint32_t j = 0; j < BO3_CAR_STATIC_N; j++)
            if (bo3_veh_class_of(static_id(j)) == r->cls && !open_byte(j))
                return 0;
        return 1;
    }
    return 0;
}

static const bo3_veh_rule *car_rule(const bo3_car_entry *e)
{
    int sk;
    if (e->has_rule)
        return &e->rule;
    sk = bo3_series_of_prefix(e->id);
    if (sk >= 0 && s_ser[sk].e.has_rule)
        return &s_ser[sk].e.rule;
    return NULL;
}

static int car_open(const bo3_car_entry *e)
{
    const bo3_veh_rule *r = car_rule(e);
    return !r || bo3_veh_rule_open(r);
}

/* ---- [bmashup.series] ---- */
static int local_ok(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > BO3_VEH_LOCAL_MAX)
        return 0;
    for (; *s; s++)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '_' || *s == '.' || *s == '-'))
            return 0;
    return 1;
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

static const char *astr(recomp_cfg *cfg, const char *key, size_t i)
{
    return recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
}

static long llen(recomp_cfg *cfg, const char *key)
{
    int t = recomp_cfg_type_of(cfg, key);
    return t == RCFG_NONE ? 0 : t == RCFG_ARRAY ? (long)recomp_cfg_array_len(cfg, key) : -1;
}

static int find_ser(const bo3_series_decl *d, const char *name)
{
    for (uint32_t i = 0; i < d->n; i++)
        if (!strcmp(d->e[i].name, name))
            return (int)i;
    return -1;
}

static int title_ok(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > BO3_VEH_TITLE_MAX)
        return 0;
    for (; *s; s++)
        if (!((*s >= 'A' && *s <= 'Z') || (*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == ' ' || *s == '-' ||
              *s == '\'' || *s == '.' || *s == '&'))
            return 0;
    return 1;
}

int bo3_series_parse(const char *text, size_t n, bo3_series_decl *out, char *why, size_t wn)
{
    char err[200], *buf;
    size_t plen = strlen(SER_PREFIX);
    recomp_cfg *cfg;
    int ok = 1;
    long na = 0, nn, nu, nai;
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
    for (size_t i = 0; ok && i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i);
        if (strncmp(k, SER_PREFIX, plen) || (k[plen] && k[plen] != '.'))
            continue;
        out->present = 1;
        if (strcmp(k, SER_PREFIX ".version") && strcmp(k, SER_PREFIX ".add") && strcmp(k, SER_PREFIX ".names") &&
            strcmp(k, SER_PREFIX ".unlock") && strcmp(k, SER_PREFIX ".ai_class")) {
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 1: version, add, names, unlock, ai_class)", k,
                     SER_PREFIX);
            ok = 0;
        }
    }
    if (ok && out->present && (recomp_cfg_type_of(cfg, SER_PREFIX ".version") != RCFG_INT ||
                               recomp_cfg_int(cfg, SER_PREFIX ".version", 0) != 1)) {
        snprintf(why, wn, "%s.version must be 1", SER_PREFIX);
        ok = 0;
    }
    if (ok && out->present) {
        na = llen(cfg, SER_PREFIX ".add");
        if (na <= 0) {
            snprintf(why, wn, "%s.add must be a list of \"<name> = <PREFIX>\"", SER_PREFIX);
            ok = 0;
        } else if (na > (long)BO3_VEH_SERIES_MAX) {
            snprintf(why, wn, "%s.add lists %ld series; at most %u", SER_PREFIX, na, (unsigned)BO3_VEH_SERIES_MAX);
            ok = 0;
        }
    }
    for (long i = 0; ok && i < na; i++) {
        char a[64], b[64];
        bo3_series_entry *e = &out->e[i];
        if (!split(astr(cfg, SER_PREFIX ".add", (size_t)i), '=', a, sizeof a, b, sizeof b) || !local_ok(a) ||
            strlen(b) != 4 || !(b[0] >= 'A' && b[0] <= 'Z') || !(b[1] >= 'A' && b[1] <= 'Z') || !(b[2] >= 'A' && b[2] <= 'Z') ||
            !(b[3] >= 'A' && b[3] <= 'Z')) {
            snprintf(why, wn, "%s.add[%ld] is not \"<name [a-z0-9_.-]> = <4 letters A-Z>\"", SER_PREFIX, i);
            ok = 0;
            break;
        }
        if (find_ser(out, a) >= 0) {
            snprintf(why, wn, "%s.add names %s twice", SER_PREFIX, a);
            ok = 0;
            break;
        }
        for (uint32_t j = 0; j < out->n; j++)
            if (!strcmp(out->e[j].prefix, b)) {
                snprintf(why, wn, "%s.add uses the prefix %s twice", SER_PREFIX, b);
                ok = 0;
            }
        strcpy(e->name, a);
        strcpy(e->prefix, b);
        strcpy(e->title, b);
        e->ai_class = -1;
        out->n = (uint32_t)i + 1;
    }
    nn = ok && out->present ? llen(cfg, SER_PREFIX ".names") : 0;
    nu = ok && out->present ? llen(cfg, SER_PREFIX ".unlock") : 0;
    nai = ok && out->present ? llen(cfg, SER_PREFIX ".ai_class") : 0;
    if (ok && (nn < 0 || nu < 0 || nai < 0)) {
        snprintf(why, wn, "%s.names / unlock / ai_class must be lists", SER_PREFIX);
        ok = 0;
    }
    for (long i = 0; ok && i < nn; i++) {
        char a[64], b[64];
        int k;
        if (!split(astr(cfg, SER_PREFIX ".names", (size_t)i), '=', a, sizeof a, b, sizeof b) || (k = find_ser(out, a)) < 0 ||
            !title_ok(b)) {
            snprintf(why, wn, "%s.names[%ld] is not \"<series> = <1..21 chars A-Z a-z 0-9 space - ' . &>\"", SER_PREFIX, i);
            ok = 0;
            break;
        }
        strcpy(out->e[k].title, b);
    }
    for (long i = 0; ok && i < nu; i++) {
        char a[64], b[64];
        int k;
        if (!split(astr(cfg, SER_PREFIX ".unlock", (size_t)i), '=', a, sizeof a, b, sizeof b) || (k = find_ser(out, a)) < 0 ||
            out->e[k].has_rule || !bo3_veh_rule_parse(b, &out->e[k].rule)) {
            snprintf(why, wn, "%s.unlock[%ld] is not \"<series> = open | cars:N | car:<RETAIL ID> | series:<CLASS>\"",
                     SER_PREFIX, i);
            ok = 0;
            break;
        }
        out->e[k].has_rule = 1;
    }
    for (long i = 0; ok && i < nai; i++) {
        char a[64], b[64];
        int k, c;
        if (!split(astr(cfg, SER_PREFIX ".ai_class", (size_t)i), '=', a, sizeof a, b, sizeof b) || (k = find_ser(out, a)) < 0 ||
            strlen(b) != 4 || (c = bo3_car_class_of(b)) < 0 || out->e[k].ai_class >= 0) {
            snprintf(why, wn, "%s.ai_class[%ld] is not \"<series> = COMP | MSCL | CUPE | SPRT | SUPR | HSPC | HEVY\"",
                     SER_PREFIX, i);
            ok = 0;
            break;
        }
        out->e[k].ai_class = c;
    }
    for (uint32_t k = 0; ok && k < out->n; k++)
        if (out->e[k].ai_class < 0) {
            snprintf(why, wn, "%s.ai_class: series %s has none (required: the retail class AI opponents come from when the "
                     "series has no eligible car)", SER_PREFIX, out->e[k].name);
            ok = 0;
        }
    recomp_cfg_free(cfg);
    if (!ok)
        out->n = 0;
    return ok;
}

/* ================= generated-code calls ================= */
uint32_t bo3_veh_gen_class(uint32_t cls, uint32_t lo, uint32_t hi)
{
#if MUT == 22
    if (cls != 9u || !s_nser_active)
        return cls;
    (void)lo; (void)hi;
    st(0);
    return BO3_VEH_SERIES_CODE0;                /* defect: any unknown prefix is the first series */
#else
    uint32_t c;
    if (cls != 9u || !s_nser_active)
        return cls;
    c = bo3_veh_class_of((uint64_t)hi << 32 | lo);
    if (c >= BO3_VEH_SERIES_CODE0)
        st(0);
    return c;
#endif
}

/* listed (flag A) cars of class cls in the list the game reads */
static uint32_t listed_of(uint32_t cls)
{
    uint32_t c = bo3_vl_count(), n = 0, cap = bo3_vl_cap_layout();
    for (uint32_t i = 0; i < c && i < cap; i++)
        if (bo3_veh_class_of(bo3_vl_id_at(i)) == cls && rdg(bo3_vl_base() + BO3_VL_OFF_A(cap) + 4u * i))
            n++;
    return n;
}

static int visible(uint32_t k)
{
    return k < s_nser && s_ser[k].active && listed_of(BO3_VEH_SERIES_CODE0 + k) > 0;
}

static uint32_t retail_max(uint32_t list)
{
    uint8_t f265 = 0, f264 = 0;
    bo3_guest_read(list + 0x265u, &f265, 1);
    bo3_guest_read(list + 0x264u, &f264, 1);
#if MUT == 23
    (void)f265; (void)f264;
    return 6u;                                  /* defect: the retail limits ignored */
#else
    return !f265 ? 4u : !f264 ? 5u : 6u;
#endif
}

static int next_series(uint32_t cur, uint32_t *out)    /* the first visible series code > cur */
{
    for (uint32_t k = 0; k < s_nser; k++) {
        uint32_t code = BO3_VEH_SERIES_CODE0 + k;
        if (code > cur && visible(k)) {
            *out = code;
            return 1;
        }
    }
    return 0;
}

int bo3_veh_gen_can_right(uint32_t list, uint32_t *al)
{
    uint32_t cur, mx, nx;
    if (!s_nser_active)
        return 0;                               /* the game's own code */
    if (rdg(list + 0x25Cu) != 9u || rdg(list + 0x238u) != 0u) {
        *al = 0;
        return 1;
    }
    cur = rdg(list + 0x258u);
    mx = retail_max(list);
    *al = (cur < BO3_VEH_SERIES_CODE0 && (int32_t)cur < (int32_t)mx) ? 1u : (uint32_t)next_series(cur < mx ? mx : cur, &nx);
    return 1;
}

uint32_t bo3_veh_gen_series_step(uint32_t list, uint32_t cur, int dir)
{
    uint32_t mx, nx;
    if (!s_nser_active)
        return cur + (uint32_t)dir;
    mx = retail_max(list);
    st(1);
    if (dir > 0) {
        if (cur < BO3_VEH_SERIES_CODE0 && (int32_t)cur < (int32_t)mx)
            return cur + 1u;
        return next_series(cur < mx ? mx : cur, &nx) ? nx : cur;
    }
    if (cur < BO3_VEH_SERIES_CODE0)
        return cur - 1u;
#if MUT == 24
    return cur - 1u;                            /* defect: 10 -> 9 (the all-series sentinel) */
#else
    for (uint32_t k = cur - BO3_VEH_SERIES_CODE0; k-- > 0;)
        if (visible(k))
            return BO3_VEH_SERIES_CODE0 + k;
    return mx;
#endif
}

uint32_t bo3_veh_gen_series_text(uint32_t cls)
{
    uint32_t k = cls - BO3_VEH_SERIES_CODE0, t;
    if (cls < BO3_VEH_SERIES_CODE0 || k >= s_nser || !s_ser[k].active)
        return 0xBE0u;                          /* the game's own answer for any class > 6 */
    t = bo3_nm_series_text_id(k, 0xBE0u);
    if (t != 0xBE0u)
        st(10);
    return t;
}

uint32_t bo3_veh_gen_open(uint32_t lo, uint32_t hi)
{
    int k;
    const bo3_car_entry *e;
    if (!bo3_car_count())
        return 1u;                              /* the game's rule for an ID outside its career table */
    k = bo3_car_find((uint64_t)hi << 32 | lo);
    if (k < 0)
        return 1u;
    e = bo3_car_at((uint32_t)k);
    if (car_open(e))
        return 1u;
    st(4);
    return 0u;
}

uint64_t bo3_veh_gen_path_id(uint32_t lo, uint32_t hi)
{
    uint64_t id = (uint64_t)hi << 32 | lo;
    int k = bo3_car_count() ? bo3_car_find(id) : -1;
    const bo3_car_entry *e;
    if (k < 0)
        return id;
    e = bo3_car_at((uint32_t)k);
#if MUT == 29
    st(5);
    return e->donor;                            /* defect: every added car uses the donor's files */
#else
    if (!e->model_donor)
        return id;
    st(5);
    return e->donor;
#endif
}

/* ---- the AI opponent picker (sub_00060120 rule, extended) ---- */
#define HSPC24 0x790798FBA1192600ull
#define HSPC25 0x790798FBA11A2000ull

static int in_list(uint64_t id)
{
    uint32_t c = bo3_vl_count();
    for (uint32_t i = 0; i < c && i < bo3_vl_cap_layout(); i++)
        if (bo3_vl_id_at(i) == id)
            return 1;
    return 0;
}

static int used_ok(uint32_t ctx, uint64_t id)   /* the race's participants list: fewer than 3 uses */
{
    uint32_t n = rdg(ctx + 0x30u) + rdg(ctx + 0x18u);
    int left = 3;
    if (n > 64u)
        n = 64u;
    for (uint32_t i = 0; i < n; i++) {
        uint64_t p = (uint64_t)rdg(ctx + 0x80u + 8u * i) | (uint64_t)rdg(ctx + 0x84u + 8u * i) << 32;
        if (p == id)
            left--;
    }
#if MUT == 26
    return 1;                                   /* defect: a car may race 4+ times */
#else
    return left > 0;
#endif
}

static uint32_t gather(uint32_t ctx, uint32_t cls, int pass, uint64_t *cand)
{
    uint32_t n = 0;
    if (cls < 7u) {                             /* the game's own rows first, exactly its rule */
        for (uint32_t j = 0; j < BO3_CAR_STATIC_N && n < BO3_AI_PICK_MAX; j++) {
            uint64_t id = static_id(j);
            if (!in_list(id))
                continue;
            if (cls == 5u ? (id != HSPC24 && id != HSPC25) : bo3_veh_class_of(id) != cls)
                continue;
            if (pass == 1 && !open_byte(j))
                continue;
            if (!used_ok(ctx, id))
                continue;
            cand[n++] = id;
        }
    }
    for (uint32_t k = 0; k < bo3_car_count() && n < BO3_AI_PICK_MAX; k++) {
        const bo3_car_entry *e = bo3_car_at(k);
        if (!e->ai || bo3_veh_class_of(e->id) != cls || !in_list(e->id))
            continue;
        if (pass == 1 && !car_open(e))
            continue;
        if (!used_ok(ctx, e->id))
            continue;
        cand[n++] = e->id;
    }
    return n;
}

static int class_has_ai(uint32_t cls)
{
    for (uint32_t k = 0; k < bo3_car_count(); k++)
        if (bo3_car_at(k)->ai && bo3_veh_class_of(bo3_car_at(k)->id) == cls)
            return 1;
    return 0;
}

int bo3_veh_gen_ai_pick(uint32_t esp_va, uint32_t *lo, uint32_t *hi)
{
    uint32_t ctx = rdg(esp_va + 4u), cls = rdg(esp_va + 8u), n, a, b, c;
    uint64_t cand[BO3_AI_PICK_MAX], id;
    int16_t s;
    if (!bo3_car_count())
        return 0;
    if (cls >= BO3_VEH_SERIES_CODE0) {
        uint32_t k = cls - BO3_VEH_SERIES_CODE0;
        int fb = k < s_nser ? s_ser[k].e.ai_class : 4;
        n = gather(ctx, cls, 1, cand);
        if (!n)
            n = gather(ctx, cls, 2, cand);
        if (!n) {
#if MUT != 27
            bo3_guest_wr32(esp_va + 8u, (uint32_t)fb);   /* the game's picker with the series' retail class */
#endif
            st(3);
            if (bo3_veh_stats(3) == 1u)
                fprintf(stderr, "[VEH] AI opponents for class %u: no eligible car of the series: the retail class %d "
                        "(ai_class)\n", (unsigned)cls, fb);
            return 0;
        }
    } else if (cls < 7u && class_has_ai(cls)) {
        n = gather(ctx, cls, 1, cand);
        if (!n)
            n = gather(ctx, cls, 2, cand);
        if (!n)
            return 0;                           /* the game's own code (same candidates: none) */
    } else {
        return 0;
    }
    /* the game's RNG step (0x60356..0x60383) */
    bo3_guest_read(RNG_A + 2u, &s, 2);
    a = rdg(RNG_A);
    a = (a << 16) + (uint32_t)(int32_t)s;
    c = rdg(RNG_B);
    a += c;
    c += a;
#if MUT != 28
    bo3_guest_wr32(RNG_A, a);
    bo3_guest_wr32(RNG_B, c);
#endif
    b = a % n;
    id = cand[b];
    *lo = (uint32_t)id;
    *hi = (uint32_t)(id >> 32);
    st(2);
    {
        char ids[13];
        int k = bo3_car_find(id);
        bo3_car_dec(id, ids);
        if (k >= 0 && bo3_veh_stats(2) <= 64u)
            fprintf(stderr, "[VEH] AI opponent %s (class %u, %u candidate(s))\n", ids, (unsigned)cls, (unsigned)n);
    }
    return 1;
}

void bo3_veh_reset(void)
{
    memset(s_ser, 0, sizeof s_ser);
    s_nser = s_nser_active = 0;
    bo3_vl_reset();
    for (int i = 0; i < 14; i++)
        atomic_store(&s_vstat[i], 0);
    bo3_paint_reset_registry();
}

#ifdef BO3_CARS_GAME
#include "bm_modreq.h"

int bo3_veh_requires(const char *text, size_t n, const char *mod_id)
{
    char err[200], *buf = (char *)malloc(n + 1), why[120];
    recomp_cfg *cfg;
    int found = 0;
    if (!buf)
        return 0;
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    if (!cfg)
        return 0;
    for (long i = 0; i < llen(cfg, "bmashup.requires_mods"); i++) {
        bo3_modreq q;
        const char *s = astr(cfg, "bmashup.requires_mods", (size_t)i);
        if (s && bo3_modreq_parse(s, &q, why, sizeof why) && !strcmp(q.id, mod_id))
            found = 1;
    }
    recomp_cfg_free(cfg);
    return found;
}

/* stage 1 per mod: phase 0 = [bmashup.series], phase 1 = [bmashup.paints] (after the mod's cars) */
int bo3_veh_game_declare_mod(int mod, const char *mod_id, const char *text, size_t n, int phase, char *why, size_t wn)
{
    if (phase == 0) {
        bo3_series_decl d;
        if (!bo3_series_parse(text, n, &d, why, wn))
            return 0;
        for (uint32_t i = 0; i < d.n; i++) {
            int k = bo3_series_register(&d.e[i], mod, why, wn);
            if (k < 0) {
                bo3_series_drop_mod(mod);
                return 0;
            }
            if (bo3_nm_series_texts((uint32_t)k, d.e[i].title) != 0) {
                snprintf(why, wn, "series %s: its text cannot be registered", d.e[i].name);
                bo3_series_drop_mod(mod);
                return 0;
            }
            fprintf(stderr, "[VEH] mod %s declares series %s/%s (prefix %s, class code %u, \"%s\", AI fallback class %d)\n",
                    mod_id, mod_id, d.e[i].name, d.e[i].prefix, (unsigned)(BO3_VEH_SERIES_CODE0 + (uint32_t)k), d.e[i].title,
                    d.e[i].ai_class);
        }
        return 1;
    }
    return bo3_paint_game_declare_mod(mod, mod_id, text, n, why, wn);
}
#endif
