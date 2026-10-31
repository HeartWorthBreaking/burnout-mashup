# bmpack 1.3 (gp slice deps1, platform 0.1.2) - patch note

New version folder `gp\slices\deps1\tools\bmpack` (copied from `host3\tools\bmpack` 1.2; kit 0.2.0 / 0.2.1 and host3 untouched).

## Changes
- Default host tree: `gp\slices\deps1\tree` (platform 0.1.2; `BMPACK_TREE` overrides).
- Spec `[mod]` takes `platform` (">=X.Y[.Z]"), `requires` (capabilities: services / tables, `"name>=N"`) and `requires_mods`
  (other mods: `"<mod id>"` or `"<mod id> >= X.Y[.Z]"`); they generate the `[bmashup]` table of mod.toml, after the manifest keys:
  ```toml
  [bmashup]
  platform = ">=0.1.2"
  requires = ["bmashup.events >= 5"]
  requires_mods = ["gp.deps-base >= 1.0.2"]
  ```
  `bmpack.json` records them under `mod`. A spec without these keys builds exactly 1.2's bytes (checked: bmp_content_set and the
  four bmp_p3_* sets rebuilt byte-identical, `logs\bmpack13_rebuild_12_sets.json`).
- validate: after modfs's order, the host's dependency order (`bo3_admit_order`, the same code as the game's glue) and
  `bo3_admit_run_deps` with the listed mods that take no part (not usable) as "known"; JSON adds `dependency_moved` and per mod
  `needs` (the Mods page text); the summary shows `dependency order: N moved` and `(REFUSED ALONE by the admission: <needs>)`.
- The admission reason is kept as the game keeps it (up to 699 characters; 1.2 cut at 640) - ROADMAP tooling item.
- Test-only mutants: `BMPACK_MUT=12` (requires_mods left out of mod.toml), `13` (the checker does not apply the dependency order).

## Tests (`tests\test_bmpack.py`, run `test_runs\bmpack13`)
Base 93 / 93 (1.2: 80 + T14's 13), mutants 13 / 13 caught. By-design adaptation D3: T10's version text reads platform 0.1.2.
T14: the generated `[bmashup]`; a malformed spec; the order (base before addon whose id sorts first); an older dependency
refused alone with the reason kept whole; not installed; the capability `bmashup.autopilot >= 2` refused by the platform gate; a
mod in `requires` (the hint to requires_mods); a malformed entry (`==`); a cycle.
