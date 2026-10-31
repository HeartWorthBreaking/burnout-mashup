# vehtool 0.1.2 - port notes (rel1b, 2026-10-27)

- Version: TOOL_VERSION 0.1.2 (successor of 0.1.1); PACKAGE_STAMP 0.1.1 (bmpack.json `packaged_by` and fixture manifests keep
  `vehtool 0.1.1`: outputs byte-identical).
- Kit placement: copy this folder byte for byte to `<kit>\tools\vehtool\`. Game data via `tools\_lib\bmkit_env.py` in the kit
  (option > BMKIT_GAME_DATA > bmkit.toml), stand-alone via option > BMKIT_GAME_DATA; `--game` stays as an alias.
  `examples\make_veh_packs.py` = the kit's `examples\authored\veh-series\make_veh_packs.py` with the vehtool beside it; if the
  kit keeps its own copy, point it at `tools\vehtool\vehtool.py`.
- Changed files: `vehtool.py` (no workspace default; hash-checked reads; messages instead of tracebacks for missing / wrong
  mod folders, invalid TOML, bad palette arguments, too few fixture series - 0.1.1 raised IndexError after writing part00;
  kit exit codes; `version`), new `gamedata.py`, `GAMEDATA_SHA256.json`; `tests\test_vehtool_limit.py` (game data argument,
  mutants get `gamedata.py`, SKIP without data); new `test_errors.py`, `test_regression.py`, `REGRESSION_SHA256.json`,
  `SELFTEST.json`; docs `README.md`, `docs\VEH_PACKS.md`, `PROVENANCE.md`.
- Exit codes: 0 ok, 1 refused (validate / inspect-car) or invalid input / path (0.1.1 raised), 2 usage, 3 cannot run
  (`vehtool: CANNOT RUN: ...`), 4 internal.
- Game data read (need list): `default.xbe`, `pveh\vlist.bin`, `pveh\<CLASS>\<Car>.bgv` (inspect-car, ramp-paint notes).
- CLI unchanged: `vehtool.py {inspect|inspect-car|validate|palette|fixture|package|version} ... [--game-data DIR]`.
- Tests: `tests\test_vehtool_limit.py OUT --game-data D` PASS (5 / 5, mutants 2 / 2); `tests\test_errors.py OUT --game-data D`
  22 / 22; `tests\test_regression.py OUT --game-data D` 4 / 4 (22 pack files = kit 0.4.0 staging, the authored packs admitted,
  the negatives refused for their reasons).
