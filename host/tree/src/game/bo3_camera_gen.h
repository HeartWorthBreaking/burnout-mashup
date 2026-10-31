/* bo3_camera_gen.h - gp slice camset1: the one call the generated code makes for bmashup.camera (bm_camera.h), in
 * sub_0002F380 at loc_0002F3DB: the field-of-view factor the one-player camera set-up is about to store. Included into
 * every generated file through BO3_GEN_OPT (-include), like the other *_gen.h. */
#ifndef BO3_CAMERA_GEN_H
#define BO3_CAMERA_GEN_H
#include <stdint.h>
float bo3_cam_gen_fov(float fov, float aspect, uint32_t wide);
#endif
