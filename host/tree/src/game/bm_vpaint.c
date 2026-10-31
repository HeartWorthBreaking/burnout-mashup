/* bm_vpaint.c - GP-VEH1 EXPERIMENTAL: the paint registry (bm_veh.h, contract CONTRACTS_CONTENT s3 "(veh v0.1)").
 *
 * A registered paint of a car has the index (the car's retail palette count) + j, j = its order among the car's active paints
 * (admission order, then name). The game carries the index as a signed byte (garage row +0x14, render object +0x59, vehicle
 * record +0x69); every site that would reduce or bound it is marked:
 *   sub_0018D0E0 (load clamp) -> bo3_veh_gen_paint_bound: a valid registered index is kept; the texture -> car map is set here
 *   sub_000303D0 (renderer, paint >= count) -> bo3_veh_gen_palette: the host palette resource of (car, j)
 *   sub_000BE140 (garage X) -> bo3_veh_gen_paint_next: retail selectable paints, then the registered ones
 *   sub_000BE1B0 (photo mirror) -> bo3_veh_gen_photo_paint; sub_000F9410 (photo draw) -> bo3_veh_gen_photo_palette
 *   sub_000BEB10 (confirm / preview) -> bo3_veh_gen_paint_confirm (and the sidecar commit)
 *   after a garage rows build -> bo3_veh_gen_rows (the session / saved / default paint restored into the rows)
 * Palette resources: guest CONTIGUOUS memory (the GPU resolves palette offsets below the arena's high-water mark into that
 * window: xboxrecomp nv2a_pb_exec.c dma_resolve), chunks of 64 units x 0x440 (0x40 D3D palette header + 256 x BGRA), allocated
 * at first use, never freed. Header = the in-file palette header (Common 0x00030001, Data, Lock 0); Data = the unit's data VA +
 * the delta the car's own palette 0 shows between its header + 0x40 and its Data word (checked: 0 or the window base).
 * Ramp paints: the entries where the car's palettes 0 and 1 differ are recoloured by their luminance between the authored lo
 * and hi colours (alpha kept); a car with one palette has no ramp -> paint 0 (logged). File paints: the authored 1024 bytes.
 * MUT=n: 41 a registered index clamped at load anyway   42 the renderer always palette 0   43 the cycle skips the registered
 *        44 the confirm reduces mod the photo count     45 the delta not applied (Data = the VA)
 *        46 the resident budget not checked             47 the ramp recolours every entry   48 the default ignored at restore
 *        49 the per-car limit not checked               50 rollback leaves the mod's paints active */
#include "bm_veh.h"

#include <ctype.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_guest.h"
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P18C
#define BO3_HOOKREQ_P18C 0   /* main21 patch 91: CMake option (default ON); stand-alone compiles (tests) keep the old rule */
#endif

#define PAINT_PREFIX "bmashup.paints"
#define UNIT 0x440u
#define CHUNK_UNITS 64u
#define REC0 0x0073F190u
#define REC_STRIDE 0x2470u
#define PREVIEW_SLOT 0x0055609Eu

typedef struct paint_reg {
    bo3_paint_entry e;
    int mod;
    char mod_id[65];
    int active;
    uint8_t *pal;                               /* FILE: 1024 B */
    uint32_t res;                               /* model palette resource (0 none yet, 1 failed) */
} paint_reg;
static paint_reg *s_p;
static uint32_t s_np, s_cap;
static struct { uint64_t car; int reg; } s_def[BO3_PAINT_DECL_MAX];
static uint32_t s_ndef;
static uint32_t (*s_alloc)(uint32_t, uint32_t);
static uint32_t s_chunk, s_chunk_used = CHUNK_UNITS, s_units;
static bo3_paint_store s_store;
static int s_have_store;

/* small maps */
#define TEXMAP 64u
static struct { uint32_t tex; uint64_t car; } s_tex[TEXMAP];
static uint32_t s_tex_next;
#define WMAP 8u
static struct { uint32_t photo, idx, w; uint64_t car; int reg; } s_wid[WMAP];   /* p4.3 fix 1: + (photo texture, index) key */
#define PHOTOS 1024u
static struct { uint32_t photo; int reg; uint32_t res; } s_ph[PHOTOS];
static uint32_t s_nph;
#define SESS 2048u
static struct { uint64_t car; int16_t paint; uint8_t used, player; char committed[112]; } s_sess[SESS];

extern uint32_t bo3_veh_stats(uint32_t w);
static _Atomic uint32_t s_pst[14];               /* this file's share of bo3_veh_stats 6..9, 12, 13 */
static void pst(uint32_t w) { atomic_fetch_add(&s_pst[w], 1); }
uint32_t bo3_vpaint_stats(uint32_t w) { return w < 14 ? atomic_load(&s_pst[w]) : 0; }

void bo3_veh_set_alloc(uint32_t (*a)(uint32_t, uint32_t)) { s_alloc = a; }
void bo3_paint_set_store(const bo3_paint_store *s)
{
    if (s) {
        s_store = *s;
        s_have_store = 1;
    } else {
        s_have_store = 0;
    }
}

static uint32_t rdg(uint32_t va)
{
    uint32_t v = 0;
    bo3_guest_rd32(va, &v);
    return v;
}
static uint8_t rd8(uint32_t va)
{
    uint8_t v = 0;
    bo3_guest_read(va, &v, 1);
    return v;
}
static uint64_t rd64g(uint32_t va) { return (uint64_t)rdg(va) | (uint64_t)rdg(va + 4u) << 32; }

void bo3_paint_reset_registry(void)
{
    for (uint32_t i = 0; i < s_np; i++)
        free(s_p[i].pal);
    free(s_p);
    s_p = NULL;
    s_np = s_cap = s_ndef = 0;
    s_chunk = 0;
    s_chunk_used = CHUNK_UNITS;
    s_units = 0;
    s_nph = 0;
    s_tex_next = 0;
    memset(s_tex, 0, sizeof s_tex);
    memset(s_wid, 0, sizeof s_wid);
    memset(s_sess, 0, sizeof s_sess);
    for (int i = 0; i < 14; i++)
        atomic_store(&s_pst[i], 0);
}

uint32_t bo3_paint_count(void)
{
    uint32_t n = 0;
    for (uint32_t i = 0; i < s_np; i++)
        n += (uint32_t)s_p[i].active;
    return n;
}

