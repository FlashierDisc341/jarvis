"""GPU Whisper microphone comparison. Does NOT import or execute JARVIS actions.
Only short, manually triggered recordings; no audio/transcript files are written.
The model is downloaded from Hugging Face on first run and cached locally.
"""
import importlib.metadata
import io
import os
from pathlib import Path
import sys
import time
import traceback
import wave

DEVICE = 2  # Same headset input as the working JARVIS setup.
RECORD_SECONDS = 7
MODEL_ID = "dropbox-dash/faster-whisper-large-v3-turbo"
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "models" / "whisper-cache"
DLL_HANDLES = []

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def prepare_nvidia_libraries():
    """Expose only installed NVIDIA wheel DLL folders to THIS Python process."""
    if os.name != "nt":
        raise RuntimeError("This test is configured for Windows.")
    wanted = {
        "nvidia-cublas-cu12", "nvidia-cudnn-cu12",
        "nvidia-cuda-runtime-cu12", "nvidia-cuda-nvrtc-cu12",
        "nvidia-nvjitlink-cu12",
    }
    folders = set()
    for distribution in importlib.metadata.distributions():
        name = (distribution.metadata.get("Name") or "").lower().replace("_", "-")
        if name not in wanted:
            continue
        for file in distribution.files or ():
            if str(file).lower().endswith(".dll"):
                path = Path(distribution.locate_file(file)).resolve().parent
                if path.is_dir():
                    folders.add(path)
    if not folders:
        raise RuntimeError("No NVIDIA runtime DLLs were found in this environment.")
    paths = [str(path) for path in sorted(folders)]
    # Keep handles alive; closing one removes its search-directory registration.
    for path in paths:
        DLL_HANDLES.append(os.add_dll_directory(path))
    os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])
    print(f"NVIDIA runtime search folders registered: {len(paths)}", flush=True)


def microphone_clip(sd, np, sample_rate):
    # sd.rec opens the input before the GO message, avoiding speech before capture.
    recording = sd.rec(
        int(RECORD_SECONDS * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=DEVICE,
        blocking=False,
    )
    print(f"GO: say ONE command now. Recording for {RECORD_SECONDS} seconds...", flush=True)
    status = sd.wait()
    if status:
        raise RuntimeError(f"Audio capture warning; discarded this clip: {status}")
    peak = float(np.max(np.abs(recording.astype(np.float32)))) / 32768
    print(f"Capture peak: {peak * 100:.1f}% of digital full scale", flush=True)
    if peak == 0:
        raise RuntimeError("The microphone returned silence. Check input device 2.")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(recording.tobytes())
    buffer.seek(0)
    return buffer


def main():
    prepare_nvidia_libraries()
    import ctranslate2
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    print("Python:", sys.version.split()[0], flush=True)
    print("CTranslate2:", ctranslate2.__version__, flush=True)
    devices = ctranslate2.get_cuda_device_count()
    print("CUDA devices detected:", devices, flush=True)
    if devices < 1:
        raise RuntimeError("No usable CUDA GPU was detected. This test will not silently use the CPU.")
    supported = ctranslate2.get_supported_compute_types("cuda", device_index=0)
    compute_type = "int8_float16" if "int8_float16" in supported else "float16"
    if compute_type not in supported:
        raise RuntimeError(f"Required GPU precision is unavailable. Supported: {supported}")
    print("GPU compute type:", compute_type, flush=True)
    device = sd.query_devices(DEVICE, "input")
    sample_rate = int(device["default_samplerate"])
    sd.check_input_settings(
        device=DEVICE, channels=1, dtype="int16", samplerate=sample_rate
    )
    print("Microphone:", device["name"], flush=True)
    print("Loading Whisper large-v3-turbo. First run downloads the model...", flush=True)
    model = WhisperModel(
        MODEL_ID, device="cuda", device_index=0, compute_type=compute_type,
        download_root=str(CACHE), cpu_threads=4, num_workers=1,
    )

    print("Checking GPU inference before recording...", flush=True)
    warmup, _ = model.transcribe(
        np.zeros(16000, dtype=np.float32),
        language="en", task="transcribe", beam_size=1,
        condition_on_previous_text=False, vad_filter=False,
    )
    list(warmup)  # Inference is lazy, so consume it to actually check the GPU stack.
    print("\nREADY. No app actions are connected. Audio stays in memory.", flush=True)
    print("Speak normally. There is no vocabulary prompt or value-to-volume replacement.", flush=True)

    while True:
        answer = input("\nPress Enter for one recording, or type q then Enter to quit: ")
        if answer.strip().lower() == "q":
            break
        with microphone_clip(sd, np, sample_rate) as buffer:
            # PyAV resamples the in-memory WAV to Whisper's 16 kHz input.
            audio = decode_audio(buffer, sampling_rate=16000)
        started = time.perf_counter()
        segments, info = model.transcribe(
            audio, language="en", task="transcribe",
            beam_size=5, temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 250},
            no_speech_threshold=0.6,
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        elapsed = time.perf_counter() - started
        print(f"\nHEARD: {transcript or '[no speech detected]'}", flush=True)
        print(f"Transcription time after capture: {elapsed:.2f} seconds", flush=True)
        # Not persisted and never passed to a command dispatcher.
        del audio
    print("Test stopped. Your JARVIS files were not changed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest stopped.")
    except Exception:
        print("\nTEST STOPPED. Keep this error output; do not change drivers or DLLs blindly.")
        traceback.print_exc()
