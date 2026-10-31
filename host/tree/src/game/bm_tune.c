/* bm_tune.c - G8-E3 EXPERIMENTAL: "bmashup.tune" (bm_tune.h, include/bmashup_tune.h). MUT=n (test builds only) compiles
 * one deliberate defect. */
#include "bm_tune.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_tune_catalog.h"
#include "bm_tune_ai.h"
#include "bo3_tune_gen.h"   /* main21 patch 115: bo3_tune_gen_cad */
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0
#endif
/* GP-AITUNE1 (v1.2 of the declarations, service version 3): the AI rows are the catalogue's last BM_TUNE_AI_N rows.
 * MUT (tests only): 8 a negative value is taken for an unsigned entry; 9 the negative side of a signed entry is not bounded;
 * 10 an AI entry is taken under [bmashup.tune] version 1; 11 a never-read AI entry is taken; 12 a negative integer is stored
 * as its magnitude. */
#define AI_FIRST ((uint32_t)(BM_TUNE_CATALOG_N - BM_TUNE_AI_N))
_Static_assert(BM_TUNE_CATALOG_N > BM_TUNE_AI_N, "the AI rows are appended to the catalogue");

/* main21 patch 115 (zackypoo 04 b): the 7 Air Ram rows (bm_tune_catalog_cad.inc) sit right before the AI rows. They are not in the
 * game's ValueDB copy (no vdb.xml entry; C1: "vdb copies into them: Air Ram 0"): sub_0010C5F0 registers them once, and the mark
 * at the end of that registration (bo3_tune_gen_cad) takes the game's value and applies an owned one. Switch BO3_HOOKREQ_ZAR
 * (OFF: the rows are not verified). MUT (tests): 13 another object accepted at the mark  14 an owned value not re-applied at
 * the mark  15 the game's value taken from the field even when it holds the owner's value (the registration writes none) */
#ifndef BO3_HOOKREQ_ZAR
#define BO3_HOOKREQ_ZAR 0
#endif
#define BM_TUNE_CAD_N 7u
#define CAD_FIRST (AI_FIRST - BM_TUNE_CAD_N)
#define CAD_OBJ 0x0064ACE8u                  /* traffic world 0x60EA00 + 0x3C2E8 (sub_001AA100 loc_001AA335) */
_Static_assert(BM_TUNE_CATALOG_N > BM_TUNE_AI_N + BM_TUNE_CAD_N, "the Air Ram rows precede the AI rows");
static int is_cad(uint32_t i) { return i >= CAD_FIRST && i < AI_FIRST; }
static struct { int have; uint32_t v; } s_cad_pre[BM_TUNE_CAD_N];   /* the field before the host's first write */
static uint32_t s_cad_marks;

/* main21 patch 118 (batch C3-6, zackypoo 04 a): the 32 camera effect rows (bm_tune_catalog_cam.inc) sit right before the Air Ram
 * rows. Their var_va is an OFFSET in the per-race camera block [0x47A134] + 0x2C30 (a heap block, re-made at every traffic
 * init), each a 3-float vector (all three written). The host writes that block ONLY at the mark right after the game's own
 * registration (bo3_tune_gen_cam): a set value is kept and applies from the next race load (applies NEXT_RACE); get answers
 * the owned value, else the game's value seen at the last registration. Switch BO3_HOOKREQ_ZCC (OFF: rows not verified).
 * MUT (tests): 16 another block accepted (no + 0x2C30)  17 an owned value not applied at the mark  18 a set value written into the
 * block at once (outside the mark) */
#ifndef BO3_HOOKREQ_ZCC
#define BO3_HOOKREQ_ZCC 0
#endif
#define BM_TUNE_CAM_N 32u
#define CAM_FIRST (CAD_FIRST - BM_TUNE_CAM_N)
#define CAM_PTR 0x0047A134u                  /* sub_00167220: the block it allocated */
#define CAM_OFF 0x2C30u                      /* the camera tunables inside it (sub_00160B90's EAX) */
_Static_assert(BM_TUNE_CATALOG_N > BM_TUNE_AI_N + BM_TUNE_CAD_N + BM_TUNE_CAM_N, "the camera rows precede the Air Ram rows");
static int is_cam(uint32_t i) { return i >= CAM_FIRST && i < CAD_FIRST; }
static uint32_t s_cam_marks, s_cam_block;

/* main21 patch 123 (batch C3-9): the spark size row (bm_tune_catalog_fx.inc) right before the camera rows - a fixed .data field the
 * start-up initialiser fills (0 in the XBE): a set value is kept until the mark after the Global.txd load (bo3_tune_gen_fx) and
 * written there; after that mark sets are written at once. Switch BO3_HOOKREQ_ZFX. MUT (tests): 19 written before the table is
 * filled  20 the owned value not applied at the mark */
#ifndef BO3_HOOKREQ_ZFX
#define BO3_HOOKREQ_ZFX 0
#endif
#define BM_TUNE_FX_N 1u
#define FX_FIRST (CAM_FIRST - BM_TUNE_FX_N)
static int is_fx(uint32_t i) { return i >= FX_FIRST && i < CAM_FIRST; }
static int s_fx_ready;

/* main21 patch 129 (C3-9b, car shadow look; notes\C3_9B_SHADOW_SOFTNESS_RE.md): the 5 car shadow rows (bm_tune_catalog_shadow.inc)
 * right before the spark row are "virtual": no guest variable; an owned value is kept here and the marks (bo3_tune_gen_shadow_*,
 * recomp_0000.c) use it at every shadow draw (applies at once, next frame); unowned = every mark is the identity. get = the owned
 * value, else the game's value (the catalogue's shipped word, constants checked at configure); reset = release. Own bounds
 * (k_sh_bounds), not 16 x the game's value. Verified only with BO3_HOOKREQ_ZSH, the "blobbyshadow" name and the k_shadow census of
 * every mark site (one byte off -> all 5 rows UNSUPPORTED). MUT (tests): 21 the shadow bounds not applied  22 the alpha test enable
 * not restored at the pass end  23 Length moves the inner rows too  24 the opacity scales the game's product, not the argument */
#ifndef BO3_HOOKREQ_ZSH
#define BO3_HOOKREQ_ZSH 0
#endif
#define BM_TUNE_SH_N 5u
#define SH_FIRST (FX_FIRST - BM_TUNE_SH_N)
_Static_assert(BM_TUNE_CATALOG_N > BM_TUNE_AI_N + BM_TUNE_CAD_N + BM_TUNE_CAM_N + BM_TUNE_FX_N + BM_TUNE_SH_N,
               "the shadow rows precede the spark row");
enum { SH_AT, SH_OPACITY, SH_WIDTH, SH_LENGTH, SH_SOFT };
static const struct { double lo, hi; } k_sh_bounds[BM_TUNE_SH_N] = {{0.0, 1.0}, {0.0, 1.0}, {0.5, 2.0}, {0.5, 2.0}, {0.05, 0.45}};
/* the XBE bytes every mark relies on (XBE 9f497acd; tests\p51 checks this table against default.xbe) */
static const struct { uint32_t va; uint8_t n; uint8_t b[16]; } k_shadow[] = {
    { 0x00043350u, 5, { 0xA1, 0xA8, 0x65, 0x4D, 0x00 } },                                  /* set-up entry: mov eax,[0x4D65A8] */
    { 0x000433B2u, 6, { 0x89, 0x0D, 0x90, 0xD5, 0x75, 0x00 } },                            /* mov [0x75D590],ecx (ALPHATESTENABLE) */
    { 0x000434D2u, 8, { 0xF3, 0x0F, 0x10, 0x15, 0xC0, 0x1A, 0x3B, 0x00 } },                /* movss xmm2,[0x3B1AC0] (v row 1) */
    { 0x000434EAu, 8, { 0xF3, 0x0F, 0x10, 0x15, 0xBC, 0x1A, 0x3B, 0x00 } },                /* movss xmm2,[0x3B1ABC] (v row 2) */
    { 0x00043597u, 13, { 0xF3, 0x0F, 0x10, 0x45, 0x10, 0xF3, 0x0F, 0x59, 0x05, 0xD8, 0x17, 0x3B, 0x00 } },   /* arg * [0x3B17D8] */
    { 0x0004382Cu, 16, { 0x6A, 0x14, 0x68, 0x58, 0xF0, 0x54, 0x00, 0x6A, 0x08, 0x6A, 0x06, 0xE8, 0x14, 0x45, 0x19, 0x00 } },   /* draw */
    { 0x00043850u, 6, { 0x8B, 0x0D, 0x78, 0xDC, 0x75, 0x00 } },                            /* end entry: mov ecx,[0x75DC78] */
    { 0x003B17D8u, 4, { 0x33, 0x33, 0x33, 0x3F } },                                        /* 0.7 */
    { 0x003B1AC0u, 4, { 0x00, 0x00, 0x40, 0x3E } },                                        /* 0.1875 */
    { 0x003B1ABCu, 4, { 0x00, 0x00, 0x50, 0x3F } },                                        /* 0.8125 */
};
#define SH_VB 0x0054F058u                    /* the 8-vertex strip (x, y, z, u, v; 0x14 a vertex) */
#define SH_ATE 0x0075D590u                   /* D3D state cache: ALPHATESTENABLE (0x3C) value 0x75D4A0 + 0x3C*4 */
#define SH_ATE_FLAG 0x0075DC70u              /*   its dirty flag 0x75DB80 + 0x3C*4 */
#define SH_QUEUE 0x0075DE20u                 /*   the dirty queue (ids), count at 0x75DB60 */
#define SH_QCOUNT 0x0075DB60u
static int is_sh(uint32_t i) { return i >= SH_FIRST && i < FX_FIRST; }

