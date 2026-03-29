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

:: Python-Pfad in bmo_python.txt speichern damit bmo_start.bat den richtigen nutzt
python -c "import sys; open('../bmo_python.txt','w').write(sys.executable)"

echo.
for /f %%i in ('python -c "import sys; print(sys.executable)"') do echo   Python: %%i
echo.
echo  ========================================
echo   [ OK ]  Setup abgeschlossen!
echo.
echo   Naechster Schritt:
echo   Doppelklick auf "BMO Starten"
echo  ========================================
echo.
pause
