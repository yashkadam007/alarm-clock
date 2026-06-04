# Alarm Clock CLI Specification

## Assignment framing

Build a Python terminal alarm clock. The application must stay terminal-only:
no web UI, no React, and no database. Because the assignment has no detailed
product spec, the implementation focuses on a small, reliable alarm workflow
that can be tested without waiting in real time.

## Requirements

- Users can create a reusable alarm for the next occurrence of a clock time:
  - Example: `python alarm.py add 07:30 --label "Wake up"`
  - If that time has already passed today, schedule it for tomorrow.
  - `add` starts a detached Python worker, records its PID in the JSON state
    file, and returns without waiting for the alarm time.
  - `--foreground` keeps the legacy behavior of waiting in the current terminal.
- Users can schedule recurring clock-time alarms:
  - Example: `python alarm.py add 07:30 --repeat daily`
  - Example: `python alarm.py add 09:00 --repeat days --days mon,tue,wed,thu,fri`
- Duration-based scheduling is not part of the alarm feature.
- Users can provide a custom label.
- When the alarm fires, the CLI prints the label and rings the terminal bell
  unless `--no-bell` is supplied.
- Alarms play `assets/audio/alarm.mp3` by default when they fire.
- Users can provide an optional audio file override:
  - Example: `python alarm.py add 07:30 --audio-file ~/Music/alarm.wav`
  - The file path is validated before the worker starts.
- Users can list alarms with their ID, scheduled time, status, and label:
  - Example: `python alarm.py list`
  - Status values: `on`, `off`, and `ringing`.
- Users can turn saved alarms on or off:
  - Example: `python alarm.py on a1b2c3`
  - Example: `python alarm.py off a1b2c3`
  - Example: `python alarm.py off --all`
  - Turning off an alarm keeps it visible, marks it disabled, and stops its
    worker process when it is still running.
- Users can open a Textual-powered TUI:
  - Example: `python alarm.py tui`
  - The TUI lists alarms and supports adding new alarms and turning off enabled
    alarms.
- The CLI supports `--dry-run` so users and tests can validate a schedule
  without waiting.
- Invalid times produce clear errors and a non-zero exit status.
- The CLI path uses the Python standard library. The TUI requires Textual.

## Non-goals

- No database or notifications.
- No background daemon or OS scheduler integration. Alarms use ordinary
  detached Python worker processes.
- No reboot, logout, or machine-sleep recovery.

## Design

The code is split into:

- `alarm.py`: thin executable entry point.
- `src/alarm_clock/core.py`: parsing and scheduling logic.
- `src/alarm_clock/cli.py`: argument parsing, dry-run behavior, detached worker
  launch, worker command dispatch, waiting loop, recurrence rescheduling,
  terminal output, alarm enable/disable actions, and audio-file playback through
  local system support.
- `src/alarm_clock/tui.py`: Textual app and background alarm launching for
  interactive terminal use.
- `src/alarm_clock/store.py`: JSON state for saved time-of-day alarms,
  including backward-compatible migration from date-bound records, so a
  separate `list` command can report alarm status.

The core module is side-effect free and covered by unit tests. The CLI module
accepts injectable clock, sleeper, and worker-launch functions so tests can
verify behavior without real delays or real detached processes.

Detached worker stdout and stderr are redirected to a log file beside the JSON
state file with a `.log` suffix. The hidden `worker <alarm-id>` command reloads
the persisted alarm record and tolerates missing, disabled, or already handled
records.

Audio playback uses standard-library process APIs and local system support:
`afplay` on macOS, `winsound` on Windows, or `paplay`, `aplay`, or `ffplay` on
Linux if available. Playback failures produce a warning after the alarm fires.

## Test plan

- Unit-test clock-time parsing and next-day rollover.
- Unit-test recurrence parsing and next-occurrence scheduling.
- Unit-test invalid inputs.
- Unit-test CLI dry-run output and alarm triggering with fake time/sleep.
- Unit-test recurring alarm rescheduling in the state store.
- Unit-test audio-file validation and injected playback behavior.
- Unit-test alarm table listing and disabled status after an alarm completes.
- Unit-test turning alarms on and off while keeping saved rows visible.
- Unit-test non-blocking `add`, worker PID persistence, foreground
  compatibility, and worker command dispatch.
- Unit-test TUI helper behavior and `tui` command dispatch without launching a
  real terminal UI.
- Run a smoke check through `alarm.py --dry-run`.
