"""Command-line interface for the alarm clock."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time as time_module
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from .core import (
    AlarmSpec,
    REPEAT_NONE,
    REPEAT_WEEKDAYS,
    build_alarm_spec,
    next_recurring_alarm_time,
    parse_weekdays,
)
from .store import (
    add_alarm,
    cancel_alarm,
    cancel_pending_alarms,
    list_alarms,
    mark_alarm_triggered,
    remove_alarm,
    update_alarm_schedule,
)


DEFAULT_LABEL = "Alarm"
DEFAULT_AUDIO_FILE_NAME = Path("assets") / "audio" / "alarm.mp3"
DEFAULT_AUDIO_FILE = Path(__file__).resolve().parents[2] / DEFAULT_AUDIO_FILE_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="Terminal-only alarm clock.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    in_parser = subparsers.add_parser(
        "in",
        help="Schedule an alarm after a relative duration.",
    )
    _add_schedule_arguments(
        in_parser,
        value_help="Duration such as 10m, 1h30m, 01:30, or 01:02:03.",
    )

    at_parser = subparsers.add_parser(
        "at",
        help="Schedule an alarm at the next occurrence of a clock time.",
    )
    _add_schedule_arguments(
        at_parser,
        value_help="Clock time such as 07:30 or 23:59:58.",
    )
    at_parser.add_argument(
        "--repeat",
        choices=["none", "daily", "days"],
        default=REPEAT_NONE,
        help="Repeat at this clock time: none, daily, or selected days.",
    )
    at_parser.add_argument(
        "--days",
        help="Comma-separated repeat days for --repeat days, such as mon,tue,friday.",
    )

    subparsers.add_parser("list", help="List alarms.")

    off_parser = subparsers.add_parser(
        "off",
        help="Turn off upcoming alarms.",
    )
    off_target = off_parser.add_mutually_exclusive_group(required=True)
    off_target.add_argument("alarm_id", nargs="?", help="Pending alarm ID to turn off.")
    off_target.add_argument(
        "--all",
        action="store_true",
        help="Turn off all pending alarms.",
    )

    subparsers.add_parser("tui", help="Open the terminal UI.")
    return parser


def _add_schedule_arguments(parser: argparse.ArgumentParser, *, value_help: str) -> None:
    parser.add_argument("value", help=value_help)
    parser.add_argument(
        "-l",
        "--label",
        dest="label",
        default=DEFAULT_LABEL,
        help="Label to show when the alarm fires.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show the schedule without waiting.",
    )
    parser.add_argument(
        "--no-bell",
        action="store_true",
        help="Do not ring the terminal bell when the alarm fires.",
    )
    parser.add_argument(
        "--audio-file",
        type=Path,
        help=(
            "Audio file to play when the alarm fires. "
            f"Defaults to {DEFAULT_AUDIO_FILE_NAME}."
        ),
    )


def play_audio_file(path: Path) -> None:
    if sys.platform == "darwin":
        _run_audio_player(["afplay", str(path)])
        return

    if sys.platform.startswith("win"):
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return

    for player in ("paplay", "aplay", "ffplay"):
        executable = shutil.which(player)
        if executable is None:
            continue
        if player == "ffplay":
            _run_audio_player([executable, "-nodisp", "-autoexit", str(path)])
        else:
            _run_audio_player([executable, str(path)])
        return

    raise RuntimeError(
        "No supported audio player found. Install paplay, aplay, or ffplay."
    )


def _run_audio_player(command: list[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Audio player not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Audio playback failed: {command[0]}") from exc


def run_alarm(
    spec: AlarmSpec,
    *,
    now_provider: Callable[[], datetime] = datetime.now,
    sleeper: Callable[[float], None] = time_module.sleep,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    bell: bool = True,
    audio_player: Callable[[Path], None] = play_audio_file,
    alarm_id: str | None = None,
    state_path: Path | None = None,
    max_fires: int | None = None,
) -> None:
    current_spec = spec
    fired_count = 0
    print(
        f"Scheduled alarm for {format_datetime(current_spec.scheduled_for)} "
        f"({current_spec.source}{format_repeat_suffix(current_spec)})",
        file=stdout,
    )
    stdout.flush()

    while True:
        while True:
            remaining = (current_spec.scheduled_for - now_provider()).total_seconds()
            if remaining <= 0:
                break
            sleeper(min(1.0, remaining))

        prefix = "\a" if bell else ""
        print(f"{prefix}ALARM: {current_spec.label}", file=stdout)
        stdout.flush()

        if current_spec.audio_file is not None:
            try:
                audio_player(current_spec.audio_file)
            except RuntimeError as exc:
                print(f"Warning: {exc}", file=stderr)

        fired_count += 1
        if current_spec.repeat == REPEAT_NONE:
            return

        clock_time = current_spec.clock_time or current_spec.scheduled_for.time()
        next_scheduled_for = next_recurring_alarm_time(
            now_provider(),
            clock_time,
            repeat=current_spec.repeat,
            repeat_days=current_spec.repeat_days,
        )
        if alarm_id is not None:
            updated = update_alarm_schedule(
                alarm_id,
                next_scheduled_for,
                state_path=state_path,
            )
            if not updated:
                return
        current_spec = replace(current_spec, scheduled_for=next_scheduled_for)
        print(
            f"Rescheduled alarm for {format_datetime(current_spec.scheduled_for)}",
            file=stdout,
        )
        stdout.flush()
        if max_fires is not None and fired_count >= max_fires:
            return


def format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_list_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def format_repeat(repeat: str, repeat_days: tuple[str, ...]) -> str:
    if repeat == REPEAT_NONE:
        return "none"
    if repeat == REPEAT_WEEKDAYS:
        return ",".join(repeat_days)
    return repeat


def format_repeat_suffix(spec: AlarmSpec) -> str:
    if spec.repeat == REPEAT_NONE:
        return ""
    return f", repeat {format_repeat(spec.repeat, spec.repeat_days)}"


def print_alarm_list(
    *,
    now: datetime,
    stdout: TextIO = sys.stdout,
    state_path: Path | None = None,
) -> None:
    alarms = list_alarms(now=now, state_path=state_path)
    if not alarms:
        print("No alarms.", file=stdout)
        return

    print(
        f"{'ID':<8}  {'Time':<16}  {'Status':<9}  {'Repeat':<11}  Label",
        file=stdout,
    )
    for alarm in alarms:
        print(
            f"{alarm.alarm_id:<8}  "
            f"{format_list_datetime(alarm.scheduled_for):<16}  "
            f"{alarm.status:<9}  "
            f"{format_repeat(alarm.repeat, alarm.repeat_days):<11}  "
            f"{alarm.label}",
            file=stdout,
        )


def validate_audio_file(path: Path | None) -> Path:
    selected = DEFAULT_AUDIO_FILE if path is None else path
    resolved = selected.expanduser()
    if not resolved.is_file():
        raise ValueError(f"Audio file does not exist: {selected}")
    return resolved


def main(
    argv: list[str] | None = None,
    *,
    now_provider: Callable[[], datetime] = datetime.now,
    sleeper: Callable[[float], None] = time_module.sleep,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    state_path: Path | None = None,
    audio_player: Callable[[Path], None] = play_audio_file,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        print_alarm_list(now=now_provider(), stdout=stdout, state_path=state_path)
        return 0

    if args.command == "off":
        now = now_provider()
        try:
            if args.all:
                canceled = cancel_pending_alarms(now=now, state_path=state_path)
                if not canceled:
                    print("No upcoming alarms to turn off.", file=stdout)
                    return 1
                count = len(canceled)
                noun = "alarm" if count == 1 else "alarms"
                print(f"Turned off {count} upcoming {noun}.", file=stdout)
                return 0

            canceled_alarm = cancel_alarm(
                args.alarm_id,
                now=now,
                state_path=state_path,
            )
        except PermissionError as exc:
            print(f"Error: Could not stop alarm process: {exc}", file=stderr)
            return 2

        if canceled_alarm is None:
            print(f"No pending alarm found with ID: {args.alarm_id}", file=stderr)
            return 1

        print(
            f"Turned off alarm {canceled_alarm.alarm_id}: {canceled_alarm.label}",
            file=stdout,
        )
        return 0

    if args.command == "tui":
        try:
            from .tui import run_tui

            return run_tui(state_path=state_path)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=stderr)
            return 2

    try:
        audio_file = validate_audio_file(args.audio_file)
        repeat_days = ()
        if getattr(args, "repeat", REPEAT_NONE) == "days":
            if not args.days:
                raise ValueError("--days is required with --repeat days")
            repeat_days = parse_weekdays(args.days)
        elif getattr(args, "days", None):
            raise ValueError("--days can only be used with --repeat days")
        spec = build_alarm_spec(
            mode=args.command,
            value=args.value,
            label=args.label,
            now=now_provider(),
            audio_file=audio_file,
            repeat=getattr(args, "repeat", REPEAT_NONE),
            repeat_days=repeat_days,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=stderr)
        return 2

    if args.dry_run:
        print(
            f"Scheduled alarm for {format_datetime(spec.scheduled_for)} "
            f"({spec.source}{format_repeat_suffix(spec)}): {spec.label}",
            file=stdout,
        )
        return 0

    alarm_id = add_alarm(spec, state_path=state_path)
    try:
        run_alarm(
            spec,
            now_provider=now_provider,
            sleeper=sleeper,
            stdout=stdout,
            stderr=stderr,
            bell=not args.no_bell,
            audio_player=audio_player,
            alarm_id=alarm_id,
            state_path=state_path,
        )
    except KeyboardInterrupt:
        remove_alarm(alarm_id, state_path=state_path)
        print("\nAlarm cancelled", file=stderr)
        return 130

    if spec.repeat == REPEAT_NONE:
        mark_alarm_triggered(alarm_id, state_path=state_path)

    return 0
