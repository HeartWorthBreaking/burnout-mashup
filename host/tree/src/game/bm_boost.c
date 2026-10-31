/*
 * bm_boost.c - "bmashup.boost" (include/bmashup_boost.h, docs/bmashup-boost.md):
 * Burnout Mashup's private boost top-up. A plugin asks; in player 1's next car
 * update the game's own add-boost routine fills the bar to its maximum, as
 * the game's own refills do. Research: research\native_gameplay_api\g5\
 * G5_FEASIBILITY_REPORT.md (each field below and where it is used).
 *
 * The car's boost block, B = car + 0x119C (player 1's car 0x73A1D0):
 *   B + 0x38  the bar (float), clamped by the routine below to
 *   B + 0x34  its maximum (240 at a race's set-up, sub_00027250; longer in some
 *             events: the table 240 / 360 / 600 / 720 at 0x3F72E4)
 *   B + 0x52  1 while the car boosts (set by sub_0017A5B0; read by the car's
 *             physics, sub_00117F90)
 * The routine, sub_0017A530 (0x17A530, 30 instructions): esi = B, one stack
 * argument (the amount, a float), ret 4. It may decline (sub_00017310 on
 * 0x4A71A0, the game's own gate); else it scales the amount by B + 0x48 /
 * B + 0x4C and by the current stage's factor, adds it to a running total at
 * B + 0x3C and to the bar, and clamps the bar to the maximum. The game's own
 * refills (sub_00029DF0, sub_0017C170, sub_00171D90) pass the maximum as the
 * amount; so does this service. Nothing else is written here.
 *
 * Where each part runs (as bm_autopilot.c, whose request model this copies):
 *   fill()     the game's thread: checks the latest race snapshot and the game
 *              (read only), notes the request. No write to the game.
 *   car update the "ap_update" mark, through bm_autopilot.c's handler (one
 *              handler a mark), esi player 1's car: checks everything again
 *              (the build, the module, no pause, phase 2, the car's vtable and
 *              player index, the same race, at most BM_STEPS_MAX steps), then
 *              calls the routine; every guest register it may touch is put
 *              back. The cap per race is counted here.
 *   after each update: follows the race (a new race, a request dropped) and
 *              publishes player 1's bar for status().
 *
 * Threads: status() copies one whole update's words (a sequence count, as
 * race_service.c), written on the game's thread only.
 *
 * Version 2 (platform 0.1.8, hook request P1, gp\hookreq\drafts\bmashup_boost_v2.h): award(player, amount). The same
 * request model per plugin (an award slot keyed by the plugin's td_host, BB_AWARD_SLOTS of them): award() checks on the
 * game's thread and notes the request; player 1's next car update re-checks (the build, the race, the amount against the
 * bar's maximum NOW) and calls sub_0017A530 with the amount instead of the maximum. Rate: at most
 * BM_BOOST_AWARDS_PER_SECOND accepted in any 60 simulation steps, BM_BOOST_AWARDS_PER_RACE carried out a race, per
 * plugin. A new race drops pending awards (STALE) and starts the counts again. Each slot's status is published behind
 * its own sequence count (award_status from any thread). MUT=n (tests) compiles one defect (11..16 are v2's).
 */
#include "bm_boost.h"

#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ai_takeover.h"
#include "plugins.h"
#include "race_service.h"
#include "takedawn_race.h"
#include "recomp_types.h"

extern ptrdiff_t g_xbox_mem_offset;
extern void sub_0017A530(void);

#define BB_M8(va)  (*(const uint8_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BB_M32(va) (*(const uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BB_MF(va)  (*(const float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

#define BB_STEP        0x004A1EB4u      /* the simulation step count (race_service.c) */
#define BB_STAGE       0x1B8u           /* the game module's stage (race_service.c) */
#define BB_VT_CAR      0x003B11A0u      /* CB3PlayerCar's vtable (bm_autopilot.c) */
#define BB_BLOCK       0x119Cu          /* the car's boost block */
#define BB_BAR         0x38u
#define BB_BAR_MAX     0x34u
#define BB_ACTIVE      0x52u
#define BB_STEPS_MAX   30u              /* simulation steps from a request to its car update */
#define BB_UPDATES_MAX 3u               /* game updates a request may wait for its car update */

enum { MODE_OFF = 0, MODE_ON = 1, MODE_DEBUG = 2 };

