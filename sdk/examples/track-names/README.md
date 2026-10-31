# Example (c): track names from plugin-owned game memory

`bm_sdk_track_names.c` names a track that a mod ADDS without naming it, through **bmashup.memory** + **bmashup.names**:

1. both services are needed; they are offered in no set order, so the plugin acts when it has both (`bmsdk_offer` keeps
   each one's state);
2. it checks the text first (name 1..27, location 1..17 characters from `A-Z a-z 0-9`, space and `- ' . &`);
3. `alloc` a block of the game's memory (a handle, never an address), `write` the UTF-16LE text through the service;
4. `set_text(track, kind, block)`: the names service validates the text in the block and FREEZES the block (read-only
   from then on: the game reads it).

```
[PLUGIN bmashup-sdk.track-names] track names: set name of US_C6_V1 = "Harbour Bay": ok
[PLUGIN bmashup-sdk.track-names] track names: set location of US_C6_V1 = "HARBOUR": ok
```

Rules (bmashup_names.h): only while the host starts the plugins (`BM_NAMES_CLOSED` afterwards); used only when the track
is one a mod adds and that mod did not name this kind itself (a mod's own names win; the host logs `[NAMES] a plugin's
text for ... ignored`); first plugin wins per track and kind.

Adapted from the runtime-validated G8-E4 demo `bm_track_names_demo.c` (launch 35: "Harbour Bay" in the selector). The
default track is `US_C6_V1`; another one at build time:
`-DBMSDK_NAMES_DEFINES="TRACK_ID=\"US_C7_V1\";TRACK_NAME=\"Pier Run\";TRACK_LOCATION=\"PIER\""`.

It needs a track mod that adds `US_C6_V1` WITHOUT names / locations (in the workspace: `runtime_data\modsets\g8cc1_track_set`;
not `g8nm1_track_set` or `g8wt_event_set*`, which name it).

Offline evidence: `verify_sdk.py` scenarios `names_memfirst` / `names_namesfirst` (both offer orders; the real services;
after the language-table install the game's own lookups return the plugin's frozen blocks), `names_missing` (no names
service: reported at exit).
