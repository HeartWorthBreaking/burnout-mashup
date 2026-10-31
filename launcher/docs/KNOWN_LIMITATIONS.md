# Known limitations (alpha, host platform 0.1.9; candidate 0.4.0-rc)

Status words: RUNTIME-VALIDATED (seen working in a guarded test run), OFFLINE (tests only), INCONCLUSIVE, OPEN (known problem /
unexplored), EXPERIMENTAL (may break), DONOR (uses retail parts from your data), NOT TESTED.

## Platform and environment
- Windows 10/11 x64 only; everything was run on ONE Windows 11 PC with one GPU. Windows 10, ARM64, other GPUs / drivers,
  laptops with two GPUs: NOT TESTED - your reports are the point of this alpha.
- Retail NTSC-U game only.
- Widescreen 16:9 / ultrawide FOV paths and split screen: NOT TESTED with the platform.
- The host has no setup window; the game data step is `prepare.cmd data`. No prebuilt host is included in this source tree (recompiled game code: Q1 / Q2 open, NOT legally cleared): you build your own on your PC with BUILD MASHUP (`launcher\docs\BUILD_MASHUP.md`).
- Linux / macOS: NOT BUILT (the host and the SDK examples are Windows x64 only in this alpha).
- Plugins (`.asi`) run with full rights inside the game; approve only modules you built or trust.

## Content
| Area | Status |
|---|---|
| Authored car (carimport) | RUNTIME-VALIDATED geometry / texture / paints; **DONOR** collision hull, wheels, engine audio, physics, crush basis |
| Authored track (trackbuild) | RUNTIME-VALIDATED geometry, collision, route, grid, traffic, LOD, PVS; **DONOR** Gamedata header / event records, sky, audio; off-track reset INCONCLUSIVE; closed circuits only |
| Expanded lanes (> 64) and transitions between tracks / modes after them | **EXPERIMENTAL, not generally safe** (U5: stale pointers, also with larger registries / asset reloads) |
| 4th World Tour region | region page globe / counters BORROWED from USA |
| Registered paints on garage photos | two visible rows sharing one photo texture show the last row's paint |
| Vehicle list | 1024 entries configured; the 917-added-car tier NOT tried at runtime (not part of this alpha's tests) |
| Texture / palette allocation failure, language switch | NOT tried at runtime (behaviour unknown) |
| `file` paints | offline only |
| AI aggression, added Crash events, chase camera, effects | not available (OPEN) |
| AI start-delay value | INCONCLUSIVE |
| Revenge track imports / trackconv | workspace-only, **not supported in this alpha** (White Mountain cloud fix unresolved) |

## Saves
- Added content writes `bmashup\progress\*.bmprog` sidecars, never the game's save records; removing a mod keeps the profile
  loadable (RUNTIME-VALIDATED). Still: back up `profile\` before testing.
- Paint 7 / 8 (GARAGE PAINT 7-8 setting) is not saved across starts.

## Tools
- Python 3.11+; generators and validators read your game data (read only).
- bmpack's host-reader check needs a C compiler (llvm-mingw).
- fetex refuses an unsupported texture format (DXT3) with a raw `KeyError` text (still a refusal; cosmetic).
- Linux / macOS builds of the SDK examples: not done.

## Launcher and lifecycle (candidate 0.4.0-rc)
- The launcher needs Python 3.11 or newer with tkinter (the python.org installer includes it). Without it,
  "Burnout Mashup.exe" (or .cmd) says what to install. OFFLINE.
- Dropping files on the window uses a Windows message hook; when it is not available, Browse and dropping onto
  "Burnout Mashup.exe" / .cmd still work. OFFLINE.
- The compatibility check is an early warning built from the host's own platform table; the game's admission at start is the
  final word (the Play tab shows its verdict). OFFLINE.
- Hand-edited plugin-settings.toml: an on / off setting must be written in lower case (`on` / `off`); choice settings ignore
  case. The game's MOD SETTINGS page always writes the right text. RUNTIME-VALIDATED (C2 run 1).
- Window layout checked at 1920x1080 and 2560x1440 at 100 / 125 / 150 % scaling and on a 3840x2160 panel at 300 % (simulated
  displays on one PC). Other PCs, standard (non-administrator) accounts and screen readers: NOT TESTED.
- Downgrade (an older package using a newer package's profile): not supported; keep the backup.
- Only this package's own folder is written; on another PC it is NOT TESTED whether antivirus or OneDrive-synced folders
  interfere (unpack outside OneDrive, e.g. C:\Games).
