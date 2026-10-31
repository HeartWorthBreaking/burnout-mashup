/* main19 (hook request P2, item 27): the marks of bm_evsound.c, force-included into the generated sources (BO3_GEN_OPT via
 * scripts\GEN_EXTRA_B.txt). Insertions in sub_001407B0's takedown-sign branch (recomp_0002.c), each wrapped in #if BO3_HOOKREQ_P23
 * (patch 27_hooks_event_sound):
 *   at loc_0014097C, before the call of sub_00140D30 (EAX = the ladder level 0..4, EBP = the sign event):
 *       eax = BO3_ES_LEVEL(eax, ebp, 0);
 *   at loc_0014099A, before the call of sub_00141150 (the alternate sound, EAX = 0..4):
 *       eax = BO3_ES_LEVEL(eax, ebp, 1);
 * = bmashup.hooks v3 EVENT_SOUND (MODIFY SOUND_LEVEL): the level after the plugins (0..4; anything else keeps the game's). */
#ifndef BO3_EVSOUND_GEN_H
#define BO3_EVSOUND_GEN_H

#include <stdint.h>

uint32_t bo3_es_gen_level(uint32_t level, uint32_t event, uint32_t alt);

#define BO3_ES_LEVEL(l, e, a) bo3_es_gen_level((uint32_t)(l), (uint32_t)(e), (uint32_t)(a))

/* main21 patch 78 (arbitrary pitch): at loc_00140D72 (sub_00140D30) and loc_001411D3 (sub_00141150), [esp] = the pitch slot */
void bo3_es_gen_pitch(uint32_t sp, uint32_t alt);
#define BO3_ES_PITCH(sp, a) bo3_es_gen_pitch((uint32_t)(sp), (uint32_t)(a))

#endif
