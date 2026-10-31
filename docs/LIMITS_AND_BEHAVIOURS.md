# Current limits and supported gameplay behaviours (mod kit 0.6.0, mainline reference host main19; evidence from main18 / mem256 / capmega1 / p4.4 / capfix1 / mega1 applies)

**Experimental, Windows x64 only.** Mainline reference host main19 (**platform 0.1.9**, identity `bmp-0.1.9+0620fe316156` (sha256 `8675e61d4c149eb1b1fd1f5d360f2e5464e1580f9a9da520114bfc4576bc1b45`); = main18
(`bmp-0.1.8+fcf55c586f78`) + mem256 (the 256 MB guest window) + hook request phases 2 and 3). Labels: **RT <host> (run)** = seen
in a guarded launch on that build; **OFF** = real host code in tests; **INC** inconclusive; **OPEN**; **NT** not tested.
Individual (slice / tool) and combined-host results are kept apart. Numbers: `docs\services\LIMITS.md`.

## 0f. Platform 0.1.9 (mainline host main19) - 256 MB window + hook request phases 2 and 3
main19 = main18 (0e below) + the two parts here. Runtime status of every 0.1.9 row: RT = seen in the retail game on main19 (three validation rounds, then an exclusive acceptance
race: 137 mods in 13 folders admitted, 38 / 38 plugins, finished 1st, no fault; peak 53,284 KB in the low 64 MB, 15,260 KB in the
high zone); the mem256 rows also carry the mem256 slice host's runs (same window code). Limits: stat bars are UNAVAILABLE and the
indicator blink is not confirmed in stills (rows below).

| Memory | 0.1.8 | 0.1.9 | Status |
|---|---|---|---|
| Guest contiguous window | 64 MB | **256 MB** (build option `BO3_GUEST_WINDOW_MB=64` = 0.1.8) | OFF (boundaries 64 MB-1 .. 256 MB, 13 / 13 compare mutants); RT mem256 host (m256_stress: expansions at 160-180 MB, race rendered correctly; m256_acc2: 16 / 16 plugins) |
| The game's own allocations | low 64 MB | **low 64 MB, the same addresses** (byte-identical sequence to retail) | RT mem256 host (4 runs) |
| Host expansions (STATIC, GAMEDATA, low-detail slots, front-end textures, paints, menu texts) | inside the 64 MB, competing with the game | **high zone 64..256 MB (192 MB)** | OFF; RT mem256 host (up to 123,316 KB used incl. a 96 MB test block) |
| Too many expansions | guest access violation at boot (cm1_acc_1) | **budget gate**: start stops with a message, exit 86 | OFF (unit + mutants); RT NT |
| A refused game allocation | access violation later | **exit 87** with the log written first | OFF; RT NT |

