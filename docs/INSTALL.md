# Installing the Burnout Mashup host (main21) + mod kit 0.7.0 - EXPERIMENTAL ALPHA, Windows x64

**Experimental alpha, written for the private mod kit 0.7.0. Windows x64 only.** In this source tree you build the host with BUILD
MASHUP (`launcher\docs\BUILD_MASHUP.md`): the release build is `BurnoutMashup.exe`, its expected sha256 and identity are in
`build\EXPECTED.json`; the values below are those of the private reference build. Host: **main21**, **Burnout Mashup platform 0.1.9**, sha256
`f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`, build identity **`bmp-0.1.9+2c8142e65f20`** (main21 = main20 (the MODS menu) + the main21 patches 66-130; technically verified, not distribution-cleared). The exe is NOT in this tree and is not handed out at all: you BUILD it with your own game
from the host source package in the **alpha tester package** (`bmashup-alpha-tester-0.4.0`: `BUILD_HOST.md`, `build-host.cmd`,
notices, `play.cmd` / `preflight.cmd` / `prepare.cmd`, demo mods, its own INSTALL guide); the build is `host\burnout3_bmashup.exe`
with exactly the bytes above. Platform 0.1.9 and kit 0.7.0 are different version domains (VERSIONING.md).

## Installation checklist (in order)
1. [ ] **Prerequisites:** Windows 10/11 x64 (tested: Windows 11 only); a GPU + driver with Vulkan (`System32\vulkan-1.dll` from
   the driver); your own retail NTSC-U Burnout 3 data (`GAME_DATA.md`); for building: `PREREQUISITES.md`. No Visual C++
   redistributable. Check: `py -3 -B tools\bmkit_doctor.py`.
2. [ ] **Host folder:** the tester package unpacked into a NEW folder (never into a Takedawn install), the host built into its
   `host\` (`build-host.cmd`); its `preflight.cmd` checks
   the exe hash, SDL2.dll, the Vulkan loader and your game data. Never put a `vulkan-1.dll` beside the exe.
3. [ ] **Game data:** the bundle's `prepare.cmd data ...` (or your Takedawn data folder, `GAME_DATA.md`); the kit tools take
   `--game-data "<data root>\Burnout 3 Takedown"`.
4. [ ] **Profile + launcher:** the bundle's `play.cmd` keeps settings, saves, logs and progress inside the bundle (s2 shows the
   same layout by hand).
5. [ ] **Build the plugins:** `powershell -NoProfile -File sdk\build.ps1 -BuildDir <dir> -LlvmMingw <dir> -CMake <exe> -Ninja <exe>`;
   compare the printed sha256 with `sdk\EXPECTED_BUILD_SHA256.txt` (same bytes = the kit's reference build). The kit ships NO
   prebuilt modules (and no game files: added cars / regions are generated from your own data, s3a).
6. [ ] **Mods:** copy data mods into a mods folder (the bundle's `mods\user`; bmpack-built packs from `examples\mods`,
   `<build>\out\gp-aitune-*`, the music pack from `make_tones.py`) and plugin mods (`<build>\out\bmashup-sdk-*` with an `.asi`).
   Validate: `py -3 -B tools\bmpack\bmpack.py validate <mods folder> [<mods folder> ...] --game-data "<game data>"`
   (refusals, dependency order, labels as the game; it needs llvm-mingw: `PREREQUISITES.md`).
7. [ ] **Approve plugins** by exact sha256 (s4): in the game, Settings > MODS > select the mod > Approve and turn on > Restart now (the approval screen shows the plugin's SHA-256).
8. [ ] **Back up saves** (s6), start `play.cmd`, check `profile\Roaming\BurnoutMashup\logs\run.log`: `[PLATFORM] host: Burnout
   Mashup platform 0.1.9, build bmp-0.1.9+2c8142e65f20 ...`, `25 services offered to plugins (bmashup.host first), as the
   platform table says`, your `[MOD]` / `[DEPS]` / `[ADMIT]` lines, no `FATAL`. A problem: `DEBUGGING.md`, `tools\bmdiag`.
9. [ ] **Remove a mod:** MODS page OFF or move the folder out; restart.

`tools\kit_selftest.py` runs every tool's tests from the kit (no launch). The alpha's onboarding run (a clean folder outside the
developer tree, minimal environment, same machine) is recorded in the alpha reports; a second machine has not been tried yet.

## 1. What is supported - and what is not
(a) **Supported:** one platform host exe, many drop-in mods (data mods and approved plugins). Every `bmashup.*` service and
`[bmashup.*]` table exists only because the host exe was built with it. (b) **Not supported:** kit mods on an unmodified
Takedawn exe: only Takedawn's plugin API exists there, every `[bmashup]` table is ignored silently, SDK plugins report their
services missing. Older platform hosts refuse mods that need 0.1.6 features ALONE (`needs a newer platform`):
p3 (0.1.1) refuses `requires_mods`, `[bmashup.music]`, `[bmashup.tune] version = 2` and every service p4 added.

## 2. Folders and `play.cmd`
```
<play root>\
    bin\                      burnout3_bmashup.exe, SDL2.dll, shaders\upscale\ (your build)
    gamedata\                 a COPY of your game data
    profile\Roaming\          APPDATA: Takedawn\settings.toml, mod-list.toml, plugin-approvals.toml, plugin-settings.toml,
                              saves (UDATA), logs\run.log, bmashup\progress\...\*.bmprog
    profile\Local\            LOCALAPPDATA: shader cache, data-folder.txt, BurnoutMashup\music-cache\set-*\ (music mods)
    mods\content\, mods\plugins\
    play.cmd
