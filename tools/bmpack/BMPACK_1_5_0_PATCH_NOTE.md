# bmpack 1.5.0 (mod kit 0.7.0) - patch note

- Host readers: the main19 host (platform 0.1.9). Changed reader sources against kit 0.5.0 (main18): `src/game/bm_fetex.c`, `src/game/bm_guest.c`, `src/game/bm_guest.h`, `src/game/bm_platform_table.h`. Every other listed file is byte-identical to kit 0.5.0's copy.
- Why: the readers carry the platform version (a mod declaring `platform = ">=0.1.9"` is refused by 1.4.0's 0.1.8 readers) and the 256 MB window / high-zone code of the texture reader.
- No checker / validate behaviour change; mod limits unchanged (256 mods, 64 texture / music mods). `[bmashup.hud]` is not a table the 0.1.9 readers take: a mod declaring it is refused ("needs a newer platform"), as on the host.
- Checker cache key `hr1.5.0` (a 1.4.0 cache is not reused).
- Tests: `gp\slices\main19\tests\limits\run_limits.py` (64 / 65 / 256 / 257 mods with the 0.4.4 and the new readers) and `tests\docs060\test_bmpack150.py` (platform >=0.1.9 accepted, >=0.2.0 refused).
