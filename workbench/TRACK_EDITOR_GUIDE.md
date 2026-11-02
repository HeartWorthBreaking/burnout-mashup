# Track editor guide - make your own track, step by step

This guide is for everyone, no programming needed. It shows how to start the track editor, find your way around it and turn a
starter track into your own. The full reference (every tool, every limit) is `TRACK_EDITOR_AUTHORING.md` in the same folder.

> **Experimental.** The track editor is new. Tracks made with it build and pass the kit's checks, but nobody has raced one in the
> game yet. Expect rough edges, save often, and keep copies of tracks you like.

## What you need
- Burnout Mashup 0.2.0-alpha.2 or newer, unpacked and set up (your game copy made, see the Quickstart).
- Edge, Chrome or Firefox. The editor is a web page that runs on your own PC only. Nothing goes on the internet.

## 1. Start: make a track project (2 minutes)
A *track project* is a folder that holds your track's sources: its shape (a 3D model), its textures and a description file.

1. Start **Burnout Mashup Workbench.exe**.
2. Open the **New track project** tab.
3. Fill in the fields:
   - **Project folder**: click *Browse...* and choose a new, empty folder, for example `Documents\My Tracks\first-track`.
   - **Template**: what your track starts from. `testloop` is a small flat loop (the safest choice), `canyon` the bigger Canyon Ring,
     `hill` a loop with a hill. If a template is refused, use `testloop`.
   - **Mod id**: your name plus the track's, with a dot, for example `alex.first-track`.
   - **Track id**: a code like `EU_T7_V1`. It starts with `EU`, `US` or `AS`, then two letters or digits, then `_V` and a digit.
     It must not be one of the game's own tracks; the *Check* button tells you.
   - **Track name** (up to 27 characters) and **Track location** (up to 17), as the game will show them.
4. Click **Check**. When it says OK, click **Create track project**.

## 2. Open the editor
Click **Open in track editor...** on the same tab.

- It opens the project you just created. If you didn't create one this time, it opens the folder in *Project folder* when that
  is a track project, otherwise it asks you to pick one.
- After a few seconds your web browser shows the editor.
- A black window titled **Burnout Mashup track editor** appears as well. Leave it open: it *is* the editor. Closing it stops the
  editor. If the browser page didn't appear, the window shows the address to open.
- If that window says something went wrong and "Press any key", read the message: usually the folder is not a track project.

## 3. Find your way around
The page has two parts: the **3D view** on the left and the **tool panel** on the right (scroll it down to see everything).

| To do this | Do this |
|---|---|
| turn the camera around the track | drag with the left mouse button |
| slide the camera sideways | drag with the right mouse button (or Shift + drag) |
| zoom in and out | mouse wheel |
| fly around | W A S D to move, Q and E for down and up |
| select something | click it; Ctrl + click adds or removes more pieces |
| jump the camera to what you selected | F |
| undo / redo | Ctrl + Z / Ctrl + Y |
| save | Ctrl + S |
| show all shortcuts | the **? Help** button, or the ? key |

The tick boxes under **Layers** show extra information on top of the track: the route (the racing line), the start grid,
collision (green floor, red walls), the wireframe and more. They only change what you see, never the track.

Colours in the view are a preview: there is no sky, fog or lighting yet, so the game will look different.

## 4. The golden rule: Preview, then Apply
Every tool works the same way:

1. Fill in its fields (many have a **Click points** or **Pick** button, so you can click on the track instead of typing numbers).
2. Click **Preview**. You see what would change. **Nothing has changed yet.**
3. Happy with it? Click **Apply**. One Apply is one undo step.
4. If the tool says no, it tells you why and nothing changes.

Then **Save** (the Save button near the bottom of the panel, or Ctrl + S). Each save keeps a backup of the previous one, so you can
always go back (tool *Restore a backup into the editor*, group **Project / test**).

Many tools have a **Preset** list at the top (for example *Garage, 6 m door* or *Two-lane country road*): pick one and it fills the
fields with sensible values you can still change. Lengths are metres, angles degrees.

## 5. Your first own track (about 15 minutes)
The editing tools are in the panel's **Authoring tools** section, grouped by task: **Race layout, Roads, Terrain, Buildings /
scenery, Materials, Mesh, Streaming, Inspect, Project / test**. Click a tool's title to open it; each group's **Guide** button
shows the matching part of this guide in the page. The search box finds a tool by name.

**The quick way:** the **First track walkthrough** at the top of the panel lists the steps below, ticks the ones your project
already has, and opens the right tool with **Open tool**. **Even quicker:** group *Project / test* -> *Starter project* ->
`town_circuit` (a flat circuit with a garage you can drive through, houses and trees) or `hill_country` (a sloped circuit with a
hill and a barn). It replaces the track with the starter in one undo step; everything in it stays editable.

1. **Draw the race route** - tool *Race layout with profile* (group Race layout). Click points around the track to make a closed loop. Keep the
   area around the first point flat: that's where the start grid goes. Preview, look, Apply (choose to replace *all* the first
   time).
2. **Make room** - the Construct section's *Unit regions*. Everything you build must lie inside a region. If a tool says
   something is outside, make the region bigger here first.