| Hook request phases 2 + 3 | Limits / rules | Status |
|---|---|---|
| Gearbox (vphysics 3) | player 0; one owner; shifts only through the game's routines; one host mark (idle re-shift to N skipped only while MANUAL is owned and the gear is 0) | OFF (real generated shift routines + idle block, 7 mutants); RT (MANUAL, gears read back) |
| Dynamics reads (racers 3) | sampled once a step at player 0's car update; `have_dynamics` after 3 steps; rpm not available; speed / accelerations host-derived | OFF; RT |
| detach_part / set_light (racers 3) | detach: state 2 (hanging) only, once per part per race, any racer; lights: head / tail / brake ON and the indicators (host blink about 1.5 Hz; lamps only on models with group 5 / 6 points), <= 10 changes a second per racer | OFF (real DetachBodyPart, 9 mutants); RT player 0 detach, indicator ON control; **visual blink not confirmed in stills** |
| award_score (racers 3) | 1..100000, 8 a second / 512 a race per plugin; adds to the HUD / results points | OFF; RT (32 x OK) |
| Traffic crash pool (traffic 3) | 64 slots, the game has NO full check; a wreck may take 3 slots; wreck refused unless >= 4 free and < 8 crashing; <= 4 a second per plugin | pool counts OFF; RT at density 3.0 (peak 8 / 64); wreck / near_vehicles / clear_wrecked UNAVAILABLE |
| Hook points | 13 (0.1.8: 7), all offered; WRECK_CAUSE observe + re-credit at wreck time | OFF (framework 77 checks, mutants); RT |
| TRAFFIC_CONTACT NO_CRASH | racer vs traffic only, same direction, closing speed < 25 m/s; the game's own non-fatal push runs | OFF (real-XBE census, mutants) |
| EVENT_SOUND | level 0..4 only (the game's ladder 1.0 .. 1.414 x); no sound played by the host | OFF |
| Camera adjust / finish poses (camera 2) | roll <= 0.35 rad, pitch / yaw <= 0.17 rad, offset <= 2 m; ONE finish pose a race within 40 m of the end-of-race camera | OFF; RT accepted (effect not judged in stills) |
| HUD draw list (hud 2) | 64 commands a plugin, 256 a picture, 1024 text glyphs a picture; sprites use the `[bmashup.textures]` limits (256 entries a mod, 768 entries / 12 MiB in all); 64 KiB high-zone block; no `[bmashup.hud]` table | OFF; RT quads / text; RT sprite (P8 `[bmashup.textures]` pictures) |
| Paints (paints 1) | player 0, BODY in races, <= 30 changes a second, 2 x 0x440 B palette units in the high zone | OFF (41 checks, 8 mutants); RT (blue -> gold in a race) |
| Menu (menu 1) | <= 8 popups, <= 4 mode rows (lists stay <= 10 rows), <= 2 bars; texts 16 KiB in the high zone | declarations OFF; RT popup + mode row; **stat bars UNAVAILABLE** (bars site off) |
| Rules (rules 1) | eliminate <= 1 a second, never the human, never twice; one-player only | OFF; RT (claimed Eliminator race ran) |
| Build option `BO3_HOOKREQ_P23=OFF` | no phase 2 / 3 mark in the game code (the generated code = the merged 0.1.8 + memory build), every function UNAVAILABLE | OFF (COFF audit) |

## 0e. Platform 0.1.8 (mainline host main18) - mod limits + hook request phase 1
main18 = capmega1 + the limits below + nine phase-1 items of the external hook request (`docs\services\README.md`). Everything
else is capmega1's (the marathon stays out of scope; the 64 MB guest window note in 0d / CAPACITY.md is unchanged: no limit
below adds a guest allocation per mod).

| Limit | capmega1 (0.1.7) | main18 (0.1.8) | Engine ceiling | Status |
|---|---|---|---|---|
| Installed mods | 64 | **256** | none (host memory only) | OFF: 64 / 65 / 256 / 257 (loader, bmpack 1.4.0 validate); RT: pending (acceptance with > 64 mods) |
| Mod folders | 8 (`BMASHUP_MODS`) | **256** (`BMASHUP_MODS` + `BMASHUP_MODS_FILE`) | one environment value: 32,767 characters (Windows) - the list file has no total limit (1 MiB file) | OFF: 8 / 9 / 256 / 257 both ways; 256 folders of 216 characters (55,552) through the file |
| Mods with `[bmashup.textures]` | 16 | **64** | the 12 MiB / 768-entry texture pool (unchanged; it bounds the textures, not the mods) | OFF (admission) |
| Music mods (soundtracks) | 16 | **64** | 100 soundtracks in the ST.DB the title's soundtrack library reads; 256 tracks in all (unchanged) | OFF: 64 accepted / 65th refused by the admission |
| Switched-off ids (mod list) | 256 | **1024** (file up to 69,760 bytes) | - | OFF: 1024 saved and read back, 1025th refused |
| Plugin approvals | 256 | **448** (64 KiB file) | - | OFF (sizes) |
| Capacity request slots (engine / streaming) | 64 | **256** | requests merge as a maximum | OFF |
| Plugin settings | 6 a plugin / 32 in all | **8 / 128** (file 512 entries) | - | OFF |
| bmashup.patch patches | 64 | **256** | - | OFF |
| bmashup.hooks points | 6 | **7** (CRASH_RESULT) | - | OFF |

