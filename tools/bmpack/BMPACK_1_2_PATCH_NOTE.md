# bmpack 1.2 - patch note (host p3, platform 0.1.1; 2026-10-26)

Copy of the frozen mod kit 0.1.0's bmpack 1.1 (`platform\kit\bmashup-modkit-0.1.0\tools\bmpack`, read only), changed here only.
`bmpack.py` = 1.1 + the anchored edits of `host3\scripts\patch_bmpack_12.py` (17, log `host3\logs\patch_bmpack_12.json`);
`checker\bmpack_check.c` rewritten for p3; `tests\test_bmpack.py` extended; four new specs `specs\bmp_p3_*.toml`.

## Spec (TOML) additions
| table / key | type | mod.toml written | rule (the host's, checked by validate) |
|---|---|---|---|
| `[[event]] name` | string | `[bmashup.extra_events] version = 2`, `names = ["<id> = <name>"]` | 1..19 characters (the longest retail text of the event-list row widget, "COMPACT GRAND PRIX "), A-Z a-z 0-9 space - ' . & |
| `[[event]] help` | string | `version = 2`, `help = ["<id> = <text>"]` | 1..97 characters (the longest retail text of that list's help bar), the same characters + `!`; shown in upper case like the game's own help texts |
| `[tune] set` | list of strings | `[bmashup.tune] version = 1`, `set = [...]` | `"Group \| Name = value"` of the host's tuning catalogue; 0 .. 16 x the game's value |
| `[capacity] lanes / low_unit_bytes / static_bytes` | integers | `[bmashup.capacity] version = 1` + the keys | the engine / streaming services' ranges |
A spec that uses none of these builds byte-identical output to 1.1 (test T12 compares the content pack's mod.toml with
`runtime_data\modsets\bmp_content_set`). A mod with `name` / `help` declares table version 2: a platform 0.1.0 host
(p1 / p2) refuses it ALONE ("needs a newer platform: [bmashup.extra_events] version 2; platform 0.1.0 reads version 1"),
the game starts without it.

## mod.toml schema (host p3)
```
[bmashup.extra_events]
version = 2                                   # 1 still reads as before; names / help need 2
add = ["harbour-night = US_C8_V1 @ US_C3", "harbour-sprint = US_C8_V1 @ US_C3"]
stage = ["harbour-sprint = 020006USC1V1"]     # optional, as before
names = ["harbour-night = Harbour Night"]     # optional: the list row (default: the track's name)
help = ["harbour-night = Race the harbour loop after dark."]   # optional: the help bar (default: "AN EVENT ADDED BY A MOD.")
```
Refusals (exit 92 at the declaration, the event and the reason named): an id not in `add`, a second text for an event, a
length outside 1..19 / 1..97, a character outside the set, `names` / `help` at version 1, a version other than 1 / 2.

## validate (the checker)
- **The admission** (`bm_admit.c`, `bo3_admit_run`) runs where `modfs.c list_mods` runs it: after the manifests, the platform
  gate and the shared-id rule, over the usable mods in the mod list's order, before any service. A refused mod is reported as
  service `admission`: `mod <id> <ver> (<folder>) refused, the game starts without it: <kind> <key>: ... mod <earlier id>
  <ver> (<folder>)`; its declarations are never registered; the other mods read as if it were absent (test T13: the state
  dump with it = without it). Exit 1 (not every mod is used), as for a platform refusal.
- **Text table**: after the events' declarations the host's text table is installed over `Data\Globalus.bin` (relocated as
  the game does); for each event W2 / W3 / W7 run and the JSON gives `name`, `help`, `row_text(_id)`, `help_text(_id)` (the
  strings the game shows) and `retail_row_help_unchanged`.
- **Labels**: each admitted mod's `label` (`changes gameplay: ...`), and the `admission` list (kind, key, other, why, label,
  page text).
- **Progress sidecar**: each added track's shadow is registered as the game does (`bm_tracks_progress.c`); with
  `BMPACK_SAVE_DIR` the sidecar is opened there and saved results are loaded into the shadows.
- `guest_fnv64` (FNV-1a 64 over the whole 64 MB guest image after every step), `tlist_fnv64`, `heap_used`: for state
  comparisons.
- `BMPACK_MUT=11` (tests only): the admission is skipped (p2's behaviour).

## Tests (`tests\test_bmpack.py OUT`, host3\test_runs\bmpack: base 80 / 80, mutants 11 / 11)
T5 / T7: the conflict / capacity refusals of the later mod come from the admission (refused alone); T10: platform 0.1.1, the
"newer table" case uses version 3; T12: names / help / tune / capacity in mod.toml, the resolved row / help texts, the
label, a 21-character name refused at build, 1.1 output unchanged; T13: refused alone, state = without it, reversed roots;
MUT 11 (no admission) caught.
