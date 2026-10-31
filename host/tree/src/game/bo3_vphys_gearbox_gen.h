/* main19 item 21 (hook request P2 A1, bmashup.vphysics 3 gearbox): force-included into the generated sources (BO3_GEN_OPT,
 * scripts\GEN_EXTRA_A.txt). Insertion (main19 patch 21_vphysics_v3_gearbox, recomp_0002.c):
 *   sub_00121560 at loc_001219E1 (the idle re-shift to neutral: gear = 0, shift flag = edx, timer), first statement:
 *       #if BO3_HOOKREQ_P23
 *       if (BO3_GBX_IDLE_SKIP(esi)) goto loc_0012183F;
 *       #endif
 *   esi = G (the gearbox, physics vehicle + 0x1448). The host answers 1 only while a plugin owns MANUAL on that car and the
 *   gear (G + 0x80) is already 0 (bm_vphysics.c bo3_vphys_gen_idle_skip); every other case runs the retail block. */
#ifndef BO3_VPHYS_GEARBOX_GEN_H
#define BO3_VPHYS_GEARBOX_GEN_H

#include <stdint.h>

int bo3_vphys_gen_idle_skip(uint32_t g);

#define BO3_GBX_IDLE_SKIP(g) bo3_vphys_gen_idle_skip((uint32_t)(g))

#endif
