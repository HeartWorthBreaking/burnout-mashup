/* bm_takedown.h - G8-E6 EXPERIMENTAL: TAKEDOWN / WRECK for bmashup.events version 3 (bm_takedown.c). */
#ifndef BO3_BM_TAKEDOWN_H
#define BO3_BM_TAKEDOWN_H

#include <stddef.h>
#include <stdint.h>

#include "bmashup_events.h"
#include "bo3_takedown_gen.h"

uint32_t bo3_e6_racer_index(uint32_t car);       /* the race's list position, or BM_EVENT_NO_RACER */
uint32_t bo3_e6_stats(uint32_t which);           /* 0 takedowns, 1 wrecks, 2 unknown kinds, 3 unpaired marks */
/* main19 (item 39): a host tap called after each new WRECK's delivery (game thread), car = the racer object, idx = its race-list
 * index; NULL = none. Set by bm_contact.c (the WRECK_CAUSE credit window). */
extern void (*bo3_e6_wreck_tap)(uint32_t car, uint32_t idx);

#endif
