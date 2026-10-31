/*
 * bm_autopilot.c - "bmashup.autopilot" (include/bmashup_autopilot.h,
 * docs/bmashup-autopilot.md): Burnout Mashup's private gameplay control. A
 * plugin asks; the game's own AI takes over player 1's car for the rest of
 * the race, with the title's own steps (ai_takeover.c, the same ones
 * RECOMP_DEBUG=autopilot has driven races with since BO-130).
 *
 * Where each part runs:
 *   engage()   the game's thread, in a takedawn.race on_update call (or
 *              anywhere else on that thread): checks the latest race
 *              snapshot and the game, and only notes the request. It writes
 *              nothing in the game.
 *   the mark   "ap_update", in player 1's car update (sub_0018C510 after
 *              0x18C511, esi the car), on the game's thread: checks
 *              everything again and, if all still holds, does the takeover
 *              there, where autopilot.c does it. While engaged it also
 *              stamps the controller records each car update, as
 *              autopilot.c does, so the race is not paused for lack of
 *              input, and applies the takeover again when the title has
 *              dropped it in the race (the AI byte back to 0, as after a
 *              crash's reset; G4 run 1: the car coasted to a stop), as
 *              autopilot.c does at every car update. It never writes 0 to
 *              the car's AI byte: there is no hand-back.
 *   a watch    after each update while engaged: a car that has not moved
 *              for BM_STALL_S of race time is reported once ("stalled"), so
 *              that a scene can stop waiting.
 *   after each update: follows the race (takedawn.race's snapshot) and
 *              drops a request the race moved on from.
 *
 * The race a request is for: the service counts races, one more each time
 * the snapshot enters a stage (from the menus, a load or a stage being
 * left) or goes back to the countdown (a restart). A request is dropped
 * (BM_AP_STALE) when the next snapshot is anything but RACING, when the
 * race count changes, when more than BM_STEPS_MAX simulation steps pass
 * between the request and its car update, or when its car update has not
 * come after BM_UPDATES_MAX game updates (a game without the mark: the
 * request simply never runs). Fail closed: anything unknown refuses.
 *
 * The game (NTSC-U, the addresses ai_takeover.h and race_service.c use):
 * the build is recognised by words of the retail default.xbe's .rdata, which
 * the runtime copies into guest memory before the game starts: the player
 * car's vtable 0x3B11A0, whose slot 1 is the update the mark is in, and the
 * game module's vtable 0x3A9ACC. Player 1's car is the CB3PlayerCar the race
 * world's constructor puts at 0x60EA00 + 0x12B7D0 = 0x73A1D0 with that
 * vtable (code at 0x1A9946): its first word and its player index (0) are
 * checked before every takeover.
 *
 * Threads: the status is one 64-bit word (state | reason << 8 | race << 32),
 * written on the game's thread only, read whole from any thread.
 *
 * Version 2 (gp I4, research\native_gameplay_api\platform\gp\slices\autopilot2):
 *   engage2    engage with an explicit policy (BM_AP_POLICY_ONCE_PER_RACE)
 *              bound to the race named (status.race): one takeover in every
 *              race of a process. Why version 1 looked "once per process":
 *              the G4 demo asked once per process (its own flag); the
 *              service was always once per race, and refuses AI_OWNED while
 *              the title's own takeover still holds the car.
 *   release    the title's hand-back (ai_takeover.c bo3_ai_handback), staged
 *              like engage and done in player 1's next car update after the
 *              same checks plus the car's physics link (car + 0x2440, whose
 *              + 0x1580 is the car) and the .rdata 1.0 it copies.
 *   lifecycle  bm_lifecycle.c's LOAD_DONE / RACE_EXIT (the events v2 points):
 *              a request or takeover never outlives one; a takeover only
 *              after a TRACK / RESTART load and before the next race exit;
 *              a read-only census of player 1's car at each, at each new
 *              race, at the GO and at the end (what the title resets).
 */
