/*
 * bm_paints_svc.c - main19 (platform 0.1.9, hook request P2 item I, patch 31): "bmashup.paints" v1 (include/bmashup_paints.h),
 * the plugin face of the paint registry (bm_vpaint.c). Design gp\hookreq\HOOK_REQUEST_DESIGN.md I, sites
 * gp\hookreq\p23\SITES_VERIFIED.md s7 (re-checked: tests\p23\step0_c_out.txt).
 *
 * How the car shows the dynamic paint (no new mark in the game code):
 *   - the renderer sub_000303D0 reads the render entity's SIGNED palette index E + 0x59 (0x3053D) and, when it is >= the
 *     texture's palette count, asks the registry's mark bo3_veh_gen_palette (bm_vpaint.c) for the palette resource; that
 *     function asks this file first (bo3_paints_dyn_palette) for index BM_P23_PAINTS_DYN_INDEX (127);
 *   - the ap_update writer (player 0's car update, game thread) sets E + 0x59 = 127 on player 0's own render entity while the
 *     paint is wanted (E = MEM32(V + 0xCC0), V = player 0's physics vehicle: the player pool entry whose + 0x13F4 is the racer
 *     0x73A1D0), and puts the saved index back after factory() / release() (only if E + 0x59 still holds 127). AI / traffic
 *     entities are never written, so they never reach index 127.
 *   - the palette: the texture's palette 0 with the BODY entries (those where palettes 0 and 1 differ: the registry's ramp
 *     rule) recoloured by brightness between 30 % of the colour and the colour, alpha kept; header as the registry
 *     (Common 0x00030001, Data = unit + 0x40 + the delta the car's palette 0 shows). Units 0x440 B in the guest high zone.
 *   - publish: a change (set_colour, another texture) is written when the renderer next asks: by default into the OTHER unit
 *     and the car switches to it (the backend sees a new palette resource: re-bind); BM_P23_PAINTS_LIVE_INPLACE 1 edits the
 *     unit the car uses (probe PR-A2 decides whether the backend shows that without a re-bind).
 * Start census (once, lazily on the game thread): the renderer's index / count reads (0x3053D `0f be 4f 59`, 0x3054C
 * `0f b6 50 69`) and the player car's vtable word; a mismatch -> every call answers UNAVAILABLE.
 * BO3_HOOKREQ_P23 == 0: every call answers UNAVAILABLE and nothing is subscribed or written.
 * Patch 41 (probe PR-A2): the entity is E = racer 0x73A1D0 + 0x10 (the object the renderer's palette bind reads, p23_a2), not
 * MEM32(V + 0xCC0) (patch 31: the v1a launch showed no colour change); the in-place publish is the default
 * (BM_P23_PAINTS_LIVE_INPLACE 1, I1 decided); at LOAD_DONE / RACE_EXIT the saved index is put back while E + 0x59 still reads 127
 * (the next load would otherwise reduce 127 mod the palette count into the player's chosen paint).
 * MUT=n (tests): 1 the entity taken from MEM32(V + 0xCC0) (patch 31's defect)  2 negative / >= 128 index accepted (index 128)
 *   3 no owner check  4 no rate limit  5 the saved index not restored  6 in-place publish under the re-bind constant (one unit)
 *   7 every entry recoloured (not only BODY)  8 any thread  9 no restore at a race exit
 */
#include "bm_paints_svc.h"

#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "bm_events.h"
#include "bm_guest.h"
#include "bm_lifecycle.h"
#include "plugins.h"
#include "recomp_types.h"
#include "bm_paints_decals.h"     /* main21 patch 73: generated per-car DECALS tables */

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 1           /* unit tests: the CMake option is not there */
#endif

#define UNIT 0x440u
#define RATE_WINDOW 60u             /* car updates a second */