/* the active registered paints of a car in index order (registration order: admission order, then name) */
static uint32_t paints_of(uint64_t car, int *regs, uint32_t max)
{
    uint32_t n = 0;
    for (uint32_t i = 0; i < s_np; i++)
        if (s_p[i].active && s_p[i].e.car == car) {
            if (regs && n < max)
                regs[n] = (int)i;
            n++;
        }
    return n;
}

uint32_t bo3_paint_of_car(uint64_t car, uint32_t *first)
{
    int r[1] = {-1};
    uint32_t n = paints_of(car, r, 1);
    if (first)
        *first = r[0] >= 0 ? (uint32_t)r[0] : 0;
    return n;
}

static int reg_of(uint64_t car, uint32_t j)
{
    int regs[BO3_PAINT_PER_CAR];
    uint32_t n = paints_of(car, regs, BO3_PAINT_PER_CAR);
    return j < n && j < BO3_PAINT_PER_CAR ? regs[j] : -1;
}

void bo3_paint_drop_mod(int mod)
{
#if MUT == 50
    (void)mod;                                  /* defect: the refused mod's paints stay */
#else
    for (uint32_t i = 0; i < s_np; i++)
        if (s_p[i].mod == mod)
            s_p[i].active = 0;
    for (uint32_t i = 0; i < s_ndef; i++)
        if (s_def[i].reg >= 0 && s_p[s_def[i].reg].mod == mod)
            s_def[i].reg = -1;
#endif
}

void bo3_paint_drop_car(uint64_t car)
{
    for (uint32_t i = 0; i < s_np; i++)
        if (s_p[i].e.car == car)
            s_p[i].active = 0;
}

int bo3_paint_register(const bo3_paint_entry *e, int mod, const char *mod_id, const uint8_t *pal, char *why, size_t wn)
{
    paint_reg *r;
    if (s_np >= BO3_PAINT_DECL_MAX) {
        snprintf(why, wn, "paint %s: more than %u paints declared", e->name, (unsigned)BO3_PAINT_DECL_MAX);
        return 1;
    }
#if MUT != 49
    if (paints_of(e->car, NULL, 0) >= BO3_PAINT_PER_CAR) {
        snprintf(why, wn, "paint %s: its car already has %u registered paints (64 with the retail ones)", e->name,
                 (unsigned)BO3_PAINT_PER_CAR);
        return 1;
    }
#endif
    if (s_np == s_cap) {
        uint32_t nc = s_cap ? s_cap * 2u : 64u;
        paint_reg *p = (paint_reg *)realloc(s_p, nc * sizeof *p);
        if (!p) {
            snprintf(why, wn, "no memory");
            return 1;
        }
        s_p = p;
        s_cap = nc;
    }
    r = &s_p[s_np];
    memset(r, 0, sizeof *r);
    r->e = *e;
    r->mod = mod;
    snprintf(r->mod_id, sizeof r->mod_id, "%s", mod_id);
    r->active = 1;
    if (pal) {
        r->pal = (uint8_t *)malloc(1024);
        if (!r->pal) {
            snprintf(why, wn, "no memory");
            return 1;
        }
        memcpy(r->pal, pal, 1024);
    }
    s_np++;
    return 0;
}

int bo3_paint_set_default(uint64_t car, int mod, const char *paint, char *why, size_t wn)
{
    for (uint32_t i = 0; i < s_ndef; i++)
        if (s_def[i].car == car && s_def[i].reg >= 0) {
            snprintf(why, wn, "a second default paint for a car");
            return 1;
        }
    for (uint32_t i = 0; i < s_np; i++)
        if (s_p[i].active && s_p[i].mod == mod && s_p[i].e.car == car && !strcmp(s_p[i].e.name, paint)) {
            if (s_ndef >= BO3_PAINT_DECL_MAX)
                break;
            s_def[s_ndef].car = car;
            s_def[s_ndef].reg = (int)i;
            s_ndef++;
            return 0;
        }
    snprintf(why, wn, "default %s: not a paint this mod declares for that car", paint);
    return 1;
}

int bo3_paint_canonical(uint64_t car, uint32_t count, uint32_t p, char *out, size_t n)
{
    char ids[13];
    int r;
    bo3_car_dec(car, ids);
    if (p < count) {
        snprintf(out, n, "retail/%s/%u", ids, (unsigned)p);
        return 1;
    }
    r = reg_of(car, p - count);
    if (r < 0)
        return 0;
    snprintf(out, n, "%s/%s", s_p[r].mod_id, s_p[r].e.name);
    return 1;
}

int bo3_paint_index(uint64_t car, uint32_t count, const char *canon)
{
    char ids[13], pre[40];
    int regs[BO3_PAINT_PER_CAR];
    uint32_t n;
    bo3_car_dec(car, ids);
    snprintf(pre, sizeof pre, "retail/%s/", ids);
    if (!strncmp(canon, pre, strlen(pre))) {
        char *end = NULL;
        long v = strtol(canon + strlen(pre), &end, 10);
        return end && !*end && v >= 0 && (uint32_t)v < count ? (int)v : -1;
    }
    n = paints_of(car, regs, BO3_PAINT_PER_CAR);
    for (uint32_t j = 0; j < n && j < BO3_PAINT_PER_CAR; j++) {
        char c[112];
        snprintf(c, sizeof c, "%s/%s", s_p[regs[j]].mod_id, s_p[regs[j]].e.name);
        if (!strcmp(c, canon))
            return (int)(count + j);
    }
    return -1;
}

/* ---- palette units (contiguous guest memory, never freed) ---- */
static uint32_t unit_alloc(void)
{
#if MUT != 46
    if (s_units >= BO3_PAINT_RESIDENT)
        return 0;
#endif
    if (s_chunk_used >= CHUNK_UNITS) {
        uint32_t c = s_alloc ? s_alloc(UNIT * CHUNK_UNITS, 0x1000u) : 0;
        if (!c)
            return 0;
        s_chunk = c;
        s_chunk_used = 0;
    }
    s_units++;
    return s_chunk + UNIT * s_chunk_used++;
}

/* the Data delta of a texture's palette 0 (its header + 0x40 vs its Data word): 1 with *delta, 0 when unexpected */
static int pal_delta(uint32_t tex, uint32_t *delta, uint32_t *data0)
{
    uint32_t h0 = rdg(tex + 0x14u), d;
    if (!h0 || !bo3_guest_window(h0, 0x40u + 0x400u))
        return 0;
    d = rdg(h0 + 4u) - (h0 + 0x40u);
    if (d != 0u && d != 0x80000000u)            /* the VA itself, or the physical offset of a window address */
        return 0;
    *delta = d;
    *data0 = h0 + 0x40u;
    return 1;
}

