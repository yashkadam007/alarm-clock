# Alarm Clock CLI

A terminal-only Python alarm clock built for the assignment. It has a CLI and a
Textual-powered TUI: no web UI, no React, and no database.

## What It Does

- Schedule an alarm after a duration.
- Schedule an alarm at the next occurrence of a clock time.
- Print a custom alarm label.
- Ring the terminal bell unless disabled.
- Play `assets/audio/alarm.mp3` when an alarm fires.
- List alarms with their ID, time, status, and label.
- Turn off upcoming alarms.
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

Run an alarm after a duration:

```bash
python3 alarm.py in 10m --label "Take a break"
```

Run an alarm at a clock time:

```bash
python3 alarm.py at 07:30 --label "Wake up"
```

Preview the schedule without waiting:

```bash
python3 alarm.py in 30s --label "Stand up" --dry-run
```

Disable the terminal bell:

```bash
python3 alarm.py in 5m --label "Quiet reminder" --no-bell
```

Override the default audio file:

```bash
python3 alarm.py in 10m --label "Wake up" --audio-file ~/Music/alarm.wav
```

List alarms:

```bash
python3 alarm.py list
```

Turn off one upcoming alarm:

```bash
python3 alarm.py off a1b2c3
```

Turn off all upcoming alarms:

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
- `o`: turn off upcoming alarms.
- `r`: refresh the alarm list.
- `q`: quit.

`list` prints a table of pending and triggered alarms:

```text
ID        Time              Status     Label
a1b2c3    2026-06-05 07:30  pending    Wake up
d4e5f6    2026-06-04 18:10  triggered  Tea break
```

Cancelled, expired, or stopped pending alarm processes are removed from the
list.

## Accepted Formats

Durations:

- `10s`
- `5m`
- `2h`
- `1h30m`
- `01:30` for 1 minute, 30 seconds
- `01:02:03` for 1 hour, 2 minutes, 3 seconds

Clock times:

- `07:30`
- `23:59:58`

If an `at` time has already passed today, the alarm is scheduled for tomorrow.

## Audio Playback

Alarms play `assets/audio/alarm.mp3` by default. Use `--audio-file` to override
it for a specific alarm. Audio files are validated before waiting.

Playback uses local system support: `afplay` on macOS, `winsound` on Windows,
or `paplay`, `aplay`, or `ffplay` on Linux if available. If playback fails, the
alarm still prints its label and reports a warning.

## Tests

```bash
python3 -m unittest discover -s tests
```
