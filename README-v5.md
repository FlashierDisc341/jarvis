# JARVIS v5: system controls and calculations

Added:
- System output volume: up/down, exact percentage, mute/unmute, status.
- Existing-window focus, minimize, maximize, restore and show desktop.
- Repeat the last spoken reply, without repeating the action.
- Command help in the terminal and spoken category help.
- One-operation arithmetic, percentages and fixed unit conversions.

Retained:
- Jarvis at either the start or end of a command.
- Full vosk-model-en-us-0.22 model and headset input DEVICE = 2.
- App/folder opening, normal close, confirmed force-end and partial-name selection.
- Calendar calculations, the optional "it" date-question fix and in-memory timers.
- Quieter normal-close replies for Discord and the listed music players.

NOT added: playback, Apple Music searches, in-app typing/clicking, shutdown/restart or an LLM.

## Install

1. Stop JARVIS with Ctrl+C. Back up your current Python files.
2. Copy all attached .py files into the existing Jarvis folder, replacing matching files.
3. Keep .venv, models and voices unchanged.
4. Install the pinned audio-control dependency:

    .\.venv\Scripts\python.exe -m pip install pycaw==20251023

5. Run the new checks:

    .\.venv\Scripts\python.exe test_basics.py

The tests use mocked window/volume actions. They do not change volume, focus apps,
load speech models, open the microphone, or terminate processes.
This build has been reviewed but has not been executed in the author's environment.
If checks fail, retain the full error and do not proceed to live app-control testing.

6. Start normally:

    .\.venv\Scripts\python.exe jarvis.py

First tests, in order:
- "Jarvis, what is the volume?" (read-only)
- "Jarvis, calculate twelve times eight."
- "What date will be in ten weeks, Jarvis?"
- "Jarvis, volume down."
- Open an empty Notepad and try "Jarvis, minimize Notepad."
- Then try "Jarvis, switch to Notepad."

## System volume

- What is the volume?
- Volume up / volume down.
- Turn the volume up / turn the volume down.
- Volume up by ten percent.
- Set volume to thirty percent.
- Mute / unmute.

Up/down defaults to FIVE PERCENTAGE POINTS. A ten-percent change means ten percentage
points, not multiplying the current setting by 1.1.
The target is the current Windows default playback device, not the microphone or one app.
Device selection itself is not changed.

Increasing output to 80% or above requires "confirm volume".
Unmuting at 80% or above also requires confirmation. "Yes" does not confirm either.
Cancel or the follow-up timeout abandons it. A changed playback device/volume invalidates
a pending confirmation.

IMPORTANT: muting system output also silences JARVIS and timer sounds.
The microphone still listens; say "Jarvis, unmute" to restore output.
Replies and confirmation requests still print in the terminal while muted.
Setting a volume level does not deliberately unmute output.

Audio implementation references:
https://pypi.org/project/pycaw/
https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-setmastervolumelevelscalar

## Window controls

- Switch to Chrome.
- Focus Discord.
- Bring Notepad to the front.
- Minimize Notepad.
- Maximize Chrome.
- Restore Chrome.
- Show desktop.

These use existing, visible windows, including minimized windows.
Use "open" instead when an app is not running.
Multiple matching apps/windows require a choice. No arbitrary window-title matching.
"Restore" returns a maximized/minimized window to its normal state.
"Show desktop" asks Windows to minimize desktop windows; it does not close apps.
Window focus is checked after the request. Windows can refuse foreground activation.
JARVIS reports that refusal instead of claiming success; no admin elevation or input hacks.
Apps hosted behind a different Windows process may still need a friendly-name mapping.

Windows references:
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindowasync
https://learn.microsoft.com/en-us/windows/win32/shell/shell-minimizeall

## Repeat/help

- Repeat that.
- Say that again.
- What can you do?
- List commands.
- Help with volume / windows / maths / timers / calendar / apps.

Repeat only speaks the recorded reply; it never re-executes an app/volume action.
The standalone "Yes, sir" wake acknowledgement does not replace the last useful reply.
A full command list prints in the terminal; category help gives spoken examples.

## Calculations

- Calculate twelve times eight.
- What is fifteen percent of eighty?
- Calculate five divided by two.
- Calculate negative five minus negative two.
- Convert ten inches to centimetres.
- Convert thirty two Fahrenheit to Celsius.

Supported operations: plus, minus, times, divided by and percent-of.
Use TWO numbers and ONE operation at a time. Chained expressions, functions and powers
are not supported. No eval, arbitrary execution, shell commands or LLM calculation.
Spoken decimals can use "two point zero five".
Outputs are rounded to at most eight decimal places; repeating division/conversions
are labelled approximately when rounded.
Input numbers are bounded to magnitudes from 0.000000000001 through 1000000000000, plus zero.

Supported conversion families:
- Length: millimetres, centimetres, metres, kilometres, inches, feet, yards, miles.
- Mass: milligrams, grams, kilograms, ounces, pounds, metric tonnes.
- Volume: millilitres and litres.
- Temperature: Celsius, Fahrenheit and Kelvin.
Common US/UK spellings and singular/plural forms are accepted.
No currency rates, ambiguous gallons/pints, or conversion across unrelated dimensions.

## Existing timer/calendar limits

Calculations use the PC's local date/time.
Unspecified date years use the next occurrence. Days-until counts calendar days.
Ambiguous clock hours need AM/PM or an unambiguous 24-hour time.
A clock time already past, with no day supplied, rolls to tomorrow.

Timers require this script running and the PC awake. Exit/restart/crash loses them.
System mute silences their audio. An ongoing action/reply can delay an announcement.
A timer alert cancels a pending choice or confirmation.
Speech interrupted by an alert is discarded; repeat the command afterward.
These are convenience timers, not safety-critical alarms.

Ctrl+C or "stop listening" stops JARVIS. Nothing is installed as a startup service.
