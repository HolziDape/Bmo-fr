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
echo   Desktop-Verknuepfungen werden erstellt
echo  ========================================
echo.

set "DIR=%~dp0"
set "PY=D:\python\Thonny\pythonw.exe"

:: Verknuepfung: BMO Starten
powershell -NoProfile -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$sc=$ws.CreateShortcut('%USERPROFILE%\Desktop\BMO Starten.lnk');" ^
  "$sc.TargetPath='%DIR%bmo_start.bat';" ^
  "$sc.WorkingDirectory='%DIR%';" ^
  "$sc.IconLocation='%SystemRoot%\system32\shell32.dll,137';" ^
  "$sc.Description='BMO Core und Web starten';" ^
  "$sc.Save()"

:: Verknuepfung: BMO Desktop
powershell -NoProfile -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$sc=$ws.CreateShortcut('%USERPROFILE%\Desktop\BMO Desktop.lnk');" ^
  "$sc.TargetPath='%DIR%bmo_desktop.bat';" ^
  "$sc.WorkingDirectory='%DIR%';" ^
  "$sc.IconLocation='%SystemRoot%\system32\shell32.dll,15';" ^
  "$sc.Description='BMO Desktop-GUI mit Wake-Word starten';" ^
  "$sc.Save()"

:: Verknuepfung: BMO Stoppen
powershell -NoProfile -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$sc=$ws.CreateShortcut('%USERPROFILE%\Desktop\BMO Stoppen.lnk');" ^
  "$sc.TargetPath='%DIR%bmo_stop.bat';" ^
  "$sc.WorkingDirectory='%DIR%';" ^
  "$sc.IconLocation='%SystemRoot%\system32\shell32.dll,131';" ^
  "$sc.Description='Alle BMO Prozesse beenden';" ^
  "$sc.Save()"

echo   [ OK ]  3 Verknuepfungen auf dem Desktop erstellt:
echo.
echo          BMO Starten   (gruen)
echo          BMO Desktop   (blau)
echo          BMO Stoppen   (rot)
echo.
echo  ========================================
echo.
pause
