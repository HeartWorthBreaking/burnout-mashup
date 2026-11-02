# Track editor - authoring tools (Workbench 0.33, 2026-11-02)

Workbench 0.33 = 0.31 (authoring queue: road design, junctions, terrain, mesh editing, materials, scenery, streaming / LOD /
visibility, viewer overlays, project workflow) + the 0.32 "Open in track editor" button and guide (0.2.0-alpha.2) + the 0.33 queue:
tools organised by task with presets and contextual guide sections, a first-track walkthrough, original starter projects, clickable
problems with how-to-fix text, a one-step Build -> Validate -> Stage -> Prepare test, explicit OBJ compaction, optional backup
retention, chunked overlays (no 60,000-triangle cutoff), a building generator and low-poly trees, a shareable source export, and
verified read-only format research (routes / props / environment, `format_research\FINDINGS.md`). An isolated successor:
`gp\workbench_te` (0.31), `gp\workbench` (0.30), the frozen baselines and the published releases are unchanged. **Every result below is offline**: kit gates (trackbuild 0.3.0 `validate`) and the editor's own checks. Nothing here has
been driven in the game; see "Runtime status".

Start: Workbench -> New track project -> **Open in track editor...**, or `py -3 -B wb_trackedit.py <track project>`. The panel
**Authoring tools** under Construct groups the tools by task (Race layout, Roads, Terrain, Buildings / scenery, Materials, Mesh,
Streaming, Inspect, Project / test); each group has a **Guide** button (the matching guide section) and most tools a **Preset**
list. **First track walkthrough** at the top shows which steps are done and opens the next tool. Every tool: **Preview** (nothing changes) -> **Apply** (with that preview; one undo step). A refusal changes nothing
and says why. `?` in the page shows the shortcuts.

## Capability matrix
Status: IMPLEMENTED = works and is tested offline (suite, kit Stage); PARTIAL = works within a stated limit; BLOCKED = not
possible with the verified format / tools (evidence + next experiment below); RUNTIME = never seen in the game.

