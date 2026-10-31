# bmashup.autopilot (Burnout Mashup, private, experimental)

**Burnout Mashup's own gameplay control. It is not a Takedawn service and is not proposed upstream.** It may change or go away.

A native plugin (docs/native-plugins.md) that the player approved on the MODS page may ask the game's own AI to take over player 1's car for the rest of the race in play.
- **The steps are the title's own:** it does this itself on a rolling start and at the finish.
- **The same code drives `RECOMP_DEBUG=autopilot`** (`src/game/ai_takeover.c`).
- **Nothing else can be changed through this service.**

**There is no hand-back.**
- The service never gives the car back to the pad, and has no call for it.
- It does not claim that the pad drives the car again in a later race. The title may give it back on its own when a new race is set up, but that has not been verified.

## The service
`include/bmashup_autopilot.h`, offered as `bmashup.autopilot` version 1 through `takedawn_plugin_service` (takedawn_services.h), beside `takedawn.race`.

| Call | What |
|---|---|
| `engage(host)` | Ask for the takeover. **The game's thread only** (an `on_update` call of `takedawn.race`). It writes nothing in the game: it checks and notes the request. `BM_AP_OK` when accepted, else the reason. |
| `status(host, &st)` | `state`, `reason`, `race`. Any thread. |

**States:**

| State | Meaning |
|---|---|
| `IDLE` | No request in this race. |
| `PENDING` | Accepted. The takeover is done in player 1's next car update, if everything still holds there. |
| `ENGAGED` | The game's AI drives player 1's car. |
| `ENDED` | That race is over or was left. The car is **not** handed back. |
| `REFUSED` | The last request in this race was refused or dropped; `reason` says why. |

`race` changes with each new race the service sees (a stage entered, or a restart).

**Reasons:**

| Reason | Meaning |
|---|---|
| `BAD_ARG` | No host, no out, or a status size below 8. |
| `UNAVAILABLE` | No game update seen yet. |
| `WRONG_THREAD` | Not the game's thread; nothing is noted. |
| `UNSUPPORTED` | A game build this does not know. |
| `DEBUG_AUTOPILOT` | `RECOMP_DEBUG=autopilot` drives the car instead; the service stays off. |
| `NOT_IN_RACE` | Menus, loading, or a stage being left. |
| `COUNTDOWN` | In a stage, before the GO. |
| `PAUSED` | The race is paused. |
| `RACE_OVER` | Player 1's race is finished. |
| `NO_CAR` | Player 1's car is not one the service can take over. |
| `AI_OWNED` | The title's AI already holds the car. |
| `ALREADY_PENDING` | A request is already waiting. |
| `ALREADY_USED` | The race already had its takeover: at most one a race. |
| `STALE` | The request was dropped because the race moved on before it ran: a pause, a new race or restart, the stage left, more than 30 simulation steps, or no car update within 3 game updates. |

## Where it acts
**The takeover happens only inside player 1's car update,** on the game's thread: the existing `ap_update` mark (sub_0018C510 after 0x18C511). There everything is checked again:
- the build;
- the game module, with its stage, running;
- not paused;
- phase 2;
- the car's vtable (0x3B11A0) and player index 0;
- the AI byte still 0;
- the same race;
- at most 30 steps since the request.

**What it writes, and nothing else:**
- the car's AI byte;
- the four route-state words;
- the AI driver's route reset (`sub_00179760`);
- the registers, put back afterwards.

