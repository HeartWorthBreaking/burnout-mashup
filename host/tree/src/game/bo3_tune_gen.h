/* G8-E3 v1.1: the host call the generated code makes (bm_tune.c), force-included into the generated sources (BO3_GEN_OPT). */
#ifndef BO3_TUNE_GEN_H
#define BO3_TUNE_GEN_H
#include <stdint.h>
void bo3_tune_gen_applied(uint32_t var_va);   /* sub_001AF040 loc_001AF09F, after the ValueDB's 32-bit copy */
/* main21 patch 115 (zackypoo 04 b): sub_0010C5F0 loc_0010CCCE, the end of the one-time Air Ram registration, right after
 * the load of ECX (the object) from [esp + 0x28], wrapped in #if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZAR (recomp_0002.c):
 *     BO3_TUNE_CAD_REGISTERED(ecx);
 * = bm_tune.c takes the game's Air Ram values and applies owned ones. */
void bo3_tune_gen_cad(uint32_t obj);
#define BO3_TUNE_CAD_REGISTERED(obj) bo3_tune_gen_cad((uint32_t)(obj))
/* main21 patch 118 (batch C3-6): sub_00167220 loc_00167296, right after `call sub_00160B90` (the camera block [0x47A134] + 0x2C30
 * registered with the game's code defaults), wrapped in #if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZCC (recomp_0003.c):
 *     BO3_TUNE_CAM_REGISTERED();
 * = bm_tune.c takes the game's camera values and applies owned ones (the only place the host writes that heap block). */
void bo3_tune_gen_cam(void);
#define BO3_TUNE_CAM_REGISTERED() bo3_tune_gen_cam()
/* main21 patch 123 (batch C3-9): sub_00015F10 loc_00015FD5 (after the Global.txd load; the fx tables are filled by then), wrapped in
 * #if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZFX (recomp_0000.c): BO3_TUNE_FX_READY(); = bm_tune.c takes the spark size and applies an owned one */
void bo3_tune_gen_fx(void);
#define BO3_TUNE_FX_READY() bo3_tune_gen_fx()
/* main21 patch 129 (C3-9b, car shadow look): the "Effects/Shadow | ..." rows, each mark wrapped in #if BO3_HOOKREQ_P23 &&
 * BO3_HOOKREQ_ZSH (recomp_0000.c). Every call is the identity while its row is not owned (the game's own bytes / values stay):
 *   sub_00043350 loc_00043350 (entry):            BO3_TUNE_SHADOW_BEGIN();   (a new pass; DEV ZDIAG: the inherited state, once a race)
 *   sub_00043350 loc_000433AC after 0x433B2:      MEM32(0x75D590) = BO3_TUNE_SHADOW_AT(ecx);   (ALPHATESTENABLE value)
 *   sub_00043350 loc_000434C7 after 0x434D2 / 0x434EA: xmm2.f[0] = BO3_TUNE_SHADOW_VSPLIT(0 / 1, xmm2.f[0]);   (v of rows 1 / 2)
 *   sub_00043570 loc_00043570 after 0x4359C:      xmm0.f[0] = BO3_TUNE_SHADOW_OPACITY(xmm0.f[0], MEMF(ebp + 0x10));
 *   sub_00043570 loc_0004382C (before the draw):  BO3_TUNE_SHADOW_SIZE();   (the 8 vertices at 0x54F058)
 *   sub_00043850 loc_00043850 (entry):            BO3_TUNE_SHADOW_END();     (ALPHATESTENABLE back to the game's value, queued) */
void bo3_tune_gen_shadow_begin(void);
uint32_t bo3_tune_gen_shadow_at(uint32_t game);
float bo3_tune_gen_shadow_vsplit(uint32_t which, float game);
float bo3_tune_gen_shadow_opacity(float game, float arg);
void bo3_tune_gen_shadow_size(void);
void bo3_tune_gen_shadow_end(void);
#define BO3_TUNE_SHADOW_BEGIN() bo3_tune_gen_shadow_begin()
#define BO3_TUNE_SHADOW_AT(v) bo3_tune_gen_shadow_at((uint32_t)(v))
#define BO3_TUNE_SHADOW_VSPLIT(w, f) bo3_tune_gen_shadow_vsplit((uint32_t)(w), (f))
#define BO3_TUNE_SHADOW_OPACITY(f, a) bo3_tune_gen_shadow_opacity((f), (a))
#define BO3_TUNE_SHADOW_SIZE() bo3_tune_gen_shadow_size()
#define BO3_TUNE_SHADOW_END() bo3_tune_gen_shadow_end()
#endif
