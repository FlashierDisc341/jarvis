from pathlib import Path
import wave
import winsound
from piper import PiperVoice

folder = Path(__file__).resolve().parent
model = folder / "voices" / "en_GB-northern_english_male-medium.onnx"
output = folder / "jarvis_voice_test.wav"

print("Loading voice...")
voice = PiperVoice.load(str(model))

print("Generating speech...")
with wave.open(str(output), "wb") as audio_file:
    voice.synthesize_wav(
        "Good evening, sir. Systems online. How may I assist you?",
        audio_file,
    )

print("Playing...")
winsound.PlaySound(str(output), winsound.SND_FILENAME)
print("Finished.")