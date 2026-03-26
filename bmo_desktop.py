"""
BMO Desktop KI (v2 — Core-Version)
=====================================
Starten: python bmo_desktop.py
Voraussetzung: bmo_core.py muss laufen (http://localhost:6000)

Was dieses Script macht:
  - Wake-Word Erkennung (openWakeWord)
  - Mikrofon-Aufnahme (SpeechRecognition)
  - Pygame GUI (Gesichtsanimation)
  - Boot/Denken/Reply-Sounds
  - Alles andere → bmo_core.py

Was bmo_core.py macht:
  - Whisper Transkription
  - Ollama (LLM)
  - TTS / RVC Stimme
  - Alle Aktionen (Wetter, Spotify, Shutdown...)
"""

import os
import numpy as np
import sounddevice as sd
from openwakeword.model import Model
import speech_recognition as sr
import pygame
import random
import time
import threading
import datetime
import requests as req
import base64
import soundfile as sf
import tempfile
import ssl

# Global die SSL-Prüfung ausschalten
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context


# ══════════════════════════════════════════════════════════════════
# KONFIGURATION
# ══════════════════════════════════════════════════════════════════

CORE_URL        = "http://localhost:6000"

WAKE_WORD_MODEL = "hey_bmo.onnx"

VOICE_VOLUME    = 0.2   # Lautstärke der BMO-Stimme (0.0 = stumm, 1.0 = max)
SOUNDS_VOLUME   = 0.2   # Lautstärke der vorgenerierten Sound-Lines

# ┌─────────────────────────────────────────────────────────────────┐
# │  WAKE-WORD EINSTELLUNGEN                                        │
# │  WAKE_THRESHOLD:    0.5 = empfindlicher, 0.7 = strenger         │
# │  WAKE_VOTES_NEEDED: 1 = sofort, 2 = empfohlen, 3 = sehr sicher  │
# └─────────────────────────────────────────────────────────────────┘
WAKE_THRESHOLD    = 0.5
WAKE_VOTES_NEEDED = 1

# ┌─────────────────────────────────────────────────────────────────┐
# │  AUFNAHME EINSTELLUNGEN                                         │
# │  LISTEN_TIMEOUT:  Sekunden warten auf ersten Ton                │
# │  PAUSE_THRESHOLD: Sekunden Stille = Satz zu Ende                │
# └─────────────────────────────────────────────────────────────────┘
LISTEN_TIMEOUT  = 4
PAUSE_THRESHOLD = 1.5

# Sound-Verzeichnisse
SOUNDS_BASE  = "sounds"
BOOT_DIR     = os.path.join(SOUNDS_BASE, "boot")
DENKEN_DIR   = os.path.join(SOUNDS_BASE, "denken")
HEYBMO_DIR   = os.path.join(SOUNDS_BASE, "heybmo")
REPLY_DIR    = os.path.join(SOUNDS_BASE, "reply")
SHUTDOWN_DIR = os.path.join(SOUNDS_BASE, "shutdown")

# Bilder-Verzeichnisse
FACES_BASE = "faces"
FACE_DIRS  = {
    "BOOT":   os.path.join(FACES_BASE, "boot"),
    "IDLE":   os.path.join(FACES_BASE, "idle"),
    "LISTEN": os.path.join(FACES_BASE, "hören"),
    "THINK":  os.path.join(FACES_BASE, "denken"),
    "SPEAK":  os.path.join(FACES_BASE, "reden")
}

# Wörter die Konversation beenden
ABBRUCH_WOERTER = [
    "ne", "nein", "nö", "pass", "danke", "reicht",
    "war alles", "das war alles", "nichts", "nichts mehr",
    "kein", "okay danke", "tschüss", "bye", "ciao"
]

# Globaler Zustand
CURRENT_STATE = "BOOT"


# ══════════════════════════════════════════════════════════════════
# CORE-VERBINDUNG
# ══════════════════════════════════════════════════════════════════

def core_health():
    """Prüft ob der Core erreichbar ist."""
    try:
        r = req.get(f"{CORE_URL}/ping", timeout=2)
        return r.status_code == 200
    except:
        return False

def core_process(text):
    """
    Schickt Text an den Core, holt Antwort + TTS-Audio via /speak.
    Gibt (antwort_text, audio_b64_oder_None, action_oder_None) zurück.

    Ablauf:
      1. POST /process  → response + action
      2. POST /speak    → WAV als base64 (RVC-TTS)
    """
    try:
        r = req.post(
            f"{CORE_URL}/process",
            json={"message": text},
            timeout=60
        )
        d = r.json()
        response_text = d.get("response", "")
        action        = d.get("action")
    except Exception as e:
        print(f"[FEHLER] Core /process nicht erreichbar: {e}")
        return "Ich kann den Core gerade nicht erreichen.", None, None

    # TTS: Antworttext in Audio umwandeln
    audio_b64 = None
    if response_text:
        try:
            rs = req.post(
                f"{CORE_URL}/speak",
                json={"text": response_text},
                timeout=120  # Beim ersten Aufruf lädt RVC ~30s
            )
            audio_b64 = rs.json().get("audio")
            if not audio_b64:
                print(f"[WARN] /speak lieferte kein Audio: {rs.json().get('error', '?')}")
        except Exception as e:
            print(f"[WARN] Core /speak nicht erreichbar: {e}")

    return response_text, audio_b64, action

