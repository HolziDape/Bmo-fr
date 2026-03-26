"""
BMO Wakeword Trainer — openWakeWord-kompatibel
===============================================
Trainiert ein "Hey BMO" Modell das direkt mit openWakeWord funktioniert.
Verwendung: python train_wakeword.py

Warum dieser Ansatz?
  openWakeWord erwartet ONNX-Modelle die auf seinen internen Embeddings
  arbeiten — nicht auf rohen Mel-Spektrogrammen. Dieser Trainer nutzt
  genau diese Embeddings als Features.

  Pipeline:
    Audio → openWakeWord Embedding-Modell → [N, 96] → Fenster [16, 96]
          → GRU-Klassifikator → Score (0–1)
"""

import os
import random
import subprocess
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from scipy.io import wavfile
from scipy.signal import resample

# Alle Pfade relativ zum Skript-Ordner (unabhängig vom Arbeitsverzeichnis)
SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(SCRIPT_DIR)

# ── KONFIGURATION ────────────────────────────────────────────────────────────
WAKEWORD      = "Hey BMO"
OUTPUT_MODEL  = str(SCRIPT_DIR / "hey_bmo.onnx")
SAMPLE_RATE   = 16000
N_SAMPLES     = 500       # Positiv-Beispiele
N_NEG_SAMPLES = 1000      # Negativ-Beispiele
TRAIN_DIR     = str(SCRIPT_DIR / "wakeword_training")
N_CONTEXT     = 16        # Embedding-Fenster (openWakeWord Standard: 16 × 80ms = 1.28s)
N_FEATURES    = 96        # Embedding-Dimension (openWakeWord Standard)
EPOCHS        = 100
BATCH_SIZE    = 64
# ─────────────────────────────────────────────────────────────────────────────

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
    "Bitte hilf mir", "Kannst du das machen",
    "Was machst du gerade", "Erzähl mir mehr",
    "Ich verstehe das nicht", "Kannst du wiederholen",
]

WAKEWORD_VARIATIONS = [
    "Hey BMO",
    "Hey B M O",
    "Hey Bimo",
    "Hey Bi Mo",
    "Hey BMO!",
    "Hey BMO, hörst du mich",
    "Hey BMO kannst du mir helfen",
    "Hey BMO bitte",
]


def setup_dirs():
    os.makedirs(f"{TRAIN_DIR}/positive", exist_ok=True)
    os.makedirs(f"{TRAIN_DIR}/negative", exist_ok=True)
    print(f"✓ Ordner erstellt: {TRAIN_DIR}/")


def generate_audio_tts(text, filepath, voice_variation=0):
    """Generiert Audio mit Windows TTS (kein Internet nötig)."""
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
    subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=15)
    return os.path.exists(filepath_abs)


def generate_training_data():
    print(f"\n{'='*50}")
    print(f"  Generiere Trainingsdaten für: '{WAKEWORD}'")
    print(f"{'='*50}\n")

    print(f"[1/3] Generiere {N_SAMPLES} Positiv-Beispiele...")
    success = 0
    for i in range(N_SAMPLES):
        text     = random.choice(WAKEWORD_VARIATIONS)
        filepath = f"{TRAIN_DIR}/positive/pos_{i:04d}.wav"
        if generate_audio_tts(text, filepath, i % 4):
            success += 1
        if (i + 1) % 50 == 0:
            print(f"  → {i+1}/{N_SAMPLES} ({success} erfolgreich)")
    print(f"  ✓ {success} Positiv-Beispiele generiert")

    print(f"\n[2/3] Generiere {N_NEG_SAMPLES} Negativ-Beispiele...")
    neg_success = 0
    for i in range(N_NEG_SAMPLES):
        text     = random.choice(NEGATIVE_PHRASES)
        filepath = f"{TRAIN_DIR}/negative/neg_{i:04d}.wav"
        if generate_audio_tts(text, filepath, i % 4):
            neg_success += 1
        if (i + 1) % 100 == 0:
            print(f"  → {i+1}/{N_NEG_SAMPLES} ({neg_success} erfolgreich)")
    print(f"  ✓ {neg_success} Negativ-Beispiele generiert")
    return success, neg_success