/* The retail NTSC-U default.xbe (title 0x4541005B): .rdata words, the same
 * check as bm_autopilot.c (research\native_gameplay_api\g4\scripts\xbe_words.py). */
static const struct { uint32_t va, word; } s_sig[] = {
    { 0x003B11A0u, 0x0018C470u },       /* CB3PlayerCar's vtable, slot 0 */
    { 0x003B11A4u, 0x0018C510u },       /* slot 1: the car update the mark is in */
    { 0x003A9ACCu, 0x00019FE0u },       /* the game module's vtable, slot 0 */
    { 0x003A9AD0u, 0x0001A000u },       /* slot 1 */
};

/* The status, as words behind a sequence count (odd while written). */
#define BB_WORDS (sizeof(bm_boost_status) / 4)
_Static_assert(sizeof(bm_boost_status) == 44, "bm_boost_status is 44 bytes");
static _Atomic uint32_t s_seq;
static _Atomic uint32_t s_words[BB_WORDS];
static bm_boost_status s_st;                    /* the game thread's own copy */

static _Atomic uint32_t s_mode;
static _Atomic int s_have_thread;
static RECOMP_TLS int t_game;
static uint32_t s_prev;                         /* the race state at the last look */
static uint32_t s_req_step, s_req_age, s_req_race;
static int s_self;

#ifndef MUT
#define MUT 0
#endif

/* ---- v2: award slots, one per plugin that awarded (game thread writes; status words behind a sequence count) ---- */
#define BB_AWARD_SLOTS 256u             /* = the plugin limit (BO3_MODFS_MAX_MODS, platform 0.1.8) */
#define BB_RATE_STEPS  60u              /* "a second" = 60 simulation steps (the game's step rate) */
#define BB_AW_WORDS (sizeof(bm_boost_award_status) / 4)
_Static_assert(sizeof(bm_boost_award_status) == 28, "bm_boost_award_status is 28 bytes");
typedef struct bb_award_slot {
    bm_boost_award_status st;           /* the game thread's own copy */
    uint32_t pending;                   /* 1: an award waits for player 1's car update */
    float amount;
    uint32_t req_step, req_age, req_race;
    uint32_t recent[BM_BOOST_AWARDS_PER_SECOND];   /* steps of the last accepted awards (ring) */
    uint32_t nrecent, rhead;
} bb_award_slot;
static _Atomic(uintptr_t) s_aw_host[BB_AWARD_SLOTS];
static bb_award_slot s_aw[BB_AWARD_SLOTS];
static _Atomic uint32_t s_aw_seq[BB_AWARD_SLOTS];
static _Atomic uint32_t s_aw_words[BB_AWARD_SLOTS][BB_AW_WORDS];
static uint32_t s_naw;                  /* slots taken (game thread) */

static void aw_publish(uint32_t k)
{
    uint32_t w[BB_AW_WORDS], q = atomic_load_explicit(&s_aw_seq[k], memory_order_relaxed);
    s_aw[k].st.struct_size = (uint32_t)sizeof s_aw[k].st;
    memcpy(w, &s_aw[k].st, sizeof w);
    atomic_store_explicit(&s_aw_seq[k], q + 1, memory_order_relaxed);
    atomic_thread_fence(memory_order_release);
    for (size_t i = 0; i < BB_AW_WORDS; i++)
        atomic_store_explicit(&s_aw_words[k][i], w[i], memory_order_relaxed);
    atomic_store_explicit(&s_aw_seq[k], q + 2, memory_order_release);
}

static void aw_set(uint32_t k, uint32_t state, uint32_t reason)
{
    s_aw[k].st.state = state;
    s_aw[k].st.reason = reason;
    aw_publish(k);
}

/* the slot of a plugin: -1 none (find only), else its index (take: a new slot when there is room) */
static int aw_slot(td_host *host, int take)
{
    for (uint32_t k = 0; k < BB_AWARD_SLOTS; k++) {
        uintptr_t h = atomic_load(&s_aw_host[k]);
        if (h == (uintptr_t)host)
            return (int)k;
        if (!h)
            break;
    }
    if (!take || s_naw >= BB_AWARD_SLOTS)
        return -1;
    memset(&s_aw[s_naw], 0, sizeof s_aw[s_naw]);
    aw_publish(s_naw);
    atomic_store(&s_aw_host[s_naw], (uintptr_t)host);
    return (int)s_naw++;
}