#include "bm_autopilot.h"

#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ai_takeover.h"
#include "bm_boost.h"
#include "bm_events.h"
#include "bm_lifecycle.h"
#include "plugins.h"
#include "race_service.h"
#include "takedawn_race.h"
#include "platform/recomp_patch.h"
#include "recomp_types.h"

extern RECOMP_TLS uint32_t g_esi;
extern ptrdiff_t g_xbox_mem_offset;

#define BM_M8(va)  (*(const uint8_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BM_M16(va) (*(const int16_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BM_M32(va) (*(const uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BM_MF(va)  (*(const float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

#define BM_STEP        0x004A1EB4u      /* the simulation step count (race_service.c) */
#define BM_STAGE       0x1B8u           /* the game module's stage (race_service.c) */
#define BM_VT_CAR      0x003B11A0u      /* CB3PlayerCar's vtable */
#define BM_STEPS_MAX   30u              /* simulation steps from a request to its car update */
#define BM_UPDATES_MAX 3u               /* game updates a request may wait for its car update */
#define BM_STALL_S     10.0f            /* race seconds without movement while engaged: one "stalled" line */
#define BM_MOVING_MPS  1.0f             /* slower is not moving */

enum { MODE_OFF = 0, MODE_ON = 1, MODE_DEBUG = 2 };

/* The retail NTSC-U default.xbe (title 0x4541005B): .rdata words
 * (research\native_gameplay_api\g4\scripts\xbe_words.py). */
static const struct { uint32_t va, word; } s_sig[] = {
    { 0x003B11A0u, 0x0018C470u },       /* CB3PlayerCar's vtable, slot 0 */
    { 0x003B11A4u, 0x0018C510u },       /* slot 1: the car update the mark is in */
    { 0x003A9ACCu, 0x00019FE0u },       /* the game module's vtable, slot 0 */
    { 0x003A9AD0u, 0x0001A000u },       /* slot 1 */
};

static _Atomic uint32_t s_mode;
static _Atomic uint64_t s_status;               /* state | reason << 8 | race << 32 */
static _Atomic int s_have_thread;               /* an update was seen: the game's thread is known */
static RECOMP_TLS int t_game;                   /* this is the game's thread */
static uint32_t s_prev;                         /* the race state at the last look */
static uint32_t s_req_step, s_req_age, s_req_race;
static unsigned s_retakes;                      /* takeovers applied again in this race (the title dropped it) */
static float s_moving_t;                        /* race time the engaged car last moved */
static int s_stalled;                           /* the "stalled" line was given (until it moves again) */
static int s_self;                              /* the service's own host handle for takedawn.race */
/* version 2 */
static _Atomic uint32_t s_rel_reason;           /* status.release_reason */
static _Atomic uint32_t s_engaged_races;        /* status.engaged_races */
static int s_rel_pending;                       /* a release waits for player 1's car update */
static uint32_t s_rel_step, s_rel_age, s_rel_race;
static int s_lc_seen, s_lc_ok;                  /* a lifecycle event came; the last one allows a race */
static uint32_t s_go_race;                      /* race + 1 the GO census was given for */
static unsigned s_censuses, s_releases;

static uint32_t st_state(void) { return (uint32_t)(atomic_load(&s_status) & 0xFFu); }
static uint32_t st_race(void) { return (uint32_t)(atomic_load(&s_status) >> 32); }

static void st_set(uint32_t state, uint32_t reason)
{
    atomic_store(&s_status, (uint64_t)state | (uint64_t)reason << 8 | (uint64_t)st_race() << 32);
}

static void say(const char *what, uint32_t reason)
{
    static const char *const names[] = { "ok", "bad argument", "unavailable", "wrong thread", "unsupported game",
                                         "debug autopilot", "not in a race", "countdown", "paused", "race over",
                                         "no car", "AI already drives", "already pending", "already used", "stale",
                                         "wrong race", "not engaged" };
    fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: %s (%s, race %u)\n", what,
            reason < sizeof names / sizeof names[0] ? names[reason] : "?", (unsigned)st_race());
}

