# Example (d): engine capacity - declaration (no code) or plugin requests

> **T1 fixed in host capfix1 / trackbuild 0.2.1; rebuild tracks made with trackbuild <= 0.2.0.** The race-start crash seen in
> the alpha RC (this plugin with the example content) was not the plugin's fault: tracks built by trackbuild <= 0.2.0 carry an
> out-of-set chevron index that the game reads relative to the STATIC pool; with a relocated pool (this plugin's STATIC request)
> the read lands on unrelated data. trackbuild 0.2.1 writes "no chevron" (mesh +0x7D = -1, gate V10) and host capfix1 skips any
> chevron index outside the track's set. Expanded lanes (more than 64) remain U5 (EXPERIMENTAL) as before.
>
> **Kit 0.4.4 / host capmega1 (platform 0.1.7)**: the chevron guard is kept; a data mod can also ask for a larger GAMEDATA
> slot with `[bmashup.capacity] gamedata_bytes` (declaration only; `docs\services\CAPACITY.md`).

Two ways to raise an engine limit for a mod's tracks. Both end in the same host services (**bmashup.engine** for AI
route lanes, **bmashup.streaming** for low-detail unit slots and, version 2, the STATIC track pool), with the same checks;
each capacity is the LARGEST accepted request (any mix, any order) and is fixed once the plugins have started.

| field | mod.toml `[bmashup.capacity]` | plugin call | range |
|---|---|---|---|
| AI route lanes (total) | `lanes` | `bm_engine_api.request_lanes` | 1..255 (the game has 64) |
| low-detail unit slot | `low_unit_bytes` | `bm_streaming_api.request_low_unit_bytes` | 4 KiB multiple, 0x18000..0x30000 |
| STATIC pool | `static_bytes` | `bm_streaming_api.request_static_bytes` (v2) | 4 KiB multiple, above 0xA00000, at most 0x20C4000 |

## declaration-only/ (preferred)
`mod.toml` with `[bmashup.capacity] version = 1` (G8-MCAP). No plugin, nothing to approve. The host requests each value for
the mod before the plugins start; a requirement it cannot meet stops the start with **exit 91** naming the mod and the field
(a VALUE out of range is caught there, not by the reader). Plain Takedawn ignores the table. The track files themselves
are not included (see `../content-template/README.md`).

## plugin/
`bm_sdk_capacity.c` asks for 80 lanes, 0x1A000 low slots and a 0xD01000 STATIC pool while the host starts it, logs each
answer, and once a race runs (first player-car update in the racing phase, **bmashup.events**, optional) logs what the
track actually got. Every service is optional: without one it says so (`bmsdk_report`) and assumes nothing. Adapted from
the G8 demos `bm_capacity_demo.c`, `bm_lanes_demo.c` (L5a runtime: 80 lanes) and `bm_static_demo.c` (L9).
Other values: `-DBMSDK_CAPACITY_DEFINES="CAP_LANES=100u;CAP_LOW_BYTES=0u;CAP_STATIC_BYTES=0u"` (0 = do not ask).

```
[CAPACITY] mod example.capacity-declaration requires 96 total lanes: accepted (merged 96)
[PLUGIN bmashup-sdk.capacity] capacity: asked for total AI lanes 0x50 (80): accepted 0; merged so far 0x60
[ENGINE] lane capacity frozen: 96 total (32 extension entries), ...
```

Memory is taken later, where it was before (lanes at a track's load, slots / STATIC at the game's memory set-up); if it
cannot be had, the game's capacity stays and the content guards stop oversized content (exit 88 / 89 / 90).

Offline evidence: `verify_sdk.py` scenarios `capacity_decl` (declaration 96 + plugin 80 -> 96 / 0x1A000 / 0xD01000 frozen,
a late request CLOSED) and `capacity_plugin` (80), through the real declarations reader, services and extensions.
