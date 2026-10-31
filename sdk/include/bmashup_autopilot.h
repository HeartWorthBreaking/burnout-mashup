/*
 * bmashup_autopilot.h - the "bmashup.autopilot" service: Burnout Mashup's
 * private, experimental gameplay control (docs/bmashup-autopilot.md). Not a
 * Takedawn service: it is offered only by Burnout Mashup's own builds, through
 * the same optional export as Takedawn's (takedawn_services.h), and may change
 * or go away.
 *
 * One thing: a plugin may ask the game's own AI to take over player 1's car
 * for the rest of the race in play, exactly as the title itself does on a
 * rolling start and at the finish. Nothing else: no address, no value, no
 * car is ever passed in, and no other part of the game can be changed
 * through it.
 *
 * Version 1: engage and status. At most one takeover a race; the service
 * never clears the AI's hold on the car by itself.
 *
 * Version 2 (gp I4) adds, at the end of the table (a version 1 caller is
 * unaffected):
 *   engage2  the same request with an explicit policy and the race it is
 *            meant for (status.race), so that a plugin can engage in every
 *            race of a process, each request bound to one race;
 *   release  the title's own hand-back (CB3PlayerCar::SetAIControlled(0)'s
 *            steps, done by the title itself at the end of a rolling start),
 *            in player 1's next car update, only while this service's own
 *            takeover holds the car in play. After it the pad drives the car
 *            (nothing pressed: it coasts). Not after the finish: the title's
 *            own finish takeover is the title's.
 * The status grows (struct_size says how much a caller gets): the last
 * release's refusal and the races engaged so far.
 */
#ifndef BMASHUP_AUTOPILOT_H
#define BMASHUP_AUTOPILOT_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_AUTOPILOT_SERVICE "bmashup.autopilot"
#define BM_AUTOPILOT_VERSION 2u

/* bm_autopilot_status.state */
enum {
    BM_AP_STATE_IDLE    = 0,    /* no request in this race */
    BM_AP_STATE_PENDING = 1,    /* accepted: the takeover is done in player 1's next car update, if still valid then */
    BM_AP_STATE_ENGAGED = 2,    /* the game's AI drives player 1's car */
    BM_AP_STATE_ENDED   = 3,    /* the race it was engaged in is over or was left; the car is NOT handed back */
    BM_AP_STATE_REFUSED = 4,    /* the last request in this race was refused or dropped: see reason */
    BM_AP_STATE_RELEASED = 5    /* version 2: handed back in this race (release); no new takeover in this race */
};

/* bm_autopilot_request.policy (version 2) */
enum {
    BM_AP_POLICY_ONCE_PER_RACE = 1  /* at most one takeover in the race named; a new race allows a new one */
};

/* engage()'s result, and bm_autopilot_status.reason. */
enum {
    BM_AP_OK              = 0,  /* engage: accepted (PENDING). reason: nothing to report */
    BM_AP_BAD_ARG         = 1,  /* no host, no out, or out->struct_size below 8 */
    BM_AP_UNAVAILABLE     = 2,  /* the service has not seen a game update yet */
    BM_AP_WRONG_THREAD    = 3,  /* engage is for the game's thread (an on_update call of takedawn.race) */
    BM_AP_UNSUPPORTED     = 4,  /* a game this service does not know: nothing is touched */
    BM_AP_DEBUG_AUTOPILOT = 5,  /* RECOMP_DEBUG=autopilot drives the car instead: this service stays off */
    BM_AP_NOT_IN_RACE     = 6,  /* menus, loading, or a stage being left */
    BM_AP_COUNTDOWN       = 7,  /* in a stage, before the GO */
    BM_AP_PAUSED          = 8,
    BM_AP_RACE_OVER       = 9,  /* player 1's race is finished */
    BM_AP_NO_CAR          = 10, /* player 1's car is not one this service can take over */
    BM_AP_AI_OWNED        = 11, /* the game's AI already holds the car (the title's own takeover) */
    BM_AP_ALREADY_PENDING = 12, /* a request is waiting already */
    BM_AP_ALREADY_USED    = 13, /* this race had its takeover: at most one a race */
    BM_AP_STALE           = 14, /* a request dropped before it ran: the race moved on (pause, new race, end) */
    /* version 2 calls only (engage2, release); never the status reason of a version 1 caller's request */
    BM_AP_WRONG_RACE      = 15, /* engage2: the race named is not the race in play (status.race) */
    BM_AP_NOT_ENGAGED     = 16  /* release: this service does not hold the car in this race */
};

typedef struct bm_autopilot_status {
    uint32_t struct_size;       /* in: the size the caller has; out: the size filled in */
    uint32_t state;             /* BM_AP_STATE_* */
    uint32_t reason;            /* BM_AP_*: why the last request was refused or dropped (REFUSED), else BM_AP_OK */
    uint32_t race;              /* which race this is about: changes with each new race the service sees */
    /* version 2 (struct_size 24) */
    uint32_t release_reason;    /* BM_AP_*: why the last release in this race was refused or dropped, else BM_AP_OK */
    uint32_t engaged_races;     /* races this process had a takeover in (this service's) */
} bm_autopilot_status;

/* engage2's request (version 2). */
typedef struct bm_autopilot_request {
    uint32_t struct_size;       /* sizeof (bm_autopilot_request): at least 12 */
    uint32_t policy;            /* BM_AP_POLICY_*; anything else: BM_AP_BAD_ARG */
    uint32_t race;              /* status.race of the race meant; 0: the race in play, whichever it is */
} bm_autopilot_request;

/* The service's table: valid until the process ends. */
typedef struct bm_autopilot_api {
    uint32_t struct_size;       /* sizeof (bm_autopilot_api) as built */
    uint32_t version;           /* BM_AUTOPILOT_VERSION */
    /* Ask for the takeover of player 1's car in the race in play. On the
     * game's thread only. It changes nothing in the game itself: the request
     * waits for player 1's next car update, which checks everything again
     * and does the takeover only if all still holds (else the state turns
     * REFUSED with BM_AP_STALE or the reason found). BM_AP_OK when accepted,
     * else the reason it was refused. */
    int32_t (TD_CALL *engage)(td_host *host);
    /* The state in *out (set out->struct_size first). Any thread. BM_AP_OK,
     * or BM_AP_BAD_ARG. */
    int32_t (TD_CALL *status)(td_host *host, bm_autopilot_status *out);
    /* Version 2 (present when version >= 2 and struct_size covers it). */
    /* engage with an explicit policy, bound to one race: refused with
     * BM_AP_WRONG_RACE (status unchanged) when req->race is not 0 and not
     * the race in play. Otherwise as engage. Game thread only. */
    int32_t (TD_CALL *engage2)(td_host *host, const bm_autopilot_request *req);
    /* Ask for the hand-back of player 1's car: only while ENGAGED (this
     * service's takeover, this race), racing, not paused. It writes nothing
     * itself: player 1's next car update checks everything again (the car,
     * the build, the race, the AI byte, the car's physics link) and does the
     * title's hand-back steps there; the state turns RELEASED. Refused or
     * dropped: the state stays ENGAGED and status.release_reason says why.
     * Game thread only. BM_AP_OK when accepted, else the reason. */
    int32_t (TD_CALL *release)(td_host *host);
} bm_autopilot_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_AUTOPILOT_H */
