# Example (f): coordinated hooks - owner and rival (bmashup.hooks 1)

One source, two modules: `bm_sdk_hooks_demo.asi` (owner) and `bm_sdk_hooks_rival.asi` (`-DBM_HOOKS_DEMO_RIVAL`).

| module | registrations | expected result |
|---|---|---|
| owner `bmashup-sdk.hooks-demo` | RACE_EXIT observe EXCLUSIVE; TAKEDOWN observe priority -10; BOOST_AWARD modify | `OK` x3; at each race exit `hooks demo: race exit N: player 1 took K cars down (TAKEDOWN hook called C times)`; player 1's perfect-lap award x1.25 |
| rival `bmashup-sdk.hooks-rival` | RACE_EXIT observe EXCLUSIVE; TAKEDOWN observe priority 10 | `CONFLICT` (host log: `[HOOKS] bmashup-sdk.hooks-rival: RACE_EXIT observe refused: CONFLICT (bmashup-sdk.hooks-demo holds it exclusively)`), then `OK`; its takedown line comes after the owner's observer |

Rules shown (contract: the platform's `hooks\CONTRACTS.md`; summary in the kit's `docs\MODDING_GUIDE.md`):
- hook points are the six the host build carries (no code address is ever accepted or returned);
- register only while the plugins start (`takedawn_plugin_service`); later requests answer `CLOSED`;
- order: MODIFY before OBSERVE, ascending priority, ties in plugin start order; an EXCLUSIVE registration must be the only one;
- each callback gets a fresh copy of typed values; the only effect is the declared output (BOOST_AWARD: `out->amount`,
  validated 0 .. 16 x the game's amount); the guest's registers are put back and a change is counted.

Offline evidence: the kit's verification runs both SDK-built modules (with the SDK patch demo and the platform's patch rival)
through the platform's `test_hk_plugins.c` against the REAL bmashup.hooks / bmashup.patch services of tree_p3 (= p2's = p1's; kit 0.2.0 verification) (unchanged
harness: the same log lines as the runtime-validated platform example). Runtime: the platform example with the same logic
ran in launch 51 (host p1) (demo RACE_EXIT exclusive OK, rival CONFLICT); the SDK build of it was not launched. The TAKEDOWN hook
has never been called at runtime (0 takedowns by player 1 in launch 51).
