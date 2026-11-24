"""Pure wake/follow-up parsing. No audio, models, Windows APIs or file writes."""
import re

WAKE_PHRASES = ("jarvis", "hey jarvis", "jervis", "hey jervis")
SEPARATORS = " ,.!?;:"


def normalize(text):
    return " ".join(text.lower().replace("\u2019", "'").strip().split())


def remove_wake_marker(text, preserve_case=False):
    text = " ".join(text.replace("\u2019", "'").strip().split()).strip(SEPARATORS)
    wake = "(?:" + "|".join(re.escape(p) for p in sorted(WAKE_PHRASES, key=len, reverse=True)) + ")"
    # Prefix wins: "Jarvis, open Jarvis" still opens the Jarvis folder.
    match = re.fullmatch(wake + r"(?:[ ,.!?;:]+(.*))?", text, re.I)
    if match:
        command = (match.group(1) or "").strip(SEPARATORS)
    else:
        match = re.fullmatch(r"(.*?)[ ,.!?;:]+" + wake, text, re.I)
        if not match:
            return None
        command = match.group(1).strip(SEPARATORS)
    return command if preserve_case else normalize(command)


def command_for_transcript(transcript, following_up=False, pending=()):
    if following_up and any(getattr(item, "kind", None) == "organizer_dictate" for item in pending):
        # All text in this explicit dictation step is DATA, even "open Chrome".
        # Do not strip a literal Jarvis from the note's beginning or end.
        return " ".join(transcript.replace("\u2019", "'").strip().split())
    command = remove_wake_marker(transcript, preserve_case=True)
    if command is None and following_up:
        return " ".join(transcript.replace("\u2019", "'").strip().split()).strip(SEPARATORS)
    return command
