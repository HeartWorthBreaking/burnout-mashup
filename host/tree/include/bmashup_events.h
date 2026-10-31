/*
 * bmashup_events.h - the "bmashup.events" service: Burnout Mashup's private,
 * experimental engine events for native plugins (docs/bmashup-events.md). Not
 * a Takedawn service: offered only by Burnout Mashup's own builds, through the
 * same optional export as Takedawn's (takedawn_services.h); it may change or go
 * away.
 *
 * A plugin subscribes to an engine point inside the game's update and is
 * called there, on the game's thread, with a small copy of what happened.
 * Several plugins may subscribe to the same event; each is called once per
 * event, observers before the game-changing services, in subscription order.
 * Observe only: no pointer into the game, no address, no write.
 *
 * Version 2 adds two lifecycle events, LOAD_DONE and RACE_EXIT, from the
 * game's own load and world-transition points (verified by Burnout Mashup's
 * ordering probe), with fields appended to bm_event. A version-1 plugin is
 * unaffected: it subscribes to the car update only and reads the fields its
 * struct_size covers.
 *
 * Version 3 adds TAKEDOWN / WRECK and version 4 BOOST_AWARD, each with fields
 * appended; earlier fields keep their offsets, so an older plugin reads the
 * prefix its struct_size covers. Version 6 adds CRASH_RESULT (a Crash
 * junction's result, with the junction and the score the game records).
 *
 * Version 7 (platform 0.1.9, hook request P2 / P3; append-only): the OBSERVE
 * twins of bmashup.hooks v3's points with the same numbers and values:
 * 8 HUD_PASS (once a picture: keep callbacks < 0.1 ms; subscribe only if
 * needed), 10 TRAFFIC_CONTACT, 11 WRECK_CAUSE, 12 EVENT_SOUND. 9
 * CAMERA_FINAL and 13 FINISH_CAMERA are hooks-only (per-picture camera math).
 * bm_event grows at its end by the fields of bm_hook_ctx's v3 tail without the
 * camera fields (same names / meanings); older plugins read their prefix.
 * Modifiers stay BOOST_AWARD only (the new outputs live in bmashup.hooks).
 * Order at one occurrence: hooks MODIFY -> these observers -> hooks OBSERVE ->
 * host observers. An event whose mark is not in this build (or whose
 * start-time check failed) answers BM_EVENTS_UNAVAILABLE at subscribe.
 *
 * Subscribe only while Takedawn starts the plugins (takedawn_plugin_init, or
 * takedawn_plugin_service): afterwards the lists are fixed. There is no
 * unsubscribe: plugins are never unloaded, and nothing is called once the
 * process starts to exit.
 */
#ifndef BMASHUP_EVENTS_H
#define BMASHUP_EVENTS_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_EVENTS_SERVICE "bmashup.events"
#define BM_EVENTS_VERSION 7u            /* 7 (platform 0.1.9): + HUD_PASS, TRAFFIC_CONTACT, WRECK_CAUSE, EVENT_SOUND */

