# bmashup.settings 2 - per-player settings (platform 0.1.8)

Header: `sdk\include\bmashup_settings.h` (`BM_SETTINGS_VERSION 2`). Example: `sdk\examples\per-player-settings`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); runtime: pending. Player 2's values are stored and
delivered, but split screen is untested on the platform.

## What version 2 adds
- `bm_setting_decl` grows (`BMSDK_SETTING_DECL_V2`): `reserved_v1` (0; ignored - version 1's struct ended in 4 bytes of padding
  on 64-bit builds, so a field there could not be told from an old plugin's padding) then `scope`: `BM_SETTING_SCOPE_GLOBAL` (0)
  or `BM_SETTING_SCOPE_PER_PLAYER`. `scope` is read only when `struct_size` covers it.
- PER_PLAYER: two values, P1 (player 0) and P2 (player 1); file keys `<mod id>/<key>#p1` and `#p2`; v1 `get` answers P1.
- Appended (`BMSDK_SETTINGS_TABLE_V2`): `subscribe2(fn2, user)` - the callback gets the player (GLOBAL settings:
  `BM_SETTING_ALL_PLAYERS`); `get_player(key, player, &value)` (players 0 / 1, else 8 `BAD_SCOPE`). One callback per plugin:
  `subscribe` or `subscribe2` (the other answers `DUPLICATE`); a v1 callback of a PER_PLAYER setting gets P1 only.
- Result code appended: 8 `BAD_SCOPE`.
- Limits for EVERY caller (capacity, not meaning): 8 settings a plugin (was 6), 128 in all (was 32); the settings file keeps 512
  entries (64 KiB).
- MOD SETTINGS page: lines in pages of at most 6; a PER_PLAYER setting shows two lines "LABEL P1" / "LABEL P2", never split over
  two pages. A version 1 plugin (GLOBAL, <= 6) gets exactly the version 1 page.

## Not added: the pause-menu entry (owner decision 7's condition)
The owner allowed MOD SETTINGS in the pause menu's 7th slot **if it is free in every mode**. It is not (shown offline from the
generated code): the race pause object holds at most 7 items; the game builds up to 6 (RESUME, RESTART and an extra line both
conditional, AUDIO, CONTROLLERS, QUIT) and upstream's MASHUP SETTINGS entry takes the 7th whenever the overlay is available;
the other pause layout always has 7 fixed lines. Settings stay on Driver Details > Settings > MODS > MOD SETTINGS; a change
there reaches the plugin's callback at once.

## Evidence
`gp\slices\main18\test_runs\svc_b_t3`: settings v2 38 / 38, 5 / 5 mutants; the camset1 suite 104 / 104, 15 / 15 mutants, MODS page
harness 165 / 165 (pages without settings byte-identical to the reference).
</content>