/* a new race: pending awards dropped, the counts start again */
static void aw_new_race(void)
{
    for (uint32_t k = 0; k < s_naw; k++) {
        if (s_aw[k].pending) {
#if MUT == 15
            continue;                   /* defect: a pending award survives into the next race */
#else
            s_aw[k].pending = 0;
            s_aw[k].st.state = BM_BOOST_STATE_REFUSED;
            s_aw[k].st.reason = BM_BOOST_STALE;
#endif
        } else {
            s_aw[k].st.state = BM_BOOST_STATE_IDLE;
            s_aw[k].st.reason = BM_BOOST_OK;
        }
        s_aw[k].st.awards = 0;
        s_aw[k].nrecent = s_aw[k].rhead = 0;
        aw_publish(k);
    }
}

/* the race left the racing state with an award pending: dropped */
static void aw_drop_pending(uint32_t reason)
{
    for (uint32_t k = 0; k < s_naw; k++)
        if (s_aw[k].pending) {
            s_aw[k].pending = 0;
            aw_set(k, BM_BOOST_STATE_REFUSED, reason);
        }
}

static void publish(void)
{
    uint32_t w[BB_WORDS], q = atomic_load_explicit(&s_seq, memory_order_relaxed);
    s_st.struct_size = (uint32_t)sizeof s_st;
    memcpy(w, &s_st, sizeof w);
    atomic_store_explicit(&s_seq, q + 1, memory_order_relaxed);
    atomic_thread_fence(memory_order_release);
    for (size_t k = 0; k < BB_WORDS; k++)
        atomic_store_explicit(&s_words[k], w[k], memory_order_relaxed);
    atomic_store_explicit(&s_seq, q + 2, memory_order_release);
}

static void set(uint32_t state, uint32_t reason)
{
    s_st.state = state;
    s_st.reason = reason;
    publish();
}

static void say(const char *what, uint32_t reason)
{
    static const char *const names[] = { "ok", "bad argument", "unavailable", "wrong thread", "unsupported game",
                                         "debug autopilot", "not in a race", "countdown", "paused", "race over",
                                         "no car", "already pending", "limit", "stale", "not added" };
    /* "[AUTOPILOT]": the line the guarded scene runner keeps (it drops [PLUGIN] lines). */
    fprintf(stderr, "[AUTOPILOT] bmashup.boost: %s (%s, race %u)\n", what,
            reason < sizeof names / sizeof names[0] ? names[reason] : "?", (unsigned)s_st.race);
}

static int in_stage(uint32_t state)
{
    return state >= TD_RACE_PRESTART && state <= TD_RACE_FINISHED;
}

/* The race moved to `state`: a new race (counted, the fills start again), a
 * request dropped. The same state again changes nothing. */
static void observe(uint32_t state)
{
    if (state == s_prev)
        return;
    if (in_stage(state) && (!in_stage(s_prev) || (state == TD_RACE_PRESTART && s_prev != TD_RACE_PRESTART))) {
        if (s_st.state == BM_BOOST_STATE_PENDING)
            say("request dropped", BM_BOOST_STALE);
        s_st.race++;
        s_st.fills = 0;
        set(BM_BOOST_STATE_IDLE, BM_BOOST_OK);
        aw_new_race();                                  /* v2 */
    } else {
        if (s_st.state == BM_BOOST_STATE_PENDING && state != TD_RACE_RACING) {
            set(BM_BOOST_STATE_REFUSED, BM_BOOST_STALE);
            say("request dropped", BM_BOOST_STALE);
        }
        if (state != TD_RACE_RACING)
            aw_drop_pending(BM_BOOST_STALE);            /* v2 */
    }
    s_prev = state;
}

static int build_ok(void)
{
    if (!g_xbox_mem_offset)
        return 0;
    for (size_t k = 0; k < sizeof s_sig / sizeof s_sig[0]; k++)
        if (BB_M32(s_sig[k].va) != s_sig[k].word)
            return 0;
    return 1;
}

/* The game's own state, read (never written): BM_BOOST_OK when player 1's
 * bar may be topped up now. */
