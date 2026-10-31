# Workbench 0.30: the developer workflow (user guide)

Choose a feature -> configure it -> build / validate / stage -> get a guarded test **plan**. Nothing here starts the game,
approves a plugin, uploads or publishes anything.

Start it: the main Workbench window's **Developer workflow** button, or `py -3 -B wbn_gui.py [--settings FILE] [--kit KIT]`, or
the command line `wbn.py` (DEVELOPER_CLI.md). From a mod kit, **`Burnout Mashup Workbench.exe`** in the kit folder starts the
Workbench window without a console (Python 3.11+ needed; it starts `workbench\workbench.py`). Windows may show "Windows protected
your PC" the first time (the exe is not code-signed): More info > Run anyway.

## 0. Settings (once)
Make an empty settings file and fill in your own paths (relative paths are relative to the file):

    py -3 -B wbn.py settings-template "%USERPROFILE%\mods\wbn-settings.json"

| key | what | needed for |
|---|---|---|
| `kit` | the unpacked mod kit folder. Not needed when this Workbench is the kit's own `<kit>\workbench` (found only when the folder around it holds HOST_INFO.json, tools\bmpack and sdk\BUILD.md) | everything |
| `game_data` | YOUR game data (`...\Burnout 3 Takedown`), read only | staging (bmpack validate) |
| `cc` | llvm-mingw `x86_64-w64-mingw32-clang.exe` | staging (bmpack compiles its checker), plugins |
| `cmake`, `ninja` | CMake / Ninja | plugins only |
| `host_readers` | optional: another bmpack host-readers folder (bmpack's own `--host-readers`); normally empty = the kit's | staging |
| `staging` | an empty folder of yours: staged mods go to `<staging>\<mod id>` | staging |
| `state` | work folders, logs, the last successful output (default: the Workbench's `state\devflow`) | - |
| `bundle` | a tester bundle (bmashup-alpha-tester) for the play plan; `run_preflight: true` also runs its preflight | plan |
| `runner`, `host_exe`, `approvals`, `profile_name`, `predecessor` | the workspace's guarded runner plan (`wb_profile.py`) | plan |

Nothing is guessed: a missing setting stops "Test this project" with SETTINGS INCOMPLETE and names it.

## 1. New project (template)
`wbn.py templates` lists them with their requirements (checked against the kit's `HOST_INFO.json`) and capabilities.

| template | kind | from the kit | capabilities |
|---|---|---|---|
| `tune-data` | data mod | `docs\TUNING_CATALOGUE.json` | `[bmashup.tune]` values; sliders (v3) on verified-range rows |
| `traffic-density` | native plugin | `sdk\examples\traffic` | one traffic density 0.0 .. 2.0 (`docs\services\TRAFFIC.md`) |
| `events-observer` | native plugin | `sdk\examples\events-observer` | observe race events, nothing written |
| `events-v2` | data template | `sdk\examples\events-v2` | World Tour events with names / help - a STARTING POINT: add your own track files |

    py -3 -B wbn.py new tune-data "%USERPROFILE%\mods\takedown bonus" --id yourname.takedown-bonus --name "Takedown bonus" --set "Score/Burnout Points | Takedown BP = 2500"

The folder must be new or empty. A project is a plain folder (`mod.toml`, sources, `README.md` with the standalone commands,
`wbn-project.json`), usable without the Workbench. (The older "New data mod" tab still works; since 0.30 it uses the same host
rules: AI rows get their real limit and `version = 2`.)

## 2. Tune (data mods)
Window tab **2 Tune**. Search a row; the panel shows its type, unit (only when the game's row name carries one), description
(only where the kit has one), default (with its source), the host's limit and rule, and when a change applies.
- **Slider**: only for rows whose range the host declares (the 5 `Effects/Shadow` rows). Every other row says
  "No slider: no verified range ... type a number" - the host's 0 .. 16 x limit is an admission limit, not a tested range.
- **Set value / Remove value / Declare slider** change the pending text only. **Preview changes** shows the exact diff;
  **Save** is enabled only for the previewed text and writes it atomically (the previous file goes to `.wbn\history\`).
  Comments, unknown keys, unknown tables, unknown rows, spacing, CRLF and a BOM stay byte for byte.
- The `[bmashup.tune]` version is raised when an edit needs it (AI rows / negative values -> 2, sliders -> 3), never lowered.
- Problems are listed live; double-click one to select its row and highlight its line.
CLI: `wbn.py tune list|set|remove|slider PROJECT ...` (preview by default, `--save` writes).

## 3. Test this project (plan only)
Window tab **3 Test this project** or `wbn.py test PROJECT --settings FILE`:
settings -> validate -> build (plugins) -> package -> stage -> compat -> approvals -> plan, with progress and **Cancel** (Esc).
- Validation errors stop the run and link to `mod.toml:line [field]` and the editor row.
- Staging uses the Workbench's existing import staging: the previous package is moved to `<staging>\.wb_stage\previous\`,
  never deleted; a failed or cancelled run leaves the staged package, its records and the last successful output unchanged.
- **Compatibility**: the tester launcher's own gate (`vendor\bmcompat.py`) against the kit's host (and the bundle's host).
- **Approvals** (plugins): reported as covered / not covered for the approvals file you name. Never written.
- **Plan**: (a) tester bundle: which host `play.cmd` would start, the profile folders it uses, the copy into `mods\user\` YOU
  would do, blockers (no host, no game data), the bundle preflight result (optional); (b) guarded runner: the `wb_profile.py`
  check of the staged package against `host_exe` and the exact draft / prepare / preflight / dryrun / launch-plan commands.
  A real launch needs the owner and `--authorize-runtime`; the Workbench never runs it.
- **Last successful output**: `wbn.py last PROJECT --settings FILE` (window button) - replaced only by a successful run.

## 4. Without the Workbench
Every project's README.md has the commands, e.g.

    py -3 -B <kit>\tools\bmpack\bmpack.py validate "<project>" --game-data "<game data>" --cc <clang.exe> --cache "<new folder>" --json

## Limitations
- bmpack does not check tune rows, values or sliders; the Workbench's checks follow the host source, the host's start-up check
  ("verified on this game build") remains the final word.
- Kit 0.7.0 as first packaged lacked four host-reader files (`bm_tune_catalog_shadow/_fx/_cam/_cad.inc`), so its bmpack could not
  build its checker; use a kit build that ships them (or the `host_readers` setting).
- Rows without a static default (camera, Air Ram, spark) show "not known offline".
- The editor catalogue (`data\EDITOR_CATALOGUE.json`) describes kit 0.7.0 / host main21; for another kit the editor says so,
  turns sliders off and offers the kit's keys. Regenerate it: `py -3 -B wbn_catalogue.py build --kit KIT [--host-tree TREE]`.
