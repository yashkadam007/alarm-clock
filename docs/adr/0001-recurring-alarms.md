# ADR 0001: Recurring Alarms

## Issue

The alarm clock currently supports one-time alarms scheduled by relative duration
or by the next occurrence of a clock time. Users now need recurring alarms, with
options for daily recurrence and selected weekdays. This needs an architecture
decision before implementation because recurrence changes the alarm lifecycle:
after an alarm fires, the system must decide whether to mark it triggered,
reschedule it, or remove it.

## Decision

Add first-class recurrence metadata to scheduled alarms and support recurring
clock-time alarms through the existing CLI, TUI, and JSON state store.

The proposed recurrence modes are:

- `none`: current one-time alarm behavior.
- `daily`: alarm repeats every day at the configured clock time.
- `weekdays`: alarm repeats only on selected weekdays.

The CLI should expose recurrence only for `at` alarms because recurring relative
durations such as "every 10 minutes" introduce different timer semantics and are
outside this requested scope.

Proposed CLI shape:

```bash
python3 alarm.py at 07:30 --label "Wake up" --repeat daily
python3 alarm.py at 09:00 --label "Standup" --repeat days --days mon,tue,wed,thu,fri
```

The TUI should add repeat controls when creating an `at` alarm:

- repeat mode: none, daily, selected days
- day selection: Monday through Sunday checkboxes when selected days is active

When a recurring alarm fires, the running alarm process should update its
persisted record to the next scheduled occurrence and continue waiting. The
alarm remains `pending` instead of becoming `triggered`. One-time alarms keep
the existing lifecycle.

## Status

Implemented.

## Group

Calendar.

## Assumptions

- The application remains terminal-only.
- The application continues to use the local JSON state file and does not add a
  database or background daemon.
- A recurring alarm is represented by one long-running process, matching the
  current model where scheduled alarms are active terminal processes.
- Recurrence is based on local system time.
- Users only need daily and weekday-selection recurrence in this change.
- Existing one-time alarm commands and persisted alarm records must continue to
  work.

## Constraints

- Recurring alarms require `at` clock-time scheduling; `in` duration alarms stay
  one-time only.
- The JSON state schema must remain backward compatible with existing records
  that do not include recurrence fields.
- The alarm process must persist the next occurrence after each trigger so
  `list`, `off`, and the TUI continue to show the upcoming alarm.
- `off <id>` and `off --all` must cancel recurring pending alarms the same way
  they cancel one-time pending alarms.
- Day names must be validated and normalized to a stable internal
  representation.

## Positions

1. Store each recurrence as one persistent pending alarm record with recurrence
   metadata.

   The alarm process rings, computes the next valid occurrence, updates the same
   record, and waits again. This keeps one alarm ID stable across occurrences.

2. Expand recurring alarms into multiple one-time alarm records.

   The scheduler would create future one-time alarms for each selected day. This
   makes the store simple but creates duplicate state and raises questions about
   how far into the future to generate occurrences.

3. Add a background scheduler daemon that owns recurrence.

   The CLI and TUI would submit recurrence rules to the daemon, and the daemon
   would wake alarms at the right time. This is a cleaner scheduling model but
   conflicts with the current no-daemon design.

4. Encode recurrence only in command-line arguments and avoid persisting it.

   The running process could keep recurrence in memory. This is simpler at
   first, but `list`, `off`, and future UI behavior would lack enough persisted
   information to explain and manage recurring alarms.

## Argument

Position 1 is the best fit for the current architecture. The app already stores
pending alarm records with a stable ID, scheduled time, label, source, status,
and PID. Adding recurrence metadata to that record preserves the current process
model and avoids introducing a scheduler daemon or a database.

This option also gives the user a simple management model: one recurring alarm
has one ID, appears once in `list`, and can be turned off with the existing
`off` command. It has lower implementation cost than a daemon and lower state
complexity than pre-generating many one-time alarms.

The tradeoff is that recurring alarms still depend on a running process. If the
process exits or the machine restarts, the pending alarm becomes stale under the
current cleanup rules. That tradeoff is consistent with the existing alarm
clock constraints and should be documented rather than solved in this change.

## Implications

- `AlarmSpec` needs recurrence fields.
- The parser needs validation for recurrence mode and selected weekdays.
- The JSON store needs backward-compatible recurrence fields.
- `StoredAlarm` and list formatting should expose recurrence clearly enough for
  users to distinguish one-time and recurring alarms.
- `run_alarm` needs to loop differently for recurring alarms: ring, compute the
  next occurrence, update state, then continue waiting.
- The existing `mark_alarm_triggered` flow should apply only to one-time alarms.
- The TUI add-alarm form needs repeat mode and day-selection controls.
- Tests need to cover daily recurrence, selected-day recurrence, backward
  compatibility with existing state, and cancellation of recurring alarms.

## Related decisions

- The existing decision to keep the application terminal-only.
- The existing decision to use a JSON-backed state store instead of a database.
- The existing decision to avoid a background daemon.
- The existing cancellation behavior added for upcoming alarms.

## Related requirements

- Users can schedule alarms at clock times.
- Users can list alarms with ID, scheduled time, status, and label.
- Users can turn off upcoming alarms.
- Users can open a TUI to view and add alarms.
- New requirement: users can create recurring alarms that repeat daily or on
  selected days.

## Related artifacts

- `SPEC.md`
- `README.md`
- `src/alarm_clock/core.py`
- `src/alarm_clock/cli.py`
- `src/alarm_clock/store.py`
- `src/alarm_clock/tui.py`
- `tests/test_core.py`
- `tests/test_cli.py`
- `tests/test_store.py`
- `tests/test_tui.py`

## Related principles

- Keep the application terminal-only.
- Prefer simple standard-library implementation for the CLI path.
- Preserve backward compatibility for existing user state where practical.
- Keep behavior testable without real-time waiting.

## Notes

- Open review question: should selected days accept both short names
  (`mon,tue`) and full names (`monday,tuesday`), or only short names?
- Open review question: should `list` include a recurrence column, or should
  recurrence be appended to the label/source text to preserve the current table
  width?
- Open review question: should recurring alarms remain active indefinitely until
  turned off, or should a future end date/count be considered later as a
  separate feature?
