# Troubleshooting

First run `preflight.cmd` - most problems show up there with a fix. Logs: `profile\Roaming\BurnoutMashup\logs\run.log`; the
console window of `play.cmd`; `gamedata\xbox_kernel.log`.

| Symptom | Cause | Fix |
|---|---|---|
| `play.cmd: no game data` (exit 3) | `gamedata\` not prepared | `prepare.cmd data --copy-from ...` or `--install-from ...` ([INSTALL.md](INSTALL.md) s3) |
| "SDL2.dll was not found" | SDL2.dll missing / moved | prebuilt: unpack the zip again (SDL2.dll must stay in `host\`); own build: `build-host.cmd --replace` (it puts SDL2.dll into `host-local\`) |
| play.cmd starts the wrong host | `host-local\` exists (your build wins) or `BMASHUP_HOST` is set | `set BMASHUP_HOST=prebuilt` (or `local`); `play.cmd --print-env` shows the exe; `preflight.cmd` names the host in use |
| preflight `host exe ... neither the expected reference build nor a documented local build` | the exe in use was changed or built another way | unpack the zip again (prebuilt) or run `build-host.cmd` (own build) |
| `build-host: CANNOT RUN` | a prerequisite is missing (Option B only) | the message names it and the fix (BUILD_HOST.md s2 / s3) |
| `build-host` exit 2 (hash differs) | another toolchain / capstone / repository state | use exactly the pinned archives; report with `build\work-<n>\build_from_source.log`; the prebuilt host is unaffected |
| "Takedawn needs a Vulkan 1.3 graphics driver", slow CPU drawing | no Vulkan 1.3 driver / loader | install the GPU vendor's current driver; preflight checks `System32\vulkan-1.dll` |
| Game ends at start with exit status 3 / "data is not installed" | `.complete` marker missing or wrong | redo `prepare.cmd data` |
| preflight `game signature ... not the retail NTSC-U` | PAL / Japanese / modified disc | only the North American retail disc is supported |
| preflight `files differ from SHA256SUMS.txt` | damaged / edited bundle file | unpack again into an empty folder |
| preflight `extra DLLs` | a DLL was added beside the program | remove it (a `vulkan-1.dll` there replaces the driver's) |
| `prepare.cmd: Python 3 was not found` | no Python | python.org, 3.11+, "Add python.exe to PATH" |
| `prepare demos` FAILED | a generator refused or crashed | read `diag\prepare_demos.log`; report with `diag.cmd` |
| a mod is missing in game | refused at admission | `run.log`: `[ADMIT] mod <id> ... refused ...: <reason>` or `[PLATFORM] mod ... refused`; MODS page shows the state (`NEEDS MOD`, `needs a newer platform`) |
| the game stops at start with exit 88-97 + a message box | a mod's own invalid table or a host guard (88 track route data, 90 STATIC, 91 capacity, 92 content / out of memory, 93 tune bound, 94 track mode, 95 / 96 World Tour, 97 lanes) | move the last added mod out of `mods\user`, report it |
| plugin "not approved" | approvals are per exact bytes | add the logged `approved = [...]` line or use APPROVE CODE on the MODS page |
| menu presses repeat / skip on the World Tour region page | retail hold-to-repeat after the globe spin | tap, don't hold |
| first races hitch | shader cache being built (`profile\Local`) | expected on first runs |
| "Check for updates" says nothing about Burnout Mashup | it asks GitHub for upstream Takedawn releases | expected; the bundle has no updater |

Still stuck: [BUGS_AND_CONTRIBUTING.md](BUGS_AND_CONTRIBUTING.md).
