/* tests/bm_autopilot - Burnout Mashup's private "bmashup.autopilot" service
 * (src/game/bm_autopilot.c over ai_takeover.c and the real race_service.c)
 * against a stand-in for the game's memory. Each game update is played the
 * way the game runs it: player 1's car update (the "ap_update" mark), then
 * the takedawn.race snapshot and its on_update calls (where a plugin asks),
 * then the service's own after-update. sub_00179760 is a stand-in that
 * records how it was called. "No write" is checked over the whole stand-in
 * memory. No game data. */
#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_autopilot.h"
#include "race_service.h"
#include "recomp_types.h"

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#endif

ptrdiff_t g_xbox_mem_offset;
RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esi, g_esp;
RECOMP_TLS uint32_t g_ebx, g_edi, g_ebp;                /* bm_boost.c's call puts these back too */
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
#define CAR2     0x0073C9B0u            /* player 2's car: the mark runs for it too */
#define VT_CAR   0x003B11A0u
#define AI       0x27D8u
#define PLAYER   0x27D0u
#define PHASE    0x134Cu
#define RESET    0x19D0u
#define CTLS     0x004AE724u
#define NOW      0x004AE200u
#define STACK    0x00100000u

static int s_pass, s_fail;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); \
    printf("\n"); } } while (0)

/* plugins.c's, played here: what is offered */
static const void *s_race_table, *s_bm_table;
static const char *s_bm_name;
static uint32_t s_bm_version;
int bo3_plugins_service(const char *name, uint32_t version, const void *table)
{
    if (!strcmp(name, "takedawn.race"))
        s_race_table = table;
    else {
        s_bm_name = name;
        s_bm_version = version;
        s_bm_table = table;
    }
    return 1;
}

/* the toolkit's mark table, played here */
static void (*s_mark)(void);
static int s_marks_registered;
void recomp_patch_on_mark(const char *name, void (*fn)(void))
{
    if (!strcmp(name, "ap_update")) {
        s_mark = fn;
        s_marks_registered++;
    }
}

/* the title's sub_00179760 (the AI driver's route reset), played here */
static int s_calls, s_call_ok;
static uint32_t s_call_eax;
void sub_00179760(void)
{
    s_calls++;
    s_call_eax = g_eax;
    s_call_ok = M32(g_esp) == 0 && M8(CAR + AI) == 1 && M32(CAR + RESET) == 0 && M32(CAR + RESET + 12) == 0;
    g_esp += 4;                                     /* its ret */
    g_ecx = 0xDEAD0001u;                            /* what a call may change */
    g_edx = 0xDEAD0002u;
}

/* bm_boost.c shares the car update (bm_autopilot.c's handler calls it); never
 * started here, so its routine is never called: tests/bm_boost covers it */
void sub_0017A530(void)
{
}

static const bm_autopilot_api *s_api;
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

/* player 1's car in a stage at `phase`, nobody paused, the AI not driving */
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

/* ---- one game update ---- */
static int s_want;                                  /* 1 engage, 2 engage2 (s_req), 3 release, from the on_update call */
static int32_t s_rc = -1;
static bm_autopilot_request s_req;
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    (void)snap;
    (void)user;
    if (s_want) {
        int w = s_want;
        s_want = 0;
        s_rc = w == 3 ? s_api->release(HOST) : w == 2 ? s_api->engage2(HOST, &s_req) : s_api->engage(HOST);
    }
}

/* steps: simulation steps this update; car: player 1's car update runs */
static void tick_n(uint32_t steps, int car)
{
    M32(STEP) += steps;
    if (car && s_mark) {
        g_esi = CAR2;                               /* player 2's car first: never acted on */
        s_mark();
        g_esi = CAR;
        s_mark();
    }
    bo3_race_after_update();
    bo3_bm_autopilot_after_update();
}
static void tick(int car) { tick_n(1, car); }

static int32_t engage_in_update(int car)
{
    s_want = 1;
    s_rc = -1;
    tick(car);
    return s_rc;
}

