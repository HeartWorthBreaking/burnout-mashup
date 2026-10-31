# Author docs for platform 0.1.9 (mod kit 0.7.0)

**EXPERIMENTAL, Windows x64, LOCAL - not published.** Reference host main19 (identity `bmp-0.1.9+2c8142e65f20` (sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`); main19 = main18 + the 256 MB guest
window + hook request phases 2 and 3, platform **0.1.9**, 25 services). Every `bmashup.*` service / table is private to Burnout
Mashup builds and may change; the headers in `sdk\include` and the host's admission are the binding contracts, these pages
explain them with their evidence and limits.

## New in 0.6.0 (hook request phases 2 + 3, 256 MB window)
| Page | Service / topic | Status on 0.1.9 |
|---|---|---|
| `VPHYSICS_V3.md` | bmashup.vphysics 3: gearbox | built; RT; CHANGES GAMEPLAY |
| `RACERS_V3.md` | bmashup.racers 3: dynamics / parts / lights reads, detach, lights + indicators, award_score | built; detach any racer; rpm UNAVAILABLE; indicator control + lamp_counts work, the visual blink is not confirmed in stills |
| `TRAFFIC_V3.md` | bmashup.traffic 3: crash pool; near_vehicles / wreck / clear_wrecked | pool counts built (RT at density 3.0); the rest UNAVAILABLE |
| `HOOKS_V3.md` | bmashup.hooks 3: points 8..13 | built; all six points offered; 11 MODIFY re-credits at wreck time |
| `EVENTS_V7.md` | bmashup.events 7: twins of 8 / 10 / 11 / 12 | built |
| `CAMERA_V2.md` | bmashup.camera 2: chase adjust, finish poses | built; finish pose reduced (one pose, 40 m) |
| `HUD_V2.md` | bmashup.hud 2: draw list (QUAD, TEXT, SPRITE) | built (QUAD, TEXT, P8 SPRITE); no `[bmashup.hud]` table |
| `PAINTS.md` | NEW bmashup.paints 1: player car colour | built; BODY in races only (RT) |
| `MENU.md` | NEW bmashup.menu 1: popup, mode row, stat bars | popup and mode row built (RT); stat bars UNAVAILABLE |
| `RULES.md` | NEW bmashup.rules 1: Eliminator rules | built (RT) |
| `LIMITS.md` | + the 0.1.9 rows (256 MB window, new caps) | tested |

Limits: garage stat bars are UNAVAILABLE (`MENU.md`); the HUD sprite works (`HUD_V2.md`); the indicator blink is not confirmed in stills
(`RACERS_V3.md`). Everything else above was run in the retail game (validation rounds and a final exclusive acceptance race with
137 mods / 38 plugins).

## New in 0.5.0 (hook request phase 1 + limits)
| Page | Service / topic | Status |
|---|---|---|
| `PATCH_V2.md` | bmashup.patch 2: verified index-table sites (detach parts) | offline (real XBE census); in-game effect NT |
| `RACERS_V2.md` | bmashup.racers 2: place / laps / time / order / session | offline; rivals PARTIAL |
| `BOOST_V2.md` | bmashup.boost 2: award an amount | offline |
| `HUD.md` | bmashup.hud 1 (new): HUD element transforms | offline (real draw routine) |
| `SETTINGS_V2.md` | bmashup.settings 2: per-player settings | offline; no pause-menu entry |
| `INPUT.md` | bmashup.input 1 (new): read-only pad | offline |
| `VPHYSICS_V2.md` | bmashup.vphysics 2: handling values outside a race | offline (= retail data) |
| `TRAFFIC_V2.md` | bmashup.traffic 2: density up to 3.0 | offline; > 2.0 EXPERIMENTAL |
| `HOOKS_V2.md` | bmashup.hooks 2: point 7 CRASH_RESULT | offline |
| `LIMITS.md` | + 256 mods / folders, 64 texture / music mods, 1024 off ids | offline 64 / 65 / 256 / 257 |

Runtime acceptance of all of these: pending at the time of writing.

## New in 0.4.0 (content)
| Page | Table / topic | Status (details on the page) |
|---|---|---|
| `TEXTURES.md` | `[bmashup.textures]` 1 (front-end textures, own garage photos) | RT individual (fetex1) and combined (p4.3) |
| `WT_MAP_ART.md` | `[bmashup.wt_map_art]` 1 (own 4th-region map art / marker / texts) | RT individual and combined; page globe / counters still borrowed |
| `CARS.md` | `[bmashup.cars]` 1 / 2, `[bmashup.series]` 1, `[bmashup.paints]` 1 | RT individual (cars2, veh1, carimport) and combined (p4.3) |
| `LIMITS.md` | mod.toml 64 KiB, vehicle / series / paint / texture limits | ceilings / configured / tested / demonstrated |
| `AUTHORING_TOOLS.md` | carimport, trackbuild, fetex, vehtool, bmpack 1.5.0 (portable; trackconv not shipped) | tests per tool; AUTHORED vs DONOR parts |

## From kits 0.3.0 / 0.3.1 (unchanged pages, evidence updates inside)
`AUTOPILOT.md`, `VPHYSICS.md` (incl. the top-speed-limit correction), `TRAFFIC.md`, `AI.md`, `CRASH_EVENTS_V6.md`, `SETTINGS.md`,
`CAMERA.md`, `REQUIRES_MODS.md`, `MUSIC.md`, `TUNE_V3_AI.md`, `GARAGE_PAINTS.md`, `WORLD_TOUR.md`; the host's own pages in `host\`.
Their statuses refer to the hosts named on each page (p4 / p4.1 / p4.2); p4.3 carries that code (25 / 25 regression suites) and
re-ran the p4.2-era sets together in gp_p43_3.
