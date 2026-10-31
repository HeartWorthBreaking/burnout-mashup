# Example (g): a verified patch of a published site (bmashup.patch 1)

`bm_sdk_patch_demo.asi` asks for the published site `game.byte_fade_rate` = 255.

| site | type | shipped | bounds | read by |
|---|---|---|---|---|
| `game.byte_fade_rate` | f32 | 510.0 | 127.5 .. 2040.0 | sub_001805B0 (2 reads) |
| `game.racer_proximity_sq` | f32 | 25600.0 | 6400.0 .. 102400.0 | sub_00197430 (1 read) |

The portable form names a site and a value; the host checks: site known, verified on this build (mapped, in `.rdata`,
current bytes = the shipped bits), value finite and in bounds, no overlap with another plugin's patch (first accepted owner
keeps it: `CONFLICT`). Nothing is written at request time; accepted patches are applied when the plugins' start ends, before
the game's first instruction, read back, and checked again at every LOAD_DONE (an overwrite is counted and logged once).
Code is never patched (the game is recompiled C: its code bytes are not executed). The experimental address form
(`request_bytes`) needs this build's signature and the expected bytes; it is not shown here.

Log lines: `patch demo: site game.byte_fade_rate: shipped 510, bounds 127.5 .. 2040, verified 1`,
`patch demo: request game.byte_fade_rate = 255: OK`, then at the first load
`patch demo: game.byte_fade_rate: state 2 (2 = applied), reason OK, overwritten 0`; the host logs
`[PATCH] bmashup-sdk.patch-demo: site game.byte_fade_rate = 255 applied`.

Facts / hypotheses: the platform example with this logic was applied at runtime (launch 51, `requests closed: 1 applied`);
what the value does in the game is a HYPOTHESIS (a byte channel's fade rate) - its in-game effect was not observed.
