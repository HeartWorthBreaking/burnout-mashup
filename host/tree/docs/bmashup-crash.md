# bmashup.crash and CRASH_RESULT (Burnout Mashup, experimental, GP-CRASH1)

Private Burnout Mashup services for native plugins; not Takedawn services. Read only: nothing here changes how Crash plays.

## bmashup.crash v1 (`include/bmashup_crash.h`)
Queries over the game's own list of Crash junctions (100 in Burnout 3):

| Call | What it gives |
|---|---|
| `junction_count(host)` | 100, or 0 when the list is not the one this host was made for |
| `junction_get(host, i, &j)` | junction `i`: its game ID (`1G0000USC3V1`) and track (`US_C3_V1`) |
| `junction_find(host, "1G0000USC3V1", &i)` | the position of a junction ID |
| `last_result(host, &r)` | the last Crash result recorded in this process (as CRASH_RESULT), `NONE_YET` before the first |

Results: `OK`, `BAD_ARG`, `NOT_FOUND`, `UNAVAILABLE`, `NONE_YET`. Any thread. Before it answers, the host checks the game's
junction list against the build it was made for (a pinned FNV-1a hash of the list, every entry's own number and track, and
the list's end); on another build every query says `UNAVAILABLE` and the log says so once
(`[CRASH] the game's junction list: ...`).

## bmashup.events v6: CRASH_RESULT
Subscribe with `subscribe(host, BM_EVENT_CRASH_RESULT, fn, user)` while the plugin starts. Once per Crash attempt (RETRY is a
new attempt), on the game's thread, at the game's own record step at the end of the event (before Crash Results is shown):

| Field | Meaning |
|---|---|
| `junction` | 0..99, the position in the game's list; `BM_EVENT_NO_JUNCTION` for an ID the list does not have |
| `junction_id`, `track_id` | the junction's game ID and its track |
| `crash_score` | the total the game records for the junction (player 1's crash total; in the game's two-player scoring the sum of both) |
| `crash_mode` | `BM_CRASH_MODE_SINGLE` or `BM_CRASH_MODE_PAIR` |

Races and the other modes give no CRASH_RESULT. The host logs each result: `[CRASH] result N: junction J <id> (track T),
score S, single scoring (flags 0x..)`.

## The junction-record guard
The game stores a Crash result into the junction's record at `records + 0x4EC0 + index x 0x17C` with the index of its
junction search and never checks it. For an ID that is not in the list (the game's own junctions always are; an event a mod
might add one day would not be) that is the record before junction 0: the last track record. The host now skips that write
for such an ID (the event is still delivered with `junction = BM_EVENT_NO_JUNCTION`). For the game's own junctions nothing
changes. Crash events added by mods stay refused (`[bmashup.extra_events]`): their other hazards are open (gp\atlas\CRASH.md).

## Example
`examples/plugins/bmashup-crash-scores` (`bm_crash_scores.c`): logs every Crash result with the junction's track and keeps
the session's best score per junction, using both services.
