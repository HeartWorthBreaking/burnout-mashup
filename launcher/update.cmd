@echo off
rem update.cmd - "Check for updates" from the command line: runs tools\launcher\bmupdate.py with Python 3 (the "py" launcher from
rem python.org, else "python"). Nothing runs by itself: each command is one step you choose. "update.cmd help" lists them.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH="
set "PYTHONHOME="
where py >nul 2>nul
if errorlevel 1 goto :trypython
py -3 -B "%ROOT%tools\launcher\bmupdate.py" %*
goto :done
:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
python -B "%ROOT%tools\launcher\bmupdate.py" %*
goto :done
:nopython
echo update.cmd: Python 3 was not found. Install it from https://www.python.org (3.11 or newer; tick "Add python.exe to PATH").
exit /b 9
:done
exit /b %ERRORLEVEL%
