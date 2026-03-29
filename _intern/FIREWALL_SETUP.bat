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
echo   Firewall-Regeln fuer BMO einrichten
echo   (einmalig, als Administrator ausfuehren)
echo  ========================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
  echo   [FEHLER]  Bitte als Administrator ausfuehren!
  echo             Rechtsklick ^> "Als Administrator ausfuehren"
  echo.
  pause
  exit /b 1
)

echo   Oeffne Port 6000 (BMO Core / KI-Server)...
netsh advfirewall firewall add rule name="BMO Core (Port 6000)" protocol=TCP dir=in localport=6000 action=allow >nul
echo   [ OK ]

echo   Oeffne Port 5000 (BMO Web-Interface)...
netsh advfirewall firewall add rule name="BMO Web (Port 5000)" protocol=TCP dir=in localport=5000 action=allow >nul
echo   [ OK ]

echo.
echo  ========================================
echo   Fertig! Dein Freund kann sich jetzt
echo   per Tailscale verbinden.
echo  ========================================
echo.
pause
