# bmashup.events 7 - the twins of bmashup.hooks 3 (platform 0.1.9)

Header: `sdk\include\bmashup_events.h` (`BM_EVENTS_VERSION 7`). Status: **BUILT, offline-tested** on the main19 host (the twins ran in the retail validation races).

## What version 7 adds
- Events 8 `HUD_PASS`, 10 `TRAFFIC_CONTACT`, 11 `WRECK_CAUSE`, 12 `EVENT_SOUND`: OBSERVE twins of the bmashup.hooks 3 points with the
  same numbers (9 CAMERA_FINAL and 13 FINISH_CAMERA have no twin). Subscribe with `subscribe()` as any direct event; an event whose
  point is not available in the run answers `BM_EVENTS_UNAVAILABLE`.
- `bm_event` grows at its end: `hud_visible`, `frame_dt_s` (HUD_PASS); `contact_racer`, `contact_traffic`, `contact_closing_mps`,
  `contact_same_dir`, `contact_outcome` (the FINAL outcome after the hooks modifiers: 0 GAME, 1 NO_CRASH); `cause_aggressor`,
  `cause_victim`; `sound`, `sound_level_game`, `sound_event`, `sound_level` (the FINAL level). Only the event's own group is set.
- Modifiers stay BOOST_AWARD only; the new outputs are bmashup.hooks MODIFY outputs. Order: hooks MODIFY -> these observers ->
  hooks OBSERVE -> host observers. Register guard, no re-entry, nothing after exit (as versions 2..6).
- HUD_PASS runs once a picture: keep the callback short (< 0.1 ms), subscribe only when needed.
- The table is unchanged (`BMSDK_EVENTS_TABLE_V7` = v5's).

## Evidence
`tests\p23\hooks\test_hk_v3.c` (twin delivery with the final values, register put back, UNAVAILABLE before the offer; mutants 17 / 18).