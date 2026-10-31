/* G8-NM1: the host calls the generated code makes (bm_names.c), force-included into the generated sources (BO3_GEN_OPT). */
#ifndef BO3_NAMES_GEN_H
#define BO3_NAMES_GEN_H
#include <stdint.h>
void bo3_nm_gen_table_ready(void);                                                   /* after the language table's relocation */
uint32_t bo3_nm_gen_text(uint32_t dflt, uint32_t kind, uint32_t lo, uint32_t hi);    /* a fallback text ID -> the track's own */
void bo3_nm_gen_note(uint32_t lo, uint32_t hi);                                      /* sub_00081BB0: the track shown */
uint32_t bo3_nm_gen_text_noted(uint32_t id, uint32_t kind);                          /* sub_00081BB0: its location ID */
#endif
