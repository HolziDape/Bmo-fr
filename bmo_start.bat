@echo off
echo Starte BMO Core + Web...

start "" "D:\python\Thonny\pythonw.exe" "D:\python\scripts\Bmo\bmo_core.py"
echo Core gestartet.

timeout /t 10 /nobreak >nul

start "" "D:\python\Thonny\pythonw.exe" "D:\python\scripts\Bmo\bmo_web.py"
echo Web gestartet.

echo.
echo BMO laeuft im Hintergrund!
echo Core: http://localhost:6000
echo Web:  http://localhost:5000
timeout /t 3 /nobreak >nul
