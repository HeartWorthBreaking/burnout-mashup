/* GP-WT4: the host calls the generated code makes (bm_wt4.c), force-included into the generated sources (BO3_GEN_OPT).
 * Marks (gp\slices\wt4\scripts\apply_wt4.py; gp\atlas\WORLDTOUR.md s6): region page G1 sub_00074940 loc_00074AC2, G2 sub_00074940
 * loc_00074B6C, G3 sub_00074C60 loc_00074D06 and loc_000751A3 (both entry-widget creations), G4 sub_00074C60 loc_00074C82, G5 loc_00074E90, G6 loc_00074EB5, G7 sub_00158920
 * entry, G8 loc_00074EE1, G9 loc_00074B8F; map page M1 sub_000D8530 (region argument), M2 eight location-count switches
 * (sub_000D8400 / D84D0 / D8530 x2 / DA0B0 / DA910 / DAC70 / E2480), M3 sub_000D80E0 loc_000D8151, M4 sub_000D6D20
 * loc_000D6E1A, M5 sub_000D8530 loc_000D86FD, M6 sub_000D8400 loc_000D84B3; textures T sub_000D8530 x3, sub_000DDCF0 x4,
 * sub_000DE220 x1. */
#ifndef BO3_WT4_GEN_H
#define BO3_WT4_GEN_H
#include <stdint.h>
uint32_t bo3_wt4_gen_enter(uint32_t region, uint32_t mode);
void bo3_wt4_gen_regions(uint32_t state);
uint32_t bo3_wt4_gen_entries(uint32_t entries);
uint32_t bo3_wt4_gen_page_region(uint32_t region, uint32_t page);
uint32_t bo3_wt4_gen_right(uint32_t wrapped, uint32_t next);
uint32_t bo3_wt4_gen_left(uint32_t wrapped);
int bo3_wt4_gen_avail(uint32_t region);
uint32_t bo3_wt4_gen_globe(uint32_t region);
uint32_t bo3_wt4_gen_map(uint32_t region);
uint32_t bo3_wt4_gen_count(uint32_t count);
int bo3_wt4_gen_suppress(void);
int bo3_wt4_gen_focus(uint32_t menu, uint32_t arg);
uint32_t bo3_wt4_gen_marker(uint32_t state, uint32_t loc);
uint32_t bo3_wt4_gen_tex(uint32_t region);
#endif
