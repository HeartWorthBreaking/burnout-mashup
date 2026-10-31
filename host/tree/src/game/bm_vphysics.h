/* bm_vphysics.h - the private "bmashup.vphysics" service (bm_vphysics.c, include/bmashup_vphysics.h). */
#ifndef BO3_BM_VPHYSICS_H
#define BO3_BM_VPHYSICS_H

#include <stdint.h>

#include "bmashup_vphysics.h"

/* Offer the service; subscribe its writer to the "ap_update" mark (player car update), unless debug_autopilot (the
 * mark is then RECOMP_DEBUG=autopilot's: the control stays off, the query works). Before the guest runs. */
void bo3_bm_vphysics_init(int debug_autopilot);
/* After each game update (hirefresh.c, beside the other services): follows the race, restores at a race's end. */
void bo3_bm_vphysics_after_update(void);
/* The car-update part (also called directly by the unit test). */
void bo3_bm_vphysics_car_update(void);
const bm_vphys_api *bo3_bm_vphysics_api(void);

#endif
