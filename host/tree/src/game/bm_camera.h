/*
 * bm_camera.h - "bmashup.camera" (include/bmashup_camera.h), version 1: the host side (gp slice camset1).
 *
 * The one-player camera set-up sub_0002F380 loads a field-of-view factor (16:9: 0x3B1768 = 1.2, after
 * display.ultrawide's patch; 4:3: 0x3B168C = 1.0) and, at loc_0002F3DB where both paths meet, the generated code
 * calls bo3_cam_gen_fov (bo3_camera_gen.h) with it, the viewport aspect the set-up will store (its stack slot
 * [esp + 0x20]) and the widescreen byte ([edi + 0xD]). The value it returns is what the set-up stores at the view
 * record's +0x100 (and hands on). main.c's display.ultrawide marks tell when a stage is set up (uw_stage_setup, the
 * stage set-up functions' entries) and when the front end sets its camera up (uw_fe_setup): bo3_cam_stage_setup /
 * bo3_cam_fe_setup. The scale applies only between a stage set-up and the next front-end set-up.
 */
#ifndef BO3_BM_CAMERA_H
#define BO3_BM_CAMERA_H

#include <stdint.h>

#include "bmashup_camera.h"

void bo3_bm_camera_init(void);                      /* offers the service (before bo3_plugins_init) */
const bm_camera_api *bo3_bm_camera_api(void);
void bo3_cam_stage_setup(void);                     /* uw_stage_setup (game thread) */
void bo3_cam_fe_setup(void);                        /* uw_fe_setup (game thread) */
float bo3_cam_gen_fov(float fov, float aspect, uint32_t wide);   /* the generated line (game thread) */

/* main19 (version 2): the v2 calls are served by bm_camview.c (the view-copy mark), which registers its operations at its
 * init; without them (a unit-test build, BO3_HOOKREQ_P23=0, a failed census) the v2 calls answer BM_CAMERA_UNAVAILABLE and
 * the v2 state fields stay 0. */
typedef struct bo3_cam_v2_ops {
    int32_t (*set_adjust)(td_host *host, const bm_camera_adjust *a);
    int32_t (*release_adjust)(td_host *host);
    void (*fill_state)(td_host *host, bm_camera_state *s);      /* the v2 fields of s */
    int32_t (*set_finish_poses)(td_host *host, const bm_camera_pose *p, uint32_t n);   /* item 29 */
    int32_t (*set_free_pose)(td_host *host, const bm_camera_free *f);                  /* main21 patch 82 (v3) */
    int32_t (*release_free)(td_host *host);
} bo3_cam_v2_ops;
void bo3_cam_set_v2(const bo3_cam_v2_ops *ops);
int bo3_cam_stage_active(void);                     /* 1: a one-player stage is set up (no front-end set-up since) */
int bo3_cam_crash_camera(void);                     /* player 1's crash-camera byte (0 outside a stage / no reader) */
/* bm_camview.c: after bo3_bm_camera_init and bo3_bm_hooks_init (census, ops, CAMERA_FINAL offer); the rotation (tests) */
void bo3_camview_init(void);
void bo3_camview_apply(float m[16], float roll, float pitch, float yaw, const float off[3]);
void bo3_camview_reset_for_tests(double (*clock_fn)(void));
uint32_t bo3_camview_written(void);

/* tests */
void bo3_cam_reset_for_tests(int available);
void bo3_cam_set_crash_reader(int (*fn)(void));     /* player 1's crash-camera byte; NULL: 0 */

#endif
