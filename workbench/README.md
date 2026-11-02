# Burnout Mashup Workbench v0.33 (2026-11-01; track editor: TRACK_EDITOR_GUIDE.md)

A small Windows window over existing tools. It decides nothing itself:
- **release pipeline** `gp\release\release.py` (`plan` = preflight + cache decision per node; `run`; `run --resume`)
- **mod validator** bmpack 1.5.0 from the mod kit 0.6.0 (`tools\bmpack\bmpack.py validate ... --json` / `verify`)
- **verified example recipes** (`wb_stage.py`): p43-coupe-photo (fetex) and sdk-host-info (SDK native plugin, CMake)
- **new plugin projects** (`wb_project.py`, v0.5): your own native plugin under your own identity, built by the same steps
- **new car projects** (`wb_car.py`, v0.12): a car for the kit's carimport (car.toml + glTF), built / validated / staged with
  the kit's carimport, vehtool and bmpack; recipe `carimport-coupe` builds the kit's authored coupe example
- **new track projects** (`wb_track.py`, v0.13): a track for the kit's trackbuild 0.2.1 (description + OBJ + PNG +
  package.toml), built / validated / staged with the kit's tb.py and bmpack; recipe `trackbuild-testloop` builds the kit's demo
- **track editor, first slice** (`wb_trackedit.py` + `trackedit.html`, v0.14): textured 3D view of a track project's SOURCE,
  layers, inspector, validation highlights, one edit kind (move start objects) with undo / redo; not a complete editor
- **material edits + read-only retail view** (v0.15): assign an existing material / set the trackbuild vertex colour of a face
  group (authored projects); `--retail` opens a retail track folder READ ONLY, decoded by the kit's verified readers into a
  separate cache (`wb_retail.py`)
- **material properties + transparency previews** (v0.16): edit an existing material's texture (an existing project PNG),
  surface word, collide and car_solid under the kit's own trackbuild rules; the retail view draws cut-out and blended
  materials from their verified material flags
- **move a face group** (v0.17): translate one selected authored face group by (dx, dy, dz) metres; the kit's trackbuild
  regenerates collision, unit bounds, streaming and visibility from the edited OBJ before the edit applies
- **multi-group moves** (v0.18): Ctrl-click several face groups, move them together (optional offset snapping) either
  isolated (gaps open at the boundary) or kept connected (neighbour faces stretch, previewed first)
- **clip check** (v0.19): a move that trackbuild would clip at the unit regions is refused before it applies, with the faces
  and unit edges named and highlighted (unit regions are never expanded)
- **selection transforms** (v0.20): turn the selected face groups about the vertical axis (optional angle snapping) and / or
  scale them uniformly, about the selection's bounding-box centre or an entered XYZ pivot, with a live preview
- **boundary inspection + welding** (v0.21): open edges highlighted, gap candidates within an explicit tolerance, weld two
  boundary vertices or two matching edge chains after a preview (uv / normal / colour seams kept; no gap filling)
- **layout construction** (v0.22): duplicate the selected face groups (exact copies at an exact offset, appended as new
  groups and selected) and bridge two explicitly selected open-edge chains with new faces after a preview (consistent
  winding, existing material, documented uv mapping; no automatic hole filling)
- the window title shows `wb_core.VERSION` (one constant; v0.22)
- **developer workflow** (v0.30; button "Developer workflow", `wbn_gui.py`, `wbn.py`): template -> tuning editor (searchable,
  host limits, sliders only for verified ranges, byte-preserving, preview before save) -> validate -> stage -> launch PLAN
  (never launches); DEVELOPER_WORKFLOW.md, DEVELOPER_CLI.md
- **test profiles** (`wb_profile.py`, v0.6): a staged plugin + a compatible host, prepared and dry-run through the workspace's
  guarded runner (`tools\runners\g_run.py`); **kit identity / switching** (`wb_kit.py`, v0.6); **Launch -> Stop -> Results**
  (v0.8): one owner-present guarded boot of a prepared profile; **visible manual test runs** (v0.9); **mod preview + draft
  Enable / Disable / Remove** (v0.10); **Import folder -> Validate -> Stage -> Preview** of finished mods (v0.11)

Python 3 standard library only (tkinter). No game launch except the explicit, confirmed Launch of a prepared test profile
(v0.8, through g_run with its token), no upload / push / publishing, no install into the game, no free
command field, no automatic updates, no deletion, never approves native code.

