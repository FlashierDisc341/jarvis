"""System output volume and named-window management. No in-app automation."""
import ctypes
from ctypes import wintypes
import re
import time

import jarvis_processes as processes
from jarvis_math import number
from jarvis_time import ParseError

U = processes.USER32
U.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
U.ShowWindowAsync.restype = wintypes.BOOL
U.SetForegroundWindow.argtypes = [wintypes.HWND]
U.SetForegroundWindow.restype = wintypes.BOOL
U.GetForegroundWindow.argtypes = []
U.GetForegroundWindow.restype = wintypes.HWND
U.IsIconic.argtypes = [wintypes.HWND]
U.IsIconic.restype = wintypes.BOOL
U.IsZoomed.argtypes = [wintypes.HWND]
U.IsZoomed.restype = wintypes.BOOL


def volume_command(text):
    """Parse only. Returns (operation, amount), None, or raises ParseError."""
    text = " ".join(text.casefold().strip(" .,?!").split())
    if text in {"what is the volume", "what's the volume", "what volume is it",
                "what is the current volume", "volume status", "check volume"}:
        return "status", None
    if text in {"mute", "mute audio", "mute sound", "mute volume", "mute the volume",
                "mute the sound", "mute the audio"}:
        return "mute", None
    if text in {"unmute", "unmute audio", "unmute sound", "unmute volume",
                "unmute the volume", "unmute the sound", "unmute the audio"}:
        return "unmute", None
    match = re.fullmatch(r"(?:set |change |turn )?(?:the )?volume (?:to )?(.+?)(?: percent|%)?", text)
    if match and not match.group(1).startswith(("up", "down")):
        value = float(number(match.group(1)))
        if not 0 <= value <= 100:
            raise ParseError("Volume must be from zero to one hundred percent")
        return "set", value
    match = re.fullmatch(
        r"(?:(?:turn |put )(?:the )?)?volume (up|down)"
        r"(?: (?:by )?(.+?)(?: percent| percentage points|%)?)?", text
    )
    if match:
        step = float(number(match.group(2))) if match.group(2) else 5.0
        if not 0 < step <= 100:
            raise ParseError("Use a volume change from one to one hundred percentage points")
        return ("up" if match.group(1) == "up" else "down"), step
    if text in {"increase volume", "increase the volume", "turn it up", "louder"}:
        return "up", 5.0
    if text in {"decrease volume", "decrease the volume", "turn it down", "quieter"}:
        return "down", 5.0
    return None


def endpoint():
    # Lazy import keeps unrelated controls available if pycaw is missing.
    from pycaw.pycaw import AudioUtilities
    device = AudioUtilities.GetSpeakers()
    if device is None:
        raise RuntimeError("Windows has no default playback device.")
    return device, device.EndpointVolume


def inspect_volume():
    device, volume = endpoint()
    return {
        "id": str(device.id),
        "name": str(device.FriendlyName),
        "level": float(volume.GetMasterVolumeLevelScalar()) * 100,
        "muted": bool(volume.GetMute()),
    }


def volume_target(operation, value, state):
    if operation == "set":
        return value
    if operation == "up":
        return min(100, state["level"] + value)
    if operation == "down":
        return max(0, state["level"] - value)
    return None


def apply_volume(operation, target, expected):
    device, volume = endpoint()
    if str(device.id) != expected["id"]:
        raise ValueError("The playback device changed. Please ask again.")
    if abs(float(volume.GetMasterVolumeLevelScalar()) * 100 - expected["level"]) > 1:
        raise ValueError("The volume changed while waiting. Please ask again.")
    if bool(volume.GetMute()) != expected["muted"]:
        raise ValueError("The mute state changed while waiting. Please ask again.")
    if operation == "mute":
        volume.SetMute(1, None)
    elif operation == "unmute":
        volume.SetMute(0, None)
    elif operation in {"set", "up", "down"}:
        if target is None or not 0 <= target <= 100:
            raise ValueError("The requested volume is outside the allowed range.")
        # Preserve mute state: a volume change does not silently unmute output.
        volume.SetMasterVolumeLevelScalar(target / 100, None)
    else:
        raise ValueError("Unsupported volume action.")
    state = {
        "level": float(volume.GetMasterVolumeLevelScalar()) * 100,
        "muted": bool(volume.GetMute()),
    }
    if operation == "mute":
        return ("System output is muted, sir." if state["muted"]
                else "Windows did not confirm that output was muted, sir.")
    if operation == "unmute":
        return (f"System output is unmuted at {state['level']:.0f} percent, sir."
                if not state["muted"] else "Windows did not confirm unmuting, sir.")
    suffix = " and remains muted" if state["muted"] else ""
    return f"System volume is {state['level']:.0f} percent{suffix}, sir."


def window_action(operation, group, window):
    item = next(p for p in group["processes"] if p["pid"] == window["pid"])
    processes.checked(item, window_only=True)
    # Revalidate the window/PID immediately before changing its state.
    current = next((w for w in processes.windows()
                    if w["hwnd"] == window["hwnd"] and w["pid"] == window["pid"]
                    and w["title"] == window["title"]), None)
    if current is None:
        return "That window changed or closed. Please ask again, sir."
    hwnd = window["hwnd"]
    if operation == "switch":
        if U.IsIconic(hwnd):
            U.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
            time.sleep(0.1)
        U.SetForegroundWindow(hwnd)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if U.GetForegroundWindow() == hwnd:
                return f"{group['name']} is in the foreground, sir."
            time.sleep(0.05)
        return f"Windows did not let me bring {group['name']} to the foreground, sir."
    codes = {"minimize": 6, "maximize": 3, "restore": 9}
    if operation not in codes:
        raise ValueError("Unsupported window action.")
    if not U.ShowWindowAsync(hwnd, codes[operation]):
        return f"Windows did not accept the {operation} request, sir."
    check = {
        "minimize": lambda: bool(U.IsIconic(hwnd)),
        "maximize": lambda: bool(U.IsZoomed(hwnd)),
        "restore": lambda: not U.IsIconic(hwnd) and not U.IsZoomed(hwnd),
    }[operation]
    deadline = time.monotonic() + 0.7
    while time.monotonic() < deadline:
        if check():
            word = {"minimize": "minimized", "maximize": "maximized", "restore": "restored"}[operation]
            return f"The {group['name']} window is {word}, sir."
        time.sleep(0.05)
    return f"I sent the {operation} request, but could not confirm the window state, sir."


def show_desktop():
    from comtypes.client import CreateObject
    shell = CreateObject("Shell.Application", dynamic=True)
    shell.MinimizeAll()
    return "Minimizing windows to show the desktop, sir."