3. **Add ground** - group Terrain: *Height terrain* makes a ground grid; *Terrain brush* raises, lowers, flattens or smooths it
   where you click (presets: gentle hill, smooth, dip, flatten). One brush stroke is one undo step.
4. **Add roads** - group Roads: *Profiled road* draws an extra road, *Junction piece* a T, Y or crossing, and *Join two road ends*
   connects them. *Open road ends* lists the loose ends you can join.
5. **Add buildings and trees** - group Buildings / scenery: *Building generator* - click the corners of the footprint, pick a
   preset (garage, house, barn, tower, walled yard), Preview, Apply. Door openings are real gaps you can drive through (put
   ground inside). *Low-poly tree* adds a tree where you click. You can also save pieces as a prefab and place copies with *Place
   a prefab copy* or *Repeat a prefab along a path*.
6. **Give it a look** - group Materials: *Import an original texture* takes a PNG picture **you made yourself**; *New / duplicate
   material* makes a material from it; select faces and assign it; *UV* scales or turns the texture, *Paint vertex colour* darkens or
   lightens areas.
7. **Fix problems** - group Inspect: *Diagnostics* lists what's wrong; click a line to see where it is. Each problem says **how
   to fix it** and has an **Open tool** button. The Mesh tools fix single faces or corners by hand.
8. **Check the size** - group Streaming: *Streaming / LOD / visibility report* shows whether each part fits the game's memory.
   With **Capacity: auto** (the default; *LOD / visibility / capacity settings*) a part may be bigger than the game's default
   slot: the report shows it as INFO with the size it declares and the host it needs (some values need a Burnout Mashup host
   with patch 131 or later); Build writes that into the mod's mod.toml. Choose **Capacity: game** for a track that must run on
   a host without capacity declarations (then anything above the game's sizes is refused).
9. **Save.** After many terrain strokes or edits, *Compact the OBJ* (group Project / test) makes the file smaller without changing
   the track.

## 6. Build it and try it in the game
1. Save, then group *Project / test* -> **Build, validate, stage + prepare test** -> **Run**. It turns your sources into game files,
   runs all the checks and writes a test plan, each time into a new folder (by default `test builds` next to your project; keep the
   path short - Windows paths are limited to 260 characters and the tool tells you when a folder is too deep). If a check fails it
   says which and how to fix it, and your last good build stays where it was. (The older **Build / Validate / Stage** box still
   works too.)
2. Start **Burnout Mashup.exe**, open the **Mods** tab, click **Import folder...** and choose the folder named after your mod id
   inside the staging folder (for example `staged\alex.first-track`). When the preview says OK, answer Yes.
3. **Play**, and look for your track by its name and location.

The test plan (`TEST_PLAN.md` in the build's `test_plan` folder) lists what to try while you drive (start, laps, AI, walls). If the game stops with an
error, turn your track off in the Mods tab and see the Troubleshooting page.

**Don't share the built game files.** A built track borrows a few parts (its sky, sounds and race events) from your own copy of
the game, so it is for your PC only. To share your work, use *Shareable export* (group Project / test): Preview shows every file
with where it came from and its licence, and what is left out (game files always; files the editor can't vouch for unless you
state their author and licence). The zip has a SHARING.md explaining what the receiver needs. Someone else opens it with *Import a
source zip as a NEW project* and builds it with their own game.

## 7. Stop the editor
1. **Save** (unsaved changes are lost when the editor stops).
2. Close the browser tab.
3. Close the **Burnout Mashup track editor** window (or press Ctrl + C in it).

To continue later: Workbench, **New track project** tab, put your project folder in *Project folder* (or just leave it empty and
pick it), then **Open in track editor...**.

## Good to know
- **Undo** goes back one Apply at a time, as far as you like, while the editor is open. After you close the editor, use the backups
  (*Backups of this project*, then *Restore a backup into the editor*). Old backups are kept until you choose otherwise with
  *Backup retention* (it shows what it would delete and asks you to confirm).
- **Not possible yet:** sky, fog and lighting changes, see-through materials (no windows / glass, no see-through leaves), real props
  (buildings, trees and placed objects are copies of the track model), point-to-point races, and AI or traffic using side roads
  (side roads are drivable, but the AI only follows the main route). The race route can only lean (bank) a tiny bit; extra roads
  can bank freely.
- **Only your own work:** textures and models must be made by you, or be under a licence that allows it. Never put game files or
  pictures taken from the game into a project you share.
- **Command line** (for experts): `py -3 -B app\workbench\wb_trackedit.py "<project folder>"` from the Burnout Mashup folder;
  `--retail "<game data>\Tracks\EU\M1_V1"` opens one of the game's tracks to look at (read only).

## When something goes wrong
| What you see | What to do |
|---|---|
| "is not a track project" | pick the folder you chose when you created the project (it contains `workbench-track.json`) |
| the browser page doesn't appear | copy the address from the *Burnout Mashup track editor* window into your browser |
| a tool refuses with a message | read it: usually something lies outside a unit region, overlaps a floor, or the route isn't flat at the start |
| Build -> Validate -> Stage fails | save first; then fix the first problem it lists (tool *8 Diagnostics* helps) and try again |
| the editor window closed by itself | open it again with *Open in track editor...*; everything up to your last Save is kept |
