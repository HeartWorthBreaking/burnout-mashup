# fetex 0.2.0 - provenance

| file | origin | change |
|---|---|---|
| `fetex.py` | content-phase fetex (gp tools, slice fetex1; unversioned) | version 0.2.0, `version` command; DXT3 / unknown formats, non-power-of-two and unreadable PNGs, bad specs, missing paths and invalid TXDs give messages instead of tracebacks (KeyError / TxdError / SystemExit before); kit 0.4.1 exit codes (3 cannot run, 4 internal; the round-trip internal error was 2); valid inputs produce identical bytes |
| `fetexlib\{codec,png,txd,__init__}.py` | content-phase fetex | unchanged |
| `fetexlib\gamedata.py`, `GAMEDATA_SHA256.json` | NEW (rel1b, alpha), shared byte-identical with carimport / vehtool | explicit, hash-checked game data (only the test suite's retail check uses it) |
| `tests\test_fetex.py` | mod kit 0.4.0 fetex tests (11 checks) | game data from `--game-data` / environment, hash-checked; F1 / F2 SKIPPED without it |
| `tests\test_errors.py`, `tests\test_regression.py`, `tests\REGRESSION_SHA256.json` | NEW | actionable errors; byte-identity against the content-phase outputs (hashes only) |
| `examples\fetex-art\gen_art.py` | fetex1 demo `gen_art.py` (AUTHORED: every pixel computed) | imports fetexlib package-relatively |
| `examples\fetex-art\make_packs.py` | fetex1 demo `make_packs.py` | explicit NEW output folder, the kit's fetex, art beside the set, optional hash-checked `--cars2-files`; mod.toml / LABELS texts unchanged (byte identity) |
| `examples\p43-coupe-photo\*` | mod kit 0.4.0 `examples\authored\bm-coupes\p43-coupe-photo` (procedural coupe photo, p4.3) | none; PNGs in `AUTHORED_FILES.json` |
Licences: BurnoutMashup project code and procedurally generated art; no third-party code or assets; no game data shipped.
