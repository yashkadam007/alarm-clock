# ADR 0003: Time-of-Day Alarms

## Issue

The CLI and TUI currently model an alarm as something scheduled for a specific
date and time. This makes each alarm feel like a one-off appointment, even when
the user intent is usually "wake me at 07:30" or "remind me at 18:00" as a
reusable alarm.

The application also supports scheduling an alarm after a relative duration.
That behavior overlaps with timer semantics. In common alarm-clock products,
including iOS, alarms are set for a clock time and can be turned on or off,
while duration-based countdowns are timers.

Users need alarms to be represented as reusable time-of-day entries that can be
enabled or disabled, and duration-based scheduling should be removed from the
alarm feature.

## Decision

Model alarms as time-of-day entries instead of date-bound scheduled events.

Each alarm should store a local clock time, enabled state, label, and optional
recurrence metadata. The scheduler should compute the next occurrence from the
stored time and recurrence settings at runtime. Users should be able to turn an
alarm on or off without deleting it.

The CLI and TUI should both use the same mental model:

- create an alarm for a clock time
- list saved alarms with their enabled or disabled state
- turn an alarm on
- turn an alarm off
- edit or remove an alarm through existing or future management actions

Duration-based alarm creation should be removed from the alarm surface. A
relative duration such as "after 10 minutes" is a timer and should not be
represented as an alarm. A separate timer feature can be considered later, but
it is outside this decision.

Proposed CLI shape:

```bash
python3 alarm.py add 07:30 --label "Wake up"
python3 alarm.py on <id>
python3 alarm.py off <id>
python3 alarm.py list
```

The TUI should show alarms as saved rows with a visible enabled control,
similar to iOS alarm toggles. Disabled alarms remain visible but do not schedule
or ring until re-enabled.

## Status

Approved.

## Group

Scheduling.

## Assumptions

- The application remains terminal-only.
- The application continues to use the local JSON state file.
- Alarm scheduling remains based on local system time.
- Existing recurrence behavior can be adapted to time-of-day alarms.
- Users expect alarms to be reusable entries rather than disposable dated
  events.
- Timer behavior is useful but should be designed as a separate concept if it
  is added later.

## Constraints

- The JSON state schema must remain backward compatible enough to read existing
  alarm records or migrate them predictably.
- Existing date-bound alarms need a migration path to time-of-day alarms.
- Disabled alarms must not ring, reschedule themselves, or appear as pending
  active work.
- Enabling an alarm must compute its next occurrence from the stored clock time
  and recurrence metadata.
- Duration-based alarm commands and TUI controls must be removed from alarm
  creation.
- The CLI and TUI must share the same alarm model and store semantics.
- Existing cancellation behavior should be reconciled with enable/disable
  behavior so users have one clear way to turn alarms off.

## Positions

1. Store alarms as reusable time-of-day entries with an enabled state.

   The alarm record owns the user-facing intent: time, label, recurrence, and
   whether it is active. The next concrete occurrence is derived from that
   intent when the alarm is enabled or rescheduled.

2. Keep date-bound alarms and add a separate enabled flag.

   This preserves the current storage shape, but it keeps the wrong conceptual
   model. Turning a dated alarm back on after its scheduled date would be
   ambiguous because the stored date may already be stale.

3. Keep both alarm-at-time and alarm-after-duration in the alarm feature.

   This is compatible with current behavior, but it continues to mix alarms and
   timers. The UI and CLI would need to explain two different scheduling
   concepts under one feature.

4. Add a separate timer feature now and migrate duration-based alarm creation
   into it immediately.

   This gives duration scheduling a correct home, but it expands the scope from
   changing alarms into designing and implementing a second product surface.

## Argument

Position 1 best matches user expectations and the product model used by common
alarm clocks. An alarm is a saved clock-time setting that can be toggled on or
off. The exact next date is implementation detail, not the identity of the
alarm.

This model also makes recurrence easier to reason about. A weekday alarm at
07:30 remains "07:30 on selected weekdays" rather than a dated alarm that must
continually rewrite its identity. The scheduler can still persist the next
computed occurrence if that is useful for process coordination, but the stored
alarm should preserve the user's intent separately from any derived runtime
state.

Removing duration-based alarm creation reduces ambiguity. A countdown is a
timer, and keeping it under alarms makes both CLI commands and TUI controls
harder to explain. Deferring timers keeps this change focused on correcting the
alarm model without committing to timer lifecycle, display, or notification
semantics.

The main tradeoff is migration complexity. Existing records may contain a
specific date and time or may have been created from a relative duration. The
implementation should either convert future dated alarms to their local
time-of-day or preserve enough compatibility to avoid breaking existing state.
Duration-created records should not define the future alarm model.

## Implications

- `AlarmSpec` and `StoredAlarm` need fields for clock time and enabled state.
- The store may keep a derived `scheduled_for` or `next_occurrence` field, but
  it should not be the primary user-facing alarm identity.
- CLI commands need to move away from `at` and `in` as the alarm creation model.
- Duration-based CLI commands and TUI inputs should be removed from alarms.
- Existing `off` behavior should disable saved alarms rather than only cancel a
  pending dated occurrence.
- An `on` action should enable a saved alarm and compute its next occurrence.
- The TUI alarm list should show disabled alarms and provide a toggle-style
  enable control.
- Recurring alarms should remain saved and enabled until the user turns them
  off.
- One-time alarms can still be represented as enabled time-of-day alarms that
  disable themselves after ringing.
- Tests need to cover creating time-of-day alarms, enabling and disabling
  alarms, listing disabled alarms, migration or compatibility for existing
  date-bound records, and removal of duration-based alarm creation.

## Related decisions

- ADR 0001: Recurring Alarms.
- ADR 0002: Visible TUI Alarm Actions.
- The existing decision to keep the application terminal-only.
- The existing decision to use a JSON-backed state store instead of a database.
- The existing decision to avoid a background daemon.

## Related requirements

- Users can schedule alarms at clock times.
- Users can list alarms with ID, time, status, and label.
- Users can turn alarms on or off.
- Users can open a TUI to view and add alarms.
- New requirement: alarms are saved time-of-day entries rather than
  date-specific events.
- New requirement: duration-based scheduling is not part of the alarm feature.

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
- Use the JSON state file as the shared contract between processes.
- Preserve backward compatibility for existing user state where practical.
- Keep behavior testable without real-time waiting.
- Keep alarms and timers as separate product concepts.
- Prefer user-facing alarm intent over derived scheduler state.

## Notes

- Open review question: should the CLI keep `at HH:MM` as an alias for
  compatibility, or should alarm creation move fully to `add HH:MM`?
- Open review question: should migrated date-bound one-time alarms disable
  themselves after the next ring, or become reusable disabled alarms after
  ringing?
- Open review question: should duration-created existing records be migrated,
  left to expire, or explicitly marked as legacy timer-like records?
