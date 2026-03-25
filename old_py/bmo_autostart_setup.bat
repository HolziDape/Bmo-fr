@echo off
:: ═══════════════════════════════════════════════════════════
:: BMO Autostart Setup (Core + Web, unsichtbar)
:: Einmalig als Administrator ausführen!
:: ═══════════════════════════════════════════════════════════

set PYTHONW=D:\python\Thonny\pythonw.exe
set CORE_SCRIPT=D:\python\scripts\Bmo\bmo_core.py
set WEB_SCRIPT=D:\python\scripts\Bmo\bmo_web.py

echo Richte BMO Core + Web Autostart ein...

:: ── Core ──────────────────────────────────────────────────
schtasks /delete /tn "BMO_Core" /f >nul 2>&1
schtasks /create ^
  /tn "BMO_Core" ^
  /tr "\"%PYTHONW%\" \"%CORE_SCRIPT%\"" ^
  /sc ONLOGON ^
  /rl HIGHEST ^
  /delay 0000:10 ^
  /f

:: ── Web (10 Sekunden nach Core starten) ───────────────────
schtasks /delete /tn "BMO_Web" /f >nul 2>&1
schtasks /create ^
  /tn "BMO_Web" ^
  /tr "\"%PYTHONW%\" \"%WEB_SCRIPT%\"" ^
  /sc ONLOGON ^
  /rl HIGHEST ^
  /delay 0000:20 ^
  /f

if %errorlevel% == 0 (
    echo.
    echo Fertig! Core und Web starten ab jetzt unsichtbar im Hintergrund.
    echo    Core:  http://localhost:6000
    echo    Web:   http://localhost:5000
    echo.
    echo Starte beide jetzt sofort...
    schtasks /run /tn "BMO_Core"
    timeout /t 10 /nobreak >nul
    schtasks /run /tn "BMO_Web"
    echo Beide Tasks gestartet!
) else (
    echo Fehler - als Administrator ausfuehren!
)

pause
