# Example (a): gameplay events observer

`bm_sdk_events_observer.c` watches player 1's race through **bmashup.events** and logs a tally at each race exit:

```
[PLUGIN bmashup-sdk.events-observer] events observer: race over (6 racers): takedowns 1, taken down 1, wrecks 1; boost awards 12, 239.0 boost (game asked 199.0, 9 changed by modifiers)
```

Adapted from the runtime-validated G8 demos `bm_lifecycle_demo.c` (E1), `bm_takedown_demo.c` (E6) and
`bm_boost_awards_demo.c` (E2).

| events | needs | on an older host |
|---|---|---|
| LOAD_DONE, RACE_EXIT | bmashup.events 2 (required) | not run: `bmashup-sdk: bmashup.events: too old ...` / `missing ...` |
| TAKEDOWN, WRECK | version 3 | off; the bind line says `takedowns / wrecks off (needs version 3)` |
| BOOST_AWARD | version 4 | off; `boost awards off (needs version 4)` |
| award_requested / award_modified | version 5 | read only when the event's `struct_size` covers them |

What it shows:
- discovery with `bmsdk_offer` and degrade with `bmsdk_has(w, 3)` / `bmsdk_has(w, 4)`;
- field checks with `BMSDK_HAS_FIELD(ev, bm_event, field)` (append-only structs);
- the missing-service report: on a platform host at the end of the offers (`BMSDK_DEFINE_SERVICES_DONE`, during the
  start); on older hosts at the first LOAD_DONE and, as the last resort, from `on_shutdown` (a host without
  bmashup.events never calls the plugin again). One line in all cases.

Observe only: events are copies valid during the call; nothing is written.

Build: `build.ps1` at the SDK root (all examples), or this folder alone (`BUILD.md`). Install: copy
`<build>\out\bmashup-sdk-events-observer\` into a mods folder and approve the module's bytes (`plugin-approvals.toml`).

Offline evidence: `verify_sdk.py` scenarios `events` (real v5 service), `old` (a v3 table), `missing` (no service).
