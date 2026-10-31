/* capfix1 (capdbg T1): force-included into the generated sources (BO3_GEN_OPT). Insertion (slices\capfix1\scripts\apply_capfix1.py):
 *   sub_001AE200 at loc_001AE26F, after EAX is loaded from +0x28 of EDI and before EDI is set to EAX + EDX * 8:
 *       if (BO3_CHEV_SKIP(edi, edx)) goto loc_001AE289;
 *   (edi = the STATIC base [0x7397B4], edx = the camera unit's s8 +0x7D chevron index; see bm_chevron.h) */
#ifndef BO3_CHEVRON_GEN_H
#define BO3_CHEVRON_GEN_H

#include <stdint.h>

int bo3_chev_gen_skip(uint32_t st, uint32_t z);

#define BO3_CHEV_SKIP(st, z) bo3_chev_gen_skip((uint32_t)(st), (uint32_t)(z))

#endif
