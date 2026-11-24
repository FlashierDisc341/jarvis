"""Hands-free local Whisper audio frontend. No app actions or persistent recordings."""
from collections import deque
from dataclasses import dataclass
import importlib.metadata
import math
import os
from pathlib import Path
import queue
import threading
import time

import av
import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parent
MODEL_ID = "dropbox-dash/faster-whisper-large-v3-turbo"
CACHE = ROOT / "models" / "whisper-cache"
DLL_HANDLES = []
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def prepare_nvidia_libraries():
    wanted = {
        "nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-runtime-cu12",
        "nvidia-cuda-nvrtc-cu12", "nvidia-nvjitlink-cu12",
    }
    folders = set()
    for distribution in importlib.metadata.distributions():
        name = (distribution.metadata.get("Name") or "").lower().replace("_", "-")
        if name in wanted:
            for file in distribution.files or ():
                if str(file).lower().endswith(".dll"):
                    folder = Path(distribution.locate_file(file)).resolve().parent
                    if folder.is_dir():
                        folders.add(folder)
    if not folders:
        raise RuntimeError("NVIDIA runtime packages are missing. Use .venv-whisper.")
    paths = [str(folder) for folder in sorted(folders)]
    for path in paths:
        DLL_HANDLES.append(os.add_dll_directory(path))
    os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])


class SpeechGate:
    """Pure timing state: speech probability in, endpoint status out."""
    def __init__(self, silence_seconds=0.75, max_seconds=12.0):
        self.silence_limit = silence_seconds
        self.max_seconds = max_seconds
        self.active = False
        self.silence = 0.0
        self.elapsed = 0.0
        self.voiced = 0.0

    def feed(self, probability, seconds):
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            return 'discard'
        if not self.active:
            if probability < 0.5:
                return "waiting"
            self.active = True
            self.elapsed = seconds
            self.voiced = seconds
            self.silence = 0.0
            return "start"
        self.elapsed += seconds
        if probability >= 0.35:
            self.voiced += seconds
            self.silence = 0.0
        else:
            self.silence += seconds
        if self.elapsed >= self.max_seconds:
            return "discard"
        if self.silence >= self.silence_limit:
            return "complete" if self.voiced >= 0.15 else "discard"
        return "continue"


@dataclass
class Capture:
    kind: str  # audio, timeout, timer, discarded
    audio: object = None


class WhisperListener:
    def __init__(self, device=2):
        self.device = device
        prepare_nvidia_libraries()
        import ctranslate2
        from faster_whisper import WhisperModel
        from faster_whisper.vad import get_vad_model

        if ctranslate2.get_cuda_device_count() < 1:
            raise RuntimeError("No CUDA GPU detected. No silent CPU fallback.")
        supported = ctranslate2.get_supported_compute_types("cuda", device_index=0)
        compute = "int8_float16" if "int8_float16" in supported else "float16"
        if compute not in supported:
            raise RuntimeError(f"No suitable GPU compute type: {supported}")
        info = sd.query_devices(device, "input")
        self.rate = int(info["default_samplerate"])
        sd.check_input_settings(
            device=device, samplerate=self.rate, channels=1, dtype="int16"
        )
        print("Microphone:", info["name"], flush=True)
        print("Loading cached Whisper model on GPU:", compute, flush=True)
        self.model = WhisperModel(
            MODEL_ID, device="cuda", device_index=0, compute_type=compute,
            download_root=str(CACHE), local_files_only=True,
            cpu_threads=4, num_workers=1,
        )
        # Pinned faster-whisper 1.2.1 provides this bundled Silero VAD interface.
        self.vad = get_vad_model()
        self.vad(np.zeros(16384, dtype=np.float32))
        warmup, _ = self.model.transcribe(
            np.zeros(16000, dtype=np.float32), language="en",
            beam_size=1, condition_on_previous_text=False, vad_filter=False,
        )
        list(warmup)
        print("Whisper and speech detection are ready.", flush=True)

    def capture(self, timer_due, timeout=None):
        """Record one utterance. Input closes before returning any outcome."""
        chunks = queue.Queue(maxsize=80)
        overflow = threading.Event()
        history = deque(maxlen=24)  # Approximately 1.2 seconds at 50 ms per chunk.
        preroll = deque(maxlen=10)  # Preserve the onset before VAD recognizes speech.
        clip = []
        gate = SpeechGate()
        analysis_samples = 0
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)

        def receive(data, frames, time_info, status):
            if status:
                overflow.set()
            try:
                chunks.put_nowait(bytes(data))
            except queue.Full:
                overflow.set()

        with sd.RawInputStream(
            device=self.device, samplerate=self.rate,
            blocksize=max(1, int(self.rate * 0.05)),
            channels=1, dtype="int16", callback=receive,
        ):
            deadline = None if timeout is None else time.monotonic() + timeout
            if timeout is None:
                print("\nLISTENING: Jarvis at the start or end of your command.", flush=True)
            else:
                print(f"\nLISTENING for your answer: {timeout:.0f} seconds remaining.", flush=True)
            while True:
                if timer_due():
                    return Capture("timer")
                if deadline is not None and time.monotonic() >= deadline:
                    return Capture("timeout")
                if overflow.is_set():
                    raise RuntimeError("Audio overflow. Stopped rather than act on incomplete speech.")
                try:
                    raw = chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                # Read signed 16-bit mono, then resample with PyAV to 16 kHz float32.
                source = np.frombuffer(raw, dtype=np.int16).reshape(1, -1)
                frame = av.AudioFrame.from_ndarray(source, format="s16", layout="mono")
                frame.sample_rate = self.rate
                for converted in resampler.resample(frame):
                    audio = converted.to_ndarray().reshape(-1).astype(np.float32, copy=True)
                    if not audio.size:
                        continue
                    history.append(audio)
                    preroll.append(audio)
                    if gate.active:
                        clip.append(audio)
                    analysis_samples += audio.size
                    # Re-evaluate a bounded recent window, not an ever-growing recording.
                    if analysis_samples < 2048:
                        continue
                    seconds = analysis_samples / 16000
                    analysis_samples = 0
                    recent = np.concatenate(tuple(history))[-16384:]
                    padding = (-len(recent)) % 512
                    if padding:
                        recent = np.pad(recent, (0, padding))
                    probabilities = np.asarray(self.vad(recent)).reshape(-1)
                    probability = float(np.max(probabilities[-4:]))
                    status = gate.feed(probability, seconds)
                    if status == "start":
                        clip = list(preroll)
                        print("Speech detected...", flush=True)
                    elif status == "complete":
                        return Capture("audio", np.concatenate(clip).astype(np.float32))
                    elif status == "discard":
                        return Capture("discarded")

    def transcribe(self, audio):
        started = time.perf_counter()
        segments, _ = self.model.transcribe(
            audio, language="en", task="transcribe",
            beam_size=5, temperature=0.0, condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 250},
            no_speech_threshold=0.6,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        print(f"Transcription: {time.perf_counter() - started:.2f} seconds", flush=True)
        return text
