# Changelog

## 0.3.0-alpha.3 - Easier to read in-game menus (experimental alpha)
- **Mods page:** after you approve a plugin or change a mod, the result stays in the help text at the bottom until you reopen the page. Before, it could be scrolled out of sight. The Mods folder lines are larger, in the normal text colour, and wrap instead of shrinking.
- **Long lists:** rows now fade out at an edge where the list carries on, instead of being cut in half.
- **Section titles and notes:** a soft dark band behind them keeps the background's blue streak from running through the text.
- **Help text:** the setting for the entry in the game's menu no longer names TAKEDAWN SETTINGS; the entry itself already read MASHUP SETTINGS.
- **Host:** this release has a new host, so Update now rebuilds it after installing.

## 0.3.0-alpha.2 - Build Mashup no longer fails after an update (experimental alpha)
- **Fix:** after updating to 0.3.0-alpha.1, Build Mashup stopped with "ended with exit 3" for anyone who had built before. Git's read-only files were left in the build folder and could not be deleted when the sources were fetched again. Build Mashup now removes them.
- **If you are stuck on exit 3:** press Update now. It installs this version and finishes the build; you don't need to delete anything by hand. If you have 0.2.0-alpha.3 or 0.2.0-alpha.4, `fix-update.cmd` is still needed once.
- **Repository:** the two upscaler programs that 0.3.0-alpha.1's commit left out (`realesrgan-ncnn-vulkan.exe`, `vcomp140.dll`) are now in the repository. The packages always had them.
- **Host:** the same as 0.3.0-alpha.1 (the same host files and reference builds).

## 0.3.0-alpha.1 - On Takedawn 0.3.0 (experimental alpha)
- **Now built on Takedawn 0.3.0.** The Mashup's host changes moved from Takedawn 0.2.1 to 0.3.0 (Takedawn `0dd10432d936`, xboxrecomp `03b4f22aa6e7`). Saves and mods stay where they are. **Build Mashup has to rebuild the host once** after this update.
- **Online play is included but off by default.** Turn it on in Settings > System > Online play (it asks for a restart). Internet uses the Takedawn community server; Local network needs no server. Not tested against Takedawn players.
- **Bloom:** Takedawn's own fix for glow dots at a render scale replaces ours.
- **Mods:** one mods page, the Mashup's. Takedawn's Mods tab is not included; its functions are on the MODS page: the mods folder, Turn every mod on, and Sharper menu pictures.
- **Sharper menu pictures:** the AI upscaler ships with the launcher (`launcher\upscaler`, about 42 MB, licences in `LICENSES`). The pictures are made on your PC from your own disc.
- **Also from 0.3.0:** soft-body damage (off by default), Language, 16:10 and more; see Takedawn's release notes. Only the North American disc is supported here: the European discs are not.
- **Tested:** one game run by the maintainer on an earlier build of this host, with no problem seen, and one automated game run of this release host: White Mountain driven by the autopilot demo for about five minutes at render scale 3, with no errors, Takedawn's bloom fix active, PS2 SOUND on and the sound playing without gaps. **Not confirmed:** whether the bloom looks better, how PS2 SOUND sounds by ear, a finished lap, the Online and MODS pages on screen, and approving a plugin on the MODS page (plugins loaded from approvals saved beforehand; in the maintainer's run the approval was not saved). No retail data and no game files are in the release. Linux and macOS: not built.