static const td_host *s_owner;
static int s_want;                  /* the plugin wants the dynamic paint shown */
static uint32_t s_rgb = 0x808080u;
static int s_dirty;
static uint32_t s_unit[2], s_cur;   /* the units; s_cur = the one the car uses */
static uint32_t s_tex;              /* the texture the units were built for */
static uint32_t s_E;                /* player 0's render entity this race (0 = not found yet) */
static int8_t s_saved;              /* E + 0x59 before the first write */
static int s_written;
static uint32_t s_tick, s_served_tick, s_window, s_in_window;
static _Atomic uint32_t s_published, s_active, s_layers;
static int s_census = -1;           /* -1 not checked yet */
static char s_stem[16];
static uint32_t s_drgb = 0x808080u;  /* patch 73: the DECALS colour */
static int s_dwant;                 /* DECALS asked for */
/* main21 patch 74: WHEELS = a per-draw palette while the car model draw sub_000303D0 draws its wheel lists (the wheel loop
 * loc_00030C96 .. loc_00030E0F): the car's dynamic palette with the table's wheel entries recoloured. The generated code binds
 * it with the game's own sub_0034DE60(0, palette) at the loop's start and the car palette again at its end - player 0's car only
 * (its render entity, the dynamic index 127 shown). Entries the wheels share with the body change colour on the wheels only. */
#ifndef BO3_HOOKREQ_P6W
#define BO3_HOOKREQ_P6W 1           /* unit tests: the CMake option is not there */
#endif
static uint32_t s_wrgb = 0x808080u;
static int s_wwant, s_wok, s_wswitched;
static int s_wcensus = -1;          /* the wheel loop's bytes (0x30C83 / 0x30C96 / 0x30E0F) */
static uint32_t s_wunit;            /* the wheel palette unit (0x440) */
static uint32_t s_wbinds;           /* wheel palettes bound (tests) */
uint32_t bo3_paints_svc_wheel_binds(void) { return s_wbinds; }
/* main21 patch 75: NITRO = a TINT of the car's boost flame. The flame is three corona sprites a car (CB3RaceCar::Draw ->
 * sub_001871E0 -> sub_00179F30, which answers the flame colour: the car's own texture coronaboost (blue) or coronaboostred, with a
 * near-white tint times the flame level). The mark right after sub_00179F30 replaces that colour for player 0's racer with the
 * plugin's colour at the same brightness; the texture stays the car's own (a blue flame can be darkened / shifted, not made red). */
#ifndef BO3_HOOKREQ_P6N
#define BO3_HOOKREQ_P6N 1           /* unit tests: the CMake option is not there */
#endif
static uint32_t s_nrgb = 0xFFFFFFu;
static int s_nwant;
static int s_nglow;                 /* patch 76: option b - the neutral glow list (any colour, a round glow) */
static int s_ncensus = -1;
static uint32_t s_ntints;           /* flame colours replaced (tests) */
uint32_t bo3_paints_svc_nitro_tints(void) { return s_ntints; }
static bo3_paints_alloc_fn s_alloc;
static RECOMP_TLS int t_game;

static uint32_t rd32(uint32_t va) { uint32_t v = 0; bo3_guest_rd32(va, &v); return v; }
static uint8_t rd8(uint32_t va) { uint8_t v = 0; bo3_guest_read(va, &v, 1); return v; }

void bo3_paints_svc_set_alloc(bo3_paints_alloc_fn a) { s_alloc = a; }

int bo3_paints_svc_census(void)
{
    static const uint8_t idx[4] = { 0x0F, 0xBE, 0x4F, 0x59 }, cnt[4] = { 0x0F, 0xB6, 0x50, 0x69 };
    uint8_t a[4], b[4];
    if (s_census < 0)
        s_census = bo3_guest_read(0x0003053Du, a, 4) && !memcmp(a, idx, 4) && bo3_guest_read(0x0003054Cu, b, 4) &&
                   !memcmp(b, cnt, 4) && rd32(BO3_PS_CAR1_VT) == 0x0018C470u;
    return s_census;
}

static int avail(void)
{
    return BO3_HOOKREQ_P23 && bo3_paints_svc_census();
}

/* player 0's physics vehicle V (the player pool entry pointing back to racer 0x73A1D0), or 0 */
static uint32_t player_vehicle(void)
{
    if (rd32(BO3_PS_CAR1) != BO3_PS_CAR1_VT || rd32(BO3_PS_CAR1 + BO3_PS_PLAYER) != 0)
        return 0;
    for (uint32_t n = 0; n < 2u; n++) {
        uint32_t v = BO3_PS_POOL + n * BO3_PS_POOL_STRIDE;
        if (rd32(v) == BO3_PS_POOL_VT && rd32(v + BO3_PS_V_RACER) == BO3_PS_CAR1)
            return v;
    }
    return 0;
}

