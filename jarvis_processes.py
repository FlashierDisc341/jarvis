"""Windows app lifecycle helpers. No shell commands or privilege elevation.
Normal close sends WM_CLOSE; forced end uses a fixed, confirmed PID snapshot.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re

import psutil

USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
USER32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]
USER32.EnumWindows.restype = wintypes.BOOL
USER32.IsWindowVisible.argtypes = [wintypes.HWND]
USER32.IsWindowVisible.restype = wintypes.BOOL
USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
USER32.GetWindowTextLengthW.restype = ctypes.c_int
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.GetWindowTextW.restype = ctypes.c_int
USER32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.GetClassNameW.restype = ctypes.c_int
USER32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
USER32.PostMessageW.restype = wintypes.BOOL
KERNEL32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
KERNEL32.ProcessIdToSessionId.restype = wintypes.BOOL

# Friendly names for common apps, including ones that run only in the tray.
APP_NAMES = {
    "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox", "opera.exe": "Opera",
    "discord.exe": "Discord", "steam.exe": "Steam",
    "notepad.exe": "Notepad", "calculatorapp.exe": "Calculator",
    "calc.exe": "Calculator", "applemusic.exe": "Apple Music",
    "fl64.exe": "FL Studio", "fl.exe": "FL Studio",
    "obs64.exe": "OBS Studio", "code.exe": "Visual Studio Code",
    "resolve.exe": "DaVinci Resolve", "spotify.exe": "Spotify",
    "epicgameslauncher.exe": "Epic Games Launcher",
    "explorer.exe": "File Explorer", "mspaint.exe": "Paint",
    "vlc.exe": "VLC media player", "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel", "powerpnt.exe": "Microsoft PowerPoint",
}
# Not a security sandbox. These prevent common accidental system/terminal kills.
PROTECTED_NAMES = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
    "dwm.exe", "sihost.exe", "fontdrvhost.exe", "taskhostw.exe",
    "runtimebroker.exe", "applicationframehost.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "securityhealthsystray.exe", "ctfmon.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
    "conhost.exe", "openconsole.exe", "python.exe", "pythonw.exe", "py.exe",
}


def session_id(pid):
    value = wintypes.DWORD()
    if not KERNEL32.ProcessIdToSessionId(pid, ctypes.byref(value)):
        raise OSError("Cannot check process session.")
    return value.value


def protected_pids():
    me = psutil.Process()
    return {me.pid, *(p.pid for p in me.parents())}


def allowed(process, force=False, window_only=False):
    if window_only:
        # Focusing/minimizing is not termination: the user's terminal may be selected.
        me = psutil.Process()
        return (
            process.pid > 4
            and process.username().casefold() == me.username().casefold()
            and session_id(process.pid) == session_id(me.pid)
        )
    if process.pid <= 4 or process.pid in protected_pids():
        return False
    name = process.name().casefold()
    if name in PROTECTED_NAMES or (force and name == "explorer.exe"):
        return False
    me = psutil.Process()
    return (
        process.username().casefold() == me.username().casefold()
        and session_id(process.pid) == session_id(me.pid)
    )


def snapshot(process):
    return {
        "pid": process.pid,
        "created": process.create_time(),
        "exe": process.exe(),
    }


def checked(item, force=False, window_only=False):
    process = psutil.Process(item["pid"])
    if (
        process.create_time() != item["created"]
        or os.path.normcase(process.exe()) != os.path.normcase(item["exe"])
        or not allowed(process, force, window_only)
    ):
        raise ValueError("The process identity changed or is protected.")
    return process


def windows():
    result = []

    @ENUMPROC
    def collect(hwnd, unused):
        if not USER32.IsWindowVisible(hwnd):
            return True
        length = USER32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(hwnd, title, length + 1)
        klass = ctypes.create_unicode_buffer(256)
        USER32.GetClassNameW(hwnd, klass, 256)
        # Never treat the desktop/taskbar as an Explorer folder window.
        if klass.value in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
            return True
        pid = wintypes.DWORD()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        result.append({"hwnd": int(hwnd), "pid": pid.value, "title": title.value})
        return True

    if not USER32.EnumWindows(collect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def discover(force=False, catalogue=(), window_only=False):
    """Only user-session GUI apps or named known apps; never match window text."""
    visible = windows()
    window_pids = {w["pid"] for w in visible}
    groups = {}
    for process in psutil.process_iter():
        try:
            exe_name = process.name().casefold()
            if process.pid not in window_pids and exe_name not in APP_NAMES:
                continue
            if not allowed(process, force, window_only):
                continue
            item = snapshot(process)
            if not item["exe"]:
                continue
            group_key = os.path.normcase(item["exe"])
            group = groups.setdefault(group_key, {
                "name": APP_NAMES.get(exe_name, Path(item["exe"]).stem),
                "aliases": [Path(item["exe"]).stem],
                "processes": [], "windows": [],
            })
            group["processes"].append(item)
        except (psutil.Error, OSError):
            continue
    output = []
    for group in groups.values():
        pids = {p["pid"] for p in group["processes"]}
        group["windows"] = [w for w in visible if w["pid"] in pids]
        executable = os.path.normcase(group["processes"][0]["exe"])
        names = []
        for name, app_id in catalogue:
            # StartApps may use a known-folder GUID instead of C:\Program Files.
            if app_id.startswith("{") and "}\\" in app_id:
                tail = os.path.normcase(app_id.split("}", 1)[1])
                matches = executable.endswith(tail)
            else:
                matches = executable == os.path.normcase(app_id)
            if matches:
                names.append(name)
        if names:
            group["aliases"].extend(names)
            group["name"] = min(names, key=len)
        # FL's executable is FL64.exe in both versions; the install path differs.
        if group["name"] == "FL Studio":
            match = re.search(r"FL Studio\s+(\d{2,4})",
                              group["processes"][0]["exe"], re.IGNORECASE)
            if match:
                group["name"] += " " + match.group(1)
        if force or group["windows"]:
            output.append(group)
    return sorted(output, key=lambda g: (g["name"].casefold(), g["processes"][0]["pid"]))


def close_window(group, window):
    try:
        item = next(p for p in group["processes"] if p["pid"] == window["pid"])
        checked(item)
        live = next((w for w in windows() if w["hwnd"] == window["hwnd"]
                     and w["pid"] == window["pid"] and w["title"] == window["title"]), None)
        if live is None:
            return "That window changed or closed. Please ask again, sir."
        if not USER32.PostMessageW(window["hwnd"], 0x0010, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        # Only omit our spoken reminder. Never bypass an application's own prompts.
        quiet_close_apps = {
            "discord.exe", "applemusic.exe", "spotify.exe",
            "music.ui.exe", "music presence.exe",
        }
        if Path(item["exe"]).name.casefold() in quiet_close_apps:
            return f"I sent {group['name']} a close request, sir."
        return f"I sent {group['name']} a close request. Check for a save prompt, sir."
    except (psutil.Error, OSError, ValueError, StopIteration) as error:
        print("Close error:", error, flush=True)
        return "I could not close that window, sir."


def prepare_end(group):
    """Capture the selected app's current processes and descendants BEFORE consent."""
    found = {}
    for item in group["processes"]:
        try:
            root = checked(item, force=True)
            tree = [root, *root.children(recursive=True)]
            for process in tree:
                if not allowed(process, force=True):
                    raise ValueError("This app tree includes a protected process.")
                saved = snapshot(process)
                found[(saved["pid"], saved["created"])] = saved
        except psutil.NoSuchProcess:
            continue
    if not found:
        raise ValueError("The selected app has already stopped.")
    return list(found.values())


def force_end(items):
    # Validate the complete captured set again. Do not search/kill new PIDs here.
    processes = []
    for item in items:
        try:
            processes.append(checked(item, force=True))
        except psutil.NoSuchProcess:
            continue
    if not processes:
        return "Those processes have already stopped, sir."
    errors = 0
    attempted = []
    for process in reversed(processes):
        try:
            if not allowed(process, force=True):
                errors += 1
                continue
            process.kill()  # On Windows, terminate() is ALSO forceful.
            attempted.append(process)
        except psutil.NoSuchProcess:
            continue
        except (psutil.Error, OSError):
            errors += 1
    gone, alive = psutil.wait_procs(attempted, timeout=2)
    if errors or alive:
        return (
            f"{len(gone)} selected processes stopped, but some could not be stopped, sir."
        )
    return (
        "The selected processes have stopped. An app or launcher may restart them, sir."
    )
