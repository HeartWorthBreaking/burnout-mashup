/* bo3_veh_gen.h - GP-VEH1: the calls the generated code makes (bm_veh.c, bm_vpaint.c). Included into every generated file
 * through BO3_GEN_OPT (-include). Every call answers the game's own value when no mod declared the feature it serves. */
#ifndef BO3_VEH_GEN_H
#define BO3_VEH_GEN_H
#include <stdint.h>

/* ---- vlist2: the vehicle list the game reads (0x4D2000, capacity 128, or the relocated image) ---- */
uint32_t bo3_vl_base(void);                       /* 0x4D2000 or the relocated image */
uint32_t bo3_vl_cap(void);                        /* 128 or its capacity */
uint32_t bo3_vl_ids(void);                        /* base + the ID array offset */
uint32_t bo3_vl_fa(void);                         /* base + the flag-A array offset */
uint32_t bo3_vl_vd(void);                         /* base + the value-D array offset */
/* the offset of a retail array offset (0x008 / 0x208 / 0x408 / 0x808 / 0xA08) in the image self: unchanged unless self is the
 * relocated image (the track list shares sub_001575A0 and keeps its own layout) */
uint32_t bo3_vl_off(uint32_t self, uint32_t retail_off);

/* ---- series / progression / AI / model alias ---- */
uint32_t bo3_veh_gen_class(uint32_t cls, uint32_t lo, uint32_t hi);    /* sub_00157300 tail: 9 -> a series code */
int bo3_veh_gen_can_right(uint32_t list, uint32_t *al);                /* sub_000BDF10: 1 = answered in *al */
uint32_t bo3_veh_gen_series_step(uint32_t list, uint32_t cur, int dir);  /* sub_000BE070 (+1) / sub_000BE0D0 (-1) */
uint32_t bo3_veh_gen_series_text(uint32_t cls);                        /* sub_000BCEF0 for a code >= 10 */
uint32_t bo3_veh_gen_open(uint32_t lo, uint32_t hi);                   /* the game's "-1 -> open" sites: 1 / 0 */
int bo3_veh_gen_ai_pick(uint32_t esp_va, uint32_t *lo, uint32_t *hi);  /* sub_00060120 entry: 1 = picked */
uint64_t bo3_veh_gen_path_id(uint32_t lo, uint32_t hi);                /* sub_00157210: model = donor -> the donor's ID */
void bo3_veh_gen_rows(uint32_t list);                                  /* after a garage rows build: paint restore */

/* ---- paints ---- */
uint32_t bo3_veh_gen_paint_bound(uint32_t rec, uint32_t tex, uint32_t cnt);    /* sub_0018D0E0 clamp */
uint32_t bo3_veh_gen_palette(uint32_t tex, uint32_t paint);                     /* sub_000303D0 paint >= count */
uint32_t bo3_paints_wheels_begin(uint32_t e);   /* main21 patch 74: sub_000303D0 wheel loop start: the wheel palette or 0 */
uint32_t bo3_paints_wheels_end(void);            /* ... its end: the car palette to bind again or 0 */
void bo3_paints_nitro_tint(uint32_t racer, uint32_t out);   /* main21 patch 75: sub_001871E0 after the flame colour */
uint32_t bo3_veh_gen_paint_next(uint32_t list, uint32_t retail_next, uint32_t d);   /* sub_000BE140 (d = its divisor) */
uint32_t bo3_veh_gen_photo_paint(uint32_t list, uint32_t retail);               /* sub_000BE1B0 */
uint32_t bo3_veh_gen_photo_row(uint32_t row, uint32_t retail);                 /* sub_000BCBA0 at 0xBCCE7 (p4.3 fix 1) */
uint32_t bo3_veh_gen_photo_palette(uint32_t photo, uint32_t paint, uint32_t widget);   /* sub_000F9410 */
uint32_t bo3_veh_gen_paint_confirm(uint32_t row, uint32_t retail);              /* sub_000BEB10 */
uint32_t bo3_veh_gen_paint_anim(uint32_t list, uint32_t r);                     /* sub_000BEB10 states 3 / 4 */
#endif
