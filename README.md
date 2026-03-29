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
| 👥 Freundes-Modus | Freund kann BMO per Web nutzen (eigener Client) |

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
├── freund/              ← 👥 Freundes-Version (eigener Ordner)
│   ├── bmo_web_freund.py   ← Web-Client für den Freund
│   ├── config.txt          ← IP-Adresse + Spotify eintragen
│   ├── START_WEB.bat       ← Starten (Doppelklick)
│   └── SETUP_EINMALIG.bat  ← Einmalige Installation
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

### Schritt 4 · Modelle ablegen

Die folgenden Dateien sind **nicht im Repo** (zu groß). Manuell in den `models/`-Ordner legen:

| Datei | Beschreibung |
|---|---|
| `models/hey_bmo.onnx` | Wake-Word Modell (selbst trainiert mit openWakeWord) |
| `models/BMO_500e_7000s.pth` | RVC Stimm-Modell |
| `models/BMO.index` | RVC Voice Index |

> ⚠️ Ohne RVC-Modell spricht BMO nicht. Core startet aber trotzdem — er gibt dann Texte ohne Audio zurück.

### Schritt 5 · Starten

**Einfach per Doppelklick:**
```
bmo_start.bat
```

Das startet den Watchdog, der automatisch `bmo_core.py` und `bmo_web.py` im Hintergrund überwacht und bei Absturz neu startet.

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

```python
WEB_PASSWORD = "1505"          # ← Login-Passwort für das Web-Interface
FRIEND_URL   = "http://HIER_FREUND_IP:5000"  # ← Tailscale-IP des Freundes (für F.Scare / F.Screen)
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

Du brauchst **nur den `freund/`-Ordner**. Den Rest musst du nicht installieren.

### Schritt 1 · Voraussetzungen

| Was | Wo |
|---|---|
| Python 3.10 | https://python.org |
| Tailscale | https://tailscale.com *(um den Core deines Freundes zu erreichen)* |

### Schritt 2 · Ordner holen

Entweder das ganze Repo klonen und nur `freund/` benutzen:
```bash
git clone https://github.com/HolziDape/Bmo-fr.git
```
Oder nur den `freund/`-Ordner von deinem Freund bekommen (ZIP, USB, etc.).

### Schritt 3 · config.txt ausfüllen

```
# IP-Adresse deines Freundes (Tailscale-IP)
CORE_IP   = 100.x.x.x
CORE_PORT = 6000

# Spotify (optional — nur wenn du Spotify-Steuerung willst)
SPOTIFY_CLIENT_ID     = HIER_CLIENT_ID_EINTRAGEN
SPOTIFY_CLIENT_SECRET = HIER_CLIENT_SECRET_EINTRAGEN
SPOTIFY_REDIRECT_URI  = http://127.0.0.1:8888/callback
SPOTIFY_PLAYLIST_ID   = HIER_PLAYLIST_ID_EINTRAGEN
```

> 💡 Spotify ist **optional**. Wenn du es nicht einträgst, funktioniert alles außer Spotify.

### Schritt 4 · Abhängigkeiten installieren

**Pflicht:**
```bash
pip install flask flask-cors requests psutil
```

**Spotify** *(optional)*:
```bash
pip install spotipy
```

**Bildschirm-Streaming** *(optional — für Admin-Zugriff auf deinen Screen)*:
```bash
pip install pillow
```

Oder einfach `SETUP_EINMALIG.bat` doppelklicken — das macht alles automatisch.

### Schritt 5 · Starten

```
START_WEB.bat  ← Doppelklick
```

Browser öffnet sich automatisch auf `http://localhost:5000`

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
