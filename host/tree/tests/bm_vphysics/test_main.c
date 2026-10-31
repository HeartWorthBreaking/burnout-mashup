/* tests/bm_vphysics - the private "bmashup.vphysics" service (src/game/bm_vphysics.c) over the real dispatcher
 * (bm_events.c), the real takedawn.race snapshot (race_service.c), the real guest access checks (bm_guest.c) and the
 * game's OWN copy of a vehicle's physics block into a car: the generated sub_00134710, extracted unchanged
 * (gen_copy.c). Stand-in guest memory; no game data. "No write" is checked over the whole stand-in memory. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_events.h"
#include "bm_vphys_catalog.h"
#include "bm_vphysics.h"
#include "race_service.h"
#include "recomp_types.h"

ptrdiff_t g_xbox_mem_offset;
RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp, g_ebx, g_esi, g_edi, g_ebp, g_seh_ebp;
RECOMP_TLS RecompXmm g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7;
RECOMP_TLS double g_fp_stack[8];
RECOMP_TLS int g_fp_top, g_df;
RECOMP_TLS uint16_t g_fp_cc;
void bo3_lanes_after_update(void) {}       /* race_service.c's LANELIFE-C diagnostic: not this test's */

#define GMEM 0x00800000u
static uint8_t *s_mem, *s_copy;
size_t xbox_GetMappedSize(void) { return GMEM; }
uint32_t xbox_ContiguousBlockSize(uint32_t va) { (void)va; return 0; }
#define M8(va)  (*(uint8_t *)(s_mem + (uint32_t)(va)))
#define M32(va) (*(uint32_t *)(s_mem + (uint32_t)(va)))
#define MF(va)  (*(float *)(s_mem + (uint32_t)(va)))

#define STATE    0x004D53B4u
#define MODULE   0x004D5370u
#define MODOBJ   0x00200000u
#define VT_GAME  0x003A9ACCu
#define PAUSED   0x004D537Cu
#define STEP     0x004A1EB4u
#define CARS     0x0073A19Cu
#define LIST     0x0073A1A8u
#define CAR      0x0073A1D0u
#define CAR2     0x00740000u
#define VT_CAR   0x003B11A0u
#define PHASE    0x134Cu
#define BLOCK1   0x00500000u
#define BLOCK2   0x00500400u
#define VEH1     0x00667E90u      /* player 1's physics vehicle: physics world 0x64B310 + 0x1CB80 (player pool, n 0) */
#define VEH2     0x00673F30u      /* an AI racer's: 0x64B310 + 0x26120 + 2 x 0x1580 (sub_001A99F0; v1.0.1 looked at + 0x27120) */
#define VEH3     0x00677FB0u      /* a third racer's: 0x64B310 + 0x2CCA0 (the 0x1560 pool, slot 0) */
#define DECOY    0x0066C960u      /* player slot 1 (0x64B310 + 0x1CB80 + 0x4AD0) with the base vtable 0x3B1188 */
#define CAR3     0x00744000u
#define BLOCK3   0x00500800u
#define STACK    0x00100000u
#define FMT      0x003AC65Cu

extern void sub_00134710(void);

static int s_pass, s_fail;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); \
    printf("\n"); } } while (0)

static const void *s_table;
static uint32_t s_version;
int bo3_plugins_service(const char *name, uint32_t version, const void *table)
{
    if (!strcmp(name, BM_VPHYS_SERVICE)) {
        s_table = table;
        s_version = version;
    }
    return 1;
}

static void (*s_mark)(void);
void recomp_patch_on_mark(const char *name, void (*fn)(void))
{
    if (!strcmp(name, "ap_update"))
        s_mark = fn;
}

static const bm_vphys_api *A;
static int s_plugin, s_other;
#define HOST  ((td_host *)(void *)&s_plugin)
#define OTHER ((td_host *)(void *)&s_other)
static uint32_t i_drag, i_boost, i_mass;

static void sig(void)
{
    M32(0x003B11A0u) = 0x0018C470u;
    M32(0x003B11A4u) = 0x0018C510u;
    M32(0x003A9ACCu) = 0x00019FE0u;
    M32(0x003A9AD0u) = 0x0001A000u;
    M32(0x003B1178u) = 0x001177B0u;     /* v1.0.1 build word */
    M32(0x003B1258u) = 0x001049A0u;     /* v1.0.2 build words */
    M32(0x003B1150u) = 0x0010EDF0u;
    strcpy((char *)s_mem + FMT, "../Export/ValueDB/VehiclePhysics/%s.cfg");
    M32(0x003B17B8u) = 0x3DD67750u;     /* .rdata constants sub_00134710 reads (retail XBE 0x3B17B8: 2 pi / 60) */
    M32(0x003A1248u) = 0x3C8EFA35u;     /* (0x3A1248: pi / 180) */
    M32(0x003B1850u) = 0x42B40000u;     /* (0x3B1850: 90.0) */
}

