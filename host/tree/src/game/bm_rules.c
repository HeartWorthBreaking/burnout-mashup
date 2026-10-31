/*
 * bm_rules.c - main19 (platform 0.1.9, hook request P3 E1, patch 35): "bmashup.rules" v1 (include/bmashup_rules.h).
 * Design gp\hookreq\HOOK_REQUEST_DESIGN.md E, sites gp\hookreq\p23\SITES_VERIFIED.md s8.4 (re-checked: tests\p23\step0_c_out.txt:
 * 0x24E92..0x24EA0 = the call of sub_00024F10 with ECX = the entry of the list at 0x73A1A8 (index EAX) and EAX = EBP; sub_00024F10 saves EBX / EBP,
 * takes its argument from [esp + 0xC] and reads +0x4C of EAX; 0x3A9DB8 = 0x00024E30).
 *
 * Only in a race whose logic is the game's own Eliminator (the current logic MEM32(MEM32(0x4D5370) + 0x1B8) has vtable 0x3A9D50)
 * AND that a bmashup.menu ELIMINATOR row started (bo3_rules_mode_race; World Tour is never touched), and only for the plugin
 * that declared that row. Everything happens on the game's thread:
 *   - set_lap_elimination(0): the mark in the per-lap rule sub_00024E30 (bo3_rules_gen.h) skips the game's own call of
 *     sub_00024F10 for this race (the same branch the game takes when no single racer is last);
 *   - eliminate(racer): queued, then the ap_update writer calls the game's own sub_00024F10 with its retail shape (EAX = the
 *     rules object, push the racer): order word, explosion, sign, scoreboard and results are the game's; <= 1 a second;
 *   - end_race(): the writer eliminates the AI racer with the lowest progress word (R + 0x10E4, the per-lap rule's own metric)
 *     once a second until one racer is left; the game's own last-standing end then fires (no state write by the host).
 * Never: the human player (LAST_PLAYER: platform 0.1.9 is one-player only), a racer already out (R + 0x10D2 != 0 or
 * R + 0x16C8 == 0: ALREADY), a racer not taking part (R + 0x19A8 == 0: NO_RACER).
 * UNAVAILABLE in 0.1.9 (BM_P23_RULES_AVAILABLE 0): no menu row can start such a race yet (PR-C / PR-E). Whether the current-logic
 * word holds the same object the per-lap rule runs on is a HYPOTHESIS until PR-E (the mark also checks the object it is given).
 * BO3_HOOKREQ_P23 == 0: every call answers UNAVAILABLE; the mark answers 0.
 * Patch 42 (probe PR-E facts): a racer still in = order R + 0x10D2 == 0xFFFF and R + 0x16C8 != 0 (-1 while racing; patch 35 had
 * order 0 = in, so every eliminate answered ALREADY); the Eliminator logic is the object 0x4D4BD8 with vtable 0x3A9D50 (both
 * checked); the game's per-lap rule eliminates an already-eliminated racer AGAIN (L + 0x4C counts on) - in a claimed race the
 * mark also skips that call; BM_P23_RULES_AVAILABLE 1.
 * MUT=n (tests): 1 the human eliminated  2 no rate limit  3 a non-Eliminator logic accepted  4 the lap call skipped with lap
 *   elimination ON  5 an eliminated racer eliminated again  6 another plugin's claim accepted  7 the queue runs without the 1 s gap
 *   8 end_race eliminates the leader too (down to 0)  10 the game's re-elimination not skipped in a claimed race
 *   11 the logic object not checked (any object with the vtable)  12 order 0 taken as "still in" (patch 35's defect)
 * main21 patch 80 (v2 set_road_rage_props): sub_00110420 asks the race's mode logic (vtable + 0xB0; Road Rage logics 0x3A99A8 /
 * 0x3A9B18 answer 1) and, on 1, skips the block that turns each loaded unit's prop instances into physics bodies (type 5, prop
 * types STATIC + 0x3C). The mark at loc_001108EC (after that call) answers 0 there while the switch is on. Own census.
 *   MUT 21 the census skipped  22 another plugin's switch accepted  23 the game's 0 turned into a skip (the mark forces 1)
 * main21 patch 83 (v3 set_end_session): the pause menu build sub_00085F70 asks the mode logic (vtable + 0xD4) at 0x86190 and on 1
 * offers END SESSION (text 284, the + 0x61 flag the input handler sub_000863F0 reads at 0x865B4 -> the game's END SESSION
 * confirmation); else CRASH NAV when the current game object + 0x1BC is 0x4D5210, else QUIT. The mark at loc_00086196 answers 1
 * where the game would show QUIT while the switch is on. Own census.
 *   MUT 24 the census skipped  25 another plugin's switch accepted  26 CRASH NAV replaced too
 */
#include "bm_rules.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bm_events.h"
#include "bm_guest.h"
#include "bm_lifecycle.h"
#include "plugins.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 1           /* unit tests */
#endif

#define SECOND 60u                  /* car updates a second */
#define QMAX 8u

static const td_host *s_owner, *s_mode_owner;
static int s_lap_on = 1, s_ending;
static int s_loaded;               /* patch 53: the menu-routed race's load is done (claims are valid from here to RACE_EXIT) */
static uint32_t s_queue[QMAX], s_nq;
static uint32_t s_tick, s_last_req = 0xFFFF0000u, s_last_exec = 0xFFFF0000u;
static uint32_t s_eliminated;
static int s_census = -1;
static bo3_rules_elim_fn s_elim;
static RECOMP_TLS int t_game;
#ifndef BO3_HOOKREQ_P10R
#define BO3_HOOKREQ_P10R 1          /* unit tests: the CMake option is not there */
#endif
static const td_host *s_props_owner;   /* patch 80 */
static int s_props_ok = -1;
static uint32_t s_props_used;
#ifndef BO3_HOOKREQ_P11E
#define BO3_HOOKREQ_P11E 1          /* unit tests: the CMake option is not there */
#endif
static const td_host *s_es_owner;   /* patch 83 */
static int s_es_ok = -1;
static uint32_t s_es_used;
#ifndef BO3_HOOKREQ_ZCB
#define BO3_HOOKREQ_ZCB 1           /* unit tests: the CMake option is not there */
#endif
static const td_host *s_cb_owner;   /* patch 105 */
static int s_cb_ok = -1;
static uint32_t s_cb_radius = BM_RULES_CB_RADIUS_DEFAULT, s_cb_arm_calls, s_cb_rearm, s_cb_blasts, s_cb_wrecks;
static bo3_rules_blast_fn s_blast;
static bo3_rules_blast_fn s_push;                                   /* patch 117 */
static uint32_t s_cb_pending, s_cb_pool0, s_cb_pushed, s_cb_traffic;
#ifndef BO3_HOOKREQ_ZRV
#define BO3_HOOKREQ_ZRV 1           /* unit tests: the CMake option is not there */
#endif
#define RV_SLOTS  5u
typedef struct rv_img { uint32_t ac; uint8_t id[RV_SLOTS][8]; uint8_t b[RV_SLOTS]; } rv_img;   /* AI part of a set-up */
static const td_host *s_rv_owner;   /* patch 106 */
static int s_rv_ok = -1, s_rv_saved;
static int32_t s_rv_count = -1, s_rv_car[RV_SLOTS] = { -1, -1, -1, -1, -1 };
static uint32_t s_rv_s, s_rv_applied = 0xFFFFFFFFu, s_rv_sets, s_rv_skipped, s_rv_lines;
static rv_img s_rv_orig, s_rv_written;
#define RV_CMP (offsetof(rv_img, b) + RV_SLOTS)   /* no padding compared */

