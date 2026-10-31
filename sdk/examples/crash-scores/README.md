# (n) crash-scores - bmashup.events 6 + bmashup.crash 1

`bm_crash_scores.c` = the host tree's example (crash1 slice / p4.1), unchanged. It subscribes to CRASH_RESULT, logs
`junction J on <track>, attempt N: $score` and the session's best per junction, and cross-checks `bmashup.crash`'s
`last_result`. Read only. Contract and evidence: `docs\services\CRASH_EVENTS_V6.md`.
