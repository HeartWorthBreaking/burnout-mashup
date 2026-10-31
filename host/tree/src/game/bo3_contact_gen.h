/* main19 (hook request P2, item 26): the marks of bm_contact.c, force-included into the generated sources (BO3_GEN_OPT via
 * scripts\GEN_EXTRA_B.txt). Insertions (each wrapped in #if BO3_HOOKREQ_P23; patch 26_hooks_contact_credit):
 *   sub_00112E70 (recomp_0002.c) at loc_001133CB, after `xmm0 = XMM_MEM(esp + 0x50);`, before
 *   the branch to loc_001133E9 taken when the closing metric is not above the fatal threshold (the comiss of the closing metric against the fatal threshold):
 *       if (_fca > _fcb && MEM8(esp + 0x1A) && BO3_CT_CONTACT(MEM32(ebp + 0xC), ebx, _fca, _fcb)) goto loc_001133E9;
 *     = TRAFFIC_CONTACT: 1 (NO_CRASH) takes the game's own non-fatal branch ([esp+0x1B] stays 1 -> loc_0011340C push response).
 *   sub_00198E60 (recomp_0003.c) at loc_00198E81 (the takedown is about to be counted; the once-per-wreck latch +0x15D6 passed),
 *   before the G8-E6 mark `bo3_e6_gen_takedown_begin(...)`:
 *       BO3_CT_WRECK_CAUSE(edi, MEM32(esi + 0xC8));
 *     = WRECK_CAUSE (OBSERVE): victim R (EDI), aggressor R (the aggressor score object's +0xC8). */
#ifndef BO3_CONTACT_GEN_H
#define BO3_CONTACT_GEN_H

#include <stdint.h>

int bo3_ct_gen_contact(uint32_t rec, uint32_t body_a, double metric, double threshold);
void bo3_ct_gen_wreck_cause(uint32_t victim, uint32_t aggressor);

#define BO3_CT_CONTACT(rec, a, m, t) bo3_ct_gen_contact((uint32_t)(rec), (uint32_t)(a), (double)(m), (double)(t))
#define BO3_CT_WRECK_CAUSE(v, a) bo3_ct_gen_wreck_cause((uint32_t)(v), (uint32_t)(a))

/* main21 patch 79 (contact push scaling): sub_00112E70 right after `xmm0 *= 100` (0x1134BB), the push force magnitude */
float bo3_ct_gen_push(uint32_t rec, float f);
#define BO3_CT_PUSH(rec, f) bo3_ct_gen_push((uint32_t)(rec), (float)(f))

/* main21 patch 110 (R20 fix): sub_00112E70 loc_001133E9 - clears the class-pair crash byte [esp + 0x1A] of an accepted NO_CRASH */
void bo3_ct_gen_nocrash(uint32_t rec, uint32_t sp);
#define BO3_CT_NOCRASH(rec, sp) bo3_ct_gen_nocrash((uint32_t)(rec), (uint32_t)(sp))

#endif
