@echo off
chcp 65001 >nul
color 0A
cls
echo.
echo  ____    __  __    ___
echo ^| __ )  ^|  \/  ^|  / _ \
echo ^|  _ \  ^| ^|\/^| ^| ^| ^| ^| ^|
echo ^| ^|_) ^| ^| ^|  ^| ^| ^| ^|_^| ^|
echo ^|____/  ^|_^|  ^|_^|  \___/
echo.
echo  ========================================
echo   Core + Web werden gestartet...
echo  ========================================
echo.

start "" "D:\python\Thonny\pythonw.exe" "D:\python\scripts\Bmo\bmo_watchdog.py"

echo   [ OK ]  Watchdog laeuft im Hintergrund
echo   [ OK ]  Core + Web werden automatisch gestartet
echo.
echo  ========================================
echo   Core :  http://localhost:6000
echo   Web  :  http://localhost:5000
echo  ========================================
echo.
timeout /t 4 /nobreak >nul
