## 0.3.4 (2026-11-02, shipped with Burnout Mashup 0.2.0-alpha.2)
- capacity: ONE table `trackbuild/capacity.py` (game default, Burnout Mashup host ceiling, mod.toml key, minimum host per value
  range): full_unit_bytes 0x28000 / 0x200000 (patch 131+), low_unit_bytes 0x18000 / 0x200000 (main21+ up to 0x30000, patch 131+
  above), static_bytes 0xD00000 / 0x4000000 (main21+ up to 0x20C4000, patch 131+ above; split screen keeps 0xA00000),
  gamedata_bytes 0x176000 / 0x800000 (main21+), lanes 64 / 255 (main21+). Host source: main21 bm_unitslots.h, bm_static.h,
  bm_gdslot.h, bm_lanes.h, bm_capdecl.c; ceilings = the host of Burnout Mashup 0.2.0-alpha.2 (main21 patch 131).
- description / package key `capacity`: "auto" (default) = build up to the host ceilings and declare exactly the need
  (page-rounded) in mod.toml `[bmashup.capacity]` (version = 1; merged with the package's own `lanes` / `[package.capacity_keys]`,
  largest value wins); "game" = the 0.3.3 refusals above the game's defaults. Route strips may give up to 255 lanes under auto.
- BUILD_REPORT.json `capacity` {mode, needed, declared, requires, min_host}; LABELS.json `capacity` only when something is
  declared; `tb.py capacity [OUT_DIR]`.
- material rows (info row `capacity.ROWS`): game 83; the host reads up to 255 with the BMRX row extension (patch 131; 127
  before). trackbuild writes no extension, so 83 stays the rule in every mode; the refusal names the host figure.
- units: pvs computed 4..162 (162 = the largest retail track); above: refused "above the largest retail
  track; untested in the game" (visibility rule +-8 unchanged). Records per block: 127 enforced; host patch 132 reads 255 with the
  block flag BMRC, which 0.3.4 does not write (the refusal says so).
- validate V6_budgets uses the effective limit (declared capacity, capped by the ceilings); the 83 material rows rule is
  unchanged (message explains it).
- vendored trackconv/package.py: mod_toml writes the merged declaration (lanes-only output unchanged; VENDOR.json edit noted).
- A track within the game's defaults builds and packages byte-identically to 0.3.3 (REFERENCE_0_2_1 unchanged).
- RUNTIME-UNVERIFIED (offline gates only): no game was launched; a declared track needs a host that supports the values.

## 0.3.3 (2026-11-02, development step, not released on its own; includes the 0.3.1 and 0.3.2 development steps below)
- route strips: `route.strips [{name, type, between [A, B], first, last, edges [[lo, hi] per rung], corners main|none}]` inserts
  branch / median lanes into the lateral lane sequence by the retail rule (trackbuild.lanegraph; DATA 36 / 36 tracks, 0 / 45,154
  slice exceptions, 968 / 968 strips): zero-width open / close on the neighbours' shared node, links and segment indices derived
  per slice, strict nesting. Without strips the route bytes are those of 0.3.2 (regression reference hashes unchanged).
- validate: V5_lane_graph (lateral sequence, strip rules, NAV-R fallback model); V2_drivable_coverage accepts several holding
  units only when EVERY holder carries the floor at the route's own height (retail crossings duplicate both decks into every
  holder; the game's unit lookup sub_001AD4A0 is first-hit, plan-only); walls probe every holder of a declared multi-level track;
  V2_level_clearance (>= 5.5 m under any floor above a route sample).
- fixtures: `gen-testloop --variant branch` (bypass + median kerb), `--variant fig8` (figure-8 bridge, desc["levels"]).
- RUNTIME-UNVERIFIED (offline gates only).

## 0.3.2 (2026-11-02, development step, not released on its own)
- materials: `retail_material {track, material, static_sha256}` copies a retail material record (+0x24 flags included) and its
  textures (D3D header, name, every texel / mip) VERBATIM from the user's static.dat (strict b3static parse; sha256 pinned).
  Refused: UV-scrolled / animated materials (+0x10 list not reproduced), Revenge bits 0x3000, no texture, non-DXT formats.
  Pass split: rows whose material has bit 0x01 go after the mesh block's first-pass count +0x73 (retail survey 36 tracks /
  2,838 blocks: 18,258 / 18,258 second-pass rows carry 0x01). Without retail materials the bytes are those of 0.3.1.
- objects: `retail_objects [{family instance|prop, track, index, static_sha256, placements [{pos, yaw_deg}]}]` copies instance
  models (+0x38; LOD-tail placements) and prop types (+0x3C; +0x44 class, +0x48 matrices, +0x4C / +0x50 per-unit lists)
  verbatim with their materials (record +0x5C / +0x5E / +0x60 remapped). Matrix = the source's first placement turned about Y,
  position replaced, elements 3 / 7 / 11 / 15 copied (APPROXIMATE). Capacity: never above the retail maxima (instances 5,433 /
  track, 120 / unit, 81 types; props 741 / track, 66 / unit, 32 types).
- validate: V11_retail_materials_verbatim, V12_retail_objects_verbatim (copied bytes vs source hashes, pass split, placements in
  their unit regions, prop words (class << 16) | matrix).
- RUNTIME-UNVERIFIED (offline gates only). Products with retail materials / objects are LOCAL ONLY.

