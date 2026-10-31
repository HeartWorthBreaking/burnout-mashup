# bmashup.traffic 3 - crash pool counts, near_vehicles / wreck / clear_wrecked (platform 0.1.9)

Header: `sdk\include\bmashup_traffic.h` (`BM_TRAFFIC_VERSION 3`). Examples: `sdk\examples\bm-traffic-check`, `bm-kamikaze`.
Status: **REDUCED in this build** (offline-tested; the pool counts ran in the retail game at density 3.0: crash pool peak 8 of 64, no refusals). Players are numbered as the API's `player` argument: player 0 = the first (one-player) player; player 1 = split screen.
Append-only: v1 / v2 unchanged.

## What works in this build
- `status()` grows 60 -> 72 bytes: `wreck_slots_used` (occupancy of the game's 64-slot crash pool, read now), `wrecks_by_plugins`,
  `pool_refusals` (this race). A v1 / v2 caller's struct is filled only to its size.

## In the table, UNAVAILABLE in this build (nothing guessed)
| function | design | why not yet |
|---|---|---|
| `near_vehicles(player, out, &n)` | live traffic nearest to the player's car as handles valid for one step (position in the car's frame, speed, same direction, crashed, class) | the traffic vehicle record's live / position / velocity / crashed / class fields are not verified (the probes did not cover them: an RE item) |
| `wreck(handle)` | the game's own induced traffic crash (the call the traffic code makes, player 0's car as the inducer) at the next traffic update | needs the handles above and player 0's inducer object (not verified) |
| `clear_wrecked(min_distance_m >= 150)` | crashed traffic far from the player removed by the game's own despawn, <= 2 a step | **UNAVAILABLE by the probe** (PR-B / PR-B2: about 600 despawns freed 0 slots; the slots of a crash clear together ~5 s after it in a bulk reset - no per-slot release a plugin could ask for) |

## The crash pool guard (implemented, tested; used by wreck once available)
The game's crash pool has 64 slots and **no full check of its own** (a 65th crash writes past the pool). A wreck may take up to 3
slots (linked vehicles). `wreck` is refused with POOL_FULL unless at least 4 slots are free and fewer than 8 vehicles are crashing
(the game's crashing cap); <= 4 wrecks a second per plugin (RATE). PR-B measured the pool at density 2.0: at most 3 / 6 of 64
busy (margin confirmed at 2.0; at density 3.0 the validation race measured a peak of 8 of 64).

## Switches and constants (`src\game\bm_traffic.c`)
`BO3_HOOKREQ_P23=OFF`: no pool reads; every v3 call UNAVAILABLE. `BM_P23_TRAFFIC_VEHICLES_KNOWN` (0; flipping it needs the verified
record layout - a compile-time #error guards it), `BM_P23_TRAFFIC_DESPAWN_FREES` (0), `BM_P23_TRAFFIC_CRASHING_CAP` (8). Census of
4 code sites (the pool walk, its missing full guard, the induce routine, its retail call).

## Evidence
`gp\slices\main19\tests\p23\traffic_v3\run_traffic_v3.py`: 17 checks, mutants 21..26 killed, OFF 4 checks, census 4 / 4 vs the XBE.