def load_audio_padded(wav_path, min_seconds=2.5):
    """
    Lädt WAV als float32 bei 16kHz.
    Padded mit Stille am Anfang damit mindestens N_CONTEXT Embedding-Frames
    entstehen (openWakeWord braucht ~80ms pro Frame).
    """
    sr, wav = wavfile.read(str(wav_path))
    if len(wav.shape) > 1:
        wav = wav.mean(axis=1)
    wav = wav.astype(np.float32)
    if wav.max() > 1.0:
        wav = wav / 32768.0
    if sr != SAMPLE_RATE:
        target_len = int(len(wav) * SAMPLE_RATE / sr)
        wav = resample(wav, target_len)

    # Sicherstellen dass genug Audio für mindestens N_CONTEXT Frames vorhanden ist
    min_samples = int(min_seconds * SAMPLE_RATE)
    if len(wav) < min_samples:
        pad = np.zeros(min_samples - len(wav), dtype=np.float32)
        wav = np.concatenate([pad, wav])  # Stille VOR dem Wakeword

    return wav


def load_clips_as_int16(wav_files, clip_samples):
    """
    Lädt eine Liste von WAV-Dateien als int16-Array [n_clips, clip_samples].
    Kürzere Clips werden am Anfang mit Stille aufgefüllt (Wakeword am Ende).
    """
    clips = []
    failed = 0
    for wav_path in wav_files:
        try:
            sr, wav = wavfile.read(str(wav_path))
            if len(wav.shape) > 1:
                wav = wav.mean(axis=1).astype(np.int16)
            if wav.dtype != np.int16:
                wav = (wav.astype(np.float32) / 32768.0 * 32767).astype(np.int16)
            if sr != SAMPLE_RATE:
                wav_f = wav.astype(np.float32)
                wav_f = resample(wav_f, int(len(wav_f) * SAMPLE_RATE / sr))
                wav = wav_f.astype(np.int16)
            # Auf clip_samples bringen (Stille vorne)
            if len(wav) < clip_samples:
                pad = np.zeros(clip_samples - len(wav), dtype=np.int16)
                wav = np.concatenate([pad, wav])
            else:
                wav = wav[:clip_samples]
            clips.append(wav)
        except Exception:
            failed += 1
    if failed:
        print(f"    [WARN] {failed} Dateien konnten nicht geladen werden")
    return np.array(clips, dtype=np.int16) if clips else None


