/*
 * bm_vphysics.c - "bmashup.vphysics" (include/bmashup_vphysics.h): Burnout Mashup's private per-car physics query and
 * one bounded, reversible control. Research: gp\atlas\PHYSICS.md (every offset below, where it was found).
 *
 * v1.0.1 (gp_p4_1 finding: every racer "not readable"): the physics fields are NOT in the racer object R (the racer list
 * entry, player 1 = 0x73A1D0) but in its physics vehicle V, a separate object in the physics world 0x64B310
 * (= the race world 0x60EA00 + 0x3C910, sub_001A9C50 -> sub_00110280): V pools (sub_00110280's loops)
 *   player vehicles  0x64B310 + 0x1CB80 + n x 0x4AD0, n < 2   (V + 0x1580 = R, sub_001177B0)
 *   racer vehicles   0x64B310 + 0x26120 + n x 0x1580, n < 5   (vtable 0x3B1240; slot 6 sub_001049A0 -> sub_0011A8F0)
 *   racer vehicles   0x64B310 + 0x2CCA0 + n x 0x1560, n < 5   (vtable 0x3B1138; slot 6 sub_0010EDF0 -> sub_0011A8F0)
 * v1.0.2 (gp_phys1_2: AI racers "not readable"): v1.0.1 had the 0x1580 pool at + 0x27120 (sub_00110280's "edi - 4458" read
 *   as hex); the constructor sub_001A99F0 (from sub_001A9930) places it at + 0x26120 and stamps every pool's final vtable
 *   (player 0x3B1160, 0x3B1240, 0x3B1138; traffic 0x3B11EC never calls sub_0011A8F0 and is not searched). Each candidate
 *   must also carry its pool's vtable.
 * sub_0011A8F0 is a V method (ecx = V, argument R): V + 0x13F4 = R, V + 0x13F8 = P; the vehicle ID is R + 0x1970 / + 0x1974.
 * So: R -> the V among those 12 whose + 0x13F4 is R (and whose block's ID is R's ID). "car" below = V.
 *
 * The game (NTSC-U, the p3 generated code):
 *   car + 0x13F8   the car's physics block P (set by sub_0011A8F0 from sub_0011A810's result)
 *   car + 0x13F4   the racer R (sub_0011A8F0's argument); R + 0x1970 / + 0x1974 = the vehicle's u64 ID
 *   P + 0x00       "../Export/ValueDB/VehiclePhysics/<car>.cfg" (sprintf in sub_00132D10)
 *   P + 0xB0/0xB4  the vehicle ID the block was made for (sub_00132D10; sub_0011A810 matches it to reuse a block)
 *   P + off        the 64 ValueDB values (sub_00132D10 registers each; the ValueDB copy fills them)
 *   car + off'     the car's copy of 63 of them (sub_00134710, called by sub_0011A810 for every car set-up / reset);
 *                  the physics step reads these (e.g. Drag Coef car + 0x1360 in sub_0011D460 at 0x11D70C)
 *   sub_0011A8F0   a car's (re)set: calls sub_0011A810 (copy) and copies Max Speed In Boost again from P + 0x1A4
 *   GP-P4.2: "Max Speed In Boost" (car + 0x13D4) is the car's TOP-SPEED LIMIT in general (normal driving and boost;
 *   r2 gp_p41g_2: x0.5 = 80 mph with and without boost) - the ValueDB key is kept as its identifier.
 * Player 1's car: 0x73A1D0 (CB3PlayerCar, vtable 0x3B11A0, player index + 0x27D0 = 0). The racer list: count 0x73A19C,
 * cars 0x73A1A8 + 4 x i (bmashup.racers).
 *
 * Where each part runs:
 *   set_scale / reset (any thread)  note the request (atomics); nothing is written to the game there.
 *   the car update ("ap_update" mark, writer, player 1's car only, the game's thread): checks the build, the module /
 *       stage, the car (vtable, player 0) and its block (structure check below); then for each owned value: the car's
 *       copy == the game's value -> write game x scale; == the scaled value -> nothing; else -> contested (left alone).
 *       A reset() is carried out here too: the copy goes back to the game's value if it still holds the scaled one.
 *   after each update (the game's thread): follows the race (takedawn.race snapshot); when a race is left, every copy
 *       still holding a scaled value goes back to the game's value (same checks).
 * Structure check (a car): its block and vehicle record pointers readable (bm_guest.c, the runtime's mappings), the
 *   block's vehicle ID == the record's, the block's name a VehiclePhysics .cfg file. Anything else: nothing written.
 * MUT=n (tests) compiles one deliberate defect.
 *
 * v3 (platform 0.1.9, main19 item 21, hook request P2 A1): the GEARBOX of player 1's car (gp\hookreq\p23\SITES_VERIFIED.md s1.1,
 * re-checked by main19-A, tests\p23\STEP0_A.md). G = the physics vehicle V + 0x1448 (embedded): gear i32 G + 0x80, gear count
 * G + 0x84 (the upshift's bound), shift flag G + 0x5C, timer G + 0x58, mode word G + 0x70 (V + 0x14B8: read at 0x11F084 to take
 * the manual path; NO writer in the build -> retail is always AUTO). Upshift sub_0011A7B0 / downshift sub_0011A7E0 (EAX = G, no
 * stack argument, plain ret; the call shape of 0x11F0A5). The idle re-shift to neutral in sub_00121560 (0x1219B9 .. 0x1219FB)
 * re-arms the shift flag every non-positive-drive update while the mode word is not 0, and reverse by brake (0x11EF94 ..
 * 0x11F00B) needs that flag clear -> one host mark at loc_001219E1 (bo3_vphys_gearbox_gen.h) skips it only while a plugin owns
 * MANUAL on that car and the gear is already 0. Applied at the car update (the same writer as set_scale). Compiled out
 * (UNSUPPORTED) when BO3_HOOKREQ_P23 is 0.
 */
#include "bm_vphysics.h"

#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "bm_events.h"
#include "bm_guest.h"
#include "bm_vphys_catalog.h"
#include "plugins.h"
#include "race_service.h"
#include "takedawn_race.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 0
#endif

extern RECOMP_TLS uint32_t g_esi;
extern ptrdiff_t g_xbox_mem_offset;

#define VP_CAR1      0x0073A1D0u
#define VP_CARS      0x0073A19Cu
#define VP_LIST      0x0073A1A8u
#define VP_VT_CAR    0x003B11A0u
#define VP_PLAYER    0x27D0u
#define VP_INFO      0x13F4u
#define VP_BLOCK     0x13F8u
#define VP_INFO_ID   0x1970u
#define VP_BLOCK_ID  0xB0u
#define VP_NAME_MAX  0xB0u
#define VP_STATE     0x004D53B4u
#define VP_MODULE    0x004D5370u
#define VP_VT_GAME   0x003A9ACCu
#define VP_STAGE     0x1B8u
#define VP_STEP      0x004A1EB4u
#define VP_FMT       0x003AC65Cu          /* .rdata "../Export/ValueDB/VehiclePhysics/%s.cfg" (sub_00132D10's format) */
#define VP_LOG_MAX   8u                   /* lines of one kind a race */
#define VP_PW        0x0064B310u          /* the physics world: race world 0x60EA00 + 0x3C910 (sub_001A9C50) */

