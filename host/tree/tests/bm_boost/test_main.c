/* tests/bm_boost - Burnout Mashup's private "bmashup.boost" service
 * (src/game/bm_boost.c, through bm_autopilot.c's car-update handler, over the
 * real race_service.c) against a stand-in for the game's memory. Each game
 * update is played the way the game runs it: the car updates (the
 * "ap_update" mark: player 2's, then player 1's), then the takedawn.race
 * snapshot and its on_update calls (where a plugin asks), then the services'
 * after-updates. The game's add-boost routine, sub_0017A530, is a stand-in
 * that records how it was called, adds as the game's does (clamped to the
 * maximum) unless its gate is set to decline, and changes every register it
 * may. "No write" is checked over the whole stand-in memory. No game data. */
#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_autopilot.h"
#include "bm_boost.h"
#include "race_service.h"
#include "recomp_types.h"

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#endif

ptrdiff_t g_xbox_mem_offset;
RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp, g_ebx, g_esi, g_edi, g_ebp;
RECOMP_TLS RecompXmm g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7;
RECOMP_TLS double g_fp_stack[8];
RECOMP_TLS int g_fp_top;

#define GMEM 0x00800000u
static uint8_t *s_mem, *s_copy;
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
#define CAR      0x0073A1D0u
#define CAR2     0x0073C9B0u
#define VT_CAR   0x003B11A0u
#define PLAYER   0x27D0u
#define PHASE    0x134Cu
#define AI       0x27D8u
#define BLOCK    (CAR + 0x119Cu)
#define BAR      (BLOCK + 0x38u)
#define BAR_MAX  (BLOCK + 0x34u)
#define TOTAL    (BLOCK + 0x3Cu)
#define ACTIVE   (BLOCK + 0x52u)
#define STACK    0x00100000u

static int s_pass, s_fail;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); \
    printf("\n"); } } while (0)

/* plugins.c's, played here: what is offered */
static const void *s_bb_table, *s_ap_table;
static const char *s_bb_name;
static uint32_t s_bb_version;
int bo3_plugins_service(const char *name, uint32_t version, const void *table)
{
    if (!strcmp(name, "bmashup.boost")) {
        s_bb_name = name;
        s_bb_version = version;
        s_bb_table = table;
    } else if (!strcmp(name, "bmashup.autopilot")) {
        s_ap_table = table;
    }
    return 1;
}

static void (*s_mark)(void);
static int s_marks_registered;
void recomp_patch_on_mark(const char *name, void (*fn)(void))
{
    if (!strcmp(name, "ap_update")) {
        s_mark = fn;
        s_marks_registered++;
    }
}

/* the title's sub_00179760 (bm_autopilot.c's takeover), played here */
static int s_takeovers;
void sub_00179760(void)
{
    s_takeovers++;
    g_esp += 4;
    g_ecx = 0xDEAD0011u;
}

/* the title's sub_0017A530 (add boost), played here */
static int s_calls, s_call_ret0, s_gate_no;
static uint32_t s_call_esi, s_call_arg;
void sub_0017A530(void)
{
    uint32_t b = g_esi;
    float amount;
    s_calls++;
    s_call_esi = b;
    s_call_ret0 = M32(g_esp) == 0;
    s_call_arg = M32(g_esp + 4);
    memcpy(&amount, &s_call_arg, 4);
    if (!s_gate_no) {
        MF(b + 0x3C) += amount;
        MF(b + 0x38) += amount;
        if (MF(b + 0x38) > MF(b + 0x34))
            MF(b + 0x38) = MF(b + 0x34);
    }
    g_esp += 8;                                     /* ret 4 */
    g_eax = 0xDEAD0001u;                            /* what a call may change */
    g_ebx = 0xDEAD0002u;
    g_ecx = 0xDEAD0003u;
    g_edx = 0xDEAD0004u;
    g_esi = 0xDEAD0005u;
    g_edi = 0xDEAD0006u;
    g_ebp = 0xDEAD0007u;
    g_xmm0.f[0] = 99.0f;
    g_xmm1.f[0] = 98.0f;
    g_xmm7.f[0] = 97.0f;
    g_fp_top = (g_fp_top + 3) & 7;
}

