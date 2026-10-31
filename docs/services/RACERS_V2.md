# bmashup.racers 2 - place, laps, race time, order, session (platform 0.1.8)

Header: `sdk\include\bmashup_racers.h` (`BM_RACERS_VERSION 2`). Example: `sdk\examples\bm-racers-order`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); runtime: pending. Read only.

## What version 2 adds
- `bm_racer_info` grows 28 -> 52 bytes (`BMSDK_RACER_INFO_V2`): `place` (1 = leading as the game ranks; 0 not ranked),
  `laps_done`, `race_time_s`, `phase` (0 / 1 before the GO, 2 racing, 3 finished), `player` (0 = player 1's car, else
  `BM_RACER_NO_PLAYER`), `eliminated` (always 0 in 0.1.8: reserved for the later bmashup.rules). The new fields are filled only
  when the caller's `struct_size` covers them.
- Appended (`BMSDK_RACERS_TABLE_V2`): `order(order[], &n)` - racer indices, ranked racers first by place, unranked last, ties by
  index; `session(&s)` - `bm_racers_session` (28 bytes): in_race, mode, context, players, racers, laps_total.
- Result code appended: 4 `NOT_IN_RACE`.

## Sources
Each racer's car record: place (int16 at the car's place field), laps, race time and phase (the fields takedawn.race reads for
player 1, runtime-proven there). Rival cars are the same class: their values are **PARTIAL** until a census run compares them
with the results screen.

## Deviations from the design draft
- `session.mode` and `session.context` are `UNKNOWN` and `laps_total` is 0: their readers are still RE items.
- `eliminated` is always 0; `order` / `session` do not enforce the game thread (read-only snapshots; call from the game thread
  for one step's consistent values).
- The fields are appended to the existing structs (not separate tail structs); the v3 dynamics and controls are phase 2.

## Evidence
`gp\slices\main18\test_runs\svc_a_r1`: 19 checks / 0 failures, 6 / 6 mutants killed.
</content>
