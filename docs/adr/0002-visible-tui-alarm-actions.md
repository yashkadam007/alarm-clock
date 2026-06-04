# ADR 0002: Visible TUI Alarm Actions

## Issue

When an alarm is launched from the TUI and then fires, the user does not get a
visible alarm state inside the TUI. The alarm subprocess prints `ALARM:` on its
own stdout, but the TUI currently starts that subprocess with stdout and stderr
discarded. The user can hear audio if playback works, but the TUI still looks
like a normal alarm list and does not provide an obvious way to respond to the
alarm that is currently going off.

Users need the TUI to make an active alarm visible and provide direct actions to
turn it off or snooze it.

## Decision

Add an explicit active-alarm state to the persisted alarm lifecycle and make the
TUI poll that state to show a prominent alarm screen or banner with actions.

The proposed alarm statuses are:

- `pending`: waiting for a future scheduled time.
- `ringing`: the alarm has fired and needs user action.
- `triggered`: a one-time alarm has completed or was stopped after ringing.

When an alarm fires, the alarm process should update its state record to
`ringing` before printing, ringing the bell, or starting audio playback. The TUI
should detect `ringing` alarms during its existing refresh loop and show an
active-alarm surface that includes:

- alarm label
- scheduled time
- repeat summary
- `Turn Off` action
- `Snooze` action

The default snooze duration should be 10 minutes. A later implementation can add
a setting or selectable snooze durations, but the first change should keep the
interaction small and predictable.

Proposed TUI bindings while an alarm is ringing:

- `enter` or `o`: turn off the active alarm.
- `s`: snooze the active alarm.
- `escape`: dismiss only non-blocking UI chrome if needed, but not silently
  dismiss the alarm.

Turning off a ringing one-time alarm should stop audio/playback if it is still
running, mark the alarm `triggered`, and remove the active-alarm prompt from the
TUI. Turning off a ringing recurring alarm should stop the current ring and
reschedule the same alarm record to its next recurrence, keeping the stable alarm
ID.

Snoozing should stop the current ring, update the same alarm record to
`pending`, set `scheduled_for` to now plus the snooze duration, and launch or
continue a waiting process for that snoozed occurrence. Snooze should not change
the alarm recurrence metadata. For recurring alarms, after the snoozed
occurrence fires and is turned off, the alarm should resume its normal recurrence
schedule.

## Status

Implemented.

## Group

Interaction.

## Assumptions

- The application remains terminal-only.
- The application continues to use the local JSON state file.
- The TUI can keep polling the state file once per second.
- Alarm processes remain the scheduling mechanism; this decision does not add a
  background daemon.
- There can be at most one active `ringing` prompt shown in the TUI at a time.
  If multiple alarms are found ringing, the TUI should present the earliest
  scheduled one first.
- Stopping audio may require terminating the alarm subprocess if playback is
  blocking.

## Constraints

- Existing records with only `pending` and `triggered` statuses must remain
  readable.
- Existing CLI list output must continue to work when `ringing` records are
  present.
- The TUI must not rely on child-process stdout to detect alarms because that
  output is intentionally not shown inside the Textual app.
- Stop and snooze must be idempotent enough to tolerate the TUI refresh loop and
  process exits racing each other.
- Snoozing must preserve the alarm ID so the user does not see duplicate alarm
  rows for one logical alarm.
- Turning off upcoming alarms should continue to affect only `pending` alarms,
  while the active-alarm prompt owns `ringing` alarm actions.

## Positions

1. Add a persisted `ringing` status and have the TUI render active alarm actions
   from store state.

   The alarm process marks its record `ringing` when it fires. The TUI polls the
   store, displays a modal or prominent banner, and calls store operations to
   stop or snooze the active alarm.

2. Pipe alarm subprocess stdout back into the TUI and show a notification when
   `ALARM:` appears.

   This directly fixes the hidden output problem, but it still couples behavior
   to text output and does not give the store enough state to support reliable
   stop and snooze actions.

3. Run alarms directly inside the TUI event loop instead of launching CLI
   subprocesses.

   This would make active alarm UI easier to coordinate, but it changes the
   current architecture more broadly and risks duplicating scheduling behavior
   already implemented in the CLI.

4. Treat fired alarms as normal triggered rows and add a general snooze command
   for triggered alarms.

   This avoids a new status, but a triggered row does not represent an ongoing
   alarm. It would make the user infer which alarm is active and would make stop
   semantics unclear after audio playback starts.

## Argument

Position 1 is the best fit for the current architecture. The application already
uses the JSON store as the shared contract between CLI, TUI, and subprocesses.
Adding a `ringing` status extends that contract in a way that is visible,
testable, and independent of terminal stdout behavior.

The key problem is not only that output is hidden. The TUI needs to know that an
alarm is currently actionable. A persisted `ringing` state gives both the alarm
process and the TUI a simple shared model: pending alarms can be cancelled,
ringing alarms can be stopped or snoozed, and triggered alarms are history.

The tradeoff is that the store lifecycle becomes slightly more complex. Stop and
snooze actions can race with the alarm process completing audio playback or
rescheduling a recurring alarm. That risk should be handled by idempotent store
functions and focused tests rather than by introducing a daemon or moving all
scheduling into the TUI.

## Implications

- `StoredAlarm.status` parsing needs to accept `ringing`.
- `run_alarm` needs to mark the alarm `ringing` before alarm output and audio
  playback.
- The state store needs operations for stopping and snoozing a ringing alarm.
- Snooze needs a deterministic default duration, initially 10 minutes.
- The TUI needs an active-alarm screen, modal, or full-width banner that is hard
  to miss.
- The TUI should keep the alarm list visible or quickly recoverable after the
  active alarm is handled.
- Audio playback may need to be controlled through a process that can be
  terminated when the user stops or snoozes.
- Existing `off` behavior should remain focused on upcoming `pending` alarms.
- Tests should cover `pending` to `ringing`, turning off ringing alarms,
  snoozing ringing alarms, recurring alarm behavior after stop/snooze, and TUI
  active-alarm row selection.

## Related decisions

- ADR 0001: Recurring Alarms.
- The existing decision to keep the application terminal-only.
- The existing decision to use a JSON-backed state store instead of a database.
- The existing decision to avoid a background daemon.

## Related requirements

- Users can open a TUI to view and add alarms.
- Users can turn off upcoming alarms.
- New requirement: users can see when an alarm is actively going off in the TUI.
- New requirement: users can turn off the active alarm from the TUI.
- New requirement: users can snooze the active alarm from the TUI.

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
- Use the JSON state file as the shared contract between processes.
- Preserve backward compatibility for existing user state where practical.
- Keep behavior testable without real-time waiting.
- Prefer explicit user-visible state over hidden subprocess output.

## Notes

- Open review question: should snooze be fixed at 10 minutes initially, or
  should the first implementation include selectable durations?
- Open review question: should turning off a ringing one-time alarm keep a
  `triggered` history row, or should it remove the alarm from the state file?
- Open review question: should the CLI also expose stop/snooze for ringing
  alarms, or should this decision stay TUI-only for the first implementation?
