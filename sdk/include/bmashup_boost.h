/*
 * bmashup_boost.h - the "bmashup.boost" service: Burnout Mashup's private,
 * experimental boost top-up (docs/bmashup-boost.md). Not a Takedawn service:
 * offered only by Burnout Mashup's own builds, through the same optional
 * export as Takedawn's (takedawn_services.h); it may change or go away.
 *
 * One thing: a plugin may ask that player 1's boost bar be topped up to its
 * current maximum, by the game's own add-boost routine (the one the game's
 * own refills use), at most a few times a race. The game then decides
 * everything else: whether the routine adds anything now, when a boost
 * starts (the player's button), how strong it is and how fast it drains.
 * Nothing else: no value, no address, no car is passed in; no setting or
 * table of the game is changed, so there is nothing to restore.
 *
 * Version 2 (platform 0.1.8, hook request P1 "arbitrary boost award"; append-only, v1 unchanged): award() asks the same
 * routine to add a CHOSEN amount (game units) to a human player's bar at that player's next car update. The game's own
 * gate, factors and cap still apply after it, so the bar gets "the amount asked, then the game's rules" (CHANGES
 * GAMEPLAY: documented label). Bounds: amount finite, > 0 and <= BM_BOOST_AWARD_MAX_BARS x the bar's maximum (checked
 * at the request and again at the car update); per plugin at most BM_BOOST_AWARDS_PER_SECOND accepted in any 60
 * simulation steps and BM_BOOST_AWARDS_PER_RACE a race (RATE / LIMIT); one pending award per plugin and player
 * (ALREADY_PENDING). Recipient: player 0 (player 1's car); player 1 (split screen) answers UNSUPPORTED until a split-
 * screen run exists; any other index NO_PLAYER. Several plugins may award (awards add, like the game's own). An award
 * never changes what bmashup.events / hooks MODIFY callbacks see as the game's awards (host source).
 */
#ifndef BMASHUP_BOOST_H
#define BMASHUP_BOOST_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_BOOST_SERVICE   "bmashup.boost"
#define BM_BOOST_VERSION   2u       /* 1: fill / status; 2 (platform 0.1.8): + award / award_status */
#define BM_BOOST_FILLS_MAX 3u       /* top-ups a race */
#define BM_BOOST_AWARD_MAX_BARS    1.0f   /* v2: an award at most this many x the bar's maximum */
#define BM_BOOST_AWARDS_PER_SECOND 8u     /* v2: per plugin, in any 60 simulation steps */
#define BM_BOOST_AWARDS_PER_RACE   512u   /* v2: per plugin and race */

/* bm_boost_status.state */
enum {
    BM_BOOST_STATE_IDLE    = 0,     /* no request in this race yet */
    BM_BOOST_STATE_PENDING = 1,     /* accepted: done in player 1's next car update, if still valid then */
    BM_BOOST_STATE_DONE    = 2,     /* the last request ran (meter_before / meter_after say what it did) */
    BM_BOOST_STATE_REFUSED = 3      /* the last request was refused or dropped: see reason */
};