static void stem_of(uint32_t v)
{
    static const char pre[] = "../Export/ValueDB/VehiclePhysics/";
    char name[0xB1];
    uint32_t b = rd32(v + BO3_PS_V_BLOCK);
    size_t n, pl = sizeof pre - 1;
    s_stem[0] = 0;
    if (!b || !bo3_guest_read(b, name, 0xB0))
        return;
    name[0xB0] = 0;
    n = strlen(name);
    if (n > pl + 4 && !strncmp(name, pre, pl) && !strcmp(name + n - 4, ".cfg") && n - pl - 4 < sizeof s_stem) {
        memcpy(s_stem, name + pl, n - pl - 4);
        s_stem[n - pl - 4] = 0;
    }
}

/* patch 73: the DECALS row of a car, found by the FNV-1a 32 of its palette 0 (the generator's key), or NULL */
static uint32_t pal_fnv(const uint32_t *p0)
{
    const uint8_t *b = (const uint8_t *)p0;
    uint32_t h = 0x811C9DC5u;
    for (int i = 0; i < 1024; i++)
        h = (h ^ b[i]) * 0x01000193u;
    return h;
}

/* patch 74: the WHEELS row of a car (the same key), or NULL */
static const bm_paints_decal_row *wheel_row(const uint32_t *p0)
{
    uint32_t h = pal_fnv(p0);
    for (size_t k = 0; k < BM_PAINTS_WHEEL_ROWS; k++)
        if (k_paint_wheels[k].pal0_fnv == h)
            return &k_paint_wheels[k];
    return NULL;
}

static const bm_paints_decal_row *decal_row(const uint32_t *p0)
{
    uint32_t h = pal_fnv(p0);
#if MUT == 92
    (void)h;
    return &k_paint_decals[0];                          /* defect: any car gets the first car's table */
#else
    for (size_t k = 0; k < BM_PAINTS_DECAL_ROWS; k++)
        if (k_paint_decals[k].pal0_fnv == h)
            return &k_paint_decals[k];
    return NULL;
#endif
}

static uint32_t lum(uint32_t bgra)
{
    return 299u * ((bgra >> 16) & 0xFF) + 587u * ((bgra >> 8) & 0xFF) + 114u * (bgra & 0xFF);
}

/* recolour the entries idx[0..n) of out by their brightness between 30 % of rgb and rgb (alpha kept) - BODY's rule */
static void recolour(const uint32_t *p0, const int *idx, int n, uint32_t rgb, uint8_t out[1024])
{
    uint32_t dark = (((rgb >> 16) & 0xFF) * 3 / 10) << 16 | (((rgb >> 8) & 0xFF) * 3 / 10) << 8 | ((rgb & 0xFF) * 3 / 10);
    uint32_t lo = 0xFFFFFFFFu, hi = 0;
    for (int k = 0; k < n; k++) {
        uint32_t l = lum(p0[idx[k]]);
        if (l < lo) lo = l;
        if (l > hi) hi = l;
    }
    for (int k = 0; k < n; k++) {
        uint32_t c = p0[idx[k]], l = lum(c), t = hi > lo ? (uint32_t)(((uint64_t)(l - lo) * 1024u) / (hi - lo)) : 1024u;
        uint32_t o = c & 0xFF000000u;
        for (int ch = 0; ch < 3; ch++) {
            uint32_t a = (dark >> (8 * ch)) & 0xFF, b = (rgb >> (8 * ch)) & 0xFF;
            o |= ((a * (1024u - t) + b * t) / 1024u) << (8 * ch);
        }
        memcpy(out + 4 * idx[k], &o, 4);
    }
}