static uint32_t rd32(uint32_t va) { uint32_t v = 0; bo3_guest_rd32(va, &v); return v; }
static uint8_t rd8(uint32_t va) { uint8_t v = 0; bo3_guest_read(va, &v, 1); return v; }
static uint16_t rd16(uint32_t va) { uint16_t v = 0; bo3_guest_read(va, &v, 2); return v; }

uint32_t bo3_rules_seconds(void) { return SECOND; }
void bo3_rules_set_elim(bo3_rules_elim_fn fn) { s_elim = fn; }
/* patch 53 (runtime m19_r2c): the route runs at the race set-up, before the track load. A claim made between the set-up and that
 * load (plugins' race updates keep running through the transition) was accepted and then dropped by LOAD_DONE's reset, so the
 * plugin believed it owned the race while the game's own rules ran. Now a claim is NOT_IN_RACE until the next LOAD_DONE. */
void bo3_rules_mode_race(const td_host *owner) { s_mode_owner = owner; s_loaded = 0; }

int bo3_rules_census(void)
{
    static const uint8_t lap[15] = { 0x8B, 0x0C, 0x85, 0xA8, 0xA1, 0x73, 0x00, 0x51, 0x8B, 0xC5, 0xE8, 0x6F, 0x00, 0x00, 0x00 };
    static const uint8_t elim[11] = { 0x53, 0x55, 0x8B, 0x6C, 0x24, 0x0C, 0x56, 0x57, 0x8B, 0x78, 0x4C };
    uint8_t a[15], b[11];
    if (s_census < 0)
        s_census = bo3_guest_read(0x00024E92u, a, 15) && !memcmp(a, lap, 15) && bo3_guest_read(0x00024F10u, b, 11) &&
                   !memcmp(b, elim, 11) && rd32(BO3_RULES_VT_ELIM + 0x68u) == 0x00024E30u;
    return s_census;
}

static int avail(void)
{
    return BO3_HOOKREQ_P23 && BM_P23_RULES_AVAILABLE && bo3_rules_census();
}

static uint32_t logic_now(void)
{
    uint32_t m = rd32(BO3_RULES_MODULE);
    return m ? rd32(m + BO3_RULES_LOGIC) : 0;
}

static int elim_race(uint32_t logic)
{
#if MUT == 3
    return logic != 0;
#else
#if MUT == 11
    return logic && rd32(logic) == BO3_RULES_VT_ELIM;
#else
    return logic == BO3_RULES_ELIM_LOGIC && rd32(logic) == BO3_RULES_VT_ELIM;
#endif
#endif
}

static uint32_t racer(uint32_t i)
{
    uint32_t n = rd32(BO3_RULES_RACERS);
    return i < n && i < 8u ? rd32(BO3_RULES_LIST + 4u * i) : 0;
}

/* main21 C3-5 (2-player Multiplayer mode rows): every human racer is protected, not only player 0's 0x73A1D0. In the 2-player
 * stage (the current module [0x4D5370] = 0x4D4798, the only stage a Multiplayer row's route runs in; sub_0005F7B0 sets 2 humans)
 * player 2's race object 0x73C640 (= 0x73A1D0 + 0x2470: the humans come first, HYPOTHESIS until the probe) and any racer whose
 * control word R + 0x134C is 2 (the Eliminator results' "human" test, HYPOTHESIS) are humans too - fail closed: a racer that
 * matches either is never eliminated by a plugin. The 1-player stage: only 0x73A1D0, as before.
 * MUT (tests): 60 player 2 eliminable by eliminate()  61 end_race eliminates player 2 */
static int human(uint32_t r)
{
    if (r == BO3_RULES_CAR1)
        return 1;
    if (rd32(BO3_RULES_MODULE) != BO3_RULES_MP_STAGE)
        return 0;
    return r == BO3_RULES_CAR2 || rd32(r + BO3_RULES_R_CTRL) == 2u;
}

static int out_already(uint32_t r)
{
#if MUT == 12
    return rd16(r + BO3_RULES_R_ORDER) != 0 || rd32(r + BO3_RULES_R_ALIVE) == 0;
#else
    return rd16(r + BO3_RULES_R_ORDER) != BO3_RULES_NOT_OUT || rd32(r + BO3_RULES_R_ALIVE) == 0;
#endif
}

static uint32_t alive_count(void)
{
    uint32_t n = 0;
    for (uint32_t i = 0; i < 8u; i++) {
        uint32_t r = racer(i);
        if (r && rd8(r + BO3_RULES_R_RACING) && !out_already(r))
            n++;
    }
    return n;
}

/* the lap mark (generated code, game thread) */
int bo3_rules_gen_lap_skip(uint32_t rules, uint32_t last)
{
    t_game = 1;
    if (!avail() || !s_owner || rules != logic_now() || !elim_race(rules))
        return 0;                                   /* nobody owns this race: the game's own rule, unchanged */
#if MUT == 4
    return 1;
#else
#if MUT == 10
    (void)last;
    return !s_lap_on;
#else
    return !s_lap_on || (last && out_already(last));   /* never the game's re-elimination of a racer already out */
#endif
#endif
}

static int32_t owner_check(td_host *host)
{
    if (!host)
        return BM_RULES_BAD_ARG;
    if (!avail())
        return BM_RULES_UNAVAILABLE;
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
    if (s_owner != host)
        return s_owner ? BM_RULES_CONFLICT : BM_RULES_NOT_OWNER;
    return BM_RULES_OK;
}

static int32_t TD_CALL r_claim(td_host *host)
{
    uint32_t logic;
    if (!host)
        return BM_RULES_BAD_ARG;
    if (!avail())
        return BM_RULES_UNAVAILABLE;
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
    logic = logic_now();
#if MUT == 13
    if (!logic || !rd32(BO3_RULES_RACERS))
#else
    if (!logic || !rd32(BO3_RULES_RACERS) || (s_mode_owner && !s_loaded))
#endif
        return BM_RULES_NOT_IN_RACE;            /* patch 53: also before the routed race's load is done */
    if (!elim_race(logic) || !s_mode_owner)
        return BM_RULES_WRONG_MODE;             /* not an Eliminator race a bmashup.menu row started (World Tour: never) */
#if MUT != 6
    if (s_mode_owner != host || (s_owner && s_owner != host))
        return BM_RULES_CONFLICT;
#endif
    s_owner = host;
    return BM_RULES_OK;
}

static int32_t TD_CALL r_lap(td_host *host, uint32_t on)
{
    int32_t r = owner_check(host);
    if (r)
        return r;
    if (on > 1u)
        return BM_RULES_BAD_ARG;
    s_lap_on = (int)on;
    return BM_RULES_OK;
}