static uint32_t check_game(void)
{
    uint32_t mod, phase;
    if (!build_ok())
        return BM_BOOST_UNSUPPORTED;
    mod = BB_M32(AP_MODULE);
    if (BB_M32(AP_MODULE_STEP) != 5 || mod < 0x10000u || mod >= 0x04000000u || BB_M32(mod) != AP_VT_GAME
            || !BB_M32(mod + BB_STAGE))
        return BM_BOOST_NOT_IN_RACE;
    if (BB_M32(AP_PAUSED_BY) != 0xFFFFFFFFu)
        return BM_BOOST_PAUSED;
    phase = BB_M32(AP_CAR1 + AP_CAR_PHASE);
    if (phase < 2)
        return BM_BOOST_COUNTDOWN;
    if (phase == 3)
        return BM_BOOST_RACE_OVER;
    if (phase != 2)
        return BM_BOOST_NOT_IN_RACE;
    if (BB_M32(AP_CAR1) != BB_VT_CAR || BB_M32(AP_CAR1 + AP_CAR_PLAYER) != 0)
        return BM_BOOST_NO_CAR;
    return BM_BOOST_OK;
}

/* The game's routine on player 1's bar: esi = B, the amount (the maximum, as
 * the game's own refills) pushed, a 0 return address for its ret. The mark
 * is between two of the title's instructions: every guest register the
 * routine (or the gate and the stage call inside it) may change is put back,
 * the x87 stack included. */
static void game_add_boost_bits(uint32_t block, uint32_t amount_bits)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;

    g_esi = block;
    PUSH32(g_esp, amount_bits);                 /* the amount (float bits): v1 the bar's maximum, v2 the award */
    PUSH32(g_esp, 0);                           /* the return address its ret takes */
    sub_0017A530();
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp;
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
}

static void game_add_boost(uint32_t block)
{
    game_add_boost_bits(block, BB_M32(block + BB_BAR_MAX));   /* v1: the amount = the bar's maximum */
}

static void award_update(void);
static void fill_update(void);

void bo3_bm_boost_car_update(void)
{
    uint32_t car = g_esi;

    if (atomic_load(&s_mode) != MODE_ON || car != AP_CAR1 || !g_xbox_mem_offset)
        return;
    t_game = 1;
    if (s_st.state == BM_BOOST_STATE_PENDING)
        fill_update();
    if (s_naw)
        award_update();                                 /* v2: after the fill (both may run in one car update) */
}

/* v1's car-update work for a pending fill (unchanged) */
static void fill_update(void)
{
    uint32_t rc, block = AP_CAR1 + BB_BLOCK;
    float before, after;
    rc = check_game();
    if (rc == BM_BOOST_OK && (s_st.race != s_req_race || BB_M32(BB_STEP) - s_req_step > BB_STEPS_MAX))
        rc = BM_BOOST_STALE;
    if (rc == BM_BOOST_OK && s_st.fills >= BM_BOOST_FILLS_MAX)
        rc = BM_BOOST_LIMIT;
    if (rc != BM_BOOST_OK) {
        set(BM_BOOST_STATE_REFUSED, rc);
        say("request refused at the car update", rc);
        return;
    }
    before = BB_MF(block + BB_BAR);
    game_add_boost(block);
    after = BB_MF(block + BB_BAR);
    s_st.fills++;
    s_st.meter_before = before;
    s_st.meter_after = after;
    set(BM_BOOST_STATE_DONE, after > before || before >= BB_MF(block + BB_BAR_MAX) ? BM_BOOST_OK : BM_BOOST_NOT_ADDED);
    fprintf(stderr, "[AUTOPILOT] bmashup.boost: filled %u/%u at step %u (race %u): bar %.1f -> %.1f of %.1f%s\n",
            (unsigned)s_st.fills, BM_BOOST_FILLS_MAX, (unsigned)BB_M32(BB_STEP), (unsigned)s_st.race, before, after,
            BB_MF(block + BB_BAR_MAX), s_st.reason == BM_BOOST_NOT_ADDED ? " (the game added nothing)" : "");
}

static int latest(td_race_snapshot *s)
{
    memset(s, 0, sizeof *s);
    s->struct_size = (uint32_t)sizeof *s;
    return bo3_race_api()->get((td_host *)(void *)&s_self, s) == TD_RACE_OK;
}

static uint32_t check_snapshot(const td_race_snapshot *s)
{
    switch (s->state) {
    case TD_RACE_RACING:
        return (s->valid & TD_RACE_HAVE_CAR) ? BM_BOOST_OK : BM_BOOST_NO_CAR;
    case TD_RACE_PRESTART:
        return BM_BOOST_COUNTDOWN;
    case TD_RACE_PAUSED:
        return BM_BOOST_PAUSED;
    case TD_RACE_FINISHED:
        return BM_BOOST_RACE_OVER;
    default:
        return BM_BOOST_NOT_IN_RACE;
    }
}

