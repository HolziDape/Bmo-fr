import os
from tts_with_rvc import TTS_RVC

# --- SETUP ---
RVC_MODEL = "BMO_500e_7000s.pth"
RVC_INDEX = "BMO.index"
# Wir holen uns den absoluten Pfad zum aktuellen Ordner
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(BASE_DIR, "sounds")

# Ordner 'sounds' auf deinem PC erstellen, falls er nicht existiert
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)
    print(f"Ordner erstellt: {OUTPUT_FOLDER}")

# BMO Stimme initialisieren
print("BMO Stimme wird geladen...")
tts = TTS_RVC(model_path=RVC_MODEL, index_path=RVC_INDEX, voice="de-DE-KatjaNeural")

def create_audio():
    print("\n--- BMO Audio Creator ---")
    print("Gib den Text ein, den BMO sagen soll.")
    print("Tippe 'exit' zum Beenden.")
    
    while True:
        text = input("\nText für BMO: ")
        
        if text.lower() == 'exit':
            break
            
        filename = input("Dateiname (z.B. bmo_hallo): ")
        
        # Sonderzeichen wie '!' im Dateinamen vermeiden (macht oft Probleme)
        filename = filename.replace("!", "").replace("?", "").strip()
        
        if not filename.endswith(".wav"):
            filename += ".wav"
            
        # Wir bauen den KOMPLETTEN Pfad, damit das Paket sich nicht verläuft
        full_path = os.path.join(OUTPUT_FOLDER, filename)
        
        print(f"Generiere Audio für: '{text}'...")
        
        try:
            # Hier nutzen wir den sauberen Pfad
            tts(
                text=text,
                pitch=4,
                tts_rate=25,
                output_filename=full_path 
            )
            print(f"✅ Erfolgreich gespeichert: {full_path}")
        except Exception as e:
            print(f"❌ Fehler: {e}")

if __name__ == "__main__":
    create_audio()