/* GP-FETEX1: the host calls the generated code makes (bm_fetex.c), force-included into the generated sources (BO3_GEN_OPT).
 * Marks (gp\slices\fetex1\scripts\apply_fetex.py; TRACE.md s4): N1 sub_0002DDF0 miss path; S the 26 dynamic reads of the
 * front-end slot table 0x464418; T1 sub_00074750 ticker IDs 0xEA..0xEC; T2 the two place-name reads of 0x39F9B0. */
#ifndef BO3_FETEX_GEN_H
#define BO3_FETEX_GEN_H
#include <stdint.h>
uint32_t bo3_fetex_gen_miss(uint32_t dict, uint32_t name_va);
uint32_t bo3_fetex_gen_slot(uint32_t slot, uint32_t retail);
uint32_t bo3_fetex_gen_text(uint32_t kind, uint32_t dflt);
uint32_t bo3_fetex_gen_global(uint32_t dict);   /* main21 patch 121: sub_00015F10 loc_00015FD5 (BO3_HOOKREQ_ZGT) */
#endif
