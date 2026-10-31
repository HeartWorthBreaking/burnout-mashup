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
