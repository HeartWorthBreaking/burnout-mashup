# Workbench 0.30 developer workflow - CLI reference (`wbn.py`)

`py -3 -B wbn.py COMMAND ...` - Python 3.11+, standard library. `--json` prints the same records the window shows.
`--kit` may be left out only when this Workbench is the kit's own `<kit>\workbench` (marker files HOST_INFO.json, tools\bmpack,
sdk\BUILD.md in the folder around it); otherwise give `--kit` or the settings file's `kit`.
Exit codes: 0 ok, 1 refused / failed (problems printed), 2 usage, 3 settings missing or unreadable.

| command | does | writes |
|---|---|---|
| `templates [--kit KIT]` | templates + requirements (vs the kit's HOST_INFO.json) + capabilities | nothing |
| `new TEMPLATE FOLDER [--kit KIT] --id ID --name NAME [--module M] [--density D] [--set "Row = v" ...]` | a new project (one rename; new / empty folder only) | FOLDER |
| `catalogue search [TEXT]` | rows: type, unit, default, limit, slider yes / no | nothing |
| `catalogue show KEY` | one row with every field and its source | nothing |
| `tune list PROJECT [--filter TEXT] [--json]` | catalogue rows with the project's values; unknown rows (kept as written) | nothing |
| `tune set PROJECT KEY VALUE [--save]` | preview diff; `--save` writes atomically (+ `.wbn\history\`) | with `--save`: mod.toml |
| `tune remove PROJECT KEY [--save]` | removes the row's value | with `--save` |
| `tune slider PROJECT ROW DEFAULT MIN MAX [--step S] [--label T] [--save]` | a MODS-page slider; refused for rows without a verified range | with `--save` |
| `validate PROJECT [--kit KIT] [--json]` | offline checks; each problem `file:line [field]` + fix + editor object | nothing |
| `test PROJECT [--settings FILE] [--json] [--staging DIR] [--state DIR] [--host-readers DIR] [--bundle DIR] [--run-preflight 1] [--runner FILE] [--host-exe FILE] [--approvals FILE] [--profile-name N] [--predecessor DIR]` | validate -> build -> package -> stage -> compat -> approvals -> launch PLAN | staging, state (and the bundle's diag\ only with --run-preflight) |
| `last PROJECT --settings FILE` | the last successful output (staged path, hashes, plan) | nothing |
| `settings-template FILE` | an empty settings file to fill in | FILE (new only) |

Problem record (validate / test): `{sev, code, msg, fix, file, line, col, field, row, obj}`; `obj` = `tune-row:<key>`,
`tune-slider:<row>`, `tune-entry:<i>`, `manifest:<key>`, `tune-version`, `compat`.

Other tools: `wbn_catalogue.py build --kit KIT [--host-tree TREE] [--out FILE]` (regenerates data\EDITOR_CATALOGUE.json),
`exe\build_wbexe.py OUT.exe --cc <x86_64-w64-mingw32-clang.exe>` (builds "Burnout Mashup Workbench.exe"; deterministic, prints
the sha256). Tests (not shipped in the kit): suites `wbn`, `wbexe`, `datamod` of `tests\run_tests.py`.
