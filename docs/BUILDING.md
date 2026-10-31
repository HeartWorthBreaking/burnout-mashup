# BUILDING - build Burnout Mashup from this source tree, on your PC, from your own copy of the game

This is a **technical description of a local build**. It is a distribution *model* (you produce everything that contains game
code yourself, from your own legal copy), **not a legal conclusion and not legal advice**: whether building and running a
recompiled copy of a game you own is permitted where you live is for you to judge (`docs/PUBLIC_STATUS.md`, Q7).
Windows 10/11 x64 only. Nothing of the game is in this repository and nothing of the game is downloaded by these scripts.

**The easy route: the launcher's Build Mashup** (`launcher\docs\BUILD_MASHUP.md`): the Setup tab's **Build Mashup...** button, or
`launcher\build-mashup.cmd build --input <your game>` on the command line. It checks your game input, finds the pinned tools (or downloads
them one by one after you confirm each, with its licence notice), runs exactly the steps of this document in an isolated build folder,
caches each step by the identity of its inputs, builds the release-named `BurnoutMashup.exe` (release profile, below), verifies it,
writes `HOST_INFO.json` and installs it into `launcher\host-local` (keeping the previous build). This document is the manual route and the
reference for what those steps do.

**Two profiles.** *Release* (what Build Mashup builds and installs): `apply_marks.py --release`, `build.ps1 -Release`, `verify.py --profile
release` -> `bin\BurnoutMashup.exe`, reference `build/EXPECTED.json` `build_release`. *Development* (the steps below without those
options): `bin\burnout3.exe`, reference `build`. Both are byte-reproducible with the pinned toolchain; the 27 generated-code objects are
identical in both; the release one is a window program with the Burnout Mashup version resource and icon and the first-start display
defaults of a packaged program (`BO3_RELEASE`). Use a fresh tree (steps 1 to 4) per profile.

## 0. What is local-only

| What | Where it is made | Rule |
|---|---|---|
| your `default.xbe` and disc files | you supply them | read only by the scripts; never copied into this tree; never uploaded |
| the generated game code (`recomp_*.c`, `recomp_funcs.h`, ...), with and without the Mashup marks | `<work>\gen_pristine`, `<work>\takedawn\src\game\recomp\gen` | derived from your game: keep on your PC, never commit, share or attach to an issue |
| objects, the host exe, the staged folder | `<work>\build`, `<work>\build\stage` | built from the generated code: same rule |
| analysis output of the recompiler | `<work>\xr` | derived from your game: same rule |
| logs | `<work>\build.logs`, `<work>\xr\*.log` | may contain paths of your PC and function addresses; review before sharing |

The work folder is therefore **outside** this repository (the repository's `.gitignore` also ignores `/work/`, but do not rely
on that). `docs/LOCAL_OUTPUTS.md` states the policy for every tool.

## 1. What you need

| Item | Version used for the reference build | Notes |
|---|---|---|
| Windows | 10 or 11, x64 | tested: Windows 11 |
| Python | 3.8 or later for the build scripts (stdlib only); the reference run used 3.14 | any `python.exe`; give its path |
| Python with `capstone` | the pip package `capstone==5.0.9` (its module reports `5.0.7`, which `regen.py` checks) | for upstream's recompiler only, e.g. `python -m venv C:\bm\venv` then `C:\bm\venv\Scripts\python.exe -m pip install capstone==5.0.9` |
| Git | any recent Git for Windows | `git.exe` path; used for `archive` / `rev-parse` only |
| your own copy of **Burnout 3: Takedown, North America (NTSC-U) retail** for the original Xbox | `default.xbe` sha256 `9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9` | no other version, region or patched file is supported; `regen.py` refuses it |
| llvm-mingw | 20260922, UCRT, x86_64 (clang 23.1.2) | `llvm-mingw-20260922-ucrt-x86_64.zip` sha256 `e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666` |
| CMake | 4.4.4 | `cmake-4.4.4-windows-x86_64.zip` sha256 `bace36e94b31c68ab6fa295f26dfa11219e0701cf7c94b0284a7d1cb13dac536` |
| Ninja | 1.13.2 | `ninja-win.zip` sha256 `07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65` |
| SDL2 (mingw devel package) | 2.32.10 | `SDL2-devel-2.32.10-mingw.tar.gz` sha256 `83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2` |
| glslang | 16.6.0, built static for mingw (no optimizer, no binaries) | source `16.6.0.tar.gz` sha256 `9c09b901149c729df745057dafa815278aaa101b84d2b6e14f16a42de52f97f2` |
| Vulkan-Headers | vulkan-sdk-1.4.363.0 + a generated `libvulkan-1.dll.a` import library | source tarball sha256 `4a078be12bef21cfebc09d878b77a63cff9d68f899254a0b00d0e37ef73e7f7e` |
| a GPU driver with Vulkan | `vulkan-1.dll` comes with the driver | needed to run, not to build |

