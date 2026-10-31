/* main19 (hook request P2 / P3, items 28 / 29): the marks of bm_camview.c, force-included into the generated sources
 * (BO3_GEN_OPT via scripts\GEN_EXTRA_B.txt). Insertions in sub_001C8A60 (the view build of a picture; recomp_0004.c), each
 * wrapped in #if BO3_HOOKREQ_P23:
 *   item 28: at loc_001C8A7E, before `xmm0 = XMM_MEM(eax);` (sub_00013E50 just built the picture's camera matrix from the
 *   game camera EDI + 0x68 into the stack copy at EAX; the function copies it into the camera frame and makes the view matrix
 *   and the frustum from it):
 *       BO3_CAM_VIEW_COPY(edi, eax);
 *     = the chase-camera adjust / CAMERA_FINAL (and, item 29, a finish pose) written into that COPY only.
 *   item 29: at loc_001C8B47, after the field-of-view angle (XMM0 lane 0) is stored to [esp + 0x18] (the angle the function is about to take
 *   the tangent of, made from the game camera's + 0x10), before the fld:
 *       MEMF(esp + 0x18) = BO3_CAM_FOV_SCALE(MEMF(esp + 0x18));
 *     = the finish pose's fov_scale for this picture (1 otherwise: the game's value returned unchanged). */
#ifndef BO3_CAMVIEW_GEN_H
#define BO3_CAMVIEW_GEN_H

#include <stdint.h>

void bo3_cam_gen_view_copy(uint32_t view, uint32_t mat);

#define BO3_CAM_VIEW_COPY(v, m) bo3_cam_gen_view_copy((uint32_t)(v), (uint32_t)(m))

float bo3_cam_gen_fov_scale(float angle);

#define BO3_CAM_FOV_SCALE(a) bo3_cam_gen_fov_scale((float)(a))

#endif
