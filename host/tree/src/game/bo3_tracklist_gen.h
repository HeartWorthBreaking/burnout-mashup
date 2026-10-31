/* G8-TL: the host calls the generated code makes for the raised track limits (bm_regions.c, content_count\limits), force-
 * included into the generated sources (BO3_GEN_OPT) after bo3_region4_gen.h. */
#ifndef BO3_TRACKLIST_GEN_H
#define BO3_TRACKLIST_GEN_H
#include <stdint.h>
void bo3_tl_gen_put(uint32_t obj, uint32_t i, uint32_t which, uint32_t v);   /* T1-T3 / T5-T7: Menu A list appends */
uint32_t bo3_tl_gen_get(uint32_t obj, uint32_t i, uint32_t which);           /* T9 / T10: sub_0008CDF0 the selected track */
uint32_t bo3_tl_gen_texts(uint32_t obj);                     /* T11 / T12: the track row's text-ID array (guest VA) */
uint32_t bo3_tl_gen_list_inc(uint32_t obj, uint32_t count, uint32_t site);   /* T4 / T8 / T13-T18: list count + 1 */
uint32_t bo3_tl_gen_flag(uint32_t base, uint32_t i, uint32_t which);         /* T19-T23: flag A / B of track list entry i */
#endif
