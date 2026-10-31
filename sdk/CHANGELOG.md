# Changelog - bmashup-sdk

## 0.6.0 - 2026-10-28 (in mod kit 0.6.0; reference host main19)
- Reference host: main19 `burnout3_gp_main19_final.exe` sha256 `8675e61d4c149eb1b1fd1f5d360f2e5464e1580f9a9da520114bfc4576bc1b45`, identity `bmp-0.1.9+0620fe316156`, platform 0.1.9
  (`bmashup_sdk.h` BMSDK_REFERENCE_*; BMSDK_VERSION 0.6.0). Headers: byte copies of the main19 tree (`include\HEADERS_FROM_MAIN19.txt`).
- Append-only ABI growth (old plugins bind unchanged): bmashup_racers.h 3 (`bm_racer_info` 52 -> 160 bytes: gear, speed,
  dynamics, parts, lights, controls; `detach_part`, `set_light`, `light_available`, `award_score`, `release`, `result_text`),
  bmashup_vphysics.h 3 (`set_gearbox`, `request_gear`, `gearbox_status`, 40-byte status), bmashup_traffic.h 3 (status 60 -> 72;
  `near_vehicles`, `wreck`, `clear_wrecked`; `bm_traffic_vehicle` 36 bytes), bmashup_hooks.h 3 (points 8..13, `BM_HOOK_POINTS_V3`
  13; `bm_hook_ctx` / `bm_hook_out` grow; table unchanged), bmashup_events.h 7 (events 8, 10, 11, 12; `bm_event` grows; table
  unchanged), bmashup_camera.h 2 (`set_adjust`, `release_adjust`, `set_finish_poses`; state 48 -> 68), bmashup_hud.h 2 (`draw`,
  `texture_info`, `draw_available`). NEW bmashup_paints.h 1, bmashup_menu.h 1, bmashup_rules.h 1.
- bmashup_sdk.h: catalogue 25 services; BMSDK_{RACERS,VPHYS,TRAFFIC,HOOKS}_TABLE_V3, BMSDK_EVENTS_TABLE_V7,
  BMSDK_CAMERA_TABLE_V1 / V2, BMSDK_HUD_TABLE_V2, BMSDK_{PAINTS,MENU,RULES}_TABLE_V1, BMSDK_RACER_INFO_V3,
  BMSDK_TRAFFIC_STATUS_V3, BMSDK_HOOK_CTX_V3, BMSDK_HOOK_OUT_V3, BMSDK_EVENT_SIZE_V7.
- A few 0.6.0 functions still answer UNAVAILABLE on the 0.1.9 host (engine rpm, traffic near_vehicles / wreck / clear_wrecked, paint DECALS / WHEELS, garage stat bars)
  and the indicator blink is not confirmed in stills (service pages): a bound table is not a working feature.
- `bmashup_racers.h` carries `lamp_counts` (appended to the v3 table).
- Examples: 15 new; every 0.5.0 / 0.4.4 example builds unchanged against 0.6.0 (-Wall -Wextra -Werror).

## 0.5.0 - 2026-10-28 (in mod kit 0.5.0; reference host main18)
- Reference host: main18 `burnout3_gp_main18.exe` sha256 `36859ca4cf4e8b03670cacdc69a11bf34de25856728a241566e6f7f98f38b4ec`, identity `bmp-0.1.8+fcf55c586f78`, platform
  0.1.8 (`bmashup_sdk.h` BMSDK_REFERENCE_*; BMSDK_VERSION 0.5.0). Headers: byte copies of the main18 tree
  (`include\HEADERS_FROM_MAIN18.txt`).
- Append-only ABI growth (old plugins bind unchanged): bmashup_boost.h 2 (`award`, `award_status`, codes 15..17),
  bmashup_racers.h 2 (`bm_racer_info` 28 -> 52, `order`, `session`, code 4), bmashup_traffic.h 2 (`set_density_v2`, status
  56 -> 60), bmashup_vphysics.h 2 (vehicle query, codes 10 / 11), bmashup_patch.h 2 (TABLE sites, `request_site_pair`, code 17,
  site_info v2 fields), bmashup_hooks.h 2 (point 7, ctx v2 fields; table unchanged), bmashup_settings.h 2 (`reserved_v1` +
  `scope`, `subscribe2`, `get_player`, code 8). NEW bmashup_hud.h 1 and bmashup_input.h 1.
