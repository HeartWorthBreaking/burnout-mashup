/*
 * bm_streaming_service.h - the private "bmashup.streaming" service
 * (include/bmashup_streaming.h): plugins request the low-detail unit slot size
 * of the slot extension (bm_unitslots.h) while they start; it is fixed afterwards.
 */
#ifndef BO3_BM_STREAMING_SERVICE_H
#define BO3_BM_STREAMING_SERVICE_H

#include "bmashup_streaming.h"

/* Offer the service (bo3_plugins_service), before bo3_plugins_init and after
 * bo3_us_game_init (which gives the slot extension its build check). */
void bo3_bm_streaming_init(void);
/* Right after bo3_plugins_init: no more requests; the merged size is handed to
 * the slot extension (bo3_us_set_low_bytes) and logged. Once. */
void bo3_bm_streaming_close(void);
/* The service's table (for the unit test). */
const bm_streaming_api *bo3_bm_streaming_api(void);

#endif
