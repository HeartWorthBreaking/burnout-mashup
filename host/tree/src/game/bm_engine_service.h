/*
 * bm_engine_service.h - the private "bmashup.engine" service
 * (include/bmashup_engine.h): plugins request the AI route-lane capacity of
 * the lane extension (bm_lanes.h) while they start; it is fixed afterwards.
 */
#ifndef BO3_BM_ENGINE_SERVICE_H
#define BO3_BM_ENGINE_SERVICE_H

#include "bmashup_engine.h"

/* Offer the service (bo3_plugins_service), before bo3_plugins_init and after
 * bo3_lanes_game_init (which gives the lane extension its build check). */
void bo3_bm_engine_init(void);
/* Right after bo3_plugins_init: no more requests; the merged capacity is
 * handed to the lane extension (bo3_lanes_set_entries) and logged. Once. */
void bo3_bm_engine_close(void);
/* The service's table (for the unit test). */
const bm_engine_api *bo3_bm_engine_api(void);

#endif
