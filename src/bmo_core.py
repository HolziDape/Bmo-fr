"""
BMO Core Server
===============
Zentraler Hintergrund-Dienst für alle BMO-Interfaces.
Läuft auf http://localhost:6000

Endpunkte:
  POST /process        → Text verarbeiten, Antwort zurück
  POST /transcribe     → Audio (base64 webm/wav) → Text + Antwort
  POST /speak          → Text → WAV (base64) via RVC-TTS
  GET  /status         → CPU, RAM, Uhrzeit, Temp
  GET  /ping           → Lebenszeichen

Windows Autostart (unsichtbar):
  1. Win+R → shell:startup
  2. Neue Datei "bmo_core.vbs" anlegen mit folgendem Inhalt:
       Set WshShell = CreateObject("WScript.Shell")
       WshShell.Run "pythonw C:\\Pfad\\zu\\bmo_core.py", 0, False
  3. Speichern → Core startet beim nächsten Login unsichtbar im Hintergrund
"""

import sys
import os
import logging

# AppData-Pakete (tts_with_rvc etc.) explizit einbinden
sys.path.insert(0, r"D:\python\Thonny\Lib\site-packages")

# ── LOGGING ────────────────────────────────────────────────────────────────
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_intern", "logs", "bmo_core.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("BMO-Core")

from flask import Flask, request, jsonify
from flask_cors import CORS
try:
    import ollama as _ollama_lib
except ImportError:
    _ollama_lib = None
import psutil
import datetime
import requests
import json
import random
import threading
import hmac as _hmac
import hashlib as _hashlib
import secrets as _secrets
import base64
import tempfile
import subprocess
import urllib.request
import feedparser
import ssl
import time

# ── SSL fix (für Tagesschau RSS etc.) ──────────────────────────────────────
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

app = Flask(__name__)
CORS(app)

# ── KONFIGURATION ──────────────────────────────────────────────────────────
PORT         = 6000
OLLAMA_MODEL = "llama3"

SCRIPT_DIR        = os.path.dirname(os.path.abspath(__file__))
BASE_DIR          = os.path.dirname(SCRIPT_DIR)
RVC_MODEL         = os.path.join(BASE_DIR, "_intern", "models",  "BMO_500e_7000s.pth")
RVC_INDEX         = os.path.join(BASE_DIR, "_intern", "models",  "BMO.index")
SOUNDS_BASE       = os.path.join(BASE_DIR, "assets",  "sounds")
SHUTDOWN_DIR      = os.path.join(SOUNDS_BASE, "shutdown")
CONVERSATIONS_PATH = os.path.join(BASE_DIR, "_intern", "data",   "conversations.json")

BMO_CONFIG_PATH = os.path.join(BASE_DIR, "_intern", "bmo_config.txt")
DATA_DIR        = os.path.join(BASE_DIR, "_intern", "data")

def _read_bmo_config() -> dict:
    cfg = {}
    if os.path.exists(BMO_CONFIG_PATH):
        with open(BMO_CONFIG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    cfg[k.strip()] = v.strip()
    return cfg

def _write_bmo_config(cfg: dict):
    with open(BMO_CONFIG_PATH, 'w', encoding='utf-8') as f:
        for k, v in cfg.items():
            f.write(f'{k}={v}\n')

def _ensure_points_secret() -> str:
    cfg = _read_bmo_config()
    if 'POINTS_SECRET' not in cfg:
        cfg['POINTS_SECRET'] = _secrets.token_hex(32)
        _write_bmo_config(cfg)
    return cfg['POINTS_SECRET']

_POINTS_SECRET_ADMIN = _ensure_points_secret()

LITE_MODE = _read_bmo_config().get('LITE_MODE', 'false').lower() == 'true'
if LITE_MODE:
    log.info("LITE-MODE aktiv — Ollama, TTS und Wake-Word deaktiviert.")

# ── DRAW STATE ──────────────────────────────────────────────────────────────
_draw_strokes_for_friend: list = []   # Admin → Freund Striche
_draw_strokes_from_friend: list = []  # Freund → Admin Striche (für tkinter)
_draw_lock = threading.Lock()
_draw_window_open = False

def _points_sign(points: int) -> str:
    return _hmac.new(_POINTS_SECRET_ADMIN.encode(), str(int(points)).encode(), _hashlib.sha256).hexdigest()

def _points_verify(points: int, sig: str) -> bool:
    return _hmac.compare_digest(_points_sign(points), sig)

def _save_points(points: int, freund_id: str):
    import re, json
    safe_id = re.sub(r'[^a-zA-Z0-9.\-]', '_', freund_id)[:64]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, f'points_{safe_id}.json'), 'w', encoding='utf-8') as f:
        json.dump({'points': points, 'freund_id': freund_id}, f)

