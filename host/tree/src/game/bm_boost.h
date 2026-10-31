/*
 * bm_boost.h - the private "bmashup.boost" service (include/bmashup_boost.h,
 * docs/bmashup-boost.md).
 */
#ifndef BO3_BM_BOOST_H
#define BO3_BM_BOOST_H

#include "bmashup_boost.h"

/* Offer the service to the plugins (bo3_plugins_service), before
 * bo3_plugins_init. debug_autopilot: RECOMP_DEBUG=autopilot holds player 1's
 * car update ("ap_update"), so this service only answers
 * BM_BOOST_DEBUG_AUTOPILOT. It hooks nothing itself: bm_autopilot.c's handler
 * of that mark calls bo3_bm_boost_car_update. Starts from no request. */
void bo3_bm_boost_init(int debug_autopilot);
/* A player car's update is about to run (the "ap_update" mark, g_esi the car),
 * on the game's thread. */
void bo3_bm_boost_car_update(void);
/* After each game update, on the game's thread, after the takedawn.race
 * snapshot and its on_update calls (hirefresh.c bo3_update). */
void bo3_bm_boost_after_update(void);
/* The service's table (for the unit test). */
const bm_boost_api *bo3_bm_boost_api(void);

#endif