/* Events. */
enum {
    /* Player 1's car is about to run its update: once per car update (each
     * simulation step of a race, so 60 a second and more with High refresh).
     * Keep the call short: it holds up the game. */
    BM_EVENT_PLAYER_CAR_UPDATE = 1,
    /* Version 2: the game finished a load (a track, the front end, or a
     * restart of the race on the resident track). load_kind says which.
     * Once per load end, on the game's thread, after the load. */
    BM_EVENT_LOAD_DONE = 2,
    /* Version 2: a race is being left (to the menus, or to load another
     * event): once, on the game's thread, before the game tears the race's
     * world down. The race's results are already final. */
    BM_EVENT_RACE_EXIT = 3,
    /* Version 3: a takedown the game counted: `actor` took `victim` down (the
     * attacker's per-race takedown count went up). Once per takedown (the
     * game's own once-per-wreck latch, sub_00198E60); `kind` is the kind the
     * game counted (sub_001994D0). Racers are their index in the race's list
     * (as bmashup.route); a car outside the list is BM_EVENT_NO_RACER. */
    BM_EVENT_TAKEDOWN = 4,
    /* Version 3: a car became wrecked (its wrecked state set by sub_0018C7D0
     * for player cars or sub_0018E010 for AI cars; only the change, so once per
     * wreck until it is back on the road). `victim` is that car; `actor` is
     * BM_EVENT_NO_RACER (the game decides blame later: see TAKEDOWN). */
    BM_EVENT_WRECK = 5,
    /* Version 4: the game is adding boost to a racer's meter (its boost-add
     * routine sub_0017A530 is entered). Once per add. `award_source` names the
     * award from the CALL SITE only (never from the amount): a site this build
     * has not verified is BM_BOOST_UNKNOWN with its address in `award_site`.
     * `award_amount` is what the game's award code asks for at that moment:
     * after bmashup.tune (the code reads the tuned value), before the meter's
     * own cap. `recipient` is the racer whose meter it is, or
     * BM_EVENT_NO_RACER. The continuous sources (tailgating, air, oncoming,
     * drift, grinding) add small amounts every simulation step: hundreds per
     * second in a race; filter by `award_source`. A boost add that a
     * subscriber's own call causes is not delivered again (no re-entry). */
    BM_EVENT_BOOST_AWARD = 6,
    /* Version 6: a Crash event ended and the game records its result: once
     * per Crash attempt (a RETRY is a new attempt), on the game's thread, at
     * the game's own record step (the end of the event, before Crash Results
     * is shown). `junction` is the junction's position in the game's list
     * (bmashup.crash), `junction_id` / `track_id` its IDs, `crash_score` the
     * total the game records for it, `crash_mode` which scoring it used. A
     * Crash event whose ID is not in the game's list (never the case for the
     * game's own junctions) is still delivered, with junction
     * BM_EVENT_NO_JUNCTION; the game's record write is then skipped (it
     * would land in another record). Races and the other modes deliver no
     * CRASH_RESULT. */
    BM_EVENT_CRASH_RESULT = 7,
    /* Version 7 (twins of bmashup.hooks v3; each UNAVAILABLE where the build has no mark) */
    BM_EVENT_HUD_PASS = 8,          /* once a picture while the race HUD is drawn (player 0) */
    BM_EVENT_TRAFFIC_CONTACT = 10,  /* a racer-vs-traffic contact about to become a traffic crash (the final outcome) */
    BM_EVENT_WRECK_CAUSE = 11,      /* a takedown about to be counted (aggressor, victim) */
    BM_EVENT_EVENT_SOUND = 12       /* the takedown-sign sound with its final pitch level */
};

#define BM_EVENT_NO_RACER 0xFFFFFFFFu
#define BM_EVENT_NO_JUNCTION 0xFFFFFFFFu

/* crash_mode (version 6, CRASH_RESULT; also in bmashup_crash.h) */
#ifndef BM_CRASH_MODE_SINGLE
#define BM_CRASH_MODE_SINGLE 1u     /* one player's crash total */
#define BM_CRASH_MODE_PAIR   2u     /* the game adds two players' totals (its two-player Crash scoring) */
#endif

/* award_source (version 4, BOOST_AWARD): the call site of the game's boost add */
enum {
    BM_BOOST_UNKNOWN       = 0,     /* a site this build does not name (award_site says which) */
    BM_BOOST_PERFECT_LAP   = 1,     /* "Score/Boost/Lap | Perfect Lap Boost value" (discrete, once per perfect lap) */
    BM_BOOST_BURNOUT_LAP   = 2,     /* "Score/Boost/Lap | Burnout Lap Boost value" (discrete) */
    BM_BOOST_TAILGATING    = 3,     /* "Score/Tailgating | Extra boost per second" (continuous) */
    BM_BOOST_AIR           = 4,     /* "Score/Boost/Air | Boost value per Air metre" (continuous) */
    BM_BOOST_ONCOMING      = 5,     /* "Score/Boost/Oncoming | Boost value per Oncoming metre" (continuous) */
    BM_BOOST_DRIFT         = 6,     /* "Score/Boost/Drift | Boost value per Drift metre" (continuous) */
    BM_BOOST_GRINDING      = 7,     /* "Score/Grinding | Extra boost per second" (continuous) */
    BM_BOOST_PROP_HIT      = 8,     /* "Score/Boost/Props | Prop Hit Boost value" (discrete) */
    BM_BOOST_BOOST_START   = 9,     /* "Score/Boost/Boost Start | Boost Start Boost value" (discrete) */
    BM_BOOST_TRADING_PAINT = 10,    /* "Score/Boost/Aggressive | Trading Paint Boost value" (discrete) */
    BM_BOOST_HOST          = 11     /* a host service's own add (bmashup.boost): no game call site */
};