/* the dynamic palette of tex: 1 (+ 2 when the car offers DECALS, + 4 WHEELS) and out[1024], 0 (no ramp / unreadable) */
static int build(uint32_t tex, uint32_t rgb, uint8_t out[1024])
{
    uint32_t n = rd8(tex + 0x69u), h0 = rd32(tex + 0x14u), h1 = rd32(tex + 0x18u), p0[256], p1[256], lo = 0xFFFFFFFFu, hi = 0;
    uint32_t dark = (((rgb >> 16) & 0xFF) * 3 / 10) << 16 | (((rgb >> 8) & 0xFF) * 3 / 10) << 8 | ((rgb & 0xFF) * 3 / 10);
    int ramp[256], nr = 0;
    if (n < 2 || !h0 || !h1 || !bo3_guest_read(h0 + 0x40u, p0, 1024) || !bo3_guest_read(h1 + 0x40u, p1, 1024))
        return 0;
    for (int i = 0; i < 256; i++)
#if MUT == 7
        ramp[nr++] = i;
#else
        if (p0[i] != p1[i])
            ramp[nr++] = i;
#endif
    if (!nr)
        return 0;
    for (int k = 0; k < nr; k++) {
        uint32_t l = lum(p0[ramp[k]]);
        if (l < lo) lo = l;
        if (l > hi) hi = l;
    }
    memcpy(out, p0, 1024);
    (void)lo, (void)hi, (void)dark;
    recolour(p0, ramp, nr, rgb, out);
    {
        const bm_paints_decal_row *row = decal_row(p0);
        int dec[256], nd = 0, w = (BO3_HOOKREQ_P6W && wheel_row(p0)) ? 4 : 0;   /* patch 74: 4 = the car offers WHEELS */
        if (!row)
            return 1 | w;
        if (s_dwant) {                                  /* the decal entries of the table (never a ramp entry) */
            for (int i = 0; i < 256; i++)
#if MUT == 91
                if (p0[i] == p1[i])                     /* defect: every non-ramp entry recoloured, not the table's */
#else
                if (((row->bits[i / 32] >> (i % 32)) & 1u) && p0[i] == p1[i])
#endif
                    dec[nd++] = i;
            recolour(p0, dec, nd, s_drgb, out);
        }
        return 3 | w;
    }
}

static int nitro_census(void);      /* patch 75 */
static int s_built;                 /* patch 73: the last build's result (2: the car offers DECALS) */
/* write the palette for tex into unit u; 1 ok */
static int publish(uint32_t tex, uint32_t u)
{
    uint8_t pal[1024];
    uint32_t hdr[16], h0 = rd32(tex + 0x14u), d;
    if (!h0 || !bo3_guest_window(h0, 0x440u))
        return 0;
    d = rd32(h0 + 4u) - (h0 + 0x40u);
    if (d != 0u && d != 0x80000000u)
        return 0;                                       /* the registry's rule: the VA or the window's physical offset */
    if (!(s_built = build(tex, s_rgb, pal)))
        return 0;
    memset(hdr, 0, sizeof hdr);
    hdr[0] = 0x00030001u;
    hdr[1] = u + 0x40u + d;
    if (!bo3_guest_write(u, hdr, 0x40u) || !bo3_guest_write(u + 0x40u, pal, 1024u))
        return 0;
    s_wok = 0;
    if ((s_built & 4) && s_wwant && s_wunit) {         /* patch 74: the wheel palette = this palette + the wheel entries */
        uint32_t p0[256];
        const bm_paints_decal_row *row;
        int wi[256], nw = 0;
        if (bo3_guest_read(h0 + 0x40u, p0, 1024) && (row = wheel_row(p0)) != NULL) {
            uint8_t wp[1024];
            uint32_t wh[16];
            memcpy(wp, pal, 1024);
            for (int i = 0; i < 256; i++)
#if MUT == 94
                if (1)                                  /* defect: every entry recoloured on the wheels */
#else
                if ((row->bits[i / 32] >> (i % 32)) & 1u)
#endif
                    wi[nw++] = i;
            recolour(p0, wi, nw, s_wrgb, wp);
            memset(wh, 0, sizeof wh);
            wh[0] = 0x00030001u;
            wh[1] = s_wunit + 0x40u + d;
            s_wok = bo3_guest_write(s_wunit, wh, 0x40u) && bo3_guest_write(s_wunit + 0x40u, wp, 1024u);
        }
    }
    atomic_fetch_add(&s_published, 1);
    return 1;
}

uint32_t bo3_paints_dyn_palette(uint32_t tex, uint32_t paint)
{
    uint32_t next;
    t_game = 1;
    if (!BO3_HOOKREQ_P23 || paint != BM_P23_PAINTS_DYN_INDEX || !s_owner || !s_want || !s_unit[0] || s_census != 1)
        return 0;
    if (tex != s_tex || s_dirty) {
#if (BM_P23_PAINTS_LIVE_INPLACE && MUT != 6)
        next = s_cur;                                   /* I1: shown at once at the same address */
#else
        next = s_cur ^ 1u;                              /* (MUT 6: the other unit under the in-place constant) */
#endif
        if (!publish(tex, s_unit[next])) {
            atomic_store(&s_layers, 0);
            return 0;                                   /* the registry answers (palette 0): UNSUPPORTED car */
        }
        s_cur = next;
        s_tex = tex;
        s_dirty = 0;
        atomic_store(&s_layers, (1u << BM_PAINT_LAYER_BODY) | ((s_built & 2) ? 1u << BM_PAINT_LAYER_DECALS : 0u) |
                                ((s_built & 4) ? 1u << BM_PAINT_LAYER_WHEELS : 0u) |
                                ((BO3_HOOKREQ_P6N && nitro_census()) ? 1u << BM_PAINT_LAYER_NITRO : 0u));   /* patch 75 */
    }
    s_served_tick = s_tick;
    atomic_store(&s_active, 1);
    return s_unit[s_cur];
}