static int32_t TD_CALL r_eliminate(td_host *host, uint32_t i)
{
    int32_t rc = owner_check(host);
    uint32_t r;
    if (rc)
        return rc;
    r = racer(i);
    if (!r || !rd8(r + BO3_RULES_R_RACING))
        return BM_RULES_NO_RACER;
#if MUT != 1
#if MUT == 60
    if (r == BO3_RULES_CAR1)
#else
    if (human(r))                               /* main21 C3-5: both humans of a 2-player race */
#endif
        return BM_RULES_LAST_PLAYER;            /* a human is never eliminated by a plugin */
#endif
#if MUT != 5
    if (out_already(r))
        return BM_RULES_ALREADY;
    for (uint32_t k = 0; k < s_nq; k++)
        if (s_queue[k] == r)
            return BM_RULES_ALREADY;
#endif
#if MUT != 2
    if (s_tick - s_last_req < SECOND)
        return BM_RULES_RATE;
#endif
    if (s_nq >= QMAX)
        return BM_RULES_RATE;
    s_queue[s_nq++] = r;
    s_last_req = s_tick;
    return BM_RULES_OK;
}

static int32_t TD_CALL r_end(td_host *host, uint32_t reason)
{
    int32_t r = owner_check(host);
    if (r)
        return r;
    if (reason < BM_RULES_END_TIME || reason > BM_RULES_END_OTHER)
        return BM_RULES_BAD_ARG;
    s_ending = 1;
    return BM_RULES_OK;
}

/* patch 80: the prop site (default.xbe 9f497acd)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[28]; } s_props_rows[] = {
    { 0x001108D8u, 28, { 0x8b,0x15,0x70,0x53,0x4d,0x00,0x8b,0x8a,0xb8,0x01,0x00,0x00,0x8b,0x01,0xff,0x90,0xb0,0x00,0x00,0x00,0x84,
                         0xc0,0x0f,0x85,0xa9,0x01,0x00,0x00 } },   /* mode logic -> vtable + 0xB0; jnz over the prop bodies */
#if MUT != 29
    /* main21 patch 102: the prop draw sub_001ACE00 asks the same question (the mode object [0x4D5370] + 0x1B8: NULL -> draw;
     * otherwise its virtual + 0xB0 decides; a non-zero answer jumps to 0x1AD03C = skip the draw) */
    { 0x001ACE09u, 11, { 0xa1,0x70,0x53,0x4d,0x00,0x8b,0x88,0xb8,0x01,0x00,0x00 } },
    { 0x001ACE1Eu, 24, { 0x3b,0xce,0x89,0x5c,0x24,0x1c,0x74,0x10,0x8b,0x11,0xff,0x92,0xb0,0x00,0x00,0x00,0x84,0xc0,0x0f,0x85,
                         0x06,0x02,0x00,0x00 } },
#endif
};
/* END-CENSUS */
static int props_census(void)
{
#if MUT == 21
    return 1;
#endif
    if (s_props_ok != 1) {
        s_props_ok = 1;
        for (size_t k = 0; k < sizeof s_props_rows / sizeof s_props_rows[0]; k++) {
            uint8_t x[28];
            if (!bo3_guest_read(s_props_rows[k].va, x, s_props_rows[k].n) || memcmp(x, s_props_rows[k].b, s_props_rows[k].n))
                s_props_ok = 0;
        }
    }
    return s_props_ok;
}

/* patch 80 mark (generated code, sub_00110420 loc_001108EC): rr = the mode logic's answer (AL); answers the value to test */
static uint32_t s_dp_calls, s_dp_rr, s_dp_lines;   /* main21 patch 86 (diagnostics): the props mark per load */

uint32_t bo3_rules_gen_props(uint32_t rr)
{
    s_dp_calls++;
    s_dp_rr += (rr & 0xFFu) != 0;
    if (s_dp_lines < 6u) {
        s_dp_lines++;
        fprintf(stderr, "[DIAG] props mark: mode answer %02x, switch %s, census %d\n", (unsigned)(rr & 0xFFu),
                s_props_owner ? "ON" : "off", props_census());
    }
#if MUT == 23
    if (s_props_owner)
        return 1;
#endif
    if (!(rr & 0xFFu) || !BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P10R || !s_props_owner || props_census() != 1)
        return rr;
    s_props_used++;
    return rr & ~0xFFu;                                  /* "not Road Rage" for the prop bodies only */
}

uint32_t bo3_rules_props_used(void) { return s_props_used; }

/* patch 102 mark (generated code, sub_001ACE00 loc_001ACE2E, every drawn frame): the same answer at the prop draw. No log per
 * call; counted per load and summed up at the load end / race exit */
static uint32_t s_pd_calls, s_pd_rr, s_pd_drawn;

uint32_t bo3_rules_gen_props_draw(uint32_t rr)
{
    s_pd_calls++;
    s_pd_rr += (rr & 0xFFu) != 0;
#if MUT == 27
    if (rr & 0xFFu)
        return rr & ~0xFFu;                              /* defect: drawn without the switch */
#endif
#if MUT == 28
    return rr;                                           /* defect: the draw gate not answered */
#endif
    if (!(rr & 0xFFu) || !BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P10R || !s_props_owner || props_census() != 1)
        return rr;
    s_pd_drawn++;
    return rr & ~0xFFu;                                  /* "not Road Rage" for the prop draw only */
}

uint32_t bo3_rules_props_drawn(void) { return s_pd_drawn; }

static void props_draw_summary(const char *when)
{
    if (s_pd_calls)
        fprintf(stderr, "[DIAG] props draw summary (%s): draw gate calls %u (Road Rage answer %u), drawn by the switch %u, "
                "switch %s\n", when, (unsigned)s_pd_calls, (unsigned)s_pd_rr, (unsigned)s_pd_drawn, s_props_owner ? "ON" : "off");
    s_pd_calls = s_pd_rr = s_pd_drawn = 0;
}

static int32_t TD_CALL r_props(td_host *host, uint32_t on)
{
    if (!host || on > 1u)
        return BM_RULES_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P10R || props_census() != 1)
        return BM_RULES_UNAVAILABLE;
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
#if MUT != 22
    if (s_props_owner && s_props_owner != host)
        return BM_RULES_CONFLICT;
#endif
    s_props_owner = on ? host : NULL;
    return BM_RULES_OK;
}

/* patch 83: the pause-menu sites (default.xbe 9f497acd)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_es_rows[] = {
    { 0x00086186u, 24, { 0x8b,0x80,0xb8,0x01,0x00,0x00,0x8b,0x10,0x8b,0xc8,0xff,0x92,0xd4,0x00,0x00,0x00,0x84,0xc0,0x74,0x2d,0xc6,
                         0x43,0x61,0x01 } },   /* mode logic -> vtable + 0xD4; je QUIT / CRASH NAV; + 0x61 = 1 */
    { 0x000861C7u, 21, { 0xa1,0x70,0x53,0x4d,0x00,0x85,0xc0,0x74,0x1c,0x81,0xb8,0xbc,0x01,0x00,0x00,0x10,0x52,0x4d,0x00,0x75,
                         0x10 } },             /* the CRASH NAV test: game object + 0x1BC == 0x4D5210 */
    { 0x000865B4u, 7,  { 0x8a,0x46,0x61,0x84,0xc0,0x74,0x66 } },                        /* the input handler reads + 0x61 */
};
/* END-CENSUS */
static int es_census(void)
{
#if MUT == 24
    return 1;
#endif
    if (s_es_ok != 1) {
        s_es_ok = 1;
        for (size_t k = 0; k < sizeof s_es_rows / sizeof s_es_rows[0]; k++) {
            uint8_t x[24];
            if (!bo3_guest_read(s_es_rows[k].va, x, s_es_rows[k].n) || memcmp(x, s_es_rows[k].b, s_es_rows[k].n))
                s_es_ok = 0;
        }
    }
    return s_es_ok;
}