class WakeWordClassifier(nn.Module):
    """
    GRU-Klassifikator der openWakeWord-Embeddings verarbeitet.

    Input:  [batch, 16, 96]  — 16 Embedding-Frames à 96 Dimensionen
    Output: [batch, 1]       — Wakeword-Wahrscheinlichkeit (0–1)
    """
    def __init__(self, n_context=N_CONTEXT, n_features=N_FEATURES):
        super().__init__()
        self.gru = nn.GRU(
            n_features, 64, num_layers=2,
            batch_first=True, dropout=0.2
        )
        self.fc = nn.Sequential(
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        # x: [batch, n_context, n_features]
        _, h = self.gru(x)   # h: [num_layers, batch, 64]
        return self.fc(h[-1])  # letzter Layer → [batch, 1]


def train_model():
    print(f"\n[3/3] Extrahiere Embeddings und trainiere Modell...")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if str(device) == "cpu":
        print("  ⚠️  Kein CUDA — Training auf CPU (dauert länger)")
    else:
        print(f"  ✓ GPU: {torch.cuda.get_device_name(0)}")

    # openWakeWord AudioFeatures laden
    print("  Lade openWakeWord Embedding-Modell...")
    try:
        from openwakeword.utils import AudioFeatures
        af = AudioFeatures()
        # Testlauf: [1, samples] int16 → [1, 16, 96]
        test = af.embed_clips(np.zeros((1, SAMPLE_RATE * 2), dtype=np.int16))
        assert test.shape == (1, N_CONTEXT, N_FEATURES), f"Unerwartete Form: {test.shape}"
        print("  ✓ Embedding-Modell geladen")
    except ImportError:
        print("❌ openwakeword nicht installiert!")
        print("   Bitte installieren mit: pip install openwakeword")
        return
    except Exception as e:
        print(f"❌ Embedding-Modell-Fehler: {e}")
        return

    pos_files = list(Path(f"{TRAIN_DIR}/positive").glob("*.wav"))
    neg_files = list(Path(f"{TRAIN_DIR}/negative").glob("*.wav"))
    print(f"  Positiv: {len(pos_files)} | Negativ: {len(neg_files)} Dateien\n")

    # Alle Clips auf 2 Sekunden normieren (= 32000 Samples bei 16kHz)
    CLIP_SAMPLES = SAMPLE_RATE * 2

    # Clips laden und Embeddings in Batches extrahieren
    BATCH = 64

    def embed_files(files, label):
        all_emb = []
        for i in range(0, len(files), BATCH):
            batch_files = files[i:i+BATCH]
            clips = load_clips_as_int16(batch_files, CLIP_SAMPLES)
            if clips is None:
                continue
            emb = af.embed_clips(clips)  # [n, 16, 96]
            all_emb.append(emb)
            if (i + BATCH) % 200 == 0 or i + BATCH >= len(files):
                print(f"    → {min(i+BATCH, len(files))}/{len(files)} verarbeitet")
        return np.concatenate(all_emb, axis=0) if all_emb else np.empty((0, N_CONTEXT, N_FEATURES))

    print("  Extrahiere positive Embeddings...")
    X_pos = embed_files(pos_files, 1)
    print(f"  → {len(X_pos)} positive Samples")

    print("  Extrahiere negative Embeddings...")
    X_neg = embed_files(neg_files, 0)
    print(f"  → {len(X_neg)} negative Samples")

    if len(X_pos) < 10 or len(X_neg) < 10:
        print("❌ Zu wenig Daten nach Embedding-Extraktion!")
        return

    # Klassen balancieren: max 3× so viele Negative wie Positive
    max_neg = min(len(X_neg), len(X_pos) * 3)
    idx_neg = np.random.choice(len(X_neg), max_neg, replace=False)
    X_neg   = X_neg[idx_neg]
    print(f"  Balanciert: {len(X_pos)} pos / {len(X_neg)} neg")

    X = np.concatenate([X_pos, X_neg], axis=0).astype(np.float32)
    y = np.array([1.0] * len(X_pos) + [0.0] * len(X_neg), dtype=np.float32)

    perm = np.random.permutation(len(X))
    X, y = X[perm], y[perm]

    X = torch.tensor(X)
    y = torch.tensor(y).unsqueeze(1)

    split   = int(0.8 * len(X))
    X_train = X[:split].to(device)
    y_train = y[:split].to(device)
    X_val   = X[split:].to(device)
    y_val   = y[split:].to(device)

    model     = WakeWordClassifier().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    criterion = nn.BCELoss()

    print(f"\n  Training: {split} Train, {len(X)-split} Val, {EPOCHS} Epochen")
    best_val = float("inf")

    for epoch in range(EPOCHS):
        model.train()
        losses = []
        perm_e = torch.randperm(len(X_train))
        for i in range(0, len(X_train), BATCH_SIZE):
            idx  = perm_e[i:i+BATCH_SIZE]
            xb, yb = X_train[idx], y_train[idx]
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())

        model.eval()
        with torch.no_grad():
            val_pred = model(X_val)
            val_loss = criterion(val_pred, y_val).item()
            val_acc  = ((val_pred > 0.5).float() == y_val).float().mean().item()

        scheduler.step(val_loss)

        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), str(SCRIPT_DIR / "best_wakeword.pt"))

        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch+1:3d}/{EPOCHS} | "
                  f"Loss: {sum(losses)/len(losses):.4f} | "
                  f"Val Loss: {val_loss:.4f} | "
                  f"Val Acc: {val_acc*100:.1f}%")

    # Bestes Modell als ONNX exportieren
    print(f"\n  Exportiere als ONNX: {OUTPUT_MODEL}")
    model.load_state_dict(torch.load(str(SCRIPT_DIR / "best_wakeword.pt"), map_location="cpu"))
    model.eval().cpu()

    dummy = torch.zeros(1, N_CONTEXT, N_FEATURES)
    torch.onnx.export(
        model, dummy, OUTPUT_MODEL,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        opset_version=11,
    )

    if os.path.exists(OUTPUT_MODEL):
        print(f"\n{'='*50}")
        print(f"  ✅ Fertig! Modell gespeichert: {OUTPUT_MODEL}")
        print(f"  → Setze in bmo_desktop.py:")
        print(f"     WAKE_WORD_MODEL = '{OUTPUT_MODEL}'")
        print(f"{'='*50}\n")
    else:
        print("❌ ONNX-Export fehlgeschlagen.")


if __name__ == "__main__":
    print("\n  BMO Wakeword Trainer (openWakeWord-kompatibel)")
    print(f"   Wakeword: '{WAKEWORD}'")
    print(f"   Ausgabe:  {OUTPUT_MODEL}\n")

    setup_dirs()

    pos_existing = list(Path(f"{TRAIN_DIR}/positive").glob("*.wav"))
    neg_existing = list(Path(f"{TRAIN_DIR}/negative").glob("*.wav"))

    if len(pos_existing) > 10 and len(neg_existing) > 10:
        print(f"✓ Daten gefunden: {len(pos_existing)} Positiv, {len(neg_existing)} Negativ")
        print("  Überspringe Generierung...\n")
        train_model()
    else:
        pos, neg = generate_training_data()
        if pos > 10 and neg > 10:
            train_model()
        else:
            print("❌ Zu wenig Daten generiert.")