- **Loose files of a mod folder are listed at the start** (as a mod's files always were): a lookup searches lists, not the disk
  (measured: a miss across 256 folders 4.9 us, 0 disk walks). A file added to a loose folder while the game runs is seen at the
  next start. A folder with more than 4,096 files or folders deeper than 8 is walked for every lookup, as before (logged).
- **`BMASHUP_MODS_FILE=<file>`**: one folder per line, after `BMASHUP_MODS`'s folders, in order (the first folder named wins).
  Blank lines and lines starting with `#` are skipped; a trailing CR and trailing spaces / tabs are dropped; a line of 260
  characters or more is skipped (logged); a file with a NUL byte or over 1 MiB is not read (logged).
- **Build option `BO3_MOD_LIMITS=legacy`** (CMake) restores every capmega1 value above (mods 64, folders 8, off ids 256, texture /
  music mods 16, approvals 256, request slots 64); the unmodified capmega1 mod-folder test passes on it (1369 / 0 / 3).

| Hook request phase 1 | Service | Status |
|---|---|---|
| Detach-parts tables (values 0 / 1, process-wide; Road Rage) | bmashup.patch 2 (`PATCH_V2.md`) | OFF (real XBE census); in-game effect NT |
| Place, laps, race time, order, session | bmashup.racers 2 (`RACERS_V2.md`) | OFF; rivals PARTIAL; mode / context UNKNOWN |
| Boost award of an amount | bmashup.boost 2 (`BOOST_V2.md`) | OFF; CHANGES GAMEPLAY; player 0 only |
| HUD element transforms | bmashup.hud 1 NEW (`HUD.md`) | OFF (real draw routine); 4 of 9 elements served |
| Per-player settings | bmashup.settings 2 (`SETTINGS_V2.md`) | OFF; pause-menu entry NOT added (7th slot not free in every mode) |
| Read-only pad | bmashup.input 1 NEW (`INPUT.md`) | OFF |
| Handling values outside a race | bmashup.vphysics 2 (`VPHYSICS_V2.md`) | OFF (6,400 values = the retail data) |
| Traffic density up to 3.0 | bmashup.traffic 2 (`TRAFFIC_V2.md`) | OFF; > 2.0 EXPERIMENTAL until the measuring launch |
| CRASH_RESULT hook point | bmashup.hooks 2 (`HOOKS_V2.md`) | OFF |

Runtime (both pending at the time of writing): one acceptance launch with every example plugin and > 64 mods, and one traffic
3.0 measuring launch. Split screen stays NT platform-wide (player 1 answers UNSUPPORTED in the new per-player calls).

</content>
## 0d. Platform 0.1.7 (mainline host capmega1) - marathon-class tracks
capmega1 = capfix1 + the mesh row extension (BMRX) + the GAMEDATA slot expansion (`docs\services\CAPACITY.md`). The two features
are the code that ran the USA Marathon on the experimental host mega1 (same `bm_rowx.c` / `bm_gdslot.c` bytes, same 11 marks);
capmega1 adds them to the reference host without changing anything else (COFF audit: 27 / 28 generated objects identical, only the
5 row-reading draw functions differ).

| Behaviour | Bounds | Status (experimental host mega1) | Status (mainline capmega1) |
|---|---|---|---|
| `[bmashup.capacity] gamedata_bytes` (GAMEDATA slot) | page multiple 0x177000..0x800000; largest wins | RT 0x200000 (gp_mega_3..6) | OFF on capmega1 (20 checks + 3 mutants, bmpack ACCEPTED); the marathon launch on capmega1 (cm1_acc_1) expanded the slot (`[GAMEDATA] slot EXPANDED ... 0x200000`) and then faulted at boot: 64 MB window exhausted (see below) |
| Mesh material rows above 83 per unit (BMRX) | up to 127 virtual rows | RT (gp_mega_1..6: 189 units, 63 with extension rows) | OFF on capmega1 (1,134,260 checks + mutant; same `bm_rowx.c` bytes and the same 11 marks as mega1) |
| Marathon-class track (USA Marathon 0.2.4: 25.5 km, 189 units, 76 lanes, STATIC 0x1499000, Gamedata 0x200000) | - | RT full loop (gp_mega_4 / 5 / 6) | not run to the track on capmega1: out of the 0.4.4 scope (owner 2026-10-28); cm1_acc_1 (with the 16 example plugins) faulted at boot, window exhausted |
| Traffic over a whole marathon-class loop | per area | RT gp_mega_6 (mean active 10-21 per area) | NT on capmega1 |
| Capacity requests of several mods (largest wins) | per key | OFF | RT cm1_acc_1 (log: lanes 128, STATIC 0x1499000, GAMEDATA 0x200000, low-detail 0x1A000 granted) - then the 64 MB budget was exceeded |
| U5 stale lane data after an expanded -> other track switch | - | OPEN | **OPEN** (unchanged; not observed, not accepted) |
| Release acceptance on capmega1 (16 example plugins incl. capacity + demo mods, no marathon) | - | - | **RT cm1_acc_2**: 25 admitted / 0 refused, 16 / 16 running, capacity lanes 80 / low 0x1A000 / STATIC 0xD01000 granted, race on MY FIRST TRACK finished (1st / 6, 30.8 s, autopilot), FATAL / fault 0, window peak 53,268 KB |

**64 MB guest window (FACT, `[CONTIG]` lines):** every expansion is a new region in the game's 64 MB contiguous window and the game's own pool stays reserved. The marathon alone ran with 61,220 KB in use (gp_mega_6, mega1e); with the capacity example's low-detail slots on top (+1,872 KB) 63,060 KB were in use and the game's next allocations were refused -> fault at boot (cm1_acc_1). Marathon-class tracks and a low-detail (or other) expansion do not fit together: `docs\services\CAPACITY.md`.

## 0c. Platform 0.1.6 - the content phase
| Behaviour | Status (individual) | Status (combined p4.3 / final) |
|---|---|---|
| Added front-end textures (`[bmashup.textures]`), own garage photos | RT fetex1 (gp_fetex1_2) | **RT p4.3** (gp_p43_2, gp_p43_5) |
| Own 4th-region map art / marker / texts (`[bmashup.wt_map_art]`) | RT fetex1 | **RT p4.3** (gp_p43_2); region-page globe / counters still borrowed |
| New series with names, unlock rules, AI rivals | RT veh1 (Neon, Dust, 46 fixture series) | **RT p4.3** (BM COUPES, AI BMCOC02 / 04) |
| 1024-entry vehicle list | RT veh1 (entry 1023 raced) | 633 / 640 with the 512 fixture as ONE mod (gp_p43_5) |
| Paint registry (ramp / file), sidecar persistence | RT veh1 (ramp; file paints OFF) | **RT p4.3** (crimson / gold; saved paint restored gp_p43_4) |
| Registered paints recolour the own garage photo | RT p4.3 fix 1 slice (gp_vfix_1) | **RT p4.4** (gp_p44_1: crimson / gold recolour the BM Coupe photo; registered retail-car paints too; `file` paint = palette 0); fix 2 (list photo cap) offline only |
| Authored car geometry (carimport) | RT p4.2 (gp_carimp_2 / 3: raced, crashed) | **RT p4.3** (the coupe in BM COUPES, gp_p43_5) |
| Authored track geometry (trackbuild) | RT p4.2 (gp_trk_1..7, 0.1.6 canyon) | **RT p4.3** with 0.1.3 (Test Loop, added car, gp_p43_5) |
| mod.toml 64 KiB | OFF (65,536 / 65,537) | RT 22,785 B (gp_p43_5) |
| Removal / reinstall of all content | RT veh1 R3 / R4 | **RT p4.3** (gp_p43_3 / 4) |
| Legacy plugins + the p4.2-era sets | - | **RT p4.3** (gp_p43_3) |
Not tried at runtime: the 917-car tier (one mod or the two-mod split), a texture allocation failure, a language switch; fix 2's
visible effect (offline only); off-track reset INC; AI start delay INC. Known limit: two visible rows sharing one photo show the last
row's paint.

## 0a. Platform 0.1.5 (p4.2) and the runs since kit 0.3.0
| Behaviour | Bounds | Status |
|---|---|---|
| **Added car** (`[bmashup.cars]` 1) | <= 128 vehicle entries, <= 20 cars per series, model <= 0x9D800 | **RT p4.2** (gp_p42_1 listed / raced / finished + saved; gp_p42_2 removed; gp_p42_3 reinstalled; saves hold no added ID) and cars2 build (gp_cars2_1 / 2); `physics_scale` OFF |
| **4th World Tour region** (`[bmashup.world_tour]` 1) | one region, one location, <= 6 events | **RT p4.2** (gp_p42_7: Oceania Night raced, silver medal in the sidecar; gp_p42_8: Oceania Sprint with the added car, silver) and wt4 build (gp_wt4_1 / 4 / 5 / 2); **borrowed USA assets** (labelled, phase 1); region-page "lost presses" = retail hold-to-repeat (a press > 0.25 s steps twice; gp_wt4_6): documented behaviour, script presses <= 100 ms |
| Top-speed limit ("Max Speed In Boost" scale) | 0.5..2, player 1 | **RT p4.1** (gp_p41g_2: x0.5 = 80 mph with and without boost) |
| Traffic density 2.0; traffic 0.0 after a race exit | 0..2 | **RT p4.1** (gp_p41g_1) / **RT p4.2** (gp_p42_4) |
| AI pace 0.5 / 1.5; 0.7 after a race exit | 0.5..1.5 | **RT p4.1** (gp_p41g_1) / **RT p4.2** (gp_p42_4) |
| Autopilot engage after a RACE_EXIT, release | - | **RT p4.2** (gp_p42_4) |
| Crash result | - | **RT p4.1** (gp_p41g_2); not run on p4.2 |
| Signed AI tuning value / start delay | 16 x bound | signed **RT p4.1**; start delay **INC** (gp_p41g_1) |
| MOD SETTINGS paint + FOV 130 %, deps page texts (`MIN`), music pack, legacy plugins (p3-era telemetry, kit 0.2.1 events observer) | - | **RT p4.2** (gp_p42_5) |
| Two-player / split screen, 16:9 / ultrawide FOV, AI aggression behaviour, added Crash events, U5 | - | **OPEN / NT** (COMPATIBILITY.md s0) |

Limits that belong to the new tables: an added car has the donor's photo and physics, no in-race name tag, no unlock rule (raced in a World
Tour event: gp_p42_8, Oceania Sprint 2nd / silver); the 4th region borrows the map's art, place name, ticker, globe and counters and holds one
location; its region page repeats held directions once per 0.25 s spin (retail behaviour). Every run: retail tracks plus the placeholder OC_C1_V1, one machine (Windows 11,
AMD RX 9070 XT).

