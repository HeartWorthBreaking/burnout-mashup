@echo off
rem fix-update.cmd - installs the newest Burnout Mashup when Update now fails with "Access denied" (WinError 5) on app\launcher.
rem Put it in the folder that holds Burnout Mashup.exe, close the launcher and the Workbench, and double-click it.
rem It runs the launcher's own signed update steps with the launcher closed. Your game copy, mods, saves and settings are kept.
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "L=%CD%\app\launcher"
set "T=%L%\tools\launcher\bmupdate.py"
set "LOG=%CD%\fix-update.log"
if exist "%T%" goto :found
echo This file is not in the right folder.
echo Move it into the folder that holds "Burnout Mashup.exe" and start it again.
goto :end
:found
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3 -B"
if defined PY goto :python
where python >nul 2>nul
if not errorlevel 1 set "PY=python -B"
if defined PY goto :python
echo Python was not found. Install Python 3.11 or newer from python.org and tick "Add python.exe to PATH".
goto :end
:python
echo Close the Burnout Mashup launcher, the Workbench and the game before going on.
pause
echo.
echo Checking for the newest release ...
%PY% "%T%" check --launcher "%L%" > "%LOG%" 2>&1
if errorlevel 1 goto :failed
findstr /c:"up_to_date" "%LOG%" >nul
if not errorlevel 1 goto :uptodate
echo Downloading ...
%PY% "%T%" download --launcher "%L%" >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
echo Preparing ...
%PY% "%T%" prepare --launcher "%L%" >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
echo Installing ...
%PY% "%T%" install --launcher "%L%" >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
echo.
echo Done. Start "Burnout Mashup.exe". If the launcher asks for it, press Build Mashup (about 3 minutes).
goto :end
:uptodate
echo You already have the newest release. Nothing was changed.
goto :end
:failed
echo.
echo The update did not finish. Your version in use is unchanged. Make sure the launcher, the Workbench and the game are closed, then try again.
echo Details are in fix-update.log beside this file. Please send that file if it keeps failing.
:end
echo.
pause
