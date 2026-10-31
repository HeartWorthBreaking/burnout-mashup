/*
 * bm_route_service.h - the private "bmashup.route" service (include/bmashup_route.h, G8-E5): read-only route holders per
 * racer, validated; available while the lifecycle (bm_lifecycle.h) says a race's track is resident.
 */
#ifndef BO3_BM_ROUTE_SERVICE_H
#define BO3_BM_ROUTE_SERVICE_H

#include <stdint.h>

#include "bmashup_route.h"

typedef const uint8_t *(*bo3_route_guest_fn)(void *user, uint32_t va, uint32_t size);

/* The guest accessor (the game's: bo3_route_game_init; tests: their own). */
void bo3_route_configure(bo3_route_guest_fn guest, void *user);
/* Offer the service (bo3_plugins_service), before bo3_plugins_init. */
void bo3_bm_route_init(void);
const bm_route_api *bo3_bm_route_api(void);
/* A lane wrapper back to its lane (exposed for the unit test): 1 and *lane (0..254 or 255 = no lane), or 0 (not a wrapper
 * of a lane the track has). */
int bo3_route_lane_of(uint32_t wrapper, uint32_t lanes, uint32_t *lane);
/* G8-E5s: copy every racer's route now (the lifecycle's race-exit capture, bo3_lc_set_exit_capture; game thread) */
void bo3_route_capture_final(void *user);

#endif