static void block(uint32_t b, uint32_t info, const char *stem, float base, uint32_t id)
{
    sprintf((char *)s_mem + b, "../Export/ValueDB/VehiclePhysics/%s.cfg", stem);
    M32(b + 0xB0) = id;
    M32(b + 0xB4) = 0x00C0FFEEu;
    M32(info + 0x1970) = id;
    M32(info + 0x1974) = 0x00C0FFEEu;
    for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++)
        MF(b + k_bm_vphys_catalog[i].block_off) = base + (float)i;
}

/* sub_0011A8F0 on physics vehicle V for racer R: V + 0x13F4 = R, then the game's copy (sub_00134710: eax = V, ecx the
 * block; the real generated code), V + 0x13F8 = the block */
static void game_copy(uint32_t car, uint32_t r, uint32_t b)
{
    uint32_t sp = STACK;
    M32(car + 0x13F4) = r;
    g_eax = car;
    g_ecx = b;
    g_esp = sp;
    M8(car + 0x1169) = 4;
    sub_00134710();
    M32(car + 0x13F8) = b;      /* sub_0011A8F0 stores the block */
}

static void game(uint32_t phase)
{
    M32(STATE) = 5;
    M32(MODULE) = MODOBJ;
    M32(MODOBJ) = VT_GAME;
    M32(MODOBJ + 0x1B8u) = 0x00300000u;
    M32(PAUSED) = 0xFFFFFFFFu;
    M32(CAR) = VT_CAR;
    M32(CAR + 0x27D0u) = 0;
    M32(CAR + PHASE) = phase;
    M32(CARS) = 3;
    M32(LIST) = CAR;
    M32(LIST + 4) = CAR2;
    M32(LIST + 8) = CAR3;
    MF(CAR + 0x10u + 15 * 4) = 1.0f;
}

static void tick(int car)
{
    M32(STEP) += 1;
    if (car && s_mark) {
        g_esi = CAR2;           /* another player car's update: never touched */
        s_mark();
        g_esi = CAR;
        s_mark();
    }
    bo3_race_after_update();
    bo3_bm_vphysics_after_update();
}

static void snap(void) { memcpy(s_copy, s_mem, GMEM); }
static uint32_t diffs(uint32_t *first)
{
    uint32_t n = 0;
    for (uint32_t k = 0; k < GMEM; k += 4)
        if (memcmp(s_mem + k, s_copy + k, 4)) {
            if (!n && first)
                *first = k;
            n++;
        }
    return n;
}

static bm_vphys_status st(void)
{
    bm_vphys_status s;
    s.struct_size = sizeof s;
    A->status(HOST, &s);
    return s;
}

static float car_val(uint32_t car, uint32_t i)
{
    return MF(car + k_bm_vphys_catalog[i].car_off);
}