static uint32_t lum(uint32_t bgra)
{
    uint32_t b = bgra & 0xFF, g = (bgra >> 8) & 0xFF, r = (bgra >> 16) & 0xFF;
    return 299u * r + 587u * g + 114u * b;     /* 0 .. 255000 */
}

/* build a palette from the texture's palettes: ramp (recolour entries that differ between palettes 0 and 1) or a file */
static int build(uint32_t tex, const paint_reg *r, uint8_t out[1024])
{
    uint32_t n = rd8(tex + 0x69u), h0 = rdg(tex + 0x14u), h1 = rdg(tex + 0x18u);
    uint32_t p0[256], p1[256], lo = 0xFFFFFFFFu, hi = 0;
    int ramp[256], nr = 0;
    if (r->e.kind == BO3_PAINT_FILE) {
        memcpy(out, r->pal, 1024);
        return 1;
    }
    if (n < 2 || !h0 || !h1 || !bo3_guest_read(h0 + 0x40u, p0, 1024) || !bo3_guest_read(h1 + 0x40u, p1, 1024))
        return 0;
    for (int i = 0; i < 256; i++) {
#if MUT == 47
        ramp[nr++] = i;                         /* defect: every entry recoloured (decals, lights too) */
#else
        if (p0[i] != p1[i])
            ramp[nr++] = i;
#endif
    }
    if (!nr)
        return 0;
    for (int k = 0; k < nr; k++) {
        uint32_t l = lum(p0[ramp[k]]);
        if (l < lo) lo = l;
        if (l > hi) hi = l;
    }
    memcpy(out, p0, 1024);
    for (int k = 0; k < nr; k++) {
        uint32_t c = p0[ramp[k]], l = lum(c), t = hi > lo ? (uint32_t)(((uint64_t)(l - lo) * 1024u) / (hi - lo)) : 1024u;
        uint32_t o = c & 0xFF000000u;
        for (int ch = 0; ch < 3; ch++) {          /* B G R from 0xRRGGBB */
            uint32_t a = (r->e.lo >> (8 * ch)) & 0xFF, b = (r->e.hi >> (8 * ch)) & 0xFF;
            uint32_t v = (a * (1024u - t) + b * t) / 1024u;
            o |= v << (8 * ch);
        }
        memcpy(out + 4 * ramp[k], &o, 4);
    }
    return 1;
}

/* a palette resource built from tex for paint r: 0 on failure (logged once per kind) */
static uint32_t make_res(uint32_t tex, const paint_reg *r, const char *what)
{
    uint8_t pal[1024];
    uint32_t delta = 0, d0 = 0, u, hdr[16];
    static int said_delta, said_build, said_mem;
    if (!pal_delta(tex, &delta, &d0)) {
        if (!said_delta++)
            fprintf(stderr, "[VEH] paint %s/%s (%s): the texture's palette 0 header is not the expected layout: paint 0 used\n",
                    r->mod_id, r->e.name, what);
        return 0;
    }
    if (!build(tex, r, pal)) {
        if (!said_build++)
            fprintf(stderr, "[VEH] paint %s/%s (%s): the texture has no paint ramp (one palette): paint 0 used\n", r->mod_id,
                    r->e.name, what);
        return 0;
    }
    u = unit_alloc();
    if (!u) {
        if (!said_mem++)
            fprintf(stderr, "[VEH] paint %s/%s (%s): no palette unit (resident budget %u or contiguous memory): paint 0 used\n",
                    r->mod_id, r->e.name, what, (unsigned)BO3_PAINT_RESIDENT);
        return 0;
    }
    memset(hdr, 0, sizeof hdr);
    hdr[0] = 0x00030001u;                       /* the in-file palette Common (bgvlib: every retail palette) */
#if MUT == 45
    hdr[1] = u + 0x40u;                         /* defect: the delta not applied */
#else
    hdr[1] = u + 0x40u + delta;
#endif
    if (!bo3_guest_write(u, hdr, 0x40u) || !bo3_guest_write(u + 0x40u, pal, 1024u))
        return 0;
    pst(6);
    if (bo3_vpaint_stats(6) <= 16u)
        fprintf(stderr, "[VEH] palette %s/%s (%s) created at 0x%08X (Data 0x%08X, delta 0x%X)\n", r->mod_id, r->e.name, what,
                (unsigned)u, (unsigned)(u + 0x40u + delta), (unsigned)delta);
    (void)d0;
    return u;
}

/* ---- maps ---- */
static void tex_map(uint32_t tex, uint64_t car)
{
    for (uint32_t i = 0; i < TEXMAP; i++)
        if (s_tex[i].tex == tex) {
            s_tex[i].car = car;
            return;
        }
    s_tex[s_tex_next].tex = tex;
    s_tex[s_tex_next].car = car;
    s_tex_next = (s_tex_next + 1u) % TEXMAP;
}

static uint64_t tex_car(uint32_t tex)
{
    for (uint32_t i = 0; i < TEXMAP; i++)
        if (s_tex[i].tex == tex)
            return s_tex[i].car;
    return 0;
}

static int sess_slot(uint64_t car, int make)
{
    uint32_t s = (uint32_t)((car * 0x9E3779B97F4A7C15ull) >> 40) & (SESS - 1u);
    for (uint32_t n = 0; n < SESS; n++, s = (s + 1u) & (SESS - 1u)) {
        if (s_sess[s].used && s_sess[s].car == car)
            return (int)s;
        if (!s_sess[s].used) {
            if (!make)
                return -1;
            s_sess[s].used = 1;
            s_sess[s].car = car;
            s_sess[s].paint = -1;
            return (int)s;
        }
    }
    return -1;
}

/* the car of a garage row (list + 12 r): class byte +0x11, nth byte +0x10 */
static uint64_t row_car(uint32_t row)
{
    int8_t cls = (int8_t)rd8(row + 0x11u), nth = (int8_t)rd8(row + 0x10u);
    if (cls < 0 || nth < 0)
        return 0;
    return bo3_vl_nth((uint32_t)cls, (uint32_t)nth);
}

static uint32_t photo_count(uint32_t row)
{
    uint32_t ph = rdg(row + 0xCu);
    return ph ? rd8(ph + 0x69u) : 0u;
}

static const char *owner_of(uint64_t car, char *buf, size_t n)
{
    int k = bo3_car_find(car);
    snprintf(buf, n, "%s", k < 0 ? "retail" : bo3_car_mod_name(bo3_car_mod_of((uint32_t)k)));
    return buf;
}