def core_transcribe(audio_data):
    """
    Schickt sr.AudioData an den Core-Transcribe-Endpoint.
    Gibt erkannten Text zurück.
    """
    try:
        # AudioData → WAV-Bytes → Base64
        wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
        b64 = base64.b64encode(wav_bytes).decode('utf-8')

        r = req.post(
            f"{CORE_URL}/transcribe",
            json={"audio": b64, "format": "wav"},
            timeout=120  # Whisper braucht beim ersten Aufruf länger zum Laden
        )
        return r.json().get("transcript", "")
    except Exception as e:
        print(f"[FEHLER] Transkription fehlgeschlagen: {e}")
        return ""


# ══════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ══════════════════════════════════════════════════════════════════

def get_files(directory, extensions):
    if os.path.exists(directory):
        return [os.path.join(directory, f)
                for f in os.listdir(directory)
                if f.lower().endswith(extensions)]
    return []

def load_face_images():
    images = {}
    for state, path in FACE_DIRS.items():
        imgs = get_files(path, ('.png', '.jpg', '.jpeg'))
        images[state] = [pygame.image.load(i) for i in imgs]
    return images


# ══════════════════════════════════════════════════════════════════
# GRAFIK-THREAD (Pygame GUI)
# ══════════════════════════════════════════════════════════════════

def bmo_face_thread():
    global CURRENT_STATE
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    pygame.display.set_caption("BMO OS")

    face_dict   = load_face_images()
    clock       = pygame.time.Clock()
    last_state  = None
    current_img = None
    next_switch = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

        now = pygame.time.get_ticks()

        # Sofort-Wechsel wenn Modus wechselt
        if CURRENT_STATE != last_state:
            available = face_dict.get(CURRENT_STATE, [])
            if available:
                current_img = random.choice(available)
            last_state  = CURRENT_STATE
            next_switch = now + 2000

        # Animation: THINK
        elif CURRENT_STATE == "THINK":
            if now > next_switch:
                available = face_dict.get("THINK", [])
                if available:
                    current_img = random.choice(available)
                next_switch = now + 1000

        # Animation: SPEAK
        elif CURRENT_STATE == "SPEAK":
            if now > next_switch:
                available = face_dict.get("SPEAK", [])
                if available:
                    current_img = random.choice(available)
                next_switch = now + 50

        screen.fill((43, 135, 115))
        if current_img:
            rect = current_img.get_rect(center=(400, 240))
            screen.blit(current_img, rect)

        pygame.display.flip()
        clock.tick(30)


# ══════════════════════════════════════════════════════════════════
# AUDIO-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════

def play_random_sound(directory, wait=False):
    sounds = get_files(directory, ".wav")
    if not sounds:
        return
    pygame.mixer.music.stop()
    pygame.mixer.music.unload()
    wahl = random.choice(sounds)
    pygame.mixer.music.load(wahl)
    pygame.mixer.music.set_volume(SOUNDS_VOLUME)
    pygame.mixer.music.play()
    if wait:
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

def speak_bmo(text, audio_b64=None):
    """
    Spielt BMO-Stimme ab.
    - Falls audio_b64 übergeben: direkt abspielen (vom Core generiert)
    - Falls None: Text als Fallback ausgeben (Core hat kein TTS)
    """
    global CURRENT_STATE

    if not audio_b64:
        # Kein Audio vom Core → trotzdem Zustand wechseln und Text ausgeben
        print(f"[BMO] {text}")
        CURRENT_STATE = "SPEAK"
        time.sleep(max(1.0, len(text) * 0.04))  # grobe Wartezeit
        CURRENT_STATE = "IDLE"
        return

    # Base64-WAV → temp Datei → pygame abspielen
    try:
        wav_bytes = base64.b64decode(audio_b64)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        CURRENT_STATE = "SPEAK"
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.set_volume(VOICE_VOLUME)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        CURRENT_STATE = "IDLE"

        try:
            os.remove(tmp_path)
        except:
            pass

    except Exception as e:
        print(f"[WARN] Audio-Wiedergabe fehlgeschlagen: {e}")
        print(f"[BMO] {text}")
        CURRENT_STATE = "IDLE"


# ══════════════════════════════════════════════════════════════════
# HAUPTPROGRAMM
# ══════════════════════════════════════════════════════════════════