/* the physics vehicle pools (sub_00110280) */
static const struct { uint32_t base, stride, n, vtable; } s_pools[] = {
    { VP_PW + 0x1CB80u, 0x4AD0u, 2u, 0x003B1160u },    /* player vehicles */
#if MUT == 8
    { VP_PW + 0x27120u, 0x1580u, 5u, 0x003B1240u },    /* defect: v1.0.1's base */
#else
    { VP_PW + 0x26120u, 0x1580u, 5u, 0x003B1240u },    /* racer vehicles (sub_001A99F0) */
#endif
    { VP_PW + 0x2CCA0u, 0x1560u, 5u, 0x003B1138u },
};

static const char k_prefix[] = "../Export/ValueDB/VehiclePhysics/";
static const char k_fmt[] = "../Export/ValueDB/VehiclePhysics/%s.cfg";

/* the retail NTSC-U default.xbe (title 0x4541005B) .rdata words, as bm_autopilot.c / bm_boost.c, plus the format string */
static const struct { uint32_t va, word; } s_sig[] = {
    { 0x003B11A0u, 0x0018C470u },         /* CB3PlayerCar's vtable, slot 0 */
    { 0x003B11A4u, 0x0018C510u },         /* slot 1: the car update the mark is in */
    { 0x003A9ACCu, 0x00019FE0u },         /* the game module's vtable, slot 0 */
    { 0x003A9AD0u, 0x0001A000u },
    { 0x003B1178u, 0x001177B0u },         /* v1.0.1: the player physics vehicle's vtable slot (sub_001177B0: V + 0x1580 = R) */
    { 0x003B1258u, 0x001049A0u },         /* v1.0.2: the 0x1580 class's slot 6 -> sub_0011A8F0 */
    { 0x003B1150u, 0x0010EDF0u },         /* v1.0.2: the 0x1560 class's slot 6 -> sub_0011A8F0 */
};

enum { MODE_OFF = 0, MODE_ON = 1, MODE_DEBUG = 2 };

static _Atomic uint32_t s_mode;
static _Atomic int s_have_thread;
static int s_self;

static _Atomic(uintptr_t) s_owner[BM_VPHYS_CATALOG_N];
static _Atomic uint32_t s_scale_bits[BM_VPHYS_CATALOG_N];    /* the owner's scale (float bits); 1.0 when none */
static _Atomic int s_pending_restore[BM_VPHYS_CATALOG_N];
static _Atomic int s_written[BM_VPHYS_CATALOG_N];             /* player 1's copy was set to s_want by this service */
static _Atomic uint32_t s_want[BM_VPHYS_CATALOG_N];          /* the bits written */
static int s_applied_race[BM_VPHYS_CATALOG_N];               /* game thread: applied in this race already */
static unsigned s_contested_logged[BM_VPHYS_CATALOG_N];

static _Atomic uint32_t s_state, s_reason, s_race, s_applied, s_reapplied, s_restored, s_contested;
static uint32_t s_prev = TD_RACE_NONE;
static unsigned s_refuse_logged, s_reapply_logged;

static float bits_f(uint32_t b) { float f; memcpy(&f, &b, 4); return f; }
static uint32_t f_bits(float f) { uint32_t b; memcpy(&b, &f, 4); return b; }

static int build_ok(void)
{
    char buf[sizeof k_fmt];
    if (!g_xbox_mem_offset)
        return 0;
    for (size_t k = 0; k < sizeof s_sig / sizeof s_sig[0]; k++) {
        uint32_t w;
        if (!bo3_guest_rd32(s_sig[k].va, &w) || w != s_sig[k].word)
            return 0;
    }
#if MUT == 1
    memcpy(buf, k_fmt, sizeof buf);
    return buf[0] != 0;                                /* defect: the physics block's format string not checked */
#else
    return bo3_guest_read(VP_FMT, buf, sizeof buf) && !memcmp(buf, k_fmt, sizeof k_fmt);
#endif
}

/* v1.0.1: the physics vehicle V of racer R (the pool entry whose + 0x13F4 is R), or 0 */
static uint32_t vehicle_of(uint32_t r)
{
#if MUT == 7
    return r;                                 /* defect: v1.0.0's assumption (the racer object holds the physics fields) */
#else
    if (!r)
        return 0;
    for (size_t p = 0; p < sizeof s_pools / sizeof s_pools[0]; p++)
        for (uint32_t k = 0; k < s_pools[p].n; k++) {
            uint32_t v = s_pools[p].base + k * s_pools[p].stride, back = 0, vt = 0;
#if MUT == 9
            vt = s_pools[p].vtable;                      /* defect: the slot's vtable not checked */
#else
            bo3_guest_rd32(v, &vt);
#endif
            if (vt == s_pools[p].vtable && bo3_guest_rd32(v + VP_INFO, &back) && back == r)
                return v;
        }
    return 0;
#endif
}

/* The structure check of racer R: 1, its physics vehicle V, its block (+ the vehicle's file stem) when V points back to R,
 * V's block belongs to R's vehicle (ID) and names a VehiclePhysics file. */
static int car_ok(uint32_t r, uint32_t *vout, uint32_t *block, char *stem, size_t sn)
{
    uint32_t car = vehicle_of(r), b = 0, info = 0, bid[2], iid[2];
    char name[VP_NAME_MAX + 1];
    size_t n, pl = sizeof k_prefix - 1;
    if (!car || !bo3_guest_rd32(car + VP_BLOCK, &b) || !bo3_guest_rd32(car + VP_INFO, &info) || !b || info != r)
        return 0;
#if MUT != 2
    if (!bo3_guest_read(b + VP_BLOCK_ID, bid, 8) || !bo3_guest_read(info + VP_INFO_ID, iid, 8) || bid[0] != iid[0] ||
        bid[1] != iid[1])
        return 0;                             /* (MUT 2: the block's vehicle not compared) */
#endif
    if (!bo3_guest_read(b, name, VP_NAME_MAX))
        return 0;
    name[VP_NAME_MAX] = 0;
    n = strlen(name);
    if (n <= pl + 4 || strncmp(name, k_prefix, pl) || strcmp(name + n - 4, ".cfg") || n - pl - 4 >= 32)
        return 0;
    if (stem && sn) {
        size_t m = n - pl - 4 < sn - 1 ? n - pl - 4 : sn - 1;
        memcpy(stem, name + pl, m);
        stem[m] = 0;
    }
    *block = b;
    *vout = car;
    return 1;
}

static int in_stage(uint32_t state)
{
    return state >= TD_RACE_PRESTART && state <= TD_RACE_FINISHED;
}

/* the game module is running a stage (no phase / pause condition: the copy is set before the GO too) */
static int game_in_stage(void)
{
    uint32_t st = 0, mod = 0, vt = 0, stage = 0;
    if (!bo3_guest_rd32(VP_STATE, &st) || st != 5 || !bo3_guest_rd32(VP_MODULE, &mod) || mod < 0x10000u ||
        mod >= 0x04000000u || !bo3_guest_rd32(mod, &vt) || vt != VP_VT_GAME || !bo3_guest_rd32(mod + VP_STAGE, &stage))
        return 0;
    return stage != 0;
}

