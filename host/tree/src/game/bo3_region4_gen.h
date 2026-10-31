/* G8-RG4: the host calls the generated code makes for a declared fourth region (bm_regions.c), force-included into the
 * generated sources (BO3_GEN_OPT). bo3_rg_gen_code itself is declared in bo3_regions_gen.h (G8-RG1). */
#ifndef BO3_REGION4_GEN_H
#define BO3_REGION4_GEN_H
#include <stdint.h>
void bo3_rg_gen_menu_regions(uint32_t obj, uint32_t menu);   /* M1 sub_0008C920 loc_0008CB43: append declared regions */
uint32_t bo3_rg_gen_menu_code(uint32_t obj, uint32_t i);     /* M2 / M6: the region code of row entry i */
uint32_t bo3_rg_gen_menu_texts(uint32_t obj);                /* M4 / M5: the region row's text-ID array (guest VA) */
uint32_t bo3_rg_gen_dj(uint32_t code);                       /* M10 sub_00155060: the DJ bank name pointer of a code */
#endif
