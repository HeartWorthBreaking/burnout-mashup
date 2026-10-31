# bmashup.rules 1 - race rules in the game's Eliminator (NEW, platform 0.1.9)

Header: `sdk\include\bmashup_rules.h` (`BM_RULES_VERSION 1`). Example: `sdk\examples\bm-eliminator-mode`. Hook request P3 E1.
**CHANGES GAMEPLAY.** Status: **OFFLINE-TESTED** (main19 patches 35 + 42: 38 checks incl. the real generated per-lap rule with the
host mark, 11 / 11 mutants killed); the host side is **probe-validated** (PR-E: the Eliminator logic run from a routed Single Event
row, host eliminations, the lap switch, the end by eliminations, correct results). **Reachable in platform 0.1.9 through
bmashup.menu mode rows** (main19 patch 43: the Single Event SELECT MODE list shows the ELIMINATOR rows plugins declare); a race can
be claimed only when such a row started it - any other race answers WRONG_MODE. The menu-started race ran in the retail game (validation round 3: the claim was
granted, the per-lap elimination was switched off, timed eliminations ran and the race finished).

## Why a new service
No existing service changes the course of a race; elimination removes a racer and changes the result: one race-level owner.

## API (`bm_rules_api`)
Results: 0 OK, 1 BAD_ARG, 2 NOT_IN_RACE, 3 CONFLICT, 4 NOT_OWNER, 5 NO_RACER, 6 LAST_PLAYER, 7 RATE, 8 WRONG_THREAD,
9 UNAVAILABLE, 10 ALREADY, 11 WRONG_MODE. Game thread (an events / hooks / takedawn.race callback) except `status`.
- `claim_race()`: only in a race whose logic is the game's Eliminator AND that this plugin's mode row started (others:
  CONFLICT; a retail Eliminator / World Tour: WRONG_MODE). From the load until RACE_EXIT; released then.
- `set_lap_elimination(on)`: 1 = the game's own "last racer at each lap is out" (default); 0 = the host skips the game's
  per-lap call for this race only (a mark in the per-lap rule sub_00024E30 takes the game's own "no single last racer" branch).
- `eliminate(racer)` (racer = the race-list index, as bmashup.racers): queued, then run at the next car update through the
  game's own elimination (order, explosion, sign, scoreboard, results); <= 1 a second (RATE); never the human player in a
  one-player race (LAST_PLAYER), never twice (ALREADY), never a racer not taking part (NO_RACER).
- `end_race(reason)`: the AI racer with the lowest progress is eliminated once a second until one racer is left; the game's own
  last-standing end then fires. The human is never eliminated by the host.
- `status()`: eliminator_race, owned / yours, racing, eliminated (this race, by the host), lap_elimination, ending.

## Facts (probe PR-E)
The Eliminator logic is the object 0x4D4BD8 (vtable 0x3A9D50; the current logic word MEM32(MEM32(0x4D5370) + 0x1B8)). A racer
still in has order R + 0x10D2 = 0xFFFF and R + 0x16C8 = -1; eliminated: order = the elimination count, R + 0x16C8 = 0. The game's
per-lap rule eliminates an already eliminated racer AGAIN when it is the lap's last; in a claimed race the host skips that call
(unclaimed races keep the game's behaviour). Eliminating the human ends the human's race (the host never does it).

## Limits
One-player only (split screen R6). The race's results and records are the game's; nothing is saved by the host. Both the logic word and the
object the per-lap rule runs on are checked (0x4D4BD8).
