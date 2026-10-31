# `[bmashup.wt_map_art] version 1` - own map art and texts for the 4th World Tour region (platform 0.1.6)

Data only. Works with `[bmashup.world_tour]` (`WORLD_TOUR.md`) and `[bmashup.textures]` (`TEXTURES.md`). Example:
`examples\authored\fetex-art\fetex-oceania-art` (requires the region mod `bmashup.wt4-oceania`, made by
`examples\content\wt-region\make_wt_region.py` from your own data).

```toml
[bmashup]
platform = ">=0.1.6"
requires = ["bmashup.textures>=1", "bmashup.wt_map_art>=1"]
requires_mods = ["bmashup.wt4-oceania"]

[bmashup.textures]
version = 1
txd = "art/oceania.txd"
class = "frontend"

[bmashup.wt_map_art]
version = 1
region = "O"                                   # the one 4th region (as [bmashup.world_tour])
art = ["SatMapU1_1 = oceania_tile_1_1", "USA1 = oceania_overview", "RaceIcon = oceania_marker"]   # <retail slot> = <texture>
place = "Harbour City"                         # 1..17 characters: the location's place name
ticker = "WELCOME TO OCEANIA...    PLEASE SELECT A LOCATION"     # 1..60 characters
```
- `art` slots: the donor map's satellite tiles / overview / area / city layers (USA1, US_LSat, SatMapU_L1..L4, SatMapU1_1..U3_2
  and the EU / ASIA equivalents) and the markers (RaceIcon / RacePulse / RaceHollow, Crash*, GP*, StartFlag). Each bound texture
  must have the same format AND size as the retail slot texture (checked at admission against the pinned retail table, and at
  first use against the live texture: a mismatch keeps retail for that slot, counted).
- Bindings act ONLY while the 4th-region map page is shown: the donor's own map stays retail.
- Texts go through bm_names' host text table (IDs `BO3_NM_MAP_BASE` + 0 / 1 = 0x1D1C / 0x1D1D since p4.3: after the series
  titles, the R1 merge fix).

## Evidence and limits
- RUNTIME-VALIDATED: gp_fetex1_2 (fetex1 build) and gp_p43_2 (combined p4.3): AUTHORED map art, a teal marker, "HARBOUR CITY",
  the ticker; Oceania Night raced (gold), map counter 1/2.
- Still BORROWED (labelled): the region PAGE globe view and its counters (wt4 marks needed), the donor map's route outline.
- Not tried at runtime: a language switch (texts re-installed offline), two texture mods clashing for one slot (offline).
