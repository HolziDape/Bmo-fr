"""
BMO Wakeword Trainer
====================
Generiert synthetische "Hey BMO" Trainingsdaten und trainiert ein .onnx Modell.
Einfach starten mit: python train_wakeword.py
"""

import os
import json
import random
import numpy as np
import torch
from scipy.io import wavfile
from scipy.signal import resample
from pathlib import Path

# ── KONFIGURATION ──────────────────────────────────────────────────────────────
WAKEWORD        = "Hey BMO"
OUTPUT_MODEL    = "hey_bmo.onnx"
SAMPLE_RATE     = 16000
N_SAMPLES       = 500       # Anzahl synthetischer Positiv-Beispiele
N_NEG_SAMPLES   = 1000      # Anzahl Negativ-Beispiele (anderer Text)
TRAIN_DIR       = "wakeword_training"
# ──────────────────────────────────────────────────────────────────────────────

# Negative Beispiele — Sätze die NICHT das Wakeword sind
NEGATIVE_PHRASES = [
    "Guten Morgen", "Wie geht es dir", "Was ist das Wetter",
    "Spiel Musik ab", "Wie spät ist es", "Hallo wie geht es",
    "Danke schön", "Auf Wiedersehen", "Ich brauche Hilfe",
    "Was kannst du machen", "Erzähl mir einen Witz",
    "Wie ist das Wetter heute", "Mach das Licht an",
    "Stell einen Timer", "Erinner mich daran",
    "OK Computer", "Hey Siri", "Alexa", "OK Google",
    "Hallo Computer", "Guten Tag", "Tschüss",
    "Kannst du mir helfen", "Ich habe eine Frage",
    "Was ist die Zeit", "Wie warm ist es draußen",
]

def setup_dirs():
    os.makedirs(f"{TRAIN_DIR}/positive", exist_ok=True)
    os.makedirs(f"{TRAIN_DIR}/negative", exist_ok=True)
    print(f"✓ Ordner erstellt: {TRAIN_DIR}/")

def generate_audio_tts(text, filepath, voice_variation=0):
    """Generiert Audio mit Windows TTS (kein Internet nötig)."""
    import subprocess

    # Absoluten Pfad sicherstellen
    filepath_abs = os.path.abspath(filepath)
    filepath_ps  = filepath_abs.replace("\\", "\\\\")

    voices = [
        "Microsoft Hedda Desktop",
        "Microsoft Stefan Desktop",
        "Microsoft Zira Desktop",
        "Microsoft David Desktop",
    ]

    rate  = random.randint(-3, 3)
    voice = voices[voice_variation % len(voices)]

    ps_script = f"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{ $synth.SelectVoice('{voice}') }} catch {{ }}
