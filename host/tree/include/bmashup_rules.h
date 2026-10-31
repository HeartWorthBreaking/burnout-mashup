/*
 * bmashup_rules.h - the "bmashup.rules" service (platform 0.1.9, hook request P3 item E1): final draft
 * gp\hookreq\p23\drafts_p23\bmashup_rules.h. Platform 0.1.9 status: the host side is validated by probe PR-E (the game's
 * Eliminator logic run from a routed Single Event row, host eliminations, the lap switch, the end by eliminations), but a race
 * can be claimed only when a bmashup.menu ELIMINATOR row started it (main19 patch 43 offers those rows in the Single Event SELECT
 * MODE list); any other race answers WRONG_MODE.
 * Justification (R0): no existing service changes the course of a race; elimination removes a racer from the race and changes its
 * result - a race-level owner (one per race) that must not be split over racers / events.
 *
 * bmashup_rules.h - Burnout Mashup's private, experimental race rules, ONLY in a race whose logic is the game's own Eliminator
 * (a race started from a bmashup.menu ELIMINATOR mode row; World Tour is never touched).
 *   claim_race(): the plugin that declared the mode row the race came from owns its rules (others: CONFLICT); from LOAD_DONE
 *     until RACE_EXIT (before the race's load is done: NOT_IN_RACE - try again at a later update; a restart's LOAD_DONE releases
 *     the claim: check status().yours and claim again). Without a claim the game's own per-lap elimination runs unchanged.
 *   set_lap_elimination(on): 1 = the game's own "last racer at each lap is out" (default); 0 = the plugin decides (the host
 *     skips the game's per-lap call for this race only).
 *   eliminate(racer): the game's own elimination (order, explosion, sign, scoreboard, results), at the race update; never the
 *     last human player in a one-player race (LAST_PLAYER); never an eliminated racer (ALREADY); <= 1 a second.
 *   end_race(reason): ends the race through the game's own path: the remaining racers behind the leader are eliminated one a
 *     second until the game's own last-standing end fires (results in the game's order). No direct state write.
 *   The race's results and records are the game's; nothing is saved by the host. CHANGES GAMEPLAY (label).
 *
 * Version 2 (main21 patch 80, hook request "zackypoo" 06; append-only, every v1 rule unchanged):
 *   set_road_rage_props(on): 1 = Road Rage races keep the track's props (crates, barrels, barriers ...): the game leaves them out
 *     of the physics world when the race's mode logic is a Road Rage one; with this switch the host answers "not Road Rage" at
 *     that ONE check (the prop bodies are built as in a race). Every other Road Rage rule stays. No race claim needed: one owner
 *     (another plugin: CONFLICT while it is on); 0 gives it back. It holds from the next physics update until set off, across
 *     races (World Tour Road Rage too). Game thread. UNAVAILABLE on a host built with BO3_HOOKREQ_P10R=OFF or whose site
 *     differs. status().road_rage_props = 1 while on. CHANGES GAMEPLAY (props give boost / score, block the road).
 *     main21 patch 102: the game asks the same question a second time when it DRAWS the props (sub_001ACE00); the switch answers
 *     "not Road Rage" there too, so the props are seen as well as hit (S8b: built and hit but invisible). Both sites must match.
 *
 * Version 3 (main21 patch 83, hook request "zackypoo" 02; append-only):
 *   set_end_session(on): 1 = the race pause menu's last item is the game's own END SESSION (its label, its confirmation, its
 *     action) where the game would offer QUIT. The pause menu build (sub_00085F70) asks the race's mode logic (vtable + 0xD4)
 *     and offers END SESSION on 1, CRASH NAV in Crash mode, else QUIT; the host answers 1 at that one check while the switch
 *     is on, except where the game would show CRASH NAV (kept). One owner (CONFLICT), no race claim, holds until off; game
 *     thread. UNAVAILABLE on a host built with BO3_HOOKREQ_P11E=OFF or whose site differs. What END SESSION then does in a mode
 *     that never offered it (Single Event, Road Rage ...) is the game's own path: probe R24. status().end_session.
 *
 * Version 4 (main21 patch 105, hook request "zackypoo" 03; append-only):
 *   set_crash_breaker_all(on, radius_m): 1 = the game's own Crash Breaker in every mode (Race, Road Rage, Eliminator, ...), for
 *     human players: a crashed player's car is armed as in Crash mode (once a crash, not once a race) and the Crash Breaker
 *     button sets off the game's own blast; every AI racer within radius_m (0 = BM_RULES_CB_RADIUS_DEFAULT, else
 *     BM_RULES_CB_RADIUS_MIN..MAX) of the player's car is wrecked through the game's crash decider and credited to the player
 *     as an aftertouch takedown (the game's own confirm: banner, boost, Road Rage tally). Crash mode itself is unchanged (the
 *     host answers only where the game says "not Crash mode"). Traffic is touched only by the game's own blast physics. No
 *     Crash Breaker HUD icon outside the Crash HUD modes (its art is not loaded there). One owner (CONFLICT), no race claim,
 *     holds until off; game thread. UNAVAILABLE on a host built with BO3_HOOKREQ_ZCB=OFF or whose arm / blast sites differ
 *     (the AI wrecks also need bmashup.racers wreck support). status().crash_breaker_all. CHANGES GAMEPLAY.
 *
 * Version 5 (main21 patch 106, hook request "zackypoo" 09 / 10; append-only):
 *   set_rival_count(count): -1 = the game's own number of AI rivals (default), 0..BM_RULES_RIVALS_MAX = that many AI rivals in
 *     every OFFLINE race set up while it is set (humans + AI <= 6; network races are never changed). New rival slots get the car
 *     of the set-up's last rival (player 1's car when it had none). The plugin sets it before the race starts (menu / mode row)
 *     and gives it back with -1; the game's own set-up is written back at the next set-up.
 *   set_rival_car(slot 0..4, car_index): the car (index 0..66 into the game's car table) of AI rival slot `slot`, -1 = the
 *     game's choice. No garage menu (a plugin chooses).
 *   One owner for both (CONFLICT); given back when the count is -1 and every slot is -1. Game thread. UNAVAILABLE on a host
 *   built with BO3_HOOKREQ_ZRV=OFF or whose set-up site differs. status().rival_count / rivals_applied. Probe items: 0 rivals in
 *   Road Rage, 5 rivals on a 4-rival grid, the chosen car's assets (load follows the set-up: HYPOTHESIS). CHANGES GAMEPLAY.
 *
 * Version 6 (main21 patch 113, hook request "zackypoo" 11; append-only):
 *   set_single_event_dj(on): the game plays its radio DJ (the music manager's intro / speech sequence) only in events entered
 *     from World Tour; in a Single Event (entered from the 1P mode select) it skips it. With this on, the music manager treats a
 *     Single Event as World Tour at its three hub tests (the stage start, the stage, the track change); every other use of the
 *     hub, 2-player and online events are unchanged. One owner (CONFLICT), holds until off; game thread. UNAVAILABLE on a host
 *     built with BO3_HOOKREQ_ZDJ=OFF or whose music-manager / hub sites differ. status().single_event_dj / dj_hub_opened.
 *     The DJ sequence reading World Tour event data in a Single Event is a probe item (HYPOTHESIS: it does not). CHANGES AUDIO.
 */
