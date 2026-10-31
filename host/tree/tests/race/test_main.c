/* tests/race - the "takedawn.race" service (src/game/race_service.c) against
 * a stand-in for the game's memory: the module state, the current module,
 * the pause, the step count and player 1's car, set by the test, then the
 * service's own after-update and its table, as a plugin uses it. Each state
 * and field, the speed (steps, holds, jumps, pauses), the copies bounded by
 * the caller's size, on_update (replace, remove, the limit, a call that
 * changes the list) and a reader on another thread that must never see half
 * of two updates. No game data. */
#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "race_service.h"

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#endif

ptrdiff_t g_xbox_mem_offset;
#define GMEM 0x00800000u
static uint8_t *s_mem;
#define M16(va) (*(int16_t *)(s_mem + (uint32_t)(va)))
#define M32(va) (*(uint32_t *)(s_mem + (uint32_t)(va)))
#define MF(va)  (*(float *)(s_mem + (uint32_t)(va)))

#define STATE    0x004D53B4u
#define MODULE   0x004D5370u
#define MODOBJ   0x00200000u            /* where the test puts the module */
#define VT_GAME  0x003A9ACCu
#define PAUSED   0x004D537Cu
#define STEP     0x004A1EB4u
#define CARS     0x0073A19Cu
#define CAR      0x0073A1D0u

static int s_pass, s_fail;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); \
    printf("\n"); } } while (0)

/* plugins.c's, played here: what bo3_race_init offers */
static const char *s_svc_name;
static uint32_t s_svc_version;
static const void *s_svc_table;
int bo3_plugins_service(const char *name, uint32_t version, const void *table)
{
    s_svc_name = name;
    s_svc_version = version;
    s_svc_table = table;
    return 1;
}

static const td_race_api *s_api;
static int s_host_a, s_host_b, s_host_r, s_hosts[70];
#define HOST(p) ((td_host *)(void *)(p))

static void race(uint32_t phase)
{
    M32(STATE) = 5;
    M32(MODULE) = MODOBJ;
    M32(MODOBJ) = VT_GAME;
    M32(MODOBJ + 0x1B8u) = 0x00300000u;
    M32(PAUSED) = 0xFFFFFFFFu;
    M32(CAR + 0x134Cu) = phase;
}

static void place_car(float x, float y, float z, float fx, float fz)
{
    float *m = &MF(CAR + 0x10u);
    memset(m, 0, 64);
    m[0] = 1.0f;
    m[5] = 1.0f;
    m[8] = fx;
    m[10] = fz;
    m[12] = x;
    m[13] = y;
    m[14] = z;
    m[15] = 1.0f;
}

