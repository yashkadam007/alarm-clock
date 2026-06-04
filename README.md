# Alarm Clock CLI

A terminal-only Python alarm clock built for the assignment. It has a CLI and a
Textual-powered TUI: no web UI, no React, and no database.

## What It Does

- Create reusable alarms at local clock times.
- Keep alarms active in detached background worker processes after `add` returns.
- Schedule recurring clock-time alarms daily or on selected weekdays.
- Turn saved alarms on or off without deleting them.
- Print a custom alarm label.
- Ring the terminal bell unless disabled.
- Play `assets/audio/alarm.mp3` when an alarm fires.
- List alarms with their ID, time, status, and label.
- Turn off enabled alarms.
- Open a terminal UI for viewing and adding alarms.
- Validate schedules with `--dry-run` without waiting.

See [SPEC.md](SPEC.md) for the requirements, design notes, and test plan.

## Usage

Install the TUI dependency and the `alarm` command in a local virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Add an alarm at a clock time:

```bash
python3 alarm.py add 07:30 --label "Wake up"
```

`add` saves the alarm, starts a detached Python worker, records that worker PID,
and returns control to the shell immediately. The machine must remain running
for the alarm to fire; alarms are not restored automatically after reboot.

Wait in the current terminal for troubleshooting:

```bash
python3 alarm.py add 07:30 --label "Wake up" --foreground
```

Run a daily recurring alarm at a clock time:

```bash
python3 alarm.py add 07:30 --label "Wake up" --repeat daily
```

Run a recurring alarm on selected weekdays:

```bash
python3 alarm.py add 09:00 --label "Standup" --repeat days --days mon,tue,wed,thu,fri
```

Preview the schedule without waiting:

```bash
python3 alarm.py add 18:00 --label "Stand up" --dry-run
```

Disable the terminal bell:

```bash
python3 alarm.py add 18:00 --label "Quiet reminder" --no-bell
```

Override the default audio file:

```bash
python3 alarm.py add 07:30 --label "Wake up" --audio-file ~/Music/alarm.wav
```

List alarms:

```bash
python3 alarm.py list
```

Turn on a saved alarm:

```bash
python3 alarm.py on a1b2c3
```

Turn off one enabled alarm:

```bash
python3 alarm.py off a1b2c3
```

Turn off all enabled alarms:

```bash
python3 alarm.py off --all
```

Open the TUI:

```bash
python3 alarm.py tui
```

Or, after installing the package:

```bash
alarm tui
```

The TUI supports:

- `a`: add an alarm.
- `o`: turn off enabled alarms.
- `r`: refresh the alarm list.
- `q`: quit.

`list` prints a table of saved alarms:

```text
ID        Time              Status     Repeat       Label
a1b2c3    2026-06-05 07:30  on         daily        Wake up
d4e5f6    2026-06-04 18:10  off        none         Tea break
```

Turned-off alarms remain visible and can be enabled again with `on`.

## Accepted Formats

Clock times:

- `07:30`
- `23:59:58`

If an `add` time has already passed today, the alarm is scheduled for tomorrow.
Selected days accept short or full day names, such as `mon,wednesday,friday`.

Recurring alarms keep one alarm ID and reschedule the same state record after
each trigger. One-time alarms disable themselves after ringing.

## Audio Playback

Alarms play `assets/audio/alarm.mp3` by default. Use `--audio-file` to override
it for a specific alarm. Audio files are validated before the worker starts.

Playback uses local system support: `afplay` on macOS, `winsound` on Windows,
or `paplay`, `aplay`, or `ffplay` on Linux if available. If playback fails, the
alarm still prints its label and reports a warning.

Detached worker output is written beside the state file with a `.log` suffix.

## Tests

```bash
python3 -m unittest discover -s tests
```
