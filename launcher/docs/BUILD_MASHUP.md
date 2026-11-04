# Build Mashup - build the host on your PC from this source tree and your own game

The launcher's **Setup** tab has a **Build Mashup...** button (host card). It opens the Build window; the same build runs from the
command line as `launcher\build-mashup.cmd` (`build-mashup.cmd help`). Both run `tools\launcher\bmbuild.py`, which runs the
repository's own build scripts (`build\fetch_upstream.py`, `apply_layers.py`, `regen.py`, `apply_marks.py`, `build.ps1`, `verify.py`,
`host_info.py`; `docs\BUILDING.md` at the top of the repository) - there is no second build system. Nothing here starts the game.
A local build is a technical route, not a legal conclusion (`docs/PUBLIC_STATUS.md`).

## One click

Setup tab -> **Build Mashup**. That one button does everything: it finds your game (in `gamedata\`, or from your last build; only if it cannot, it asks for the folder),
asks ONCE for all the tools that are missing (name, source, size, licence of each), downloads them, builds, verifies the result and installs it.
With everything already there it asks nothing. It stops at the first thing that fails and says what to do; pressing it again reuses what is done.
**Build options...** opens the same window without starting; there, **Advanced options** has the upstream source, the tools (one tool at a time, or a folder that already holds them) and the build folder.

## 1. What you need

| | |
|---|---|
| your game | the retail **North American (NTSC-U)** Burnout 3: Takedown for the original Xbox: your installed game data folder (it holds `Burnout 3 Takedown\default.xbe`), the extracted disc folder, the `default.xbe` file, or a disc image (`.iso` / `.xiso`, plain xiso or a full dump). Only that one executable is supported (sha256 `9f497acd82ad...`, `build/EXPECTED.json`): the recompiler's seeds and patch sites are addresses in it. Other regions, revisions and modified files are refused with the reason (`check-input` shows it before anything else runs). |
| the pinned tools | llvm-mingw 20260922 (clang 23.1.2), CMake 4.4.4, Ninja 1.13.2, SDL2 2.32.10 (MinGW), glslang 16.6.0 (built here), Vulkan-Headers 1.4.363.0 (+ an import library made here), Git (any 2.x; PortableGit 2.56.0.2 is offered), a Python with capstone 5.0.9 |
| Windows | Windows 10 / 11 x64, Windows PowerShell 5.1, Python 3.11+ (the launcher's), about 0.6 GB free for a build folder |

## 2. Tools: found, or downloaded only when you say so

The window's tool list (and `build-mashup.cmd tools`) shows every tool with the version found and where. Tools you already have are used
in place: **Use existing toolchain folder...** (or `--toolchain DIR`, `--deps`, `--cmake`, `--ninja`, `--git`, `--python-capstone`); a
version other than the pinned one is reported, not used. For a missing tool, **Download selected...** (or `build-mashup.cmd download TOOL`)
first shows the tool's **licence notice**, the official URL, the size and the pinned sha256, and asks you - one tool at a time. Then it
downloads into the tools folder (default `%LOCALAPPDATA%\BurnoutMashup\tools`), checks the sha256 (a different file is deleted and never
used; an interrupted download leaves nothing), and unpacks into `<tool>.partial`, renamed when complete. glslang is compiled there; the
Vulkan import library is generated from your driver's `vulkan-1.dll` export list; PortableGit's self-extractor is started once (after the
sha256 check); capstone comes from the Python Package Index into a private Python environment and its installed files are checked
against pinned sha256 values. No administrator rights, no installer, no PATH or registry change. Archives you downloaded yourself can be
given with `--downloads FOLDER` (checked the same way). Pins and licence notices: `tools\launcher\BUILD_TOOLS.json` (= `tools\prepare_deps.py`).

## 3. Where it builds

A build folder you choose (default `%LOCALAPPDATA%\BurnoutMashup\build`); it must be writable and outside the source checkout. Paths with
spaces or non-ASCII characters are fine: the tools reach the folder through a junction (a directory link; no administrator rights
or developer mode needed), because upstream's CMake splits a list at spaces. The junction goes into the FIRST of
`%LOCALAPPDATA%\BurnoutMashup\links`, `%ProgramData%\BurnoutMashup\links`, `%SystemDrive%\BMashup-links` that has a plain-ASCII path and
passes a check made on every run: the junction can be created, and folders can be made, written, renamed, replaced and removed THROUGH
it (some PCs refuse renames through a junction in some folders; the maintainer PC refused them under `%LOCALAPPDATA%`). A refused place is
named in the log (`tool path of the build folder: ... (not usable: ...)`) and its junction removed again; a real folder already at the
junction's name is never touched. `--alias-root FOLDER` tries only FOLDER. If no place passes, the build is refused before anything runs
(exit 2) with each reason: choose a build folder whose path has no spaces / non-ASCII characters, or a writable `--alias-root`. `%TEMP%`
is never used for the junction (temp clean-up tools may walk into it). The build steps run with a minimal environment (the reference build's: system
essentials, TEMP inside the build folder; no user PATH, no `TAKEDAWN_*` / `BMASHUP_*` / Python variables, no APPDATA). Your
`default.xbe` is read in place; from a disc image it is copied once into `<build folder>\xbe\`. The generated code, objects and the exe
stay in the build folder and in `launcher\host-local` - they are derived from your game: keep them on your PC, never share them.
`build-mashup.cmd remove-build-dir --build-dir DIR --yes` deletes a build folder (junctions are unlinked first; host-local is kept).

## 4. The steps, the cache, cancel and resume

| step | runs | output (in the build folder) |
|---|---|---|
| fetch | `build\fetch_upstream.py`: Takedawn + xboxrecomp at the pinned commits (GitHub, local clones read only, or any git remote incl. `file:///`) | `s1_fetch` |
| layers | `build\apply_layers.py host` on a copy | `s2_layers` |
| regen | `build\regen.py`: upstream's recompiler on your default.xbe (the analysis folder is removed afterwards, its logs kept) | `s3_regen` |
| marks | `build\apply_marks.py` (`--release` for the release build) on a copy | `s4_marks` |
| build | `build\build.ps1` (`-Release`: `BurnoutMashup.exe`) | `s5_build` |
| verify | `build\verify.py --profile release`: identical to `build\EXPECTED.json` `build_release` | `s6_verify` |
| host_info | `build\host_info.py` (+ `--check` against the exe) | `s7_host_info\HOST_INFO.json` |
| install | staged copy, re-verified, then swapped into `launcher\host-local` | `launcher\host-local` |

`BUILD_STATE.json` records every step with the **identity of its inputs** (the pins, the hashes of the scripts it runs, the host layer
files, your default.xbe's sha256, the capstone environment, the toolchain fingerprint, the profile, and the recorded outputs of the steps
before it). A step is reused only when its identity is unchanged **and** its output still verifies now (digests recomputed); otherwise it
runs again, and each later step is reused only if what it reads is unchanged. Cancel stops the running step and its child processes; its
partial output is removed and the completed steps are kept. If a build is killed, the step it was in is redone next time. A second build
in the same folder is refused while one runs (`LOCK`).

## 5. Install, previous build, Play

The verified build (BurnoutMashup.exe, SDL2.dll, shaders, licence texts, HOST_INFO.json, BUILD_RESULT.json) is copied to
`host-local.new`, checked again, then `host-local` becomes `host-local.prev` and `host-local.new` becomes `host-local`; the repository's
`HOST_INFO.json` (for the Workbench) is written last. Any failure puts everything back. **Previous build** (Setup tab) or
`build-mashup.cmd switch-back` swaps `host-local` and `host-local.prev`. A build that is not byte-identical to the reference is never
installed. **Play is enabled only when** host-local holds BurnoutMashup.exe with its HOST_INFO.json and BUILD_RESULT.json and they agree
(sha256 of the exe, the build identity read from the exe, "verified"), the repository's HOST_INFO.json is the same file, and your game data
is prepared (Setup step 1). `build-mashup.cmd play-state` prints the same rule.

## 6. Time and disk

Measured on the maintainers' PC (`tools\launcher\BUILD_ESTIMATES.json`, shown in the window before you start): a clean build takes about
3 minutes (the recompiler about 2 of them) and about 0.5 GB in the build folder; a build with nothing changed about 10 seconds. A GitHub
fetch adds the download of both repositories. The free-space check needs the estimate of the steps that will run + 500 MB.

## 7. When something fails

| what you see | what to do |
|---|---|
| REFUSED (input) | give the retail NTSC-U game (section 1); `check-input` says what the file is (title, region, revision) |
| REFUSED (tools) | download the missing tools (section 2) or point to the ones you have; versions must be the pinned ones |
| REFUSED (space) | free disk space or choose a build folder on another drive |
| REFUSED (folder) | choose a writable folder outside the source checkout |
| REFUSED (lock) | another build runs in that folder: wait, cancel it, or use another folder |
| FAILED at fetch | network (GitHub source) or local clones without the pinned commits: fix and run again (nothing after it ran) |
| FAILED at layers / marks | this checkout or the sources differ from the pins: use a fresh copy of the repository |
| FAILED at regen | the capstone Python is not the pinned one, or the game file is not the supported one |
| FAILED at build | see `logs\build.log` and `s5_build\build.logs` in the build folder; check the tool versions |
| NOT identical (exit 4) | not installed, your previous build is still used: check the tool versions and that the checkout is unmodified |
| FAILED at install | the previous build was restored: close the game if it runs from host-local, then run again (only the install step runs) |
| CANCELLED (exit 5) | run again: completed steps are verified and reused |

Exit codes of `build-mashup.cmd build`: 0 done, 1 usage, 2 refused (nothing changed), 3 a step failed (previous build unchanged),
4 built but not identical to the reference (not installed), 5 cancelled.

## 8. Updates

The launcher can update to a newer published release of the Mashup channel (Help tab -> **Check for updates...**, or `update.cmd`):
the new **source** is downloaded, verified against a signed release manifest, unpacked into a new folder beside the current source and
built here with BUILD MASHUP (this build folder, its cache and the pinned tools); the exe must be identical to the release's reference
and is installed like any build (the previous build and the previous source are kept; **Switch back to previous version** restores
both). Nothing is checked, downloaded or built unless you press the button for that step; no update check runs at start, in the
background or from the game; an upstream Takedawn repository is never used. This release ships **without** an update channel
(`update_channel.json` is empty: the window says "No update channel configured"). Details: `docs\UPDATES.md`.
