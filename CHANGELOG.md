# Changelog

## 0.2.0-alpha.2 - bigger track limits, retail-style track authoring, an easier track editor, Build demos fixed (experimental alpha)
- **Host: much larger limits for detailed tracks.** A track mod can ask for bigger full-detail sections with the new mod.toml key
  `[bmashup.capacity] full_unit_bytes` (up to 2 MiB a section; the game has 160 KB), and the existing keys go higher:
  `low_unit_bytes` up to 2 MiB, `static_bytes` up to 64 MiB. A section can draw up to 255 material rows (BMRX, was 127) and hold
  up to 255 mesh records (new block flag BMRC, was 128); the renderer keeps twice as many textures. Before, a detailed track could
  stop the game with "track unit too large". Details: `docs/services/CAPACITY.md`. **Build Mashup builds the new host once** after
  this update (the host sources changed); an older host refuses a mod that uses `full_unit_bytes` and starts without it.
- **Workbench and track editor: capacity.** Build uses the new limits automatically (**Capacity: auto**, the default): a track
  that needs more than the game's defaults is built anyway and its mod declares exactly what it needs. **Capacity: game** keeps
  the old limits for tracks meant for older hosts. The editor shows each limit, the game value, the host ceiling and what the
  track uses.
- **Workbench 0.33 - retail-style track authoring:** dress your own track in the style of the Burnout 3 tracks on YOUR disc.
  The track editor's **Retail-style authoring** and **Retail-style designer** panels build a local asset library from your game
  data (read only), offer measured styles (waterfront city, downtown city, countryside, original town), generate roads, verges,
  walls, buildings, trees and posts along your route (preview first, one undo step) and place single pieces. Nothing from the game
  ships with Burnout Mashup, and shared projects hold instructions only. Guide: `workbench/RETAIL_STYLE_GUIDE.md`.
- **Workbench 0.33 - an easier track editor:** tools grouped by task with presets and guide buttons, a first-track walkthrough,
  starter projects, "How to fix" for every problem, build + validate + stage in one step, a building generator and low-poly trees,
  project health (OBJ compaction with backup), large-track viewer, shareable export. `TRACK_EDITOR_GUIDE.md` covers the new parts.
- **trackbuild 0.3.4** (capacity auto / game, `tb.py capacity`) on top of **0.3.3:** branch lanes (a bypass beside the main road) and bridges (a road crossing over itself; templates `branch`,
  `fig8`), retail materials and objects for the retail-style tools, race layouts of 18..64 sections with computed visibility, LOD
  fallbacks for detailed scenery. Flat test loops still build byte-identical.
- The Workbench / editor features are checked offline only. The new host limits ran in the game once (a restyled White Mountain
  track with bigger sections raced two laps); the maxima, split screen, Linux and macOS are not tested.
- **Workbench 0.32:** the **New track project** tab has an **Open in track editor...** button (the project you just created,
  or one you pick) and a **Track editor guide** button. Before, the editor could only be started from a command line. The editor
  runs in its own window; close it to stop the editor.
- **New guide:** `workbench/TRACK_EDITOR_GUIDE.md`, a step-by-step guide to making a track for people new to the editor. The
  reference page `TRACK_EDITOR_AUTHORING.md` now points to it, and its first tutorial step names the right templates.
- **Fixed: Setup step 3 "Build demos"** failed in 0.2.0-alpha.1 for everyone (`coupe: FAILED - [WinError 3] ...` and
  `REFUSED: ...tools\kit\trackbuild\tb.py missing: unpack the bundle again`). `launcher/tools/TOOLS.json` still named the folders
  of the old tester package; it now names the tools and sources this package ships (`tools/carimport`, `tools/trackbuild`,
  `examples/authored/...`). The three demos (coupe, test loop, canyon ring) build again. Playing was never affected.
- Not changed: the launcher and updater code and your data. The host sources changed (see above): Build Mashup rebuilds it.
  Help -> Check for updates in 0.2.0-alpha.1 finds and installs this version.

## 0.2.0-alpha.1 - the Windows package, updates, Workbench 0.31 (experimental alpha)
- **New download:** `BurnoutMashup-0.2.0-alpha.1-windows.zip` with two small starters (`Burnout Mashup.exe`, `Burnout Mashup
  Workbench.exe`), `gamedata\` (your game copy, with your mods in `gamedata\mods\user` and the demo mods made from your game in
  `gamedata\mods\generated`) and `app\` (the program = this source). The starters are release downloads only, never in git; no game
  executable is shipped (Build Mashup builds it on your PC as before). Their source: `launcher/tools/launcher/exe`, `workbench/exe`.
- **Moving from 0.1.0-alpha.1:** unpack the new zip into your old folder and start `Burnout Mashup.exe`. Your saves, settings,
  plugin approvals, mods, game copy, host builds, Workbench settings and any file you added are moved into the new layout in one
  transaction (renames only, undone on any error, finished or undone after a crash at the next start); the old program files are
  kept in `app\.update\versions`. Or start the new version in a fresh folder and use **Bring my data from an older Burnout Mashup
  folder** (copies, the old folder is only read). Your host build stays valid: the host is unchanged in this release.
- **Updates work:** the update channel is set (this repository's releases, signed with the release key
  `SHA256:tQRHolv3k/JYwlk5b3rS8fkZ3LbHWdOfyl+5eXUHnGg`). Help -> Check for updates: check, download, prepare, **Install** (the program
  and both starters are replaced in one undoable step; your data is carried over; the launcher restarts), **Switch back**. Nothing
  is checked by itself.
- **Workbench 0.31:** the track-editor authoring tools (sloped and banked roads, junctions, terrain, materials, prefabs, LOD,
  streaming report; `workbench/TRACK_EDITOR_AUTHORING.md`). Runtime-unverified in the game (see that page's limitations).

## 0.1.0-alpha.1 - the first public source release (experimental alpha)
- The first public version of Burnout Mashup, as source code only. It contains the host (as changes on top of Takedawn 4f074e211822
  and xboxrecomp e3756d1b2fef) with its own name, folders and icon, so it never touches a Takedawn install; the hook marks; the SDK;
  the content tools; the Workbench; the launcher with Build Mashup; original examples; and the documentation.
- Build Mashup builds the game on your PC from your own copy and checks the result against the reference build before it can
  be played.
- The updater is included but has no update channel yet, so it never checks for anything.
- Experimental: tested by its authors on one PC. Open questions are listed in `docs/PUBLIC_STATUS.md`. The history of the
  earlier private kit releases is in `docs/CHANGELOG.md`.
