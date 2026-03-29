@echo off
echo Starte BMO Watchdog...

start "" "D:\python\Thonny\pythonw.exe" "D:\python\scripts\Bmo\bmo_watchdog.py"

echo.
echo BMO Watchdog laeuft im Hintergrund!
echo (startet Core + Web automatisch und haelt sie am Laufen)
echo Core: http://localhost:6000
echo Web:  https://localhost:5000
timeout /t 3 /nobreak >nul