/* commit = 1: the confirm path (only a choice the player made with X is written); player = 1: the X cycle */
static void remember(uint64_t car, uint32_t count, int p, int commit)
{
    int s = sess_slot(car, 1);
    char canon[112], owner[80];
    if (s < 0)
        return;
    s_sess[s].paint = (int16_t)p;
    if (commit == 2)
        s_sess[s].player = 1;
    if (commit != 1 || !s_sess[s].player || !s_have_store || !bo3_paint_canonical(car, count, (uint32_t)p, canon, sizeof canon))
        return;
    if (!strcmp(s_sess[s].committed, canon))
        return;
    if (s_store.put && s_store.put(s_store.user, owner_of(car, owner, sizeof owner), car, canon)) {
        snprintf(s_sess[s].committed, sizeof s_sess[s].committed, "%s", canon);
        pst(8);
    }
}

/* the paint a car with registered paints shows (pc = its retail palette count): the player's choice this session, else the
 * saved one (sidecar), else the declared default; -1 = none (the game's own value stays). A saved paint that no longer
 * exists -> paint 0 (logged). The answer is cached in the session (not as a player choice: nothing is written for it). */
static int desired(uint64_t car, uint32_t pc)
{
    int s = sess_slot(car, 0), p = -1;
    char canon[112] = "";
    if (s >= 0 && s_sess[s].paint >= 0)
        return s_sess[s].paint;
    if (s_have_store && s_store.get) {
        char owner[80];
        if (s_store.get(s_store.user, owner_of(car, owner, sizeof owner), car, canon, sizeof canon)) {
            p = bo3_paint_index(car, pc, canon);
            if (p < 0) {
                char ids[13];
                bo3_car_dec(car, ids);
                fprintf(stderr, "[VEH] saved paint \"%s\" of %s is not available: paint 0 (retail)\n", canon, ids);
                p = 0;
            }
        }
    }
#if MUT != 48
    if (p < 0)
        for (uint32_t i = 0; i < s_ndef; i++)
            if (s_def[i].car == car && s_def[i].reg >= 0 && s_p[s_def[i].reg].active) {
                int regs[BO3_PAINT_PER_CAR];
                uint32_t n = paints_of(car, regs, BO3_PAINT_PER_CAR);
                for (uint32_t j = 0; j < n && j < BO3_PAINT_PER_CAR; j++)
                    if (regs[j] == s_def[i].reg)
                        p = (int)(pc + j);
            }
#endif
    if (p >= 0) {
        s = sess_slot(car, 1);
        if (s >= 0) {
            s_sess[s].paint = (int16_t)p;
            if (canon[0])
                snprintf(s_sess[s].committed, sizeof s_sess[s].committed, "%s", canon);
        }
    }
    return p;
}

/* ================= generated-code calls ================= */
uint32_t bo3_veh_gen_paint_bound(uint32_t rec, uint32_t tex, uint32_t cnt)
{
    uint64_t car;
    int8_t p;
    if (!s_np)
        return cnt;
    car = rd64g(rec + 0x1970u);
    tex_map(tex, car);
    p = (int8_t)rd8(rec + 0x69u);
    cnt &= 0xFFu;
#if MUT == 41
    return cnt;                                 /* defect: clamped anyway */
#else
    if (p >= (int8_t)cnt && reg_of(car, (uint32_t)(p - (int8_t)cnt)) >= 0)
        return (uint32_t)p + 1u;               /* no reduction: the registered paint stays */
    return cnt;
#endif
}

uint32_t bo3_veh_gen_palette(uint32_t tex, uint32_t paint)
{
    uint32_t base = rdg(tex + 0x14u), n;
    uint64_t car;
    int r;
#if MUT == 42
    return base;
#endif
#if BO3_HOOKREQ_P23
    {   /* main19 (patch 31, bmashup.paints): player 0's dynamic paint (index BM_P23_PAINTS_DYN_INDEX) first */
        extern uint32_t bo3_paints_dyn_palette(uint32_t tex, uint32_t paint);
        uint32_t dyn = bo3_paints_dyn_palette(tex, paint);
        if (dyn)
            return dyn;
    }
#endif
    if (!s_np || (int32_t)paint < 0)
        return base;
    n = rd8(tex + 0x69u);
    car = tex_car(tex);
    if (!car || paint < n || (r = reg_of(car, paint - n)) < 0)
        return base;
    if (s_p[r].res == 0) {
        uint32_t u = make_res(tex, &s_p[r], "model");
        s_p[r].res = u ? u : 1u;
        if (!u)
            pst(7);
    }
    if (s_p[r].res <= 1u)
        return base;
    pst(12);
    return s_p[r].res;
}

uint32_t bo3_veh_gen_paint_next(uint32_t list, uint32_t retail_next, uint32_t d)
{
    uint32_t r = rdg(list + 0x244u), row = list + 12u * r, n, k;
    uint64_t car;
    int8_t p0;
    uint32_t rec = REC0 + (uint32_t)(int32_t)(int8_t)rd8(PREVIEW_SLOT) * REC_STRIDE;
    if (!s_np)
        return retail_next;
    car = row_car(row);
    k = car ? paints_of(car, NULL, 0) : 0;
    if (!k)
        return retail_next;
    n = rd64g(rec + 0x1970u) == car ? rd8(rdg(rdg(rec + 0x50u) + 0x60u) + 0x69u) : photo_count(row);
    if (k > BO3_PAINT_PER_CAR)
        k = BO3_PAINT_PER_CAR;
    p0 = (int8_t)rd8(row + 0x14u);
#if MUT == 43
    (void)n; (void)d; (void)p0;
    return retail_next;
#else
    {
        uint32_t next;
        if (p0 >= 0 && (uint32_t)p0 + 1u < d)
            next = (uint32_t)p0 + 1u;
        else if (p0 >= 0 && (uint32_t)p0 + 1u == d)
            next = n;                           /* after the last retail selectable: the first registered */
        else if (p0 >= (int8_t)n && (uint32_t)(p0 - (int8_t)n) + 1u < k)
            next = (uint32_t)p0 + 1u;
        else
            next = 0;
        remember(car, n, (int)next, 2);          /* the player's choice (committed at the confirm) */
        return next;
    }
#endif
}

/* p4.3 fix 1: the photo map is keyed by (photo texture, paint index): the garage draws its car photos as per-frame draw nodes
 * built by sub_000BCBA0 (sub_000F9320, draw callback sub_000F9410), so the object sub_000F9410 receives is not the list's
 * widget (+0x1EC / +0x1F0) + 0x20; the widget stays a second key (sub_000BE1B0's preview widget). Same texture + same index
 * with two different registered paints (two visible rows sharing a donor photo) -> the last row drawn wins (documented). */
