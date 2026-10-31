# bmashup.camera 2 - chase-camera adjust and finish poses (platform 0.1.9, hook request P2 C1 + P3 C2)

Header: `sdk\include\bmashup_camera.h` (`BM_CAMERA_VERSION 2`). Examples: `bm-camera-roll`, `bm-finish-camera`.
Status: **BUILT, AVAILABLE** (chase adjust: full; finish pose: reduced form); OFFLINE-TESTED; slots decided by probes PR-A2 / PR-D;
accepted by the host in the retail validation races (roll 0.12 rad held; one finish pose accepted) - the effect is too small to judge in still screenshots.

## What version 2 adds (append-only; the FOV scale of version 1 is unchanged)
- `set_adjust(host, bm_camera_adjust *)` / `release_adjust(host)`: a roll / pitch / yaw / offset LEVEL for player 0's chase view
  (|roll| <= 0.35, |pitch|, |yaw| <= 0.17 rad, |offset| <= 2 m, `smoothing_s` 0..1 s exponential). One owner (BUSY / NOT_OWNER).
  Applied to the picture's COPY of the camera matrix (the matrix the game builds for the picture before the frame, the view matrix
  and the frustum are made): nothing of the game's camera state is written. Never in crash / takedown cameras, the front end,
  split screen, or when another camera is active. bmashup.hooks CAMERA_FINAL modifiers may change it per picture.
- `set_finish_poses(host, poses, n)` (REDUCED form on 0.1.9): the game's end-of-race camera is ONE STATIC pose per track and the car
  drives on, so at most ONE authored pose a race (`BM_CAMERA_FINISH_POSES_SERVED` 1; n > 1: OUT_OF_RANGE), RELATIVE TO THE GAME'S OUTRO
  CAMERA (x right, y up, z forward of it), within `BM_CAMERA_FINISH_RADIUS_M` 40 m of it; fov 0.7..1.4; hold 0.5..10 s (checked, not used:
  the pose holds for the whole outro). NOT_IN_RACE outside a one-player race stage; cleared when the stage ends; own owner.
  bmashup.hooks FINISH_CAMERA modifiers may give another pose per picture (same 40 m rule).
- `bm_camera_state` grows to 68 bytes: `chase_active`, `applied_roll_rad`, `adjust_owned`, `adjust_yours`, `finish_active`.
- Results: `BM_CAMERA_WRONG_THREAD` 6 (reserved; every v2 call takes any thread), `BM_CAMERA_NOT_IN_RACE` 7.

## Availability on 0.1.9
Chase camera = the game's camera-dispatch bit 2 alone (probe PR-A2); crash (bit 6), alternative views (4 / 5), intro, pre-race and
outro cameras are never adjusted. End-of-race camera = bit 8 alone (probe PR-D). Both are available on 0.1.9.

## Evidence
`tests\p23\hooks\test_camview.c`: the shipped bits (75 checks: rotation math, orthonormal rows, bounds, ownership, smoothing, the
game camera object untouched, not in crash / another camera / front end / another view, CAMERA_FINAL bounds, one finish pose
anchored on the outro camera for the whole outro, 40 m radius, fov for one picture, cleared at the stage end, real-XBE census +
tamper; mutants 221..230) and the unknown-slot form (22 checks).