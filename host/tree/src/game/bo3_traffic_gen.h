/* gp slice traffic1: the host call the generated code makes (bm_traffic.c), force-included into the generated sources
 * (BO3_GEN_OPT). */
#ifndef BO3_TRAFFIC_GEN_H
#define BO3_TRAFFIC_GEN_H
#include <stdint.h>
void bo3_tr_gen_init(uint32_t traffic);   /* sub_001A13F0 (eax = T) and sub_001A28B0 ([esp+4] = T) entries */
void bo3_tr_gen_seed(uint32_t traffic);   /* main21 P5a: loc_001A1A1F after the traffic reset (esi = T) */
void bo3_tr_gen_update(uint32_t traffic); /* main21 P5b: loc_001A2567 in the traffic update, after the induce pass (ebx = T) */
void bo3_tr_gen_preload(uint32_t traffic);   /* main21 patch 109: sub_001A3AE0 loc_001A3E61, the trigger machine's exit (ebp = T) */
void bo3_tr_gen_park(uint32_t traffic);   /* main21 C3-4: sub_001A20F0 loc_001A264F, after the vehicle loop (ebx = T): parked cars */
float bo3_tr_gen_section(float e);         /* main21 P5c: sub_001A6070 loc_001A61C1, the cars expected in a lane section */
float bo3_tr_gen_place(float game_pos, float i, float rand_spacing, float spacing);   /* P5c: loc_001A62A4, car i's position */
void bo3_tr_dev_time(uint32_t edge);       /* main21 patch 90, DEV ONLY (BO3_DEV_TRPROBE): the per-vehicle loop's timer marks */
void bo3_tr_dev_wreck(uint32_t m, uint32_t esp);   /* main21 patch 92, DEV ONLY: sub_00114910 entry (ECX = M, [esp] = return) */
void bo3_tr_dev_crash(uint32_t veh, uint32_t esp); /* main21 patch 97, DEV ONLY: sub_0011FC60 entry (ECX = the vehicle) */
/* main21 patch 100, DEV ONLY (BO3_DEV_PROPPROBE): Road Rage prop bodies made (sub_00110420) / removed (sub_00111850) */
void bo3_pp_dev_gate(uint32_t t, uint32_t answer);  /* loc_001108EC after patch 80: T = ebx, the final mode answer */
void bo3_pp_dev_path(uint32_t path);                /* 1 = loc_0011094B, 2 = loc_001109B3 */
void bo3_pp_dev_limit(uint32_t limit);              /* loc_001109BF: edi, the unit loop limit */
void bo3_pp_dev_made(uint32_t t);                   /* loc_00110A9D: the count after the prop loop */
void bo3_pp_dev_rm_begin(uint32_t t, uint32_t esp); /* sub_00111850 entry: T = esi, [esp] = the return */
void bo3_pp_dev_rm_one(uint32_t rec);               /* loc_0011188D: one body removed, kind = byte [rec] */
void bo3_pp_dev_rm_end(uint32_t t);                 /* loc_00111A7F: the single exit */
void bo3_pp_dev_stats(uint32_t out[14]);            /* tests: builds, made, path, limit, build lines, rm lines, kinds 0..6, other */
#endif
