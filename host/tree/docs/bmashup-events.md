# bmashup.events and the engine-point dispatcher (Burnout Mashup, private, experimental)

**Burnout Mashup's own engine events.** They are not a Takedawn service. The dispatcher core (`src/game/bm_events.c`) is written to be general, with no game names in its interface, so that a general event service could later sit on it; the service and its events are Burnout Mashup's.

## The dispatcher (`src/game/bm_events.c/.h`)
**Why:** the toolkit runs only the first handler registered for a mark (`recomp_patch.c`). So the dispatcher owns the mark and calls an ordered list behind it, instead of each part of the host registering its own handler.

**The rules:**
- **One owner per mark:** `bo3_events_hook(name)`, once, before the guest runs. At most 4 marks, each with up to 24 subscribers.
- **Registration only at start:** subscribers are added only while registration is open, which is the single-threaded start up to the end of the plugins' start (`bo3_events_close` in `main.c`). The lists are fixed afterwards, so dispatch takes no lock.
- **Order:** observers first (they see the state before any change), then writers; each kind in registration order.
- **Registers:** after each subscriber, the guest registers (general, esp, xmm0–7, the x87 top) are compared and put back if changed, and the change is counted. For an observer it is also logged once. A writer may call a game routine that uses volatile registers.
- **No re-entry:** a mark reached again from inside its own dispatch is not run again; that is counted.
- **Exit:** once the process starts to exit, nothing is dispatched. The stop is registered with `atexit` after the plugins' `on_shutdown`, so it runs before them.

**Today one mark is owned: `ap_update`** (player cars' update, 0x18C511). Its writers:
- `bmashup.autopilot`, then `bmashup.boost`, in the same order as before; this replaces G4/G5's hard-wired `bm_mark`.

With `RECOMP_DEBUG=autopilot` the mark is left to the debug driver, as before.

## The service (`include/bmashup_events.h`, `bmashup.events` v1)
**`subscribe(host, BM_EVENT_PLAYER_CAR_UPDATE, fn, user)`:** only while the plugins start, in `takedawn_plugin_init` or `takedawn_plugin_service`. `fn(event, user)` is then called:
- on the game's thread;
- inside player 1's car update (player 2's are not delivered), once per car update;
- with a copy: `{ struct_size, event, sequence, step, race_time_s, car_phase }`;
- **observe only:** no pointer, no address, no write.

Every subscriber of one occurrence gets the same `sequence`.

**Results:**

| Result | Meaning |
|---|---|
| `OK` | Subscribed |
| `BAD_ARG` | Bad arguments |
| `UNKNOWN_EVENT` | No such event |
| `CLOSED` | After the plugins' start |
| `UNAVAILABLE` | The point is not hooked, for example under the debug autopilot |
| `ALREADY` | This plugin has already subscribed to this event |
| `FULL` | No room for another subscriber |

**`stats(host, event, &st)`** (any thread): events delivered to this plugin, occurrences of the point (any car), and this plugin's register faults.

**Cost:** the event comes once per car update: 60 a second, more with High refresh. A subscriber holds up the game while it runs.

Plugins stay unsandboxed: the dispatcher contains register mistakes, not crashes.

## Version 6: CRASH_RESULT (GP-CRASH1)
One event per Crash attempt at the game's record step, with the junction (position, game ID, track), the total the game
records and its scoring mode. See [bmashup-crash.md](bmashup-crash.md). Fields are appended to `bm_event`; older plugins
read the prefix their `struct_size` covers.

## The demos
`examples/plugins/bmashup-events`: one source built twice as two plugins, A and B (`a/mod.toml`, `b/mod.toml`). Each:
- subscribes while it starts;
- counts the events;
- once a second of race time logs its count with the event's sequence, step and race time.

Both see the same updates, so their lines carry the same sequence numbers.

## Tests
- **`tests/bm_events`:** the core on its own marks (order, re-entry, register state, capacity, close, stop), and the service on the real car-update mark with the real writers. That includes two plugins on one event, player 2 filtered, observers seeing the state before the writers act, a rule-breaking observer contained, and the stop.
- **`tests/bm_autopilot`, `tests/bm_boost`:** unchanged results on the dispatcher.
- **`tests/plugins`:** loads both demos for real with a stand-in service.
