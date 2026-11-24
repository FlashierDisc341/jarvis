"""JARVIS: local, manually armed voice-command test for Windows.
Press Enter to listen for one phrase (up to 10 seconds).
Only the fixed commands below are handled. No apps or shell commands run.
Microphone audio stays in memory. Synthesized replies use an in-memory WAV.
"""
import io
import json
import queue
import time
import wave
import winsound
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from piper import PiperVoice
from vosk import Model, KaldiRecognizer

DEVICE = 2  # onn Gaming Headset in your current device list
FOLDER = Path(__file__).resolve().parent
MODEL_PATH = FOLDER / "models" / "vosk-model-small-en-us-0.15"
VOICE_PATH = FOLDER / "voices" / "en_GB-northern_english_male-medium.onnx"


def speak(voice, text):
    print("JARVIS:", text)
    # Build the reply WAV in memory, not a recording of your microphone.
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)


def listen_once(model, sample_rate):
    chunks = queue.Queue()
    recognizer = KaldiRecognizer(model, sample_rate)

    def receive_audio(indata, frames, time_info, status):
        if status:
            print("Audio warning:", status)
        chunks.put(bytes(indata))

    # Leaving this block closes the microphone before JARVIS speaks.
    with sd.RawInputStream(
        device=DEVICE,
        samplerate=sample_rate,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=receive_audio,
    ):
        print("Listening: say one command, then pause.")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                audio = chunks.get(timeout=0.25)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(audio):
                text = json.loads(recognizer.Result()).get("text", "").strip()
                if text:
                    return text
        return json.loads(recognizer.FinalResult()).get("text", "").strip()


def main():
    for path in (MODEL_PATH, VOICE_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Missing model or voice: {path}")
    print("Loading recognition and voice models...")
    model = Model(str(MODEL_PATH))
    voice = PiperVoice.load(str(VOICE_PATH))
    device = sd.query_devices(DEVICE, "input")
    sample_rate = int(device["default_samplerate"])
    print("Microphone:", device["name"])
    print("Commands: hello there | what time is it | status report | goodbye")
    speak(voice, "Systems online, sir.")

    while True:
        choice = input("\nPress Enter to listen, or type q then Enter to quit: ")
        if choice.strip().lower() == "q":
            break
        if choice.strip():
            continue
        text = " ".join(listen_once(model, sample_rate).lower().split())
        print("Heard:", text or "(nothing)")
        if text in {"hello", "hello there"}:
            speak(voice, "Good evening, sir. At your service.")
        elif text == "what time is it":
            current_time = datetime.now().strftime("%I:%M %p").lstrip("0")
            speak(voice, f"The time is {current_time}, sir.")
        elif text == "status report":
            speak(voice, "Voice and speech recognition are online, sir.")
        elif text == "goodbye":
            speak(voice, "Goodbye, sir.")
            break
        else:
            print("No matching command. No action taken.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as error:
        print(f"Error ({type(error).__name__}): {error}")
