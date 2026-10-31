# External tester checklist (candidate 0.4.0-rc, launcher)

About 45 minutes. Use a **new empty folder**; tick what you tried and report each problem separately with the feedback
template (`FEEDBACK_TEMPLATE.md`) and a diagnostic export (launcher Help tab). Your PC's details matter most - this
package was only tested on the developers' own PC, so every other PC is new ground.

| # | Try | Expected |
|---|---|---|
| 1 | Double-click `Burnout Mashup.exe` (or `Burnout Mashup.cmd`) | the launcher opens (or, without Python 3.11+, a message says what to install) |
| 2 | Setup: drop your game folder / disc image on the window (or Browse) | progress, then "Done."; game data **ready** |
| 3 | Setup: press Cancel during step 2 once, then run it again | "Cancelled ..."; the second run completes; nothing half-done left |
| 4 | Setup: *Check now* | every line PASS / WARN / INFO with a fix; ends PASS (a FAIL names its fix: did the fix work?) |
| 5 | Setup: *Build demos* | demo car / tracks built; **built** |
| 6 | Mods: list | demo mods listed **on**, OK; native-code mods marked |
| 7 | Mods: follow `docs\FIRST_MOD_TUTORIAL.md` (10 minutes) | BLOCKED with the typo message, then OK after the fix; imported; **on** |
| 8 | Mods: *Turn on / off* one demo mod, then Play | the Play results no longer list it; turn it back on |
| 9 | Play: race once (Single Event > Race), quit | results: mods loaded / admitted, your tutorial mod listed, no FATAL |
| 10 | Play again | saves and settings kept |
| 11 | Help: *Export diagnostics (zip)...* | a zip; open it: no saves, no game files, no user name / computer name |
| 12 | Help: *Back up my profile...* | a backup folder with profile\ and mods\user\ |
| 13 | Update: unpack the package again into a second new folder; there Help: *Bring my data from an older ... folder* | your saves, settings and tutorial mod appear in the new folder; the old folder unchanged |
| 14 | Help: *Remove re-creatable files* | game data copy / demos / work deleted; saves and your mods kept |
| 15 | Window: resize small / large, use only the keyboard (Ctrl+1..4, Tab, Space, Esc, Alt+letters), 125-200 % display scaling | everything reachable and readable |
| - | Do NOT test | expanded-lane (> 64 lanes) workflows, trackconv / Revenge conversion, Linux / macOS (not built), sharing generated mods (they contain your game's data) |

Please also tell us: where you got stuck, anything you had to guess, and any wording that was unclear.