static uint32_t player1_ok(uint32_t *veh, uint32_t *block, char *stem, size_t sn)
{
    uint32_t vt = 0, pl = 1;
    if (!build_ok())
        return BM_VPHYS_UNSUPPORTED;
    if (!game_in_stage())
        return BM_VPHYS_UNAVAILABLE;
    if (!bo3_guest_rd32(VP_CAR1, &vt) || vt != VP_VT_CAR || !bo3_guest_rd32(VP_CAR1 + VP_PLAYER, &pl) || pl != 0)
        return BM_VPHYS_UNSUPPORTED;
    if (!car_ok(VP_CAR1, veh, block, stem, sn))
        return BM_VPHYS_UNSUPPORTED;
    return BM_VPHYS_OK;
}

static uint32_t step_now(void)
{
    uint32_t s = 0;
    bo3_guest_rd32(VP_STEP, &s);
    return s;
}

/* game value (bits as the game copies them) of entry i from block b */
static int game_bits(uint32_t b, uint32_t i, uint32_t *out)
{
    uint32_t v;
    if (!bo3_guest_rd32(b + k_bm_vphys_catalog[i].block_off, &v))
        return 0;
    if (k_bm_vphys_catalog[i].kind != 0)
        return 0;                                   /* only plain copies are compared / written (the writable ones) */
    if (k_bm_vphys_catalog[i].factor != 1.0f)
        v = f_bits(bits_f(v) * k_bm_vphys_catalog[i].factor);
    *out = v;
    return 1;
}

static int any_work(void)
{
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        if (atomic_load(&s_owner[i]) || atomic_load(&s_pending_restore[i]))
            return 1;
    return 0;
}

/* ---- v3 (platform 0.1.9, main19 item 21): the gearbox ---- */
#define GB_OFF      0x1448u               /* G = V + 0x1448 (0x11F0A5 lea eax,[ebx+0x1448]) */
#define GB_TIMER    0x58u
#define GB_SHIFTING 0x5Cu
#define GB_MODE     0x70u
#define GB_GEAR     0x80u
#define GB_GEARS    0x84u
#define GB_GEAR_SANE 16

extern void sub_0011A7B0(void);
extern void sub_0011A7E0(void);

/* the census: the bytes of every site the gearbox uses (default.xbe 9f497acd; tests\p23\vphysics_v3 checks this table against
 * the XBE file). BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_gbx_census[] = {
    { 0x001219D6u, 11, { 0x8b,0x46,0x70,0x85,0xc0,0x0f,0x84,0x5e,0xfe,0xff,0xff } },              /* mode gate (idle reset) */
    { 0x001219E1u, 18, { 0xf3,0x0f,0x10,0x05,0x28,0x1a,0x3b,0x00,0xc7,0x86,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00 } },  /* the mark */
    { 0x0011A7B0u, 16, { 0x8b,0x88,0x80,0x00,0x00,0x00,0x85,0xc9,0x7c,0x23,0x3b,0x88,0x84,0x00,0x00,0x00 } },  /* upshift */
    { 0x0011A7E0u, 11, { 0x8b,0x88,0x80,0x00,0x00,0x00,0x83,0xf9,0x02,0x7c,0x1b } },              /* downshift */
    { 0x0011F084u, 14, { 0x8b,0x83,0xb8,0x14,0x00,0x00,0x85,0xc0,0x0f,0x84,0xb2,0x01,0x00,0x00 } },  /* the manual path's gate */
    { 0x0011F0A5u, 11, { 0x8d,0x83,0x48,0x14,0x00,0x00,0xe8,0x00,0xb7,0xff,0xff } },              /* the retail call shape */
};
/* END-CENSUS */

static _Atomic(uintptr_t) s_gbx_owner;          /* the plugin holding MANUAL, 0 none */
static _Atomic int32_t s_gbx_req;               /* requested gear, 0 none */
static _Atomic uint32_t s_gbx_g;                /* G of player 1's car while this service holds its mode word, else 0 */
static _Atomic uint32_t s_gbx_skips;
static _Atomic int s_gbx_census_ok;             /* -1 not checked, 0 failed, 1 ok */
static unsigned s_gbx_logged;

static int gbx_census(void)
{
    int c = atomic_load(&s_gbx_census_ok);
    if (c >= 0)
        return c;
#if MUT == 27
    c = 1;                                      /* defect: the sites' bytes not checked */
#else
    c = BO3_HOOKREQ_P23 && g_xbox_mem_offset != 0;
    for (size_t k = 0; c && k < sizeof s_gbx_census / sizeof s_gbx_census[0]; k++) {
        uint8_t b[24];
        if (!bo3_guest_read(s_gbx_census[k].va, b, s_gbx_census[k].n) || memcmp(b, s_gbx_census[k].b, s_gbx_census[k].n))
            c = 0;
    }
#endif
    if (!g_xbox_mem_offset)
        return 0;                               /* not decided before the game's memory exists */
    atomic_store(&s_gbx_census_ok, c);
    if (!c)
        fprintf(stderr, "[VPHYS] bmashup.vphysics 3: the gearbox is UNSUPPORTED on this build (%s)\n",
                BO3_HOOKREQ_P23 ? "a site's bytes differ from the verified build" : "BO3_HOOKREQ_P23=OFF");
    return c;
}

/* the game's own shift routine on G (EAX = G, a 0 return address for its ret); every guest register put back */
static void gbx_call(void (*fn)(void), uint32_t g)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;
    g_eax = g;
    PUSH32(g_esp, 0);
    fn();
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp;
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
}

/* G of player 1's car in a race (the same structure check as set_scale), else 0 */
static uint32_t gbx_g_now(void)
{
    uint32_t veh = 0, block = 0;
    if (player1_ok(&veh, &block, NULL, 0) != BM_VPHYS_OK)
        return 0;
    return veh + GB_OFF;
}

static void gbx_give_back(uint32_t g, const char *why)
{
    uint32_t m = 0;
    atomic_store(&s_gbx_g, 0);
#if MUT == 25
    (void)g; (void)m; (void)why;                /* defect: the mode word not given back */
#else
    if (g && bo3_guest_rd32(g + GB_MODE, &m) && m == 1u) {
        bo3_guest_wr32(g + GB_MODE, 0);
        fprintf(stderr, "[VPHYS] bmashup.vphysics 3: player 1's gearbox back to AUTO (%s)\n", why);
    }
#endif
}

