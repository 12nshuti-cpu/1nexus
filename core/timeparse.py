"""Small, deterministic natural-language time parser for reminders.

Supports, in any position inside a sentence:

* relative:  ``in 10 minutes``, ``in 2 hours and 30 minutes``, ``in an hour``
* clock:     ``at 5pm``, ``at 17:30``, ``at 5:30 pm`` (rolls to tomorrow if past)
* day words: ``today``, ``tonight``, ``tomorrow``, ``on friday``, ``next monday``
* combos:    ``tomorrow at 9am``, ``friday at 3pm``

Times are naive *local* times (the computer's own clock). Anything the parser
cannot understand returns ``None`` so callers can ask the user instead of
guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "sixty": 60,
    "half": 0.5,
}
_UNIT_SECONDS = {
    "second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600,
    "day": 86400, "week": 604800,
}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_NUM = r"(?:\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, _NUMBER_WORDS), key=len, reverse=True)) + r")"
_UNIT = r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)"
_REL_PART = rf"(?:{_NUM}(?:\s+and\s+a\s+half)?\s*{_UNIT})"
_RELATIVE = re.compile(
    rf"\bin\s+(?P<rel>(?:half\s+an?\s+hour|{_REL_PART}(?:\s*(?:,|and)?\s*{_REL_PART})*))\b",
    re.IGNORECASE,
)
_DAY = re.compile(
    r"\b(?:(?P<next>next|on|this|coming)\s+)?(?P<day>today|tonight|tomorrow|"
    + "|".join(_WEEKDAYS)
    + r")\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"\b(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)\b"
    r"|\bat\s+(?P<h24>\d{1,2}):(?P<m24>[0-5]\d)\b"
    r"|\bat\s+(?P<hbare>\d{1,2})\b(?!\s*(?:am|pm|:))",
    re.IGNORECASE,
)
_NOON = re.compile(r"\b(?:at\s+)?(?P<w>noon|midnight)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedTime:
    due: datetime
    remainder: str  # the original text with the time expression removed


def _number(token: str) -> float:
    token = token.lower()
    return float(token) if re.fullmatch(r"\d+(?:\.\d+)?", token) else float(_NUMBER_WORDS[token])


def _parse_relative(text: str) -> float | None:
    if re.fullmatch(r"half\s+an?\s+hour", text.strip(), re.IGNORECASE):
        return 1800.0
    total = 0.0
    for match in re.finditer(rf"(?P<n>{_NUM})(?P<half>\s+and\s+a\s+half)?\s*(?P<u>{_UNIT})", text, re.IGNORECASE):
        unit = match.group("u").lower().rstrip("s")
        seconds = _UNIT_SECONDS.get(unit)
        if seconds is None:
            return None
        amount = _number(match.group("n")) + (0.5 if match.group("half") else 0)
        total += amount * seconds
    return total or None


def _clock_from(match: re.Match) -> tuple[int, int] | None:
    if match.group("ap"):
        hour, minute = int(match.group("h")), int(match.group("m") or 0)
        if not 1 <= hour <= 12:
            return None
        pm = match.group("ap").lower().startswith("p")
        return (hour % 12) + (12 if pm else 0), minute
    if match.group("h24"):
        hour, minute = int(match.group("h24")), int(match.group("m24"))
        return (hour, minute) if 0 <= hour <= 23 else None
    hour = int(match.group("hbare"))
    return (hour, 0) if 0 <= hour <= 23 else None


def _remove(text: str, span: tuple[int, int]) -> str:
    return (text[: span[0]] + " " + text[span[1]:]).strip()


def parse_time(text: str, now: datetime | None = None) -> ParsedTime | None:
    """Find a time expression in ``text`` and return when it refers to."""
    now = (now or datetime.now()).replace(microsecond=0)
    source = str(text or "")

    relative = _RELATIVE.search(source)
    if relative:
        seconds = _parse_relative(relative.group("rel"))
        if seconds is None or seconds <= 0:
            return None
        return ParsedTime(now + timedelta(seconds=seconds), _remove(source, relative.span()))

    day_match = _DAY.search(source)
    clock_match = _CLOCK.search(source)
    noon_match = _NOON.search(source)
    if not (day_match or clock_match or noon_match):
        return None

    spans = [m.span() for m in (day_match, clock_match, noon_match) if m]
    clock: tuple[int, int] | None = None
    if clock_match:
        clock = _clock_from(clock_match)
        if clock is None:
            return None
    elif noon_match:
        clock = (12, 0) if noon_match.group("w").lower() == "noon" else (0, 0)

    target_date = now.date()
    day_word = day_match.group("day").lower() if day_match else None

    if day_word == "tomorrow":
        target_date = now.date() + timedelta(days=1)
    elif day_word in _WEEKDAYS:
        # A weekday name always means its nearest *upcoming* occurrence
        # ("next friday" is treated the same way).
        ahead = (_WEEKDAYS.index(day_word) - now.weekday()) % 7
        if ahead == 0:
            same_day = datetime.combine(now.date(), datetime.min.time())
            if clock is None or same_day.replace(hour=clock[0], minute=clock[1]) <= now:
                ahead = 7
        target_date = now.date() + timedelta(days=ahead)
    elif day_word == "tonight" and clock is None:
        clock = (20, 0)

    if clock is None:
        clock = (9, 0)  # a bare "tomorrow"/"on friday" means 9:00
    due = datetime.combine(target_date, datetime.min.time()).replace(hour=clock[0], minute=clock[1])

    if day_word in {None, "today", "tonight"} and due <= now:
        due += timedelta(days=1)  # "at 5pm" said at 6pm means tomorrow

    remainder = source
    for span in sorted(spans, reverse=True):
        remainder = _remove(remainder, span)
    return ParsedTime(due, remainder)


# ----------------------------------------------------------------------
# Reminder sentence parsing
# ----------------------------------------------------------------------

_LEAD = re.compile(
    r"^(?:please\s+|can you\s+|could you\s+|nexus[,]?\s+)*"
    r"(?:(?:set|create|add|make)\s+(?:me\s+)?(?:a\s+|an\s+)?reminder|remind\s+me)\b[\s,:]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedReminder:
    message: str
    due: datetime


def is_reminder_request(text: str) -> bool:
    return bool(_LEAD.match(str(text or "").strip()))


def parse_reminder(text: str, now: datetime | None = None) -> ParsedReminder | None:
    """Parse "remind me to call mum in 10 minutes" into (message, due).

    Returns ``None`` if the sentence is not a reminder request, has no
    understandable time, or has no message.
    """
    value = str(text or "").strip().rstrip(".!")
    lead = _LEAD.match(value)
    if not lead:
        return None
    body = value[lead.end():].strip()
    parsed = parse_time(body, now)
    if parsed is None:
        return None
    message = parsed.remainder
    message = re.sub(r"^(?:to|that|about|for|of)\s+", "", message.strip(" ,:;-"), flags=re.IGNORECASE)
    message = re.sub(r"\s+(?:at|on|in|by|for)\s*$", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\s{2,}", " ", message).strip(" ,:;-")
    if not message:
        return None
    return ParsedReminder(message[:500], parsed.due)


def describe_due(due: datetime, now: datetime | None = None) -> str:
    """Human-friendly absolute time, e.g. 'today at 17:30' or 'Fri 24 Oct at 09:00'."""
    now = now or datetime.now()
    clock = due.strftime("%H:%M")
    if due.date() == now.date():
        return f"today at {clock}"
    if due.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {clock}"
    if 0 < (due.date() - now.date()).days < 7:
        return f"{due.strftime('%A')} at {clock}"
    return f"{due.strftime('%a %d %b')} at {clock}"
