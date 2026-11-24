# JARVIS v8: local notes and persistent reminders

Adds the agreed notes/reminders batch. In-app controls, PC status and conversational
AI are still deferred. The working maths upgrade and comma fix are not replaced.

## Files and setup

Stop JARVIS first with Ctrl+C. Put the attached Python files in the existing Jarvis folder.

REPLACE:
- jarvis_whisper.py
- jarvis_actions.py
- jarvis_help.py

ADD:
- jarvis_organizer.py
- jarvis_dialogue.py
- test_organizer.py

Keep all other existing files, especially:
- jarvis_whisper_audio.py
- jarvis_math.py and the FIXED jarvis_math_engine.py
- jarvis_time.py, jarvis_desktop.py and jarvis_processes.py
- your voices, model cache, environments and existing tests

No additional pip packages are introduced by this batch.
It uses Python's sqlite3 module and your existing JARVIS dependencies.

Run the new tests first, from PowerShell in the Jarvis folder:

    .\.venv-whisper\Scripts\python.exe test_organizer.py

The tests use TEMPORARY databases, simulated clocks and mocked action/audio calls.
They do not open your real notebook, microphone, speech models or applications.
Windows-only tests cover the dispatcher and live-loop reminder wiring with mocks.
This generated build has been reviewed but has NOT been executed by its author.
If the tests fail, stop and keep the complete output.

Optional regression checks for the features you just verified:

    .\.venv-whisper\Scripts\python.exe test_math.py
    .\.venv-whisper\Scripts\python.exe test_whisper_frontend.py

The old v5 test_basics.py contains obsolete maths expectations and is NOT the current
maths test suite. Its "one operation only" assertion no longer describes v7 maths.

When the current tests report OK, start the updated entry point:

    .\.venv-whisper\Scripts\python.exe jarvis_whisper.py

Do NOT use --dry-run for the note/reminder walkthrough.
Dry-run only prints commands; it neither opens the notebook nor performs follow-ups.

Use this updated Whisper entry point for reminders. The original Vosk jarvis.py is
unchanged and does NOT include persistent-reminder announcements. Do not run both.

## First voice test: a note

1. Say: "Jarvis, take a note."
2. Wait for the dictation prompt and LISTENING.
3. Say: "Bring the blue folder tomorrow."
   Do not include Jarvis during this dedicated dictation step.
4. JARVIS reads back the transcribed text.
5. Say: "Save note."
6. Wait for LISTENING, then say: "Jarvis, read my notes."

The note is NOT saved before step 5. "Yes" is deliberately not a save command.
If it heard the wrong text, say "change note", wait, and dictate again.
Say "cancel" to abandon the draft.

You can also give one inline command:
    "Jarvis, take a note: Bring the blue folder tomorrow."

After a successful save, stop and restart JARVIS, then read the note again.
The saved content and note number should survive.

## Notes: commands and boundaries

- take a note / make a note / add a note
- take a note: [text]
- note that [text]
- save note / change note / cancel, during the relevant prompt
- read my notes / list notes
- read note one
- read notes after three
- archive note one, then "confirm archive"
- list archived notes
- read archived notes after three
- restore note one, then "confirm restore"

Numbers refer to stable saved IDs, not changing positions in a list.
Lists read three notes per page and give the command for the next page.

"Delete note one" offers ARCHIVING, with a readback and confirmation.
It does not permanently delete the text. Archived notes can be read and restored.
No permanent-delete or delete-all operation is included.

Each note is one short utterance, up to 400 characters. The existing listener's
12-second recording cap still applies. A long utterance is discarded, not clipped
and silently saved. This is not continuous dictation or a multi-paragraph editor.
Spelling, case and punctuation follow Whisper's output, not a guaranteed verbatim
recording. Whitespace is normalized. Listen to the readback before saving.

During explicit dictation, "open Chrome", "close Notepad" and similar text are
NOTE CONTENT, not commands. Even a literal Jarvis at either end is retained.
Exact cancel/stop commands are reserved; use "cancel" without a wake phrase in this step.
Other command requests do not escape a confirmation prompt: cancel it first.
"Repeat that" can repeat a confirmation readback without saving anything.

## First reminder test

Say:
    "Jarvis, remind me in two minutes to stretch."

JARVIS reads the task and the complete date/time/timezone.
Check it, then say:
    "Save reminder."

Wait for the alert, or stop JARVIS before it is due and restart after the due time.
An unannounced, overdue reminder should be reported as missed when it starts again.
Then ask:
    "Jarvis, read my reminders."

A completed announcement is recorded, so it should not repeat at every startup.
That is NOT a claim that you heard it or completed the task.

## Reminder commands

Create:
- remind me in ten minutes to check the oven
- remind me tomorrow at six PM to practise guitar
- remind me on December eighteenth at five PM to call the garage
- remind me at five thirty PM to stretch
- set a reminder for tomorrow at noon to check the list

