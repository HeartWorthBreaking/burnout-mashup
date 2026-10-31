# bmashup.vphysics 1 - per-car physics values (query) and one bounded control

Header: `sdk\include\bmashup_vphysics.h` (`BM_VPHYS_VERSION 1`; host implementation 1.0.2 in p4.1 / p4.2; SDK 0.4.2 corrects
the header comment only). Host page: `host\bmashup-vphysics.md` (p4.2, with the correction table). Example:
`sdk\examples\vphysics-demo` (mod `bmashup-sdk.vphysics-demo`).

## What a value is
Each vehicle has a ValueDB file `VehiclePhysics/<car>.cfg`; at race set-up the game registers 64 of its values into a
per-vehicle block and COPIES them into the car's physics vehicle, which the physics step reads. So every value has two
readings: `game_value` (the vehicle's block) and `current` (the car's copy). Both are given in ValueDB units (the service
converts the copies the game scales, e.g. revs to rad/s, back).

## API
| Call | What |
|---|---|
| `count` / `info(i)` / `find("Group \| Name")` | the 64-value catalogue: name, unit, `writable`, `scale_min` / `scale_max` |
| `racers()` / `get(racer, i)` | any racer of the race in play (index as `bmashup.racers`): `current`, `game_value`, `scaled`, `scale`, `vehicle` (file stem, e.g. `COMPCAR1`), `is_player1` |
| `set_scale(i, scale)` | player 1's car uses `game_value x scale` from its next car update, every race, until `reset` - WRITABLE values only: **Drag Coef 0.25..4**, **"Max Speed In Boost" 0.5..2 = the car's TOP-SPEED LIMIT** (see the correction) |
| `reset(i)` / `status()` | restore at the next car update; status counters (applied, reapplied, restored, contested) |

## Behaviour
- Writes happen only on the game's thread (car update; after an update when a race is left). At each car update the copy is
  checked: still the game's value (the game copied it again) -> written again; already scaled -> nothing; a third value
  (another writer) -> left alone, counted `contested`. Leaving a race or `reset` puts the game's value back.
- Other cars, the vehicle block and the game's data are never written (AI cars sharing player 1's vehicle keep the game value).
- Ownership: one plugin per value (`BM_VPHYS_CONFLICT` for another). Fail closed: unknown build or a car whose structure check
  fails -> nothing read / written, `UNSUPPORTED` / `UNAVAILABLE`. `RECOMP_DEBUG=autopilot` -> control off.
- Writer order on the car update (host): autopilot, boost, then vphysics (its value is what the car update reads).

## Evidence
- **Query RUNTIME-VALIDATED** (all 6 racers with vehicle names and game values): gp_phys1_3 (slice v1.0.2) and gp_p41_2 (p4.1).
- **Drag Coef x0.5 RUNTIME-VALIDATED**: gp_phys1_2 (+5.66 m/s mean, 7-17 s, 20 / 21 samples); gp_p41_2 (+0.86 m/s 1-5.5 s,
  +5.9 m/s 14.5-20 s); restored at RESTART, race 2 not scaled. Measured on an unsteered car (RT held): only windows with
  comparable driving count.
- **"Max Speed In Boost" RUNTIME-VALIDATED on p4.1** (gp_p41g_2): x0.5 pinned the car at 80.0-80.8 mph with AND without boost
  (baseline boosting 159.7 mph); restored 80 -> 160 at race exit; scales 0.49 / 2.01 refused. AI-car control: not offered (v1 is
  player 1 only).
- On p4.2 (gp_p42_1): Drag x0.5 on an ADDED car (race 1 faster in 68 / 91 samples 0-45 s, +2.90 m/s); the added car reports the
  donor's vehicle (`COMPCAR1`), by design.
- History: host 1.0.0 (in p4) refused every car at runtime (it looked in the racer object, not the physics vehicle); fixed in
  1.0.1 / 1.0.2 (p4.1).

## Correction (kit 0.3.1, observed semantics)
The catalogue name `Physics/Race Car/Misc | Max Speed In Boost` (the game's ValueDB key, kept as the identifier: no ABI or name
change) is, by its observed behaviour, the car's **top-speed limit**: it caps the car's speed in normal driving AND while boosting.
The retail value lies above the unboosted top speed, so retail play only meets it while boosting. A scale below 1 lowers the
car's top speed; above 1 raises the ceiling (the car still needs the power to reach it). Kit 0.3.0's text ("Max Speed In Boost
scale", boost only) was wrong on this point. Source: run gp_p41g_2 (`integration\p4_1\runtime\P41_GAPS_REPORT.md`) and the
p4.2 M2 documentation change.
