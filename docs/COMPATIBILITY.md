# Compatibility and coverage limits - reference host main21 (EXPERIMENTAL Windows x64 mod kit 0.7.0)

**Kit 0.6.0 reference host: the MAINLINE host main21** `burnout3_gp_main21.exe` (you build it as `burnout3_bmashup.exe`),
sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`, identity `bmp-0.1.9+2c8142e65f20`, **platform 0.1.9** = main18 + mem256 (the 256 MB guest window) + hook request phases 2 and 3, 25 services. Release acceptance: one exclusive race with 137 mods and 38 plugins finished first with no fault (`docs\CHANGELOG.md`, which also lists the two limited items: stat bars UNAVAILABLE, indicator blink not visually confirmed). U5 stays OPEN. (The paragraphs below were written for capfix1 / p4.4 and name the host as it was then.)


**Kit 0.4.3 reference host (previous): capfix1 `burnout3_gp_capfix1.exe`, sha256 `a7aea02d5a72a7820cd5649bbd9a01ee23271f89d358890042821092faf3b601`, build identity `bmp-0.1.6+0c5a321ae0fa`**, platform 0.1.6, 20 services. capfix1 = clean1 (p4.4 + one build option: the toolkit's build-machine shader path is not compiled in) + the chevron set-index guard (one mark in the chevron draw + `bm_chevron.c`; defect T1). Every other platform source file and 27 of the 28 generated-code objects equal p4.4's, so the p4.4 evidence below applies. Guarded launches on clean1 (lic_portable_1, the RC onboarding) and on capfix1 (capdbg_3, the RC acceptance launch) are listed in the release-candidate report, not in this kit.

Previous reference host (kit 0.4.0 / 0.4.1), whose evidence this page cites: **`burnout3_gp_p4_4.exe`** sha256 `fa63df57dde6b522e77ba0330f0c83ee76ae483cac84f9d58bd9d5a479ce3825`, identity **`bmp-0.1.6+ab3a98869d10`**, platform **0.1.6** (p4.3 = p4.2 + fetex1 +
veh1 + M1-M8; the final candidate p4.4 = p4.3 + fix 1 (the garage photo follows registered paints) + fix 2 (the list-photo cap is
bounded by the photo palettes)). FINAL content-phase candidate (p4.4 = p4.3 + fix 1 + fix 2; integration report gp\integration\p4_4\P4_4_REPORT.md); a candidate, not a freeze Combined-host evidence: gp_p43_2
(World Tour with fetex art + wt4 + cars), gp_p43_3 (removal + p4.2-era sets), gp_p43_4 (reinstall), gp_p43_5 (authored coupe in a new
series, the 512 fixture, trackbuild 0.1.3 Test Loop); final focused run: gp_p44_1 (RUNTIME-VALIDATED: fix 1; fix 2 offline; BM Test Loop 0.1.3 raced with the crimson authored coupe, 3rd; FATAL 0; UDATA 0 added IDs).

**Windows x64 only; Linux / macOS NOT BUILT.** A retail / upstream Takedawn exe ignores `[bmashup.*]`: NOT SUPPORTED.

## 0. The explicit gaps (summary)
| gap | status |
|---|---|
| **U5** stale lane-pointer use across tracks (now also: larger registries / asset reloads keep their pointers; no free-before-proof) | **OPEN** |
| widescreen 16:9 / ultrawide FOV; split screen (incl. its camera); online / system link | **NT** |
| AI aggression behaviour; added Crash events (H2-H6) | **OPEN** |
| Revenge imports (White Mountain, Motor City) on p4.x | **NT** (ran only on frozen p3); **White Mountain cloud fix NOT resolved** (runtime-unverified); Motor City watch items not examined |
| trackbuild: off-track reset | **INC** (exit not reached) |
| trackbuild: donor Gamedata header / event records, sky (enviro), audio | **DONOR** (labelled; not authored) |
| carimport: donor collision hull, wheels, engine audio, physics, crush basis | **DONOR** (labelled; not authored) |
| AI start-delay value | **INC** |
| 4th region: region-page globe view and counters | **BORROWED** (labelled); the map art / marker / texts are now authored |
| the 917-car tier (as ONE mod, and as vehtool 0.1.1's two-mod split); a texture-pool allocation failure; a language switch | **NT** (offline only) |
| fix 2 (list-photo cap) visible effect | **OFF only**: needs a car whose palettes 6 / 7 differ visibly from 0 / 1 |
| two visible garage rows sharing ONE photo texture with different registered paints | known limit (fix 1): both show the last row's paint |
| the kit's own built modules in the game | **NT** |
| another machine / GPU; Windows 10 | **NT** |

## Kit 0.3.1's matrices (host p4.2 and earlier, unchanged text)
## (kit 0.3.1) The explicit gaps on p4.2
| gap | status |
|---|---|
| **U5** stale lane-pointer use across tracks | **OPEN** |
| World Tour region page "lost presses" | **documented retail behaviour, not a defect**: held directions repeat once per 0.25 s globe spin (gp_wt4_6, WT4_NAV_REPORT); script presses <= 100 ms |
| **4th region borrowed USA assets** (art, place name, ticker, globe, counters) | **labelled limitation** (phase 1); OPEN hypothesis: the OCEANIA map reads "0/2" after a silver (gp_p42_8; 1/2 after a gold in gp_wt4_5) - probably the borrowed USA counters |
| **Imported Revenge tracks (White Mountain, Motor City) on p4.x** | **NT** - the Revenge sets ran only on frozen p3 (rev_1b); the White Mountain cloud fix is runtime-UNVERIFIED (not resolved); Motor City watch items not examined (both owner-deferred) |
| widescreen 16:9 / ultrawide FOV; split screen (incl. its camera); online / system link | **NT** (FOV 16:9 OFF only; split-screen FOV not scaled by design) |
| AI aggression behaviour (attack state machine); added Crash events (H2-H6) | **OPEN** (discovered only) |
| AI start-delay value | **INC** (read back, effect unobserved) |
| hooks sink CRASH_RESULT | **NS** (needs hooks v2) |
| `bmpack validate` of a `[bmashup.world_tour]` mod | **tool limitation**: falsely refused (checker lacks the declared location); the host accepts it (gp_p42_7) |
| plugin settings read back after a restart; music mp3 / flac / ogg | **OFF only** |
| an added car raced in World Tour | **RT p4.2 gp_p42_8**: cars2 + wt4 loaded together; COMPACT MASHUP offered last in the World Tour garage, raced Oceania Sprint to 2nd / silver; sidecar holds the track + event records (no car record); retail save 0 added IDs |
| `physics_scale`; several added cars / series | OFF / NT |
| another machine / GPU; Windows 10 | **NT** |
| the kit's OWN built modules in the game | **NT** (the runs used modules from the same sources built in the workspace; kit 0.2.1's prebuilt events observer ran on p4.2) |

## Kit 0.3.0's matrices (host p4.1 and earlier, unchanged text)
## Inherited from kit 0.2.1 (host p3, platform 0.1.1)
The tables below are kit 0.2.1's, unchanged: statuses refer to p3 or earlier hosts (named). p4 / p4.1 carry this code; the
regression suites (25 / 25 on p4 and p4.1) are the only p4.1 evidence for them unless section 0 says otherwise.

## 1. Installation and the platform itself
| feature | status |
|---|---|
| one unchanged host exe across the launches | RT-p3 (bmp_p3_1 / 2: `6f008b21...`) |
| build identity `bmp-0.1.1+b56e33b66dc3` in the boot line | RT-p3 (bmp_p3_2: `[PLATFORM] host: Burnout Mashup platform 0.1.1, build bmp-0.1.1+b56e33b66dc3, game signature D0FC2EF4E9B2A86F`) |
| identity check by a plugin (host-info vs `BMSDK_REFERENCE_BUILD`) | RT-p3 boot (bmp_kit2_1: `= the SDK's reference host`); RT-p2 (55, SDK 0.2.0 vs p2) |
| platform line, 14 services offered, bmashup.host first | RT-p3 (bmp_p3_2: `14 services offered to plugins (bmashup.host first)`) |
| `[bmashup] platform` / table version / typo refusal of ONE mod | RT-p1 (53 / 54); the p3 gate: OFF (gate agreement 39 cases, same texts as bmpack) |
| `[bmashup] requires` / unknown table refusal | OFF |
| **cross-mod clash: the later mod refused alone, both named, the game starts** | **RT-p3 (bmp_p3_2: track id / name / location)**; other kinds OFF (admission 105 / 105, 8 mutants caught; kit admission agreement 8 cases) |
| refused mod = absent (guest image, track list, sidecar byte-identical) | OFF (HOST_P3_REPORT S) |
| gameplay labels (log + Mods page), no prompt | RT-p3 (bmp_p3_2); "nothing stored / no prompt on a second start" OFF (source) |
| duplicate mod ids: both refused | OFF - NT at runtime |
| mod removal, progress kept | RT-p1 (52); RT-p2 (56: removal without rebuild) |
| content mods on a retail / plain Takedawn host | NT (silent no-op by the manifest rule) |
| a platform 0.1.1 mod on p2 refused alone | OFF (the real p2 gate + kit 0.1.0's bmpack: same text) |
| host distribution layout (exe + SDL2.dll + shaders + licences + check_host) | p2 distribution RT-p2 (clean-env runs A / B); the p3 distribution (kit2\host_dist, same layout / imports) - preflight OFF on this machine, NOT launched from the folder |

## 2. Content (declarative)
| feature | SE | WT | SPLIT | ONL | CAR |
|---|---|---|---|---|---|
| file replacement (`files\`, loose) | RT-p1 (51-54) | RT-p1 (51) | NT | NT | n/a |
| added track in a retail region | RT-p1 (51; 54) | NS as a free track (exit 94, OFF); playable as a declared WT event | NT | NS: exit 94 (OFF) | `.bmprog` sidecar (RT-p1 51) |
| track names / locations | RT-p1 (51 / 54) | row text: RT-p3 (bmp_p3_1) | NT | NT | n/a |
| **event row names / help texts** (extra_events v2) | n/a | **RT-p3 (bmp_p3_1: "Harbour Night" / "Harbour Sprint", own help texts)**; limits 19 / 97 OFF | n/a | n/a | n/a |
| declared regions | RT-p1 (51 / 52); RT-c2 (50); 23 OFF; DJ branch NT | NS (map has 3 regions) | NS | NT | codes never saved |
| track list > 128 / list > 19 rows | RT-c2 (50); 383 OFF | n/a | twin / B / C stop at 19 (OFF) | NT | NT |
| World Tour added events (up to 35) | n/a | RT-p1 (51: raced, medal); RT-p3 (bmp_p3_1: listed); > 2 at once NT; 35 OFF | n/a | n/a | sidecar only (RT-p1 51) |
| WT replay improvement | n/a | OFF | n/a | n/a | OFF |
| > 20 events in one PrgData element | n/a | OFF - **NT** | n/a | n/a | NT |
| progress sidecar, per-mod isolation | RT-p1 (51 / 52) | RT-p1 | NT | NT | sidecar only |
| `[bmashup.capacity]` | RT-lin (18; refusal 19); RT-p3 (bmp_p3_2: lanes 80 accepted) | NT | NT | NT | n/a |
| `[bmashup.tune]` | RT-lin (34); RT-p3 (bmp_p3_2: 2 values set, labelled) | NT | NT | NT | NT |

## 3. Engine limits and guards
| feature | SE | WT | SPLIT | ONL |
|---|---|---|---|---|
| lanes > 64 (80) | RT-c2 (50); RT-lin | NT | NT | NT |
| lane lifetime design C | RT-c2 (50); RT-lin (39) | NT | NT | NT |
| **U5 stale lane-pointer use across tracks** | **OPEN** (p3 counter present, not observed) | OPEN | OPEN | OPEN |
| low-detail unit slots / guard 89 | RT-lin (8 / 9) | NT | NS: split keeps 35 x 0x18000, oversize stops 89 | NT |
| STATIC pool / guard 90 | RT-lin (13 / 14) | NT | INC | NT |
| GAMEDATA guard 88 | RT-lin (7); fit RT-c2 (49) | RT-lin (41) | NT | NT |
| lane overflow without capacity (97) | OFF | NT | NT | NT |
| exits 91 / 93 / 94 / 95 / 96 / 97 on p3 | OFF | OFF | NT | NT |

## 4. Plugin services (approved native plugins)
| feature | SE | WT | SPLIT | ONL | CAR |
|---|---|---|---|---|---|
| loader + exact-sha256 approval | RT-p2 (55 / 56); RT-p3 boot (bmp_kit2_1: 6 plugins) | RT-p1 (51) | NT | NT | n/a |
| bmashup.host 1 + end of offers | RT-p2 (55); RT-p3 boot (bmp_kit2_1: 14 / 14) | RT-p1 | NT | NT | n/a |
| SDK 0.2.0 modules (kit 0.1.0) | RT-p2 (55 / 56: host-info, events-observer, boost-modifier, hooks demo / rival, patch); on p3 OFF (binding through the p3 loader, `*_kit010`) | NT | NT | NT | NT |
| SDK 0.3.0 modules (this kit; 6 = SDK 0.2.0 bytes, 2 new) | RT-p3 boot only (bmp_kit2_1: all 6 loaded and bound; hooks registration + CONFLICT; patch applied); gameplay dispatch on p3 NT | NT | NT | NT | NT |
| events v5 observers / BOOST_AWARD modifier | RT-p1 (51) | RT-p1 (51) | car update: player 2 filtered (OFF) | NT | NT |
| hooks v1: registration, EXCLUSIVE CONFLICT, RACE_EXIT | RT-p1 (51); RT-p2 (55) | RT-p1 | NT | NT | n/a |
| hooks v1: TAKEDOWN callback | RT-p2 (bmp_demo_1: 4 / 4, 1:1 with the events service) | NT | NT | NT | n/a |
| hooks v1: BOOST_AWARD MODIFY effect | OFF (test_hk) - NT at runtime | NT | NT | NT | NT |
| patch v1: published site applied / in-game effect | RT-p1 (51) / RT-p2 (bmp_demo_1: intro film as predicted) | RT-p1 | NT | NT | n/a |
| memory v1 + names v1 | RT-c2 (49); RT-lin (35) | RT-c2 | NT | NT | n/a |
| tune v2 / engine v1 / streaming v2 / route v2 / autopilot v1 / boost v1 | RT-lin | NT | streaming v2 INC | NT | NT |
| racers v1 | OFF | NT | NT | NT | n/a |
| plugin-vs-plugin conflicts (service CONFLICT codes; not the admission) | OFF | NT | NT | NT | n/a |
| `on_shutdown` at a normal exit | NT | NT | NT | NT | n/a |

## 5. Kit 0.3.0 coverage (offline)
kit 0.4.0 release check (`stage_verify.py`, developer side) from the zip in a clean folder: sums; no binaries / game data; every SDK example rebuilt = `sdk\EXPECTED_BUILD_SHA256.txt`; the bmpack packs and the music / tune examples = the launched sets byte for byte; the INSTALL walk on the exact p4.1 exe (not run) with bmpack 1.3 validate against the p4.1 tree; two refusal demonstrations (a clash, a missing dependency version). Result: the workspace `gp\kit3\KIT030_REPORT.md`.