static td_race_snapshot snap(void)
{
    td_race_snapshot s;
    memset(&s, 0xEE, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    if (s_api->get(HOST(&s_host_a), &s) != TD_RACE_OK)
        memset(&s, 0, sizeof s);
    return s;
}

static td_race_snapshot update(void)
{
    bo3_race_after_update();
    return snap();
}

static int close_to(float a, float b)
{
    return fabsf(a - b) < 0.01f;
}

/* ---- on_update ---- */
static int s_calls[4];
static uint32_t s_seen_size, s_seen_state;
static void TD_CALL cb_count(const td_race_snapshot *s, void *user)
{
    s_calls[(int)(intptr_t)user]++;
    s_seen_size = s->struct_size;
    s_seen_state = s->state;
}
static void TD_CALL cb_remove_self(const td_race_snapshot *s, void *user)
{
    (void)s;
    s_calls[(int)(intptr_t)user]++;
    s_api->on_update(HOST(&s_host_r), NULL, NULL);      /* the list changed from inside a call */
}
static void TD_CALL cb_none(const td_race_snapshot *s, void *user)
{
    (void)s;
    (void)user;
}

/* ---- a reader on another thread ---- */
static _Atomic int s_stop;
static long s_reads, s_torn;
#if defined(_WIN32)
static DWORD WINAPI reader(LPVOID arg)
#else
static void *reader(void *arg)
#endif
{
    (void)arg;
    while (!s_stop) {
        td_race_snapshot s;
        s.struct_size = (uint32_t)sizeof s;
        if (s_api->get(HOST(&s_host_b), &s) != TD_RACE_OK)
            continue;
        s_reads++;
        /* every update writes one number k into all of these */
        if (s.position[0] != s.position[1] || s.position[1] != s.position[2] || s.race_time_s != s.position[0]
                || (float)s.lap != s.race_time_s || s.best_lap_s != s.race_time_s)
            s_torn++;
    }
#if defined(_WIN32)
    return 0;
#else
    return NULL;
#endif
}

int main(void)
{
    td_race_snapshot s;

    s_mem = calloc(1, GMEM);
    if (!s_mem)
        return 2;
    s_api = bo3_race_api();

    /* the table and its sizes: fixed for every compiler and system */
    CHECK(sizeof(td_race_snapshot) == 64 && offsetof(td_race_snapshot, speed_mps) == 36
          && offsetof(td_race_snapshot, position) == 40 && offsetof(td_race_snapshot, forward) == 52,
          "td_race_snapshot: 64 bytes, its fields where the header says");
    CHECK(s_api->struct_size == sizeof(td_race_api) && s_api->version == TD_RACE_VERSION && s_api->get && s_api->on_update,
          "the table: its size, version 1, both functions");
    bo3_race_init();
    CHECK(s_svc_name && !strcmp(s_svc_name, "takedawn.race") && s_svc_version == 1 && s_svc_table == s_api,
          "offered to the plugins as takedawn.race 1");

    /* before the game's first update */
    s.struct_size = (uint32_t)sizeof s;
    CHECK(s_api->get(HOST(&s_host_a), &s) == TD_RACE_UNAVAILABLE, "no snapshot before the first update");
    CHECK(s_api->get(NULL, &s) == TD_RACE_BAD_ARG && s_api->get(HOST(&s_host_a), NULL) == TD_RACE_BAD_ARG,
          "no host or no out: a bad argument");
    s.struct_size = 4;
    CHECK(s_api->get(HOST(&s_host_a), &s) == TD_RACE_BAD_ARG, "a size below 8: a bad argument");

    /* no guest memory yet, then the game's states */
    g_xbox_mem_offset = 0;
    s = update();
    CHECK(s.state == TD_RACE_NONE && s.valid == 0 && s.struct_size == 64, "no game: NONE, nothing valid");
    g_xbox_mem_offset = (ptrdiff_t)s_mem;
    place_car(1.0f, 2.0f, 3.0f, 0.0f, 1.0f);              /* stale bytes of a car: never shown outside a stage */
    M16(CAR + 0x10D0u) = 2;
    M32(STATE) = 0;
    s = update();
    CHECK(s.state == TD_RACE_NONE && s.valid == 0, "state 0: NONE");
    M32(STATE) = 3;
    s = update();
    CHECK(s.state == TD_RACE_LOADING && s.valid == 0 && s.position[0] == 0.0f, "a load: LOADING, no car");
    M32(STATE) = 6;
    s = update();
    CHECK(s.state == TD_RACE_LEAVING && s.valid == 0, "being left: LEAVING");
    race(2);
    M32(MODULE) = 0;
    s = update();
    CHECK(s.state == TD_RACE_FRONTEND && s.valid == 0, "no module: FRONTEND");
    M32(MODULE) = 0x05000000u;
    s = update();
    CHECK(s.state == TD_RACE_FRONTEND, "a module pointer out of range: FRONTEND (never followed)");
    race(2);
    M32(MODOBJ) = 0x003A0000u;
    s = update();
    CHECK(s.state == TD_RACE_FRONTEND && s.valid == 0, "another module (its vtable): FRONTEND");
    race(2);
    M32(MODOBJ + 0x1B8u) = 0;
    s = update();
    CHECK(s.state == TD_RACE_FRONTEND && s.valid == 0 && s.place == 0, "the game module without a stage: FRONTEND");

    /* in a stage: the phases, the pause */
    race(0);
    M16(CAR + 0x10D0u) = 3;
    M32(CAR + 0x10E4u) = 2;
    MF(CAR + 0x10DCu) = 12.5f;
    MF(CAR + 0x110Cu) = 0.0f;
    M32(CARS) = 6;
    place_car(10.0f, -2.0f, 400.0f, 3.0f, 4.0f);
    s = update();
    CHECK(s.state == TD_RACE_PRESTART && (s.valid & TD_RACE_HAVE_CAR) && s.place == 3 && s.lap == 2
          && close_to(s.race_time_s, 12.5f) && s.cars == 6 && close_to(s.position[0], 10.0f) && close_to(s.position[1], -2.0f)
          && close_to(s.position[2], 400.0f) && close_to(s.forward[0], 0.6f) && close_to(s.forward[2], 0.8f),
          "phase 0: PRESTART, the car's fields, forward made unit length");
    race(1);
    CHECK(update().state == TD_RACE_PRESTART, "phase 1 (a rolling start): PRESTART");
    race(2);
    CHECK(update().state == TD_RACE_RACING, "phase 2: RACING");
    M32(PAUSED) = 0;
    s = update();
    CHECK(s.state == TD_RACE_PAUSED && (s.valid & TD_RACE_HAVE_CAR) && !(s.valid & TD_RACE_HAVE_SPEED),
          "paused: PAUSED, the car, no speed");
    race(3);
    CHECK(update().state == TD_RACE_FINISHED, "phase 3: FINISHED");
    race(7);
    s = update();
    CHECK(s.state == TD_RACE_LOADING && s.valid == 0, "a phase it does not know: nothing read");
    race(2);
    M32(CARS) = 1000;
    s = update();
    CHECK(s.cars == 0 && (s.valid & TD_RACE_HAVE_CAR), "an impossible car count: 0");
    M32(CARS) = 6;
    MF(CAR + 0x10u + 12 * 4) = NAN;
    s = update();
    CHECK(s.state == TD_RACE_RACING && !(s.valid & TD_RACE_HAVE_CAR) && s.position[0] == 0.0f,
          "a matrix that is not numbers: no car");

    /* speed: the move per step */
    race(2);
    M32(STEP) = 100;
    place_car(0.0f, 0.0f, 0.0f, 0.0f, 1.0f);
    s = update();
    CHECK((s.valid & TD_RACE_HAVE_CAR) && !(s.valid & TD_RACE_HAVE_SPEED), "the first step seen: no speed yet");
    M32(STEP) = 101;
    place_car(0.77f, 0.0f, 0.0f, 0.0f, 1.0f);
    s = update();
    CHECK((s.valid & TD_RACE_HAVE_SPEED) && close_to(s.speed_mps, 46.2f), "0.77 units in a step: 46.2 m/s (%.3f)", s.speed_mps);
    s = update();
    CHECK((s.valid & TD_RACE_HAVE_SPEED) && close_to(s.speed_mps, 46.2f), "no step since: the speed holds");
    M32(STEP) = 103;
    place_car(1.77f, 0.0f, 0.0f, 0.0f, 1.0f);
    s = update();
    CHECK((s.valid & TD_RACE_HAVE_SPEED) && close_to(s.speed_mps, 30.0f), "1 unit in 2 steps: 30 m/s (%.3f)", s.speed_mps);
    M32(STEP) = 104;
    place_car(11.77f, 0.0f, 0.0f, 0.0f, 1.0f);
    s = update();
    CHECK(!(s.valid & TD_RACE_HAVE_SPEED), "10 units in a step (a reset): no speed");
    M32(STEP) = 105;
    place_car(11.77f, 0.3f, 0.4f, 0.0f, 1.0f);
    s = update();
    CHECK((s.valid & TD_RACE_HAVE_SPEED) && close_to(s.speed_mps, 30.0f), "then from the new place: 30 m/s (%.3f)", s.speed_mps);
    M32(STEP) = 120;
    place_car(12.0f, 0.3f, 0.4f, 0.0f, 1.0f);
    s = update();
    CHECK(!(s.valid & TD_RACE_HAVE_SPEED), "15 steps at once: no speed");
    M32(PAUSED) = 1;
    s = update();
    CHECK(!(s.valid & TD_RACE_HAVE_SPEED), "paused: no speed");
    M32(PAUSED) = 0xFFFFFFFFu;
    M32(STEP) = 121;
    place_car(12.5f, 0.3f, 0.4f, 0.0f, 1.0f);
    s = update();
    CHECK(!(s.valid & TD_RACE_HAVE_SPEED), "the first step after a pause: no speed yet");
    M32(STEP) = 122;
    place_car(13.0f, 0.3f, 0.4f, 0.0f, 1.0f);
    s = update();
    CHECK((s.valid & TD_RACE_HAVE_SPEED) && close_to(s.speed_mps, 30.0f), "and then again (%.3f)", s.speed_mps);
    M32(MODOBJ + 0x1B8u) = 0;
    update();
    race(2);
    M32(STEP) = 123;
    place_car(13.5f, 0.3f, 0.4f, 0.0f, 1.0f);
    s = update();
    CHECK(!(s.valid & TD_RACE_HAVE_SPEED), "back from the front end: no speed from the old place");

    /* copies bounded by the caller's size */
    {
        struct { td_race_snapshot s; uint32_t guard[8]; } big;
        uint8_t raw[12];
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = 8;
        CHECK(s_api->get(HOST(&s_host_a), &big.s) == TD_RACE_OK && big.s.struct_size == 8 && big.s.state == TD_RACE_RACING
              && big.s.valid == 0xAAAAAAAAu, "a caller with 8 bytes: 8 written, the rest as it was");
        memset(&big, 0xAA, sizeof big);
        big.s.struct_size = (uint32_t)sizeof big;
        CHECK(s_api->get(HOST(&s_host_a), &big.s) == TD_RACE_OK && big.s.struct_size == 64 && big.guard[0] == 0xAAAAAAAAu
              && big.guard[7] == 0xAAAAAAAAu, "a caller with a larger struct: 64 written, its own fields after them left");
        memset(raw, 0xAA, sizeof raw);
        ((td_race_snapshot *)(void *)raw)->struct_size = 12;     /* a header from before more fields */
        CHECK(s_api->get(HOST(&s_host_a), (td_race_snapshot *)(void *)raw) == TD_RACE_OK && raw[11] != 0xAA,
              "a caller with 12 bytes gets its 12");
    }

    /* on_update */
    CHECK(s_api->on_update(NULL, cb_count, NULL) == TD_RACE_BAD_ARG, "no host: a bad argument");
    CHECK(s_api->on_update(HOST(&s_host_a), cb_count, (void *)(intptr_t)0) == TD_RACE_OK
          && s_api->on_update(HOST(&s_host_b), cb_count, (void *)(intptr_t)1) == TD_RACE_OK, "two plugins register");
    bo3_race_after_update();
    CHECK(s_calls[0] == 1 && s_calls[1] == 1 && s_seen_size == 64 && s_seen_state == TD_RACE_RACING,
          "each called once per update, with the snapshot");
    s_api->on_update(HOST(&s_host_a), cb_count, (void *)(intptr_t)2);
    bo3_race_after_update();
    CHECK(s_calls[0] == 1 && s_calls[2] == 1 && s_calls[1] == 2, "a new fn replaces the plugin's old one");
    s_api->on_update(HOST(&s_host_b), NULL, NULL);
    bo3_race_after_update();
    CHECK(s_calls[1] == 2 && s_calls[2] == 2, "NULL removes it");
    s_api->on_update(HOST(&s_host_r), cb_remove_self, (void *)(intptr_t)3);
    bo3_race_after_update();
    bo3_race_after_update();
    CHECK(s_calls[3] == 1, "a call that removes itself: no deadlock, not called again (%d)", s_calls[3]);
    {
        int ok = 1;
        for (int k = 0; k < 63; k++)                           /* host a is already in: 64 in all */
            ok &= s_api->on_update(HOST(&s_hosts[k]), cb_none, NULL) == TD_RACE_OK;
        CHECK(ok && s_api->on_update(HOST(&s_hosts[63]), cb_none, NULL) == TD_RACE_BAD_ARG
              && s_api->on_update(HOST(&s_host_a), cb_count, (void *)(intptr_t)2) == TD_RACE_OK,
              "64 plugins: a 65th refused, one already in can still change its own");
        for (int k = 0; k < 63; k++)
            s_api->on_update(HOST(&s_hosts[k]), NULL, NULL);
        s_api->on_update(HOST(&s_host_a), NULL, NULL);
    }

    /* a reader on another thread: never half of two updates */
    {
#if defined(_WIN32)
        HANDLE th;
#else
        pthread_t th;
#endif
        race(2);
        place_car(0.0f, 0.0f, 0.0f, 0.0f, 1.0f);              /* k = 0 everywhere before the reader starts */
        MF(CAR + 0x10DCu) = 0.0f;
        MF(CAR + 0x110Cu) = 0.0f;
        M32(CAR + 0x10E4u) = 0;
        bo3_race_after_update();
#if defined(_WIN32)
        th = CreateThread(NULL, 0, reader, NULL, 0, NULL);
#else
        pthread_create(&th, NULL, reader, NULL);
#endif
        for (int k = 1; k <= 20000; k++) {
            float v = (float)k;
            place_car(v, v, v, 0.0f, 1.0f);
            MF(CAR + 0x10DCu) = v;
            MF(CAR + 0x110Cu) = v;
            M32(CAR + 0x10E4u) = (uint32_t)k;
            M32(STEP) = 1000u + (uint32_t)k;
            bo3_race_after_update();
        }
        s_stop = 1;
#if defined(_WIN32)
        WaitForSingleObject(th, INFINITE);
        CloseHandle(th);
#else
        pthread_join(th, NULL);
#endif
        CHECK(s_reads > 0 && s_torn == 0, "a reader on another thread: %ld reads, %ld torn", s_reads, s_torn);
    }

    printf("race: %d passed, %d failed\n", s_pass, s_fail);
    free(s_mem);
    return s_fail ? 1 : 0;
}
