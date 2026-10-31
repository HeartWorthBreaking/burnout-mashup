# bmpack 1.3.3 (mod kit 0.4.0, worker d1) - patch note

Base: the p4.3 integration copy 1.3.2 (`gp\integration\p4_3\tools\bmpack`: 1.3 + `bm_wt4.c` linked (1.3.1) + `bm_fetex.c` linked
(1.3.2)). Kit 0.3.0 / 0.3.1 copies untouched.

## Change (REMAINING_WORK A13)
- In a host tree with wt4 (platform 0.1.5+), the checker now parses every usable mod's `[bmashup.world_tour]` with the host's own
  `bo3_wt4_parse` BEFORE the World Tour events, as the game does (`bo3_wt4_game_declare` before the events). bmpack 1.3.1 / 1.3.2
  refused such a mod falsely ("OC_L1 is not a race location ... nor the location of a World Tour region a mod declares").
  A world_tour declaration the host refuses is reported as `[world_tour] <mod>: <reason>`.
- `bmpack.py`: `TOOL_VERSION = '1.3.3'`; `-DBMPACK_WT4=1` for the checker when the tree has `bm_wt4.c` (checker cache key grows
  by a tag); test-only mutant `BMPACK_MUT=14` (the world_tour parse skipped).
- Output format (`VERSION = '1'`) unchanged: every build output is byte-identical to 1.3.x.

## Tests (`tests\test_bmpack.py`)
Base 96 / 96 (93 + T15a / T15b x2); T15 uses `BMPACK_TREE` = `gp\integration\p4_3\tree_p43` (a tree with wt4 and fetex1):
T15a the launched 4th-region mod `runtime_data\modsets\gp_wt4_set\bmashup-wt4-oceania` ACCEPTED with its two events; T15b a
location the events do not use -> `[events-resolve]` refusal; a world_tour region no mod declares -> `[world_tour]` refusal.
MUT 14 caught (94 / 96: the old false refusal comes back). Mutants 1-13 as before.
