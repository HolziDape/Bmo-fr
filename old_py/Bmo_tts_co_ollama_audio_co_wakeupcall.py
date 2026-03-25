import os
import numpy as np
import sounddevice as sd
from openwakeword.model import Model
import ollama
import speech_recognition as sr
import pygame
import random
import time
import threading
from tts_with_rvc import TTS_RVC
import datetime
import requests
import psutil
import feedparser
import ssl
import urllib.request
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import whisper
import tempfile
import soundfile as sf

# Global die SSL-Prüfung ausschalten (kommt ganz oben ins Skript)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# --- SYSTEM PROMPT ---
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
"""

# --- 1. KONFIGURATION & PFADE ---
WAKE_WORD_MODEL = "wakeword.onnx"
RVC_MODEL = "BMO_500e_7000s.pth"
RVC_INDEX = "BMO.index"

# ┌─────────────────────────────────────────────────────────────────┐
# │  WAKE-WORD EINSTELLUNGEN                                        │
# │                                                                 │
# │  WAKE_THRESHOLD: Empfindlichkeit pro Chunk                      │
# │    0.5 = empfindlicher (mehr Treffer, evtl. Fehlauslöser)       │
# │    0.7 = strenger (weniger Fehlauslöser, aber sicherer)         │
# │                                                                 │
# │  WAKE_VOTES_NEEDED: Wie viele Chunks hintereinander             │
# │  müssen über dem Threshold liegen, bevor BMO reagiert?          │
# │    1 = sofort (wie vorher)                                      │
# │    2 = zwei bestätigende Chunks (~160ms) → empfohlen            │
# │    3 = drei Chunks (~240ms) → sehr sicher, kaum Fehlauslöser    │
# └─────────────────────────────────────────────────────────────────┘
WAKE_THRESHOLD    = 0.5   # Schwellenwert gesenkt: empfindlicher
WAKE_VOTES_NEEDED = 1     # Mindestens 2 bestätigende Chunks

# ┌─────────────────────────────────────────────────────────────────┐
# │  WHISPER EINSTELLUNGEN                                          │
# │                                                                 │
# │  WHISPER_MODEL: Größe des Modells                               │
# │    "tiny"   = schnellst, ungenauer  (~75MB)                     │
# │    "base"   = gut & schnell         (~150MB)  ← empfohlen       │
# │    "small"  = besser, etwas langsam (~500MB)                    │
# │    "medium" = sehr gut, langsamer   (~1.5GB)                    │
# └─────────────────────────────────────────────────────────────────┘
WHISPER_MODEL_SIZE = "small"
# │                                                                 │
# │  LISTEN_TIMEOUT: Wie viele Sekunden wartet BMO auf den          │
# │  ERSTEN Ton, bevor er aufgibt?                                  │
# │    4 = 4 Sekunden Stille → dann Abbruch (wie vorher)            │
# │                                                                 │
# │  PAUSE_THRESHOLD: Wie viele Sekunden Stille NACH dem letzten    │
# │  Wort gelten als "Satz zu Ende"?                                │
# │    3.0 = 3 Sekunden Pause → dann stoppt die Aufnahme            │
# │    Erhöhe auf 5.0 oder 10.0 für noch mehr Geduld                │
# └─────────────────────────────────────────────────────────────────┘
LISTEN_TIMEOUT   = 4      # Sekunden bis zum ersten Ton
PAUSE_THRESHOLD  = 1.5    # Sekunden Stille nach dem letzten Wort

# Sound-Verzeichnisse
SOUNDS_BASE = "sounds"
BOOT_DIR    = os.path.join(SOUNDS_BASE, "boot")
DENKEN_DIR  = os.path.join(SOUNDS_BASE, "denken")
HEYBMO_DIR  = os.path.join(SOUNDS_BASE, "heybmo")
REPLY_DIR   = os.path.join(SOUNDS_BASE, "reply")
SHUTDOWN_DIR = os.path.join(SOUNDS_BASE, "shutdown")

# ┌─────────────────────────────────────────────────────────────────┐
# │  SPOTIFY EINSTELLUNGEN                                          │
# └─────────────────────────────────────────────────────────────────┘
SPOTIFY_CLIENT_ID     = "365b371ad2c7483ea7dda2029869c3a3"
SPOTIFY_CLIENT_SECRET = "2c6b2968fbb9425792b99355b03b65ac"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"
# Cache direkt ins Skript-Verzeichnis speichern → kein Berechtigungsproblem
SPOTIFY_CACHE_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spotify_cache")

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope="user-modify-playback-state user-read-playback-state",
    cache_path=SPOTIFY_CACHE_PATH  # ← fixer Cache-Pfad
))

# Bilder-Verzeichnisse
FACES_BASE = "faces"
FACE_DIRS = {
    "BOOT":   os.path.join(FACES_BASE, "boot"),
    "IDLE":   os.path.join(FACES_BASE, "idle"),
    "LISTEN": os.path.join(FACES_BASE, "hören"),
    "THINK":  os.path.join(FACES_BASE, "denken"),
    "SPEAK":  os.path.join(FACES_BASE, "reden")
}

# Globaler Zustand
CURRENT_STATE = "BOOT"

# --- 2. HILFSFUNKTIONEN ---

def get_files(directory, extensions):
    if os.path.exists(directory):
        return [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(extensions)]
    return []

def load_face_images():
    images = {}
    for state, path in FACE_DIRS.items():
        imgs = get_files(path, ('.png', '.jpg', '.jpeg'))
        images[state] = [pygame.image.load(i) for i in imgs]
    return images

# --- 3. GRAFIK-THREAD ---

def bmo_face_thread():
    global CURRENT_STATE
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    pygame.display.set_caption("BMO OS")
    
    face_dict = load_face_images()
    clock = pygame.time.Clock()
    
    last_state  = None
    current_img = None
    next_switch = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return

        now = pygame.time.get_ticks()

        # 1. SOFORT-WECHSEL wenn sich der Modus ändert
        if CURRENT_STATE != last_state:
            available = face_dict.get(CURRENT_STATE, [])
            if available:
                current_img = random.choice(available)
            last_state  = CURRENT_STATE
            next_switch = now + 2000

        # 2. ANIMATION während des Denkens (THINK)
        elif CURRENT_STATE == "THINK":
            if now > next_switch:
                available = face_dict.get("THINK", [])
                if available:
                    current_img = random.choice(available)
                next_switch = now + 1000

        # 3. ANIMATION während des Redens (SPEAK)
        elif CURRENT_STATE == "SPEAK":
            if now > next_switch:
                available = face_dict.get("SPEAK", [])
                if available:
                    current_img = random.choice(available)
                next_switch = now + 50

        # Zeichnen
        screen.fill((43, 135, 115))
        if current_img:
            rect = current_img.get_rect(center=(400, 240))
            screen.blit(current_img, rect)

        pygame.display.flip()
        clock.tick(30)

# --- 4. AUDIO-FUNKTIONEN ---

def play_random_sound(directory, wait=False):
    sounds = get_files(directory, ".wav")
    if not sounds: return
    pygame.mixer.music.stop()
    pygame.mixer.music.unload()
    wahl = random.choice(sounds)
    pygame.mixer.music.load(wahl)
    pygame.mixer.music.set_volume(0.3)
    pygame.mixer.music.play()
    if wait:
        while pygame.mixer.music.get_busy(): time.sleep(0.1)

def speak_bmo(text, tts_engine):
    global CURRENT_STATE
    print("Generiere Stimme...")

    path = tts_engine(text=text, pitch=4, tts_rate=25, output_filename="bmo_live.wav")

    CURRENT_STATE = "SPEAK"
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        time.sleep(0.1)

    CURRENT_STATE = "IDLE"

def get_bmo_time():
    now = datetime.datetime.now()
    return now.strftime("%H:%M")

def get_weather(city):
    try:
        url = f"https://wttr.in/{city}?format=%C+und+%t"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.text
        return "leider unbekannt"
    except:
        return "nicht erreichbar"

def get_bmo_joke():
    witze = [
        "Was ist grün und rennt durch den Wald? Ein Rudel Gurken!",
        "Warum können Geister so schlecht lügen? Weil sie so leicht zu durchschauen sind!",
        "Was sagt ein großer Stift zum kleinen Stift? Wachsmalstift!",
        "Wie nennt man ein Kaninchen im Fitnessstudio? Pumpernickel!"
    ]
    return random.choice(witze)

def get_bmo_status():
    cpu_load = psutil.cpu_percent()
    return f"Meine CPU ist zu {cpu_load} Prozent ausgelastet. Ich fühle mich topfit!"

def get_bmo_news():
    print("Greife auf Tagesschau-Server zu...")
    url = "https://www.tagesschau.de/index~rss2.xml"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
        feed = feedparser.parse(xml_data)
        if not feed.entries:
            return "Ich kann gerade keine Nachrichten finden. Vielleicht machen die Reporter gerade Pause?"
        schlagzeilen = []
        for i, entry in enumerate(feed.entries[:3]):
            titel = entry.title.replace(' - tagesschau.de', '')
            schlagzeilen.append(f"Meldung {i+1}: {titel}")
        return "Hier sind die Nachrichten: " + " ... ".join(schlagzeilen)
    except Exception as e:
        print(f"Fehler im Detail: {e}")
        return "Mein Nachrichten-Modul hat einen kleinen Wackelkontakt."

def shutdown_pc():
    import subprocess
    play_random_sound(SHUTDOWN_DIR, wait=True)
    subprocess.run(["shutdown", "/s", "/t", "0"])

def spotify_play(query=""):
    try:
        devices = sp.devices()

        # Falls kein Gerät aktiv: Spotify starten
        if not devices['devices']:
            import subprocess
            import ctypes

            # Mögliche Spotify Pfade (normale Installation + Microsoft Store)
            spotify_pfade = [
                os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "Spotify.exe"),
                r"C:\Users\damja\AppData\Local\Microsoft\WindowsApps\Spotify.exe",
            ]

            gestartet = False
            for pfad in spotify_pfade:
                if os.path.exists(pfad):
                    print(f"Starte Spotify: {pfad}")
                    # start minimiert im Hintergrund
                    subprocess.Popen(
                        [pfad],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    gestartet = True
                    break

            if not gestartet:
                # Letzter Versuch: über Windows URI (funktioniert immer bei Store-Version)
                subprocess.Popen(
                    ["explorer.exe", "spotify:"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # Warten bis Spotify bereit ist (max 8 Sekunden)
            print("Warte auf Spotify...")
            for _ in range(8):
                time.sleep(1)
                devices = sp.devices()
                if devices['devices']:
                    break

            if not devices['devices']:
                return "Spotify startet gerade noch, versuch es in ein paar Sekunden nochmal."

        device_id = devices['devices'][0]['id']

        # Spotify Fenster minimiert lassen via Windows API
        try:
            import ctypes
            import ctypes.wintypes
            EnumWindows   = ctypes.windll.user32.EnumWindows
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            ShowWindow    = ctypes.windll.user32.ShowWindow
            CALLBACK      = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            def callback(hwnd, _):
                buf = ctypes.create_unicode_buffer(256)
                GetWindowText(hwnd, buf, 256)
                if "Spotify" in buf.value:
                    ShowWindow(hwnd, 6)  # SW_MINIMIZE
                return True

            EnumWindows(CALLBACK(callback), 0)
        except:
            pass

        if query:
            # Whisper hört Songnamen oft falsch → großzügige Suche mit mehr Ergebnissen
            # Ollama hat den Satz bereits zu einem Suchbegriff vereinfacht,
            # aber wir suchen trotzdem breit
            print(f"[Spotify] Suche nach: '{query}'")
            results = sp.search(q=query, limit=5, type='track')
            if results['tracks']['items']:
                track  = results['tracks']['items'][0]
                sp.start_playback(device_id=device_id, uris=[track['uri']])
                name   = track['name']
                artist = track['artists'][0]['name']
                print(f"[Spotify] Spiele: {name} - {artist}")
                return f"Ich spiele {name} von {artist}."
            else:
                # Zweiter Versuch: nur die ersten zwei Wörter der Query
                kurze_query = " ".join(query.split()[:2])
                print(f"[Spotify] Zweiter Versuch mit: '{kurze_query}'")
                results2 = sp.search(q=kurze_query, limit=1, type='track')
                if results2['tracks']['items']:
                    track  = results2['tracks']['items'][0]
                    sp.start_playback(device_id=device_id, uris=[track['uri']])
                    name   = track['name']
                    artist = track['artists'][0]['name']
                    return f"Ich habe nichts Genaues gefunden, spiele stattdessen {name} von {artist}."
                return f"Ich konnte leider nichts zu '{query}' finden."
        else:
            sp.start_playback(device_id=device_id)
            return "Musik läuft!"
    except Exception as e:
        print(f"Spotify Fehler: {e}")
        return "Spotify hat gerade einen Schluckauf."

def spotify_pause():
    try:
        sp.pause_playback()
        return "Musik pausiert."
    except:
        return "Ich konnte die Musik nicht pausieren."

def spotify_resume():
    try:
        sp.start_playback()
        return "Musik läuft weiter."
    except:
        return "Ich konnte die Musik nicht fortsetzen."

def spotify_next():
    try:
        sp.next_track()
        return "Nächstes Lied!"
    except:
        return "Ich konnte nicht zum nächsten Lied springen."

# --- 5. HAUPTPROGRAMM ---

# Whisper global damit transcribe() darauf zugreifen kann
whisper_model = None

def transcribe(audio) -> str:
    """Wandelt sr.AudioData mit Whisper in Text um."""
    sample_rate = audio.sample_rate
    raw = np.frombuffer(audio.get_raw_data(), dtype=np.int16).astype(np.float32) / 32768.0

    # Whisper braucht exakt 16000 Hz — falls abweichend resamplen
    if sample_rate != 16000:
        import scipy.signal
        raw = scipy.signal.resample(raw, int(len(raw) * 16000 / sample_rate))

    # Zu kurze oder zu leise Aufnahmen direkt ablehnen (Stille-Filter)
    if len(raw) < 8000:  # weniger als 0.5 Sekunden
        print("[Whisper] Aufnahme zu kurz, ignoriert.")
        return ""
    if np.abs(raw).max() < 0.01:  # fast kein Signal
        print("[Whisper] Aufnahme zu leise, ignoriert.")
        return ""

    result = whisper_model.transcribe(
        raw,
        language="de",
        fp16=False,
        temperature=0.0,
        no_speech_threshold=0.7,      # höher = strenger gegen Stille
        condition_on_previous_text=False
    )

    # Whisper gibt manchmal Phantomtexte zurück wenn nichts gesagt wurde
    text = result["text"].strip()
    PHANTOM_TEXTE = [".", "..", "...", "Untertitel", "Untertitelung", "Vielen Dank", ""]
    if text in PHANTOM_TEXTE:
        print(f"[Whisper] Phantomtext erkannt ('{text}'), ignoriert.")
        return ""

    print(f"[Whisper] erkannt: '{text}'")
    return text

def main():
    global CURRENT_STATE, whisper_model

    # Grafik starten
    threading.Thread(target=bmo_face_thread, daemon=True).start()

    # Initialisierung
    print("Initialisiere Systeme...")
    pygame.mixer.init()

    # ── Whisper laden (einmalig, danach im RAM) ────────────────────────────
    print(f"Lade Whisper Modell ({WHISPER_MODEL_SIZE})...")
    whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    print("Whisper bereit!")
    # ──────────────────────────────────────────────────────────────────────

    # ── SpeechRecognition nur noch für Audio-Aufnahme ─────────────────────
    recognizer = sr.Recognizer()
    recognizer.pause_threshold       = PAUSE_THRESHOLD
    recognizer.non_speaking_duration = PAUSE_THRESHOLD
    # ──────────────────────────────────────────────────────────────────────

    tts       = TTS_RVC(model_path=RVC_MODEL, index_path=RVC_INDEX, voice="de-DE-KatjaNeural")
    oww_model = Model(wakeword_models=[WAKE_WORD_MODEL])

    # Boot-Vorgang
    CURRENT_STATE = "BOOT"
    play_random_sound(BOOT_DIR, wait=True)
    CURRENT_STATE = "IDLE"

    while True:
        # --- SCHRITT 1: STANDBY – Wake-Word mit Voting-System ---
        with sd.InputStream(samplerate=16000, channels=1, dtype='int16') as stream:
            print(f"[STBY] Warte auf Wake-Word "
                  f"(Threshold={WAKE_THRESHOLD}, Votes={WAKE_VOTES_NEEDED})...")
            oww_model.reset()
            wake_detected = False
            vote_counter  = 0   # ← NEU: Zählt aufeinanderfolgende positive Chunks

            while not wake_detected:
                audio_chunk, _ = stream.read(1280)
                audio_chunk     = np.frombuffer(audio_chunk, dtype=np.int16)
                oww_model.predict(audio_chunk)

                # Prüfe ob IRGENDEIN Modell über dem Threshold liegt
                triggered = any(
                    oww_model.prediction_buffer[m][-1] > WAKE_THRESHOLD
                    for m in oww_model.prediction_buffer
                )

                if triggered:
                    vote_counter += 1
                    print(f"[WAKE] Vote {vote_counter}/{WAKE_VOTES_NEEDED}...")
                    if vote_counter >= WAKE_VOTES_NEEDED:
                        wake_detected = True
                else:
                    # Kein Treffer → Zähler zurücksetzen (kein Flackern)
                    vote_counter = 0

        # --- SCHRITT 2: AKTIV-MODUS ---
        conversation_active  = True
        is_first_interaction = True

        # Wörter die bedeuten "nein, ich bin fertig"
        ABBRUCH_WOERTER = [
            "ne", "nein", "nö", "pass", "danke", "reicht",
            "war alles", "das war alles", "nichts", "nichts mehr",
            "kein", "okay danke", "tschüss", "bye", "ciao"
        ]

        while conversation_active:
            CURRENT_STATE = "LISTEN"

            # Beim ersten Mal: Hey-BMO Sound, danach direkt zuhören (kein Reply-Sound)
            if is_first_interaction:
                play_random_sound(HEYBMO_DIR)
                is_first_interaction = False

            with sr.Microphone() as source:
                try:
                    print(f"Höre zu... (Pause nach {PAUSE_THRESHOLD}s Stille)")
                    audio_input = recognizer.listen(
                        source,
                        timeout=LISTEN_TIMEOUT
                    )
                    user_text = transcribe(audio_input)
                    print(f"User: {user_text}")

                    # Leere Erkennung ignorieren → nochmal zuhören
                    if not user_text:
                        print("[INFO] Nichts erkannt, nochmal zuhören...")
                        continue

                    CURRENT_STATE = "THINK"
                    play_random_sound(DENKEN_DIR)

                    response = ollama.chat(model='llama3', messages=[
                        {'role': 'system', 'content': BASE_SYSTEM_PROMPT},
                        {'role': 'user',   'content': user_text},
                    ])

                    content = response['message']['content']
                    skip_followup = False  # ← nach Spotify kein Followup

                    if "{" in content and "action" in content:
                        try:
                            start    = content.find('{')
                            end      = content.rfind('}') + 1
                            json_str = content[start:end]
                            data     = json.loads(json_str)

                            if data.get("action") == "get_time":
                                speak_bmo(f"Es ist jetzt {get_bmo_time()} Uhr!", tts)
                            elif data.get("action") == "get_joke":
                                speak_bmo(get_bmo_joke(), tts)
                            elif data.get("action") == "get_news":
                                speak_bmo(get_bmo_news(), tts)
                            elif data.get("action") == "get_status":
                                speak_bmo(get_bmo_status(), tts)
                            elif data.get("action") == "get_weather":
                                ort = data.get("location", "Berlin")
                                speak_bmo(f"In {ort} ist es aktuell {get_weather(ort)}.", tts)
                            elif data.get("action") == "shutdown_pc":
                                speak_bmo("Okay, ich fahre jetzt herunter. Tschüss!", tts)
                                shutdown_pc()
                            elif data.get("action") == "spotify_play":
                                query = data.get("query", "")
                                speak_bmo(spotify_play(query), tts)
                                skip_followup = True  # ← kein Followup nach Musik
                            elif data.get("action") == "spotify_pause":
                                speak_bmo(spotify_pause(), tts)
                                skip_followup = True
                            elif data.get("action") == "spotify_resume":
                                speak_bmo(spotify_resume(), tts)
                                skip_followup = True
                            elif data.get("action") == "spotify_next":
                                speak_bmo(spotify_next(), tts)
                                skip_followup = True
                        except:
                            speak_bmo(content, tts)
                    else:
                        speak_bmo(content, tts)

                    # ── FOLLOWUP: BMO fragt ob noch was ist ──────────────
                    if skip_followup:
                        # Nach Spotify direkt in Standby
                        print("Spotify Aktion → kein Followup, Standby...")
                        conversation_active = False
                        CURRENT_STATE = "IDLE"
                        continue

                    CURRENT_STATE = "LISTEN"
                    play_random_sound(REPLY_DIR, wait=True)

                    try:
                        with sr.Microphone() as followup_source:
                            print("Warte auf Followup...")
                            followup_audio = recognizer.listen(
                                followup_source,
                                timeout=5,           # 5s warten auf ersten Ton
                                phrase_time_limit=4  # max 4s Antwort
                            )
                            followup_text = transcribe(followup_audio).lower()
                            print(f"Followup: {followup_text}")

                            # Prüfen ob einer der Abbruch-Wörter enthalten ist
                            if any(wort in followup_text for wort in ABBRUCH_WOERTER):
                                print("Abbruch erkannt → Standby")
                                conversation_active = False
                            else:
                                # Normale Weiterführung — Text wird im nächsten
                                # Loop-Durchlauf als neue Frage verarbeitet
                                # Dafür setzen wir user_text auf followup_text
                                # und springen direkt zur Verarbeitung
                                CURRENT_STATE = "THINK"
                                play_random_sound(DENKEN_DIR)

                                response2 = ollama.chat(model='llama3', messages=[
                                    {'role': 'system', 'content': BASE_SYSTEM_PROMPT},
                                    {'role': 'user',   'content': followup_text},
                                ])
                                content2 = response2['message']['content']
                                if "{" in content2 and "action" in content2:
                                    try:
                                        start    = content2.find('{')
                                        end      = content2.rfind('}') + 1
                                        data2    = json.loads(content2[start:end])
                                        if data2.get("action") == "get_time":
                                            speak_bmo(f"Es ist jetzt {get_bmo_time()} Uhr!", tts)
                                        elif data2.get("action") == "get_joke":
                                            speak_bmo(get_bmo_joke(), tts)
                                        elif data2.get("action") == "get_news":
                                            speak_bmo(get_bmo_news(), tts)
                                        elif data2.get("action") == "get_status":
                                            speak_bmo(get_bmo_status(), tts)
                                        elif data2.get("action") == "get_weather":
                                            ort = data2.get("location", "Berlin")
                                            speak_bmo(f"In {ort} ist es aktuell {get_weather(ort)}.", tts)
                                        elif data2.get("action") == "shutdown_pc":
                                            speak_bmo("Okay, ich fahre jetzt herunter. Tschüss!", tts)
                                            shutdown_pc()
                                        elif data2.get("action") == "spotify_play":
                                            speak_bmo(spotify_play(data2.get("query", "")), tts)
                                        elif data2.get("action") == "spotify_pause":
                                            speak_bmo(spotify_pause(), tts)
                                        elif data2.get("action") == "spotify_resume":
                                            speak_bmo(spotify_resume(), tts)
                                        elif data2.get("action") == "spotify_next":
                                            speak_bmo(spotify_next(), tts)
                                    except:
                                        speak_bmo(content2, tts)
                                else:
                                    speak_bmo(content2, tts)

                    except (sr.WaitTimeoutError, sr.UnknownValueError):
                        # Keine Antwort auf Followup → Standby
                        print("Keine Followup-Antwort → Standby")
                        conversation_active = False
                    # ─────────────────────────────────────────────────────

                    CURRENT_STATE = "IDLE"

                except (sr.WaitTimeoutError, sr.UnknownValueError):
                    print("Kein Input → Standby...")
                    conversation_active = False
                except Exception as e:
                    print(f"Abbruch: {e}")
                    conversation_active = False

        CURRENT_STATE = "IDLE"
        print("[FERTIG] Zurück im Wake-Word-Modus.")

if __name__ == "__main__":
    main()