Disk: about 1 GB for the toolchain, about 0.5 GB for one work folder (reference run: 410 MB). Time (reference PC, 8 cores): the recompiler about 2 minutes, the build about 40 seconds.

**The dependency folder (`deps`).** The build wants one folder with `llvm-mingw\`, `SDL2\` (the unpacked devel package, containing
`x86_64-w64-mingw32\`), `glslang\` (its install prefix: `include\`, `lib\`) and `vulkan\` (`include\` + `lib\libvulkan-1.dll.a`).
Two ways to make it:

- *Scripted (upstream's own recipe).* After step 2 below, open Git Bash and run, with `cmake` and `ninja` on its PATH:
  `BO3_WINDEPS=/c/bm/deps bash /c/bm/work/takedawn/tools/win/fetch-deps.sh`. It downloads exactly the versions above and builds
  glslang and the import library. Then check the downloads against the sha256 values in the table (`Get-FileHash`).
- *By hand.* Download each file from its upstream release page, compare the sha256 in the table, unpack, and build glslang with
  `-DCMAKE_TOOLCHAIN_FILE=<takedawn>/cmake/llvm-mingw-x86_64.cmake -DBUILD_SHARED_LIBS=OFF -DENABLE_OPT=OFF
  -DENABLE_GLSLANG_BINARIES=OFF -DENABLE_CTEST=OFF -DBUILD_EXTERNAL=OFF`; make the import library with llvm-mingw's `dlltool`
  from a `.def` that lists the `vk*` entry points of the headers (the script above shows how).

CMake and Ninja are used by absolute path (`-Cmake`, `-Ninja`); they do not have to be on PATH. Nothing is searched for.

## 2. Folders used in the examples

```
C:\bm\repo          this repository (your clone of the public fork)
C:\bm\work          NEW work folder for one build (does not exist yet); everything below it is local-only
C:\bm\deps          the dependency folder above
C:\bm\cmake\bin\cmake.exe     C:\bm\ninja\ninja.exe     C:\bm\git\cmd\git.exe
C:\bm\venv\Scripts\python.exe the Python with capstone
D:\game\Burnout 3 Takedown\default.xbe       your own copy
```
Use a **new** work folder for every build; the scripts refuse to write into existing result folders. A path with spaces is fine
for this repository, the tools, the xboxrecomp folder and the build folder (the proof build used a repository path with
spaces), but **the work folder, which holds `takedawn`, must not contain spaces**: the tree's CMake splits the generated-code
force-include list at spaces, and `build.ps1` refuses such a path. Pass `-BuildDir` explicitly if you want the build elsewhere.

All commands are PowerShell. `py -3 -B` and `python -B` are interchangeable; `-B` keeps `__pycache__` out of the tree.

## 3. The steps

**Check the checkout first.** The layers are hashed as bytes. This repository carries a `.gitattributes` (`* -text`) so that git does
not convert line ends; keep it. If the scripts say a file "is not the published one" or "contains carriage returns", your clone
converted line ends (`git config core.autocrlf` in *that clone* is `true` and `.gitattributes` was not honoured): re-clone with
`git clone -c core.autocrlf=false <url>`.

```powershell
cd C:\bm\repo
$py = 'C:\Python314\python.exe'          # any Python 3.8+
```

**Step 1 - fetch upstream at the pinned commits** (`host/PINS.json`): Takedawn `4f074e211822` and xboxrecomp `e3756d1b2fef`.
Give a git URL or a local clone for each (a URL is cloned bare into the work folder and removed again; a local clone is only
read with `rev-parse` and `archive`).
```powershell
& $py -B build\fetch_upstream.py --git C:\bm\git\cmd\git.exe --work C:\bm\work `
    --takedawn https://github.com/xenophobentx/takedawn --xboxrecomp https://github.com/xenophobentx/xboxrecomp
```
It checks that the commit exists, that its tree id is the pinned one (`26cdbea6f8c4`, `480d8993bb58`), and that the extracted
files (count and one digest over all path+hash pairs) equal the pinned archive. The line-end mode is passed to git explicitly
(`-c core.autocrlf=false` for Takedawn, `true` for xboxrecomp, as pinned); your global git configuration cannot change the bytes
and is not changed. Result: `C:\bm\work\takedawn`, `C:\bm\work\xboxrecomp`.

