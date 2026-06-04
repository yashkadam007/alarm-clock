"""Small JSON-backed state store for running alarms."""

from __future__ import annotations

import json
import os
import signal
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from .core import (
    AlarmSpec,
    REPEAT_NONE,
    REPEAT_WEEKDAYS,
    next_alarm_time,
    next_recurring_alarm_time,
    normalize_repeat_days,
    parse_repeat_mode,
)


STATE_ENV_VAR = "ALARM_CLOCK_STATE"
STATUS_PENDING = "pending"
STATUS_RINGING = "ringing"
STATUS_TRIGGERED = "triggered"
SNOOZE_MINUTES = 10


@dataclass(frozen=True)
class StoredAlarm:
    alarm_id: str
    scheduled_for: datetime
    status: str
    label: str
    source: str
    pid: int
    repeat: str = REPEAT_NONE
    repeat_days: tuple[str, ...] = ()
    clock_time: time | None = None
    enabled: bool = True


def default_state_path() -> Path:
    configured = os.environ.get(STATE_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".alarm_clock_alarms.json"


def add_alarm(spec: AlarmSpec, *, state_path: Path | None = None) -> str:
    path = state_path or default_state_path()
    alarms = _read_raw(path)
    alarm_id = uuid.uuid4().hex[:8]
    alarms.append(
        {
            "id": alarm_id,
            "scheduled_for": spec.scheduled_for.isoformat(),
            "status": "pending",
            "label": spec.label,
            "source": spec.source,
            "pid": os.getpid(),
            "repeat": spec.repeat,
            "repeat_days": list(spec.repeat_days),
            "clock_time": spec.clock_time.isoformat() if spec.clock_time else None,
            "enabled": spec.enabled,
        }
    )
    _write_raw(path, alarms)
    return alarm_id


def remove_alarm(alarm_id: str, *, state_path: Path | None = None) -> None:
    path = state_path or default_state_path()
    alarms = [alarm for alarm in _read_raw(path) if alarm.get("id") != alarm_id]
    _write_raw(path, alarms)


def mark_alarm_triggered(alarm_id: str, *, state_path: Path | None = None) -> None:
    path = state_path or default_state_path()
    alarms = []
    for item in _read_raw(path):
        if item.get("id") == alarm_id:
            item = {**item, "status": "triggered", "pid": 0, "enabled": False}
        alarms.append(item)
    _write_raw(path, alarms)


def mark_alarm_ringing(alarm_id: str, *, state_path: Path | None = None) -> bool:
    path = state_path or default_state_path()
    alarms = []
    updated = False
    for item in _read_raw(path):
        if item.get("id") == alarm_id:
            item = {**item, "status": STATUS_RINGING, "pid": os.getpid()}
            updated = True
        alarms.append(item)
    _write_raw(path, alarms)
    return updated


def update_alarm_schedule(
    alarm_id: str,
    scheduled_for: datetime,
    *,
    state_path: Path | None = None,
) -> bool:
    """Update one pending alarm to its next scheduled occurrence."""
    path = state_path or default_state_path()
    alarms = []
    updated = False
    for item in _read_raw(path):
        if item.get("id") == alarm_id:
            item = {
                **item,
                "scheduled_for": scheduled_for.isoformat(),
                "status": "pending",
                "pid": os.getpid(),
                "enabled": True,
            }
            updated = True
        alarms.append(item)
    _write_raw(path, alarms)
    return updated


def stop_ringing_alarm(
    alarm_id: str,
    *,
    now: datetime,
    state_path: Path | None = None,
    terminator: Callable[[int], None] | None = None,
) -> StoredAlarm | None:
    """Stop one ringing alarm and move it to its completed or next state."""
    alarms = list_alarms(now=now, state_path=state_path)
    selected = next(
        (
            alarm
            for alarm in alarms
            if alarm.alarm_id == alarm_id and alarm.status == STATUS_RINGING
        ),
        None,
    )
    if selected is None:
        return None

    _terminate_alarm(selected.pid, terminator=terminator)
    updated = []
    for alarm in alarms:
        if alarm.alarm_id != alarm_id:
            updated.append(alarm)
            continue
        if alarm.repeat == REPEAT_NONE:
            updated.append(replace(alarm, status=STATUS_TRIGGERED, pid=0, enabled=False))
        else:
            updated.append(_reschedule_recurring_alarm(alarm, now=now))

    _write_raw(
        state_path or default_state_path(),
        [_serialize_alarm(alarm) for alarm in updated],
    )
    return selected


def snooze_ringing_alarm(
    alarm_id: str,
    *,
    now: datetime,
    minutes: int = SNOOZE_MINUTES,
    state_path: Path | None = None,
    terminator: Callable[[int], None] | None = None,
) -> StoredAlarm | None:
    """Stop one ringing alarm and schedule the same record for a snoozed fire."""
    alarms = list_alarms(now=now, state_path=state_path)
    selected = next(
        (
            alarm
            for alarm in alarms
            if alarm.alarm_id == alarm_id and alarm.status == STATUS_RINGING
        ),
        None,
    )
    if selected is None:
        return None

    _terminate_alarm(selected.pid, terminator=terminator)
    snoozed_for = now + timedelta(minutes=minutes)
    updated = [
        (
            replace(
                alarm,
                scheduled_for=snoozed_for,
                status=STATUS_PENDING,
                pid=0,
                enabled=True,
            )
            if alarm.alarm_id == alarm_id
            else alarm
        )
        for alarm in alarms
    ]
    _write_raw(
        state_path or default_state_path(),
        [_serialize_alarm(alarm) for alarm in updated],
    )
    return selected


def disable_alarm(
    alarm_id: str,
    *,
    now: datetime,
    state_path: Path | None = None,
    terminator: Callable[[int], None] | None = None,
) -> StoredAlarm | None:
    """Disable and stop one saved alarm by ID."""
    alarms = list_alarms(now=now, state_path=state_path)
    selected = next(
        (
            alarm
            for alarm in alarms
            if alarm.alarm_id == alarm_id and alarm.enabled
        ),
        None,
    )
    if selected is None:
        return None

    _terminate_alarm(selected.pid, terminator=terminator)
    remaining = [
        (
            replace(alarm, status=STATUS_TRIGGERED, pid=0, enabled=False)
            if alarm.alarm_id == alarm_id
            else alarm
        )
        for alarm in alarms
    ]
    _write_raw(
        state_path or default_state_path(),
        [_serialize_alarm(alarm) for alarm in remaining],
    )
    return selected


def disable_enabled_alarms(
    *,
    now: datetime,
    state_path: Path | None = None,
    terminator: Callable[[int], None] | None = None,
) -> list[StoredAlarm]:
    """Disable and stop all enabled alarms."""
    alarms = list_alarms(now=now, state_path=state_path)
    canceled = [alarm for alarm in alarms if alarm.enabled]
    if not canceled:
        return []

    for alarm in canceled:
        _terminate_alarm(alarm.pid, terminator=terminator)

    remaining = [
        (
            replace(alarm, status=STATUS_TRIGGERED, pid=0, enabled=False)
            if alarm.enabled
            else alarm
        )
        for alarm in alarms
    ]
    _write_raw(
        state_path or default_state_path(),
        [_serialize_alarm(alarm) for alarm in remaining],
    )
    return canceled


def enable_alarm(
    alarm_id: str,
    *,
    now: datetime,
    state_path: Path | None = None,
) -> StoredAlarm | None:
    """Enable a saved alarm and compute its next concrete occurrence."""
    alarms = list_alarms(now=now, state_path=state_path)
    selected = next((alarm for alarm in alarms if alarm.alarm_id == alarm_id), None)
    if selected is None:
        return None

    clock_time = selected.clock_time or selected.scheduled_for.time()
    scheduled_for = _next_scheduled_for(
        now,
        clock_time,
        repeat=selected.repeat,
        repeat_days=selected.repeat_days,
    )
    updated_alarm = replace(
        selected,
        scheduled_for=scheduled_for,
        status=STATUS_PENDING,
        pid=os.getpid(),
        clock_time=clock_time,
        enabled=True,
    )
    updated = [
        updated_alarm if alarm.alarm_id == alarm_id else alarm for alarm in alarms
    ]
    _write_raw(
        state_path or default_state_path(),
        [_serialize_alarm(alarm) for alarm in updated],
    )
    return updated_alarm


def list_alarms(
    *,
    now: datetime,
    state_path: Path | None = None,
) -> list[StoredAlarm]:
    path = state_path or default_state_path()
    raw_alarms = _read_raw(path)
    alarms: list[StoredAlarm] = []

    for item in raw_alarms:
        alarm = _parse_alarm(item)
        if alarm is None:
            continue
        if _is_stale_pending(alarm, now=now):
            alarm = replace(alarm, status=STATUS_TRIGGERED, pid=0, enabled=False)
        alarms.append(alarm)

    alarms.sort(key=lambda alarm: alarm.scheduled_for)
    cleaned = [_serialize_alarm(alarm) for alarm in alarms]
    if cleaned != raw_alarms:
        _write_raw(path, cleaned)
    return alarms


def _read_raw(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_raw(path: Path, alarms: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(alarms, file, indent=2)
        file.write("\n")
    temp_path.replace(path)


def _parse_alarm(item: dict[str, Any]) -> StoredAlarm | None:
    try:
        alarm_id = str(item["id"])
        scheduled_for = datetime.fromisoformat(str(item["scheduled_for"]))
        status = str(item.get("status", "pending"))
        if status not in {STATUS_PENDING, STATUS_RINGING, STATUS_TRIGGERED}:
            return None
        raw_label = item.get("label", item.get("message"))
        if raw_label is None:
            return None
        label = str(raw_label)
        source = str(item["source"])
        pid = int(item.get("pid", 0))
        repeat = parse_repeat_mode(str(item.get("repeat", REPEAT_NONE)))
        if repeat == REPEAT_WEEKDAYS:
            raw_days = item.get("repeat_days", [])
            if not isinstance(raw_days, list):
                return None
            repeat_days = normalize_repeat_days([str(day) for day in raw_days])
        else:
            repeat_days = ()
        raw_clock_time = item.get("clock_time")
        clock_time = (
            time.fromisoformat(str(raw_clock_time)) if raw_clock_time else None
        )
        if clock_time is None:
            clock_time = scheduled_for.time()
        raw_enabled = item.get("enabled")
        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        else:
            enabled = status in {STATUS_PENDING, STATUS_RINGING}
    except (KeyError, TypeError, ValueError):
        return None

    return StoredAlarm(
        alarm_id=alarm_id,
        scheduled_for=scheduled_for,
        status=status,
        label=label,
        source=source,
        pid=pid,
        repeat=repeat,
        repeat_days=repeat_days,
        clock_time=clock_time,
        enabled=enabled,
    )


def _serialize_alarm(alarm: StoredAlarm) -> dict[str, Any]:
    return {
        "id": alarm.alarm_id,
        "scheduled_for": alarm.scheduled_for.isoformat(),
        "status": alarm.status,
        "label": alarm.label,
        "source": alarm.source,
        "pid": alarm.pid,
        "repeat": alarm.repeat,
        "repeat_days": list(alarm.repeat_days),
        "clock_time": alarm.clock_time.isoformat() if alarm.clock_time else None,
        "enabled": alarm.enabled,
    }


def _is_stale_pending(alarm: StoredAlarm, *, now: datetime) -> bool:
    if not alarm.enabled:
        return False
    if alarm.status != STATUS_PENDING:
        return False
    if alarm.pid and not _pid_is_running(alarm.pid):
        return True
    if alarm.scheduled_for <= now and not alarm.pid:
        return True
    return False


def _reschedule_recurring_alarm(alarm: StoredAlarm, *, now: datetime) -> StoredAlarm:
    clock_time = alarm.clock_time or alarm.scheduled_for.time()
    next_scheduled_for = _next_scheduled_for(
        now,
        clock_time,
        repeat=alarm.repeat,
        repeat_days=alarm.repeat_days,
    )
    return replace(
        alarm,
        scheduled_for=next_scheduled_for,
        status=STATUS_PENDING,
        pid=0,
        enabled=True,
    )


def _next_scheduled_for(
    now: datetime,
    clock_time: time,
    *,
    repeat: str,
    repeat_days: tuple[str, ...],
) -> datetime:
    if repeat == REPEAT_NONE:
        return next_alarm_time(now, clock_time)
    return next_recurring_alarm_time(
        now,
        clock_time,
        repeat=repeat,
        repeat_days=repeat_days,
    )


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_alarm(
    pid: int,
    *,
    terminator: Callable[[int], None] | None,
) -> None:
    if pid <= 0:
        return

    selected_terminator = terminator or _terminate_pid
    selected_terminator(pid)


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
