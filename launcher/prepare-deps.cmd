@echo off
rem prepare-deps.cmd - runs tools\prepare_deps.py with Python 3 (the "py" launcher from python.org, else "python"). Arguments are passed on.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH="
set "PYTHONHOME="
where py >nul 2>nul
if errorlevel 1 goto :trypython
py -3 -B "%ROOT%tools\prepare_deps.py" %*
goto :done
:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
python -B "%ROOT%tools\prepare_deps.py" %*
goto :done
:nopython
echo prepare-deps.cmd: Python 3 was not found. Install it from https://www.python.org (3.11 or newer; tick "Add python.exe to PATH").
exit /b 9
:done
exit /b %ERRORLEVEL%