/* the car update (game thread, player 1's car, the "ap_update" writer) */
static void gbx_update(void)
{
    uint32_t g, mode = 0, sh = 0;
    int32_t gear = 0, gears = 0, req;
    uintptr_t own = atomic_load(&s_gbx_owner);
    if (!own) {
        if (atomic_load(&s_gbx_g))
            gbx_give_back(atomic_load(&s_gbx_g), "released");
        return;
    }
    if (!gbx_census() || !(g = gbx_g_now()))
        return;
    if (!bo3_guest_rd32(g + GB_MODE, &mode) || !bo3_guest_rd32(g + GB_GEAR, (uint32_t *)&gear) ||
        !bo3_guest_rd32(g + GB_GEARS, (uint32_t *)&gears) || !bo3_guest_rd32(g + GB_SHIFTING, &sh))
        return;
    if (gears < 1 || gears > GB_GEAR_SANE || gear < -1 || gear > GB_GEAR_SANE) {
        if (s_gbx_logged++ < VP_LOG_MAX)
            fprintf(stderr, "[VPHYS] bmashup.vphysics 3: player 1's gearbox not changed (gear %d of %d: not a gearbox this "
                            "service knows)\n", (int)gear, (int)gears);
        return;
    }
    if (mode != 1u) {
        bo3_guest_wr32(g + GB_MODE, 1u);
        if (s_gbx_logged++ < VP_LOG_MAX)
            fprintf(stderr, "[VPHYS] bmashup.vphysics 3: player 1's gearbox MANUAL (gear %d of %d) at step %u (race %u)\n",
                    (int)gear, (int)gears, (unsigned)step_now(), (unsigned)atomic_load(&s_race));
    }
    atomic_store(&s_gbx_g, g);
    req = atomic_load(&s_gbx_req);
    if (!req)
        return;
    if (req == gear || req < 1 || req > gears) {
        atomic_store(&s_gbx_req, 0);
        return;
    }
#if MUT != 26
    if (sh)
        return;                                 /* a shift is in progress: the next update */
#endif
#if MUT == 22
    bo3_guest_wr32(g + GB_GEAR, (uint32_t)req);  /* defect: the gear written directly */
    atomic_store(&s_gbx_req, 0);
#else
    if (req > gear)
        gbx_call(sub_0011A7B0, g);              /* refuses gear < 0 (reverse) itself: the request waits */
    else if (gear >= 2)
        gbx_call(sub_0011A7E0, g);
#endif
}

/* the mark in sub_00121560 (bo3_vphys_gearbox_gen.h): 1 = skip the idle re-shift to neutral */
int bo3_vphys_gen_idle_skip(uint32_t g)
{
    uint32_t gear = 1;
#if MUT == 21
    if (!bo3_guest_rd32(g + GB_GEAR, &gear) || gear != 0)   /* defect: active without the ownership */
        return 0;
#else
    if (!BO3_HOOKREQ_P23 || !g || g != atomic_load(&s_gbx_g) || !atomic_load(&s_gbx_owner) ||
        !bo3_guest_rd32(g + GB_GEAR, &gear) || gear != 0)
        return 0;
#endif
    atomic_fetch_add(&s_gbx_skips, 1);
    return 1;
}

static void gbx_race_reset(const char *why)
{
    uint32_t g = atomic_load(&s_gbx_g);
    if (g)
        gbx_give_back(g, why);
    if (atomic_load(&s_gbx_owner))
        fprintf(stderr, "[VPHYS] bmashup.vphysics 3: %s: the gearbox owner and its request are dropped\n", why);
    atomic_store(&s_gbx_owner, 0);
    atomic_store(&s_gbx_req, 0);
    atomic_store(&s_gbx_skips, 0);
    s_gbx_logged = 0;
}

