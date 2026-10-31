# bmashup.hooks 2 - point 7 CRASH_RESULT (platform 0.1.8)

Header: `sdk\include\bmashup_hooks.h` (`BM_HOOKS_VERSION 2`). Example: `sdk\examples\crash-hooks`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); runtime: pending.

## What version 2 adds
- Point 7 `CRASH_RESULT`, OBSERVE only: a Crash junction attempt was scored (the crash1 mark, the game's record step). Dispatched
  through bmashup.events' delivery, after the bmashup.events v6 CRASH_RESULT subscribers, then hooks observers by priority, then
  host observers.
- `bm_hook_ctx` grows at its end (`BMSDK_HOOK_CTX_V2`): `player` (0 here: one record step per event; two-player Crash adds the
  totals, `crash_mode` says so), `crash_junction` (0..99 or `BM_HOOK_NO_JUNCTION`), `crash_score`, `crash_mode`,
  `crash_junction_id[16]`, `crash_track_id[16]` - the bmashup.events v6 values. A v1 plugin reads its prefix only.
- The table is unchanged (`BMSDK_HOOKS_TABLE_V2` = v1's). `BM_HOOK_POINTS` keeps 6 (compiled into v1 plugins);
  `BM_HOOK_POINTS_V2` = 7.
- Points 8..13 (HUD_PASS, CAMERA_FINAL, TRAFFIC_CONTACT, WRECK_CAUSE, EVENT_SOUND, FINISH_CAMERA) are reserved for later phases:
  registering there answers `UNKNOWN_POINT` on a 0.1.8 host.

## Rules kept
Register only while the plugins start; re-entry counted (`reentered`), not dispatched; nothing after exit; registers / x87 /
flags saved and put back.

## Evidence
`gp\slices\main18\test_runs\svc_b_t3` (test_b_v2.c): order (events subscriber before the hook), values, sequence, re-entry,
after-stop; mutants (MODIFY offered, score lost, dispatched after the stop / on re-entry) killed. crash1's own runner could not be
re-pointed (it compares against older generated code).
</content>
