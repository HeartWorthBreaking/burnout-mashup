@echo off
rem trackbuild 0.2.1 launcher: finds Python 3 (py launcher first, then python.exe on PATH) and runs tb.py next to this file.
setlocal
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -B "%~dp0tb.py" %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if not errorlevel 1 (
  python -B "%~dp0tb.py" %*
  exit /b %errorlevel%
)
echo trackbuild: CANNOT RUN: no Python found (neither the py launcher nor python.exe is on PATH). Install Python 3.11 or later from python.org (tick "Add python.exe to PATH" or keep the py launcher), open a new terminal and run tb.cmd again. 1>&2
exit /b 3
