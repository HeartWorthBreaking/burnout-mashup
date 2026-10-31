# ps2look - "PS2 look: shadows and sparks" mod, built from your own PS2 disc

Converts four textures of the Burnout 3 PS2 version (your own disc) into an Xbox-format texture dictionary the PC mod loader
reads, plus the mod's `mod.toml`. Background: `gp\slices\main21\notes\C3_9_PS2_SHADOWS_SPARKS.md`. Pure Python 3, standard
library + `gp\tools\fetex\fetexlib` (unchanged; imported).

```
py -3 -B ps2look.py --ps2-global PATH\GLOBAL.TXD --out MOD_DIR
py -3 -B ps2look.py --ps2-root EXTRACTED_DISC_DIR --out MOD_DIR        (finds DATA\GLOBAL.TXD, any letter case)
  [--previews DIR] [--xbox-global PATH\Data\Global.txd] [--force]
py -3 -B tests\test_ps2look.py                                         (self-test; env PS2LOOK_PS2_GLOBAL / _XBOX_GLOBAL / _OUT)
```

## Input
`DATA\GLOBAL.TXD` of **your own** Burnout 3: Takedown PS2 disc, extracted to a folder (any ISO9660 extractor; in this workspace
`PS2\tools\02_extract.py` made `PS2\extracted\b3\DATA\GLOBAL.TXD`). Read only.

## What it does
1. Decodes exactly (`ps2tex.py`, self-contained; checked against the PS2 project's `map_codec.py` and `gsmem.py` by the tests):

   | name | PS2 | decode |
   |---|---|---|
   | blobbyshadow | 64x64 PSMT8 + 256 CLUT | CT32 (w/2 x h/2) upload unswizzle (map_codec rule), CSM1 palette |
   | fxspark | 32x8 PSMCT32 | raster order (CT32 32x8 upload) |
   | fxscrape | 64x64 PSMT4 + 16 CLUT | CT16 32x32 upload replayed in a GS memory model, sampled as T4 |
   | fxpopcornspark | 8x8 PSMCT32 | raster order |

   The GIF upload packet in front of each pixel block (TRXREG size, IMAGE tag size) is checked, so a different layout is refused,
   not mis-decoded. Alpha: PS2 0..0x80 (0x80 = 1.0) -> `min(255, 2 * a)`, the project's established rule (PS2
   `fe_x2b...\scripts\map_codec.py`, `retex...\scripts\texdecode.view`, C3.9 `c3_9_compare.py`). RGB as stored.
2. Writes `MOD_DIR\global_ps2.txd`: the four textures under the same names, each P8 (8-bit index, NV2A swizzle, one palette of
   256 A8R8G8B8 entries), 1 mip - lossless (126 / 42 / 16 / 31 colours). Before writing, the TXD is parsed back by fetexlib's
   strict reader (the layout the host's `bm_fetex_parse.inc` checks), checked against the capability list and decoded back
   pixel for pixel. The PS2 shadow stays 64x64 (the Xbox retail one is a 128x128 DXT5 re-encode with mips).
3. Writes `MOD_DIR\mod.toml`: `bmashup.ps2-look`, `[bmashup.textures]` version 1, `txd = "global_ps2.txd"`,
   `class = "global"` (named entries replace the retail `Data/Global.txd` entries of the same name - host class in development).
   The PS2 spark size (0.017 vs Xbox 0.012) is noted as a later tune row.
4. Optional `--previews`: PNGs of the PS2 decode (and with `--xbox-global` the retail Xbox DXT5 mip 0) and `compare.png`
   (PS2 left, Xbox right, scaled, over a grey checker).

## Tests (`tests\test_ps2look.py`)
Round trip exact RGBA (4/4), the decoder == the PS2 project's decoders, mod.toml keys, refusals (bad magic, missing name,
corrupt upload packet, `--out` inside the tool, case-insensitive `--ps2-root` lookup), and the host's own C check:
`tests\c_check\fx_check_main.c` includes `slices\main21\tree\src\game\bm_fetex_parse.inc` and runs `fx_check_txd` on the written
TXD (compiled with the toolchain's clang into the output folder; skipped if clang / the host sources are missing), plus a
negative control (one reserved header byte set -> refused). Note: the current main21 `fx_parse` still accepts only
`class = "frontend"`; the TXD check itself is class independent.

## Why the output must stay on your PC
`global_ps2.txd` and the previews are EA's art from your own disc. This tool ships no art: you build the mod locally from your
disc, like the kit's demo mods built from your own data. Never copy the output into a package, a repository, a release or an
upload (the tool refuses `--out` inside its own folder).

## Car shadow settings (host patch 129)
`--shadow ps2` (default: the whole soft shadow, the alpha test off as on the PS2), `soft`, `softer` (wider shadows that fade out gradually; tried in game 2026-10-31) or `xbox` (the game's own draw). The generated mod.toml lists every shadow row with its range and both presets as ready-to-copy lines: change the `set = [...]` line to taste; the game reads it at start-up.

## Local-only outputs (project policy)
Everything this tool builds from your own game data is derived from it: keep it on your PC and never upload, share or commit it. Only sources marked AUTHORED are meant to be shared. See `docs/LOCAL_OUTPUTS.md`.
