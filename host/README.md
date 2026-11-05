# host/ - the Burnout Mashup host as layers

| path | what | licence |
|---|---|---|
| `PINS.json` | upstream commits, tree ids, pristine-gen hash, toolchain pins | MIT |
| `LAYERS.json` | per layer: added files, modified files with base / result sha256, patch hunk counts | MIT |
| `tree/` | files added to Takedawn (`4f074e211822`), at their tree paths (incl. the identity layer and the original icon) | MIT (icon: project artwork, `../LICENSES/LicenseRef-BurnoutMashup-Artwork.txt`) |
| `tree.patch` | our hunks in upstream Takedawn files (position-free: every old block occurs exactly once) | MIT (context lines: upstream MIT) |
| `toolkit/toolkit.patch` | our hunks in MIT xboxrecomp files (`e3756d1b2fef`) | MIT (context: upstream MIT) |
| `toolkit/added/` | files added to xboxrecomp, at their paths in that tree | MIT |
| `toolkit/lgpl/apu_core.patch` + `NOTICE` | our hunks in the LGPL files `src/apu/apu_core.c`, `apu.h`, `apu_state.h`, `apu_vp.c` (the file name is kept from earlier releases) | **LGPL-2.1-or-later** |
| `marks/` | hook marks as address anchors + Mashup text (`anchors.json`), accessor macros (`include/bm_gen_access.h`), tools | MIT |

No generated game code, no exe, no object file is here. The generated files are made on the user's PC (`docs/BUILDING.md`).
