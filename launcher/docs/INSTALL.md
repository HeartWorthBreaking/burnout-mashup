# Install, build, prepare, run, remove - tester package 0.4.0

> **Burnout Mashup 0.2.0 and later (the Windows package):** start with `QUICKSTART.md`. In the package the game copy and your mods
> are in `gamedata\` and `gamedata\mods\user` beside `app\` (not in this folder); saves, settings and builds stay in
> `app\launcher\profile` / `host-local`. The commands below work the same (they find those places themselves). The rest of this page
> describes the older tester package.

Order: unpack -> game data -> (Option B only: toolchain + build the host) -> preflight -> demos -> play.
Two choices for the host: **A = the prebuilt `host\` (use it as is)**, **B = build your own from source into `host-local\`**.
Read the risk note in START_HERE.md section 0 first: the prebuilt host holds code recompiled from the game (Q1 open, not cleared). Background: [START_HERE.md](START_HERE.md).

## 1. Unpack
1. Check the zip: `Get-FileHash bmashup-alpha-tester-0.4.0.zip` must equal the value you were given.
2. Unpack into a **new, empty folder of its own** with a short path, e.g. `C:\Games\bmashup-alpha` (not Program Files, not inside
   Takedawn's folders, not a synced folder such as OneDrive).

Inside: `host-source\` (the host source package: patch, hook marks, build scripts - no game code), `host\` (the PREBUILT host: exe, SDL2.dll, shaders, licences), `host-local\` (appears only if you build: Option B), `lgpl-kit\` (LGPL library source + relink scripts),
`mods\demo\` (AUTHORED demo mods), `sources\` (AUTHORED sources of the generated demos), `tools\` (preflight, prepare,
prepare_deps, build_host, remove, diagnostic export, carimport, trackbuild), `docs\`, `*.cmd`, `BUILD_HOST.md`, `BUNDLE.json`,
`SHA256SUMS.txt`, `README.txt`, `NOTICE.txt`, `RELEASE_STATUS.md`, `licenses\`.

## 2. Game data
**A. Installed Takedawn data** (`%LOCALAPPDATA%\BurnoutMashup\Game`, or any folder holding `Burnout 3 Takedown\default.xbe` + `.complete`):
`prepare.cmd data --copy-from "%LOCALAPPDATA%\BurnoutMashup\Game"` - reads the source only, checks the signature and the install
marker (manifest `81dc20fd647fb0b1`), copies ~2.5 GB into `gamedata\`.
**B. Your disc** (image or extracted folder): with the prebuilt host (Option A) just run
`prepare.cmd data --install-from "<image or folder>"`; with Option B build the host first with `build-host.cmd --xbe "<disc folder>\default.xbe"`, then
`prepare.cmd data --install-from "<image or folder>"` (the host's own installer; not exercised in the alpha's validation).

## 3. The host: A prebuilt or B build from source
**A. Prebuilt (quickest) - not in this copy (no host included; use B):** nothing to do. `host\burnout3_bmashup.exe` is the reference build (sha256 `f0b9c8a9bf3b...`), with
`SDL2.dll`, `shaders\upscale` and `licenses\` beside it. `preflight.cmd` checks all of them against `SHA256SUMS.txt`.
**B. Build from source:** [BUILD_HOST.md](../BUILD_HOST.md): downloads with sha256, `prepare-deps.cmd`, the capstone venv,
`build-host.cmd`. Result in `host-local\`: `burnout3_bmashup.exe` = the reference build (same sha256 with the pinned toolchain),
`SDL2.dll`, `shaders\upscale`, `licenses\`, `BUILD_RESULT.json`. `host\` is not touched.
**Which one starts:** `BMASHUP_HOST=prebuilt` -> `host\`; `BMASHUP_HOST=local` -> `host-local\`; not set -> `host-local\` if it holds
a host, else `host\` (`play.cmd` prints its choice; `play.cmd --print-env` shows the path).

## 4. Preflight
`preflight.cmd` (read only): package files vs `SHA256SUMS.txt`, the host in use (prebuilt or your build: its sha256, identity, SDL2, shaders, licences; a warning when it is neither the reference build nor a documented local build),
Windows version / architecture, Windows DLLs, Vulkan loader >= 1.3 (and the GPU when `vulkaninfo` is installed), `gamedata`,
demo mods, free space, location. Must end with `RESULT PASS`.

## 5. Demos that need your data
`prepare.cmd demos` (or `--only coupe,loop`) builds `bm-coupes-series`, `bm-test-loop`, `bm-canyon-ring` into `mods\generated\`.
They contain DONOR parts copied from your game data: keep them private. Each build is validated and compared with the reference
bytes raced in testing.

## 6. Play
`play.cmd` (`play.cmd --print-env` shows what it would start). Everything the game writes stays in this folder:
`profile\Roaming\BurnoutMashup\` (settings, mod list, plugin approvals, saves `UDATA`, `logs\run.log`, `bmashup\progress\*.bmprog`),
`profile\Local\` (shader cache), `gamedata\`. Your normal `%APPDATA%\BurnoutMashup` is not read or written. Mods: `mods\demo`,
`mods\generated`, `mods\user` (yours; at most 64 mods in total). MODS page in the game turns mods on / off.
To continue from your Takedawn progress, COPY (never move) `%APPDATA%\BurnoutMashup\UDATA` into `profile\Roaming\BurnoutMashup\` first.

## 7. Remove
1. `remove.cmd backup --to "C:\somewhere"` (saves, mod progress sidecars, settings).
2. `remove.cmd list`, then `remove.cmd clean --yes` - deletes `gamedata\`, `profile\`, `mods\generated\`, `mods\user\`, `work\`,
   `diag\`, `build\` and your own host build `host-local\` (`--keep-gamedata` / `--keep-host` keep those). The prebuilt `host\` is part
   of the package and is never deleted by `clean`.
3. Delete the folder. Nothing outside it was written by the package's scripts or by `play.cmd` (Windows' own Prefetch /
   SmartScreen records and the GPU driver's shader cache are managed by Windows / the driver).
Re-install: unpack again, copy the backup into `profile\Roaming\BurnoutMashup\`, build / prepare again. Saved paints and World Tour
progress of added content come back with the `bmashup\progress` sidecars.
