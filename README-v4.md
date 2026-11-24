# JARVIS v4: dates, calculations and timers

This is an update to the existing Windows/Piper/Vosk app-control build.
It keeps microphone DEVICE = 2 and the full vosk-model-en-us-0.22 model.
No new pip packages are required beyond the preceding build, including psutil.

## Install

Stop the running script with Ctrl+C. Back up the current Python files.
Put all attached .py files in your existing Jarvis folder, replacing same-named files.
Keep your models, voices and .venv folders.

Run these tests from the Jarvis folder:

    .\.venv\Scripts\python.exe test_time.py
    .\.venv\Scripts\python.exe test_matching.py

These tests do not use the microphone, open apps, close apps, or wait for real timers.
They are included for you to run; this build has not been executed in the author's environment.
If either test reports a failure, keep the complete error and do not proceed to app-control testing.

Then run:

    .\.venv\Scripts\python.exe jarvis.py

First voice test: "Jarvis, set a timer for ten seconds."
Wait for the beep and spoken completion.

## Calendar and clock examples

Prefix these with "Jarvis", or say "Jarvis" first and wait for the listening message.

- What's the date today?
- What day of the week is it?
- What time is it?
- How many days until December eighteenth?
- How many days until December eighteenth twenty twenty six?
- How many days until Friday?
- What day is December eighteenth?
- What date will it be in two weeks?
- How many minutes until five thirty PM?
- How many hours until tomorrow at noon?
- How long until seventeen thirty?

Dates/calculations use the PC's local date/time settings.
"Days until" means calendar-date difference, not completed 24-hour periods.
A month/day without a year means the next occurrence, including today.
An explicit past date is reported as days ago.
A clock time without a day means its next occurrence, rolling to tomorrow if already past.
Use AM/PM for ambiguous hours, or unambiguous 24-hour time such as "seventeen thirty".
If a question is unclear, repeat the full question with the missing details.
Numeric dates such as 03/04 are intentionally rejected; use the month name.
This does not connect to Outlook, Google Calendar, or any calendar account.

## Timers

- Set a timer for ten seconds.
- Set a timer for five minutes.
- Set a timer for one hour and thirty minutes.
- Set a timer for half an hour.
- Set a timer for ten minutes called pasta.
- How much time is left on my timer?
- How much time is left on timer two?
- List timers.
- Cancel timer.
- Cancel timer two.
- Cancel timer pasta.
- Cancel all timers.

Timers receive numbers. An optional name can identify one instead.
"Cancel timer" and "my timer" work without a number only if exactly one timer exists.
Up to ten timers can run; each duration must be from one second to seven days.
Timer deadlines use a monotonic clock, so ordinary system-clock edits do not change the countdown.
Python reference: https://docs.python.org/3/library/time.html#time.monotonic

IMPORTANT:
- Timers exist only in this running Python process. Exit, crash or restart loses them.
- JARVIS must remain running and the PC awake. This does not wake a sleeping PC.
- An announcement can be delayed while another action or spoken reply is in progress.
- Expiry beeps and speaks once; it is not a repeating alarm.
- A timer alert cancels a pending app selection/force-stop confirmation.
- Speech interrupted by an alert is discarded. Repeat the command after the alert.
- The mic stays off during JARVIS speech. The listening message now prints after the input stream opens.
- These are convenience timers, not a substitute for safety-critical alarms.

## App-close wording

Normal close no longer adds the spoken save-prompt reminder for:
Discord, Apple Music, Spotify, the Windows Music.UI player and Music Presence.

This only changes JARVIS's wording. It never dismisses or bypasses an app's own prompts.
Editors and unknown apps retain the reminder.
Force-end still requires "confirm end task" and retains its warning.

## Existing app controls

- Open / launch / start [app or folder].
- Close / end [app]: normal close request.
- End the task [app]: forced termination, requiring explicit confirmation.
- Answer an app-choice question with a number or unique name fragment.
- "2026" and "twenty twenty six" both work for an FL Studio version choice.
- "Cancel" abandons a pending choice.
- "Stop listening" or Ctrl+C exits JARVIS and cancels its timers.

Some hosted Windows apps still need mappings. Protected system/terminal processes remain excluded.
