/* bm_crash.h - GP-CRASH1 EXPERIMENTAL: "bmashup.crash" v1 (read-only Crash junction queries, the last Crash result) and the
 * bmashup.events v6 CRASH_RESULT source + H1 guard at sub_0001EE80 (bm_crash.c). */
#ifndef BO3_BM_CRASH_H
#define BO3_BM_CRASH_H

#include <stdint.h>

#include "bmashup_crash.h"
#include "bo3_crash_gen.h"

void bo3_bm_crash_init(void);                            /* offer the service (main.c, after bmashup.racers) */
const bm_crash_api *bo3_bm_crash_api(void);              /* for the tests */
void bo3_cr_decode(uint64_t v, char out[16]);            /* 64-bit base-40 -> 12-character ID */
void bo3_cr_track_of(const char *id, char out[16]);      /* "1G0000USC3V1" -> "US_C3_V1" */
uint32_t bo3_cr_stats(uint32_t which);                   /* 0 results, 1 skipped record writes (H1) */

#endif