static unsigned s_results;                      /* "result" lines given (for the unit test) */

/* The engaged race's result, once, from player 1's race record: whichever
 * sees the finish first (the car update at phase 3, or the snapshot). */
static void say_result(void)
{
    s_results++;
    fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: result place %d/%u time %.3f s best lap %.3f s laps %u\n",
            BM_M16(AP_CAR1 + AP_CAR_PLACE), BM_M32(AP_RACERS), BM_MF(AP_CAR1 + AP_CAR_TIME), BM_MF(AP_CAR1 + AP_CAR_BEST),
            BM_M32(AP_CAR1 + AP_CAR_LAPS));
}

static int in_stage(uint32_t state)
{
    return state >= TD_RACE_PRESTART && state <= TD_RACE_FINISHED;
}

/* Version 2: player 1's car as the title left it, read only, one line:
 * the evidence of what the title resets between races (gp I4). */
static void census(const char *at)
{
    uint32_t car = AP_CAR1, phys;
    int link;

    if (!g_xbox_mem_offset)
        return;
    s_censuses++;
    phys = BM_M32(car + AP_CAR_PHYS);
    link = phys >= 0x10000u && phys < 0x04000000u - 0x2000u && BM_M32(phys + AP_PHYS_CAR) == car;
    fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: census at %s (race %u): vtable %s, player %u, phase %u, AI byte %u, "
                    "+0x19D0 %08X %08X %08X %08X, physics link %s",
            at, (unsigned)st_race(), BM_M32(car) == BM_VT_CAR ? "ok" : "other", (unsigned)BM_M32(car + AP_CAR_PLAYER),
            (unsigned)BM_M32(car + AP_CAR_PHASE), (unsigned)BM_M8(car + AP_CAR_AI), (unsigned)BM_M32(car + AP_CAR_AI_RESET),
            (unsigned)BM_M32(car + AP_CAR_AI_RESET + 4), (unsigned)BM_M32(car + AP_CAR_AI_RESET + 8),
            (unsigned)BM_M32(car + AP_CAR_AI_RESET + 12), link ? "ok" : "no");
    if (link)
        fprintf(stderr, " (+0x1524 %u, +0x1534 %.3f)", (unsigned)BM_M32(phys + AP_PHYS_MODE), BM_MF(phys + AP_PHYS_BLEND));
    fprintf(stderr, "\n");
}

/* Version 2: a staged release that will not run. */
static void drop_release(uint32_t reason, const char *why)
{
    if (!s_rel_pending)
        return;
    s_rel_pending = 0;
    atomic_store(&s_rel_reason, reason);
    say(why, reason);
}

/* The race moved to `state`: a new race, the end of an engaged one, a
 * request dropped. The same state again changes nothing. */
static void observe(uint32_t state)
{
    uint32_t cur = st_state();
    if (state == s_prev)
        return;
    if (in_stage(state) && (!in_stage(s_prev) || (state == TD_RACE_PRESTART && s_prev != TD_RACE_PRESTART))) {
        if (cur == BM_AP_STATE_ENGAGED)
            say("race left while engaged; the car is not handed back", BM_AP_OK);
        if (cur == BM_AP_STATE_PENDING)
            say("request dropped", BM_AP_STALE);
        drop_release(BM_AP_STALE, "release dropped: a new race");
        atomic_store(&s_status, (uint64_t)BM_AP_STATE_IDLE | (uint64_t)(st_race() + 1u) << 32);
        atomic_store(&s_rel_reason, BM_AP_OK);
        s_retakes = 0;
        s_stalled = 0;
        census("a new race");
    } else if (cur == BM_AP_STATE_ENGAGED && state != TD_RACE_RACING && state != TD_RACE_PAUSED) {
        drop_release(BM_AP_RACE_OVER, "release dropped: the race ended");
        if (state == TD_RACE_FINISHED && g_xbox_mem_offset)
            say_result();                       /* the snapshot saw the finish first (G4 r2) */
        st_set(BM_AP_STATE_ENDED, BM_AP_OK);
        say("ended; the car is not handed back", BM_AP_OK);
        census("the end");
    } else if (cur == BM_AP_STATE_PENDING && state != TD_RACE_RACING) {
        st_set(BM_AP_STATE_REFUSED, BM_AP_STALE);
        say("request dropped", BM_AP_STALE);
    }
    if (state != TD_RACE_RACING)
        drop_release(BM_AP_STALE, "release dropped: not racing before its car update");
    s_prev = state;
}

