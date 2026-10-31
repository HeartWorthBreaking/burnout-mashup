# bmashup.hud 1 - HUD element transforms (NEW, platform 0.1.8)

Header: `sdk\include\bmashup_hud.h` (`BM_HUD_VERSION 1`). Example: `sdk\examples\bmashup-hud-shake` (mod 08 "boost bar shake":
the boost bar shakes while boosting).
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`), incl. the real generated HUD draw routine on a synthetic
scene; runtime: pending.

## Why a new service
No existing service touches the HUD (bmashup.camera is the 3D view, bmashup.settings the host's page). Elements, ownership and a
per-picture lifetime need their own service (design rule R0's justification).

## API (`BMSDK_HUD_TABLE_V1`)
| Call | Thread | What |
|---|---|---|
| `set_transform(player, element, &t)` | game thread, during a stage | `bm_hud_transform{dx, dy, scale, alpha}` for this picture and the next ones up to `BM_HUD_TTL_PICTURES` (4) |
| `release(player, element)` | game thread | give the element back (4 `NOT_OWNER` if not yours) |
| `element_rect(player, element, rect[4])` | any | where the element was drawn in the last picture (HUD units); 14 `NOT_SHOWN` |
| `element_available(element)` | any | 1 when this build serves the element |

Bounds (refused, never clamped, 2 `OUT_OF_RANGE`): |dx|, |dy| <= 64 HUD units (640 x 480), scale 0.5 .. 2.0, alpha 0 .. 1,
finite. One owner per (element, player): 3 `CONFLICT`. Player 1: 13 `UNSUPPORTED` (split screen untested).

## Elements served (player 0)
| element | served | how the host knows it |
|---|---|---|
| `BM_HUD_BOOST_BAR` | yes | its object's render callback (stored by one routine only) |
| `BM_HUD_BOOST_MESSAGE` | yes | its render callback (AIR, ONCOMING, DRIFT, NEAR MISS, TAILGATING) |
| `BM_HUD_AWARD` | yes (texts only) | the award callback inside the HUD scene; the award icons are shared with the crash banner, excluded |
| `BM_HUD_SCORE_BOARD` | yes | the objects on the score board's frame (the upstream score-board test) |
| `BM_HUD_POSITION`, `BM_HUD_LAP`, `BM_HUD_TAKEDOWNS` | no: 8 `UNAVAILABLE` | they share their plate / digit callbacks with each other and the board; frames not identified (RE) |
| `BM_HUD_SPEED`, `BM_HUD_CENTRE_MESSAGE` | no: `UNAVAILABLE` | both use one text callback; the centre message's frame is a runtime address |

## Mechanism (nothing the title reads back)
Before the HUD is drawn (the stage render mark) the host writes the element objects' position / size / alpha; at the picture's
flip it puts back every word that still holds the host's value - a title write in between wins. Order with the upstream score
board: the hud's own writes are put back first, the score board draws, then the plugins' transforms apply; alpha multiplies on
top of the score board's. dx / dy are HUD units before the widescreen squeeze. The HUD is not drawn under crash cameras, and
nothing is applied then.

## Deviations from the design draft
- Scale is about the element's drawn-box CENTRE (draft: the frame origin), else elements on shared frames would fly off.
- `element_available` is added to the table; codes 13 `UNSUPPORTED` and 14 `NOT_SHOWN` appended; 9..12 reserved for v2.
- Ownership lapses with the request's 4-picture lifetime (no RACE_EXIT hook needed: nothing outlives 4 pictures).
- The scale centre uses the last render's frame values: it may lag one picture for a frame the title moves.
- The draw list (draft version 2) is hook request phase 2.

## Evidence
`gp\slices\main18\test_runs\svc_c_r1`: 53 checks / 0 failures (offset +7.5 drawn columns for dx 10 under a 0.75 squeeze, scale
about the centre, alpha multiplies, put-back, a title write wins, TTL, CONFLICT / NOT_OWNER, bounds, crash cameras); mutants 1..7
killed.
</content>
