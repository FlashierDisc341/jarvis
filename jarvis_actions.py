"""JARVIS actions v5: local app discovery, folder lookup and clarification.
No LLM, arbitrary command execution, recursive file indexing or file deletion.
Only names from Windows' Start-app catalogue can become app launch targets.
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import jarvis_processes as lifecycle
from jarvis_time import CalendarTimers, ParseError
import jarvis_desktop as desktop
from jarvis_math import calculator
from jarvis_help import help_reply
import jarvis_monitor as monitoring
from jarvis_organizer import Organizer, Draft, is_request as is_organizer_request
import jarvis_extras as extras

ROOT = Path(__file__).resolve().parent
WINDOWS = Path(os.environ.get("SystemRoot", r"C:\Windows"))
POWERSHELL = WINDOWS / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
EXPLORER = WINDOWS / "explorer.exe"

# These are aliases for app names, NOT executable paths.
APP_ALIASES = {
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "vs code": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "obs": "OBS Studio",
    "epic": "Epic Games Launcher",
    "epic games": "Epic Games Launcher",
    "resolve": "DaVinci Resolve",
    "da vinci": "DaVinci Resolve",
    "opera": "Opera GX Browser",
    "opera gx": "Opera GX Browser",
    "g mod": "Garry's Mod",
}
BLOCKED_WORDS = (
    "uninstall", "unload kernel", "reset settings",
    "safe mode", "recovery drive", "windows memory diagnostic",
)
KNOWN_FOLDERS = {
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
FOLDER_ALIASES = {
    "document": "documents", "docs": "documents",
    "download": "downloads", "picture": "pictures", "video": "videos",
}
STOP_COMMANDS = {"goodbye", "stop listening", "exit", "quit"}
CANCEL_COMMANDS = {"cancel", "never mind", "nevermind", "no", "no thanks"}


def normalize(text):
    return " ".join(text.casefold().strip().split())



@lru_cache(maxsize=2048)
def spoken_years(text):
    """Normalize common spoken 2000-2099 years in names and choice answers."""
    ones = ("zero one two three four five six seven eight nine ten eleven twelve "
            "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
    tens = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
            60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}
    replacements = {}
    for value in range(100):
        if value < 20:
            suffix = ones[value]
        else:
            suffix = tens[value // 10 * 10]
            if value % 10:
                suffix += " " + ones[value % 10]
        year = str(2000 + value)
        if value:
            replacements["two thousand " + suffix] = year
            replacements["two thousand and " + suffix] = year
        if value >= 10:
            replacements["twenty " + suffix] = year
        elif value:
            replacements["twenty oh " + suffix] = year
    replacements["two thousand"] = "2000"
    text = normalize(text).replace("-", " ")
    pattern = r"\b(?:" + "|".join(
        re.escape(phrase) for phrase in sorted(replacements, key=len, reverse=True)
    ) + r")\b"
    return re.sub(pattern, lambda match: replacements[match.group()], text)


def key(text):
    # Treat spaces/punctuation alike: "note pad" and "notepad" have one key.
    return "".join(c for c in spoken_years(text) if c.isalnum())


def clean_target(text):
    text = normalize(text)
    while text.startswith(("the ", "my ")):
        text = text.split(" ", 1)[1]
    return text


def folder_key(text):
    text = clean_target(text)
    if text.startswith("folder "):
        text = clean_target(text[7:])
    if text.endswith(" folder"):
        text = text[:-7].strip()
    return FOLDER_ALIASES.get(text, text)


@dataclass(frozen=True)
class Target:
    kind: str
    name: str
    value: str


@dataclass(frozen=True)
class Result:
    reply: str
    choices: tuple = ()
    stop: bool = False
    handled: bool = True


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def known_folder(name):
    """Ask Windows for the real location, including folder redirection."""
    guid = GUID.from_buffer_copy(uuid.UUID(KNOWN_FOLDERS[name]).bytes_le)
    shell = ctypes.WinDLL("shell32")
    ole = ctypes.WinDLL("ole32")
    get_path = shell.SHGetKnownFolderPath
    get_path.argtypes = [
        ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_path.restype = ctypes.c_long
    free = ole.CoTaskMemFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = None
    pointer = ctypes.c_void_p()
    try:
        result = get_path(ctypes.byref(guid), 0, None, ctypes.byref(pointer))
        if result != 0 or not pointer.value:
            raise OSError(f"Windows could not locate {name}: HRESULT {result}")
        return Path(ctypes.wstring_at(pointer.value))
    finally:
        if pointer.value:
            free(pointer)


def question(candidates, uncertain=False):
    choices = tuple(candidates)
    if not choices:
        return Result("I could not find that app or folder, sir.")
    if len(choices) > 5:
        return Result(
            f"I found {len(choices)} matches. Please give a more specific name, sir."
        )
    for number, target in enumerate(choices, 1):
        print(f"Choice {number}: {target.name} [{target.kind}]", flush=True)
    if len(choices) == 1:
        return Result(f"Did you mean {choices[0].name}, sir?", choices)
    labels = "; ".join(
        f"{number}, {target.name}" for number, target in enumerate(choices, 1)
    )
    prefix = "The closest matches are" if uncertain else "I found"
    return Result(f"{prefix}: {labels}. Which one, sir?", choices)


def choose(text, choices):
    """Only resolve against the choices currently waiting for an answer."""
    text = normalize(text).strip(".,?!")
    if len(choices) == 1 and text in {"yes", "yes please", "correct", "that's right"}:
        return choices[0]
    numbers = {
        "1": 0, "one": 0, "first": 0,
        "2": 1, "two": 1, "second": 1,
        "3": 2, "three": 2, "third": 2,
        "4": 3, "four": 3, "fourth": 3,
        "5": 4, "five": 4, "fifth": 4,
    }
    number_text = re.sub(r"^(?:the |option |number )+", "", text)
    number_text = re.sub(r"^(first|second|third|fourth|fifth) one$", r"\1", number_text)
    index = numbers.get(number_text)
    if index is not None and index < len(choices):
        return choices[index]
    wanted = key(clean_target(text))
    exact = [item for item in choices if key(item.name) == wanted]
    if len(exact) == 1:
        return exact[0]
    # A unique literal fragment is accepted only within this explicit choice list.
    partial = [item for item in choices if len(wanted) >= 3 and wanted in key(item.name)]
    return partial[0] if len(partial) == 1 else None


class Actions:
    def __init__(self):
        self.calendar = CalendarTimers()
        self.organizer = Organizer(ROOT / "data" / "jarvis-organizer.sqlite3")
        self.last_reply = ''
        self.apps = []
        self.blocked = set()
        self.catalogue_error = None
        self.refresh()

    def refresh(self):
        # Fixed read-only command. No recognized speech is inserted here.
        script = (
            "$ErrorActionPreference = 'Stop'; "
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "@(Get-StartApps | Select-Object Name, AppID) | ConvertTo-Json -Compress"
        )
        try:
            output = subprocess.run(
                [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, encoding="utf-8-sig",
                errors="replace", timeout=30, check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            rows = json.loads(output.stdout)
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                raise ValueError("Windows did not return an app list.")
            apps, blocked, seen = [], set(), set()
            for row in rows:
                name = str(row.get("Name", "")).strip()
                app_id = str(row.get("AppID", "")).strip()
                if not name or not app_id:
                    continue
                # Do not include uninstall/reset shortcuts or web documentation links.
                if (any(word in normalize(name) for word in BLOCKED_WORDS)
                        or app_id.casefold().startswith(("http:", "https:"))):
                    blocked.add(key(name))
                    continue
                if app_id in seen:
                    continue
                seen.add(app_id)
                apps.append(Target("app", name, app_id))
            self.apps = sorted(apps, key=lambda item: item.name.casefold())
            self.blocked = blocked
            self.catalogue_error = None
            print(f"App catalogue: {len(self.apps)} launch entries loaded.", flush=True)
            return True
        except (OSError, subprocess.SubprocessError, ValueError, TypeError) as error:
            self.catalogue_error = str(error)
            print("App catalogue unavailable:", error, flush=True)
            return False

    def launch(self, target):
        if target.kind == "monitor_memory":
            return self.monitor_memory(target)
        if target.kind.startswith("desktop_"):
            return self.desktop_action(target)
        if target.kind.startswith("life_"):
            return self.lifecycle_action(target)
        try:
            if target.kind == "explorer":
                subprocess.Popen([str(EXPLORER)], shell=False)
            elif target.kind == "folder":
                folder = Path(target.value)
                if not folder.is_dir():
                    raise FileNotFoundError(f"Folder no longer exists: {folder}")
                os.startfile(str(folder))
            elif target.kind == "app":
                if target not in self.apps:
                    raise ValueError("App is not in the current catalogue.")
                app_id = target.value
                if re.fullmatch(r"steam://rungameid/\d+", app_id, re.IGNORECASE):
                    os.startfile(app_id)
                elif Path(app_id).is_absolute() and Path(app_id).is_file():
                    # A literal path supplied by Windows, not by spoken text.
                    os.startfile(app_id)
                else:
                    os.startfile("shell:AppsFolder\\" + app_id)
            else:
                raise ValueError("Unsupported launch target.")
        except (OSError, ValueError) as error:
            print("Launch error:", error, flush=True)
            return Result(f"I could not open {target.name}, sir.")
        # Shell dispatch is not proof that an application's window is ready.
        return Result(f"Opening {target.name}, sir.")

    def match_apps(self, name):
        wanted = key(name)
        if wanted in self.blocked:
            return Result("That entry is excluded from voice launching, sir.")
        if self.catalogue_error and not self.apps:
            return Result("The app catalogue is unavailable, sir.")
        aliases = {key(alias): key(value) for alias, value in APP_ALIASES.items()}
        wanted = aliases.get(wanted, wanted)
        exact = [item for item in self.apps if key(item.name) == wanted]
        if len(exact) == 1:
            return self.launch(exact[0])
        if exact:
            return question(exact)
        if len(wanted) < 3:
            return Result("Please give a longer app name, sir.")
        partial = [item for item in self.apps if wanted in key(item.name)]
        if partial:
            return question(partial)
        ranked = sorted(
            ((SequenceMatcher(None, wanted, key(item.name)).ratio(), item)
             for item in self.apps),
            key=lambda pair: pair[0], reverse=True,
        )
        suggestions = [item for score, item in ranked[:5] if score >= 0.65]
        return question(suggestions, uncertain=True)

    def open_request(self, text):
        target_name = clean_target(text)
        if not target_name:
            return Result("Please include the app or folder name, sir.")
        if key(target_name) in {"files", "fileexplorer", "explorer"}:
            return self.launch(Target("explorer", "File Explorer", ""))

        # A single explicit child folder in a known root, not a whole-disk search.
        child_request = re.fullmatch(r"(.+?)\s+in\s+(.+)", target_name)
        if child_request:
            child_name = folder_key(child_request.group(1))
            parent_name = folder_key(child_request.group(2))
            if parent_name in KNOWN_FOLDERS:
                try:
                    parent = known_folder(parent_name)
                    children = [
                        Target("folder", entry.name, str(entry))
                        for entry in parent.iterdir()
                        if entry.is_dir()
                    ]
                except OSError as error:
                    print("Folder lookup error:", error, flush=True)
                    return Result(f"I could not read the {parent_name} folder, sir.")
                exact = [item for item in children if key(item.name) == key(child_name)]
                if len(exact) == 1:
                    return self.launch(exact[0])
                if exact:
                    return question(exact)
                partial = [
                    item for item in children
                    if len(key(child_name)) >= 3 and key(child_name) in key(item.name)
                ]
                return question(partial)

        name = folder_key(target_name)
        if name in {"jarvis", "project"}:
            return self.launch(Target("folder", "the Jarvis folder", str(ROOT)))
        if name in KNOWN_FOLDERS:
            try:
                folder = known_folder(name)
                return self.launch(Target("folder", name.capitalize(), str(folder)))
            except OSError as error:
                print("Folder lookup error:", error, flush=True)
                return Result(f"I could not locate {name}, sir.")
        return self.match_apps(target_name)


    def lifecycle_request(self, name, force=False):
        name = clean_target(name)
        if not name:
            return Result("Please include an application name, sir.")
        wanted = key(APP_ALIASES.get(normalize(name), name))
        if len(wanted) < 3:
            return Result("Please give a longer application name, sir.")
        try:
            groups = lifecycle.discover(force, [(app.name, app.value) for app in self.apps])
        except (OSError, lifecycle.psutil.Error) as error:
            print("App lookup error:", error, flush=True)
            return Result("I could not inspect running applications, sir.")
        exact, partial = [], []
        for group in groups:
            keys = [key(group["name"]), *(key(a) for a in group["aliases"])]
            target = Target("life_end" if force else "life_close",
                            group["name"], json.dumps(group))
            if wanted in keys:
                exact.append(target)
            elif any(wanted in item for item in keys):
                partial.append(target)
        matches = exact or partial
        if not matches:
            return Result(
                "I could not find a supported running app with that name. "
                "System processes and the voice-control terminal are excluded, sir."
            )
        # Identical labels still get distinct choice numbers.
        if len(matches) == 1:
            return self.lifecycle_action(matches[0])
        return question(matches)

    def lifecycle_action(self, target):
        data = json.loads(target.value)
        try:
            if target.kind == "life_close":
                windows = data["windows"]
                if len(windows) == 1:
                    return Result(lifecycle.close_window(data, windows[0]))
                choices = [
                    Target("life_window",
                           f"{target.name} window {number}: {window['title'][:60]}",
                           json.dumps({"group": data, "window": window}))
                    for number, window in enumerate(windows, 1)
                ]
                return question(choices)
            if target.kind == "life_window":
                return Result(lifecycle.close_window(data["group"], data["window"]))
            if target.kind == "life_end":
                items = lifecycle.prepare_end(data)
                confirmation = Target("life_confirm", target.name, json.dumps(items))
                return Result(
                    f"Force-ending {target.name} will stop its captured "
                    f"{len(items)} processes, including captured child processes. "
                    "Unsaved work may be lost. Say confirm end task, or cancel, sir.",
                    (confirmation,),
                )
            if target.kind == "life_confirm":
                # This branch is called ONLY by the explicit confirmation handler.
                return Result(lifecycle.force_end(data))
        except (OSError, ValueError, lifecycle.psutil.Error) as error:
            print("Lifecycle action error:", error, flush=True)
            return Result("That action could not proceed safely. Please ask again, sir.")
        return Result("That application action is not configured, sir.")



    def volume_request(self, operation, value):
        try:
            state = desktop.inspect_volume()
            print(f"Default playback device: {state['name']}", flush=True)
            if operation == "status":
                muted = " and muted" if state["muted"] else ""
                return Result(f"System volume is {state['level']:.0f} percent{muted}, sir.")
            target = desktop.volume_target(operation, value, state)
            loud_increase = target is not None and target > state["level"] and target >= 80
            loud_unmute = operation == "unmute" and state["muted"] and state["level"] >= 80
            if loud_increase or loud_unmute:
                level = target if target is not None else state["level"]
                data = {"operation": operation, "target": target, "state": state}
                choice = Target("volume_confirm", f"volume {level:.0f} percent", json.dumps(data))
                return Result(
                    f"That would {'unmute output at' if loud_unmute else 'raise volume to'} "
                    f"{level:.0f} percent. Say confirm volume, or cancel, sir.", (choice,)
                )
            return Result(desktop.apply_volume(operation, target, state))
        except Exception as error:
            print("Volume control error:", type(error).__name__, error, flush=True)
            return Result(
                "I could not access system volume. Check the terminal and the pycaw installation, sir."
            )

    def confirm_volume(self, target):
        try:
            data = json.loads(target.value)
            return Result(desktop.apply_volume(data["operation"], data["target"], data["state"]))
        except Exception as error:
            print("Volume confirmation error:", type(error).__name__, error, flush=True)
            return Result("The volume change was not confirmed. Please ask again, sir.")

    def window_request(self, operation, name):
        name = clean_target(name)
        wanted = key(APP_ALIASES.get(normalize(name), name))
        if len(wanted) < 3:
            return Result("Please give a longer application name, sir.")
        try:
            groups = lifecycle.discover(
                catalogue=[(app.name, app.value) for app in self.apps], window_only=True
            )
        except (OSError, lifecycle.psutil.Error) as error:
            print("Window discovery error:", error, flush=True)
            return Result("I could not inspect open windows, sir.")
        exact, partial = [], []
        for group in groups:
            keys = [key(group["name"]), *(key(alias) for alias in group["aliases"])]
            data = {"operation": operation, "group": group}
            candidate = Target("desktop_group", group["name"], json.dumps(data))
            if wanted in keys:
                exact.append(candidate)
            elif any(wanted in candidate_key for candidate_key in keys):
                partial.append(candidate)
        matches = exact or partial
        if not matches:
            return Result("I could not find a matching open window. Use open to launch an app, sir.")
        return self.desktop_action(matches[0]) if len(matches) == 1 else question(matches)

    def desktop_action(self, target):
        try:
            data = json.loads(target.value)
            group, operation = data["group"], data["operation"]
            if target.kind == "desktop_group":
                windows = group["windows"]
                if len(windows) == 1:
                    return Result(desktop.window_action(operation, group, windows[0]))
                choices = [
                    Target("desktop_window",
                           f"{group['name']} window {index}: {window['title'][:60]}",
                           json.dumps({"operation": operation, "group": group, "window": window}))
                    for index, window in enumerate(windows, 1)
                ]
                return question(choices)
            if target.kind == "desktop_window":
                return Result(desktop.window_action(operation, group, data["window"]))
        except (OSError, ValueError, StopIteration, lifecycle.psutil.Error) as error:
            print("Window action error:", error, flush=True)
            return Result("I could not change that window. Please ask again, sir.")
        return Result("That window action is not configured, sir.")


    def monitor_instance(self):
        if not hasattr(self, "_monitor"):
            self._monitor = monitoring.Monitor()
        return self._monitor

    def monitor_memory(self, target):
        try:
            data = json.loads(target.value)
            return Result(self.monitor_instance().memory_report(
                data["path"], [(app.name, app.value) for app in self.apps]
            ))
        except (ValueError, KeyError, OSError, monitoring.MonitorError, lifecycle.psutil.Error) as error:
            print("App memory report error:", type(error).__name__, error, flush=True)
            return Result("I could not read that app's memory usage. Check the terminal, sir.")

    def monitor_request(self, command):
        query = monitoring.request(command)
        if query is None:
            return None
        kind, argument = query
        monitor = self.monitor_instance()
        catalogue = [(app.name, app.value) for app in self.apps]
        try:
            if kind == "top_cpu":
                return Result(monitor.top_cpu_report(catalogue))
            if kind != "app_memory":
                return Result(monitor.basic_report(kind))
            name = clean_target(argument)
            wanted = key(APP_ALIASES.get(normalize(name), name))
            if len(wanted) < 3:
                return Result("Please give a longer application name, sir.")
            inventory = monitor.groups(catalogue)
            exact, partial = [], []
            for group in inventory["groups"]:
                keys = [key(group["name"]), *(key(alias) for alias in group["aliases"])]
                # Distinct installations with the same name still get separate choices.
                first_pid = min(item["pid"] for item in group["items"])
                target = Target("monitor_memory",
                                f"{group['name']}, process group {first_pid}",
                                json.dumps({"path": group["path"]}))
                if wanted in keys:
                    exact.append(target)
                elif any(wanted in candidate for candidate in keys):
                    partial.append(target)
            matches = exact or partial
            if not matches:
                return Result(
                    "I found no matching readable process group in your Windows session. "
                    "The app may be closed, named differently, or inaccessible, sir."
                )
            return self.monitor_memory(matches[0]) if len(matches) == 1 else question(matches)
        except (ValueError, OSError, monitoring.MonitorError, lifecycle.psutil.Error) as error:
            print("PC report error:", type(error).__name__, error, flush=True)
            return Result("I could not read that PC report. Check the terminal, sir.")

    def close(self):
        organizer = getattr(self, "organizer", None)
        if organizer is not None:
            organizer.close()

    def has_due(self):
        organizer = getattr(self, "organizer", None)
        return self.calendar.has_due() or (organizer is not None and organizer.has_due())

    def organizer_action(self, raw_command, pending=()):
        own = [item for item in pending if item.kind.startswith("organizer_")]
        if not own and not is_organizer_request(raw_command):
            return None
        organizer = getattr(self, "organizer", None)
        if organizer is None:
            return Result("Notes and reminders are unavailable in this session, sir.")
        draft = None
        if own:
            if len(own) != 1 or len(pending) != 1:
                return Result("That organizer choice is invalid; please ask again, sir.")
            try:
                draft = Draft(own[0].kind, json.loads(own[0].value))
            except (ValueError, TypeError):
                return Result("That organizer choice is invalid; please ask again, sir.")
        answer = organizer.handle(raw_command, draft)
        if answer is None:
            return None
        choices = ()
        if answer.draft is not None:
            choices = (Target(answer.draft.kind, "Organizer",
                              json.dumps(answer.draft.data, ensure_ascii=False)),)
        return Result(answer.text, choices)

    def handle(self, command, pending=()):
        raw_command = " ".join(command.replace("\u2019", "'").strip().split())
        command = normalize(command).strip(".,?!")
        command = re.sub(r"^(?:please |can you |could you )+", "", command)
        command = re.sub(r",?\s+please$", "", command)

        if command in STOP_COMMANDS:
            return Result("Stopping voice control, sir.", stop=True)
        if command in CANCEL_COMMANDS:
            return Result("Cancelled, sir.")
        if pending and any(item.kind.startswith("organizer_") for item in pending):
            if (not any(item.kind == "organizer_dictate" for item in pending)
                    and command in {"repeat that", "say that again", "repeat your last reply"}):
                return Result(getattr(self, "last_reply", "") or "Please confirm or cancel, sir.",
                              tuple(pending))
            # Explicit note dictation is data, never an app/window/system command.
            return self.organizer_action(raw_command, pending)
        if command in {"repeat that", "say that again", "repeat your last reply"}:
            last = getattr(self, "last_reply", "")
            return Result(last or "There is no previous reply to repeat, sir.", tuple(pending))
        # Spoken joke only. Explicit note dictation/confirmation is handled above.
        if command == "jerk it a little":
            return Result("activating goon mode sir")

        new_request = command.startswith(
            ("open ", "launch ", "start ", "close ", "end ", "set ",
             "what ", "what's ", "whats ", "how ", "tell ", "list ",
             "cancel timer", "cancel the timer", "cancel my timer", "cancel all timers",
             "stop timer", "stop the timer", "stop my timer", "stop all timers",
             "timer status", "time remaining ", "switch ", "focus ", "minimize ",
             "maximize ", "restore ", "bring ", "show ", "help", "mute", "unmute",
             "volume ", "increase ", "decrease ", "turn ", "put ", "louder", "quieter",
             "change ", "calculate ", "convert ", "work out ",
             "compute ", "evaluate ", "solve ", "simplify ", "expand ", "factor ",
             "factorise ", "factorize ", "differentiate ", "integrate ",
             "derivative of ", "integral of ",
             "take a note", "make a note", "add a note", "note that ",
             "remind me ", "read ", "archive note ", "delete note ",
             "cancel reminder ", "list archived ", "list cancelled ",
             "system report", "system status", "pc status", "pc report", "resource report",
             "cpu usage", "ram usage", "memory usage", "disk space", "storage report",
             "top cpu usage", "which app ",
             # v10 extras
             "play", "pause", "resume", "skip", "next track", "next song",
             "previous track", "previous song", "last song", "go back a song",
             "search ", "google ", "look up ", "weather", "how's ", "hows ",
             "will it rain", "is it going to rain", "is it rain",
             "screenshot", "take a screenshot", "take screenshot",
             "grab the screen", "capture the screen",
             "good morning", "good afternoon", "good evening",
             "daily briefing", "morning briefing", "briefing", "brief me",
             "flip a coin", "toss a coin", "coin flip", "roll ",
             "clip", "save that", "save the clip",
             "record", "begin recording", "stop recording", "stop the recording",
             "end recording", "end the recording", "finish recording")
        )
        if pending and not new_request:
            if any(item.kind == "volume_confirm" for item in pending):
                if command == "confirm volume" and len(pending) == 1:
                    return self.confirm_volume(pending[0])
                return Result("Say confirm volume, or cancel, sir.", tuple(pending))
            if any(item.kind == "life_confirm" for item in pending):
                if command == "confirm end task" and len(pending) == 1:
                    return self.lifecycle_action(pending[0])
                return Result(
                    "Say confirm end task to force-stop the selected application, "
                    "or cancel, sir.", tuple(pending)
                )
            selected = choose(command, pending)
            if selected:
                return self.launch(selected)
            return Result("Please say a choice number, part of the name, or cancel, sir.",
                          tuple(pending))

        organizer_reply = self.organizer_action(
            re.sub(r"^(?:please |can you |could you )+", "", raw_command, flags=re.I)
        )
        if organizer_reply is not None:
            return organizer_reply

        report = self.monitor_request(command)
        if report is not None:
            return report

        help_text = help_reply(command)
        if help_text is not None:
            return Result(help_text)

        # v10: media keys, search, weather, screenshots, briefing, coin, dice.
        extra_reply = extras.handle(command)
        if extra_reply is not None:
            return Result(extra_reply)
        try:
            volume_plan = desktop.volume_command(command)
        except (ParseError, ValueError) as error:
            return Result(f"{error}, sir.")
        if volume_plan is not None:
            return self.volume_request(*volume_plan)
        if command in {"show desktop", "show the desktop"}:
            try:
                return Result(desktop.show_desktop())
            except Exception as error:
                print("Show desktop error:", error, flush=True)
                return Result("I could not show the desktop, sir.")
        window = re.fullmatch(r"(switch to|focus|minimize|maximize|restore)\s+(.+)", command)
        if window:
            operation = {"switch to": "switch", "focus": "switch"}.get(window.group(1), window.group(1))
            return self.window_request(operation, window.group(2))
        bring = re.fullmatch(r"bring\s+(.+?)\s+to\s+(?:the\s+)?(?:front|foreground)", command)
        if bring:
            return self.window_request("switch", bring.group(1))

        calendar_reply = self.calendar.handle(command)
        if calendar_reply is not None:
            return Result(calendar_reply)

        calculation = calculator(command)
        if calculation is not None:
            return Result(calculation)

        match = re.fullmatch(r"end\s+(?:the\s+)?task[\s,]+(.+)", command)
        if match:
            return self.lifecycle_request(match.group(1), force=True)
        match = re.fullmatch(r"(?:close|end)\s+(.+)", command)
        if match:
            return self.lifecycle_request(match.group(1))


        if command in {"what time is it", "tell me the time"}:
            value = datetime.now().strftime("%I:%M %p").lstrip("0")
            return Result(f"The time is {value}, sir.")
        if command in {"what is the date", "what's the date", "tell me the date"}:
            now = datetime.now()
            value = f"{now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}"
            return Result(f"Today is {value}, sir.")
        if command in {"hello", "hello there"}:
            return Result("Hello, sir.")
        if command == "status report":
            if self.catalogue_error:
                return Result("Voice control is available, but the app catalogue needs attention, sir.")
            return Result(f"Voice control is available, with {len(self.apps)} app entries loaded, sir.")
        if command in {"refresh apps", "refresh applications"}:
            if self.refresh():
                return Result(f"The app catalogue now contains {len(self.apps)} entries, sir.")
            return Result("I could not refresh the app catalogue, sir.")
        match = re.fullmatch(r"(?:open|launch|start)\s+(.+)", command)
        if match:
            return self.open_request(match.group(1))
        return Result("That command is not configured, sir.", handled=False)
