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
echo   Verknuepfungen werden erstellt...
echo  ========================================
echo.

set "DIR=%~dp0"

:: Shortcut: BMO Starten (gruen — Shell-Icon 137)
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut('%DIR%BMO Starten.lnk'); $sc.TargetPath='%DIR%_intern\bmo_start.bat'; $sc.WorkingDirectory='%DIR%'; $sc.IconLocation='%SystemRoot%\system32\shell32.dll,137'; $sc.Description='BMO Core und Web starten'; $sc.Save()"

:: Shortcut: BMO Desktop (Monitor-Icon aus imageres.dll)
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut('%DIR%BMO Desktop.lnk'); $sc.TargetPath='%DIR%_intern\bmo_desktop.bat'; $sc.WorkingDirectory='%DIR%'; $sc.IconLocation='%SystemRoot%\system32\imageres.dll,109'; $sc.Description='BMO Desktop-GUI mit Wake-Word starten'; $sc.Save()"

:: Shortcut: BMO Stoppen (rot — Shell-Icon 131)
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut('%DIR%BMO Stoppen.lnk'); $sc.TargetPath='%DIR%_intern\bmo_stop.bat'; $sc.WorkingDirectory='%DIR%'; $sc.IconLocation='%SystemRoot%\system32\shell32.dll,131'; $sc.Description='Alle BMO Prozesse beenden'; $sc.Save()"

:: Shortcut: Firewall Setup (Schild-Icon)
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut('%DIR%BMO Firewall Setup.lnk'); $sc.TargetPath='%DIR%_intern\FIREWALL_SETUP.bat'; $sc.WorkingDirectory='%DIR%'; $sc.IconLocation='%SystemRoot%\system32\imageres.dll,54'; $sc.Description='Firewall-Regeln fuer BMO einrichten (einmalig)'; $sc.Save()"

echo   [ OK ]  4 Verknuepfungen erstellt:
echo.
echo          BMO Starten.lnk
echo          BMO Desktop.lnk
echo          BMO Stoppen.lnk
echo          BMO Firewall Setup.lnk
echo.
echo   Die Bat-Dateien liegen in:  _intern\
echo.
echo  ========================================
echo.
pause