static int build_ok(void)
{
    if (!g_xbox_mem_offset)
        return 0;
    for (size_t k = 0; k < sizeof s_sig / sizeof s_sig[0]; k++)
        if (BM_M32(s_sig[k].va) != s_sig[k].word)
            return 0;
    return 1;
}

/* The game's own state, read (never written): BM_AP_OK when player 1's car
 * may be taken over now. */
static uint32_t check_game(void)
{
    uint32_t mod, phase;
    if (!build_ok())
        return BM_AP_UNSUPPORTED;
    if (s_lc_seen && !s_lc_ok)
        return BM_AP_NOT_IN_RACE;               /* v2: no TRACK / RESTART load since the last race exit */
    mod = BM_M32(AP_MODULE);
    if (BM_M32(AP_MODULE_STEP) != 5 || mod < 0x10000u || mod >= 0x04000000u || BM_M32(mod) != AP_VT_GAME
            || !BM_M32(mod + BM_STAGE))
        return BM_AP_NOT_IN_RACE;
    if (BM_M32(AP_PAUSED_BY) != 0xFFFFFFFFu)
        return BM_AP_PAUSED;
    phase = BM_M32(AP_CAR1 + AP_CAR_PHASE);
    if (phase < 2)
        return BM_AP_COUNTDOWN;
    if (phase == 3)
        return BM_AP_RACE_OVER;
    if (phase != 2)
        return BM_AP_NOT_IN_RACE;
    if (BM_M32(AP_CAR1) != BM_VT_CAR || BM_M32(AP_CAR1 + AP_CAR_PLAYER) != 0)
        return BM_AP_NO_CAR;
    if (BM_M8(AP_CAR1 + AP_CAR_AI))
        return BM_AP_AI_OWNED;
    return BM_AP_OK;
}

/* autopilot.c's ap_in_play: the race is in play for player 1's car. */
static int in_play(void)
{
    uint32_t mod = BM_M32(AP_MODULE);
    if (mod < 0x10000u || mod >= 0x04000000u || BM_M32(mod) != AP_VT_GAME)
        return 0;
    if (BM_M32(AP_PAUSED_BY) != 0xFFFFFFFFu || BM_M32(AP_MODULE_STEP) == 6)
        return 0;
    return BM_M32(AP_CAR1 + AP_CAR_PHASE) == 2;
}

/* Version 2: may the staged release run now, in player 1's car update? */
static uint32_t check_release(uint32_t car)
{
    uint32_t phys;

    if (!build_ok() || BM_M32(AP_ONE) != 0x3F800000u)
        return BM_AP_UNSUPPORTED;
    if (BM_M32(AP_PAUSED_BY) != 0xFFFFFFFFu)
        return BM_AP_PAUSED;
    if (BM_M32(car + AP_CAR_PHASE) == 3)
        return BM_AP_RACE_OVER;
    if (!in_play() || (s_lc_seen && !s_lc_ok))
        return BM_AP_NOT_IN_RACE;
    if (st_race() != s_rel_race || BM_M32(BM_STEP) - s_rel_step > BM_STEPS_MAX)
        return BM_AP_STALE;
    if (BM_M32(car) != BM_VT_CAR || BM_M32(car + AP_CAR_PLAYER) != 0)
        return BM_AP_NO_CAR;
    phys = BM_M32(car + AP_CAR_PHYS);
    if (phys < 0x10000u || phys >= 0x04000000u - 0x2000u || BM_M32(phys + AP_PHYS_CAR) != car)
        return BM_AP_NO_CAR;                    /* the physics object is not this car's */
    return BM_AP_OK;
}

