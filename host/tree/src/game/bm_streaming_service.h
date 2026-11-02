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
/* patch 131: the full-detail unit slot size for mod.toml [bmashup.capacity] full_unit_bytes (host internal; the plugin
 * table and its version are unchanged). BM_STREAMING_OK / OUT_OF_RANGE / CLOSED / UNSUPPORTED / BAD_ARG. */
int32_t bo3_bm_streaming_request_full(td_host *host, uint32_t bytes, uint32_t *merged_bytes);
/* The service's table (for the unit test). */
const bm_streaming_api *bo3_bm_streaming_api(void);

#endif
