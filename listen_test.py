import json
import queue
import sys
from pathlib import Path

import sounddevice as sd
from vosk import Model, KaldiRecognizer

DEVICE = 2
folder = Path(__file__).resolve().parent
model_path = folder / "models" / "vosk-model-small-en-us-0.15"
audio_queue = queue.Queue()


def receive_audio(indata, frames, time_info, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(bytes(indata))


def main():
    device = sd.query_devices(DEVICE, "input")
    sample_rate = int(device["default_samplerate"])
    model = Model(str(model_path))
    recognizer = KaldiRecognizer(model, sample_rate)

    with sd.RawInputStream(
        device=DEVICE,
        samplerate=sample_rate,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=receive_audio,
    ):
        print(f"Listening through: {device['name']}")
        print("Speak, then pause. Ctrl+C stops the test.")
        while True:
            audio = audio_queue.get()
            if recognizer.AcceptWaveform(audio):
                text = json.loads(recognizer.Result()).get("text", "")
                if text:
                    print("Heard:", text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nListening stopped.")