# bmashup.vphysics 2 - handling values outside a race (platform 0.1.8)

Header: `sdk\include\bmashup_vphysics.h` (`BM_VPHYS_VERSION 2`). Example: `sdk\examples\bm-vphysics-garage`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); runtime: pending.

## What version 2 adds
Version 1 (catalogue of 64 values, `get` per racer, `set_scale` on player 1, `status`) is unchanged. Appended
(`BMSDK_VPHYS_TABLE_V2`), all READ ONLY, any thread, in or out of a race:

| Call | What |
|---|---|
| `vehicle_count()` | vehicles in the list (retail: 100); 0 while UNAVAILABLE |
| `vehicle_info(v, &info)` | `bm_vphys_vehicle_info` (40 bytes): index, name (e.g. "COMPCAR1"), class, flags |
| `vehicle_find(name, &v)` | the index of a name, else 10 `NO_VEHICLE` |
| `vehicle_value(v, catalogue index, &val)` | `bm_vphys_vehicle_value` (40 bytes): `have`, `value`, `game_value`, `scaled`; 11 `NO_VALUE` when the file has no record (out filled, have = 0) |

## Mechanism
Values are looked up in the vehicle-physics ValueDB the game loaded at boot, the way the game does (the same key hash and the
same signed binary search), and passed through the catalogue's transforms of version 1. No guest write; no address is returned.
Every check fails closed with `UNAVAILABLE` (e.g. before the boot load).

## Honest limits (deviations from the design draft)
- The list is every `<class>CAR<n>` vehicle file in the loaded ValueDB, ordered by class then number - not the garage order.
  `series_class` is that class (`BM_VEH_CLASS_*`).
- Added cars (`[bmashup.cars]`) are not listed: query their donor by name. `scaled` is always 0 and `value` = `game_value`
  (mod scales are applied at race set-up, not here).
- `open` (unlocked) is always UNKNOWN: the unlock reader is not verified.
- The gearbox controls of the draft are hook request phase 2 (not in the table).
- The garage's own binding path (sub_000C0080 -> sub_001AEDB0 against "../Export/ValueDB/VehiclePhysics/%s.cfg"; modder's
  hint, verified only as far as the ValueDB load) is not used: the service reads the same loaded data directly.

## Evidence
`gp\slices\main18\test_runs\svc_a_r1`: 15 checks / 0 failures, 6 / 6 mutants killed; all 100 vehicles x 64 values (6,400)
equal the atlas's independent reader of the retail data (read only), including missing records. Version 1 suite 59 / 0,
physics1 mutants 9 / 9.
