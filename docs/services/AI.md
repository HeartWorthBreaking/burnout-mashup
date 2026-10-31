# bmashup.ai 1 - racer-AI query and rival pace

Header: `sdk\include\bmashup_ai.h` (`BM_AI_VERSION 1`). Example: `sdk\examples\ai` (mods `bmashup-sdk.ai-slow`,
`bmashup-sdk.ai-probe`). The AI's ValueDB values (aggression, avoidance, top speed ...) are data-mod tuning:
`TUNE_V3_AI.md`.

## API
| Call | Thread | What |
|---|---|---|
| `count()` / `get(i, &r)` | game thread | per racer of the race's list: `speed_cap` (m/s, after pace), `target_speed`, `schedule_offset` (s; > 0 = ahead, the game slows it), `schedule_column` (0..7), `zone`, `car_speed`, `pace_applied`, `is_player` |
| `set_pace(p)` | game thread | every AI-driven RIVAL's speed cap x p, `0.5 <= p <= 1.5`; 1.0 = the game's own (nothing written) |
| `get_pace` / `reset` | game thread | reset (owner only) returns to 1.0 and releases |

## Behaviour
- Applied each AI update right after the game computed the cap; the cap is recomputed every update, so `reset` / 1.0 is
  immediate. Nothing persists.
- Player cars are never changed (player 1 under the game's autopilot keeps the game's pace).
- The game's own rubber band still runs: a slower rival falls behind its schedule and the game raises its cap again (up to
  its own 4 s per zone correction), so the visible effect is smaller than the factor.
- Ownership: first requester owns the pace; another `set_pace` -> `BM_AI_CONFLICT`.

## Evidence
- **Query RUNTIME-VALIDATED** (gp_p4_1; on p4.1 the AI probe read every rival cap in gp_p41_2 / gp_p41_3).
- **Pace RUNTIME-VALIDATED on p4** (gp_p4c_2, four RESTART segments, autopilot on player 1): rivals x0.70 / x1.30 (players
  x1.00); cap ceiling 88 -> 61.6 / 114.4; rival real speed 53.80 -> 48.49 / 60.25 m/s; player mean place 5.35 -> 4.83 / 5.97;
  segment 4 = segment 1 identically (deterministic replay).
- Not run: the 0.5 / 1.5 bounds; pace on p4.1 (OFFLINE-VALIDATED there).
- Hypothesis (not shown): far-mode rivals (> 125-140 m from the player) follow their previous speed.

## Evidence update (kit 0.3.1)
Bounds **0.5 / 1.5 RUNTIME-VALIDATED on p4.1** (gp_p41g_1: caps 44 / 132, rival speed -46.1 % / +22.4 %). **p4.2** (gp_p42_4):
race 2 after a RACE_EXIT at 0.70: rival caps x0.70 exactly (52.9 -> 37.0 ...), player row x1.00, rival mean speed 53.79 -> 46.65 m/s.