static bm_autopilot_status st(void)
{
    bm_autopilot_status s;
    memset(&s, 0xEE, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    if (s_api->status(HOST, &s) != BM_AP_OK)
        memset(&s, 0xFF, sizeof s);
    return s;
}

/* The whole stand-in memory against a copy; the step count is the test's own
 * clock (each update moves it), so it is left out. */
static void snap_mem(void) { memcpy(s_copy, s_mem, GMEM); }
static int mem_same(void)
{
    memcpy(s_copy + STEP, s_mem + STEP, 4);
    return !memcmp(s_copy, s_mem, GMEM);
}

/* ---- another thread ---- */
static _Atomic int s_stop;
static long s_reads, s_torn, s_wrong_ok;
static int32_t s_thread_rc;
static int s_th_release;                            /* the other thread calls release instead of engage */
#if defined(_WIN32)
static DWORD WINAPI th_engage(LPVOID arg)
#else
static void *th_engage(void *arg)
#endif
{
    (void)arg;
    s_thread_rc = s_th_release ? s_api->release(HOST) : s_api->engage(HOST);
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
        bm_autopilot_status s;
        s.struct_size = (uint32_t)sizeof s;
        if (s_api->status(HOST, &s) != BM_AP_OK)
            continue;
        s_reads++;
        /* a reason only with REFUSED; states and reasons in range */
        if (s.state > BM_AP_STATE_REFUSED || s.reason > BM_AP_STALE || (s.reason && s.state != BM_AP_STATE_REFUSED))
            s_torn++;
        if (s_api->engage(HOST) == BM_AP_OK)
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
static void th_start(int reader) { s_th = CreateThread(NULL, 0, reader ? th_reader : th_engage, NULL, 0, NULL); }
static void th_join(void) { WaitForSingleObject(s_th, INFINITE); CloseHandle(s_th); }
#else
static pthread_t s_th;
static void th_start(int reader) { pthread_create(&s_th, NULL, reader ? th_reader : th_engage, NULL); }
static void th_join(void) { pthread_join(s_th, NULL); }
#endif

int main(void)
{
    bm_autopilot_status s;
    uint32_t race0;

    setvbuf(stdout, NULL, _IONBF, 0);              /* every FAIL line out, even before a fault */
    s_mem = calloc(1, GMEM);
    s_copy = calloc(1, GMEM);
    if (!s_mem || !s_copy)
        return 2;
    g_xbox_mem_offset = (ptrdiff_t)s_mem;
    g_esp = STACK;                                  /* a takeover that should not happen pushes here, not off the memory */
    sig();
    s_api = bo3_bm_autopilot_api();
    s_race = bo3_race_api();

    /* the table and the header's sizes */
    CHECK(sizeof(bm_autopilot_status) == 24 && offsetof(bm_autopilot_status, race) == 12
          && offsetof(bm_autopilot_status, release_reason) == 16 && sizeof(bm_autopilot_request) == 12
          && s_api->struct_size == sizeof(bm_autopilot_api) && s_api->version == 2 && s_api->engage && s_api->status
          && s_api->engage2 && s_api->release && offsetof(bm_autopilot_api, engage2) == 8 + 2 * sizeof(void *),
          "the table: its size, version 2, four functions (version 1's two first); the status 24 bytes, version 1's 16 first");

    /* RECOMP_DEBUG=autopilot: offered, but off; the mark stays autopilot.c's */
    bo3_race_init();
    bo3_bm_autopilot_init(1);
    CHECK(s_bm_name && !strcmp(s_bm_name, "bmashup.autopilot") && s_bm_version == 2 && s_bm_table == s_api
          && s_race_table == s_race, "offered as bmashup.autopilot 2, beside takedawn.race");
    CHECK(s_marks_registered == 0 && !s_mark, "debug autopilot on: the car update is not hooked");
    game(2);
    tick(0);
    s = st();
    CHECK(s_api->engage(HOST) == BM_AP_DEBUG_AUTOPILOT && s.state == BM_AP_STATE_REFUSED && s.reason == BM_AP_DEBUG_AUTOPILOT,
          "debug autopilot on: engage refused, the status says why");
    s_req.struct_size = (uint32_t)sizeof s_req;
    s_req.policy = BM_AP_POLICY_ONCE_PER_RACE;
    CHECK(s_api->engage2(HOST, &s_req) == BM_AP_DEBUG_AUTOPILOT && s_api->release(HOST) == BM_AP_DEBUG_AUTOPILOT,
          "debug autopilot on: engage2 and release refused too");
    bo3_bm_autopilot_lifecycle(1, 1);
    CHECK(bo3_bm_autopilot_censuses() == 0, "debug autopilot on: the lifecycle is not followed (no census)");

    /* the service on */
    memset(s_mem, 0, GMEM);
    sig();
    bo3_bm_autopilot_init(0);
    CHECK(s_marks_registered == 1 && s_mark, "the car update hooked once");
    CHECK(s_race->on_update(HOST, on_update, NULL) == TD_RACE_OK, "a plugin's on_update registered");
    s = st();
    CHECK(s.state == BM_AP_STATE_IDLE && s.reason == BM_AP_OK && s.struct_size == 24 && s.release_reason == 0
          && s.engaged_races == 0, "IDLE at the start");
    CHECK(s_api->engage(HOST) == BM_AP_UNAVAILABLE, "before the first update: unavailable");
    CHECK(s_api->engage(NULL) == BM_AP_BAD_ARG && s_api->status(NULL, &s) == BM_AP_BAD_ARG
          && s_api->status(HOST, NULL) == BM_AP_BAD_ARG, "no host, no out: a bad argument");
    s.struct_size = 4;
    CHECK(s_api->status(HOST, &s) == BM_AP_BAD_ARG, "a status size below 8: a bad argument");
    {
        struct { bm_autopilot_status s; uint32_t guard; } big;
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = 8;
        CHECK(s_api->status(HOST, &big.s) == BM_AP_OK && big.s.struct_size == 8 && big.s.reason == 0xAAAAAAAAu,
              "a caller with 8 bytes: 8 written");
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = (uint32_t)sizeof big;
        CHECK(s_api->status(HOST, &big.s) == BM_AP_OK && big.s.struct_size == 24 && big.guard == 0xAAAAAAAAu,
              "a caller with a larger struct: 24 written");
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = 16;
        CHECK(s_api->status(HOST, &big.s) == BM_AP_OK && big.s.struct_size == 16 && big.s.release_reason == 0xAAAAAAAAu,
              "a version 1 caller (16 bytes): 16 written, nothing past them");
    }

    /* the menus, loading, a stage being left: refused, nothing written */
    M32(STATE) = 5;
    tick(0);                                        /* no module: FRONTEND */
    snap_mem();
    CHECK(engage_in_update(0) == BM_AP_NOT_IN_RACE && mem_same(), "menus: not in a race, nothing written");
    s = st();
    CHECK(s.state == BM_AP_STATE_REFUSED && s.reason == BM_AP_NOT_IN_RACE, "the status says why");
    M32(STATE) = 3;
    CHECK(engage_in_update(0) == BM_AP_NOT_IN_RACE, "loading: not in a race");
    M32(STATE) = 6;
    CHECK(engage_in_update(0) == BM_AP_NOT_IN_RACE, "a stage being left: not in a race");

    /* the countdown, the pause, the finish */
    game(0);
    snap_mem();
    CHECK(engage_in_update(1) == BM_AP_COUNTDOWN && mem_same(), "phase 0: the countdown, nothing written");
    game(1);
    CHECK(engage_in_update(1) == BM_AP_COUNTDOWN, "phase 1 (a rolling start): the countdown");
    game(2);
    M32(PAUSED) = 0;
    snap_mem();
    CHECK(engage_in_update(1) == BM_AP_PAUSED && mem_same(), "paused: refused, nothing written");
    game(3);
    CHECK(engage_in_update(1) == BM_AP_RACE_OVER, "finished: the race is over");

    /* the wrong thread: refused, nothing noted */
    game(2);
    tick(1);
    s = st();
    snap_mem();
    th_start(0);
    th_join();
    CHECK(s_thread_rc == BM_AP_WRONG_THREAD && mem_same() && st().state == s.state && st().reason == s.reason,
          "engage from another thread: refused, nothing written, the status as it was");

    /* a game this service does not know; no car; a car it cannot take */
    M32(0x003B11A4u) = 0x0018C511u;
    snap_mem();
    CHECK(engage_in_update(1) == BM_AP_UNSUPPORTED && mem_same() && s_calls == 0, "another build: unsupported, nothing written");
    sig();
    MF(CAR + 0x10u + 12 * 4) = NAN;
    CHECK(engage_in_update(1) == BM_AP_NO_CAR, "no car in the snapshot: no car");
    MF(CAR + 0x10u + 12 * 4) = 0.0f;
    M32(CAR) = 0x003B1204u;
    CHECK(engage_in_update(1) == BM_AP_NO_CAR, "another object at player 1's car: no car");
    M32(CAR) = VT_CAR;
    M32(CAR + PLAYER) = 1;
    CHECK(engage_in_update(1) == BM_AP_NO_CAR, "player 1's car with another player index: no car");
    M32(CAR + PLAYER) = 0;
    M8(CAR + AI) = 1;
    CHECK(engage_in_update(1) == BM_AP_AI_OWNED && st().reason == BM_AP_AI_OWNED, "the AI already drives: refused");
    M8(CAR + AI) = 0;
    CHECK(s_calls == 0, "no takeover so far");

    /* the takeover: staged, then done in the next car update */
    M32(CAR + RESET) = 0x11u;
    M32(CAR + RESET + 4) = 0x22u;
    M32(CAR + RESET + 8) = 0x33u;
    M32(CAR + RESET + 12) = 0x44u;
    MF(NOW) = 123.0f;
    race0 = st().race;
    snap_mem();
    CHECK(engage_in_update(0) == BM_AP_OK && mem_same() && s_calls == 0, "accepted in an on_update call; nothing written yet");
    s = st();
    CHECK(s.state == BM_AP_STATE_PENDING && s.reason == BM_AP_OK && s.race == race0, "PENDING");
    s_want = 1;
    tick(0);
    CHECK(s_rc == BM_AP_ALREADY_PENDING && st().state == BM_AP_STATE_PENDING && s_calls == 0, "again while pending: refused");
    g_eax = 0x1111u;
    g_ecx = 0x2222u;
    g_edx = 0x3333u;
    g_esp = STACK;
    tick(1);
    CHECK(s_calls == 1 && s_call_eax == CAR + 0x1A00u && s_call_ok, "the takeover once: the byte, the four words, eax = car + 0x1A00");
    CHECK(M8(CAR + AI) == 1 && M32(CAR + RESET + 4) == 0 && M32(CAR + RESET + 8) == 0, "the car's AI byte set, the words zeroed");
    CHECK(g_eax == 0x1111u && g_ecx == 0x2222u && g_edx == 0x3333u && g_esp == STACK, "the registers put back");
    CHECK(MF(CTLS + 0x184u) == 123.0f && MF(CTLS + 3 * 0x188u + 0x184u) == 123.0f, "the controller records stamped");
    s = st();
    CHECK(s.state == BM_AP_STATE_ENGAGED && s.reason == BM_AP_OK && s.race == race0, "ENGAGED");
    CHECK(M8(CAR2 + AI) == 0, "player 2's car untouched");
    s_want = 1;
    tick(1);
    CHECK(s_rc == BM_AP_ALREADY_USED && s_calls == 1, "again while engaged: refused, no second takeover");
    MF(NOW) = 200.0f;
    tick(1);
    CHECK(MF(CTLS + 2 * 0x188u + 0x184u) == 200.0f && s_calls == 1, "stamped at each car update while engaged");
    M32(PAUSED) = 0;
    MF(NOW) = 300.0f;
    tick(1);
    tick(1);
    CHECK(MF(CTLS + 0x184u) == 200.0f && st().state == BM_AP_STATE_ENGAGED, "paused: no stamp, still ENGAGED");
    M32(PAUSED) = 0xFFFFFFFFu;
    tick(1);
    CHECK(MF(CTLS + 0x184u) == 300.0f, "resumed: stamped again");

    /* the finish: ENDED, the car not handed back */
    M32(CAR + PHASE) = 3;
    tick(1);
    s = st();
    CHECK(s.state == BM_AP_STATE_ENDED && M8(CAR + AI) == 1 && s_calls == 1, "the finish: ENDED; the AI byte left set");
    snap_mem();
    tick(1);
    tick(1);
    CHECK(mem_same(), "after the end: nothing written");
    s_want = 1;
    tick(1);
    CHECK(s_rc == BM_AP_ALREADY_USED && s_calls == 1, "after the end: at most one takeover a race");

    /* a new race: counted, IDLE; the byte is not cleared by the service */
    M32(STATE) = 6;
    tick(0);
    M32(STATE) = 3;
    tick(0);
    game(0);
    M8(CAR + AI) = 1;                               /* as the title left it */
    tick(1);
    s = st();
    CHECK(s.state == BM_AP_STATE_IDLE && s.race == race0 + 1, "a new race: IDLE, the race count moved on (%u)", s.race);
    game(2);
    M8(CAR + AI) = 1;
    CHECK(engage_in_update(1) == BM_AP_AI_OWNED && s_calls == 1, "the title's AI still holds it: refused, never cleared");
    M8(CAR + AI) = 0;                               /* the title gave it back itself */
    CHECK(engage_in_update(0) == BM_AP_OK, "the next race: accepted again");
    tick(1);
    CHECK(s_calls == 2 && st().state == BM_AP_STATE_ENGAGED, "one takeover in the new race");

    /* a restart from the pause menu while engaged: ENDED news, then a new race */
    game(0);
    tick(0);
    s = st();
    CHECK(s.state == BM_AP_STATE_IDLE && s.race == race0 + 2, "a restart: a new race, IDLE");

    /* requests that must not survive */
#define FRESH() do { game(2); M8(CAR + AI) = 0; tick(0); } while (0)
    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (pause next)");
    M32(PAUSED) = 0;
    tick(0);                                        /* the next snapshot: PAUSED */
    s = st();
    CHECK(s.state == BM_AP_STATE_REFUSED && s.reason == BM_AP_STALE, "a pause before its car update: dropped");
    M32(PAUSED) = 0xFFFFFFFFu;
    snap_mem();
    tick(1);
    CHECK(s_calls == 2 && M8(CAR + AI) == 0, "and never done later");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (restart next)");
    M32(CAR + PHASE) = 0;
    tick(0);
    M32(CAR + PHASE) = 2;
    tick(1);
    CHECK(s_calls == 2 && st().state == BM_AP_STATE_IDLE, "a restart before its car update: dropped, never done in the next race");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (stage left next)");
    M32(STATE) = 6;
    tick(0);
    CHECK(st().state == BM_AP_STATE_REFUSED && st().reason == BM_AP_STALE, "the stage left before its car update: dropped");
    game(2);
    tick(1);
    CHECK(s_calls == 2, "and never done");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (no car update)");
    tick(0);
    tick(0);
    CHECK(st().state == BM_AP_STATE_PENDING, "still pending 3 updates on without its car update");
    tick(0);
    CHECK(st().state == BM_AP_STATE_REFUSED && st().reason == BM_AP_STALE, "the 4th: dropped (a game without the mark)");
    tick(1);
    CHECK(s_calls == 2, "and never done");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (steps jump)");
    snap_mem();
    tick_n(31, 1);
    CHECK(s_calls == 2 && st().reason == BM_AP_STALE && M8(CAR + AI) == 0, "31 steps before its car update: dropped");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (another car)");
    M32(CAR) = 0x003B1204u;
    tick(1);
    CHECK(s_calls == 2 && st().reason == BM_AP_NO_CAR && M8(CAR + AI) == 0, "the car changed before its update: refused there");
    M32(CAR) = VT_CAR;

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (another player)");
    M32(CAR + PLAYER) = 1;
    tick(1);
    CHECK(s_calls == 2 && st().reason == BM_AP_NO_CAR && M8(CAR + AI) == 0, "the player index changed: refused there");
    M32(CAR + PLAYER) = 0;

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (the title takes it)");
    M8(CAR + AI) = 1;
    tick(1);
    CHECK(s_calls == 2 && st().reason == BM_AP_AI_OWNED, "the title's AI took it first: refused there");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (pause at the car update)");
    M32(PAUSED) = 1;
    M32(STEP) += 1;
    g_esi = CAR;
    snap_mem();
    s_mark();                                       /* the car update sees the pause */
    CHECK(s_calls == 2 && st().reason == BM_AP_PAUSED && mem_same(), "paused at its car update: refused, nothing written");
    M32(PAUSED) = 0xFFFFFFFFu;

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (finish at the car update)");
    M32(CAR + PHASE) = 3;
    g_esi = CAR;
    snap_mem();
    s_mark();
    CHECK(s_calls == 2 && st().reason == BM_AP_RACE_OVER && mem_same(), "the race over at its car update: refused, nothing written");

    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (build check at the car update)");
    M32(0x003A9ACCu) = 0;
    tick(1);
    CHECK(s_calls == 2 && st().reason == BM_AP_UNSUPPORTED, "the build check fails at its car update: refused");
    sig();

    /* refusals at the car update write nothing (no stamp either) */
    FRESH();
    CHECK(engage_in_update(0) == BM_AP_OK, "staged (no stamp)");
    MF(NOW) = 999.0f;
    M32(CAR) = 0;
    M32(STEP) += 1;
    g_esi = CAR;
    snap_mem();
    s_mark();
    CHECK(s_calls == 2 && MF(CTLS + 0x184u) != 999.0f && mem_same(), "a refused takeover stamps nothing");
    M32(CAR) = VT_CAR;

    /* the title drops the takeover in the race (a crash's reset: the AI byte
     * back to 0): applied again, the same steps, only while in play, only
     * for player 1's car, never after the end */
    {
        int c0;
        FRESH();
        CHECK(engage_in_update(0) == BM_AP_OK, "staged (taken again)");
        tick(1);
        c0 = s_calls;
        CHECK(st().state == BM_AP_STATE_ENGAGED && bo3_bm_autopilot_retakes() == 0, "engaged, nothing taken again yet");
        M8(CAR + AI) = 0;
        M32(PAUSED) = 0;
        tick(1);
        CHECK(s_calls == c0 && M8(CAR + AI) == 0, "the AI byte cleared while paused: not taken again while paused");
        M32(PAUSED) = 0xFFFFFFFFu;
        tick(1);
        CHECK(s_calls == c0 + 1 && s_call_ok && s_call_eax == CAR + 0x1A00u && M8(CAR + AI) == 1
              && st().state == BM_AP_STATE_ENGAGED && bo3_bm_autopilot_retakes() == 1,
              "the title cleared the AI byte: taken again once, the same steps, still ENGAGED");
        tick(1);
        tick(1);
        CHECK(s_calls == c0 + 1, "not again while the AI holds it");
        M8(CAR + AI) = 0;
        M32(CAR) = 0x003B1204u;
        tick(1);
        CHECK(s_calls == c0 + 1 && M8(CAR + AI) == 0, "another object at player 1's car: not taken again");
        M32(CAR) = VT_CAR;
        tick(1);
        CHECK(s_calls == c0 + 2 && bo3_bm_autopilot_retakes() == 2, "player 1's car again: taken again");
        M32(CAR + PHASE) = 3;
        tick(1);
        M8(CAR + AI) = 0;
        tick(1);
        tick(1);
        CHECK(s_calls == c0 + 2 && st().state == BM_AP_STATE_ENDED && M8(CAR + AI) == 0,
              "after the finish: never taken again, nothing written to the byte");
    }

    /* the watch: an engaged car that does not move for 10 s of race time is
     * reported once; moving again re-arms it */
    {
        game(0);                                    /* a new race: the last one had its takeover */
        tick(0);
        FRESH();
        MF(CAR + 0x10DCu) = 20.0f;
        CHECK(engage_in_update(0) == BM_AP_OK, "staged (the watch)");
        tick(1);
        for (int k = 1; k <= 5; k++) {
            MF(CAR + 0x10u + 12 * 4) += 0.5f;
            MF(CAR + 0x10DCu) = 20.0f + (float)k;
            tick(1);
        }
        CHECK(st().state == BM_AP_STATE_ENGAGED && !bo3_bm_autopilot_stalled(), "moving: not stalled");
        for (int k = 1; k <= 9; k++) {
            MF(CAR + 0x10DCu) = 25.0f + (float)k;
            tick(1);
        }
        CHECK(!bo3_bm_autopilot_stalled(), "9 s without moving: not yet");
        MF(CAR + 0x10DCu) = 35.0f;
        tick(1);
        CHECK(bo3_bm_autopilot_stalled(), "10 s without moving: stalled");
        MF(CAR + 0x10u + 12 * 4) += 0.5f;
        MF(CAR + 0x10DCu) = 36.0f;
        tick(1);
        CHECK(!bo3_bm_autopilot_stalled(), "moving again: the watch re-arms");
        M32(CAR + PHASE) = 3;
        tick(1);
    }

    /* the finish seen first by the snapshot, before a car update at phase 3
     * (G4 r2: the result line was missing): the result line all the same,
     * once; the car update's own finish path gives it once too */
    {
        unsigned r0;
        game(0);
        tick(0);
        FRESH();
        CHECK(engage_in_update(0) == BM_AP_OK, "staged (the finish seen first by the snapshot)");
        tick(1);
        r0 = bo3_bm_autopilot_results();
        M32(CAR + PHASE) = 3;
        tick(0);
        CHECK(st().state == BM_AP_STATE_ENDED && bo3_bm_autopilot_results() == r0 + 1,
              "the snapshot saw the finish first: ENDED with the result line");
        tick(1);
        tick(1);
        CHECK(bo3_bm_autopilot_results() == r0 + 1, "the result line once, not again at the car update");
        game(0);
        tick(0);
        FRESH();
        CHECK(engage_in_update(0) == BM_AP_OK, "staged (the finish seen first by the car update)");
        tick(1);
        M32(CAR + PHASE) = 3;
        tick(1);
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENDED && bo3_bm_autopilot_results() == r0 + 2,
              "the car update saw the finish first: the result line once");
    }

#include "test_v2.inc"

    /* a reader and a wrong-thread caller on another thread while races run */
    {
        int races = 0;
        int calls0 = s_calls;
        s_stop = 0;
        th_start(1);
        for (int k = 0; k < 2000; k++) {
            game(0);
            M8(CAR + AI) = 0;
            tick(1);                                /* a new race */
            game(2);
            tick(1);
            engage_in_update(0);
            tick(1);
            tick(1);
            M32(CAR + PHASE) = 3;
            tick(1);
            races++;
        }
        s_stop = 1;
        th_join();
        CHECK(s_calls - calls0 == races && s_reads > 0 && s_torn == 0 && s_wrong_ok == 0,
              "%d races: %d takeovers (one each); another thread: %ld reads, %ld torn, %ld engages accepted",
              races, s_calls - calls0, s_reads, s_torn, s_wrong_ok);
    }

    printf("bm_autopilot: %d passed, %d failed\n", s_pass, s_fail);
    free(s_mem);
    free(s_copy);
    return s_fail ? 1 : 0;
}
