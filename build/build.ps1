# build.ps1 - configure and build the Burnout Mashup host from the prepared Takedawn tree (host layers + your generated, marked code).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 `
#       -Takedawn  <work>\takedawn      -Xboxrecomp <work>\xboxrecomp `
#       -Deps      <folder with llvm-mingw\, SDL2\, glslang\, vulkan\>  -Cmake <cmake.exe>  -Ninja <ninja.exe> `
#       -BuildDir  <NEW build folder>   [-LogDir <new folder>] [-Jobs 8] [-AllowOtherToolchain] [-Release]
#
# -Release: the release-named executable bin\BurnoutMashup.exe (BO3_RELEASE=ON with BMASHUP_IDENTITY: window program, Burnout Mashup
# version resource and icon, the first-start display defaults of a packaged program). Needs a tree made with apply_marks.py --release
# (its regen.stamp names the marked tree; the release configuration refuses any other). The button-prompt art for other pads is OFF in
# both profiles (BO3_GLYPHS=OFF here; the development reference build has no SVG renderer either), so no extra tool is needed.
# Without -Release: the development target bin\burnout3.exe, the reference build of EXPECTED.json "build".
#
# Run it after fetch_upstream.py, apply_layers.py host, regen.py and apply_marks.py. The toolchain is NOT searched for: every
# tool is given by path, and its version is checked against build\EXPECTED.json (the reference exe is only reproducible with the
# pinned toolchain; -AllowOtherToolchain builds anyway and says so). The build folder must not exist.
# Fixed configuration (the reference build's): Release, Ninja, the llvm-mingw x86_64 toolchain file of the tree, 256 MB guest window,
# BO3_REPRODUCIBLE=ON (path prefix maps, fixed SOURCE_DATE_EPOCH, no PE time stamp), BMASHUP_IDENTITY=ON, and the generated-code
# hook headers of EXPECTED.json (build.gen_opt_headers) force-included in that exact order, bm_gen_access.h last.
# SOURCE_DATE_EPOCH of your environment is ignored (cleared for this process): the build's own fixed date is used.
# Result: <BuildDir>\bin\burnout3.exe, a staged copy <BuildDir>\stage\BurnoutMashup.exe (+ SDL2.dll, shaders, licenses) and
# <LogDir>\build_result.json. Then run verify.py. Original code (MIT).
param([Parameter(Mandatory = $true)][string]$Takedawn,
      [Parameter(Mandatory = $true)][string]$Xboxrecomp,
      [Parameter(Mandatory = $true)][string]$Deps,
      [Parameter(Mandatory = $true)][string]$Cmake,
      [Parameter(Mandatory = $true)][string]$Ninja,
      [Parameter(Mandatory = $true)][string]$BuildDir,
      [string]$LogDir = '',
      [int]$Jobs = 8,
      [switch]$AllowOtherToolchain,
      [switch]$Release)
$ErrorActionPreference = 'Stop'
function Fail([string]$m) { [Console]::Error.WriteLine("REFUSED: $m"); exit 2 }
function Norm([string]$p) { return ([System.IO.Path]::GetFullPath($p) -replace '\\', '/') }

