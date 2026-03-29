@echo off
color 0A
cls
echo.
echo  ██████╗ ███╗   ███╗ ██████╗
echo  ██╔══██╗████╗ ████║██╔═══██╗
echo  ██████╔╝██╔████╔██║██║   ██║
echo  ██╔══██╗██║╚██╔╝██║██║   ██║
echo  ██████╔╝██║ ╚═╝ ██║╚██████╔╝
echo  ╚═════╝ ╚═╝     ╚═╝ ╚═════╝
echo.
echo  ----------------------------------------
echo   Core + Web werden gestartet...
echo  ----------------------------------------
echo.

start "" "D:\python\Thonny\pythonw.exe" "D:\python\scripts\Bmo\bmo_watchdog.py"

echo   [OK]  Watchdog laeuft im Hintergrund
echo   [OK]  Core + Web werden automatisch gestartet
echo.
echo  ----------------------------------------
echo   Core :  http://localhost:6000
echo   Web  :  http://localhost:5000
echo  ----------------------------------------
echo.
timeout /t 4 /nobreak >nul
