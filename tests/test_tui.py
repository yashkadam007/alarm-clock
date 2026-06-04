import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from alarm_clock.store import StoredAlarm
from alarm_clock.tui import alarm_table_rows, build_alarm_command


class TuiHelperTests(unittest.TestCase):
    def test_build_alarm_command_uses_alarm_entrypoint(self):
        command = build_alarm_command(
            mode="in",
            value="10m",
            label="Tea",
            audio_file=Path("assets/audio/alarm.mp3"),
        )

        self.assertIn("alarm.py", command[1])
        self.assertEqual(
            command[2:],
            [
                "in",
                "10m",
                "--label",
                "Tea",
                "--audio-file",
                "assets/audio/alarm.mp3",
            ],
        )

    def test_build_alarm_command_adds_recurring_clock_options(self):
        command = build_alarm_command(
            mode="at",
            value="09:00",
            label="Standup",
            repeat="weekdays",
            days=("mon", "tue", "wed", "thu", "fri"),
        )

        self.assertEqual(
            command[2:],
            [
                "at",
                "09:00",
                "--label",
                "Standup",
                "--repeat",
                "days",
                "--days",
                "mon,tue,wed,thu,fri",
            ],
        )

    def test_alarm_table_rows_match_cli_list_shape(self):
        alarms = [
            StoredAlarm(
                alarm_id="a1b2c3",
                scheduled_for=datetime(2026, 6, 5, 7, 30, 0),
                status="pending",
                label="Wake up",
                source="at 07:30",
                pid=0,
                repeat="daily",
            )
        ]

        self.assertEqual(
            alarm_table_rows(alarms),
            [("a1b2c3", "2026-06-05 07:30", "pending", "daily", "Wake up")],
        )


if __name__ == "__main__":
    unittest.main()