static void photo_map(uint32_t photo, uint32_t idx, uint32_t w, uint64_t car, int reg)
{
    uint32_t slot = WMAP;
#if MUT == 51
    photo = 0;                                  /* defect: the p4.3 rule (the widget key only) */
#endif
    for (uint32_t i = 0; i < WMAP && slot == WMAP; i++)
        if (photo ? (s_wid[i].photo == photo && s_wid[i].idx == idx) : (s_wid[i].w == w && !s_wid[i].photo))
            slot = i;
    for (uint32_t i = 0; i < WMAP && slot == WMAP; i++)
        if (!s_wid[i].photo && !s_wid[i].w)
            slot = i;
    if (slot == WMAP) {                         /* full: the oldest goes (round robin) */
        static uint32_t rr;
        slot = rr++ % WMAP;
    }
    s_wid[slot].photo = photo;
    s_wid[slot].idx = idx;
    s_wid[slot].w = w;
    s_wid[slot].car = car;
    s_wid[slot].reg = reg;
}

/* the row's registered paint (or -1): p = the row byte, pc = its photo's palette count */
static int row_reg(uint32_t row, uint64_t *car_out, int8_t *p_out)
{
    uint32_t pc = photo_count(row);
    uint64_t car = row_car(row);
    int8_t p = (int8_t)rd8(row + 0x14u);
    *car_out = car;
    *p_out = p;
    if (!car || p < (int8_t)pc)
        return -1;
    return reg_of(car, (uint32_t)(p - (int8_t)pc));
}

uint32_t bo3_veh_gen_photo_paint(uint32_t list, uint32_t retail)
{
    uint32_t r = rdg(list + 0x244u), row = list + 12u * r;
    uint64_t car;
    int8_t p;
    int reg;
    if (!s_np || (reg = row_reg(row, &car, &p)) < 0)
        return retail;
    photo_map(rdg(row + 0xCu), (uint32_t)(uint8_t)p, rdg(list + (r == 0 ? 0x1ECu : 0x1F0u)), car, reg);
    return (uint32_t)(uint8_t)p;
}

/* sub_000BCBA0 (the garage list draw, list +0x234 == 4): each row's photo node gets paint = row byte % min(palettes, 6), so a
 * registered paint (index >= the palette count) wrapped to a retail palette (crimson 6 -> 0, gold 7 -> 1) and never reached
 * sub_000F9410's registered path: p4.3 open item 1. row = the list row (edi - 0x12 at 0xBCCE7). */
uint32_t bo3_veh_gen_photo_row(uint32_t row, uint32_t retail)
{
    uint64_t car;
    int8_t p;
    int reg;
    if (!s_np || (reg = row_reg(row, &car, &p)) < 0)
        return retail;
#if MUT == 53
    return retail;                              /* defect: the p4.3 wrap (registered index -> retail palette) */
#endif
    photo_map(rdg(row + 0xCu), (uint32_t)(uint8_t)p, 0, car, reg);
    return (uint32_t)(uint8_t)p;
}

uint32_t bo3_veh_gen_photo_palette(uint32_t photo, uint32_t paint, uint32_t widget)
{
    uint32_t pc = rd8(photo + 0x69u), base = rdg(photo + 0x14u);
    int reg = -1;
    if ((int32_t)paint >= 0 && paint < pc && paint < 8u)
        return rdg(photo + 0x14u + 4u * paint);   /* the game's own read */
    if (!s_np)
        return base;
    for (uint32_t i = 0; i < WMAP; i++)          /* p4.3 fix 1: the photo texture drawn + the index */
        if (s_wid[i].photo && s_wid[i].photo == photo && s_wid[i].idx == paint)
            reg = s_wid[i].reg;
#if MUT != 52
    if (reg < 0)                                 /* (the p4.3 rule as a second key: the widget + 0x20) */
#else
    if (0)                                       /* defect: no fallback key, and */
#endif
        for (uint32_t i = 0; i < WMAP; i++)
            if (s_wid[i].w && s_wid[i].w + 0x20u == widget)
                reg = s_wid[i].reg;
    if (reg < 0) {
        static int said;
        if (!said++)
            fprintf(stderr, "[VEH] photo 0x%08X drawn with paint %u (>= its %u palettes) from object 0x%08X: no registered paint "
                    "of a car known for it: palette 0\n", (unsigned)photo, (unsigned)paint, (unsigned)pc, (unsigned)widget);
        return base;
    }
    if (!s_p[reg].active)
        return base;
    if (s_p[reg].e.kind == BO3_PAINT_FILE)
        return base;                            /* contract s3: file paints show photo palette 0 */
    for (uint32_t i = 0; i < s_nph; i++)
        if (s_ph[i].photo == photo && s_ph[i].reg == reg)
            return s_ph[i].res > 1u ? (pst(13), s_ph[i].res) : base;
    if (s_nph < PHOTOS) {
        uint32_t u = make_res(photo, &s_p[reg], "photo");
        s_ph[s_nph].photo = photo;
        s_ph[s_nph].reg = reg;
        s_ph[s_nph].res = u ? u : 1u;
        s_nph++;
        if (u) {
            pst(13);
            return u;
        }
        pst(7);
    }
    return base;
}

uint32_t bo3_veh_gen_paint_confirm(uint32_t row, uint32_t retail)
{
    uint64_t car;
    uint32_t pc;
    int8_t p;
    if (!s_np)
        return retail;
    car = row_car(row);
    if (!car || !paints_of(car, NULL, 0))
        return retail;
    pc = photo_count(row);
#if MUT == 44
    (void)p;
    remember(car, pc, (int)retail, 1);
    return retail;
#else
    {   /* the car's paint (player / saved / default); the row byte follows it so the X cycle starts there */
        int d = desired(car, pc);
        uint8_t b;
        if (d < 0)
            return retail;
        b = (uint8_t)d;
        p = (int8_t)rd8(row + 0x14u);
        if (p != (int8_t)b)
            bo3_guest_write(row + 0x14u, &b, 1);
        remember(car, pc, d, 1);
        return (uint32_t)b;
    }
#endif
}

/* sub_000BEB10 while the series list animates (states 3 / 4: the game answers 0): the car of row r of the SECOND list (the
 * series being shown) gets its paint, so the preview shows it from the start */