static const bm_boost_api *s_api;
static const bm_autopilot_api *s_ap;
static const td_race_api *s_race;
static int s_plugin;
#define HOST ((td_host *)(void *)&s_plugin)

static void sig(void)
{
    M32(0x003B11A0u) = 0x0018C470u;
    M32(0x003B11A4u) = 0x0018C510u;
    M32(0x003A9ACCu) = 0x00019FE0u;
    M32(0x003A9AD0u) = 0x0001A000u;
}

static void game(uint32_t phase)
{
    M32(STATE) = 5;
    M32(MODULE) = MODOBJ;
    M32(MODOBJ) = VT_GAME;
    M32(MODOBJ + 0x1B8u) = 0x00300000u;
    M32(PAUSED) = 0xFFFFFFFFu;
    M32(CAR) = VT_CAR;
    M32(CAR + PLAYER) = 0;
    M32(CAR + PHASE) = phase;
    M32(CARS) = 6;
    MF(CAR + 0x10u + 15 * 4) = 1.0f;
}

static int s_want, s_want_ap;
static int32_t s_rc = -1, s_ap_rc = -1;
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    (void)snap;
    (void)user;
    if (s_want_ap) {
        s_want_ap = 0;
        s_ap_rc = s_ap->engage(HOST);
    }
    if (s_want) {
        s_want = 0;
        s_rc = s_api->fill(HOST);
    }
}

static void tick_n(uint32_t steps, int car)
{
    M32(STEP) += steps;
    if (car && s_mark) {
        g_esi = CAR2;
        s_mark();
        g_esi = CAR;
        s_mark();
    }
    bo3_race_after_update();
    bo3_bm_autopilot_after_update();
    bo3_bm_boost_after_update();
}
static void tick(int car) { tick_n(1, car); }

static int32_t fill_in_update(int car)
{
    s_want = 1;
    s_rc = -1;
    tick(car);
    return s_rc;
}

