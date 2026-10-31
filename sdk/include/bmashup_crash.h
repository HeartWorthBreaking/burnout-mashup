/*
 * bmashup_crash.h - the "bmashup.crash" service: Burnout Mashup's private,
 * experimental, READ-ONLY queries about Crash mode for native plugins
 * (docs/bmashup-crash.md). Not a Takedawn service; it may change or go away.
 *
 * - The Crash junctions as the game lists them: their count, each one's game
 *   ID ("1G0000USC3V1") and track ("US_C3_V1"), and the position of an ID.
 *   The host checks the game's list against the build it was made for before
 *   it answers; on another build every query says BM_CRASH_UNAVAILABLE.
 * - The last Crash result the game recorded (the same values as
 *   bmashup.events version 6 CRASH_RESULT), for a plugin that only looks now
 *   and then.
 *
 * Nothing here writes to the game. No address or pointer into the game is
 * given out. Any thread; the last result is a consistent copy.
 */
#ifndef BMASHUP_CRASH_H
#define BMASHUP_CRASH_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_CRASH_SERVICE "bmashup.crash"
#define BM_CRASH_VERSION 1u

/* Results. */
enum {
    BM_CRASH_OK          = 0,
    BM_CRASH_BAD_ARG     = 1,       /* no host, no out, out->struct_size below 8, or a malformed ID */
    BM_CRASH_NOT_FOUND   = 2,       /* no junction at that position / with that ID */
    BM_CRASH_UNAVAILABLE = 3,       /* the game's junction list is not the one this host was made for */
    BM_CRASH_NONE_YET    = 4        /* no Crash result recorded in this process yet */
};

#define BM_CRASH_NO_JUNCTION 0xFFFFFFFFu

/* Crash scoring (as bmashup_events.h's crash_mode). */
#ifndef BM_CRASH_MODE_SINGLE
#define BM_CRASH_MODE_SINGLE 1u
#define BM_CRASH_MODE_PAIR   2u
#endif

typedef struct bm_crash_junction {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t index;                 /* its position in the game's list, 0-based */
    char     id[16];                /* the game ID, e.g. "1G0000USC3V1" */
    char     track_id[16];          /* its track, e.g. "US_C3_V1" */
} bm_crash_junction;

typedef struct bm_crash_result {
    uint32_t struct_size;           /* in / out as above */
    uint32_t sequence;              /* the CRASH_RESULT count of this process (1 = the first) */
    uint32_t junction;              /* 0..99, or BM_CRASH_NO_JUNCTION */
    uint32_t score;                 /* the total the game recorded */
    uint32_t mode;                  /* BM_CRASH_MODE_* */
    char     junction_id[16];
    char     track_id[16];
} bm_crash_result;

/* The service's table: valid until the process ends. */
typedef struct bm_crash_api {
    uint32_t struct_size;           /* sizeof (bm_crash_api) as built */
    uint32_t version;               /* BM_CRASH_VERSION */
    /* The number of junctions (100 in Burnout 3), 0 when unavailable. */
    uint32_t (TD_CALL *junction_count)(td_host *host);
    /* Junction `index` into *out (set out->struct_size). */
    int32_t (TD_CALL *junction_get)(td_host *host, uint32_t index, bm_crash_junction *out);
    /* The position of the junction with game ID `id` ("1G0000USC3V1") into *index. */
    int32_t (TD_CALL *junction_find)(td_host *host, const char *id, uint32_t *index);
    /* The last Crash result the game recorded (any junction), into *out. */
    int32_t (TD_CALL *last_result)(td_host *host, bm_crash_result *out);
} bm_crash_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_CRASH_H */
