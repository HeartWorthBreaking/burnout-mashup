/* G8-CC1: the host calls the generated code makes (bm_tracks.c), force-included into the generated sources (BO3_GEN_OPT). */
#ifndef BO3_TRACKS_GEN_H
#define BO3_TRACKS_GEN_H
#include <stdint.h>
void bo3_cc_gen_tlist_loaded(void);                  /* sub_00015F10 loc_00016124: tlist.bin is read */
int bo3_cc_gen_skip(uint32_t site, uint32_t index);  /* 1: the track index is -1: skip the write */
uint32_t bo3_cc_gen_record(uint32_t rec_va);         /* G8-CC1.1 F1: sub_000EAC60's record pointer, -1 -> the stand-in */
/* G8-CC1.2 */
int bo3_cc_gen_best(uint32_t site, uint32_t index, float v);  /* sub_0001BA00 / BAF0: 1 = slot -1: the game must not write */
void bo3_cc_gen_total(uint32_t index, uint32_t add);       /* sub_0001B820: slot -1's total */
int bo3_cc_gen_insert_skip(uint32_t index);                 /* sub_0001EE80: 1 = no shadow: skip the insert */
void bo3_cc_gen_race_end_reset(void);                       /* after sub_0001F680 */
uint32_t bo3_cc_gen_insert_record(uint32_t rec_va);
uint32_t bo3_cc_gen_record_for(uint32_t rec_va, uint32_t id_lo, uint32_t id_hi);   /* G8-CC1.3: the records screen's own track */
void bo3_cc_gen_recorded(void);                   /* the end of sub_0001EE80 */
void bo3_cc_gen_unsupported(uint32_t what);                 /* fail closed (exit 94) */
#endif
