@echo off
chcp 65001 >nul
color 0B
cls
echo.
echo  ____    __  __    ___
echo ^| __ )  ^|  \/  ^|  / _ \
echo ^|  _ \  ^| ^|\/^| ^| ^| ^| ^| ^|
echo ^| ^|_) ^| ^| ^|  ^| ^| ^| ^|_^| ^|
echo ^|____/  ^|_^|  ^|_^|  \___/
echo.
echo  ========================================
echo   Desktop-GUI wird gestartet...
echo  ========================================
echo.

cd /d "%~dp0"
start "" "D:\python\Thonny\python.exe" "D:\python\scripts\Bmo\bmo_desktop.py"

echo   [ OK ]  BMO Desktop laeuft!
echo.
echo   Sag  "Hey BMO"  um zu starten.
echo.
echo  ========================================
echo.
timeout /t 4 /nobreak >nul
