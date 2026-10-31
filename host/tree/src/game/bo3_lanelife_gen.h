/* Lane lifetime design "C" (EXPERIMENTAL): force-included into the generated sources (BO3_GEN_OPT=-include ...).
 * The two marks content_count\cross_track\lifetime\scripts\apply_lanelife.py writes into the generated C:
 *   sub_0018BD60 (race-exit route teardown), before ECX is stored to +0x560 of EAX  ->  BO3_LANE_RETAIN(eax);
 *   sub_0018B250 (load ACQUIRE), after EAX is stored to +0x560 of EDI              ->  BO3_LANE_RETAIN_ACQ(edi);
 * Both snapshot the live extension lanes (bm_lanes.c bo3_lanes_retain); neither changes a guest register or flag. */
#ifndef BO3_LANELIFE_GEN_H
#define BO3_LANELIFE_GEN_H

#include <stdint.h>

void bo3_lane_retain_gen(uint32_t route);       /* the race exit: route = eax, route + 0x560 still the slot buffer */
void bo3_lane_retain_acq_gen(uint32_t route);   /* ACQUIRE backup: acts only when the exit was not seen */

#define BO3_LANE_RETAIN(r) bo3_lane_retain_gen((uint32_t)(r))
#define BO3_LANE_RETAIN_ACQ(r) bo3_lane_retain_acq_gen((uint32_t)(r))

#endif