| Area | Feature | Status | Tested by |
|---|---|---|---|
| 1 Road | profiled roads: per-point width, bank (smoothstep transitions), monotone elevation, cross-sections, continuity warnings, u 0..1 / continuous v, plane normals | IMPLEMENTED | te31 r03, te41 g01 |
| 1 Road | race route: sloped (needs trackbuild >= 0.3.0), variable width, outer-wall gaps | IMPLEMENTED (STAGED) | te31 r01/r05, te41 |
| 1 Road | race route banking | PARTIAL: limited by kit gate V2 to ~0.27..0.4 deg (width-dependent) | te31 r02 |
| 2 Junctions | T / Y / cross (3..6 arms) level junction pieces, road-end joins (exact corners), overlap refusal, open-end list | IMPLEMENTED | te32, te41 g02 |
| 2 Routing | routing report: route, direction, lanes, starts, checkpoints, traffic, gaps; junctions marked geometric only | IMPLEMENTED | te32 j05 |
| 2 Routing | AI / traffic navigation on side roads or branches | BLOCKED (format: one closed S4 route) | - |
| 3 Terrain | height grid (<= 128 x 128, 4096 cells / block), raise / lower / flatten / smooth / set brushes, radius / strength, one undo per stroke | IMPLEMENTED | te33 |
| 3 Terrain | road-edge blending (terrain moves, the road never; clearance on the generated surface) | IMPLEMENTED | te33 t03, te41 g03 |
| 4 Mesh | vertex / edge / face selection (click-pick), move / turn / scale, axis lock, new-plane normals | IMPLEMENTED | te34 m02 |
| 4 Mesh | triangulate, subdivide (crack refusal), extrude (manifold), delete (route checks), explicit hole fill | IMPLEMENTED | te34 |
| 5 Materials | import ORIGINAL PNG (kit rules, provenance, held until Save), new / duplicate material, UV scale / offset / rotation, vertex-colour painting | IMPLEMENTED | te35, te41 |
| 5 Materials | transparency / blend / shaders / animated materials | BLOCKED (trackbuild materials are opaque DXT1, 4 keys) | te35 x03 |
| 6 Scenery | prefab library (search, generated previews), snapped placement + drop to ground, repeat along a path, collision keep / none (explicit twins), linked-copy refresh | IMPLEMENTED | te36, te41 |
| 6 Scenery | real instances / props | BLOCKED (no instances in trackbuild: copies only) | - |
| 7 Streaming | per-section report (coverage, memory vs slots, polys), LOD preview, LOD / PVS settings, limits classified with evidence | IMPLEMENTED | te37 |
| 7 Streaming | larger mesh / LOD blocks, static.dat, route data, > 64 lanes (RTA5, trackbuild 0.3.4 capacity auto) | IMPLEMENTED offline: up to the host ceilings, declared in mod.toml [bmashup.capacity]; RUNTIME-UNVERIFIED; needs a host with the values (patch 131+ for full_unit_bytes, low > 0x30000, static > 0x20C4000) | cap5, kit test_capacity |
| 8 Viewer | wireframe, stored normals (mismatch red), collision, routes, sections / LOD, clickable diagnostics, approximate-shading label | IMPLEMENTED | te38, te40, te41 screens |
| 8 Viewer | sky / fog / track lighting previews | BLOCKED (enviro.dat: no verified reader) | - |
| 9 Workflow | backups on every Save + verified restore, transactional save, source export / import (manifest), versions, prepare test (plan + package record, no launch), shortcuts, help, click filter, tool search | IMPLEMENTED | te39, te40 |
| 10 Integration | one original track with all of the above, built over the editor's HTTP API, saved / reopened, staged twice identically, inspected, test prepared, screenshots | IMPLEMENTED (offline) | te41 |
| 0.33 Ease of use | tools grouped by task, presets, tool search, guide sections per group, walkthrough (done / next from the project), starter recipes town_circuit / hill_country (one undo step, rollback on refusal) | IMPLEMENTED (automated) | te44 g01-g03, te40 UI steps |
| 0.33 Ease of use | clickable problems: faces highlighted + how-to-fix text + "open tool" | IMPLEMENTED | te44 g04, te40 |
| 0.33 Ease of use | drag handles / 3-D gizmos in the viewport | NOT DONE (numeric entry, click-picking, snapping and axis locks cover the tools; a drag gizmo is a larger viewer change - proposal) | - |
| 0.33 Ease of use | human usability (discoverability, first-time users) | NOT TESTED by a person (automated self-tests only; see "Usability evidence") | - |
| 0.33 Health | explicit OBJ compaction: unused v / vt / vn removed, faces renumbered; equivalence = same corner text, same other lines, identical kit unit blocks; backup first; one undo step | IMPLEMENTED | te42 h02-h05 |
| 0.33 Health | optional backup retention (keep newest N / older than D days): preview, confirm, newest kept, foreign folders untouched, logged; nothing by default | IMPLEMENTED | te42 h06 |
| 0.33 Viewer | wireframe / normals in 64 m chunks, frustum culled, nearest first within 400,000 triangles per frame (replaces the 60,000 cutoff) | IMPLEMENTED (counts benchmarked; frame times not measurable headless) | te40 UI steps, logs\bench_overlay.json |
| 0.33 Buildings | building generator: simple-polygon footprint, height, flat / gable / no roof, wall thickness, door openings (real gaps in walls AND collision; jambs + soffit), ground placement, collision keep / none (twins), re-generate in place | IMPLEMENTED (STAGED) | te43 b02-b05, b07 |
| 0.33 Scenery | low-poly opaque trees (trunk + foliage cone); original examples saved as prefabs (garage, tree) and used by the starters | IMPLEMENTED (STAGED) | te43 b06-b07, te44 g02 |
| 0.33 Buildings | windows / glass, interiors, hip roofs | DEFERRED (opaque materials only; no floors generated; flat / gable only) | - |
| 0.33 Props | real prop instances | BLOCKED for writing: retail placements / lists / consumer VERIFIED-READ (format_research), no writer, prop pool capacity unknown, trackbuild writes none | format_research |
| 0.33 Sharing | shareable export: provenance + licence per file, unknown / game-data files excluded by default, donor requirements, versions without local paths, deterministic zip, imports as a new project | IMPLEMENTED | te44 g07 |
| 0.33 Test | one step Build -> Validate -> Stage -> Prepare test into a new folder; failed gates with how-to-fix; last successful output recorded and kept | IMPLEMENTED (failure path simulated) | te44 g05 |
| 0.33 Viewer | donor environment (sky slots, sun direction / colour, light colour) shown READ ONLY with evidence labels | IMPLEMENTED (read only; no editing) | te44 g08 |
| 0.33 Research | routes (branches, point-to-point), props (placements / lists / consumer), enviro (slots, sun / light consumers) - read-only parsers, 110/110 byte-identical round trips | VERIFIED-READ / PARTIAL | format_research\ROUNDTRIP.json |
| 0.33 Retail (LOCAL ONLY) | owner-requested copies from the user's own game data: retail textures -> materials, opaque retail geometry regions (street-level ground left out, structural-only collision), real retail lampposts (instance models) along the route; provenance retail, share export refused | IMPLEMENTED (local only) | te45, te46 |
| 0.33 Kit 0.3.1-te2 | LOD fallback per material; lod.drop_below (small pieces out of the far mesh, V8 same rule) | IMPLEMENTED (kit suites 5/5) | te46, trackbuild tests_031 |
| 0.33 Road | road_lanes: route road -> lane band + two edge strips at retail-measured repeats (same plane; route checks unchanged; one undo step) | IMPLEMENTED | te43 b08 |
| 0.33 Viewer | authored preview uses the game's UV convention (v unchanged; the old 1 - v showed authored textures upside down) | IMPLEMENTED (preview only) | te40, trackedit, te41 |
| 0.33 Limits | section slots 0x28000 / 0x18000 (HOST pool) | RTA5: host capacity declarations (main21 + patch 131), used by capacity auto | cap5 |
| all | gameplay behaviour of any of it | RUNTIME-UNVERIFIED | - |

