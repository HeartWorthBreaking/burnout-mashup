# vehtool 0.1.2 - cars, series and paints as data mods

Writes and checks BurnoutMashup data mods that add cars on donor models (`[bmashup.cars]` v2), new car series
(`[bmashup.series]` v1) and paints (`[bmashup.paints]` v1). The host is authoritative; `validate` mirrors its admission rules
so a mod is checked before a launch. Guide with worked examples: `docs\VEH_PACKS.md`. Python 3.11+ (tomllib) for the
commands that read mod.toml; standard library only.

| command | game data? | what it does |
|---|---|---|
| `inspect --game-data DIR` | yes | the retail vehicle list: entries / listed rows per class, rows free, host capacity |
| `inspect-car ID --game-data DIR` | yes | a retail car's palette count and paint-ramp entries (a ramp paint needs >= 2 palettes) |
| `validate MODDIR ... --game-data DIR` | yes | the mods in list order: declarations, references, files, sizes, rows, capacity, paints per car; REFUSED lines name the reasons |
| `palette OUT.bmpal --gradient HI LO [--alpha A]` | no | an authored 256 x BGRA palette (1024 bytes) for a `file` paint |
| `fixture OUTDIR --cars N [--series S] [--id ID]` | no | a registry stress fixture (generated series + cars on donor models, label FIXTURE) |
| `package MODDIR --label L` | no | `bmpack.json` (sha256 + size of every file; AUTHORED / CONTROL / DERIVED / FIXTURE) |
| `version` | no | tool version, package stamp, Python |
Game data: `--game-data "<game-data>"` (the prepared folder with the NTSC-U `default.xbe` and `pveh\`; `--game` is accepted)
or the `BMKIT_GAME_DATA` environment variable (in the mod kit also `bmkit.toml`); read only, every file hash-checked against
`GAMEDATA_SHA256.json`; no default.
Exit codes (mod kit 0.4.1 convention): 0 ok, 1 refused (validate / inspect-car) or invalid input / path, 2 usage, 3 cannot
run (prerequisite missing: Python 3.11, tool files, game data), 4 internal error (report it).

Examples: `py -3 -B examples\make_veh_packs.py <new folder>` writes the AUTHORED packs Neon (series BMNE, 6 cars, 12 ramp
paints), Dust Runners (BMDU, unlock rules), retail-car paints (ramps + an authored file palette), a cross-mod paint, the
21 / 512 / 917-car fixtures and two negative fixtures. They use `model = donor`: no game data inside.

Tests (OUT folders must be new):
```
py -3 -B tests\test_vehtool_limit.py <out> --game-data <data>   65536 / 65537 / 8193-byte manifests, 917-car split, 2 mutants
py -3 -B tests\test_errors.py <out> [--game-data <data>]        actionable errors
py -3 -B tests\test_regression.py <out> [--game-data <data>]    example packs = the content-phase bytes (+ validate them)
```
Without game data the data-dependent checks are SKIPPED (never reported as passed).

Version: 0.1.2 = portable successor of 0.1.1 (explicit hash-checked game data, actionable errors; a late IndexError of
`fixture` with too few `--series` is now a message). Outputs are byte-identical to 0.1.1, so `bmpack.json` and fixture
manifests keep the stamp `vehtool 0.1.1` (`PACKAGE_STAMP`). Labels: AUTHORED = original names / colours / palettes; CONTROL =
retail cars as donors or paint targets (no retail bytes shipped); FIXTURE = generated. No package of this tool contains game
data. Provenance: `PROVENANCE.md`.

## Local-only outputs (project policy)
Everything this tool builds from your own game data is derived from it: keep it on your PC and never upload, share or commit it. Only sources marked AUTHORED are meant to be shared. See `docs/LOCAL_OUTPUTS.md`.
