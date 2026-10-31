# build/ - scripts that build Burnout Mashup from this tree and your own copy of the game

The full guide is `docs/BUILDING.md`. Run the scripts in this order; each prints one JSON verdict line (stdout) and human text
(stderr). Exit codes: **0** done, **1** usage error or a tool failed, **2 REFUSED** (an input is not the pinned one; nothing was
written). Python 3.8+, standard library only; the build step is PowerShell 5.1. Original code, MIT.

| # | script | does |
|---|---|---|
| 1 | `fetch_upstream.py` | upstream Takedawn and xboxrecomp at the pinned commits (git URL or a local clone), tree id and archive digest checked, line-end mode explicit |
| 2 | `apply_layers.py host` | `host/tree`, `host/tree.patch`, `host/toolkit/*.patch` onto them; a hunk applies only if its old block occurs exactly once |
| 3 | `regen.py` | upstream's recompiler on **your** `default.xbe` (retail NTSC-U only); result checked against the pinned generated tree hash |
| 4 | `apply_marks.py` | `host/marks/anchors.json` onto your generated files with exact-anchor refusal (`--release`: the stamp names the marked tree, for the release build) |
| 5 | `build.ps1` | configure + build in a NEW folder with the pinned toolchain (given by path), `BO3_REPRODUCIBLE=ON`, `BMASHUP_IDENTITY=ON` (`-Release`: the release-named `bin/BurnoutMashup.exe`, `BO3_RELEASE=ON`) |
| 6 | `verify.py` | generated-code objects and the exe against `EXPECTED.json` (`--profile dev`: `build`, `release`: `build_release`) |
| 7 | `host_info.py` | `HOST_INFO.json` from the verified build only (exe identity read from the exe, platform / services / tables from the built tree; refuses on any mismatch); also `verify.py --host-info FILE` |

`EXPECTED.json` holds pins and hashes only (toolchain versions, recompiler report, the host layer results, the force-include
list, the reference exe and object hashes). `bmb_common.py` is the shared helper module.

**Local-only:** everything the steps 3 to 5 produce (generated code, objects, the exe, the recompiler's analysis folder and
their logs) is derived from your game. Keep it on your PC; never commit, upload or attach it. The scripts never copy your
`default.xbe`, never write into this repository, and never change a git configuration. A local build is a technical model,
not a legal conclusion (`docs/PUBLIC_STATUS.md`).

The launcher's **Build Mashup** (`launcher/build-mashup.cmd`, `launcher/docs/BUILD_MASHUP.md`) runs these seven scripts in this order (release
profile), caches each step by the identity of its inputs and installs the verified result into `launcher/host-local`.