- bmashup_sdk.h: catalogue 22 services; table / struct size macros BMSDK_{BOOST,RACERS,TRAFFIC,VPHYS,PATCH,SETTINGS}_TABLE_V2,
  BMSDK_HOOKS_TABLE_V2, BMSDK_HUD_TABLE_V1, BMSDK_INPUT_TABLE_V1, BMSDK_RACER_INFO_V2, BMSDK_TRAFFIC_STATUS_V2,
  BMSDK_HOOK_CTX_V2, BMSDK_PATCH_SITE_INFO_V2, BMSDK_SETTING_DECL_V2.
- Examples: 9 new (bm-boost-award, bm-racers-order, bm-traffic-x3, bm-vphysics-garage, bmashup-hud-shake, bmashup-input-log,
  crash-hooks, damage-panels, per-player-settings); every 0.4.4 example builds unchanged against 0.5.0 (-Wall -Wextra -Werror).

## 0.4.2 - 2026-10-27 (in mod kit 0.3.1; reference host p4.2)
- Reference host: p4.2 `burnout3_gp_p4_2.exe` sha256 `4fd86d1066aeb6fc210e28e463178c45c31cf75f2f8a0d2890c4e86fc58dcf4b`,
  identity `bmp-0.1.5+0db09076e5b8`, platform 0.1.5 (`bmashup_sdk.h` BMSDK_REFERENCE_*; BMSDK_VERSION 0.4.2).
- No ABI change. `bmashup_vphysics.h`: comment only - the writable values are Drag Coef (0.25..4) and "Max Speed In Boost"
  (0.5..2), the latter being the car's TOP-SPEED LIMIT (caps normal AND boost speed; runtime gp_p41g_2). Every other host header
  is byte-identical to 0.4.1 (`include\HEADERS_FROM_P42.txt`).
