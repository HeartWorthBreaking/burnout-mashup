# bmashup.traffic 5 - vehicle queries, wrecks, section minimum, spawn spread (main21, hook request v2 P5b + P5c)

Header: `sdk\include\bmashup_traffic.h` (`BM_TRAFFIC_VERSION 5`). Examples: `bm-traffic-kamikaze` (near_vehicles / wreck),
`bm-traffic-attack` (seed, lane floor, section minimum, spread). v4 (seed, lane floor): `TRAFFIC_V4.md`.
Status: **BUILT, offline-tested; NOT yet seen in the game** (probe P5-R). Append-only: v1..v4 unchanged.

## near_vehicles(0, out, &n) and wreck(handle) - now working (P5b; same v3 table entries)
- **near_vehicles**: live traffic vehicles nearest to your car first, at most 32. `rel_pos_m` in your car's frame (x right, y up,
  z forward), `speed_mps` and `same_direction` derived from the vehicle's positions over the last steps (0 for a vehicle's first
  step), `crashed` = the game's own "do not induce" state, `vehicle_class` (1 car .. 11 artic trailer). Player 0 only.
  The handle is valid in the same simulation step only (else STALE).
- **wreck(handle)**: the game's own induced crash with your car as the inducer, carried out in the same traffic update right after
  the game's own crash pass, after re-checking the vehicle (still live, not crashing) and the crash pool (>= 4 of 64 slots free,
  fewer than 8 crashing; else POOL_FULL). <= 4 a second per plugin, 16 queued at most (RATE). The game's fatal table may refuse a
  class pair: then nothing happens.
- clear_wrecked stays UNAVAILABLE (the game frees crash slots only by its bulk reset).
- The vehicle records are **statically mapped** (census-checked against the game code at start); treat results as EXPERIMENTAL
  until the probe confirms them.

## set_section_min(cars) and set_spawn_spread(on) - v5 (P5c)
- The game fills a lane section with round(e) cars, e = the cars it expects there from the section length, the lane speed and
  its flows; a section with e < 0.5 gets none. `set_section_min(c)` fills a section with 0 < e < c as if e were c (0 = off,
  at most 4). Lanes without flow stay empty.
- The game places car i at i x rand x spacing, bunched toward the section start. `set_spawn_spread(1)` places car i at
  (i + rand) x length / N: one car per slice, every car inside the section. The game's own random draws are used (a seed still
  reproduces the traffic).
- Same owner as the density / lane floor; `reset()` clears both.
- status() 92 -> 108 bytes: `spawn_spread`, `section_min`, `sections_raised`, `cars_spread`.

## Switches
`BO3_HOOKREQ_P5B=OFF`: near_vehicles / wreck UNAVAILABLE (as in 0.1.9). `BO3_HOOKREQ_P5C=OFF`: the two v5 functions UNAVAILABLE.
With every P5 switch OFF the generated game code is byte-identical to main20's (audit).

## Not in this version (hook request v2, still open)
Parked cars (T3) and traffic in the racing lane (T4) need the lane network (the modder's prototypes detach a car from its lane /
build a virtual lane); pre-loading the next sector and filling lane stretches no sector lists (the sector system is not mapped);
the colour picker screen (front-end screens, no service yet). (Zero-flow lanes: v6, below.)

## Evidence
`gp\slices\main21\tests\p5\run_p5.py` (`test_runs\p5_final`): P5a 41 + 8 mutants, P5b 34 + 8 mutants, P5c 22 + 7 mutants, OFF builds,
traffic1 over the retail sets 4548, traffic v2 / v3; census 14 rows vs the XBE; the generated code = main20's + the 4 marks.

## set_fill_empty_lanes(on) - v6 (main21 patch 70, the modder's K_FILL)
- At the traffic set-up, a lane whose six flows are all 0 takes the rates of the first lane of the **same road in the same
  trigger** that has flow (before the density and the lane floor). Roads without any flowing lane stay empty. Same owner as the
  density; reset() clears it. status() 108 -> 116: `fill_empty_lanes`, `lanes_filled`.
- Retail census (377 sets, 160,567 lanes): 16.4 % of the lanes are empty (the modder measured 16 %); **2,807** have a flowing lane of
  the same road in the same trigger (filled by this rule); 5,568 would with earlier triggers too, 6,841 with any trigger of the set;
  the rest are on roads with no flow at all (e.g. the crash-junction sets). The stricter rule is exact on the data; the wider ones
  guess at the runtime valve state - a decision after the probe.
- Evidence: `tests\p5f\test_traffic_fill.c` 20 checks + mutants 61..63, OFF build; `test_runs\p70_final` all_ok.
