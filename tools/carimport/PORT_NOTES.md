# carimport 0.1.1 - port notes (rel1b, 2026-10-27)

- Version: TOOL_VERSION 0.1.1 (successor of content-phase 0.1.0); PACKAGE_STAMP 0.1.0 (outputs byte-identical, so the stamp in
  mod.toml / carimport.json stays).
- Kit placement: copy this folder byte for byte to `<kit>\tools\carimport\`. Inside the kit, game data is resolved by
  `tools\_lib\bmkit_env.py` (option > BMKIT_GAME_DATA > bmkit.toml, NTSC-U default.xbe); the folder also works stand-alone
  (option > BMKIT_GAME_DATA). The strict reader is vendored as `carimp\bgvlib.py` (byte-identical to the kit's
  `_vendor\bgvlib.py`, sha256 b5df11b9...0a61); no other import outside this folder except the optional kit resolver.
- Changed files: `carimport.py`, `carimp\bgvwrite.py` (package-relative bgvlib), new `carimp\gamedata.py`, `carimp\bgvlib.py`,
  `GAMEDATA_SHA256.json`, `tests\run_tests.py` (game data argument); new tests `test_errors.py`, `test_regression.py`,
  `REGRESSION_SHA256.json`, `SELFTEST.json`; docs `README.md` (quick start), `docs\ADVANCED.md`, `PROVENANCE.md`,
  `AUTHORED_FILES.json`; examples = kit 0.4.0 `examples\authored\carimport\{coupe,wedge}` (unchanged bytes).
- Exit codes now follow the kit convention: 1 refused (0.1.0: 3), 2 usage, 3 cannot run (`carimport: CANNOT RUN: ...` on
  stderr), 4 internal. No C compiler is needed by any command.
- Game data read (need list): `default.xbe` (folder recognition), the donor's `pveh\<CLASS>\<CAR>.bgv / .hwd / .lwd`; tests
  also every `pveh\*\*.bgv` (T2). Every file is sha256-checked against `GAMEDATA_SHA256.json`.
- CLI: `carimport.py {demo|inspect|validate|import|build|package|export-bgv|preview|version} ... [--game-data DIR] [--json]`;
  the tester bundle's form `package <car.toml> <out set> --game-data <game data>` is unchanged.
- Tests: `tests\run_tests.py --game-data D` 48 / 48; `tests\test_errors.py OUT --game-data D` 27 / 27;
  `tests\test_regression.py OUT --game-data D` 5 / 5 (coupe CIC1.bgv ed977c8a..., wedge CIW1.bgv d1258dc9..., every package
  file = content phase). Run stand-alone and in the kit layout from a clean folder outside the developer tree under an
  access guard (same machine).
