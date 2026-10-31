# Garage paints 7 / 8 - a host setting (p4.1)

Not a service and not a mod declaration: a **player setting** of the host. MODS > MOD SETTINGS > BURNOUT MASHUP >
`GARAGE PAINT 7-8` (BOOL, **default OFF**).

## What it does
The garage's paint button cycles a car's paints modulo min(the car's palettes, 6) in retail. With the setting ON the cap is
min(the car's photo palette count, 8), so cars with 8 palettes offer paints 7 and 8. The game's online lobby uses palettes 7 /
8 as its red / blue team colours; offline the choice only changes the look. The paint is run-time state (not in the profile
save): no save-format change, no sidecar.

Order of the cap: `BMASHUP_GARAGE_PAINT_CAP=1..8` (a DEVELOPER override, logged "developer override"; an invalid value is
ignored and logged) > the setting > retail 6. Turning the setting off is retail again. A data mod declares nothing for this
(the palettes are in the retail car files already). Car liveries (replacing a car's textures / palettes with a data mod) are
possible with ordinary file replacement but contain game-derived data: never ship such files.

## Evidence
- **RUNTIME-VALIDATED**: gp_p41_2 (page `GARAGE PAINT 7-8 OFF` -> ON saved; `[PAINTS] garage paint cap 8 (MOD SETTINGS ...)`;
  after 7 X presses the car is blue (paint 8), 7 more red (paint 7)); gp_cars1_3 (paints1 build, env cap 8: an 8-step cycle).
- OFFLINE-VALIDATED: the developer override, cap 6 = the retail functions exactly (real generated code tests).
- Hypothesis: the exact look of 7 / 8 as the team colours (no retail reference shot).

## Evidence update (kit 0.3.1)
**p4.2** (gp_p42_5): the toggle saved, `[PAINTS] garage paint cap 8`, paint 8 (blue) shown in the garage.
