# bmashup.autopilot 2 - the game's AI drives player 1 (engage per race, release)

Header: `sdk\include\bmashup_autopilot.h` (`BM_AUTOPILOT_VERSION 2`). Host page: `host\bmashup-autopilot.md`. Example:
`sdk\examples\autopilot-demo` (mod `bmashup-sdk.autopilot-demo`).

## What it does
A plugin asks the game's own AI to take over player 1's car for the race in play - the same steps the title takes on a
rolling start and at the finish. Version 2 adds `engage2` (an explicit policy, bound to one race, so a plugin can engage in
every race of a process) and `release` (the title's own hand-back, `SetAIControlled(0)`'s steps). Nothing else can be
changed through it: no address, value or car is passed in.

## API
| Call | Thread | Result |
|---|---|---|
| `engage(host)` | game thread (an `on_update` of `takedawn.race`) | `BM_AP_OK` = accepted (PENDING); the takeover happens at player 1's next car update if everything still holds |
| `engage2(host, &req)` | game thread | `req.policy = BM_AP_POLICY_ONCE_PER_RACE`, `req.race` = `status.race` of the race meant (0 = the race in play); another race: `BM_AP_WRONG_RACE` |
| `release(host)` | game thread | only while ENGAGED by this service, racing, not paused; done at player 1's next car update; state -> RELEASED |
| `status(host, &st)` | any | `state` (IDLE / PENDING / ENGAGED / ENDED / REFUSED / RELEASED), `reason`, `race`; v2 (struct_size 24): `release_reason`, `engaged_races` |

Refusal reasons (`BM_AP_*`): NOT_IN_RACE, COUNTDOWN, PAUSED, RACE_OVER, NO_CAR, AI_OWNED (the title's own takeover still
holds the car), ALREADY_PENDING, ALREADY_USED (one takeover a race), STALE (the race moved on before the request ran),
WRONG_RACE, NOT_ENGAGED, DEBUG_AUTOPILOT (`RECOMP_DEBUG=autopilot` drives instead), UNSUPPORTED (unknown build).

## Lifecycle and limits
- At most one takeover a race; a new race (incl. a pause RESTART) allows a new one. The service never hands the car back by
  itself; after `release` the pad drives the car (nothing pressed: it coasts). Not after the finish (that takeover is the title's).
- Requests and staged releases are bound to the lifecycle (load done / race exit) before plugins see those events.
- `[plugin]` mods need approval by exact sha256 (INSTALL.md s4).

## Evidence
- **RUNTIME-VALIDATED** on p4 (gp_p4_1: engaged in race 1 and race 2 of one process; gp_p4c_1 / gp_p4c_2: engaged after
  every RESTART) and on p4.1 (gp_p41_2: engaged at 5 s and **released at 8 s** in both races, "the pad drives player 1").
- Offline: bm_autopilot 168 / 0, 20 / 20 mutants (slice autopilot2).
- Not covered: the standalone slice build never ran; the car after a release was unsteered in the run (RT held only).

## Demo build options (`sdk\examples\autopilot-demo`)
`BM_AP_DEMO_EVERY_RACE` (1 = every race, 0 = once per process as demo 0.1), `BM_AP_DEMO_RELEASE_S=N` (release N race
seconds after the takeover), `BM_AP_DEMO_RELEASE_FROM=k` (from the k-th engaged race), `BM_AP_DEMO_PROBE=1` (logged negative
controls). The kit builds the defaults (every race, no release); set `BMSDK_AUTOPILOT_DEFINES` for others.

## Evidence update (kit 0.3.1)
p4.2 gp_p42_4: engaged in race 1 and again in race 2 after a RACE_EXIT (pause QUIT, the same event again); released in race 2
(`SetAIControlled 0; the pad drives player 1`). p4.1 gp_p41g_1: engaged in 8 RESTART segments and after a race-2 RACE_EXIT.
