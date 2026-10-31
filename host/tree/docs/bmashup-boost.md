# bmashup.boost (Burnout Mashup, private, experimental)

**Burnout Mashup's own vehicle control. It is not a Takedawn service and is not proposed upstream.** It may change or go away.

A native plugin approved on the MODS page may ask for player 1's boost bar to be topped up to its current maximum, **by the game's own add-boost routine**: the one the game's own refills use.
- **The game decides the rest:** whether the routine adds anything now, when a boost starts (the player's button), how strong it is and how fast it drains.
- **No value or address is passed in.**
- **Nothing to restore:** no setting or table of the game is changed.

**The research behind it** (every field and where the game uses it): `research\native_gameplay_api\g5\G5_FEASIBILITY_REPORT.md` in the Burnout Mashup workspace.

## The service
`include/bmashup_boost.h`, offered as `bmashup.boost` version 1 through `takedawn_plugin_service`, beside `takedawn.race` and `bmashup.autopilot`.

| Call | What |
|---|---|
| `fill(host)` | Ask for one top-up. **The game's thread only** (an `on_update` call of `takedawn.race`). It writes nothing in the game: it checks and notes the request. `BM_BOOST_OK` when accepted, else the reason. At most `BM_BOOST_FILLS_MAX` (3) a race |
| `status(host, &st)` | `state`, `reason`, `race`, `fills`; player 1's bar as of the last update (`have_meter`, `meter`, `meter_max`, `boosting`); and the last top-up's `meter_before` / `meter_after`. Any thread; always one whole update's values |

**States:**

| State | Meaning |
|---|---|
| IDLE | No request yet in this race |
| PENDING | The top-up runs in player 1's next car update, if everything still holds there |
| DONE | The last request ran |
| REFUSED | The last request was refused or dropped |

**Reasons:**

| Reason | Meaning |
|---|---|
| `BAD_ARG`, `UNAVAILABLE`, `WRONG_THREAD`, `UNSUPPORTED`, `DEBUG_AUTOPILOT`, `NOT_IN_RACE`, `COUNTDOWN`, `PAUSED`, `RACE_OVER`, `NO_CAR` | As in `bmashup.autopilot` |
| `ALREADY_PENDING` | A request is already waiting |
| `LIMIT` | The race already had 3 top-ups |
| `STALE` | Dropped: a pause, a new race or restart, the stage left, more than 30 simulation steps, or no car update within 3 game updates |
| `NOT_ADDED` | With DONE: the game's routine added nothing, and the bar was not full. A `meter_before` equal to `meter_after` says so too |

## Where it acts
**The top-up happens only inside player 1's car update** (the `ap_update` mark), on the game's thread.
- **One handler:** the toolkit runs only the first handler of a mark, so `bm_autopilot.c`'s handler serves both services. It is a local dispatcher, not a general hook design.
- **Everything is checked again there:**
  - the build (`.rdata` words);
  - the game module, with a stage, running;
  - not paused;
  - phase 2;
  - the car's vtable (0x3B11A0) and player index 0;
  - the same race;
  - at most 30 steps since the request;
  - the cap.
- **The call:** `sub_0017A530` with `esi` = the car's boost block (car + 0x119C) and the bar's maximum (block + 0x34) as the amount, as the game's own refills pass it.
- **Afterwards:** every guest register it may change is put back: the general ones, xmm0–7 and the x87 top.
- **It never presses boost** or touches steering, throttle or the AI.

**The log** (`[AUTOPILOT]`-prefixed, so that the guarded scene runner keeps the lines):
- `[AUTOPILOT] bmashup.boost: filled N/3 at step S (race R): bar a -> b of m`
- one line per refusal or drop.

## Open (not yet seen in the game)
- **The gate:** the routine's own gate (`sub_00017310` on 0x4A71A0) is not known. If it declines, the status says `NOT_ADDED`.
- **A side effect:** the routine also adds to a running total (block + 0x3C). Whether that reaches records or saves is not known.
- **No game run yet.**

## The demo
`examples/plugins/bmashup-boost`:
- about 10 s into a race (RACING, with a car), it calls `fill` once;
- it logs the answer with the bar, and each status change with the bar before and after.

## Tests
- **`tests/bm_boost`:** the service through the shared car-update handler, over the real `race_service.c`, against a stand-in guest memory and a stand-in routine.
- **`tests/plugins`:** loads the demo for real with a stand-in service.
