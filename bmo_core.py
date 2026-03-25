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
sys.path.insert(0, r"C:\Users\damja\AppData\Roaming\Python\Python310\site-packages")

# ── LOGGING ────────────────────────────────────────────────────────────────
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bmo_core.log")
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
import ollama
import psutil
import datetime
import requests
import json
import random
import threading
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

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
RVC_MODEL    = os.path.join(SCRIPT_DIR, "BMO_500e_7000s.pth")
RVC_INDEX    = os.path.join(SCRIPT_DIR, "BMO.index")
SOUNDS_BASE  = os.path.join(SCRIPT_DIR, "sounds")
SHUTDOWN_DIR = os.path.join(SOUNDS_BASE, "shutdown")

SPOTIFY_CLIENT_ID     = "365b371ad2c7483ea7dda2029869c3a3"
SPOTIFY_CLIENT_SECRET = "2c6b2968fbb9425792b99355b03b65ac"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"
SPOTIFY_CACHE_PATH    = os.path.join(SCRIPT_DIR, ".spotify_cache")

SPOTIFY_PLAYLIST_ID = "1CQx19s0ib50fjgxM47FXY"

WHISPER_MODEL_SIZE = "small"

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
Playlist:    {"action": "spotify_playlist"}

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
"lauter"                    → {"action": "spotify_volume", "level": 80}
"leiser"                    → {"action": "spotify_volume", "level": 30}
"Lautstärke auf 50"         → {"action": "spotify_volume", "level": 50}
"spiel meine Playlist"      → {"action": "spotify_playlist"}
"meine Lieblingsmusik"      → {"action": "spotify_playlist"}
"""

WITZE = [
    "Was ist grün und rennt durch den Wald? Ein Rudel Gurken!",
    "Warum können Geister so schlecht lügen? Weil sie so leicht zu durchschauen sind!",
    "Was sagt ein großer Stift zum kleinen Stift? Wachsmalstift!",
    "Wie nennt man ein Kaninchen im Fitnessstudio? Pumpernickel!"
]

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

JUMPSCARE_IMAGE = r"D:\python\scripts\Bmo\static\jumpscare.png"
JUMPSCARE_SOUND = r"D:\python\scripts\Bmo\static\jumpscare.mp3"

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

def process_text(text: str) -> tuple:
    """
    Schickt Text an Ollama, erkennt Aktionen, gibt (antwort, action) zurück.
    FIX: Gibt jetzt immer ein Tupel (response_text, action_or_None) zurück,
         damit Desktop und Web auf Aktionen reagieren können.
    """
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=[
            {'role': 'system', 'content': BASE_SYSTEM_PROMPT},
            {'role': 'user',   'content': text},
        ])
        content = response['message']['content']
    except Exception as e:
        return f"Ollama ist gerade nicht erreichbar: {e}", None

    if "{" in content and "action" in content:
        try:
            start  = content.find('{')
            end    = content.rfind('}') + 1
            data   = json.loads(content[start:end])
            action = data.get("action", "")

            if action == "get_time":
                return f"Es ist jetzt {datetime.datetime.now().strftime('%H:%M')} Uhr.", action
            elif action == "get_joke":
                return random.choice(WITZE), action
            elif action == "get_news":
                return get_news(), action
            elif action == "get_status":
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                return f"CPU: {cpu}%, RAM: {ram}%. Alles läuft gut!", action
            elif action == "get_weather":
                city = data.get("location", "Berlin")
                return f"In {city} ist es aktuell {get_weather(city)}.", action
            elif action == "shutdown_pc":
                threading.Thread(target=shutdown_pc, daemon=True).start()
                return "Okay, ich fahre jetzt herunter. Tschüss!", action
            elif action == "spotify_play":
                return spotify_play(data.get("query", "")), action
            elif action == "spotify_pause":
                return spotify_pause(), action
            elif action == "spotify_resume":
                return spotify_resume(), action
            elif action == "spotify_next":
                return spotify_next(), action
            elif action == "spotify_playlist":
                return spotify_playlist(), action
            elif action == "spotify_volume":
                return spotify_volume(data.get("level", 50)), action
        except json.JSONDecodeError:
            pass

    return content, None

# ── ROUTES ─────────────────────────────────────────────────────────────────

@app.route('/process', methods=['POST'])
def route_process():
    """Hauptendpunkt: Text rein → Antwort + action raus."""
    data = request.json or {}
    # FIX: akzeptiert sowohl "message" als auch "text" als Key
    text = (data.get('message') or data.get('text') or '').strip()
    if not text:
        return jsonify(response="Ich habe nichts verstanden.", action=None)
    response, action = process_text(text)
    return jsonify(response=response, action=action)


@app.route('/transcribe', methods=['POST'])
def route_transcribe():
    """Audio (base64 webm/wav) → Transkript + Antwort + action."""
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

    response, action = process_text(transcript)
    return jsonify(transcript=transcript, response=response, action=action)


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


@app.route('/status', methods=['GET'])
def route_status():
    """Systemstatus für Status-Karten in beiden Interfaces."""
    cpu  = psutil.cpu_percent(interval=0.5)
    ram  = psutil.virtual_memory().percent
    zeit = datetime.datetime.now().strftime('%H:%M')

    # GPU via wmi (AMD-kompatibel)
    gpu_load = None
    try:
        import wmi
        w = wmi.WMI(namespace="root\OpenHardwareMonitor")
        sensors = w.Sensor()
        for s in sensors:
            if s.SensorType == "Load" and "GPU" in s.Name:
                gpu_load = f"{s.Value:.0f}%"
            if s.SensorType == "SmallData" and "GPU" in s.Name and "Memory Used" in s.Name:
                gpu_mem = f"{s.Value:.0f}MB"
    except:
        # Fallback: wmi ohne OpenHardwareMonitor
        try:
            import wmi
            w = wmi.WMI()
            for gpu in w.Win32_VideoController():
                if gpu.Name:
                    gpu_load = gpu.Name.split()[0]  # nur GPU-Name als Fallback
                    break
        except:
            pass

    return jsonify(cpu=cpu, ram=ram, time=zeit, gpu=gpu_load, gpu_mem=gpu_mem)


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


@app.route('/ping', methods=['GET'])
def route_ping():
    """Lebenszeichen — Interfaces prüfen hiermit ob Core läuft."""
    return jsonify(status="ok", version="1.0", port=PORT)


# ── START ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("\n🤖 BMO Core startet...")
    print(f"   Port       : {PORT}")
    print(f"   Modell     : {OLLAMA_MODEL}")
    print(f"   Whisper    : {WHISPER_MODEL_SIZE}  (lazy – wird beim 1. Aufruf geladen)")
    print(f"   TTS/RVC    : {RVC_MODEL}")
    print(f"\n   Endpunkte  :")
    print(f"   POST  /process     → Text → Antwort + action")
    print(f"   POST  /transcribe  → Audio → Transkript + Antwort + action")
    print(f"   POST  /speak       → Text → WAV (base64)")
    print(f"   GET   /status      → CPU / RAM / Uhrzeit / Temp")
    print(f"   GET   /ping        → Lebenszeichen\n")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)