## 0b. Platform 0.1.2 - 0.1.4 (kit 0.3.0 text: statuses as of the p4 / p4.1 / slice runs; later runs in 0a)
| Behaviour | Bounds | Status |
|---|---|---|
| **Autopilot every race** (`bmashup.autopilot` 2 `engage2`, ONCE_PER_RACE bound to the race) | one takeover a race; game thread | **RT p4** (gp_p4_1: races 1 + 2; gp_p4c_1 / 2: every RESTART) and **RT p4.1** (gp_p41_2) |
| **Autopilot release** (the title's hand-back) | only while this service holds the car, racing, not paused | **RT p4.1** (gp_p41_2: released at 8 s, both races) |
| **Per-car physics query** (`bmashup.vphysics` 1, 64 values, every racer) | read only | **RT p4.1** (gp_p41_2, 6 / 6 racers) and slice build (gp_phys1_3) |
| **Player 1 Drag Coef scale** | 0.25..4, player 1 only, restored at race exit / reset | **RT p4.1** (gp_p41_2) and slice (gp_phys1_2: +5.66 m/s 7-17 s) |
| Player 1 Max Speed In Boost scale | 0.5..2 | Offline-validated |
| **Traffic density** (`bmashup.traffic` 1) | 0.0..2.0 at the traffic set-up; one owner | **RT p4** 0.0 / 0.5 / 1.0 (gp_p4c_1: mean active 0.00 / 4.58 vs 11.12); 2.0 offline; p4.1 offline |
| Traffic query | read only | RT p4 (gp_p4_1, gp_p4c_1) |
| **AI rival pace** (`bmashup.ai` 1) | 0.5..1.5, rivals only, every AI update; one owner | **RT p4** 0.7 / 1.3 (gp_p4c_2: rival speed -9.9 % / +12.0 %); bounds offline; p4.1 offline |
| AI per-racer query | read only | RT p4 (gp_p4_1) and p4.1 (gp_p41_2 / 3 probe) |
| **AI ValueDB values as data** (`[bmashup.tune] version = 2`, `bmashup.tune` 3) | 158 entries (73 AI), signed bounds 16 x | **RT p4.1** for Top speed 40 (gp_p41_2 vs gp_p41_3: caps 40 vs 52.4..88) and slice (gp_aitune1_1); signed / start delay offline |
| **Crash results** (`bmashup.events` 6 CRASH_RESULT, `bmashup.crash` 1) | read only; once per attempt | **RT crash1 slice build** (gp_crash1_1: scores = Crash Results screen); p4 bind only; p4.1 offline |
| **Plugin settings on MODS > MOD SETTINGS** (`bmashup.settings` 1) | BOOL / INT / ENUM; 6 per plugin, 32 in all | **RT p4.1** (gp_p41_2: host + plugin groups), p4 (gp_p4c_1), slice (gp_camset1_r1); restart persistence offline |
| **Camera FOV scale** (`bmashup.camera` 1) | 70..140 %, one-player stages, from the next set-up | **RT p4** 130 % (gp_p4c_1, frames k 1.30) and slice (gp_camset1_r1); 4:3 only; 16:9 offline; split screen not scaled |
| **Mod dependencies** (`[bmashup] requires_mods`, dependency order, NEEDS MOD) | 16 entries, `>=` only | **RT p4** (gp_p4c_1) and slice (deps1_1); p4.1 page texts offline |
| **Music packs** (`[bmashup.music] version 1`, EA GAMES TRAX banner) | 16 soundtracks, 256 tracks, 64 MiB / file | **RT p4.1** (gp_p41_2: banner shots, audio 440 / 523 Hz, host cache) and slice (gp_music1_3); wav only at runtime |
| **Garage paints 7 / 8** (host setting GARAGE PAINT 7-8, default OFF) | <= the car's palettes, <= 8 | **RT p4.1** (gp_p41_2: paint 8 blue / 7 red) |
| Gameplay label `CHANGES GAMEPLAY: AI` | - | log RT p4.1; page text offline |
| Service registry 32, 20 offered = the platform table | - | RT p4 / p4.1 boot lines |

Limits that belong to the new services: the hooks sink gets no CRASH_RESULT; traffic has no mod.toml declaration; vphysics
controls player 1 only; music mods have no Mods-page label; the MODS page counts the host settings group as a mod
(`SETTINGS OF 2 MODS WITH CODE`, cosmetic). Every run: retail tracks, one machine (Windows 11, AMD RX 9070 XT).

# Inherited from kit 0.2.1 (statuses on host p3 or earlier hosts, as named)

## 1. Content limits (data-only mods: `mod.toml` + files, no code)

| What | Limit | Status |
|---|---|---|
| Tracks in the game's track list | 383 entries in total (36 retail, so up to 347 added) | 86 entries runtime-validated (candidate 2); 383 offline-validated |
| Tracks per region in Single Event | 383 + Random (retail: 19 + Random) | 27 rows runtime-validated (candidate 2) |
| Added main regions | 23 (one letter each; every letter except U / E / A) | 10 runtime-validated (candidate 2); 23 offline-validated |
| Named added tracks | 383 (track name up to 27 characters, location up to 17) | 50 runtime-validated (earlier host) |
| Added World Tour events | 35 in total; each location's event list shows at most 6 rows, so each location holds 6 minus its retail events | 2 at one location runtime-validated on p3 (bmp_p3_1), 3 on p1 (launch 51); 35 offline-validated |
| **Event row name** (`[bmashup.extra_events] version 2` `names`) | 1..19 characters, `A-Z a-z 0-9 space - ' . &` (19 = the longest retail text of that list row) | **runtime-validated (p3)**: "Harbour Night" / "Harbour Sprint" listed at Silver Lake (bmp_p3_1); limits offline-validated; that a full 19-character name draws completely is a hypothesis (the widget stores a pointer, same font) |
| **Event help text** (`help`) | 1..97 characters, the same set plus `!`; shown in UPPER CASE like the game's own help texts (97 = the longest retail help-bar text) | **runtime-validated (p3)**: each row showed its own help text (49 characters each) in bmp_p3_1; 97 offline-validated, its full drawing a hypothesis |
| Defaults without names / help | row = the track's name; help = `AN EVENT ADDED BY A MOD.` | row default runtime-validated (p1, launch 51: the track's name); on p3 offline-validated (bmpack 1.2 resolves the p2 content set to "Harbour Lights" + the generic help); the generic help was not seen in a launch |
| Race-result progress for added tracks / events | one record per track and per event, in a separate `.bmprog` file per profile | runtime-validated (p1, launches 51 / 52; sidecar code unchanged in p3) |
| Lanes per track | 64 retail + an extension up to 255 (requested by a plugin or declared) | 80 lanes runtime-validated (candidate 2 / p1); p3 changed only the lanes log (a new counter) |
| Track static data pool (STATIC) | larger pool on request (single view) | runtime-validated in single view (lineage); split screen not tested |

