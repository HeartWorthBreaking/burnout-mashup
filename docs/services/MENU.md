# bmashup.menu 1 - front-end additions: popup, mode row, stat bars (NEW, platform 0.1.9)

Header: `sdk\include\bmashup_menu.h` (`BM_MENU_VERSION 1`). Examples: `sdk\examples\bm-menu-popup`, `bm-eliminator-mode`,
`bm-garage-stats`. Hook request P3 items D1 / D2 / D3.
Status: **POPUP SERVED** (main19 patch 45; offline-tested: live state machine 21 checks + 5 / 5 mutants, the real generated
car-select input handlers with the marks, real-XBE census of every site; confirmed in the retail game: the YES / NO dialog opened on
car select and the answer was saved as a setting). **MODE SERVED** (main19 patch 43; offline-tested: 18 checks with the REAL
generated list set-up / SE state handler / SE race set-up carrying the marks, 5 / 5 mutants, real-XBE census; confirmed in the retail
game: the "TIMED ELIM" row appeared as the 5th row of SELECT MODE, was chosen and the Eliminator race ran to its results).
**BARS: UNAVAILABLE** (below). Declarations of all three are offline-tested (patches 32..34, 58 checks, 11 / 11 mutants).
Always test `feature_available()`.

## Why a new service
bmashup.settings owns the host's pages and bounded values; a popup in the title's flow, a SELECT MODE row and bars on car select
are title UI objects with their own lifecycle (one dialog owner, list capacity, a mode dispatch). The values stay settings: a
popup answers into a PER_PLAYER setting, an option row edits a GLOBAL setting of the same plugin.

## API (`bm_menu_api`)
Declare while the plugins start only (`CLOSED` after). Results: 0 OK, 1 BAD_ARG, 2 CLOSED, 3 FULL, 4 DUPLICATE, 5 BAD_TEXT,
6 CONFLICT, 7 UNAVAILABLE, 8 UNKNOWN_SETTING, 9 WRONG_SETTING. Texts: printable ASCII.
- `declare_popup(d)`: `setting_key` = this plugin's own PER_PLAYER BOOL (YES / NO) or ENUM (its first two choices) setting
  (declare the setting first: bmashup.settings is offered before bmashup.menu); `title` <= 24; `contexts` =
  `BM_MENU_CTX_SINGLE_EVENT` and / or `BM_MENU_CTX_MULTIPLAYER` (World Tour is never accepted). <= 8 popups over all plugins;
  <= 2 shown after one confirmation, in plugin start order.
- `declare_mode(d)`: `id` [a-z0-9_] 1..24 (unique per plugin), `label` <= 16, `help` <= 96, `base` = `BM_MENU_BASE_ELIMINATOR`
  (the only base in v1; others UNAVAILABLE), `contexts` as above, `option_keys` / `n_options` 0..2 of this plugin's GLOBAL INT /
  ENUM settings. <= 4 rows over all plugins (the title's lists keep <= 10 rows).
- `declare_bar(d)`: `label` <= 12, `fn(vehicle, user)` -> 0..1 (outside or NaN: not drawn), `user`. <= 2 bars over all plugins.
- `active_mode(id, room)`: the added mode the race in play came from ("" for a retail mode; always "" in 0.1.9).
- `feature_available(feature)`: 1 when this host shows that feature.

## How it works (host)
Texts are copied once, at the end of the plugins' start, into the guest high zone as UTF-16 (16 KiB budget). The popup driver
uses the title's own dialog (0x550DA0): it opens it (type 7, the retail call shape of 0x86600) only when nobody else owns it,
polls it once a frame (the shape of 0x86800; 15 = no answer yet, 4 / 5 = first / second choice), stores the answer in the
setting, and closes it only if the host opened it and it is still open.

**When a popup shows (patch 45).** In the Single Event flow (SELECT MODE list -> options -> car select), when the player presses
A on the car-select page, the host takes that press (the car is NOT confirmed yet), and the title's dialog asks each SINGLE_EVENT
popup in turn (<= 2, plugin start order). Any pad answers (the dialog is polled with "every pad"). After the last answer the page
gets its input back once A is released; the player's next A confirms the car as usual. Once per visit of the car-select page
(leaving and coming back in the Single Event flow asks again). Answers are written to the plugin's PER_PLAYER setting for player 0
as a MOD SETTINGS change (saved, the setting callback gets BM_SETTING_CHANGED). Not shown: Multiplayer (its list page is not
verified, MULTIPLAYER popups never trigger in 0.1.9), World Tour (by design), player 1 (split screen, R6).
How: two marks at the entries of the car-select page's input handlers (vt 0x3AC044 slot 0 sub_00071AF0, slot 4 sub_00072500;
`bo3_menu_gen.h`) skip the page's input for a frame while the host popup owns the pad; the page tracker runs at each flip.

## Probe results (PR-C / PR-E / PR-F) and what is still missing
- POPUP: READY by PR-F (p23_fa4 / p23_fb4: the dialog opened, drawn over car select, answered YES / NO with controller -1, closed;
  the page worked after) -> served by patch 45 (`BM_P23_MENU_POPUP_SITE` 1; 0 = UNAVAILABLE).
- MODE (patch 43, offline RE in tests\p23\STEP0_G.md): the SE list page L = 0x5595A4 holds 10 rows (L+4 count, L+0x10 + 4 i text
  ids, L+0x38 / L+0x42 + i flags, L+0x54 + 8 i rows {text pointer, disabled, 0} read by the list widget 0x5509F4; the page ends at
  the car-select page 0x559648); down moves while sel + 1 < the widget's count copy L+0x50 (0x769CD); the accept dispatch maps a row
  >= 4 to the Race selector 0 (0x69F6C); the Race case of the set-up (0x5F514, S = 0x463AF0) is where the route writes the
  Eliminator logic 0x4D4BD8 and 5 laps. Texts are UTF-16 (Globalus.bin: ids 0x149 SELECT MODE, 0x14A RACE, 0x14C TIME ATTACK,
  0x14B ROAD RAGE, 0x150 CRASH).

**When a mode row shows (patch 43).** Each declared mode with `BM_MENU_CTX_SINGLE_EVENT` (<= 4) is an extra row after CRASH in
the Single Event SELECT MODE list, showing its `label` (help is not shown). Choosing it continues like RACE (options, car select)
and the race runs the title's Eliminator logic with 5 laps on the chosen track; `active_mode()` names the mode, and bmashup.rules
`claim_race()` accepts the declaring plugin. The row routed last is pre-selected next time. Option rows are NOT shown (use the MOD
SETTINGS page for the option settings). Not shown: the Multiplayer list (unverified), World Tour (by design).
- BARS: car select draws its two native bars (TOP SPEED / WEIGHT) with a widget not located; the host draws declared bars with the title's
  rect primitive at the end of the car-select page's draw routine (sub_000B6F90; main19 patch 47, `BM_P23_MENU_BARS_SITE`).
  **UNAVAILABLE on this host:** in the retail game the bars never appeared on the car-select screen (only the game's own TOP SPEED /
  WEIGHT meters), so this host ships with `BM_P23_MENU_BARS_SITE` 0: `feature_available(BM_MENU_FEATURE_BARS)` answers 0 and nothing is
  drawn. The declarations are still accepted and validated. Cause open; a follow-up.

## Limits
Split screen: player 1's popup is designed (the answer goes to that player's setting) but unvalidated (R6). Option rows: the
title's option records are at MEM32(O + 0x10) + 0x14 i (step 0 re-read; an external report's O + 0x28 was wrong); the row
editing is not implemented (no option rows, no help line).
