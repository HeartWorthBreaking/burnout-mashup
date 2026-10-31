# damage-panels (bmashup.patch 2)

Sets every car part kind 0..6 to be **counted and detached** by the game's per-frame part damage loop (shipped: kinds 2 and 4 only),
through the bmashup.patch v2 TABLE sites `game.damage.panel_count.<k>` / `game.damage.panel_detach.<k>` and
`request_site_pair` (count and detach as one unit). Values are 0 / 1 only; anything else is OUT_OF_BOUNDS.

- Needs a platform 0.1.8 host (bmashup.patch 2). The host verifies the two switch index tables against the running build at start;
  on another build the sites are unverified and nothing is written.
- **Process-wide**: every mode that runs the damage loop sees it. Which modes run it, and the in-game look, are NOT runtime-verified.
- Changes the game (a gameplay label): do not use it for records.