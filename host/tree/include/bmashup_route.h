/*
 * bmashup_route.h - the "bmashup.route" service: Burnout Mashup's private,
 * experimental, READ-ONLY view of where each racer is on the track's AI
 * route: the lane and segment its tracker holds, and the racing lane and
 * segment its AI drives. Not a Takedawn service: offered only by Burnout
 * Mashup's own builds, through the same optional export as Takedawn's
 * (takedawn_services.h); it may change or go away.
 *
 * Lanes are the track's AI route lanes, numbered as in the track data:
 * 0..63 the game's, 64.. the lane extension's (bmashup.engine). Segments are
 * the lane's own segment numbers. Nothing here is an address; every value is
 * a copy, validated before it is returned (a holder that names no lane the
 * game or the extension knows is reported as not valid, never guessed).
 *
 * Available while a race's track is resident: from the track's load
 * (bmashup.events LOAD_DONE, kind TRACK or RESTART) to its exit (RACE_EXIT).
 * Otherwise every call answers BM_ROUTE_UNAVAILABLE.
 *
 * Threads: call on the game's thread (inside a bmashup.events callback) for
 * values of one update. From another thread the reads are safe (plain
 * aligned reads of validated addresses) but may mix two updates.
 *
 * Version 2 adds final_race(): a COPY of the last race's route, taken at the
 * race exit just before the game tears the race's world down (the point
 * bmashup.events RACE_EXIT is delivered from, before the delivery). Live
 * queries stay unavailable from the exit on; the copy is how a RACE_EXIT
 * callback (or anything later) learns where the racers ended. It holds what
 * the live queries would have answered at that moment, validated the same
 * way: a racer whose holder could not be validated has its flag clear. It
 * stays readable until the next race exit replaces it (race_exit says which
 * exit it is from); before the first race exit final_race answers
 * BM_ROUTE_UNAVAILABLE. Positions, laps, times and results are not in it.
 */
#ifndef BMASHUP_ROUTE_H
#define BMASHUP_ROUTE_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_ROUTE_SERVICE "bmashup.route"
#define BM_ROUTE_VERSION 2u
#define BM_ROUTE_FINAL_RACERS 8u        /* the game's racer list holds at most 8 */

#define BM_ROUTE_NO_LANE 0xFFu          /* the holder names "no lane" (the game's NONE) */

enum {
    BM_ROUTE_OK          = 0,
    BM_ROUTE_BAD_ARG     = 1,           /* no host, no out, out->struct_size below 8 */
    BM_ROUTE_UNAVAILABLE = 2,           /* no race's track is resident */
    BM_ROUTE_NO_RACER    = 3            /* index past the race's racers */
};

/* flags */
enum {
    BM_ROUTE_TRACKER_VALID = 1u,        /* tracker_lane / tracker_segment hold a lane the track has, or NO_LANE */
    BM_ROUTE_RACING_VALID  = 2u,        /* racing_lane / racing_segment likewise (racers with an AI driver only) */
    BM_ROUTE_ON_EXTENSION  = 4u         /* a lane >= 64 (the lane extension) is among them */
};

typedef struct bm_route_track {
    uint32_t struct_size;               /* in: the size you have; out: the size filled in */
    uint32_t lanes;                     /* the resident track's lanes */
    uint32_t extension_lanes;           /* of them on the lane extension (lanes >= 64) */
    uint32_t racers;                    /* the race's racers (the world's list) */
    uint32_t load_kind;                 /* the load that made it resident: bmashup.events BM_LOAD_TRACK / BM_LOAD_RESTART */
    uint32_t track_loads;               /* track loads so far (as bmashup.events reports) */
} bm_route_track;                       /* 24 bytes */

typedef struct bm_route_racer {
    uint32_t struct_size;
    uint32_t index;                     /* the racer's position in the race's list */
    uint32_t flags;                     /* BM_ROUTE_* */
    uint32_t tracker_lane;              /* 0..254, BM_ROUTE_NO_LANE */
    uint32_t tracker_segment;
    uint32_t racing_lane;               /* 0..254, BM_ROUTE_NO_LANE */
    uint32_t racing_segment;
} bm_route_racer;                       /* 28 bytes */

/* final flags (version 2) */
enum {
    BM_ROUTE_FINAL_LIST_INVALID = 1u    /* the racer list could not be read at the exit: racers = 0 */
};

typedef struct bm_route_final {         /* version 2 */
    uint32_t struct_size;               /* in: the size you have; out: the size filled in */
    uint32_t race_exit;                 /* the race exit it was taken at (bmashup.events race_exits) */
    uint32_t flags;                     /* BM_ROUTE_FINAL_* */
    uint32_t lanes;                     /* the track's lanes then */
    uint32_t extension_lanes;
    uint32_t load_kind;                 /* the load the race ran on: BM_LOAD_TRACK / BM_LOAD_RESTART */
    uint32_t track_loads;
    uint32_t racers;                    /* entries of racer[] that are filled (0..8) */
    bm_route_racer racer[BM_ROUTE_FINAL_RACERS];    /* as racer() would have answered then */
} bm_route_final;                       /* 256 bytes */

typedef struct bm_route_api {
    uint32_t struct_size;               /* sizeof (bm_route_api) as built */
    uint32_t version;                   /* BM_ROUTE_VERSION */
    int32_t (TD_CALL *track)(td_host *host, bm_route_track *out);
    int32_t (TD_CALL *racer)(td_host *host, uint32_t index, bm_route_racer *out);
    /* version 2 (struct_size says whether it is there): the last race's route, copied at its exit. BM_ROUTE_OK, or
     * BM_ROUTE_UNAVAILABLE before the first race exit (or, from another thread, while the copy is being taken). */
    int32_t (TD_CALL *final_race)(td_host *host, bm_route_final *out);
} bm_route_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_ROUTE_H */
