# Versions in the Burnout Mashup mod kit 0.7.0 - which number means what

**The host's platform version (0.1.9) and the mod-kit release (0.6.0) are DIFFERENT VERSION DOMAINS.** A mod that says
`platform = ">=0.4"` is refused by this host (platform 0.1.9).

| domain | current value | where | changes when |
|---|---|---|---|
| **platform version** | **0.1.9** | boot line `[PLATFORM] Burnout Mashup platform 0.1.9`, `bmashup.host` | the mod-facing surface changes |
| **host build identity** | `bmp-0.1.9+2c8142e65f20` (main21; capfix1 was `bmp-0.1.6+0c5a321ae0fa`, clean1 `bmp-0.1.6+345dc71c5cd3`, p4.4 `bmp-0.1.6+ab3a98869d10`) | boot line, `bmashup.host` `build` | any host source change |
| **host name** | main21 (`burnout3_gp_main21.exe` in the project; your own build: `burnout3_bmashup.exe`, same bytes) | workspace label | a new candidate / freeze |
| **mod-kit release** | **0.6.0** | this package | any change; a new reference host always means a new kit release |
| **SDK package** | **0.6.0** | `sdk\` | plugin headers change |
| **service ABI versions** | 25 services; the version of each service: `docs\services\README.md` and the `BM_*_VERSION` macros of its header | per service | a table grows |
| **mod.toml table versions** | `capacity` 1, `tune` 2, `regions` 1, `tracks` 1, `extra_events` 2, `music` 1, **`cars` 2**, `world_tour` 1, **`series` 1**, **`paints` 1**, **`textures` 1**, **`wt_map_art` 1** | the host's readers | a reader takes new keys |
| **mod.toml size** | **65536 bytes** (0.1.6; 8192 before) | the manifest reader | a platform decision |
| **tools** | bmpack 1.5.0, bmdiag 0.1.0, bmkit_doctor 0.1.0, kit_selftest 0.1.0, trackbuild 0.2.1, carimport 0.1.1, fetex 0.2.0, vehtool 0.1.2 (trackconv: not shipped in 0.4.1 - 0.6.0) | each tool | the tool changes |

## Platform steps
0.1.1 (p3) -> 0.1.2 (`requires_mods`; events 6 + crash) -> 0.1.3 (p4: seven gp slices) -> 0.1.4 (p4.1: music, tune 2, paints 7 / 8)
-> 0.1.5 (p4.2: `[bmashup.cars]` 1, `[bmashup.world_tour]` 1) -> **0.1.6** (p4.3: `[bmashup.textures]` 1, `[bmashup.wt_map_art]` 1,
`[bmashup.cars]` 2 incl. `photos`, `[bmashup.series]` 1, `[bmashup.paints]` 1, mod.toml 65536 B; no plugin ABI change).
A mod that needs a 0.1.6 table says `platform = ">=0.1.6"` (or names the table in `requires`); older hosts refuse it alone.

## Platform 0.1.7 (mod kit 0.4.4)
0.1.6 -> **0.1.7** (host capmega1, mod kit 0.4.4): `[bmashup.capacity]` takes `gamedata_bytes` (table version unchanged, 1); the mesh row extension
(BMRX) is read from track data (no key). No service, plugin ABI or SDK header change (SDK 0.4.2). A mod that uses
`gamedata_bytes` says `platform = ">=0.1.7"`.

## Platforms 0.1.8 and 0.1.9 (mod kits 0.5.0 and 0.6.0)
0.1.7 -> 0.1.8 (main18, mod kit 0.5.0): the mod limits and hook request phase 1 (`docs\CHANGELOG.md`). 0.1.8 -> **0.1.9** (main21, mod kit 0.7.0): the 256 MB guest window and hook request phases 2 and 3 (25 services; append-only service ABI growth, `sdk\CHANGELOG.md`; SDK 0.6.0). A mod that needs a 0.1.9 feature says `platform = ">=0.1.9"` (bmpack 1.5.0 accepts it; older hosts refuse the mod alone).