$exp = Get-Content (Join-Path $PSScriptRoot 'EXPECTED.json') -Raw | ConvertFrom-Json
$W = Norm $Takedawn
$XR = Norm $Xboxrecomp
$D = Norm $Deps
$B = Norm $BuildDir
if (-not $LogDir) { $LogDir = "$B.logs" }
$LogDir = Norm $LogDir
$cmake = Norm $Cmake
$ninja = Norm $Ninja
foreach ($f in @($cmake, $ninja)) { if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { Fail "tool not found: $f" } }
foreach ($dir in @($W, $XR, "$D/llvm-mingw", "$D/SDL2", "$D/glslang", "$D/vulkan")) { if (-not (Test-Path -LiteralPath $dir -PathType Container)) { Fail "folder not found: $dir" } }
if ($W -match '\s') { Fail "the path of the Takedawn tree must not contain spaces ($W): the tree's CMake splits the generated-code force-include list (BO3_GEN_OPT) at spaces. Use a work folder without spaces; the build folder, the xboxrecomp folder and this repository may have spaces." }
if (Test-Path -LiteralPath $B) { Fail "build folder exists: $B (use a new one)" }
if (Test-Path -LiteralPath $LogDir) { Fail "log folder exists: $LogDir" }
if (-not (Test-Path -LiteralPath "$W/src/game/recomp/gen/regen.stamp")) { Fail "no generated code in the tree: run regen.py and apply_marks.py first" }
if (-not (Test-Path -LiteralPath "$W/src/game/bm_gen_access.h")) { Fail "bm_gen_access.h missing: run apply_marks.py first" }
$relStamp = [bool](Select-String -LiteralPath "$W/src/game/recomp/gen/regen.stamp" -Pattern '^pristine [0-9a-f]{64}$' -Quiet)
if ($Release -and -not $relStamp) { Fail "-Release needs a tree made with apply_marks.py --release (its regen.stamp names the marked tree)" }
if (-not $Release -and $relStamp) { Fail "this tree was made with apply_marks.py --release: build it with -Release (or make a fresh tree for the development build)" }

# ---- toolchain versions against the pins (a reproducible exe needs the pinned toolchain)
$ver = [ordered]@{}
$ver.cmake = ((& $cmake --version | Select-Object -First 1) -replace '^cmake version ', '').Trim()
$ver.ninja = ((& $ninja --version | Select-Object -First 1)).Trim()
$ver.clang = (((& "$D/llvm-mingw/bin/clang.exe" --version | Select-Object -First 1)) -replace '^.*clang version ([0-9.]+).*$', '$1').Trim()
$sdl = Get-Content "$D/SDL2/x86_64-w64-mingw32/include/SDL2/SDL_version.h" -Raw
$ver.sdl2 = ('{0}.{1}.{2}' -f ([regex]::Match($sdl, 'define SDL_MAJOR_VERSION\s+(\d+)').Groups[1].Value), ([regex]::Match($sdl, 'define SDL_MINOR_VERSION\s+(\d+)').Groups[1].Value), ([regex]::Match($sdl, 'define SDL_PATCHLEVEL\s+(\d+)').Groups[1].Value))
$bad = @()
foreach ($k in $ver.Keys) { if ($ver[$k] -ne $exp.toolchain.$k) { $bad += "$k $($ver[$k]) (pinned $($exp.toolchain.$k))" } }
if ($bad.Count) {
    if (-not $AllowOtherToolchain) { Fail ("toolchain differs from the pins: " + ($bad -join '; ') + ". Use the pinned versions (docs/BUILDING.md) or -AllowOtherToolchain (the exe will then not match EXPECTED.json).") }
    [Console]::Error.WriteLine("WARNING: other toolchain: " + ($bad -join '; '))
}

# ---- the generated-code force-include list (order is part of the build identity)
$gens = @($exp.build.gen_opt_headers)
foreach ($h in $gens) { if (-not (Test-Path -LiteralPath "$W/src/game/$h")) { Fail "force-include header missing in the tree: src/game/$h" } }
$opt = ($gens | ForEach-Object { "-include $W/src/game/$_" }) -join ' '

