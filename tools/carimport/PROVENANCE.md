# carimport 0.1.1 - provenance

| file | origin | change |
|---|---|---|
| `carimport.py` | content-phase carimport 0.1.0 (gp tools, worker carimp) | portable: no workspace path, explicit `--game-data` / `BMKIT_GAME_DATA` (kit: also bmkit.toml, via `tools\_lib\bmkit_env.py`; no default), hash-checked donor reads, actionable errors with the kit 0.4.1 exit codes (1 refused - was 3, 3 cannot run, 4 internal), `version` command, `PACKAGE_STAMP` keeps the 0.1.0 output bytes |
| `carimp\bgvlib.py` | VENDORED, byte-identical: the s6 strict Burnout 3 vehicle-model reader / writer (gp atlas cars scripts, our own code), sha256 `b5df11b92d4a9fff8bc3ba5f5e5bdb3566b7a390710616d0cdb1ec2f8ca80a61` | none (pinned in `bgvwrite.BGVLIB_SHA`, checked by `tests\test_regression.py` R1) |
| `carimp\bgvwrite.py` | carimport 0.1.0 | imports the vendored `bgvlib` package-relatively (0.1.0 added a workspace folder to `sys.path`) |
| `carimp\gamedata.py` | NEW (rel1b, alpha), shared byte-identical by carimport / fetex / vehtool | explicit, hash-checked game-data access; inside the mod kit it delegates the folder choice to `tools\_lib\bmkit_env.py` (rel1), stand-alone it applies the same rules (option > BMKIT_GAME_DATA, NTSC-U default.xbe) |
| `carimp\{demo,gltf,model,png,preview,texture,__init__}.py` | carimport 0.1.0 | unchanged |
| `GAMEDATA_SHA256.json` | NEW: sha256 + size of the 244 game-data files the tools read (default.xbe, Data/Frontend.txd, pveh/**) (Burnout 3: Takedown Xbox NTSC-U, the release the host is built against) | hashes only, no game bytes |
| `tests\run_tests.py` | carimport 0.1.0 tests (48 checks) | game data from `--game-data` / environment, hash-checked; SKIPPED (not passed) without it |
| `tests\test_errors.py`, `tests\test_regression.py`, `tests\REGRESSION_SHA256.json` | NEW | actionable errors; byte-identity against the content-phase outputs (hashes only) |
| `examples\coupe`, `examples\wedge` | ORIGINAL, written by `carimport.py demo` (procedural; no retail or third-party input) = mod kit 0.4.0 `examples\authored\carimport` | none; binaries listed in `AUTHORED_FILES.json` |
| `docs\DESIGN.md` | carimport 0.1.0 DESIGN.md | none (workspace-relative references are history) |
Licences: all code here is BurnoutMashup project code; no third-party code or assets. Game data is never shipped.