/* main21 patch 130: [bmashup.tune] version 3 sliders (bm_tune.h). MUT (tests): 25 a slider range outside the row's own bounds taken
 * 26 sliders taken under version 1 / 2  27 the saved value not applied at the start  28 a default that differs from the mod's set
 * value taken */
static bo3_tune_slider s_sl[BO3_TUNE_SLIDERS_MAX];
static uint32_t s_nsl;
static int s_sh_census;
static int s_sh_diag;                         /* DEV ZDIAG: log the inherited state at the next pass (once a race load) */
static struct { int changed; uint32_t game; } s_sh_at;

static uint32_t ai_flags(uint32_t i)
{
    return i >= AI_FIRST && i < BM_TUNE_CATALOG_N ? k_bm_tune_ai[i - AI_FIRST].flags : 0u;
}

static int is_signed(uint32_t i)
{
    return (ai_flags(i) & BM_TUNE_AI_SIGNED) != 0;
}

typedef struct st {
    int verified;
    const td_host *owner;
    uint32_t raw;                           /* the owner's value (as stored), re-applied after the game's ValueDB copy */
    int decl;                               /* v1.2: the owner is a mod.toml declaration (refusal = exit 93) */
    int have_game;                          /* v1.2: the game's own value (its ValueDB, Data/vdb.xml) is known */
    uint32_t game_raw;                      /*        that value, read right after the game's copy */
} st;

static uint32_t s_reverted, s_decl_refusals;
static void (*s_decl_refused)(uint32_t index, double value, double max);   /* the game build: exit 93 */

static st s_st[BM_TUNE_CATALOG_N];
static bo3_tune_guest s_g;
static int s_configured;

/* the program's value: the .data word, or for an AI row the code default sub_0016AFD0 writes (the block is BSS before) */
static double shipped(uint32_t i)
{
    uint32_t raw = k_bm_tune_catalog[i].shipped;
    float f;
    if (i >= AI_FIRST)
        return k_bm_tune_ai[i - AI_FIRST].vdefault;
    if (k_bm_tune_catalog[i].type == BM_TUNE_INT)
        return (double)raw;
    memcpy(&f, &raw, 4);
    return (double)f;
}

static double as_double(uint32_t i, uint32_t raw)
{
    float f;
    if (k_bm_tune_catalog[i].type == BM_TUNE_INT)
        return is_signed(i) ? (double)(int32_t)raw : (double)raw;
    memcpy(&f, &raw, 4);
    return (double)f;
}

/* v1.2 (G14): the bound is 16 x max(.data value, the game's ValueDB value, 1) once the game's value is known (the copy at the
 * end of boot); before that only a sanity cap applies (the strict check runs at the copy). GP-AITUNE1: magnitudes. */
static double bound(uint32_t i)
{
    double s = fabs(shipped(i)), g = s_st[i].have_game ? fabs(as_double(i, s_st[i].game_raw)) : 0.0;
    if (g > s)
        s = g;
    return 16.0 * (s > 1.0 ? s : 1.0);
}

/* GP-AITUNE1: v inside the entry's range for this bound (0 .. b, or -b .. b for a signed entry) */
static int in_range(uint32_t i, double v, double b)
{
#if MUT == 8
    (void)i;
    return v <= b;                                  /* defect: negative values taken for every entry */
#elif MUT == 9
    return is_signed(i) ? v <= b : v >= 0.0 && v <= b;   /* defect: the negative side is not bounded */
#else
    return is_signed(i) ? v >= -b && v <= b : v >= 0.0 && v <= b;
#endif
}

static double limit_now(uint32_t i)
{
#if MUT == 7
    return 16.0 * (shipped(i) > 1.0 ? shipped(i) : 1.0);     /* defect: the .data value only (v1.1) */
#else
    return s_st[i].have_game ? bound(i) : BM_TUNE_PROVISIONAL_MAX;
#endif
}

static int sh_census(void)
{
    for (size_t r = 0; r < sizeof k_shadow / sizeof k_shadow[0]; r++)
        for (uint32_t k = 0; k < k_shadow[r].n; k++) {
            uint32_t w = 0;
            if (!s_g.read32(s_g.user, k_shadow[r].va + k, &w) || (uint8_t)w != k_shadow[r].b[k])
                return 0;
        }
    return 1;
}

static int sh_in(uint32_t k, double v)
{
#if MUT == 21
    (void)k;
    return v >= 0.0;                                /* defect: the shadow bounds are not applied */
#else
    return v >= k_sh_bounds[k].lo && v <= k_sh_bounds[k].hi;
#endif
}

/* the owned value of shadow row k (checked again: a mark never applies a value outside the row's bounds) */
static int sh_owned(uint32_t k, double *v)
{
    uint32_t i = SH_FIRST + k;
    if (!BO3_HOOKREQ_ZSH || !s_configured || !s_st[i].verified || !s_st[i].owner)
        return 0;
    *v = as_double(i, s_st[i].raw);
    return sh_in(k, *v);
}

uint32_t bo3_tune_configure(const bo3_tune_guest *g)
{
    uint32_t n = 0;
    s_g = *g;
    s_configured = 1;
    s_sh_census = BO3_HOOKREQ_ZSH && sh_census();   /* patch 129: every shadow mark site, once */
    for (uint32_t i = 0; i < BM_TUNE_CATALOG_N; i++) {
        uint32_t v = 0;
        const bm_tune_entry *e = &k_bm_tune_catalog[i];
        s_st[i].owner = NULL;
        s_st[i].decl = 0;
        s_st[i].have_game = 0;
#if MUT == 1
        s_st[i].verified = 1;               /* defect: nothing is checked against the running build */
        (void)v; (void)e;
#else
        s_st[i].verified = s_g.strcmp_at(s_g.user, e->name_va, e->name) && s_g.read32(s_g.user, e->var_va, &v) && v == e->shipped;
#endif
#if MUT != 11
        if (ai_flags(i) & BM_TUNE_AI_UNREAD)
            s_st[i].verified = 0;               /* GP-AITUNE1: the game never reads it: setting it would change nothing */
#endif
        if (is_cad(i) && !BO3_HOOKREQ_ZAR)
            s_st[i].verified = 0;               /* main21 patch 115: no registration mark -> an owned value is not kept */
        if (is_cam(i))                          /* main21 patch 118: the key string only (the value lives in a heap block) */
            s_st[i].verified = BO3_HOOKREQ_ZCC && s_g.strcmp_at(s_g.user, e->name_va, e->name);
        if (is_fx(i))                           /* main21 patch 123: "fxspark" (the table is filled at start-up, 0 now) */
            s_st[i].verified = BO3_HOOKREQ_ZFX && s_g.strcmp_at(s_g.user, e->name_va, e->name);
        if (is_sh(i)) {                         /* main21 patch 129: census + "blobbyshadow" + the constant it replaces (if any) */
            s_st[i].verified = s_sh_census && s_g.strcmp_at(s_g.user, e->name_va, e->name) &&
                               (!e->var_va || (s_g.read32(s_g.user, e->var_va, &v) && v == e->shipped));
            s_st[i].game_raw = e->shipped;      /* the game's value is the code's own constant: known from the start */
            s_st[i].have_game = s_st[i].verified;
        }
        n += (uint32_t)s_st[i].verified;
    }
    memset(s_cad_pre, 0, sizeof s_cad_pre);
    s_cad_marks = 0;
    s_cam_marks = s_cam_block = 0;
    s_fx_ready = 0;
    s_sh_at.changed = 0;
    s_sh_diag = 1;
    s_nsl = 0;                                      /* patch 130: no slider before the declarations */
    return n;
}