/* patch 83 mark (generated code, sub_00085F70 loc_00086196): r = the mode logic's + 0xD4 answer (AL) */
uint32_t bo3_rules_gen_end_session(uint32_t r)
{
    uint32_t game;
    if ((r & 0xFFu) || !BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P11E || !s_es_owner || es_census() != 1)
        return r;
#if MUT != 26
    game = rd32(0x004D5370u);
    if (game && rd32(game + 0x1BCu) == 0x004D5210u)
        return r;                                        /* Crash mode: the game's CRASH NAV stays */
#else
    (void)game;
#endif
    s_es_used++;
    return (r & ~0xFFu) | 1u;
}

uint32_t bo3_rules_end_session_used(void) { return s_es_used; }

static int32_t TD_CALL r_end_session(td_host *host, uint32_t on)
{
    if (!host || on > 1u)
        return BM_RULES_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P11E || es_census() != 1)
        return BM_RULES_UNAVAILABLE;
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
#if MUT != 25
    if (s_es_owner && s_es_owner != host)
        return BM_RULES_CONFLICT;
#endif
    s_es_owner = on ? host : NULL;
    return BM_RULES_OK;
}

/* main21 patch 105 (hook request "zackypoo" 03): Crash Breaker in every mode (default.xbe 9f497acd)
 * arm   sub_001935F0 0x1940F6..0x194196: the inlined Crash-mode test (vt + 0x90 == 6, vt + 0x94 in 3 / 4 / 5), the count
 *       sub_0017E030, + 0x3CB (once a race), the car not wrecked-out [car + 0x1920] and crashed [car + 0x18FA], the physics
 *       vehicle by [car + 0x27D0] < [0x731F90] (humans), sub_00119C90 = ARM (V + 0x4AC6 = 1), + 0x3CB = 1.
 * fire  sub_00118410 0x1188EB..0x118943: armed V + 0x4AC6, [esp + 0x1E] = sub_00017310 (Crash mode), pad bit [V + 0x13FC] & 1,
 *       V vt + 0x20(0) = the blast, message 1 to 0x739C60, disarm.
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[32]; } s_cb_rows[] = {
    { 0x001940F6u, 32, { 0x8b,0x06,0x8b,0xce,0xff,0x90,0x90,0x00,0x00,0x00,0x83,0xf8,0x06,0x74,0x31,0x8b,0x16,0x8b,0xce,0xff,0x92,
                         0x94,0x00,0x00,0x00,0x83,0xf8,0x03,0x74,0x22,0x8b,0x06 } },
    { 0x00194116u, 32, { 0x8b,0xce,0xff,0x90,0x94,0x00,0x00,0x00,0x83,0xf8,0x04,0x74,0x13,0x8b,0x16,0x8b,0xce,0xff,0x92,0x94,0x00,
                         0x00,0x00,0x83,0xf8,0x05,0x0f,0x85,0x79,0x00,0x00,0x00 } },
    { 0x00194136u, 32, { 0x8b,0x87,0xc8,0x00,0x00,0x00,0x0f,0xbe,0xb0,0xbc,0x19,0x00,0x00,0x68,0x60,0x9c,0x73,0x00,0xe8,0xe3,0x9e,
                         0xfe,0xff,0x85,0xc0,0x7f,0x5e,0x8a,0x87,0xcb,0x03,0x00 } },
    { 0x00194156u, 32, { 0x00,0x84,0xc0,0x75,0x54,0x8b,0x87,0xc8,0x00,0x00,0x00,0x8b,0x88,0x20,0x19,0x00,0x00,0x85,0xc9,0x75,0x44,
                         0x8a,0x88,0xfa,0x18,0x00,0x00,0x84,0xc9,0x74,0x3a,0x8b } },
    { 0x00194176u, 32, { 0x80,0xd0,0x27,0x00,0x00,0x3b,0x05,0x90,0x1f,0x73,0x00,0x7d,0x1e,0x69,0xc0,0xd0,0x4a,0x00,0x00,0x05,0x90,
                         0x7e,0x66,0x00,0xe8,0xfd,0x5a,0xf8,0xff,0xc6,0x87,0xcb } },
    { 0x001188EBu, 32, { 0x8a,0x86,0xc6,0x4a,0x00,0x00,0x84,0xc0,0x74,0x4e,0x8a,0x44,0x24,0x1e,0x84,0xc0,0x74,0x46,0xf6,0x07,0x01,
                         0x74,0x41,0x8b,0x16,0x6a,0x00,0x8b,0xce,0xff,0x52,0x20 } },
    { 0x0011890Bu, 32, { 0xf3,0x0f,0x10,0x05,0x20,0xea,0x60,0x00,0x8b,0x86,0x80,0x15,0x00,0x00,0xf3,0x0f,0x11,0x86,0x74,0x3a,0x00,
                         0x00,0x0f,0xbe,0x80,0xbc,0x19,0x00,0x00,0x6a,0x01,0xb9 } },
    { 0x0011892Bu, 24, { 0x60,0x9c,0x73,0x00,0xe8,0xbc,0x53,0x06,0x00,0xf3,0x0f,0x10,0x2d,0x8c,0x16,0x3b,0x00,0xc6,0x86,0xc6,0x4a,
                         0x00,0x00,0x00 } },
    /* patch 117: sub_00120800 0x120865: the call of sub_00115130 with [ebp + 8], 0, ESI and 0x64B310 (ESI saved around it) */
    { 0x00120865u, 18, { 0x8b,0x4d,0x08,0x51,0x6a,0x00,0x56,0x68,0x10,0xb3,0x64,0x00,0xe8,0xba,0x48,0xff,0xff,0x5e } },
};
/* END-CENSUS */
#define CB_HUMANS     0x00731F90u     /* the number of player physics vehicles (the arm's own human test) */
#define CB_V_BASE     0x00667E90u     /* player physics vehicle 0 (stride 0x4AD0) */
#define CB_V_STRIDE   0x4AD0u
#define CB_V_ARMED    0x4AC6u
#define CB_V_PAD      0x13FCu
#define CB_S_ONCE     0x3CBu
#define CB_CAR_CRASH  0x18FAu
#define CB_POOL_COUNT 0x00731F9Cu     /* patch 117: M 0x64B310 + 0xE6C8C, the active wreck-pool count (sub_00115130 loop 2) */
static int cb_census(void)
{
#if MUT == 30
    return 1;
#endif
    if (s_cb_ok != 1) {
        s_cb_ok = 1;
        for (size_t k = 0; k < sizeof s_cb_rows / sizeof s_cb_rows[0]; k++) {
            uint8_t x[32];
            if (!bo3_guest_read(s_cb_rows[k].va, x, s_cb_rows[k].n) || memcmp(x, s_cb_rows[k].b, s_cb_rows[k].n))
                s_cb_ok = 0;
        }
    }
    return s_cb_ok;
}

