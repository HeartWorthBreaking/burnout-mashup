# `[bmashup.world_tour] version 1` - a fourth World Tour region on a BORROWED map (platform 0.1.5, phase 1)

Data only, no approval. Host page: `host\bmashup-world-tour.md` (p4.2's own, byte copy). Example: `examples\content\wt-region`
(`make_wt_region.py` builds the placeholder track from your own data; the kit ships none).

## Declaration (with the tables it works with)
```toml
[bmashup]
requires = ["bmashup.world_tour>=1"]
[bmashup.tracks]
version = 1
add = ["OC_C1_V1"]
[bmashup.regions]
version = 1
add = ["O = OCEANIA"]
[bmashup.world_tour]
version = 1
region = "O"          # a letter of [bmashup.regions]
map = "USA"           # USA | EUROPE | ASIA: the retail map the region BORROWS
location = "OC_L1"    # its one location: 5 characters, the region letter first
[bmashup.extra_events]
version = 2
add = ["oc-night = OC_C1_V1 @ OC_L1"]     # at most 6 events at the location; tracks of the region
stage = ["oc-night = 020006USC1V1"]       # recommended: a retail race on the track's geometry donor
```
One fourth region in all mods; refusals stop the start with exit 92 naming the mod (rules: the host page). Fail closed: no
declaration, an unresolved region / text, or no installed event -> the World Tour stays retail and the log says why.

## Borrowed assets - LABELLED, read before you ship a region
The region has NO art or texts of its own except its name on the region page and its events' names / help. The player SEES the
borrowed map's: map art, first marker and its place name ("SILVER LAKE"), the ticker ("WELCOME TO THE USA... PLEASE SELECT A
LOCATION"), the globe view and the USA counters (0/55, 0/173); OPEN hypothesis: the OCEANIA map's location counter reads "0/2" after a silver
(gp_p42_8; "1/2" after a gold in gp_wt4_5), probably the borrowed USA counters. Own art needs an untraced texture loader (a later phase).

## Evidence
- **RUNTIME-VALIDATED** on the wt4 build (gp_wt4_1 / 4 / 5: navigation both ways, both events listed with names / help and
  raced, silver / gold medals in the sidecar and the list, persistence across a restart on a copied save, a retail race and the
  retail progress unaffected, 0 added IDs in the save; gp_wt4_2: mod off -> retail region page) and **on p4.2** (gp_p42_7: OCEANIA
  reached, Oceania Night raced, silver medal recorded, sidecar holds the track + event records, Profile 1 saved, save scan 0).
- **Region-page navigation - documented behaviour, not a defect.** The page reads the d-pad as HELD (level) input, once per 0.25 s
  globe spin: a press held longer than one spin steps twice. With only USA and OCEANIA open (EUROPE / FAR EAST locked on a fresh
  profile) two steps land back on the start entry, which earlier records called "lost presses" (wt4 post-race, gp_p42_6 /
  gp_p42_7). Run gp_wt4_6 (log-only trace): 300 ms presses -> 2 moves each; 100 ms presses -> exactly 1 move each. This is the
  retail hold-to-repeat, made visible by the 4th entry; a player tapping the d-pad gets one step per tap. **Scripting rule: use
  presses of 100 ms or less.** No wrong region was ever entered. (`gp\slices\wt4\WT4_NAV_REPORT.md`.)
- **p4.2 gp_p42_8 (RUNTIME-VALIDATED):** with the added-car mod also loaded and 100 ms presses: right moved USA -> OCEANIA in one
  press, left back after the race; Oceania Sprint raced with the added car (2nd / silver, `medal 2 recorded`), sidecar holds the
  track + event records, retail save 0 added IDs.
- Not run: more than one location; other borrowed maps.

- **Tool limitation (kit 0.3.1): `bmpack validate` (1.3.1) REFUSES a `[bmashup.world_tour]` mod** with "OC_L1 is not a race location ..." -
  its checker does not register the declared location. The host accepts and races the same mod (gp_p42_7). Validate such a mod in
  the game (log `[WT4]` lines) until bmpack learns the table; keep it in its own mods folder when you validate the others.
