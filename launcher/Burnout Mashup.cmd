@echo off
rem Burnout Mashup.cmd - opens the Burnout Mashup launcher (setup, mods, play, help). Double-click it, or drop your game
rem folder / disc image / a mod folder or .zip onto it. Needs Python 3.11+ (python.org; tick "Add python.exe to PATH").
setlocal
set "L=%~dp0tools\launcher\bmlauncher.pyw"
where pyw >nul 2>nul && (start "" pyw -3 "%L%" %* & exit /b 0)
where pythonw >nul 2>nul && (start "" pythonw "%L%" %* & exit /b 0)
echo Burnout Mashup needs Python 3.11 or newer: install it from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH"), then double-click "Burnout Mashup.cmd" again.
pause
exit /b 9
