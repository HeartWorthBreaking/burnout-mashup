# Track editor - authoring tools (Workbench 0.31, gp\workbench_te, 2026-11-01)

An isolated successor of Workbench v0.30 (`gp\workbench` is unchanged). It adds the authoring queue to the track editor:
road design, junctions, terrain, mesh editing, materials, scenery, streaming / LOD / visibility, viewer overlays and project
workflow. **Every result below is offline**: kit gates (trackbuild 0.3.0 `validate`) and the editor's own checks. Nothing here has
been driven in the game; see "Runtime status".

Start: `py -3 -B wb_trackedit.py <track project>` (the Workbench's track editor; panel **Authoring tools (TE queue)** under
Construct). Every tool: **Preview** (nothing changes) -> **Apply** (with that preview; one undo step). A refusal changes nothing
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
| 7 Streaming | raising mesh / LOD slot sizes | BLOCKED here (HOST ceiling: needs host work, separate checkpoint) | - |
| 8 Viewer | wireframe, stored normals (mismatch red), collision, routes, sections / LOD, clickable diagnostics, approximate-shading label | IMPLEMENTED | te38, te40, te41 screens |
| 8 Viewer | sky / fog / track lighting previews | BLOCKED (enviro.dat: no verified reader) | - |
| 9 Workflow | backups on every Save + verified restore, transactional save, source export / import (manifest), versions, prepare test (plan + package record, no launch), shortcuts, help, click filter, tool search | IMPLEMENTED | te39, te40 |
| 10 Integration | one original track with all of the above, built over the editor's HTTP API, saved / reopened, staged twice identically, inspected, test prepared, screenshots | IMPLEMENTED (offline) | te41 |
| all | gameplay behaviour of any of it | RUNTIME-UNVERIFIED | - |

## Tutorial (about 15 minutes)
1. **New project**: Workbench -> New track project (template EU_T5 or hill). Open it in the track editor.
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
  HOST ceilings (retail pool layout); 127 records, 65,536 vertices, 83 rows, 17-chunk PVS window, +-128 collision cells = FORMAT;
  17 units with pvs all, 4..162 computed, LOD e_max <= 0.3 m = TOOL-configured; 4096 cells per terrain block = EDITOR.
- **Viewer**: shading is approximate (texture x baked colour); no sky / fog / lighting (no enviro.dat reader). Overlays are capped
  at 60,000 triangles for responsiveness.
- **Backups** accumulate in Workbench state (never deleted by the editor).

## Blocked items: evidence, research, next experiment
| Item | Evidence | Research needed | Next experiment |
|---|---|---|---|
| Banked drivable route | validate.py 157-188 (V2 0.05 m wall to wall) | does the game's AI / respawn / floor probe handle a banked route? | owner-present run of a route banked within V2 (built here) and, separately, a trackbuild branch with a bank-aware V2 rule (kit change, owner decision) |
| AI / traffic branching | trackbuild writes one S4 route (5 cyclic lanes), S3 one road | S4 / S3 fields for branches (unknown; never guess) | read retail tracks with junction-like layouts in the S4 / S3 readers |
| Transparent / special materials | trackbuild preflight: 4 keys; DXT1 opaque | material type / flag semantics (retail +0x24 flags are read in the retail VIEW only) | a kit change for alpha-tested DXT1 + one in-game check |
| Instances / props | no prop / instance path in trackbuild | retail prop sections | reader work first |
| Sky / fog / lighting | wb_retail: "enviro.dat UNSUPPORTED: no reader in the kit" | enviro.dat format | a verified reader (KB) before any preview |
| Larger unit memory | streamed.py:22 retail pool layout | host streaming pool | host checkpoint (SDK capacity example), not editor work |

## Runtime status
RUNTIME-UNVERIFIED for every feature above: no game was launched in this queue. The demo (tests\test_te41_demo.py) produces a
staged package and a TEST_PLAN.md; running it needs the owner, the runner token and a fresh root (PC CLAUDE.md).

## Files
wb_te_geom.py (road / junction / terrain geometry), wb_te_mesh.py (OBJ mesh editing), wb_te_author.py (the editor operations,
mixin of wb_trackedit.TrackSource), wb_trackedit.py (hooks: profile branch of race layouts, pending imported files in Save,
backups, normals in the scene, TE dispatcher), trackedit.html (Authoring tools panel, overlays, picking, shortcuts, self-test
section "te"). Tests: tests\test_te31_road.py .. test_te41_demo.py (suites te31 .. te41 in tests\test_deps.json).
Compatibility: no shared schema changed. Description keys used are trackbuild's own (stations, units, widths via offsets, wall_gaps,
lod, pvs, materials, rows); editor data lives in OBJ comment tags (`# wb-construct {...}`, ignored by trackbuild) and in
`editor_provenance.json`; old projects open unchanged and a race layout without a profile writes byte-identical output to v0.30
(te31 r06).