static int32_t TD_CALL bb_fill(td_host *host)
{
    td_race_snapshot s;
    uint32_t rc, mode = atomic_load(&s_mode);

    if (!host)
        return BM_BOOST_BAD_ARG;
    if (mode == MODE_DEBUG)
        return BM_BOOST_DEBUG_AUTOPILOT;
    if (mode != MODE_ON || !atomic_load(&s_have_thread))
        return BM_BOOST_UNAVAILABLE;
    if (!t_game)
        return BM_BOOST_WRONG_THREAD;           /* nothing noted: the status is the game thread's */
    if (!latest(&s))
        return BM_BOOST_UNAVAILABLE;
    observe(s.state);
    if (s_st.state == BM_BOOST_STATE_PENDING)
        return BM_BOOST_ALREADY_PENDING;
    rc = s_st.fills >= BM_BOOST_FILLS_MAX ? BM_BOOST_LIMIT : check_snapshot(&s);
    if (rc == BM_BOOST_OK)
        rc = check_game();
    if (rc != BM_BOOST_OK) {
        set(BM_BOOST_STATE_REFUSED, rc);
        say("request refused", rc);
        return (int32_t)rc;
    }
    s_req_step = BB_M32(BB_STEP);
    s_req_age = 0;
    s_req_race = s_st.race;
    set(BM_BOOST_STATE_PENDING, BM_BOOST_OK);
    say("request accepted; the top-up waits for player 1's car update", BM_BOOST_OK);
    return BM_BOOST_OK;
}

static int32_t TD_CALL bb_status(td_host *host, bm_boost_status *out)
{
    uint32_t w[BB_WORDS], a, b, room;

    if (!host || !out || out->struct_size < 8)
        return BM_BOOST_BAD_ARG;
    do {
        a = atomic_load_explicit(&s_seq, memory_order_acquire);
        for (size_t k = 0; k < BB_WORDS; k++)
            w[k] = atomic_load_explicit(&s_words[k], memory_order_relaxed);
        atomic_thread_fence(memory_order_acquire);
        b = atomic_load_explicit(&s_seq, memory_order_relaxed);
    } while ((a & 1u) || a != b);
    room = out->struct_size < sizeof w ? out->struct_size : (uint32_t)sizeof w;
    memcpy(out, w, room);
    out->struct_size = room;
    return BM_BOOST_OK;
}

/* ---- v2: award ---- */
static int amount_ok(float amount, float bar_max)
{
#if MUT == 11
    (void)bar_max;
    return amount > 0.0f;                               /* defect: no upper bound (and NaN / inf not refused) */
#else
    return isfinite(amount) && amount > 0.0f && isfinite(bar_max) && bar_max > 0.0f &&
           amount <= BM_BOOST_AWARD_MAX_BARS * bar_max;
#endif
}

/* accepted in the last 60 steps (ring of the last BM_BOOST_AWARDS_PER_SECOND accepted steps) */
static int rate_ok(const bb_award_slot *a, uint32_t now)
{
#if MUT == 12
    (void)a; (void)now;
    return 1;                                           /* defect: no rate bound */
#else
    uint32_t in = 0;
    for (uint32_t i = 0; i < a->nrecent; i++)
        if (now - a->recent[i] < BB_RATE_STEPS)
            in++;
    return in < BM_BOOST_AWARDS_PER_SECOND;
#endif
}