```
```
@echo off
set ROOT=%~dp0
set APPDATA=%ROOT%profile\Roaming
set LOCALAPPDATA=%ROOT%profile\Local
set BMASHUP_DATA=%ROOT%gamedata
set BMASHUP_MODS=%ROOT%mods\content;%ROOT%mods\plugins
cd /d "%ROOT%bin"
burnout3_bmashup.exe
```
With APPDATA / LOCALAPPDATA redirected, settings, mod list, approvals, plugin settings, saves, logs, the progress sidecar and
the music cache stay under `<play root>\profile`. To start from your own saves, COPY `%APPDATA%\BurnoutMashup\UDATA` (never move it).

## 3. Mods folders, order and dependencies
`BMASHUP_MODS` names up to 8 folders (`;`); every subfolder with a `mod.toml` is a mod; at most 64 mods. Order: folders in
`BMASHUP_MODS` order, then mods by id - then (platform 0.1.2+) the **dependency order**: every mod after the mods its
`requires_mods` names (`[DEPS] the mod list in dependency order ...`). The admission and the services follow this order; of two
clashing mods the LATER one is refused. Every mod is ON unless `mod-list.toml` (`disabled = [...]`) or the MODS page turns it off.
bmpack 1.5.0 validates with the reference host's own readers (main21's own sources), shipped as source in `tools\bmpack\host_readers` (no host tree needed).

### 3a. Added cars and a 4th World Tour region (platform 0.1.6)
The kit ships only their mod.toml and generators: `py -3 -B examples\content\added-car\make_added_car.py --data "<game>\Burnout 3
Takedown" --out <new folder>` and `...\wt-region\make_wt_region.py` (same arguments) write complete mod folders from YOUR OWN
retail data (inputs checked by sha256). Copy them into `mods\content`. They contain retail data: local only, never share them.
Borrowed-map limits and the region page's hold-to-repeat (script presses <= 100 ms) of the region: `docs\services\WORLD_TOUR.md`.

## 4. Approvals, labels, settings
- A plugin runs only when its exact bytes are approved. In the game: Settings > MODS > select the mod > Approve and turn on > Restart now (the approval screen shows the exact SHA-256;
  MOD SETTINGS lists the plugin's settings). Alternatively add `approved = ["<mod id> sha256:<64 hex>"]` to
  `<APPDATA>\Takedawn\plugin-approvals.toml` by hand (still valid). The log prints the line to add for an unapproved
  module. Deterministic builds (`-Wl,--no-insert-timestamp`) keep an approval valid across rebuilds with the same toolchain.
- Data mods need no approval; gameplay-changing ones are labelled (log `[MODS] <id> <ver> changes gameplay: ...`, Mods page
  `CHANGES GAMEPLAY: BOOST, SCORING, CAPACITY, AI`).
- MODS > **MOD SETTINGS**: plugin settings (`bmashup.settings`) and the host's group BURNOUT MASHUP (GARAGE PAINT 7-8, default
  OFF); saved in `plugin-settings.toml` at once.

## 5. What is refused, and how (platform 0.1.9)
**A. One mod refused, the game starts without it:** `platform` newer than the host; a table version newer than the host reads
(e.g. `[bmashup.tune] version 3`); an unknown key / table; `requires` a service or version the host does not offer
(`needs bmashup.autopilot >= 3; this host (platform 0.1.9) offers version 2`); a clash with an EARLIER mod (track id / name /
location, region letter, event key, a location's rows, track-list capacity, a tuning value, a soundtrack name, a music replace);
**a required mod** not installed / switched off / not usable / older than required / refused / in a cycle (`NEEDS MOD`, Mods page
detail e.g. `NEEDS GP.DEPS-BASE MIN 1.1: HAS 1.0.2` - the page text since p4.1, runtime-seen on p4.2 (gp_p42_5); on p4.3 the deps set gave 8 admitted / 3 refused (gp_p43_3); p4 showed `> =`). Log: `[PLATFORM] mod <id> <ver> refused ...` or `[ADMIT] mod <id> <ver>
(<folder>) refused, the game starts without it: <reason>`.
**B. The start stops** (a mod's OWN invalid table or a host guard; log line, message box, exit code): 88 track route data too
large, 89 unit slot, 90 STATIC, 91 capacity, 92 content declaration / host out of memory, 93 tune above its bound, 94 added
track in an unsupported mode, 95 / 96 World Tour launch / data, 97 more lanes than the capacity. (Unchanged since p3; on p4.4 and main21
OFFLINE-VALIDATED through the regression suites.)

## 6. Save safety
Added content writes the `.bmprog` sidecar, never the game's save records; the host writes nothing into the saves for music
(p4.1 / p4.2 stage music in the host cache; the upstream toolkit itself keeps `TDATA\FFFE0000\MUSIC.HOST`). The paint 7 / 8 choice is
run-time state (not saved). Back up `UDATA` and `bmashup\progress` before trying mods; never point the host at your Takedawn
save folder.

## 3b. Content authoring tools (platform 0.1.6)
Build content locally from AUTHORED sources and your own game data (donor parts), then install the package folders into
`mods\content`: cars (`tools\carimport`: glTF 2.0 -> `[bmashup.cars]` package), tracks (`tools\trackbuild`: OBJ -> `[bmashup.tracks]`
package), front-end art (`tools\fetex pack` -> `[bmashup.textures]`), series / paints (`tools\vehtool validate / package`). Validate a
set with bmpack 1.5.0 AND `vehtool validate` (bmpack does not run the vehicle checks). Packages with donor parts are LOCAL ONLY.
Docs: `docs\services\AUTHORING_TOOLS.md`, `CARS.md`, `TEXTURES.md`, `WT_MAP_ART.md`, `LIMITS.md`; examples: `examples\authored`.