/* kind (version 3, TAKEDOWN) */
enum {
    BM_TAKEDOWN_STANDARD   = 1,     /* incl. psyche-out; double / spree are bonuses on top */
    BM_TAKEDOWN_AFTERTOUCH = 2,
    BM_TAKEDOWN_SIGNATURE  = 3,
    BM_TAKEDOWN_UNKNOWN    = 4      /* none of the three counters moved (reported, not hidden) */
};

/* load_kind (version 2). */
enum {
    BM_LOAD_NONE     = 0,
    BM_LOAD_TRACK    = 1,           /* a track was loaded (its route data and lanes are new) */
    BM_LOAD_FRONTEND = 2,           /* the menus / front end */
    BM_LOAD_PARTIAL  = 3,           /* a load the classification does not recognise (reported, not hidden) */
    BM_LOAD_RESTART  = 4            /* the race restarted on the track already loaded (Retry) */
};

/* Results. */
enum {
    BM_EVENTS_OK            = 0,
    BM_EVENTS_BAD_ARG       = 1,    /* no host, no fn, no out, or out->struct_size below 8 */
    BM_EVENTS_UNKNOWN_EVENT = 2,
    BM_EVENTS_CLOSED        = 3,    /* the plugins' start is over: lists are fixed */
    BM_EVENTS_UNAVAILABLE   = 4,    /* not hooked in this run (RECOMP_DEBUG=autopilot holds the point) */
    BM_EVENTS_ALREADY       = 5,    /* this plugin has subscribed to this event */
    BM_EVENTS_FULL          = 6     /* no room for another subscriber */
};

/* What a subscriber is given (Takedawn's, for the call's length only). */
typedef struct bm_event {
    uint32_t struct_size;           /* the size Takedawn filled in */
    uint32_t event;                 /* BM_EVENT_* */
    uint32_t sequence;              /* the engine point's count: the same for every subscriber of one occurrence */
    uint32_t step;                  /* the game's simulation step */
    float    race_time_s;           /* player 1's race time */
    uint32_t car_phase;             /* player 1's event phase: 0 / 1 before the GO, 2 racing, 3 finished */
    /* version 2 (struct_size says whether they are there; 0 for PLAYER_CAR_UPDATE) */
    uint32_t load_kind;             /* LOAD_DONE: BM_LOAD_*; RACE_EXIT: the race's load (TRACK or RESTART) */
    uint32_t track_loads;           /* track loads so far in this process */
    uint32_t race_exits;            /* race exits so far, this one included */
    uint32_t lanes;                 /* the loaded track's AI route lanes (0 when no track is loaded) */
    uint32_t racers;                /* RACE_EXIT: the race's racers; LOAD_DONE: 0 */
    /* version 3 (TAKEDOWN / WRECK; 0 for the other events) */
    uint32_t actor;                 /* racer index, or BM_EVENT_NO_RACER */
    uint32_t victim;                /* racer index, or BM_EVENT_NO_RACER */
    uint32_t kind;                  /* TAKEDOWN: BM_TAKEDOWN_*; WRECK: 0 */
    uint32_t actor_takedowns;       /* TAKEDOWN: the actor's takedowns this race, this one included */
    /* version 4 (BOOST_AWARD; 0 for the other events) */
    uint32_t recipient;             /* racer index, or BM_EVENT_NO_RACER */
    uint32_t award_source;          /* BM_BOOST_* */
    uint32_t award_site;            /* the game's call site (return address); 0 for BM_BOOST_HOST */
    float    award_amount;          /* boost units asked for (after bmashup.tune, before the meter's cap); v5: after the modifiers */
    /* version 5 (BOOST_AWARD) */
    float    award_requested;       /* what the game asked for, before any modifier (= award_amount when none changed it) */
    uint32_t award_modified;        /* 1 when a modifier changed the amount */
    /* version 6 (CRASH_RESULT; 0 / empty for the other events) */
    uint32_t junction;              /* 0..99, or BM_EVENT_NO_JUNCTION */
    uint32_t crash_score;           /* the total the game records for the junction */
    uint32_t crash_mode;            /* BM_CRASH_MODE_* */
    char     junction_id[16];       /* the junction's game ID, e.g. "1G0000USC3V1" (NUL-terminated) */
    char     track_id[16];          /* its track, e.g. "US_C3_V1" ("" when the ID names none) */
    /* version 7 (one group per event; 0 for the other events) */
    uint32_t hud_visible;           /* HUD_PASS: 1 when the title draws its HUD scenes this picture */
    float    frame_dt_s;            /* HUD_PASS: time since the last picture */
    uint32_t contact_racer;         /* TRAFFIC_CONTACT: racer index */
    uint32_t contact_traffic;       /* TRAFFIC_CONTACT: traffic handle (opaque, this occurrence only) */
    float    contact_closing_mps;   /* TRAFFIC_CONTACT: closing speed */
    uint32_t contact_same_dir;      /* TRAFFIC_CONTACT: 1 when the two cars move the same way */
    uint32_t contact_outcome;       /* TRAFFIC_CONTACT: the final outcome (bmashup_hooks.h BM_CONTACT_*: 0 GAME, 1 NO_CRASH) */
    uint32_t cause_aggressor;       /* WRECK_CAUSE: racer index or BM_EVENT_NO_RACER */
    uint32_t cause_victim;          /* WRECK_CAUSE: racer index */
    uint32_t sound;                 /* EVENT_SOUND: 1 = the takedown sign */
    uint32_t sound_level_game;      /* EVENT_SOUND: the game's level 0..4 */
    uint32_t sound_event;           /* EVENT_SOUND: the sign event (0x93, 0x9F..0xA6) */
    uint32_t sound_level;           /* EVENT_SOUND: the final level 0..4 (after bmashup.hooks modifiers) */
} bm_event;