/* patch 74 marks (generated code, sub_000303D0 / sub_00030455's wheel loop; e = the drawn render entity [ebp + 0xC]):
 * begin answers the wheel palette to bind (0 = leave the car's), end the car palette to bind again (0 = nothing switched) */
/* the wheel loop's sites (default.xbe 9f497acd; main21 tests\p6\run_wheels.py checks them against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[20]; } s_wh_census[] = {
    { 0x00030C83u, 19, { 0x8a,0x41,0x0d,0x84,0xc0,0xc7,0x44,0x24,0x10,0x00,0x00,0x00,0x00,0x0f,0x8e,0x79,0x01,0x00,0x00 } },  /* count, jle */
    { 0x00030C96u, 9,  { 0x8b,0x45,0x10,0x8d,0x90,0xe8,0x04,0x00,0x00 } },                     /* the loop's start (mark A) */
    { 0x00030E0Fu, 10, { 0x8b,0x44,0x24,0x28,0x8b,0x90,0xc0,0x16,0x00,0x00 } },                /* the loop's end (mark B) */
    { 0x00030554u, 12, { 0x8b,0x44,0x88,0x14,0x50,0x6a,0x00,0xe8,0x00,0xd9,0x31,0x00 } },      /* the car palette bind, cdecl */
};
/* END-CENSUS */
static int wheels_census(void)
{
    if (s_wcensus < 0) {
        s_wcensus = 1;
        for (size_t k = 0; k < sizeof s_wh_census / sizeof s_wh_census[0]; k++) {
            uint8_t x[20];
            if (!bo3_guest_read(s_wh_census[k].va, x, s_wh_census[k].n) || memcmp(x, s_wh_census[k].b, s_wh_census[k].n))
                s_wcensus = 0;
        }
    }
    return s_wcensus;
}

uint32_t bo3_paints_wheels_begin(uint32_t e)
{
    s_wswitched = 0;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P6W || !s_owner || !s_want || !s_wwant || !s_wok || s_census != 1 || !wheels_census())
        return 0;
#if MUT != 95
    if (e != BO3_PS_CAR1 + BO3_PS_E_OFF || rd8(e + BO3_PS_E_PAINT) != (uint8_t)BM_P23_PAINTS_DYN_INDEX)
        return 0;                                       /* another car (AI / traffic) or not the dynamic paint: untouched */
#else
    (void)e;                                            /* defect: every car's wheels get the player's wheel palette */
#endif
    s_wswitched = 1;
    s_wbinds++;
    return s_wunit;
}

/* the flame-colour site (default.xbe 9f497acd; main21 tests\p6\run_nitro.py checks them against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_ni_census[] = {
    { 0x001871EEu, 20, { 0x8b,0x75,0x08,0x33,0xc0,0x8a,0x86,0x01,0x19,0x00,0x00,0x57,0x8b,0xf9,0x8d,0x8e,0x9c,0x11,0x00,0x00 } },  /* racer, flag */
    { 0x00187202u, 13, { 0x50,0x8d,0x84,0x24,0x64,0x01,0x00,0x00,0xe8,0x21,0x2d,0xff,0xff } },   /* out = esp + 0x160, call sub_00179F30 */
    { 0x0018720Fu, 17, { 0xf3,0x0f,0x10,0x05,0xd8,0x7e,0x3a,0x00,0xf3,0x0f,0x10,0xb4,0x24,0x70,0x01,0x00,0x00 } },  /* reads size + 0x10 */
    { 0x00179F30u, 24, { 0x55,0x8b,0xec,0x83,0xe4,0xf0,0x83,0xec,0x10,0xf3,0x0f,0x10,0x49,0x14,0x0f,0x57,0xc0,0x0f,0x2f,0xc8,0x76,0x7d,
                         0x8a,0x55 } },                                                         /* the flame answer: level + 0x14 */
};
/* END-CENSUS */
static int nitro_census(void)
{
    if (s_ncensus != 1) {                               /* re-read until it matches (the XBE is mapped before any race) */
        s_ncensus = 1;
        for (size_t k = 0; k < sizeof s_ni_census / sizeof s_ni_census[0]; k++) {
            uint8_t x[24];
            if (!bo3_guest_read(s_ni_census[k].va, x, s_ni_census[k].n) || memcmp(x, s_ni_census[k].b, s_ni_census[k].n))
                s_ncensus = 0;
        }
    }
    return s_ncensus;
}

