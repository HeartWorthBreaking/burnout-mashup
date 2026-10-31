# build.ps1 - bmashup-sdk 0.7.0 (mod kit 0.7.0, portable build script): configure and build every example in one command
# (BUILD.md). Windows x64 only. No developer-workspace default: every tool is given or found on PATH.
#   powershell -NoProfile -File build.ps1 [-BuildDir <dir>] [-LlvmMingw <dir>] [-CMake <cmake.exe>] [-Ninja <ninja.exe>]
#                                         [-Toolchain <dir>] [-Clean]
# -BuildDir   the build folder (default: <sdk>\..\build\bmashup-sdk-0.6.0); outputs in <BuildDir>\out\<mod folder>\
# -LlvmMingw  the llvm-mingw folder (bin\x86_64-w64-mingw32-clang.exe in it); else env BMKIT_LLVM_MINGW; else the clang on PATH
# -CMake      cmake.exe; else cmake on PATH          -Ninja  ninja.exe; else ninja on PATH
# -Toolchain  optional: ONE folder holding the three (cmake\**\cmake.exe, ninja\ninja.exe, llvm-mingw\ or bo3-windeps\llvm-mingw\);
#             also env BMSDK_TOOLCHAIN. Explicit -LlvmMingw / -CMake / -Ninja win over it.
# -Clean      remove -BuildDir first (only a folder this script made: it must hold bmsdk_build.stamp)
# Exit: 0 built; 1 configure / build failed; 3 a prerequisite is missing (the message says what to install and where).
param([string]$BuildDir = '', [string]$LlvmMingw = '', [string]$CMake = '', [string]$Ninja = '', [string]$Toolchain = '',
      [switch]$Clean)
$ErrorActionPreference = 'Stop'
$sdk = $PSScriptRoot
$prereq = 'see the kit''s docs\PREREQUISITES.md'
function Stop-Missing([string]$what) { [Console]::Error.WriteLine("build.ps1: CANNOT RUN: $what ($prereq)"); exit 3 }

if (-not $BuildDir) { $BuildDir = Join-Path (Split-Path $sdk -Parent) 'build\bmashup-sdk-0.6.0' }
if (-not $Toolchain) { $Toolchain = $env:BMSDK_TOOLCHAIN }
if ($Toolchain) {
    if (-not (Test-Path -LiteralPath $Toolchain -PathType Container)) { Stop-Missing "-Toolchain / BMSDK_TOOLCHAIN names $Toolchain, which is not a folder" }
    if (-not $CMake) { $c = Get-ChildItem (Join-Path $Toolchain 'cmake') -Filter cmake.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $CMake = $c.FullName } }
    if (-not $Ninja) { $n = Join-Path $Toolchain 'ninja\ninja.exe'; if (Test-Path $n) { $Ninja = $n } }
    if (-not $LlvmMingw) {
        foreach ($cand in (Join-Path $Toolchain 'llvm-mingw'), (Join-Path $Toolchain 'bo3-windeps\llvm-mingw')) {
            if (Test-Path (Join-Path $cand 'bin\x86_64-w64-mingw32-clang.exe')) { $LlvmMingw = $cand; break }
        }
    }
}
if (-not $LlvmMingw) { $LlvmMingw = $env:BMKIT_LLVM_MINGW }
if (-not $LlvmMingw) {
    $c = Get-Command x86_64-w64-mingw32-clang.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { $LlvmMingw = Split-Path (Split-Path $c.Source -Parent) -Parent }
}
if (-not $LlvmMingw) { Stop-Missing 'no llvm-mingw found: give -LlvmMingw <folder>, set BMKIT_LLVM_MINGW, or put its bin folder on PATH. Get llvm-mingw-20260922-ucrt-x86_64.zip from https://github.com/mstorsjo/llvm-mingw/releases/tag/20260922 (sha256 e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666)' }
if (-not (Test-Path (Join-Path $LlvmMingw 'bin\x86_64-w64-mingw32-clang.exe'))) { Stop-Missing "$LlvmMingw is not an llvm-mingw folder (no bin\x86_64-w64-mingw32-clang.exe)" }
if (-not $CMake) { $c = Get-Command cmake.exe -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $CMake = $c.Source } }
if (-not $CMake -or -not (Test-Path -LiteralPath $CMake)) { Stop-Missing 'no cmake.exe: give -CMake <cmake.exe> or put CMake 3.20+ on PATH (cmake-4.4.4-windows-x86_64.zip from https://github.com/Kitware/CMake/releases/tag/v4.4.4 was used)' }
if (-not $Ninja) { $c = Get-Command ninja.exe -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $Ninja = $c.Source } }
if (-not $Ninja -or -not (Test-Path -LiteralPath $Ninja)) { Stop-Missing 'no ninja.exe: give -Ninja <ninja.exe> or put Ninja on PATH (ninja-win.zip 1.13.2 from https://github.com/ninja-build/ninja/releases/tag/v1.13.2 was used)' }

if ($Clean -and (Test-Path $BuildDir)) {
    if (-not (Test-Path (Join-Path $BuildDir 'bmsdk_build.stamp'))) { Stop-Missing "not removing $BuildDir : not made by build.ps1" }
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Force $BuildDir | Out-Null
Set-Content -Encoding ascii (Join-Path $BuildDir 'bmsdk_build.stamp') 'bmashup-sdk 0.7.0 build folder (build.ps1)'
$fwd = { param($p) $p -replace '\\', '/' }
$conf = @('-S', (& $fwd $sdk), '-B', (& $fwd $BuildDir), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
          "-DCMAKE_MAKE_PROGRAM=$(& $fwd $Ninja)", "-DCMAKE_TOOLCHAIN_FILE=$(& $fwd (Join-Path $sdk 'cmake\llvm-mingw-x86_64.cmake'))",
          "-DLLVM_MINGW_ROOT=$(& $fwd $LlvmMingw)")
"llvm-mingw: $LlvmMingw"
"cmake:      $CMake"
"ninja:      $Ninja"
$ErrorActionPreference = 'Continue'      # cmake writes notes to stderr; the exit codes decide
& $CMake @conf
if ($LASTEXITCODE) { [Console]::Error.WriteLine("build.ps1: configure failed ($LASTEXITCODE)"); exit 1 }
& $CMake --build (& $fwd $BuildDir)
if ($LASTEXITCODE) { [Console]::Error.WriteLine("build.ps1: build failed ($LASTEXITCODE)"); exit 1 }
$ErrorActionPreference = 'Stop'
$out = Join-Path $BuildDir 'out'
Get-ChildItem $out -Recurse -File | Where-Object { $_.Extension -in '.asi', '.toml' } | ForEach-Object {
    '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.FullName.Substring($out.Length + 1)
}
"bmashup-sdk 0.7.0: built into $out"
exit 0