New-Item -ItemType Directory -Force $LogDir | Out-Null
$env:SOURCE_DATE_EPOCH = $null
Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue
$env:PATH = ((Norm "$D/llvm-mingw/bin") -replace '/', '\') + ';' + $env:PATH
$cfg = @('-S', $W, '-B', $B, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_MAKE_PROGRAM=$ninja",
    "-DCMAKE_TOOLCHAIN_FILE=$W/cmake/llvm-mingw-x86_64.cmake", "-DLLVM_MINGW_ROOT=$D/llvm-mingw",
    "-DCMAKE_PREFIX_PATH=$D/SDL2/x86_64-w64-mingw32;$D/glslang",
    "-DSDL2_DIR=$D/SDL2/x86_64-w64-mingw32/lib/cmake/SDL2", "-Dglslang_DIR=$D/glslang/lib/cmake/glslang",
    "-DVulkan_INCLUDE_DIR=$D/vulkan/include", "-DVulkan_LIBRARY=$D/vulkan/lib/libvulkan-1.dll.a",
    "-DXBOXRECOMP_DIR=$XR", "-DBO3_COMPILE_JOBS=$Jobs", "-DBO3_BIN_DIR=$B/bin", '-DBO3_GUEST_WINDOW_MB=256',
    '-DBO3_REPRODUCIBLE=ON', '-DBMASHUP_IDENTITY=ON', "-DBO3_GEN_OPT=$opt")
if ($Release) { $cfg += @('-DBO3_RELEASE=ON', '-DBO3_GLYPHS=OFF') }
$t0 = Get-Date
$ErrorActionPreference = 'Continue'
& $cmake @cfg *> "$LogDir/configure.log"
$rc1 = $LASTEXITCODE
if ($rc1) { [Console]::Error.WriteLine("configure failed (rc $rc1), see $LogDir/configure.log"); exit 1 }
& $cmake --build $B --target burnout3 *> "$LogDir/build.log"
$rc2 = $LASTEXITCODE
if ($rc2) { [Console]::Error.WriteLine("build failed (rc $rc2), see $LogDir/build.log"); exit 1 }
$ErrorActionPreference = 'Stop'

$exeName = if ($Release) { 'BurnoutMashup.exe' } else { 'burnout3.exe' }
$exe = "$B/bin/$exeName"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { [Console]::Error.WriteLine("the build made no $exe"); exit 1 }
$h = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLower()
$idm = [regex]::Match((Get-Content "$B/src/game/build_id/bo3_build_id.h" -Raw), 'BO3_BUILD_COMMIT "([^"]+)"')
# ---- stage a runnable folder (exe renamed, SDL2.dll, upscale shaders, licence texts of the inputs)
$st = "$B/stage"
New-Item -ItemType Directory -Force "$st/licenses" | Out-Null
Copy-Item -LiteralPath $exe -Destination "$st/BurnoutMashup.exe"
Copy-Item -LiteralPath "$D/SDL2/x86_64-w64-mingw32/bin/SDL2.dll" -Destination "$st/SDL2.dll"
New-Item -ItemType Directory -Force "$st/shaders" | Out-Null
if (Test-Path -LiteralPath "$XR/third_party/upscale_shaders") { Copy-Item -LiteralPath "$XR/third_party/upscale_shaders" -Destination "$st/shaders/upscale" -Recurse }
foreach ($p in @(@("$W/LICENSE", 'takedawn-LICENSE.txt'), @("$W/THIRD_PARTY_NOTICES.md", 'THIRD_PARTY.txt'), @("$XR/LICENSE", 'xboxrecomp-LICENSE.txt'),
                 @("$XR/NOTICE", 'xboxrecomp-NOTICE.txt'), @("$XR/LICENSES/LGPL-2.1.txt", 'xboxrecomp-LGPL-2.1.txt'),
                 @("$XR/LICENSES/ADPCM-XQ-BSD-3-Clause.txt", 'ADPCM-XQ-BSD-3-Clause.txt'))) {
    if (Test-Path -LiteralPath $p[0]) { Copy-Item -LiteralPath $p[0] -Destination "$st/licenses/$($p[1])" }
}
$res = [ordered]@{ ok = $true; exe = $exe; exe_sha256 = $h; identity = $idm.Groups[1].Value; toolchain = $ver
                   seconds = [int]((Get-Date) - $t0).TotalSeconds; gen_headers = $gens.Count }
if ($Release) { $res.profile = 'release'; $res.exe_name = $exeName }
($res | ConvertTo-Json -Depth 4) | Out-File -Encoding utf8 "$LogDir/build_result.json"
[Console]::Error.WriteLine("built in $($res.seconds) s: $exe")
$res | ConvertTo-Json -Compress -Depth 4
exit 0
