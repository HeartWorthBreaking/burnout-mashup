# vehtool 0.1.2 - provenance

| file | origin | change |
|---|---|---|
| `vehtool.py` | vehtool 0.1.1 (gp tools, slices veh1 / veh1_fix) | no workspace default; `--game-data` (alias `--game`) / `BMKIT_GAME_DATA` (kit: also bmkit.toml via `tools\_lib\bmkit_env.py`), hash-checked reads of `pveh\vlist.bin` and car models; actionable errors with the kit 0.4.1 exit codes (1 refused / invalid, 3 cannot run, 4 internal), `version`; `fixture` refuses too few series up front (0.1.1: IndexError after writing part00); `PACKAGE_STAMP` keeps the 0.1.1 output bytes |
| `gamedata.py`, `GAMEDATA_SHA256.json` | NEW (rel1b, alpha), shared byte-identical with carimport / fetex | explicit, hash-checked game data |
| `tests\test_vehtool_limit.py` | mod kit 0.4.0 copy of the p4.3 limit tests | game data passed to `validate`; the mutants get the package-relative `gamedata.py`; SKIPPED without game data |
| `tests\test_errors.py`, `tests\test_regression.py`, `tests\REGRESSION_SHA256.json` | NEW | actionable errors; byte identity of the example packs (hashes only) |
| `examples\make_veh_packs.py` | mod kit 0.4.0 `examples\authored\veh-series\make_veh_packs.py` (= veh1 `make_veh1_packs.py`) | the vehtool beside it; workspace default removed; docstring (also the README.txt it writes) unchanged |
Licences: BurnoutMashup project code; authored names / colours; no third-party code or assets; no game data shipped.
