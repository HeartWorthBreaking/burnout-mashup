/*
 * bm_events_service.h - the private "bmashup.events" service
 * (include/bmashup_events.h, docs/bmashup-events.md) over the engine-point
 * dispatcher (bm_events.h).
 */
#ifndef BO3_BM_EVENTS_SERVICE_H
#define BO3_BM_EVENTS_SERVICE_H

#include "bmashup_events.h"

/* Offer the service (bo3_plugins_service), before bo3_plugins_init and after
 * bo3_bm_autopilot_init (which hooks the car update). */
void bo3_bm_events_init(void);
/* The service's table (for the unit test). */
const bm_events_api *bo3_bm_events_api(void);
/* Version 2 (G8-E1): right after bo3_events_close: nothing is delivered once the process starts to exit. */
void bo3_bm_events_lifecycle_close(void);
/* Version 2: called by bm_lifecycle.c (the game's thread) at a load end / a race exit. */
struct bo3_lc_event;
void bo3_bm_events_deliver_lifecycle(const struct bo3_lc_event *ev);
/* Version 3 (G8-E6): called by bm_takedown.c (the game's thread): TAKEDOWN / WRECK. */
void bo3_bm_events_deliver_game(uint32_t event, uint32_t actor, uint32_t victim, uint32_t kind, uint32_t actor_takedowns);
/* Version 4 (G8-E2): called by bm_boost_award.c (the game's thread): BOOST_AWARD; re-entries counted, not delivered. */
void bo3_bm_events_deliver_boost(uint32_t recipient, uint32_t source, uint32_t site, float amount, float requested,
                                 int modified);
/* Version 5 (G8-E2M): the amount after the BOOST_AWARD modifiers (subscription order, validated, HOST never, no re-entry). */
float bo3_bm_events_modify_boost(uint32_t recipient, uint32_t source, uint32_t site, float requested, int *modified);
uint32_t bo3_bm_events_boost_reentries(void);
/* Version 6 (GP-CRASH1): called by bm_crash.c (the game's thread): CRASH_RESULT. */
typedef struct bo3_bm_crash_result {
    uint32_t junction;              /* 0..99 or BM_EVENT_NO_JUNCTION */
    uint32_t score;
    uint32_t mode;                  /* BM_CRASH_MODE_* */
    char junction_id[16], track_id[16];
} bo3_bm_crash_result;
void bo3_bm_events_deliver_crash(const bo3_bm_crash_result *cr);
/* PLATFORM-HK: one host sink (bmashup.hooks, bm_hooks.c) gets the same occurrences after this service's own subscribers:
 * the lifecycle / TAKEDOWN / WRECK deliveries, the BOOST_AWARD amount (after this service's modifiers; it returns the
 * amount to use and sets *modified when it changed it) and the BOOST_AWARD observers' step. NULL: none. */
typedef struct bo3_bm_events_sink {
    void (*lifecycle)(const struct bo3_lc_event *ev);
    void (*game)(uint32_t event, uint32_t actor, uint32_t victim, uint32_t kind, uint32_t actor_takedowns);
    float (*modify_boost)(uint32_t recipient, uint32_t source, uint32_t site, float requested, float amount, int *modified);
    void (*boost)(uint32_t recipient, uint32_t source, uint32_t site, float amount, float requested, int modified);
    /* main18 (bmashup.hooks v2): CRASH_RESULT, after this service's subscribers. NULL: not passed on. */
    void (*crash)(const bo3_bm_crash_result *cr);
} bo3_bm_events_sink;
void bo3_bm_events_set_sink(const bo3_bm_events_sink *sink);
/* main19 (version 7): the twins of bmashup.hooks v3's points 8 / 10 / 11 / 12. offer: the point's mark is in this run (called by
 * bm_hooks.c bo3_hk_offer_point, before the plugins start; an event not offered answers UNAVAILABLE at subscribe). deliver: one
 * occurrence (proto = event, sequence, step and the event's group), from bmashup.hooks' dispatcher after its MODIFY step. */
void bo3_bm_events_offer_v7(uint32_t event);
int bo3_bm_events_v7_wanted(uint32_t event);
void bo3_bm_events_deliver_v7(const bm_event *proto);

#endif
