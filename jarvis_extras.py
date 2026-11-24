"""JARVIS extras v10.2: media keys, web search, weather, screenshots,
daily briefing, coin flips, dice, NVIDIA clip + recording hotkeys.
Called from jarvis_actions.py.

Only the weather goes online: Open-Meteo first, wttr.in as a backup
(both free, no API key, no account). Web search opens your default browser.
Everything else stays on the PC.
"""
import ctypes
import json
import os
import random
import re
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

# Per-PC settings now live in config.json (see jarvis_config.py).
# Updates never touch config.json, so location and hotkeys stay put.
from jarvis_config import CONFIG, key_code

LATITUDE = CONFIG["latitude"]
LONGITUDE = CONFIG["longitude"]
FAHRENHEIT = CONFIG["fahrenheit"]
CLIP_KEY = key_code(CONFIG["clip_key"])      # default F4
RECORD_KEY = key_code(CONFIG["record_key"])  # default F3

ROOT = Path(__file__).resolve().parent
SCREENSHOT_DIR = ROOT / "screenshots"
USER_AGENT = "JARVIS-local-assistant/10"

# Windows virtual-key codes for the media keys on a keyboard.
MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1}
MEDIA_COMMANDS = {
    "play": "play_pause", "pause": "play_pause", "resume": "play_pause",
    "play music": "play_pause", "pause music": "play_pause",
    "pause the music": "play_pause", "resume music": "play_pause",
    "resume the music": "play_pause",
    "next": "next", "next track": "next", "next song": "next",
    "skip": "next", "skip song": "next", "skip this song": "next",
    "skip track": "next", "skip the song": "next",
    "previous": "previous", "previous track": "previous",
    "previous song": "previous", "last song": "previous",
    "go back a song": "previous",
}
MEDIA_REPLIES = {
    "play_pause": "Toggling playback, sir.",
    "next": "Skipping ahead, sir.",
    "previous": "Going back a track, sir.",
}

# Open-Meteo uses the standard WMO weather codes.
WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear skies", 2: "partly cloudy skies",
    3: "overcast skies", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "a thunderstorm", 96: "a thunderstorm with hail",
    99: "a thunderstorm with heavy hail",
}

SEARCH = re.compile(r"(?:search(?: google| the web)?(?: for)?|google|look up)\s+(.+)")
WEATHER = re.compile(
    r"(?:(?:what's|whats|what is|how's|hows|how is) )?(?:the )?"
    r"weather(?: like| forecast| report)?(?: (?:for |like )?(today|tomorrow))?"
)
RAIN = re.compile(r"(?:will|is) it (?:going to )?rain(?: (today|tomorrow))?")
SCREENSHOT_COMMANDS = {
    "screenshot", "take a screenshot", "take screenshot",
    "screenshot this", "grab the screen", "capture the screen",
}
SHOW_SCREENSHOTS = re.compile(r"(?:open|show)(?: me)?(?: my| the)? screenshots?(?: folder)?")
BRIEFING_COMMANDS = {
    "good morning", "good afternoon", "good evening",
    "daily briefing", "morning briefing", "briefing", "brief me",
}
COIN = {"flip a coin", "toss a coin", "coin flip", "flip coin"}
DICE = re.compile(r"roll (?:a |an |one )?(?:die|dice|d(\d{1,3}))")
CLIP_COMMANDS = {"clip that", "clip it", "clip this", "clip", "save that", "save the clip"}
RECORD_START = {"start recording", "start a recording", "begin recording", "record",
                "start the recording"}
RECORD_STOP = {"stop recording", "stop the recording", "end recording",
               "end the recording", "finish recording"}


def tap(vk):
    """Press and release one key, like a finger tapping it."""
    user32 = ctypes.windll.user32
    # Some hotkey listeners (like NVIDIA's overlay) ignore keypresses with no
    # hardware scan code, so look up the real one for this key.
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, scan, 0, 0)   # key down
    time.sleep(0.08)                     # hold it briefly, like a real finger
    user32.keybd_event(vk, scan, 2, 0)   # key up (2 = KEYEVENTF_KEYUP)
    print(f"Pressed key 0x{vk:02X} (scan {scan})", flush=True)


def press_media(name):
    tap(MEDIA_KEYS[name])
    return MEDIA_REPLIES[name]


def web_search(query):
    query = query.strip(" .,?!")
    if not query:
        return "What should I search for, sir?"
    if len(query) > 200:
        return "That search is too long, sir."
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    return f"Searching for {query}, sir."


# ---------- weather ----------
# Both sources are turned into the same shape:
#   current = {"temp", "sky", "wind"}
#   days    = [{"high", "low", "rain", "sky"}, ...]   index 0 = today, 1 = tomorrow

def get_json(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read(1_000_000))


def from_open_meteo():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max",
        "temperature_unit": "fahrenheit" if FAHRENHEIT else "celsius",
        "wind_speed_unit": "mph" if FAHRENHEIT else "kmh",
        "timezone": "auto",
        "forecast_days": 2,
    }
    data = get_json("https://api.open-meteo.com/v1/forecast?" + urlencode(params))
    now, daily = data["current"], data["daily"]
    current = {
        "temp": now["temperature_2m"],
        "sky": WEATHER_CODES.get(now["weather_code"], "mixed weather"),
        "wind": now["wind_speed_10m"],
    }
    days = [{
        "high": daily["temperature_2m_max"][i],
        "low": daily["temperature_2m_min"][i],
        "rain": daily["precipitation_probability_max"][i],
        "sky": WEATHER_CODES.get(daily["weather_code"][i], "mixed weather"),
    } for i in range(2)]
    return current, days