- Data-mod tables of platform 0.1.5 (no header): `[bmashup.cars] version = 1`, `[bmashup.world_tour] version = 1`.
- Examples: unchanged sources (the host-info module's bytes change with the reference strings).

## 0.4.1 - 2026-10-27 (in mod kit 0.3.0; reference host p4.1)
- Reference host: p4.1 `burnout3_gp_p4_1b.exe` sha256 `80b7aea9d74381c0aa729d02ccba6eb59ff6668b8f0e71965ff308f79087581a`,
  identity `bmp-0.1.4+bbfb763a604a`, platform 0.1.4.
- `bmashup_tune.h` version 3: 158 entries (+ 73 AI ValueDB values), signed entries, `bm_tune_info` 184 -> 200 bytes (min,
  is_signed, applies); BMSDK_TUNE_INFO_V3. Every other header byte-identical to 0.4.0 (`include\HEADERS_FROM_P41.txt`).
- Data-mod tables of platform 0.1.4 (no header): `[bmashup.tune] version = 2`, `[bmashup.music] version = 1`; the host setting
  GARAGE PAINT 7-8.
- Examples (j)-(q) added in the kit: autopilot-demo, vphysics-demo, traffic, ai, crash-scores, camera-fov, tune-ai,
  music-pack; `EXPECTED_BUILD_SHA256.txt`. The nine 0.3.0 examples are unchanged; `cmake\bmsdk.cmake`, `build.ps1`, `BUILD.md`
  carry the new version number only.

## 0.4.0 - 2026-10-27 (p4 integration; not released in a kit)
- Reference host p4 (`burnout3_gp_p4.exe` 4d0d20ff8791, identity bmp-0.1.3+9ae165af1e28), platform 0.1.3.
- New service headers: `bmashup_vphysics.h`, `bmashup_crash.h`, `bmashup_traffic.h`, `bmashup_ai.h`, `bmashup_settings.h`,
  `bmashup_camera.h`. Changed: `bmashup_autopilot.h` version 2 (engage2, release), `bmashup_events.h` version 6
  (CRASH_RESULT; `bm_event` 84 -> 128 bytes, older fields at the same offsets).
- `bmashup_sdk.h`: catalogue of 20 services in p4's offer order, BMSDK_HOST_MAX_SERVICES 32, BMSDK_EVENTS_TABLE_V6,
  BMSDK_EVENT_SIZE_V6, BMSDK_AUTOPILOT_TABLE_V2. The helper API is unchanged; 0.3.0 plugins and sources build / bind.

The SDK's own version (VERSIONING.md). Service versions are the host's and are listed per release.

## 0.3.0 - 2026-10-26 (offline verified against host p3; part of the mod kit 0.2.0)
Reference host: `burnout3_bmp_p3.exe` sha256 `6f008b218400d62df2c042c5aa5d23dbdcda3d27eac2807146e93d5853e009ed`, build
identity `bmp-0.1.1+b56e33b66dc3`, Burnout Mashup platform 0.1.1. A new reference host means a new SDK version
(VERSIONING.md); the content changed, so the package moves to 0.3.0. **No service ABI version changed**: host p3's 16 public
headers are byte-identical to p2's (`HEADERS_FROM_P3.txt` records the same hashes).

Changed
- `bmashup_sdk.h`: `BMSDK_VERSION_*` 0.3.0; `BMSDK_REFERENCE_HOST` / `BMSDK_REFERENCE_BUILD` / `BMSDK_REFERENCE_PLATFORM` = p3
  (`burnout3_bmp_p3.exe sha256 6f008b21...`, `bmp-0.1.1+b56e33b66dc3`, `0.1.1`). Catalogue (14 services, versions, order)
  unchanged. No function, macro, diagnostic text or struct changed.
- `include\HEADERS_FROM_P3.txt` replaces `HEADERS_FROM_P2.txt` (same 16 hashes).
- Build files: `build.ps1`'s default folder `..\build\bmashup-sdk-0.3.0`; texts.
- Example (h) host-info: comments for p3 (its code is unchanged; its bytes change with the reference constants).

Added
- Example (i) `events-v2` (data-only): `[bmashup.extra_events] version 2` with `names` / `help`, `[bmashup] platform =
  ">=0.1.1"`, `requires = ["bmashup.tracks>=1", "bmashup.extra_events>=2"]` (refused alone by a platform 0.1.0 host).

Binaries (deterministic builds, two builds identical): boost-modifier, capacity, hooks demo / rival, patch, track-names
are byte-identical to SDK 0.2.0's (approvals stay valid); events-observer (logs `BMSDK_VERSION_STRING`) and host-info
(compares `BMSDK_REFERENCE_BUILD`) have new bytes. SDK 0.2.0 modules keep binding to p3 (offline, the kit's verification).
The unchanged examples' files are byte-identical to SDK 0.2.0's, so their first comment lines still read "bmashup-sdk 0.2.0 example (x)" (kept on purpose: unchanged bytes, unchanged mod.toml).
## 0.2.0 - 2026-10-26 (offline verified against host p2; not runtime verified as SDK builds)
Reference host: `burnout3_bmp_p2.exe` sha256 `e73ef9004fbe053bc585d4fa5451a546f1dc92b1da1d879afb855d47b2b59338`,
build identity `bmp-0.1.0+b8710764485c` (Burnout Mashup platform 0.1.0; p2 = p1 + a reproducible build identity). Part of the local mod kit `bmashup-modkit-0.1.0`.

Added
- `include\`: 3 new host headers, byte copies of host p2 (`HEADERS_FROM_P2.txt`, replaces HEADERS_FROM_CAND2.txt; p2's headers = p1's):
  `bmashup_host.h` (bmashup.host 1 + the optional export `takedawn_plugin_services_done`), `bmashup_hooks.h`
  (bmashup.hooks 1), `bmashup_patch.h` (bmashup.patch 1). The other 13 headers are unchanged (byte-identical to 0.1.0's).
- `bmashup_sdk.h`: catalogue of 14 services, bmashup.host first (`BMSDK_SERVICE_COUNT` 14); `BMSDK_HOST_TABLE_V1`,
  `BMSDK_HOOKS_TABLE_V1`, `BMSDK_PATCH_TABLE_V1`; `BMSDK_REFERENCE_PLATFORM`, `BMSDK_REFERENCE_BUILD`; `bmsdk_host`, `bmsdk_host_offers`,
  `bmsdk_host_missing`, `bmsdk_services_done`, `bmsdk_offers_done`, `bmsdk_offers_seen`, `bmsdk_host_state_get`,
  `BMSDK_DEFINE_SERVICES_DONE(needs, reported)`.
- Examples: (f) hooks owner + rival, (g) published-site patch, (h) host-info probe.
- Every example mod.toml: `[bmashup] platform = ">=0.1"` and the services / tables it requires at the versions p2 offers; the content template
  declares two World Tour events (the platform host takes up to 35).

Changed
- `bmsdk_offer` also keeps a usable `bmashup.host` table and counts every offer (its signature, return value and the
  states of `bmsdk_need` are unchanged).
- The four plugin examples (a)-(d) export `takedawn_plugin_services_done` (via the macro): on a platform host "missing"
  is said during the start; on older hosts as before. Their module bytes (and so their approvals) changed.
- `BMSDK_SERVICE_COUNT` 11 -> 14 and the catalogue's order (now the host's offer order): a minor-version change while the
  major version is 0 (VERSIONING.md).
- Build: `build.ps1`'s default folder is `..\build\bmashup-sdk-0.2.0`.

Unchanged: every diagnostic text, `bmsdk_need`'s layout, the 0.1.0 functions and macros.

## 0.1.0 - 2026-10-26 (first release; offline verified, not runtime verified)
Reference host: `burnout3_g8cand2.exe` sha256 `8d570f8d7101a9fcb23d17ff9f90b1d0b45449a5e81440a0f5c77a1ee2b7100b`
(G8 consolidated candidate 2).

Added
- `include\`: the host's 13 public headers, byte copies of candidate 2 (`HEADERS_FROM_CAND2.txt`): takedawn_plugin.h
  (plugin API 1), takedawn_services.h, takedawn_race.h (takedawn.race 1), bmashup_autopilot.h (1), bmashup_boost.h (1),
  bmashup_engine.h (1), bmashup_events.h (5), bmashup_memory.h (1), bmashup_names.h (1), bmashup_racers.h (1),
  bmashup_route.h (2), bmashup_streaming.h (2), bmashup_tune.h (2).
- `include\bmashup_sdk.h` (header only): SDK version macros; the service catalogue (`bmsdk_catalogue`); the discovery /
  capability helper on the host's offer callback (`bmsdk_need`, `bmsdk_offer`, `bmsdk_has`, `bmsdk_fail`,
  `bmsdk_describe`, `bmsdk_log_need`, `bmsdk_report`, `bmsdk_report_once`) with fixed diagnostic texts; append-only struct
  helpers (`BMSDK_FIELD_END`, `BMSDK_HAS_FIELD`, `BMSDK_*_TABLE_V*`); `BMSDK_DEFINE_API_VERSION()`.
- Examples: (a) events observer, (b) capped boost modifier, (c) track names from plugin memory, (d) capacity -
  declaration-only mod and request plugin, (e) data-only content template; CMake build of all (`build.ps1`).

Known limits
- The host has no pull-style service lookup and no end-of-offers signal: "missing" can only be reported after the start
  (SDK_REPORT.md gaps G1 / G2). Handled in the SDK without changing the host. (Answered by host p1 / p2 and SDK 0.2.0.)
- Windows x64 only.

## Mod kit 0.7.0 (host main21, platform 0.1.9, SDK 0.7.0)
Reference host main21 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`, identity `bmp-0.1.9+2c8142e65f20` (previous: main19_final `8675e61d4c14`). New: SDK headers bmashup_camera.h, bmashup_hooks.h, bmashup_hud.h, bmashup_menu.h, bmashup_paints.h, bmashup_racers.h, bmashup_rules.h, bmashup_settings.h, bmashup_traffic.h, bmashup_tune.h (changed) / - (new); examples added bm-ai-names, bm-free-camera, bm-headlights, bm-traffic-attack, bm-traffic-kamikaze; trackbuild 0.3.0 (sloped routes); Workbench 0.29 in `workbench\`; PS2-look converter in `tools\ps2look` (tool only: it builds the shadow / spark mod from YOUR disc; nothing of the game is shipped); `HOST_INFO.json` and `docs\TUNING_CATALOGUE.md` generated from the host. Details of the host changes: `docs\services\`. (Generated by the release builder; prose review pending.)
