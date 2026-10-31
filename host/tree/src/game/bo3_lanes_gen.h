/* G8-L4 EXPERIMENTAL: force-included into the TRANSFORMED generated sources only (BO3_GEN_OPT=-include ...).
 * The entry points the lane transformation (l4\scripts\lane_xform_v4.py) writes into the generated C. */
#ifndef BO3_LANES_GEN_H
#define BO3_LANES_GEN_H

#include <stdint.h>

uint32_t bo3_lane_w(uint32_t index);                            /* an index: the rule, else 0x60EA2C + 8 i   */
uint32_t bo3_lane_w8(uint32_t x);                               /* a scaled index x = 8 i                    */
uint32_t bo3_lane_load_gen(uint32_t index, uint32_t lane_count); /* the loader: store address, or 0 = refused */

#define BO3_LANE_W(i) bo3_lane_w((uint32_t)(i))
#define BO3_LANE_W8(x) bo3_lane_w8((uint32_t)(x))
#define BO3_LANE_LOAD(i, n) bo3_lane_load_gen((uint32_t)(i), (uint32_t)(n))

#endif
