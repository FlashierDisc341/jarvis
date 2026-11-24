# JARVIS

A local voice assistant for Windows, made by **FlashierDisc341**.

You talk, he listens, he does stuff. Speech recognition and his voice both run **on your own PC**, so nothing you say gets sent anywhere. Only a few features go online (weather and web search), and only when you ask for them.

> "Jarvis, clip that."
> "Clipped, sir."

---

## What he can do

| | |
|---|---|
| 🎵 **Music** | play, pause, skip, go back (works with Spotify, Apple Music, YouTube, anything that uses media keys) |
| 🎮 **NVIDIA clips** | save the last 30 seconds, start/stop recording |
| 🌦️ **Weather** | today, tomorrow, "will it rain?" |
| 🔎 **Web search** | opens a Google search in your default browser |
| 📸 **Screenshots** | captures all your screens, saved in a `screenshots` folder |
| ☀️ **Daily briefing** | "good morning" gets you the time, weather and what's coming up |
| 📝 **Notes & reminders** | saved on your PC, they survive restarts |
| ⏱️ **Timers, time & math** | timers, the time and date, spoken math |
| 🖥️ **PC reports** | what your PC is doing |
| 🎲 **Fun** | flip a coin, roll dice |
| 🧠 **Smart fallback** (optional) | with Ollama installed, he understands requests worded in ways he wasn't coded for |

---

## How to talk to him

Say **"Jarvis"** at the **start or end** of what you say:

- "Jarvis, skip this song"
- "What's the weather tomorrow, Jarvis"

Or just say **"Jarvis"** on its own. He answers **"Yes, sir"** and listens for about 15 seconds, so you can say the command without the name.

Wait for **LISTENING** in the window before you speak. To shut him down, say **"goodbye"** or **"stop listening"**, or press **Ctrl+C** in the window.

---

## Requirements

- **Windows 10 or 11**
- **An NVIDIA graphics card.** Speech recognition runs on the GPU, which is how he understands you in about half a second.
- **Python 3.14**, specifically. **Not 3.15 or newer**, because some packages don't support it yet.
- **Git**
- About **3 GB** of free space
- A microphone

---

## Install (one time)

### 1. Install Git
[git-scm.com](https://git-scm.com/download/win) → download for Windows → click **Next** through everything. The default options are fine.

### 2. Install Python 3.14
[python.org/downloads](https://www.python.org/downloads/) → find the newest **3.14.x** release (scroll down, or use *All releases*).

⚠️ On the first installer screen, **check "Add python.exe to PATH"** before clicking Install.

### 3. Get access
This repo is private. Ask FlashierDisc341 to add you, then accept the invite from your email.

### 4. Run the installer
Download **`Install_JARVIS.bat`** from this repo and double-click it.

- A GitHub login window pops up the first time. Log in.
- It downloads around **2 GB** of packages, so give it a while.
- At the end it lists your microphones. **Type the number** of the one you use.

JARVIS gets installed in `C:\Users\<you>\Jarvis`.

### 5. Make a shortcut
In that folder, right-click **`Start_JARVIS.bat`** → *Send to* → **Desktop (create shortcut)**.

The first start takes a bit longer, because he downloads his speech model (one time only).

---

## Updating

**You don't have to do anything.** Every time you open `Start_JARVIS.bat`, he checks for updates, downloads only what changed, and then starts.

Updates never touch your settings, notes or reminders.

---

## Settings (`config.json`)

This file is created in the Jarvis folder the first time he starts. Open it with Notepad to change things:

```json
{
  "mic_device": 2,
  "latitude": null,
  "longitude": null,
  "fahrenheit": true,
  "clip_key": "F4",
  "record_key": "F3"
}
```

| Setting | What it does |
|---|---|
| `mic_device` | Which mic he listens to. Set it to `null` and restart him to pick again. |
| `latitude` / `longitude` | **Needed for weather.** Search "*your town* coordinates". West longitudes are negative (the whole US is negative). Example: `41.88` and `-87.63` |
| `fahrenheit` | `true` = °F and mph, `false` = °C and km/h |
| `clip_key` | Your NVIDIA "save last 30 seconds" hotkey (F1 to F12) |
| `record_key` | Your NVIDIA "start/stop recording" hotkey (F1 to F12) |

This file stays on your PC. It's never uploaded, so your location stays private.

---

## Commands

You don't need to say these word for word. These are just examples.

### 🎵 Music
- "play" / "pause" / "resume"
- "skip" / "next song" / "next track"
- "previous song" / "last song" / "go back a song"

Media keys go to whatever app played sound most recently.

### 🎮 NVIDIA
- "clip that" / "clip it" / "save that": saves the last 30 seconds
- "start recording" / "stop recording"

Needs **NVIDIA Instant Replay** turned on in the NVIDIA app, with the same hotkeys as in `config.json`.

### 🌦️ Weather
- "what's the weather" / "how's the weather tomorrow"
- "will it rain" / "is it going to rain tomorrow"

Needs your coordinates in `config.json`.

### 🔎 Search
- "search for *anything*" / "google *anything*" / "look up *anything*"

### 📸 Screenshots
- "take a screenshot"
- "show my screenshots"

### ☀️ Briefing
- "good morning" / "good afternoon" / "good evening"
- "daily briefing" / "brief me"

### 🎲 Fun
- "flip a coin"
- "roll a d20" / "roll a die"

### 📝 Notes, reminders, timers, math, PC reports
These have their own guides in this repo:
- [Notes & reminders](README-notes-reminders-v8.md)
- [Math](README-maths-v7.md)
- [PC reports](README-pc-reports-v9.md)

---

## Smart mode (optional): Ollama

Without it, JARVIS only understands the commands he was coded for. With it, a small AI model running **on your PC** works out what you meant when you word things differently, like "is it gonna be wet out" → rain check.

The AI never does anything by itself. It can only pick from JARVIS's existing commands, and the risky ones still ask you to confirm.

Setup steps are in [JARVIS_OLLAMA_SETUP.txt](JARVIS_OLLAMA_SETUP.txt).

If Ollama isn't installed, JARVIS still works normally.

---

## Troubleshooting

**He doesn't react when I talk**
- Wait for **LISTENING** in the window first.
- Check the window: it prints what he *heard*. If it's gibberish, he's on the wrong mic. Set `"mic_device": null` in `config.json` and restart him.
- Make sure "Jarvis" is at the very start or end of the sentence.

**`PermissionError` when starting**
Two JARVIS windows are open. Close all of them and start just one.

**"Update check failed"**
Harmless. He starts with the version you already have. Usually it means no internet, or Git isn't installed.

**Installer says Python 3.14 is not installed**
You have a different version. Install **3.14.x** next to it (you don't have to uninstall the other one).

**"clip that" does nothing**
Check that NVIDIA Instant Replay is on, and that your NVIDIA hotkey matches `clip_key` in `config.json`.

**Weather doesn't work**
Put your `latitude` and `longitude` in `config.json`.

**Something else broke**
Screenshot the whole black window and send it to FlashierDisc341.

---

## Privacy

- Your voice is turned into text **on your PC**. No audio ever leaves it.
- Notes, reminders, screenshots and settings stay **on your PC** and are never uploaded.
- Online only when you ask: weather (Open-Meteo / wttr.in, no account) and web searches (your browser).

---

*Built by FlashierDisc341.*
