# Example (b): BOOST_AWARD modifier with caps

`bm_sdk_boost_modifier.c` changes gameplay through **bmashup.events version 5** (`subscribe_modifier`): player 1 earns
`BONUS_FACTOR` (1.5) x the boost from drifting and oncoming driving, with the plugin's own caps:

| cap | default | effect |
|---|---|---|
| `BONUS_MAX_EXTRA` | 5.0 | at most this much extra boost per award |
| `BONUS_RACE_BUDGET` | 40.0 | at most this much extra per race; once spent, awards are left alone until the next race |
| sources | drift, oncoming (`BONUS_SOURCE_A` / `_B`) | every other source, racer and the host's own adds are untouched |

On top, the **service's** rules (`bmashup_events.h`): a result must be finite and within 0 .. 16 x what the game asked for
(else ignored and counted as `rejected`); modifiers run in subscription order (the plugins' start order), each seeing the
previous result; `BM_BOOST_HOST` adds are never modified; nothing re-enters.

At each race exit:

```
[PLUGIN bmashup-sdk.boost-modifier] boost modifier: race over: 9 awards boosted, +40.00 boost of 40.00 per race; capped per award 9, by the race budget 2; service: modified 9, rejected 0
```

Adapted from the runtime-validated G8-E2M demo `bm_boost_bonus_demo.c` (+50 %, no caps). Needs version 5: on an older host
it logs `bmashup-sdk: bmashup.events: too old: ...` at the start and the loader logs `service bmashup.events N: not used`.

Change the rule at build time: `-DBMSDK_BOOST_DEFINES="BONUS_FACTOR=2.0f;BONUS_RACE_BUDGET=20.0f"` (CMake) or `-D...` (clang).
A changed build has new bytes: approve it again.

Offline evidence: `verify_sdk.py` scenario `events` drives 13 awards through the real v5 modifier chain and checks every
amount (4 -> 6, 20 -> 25 capped, perfect lap / racer 1 / host untouched, the budget's last 3, then left alone, reset next
race); `old` checks the too-old path.
