@echo off
color 0C
cls
echo.
echo  ----------------------------------------
echo   BMO wird gestoppt...
echo  ----------------------------------------
echo.

:: Alle pythonw.exe Prozesse die bmo_ im Pfad haben beenden
wmic process where "name='pythonw.exe' and CommandLine like '%%bmo_%%'" delete >nul 2>&1

:: Fallback: alle pythonw.exe beenden falls obiges nicht klappt
taskkill /f /im pythonw.exe >nul 2>&1

echo   [OK]  Alle BMO Prozesse beendet.
echo.
echo  ----------------------------------------
echo   Tschuess!  o(^-^)o
echo  ----------------------------------------
echo.
timeout /t 3 /nobreak >nul