static bm_boost_status st(void)
{
    bm_boost_status s;
    memset(&s, 0xEE, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    if (s_api->status(HOST, &s) != BM_BOOST_OK)
        memset(&s, 0xFF, sizeof s);
    return s;
}

static void snap_mem(void) { memcpy(s_copy, s_mem, GMEM); }
/* The whole memory against the copy, but for the step count (the test's own
 * clock) and what the game's routine itself writes (the bar, its total, the
 * two stack words of the call). */
static int mem_same(void)
{
    memcpy(s_copy + STEP, s_mem + STEP, 4);
    return !memcmp(s_copy, s_mem, GMEM);
}
static int mem_same_but_routine(void)
{
    memcpy(s_copy + STEP, s_mem + STEP, 4);
    memcpy(s_copy + BAR, s_mem + BAR, 4);
    memcpy(s_copy + TOTAL, s_mem + TOTAL, 4);
    memcpy(s_copy + STACK - 8, s_mem + STACK - 8, 8);
    return !memcmp(s_copy, s_mem, GMEM);
}

static int same_float(float a, float b) { return fabsf(a - b) < 0.001f; }

/* ---- another thread ---- */
static _Atomic int s_stop;
static long s_reads, s_torn, s_wrong_ok;
static int32_t s_thread_rc;
#if defined(_WIN32)
static DWORD WINAPI th_fill(LPVOID arg)
#else
static void *th_fill(void *arg)
#endif
{
    (void)arg;
    s_thread_rc = s_api->fill(HOST);
#if defined(_WIN32)
    return 0;
#else
    return NULL;
#endif
}
#if defined(_WIN32)
static DWORD WINAPI th_reader(LPVOID arg)
#else
static void *th_reader(void *arg)
#endif
{
    (void)arg;
    while (!s_stop) {
        bm_boost_status s;
        s.struct_size = (uint32_t)sizeof s;
        if (s_api->status(HOST, &s) != BM_BOOST_OK)
            continue;
        s_reads++;
        /* each update writes one number k into the bar and its maximum */
        if (s.state > BM_BOOST_STATE_REFUSED || s.fills > BM_BOOST_FILLS_MAX
                || (s.have_meter && s.meter != s.meter_max) || s.struct_size != sizeof s)
            s_torn++;
        if (s_api->fill(HOST) == BM_BOOST_OK)
            s_wrong_ok++;
    }
#if defined(_WIN32)
    return 0;
#else
    return NULL;
#endif
}
#if defined(_WIN32)
static HANDLE s_th;
static void th_start(int reader) { s_th = CreateThread(NULL, 0, reader ? th_reader : th_fill, NULL, 0, NULL); }
static void th_join(void) { WaitForSingleObject(s_th, INFINITE); CloseHandle(s_th); }
#else
static pthread_t s_th;
static void th_start(int reader) { pthread_create(&s_th, NULL, reader ? th_reader : th_fill, NULL); }
static void th_join(void) { pthread_join(s_th, NULL); }
#endif

/* a running race with the bar at `bar` of 240, nothing boosting */
#define FRESH(bar) do { game(2); MF(BAR) = (bar); MF(BAR_MAX) = 240.0f; M8(ACTIVE) = 0; tick(0); } while (0)
/* a new race (the countdown, then the GO) */
#define NEW_RACE(bar) do { game(0); tick(0); FRESH(bar); } while (0)

int main(void)
{
    bm_boost_status s;
    uint32_t race0;
    float amount;

    setvbuf(stdout, NULL, _IONBF, 0);
    s_mem = calloc(1, GMEM);
    s_copy = calloc(1, GMEM);
    if (!s_mem || !s_copy)
        return 2;
    g_xbox_mem_offset = (ptrdiff_t)s_mem;
    g_esp = STACK;
    sig();
    s_api = bo3_bm_boost_api();
    s_ap = bo3_bm_autopilot_api();
    s_race = bo3_race_api();

    /* the table and the header's sizes */
    CHECK(sizeof(bm_boost_status) == 44 && offsetof(bm_boost_status, meter) == 24 && offsetof(bm_boost_status, boosting) == 32
          && offsetof(bm_boost_status, meter_after) == 40 && s_api->struct_size == sizeof(bm_boost_api) && s_api->version == 2
          && s_api->fill && s_api->status, "the table: its size, version 1, both functions; the status 44 bytes");

    /* RECOMP_DEBUG=autopilot: offered, off; nobody hooks the car update */
    bo3_race_init();
    bo3_bm_autopilot_init(1);
    bo3_bm_boost_init(1);
    CHECK(s_bb_name && !strcmp(s_bb_name, "bmashup.boost") && s_bb_version == 2 && s_bb_table == s_api && s_ap_table == s_ap,
          "offered as bmashup.boost 2, beside bmashup.autopilot");
    CHECK(s_marks_registered == 0, "debug autopilot on: the car update is not hooked");
    game(2);
    tick(0);
    s = st();
    CHECK(s_api->fill(HOST) == BM_BOOST_DEBUG_AUTOPILOT && s.state == BM_BOOST_STATE_REFUSED && s.reason == BM_BOOST_DEBUG_AUTOPILOT,
          "debug autopilot on: fill refused, the status says why");

    /* the services on: one handler for the car update, both services behind it */
    memset(s_mem, 0, GMEM);
    sig();
    bo3_bm_autopilot_init(0);
    bo3_bm_boost_init(0);
    CHECK(s_marks_registered == 1 && s_mark, "the car update hooked once (bm_autopilot.c's handler)");
    CHECK(s_race->on_update(HOST, on_update, NULL) == TD_RACE_OK, "a plugin's on_update registered");
    s = st();
    CHECK(s.state == BM_BOOST_STATE_IDLE && s.reason == BM_BOOST_OK && s.fills == 0 && !s.have_meter && s.struct_size == 44,
          "IDLE at the start, no bar");
    CHECK(s_api->fill(HOST) == BM_BOOST_UNAVAILABLE, "before the first update: unavailable");
    CHECK(s_api->fill(NULL) == BM_BOOST_BAD_ARG && s_api->status(NULL, &s) == BM_BOOST_BAD_ARG
          && s_api->status(HOST, NULL) == BM_BOOST_BAD_ARG, "no host, no out: a bad argument");
    s.struct_size = 4;
    CHECK(s_api->status(HOST, &s) == BM_BOOST_BAD_ARG, "a status size below 8: a bad argument");
    {
        struct { bm_boost_status s; uint32_t guard; } big;
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = 8;
        CHECK(s_api->status(HOST, &big.s) == BM_BOOST_OK && big.s.struct_size == 8 && big.s.reason == 0xAAAAAAAAu,
              "a caller with 8 bytes: 8 written");
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = (uint32_t)sizeof big;
        CHECK(s_api->status(HOST, &big.s) == BM_BOOST_OK && big.s.struct_size == 44 && big.guard == 0xAAAAAAAAu,
              "a caller with a larger struct: 44 written");
    }

    /* refusals, nothing written */
    MF(BAR) = 50.0f;
    MF(BAR_MAX) = 240.0f;
    M32(STATE) = 5;
    tick(0);
    snap_mem();
    CHECK(fill_in_update(0) == BM_BOOST_NOT_IN_RACE && mem_same(), "menus: not in a race, nothing written");
    CHECK(st().state == BM_BOOST_STATE_REFUSED && st().reason == BM_BOOST_NOT_IN_RACE && !st().have_meter,
          "the status says why; no bar outside a stage");
    M32(STATE) = 3;
    CHECK(fill_in_update(0) == BM_BOOST_NOT_IN_RACE, "loading: not in a race");
    M32(STATE) = 6;
    CHECK(fill_in_update(0) == BM_BOOST_NOT_IN_RACE, "a stage being left: not in a race");
    game(0);
    snap_mem();
    CHECK(fill_in_update(1) == BM_BOOST_COUNTDOWN && mem_same(), "phase 0: the countdown, nothing written");
    game(1);
    CHECK(fill_in_update(1) == BM_BOOST_COUNTDOWN, "phase 1: the countdown");
    game(2);
    M32(PAUSED) = 0;
    snap_mem();
    CHECK(fill_in_update(1) == BM_BOOST_PAUSED && mem_same(), "paused: refused, nothing written");
    game(3);
    CHECK(fill_in_update(1) == BM_BOOST_RACE_OVER, "finished: the race is over");
    game(2);
    tick(1);
    s = st();
    snap_mem();
    th_start(0);
    th_join();
    CHECK(s_thread_rc == BM_BOOST_WRONG_THREAD && mem_same() && st().state == s.state && st().reason == s.reason,
          "fill from another thread: refused, nothing written, the status as it was");
    M32(0x003B11A4u) = 0x0018C511u;
    snap_mem();
    CHECK(fill_in_update(1) == BM_BOOST_UNSUPPORTED && mem_same() && s_calls == 0, "another build: unsupported, nothing written");
    CHECK(!st().have_meter, "another build: no bar read either");
    sig();
    MF(CAR + 0x10u + 12 * 4) = NAN;
    CHECK(fill_in_update(1) == BM_BOOST_NO_CAR, "no car in the snapshot: no car");
    MF(CAR + 0x10u + 12 * 4) = 0.0f;
    M32(CAR) = 0x003B1204u;
    CHECK(fill_in_update(1) == BM_BOOST_NO_CAR && !st().have_meter, "another object at player 1's car: no car, no bar");
    M32(CAR) = VT_CAR;
    M32(CAR + PLAYER) = 1;
    CHECK(fill_in_update(1) == BM_BOOST_NO_CAR, "player 1's car with another player index: no car");
    M32(CAR + PLAYER) = 0;
    CHECK(s_calls == 0, "the routine never called so far");

    /* the bar, read only */
    tick(0);
    s = st();
    CHECK(s.have_meter && same_float(s.meter, 50.0f) && same_float(s.meter_max, 240.0f) && s.boosting == 0,
          "racing: the bar 50 of 240, not boosting");
    M8(ACTIVE) = 1;
    tick(0);
    CHECK(st().boosting == 1, "boosting: 1");
    M8(ACTIVE) = 0;

    /* the top-up: staged, then done in the next car update */
    race0 = st().race;
    snap_mem();
    CHECK(fill_in_update(0) == BM_BOOST_OK && mem_same() && s_calls == 0, "accepted in an on_update call; nothing written yet");
    s = st();
    CHECK(s.state == BM_BOOST_STATE_PENDING && s.race == race0 && s.fills == 0, "PENDING");
    s_want = 1;
    tick(0);
    CHECK(s_rc == BM_BOOST_ALREADY_PENDING && s_calls == 0, "again while pending: refused");
    g_eax = 0x1111u;
    g_ebx = 0x2222u;
    g_ecx = 0x3333u;
    g_edx = 0x4444u;
    g_edi = 0x5555u;
    g_ebp = 0x6666u;
    g_esp = STACK;
    g_xmm0.f[0] = 1.0f;
    g_xmm1.f[0] = 2.0f;
    g_xmm7.f[0] = 7.0f;
    g_fp_top = 5;
    snap_mem();
    tick(1);
    memcpy(&amount, &s_call_arg, 4);
    CHECK(s_calls == 1 && s_call_esi == BLOCK && s_call_ret0 && same_float(amount, 240.0f),
          "the game's routine once: esi = car + 0x119C, the amount the maximum (%.1f), a 0 return address", amount);
    CHECK(g_eax == 0x1111u && g_ebx == 0x2222u && g_ecx == 0x3333u && g_edx == 0x4444u && g_edi == 0x5555u && g_ebp == 0x6666u
          && g_esp == STACK && g_esi == CAR && g_xmm0.f[0] == 1.0f && g_xmm1.f[0] == 2.0f && g_xmm7.f[0] == 7.0f && g_fp_top == 5,
          "every register put back (the general ones, xmm, the x87 top)");
    CHECK(mem_same_but_routine(), "nothing written but by the game's routine");
    s = st();
    CHECK(s.state == BM_BOOST_STATE_DONE && s.reason == BM_BOOST_OK && s.fills == 1 && same_float(s.meter_before, 50.0f)
          && same_float(s.meter_after, 240.0f) && same_float(s.meter, 240.0f), "DONE: the bar 50 -> 240, one top-up");
    CHECK(M8(CAR2 + 0x119Cu + 0x38u) == 0, "player 2's car untouched");

    /* the cap */
    MF(BAR) = 10.0f;
    CHECK(fill_in_update(0) == BM_BOOST_OK, "a second request");
    tick(1);
    MF(BAR) = 10.0f;
    CHECK(fill_in_update(0) == BM_BOOST_OK, "a third request");
    tick(1);
    CHECK(s_calls == 3 && st().fills == 3, "three top-ups");
    snap_mem();
    CHECK(fill_in_update(1) == BM_BOOST_LIMIT && mem_same() && s_calls == 3 && st().reason == BM_BOOST_LIMIT,
          "a fourth in the race: the limit, nothing written");

    /* a new race: counted, the top-ups start again */
    NEW_RACE(20.0f);
    s = st();
    CHECK(s.state == BM_BOOST_STATE_IDLE && s.race == race0 + 1 && s.fills == 0, "a new race: IDLE, no top-ups yet");
    CHECK(fill_in_update(0) == BM_BOOST_OK, "accepted again in the new race");
    tick(1);
    CHECK(s_calls == 4 && st().fills == 1, "one top-up in the new race");

    /* the game's routine declines, or the bar is full already */
    s_gate_no = 1;
    MF(BAR) = 30.0f;
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (the game declines)");
    tick(1);
    s = st();
    CHECK(s_calls == 5 && s.state == BM_BOOST_STATE_DONE && s.reason == BM_BOOST_NOT_ADDED && same_float(s.meter_before, 30.0f)
          && same_float(s.meter_after, 30.0f) && same_float(MF(BAR), 30.0f), "the game added nothing: DONE, NOT_ADDED, 30 -> 30");
    s_gate_no = 0;
    MF(BAR) = 240.0f;
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (the bar full already)");
    tick(1);
    CHECK(st().state == BM_BOOST_STATE_DONE && st().reason == BM_BOOST_OK, "the bar full already: DONE, OK");
    CHECK(fill_in_update(0) == BM_BOOST_LIMIT, "and the limit counts those too");

    /* requests that must not survive */
    NEW_RACE(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (pause next)");
    M32(PAUSED) = 0;
    tick(0);
    CHECK(st().state == BM_BOOST_STATE_REFUSED && st().reason == BM_BOOST_STALE, "a pause before its car update: dropped");
    M32(PAUSED) = 0xFFFFFFFFu;
    tick(1);
    CHECK(s_calls == 6 && same_float(MF(BAR), 20.0f), "and never done later");

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (restart next)");
    M32(CAR + PHASE) = 0;
    tick(0);
    M32(CAR + PHASE) = 2;
    tick(1);
    CHECK(s_calls == 6 && st().state == BM_BOOST_STATE_IDLE, "a restart before its car update: dropped, never done in the next race");

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (stage left next)");
    M32(STATE) = 6;
    tick(0);
    CHECK(st().reason == BM_BOOST_STALE, "the stage left before its car update: dropped");
    game(2);
    tick(1);
    CHECK(s_calls == 6, "and never done");

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (no car update)");
    tick(0);
    tick(0);
    CHECK(st().state == BM_BOOST_STATE_PENDING, "still pending 3 updates on without its car update");
    tick(0);
    CHECK(st().reason == BM_BOOST_STALE, "the 4th: dropped (a game without the mark)");
    tick(1);
    CHECK(s_calls == 6, "and never done");

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (steps jump)");
    tick_n(31, 1);
    CHECK(s_calls == 6 && st().reason == BM_BOOST_STALE, "31 steps before its car update: dropped");

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (another car)");
    M32(CAR) = 0x003B1204u;
    M32(STEP) += 1;
    g_esi = CAR;
    snap_mem();
    s_mark();
    CHECK(s_calls == 6 && st().reason == BM_BOOST_NO_CAR && mem_same(), "the car changed before its update: refused there, nothing written");
    M32(CAR) = VT_CAR;

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (pause at the car update)");
    M32(PAUSED) = 1;
    M32(STEP) += 1;
    g_esi = CAR;
    snap_mem();
    s_mark();
    CHECK(s_calls == 6 && st().reason == BM_BOOST_PAUSED && mem_same(), "paused at its car update: refused, nothing written");
    M32(PAUSED) = 0xFFFFFFFFu;

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (finish at the car update)");
    M32(CAR + PHASE) = 3;
    M32(STEP) += 1;
    g_esi = CAR;
    snap_mem();
    s_mark();
    CHECK(s_calls == 6 && st().reason == BM_BOOST_RACE_OVER && mem_same(), "the race over at its car update: refused, nothing written");

    FRESH(20.0f);
    CHECK(fill_in_update(0) == BM_BOOST_OK, "staged (build check at the car update)");
    M32(0x003A9ACCu) = 0;
    tick(1);
    CHECK(s_calls == 6 && st().reason == BM_BOOST_UNSUPPORTED, "the build check fails at its car update: refused");
    sig();

    /* both services behind the one car-update handler, in the same update */
    NEW_RACE(20.0f);
    M8(CAR + AI) = 0;
    s_want_ap = 1;
    s_want = 1;
    tick(0);
    CHECK(s_ap_rc == BM_AP_OK && s_rc == BM_BOOST_OK, "an autopilot request and a top-up in the same update");
    g_esp = STACK;
    tick(1);
    CHECK(s_takeovers == 1 && s_calls == 7 && M8(CAR + AI) == 1 && same_float(MF(BAR), 240.0f) && g_esi == CAR && g_esp == STACK,
          "the car update did both: the takeover and the top-up, the registers put back");
    M32(CAR + PHASE) = 3;
    tick(1);

    /* a reader and a wrong-thread caller on another thread while updates run */
    {
        NEW_RACE(0.0f);
        MF(BAR_MAX) = 0.0f;                         /* k = 0 everywhere before the reader starts */
        tick(0);
        s_stop = 0;
        th_start(1);
        for (int k = 1; k <= 20000; k++) {
            MF(BAR) = (float)k;
            MF(BAR_MAX) = (float)k;
            M32(STEP) += 1;
            bo3_race_after_update();
            bo3_bm_boost_after_update();
        }
        s_stop = 1;
        th_join();
        CHECK(s_reads > 0 && s_torn == 0 && s_wrong_ok == 0, "another thread: %ld reads, %ld torn, %ld fills accepted",
              s_reads, s_torn, s_wrong_ok);
    }

    printf("bm_boost: %d passed, %d failed\n", s_pass, s_fail);
    free(s_mem);
    free(s_copy);
    return s_fail ? 1 : 0;
}