def main():
    global CURRENT_STATE

    # ── Core-Check ────────────────────────────────────────────────
    print("Prüfe BMO Core...")
    if not core_health():
        print("❌ BMO Core nicht erreichbar! Bitte bmo_core.py starten.")
        print("   Warte 10 Sekunden und versuche es erneut...")
        time.sleep(10)
        if not core_health():
            print("❌ Core immer noch nicht erreichbar. Beende.")
            return
    print("✅ BMO Core verbunden!")

    # ── Grafik starten ────────────────────────────────────────────
    threading.Thread(target=bmo_face_thread, daemon=True).start()

    # ── Systeme initialisieren ────────────────────────────────────
    print("Initialisiere Systeme...")
    pygame.mixer.init()

    recognizer = sr.Recognizer()
    recognizer.pause_threshold       = PAUSE_THRESHOLD
    recognizer.non_speaking_duration = PAUSE_THRESHOLD

    oww_model = Model(wakeword_models=[WAKE_WORD_MODEL])

    # ── Boot-Vorgang ──────────────────────────────────────────────
    CURRENT_STATE = "BOOT"
    play_random_sound(BOOT_DIR, wait=True)
    CURRENT_STATE = "IDLE"

    # ══════════════════════════════════════════════════════════════
    # HAUPTSCHLEIFE
    # ══════════════════════════════════════════════════════════════
    while True:

        # ── SCHRITT 1: STANDBY — Wake-Word ────────────────────────
        with sd.InputStream(samplerate=16000, channels=1, dtype='int16') as stream:
            print(f"\n[STBY] Warte auf Wake-Word "
                  f"(Threshold={WAKE_THRESHOLD}, Votes={WAKE_VOTES_NEEDED})...")
            oww_model.reset()
            wake_detected = False
            vote_counter  = 0

            while not wake_detected:
                audio_chunk, _ = stream.read(1280)
                audio_chunk = np.frombuffer(audio_chunk, dtype=np.int16)
                oww_model.predict(audio_chunk)

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
                    vote_counter = 0

        # ── SCHRITT 2: AKTIV-MODUS ────────────────────────────────
        conversation_active  = True
        is_first_interaction = True

        while conversation_active:
            CURRENT_STATE = "LISTEN"

            # Erstes Mal: Hey-BMO Sound
            if is_first_interaction:
                play_random_sound(HEYBMO_DIR)
                is_first_interaction = False

            # ── Aufnahme ──────────────────────────────────────────
            with sr.Microphone() as source:
                try:
                    print(f"Höre zu... (Pause nach {PAUSE_THRESHOLD}s Stille)")
                    audio_input = recognizer.listen(
                        source,
                        timeout=LISTEN_TIMEOUT
                    )
                except (sr.WaitTimeoutError, sr.UnknownValueError):
                    print("Kein Input → Standby...")
                    conversation_active = False
                    continue
                except Exception as e:
                    print(f"Aufnahme-Fehler: {e}")
                    conversation_active = False
                    continue

            # ── Transkription via Core ─────────────────────────────
            CURRENT_STATE = "THINK"
            play_random_sound(DENKEN_DIR)

            user_text = core_transcribe(audio_input)
            print(f"User: {user_text}")

            if not user_text:
                print("[INFO] Nichts erkannt, nochmal zuhören...")
                CURRENT_STATE = "LISTEN"
                continue

            # ── Verarbeitung via Core ──────────────────────────────
            # FIX: core_process() verwendet jetzt "message" als Key
            response_text, audio_b64, action = core_process(user_text)
            print(f"BMO: {response_text}")

            speak_bmo(response_text, audio_b64)

            # ── Followup nach Spotify-Aktion: direkt Standby ──────
            if action in ("spotify_play", "spotify_pause", "spotify_resume", "spotify_next"):
                print("Spotify Aktion → kein Followup, Standby...")
                conversation_active = False
                CURRENT_STATE = "IDLE"
                continue

            # ── Shutdown: Shutdown-Sound spielen ──────────────────
            if action == "shutdown_pc":
                play_random_sound(SHUTDOWN_DIR, wait=True)
                conversation_active = False
                CURRENT_STATE = "IDLE"
                break

            # ── FOLLOWUP: BMO fragt ob noch was ist ───────────────
            CURRENT_STATE = "LISTEN"
            play_random_sound(REPLY_DIR, wait=True)

            try:
                with sr.Microphone() as followup_source:
                    print("Warte auf Followup...")
                    followup_audio = recognizer.listen(
                        followup_source,
                        timeout=5,
                        phrase_time_limit=4
                    )
                    followup_text = core_transcribe(followup_audio).lower()
                    print(f"Followup: {followup_text}")

                    if any(wort in followup_text for wort in ABBRUCH_WOERTER):
                        print("Abbruch erkannt → Standby")
                        conversation_active = False
                    else:
                        # Followup-Text direkt verarbeiten
                        CURRENT_STATE = "THINK"
                        play_random_sound(DENKEN_DIR)
                        response_text2, audio_b64_2, action2 = core_process(followup_text)
                        print(f"BMO: {response_text2}")
                        speak_bmo(response_text2, audio_b64_2)

                        if action2 == "shutdown_pc":
                            play_random_sound(SHUTDOWN_DIR, wait=True)
                            conversation_active = False

            except (sr.WaitTimeoutError, sr.UnknownValueError):
                print("Keine Followup-Antwort → Standby")
                conversation_active = False

            CURRENT_STATE = "IDLE"

        CURRENT_STATE = "IDLE"
        print("[FERTIG] Zurück im Wake-Word-Modus.")


if __name__ == "__main__":
    main()