/* A player car's update is about to run: the autopilot's part. */
static void autopilot_car_update(void)
{
    uint32_t car = g_esi, state, rc;

    if (car != AP_CAR1 || !g_xbox_mem_offset)
        return;
    t_game = 1;
    state = st_state();
    if (BM_M32(car + AP_CAR_PHASE) == 2 && s_go_race != st_race() + 1u) {
        s_go_race = st_race() + 1u;
        census("the GO (player 1's first car update in play)");
    }
    if (state == BM_AP_STATE_ENGAGED && s_rel_pending && BM_M32(car + AP_CAR_PHASE) != 3) {
        int wrote = 0;
        s_rel_pending = 0;
        rc = check_release(car);
        if (rc == BM_AP_OK) {
            if (BM_M8(car + AP_CAR_AI)) {
                bo3_ai_handback(car);
                wrote = 1;
            }
            s_releases++;
            atomic_store(&s_rel_reason, BM_AP_OK);
            st_set(BM_AP_STATE_RELEASED, BM_AP_OK);
            fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: released at step %u (race %u): %s; the pad drives player 1\n",
                    (unsigned)BM_M32(BM_STEP), (unsigned)st_race(),
                    wrote ? "the title's hand-back steps (SetAIControlled 0)" : "no write, the title had cleared the AI byte");
            census("the release");
            return;
        }
        atomic_store(&s_rel_reason, rc);
        say("release refused at the car update; still engaged", rc);
    }
    if (state == BM_AP_STATE_ENGAGED) {
        if (BM_M32(car + AP_CAR_PHASE) == 3) {
            drop_release(BM_AP_RACE_OVER, "release dropped: the finish");
            say_result();
            st_set(BM_AP_STATE_ENDED, BM_AP_OK);
            say("ended at the finish; the car is not handed back", BM_AP_OK);
            census("the end");
        } else if (in_play()) {
            /* The title can drop the takeover in a race (the AI byte back to
             * 0, as after a crash's reset: the car then coasts on an empty
             * pad). It is applied again here, the same steps, as
             * RECOMP_DEBUG=autopilot does at every car update; only for the
             * same car, in this race (ENGAGED ends with it). */
            if (!BM_M8(car + AP_CAR_AI) && build_ok() && BM_M32(car) == BM_VT_CAR && BM_M32(car + AP_CAR_PLAYER) == 0) {
                bo3_ai_takeover(car);
                s_retakes++;
                fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: taken again at step %u (race %u): the title had cleared "
                                "the AI byte (%u in this race)\n", (unsigned)BM_M32(BM_STEP), (unsigned)st_race(), s_retakes);
            }
            bo3_ai_stamp_pads();
        }
        return;
    }
    if (state != BM_AP_STATE_PENDING)
        return;
    rc = check_game();
    if (rc == BM_AP_OK && (st_race() != s_req_race || BM_M32(BM_STEP) - s_req_step > BM_STEPS_MAX))
        rc = BM_AP_STALE;
    if (rc != BM_AP_OK) {
        st_set(BM_AP_STATE_REFUSED, rc);
        say("request refused at the car update", rc);
        return;
    }
    bo3_ai_takeover(car);
    bo3_ai_stamp_pads();
    s_moving_t = BM_MF(car + AP_CAR_TIME);
    s_stalled = 0;
    atomic_store(&s_engaged_races, atomic_load(&s_engaged_races) + 1u);
    st_set(BM_AP_STATE_ENGAGED, BM_AP_OK);
    fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: engaged at step %u (race %u): the game's AI drives player 1; "
                    "no hand-back\n", (unsigned)BM_M32(BM_STEP), (unsigned)st_race());
}