## 0.3.1 (2026-11-01, development step, not released on its own)
- lod decimate: a material that cannot be simplified within e_max keeps its full detail in the LOD block (identity records for
  that material, error 0) instead of failing the build; stats list them as full_detail_materials. V8_lod unchanged (those rows
  measure 0). Reason: detailed copied geometry forced lod identity for the whole track, which filled the LOD slots.
- lod.drop_below (m, optional): connected pieces smaller than this are left out of the FAR (LOD) render mesh only; collision is
  complete. V8_lod applies the same rule (lod.small_components) to the mesh records and measures the rest; its detail reports
  the left-out triangles. Without the key nothing changes.
- RUNTIME-UNVERIFIED (offline gates only).

# trackbuild changelog

## 0.3.0 (2026-10-29) - sloped routes (main21 kit layer, patch 66)
- Routes may climb and descend. `V2_drivable_coverage` compares the highest floor at every sample with the ROUTE height there
  (the two stations' own y, interpolated) instead of station 0's height; `V2_walls_hold` probes 0.7 m above each station's own
  height. The gates are as strict as before (0.05 m): a route lifted 0.3 m above its road is still refused
  (tests/test_slopes.py h02). New report value `max_route_grade_pct`.
- Nothing else in the builder assumed a flat route: the AI route nodes (S4), traffic nodes and visibility samples already used
  each station's height (the built S4 nodes of the hill demo carry the stations' heights: h01).
- New demo variant `gen-testloop --variant hill` (BM Hill Loop, examples/hill_package.toml, EU_T8_V1): an 8 m hill on the back
  60 % of the lap (max grade 5.9 %); the start line, grid and first 30 % of the lap stay flat (the S1 grid matrices are level).
- Flat tracks: identical sources and packages (tests/REFERENCE_0_2_1.json still holds; demo / crash / canyon sources
  byte-identical to 0.2.1's generator).
- New tests/test_slopes.py (h01 hill pipeline + built route heights, h02 lifted route refused, h03 flattened route refused);
  run by tests/run_tests.py.
- Runtime: the game drives sloped routes (retail tracks; the converted White Mountain track ran an autopilot race, KB
  ADDENDUM_2026_10_26_WHITE_MOUNTAIN_CONVERSION), but no trackbuild-built sloped track has been run in the game yet.

## 0.2.1 (2026-10-27) - crash fix (capdbg T1)
- Every mesh unit block now writes the chevron set index (+0x7D) as -1 ("none"). trackbuild writes no chevron set, but 0.2.0 and
  earlier wrote index 0, and the game draws chevron entry 0 without checking the set's count. It then read the next structure
  (the relocated per-unit pointer table) as an entry. With the game's own track pool the bogus count is negative and nothing
  happens. With a relocated STATIC pool (for example a plugin's bmashup.streaming STATIC request, the SDK capacity example) it
  is about +19,000, and the game crashed at race start (alpha RC rc_onb_1 / 1b).
- New validate gate V10_chevron_index_in_set: refuses any unit whose chevron index is >= the track's chevron set count.
- Output: streamed.dat differs from 0.2.0 by one byte per unit (0x00 -> 0xFF); every other file is byte-identical
  (tests/REFERENCE_0_2_1.json; the 0.1.6 / 0.2.0 reference stays as tests/REFERENCE_0_1_6.json).
- Rebuild every track made with 0.2.0 or earlier (or run the host with the capfix1 chevron guard).
## 0.2.0 (2026-10-27) - portable successor of 0.1.6
Same track files and packages as 0.1.6 for the same sources and donor data (byte-identical: BM Test Loop, BM Canyon Ring;
tests\test_regression.py). Changes:
- No developer-workspace dependency: the readers / writers are vendored in `trackbuild\_vendor` (VENDOR.md); no absolute
  paths, no sys.path into other folders; package-relative imports only.
- Donor data from an explicit game-data folder (`--game-data`, `TRACKBUILD_GAME_DATA`, `BMKIT_GAME_DATA`), every donor
  file hash-checked (`trackbuild\donor.py`); `check-game-data` command; other hosts only with `--unpinned-donor`.
- Actionable errors with exit codes (2 usage / path, 3 prerequisite, 4 unsupported input, 1 failed gate); `selfcheck`;
  `tb.cmd` launcher that reports a missing Python.
- New input refusals (formerly ignored silently): unknown material keys (alpha, shader, animated, ...), transparent texture
  pixels, more than 83 material rows, missing texture / OBJ files named by the description.
- `package` requires a passing `validate` of the current files (VALIDATION.json records their sha256); the host-reader check
  (bmpack validate) is explicit: `--bmpack FILE`.
- `tests\test_errors.py` (actionable errors), `tests\test_regression.py`, `tests\run_tests.py`; the 0.1.6 suite takes the
  game data as a parameter (T4 converted control optional: `--converted DIR`).
- Opt-in access monitor `trackbuild\accessguard.py` (isolation check).

## 0.1.2 .. 0.1.6 (gp tools, summary)
0.1.2 vertex colour 0.2; 0.1.3 authored traffic (S2 / S3); 0.1.4 LOD decimation; 0.1.5 computed PVS (<= 162 units);
0.1.6 grid slot start unit, canyon = 30-unit stadium.