Design ceilings: 383 track entries is the ceiling of the current host; going beyond needs a new host build. The World Tour
map itself has exactly 3 regions: added regions appear in Single Event only.

## 2. Supported gameplay behaviours

### Content
- **Added tracks in Single Event**: listed in their region with their own name; raced to the result; Random in a region picks
  only valid entries. *Runtime-validated (p1, launches 51-54).*
- **Regions that exist only through added tracks**: listed. *Runtime-validated (p1).*
- **Added main regions** (`[bmashup.regions]`): shown in the region row, their tracks raced, Random works.
  *Runtime-validated (candidate 2 / p1).* The region announcer (radio DJ) uses a retail bank as a placeholder and has
  never been heard in testing.
- **Added World Tour events** (`[bmashup.extra_events]`): listed at their location, selected, loaded, raced, medal shown on
  the list, kept across restarts; removing the mod restores the original list and keeps the record; reinstalling finds it
  again. *Runtime-validated on p1 (launches 45 / 46 / 51 / 52).* On p3 (which reads the World Tour declarations earlier, at
  the names load, P-11): the rows and their help texts were seen (bmp_p3_1); a p3 race of an added event was not run.
  A medal improving on replay is offline-validated only.
- **Distinct row names and help texts per event** (version 2): two events on the same track now show their own names and
  help texts. *Runtime-validated (p3, bmp_p3_1).* On p2 such a mod is refused alone (it needs platform 0.1.1).
