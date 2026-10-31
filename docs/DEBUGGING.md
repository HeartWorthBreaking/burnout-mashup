# Debugging and validating mods (mod kit 0.4.1)

## Before you start the game
1. `py -3 -B tools\bmkit_doctor.py` - prerequisites (exit 3 + the fix when something is missing).
2. Data mods: `py -3 -B tools\bmpack\bmpack.py validate <mods folder> [...] --game-data "<game data>"` runs the host's own readers
   in the game's order: every refusal is printed as `[service] <mod id>: <the host's reason>` - the same text the game logs.
   Vehicle tables (`[bmashup.cars]`, `series`, `paints`) are checked by `tools\vehtool` `validate` (bmpack does not run them).
3. A built mod against its manifest: `bmpack.py verify <mod folder>` (every file's sha256).
4. Plugins: build with `sdk\build.ps1`; the printed sha256 is what you approve (`plugin-approvals.toml` or MODS page APPROVE CODE).

## Reading the host log (`<profile>\Roaming\BurnoutMashup\logs\run.log`)
| line | meaning |
|---|---|
| `[PLATFORM] host: Burnout Mashup platform 0.1.9, build bmp-0.1.9+...` | the host is the reference host |
| `[MOD] <id> <version> ...` / `[MODS] ... changes gameplay: ...` | a mod was found / its gameplay label |
| `[DEPS] the mod list in dependency order ...` | `requires_mods` reordered the list |
| `[ADMIT] mod <id> <ver> (<folder>) refused, the game starts without it: <reason>` | a clash or an unmet requirement: that mod alone is off |
| `[PLATFORM] mod <id> <ver> refused ...` | the mod needs a newer platform / an unknown table or key |
| `[PLUGIN] <id>: running (plugin API 1)` + `service <name> <version>: used / not used` | a plugin loaded |
| `[PLUGIN] ... not approved ... add: "<id> sha256:<hash>"` | approve the exact module |
| `FATAL ...` + exit code 88..97 | a host guard stopped the start (`INSTALL.md` s5 B lists the codes) |

## When something goes wrong
- Turn mods off one by one (MODS page or move the folder out); a refusal never stops the game, a FATAL does.
- Keep the run short and note what you pressed; a screenshot of the screen helps.
- Export a diagnostic package: `py -3 -B tools\bmdiag\bmdiag.py --bundle <tester bundle> --data "<game data root>" --out diag.zip`
  (versions, hashes, key log lines, the mod list by name + hash, the preflight output). It never takes saves, progress, game
  data, mod file contents or environment values, and it replaces your user / computer name, home / bundle paths and e-mail
  addresses. Look at the files before you send them. `--include-more` adds the whole log and settings files (still redacted).
- Report it as `CONTRIBUTING.md` says.

## Self-test of the kit
`py -3 -B tools\kit_selftest.py <new folder> [--game-data DIR] [--cc FILE] [--sdk --llvm-mingw DIR --cmake EXE --ninja EXE]`
runs every tool's test suite from the kit (suites that need game data or the compiler are SKIPPED, never passed, without them)
and, with `--sdk`, rebuilds the SDK examples and compares them with `sdk\EXPECTED_BUILD_SHA256.txt`.
