"""Core parsing and scheduling logic for the alarm clock CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path


_UNIT_DURATION_RE = re.compile(r"(?P<amount>\d+)(?P<unit>[hms])")
_CLOCK_TIME_RE = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")
REPEAT_NONE = "none"
REPEAT_DAILY = "daily"
REPEAT_WEEKDAYS = "weekdays"
REPEAT_MODES = {REPEAT_NONE, REPEAT_DAILY, REPEAT_WEEKDAYS}
WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_ALIASES = {
    "mon": "mon",
    "monday": "mon",
    "tue": "tue",
    "tues": "tue",
    "tuesday": "tue",
    "wed": "wed",
    "weds": "wed",
    "wednesday": "wed",
    "thu": "thu",
    "thur": "thu",
    "thurs": "thu",
    "thursday": "thu",
    "fri": "fri",
    "friday": "fri",
    "sat": "sat",
    "saturday": "sat",
    "sun": "sun",
    "sunday": "sun",
}


@dataclass(frozen=True)
class AlarmSpec:
    scheduled_for: datetime
    label: str
    source: str
    audio_file: Path | None = None
    repeat: str = REPEAT_NONE
    repeat_days: tuple[str, ...] = ()
    clock_time: time | None = None


def parse_duration(value: str) -> timedelta:
    """Parse a positive duration from unit or colon notation."""
    text = value.strip().lower()
    if not text:
        raise ValueError("Duration is required")

    if ":" in text:
        duration = _parse_colon_duration(text)
    else:
        duration = _parse_unit_duration(text)

    if duration.total_seconds() <= 0:
        raise ValueError("Duration must be greater than zero")
    return duration


def _parse_unit_duration(text: str) -> timedelta:
    position = 0
    seconds = 0
    units = {"h": 3600, "m": 60, "s": 1}

    for match in _UNIT_DURATION_RE.finditer(text):
        if match.start() != position:
            raise ValueError(f"Invalid duration: {text}")
        position = match.end()
        seconds += int(match.group("amount")) * units[match.group("unit")]

    if position != len(text):
        raise ValueError(f"Invalid duration: {text}")
    return timedelta(seconds=seconds)


def _parse_colon_duration(text: str) -> timedelta:
    parts = text.split(":")
    if len(parts) == 2:
        minutes_text, seconds_text = parts
        hours_text = "0"
    elif len(parts) == 3:
        hours_text, minutes_text, seconds_text = parts
    else:
        raise ValueError(f"Invalid duration: {text}")

    if not all(part.isdigit() for part in [hours_text, minutes_text, seconds_text]):
        raise ValueError(f"Invalid duration: {text}")

    hours = int(hours_text)
    minutes = int(minutes_text)
    seconds = int(seconds_text)
    if minutes > 59 or seconds > 59:
        raise ValueError(f"Invalid duration: {text}")

    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_clock_time(value: str) -> time:
    """Parse HH:MM or HH:MM:SS clock time."""
    text = value.strip()
    if not _CLOCK_TIME_RE.match(text):
        raise ValueError("Clock time must use HH:MM or HH:MM:SS")

    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        hour, minute = parts
        second = 0
    else:
        hour, minute, second = parts

    try:
        return time(hour=hour, minute=minute, second=second)
    except ValueError as exc:
        raise ValueError(f"Invalid clock time: {text}") from exc


def next_alarm_time(now: datetime, target_time: time) -> datetime:
    """Return the next datetime matching target_time."""
    scheduled = datetime.combine(now.date(), target_time)
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return scheduled


def parse_repeat_mode(value: str) -> str:
    """Normalize a user-facing repeat mode to its persisted representation."""
    text = value.strip().lower()
    if text == "days":
        return REPEAT_WEEKDAYS
    if text in REPEAT_MODES:
        return text
    raise ValueError("Repeat must be one of: none, daily, days")


def parse_weekdays(value: str) -> tuple[str, ...]:
    """Parse comma-separated weekdays into stable mon..sun abbreviations."""
    text = value.strip().lower()
    if not text:
        raise ValueError("At least one repeat day is required")

    selected: list[str] = []
    for part in text.split(","):
        day_text = part.strip()
        if not day_text:
            raise ValueError("Repeat days must be comma-separated day names")
        try:
            day = _WEEKDAY_ALIASES[day_text]
        except KeyError as exc:
            raise ValueError(f"Invalid repeat day: {day_text}") from exc
        if day not in selected:
            selected.append(day)

    selected.sort(key=WEEKDAY_NAMES.index)
    return tuple(selected)


def next_recurring_alarm_time(
    now: datetime,
    target_time: time,
    *,
    repeat: str,
    repeat_days: tuple[str, ...] = (),
) -> datetime:
    """Return the next datetime for a recurring clock-time alarm."""
    normalized_repeat = parse_repeat_mode(repeat)
    if normalized_repeat == REPEAT_DAILY:
        return next_alarm_time(now, target_time)
    if normalized_repeat != REPEAT_WEEKDAYS:
        raise ValueError("Recurring alarm must repeat daily or on selected days")

    normalized_days = normalize_repeat_days(repeat_days)
    selected_indexes = {WEEKDAY_NAMES.index(day) for day in normalized_days}
    for offset in range(8):
        candidate_date = now.date() + timedelta(days=offset)
        if candidate_date.weekday() not in selected_indexes:
            continue
        candidate = datetime.combine(candidate_date, target_time)
        if candidate > now:
            return candidate

    raise ValueError("No valid repeat day found")


def normalize_repeat_days(days: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if not days:
        raise ValueError("At least one repeat day is required")

    selected: list[str] = []
    for raw_day in days:
        day_text = str(raw_day).strip().lower()
        try:
            day = _WEEKDAY_ALIASES[day_text]
        except KeyError as exc:
            raise ValueError(f"Invalid repeat day: {day_text}") from exc
        if day not in selected:
            selected.append(day)

    selected.sort(key=WEEKDAY_NAMES.index)
    return tuple(selected)


def build_alarm_spec(
    mode: str,
    value: str,
    label: str,
    now: datetime,
    audio_file: Path | None = None,
    repeat: str = REPEAT_NONE,
    repeat_days: tuple[str, ...] = (),
) -> AlarmSpec:
    normalized_repeat = parse_repeat_mode(repeat)
    normalized_days: tuple[str, ...] = ()
    clock_time: time | None = None

    if mode == "in":
        if normalized_repeat != REPEAT_NONE or repeat_days:
            raise ValueError("Recurring alarms require the 'at' command")
        scheduled_for = now + parse_duration(value)
    elif mode == "at":
        clock_time = parse_clock_time(value)
        if normalized_repeat == REPEAT_WEEKDAYS:
            normalized_days = normalize_repeat_days(repeat_days)
            scheduled_for = next_recurring_alarm_time(
                now,
                clock_time,
                repeat=normalized_repeat,
                repeat_days=normalized_days,
            )
        elif normalized_repeat == REPEAT_DAILY:
            if repeat_days:
                raise ValueError("--days can only be used with --repeat days")
            scheduled_for = next_alarm_time(now, clock_time)
        else:
            if repeat_days:
                raise ValueError("--days can only be used with --repeat days")
            scheduled_for = next_alarm_time(now, clock_time)
    else:
        raise ValueError(f"Unsupported alarm mode: {mode}")

    return AlarmSpec(
        scheduled_for=scheduled_for,
        label=label,
        source=f"{mode} {value}",
        audio_file=audio_file,
        repeat=normalized_repeat,
        repeat_days=normalized_days,
        clock_time=clock_time,
    )
