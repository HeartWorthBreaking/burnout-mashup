# Changelog

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