/* patch 75 mark (generated code, sub_001871E0 right after sub_00179F30): racer = esi, out = esp + 0x160 (colour vec4, size + 0x10,
 * list + 0x14). The plugin colour at the game's brightness: c x max(r, g, b) of the game's colour (the level is kept). */
void bo3_paints_nitro_tint(uint32_t racer, uint32_t out)
{
    float c[3];
    float m;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P6N || !s_owner || !s_want || !s_nwant || s_census != 1 || !nitro_census())
        return;
#if MUT != 97
    if (racer != BO3_PS_CAR1)
        return;                                         /* AI / other racers: their own flame */
#else
    (void)racer;                                        /* defect: every car's flame takes the colour */
#endif
    if (!bo3_guest_read(out, c, sizeof c))
        return;
    m = c[0] > c[1] ? c[0] : c[1];
    m = m > c[2] ? m : c[2];
    if (!(m > 0.0f))
        return;                                         /* no flame this frame */
#if MUT == 98
    m = 1.0f;                                           /* defect: the flame level is lost (always full) */
#endif
    c[0] = (float)((s_nrgb >> 16) & 0xFF) / 255.0f * m;
    c[1] = (float)((s_nrgb >> 8) & 0xFF) / 255.0f * m;
    c[2] = (float)(s_nrgb & 0xFF) / 255.0f * m;
#if MUT != 100
    if (s_nglow) {                                      /* patch 76: list 0 = coronaglow (a neutral grey texture) */
        uint32_t list = 0;
        if (!bo3_guest_write(out + 0x14u, &list, 4))
            return;
    }
#endif
    if (bo3_guest_write(out, c, sizeof c))
        s_ntints++;
}

uint32_t bo3_paints_wheels_end(void)
{
#if MUT != 96
    if (!s_wswitched)
        return 0;                                       /* nothing switched: the game's binding stays */
#endif
    s_wswitched = 0;
    return s_unit[s_cur];                               /* the car palette again for the rest of the model */
}

void bo3_paints_svc_tick(void *user)
{
    uint32_t v, e;
    (void)user;
    t_game = 1;
    s_tick++;
    if (s_tick - s_served_tick > 2u)
        atomic_store(&s_active, 0);
    if (!BO3_HOOKREQ_P23 || !s_owner || !avail())
        return;
    v = player_vehicle();                               /* player 0's car exists (and its ValueDB name) */
#if MUT == 1
    e = v ? rd32(v + BO3_PS_V_ENTITY) : 0;
#else
    e = v ? BO3_PS_CAR1 + BO3_PS_E_OFF : 0;
#endif
    if (!e || !bo3_guest_window(e + BO3_PS_E_PAINT, 1))
        return;
    if (e != s_E) {                                     /* a new entity (a new race): nothing of the old one is touched */
        s_E = e;
        s_written = 0;
        stem_of(v);
    }
    if (s_want) {
        int8_t cur = (int8_t)rd8(e + BO3_PS_E_PAINT);
#if MUT == 2
        const uint8_t dyn = 128u;
#else
        const uint8_t dyn = (uint8_t)BM_P23_PAINTS_DYN_INDEX;
#endif
        if ((uint8_t)cur != dyn) {
            if (!s_written)
                s_saved = cur;
            bo3_guest_write(e + BO3_PS_E_PAINT, &dyn, 1);
            s_written = 1;
        }
    } else if (s_written) {
#if MUT != 5
        if (rd8(e + BO3_PS_E_PAINT) == (uint8_t)BM_P23_PAINTS_DYN_INDEX)
            bo3_guest_write(e + BO3_PS_E_PAINT, &s_saved, 1);
#endif
        s_written = 0;
    }
}