/* The "ap_update" mark (a player car's update is about to run) belongs to the
 * engine-point dispatcher (bm_events.c); both Burnout Mashup services are its
 * writers there, in this order, and the "bmashup.events" observers run before
 * them (bm_events_service.c). The dispatcher puts the guest registers back
 * after each, so the boost part sees the car in g_esi again. */
static int s_car_mark = -1;

static void autopilot_writer(void *user)
{
    (void)user;
    autopilot_car_update();
}

static void boost_writer(void *user)
{
    (void)user;
    bo3_bm_boost_car_update();
}

int bo3_bm_car_update_mark(void)
{
    return s_car_mark;
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
        return (s->valid & TD_RACE_HAVE_CAR) ? BM_AP_OK : BM_AP_NO_CAR;
    case TD_RACE_PRESTART:
        return BM_AP_COUNTDOWN;
    case TD_RACE_PAUSED:
        return BM_AP_PAUSED;
    case TD_RACE_FINISHED:
        return BM_AP_RACE_OVER;
    default:
        return BM_AP_NOT_IN_RACE;
    }
}

/* engage (version 1) and engage2 (race 0: the race in play; else that race only) */
static int32_t engage_for(td_host *host, uint32_t race)
{
    td_race_snapshot s;
    uint32_t state, rc, mode = atomic_load(&s_mode);

    if (!host)
        return BM_AP_BAD_ARG;
    if (mode == MODE_DEBUG)
        return BM_AP_DEBUG_AUTOPILOT;
    if (mode != MODE_ON || !atomic_load(&s_have_thread))
        return BM_AP_UNAVAILABLE;
    if (!t_game)
        return BM_AP_WRONG_THREAD;              /* nothing noted: the status is the game thread's */
    if (!latest(&s))
        return BM_AP_UNAVAILABLE;
    observe(s.state);
    if (race && race != st_race()) {
        fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: request for race %u refused: race %u is in play (wrong race)\n",
                (unsigned)race, (unsigned)st_race());
        return BM_AP_WRONG_RACE;                /* the status is left as it was */
    }
    state = st_state();
    if (state == BM_AP_STATE_PENDING)
        return BM_AP_ALREADY_PENDING;
    if (state == BM_AP_STATE_ENGAGED || state == BM_AP_STATE_ENDED || state == BM_AP_STATE_RELEASED)
        return BM_AP_ALREADY_USED;
    rc = check_snapshot(&s);
    if (rc == BM_AP_OK)
        rc = check_game();
    if (rc != BM_AP_OK) {
        st_set(BM_AP_STATE_REFUSED, rc);
        say("request refused", rc);
        return (int32_t)rc;
    }
    s_req_step = BM_M32(BM_STEP);
    s_req_age = 0;
    s_req_race = st_race();
    st_set(BM_AP_STATE_PENDING, BM_AP_OK);
    say("request accepted; the takeover waits for player 1's car update", BM_AP_OK);
    return BM_AP_OK;
}

static int32_t TD_CALL bm_engage(td_host *host)
{
    return engage_for(host, 0);
}

static int32_t TD_CALL bm_engage2(td_host *host, const bm_autopilot_request *req)
{
    if (!host || !req || req->struct_size < 12 || req->policy != BM_AP_POLICY_ONCE_PER_RACE)
        return BM_AP_BAD_ARG;
    return engage_for(host, req->race);
}

