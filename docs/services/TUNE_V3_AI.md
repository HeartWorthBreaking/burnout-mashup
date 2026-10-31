# bmashup.tune 3 and `[bmashup.tune] version = 2` - the 73 AI ValueDB values (signed bounds)

Header: `sdk\include\bmashup_tune.h` (`BM_TUNE_VERSION 3`, `bm_tune_info` 200 bytes). Platform table `tune` 2. Example:
`sdk\examples\tune-ai` (data mods `gp.aitune.topspeed`, `gp.aitune.aggression`).

## What is new in version 3
- The catalogue (158 entries) adds the AI's 73 ValueDB values after the scoring / boost entries: `AI/Car` (top / min speed
  ...), `AI/Arbitrator`, `AI/Avoidance`, `AI/Target`, `AI/Driver`, `AI/Aggressive Driving`, `.../Slam`, `.../Reactions`.
- **Signed entries** (a negative default or ValueDB value, or read as a signed integer) take `-bound .. +bound`, bound =
  16 x max(|shipped|, |game|, 1). Others stay `0 .. bound`.
- `info()` adds `min`, `is_signed`, `applies`: `NEXT_USE` (re-read at every use: 69 values), `NEXT_RACE` (read once per racer
  at the race set-up: the start delay of aggressive driving), `NEVER` (3 values the build never reads: UNSUPPORTED).
- Version 2 callers (184-byte struct) are unchanged.

## As a data mod
```toml
[bmashup]
requires = ["bmashup.tune>=3"]

[bmashup.tune]
version = 2                                   # needed for AI values and for negative values
set = ["AI/Car | Top speed mps = 40"]
```
An older host refuses that mod alone ("needs a newer platform"). The admission labels it: log `[MODS] <id> <ver> changes
gameplay: ai (Top speed mps 80 -> 40)`, Mods page `CHANGES GAMEPLAY: AI`. Two mods setting one value: the later one is
refused (CONFLICT). Timing: the declaration is applied at host start and re-written after the game's ValueDB copy at the end
of its boot; it holds for every race.

## Evidence
- **RUNTIME-VALIDATED** for one value (Top speed 40): gp_aitune1_1 (rival caps 40.0 only vs 88 baseline; mean rival speed
  39.7 vs 54.9 m/s; a launch overshoot to 48.1 m/s at t 4-8 s) and on p4.1 gp_p41_2 vs the same-exe baseline gp_p41_3 (caps
  40 vs 52.4..88). `155 of 158 tuning values verified on this game build` (the 3 never-read values UNSUPPORTED, as predicted).
- OFFLINE only: signed values, the start delay (next race), the aggression example, a plugin `set()` during a race; the
  `CHANGES GAMEPLAY: AI` page text (the log line was seen at runtime).

## Evidence update (kit 0.3.1)
**p4.1** (gp_p41g_1): a SIGNED integer value (-12) read back and the race diverged from 35 s - RUNTIME-VALIDATED; the start
delay (60) read back only, its effect not observed - INCONCLUSIVE. The aggression example and AI aggression behaviour stay OPEN.