void bo3_paints_svc_lifecycle(uint32_t kind)
{
    t_game = 1;
    if (kind == BO3_LC_EV_LOAD_DONE || kind == BO3_LC_EV_RACE_EXIT) {
#if MUT != 9
        if (s_written && s_E && rd8(s_E + BO3_PS_E_PAINT) == (uint8_t)BM_P23_PAINTS_DYN_INDEX)
            bo3_guest_write(s_E + BO3_PS_E_PAINT, &s_saved, 1);   /* never carried into the next load (mod count) */
#endif
        s_E = 0;
        s_written = 0;
        s_stem[0] = 0;
        atomic_store(&s_active, 0);
    }
}

static int32_t check(td_host *host, uint32_t player, int need_owner)
{
    if (!host)
        return BM_PAINTS_BAD_ARG;
    if (!avail())
        return BM_PAINTS_UNAVAILABLE;
    if (player == 1u)
        return BM_PAINTS_UNSUPPORTED;                   /* R6: split screen not validated */
    if (player != 0u)
        return BM_PAINTS_BAD_ARG;
#if MUT != 8
    if (!t_game)
        return BM_PAINTS_WRONG_THREAD;
#endif
#if MUT != 3
    if (need_owner && s_owner != host)
        return s_owner ? BM_PAINTS_CONFLICT : BM_PAINTS_NOT_OWNER;
#else
    (void)need_owner;
#endif
    return BM_PAINTS_OK;
}

static int32_t TD_CALL p_claim(td_host *host, uint32_t player)
{
    int32_t r = check(host, player, 0);
    if (r)
        return r;
    if (s_owner && s_owner != host)
        return BM_PAINTS_CONFLICT;
    if (!s_unit[0]) {
        uint32_t a = s_alloc ? s_alloc(3u * UNIT, 0x1000u) : 0;   /* patch 74: + the wheel unit */
        if (!a) {
            fprintf(stderr, "[PAINTS] bmashup.paints: no high-zone memory for the dynamic palette (3 x 0x440 B): NO_MEMORY\n");
            return BM_PAINTS_NO_MEMORY;
        }
        s_unit[0] = a;
        s_unit[1] = a + UNIT;
        s_wunit = a + 2u * UNIT;
        s_cur = 0;
    }
    s_owner = host;
    s_want = 1;
    s_dirty = 1;
    return BM_PAINTS_OK;
}

static int32_t TD_CALL p_set(td_host *host, uint32_t player, uint32_t layer, uint32_t rgb)
{
    int32_t r = check(host, player, 1);
    uint32_t w;
    if (r)
        return r;
#if MUT == 101
    if ((rgb & ~BM_PAINTS_NITRO_GLOW) > 0xFFFFFFu || layer < BM_PAINT_LAYER_BODY || layer > BM_PAINT_LAYER_NITRO)   /* defect: flag on any layer */
#else
    if ((rgb > 0xFFFFFFu && !(layer == BM_PAINT_LAYER_NITRO && (rgb & ~BM_PAINTS_NITRO_GLOW) <= 0xFFFFFFu)) ||
        layer < BM_PAINT_LAYER_BODY || layer > BM_PAINT_LAYER_NITRO)
#endif
        return BM_PAINTS_BAD_ARG;
    /* patch 73: DECALS once the current car is known to offer it (its palette built, a generated table row: status().layers);
     * patch 74: WHEELS the same (a wheel table row; a per-draw palette, see the marks); patch 75: NITRO = a flame tint (its site's
     * census; every car) */
#if MUT == 93
    if (layer != BM_PAINT_LAYER_BODY && layer != BM_PAINT_LAYER_DECALS && layer != BM_PAINT_LAYER_WHEELS)   /* defect: no table needed */
#elif MUT == 99
    if (layer != BM_PAINT_LAYER_BODY && layer != BM_PAINT_LAYER_NITRO &&                    /* defect: NITRO never checked */
        !((layer == BM_PAINT_LAYER_DECALS || layer == BM_PAINT_LAYER_WHEELS) && (atomic_load(&s_layers) & (1u << layer))))
#else
    if (layer != BM_PAINT_LAYER_BODY && !(atomic_load(&s_layers) & (1u << layer)))   /* DECALS / WHEELS / NITRO: when offered */
#endif
        return BM_PAINTS_NO_LAYER;
    w = s_tick / RATE_WINDOW;
    if (w != s_window) {
        s_window = w;
        s_in_window = 0;
    }
#if MUT != 4
    if (s_in_window >= BM_PAINTS_UPDATES_PER_SECOND)
        return BM_PAINTS_RATE;
#endif
    s_in_window++;
    if (layer == BM_PAINT_LAYER_DECALS)
        s_drgb = rgb, s_dwant = 1;
    else if (layer == BM_PAINT_LAYER_WHEELS)
        s_wrgb = rgb, s_wwant = 1;                      /* patch 74 */
    else if (layer == BM_PAINT_LAYER_NITRO)
        s_nrgb = rgb & 0xFFFFFFu, s_nglow = (rgb & BM_PAINTS_NITRO_GLOW) != 0, s_nwant = 1;   /* patches 75 / 76 */
    else
        s_rgb = rgb;
    s_want = 1;
    s_dirty = 1;
    return BM_PAINTS_OK;
}