## Tutorial (about 15 minutes)
1. **New project**: Workbench -> New track project (template testloop or hill, a track id such as EU_T5_V1) -> Create track
   project -> **Open in track editor...** (Workbench 0.32; the editor runs in its own window titled "Burnout Mashup track editor",
   close it to stop). Step-by-step version for new users: `TRACK_EDITOR_GUIDE.md`.
2. **Route** (Authoring -> "1 Race layout with profile"): closed control points; keep the points around point 0 level (the start
   grid stretch: 45 m before .. 30 m after point 0). Profile `{"sloped": true, "widths": [...one per point], "banks": null}`.
   Preview -> check the structural results and the cross-section chart -> Apply (replace `all` the first time).
3. **Make room for geometry**: Construct -> Unit regions: `include` a rectangle (infield) or `lateral` on one unit (outside).
   Everything must lie inside a unit region; the editor refuses clipping, it never grows regions by itself.
4. **Terrain**: "3 Height terrain" (rect, cell, height a little below the road) -> "3 Terrain brush": click the centre, raise /
   smooth; after roads exist, `blend` to a road block (terrain only moves).
5. **Roads / junctions**: "1 Profiled road" (widths / banks per point) over the terrain; "2 Junction piece"; "2 Open road ends"
   lists refs such as `road2:end`, `junction1:arm0` -> "2 Join". To reach the route, declare an outer gap in the profile
   (`outer_gaps`) and start a road at the gap's outer wall face.
