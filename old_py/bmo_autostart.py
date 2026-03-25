"""
BMO Autostart Setup
====================
Dieses Script richtet den Windows-Autostart für bmo_core.py ein.
Einmal ausführen: python bmo_autostart.py

Danach startet bmo_core.py automatisch beim Windows-Start,
unsichtbar im Hintergrund (kein Konsolenfenster).
"""

import os
import sys
import winreg

def setup_autostart():
    # Pfad zu dieser Datei → bmo_core.py liegt im selben Ordner
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    core_script = os.path.join(script_dir, "bmo_core.py")
    pythonw     = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

    # pythonw.exe nutzen → kein Konsolenfenster
    if not os.path.exists(pythonw):
        pythonw = sys.executable  # Fallback auf python.exe

    if not os.path.exists(core_script):
        print(f"❌ bmo_core.py nicht gefunden in: {script_dir}")
        return

    # Autostart-Befehl
    command = f'"{pythonw}" "{core_script}"'

    # Windows Registry: HKCU\Software\Microsoft\Windows\CurrentVersion\Run
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    entry_name = "BMOCore"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, entry_name, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        print(f"✅ Autostart eingerichtet!")
        print(f"   Eintrag: {entry_name}")
        print(f"   Befehl:  {command}")
        print(f"\n   BMO Core startet ab sofort automatisch beim Windows-Login.")
        print(f"   (Unsichtbar im Hintergrund — kein Konsolenfenster)\n")
    except Exception as e:
        print(f"❌ Fehler beim Einrichten: {e}")

def remove_autostart():
    key_path   = r"Software\Microsoft\Windows\CurrentVersion\Run"
    entry_name = "BMOCore"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, entry_name)
        winreg.CloseKey(key)
        print("✅ Autostart-Eintrag entfernt.")
    except FileNotFoundError:
        print("ℹ️  Kein Autostart-Eintrag vorhanden.")
    except Exception as e:
        print(f"❌ Fehler: {e}")

def check_autostart():
    key_path   = r"Software\Microsoft\Windows\CurrentVersion\Run"
    entry_name = "BMOCore"
    try:
        key   = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, entry_name)
        winreg.CloseKey(key)
        print(f"✅ Autostart aktiv: {value}")
    except FileNotFoundError:
        print("ℹ️  Kein Autostart-Eintrag gefunden.")

if __name__ == "__main__":
    print("\n── BMO Autostart Setup ──────────────────────────────\n")
    print("  [1] Autostart einrichten (empfohlen)")
    print("  [2] Autostart entfernen")
    print("  [3] Status prüfen")
    print()
    choice = input("Wahl (1/2/3): ").strip()

    if choice == "1":
        setup_autostart()
    elif choice == "2":
        remove_autostart()
    elif choice == "3":
        check_autostart()
    else:
        print("Ungültige Eingabe.")
