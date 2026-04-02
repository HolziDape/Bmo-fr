@echo off
chcp 65001 >nul
color 0E
cls
echo.
echo  ____    __  __    ___
echo ^| __ )  ^|  \/  ^|  / _ \
echo ^|  _ \  ^| ^|\/^| ^| ^| ^| ^| ^|
echo ^| ^|_) ^| ^| ^|  ^| ^| ^| ^|_^| ^|
echo ^|____/  ^|_^|  ^|_^|  \___/
echo.
echo  ========================================
echo   Einmaliges Setup - Admin-Version
echo  ========================================
echo.
echo   Installiere benoetigte Pakete...
echo   (benutzt Python das dieses Skript ausfuehrt)
echo.

python -m pip install flask flask-cors requests psutil feedparser pillow pygame sounddevice soundfile speechrecognition openwakeword spotipy ollama

echo.
echo  ========================================
echo   Python-Pfad wird gespeichert...
echo  ========================================

:: pythonw.exe speichern — nur schreiben wenn bmo_python.txt noch nicht existiert
if not exist "%~dp0..\bmo_python.txt" (
    python -c "import sys,os; p=sys.executable; pw=os.path.join(os.path.dirname(p),'pythonw.exe'); open('../bmo_python.txt','w').write(pw if os.path.exists(pw) else p)"
)

echo.
set /p PYEXE=<"%~dp0..\bmo_python.txt"
echo   Python: %PYEXE%
echo.
echo  ========================================
echo   [ OK ]  Setup abgeschlossen!
echo.
echo   Naechster Schritt:
echo   Doppelklick auf "BMO Starten"
echo  ========================================
echo.
pause
