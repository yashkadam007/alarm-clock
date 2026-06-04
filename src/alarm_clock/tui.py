"""Textual-based terminal UI for the alarm clock."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .cli import DEFAULT_AUDIO_FILE_NAME, format_list_datetime
from .store import (
    STATE_ENV_VAR,
    StoredAlarm,
    cancel_pending_alarms,
    default_state_path,
    list_alarms,
)


def build_alarm_command(
    *,
    mode: str,
    value: str,
    label: str,
    audio_file: Path | None = None,
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
    return command


def launch_alarm(
    *,
    mode: str,
    value: str,
    label: str,
    audio_file: Path | None = None,
    state_path: Path | None = None,
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
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


def alarm_table_rows(alarms: list[StoredAlarm]) -> list[tuple[str, str, str, str]]:
    return [
        (
            alarm.alarm_id,
            format_list_datetime(alarm.scheduled_for),
            alarm.status,
            alarm.label,
        )
        for alarm in alarms
    ]


def run_tui(*, state_path: Path | None = None) -> int:
    try:
        from textual import on
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static
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

        #add-actions {
            height: auto;
            align-horizontal: right;
        }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="add-dialog"):
                yield Label("Add alarm")
                yield Select(
                    [("After duration", "in"), ("At clock time", "at")],
                    id="alarm-mode",
                    value="in",
                )
                yield Input(placeholder="10m, 1h30m, 07:30", id="alarm-value")
                yield Input(placeholder="Label", id="alarm-label")
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
            mode = self.query_one("#alarm-mode", Select).value
            value = self.query_one("#alarm-value", Input).value.strip()
            label = self.query_one("#alarm-label", Input).value.strip() or "Alarm"
            audio_file = self.query_one("#alarm-audio", Input).value.strip()

            if not value:
                self.app.notify("Enter a duration or clock time", severity="error")
                return

            self.dismiss(
                {
                    "mode": str(mode),
                    "value": value,
                    "label": label,
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
            ("o", "turn_off_upcoming", "Off"),
            ("r", "refresh", "Refresh"),
            ("q", "quit", "Quit"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(id="summary")
            yield DataTable(id="alarms")
            with Horizontal(id="actions"):
                yield Button("Refresh", id="refresh")
                yield Button("Turn Off Upcoming", id="turn-off")
                yield Button("Add", id="add", variant="primary")
                yield Button("Quit", id="quit")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#alarms", DataTable)
            table.add_columns("ID", "Time", "Status", "Label")
            self.refresh_table()
            self.set_interval(1, self.refresh_table)

        def refresh_table(self) -> None:
            alarms = list_alarms(now=datetime.now(), state_path=selected_state_path)
            table = self.query_one("#alarms", DataTable)
            table.clear()
            for row in alarm_table_rows(alarms):
                table.add_row(*row, key=row[0])

            summary = self.query_one("#summary", Static)
            pending_count = sum(1 for alarm in alarms if alarm.status == "pending")
            triggered_count = sum(1 for alarm in alarms if alarm.status == "triggered")
            summary.update(
                f"{pending_count} pending, {triggered_count} triggered | "
                f"state: {selected_state_path}"
            )

        def action_refresh(self) -> None:
            self.refresh_table()

        def action_turn_off_upcoming(self) -> None:
            try:
                canceled = cancel_pending_alarms(
                    now=datetime.now(),
                    state_path=selected_state_path,
                )
            except PermissionError as exc:
                self.notify(f"Could not stop alarm process: {exc}", severity="error")
                return

            if not canceled:
                self.notify("No upcoming alarms to turn off")
                return

            count = len(canceled)
            noun = "alarm" if count == 1 else "alarms"
            self.notify(f"Turned off {count} upcoming {noun}")
            self.refresh_table()

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
            self.action_turn_off_upcoming()

        @on(Button.Pressed, "#quit")
        def quit_pressed(self) -> None:
            self.exit()

    AlarmTuiApp().run()
    return 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
