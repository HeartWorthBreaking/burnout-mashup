@echo off
rem build-mashup.cmd - BUILD MASHUP from the command line: runs tools\launcher\bmbuild.py with Python 3 (the "py" launcher from python.org,
rem else "python"). The launcher's Build window runs the same program. "build-mashup.cmd help" lists the commands.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH="
set "PYTHONHOME="
where py >nul 2>nul
if errorlevel 1 goto :trypython
py -3 -B "%ROOT%tools\launcher\bmbuild.py" %*
goto :done
:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
python -B "%ROOT%tools\launcher\bmbuild.py" %*
goto :done
:nopython
echo build-mashup.cmd: Python 3 was not found. Install it from https://www.python.org (3.11 or newer; tick "Add python.exe to PATH").
exit /b 9
:done
exit /b %ERRORLEVEL%