int main(void)
{
    bm_vphys_info inf;
    bm_vphys_value v;
    uint32_t idx, first = 0;
    s_mem = (uint8_t *)calloc(1, GMEM);
    s_copy = (uint8_t *)calloc(1, GMEM);
    if (!s_mem || !s_copy)
        return 2;
    g_xbox_mem_offset = (ptrdiff_t)s_mem;
    sig();

    /* --- debug mode: query only --- */
    bo3_bm_vphysics_init(1);
    A = (const bm_vphys_api *)s_table;
    CHECK(A && s_version == BM_VPHYS_VERSION && A->version >= 2 && A->struct_size == sizeof(bm_vphys_api), "offered");
    CHECK(A->find(HOST, "Physics/Race Car/Misc | Drag Coef", &i_drag) == BM_VPHYS_OK, "find drag");
    CHECK(A->set_scale(HOST, i_drag, 0.5) == BM_VPHYS_DEBUG_AUTOPILOT, "debug: control off");

    /* --- normal mode --- */
    bo3_events_reset_for_test();
    bo3_bm_vphysics_init(0);
    bo3_events_close();
    CHECK(s_mark != NULL, "the car-update mark is hooked");
    CHECK(A->count(HOST) == 64 && A->count(NULL) == 0, "count %u", A->count(HOST));
    CHECK(A->find(HOST, "Physics/Race Car/Misc | Max Speed In Boost", &i_boost) == BM_VPHYS_OK, "find boost");
    CHECK(A->find(HOST, "Physics/Vehicle | Mass (Kg)", &i_mass) == BM_VPHYS_OK, "find mass");
    CHECK(A->find(HOST, "nope", &idx) == BM_VPHYS_NOT_FOUND, "find none");
    inf.struct_size = sizeof inf;
    CHECK(A->info(HOST, i_drag, &inf) == BM_VPHYS_OK && inf.writable && inf.scale_min == 0.25f && inf.scale_max == 4.0f &&
          !strcmp(inf.name, "Physics/Race Car/Misc | Drag Coef"), "info drag");
    CHECK(A->info(HOST, i_boost, &inf) == BM_VPHYS_OK && inf.writable && !strcmp(inf.unit, "mph"), "info boost");
    CHECK(A->info(HOST, i_mass, &inf) == BM_VPHYS_OK && !inf.writable && !strcmp(inf.unit, "kg"), "info mass");
    CHECK(A->info(HOST, 64, &inf) == BM_VPHYS_BAD_ARG, "info range");
    inf.struct_size = 12;
    CHECK(A->info(HOST, i_drag, &inf) == BM_VPHYS_OK && inf.struct_size == 12, "short struct");

    /* not in a race: nothing */
    v.struct_size = sizeof v;
    CHECK(A->racers(HOST) == 0, "no racers outside a race");
    CHECK(A->get(HOST, 0, i_drag, &v) == BM_VPHYS_NO_RACER, "get outside a race");
    CHECK(A->set_scale(HOST, i_drag, 0.2) == BM_VPHYS_OUT_OF_RANGE, "below min");
    CHECK(A->set_scale(HOST, i_drag, 4.5) == BM_VPHYS_OUT_OF_RANGE, "above max");
    CHECK(A->set_scale(HOST, i_drag, NAN) == BM_VPHYS_BAD_ARG, "nan");
    CHECK(A->set_scale(HOST, i_mass, 1.0) == BM_VPHYS_READ_ONLY, "mass read only");
    CHECK(A->reset(HOST, i_drag) == BM_VPHYS_CONFLICT, "reset of nothing owned");
    CHECK(A->set_scale(HOST, i_drag, 0.5) == BM_VPHYS_OK, "set drag");
    CHECK(A->set_scale(OTHER, i_drag, 0.5) == BM_VPHYS_CONFLICT, "other plugin refused");
    CHECK(A->reset(OTHER, i_drag) == BM_VPHYS_CONFLICT, "other plugin cannot reset");
    CHECK(st().state == BM_VPHYS_STATE_SET, "state set");
    snap();
    tick(1);
    CHECK(diffs(NULL) == 1, "menus: only the step count changed");   /* the step word */

    /* --- a race: the game sets the cars up (the real copy) --- */
    block(BLOCK1, CAR, "COMPCAR1", 100.0f, 0x1111u);
    block(BLOCK2, CAR2, "SPRTCAR1", 500.0f, 0x2222u);
    block(BLOCK3, CAR3, "MSCLCAR2", 900.0f, 0x3333u);
    M32(VEH1) = 0x003B1160u;            /* the pools' final vtables (sub_001A99F0) */
    M32(VEH2) = 0x003B1240u;
    M32(VEH3) = 0x003B1138u;
    M32(DECOY) = 0x003B1188u;           /* a decoy pointing back at the AI racer, its block another vehicle's */
    M32(DECOY + 0x13F4) = CAR2;
    M32(DECOY + 0x13F8) = BLOCK1;
    M32(CAR3 + 0x13F8) = 0;
    /* the racer objects hold no physics block (v1.0.0 read the block from here: the gp_p4_1 refusal) */
    M32(CAR + 0x13F8) = 0;
    M32(CAR2 + 0x13F8) = 0;
    game(1);
    game_copy(VEH1, CAR, BLOCK1);
    game_copy(VEH2, CAR2, BLOCK2);
    game_copy(VEH3, CAR3, BLOCK3);
    {
        int ok = 1;
        for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++) {
            const bm_vphys_entry *e = &k_bm_vphys_catalog[i];
            float x = 100.0f + (float)i, deg = 0.0174532924f;
            float want = e->kind == 1 ? (float)cos((double)(x * deg)) : e->kind == 2 ? (float)cos((double)((90.0f - x) * deg))
                                                                                       : x * e->factor;
            if (car_val(VEH1, i) != want) {
                ok = 0;
                printf("  catalogue %u %s: car %g, block x factor %g\n", i, e->full, (double)car_val(VEH1, i), (double)want);
            }
        }
        CHECK(ok, "every catalogue entry = the real generated copy (offsets and factors)");
    }
    tick(0);
    CHECK(A->racers(HOST) == 3, "racers %u", A->racers(HOST));
    v.struct_size = sizeof v;
    CHECK(A->get(HOST, 1, i_drag, &v) == BM_VPHYS_OK && !v.is_player1 && v.current == v.game_value &&
          !strcmp(v.vehicle, "SPRTCAR1") && !v.scaled && v.game_value == 500.0f + (float)i_drag, "AI car query");
    v.struct_size = sizeof v;
    CHECK(A->get(HOST, 2, i_drag, &v) == BM_VPHYS_OK && !v.is_player1 && !strcmp(v.vehicle, "MSCLCAR2") &&
          v.current == 900.0f + (float)i_drag, "racer in the 0x1560 pool");
    {
        int ok = 1;
        for (uint32_t i = 0; i < BM_VPHYS_CATALOG_N; i++) {
            v.struct_size = sizeof v;
            const bm_vphys_entry *e = &k_bm_vphys_catalog[i];
            int rc = A->get(HOST, 0, i, &v);
            double c = v.current, g = v.game_value, k = 3.14159265358979 / 180.0;
            if (e->kind == 1) {                     /* a cosine: equal as cosines (acos is unique on 0..180 only) */
                c = cos(c * k);
                g = cos(g * k);
            } else if (e->kind == 2) {
                c = cos((90.0 - c) * k);
                g = cos((90.0 - g) * k);
            }
            if (rc != BM_VPHYS_OK || fabs(c - g) > 1e-3 * (1.0 + fabs(g))) {
                ok = 0;
                printf("  get %u %s: current %g game %g\n", i, k_bm_vphys_catalog[i].full, (double)v.current, (double)v.game_value);
            }
        }
        CHECK(ok, "get(): every value back in the ValueDB's units (factors, cos kinds)");
    }
    snap();
    tick(1);    /* player 1's car update in the countdown: the scale applies */
    {
        float g = 100.0f + (float)i_drag;
        uint32_t n = diffs(&first);
        CHECK(car_val(VEH1, i_drag) == g * 0.5f, "drag scaled: %g", (double)car_val(VEH1, i_drag));
        CHECK(n == 2, "only the step and the car's drag written (%u, first 0x%X)", n, first);
        CHECK(car_val(VEH2, i_drag) == 500.0f + (float)i_drag && car_val(VEH3, i_drag) == 900.0f + (float)i_drag,
              "the AI cars untouched (v1 writes player 1 only)");
        v.struct_size = sizeof v;
        CHECK(A->get(HOST, 1, i_drag, &v) == BM_VPHYS_OK && !v.scaled && v.scale == 1.0f && v.current == v.game_value,
              "AI query while player 1 is scaled: its own value, not scaled");
        CHECK(MF(BLOCK1 + k_bm_vphys_catalog[i_drag].block_off) == g, "the block untouched");
        CHECK(st().state == BM_VPHYS_STATE_APPLIED && st().applied == 1, "applied");
        CHECK(A->get(HOST, 0, i_drag, &v) == BM_VPHYS_OK && v.is_player1 && v.scaled && v.scale == 0.5f &&
              v.game_value == g && v.current == g * 0.5f && !strcmp(v.vehicle, "COMPCAR1"), "player query");
    }
    snap();
    tick(1);
    CHECK(diffs(NULL) == 1 && st().applied == 1, "steady: nothing written");

    /* the game copies its values again (a reset): written again, counted */
    game_copy(VEH1, CAR, BLOCK1);
    tick(1);
    CHECK(car_val(VEH1, i_drag) == (100.0f + (float)i_drag) * 0.5f && st().reapplied == 1, "reapplied after the game's copy");

    /* the scale changed by its owner */
    CHECK(A->set_scale(HOST, i_drag, 0.25) == BM_VPHYS_OK, "owner changes the scale");
    tick(1);
    CHECK(car_val(VEH1, i_drag) == (100.0f + (float)i_drag) * 0.25f, "new scale");
    CHECK(A->set_scale(HOST, i_drag, 0.5) == BM_VPHYS_OK, "back to 0.5");
    tick(1);

    /* the second writable value, and sub_0011A8F0's own re-copy of it */
    CHECK(A->set_scale(HOST, i_boost, 1.5) == BM_VPHYS_OK, "boost speed scale");
    tick(1);
    CHECK(car_val(VEH1, i_boost) == (100.0f + (float)i_boost) * 1.5f, "boost speed scaled");
    MF(VEH1 + 0x13D4) = MF(BLOCK1 + 0x1A4);      /* sub_0011A8F0: the car's Max Speed In Boost from the block */
    tick(1);
    CHECK(car_val(VEH1, i_boost) == (100.0f + (float)i_boost) * 1.5f, "boost speed applied again after the reset copy");

    /* another writer: left alone */
    MF(VEH1 + k_bm_vphys_catalog[i_drag].car_off) = 7.0f;
    tick(1);
    CHECK(car_val(VEH1, i_drag) == 7.0f && st().contested >= 1, "contested value left alone");
    MF(VEH1 + k_bm_vphys_catalog[i_drag].car_off) = (100.0f + (float)i_drag) * 0.5f;
    tick(1);

    /* the structure check fails: nothing written */
    M32(BLOCK1 + 0xB0) = 0x9999u;
    game_copy(VEH1, CAR, BLOCK1);
    snap();
    tick(1);
    CHECK(diffs(NULL) == 1 && st().state == BM_VPHYS_STATE_REFUSED && st().reason == BM_VPHYS_UNSUPPORTED,
          "block of another vehicle: refused, nothing written");
    M32(BLOCK1 + 0xB0) = 0x1111u;
    strcpy((char *)s_mem + BLOCK1, "../Export/ValueDB/VehicleAudio/COMPCAR1.cfg");
    snap();
    tick(1);
    CHECK(diffs(NULL) == 1 && st().state == BM_VPHYS_STATE_REFUSED, "not a VehiclePhysics block: refused");
    strcpy((char *)s_mem + BLOCK1, "../Export/ValueDB/VehiclePhysics/COMPCAR1.cfg");
    M8(FMT + 20) ^= 1;
    snap();
    tick(1);
    CHECK(diffs(NULL) == 1 && st().reason == BM_VPHYS_UNSUPPORTED, "unknown build: refused");
    v.struct_size = sizeof v;
    CHECK(A->get(HOST, 0, i_drag, &v) == BM_VPHYS_UNSUPPORTED, "unknown build: no query");
    M8(FMT + 20) ^= 1;
    tick(1);
    CHECK(car_val(VEH1, i_drag) == (100.0f + (float)i_drag) * 0.5f && st().state == BM_VPHYS_STATE_APPLIED, "applies again");

    /* the race is left: the copies go back to the game's values */
    M32(STATE) = 6;
    snap();
    tick(0);
    CHECK(car_val(VEH1, i_drag) == 100.0f + (float)i_drag && car_val(VEH1, i_boost) == 100.0f + (float)i_boost,
          "restored at race exit");
    CHECK(diffs(NULL) == 3 && st().restored == 2, "exactly the two values (+ step) restored (%u)", st().restored);

    /* a new race: applies again; reset() by the owner restores in the car update */
    game(1);
    game_copy(VEH1, CAR, BLOCK1);
    tick(0);
    tick(1);
    CHECK(car_val(VEH1, i_drag) == (100.0f + (float)i_drag) * 0.5f && st().race == 2, "second race applied (race %u)", st().race);
    CHECK(A->reset(HOST, i_drag) == BM_VPHYS_OK, "reset");
    tick(1);
    CHECK(car_val(VEH1, i_drag) == 100.0f + (float)i_drag, "reset restores");
    CHECK(A->set_scale(OTHER, i_drag, 2.0) == BM_VPHYS_OK, "free again: another plugin may own it");
    tick(1);
    CHECK(car_val(VEH1, i_drag) == (100.0f + (float)i_drag) * 2.0f, "other owner's scale");

    /* the race left while the physics vehicle no longer points back to the racer: nothing written, said */
    M32(VEH1 + 0x13F4) = 0;
    M32(STATE) = 6;
    snap();
    tick(0);
    CHECK(diffs(NULL) == 1, "car gone: nothing restored, nothing written");

    printf("bm_vphysics: %d passed, %d failed\n", s_pass, s_fail);
    return s_fail ? 1 : 0;
}
