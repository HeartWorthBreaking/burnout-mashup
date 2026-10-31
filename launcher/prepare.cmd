@echo off
rem prepare.cmd - runs tools\prepare.py with Python 3 (the "py" launcher from python.org, else "python"). Arguments are passed on.
rem Drag and drop: started with exactly ONE argument that is an existing path (an Explorer drop of your game folder or a disc image), it runs
rem "prepare.py auto <path>" and pauses at the end so the window stays readable. Typed commands (data / demos / status ...) behave as before.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH="
set "PYTHONHOME="
set "DROP="
set "DROPARG="
if not "%~1"=="" if "%~2"=="" if exist "%~1" set "DROP=1"
if /i "%~1"=="data" set "DROP="
if /i "%~1"=="demos" set "DROP="
if /i "%~1"=="status" set "DROP="
if defined DROP set "DROPARG=%~1"
if defined DROP if exist "%~1\." set "DROPARG=%~1\."
where py >nul 2>nul
if errorlevel 1 goto :trypython
if defined DROP goto :pydrop
py -3 -B "%ROOT%tools\prepare.py" %*
goto :done
:pydrop
py -3 -B "%ROOT%tools\prepare.py" auto "%DROPARG%"
goto :done
:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
if defined DROP goto :pythondrop
python -B "%ROOT%tools\prepare.py" %*
goto :done
:pythondrop
python -B "%ROOT%tools\prepare.py" auto "%DROPARG%"
goto :done
:nopython
echo prepare.cmd: Python 3 was not found. Install it from https://www.python.org (3.11 or newer; tick "Add python.exe to PATH").
if defined DROP pause
exit /b 9
:done
set "RC=%ERRORLEVEL%"
if defined DROP echo.
if defined DROP echo prepare.cmd finished with exit status %RC%. Press any key to close this window.
if defined DROP pause >nul
exit /b %RC%
