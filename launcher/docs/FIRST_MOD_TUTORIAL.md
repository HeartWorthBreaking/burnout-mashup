# Your first Burnout Mashup mod in 10 minutes

You make a small **data mod** with your own values: takedowns give **2500** Burnout points instead of the game's 1000.
No programming, no game files copied, no command line - Notepad and the launcher are enough. Your mod contains only text
you wrote, so you may share it.

Before you start: the quickstart is done (the launcher's Setup tab shows the game data **ready** and the check **PASS**).

## Step 1 - the folder (1 minute)
Create a folder anywhere outside the Burnout Mashup folder, for example `Documents\My Mods\bigger-takedowns`.

## Step 2 - mod.toml with a deliberate mistake (2 minutes)
In that folder create a text file named exactly `mod.toml` (in Notepad: *Save as type: All files*, encoding UTF-8) with:

```toml
id = "me.bigger-takedowns"
name = "Bigger Takedowns"
version = "1.0.0"
description = "Takedowns give 2500 Burnout points instead of 1000."

[bmashup]
platform = ">=0.1.9"
requires = ["bmashup.tune>=1"]

[bmashup.tune]
version = 1
sett = ["Score/Burnout Points | Takedown BP = 2500"]
```

What the lines mean:
- `id` - a unique name: lower-case letters, digits and `. _ -`; start it with something of yours (`me.`).
- `[bmashup] platform / requires` - which Burnout Mashup host the mod needs; the launcher checks this for you.
- `[bmashup.tune]` - game values to change; each entry is `"Group | Name = value"` from the tuning catalogue
  (`docs\TUNING_CATALOGUE.md` in this package: every key, its type and the game's value).

The last line has a typo on purpose: `sett` instead of `set`.

## Step 3 - import and read the verdict (2 minutes)
Launcher -> **Mods** tab -> *Import folder...* -> choose your folder (or drop the folder on the window).
The preview shows your mod's name and files and the verdict:

> Compatibility: **BLOCKED**
> - [bmashup.tune] keys this host does not take (a typo?): sett

(The Mods tab shows a BLOCKED mod the same way - red, with the reason under the list: `images/2_mods.png`.)
Nothing has been copied yet. Answer **No**. (The game itself would refuse the mod at start for the same reason: the
launcher tells you before you play.)

## Step 4 - fix it (1 minute)
In Notepad change `sett` to `set`, save, and import again. Now the preview says **OK**; answer **Yes**. The mod is copied
into the Burnout Mashup folder (`mods\user\me.bigger-takedowns`) and appears in the list as **on**.
Importing it again later (after more changes) asks whether to **replace** it; the previous copy is kept in `mods\.backup\`.

## Step 5 - play and check (4 minutes)
**Play** tab -> *Play*. Start any race and take an opponent down: the takedown is worth 2500 points.
After you quit, the Play tab shows the results:

> Mods loaded: ...   admitted: ...
>   loaded me.bigger-takedowns 1.0.0
> No FATAL line.

The full log (`profile\Roaming\BurnoutMashup\logs\run.log`) has the line
`[TUNE] "Score/Burnout Points | Takedown BP" = 2500: set`.

## If something is not as described
- **BLOCKED: needs platform ...** - your host is older than the mod asks for: use the host shipped with this package or
  lower `platform`.
- **not valid TOML** - a quote or bracket is missing; the message names the line.
- **The mod is not in the list** - it must be a folder with `mod.toml` directly inside (not `mod.toml.txt`: in Explorer turn on
  *View > File name extensions*).
- To turn the mod off: select it, *Turn on / off* (or Space). To remove it: delete its folder in `mods\user`.

## Next steps
- More values: `docs\TUNING_CATALOGUE.md` lists every `Group | Name` with its game value and the limits.
- Plugins (C code), cars and tracks: the developer kit and the Workbench (developer documentation).
