@echo off
echo Starte BMO Desktop (Wake-Word + GUI)...
cd /d "%~dp0"
start "" "D:\python\Thonny\python.exe" "D:\python\scripts\Bmo\bmo_desktop.py"
echo.
echo BMO Desktop laeuft!
echo (Wake-Word aktiv — sag "Hey BMO" um zu starten)
timeout /t 3 /nobreak >nul
