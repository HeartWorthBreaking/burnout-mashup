# bmashup.traffic 2 - density up to 3.0 (platform 0.1.8)

Header: `sdk\include\bmashup_traffic.h` (`BM_TRAFFIC_VERSION 2`). Example: `sdk\examples\bm-traffic-x3`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); densities above 2.0 are **EXPERIMENTAL** until the
measuring launch (pool 254, draw limit 32 a view, 8 crashing, frame time at 3.0) is recorded. **CHANGES GAMEPLAY.**

## What version 2 adds
- Appended (`BMSDK_TRAFFIC_TABLE_V2`): `set_density_v2(d)` with `0.0 <= d <= BM_TRAFFIC_DENSITY_MAX_V2` (3.0). Version 1's
  `set_density` keeps its 2.0 bound (`BM_TRAFFIC_DENSITY_MAX`): a v1 plugin sees exactly v1's behaviour.
- Both functions share the one owner of version 1 (`CONFLICT` for anyone else).
- `bm_traffic_status` grows 56 -> 60 bytes (`BMSDK_TRAFFIC_STATUS_V2`): `experimental` = 1 when the requested or last applied
  density is above 2.0 (`BM_TRAFFIC_DENSITY_LABELLED`).
- A density above 2.0 is logged EXPERIMENTAL at the request and at each traffic set-up.

## What it does not change
As version 1: only the flow values of the race's own traffic set (original x density). Not the pool (254), the draw limit, the
crashing limit or the spawn rules: above 2.0 the game itself may refuse spawns or not draw far vehicles.

## Deviations from the design draft
`near_vehicles`, `wreck` and `clear_wrecked` (hook request phase 2) are not in the table.

## Evidence
`gp\slices\main18\test_runs\svc_a_r1`: 14 checks / 0 failures, 3 / 3 mutants; the traffic1 suite on the new source 4548 / 4548
(its status-size check moved 56 -> 60), 7 / 7 mutants. The EXPERIMENTAL text of the set-up log line is checked only in game.
</content>
