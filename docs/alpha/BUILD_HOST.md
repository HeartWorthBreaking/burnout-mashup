# BUILD_HOST - Option B: build the Burnout Mashup host from source with your own game (tester package 0.4.0)

**You do not have to do this.** Option A is the prebuilt host already in `host\` (see `docs\START_HERE.md` section 0). Do this
only if you prefer not to run the prebuilt exe, want to modify the host (or the LGPL audio library), or want to check that the
source gives the same exe.

**Status: technically verified, NOT legally cleared.** The prebuilt host contains recompiled game code whose redistribution is
an open question (`docs/PUBLIC_STATUS.md` Q1); this route builds the same host on your PC: upstream's recompiler translates YOUR OWN
`default.xbe`. Whether building / owning such a copy is permitted where you live is for you to judge (Q7); nobody has described
this route as legally cleared.

**Where the result goes:** `host-local\` (the prebuilt `host\` is never touched). `play.cmd` starts `host-local\` when it
holds a host, unless `BMASHUP_HOST=prebuilt` is set; `BMASHUP_HOST=local` forces it. `preflight.cmd` names the host in use, and
treats `host-local\BUILD_RESULT.json` (written by `build-host.cmd`) as the record of a documented local build.

## 1. Requirements
| Item | Detail |
|---|---|
| Windows | 10 / 11 x64 (verified: Windows 11 build 26300 only) |
| Your game | retail NTSC-U *Burnout 3: Takedown* (Xbox), extracted disc or installed Takedawn data; `default.xbe` sha256 `9f497acd82adb8edfb72cc31aeeb35010b45d32b13a3f1fc6540717ff24d13f9` |
| Python | 3.11+ from python.org (3.8+ for the build scripts themselves), on PATH as `py` |
| Python for the recompiler | a private venv with `capstone==5.0.9` (the module reports `__version__` 5.0.7; the host source package's BUILDING.md names that number) |
| git | Git for Windows on PATH, or `PortableGit-2.56.0.2-64-bit.7z.exe` (section 2) unpacked with `prepare-deps.cmd --extract-git` |
| Network | to download the archives below and to clone the two upstream repositories (or give local clones) |
| Disk | ~10 GB free: toolchain ~2.5 GB, build work ~3 GB, game data copy 2.5 GB, caches |
| Time | prepare-deps 5-10 min (glslang build), host build 3-6 min (recompile ~2 min + compile), game data copy 1-3 min |

## 2. Downloads (exact pins; put them in ONE folder, e.g. `C:\Downloads\bm-toolchain`)
| File | URL | sha256 |
|---|---|---|
| llvm-mingw-20260922-ucrt-x86_64.zip | https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/llvm-mingw-20260922-ucrt-x86_64.zip | e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666 |
| cmake-4.4.4-windows-x86_64.zip | https://github.com/Kitware/CMake/releases/download/v4.4.4/cmake-4.4.4-windows-x86_64.zip | bace36e94b31c68ab6fa295f26dfa11219e0701cf7c94b0284a7d1cb13dac536 |
| ninja-win.zip (1.13.2) | https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-win.zip | 07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65 |
| SDL2-devel-2.32.10-mingw.tar.gz | https://github.com/libsdl-org/SDL/releases/download/release-2.32.10/SDL2-devel-2.32.10-mingw.tar.gz | 83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2 |
| glslang-16.6.0.tar.gz | https://github.com/KhronosGroup/glslang/archive/refs/tags/16.6.0.tar.gz | 9c09b901149c729df745057dafa815278aaa101b84d2b6e14f16a42de52f97f2 |
| Vulkan-Headers-vulkan-sdk-1.4.363.0.tar.gz | https://github.com/KhronosGroup/Vulkan-Headers/archive/refs/tags/vulkan-sdk-1.4.363.0.tar.gz | 4a078be12bef21cfebc09d878b77a63cff9d68f899254a0b00d0e37ef73e7f7e |
| PortableGit-2.56.0.2-64-bit.7z.exe (optional) | https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.2/PortableGit-2.56.0.2-64-bit.7z.exe | 075e158ef8e1f0ab80b347e245405d3eca735c2dc88fd8e032e137d0ca61f61b |

Check a download: `Get-FileHash <file>` in PowerShell (or `certutil -hashfile <file> SHA256`). `prepare-deps.cmd` checks all of
them and refuses a wrong file.

## 3. Steps (Command Prompt in this package folder)
```
prepare.cmd data --copy-from "<folder holding Burnout 3 Takedown>"     your game data -> gamedata\ (read only on the source)
prepare-deps.cmd --downloads C:\Downloads\bm-toolchain                 -> build\deps\ (llvm-mingw, cmake, ninja, SDL2, glslang, vulkan)
py -3 -m venv build\deps\pyenv
build\deps\pyenv\Scripts\pip install capstone==5.0.9
build-host.cmd [--git <git.exe>]                                         -> host-local\burnout3_bmashup.exe + SDL2.dll + shaders\ + licenses\
preflight.cmd                                                            must end with RESULT PASS (host in use = your build)
```
- `build-host.cmd` runs `host-source\build_from_source.py` (unchanged host source package): clones upstream Takedawn at
  **4f074e211822eaf43d4a3902c744d5ed0e9c9adf** and xboxrecomp at **e3756d1b2fefdae6888038384c748cbdd37a41ba**, applies our patch
  (`host-source\patches\bmashup-host-main19_final-vs-takedawn-4f074e2.patch`, sha256 `c4bb497ee834c5689475aec1dc07896000fafcfe1f7d589a964b5d49bbd45b6e`),
  regenerates the game code from your `default.xbe` (checks the generated tree `5f8203841651186bc670dc68e36a0d5529b6a2ebab7b35f014494b608bc29ae5`),
  applies the 453 hook marks (`host-source\marks\marks_main19_final.json`, sha256 `1e99f47379b73d4070c5cb15f1c8fd13d866d2993df419a93034661263c2a068`;
  refuses on any hash mismatch), configures + builds, and installs the result into `host-local\` (beside the prebuilt `host\`).
- No network? `--takedawn <local clone> --xboxrecomp <local clone>`. Disc instead of installed data? `--xbe <disc folder>\default.xbe`,
  then `prepare.cmd data --install-from <disc folder or image>` (runs the host's own installer `--install ... --dest`: not
  exercised in the alpha's validation; it may show the host's console / installer output).
- Everything stays inside this folder; nothing is installed system-wide, no registry or PATH change. The build steps are console
  programs; the only window is PortableGit's optional 7-Zip progress window (`--extract-git`).

## 4. Expected results (EXPECTED.json of the source package)
| | value |
|---|---|
| host exe `host-local\burnout3_bmashup.exe` (identical to the prebuilt `host\burnout3_bmashup.exe`) | sha256 **f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656** (reference build main21), 27,380,224 bytes |
| build identity (log line `[PLATFORM] host: Burnout Mashup platform 0.1.9, build ...`) | **bmp-0.1.9+2c8142e65f20** |
| SDL2.dll (from the SDL2 devel package) | sha256 53e8fa7e9ed43c30bd650c39396f0d9d2067d2fff0b926c9433b75202592e4aa |
| generated game-code tree (your recompile, before the marks) | 5f8203841651186bc670dc68e36a0d5529b6a2ebab7b35f014494b608bc29ae5 |

`build-host.cmd` exits 0 only when the exe equals the reference; 2 = built but different (unsupported; check the pins); 3 = a step
failed (log `build\work-<n>\build_from_source.log`). Your glslang libraries will differ from ours in their object time stamps only;
the linker ignores those, so the exe is still byte-identical (verified).

## 5. Licences of what you build
Upstream Takedawn and xboxrecomp: MIT. xboxrecomp contains LGPL-2.1-or-later code (the MCPX APU audio, from xemu), statically
linked into your build; you build it from source yourself, so you can change and rebuild it at any time (this package's `lgpl-kit\`
also carries that library's source as built, its compile script and the relink scripts). **Q2 (whether this route satisfies the LGPL for a
binary hand-over) is still open.** SDL2: zlib; glslang: BSD-3-Clause and others; LLVM runtime: Apache-2.0 WITH
LLVM-exception; mingw-w64: its runtime licence; upscale shaders: LGPL-3.0-or-later (sources included under
`host-local\shaders\upscale\upstream`). `build-host.cmd` copies the Takedawn / xboxrecomp licence, NOTICE and LGPL texts into
`host-local\licenses\`; the toolchain licences are inside the archives you downloaded. The Burnout Mashup patch, marks and scripts: our
own work, MIT (`LICENSE`, `REUSE.toml`; `docs/PUBLIC_STATUS.md` Q3).
