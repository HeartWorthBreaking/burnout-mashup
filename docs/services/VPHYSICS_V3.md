# bmashup.vphysics 3 - the gearbox of player 0's car (platform 0.1.9)

Header: `sdk\include\bmashup_vphysics.h` (`BM_VPHYS_VERSION 3`). Example: `sdk\examples\bm-gearbox-toggle`.
Status: **BUILT, offline-tested and run in the retail game** (the game's own shift routines and the idle block run in the tests; in the
validation race the gearbox went MANUAL and the requested gears 2 -> 6 -> 1 -> 2 were read back). **CHANGES GAMEPLAY** (label). Players are numbered as the API's `player` argument: player 0 = the first (one-player) player; player 1 = split screen.
Append-only: v1 / v2 unchanged.

## Functions
| function | what | codes |
|---|---|---|
| `set_gearbox(player, AUTO / MANUAL)` | MANUAL: the gearbox's own mode word is held at MANUAL from the car's next update in a race (retail Xbox never sets it); the game's own manual path then shifts on the car's shift inputs. AUTO: given back (the word returns to 0 at the next car update) | NOT_PLAYER (player > 1), UNSUPPORTED (player 1 = split screen, or the census failed), CONFLICT (another owner; AUTO by a non-owner), BAD_ARG, DEBUG_AUTOPILOT |
| `request_gear(player, gear)` | one shift toward `gear` per car update through the game's up / down shift routines (never a raw gear write) | WRONG_MODE (not MANUAL by you), BAD_ARG (outside 1 .. max_gear), BUSY_SHIFT (the game's shift flag is set now), UNAVAILABLE (no car in a race) |
| `gearbox_status(player, out)` | available, mode, gear (-1 R / 0 N / 1..), max_gear, requested, shifting, owned / yours, idle_fix_skips (40 bytes) | any thread |

- Neutral and reverse stay the game's: in MANUAL the car stops in N and reverse is the brake-hold path, as in AUTO.
- One host mark in the gearbox update (sub_00121560): while a plugin owns MANUAL on that car and the gear is already 0, the
  game's idle re-shift to neutral is skipped (otherwise its re-armed shift flag blocks reverse by brake; the PS2 mod's fix).
  Nobody owning MANUAL = the retail block runs unchanged.
- Owner and request are dropped and the word goes back to AUTO when a race is left or restarted: set MANUAL again for the next
  race (a set before the race applies from its first car update). set / request are recorded on any thread and carried out at
  the car update (the game's thread).

## Switches
`BO3_HOOKREQ_P23=OFF`: the mark is compiled out and every v3 call answers UNSUPPORTED. Census at first use: the 6 code sites
(the mode gate, the idle block, both shift routines, the manual path's gate and its retail call shape) must match the verified
build, else UNSUPPORTED (`available` 0).

## Evidence
`gp\slices\main19\tests\p23\vphysics_v3\run_vphysics_v3.py`: 35 checks over the REAL generated sub_0011A7B0 / sub_0011A7E0 and the
idle block of sub_00121560 (with the mark), mutants 21..27 killed, the OFF build 7 checks, census 6 / 6 vs the XBE.
