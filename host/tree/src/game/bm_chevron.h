/* Burnout Mashup host hardening (capdbg T1, slice capfix1; not a service, no plugin API).
 *
 * The game's chevron draw sub_001AE200 takes z = s8 [camera full unit block + 0x7D] and, for z >= 0, draws chevron entry
 * [STATIC + 0x28] + 8 * z (sub_0019B1B0: s16 model count, u32 models) WITHOUT checking z against the chevron set's count
 * s16 [STATIC + 0x1E]. Every retail track has z < count (37 / 37). Tracks built by trackbuild <= 0.2.0 have an EMPTY chevron set
 * and z = 0, so entry 0 is the following structure (the relocated per-unit pointer table): its low 16 bits become the model
 * count, positive or negative depending on the STATIC pool base -> with a relocated pool (bmashup.streaming STATIC request)
 * thousands of garbage models are drawn and the game faults (rc_onb_1 / 1b, guest read 0xBC6BC094).
 *
 * The guard (mark in sub_001AE200 at 0x001AE26F, before `edi = eax + edx * 8`): skip the chevron draw when z is outside the
 * set (z < 0 or z >= count) or the STATIC header is unreadable. The skip path is the one the game takes after the draw
 * (loc_001AE289; sub_0019B1B0 is `ret 4`, so the stack is the same), i.e. exactly what a 0-model entry does. In-set indices
 * (every retail track) are unchanged. */
#ifndef BM_CHEVRON_H
#define BM_CHEVRON_H

#include <stdint.h>

#define BO3_CHEV_COUNT_OFF 0x1Eu       /* s16 chevron set count in the STATIC header (trackconv b3static SET_COUNT[0x28]) */

int bo3_chev_skip(uint32_t st, int32_t z);   /* 1 = skip the draw */
uint32_t bo3_chev_skips(void);               /* skips so far (tests / diagnostics) */
int bo3_chev_gen_skip(uint32_t st, uint32_t z);

#endif
