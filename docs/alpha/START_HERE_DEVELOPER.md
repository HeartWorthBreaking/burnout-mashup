# START HERE - Burnout Mashup developer guide (experimental alpha; written for developer bundle 0.7.0)

For people who write plugins, data mods or tools for the Burnout Mashup platform (host platform 0.1.9 on Takedawn, the native PC
port of *Burnout 3: Takedown*). Unofficial fan project, not affiliated with Electronic Arts, Criterion Games, Microsoft or the
Takedawn project. **Technically verified on one PC; NOT distribution-cleared, NOT legally cleared**: `docs/PUBLIC_STATUS.md` (open
questions: game code, LGPL route, the project name, the relationship to upstream, reverse-engineering notes, derived outputs; the
licences of our own work are set: `LICENSE`, `REUSE.toml`). Written for the private developer bundle 0.7.0; in this source tree the
host is built with BUILD MASHUP (`launcher\docs\BUILD_MASHUP.md`), its expected values are in `build\EXPECTED.json`.

This bundle contains no game, no game data, no generated game code and no executables.

## 1. What the alpha supports
| | Supported | Not supported / not proven |
|---|---|---|
| Host | the reference build **main21** (`bmp-0.1.9+2c8142e65f20`, sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`; the MAINLINE host = main20 (main19 + the MODS menu) + main21 patches 66-130 (traffic, racers, paints, HUD, sound / camera, rules / modes, contacts, tuning, textures)), platform 0.1.9, 25 services | unmodified Takedawn exes (`[bmashup.*]` tables ignored, services missing) |
| OS | Windows 10/11 **x64** (verified: one Windows 11 PC) | **Linux / macOS: not built** (host and SDK examples); Windows 10 / ARM64 / other GPUs: NOT TESTED |
| Plugins | C plugins against SDK 0.7.0 (plugin API 1), llvm-mingw x86_64 UCRT, approved per exact sha256 | raw guest memory is not an API; unverified fixed addresses are not public contracts |
| Data mods | `mod.toml` tables listed in `COMPATIBILITY_REQUIREMENTS.md`, validated with bmpack 1.5.0 / vehtool | |
| Authoring | carimport (cars, DONOR collision / wheels / audio / physics), **trackbuild 0.3.0** (tracks, DONOR Gamedata header / sky / audio; gate V10 - rebuild tracks made with <= 0.2.0), fetex, vehtool | sharing DONOR / DERIVED outputs (RELEASE_STATUS Q9: local only) |
| Experimental | - | **U5: expanded lanes (more than 64) and transitions between tracks / modes after them: EXPERIMENTAL, not generally safe.** trackconv (Revenge conversion): not shipped, not supported |

## 2. What you supply
Your own retail NTSC-U game data (`docs\GAME_DATA.md`); Python 3.11+; for plugins and bmpack's host-reader check llvm-mingw
20260922 ucrt x86_64 + CMake 4.4.4 + Ninja 1.13.2 (`docs\PREREQUISITES.md`; the same archives the tester package's
`BUILD_HOST.md` lists with sha256). Check: `py -3 -B tools\bmkit_doctor.py --game-data <data> --cc <clang> --cmake <exe> --ninja <exe>`.

## 3. The host
Not in this bundle (Q1). Build it with your own game from the **tester package 0.4.0** (`bmashup-alpha-tester-0.4.0`:
`BUILD_HOST.md`, `prepare-deps.cmd`, `build-host.cmd`; a build with the pinned toolchain equals the reference bytes). Private
testers may instead have been given `bmashup-alpha-tester-0.4.0-prebuilt` (prebuilt host only; never uploaded, owner's decision).
`lgpl-source\` in this bundle holds the complete source of the statically linked LGPL-2.1-or-later audio library (APU) with its
compile script, as source for the local build (`lgpl-source\LGPL_NOTE.md`).

## 4. Run an example mod
Put a data mod folder into the tester package's `mods\user` (e.g. `sdk\examples\tune-ai` built output `gp-aitune-topspeed`, or
`examples\authored\veh-series` packs made by `make_veh_packs.py <new folder>`), start `play.cmd`, read
`profile\Roaming\BurnoutMashup\logs\run.log`: `[ADMIT] ... admitted`, your `[MOD]` line, no `FATAL`. MODS page shows it ON.

## 5. Build an example plugin
```
powershell -NoProfile -File sdk\build.ps1 -BuildDir C:\work\sdk1 -LlvmMingw <llvm-mingw dir> -CMake <cmake.exe> -Ninja <ninja.exe>
```
It builds all the example plugins + data examples into `C:\work\sdk1\out\<mod>\`. All of them (capacity included: T1 fixed by trackbuild 0.3.0 and the host's
chevron guard, defect T1) ran together in one race on main21 (release acceptance: 137 mods, 38 plugins, finished first, no fault). Compare the printed sha256 with
`sdk\EXPECTED_BUILD_SHA256.txt` (same toolchain = same bytes). Copy e.g. `out\bmashup-sdk-host-info` into the tester package's
`mods\user`, start the game once: the log prints the approval line for the unapproved module; put
`approved = ["bmashup-sdk.host-info sha256:<hash>"]` into `profile\Roaming\BurnoutMashup\plugin-approvals.toml` (or MODS page >
APPROVE CODE), restart: `[PLUGIN] ... running (plugin API 1)`, then the plugin's own lines (host-info lists the 25 services; it
reports the host as the SDK's reference build (SDK 0.7.0's reference constant names the host main19) - informational,
the platform version is the contract). Your own plugin: copy `sdk\examples\host-info`, change the mod id, follow `sdk\BUILD.md`.

## 6. Create and validate a content pack
- Data pack by spec: `py -3 -B tools\bmpack\bmpack.py build examples\mods\<spec>.toml <out> --game-data <data>`, then
  `py -3 -B tools\bmpack\bmpack.py validate <mods folder> --game-data <data> --cc <clang>` (the host's own readers, shipped as
  source, compile and judge the set exactly as the game will: refusals, dependency order, labels).
- Vehicle series / paints: `tools\vehtool` (`validate`, `package`); bmpack does not run the vehicle checks.
- Track: `tools\trackbuild\tb.py gen-testloop / build / validate / package` with `examples\my_track_package.toml`.
- Car: `tools\carimport\carimport.py validate / package <car.toml> <set> --game-data <data>`.
Label every file AUTHORED / DERIVED / CONTROL; packages with DONOR parts stay local.

## 7. Remove mods and recover progress
Move the mod folder out (or MODS page OFF) and restart: the profile loads, added content disappears, retail fallbacks are used.
Added content stores its progress in `.bmprog` sidecars (never in the game save); putting the mod back restores it. Plugins have
no persistent state beyond `plugin-settings.toml`. Back up `profile\Roaming\BurnoutMashup` before experiments
(tester package `remove.cmd backup`).

## 8. Diagnostics and reporting
`py -3 -B tools\bmdiag\bmdiag.py --bundle <tester package> --out <zip>` (no saves, progress, game files, mod contents; user name
redacted; prints its file list). Logs: `[PLATFORM]`, `[ADMIT]`, `[DEPS]`, `[MOD]`, `[PLUGIN]`, `FATAL` (`docs\DEBUGGING.md`).
Report through the repository's issue templates once the project has opened them; never attach exes, game files, derived packs or saves.
Contributing: `docs\CONTRIBUTING.md` - keep `tools\kit_selftest.py` passing, no machine-specific paths, standard-library Python,
actionable errors. The licence for contributions is not decided yet (Q3): ask before sending code.

## 9. Versions and where things are
| | |
|---|---|
| host platform | 0.1.9 (mainline reference build main21 `bmp-0.1.9+2c8142e65f20`; capacity table: `docs\services\CAPACITY.md`) |
| SDK | 0.7.0 (headers unchanged since kit 0.4.0) |
| mod kit / this bundle | 0.7.0 (`KIT_MANIFEST.json`, `docs\CHANGELOG.md`) |
| tools | bmpack 1.5.0, trackbuild 0.3.0, carimport 0.1.1, fetex 0.2.0, vehtool 0.1.2, bmdiag 0.1.0, bmkit_doctor 0.1.0, kit_selftest 0.1.0 |
| `SERVICE_CATALOGUE.md`, `COMPATIBILITY_REQUIREMENTS.md` | services / tables and what a plugin / mod / tool must meet |
| `sdk\`, `tools\`, `examples\`, `docs\` | the mod kit 0.7.0 |
| `lgpl-source\` | LGPL APU library source kit (source only) |
| `docs/PUBLIC_STATUS.md` | the open questions of this source tree |