## Start (first time: set the paths once)
```bash
py -3 -B workbench\workbench.py        (from the mod kit folder; the Workbench finds this kit by itself)
```
**v0.4: there are no built-in developer paths.** On a fresh install the status bar says "Settings incomplete". In the
**Settings** tab: **Discover** (lists candidates per field with where each was found; applies nothing) -> pick a value in each
field (drop-down, type, or **Browse...**) -> **Check** (per-field OK / problem) -> **Save** (writes `workbench.json` beside the
script; refused while a filled-in field does not check out; empty fields are saved as "not set"). The same without the window:
```bash
py -3 -B wb_core.py config
py -3 -B wb_core.py config --kit "<kit>" --cc "<clang.exe>" --cmake "<cmake.exe>" --ninja "<ninja.exe>" --game-data "<data>" --pipeline "<release>" --save
py -3 -B wb_core.py config --use-discovered --save
```
(`config` prints settings + sources + problems, the protected roots and the discovered candidates as JSON; `--use-discovered`
fills only empty settings from the first candidate, still only saved with `--save`; `--protect DIR` (repeatable) sets the extra
protected folders.) Lookup per setting, highest first: option (`--kit` ...) > `workbench.json` (or `--config FILE`) > the kit's
documented environment / PATH lookup (`BMKIT_CC`, `BMKIT_LLVM_MINGW`, `BMKIT_GAME_DATA`, `cmake.exe` / `ninja.exe` /
`x86_64-w64-mingw32-clang.exe` on PATH) > not set. Discover also offers kits found next to the Workbench folder, the kit's
`bmkit.toml`, a `release\` next to it, and (only when the script is inside the developer workspace) the workspace's toolchain,
kit and game data, labelled "developer workspace"; none of these is used unless it is put in a field.

| setting | needed by | check |
|---|---|---|
| Mod kit | every recipe, Mod validation | `tools\bmpack\bmpack.py` + `sdk\BUILD.md` |
| C compiler | SDK plugin recipe, Mod validation | llvm-mingw `bin\x86_64-w64-mingw32-clang.exe` |
| CMake, Ninja | SDK plugin recipe | `cmake.exe`, `ninja.exe` |
| Game data | Mod validation, p43 recipe | `Data\PrgData.bin`, `stagehed.bin`, `Globalus.bin` (read only) |
| Release pipeline | Release tab | `release.py` |
| bmpack checker cache / logs / lock | (fixed) | `<workbench>\state\bmpack_cache`, `<workbench>\logs`, `<workbench>\state\OPERATION.lock` |

The developer workspace values (for this machine): kit `gp\alpha_rc\v060\prose_final\kit_unpacked\bmashup-modkit-0.6.0`,
`toolchain\llvm-mingw-x\llvm-mingw-20260922-ucrt-x86_64\bin\x86_64-w64-mingw32-clang.exe`, `toolchain\cmake\cmake-4.4.4-windows-x86_64\bin\cmake.exe`,
`toolchain\ninja\ninja.exe`, `runtime_data\base\Burnout 3 Takedown`, `gp\release` (Discover lists them; `config --use-discovered --save`
saves them).

The same backend works without the window (one verdict per call):
```bash
py -3 -B wb_core.py plan  "<spec.json>" [--pipeline DIR] [--cache DIR]
py -3 -B wb_core.py run   "<spec.json>" [--cache DIR] [--jobs 4] [--no-publish] [--resume RUN_ID]
py -3 -B wb_core.py validate "<mod or mod set folder>" [...]      |  wb_core.py verify "<mod folder>"
```
Exit codes: 0 OK, 1 failed / refused, 3 not started (spec problem or missing prerequisite), 4 another operation is running.

## Release tab
1. **Release spec**: the list shows `release_spec*.json` of the pipeline folder; **Browse...** takes any spec file. The line below
   shows release id, nodes, deliverables, checks and versions, read from the spec.
2. **Cache**: preselected = the cache of this spec's newest run (from the pipeline's own `runs\*\summary.json`), else `cache`.
   For `release_spec_v060.json` that is `cache_v060`.
3. **Check spec**: structure only (JSON, schema `bm-release-spec/1`, required sections, workspace root).
4. **Preflight** = `release.py plan`: the pipeline's own preflight (sources, toolchains, policies, disk) and, per node, its cache
   decision (`cached` / `would build (reason)` / `depends on a node that must be built first`). Executes nothing.
5. **Build release** = `release.py run --label wb<time>` (with **Publish outputs** unticked: `--no-publish`). The progress bar
   counts finished nodes from the run's journal. The result shows the pipeline's verdict (`COMPLETE`, `COMPLETE - RUNTIME
   ACCEPTANCE REQUIRED (owner)`, `CHECKS FAILED`, `FAILED`), nodes built / from cache, failed nodes and checks with their first
   issues, the runtime-acceptance status and the output folder.
6. Buttons below: **Full log**, **Run folder**, **summary.json**, **Output folder**, **RELEASE_MANIFEST**, **PUBLISH_PLAN**
   (enabled when the file exists). Outputs go where the pipeline always puts them: `gp\release\runs\<id>`, `gp\release\out\<id>`
   (local only; `PUBLISH_PLAN.json` is a plan, nothing is uploaded).
7. **Cancel** stops the whole process tree (`taskkill /T /F`). The pipeline's actions run in job objects (they die with it),
   its cache lock is stale once the pid is gone and its staging is cleared by the next run; cache entries and `out\<id>` are
   written only after success. A cancelled run shows **Resume** (`release.py run --resume <id>`).

A real build of the current `release_spec_v060.json` builds the main20 host and all packages into the shared `cache_v060`
(about 2 minutes cold) and today ends `CHECKS FAILED` on `frozen_baselines` (KB `HANDOFF.md` / `INDEX.md` prefix changed since
the snapshot; pre-existing, not a Workbench issue).

## Mod validation tab
Add one or more **mod folders or mod set folders** (game load order = list order); game data / compiler / kit come from the
Settings tab (v0.4). Then:
- **Validate** = `bmpack validate ROOT.. --game-data .. --cc .. --cache .. --json`: ACCEPTED / REFUSED, each mod with its version
  and usable flag, refusals as `[service] mod: reason` (the host's own reasons), tracks / events added. The first run compiles
  the checker (about a minute) unless the cache already holds it.
- **Check files of selected mod** = `bmpack verify MOD_DIR`: OK or the files that differ from `bmpack.json`.

## Example mod tab: Build -> Validate -> Stage (v0.2; v0.4 guards)
One verified recipe (`wb_stage.RECIPES`): **p43-coupe-photo**, the kit's authored garage-photo pack
(`examples\authored\bm-coupes\p43-coupe-photo`; kit README: `fetex.py pack photo_spec.json art\photo.txd`).
1. **Example project**: preset to the kit example; another folder is accepted only if its `mod.toml` id is the recipe's
   (`bmashup.p43-coupe-photo`) and it has `photo_spec.json`.
2. **Staging folder**: a new or empty folder, or one the Workbench staged before. v0.4 refuses (wherever the Workbench is
   installed): the configured game data, kit, release pipeline and **extra protected folders** (Settings), the source project,
   the Workbench's logs / state, `%APPDATA%\Takedawn` / `%LOCALAPPDATA%\Takedawn` (a separate upstream install's saves), the
   existing entries of `%APPDATA%\BurnoutMashup` other than its `workbench\` folder (Burnout Mashup saves), and - only when the script is inside
   the developer workspace - its `runtime_data\base|runs|modsets`, `roots`, `build`, `gp\release`. **Markers**, checked on the
   destination and every folder above it: `default.xbe` or `Data\PrgData.bin` (retail data), a folder holding such a game data
   folder one level down, `burnout3*.exe` / `takedawn*.exe` (game / host executables), `plugin-approvals.toml` (saves),
   `release.py` / `RELEASE_MANIFEST.json` / `PUBLISH_PLAN.json` (releases), `FROZEN.md` (frozen baselines), a mod kit, a
   `mod.toml` above it (inside a mod), sealed folders (a `SHA256SUMS*.txt` listing files there). Also a drive root and a
   non-empty folder the Workbench did not make.
3. **Build -> Validate -> Stage**: copies the project to `<staging>\.wb_stage\work\<time>\p43-coupe-photo`, runs `fetex pack` there,
   then `fetex validate --class frontend` and `bmpack validate --json` (game data + compiler from the Mod validation tab). Only
   if all pass is the package moved to `<staging>\p43-coupe-photo`; an earlier one moves to `.wb_stage\previous\<time>\`.
   `.wb_stage\STAGE.json` records source and package hashes, the bmpack verdict and whether `photo.txd` equals the launched p4.3
   file; `history.jsonl` lists every stage. Nothing is ever deleted.
4. A failed, refused or cancelled attempt leaves the staged package unchanged; its folder (with `ATTEMPT.json`) stays for
   diagnosis (**Attempt folder** button). Buttons **Staged package**, **STAGE.json**, **Full log**.

CLI: `py -3 -B wb_stage.py "<project>" "<staging folder>"` (exit 0 staged, 1 failed, 3 not started, 4 busy).

## Second recipe (v0.3): SDK native plugin example `sdk-host-info`
`wb_stage.RECIPES['sdk-host-info']`: the SDK's example (h) `sdk\examples\host-info` (mod id `bmashup-sdk.host-info`; it only logs
the host's version, build and services, changes nothing, reads no game data). Same CLI / tab / destination guard / transaction:
```bash
py -3 -B wb_stage.py "<kit>\sdk\examples\host-info" "<staging folder>" [--kit DIR] [--cc FILE] [--cmake FILE] [--ninja FILE]
```
- **Prerequisites** (kit `docs\PREREQUISITES.md`, `sdk\BUILD.md`): llvm-mingw clang (`--cc` = `<llvm-mingw>\bin\x86_64-w64-mingw32-clang.exe`),
  CMake 3.20+ (`--cmake`), Ninja (`--ninja`). Order (v0.4): option > `workbench.json` (Settings) > `BMKIT_CC` /
  `BMKIT_LLVM_MINGW` (clang) > PATH; the workspace toolchain only as a Discover candidate. A missing or wrong tool stops before anything runs (exit 3) with
  what to give and where to download it (URL + sha256).
- **Build** = the BUILD.md "By hand (CMake)" commands for one example, as fixed argument lists (tool and folder placeholders only):
  `cmake -S <src> -B <build> -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MAKE_PROGRAM=<ninja> -DCMAKE_TOOLCHAIN_FILE=<sdk>/cmake/llvm-mingw-x86_64.cmake -DLLVM_MINGW_ROOT=<llvm-mingw>`,
  then `cmake --build <build>`, in `<staging>\.wb_stage\work\<time>\` (`src\sdk\` = copies of the kit's `sdk\cmake`, `sdk\include`
  and the project at `examples\host-info`). The project's `CMakeLists.txt` must be byte-identical to the kit's (sha256 pinned in
  the recipe); otherwise nothing is configured, because CMake would run the project's own commands.
- **Validate** (in-process, nothing executed): package = exactly `bm_sdk_host_info.asi` + `mod.toml`; mod.toml id, `[plugin] api = 1`,
  `windows` = the built module, mod.toml = the project's; PE32+ x86-64 DLL exporting `takedawn_plugin_api_version` and
  `takedawn_plugin_init`; link time stamp 0 (reproducible bytes). The comparison with the kit's `sdk\EXPECTED_BUILD_SHA256.txt` is
  recorded (`reference_match`); a different llvm-mingw gives other bytes, which are not refused. bmpack validate is not run (it
  needs game data; a code-only mod has no content for it to check).
- **STAGE.json** adds `kind: sdk-plugin`, `kit`, `sdk_files` (sha256 of the copied cmake / include files), `tools` (path, sha256,
  `--version` line of clang, cmake, ninja; llvm-mingw root), `build_steps`, `validation`, `module` (sha256, exports, imported DLLs),
  `reference_expected`, and `native_code: {approved: false, sha256, note}`. **The Workbench never approves native code** and never
  writes `plugin-approvals.toml`; the player approves the recorded sha256 (kit `docs\INSTALL.md`). Nothing is installed.
- Reference result (2026-10-28, llvm-mingw 20260922 + CMake 4.4.4 + Ninja 1.13.2): `bm_sdk_host_info.asi` 4952a4c403df,
  `mod.toml` 2fae2d770c69 = the kit's expected bytes = the direct CLI build.
- Copies elsewhere (v0.4): no built-in paths at all; `PC` (workspace) is only known when the script is at
  `<PC>\research\native_gameplay_api\platform\gp\workbench` and then only labels Discover candidates and adds the workspace's
  protected folders. Verified with a copy under `%TEMP%` (path with spaces, no tools on PATH, no BMKIT_*): exit 3 with what to set,
  Discover finds only the copied kit, `config ... --save`, then STAGED with the reference bytes (tests c01).

## Plugin modes (v0.4): reference example / custom source
Both modes run exactly the same approved SDK build steps; a changed `CMakeLists.txt` is always refused.
- **reference**: the project is file-for-file the kit's `sdk\examples\host-info`. The output must equal the kit's
  `sdk\EXPECTED_BUILD_SHA256.txt` (check "reference bytes"); another toolchain's bytes fail validation. Asking for reference mode
  with changed sources is refused before anything runs.
- **custom**: changed sources (C file, mod.toml) on the kit's pinned `CMakeLists.txt` - found by that build script, so the mod id
  may be your own. Other output bytes are allowed; every structural check still applies (package files, mod.toml id = the
  project's valid id, `api = 1`, `windows` = the module, PE32+ x86-64 DLL, `takedawn_plugin_api_version` + `takedawn_plugin_init`
  exported, time stamp 0). The staged folder name stays `bmashup-sdk-host-info` (MOD_DIR in the pinned script).
- **auto** (default, GUI and CLI `--mode auto|reference|custom`): reference when the project equals the kit example, else custom.
- STAGE.json adds `mode`, `reference_required`, `source_changes` (files differing from the kit example), `output_files`; with
  `source_files`, `sdk_files`, `tools` and `module` it records source, SDK, tool and output hashes.
- **Structural checks are no proof that native code is safe.** The Workbench never approves or installs a module
  (`native_code.approved` is always false); the player reviews the source and approves the recorded sha256 (kit `docs\INSTALL.md`).

GUI: Example mod tab -> **sdk-host-info** (preset to the kit example) or **Browse...** to your copy -> staging folder -> plugin
mode -> **Build -> Validate -> Stage**. Tool paths come from the Settings tab; a missing tool is shown at once (NOT STARTED, with
the download link). The GUI and the CLI give the same package, STAGE.json fields and summary lines (tests g02).

Remaining limits: Windows x64 only; one SDK example (host-info) is wired; the staged module was not loaded or launched; custom
mode keeps the example's file names (one C file `bm_sdk_host_info.c`, module `bm_sdk_host_info.asi`); outside the developer
workspace, folders that are not configured and carry none of the markers are not protected (add them under Settings ->
extra protected folders); the window was driven by scripted button presses, not by a person; no machine-specific
locations are built in (the public default list is empty: add your own under Settings -> extra protected folders).

## New plugin project (v0.5)
Tab **New plugin project**: project folder (new or empty), **mod id** (namespaced, lower case: `yourname.my-plugin`), **display
name**, **module name** (`my_plugin` -> `my_plugin.c`, `my_plugin.asi`) -> **Check** -> **Create project** -> **Use in Build /
stage** -> staging folder -> **Build -> Validate -> Stage**. Same without the window:
```bash
py -3 -B wb_project.py new "%USERPROFILE%\mods\my plugin" --id yourname.my-plugin --name "My plugin" --module my_plugin
py -3 -B wb_stage.py "%USERPROFILE%\mods\my plugin" "%USERPROFILE%\mods\staged"
```
- **What is made**: `mod.toml`, `<module>.c` (minimal plugin following the kit's SDK example (h) host-info: the API version
  export, `takedawn_plugin_init`, a load and a shutdown log line), `workbench-project.json` (declared identity + sha256 of the
  kit template files), `README.txt`. **No build script.** The project appears in one rename, complete or not at all.
- **Build**: recipe `plugin-project` = the SDK by-hand CMake steps of sdk-host-info, with the Workbench's own CMakeLists.txt
  (`wb_project.project_cmake`, from the validated names only) written into the build copy. A `CMakeLists.txt`, `*.cmake`,
  CMake presets, `Makefile`, `build.ninja` or `*.ps1/.bat/.cmd/.sh` in the project is refused, never run. Every top-level
  `*.c` beside `<module>.c` is compiled too.
- **Identity, used consistently**: staged folder = the mod id, module = `<module>.asi`, source = `<module>.c`, mod.toml `id` /
  `name` / `[plugin] windows` = the declared ones (re-checked before every build; a mismatch is NOT STARTED).
- **Refused**: invalid names (mod id not namespaced, upper case, spaces, `/ \ ..`, reserved namespaces `bmashup.`,
  `bmashup-sdk.`, `takedawn.` ..., Windows device names; display name with quotes / backslashes / line breaks; module not a
  lower-case C name, a CMake target name, or the kit's module), a relative path or `..`, an existing non-empty folder (never
  overwritten), a missing parent, the kit, game data, protected / sealed / frozen folders, a folder inside a staging folder.
  Staging: `<dest>\<mod id>` is replaced only by the same mod id from the same project (a different mod, another project with
  that id, or a folder the Workbench has no record of is refused). Missing tools: creating works (warning), staging is NOT
  STARTED with the download link.
- **Records**: STAGE.json (latest) plus `.wb_stage\packages\<mod id>.json` per package: identity, build_script (owner, sha256,
  sources), source / SDK / tool / output hashes, validation, `native_code.approved: false`. Mode `project` (no reference bytes;
  asking for reference mode is refused). The kit examples' reference / custom workflows are unchanged.
- **Machine-specific files** (`workbench.json`, `logs\`, `state\`, `test area\`) are listed in `.gitignore`; never commit or
  package them.

## Kit identity and switching (v0.6)
- **Kit identity** (`wb_kit.kit_identity`, Settings shows it): `kit-<version>+<sha12 of MANIFEST.json>` plus the sha256 of the SDK
  headers / CMake files / host-info template, the SDK version and the kit's reference host (name, build identity, sha256,
  platform, the offered services from `tools\bmpack\host_readers\...\bm_platform_table.h`). Content-based: a copy of the same
  kit has the same identity. `py -3 -B wb_kit.py identity [KIT]`.
- **Recorded in**: new projects (`workbench-project.json` `kit` + `kit_history`), every staged package (STAGE.json and the
  per-package record: `kit_identity`; summary line "built with kit ..."), every test profile (PROFILE.json kit at prepare and
  the package's kit, PREFLIGHT.json / DRYRUN.json kit).
- **Change the kit**: Settings -> Mod kit field -> Check (or Save). On a different identity the window clears its cached
  results (last result, last created project, last profile check) and shows `KIT CHANGED` with the differences and what is now
  stale. Nothing is migrated:
  - a project bound to another kit is **not built** (`kit binding: bound to kit ..., the current kit is ...`); **Rebind project
    to current kit** (Build / stage tab, or `wb_project.py rebind FOLDER`) is the explicit step. It changes only
    `workbench-project.json` (previous binding -> `kit_history`). The next Stage moves the old package to
    `.wb_stage\previous\<time>\` (kept). Projects from v0.5 have no binding ("unbound") and are bound the same way.
  - a test profile's preflight made with another kit is **stale**: Dry run refuses it until Preflight runs again.
  - the bmpack checker cache needs nothing: bmpack keys it by the host-reader sources it compiles.
- **Kit identity is not compatibility**: whether a package may run on a host is decided by the host's service table
  (platform version, `[bmashup] requires`, `[plugin] api`), so a package built with kit 0.6.0 may be tested while kit 0.4.3 is
  current, and on kit 0.4.3's host when what it needs is there. A host is described by a kit whose reference host it is
  (the current kit, or the kit the package was built with); a host no such kit describes is refused (services unknown).

## Test profile tab (v0.6)
Fields: **staged plugin package** (`<staging folder>\<mod id>` with its Workbench record), **host exe** (a host folder under the
workspace `build\`: exe + SDL2.dll + shaders, e.g. `build\main19final_acc\burnout3_bmashup.exe`), **your approvals file**
(`plugin-approvals.toml` format, written by you or the game's MODS page), **new profile folder**
(`runtime_data\modsets\wbp_<name>`). Buttons:
- **Check**: module sha256, host sha256 / build identity / platform / which kit describes it and its service count, the
  plugin's requirements, approval status, kit note - and every refusal. Writes nothing.
- **Prepare**: the same checks, then the runner's own `g_run.py make-root <name>` (runtime_data\base copied and SHA-256
  verified, marker `.g_disposable.json`) and, in one rename, `runtime_data\modsets\<name>\` = `PROFILE.json`,
  `plugins\<mod id>\{mod.toml, <module>.asi}` (copies verified), `state\mod-list.toml` (all on), `state\plugin-approvals.toml`
  (only your line for these bytes, copied from your file with its sha256). About 11 s.
- **Preflight**: module / host bytes = the recorded ones, staged package unchanged, approval line present, compatibility
  rechecked with the current kit, root unused, no game running -> `PREFLIGHT.json`.
- **Dry run**: needs a valid preflight (re-checked, not trusted); `g_run.py run td_run --dry-run --data-root ROOT -- RUN --data
  ROOT --scene boot --boot-secs 20 --exe HOST --saves empty --env BMASHUP_MODS=... BMASHUP_MOD_LIST=...
  BMASHUP_PLUGIN_APPROVALS=...` into a new `runtime_data\runs\<name>_dry[N]` -> `DRYRUN.json` (REFUSED 0, WOULD_LAUNCH 1,
  LAUNCH 0, root still unused, the token a real run would need). About 21 s. **The game is not executed.**
- **Profile status**: preflight valid / stale (why) / none, last dry run.
- **Refused** (nothing written): a profile folder outside `runtime_data\modsets`, nested, existing (also its root or dry-run
  folder), not named `wbp_...`, with `..` or relative; a host outside `build\`, without SDL2.dll or a platform build identity,
  or that no known kit describes; requirements the host does not meet (`needs bmashup.camera >= 3; this host (platform 0.1.9)
  offers version 2`, `needs platform >=0.1.9; this host is platform 0.1.6`); no approval, or one for other bytes; module or
  package files changed since staging. A failed Preflight / Dry run keeps the profile's earlier PREFLIGHT / DRYRUN record (only
  `history.jsonl` grows); a failed Prepare leaves no profile folder.
- **Never**: approving code (the approval line is yours), launching the game outside the v0.8 Launch below (a real run needs the owner present and
  `--authorize-runtime RUN:SHA12`, `tools\runners\README.md`), touching saves (`--saves empty`; APPDATA / LOCALAPPDATA go to
  the run folder), the game installation or other mod sets / roots.
- CLI: `py -3 -B wb_profile.py check|prepare PACKAGE HOST PROFILE --approvals FILE`; `wb_profile.py status|preflight|dryrun PROFILE`.

## Multi-mod test profiles (v0.7)
A profile now holds **several staged packages**: native plugins and data-only mods (e.g. the staged `p43-coupe-photo` pack).
- **Members** (Test profile tab): a list with Mod ID, version, kind (plugin / data), hash (module sha256 or files digest),
  requirements (platform, services / tables, plugin API, `requires_mods`) and approval status. **Add** (the package field),
  **Remove selected**, **Save draft...** / **Load draft / profile...** (a draft is a small JSON file: packages, host, approvals
  file, profile folder, predecessor). With the list empty, the single package field works as in v0.6.
- **Admission = the host's own rules**: Check, Prepare and Preflight run the kit's own `bmpack validate` (its `configure` +
  `validate`, as `bmpack.py validate --json` does) with the host readers of **the kit that describes the host**: modfs order,
  shared ids, the loader's 256-mod cap, the platform gate, `requires_mods` order / missing / too old / cycles, cross-mod clashes
  (e.g. two mods setting the same tune value). The Workbench adds only layout checks (each mod id once, a package listed once).
  Check passes every package folder as its own root in mod-id order (= one mod set ordered by id); Prepare runs it again on the
  assembled `plugins\` folder before any data root is made, Preflight on the profile's `plugins\`.
- **Compatibility** by offered capabilities: services and `[bmashup.<table>]` readers (`T(...)` in `bm_platform_table.h`;
  v0.7 reads both - v0.6 read only services, which wrongly refused a data mod needing `bmashup.textures`), never by kit version.
- **Approvals**: one approvals file you choose; every plugin module needs its exact-bytes line in it; data-only mods need none;
  the profile's `state\plugin-approvals.toml` gets only the plugin lines (copied, with the source file's sha256). Nothing is
  approved automatically.
- **Profile layout** (schema `bm-workbench-profile/2`): `PROFILE.json` (host first, then `members` - mod id, version, kind,
  package + record path + record sha256, every file's sha256, digest, module sha256, requirements, package kit identity,
  approval line / source -, `load_order` and `admission` from the host's readers, kit identity, approvals, predecessor,
  changes, root), `plugins\<mod id>\<package files>` (the BMASHUP_MODS root; name kept from v0.6), `state\`, `results\`,
  `history.jsonl`. A one-plugin profile also keeps the v0.6 top-level fields.
- **Stale results**: every successful Preflight / Dry run is kept in `results\<kind>_<time>.json` (PREFLIGHT.json / DRYRUN.json =
  the latest). Profile status lists them all, each `valid` or `STALE` with the reason: kit changed, membership changed (a
  folder added / removed under `plugins\`), files of a mod changed, host bytes changed, PROFILE.json changed since Prepare.
  Dry run needs the latest preflight valid.
- **Immutable profiles, successors**: an existing profile folder is never prepared again. Load a profile (Load draft /
  profile -> its members, host and approvals source, "Successor of" filled, no profile folder), change it, choose a new
  name, Prepare: PROFILE.json records `predecessor` (path, PROFILE.json sha256, members) and `changes` (added / removed /
  other bytes / host / kit); preflight and dry run start again (`progress`); the predecessor is unchanged except one
  `superseded` line in its history.jsonl, and its results appear in the successor's status as STALE history. **Data root**:
  with "reuse the predecessor's data root" (default) a successor adopts the predecessor's root while it is unused and
  verified (no second 2.4 GB copy; `root_mode` says so); once either profile runs for real, the other's preflight reports the
  root as used. Untick it (CLI `--new-root`) for a fresh `g_run make-root`.
- **v0.6 profiles** (schema /1) are read: status, preflight, dry run, and Load as the predecessor of a successor.
- CLI: `wb_profile.py check|prepare PACKAGE [PACKAGE ...] HOST PROFILE --approvals FILE [--predecessor DIR] [--new-root]`,
  `check|prepare --draft FILE`, `draft FILE [--add PACKAGE] [--remove MOD_ID|PACKAGE] [--host EXE] [--approvals FILE]
  [--dest DIR] [--from-profile DIR] [--predecessor DIR] [--new-root]`, `status|preflight|dryrun PROFILE`.

## Launch -> Stop -> Results (v0.8)
One REAL guarded boot of a prepared profile, only with the owner present. The Workbench adds no launcher of its own: it runs
the existing `g_run.py run td_run --authorize-runtime RUN:SHA12 ...` (nothing parallel) and records what happened.
- **Launch...** (Test profile tab; the profile in "New profile folder") first shows the **launch plan**: the profile folder and
  its PROFILE.json sha256, the host path, full sha256, build identity, platform and its bytes now, every mod's id, version,
  kind, module sha256 / files digest and approval line, the approvals source, load order, preflight and dry-run state (valid /
  stale / none, with time and why), the data root and its marker, the new run folder `runtime_data\runs\<profile>_run1`, the
  token, the exact g_run command and a plan id. Then it asks (Yes / No) with the token. CLI: `wb_profile.py launch-plan PROFILE`,
  then `wb_profile.py launch PROFILE --authorize-runtime RUN:SHA12 [--plan-id ID]`.
- **Token**: RUN = `<profile>_run1`; SHA12 = the first 12 hex digits of the exe sha256 that **the runner** validated in the
  profile's dry run (its `WOULD_LAUNCH` guard event), which must equal the profile's host bytes and data root.
- **Rechecked immediately before the start** (under the operation lock and a per-profile `results\LAUNCH.lock`): every member's
  and the host's bytes, approvals, host admission, the latest preflight and dry run valid (not stale), root marker unused, no
  game running, the token, and the plan id (anything changed since the plan was shown -> refused).
- **Refused, nothing started** (no runner call, no run folder, no root): a running operation (this or another window), a second
  launch of the profile, stale or missing preflight / dry run, changed member or host bytes, a missing approval, a used root,
  an existing run folder or launch record, a game already running, a wrong token or changed plan. Prepared profiles stay
  immutable; a launch only adds `results\launch_<time>.json`, `LAUNCH.json` and history lines.
- **Used roots**: one real launch per profile root. A spent root (e.g. the v0.7 profiles `wbp_m1028222237_combo` / `_succ` /
  `_own`, which share the root `_own_run1` used) is never reused or repaired: prepare a **successor with a new root** (untick
  "reuse the predecessor's data root", CLI `--new-root`). Since v0.8 a successor that would reuse a used root is refused
  (v0.7 silently planned a new root).
- **Stop** (or Cancel, closing the window, CLI Ctrl+C) ends only what this launch owns: the game pid from this session's guard
  `POPEN` event, verified as a descendant of this launch's g_run pid (Toolhelp snapshot, creation times) with that image, gets
  `TerminateProcess(STOP_EXIT_CODE 0x5770)`; if the runner has not ended `STOP_GRACE` (50 s) later, or no game is recorded yet,
  the runner's own tree is ended by pid (`taskkill /PID <g_run pid> /T /F`). Never by image name. Who stopped is recorded.
  A wall limit (150 s) stops a launch the same way (class timeout).
- **Results** (button / `wb_profile.py results PROFILE` / Profile status): each launch is one class:
  normal exit (the game ended by itself, code 0) / runner stop: boot-window end (td_run's boot scene ends the game with
  `Popen.terminate()` = TerminateProcess(game, 1) after its alive() check: **ok true + exit_code 1 = this**, see the workbench
  CHECKPOINT "v0.8 STEP 1") / operator stop (+ who) / timeout (Workbench wall limit or td_run's own) / probe / host STOP (the
  host's documented deliberate start stops, exit 88-97) / crash (NTSTATUS such as 0xC0000005, another non-zero code, or FATAL
  lines) / runner refused (no launch) / UNRESOLVED (e.g. no result.json). Each record links the run folder, session folder,
  log.txt, result.json, guard_events.jsonl and summary.json (buttons below the output) and says whether the profile's `state\`
  files changed. **Visual correctness is never claimed**: `[FETEX] ... registered` or `[PLUGIN] ... running` lines show loading only.

## Visible manual test runs (v0.9)
Same Launch / Stop / Results, same checks (approvals, identity, preflight, used root, token, plan id); no host or runner
change. **Launch preset** row in the Test profile tab (CLI `--preset`):
| preset | what td_run gets | duration | evidence |
|---|---|---|---|
| `boot` headless boot smoke (default, = v0.8) | `--scene boot --boot-secs 20` headless | 1-300 s | log, result.json, guard events |
| `visible` visible manual test | the same + `--window` (game window shown, you can play) + `--dump-flips` | 10-1800 s (default 300) | + guest frame dumps, + window captures |
- **Frame dumps** (default flips `600,1800,3600` = about 10 / 30 / 60 s): the host's own `RECOMP_FB_DUMP`, 640x480 BMPs in the
  run folder: `fb_flip_<flip>.bmp` for each requested flip, plus numbered `fb_NNN.bmp` (the host dumps "flip ranges"). The
  game's own frame: no overlay.
- **Window captures** (default every 30 s, and always just before a Stop / timeout; **Capture now** during the run):
  `wb_capture.py` = the PrintWindow method of `gp\modsmenu\runtime\tools\winshot.ps1`, but the window is found by the pid this
  launch owns (winshot.ps1 selects `main20m` by image name). PNGs in the profile's `results\launch_<time>_captures\`, with a
  simple brightness check. v0.21: captured in the window's OWN pixel space under display scaling (a DPI-unaware window at
  300 % is captured at its own size, not as a 3x bitmap with the content in one ninth; the JSON `dpi` field gives awareness,
  window / monitor DPI, scale, physical and own sizes; `tests\test_capture_dpi.py`). They show what the window showed, overlay included (e.g. the host's banner "Test script is driving
  the controller - press a button to take over", because td_run sets a live pad file; pressing a button takes over).
- **Stop behaviour** (shown in the plan): Stop / Cancel / closing the window / Ctrl+C ends only this launch's game pid
  (TerminateProcess 0x5770). td_run's boot scene notices only when its sleep ends: when that is further away than the stop
  grace, the runner's tree is ended (by pid) 10 s after the stop and **td_run writes no result.json**; the counts then come
  from guard_events.jsonl. The Workbench keeps its own handle on the game, so its exit code is recorded either way.
- **Results**: manual stop (operator, with who) / runner stop (end of the duration, exit 1) / timeout (wall limit = duration +
  130 s) / crash (from td_run, or from the Workbench's handle when the game ends early: the runner is then ended 10 s later) /
  normal exit (e.g. you closed the game window: exit 0) / host STOP / runner refused / UNRESOLVED.
- **Successor (new root)...** (CLI `wb_profile.py successor PROFILE --dest NEW [--check]`): an explicit successor of the profile
  in the folder field with the same members, host and approvals source, and ALWAYS a new data root (`g_run make-root`, ~2.4 GB).
  Check is shown first, then a confirmation; the predecessor only gets a `superseded` history line. Then Preflight, Dry run,
  Launch. (The dry run validates the headless argv; `--window` / `--dump-flips` are checked by the runner's guard at launch.)
- Visual correctness is never inferred: a mod's art is shown only if its screen is reached and captured (the p43 photo needs
  the garage; the v0.9 real run reached the title screen only).
- Usage: `wb_profile.py launch-plan PROFILE --preset visible [--secs 300] [--dump-flips 600,1800,3600] [--capture-every 30]`,
  then `wb_profile.py launch PROFILE --preset visible ... --authorize-runtime RUN:SHA12 --plan-id ID` (same options), Ctrl+C =
  Stop; or the GUI: preset row -> Launch... -> (play) -> Capture now / Stop -> Results.

## Mod preview and profile drafts (v0.10)
Look at a mod before it joins a profile, then switch members on / off in the draft. Nothing here launches, deletes,
approves or changes a prepared profile.
- **Start from mod folders**: a staged package (`<staging folder>\<mod id>` with its Workbench record) or a **plain mod
  folder** (a `mod.toml` bmpack can read). A plain folder can be previewed, but only staged packages can join a profile
  (Check refuses a folder without a staging record: the profile records the bytes the staging verified; since v0.11 use
  **Import folder** below to stage it). **Archives
  (.zip etc.) are deferred**: no verified extraction exists in the Workbench or the kit; unpack into a new folder yourself.
- **Preview...** (Test profile tab: the package field, else the selected row; CLI `wb_profile.py preview MOD_FOLDER
  [--draft FILE|PROFILE_DIR] [--host EXE] [--approvals FILE] [--json]`) - read only, against the current draft:
  | label | what | from |
  |---|---|---|
  | DECLARED | id / version / name / description, content kinds (`[plugin]`, each `[bmashup.<table>]`), the declared gameplay changes (each table's entries, e.g. a tune `set` line, a txd), requirements (platform, services / tables, plugin api, `requires_mods`), the staging record (recipe, recorded module sha256, kit, `native_code.approved`) | mod.toml, staging record |
  | VERIFIED | every file's sha256 now, by extension, digest, "= the staging record" or DIFFERENT; the native module's exact sha256 and whether it is the record's bytes; approval status of those bytes in the draft's approvals file (line shown, never written) | the bytes, hashed now |
  | HOST READERS | the kit's `bmpack validate` (the host's own admission) of the draft's **enabled** members + this mod, and without it: ACCEPTED / REFUSED, load order, each refusal marked NEW (caused by adding it) or had; host compatibility by offered services / tables | describing kit |
  Also: dependencies (each `requires_mods` entry: on / switched off / not in the draft), enabled members that require it,
  a SAME mod id warning. **The labels are not a code-safety assessment**: nothing says what a native module does.
- **Draft actions** (Test profile tab buttons **Add**, **Enable selected**, **Disable selected**, **Remove selected**; CLI
  `wb_profile.py draft FILE [--add PACKAGE] [--enable|--disable|--remove MOD_ID|PACKAGE] ... [--even-if-required]`, applied
  in the order given). Both call `wb_profile.draft_apply`, so the CLI and the GUI give the same draft.
  - Only the draft changes: never the source folder, its staging record / sidecar progress (`.wb_stage`), an approvals file
    or a prepared profile. Remove takes the package out of the draft only.
  - **Transactional**: all actions are computed in memory, then one atomic replace of the draft file; a refusal or a write
    failure leaves the draft byte for byte (no temp file left). The GUI's list changes only when an action succeeds.
  - **Disable / Remove of a mod that enabled members declare in `requires_mods`**: refused with the dependents named
    (nothing changed). Confirm (GUI Yes / CLI `--even-if-required`) to change only that mod: the dependents stay exactly as
    they are and Check refuses them until you fix it. Enable / Add report what the mod declares it needs that is missing or
    switched off; nothing is enabled or added for you.
  - **From a prepared profile** (`draft NEW.json --from-profile DIR ...`, or Load draft / profile in the GUI): the result is a
    successor draft (predecessor recorded, no profile folder); a draft file is never written inside a profile. Then Check ->
    Prepare (new profile) -> Preflight -> Dry run start again; PROFILE.json `changes` adds `switched_off` / `switched_on`.
- **How "disabled" is represented** (decided from the host code): the draft keeps the package and lists its folder in
  `disabled` (draft schema `bm-workbench-profile-draft/2`; /1 drafts are read with everything on). Prepare copies it into
  `plugins\<mod id>\` like the others and writes `state\mod-list.toml` `disabled = ["id", ...]` - the host's own switch:
  modfs (`modfs.c` list_mods) marks those ids `enabled = 0` and the host's admission (`bm_admit.c` admit_cb) skips them
  (a dependant's reason names them "switched off"). The kit's `bmpack validate` does not read mod-list.toml, so Check /
  Prepare / Preflight pass it the **enabled** folders only (mod-id order, = the host's one-root order). PROFILE.json:
  `disabled` and `enabled: false` on those members. A switched-off plugin needs no approval now and its line is **not**
  copied into the profile (switching it on is a successor that needs your approval). Preflight checks "mod list = the
  profile's"; a change of the list (e.g. on the game's MODS page) makes earlier results STALE.
- Still decided by the host's rules, unchanged: duplicate ids (refused even when one copy is off - modfs refuses a shared id
  before the switch), requires_mods order / missing / too old / cycles, clashes, the platform gate, the 256-mod cap.
- **Parity with switched-off members (v0.11, `admission_switched`)**: the kit's checker cannot mark a folder switched off, so
  with any member off the Workbench runs it twice: (1) the enabled folders = admission, order, clashes, dependencies; a
  dependency it calls `not installed` that is a switched-off member gets the host's own text (`bm_admit.c`:
  `requires_mods "<rq>": installed but switched off: mod <id> <version> (<folder>)`); (2) every folder, switched-off ones
  included, from which only the loader's own refusals are taken: the cap (`more than 256 mods: the loader ignores it` -
  modfs counts every folder) and shared ids (`is also used by`). Check, Prepare, Preflight and Preview use it. (v0.10 counted
  only enabled folders toward the cap.)

## Import a finished mod folder (v0.11)
For mods that already exist as finished folders (a data pack, or a plugin package with its built module): **Example mod
tab -> "Project" = the mod folder, "Staging folder" -> Import folder -> Validate -> Stage**; the result shows the staging
summary and a Preview of the staged package against the Test profile draft; **Add imported package to the profile draft**
then uses the normal Add action. CLI: `py -3 -B wb_stage.py SOURCE DEST --import [--check] [--draft FILE]` (`--check` = the
checks only, writes nothing; `--draft` = preview against that draft). GUI and CLI run the same `import_check` and job.
- **Never**: building, configuring or running anything from the package (scripts and executables are copied, never run, and
  listed as a note), installing into the game, creating approvals (a plugin is staged with `native_code.approved false`;
  you approve its exact bytes yourself), writing the source.
- **Refused, nothing written**: no `mod.toml` at the top, invalid TOML, an invalid mod id or no version, unreadable
  `[bmashup]` requirements, `[plugin]` with api other than 1 or a `windows` module that is not a plain file at the top
  (no `..`, separators or drive), a module that is not a PE32+ x86-64 DLL with the SDK plugin exports, host requirements
  the kit's reference host does not offer, links / junctions / other reparse points anywhere in the source (or the source
  itself), a `.wb_stage` folder in the source, more than 5000 files or 2 GB, a staging folder inside the source or the
  source inside the staging folder, every v0.2 destination rule (protected locations, markers, sealed folders), a mod id
  that another package in the staging folder already has, a folder of that id that holds a Workbench BUILD or an import from
  another source. Archives (.zip etc.): **deferred** (unpack into a new folder yourself and import that).
- **Validate -> Stage**: files are copied one by one into `<staging>\.wb_stage\work\<time>\<mod id>`, the copy's sha256 must
  equal the source's, then the kit's `bmpack validate` runs on the COPY (the host's admission of the mod alone). Only when
  everything passed, an earlier import is moved to `.wb_stage\previous\<time>\` and the copy becomes `<staging>\<mod id>`
  (one rename); a failure leaves the staged package and its record exactly as they were (the attempt folder stays for
  diagnosis). The source is hashed again before the commit (changed -> not staged).
- **Record** (`.wb_stage\packages\<mod id>.json`): `recipe "import"`, `kind imported-data | imported-plugin`, `provenance`
  (type imported, `reproducible_build: false`, source path, time, every source file's sha256 and size), `package_files`,
  validation checks, bmpack result, module sha256 / exports / imports / link time stamp, `native_code.approved false`.
- **Imported vs built**: Check, Preview and the member list show `IMPORTED as is ... not reproducible from source` /
  `(imported)`; kit recipes and New plugin projects show `BUILT by the Workbench recipe ... (reproducible)`. An import never
  replaces a built package.

## New car project -> Build -> Validate -> Stage (v0.12)
Tab **New car project**: project folder (new or empty), template (`coupe` / `wedge` = the kit's AUTHORED carimport examples),
**mod id** (namespaced, your own: `yourname.my-car`), mod display name, version, **vehicle id** (retail class + 1..8 of A-Z 0-9:
`COMPMY1`), **donor** (a retail race car of the same class), **car name** (garage, 1..21 of `A-Z a-z 0-9 space - ' . &`),
deform (`transfer` / `rigid`), paints (one `name #RRGGBB` per line, max 8; empty = the template's six) -> **Check** -> **Create car
project** -> **Use in Build / stage** -> staging folder -> **Build -> Validate -> Stage** (the result shows a Preview; **Add ...
to the profile draft** = the normal Add). The kit's own coupe example: Build / stage tab, button **carimport-coupe**. CLI:
```bash
py -3 -B wb_car.py new "%USERPROFILE%\cars\my car" --id yourname.my-car --car COMPMY1 --donor COMPCAR1 --name "My Car" [--mod-name T] [--version 1.0.0] [--template coupe|wedge] [--deform transfer|rigid] [--paint ink=#102030 ...]
py -3 -B wb_car.py check "%USERPROFILE%\cars\my car" [DEST]      # the input checks only, read only (exit 0 / 3)
py -3 -B wb_car.py donors [--class COMP]                         # the 67 donors of the kit's reference table
py -3 -B wb_stage.py "%USERPROFILE%\cars\my car" "%USERPROFILE%\cars\staged" [--draft FILE]
```
- **What is made** (one rename, complete or not at all; an existing non-empty folder is never written): `car.toml` (carimport's
  own schema: `[car]` id / donor / name / model / paint_mask / texture_name / deform / mod_id / mod_name / mod_version +
  `[[paint]]`; a comment block labels the DONOR DEPENDENCY), the template's `<model>.gltf`, `.bin`, `texture.png`,
  `paint_mask.png` (kit bytes, copied), `workbench-car.json` (declared mod id + vehicle id, template sha256, kit binding, donor
  dependency, deferred list), `README.txt`. No new importer, format or build script. Edit names, paints, donor, deform and the
  assets freely; keep `id` / `mod_id` = workbench-car.json (checked before every build; Rebind works as for plugin projects).
- **Donor dependency (not your content)**: carimport does not make a whole car. The donor in YOUR game data gives the collision
  hull, wheel / locator / crush tables, emitters, engine audio (DERIVED copies in the package) and, in the game, physics /
  handling and the garage photo. The record lists every donor file read (`pveh\<CLASS>\<car>.bgv/.hwd/.lwd`, reference sha256).
  **A built car package is LOCAL ONLY** (derived retail data): never upload or ship it.
- **Build** (recipes `car-project` / `carimport-coupe`; fixed argument lists, no free command field): the checked inputs only
  are copied into `<staging>\.wb_stage\work\<time>\src`; then `carimport.py version`, `vehtool.py version` (identities),
  `carimport.py validate car.toml --game-data <data> --json`, `carimport.py package car.toml <attempt>\out --game-data <data>
  --json`, `vehtool.py validate <package> --game-data <data>`, the kit's `bmpack validate` of the package. Commit as every
  recipe (previous package -> `.wb_stage\previous\<time>`, one rename, nothing deleted). Staged folder: the mod id (car
  project) / `carimp-coupe` (kit example, = what carimport writes).
- **Refused before anything runs (NOT STARTED, nothing written)**: links / junctions / reparse points; scripts, executables or
  build files in the project (never run); no `car.toml` / invalid TOML; a malformed glTF (not JSON, no `asset`, bad GLB
  header); a missing model / buffer / image / paint mask; a model that is not `.gltf` / `.glb`, a mask that is not PNG; any
  reference that leaves the project: car.toml `model` / `paint_mask` and glTF buffer / image `uri` with `..`, an absolute
  path, drive, UNC or URI scheme (`file:`), and in a uri a backslash, `?` / `#` or a %-escape other than `%20` (carimport decodes
  only `%20`); identity mismatches with workbench-car.json; a reserved / invalid mod id, a retail or invalid vehicle id, a donor
  that is unknown or of another class; the destination rules of v0.2. `data:` URIs are allowed (inline).
- **Refused by the kit tools' own checks (VALIDATION FAILED)**: everything carimport cannot carry (extensions such as Draco,
  skins, animations, morph targets, JPEG / non-PNG images, vertex colours, extra UV sets, unknown material classes, body extent
  > +-30 % of the donor, texture size ...), vehtool / bmpack refusals. The staged package and its record stay as they were.