static int32_t gbx_player(uint32_t player)
{
    if (player > 1u)
        return BM_VPHYS_NOT_PLAYER;
#if MUT != 24
    if (player == 1u)
        return BM_VPHYS_UNSUPPORTED;            /* split screen (R6) */
#endif
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_set_gearbox(td_host *host, uint32_t player, uint32_t mode)
{
    int32_t rc;
    uintptr_t none = 0;
    if (!host || mode > BM_GEARBOX_MANUAL)
        return BM_VPHYS_BAD_ARG;
    if ((rc = gbx_player(player)) != BM_VPHYS_OK)
        return rc;
    if (!BO3_HOOKREQ_P23 || (g_xbox_mem_offset && !gbx_census()))
        return BM_VPHYS_UNSUPPORTED;
    if (atomic_load(&s_mode) == MODE_DEBUG)
        return BM_VPHYS_DEBUG_AUTOPILOT;
    if (mode == BM_GEARBOX_MANUAL) {
        if (!atomic_compare_exchange_strong(&s_gbx_owner, &none, (uintptr_t)host) && none != (uintptr_t)host)
            return BM_VPHYS_CONFLICT;
        fprintf(stderr, "[VPHYS] bmashup.vphysics 3: player 1's gearbox MANUAL from its next car update in a race "
                        "(CHANGES GAMEPLAY)\n");
        return BM_VPHYS_OK;
    }
    if (atomic_load(&s_gbx_owner) != (uintptr_t)host)
        return atomic_load(&s_gbx_owner) ? BM_VPHYS_CONFLICT : BM_VPHYS_OK;   /* AUTO while nobody owns it: nothing to do */
    atomic_store(&s_gbx_req, 0);
    atomic_store(&s_gbx_owner, 0);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_request_gear(td_host *host, uint32_t player, int32_t gear)
{
    int32_t rc, gears = 0;
    uint32_t g, sh = 0;
    if (!host)
        return BM_VPHYS_BAD_ARG;
    if ((rc = gbx_player(player)) != BM_VPHYS_OK)
        return rc;
    if (!BO3_HOOKREQ_P23 || (g_xbox_mem_offset && !gbx_census()))
        return BM_VPHYS_UNSUPPORTED;
    if (atomic_load(&s_gbx_owner) != (uintptr_t)host)
        return BM_VPHYS_WRONG_MODE;
    if (!(g = gbx_g_now()) || !bo3_guest_rd32(g + GB_GEARS, (uint32_t *)&gears) || gears < 1 || gears > GB_GEAR_SANE)
        return BM_VPHYS_UNAVAILABLE;
#if MUT == 23
    (void)gears;
    if (gear == 0)                              /* defect: only 0 refused (reverse / beyond the top gear accepted) */
#else
    if (gear < 1 || gear > gears)
#endif
        return BM_VPHYS_BAD_ARG;
    if (bo3_guest_rd32(g + GB_SHIFTING, &sh) && sh)
        return BM_VPHYS_BUSY_SHIFT;
    atomic_store(&s_gbx_req, gear);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_gearbox_status(td_host *host, uint32_t player, bm_vphys_gearbox_status *out)
{
    bm_vphys_gearbox_status o;
    int32_t rc;
    uint32_t g;
    if (!host || !out || out->struct_size < 8)
        return BM_VPHYS_BAD_ARG;
    if ((rc = gbx_player(player)) != BM_VPHYS_OK)
        return rc;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.available = BO3_HOOKREQ_P23 && g_xbox_mem_offset && gbx_census() ? 1u : 0u;
    if (o.available && (g = gbx_g_now()) != 0) {
        uint32_t m = 0, sh = 0;
        bo3_guest_rd32(g + GB_MODE, &m);
        bo3_guest_rd32(g + GB_GEAR, (uint32_t *)&o.gear);
        bo3_guest_rd32(g + GB_GEARS, (uint32_t *)&o.max_gear);
        bo3_guest_rd32(g + GB_SHIFTING, &sh);
        o.mode = m ? BM_GEARBOX_MANUAL : BM_GEARBOX_AUTO;
        o.shifting = sh ? 1u : 0u;
    }
    o.requested = atomic_load(&s_gbx_req);
    o.owned = atomic_load(&s_gbx_owner) ? 1u : 0u;
    o.yours = atomic_load(&s_gbx_owner) == (uintptr_t)host;
    o.idle_fix_skips = atomic_load(&s_gbx_skips);
    memcpy(out, &o, o.struct_size);
    return BM_VPHYS_OK;
}

void bo3_bm_vphysics_car_update(void)
{
    uint32_t car = g_esi, veh = 0, block = 0, rc;
    char stem[32] = "";
    int all = 1, owned = 0;

    if (car != VP_CAR1 || !g_xbox_mem_offset)
        return;
    if (atomic_load(&s_mode) == MODE_ON)
        gbx_update();                           /* v3: the gearbox (its own owner / checks) */
    if (atomic_load(&s_mode) != MODE_ON || !any_work())
        return;
    rc = player1_ok(&veh, &block, stem, sizeof stem);
    if (rc != BM_VPHYS_OK) {
        atomic_store(&s_state, BM_VPHYS_STATE_REFUSED);
        atomic_store(&s_reason, rc);
        if (s_refuse_logged++ < VP_LOG_MAX)
            fprintf(stderr, "[VPHYS] bmashup.vphysics: player 1's car not changed at step %u (race %u): %s\n",
                    (unsigned)step_now(), (unsigned)atomic_load(&s_race),
                    rc == BM_VPHYS_UNSUPPORTED ? "the build or the car's physics block is not one this service knows"
                                               : "no stage");
        return;
    }
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++) {
        const bm_vphys_entry *e = &k_bm_vphys_catalog[i];
        uint32_t gb, cur, want, va = veh + e->car_off;
        if (!e->writable)
            continue;
        if (!game_bits(block, i, &gb) || !bo3_guest_rd32(va, &cur))
            continue;
        if (atomic_load(&s_pending_restore[i])) {
            atomic_store(&s_pending_restore[i], 0);
            if (atomic_load(&s_written[i]) && cur == atomic_load(&s_want[i])) {
                bo3_guest_wr32(va, gb);
                atomic_fetch_add(&s_restored, 1);
                fprintf(stderr, "[VPHYS] bmashup.vphysics: reset: player 1 (%s) \"%s\" back to %g at step %u (race %u)\n",
                        stem, e->full, (double)bits_f(gb), (unsigned)step_now(), (unsigned)atomic_load(&s_race));
            }
            atomic_store(&s_written[i], 0);
        }
        if (!atomic_load(&s_owner[i]))
            continue;
        owned = 1;
        want = f_bits(bits_f(gb) * bits_f(atomic_load(&s_scale_bits[i])));
        if (!isfinite(bits_f(gb)) || !isfinite(bits_f(want))) {
            all = 0;
            continue;
        }
        if (cur == want) {
            atomic_store(&s_want[i], want);
            atomic_store(&s_written[i], 1);
            continue;
        }
#if MUT == 3
        if (1) {                                  /* defect: writes over any value (another writer's too) */
#else
        if (cur == gb || (atomic_load(&s_written[i]) && cur == atomic_load(&s_want[i]))) {
#endif
            bo3_guest_wr32(va, want);
            atomic_store(&s_want[i], want);
            atomic_store(&s_written[i], 1);
            if (s_applied_race[i]) {
                if (cur == gb)
                    atomic_fetch_add(&s_reapplied, 1);
                if (s_reapply_logged++ < VP_LOG_MAX)
                    fprintf(stderr, "[VPHYS] bmashup.vphysics: player 1 (%s) \"%s\" set again %g -> %g at step %u (race %u): %s\n",
                            stem, e->full, (double)bits_f(cur), (double)bits_f(want), (unsigned)step_now(),
                            (unsigned)atomic_load(&s_race), cur == gb ? "the game had copied its value back" : "the scale changed");
            } else {
                s_applied_race[i] = 1;
                atomic_fetch_add(&s_applied, 1);
                fprintf(stderr, "[VPHYS] bmashup.vphysics: player 1 (%s) \"%s\" %g -> %g (x%g, game value %g) at step %u (race %u)\n",
                        stem, e->full, (double)bits_f(cur), (double)bits_f(want), (double)bits_f(atomic_load(&s_scale_bits[i])),
                        (double)bits_f(gb), (unsigned)step_now(), (unsigned)atomic_load(&s_race));
            }
        } else {
            all = 0;
            atomic_fetch_add(&s_contested, 1);
            if (s_contested_logged[i]++ < 2)
                fprintf(stderr, "[VPHYS] bmashup.vphysics: player 1 (%s) \"%s\" holds %g (game value %g): another writer; left "
                                "alone (race %u)\n", stem, e->full, (double)bits_f(cur), (double)bits_f(gb),
                        (unsigned)atomic_load(&s_race));
        }
    }
    atomic_store(&s_reason, BM_VPHYS_OK);
    atomic_store(&s_state, !owned ? BM_VPHYS_STATE_IDLE : all ? BM_VPHYS_STATE_APPLIED : BM_VPHYS_STATE_SET);
}

/* a race was left: every copy still holding a scaled value goes back to the game's value */
static void restore_all(const char *why)
{
    uint32_t veh = 0, block = 0;
    char stem[32] = "";
    int any = 0;
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        any |= atomic_load(&s_written[i]);
    if (!any)
        return;
#if MUT == 4
    (void)why; (void)block; (void)veh;
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        atomic_store(&s_written[i], 0);         /* defect: forgets without restoring */
    return;
#else
    if (!build_ok() || !car_ok(VP_CAR1, &veh, &block, stem, sizeof stem)) {
        fprintf(stderr, "[VPHYS] bmashup.vphysics: %s: player 1's car is gone; nothing restored (the game sets the car up "
                        "again from its own values)\n", why);
    } else {
        for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++) {
            const bm_vphys_entry *e = &k_bm_vphys_catalog[i];
            uint32_t gb, cur, va = veh + e->car_off;
            if (!atomic_load(&s_written[i]))
                continue;
            if (game_bits(block, i, &gb) && bo3_guest_rd32(va, &cur) && cur == atomic_load(&s_want[i])) {
                bo3_guest_wr32(va, gb);
                atomic_fetch_add(&s_restored, 1);
                fprintf(stderr, "[VPHYS] bmashup.vphysics: %s: player 1 (%s) \"%s\" %g -> %g (the game's value) (race %u)\n",
                        why, stem, e->full, (double)bits_f(cur), (double)bits_f(gb), (unsigned)atomic_load(&s_race));
            }
        }
    }
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        atomic_store(&s_written[i], 0);
#endif
}

static void observe(uint32_t state)
{
    if (state == s_prev)
        return;
    if (in_stage(state) && (!in_stage(s_prev) || (state == TD_RACE_PRESTART && s_prev != TD_RACE_PRESTART))) {
        if (in_stage(s_prev)) {
            restore_all("race restarted");
            gbx_race_reset("race restarted");   /* v3 */
        }
        atomic_fetch_add(&s_race, 1);
        memset(s_applied_race, 0, sizeof s_applied_race);
        memset(s_contested_logged, 0, sizeof s_contested_logged);
        s_refuse_logged = s_reapply_logged = 0;
    } else if (in_stage(s_prev) && !in_stage(state)) {
        restore_all("race left");
        gbx_race_reset("race left");            /* v3 */
    }
    s_prev = state;
}

void bo3_bm_vphysics_after_update(void)
{
    td_race_snapshot s;
    atomic_store(&s_have_thread, 1);
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    if (bo3_race_api()->get((td_host *)(void *)&s_self, &s) != TD_RACE_OK)
        return;
    if (atomic_load(&s_mode) == MODE_ON)
        observe(s.state);
    else
        s_prev = s.state;
}

/* ---- the table ---- */
static uint32_t TD_CALL v_count(td_host *host)
{
    return host ? (uint32_t)BM_VPHYS_CATALOG_N : 0u;
}

static int32_t TD_CALL v_info(td_host *host, uint32_t index, bm_vphys_info *out)
{
    bm_vphys_info o;
    const bm_vphys_entry *e;
    if (!host || !out || out->struct_size < 8 || index >= BM_VPHYS_CATALOG_N)
        return BM_VPHYS_BAD_ARG;
    e = &k_bm_vphys_catalog[index];
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.index = index;
    o.writable = e->writable;
    o.scale_min = e->smin;
    o.scale_max = e->smax;
    snprintf(o.name, sizeof o.name, "%s", e->full);
    snprintf(o.unit, sizeof o.unit, "%s", e->unit);
    memcpy(out, &o, o.struct_size);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_find(td_host *host, const char *name, uint32_t *index)
{
    if (!host || !name || !index)
        return BM_VPHYS_BAD_ARG;
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        if (!strcmp(name, k_bm_vphys_catalog[i].full)) {
            *index = i;
            return BM_VPHYS_OK;
        }
    return BM_VPHYS_NOT_FOUND;
}

static uint32_t racers_now(void)
{
    uint32_t n = 0;
    if (!build_ok() || !game_in_stage() || !bo3_guest_rd32(VP_CARS, &n))
        return 0;
    return n > 8u ? 8u : n;
}

static uint32_t TD_CALL v_racers(td_host *host)
{
    return host ? racers_now() : 0u;
}

static int32_t TD_CALL v_get(td_host *host, uint32_t racer, uint32_t index, bm_vphys_value *out)
{
    bm_vphys_value o;
    const bm_vphys_entry *e;
    uint32_t car = 0, veh = 0, block = 0, cur, gb;
    if (!host || !out || out->struct_size < 8 || index >= BM_VPHYS_CATALOG_N)
        return BM_VPHYS_BAD_ARG;
    if (!build_ok())
        return BM_VPHYS_UNSUPPORTED;
    if (racer >= racers_now())
        return BM_VPHYS_NO_RACER;
    e = &k_bm_vphys_catalog[index];
    memset(&o, 0, sizeof o);
    if (!bo3_guest_rd32(VP_LIST + 4u * racer, &car) || !car_ok(car, &veh, &block, o.vehicle, sizeof o.vehicle))
        return BM_VPHYS_UNAVAILABLE;
    if (!bo3_guest_rd32(veh + e->car_off, &cur) || !bo3_guest_rd32(block + e->block_off, &gb))
        return BM_VPHYS_UNAVAILABLE;
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.racer = racer;
    o.is_player1 = car == VP_CAR1;
    o.param = index;
    if (e->kind == 1 || e->kind == 2) {             /* car = cos(deg) / cos((90 - deg)): back to degrees */
        double c = bits_f(cur), d = acos(c < -1.0 ? -1.0 : c > 1.0 ? 1.0 : c) * (180.0 / 3.14159265358979323846);
        o.current = (float)(e->kind == 1 ? d : 90.0 - d);
    } else {
        o.current = bits_f(cur) / e->factor;
    }
    o.game_value = bits_f(gb);
    o.scaled = o.is_player1 && atomic_load(&s_written[index]) && cur == atomic_load(&s_want[index]);
    o.scale = o.is_player1 && atomic_load(&s_owner[index]) ? bits_f(atomic_load(&s_scale_bits[index])) : 1.0f;   /* v1.0.2: player 1 only */
    memcpy(out, &o, o.struct_size);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_set_scale(td_host *host, uint32_t index, double scale)
{
    const bm_vphys_entry *e;
    uintptr_t none = 0;
    if (!host || index >= BM_VPHYS_CATALOG_N || isnan(scale))
        return BM_VPHYS_BAD_ARG;
    if (atomic_load(&s_mode) == MODE_DEBUG)
        return BM_VPHYS_DEBUG_AUTOPILOT;
    e = &k_bm_vphys_catalog[index];
    if (!e->writable)
        return BM_VPHYS_READ_ONLY;
#if MUT != 5
    if (!(scale >= e->smin && scale <= e->smax))
        return BM_VPHYS_OUT_OF_RANGE;
#endif
#if MUT == 6
    atomic_store(&s_owner[index], (uintptr_t)host);   /* defect: takes the value over from its owner */
#else
    if (!atomic_compare_exchange_strong(&s_owner[index], &none, (uintptr_t)host) && none != (uintptr_t)host)
        return BM_VPHYS_CONFLICT;
#endif
    atomic_store(&s_pending_restore[index], 0);
    atomic_store(&s_scale_bits[index], f_bits((float)scale));
    if (atomic_load(&s_state) != BM_VPHYS_STATE_APPLIED)
        atomic_store(&s_state, BM_VPHYS_STATE_SET);
    fprintf(stderr, "[VPHYS] bmashup.vphysics: \"%s\" x%g for player 1's car, from its next car update in a race\n", e->full,
            scale);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_reset(td_host *host, uint32_t index)
{
    if (!host || index >= BM_VPHYS_CATALOG_N)
        return BM_VPHYS_BAD_ARG;
    if (!k_bm_vphys_catalog[index].writable)
        return BM_VPHYS_READ_ONLY;
    if (atomic_load(&s_owner[index]) != (uintptr_t)host)
        return BM_VPHYS_CONFLICT;
    atomic_store(&s_scale_bits[index], f_bits(1.0f));
    atomic_store(&s_pending_restore[index], 1);
    atomic_store(&s_owner[index], 0);
    fprintf(stderr, "[VPHYS] bmashup.vphysics: \"%s\" reset: player 1's car goes back to the game's value at its next car "
                    "update\n", k_bm_vphys_catalog[index].full);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_status(td_host *host, bm_vphys_status *out)
{
    bm_vphys_status o;
    if (!host || !out || out->struct_size < 8)
        return BM_VPHYS_BAD_ARG;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.state = atomic_load(&s_state);
    o.reason = atomic_load(&s_reason);
    o.race = atomic_load(&s_race);
    o.applied = atomic_load(&s_applied);
    o.reapplied = atomic_load(&s_reapplied);
    o.restored = atomic_load(&s_restored);
    o.contested = atomic_load(&s_contested);
    memcpy(out, &o, o.struct_size);
    return BM_VPHYS_OK;
}

/* ---- v2 (platform 0.1.8): the vehicle query over the game's loaded ValueDB (read only, any thread) ----
 * The registry (gp\atlas\PHYSICS.md s1; the generated code): B = MEM32(0x4A1E94) (set at boot to game + 0x83E0, the same
 * base sub_00015F10 passes to the load sub_001AF200 as ebx; sub_00132D10 reads it for every car block). The registry
 * object R = B + 0x10 (vtable slot +8 = sub_001AF040, the register-and-apply). sub_001AF0F0 (after the load into
 * B + 0xE540) sets R + 0xE520 = the record count (file + 4), R + 0xE524 = the records (file + 0x14, {u32 value, u32 key}),
 * R + 0xE528 / + 0xE52C = the file table's count / address. sub_001AEFE0 looks a key up by a SIGNED binary search; the
 * key is sub_001AF250's hash (table 0x3F7700, signed bytes, arithmetic shift) of name + group + "/" + file. A 32-bit value
 * is the record's value word itself (sub_001AF040 loc_001AF09F). */
#define VD_PTR      0x004A1E94u
#define VD_OBJ      0x10u
#define VD_COUNT    0xE530u
#define VD_RECS     0xE534u
#define VD_FCOUNT   0xE538u
#define VD_FTAB     0xE53Cu
#define VD_FILE     0xE540u
#define VD_CRC      0x003F7700u
#define VD_APPLY    0x001AF040u
#define VD_MAX_RECS (1u << 20)
#define VD_MAX_FILES 65536u

static const char *const k_vclass[] = { "COMP", "CUPE", "HEVY", "HSPC", "MSCL", "SPRT", "SUPR", "TSPC", "TRAF" };
static uint32_t s_crc[256];
static uint32_t s_vd_b;                                       /* B of the checked registry */
static char s_vname[BM_VPHYS_VEHICLES_MAX][16];
static uint8_t s_vclass_of[BM_VPHYS_VEHICLES_MAX], s_vrace[BM_VPHYS_VEHICLES_MAX];
static uint32_t s_nveh;
static _Atomic int s_vd_state;                                /* 0 not built, 1 building, 2 built */

static int vd_hash(const char *s, uint32_t *out)
{
    uint32_t h = 0xFFFFFFFFu;
    for (; *s; s++) {
        uint32_t idx = (h & 0xFFu) ^ (uint32_t)(int32_t)(signed char)*s;
        if (idx > 0xFFu)
            return 0;                                         /* a non-ASCII byte: outside the game's table */
#if MUT == 11
        h = s_crc[idx] ^ (h >> 8);                            /* defect: logical shift (the game's sar keeps the sign) */
#else
        h = s_crc[idx] ^ (uint32_t)((int32_t)h >> 8);
#endif
    }
    *out = h;
    return 1;
}

/* the game's sub_001AEFE0: 1 and the value word when the key has a record */
static int vd_lookup(uint32_t key, uint32_t *value)
{
    uint32_t n = 0, recs = 0;
    int32_t hi, lo = -1;
    if (!bo3_guest_rd32(s_vd_b + VD_COUNT, &n) || !bo3_guest_rd32(s_vd_b + VD_RECS, &recs) || !n || n > VD_MAX_RECS)
        return 0;
    hi = (int32_t)n;
    while (hi - lo > 1) {
        int32_t mid = (hi + lo) / 2;                          /* cdq / sub / sar: toward zero */
        uint32_t k = 0;
        if (!bo3_guest_rd32(recs + (uint32_t)mid * 8u + 4u, &k))
            return 0;
        if (k == key)
            return bo3_guest_rd32(recs + (uint32_t)mid * 8u, value);
#if MUT == 12
        if (k > key)                                          /* defect: unsigned order (the game compares signed) */
#else
        if ((int32_t)k > (int32_t)key)
#endif
            hi = mid;
        else
            lo = mid;
    }
    return 0;
}

static int vd_file_listed(uint32_t fkey)
{
    uint32_t n = 0, tab = 0;
    if (!bo3_guest_rd32(s_vd_b + VD_FCOUNT, &n) || !bo3_guest_rd32(s_vd_b + VD_FTAB, &tab) || n > VD_MAX_FILES)
        return 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t k = 0;
        if (!bo3_guest_rd32(tab + i * 8u + 4u, &k))
            return 0;
        if (k == fkey)
            return 1;
    }
    return 0;
}

/* the registry's structure check: 1 when the loaded ValueDB is the one this service reads */
static int vd_check(void)
{
    uint32_t b = 0, vt = 0, apply = 0, n = 0, recs = 0, hn = 0, fn = 0, ftab = 0, hfn = 0, hfo = 0;
    if (!build_ok() || !bo3_guest_rd32(VD_PTR, &b) || !b || !bo3_guest_read(VD_CRC, s_crc, sizeof s_crc))
        return 0;
    if (s_crc[0] != 0u || s_crc[1] != 0x77073096u || s_crc[255] != 0x2D02EF8Du)
        return 0;                                             /* the key table (the standard CRC-32 table) */
#if MUT != 13
    if (!bo3_guest_rd32(b + VD_OBJ, &vt) || !bo3_guest_rd32(vt + 8u, &apply) || apply != VD_APPLY)
        return 0;                                             /* (MUT 13: the registry object not verified) */
#endif
    if (!bo3_guest_rd32(b + VD_COUNT, &n) || !bo3_guest_rd32(b + VD_RECS, &recs) || !bo3_guest_rd32(b + VD_FILE + 4u, &hn) ||
        !bo3_guest_rd32(b + VD_FCOUNT, &fn) || !bo3_guest_rd32(b + VD_FTAB, &ftab) ||
        !bo3_guest_rd32(b + VD_FILE + 0xCu, &hfn) || !bo3_guest_rd32(b + VD_FILE + 0x10u, &hfo))
        return 0;
    if (!n || n > VD_MAX_RECS || n != hn || recs != b + VD_FILE + 0x14u || fn != hfn || fn > VD_MAX_FILES ||
        ftab != b + VD_FILE + hfo)
        return 0;                                             /* not loaded yet (count 0), or not this layout */
    if (!bo3_guest_window(recs, n * 8u) || !bo3_guest_window(ftab, fn * 8u))
        return 0;
    s_vd_b = b;
    return 1;
}

static int vd_key(const char *full, const char *file, uint32_t *key)
{
    char buf[256];
    const char *bar = strstr(full, " | ");
    size_t gl;
    if (!bar)
        return 0;
    gl = (size_t)(bar - full);
#if MUT == 14
    if (snprintf(buf, sizeof buf, "%s%.*s%s", bar + 3, (int)gl, full, file) >= (int)sizeof buf)   /* defect: no "/" */
#else
    if (snprintf(buf, sizeof buf, "%s%.*s/%s", bar + 3, (int)gl, full, file) >= (int)sizeof buf)
#endif
        return 0;
    return vd_hash(buf, key);
}

static uint32_t drag_index(void)
{
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        if (!strcmp(k_bm_vphys_catalog[i].full, "Physics/Race Car/Misc | Drag Coef"))
            return i;
    return 0;
}

/* the vehicle list, once (the ValueDB never changes after the boot load) */
static int vd_ready(void)
{
    int st = atomic_load(&s_vd_state), zero = 0;
    if (st == 2)
        return 1;
    if (st == 1 || !atomic_compare_exchange_strong(&s_vd_state, &zero, 1))
        return 0;                                             /* another thread builds it now */
    if (!vd_check()) {
        atomic_store(&s_vd_state, 0);
        return 0;
    }
    s_nveh = 0;
    for (uint32_t c = 0; c < sizeof k_vclass / sizeof k_vclass[0]; c++)
        for (uint32_t k = 0; k < 100u && s_nveh < BM_VPHYS_VEHICLES_MAX; k++) {
            char nm[16], file[96];
            uint32_t fkey, key, v;
            snprintf(nm, sizeof nm, "%sCAR%u", k_vclass[c], (unsigned)k);
            snprintf(file, sizeof file, k_fmt, nm);
#if MUT == 15
            if (!vd_hash(file, &fkey))
                continue;                                     /* defect: the file table not consulted (every candidate) */
#else
            if (!vd_hash(file, &fkey) || !vd_file_listed(fkey))
                continue;
#endif
            snprintf(s_vname[s_nveh], sizeof s_vname[s_nveh], "%s", nm);
            s_vclass_of[s_nveh] = (uint8_t)c;
            s_vrace[s_nveh] = vd_key(k_bm_vphys_catalog[drag_index()].full, file, &key) && vd_lookup(key, &v);
            s_nveh++;
        }
    fprintf(stderr, "[VPHYS] bmashup.vphysics 2: the ValueDB vehicle query: %u vehicles\n", (unsigned)s_nveh);
    atomic_store(&s_vd_state, 2);
    return 1;
}

static uint32_t TD_CALL v_vehicle_count(td_host *host)
{
    return host && vd_ready() ? s_nveh : 0u;
}

static int32_t TD_CALL v_vehicle_info(td_host *host, uint32_t vehicle, bm_vphys_vehicle_info *out)
{
    bm_vphys_vehicle_info o;
    if (!host || !out || out->struct_size < 8)
        return BM_VPHYS_BAD_ARG;
    if (!vd_ready())
        return BM_VPHYS_UNAVAILABLE;
    if (vehicle >= s_nveh)
        return BM_VPHYS_NO_VEHICLE;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.index = vehicle;
    snprintf(o.name, sizeof o.name, "%s", s_vname[vehicle]);
    o.series_class = s_vclass_of[vehicle];
    o.added = 0;
    o.open = BM_VEH_OPEN_UNKNOWN;
    o.race_vehicle = s_vrace[vehicle];
    memcpy(out, &o, o.struct_size);
    return BM_VPHYS_OK;
}

static int32_t TD_CALL v_vehicle_find(td_host *host, const char *name, uint32_t *vehicle)
{
    if (!host || !name || !vehicle)
        return BM_VPHYS_BAD_ARG;
    if (!vd_ready())
        return BM_VPHYS_UNAVAILABLE;
    for (uint32_t i = 0; i < s_nveh; i++)
        if (!strcmp(name, s_vname[i])) {
            *vehicle = i;
            return BM_VPHYS_OK;
        }
    return BM_VPHYS_NO_VEHICLE;
}

static int32_t TD_CALL v_vehicle_value(td_host *host, uint32_t vehicle, uint32_t index, bm_vphys_vehicle_value *out)
{
    bm_vphys_vehicle_value o;
    char file[96];
    uint32_t key, word = 0;
    int have;
    if (!host || !out || out->struct_size < 8 || index >= BM_VPHYS_CATALOG_N)
        return BM_VPHYS_BAD_ARG;
    if (!vd_ready())
        return BM_VPHYS_UNAVAILABLE;
    if (vehicle >= s_nveh)
        return BM_VPHYS_NO_VEHICLE;
    snprintf(file, sizeof file, k_fmt, s_vname[vehicle]);
    if (!vd_key(k_bm_vphys_catalog[index].full, file, &key))
        return BM_VPHYS_UNAVAILABLE;
    have = vd_lookup(key, &word);
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.vehicle = vehicle;
    o.param = index;
#if MUT == 16
    o.have = 1;                                               /* defect: a missing record reported as a value (0) */
    have = 1;
#else
    o.have = have ? 1u : 0u;
#endif
    if (have) {
        o.game_value = (double)bits_f(word);
        o.value = o.game_value;
    }
    o.scaled = 0;
    memcpy(out, &o, o.struct_size);
    return have ? BM_VPHYS_OK : BM_VPHYS_NO_VALUE;
}

static const bm_vphys_api s_api = {
    (uint32_t)sizeof(bm_vphys_api), BM_VPHYS_VERSION, v_count, v_info, v_find, v_racers, v_get, v_set_scale, v_reset, v_status,
    v_vehicle_count, v_vehicle_info, v_vehicle_find, v_vehicle_value,
    v_set_gearbox, v_request_gear, v_gearbox_status       /* v3 */
};

const bm_vphys_api *bo3_bm_vphysics_api(void)
{
    return &s_api;
}

static void vphys_writer(void *user)
{
    (void)user;
    bo3_bm_vphysics_car_update();
}

void bo3_bm_vphysics_init(int debug_autopilot)
{
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++) {
        atomic_store(&s_owner[i], 0);
        atomic_store(&s_scale_bits[i], f_bits(1.0f));
        atomic_store(&s_pending_restore[i], 0);
        atomic_store(&s_written[i], 0);
        atomic_store(&s_want[i], 0);
        s_applied_race[i] = 0;
        s_contested_logged[i] = 0;
    }
    atomic_store(&s_state, BM_VPHYS_STATE_IDLE);
    atomic_store(&s_reason, BM_VPHYS_OK);
    atomic_store(&s_race, 0);
    atomic_store(&s_applied, 0);
    atomic_store(&s_reapplied, 0);
    atomic_store(&s_restored, 0);
    atomic_store(&s_contested, 0);
    atomic_store(&s_have_thread, 0);
    atomic_store(&s_vd_state, 0);                             /* v2: the vehicle list is built at its first use */
    atomic_store(&s_gbx_owner, 0);                            /* v3 */
    atomic_store(&s_gbx_req, 0);
    atomic_store(&s_gbx_g, 0);
    atomic_store(&s_gbx_skips, 0);
    atomic_store(&s_gbx_census_ok, -1);
    s_gbx_logged = 0;
    s_nveh = 0;
    s_prev = TD_RACE_NONE;
    s_refuse_logged = s_reapply_logged = 0;
    if (debug_autopilot) {
        atomic_store(&s_mode, MODE_DEBUG);
        fprintf(stderr, "[VPHYS] bmashup.vphysics: control off (RECOMP_DEBUG=autopilot holds the car update); query on\n");
    } else {
        int mark = bo3_events_hook("ap_update");
        if (mark < 0 || bo3_events_subscribe(mark, BO3_EVENT_WRITER, vphys_writer, NULL, "bmashup.vphysics") != 0) {
            atomic_store(&s_mode, MODE_OFF);
            fprintf(stderr, "[VPHYS] bmashup.vphysics: control off (the car-update mark is not available); query on\n");
        } else {
            atomic_store(&s_mode, MODE_ON);
        }
    }
    bo3_plugins_service(BM_VPHYS_SERVICE, BM_VPHYS_VERSION, &s_api);
    {
        unsigned w = 0;
        for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
            w += k_bm_vphys_catalog[i].writable;
        fprintf(stderr, "[VPHYS] bmashup.vphysics %u (1.0.2): %u per-car physics values, %u writable; gearbox %s\n",
                (unsigned)BM_VPHYS_VERSION, (unsigned)BM_VPHYS_CATALOG_N, w,
                BO3_HOOKREQ_P23 ? "on (player 1, census at first use)" : "off (BO3_HOOKREQ_P23=OFF)");
    }
}
