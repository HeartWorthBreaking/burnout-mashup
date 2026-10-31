# Migration: mod kit 0.6.0 / host main19_final -> mod kit 0.7.0 / host main21

## For players
- Reference host main19_final -> **main21** (identity `bmp-0.1.9+2c8142e65f20`, sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`). The platform version stays **0.1.9**.
- Back up your profile first (the launcher's Help tab, or `remove.cmd backup`), then use the new host.
- Plugins are approved by their exact sha256. A plugin that was rebuilt (for example against the 0.7.0 headers) has new bytes and
  has to be approved again: Settings > MODS > select the mod > Approve and turn on.
- To get sloped routes, rebuild a track with trackbuild 0.3.0. Tracks you built earlier are not changed by the new tool.

## For mod authors
- Plugins built with older headers bind as before: every table and struct only grows at its end (struct_size / version gating).
- **The platform version did not change (0.1.9), the service versions did.** main19_final is also platform 0.1.9 but offers older
  services (for example racers 3, traffic 3, camera 2, rules 1). State the service versions your mod needs, and check at run
  time:

      [bmashup]
      platform = ">=0.1.9"
      requires = ["bmashup.racers>=6", "bmashup.rules>=6", "bmashup.traffic>=8", "bmashup.camera>=4"]   # only what you use

  In the plugin: `BMSDK_NEED(...)` as before, and read new struct fields only under `BMSDK_HAS_FIELD`. Versions in the 0.7.0 headers:
  racers 6, rules 6, traffic 8, camera 4, hooks 3, events 7, settings 2, tune 3.
- Behaviour changes to check in your mods: NO_CRASH now really skips the crash (before, only the push was kept), and its
  closing-speed bound is 60 m/s (was 25).
- Some calls depend on a hook switch of the host build and answer UNAVAILABLE when it is off (the default host has them on, except
  parked traffic). Check the result code and the `*_available` calls before relying on a feature, and keep working without it.
- Content: validate with **bmpack 1.5.0** (unchanged).

## Earlier migration (kit 0.6.0 text, unchanged)
# Migration: mod kit 0.5.0 / host main18 -> mod kit 0.6.0 / host main19

## For players
- Reference host main18 -> **main19** (identity `bmp-0.1.9+0620fe316156` (sha256 `8675e61d4c149eb1b1fd1f5d360f2e5464e1580f9a9da520114bfc4576bc1b45`), platform 0.1.9). Mods, saves, sidecars, plugin approvals, plugin settings
  and the mod list carry over unchanged.
- Big content sets that stopped with "guest 64 MB window full" on 0.1.7 / 0.1.8 now have room (the host's expansions moved to
  the 256 MB window's high zone). If a set is still too big, the start stops with a message naming the budget (exit 86)
  instead of crashing.

## For mod authors (nothing breaks)
- Plugins built with SDK 0.5.0 (or older) headers bind unchanged: every table / struct only grew at its end (struct_size /
  version gating); a v2-sized caller sees v2 behaviour byte for byte.
- To use a 0.1.9 feature, declare it and check it at run time:

      [bmashup]
      platform = ">=0.1.9"
      requires = ["bmashup.vphysics>=3"]       # or racers / traffic / hooks >= 3, events >= 7, camera / hud >= 2, paints / menu / rules >= 1

  In the plugin (SDK 0.6.0): `BMSDK_NEED(BM_VPHYS_SERVICE, 3, BMSDK_VPHYS_TABLE_V3, 1)`; read new struct fields only under
  `BMSDK_HAS_FIELD` (`BMSDK_RACER_INFO_V3`, `BMSDK_TRAFFIC_STATUS_V3`, `BMSDK_HOOK_CTX_V3`, `BMSDK_HOOK_OUT_V3`,
  `BMSDK_EVENT_SIZE_V7`).
- **A bound v3 table does not mean every v3 function works.** On 0.1.9 a few functions answer UNAVAILABLE (engine rpm, traffic near_vehicles / wreck / clear_wrecked,
  paint DECALS / WHEELS, garage stat bars; list in the CHANGELOG / `docs\services\README.md`) and the indicator blink is not confirmed in stills. Handle it like a refusal: check the result code, `point_info().available`
  (hooks 8..13), `draw_available()` (hud), `feature_available()` (menu), `status().available` (gearbox) before relying on a
  feature, and keep working without it. Do not depend on a UNAVAILABLE function becoming available in a given host.
- CHANGES GAMEPLAY labels (say so in your mod's description; the host logs them): gearbox MANUAL, TRAFFIC_CONTACT NO_CRASH,
  EVENT_SOUND level (audio), award_score and rules (when offered). Detach / lights / paints change looks only.
- Controls have one owner and are given back at RACE_EXIT / restart: set them again for each race.
- `[bmashup.hud]` (HUD textures) is NOT a table platform 0.1.9 reads: a mod that declares it is refused by the admission
  ("needs a newer platform", as any unknown `[bmashup.*]` table). Do not declare it yet.
- Player 1 (split screen): every new control answers UNSUPPORTED.
- Content: validate with **bmpack 1.5.0** (main19 readers); 1.4.0 refuses `platform = ">=0.1.9"`.

## Earlier migration (kit 0.5.0 text, unchanged)

# Migration: mod kit 0.4.4 / host capmega1 -> mod kit 0.5.0 / host main18

## For players
- Reference host capmega1 -> **main18** (identity `bmp-0.1.8+fcf55c586f78` (sha256 `36859ca4cf4e8b03670cacdc69a11bf34de25856728a241566e6f7f98f38b4ec`), platform 0.1.8). Mods, saves, sidecars, plugin approvals,
  plugin settings and the mod list carry over unchanged (the files only grow: the mod list may now hold 1024 ids).
- More than 8 mod folders: list them in a text file and set `BMASHUP_MODS_FILE` to it (one folder a line; see
  `docs\LIMITS_AND_BEHAVIOURS.md` 0e). `BMASHUP_MODS` keeps working and comes first.
- A file you drop into a loose mod folder while the game runs is used from the next start.

## For mod authors (nothing breaks)
- Every service keeps its version 1 behaviour for plugins built with older headers: tables and structs only grew at their end
  (struct_size / version gating), result codes were appended. Old plugins need no rebuild (all kit 0.4.4 examples build and bind).
- To use a 0.1.8 feature, declare it in mod.toml and check it at run time:

      [bmashup]
      platform = ">=0.1.8"
      requires = ["bmashup.boost>=2"]          # or racers / traffic / vphysics / patch / hooks / settings >= 2, hud / input >= 1

  In the plugin (SDK 0.5.0): `BMSDK_NEED(BM_BOOST_SERVICE, 2, BMSDK_BOOST_TABLE_V2, 1)`, call `award` only when bound; read
  new struct fields only under `BMSDK_HAS_FIELD` (e.g. `BMSDK_RACER_INFO_V2`, `BMSDK_HOOK_CTX_V2`, `BMSDK_SETTING_DECL_V2`).
- traffic: 3.0 needs the new `set_density_v2`; `set_density` stays bounded at 2.0.
- settings: a per-player setting needs `struct_size >= BMSDK_SETTING_DECL_V2` and `scope = BM_SETTING_SCOPE_PER_PLAYER`; limits
  are now 8 a plugin / 128 in all for everyone.
- Content: mod sets of up to 256 mods; `bmpack 1.4.0 validate` uses the main18 readers (64 music / 64 texture mods).

## Earlier migration (kit 0.4.4 text, unchanged)

# Migration: mod kit 0.4.3 / host capfix1 -> mod kit 0.4.4 / host capmega1

## For players
- Reference host capfix1 -> **capmega1** (bmp-0.1.7+9c6131448f9b, platform 0.1.7): build it from the host source package of tester package 0.2.4
  (or use the prebuilt host where you were given one). Mods, saves, sidecars and plugin approvals carry over unchanged.
- Everything that ran on capfix1 runs on capmega1 (the T1 chevron guard is kept).

## For mod authors
- New: `[bmashup.capacity] gamedata_bytes` (say `platform = ">=0.1.7"`). Big tracks: `docs\services\CAPACITY.md`.
- Nothing else changes: same tables, keys, tools and SDK headers.

## Earlier migration (kit 0.4.3 text, unchanged)

## mod kit 0.4.2 / host clean1 -> mod kit 0.4.3 / host capfix1

## For players
- Reference host clean1 -> **capfix1** (bmp-0.1.6+0c5a321ae0fa): build it from the host source package of tester package 0.2.2 (or use the
  prebuilt host where you were given one). Mods, saves, sidecars and plugin approvals carry over unchanged.
- **Tracks made with trackbuild <= 0.2.0 (BM Test Loop, BM Canyon Ring, your own): rebuild them with trackbuild 0.2.1.** capfix1
  also protects old tracks (it logs `[CHEVRON] unit chevron index 0 is outside the track's chevron set ...` once), but rebuilt
  tracks are the supported form.
- The capacity example plugin can be used again.

## For mod authors
- trackbuild 0.2.1: `validate` adds gate V10 (chevron index in set); nothing else changes in the package format.

## Earlier migration (kit 0.4.2 text, unchanged)

## mod kit 0.4.1 / host p4.4 -> mod kit 0.4.2 / host clean1

## For players
- The reference host changes from p4.4 (`burnout3_gp_p4_4.exe`, bmp-0.1.6+ab3a98869d10) to **clean1** (bmp-0.1.6+345dc71c5cd3). In this alpha you build
  it yourself from the host source package with your own game (`burnout3_bmashup.exe`, tester package `BUILD_HOST.md`).
- Nothing else changes: same platform 0.1.6, services, tables, mod admission, saves, sidecars and plugin approvals (approvals are
  per plugin bytes; the SDK and the example plugin bytes are unchanged).
- Texture upscale (`graphics.texture_upscale`) needs `shaders\upscale` beside the exe (the source build puts it there). Without
  it the log says `[TEXUP] no shader files found: texture upscale stays off` and the game runs normally.

## For mod authors
- Nothing to change. bmpack 1.3.4's readers are the same source bytes; its summary line now names clean1.

## Earlier migration (kit 0.4.0 text, unchanged)

## mod kit 0.3.1 / host p4.2 -> mod kit 0.4.0 / host p4.4

## For players
- The host changes to `burnout3_gp_p4_4.exe` (platform 0.1.6). Same folders and `play.cmd` pattern (only the exe name). Mods, approvals,
  settings and sidecars carry over; a new sidecar `Profile 1 veh.bmprog` keeps registered paint choices.
- New content kinds: new car series, many more cars (1024-entry list), registered paints, own garage photos, own 4th-region map art,
  authored cars and tracks. Remove a content mod at any time: the profile still loads (retail garage / regions).

## For mod authors
- New tables need `platform = ">=0.1.6"` (or `requires = ["bmashup.textures>=1"]` etc.). `[bmashup.cars] version = 2` for the new
  keys (model / unlock / ai / photos); version 1 files keep working.
- One mod.toml may now be up to 65536 bytes (8192 before): fewer split mods for large registries (vehtool 0.1.1 splits at 65536).
- bmpack 1.3.3 validates World Tour region mods (1.3.1 refused them falsely); set `BMPACK_TREE` to the reference host's tree.
- SDK unchanged (0.4.2).

## Earlier migrations (kit 0.3.1 text, unchanged)

## For players
- The host changes: `burnout3_gp_p4_1b.exe` (platform 0.1.4) -> `burnout3_gp_p4_2.exe` (platform 0.1.5). Same folders and
  `play.cmd` pattern (only the exe name). Mods, approvals and settings carry over (plugin bytes built with kit 0.3.0 that did not
  change keep their approvals; compare with `sdk\EXPECTED_BUILD_SHA256.txt`).
- New: added cars (last row of their series) and a 4th World Tour region (borrowed map) as data mods. Removing an added-car mod
  leaves a loadable profile (a retail car is selected).

## For mod authors
- New tables need `platform = ">=0.1.5"` (or `requires = ["bmashup.cars>=1"]` / `["bmashup.world_tour>=1"]`); older hosts refuse
  the mod alone.
- `bmashup.vphysics`: "Max Speed In Boost" is the car's top-speed limit (normal AND boost). Code that assumed a boost-only effect
  should be re-checked; no ABI change.
- Build against SDK 0.4.2; 0.4.1 sources compile unchanged. Validate with bmpack 1.3.1 and `BMPACK_TREE` = the p4.2 tree.

## Earlier migrations (kit 0.3.0 text, unchanged)

## For players
- The host changes: `burnout3_bmp_p3.exe` (platform 0.1.1) -> `burnout3_gp_p4_1b.exe` (platform 0.1.4). Same folder layout,
  same `play.cmd` pattern (only the exe name), same profile / mods folders. Your mod list and approvals carry over; plugin
  approvals are per exact bytes, so a module you rebuild with kit 0.3.0 needs a new approval line if its bytes changed.
- New on the MODS page: **MOD SETTINGS** (plugin settings + the host's GARAGE PAINT 7-8, default OFF), `NEEDS MOD` states.
- Music packs are staged into `%LOCALAPPDATA%\BurnoutMashup\music-cache` (with `play.cmd`: `profile\Local\...`); delete the
  folder any time to reclaim space (nothing is ever deleted by the host).
- p3-era mods keep working: their tables and services are unchanged (regression suites on p4 / p4.1; legacy plugin
  binaries of events v2-v5 bind).

## For mod authors
- Data mods: new `[bmashup] requires_mods`, `[bmashup.music] version 1`, `[bmashup.tune] version = 2` (AI values, negative
  values). Say `platform = ">=0.1.4"` (or name the table / service in `requires`) when you use them, so older hosts refuse your
  mod alone.
- Plugins: build against `sdk\include` (SDK 0.4.1). Sources written for SDK 0.3.0 compile unchanged (verified for the nine
  0.3.0 examples). New services: `docs\services\`. `bm_event` is 128 bytes in events 6; older plugins read their prefix.
- `bmashup.autopilot` 1 callers keep working (once per race as before); use `engage2` for an explicit per-race request and
  `release` for the hand-back.
- bmpack 1.3: set `BMPACK_TREE` to the p4.1 tree when validating for this host.
- No prebuilt modules ship: build with `sdk\build.ps1`.

## Earlier migration (kit 0.1.0 / p2 -> kit 0.2.x / p3), unchanged from kit 0.2.1

| | before | now |
|---|---|---|
| host | `burnout3_bmp_p2.exe` `e73ef900...`, identity `bmp-0.1.0+b8710764485c`, **platform 0.1.0** | `burnout3_bmp_p3.exe` `6f008b21...`, identity `bmp-0.1.1+b56e33b66dc3`, **platform 0.1.1** |
| mod kit | 0.1.0 | 0.2.1 (= 0.2.0 + documentation fixes; same SDK, tools, examples) |
| SDK package | 0.2.0 | 0.3.0 |
| bmpack | 1.1 | 1.2 |
| service ABI versions | 14 services | the same 14, same versions, headers byte-identical |
| `[bmashup.extra_events]` | version 1 | versions 1 and 2 (2 = + `names`, `help`) |

Version domains are separate (platform 0.1.1 is not kit 0.2.1): VERSIONING.md. Evidence labels: **RT** = seen in a guarded
launch on p3 (bmp_p3_1 / bmp_p3_2; plugin start-up only: bmp_kit2_1, boot only, no race), **OFF** = offline with the host's
real code (this kit's verification, KIT2_REPORT).

## For players
1. **Install the p3 host** as a NEW host folder (INSTALL.md checklist), or replace the contents of your `bin\` with the
   p3 host distribution. Keep your `profile\` (settings, saves, approvals, `.bmprog` sidecars) and your `mods\` folders.
   Check the identity: `check_host` PASS, boot line `[PLATFORM] host: Burnout Mashup platform 0.1.1, build
   bmp-0.1.1+b56e33b66dc3, ...`.
2. **Mods keep working.** Every content pack and every example of kit 0.1.0 is accepted by the p3 platform gate (OFF:
   gate agreement, 39 cases; the kit 0.1.0 packs `bmp_content_set` / `bmp_track_set` are the same bytes in this kit).
3. **Approvals:** six of the eight example modules have the same bytes as in kit 0.1.0 (approvals stay valid). The
   SDK 0.3.0 builds of `bmashup-sdk.events-observer` and `bmashup-sdk.host-info` have NEW bytes: if you replace those two,
   approve them again (`prebuilt\APPROVALS.txt`); if you keep the kit 0.1.0 files, nothing changes (they keep binding, below).
4. **What you will notice:**
   - two mods that declare the same track / name / location / event / region letter / tuning value, or that overfill a
     World Tour location's 6 rows: on p2 the start STOPPED (exit 92, one mod named); on p3 **the later mod is refused alone**
     before any of its declarations is used, the log names BOTH mods and folders, the game starts with the other mods
     (RT bmp_p3_2; OFF admission agreement). The MODS page shows the refused mod as `CONFLICT` with the reason.
   - data mods that change gameplay values (`[bmashup.tune]`, `[bmashup.capacity]`) are **labelled**: a `[MODS] <mod>
     changes gameplay: ...` log line and `CHANGES GAMEPLAY: ...` on the MODS page. Nothing is asked and nothing is stored
     (RT bmp_p3_2). Code approval is unchanged (per sha256).
   - World Tour events can carry their own row name and help text (mods that use `[bmashup.extra_events] version 2`).
5. **Progress / saves:** the `.bmprog` sidecar code (`bm_progress`, `bm_tracks_progress`) is p2's bytes (the p3 build audit
   lists the 12 objects that changed; those are not among them) and p3's offline tests load seeded sidecar records. FACT:
   format code unchanged; NOT TESTED: a p2-written sidecar read by p3 in the game. Retail saves are untouched as before.
   Back up `UDATA` and `bmashup\progress` before switching hosts.
6. **Rollback:** p2 and kit 0.1.0 stay frozen and valid (FREEZE_P3.md s3). Going back to p2: mods using `[bmashup.extra_events]
   version 2` are then refused alone (below); a cross-mod clash stops the start again (exit 92).

## For mod authors
### Content mods (data)
- **Nothing to change** for existing mods: version 1 tables read exactly as before.
- **New:** per-event list-row names and help texts. Write `[bmashup.extra_events] version = 2` and add `names` / `help`
  (MODDING_GUIDE.md s2; limits 19 / 97 characters). Declare `[bmashup] platform = ">=0.1.1"` and `requires =
  ["bmashup.extra_events>=2"]` so the need is explicit. bmpack 1.2: `[[event]] name / help` in a spec.
- **Such a mod needs p3.** A p2 (platform 0.1.0) host refuses it ALONE and starts without it (OFF: the real p2 gate and
  kit 0.1.0's bmpack 1.1 give the same text):
  `[PLATFORM] mod example.events-v2 0.3.0 refused, the game starts without it: needs a newer platform: [bmashup.extra_events]
  version 2; platform 0.1.0 reads version 1 (this host: Burnout Mashup platform 0.1.0)`.
  Want to support both hosts? Ship the events at `version = 1` (no names / help) - p3 reads that too.
- **Conflicts are now per mod.** Plan your ids: the order is `BMASHUP_MODS` folder order, then mod id; the LATER of two
  clashing mods is refused, together with mods that need content only it declares. What still stops the start: your
  mod's OWN invalid table (91 / 92 / 93), host guards, host integrity (MODDING_GUIDE.md s1).
- **Labels:** a mod with `[bmashup.tune]` or `[bmashup.capacity]` is shown as changing gameplay. Say so in its description.
- `bmpack validate` (1.2) now runs the admission and prints the same `[admission]` text the game logs (OFF: identical to
  the game's `[ADMIT]` line of bmp_p3_2; limitation: bmpack keeps up to 640 characters of a reason - fewer when the mod id /
  version / folder are very long - while the game keeps up to 699; verdict and refused mod agree).

### Code mods (plugins)
- **Plugins built with SDK 0.2.0 keep working on p3.** OFF: the mod kit 0.1.0 PREBUILT modules (events-observer +
  boost-modifier 20 / 20 checks, track-names 7 / 7, capacity 7 / 7, host-info 3 / 3) bound through tree_p3's real loader /
  registry / services with the same expected log lines as the new builds (KIT2_REPORT, sdk_p3 scenarios `*_kit010`). At
  runtime on p3, plugin START-UP is validated (bmp_kit2_1, boot only: 6 kit plugins, four of them with SDK 0.2.0 bytes -
  boost-modifier, hooks demo / rival, patch demo); plugin gameplay on p3 is not tested (COMPATIBILITY.md).
- **Rebuild only if you want SDK 0.3.0 constants.** SDK 0.3.0 changes `BMSDK_VERSION_*` ("0.3.0") and
  `BMSDK_REFERENCE_HOST / _BUILD / _PLATFORM` (p3); no function, macro, text or struct changed. A plugin that does not use
  those macros rebuilds to the SAME bytes (six of the eight examples did) - its approval stays valid.
- A plugin that compares `build` with `BMSDK_REFERENCE_BUILD` (like host-info) built with SDK 0.2.0 reports p3 as "not the
  SDK's reference build" - that is informational; the platform version decides compatibility.
- Plugin registrations are NOT part of the admission: a cross-mod clash between plugins (e.g. two names for one track via
  `bmashup.names`) is answered by the service with its CONFLICT code, as on p2.

## For tool users
- bmpack 1.2 replaces 1.1: default host tree `platform\host3\tree_p3`; 1.1 specs build byte-identical mods (OFF: the
  kit's packs rebuilt = the reference sets). New spec keys `[[event]] name / help`, `[tune] set`, `[capacity]`.
- `tools\stage_verify.py` now checks three example packs, the p3 host (or the p3 host distribution with `--host-zip`) and
  demonstrates the admission refusal.
