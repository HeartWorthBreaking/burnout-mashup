# START HERE - Burnout Mashup tester guide (experimental alpha; written for tester package 0.4.0)

Burnout Mashup is an experimental modding platform for **Takedawn**, the native PC port (static recompilation) of the Xbox game
*Burnout 3: Takedown*. It is a host program with versioned services for native plugins (`.asi`) and data-only mods (`mod.toml`):
new car series and paints, garage photos, authored cars and tracks, World Tour events, AI / traffic / physics tuning, music packs.

**Experimental alpha.** Unofficial fan project, not affiliated with Electronic Arts, Criterion Games, Microsoft or the Takedawn
project. **Technically tested by the authors on one PC; NOT distribution-cleared and NOT legally cleared** - questions about rights,
licences and naming are open (`docs/PUBLIC_STATUS.md`). Keep everything you build from your game on your PC.

> **In this source tree:** this guide was written for the private tester package 0.4.0 and is kept for its tester steps. There is
> **no prebuilt host** here (Option A below does not exist in this tree): build the host on your PC from your own game with
> **BUILD MASHUP** (launcher Setup tab > *Build Mashup...*, or `build-mashup.cmd`; `launcher\docs\BUILD_MASHUP.md`,
> `launcher\docs\QUICKSTART.md`). Its result is `host-local\BurnoutMashup.exe`; the expected sha256 and build identity are in
> `build\EXPECTED.json` (the values quoted below belong to the private 0.4.0 reference build `main21`).

## The easiest way: the launcher
Double-click **`Burnout Mashup.exe`** (the blue Burnout Mashup icon; `Burnout Mashup.cmd` does the same). Windows may show
"Windows protected your PC" the first time because the exe is not code-signed: More info > Run anyway. The window has four tabs:
- **Setup** - choose your game data (Browse, or drag and drop), check this PC (every problem comes with a fix), build the demo mods.
- **Mods** - turn mods on and off; import a mod folder or zip and see what it is and its compatibility verdict
  (OK / WARN / BLOCKED) before anything is copied.
- **Play** - start the game; afterwards the tab shows which mods were admitted or refused, and why.
- **Help** - troubleshooting, diagnostics export, profile backup, update from an older folder, verify / repair, remove files that
  can be re-created.
A one-page guide with screenshots: `docs\QUICKSTART.md`. The `.cmd` steps below do the same things from a Command Prompt.
In this source tree the host program is not included: build it first with BUILD MASHUP (`launcher\docs\BUILD_MASHUP.md`).

## 0. Two ways to get the host program: A = prebuilt (quickest), B = build it from source
This package gives you the choice. Pick one (you can do both; section 3 explains which one `play.cmd` starts).

