# bmashup.traffic 4 - traffic seed and lane floor (main21, hook request v2 P5a)

Header: `sdk\include\bmashup_traffic.h` (`BM_TRAFFIC_VERSION 4`). Example: `sdk\examples\bm-traffic-attack`.
Status: **BUILT, offline-tested; NOT yet seen in the game** (probe P5a-R). Append-only: v1 / v2 / v3 unchanged.

## set_seed(mode, seed)
- The game resets its traffic spawn generator at every traffic set-up to **one fixed seed** (Xbox: no clock is mixed in).
  `BM_TRAFFIC_SEED_GAME` (default) keeps it. `BM_TRAFFIC_SEED_FIXED` starts the generator from your seed instead, right after
  that reset and before the first spawn. Seed 0 = exactly the game's own state.
- Same seed + same race inputs = the same traffic. For a new pattern each race, set a new seed before the race loads; keep it
  for that race's replay. Whether a replay runs the traffic reset again is **not verified yet** (probe P5a-R).
- One owner: the first plugin that sets a seed owns it (others: CONFLICT); the owner's `set_seed(GAME, 0)` releases it.
- UNAVAILABLE when the build has `BO3_HOOKREQ_P5A=OFF` or the game's reset code differs from the verified bytes (census).

## set_lane_floor(cars_per_min)
- A **floor, not a multiplier**: at the traffic set-up, after the density, every lane (flow record) whose flows summed over the
  six vehicle classes are above 0 but below the floor is scaled up to exactly the floor (its class mix kept). Busier lanes and
  lanes without any flow are untouched. 0 = off; at most `BM_TRAFFIC_LANE_FLOOR_MAX` (10) cars / minute.
- Same owner as the density (one owner of the set's flows); `reset()` clears the floor too. Idempotent like the density.
- The game's own limits are unchanged (pool 254, spawn refusal at active + 2, draw cap, 275 m live radius).

## status() v4 (72 -> 92 bytes)
`lane_floor`, `lanes_raised` (last set-up), `seed_mode`, `seed`, `seeds_applied` (traffic resets that took your seed). A v3 caller's
struct is filled only to its size.

## Not in this version (hook request v2, later phases)
Spawn spread / sector pre-load / filling lanes outside sectors, parked cars, traffic in the racing lane (need the traffic
vehicle record layout, P5b / P5c); zero-flow lanes borrowing another lane's rates (the modder's K_FILL) - say if you need it.

## Evidence
`gp\slices\main21\tests\p5a\run_p5a.py`: v4 41 checks, mutants 31..38 killed, OFF build 8 checks; regressions traffic1 (retail
sets, 4548 checks, mutants 1..7), traffic v2, v3 (+ OFF); census 6 rows vs the XBE; the generated code = main20's + the 3-line mark.
