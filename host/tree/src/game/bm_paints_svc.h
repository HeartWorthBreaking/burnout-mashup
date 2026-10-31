/* bm_paints_svc.h - main19 (platform 0.1.9, hook request P2 item I, patch 31): "bmashup.paints" v1 (include/bmashup_paints.h),
 * the host side. (bm_paints.c is the older garage paint cap; this file is the plugin service.) */
#ifndef BO3_BM_PAINTS_SVC_H
#define BO3_BM_PAINTS_SVC_H

#include <stdint.h>

#include "bmashup_paints.h"

/* probe-pending constants (main19 STATE_C.md; FEASIBILITY I1 / I2) */
#ifndef BM_P23_PAINTS_LIVE_INPLACE
#define BM_P23_PAINTS_LIVE_INPLACE 1   /* PR-A2 (I1) DECIDED (p23_a2, 22 toggles): an edited palette at the SAME guest address is
                                        * shown at once without a re-bind -> 1 (default since patch 41) = one unit edited in place;
                                        * 0 = the two-unit re-bind path of patch 31 */
#endif
#ifndef BM_P23_PAINTS_LAYER_TABLES
#define BM_P23_PAINTS_LAYER_TABLES 0   /* I2: 1 = per-car DECALS / WHEELS tables are verified and compiled in; 0 (default) =
                                        * BODY only (DECALS / WHEELS answer NO_LAYER) */
#endif
#define BM_P23_PAINTS_DYN_INDEX 127u   /* the dynamic paint's index (signed byte: never negative, never >= 128; above every
                                        * registered paint: retail <= 8 + BO3_PAINT_PER_CAR 56 = 64) */

/* the guest sites (FACT: gp\hookreq\p23\SITES_VERIFIED.md s7, re-checked tests\p23\step0_c_out.txt) */
#define BO3_PS_CAR1       0x0073A1D0u   /* player 0's racer (CB3PlayerCar) */
#define BO3_PS_CAR1_VT    0x003B11A0u
#define BO3_PS_PLAYER     0x27D0u       /* racer + 0x27D0 = player index */
#define BO3_PS_POOL       (0x0064B310u + 0x1CB80u)   /* player physics vehicles (bm_vphysics.c s_pools[0]) */
#define BO3_PS_POOL_STRIDE 0x4AD0u
#define BO3_PS_POOL_VT    0x003B1160u
#define BO3_PS_V_RACER    0x13F4u       /* V + 0x13F4 = R */
#define BO3_PS_V_BLOCK    0x13F8u       /* V + 0x13F8 = the physics block (its name = the ValueDB .cfg path) */
#define BO3_PS_V_ENTITY   0xCC0u        /* patch 31 used E = MEM32(V + 0xCC0): WRONG for the renderer (m19_v1a: no colour) */
#define BO3_PS_E_OFF      0x10u         /* patch 41 (FACT p23_a2): the renderer's palette bind (sub_000303D0 loc_00030554, EDI = E)
                                         * sees player 0's car with E = racer 0x73A1D0 + 0x10 */
#define BO3_PS_E_PAINT    0x59u         /* E + 0x59 = the signed palette index the renderer reads (0x3053D) = racer + 0x69 */

typedef uint32_t (*bo3_paints_alloc_fn)(uint32_t size, uint32_t align);

void bo3_bm_paints_svc_init(void);                   /* registers the service (and, P23 on, the ap_update writer) */
void bo3_paints_svc_set_alloc(bo3_paints_alloc_fn a); /* the high-zone allocator (game: xbox_ContiguousAllocHigh) */
/* the renderer's paint >= count path (bm_vpaint.c bo3_veh_gen_palette): the dynamic palette resource, or 0 */
uint32_t bo3_paints_dyn_palette(uint32_t tex, uint32_t paint);
/* main21 patch 74: the WHEELS marks (generated code, the car model draw's wheel loop) and a test counter */
uint32_t bo3_paints_wheels_begin(uint32_t e);
uint32_t bo3_paints_wheels_end(void);
uint32_t bo3_paints_svc_wheel_binds(void);
/* main21 patch 75: the NITRO mark (sub_001871E0, the flame colour) and a test counter */
void bo3_paints_nitro_tint(uint32_t racer, uint32_t out);
uint32_t bo3_paints_svc_nitro_tints(void);
void bo3_paints_svc_tick(void *user);                /* the ap_update writer (game thread) */
void bo3_paints_svc_lifecycle(uint32_t kind);         /* bm_lifecycle.c: LOAD_DONE / RACE_EXIT (game thread) */
const bm_paints_api *bo3_bm_paints_svc_api(void);
void bo3_paints_svc_reset(void);                      /* tests */
int bo3_paints_svc_census(void);                      /* 1: this build's sites match (checked once, lazily) */

#endif
