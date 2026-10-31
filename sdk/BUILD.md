# Building the bmashup-sdk 0.7.0 examples

**Only Windows x64 is built and tested.** The host loads `.asi` / `.dll` modules on Windows; Linux / macOS modules
(`.so` / `.dylib`) are possible in Takedawn's loader but are not built or tested by this SDK (some example mod.toml files
name them; nothing is built for them).

## Requirements (install them yourself; the kit's `docs\PREREQUISITES.md` has the download links and sha256)
| tool | version used for the reference build | where it comes from |
|---|---|---|
| llvm-mingw (clang, x86_64-w64-mingw32 target, UCRT) | 20260922 (clang 23.1.2), `llvm-mingw-20260922-ucrt-x86_64.zip` | github.com/mstorsjo/llvm-mingw releases |
| CMake | 3.20 or later (4.4.4 used) | cmake.org / github.com/Kitware/CMake releases |
| Ninja | any (1.13.2 used) | github.com/ninja-build/ninja releases |
| PowerShell | Windows PowerShell 5.1 | (Windows) |
| Python 3.11+ | only for `examples\music-pack\make_tones.py` | python.org |

`EXPECTED_BUILD_SHA256.txt` holds the bytes the reference toolchain gives for ALL the examples listed below (built against the 0.6.0 headers in `include\`); another llvm-mingw version may give other bytes
(still valid modules, but a player must approve the new sha256).

## One command
```
powershell -NoProfile -File build.ps1 -BuildDir <new folder> -LlvmMingw <your llvm-mingw> -CMake <your cmake.exe> -Ninja <your ninja.exe>
```
- builds into `-BuildDir` (default `..\build\bmashup-sdk-0.6.0` next to the SDK folder);
- finds each tool from its option, else (llvm-mingw) `%BMKIT_LLVM_MINGW%`, else `-Toolchain <dir>` / `%BMSDK_TOOLCHAIN%` (one folder
  holding all three), else PATH. Nothing else is searched; a missing tool stops with exit 3 and says what to install;
- prints the sha256 of every output: compare with `EXPECTED_BUILD_SHA256.txt` (the kit's reference build). `-Clean` removes a
  build folder it made before.

Output, one drop-in mod per folder (`<build>\out\`), 40 plugins and 7 data folders in all (every example of the kit):
```
bmashup-sdk-events-observer\  bmashup-sdk-boost-modifier\  bmashup-sdk-track-names\  bmashup-sdk-capacity\
bmashup-sdk-hooks-demo\  bmashup-sdk-hooks-rival\  bmashup-sdk-patch-demo\  bmashup-sdk-host-info\        (a)-(h) plugins
example-capacity-declaration\  example-content-template\  example-events-v2\                              data templates
bmashup-sdk-autopilot-demo\  bmashup-sdk-vphysics-demo\  bmashup-sdk-traffic-half\  bmashup-sdk-traffic-probe\
bmashup-sdk-ai-slow\  bmashup-sdk-ai-probe\  bmashup-sdk-crash-scores\  bmashup-sdk-camera-fov\           (j)-(o) plugins
gp-aitune-topspeed\  gp-aitune-aggression\  bmashup-test-tones\  bmashup-test-tones-remix\              (p) / (q) data mods
bmashup-sdk-crash-hooks\  bmashup-sdk-damage-panels\  bmashup-sdk-per-player-settings\                    SDK 0.5.0 plugins
bm-boost-award\  bm-camera-roll\  bm-car-colour\  bm-contact-no-crash\  bm-detach-parts\                  SDK 0.6.0 plugins
bm-eliminator-mode\  bm-finish-camera\  bm-garage-stats\  bm-gearbox-toggle\  bm-hud-rpm-meter\
bm-kamikaze\  bm-lights-blinkers\  bm-menu-popup\  bm-racers-dynamics\  bm-racers-order\
bm-takedown-pitch\  bm-traffic-check\  bm-traffic-x3\  bm-vphysics-garage\  bmashup-hud-shake\  bmashup-input-log\
```
Some of the 0.6.0 plugins change gameplay or are experimental (`bm-traffic-x3`, `bm-gearbox-toggle`, `bm-kamikaze`, ...): read each
example's `mod.toml` description before installing it. Services the running host marks UNAVAILABLE answer cleanly (see the docs).
The music mods need their audio: `py -3 -B examples\music-pack\make_tones.py <folder>` writes both mods complete.

## By hand (CMake)
```
cmake -S . -B <build> -G Ninja -DCMAKE_MAKE_PROGRAM=<ninja.exe> ^
      -DCMAKE_TOOLCHAIN_FILE=cmake/llvm-mingw-x86_64.cmake -DLLVM_MINGW_ROOT=<llvm-mingw>
cmake --build <build>
```
One example alone: `-S examples/<name>`. Build-time options: `BMSDK_BOOST_DEFINES`, `BMSDK_NAMES_DEFINES`,
`BMSDK_CAPACITY_DEFINES`, `BMSDK_AUTOPILOT_DEFINES`, `BMSDK_VPHYSICS_DEFINES` (each example's README); the traffic / ai
variants are fixed per target (`GP_DENSITY`, `GP_PACE`).

## Flags that matter
- `-fvisibility=hidden` + `TD_EXPORT` on the exports: nothing else is exported.
- `-Wl,--no-insert-timestamp`: no link time in the PE header, so the same sources and toolchain give the same bytes and the
  same sha256 (a player's approval survives a rebuild; `tools\kit_selftest.py --sdk` rebuilds and compares).
- `-Wall -Wextra -Werror`: every example builds clean.
- Keep `DllMain` / constructors empty.

## Installing a built mod (manual, for testing)
1. Copy the mod folder into a mods folder (`BMASHUP_MODS`). 2. Approve the module (MODS page APPROVE CODE, or
`"<mod id> sha256:<sha256 of the .asi>"` in `plugin-approvals.toml`). 3. Start; the log shows `[PLUGIN] <id>: running (plugin
API 1)` and one `service <name> <version>: used / not used` line per offered service. Full procedure: the kit's
`docs\INSTALL.md`.
