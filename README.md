# BMO 🤖

**Lokaler KI-Assistent mit Wake-Word, animiertem Gesicht und RVC-Stimme — komplett offline.**

Inspiriert von BMO aus Adventure Time. Läuft lokal auf Windows — kein Cloud-Zwang, keine API-Kosten.

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| 🎙️ Wake-Word | „Hey BMO" — eigenes trainiertes openWakeWord-Modell |
| 🧠 Lokale KI | Ollama (llama3) — läuft komplett auf deinem PC |
| 🗣️ RVC-Stimme | BMO spricht mit geklonter Stimme (RVC Voice Cloning) |
| 🎮 Desktop-GUI | Animiertes BMO-Gesicht reagiert auf Gespräche (Pygame) |
| 🌐 Web-Interface | Steuerung per Handy oder Browser |
| 🎵 Spotify | Musik abspielen, pausieren, überspringen, Lautstärke |
| ☁️ Wetter & News | Aktuelle Infos auf Anfrage |
| 💻 System-Status | CPU, RAM, Uhrzeit |
| 😱 Jumpscare | Selbsterklärend |
| 👥 Freundes-Modus | Freund kann BMO per Web nutzen → [Bmo_f](https://github.com/HolziDape/Bmo_f) |

---

## 👤 Wer bist du?

> **[→ Ich bin der Admin (Hauptnutzer)](#-installation--admin)**
> Ich betreibe BMO auf meinem PC. Ich will Core, Web-Interface und/oder Desktop-GUI.

> **[→ Ich bin der Freund](#-installation--freund)**
> Mein Freund betreibt BMO. Ich will nur den Freundes-Client installieren.

---

## 📂 Projektstruktur

```
Bmo/
├── bmo_core.py          ← 🧠 KI-Server (Ollama, TTS, Aktionen) — Port 6000
├── bmo_web.py           ← 🌐 Web-Interface für Handy/Browser — Port 5000
├── bmo_desktop.py       ← 🖥️ Desktop-Client (Wake-Word, Mikrofon, GUI)
├── bmo_watchdog.py      ← 🔁 Auto-Neustart wenn etwas abstürzt
├── bmo_start.bat        ← ▶️ Startet alles (Doppelklick)
├── bmo_stop.bat         ← ⏹️ Stoppt alle BMO-Prozesse
│
├── models/
│   ├── hey_bmo.onnx     ← Wake-Word Modell (nicht im Repo — siehe unten)
│   ├── BMO.index        ← RVC Voice Index (nicht im Repo — siehe unten)
│   └── BMO_500e.pth     ← RVC Voice Modell (nicht im Repo — siehe unten)
│
├── assets/
│   ├── faces/           ← BMO Gesichter (PNG)
│   ├── sounds/          ← Sound-Lines
│   └── jumpscare/       ← Jumpscare Bilder
│
└── data/
    └── conversations.json
```

---

## 🚀 Installation — Admin

### Schritt 1 · Voraussetzungen

| Was | Wo |
|---|---|
| Python 3.10 | https://python.org |
| [Ollama](https://ollama.com) | https://ollama.com — nach Installation: `ollama pull llama3` |
| Mikrofon | Für Desktop-GUI und Wake-Word |
| Git | https://git-scm.com *(optional, fürs Klonen)* |

### Schritt 2 · Repo klonen

```bash
git clone https://github.com/HolziDape/Bmo-fr.git
cd Bmo-fr
```

### Schritt 3 · Abhängigkeiten installieren

**Core + Web** (Pflicht):
```bash
pip install flask flask-cors requests psutil feedparser pillow
```

**Desktop-GUI** *(optional — nur wenn du das animierte Fenster willst)*:
```bash
pip install pygame sounddevice soundfile speechrecognition openwakeword
```

**Spotify-Steuerung** *(optional — nur wenn du Spotify nutzen willst)*:
```bash
pip install spotipy
```

> 💡 Alles auf einmal:
> ```bash
> pip install flask flask-cors requests psutil feedparser pillow pygame sounddevice soundfile speechrecognition openwakeword spotipy
> ```

### Schritt 4 · Modelle

Die Modell-Dateien sind bereits im Repo enthalten und werden beim Klonen automatisch mitgeladen:

| Datei | Beschreibung |
|---|---|
| `models/hey_bmo.onnx` | Wake-Word Modell |
| `models/BMO_500e_7000s.pth` | RVC Stimm-Modell |
| `models/BMO.index` | RVC Voice Index |

> ⚠️ Ohne RVC-Modell spricht BMO nicht. Core startet aber trotzdem — er gibt dann Texte ohne Audio zurück.

### Schritt 5 · Starten

| Was | Doppelklick auf |
|---|---|
| Core + Web (Hintergrund, empfohlen) | `bmo_start.bat` |
| Desktop-GUI mit Wake-Word | `bmo_desktop.bat` |

`bmo_start.bat` startet den Watchdog, der Core und Web automatisch überwacht und bei Absturz neu startet.

> 💡 **Erster Start:** Beim allerersten Start öffnet sich automatisch `http://localhost:5000/setup` im Browser — dort kannst du dein Login-Passwort direkt im Web-Interface setzen. Es wird in `bmo_config.txt` gespeichert und danach nie wieder abgefragt.

**Oder manuell:**
```bash
# Terminal 1 — Core (Pflicht, immer zuerst)
python bmo_core.py

# Terminal 2 — Web-Interface (optional)
python bmo_web.py

# Terminal 3 — Desktop-GUI mit Wake-Word (optional)
python bmo_desktop.py
```

### Schritt 6 · Öffnen

| Interface | URL |
|---|---|
| Web lokal | http://localhost:5000 |
| Web per Handy (Heimnetz) | http://\<deine-lokale-ip\>:5000 |
| Web per Handy (überall) | http://\<tailscale-ip\>:5000 *(siehe Tailscale)* |

---

## ⚙️ Konfiguration

### bmo_web.py

Das Passwort wird beim ersten Start über die Setup-Seite im Browser gesetzt (`/setup`) und in `bmo_config.txt` gespeichert.
Willst du es nachträglich ändern, einfach `bmo_config.txt` öffnen und die Zeile anpassen:
```
WEB_PASSWORD=deinNeuesPasswort
```

Die Tailscale-IP des Freundes direkt in `bmo_web.py` eintragen *(nur für F.Scare / F.Screen nötig)*:
```python
FRIEND_URL = "http://HIER_FREUND_IP:5000"
```

### bmo_desktop.py

```python
WAKE_THRESHOLD    = 0.5   # Wake-Word Empfindlichkeit (niedriger = sensibler)
WAKE_VOTES_NEEDED = 2     # Erkennungen am Stück bis Aktivierung
VOICE_VOLUME      = 0.2   # Lautstärke der BMO-Stimme  (0.0–1.0)
SOUNDS_VOLUME     = 0.2   # Lautstärke der Sound-Lines (0.0–1.0)
LISTEN_TIMEOUT    = 4     # Sekunden warten auf Sprache
```

---

## 🌐 Tailscale *(optional — für Zugriff von überall)*

Ohne Tailscale ist BMO nur im Heimnetz erreichbar.
Mit Tailscale kannst du BMO von jedem Gerät weltweit nutzen — auch der Freund kann sich verbinden.

**Einrichten:**
1. [tailscale.com](https://tailscale.com) → kostenloser Account
2. Tailscale auf deinem PC und deinem Handy installieren
3. Beide mit demselben Account verbinden
4. Deine Tailscale-IP findest du mit: `tailscale ip -4`
5. BMO öffnen: `http://<tailscale-ip>:5000`

**Für den Freund:**
- Freund braucht ebenfalls Tailscale (kostenlos)
- Ihr müsst im selben Tailscale-Netzwerk sein (z.B. über „Share node" oder gemeinsamen Account)
- Freund trägt deine Tailscale-IP in seine `config.txt` ein

---

## 🔒 Windows Autostart *(optional)*

Damit BMO beim PC-Start automatisch mitstartet:

**Methode 1 — Startup-Ordner:**
1. `Win + R` → `shell:startup`
2. Neue Datei `bmo.vbs` erstellen:
```vbscript
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw C:\Pfad\zu\Bmo\bmo_watchdog.py", 0, False
```

**Methode 2 — Aufgabenplanung:**
1. `Win + S` → „Aufgabenplanung"
2. Neue einfache Aufgabe → Bei Anmeldung → `bmo_start.bat` ausführen

---

## 🚀 Installation — Freund

Die Freundes-Version ist in einem **eigenen Repo**:

> 👉 **https://github.com/HolziDape/Bmo_f**

Dort gibt es eine eigene Anleitung.

---

## 👥 Admin-zu-Freund Funktionen

Der Admin kann optional auf bestimmte Dinge beim Freund zugreifen — **aber nur wenn der Freund es erlaubt**.

| Funktion | Admin-Button | Freund muss |
|---|---|---|
| 👻 Jumpscare beim Freund | `F.Scare` | 🔒 Admin-Zugriff aktivieren |
| 🖥️ Freund Bildschirm live | `F.Screen` | 🔒 Admin-Zugriff aktivieren |

**So funktioniert es:**
1. Freund öffnet BMO → klickt auf `🔒 Admin`-Button → aktiviert Zugriff
2. Admin sieht `F.Scare` / `F.Screen` Buttons und kann sie nutzen
3. Freund kann Zugriff jederzeit wieder deaktivieren

**Admin-Setup:**
In `bmo_web.py` die Tailscale-IP des Freundes eintragen:
```python
FRIEND_URL = "http://100.x.x.x:5000"   # ← Tailscale-IP des Freundes
```

---

## ⚡ Geschwindigkeit & GPU

BMO läuft komplett lokal — die Antwortgeschwindigkeit hängt stark von deiner Hardware ab.

### Ungefähre Antwortzeiten

| Hardware | Web-Interface | Desktop (nach Wake-Word) |
|---|---|---|
| Moderne NVIDIA GPU (RTX 3000+) | ~3–6 Sek. | ~5–9 Sek. |
| Ältere NVIDIA GPU | ~6–12 Sek. | ~9–16 Sek. |
| AMD GPU | ~10–25 Sek. | ~15–30 Sek. |
| Nur CPU (kein GPU) | ~30–90 Sek. | ~40–120 Sek. |

> ⚠️ **AMD GPU:** Ollama hat aktuell keine native AMD-Unterstützung auf Windows — das Modell läuft auf der CPU, was deutlich langsamer ist. Auf Linux funktioniert AMD GPU (ROCm) besser.

> 💡 **Erste Nachrichten dauern länger:** Beim allerersten Start müssen Ollama (KI) und Whisper (Spracherkennung) ihre Modelle in den Speicher laden. Das kann **30–60 Sekunden extra** dauern. Ab der zweiten Nachricht läuft alles normal.

### Tipps für mehr Geschwindigkeit

- **Schnelleres Modell:** In `bmo_core.py` `OLLAMA_MODEL = "llama3"` auf `"llama3.2:1b"` ändern — deutlich schneller, aber etwas weniger schlau
- **Whisper verkleinern:** `WHISPER_MODEL_SIZE = "small"` auf `"tiny"` ändern — schnellere Spracherkennung, etwas ungenauer
- **RAM:** Mindestens 16 GB empfohlen, 32 GB für flüssigen Betrieb

---

## ❓ Häufige Probleme

**„Core nicht erreichbar"**
→ Ollama läuft nicht. `ollama serve` in einem Terminal starten.

**BMO antwortet aber spricht nicht**
→ RVC-Modell fehlt im `models/`-Ordner. Ohne Modell gibt es keine Stimme.

**Web-Interface lädt nicht**
→ `bmo_core.py` muss vor `bmo_web.py` gestartet sein.

**Freund kann sich nicht verbinden**
→ Tailscale prüfen: Beide müssen online und im selben Netzwerk sein.

**Wake-Word reagiert nicht / zu oft**
→ `WAKE_THRESHOLD` in `bmo_desktop.py` anpassen (höher = strenger).

**`tflite` Fehler beim Start**
→ Ignorieren — openWakeWord fällt automatisch auf `onnxruntime` zurück.

---

## 📄 Lizenz

MIT — Fan-Projekt, nicht offiziell mit Cartoon Network / Adventure Time verbunden.
