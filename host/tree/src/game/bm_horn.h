/* bm_horn.h - main21 patch 120 (batch C3-3): the player horn (bm_horn.c). */
#ifndef BM_HORN_H
#define BM_HORN_H
#include <stdint.h>
void bo3_horn_tick(void);             /* hirefresh.c bo3_race_audio: once a race-audio tick, game thread */
int bo3_horn_census(void);            /* 1 = the voice API bytes are the retail ones */
uint32_t bo3_horn_stat(uint32_t which);   /* 0 starts, 1 stops, 2 voices lost to the pool, 3 the voice held now, 4 ticks,
                                            5 no horn sample in the bank at the last press */
void bo3_horn_reset(void);            /* tests */
#endif