static int cb_on(void)
{
    return BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZCB && s_cb_owner && cb_census() == 1;
}

/* patch 105 mark 1 (sub_001935F0 loc_0019412D, before the last mode compare): EAX = vt + 0x94's answer after vt + 0x90 != 6 and
 * vt + 0x94 not 3 / 4 = the game's "not Crash mode" exactly when EAX != 5; EDI = the racer's scoring object S. 1 = go on with the
 * Crash Breaker checks (loc_00194136) as in Crash mode: the count sub_0017E030 is 0 outside Crash mode, so a crashed human car
 * arms. Once a race (+ 0x3CB) becomes once a crash: + 0x3CB is cleared while the car is neither crashed nor armed. */
uint32_t bo3_rules_gen_cb_arm(uint32_t eax, uint32_t s)
{
    uint32_t car, idx;
    if (eax == 5u || !cb_on() || !s)
        return 0;
    car = rd32(s + 0xC8u);
    if (!car)
        return 0;
    idx = rd32(car + 0x27D0u);
#if MUT != 31
    if ((int32_t)idx < 0 || (int32_t)idx >= (int32_t)rd32(CB_HUMANS))
        return 0;                                        /* an AI racer: the game's own answer (no Crash Breaker) */
#endif
#if MUT != 32
    if (!rd8(car + CB_CAR_CRASH) && !rd8(CB_V_BASE + idx * CB_V_STRIDE + CB_V_ARMED) && rd8(s + CB_S_ONCE)) {
        uint8_t z = 0;
        bo3_guest_write(s + CB_S_ONCE, &z, 1);
        s_cb_rearm++;
    }
#endif
    s_cb_arm_calls++;
    return 1;
}

/* patch 105 mark 2 (sub_00118410 loc_001188F5, after the read of [esp + 0x1E]; only reached when V + 0x4AC6 = armed):
 * EAX's AL = the stored Crash-mode answer, ESI = V. AL = 1 outside Crash mode for a human player's vehicle while the switch is on
 * (the stored local itself is untouched: its other user 0x11886D keeps the game's answer). When the pad bit is set the blast
 * happens now: the AI racers within the radius are wrecked (bm_racers.c, aftertouch takedown credit). */
uint32_t bo3_rules_gen_cb_fire(uint32_t eax, uint32_t v)
{
    if ((eax & 0xFFu) || !cb_on())
        return eax;
#if MUT != 33
    if (v < CB_V_BASE || v >= CB_V_BASE + 2u * CB_V_STRIDE || (v - CB_V_BASE) % CB_V_STRIDE)
        return eax;                                      /* not a player physics vehicle */
#endif
#if MUT != 34
    if (rd8(v + CB_V_PAD) & 1u) {
#else
    {
#endif
        s_cb_blasts++;
        if (s_blast)
            s_cb_wrecks += s_blast(v, s_cb_radius);
        s_cb_pending = v;                                /* patch 117: the push follows at the blast routine's return */
        bo3_guest_read(CB_POOL_COUNT, &s_cb_pool0, 4);
        fprintf(stderr, "[RULES] Crash Breaker (all modes) blast by V %08x, radius %u m\n", (unsigned)v, (unsigned)s_cb_radius);
    }
    return (eax & ~0xFFu) | 1u;
}

void bo3_rules_set_blast(bo3_rules_blast_fn fn) { s_blast = fn; }

/* patch 117 mark (sub_00120800 loc_00120876): the game's blast routine sub_00115130 has run for V - it induced and pushed the
 * traffic within its radius and pushed the wreck pool (any mode; it has no mode test). The game never pushes the racers: for a
 * blast this switch started (s_cb_pending == V) the AI racers within the radius get the same outward push (bm_racers.c
 * bo3_racers_push). Logs the wreck-pool growth = the traffic the game's blast wrecked. */
void bo3_rules_gen_cb_pushed(uint32_t v)
{
    uint32_t pool1 = 0, n = 0;
    if (!cb_on() || !v)
        return;
#if MUT != 48
    if (s_cb_pending != v)
        return;                                          /* the game's own Crash-mode blast, or another vehicle's */
#endif
    s_cb_pending = 0;
    if (s_push)
        n = s_push(v, s_cb_radius);
    s_cb_pushed += n;
    bo3_guest_read(CB_POOL_COUNT, &pool1, 4);
    if (pool1 > s_cb_pool0 && pool1 - s_cb_pool0 < 256u)
        s_cb_traffic += pool1 - s_cb_pool0;
    fprintf(stderr, "[RULES] Crash Breaker push by V %08x: %u AI racer(s) pushed, wreck pool %u -> %u (the game's blast)\n",
            (unsigned)v, (unsigned)n, (unsigned)s_cb_pool0, (unsigned)pool1);
}

void bo3_rules_set_push(bo3_rules_blast_fn fn) { s_push = fn; }
uint32_t bo3_rules_cb_pushed(void) { return s_cb_pushed; }
uint32_t bo3_rules_cb_blasts(void) { return s_cb_blasts; }
uint32_t bo3_rules_cb_rearms(void) { return s_cb_rearm; }

static int32_t TD_CALL r_crash_breaker(td_host *host, uint32_t on, uint32_t radius_m)
{
    if (!host || on > 1u || (on && radius_m && (radius_m < BM_RULES_CB_RADIUS_MIN || radius_m > BM_RULES_CB_RADIUS_MAX)))
        return BM_RULES_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZCB || cb_census() != 1)
        return BM_RULES_UNAVAILABLE;
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
#if MUT != 35
    if (s_cb_owner && s_cb_owner != host)
        return BM_RULES_CONFLICT;
#endif
    s_cb_owner = on ? host : NULL;
    s_cb_radius = on && radius_m ? radius_m : BM_RULES_CB_RADIUS_DEFAULT;
    return BM_RULES_OK;
}

/* main21 patch 106 (hook request "zackypoo" 09 / 10): rival count and rival cars at the race set-up apply sub_00017450
 * (ECX = ESI = the set-up object S): at 0x17464 it passes S + 0xA8 (humans), S + 0xAC (AI count), S + 0xB0 (network) to the racer
 * list builder sub_001AACB0, then copies the AI car ids S + 0x20 + k * 8 (looked up in the car table 0x39FC90, 67 ids) and one
 * byte S + 0x80 + k * 4 per AI racer. (default.xbe 9f497acd)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[32]; } s_rv_rows[] = {
    { 0x00017450u, 20, { 0x83,0xec,0x08,0x56,0x8b,0xf1,0x8a,0x86,0xc0,0x01,0x00,0x00,0x84,0xc0,0x0f,0x84,0xae,0x02,0x00,0x00 } },
    { 0x00017464u, 32, { 0x8b,0x86,0xa8,0x00,0x00,0x00,0x8b,0x8e,0xb0,0x00,0x00,0x00,0x8b,0x96,0xac,0x00,0x00,0x00,0x53,0x55,0x57,
                         0x50,0xb8,0x00,0xea,0x60,0x00,0xe8,0x2c,0x38,0x19,0x00 } },
    { 0x00017484u, 32, { 0x8b,0x86,0xa8,0x00,0x00,0x00,0x33,0xff,0x85,0xc0,0x0f,0x8e,0x81,0x00,0x00,0x00,0x8d,0x4e,0x78,0x89,0x4c,
                         0x24,0x10,0xb8,0x40,0xbb,0x73,0x00,0x8d,0x56,0x10,0x8b } },
};
/* END-CENSUS */
#define RV_HUMANS 0xA8u
#define RV_AI     0xACu
#define RV_NET    0xB0u
#define RV_HID    0x10u             /* + i * 8: human car ids */
#define RV_AID    0x20u             /* + k * 8: AI car ids */
#define RV_HB     0x78u             /* + i * 4: one byte per human */
#define RV_AB     0x80u             /* + k * 4: one byte per AI racer */
#define RV_TABLE  0x0039FC90u

