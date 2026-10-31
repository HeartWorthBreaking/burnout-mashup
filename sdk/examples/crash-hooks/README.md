# crash-hooks (bmashup.hooks 2)

Observes the hooks v2 point **CRASH_RESULT** (7): each scored Crash junction attempt is logged (junction, IDs, score, mode) and the
session's best score is kept. OBSERVE only - the point has no output. bmashup.events v6 subscribers of BM_EVENT_CRASH_RESULT receive
the same occurrence first. Read only. Needs a platform 0.1.8 host.