- **Your game save is not written for added content**: race results, medals and attempts of added tracks / events go to
  the `.bmprog` sidecar. Retail event and track records in the save stay unchanged. *Runtime-validated (p1, launch 51).*
  (Back up your saves anyway.)

### Native plugins (code; each needs approval by its exact SHA-256)
- **Gameplay events** (`bmashup.events` v5): race exit, takedowns (AI-on-AI included), wrecks, boost awards; plugins built
  for older versions (v2-v4) keep working. *Runtime-validated (earlier hosts: p1 launch 51, bmp_demo_1).*
- **Boost-award modifiers**: change the boost the game awards (0 to 16 times the game's request; the game's own factors
  and bar cap still apply), in a fixed order. *Runtime-validated (p1).*
- **Hooks** (`bmashup.hooks` v1): six published points; fixed order; exclusive owners; a second claimant is refused and
  the owner is named. *Runtime-validated (earlier hosts: p1 launch 51, p2 launch 55, the demo launch bmp_demo_1: TAKEDOWN fired 4 / 4).*
- **Patches** (`bmashup.patch` v1): byte changes to read-only game data, only after checks of the game build signature and
  the expected original bytes; overlapping patches from two plugins are refused. *Runtime-validated (earlier hosts: applied in p1 launch 51 / p2 launch 55; the in-game effect as predicted in bmp_demo_1).*
