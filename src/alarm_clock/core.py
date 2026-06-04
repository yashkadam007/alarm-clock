"""Core parsing and scheduling logic for the alarm clock CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path


_UNIT_DURATION_RE = re.compile(r"(?P<amount>\d+)(?P<unit>[hms])")
_CLOCK_TIME_RE = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")


@dataclass(frozen=True)
class AlarmSpec:
    scheduled_for: datetime
    label: str
    source: str
    audio_file: Path | None = None


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


def build_alarm_spec(
    mode: str,
    value: str,
    label: str,
    now: datetime,
    audio_file: Path | None = None,
) -> AlarmSpec:
    if mode == "in":
        scheduled_for = now + parse_duration(value)
    elif mode == "at":
        scheduled_for = next_alarm_time(now, parse_clock_time(value))
    else:
        raise ValueError(f"Unsupported alarm mode: {mode}")

    return AlarmSpec(
        scheduled_for=scheduled_for,
        label=label,
        source=f"{mode} {value}",
        audio_file=audio_file,
    )
