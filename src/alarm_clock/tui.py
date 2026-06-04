"""Textual-based terminal UI for the alarm clock."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from .cli import (
    DEFAULT_AUDIO_FILE_NAME,
    format_alarm_status,
    format_list_datetime,
    format_repeat,
)
from .core import REPEAT_NONE, REPEAT_WEEKDAYS, WEEKDAY_NAMES, parse_repeat_mode
from .store import (
    STATE_ENV_VAR,
    SNOOZE_MINUTES,
    StoredAlarm,
    default_state_path,
    disable_alarm,
    disable_enabled_alarms,
    list_alarms,
    snooze_ringing_alarm,
)


def build_alarm_command(
    *,
    mode: str,
    value: str,
    label: str,
    audio_file: Path | None = None,
    repeat: str = REPEAT_NONE,
    days: tuple[str, ...] = (),
    alarm_id: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(_repo_root() / "alarm.py"),
        mode,
        value,
        "--label",
        label,
    ]
    if audio_file is not None:
        command.extend(["--audio-file", str(audio_file)])
    if alarm_id is not None:
        command.extend(["--alarm-id", alarm_id])
    normalized_repeat = parse_repeat_mode(repeat)
    if mode == "add" and normalized_repeat != REPEAT_NONE:
        cli_repeat = "days" if normalized_repeat == REPEAT_WEEKDAYS else repeat
        command.extend(["--repeat", cli_repeat])
        if normalized_repeat == REPEAT_WEEKDAYS:
            command.extend(["--days", ",".join(days)])
    return command


def launch_alarm(
    *,
    mode: str,
    value: str,
    label: str,
    audio_file: Path | None = None,
    repeat: str = REPEAT_NONE,
    days: tuple[str, ...] = (),
    state_path: Path | None = None,
    alarm_id: str | None = None,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    if state_path is not None:
        env[STATE_ENV_VAR] = str(state_path)

    return subprocess.Popen(
        build_alarm_command(
            mode=mode,
            value=value,
            label=label,
            audio_file=audio_file,
            repeat=repeat,
            days=days,
            alarm_id=alarm_id,
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


def alarm_table_rows(alarms: list[StoredAlarm]) -> list[tuple[str, str, str, str, str]]:
    return [
        (
            alarm.alarm_id,
            format_list_datetime(alarm.scheduled_for),
            format_alarm_status(alarm.status, alarm.enabled),
            format_repeat(alarm.repeat, alarm.repeat_days),
            alarm.label,
        )
        for alarm in alarms
    ]


def active_ringing_alarm(alarms: list[StoredAlarm]) -> StoredAlarm | None:
    ringing = [alarm for alarm in alarms if alarm.status == "ringing"]
    if not ringing:
        return None
    return min(ringing, key=lambda alarm: alarm.scheduled_for)


def run_tui(*, state_path: Path | None = None) -> int:
    try:
        from textual import on
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import (
            Button,
            Checkbox,
            DataTable,
            Footer,
            Header,
            Input,
            Label,
            Select,
            Static,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Textual is required for the TUI. Install it with "
            "`python3 -m pip install textual`."
        ) from exc

    selected_state_path = state_path or default_state_path()

    class AddAlarmScreen(ModalScreen[dict[str, str] | None]):
        BINDINGS = [("escape", "cancel", "Cancel")]

        DEFAULT_CSS = """
        AddAlarmScreen {
            align: center middle;
        }

        #add-dialog {
            width: 72;
            height: auto;
            padding: 1 2;
            border: thick $primary;
            background: $surface;
        }

        #add-dialog Input,
        #add-dialog Select {
            margin-bottom: 1;
        }

        #repeat-days {
            height: auto;
            margin-bottom: 1;
        }

        #add-actions {
            height: auto;
            align-horizontal: right;
        }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="add-dialog"):
                yield Label("Add alarm")
                yield Input(placeholder="07:30", id="alarm-value")
                yield Input(placeholder="Label", id="alarm-label")
                yield Select(
                    [
                        ("No repeat", "none"),
                        ("Daily", "daily"),
                        ("Selected days", "weekdays"),
                    ],
                    id="alarm-repeat",
                    value="none",
                )
                with Vertical(id="repeat-days"):
                    yield Checkbox("Monday", id="repeat-mon")
                    yield Checkbox("Tuesday", id="repeat-tue")
                    yield Checkbox("Wednesday", id="repeat-wed")
                    yield Checkbox("Thursday", id="repeat-thu")
                    yield Checkbox("Friday", id="repeat-fri")
                    yield Checkbox("Saturday", id="repeat-sat")
                    yield Checkbox("Sunday", id="repeat-sun")
                yield Input(
                    placeholder=f"Audio file override, default {DEFAULT_AUDIO_FILE_NAME}",
                    id="alarm-audio",
                )
                with Horizontal(id="add-actions"):
                    yield Button("Cancel", id="add-cancel")
                    yield Button("Add", id="add-save", variant="primary")

        @on(Button.Pressed, "#add-cancel")
        def cancel(self) -> None:
            self.action_cancel()

        def action_cancel(self) -> None:
            self.dismiss(None)

        @on(Button.Pressed, "#add-save")
        def save(self) -> None:
            value = self.query_one("#alarm-value", Input).value.strip()
            label = self.query_one("#alarm-label", Input).value.strip() or "Alarm"
            repeat = self.query_one("#alarm-repeat", Select).value
            selected_days = tuple(
                day
                for day in WEEKDAY_NAMES
                if self.query_one(f"#repeat-{day}", Checkbox).value
            )
            audio_file = self.query_one("#alarm-audio", Input).value.strip()

            if not value:
                self.app.notify("Enter a clock time", severity="error")
                return
            if repeat == "weekdays" and not selected_days:
                self.app.notify("Select at least one repeat day", severity="error")
                return

            self.dismiss(
                {
                    "mode": "add",
                    "value": value,
                    "label": label,
                    "repeat": str(repeat),
                    "days": ",".join(selected_days),
                    "audio_file": audio_file,
                }
            )

    class AlarmTuiApp(App[None]):
        TITLE = "Alarm Clock"

        CSS = """
        Screen {
            layout: vertical;
        }

        #summary {
            height: 3;
            padding: 0 1;
            content-align: left middle;
        }

        #active-alarm {
            height: auto;
            min-height: 4;
            padding: 0 1;
            border: heavy $error;
            content-align: left middle;
        }

        #active-actions {
            height: 3;
            padding: 0 1;
            align-horizontal: right;
        }

        #alarms {
            height: 1fr;
        }

        #actions {
            height: 3;
            padding: 0 1;
            align-horizontal: right;
        }
        """

        BINDINGS = [
            ("a", "add_alarm", "Add"),
            ("o", "turn_off", "Off"),
            ("enter", "turn_off_active", "Turn Off Active"),
            ("s", "snooze_alarm", "Snooze"),
            ("r", "refresh", "Refresh"),
            ("q", "quit", "Quit"),
        ]

        active_alarm_id: str | None = None

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(id="summary")
            yield Static(id="active-alarm")
            with Horizontal(id="active-actions"):
                yield Button("Turn Off", id="active-off", variant="error", disabled=True)
                yield Button(
                    f"Snooze {SNOOZE_MINUTES}m",
                    id="active-snooze",
                    variant="warning",
                    disabled=True,
                )
            yield DataTable(id="alarms")
            with Horizontal(id="actions"):
                yield Button("Refresh", id="refresh")
                yield Button("Turn Off", id="turn-off")
                yield Button("Add", id="add", variant="primary")
                yield Button("Quit", id="quit")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#alarms", DataTable)
            table.add_columns("ID", "Time", "Status", "Repeat", "Label")
            self.refresh_table()
            self.set_interval(1, self.refresh_table)

        def refresh_table(self) -> None:
            alarms = list_alarms(now=datetime.now(), state_path=selected_state_path)
            table = self.query_one("#alarms", DataTable)
            table.clear()
            for row in alarm_table_rows(alarms):
                table.add_row(*row, key=row[0])

            active_alarm = active_ringing_alarm(alarms)
            self.active_alarm_id = active_alarm.alarm_id if active_alarm else None
            self._refresh_active_alarm(active_alarm)

            summary = self.query_one("#summary", Static)
            pending_count = sum(1 for alarm in alarms if alarm.status == "pending")
            ringing_count = sum(1 for alarm in alarms if alarm.status == "ringing")
            triggered_count = sum(1 for alarm in alarms if alarm.status == "triggered")
            summary.update(
                f"{pending_count} pending, {ringing_count} ringing, "
                f"{triggered_count} triggered | "
                f"state: {selected_state_path}"
            )

        def _refresh_active_alarm(self, alarm: StoredAlarm | None) -> None:
            active = self.query_one("#active-alarm", Static)
            off_button = self.query_one("#active-off", Button)
            snooze_button = self.query_one("#active-snooze", Button)
            off_button.disabled = alarm is None
            snooze_button.disabled = alarm is None
            if alarm is None:
                active.update("No alarm ringing")
                return

            active.update(
                "ALARM RINGING\n"
                f"{alarm.label} | {format_list_datetime(alarm.scheduled_for)} | "
                f"repeat {format_repeat(alarm.repeat, alarm.repeat_days)}"
            )

        def action_refresh(self) -> None:
            self.refresh_table()

        def action_turn_off(self) -> None:
            if self.active_alarm_id is not None:
                self.action_turn_off_active()
                return
            self.action_turn_off_upcoming()

        def action_turn_off_active(self) -> None:
            if self.active_alarm_id is None:
                self.notify("No active alarm to turn off")
                return

            now = datetime.now()
            try:
                stopped = disable_alarm(
                    self.active_alarm_id,
                    now=now,
                    state_path=selected_state_path,
                )
            except PermissionError as exc:
                self.notify(f"Could not stop alarm process: {exc}", severity="error")
                return

            if stopped is None:
                self.notify("No active alarm to turn off")
                self.refresh_table()
                return

            self.notify(f"Turned off active alarm: {stopped.label}")
            self.refresh_table()

        def action_snooze_alarm(self) -> None:
            if self.active_alarm_id is None:
                self.notify("No active alarm to snooze")
                return

            now = datetime.now()
            try:
                snoozed = snooze_ringing_alarm(
                    self.active_alarm_id,
                    now=now,
                    state_path=selected_state_path,
                )
            except PermissionError as exc:
                self.notify(f"Could not stop alarm process: {exc}", severity="error")
                return

            if snoozed is None:
                self.notify("No active alarm to snooze")
                self.refresh_table()
                return

            self._launch_waiting_alarm(
                replace(
                    snoozed,
                    scheduled_for=now + timedelta(minutes=SNOOZE_MINUTES),
                    status="pending",
                ),
                use_scheduled_time=True,
            )
            self.notify(f"Snoozed {snoozed.label} for {SNOOZE_MINUTES} minutes")
            self.refresh_table()

        def action_turn_off_upcoming(self) -> None:
            try:
                canceled = disable_enabled_alarms(
                    now=datetime.now(),
                    state_path=selected_state_path,
                )
            except PermissionError as exc:
                self.notify(f"Could not stop alarm process: {exc}", severity="error")
                return

            if not canceled:
                self.notify("No enabled alarms to turn off")
                return

            count = len(canceled)
            noun = "alarm" if count == 1 else "alarms"
            self.notify(f"Turned off {count} {noun}")
            self.refresh_table()

        def _launch_waiting_alarm(
            self,
            alarm: StoredAlarm,
            *,
            use_scheduled_time: bool = False,
        ) -> None:
            mode = "add"
            if use_scheduled_time:
                value = alarm.scheduled_for.time().strftime("%H:%M:%S")
                repeat = REPEAT_NONE
                days: tuple[str, ...] = ()
            else:
                value = (alarm.clock_time or alarm.scheduled_for.time()).strftime(
                    "%H:%M:%S"
                )
                repeat = alarm.repeat
                days = alarm.repeat_days

            try:
                launch_alarm(
                    mode=mode,
                    value=value,
                    label=alarm.label,
                    repeat=repeat,
                    days=days,
                    state_path=selected_state_path,
                    alarm_id=alarm.alarm_id,
                )
            except OSError as exc:
                self.notify(f"Could not restart alarm: {exc}", severity="error")

        def action_add_alarm(self) -> None:
            self.push_screen(AddAlarmScreen(), self.add_alarm_from_form)

        def add_alarm_from_form(self, result: dict[str, str] | None) -> None:
            if result is None:
                return

            audio_text = result["audio_file"]
            audio_file = Path(audio_text).expanduser() if audio_text else None
            try:
                launch_alarm(
                    mode=result["mode"],
                    value=result["value"],
                    label=result["label"],
                    audio_file=audio_file,
                    repeat=result["repeat"],
                    days=tuple(day for day in result["days"].split(",") if day),
                    state_path=selected_state_path,
                )
            except OSError as exc:
                self.notify(f"Could not start alarm: {exc}", severity="error")
                return

            self.notify("Alarm scheduled")
            self.refresh_table()

        @on(Button.Pressed, "#refresh")
        def refresh_pressed(self) -> None:
            self.action_refresh()

        @on(Button.Pressed, "#add")
        def add_pressed(self) -> None:
            self.action_add_alarm()

        @on(Button.Pressed, "#turn-off")
        def turn_off_pressed(self) -> None:
            self.action_turn_off()

        @on(Button.Pressed, "#active-off")
        def active_off_pressed(self) -> None:
            self.action_turn_off_active()

        @on(Button.Pressed, "#active-snooze")
        def active_snooze_pressed(self) -> None:
            self.action_snooze_alarm()

        @on(Button.Pressed, "#quit")
        def quit_pressed(self) -> None:
            self.exit()

    AlarmTuiApp().run()
    return 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
