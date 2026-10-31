# Example (i): World Tour events with their own row names and help texts (platform 0.1.1)

`mod.toml` is a DATA-ONLY template (no plugin, no approval) for the `[bmashup.extra_events]` **version 2** keys that
platform 0.1.1 (host p3, `burnout3_bmp_p3.exe`) added:

| key | what the player sees | limits (measured from the game's own texts) | default |
|---|---|---|---|
| `names = ["<event id> = <text>"]` | the event's row in the location's event list | 1..19 characters, `A-Z a-z 0-9 space - ' . &` | the track's name |
| `help = ["<event id> = <text>"]` | the help bar under the list while the row is selected | 1..97 characters, the same set plus `!`; stored and shown in UPPER CASE | `AN EVENT ADDED BY A MOD.` |

Rules: every id named must be in `add`; one name and one help text per event at most; `names` / `help` need
`version = 2` (at version 1 they are unknown keys and the mod is refused alone).

It declares `[bmashup] platform = ">=0.1.1"` and `requires = ["bmashup.tracks>=1", "bmashup.extra_events>=2"]`:

- on platform 0.1.1 (p3) it is read (offline: the kit verification runs it through the real p3 readers and gate, and
  through eight refused variants: a 24-character name, a 102-character help, a character outside the set, an id not in
  `add`, names at version 1, version 3, `platform >=0.1.2`, `extra_events>=3`);
- on platform 0.1.0 (p2) the mod is refused ALONE with `[PLATFORM] mod example.events-v2 0.3.0 refused, the game starts
  without it: needs a newer platform: [bmashup.extra_events] version 2; platform 0.1.0 reads version 1 (this host: Burnout
  Mashup platform 0.1.0)` and the game starts without it (offline: the real p2 gate and kit 0.1.0's bmpack 1.1 give this
  exact text; the table version is checked before the `platform` bound, so that is the reason named).

It is a template: it declares track `US_C9_V1` without its files. To make it a real mod, put your own track files in
`files\Tracks\US\C9_V1\` (`Gamedata.bgd`, `static.dat`, `streamed.dat`, `enviro.dat`), or build the equivalent pack with
bmpack 1.2 from a spec with `[[event]] name / help` (the kit's `examples\mods\events-pack\`, which was launched on p3:
Silver Lake listed "Harbour Night" / "Harbour Sprint", each with its own help text - launch bmp_p3_1).
