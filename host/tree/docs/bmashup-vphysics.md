# bmashup.vphysics - per-car physics query and a bounded player control (Burnout Mashup, EXPERIMENTAL)

Service `bmashup.vphysics` version 1 (implementation 1.0.2), header `include/bmashup_vphysics.h`. Offered only by Burnout
Mashup builds (platform 0.1.4 and later; p4.2 = 0.1.5). Research: `gp\atlas\PHYSICS.md`.

## What it reads
Every racer of the race in play (index as bmashup.racers), 64 VehiclePhysics values of the car's vehicle (the catalogue: `count()`,
`info(i)`, `find(name)`), each as `game_value` (the vehicle's ValueDB value) and `current` (the car's copy, the one the physics
step reads), in the ValueDB's units. Since 1.0.2 the car's physics vehicle is found by its pool, vtable and back-link (AI racers
included).

## What it writes (player 1 only, one owner per value)
`set_scale(index, scale)` from player 1's next car update, every race, until `reset()`; restored when a race is left. Other cars,
the vehicle's ValueDB block and the game's data are never written.

| Catalogue name (= ValueDB key, the identifier) | Meaning | Scale |
|---|---|---|
| `Physics/Race Car/Misc \| Drag Coef` | drag coefficient (higher = slower at speed) | 0.25 .. 4 |
| `Physics/Race Car/Misc \| Max Speed In Boost` | **top-speed limit**: despite its ValueDB name it caps the car's top speed in normal driving AND while boosting | 0.5 .. 2 |

**Correction (p4.2, owner requirement).** Earlier text called the second value a boost-only limit. Runtime r2 (gp_p41g_2,
`integration\p4_1\runtime\P41_GAPS_REPORT.md`) measured x0.5 (160 -> 80): the car stayed at 80.0-80.8 mph with AND without boost,
while the baseline race reached 159.7 mph boosting. The retail value is above the car's unboosted top speed, so the retail game
never shows the cap outside a boost. A scale below 1 therefore lowers the car's top speed; above 1 raises the ceiling (the car
still needs the power to reach it). The name and the catalogue entry are unchanged (no ABI change).

## Failure behaviour
Unknown build, a car whose structure check fails, another writer's value: nothing written, the status says why. `RECOMP_DEBUG=
autopilot`: control off, query on. Data mods use the same values through `[bmashup.cars] physics_scale` (an added car's block).