- **Validation also checks**: the package = carimport's documented layout (mod.toml, carimport.json, LABELS.txt,
  SHA256SUMS.txt, `files\pveh\<CLASS>\<REST>.bgv/.hwd/.lwd`), SHA256SUMS.txt = the files, engine audio = the donor's reference
  bytes, mod.toml requirements vs the kit's reference host; kit example in reference mode: = the kit's
  `tools\carimport\tests\REGRESSION_SHA256.json` bytes.
- **Record** (`.wb_stage\packages\<folder>.json`): `kind car`, car (id, donor, class, name, paints, deform), `inputs` (sha256 of
  every input), `source_files`, `tools` (python, carimport / vehtool path, sha256, version, tool-tree digest), `build_steps`,
  `validation`, `bmpack`, `requirements` (platform `>=0.1.5`, `[bmashup.cars]` v1), `donor_dependencies`, `labels`,
  `local_only`, `deferred`, `not_verified`, kit identity, package files. Profiles take it as a data package (Preview / Add /
  Check unchanged).
- **Supported metadata**: carimport's paints (= in-file palettes of the model). **Deferred** (recorded in every record):
  interactive 3D preview (offline `carimport.py preview` by hand), own series / class prefix (carimport ids use a retail class;
  the car joins that series), registered paints, own garage photo, `[bmashup.cars]` v2 options (physics_scale, unlock, ai,
  model = donor), several cars per project.
