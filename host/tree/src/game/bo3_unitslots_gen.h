/* G8-L7: force-included into the generated sources (BO3_GEN_OPT). Insertions (apply_l7.py):
 *   sub_00015A60 after the call to sub_00022F60 (the memory manager's init):  BO3_US_APPLY();
 *   sub_0019CBB0 before the low-detail unit read (edx = slot buffer, esi = size):  BO3_US_CHECK(0, edx, esi);
 *   sub_0019CC60 before the full-detail unit read (edx = slot buffer, edi = size): BO3_US_CHECK(1, edx, edi); */
#ifndef BO3_UNITSLOTS_GEN_H
#define BO3_UNITSLOTS_GEN_H

#include <stdint.h>

void bo3_us_gen_apply(void);
void bo3_us_gen_check(int kind, uint32_t buf, uint32_t size);

#define BO3_US_APPLY() bo3_us_gen_apply()
#define BO3_US_CHECK(kind, buf, size) bo3_us_gen_check((kind), (uint32_t)(buf), (uint32_t)(size))

#endif
