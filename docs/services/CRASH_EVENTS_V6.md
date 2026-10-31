# bmashup.crash 1 + bmashup.events 6 (CRASH_RESULT)

Headers: `sdk\include\bmashup_crash.h`, `sdk\include\bmashup_events.h` (`BM_EVENTS_VERSION 6`). Host page:
`host\bmashup-crash.md`. Example: `sdk\examples\crash-scores` (mod `bmashup-sdk.crash-scores`). Read only: nothing here
changes how Crash plays.

## bmashup.crash 1 (any thread)
`junction_count` (100, or 0 when unavailable), `junction_get(i)` (game ID `1G0000USC3V1`, track `US_C3_V1`),
`junction_find(id)`, `last_result` (the last CRASH_RESULT of this process; `NONE_YET` before the first). The host verifies
the game's junction list (pinned FNV-1a, every entry's number and track, the list's end) before it answers; on another build
every query is `UNAVAILABLE`.

## bmashup.events 6: CRASH_RESULT (`BM_EVENT_CRASH_RESULT = 7`)
Subscribe while the plugin starts. Delivered once per Crash attempt (a RETRY is a new attempt), on the game's thread, at
the game's own record step (before Crash Results is shown). `bm_event` grows 84 -> 128 bytes; older plugins read their
prefix. Fields: `junction` (0..99 or `BM_EVENT_NO_JUNCTION`), `junction_id`, `track_id`, `crash_score` (the total the game
records), `crash_mode` (`BM_CRASH_MODE_SINGLE` / `PAIR`). Races and other modes give none.

Junction-record guard (host): an ID outside the game's list (never the case for retail junctions) is still delivered with
`BM_EVENT_NO_JUNCTION`, and the game's record write is skipped (it would land in the last track record).

## Evidence
- **RUNTIME-VALIDATED on the crash1 build** (gp_crash1_1): list verified (100 junctions); race (negative control) 0 events;
  Crash junction 1 x2 -> CRASH_RESULT junction 0 `1G0000USC3V1` scores 15019 / 3376 = the Crash Results screen ($15,019 /
  $3,376).
- On p4: the example bound events 6 + crash 1 at runtime (gp_p4_1, no Crash run); on p4.1: OFFLINE-VALIDATED (slice suite).
- Not covered: pair scoring (two-player Crash), other junctions (only junction 1 is open on a fresh profile), the guard's
  skip path (unreachable with retail junctions; offline only).

## Limits
- The `bmashup.hooks` sink does NOT get CRASH_RESULT (needs a hooks v2; plugins use events v6).
- Crash events added by mods stay refused (`[bmashup.extra_events]`): their other hazards (launch walk, medal store, list row
  / map marker, per-junction arrays) are open.

## Evidence update (kit 0.3.1)
**On p4.1 RUNTIME-VALIDATED** (gp_p41g_2: CRASH_RESULT 93235 = Crash Results $93,235, CONSISTENT, 0 events in the races). Not
run on p4.2 (the code is unchanged in its merge delta).