- **Not verified**: offline construction only - no car built by the Workbench has been seen in a game (not a visual or gameplay
  acceptance); the kit's coupe bytes were raced in the content phase (gp_carimp_2 / 3), the Workbench output is byte-identical
  to them.

## New track project -> Build -> Validate -> Stage (v0.13)
Tab **New track project** (or `wb_track.py new`), then the **Build / stage** tab with the project folder - the same job as the
CLI `wb_stage.py PROJECT DEST`.
```bash
py -3 -B wb_track.py new "%USERPROFILE%\my tracks\night loop" --id yourname.night-loop --track EU_T7_V1 --name "Night Loop" --location "MY TRACKS" [--template testloop|canyon] [--mod-name T] [--version 1.0.0] [--author A]
py -3 -B wb_track.py check "%USERPROFILE%\my tracks\night loop"          (read only: exit 0 ok, 3 refused)
py -3 -B wb_stage.py "%USERPROFILE%\my tracks\night loop" "%USERPROFILE%\staging"   (Build -> Validate -> Stage + Preview)
py -3 -B wb_track.py example "%USERPROFILE%\my tracks\kit example"       (the kit's reference input; builds = REFERENCE_0_2_1 bytes)
py -3 -B wb_track.py status|rebind PROJECT
```
- **Project** = trackbuild's own inputs: `<name>.track.json` (trackbuild.track/1), the OBJ, `textures\*.png` - written by the
  KIT's generator (`tb.py gen-testloop [--variant canyon]`, the demo the kit README names) and copied unchanged - plus
  `package.toml` (the kit's `my_track_package.toml` keys; set `workbench`, folder = mod id), `workbench-track.json`
  (identity, template hashes, kit binding, donor dependency, supported / deferred lists) and README.txt. Edit the mesh in a
  3-D tool and the description by hand (kit `docs\ADVANCED.md` s3) or with the editor below; keep mod_id / track_id / set /
  folder.
- **Build** (recipe `track-project`; kit example `trackbuild-testloop`): fixed argument lists `tb.py build {src} {desc}
  {tbuild} --game-data`, `tb.py validate {tbuild}`, `tb.py package {tbuild} package.toml {out}`, then bmpack validate of the
  mod folder; in `<staging>\.wb_stage\work\<time>\src` = a copy of the CHECKED inputs only (description, OBJ, textures,
  package.toml; the `.mtl` is not read by trackbuild). Nothing in the project is run.
- **Supported (what trackbuild builds)**: geometry / materials (opaque DXT1 PNG, <= 83 rows), collision (surface word,
  collide, car_solid), routes (stations, lanes, corners), starts (6 grid slots, start line, 1..12 checkpoints), streaming
  units (4..162), visibility (pvs all / computed), LOD (identity / decimate), optional authored traffic. Track ids: retail
  regions EU / US / AS, not a retail id (checked against your game data's `Tracks`).
- **DONOR DEPENDENCY** (labelled in every record): the Gamedata header / event records, `enviro.dat` (sky, light) and the audio
  are copies of retail EU/M1_V1 from YOUR game data (hash-pinned by trackbuild). **A built package is LOCAL ONLY.**
- **Refused before any tool runs**: links / reparse points, scripts / executables / build files (.py .cmd .bat .ps1 ...),
  malformed description / package.toml, `closed: false`, missing OBJ / textures, non-OBJ mesh, non-PNG texture, references
  leaving the project (description `obj` / `texture`, package `set` / `folder`: `..`, absolute, drive, UNC, URI scheme),
  identity mismatches, reserved / retail / malformed ids. Unsupported features (alpha materials etc.): trackbuild's own refusal.
- **Record** (`.wb_stage\packages\<mod id>.json`): inputs (sha256), tool identity (tb.py + tree hash), the 17 trackbuild gates,
  layout / sums / donor-copy / build-identity checks, bmpack, requirements, set files (LABELS.json + SHA256SUMS.txt, kept in
  the attempt's `out`), donor dependency, deferred list, evidence: offline (this build) vs runtime (none - no game launched).
- **Deferred**: own region, point-to-point, special materials / props / instances, own sky / audio / event header, other donor
  hosts, more than one track per project. Off-track reset is UNTESTED by the kit; every new track needs its own in-game check.

## Track editor, first slice (v0.14) - not a complete editor
```bash
py -3 -B wb_trackedit.py "%USERPROFILE%\my tracks\night loop" [--port 0] [--no-browser]
```
Opens `http://127.0.0.1:<port>/?t=<random token>` in the default browser (Ctrl+C in the console stops it; unsaved edits are
discarded). Authority = the project's editable SOURCE (description, OBJ, textures); compiled game files are never read or
written by the editor - they come only from Build.
- **Choice (v0.14)**: a standard-library HTTP server on 127.0.0.1 + one self-contained page with raw WebGL 1 (no library, no
  CDN) in the installed browser. Tk cannot texture-map, no GL binding / numpy / PIL is installed and none was added; Edge has
  WebGL on every Windows 10 / 11; the page keeps no state that matters, so the model is testable without a browser.
- **View**: textured mesh (each material's PNG, vertex light), orbit (drag), pan (right / shift-drag), zoom (wheel), fly
  (W A S D Q E), click selection. Layers: collision (green floor, red car-solid wall, yellow not car-solid, grey none),
  streaming bounds (units), routes (centre line, lane offsets, corners), starts (grid, start line, checkpoints). PVS / LOD:
  settings shown, not drawn (computed by trackbuild at Build).
- **Inspector**: the selected object's source properties; editable or the reason it is read only. Preserved / unsupported
  data (traffic, lod, pvs, generator, unknown keys, OBJ statements trackbuild refuses) is listed and flagged, never dropped.
- **Edit**: move a grid slot / checkpoint / the start line by (dx, dy, dz) (<= 50 m per axis), Undo / Redo (Ctrl+Z / Ctrl+Y).
  **Save** splices only the edited number spans of the description (temp file + atomic replace; nothing written without a
  change; refused when the file or another project file changed on disk). Refused with the reason: stations, units, route,
  new materials, welding / topology edits / new OBJ geometry, traffic, lod, pvs, anything else (v0.15 / v0.16 add the material
  edits, v0.17 face-group translation below).
- **Validation**: Check = the v0.13 input checks; Build -> Validate -> Stage = the v0.13 job (needs a saved state); failed
  trackbuild gates are mapped to objects / layers and highlighted (e.g. V5_grid_* -> grid slots, V2_* -> collision, V5_route ->
  route); input problems -> the material / mesh.
- **Editor path (not implemented)**: (1) material edits - v0.15 did assignment + vertex colour, v0.16 the four trackbuild
  properties; still open: new materials, new textures (importing a PNG), anything trackbuild 0.2 refuses (alpha, blend,
  animation: needs trackbuild support first); (2) object placement - props / instances are refused by trackbuild 0.2.1, so they need trackbuild support
  first; (3) road / terrain tools - stations + offsets generate the road mesh, units, collision cut lines and route together:
  needs a source generator owned by the editor (gen-testloop's parameters are the start) and regeneration of the OBJ;
  (4) route editing - lanes / corners against the station offsets with the V5_route checks live; (5) dependent regeneration
  - collision, visibility (PVS) and LOD are always recomputed by trackbuild at Build (no cached copies to invalidate), so the
  editor only has to keep the source consistent and re-run Build -> Validate (v0.17 also dry-runs the kit's build_units at
  edit time for geometry moves); (6) geometry - v0.17 translates one face group, v0.18 several (isolate / keep connected,
  snapping), v0.19 refuses moves that trackbuild would clip at the unit regions, v0.20 turns / scales the selection, v0.21 inspects the boundary and welds
  open-edge vertices / chains, v0.22 duplicates face groups and bridges two selected open-edge chains with new faces; still
  open: automatic gap / hole filling, deleted / split faces (other topology edits), unit region editing. **Next smallest editor
  milestone** (after v0.22):
  new materials (a description entry + a render row from an existing project PNG) - or route editing, owner's choice.

## Material edits and read-only retail view (v0.15)
```bash
py -3 -B wb_trackedit.py "%USERPROFILE%\my tracks\night loop"
py -3 -B wb_trackedit.py --retail "<your game data>\Tracks\US\P1_V1"
py -3 -B wb_retail.py check|decode "<your game data>\Tracks\US\P1_V1"
```
**Material edits (authored projects).** Click the mesh to select a **face group** (the faces after one `usemtl` statement of
the OBJ; the inspector shows its material, faces, vertex colours and the material's properties). Scope: this group, or every
group of its material.
- **Assign**: one of the description's existing materials that has a render row (`rows`) and only supported keys. Only the
  `usemtl` name bytes change.
- **Vertex colour**: the trackbuild colour extension `v x y z r g b` (the baked light; 0..1 per channel, 0.2 = the demo's
  neutral). Vertices used only by the target faces get their colour tokens rewritten in place (same number format). Vertices
  shared with other faces are duplicated: new `v` lines after the last existing one, and the target faces point to them, so no
  other face changes colour (checked with the kit's own OBJ reader).
- Live preview (the view is drawn from the unsaved buffer), Undo / Redo across start moves and material edits, Save writes the
  OBJ and / or the description (temp file + atomic replace each), reopen is byte-identical, Build -> Validate -> Stage = the
  v0.13 job. Every other OBJ line, the description and every other project file stay byte for byte.
- Refused with the reason, nothing changed: new or unknown materials, materials without a render row or with keys trackbuild refuses, colours outside 0..1 / NaN / wrong
  shape, an unchanged colour, unknown groups / scopes, an OBJ whose target faces come before its last `v` line (duplicating
  would need renumbering).

**Read-only retail view.** `--retail FOLDER` (explicit; the authored opener refuses a retail folder and points here, and the
retail opener refuses an authored project). FOLDER = YOUR game data's `Tracks\RR\NN_VN` with static.dat, streamed.dat and
Gamedata.bgd.
- The folder is only read: sha256 + size + mtime of every file are compared before / after the decode (a change discards the
  cache); links / junctions, empty or oversized files and folders inside the Workbench state are refused before any decode.
- The decode goes to `state\retail_cache\<RR_NN_VN>-<sha12 of the three files>\` (view.json, mesh.bin, coll.bin, tex\*.png +
  a README), written to a temporary folder and renamed; a second open reuses it. `state\` is a Workbench-protected folder: it is
  never a staging destination, and nothing in it is packaged, staged or uploaded. Delete it any time; it is rebuilt.
- Decoders: only the mod kit's trackbuild 0.2.1 vendored readers, imported after their sha256 matched the kit's VENDOR.json:
  xbmesh (materials, textures DXT1 / DXT3 / DXT5, mesh blocks, PVS material map), bolib.collision (collision trees),
  ct2_gamedata / ct2_route (Gamedata, S4 AI route), ctnav_min.slots (start grid). static.dat must be version 0x27 with units.
- **Shown**: textured full-detail mesh (per retail material, PNG preview of mip 0 with its decoded alpha; v0.16
  transparency below), collision (triangles coloured by the
  retail surface word), sections = streamed units with their streaming bounds (region quad), AI route lanes (rung midpoints),
  start-grid slots (distinct positions over all events), counts and the kit readers' own checks as validation.
- **Labelled, not shown**: checkpoints / lap lines / start line (Gamedata S1: NO verified reader in the kit - the specific gap,
  not reverse-engineered here), traffic (S2 / S3), route corners (count only; fields partly decoded), LOD render mesh, PVS
  rows, props, enviro.dat (sky), audio, line records.
- No edit, undo, save or build path exists in retail mode (every one raises "READ ONLY", also over HTTP: 409), and retail data
  is never converted into an authored project. Kings of the Road (US/P1_V1): 89 sections, 168,843 render triangles, 231 / 323
  textures previewed (the ones its meshes use), 68,481 collision quads, 46 route lanes, 6 start slots; decode ~4 s.
- Display only: the vertex light is scaled to a mid grey (`lit_scale`); the view uses the game frame as stored, like the
  authored view (the kit's glTF export mirrors Z; whether the game shows the scene mirrored relative to this view is NOT checked).

## Material properties and transparency previews (v0.16)
**Material properties (authored projects).** Select a material (Materials list, or "Edit this material's properties" on a
selected face group). Exactly the four keys trackbuild 0.2 supports, nothing else:

| key | accepted values (the kit's rules) | meaning shown |
|---|---|---|
| `texture` | an EXISTING `.png` of this project (relative path, no link); opaque (trackbuild writes opaque DXT1); power of two 4..1024; name < 32 characters | the preview loads the new texture at once |
| `surface` | a 16-bit hex word `0x0000`..`0xFFFF` (written as `0xNNNN`) | documented: 0x0001 tarmac, 0x0002 concrete, 0x000F grass, 0x0018 road-facing wall, 0x1018 back face; flag 0x1000 = not solid for cars. Every other word is accepted (trackbuild does) and labelled **UNKNOWN semantics** |
| `collide` | true / false | the faces are collision (collision layer updates) |
| `car_solid` | true / false (absent = true) | a trackbuild CHECK flag: it changes no built byte by itself; it only allows a collide material a word with flag 0x1000 |

- Every edit runs the kit's own code on the edited material before it applies: `trackbuild.preflight.check_desc`,
  `trackbuild.build.texture_record` (new texture) and the build's car-solid rule (collide + car_solid + 0x1000 refused); the
  three kit modules are imported only after their sha256 matched the kit's SHA256SUMS.txt. The texture list shows every project
  PNG with the kit reader's verdict (refused ones are greyed out with the reason).
- A material used by more than one face group needs the confirmation box ("N face groups share ..."); the HTTP / model call
  is refused with NEEDS CONFIRMATION otherwise. (The demo's grass is 357 face groups.)
- Only the value's bytes change; an absent key (e.g. `car_solid`) is added as one member after the material's last one.
  Every other material and key is compared before / after (an edit touching anything else is refused as internal error).
- Undo / Redo share the stack with the other edits; Save is all-or-nothing: temp files first, then the replaces; a failed
  replace writes the already-replaced file back from its saved bytes, removes the temp files and keeps the edits unsaved
  (also refused when a project file changed on disk: never overwritten). Reopen is byte-identical.
- Refused: new materials, other keys (alpha / blend / shader / flags / animation ... are not trackbuild 0.2 features),
  materials without a render row (no OBJ face can use them, so no effect), materials that already carry a refused key, values
  that are unchanged, of the wrong type or outside the rules above.
- Build check (offline, NOT gameplay validation): a saved surface edit changes the built collision words (grass 0x000F ->
  0x0002: all its quads), collide false removes the material's quads, a texture swap changes the static.dat texture table; an
  edited-then-undone project and a car_solid-only change rebuild static.dat / streamed.dat / Gamedata.bgd byte-identical to the
  reference. Whether the game drives differently on a changed word is not tested (no game launch).

**Transparency previews (retail view, read only).** The cache keeps each texture's decoded RGBA (the PNG equals the kit's
`xbmesh.decode_dxt` output byte for byte). The render class comes from the material's `+0x24` flags as the game's state setup
(`sub_000393C0`, source-verified) reads them - never from texture names:
- bit 0x01 = **blended**: drawn after opaque and cut-out geometry, sections far to near, source alpha / one minus source alpha;
- bit 0x10 = **cut-out** (alpha test): texels with alpha < 0.5 are discarded, depth written;
- neither = **opaque** (texture alpha ignored); bit 0x400 = no depth write (the shadow decals).
- Cross-check recorded as a validation entry: the blend bit agrees with the game's own pass split (mesh-block PVS rows: first =
  opaque pass, rest = translucent pass) for every drawn material (Kings of the Road: 239 materials, 0 problems; 175 opaque,
  45 cut-out, 18 blended, 1 blended + alpha test).
- Representatives verified (test_trackedit_v16 t01 / t03): Tree_shadow1 (DXT5, +0x24 0x40F, blended, no depth write),
  GL_bridgeshadow (DXT5, 0x40B, blended, no depth write), GL_treeflat (DXT1, 0x32, cut-out): the real shader rendering each
  texture 1:1 matches the decoded RGBA in every pixel.
- Retail materials are inspection only: the Materials list shows each non-opaque material's class, flags and pass; the inspector
  adds the texture's alpha statistics. No edit path.
- **Differences from the game's renderer** (also listed in the page under "preview vs the game renderer"): blend factor names
  are a hypothesis (the game's state indices are known, their D3D names are not decoded; no B3 material is additive); the
  alpha-test reference value is not decoded (0.5 used; DXT1 cut-outs are 0 / 255 so it only matters for DXT3 / DXT5 cut-outs);
  vertex alpha is not applied (the combiner setup is not decoded and many tree-card vertices carry alpha 0); blended surfaces
  get a small depth offset in the preview (the game's depth bias is not decoded); sorting is per section centre, not the
  game's PVS row order; not reproduced: fog, sky, reflections (type 8 / 9 second pass), UV scroll (0x200), lighting beyond the
  baked vertex colour, mip / LOD bias, anisotropy, the host renderer's settings.

## Moving a face group (v0.17)
Select a face group (click the mesh), enter the offset in metres in "move this face group by" and press **Move group**.

- **What moves**: exactly the selected face group = the `f` lines after its one `usemtl` statement, up to the next `usemtl`.
  Never the other groups of the same material, never neighbouring faces. (The demo's groups are 1 - 2 faces each; there is
  no multi-group selection yet.)
- **Exact offset**: each moved corner's x / y / z token is rewritten as an exact decimal sum at the token's own precision
  (demo: 4 decimals = 0.1 mm). An offset finer than that is refused (never rounded). At most 50 m per axis per edit (a
  typo guard), never zero. An independent re-read checks that the group's corners moved by exactly the offset and every
  other face corner, uv / normal reference and colour is unchanged before the edit applies.
- **Shared corners**: a corner used by the group and by any other face is duplicated (a new `v` line after the last one, with
  the same colour tokens; the group's faces re-pointed), so no other face moves. The group therefore detaches from its
  neighbours: moving it opens a seam / step at its edges (no welding or stitching). Corners used only by the group are
  rewritten in place. uv (`vt`), normals (`vn`), comments, `g` / `s` / `o` lines and every other line stay byte for byte; the
  description is not touched.
- **Dependent data**: before the edit applies, the kit's own trackbuild `build_units` (sha-checked kit module) runs on the
  edited OBJ + the current description in a temporary folder under Workbench state: render clipping into units (streaming),
  collision copies per unit, unit culling prism (bounds), PVS (mode all / computed incl. its ring check) and LOD (identity /
  decimate). If trackbuild refuses (e.g. faces outside every unit region, a mesh / LOD block over its slot, sliver loss, a
  computed PVS beyond the +-8 ring) the edit is **refused with trackbuild's reason** and nothing changes. The result lists
  each unit whose blocks change (bounds y, render / collision polygon counts). The Build regenerates exactly the same data
  from the saved source: test g05 shows the built `streamed.dat` equals the edit's dry run byte for byte. Nothing derived is
  cached in the source, so nothing can go stale.
- **Not moved (separate adjustment)**: routes / stations, grid slots, the start line, checkpoints, traffic lanes and unit
  regions are authored source data and never move with geometry. The edit reports every grid slot, start line, checkpoint
  and route station (centre + lane offset samples) standing on the group's old or new footprint (xz) as **NEEDS SEPARATE
  ADJUSTMENT**. Grid / start / checkpoints can be moved with the start-object edit; the route cannot be edited yet. The
  Build's own gates then decide: e.g. raising a road group under the route 0.5 m is accepted as an edit (trackbuild can
  regenerate it) but the Build stops at `V2_drivable_coverage` (floor no longer at the route height) - nothing is staged and
  the previous staged package stays.
- Undo / Redo / Save / reopen as for every edit (shared stack, all-or-nothing save). Undoing and saving rebuilds the
  reference bytes. Retail mode refuses the move like every write (READ ONLY).
- **Deferred**: rotation, scaling, several groups at once, welding / closing seams, adding / deleting faces, terrain / road
  generation, any new renderer effect.
- Verified (offline, `tests\test_trackedit_v17.py`; NOT gameplay validation): exact move and untouched neighbours (kit
  `read_obj` re-read), preview follows, undo / redo / save / reopen exact, refusals leave the buffers and stacks unchanged
  (incl. a trackbuild "outside every unit region" refusal), the adjustment report (grid slot 0 + route stations over a moved
  road group), and built data: moved render corners exact in float32, collision quads at the new position within the
  1000 / 65536 m quantisation and gone from the old one, units the dry run did not change keep their vertices, collision and
  bounds, every unit prism = its built vertex
  y range; a failed save (read-only OBJ) and a failed Build leave the source and the prior staged package unchanged.

## Multi-group selection, snapping and boundary modes (v0.18)
- **Selection**: click a face group to select it alone; **Ctrl-click** adds or removes a group; **Clear selection** empties it.
  The group box shows the count ("selection: N face group(s), F face(s) - groups ..."); every selected group is outlined in
  yellow. The selection is exactly the union of the selected groups' faces (each = the `f` lines after one `usemtl`).
- **Offset**: X / Y / Z in metres (at most 50 m per axis, exact decimal at the source precision, as in v0.17). **Snap** (optional,
  0.1 / 0.25 / 0.5 / 1 / 2 / 5 m): each axis of the offset is rounded to the nearest multiple of the step (halves away from zero),
  e.g. 0.37 / -0.38 / 0.12 with 0.25 -> 0.25 / -0.5 / 0. Snapping applies to the offset, not to absolute positions (the
  selection keeps its shape and its position relative to the grid it was built on). An offset that snaps to zero or beyond
  50 m is refused.
- Corners shared **inside** the selection always stay shared (moved once), so the selection moves as one piece.
- **Isolate** (default): corners shared with unselected faces are duplicated (v0.17 behaviour) - nothing else moves; gaps /
  steps open along the boundary and the result warns with the boundary-corner and neighbour counts.
- **Keep connected**: those boundary corners move with the selection, so the neighbour faces using them stretch (no new vertex
  lines; continuity kept). **Preview affected neighbours** first: the neighbour faces' groups are outlined in orange with the
  counts; the move is refused (NEEDS PREVIEW) unless it carries the key of a preview of exactly this selection, mode and
  current source (any edit in between makes the key stale). Pressing Move without a preview runs the preview and asks again.
  Each stretched face is checked before the edit applies and the edit is refused with the face's line when it would collapse
  (area <= 1e-4 m2, trackbuild's degenerate rule), fold over (a triangle flips) or turn against a stored normal it agreed with
  (trackbuild's V3_winding rule). Stretched faces keep their uv and normal references (the texture stretches; lighting normals
  are not recomputed); the result reports the maximum quad non-planarity.
- Unchanged from v0.17: uv / normal / colour references and every other line byte for byte; the kit's trackbuild build_units
  dry run regenerates collision / bounds / streaming / PVS / LOD before the edit applies (refusals with trackbuild's reason);
  start / route points on the old or new footprint (selected faces + stretched neighbours) reported as NEEDS SEPARATE
  ADJUSTMENT, never moved; undo / redo / all-or-nothing save; retail READ ONLY (preview refused too).
- **Deferred**: welding, gap filling, rotation, scaling, snapping absolute positions, partial-group (single face) selection.
- Verified (offline, `tests\test_trackedit_v18.py`; NOT gameplay validation): selection refusals and preview counts against an
  independent count; snapping cases exact; isolate keeps inside-shared corners shared and duplicates exactly the boundary
  corners (neighbours unchanged); keep connected keeps every boundary corner shared, moves exactly the neighbours' boundary
  corners and nothing else, refuses without / with a wrong or stale preview key and refuses a fold-over; both modes built:
  `streamed.dat` = the dry run, moved and stretched render corners exact, collision at the new positions and gone from the
  old ones, unchanged units identical, undo + save = reference bytes, a failed save keeps the project and the edit; GUI:
  Ctrl-click add / remove, count, outline, snapped isolate move, connected refused until previewed (orange neighbours) then
  applied, undo, clear (headless Edge).

## Clipping at the unit regions (v0.19)
- **Why**: trackbuild cuts every render face to the unit regions (the streamed sections; Sutherland-Hodgman, `units.clip`)
  and silently drops whatever lies outside all of them; only a face wholly outside fails the build. Before v0.19 a move that
  pushed faces partly past a region edge was accepted and the built track lost that geometry (the old v0.17 / v0.18 test moves
  `[0.25, 3, -1.5]`, `[0.5, 1.25, -0.75]`, `[0.5, 1, -0.5]` and the snapped `[1, 3, -3]` did exactly that: 0.5 - 5.5 m2 at unit 0's lateral edge).
- **Check** (every move, both boundary modes, before anything applies): every face of the edited OBJ goes through the kit's own
  `make_units` / `clip` (the functions `build_units` uses; `trackbuild/units.py` is hash-verified with the other kit modules)
  and is compared with the same clip of the unedited OBJ. Per face: its area inside the **union** of the unit regions
  (overlapping regions counted once - 201 demo faces lie in two regions). A selected or stretched face that would keep less
  area than before (tolerance 1e-6 m2 + 1e-9 x area), or a moved collision face no unit would hold (more than the kit's 6 m
  collision margin outside every region), refuses the edit: "refused: trackbuild would clip N face(s) ... face line L (group G,
  selected / neighbour, material) loses A of B m2 at unit U lateral edge -32.85 m ... Unit regions are authored source data and
  are never expanded automatically ... Nothing changed".
- **Viewer**: the refused faces are drawn in red at their intended position and the unit region edges they cross in magenta;
  the report lists each face, its lost area and the edges. A new selection clears the highlight.
- **Same as the build**: the dry-run regeneration compares the check's per-unit pieces with `build_units`' own unit polygons,
  exactly; any difference refuses the edit (internal error), so the check can never drift from what Build produces.
- Faces split across units by a move are fine (pieces in several units, nothing lost). A face that was **already** partly
  outside before the edit (demo: one 35.8 m2 grass face, 0.00002 m2) is accepted when it loses no more, and reported as a
  warning + highlight, never silently.
- Unchanged: the kit's rules (a face wholly outside still fails `build_units` itself), unit regions / route / starts never
  moved or expanded, undo / redo / all-or-nothing save, retail READ ONLY. Other trackbuild refusals still apply (e.g. LOD
  decimation error above `e_max`).
- Verified (offline, `tests\test_trackedit_v19.py`; NOT gameplay validation): isolate and connected out-of-region moves refused
  with source / description / buffers / undo stacks unchanged, the refused faces = an independent corner-outside-every-region
  count, boundary segments on unit region corners, a wholly-outside face (+ its collision) named; valid moves across unit cuts
  and at a lateral edge (both modes) accepted with nothing lost, built `streamed.dat` = the dry run and every intended corner in
  the built mesh; the pre-existing clipped face warned; undo + save = opened bytes, Build = the reference package, a refused move
  leaves the staged package; check pieces = `build_units` pieces, a tampered check refused; GUI: clip check reported, an
  out-of-region move refused + highlighted + listed, highlight cleared (headless Edge).

## Selection transforms: turn and scale (v0.20)
- **What**: the selected face groups (Ctrl-click; same selection, boundary modes and neighbour preview as moves) are turned
  about the vertical axis by an angle in degrees (positive = counter-clockwise seen from above: +x turns towards -z; optional
  snapping to 1 / 5 / 15 / 45 / 90 degrees, half away from zero) and / or scaled uniformly by a factor (0.1 .. 10; only
  positive uniform scaling: mirroring, flattening and per-axis scaling are refused), about a **pivot**: the selection's
  bounding-box centre (exact decimal centre of its corners) or an entered XYZ (m) ("Use bbox centre" fills it in). One undo
  entry per applied transform.
- **Live preview**: while the angle / scale / pivot are edited the viewer draws the transformed selection in cyan and the pivot
  as a white cross (client-side; nothing changes until "Transform selection"). The server reports the pivot it used.
- **Precision**: p' = pivot + scale * Ry(angle) (p - pivot), computed in decimal and rounded to each coordinate's own source
  precision: every corner lies within half a unit of its last decimal of the exact result (0.00005 m for the demo's 4
  decimals); multiples of 90 degrees use exact cos / sin. Corners shared inside the selection stay shared; a corner may move at
  most 50 m per axis per edit (a typo guard: use a pivot near the selection).
- **Normals**: the selected faces' stored normals turn with the yaw (a positive uniform scale keeps their direction); in keep
  connected mode every stretched neighbour face's stored normals are **recomputed**: turned by the rotation that takes the
  face's old plane to its new one (so smooth shading is kept and the winding stays with the normal). A changed normal points to
  an existing identical `vn` line or a new one after the last `vn` line (5 decimals, as the source). Refused with the reason:
  an OBJ where faces come before the last `vn` line (new normals would need renumbering; a scale that needs no new normal still
  works there), a zero-area neighbour face, a neighbour whose plane would turn by 90 degrees or more, and any transform after
  which trackbuild would silently **drop a triangle** (its blocks rule: a fan triangle under 0.005 m2 or winding against the
  first corner's normal) - e.g. a keep-connected 0.3 shrink of a pad turns a neighbour triangle into a sliver.
- **Reused unchanged**: isolate (boundary corners duplicated: gaps / steps) and keep connected (preview first; collapse /
  fold-over refused), the v0.19 clip check (a transform that trackbuild would clip at the unit regions is refused and
  highlighted; regions never expanded), the kit's build_units dry run before the edit applies, NEEDS SEPARATE ADJUSTMENT for
  grid slots / start line / checkpoints / route stations on the old or new footprint (never moved), all-or-nothing save,
  retail READ ONLY. Texture coordinates (vt refs), vertex colours and every other line stay byte for byte (a scaled face shows
  its texture scaled with it: reported).
- **Fact (kit validation)**: the edit-time dry run is trackbuild's build_units, not its validation gates. A road-facing wall
  turned 20 degrees builds but fails the kit's `V2_walls_hold` at Build -> Validate -> Stage, which refuses it (the staged
  package stays unchanged); undo and stage again.
- **Deferred**: welding / gap filling, topology edits (new / deleted / split faces), per-axis or negative scaling, rotation about
  other axes, unit region editing.
- Verified (offline, `tests\test_trackedit_v20.py`; NOT gameplay validation): turns (20, 90, snapped 22 -> 15 degrees), scale
  0.5 about an entered pivot, turn -30 + scale 1.2 of two groups: every corner within the bound of an independent float
  recomputation, bbox pivot = the independent decimal centre, selected normals = old normals turned (within 0.00001), uv refs /
  colours / vt / usemtl / comment lines / existing vn lines / unselected faces unchanged, one undo entry, undo exact; 17 invalid
  inputs refused with nothing changed; isolate duplicates exactly the boundary corners (neighbours unchanged); keep connected
  refused until previewed, stretched neighbours' moved corners transformed and their normals = an independent plane-to-plane
  rotation; clipping (both modes), fold-over, a dropped triangle and the unsupported layout refused unchanged; Build: streamed.dat
  = the dry run, every transformed / stretched corner in the built mesh with its turned normal (trackbuild's packed normal),
  collision at the new positions (surface kept, within the collision quantum) and gone from the old, undo + save = the reference
  package; undo / redo / save / reopen exact, a refused transform on a dirty buffer and a failed save keep everything; GUI: live
  preview + pivot marker, snapped turn, server pivot = previewed bbox centre, entered pivot + scale, negative scale refused,
  connected transform previewed first, undo (headless Edge).

## Boundary inspection and welding (v0.21)
- **Show open edges + gaps** (Boundary / weld box, authored projects): open edges = edges used by ONE face, by POSITION (all v
  lines with the same decimal coordinates are one corner, so uv / colour seams - 2142 in the demo - are not open). Orange
  lines; the report also counts non-manifold (more than two faces) and misoriented edges. With the tolerance (metres,
  explicit, 0 < t <= 1) it lists **gap candidates**: chains of open-edge corners whose every corner has exactly one other
  open-edge corner within the tolerance (mutual, not a corner of the same face), joined along open edges on both sides; green
  lines = gap distances; corners with several partners are listed as ambiguous. Inspection changes nothing; candidates are
  suggestions only.
- **Choose what to weld**: click a candidate (two matching chains, or vertex pairs when the chain branches), or **Pick 2
  boundary vertices** and click them in the view (nearest open-edge corner within 14 px; pink). **keep**: side A stays (B moves
  onto it), side B stays, or both move to the midpoint (rounded HALF_EVEN at the finer source precision).
- **Preview weld** shows the matched pairs with their gap distances and targets, the faces that stretch (blue) and the open-edge
  count before / after; **Weld** applies only with the key of that preview (otherwise NEEDS PREVIEW, and the preview is shown).
  Refused with the reason, nothing changed: a corner not on an open edge (interior: unsupported topology), chains that do not
  follow open edges / have different lengths / do not run together, a gap wider than the tolerance (NO MATCH / GAP TOO WIDE),
  another open-edge corner within the tolerance of either end (AMBIGUOUS), two corners of one face (would collapse), a corner in
  two pairs, and a result with a collapsed face, a new non-manifold or misoriented (flipped) edge, a folded or sliver triangle
  or one turning against its stored normal; then the v0.19 clip check and the kit trackbuild regeneration (refusals as for
  moves).
- **What changes**: only the x y z tokens of the moving corners' v lines (their colour tokens kept); every face keeps its own
  v / vt / vn references, so uv, normal and colour seams are preserved and no line is added, removed or renumbered. Stretched
  faces keep their normals (not recomputed; the move is at most the tolerance). One undo entry; save / reopen as before.
  Routes, starts, checkpoints and unit regions are never moved (adjustment report as for moves).
- **Deferred**: automatic gap filling (new faces), merging v lines (index welding), other topology edits, unit region editing.
- Verified (offline, `tests\test_trackedit_v21.py`; NOT gameplay validation): open edges / seams / non-manifold = an independent
  count (demo: 714 / 2142 / 0); a +0.03 m isolate move gives one closed 4-pair candidate; the chain weld puts every face corner
  back at its opened decimal position and rewrites only 4 v lines' coordinates (colours, face references and every other line
  byte for byte); the regenerated data = the opened source's and the Stage package = the reference build byte for byte; a
  midpoint weld (error <= 0.00005 m) builds with the corners in the mesh and the collision at the welded positions; refusals
  (argument errors, interior / missing corners, gap too wide, chain mismatches, no / stale preview, retail; synthetic OBJs:
  ambiguous, collapse, fold-over, non-manifold, misoriented) change nothing; undo / redo / save / reopen exact; a failed save
  keeps everything; GUI: open edges, candidate, click-picked pair, forced preview, pair weld + undo, tolerance refusal, chain
  weld back to the data before the gap.

## Layout construction: duplicate and bridge (v0.22)
- **Duplicate selection** (group box; the Ctrl-click selection of face groups): one undo step. **Where the copies go**: each
  selected group becomes a new face group APPENDED AT THE END of the OBJ, in the selection's group order: the source group's
  `usemtl` line byte for byte + its `f` lines with only the vertex index of each corner changed. New `v` lines (one per original
  v line the selection uses) go right after the last existing `v` line; nothing else moves, so every existing line, group index
  and face line number stays. **Exact attributes**: the copies keep every corner's own `vt` / `vn` reference (the same uv and
  normal lines: exact), each new v line carries the original's colour tokens, and corners shared inside the selection stay
  shared in the copy; the copy shares no corner with any other face (so moving it never stretches anything).
- **Placement**: the copy is placed at the "move the selection by" offset (X / Y / Z m, exact decimal at each coordinate's own
  precision, at most 50 m per axis; finer than the source precision is refused); `0 0 0` = in place (the v lines are byte
  copies). **Selected afterwards**: the copies become the selection (yellow) and the result names their group indices, so Move /
  Transform (turn, scale) apply to the copy next - each its own undo step.
- **Fact (kit trackbuild)**: a copy lying exactly on, or stacked above, its original can be refused by trackbuild's own LOD
  decimation (demo, lod decimate e_max 0.3 m): an in-place copy of two road quads -> "LOD decimation error 1.644 m above the
  bound"; a copy of one big grass face 0.5 m above it -> error 0.5 m; the same copy 0.05 m above is accepted. The refusal names
  the cause; give an offset (or a different one). Copies 3 m above road quads and 1 m above grass build and stage.
- **Checks** (every duplication, before it applies): an independent re-read (original lines byte for byte, new v lines only after
  the last v line, the copies only at the end, per corner position + offset exact, same colour / vt / vn, fresh v lines with the
  source's sharing pattern), the v0.19 clip rule for the copies (a copy may lose no more area outside the unit regions than its
  original; a moved collision copy must stay within the 6 m collision margin: e.g. the pre-clipped grass face copied 0.5 m
  sideways is refused, highlighted red), the kit's build_units dry run, NEEDS SEPARATE ADJUSTMENT for grid / start / checkpoints /
  route stations on the copy's footprint. Refused with nothing changed: empty / invalid selection, a bad offset, an OBJ whose
  faces come before the last v line or without a final line end (layout guard), retail (READ ONLY).
- **Bridge two open-edge chains** (Boundary / weld box, "Bridge" part): chain A and chain B are explicit lists of OBJ vertex
  indices along open edges (by position, as v0.21): **Pick A** / **Pick B** then click open-edge vertices in order, or **Use the
  chosen gap's chains** (a v0.21 gap candidate), or type them; **closed loops** when both chains close back to their first
  vertex. Compatible = the same number of vertices, disjoint, each step an open edge; one quad per chain edge. Nothing is
  chosen or filled automatically.
- **Correspondence and winding**: the existing face on each chain edge fixes the direction its boundary runs; every new face
  runs its chain-A edge and its chain-B edge OPPOSITE to those faces (consistent winding with both neighbours: no misoriented
  edge), which pairs chain A with chain B in opposite boundary directions (open chains end to end). Closed loops also need the
  starting pair: the shift with the smallest total pair distance; refused (AMBIGUOUS) when another shift is within 10 %.
  Refused when a chain's faces wind inconsistently along it, or when the winding-consistent pairing is crossed while the other
  is nearer ("the chains face the same way").
- **New faces**: a new face group (`usemtl MATERIAL` + the quads) appended at the end of the OBJ. MATERIAL = an EXISTING
  assignable material (a description entry with a render row; never created here). Corners = the existing v lines that the
  neighbour face on that chain edge uses (its position and colour; no v line added or moved). **Normals**: one new normal per
  new face = its Newell normal (5 decimals; flat shading; agrees with the winding). **UV mapping** (documented, `BRIDGE_UV_M` =
  4 m): u = distance along chain A from its first bridged vertex / 4 m (a chain-B corner takes its partner's u, so the texture is
  not sheared along the chain), v = 0 on chain A and the pair distance / 4 m on chain B; 5 decimals. New `vt` / `vn` lines go
  right after the last existing ones (an identical existing line is reused); faces before those lines -> refused (layout guard).
- **Preview first**: **Preview bridge** shows the pairs (green), the new faces (purple), the correspondence, winding, uv
  mapping, open edges before / after and the lines added; **Bridge** applies only with that preview's key (otherwise NEEDS
  PREVIEW and the preview is shown). After a bridge the new group is selected.
- **Refused with the reason, nothing changed**: a vertex not on an open edge, chains not along open edges / sharing a location /
  of unequal length (no automatic triangulation) / a closed flag on an open chain, inconsistent winding, crossed or ambiguous
  correspondence, a pair farther than 50 m or two corners of one face, and new faces that are degenerate (area <= 1e-4 m2),
  slivers trackbuild would drop (its fan-triangle rule), twisted (the two triangles fold against each other), fold back over a
  neighbour face or the previous new face (more than 120 degrees: e.g. raising a demo grass strip beside a wall would put the
  bridge face back to back on the wall), or a result with a new non-manifold / misoriented edge; then the clip rule for the new
  faces (any area outside the unit regions, or a collision face outside the margin) and the kit's build_units dry run. Pairs at
  one location cannot occur (a location is one position); a rung on an existing edge implies two corners of one face (refused),
  so the non-manifold / misoriented result checks are a second line of defence.
- **Open chains** leave their two end rungs as new open edges (reported); closed loops close every chain edge.
- **Routes / starts / checkpoints / unit regions** are never moved or expanded; points on the new faces' footprint are reported
  as NEEDS SEPARATE ADJUSTMENT. The kit's validation still decides at Stage: e.g. a road quad sunk 0.25 m and bridged builds,
  but Build -> Validate stops at `V2_drivable_coverage` (floor no longer at the route height) - as for v0.17 moves.
- **Deferred**: automatic gap / hole filling, triangulating unequal chains, deleting / splitting faces, unit region editing.
- Verified (offline, `tests\test_trackedit_v22.py` 19/19; NOT gameplay validation): b01 two adjacent road quads copied at
  [0, 3, 0]: original lines byte for byte, per corner position + offset exact with the same colour / vt / vn, shared corner kept
  shared, kit read equal; the in-place copy refused (LOD) with nothing changed; the copy then moved and turned 10 deg + scaled
  0.9 with the originals unchanged; b02 argument / offset / layout / retail refusals, clip refusal of a sideways copy, a
  pre-clipped copy accepted with a warning; b03 a closed gap (road quad sunk 0.25 m) bridged by 4 quads: open edges back to 714,
  0 non-manifold / misoriented (independent count), corners on existing neighbour v lines, uv = the mapping, normals = Newell;
  an open notch bridged (the 2 end rungs open); b04 every refusal unchanged incl. narrowed unit regions (clip), the wall
  fold-back and 7 synthetic cases + 2 accepted controls; b05 Stage: copy and bridge corners / packed normals / uv in the built
  mesh, collision at copy + original and for the bridge faces, streamed.dat = the dry run, undo + save = the reference package;
  b06 four-step undo / redo / failed save / reopen exact; b07 GUI (headless Edge section construct).

## Unit regions: edit, add, merge, move cuts (v0.23)
Construct box -> **Unit regions** (authored projects; retail READ ONLY). A unit = the streamed section between two cut stations
(`cut_from` / `cut_to`) and two lateral lines along its chord normal (`lateral` [lo, hi] m); the kit's trackbuild needs the
units to tile the loop in order (each end cut = the next unit's start cut), convex regions, 4..17 units with pvs `all`
(4..162 with `computed`), and every unit's mesh / LOD block within its slot (0x28000 / 0x18000 bytes; RTA5 capacity auto: up to
the host ceilings 0x200000, declared in mod.toml - wb_capacity / kit trackbuild.capacity), <= 65,536 vertices and
<= 127 records.
- **Operations** (unit number + one of): **fit lateral bounds** (refit to the route corridor - station offsets[0] / [-1] - and
  the geometry the unit holds, + 0.25 m: the kit generator's rule), **set lateral bounds** (explicit [lo, hi]), **split at
  station** (adds a region: two units with recomputed chord normals and fitted bounds), **merge with the next unit**, **move its
  end cut to station** (both neighbours refitted). The last unit cannot be merged / have its end cut moved (the list starts at
  unit 0, the start cut stays); merge / move the cut from its predecessor.
- **Preview** (nothing changes): the candidate regions (cyan; bright = changed), coverage (every face's area inside the union
  of the regions before / after - the kit's own make_units / clip; the kit validator's drivable samples and the grid slots each
  in exactly one unit) and capacity (per unit: vertices, records, mesh / LOD bytes as % of their slots, from the kit's
  build_units dry run on the candidate description). **Apply** needs the preview's key.
- **Refused, nothing changed**: a unit count outside the kit's range (the demo has 17 = the maximum with pvs all: split refused
  until two units are merged), a region the kit cannot build (not convex / cuts not shared), **any face keeping less area**
  (unintended geometry loss: Build would drop it silently; such faces are drawn red), a drivable sample not in exactly one unit
  (V2_drivable_coverage), a grid slot not in exactly one unit (its start unit), anything build_units refuses (slots, LOD, PVS).
- **What changes**: only the description's `units` value (spliced: every other byte, unknown keys and number spellings kept;
  demo: a lateral edit changes 2 lines). One undo entry; transactional save. Geometry, route, starts and checkpoints are not
  changed; trackbuild recomputes the dependent data (streaming sections, collision copies, bounds, PVS, LOD, grid start units)
  at Build. Units after a split / merge are renumbered.
- Verified (offline, `tests\test_trackedit_v23.py` 18/18; NOT runtime validation - streaming in the game is unproven for
  edited regions): preview read only, regions = kit make_units, coverage = an independent sampling, capacity = build_units;
  widen applied as a 2-line splice; narrowing refused with exactly the faces an independent sampling finds; merge / split /
  cut / fit with the generator's chord normals and the corridor inside; refusals; merge 7 + split built: Stage STAGED (kit
  validation), built unit table = the capacity preview, streamed.dat = the dry run; undo / redo / save / reopen; GUI (section
  units).

## Road strips from editable control points (v0.24)
Construct box -> **Road strip** (authored projects; retail READ ONLY).
- **Input**: control points (one `x y z` per line; y = the elevation; **Click points** appends the clicked mesh point + a lift,
  0.05 m by default), open or **closed loop**, width (2..60 m), an EXISTING material (with a render row), step between
  cross-sections (0.5..20 m, default 4) and uv length per texture repeat (default 14 m, as the demo road). The curve is a
  centripetal Catmull-Rom spline through every control point, resampled evenly by arc length (simple curves; no banking - the
  road is level across, deferred).
- **Generated**: one quad per step from -width/2 to +width/2 across the curve's n+ axis (trackbuild's lateral convention),
  faces up; uv u 0 (n- edge) .. 1 (n+ edge), v = distance along / uv length; normal = each quad's own plane (Newell, 5 decimals);
  vertex colour 0.2 (the demo's neutral); collision = the material's (`collide` / surface word), built by trackbuild.
- **Editable**: the road is a tagged construction block: its face group carries `# wb-construct {"kind": "road", "id": ...,
  "points": ..., ...}` right after its `usemtl` line (ASCII JSON comment; trackbuild ignores comments). Choose the road in the
  list, change points / width / material, Preview + Apply: its old usemtl / tag / f lines are removed (its old v / vt / vn lines
  stay, unused) and the new block is appended. New v / vt / vn lines go after the last existing ones (identical vt / vn reused).
- **Refused, nothing changed**: invalid / too close (< 1 m) points, a curve tighter than 1.25 x half the width (the inner
  edge would fold), a self-crossing road (no junctions / bridges), widths / steps / uv lengths out of range, unknown materials or
  road ids, faces degenerate or dropped by trackbuild as WRITTEN, faces outside the unit regions (v0.19 clip rule; regions are
  never expanded - edit them first, v0.23), no / stale preview key; then the kit's build_units dry run as for every edit.
- **Route floor (kit fact)**: the validator's V2_drivable_coverage needs the HIGHEST floor at every route sample (wall to wall)
  within 0.05 m of station 0's height, so a drivable route must stay at one height. A road over the route at another height is
  accepted with a warning naming the gate; Build -> Validate then refuses it (test r05: warned, Stage refused exactly
  V2_drivable_coverage). Roads off the route may have elevation (the ramp 20.05 -> 21.5 m builds and stages).
- Verified (offline, `tests\test_trackedit_v24.py` 19/19; NOT gameplay validation): exact geometry / uv / normals / colours /
  shared edges / centre line through the points, original lines kept, tag parameters; ramp + re-generation; 15 refusals; Stage
  STAGED with every road corner + packed normal in the built mesh and collision quads with the material surface; the route-floor
  rule matches the kit; undo / redo / save / reopen (blocks read back from their tags); GUI (section road).

## Race layout: route, starts, checkpoints, structural validation (v0.25)
Construct box -> **Race layout** (authored projects; retail READ ONLY).
- **Check race layout** (read only): STRUCTURAL checks of the current source - connectivity (closed route, even station spacing,
  no self-crossing, tangents turning < 30 degrees per station), direction (stations, grid slots, start line and checkpoints
  facing along the route), drivable coverage (the kit validator's V2 sampling: every sample wall to wall in exactly one unit,
  with a collide floor whose highest face is within 0.05 m of station 0), walls hold (the kit's V2 wall probes against car-solid
  wall words), lap order (start line, then checkpoints in increasing route order, >= 10 stations apart, 1..12) and grid (6 slots
  between the main-lane edges, each in one unit). Each check is provoked in tests\test_trackedit_v25.py x01. The report always
  states the **runtime** part as unproven: AI drivers following the route, lap / checkpoint counting, respawn, streaming and
  collision in the game need an in-game run (see "Runtime acceptance plan"). The kit gates at Build -> Validate stay the
  authority.
- **Layout from closed control points** (one height: the kit's V2 floor rule): road (width, existing floor material) + walls on
  both sides (wall / wallback, height) + verges (outer / inner widths, grass) as tagged blocks, and the description's route
  values: stations every ~1.9-2 m (count = 17 units x a multiple of stations_per_slice 3), the demo's 6 lane-boundary offsets,
  5 lanes, corner records from the curvature (turn sign + degrees, first 2 slices early as the demo), **17 units** fitted to the
  corridor + geometry, 6 grid slots behind the start line at station 0 (the demo's runtime-validated pattern), 1..12 checkpoints
  evenly in lap order, authored traffic in the demo's shape (or donor). **replace "all"** replaces every face group (explicit:
  confirmation box); **replace "route"** re-generates only the earlier layout's blocks and keeps other geometry (refused when
  kept faces would leave the new unit regions). One undo entry for description + OBJ; every other description byte kept; the
  demo's `generator` block is preserved (trackbuild does not read it; reported).
- **Checkpoints at stations**: a list of station indices (lap order checked; refused otherwise); the start line stays at the
  route origin (station 0); single grid slots / start line / checkpoints still move with the v0.14 start edit (then Check).
- **Kit facts found here**: (1) with pvs "all" the kit's validator accepts exactly **17 units** (trackbuild.blocks.pvs_chunks
  lists 17 relative units per unit; fewer repeat a target and V3_pvs_walk fails, although build_units accepts 4..17) - race
  layouts use 17 and unit edits warn below 17; (2) faces that end exactly on a unit cut lose hair-thin slivers (< 0.00005 m x
  the face perimeter) to 4-decimal coordinates in the kit's own clipper - accepted for race layouts and reported
  (cut_rounding_slivers_m2), refused everywhere else as before; (3) the layout's units hug the corridor, so geometry in the
  infield needs wider units first (v0.26 unit op "include").
- Refused, nothing changed: control points at different heights, unit counts other than 17, a strip edge that folds (curve
  tighter than an offset) or crosses itself, road material not a floor word / wall material not a car-solid wall word, unknown
  materials, replace "route" without an earlier layout, a structural check failing on the generated layout, no / stale key.
- Verified (offline, `tests\test_trackedit_v25.py` 18/18; NOT gameplay validation): structural checks each provoked; checkpoint
  splice + 7 refusals; a new original 771 m layout exact (spacing 1.890 m, 17 units tiling, corner signs, grid, tags, other
  description bytes); **the editor-built layout STAGED with every kit gate passed (17 / 17)**, streamed.dat = the dry run; a
  route re-generation keeps a verge road and stages again; undo / redo / save / reopen; GUI (section race).

## Terrain, barriers, prefabs (v0.26)
Construct box -> **Terrain / scenery** and Unit regions -> **include** (authored projects; retail READ ONLY). Each is preview ->
apply with the preview key, a tagged construction block appended to the OBJ, the exact re-read, the v0.19 clip rule, the kit's
build_units dry run and one undo entry; giving an existing `id` re-generates that block.
- **Unit op "include"** (rect x0, z0, x1, z1): grows exactly the units whose cut lines span part of the rectangle, so geometry
  in the infield is inside a unit region (race layouts' units hug the corridor). Cuts and chord normals stay; the drivable
  samples stay in one unit each. Refused: nothing to include, invalid rectangle.
- **Terrain** (rect, heights = one value or 4 corners -> bilinear, cell 1..100 m, an EXISTING material): a grid of quads,
  uv = plan / 8 m, normals up.
- **Barrier** (clicked / given points, open or closed, height 0.3..30 m, thickness 0.1..5 m, sample step 0.5..20 m, side 1 / -1,
  front + back materials, default wall / wallback): front
  faces on the points' line facing away from the body, top and back faces; the fronts become car-solid wall collision. Refused:
  self-crossing, turning tighter than its thickness, bad side / height.
- **Prefabs**: Save the selected face groups as `<name>.prefab.json` (positions relative to their bounding-box centre / lowest
  point, uv, normals, colours as the kit reads them) in the Workbench's prefab folder (config `prefabs`, default
  `state\prefabs`; never inside a project; tests use their own test-area folder); insert a copy at a position turned by an angle.
  Refused: unknown / damaged prefab, bad name, a material the project does not have, overwrite without consent.
- Allowed per kind: only the kind's own arguments (SCENERY_KEYS whitelist; anything else is refused).
- **Cut rounding**: terrain cells, barrier steps and prefab faces may cross a unit cut; the kit clipper loses the same
  4-decimal rounding slivers there as on race layouts (< 0.00005 m x perimeter, reported as cut_rounding_slivers_m2) - accepted
  for these three kinds; roads and all other edits keep the strict clip rule (found by test_trackedit_v26 s02: 22 terrain cells
  losing 0.0001 m2 in total).
- Verified (offline, `tests\test_trackedit_v26.py` 20/20; NOT gameplay validation): include grows only spanning units; flat and
  4-corner terrain exact; barrier geometry / thickness; prefab save + 45 degree insert against an independent rotation; layout +
  include + terrain + barrier + prefab STAGED (kit gates), scenery corners in the built mesh, barrier fronts as wall collision,
  streamed.dat = the dry run; undo / redo / save / reopen, failed save keeps both files; GUI (section scenery).

## An original loop built entirely through the editor (v0.27)
- `tests\test_trackedit_v27.py` builds a new ~594 m rounded-pentagon loop (306 stations, 17 units, not the demo's route)
  through the editor server's own HTTP endpoints (the ones the page's buttons call, token required: a request without it is
  403): race layout (replace "all") -> terrain refused outside the units -> units include -> terrain -> barrier -> prefab saved
  and inserted turned 180 degrees -> checkpoints at 4 chosen stations -> race check -> Save -> Stage = **STAGED, every kit gate**.
  Then: every OBJ face group belongs to an editor block (no demo geometry left), scenery corners in the built mesh, barrier and
  prefab fronts as wall collision, streamed.dat = the dry run, reopen exact, a second Stage builds identical package files.
- **include fix (found here)**: v0.26 sampled the rectangle on a 1 m grid and missed thin wedges (one terrain cell lost 0.25 m2,
  refused by the clip rule). include now clips the rectangle exactly by each unit's two cut half-planes and grows the lateral
  bounds to that polygon's vertices + 0.25 m, **capped 1 mm short of the apex** where the unit's cut lines meet (kit rule: the
  region quad must stay convex; past the apex the kit refuses it). Geometry beyond such an apex cannot be held by that unit.
- **Screenshots**: `ui_smoke_trackedit.screenshot(project, png, view=(pitch, yaw, dist), layers=[...])` - headless Edge with the
  SAME shared test profile and lockout guard as the self tests, read only; the page accepts `&view=` / `&layers=` for this
  (no effect otherwise). Pictures: `logs\screens\v027_overview.png`, `v027_units_collision.png` (editor, offline).
- Runtime: NOT tested (no game launch). Plan: `RUNTIME_ACCEPTANCE_PLAN.md` (load, streaming, surface, walls, scenery, laps /
  checkpoints, AI, respawn, grid, traffic).

## v0.30 (2026-10-31): developer workflow, New-data-mod fix, Workbench exe
- **Developer workflow**: the button
  **Developer workflow** at the bottom of this window opens `wbn_gui.py` (its own process): **1 New project** from the kit's
  examples (`tune-data`, `traffic-density`, `events-observer`, `events-v2`; requirements checked against the kit's
  HOST_INFO.json), **2 Tune** (the editor catalogue `data\EDITOR_CATALOGUE.json`: every row's default, unit, host limit and rule
  with its source; a slider only where the host declares the row's range; byte-preserving edits; Save only after Preview),
  **3 Test this project** (validate -> build -> stage through the existing import staging -> compatibility (the tester
  launcher's gate, `vendor\bmcompat.py`) -> approvals REPORTED -> the launch plan for a tester bundle and the guarded runner;
  progress, Cancel, problems linked to file / line / field / editor row, the last successful output). Same functions on the
  command line: `wbn.py`. Guide: DEVELOPER_WORKFLOW.md; reference: DEVELOPER_CLI.md.
- **New data mod fix**: v0.29 wrote `[bmashup.tune] version = 1` also for AI rows (the host needs 2) and allowed AI rows only
  0 .. 16 (16 x the kit catalogue's placeholder 0). Rows the editor catalogue knows now use the host's own limit (AI rows from
  their code default, signed rows -B .. B, never-read rows refused) and the mod gets the version its values need
  (`wb_datamod.py` with the developer workflow's `wbn_rules` / `wbn_catalogue`).
- **Kit-relative defaults**: a Workbench inside an extracted kit (`<kit>\workbench`) uses the folder around it as the kit ONLY
  when it holds the kit marker files (HOST_INFO.json, tools\bmpack\bmpack.py, sdk\BUILD.md; `wb_core.kit_marker_ok`);
  otherwise the kit must be given (Settings / `--kit`). No workspace path is a default.
- **Workbench exe**: `exe\wbstart.c` + `exe\build_wbexe.py` build "Burnout Mashup Workbench.exe" (deterministic llvm-mingw
  build, no console, a gear icon; adapted from the tester launcher's starter). The kit puts it in the kit folder; it starts
  `workbench\workbench.py` with pyw / pythonw (Python 3.11+) and passes dropped files on. Windows may show "Windows protected
  your PC" the first time (the exe is not code-signed): More info > Run anyway. The exe is built at kit packaging; no built exe
  is kept here.
- Tests: suites `wbn` (developer workflow, one process per case), `wbexe` (the exe) and `datamod` d07 (AI rows) in
  `tests\test_deps.json`.

## v0.31 (2026-11-01, gp\workbench_te): track-editor authoring tools
The track editor gains an **Authoring tools** panel: profiled roads (width / bank / grade, cross-sections) and sloped /
variable-width race routes with outer-wall gaps; T / Y / cross junction pieces and road-end joins (geometric only - the AI route
cannot branch); height-grid terrain with brushes and road-edge blending; vertex / edge / face mesh editing (move / turn / scale,
triangulate, subdivide, extrude, explicit hole fill); original-texture import with provenance, new / duplicate materials, UV
transforms, vertex-colour painting; a prefab library with previews, snapped placement, repeats along a path and linked-copy
refresh; a streaming / LOD / visibility report with the limits classified (format / host / tool / editor); wireframe / normals
overlays and clickable diagnostics; backups on Save, source export / import, a version record and "prepare test" (no launch).
Tutorial, capability matrix, known limitations and blocked items: **TRACK_EDITOR_AUTHORING.md**. Offline only: every feature is
runtime-unverified. Tests: suites te31 .. te41.

## v0.32 (2026-11-01, Burnout Mashup 0.2.0-alpha.2): the track editor opens from the window
**New track project** tab: **Open in track editor...** starts the editor for the project just created, else for the *Project
folder* when it is a track project, else for a folder you pick (refused with a message when it has no `workbench-track.json`).
The editor runs in its own console window titled "Burnout Mashup track editor" (the console Python beside the Workbench's
pythonw; working folder = the project, never the program folder) with the Workbench's settings file; closing that window stops
it, and when the editor stops with an error the window stays open with the reason. **Track editor guide** opens
**TRACK_EDITOR_GUIDE.md**, a step-by-step guide for new users (the reference stays TRACK_EDITOR_AUTHORING.md). The editor itself
is unchanged. Test: rel021 `tests\test_wb_button.py` (command line and quoting, the cmd.exe wrapper and its error pause, the real
editor serving a project, the window's button, the guide).

## v0.33 (2026-11-02, Burnout Mashup 0.2.0-alpha.2): an easier track editor, buildings, project health, sharing
User documentation: `TRACK_EDITOR_GUIDE.md` (new users) and `TRACK_EDITOR_AUTHORING.md` (reference, capability matrix, limits).
- **Authoring tools grouped by task** (Race layout, Roads, Terrain, Buildings / scenery, Materials, Mesh, Streaming, Inspect,
  Project / test) with **Preset** lists, a **Guide** button per group, tool search and a **First track walkthrough**.
- **Starter projects** (`data/starters`, original): town_circuit, hill_country and more - replayed through the normal tools as ONE
  undo step, rolled back completely when a step is refused.
- **Problems you can act on**: every failing diagnostics item has a "How to fix" line and an "Open tool" button.
- **Build, validate, stage + prepare test** in one step (new folder per run, last good output kept, a path-length guard for the
  Windows 260-character limit). Nothing is launched or approved.
- **Building generator** (footprint, height, roof, wall thickness, door openings that are real gaps in walls and collision) and
  **low-poly trees** (static geometry).
- **Project health**: OBJ compaction with a backup first (one undo step); optional backup retention (preview + confirm).
- **Viewer**: wireframe / normals drawn in 64 m chunks with view culling (large tracks).
- **Shareable export**: provenance + licence per file, game data and unknown files excluded, deterministic zip.
- Branch lanes and bridges: templates **branch** (a bypass beside the main road) and **fig8** (a road crossing over itself),
  checked by trackbuild 0.3.3; race layouts of 18..64 sections with computed visibility.
Everything here is checked offline; it has not been driven in the game yet (RUNTIME-UNVERIFIED).

## Retail-style track authoring (v0.33)
Dress your own track in the style of the Burnout 3 tracks on YOUR disc. Panels **Retail-style authoring** and **Retail-style
designer** in the track editor; step-by-step guide: `RETAIL_STYLE_GUIDE.md`.
- **Asset library** built locally from your own game data (read only, cached by file hash): textures, roadside models, buildings and
  structures of every track, with measured sizes, facing and provenance. Nothing from the game is shipped with Burnout Mashup.
- **Styles** (`data/rta_styles`): measured presets (waterfront city, downtown city, countryside) and an original-only style;
  derive your own from any track.
- **Generate** roads, verges, walls, buildings, trees and posts along your route from a style: preview first (problems listed, Apply
  disabled while there are any), then ONE undo step; regenerate one part with a new seed, lock parts.
- **Place** single pieces (buildings, posts, trees, props as static scenery) with a preview.
- **Share recipes, never content**: a shared project holds instructions only; whoever opens it rebuilds the pieces from their own
  game data. Anything built from your game data stays on your PC.
Needs trackbuild 0.3.3 (shipped in `tools/trackbuild`). Offline-checked; not yet driven in the game.

## Safety and limits
- One operation at a time (buttons disabled + `state\OPERATION.lock` across windows; the pipeline's own cache lock too).
- Every command is an argument list with an explicit working directory; paths with spaces are kept whole.
- **Pipeline folder path with spaces**: the pipeline's host build recipe passes the tree path unquoted (`BO3_GEN_OPT
  -include <tree>/...`), so the Workbench refuses to start a build when the pipeline folder path has a space (specs, caches,
  mods and game data may have spaces). `gp\release` has none.
- GUI tested by scripted button presses (tests\test_wb.py t13; test_stage.py s09, g01-g03; test_newproj.py n03;
  test_profile.py p03, p06; test_multi.py m04, m05, m07; test_launch.py l13; test_mods.py d06, d07; test_import.py i10; test_car.py c09; test_track.py t09), not
  by a person. The track editor page is tested by a scripted self test in headless Edge (test_trackedit.py e07; retail view:
  test_trackedit_v15.py r05; transparency probes + property edits: test_trackedit_v16.py t03 and the e07 steps; duplicate /
  bridge: test_trackedit_v22.py b07, section construct), not by a person.

## Test runner: smoke / affected / full
```bash
py -3 -B tests\run_tests.py                 # = affected (default)
py -3 -B tests\run_tests.py smoke
py -3 -B tests\run_tests.py full
py -3 -B tests\run_tests.py --suite trackedit20 --cases x01,x02     # focused development run
py -3 -B tests\run_tests.py affected --dry-run [--changed wb_trackedit.py,trackedit.html]   # show the selection only
```
- **Testing policy (owner 2026-10-29; replaces every earlier "run the mandatory regressions" instruction of this folder)**:
  - during development: focused tests (`--suite S --cases ...`, or a suite's own `--only`);
  - each milestone: the shared-code consumers, new and affected suites once on the final code, as an explicit list
    (`--suite a,b,...`, consumers from the map; `affected` gives the same list unless a FULL entry - wb_core / wb_stage /
    wb_kit / workbench.json - changed, in which case it would select full: use the explicit list then);
  - the **full** suite runs **only when the owner says so** (owner, 2026-10-29; replaces the earlier "at session end / before
    a release / for shared-core changes" rule - those are now reasons to ASK for a full run, never to start one);
  - a full run is **reused**, not repeated, when no relevant input changed (`full` with evidence reuse: unchanged suites are
    REUSED; documentation never makes it pending - don't re-run it for docs);
  - record what passed and what is pending: `py -3 -B tests\run_tests.py status` prints the affected suites still pending and
    whether the last passing full run is CURRENT or PENDING. A milestone may be complete with the full regression PENDING;
    do not call it fully validated until status says "fully validated (full regression CURRENT)". Checkpoints state it.
  - every assertion and safety check stays (snapshots of protected areas, cancellation, timeout and process-cleanup cases).
  `smoke` (static checks + self-contained fast cases, ~80 s fresh, ~25 s when evidence is reused) is a quick sanity pass,
  never a milestone verdict.
- **affected** selects suites from the files changed since the last affected / full run without failures (baseline
  `tests\results\runner_baseline.json`: sha256 of every watched `*.py / *.html / *.json / *.md` of gp\workbench and its tests)
  or from `--changed`, through the explicit map `tests\test_deps.json`. Shared core (`wb_core.py`, `wb_stage.py`, `wb_kit.py`,
  `workbench.json`), any watched file the map does not know, and no baseline select **full**; `*.md` selects nothing. Shared
  code lists its consumers: e.g. `wb_trackedit.py` / `trackedit.html` / `wb_retail.py` -> the trackedit suites (trackedit, trackedit15 .. trackedit22) + track
  (the editor milestones' mandatory regression set, unchanged); `wb_profile.py` / `workbench.py` -> profile, multi, mods,
  launch, import, car, track, wb, stage and (through `test_car`) the trackedit suites; a test module -> itself and the suites
  importing it (`test_trackedit_v17.py` -> v17 .. v20). A self-check (smoke, `test_runner.py` r02) proves the map selects every
  suite for every file its test code imports (test modules followed transitively; product modules reach each other only
  through the FULL shared core).
- **Evidence reuse**: a suite (with its case list) is REUSED only when an earlier PASS has the same evidence key: sha256 of its
  static import closure (product + test modules), its map inputs (fixtures, tools such as the kit's trackbuild SHA256SUMS /
  VENDOR.json and `tools\runners\g_run.py`, configuration such as `workbench.json`, `trackedit.html`), its prerequisite's
  inputs, the Python version and its arguments. Failures are never reused; `--no-reuse` runs everything selected. Game data
  (protected, read only) is not hashed.
- **Report**: every check is PASSED / FAILED / REUSED (with the evidence's time and run) / SKIPPED (with the reason); the
  runner's exit code is 1 when any selected suite failed (rc != 0, a FAIL verdict, a missing or stale result file, rc and
  verdict disagreeing, a crash, a failed prerequisite), 2 for a map / lock / usage error, else 0. All selected suites run
  after a failure unless `--fail-fast` (the rest is reported SKIPPED). Logs: `logs\runner\<time> <mode>\` (REPORT.json with the
  selection, statuses, reasons and bottlenecks; one log per suite; result copies); `tests\results\evidence.json`,
  `tests\results\timings.jsonl` (wall time per suite per run).
- **Sequential**: one suite at a time (OPERATION.lock, the runner roots and headless Edge are shared) and one runner at a time
  (`state\RUNNER.lock`, held by the process). Partial runs (smoke / `--cases`) restore the suite's canonical
  `tests\results` file, which therefore always holds the last whole run.
- **Builds / data roots**: the fixture prerequisite (`make_fixture.py`, idempotent) runs only before `wb` and only when its
  inputs changed; the cold fixture build is never repeated. profile, multi and mods (d09) each make one disposable data root
  with `g_run make-root` (a 2.3 GB copy of `runtime_data\base`): that copy is the product's Prepare under test, so it stays per
  suite (isolation); `affected` avoids it whenever those suites are not selected.
- Tests of the runner: `py -3 -B tests\test_runner.py` (selection rules on the real map, map coverage, baseline, failure
  propagation with fake suites that pass / fail / crash / lie / leave a stale result / fail a prerequisite, evidence reuse,
  partial runs, the single-runner lock, the policy status (pending / CURRENT, docs never pending, a repeated full reuses);
  fake workbench roots in `test area\runner tests <time>`).

## Tests
```bash
py -3 -B tests\make_fixture.py
py -3 -B wb_core.py run "test area\specs with spaces\release_spec_fx ok.json" --pipeline test_pipe\release --cache "test_pipe\release\cache with spaces"
py -3 -B tests\test_wb.py
```
Staging + settings (v0.2-v0.4): `py -3 -B tests\test_stage.py` (own test area `test area\stage tests <time>` and a copied
install under `%TEMP%\wb copied install <time>`, about 30 s) -> `tests\results\stage_tests.json`. The tests pass the developer
workspace's paths explicitly (`wb_core.workspace_values()`); they never write the real `workbench.json`.
New plugin projects (v0.5): `py -3 -B tests\test_newproj.py` (test area `test area\newproj tests <time>`, about 11 s) ->
`tests\results\newproj_tests.json`.
Test profiles + kit switching (v0.6): `py -3 -B tests\test_profile.py` (test area `test area\profile tests <time>`; one
`g_run make-root` + three dry runs, about 75 s) -> `tests\results\profile_tests.json`. Run `tests\test_wb.py` from the same
kind of shell each time: the pipeline's cache key includes PATH (its `env` toolchain), so a Git Bash run misses PowerShell
cache entries.
Multi-mod profiles (v0.7): `py -3 -B tests\test_multi.py [--only m01,m02,m03,m04]` (test area `test area\multi tests <time>`;
one `g_run make-root` + two dry runs, about 90 s; `--only` runs the cheap stages without a data root) ->
`tests\results\multi_tests.json`. Refusal cases use small data-only fixture packages (a mod.toml + a record marked TEST FIXTURE).
Launch / Stop / Results (v0.8): `py -3 -B tests\test_launch.py [--only l01,l02]` (test area `test area\launch tests <time>`;
MOCKED: a fake `g_run.py` with the real runner's session / guard / summary contract and td_run's boot logic, a Python child as
the "game", marker-only roots - no game, no real runner call, no 2.4 GB copy) -> `tests\results\launch_tests.json`.
Mod preview + drafts (v0.10): `py -3 -B tests\test_mods.py [--only d01,...,d08]` (test area `test area\mods tests <time>`;
d01-d08 need no data root (~18 s); d09 = one `g_run make-root` + Preflight + dry run, ~55 s in all; no game) ->
`tests\results\mods_tests.json`.
Import + admission parity (v0.11): `py -3 -B tests\test_import.py [--only i02,...]` (test area `test area\import tests <time>`
only, ~25 s; no data root, no game; makes two junctions in its own test area and removes those links again) ->
`tests\results\import_tests.json`.
Car projects (v0.12): `py -3 -B tests\test_car.py [--only c02,...]` (test area `test area\car tests <time>` only, ~21 s; reads
the configured game data for the donor (read only); no data root, no game; makes one junction in its own test area and
removes the link again) -> `tests\results\car_tests.json`.
Track projects (v0.13): `py -3 -B tests\test_track.py [--only t04,...]` (test area `test area\track tests <time>` only, ~100 s;
reads the configured game data for the donor; no game; one junction in its own test area, removed again) ->
`tests\results\track_tests.json`.
Track editor (v0.14): `py -3 -B tests\test_trackedit.py [--only e03,...]` (test area `test area\trackedit tests <time>`, ~30 s;
e07 starts headless Edge with a throwaway profile in the test area and stops it) -> `tests\results\trackedit_tests.json`;
the UI smoke alone: `py -3 -B tests\ui_smoke_trackedit.py PROJECT WORK_DIR [--retail]`.
Material edits + retail view (v0.15): `py -3 -B tests\test_trackedit_v15.py [--only m01,...]` (test area
`test area\trackedit15 tests <time>` with its own retail cache, ~40 s; reads `<game data>\Tracks\US\P1_V1` read only; one
headless Edge run) -> `tests\results\trackedit15_tests.json`.
Material properties + transparency (v0.16): `py -3 -B tests\test_trackedit_v16.py [--only t01,p05,...]` (test area
`test area\trackedit16 tests <time>` with its own retail cache, ~2 min: 4 builds; one headless Edge run) ->
`tests\results\trackedit16_tests.json`.
Face-group translation (v0.17): `py -3 -B tests\test_trackedit_v17.py [--only g01,g05,...]` (test area
`test area\trackedit17 tests <time>`, ~1.5 min: 4 builds; one headless Edge run) -> `tests\results\trackedit17_tests.json`.
Multi-group moves (v0.18): `py -3 -B tests\test_trackedit_v18.py [--only s01,s05,...]` (test area
`test area\trackedit18 tests <time>`, ~1.5 min: 4 builds; one headless Edge run) -> `tests\results\trackedit18_tests.json`.
Clip check (v0.19): `py -3 -B tests\test_trackedit_v19.py [--only c01,c02,...]` (test area `test area\trackedit19 tests <time>`,
~1.5 min: 4 builds; one headless Edge run) -> `tests\results\trackedit19_tests.json`.
Selection transforms (v0.20): `py -3 -B tests\test_trackedit_v20.py [--only x01,x02,...]` (test area
`test area\trackedit20 tests <time>`, ~2 min: 5 builds; one headless Edge run) -> `tests\results\trackedit20_tests.json`.
Boundary / weld (v0.21): `py -3 -B tests\test_trackedit_v21.py [--only w01,w02,...]` (test area `test area\trackedit21 tests <time>`,
~1.5 min: 4 builds; one headless Edge run) -> `tests\results\trackedit21_tests.json`.
Layout construction (v0.22): `py -3 -B tests\test_trackedit_v22.py [--only b01,b02,...]` (test area
`test area\trackedit22 tests <time>`, ~2.5 min: 5 builds; one headless Edge run) -> `tests\results\trackedit22_tests.json`.
Capture under display scaling (v0.21): `py -3 -B tests\test_capture_dpi.py` (seconds; opens small test windows; live cases at the
scaling present; `tests\results\capture_dpi_scales.json` records every scaling a live run passed at).
`make_fixture.py` builds an isolated engine copy (`test_pipe\release`) and fixture specs / mods; the second line is the one cold
build the tests compare warm builds with. Results: `tests\results\wb_tests.json`.

## Later milestones (not implemented)
Scripted navigation in visible runs (e.g. to the garage); menu / race scenes; archive import (verified extraction); more
project templates (other SDK examples' services); developer test-launch workflows; more example recipes (the other SDK
plugins; other authored examples: veh-series, fetex-art); the car features deferred in v0.12 (interactive 3D preview, own
series, registered paints, own garage photo, `[bmashup.cars]` v2 options); the track features deferred in v0.13 and the
editor path above (new materials or route editing next, then unit region editing, gap filling / topology edits and road tools; retail checkpoints need a verified S1 reader first); an owner-present in-game check of a Workbench-built track.

## Track builder binding: trackbuild 0.3.0 sloped routes (v0.28)
The track editor and the track recipes (track-project, trackbuild-testloop) use the trackbuild tree named by the optional setting
`"trackbuild"` in workbench.json (a folder holding tb.py); not set = the kit's own `tools\trackbuild` (0.2.1 in kit 0.6.0). This
workspace binds main21's `slices\main21\kit\trackbuild` = trackbuild 0.3.0 (main21 patch 66, sloped routes; RESULT manifest).
Everything else (bmpack, SDK, carimport, kit identity) still comes from the kit. `wb_core.trackbuild_dir` / `kit_path` resolve it.
- Flat tracks: unchanged bytes (0.3.0 builds them byte-identical to REFERENCE_0_2_1; test_track t02 = the kit reference).
- The editor's route-floor warning (roads) and the race check follow the route height at each sample (`wb_construct.route_samples`,
  = the 0.3.0 V2_drivable_coverage rule; wall probes at each station's height). Flat routes: the same numbers as before.
- New template `hill` (tb.py gen-testloop --variant hill, +8 m hill; needs 0.3.0). The race layout generator still builds one height.
