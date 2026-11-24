"""Local notes and one-off reminders. SQLite, strict dates, explicit confirmations.
No microphone, LLM, shell commands, cloud service or background scheduler.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import os
from pathlib import Path
import re
import sqlite3
import time

from jarvis_time import ParseError, clean, integer, parse_clock, parse_date, duration_seconds

MAX_BODY = 400
MAX_REMINDER_BODY = 240
PAGE_SIZE = 3
MAX_NOTES = 1000
MAX_REMINDERS = 2000


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class Draft:
    kind: str
    data: dict


@dataclass(frozen=True)
class Reply:
    text: str
    draft: Draft | None = None


def body_text(text, limit=MAX_BODY):
    text = " ".join(text.strip().split())
    if not text:
        raise ParseError("The text is empty")
    if len(text) > limit:
        raise ParseError(f"Please keep that text to at most {limit} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ParseError("That text contains an unsupported control character")
    return text


def identifier(text):
    value = integer(re.sub(r"^(?:number\s+)?", "", clean(text)))
    if not 1 <= value <= 1000000:
        raise ParseError("Please use the saved item's positive number")
    return value


def local_label(stamp):
    value = datetime.fromtimestamp(stamp).astimezone()
    clock_format = "%I:%M:%S %p" if value.second else "%I:%M %p"
    return (f"{value.strftime('%A, %B')} {value.day}, {value.year}, "
            f"at {value.strftime(clock_format).lstrip('0')} "
            f"{value.tzname()}, UTC{value.strftime('%z')}")


def unique_local_timestamp(target):
    """Reject DST gaps/folds instead of silently selecting an occurrence."""
    candidates = set()
    for fold in (0, 1):
        stamp = target.replace(fold=fold).timestamp()
        if datetime.fromtimestamp(stamp) == target:
            candidates.add(stamp)
    if len(candidates) != 1:
        raise ParseError("That local time is skipped or repeated by a clock change; choose another time")
    return candidates.pop()


def schedule(text, now_stamp):
    text = clean(text)
    now = datetime.fromtimestamp(now_stamp)
    if text.startswith("in "):
        due = math.ceil(now_stamp + duration_seconds(text[3:]))
    else:
        match = re.fullmatch(r"(?:(.+?)\s+)?at\s+(.+)", text)
        if not match:
            raise ParseError("Say in ten minutes, or tomorrow at six PM")
        date_text, clock_text = match.groups()
        hour, minute = parse_clock(clock_text)
        if date_text:
            day = parse_date(re.sub(r"^on\s+", "", date_text), now.date())
        else:
            day = now.date()
        target = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
        if not date_text and target <= now:
            target += timedelta(days=1)
        due = unique_local_timestamp(target)
    if not math.isfinite(due) or due <= now_stamp:
        raise ParseError("That time has already passed")
    if due - now_stamp > 366 * 86400:
        raise ParseError("Please choose a date within the next 366 days")
    return due


def reminder_request(text, now_stamp):
    # Preserve the actual reminder text, not just its lower-case command form.
    match = re.match(r"^(?:remind me|set (?:a )?reminder)(?:\s+for)?\s+(.+)$", text, re.I)
    if not match:
        raise ParseError("Say remind me tomorrow at six PM to practise guitar")
    tail = match.group(1)
    candidates = []
    errors = []
    # 'quarter to six PM' and a task containing 'to' are both valid.
    for separator in re.finditer(r"\s+to\s+", tail, re.I):
        when = tail[:separator.start()]
        task = tail[separator.end():]
        try:
            due = schedule(when, now_stamp)
            candidates.append((due, body_text(task, MAX_REMINDER_BODY)))
        except (ParseError, ValueError, OverflowError, OSError) as error:
            errors.append(str(error))
    if len(candidates) != 1:
        if len(candidates) > 1:
            raise ParseError("The date and reminder text are ambiguous; please rephrase")
        if errors:
            raise ParseError(errors[0])
        raise ParseError("Include the reminder text after to, such as in ten minutes to stretch")
    return candidates[0]


class Store:
    """Single-instance lease plus transactional, parameterized SQLite writes."""
    def __init__(self, path):
        self.path = Path(path)
        self.db = None
        self.lease = None
        self.locked = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.lease = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
            self.lease.seek(0, 2)
            if self.lease.tell() == 0:
                self.lease.write(b"\0")
                self.lease.flush()
            self.lease.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.locked = True
            self.db = sqlite3.connect(self.path, timeout=1.0, isolation_level="DEFERRED",
                                      autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StoreError("The organizer database failed its integrity check; it was not reset")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if self.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone():
                    raise StoreError("This is an unrecognized database; it was not overwritten")
                with self.db:
                    self.db.execute("BEGIN")
                    self.db.execute("""CREATE TABLE notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        body TEXT NOT NULL,
                        created REAL NOT NULL,
                        archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
                        version INTEGER NOT NULL DEFAULT 1
                    )""")
                    self.db.execute("""CREATE TABLE reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        body TEXT NOT NULL,
                        due REAL NOT NULL,
                        created REAL NOT NULL,
                        confirmed_label TEXT NOT NULL,
                        cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
                        announced_at REAL,
                        version INTEGER NOT NULL DEFAULT 1
                    )""")
                    self.db.execute("CREATE INDEX reminder_due ON reminders(cancelled, announced_at, due)")
                    self.db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise StoreError("The organizer database version is unsupported; it was not changed")
            # Validate expected columns even for a version-1 file.
            self.db.execute("SELECT id,body,created,archived,version FROM notes LIMIT 0")
            self.db.execute(
                "SELECT id,body,due,created,confirmed_label,cancelled,announced_at,version FROM reminders LIMIT 0"
            )
        except (OSError, sqlite3.Error, StoreError) as error:
            self.close()
            raise StoreError(
                "Notes and reminders could not open their local storage. "
                "Another JARVIS instance, file permissions or database damage may be responsible. "
                + str(error)
            ) from error

    def close(self):
        try:
            if self.db is not None:
                self.db.close()
                self.db = None
        finally:
            if self.lease is not None:
                try:
                    if self.locked:
                        self.lease.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(self.lease.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(self.lease.fileno(), fcntl.LOCK_UN)
                finally:
                    self.lease.close()
                    self.lease = None
                    self.locked = False

    def get_note(self, number):
        row = self.db.execute("SELECT * FROM notes WHERE id=?", (number,)).fetchone()
        if row is None:
            raise ParseError("I could not find that note number")
        return dict(row)

    def get_reminder(self, number):
        row = self.db.execute("SELECT * FROM reminders WHERE id=?", (number,)).fetchone()
        if row is None:
            raise ParseError("I could not find that reminder number")
        return dict(row)

    def add_note(self, body, now):
        body = body_text(body)
        with self.db:
            if self.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0] >= MAX_NOTES:
                raise ParseError("This notebook has reached its one thousand note limit, including archived notes")
            cursor = self.db.execute("INSERT INTO notes(body,created) VALUES(?,?)", (body, now))
            number = cursor.lastrowid
        return number

    def add_reminder(self, body, due, label, now):
        body = body_text(body, MAX_REMINDER_BODY)
        if not math.isfinite(due) or due <= now:
            raise ParseError("That reminder time passed before confirmation; please set it again")
        with self.db:
            if self.db.execute("SELECT COUNT(*) FROM reminders").fetchone()[0] >= MAX_REMINDERS:
                raise ParseError("The saved reminder history has reached its two thousand item limit")
            cursor = self.db.execute(
                "INSERT INTO reminders(body,due,created,confirmed_label) VALUES(?,?,?,?)",
                (body, due, now, label),
            )
            number = cursor.lastrowid
        return number

    def change_note(self, number, version, archived):
        with self.db:
            cursor = self.db.execute(
                "UPDATE notes SET archived=?,version=version+1 WHERE id=? AND version=?",
                (int(archived), number, version),
            )
            if cursor.rowcount != 1:
                raise ParseError("That note changed; please ask again")

    def change_reminder(self, number, version, cancelled):
        with self.db:
            cursor = self.db.execute(
                """UPDATE reminders SET cancelled=?,announced_at=NULL,version=version+1
                   WHERE id=? AND version=?""",
                (int(cancelled), number, version),
            )
            if cursor.rowcount != 1:
                raise ParseError("That reminder changed; please ask again")

    def notes_page(self, after=0, archived=False):
        rows = self.db.execute(
            "SELECT * FROM notes WHERE archived=? AND id>? ORDER BY id LIMIT ?",
            (int(archived), after, PAGE_SIZE + 1),
        ).fetchall()
        return [dict(row) for row in rows]

    def reminders_page(self, after=0, cancelled=False):
        # Stable ID pagination, not a moving display-index.
        rows = self.db.execute(
            "SELECT * FROM reminders WHERE cancelled=? AND id>? ORDER BY id LIMIT ?",
            (int(cancelled), after, PAGE_SIZE + 1),
        ).fetchall()
        return [dict(row) for row in rows]

    def next_due(self):
        return self.db.execute(
            "SELECT MIN(due) FROM reminders WHERE cancelled=0 AND announced_at IS NULL"
        ).fetchone()[0]

    def due_rows(self, now):
        return [dict(row) for row in self.db.execute(
            """SELECT * FROM reminders WHERE cancelled=0 AND announced_at IS NULL
               AND due<=? ORDER BY due,id""", (now,)
        ).fetchall()]

    def acknowledge_announcements(self, rows, now):
        # Only after the frontend has completed the spoken batch/summary.
        with self.db:
            for row in rows:
                self.db.execute(
                    """UPDATE reminders SET announced_at=?
                       WHERE id=? AND version=? AND cancelled=0 AND announced_at IS NULL""",
                    (now, row["id"], row["version"]),
                )


NOTE_START = {"take a note", "make a note", "add a note"}
NOTE_READ = {"read my notes", "read notes", "list my notes", "list notes"}
REMINDER_READ = {"read my reminders", "read reminders", "list my reminders", "list reminders"}
NOTE_PREFIX = re.compile(r"^(?:take a note|make a note|add a note|note that)\s*[:,-]?\s+(.+)$", re.I)


def is_request(command):
    text = clean(command)
    return (text in NOTE_START | NOTE_READ | REMINDER_READ
            or text in {"list archived notes", "read archived notes",
                        "list cancelled reminders", "read cancelled reminders"}
            or bool(re.match(
                r"^(?:take a note|make a note|add a note|note that|remind me|set (?:a )?reminder"
                r"|read (?:note|reminder)\b|(?:read|list) (?:archived )?notes after\b"
                r"|(?:read|list) (?:cancelled )?reminders after\b"
                r"|(?:archive|delete|restore) note\b|(?:cancel|restore) reminder\b)",
                text)))


class Organizer:
    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.store = Store(path)
        self.next_deadline = self.store.next_due()

    def close(self):
        self.store.close()

    def refresh_deadline(self):
        self.next_deadline = self.store.next_due()

    def has_due(self):
        # No database polling on the microphone capture path.
        return self.next_deadline is not None and self.next_deadline <= self.clock()

    def due_rows(self):
        return self.store.due_rows(self.clock())

    def acknowledge(self, rows):
        self.store.acknowledge_announcements(rows, self.clock())
        self.refresh_deadline()

    def alert_text(self, rows, started_at):
        if not rows:
            return ""
        print("\nDUE REMINDERS:", flush=True)
        for row in rows:
            print(f'#{row["id"]}: {local_label(row["due"])}: {row["body"]}', flush=True)
        spoken = []
        for row in rows[:PAGE_SIZE]:
            if row["due"] < started_at:
                spoken.append(
                    f'Missed reminder {row["id"]}, due {local_label(row["due"])}: {row["body"]}'
                )
            else:
                spoken.append(f'Reminder {row["id"]}: {row["body"]}')
        if len(rows) > PAGE_SIZE:
            spoken.append(
                f'There are {len(rows) - PAGE_SIZE} more due reminders, listed in the terminal. '
                'Say read reminder followed by its number for the full text'
            )
        return ". ".join(spoken).rstrip(".") + ", sir."

    def handle(self, command, draft=None):
        if draft is None and not is_request(command):
            return None
        try:
            result = self._handle(command, draft)
            self.refresh_deadline()
            return result
        except (ParseError, ValueError, OverflowError, OSError) as error:
            return Reply(str(error).rstrip(".") + ", sir.")
        except sqlite3.Error as error:
            print("Organizer storage error:", error, flush=True)
            return Reply("The storage operation failed. I cannot confirm it was saved; check the terminal, sir.")

    def _handle(self, command, draft):
        text = clean(command)
        if draft:
            if draft.kind == "organizer_dictate":
                body = body_text(command)
                return Reply(
                    f'The note says: {body}. Say save note to keep it, change note to dictate again, or cancel, sir.',
                    Draft("organizer_note_save", {"body": body}),
                )
            if draft.kind == "organizer_note_save":
                if text == "change note":
                    return Reply("Dictate one short note after LISTENING, without a wake phrase, sir.",
                                 Draft("organizer_dictate", {}))
                if text == "save note":
                    number = self.store.add_note(draft.data["body"], self.clock())
                    return Reply(f"Note {number} is saved locally, sir.")
                return Reply("Say save note, change note, or cancel, sir.", draft)
            if draft.kind == "organizer_reminder_save":
                if text in {"save reminder", "confirm reminder"}:
                    data = draft.data
                    number = self.store.add_reminder(data["body"], data["due"], data["label"], self.clock())
                    return Reply(f'Reminder {number} is saved for {data["label"]}, sir.')
                return Reply("Say save reminder or cancel, sir.", draft)
            if draft.kind == "organizer_note_change":
                if text == draft.data["confirmation"]:
                    data = draft.data
                    self.store.change_note(data["id"], data["version"], data["archived"])
                    verb = "archived" if data["archived"] else "restored"
                    return Reply(f'Note {data["id"]} is {verb}, sir.')
                return Reply(f'Say {draft.data["confirmation"]}, or cancel, sir.', draft)
            if draft.kind == "organizer_reminder_change":
                if text == draft.data["confirmation"]:
                    data = draft.data
                    self.store.change_reminder(data["id"], data["version"], data["cancelled"])
                    verb = "cancelled" if data["cancelled"] else "restored"
                    return Reply(f'Reminder {data["id"]} is {verb}, sir.')
                return Reply(f'Say {draft.data["confirmation"]}, or cancel, sir.', draft)
            return Reply("That pending organizer request is invalid; please ask again, sir.")

        if text in NOTE_START:
            return Reply("Dictate one short note after LISTENING, without a wake phrase, sir.",
                         Draft("organizer_dictate", {}))
        match = NOTE_PREFIX.fullmatch(command.strip())
        if match:
            return self._handle(match.group(1), Draft("organizer_dictate", {}))
        if re.match(r"^(?:remind me|set (?:a )?reminder)\b", text):
            due, body = reminder_request(command, self.clock())
            label = local_label(due)
            return Reply(
                f'Remind you {label} to {body}. Say save reminder or cancel, sir.',
                Draft("organizer_reminder_save", {"body": body, "due": due, "label": label}),
            )
        match = re.fullmatch(r"(?:archive|delete|restore) note\s+(.+)", text)
        if match:
            row = self.store.get_note(identifier(match.group(1)))
            archived = not text.startswith("restore ")
            if bool(row["archived"]) == archived:
                return Reply(f'That note is already {"archived" if archived else "active"}, sir.')
            verb = "archive" if archived else "restore"
            data = {"id": row["id"], "version": row["version"],
                    "archived": archived, "confirmation": "confirm " + verb}
            return Reply(
                f'{verb.capitalize()} note {row["id"]}: {row["body"]}. '
                f'Say confirm {verb} or cancel. Archiving does not permanently delete the text, sir.',
                Draft("organizer_note_change", data),
            )
        match = re.fullmatch(r"(cancel|restore) reminder\s+(.+)", text)
        if match:
            row = self.store.get_reminder(identifier(match.group(2)))
            cancelled = match.group(1) == "cancel"
            if bool(row["cancelled"]) == cancelled:
                return Reply(f'That reminder is already {"cancelled" if cancelled else "active"}, sir.')
            verb = "cancel" if cancelled else "restore"
            data = {"id": row["id"], "version": row["version"],
                    "cancelled": cancelled, "confirmation": "confirm " + verb}
            extra = (" Its time has passed, so restoring it will announce it shortly."
                     if not cancelled and row["due"] <= self.clock() else "")
            return Reply(
                f'{verb.capitalize()} reminder {row["id"]}, due {local_label(row["due"])}: '
                f'{row["body"]}.{extra} Say confirm {verb} or cancel, sir.',
                Draft("organizer_reminder_change", data),
            )
        match = re.fullmatch(r"read note\s+(.+)", text)
        if match:
            row = self.store.get_note(identifier(match.group(1)))
            status = "Archived note" if row["archived"] else "Note"
            return Reply(f'{status} {row["id"]}: {row["body"]}, sir.')
        match = re.fullmatch(r"read reminder\s+(.+)", text)
        if match:
            row = self.store.get_reminder(identifier(match.group(1)))
            return Reply(self.reminder_line(row) + ", sir.")

        notes_page = re.fullmatch(r"(?:read|list) (archived )?notes after\s+(.+)", text)
        if text in NOTE_READ | {"list archived notes", "read archived notes"} or notes_page:
            archived = "archived " in text
            after = identifier(notes_page.group(2)) if notes_page else 0
            rows = self.store.notes_page(after, archived)
            if not rows:
                return Reply("There are no more notes in that list, sir.")
            lines = [f'Note {row["id"]}: {row["body"]}' for row in rows[:PAGE_SIZE]]
            if len(rows) > PAGE_SIZE:
                category = "archived notes" if archived else "notes"
                lines.append(f'For more, say read {category} after {rows[PAGE_SIZE - 1]["id"]}')
            return Reply(". ".join(lines).rstrip(".") + ", sir.")

        reminders_page = re.fullmatch(r"(?:read|list) (cancelled )?reminders after\s+(.+)", text)
        if text in REMINDER_READ | {"list cancelled reminders", "read cancelled reminders"} or reminders_page:
            cancelled = "cancelled " in text
            after = identifier(reminders_page.group(2)) if reminders_page else 0
            rows = self.store.reminders_page(after, cancelled)
            if not rows:
                return Reply("There are no more reminders in that list, sir.")
            lines = [self.reminder_line(row) for row in rows[:PAGE_SIZE]]
            if len(rows) > PAGE_SIZE:
                category = "cancelled reminders" if cancelled else "reminders"
                lines.append(f'For more, say read {category} after {rows[PAGE_SIZE - 1]["id"]}')
            return Reply(". ".join(lines).rstrip(".") + ", sir.")
        return Reply("Try take a note, read my notes, or remind me tomorrow at six PM to stretch, sir.")

    def reminder_line(self, row):
        if row["cancelled"]:
            status = "cancelled"
        elif row["announced_at"] is not None:
            status = "announcement made, not a completion confirmation"
        elif row["due"] <= self.clock():
            status = "overdue"
        else:
            status = "scheduled"
        return f'Reminder {row["id"]}, {status}, due {local_label(row["due"])}: {row["body"]}'
