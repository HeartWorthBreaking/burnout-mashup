# bmashup-modkit 0.7.0 - EXPERIMENTAL Windows x64 mod kit for the Burnout Mashup platform (reference host main21, platform 0.1.9)

**EXPERIMENTAL source release. Windows x64 only. Technically verified by the authors; NOT a release and NOT distribution-cleared**
(open questions: `docs/PUBLIC_STATUS.md`). For the Burnout Mashup build of Takedawn (Burnout 3: Takedown, native PC).
This tree contains no game material; what the tools build from your own game stays on your PC (`docs/LOCAL_OUTPUTS.md`).
Kit and tester documents were written for the private pre-releases (kit 0.7.0, tester package 0.4.0); where they name the private
reference build (`burnout3_bmashup.exe`, sha256 `f0b9c8a9...`), this source tree builds `BurnoutMashup.exe` with BUILD MASHUP
(`launcher/docs/BUILD_MASHUP.md`; expected values: `build/EXPECTED.json`).

| | |
|---|---|
| reference host | **main21**: build identity `bmp-0.1.9+2c8142e65f20`, sha256 `f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656`, **Burnout Mashup platform 0.1.9**, 25 services. The host is NOT in this kit: you build it yourself from the host source package with your own game (the tester package's `BUILD_HOST.md`); a build with the pinned toolchain gives exactly these bytes (file name `burnout3_bmashup.exe`). main21 = main20 (the MODS menu) + the main21 patches 66-130; service growth is append-only (`docs\CHANGELOG.md`) |
| versions | mod kit **0.7.0** - SDK **0.7.0** - bmpack **1.5.0** - bmdiag **0.1.0** - bmkit_doctor **0.1.0** - kit_selftest **0.1.0** - trackbuild **0.3.0** - Workbench **0.30** - the other authoring tools: see `docs\VERSIONING.md` and each tool's README |
| new in 0.7.0 | SDK headers of the main21 host (service versions: racers 6, rules 6, traffic 8, camera 4, hooks 3, events 7, settings 2, tune 3); new examples; trackbuild 0.3.0 with sloped routes; Workbench 0.30; the PS2-look converter (`tools\ps2look`, tool only); `HOST_INFO.json` and the tuning catalogue generated from the host; details: `docs\CHANGELOG.md`, `docs\MIGRATION.md` |
| not in 0.7.0 | trackconv (Revenge -> Burnout 3 conversion): research tooling, **not supported in this alpha** |
| binaries / game data | no `.asi`, DLL, game file, generated game code or Revenge content. The only exe is `Burnout Mashup Workbench.exe`, a small starter for the Workbench window built from `workbench\exe\wbstart.c`. Examples are AUTHORED sources or generators that read YOUR OWN game data locally |

## Start here
1. Install the prerequisites you need (`docs\PREREQUISITES.md`) and check them: `py -3 -B tools\bmkit_doctor.py`.
2. Get the host: prepare your own NTSC-U game data (`docs\GAME_DATA.md`) and build the host with it (the tester package's `BUILD_HOST.md`),
   or use the private prebuilt tester package if you were given one.
3. Build the example plugins: `powershell -NoProfile -File sdk\build.ps1 -BuildDir <new folder> -LlvmMingw <dir> -CMake <exe> -Ninja <exe>` (`sdk\BUILD.md`).
   Copy only the PLUGIN folders of `<build>\out` into your mods folder. The data-only template outputs (for example
   `example.content-template`, `example.events-v2`) are starting points to edit, not mods to enable as they are: enabled
   unchanged, the host refuses them or stops at start-up.
4. Make a data mod: `docs\MODDING_GUIDE.md`; authoring tools: `docs\services\AUTHORING_TOOLS.md`; validate it:
   `py -3 -B tools\bmpack\bmpack.py validate <mods folder> --game-data <game data>`. The Workbench is a window for the same steps:
   double-click `Burnout Mashup Workbench.exe` (or `py -3 -B workbench\workbench.py` from the kit folder); its Developer workflow
   window walks you from a template to a validated, staged mod and a launch plan (`workbench\DEVELOPER_WORKFLOW.md`).
5. Run it on your host (`docs\INSTALL.md`). When something goes wrong: `docs\DEBUGGING.md` and `tools\bmdiag`.

## Model
Install the host exe ONCE, then add / remove data mods and approved plugins by dropping folders into the mods folders - no
rebuild. A mod the host cannot serve, the later of two clashing mods, a mod whose requirements are unmet, or a content mod with a
bad declaration is refused ALONE (transactionally) and the game starts without it.

## Layout
| path | what |
|---|---|
| `sdk\` | bmashup-sdk 0.7.0 (26 headers + `bmashup_sdk.h`, 46 example folders (45 plugins and 52 mod.toml files are built by `build.ps1`), portable `build.ps1`, `EXPECTED_BUILD_SHA256.txt`) |
| `tools\` | authoring / packaging tools (each with tests), `bmpack` 1.5.0 (+ `host_readers` source package), `bmdiag`, `bmkit_doctor.py`, `kit_selftest.py`, `ps2look`, `_lib\bmkit_env.py` (shared configuration), `_vendor\` (vendored readers, `VENDORED.json`), `reference_host.json` |
| `workbench\` | the Workbench 0.30 (a window for mods, tracks and tuning; `workbench\README.md`) |
| `examples\authored\` | AUTHORED sources (cars, track descriptions, front-end art, vehicle series / paints); `AUTHORED_FILES.json` lists every non-text file with sha256 |
| `examples\content\` | generators that need your game data (the added car, the World Tour region placeholder); their outputs are DERIVED: local only |
| `examples\mods\` | bmpack specs (test packs, dependency fixtures) and data mod examples |
| `docs\` | GAME_DATA, PREREQUISITES, INSTALL, MODDING_GUIDE, DEBUGGING, CONTRIBUTING, LIMITS_AND_BEHAVIOURS, COMPATIBILITY, MIGRATION, VERSIONING, ROADMAP, CHANGELOG, TUNING_CATALOGUE; `docs\services\` per service / table |
| `HOST_INFO.json` | what the reference host offers (used by the compatibility checks) |
| `bmkit.example.toml` | optional configuration file example |
| `MANIFEST.json`, `SHA256SUMS_kit.txt` | every file with its sha256 |

## Licences
Kit sources: the project's own work; licences set by the project (MIT for code / SDK / tools, CC-BY-4.0 for docs, CC0-1.0 for
AUTHORED example assets the project may dedicate; per file: `REUSE.toml`; `docs/PUBLIC_STATUS.md` Q3). `tools\bmpack\host_readers` holds Takedawn host code
(MIT, `LICENSE-takedawn.txt`) and xboxrecomp's `recomp_cfg` (MIT, `xboxrecomp\LICENSE.txt`). `tools\_vendor` holds this project's
own research readers (`VENDORED.json`). No third-party code beyond these.
