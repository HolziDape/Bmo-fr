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
echo   Einmaliges Setup - Freund-Version
echo  ========================================
echo.
echo   Installiere benoetigte Pakete...
echo.

pip install flask flask-cors requests psutil spotipy pillow

echo.
echo  ========================================
echo   [ OK ]  Setup abgeschlossen!
echo.
echo   Naechster Schritt:
echo   1. config.txt ausfuellen (IP eintragen)
echo   2. START_WEB.bat starten
echo  ========================================
echo.
pause