typedef void (TD_CALL *bm_event_fn)(const bm_event *event, void *user);

/* Version 5: a MODIFIER of BOOST_AWARD (subscribe_modifier). Called on the game's thread before the game adds the boost and
 * before the observers, with the event (award_amount = the amount so far) and the amount to change in *amount. Return 1
 * to change it to *amount, 0 to leave it. Rules (BM_BOOST_MOD_*): the result must be finite and in 0 .. 16 x what the game
 * asked for (award_requested), else it is ignored and counted; modifiers run in the order they subscribed (the plugins'
 * start order), each seeing the previous one's result; HOST awards (a host service's own add) are never modified; an add
 * caused while a modifier or observer runs is neither modified nor delivered (no feedback). */
typedef int32_t (TD_CALL *bm_modifier_fn)(const bm_event *event, float *amount, void *user);
#define BM_BOOST_MOD_MAX_FACTOR 16.0f

typedef struct bm_events_stats {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t delivered;             /* events this plugin was given */
    uint32_t occurrences;           /* times the engine point ran (any car) */
    uint32_t register_faults;       /* times this plugin's call changed the guest's registers (put back) */
    /* version 5 (BOOST_AWARD modifiers) */
    uint32_t modified;              /* this plugin's modifier changed the amount */
    uint32_t rejected;              /* this plugin's modifier returned an invalid amount (ignored) */
} bm_events_stats;

/* The service's table: valid until the process ends. */
typedef struct bm_events_api {
    uint32_t struct_size;           /* sizeof (bm_events_api) as built */
    uint32_t version;               /* BM_EVENTS_VERSION */
    /* fn(event, user) for each `event` from now on. While the plugins start
     * only. BM_EVENTS_OK, or why not. */
    int32_t (TD_CALL *subscribe)(td_host *host, uint32_t event, bm_event_fn fn, void *user);
    /* This plugin's counts for `event` into *out (set out->struct_size). Any thread. */
    int32_t (TD_CALL *stats)(td_host *host, uint32_t event, bm_events_stats *out);
    /* version 5: a modifier of `event` (BOOST_AWARD only), one per plugin; while the plugins start only */
    int32_t (TD_CALL *subscribe_modifier)(td_host *host, uint32_t event, bm_modifier_fn fn, void *user);
} bm_events_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_EVENTS_H */
