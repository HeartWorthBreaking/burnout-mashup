# fetex 0.2.0 - port notes (rel1b, 2026-10-27)

- Version: TOOL_VERSION 0.2.0 (first versioned fetex; the content-phase tool had no number). TXD / pack outputs byte-identical.
- Kit placement: copy this folder byte for byte to `<kit>\tools\fetex\`. The tool itself reads only the files you name (no game
  data); the test suite's retail check (F1 / F2) resolves game data through `tools\_lib\bmkit_env.py` in the kit, else
  `--game-data` / BMKIT_GAME_DATA, and hash-checks `Data\Frontend.txd`.
- Changed files: `fetex.py` (messages instead of tracebacks: DXT3 / unknown format - was a raw KeyError -, non-power-of-two,
  unreadable PNG, bad spec, missing paths, invalid TXD; `version`; kit exit codes), new `fetexlib\gamedata.py`,
  `GAMEDATA_SHA256.json`; `tests\test_fetex.py` (game data argument, SKIP without it); new `test_errors.py`,
  `test_regression.py`, `REGRESSION_SHA256.json`, `SELFTEST.json`; examples `fetex-art\gen_art.py` (package-relative import),
  `fetex-art\make_packs.py` (explicit new output, optional hash-checked `--cars2-files`), `p43-coupe-photo` (kit 0.4.0 bytes);
  docs `README.md`, `docs\TEXTURE_PACKS.md`, `PROVENANCE.md`, `AUTHORED_FILES.json`.
- Exit codes: 0 ok, 1 refused / invalid input or path, 2 usage, 3 cannot run (`fetex: CANNOT RUN: ...`), 4 internal.
- Game data read: tests only - `default.xbe` (recognition), `Data\Frontend.txd`.
- CLI unchanged: `fetex.py {inspect|validate|extract|rebuild|pack|version} ...`.
- Tests: `tests\test_fetex.py OUT --game-data D` 11 / 11; `tests\test_errors.py OUT --game-data D` 23 / 23;
  `tests\test_regression.py OUT [--cars2-files DIR]` 7 / 7 (8 / 8 with the cars2 files): 23 art PNGs, photo.txd 2f523e51...,
  oceania.txd 501eab45..., p43 photo TXD, the fetex-photo / fetex-oceania-art packs = content phase.