static uint32_t TD_CALL t_count(td_host *host)
{
    return host ? (uint32_t)BM_TUNE_CATALOG_N : 0;
}

static int32_t TD_CALL t_get(td_host *host, uint32_t i, double *value)
{
    uint32_t v;
    float f;
    if (!host || !value || i >= BM_TUNE_CATALOG_N || !s_configured)
        return BM_TUNE_BAD_ARG;
    if (!s_st[i].verified)
        return BM_TUNE_UNSUPPORTED;
    if (is_sh(i)) {                             /* patch 129: virtual - the owned value, else the game's */
        v = s_st[i].owner ? s_st[i].raw : s_st[i].game_raw;
    } else if (is_fx(i) && !s_fx_ready) {       /* patch 123: the table is not filled yet */
        if (!s_st[i].owner)
            return BM_TUNE_UNSUPPORTED;
        v = s_st[i].raw;
    } else if (is_cam(i)) {                     /* patch 118: never reads the heap block outside the mark */
        if (!s_st[i].owner && !s_st[i].have_game)
            return BM_TUNE_UNSUPPORTED;         /* no race loaded yet: the game's value is not known */
        v = s_st[i].owner ? s_st[i].raw : s_st[i].game_raw;
    } else if (!s_g.read32(s_g.user, k_bm_tune_catalog[i].var_va, &v))
        return BM_TUNE_UNSUPPORTED;
    if (k_bm_tune_catalog[i].type == BM_TUNE_INT) {
        *value = as_double(i, v);
    } else {
        memcpy(&f, &v, 4);
        *value = (double)f;
    }
    return BM_TUNE_OK;
}

static int32_t TD_CALL t_info(td_host *host, uint32_t i, bm_tune_info *out)
{
    bm_tune_info o;
    double cur = 0;
    if (!host || !out || out->struct_size < 8 || i >= BM_TUNE_CATALOG_N)
        return BM_TUNE_BAD_ARG;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.type = k_bm_tune_catalog[i].type;
    o.verified = (uint32_t)s_st[i].verified;
    o.owner = !s_st[i].owner ? BM_TUNE_OWNER_NONE : s_st[i].owner == host ? BM_TUNE_OWNER_YOU : BM_TUNE_OWNER_OTHER;
    o.shipped = shipped(i);
    if (t_get(host, i, &cur) == BM_TUNE_OK)
        o.current = cur;
    o.max = limit_now(i);
    o.game_value = s_st[i].have_game ? as_double(i, s_st[i].game_raw) : 0.0;
    o.game_value_known = (uint32_t)s_st[i].have_game;
    o.is_signed = (uint32_t)is_signed(i);                       /* version 3 */
    o.min = o.is_signed ? -o.max : 0.0;
    if (is_sh(i)) {                                             /* patch 129: the shadow rows' own range */
        o.min = k_sh_bounds[i - SH_FIRST].lo;
        o.max = k_sh_bounds[i - SH_FIRST].hi;
    }
    o.applies = (ai_flags(i) & BM_TUNE_AI_UNREAD) ? BM_TUNE_APPLIES_NEVER :
                ((ai_flags(i) & BM_TUNE_AI_SETUP) || is_cam(i)) ? BM_TUNE_APPLIES_NEXT_RACE : BM_TUNE_APPLIES_NEXT_USE;
    snprintf(o.name, sizeof o.name, "%s", k_bm_tune_catalog[i].full);
    memcpy(out, &o, o.struct_size);
    return BM_TUNE_OK;
}

static int32_t TD_CALL t_find(td_host *host, const char *name, uint32_t *index)
{
    if (!host || !name || !index)
        return BM_TUNE_BAD_ARG;
    for (uint32_t i = 0; i < BM_TUNE_CATALOG_N; i++)
        if (!strcmp(name, k_bm_tune_catalog[i].full)) {
            *index = i;
            return BM_TUNE_OK;
        }
    return BM_TUNE_NOT_FOUND;
}

static int32_t TD_CALL t_set(td_host *host, uint32_t i, double value)
{
    uint32_t raw;
    if (!host || i >= BM_TUNE_CATALOG_N || !s_configured)
        return BM_TUNE_BAD_ARG;
    if (!s_st[i].verified)
        return BM_TUNE_UNSUPPORTED;
#if MUT != 2
    if (!isfinite(value) || !in_range(i, value, limit_now(i)) ||
        (k_bm_tune_catalog[i].type == BM_TUNE_INT && value != floor(value)))
        return BM_TUNE_OUT_OF_RANGE;
#endif
    if (is_sh(i) && !sh_in(i - SH_FIRST, value))
        return BM_TUNE_OUT_OF_RANGE;            /* patch 129: the shadow rows' own range */
#if MUT != 3
    if (s_st[i].owner && s_st[i].owner != host)
        return BM_TUNE_CONFLICT;
#endif
    if (k_bm_tune_catalog[i].type == BM_TUNE_INT) {
#if MUT == 12
        raw = (uint32_t)fabs(value);                /* defect: the sign is lost */
#else
        raw = value < 0.0 ? (uint32_t)(int32_t)value : (uint32_t)value;   /* GP-AITUNE1: two's complement for signed ints */
#endif
    } else {
        float f = (float)value;
        memcpy(&raw, &f, 4);
    }
    if (is_sh(i)) {                             /* patch 129: kept host-side (the value first: a mark never sees an owner + old value) */
        s_st[i].raw = raw;
        s_st[i].decl = 0;
        s_st[i].owner = host;
        return BM_TUNE_OK;
    }
    if (is_fx(i) && !s_fx_ready) {              /* patch 123: kept; written at the mark (the initialiser would overwrite it) */
#if MUT == 19
        s_g.write32(s_g.user, k_bm_tune_catalog[i].var_va, raw);   /* defect: written before the table is filled */
#endif
        s_st[i].owner = host;
        s_st[i].raw = raw;
        s_st[i].decl = 0;
        return BM_TUNE_OK;
    }
    if (is_cam(i)) {                            /* patch 118: kept; written into the block at the next registration mark */
#if MUT == 18
        if (s_cam_block)
            s_g.write32(s_g.user, s_cam_block + k_bm_tune_catalog[i].var_va, raw);   /* defect: a write outside the mark */
#endif
        s_st[i].owner = host;
        s_st[i].raw = raw;
        s_st[i].decl = 0;
        return BM_TUNE_OK;
    }
    if (is_cad(i) && !s_cad_pre[i - CAD_FIRST].have &&           /* main21 patch 115: the field before the host's first write */
        s_g.read32(s_g.user, k_bm_tune_catalog[i].var_va, &s_cad_pre[i - CAD_FIRST].v))
        s_cad_pre[i - CAD_FIRST].have = 1;
    if (!s_g.write32(s_g.user, k_bm_tune_catalog[i].var_va, raw))
        return BM_TUNE_UNSUPPORTED;
    s_st[i].owner = host;
    s_st[i].raw = raw;
    s_st[i].decl = 0;
    return BM_TUNE_OK;
}

/* G8-E3 v1.1 (analysis\TUNE_RESET_TRACE.md): at the end of boot the game copies its ValueDB (Data/vdb.xml) into every
 * registered variable (sub_001AF040, loc_001AF09F: 32-bit values). The mark right after that copy calls here with the
 * variable's address: an owned catalogue value is written again, so the owner's value is the one the game uses. */
