/*
 * bm_autopilot.h - the private "bmashup.autopilot" service
 * (include/bmashup_autopilot.h, docs/bmashup-autopilot.md).
 */
#ifndef BO3_BM_AUTOPILOT_H
#define BO3_BM_AUTOPILOT_H

#include <stdint.h>

#include "bmashup_autopilot.h"

/* Offer the service to the plugins (bo3_plugins_service), before
 * bo3_plugins_init, and hook player 1's car update ("ap_update"), unless
 * RECOMP_DEBUG=autopilot is on (debug_autopilot): then that one drives and
 * this service only answers BM_AP_DEBUG_AUTOPILOT. Starts from no request. */
void bo3_bm_autopilot_init(int debug_autopilot);
/* After each game update, on the game's thread, after the takedawn.race
 * snapshot and its on_update calls (hirefresh.c bo3_update). */
void bo3_bm_autopilot_after_update(void);
/* The service's table (for the unit test). */
const bm_autopilot_api *bo3_bm_autopilot_api(void);
/* The engine-point dispatcher's id of player cars' update mark ("ap_update",
 * bm_events.h), or -1 while it is not hooked (RECOMP_DEBUG=autopilot). */
int bo3_bm_car_update_mark(void);
/* For the unit test: takeovers applied again in this race (the title had
 * dropped it), and whether the "stalled" line was given. */
unsigned bo3_bm_autopilot_retakes(void);
int bo3_bm_autopilot_stalled(void);
/* For the unit test: "result" lines given (one per engaged race that finished). */
unsigned bo3_bm_autopilot_results(void);
/* Version 2 (gp I4): the track lifecycle (bm_lifecycle.c, the game's thread,
 * before bmashup.events delivers it): kind BO3_LC_EV_LOAD_DONE / RACE_EXIT,
 * load_kind BO3_LC_LD_*. A request or takeover never outlives a load end or
 * a race exit; a takeover is accepted only after a TRACK or RESTART load and
 * before the next race exit. Each event logs a read-only census of player 1's
 * car (what the title reset). */
void bo3_bm_autopilot_lifecycle(uint32_t kind, uint32_t load_kind);
/* For the unit test: census lines given; releases done (the hand-back). */
unsigned bo3_bm_autopilot_censuses(void);
unsigned bo3_bm_autopilot_releases(void);

#endif