**While engaged,** in each car update in play:
- **The stamp:** it stamps the controller records (as `RECOMP_DEBUG=autopilot` does), so that a race with no pad input is not paused.
- **Taking the car again:** if the title has dropped the takeover (the AI byte back to 0, as after a crash's reset), it applies the same steps again. This is what `RECOMP_DEBUG=autopilot` does at every car update. Without it, the car coasted to a stop after its first crash (G4 run 1).
- **Limits:** only player 1's car, only in this race, never while paused, never after the finish.

**A watch:** an engaged car that has not moved for 10 s of race time is reported once (`... stalled: ...`). It changes nothing; a scene can stop waiting on it.

**The log:**
- `[AUTOPILOT] bmashup.autopilot: engaged at step N (race R) ...`
- at the finish, `[AUTOPILOT] bmashup.autopilot: result place P/N time T s best lap B s laps L`
- `[AUTOPILOT] bmashup.autopilot: taken again at step N ...` each time the takeover is applied again;
- `[AUTOPILOT] bmashup.autopilot: stalled: ...` from the watch;
- one line per refusal or drop.

## With RECOMP_DEBUG=autopilot
- The toolkit runs only the first handler of a mark, so the two never share it.
- With the debug autopilot on, this service does not hook the car update and answers `DEBUG_AUTOPILOT`.

## Version 2: every race, an explicit policy, the hand-back
Version 1 was always "at most one takeover a race"; the G4 demo asked once per process (its own flag). In a later race the
service refuses `AI_OWNED` while the title's own takeover (its finish / rolling start) still holds the car; the title
clears it itself (CB3PlayerCar's reset, vtable slot 0 `sub_0018C470`, and the rolling start's end at 0x193892).

| Call | Effect |
|---|---|
| `engage2(host, &req)` | `req.policy = BM_AP_POLICY_ONCE_PER_RACE` (anything else: `BAD_ARG`); `req.race` = `status.race` of the race meant, or 0 for the race in play. Another race: `WRONG_RACE`, status unchanged. Otherwise exactly `engage` |
| `release(host)` | Only while `ENGAGED` (this service's takeover, this race), racing, not paused; else `NOT_ENGAGED` or the reason. Staged: player 1's next car update checks the build (plus the .rdata 1.0 at 0x3B168C), in play, the same race within 30 steps, the car (vtable, player 0) and its physics link (`car + 0x2440`, whose `+ 0x1580` is the car), then does the title's hand-back: `CB3PlayerCar::SetAIControlled(0)`'s steps (`sub_0018CB60` at 0x18CB86, also the rolling start's end and `sub_000279C0`): AI byte 0, physics `+ 0x1534 = 1.0`, `+ 0x1524` 4 -> 0. State `RELEASED`; no stamping, no re-take, no new takeover in that race. Refused or dropped: still `ENGAGED`, `status.release_reason` says why |

- **Status (struct_size 24):** `release_reason`, `engaged_races`. A 16-byte caller gets version 1's fields.
- **Lifecycle (`bm_lifecycle.c`, the events v2 points, before plugins see them):** a request, a staged release or a takeover
  never outlives a `LOAD_DONE` or `RACE_EXIT` (dropped `STALE` / `ENDED`); a takeover is accepted only after a TRACK or RESTART
  load and before the next race exit (else `NOT_IN_RACE`).
- **Census (read only):** `[AUTOPILOT] bmashup.autopilot: census at <point> (race N): vtable, player, phase, AI byte, the four
  words at + 0x19D0, physics link (+0x1524, +0x1534)` at each load end, race exit, new race, the GO, the end and a release.
- **After a release the pad drives the car.** Nothing pressed: the car coasts (the human physics path reads an empty pad).
- **Version 1 callers are unaffected:** the table only grows; `WRONG_RACE` / `NOT_ENGAGED` never become a status reason, and
  `RELEASED` appears only after a version 2 caller released.

## The demo
`examples/plugins/bmashup-autopilot` (build-time modes, see the source):
- default (`BM_AP_DEMO_EVERY_RACE=1`): in every race, about 5 s in (`RACING`, with a car), one takeover: `engage2` bound to
  `status.race` (version 1 service: `engage`); a refusal the race can outgrow (countdown, pause, `AI_OWNED`, `STALE`) is
  asked again a second later, at most 5 times a race;
- `BM_AP_DEMO_EVERY_RACE=0`: the G4 behaviour, one request in the whole process;
- `BM_AP_DEMO_RELEASE_S=N` (+ `BM_AP_DEMO_RELEASE_FROM=k`): `release` N race seconds after the takeover, from the k-th engaged
  race on; `BM_AP_DEMO_PROBE=1`: logged negative controls (engage2 + release in the front end, engage2 in each countdown);
- it logs the answer and each status change;
- it reads the race through `takedawn.race` and changes nothing else.

Like every native plugin, it is never loaded until its bytes are approved on the MODS page.

## Tests
- **`tests/bm_autopilot`:** the service over the real `race_service.c` and `ai_takeover.c`, against a stand-in guest memory. It covers each refusal, the staged request, the takeover's exact steps, the requests that must not survive, the end without a hand-back, and another thread.
- **`tests/plugins`:** loads the demo for real with a stand-in service.