static int rv_census(void)
{
#if MUT == 36
    return 1;
#endif
    if (s_rv_ok != 1) {
        s_rv_ok = 1;
        for (size_t k = 0; k < sizeof s_rv_rows / sizeof s_rv_rows[0]; k++) {
            uint8_t x[32];
            if (!bo3_guest_read(s_rv_rows[k].va, x, s_rv_rows[k].n) || memcmp(x, s_rv_rows[k].b, s_rv_rows[k].n))
                s_rv_ok = 0;
        }
    }
    return s_rv_ok;
}

static void rv_read(uint32_t s, rv_img *m)
{
    memset(m, 0, sizeof *m);
    m->ac = rd32(s + RV_AI);
    for (uint32_t k = 0; k < RV_SLOTS; k++) {
        bo3_guest_read(s + RV_AID + 8u * k, m->id[k], 8);
        m->b[k] = rd8(s + RV_AB + 4u * k);
    }
}

static void rv_write(uint32_t s, const rv_img *m)
{
    bo3_guest_wr32(s + RV_AI, m->ac);
    for (uint32_t k = 0; k < RV_SLOTS; k++) {
        bo3_guest_write(s + RV_AID + 8u * k, m->id[k], 8);
        bo3_guest_write(s + RV_AB + 4u * k, &m->b[k], 1);
    }
}

static int rv_active(void)
{
    if (!s_rv_owner)
        return 0;
    if (s_rv_count >= 0)
        return 1;
    for (uint32_t k = 0; k < RV_SLOTS; k++)
        if (s_rv_car[k] >= 0)
            return 1;
    return 0;
}

/* patch 106 mark (generated code, sub_00017450 loc_00017464, before the three reads): ESI = S. While a plugin's rival settings
 * are on, the AI count / car ids / bytes of an OFFLINE set-up are changed in S (humans + AI <= 6, AI <= 5; new slots copy the
 * last AI slot of the game's own set-up, or player 1's car when it had none; a chosen car index replaces a slot's id). The
 * game's own values are kept and written back at the next set-up after the switch is off (or for another set-up object); a
 * set-up the game rewrote meanwhile is taken as the new original. */
void bo3_rules_gen_rivals(uint32_t s)
{
    rv_img cur, img;
    uint32_t humans, net, n;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZRV || !s || rv_census() != 1)
        return;
    rv_read(s, &cur);
#if MUT != 39
    if (s_rv_saved && (s_rv_s != s || !rv_active())) {
        if (!memcmp(&cur, &s_rv_written, RV_CMP) || s_rv_s != s)
            rv_write(s_rv_s, &s_rv_orig);               /* the game's own set-up back */
        s_rv_saved = 0;
        fprintf(stderr, "[RULES] rivals: the game's own set-up written back (AI %u)\n", (unsigned)s_rv_orig.ac);
        if (s_rv_s == s)
            rv_read(s, &cur);
    }
#endif
    if (!rv_active())
        return;
    humans = rd32(s + RV_HUMANS);
    net = rd32(s + RV_NET);
#if MUT != 37
    if ((int32_t)net > 0 || humans < 1u || humans > 2u || cur.ac > RV_SLOTS) {
#else
    if (humans < 1u || humans > 2u || cur.ac > RV_SLOTS) {
#endif
        s_rv_skipped++;
        if (s_rv_lines++ < 8u)
            fprintf(stderr, "[RULES] rivals: set-up left unchanged (network %d, humans %u, AI %u)\n", (int)net, (unsigned)humans,
                    (unsigned)cur.ac);
        return;
    }
#if MUT != 42
    if (!s_rv_saved || s_rv_s != s || memcmp(&cur, &s_rv_written, RV_CMP)) {
#else
    if (!s_rv_saved || s_rv_s != s) {
#endif
        s_rv_orig = cur;                                /* the game's own set-up (new, or rewritten by the game) */
        s_rv_s = s;
        s_rv_saved = 1;
    }
    img = s_rv_orig;
    n = s_rv_count >= 0 ? (uint32_t)s_rv_count : s_rv_orig.ac;
#if MUT != 38
    if (n > 6u - humans)
        n = 6u - humans;
#endif
    if (n > RV_SLOTS)
        n = RV_SLOTS;
    for (uint32_t k = s_rv_orig.ac; k < n; k++) {
#if MUT != 40
        if (s_rv_orig.ac) {
            memcpy(img.id[k], s_rv_orig.id[s_rv_orig.ac - 1u], 8);
            img.b[k] = s_rv_orig.b[s_rv_orig.ac - 1u];
        } else {
            bo3_guest_read(s + RV_HID, img.id[k], 8);   /* no AI in the game's set-up: player 1's car */
            img.b[k] = rd8(s + RV_HB);
        }
#endif
    }
    for (uint32_t k = 0; k < n; k++)
        if (s_rv_car[k] >= 0)
            bo3_guest_read(RV_TABLE + 8u * (uint32_t)s_rv_car[k], img.id[k], 8);
    img.ac = n;
    rv_write(s, &img);
    s_rv_written = img;
    s_rv_applied = n;
    s_rv_sets++;
    if (s_rv_lines++ < 8u)
        fprintf(stderr, "[RULES] rivals: offline set-up, humans %u, AI %u -> %u (count %d, cars %d %d %d %d %d)\n", (unsigned)humans,
                (unsigned)s_rv_orig.ac, (unsigned)n, (int)s_rv_count, (int)s_rv_car[0], (int)s_rv_car[1], (int)s_rv_car[2],
                (int)s_rv_car[3], (int)s_rv_car[4]);
}

uint32_t bo3_rules_rivals_sets(void) { return s_rv_sets; }

static int32_t rv_take(td_host *host)
{
    if (!host)
        return BM_RULES_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZRV || rv_census() != 1)
        return BM_RULES_UNAVAILABLE;
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
#if MUT != 41
    if (s_rv_owner && s_rv_owner != host)
        return BM_RULES_CONFLICT;
#endif
    return BM_RULES_OK;
}

static int32_t TD_CALL r_rival_count(td_host *host, int32_t n)
{
    int32_t rc;
    if (n < -1 || n > (int32_t)BM_RULES_RIVALS_MAX)
        return BM_RULES_BAD_ARG;
    if ((rc = rv_take(host)) != BM_RULES_OK)
        return rc;
    s_rv_count = n;
    s_rv_owner = host;
    if (!rv_active())
        s_rv_owner = NULL;                              /* everything back to the game: given back */
    return BM_RULES_OK;
}