$synth.Rate = {rate}
$synth.SetOutputToWaveFile('{filepath_ps}')
$synth.Speak('{text}')
$synth.Dispose()
"""
    subprocess.run(
        ["powershell", "-Command", ps_script],
        capture_output=True, timeout=15
    )
    return os.path.exists(filepath_abs)

def add_noise(waveform, noise_level=0.005):
    """Fügt leichtes Rauschen hinzu."""
    noise = torch.randn_like(waveform) * noise_level
    return waveform + noise

def change_speed(waveform, sr, factor):
    """Ändert die Geschwindigkeit."""
    effects = [["rate", str(int(sr * factor))]]
    try:
        waveform, _ = torchaudio.sox_effects.apply_effects_tensor(waveform, sr, effects)
    except:
        pass
    return waveform

def generate_training_data():
    print(f"\n{'='*50}")
    print(f"  Generiere Trainingsdaten für: '{WAKEWORD}'")
    print(f"{'='*50}\n")

    # ── POSITIV-BEISPIELE ────────────────────────────────────────────
    print(f"[1/3] Generiere {N_SAMPLES} Positiv-Beispiele...")
    success = 0

    # Variationen des Wakewords
    variations = [
        "Hey BMO",
        "Hey B M O",
        "Hey Bimo",   # häufige Aussprache
        "Hey Bi Mo",
        "Hey BMO!",
    ]

    for i in range(N_SAMPLES):
        text     = random.choice(variations)
        filepath = f"{TRAIN_DIR}/positive/pos_{i:04d}.wav"
        voice_v  = i % 4

        if generate_audio_tts(text, filepath, voice_v):
            success += 1

        if (i + 1) % 50 == 0:
            print(f"  → {i+1}/{N_SAMPLES} ({success} erfolgreich)")

    print(f"  ✓ {success} Positiv-Beispiele generiert")

    # ── NEGATIV-BEISPIELE ────────────────────────────────────────────
    print(f"\n[2/3] Generiere {N_NEG_SAMPLES} Negativ-Beispiele...")
    neg_success = 0

    for i in range(N_NEG_SAMPLES):
        text     = random.choice(NEGATIVE_PHRASES)
        filepath = f"{TRAIN_DIR}/negative/neg_{i:04d}.wav"
        voice_v  = i % 4

        if generate_audio_tts(text, filepath, voice_v):
            neg_success += 1

        if (i + 1) % 100 == 0:
            print(f"  → {i+1}/{N_NEG_SAMPLES} ({neg_success} erfolgreich)")

    print(f"  ✓ {neg_success} Negativ-Beispiele generiert")
    return success, neg_success

def extract_features(wav_path, n_mels=40):
    """Extrahiert Mel-Spektrogramm Features mit scipy statt torchaudio."""
    try:
        sr, wav = wavfile.read(wav_path)

        # Stereo → Mono
        if len(wav.shape) > 1:
            wav = wav.mean(axis=1)

        # Int → Float
        wav = wav.astype(np.float32)
        if wav.dtype == np.float32 and wav.max() > 1.0:
            wav = wav / 32768.0

        # Resample auf 16000 Hz
        if sr != SAMPLE_RATE:
            target_len = int(len(wav) * SAMPLE_RATE / sr)
            wav = resample(wav, target_len)

        # Mel-Spektrogramm manuell berechnen
        n_fft    = 512
        hop      = 160
        frames   = []
        window   = np.hanning(n_fft)

        for i in range(0, max(1, len(wav) - n_fft), hop):
            frame = wav[i:i+n_fft]
            if len(frame) < n_fft:
                frame = np.pad(frame, (0, n_fft - len(frame)))
            spectrum = np.abs(np.fft.rfft(frame * window))
            frames.append(spectrum)

        if not frames:
            return None

        spec = np.array(frames).T  # [freq, time]

        # Mel-Filterbank
        freqs    = np.fft.rfftfreq(n_fft, 1.0/SAMPLE_RATE)
        mel_min  = 2595 * np.log10(1 + 20/700)
        mel_max  = 2595 * np.log10(1 + (SAMPLE_RATE/2)/700)
        mel_pts  = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_pts   = 700 * (10**(mel_pts/2595) - 1)
        bin_pts  = np.floor((n_fft+1) * hz_pts / SAMPLE_RATE).astype(int)

        fbank = np.zeros((n_mels, spec.shape[0]))
        for m in range(1, n_mels+1):
            f_m_minus = bin_pts[m-1]
            f_m       = bin_pts[m]
            f_m_plus  = bin_pts[m+1]
            for k in range(f_m_minus, f_m):
                if f_m != f_m_minus:
                    fbank[m-1, k] = (k - f_m_minus) / (f_m - f_m_minus)
            for k in range(f_m, f_m_plus):
                if f_m_plus != f_m:
                    fbank[m-1, k] = (f_m_plus - k) / (f_m_plus - f_m)

        mel_spec = np.dot(fbank, spec)
        mel_spec = 10 * np.log10(mel_spec + 1e-10)  # dB

        # Auf feste Länge bringen (300 Frames)
        target_len = 300
        if mel_spec.shape[1] < target_len:
            mel_spec = np.pad(mel_spec, ((0,0),(0, target_len - mel_spec.shape[1])))
        else:
            mel_spec = mel_spec[:, :target_len]

        return torch.tensor(mel_spec, dtype=torch.float32)

    except Exception as e:
        print(f"  [WARN] Feature-Fehler bei {wav_path}: {e}")
        return None

class WakeWordModel(torch.nn.Module):
    def __init__(self, n_mels=40):
        super().__init__()
        self.conv = torch.nn.Sequential(
            torch.nn.Conv2d(1, 32, kernel_size=3, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(2),
            torch.nn.Conv2d(32, 64, kernel_size=3, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(2),
            torch.nn.Conv2d(64, 128, kernel_size=3, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(2),
        )
        # Größe automatisch berechnen
        dummy = torch.zeros(1, 1, n_mels, 300)
        conv_out = self.conv(dummy)
        flat_size = conv_out.view(1, -1).shape[1]

        self.fc = torch.nn.Sequential(
            torch.nn.Flatten(),
            torch.nn.Linear(flat_size, 256),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.3),
            torch.nn.Linear(256, 1),
            torch.nn.Sigmoid()
        )

    def forward(self, x):
        x = x.unsqueeze(1)
        x = self.conv(x)
        return self.fc(x)

    def forward(self, x):
        x = x.unsqueeze(1)  # [B, 1, n_mels, time]
        x = self.conv(x)
        return self.fc(x)

def train_model():
    print(f"\n[3/3] Lade Features und trainiere Modell...")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if str(device) == "cpu":
        print("  ⚠️  Kein CUDA gefunden — Training läuft auf CPU (dauert länger)")
    else:
        print(f"  ✓ GPU erkannt: {torch.cuda.get_device_name(0)}")

    # Features laden
    X, y = [], []

    pos_files = list(Path(f"{TRAIN_DIR}/positive").glob("*.wav"))
    neg_files = list(Path(f"{TRAIN_DIR}/negative").glob("*.wav"))

    print(f"  Positiv: {len(pos_files)} Dateien")
    print(f"  Negativ: {len(neg_files)} Dateien")

    for f in pos_files:
        feat = extract_features(str(f))
        if feat is not None:
            X.append(feat)
            y.append(1.0)

    for f in neg_files:
        feat = extract_features(str(f))
        if feat is not None:
            X.append(feat)
            y.append(0.0)

    if len(X) < 10:
        print("❌ Zu wenig Trainingsdaten! Bitte zuerst generate_training_data() ausführen.")
        return

    X = torch.stack(X)
    y = torch.tensor(y).unsqueeze(1)

    # Shuffle
    idx = torch.randperm(len(X))
    X, y = X[idx], y[idx]

    # Train/Val Split
    split    = int(0.8 * len(X))
    X_train  = X[:split].to(device)
    y_train  = y[:split].to(device)
    X_val    = X[split:].to(device)
    y_val    = y[split:].to(device)

    model     = WakeWordModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.0001, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    criterion = torch.nn.BCELoss()

    print(f"\n  Training startet ({split} Train, {len(X)-split} Val)...")
    best_val  = float('inf')

    for epoch in range(50):
        model.train()
        # Mini-batches
        batch_size = 32
        losses = []
        for i in range(0, len(X_train), batch_size):
            xb = X_train[i:i+batch_size]
            yb = y_train[i:i+batch_size]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())

        # Validation
        model.eval()
        with torch.no_grad():
            val_pred = model(X_val)
            val_loss = criterion(val_pred, y_val).item()
            val_acc  = ((val_pred > 0.5).float() == y_val).float().mean().item()

        avg_loss = sum(losses) / len(losses)

        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch+1:3d}/50 | Loss: {avg_loss:.4f} | Val Loss: {val_loss:.4f} | Val Acc: {val_acc*100:.1f}%")

        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), "best_wakeword.pt")

        scheduler.step(val_loss)

    # Bestes Modell laden und als ONNX exportieren
    print(f"\n  Exportiere als ONNX: {OUTPUT_MODEL}")
    model.load_state_dict(torch.load("best_wakeword.pt"))
    model.eval()
    model.cpu()

    dummy = torch.zeros(1, 40, 300)
    torch.onnx.export(
        model, dummy, OUTPUT_MODEL,
        input_names=["input"],
        output_names=["output"],
        opset_version=11
    )

    if os.path.exists(OUTPUT_MODEL):
        print(f"\n{'='*50}")
        print(f"  ✅ Fertig! Modell gespeichert: {OUTPUT_MODEL}")
        print(f"  → Ersetze 'wakeword.onnx' in BMO durch '{OUTPUT_MODEL}'")
        print(f"  → Oder ändere WAKE_WORD_MODEL = '{OUTPUT_MODEL}' in der Config")
        print(f"{'='*50}\n")
    else:
        print("❌ Export fehlgeschlagen.")

if __name__ == "__main__":
    print("\n🤖 BMO Wakeword Trainer")
    print(f"   Wort: '{WAKEWORD}'")
    print(f"   Ausgabe: {OUTPUT_MODEL}\n")

    setup_dirs()

    # Prüfen ob bereits Daten vorhanden
    pos_existing = list(Path(f"{TRAIN_DIR}/positive").glob("*.wav"))
    neg_existing = list(Path(f"{TRAIN_DIR}/negative").glob("*.wav"))

    if len(pos_existing) > 10 and len(neg_existing) > 10:
        print(f"✓ Bereits {len(pos_existing)} Positiv- und {len(neg_existing)} Negativ-Beispiele gefunden!")
        print("  Überspringe Generierung und starte direkt mit Training...\n")
        train_model()
    else:
        pos, neg = generate_training_data()
        if pos > 10 and neg > 10:
            train_model()
        else:
            print("❌ Zu wenig Daten generiert.")