**Step 2 - apply the host layers** (strict, all or nothing).
```powershell
& $py -B build\apply_layers.py host --takedawn C:\bm\work\takedawn --xboxrecomp C:\bm\work\xboxrecomp
```
`host/tree/**` is added to Takedawn; `host/tree.patch` modifies 16 Takedawn files; `host/toolkit/toolkit.patch` and
`host/toolkit/lgpl/apu_core.patch` modify 13 xboxrecomp files (the LGPL file has its own patch). A hunk applies only if its old
block occurs **exactly once** in the file; a missing block, an ambiguous block, a pre-image that is not the pinned base, a file
that already exists, an edited layer file or a result that is not the pinned result is a refusal (exit 2) and nothing is written.

**Step 3 - regenerate the game code from YOUR executable.**
```powershell
& $py -B build\regen.py --takedawn C:\bm\work\takedawn --xboxrecomp C:\bm\work\xboxrecomp `
    --xbe 'D:\game\Burnout 3 Takedown\default.xbe' --python C:\bm\venv\Scripts\python.exe --work C:\bm\work
```
This runs upstream's recompiler (the five steps of its `regen.sh`: `xbe_parser`, `disasm`, `func_id`, `abi_analysis`, `recomp`,
with the guest patches of `config/patches.json` and the spin-wait list on) on your executable. It must run **after** step 2
(the Mashup layer changes `config/patches.json`, an input of the recompiler). The executable is only read. The output is
`C:\bm\work\gen_pristine`; the script then checks the generated tree hash (`5f8203841651...`, from `host/PINS.json`), the
recompiler's patch report (117 of 117 sites) and the number of spin waits, and refuses (deleting the output) if anything
differs: another `default.xbe` build, another recompiler or capstone version.

**Step 4 - apply the hook marks.**
```powershell
& $py -B build\apply_marks.py --takedawn C:\bm\work\takedawn --pristine C:\bm\work\gen_pristine
```
`host/marks/anchors.json` ("bm-anchors 1") stores each mark as the guest address of a nearby label or function plus the sha256 of
the generated lines it sits between or replaces, and the Mashup text to insert; no generated text is in the repository. The
marks are applied to **your** pristine files by `host/marks/tools/anchors.py` with exact-anchor refusal: a missing or duplicate
landmark, a changed span, a different deleted or neighbouring line, or a result that is not the pinned sha256 stops everything
(exit 2, nothing written). Marks are never relocated approximately. On success the 29 marked files and `regen.stamp` are written
into `takedawn\src\game\recomp\gen` and `bm_gen_access.h` into `takedawn\src\game`. This edits your locally generated code on
your PC only; the result is a local build input.

**Step 5 - build** into a new folder.
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 `
    -Takedawn C:\bm\work\takedawn -Xboxrecomp C:\bm\work\xboxrecomp -Deps C:\bm\deps `
    -Cmake C:\bm\cmake\bin\cmake.exe -Ninja C:\bm\ninja\ninja.exe -BuildDir C:\bm\work\build
```
Configuration: Release, Ninja, 256 MB guest window, `BO3_REPRODUCIBLE=ON` (path prefix maps for `__FILE__` and debug info, a
fixed `SOURCE_DATE_EPOCH`, no PE time stamp), `BMASHUP_IDENTITY=ON` (own application name and folder, no update check against
upstream), and the 36 generated-code hook headers of `build/EXPECTED.json` plus `bm_gen_access.h` force-included in that exact
order (the order is part of the build identity). The script first compares the versions of cmake, ninja, clang and SDL2 with the
pins and refuses on a difference (`-AllowOtherToolchain` builds anyway; the exe will then differ from the reference). A
`SOURCE_DATE_EPOCH` in your environment is ignored. Result: `C:\bm\work\build\bin\burnout3.exe`, a staged folder
`C:\bm\work\build\stage\` (`BurnoutMashup.exe`, `SDL2.dll`, `shaders\upscale`, `licenses\`) and logs in `C:\bm\work\build.logs\`.
Release profile: run step 4 as `apply_marks.py ... --release` (the stamp then names the marked tree, which `BO3_RELEASE` requires) and step
5 with `-Release`: the result is `C:\bm\work\build\bin\BurnoutMashup.exe` (`BO3_RELEASE=ON`, `BO3_GLYPHS=OFF` as in the development build).

**Step 6 - verify.**
```powershell
& $py -B build\verify.py --build-dir C:\bm\work\build
```
Exit 0 means: all 27 generated-code objects have the sha256 recorded in `build/EXPECTED.json`, and `burnout3.exe` is
**byte-identical** to the reference build (sha256 in `EXPECTED.json`). The first holds for any compiler that compiles the same
text the same way; the second only with the pinned toolchain and inputs. If it fails, the report names what differs (build
identity string, toolchain versions, objects). The executable contains a build identity `bmp-<version>+<12 hex>` that is a digest
of every source file that was built, so any different input (another upstream revision, edited layer, other line ends, other
`default.xbe`-derived code) changes it. Hashes of objects are not game data. Release profile: `verify.py --build-dir ... --profile
release` checks `bin\BurnoutMashup.exe` against `build_release` (without `--profile` the build folder decides). Reference hashes:
development `burnout3.exe` `cae5f5ff4d85...` (identity `bmp-0.1.9+6f17b9e08be3`), release `BurnoutMashup.exe` `96a9612800bd...`
(identity `bmp-0.1.9+73d8b45b4380`); both rebuilt from clean checkouts in different folders with identical results.

**Step 7 - write `HOST_INFO.json` (the host describes itself).** The launcher's compatibility gate and the Workbench check a mod
against the host you built, and they read that description from `HOST_INFO.json`. It is made from your build only:
```powershell
& $py -B build\verify.py --build-dir C:\bm\work\build --host-info C:\bm\work\build\stage\HOST_INFO.json
```
(or `& $py -B build\host_info.py --build-dir C:\bm\work\build`, which runs the same checks of step 6 first; `--out FILE` chooses the
file, default `<build>\stage\HOST_INFO.json`). `host_info.py` writes the sha256 and size of the built exe, the build identity read
**from the exe's bytes** (the host is not started, not even with `--version`), the platform version, the services and the `mod.toml`
tables with the newest version each reader takes (from `src/game/bm_platform_table.h` of the tree that was built), the plugin api,
the upstream pins, the toolchain, and for every field the source it came from. It **refuses** (exit 2, no file) when the exe or the
build records are missing, when step 6 fails, when the identity inside the exe differs from the build's own record, or when the
source tree on disk is no longer the one the identity was taken over (the digest is recomputed with the rule of
`cmake/bo3_source_id.cmake`). Nothing is typed in or guessed; a changed or unbuilt tree gives no file. Place the file where the
tool that needs it looks: next to the exe of the launcher bundle (`host-local\`) and, for the Workbench, in the root of the kit folder
(this repository; ignored by git) - Build Mashup's install step does both, atomically. `build\host_info.py --check HOST_INFO.json --exe EXE` re-checks an existing file against its exe.

**Before a build exists.** The launcher and the Workbench start without `HOST_INFO.json` and offer everything that does not need a
host: the launcher lists and imports mods and shows the setup state; the Workbench makes projects from the templates, edits tuning
values with the catalogue and validates a project without the host check. What needs a host says `needs a built host ... Build
Mashup first` (compatibility of a mod with the host, the Workbench's Test step, Play); nothing is assumed in its place.

## 4. Running it

The staged folder is the Mashup host, not a launcher. Put your own game data next to it as for Takedawn (setup / `--install` from
your disc, `--data <folder>`): see `docs/INSTALL.md`, `docs/GAME_DATA.md`. Settings and saves live in `%APPDATA%\BurnoutMashup`
(own folder; an existing Takedawn profile is never touched; `tools/migrate` copies it on request). Mods, plugin approval and the
launcher: `docs/MODDING_GUIDE.md`, `docs/INSTALL.md`. A Vulkan driver is required (`vulkan-1.dll`); never put a `vulkan-1.dll`
beside the exe.

## 5. Troubleshooting

| Message | Cause and fix |
|---|---|
| `fetch_upstream ... tree id ... differs from the pinned` / `extracted files ... differ` | the source is not upstream at that commit (wrong repository, a fork, history rewritten). Use the official repositories (`host/PINS.json`) |
| `commit ... is not the pinned` / `git rev-parse failed` | the clone is shallow or lacks the commit; fetch it (`git fetch --unshallow`) in your own clone, then retry |
| `host/tree is not the published one` / `contains carriage returns` | line ends were converted by your clone; re-clone with `core.autocrlf=false` (section 3) |
| `pre-image sha256 ... differs from the pinned base` | the work folder was already patched (run step 2 once per fresh step-1 folder) or the upstream files differ |
| `MISSING anchor` / `AMBIGUOUS anchor` | a layer hunk does not match exactly once: the layer files or upstream are not the pinned ones |
| `is not the supported retail default.xbe` | not the NTSC-U retail executable, or modified. Only the one in the table is supported |
| `needs capstone 5.0.7` | the Python given to `--python` lacks `capstone==5.0.9` (module version 5.0.7) |
| `the generated code differs from the pinned one` | another recompiler / capstone / `default.xbe` build, or step 2 was skipped before step 3 |
| `PRISTINE` / `MISSING_ANCHOR` / `SPAN` / `CONTEXT` / `DELETE` / `RESULT` from apply_marks | your pristine files are not the pinned ones; regenerate (step 3) in a fresh work folder |
| `toolchain differs from the pins` | install the pinned versions (section 1) or accept a non-reproducible exe with `-AllowOtherToolchain` |
| configure fails `include ... No such file` for a `bo3_*_gen.h` | step 2 was not run on this tree, or the tree was edited |
| `the path of the Takedawn tree must not contain spaces` | use a work folder such as `C:\bm\work` (the repository itself may live in a folder with spaces) |
| `verify` says the exe differs but all generated objects are equal | toolchain or SDL2 / glslang build differs; compare the `why` block |

## 6. What the scripts do not do

They do not download the game, anything of the game, a prebuilt host, or generated code. They do not write to your Takedawn
installation, your Takedawn profile, `%APPDATA%`, or this repository (except the optional `__pycache__` you disabled with `-B`).
They do not change any git configuration. `build/EXPECTED.json` holds pins and hashes only.

## 7. LGPL component: `src/apu/apu_core.c`

One file of the build is licensed under the **GNU Lesser General Public License** and is modified by this fork: `src/apu/apu_core.c`
of xboxrecomp (the audio processor code that xboxrecomp took from xemu; its header says "either version 2 of the License, or (at
your option) any later version"; xboxrecomp distributes it as `LGPL-2.1-or-later`, the terms this tree's hunks follow; the
evidence is in `host/toolkit/lgpl/NOTICE`). This section is about the **source** only.

- **Where the modified source is.** This repository holds the modification, not the whole file: `host/toolkit/lgpl/apu_core.patch`
  (4 hunks; the "MEM256" window, dated 2026-10-28 in the file itself) against the pinned upstream file (xboxrecomp `e3756d1b2fef`,
  blob `45c3334f4e33`). After step 2 above the complete modified file is `C:\bm\work\xboxrecomp\src\apu\apu_core.c`. The licence
  text, the header of the file, the change notice and the blob / sha256 pins of the twelve LGPL-marked files are in
  `host/toolkit/lgpl/NOTICE` and `LICENSES/LGPL-2.1-or-later.txt`.
- **The window define.** The patched file reads `XBOX_CONTIG_WINDOW_MB`: with it absent or equal to 64 the file behaves like
  upstream (the `#else` branch, a 64 MB window). The host layer defines it from the CMake option `BO3_GUEST_WINDOW_MB`
  (`add_compile_definitions(XBOX_CONTIG_WINDOW_MB=${BO3_GUEST_WINDOW_MB})` in `host/tree.patch`); `build/build.ps1` passes
  `-DBO3_GUEST_WINDOW_MB=256`.
- **Rebuilding with a modified copy.** Edit `work\xboxrecomp\src\apu\apu_core.c` (or put another version of the file there), then
  build into a **new** build folder with step 5 (`build\build.ps1 ... -BuildDir C:\bm\work\build2`). Do not run step 2 again on the
  edited work folder: the layer scripts refuse a pre-image that is not the pinned base. Step 6 (`verify.py`) will then report that
  `burnout3.exe` is not byte-identical to the reference (expected: the library source differs); the generated-code objects are
  still checked. Steps 3-4 (regenerating the game code) need your own `default.xbe` in every case.
- **What this section does not cover.** It makes no statement about executables or object code built from these sources; nothing
  of that kind is distributed by this repository (`docs/PUBLIC_STATUS.md`).
