# Whisper GPU transcription test

For the current Windows PC with Ryzen 5 8400F, 16 GB RAM and RTX 4060 Ti.
This is a separate transcription-only test, not a replacement JARVIS build yet.

The test uses Whisper large-v3-turbo via faster-whisper.
It prefers GPU int8_float16 to reduce memory usage, with float16 as the fallback
if the installed GPU backend does not offer int8_float16.
It does NOT silently fall back to CPU inference.

## Setup in the existing Jarvis folder

Stop JARVIS with Ctrl+C first. Close games or other loaded GPU models for this test.
Put whisper_test.py and whisper-requirements.txt beside jarvis.py.
Do NOT replace jarvis.py or any jarvis_*.py modules.

Create a separate environment using the Python you already have:

    .\.venv\Scripts\python.exe -m venv .venv-whisper
    .\.venv-whisper\Scripts\python.exe -m pip install --upgrade pip
    .\.venv-whisper\Scripts\python.exe -m pip install --only-binary=:all: -r whisper-requirements.txt

This is a multi-GB download/setup including NVIDIA libraries and the model.
The Python package installer changes only .venv-whisper, not your existing .venv.
No admin shell, global PATH edit, full CUDA developer toolkit or source build is requested.
The test adds the installed NVIDIA DLL folders only to its own process search paths.

Current official package pages provide Windows x86-64 wheels, including Python 3.14
for CTranslate2. That does not prove your local driver/runtime combination works;
the script checks GPU inference before it asks you to record.

If package installation fails, stop and keep the actual error rather than changing Python versions blindly.

## Run

    .\.venv-whisper\Scripts\python.exe whisper_test.py

First run downloads the converted model from Hugging Face into models/whisper-cache.
The model source is dropbox-dash/faster-whisper-large-v3-turbo, the current location
of the conversion referenced by faster-whisper's turbo model mapping.
Model/tokenizer weights are downloaded; no Hugging Face remote Python code is executed.

After GPU warm-up:
1. Press Enter.
2. Wait for GO.
3. Speak one normal command within the seven-second recording window.
4. Read HEARD and the reported transcription time.
5. Repeat, or type q and Enter to quit. Ctrl+C also stops it.

Suggested comparison phrases:
- Jarvis, what is the volume?
- Set volume to thirty percent, Jarvis.
- Jarvis, volume down.
- Jarvis, minimize Notepad.
- What day of the week is it, Jarvis?
- Jarvis, what date will be in ten weeks?

Try the troublesome volume phrases more than once, at your normal speaking pace.
The model gets NO vocabulary prompt and NO value-to-volume text replacement in this test.
This makes the raw recognition result easier to assess.
The seven-second capture duration is a test control, not the intended final command latency.

## Privacy and effects

- Input remains headset device 2. Its current name prints before recording.
- Recording happens only after you press Enter.
- Audio is kept in memory, not saved to files or uploaded by this test.
- Transcription runs locally on your GPU.
- Recognized text prints to the local console; it is not written to a transcript file.
- No JARVIS actions are imported or called. Saying close/end/mute cannot execute them.
- Nothing is installed as a service or startup task.
- Your existing JARVIS environment and source files stay intact.
- Downloaded Python packages and model weights remain on disk.

This script has not been executed in the author's environment.
A successful package install is not a successful GPU or recognition test.
If GPU/DLL/driver errors occur, keep the exact error so the actual dependency can be identified.

References:
https://github.com/SYSTRAN/faster-whisper
https://pypi.org/project/ctranslate2/
https://pypi.org/project/nvidia-cublas-cu12/
https://pypi.org/project/nvidia-cudnn-cu12/
https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo
