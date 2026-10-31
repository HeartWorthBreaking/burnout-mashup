/* GP-CRASH1: the mark the generated code makes (bm_crash.c), force-included into the generated sources (BO3_GEN_OPT). */
#ifndef BO3_CRASH_GEN_H
#define BO3_CRASH_GEN_H
#include <stdint.h>
/* sub_0001EE80 loc_0001EEC1 (eax = junction index from sub_00157720, ebx = results flags): CRASH_RESULT; returns 1 when the
 * index is outside the game's list (the generated line then skips the record write: H1 guard). */
int bo3_cr_gen_junction_record(uint32_t index, uint32_t flags);
#endif