6. **Materials**: "5 Import an original texture" (your own PNG, author + licence) -> "5 New / duplicate material" -> assign it
   (Selection -> material) -> "5 UV" / "5 Paint".
7. **Scenery**: save a selection as a prefab (Construct -> Terrain / scenery) -> "6 Prefab library" -> "6 Place" (snap, ground) or
   "6 Repeat along a path". Changing the prefab later: "6 Refresh copies".
8. **Fix-ups**: "4 Mesh" tools on clicked faces / vertices; "8 Diagnostics" lists problems - click one to see its faces.
9. **Check**: "7 Streaming report" (capacity per section), Save (a backup of the previous save is kept), Build -> Validate ->
   Stage (kit gates), "9 Prepare test" (TEST_PLAN.md + PACKAGE_RECORD.json - an owner-present run is a separate step).

## Buildings and scenery (0.33)
- **Building** (Buildings / scenery -> "Building generator"): footprint corners (plan x z per line, any simple outline of 3..32
  corners, edges >= 1 m, corners >= 30 deg), height, roof `flat` / `gable` (4 corners) / `none`, wall thickness (0 = single-sided;
  > 0 adds the inner shell, jambs and the underside of each lintel), openings `[{edge, offset, width, height}]` (edge i runs from
  corner i to i+1; offset empty = centred). `ground` sits the walls 5 cm below the lowest corner's floor (a warning when the
  corners differ by more than 0.5 m: flatten first). Openings are real gaps in the walls and in their collision (the kit makes
  collision from the faces); the generator adds no floor - drive-through needs a floor inside. Warnings below about 3 m wide /
  2.2 m high (a car may not fit; runtime unproven).
- **Collision**: `keep` uses the materials as they are; `none` uses each material's `<name>_nc` twin (create it with "New /
  duplicate material", collide false) - never created automatically.
- **Tree**: trunk prism + foliage cone, opaque, 3..12 sides; the foliage material decides its collision.
- **Static geometry, not instances**: every building / tree / prefab copy is geometry in its unit (counts fully in the streaming
  report). Real prop instances need a verified writer (format_research\FINDINGS.md section 2: placements and lists are read and
  round-trip exactly; the run-time prop pool size is unknown; trackbuild writes no props).
- Deferred with reasons: windows / glass (no transparency), interiors / storeys (no floors), hip / curved roofs.
- Original examples: `data\starters\town_circuit.json` (garage with a 6 m door, two gable houses, trees) and
  `hill_country.json` (sloped route, brushed hill, farm building); save any block as a prefab to reuse it.

## Project health (0.33)
- **Compact OBJ** (Project / test): removes v / vt / vn lines no face uses (left behind by re-generated blocks, terrain strokes
  and mesh edits) and renumbers the faces. Preview shows the saving; Apply writes a backup of the editor buffers first, proves
  equivalence (every face corner resolves to the same text, every other line unchanged, the kit dry run gives identical per-unit
  streamed blocks) and is one undo step. A commented record is kept. Measured: 6 terrain strokes on a 12 x 5 grid project ->
  1,001,826 bytes, 6,224 v + 3,660 vt + 348 vn unused, 41.2 % smaller, 17 / 17 unit blocks identical (te42).
- **Backup retention** (optional): a rule `keep_last` N and / or `older_than_days` D; Preview lists what would go; Apply needs
  confirm and deletes exactly that list (cannot be undone). The newest backup is always kept; folders the editor did not write
  are never touched; RETENTION_LOG.jsonl records it. Nothing is deleted unless you do this.
- **Overlays**: wireframe / normals are binned into 64 m chunks once per mesh change; each frame draws the chunks in view,
  nearest first, up to 400,000 triangles (the HUD says when the budget leaves distant chunks out).

