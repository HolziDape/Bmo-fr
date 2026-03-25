@echo off
echo Stoppe BMO...

:: Alle pythonw.exe Prozesse die bmo_ im Pfad haben beenden
wmic process where "name='pythonw.exe' and CommandLine like '%%bmo_%%'" delete >nul 2>&1

:: Fallback: alle pythonw.exe beenden falls obiges nicht klappt
taskkill /f /im pythonw.exe >nul 2>&1

echo BMO gestoppt.
timeout /t 2 /nobreak >nul
