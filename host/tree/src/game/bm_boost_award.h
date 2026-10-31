/* bm_boost_award.h - G8-E2: BOOST_AWARD (bmashup.events v4) from the entry of the game's boost add (bm_boost_award.c). */
#ifndef BO3_BM_BOOST_AWARD_H
#define BO3_BM_BOOST_AWARD_H

#include <stdint.h>

uint32_t bo3_e2_source_of(uint32_t site, float amount);   /* BM_BOOST_* from the call site alone */
uint32_t bo3_e2_recipient_of(uint32_t meter);             /* racer index, or BM_EVENT_NO_RACER */
uint32_t bo3_e2_gen_boost_award(uint32_t ret, uint32_t meter, uint32_t amount_bits);   /* v5: the amount bits to use */

#endif