static int32_t TD_CALL p_factory(td_host *host, uint32_t player)
{
    int32_t r = check(host, player, 1);
    if (r)
        return r;
    s_want = 0;                                         /* the next car update puts the chosen paint's index back */
    s_dwant = 0;                                        /* patch 73: decals with it */
    s_wwant = 0;                                        /* patch 74: wheels too */
    s_nwant = 0;                                        /* patch 75: and the flame */
    return BM_PAINTS_OK;
}

static int32_t TD_CALL p_release(td_host *host, uint32_t player)
{
    int32_t r = check(host, player, 1);
    if (r)
        return r;
    s_want = 0;
    s_dwant = 0;
    s_wwant = 0;
    s_nwant = 0;
    s_owner = NULL;
    if (s_written && s_E) {                             /* put the index back now (game thread) */
        if (rd8(s_E + BO3_PS_E_PAINT) == (uint8_t)BM_P23_PAINTS_DYN_INDEX)
            bo3_guest_write(s_E + BO3_PS_E_PAINT, &s_saved, 1);
        s_written = 0;
    }
    return BM_PAINTS_OK;
}

static int32_t TD_CALL p_status(td_host *host, uint32_t player, bm_paints_status *out)
{
    bm_paints_status s;
    uint32_t room;
    if (!host || !out || out->struct_size < 8u || player > 1u)
        return BM_PAINTS_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || s_census == 0)
        return BM_PAINTS_UNAVAILABLE;
    if (player == 1u)
        return BM_PAINTS_UNSUPPORTED;
    memset(&s, 0, sizeof s);
    s.owned = s_owner != NULL;
    s.yours = s_owner == host;
    s.active = atomic_load(&s_active);
    s.layers = atomic_load(&s_layers);
    s.published = atomic_load(&s_published);
    memcpy(s.vehicle, s_stem, sizeof s.vehicle);
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    s.struct_size = room;
    memcpy(out, &s, room);
    return BM_PAINTS_OK;
}

static const bm_paints_api s_api = { (uint32_t)sizeof(bm_paints_api), BM_PAINTS_VERSION, p_claim, p_set, p_factory, p_release,
                                     p_status };

const bm_paints_api *bo3_bm_paints_svc_api(void) { return &s_api; }

void bo3_paints_svc_reset(void)
{
    s_owner = NULL;
    s_want = s_dirty = s_written = 0;
    s_unit[0] = s_unit[1] = s_cur = s_tex = s_E = 0;
    s_tick = s_served_tick = s_window = s_in_window = 0;
    s_census = -1;
    s_rgb = 0x808080u;
    s_stem[0] = 0;
    atomic_store(&s_published, 0);
    atomic_store(&s_active, 0);
    atomic_store(&s_layers, 0);
    s_dwant = 0;
    s_drgb = 0x808080u;
    s_built = 0;
    s_wwant = s_wok = s_wswitched = 0;
    s_wcensus = -1;
    s_wrgb = 0x808080u;
    s_wunit = 0;
    s_wbinds = 0;
    s_nwant = 0;
    s_nrgb = 0xFFFFFFu;
    s_nglow = 0;
    s_ncensus = -1;
    s_ntints = 0;
    t_game = 0;
}

void bo3_bm_paints_svc_init(void)
{
#if BO3_HOOKREQ_P23
    int mark = bo3_events_hook("ap_update");
    if (mark < 0 || bo3_events_subscribe(mark, BO3_EVENT_WRITER, bo3_paints_svc_tick, NULL, "bmashup.paints") != 0)
        fprintf(stderr, "[PAINTS] bmashup.paints: the car-update mark is not available: the dynamic paint is never shown\n");
#endif
    bo3_plugins_service(BM_PAINTS_SERVICE, BM_PAINTS_VERSION, &s_api);
}