def from_wttr():
    unit = "F" if FAHRENHEIT else "C"
    data = get_json(f"https://wttr.in/{LATITUDE},{LONGITUDE}?format=j1")
    now = data["current_condition"][0]
    current = {
        "temp": float(now[f"temp_{unit}"]),
        "sky": now["weatherDesc"][0]["value"].strip().lower(),
        "wind": float(now["windspeedMiles"] if FAHRENHEIT else now["windspeedKmph"]),
    }
    days = []
    for day in data["weather"][:2]:
        hours = day["hourly"]
        midday = hours[len(hours) // 2]
        days.append({
            "high": float(day[f"maxtemp{unit}"]),
            "low": float(day[f"mintemp{unit}"]),
            "rain": max(int(h["chanceofrain"]) for h in hours),
            "sky": midday["weatherDesc"][0]["value"].strip().lower(),
        })
    return current, days


def fetch_weather():
    """Try Open-Meteo twice, then wttr.in. Raises only if all of them fail."""
    attempts = [("Open-Meteo", from_open_meteo), ("Open-Meteo retry", from_open_meteo),
                ("wttr.in", from_wttr)]
    last_error = None
    for name, source in attempts:
        try:
            result = source()
            print("Weather source:", name, flush=True)
            return result
        except Exception as error:
            print(f"Weather error ({name}):", type(error).__name__, error, flush=True)
            last_error = error
            time.sleep(0.5)
    raise last_error


def weather(day="today", rain_only=False):
    if LATITUDE is None or LONGITUDE is None:
        return "Set your latitude and longitude at the top of jarvis extras first, sir."
    try:
        current, days = fetch_weather()
    except Exception:
        return "Every weather service is unreachable right now, sir."
    today = day != "tomorrow"
    info = days[0 if today else 1]
    high, low = round(info["high"]), round(info["low"])
    rain = info["rain"]
    rain_text = f"a {rain} percent chance of rain" if rain is not None else "no rain data"
    if rain_only:
        verdict = "Probably" if rain is not None and rain >= 50 else "Probably not"
        return f"{verdict}, sir. {day.capitalize()} has {rain_text}."
    if today:
        speed = "miles per hour" if FAHRENHEIT else "kilometres per hour"
        return (f"It is {round(current['temp'])} degrees with {current['sky']} "
                f"and wind at {round(current['wind'])} {speed}. "
                f"Today's high is {high} and the low is {low}, with {rain_text}, sir.")
    return f"Tomorrow: {info['sky']}, high {high}, low {low}, with {rain_text}, sir."


# ---------- screenshots ----------

def screenshot():
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Screenshots need Pillow installed in the whisper environment, sir."
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / datetime.now().strftime("screenshot-%Y-%m-%d_%H-%M-%S.png")
    try:
        ImageGrab.grab(all_screens=True).save(path)
    except OSError as error:
        print("Screenshot error:", error, flush=True)
        return "I could not capture the screen, sir."
    print("Screenshot saved:", path, flush=True)
    return "Screenshot saved, sir."


def show_screenshots():
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    os.startfile(str(SCREENSHOT_DIR))
    return "Opening your screenshots, sir."


# ---------- briefing / fun ----------

def briefing():
    now = datetime.now()
    if now.hour < 12:
        greeting = "Good morning"
    elif now.hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    clock = now.strftime("%I:%M %p").lstrip("0")
    parts = [f"{greeting}, sir. It is {clock} on {now.strftime('%A')}, "
             f"{now.day} {now.strftime('%B')}."]
    if LATITUDE is not None and LONGITUDE is not None:
        parts.append(weather("today"))
    parts.append("Say read my reminders to hear what is coming up.")
    return " ".join(parts)


def roll(sides):
    if not 2 <= sides <= 1000:
        return "Pick a die between 2 and 1000 sides, sir."
    return f"You rolled a {random.randint(1, sides)}, sir."


# ---------- router ----------

def handle(command):
    """command is already lowercased and trimmed by Actions.handle.
    Returns a reply string, or None if this isn't an extras command."""
    try:
        if command in CLIP_COMMANDS:
            tap(CLIP_KEY)
            return "Clipped, sir."
        if command in RECORD_START:
            tap(RECORD_KEY)
            return "Recording, sir."
        if command in RECORD_STOP:
            tap(RECORD_KEY)
            return "Recording stopped, sir."
        if command in MEDIA_COMMANDS:
            return press_media(MEDIA_COMMANDS[command])
        match = SEARCH.fullmatch(command)
        if match:
            return web_search(match.group(1))
        match = RAIN.fullmatch(command)
        if match:
            return weather(match.group(1) or "today", rain_only=True)
        match = WEATHER.fullmatch(command)
        if match:
            return weather(match.group(1) or "today")
        if command in SCREENSHOT_COMMANDS:
            return screenshot()
        if SHOW_SCREENSHOTS.fullmatch(command):
            return show_screenshots()
        if command in BRIEFING_COMMANDS:
            return briefing()
        if command in COIN:
            return f"{random.choice(['Heads', 'Tails'])}, sir."
        match = DICE.fullmatch(command)
        if match:
            return roll(int(match.group(1) or 6))
    except Exception as error:
        print("Extras error:", type(error).__name__, error, flush=True)
        return "That extra command failed. Check the terminal, sir."
    return None
