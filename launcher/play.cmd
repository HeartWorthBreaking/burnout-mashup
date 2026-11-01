@echo off
rem play.cmd - start the Burnout Mashup alpha host with everything kept INSIDE this bundle folder.
rem Settings, saves, logs, mod list, plugin approvals, shader cache and mod progress go to profile\ ; your normal Burnout Mashup
rem folders (%APPDATA%\BurnoutMashup, %LOCALAPPDATA%\BurnoutMashup) are not read or written.
rem   play.cmd                 start the game
rem   play.cmd --print-env     show what would be started, start nothing
rem Which host program starts (tester package 0.4.0):
rem   BMASHUP_HOST=prebuilt    host\burnout3_bmashup.exe       (Option A: the prebuilt host shipped in this package)
rem   BMASHUP_HOST=local       host-local\burnout3_bmashup.exe (Option B: the host YOU built with build-host.cmd)
rem   not set                  host-local\ if it holds a host (your own build wins), else host\
rem Example:  set BMASHUP_HOST=prebuilt  and then  play.cmd
setlocal EnableExtensions DisableDelayedExpansion
set "ROOT=%~dp0"
rem 0.2.0 layout 2 (the Windows package): the game copy and your mods live in <install>\gamedata beside app\ (bmpaths.py)
set "GD=%ROOT%gamedata"
set "MODG=%ROOT%mods\generated"
set "MODU=%ROOT%mods\user"
for %%I in ("%ROOT%..") do set "TREENAME=%%~nxI"
for %%I in ("%ROOT%..\..") do set "INST=%%~fI"
if not "%INST:~-1%"=="\" set "INST=%INST%\"
if /i "%TREENAME%"=="app" if exist "%INST%Burnout Mashup.exe" (
  set "GD=%INST%gamedata"
  set "MODG=%INST%gamedata\mods\generated"
  set "MODU=%INST%gamedata\mods\user"
)
set "SEL=%BMASHUP_HOST%"
set "HOSTDIR="
set "KIND="
if /i "%SEL%"=="prebuilt" (
  set "HOSTDIR=%ROOT%host"
  set "KIND=prebuilt host - Option A - chosen by BMASHUP_HOST"
) else if /i "%SEL%"=="local" (
  set "HOSTDIR=%ROOT%host-local"
  set "KIND=local build - Option B - chosen by BMASHUP_HOST"
) else if not "%SEL%"=="" (
  echo play.cmd: BMASHUP_HOST must be "prebuilt" or "local" ^(it is "%SEL%"^).
  exit /b 2
) else if exist "%ROOT%host-local\BurnoutMashup.exe" (
  set "HOSTDIR=%ROOT%host-local"
  set "KIND=your verified build - Build Mashup - host-local\ holds BurnoutMashup.exe"
) else if exist "%ROOT%host-local\burnout3_bmashup.exe" (
  set "HOSTDIR=%ROOT%host-local"
  set "KIND=local build - Option B - host-local\ holds a host"
) else (
  set "HOSTDIR=%ROOT%host"
  set "KIND=prebuilt host - Option A - host-local\ is empty"
)
set "EXE=%HOSTDIR%\burnout3_bmashup.exe"
rem BUILD MASHUP: the release-named host; it starts only with the HOST_INFO.json and BUILD_RESULT.json of its verified install
if exist "%HOSTDIR%\BurnoutMashup.exe" set "EXE=%HOSTDIR%\BurnoutMashup.exe"
if exist "%HOSTDIR%\BurnoutMashup.exe" if not exist "%HOSTDIR%\HOST_INFO.json" goto :unverified
if exist "%HOSTDIR%\BurnoutMashup.exe" if not exist "%HOSTDIR%\BUILD_RESULT.json" goto :unverified
if not exist "%EXE%" goto :nohost
if not exist "%GD%\.complete" goto :nodata
for %%D in ("%ROOT%profile\Roaming" "%ROOT%profile\Local" "%MODG%" "%MODU%") do (
  if not exist "%%~D" mkdir "%%~D"
)
rem developer / research overrides from the calling shell never reach the game
for /f "delims==" %%V in ('set RECOMP_ 2^>nul') do set "%%V="
for /f "delims==" %%V in ('set BO3_ 2^>nul') do set "%%V="
for /f "delims==" %%V in ('set TAKEDAWN_ 2^>nul') do set "%%V="
for /f "delims==" %%V in ('set BMASHUP_ 2^>nul') do set "%%V="
set "XDG_DATA_HOME="
set "HOME="
set "APPDATA=%ROOT%profile\Roaming"
set "LOCALAPPDATA=%ROOT%profile\Local"
set "BMASHUP_DATA=%GD%"
set "BMASHUP_MODS=%ROOT%mods\demo;%MODG%;%MODU%"
if /i "%~1"=="--print-env" goto :printenv
echo play.cmd: host = %KIND%
cd /d "%HOSTDIR%"
"%EXE%" --data "%GD%" %*
set "RC=%ERRORLEVEL%"
echo play.cmd: the game ended with exit status %RC%. Log: "%APPDATA%\BurnoutMashup\logs\run.log"
if not "%RC%"=="0" echo   For a bug report run:  diag.cmd   ^(docs\BUGS_AND_CONTRIBUTING.md^)
exit /b %RC%

:printenv
echo HOST=%KIND%
echo EXE=%EXE%
echo CWD=%HOSTDIR%
echo APPDATA=%APPDATA%
echo LOCALAPPDATA=%LOCALAPPDATA%
echo BMASHUP_DATA=%BMASHUP_DATA%
echo BMASHUP_MODS=%BMASHUP_MODS%
echo LOG=%APPDATA%\BurnoutMashup\logs\run.log
exit /b 0

:nohost
echo play.cmd: %EXE% is missing.
echo   Prebuilt host: unpack the package again ^(host\ is part of it^). Own build: build-host.cmd ^(BUILD_HOST.md^).
exit /b 2

:unverified
echo play.cmd: %HOSTDIR% holds BurnoutMashup.exe without its HOST_INFO.json / BUILD_RESULT.json: not a verified install.
echo   Run Build Mashup again ^(build-mashup.cmd build --input ^<your game^>^); it installs and verifies the host.
exit /b 2

:nodata
echo play.cmd: no game data in "%GD%" yet.
echo   Run:  prepare.cmd data --copy-from ^<your installed game data folder^>
echo   or:   prepare.cmd data --install-from ^<your disc image or extracted disc folder^>
echo   Then: preflight.cmd     ^(docs\INSTALL.md^)
exit /b 3