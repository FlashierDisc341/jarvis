"""Whisper JARVIS with persistent notes/reminders. Default: live controls.
--dry-run prints commands only; it does not open the organizer database.
"""
import argparse
import io
import time
import traceback
import wave
import winsound
from pathlib import Path

from jarvis_whisper_audio import WhisperListener
from jarvis_dialogue import normalize, remove_wake_marker, command_for_transcript
from jarvis_intent import IntentRouter

from jarvis_config import CONFIG

DEVICE = CONFIG["mic_device"]  # set in config.json
ROOT = Path(__file__).resolve().parent
VOICE_PATH = ROOT / "voices" / "en_GB-northern_english_male-medium.onnx"
FOLLOWUP_SECONDS = 15


def speak(voice, text):
    print("JARVIS:", text, flush=True)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        voice.synthesize_wav(text, wav)
    winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)
    time.sleep(0.2)


def main(dry_run=False, no_ollama=False):
    started_at = time.time()
    if not VOICE_PATH.is_file():
        raise FileNotFoundError(f"Missing Piper voice: {VOICE_PATH.name}")
    listener = WhisperListener(device=DEVICE)
    from piper import PiperVoice
    voice = PiperVoice.load(str(VOICE_PATH))
    actions = None
    try:
        if dry_run:
            alert_due = lambda: False
            speak(voice, "Dry run is ready. Commands will only be printed, sir.")
        else:
            from jarvis_actions import Actions, Result
            actions = Actions()
            router = IntentRouter(actions, Result, enabled=not no_ollama)
            print("Ollama fallback:", "disabled" if no_ollama else "enabled (checked on use)", flush=True)
            alert_due = actions.has_due
            speak(voice, "Whisper voice control, notes and reminders are ready, sir.")
        pending = ()
        followup_until = None

        def announce_due():
            # Microphone capture is already closed. No spoken text is executed.
            try:
                winsound.Beep(880, 200)
                winsound.Beep(1100, 200)
            except RuntimeError:
                pass
            for alert in actions.calendar.take_alerts():
                speak(voice, alert)
                actions.last_reply = alert
            rows = actions.organizer.due_rows()
            if rows:
                alert = actions.organizer.alert_text(rows, started_at)
                speak(voice, alert)
                actions.last_reply = alert
                # Playback returning does not prove the user heard it.
                # A speech failure before this point leaves reminders unannounced.
                actions.organizer.acknowledge(rows)

        print("Ctrl+C stops this script. Wait for LISTENING before speaking.", flush=True)
        while True:
            if alert_due():
                had_pending = bool(pending)
                pending, followup_until = (), None
                announce_due()
                if had_pending:
                    speak(voice, "The pending request was cancelled by the alert. Please ask again, sir.")
                continue
            following_up = followup_until is not None
            if following_up:
                remaining = followup_until - time.monotonic()
                if remaining <= 0:
                    pending, followup_until = (), None
                    print("Answer window expired. Unsaved request cancelled.", flush=True)
                    continue
            else:
                remaining = None
            captured = listener.capture(alert_due, timeout=remaining)
            if captured.kind == "timer":
                # The same capture interruption now also covers reminders.
                continue
            if captured.kind == "timeout":
                pending, followup_until = (), None
                print("Answer window expired. Unsaved request cancelled.", flush=True)
                continue
            if captured.kind == "discarded":
                pending, followup_until = (), None
                print("Unclear or overlong utterance discarded. Say the full command again.", flush=True)
                continue
            if alert_due():
                continue
            print("Processing speech. Microphone paused...", flush=True)
            transcript = listener.transcribe(captured.audio)
            del captured
            if alert_due():
                continue
            # Do not accept an expired confirmation just because transcription took time.
            if following_up and time.monotonic() >= followup_until:
                pending, followup_until = (), None
                print("Answer window expired during transcription. Unsaved request cancelled.", flush=True)
                continue
            if not transcript:
                print("No speech transcribed.", flush=True)
                continue
            print("Heard:", transcript, flush=True)
            command = command_for_transcript(transcript, following_up, pending)
            if command is None:
                print("No wake phrase at either end. Ignored.", flush=True)
                continue
            if not command:
                speak(voice, "Yes, sir.")
                followup_until = time.monotonic() + FOLLOWUP_SECONDS
                continue
            if dry_run:
                print("DRY RUN COMMAND:", normalize(command), flush=True)
                print("No action executed.", flush=True)
                if normalize(command) in {"goodbye", "stop listening", "exit", "quit"}:
                    return
                pending, followup_until = (), None
                continue
            result = router.handle(command, pending, interrupted=alert_due)
            if alert_due():
                # The next loop announces the alert and cancels pending work.
                continue
            if result.reply:
                speak(voice, result.reply)
                actions.last_reply = result.reply
            if result.stop:
                if actions.calendar.timers:
                    speak(voice, "Running timers are cancelled when voice control stops, sir.")
                return
            pending = result.choices
            followup_until = time.monotonic() + FOLLOWUP_SECONDS if pending else None
    finally:
        if actions is not None:
            actions.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing actions or opening notes/reminders.")
    parser.add_argument("--no-ollama", action="store_true",
                        help="Use only existing exact commands; no Ollama requests.")
    options = parser.parse_args()
    try:
        main(dry_run=options.dry_run, no_ollama=options.no_ollama)
    except KeyboardInterrupt:
        print("\nJARVIS stopped. Unsaved drafts and timers are cancelled. Saved notes/reminders remain.")
    except Exception:
        print("\nJARVIS stopped. Keep the following error output:")
        traceback.print_exc()
