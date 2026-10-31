# Changelog - bmashup-modkit (EXPERIMENTAL Windows x64 mod kit; local, not published)

The kit's own release number. It is NOT the platform version of the host (docs\VERSIONING.md).

## 0.7.0 - 2026-10-31 (private alpha, LOCAL; MAINLINE reference host main21, platform 0.1.9)
Reference host: **main21** (your own build is `burnout3_bmashup.exe`), identity `bmp-0.1.9+2c8142e65f20`, sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`,
**platform 0.1.9** (unchanged), 25 services. SDK **0.7.0**. bmpack **1.5.0** (unchanged). The previous release was kit 0.6.0
on main19_final (sha256 `8675e61d4c14...`).
main21 = main20 (the MODS menu) + the main21 patches 66-130. Service ABIs only grow at their end (append-only).
Status: technically verified; NOT distribution-cleared. Which features have been seen in the game and which are tested offline
only is listed in the release notes of v0.7.0-alpha.1.

### New in the host (details: `docs\services\` and the comments in `sdk\include\`)
Service versions declared by the shipped headers: racers 6, rules 6, traffic 8, camera 4, hooks 3, events 7, settings 2, tune 3.
- Traffic: seed and lane floor; Traffic Attack spread and section fill; fill empty lanes (with fill modes); sector pre-load.
  Parked cars (`set_parked`) are in the code but switched OFF in the default host (a probe run hung).
- Racers and cars: engine rpm; light OFF and a reverse lamp; headlights, light ON and a tail-lamp stand-in; pose and AI name
  labels; wreck a racer on request; rival count and rival cars (also chosen on the MODS page).
- Paints: decals, wheels, nitro tint and glow; the colour picker is the paint picker of every car.
- HUD: the elements POSITION, LAP, SPEED, TAKEDOWNS and CENTRE_MESSAGE; car-select stat bars.
- Sound and camera: free sound pitch; a free camera and the look-back third-person view; the picture-view window; the player
  horn on L3.
- Rules and modes: props in Road Rage; END SESSION in every mode; help text and option values for mode rows (Eliminator); the
  pause-menu MOD SETTINGS; the game's leftover DEBUG page as a named switch (off by default); Crash Breaker in every mode;
  Single Event DJ; World Tour Face-Off, Road Rage, Eliminator and Burning Lap events; Multiplayer mode rows.
- Contacts: push scaling. NO_CRASH now really skips the crash (before, only the push was kept), and its closing-speed bound is
  60 m/s (was 25).
- Tuning rows: Air Ram, 32 crash and in-game camera rows, spark size, car shadow rows. A data mod can declare `[bmashup.tune]`
  sliders that appear on the MODS page.
- Textures: `[bmashup.textures]` class `global` replaces the shadow and spark entries of `Global.txd` (`docs\services\TEXTURES.md`).
- DEV-only probes are compiled out of the default host build.

### New in the kit
- SDK headers: byte copies of the headers of the host tree (sha256 list: `sdk\include\HEADERS_FROM_MAIN21.txt`). Changed: bmashup_camera.h, bmashup_hooks.h, bmashup_hud.h, bmashup_menu.h, bmashup_paints.h, bmashup_racers.h, bmashup_rules.h, bmashup_settings.h, bmashup_traffic.h, bmashup_tune.h.
  New: -.
- SDK examples: added bm-ai-names, bm-free-camera, bm-headlights, bm-traffic-attack, bm-traffic-kamikaze; updated bm-eliminator-mode, bm-garage-stats. Data mod examples (`examples\mods\`): bm-colour-picker.
  `sdk\EXPECTED_BUILD_SHA256.txt` is regenerated with the pinned toolchain from every example wired into `sdk\CMakeLists.txt`.
- trackbuild 0.3.0: sloped routes (the route follows hills and ramps instead of staying flat). The Workbench uses the kit's copy.
- Workbench 0.30 in `workbench\`: starts from the kit folder, a "New data mod" tab, a DPI-aware window, the same look as the launcher.
  New in 0.30: a Developer workflow window (task templates for a tune data mod, traffic density and an events observer plugin; a
  searchable tuning editor with sliders only where the host declares a verified range; "Test this project": validate, build, stage,
  compatibility, approvals report and the launch plan, without launching). "New data mod" writes tune version 2 for AI rows.
- `Burnout Mashup Workbench.exe` in the kit folder starts the Workbench window (it uses your installed Python 3.11+; built from
  `workbench\exe\wbstart.c`). Windows may show "Windows protected your PC" the first time: More info > Run anyway.
- `bmpack validate` now builds its checker on a fresh install: the host readers ship every tuning catalogue part
  (`bm_tune_catalog_*.inc`).
- `tools\ps2look`: converts the PS2 shadow and spark look into a mod, from YOUR own PS2 disc. It is a tool only; nothing of the
  game is shipped.
- `HOST_INFO.json` and `docs\TUNING_CATALOGUE.md` are generated from the host (every tuning key with its game value and limits).
- `docs\services\` describes the main21 services; `docs\INSTALL.md` and `docs\MODDING_GUIDE.md` carry the MODS-menu texts
  (Settings > MODS > select the mod > Approve and turn on).

### Not in this release
- trackconv (Revenge -> Burnout 3 conversion) is still research tooling and not supported in this alpha.
- Parked traffic cars are off by default (see above).

## 0.6.0 - 2026-10-28 (private alpha, LOCAL; MAINLINE reference host main19, platform 0.1.9)
Reference host: **main19** (`burnout3_gp_main19_final.exe` in the project; your own build `burnout3_bmashup.exe`), identity `bmp-0.1.9+0620fe316156` (sha256 `8675e61d4c149eb1b1fd1f5d360f2e5464e1580f9a9da520114bfc4576bc1b45`),
**platform 0.1.9**, 25 services. SDK **0.6.0**. bmpack **1.5.0** (the main19 readers).
main19 = main18 (kit 0.5.0) + mem256 (the 256 MB guest window) + hook request phases 2 and 3.
Status: offline-tested (unit tests + mutants per service, real generated-code tests, real-XBE checks, COFF audit against main18
and mem256, a = b = clean-folder rebuild) and run in the retail game (three validation rounds, then an exclusive release
acceptance race with 137 mods and 38 plugins: finished first, no fault). Two items are limited (stat bars UNAVAILABLE; indicator blink not visually confirmed): see the notes below.

Added
- **256 MB guest memory window** (mem256, owner "Go to 256mb directly"): the game keeps its own 64 MB exactly where it was;
  every host capacity expansion (STATIC pool, GAMEDATA slot, low-detail slots, front-end textures, paint palettes, the new
  0.6.0 pools) now lives in the 192 MB above it (the high zone). The 64 MB limit that stopped marathon-class tracks plus other
  expansions (kit 0.4.4 CAPACITY.md) is gone for host expansions. A budget gate checks the sum of the expansions at the start
  and stops with a clear message (exit 86) instead of a crash; a refused game allocation stops with exit 87.
  Build option `BO3_GUEST_WINDOW_MB=64` = the 0.5.0 memory behaviour.
- **Hook request phases 2 and 3** (external request, owner: "Leave out phase 4 but I want 2 and 3"):

| Item (hook request) | Service | State on platform 0.1.9 |
|---|---|---|
| Gearbox: AUTO / MANUAL, request a gear, status (A1) | bmashup.vphysics 3 (`VPHYSICS_V3.md`) | BUILT; CHANGES GAMEPLAY; player 0 |
| Dynamics reads: gear, speed, yaw rate, lateral / longitudinal acceleration, parts, lights (A2) | bmashup.racers 3 (`RACERS_V3.md`) | BUILT; speed and accelerations host-derived from the car's position; engine rpm not available (`have_rpm` 0, UNAVAILABLE) |
| Detach a hanging part (A3) | bmashup.racers 3 | BUILT: any racer (AI cars at the game's per-car mark) |
| Lights ON / GAME (A4) | bmashup.racers 3 | BUILT: head / tail / brake on any racer, plus the indicators LEFT / RIGHT / HAZARD (the host blinks them at about 1.5 Hz) and the new `lamp_counts` query; lamps show only on models with group 5 / 6 points; OFF not possible; the visual blink is not confirmed in still screenshots |
| Award score (A5) | bmashup.racers 3 | BUILT: adds to the points shown on the HUD / results |
| Traffic crash-pool counts (F4) | bmashup.traffic 3 (`TRAFFIC_V3.md`) | BUILT (status grows 60 -> 72 bytes) |
| near_vehicles / wreck traffic / clear_wrecked (F4, F5) | bmashup.traffic 3 | UNAVAILABLE (traffic record layout not verified; clear_wrecked is impossible: the game frees crash slots only by its bulk reset) |
| Hook points 8..13 + event twins (F0) | bmashup.hooks 3 / bmashup.events 7 (`HOOKS_V3.md`, `EVENTS_V7.md`) | BUILT; every point is offered |
| TRAFFIC_CONTACT NO_CRASH (F1) | bmashup.hooks 3 point 10 | BUILT; CHANGES GAMEPLAY |
| WRECK_CAUSE observe (F2) | bmashup.hooks 3 point 11 | BUILT (observe only) |
| Takedown credit (F3) | bmashup.hooks 3 point 11 MODIFY | BUILT: a plugin can change who is credited at wreck time (refused for a victim that is not in the racer list, a racer index >= 6, or a victim whose flag at +0x15D6 is already set) |
| Takedown sound pitch level 0..4 (G1) | bmashup.hooks 3 point 12 EVENT_SOUND | BUILT; CHANGES GAMEPLAY AUDIO |
| Chase-camera roll / pitch / yaw / offset (C1) | bmashup.camera 2 + hooks point 9 (`CAMERA_V2.md`) | BUILT |
| Finish camera poses (C2) | bmashup.camera 2 + hooks point 13 | REDUCED: one pose per race, anchored on the end-of-race camera, within 40 m |
| HUD pass (B2) | bmashup.hooks 3 point 8 HUD_PASS | BUILT |
| HUD draw list (B2) | bmashup.hud 2 (`HUD_V2.md`) | BUILT: solid quads, text (host 5x7 font) and sprites from your `[bmashup.textures]` pictures; there is NO `[bmashup.hud]` table; the sprite picture is drawn (P8 entries only) |
| Player car colour (I1, I2) | NEW bmashup.paints 1 (`PAINTS.md`) | BUILT: BODY layer, in races, changed in place; DECALS / WHEELS NO_LAYER (UNAVAILABLE); NITRO reserved |
| Popup after car select (D1) | NEW bmashup.menu 1 (`MENU.md`) | BUILT: on A in Single Event car select; the answer is stored as a per-player setting; not in multiplayer / World Tour / for player 1 |
| Mode row ELIMINATOR (D2) | bmashup.menu 1 | BUILT: up to 4 Eliminator rows in the Single Event mode list, 5 laps; no help line, no option rows, not in multiplayer |
| Stat bars on car select (D3) | bmashup.menu 1 | UNAVAILABLE (the declarations are accepted and validated; the host does not draw the bars; cause open, follow-up) |
| Eliminate / end race / lap elimination (E1) | NEW bmashup.rules 1 (`RULES.md`) | BUILT: a plugin claims an Eliminator race (after the load is done) and runs the eliminations itself |
| Speed unit (X1) | the existing host setting `game.speed_units` | nothing new: already in the host |

- Not possible in this release (reasons on the service pages and in the hook-request feasibility study): a racer wreck on
  request, light OFF, the NITRO paint layer, an arbitrary sound pitch, scaling the contact push, World Tour mode rows / any save
  write, every new control for player 1 (split screen untested platform-wide, R6). Phase 4 (projected shadows) is deferred by the
  owner.
- Limits of this release: (1) garage stat bars (D3) are UNAVAILABLE: the bars could not be shown on the car-select screen in the retail
  game, so `feature_available(BM_MENU_FEATURE_BARS)` answers 0 and nothing is drawn (follow-up); (2) HUD sprites work (P8 entries from
  `[bmashup.textures]`); (3) indicator blink: the control and `lamp_counts` work; the blinking itself was not confirmed in still
  screenshots. Always check the result code and `*_available`.
- UNAVAILABLE means: the function is in the header and the table, the host answers its UNAVAILABLE code (or
  `available` / `feature_available` 0), and nothing in the game is touched. Still UNAVAILABLE in 0.1.9: engine rpm, traffic
  near_vehicles / wreck / clear_wrecked, paint DECALS / WHEELS, garage stat bars. A later host can turn them on without a header change.
- Build option `BO3_HOOKREQ_P23=OFF`: every phase 2 / 3 mark is compiled out of the game code and every phase 2 / 3 function
  answers UNAVAILABLE (the exact 0.5.0-plus-memory sources are the slice's revert script).
- 15 new SDK examples (`sdk\examples`): bm-gearbox-toggle, bm-lights-blinkers, bm-detach-parts, bm-racers-dynamics,
  bm-traffic-check, bm-kamikaze, bm-takedown-pitch, bm-contact-no-crash, bm-camera-roll, bm-finish-camera, bm-hud-rpm-meter,
  bm-car-colour, bm-menu-popup, bm-eliminator-mode, bm-garage-stats. Each example checks the result code and
  falls back cleanly when a function answers UNAVAILABLE.

Changed
- Nothing a 0.5.0 plugin or mod depends on: tables and structs only grew at their end; codes were appended.
- **bmpack 1.5.0**: the host readers of main19 (platform 0.1.9; bmpack 1.4.0 refuses a mod that says `platform = ">=0.1.9"`).
  No validate behaviour change otherwise (`tools\bmpack\BMPACK_1_5_0_PATCH_NOTE.md`).

## 0.5.0 - 2026-10-28 (private alpha, LOCAL; MAINLINE reference host main18, platform 0.1.8)
Reference host: **main18** (`burnout3_gp_main18.exe` in the project; your own build `burnout3_bmashup.exe`), identity `bmp-0.1.8+fcf55c586f78` (sha256 `36859ca4cf4e8b03670cacdc69a11bf34de25856728a241566e6f7f98f38b4ec`),
**platform 0.1.8**, 22 services. SDK **0.5.0**. bmpack **1.4.0**. main18 = capmega1 + the mod-limit raise + hook request phase 1.
Status of every 0.1.8 item: offline-tested (unit tests + mutants, COFF audit, a = b rebuild); runtime acceptance pending.

Added
- **Mod limits** (owner 2026-10-28): 256 mods (was 64), 256 mod folders (was 8) with the new mods-folders list file
  `TAKEDAWN_MODS_FILE`, 64 texture mods and 64 music mods (were 16), 1024 switched-off ids (was 256), 448 plugin approvals,
  256 capacity request slots. Engine ceilings stay: the 12 MiB / 768-entry texture pool, 100 soundtracks, the 64 MB guest window.
  Build option `BO3_MOD_LIMITS=legacy` restores capmega1's values. `docs\LIMITS_AND_BEHAVIOURS.md` 0e, `docs\services\LIMITS.md`.
- **Hook request phase 1** (external request, owner decisions 2026-10-28): bmashup.patch 2 (verified index-table sites: the
  detach-parts tables), bmashup.racers 2 (place / laps / time / order / session), bmashup.boost 2 (award an amount), NEW
  bmashup.hud 1 (HUD element transforms), bmashup.settings 2 (per-player values, 8 / 128), NEW bmashup.input 1 (read-only pad),
  bmashup.vphysics 2 (handling values outside a race), bmashup.traffic 2 (density up to 3.0, EXPERIMENTAL above 2.0),
  bmashup.hooks 2 (point 7 CRASH_RESULT). Pages in `docs\services\` (*_V2.md, HUD.md, INPUT.md); 9 new SDK examples.
- **bmpack 1.4.0**: host readers of main18; mods past the loader's cap are reported instead of dropped silently.

Changed
- Loose files of a mod folder are listed at the start (as a mod's own files): a file added while the game runs is seen at the
  next start; lookups across 256 folders stay fast.

Not done (honest list)
- MOD SETTINGS in the pause menu: not added - the 7th slot is not free in every mode (upstream's TAKEDAWN SETTINGS entry uses it).
- bmashup.hud serves 4 of its 9 named elements (BOOST_BAR, BOOST_MESSAGE, AWARD, SCORE_BOARD); the others answer UNAVAILABLE.
- bmashup.racers: mode / context UNKNOWN, laps_total 0, rival values PARTIAL. bmashup.vphysics 2: no added cars, open UNKNOWN.
- Every per-player call answers UNSUPPORTED for player 1 (split screen untested platform-wide).
- Pool reuse (memory option B) is not in this release.

## 0.4.4 - 2026-10-28 (private alpha; MAINLINE reference host capmega1, platform 0.1.7)
Reference host: **capmega1** (`burnout3_gp_capmega1.exe` in the project; your own build `burnout3_bmashup.exe`), sha256
`b3edf3d4ef839fadeedf4929f75383c432a92fee719ff4f9b201a21a2244bd39`, identity `bmp-0.1.7+9c6131448f9b`, **platform 0.1.7**, 20 services. SDK headers unchanged (0.4.2); tools unchanged.

Added
- **Mainline host policy**: capmega1 is the single mainline reference host (capfix1 + the mesh row extension + the GAMEDATA slot
  expansion, both proven on the experimental host mega1). Content targets the mainline host.
- **`[bmashup.capacity] gamedata_bytes`** (platform 0.1.7): a larger GAMEDATA slot (0x177000..0x800000, page multiple; largest
  request wins). `docs\services\CAPACITY.md` = the full capacity table, limits, evidence and refusal behaviour on older hosts.
- **Mesh row extension (BMRX)**: more than 83 material rows per streamed unit (up to 127), read from track data.
- The host side of marathon-class tracks (more than 64 lanes, more than 83 rows, a large Gamedata) is in capmega1; such a track
  is runtime-validated only on the experimental host mega1 and must fit the 64 MB guest window (CAPACITY.md). U5 stays OPEN.
- Release acceptance on capmega1: cm1_acc_2 (all 16 example plugins + demo content, race finished, 0 faults).

Changed
- Reference host constants / `tools\reference_host.json` / docs: capmega1. `tools\bmpack\host_readers` regenerated from the
  capmega1 tree (`bm_admit.c` / `bm_platform_table.h` know `gamedata_bytes` and platform 0.1.7).

## 0.4.3 - 2026-10-27 (private alpha; reference host capfix1; T1 fixed)
Reference host: **capfix1** (`burnout3_gp_capfix1.exe` in the project; your own build `burnout3_bmashup.exe`), sha256
`a7aea02d5a72a7820cd5649bbd9a01ee23271f89d358890042821092faf3b601`, identity `bmp-0.1.6+0c5a321ae0fa`, platform 0.1.6, 20 services. SDK headers unchanged (0.4.2).

Fixed (T1, "capacity example crashes at race start")
- Cause (diagnosis capdbg): tracks built by trackbuild <= 0.2.0 write an empty chevron set but chevron index 0 in every unit's mesh
  block (+0x7D). The game draws "entry 0" without checking it against the set count; with the game's own STATIC pool the garbage
  count is negative (nothing drawn), with a relocated STATIC pool (the capacity example's request) it is ~19k models and the
  race start faults. Retail tracks are in bounds.
- **trackbuild 0.2.1**: writes +0x7D = -1 ("no chevron"); new validate gate **V10_chevron_index_in_set** (package refuses a
  failing build). **Rebuild every track made with trackbuild <= 0.2.0** (the kit's demo tracks included).
- **Host capfix1** = clean1 + one mark in the chevron draw + `bm_chevron.c`: a chevron index outside the set is skipped (logged
  once as `[CHEVRON] ...`), which also protects tracks already built.
- `sdk\examples\capacity`: supported again; its README explains the fix.

Changed
- Reference host constants / `tools\reference_host.json` / docs: capfix1. `tools\bmpack\host_readers` regenerated from the capfix1
  tree (reader source bytes unchanged; HOST_READERS.json names capfix1).

## 0.4.2 - 2026-10-27 (private alpha release candidate; reference host clean1)
Reference host: **clean1** (`burnout3_gp_clean1.exe` in the project; a user's own build is `burnout3_bmashup.exe`), sha256
`bc0c16c3f111e4982d1e400f9bf3ef4a7e398573180457d81c099f7368909e56`, identity `bmp-0.1.6+345dc71c5cd3`, platform 0.1.6, 20 services. Same SDK headers (0.4.2), same tools and tool versions as 0.4.1.
Why 0.4.2: a new reference host always means a new kit release (VERSIONING.md).

Changed
- Reference host p4.4 -> clean1. clean1 = p4.4 + one CMake option (`BMASHUP_NO_SOURCE_TREE_FALLBACK`): the toolkit's
  build-machine shader path is no longer compiled into the exe, so the upscale shaders are found only next to the exe
  (`shaders\upscale`) or where you point `RECOMP_DEBUG=texup_shaders=<dir>`. Every platform source file and all 28 generated-code
  objects are identical to p4.4: mods, plugins and approvals carry over unchanged; p4.4's runtime evidence applies.
- `tools\bmpack\host_readers` regenerated from the clean1 tree: every reader file has the same bytes as in 0.4.1;
  `HOST_READERS.json` names clean1 (`host readers: bmp-0.1.6+345dc71c5cd3 (exe bc0c16c3f111)` in bmpack's summary line).
- `tools\reference_host.json`, README, INSTALL, VERSIONING, COMPATIBILITY, PREREQUISITES, LIMITS pages: the clean1 host.
- The host is no longer handed out as an exe in this alpha (an open distribution question): build it with your own game from
  the host source package (tester package `BUILD_HOST.md`).

Known issue (OPEN DEFECT, under investigation)
- `sdk\examples\capacity` plugin: EXPERIMENTAL - known crash at race start in combination with the full example set (alpha RC
  onboarding on clean1: guest access violation at race start on two tracks; gone with only this plugin left out). Its README
  carries the warning; do not install it with other mods for play.

Removed
- Internal work notes that named the alpha team's test folders: `tools\trackbuild\CHECKPOINT.md` (dropped; its line removed from
  the tool's `SHA256SUMS.txt`) and two lines of `tools\carimport\PORT_NOTES.md` (rephrased; the tool's `SHA256SUMS.txt` updated).

## 0.4.1 - 2026-10-27 (private alpha; portable tools)
Same reference host (p4.4, platform 0.1.6), same SDK headers (0.4.2). Why 0.4.1: a PATCH step - no new data table or service;
the tools now run from any folder on any machine with your own prerequisites and game data.

Changed
- Every shipped tool is free of developer-workspace paths: package-relative paths (`tools\_lib\bmkit_env.py`), explicit
  configuration (options > `BMKIT_*` variables > `bmkit.toml` > PATH), prerequisite discovery; a missing prerequisite, wrong /
  absent game data or an invalid path stops with exit 3 and a message saying what to install or give (`docs\PREREQUISITES.md`,
  `docs\GAME_DATA.md`). No silent fallback to any fixed location.
- **bmpack 1.3.4**: `validate` compiles the p4.4 host's own readers from the shipped SOURCE package `tools\bmpack\host_readers`
  (Takedawn MIT + xboxrecomp MIT; `HOST_READERS.json`); the game's PrgData relocation, which 1.3.3 took from generated game code,
  is re-implemented and proven equal (whole guest image) on 7 mod-set combinations; options `--game-data`, `--cc`, `--cache`.
  Outputs of `build` are unchanged. Its test suite runs from the kit: 96 / 96, 14 / 14 mutants caught.
- `sdk\build.ps1`: `-LlvmMingw` / `-CMake` / `-Ninja` / `-Toolchain` or PATH; no default location.
- Authoring tools ported by the alpha team (trackbuild, carimport, fetex, vehtool): versions in `docs\VERSIONING.md`.
- Readers the tools need (collision / route / Gamedata / BGV / lane-model helpers of this project's research) are vendored with
  provenance inside each tool (trackbuild, carimport); `tools\_vendor` (`VENDORED.json`) holds the BGV reader and the recolour
  step the added-car example uses (no workspace module is imported any more).

Added
- `tools\bmdiag` 0.1.0: diagnostic export (versions, hashes, key log lines, mods by name + hash, preflight output); excludes
  saves, progress, game data, mod file contents and environment values; redacts user / computer names, home / bundle paths and
  e-mail addresses; `--include-more` opt-in. Tests prove each exclusion (45 checks, 4 mutants).
- `tools\bmkit_doctor.py` 0.1.0 (prerequisite report), `tools\kit_selftest.py` 0.1.0 (runs every suite from the kit; replaces
  `stage_verify.py`, which compared against the developer workspace), `bmkit.example.toml`, `docs\GAME_DATA.md`,
  `docs\PREREQUISITES.md`, `docs\DEBUGGING.md`, `docs\CONTRIBUTING.md`.

Removed
- `tools\trackconv` and `docs\TRACKCONV.md`: the Revenge -> Burnout 3 conversion is workspace-only research tooling and not
  supported in this alpha (`docs\FORMAT_SEMANTICS.md` stays as format documentation).
- `tools\stage_verify.py` (developer-side release check; replaced by `kit_selftest.py` for users).

## 0.4.0 - 2026-10-27 (LOCAL STAGING; the content phase; not published)
Reference host: **p4.4** `burnout3_gp_p4_4.exe` sha256 `fa63df57dde6b522e77ba0330f0c83ee76ae483cac84f9d58bd9d5a479ce3825`, identity `bmp-0.1.6+ab3a98869d10`, Burnout Mashup platform
**0.1.6**. FINAL content-phase candidate (p4.4 = p4.3 + fix 1 + fix 2; integration report gp\integration\p4_4\P4_4_REPORT.md); a candidate, not a freeze

Why 0.4.0: a MINOR step - new data-mod tables and four new authoring tools change what an author can make; existing mods and
sources work unchanged (SDK 0.4.2 headers unchanged; stage_verify rebuilds them).

Added
- Author docs: `docs\services\TEXTURES.md` (`[bmashup.textures]` 1), `WT_MAP_ART.md` (`[bmashup.wt_map_art]` 1), `CARS.md`
  rewritten for `[bmashup.cars]` 2 + `[bmashup.series]` 1 + `[bmashup.paints]` 1 (series, paint registry, own photos, AI
  eligibility, 1024-entry vehicle list), `LIMITS.md` (mod.toml 64 KiB, texture / vehicle / paint limits with format ceiling /
  configured / tested / demonstrated), `AUTHORING_TOOLS.md`.
- Tools with their tests: `tools\carimport` 0.1.0 (glTF 2.0 cars), `tools\trackbuild` 0.1.6 (OBJ tracks), `tools\fetex` (TXD;
  kit test suite `tests\test_fetex.py`), `tools\vehtool` 0.1.1 (65536-byte mod.toml; `tests\test_vehtool_limit.py`).
- `examples\authored\`: carimport coupe / wedge (glTF + PNG), trackbuild package descriptions (sources from `tb.py
  gen-testloop`), fetex art generator + packs, veh series / paints generator, the BM Coupes series + photo
  (`AUTHORED_FILES.json`: provenance + sha256 of every non-text file).

Changed
- bmpack 1.3.2 -> **1.3.3**: validate registers `[bmashup.world_tour]` locations (the false refusal of a 4th-region mod in 1.3.1 /
  1.3.2 is gone); T15 tests + mutant 14 (`tools\bmpack\BMPACK_1_3_3_PATCH_NOTE.md`).
- `tools\stage_verify.py`: every tool's tests from the staging copy, every generator against its workspace original, the
  authored-file provenance check, the content install walk on the reference exe (copied, never run).
- INSTALL / LIMITS_AND_BEHAVIOURS / COMPATIBILITY / VERSIONING / ROADMAP / MIGRATION / MODDING_GUIDE for platform 0.1.6.

Not changed: SDK 0.4.2 and its 17 examples; kits 0.3.0 / 0.3.1 (folders, zips, the private repo copy) are untouched.

## 0.3.1 - 2026-10-27 (LOCAL STAGING; offline verified against host p4.2; not published)
Reference host: **p4.2** `burnout3_gp_p4_2.exe` sha256 `4fd86d1066aeb6fc210e28e463178c45c31cf75f2f8a0d2890c4e86fc58dcf4b`,
build identity `bmp-0.1.5+0db09076e5b8`, Burnout Mashup platform **0.1.5** (an integration candidate; referenced, not
included). SDK package **0.4.2**, bmpack **1.3.1**, trackconv **0.1.0**.

Why 0.3.1 (not 0.4.0): the reference host changed (which always means a new kit release), but every change for a mod author is
additive - two new data tables, a header comment, docs and example generators; no service ABI, no kit tool behaviour for existing
mods, no file layout change. Kit 0.3.0 mods and sources work unchanged on p4.2 (stage_verify rebuilds them).

Added
- `docs\services\CARS.md` (`[bmashup.cars] version 1`: a car added to an existing series on a donor) and `WORLD_TOUR.md`
  (`[bmashup.world_tour] version 1`: a 4th World Tour region on a BORROWED map; borrowed assets labelled; the region page's
  hold-to-repeat documented as retail behaviour, scripting rule presses <= 100 ms); the host's own `bmashup-vphysics.md` and `bmashup-world-tour.md`.
- `examples\content\added-car` and `examples\content\wt-region`: mod.toml + generators that build the files from YOUR OWN retail data
  (input sha256 checked; outputs = the runtime-validated sets byte for byte; LOCAL ONLY). No game file ships.
- "Evidence update (kit 0.3.1)" on every service page (p4.1 gaps runs gp_p41g_1 / 2, p4.2 runs gp_p42_1..8).

Changed
- SDK 0.4.1 -> **0.4.2**: `bmashup_vphysics.h` comment only - "Max Speed In Boost" is the car's TOP-SPEED LIMIT (it caps normal
  AND boost speed; runtime gp_p41g_2); `bmashup_sdk.h` reference host / build / platform = p4.2. No ABI change.
- `docs\services\VPHYSICS.md`: the correction (observed semantics, the ValueDB name kept and qualified).
- bmpack 1.3 -> **1.3.1** (the p4.2 integration copy): links `bm_wt4.c` when the host tree has it (platform 0.1.5 trees); nothing
  else (its `TOOL_VERSION` text still reads 1.3; the file gained a UTF-8 BOM). Known limitation: its validate REFUSES a
  `[bmashup.world_tour]` mod ("... is not a race location ..."), which the host accepts (gp_p42_7) - documented, not fixed here.
- INSTALL / LIMITS_AND_BEHAVIOURS / COMPATIBILITY / VERSIONING / ROADMAP / MIGRATION / MODDING_GUIDE for host p4.2.
- `tools\stage_verify.py`: p4.2 host; runs the bmpack and trackconv test suites from the staging copy; runs both content
  generators and compares them with the launched sets; installs them in the INSTALL walk.

Not changed: the 17 SDK examples' sources and mod.toml files; kit 0.3.0 (folder, zip, private repo copy) is untouched.

## 0.3.0 - 2026-10-27 (LOCAL STAGING; offline verified against host p4.1; not published)
Reference host: **p4.1** `burnout3_gp_p4_1b.exe` sha256 `80b7aea9d74381c0aa729d02ccba6eb59ff6668b8f0e71965ff308f79087581a`,
build identity `bmp-0.1.4+bbfb763a604a`, Burnout Mashup platform **0.1.4** (an integration candidate; referenced, not
included). SDK package **0.4.1**, bmpack **1.3**, trackconv **0.1.0**.

Added
- SDK 0.4.1 (`sdk\include` = p4.1's 22 public headers, byte copies): `bmashup_autopilot.h` 2, `bmashup_vphysics.h`,
  `bmashup_traffic.h`, `bmashup_ai.h`, `bmashup_crash.h`, `bmashup_events.h` 6, `bmashup_settings.h`, `bmashup_camera.h`,
  `bmashup_tune.h` 3; `bmashup_sdk.h` catalogue of 20 services.
- Examples (j)-(q): autopilot demo 0.2.0 (every race, optional release), vphysics demo, traffic (half / probe), AI (slow /
  probe), crash scores, camera FOV (settings + camera), AI tuning data mods, music packs (audio generated by `make_tones.py`).
- `docs\services\`: author docs for every new service and declaration, with runtime evidence and limits.
- `examples\mods\deps-*`: bmpack specs for `requires_mods` fixtures (base, addon, newer).
- `tools\bmpack` 1.3 (`requires_mods`, dependency order; validate with `BMPACK_TREE` = the p4.1 tree).
- `tools\trackconv` 0.1.0 + `docs\TRACKCONV.md`, `docs\FORMAT_SEMANTICS.md` (from the 0.2.2-trackconv add-on, unchanged).
- `sdk\EXPECTED_BUILD_SHA256.txt`: the reference build's bytes; `tools\stage_verify.py` rebuilds and compares.

Changed
- **No prebuilt modules** (kit 0.2.x shipped `prebuilt\`): build with `sdk\build.ps1`, approve your own bytes.
- INSTALL / LIMITS_AND_BEHAVIOURS / COMPATIBILITY / VERSIONING / ROADMAP / MIGRATION / MODDING_GUIDE for host p4.1.

Not changed: kit 0.2.0 / 0.2.1, SDK 0.3.0 / 0.4.0 / 0.4.1 sources, bmpack 1.3 (byte copies), the private repo export.

## 0.2.1 - 2026-10-26 (documentation-only patch release of 0.2.0)
Same reference host p3 (`6f008b21...`, `bmp-0.1.1+b56e33b66dc3`, platform 0.1.1), same SDK package **0.3.0**, same bmpack
**1.2**. Every non-document file - SDK headers, sources, examples, prebuilt plugins, approvals, tools, specs - is
byte-identical to 0.2.0; only Markdown documents, MANIFEST.json and SHA256SUMS_kit.txt changed.

Changed (documentation)
- p3 evidence now cites the kit 0.2.0 smoke launch **bmp_kit2_1** accurately, as BOOT-ONLY: plugin start-up on p3 is
  runtime-validated (approval per sha256, loading, service binding, host-info identity, hooks CONFLICT, patch applied, 8 mods
  admitted / 0 refused); plugin GAMEPLAY on p3 (event / hook dispatch, modifier effect, race-exit summaries) remains NOT
  TESTED (COMPATIBILITY.md, LIMITS_AND_BEHAVIOURS.md).
- ROADMAP: the smoke-launch item is done; Priority 1 item 1 is now "plugin gameplay on p3" (one race).
- The bmpack admission-reason truncation is described accurately: bmpack 1.2 keeps up to 640 characters of a reason (fewer
  when the mod id / version / folder are very long - its line buffer is 900 bytes); the game itself keeps up to 699
  characters (`BO3_ADMIT_WHY` 700), not "the whole reason" as 0.2.0 said. Verdict and refused mod agree either way.
- Kit-release references 0.2.0 -> 0.2.1 where they name this release (titles, INSTALL zip name, VERSIONING).

## 0.2.0 - 2026-10-26 (offline verified against host p3; plugins not yet launched on p3)
Reference host: `burnout3_bmp_p3.exe` sha256 `6f008b218400d62df2c042c5aa5d23dbdcda3d27eac2807146e93d5853e009ed`, build
identity `bmp-0.1.1+b56e33b66dc3`, Burnout Mashup platform **0.1.1** (frozen, FREEZE_P3.md; referenced, not included).
Runtime evidence on p3: launches bmp_p3_1 / bmp_p3_2.

Changed
- Reference host p2 -> **p3** everywhere (docs, SDK constants, stage_verify, catalogue checks).
- `sdk\` bmashup-sdk **0.2.0 -> 0.3.0**: `BMSDK_REFERENCE_HOST / _BUILD / _PLATFORM` = p3; `HEADERS_FROM_P3.txt` (the 16
  headers byte-identical to p2's: no service ABI version changed); new data example (i) `events-v2`
  (`[bmashup.extra_events] version 2` names / help, `platform = ">=0.1.1"`); host-info comments for p3. Six example modules
  rebuild to kit 0.1.0's bytes; events-observer and host-info have new bytes (they log the SDK version / compare the
  reference build).
- `tools\bmpack\` bmpack **1.1 -> 1.2** (= host3's frozen bmpack 1.2): default tree tree_p3; spec `[[event]] name / help`,
  `[tune]`, `[capacity]`; validate runs the two-phase admission (refused alone, both mods named, the game's `[ADMIT]` text),
  shows event row / help texts as the game resolves them and gameplay labels; 1.1 specs build byte-identical mods.
- `tools\stage_verify.py`: three example packs (+ events-pack = `bmp_p3_events_set`), the exact frozen p3 host (or the p3
  host distribution with `--host-zip` + check_host), the conflict demonstration (the later pack refused alone).
- `examples\mods\events-pack\`: the p3 events fixture spec (launched in bmp_p3_1) + expected mod.toml.
- `docs\`: INSTALL (checklist at the top, dependency facts: SDL2 only shipped, Vulkan from the driver, no VC runtime;
  preflight; p3 identity; per-mod conflict refusals; labels), MODDING_GUIDE (event names / help 19 / 97, conflicts, what
  still stops the start, labels), COMPATIBILITY (all gaps explicit), ROADMAP.
- `prebuilt\APPROVALS.txt` marks which modules kept their kit 0.1.0 bytes.

Added
- `docs\LIMITS_AND_BEHAVIOURS.md` (platform 0.1.1), `docs\MIGRATION.md`, `docs\VERSIONING.md`.
- Beside the zip (local): `MANIFEST_modkit_0.2.0.json`, `SHA256SUMS_modkit_0.2.0.txt`, `MANIFEST_host_p3_reference.json`
  (the p3 host distribution layout, without the exe) and the LOCAL ONLY host distribution `host_dist\bmashup-host-p3-0.1.1`.

Known
- bmpack 1.2 keeps at most 640 characters of an admission reason; the game prints the whole reason (cosmetic, roadmap).
- Not launched: any plugin on p3; SDK 0.3.0's two new module builds anywhere (COMPATIBILITY.md s0).

## 0.1.0 - 2026-10-26 (first kit; offline verified; host p2 later launched in 55 / 56)
Host: `burnout3_bmp_p2.exe` sha256 `e73ef9004fbe053bc585d4fa5451a546f1dc92b1da1d879afb855d47b2b59338`, build identity
`bmp-0.1.0+b8710764485c`, Burnout Mashup platform 0.1.0 (referenced, not included). Drop-in runtime evidence: host p1
(the same platform 0.1.0), launches 51-54.

Contents
- `sdk\` bmashup-sdk **0.2.0** (from 0.1.0): headers of host p2 (16, incl. bmashup_host.h / bmashup_hooks.h /
  bmashup_patch.h), catalogue of 14 services with bmashup.host first, `BMSDK_REFERENCE_BUILD`, the end-of-offers helper
  (`BMSDK_DEFINE_SERVICES_DONE`) with the 0.1.0 shutdown fallback, new examples hooks (owner + rival), patch (published
  site), host-info (identity check); every example mod.toml with `[bmashup] platform` / `requires` (SDK CHANGELOG).
- `prebuilt\` the SDK examples built (byte-identical in two builds) + `APPROVALS.txt`.
- `tools\bmpack\` bmpack **1.1**: `validate` runs the platform gate (same verdict and text as the real p2 gate and the
  game's log); `verify` hardened; default tree tree_p2; checker cache outside the tool (BMPACK_CACHE). Output format unchanged.
- `tools\stage_verify.py`: the zip checked from a clean staging copy, up to the game launch.
- `examples\mods\` the specs + expected mod.toml of the two drop-in test packs (no game data).
- `docs\` INSTALL, MODDING_GUIDE, COMPATIBILITY (all coverage limits), ROADMAP, this file.
