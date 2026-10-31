/* G8-WT1: the host calls the generated code makes (bm_wtour.c), force-included into the generated sources (BO3_GEN_OPT).
 * Marks (content_count\events\WORLD_TOUR_TRACE.md s3; apply_wt.py): W1 sub_00015F10 loc_00016196, W2 sub_000D80E0
 * loc_000D831C, W3 sub_000D6D20 loc_000D7030, W4 sub_000D6D20 loc_000D71DF, W5 sub_0005EBE0 loc_0005EBE0, W6 sub_00066C40
 * loc_00066CBD; G8-WT2: W8 sub_0018B250 loc_0018B3BF (the track Gamedata header's race-ID lookup, miss path); platform EV
 * (platform\content\scripts\apply_ev.py): W9 sub_000E27E0 loc_000E280B (the list's race-ID read follows the cursor's host
 * row). */
#ifndef BO3_WTOUR_GEN_H
#define BO3_WTOUR_GEN_H
#include <stdint.h>
void bo3_wt_gen_prg_loaded(void);                                                   /* W1: after the 7 -> 6 cut */
void bo3_wt_gen_loc(uint32_t menu, uint32_t region, uint32_t loc, uint32_t value);  /* W2: a race location's counts */
int bo3_wt_gen_row(uint32_t item, uint32_t row, uint32_t esp);                      /* W3: 1 = the host row was made */
uint32_t bo3_wt_gen_icon(uint32_t item, uint32_t medal);                            /* W4: item -1's medal */
uint32_t bo3_wt_gen_stage(uint32_t race);                                           /* W5: the host stage record or 0 */
void bo3_wt_gen_launch(uint32_t lo, uint32_t hi);                                   /* W6: fail closed */
uint32_t bo3_wt_gen_gd_key(uint32_t hdr, uint32_t lo, uint32_t hi, uint32_t off);    /* W8 (G8-WT2): sub_0018B250's race-ID miss */
void bo3_wt_gen_cell(uint32_t item);                                                /* W9 (EV): the cursor's host row -> the cell */
uint32_t bo3_wt_gen_help(uint32_t text);                                            /* W7 (P3): sub_00074750 loc_0007486A, the help bar */
#endif
