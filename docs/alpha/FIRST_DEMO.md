# Run the first demo (tester package 0.4.0)

Prerequisite: [INSTALL.md](INSTALL.md) steps 2-5 done, `preflight.cmd` ends with `RESULT PASS`, `prepare.cmd demos` printed OK.

## 1. Start
`play.cmd`. A console window opens with the game window. First start: press START at the title, then A to create the
new profile ("Profile 1"); shader compilation makes the first menus / races hitch a little (cache in `profile\Local`). The first
race of a new profile shows a "Race Training / Rules of the Road" screen: A continues.

Check the log `profile\Roaming\BurnoutMashup\logs\run.log` (or the console):
- `[PLATFORM] host: Burnout Mashup platform 0.1.9, build bmp-0.1.9+2c8142e65f20` and `25 services offered to plugins`;
- one `[MOD]` / `[ADMIT]` line per demo mod, `[DEPS]` with the dependency order, no `refused`, no `FATAL`.

## 2. See the demo content
Controls: an Xbox-style pad, or the keyboard (Takedawn's defaults; the in-game Settings menu lists them). Menu navigation:
D-pad / arrows, A = confirm, B = back.

1. **MODS page** (main menu, the Mods entry): every demo mod listed ON with its version; `bmashup.veh-cross` shows that it
   needs `bmashup.veh-neon`.
2. **Track and car** (Single Event > Race; REGION: right to Europe; TRACK: left from Random = **BM Test Loop**, once more =
   **BM Canyon Ring**; A). In SELECT CAR press right through the series (most retail series are locked on a new profile):
   **DUST RUNNERS**, **NEON** and **BM COUPES** (the authored BM Coupe with its own garage photo) come after the retail ones. Press X to cycle paints: the
   coupe's crimson / gold, Neon Dart's magenta / cyan / gold (gold comes from the cross-mod `bm-veh-cross`). Compact Type 1
   offers the extra paints sunset / ice / moss / chrome. The garage photo follows the paint.
3. **Race on the authored track**: pick the BM Coupe in crimson (X six times), A, race BM Test Loop with 5 rivals.
4. Quit the race (pause = START, QUIT), back to the menu, quit the game. Start `play.cmd` again: your profile and the paint you
   chose for the coupe are still there (`profile\Roaming\BurnoutMashup\bmashup\progress\` holds the paint sidecar).

What is DONOR in what you just saw: the coupe drives, sounds and collides like Compact Type 1 (COMPCAR1); the tracks use the
sky, sound and event set-up of a retail Europe track; Neon / Dust cars are retail models with new names and paints.

## 3. Turn a mod off / remove it
MODS page: switch a mod OFF (saved in the bundle's `mod-list.toml`), restart the game. Or move its folder out of
`mods\demo` / `mods\generated`. Your profile still loads; a car you selected from a removed mod falls back to a retail car.

## 4. If something goes wrong
[TROUBLESHOOTING.md](TROUBLESHOOTING.md). For a report: `diag.cmd` (diagnostic export), then [BUGS_AND_CONTRIBUTING.md](BUGS_AND_CONTRIBUTING.md).