void bo3_tune_gen_applied(uint32_t var_va)
{
#if defined(BO3_HOOKREQ_ZDIAG) && BO3_HOOKREQ_ZDIAG
    {
        extern void bo3_zdiag_copy(uint32_t var_va);   /* main21 patch 107: DEV-only crash camera / Air Ram copy probe */
        bo3_zdiag_copy(var_va);
    }
#endif
    for (uint32_t i = 0; i < BM_TUNE_CATALOG_N; i++)
        if (k_bm_tune_catalog[i].var_va == var_va && !is_cam(i) && !is_sh(i)) {   /* patch 118: camera rows hold offsets; 129: virtual */
            uint32_t now = 0;
            if (!s_configured || !s_g.read32(s_g.user, var_va, &now))
                return;
            s_st[i].game_raw = now;             /* v1.2: what the game just copied in is its own value */
            s_st[i].have_game = 1;
#if MUT != 5
            if (s_st[i].owner) {
                double v = as_double(i, s_st[i].raw);
#if MUT == 6
                if (1) {                        /* defect: no strict check at the copy */
#else
                if (in_range(i, v, bound(i))) {
#endif
                    s_g.write32(s_g.user, var_va, s_st[i].raw);
                } else if (s_st[i].decl) {
                    s_decl_refusals++;
                    if (s_decl_refused)
                        s_decl_refused(i, v, bound(i));
                    s_st[i].owner = NULL;       /* (tests: the game build exits 93 in s_decl_refused) */
                } else {
                    s_reverted++;               /* a plugin's value above the bound: the game's value stays */
                    fprintf(stderr, "[TUNE] \"%s\" = %g refused at the game's value %g (bound %g): the game's value is used\n",
                            k_bm_tune_catalog[i].full, v, as_double(i, now), bound(i));
                    s_st[i].owner = NULL;
                }
            }
#else
            (void)s_decl_refused;
#endif
            return;
        }
}

/* main21 patch 115: the mark at the end of sub_0010C5F0's one-time registration (loc_0010CCCE, before `mov byte [ecx + 0x578],
 * 1`; ECX = the object). The game's value of each Air Ram row = the field now, unless it still holds the owner's value (the
 * registration writes none, statically): then the field's value before the host's first write. An owned value inside the bound
 * is (re)written; above it: a declaration -> the refusal handler (exit 93), a plugin's value -> the game's value is written back
 * and the owner released. One log line per registration with the game's values. */
void bo3_tune_gen_cad(uint32_t obj)
{
    float gv[BM_TUNE_CAD_N];
    uint32_t owned = 0;
#if MUT != 13
    if (!BO3_HOOKREQ_ZAR || !s_configured || obj != CAD_OBJ) {
        fprintf(stderr, "[TUNE] Air Ram registration: object %08x not the expected %08x (or rows off): nothing applied\n",
                (unsigned)obj, (unsigned)CAD_OBJ);
        return;
    }
#endif
    s_cad_marks++;
    for (uint32_t k = 0; k < BM_TUNE_CAD_N; k++) {
        uint32_t i = CAD_FIRST + k, va = k_bm_tune_catalog[i].var_va, now = 0, game;
        if (!s_st[i].verified || !s_g.read32(s_g.user, va, &now)) {
            gv[k] = 0.0f;
            continue;
        }
#if MUT == 15
        game = now;
#else
        game = (s_st[i].owner && now == s_st[i].raw && s_cad_pre[k].have) ? s_cad_pre[k].v : now;
#endif
        memcpy(&gv[k], &game, 4);
        s_st[i].game_raw = game;
        s_st[i].have_game = 1;
        if (s_st[i].owner) {
            double v = as_double(i, s_st[i].raw);
            if (in_range(i, v, bound(i))) {
#if MUT != 14
                s_g.write32(s_g.user, va, s_st[i].raw);
#endif
                owned++;
            } else if (s_st[i].decl) {
                s_decl_refusals++;
                s_g.write32(s_g.user, va, game);
                if (s_decl_refused)
                    s_decl_refused(i, v, bound(i));
                s_st[i].owner = NULL;
            } else {
                s_reverted++;
                s_g.write32(s_g.user, va, game);
                fprintf(stderr, "[TUNE] \"%s\" = %g refused at the game's value %g (bound %g): the game's value is used\n",
                        k_bm_tune_catalog[i].full, v, as_double(i, game), bound(i));
                s_st[i].owner = NULL;
            }
        }
    }
    fprintf(stderr, "[TUNE] Air Ram registered (object %08x): game values front corner %g, back corner %g, side %g, front %g, "
            "back %g, world %g, low speed %g; owned applied %u\n", (unsigned)obj, gv[0], gv[1], gv[2], gv[3], gv[4], gv[5], gv[6],
            (unsigned)owned);
}

/* main21 patch 118: the mark right after sub_00167220's call of sub_00160B90 (loc_00167296): the camera block [0x47A134] + 0x2C30
 * holds the game's code defaults now. Each row: the game's value = its x component; an owned value inside the bound is written to
 * all three components; above it: a declaration -> the refusal handler (exit 93), a plugin's value -> released (the game's value
 * stays). The only host write into this heap block. One log line per registration. */
void bo3_tune_gen_cam(void)
{
    uint32_t base = 0, owned = 0;
    float hc[2] = {0.0f, 0.0f};
    s_sh_diag = 1;                                          /* patch 129 (DEV ZDIAG): a race load - log the shadow state again */
    if (!BO3_HOOKREQ_ZCC || !s_configured || !s_g.read32(s_g.user, CAM_PTR, &base) || !base) {
        fprintf(stderr, "[TUNE] camera registration: no block (or rows off): nothing applied\n");
        return;
    }
#if MUT == 16
    s_cam_block = base;                                     /* defect: the allocation itself, not the tunables */
#else
    s_cam_block = base + CAM_OFF;
#endif
    s_cam_marks++;
    for (uint32_t k = 0; k < BM_TUNE_CAM_N; k++) {
        uint32_t i = CAM_FIRST + k, va = s_cam_block + k_bm_tune_catalog[i].var_va, game = 0;
        if (!s_st[i].verified || !s_g.read32(s_g.user, va, &game))
            continue;
        s_st[i].game_raw = game;
        s_st[i].have_game = 1;
        if (k < 2)
            memcpy(&hc[k], &game, 4);
        if (s_st[i].owner) {
            double v = as_double(i, s_st[i].raw);
            if (in_range(i, v, bound(i))) {
#if MUT != 17
                for (uint32_t c = 0; c < 3; c++)
                    s_g.write32(s_g.user, va + 4u * c, s_st[i].raw);
#endif
                owned++;
            } else if (s_st[i].decl) {
                s_decl_refusals++;
                if (s_decl_refused)
                    s_decl_refused(i, v, bound(i));
                s_st[i].owner = NULL;
            } else {
                s_reverted++;
                fprintf(stderr, "[TUNE] \"%s\" = %g refused at the game's value %g (bound %g): the game's value is used\n",
                        k_bm_tune_catalog[i].full, v, as_double(i, game), bound(i));
                s_st[i].owner = NULL;
            }
        }
    }
    fprintf(stderr, "[TUNE] camera registered (block %08x): HandyCam spring %g damping %g; owned applied %u\n",
            (unsigned)s_cam_block, hc[0], hc[1], (unsigned)owned);
}

/* main21 patch 123: the mark after the Global.txd load - the fx tables hold the game's values now */
void bo3_tune_gen_fx(void)
{
    uint32_t i = FX_FIRST, va = k_bm_tune_catalog[FX_FIRST].var_va, game = 0;
    float gv = 0.0f;
    if (!BO3_HOOKREQ_ZFX || !s_configured || !s_st[i].verified || s_fx_ready || !s_g.read32(s_g.user, va, &game))
        return;
    s_fx_ready = 1;
    s_st[i].game_raw = game;
    s_st[i].have_game = 1;
    memcpy(&gv, &game, 4);
    if (s_st[i].owner) {
        double v = as_double(i, s_st[i].raw);
        if (in_range(i, v, bound(i))) {
#if MUT != 20
            s_g.write32(s_g.user, va, s_st[i].raw);
#endif
        } else if (s_st[i].decl) {
            s_decl_refusals++;
            if (s_decl_refused)
                s_decl_refused(i, v, bound(i));
            s_st[i].owner = NULL;
        } else {
            s_reverted++;
            s_st[i].owner = NULL;
        }
    }
    fprintf(stderr, "[TUNE] sparks: the game's size %g%s\n", gv, s_st[i].owner ? ", the owned value applied" : "");
}

/* main21 patch 129: the car shadow marks (bo3_tune_gen.h). Each one is the identity while its row is not owned. */
void bo3_tune_gen_shadow_begin(void)        /* sub_00043350 entry: a new shadow pass */
{
    s_sh_at.changed = 0;
#if defined(BO3_HOOKREQ_ZDIAG) && BO3_HOOKREQ_ZDIAG
    if (s_sh_diag && s_configured && BO3_HOOKREQ_ZSH) {     /* DEV: the state the shadow inherits (notes M0), once a race load */
        static const uint32_t va[10] = {0x75D594u, 0x75D588u, 0x75D584u, 0x75D590u, 0x75D770u, 0x75D780u, 0x75D790u, 0x75D7A0u,
                                        0x75D7B0u, 0x75D5A0u};
        uint32_t w[10] = {0};
        for (int k = 0; k < 10; k++)
            s_g.read32(s_g.user, va[k], &w[k]);
        s_sh_diag = 0;
        fprintf(stderr, "[DIAG] shadow state: ALPHAREF 0x%X ALPHAFUNC 0x%X ZFUNC 0x%X ALPHATESTENABLE %u stage0 MAG %u MIN %u MIP %u "
                "LODBIAS 0x%08X MAXMIP %u (ZWRITEENABLE %u)\n", (unsigned)w[0], (unsigned)w[1], (unsigned)w[2], (unsigned)w[3],
                (unsigned)w[4], (unsigned)w[5], (unsigned)w[6], (unsigned)w[7], (unsigned)w[8], (unsigned)w[9]);
    }
#else
    (void)s_sh_diag;                                        /* the release build: no probe */
#endif
}

uint32_t bo3_tune_gen_shadow_at(uint32_t game)   /* 0x433B2: the ALPHATESTENABLE value the set-up writes (game: 1) */
{
    double v;
    if (!sh_owned(SH_AT, &v))
        return game;
    s_sh_at.game = game;
    s_sh_at.changed = (uint32_t)v != game;
    return (uint32_t)v;
}

float bo3_tune_gen_shadow_vsplit(uint32_t which, float game)   /* 0x434D2 (0: v of row 1) / 0x434EA (1: v of row 2) */
{
    double v;
    if (!sh_owned(SH_SOFT, &v))
        return game;
    return which ? 1.0f - (float)v : (float)v;
}

float bo3_tune_gen_shadow_opacity(float game, float arg)   /* after 0x4359C: game = arg * 0.7; owned: arg * value */
{
    double v;
    if (!sh_owned(SH_OPACITY, &v))
        return game;
#if MUT == 24
    (void)arg;
    return game * (float)v;                         /* defect: the game's product scaled again */
#else
    return arg * (float)v;
#endif
}

/* before the draw at 0x4382C: the 8 vertices at 0x54F058 (rows of 2: outer front, inner front, inner rear, outer rear). Width: every x
 * about the strip centre; Length: the outer rows' z away from the box centre (never inside the inner rows: no folded strip). */
void bo3_tune_gen_shadow_size(void)
{
    double w = 1.0, l = 1.0;
    int ow = sh_owned(SH_WIDTH, &w) && w != 1.0, ol = sh_owned(SH_LENGTH, &l) && l != 1.0;
    uint32_t r[8][2];
    float x[8], z[8];
    if (!ow && !ol)
        return;
    for (uint32_t k = 0; k < 8; k++)
        if (!s_g.read32(s_g.user, SH_VB + k * 0x14u, &r[k][0]) || !s_g.read32(s_g.user, SH_VB + k * 0x14u + 8u, &r[k][1]))
            return;
    for (uint32_t k = 0; k < 8; k++) {
        memcpy(&x[k], &r[k][0], 4);
        memcpy(&z[k], &r[k][1], 4);
    }
    if (ow) {
        float cx = 0.5f * (x[0] + x[1]);
        for (uint32_t k = 0; k < 8; k++)
            x[k] = cx + (x[k] - cx) * (float)w;
    }
    if (ol) {
        float cz = 0.5f * (z[0] + z[6]);
        for (uint32_t k = 0; k < 8; k++) {
#if MUT == 23
            int outer = 1;                          /* defect: the inner rows move too */
#else
            int outer = k < 2 || k >= 6;
#endif
            float d, in;
            if (!outer)
                continue;
            d = (z[k] - cz) * (float)l;
            in = z[k < 2 ? 2 : 4] - cz;             /* the inner row on the same side */
            if (fabsf(d) < fabsf(in) && d * in >= 0.0f)
                d = in;
            z[k] = cz + d;
        }
    }
    for (uint32_t k = 0; k < 8; k++) {
        memcpy(&r[k][0], &x[k], 4);
        memcpy(&r[k][1], &z[k], 4);
        s_g.write32(s_g.user, SH_VB + k * 0x14u, r[k][0]);
        s_g.write32(s_g.user, SH_VB + k * 0x14u + 8u, r[k][1]);
    }
}

/* sub_00043850 entry: the game's end leaves ALPHATESTENABLE as the set-up wrote it (1; sub_00043850 restores only SRC / DESTBLEND and
 * the stage-0 address modes): after an owned value the game's value goes back into the state cache through the game's own dirty-queue
 * protocol (value, flag 0x75DC70, queue entry 0x3C), so later draws inherit exactly what retail leaves. */
void bo3_tune_gen_shadow_end(void)
{
    uint32_t flag = 1, cnt = 0;
    if (!s_sh_at.changed)
        return;
    s_sh_at.changed = 0;
#if MUT != 22
    s_g.write32(s_g.user, SH_ATE, s_sh_at.game);
    if (s_g.read32(s_g.user, SH_ATE_FLAG, &flag) && !flag && s_g.read32(s_g.user, SH_QCOUNT, &cnt) && cnt < 0x100u) {
        s_g.write32(s_g.user, SH_QUEUE + cnt * 4u, 0x3Cu);
        s_g.write32(s_g.user, SH_ATE_FLAG, 1u);
        s_g.write32(s_g.user, SH_QCOUNT, cnt + 1u);
    }
#else
    (void)flag; (void)cnt;
#endif
}

uint32_t bo3_tune_stats(uint32_t which)
{
    return which == 0 ? s_reverted : which == 1 ? s_decl_refusals : which == 3 ? s_cam_marks : s_cad_marks;
    /* 2: Air Ram registrations (patch 115), 3: camera registrations (patch 118) */
}

void bo3_tune_set_decl_refused(void (*fn)(uint32_t index, double value, double max))
{
    s_decl_refused = fn;
}

static int32_t TD_CALL t_reset(td_host *host, uint32_t i)
{
    if (!host || i >= BM_TUNE_CATALOG_N || !s_configured)
        return BM_TUNE_BAD_ARG;
    if (!s_st[i].verified)
        return BM_TUNE_UNSUPPORTED;
    if (s_st[i].owner != host)
        return BM_TUNE_CONFLICT;            /* only the owner restores (and releases) */
    if (is_fx(i) && !s_fx_ready) {          /* patch 123: nothing written yet */
        s_st[i].owner = NULL;
        return BM_TUNE_OK;
    }
    if (is_cam(i) || is_sh(i)) {            /* patch 118: the next registration writes the game's defaults again; 129: release */
        s_st[i].owner = NULL;
        return BM_TUNE_OK;
    }
#if MUT != 4
    if (!s_g.write32(s_g.user, k_bm_tune_catalog[i].var_va, s_st[i].have_game ? s_st[i].game_raw : k_bm_tune_catalog[i].shipped))
        return BM_TUNE_UNSUPPORTED;         /* v1.2: the game's own value once known, else the .data value */
#endif                                      /* MUT 4: reset releases without restoring */
    s_st[i].owner = NULL;
    return BM_TUNE_OK;
}

static const bm_tune_api s_api = {(uint32_t)sizeof(bm_tune_api), BM_TUNE_VERSION, t_count, t_info, t_find, t_get, t_set, t_reset};

const bm_tune_api *bo3_bm_tune_api(void)
{
    return &s_api;
}

/* ---- mod.toml declarations ---- */
static void trim(char *s)
{
    size_t n = strlen(s), a = 0;
    while (n && (s[n - 1] == ' ' || s[n - 1] == '\t'))
        s[--n] = 0;
    while (s[a] == ' ' || s[a] == '\t')
        a++;
    memmove(s, s + a, strlen(s + a) + 1);
}

/* ---- main21 patch 130: sliders ([bmashup.tune] version 3; bm_tune.h) ---- */

/* t (trimmed in place) is "[-]D[.D]": 1 with the value and its decimal count */
static int num_tok(char *t, double *v, uint32_t *dec)
{
    const char *p;
    uint32_t d = 0;
    int digits = 0;
    trim(t);
    p = t + (*t == '-');
    for (; *p >= '0' && *p <= '9'; p++)
        digits++;
    if (*p == '.') {
        for (p++; *p >= '0' && *p <= '9'; p++)
            d++;
        if (!d)
            return 0;
    }
    if (*p || !digits || strlen(t) > 20)
        return 0;
    *v = strtod(t, NULL);
    *dec = d;
    return 1;
}

/* the row's own bounds: the shadow rows' k_sh_bounds; else 0 (signed: -B) .. B, B = 16 x max(|the program's value|, 1) - inside every
 * later bound (bound() only grows with the game's value) */
static void row_bounds(uint32_t i, double *lo, double *hi)
{
    double b = fabs(shipped(i));
    if (is_sh(i)) {
        *lo = k_sh_bounds[i - SH_FIRST].lo;
        *hi = k_sh_bounds[i - SH_FIRST].hi;
        return;
    }
    b = 16.0 * (b > 1.0 ? b : 1.0);
    *hi = b;
    *lo = is_signed(i) ? -b : 0.0;
}

static int text_plain(const char *t, size_t lo, size_t hi)
{
    size_t n = strlen(t);
    if (n < lo || n > hi)
        return 0;
    for (size_t k = 0; k < n; k++)
        if ((unsigned char)t[k] < 0x20 || (unsigned char)t[k] > 0x7E || t[k] == '"' || t[k] == '\\')
            return 0;
    return 1;
}

/* s as [a-z0-9_] (runs of other characters = one '_', none at the ends) into k (cap bytes); its length */
static size_t slug(const char *s, char *k, size_t cap)
{
    size_t n = 0;
    for (; *s; s++) {
        char c = *s >= 'A' && *s <= 'Z' ? (char)(*s + 32) : *s;
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
            if (n < cap - 1)
                k[n++] = c;
        } else if (n && k[n - 1] != '_' && n < cap - 1) {
            k[n++] = '_';
        }
    }
    while (n && k[n - 1] == '_')
        n--;
    k[n] = 0;
    return n;
}

