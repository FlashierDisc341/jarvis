"""JARVIS base v5 - local voice, app/folder catalogue and choice handling.
Keep all supplied jarvis_*.py modules beside this file.
Uses the full en-us-0.22 model. Install pycaw for system volume; existing dependencies are retained.
Mic audio/transcripts are not saved; recognized text is printed in the terminal.
The mic closes during actions and speech. No startup task or service is added.
"""
import io
import json
import queue
import threading
import time
import wave
import winsound
from pathlib import Path

import sounddevice as sd
from piper import PiperVoice
from vosk import Model, KaldiRecognizer
from jarvis_actions import Actions

DEVICE = 2
FOLDER = Path(__file__).resolve().parent
MODEL_PATH = FOLDER / "models" / "vosk-model-en-us-0.22"
VOICE_PATH = FOLDER / "voices" / "en_GB-northern_english_male-medium.onnx"
WAKE_PHRASES = ("jarvis", "hey jarvis")
FOLLOWUP_SECONDS = 15
TIMER_DUE = object()

def normalize(text):
    return " ".join(text.lower().strip().split())


def remove_wake_marker(text):
    """None = not addressed; empty string = wake phrase alone.

    Accept a whole wake phrase at the start OR end, never in the middle.
    Prefix wins so "Jarvis, open Jarvis" still opens the Jarvis folder.
    """
    separators = " ,.!?;:"
    text = normalize(text).strip(separators)
    phrases = sorted(WAKE_PHRASES, key=len, reverse=True)
    for phrase in phrases:
        if text == phrase:
            return ""
        if text.startswith(phrase):
            remainder = text[len(phrase):]
            if remainder and remainder[0] in separators:
                return remainder.strip(separators)
    for phrase in phrases:
        if text.endswith(phrase):
            before = text[:-len(phrase)]
            if before and before[-1] in separators:
                return before.strip(separators)
    return None


def speak(voice, text):
    print("JARVIS:", text, flush=True)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)
    # Let the very end of playback settle before reopening the input.
    time.sleep(0.2)


def listen(model, sample_rate, require_wake, timer_due):
    """Return a command, TIMER_DUE, or None on follow-up timeout."""
    chunks = queue.Queue(maxsize=32)
    overflow = threading.Event()
    recognizer = KaldiRecognizer(model, sample_rate)

    def receive_audio(indata, frames, time_info, status):
        if status:
            overflow.set()
        try:
            chunks.put_nowait(bytes(indata))
        except queue.Full:
            overflow.set()

    def interpret(text):
        text = normalize(text)
        if not text:
            return None
        print("Heard:", text, flush=True)
        after_wake = remove_wake_marker(text)
        if require_wake:
            return after_wake
        return after_wake if after_wake is not None else text

    with sd.RawInputStream(
        device=DEVICE,
        samplerate=sample_rate,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=receive_audio,
    ):
        if require_wake:
            print("\nWaiting for a command with Jarvis at the start or end...", flush=True)
        else:
            print("\nListening for your answer (15 seconds)...", flush=True)
        deadline = None if require_wake else time.monotonic() + FOLLOWUP_SECONDS
        while deadline is None or time.monotonic() < deadline:
            if timer_due():
                return TIMER_DUE
            if overflow.is_set():
                raise RuntimeError(
                    "Audio overflow/status warning. Stopped rather than act on incomplete audio."
                )
            try:
                audio = chunks.get(timeout=0.25)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(audio):
                text = json.loads(recognizer.Result()).get("text", "")
                command = interpret(text)
                if command is not None:
                    return command
        # At timeout, deliberately discard unfinished speech.
        return None



def main():
    for path in (MODEL_PATH, VOICE_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Missing model or voice: {path}")
    device = sd.query_devices(DEVICE, "input")
    print("Microphone:", device["name"], flush=True)
    sample_rate = int(device["default_samplerate"])
    print("Loading local speech models...", flush=True)
    model = Model(str(MODEL_PATH))
    voice = PiperVoice.load(str(VOICE_PATH))
    actions = Actions()
    print("Say Jarvis at the start or end of a command. Ctrl+C stops the script.", flush=True)
    speak(voice, "Voice control is ready, sir.")
    pending = ()
    followup = False

    while True:
        command = listen(
            model, sample_rate, require_wake=not followup,
            timer_due=actions.calendar.has_due,
        )
        # The input stream is closed before beeping or speaking.
        if command is TIMER_DUE or actions.calendar.has_due():
            had_pending = bool(pending)
            pending = ()
            followup = False
            try:
                winsound.Beep(880, 200)
                winsound.Beep(1100, 200)
            except RuntimeError:
                pass
            for alert in actions.calendar.take_alerts():
                speak(voice, alert)
                actions.last_reply = alert
            if had_pending:
                speak(voice, "The pending choice was cancelled. Please ask again, sir.")
            # Discard any utterance interrupted by an alert, never execute half a command.
            continue
        if command is None:
            pending = ()
            followup = False
            print("Answer window expired. Pending action cancelled.", flush=True)
            continue
        if command == "":
            speak(voice, "Yes, sir.")
            followup = True
            continue
        result = actions.handle(command, pending)
        if result.reply:
            speak(voice, result.reply)
            actions.last_reply = result.reply
        if result.stop:
            if actions.calendar.timers:
                speak(voice, "Running timers are cancelled when voice control stops, sir.")
            return
        pending = result.choices
        followup = bool(pending)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nJARVIS stopped. Microphone closed. Any active timers are cancelled.")
    except Exception as error:
        print(f"Stopped ({type(error).__name__}): {error}")
