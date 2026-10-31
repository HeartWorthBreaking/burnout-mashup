# bmpack 1.4.0 (mod kit 0.5.0) - patch note

- Host readers: the main18 host (platform 0.1.8). Changed reader sources against kit 0.4.4 (capmega1): `src/game/bm_admit.c`, `src/game/bm_admit.h`, `src/game/bm_fetex.h`, `src/game/bm_music.h`, `src/game/bm_platform_table.h`. Every other listed file is byte-identical to kit 0.4.4's copy.
- New limits the readers carry: 256 mods (`BO3_ADMIT_MAX`, was 64), mods with `[bmashup.textures]` 64 (was 16), music mods 64 (was 16; the ST.DB format holds 100 soundtracks), platform 0.1.8.
- `validate` mirrors the loader's mod cap: with more mods than the host takes (256), every mod past the cap is reported as a refusal `[modfs] <folder>: more than 256 mods: the loader ignores it` (RESULT REFUSED, exit 1). With mod paths longer than the Windows command line holds (32,767 characters; about 256 mods) the mod list reaches the checker through a response file (`@FILE`, one `ROOT=i<TAB>DIR` a line, in the checker cache). bmpack 1.3.4 dropped mods past 256 silently, and with the 0.4.4 readers (cap 64) admitted only the first 64 usable mods while reporting the rest as accepted.
- Checker cache key `hr1.4.0` (a 1.3.4 cache is not reused).
- Tests: `gp\slices\main18\tests\limits\run_limits.py` (64 / 65 / 256 / 257 mods with the 0.4.4 and the 1.4.0 readers).