static int32_t TD_CALL bm_release(td_host *host)
{
    td_race_snapshot s;
    uint32_t rc, mode = atomic_load(&s_mode);

    if (!host)
        return BM_AP_BAD_ARG;
    if (mode == MODE_DEBUG)
        return BM_AP_DEBUG_AUTOPILOT;
    if (mode != MODE_ON || !atomic_load(&s_have_thread))
        return BM_AP_UNAVAILABLE;
    if (!t_game)
        return BM_AP_WRONG_THREAD;
    if (!latest(&s))
        return BM_AP_UNAVAILABLE;
    observe(s.state);
    if (st_state() != BM_AP_STATE_ENGAGED)
        return BM_AP_NOT_ENGAGED;               /* never the title's own takeover: only this service's */
    if (s_rel_pending)
        return BM_AP_ALREADY_PENDING;
    rc = check_snapshot(&s);
    if (rc != BM_AP_OK) {
        atomic_store(&s_rel_reason, rc);
        say("release refused", rc);
        return (int32_t)rc;
    }
    s_rel_pending = 1;
    s_rel_step = BM_M32(BM_STEP);
    s_rel_age = 0;
    s_rel_race = st_race();
    atomic_store(&s_rel_reason, BM_AP_OK);
    say("release accepted; the hand-back waits for player 1's car update", BM_AP_OK);
    return BM_AP_OK;
}

void bo3_bm_autopilot_lifecycle(uint32_t kind, uint32_t load_kind)
{
    uint32_t cur;
    char at[64];

    if (atomic_load(&s_mode) != MODE_ON || (kind != BO3_LC_EV_LOAD_DONE && kind != BO3_LC_EV_RACE_EXIT))
        return;
    t_game = 1;
    s_lc_seen = 1;
    s_lc_ok = kind == BO3_LC_EV_LOAD_DONE && (load_kind == BO3_LC_LD_TRACK || load_kind == BO3_LC_LD_RESTART);
    cur = st_state();
    drop_release(BM_AP_STALE, kind == BO3_LC_EV_LOAD_DONE ? "release dropped: a load end" : "release dropped: a race exit");
    if (cur == BM_AP_STATE_PENDING) {
        st_set(BM_AP_STATE_REFUSED, BM_AP_STALE);
        say(kind == BO3_LC_EV_LOAD_DONE ? "request dropped: a load end" : "request dropped: a race exit", BM_AP_STALE);
    } else if (cur == BM_AP_STATE_ENGAGED) {
        st_set(BM_AP_STATE_ENDED, BM_AP_OK);
        say(kind == BO3_LC_EV_LOAD_DONE ? "ended: a load end; the car is not handed back"
                                        : "ended: a race exit; the car is not handed back", BM_AP_OK);
    }
    if (kind == BO3_LC_EV_LOAD_DONE)
        snprintf(at, sizeof at, "a load end (kind %u, a race %s)", (unsigned)load_kind, s_lc_ok ? "may follow" : "may not");
    else
        snprintf(at, sizeof at, "a race exit");
    census(at);
}

unsigned bo3_bm_autopilot_censuses(void)
{
    return s_censuses;
}

unsigned bo3_bm_autopilot_releases(void)
{
    return s_releases;
}

static int32_t TD_CALL bm_status(td_host *host, bm_autopilot_status *out)
{
    bm_autopilot_status s;
    uint64_t v;
    uint32_t room;

    if (!host || !out || out->struct_size < 8)
        return BM_AP_BAD_ARG;
    v = atomic_load(&s_status);
    s.struct_size = (uint32_t)sizeof s;
    s.state = (uint32_t)(v & 0xFFu);
    s.reason = (uint32_t)(v >> 8 & 0xFFu);
    s.race = (uint32_t)(v >> 32);
    s.release_reason = atomic_load(&s_rel_reason);     /* v2 fields: each read whole, not with the word above */
    s.engaged_races = atomic_load(&s_engaged_races);
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_AP_OK;
}

