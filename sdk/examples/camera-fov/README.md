# (o) camera-fov - bmashup.settings 1 + bmashup.camera 1

`bm_gp_camera_fov.c` = the gp camset1 slice's plugin source, unchanged. It declares one INT setting `fov_scale` ("CAMERA FOV",
70..140 % step 5, default 100) on MODS > MOD SETTINGS and passes every value to `bmashup.camera`'s `set_fov_scale`; the
scale applies from the next one-player race / RESTART. Contract and evidence: `docs\services\SETTINGS.md`, `CAMERA.md`.