static int32_t TD_CALL r_rival_car(td_host *host, uint32_t slot, int32_t index)
{
    int32_t rc;
    if (slot >= RV_SLOTS || index < -1 || index >= (int32_t)BM_RULES_RIVAL_CARS)
        return BM_RULES_BAD_ARG;
    if ((rc = rv_take(host)) != BM_RULES_OK)
        return rc;
    s_rv_car[slot] = index;
    s_rv_owner = host;
    if (!rv_active())
        s_rv_owner = NULL;
    return BM_RULES_OK;
}

/* main21 patch 113 (hook request "zackypoo" 11): the radio DJ in a Single Event (default.xbe 9f497acd). The music manager
 * (0x4115E8) runs its DJ / intro sequence only when the front-end hub [0x463AF4] is 0 (World Tour); sub_00067B40 writes the hub:
 * 0 MFS_CRASHNAV, 1 MFS_1PMODESE (Single Event), 2 MFS_2PMODESE, 3 MFS_ONLICONN. The three hub tests answer 0 for hub 1 while on.
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[28]; } s_dj_rows[] = {
    { 0x0015481Fu, 9,  { 0xa1,0xf4,0x3a,0x46,0x00,0x85,0xc0,0x74,0x0a } },             /* sub_00154800: mov eax, [hub]; je open */
    { 0x00154585u, 13, { 0xa1,0xf4,0x3a,0x46,0x00,0x85,0xc0,0x0f,0x85,0x69,0xff,0xff,0xff } },   /* sub_001544C0: jne back */
    { 0x00154ABDu, 9,  { 0xa1,0xf4,0x3a,0x46,0x00,0x85,0xc0,0x74,0x1f } },             /* sub_00154A70: je the DJ path */
    { 0x00067BE8u, 27, { 0x68,0xad,0x3c,0x41,0x94,0x68,0x29,0x3f,0x35,0x86,0x33,0xff,0x68,0x70,0x71,0x56,0x00,0xc7,0x05,0xf4,
                         0x3a,0x46,0x00,0x01,0x00,0x00,0x00 } },   /* sub_00067B40 case 1: id MFS_1PMODESE, mov [hub], 1 */
};
/* END-CENSUS */
#ifndef BO3_HOOKREQ_ZDJ
#define BO3_HOOKREQ_ZDJ 1           /* unit tests: the CMake option is not there */
#endif
#define DJ_HUB_SINGLE 1u
static const td_host *s_dj_owner;
static int s_dj_ok = -1;
static uint32_t s_dj_calls, s_dj_opened, s_dj_lines;

static int dj_census(void)
{
#if MUT == 43
    return 1;
#endif
    if (s_dj_ok != 1) {
        s_dj_ok = 1;
        for (size_t k = 0; k < sizeof s_dj_rows / sizeof s_dj_rows[0]; k++) {
            uint8_t x[28];
            if (!bo3_guest_read(s_dj_rows[k].va, x, s_dj_rows[k].n) || memcmp(x, s_dj_rows[k].b, s_dj_rows[k].n))
                s_dj_ok = 0;
        }
    }
    return s_dj_ok;
}

/* patch 113 marks (generated code): hub = [0x463AF4] just read into EAX; the answer replaces EAX before the game's test */
uint32_t bo3_rules_gen_dj_hub(uint32_t hub)
{
    s_dj_calls++;
#if MUT == 44
    if (!hub || !BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZDJ || !s_dj_owner || dj_census() != 1)   /* 2P / online opened too */
#else
    if (hub != DJ_HUB_SINGLE || !BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZDJ || !s_dj_owner || dj_census() != 1)
#endif
        return hub;
    s_dj_opened++;
    if (s_dj_lines < 4u) {
        s_dj_lines++;
        fprintf(stderr, "[RULES] Single Event DJ: hub 1 answered as World Tour (opened %u)\n", (unsigned)s_dj_opened);
    }
#if MUT == 45
    return hub;
#else
    return 0u;
#endif
}

uint32_t bo3_rules_dj_opened(void) { return s_dj_opened; }

static int32_t TD_CALL r_single_event_dj(td_host *host, uint32_t on)
{
    if (!host || on > 1u)
        return BM_RULES_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZDJ || dj_census() != 1)
        return BM_RULES_UNAVAILABLE;
#if MUT != 46
    if (!t_game)
        return BM_RULES_WRONG_THREAD;
#endif
#if MUT != 47
    if (s_dj_owner && s_dj_owner != host)
        return BM_RULES_CONFLICT;
#endif
    s_dj_owner = on ? host : NULL;
    return BM_RULES_OK;
}

static int32_t TD_CALL r_status(td_host *host, bm_rules_status *out)
{
    bm_rules_status s;
    uint32_t room;
    if (!host || !out || out->struct_size < 8u)
        return BM_RULES_BAD_ARG;
    if (!BO3_HOOKREQ_P23)
        return BM_RULES_UNAVAILABLE;
    memset(&s, 0, sizeof s);
    s.eliminator_race = (uint32_t)elim_race(logic_now());
    s.owned = s_owner != NULL;
    s.yours = s_owner == host;
    s.racing = alive_count();
    s.eliminated = s_eliminated;
    s.lap_elimination = (uint32_t)s_lap_on;
    s.ending = (uint32_t)s_ending;
    s.road_rage_props = s_props_owner != NULL;
    s.end_session = s_es_owner != NULL;
    s.crash_breaker_all = s_cb_owner != NULL;   /* patch 105 */
    s.crash_breaker_radius = s_cb_radius;
    s.rival_count = (uint32_t)s_rv_count;       /* patch 106 */
    s.rivals_applied = s_rv_applied;
    s.single_event_dj = s_dj_owner != NULL;     /* patch 113 */
    s.dj_hub_opened = s_dj_opened;
    room =out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    s.struct_size = room;
    memcpy(out, &s, room);
    return BM_RULES_OK;
}

static const bm_rules_api s_api = { (uint32_t)sizeof(bm_rules_api), BM_RULES_VERSION, r_claim, r_lap, r_eliminate, r_end,
                                    r_status, r_props, r_end_session, r_crash_breaker, r_rival_count, r_rival_car,
                                    r_single_event_dj };

const bm_rules_api *bo3_bm_rules_api(void) { return &s_api; }

static void do_elim(uint32_t logic, uint32_t r)
{
#if MUT == 60 || MUT == 61
    if (!s_elim || out_already(r) || r == BO3_RULES_CAR1)
#else
    if (!s_elim || out_already(r) || human(r))
#endif
        return;
    s_elim(logic, r);
    s_eliminated++;
    s_last_exec = s_tick;
}

