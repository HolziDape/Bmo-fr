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

:: Gespeicherten Python-Pfad aus bmo_python.txt lesen (von SETUP_EINMALIG.bat gesetzt)
set "PYEXE="
if exist "%~dp0..\bmo_python.txt" (
  set /p PYEXE=<"%~dp0..\bmo_python.txt"
)

:: Falls kein gespeicherter Pfad, pythonw aus PATH versuchen
if "%PYEXE%"=="" set "PYEXE=pythonw"

start "" "%PYEXE%" "%~dp0..\bmo_watchdog.py"

echo   [ OK ]  Watchdog laeuft im Hintergrund
echo   [ OK ]  Core + Web werden automatisch gestartet
echo.
echo  ========================================
echo   Core :  http://localhost:6000
echo   Web  :  http://localhost:5000
echo  ========================================
echo.
timeout /t 4 /nobreak >nul
