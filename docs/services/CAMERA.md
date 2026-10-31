# bmashup.camera 1 - field-of-view scale of the one-player race camera

Header: `sdk\include\bmashup_camera.h` (`BM_CAMERA_VERSION 1`). Example: `sdk\examples\camera-fov` (mod
`bmashup-sdk.camera-fov`: a CAMERA FOV setting 70..140 % on MOD SETTINGS).

## What it does
The game sets each view's camera up once per stage (a race, Road Rage, Crash, a RESTART) with its own field-of-view factor
(1.0 in 4:3, 1.2 in 16:9; display.ultrawide widens it). `set_fov_scale(percent)` (70..140, 100 = the game's) scales the
factor the set-up loaded, before the game stores it, at the NEXT ONE-PLAYER stage set-up. The front end (menus, garage)
always gets the game's factor; split-screen stages are not changed (version 1). Nothing is written into the game's data.

## API
| Call | What |
|---|---|
| `set_fov_scale(host, percent)` | 70..140 (`BM_CAMERA_OUT_OF_RANGE` otherwise); any thread after (or during) the plugins' start |
| `release(host)` | back to 100 from the next set-up; another plugin may take it |
| `state(host, &st)` | available, stage_active, setups, game_fov, game_aspect, applied_fov, applied_scale, requested_scale, owned / yours, crash_camera (player 1's crash / takedown camera byte) |
Ownership: the first plugin that asks for anything but 100 owns the scale; others get `BM_CAMERA_BUSY` until it asks for 100
or releases.

## Evidence
- **RUNTIME-VALIDATED (4:3 path)**: gp_camset1_r1 (race 1 at 100 % = 1.0, race 2 at 130 % = 1.3; frames of race 2 = race 1
  zoomed out by k 1.30, control k 1.00, garage unchanged) and gp_p4c_1 (130 % in four RESTART segments on p4). On p4.1 the
  page showed `CAMERA FOV 100 %` (gp_p41_2); the scale itself was not re-measured there.
- OFFLINE only: the 16:9 / ultrawide path (same generated line); not supported: split screen.

## Evidence update (kit 0.3.1)
**p4.2** (gp_p42_5): `field of view 1.0000 x 130% = 1.3000` logged at the stage set-up; the race frame looks wider (a visual
comparison, no zoom fit). 16:9 / ultrawide and split screen: still not run.