- **Names** (`bmashup.memory`, `bmashup.names`): a plugin can name an added track; a name declared in a mod wins.
  *Runtime-validated (earlier host).*
- **Tuning** (`bmashup.tune`): change game tunables within bounds; also declarable in `mod.toml`. *Declaration path
  runtime-validated (p3, bmp_p3_2: two values set).*
- **Read-only racer queries** (`bmashup.racers`). *Offline-validated.*
- **Host identity** (`bmashup.host` v1): platform version, build identity, game signature, the service list; an optional
  export tells a plugin when all services were offered. *Runtime-validated on p2 (launch 55) and at start-up on p3
  (bmp_kit2_1).*
- **Plugins on p3: start-up runtime-validated, gameplay not tested.** In bmp_kit2_1 (a boot-only smoke launch to the front
  end, no race) the kit's 6 SDK 0.3.0 plugins were approved per sha256, loaded and bound their services; host-info matched
  the reference identity; the hooks rival was refused with CONFLICT; the patch demo was applied. No race ran, so event and
  hook dispatch, the BOOST_AWARD modifier effect and race-exit summaries are runtime-validated only on earlier hosts
  (p1 / p2), not on p3. SDK 0.2.0 plugins bind through the p3 loader offline (MIGRATION.md).

Plugins can only use what the host publishes: there are no arbitrary-address code hooks (the game is statically
recompiled). A new hook point needs a new host build.