Confirm:
- save reminder
- confirm reminder
- cancel

Read/manage:
- read my reminders / list reminders
- read reminder one
- read reminders after three
- cancel reminder one, then "confirm cancel"
- list cancelled reminders
- read cancelled reminders after three
- restore reminder one, then "confirm restore"

Cancelling keeps the record; it does not delete its text.
Restoring a past reminder explicitly warns that it will be announced shortly.
Restoring clears its prior announcement marker.

Relative delays use the existing parser: one second through seven days.
Calendar dates must be within the next 366 days.
For ambiguous clock hours, include AM/PM. Noon, midnight and unambiguous 24-hour
times also work. No AM/PM guess is made for "tomorrow at six".
If a date is omitted, "at five PM" means the next occurrence of five PM, today or tomorrow.
An explicitly past date/time is rejected.
A reminder whose due time passes before you confirm is not saved; ask again.

"Quarter to six PM" and reminder text containing "to" are supported.
Unrecognized phrasing returns a correction request rather than guessing a time.
There are no recurring reminders, snooze, relative "next week" interpretations,
phone notifications, email, or calendar-account integration in this batch.

## Time and delivery behavior

All spoken dates use the PC's LOCAL time, not this Discord server's timezone.
The confirmation includes the full calendar date, local timezone label and UTC offset.
Ambiguous or nonexistent local times during a clock change are rejected.
Relative delays are rounded up to the next whole second for a consistent readback.

A saved reminder uses an absolute timestamp. Changing the PC timezone later does
not move its instant; later readbacks show that instant in the PC's new local time.
There is no background process, auto-start registration or mechanism to wake the PC.

JARVIS must be running and the PC awake to announce on time. Due reminders interrupt
microphone capture, including an unfinished note/confirmation; unsaved drafts are
cancelled, never saved by an alert. Ask for the interrupted operation again.

As before, the microphone closes during transcription, actions and speech.
Long calculations, slow app discovery and spoken lists can delay alerts.
Afterwards the loop checks what is due. This is NOT a real-time or medical alarm.
Muted output may make an alert inaudible. Text still prints to the terminal, and a
successful playback return records an announcement even if you did not hear it.
Use "read my reminders" to review; an announcement is not task completion.

If several reminders are overdue, up to three are read aloud in one batch.
Any remaining reminders are counted in the spoken summary and listed in full in
the terminal. Their IDs can be used with "read reminder [number]".
The entire displayed/summarized batch is then marked announced, rather than making
JARVIS recite a long backlog indefinitely.

Reminder records are marked announced only AFTER the batch's speech returns.
A speech failure leaves them unannounced. A crash between speech and the database
commit can cause a duplicate announcement on restart; it should not silently lose
an unannounced reminder just because a readback was being generated.

Ordinary timers still live only in memory and disappear when JARVIS exits.
Persistent reminders are separate from those timers.

## Local storage and privacy

The notebook is created automatically at:

    Jarvis\data\jarvis-organizer.sqlite3

A sibling .lock file prevents multiple organizer instances from sharing this file.
A leftover lock file after exit is normal; the OS releases the actual lock.
If storage is unavailable, locked by another running instance, corrupt or a different
schema version, startup fails with an error rather than resetting the notebook.

Writes use SQLite transactions and bound parameters. Note/reminder text is data,
not SQL, Python, a shell command or an instruction for other actions.
The database allows 1,000 saved notes and 2,000 reminder records, including archived
and cancelled history. It does not automatically erase old records.

There is no encryption, password vault, cloud account or speaker authentication.
Anyone with access to these local files can read them; nearby speech can trigger
commands when the listener is active. Notes/reminders and their readbacks appear
in the local terminal and can be spoken aloud. Do not use it to store credentials.

This code does not upload the database or sync it itself. If your Jarvis folder is
inside OneDrive or another synced/backed-up folder, that service may copy the file.
For a manual backup, STOP JARVIS first, then copy the SQLite file somewhere safe.
Do not overwrite or delete the database when updating Python modules.

## What changed

- jarvis_organizer.py adds the local store, strict reminder parser, confirmations,
  note retrieval and reminder announcement state.
- jarvis_dialogue.py separates wake-phrase parsing from explicit note dictation.
- jarvis_actions.py routes notes/reminders before app actions where appropriate.
  Existing app/window/volume confirmation behavior is retained.
- jarvis_whisper.py checks timers AND saved reminders in the existing capture loop,
  acknowledges reminder speech afterwards, and releases storage on exit.
- jarvis_help.py adds the new command categories.

The headset device, Whisper model/GPU settings, Piper voice, math engine,
window controls and app matching have not been changed.

## Primary references

Python's local SQLite interface and parameter binding:
https://docs.python.org/3/library/sqlite3.html

Local-time timestamp conversion and fold handling:
https://docs.python.org/3/library/datetime.html
