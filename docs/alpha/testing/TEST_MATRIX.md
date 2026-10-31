# Alpha test matrix (tester bundle 0.1.1, host platform 0.1.6, kit 0.4.1)

Small and prioritised: P1 = every tester, first session; P2 = when P1 passes; P3 = if you have time / the hardware. Each test:
what to do, what PASS looks like, what to attach (always the diagnostic export `diag.cmd`, never saves / game files / the exe).
Status words for your report: PASS / FAIL / BLOCKED (could not run) / ODD (works but looks wrong).

## A. Installation, GPU and Windows environment
| ID | P | Test | PASS when |
|---|---|---|---|
| A1 | P1 | Unpack to a new folder, `preflight.cmd` before any preparation | it runs; only the game-data line FAILs, with the fix printed |
| A2 | P1 | `prepare.cmd data --copy-from <your installed data>` then `preflight.cmd` | `RESULT PASS`; note every WARN |
| A3 | P2 | `prepare.cmd data --install-from <your disc image or folder>` (instead of A2, in a second unpacked copy) | gamedata holds a checked install; preflight PASS (not exercised by the developers) |
| A4 | P1 | `prepare.cmd demos` | prints OK for coupe / loop / canyon; the coupe "byte-identical to the reference build" |
| A5 | P1 | `play.cmd` first start | game window, `run.log` has `[PLATFORM] ... platform 0.1.6` and 20 services, no FATAL, no refused demo mod |
| A6 | P1 | Your environment | report Windows edition + build, GPU + driver version, display resolution / refresh, pad or keyboard (in the export) |
| A7 | P2 | Windows 10, ARM64, laptop with two GPUs, HDR / high refresh display, non-ASCII or very long folder path | preflight + start work, or a clear message |
| A8 | P2 | Negative paths: no Vulkan 1.3 driver / remove `SDL2.dll` / a PAL `default.xbe` / an extra `vulkan-1.dll` in `host\` | preflight FAILs with an actionable fix; the game never starts silently wrong |
| A9 | P3 | Second machine with the SAME zip | same preflight result (the developers could only test on their own PC) |

## B. Example plugins and mod combinations (developer bundle for the plugins)
| ID | P | Test | PASS when |
|---|---|---|---|
| B1 | P1 | Demo mods only (bundle default) | all admitted; MODS page lists them ON |
| B2 | P2 | + SDK autopilot demo built from kit 0.4.1, approved by hash | `[AUTOPILOT]` engages every race; unapproved module is NOT loaded and the log prints the approval line |
| B3 | P2 | + camera-fov (MOD SETTINGS page), + traffic / AI pace examples | setting saved and applied next race; traffic / rival pace change visibly |
| B4 | P2 | Dependency refusals: remove `bm-veh-neon` but keep `bm-veh-cross` | cross refused with `NEEDS MOD`; everything else starts |
| B5 | P3 | Many mods (40-64) from several folders in `mods\user` | admission order + clashes as bmpack predicts; > 64: preflight FAILs |

## C. Authored cars and tracks
| ID | P | Test | PASS when |
|---|---|---|---|
| C1 | P1 | BM Coupes series: BM Coupe, paints teal..lime, crimson, gold | model + garage photo follow every paint |
| C2 | P1 | Race BM Test Loop with the BM Coupe, 5 AI | race finishes; walls hold; no fall-through |
| C3 | P2 | Race BM Canyon Ring (30 units) | 2 laps, no missing geometry / void pixels |
| C4 | P2 | Crash the coupe hard into a wall on both tracks | crash camera, respawn on the road facing the route |
| C5 | P2 | Make your own car with carimport (IMPORT_CAR.md) and race it | validate passes; car drives; report donor-related oddities |
| C6 | P3 | Make your own small track with trackbuild (BUILD_TRACK.md) | validate passes; loads, laps count |
| C7 | P3 | Leave the track on purpose (off-track reset) | reset back on the track (INCONCLUSIVE so far) |

## D. Removal, re-installation and sidecar persistence
| ID | P | Test | PASS when |
|---|---|---|---|
| D1 | P1 | Choose crimson for the BM Coupe, quit, `play.cmd` again | crimson restored (paint sidecar in `profile\Roaming\Takedawn\bmashup\progress`) |
| D2 | P1 | Turn the BM Coupes series OFF on the MODS page, restart | profile loads; car select falls back to a retail car; no prompt for a new profile |
| D3 | P2 | Turn it back ON, restart | series back, saved paint restored |
| D4 | P2 | `remove.cmd backup`, `remove.cmd clean --yes`, delete the folder; unpack again, restore the backup, prepare | profile + progress back; nothing left outside the folder (check `%APPDATA%\Takedawn` untouched) |
| D5 | P2 | Copy your Takedawn `UDATA` into a bundle profile (a COPY) | profile loads with your progress; the original stays unchanged |

## E. Unsupported or risky workflows (expect problems; report what happens, do not use your real saves)
| ID | P | Test | Expected / known |
|---|---|---|---|
| E1 | P3 | Expanded-lane track (> 64 lanes), then switch track / mode several times | **EXPERIMENTAL (U5)**: may crash or misbehave; report the exact sequence |
| E2 | P3 | Widescreen / ultrawide window, split screen | NOT TESTED with the platform |
| E3 | P3 | Revenge track conversion (trackconv) | not supported in this alpha: do not test |
| E4 | P3 | Pointing play.cmd at your real Takedawn profile (editing the launcher) | not supported: never do this with real saves |

## F. Asset reloads
| ID | P | Test | PASS when |
|---|---|---|---|
| F1 | P1 | Garage -> race -> back to the garage (front end reloaded) x3 | coupe photo, paints, series names still the mod's |
| F2 | P2 | Race on BM Test Loop, quit, race on a retail track, back to BM Test Loop (track reload) | each track loads correctly; no stale geometry / sky |
| F3 | P2 | World Tour region page / map in and out several times (developer bundle's region mod) | map art and texts stay correct; tap, do not hold |

## G. Allocation-failure behaviour
| ID | P | Test | PASS when |
|---|---|---|---|
| G1 | P2 | A texture pack above the limits (fetex: > 12 MiB per mod / > 768 textures / > 512 photos) | refused at packaging or admission with the limit named; the game starts without it |
| G2 | P2 | A mod.toml > 64 KiB; a vehicle list beyond 1024 entries | refused with the limit named |
| G3 | P3 | Low-memory machine (8 GB RAM) with all demos | starts; if not, the exit code (92 = out of memory for content) and message |
| G4 | - | Injected pool / palette allocation failure | NOT possible for testers (needs a host switch that does not exist yet); listed so nobody assumes it was tested |

Not in scope: the 917-car registry tier (not required), Linux / macOS, public sharing of anything.
