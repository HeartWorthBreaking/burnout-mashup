# bmashup.hooks 3 - points 8..13 (platform 0.1.9, hook request P2 / P3)

Header: `sdk\include\bmashup_hooks.h` (`BM_HOOKS_VERSION 3`, `BM_HOOKS_VERSION_3`). Examples: `bm-takedown-pitch`,
`bm-contact-no-crash`, `bm-hud-rpm-meter` (HUD_PASS). Status: **BUILT, offline-tested and run in the retail game**: HUD_PASS, WRECK_CAUSE observe and MODIFY (the context carries the aggressor and
`credit_racer`), the camera points and the sound / contact registrations ran without fault. Not seen at runtime: a NO_CRASH-eligible
contact, the sound level firing count.

## What version 3 adds
| point | name | roles | output | available on 0.1.9 |
|---|---|---|---|---|
| 8 | HUD_PASS | OBSERVE | - | YES (once a picture while player 0's race HUD is drawn; bmashup.hud draw() is taken only here) |
| 9 | CAMERA_FINAL | OBSERVE, MODIFY | CAMERA_ADJUST (roll / pitch / yaw / offset; the total \|roll\| <= 0.35, \|pitch\|, \|yaw\| <= 0.17 rad, \|offset\| <= 2 m) | YES (chase camera = the game's camera bit 2 alone, probe PR-A2) |
| 10 | TRAFFIC_CONTACT | OBSERVE, MODIFY | CONTACT_OUTCOME (GAME / NO_CRASH) | YES (when the start-time check of the game's bytes passes) |
| 11 | WRECK_CAUSE | OBSERVE, MODIFY | WRECK_CREDIT (credit_racer or NO_RACER) | YES (observe at the game's count step; MODIFY asked when the victim wrecks - see below) |
| 12 | EVENT_SOUND | OBSERVE, MODIFY | SOUND_LEVEL 0..4 (the game's pitch ladder 1.0 .. 1.414 x) | YES |
| 13 | FINISH_CAMERA | OBSERVE, MODIFY | FINISH_CAMERA (GAME / POSE: pos, at, fov 0.7..1.4, within 40 m of the game's outro camera) | YES, reduced (the game's outro = one static camera pose per track, bit 8; probe PR-D) |

- `bm_hook_ctx` grows at its end (one group per point; the others 0): HUD_PASS `hud_visible`, `frame_dt_s`; camera points
  `cam_pos / cam_right / cam_up / cam_fwd`, `car_speed_mps`, `car_yaw_rate_rps`, `car_lat_accel_mps2` (0 in 0.1.9),
  `finish_time_s`; TRAFFIC_CONTACT `contact_racer`, `contact_traffic` (opaque, this occurrence), `contact_closing_mps`,
  `contact_same_dir`; WRECK_CAUSE `cause_aggressor`, `cause_victim`; EVENT_SOUND `sound` (BM_SOUND_TAKEDOWN), `sound_level_game`,
  `sound_event` (0x93, 0x9F..0xA6).
- `bm_hook_out` grows at its end: one group per output (`roll_rad ... offset_m[3]`, `outcome`, `credit_racer`, `sound_level`,
  `finish_camera`, `pose_pos[3]`, `pose_at[3]`, `pose_fov_scale`). A MODIFY callback gets `out` PREFILLED with the value so far and
  returns BM_HOOK_CHANGE with its proposal; a proposal outside the bounds (or of another output type) is IGNORED and counted
  (`stats.rejected`), never clamped.
- `point_info()` for 8..13: `available` = offered in this run; `roles` = the roles offered in this run (0 when unavailable).
  Registering at an unavailable point answers `BM_HOOKS_UNAVAILABLE`; 14 and above `UNKNOWN_POINT`. The table is unchanged
  (`BMSDK_HOOKS_TABLE_V3` = v1's). `BM_HOOK_POINTS` (6) and `BM_HOOK_POINTS_V2` (7) keep their values; `BM_HOOK_POINTS_V3` = 13.
- Order at one occurrence: hooks MODIFY (priority order) -> bmashup.events v7 twin observers (with the final output) -> hooks
  OBSERVE -> host observers. Re-entry, the stop at exit and the register guard are v1's rules.

## TRAFFIC_CONTACT (CHANGES GAMEPLAY with NO_CRASH)
Dispatched only when the game is about to make a racer-vs-traffic contact fatal (the vehicle-contact response sub_00112E70: the
closing metric above its threshold, the class pair fatal in the game's matrix, not the game's own forced path). Never for
racer vs racer. NO_CRASH is accepted only for `contact_same_dir == 1` and `contact_closing_mps < BM_HOOK_CONTACT_MAX_MPS` (25);
the game's own non-fatal push then runs. `contact_closing_mps` = the game's own metric in m/s; `contact_same_dir` = the game's two
velocity vectors point the same way.

## WRECK_CAUSE credit (CHANGES GAMEPLAY)
The MODIFY step runs when a racer WRECKS (cause_victim = it, cause_aggressor = BM_HOOK_NO_RACER: nobody credited yet), without
observers. An accepted `credit_racer` becomes the game's own claim (in that racer's score object: the claim time = its race time,
the claim mark = 1, for the victim's list index); the game's claim processing then decides and grants within about 0.5 s (a
competing claim may win). Refused: a racer outside the list, the victim itself, a victim already credited for this wreck. The
observers see WRECK_CAUSE when the game counts the takedown, with the aggressor the game chose. (Probe PR-H.)

## EVENT_SOUND (CHANGES GAMEPLAY AUDIO)
Both takedown-sign pitch calls (the normal sign and the alternate sound after 5 takedowns) pass the LEVEL through the point. A game
level outside 0..4 is never offered. No sound is played and no voice is used by the host.

## Build switch
`BO3_HOOKREQ_P23=OFF` (CMake): every point 8..13 stays UNAVAILABLE and no mark is in the generated code.

## Evidence
`tests\p23\hooks\run_hooks.py` (main19): framework 77 checks + OFF build + mutants 130..137; contact (real-XBE census of the
three mark ranges, tampered byte -> UNAVAILABLE; racer-vs-racer / forced path / oncoming / too fast refused; mutants 201..205);
event sound (mutants 211..213); marks wrapped in `#if BO3_HOOKREQ_P23`, once each.