## Sharing (0.33)
- **Shareable export** (Project / test): Preview lists every file with its provenance (kit template unchanged / edited, imported
  original file with author + licence, project file) and what is excluded: game / build data always, files of unknown origin
  unless you include them with your own author + licence statement. The zip holds `sources\`, `MANIFEST.json` (sha256,
  provenance, versions without local paths, donor requirements) and `SHARING.md` (licences, donor requirements, reproduction
  steps). Same saved project -> identical zip bytes. Import: "Import a source zip as a NEW project".
- **Donor**: a build still copies sky / lighting (enviro), audio and the event header from the donor track of the receiver's own
  game data; the track is not independent of the donor. A built package contains retail data: keep it local.

## Roads and race layout (0.33 assessment)
- **Banking on the route**: still limited by the kit gate V2 (the floor must stay within 0.05 m of the route height wall to wall).
  Not loosened. A surface- / cross-section-aware V2 (compare each sample with the BANKED cross-section height instead of the
  centre height) is the justified successor rule, but it changes what the kit accepts as drivable and the game's AI / respawn /
  floor probe behaviour on a banked route is unproven: PROPOSAL P-BANK (trackbuild successor + one owner-present run of a route
  banked within today's limit first). Off-route roads bank freely (geometry + collision only).
- **Variable width, elevation transitions, joins, junctions**: implemented in 0.31 (te31 / te32) and used by the hill_country starter.
- **Branching AI / traffic routes**: the retail format is now understood (format_research 1: alternate lanes on the shared slice
  axis, zero-width rungs, lateral links; no fork record) - three levels kept apart: GEOMETRIC connectivity (editor: junction /
  join, done), STRUCTURALLY VALID data (needs a trackbuild successor writing an extra lane through the ct2_route rules - not built),
  RUNTIME-PROVEN behaviour (none). The editor's routing report marks junctions "geometric only".
- **Lanes, checkpoints, starts, laps, respawn**: validated structurally by the kit gates and the routing report; runtime unproven
  (R1-R11 of the 0.31 plan).
- **Point-to-point**: retail uses it (P tracks: chained non-cyclic lanes, 1 lap). Blocked for authoring by trackbuild (closed
  circuits only) and by the undecoded S1 finish / progress data. **Flat start**: the editor keeps 45 m before .. 30 m after point 0
  level because trackbuild writes the grid and start line level (kit 0.3.0 README); a sloped grid needs grid / start heights in the
  writer first.

## Streaming and limits (0.33 audit)
| Limit | Value | Class | Where | Raising it |
|---|---|---|---|---|
| mesh block per unit | game 0x28000 B, host ceiling 0x200000 | HOST (declared capacity) | kit trackbuild.capacity TABLE (RTA5) | capacity auto: mod.toml full_unit_bytes (patch 131+) |
| LOD block per unit | game 0x18000 B, host ceiling 0x200000 | HOST (declared capacity) | trackbuild.capacity (the stacked-terrain 0x22000 is within the ceiling under auto; benchmark not re-run) | capacity auto: low_unit_bytes (main21+ to 0x30000, patch 131+ above) |
| static.dat / Gamedata / lanes | game 0xD00000 / 0x176000 / 64; ceiling 0x4000000 / 0x800000 / 255 | HOST (declared capacity) | trackbuild.capacity | capacity auto: static_bytes (patch 131+ above 0x20C4000), gamedata_bytes, lanes |
| records per unit | 127 | FORMAT | unit record count field | no (format) |
| vertices per unit | 65,536 | FORMAT | u16 indices | no (format) |
| material rows | 83 | FORMAT / TOOL | trackbuild preflight | format study first |
| PVS window | 17 chunks | FORMAT | visibility.py | no |
| collision cells | +-128 | FORMAT | blocks.py | no |
| units | 17 (pvs all) / 4..162 (computed) | TOOL | trackbuild units.py | trackbuild successor + runtime check |
| LOD e_max | <= 0.3 m | TOOL (runtime-validated bound) | lod.py / editor | needs a run with larger values |
| terrain cells per block | 4096 | EDITOR | wb_te_author | editor (no format reason; kept for responsiveness) |
| overlay triangles | 400,000 per frame (budget, nearest first) | EDITOR | trackedit.html | editor |
| prop pool | unknown | HOST | pool 0x3FA4D4 (format_research 2) | find the size first |
Nothing is clipped, dropped or grown silently: a block that does not fit is refused with the slot named (the streaming report and
the kit dry run on every Apply). RTA5: project setting **Capacity** (Streaming -> LOD / visibility / capacity settings; the
description key `capacity`): **auto** (default) = a block above the game's slot that fits the host ceiling is INFO ("unit 19 mesh
0x2A000 - above the game's 0x28000, declared full_unit_bytes 0x2A000 (needs ... patch 131+)") and the package declares it in
mod.toml; **game** = refused above the game's defaults (for hosts without capacity declarations). Retail track extensions keep
the game's slots (their output has no mod.toml).

## Usability evidence
- AUTOMATED (this session): headless-Edge page self-test (te40: 38 steps incl. grouped panel, presets, guide sections, walkthrough,
  building through the panel, fix lines, compaction preview, overlay culling); HTTP-level suites te31-te44; button test (5 cases).
- NOT DONE: a person using the editor for the first time (discoverability, wording), keyboard-only operation beyond the listed
  shortcuts, window resizing / high DPI at 300 % in a real browser (the pre-existing test_capture_dpi item stays pending). These
  need a human session; nothing here claims them.

## Known limitations (facts, with where they come from)
- **Route banking**: kit validate.py V2_drivable_coverage samples wall to wall and needs the floor within 0.05 m of the route
  height -> a drivable route can bank only by `atan(0.04 / half reach)` (the editor keeps 0.01 m margin). Off-route roads bank
  freely. Not loosened.
- **Sloped routes need trackbuild >= 0.3.0** (the Workbench config binds main21 trackbuild 0.3.0; the older suites' test config
  binds the kit's 0.2.1). The start stretch must stay level (the grid is written level).
- **Routing**: one closed AI route with 5 cyclic lanes, one authored traffic road (format). Junctions, joins and side roads are
  geometry and collision only; AI and traffic never use them. Outer-wall gaps are the kit's declared "crash-test variant".
- **Overlaps**: a new floor coplanar with (within 0.03 m of) or below an existing collision floor is refused; on top is allowed
  (layered: the highest floor counts). Terrain blocks lie under roads by design.
- **Terrain**: each stroke re-writes the block; the old v lines stay unused in the OBJ (no renumbering compaction): after many
  strokes the OBJ grows (8 strokes on 24 x 10: 1.1 MB).
- **Hand mesh edits on a construction block** are kept but re-generating that block from its tool replaces them (warned).
- **Mesh edits**: the clip rule for changed faces is measured in plan; a face that was already partly outside a region and is
  edited is refused (no partial-loss allowance beyond the cut-rounding one).
- **Materials**: opaque, one texture, keys texture / surface / collide / car_solid, <= 83 rows; surface words beyond the documented
  ones are shown as unknown, never interpreted.
- **UV seams at joins**: geometry is continuous; u can mirror and v can jump at a join's far end (reported, not hidden).
- **Copies, not instances**: placed prefabs count fully in each unit's capacity.
- **Limits** (streaming report has the table): mesh 0x28000 / LOD 0x18000 bytes per unit, static 0xD00000, Gamedata 0x176000 =
  the game's defaults; RTA5 capacity auto raises them up to the host ceilings (0x200000 / 0x200000 / 0x4000000 / 0x800000, 255
  lanes; 255 material rows with the host BMRX extension - trackbuild keeps 83; records 127, 255 planned with patch 132; units 4..162 computed) with a mod.toml declaration (HOST, kit capacity table); 127 records, 65,536 vertices, 83 rows, 17-chunk PVS window, +-128 collision cells = FORMAT;
  17 units with pvs all, 4..162 computed, LOD e_max <= 0.3 m = TOOL-configured; 4096 cells per terrain block = EDITOR.
- **Viewer**: shading is approximate (texture x baked colour); no sky / fog / lighting preview (enviro.dat is now read-only
  decoded - slots and sun / light consumers traced, fog HYP - but no editor control or writer). Overlays: see Project health.
- **Backups** accumulate in Workbench state unless you apply a retention rule (0.33).
- **Point-to-point**: retail P tracks are chained non-cyclic lanes with 1 lap (format_research); trackbuild builds closed circuits
  only and the S1 finish / progress data is not decoded - not authorable yet.

## Blocked items: evidence, research, next experiment
| Item | Evidence | Research needed | Next experiment |
|---|---|---|---|
| Banked drivable route | validate.py 157-188 (V2 0.05 m wall to wall) | does the game's AI / respawn / floor probe handle a banked route? | owner-present run of a route banked within V2 (built here) and, separately, a trackbuild branch with a bank-aware V2 rule (kit change, owner decision) |
| AI / traffic branching | trackbuild writes one S4 route (5 cyclic lanes), S3 one road | DONE (read): branches = extra lanes on the shared slice axis, zero-width rungs, lateral links only (format_research 1) | a trackbuild successor writing one alternate lane through the existing ct2_route rules + an owner-present run |
| Transparent / special materials | trackbuild preflight: 4 keys; DXT1 opaque | material type / flag semantics (retail +0x24 flags are read in the retail VIEW only) | a kit change for alpha-tested DXT1 + one in-game check |
| Instances / props | no prop / instance path in trackbuild | DONE (read): placements, per-unit lists, consumer sub_0018CBC0 (format_research 2) | the prop pool size (0x3FA4D4), then a writer on wm2_static |
| Sky / fog / lighting | no editor path | PARTIAL: slots + sun / light consumers traced; fog fields HYP (format_research 3) | trace view 0x4D6170 + 0x260 readers or one runtime A/B |
| Larger unit memory | streamed.py:22 retail pool layout | host streaming pool | host checkpoint (SDK capacity example), not editor work |

## Runtime status
RUNTIME-UNVERIFIED for every feature above: no game was launched in this queue. RUNTIME_PLANS_TE2.md has the owner-present plans:
part A = the 0.31 baseline demo package (R1-R11), part B = the 0.33 candidates (town_circuit, hill_country; built twice
identically by tools\make_candidates.py), each with exact hashes, controls, expected outcomes and stop conditions.

## Files
wb_te_geom.py (road / junction / terrain geometry), wb_te_mesh.py (OBJ mesh editing), wb_te_author.py (the editor operations,
mixin of wb_trackedit.TrackSource), wb_trackedit.py (hooks: profile branch of race layouts, pending imported files in Save,
backups, normals in the scene, TE dispatcher), trackedit.html (Authoring tools panel, overlays, picking, shortcuts, self-test
section "te"). 0.33: wb_te_health.py (compaction, retention), wb_te_bldg.py (buildings, trees), wb_te_guide.py (fix hints,
walkthrough, guide sections, test chain, starters, donor environment view), wb_te_share.py (shareable export), data\starters\*.json,
format_research\ (read-only parsers). Tests: tests\test_te31_road.py .. test_te44_guide.py (suites te31 .. te44 in
tests\test_deps.json), tests\bench_overlay.py, tests\test_wb_button.py, tools\make_candidates.py.
Compatibility: no shared schema changed (0.33 adds block kinds `building` / `tree` in the same comment tags; older editors show
them as ordinary face groups). Description keys used are trackbuild's own (stations, units, widths via offsets, wall_gaps,
lod, pvs, materials, rows); editor data lives in OBJ comment tags (`# wb-construct {...}`, ignored by trackbuild) and in
`editor_provenance.json`; old projects open unchanged and a race layout without a profile writes byte-identical output to v0.30
(te31 r06).
