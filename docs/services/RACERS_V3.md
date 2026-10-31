# bmashup.racers 3 - dynamics, parts, lights reads and the racer controls (platform 0.1.9)

Header: `sdk\include\bmashup_racers.h` (`BM_RACERS_VERSION 3`). Examples: `sdk\examples\bm-racers-dynamics`,
`bm-detach-parts`, `bm-lights-blinkers`. Status: **BUILT, offline-tested and run in the retail game** (patches 22 / 23 / 24 + 37 / 49 / 50). Runtime (validation rounds): the reads
ran once a second (speed up to 243 km/h), `award_score` 32 x OK, `detach_part` on player 0 OK, the indicator control and `lamp_counts`
answered (left 2 / right 2). The visual indicator BLINK itself is not confirmed in still screenshots.
Players are numbered as the API's `player` argument: player 0 = the first (one-player) player; player 1 = split screen.
Append-only: a v1 / v2 caller sees exactly v1 / v2 behaviour (its `struct_size` bounds what is read and written).

## Reads (bm_racer_info 52 -> 160 bytes)
| field | source | note |
|---|---|---|
| `gear` | the gearbox's own gear (physics vehicle + 0x1448 + 0x80) | -1 R, 0 N, 1..6 |
| `speed_mps` | **host-derived** for every racer (world-position change between two steps x 60) | REDUCED: the speedometer's HUD object (constant value 2) read 0 at runtime (m19_r2a: 0.0 km/h in 324 samples) - wrong object / view; derived is the default (patch 50) |
| `yaw_rate_rps`, `lat_accel_mps2`, `long_accel_mps2` | **host-derived** from the car's world matrix at successive steps | yaw + = turning left; lateral + = left; longitudinal + = forward |
| `have_dynamics` | 1 after three successive steps | 0 at the race start, after a respawn / a jump > 50 m, or when the racer leaves the list |
| `have_rpm` / `engine_rpm` | - | `have_rpm` 0 (REDUCED: no word in the gearbox / engine data follows the revs, PR-A2) |
| `parts`, `part_kind[32]`, `part_state[32]` | the car model's damage parts (count byte, kinds 0..6, the game's state byte) | state 0 intact, 1 damaged, 2 hanging, 3 flying, 4 removed; 0xFF past `parts`. Kind names (PS2-derived, visual check pending): 0 R door, 1 L door, 2 front bumper, 3 rear bumper, 4 bonnet, 5 boot, 6 extra |
| `lights` | the light flags the car update built this step | head (0x02 / 0x04), tail 0x08, brake 0x10; indicators 0x20 / 0x40 reported (blinking ones read on / off with the phase; patch 49) |
| `controls_owned` | the v3 controls held by any plugin for this racer | bit (1 << BM_RACER_CTL_*) |
The dynamics are sampled once per simulation step at player 0's car update (an observer: nothing written).

## Controls (recorded on any thread, carried out at player 0's next car update on the game's thread)
| function | what | limits / codes |
|---|---|---|
| `detach_part(racer, part)` | the game's DetachBodyPart for a HANGING part (state 2), as the Road Rage update calls it | once per part per race (ALREADY); NOT_HANGING otherwise; one DAMAGE owner per racer (CONFLICT); any racer: player 0's car at its next car update, an AI racer at the start of its own car update (PR-A1: that point runs for every racer) |
| `set_light(racer, light, ON / GAME)` | the racer byte the car update ORs into its light flags (retail never sets it) | head / tail / brake and the indicators (see Indicators below) on any racer; OFF UNSUPPORTED (an OR cannot clear the game's bits); <= 10 changes a second per racer (RATE); one LIGHTS owner per racer |
| `light_available(racer)` | the lights `set_light` can show | head / tail / brake; IND_LEFT / IND_RIGHT only on models with group 5 / 6 points |
| `award_score(player, amount)` | CHANGES GAMEPLAY: add to player 0's score total = the word the HUD SCORE counts up to and the results' BURNOUT POINTS show (PR-A1 / PR-E) | 1..100000, 8 a second / 512 a race per plugin (RATE), added at player 0's next car update; takedown counts / points untouched |
| `release(racer, family)` | give a family back now | NOT_OWNER for a family you do not hold |
| `result_text(code)` | a code's name | |
Everything is given back when a race is left or restarted (light bytes back to 0, pending detaches / awards dropped).
Not offered: a racer wreck on request (no verified whole-path entry), light OFF.

### Indicators (main19 patch 49, owner)
`set_light` takes IND_LEFT (0x20, light group 5), IND_RIGHT (0x40, group 6) and HAZARD (both) on any racer; the host
blinks them (period 40 steps = about 1.5 Hz: ORed in for 20 steps, its own bits taken out for 20). **Lamps show only on
models with group 5 / 6 points**: `lamp_counts(racer, &g5, &g6)` (appended to the v3 table) reads the model's counts and
`light_available()` lists IND_LEFT / IND_RIGHT only where they are non-zero (the probe's Compact Type 1 has none).
Which side group 5 / 6 is follows the renderer's group order (visual check per model pending).

## Switches and probe constants (`src\game\bm_racers.c`)
`BO3_HOOKREQ_P23=OFF`: every control UNSUPPORTED, the per-car mark compiled out (reads stay). Constants a probe flips:
`BM_P23_RACERS_SPEED_SOURCE` (0 derived / 1 the physics speed word), `BM_P23_RACERS_RPM_KNOWN`, `BM_P23_RACERS_INDICATORS_KNOWN`,
`BM_P23_RACERS_APPLY_PER_RACER` (1 since patch 37), `BM_P23_RACERS_SCORE_FIELD` (2 since patch 37: the verified word S + 0x4C),
`BM_P23_RACERS_SPEED_SOURCE` (0 = derived, the default again since patch 50; 2 = the speedometer object, reads 0 at runtime). A census of the controls' 6 code sites runs at first use: a different game build -> UNSUPPORTED.

## Evidence
`gp\slices\main19\tests\p23\racers_v3\run_racers_v3.py`: reads 14 checks (two analytic paths) + mutants 31..37; controls 36 checks
on the REAL generated DetachBodyPart incl. an AI detach at the per-car mark and the live score path + mutants 41..48, 50..53;
OFF build 6 checks; census 6 / 6 vs the XBE.
