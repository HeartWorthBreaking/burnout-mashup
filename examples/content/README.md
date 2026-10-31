# Content examples (mod kit 0.3.1) - generators, NO game data

| folder | table | mod | build |
|---|---|---|---|
| `added-car\` | `[bmashup.cars] version 1` | `bmashup.gp-cars2`: COMPBM01 "Compact Mashup" on the donor COMPCAR1 | `py -3 -B make_added_car.py --data "<game>\Burnout 3 Takedown" --out <new folder>` (`--plain` = donor model unchanged, no workspace modules) |
| `wt-region\` | `[bmashup.world_tour] version 1` (+ regions, tracks, extra_events v2) | `bmashup.wt4-oceania`: region OCEANIA on the borrowed USA map, track OC_C1_V1 (placeholder copy of US_C1_V1), events Oceania Sprint / Night | `py -3 -B make_wt_region.py --data "<game>\Burnout 3 Takedown" --out <new folder>` |

Both scripts check every input against its retail sha256 (NTSC-U) and refuse anything else. The outputs are retail-derived:
**local only, never upload, never put them in a kit or repository.** Install the generated mod folder into a content mods folder
(`BMASHUP_MODS`); no approval is needed (data only). Both need platform 0.1.5 (an older host refuses the mod alone).

What the runtime runs showed and what stays open: `docs\services\CARS.md`, `docs\services\WORLD_TOUR.md`. In short: the added car is
listed last in its series, selectable, raced, removable (the profile loads without it); the region's events race and keep their
medals in the sidecar, but its map page BORROWS the USA art / place name / ticker / counters, and the region page repeats a HELD
direction once per 0.25 s globe spin (retail behaviour: tap, or script presses of 100 ms or less).

`added-car\mod.toml` differs from the launched set's only in its comment and `[bmashup]` (`platform >= 0.1.5`, `requires`);
`wt-region\mod.toml` is the launched set's byte for byte.