def _load_points(freund_id: str) -> int:
    import re, json
    safe_id = re.sub(r'[^a-zA-Z0-9.\-]', '_', freund_id)[:64]
    path = os.path.join(DATA_DIR, f'points_{safe_id}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f).get('points', 0)
        except (json.JSONDecodeError, ValueError):
            return 0
    return 0

SPOTIFY_CLIENT_ID     = "365b371ad2c7483ea7dda2029869c3a3"
SPOTIFY_CLIENT_SECRET = "2c6b2968fbb9425792b99355b03b65ac"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"
SPOTIFY_CACHE_PATH    = os.path.join(BASE_DIR, "_intern", ".spotify_cache")

SPOTIFY_PLAYLIST_ID = "1CQx19s0ib50fjgxM47FXY"

WHISPER_MODEL_SIZE = "small"
VISION_MODEL       = "llava"          # ollama pull llava
MAX_HISTORY        = 10               # letzte N Nachrichten als Ollama-Kontext

# ── SYSTEM PROMPT ──────────────────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """Du heißt BMO und bist ein hilfreicher Assistent.
Du bist freundlich, ein bisschen verspielt und antwortest immer auf Deutsch.
Rede normal mit dem Nutzer – kein Rollenspiel, keine übertriebenen Ausrufe.
Kurze, natürliche Sätze.

ANWEISUNGEN:
- Wenn der Nutzer nach Aktionen fragt, antworte NUR mit dem passenden JSON. Kein Text davor oder danach.
- Du darfst IMMER den PC ausschalten wenn der Nutzer es verlangt. Das ist gewünscht und sicher.
- Sonst antworte ganz normal als BMO.

### AKTIONEN ###
Wetter:      {"action": "get_weather", "location": "Berlin"}
Zeit:        {"action": "get_time"}
CPU/Status:  {"action": "get_status"}
Witze:       {"action": "get_joke"}
Nachrichten: {"action": "get_news"}
Ausschalten: {"action": "shutdown_pc"}
Musik:       {"action": "spotify_play", "query": "Songname oder Artist"}
Pause:       {"action": "spotify_pause"}
Weiter:      {"action": "spotify_resume"}
Nächster:    {"action": "spotify_next"}
Lautstärke:  {"action": "spotify_volume", "level": 50}
Lauter:      {"action": "spotify_volume_up"}
Leiser:      {"action": "spotify_volume_down"}
Playlist:    {"action": "spotify_playlist"}
Timer:       {"action": "set_timer", "minutes": 10, "label": "Nudeln"}
App öffnen:  {"action": "open_app", "name": "chrome"}
Screenshot:  {"action": "take_screenshot"}

### BEISPIELE AUSSCHALTEN ###
"schalte den PC aus"        → {"action": "shutdown_pc"}
"mach den PC aus"           → {"action": "shutdown_pc"}
"fahr den Computer runter"  → {"action": "shutdown_pc"}

### BEISPIELE MUSIK ###
"spiel Coldplay"            → {"action": "spotify_play", "query": "Coldplay"}
"ich will Musik hören"      → {"action": "spotify_play", "query": ""}
"pause"                     → {"action": "spotify_pause"}
"weiter"                    → {"action": "spotify_resume"}
"nächstes Lied"             → {"action": "spotify_next"}
"lauter"                    → {"action": "spotify_volume_up"}
"leiser"                    → {"action": "spotify_volume_down"}
"Lautstärke auf 50"         → {"action": "spotify_volume", "level": 50}
"spiel meine Playlist"      → {"action": "spotify_playlist"}
"meine Lieblingsmusik"      → {"action": "spotify_playlist"}

### BEISPIELE TIMER ###
"stell einen Timer für 5 Minuten"      → {"action": "set_timer", "minutes": 5, "label": ""}
"Timer 10 Minuten Nudeln kochen"       → {"action": "set_timer", "minutes": 10, "label": "Nudeln"}
"erinner mich in einer halben Stunde"  → {"action": "set_timer", "minutes": 30, "label": ""}

### BEISPIELE SCREENSHOT ###
"mach einen Screenshot"     → {"action": "take_screenshot"}
"screenshot"                → {"action": "take_screenshot"}
"fotografier den Bildschirm" → {"action": "take_screenshot"}

### BEISPIELE APP ÖFFNEN ###
"öffne Chrome"              → {"action": "open_app", "name": "chrome"}
"starte Discord"            → {"action": "open_app", "name": "discord"}
"mach den Taschenrechner auf" → {"action": "open_app", "name": "calculator"}
"öffne Explorer"            → {"action": "open_app", "name": "explorer"}
"""

WITZE = [
    "Was ist grün und rennt durch den Wald? Ein Rudel Gurken!",
    "Warum können Geister so schlecht lügen? Weil sie so leicht zu durchschauen sind!",
    "Was sagt ein großer Stift zum kleinen Stift? Wachsmalstift!",
    "Wie nennt man ein Kaninchen im Fitnessstudio? Pumpernickel!"
]

# ── GESPRÄCHSVERLAUF (In-Memory Ollama-Kontext) ────────────────────────────
_conversation_history = []

# ── AKTIVE TIMER ────────────────────────────────────────────────────────────
_active_timers = []
_timer_lock    = threading.Lock()

# ── LAZY LOADING ───────────────────────────────────────────────────────────
# Module werden erst beim ersten Aufruf geladen → Core startet sofort schnell

_whisper_model = None
_tts_engine    = None
_spotify       = None

def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        log.info(f"Lade Whisper ({WHISPER_MODEL_SIZE})...")
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
        log.info("Whisper bereit.")
    return _whisper_model

def get_tts():
    global _tts_engine
    if _tts_engine is None:
        try:
            from tts_with_rvc import TTS_RVC
            log.info("Lade RVC-TTS...")
            _tts_engine = TTS_RVC(
                model_path=RVC_MODEL,
                index_path=RVC_INDEX,
                voice="de-DE-KatjaNeural"
            )
            log.info("TTS bereit.")
        except Exception as e:
            log.warning(f"TTS nicht verfügbar: {e}")
            _tts_engine = "unavailable"
    return _tts_engine if _tts_engine != "unavailable" else None

def get_spotify():
    # FIX: "unavailable" nicht dauerhaft cachen – Retry bei erneutem Aufruf möglich
    global _spotify
    if _spotify is not None:
        return _spotify
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        log.info("Verbinde Spotify...")
        _spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="user-modify-playback-state user-read-playback-state",
            cache_path=SPOTIFY_CACHE_PATH
        ))
        log.info("Spotify bereit.")
        return _spotify
    except Exception as e:
        log.warning(f"Spotify nicht verfügbar: {e}")
        return None  # Nicht in _spotify cachen → nächster Aufruf versucht es erneut

# ── AKTIONEN ───────────────────────────────────────────────────────────────

def get_weather(city):
    try:
        r = requests.get(f"https://wttr.in/{city}?format=%C+und+%t", timeout=5)
        return r.text if r.status_code == 200 else "leider unbekannt"
    except:
        return "nicht erreichbar"

def get_news():
    try:
        req = urllib.request.Request(
            "https://www.tagesschau.de/index~rss2.xml",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req) as resp:
            feed = feedparser.parse(resp.read())
        headlines = []
        for i, e in enumerate(feed.entries[:3]):
            headlines.append(f"Meldung {i+1}: {e.title.replace(' - tagesschau.de','')}")
        return "Hier sind die Nachrichten: " + " ... ".join(headlines)
    except:
        return "Mein Nachrichten-Modul hat einen kleinen Wackelkontakt."

def spotify_play(query=""):
    sp = get_spotify()
    if not sp:
        return "Spotify ist gerade nicht verfügbar."
    try:
        devices = sp.devices()
        if not devices['devices']:
            spotify_pfade = [
                os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "Spotify.exe"),
                r"C:\Users\damja\AppData\Local\Microsoft\WindowsApps\Spotify.exe",
            ]
            for pfad in spotify_pfade:
                if os.path.exists(pfad):
                    subprocess.Popen([pfad], creationflags=subprocess.CREATE_NO_WINDOW,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
            else:
                subprocess.Popen(["explorer.exe", "spotify:"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(8):
                time.sleep(1)
                devices = sp.devices()
                if devices['devices']:
                    break
            if not devices['devices']:
                return "Spotify startet gerade, versuch es gleich nochmal."

        device_id = devices['devices'][0]['id']
        if query:
            results = sp.search(q=query, limit=5, type='track')
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
                sp.start_playback(device_id=device_id, uris=[track['uri']])
                return f"Ich spiele {track['name']} von {track['artists'][0]['name']}."
            kurze_query = " ".join(query.split()[:2])
            results2 = sp.search(q=kurze_query, limit=1, type='track')
            if results2['tracks']['items']:
                track = results2['tracks']['items'][0]
                sp.start_playback(device_id=device_id, uris=[track['uri']])
                return f"Spiele stattdessen {track['name']} von {track['artists'][0]['name']}."
            return f"Ich konnte nichts zu '{query}' finden."
        else:
            sp.start_playback(device_id=device_id)
            return "Musik läuft!"
    except Exception as e:
        log.error(f"Spotify Fehler: {e}")
        return "Spotify hat gerade einen Schluckauf."

def spotify_pause():
    sp = get_spotify()
    if not sp: return "Spotify nicht verfügbar."
    try: sp.pause_playback(); return "Musik pausiert."
    except: return "Konnte Musik nicht pausieren."

def spotify_resume():
    sp = get_spotify()
    if not sp: return "Spotify nicht verfügbar."
    try: sp.start_playback(); return "Musik läuft weiter."
    except: return "Konnte Musik nicht fortsetzen."

def spotify_next():
    sp = get_spotify()
    if not sp: return "Spotify nicht verfügbar."
    try: sp.next_track(); return "Nächstes Lied!"
    except: return "Konnte nicht zum nächsten Lied springen."

def spotify_playlist():
    """Spielt die konfigurierte Lieblings-Playlist."""
    sp = get_spotify()
    if not sp:
        return "Spotify ist gerade nicht verfügbar."
    try:
        devices = sp.devices()
        if not devices['devices']:
            spotify_pfade = [
                os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "Spotify.exe"),
                r"C:\Users\damja\AppData\Local\Microsoft\WindowsApps\Spotify.exe",
            ]
            for pfad in spotify_pfade:
                if os.path.exists(pfad):
                    subprocess.Popen([pfad], creationflags=subprocess.CREATE_NO_WINDOW,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
            else:
                subprocess.Popen(["explorer.exe", "spotify:"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(8):
                time.sleep(1)
                devices = sp.devices()
                if devices['devices']:
                    break
            if not devices['devices']:
                return "Spotify startet gerade, versuch es gleich nochmal."

        device_id = devices['devices'][0]['id']
        sp.start_playback(device_id=device_id,
                          context_uri=f"spotify:playlist:{SPOTIFY_PLAYLIST_ID}")
        return "Deine Playlist läuft!"
    except Exception as e:
        log.error(f"Spotify Playlist Fehler: {e}")
        return "Konnte Playlist nicht starten."

def spotify_volume(level: int):
    """Setzt Spotify-Lautstärke (0-100)."""
    sp = get_spotify()
    if not sp: return "Spotify nicht verfügbar."
    try:
        level = max(0, min(100, int(level)))
        sp.volume(level)
        return f"Lautstärke auf {level}% gesetzt."
    except Exception as e:
        log.error(f"Spotify Lautstärke Fehler: {e}")
        return "Konnte Lautstärke nicht ändern."

def spotify_get_volume():
    """Gibt aktuelle Spotify-Lautstärke zurück."""
    sp = get_spotify()
    if not sp: return None
    try:
        playback = sp.current_playback()
        if playback and playback.get('device'):
            return playback['device']['volume_percent']
    except:
        pass
    return None

def spotify_volume_up():
    current = spotify_get_volume()
    if current is None: return "Spotify nicht verfügbar."
    return spotify_volume(min(100, current + 20))

def spotify_volume_down():
    current = spotify_get_volume()
    if current is None: return "Spotify nicht verfügbar."
    return spotify_volume(max(0, current - 20))

# ── TIMER ──────────────────────────────────────────────────────────────────

def set_timer(minutes: float, label: str = ""):
    display   = f"{label} ({minutes} Min.)" if label else f"{minutes} Min."
    timer_id  = int(time.time() * 1000)
    entry = {
        'id':       timer_id,
        'label':    label or f"{minutes} Min.",
        'start':    time.time(),
        'duration': minutes * 60,
    }
    with _timer_lock:
        _active_timers.append(entry)

    def callback():
        log.info(f"Timer '{display}' abgelaufen.")
        with _timer_lock:
            _active_timers[:] = [t for t in _active_timers if t['id'] != timer_id]
        try:
            import pygame
            pygame.mixer.init()
            for dirpath, _, files in os.walk(SOUNDS_BASE):
                for fname in files:
                    if fname.lower().endswith('.wav'):
                        pygame.mixer.music.load(os.path.join(dirpath, fname))
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.1)
                        return
        except Exception as e:
            log.warning(f"Timer-Sound Fehler: {e}")

    t = threading.Timer(minutes * 60, callback)
    t.daemon = True
    t.start()
    return f"Timer gestellt: {display}. Ich sage Bescheid!"

# ── APP ÖFFNEN ─────────────────────────────────────────────────────────────

APP_MAP = {
    "chrome":         ["chrome"],
    "firefox":        ["firefox"],
    "edge":           ["msedge"],
    "spotify":        [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "Spotify.exe")],
    "discord":        ["discord"],
    "explorer":       ["explorer.exe"],
    "datei":          ["explorer.exe"],
    "notepad":        ["notepad.exe"],
    "notizblock":     ["notepad.exe"],
    "taschenrechner": ["calc.exe"],
    "calculator":     ["calc.exe"],
    "rechner":        ["calc.exe"],
    "vs code":        ["code"],
    "vscode":         ["code"],
    "terminal":       ["wt.exe"],
    "cmd":            ["cmd.exe"],
    "taskmanager":    ["taskmgr.exe"],
    "aufgaben":       ["taskmgr.exe"],
}

def open_app(name: str):
    name_lower = name.lower()
    for key, cmd in APP_MAP.items():
        if key in name_lower:
            try:
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"{name.capitalize()} wird geöffnet."
            except Exception as e:
                try:
                    subprocess.Popen(cmd[0])
                    return f"{name.capitalize()} wird geöffnet."
                except:
                    return f"Konnte '{name}' nicht öffnen: {e}"
    return f"Die App '{name}' kenne ich leider nicht."

def take_screenshot():
    """Macht einen Screenshot und speichert ihn im screenshots/ Ordner."""
    try:
        from PIL import ImageGrab
        folder = os.path.join(SCRIPT_DIR, "screenshots")
        os.makedirs(folder, exist_ok=True)
        filename = datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
        path = os.path.join(folder, filename)
        img = ImageGrab.grab()
        img.save(path)
        log.info(f"Screenshot gespeichert: {path}")
        return f"Screenshot gespeichert als {filename}."
    except Exception as e:
        log.error(f"Screenshot Fehler: {e}")
        return "Screenshot fehlgeschlagen."

def shutdown_pc():
    if os.path.exists(SHUTDOWN_DIR):
        sounds = [os.path.join(SHUTDOWN_DIR, f)
                  for f in os.listdir(SHUTDOWN_DIR) if f.lower().endswith('.wav')]
        if sounds:
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(random.choice(sounds))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            except:
                pass
    subprocess.run(["shutdown", "/s", "/t", "0"])

# ── JUMPSCARE ─────────────────────────────────────────────────────────────────

JUMPSCARE_IMAGE = os.path.join(BASE_DIR, "assets", "jumpscare", "jumpscare.png")
JUMPSCARE_SOUND = os.path.join(BASE_DIR, "assets", "jumpscare", "jumpscare.mp3")

def do_jumpscare():
    """Öffnet Vollbild-Jumpscare auf dem Hauptmonitor via tkinter."""
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
        import threading

        def run():
            log.info(f"Jumpscare Bild: {JUMPSCARE_IMAGE} – existiert: {os.path.exists(JUMPSCARE_IMAGE)}")
            log.info(f"Jumpscare Sound: {JUMPSCARE_SOUND} – existiert: {os.path.exists(JUMPSCARE_SOUND)}")
            root = tk.Tk()
            root.attributes('-fullscreen', True)
            root.attributes('-topmost', True)
            root.configure(bg='black')
            root.overrideredirect(True)

            # Bild laden
            if os.path.exists(JUMPSCARE_IMAGE):
                img = Image.open(JUMPSCARE_IMAGE)
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                img = img.resize((sw, sh), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(root, image=photo, bg='black')
                lbl.pack(fill='both', expand=True)
            else:
                lbl = tk.Label(root, text='👻', font=('Arial', 200), bg='black', fg='white')
                lbl.pack(expand=True)

            # Sound abspielen
            if os.path.exists(JUMPSCARE_SOUND):
                try:
                    import pygame
                    pygame.mixer.init()
                    pygame.mixer.music.load(JUMPSCARE_SOUND)
                    pygame.mixer.music.set_volume(1.0)
                    pygame.mixer.music.play()
                except Exception as e:
                    log.warning(f"Jumpscare Sound Fehler: {e}")

            # Klick oder Taste schließt Fenster
            root.bind('<Button-1>', lambda e: root.destroy())
            root.bind('<Key>', lambda e: root.destroy())

            # Auto-close nach 4 Sekunden
            root.after(4000, root.destroy)
            root.mainloop()

        threading.Thread(target=run, daemon=True).start()
    except Exception as e:
        log.error(f"Jumpscare Fehler: {e}")

# ── KERNFUNKTION: Text → Antwort ───────────────────────────────────────────

# Aktionen die NUR lokal ausgeführt werden dürfen (nicht für Remote-Anfragen vom Freund)
_REMOTE_SKIP = {
    "shutdown_pc", "set_timer", "open_app", "take_screenshot",
    "spotify_play", "spotify_pause", "spotify_resume", "spotify_next",
    "spotify_playlist", "spotify_volume", "spotify_volume_up", "spotify_volume_down",
}

def process_text(text: str, remote: bool = False) -> tuple:
    """
    Schickt Text an Ollama (mit Gesprächskontext), erkennt Aktionen,
    gibt (antwort, action, action_params) zurück.
    Bei remote=True werden lokale Aktionen nicht ausgeführt.
    """
    global _conversation_history

    messages = [{'role': 'system', 'content': BASE_SYSTEM_PROMPT}]
    messages.extend(_conversation_history)
    messages.append({'role': 'user', 'content': text})

    try:
        response = _ollama_lib.chat(model=OLLAMA_MODEL, messages=messages)
        content  = response['message']['content']
    except Exception as e:
        return f"Ollama ist gerade nicht erreichbar: {e}", None, {}

    result_text   = content
    action_name   = None
    action_params = {}

    if "{" in content and "action" in content:
        try:
            start  = content.find('{')
            end    = content.rfind('}') + 1
            data   = json.loads(content[start:end])
            action = data.get("action", "")
            action_name   = action
            action_params = data

            skip = remote and action in _REMOTE_SKIP

            if action == "get_time":
                result_text = f"Es ist jetzt {datetime.datetime.now().strftime('%H:%M')} Uhr."
            elif action == "get_joke":
                result_text = random.choice(WITZE)
            elif action == "get_news":
                result_text = get_news()
            elif action == "get_status":
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                result_text = f"CPU: {cpu}%, RAM: {ram}%. Alles läuft gut!"
            elif action == "get_weather":
                city = data.get("location", "Berlin")
                result_text = f"In {city} ist es aktuell {get_weather(city)}."
            elif action == "shutdown_pc":
                if not skip:
                    threading.Thread(target=shutdown_pc, daemon=True).start()
                result_text = "Okay, ich fahre jetzt herunter. Tschüss!"
            elif action == "spotify_play":
                result_text = "Musik wird gestartet!" if skip else spotify_play(data.get("query", ""))
            elif action == "spotify_pause":
                result_text = "Musik pausiert!" if skip else spotify_pause()
            elif action == "spotify_resume":
                result_text = "Musik wird fortgesetzt!" if skip else spotify_resume()
            elif action == "spotify_next":
                result_text = "Nächstes Lied!" if skip else spotify_next()
            elif action == "spotify_playlist":
                result_text = "Playlist wird gestartet!" if skip else spotify_playlist()
            elif action == "spotify_volume":
                result_text = f"Lautstärke auf {data.get('level', 50)}%!" if skip else spotify_volume(data.get("level", 50))
            elif action == "spotify_volume_up":
                result_text = "Lauter!" if skip else spotify_volume_up()
            elif action == "spotify_volume_down":
                result_text = "Leiser!" if skip else spotify_volume_down()
            elif action == "set_timer":
                result_text = f"Timer für {data.get('minutes', 5)} Minuten gesetzt!" if skip else set_timer(data.get("minutes", 5), data.get("label", ""))
            elif action == "open_app":
                result_text = f"App wird geöffnet!" if skip else open_app(data.get("name", ""))
            elif action == "take_screenshot":
                result_text = "Screenshot wird gemacht!" if skip else take_screenshot()
        except json.JSONDecodeError:
            pass

    # Kontext aktualisieren (echter Antworttext, nicht JSON)
    _conversation_history.append({'role': 'user',      'content': text})
    _conversation_history.append({'role': 'assistant', 'content': result_text})
    if len(_conversation_history) > MAX_HISTORY * 2:
        _conversation_history = _conversation_history[-(MAX_HISTORY * 2):]

    return result_text, action_name, action_params

# ── ROUTES ─────────────────────────────────────────────────────────────────

def save_conversation(user_text, bmo_text):
    """Hängt einen Gesprächseintrag an conversations.json an."""
    try:
        if os.path.exists(CONVERSATIONS_PATH):
            with open(CONVERSATIONS_PATH, 'r', encoding='utf-8') as f:
                convs = json.load(f)
        else:
            convs = []
        convs.insert(0, {
            'id':        int(time.time() * 1000),
            'user':      user_text,
            'bmo':       bmo_text,
            'timestamp': datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
        })
        with open(CONVERSATIONS_PATH, 'w', encoding='utf-8') as f:
            json.dump(convs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"Gespräch konnte nicht gespeichert werden: {e}")


@app.route('/process', methods=['POST'])
def route_process():
    """Hauptendpunkt: Text rein → Antwort + action raus."""
    if LITE_MODE or _ollama_lib is None:
        return jsonify(response="KI nicht verfügbar im Lite-Mode."), 503
    data = request.json or {}
    text = (data.get('message') or data.get('text') or '').strip()
    remote = bool(data.get('remote', False))
    if not text:
        return jsonify(response="Ich habe nichts verstanden.", action=None)
    response, action, action_params = process_text(text, remote=remote)
    save_conversation(text, response)
    return jsonify(response=response, action=action, action_params=action_params)


@app.route('/transcribe', methods=['POST'])
def route_transcribe():
    """Audio (base64 webm/wav) → Transkript + Antwort + action."""
    if LITE_MODE or _ollama_lib is None:
        return jsonify(response="KI nicht verfügbar im Lite-Mode."), 503
    data = request.json or {}
    b64  = data.get('audio', '')
    fmt  = data.get('format', 'webm')
    if not b64:
        return jsonify(transcript='', response='Kein Audio empfangen.', action=None)

    audio_bytes = base64.b64decode(b64)
    suffix = '.wav' if fmt == 'wav' else '.webm'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        in_path = f.name

    wav_path = in_path.rsplit('.', 1)[0] + '_conv.wav'
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', in_path, '-ar', '16000', '-ac', '1', wav_path],
            capture_output=True, timeout=15
        )
    except:
        wav_path = in_path

    transcript = ''
    try:
        wm     = get_whisper()
        result = wm.transcribe(wav_path, language="de", fp16=False,
                               temperature=0.0, no_speech_threshold=0.7,
                               condition_on_previous_text=False)
        text = result['text'].strip()
        PHANTOM = {".", "..", "...", "Untertitel", "Untertitelung", "Vielen Dank", ""}
        transcript = '' if text in PHANTOM else text
    except Exception as e:
        log.error(f"Whisper Fehler: {e}")

    for p in [in_path, wav_path]:
        try: os.remove(p)
        except: pass

    if not transcript:
        return jsonify(transcript='', response='Ich habe dich nicht verstanden.', action=None)

    remote = bool(data.get('remote', False))
    response, action, action_params = process_text(transcript, remote=remote)
    return jsonify(transcript=transcript, response=response, action=action, action_params=action_params)


@app.route('/speak', methods=['POST'])
def route_speak():
    """Text → WAV als base64 via RVC-TTS. Für Web-Interface oder externe Nutzung."""
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify(audio=None, error="Kein Text angegeben.")

    tts = get_tts()
    if not tts:
        return jsonify(audio=None, error="TTS nicht verfügbar.")

    try:
        out_path = os.path.join(tempfile.gettempdir(), "bmo_speak_out.wav")
        tts(text=text, pitch=4, tts_rate=25, output_filename=out_path)
        with open(out_path, 'rb') as f:
            audio_b64 = base64.b64encode(f.read()).decode('utf-8')
        try: os.remove(out_path)
        except: pass
        return jsonify(audio=audio_b64)
    except Exception as e:
        log.error(f"TTS Fehler: {e}")
        return jsonify(audio=None, error=str(e))


_gpu_cache = {"load": None, "mem": None}
_gpu_cache_lock = threading.Lock()

_bmo_busy = False
_bmo_busy_lock = threading.Lock()

def _refresh_gpu():
    """Hintergrund-Thread: GPU-Info alle 30s via WMI aktualisieren."""
    while True:
        load, mem = None, None
        try:
            import wmi
            w = wmi.WMI(namespace=r"root\OpenHardwareMonitor")
            for s in w.Sensor():
                if s.SensorType == "Load" and "GPU" in s.Name:
                    load = f"{s.Value:.0f}%"
                if s.SensorType == "SmallData" and "GPU" in s.Name and "Memory Used" in s.Name:
                    mem = f"{s.Value:.0f}MB"
        except:
            try:
                import wmi
                for gpu in wmi.WMI().Win32_VideoController():
                    if gpu.Name:
                        load = gpu.Name.split()[0]
                        break
            except:
                pass
        with _gpu_cache_lock:
            _gpu_cache["load"] = load
            _gpu_cache["mem"]  = mem
        time.sleep(30)

threading.Thread(target=_refresh_gpu, daemon=True).start()

@app.route('/status', methods=['GET'])
def route_status():
    """Systemstatus — sofort, GPU aus Cache."""
    cpu  = psutil.cpu_percent()
    ram  = psutil.virtual_memory().percent
    zeit = datetime.datetime.now().strftime('%H:%M')
    with _gpu_cache_lock:
        gpu_load = _gpu_cache["load"]
        gpu_mem  = _gpu_cache["mem"]
    with _bmo_busy_lock:
        busy = _bmo_busy
    return jsonify(cpu=cpu, ram=ram, time=zeit, gpu=gpu_load, gpu_mem=gpu_mem, busy=busy)


@app.route('/jumpscare', methods=['POST'])
def route_jumpscare():
    """Startet Vollbild-Jumpscare auf dem PC."""
    threading.Thread(target=do_jumpscare, daemon=True).start()
    return jsonify(response="BOO! 👻")


@app.route('/spotify/playlist', methods=['POST'])
def route_spotify_playlist():
    """Startet die konfigurierte Playlist."""
    msg = spotify_playlist()
    return jsonify(response=msg)


@app.route('/spotify/current', methods=['GET'])
def route_spotify_current():
    """Gibt aktuell spielenden Track zurück."""
    sp = get_spotify()
    if not sp:
        return jsonify(track=None, artist=None, playing=False)
    try:
        pb = sp.current_playback()
        if pb and pb.get('item'):
            images = pb['item'].get('album', {}).get('images', [])
            cover  = images[1]['url'] if len(images) > 1 else (images[0]['url'] if images else None)
            return jsonify(
                track=pb['item']['name'],
                artist=pb['item']['artists'][0]['name'],
                playing=pb['is_playing'],
                cover=cover
            )
    except:
        pass
    return jsonify(track=None, artist=None, playing=False)


@app.route('/spotify/volume', methods=['GET', 'POST'])
def route_spotify_volume():
    """GET → aktuelle Lautstärke; POST {level: 0-100} → Lautstärke setzen."""
    if request.method == 'GET':
        vol = spotify_get_volume()
        if vol is None:
            return jsonify(volume=None, error="Spotify nicht verfügbar.")
        return jsonify(volume=vol)
    else:
        data  = request.json or {}
        level = data.get('level', 50)
        msg   = spotify_volume(level)
        return jsonify(response=msg, volume=level)


@app.route('/photo', methods=['POST'])
def route_photo():
    """Bild (base64 JPEG) + optionale Frage → BMO beschreibt das Bild via Vision-Modell."""
    if LITE_MODE or _ollama_lib is None:
        return jsonify(response="KI nicht verfügbar im Lite-Mode."), 503
    data     = request.json or {}
    b64      = data.get('image', '')
    question = data.get('question', 'Was siehst du auf diesem Bild? Beschreibe es kurz auf Deutsch.')
    if not b64:
        return jsonify(response="Kein Bild empfangen.", action=None)
    try:
        response = _ollama_lib.chat(
            model=VISION_MODEL,
            messages=[{
                'role':    'user',
                'content': question,
                'images':  [b64]
            }]
        )
        content = response['message']['content']
        return jsonify(response=content, action='photo_analyzed')
    except Exception as e:
        log.error(f"Vision Fehler: {e}")
        return jsonify(
            response=f"Ich konnte das Bild leider nicht analysieren. Läuft '{VISION_MODEL}' in Ollama? (ollama pull {VISION_MODEL})",
            action=None
        )


@app.route('/conversations', methods=['GET'])
def route_conversations():
    """Gibt alle gespeicherten Gespräche zurück."""
    try:
        if os.path.exists(CONVERSATIONS_PATH):
            with open(CONVERSATIONS_PATH, 'r', encoding='utf-8') as f:
                convs = json.load(f)
        else:
            convs = []
        return jsonify(conversations=convs)
    except Exception as e:
        return jsonify(conversations=[], error=str(e))

@app.route('/conversations', methods=['DELETE'])
def route_conversations_clear():
    """Löscht den gesamten Gesprächsverlauf."""
    try:
        if os.path.exists(CONVERSATIONS_PATH):
            os.remove(CONVERSATIONS_PATH)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route('/history/clear', methods=['POST'])
def route_history_clear():
    """In-Memory Kontext zurücksetzen."""
    global _conversation_history
    _conversation_history = []
    log.info("Gesprächskontext gelöscht.")
    return jsonify(status="ok")


@app.route('/timers', methods=['GET'])
def route_timers():
    """Gibt alle aktiven Timer mit verbleibender Zeit zurück."""
    now = time.time()
    with _timer_lock:
        result = []
        for t in _active_timers:
            remaining = t['duration'] - (now - t['start'])
            if remaining > 0:
                result.append({
                    'id':        t['id'],
                    'label':     t['label'],
                    'remaining': int(remaining),
                    'duration':  int(t['duration']),
                })
    return jsonify(timers=result)


@app.route('/ping', methods=['GET'])
def route_ping():
    """Lebenszeichen — Interfaces prüfen hiermit ob Core läuft."""
    return jsonify(status="ok", version="1.0", port=PORT)


@app.route('/api/points/verify', methods=['POST'])
def route_points_verify():
    """Empfängt und verifiziert Punkte-Stand vom Freund-Server."""
    data      = request.get_json(silent=True) or {}
    try:
        points = int(data.get('points', 0))
    except (ValueError, TypeError):
        return jsonify(error='Ungültiger Punktestand'), 400
    freund_id = data.get('freund_id', 'unknown')

    stored = _load_points(freund_id)
    # Erlaubt: Stand stimmt mit gespeichertem überein oder ist höher (Punkte verdient)
    # Ablehnen: Stand ist niedriger als gespeichert (hätte schon abgezogen sein müssen)
    if points < stored:
        # Manipulation erkannt: gespeicherten Stand zurückspielen
        return jsonify(points=stored, corrected=True)

    _save_points(points, freund_id)
    return jsonify(points=points, corrected=False)


@app.route('/api/draw/open', methods=['POST'])
def route_draw_open():
    """Freund hat screen_draw gekauft — öffnet tkinter-Canvas auf Admin-Monitor."""
    global _draw_window_open, _draw_strokes_from_friend
    with _draw_lock:
        _draw_strokes_from_friend = []
        _draw_window_open = True
    threading.Thread(target=_run_draw_window, daemon=True).start()
    return jsonify(ok=True)

@app.route('/api/draw/stroke', methods=['POST'])
def route_draw_stroke():
    """Empfängt Strich vom Freund → Admin-tkinter rendert ihn."""
    data = request.get_json(silent=True) or {}
    with _draw_lock:
        if _draw_window_open:
            _draw_strokes_from_friend.append(data)
    return jsonify(ok=True)

@app.route('/api/draw/strokes', methods=['GET'])
def route_draw_strokes():
    """Freund pollt Admin-Striche (Admin→Freund Richtung)."""
    with _draw_lock:
        strokes = list(_draw_strokes_for_friend)
        _draw_strokes_for_friend.clear()
    return jsonify(strokes=strokes)

@app.route('/api/draw/friend-stroke', methods=['POST'])
def route_draw_friend_stroke():
    """Admin sendet Strich an Freund-Browser."""
    data = request.get_json(silent=True) or {}
    with _draw_lock:
        _draw_strokes_for_friend.append(data)
    return jsonify(ok=True)

@app.route('/api/draw/close', methods=['POST'])
def route_draw_close():
    """Schließt Draw-Session."""
    global _draw_window_open
    with _draw_lock:
        _draw_window_open = False
        _draw_strokes_from_friend.clear()
        _draw_strokes_for_friend.clear()
    return jsonify(ok=True)


@app.route('/lite-mode', methods=['GET'])
def route_lite_mode_get():
    return jsonify(lite_mode=LITE_MODE)

@app.route('/lite-mode', methods=['POST'])
def route_lite_mode_set():
    """Schaltet Lite-Mode ein/aus (Neustart empfohlen)."""
    global LITE_MODE
    data   = request.get_json(silent=True) or {}
    enable = data.get('enable', not LITE_MODE)
    cfg    = _read_bmo_config()
    cfg['LITE_MODE'] = 'true' if enable else 'false'
    _write_bmo_config(cfg)
    LITE_MODE = enable
    log.info(f"Lite-Mode {'aktiviert' if enable else 'deaktiviert'}. Neustart empfohlen.")
    return jsonify(lite_mode=enable, restart_required=True)


# ── START ───────────────────────────────────────────────────────────────────
def _run_draw_window():
    """Öffnet transparentes tkinter-Overlay auf dem Admin-Monitor (Freund malt drauf)."""
    global _draw_window_open
    try:
        import tkinter as tk
        root = tk.Tk()
        root.attributes('-fullscreen', True)
        root.attributes('-topmost', True)
        root.attributes('-alpha', 0.7)
        root.configure(bg='black')
        root.overrideredirect(True)

        canvas = tk.Canvas(root, bg='black', highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        tk.Label(root, text='Freund malt... (Klick zum Schließen)',
                 bg='black', fg='#4ade80', font=('Arial', 14)).place(x=10, y=10)

        def close(_=None):
            global _draw_window_open
            _draw_window_open = False
            try:
                root.destroy()
            except Exception:
                pass

        root.bind('<Button-1>', close)
        root.bind('<Escape>', close)
        root.after(60000, close)

        last_x = last_y = None

        def poll_strokes():
            nonlocal last_x, last_y
            with _draw_lock:
                strokes = list(_draw_strokes_from_friend)
                _draw_strokes_from_friend.clear()
            for s in strokes:
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                x = int(s.get('x', 0) * sw)
                y = int(s.get('y', 0) * sh)
                if s.get('type') == 'move' and last_x is not None:
                    canvas.create_line(last_x, last_y, x, y,
                                       fill=s.get('color', '#ef4444'),
                                       width=int(s.get('w', 4)),
                                       smooth=True, capstyle='round')
                last_x, last_y = x, y
                if s.get('type') == 'up':
                    last_x = last_y = None
            if not _draw_window_open:
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            root.after(100, poll_strokes)

        root.after(100, poll_strokes)
        root.mainloop()
    except Exception as e:
        log.error(f'Draw-Fenster Fehler: {e}')
    finally:
        _draw_window_open = False

def _warmup_ollama():
    """Lädt das Ollama-Modell vorab in den RAM — erster Prompt wird schnell."""
    try:
        log.info(f"Ollama Warmup: Lade {OLLAMA_MODEL} vor...")
        if _ollama_lib is None:
            log.info("Ollama nicht verfügbar (Lite-Mode oder nicht installiert).")
            return
        _ollama_lib.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": "hi"}])
        log.info("Ollama Warmup abgeschlossen — Modell bereit.")
    except Exception as e:
        log.warning(f"Ollama Warmup fehlgeschlagen (Ollama läuft?): {e}")

if __name__ == '__main__':
    log.info("BMO Core startet...")
    log.info(f"Port: {PORT} | Modell: {OLLAMA_MODEL} | Whisper: {WHISPER_MODEL_SIZE}")
    if not LITE_MODE:
        threading.Thread(target=_warmup_ollama, daemon=True).start()
    try:
        from waitress import serve
        log.info("Nutze waitress als WSGI-Server (stabil, kein Keep-Alive-Problem)")
        serve(app, host='0.0.0.0', port=PORT, threads=4)
    except ImportError:
        log.warning("waitress nicht installiert — nutze Werkzeug (pip install waitress empfohlen)")
        app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)