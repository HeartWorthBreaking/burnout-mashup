/* G8-E1: force-included into the generated sources (BO3_GEN_OPT). Insertions (apply_e1.py), at the R3 probe's verified sites:
 *   sub_001AA990 after EAX is copied to EDI                 BO3_LC_OPEN(edi);
 *   sub_0018B250 after EAX is stored to +0x560 of EDI       BO3_LC_ACQUIRE(eax);
 *   sub_0018B250 after ECX is stored to guest address 0x73A178              BO3_LC_PUBLISH(MEM32(0x73A168), ecx);
 *   sub_001AA100 after 0x17 is stored to +0x144384 of EBP   BO3_LC_LOADED(); */
#ifndef BO3_LIFECYCLE_GEN_H
#define BO3_LIFECYCLE_GEN_H

#include <stdint.h>

void bo3_lc_gen_open(uint32_t world);
void bo3_lc_gen_acquire(uint32_t buffer);
void bo3_lc_gen_publish(uint32_t array, uint32_t lanes);
void bo3_lc_gen_loaded(void);

#define BO3_LC_OPEN(w) bo3_lc_gen_open((uint32_t)(w))
#define BO3_LC_ACQUIRE(b) bo3_lc_gen_acquire((uint32_t)(b))
#define BO3_LC_PUBLISH(a, n) bo3_lc_gen_publish((uint32_t)(a), (uint32_t)(n))
#define BO3_LC_LOADED() bo3_lc_gen_loaded()

#endif
