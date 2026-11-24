"""JARVIS per-PC settings.

Everything that's different on each PC (mic, location, hotkeys) lives in
config.json next to this file. Updates replace the code files but never
config.json, so nobody loses their settings when JARVIS updates.

config.json is created automatically the first time JARVIS starts.
To pick a different mic later: open config.json and set "mic_device": null,
then start JARVIS again and it will ask.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "mic_device": None,   # asked on first start
    "latitude": None,     # e.g. 41.88  (weather needs these)
    "longitude": None,    # e.g. -87.63 (west = negative)
    "fahrenheit": True,   # false = Celsius and km/h
    "clip_key": "F4",     # NVIDIA: save the last 30 seconds
    "record_key": "F3",   # NVIDIA: start/stop recording
}

# F1 = 0x70 ... F12 = 0x7B (Windows virtual-key codes)
F_KEYS = {f"F{i}": 0x6F + i for i in range(1, 13)}


def key_code(name):
    return F_KEYS.get(str(name).strip().upper(), 0x73)


def _pick_mic():
    import sounddevice as sd
    inputs = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
              if d["max_input_channels"] > 0]
    valid = {i for i, _ in inputs}
    print("\nWhich microphone should JARVIS use?\n")
    for i, name in inputs:
        print(f"  {i}: {name}")
    default = sd.default.device[0]
    hint = f" (Enter = Windows default, {default})" if default in valid else ""
    while True:
        raw = input(f"\nType the number{hint}: ").strip()
        if raw == "" and default in valid:
            return int(default)
        if raw.isdigit() and int(raw) in valid:
            return int(raw)
        print("That number isn't in the list.")


def save(data):
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load():
    data = dict(DEFAULTS)
    changed = not CONFIG_PATH.is_file()
    if not changed:
        data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        # add any settings that newer versions introduced
        changed = any(k not in json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                      for k in DEFAULTS)
    if data["mic_device"] is None:
        data["mic_device"] = _pick_mic()
        changed = True
    if changed:
        save(data)
        print(f"Settings saved to {CONFIG_PATH.name}.", flush=True)
    return data


CONFIG = load()
