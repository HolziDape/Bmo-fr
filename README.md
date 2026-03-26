# BMO 🤖

**Ein lokaler KI-Assistent mit eigenem Wake-Word, animiertem Gesicht und RVC-Stimme — komplett offline.**

Inspiriert von BMO aus Adventure Time. Läuft komplett lokal auf Windows — kein Cloud-Zwang, keine API-Kosten.

---

## ✨ Features

- 🎙️ **Eigenes Wake-Word** — "Hey BMO" erkennt dich mit einem selbst trainierten openWakeWord-Modell
- 🧠 **Lokale KI** — Ollama läuft auf deinem PC, keine Daten verlassen dein Netzwerk
- 🗣️ **RVC-Stimme** — BMO spricht mit einer geklonten Stimme (RVC Voice Cloning)
- 🎮 **Pygame GUI** — Animiertes BMO-Gesicht reagiert auf Gespräche
- 🌐 **Web-Interface** — Erreichbar per Handy über Tailscale
- 🎵 **Spotify-Steuerung** — Musik abspielen, pausieren, nächsten Track
- ☁️ **Wetter & News** — Aktuelle Infos direkt auf Anfrage
- 💻 **System-Status** — CPU, RAM, Uhrzeit auf Befehl
- 😱 **Jumpscare-Modus** — Selbsterklärend

---

## 🛠️ Voraussetzungen

- Windows 10 / 11
- Python 3.10
- [Ollama](https://ollama.com) (lokal installiert, z. B. `ollama run llama3`)
- Mikrofon

---

## 📂 Projektstruktur

```
Bmo/
├── bmo_core.py          ← Zentraler Server (KI, TTS, Aktionen) — Port 6000
├── bmo_desktop.py       ← Desktop-Client (Wake-Word, Mikrofon, GUI)
├── bmo_web.py           ← Web-Interface für Handy — Port 5000
├── train_wakeword.py    ← Wake-Word Trainer (generiert hey_bmo.onnx)
├── bmo_start.bat        ← Startet Core + Web
├── bmo_stop.bat         ← Stoppt alle BMO-Prozesse
├── models/
│   ├── hey_bmo.onnx     ← Trainiertes Wake-Word Modell
│   ├── BMO.index        ← RVC Voice Index
│   └── BMO_500e.pth     ← RVC Voice Modell
├── assets/
│   ├── faces/           ← BMO Gesichter (PNG)
│   ├── sounds/          ← Vorgenerierte Sound-Lines
│   └── jumpscare/       ← Jumpscare Bilder
├── data/
│   └── conversations.json
└── logs/
```

---

## 🚀 Installation

**1. Repo klonen**
```bash
git clone https://github.com/damjanGP/Bmo-fr.git
cd Bmo-fr
```

**2. Abhängigkeiten installieren**
```bash
pip install flask flask-cors ollama openwakeword speechrecognition pygame sounddevice soundfile psutil feedparser requests
```

**3. Ollama starten und Modell laden**
```bash
ollama pull llama3
```

**4. BMO Core starten** (im Hintergrund, einmalig)
```bash
python bmo_core.py
```

**5. Desktop-Version starten**
```bash
python bmo_desktop.py
```

Oder einfach `bmo_start.bat` doppelklicken.

---

## ⚙️ Konfiguration

In `bmo_desktop.py` oben:

```python
WAKE_WORD_MODEL  = "models/hey_bmo.onnx"  # Pfad zum Wake-Word Modell
VOICE_VOLUME     = 0.2    # Lautstärke der BMO-Stimme  (0.0 – 1.0)
SOUNDS_VOLUME    = 0.2    # Lautstärke der Sound-Lines (0.0 – 1.0)
WAKE_THRESHOLD   = 0.5    # Wake-Word Empfindlichkeit  (höher = strenger)
WAKE_VOTES_NEEDED = 2     # Nötige Erkennungen am Stück (1 = sofort)
```

---

## 🌐 Web-Interface (Handy)

```bash
python bmo_web.py
```

Dann im Browser öffnen: `http://<deine-tailscale-ip>:5000`

---

## Windows Autostart (unsichtbar)

Damit `bmo_core.py` beim Login automatisch startet:

1. `Win + R` → `shell:startup`
2. Neue Datei `bmo_core.vbs` erstellen:
```vbscript
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw C:\Pfad\zu\bmo_core.py", 0, False
```

---

## ⚠️ Hinweise

- **Ollama muss laufen** bevor `bmo_desktop.py` oder `bmo_web.py` gestartet werden
- **tflite** ist nicht nötig — openWakeWord fällt automatisch auf onnxruntime zurück
- Das RVC-Modell ist nicht im Repo enthalten (zu groß) — eigenes Modell in `models/` ablegen

---

## 📄 Lizenz

MIT — Fan-Projekt, nicht offiziell mit Cartoon Network / Adventure Time verbunden.