#ifndef BMASHUP_RULES_H
#define BMASHUP_RULES_H
#include "takedawn_plugin.h"
#ifdef __cplusplus
extern "C" {
#endif
#define BM_RULES_SERVICE "bmashup.rules"
#define BM_RULES_VERSION 6u         /* 1: Eliminator rules; 2: + set_road_rage_props; 3: + set_end_session;
                                       4: + set_crash_breaker_all; 5: + set_rival_count / set_rival_car;
                                       6: + set_single_event_dj */
#define BM_RULES_VERSION_5 5u
#define BM_RULES_VERSION_4 4u
#define BM_RULES_RIVALS_MAX 5       /* AI rivals (humans + AI <= 6) */
#define BM_RULES_RIVAL_CARS 67u     /* car index range 0..66 (the game's car table) */
#define BM_RULES_VERSION_3 3u
#define BM_RULES_VERSION_2 2u
#define BM_RULES_CB_RADIUS_DEFAULT 15u   /* metres */
#define BM_RULES_CB_RADIUS_MIN 5u
#define BM_RULES_CB_RADIUS_MAX 40u
#define BM_RULES_VERSION_1 1u

enum { BM_RULES_OK = 0, BM_RULES_BAD_ARG = 1, BM_RULES_NOT_IN_RACE = 2, BM_RULES_CONFLICT = 3, BM_RULES_NOT_OWNER = 4,
       BM_RULES_NO_RACER = 5, BM_RULES_LAST_PLAYER = 6, BM_RULES_RATE = 7, BM_RULES_WRONG_THREAD = 8,
       BM_RULES_UNAVAILABLE = 9, BM_RULES_ALREADY = 10, BM_RULES_WRONG_MODE = 11 /* not an Eliminator-logic race */ };
enum { BM_RULES_END_TIME = 1, BM_RULES_END_LAST_STANDING = 2, BM_RULES_END_OTHER = 3 };

typedef struct bm_rules_status {
    uint32_t struct_size;
    uint32_t eliminator_race;       /* 1: the race in play runs the game's Eliminator logic */
    uint32_t owned, yours;
    uint32_t racing;                /* racers still racing */
    uint32_t eliminated;            /* this race (game and plugin) */
    uint32_t lap_elimination;       /* 1: the game's per-lap elimination is on */
    uint32_t ending;                /* 1: end_race is running */
    /* ---- version 2 ---- */
    uint32_t road_rage_props;       /* 1: set_road_rage_props is on */
    /* ---- version 3 ---- */
    uint32_t end_session;           /* 1: set_end_session is on */
    /* ---- version 4 ---- */
    uint32_t crash_breaker_all;     /* 1: set_crash_breaker_all is on */
    uint32_t crash_breaker_radius;  /* its radius in metres */
    /* ---- version 5 ---- */
    uint32_t rival_count;           /* set_rival_count's value as int32 (0xFFFFFFFF = -1: the game's own count) */
    uint32_t rivals_applied;        /* the AI count the last changed set-up got (0xFFFFFFFF: none yet) */
    /* ---- version 6 ---- */
    uint32_t single_event_dj;       /* 1: set_single_event_dj is on */
    uint32_t dj_hub_opened;         /* hub tests answered "World Tour" for a Single Event since the last load (diagnostic) */
} bm_rules_status;                  /* 64 bytes (v1: 32, v2: 36, v3: 40, v4: 48, v5: 56) */

typedef struct bm_rules_api {
    uint32_t struct_size;
    uint32_t version;
    int32_t (TD_CALL *claim_race)(td_host *host);
    int32_t (TD_CALL *set_lap_elimination)(td_host *host, uint32_t on);
    int32_t (TD_CALL *eliminate)(td_host *host, uint32_t racer);
    int32_t (TD_CALL *end_race)(td_host *host, uint32_t reason);
    int32_t (TD_CALL *status)(td_host *host, bm_rules_status *out);
    /* ---- version 2 (check version >= 2 / struct_size before calling) ---- */
    int32_t (TD_CALL *set_road_rage_props)(td_host *host, uint32_t on);
    /* ---- version 3 (check version >= 3 / struct_size before calling) ---- */
    int32_t (TD_CALL *set_end_session)(td_host *host, uint32_t on);
    /* ---- version 4 (check version >= 4 / struct_size before calling) ---- */
    int32_t (TD_CALL *set_crash_breaker_all)(td_host *host, uint32_t on, uint32_t radius_m);
    /* ---- version 5 (check version >= 5 / struct_size before calling) ---- */
    int32_t (TD_CALL *set_rival_count)(td_host *host, int32_t count);
    int32_t (TD_CALL *set_rival_car)(td_host *host, uint32_t slot, int32_t car_index);
    /* ---- version 6 (check version >= 6 / struct_size before calling) ---- */
    int32_t (TD_CALL *set_single_event_dj)(td_host *host, uint32_t on);
} bm_rules_api;
#ifdef __cplusplus
}
#endif
#endif
