/* G8-L9: force-included into the generated sources (BO3_GEN_OPT). Insertions (apply_l9.py):
 *   sub_00015A60, after the unit slots' apply (after sub_00022F60):  BO3_ST_APPLY();
 *   sub_0019AE10 state 0x16, after EDI is loaded from +4 of EBP (the STATIC buffer), before the relocation sub_0019B4E0:
 *                                                                    BO3_ST_CHECK(edi); */
#ifndef BO3_STATIC_GEN_H
#define BO3_STATIC_GEN_H

#include <stdint.h>

void bo3_st_gen_apply(void);
void bo3_st_gen_check(uint32_t buf);

#define BO3_ST_APPLY() bo3_st_gen_apply()
#define BO3_ST_CHECK(buf) bo3_st_gen_check((uint32_t)(buf))

#endif
