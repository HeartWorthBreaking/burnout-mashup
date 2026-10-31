# Prerequisites (mod kit 0.4.1) - what to install, where it comes from, how the tools find it

Nothing here is bundled with the kit; install what your workflow needs. `py -3 -B tools\bmkit_doctor.py` reports what it finds
(`--for plugins`, `--for tools`, `--for host --host <folder>`), and every tool stops with exit 3 and the fix when something is
missing.

| What | Needed for | Version used for the reference results | Source (verify the sha256 of the download) |
|---|---|---|---|
| Python | every kit tool (stdlib only) | 3.11 or later (3.14.2 used) | python.org |
| llvm-mingw (clang for x86_64-w64-mingw32, UCRT) | building plugins (SDK); `bmpack validate` (compiles the host's readers) | 20260922 (clang 23.1.2): `llvm-mingw-20260922-ucrt-x86_64.zip`, sha256 `e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666` | https://github.com/mstorsjo/llvm-mingw/releases/tag/20260922 |
| CMake | building plugins | 3.20+ (4.4.4: `cmake-4.4.4-windows-x86_64.zip`, sha256 `bace36e94b31c68ab6fa295f26dfa11219e0701cf7c94b0284a7d1cb13dac536`) | https://github.com/Kitware/CMake/releases/tag/v4.4.4 |
| Ninja | building plugins | 1.13.2 (`ninja-win.zip`, sha256 `07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65`) | https://github.com/ninja-build/ninja/releases/tag/v1.13.2 |
| Windows PowerShell 5.1 | `sdk\build.ps1` | (Windows) | - |
| your game data (NTSC-U) | donor-based tools, `bmpack validate`, content examples | see `GAME_DATA.md` | your own disc |
| a host to run mods | trying mods in game | your own build of the host (main21, `burnout3_bmashup.exe` + SDL2.dll 2.32.10 + `shaders\upscale`) | the tester package's `BUILD_HOST.md` |
| GPU driver with Vulkan 1.2+ | running the host | `vulkan-1.dll` in `Windows\System32` comes with the driver | AMD / NVIDIA / Intel |

Unpack each zip into a folder of your choice (no installer needed); `Get-FileHash <zip>` shows its sha256.

## How the tools find them (first match wins; no fixed or developer paths)
| Item | Option | Environment | `bmkit.toml` `[paths]` | Last resort |
|---|---|---|---|---|
| game data | `--game-data DIR` | `BMKIT_GAME_DATA` | `game_data` | (none: exit 3) |
| clang (Python tools) | `--cc FILE` | `BMKIT_CC`, else `BMKIT_LLVM_MINGW` (folder) | `cc`, `llvm_mingw` | `x86_64-w64-mingw32-clang.exe` on PATH |
| SDK build (`build.ps1`) | `-LlvmMingw`, `-CMake`, `-Ninja` (or `-Toolchain` = one folder with all three) | `BMKIT_LLVM_MINGW`, `BMSDK_TOOLCHAIN` | - | PATH |
| bmpack checker cache | `--cache DIR` | `BMPACK_CACHE` | - | `_bmpack_cache` in the current folder |

`bmkit.toml` is optional: `BMKIT_CONFIG=<file>`, else `<kit>\bmkit.toml`; start from `bmkit.example.toml`.

## Exit codes (every kit tool)
0 done / accepted; 1 refused input or failed validation (the reason is printed); 2 usage error; 3 a prerequisite or setting is
missing or wrong (`<tool>: CANNOT RUN: <what and how to fix>`).