/* the settings key of row i: its full name as [a-z0-9_] ("effects_shadow_width"); longer than 24: the last group part + the name
 * ("shadow_alpha_test"); still longer: the first 15 + '_' + 8 hex digits of the full name's FNV-1a (stable: the name is the game's) */
static void slider_key(uint32_t i, char out[25])
{
    char k[160];
    const char *full = k_bm_tune_catalog[i].full, *bar = strstr(full, "| "), *last = full;
    size_t n;
    uint32_t h = 2166136261u;
    for (const char *p = full; *p; p++)
        h = (h ^ (uint8_t)*p) * 16777619u;
    if ((n = slug(full, k, sizeof k)) <= 24) {
        snprintf(out, 25, "%s", k);
        return;
    }
    for (const char *p = full; bar && p < bar; p++)
        if (*p == '/')
            last = p + 1;
    if (bar && slug(last, k, sizeof k) <= 24) {
        snprintf(out, 25, "%s", k);
        return;
    }
    slug(full, k, sizeof k);
    n = 15;
    while (n && k[n - 1] == '_')
        n--;
    snprintf(out, 25, "%.*s_%08x", (int)n, k, (unsigned)h);
}

/* the mod's set = [...] value of row idx: 1 with it (the set block checked the lines already) */
static int set_value_of(const recomp_cfg *cfg, uint32_t idx, double *v)
{
    size_t cnt = recomp_cfg_type_of(cfg, "bmashup.tune.set") != RCFG_NONE ? recomp_cfg_array_len(cfg, "bmashup.tune.set") : 0;
    for (size_t k = 0; k < cnt; k++) {
        char line[300], *eq;
        const char *s = recomp_cfg_array_string(cfg, "bmashup.tune.set", k, NULL);
        if (!s || strlen(s) >= sizeof line || !(eq = strrchr(strcpy(line, s), '=')))
            continue;
        *eq = 0;
        trim(line);
        if (!strcmp(line, k_bm_tune_catalog[idx].full)) {
            *v = strtod(eq + 1, NULL);
            return 1;
        }
    }
    return 0;
}

