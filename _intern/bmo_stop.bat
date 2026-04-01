@echo off
chcp 65001 >nul
color 0C
cls
echo.
echo  ____    __  __    ___
echo ^| __ )  ^|  \/  ^|  / _ \
echo ^|  _ \  ^| ^|\/^| ^| ^| ^| ^| ^|
echo ^| ^|_) ^| ^| ^|  ^| ^| ^| ^|_^| ^|
echo ^|____/  ^|_^|  ^|_^|  \___/
echo.
echo  ========================================
echo   BMO wird gestoppt...
echo  ========================================
echo.

powershell -NoProfile -Command "Get-WmiObject Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*bmo_*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo   [ OK ]  Alle BMO Prozesse beendet.
echo.
echo  ========================================
echo   Tschuess!  o(^-^)o
echo  ========================================
echo.
timeout /t 3 /nobreak >nul