## 3. Installation behaviour
- **Install the host once, then add or remove packs and plugins without rebuilding anything.** *Runtime-validated (p1 / p2).*
- **A mod that needs a newer platform, a newer table version, or has a misspelt key is refused alone**, with its reason,
  and the game starts without it. *Runtime-validated (p1, launches 53 / 54); the same gate in p3 with platform 0.1.1.*
- **Two mods that clash** (the same track id / name / location, region letter with another text, World Tour event key, a
  location's 6 rows overfilled, the track list's capacity, the same tuning value): **the LATER mod is refused alone,
  before any of its declarations is used; the log names BOTH mods and their folders; the earlier mod and the others are
  unaffected; the game starts.** "Later" = `BMASHUP_MODS` folder order, then mod id. A mod that needs content only the
  refused mod declares is refused with it. *Runtime-validated (p3, bmp_p3_2: a track id / name / location clash)*:
  `[ADMIT] mod bmashup.bmp-p3-late 1.0.0 (<folder>) refused, the game starts without it: track id US_C8_V1: already added by
  mod bmashup.bmp-p3-early 1.0.0 (<folder>); ...`, then `[MOD] mod ignored (conflict with bmashup.bmp-p3-early: track id
  US_C8_V1): <folder>`; the Mods page shows `CONFLICT` with the reason. The other clash kinds and the "state with the
  refused mod = state without it" proof: *offline-validated*.
- **What still stops the start**: a mod's OWN invalid table (exit 91 capacity, 92 tracks / regions / names / events, 93 tune
  - the author's error, deliberately unchanged), a guest-dependent check at launch (92 / 95 / 96), host integrity / out of
  memory (92), and the host guards 88 / 89 / 90 / 94 / 97. Exit codes: 88 track route data too large, 89 unit slots, 90
  STATIC truncation, 91 capacity declaration, 92 content declaration / host out of memory, 93 tune, 94 added track in an
  unsupported mode, 95 / 96 World Tour launch / data, 97 more lanes than the capacity.
- **Clashes between plugins** (runtime registrations, e.g. two plugins naming one track) are not part of the admission: the
  service answers the second plugin with its CONFLICT code, as before.
- **Duplicate mod ids**: both copies are refused (offline-validated).
- **Data mods that change gameplay values are labelled**: a mod with `[bmashup.tune]` (scoring / boost values, up to 16 x) or
  `[bmashup.capacity]` (lanes, low-detail slot, STATIC pool) gets a log line `[MODS] <mod> <ver> changes gameplay: boost
  (Trading Paint Boost value (Boost units) 3 -> 6), scoring (Takedown BP 1000 -> 2000), capacity (AI route lanes 80)` plus
  `[MODS] N data mod(s) change(s) gameplay values (informational: no approval is asked; native code approval is separate,
  per sha256)`, and the Mods page shows `CHANGES GAMEPLAY: BOOST, SCORING, CAPACITY` for it. No prompt, no acknowledgement,
  nothing stored; a refused mod gets no label. *Runtime-validated (p3, bmp_p3_2: log + Mods page).* Adding tracks / regions
  / events is not labelled (it changes no existing value).

## 4. Not tested or not supported
- Split screen (two players), online / system link: **not tested**.
- Career / World Tour progression beyond the tested events; the World Tour map with a 4th region: **not supported**.
- More than 20 World Tour events in one game data element at runtime (35 offline-validated); a medal improving on replay
  (offline only); the region announcer (never heard).
- Linux, macOS: **not built**. Windows 10: not tested (tested on Windows 11 build 26300). One GPU tested (AMD RX 9070 XT).
- Another machine: the host was staged and run on the development machine only.
- **U5 (open):** whether any game code reads stale lane data after switching from an expanded track to another track. The
  lane-lifetime protection kept the old data valid in every test. p3 adds a counter for it (`[LANES] lane lifetime at LOADED
  ...; served from retained snapshots N`, a race-exit line and a process-exit summary) - the counter is PRESENT but has NOT
  been observed in a launch with an expanded -> distinct track transition; its presence is not U5 acceptance. U5 stays OPEN.

See `COMPATIBILITY.md` (p4.1 gaps: its section 0) for the full matrix and `ROADMAP.md` for what comes next.
