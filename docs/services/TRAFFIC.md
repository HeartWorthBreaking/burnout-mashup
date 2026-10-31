# bmashup.traffic 1 - traffic query and density control

Header: `sdk\include\bmashup_traffic.h` (`BM_TRAFFIC_VERSION 1`). Example: `sdk\examples\traffic`
(mods `bmashup-sdk.traffic-half`, `bmashup-sdk.traffic-probe`).

## What it changes
The traffic FLOW of the race's own traffic set (vehicles per minute per lane and class, for every trigger) as
`original x density`. Nothing else: no pool size, draw limit, route, vehicle list or file.

## API
| Call | Thread | What |
|---|---|---|
| `status(&st)` | any | in_race, active vehicles, pool (254), set flags, triggers, flow records, start-trigger flow (game / now), density asked / applied, applications, refusals, owner |
| `set_density(d)` | game thread (plugin init, an events callback, `takedawn.race` update) | `0.0 <= d <= 2.0` (`BM_TRAFFIC_DENSITY_MAX`); used from the next traffic set-up |
| `get_density` / `reset` | game thread | reset (owner only) returns to 1.0 and releases |

## Behaviour
- Applied at the race's traffic set-up (the traffic init during the load and the pre-race population). A pause RESTART runs a
  new set-up (seen at runtime), so a change during a race counts from the next race / restart.
- 1.0 with nothing ever scaled writes nothing (zero touch). Idempotent: originals are kept, a repeated set-up never compounds.
- Fail closed: the set is checked first (trigger count, table bounds, every original finite and 0..1000 / min); a failing set
  is left untouched and counted in `refusals`.
- Ownership: the first requester owns the density; another `set_density` -> `BM_TRAFFIC_CONFLICT`.
- No mod.toml declaration exists yet (plugin API only).

## Evidence
- **RUNTIME-VALIDATED on p4** (gp_p4c_1, four RESTART segments): mean active traffic 11.12 / 0.00 / 4.58 / 11.44 at density
  1.0 / 0.0 / 0.5 / 1.0 (written back); `[TRAFFIC] density 0.00 at the traffic set-up: 28 triggers, 191 flow records, start flow
  31.2 -> 0.0 vehicles/min (495 values written)`. Query also in gp_p4_1 (active up to 21).
- On p4.1: OFFLINE-VALIDATED (slice suite PASS; the traffic code is not in p4.1's merge delta). Density 2.0: offline only.
- Note: the active count depends on the player's position on the route; compare runs with the same route.

## Evidence update (kit 0.3.1)
Density **2.0 RUNTIME-VALIDATED on p4.1** (gp_p41g_1: mean active 18.01 vs 8.75, max 26, pool 254 not approached). **p4.2**
(gp_p42_4): race 2 after a RACE_EXIT took 0.0: mean active 8.75 -> 0.00 (t 10 / 20 s: 11 / 13 -> 0 / 0).