uint32_t bo3_veh_gen_paint_anim(uint32_t list, uint32_t r)
{
    uint32_t row;
    uint64_t car;
    int d;
    if (!s_np || r >= BO3_CAR_ROWS)
        return 0;
    row = list + 0xF0u + 12u * r;
    car = row_car(row);
    if (!car || !paints_of(car, NULL, 0))
        return 0;
    d = desired(car, photo_count(row));
    return d > 0 ? (uint32_t)d : 0u;
}

/* both row lists of the garage list object: the first (rows at +0x0C, count +0x248) and, while a series change animates,
 * the second (rows at +0xFC, count +0x24C; sub_000BEA70 / BEAE0 read it in states 3 / 4) */
static void rows_of(uint32_t base, uint32_t rows);
void bo3_veh_gen_rows(uint32_t list)
{
    if (!s_np)
        return;
    rows_of(list, rdg(list + 0x248u));
    rows_of(list + 0xF0u, rdg(list + 0x24Cu));
}

static void rows_of(uint32_t list, uint32_t rows)
{
    if (rows > BO3_CAR_ROWS)
        rows = BO3_CAR_ROWS;
    for (uint32_t r = 0; r < rows; r++) {
        uint32_t row = list + 12u * r, pc;
        uint64_t car = row_car(row);
        int p;
        if (!car || !paints_of(car, NULL, 0))
            continue;
        pc = photo_count(row);
        p = desired(car, pc);
        if (p < 0)
            continue;
        {
            uint8_t b = (uint8_t)p;
            bo3_guest_write(row + 0x14u, &b, 1);
            pst(9);
        }
    }
}

/* ================= [bmashup.paints] ================= */
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

static int hex6(const char *s, uint32_t *v)
{
    char *end = NULL;
    unsigned long x;
    if (strlen(s) != 6)
        return 0;
    for (int i = 0; i < 6; i++)
        if (!isxdigit((unsigned char)s[i]))
            return 0;
    x = strtoul(s, &end, 16);
    *v = (uint32_t)x;
    return end && !*end;
}

static const char *astr(recomp_cfg *cfg, const char *key, size_t i)
{
    return recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
}

void bo3_paint_decl_free(bo3_paint_decl *d)
{
    if (d) {
        free(d->e);
        memset(d, 0, sizeof *d);
    }
}

int bo3_paint_parse(const char *text, size_t n, bo3_paint_decl *out, char *why, size_t wn)
{
    char err[200], *buf;
    size_t plen = strlen(PAINT_PREFIX);
    recomp_cfg *cfg;
    int ok = 1;
    long na = 0, nd = 0;
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
        if (strncmp(k, PAINT_PREFIX, plen) || (k[plen] && k[plen] != '.'))
            continue;
        out->present = 1;
        if (strcmp(k, PAINT_PREFIX ".version") && strcmp(k, PAINT_PREFIX ".add") && strcmp(k, PAINT_PREFIX ".default")) {
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 1: version, add, default; livery textures per "
                     "paint are not part of version 1)", k, PAINT_PREFIX);
            ok = 0;
        }
    }
    if (ok && out->present && (recomp_cfg_type_of(cfg, PAINT_PREFIX ".version") != RCFG_INT ||
                               recomp_cfg_int(cfg, PAINT_PREFIX ".version", 0) != 1)) {
        snprintf(why, wn, "%s.version must be 1", PAINT_PREFIX);
        ok = 0;
    }
    if (ok && out->present) {
        na = recomp_cfg_type_of(cfg, PAINT_PREFIX ".add") == RCFG_ARRAY ? (long)recomp_cfg_array_len(cfg, PAINT_PREFIX ".add") : -1;
        nd = recomp_cfg_type_of(cfg, PAINT_PREFIX ".default") == RCFG_NONE ? 0 :
             recomp_cfg_type_of(cfg, PAINT_PREFIX ".default") == RCFG_ARRAY ? (long)recomp_cfg_array_len(cfg, PAINT_PREFIX ".default") : -1;
        if (na <= 0 || nd < 0 || nd > 64) {
            snprintf(why, wn, "%s.add must be a list of \"<name> = <car> | ramp RRGGBB RRGGBB\" or \"... | file <path>\" "
                     "(default: a list of at most 64 \"<car> = <name>\")", PAINT_PREFIX);
            ok = 0;
        } else if (na > (long)BO3_PAINT_DECL_MAX) {
            snprintf(why, wn, "%s.add lists %ld paints; at most %u", PAINT_PREFIX, na, (unsigned)BO3_PAINT_DECL_MAX);
            ok = 0;
        } else if (!(out->e = (bo3_paint_entry *)calloc((size_t)na, sizeof *out->e))) {
            snprintf(why, wn, "no memory");
            ok = 0;
        }
        out->cap = ok ? (uint32_t)na : 0;
    }
    for (long i = 0; ok && i < na; i++) {
        char a[64], b[200], car[96], def[120];
        bo3_paint_entry *e = &out->e[i];
        if (!split(astr(cfg, PAINT_PREFIX ".add", (size_t)i), '=', a, sizeof a, b, sizeof b) || !local_ok(a) ||
            !split(b, '|', car, sizeof car, def, sizeof def)) {
            snprintf(why, wn, "%s.add[%ld] is not \"<name [a-z0-9_.-]> = <car> | <definition>\"", PAINT_PREFIX, i);
            ok = 0;
            break;
        }
        for (uint32_t j = 0; j < out->n; j++)
            if (!strcmp(out->e[j].name, a)) {
                snprintf(why, wn, "%s.add names %s twice", PAINT_PREFIX, a);
                ok = 0;
            }
        if (!ok)
            break;
        strcpy(e->name, a);
        snprintf(e->car_ref, sizeof e->car_ref, "%s", car);
        if (!strncmp(def, "ramp ", 5)) {
            char h[16], l[16];
            if (sscanf(def + 5, "%15s %15s", h, l) != 2 || !hex6(h, &e->hi) || !hex6(l, &e->lo)) {
                snprintf(why, wn, "%s.add: %s: \"ramp RRGGBB RRGGBB\" (hex colours, the bright end first)", PAINT_PREFIX, a);
                ok = 0;
                break;
            }
            e->kind = BO3_PAINT_RAMP;
        } else if (!strncmp(def, "file ", 5)) {
            const char *f = def + 5;
            while (*f == ' ')
                f++;
            if (!*f || strlen(f) >= sizeof e->file || strstr(f, "..") || f[0] == '/' || f[0] == '\\' || strchr(f, ':')) {
                snprintf(why, wn, "%s.add: %s: \"file <path inside the mod's files folder>\"", PAINT_PREFIX, a);
                ok = 0;
                break;
            }
            snprintf(e->file, sizeof e->file, "%s", f);
            e->kind = BO3_PAINT_FILE;
        } else {
            snprintf(why, wn, "%s.add: %s: the definition must be \"ramp ...\" or \"file ...\" (version 1 knows no other kind)",
                     PAINT_PREFIX, a);
            ok = 0;
            break;
        }
        out->n = (uint32_t)i + 1;
    }
    for (long i = 0; ok && i < nd; i++) {
        char a[96], b[64];
        uint64_t id = 0;
        if (!split(astr(cfg, PAINT_PREFIX ".default", (size_t)i), '=', a, sizeof a, b, sizeof b) || !local_ok(b) ||
            !bo3_car_enc(a, &id) || strlen(a) < 5 || strlen(a) > 12) {
            snprintf(why, wn, "%s.default[%ld] is not \"<VEHICLE ID> = <paint name>\"", PAINT_PREFIX, i);
            ok = 0;
            break;
        }
        out->def[out->ndef].car = id;
        snprintf(out->def[out->ndef].paint, sizeof out->def[0].paint, "%s", b);
        out->ndef++;
    }
    recomp_cfg_free(cfg);
    if (!ok)
        bo3_paint_decl_free(out);
    return ok;
}