void bo3_rules_tick(void *user)
{
    uint32_t logic;
    (void)user;
    t_game = 1;
    s_tick++;
    if (!s_owner || !avail())
        return;
    logic = logic_now();
    if (!elim_race(logic)) {                    /* the race went away under us: nothing more is done */
        s_nq = 0;
        s_ending = 0;
        return;
    }
#if MUT != 7
    if (s_tick - s_last_exec < SECOND)
        return;
#endif
    if (s_nq) {
        uint32_t r = s_queue[0];
        memmove(s_queue, s_queue + 1, (s_nq - 1u) * sizeof s_queue[0]);
        s_nq--;
        do_elim(logic, r);
        return;
    }
    if (s_ending) {
        uint32_t best = 0;
        int32_t lo = 0x7FFFFFFF;
#if MUT == 8
        if (alive_count() < 1u) {
#else
        if (alive_count() <= 1u) {
#endif
            s_ending = 0;
            return;
        }
        for (uint32_t i = 0; i < 8u; i++) {
            uint32_t r = racer(i);
            int32_t p;
#if MUT == 61
            if (!r || r == BO3_RULES_CAR1 || !rd8(r + BO3_RULES_R_RACING) || out_already(r))
#else
            if (!r || human(r) || !rd8(r + BO3_RULES_R_RACING) || out_already(r))
#endif
                continue;
            p = (int32_t)rd32(r + BO3_RULES_R_PROG);
            if (p < lo) {
                lo = p;
                best = r;
            }
        }
        if (best)
            do_elim(logic, best);
        else
            s_ending = 0;                       /* only humans are left: the game ends it */
    }
}

void bo3_rules_lifecycle(uint32_t kind)
{
    t_game = 1;
    if (kind == BO3_LC_EV_LOAD_DONE) {                   /* main21 patch 86 (diagnostics) */
        fprintf(stderr, "[DIAG] props summary (load): mark calls %u (Road Rage answer %u), skipped by the switch %u, switch %s\n",
                (unsigned)s_dp_calls, (unsigned)s_dp_rr, (unsigned)s_props_used, s_props_owner ? "ON" : "off");
        s_dp_calls = s_dp_rr = s_dp_lines = 0;
    }
    if (kind == BO3_LC_EV_LOAD_DONE || kind == BO3_LC_EV_RACE_EXIT)   /* patch 102 */
        props_draw_summary(kind == BO3_LC_EV_LOAD_DONE ? "load" : "race exit");
    if ((kind == BO3_LC_EV_LOAD_DONE || kind == BO3_LC_EV_RACE_EXIT) && (s_cb_arm_calls || s_cb_blasts)) {   /* patch 105 */
        fprintf(stderr, "[DIAG] Crash Breaker summary (%s): arm checks %u, once-a-crash clears %u, blasts %u, AI wrecks queued %u, "
                "AI racers pushed %u, traffic wrecked by the blast %u, switch %s\n", kind == BO3_LC_EV_LOAD_DONE ? "load" : "race exit",
                (unsigned)s_cb_arm_calls, (unsigned)s_cb_rearm, (unsigned)s_cb_blasts, (unsigned)s_cb_wrecks, (unsigned)s_cb_pushed,
                (unsigned)s_cb_traffic, s_cb_owner ? "ON" : "off");
        s_cb_arm_calls = s_cb_wrecks = s_cb_pushed = s_cb_traffic = 0;
    }
    if (kind == BO3_LC_EV_LOAD_DONE && (s_rv_sets || s_rv_skipped)) {   /* patch 106 */
        fprintf(stderr, "[DIAG] rivals summary (load): set-ups changed %u, left unchanged %u, last AI count %d, owner %s\n",
                (unsigned)s_rv_sets, (unsigned)s_rv_skipped, (int)s_rv_applied, s_rv_owner ? "yes" : "none");
        s_rv_lines = 0;
    }
    if (kind == BO3_LC_EV_RACE_EXIT && s_dj_calls)   /* patch 113: the hub tests run after the load (stage start, stage) */
        fprintf(stderr, "[DIAG] Single Event DJ summary (race exit): hub tests %u, answered as World Tour %u, switch %s\n",
                (unsigned)s_dj_calls, (unsigned)s_dj_opened, s_dj_owner ? "ON" : "off");
    if (kind == BO3_LC_EV_LOAD_DONE)
        s_dj_calls = s_dj_opened = s_dj_lines = 0;
    if (kind == BO3_LC_EV_LOAD_DONE || kind == BO3_LC_EV_RACE_EXIT) {
        s_loaded = kind == BO3_LC_EV_LOAD_DONE;      /* patch 53 */
        s_owner = NULL;
        s_lap_on = 1;
        s_ending = 0;
        s_nq = 0;
        s_eliminated = 0;
        if (kind == BO3_LC_EV_RACE_EXIT)
            s_mode_owner = NULL;
    }
}

void bo3_rules_reset(void)
{
    s_owner = s_mode_owner = NULL;
    s_loaded = 0;
    s_lap_on = 1;
    s_ending = 0;
    s_nq = 0;
    s_tick = 0;
    s_last_req = s_last_exec = 0xFFFF0000u;
    s_eliminated = 0;
    s_census = -1;
    s_props_owner = NULL;
    s_props_ok = -1;
    s_props_used = 0;
    s_pd_calls = s_pd_rr = s_pd_drawn = 0;   /* patch 102 */
    s_es_owner = NULL;
    s_es_ok = -1;
    s_es_used = 0;
    s_cb_owner = NULL;                          /* patch 105 */
    s_cb_ok = -1;
    s_cb_radius = BM_RULES_CB_RADIUS_DEFAULT;
    s_cb_arm_calls = s_cb_rearm = s_cb_blasts = s_cb_wrecks = 0;
    s_cb_pending = s_cb_pool0 = s_cb_pushed = s_cb_traffic = 0;   /* patch 117 */
    s_rv_owner = NULL;                          /* patch 106 */
    s_rv_ok = -1;
    s_rv_saved = 0;
    s_rv_count = -1;
    for (uint32_t k = 0; k < RV_SLOTS; k++)
        s_rv_car[k] = -1;
    s_rv_s = s_rv_sets = s_rv_skipped = s_rv_lines = 0;
    s_rv_applied = 0xFFFFFFFFu;
    s_dj_owner = NULL;                          /* patch 113 */
    s_dj_ok = -1;
    s_dj_calls = s_dj_opened = s_dj_lines = 0;
    t_game = 0;
}

#ifdef BO3_RULES_GAME
extern void sub_00024F10(void);
extern uint32_t bo3_racers_blast(uint32_t v, uint32_t radius_m);   /* bm_racers.c, patch 105 */
extern uint32_t bo3_racers_push(uint32_t v, uint32_t radius_m);    /* bm_racers.c, patch 117 */

/* the game's eliminate with the retail shape of 0x24E92..0x24E9C; every guest register put back (bm_boost.c's pattern) */
static void game_elim(uint32_t rules, uint32_t r)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;
    g_eax = rules;
    PUSH32(g_esp, r);
    PUSH32(g_esp, 0);                           /* the return address its ret 4 takes */
    sub_00024F10();
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp;
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
}
#endif

void bo3_bm_rules_init(void)
{
#ifdef BO3_RULES_GAME
    s_elim = game_elim;
    s_blast = bo3_racers_blast;                 /* patch 105 */
    s_push = bo3_racers_push;                   /* patch 117 */
#endif
#if BO3_HOOKREQ_P23
    {
        int mark = bo3_events_hook("ap_update");
        if (mark < 0 || bo3_events_subscribe(mark, BO3_EVENT_WRITER, bo3_rules_tick, NULL, "bmashup.rules") != 0)
            fprintf(stderr, "[RULES] bmashup.rules: the car-update mark is not available: eliminate / end_race never run\n");
    }
#endif
    bo3_plugins_service(BM_RULES_SERVICE, BM_RULES_VERSION, &s_api);
}
