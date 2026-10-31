# Runtime acceptance plan - editor-built tracks (written 2026-10-29, v0.27; NOT executed)

Everything the track editor proves today is **offline**: structural race checks, the kit's trackbuild gates (V2 coverage / walls,
V3 PVS walk, V5 route / grid, V6, V7 traffic, V8 LOD), byte-exact built data and the editor's dry run. Nothing below has been run.
Each run needs the owner present, the runner's token (`--authorize-runtime RUN:sha12`), a fresh disposable root and a new run
folder (PC `CLAUDE.md`; Workbench "Launch -> Stop -> Results (v0.8)"). One bounded run per authorisation.

## Candidate
- The stage-5 loop: `tests\test_trackedit_v27.py` w01 builds it (original rounded-pentagon loop, ~600 m, 17 units, terrain +
  barrier + prefab in the infield, 4 checkpoints at chosen stations) and stages it into its test area. For a runtime run, build it
  again into a NEW project + staging folder outside the test area (same steps through the editor), so the run uses bytes that
  are not deleted with test areas. Record the staged package's file hashes (`package_record`) in the run folder.
- Control: the unchanged demo track project (testloop), whose grid / start pattern is the runtime-validated reference. Run it
  first in the same profile shape if the candidate fails, to separate "editor output" from "profile / host" problems.

## Preparation (offline, no game)
1. Test profile (multi-mod v0.7) with the staged track package on the verified host exe (`build\..._acc`, with SDL2.dll,
   shaders, licences - see the acceptance-exe companions note), approvals file, Prepare -> Preflight -> dry run.
2. Read the launch plan; the owner gives the token. Max wall time set; background tool timeout above max-wall + boot.

## Checks in the run (each: PASS / FAIL / NOT REACHED, with the evidence)
| # | Area | What to do | Evidence | Pass |
|---|---|---|---|---|
| R1 | Load | Select the track slot (EU_T5_V1 id) in a single race | log: package mounted, no FATAL; winshot of the grid | race starts, no crash / hang |
| R2 | Streaming | Drive one full lap at normal speed | log: unit loads / no missing-unit warnings; winshots at 4 points | no pop-in holes, no fall-through at the 17 unit cuts |
| R3 | Driving surface | Drive the whole road edge to edge, incl. the cut lines | winshots, car height | car stays on the road; no bumps at cuts (cut-rounding slivers < 0.00005 m must be invisible) |
| R4 | Collision: walls | Hit the outer and inner walls at an angle and head-on | winshots, log | car is stopped / deflected, never passes through |
| R5 | Collision: scenery | Reach the infield only if the walls allow (they should not); otherwise inspect barrier + prefab visually from the road | winshots | barriers and terrain render; no z-fighting with verges that blocks play |
| R6 | Laps / checkpoints | Complete 2 laps in order; then try to skip a checkpoint (cut the infield is impossible -> drive backwards past one) | HUD lap counter, log | lap counts only in order (start line, 4 checkpoints); backwards does not count |
| R7 | AI | Race with AI opponents, 2 laps | winshots, final positions | AI follow the route, take all corners, finish; no AI stuck at a cut or wall |
| R8 | Respawn / reset | Crash into a wall (takedown / crash cam), and force a reset off the road if possible | winshots, log | car respawns on the route, facing the route direction, inside a unit |
| R9 | Grid / start | Start positions | winshot at the start | 6 grid slots behind the start line, all cars on the road facing forward |
| R10 | Traffic | If the mode spawns traffic | winshots | traffic on the lanes, moving in the route direction |

## Stop rules
- Stop the game once the run is stuck or its evidence is complete (operator stop, reported as such).
- A FATAL / crash: keep the log tail, the winshot and the run folder; no second launch in the same authorisation.

## What a pass would and would not mean
- A pass of R1-R10 on the stage-5 loop is evidence for THAT package on THAT host build. It does not cover other shapes (route
  heights other than flat, which the kit's V2 rule does not support today), other unit counts (kit: 17 for pvs "all") or tracks
  with more geometry per unit (capacity is checked offline only).
- Report facts (what was seen / logged) separately from hypotheses (why something happened).
