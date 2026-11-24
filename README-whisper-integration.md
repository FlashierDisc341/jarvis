# JARVIS: integrated Whisper frontend

The manually triggered Whisper test recognized all three displayed volume commands.
This build connects that recognizer to the existing v5 JARVIS actions, with automatic
speech boundaries instead of the fixed seven-second test recording.

It adds a NEW entry point, jarvis_whisper.py.
It does NOT replace jarvis.py or any existing command modules.
The original Vosk program/environment remains available as a fallback.

## Install

Stop the old JARVIS and whisper_test.py.
Put these attached files in the same Jarvis folder:
- jarvis_whisper.py
- jarvis_whisper_audio.py
- test_whisper_frontend.py

Use the .venv-whisper environment that just passed the GPU test.
Install the existing voice/control dependencies into that environment:

    .\.venv-whisper\Scripts\python.exe -m pip install --only-binary=:all: piper-tts==1.8.0 pycaw==20251023 psutil==7.2.2

The old .venv environment is not changed.
The existing downloaded Piper voice and Whisper model cache are reused.
The Whisper listener uses local_files_only=True; it does not download another model.
Keep all existing jarvis_actions, jarvis_processes, jarvis_time, jarvis_desktop,
jarvis_math and jarvis_help modules beside the new entry point.

Run the component checks:

    .\.venv-whisper\Scripts\python.exe test_whisper_frontend.py

These test endpoint timing, wake-word extraction and PyAV resampling.
They do not load a GPU model, open the microphone, alter volume or operate apps.
This integration has not been run in the author's environment.
The successful microphone test validates that test, not this new end-of-speech integration.

## First run: hands-free dry run

    .\.venv-whisper\Scripts\python.exe jarvis_whisper.py --dry-run

Wait for LISTENING. Speak normally, then pause briefly:
- "Jarvis, what is the volume?"
- "Set volume to thirty percent, Jarvis."
- "Jarvis, volume down."
- "What date will be in ten weeks, Jarvis?"

It should detect the speech, transcribe it and print DRY RUN COMMAND.
No app or volume actions are connected in dry-run mode.
Piper still speaks the startup/wake acknowledgement, so you can also check its voice.
"Jarvis" alone should say "Yes, sir" and open the follow-up window.
Ctrl+C stops it.

## Live run

If the dry-run commands look right, stop it and run:

    .\.venv-whisper\Scripts\python.exe jarvis_whisper.py

There is no --dry-run flag here: existing v5 controls are now connected.
Start with the read-only volume question, then volume down.
Normal close/force-end, volume confirmations and choice handling are unchanged.
All existing commands remain in the v5 README and "what can you do" help.
No playback or other in-app controls were added.

## How listening now works

- Uses the same headset input DEVICE = 2.
- Captures at the device's default rate and resamples in memory to 16 kHz.
- Uses the bundled Silero speech detector before calling Whisper.
- Preserves a short pre-roll to avoid losing the beginning of the wake phrase.
- Waits for roughly three quarters of a second of VAD silence, plus detector
  windowing, rather than recording every phrase for seven seconds.
- Uses the same GPU model, beam setting and English transcription mode as the test.
- Still requires Jarvis at the start or end, except during an explicit follow-up.
- Follow-up time is 15 seconds. Empty recognition does not keep extending it.
- Overlong utterances are discarded instead of executing a cut-off command.
- The microphone is CLOSED during GPU transcription, actions and spoken replies.
  Wait for LISTENING before the next command; this is not voice interruption/barge-in.
- Unaddressed speech is ignored after local transcription, not passed to actions.
- No vocabulary prompt or value-to-volume replacement is applied.

Timers still interrupt listening. An expiry during transcription wins over that command.
Pending confirmations are cancelled by an alert; interrupted speech is not executed.
Timers still require this process running and the PC awake.

## Privacy and limitations

Audio remains in memory and is not saved/uploaded by this frontend.
Transcripts print to the local terminal; they are not written to a transcript file.
The speech models run locally, and cached Whisper files are required.
This is not speaker authentication: a wake phrase can also come from nearby people/media.
Speech recognition can still make mistakes. Force-end and loud-volume confirmations remain.

A GPU error does not silently select a CPU model.
If the new frontend fails, keep the full error output.
The original program is still runnable with:

    .\.venv\Scripts\python.exe jarvis.py

Avoid running both listeners at once.

References:
https://github.com/SYSTRAN/faster-whisper
https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/faster_whisper/vad.py
https://pyav.org/docs/stable/api/audio.html
