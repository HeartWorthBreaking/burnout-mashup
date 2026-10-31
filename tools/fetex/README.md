# fetex 0.2.0 - front-end texture tool (texture packs for `[bmashup.textures]`)

Reads, checks, extracts and builds Criterion texture dictionaries (`.txd`, the format of Burnout 3's `Data\Frontend.txd`) for
BurnoutMashup texture-pack mods: garage photos, World Tour map art, markers. Pure Python 3.8+ standard library; no game data
needed to build packs. Guide with worked examples: `docs\TEXTURE_PACKS.md`.

```
py -3 -B fetex.py inspect  FILE.txd [--json]           list entries: name, format, size, palettes, bytes
py -3 -B fetex.py validate FILE.txd [--class frontend] strict structure + the front-end capability list (exit 1 if refused)
py -3 -B fetex.py extract  FILE.txd OUTDIR [--name REGEX] [--all-palettes]   decode to PNG (P8 / DXT1 / DXT5)
py -3 -B fetex.py rebuild  FILE.txd OUT.txd             parse + re-emit; says BYTE-IDENTICAL or DIFFERENT
py -3 -B fetex.py pack     SPEC.json OUT.txd            PNGs -> TXD, then validated and round-tripped
py -3 -B fetex.py version
```
Exit codes (mod kit 0.4.1 convention): 0 ok, 1 refused / invalid input or path (the message says what to change), 2 usage,
3 cannot run (prerequisite missing: Python 3.8+, tool files), 4 internal error (report it).

Pack spec (JSON, paths relative to the spec):
```json
{"tag": 0, "entries": [
  {"name": "compbm01_photo", "png": "photo/paint0.png", "format": "P8", "palettes": ["photo/paint1.png", "photo/paint2.png"]},
  {"name": "oceania_tile_1_1", "png": "tiles/1_1.png", "format": "DXT1"},
  {"name": "oceania_marker", "png": "marker/icon.png", "format": "DXT5"}]}
```
Front-end capability list v1 (the host admits the same): formats P8 (1..8 palettes of 256 BGRA colours), DXT1 (opaque), DXT5
(alpha); sides powers of two 4..1024; 1 mip; <= 64 entries per file; <= 1 MiB per entry; names `[a-z0-9_.-]{1,31}` (registered
as `<mod-id>/<name>`). Refused with the reason: DXT3, ARGB, 16-colour P8, mips, cube / volume textures, non-power-of-two
pictures, 16-bit / interlaced PNG, palette pictures that are not the same picture.

Examples (AUTHORED, every pixel computed by code): `examples\fetex-art` (`make_packs.py NEW_SET` builds fetex-photo and
fetex-oceania-art), `examples\p43-coupe-photo` (a 6-paint photo of the carimport coupe).

Tests (OUT folders must be new):
```
py -3 -B tests\test_fetex.py <out> [--game-data <data>]   11 checks; F1 / F2 rebuild YOUR retail Frontend.txd (hash-checked)
py -3 -B tests\test_errors.py <out>                      actionable errors
py -3 -B tests\test_regression.py <out>                  art, TXDs and packs = the content-phase bytes
```
Game data (only for F1 / F2): `--game-data "<game-data>"` (the prepared folder with the NTSC-U `default.xbe`) or
`BMKIT_GAME_DATA` (kit: also `bmkit.toml`); without it F1 / F2 are SKIPPED. Extracting the retail dictionary is for local inspection only; never ship retail art.

Version: 0.2.0 is the first versioned fetex (the content-phase tool had no number); outputs are byte-identical to it.
Provenance: `PROVENANCE.md`.

## Local-only outputs (project policy)
Everything this tool builds from your own game data is derived from it: keep it on your PC and never upload, share or commit it. Only sources marked AUTHORED are meant to be shared. See `docs/LOCAL_OUTPUTS.md`.
