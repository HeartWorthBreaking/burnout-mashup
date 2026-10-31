# bmashup.settings 1 - bounded plugin settings on the MODS page

Header: `sdk\include\bmashup_settings.h` (`BM_SETTINGS_VERSION 1`). Example: `sdk\examples\camera-fov` (declares one
INT setting and uses `bmashup.camera`).

## What it does
A plugin declares a few BOUNDED settings while the plugins start. The player sees and changes them in the title's own menu:
Driver Details > Settings > MODS > **MOD SETTINGS** (A steps a value, B goes back). Each change is saved at once to
`plugin-settings.toml` (beside the mod list; `BMASHUP_PLUGIN_SETTINGS` moves it, `""` = session only) and handed to the
plugin's callback on the game's thread. The host only keeps values inside the declared bounds; the plugin decides what a
value does.

## Declaring
| Kind | Bounds |
|---|---|
| `BM_SETTING_BOOL` | 0 / 1 |
| `BM_SETTING_INT` | `min..max` step `step`, at most 64 values, within +-1,000,000; `unit` 0..3 characters (e.g. `%`) |
| `BM_SETTING_ENUM` | 2..8 choices, each 1..10 printable ASCII |
Limits: 6 settings per plugin, 32 in all; key 1..24 of `[a-z0-9_]`; label 1..16 printable ASCII (shown upper case). Declare
and `subscribe` (one callback per plugin) only during start-up (`takedawn_plugin_init`, `takedawn_plugin_service`,
`takedawn_plugin_services_done`); afterwards `BM_SETTINGS_CLOSED`. `get` works on any thread.

## Values and callbacks
- The stored value when it fits the declaration, else the default (logged; a stored value is never clamped).
- Callback: once per setting with `BM_SETTING_INITIAL` at the first front-end or stage set-up after start (before any race),
  then `BM_SETTING_CHANGED` after each change (already saved). Keep it short; no declare / subscribe inside it.
- File: `values = ["<mod id>/<key> = <value>", ...]`; other mods' entries are kept.
- Ownership: a setting belongs to the declaring plugin (its mod id is the namespace).

## Host settings (p4.1)
The host's own group appears as **BURNOUT MASHUP** (pseudo mod id `bmashup.host`, which no plugin can hold), e.g. `GARAGE
PAINT 7-8` (`GARAGE_PAINTS.md`). Saved as `bmashup.host/<key> = <value>`.

## Evidence
- **RUNTIME-VALIDATED**: gp_camset1_r1 (page shown, stepped 100 -> 130 %, saved, delivered), gp_p4c_1 (on p4), gp_p41_2 (host
  group + plugin group, toggle saved: `bmashup.host/garage_paints_78 = on (MODS page), saved`).
- OFFLINE-VALIDATED: persistence across a process restart (the file is written; its read-back tested offline); several
  plugins' groups (MODS-page harness).
- Cosmetic (p4.1): the MODS page details read `SETTINGS OF 2 MODS WITH CODE` when the host group and one plugin are present
  (the host group is counted as a mod).

## Evidence update (kit 0.3.1)
**p4.2** (gp_p42_5): GARAGE PAINT 7-8 OFF -> ON saved, CAMERA FOV 100 -> 130 saved and delivered. Persistence across a process
restart: still offline only.
