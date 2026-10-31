# Your game data: which version, how to prepare it, how to check it (mod kit 0.4.1)

The kit ships **no game data and no game code**. Tools that build on retail parts (donor tracks for `bmpack build`, donor car
parts for `carimport`, the retail vehicle list for `vehtool`, the host's text table and track list for `bmpack validate`, the
content examples in `examples\content\`) read **your own** prepared copy of the game, read only, from a folder you name.

## Which version
Only **Burnout 3: Takedown, North America (NTSC-U) retail disc for the original Xbox** - the one version Takedawn supports. It is
recognised by the SHA-256 of its `default.xbe`:

    9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9

PAL, Japanese, other regions and patched files are refused by the tools (exit 3, both hashes shown), as Takedawn refuses them.

## Supported preparation (the same as Takedawn's own setup)
1. Make a copy of your own disc: an `.iso` in XISO layout, a full disc image, or a folder with the extracted files. The kit
   and its authors do not provide disc images or game files and do not link to them.
2. Install Takedawn (the Windows setup program from the Takedawn releases page; the Burnout Mashup host is built from Takedawn
   0.2.0) and start it once. Its setup window takes your image or folder, checks that it is the right game and version, copies
   the data and checks every one of the 716 files against known sizes and SHA-256 sums. By default the data goes to
   `%LOCALAPPDATA%\BurnoutMashup\Game`; with Change... you can pick another folder. The alpha tester bundle can do the same with
   `prepare.cmd data ...` into its own `gamedata\` folder (see its INSTALL guide).
3. The folder the kit tools need is the one that holds `default.xbe`, `Data\`, `Tracks\`, `pveh\`: in a Takedawn data folder
   that is the subfolder **`Burnout 3 Takedown`**, for example `%LOCALAPPDATA%\BurnoutMashup\Game\Burnout 3 Takedown` or
   `<tester bundle>\gamedata\Burnout 3 Takedown`. (Given the parent, the tools tell you to add `Burnout 3 Takedown`.)

Never point a tool at the only copy of your saves, and never let anything write into the game-data folder: the kit tools only
read it, and their outputs go to the NEW folders you name.

## Telling the tools where it is (first match wins)
1. the tool's option `--game-data "<folder>"`;
2. the environment variable `BMKIT_GAME_DATA`;
3. `game_data = '<folder>'` under `[paths]` in the kit configuration file: `BMKIT_CONFIG=<file>`, else `<kit>\bmkit.toml`
   (copy `bmkit.example.toml`).
There is no default location: if none is given, the tool stops and says so (exit 3).

## Checking it
    py -3 -B tools\bmkit_doctor.py --for tools --game-data "<folder>"
prints `OK game data (NTSC-U)` when `default.xbe` has the hash above and the files the tools read are present
(`Tracks\tlist.bin`, `Data\PrgData.bin`, `pveh\vlist.bin`); otherwise it names what is wrong and what to do. Takedawn's own
`takedawn --data-status` reports whether its data is whole.

## What stays local
Anything a tool builds from donor parts contains retail bytes (labelled DONOR / DERIVED in the outputs): keep it on your machine,
never upload or share it. AUTHORED parts (your own models, textures, track geometry, mod.toml) are yours to share.