/* fill()'s result, and bm_boost_status.reason. */
enum {
    BM_BOOST_OK              = 0,   /* fill: accepted (PENDING). reason: nothing to report */
    BM_BOOST_BAD_ARG         = 1,   /* no host, no out, or out->struct_size below 8 */
    BM_BOOST_UNAVAILABLE     = 2,   /* the service has not seen a game update yet */
    BM_BOOST_WRONG_THREAD    = 3,   /* fill is for the game's thread (an on_update call of takedawn.race) */
    BM_BOOST_UNSUPPORTED     = 4,   /* a game this service does not know: nothing is touched */
    BM_BOOST_DEBUG_AUTOPILOT = 5,   /* RECOMP_DEBUG=autopilot holds the car update: this service stays off */
    BM_BOOST_NOT_IN_RACE     = 6,   /* menus, loading, or a stage being left */
    BM_BOOST_COUNTDOWN       = 7,   /* in a stage, before the GO */
    BM_BOOST_PAUSED          = 8,
    BM_BOOST_RACE_OVER       = 9,   /* player 1's race is finished */
    BM_BOOST_NO_CAR          = 10,  /* player 1's car is not one this service knows */
    BM_BOOST_ALREADY_PENDING = 11,  /* a request is waiting already */
    BM_BOOST_LIMIT           = 12,  /* BM_BOOST_FILLS_MAX top-ups this race already */
    BM_BOOST_STALE           = 13,  /* a request dropped before it ran: the race moved on */
    BM_BOOST_NOT_ADDED       = 14,  /* DONE, but the game's routine added nothing (the bar was not full) */
    /* v2 (appended) */
    BM_BOOST_OUT_OF_RANGE    = 15,  /* award: amount not finite, <= 0 or above BM_BOOST_AWARD_MAX_BARS x the bar's max */
    BM_BOOST_RATE            = 16,  /* award: BM_BOOST_AWARDS_PER_SECOND accepted in the last 60 steps already */
    BM_BOOST_NO_PLAYER       = 17   /* award: not a human player's index (0 / 1) */
};
/* v2: award() also answers BM_BOOST_UNSUPPORTED for player 1 (split screen, not tested), ALREADY_PENDING, LIMIT
 * (BM_BOOST_AWARDS_PER_RACE), and the v1 reasons (WRONG_THREAD, NOT_IN_RACE, COUNTDOWN, PAUSED, RACE_OVER, NO_CAR...). */

typedef struct bm_boost_status {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t state;                 /* BM_BOOST_STATE_* */
    uint32_t reason;                /* BM_BOOST_*: why REFUSED, or NOT_ADDED with DONE, else BM_BOOST_OK */
    uint32_t race;                  /* which race: changes with each new race the service sees */
    uint32_t fills;                 /* top-ups done in this race */
    uint32_t have_meter;            /* 1: the next three fields are player 1's, as of the last game update */
    float    meter;                 /* the boost bar, in the game's units (0 .. meter_max) */
    float    meter_max;             /* its current maximum (the bar's length; grows in some events) */
    uint32_t boosting;              /* 1 while player 1 boosts */
    float    meter_before;          /* the last top-up: the bar before and after the game's routine */
    float    meter_after;
} bm_boost_status;

/* v2: one plugin's award state (per plugin and player). */
typedef struct bm_boost_award_status {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t state;                 /* BM_BOOST_STATE_* of the plugin's last award (IDLE: none this race) */
    uint32_t reason;                /* BM_BOOST_*: why REFUSED, or NOT_ADDED with DONE, else BM_BOOST_OK */
    uint32_t awards;                /* awards of this plugin carried out in this race */
    float    requested;             /* the last award's amount */
    float    meter_before;          /* the bar before / after the game's routine (DONE) */
    float    meter_after;
} bm_boost_award_status;            /* 28 bytes */

/* The service's table: valid until the process ends. */
typedef struct bm_boost_api {
    uint32_t struct_size;           /* sizeof (bm_boost_api) as built */
    uint32_t version;               /* BM_BOOST_VERSION */
    /* Ask for one top-up of player 1's boost bar in the race in play. On the
     * game's thread only. It changes nothing in the game itself: the request
     * waits for player 1's next car update, which checks everything again
     * and only then calls the game's routine. BM_BOOST_OK when accepted,
     * else the reason it was refused. */
    int32_t (TD_CALL *fill)(td_host *host);
    /* The state and player 1's boost bar in *out (set out->struct_size
     * first). Any thread; always one whole update's values. BM_BOOST_OK, or
     * BM_BOOST_BAD_ARG. */
    int32_t (TD_CALL *status)(td_host *host, bm_boost_status *out);
    /* ---- version 2 (read only when version >= 2 and struct_size covers them) ---- */
    /* Award `amount` (game units) to human player `player` at that player's next car update, by the game's add-boost
     * routine. On the game's thread only. BM_BOOST_OK when accepted (the plugin's award state PENDING), else why. */
    int32_t (TD_CALL *award)(td_host *host, uint32_t player, float amount);
    /* The calling plugin's last award for `player` (set out->struct_size first). Any thread. BM_BOOST_OK, BAD_ARG,
     * NO_PLAYER. A plugin that never awarded gets state IDLE. */
    int32_t (TD_CALL *award_status)(td_host *host, uint32_t player, struct bm_boost_award_status *out);
} bm_boost_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_BOOST_H */
