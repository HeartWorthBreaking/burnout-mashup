# [bmashup.world_tour] version 1 - a fourth World Tour region (EXPERIMENTAL, platform 0.1.5)

A data mod can give one of its declared regions (`[bmashup.regions]`) a place in the World Tour: a fourth entry on the
region page, a map page with one location, and that location's events (`[bmashup.extra_events]`).

```toml
[bmashup]
requires = ["bmashup.world_tour>=1"]      # an older host refuses the mod as a whole (fail closed)

[bmashup.tracks]
version = 1
add = ["OC_C1_V1"]

[bmashup.regions]
version = 1
add = ["O = OCEANIA"]

[bmashup.world_tour]
version = 1
region = "O"          # a letter of [bmashup.regions] (any mod of the set); the entry shows the region's text
map = "USA"           # USA | EUROPE | ASIA: the retail map the region borrows
location = "OC_L1"    # the region's one location: 5 characters, the region letter first ("O?_XN"), not US / EU / AS

[bmashup.extra_events]
version = 2
add = ["oc-race = OC_C1_V1 @ OC_L1"]       # tracks of the region (first letter O); at most 6 events at the location
stage = ["oc-race = 020006USC1V1"]         # recommended: a retail race on the track's geometry donor
```

## What the player sees (phase 1)
- Region page: USA, EUROPE, ASIA and the region's name; the cursor wraps over the four. The globe turns to the borrowed
  map's view (the globe's tables hold three regions).
- Map page: the borrowed map (its textures, its first marker and that marker's place name), ONE location, whose list holds
  only the mod's events (never the borrowed location's retail events). The rest of the borrowed map is not shown.
- An event races and finishes as any added World Tour event (sidecar medal, no save write); the race returns to the
  fourth region's map.
- Cosmetic, not changed in phase 1: the place name on the marker / list title and the region page's event counts are the
  borrowed map's.

## Borrowed assets (phase 1 - read before you ship a region)
The fourth region has NO art or texts of its own except its name on the region page and its events' names / help. Everything
else is the borrowed map's (`map = "USA"` in the example), and the player SEES it (runtime gp_wt4_1 / gp_wt4_4):
| What | Shown for the fourth region |
|---|---|
| Map page art (satellite tiles, title / overlay textures) | the borrowed map's (USA) |
| Location marker, its place name, the list title | the borrowed map's first location (USA: "SILVER LAKE") |
| Map ticker | the borrowed map's ("WELCOME TO THE USA... PLEASE SELECT A LOCATION") - **"USA" text is visible** |
| Region page globe view and event counters | the borrowed region's view and counters (USA "0/55") |
| Location panel | "2 EVENTS AVAILABLE" = the region's own events; the gold counter is the game's (gold medals only) |
| Region name on the region page, event row names, event help bar | the mod's own (OCEANIA, "Oceania Sprint", its help) |
Known limitation, not a defect: a player can tell the fourth region is drawn with the USA map. Own art needs the untraced
texture loader (a host-loaded .txd), own place names a names redirect - both later phases.

## Rules (a refusal stops the start with exit 92 and names the mod and the reason)
- `version = 1`; keys `version region map location` only.
- One fourth region in all mods (a second `[bmashup.world_tour]` is refused).
- `region` must be a region some mod declares in `[bmashup.regions]`.
- An event at a location that is neither a retail race location nor the declared one is refused.
- The event's track must be a track a mod adds whose first letter is the region's.

## Fail closed
- No `[bmashup.world_tour]`: the World Tour is retail (three regions), whatever `[bmashup.regions]` declares.
- The region is shown only while its declaration resolved, at least one of its events is installed and its text resolves
  in the game's text table; otherwise the region page stays retail and the log says why (`[WT4] ... is not shown`).
- A host without this table (platform < 0.1.5) refuses the mod at the platform gate ("needs a newer platform").

## How (engine notes)
The menu's region field stays 0..2 (the borrowed map's index); a host flag marks the fourth region. 31 generated lines:
region page (entries relocated to a host block, cursor wrap 4, availability, globe = borrowed view), map page (location count
1, retail events of the borrowed location suppressed, focus, marker), and a guard on the eight SatMap index-table reads
(a region > 2 is bounded to the borrowed map: the retail read for 3 is a wild read). See `gp\atlas\WORLDTOUR.md` s6.
