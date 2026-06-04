# ADR 0004: OS-Agnostic Background Alarm Workers

## Issue

The CLI currently schedules an alarm by keeping the `add` command running until
the alarm fires. If the user exits the terminal process, the alarm does not
ring. This behavior is surprising for a saved time-of-day alarm because users
expect `python3 alarm.py add 17:15` to return control to the shell while the
alarm remains active.

The implementation needs a way to make alarms ring after the command exits
without depending on one operating system's scheduler, such as macOS `launchd`,
Linux `systemd`, cron, or Windows Task Scheduler.

## Decision

Use an OS-agnostic detached Python worker process for each enabled alarm.

The user-facing `add` command should:

- validate and persist the alarm record
- start a detached worker process using the same Python interpreter
- record the worker PID in the JSON state file
- print the scheduled alarm details and return immediately

The detached worker should run a hidden internal command that reuses the
existing wait, ring, recurrence, and state-update logic. It should not require a
terminal to remain open. The worker should redirect its standard output and
standard error to a log file so the parent command can exit without inheriting
terminal streams.

Proposed CLI shape:

```bash
python3 alarm.py add 17:15
python3 alarm.py list
python3 alarm.py off <id>
```

Normal `add` should return immediately. A debug or compatibility option can keep
the old foreground behavior:

```bash
python3 alarm.py add 17:15 --foreground
```

The internal worker command should not be documented as a user-facing feature,
but it should remain testable:

```bash
python3 alarm.py worker <alarm-id>
```

## Status

Proposed.

## Group

Scheduling.

## Assumptions

- The application remains terminal-only.
- The application continues to use the local JSON state file.
- The implementation should work on macOS, Linux, and Windows without requiring
  platform scheduler configuration.
- A detached Python process is acceptable as the scheduling mechanism.
- The machine must remain running for the alarm to fire. This decision does not
  require waking a suspended machine or surviving reboot.
- Multiple enabled alarms may mean multiple worker processes.
- Audio playback support remains platform-specific through the existing local
  audio player selection.

## Constraints

- The implementation must not require `launchd`, `systemd`, cron, Windows Task
  Scheduler, or a third-party daemon package.
- The worker must use the same persisted alarm record so `list`, `off`, TUI
  actions, and recurrence behavior stay coherent.
- The state file must record the worker PID after the worker is launched so
  `off` can terminate pending or ringing alarms.
- The worker command must tolerate stale, disabled, missing, or already handled
  alarm records.
- The parent `add` command must not wait for the scheduled alarm time.
- Standard output and standard error from detached workers must not keep the
  launching terminal attached.
- Existing tests should still be able to exercise alarm firing without waiting
  in real time by injecting clock and sleep functions.

## Positions

1. Start one detached Python worker process per enabled alarm.

   The CLI persists the alarm, launches a child Python process for that alarm,
   stores the child PID, and returns. The worker waits until the alarm fires and
   then updates the same record.

2. Add a single project-owned scheduler daemon.

   The CLI would only edit the state file, while one daemon process watches all
   enabled alarms and fires them at the right time.

3. Use native OS schedulers behind a common adapter.

   The app would create `launchd`, `systemd`/cron, or Windows Task Scheduler
   jobs depending on the host platform.

4. Keep the current foreground process model and document shell workarounds.

   Users could run commands with `nohup`, `tmux`, `screen`, or shell background
   jobs.

## Argument

Position 1 best satisfies the OS-agnostic requirement while staying close to the
current architecture. The application already has a tested wait-and-ring path,
a JSON-backed state store, PID-based cancellation, and recurrence rescheduling.
A detached worker keeps those pieces useful while changing the user-facing
behavior of `add` from "wait in the foreground" to "schedule and return."

Compared with native OS schedulers, detached Python workers avoid a large amount
of platform-specific code and configuration. Native schedulers are better at
surviving logout, reboot, and machine sleep, but they are not OS-agnostic in
implementation. They would also require separate test and support paths for
macOS, Linux, and Windows.

Cron is a good example of this tradeoff. It is a solid fit for recurring
Unix-style schedules, but it is awkward for one-off alarms, is not Windows-native,
and would require the application to edit external scheduler state. Cancellation
would also need to coordinate both crontab entries and any already-running alarm
process. Detached workers keep one-off and recurring alarm behavior inside the
application's existing JSON state and PID-based cancellation model.

Compared with a daemon, one worker per alarm is simpler to introduce. A daemon
is cleaner for many concurrent alarms because it centralizes scheduling in one
process, but it creates a second lifecycle problem: the app must install, start,
monitor, and recover that daemon. For this project, the user requirement is to
avoid keeping the original terminal command running, not to introduce a full
service manager.

The main tradeoff is that workers are still normal processes. If the machine
reboots, the alarm will not fire unless a later feature restores enabled alarms
on startup. If the machine sleeps through the scheduled time, firing behavior
depends on when the worker resumes and how stale alarms are handled. These
limits should be documented clearly and can be revisited with a native scheduler
or daemon decision later.

## Implications

- `add` should become non-blocking by default.
- A hidden worker command should load the alarm record by ID, reconstruct the
  `AlarmSpec`, and call the existing alarm runner.
- The CLI should offer `--foreground` to preserve manual foreground behavior and
  simplify troubleshooting.
- The store needs a way to update an alarm PID after the detached worker starts.
- Cancellation should continue to use the stored PID.
- Logs for detached workers should be written to a predictable local path.
- The TUI should launch alarms through the same detached-worker path or continue
  using compatible command construction.
- One-time alarms should still disable themselves after ringing.
- Recurring alarms should keep one stable alarm ID and reschedule through the
  same worker behavior.
- Tests should cover non-blocking `add`, worker command dispatch, PID
  persistence, foreground compatibility, and cancellation of detached workers.

## Related decisions

- ADR 0001: Recurring Alarms.
- ADR 0002: Visible TUI Alarm Actions.
- ADR 0003: Time-of-Day Alarms.
- The existing decision to keep the application terminal-only.
- The existing decision to use a JSON-backed state store instead of a database.

## Related requirements

- Users can create reusable alarms at local clock times.
- Users can list alarms with their ID, time, status, repeat mode, and label.
- Users can turn saved alarms on or off.
- New requirement: adding an alarm should not require the original terminal
  process to stay open.
- New requirement: the implementation should be OS-agnostic.

## Related artifacts

- `SPEC.md`
- `README.md`
- `src/alarm_clock/cli.py`
- `src/alarm_clock/store.py`
- `src/alarm_clock/tui.py`
- `tests/test_cli.py`
- `tests/test_store.py`
- `tests/test_tui.py`

## Related principles

- Keep the application terminal-only.
- Prefer standard-library implementation for the CLI path.
- Use the JSON state file as the shared contract between processes.
- Preserve backward compatibility for existing user state where practical.
- Keep behavior testable without real-time waiting.
- Avoid platform-specific scheduling mechanisms unless a later decision accepts
  that tradeoff explicitly.

## Notes

- Open review question: should worker logs live beside the state file, under a
  cache directory, or under a configurable path?
- Open review question: should stale enabled alarms be restarted automatically
  by `list`, `on`, or a future recovery command?
- Open review question: should recurring alarms run forever in one worker, or
  should each occurrence spawn a fresh worker after rescheduling?