static int cmp_name(const void *a, const void *b)
{
    return strcmp(((const bo3_paint_entry *)a)->name, ((const bo3_paint_entry *)b)->name);
}

/* a car reference: VEHICLEID, retail/VEHICLEID, or <mod-id>/<vehicleid lower> (*owner_id set then) */
static int car_ref(const char *ref, uint64_t *id, char *owner_id, size_t on)
{
    const char *sl = strchr(ref, '/');
    char up[16];
    owner_id[0] = 0;
    if (!sl) {
        snprintf(up, sizeof up, "%s", ref);
    } else {
        size_t l = (size_t)(sl - ref);
        if (l >= on || strlen(sl + 1) >= sizeof up)
            return 0;
        memcpy(owner_id, ref, l);
        owner_id[l] = 0;
        snprintf(up, sizeof up, "%s", sl + 1);
        if (!strcmp(owner_id, "retail"))
            owner_id[0] = 0;
    }
    for (char *p = up; *p; p++)
        *p = (char)toupper((unsigned char)*p);
    return strlen(up) >= 5 && strlen(up) <= 12 && bo3_car_enc(up, id);
}

/* main21 patch 91 (open-list item 14, the colour picker): a paint entry whose car is "*" is registered for EVERY retail race car
 * (the game's career table, 67 cars: bo3_paint_set_retail), in that table's order, with one name - so a single palette mod gives
 * every car the same extra paints in the car-select paint cycle (the registry's photo palettes paint the thumbnails). A car that
 * reaches the per-car limit refuses the mod as before; a ramp on a car with one palette is that car's paint 0 (logged, as before).
 * MUT 54: "*" accepted (nothing registered) without a retail source  55: only the first retail car registered */
#if BO3_HOOKREQ_P18C
static uint32_t (*s_retail_n)(void);
static uint64_t (*s_retail_at)(uint32_t i);
#endif
void bo3_paint_set_retail(uint32_t (*count)(void), uint64_t (*at)(uint32_t i))
{
#if BO3_HOOKREQ_P18C
    s_retail_n = count;
    s_retail_at = at;
#else
    (void)count;
    (void)at;
#endif
}

int bo3_paint_declare_mod(int mod, const char *mod_id, const char *text, size_t n, bo3_paint_car_fn car_known,
                          bo3_paint_file_fn file, int (*requires)(const char *owner_mod_id), char *why, size_t wn)
{
    bo3_paint_decl d;
    uint32_t first = s_np, nwild = 0;
    uint8_t pal[1024];
    if (!bo3_paint_parse(text, n, &d, why, wn))
        return 0;
    if (!d.present)
        return 1;
    qsort(d.e, d.n, sizeof d.e[0], cmp_name);  /* contract s1: admission order, then name */
    for (uint32_t i = 0; i < d.n; i++) {
        bo3_paint_entry *e = &d.e[i];
        char owner[80];
        int known;
#if BO3_HOOKREQ_P18C
        if (!strcmp(e->car_ref, "*")) {
            uint32_t nr = s_retail_n && s_retail_at ? s_retail_n() : 0u, k;
#if MUT != 54
            if (!nr) {
                snprintf(why, wn, "paint %s: \"*\" (every retail race car) is not available here", e->name);
                goto fail;
            }
#endif
            if (e->kind == BO3_PAINT_FILE && !(file && file(mod, e->file, pal))) {
                snprintf(why, wn, "paint %s: the mod has no file %s of exactly 1024 bytes (256 x B G R A)", e->name, e->file);
                goto fail;
            }
#if MUT == 55
            nr = nr ? 1u : 0u;
#endif
            for (k = 0; k < nr; k++) {
                bo3_paint_entry c = *e;
                if (!(c.car = s_retail_at(k)))
                    continue;
                snprintf(c.car_ref, sizeof c.car_ref, "*");
                if (bo3_paint_register(&c, mod, mod_id, c.kind == BO3_PAINT_FILE ? pal : NULL, why, wn))
                    goto fail;
            }
            nwild++;
            continue;
        }
#endif
        if (!car_ref(e->car_ref, &e->car, owner, sizeof owner)) {
            snprintf(why, wn, "paint %s: \"%s\" is not a car reference (VEHICLEID, retail/VEHICLEID or <mod-id>/<car>)",
                     e->name, e->car_ref);
            goto fail;
        }
        known = car_known ? car_known(e->car) : -2;
        if (known == -2) {
            snprintf(why, wn, "paint %s: the car %s is neither a retail race car nor a car of an admitted mod", e->name,
                     e->car_ref);
            goto fail;
        }
        if (owner[0] && strcmp(owner, mod_id) && !(requires && requires(owner))) {
            snprintf(why, wn, "paint %s: the car %s belongs to mod %s, which is not in this mod's requires_mods", e->name,
                     e->car_ref, owner);
            goto fail;
        }
        if (known >= 0 && known != mod && !owner[0]) {
            snprintf(why, wn, "paint %s: %s is another mod's car: write it as <mod-id>/<car> and require that mod", e->name,
                     e->car_ref);
            goto fail;
        }
        if (e->kind == BO3_PAINT_FILE && !(file && file(mod, e->file, pal))) {
            snprintf(why, wn, "paint %s: the mod has no file %s of exactly 1024 bytes (256 x B G R A)", e->name, e->file);
            goto fail;
        }
        if (bo3_paint_register(e, mod, mod_id, e->kind == BO3_PAINT_FILE ? pal : NULL, why, wn))
            goto fail;
    }
    for (uint32_t i = 0; i < d.ndef; i++)
        if (bo3_paint_set_default(d.def[i].car, mod, d.def[i].paint, why, wn))
            goto fail;
    fprintf(stderr, "[VEH] mod %s registers %u paint(s)%s%s\n", mod_id, (unsigned)d.n, d.ndef ? " + defaults" : "",
            nwild ? " (some for every retail race car: \"*\")" : "");
    bo3_paint_decl_free(&d);
    return 1;
fail:
    for (uint32_t i = first; i < s_np; i++)    /* rollback: this mod's registrations of this call */
        s_p[i].active = 0;
    bo3_paint_drop_mod(mod);
    bo3_paint_decl_free(&d);
    return 0;
}

