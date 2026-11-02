# Retail-style track authoring - user guide (Workbench v0.33)

Start the track editor on a track project as usual (Workbench -> New track project -> Open in track editor..., or
`py -3 -B wb_trackedit.py "<project>"` inside the `workbench` folder). Open the panel **Retail-style authoring** in the right column.
Every step previews first; nothing in your project changes until you press an Apply / Add button. Your game data is only read.
Anything built from your game data stays on your PC (never share or upload it); step 7 shares instructions only.

## 1 Asset library
- The panel shows the game data folder the Workbench uses (Workbench settings), how many tracks it found and how many are
  catalogued. Tracks that cannot be catalogued are listed with the reason (e.g. US/C5_V1 has no Gamedata.bgd).
- **Create / refresh asset library** runs in the background (progress bar, **Cancel**). First time about 5 minutes for 36 tracks;
  afterwards seconds (cache keyed by the sha256 of your files; a changed file is re-read).
- **Search** by name / role / kind / track. Click a result: thumbnail (made on demand) + measured facts (size, memory estimate,
  area, facing, distance from the route, setback / spacing for roadside models) and how it can be used:
  - textures: as authored road / wall / ground materials (opaque only);
  - instance models (posts, trees, signs): GEOMETRY COPIES along a route (opaque ones only; cut-out trees are refused);
  - smashable props: read only (no writer).
- Kinds include **building** and **structure**: pieces of each track's render mesh (all tracks, 15,709 + 26,613). Click one:
  thumbnail + size, then **Place in this project** (x z, turn, collision) -> Preview -> Place (one undo step, LOCAL ONLY).
  Instance models (posts, trees, signs, benches, cars) and smashable props (placed as static scenery) work the same way.
- Roles are MEASURED geometry classes ("road surface", "barrier / wall", "tall vertical surface (facade / cliff)", ...), never
  guessed from names.

## 2 Style
- Pick a preset and press **Show**: three separate sections - **Measured** (read only, from one retail track), **Palette** (with
  the reason for each choice) and **Artistic defaults** (editable). Builder limits are listed at the bottom.
- Shipped presets: Waterfront city (US/C1_V1), Downtown city (US/C2_V1), Countryside (EU/C2_V1), Original town (no game data).
  A preset's "kind" is only given when the measured composition supports it; facades and cliffs measure alike.
- **Derive** a new preset from any catalogued track (it lands in your Workbench state, never overwriting the shipped ones).

## 3 Route
- Click the sketch to add control points (closed loop; red = point 0, the start - keep it on a straight; right-click removes the
  last point), or type `x y z` per line, or **Use current route**. Grid sizes 400 / 800 / 1600 m.
- One height per route keeps the start level; different heights make a sloped route (start stretch stays level).

## 4 Generate
- Seed, road width, densities (buildings / trees / posts), parts on / off, exclusion rectangles (`x0 z0 x1 z1; ...`).
- **posts**: empty = the style's measured posts (two types: one per side). Or list your own, from ANY track:
  `TRACK MODEL SIDE [spacing] [start]; ...` e.g. `US/C1_V1 I35 outer 100 10; EU/C4_V1 I11 outer 100 60` alternates a cobra-head
  with an ornate European lamp. **Post types...** lists every post-shaped model (size, measured spacing / setback); click add.
- **Preview generation** runs in the background on a copy (Cancel any time): steps, capacity of the worst unit (mesh / LOD slot),
  material rows, PROBLEMS (Apply is disabled while there are any), notes (e.g. "verges stepped down on a tight curve") and the
  skipped placements grouped by reason - click a reason to see the places as markers in the 3-D view.
- **Apply** = ONE undo step (Undo removes the whole generation incl. imported textures). Save, then Build / Validate / Stage as usual.

## 5 Generated parts
- Buildings and trees are one block each, with seed and parameters stored. **Regenerate this part only** (new seed) leaves every
  other block byte-identical. **Lock** protects a part. A part you edited by hand is refused unless "replace hand edits" is ticked.
- Everything else (road, walls, verges, posts) is the editor's normal construction blocks: edit them with the usual tools.

## 6 Extend a retail track
- Pick a track, **Round-trip check** (proves the untouched track is rebuilt byte-identically by the verified readers; editing is
  blocked otherwise), choose a NEW folder, **Create** (the project only references your retail files).
- **Unit materials** lists what that unit draws; an extension piece can only use those. Set side / setback / along / size,
  **Preview attachment** (top view, ground seam, budget, LOD / visibility / collision notes) -> **Add to project** -> **Build
  extension** into a new folder. The build report lists every changed / moved / unchanged section.
- What it is: decorative buildings beside the route, no collision, not drawn in the far LOD. What it is not (blocked): drivable
  roads, branches, new materials, props.

## 7 Share (recipe only)
- **Preview** / **Export** a recipe of this project's generation or of the extension project: recipe.json + SHARING.md, a few KB,
  with asset references, measured numbers, file hashes, versions and seeds. Author and licence are required.
- **Check** / **Rebuild** a recipe from someone else: refused when your game files differ from theirs. Rebuilding a generation
  recipe starts the preview on the open project; an extension recipe creates a new extension project.
- A recipe never contains textures, retail geometry, thumbnails, caches or built tracks. Rebuilding from your own copy is not
  legal clearance; the project's distribution questions (Q1-Q9) remain open.

## Troubleshooting
| Message | Meaning / remedy |
|---|---|
| no Tracks folder in ... | set the game data folder in the Workbench settings |
| your game data changed since the catalogue was made | press Create / refresh |
| style ... cannot be applied to your game data | your files differ from the preset's measurement: Derive a preset from your data |
| verges outer X / inner Y refused | the route curves too tightly for wide ground strips: the generator steps down; or widen the curve |
| a unit is above 95 % of its slot | lower densities, add exclusion areas |
| unit N has no strip record with texture T | pick a texture from Unit materials |
| ... outside unit N's region quad | smaller setback / size, or another unit |
