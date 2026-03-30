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

:: Beim ersten Start Pakete installieren und Python-Pfad speichern
if not exist "%~dp0..\bmo_python.txt" (
    echo   Erster Start - Pakete werden installiert...
    echo   (Dies kann einige Minuten dauern)
    echo.
    python -m pip install flask flask-cors requests psutil feedparser pillow pygame sounddevice soundfile speechrecognition openwakeword spotipy ollama
    echo.
    cd /d "%~dp0"
    python -c "import sys; open('../bmo_python.txt','w').write(sys.executable)"
    echo   [ OK ]  Setup abgeschlossen!
    echo.
)

:: Gespeicherten Python-Pfad laden
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
