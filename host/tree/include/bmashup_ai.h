/*
 * bmashup_ai.h - the "bmashup.ai" service: Burnout Mashup's private, experimental racer-AI query and pace control (Burnout Mashup
 * builds only; may change or go away). gp slice ai1, atlas gp\atlas\AI.md.
 *
 * Contract (version 1):
 *  - **Query:** per racer of the race's list (index as bmashup.racers / bmashup.events): the AI's speed cap (the limit its
 *    pace schedule / rubber band sets, m/s), its target speed (m/s), its schedule offset (s; > 0 = ahead of its schedule, so
 *    the game slows it), its schedule column and zone, and the car's speed (m/s). Read-only copies, no address.
 *  - **What pace changes:** the speed cap of every AI-driven RIVAL, each AI update, as cap x pace, right after the game has
 *    computed it. Player cars are never changed (player 1 under the game's own autopilot keeps the game's pace). The game's
 *    own rubber band still runs on top: a slower AI falls behind its schedule and the game raises its cap again (by at most
 *    its own 4 s per zone correction), so the visible effect is smaller than the factor.
 *  - **Bounds:** pace finite, BM_AI_PACE_MIN (0.5) <= pace <= BM_AI_PACE_MAX (1.5); 1.0 = the game's own cap (nothing written).
 *  - **When / reversible:** used from the next AI update after set(); the cap is recomputed from scratch every update, so
 *    reset() (or pace 1.0) gives the game's own behaviour at once. Nothing persists.
 *  - **Ownership / conflicts:** the first requester owns the pace; another requester's set() is refused (CONFLICT);
 *    reset() by the owner returns to 1.0 and releases.
 *  - **Threads:** set / reset / get on the game's thread (plugin init, a bmashup.events callback, takedawn.race's update);
 *    racer queries there too (values of the last game update).
 */
#ifndef BMASHUP_AI_H
#define BMASHUP_AI_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_AI_SERVICE "bmashup.ai"
#define BM_AI_VERSION 1u
#define BM_AI_PACE_MIN 0.5
#define BM_AI_PACE_MAX 1.5

enum {
    BM_AI_OK = 0,
    BM_AI_BAD_ARG = 1,               /* no host / out, struct_size below 8 */
    BM_AI_NO_RACER = 2,              /* index past the race's list (outside a race the list is empty) */
    BM_AI_UNAVAILABLE = 3,           /* the racer could not be read / service not verified on this build */
    BM_AI_OUT_OF_RANGE = 4,          /* pace not finite or outside the bounds */
    BM_AI_CONFLICT = 5               /* another requester owns the pace; reset by a non-owner */
};

typedef struct bm_ai_racer {
    uint32_t struct_size;            /* in: the size you have; out: the size filled in */
    uint32_t index;
    uint32_t is_player;              /* 1: a player's car (never changed by pace) */
    uint32_t schedule_column;        /* the column of the pace schedule this racer follows (0..7) */
    uint32_t zone;                   /* the schedule zone the racer is in */
    float speed_cap;                 /* m/s, after pace */
    float target_speed;              /* m/s, the AI's current target (min of its corner plan and the cap) */
    float schedule_offset;           /* s, > 0 ahead of schedule (the game slows it), < 0 behind */
    float car_speed;                 /* m/s */
    float pace_applied;              /* the factor applied to this racer's cap at its last update (1.0 none) */
} bm_ai_racer;                       /* 40 bytes */

typedef struct bm_ai_api {
    uint32_t struct_size;
    uint32_t version;
    uint32_t (TD_CALL *count)(td_host *host);
    int32_t (TD_CALL *get)(td_host *host, uint32_t index, bm_ai_racer *out);
    int32_t (TD_CALL *set_pace)(td_host *host, double pace);
    int32_t (TD_CALL *get_pace)(td_host *host, double *pace);
    int32_t (TD_CALL *reset)(td_host *host);
} bm_ai_api;

#ifdef __cplusplus
}
#endif
#endif