static const bm_autopilot_api s_api = {
    (uint32_t)sizeof(bm_autopilot_api), BM_AUTOPILOT_VERSION, bm_engage, bm_status, bm_engage2, bm_release
};

const bm_autopilot_api *bo3_bm_autopilot_api(void)
{
    return &s_api;
}

void bo3_bm_autopilot_init(int debug_autopilot)
{
    s_prev = TD_RACE_NONE;
    s_req_step = s_req_age = s_req_race = 0;
    s_retakes = 0;
    s_stalled = 0;
    s_rel_pending = 0;
    s_rel_step = s_rel_age = s_rel_race = 0;
    s_lc_seen = s_lc_ok = 0;
    s_go_race = 0;
    atomic_store(&s_rel_reason, BM_AP_OK);
    atomic_store(&s_engaged_races, 0);
    atomic_store(&s_have_thread, 0);
    if (debug_autopilot) {
        atomic_store(&s_status, (uint64_t)BM_AP_STATE_REFUSED | (uint64_t)BM_AP_DEBUG_AUTOPILOT << 8);
        atomic_store(&s_mode, MODE_DEBUG);
        fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: off: RECOMP_DEBUG=autopilot drives the car\n");
    } else {
        atomic_store(&s_status, (uint64_t)BM_AP_STATE_IDLE);
        if (s_car_mark < 0) {
            s_car_mark = bo3_events_hook("ap_update");
            bo3_events_subscribe(s_car_mark, BO3_EVENT_WRITER, autopilot_writer, NULL, "bmashup.autopilot");
            bo3_events_subscribe(s_car_mark, BO3_EVENT_WRITER, boost_writer, NULL, "bmashup.boost");
        }
        atomic_store(&s_mode, MODE_ON);
    }
    bo3_plugins_service(BM_AUTOPILOT_SERVICE, BM_AUTOPILOT_VERSION, &s_api);
}

void bo3_bm_autopilot_after_update(void)
{
    td_race_snapshot s;

    if (atomic_load(&s_mode) != MODE_ON)
        return;
    t_game = 1;
    atomic_store(&s_have_thread, 1);
    if (!latest(&s))
        return;
    observe(s.state);
    if (st_state() == BM_AP_STATE_PENDING && ++s_req_age > BM_UPDATES_MAX) {
        st_set(BM_AP_STATE_REFUSED, BM_AP_STALE);
        say("request dropped: its car update did not come", BM_AP_STALE);
    }
    if (s_rel_pending && ++s_rel_age > BM_UPDATES_MAX)
        drop_release(BM_AP_STALE, "release dropped: its car update did not come");
    /* A watch, nothing more: an engaged car that has not moved for
     * BM_STALL_S of race time is reported once (a runner can stop waiting). */
    if (st_state() == BM_AP_STATE_ENGAGED && s.state == TD_RACE_RACING && (s.valid & TD_RACE_HAVE_CAR)) {
        if ((s.valid & TD_RACE_HAVE_SPEED) && s.speed_mps >= BM_MOVING_MPS) {
            s_moving_t = s.race_time_s;
            s_stalled = 0;
        } else if (!s_stalled && s.race_time_s - s_moving_t >= BM_STALL_S) {
            s_stalled = 1;
            fprintf(stderr, "[AUTOPILOT] bmashup.autopilot: stalled: player 1's car has not moved for %.0f s of race "
                            "time (race %.1f s, AI byte %u, taken again %u)\n", BM_STALL_S, s.race_time_s,
                    g_xbox_mem_offset ? (unsigned)BM_M8(AP_CAR1 + AP_CAR_AI) : 0u, s_retakes);
        }
    }
}

unsigned bo3_bm_autopilot_retakes(void)
{
    return s_retakes;
}

int bo3_bm_autopilot_stalled(void)
{
    return s_stalled;
}

unsigned bo3_bm_autopilot_results(void)
{
    return s_results;
}
