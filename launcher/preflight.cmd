@echo off
rem preflight.cmd - runs tools\preflight.py with Python 3 (the "py" launcher from python.org, else "python"). Arguments are passed on.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH="
set "PYTHONHOME="
where py >nul 2>nul
if errorlevel 1 goto :trypython
py -3 -B "%ROOT%tools\preflight.py" %*
goto :done
:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
python -B "%ROOT%tools\preflight.py" %*
goto :done
:nopython
echo preflight.cmd: Python 3 was not found. Install it from https://www.python.org (3.11 or newer; tick "Add python.exe to PATH").
exit /b 9
:done
exit /b %ERRORLEVEL%