# Alarm Clock CLI Specification

## Assignment framing

Build a Python terminal alarm clock. The application must stay terminal-only:
no web UI, no React, and no database. Because the assignment has no detailed
product spec, the implementation focuses on a small, reliable alarm workflow
that can be tested without waiting in real time.

## Requirements

- Users can schedule an alarm for a relative duration:
  - Example: `python alarm.py in 10m --label "Stretch"`
  - Duration formats: `10s`, `5m`, `2h`, `1h30m`, `01:30`, `01:02:03`.
- Users can schedule an alarm for the next occurrence of a clock time:
  - Example: `python alarm.py at 07:30 --label "Wake up"`
  - If that time has already passed today, schedule it for tomorrow.
- Users can schedule recurring clock-time alarms:
  - Example: `python alarm.py at 07:30 --repeat daily`
  - Example: `python alarm.py at 09:00 --repeat days --days mon,tue,wed,thu,fri`
  - Recurring duration alarms are not supported.
- Users can provide a custom label.
- When the alarm fires, the CLI prints the label and rings the terminal bell
  unless `--no-bell` is supplied.
- Alarms play `assets/audio/alarm.mp3` by default when they fire.
- Users can provide an optional audio file override:
  - Example: `python alarm.py in 10m --audio-file ~/Music/alarm.wav`
  - The file path is validated before the CLI starts waiting.
- Users can list alarms with their ID, scheduled time, status, and label:
  - Example: `python alarm.py list`
  - Status values: `pending` and `triggered`.
- Users can turn off upcoming alarms:
  - Example: `python alarm.py off a1b2c3`
  - Example: `python alarm.py off --all`
  - Turning off an alarm removes it from the state file and stops its waiting
    process when it is still running.
- Users can open a Textual-powered TUI:
  - Example: `python alarm.py tui`
  - The TUI lists alarms and supports adding new alarms and turning off
    upcoming alarms.
- The CLI supports `--dry-run` so users and tests can validate a schedule
  without waiting.
- Invalid durations or times produce clear errors and a non-zero exit status.
- The CLI path uses the Python standard library. The TUI requires Textual.

## Non-goals

- No database or notifications.
- No background daemon. The terminal process must remain running until the alarm
  fires, and recurring alarms require that process to keep running between
  occurrences.
- No concurrent multiple-alarm scheduling.

## Design

The code is split into:

- `alarm.py`: thin executable entry point.
- `src/alarm_clock/core.py`: parsing and scheduling logic.
- `src/alarm_clock/cli.py`: argument parsing, dry-run behavior, waiting loop,
  recurrence rescheduling, terminal output, alarm cancellation, and audio-file
  playback through local system support.
- `src/alarm_clock/tui.py`: Textual app and background alarm launching for
  interactive terminal use.
- `src/alarm_clock/store.py`: JSON state for pending and triggered alarms,
  including backward-compatible recurrence metadata, so a separate `list`
  command can report alarm status.

The core module is side-effect free and covered by unit tests. The CLI module
accepts injectable clock and sleeper functions so tests can verify behavior
without real delays.

Audio playback uses standard-library process APIs and local system support:
`afplay` on macOS, `winsound` on Windows, or `paplay`, `aplay`, or `ffplay` on
Linux if available. Playback failures produce a warning after the alarm fires.

## Test plan

- Unit-test duration parsing for unit and colon formats.
- Unit-test clock-time parsing and next-day rollover.
- Unit-test recurrence parsing and next-occurrence scheduling.
- Unit-test invalid inputs.
- Unit-test CLI dry-run output and alarm triggering with fake time/sleep.
- Unit-test recurring alarm rescheduling in the state store.
- Unit-test audio-file validation and injected playback behavior.
- Unit-test alarm table listing and triggered status after an alarm completes.
- Unit-test turning off one pending alarm and all pending alarms.
- Unit-test TUI helper behavior and `tui` command dispatch without launching a
  real terminal UI.
- Run a smoke check through `alarm.py --dry-run`.