/* ================= the game build ================= */
#ifdef BO3_CARS_GAME
#include "modfs.h"
#include "bm_progress.h"

extern ptrdiff_t g_xbox_mem_offset;
extern uint32_t xbox_ContiguousAlloc(uint32_t size, uint32_t alignment);
int bo3_cc_progress_location(char *dir, size_t dn, char *prof, size_t pn);   /* bm_tracks_progress.c */

static const char *g_text;
static size_t g_n;

static int game_car_known(uint64_t id)
{
    int m;
    for (uint32_t j = 0; j < BO3_CAR_STATIC_N; j++)
        if (((uint64_t)rdg(BO3_CAR_STATIC_VA + 8u * j) | (uint64_t)rdg(BO3_CAR_STATIC_VA + 8u * j + 4u) << 32) == id)
            return -1;
    m = bo3_car_declared_mod(id);
    return m >= 0 ? m : -2;
}

static int game_file(int mod, const char *rel, uint8_t *buf)
{
    const bo3_mod *m = bo3_modfs_mod(mod);
    char path[BO3_MODFS_PATH_MAX + 120];
    FILE *f;
    size_t r;
    int extra;
    if (!m)
        return 0;
    snprintf(path, sizeof path, "%s\\files\\%s", m->folder, rel);
    f = fopen(path, "rb");
    if (!f)
        return 0;
    r = fread(buf, 1, 1024, f);
    extra = fgetc(f) != EOF;
    fclose(f);
    return r == 1024 && !extra;
}

static int game_requires(const char *owner)
{
    return bo3_veh_requires(g_text, g_n, owner);
}

#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
extern uint32_t xbox_ContiguousAllocHigh(uint32_t size, uint32_t alignment);   /* MEM256: the high zone */
#endif
static uint32_t game_alloc(uint32_t size, uint32_t align)
{
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    return xbox_ContiguousAllocHigh(size, align);   /* MEM256: the high zone */
#else
    return xbox_ContiguousAlloc(size, align);
#endif
}

/* the sidecar: <save dir>/bmashup/progress/<folder>/Profile 1 veh.bmprog (kind VEHICLE) */
static bm_prog *s_vs;
static int s_vs_tried;

static int vs_open(void)
{
    char dir[1400], prof[400];
    bm_prog_report r;
    if (s_vs)
        return bm_prog_writable(s_vs) ? 1 : 2;
    if (s_vs_tried)
        return 0;
    if (!bo3_cc_progress_location(dir, sizeof dir, prof, sizeof prof))
        return 0;                               /* no profile folder yet: retried at the next use */
    s_vs_tried = 1;
    bm_prog_open(bm_prog_io_native(), dir, "Profile 1 veh", prof, 0, &s_vs, &r);
    fprintf(stderr, "[VEH] paint sidecar %s/Profile 1 veh.bmprog: %s (%u records%s%s)\n", dir, bm_prog_status_name(r.status),
            (unsigned)r.records, r.why[0] ? "; " : "", r.why);
    return s_vs ? (bm_prog_writable(s_vs) ? 1 : 2) : 0;
}

static int vs_get(void *u, const char *owner, uint64_t car, char *canon, size_t n)
{
    bm_prog_key k;
    bm_prog_vehicle v;
    char ids[13];
    (void)u;
    if (!vs_open())
        return 0;
    bo3_car_dec(car, ids);
    if (bm_prog_key_make(&k, BM_PROG_VEHICLE, owner, ids) != BM_PROG_OK || bm_prog_get_vehicle(s_vs, &k, &v) != BM_PROG_OK)
        return 0;
    snprintf(canon, n, "%s", v.paint);
    return 1;
}

static int vs_put(void *u, const char *owner, uint64_t car, const char *canon)
{
    bm_prog_key k;
    bm_prog_vehicle v;
    char ids[13];
    (void)u;
    if (vs_open() != 1)
        return 0;
    bo3_car_dec(car, ids);
    memset(&v, 0, sizeof v);
    snprintf(v.paint, sizeof v.paint, "%s", canon);
    if (bm_prog_key_make(&k, BM_PROG_VEHICLE, owner, ids) != BM_PROG_OK || bm_prog_put_vehicle(s_vs, &k, "", &v) != BM_PROG_OK ||
        bm_prog_commit(s_vs, 0) != BM_PROG_OK)
        return 0;
    return 1;
}

/* main21 patch 91: the retail race cars = the career table BO3_CAR_STATIC_VA (u64 x 67, .rdata) */
static uint32_t game_retail_n(void) { return BO3_CAR_STATIC_N; }
static uint64_t game_retail_at(uint32_t i)
{
    return i < BO3_CAR_STATIC_N ? ((uint64_t)rdg(BO3_CAR_STATIC_VA + 8u * i) | (uint64_t)rdg(BO3_CAR_STATIC_VA + 8u * i + 4u) << 32) : 0;
}

int bo3_paint_game_declare_mod(int mod, const char *mod_id, const char *text, size_t n, char *why, size_t wn)
{
    static int init;
    if (!init) {
        bo3_paint_store st_ = {vs_get, vs_put, NULL};
        init = 1;
        bo3_paint_set_retail(game_retail_n, game_retail_at);   /* main21 patch 91 */
        bo3_veh_set_alloc(game_alloc);
        bo3_paint_set_store(&st_);
    }
    g_text = text;
    g_n = n;
    return bo3_paint_declare_mod(mod, mod_id, text, n, game_car_known, game_file, game_requires, why, wn);
}
#endif