## 0.2.0-alpha.5 - Update now and Switch back no longer fail because of the launcher's own font (experimental alpha)
- **Fix:** in 0.2.0-alpha.3 and 0.2.0-alpha.4 the launcher kept its font file (`app\launcher\fonts\RobotoCondensed-Medium.ttf`) open for as long as it ran, so Update now
  and Switch back could not rename the `app\launcher` folder and stopped with "WinError 5, access denied". The theme (`bmtheme.py`; the Workbench's `wb_theme.py` is the same file)
  now reads the font file, closes it and hands the bytes to Windows (`AddFontMemResourceEx`, a font of that process only), so no file under `app\launcher` stays open.
  If that fails the system font is used, without an error. Nothing else changed in the launcher (1.2.0) or the Workbench (0.34).
- **From 0.2.0-alpha.3 or 0.2.0-alpha.4 you need `fix-update.cmd` once.** The old launcher is the one that runs the update, so it still fails. `fix-update.cmd` is a new file of
  this release (also in `launcher/`): close the launcher and the Workbench, put it in the folder that holds `Burnout Mashup.exe` and double-click it; it runs the launcher's own
  check, download, prepare and install, and stops with a plain message at any failure. From 0.2.0-alpha.5 on, Update now and Switch back work from the launcher.
- **Host:** unchanged from 0.2.0-alpha.4 (the same host files and reference builds). An update from 0.2.0-alpha.4 needs no rebuild; from 0.2.0-alpha.3 Build Mashup rebuilds
  the host once, as for alpha.4.
- **Tested:** a real launcher window (no game) was kept open while the shipped `bmupdate.py` did a real install and a real switch back, against a local test channel with a test key (all signature checks on; only the trusted key was the test key). With the 0.2.0-alpha.4 launcher both steps failed with WinError 5 and the install was undone; with the 0.2.0-alpha.5 launcher both worked, also the update from the published 0.2.0-alpha.4 package to this package. `fix-update.cmd` was run on real 0.2.0-alpha.3 packages against the live 0.2.0-alpha.4 channel (fresh, second run, already prepared, after a failed install, a path with spaces, brackets and an ampersand, wrong folder) and once from 0.2.0-alpha.4 to this package. Not tested: the update through the real channel to this release (it is not published yet), the Workbench window, the buttons pressed by a person, Linux and macOS.
- **Sound:** as far as we know no one has confirmed the PS2 SOUND host of 0.2.0-alpha.4 in the game yet; nothing about the sound changed here and nothing new is claimed.
  No retail data and no game files are in the release. Linux and macOS: not built.

## 0.2.0-alpha.4 - PS2 SOUND setting (experimental alpha)
- **New setting PS2 SOUND** (MOD SETTINGS, BURNOUT MASHUP; **default off**). It brings the sound closer to the PS2 version; it does not make it equal to it.
  The mix part works in stereo only. While it is on:
  - effects are interpolated the way the PS2 sound chip's interpolation works (our own formula; no table of the chip's or of an emulator's is included);
  - sounds get no Doppler pitch;
  - the reverb uses the PS2 version's room levels;
  - music has the bandwidth of the PS2 version's streams;
  - boost and takedown sounds are no longer summed up by the stereo fold and are kept out of the engine distortion stage.
  **The safety limiter is off while PS2 SOUND is on, so the loudest moments can clip.**
- **Host:** main21 patches 139..146. Three new files for xboxrecomp in `host/toolkit/added/src/apu/` (`apu_gauss.h`, `apu_softmusic.h`, `apu_ps2mix.h`;
  our own files, MIT, with their licence header); `host/marks`: 524 marks (3 new, none changed or removed). CMake switches `BO3_HOOKREQ_ZDOP`,
  `BO3_HOOKREQ_ZPS2`, `BO3_HOOKREQ_ZPSM`, `BO3_HOOKREQ_ZPSX` (ON in the public build; OFF compiles the part out). `build/EXPECTED.json`: new reference builds.
  Build Mashup rebuilds the host once after the update. Launcher 1.2.0 and Workbench 0.34 are unchanged.
- **Licence:** the changes to the xemu-derived LGPL files `apu.h`, `apu_state.h` and `apu_vp.c` are in `host/toolkit/lgpl/` (LGPL-2.1-or-later), each with a dated
  "Burnout Mashup modification" note in the code and named in `host/toolkit/lgpl/NOTICE`; `host/toolkit/toolkit.patch` (MIT) holds no hunk of a file with an xemu or LGPL header.
  The patch file there keeps the name `apu_core.patch`. `build/apply_layers.py` reads the list of LGPL files from `host/LAYERS.json`.
- **Facts:** a tester sent a recording of a race on the earlier host (no written verdict); the project owner listened and judged it good enough. The single-switch change,
  the boost and takedown change and this exact host have not been started by anyone; tested offline only. No retail data and no game files are in the release.
  Linux and macOS: not built.

## 0.2.0-alpha.3 - one-click Update and Build, a new look, custom music on the banner and in the mix, bloom fix (experimental alpha)
- **Update now:** Help and the Updates window have one button: check, download, prepare, install, restart (and build when one is
  needed). The click is the consent; Cancel stops, Switch back undoes. The single steps stay under Advanced options. There is still no
  automatic check. Fixed: the Updates window never restarted the launcher after an install or a switch back. That fix is in this
  version, so an update FROM 0.2.0-alpha.1 / alpha.2 does not restart by itself: start the launcher again by hand once.
- **Build Mashup:** one button: it takes the game from the last build or `gamedata\`, asks one question for all missing tools (names,
  sources, sizes, licences), downloads, builds, verifies and installs. Upstream source, tools table and build folder are under Advanced
  options. **The update from 0.2.0-alpha.2 needs one Build Mashup rebuild** (the host sources and the icon changed).
- **New look** for the launcher and the Workbench 0.34: near-black palette, Roboto Condensed Medium (`launcher/fonts`, SIL OFL 1.1), a new
  title picture and a new BM icon for the host and both starter programs. The title and icon are fixed pictures (`launcher/art`,
  `host/tree/assets/icon/bmashup.ico`); no game art is in them and no font they were drawn with ships. They are project artwork, not MIT or CC0 (`LICENSES/LicenseRef-BurnoutMashup-Artwork.txt`).
- **Warning before a game about clashing mods:** two enabled mods adding one track id, or declaring a region differently: the one the
  host would refuse is marked BLOCKED, so Play asks first and names the reason. The host stays the final word; other clash kinds
  (events, tune keys, music replaces) are not covered.
- **Host: bloom at a render scale (Vulkan only; takedawn issue 78):** a scaled frame read by a smaller target goes through a copy reduced
  to the game's size, so a small bright spot no longer glows or misses by where it falls. 1x and the Metal / D3D11 backends are unchanged.
  Switches: CMake `BO3_RT_SHRINK_NATIVE=OFF`, at run time `RECOMP_DEBUG=rt_shrink=0`.
- **Host: redundant Mods rows removed** (the pause menu's MOD SETTINGS and Settings > MODS while the overlay is there; the overlay pages
  stay; without an overlay the MODS line stays). `BO3_HOOKREQ_P22M=ON` restores both.
- **Host: custom music.** The EA GAMES TRAX banner shows the tags of a song from your folder (title, artist, album from ID3 / flac / ogg
  tags; m4a and wav are not read). New setting **MIX WITH EA TRAX** (MOD SETTINGS, BURNOUT MASHUP; **default off**): every
  song of the folder and the 44 EA tracks in one pool. A change of source is a stop + start, no crossfade. `docs/custom-music.md`.
- `host/marks`: 521 marks (3 new). `build/EXPECTED.json`: new reference builds. `build/apply_layers.py`: a new file for xboxrecomp goes
  to `host/toolkit/added/` (byte copy, digest pinned, an existing file is a collision).
- **Tried in the game, briefly, on one PC only:** the banner and the mix were used by a person in short sessions (the mix on a private build with the same
  music code); the bloom fix and the removed rows ran in one session, without a side-by-side check of the picture. Update now and Build Mashup are tested
  offline with a mock channel and stand-ins; no real network install and no person has pressed them. Linux and macOS: not built.

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
