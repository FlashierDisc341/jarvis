"""Command help, kept local. These strings do not execute actions."""
HELP = {
    "system": (
        "Say system report, CPU usage, RAM usage, or how much disk space is free. "
        "Ask how much memory Chrome is using, or what is using the most CPU. "
        "App memory is a combined working set, and the CPU ranking covers readable "
        "processes in your Windows session. These reports do not change anything, sir."
    ),
    "notes": (
        "Say take a note, wait for LISTENING, then dictate one short note without Jarvis. "
        "I will read it back. Say save note to keep it, or cancel. "
        "Read my notes, read note one, archive note one and restore note one are also available, sir."
    ),
    "reminders": (
        "Say remind me tomorrow at six PM to practise guitar, then confirm with save reminder. "
        "I use your computer's local time and read back the full date and time. "
        "Say read my reminders, read reminder one, or cancel reminder one. "
        "Saved reminders survive restarts, but I must be running and your PC awake to announce them, sir."
    ),
    "volume": (
        "Volume up or down changes it by five percentage points. "
        "Say set volume to thirty percent, mute, unmute, or what is the volume, sir."
    ),
    "windows": (
        "Say switch to Chrome, minimize Notepad, maximize Discord, restore Chrome, "
        "or show desktop. Multiple windows require a choice, sir."
    ),
    "maths": (
        "Say what is three to the power of seven, square root of eighty one, "
        "solve two x plus three equals eleven, or differentiate x cubed. "
        "I also do multi-step arithmetic, percentages, trig and unit conversions. "
        "Use degrees explicitly for degree-based trig; otherwise I use radians, sir."
    ),
    "timers": (
        "Say set a timer for ten minutes, list timers, "
        "how much time is left on my timer, or cancel timer one, sir."
    ),
    "calendar": (
        "Ask what day of the week it is, how many days until December eighteenth, "
        "what date will be in ten weeks, or how many minutes until five PM, sir."
    ),
    "apps": (
        "Say open an app or folder by name, close an app, or end the task followed "
        "by its name. Force-ending requires confirm end task, sir."
    ),
}
FULL_HELP = """
JARVIS local Ollama routing v10 - put Jarvis at the START OR END of your spoken command.

PC REPORTS - READ ONLY:
  system report / pc status
  CPU usage / RAM usage
  how much disk space is free         (Windows drive only)
  how much memory is Chrome using
  memory usage for FL Studio
  what's using the most CPU
  CPU rankings are short samples of readable executable groups in your session.
  App memory is combined RSS/working set, not unique memory or Task Manager's default.
  No temperatures, GPU readings, automatic app closing or tuning.

NOTES:
  take a note                        (wait, dictate, then say save note)
  take a note: Bring the blue folder
  read my notes / read note one
  read notes after three             (saved ID, not a temporary list position)
  archive note one                   (then confirm archive)
  list archived notes / restore note one (then confirm restore)

REMINDERS:
  remind me in two minutes to stretch (then save reminder)
  remind me tomorrow at six PM to practise guitar
  remind me on December eighteenth at five PM to call the garage
  read my reminders / read reminder one
  read reminders after three
  cancel reminder one                (then confirm cancel)
  list cancelled reminders / restore reminder one (then confirm restore)
  One-off reminders, local PC time. Use AM/PM when the hour is ambiguous.
  No recurring reminders, phone/calendar sync, startup service or PC wake.
  Missed reminders are checked when this Whisper entry point starts.
  The older Vosk entry point does not announce persistent reminders.

SYSTEM VOLUME:
  volume up / volume down             (5 percentage points)
  volume up by ten percent
  set volume to thirty percent
  mute / unmute / what is the volume
  confirm volume                     (only when requested for a loud increase)

WINDOWS:
  switch to Chrome / focus Discord
  minimize Notepad / maximize Chrome / restore Chrome
  show desktop
  Existing windows only; multiple matches require a choice.

CALCULATIONS:
  calculate twelve times eight
  what is fifteen percent of eighty
  calculate five divided by two
  convert ten inches to centimetres
  convert thirty two Fahrenheit to Celsius
  what is three to the power of seven
  what is two plus three times four
  what is open bracket two plus three close bracket times four
  what is the square root of eighty one
  what is sine of thirty degrees
  what is five factorial
  solve two x plus three equals eleven
  solve x squared minus five x plus six equals zero
  expand open bracket x plus two close bracket squared
  factor x squared minus nine
  differentiate x cubed plus two x
  integrate x squared
  integrate x squared from zero to three
  Brackets set grouping. Powers apply before multiplication, then addition.
  Trig uses radians unless you explicitly say degrees.
  x is the only variable. Polynomial equations up to degree four, real solutions.
  Definite integrals: polynomials only. No word-problem interpretation or proofs.
  Symbolic division and variable exponents are not included.
  Bounded inputs; calculations time out after six seconds. No currency lookup.

HELP:
  what can you do / list commands / help
  help with system / notes / reminders / volume / windows / maths / timers / calendar / apps
  repeat that / say that again

EXISTING:
  open Notepad / open downloads / open Jarvis
  close Notepad / end Notepad
  end the task Notepad               (then confirm end task)
  what's the date today / what day of the week is it
  how many days until December eighteenth
  what date will be in ten weeks
  how many minutes until five thirty PM
  set a timer for ten seconds
  set a timer for ten minutes called pasta
  list timers / how much time is left on my timer / cancel timer pasta
  cancel / stop listening

NOT INCLUDED:
  Weather, web search, free-form AI chat, in-app playback, song search,
  typing, clicking, shutdown/restart.

LOCAL OLLAMA FALLBACK (Whisper entry point only):
  Existing recognized commands still use the deterministic parser first.
  Otherwise, a local qwen2.5:3b model can interpret supported paraphrases.
  Read-only requests run through existing handlers. Interpreted changes ask
  for confirm interpretation first, then retain all original confirmations.
  Pending choices, dictation and confirmations never go through the model.
  Examples: get Notepad up for me; could you tell me the current hour.
  No free-form model answer is spoken. Unsupported requests stay unsupported.
  Use --no-ollama with jarvis_whisper.py for exact-command-only operation.
Timers require JARVIS running and the PC awake; exit loses them.
Mute silences JARVIS's output too, but not the microphone. Say unmute to hear him again.
"""


def help_reply(command):
    if command in {"help", "what can you do", "what commands can you do",
                   "what commands do you know", "list commands", "show commands"}:
        print(FULL_HELP, flush=True)
        return (
            "I can open and close apps, manage windows and system volume, "
            "calculate dates and numbers, convert units, run timers, save notes, set reminders, "
            "and report CPU, RAM and disk usage. "
            "The command list is in the terminal. Say help with a category for examples, sir."
        )
    for prefix in ("help with ", "help on "):
        if command.startswith(prefix):
            topic = command[len(prefix):].strip()
            topic = {"math": "maths", "calculations": "maths", "audio": "volume",
                     "dates": "calendar", "applications": "apps", "note": "notes", "reminder": "reminders", "pc": "system", "status": "system"}.get(topic, topic)
            return HELP.get(
                topic, "Help categories are system, notes, reminders, volume, windows, maths, timers, calendar and apps, sir."
            )
    return None
