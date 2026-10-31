# per-player-settings (bmashup.settings 2)

Declares a **PER_PLAYER** ENUM (SPEED UNIT: KMH / MPH, one value for P1 and one for P2) and a GLOBAL BOOL on MODS > MOD SETTINGS,
subscribes with `subscribe2` (the callback gets the player; BM_SETTING_ALL_PLAYERS for a GLOBAL setting) and reads values with
`get_player`. The file keeps `<mod id>/unit#p1` and `#p2`. Split screen is not tested on the platform: P2's value is stored
and delivered only. The MOD SETTINGS page is reached from Driver Details > Settings > MODS (not from the race pause menu: its 7th
slot is not free in every mode). Read only. Needs a platform 0.1.8 host.