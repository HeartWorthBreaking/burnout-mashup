# bmashup.input 1 - read-only pad snapshot (NEW, platform 0.1.8)

Header: `sdk\include\bmashup_input.h` (`BM_INPUT_VERSION 1`). Example: `sdk\examples\bmashup-input-log`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`); runtime: pending.

## Why a new service
No service reads input: takedawn.race is upstream's, bmashup.autopilot INJECTS input, bmashup.settings is a host page.

## API (`BMSDK_INPUT_TABLE_V1`)
`pad(pad, &p)` -> `bm_input_pad`: connected, owner, context, frame, buttons / pressed / released, lx / ly / rx / ry (-1..1),
lt / rt (0..1). Results: 0 OK, 1 BAD_ARG, 2 NO_PAD, 3 WRONG_THREAD, 4 UNAVAILABLE. A short struct gets its prefix only.

- `pad` is the HOST pad index 0..3 (pad 0 = the first host controller), not a race player: the title chooses its pad.
- Buttons: Xbox names (`BM_PAD_A` .. `BM_PAD_RIGHT`) plus `BM_PAD_LT` / `BM_PAD_RT` (triggers held); an analog button counts as
  held above 30 of 255. The host's PS2 scheme / keyboard map is applied before (it is what the title received).
- One snapshot per frame and pad, taken when the title reads its pad (the ctl_pad mark), identical for every plugin.
- Nothing is injected or consumed: the title still sees every press.

## Owner masking
`owner` = `BM_INPUT_GAME`, `BM_INPUT_HOST_PAGE` (MODS / MOD SETTINGS shown) or `BM_INPUT_OVERLAY` (the toolkit overlay). While it
is not GAME, buttons, edges, sticks and triggers all read 0, and a button still held when the game gets the pad back reads
`released` until it is let go - a plugin never acts on a press a host page took.

## Context
`BM_INPUT_CTX_RACE`, `_PAUSE`, `_FRONT_END`, `_LOADING` (0 when unknown). `_GARAGE` is not detected in 0.1.8: car select reads
FRONT_END.

## Deviations from the design draft
Pad index instead of player; LT / RT bits appended; sticks / triggers also masked; the hand-back latch; GARAGE not detected.
The modder's notes on the pad manager (raw records, device objects) agree with the site used; no raw record or address is exposed.

## Evidence
`gp\slices\main18\test_runs\svc_c_r1`: 23 checks / 0 failures (edges, digital / analog mapping, frame identity across plugins,
host-page and overlay masking, latch, contexts, prefix copy, port mapping); mutants 1..4 killed.
</content>
