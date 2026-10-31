# bmashup.boost 2 - award an amount of boost (platform 0.1.8)

Header: `sdk\include\bmashup_boost.h` (`BM_BOOST_VERSION 2`). Example: `sdk\examples\bm-boost-award`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); runtime: pending. **CHANGES GAMEPLAY.**

## What version 2 adds
Version 1 (`fill` = up to 3 full top-ups a race, `status`) is unchanged. Appended (`BMSDK_BOOST_TABLE_V2`):

| Call | Thread | What |
|---|---|---|
| `award(player, amount)` | game thread | ask that `amount` (game units) be added to the player's bar at that player's next car update |
| `award_status(player, &st)` | any | `bm_boost_award_status` (28 bytes): state, reason, awards this race, requested, bar before / after |

## Mechanism
The game's own add-boost routine (the one the game's refills and v1's `fill` use) is called at the car update with the amount as
its argument; every guest register it may touch is put back. The game's per-meter factors and the bar's cap still apply after
it: "the amount asked, then the game's rules". Awards from this service are a HOST source: bmashup.events / bmashup.hooks
BOOST_AWARD modifiers never change them.

## Bounds (refused, never clamped)
| rule | value | code |
|---|---|---|
| amount | finite, > 0, <= `BM_BOOST_AWARD_MAX_BARS` (1.0) x the bar's maximum (checked at the request and again at the update) | 15 `OUT_OF_RANGE` |
| rate | `BM_BOOST_AWARDS_PER_SECOND` (8) a plugin in any 60 simulation steps | 16 `RATE` |
| per race | `BM_BOOST_AWARDS_PER_RACE` (512) a plugin | 12 `LIMIT` |
| pending | one a plugin and player | 11 `ALREADY_PENDING` |
| player | 0 only; 1 answers 4 `UNSUPPORTED` (split screen untested); others 17 `NO_PLAYER` | |

Several plugins may award (no owner: awards add, as the game's own do). A new race or a missed car update drops a pending award
(13 `STALE`).

## Deviations from the design draft
- Player 1 (split screen) is UNSUPPORTED instead of served (rule R6).
- "Per second" is counted as 60 simulation steps.

## Evidence
`gp\slices\main18\test_runs\svc_a_r1`: 37 checks / 0 failures, 6 / 6 mutants killed; version 1's suite 74 / 0 on the new source.
</content>