| | **Option A - prebuilt host (quickest)** | **Option B - build from source** |
|---|---|---|
| What | use `host\` as it is: `burnout3_bmashup.exe` + `SDL2.dll` + `shaders\upscale` + `licenses\` | `build-host.cmd` recompiles the host on your PC from `host-source\` and YOUR OWN `default.xbe`; result in `host-local\` |
| Effort | none: go straight to game data, preflight, play | ~10 GB disk, seven toolchain downloads, ~15-30 min (`BUILD_HOST.md`) |
| Result | sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656` (reference build `main21`, identity `bmp-0.1.9+2c8142e65f20`) | the SAME sha256 with the pinned toolchain (byte for byte; checked by `build-host.cmd`) |
| Source | `host-source\` + `lgpl-kit\` (see the notes below) | you build it yourself, so you can change any of it |

### Risk note (please read before choosing A)
- **The prebuilt host contains code recompiled from the game's own executable** (about 17 MB of translated machine code). Whether
  that code may be handed to anyone is an **open legal question (Q1) and is NOT cleared**; nobody has said the prebuilt host may be
  redistributed. A private variant included it only because the project owner decided to give private testers this choice and accepted the
  risk (`docs/PUBLIC_STATUS.md`). That acceptance is not a permission from the game's rights holder. **Do not upload, publish or pass
  on this package.** Option B avoids receiving such code from us, but is not described as legally cleared either (Q7); judge it
  for where you live.
- **You still need your own game data.** Nothing in this package is game data: no textures, models, audio, films or disc files.
  You need your own retail NTSC-U *Burnout 3: Takedown* (Xbox), and the host refuses any other copy.
- **LGPL notice.** The host statically links LGPL-2.1-or-later audio code (the MCPX APU library from xemu). Its complete source
  as built, its compile script and the relink scripts are in `lgpl-kit\`; licence texts in `host\licenses\`. **Option B lets you
  rebuild the whole exe with a modified version of that library** (the relink inputs that contain compiled game code are not
  shipped; `build-host.cmd` regenerates them from your own game). Whether this route satisfies the LGPL for a binary hand-over is
  open (Q2). This package is verified on one PC only and is **not distribution-cleared** (nine open questions: `docs/PUBLIC_STATUS.md`).

## 1. What this alpha supports
| | Supported | Not supported / not proven |
|---|---|---|
| OS / hardware | Windows 10/11 **x64**, a GPU driver with **Vulkan 1.3** | tested on ONE Windows 11 PC with one GPU; Windows 10, ARM64, laptops with two GPUs: NOT TESTED; **Linux / macOS: not built** |
| Game | your own retail **NTSC-U** Xbox *Burnout 3: Takedown* | PAL / Japanese / demo / modified copies are refused |
| Mods | data mods + approved plugins on host platform 0.1.9; car series / paints / garage photos (RUNTIME-VALIDATED); authored cars and tracks with DONOR parts from your data; World Tour 4th region (borrowed map) | widescreen / ultrawide / split screen: NOT TESTED; the 917-added-car tier: not tried at runtime |
| Experimental | - | **U5: expanded lanes (more than 64) and transitions between tracks / modes after them are EXPERIMENTAL and not generally safe** (stale pointers, also with large registries / asset reloads). Revenge track conversion (trackconv) is **not supported** in this alpha |

Full list: `docs\KNOWN_LIMITATIONS.md`.

## 2. What you supply
1. Your extracted retail NTSC-U disc or an installed Takedawn data folder (`Burnout 3 Takedown\default.xbe`, sha256
   `9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9`, plus the disc files). **Nothing of the game is included.**
2. Python 3.11+ from python.org (on PATH as `py`), a Vulkan 1.3 GPU driver, ~4 GB free disk (Option A).
3. Only for Option B: the toolchain downloads of `BUILD_HOST.md` section 2 (seven archives, exact sha256), git (or the PortableGit
   archive), the Python package `capstone 5.0.9` in a private venv, and ~10 GB more disk space.

## 3. Steps, and which host `play.cmd` starts
**Option A (prebuilt) - from this folder in a Command Prompt:**
```
prepare.cmd data --copy-from "%LOCALAPPDATA%\BurnoutMashup\Game"     (or your own folder holding "Burnout 3 Takedown"; read only)
preflight.cmd                                                     (must end with RESULT PASS; it names the host it checks)
prepare.cmd demos                                                 (builds the coupe and test tracks from YOUR data)
play.cmd
```
Shortcut: drag your game folder or disc image onto `prepare.cmd` (it picks `--copy-from` or `--install-from` for you).
**Option B (build from source):** follow `BUILD_HOST.md` (`prepare-deps.cmd`, the capstone venv, `build-host.cmd`), then
`preflight.cmd`, `prepare.cmd demos`, `play.cmd`. The build never touches `host\`: it installs into `host-local\`.

**How `play.cmd` picks the host** (`preflight.cmd` and `prepare.cmd data --install-from` use the same rule; `diag.cmd` lists the files of both folders):
1. `set BMASHUP_HOST=prebuilt` before `play.cmd` -> always `host\burnout3_bmashup.exe` (Option A);
2. `set BMASHUP_HOST=local` -> always `host-local\burnout3_bmashup.exe` (Option B);
3. not set -> `host-local\` if it holds a host (your own build wins), otherwise `host\`.
`play.cmd` prints `play.cmd: host = ...` on every start and `play.cmd --print-env` shows the exe path without starting anything.
`preflight.cmd` reports the host in use with its sha256 and warns if it is neither the expected reference build nor a documented
local build (`host-local\BUILD_RESULT.json`). To replace the prebuilt host completely you may delete `host\` after building
(preflight then shows a warning about the missing package files, not an error); unpack the zip again to get it back.
Nothing is installed system-wide; everything lives in this folder (`host\`, `host-local\`, `build\`, `gamedata\`, `profile\`).

## 4. Run an example mod
`prepare.cmd demos` builds the coupe and test tracks from your data into `mods\generated` (DONOR parts: local only). Then
`play.cmd` (it prints which host it starts). In the game: Single Event > Race > Europe > **BM Test Loop**; in SELECT CAR go right to **BM COUPES** and pick the
BM Coupe (X cycles paints - crimson / gold). The ready-made AUTHORED demo mods in `mods\demo` add the Neon / Dust Runners series
and paints. Walk-through: `docs\FIRST_DEMO.md`. Log check: `profile\Roaming\BurnoutMashup\logs\run.log` has
`[PLATFORM] host: Burnout Mashup platform 0.1.9, build bmp-0.1.9+2c8142e65f20` (the same for both options), the `[ADMIT]` line, no `FATAL`.

## 5. Build an example plugin (developer bundle)
Plugins are C code built against the SDK in the **developer bundle** (`bmashup-dev-0.7.0`). In short: install llvm-mingw / CMake /
Ninja (the same archives as above), then `powershell -NoProfile -File sdk\build.ps1 -BuildDir <new folder> -LlvmMingw <dir>
-CMake <exe> -Ninja <exe>`; compare the printed sha256 with `sdk\EXPECTED_BUILD_SHA256.txt`; copy e.g.
`<build>\out\bmashup-sdk-host-info` into `mods\user`; approve its exact sha256 (the log prints the `approved = [...]` line to put
into `profile\Roaming\BurnoutMashup\plugin-approvals.toml`, or MODS page > APPROVE CODE); restart. The log then shows
`[PLUGIN] ... running (plugin API 1)`. Details: the developer bundle's `START_HERE.md`. This package installs no plugin by
default. The capacity example (`bmashup-sdk-capacity`) works (defect T1 was fixed in trackbuild 0.2.1). **Rebuild any track you made with trackbuild 0.2.0 or older** (commands in s6; this package has trackbuild 0.3.0).

## 6. Create and validate a content pack
Your own track from the trackbuild template, no compiler needed:
```
mkdir work\mytrack
py -3 -B tools\kit\trackbuild\tb.py gen-testloop work\mytrack\src
py -3 -B tools\kit\trackbuild\tb.py build work\mytrack\src work\mytrack\src\<the .track.json it wrote> work\mytrack\build --game-data "gamedata\Burnout 3 Takedown"
py -3 -B tools\kit\trackbuild\tb.py validate work\mytrack\build
copy tools\kit\trackbuild\examples\my_track_package.toml work\mytrack\   (edit name / id / author)
py -3 -B tools\kit\trackbuild\tb.py package work\mytrack\build work\mytrack\my_track_package.toml work\mytrack\pkg
xcopy /E /I work\mytrack\pkg\my_tracks\my-first-track mods\user\my-first-track
```
`gen-testloop` needs the parent folder to exist (hence `mkdir`). `validate` runs the track gates (16); `package` refuses unless
`validate` passed on the current files. `package` writes a whole mod SET (`pkg\my_tracks\...` + LABELS / SHA256SUMS): copy only
the mod folder into `mods\user` (the host reads mods one level below each mods folder). The pack appears in Europe as MY FIRST
TRACK. With the developer bundle you can also check the whole set as the game will:
`py -3 -B <dev>\tools\bmpack\bmpack.py validate mods\demo mods\generated mods\user --game-data "gamedata\Burnout 3 Takedown" --cc build\deps\llvm-mingw\bin\x86_64-w64-mingw32-clang.exe`
(`RESULT ACCEPTED`). It contains DONOR parts of your data: local only. Data mods by hand: the developer bundle's MODDING_GUIDE and
`bmpack validate` (needs llvm-mingw).

## 7. Remove mods and recover progress
- One mod: MODS page OFF (saved in `profile\Roaming\BurnoutMashup\mod-list.toml`) or move its folder out; restart. Your profile still
  loads; a car from a removed mod falls back to a retail car. Added content keeps its progress in sidecar files
  (`profile\Roaming\BurnoutMashup\bmashup\progress\*.bmprog`), never in the game save: put the mod back and the saved paint / medals
  come back.
- Backup first: `remove.cmd backup --to C:\somewhere` (saves, sidecars, settings). Restore = copy them back into
  `profile\Roaming\BurnoutMashup\`.
- Everything: `remove.cmd list`, then `remove.cmd clean --yes` (add `--keep-host` to keep your own build `host-local\` + `build\`, `--keep-gamedata` to
  keep the data copy; the prebuilt `host\` is a package file and stays), then delete this folder. Your normal Takedawn folders are never read or written by `play.cmd`.

## 8. Diagnostics and reporting
`diag.cmd --bundle . --out diag\bugreport.zip` - versions, hashes, mod list, log lines, preflight result; no saves, progress,
game files or mod contents; user name replaced. It prints every file it adds: read the list before sending. Report through the
channel named in `docs\BUGS_AND_CONTRIBUTING.md`, never to the Takedawn project. Never attach the host exe (prebuilt or
your build), game files, generated mods or saves. Short checklist of what to try: `docs\TEST_CHECKLIST.md`.

## 9. Versions
host platform **0.1.9** (reference build main21 `bmp-0.1.9+2c8142e65f20`) - SDK **0.7.0** - mod kit / developer bundle **0.7.0** -
tools in this package: carimport 0.1.1, trackbuild 0.3.0, bmdiag 0.1.0 (`tools\TOOLS.json`) - this package **0.4.0** (the launcher and the other 0.4.0 changes; no host binary in this copy: build it with BUILD_HOST.md).