/* one slider line into *o (not yet recorded); 0 with why */
static int slider_parse(const recomp_cfg *cfg, const char *s, td_host *who, bo3_tune_slider *o, char *why, size_t wn)
{
    char line[300], *lab, *eq, *colon, *dots, *st, *rhs;
    double v[4] = {0, 0, 0, 0}, rlo, rhi, sv, p = 1.0;
    uint32_t dec[4] = {0, 0, 0, 0}, d = 0, idx;
    long long u[4];
    bm_tune_info inf;
    const char *nm;
    memset(o, 0, sizeof *o);
    if (!s || strlen(s) >= sizeof line) {
        snprintf(why, wn, "a slider is not \"Group | Name = default : min .. max [step s] [label text]\"");
        return 0;
    }
    strcpy(line, s);
    if ((lab = strstr(line, " label ")) != NULL) {
        *lab = 0;
        lab += 7;
        trim(lab);
    }
    if (!(eq = strrchr(line, '=')) || !(colon = strchr(eq, ':')) || !(dots = strstr(colon, ".."))) {
        snprintf(why, wn, "slider \"%.80s\" is not \"Group | Name = default : min .. max [step s] [label text]\"", s);
        return 0;
    }
    *eq = *colon = *dots = 0;
    rhs = dots + 2;
    if ((st = strstr(rhs, "step")) != NULL)
        *st = 0;
    trim(line);
    if (!num_tok(eq + 1, &v[0], &dec[0]) || !num_tok(colon + 1, &v[1], &dec[1]) || !num_tok(rhs, &v[2], &dec[2]) ||
            (st && !num_tok(st + 4, &v[3], &dec[3]))) {
        snprintf(why, wn, "slider \"%s\": default, min, max and step must be numbers ([-]D[.D])", line);
        return 0;
    }
    if (t_find(who, line, &idx) != BM_TUNE_OK) {
        snprintf(why, wn, "slider \"%s\" is not a tuning value this build knows", line);
        return 0;
    }
    if (!s_st[idx].verified) {
        snprintf(why, wn, "slider \"%s\": not verified on this game build", line);
        return 0;
    }
    for (int k = 0; k < 4; k++)
        d = dec[k] > d ? dec[k] : d;
    if (d > BO3_TUNE_SLIDER_DECIMALS || (d && k_bm_tune_catalog[idx].type == BM_TUNE_INT)) {
        snprintf(why, wn, "slider \"%s\": %s", line, d > BO3_TUNE_SLIDER_DECIMALS ? "at most 6 decimals" :
                 "this row takes whole numbers");
        return 0;
    }
    for (uint32_t k = 0; k < d; k++)
        p *= 10.0;
    for (int k = 0; k < 4; k++)
        u[k] = llround(v[k] * p);
    if (!st)
        u[3] = 1;                                   /* one unit of the finest decimal given */
    row_bounds(idx, &rlo, &rhi);
    if (u[3] < 1 || u[1] >= u[2] || (u[2] - u[1]) % u[3] || (u[2] - u[1]) / u[3] + 1 > BO3_TUNE_SLIDER_STEPS ||
            llabs(u[1]) > 1000000 || llabs(u[2]) > 1000000) {
        snprintf(why, wn, "slider \"%s\": min < max, max = min + a whole number of steps (step > 0), at most %u values, at most "
                 "1000000 units of the finest decimal", line, BO3_TUNE_SLIDER_STEPS);
        return 0;
    }
#if MUT != 25
    if (v[1] < rlo || v[2] > rhi) {
#else
    if (0) {                                        /* defect: the row's own bounds not checked */
#endif
        snprintf(why, wn, "slider \"%s\": %g .. %g is outside the row's own bounds %g .. %g", line, v[1], v[2], rlo, rhi);
        return 0;
    }
    if (u[0] < u[1] || u[0] > u[2]) {
        snprintf(why, wn, "slider \"%s\": the default %g is not in %g .. %g", line, v[0], v[1], v[2]);
        return 0;
    }
#if MUT != 28
    if (set_value_of(cfg, idx, &sv) && fabs(sv * p - (double)u[0]) > 1e-6) {
#else
    if (0 && set_value_of(cfg, idx, &sv)) {         /* defect: two different defaults taken */
#endif
        snprintf(why, wn, "slider \"%s\": the default %g differs from the mod's set value %g (the set value is the default)", line,
                 v[0], sv);
        return 0;
    }
    nm = strstr(k_bm_tune_catalog[idx].full, "| ");
    nm = nm ? nm + 2 : k_bm_tune_catalog[idx].full;
    if (!text_plain(lab ? lab : nm, 1, 16)) {
        snprintf(why, wn, "slider \"%s\": %s", line, lab ? "the label must be 1..16 printable characters (no \" or \\)" :
                 "the row's name is longer than 16 characters: add \"label TEXT\"");
        return 0;
    }
    o->who = who;
    o->index = idx;
    o->decimals = d;
    o->min = (int32_t)u[1];
    o->max = (int32_t)u[2];
    o->step = (int32_t)u[3];
    o->def = (int32_t)u[0];
    o->kind = k_bm_tune_catalog[idx].type == BM_TUNE_INT && u[1] == 0 && u[2] == 1 ? BO3_TUNE_SLIDER_SWITCH : BO3_TUNE_SLIDER_VALUE;
    memset(&inf, 0, sizeof inf);
    inf.struct_size = (uint32_t)sizeof inf;
    o->applies = t_info(who, idx, &inf) == BM_TUNE_OK ? inf.applies : BM_TUNE_APPLIES_NEXT_USE;
    snprintf(o->label, sizeof o->label, "%s", lab ? lab : nm);
    slider_key(idx, o->key);
    return 1;
}

static double slider_value(const bo3_tune_slider *sl, int32_t units)
{
    double p = 1.0;
    for (uint32_t k = 0; k < sl->decimals; k++)
        p *= 10.0;
    return (double)units / p;
}

/* every slider of the mod: parsed, checked, its default applied as the mod's declaration, recorded; 0 with why (none recorded) */
static int sliders_decl(const recomp_cfg *cfg, td_host *who, char *why, size_t wn)
{
    size_t cnt = recomp_cfg_array_len(cfg, "bmashup.tune.sliders");
    long long ver = recomp_cfg_type_of(cfg, "bmashup.tune.version") == RCFG_INT ? recomp_cfg_int(cfg, "bmashup.tune.version", 0) : 0;
    uint32_t first = s_nsl, mine = 0;
#if MUT != 26
    if (ver != 3) {
#else
    if (ver < 1 || ver > 3) {                       /* defect: sliders under version 1 / 2 */
#endif
        snprintf(why, wn, "bmashup.tune.sliders needs [bmashup.tune] version = 3");
        return 0;
    }
    if (recomp_cfg_type_of(cfg, "bmashup.tune.sliders") != RCFG_ARRAY) {
        snprintf(why, wn, "bmashup.tune.sliders must be a list of strings");
        return 0;
    }
    for (uint32_t k = 0; k < s_nsl; k++)
        mine += s_sl[k].who == who;
    for (size_t k = 0; k < cnt; k++) {
        bo3_tune_slider o;
        const char *s = recomp_cfg_array_type(cfg, "bmashup.tune.sliders", k) == RCFG_STRING ?
                        recomp_cfg_array_string(cfg, "bmashup.tune.sliders", k, NULL) : NULL;
        int32_t rc;
        int ok = slider_parse(cfg, s, who, &o, why, wn);
        for (uint32_t j = first; ok && j < s_nsl; j++)
            if (s_sl[j].index == o.index || !strcmp(s_sl[j].key, o.key)) {
                snprintf(why, wn, "slider \"%s\": the row (or its settings key %s) has a slider already",
                         k_bm_tune_catalog[o.index].full, o.key);
                ok = 0;
            }
        if (ok && (mine + (s_nsl - first) >= BO3_TUNE_SLIDERS_PER_MOD || s_nsl == BO3_TUNE_SLIDERS_MAX)) {
            snprintf(why, wn, "at most %u sliders a mod (%u in all)", BO3_TUNE_SLIDERS_PER_MOD, BO3_TUNE_SLIDERS_MAX);
            ok = 0;
        }
        if (ok) {
            rc = t_set(who, o.index, slider_value(&o, o.def));
            if (rc == BM_TUNE_OK)
                s_st[o.index].decl = 1;             /* a declaration: checked again at the game's copy (exit 93 there) */
            else {
                snprintf(why, wn, "slider \"%s\" = %g: %s", k_bm_tune_catalog[o.index].full, slider_value(&o, o.def),
                         rc == BM_TUNE_CONFLICT ? "already set by another mod or plugin" : "refused");
                ok = 0;
            }
        }
        if (!ok) {
            s_nsl = first;                          /* this mod's sliders: none (the start stops anyway) */
            return 0;
        }
        s_sl[s_nsl++] = o;
        fprintf(stderr, "[TUNE] slider \"%s\" (%s): default %g, %g .. %g\n", k_bm_tune_catalog[o.index].full, o.key,
                slider_value(&o, o.def), slider_value(&o, o.min), slider_value(&o, o.max));
    }
    return 1;
}

uint32_t bo3_tune_slider_count(void) { return s_nsl; }

const bo3_tune_slider *bo3_tune_slider_at(uint32_t k) { return k < s_nsl ? &s_sl[k] : NULL; }

int32_t bo3_tune_slider_apply(uint32_t k, int32_t units)
{
    const bo3_tune_slider *sl;
    int32_t rc;
    if (k >= s_nsl)
        return BM_TUNE_BAD_ARG;
    sl = &s_sl[k];
    if (units < sl->min || units > sl->max)
        return BM_TUNE_OUT_OF_RANGE;
    rc = t_set(sl->who, sl->index, slider_value(sl, units));
    if (rc == BM_TUNE_OK)
        s_st[sl->index].decl = 1;
    fprintf(stderr, "[TUNE] slider \"%s\" = %g: %s\n", k_bm_tune_catalog[sl->index].full, slider_value(sl, units),
            rc == BM_TUNE_OK ? "set" : "REFUSED");
    return rc;
}

#if defined(BO3_TUNE_GAME) || defined(BO3_TUNE_PS_GLUE)
#include "bm_settings.h"

static void slider_changed(void *user, int32_t value)
{
    bo3_tune_slider_apply((uint32_t)(uintptr_t)user, value);
}

int bo3_tune_sliders_offer(const char *(*mod_of)(const td_host *who), char *why, size_t wn)
{
    if (why && wn)
        why[0] = 0;
    for (uint32_t k = 0; k < s_nsl; k++) {
        const bo3_tune_slider *sl = &s_sl[k];
        const char *mod = mod_of ? mod_of(sl->who) : NULL;
        bm_setting_decl d;
        bo3_ps_data_ext x;
        int32_t v = sl->def, rc;
        memset(&d, 0, sizeof d);
        memset(&x, 0, sizeof x);
        d.struct_size = (uint32_t)sizeof d;
        d.kind = sl->kind == BO3_TUNE_SLIDER_SWITCH ? BM_SETTING_BOOL : BM_SETTING_INT;
        d.key = sl->key;
        d.label = sl->label;
        d.min = sl->min;
        d.max = sl->max;
        d.step = sl->step;
        d.def = sl->def;
        d.scope = BM_SETTING_SCOPE_GLOBAL;
        x.decimals = sl->decimals;
        x.when = sl->applies == BM_TUNE_APPLIES_NEXT_RACE ? BO3_PS_WHEN_NEXT_RACE : BO3_PS_WHEN_AT_ONCE;
        x.fn = slider_changed;
        x.user = (void *)(uintptr_t)k;
        rc = bo3_ps_data_declare(sl->who, mod ? mod : "", &d, &x, &v);
        if (rc != BM_SETTINGS_OK) {
            snprintf(why, wn, "slider \"%s\": the MODS page refused it (bmashup.settings %d)", k_bm_tune_catalog[sl->index].full,
                     (int)rc);
            return 0;
        }
#if MUT != 27
        if (v != sl->def)                           /* the player's saved value wins over the default */
            bo3_tune_slider_apply(k, v);
#endif
    }
    return 1;
}
#endif

int bo3_tune_apply_decl(const char *text, size_t n, td_host *who, char *why, size_t wn)
{
    char err[200], *buf;
    recomp_cfg *cfg;
    int ok = 1;
    if (why && wn)
        why[0] = 0;
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
    for (size_t k = 0; ok && k < recomp_cfg_count(cfg); k++) {
        const char *key = recomp_cfg_key_at(cfg, k);
        if (strncmp(key, "bmashup.tune", 12) != 0 || (key[12] && key[12] != '.'))
            continue;
        if (strcmp(key, "bmashup.tune.version") && strcmp(key, "bmashup.tune.set") && strcmp(key, "bmashup.tune.sliders")) {
            snprintf(why, wn, "%s is not a key this build reads (bmashup.tune version 3: version, set, sliders)", key);
            ok = 0;
        }
    }
    if (ok && recomp_cfg_type_of(cfg, "bmashup.tune.set") != RCFG_NONE) {
        size_t cnt = recomp_cfg_array_len(cfg, "bmashup.tune.set");
        long long ver = recomp_cfg_type_of(cfg, "bmashup.tune.version") == RCFG_INT ? recomp_cfg_int(cfg, "bmashup.tune.version", 0) : 0;
        if (ver < 1 || ver > 3) {           /* GP-AITUNE1: version 2 = + the AI values and signed values; patch 130: 3 = + sliders */
            snprintf(why, wn, "bmashup.tune.version must be 1, 2 or 3");
            ok = 0;
        }
        for (size_t k = 0; ok && k < cnt; k++) {
            char line[300], *eq, *end;
            const char *s = recomp_cfg_array_type(cfg, "bmashup.tune.set", k) == RCFG_STRING ? recomp_cfg_array_string(cfg, "bmashup.tune.set", k, NULL) : NULL;
            uint32_t idx;
            double v;
            int32_t rc;
            if (!s || strlen(s) >= sizeof line || !(eq = strrchr(strcpy(line, s), '='))) {
                snprintf(why, wn, "bmashup.tune.set entry %u is not \"Group | Name = value\"", (unsigned)k);
                ok = 0;
                break;
            }
            *eq = 0;
            trim(line);
            trim(eq + 1);
            v = strtod(eq + 1, &end);
            if (end == eq + 1 || *end) {
                snprintf(why, wn, "\"%s\": the value \"%s\" is not a number", line, eq + 1);
                ok = 0;
                break;
            }
            if (t_find(who, line, &idx) != BM_TUNE_OK) {
                snprintf(why, wn, "\"%s\" is not a tuning value this build knows", line);
                ok = 0;
                break;
            }
#if MUT != 10
            if (ver < 2 && (idx >= AI_FIRST || v < 0.0)) {
#else
            if (ver < 2 && v < 0.0) {           /* defect: an AI value is taken under version 1 */
#endif
                snprintf(why, wn, "\"%s\" = %g needs [bmashup.tune] version = 2 (the AI values and negative values)", line, v);
                ok = 0;
                break;
            }
            rc = t_set(who, idx, v);
            if (rc == BM_TUNE_OK)
                s_st[idx].decl = 1;             /* v1.2: checked again at the game's copy; out of range there = exit 93 */
            fprintf(stderr, "[TUNE] \"%s\" = %g: %s\n", line, v, rc == BM_TUNE_OK ? "set" : "REFUSED");
            if (rc != BM_TUNE_OK) {
                snprintf(why, wn, "\"%s\" = %g: %s", line, v,
                         rc == BM_TUNE_UNSUPPORTED ? ((ai_flags(idx) & BM_TUNE_AI_UNREAD) ?
                             "never read by this game build (it would change nothing)" : "not verified on this game build") :
                         rc == BM_TUNE_OUT_OF_RANGE && is_sh(idx) ? "out of range (Effects/Shadow: Alpha Test 0 or 1, Opacity 0 .. 1, "
                             "Width / Length 0.5 .. 2, Soft Edge 0.05 .. 0.45)" :
                         rc == BM_TUNE_OUT_OF_RANGE ? (is_signed(idx) ?
                             "out of range (-16 .. 16 x the larger of the shipped and the game's value; whole numbers for counts)" :
                             "out of range (0 .. 16 x the shipped value; whole numbers for counts)") :
                         rc == BM_TUNE_CONFLICT ? "already set by another mod or plugin" : "refused");
                ok = 0;
            }
        }
    }
    if (ok && recomp_cfg_type_of(cfg, "bmashup.tune.sliders") != RCFG_NONE)
        ok = sliders_decl(cfg, who, why, wn);       /* main21 patch 130 */
    recomp_cfg_free(cfg);
    return ok;
}

#ifdef BO3_TUNE_GAME
#include "modfs.h"
#include "plugins.h"

extern ptrdiff_t g_xbox_mem_offset;
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

static int g_read32(void *u, uint32_t va, uint32_t *out)
{
    (void)u;
    if (!g_xbox_mem_offset || va < 0x10000u || va > 0x00800000u - 4)
        return 0;
    memcpy(out, (const void *)((uintptr_t)g_xbox_mem_offset + va), 4);
    return 1;
}

static int g_write32(void *u, uint32_t va, uint32_t v)
{
    (void)u;
    if (!g_xbox_mem_offset || va < 0x003B2360u || va > 0x00800000u - 4)   /* .data and above only */
        return 0;
    memcpy((void *)((uintptr_t)g_xbox_mem_offset + va), &v, 4);
    return 1;
}

static int g_strcmp_at(void *u, uint32_t va, const char *s)
{
    size_t n = strlen(s) + 1;
    (void)u;
    if (!g_xbox_mem_offset || va < 0x10000u || va > 0x00800000u - n)
        return 0;
    return memcmp((const void *)((uintptr_t)g_xbox_mem_offset + va), s, n) == 0;
}

static void decl_refused(uint32_t i, double value, double max)
{
    fprintf(stderr, "[TUNE] FATAL: a mod declares \"%s\" = %g; the game's own value is %g, the bound %g\n", k_bm_tune_catalog[i].full,
            value, as_double(i, s_st[i].game_raw), max);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: a mod's tuning values cannot be applied",
              "A mod declares in its mod.toml ([bmashup.tune]) \"%s\" = %g, above 16 x the game's own value %g.\n\n"
              "Turn the mod off, or fix its declaration.", k_bm_tune_catalog[i].full, value, as_double(i, s_st[i].game_raw));
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(93);
}

void bo3_bm_tune_init(void)
{
    static const bo3_tune_guest g = {g_read32, g_write32, g_strcmp_at, NULL};
    bo3_tune_set_decl_refused(decl_refused);
    uint32_t n = bo3_tune_configure(&g);
    fprintf(stderr, "[TUNE] bmashup.tune: %u of %u tuning values verified on this game build\n", (unsigned)n,
            (unsigned)BM_TUNE_CATALOG_N);
    bo3_plugins_service(BM_TUNE_SERVICE, BM_TUNE_VERSION, &s_api);
}

static int s_tok[BO3_MODFS_MAX_MODS];

void bo3_tune_game_apply(void)
{
    for (int i = 0; i < bo3_modfs_mod_count() && i < BO3_MODFS_MAX_MODS; i++) {
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
        if (!bo3_tune_apply_decl(text, n, (td_host *)&s_tok[i], why, sizeof why)) {
            free(text);
            fprintf(stderr, "[TUNE] FATAL: mod %s: %s\n", m->manifest.id, why);
            fflush(stderr);
            xbox_crash_log_flush(1000);
            bo3_fatal("Takedawn: a mod's tuning values cannot be applied",
                      "The mod \"%s\" declares in its mod.toml ([bmashup.tune]) a value this build cannot apply:\n%s\n\n"
                      "Turn the mod off, or fix its declaration.", m->manifest.id, why);
            fflush(stdout);
            fflush(stderr);
            xbox_crash_log_flush(1000);
            _Exit(93);
        }
        free(text);
    }
}

/* main21 patch 130: a slider's token -> its mod's id (s_tok[i] is mod i's) */
static const char *tok_mod(const td_host *who)
{
    const int *t = (const int *)(const void *)who;
    const bo3_mod *m;
    if (t < s_tok || t >= s_tok + BO3_MODFS_MAX_MODS || !(m = bo3_modfs_mod((int)(t - s_tok))))
        return NULL;
    return m->manifest.id;
}

void bo3_tune_game_sliders(void)
{
    char why[400];
    if (!bo3_tune_slider_count())
        return;
    if (!bo3_tune_sliders_offer(tok_mod, why, sizeof why)) {
        fprintf(stderr, "[TUNE] FATAL: %s\n", why);
        fflush(stderr);
        xbox_crash_log_flush(1000);
        bo3_fatal("Takedawn: a mod's tuning values cannot be applied",
                  "A mod declares in its mod.toml ([bmashup.tune] sliders) a slider the MODS page cannot show:\n%s\n\n"
                  "Turn the mod off, or fix its declaration.", why);
        fflush(stdout);
        fflush(stderr);
        xbox_crash_log_flush(1000);
        _Exit(93);
    }
    fprintf(stderr, "[TUNE] %u slider(s) on the MODS page\n", (unsigned)bo3_tune_slider_count());
}
#endif