static void award_update(void)
{
    uint32_t block = AP_CAR1 + BB_BLOCK;
    for (uint32_t k = 0; k < s_naw; k++) {
        bb_award_slot *a = &s_aw[k];
        uint32_t rc, bits;
        float before, after;
        if (!a->pending)
            continue;
        a->pending = 0;
        rc = check_game();
        if (rc == BM_BOOST_OK && (s_st.race != a->req_race || BB_M32(BB_STEP) - a->req_step > BB_STEPS_MAX))
            rc = BM_BOOST_STALE;
#if MUT != 13
        if (rc == BM_BOOST_OK && a->st.awards >= BM_BOOST_AWARDS_PER_RACE)
            rc = BM_BOOST_LIMIT;
#endif
        if (rc == BM_BOOST_OK && !amount_ok(a->amount, BB_MF(block + BB_BAR_MAX)))
            rc = BM_BOOST_OUT_OF_RANGE;                 /* the maximum changed since the request */
        if (rc != BM_BOOST_OK) {
            aw_set(k, BM_BOOST_STATE_REFUSED, rc);
            say("award refused at the car update", rc);
            continue;
        }
        memcpy(&bits, &a->amount, 4);
        before = BB_MF(block + BB_BAR);
        game_add_boost_bits(block, bits);
        after = BB_MF(block + BB_BAR);
        a->st.awards++;
        a->st.meter_before = before;
        a->st.meter_after = after;
        aw_set(k, BM_BOOST_STATE_DONE, after > before || before >= BB_MF(block + BB_BAR_MAX) ? BM_BOOST_OK
                                                                                             : BM_BOOST_NOT_ADDED);
        fprintf(stderr, "[AUTOPILOT] bmashup.boost: award %.1f (plugin slot %u, %u this race) at step %u (race %u): bar %.1f -> "
                "%.1f of %.1f%s\n", (double)a->amount, (unsigned)k, (unsigned)a->st.awards, (unsigned)BB_M32(BB_STEP),
                (unsigned)s_st.race, before, after, BB_MF(block + BB_BAR_MAX),
                a->st.reason == BM_BOOST_NOT_ADDED ? " (the game added nothing)" : "");
    }
}

static int32_t TD_CALL bb_award(td_host *host, uint32_t player, float amount)
{
    td_race_snapshot s;
    uint32_t rc, mode = atomic_load(&s_mode), now;
    int k;
    bb_award_slot *a;

    if (!host)
        return BM_BOOST_BAD_ARG;
#if MUT == 14
    if (player > 1)
        return BM_BOOST_NO_PLAYER;                      /* defect: player 1 (split screen, untested) accepted */
#else
    if (player == 1)
        return BM_BOOST_UNSUPPORTED;                    /* R6: split screen not tested on the platform */
    if (player != 0)
        return BM_BOOST_NO_PLAYER;
#endif
    if (mode == MODE_DEBUG)
        return BM_BOOST_DEBUG_AUTOPILOT;
    if (mode != MODE_ON || !atomic_load(&s_have_thread))
        return BM_BOOST_UNAVAILABLE;
    if (!t_game)
        return BM_BOOST_WRONG_THREAD;
    if (!latest(&s))
        return BM_BOOST_UNAVAILABLE;
    observe(s.state);
    k = aw_slot(host, 1);
    if (k < 0)
        return BM_BOOST_UNAVAILABLE;                    /* more plugins than slots (cannot happen within the plugin limit) */
    a = &s_aw[k];
    a->st.requested = amount;
    if (a->pending)
        return BM_BOOST_ALREADY_PENDING;
    now = BB_M32(BB_STEP);
    rc = check_snapshot(&s);
    if (rc == BM_BOOST_OK)
        rc = check_game();
    if (rc == BM_BOOST_OK && !amount_ok(amount, BB_MF(AP_CAR1 + BB_BLOCK + BB_BAR_MAX)))
        rc = BM_BOOST_OUT_OF_RANGE;
#if MUT != 13
    if (rc == BM_BOOST_OK && a->st.awards >= BM_BOOST_AWARDS_PER_RACE)
        rc = BM_BOOST_LIMIT;
#endif
    if (rc == BM_BOOST_OK && !rate_ok(a, now))
        rc = BM_BOOST_RATE;
    if (rc != BM_BOOST_OK) {
        aw_set((uint32_t)k, BM_BOOST_STATE_REFUSED, rc);
        return (int32_t)rc;
    }
    a->recent[a->rhead] = now;
    a->rhead = (a->rhead + 1) % BM_BOOST_AWARDS_PER_SECOND;
    if (a->nrecent < BM_BOOST_AWARDS_PER_SECOND)
        a->nrecent++;
    a->pending = 1;
    a->amount = amount;
    a->req_step = now;
    a->req_age = 0;
    a->req_race = s_st.race;
    aw_set((uint32_t)k, BM_BOOST_STATE_PENDING, BM_BOOST_OK);
    return BM_BOOST_OK;
}

