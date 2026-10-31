# bmpack 1.5.0 (mod kit 0.7.0) - build, validate and verify Burnout Mashup content mods

`bmpack.py` builds content mods (added tracks, regions, World Tour events, tune / capacity tables) from one declarative spec,
validates mod folders with the HOST's own readers in the game's boot order, and verifies a built mod against its `bmpack.json`.
Full reference: the docstring of `bmpack.py`; patch notes `BMPACK_1_2_PATCH_NOTE.md` .. `BMPACK_1_5_0_PATCH_NOTE.md`.

    py -3 -B bmpack.py build SPEC.toml OUT_SET --game-data DIR [--with ROOT ...] [--no-validate] [--cc FILE] [--cache DIR]
    py -3 -B bmpack.py validate ROOT [ROOT ...] --game-data DIR [--json] [--cc FILE] [--cache DIR]
    py -3 -B bmpack.py verify MOD_DIR

- **Game data**: YOUR OWN NTSC-U data (`docs\GAME_DATA.md`), read only: donor tracks for `build`; `Tracks\tlist.bin`,
  `Data\PrgData.bin`, `Data\stagehed.bin`, `Data\Globalus.bin` for `validate`. `--game-data` > `BMKIT_GAME_DATA` > `bmkit.toml`.
- **Compiler** (validate only): llvm-mingw's `x86_64-w64-mingw32-clang.exe` (`docs\PREREQUISITES.md`); `--cc` > `BMKIT_CC` >
  `BMKIT_LLVM_MINGW` > `bmkit.toml` > PATH. The first validate compiles the checker (about a minute) into the cache
  (`--cache` > `BMPACK_CACHE` > `.\_bmpack_cache`); later runs reuse it.
- **Host readers**: `host_readers\` = the reference host's own mod readers (kit 0.6.0: main19, platform 0.1.9) / admission code as SOURCE (Takedawn, MIT) + xboxrecomp's
  `recomp_cfg` (MIT); `HOST_READERS.json` lists every file with its origin and sha256. No generated game code, no game data.
- Exit codes: 0 accepted / built / verified, 1 refused (each refusal names its service and the host's reason), 2 usage,
  3 a prerequisite or setting is missing (the message says what to do).
- Tests: `py -3 -B tests\test_bmpack.py <new folder> --game-data DIR [--cc FILE]` (96 checks + 14 mutants; ~15 minutes).
- Built packs contain retail data from your donor tracks: local only, never upload them.
