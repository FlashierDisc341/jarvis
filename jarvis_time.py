"""Local calendar calculations and in-memory timers for JARVIS.
No calendar-account access, disk persistence, background service, or PC wake-up.
Timers are checked by the main voice loop; speech/actions can delay announcements.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re
import time

SMALL = dict(zip(
    ("zero one two three four five six seven eight nine ten eleven twelve "
     "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split(),
    range(20),
))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(),
                range(20, 100, 10)))
ORDINALS = dict(zip(
    ("first second third fourth fifth sixth seventh eighth ninth tenth "
     "eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth "
     "eighteenth nineteenth twentieth thirtieth").split(),
    list(range(1, 21)) + [30],
))
MONTHS = dict(zip(
    "january february march april may june july august september october november december".split(),
    range(1, 13),
))
WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()


class ParseError(ValueError):
    pass


def clean(text):
    text = text.casefold().replace("\u2019", "'")
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    text = re.sub(r"\bwhat(?:'s|s)\b", "what is", text)
    return " ".join(text.strip(" .,?!").split())


def under_hundred(words):
    if len(words) == 1:
        if words[0] in SMALL:
            return SMALL[words[0]]
        if words[0] in TENS:
            return TENS[words[0]]
    if (len(words) == 2 and words[0] in TENS
            and words[1] in SMALL and 0 < SMALL[words[1]] < 10):
        return TENS[words[0]] + SMALL[words[1]]
    raise ParseError("I could not read that number")


def integer(text, ordinal=False):
    text = clean(text)
    if ordinal:
        text = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text)
    if re.fullmatch(r"\d+", text):
        return int(text)
    words = text.split()
    if ordinal and words and words[-1] in ORDINALS:
        value = ORDINALS[words[-1]]
        if len(words) == 1:
            return value
        if len(words) == 2 and words[0] in TENS and value < 10:
            return TENS[words[0]] + value
        raise ParseError("I could not read that day")
    if "thousand" in words:
        if words.count("thousand") != 1:
            raise ParseError("I could not read that number")
        index = words.index("thousand")
        head = under_hundred(words[:index])
        tail = words[index + 1:]
        if tail[:1] == ["and"]:
            tail = tail[1:]
        return head * 1000 + (integer(" ".join(tail)) if tail else 0)
    if "hundred" in words:
        if words.count("hundred") != 1 or words.index("hundred") != 1:
            raise ParseError("I could not read that number")
        if words[0] not in SMALL or not 1 <= SMALL[words[0]] <= 9:
            raise ParseError("I could not read that number")
        tail = words[2:]
        if tail[:1] == ["and"]:
            tail = tail[1:]
        return SMALL[words[0]] * 100 + (under_hundred(tail) if tail else 0)
    return under_hundred(words)


def amount(text):
    text = clean(text)
    if text in {"a", "an"}:
        return 1.0
    if text in {"half", "half a", "half an"}:
        return 0.5
    if text in {"a quarter", "a quarter of a", "a quarter of an"}:
        return 0.25
    if text.endswith(" and a half"):
        return (1 if text[:-11] in {"a", "an"} else integer(text[:-11])) + 0.5
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    return float(integer(text))


def duration_seconds(text):
    text = clean(text)
    # Normalize the natural "an hour and a half" without guessing missing units.
    text = re.sub(
        r"\b(a|an|one|\d+)\s+(seconds?|minutes?|hours?|days?)\s+and a half\b",
        r"\1 and a half \2", text,
    )
    units = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    total, end, seen = 0.0, 0, set()
    pattern = r"(.+?)\s+(seconds?|minutes?|hours?|days?)(?=\s|$)"
    for match in re.finditer(pattern, text):
        if text[end:match.start()].strip():
            raise ParseError("Please include a number and unit for each duration")
        number = re.sub(r"^and\s+", "", match.group(1).strip())
        unit = match.group(2).rstrip("s")
        if unit in seen:
            raise ParseError("Please use each time unit only once")
        seen.add(unit)
        total += amount(number) * units[unit]
        end = match.end()
    if not seen or text[end:].strip():
        raise ParseError("Please say a duration such as ten minutes or one hour and thirty minutes")
    if not math.isfinite(total) or not 1 <= total <= 7 * 86400:
        raise ParseError("Timers must be between one second and seven days")
    return total


def duration_label(seconds):
    seconds = max(0, math.ceil(seconds))
    pieces = []
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute"), (1, "second")):
        value, seconds = divmod(seconds, size)
        if value:
            pieces.append(f"{value} {unit}{'' if value == 1 else 's'}")
    return " and ".join(pieces) if pieces else "zero seconds"


def parse_year(text):
    text = clean(text)
    if text.startswith("twenty "):
        value = 2000 + integer(text[7:])
    elif text.startswith("nineteen "):
        value = 1900 + integer(text[9:])
    else:
        value = integer(text)
    if not 1900 <= value <= 9999:
        raise ParseError("Please use a four digit year")
    return value


def date_label(value):
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def parse_date(text, today):
    text = clean(text)
    text = re.sub(r"^(?:on |the )+", "", text)
    if text in {"today", "tomorrow", "yesterday"}:
        return today + timedelta(days={"today": 0, "tomorrow": 1, "yesterday": -1}[text])
    match = re.fullmatch(r"(next |this )?(" + "|".join(WEEKDAYS) + r")", text)
    if match:
        days = (WEEKDAYS.index(match.group(2)) - today.weekday()) % 7
        if match.group(1) == "next " and days == 0:
            days = 7
        return today + timedelta(days=days)
    match = re.fullmatch(r"in (.+) (days?|weeks?)", text)
    if match:
        days = integer(match.group(1)) * (7 if match.group(2).startswith("week") else 1)
        if not 0 <= days <= 36500:
            raise ParseError("Please use a smaller date offset")
        return today + timedelta(days=days)

    # Named months avoid ambiguous numeric dates such as 03/04.
    tokens = [word for word in text.replace(",", " ").split() if word not in {"the", "of"}]
    indices = [index for index, word in enumerate(tokens) if word in MONTHS]
    if len(indices) != 1:
        raise ParseError("Please repeat the question with a month name, such as December eighteenth")
    index = indices[0]
    month = MONTHS[tokens[index]]
    before, after = tokens[:index], tokens[index + 1:]
    candidates = []
    if before:
        try:
            day = integer(" ".join(before), ordinal=True)
            year_text = " ".join(after)
            candidates.append((day, year_text))
        except ParseError:
            pass
    else:
        for split in range(1, len(after) + 1):
            try:
                day = integer(" ".join(after[:split]), ordinal=True)
                if 1 <= day <= 31:
                    candidates.append((day, " ".join(after[split:])))
            except ParseError:
                continue
    valid = []
    for day, year_text in candidates:
        try:
            if year_text:
                if year_text in {"next year", "this year"}:
                    year = today.year + int(year_text == "next year")
                else:
                    year = parse_year(year_text)
                valid.append(date(year, month, day))
            else:
                # No year means the next occurrence, including today.
                for year in range(today.year, min(today.year + 9, 10000)):
                    try:
                        value = date(year, month, day)
                    except ValueError:
                        continue
                    if value >= today:
                        valid.append(value)
                        break
        except (ValueError, OverflowError):
            continue
    unique = set(valid)
    if len(unique) != 1:
        raise ParseError("That date is invalid or unclear. Please repeat it with the month, day and year")
    return unique.pop()


def parse_clock(text):
    text = clean(text).replace(".", "")
    text = re.sub(r"\b([ap])\s+m\b", r"\1m", text)
    text = re.sub(r"\s+in the morning$", " am", text)
    text = re.sub(r"\s+in the (?:afternoon|evening)$", " pm", text)
    text = re.sub(r"\s+o[' ]?clock\b", "", text)
    if text == "noon":
        return 12, 0
    if text == "midnight":
        return 0, 0
    match = re.search(r"\s*(am|pm)$", text)
    period = match.group(1) if match else None
    body = text[:match.start()].strip() if match else text
    adjustment = 0
    for prefix, minutes in (("quarter past ", 15), ("half past ", 30), ("quarter to ", -15)):
        if body.startswith(prefix):
            adjustment = minutes
            body = body[len(prefix):]
            break
    colon = re.fullmatch(r"(\d{1,2}):(\d{2})", body)
    leading_zero = bool(re.fullmatch(r"0\d(?::\d{2})?", body))
    if colon:
        hour, minute = map(int, colon.groups())
    else:
        try:
            hour, minute = integer(body), 0
        except ParseError:
            tokens = body.split()
            possibilities = []
            for split in range(1, len(tokens)):
                try:
                    h = integer(" ".join(tokens[:split]))
                    tail = tokens[split:]
                    if tail[:1] in (["oh"], ["zero"]):
                        tail = tail[1:]
                    m = integer(" ".join(tail))
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        possibilities.append((h, m))
                except ParseError:
                    continue
            if len(set(possibilities)) != 1:
                raise ParseError("Please repeat the question with a time such as five thirty PM")
            hour, minute = possibilities[0]
    if not 0 <= minute <= 59:
        raise ParseError("Minutes must be between zero and fifty nine")
    if period:
        if not 1 <= hour <= 12:
            raise ParseError("With AM or PM, use an hour from one to twelve")
        hour = hour % 12 + (12 if period == "pm" else 0)
    elif 1 <= hour <= 12 and not leading_zero:
        raise ParseError("Please repeat the question with AM or PM, or use twenty four hour time")
    if not 0 <= hour <= 23:
        raise ParseError("That hour is invalid")
    total = (hour * 60 + minute + adjustment) % 1440
    return divmod(total, 60)


def until_clock(text, now):
    text = clean(text)
    day = None
    for word, offset in (("today", 0), ("tomorrow", 1)):
        if text.startswith(word + " "):
            day = now.date() + timedelta(days=offset)
            text = text[len(word):].strip()
        elif text.endswith(" " + word):
            day = now.date() + timedelta(days=offset)
            text = text[:-len(word)].strip()
    text = re.sub(r"^at\s+", "", text)
    hour, minute = parse_clock(text)
    target = datetime.combine(day or now.date(), datetime.min.time()).replace(
        hour=hour, minute=minute
    )
    if day is None and target < now:
        target += timedelta(days=1)
    if day is not None and target < now:
        raise ParseError("That time has already passed")
    # Reject nonexistent/repeated local times rather than silently choose a DST fold.
    timestamps = set()
    for fold in (0, 1):
        stamp = target.replace(fold=fold).timestamp()
        if datetime.fromtimestamp(stamp) == target:
            timestamps.add(stamp)
    if len(timestamps) != 1:
        raise ParseError("That local time is skipped or repeated by a clock change")
    return max(0, timestamps.pop() - now.timestamp()), target


@dataclass
class Timer:
    number: int
    label: str
    deadline: float


class CalendarTimers:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.timers = {}
        self.next_number = 1

    def has_due(self):
        now = self.clock()
        return any(timer.deadline <= now for timer in self.timers.values())

    def take_alerts(self):
        now = self.clock()
        due = sorted(
            (timer for timer in self.timers.values() if timer.deadline <= now),
            key=lambda timer: timer.deadline,
        )
        for timer in due:
            del self.timers[timer.number]
        return [f"{timer.label} has finished, sir." for timer in due]

    def find_timer(self, text):
        text = re.sub(r"^(?:my |the )+", "", clean(text))
        if text in {"", "timer"}:
            if len(self.timers) == 1:
                return next(iter(self.timers.values()))
            if not self.timers:
                raise ParseError("There are no active timers")
            raise ParseError("There is more than one timer. Please specify its number or name")
        text = re.sub(r"^timer\s+", "", text)
        try:
            number = integer(text, ordinal=True)
        except ParseError:
            number = None
        if number in self.timers:
            return self.timers[number]
        found = [timer for timer in self.timers.values()
                 if clean(timer.label) == text]
        if len(found) == 1:
            return found[0]
        raise ParseError("I could not find that timer")

    def handle(self, command, now=None):
        """Return None for unrelated commands, otherwise a complete spoken reply."""
        try:
            return self._handle(clean(command), now or datetime.now())
        except (ParseError, OverflowError) as error:
            return f"{error}, sir."

    def _handle(self, text, now):
        if text in {
            "what is the date", "what is the date today", "what is today's date",
            "what is todays date", "tell me the date", "what date is it",
            "what date is it today", "what is today",
        }:
            return f"Today is {now.strftime('%A')}, {date_label(now.date())}, sir."
        if text in {
            "what day is it", "what day is it today", "what day is today",
            "what day of the week is it", "what day of the week is it today",
            "what is the day today",
        }:
            return f"Today is {now.strftime('%A')}, sir."
        if text in {"what time is it", "what is the time", "tell me the time"}:
            return f"The time is {now.strftime('%I:%M %p').lstrip('0')}, sir."

        match = re.fullmatch(r"(?:how many days|how long)\s+(?:until|till)\s+(.+)", text)
        if match:
            target_text = match.group(1)
            # "How long until five PM" is handled by the clock branch below.
            is_clock = text.startswith("how long") and not (
                target_text in {"today", "tomorrow", "yesterday"}
                or any(re.search(r"\b" + word + r"\b", target_text)
                       for word in (*MONTHS, *WEEKDAYS))
                or re.fullmatch(r"in .+ (?:days?|weeks?)", target_text)
            )
            if not is_clock:
                target = parse_date(target_text, now.date())
                days = (target - now.date()).days
                label = date_label(target)
                if days < 0:
                    return f"{label} was {-days} calendar days ago, sir."
                if days == 0:
                    return f"{label} is today, sir."
                return f"There {'is' if days == 1 else 'are'} {days} calendar day{'' if days == 1 else 's'} until {label}, sir."

        match = re.fullmatch(
            r"(?:how many (minutes|hours|seconds)|how (long|much time))\s+(?:until|till)\s+(.+)",
            text,
        )
        if match:
            seconds, target = until_clock(match.group(3), now)
            unit = match.group(1)
            if unit == "minutes":
                value = f"about {math.ceil(seconds / 60)} minutes"
            elif unit == "hours":
                value = f"about {seconds / 3600:.1f} hours"
            elif unit == "seconds":
                value = f"about {math.ceil(seconds)} seconds"
            else:
                value = duration_label(seconds)
            label = target.strftime("%I:%M %p").lstrip("0")
            if target.date() != now.date():
                label += " tomorrow"
            return f"There are {value} until {label}, sir."

        match = re.fullmatch(r"what (?:day|day of the week) (?:is|will it be on)\s+((?!it\b).+)", text)
        if match:
            target = parse_date(match.group(1), now.date())
            return f"{date_label(target)} is a {target.strftime('%A')}, sir."
        match = re.fullmatch(
            r"what (date|day) (?:is(?: it)?|will(?: it)? be)\s+in\s+(.+)\s+(days?|weeks?)", text
        )
        if match:
            target = parse_date(f"in {match.group(2)} {match.group(3)}", now.date())
            return f"It will be {target.strftime('%A')}, {date_label(target)}, sir."

        match = re.fullmatch(r"(?:set|start)\s+(?:a |the )?timer\s+for\s+(.+)", text)
        if match:
            specification = match.group(1)
            named = re.fullmatch(r"(.+?)\s+(?:called|named)\s+(.+)", specification)
            seconds = duration_seconds(named.group(1) if named else specification)
            if len(self.timers) >= 10:
                return "Ten timers are already running. Cancel one before adding another, sir."
            number = self.next_number
            label = named.group(2).strip() if named else f"Timer {number}"
            if not 1 <= len(label) <= 40:
                return "Please use a shorter timer name, sir."
            if any(clean(t.label) == clean(label) for t in self.timers.values()):
                return "A timer with that name already exists. Please use another name, sir."
            if named and (re.fullmatch(r"(?:timer\s+)?\d+", label) or
                          label in {"all", "timer", "timers"}):
                return "Please use a descriptive timer name rather than a number, sir."
            self.next_number += 1
            self.timers[number] = Timer(number, label, self.clock() + seconds)
            return f"{label} is set for {duration_label(seconds)}, sir."

        if text in {"list timers", "list my timers", "timer status", "what timers are running",
                    "how much time is left on my timers"}:
            if not self.timers:
                return "There are no active timers, sir."
            remaining = [
                f"{timer.label}, {duration_label(timer.deadline - self.clock())} remaining"
                for timer in self.timers.values()
            ]
            return "; ".join(remaining) + ", sir."
        if text in {"cancel all timers", "stop all timers"}:
            count = len(self.timers)
            self.timers.clear()
            return f"Cancelled {count} timers, sir."
        match = re.fullmatch(r"(?:cancel|stop)\s+(?:(?:my|the)\s+)?timer(?:\s+(.+))?", text)
        if match:
            timer = self.find_timer(match.group(1) or "")
            del self.timers[timer.number]
            return f"{timer.label} is cancelled, sir."
        match = re.fullmatch(
            r"(?:how much time is left|how long is left|time remaining)\s+on\s+"
            r"(?:(?:my|the)\s+)?timer(?:\s+(.+))?", text
        )
        if match:
            timer = self.find_timer(match.group(1) or "")
            return f"{timer.label} has {duration_label(timer.deadline - self.clock())} remaining, sir."
        return None