static int32_t TD_CALL bb_award_status(td_host *host, uint32_t player, bm_boost_award_status *out)
{
    uint32_t w[BB_AW_WORDS], a, b, room;
    int k;

    if (!host || !out || out->struct_size < 8)
        return BM_BOOST_BAD_ARG;
    if (player > 1)
        return BM_BOOST_NO_PLAYER;
    room = out->struct_size < sizeof w ? out->struct_size : (uint32_t)sizeof w;
    k = player == 0 ? aw_slot(host, 0) : -1;
    if (k < 0) {
        memset(w, 0, sizeof w);
        w[0] = (uint32_t)sizeof w;                      /* IDLE: never awarded (player 1: never possible) */
    } else {
        do {
            a = atomic_load_explicit(&s_aw_seq[k], memory_order_acquire);
            for (size_t i = 0; i < BB_AW_WORDS; i++)
                w[i] = atomic_load_explicit(&s_aw_words[k][i], memory_order_relaxed);
            atomic_thread_fence(memory_order_acquire);
            b = atomic_load_explicit(&s_aw_seq[k], memory_order_relaxed);
        } while ((a & 1u) || a != b);
    }
    memcpy(out, w, room);
    out->struct_size = room;
    return BM_BOOST_OK;
}

static const bm_boost_api s_api = {
    (uint32_t)sizeof(bm_boost_api), BM_BOOST_VERSION, bb_fill, bb_status, bb_award, bb_award_status
};

const bm_boost_api *bo3_bm_boost_api(void)
{
    return &s_api;
}

void bo3_bm_boost_init(int debug_autopilot)
{
    s_prev = TD_RACE_NONE;
    s_req_step = s_req_age = s_req_race = 0;
    memset(&s_st, 0, sizeof s_st);
    atomic_store(&s_have_thread, 0);
    for (uint32_t k = 0; k < BB_AWARD_SLOTS; k++) {     /* v2: no award slot taken */
        atomic_store(&s_aw_host[k], 0);
        memset(&s_aw[k], 0, sizeof s_aw[k]);
    }
    s_naw = 0;
    if (debug_autopilot) {
        s_st.state = BM_BOOST_STATE_REFUSED;
        s_st.reason = BM_BOOST_DEBUG_AUTOPILOT;
        atomic_store(&s_mode, MODE_DEBUG);
        fprintf(stderr, "[AUTOPILOT] bmashup.boost: off: RECOMP_DEBUG=autopilot holds the car update\n");
    } else {
        atomic_store(&s_mode, MODE_ON);
    }
    publish();
    bo3_plugins_service(BM_BOOST_SERVICE, BM_BOOST_VERSION, &s_api);
}

void bo3_bm_boost_after_update(void)
{
    td_race_snapshot s;
    uint32_t block = AP_CAR1 + BB_BLOCK;

    if (atomic_load(&s_mode) != MODE_ON)
        return;
    t_game = 1;
    atomic_store(&s_have_thread, 1);
    if (!latest(&s))
        return;
    observe(s.state);
    if (s_st.state == BM_BOOST_STATE_PENDING && ++s_req_age > BB_UPDATES_MAX) {
        set(BM_BOOST_STATE_REFUSED, BM_BOOST_STALE);
        say("request dropped: its car update did not come", BM_BOOST_STALE);
    }
    for (uint32_t k = 0; k < s_naw; k++)                /* v2: the same rule for each pending award */
#if MUT == 16
        (void)k;                                        /* defect: an award waits forever for its car update */
#else
        if (s_aw[k].pending && ++s_aw[k].req_age > BB_UPDATES_MAX) {
            s_aw[k].pending = 0;
            aw_set(k, BM_BOOST_STATE_REFUSED, BM_BOOST_STALE);
            say("award dropped: its car update did not come", BM_BOOST_STALE);
        }
#endif
    /* player 1's bar for status(): read only, in a stage with a car the
     * service knows */
    s_st.have_meter = 0;
    s_st.meter = s_st.meter_max = 0.0f;
    s_st.boosting = 0;
    if (in_stage(s.state) && (s.valid & TD_RACE_HAVE_CAR) && build_ok() && BB_M32(AP_CAR1) == BB_VT_CAR
            && BB_M32(AP_CAR1 + AP_CAR_PLAYER) == 0) {
        s_st.have_meter = 1;
        s_st.meter = BB_MF(block + BB_BAR);
        s_st.meter_max = BB_MF(block + BB_BAR_MAX);
        s_st.boosting = BB_M8(block + BB_ACTIVE) ? 1u : 0u;
    }
    publish();
}
