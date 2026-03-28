@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: build_luca.bat  —  Packages Luca into a single distributable .exe
::
:: Requirements (run once if not already installed):
::   pip install pyinstaller
::
:: Output:  dist\Luca.exe
:: ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

echo.
echo  Building Luca.exe ...
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "Luca" ^
    --icon "audit_icon.ico" ^
    --add-data "audit_icon.ico;." ^
    --add-data "APPGUIDE.md;." ^
    --hidden-import "tkcalendar" ^
    --hidden-import "babel.numbers" ^
    audit_gui.py

echo.
if exist "dist\Luca.exe" (
    echo  ✓  Build complete:  %~dp0dist\Luca.exe
    echo.
    echo  Copy dist\Luca.exe to any Windows machine — no Python install needed.
) else (
    echo  ✗  Build failed. Check the output above for errors.
)
echo.
pause
