import unittest
from datetime import datetime
from pathlib import Path

import _path  # noqa: F401

from alarm_clock.store import StoredAlarm
from alarm_clock.tui import active_ringing_alarm, alarm_table_rows, build_alarm_command


class TuiHelperTests(unittest.TestCase):
    def test_build_alarm_command_uses_alarm_entrypoint(self):
        command = build_alarm_command(
            mode="add",
            value="07:30",
            label="Tea",
            audio_file=Path("assets/audio/alarm.mp3"),
        )

        self.assertIn("alarm.py", command[1])
        self.assertEqual(
            command[2:],
            [
                "add",
                "07:30",
                "--label",
                "Tea",
                "--audio-file",
                "assets/audio/alarm.mp3",
            ],
        )

    def test_build_alarm_command_adds_recurring_clock_options(self):
        command = build_alarm_command(
            mode="add",
            value="09:00",
            label="Standup",
            repeat="weekdays",
            days=("mon", "tue", "wed", "thu", "fri"),
        )

        self.assertEqual(
            command[2:],
            [
                "add",
                "09:00",
                "--label",
                "Standup",
                "--repeat",
                "days",
                "--days",
                "mon,tue,wed,thu,fri",
            ],
        )

    def test_build_alarm_command_can_target_existing_alarm_record(self):
        command = build_alarm_command(
            mode="add",
            value="07:30",
            label="Tea",
            alarm_id="a1b2c3",
        )

        self.assertEqual(
            command[2:],
            ["add", "07:30", "--label", "Tea", "--alarm-id", "a1b2c3"],
        )

    def test_alarm_table_rows_match_cli_list_shape(self):
        alarms = [
            StoredAlarm(
                alarm_id="a1b2c3",
                scheduled_for=datetime(2026, 6, 5, 7, 30, 0),
                status="pending",
                label="Wake up",
                source="add 07:30",
                pid=0,
                repeat="daily",
            )
        ]

        self.assertEqual(
            alarm_table_rows(alarms),
            [("a1b2c3", "2026-06-05 07:30", "on", "daily", "Wake up")],
        )

    def test_active_ringing_alarm_selects_earliest_ringing_alarm(self):
        alarms = [
            StoredAlarm(
                alarm_id="pending",
                scheduled_for=datetime(2026, 6, 4, 11, 0, 0),
                status="pending",
                label="Pending",
                source="add 11:30",
                pid=0,
            ),
            StoredAlarm(
                alarm_id="late",
                scheduled_for=datetime(2026, 6, 4, 12, 5, 0),
                status="ringing",
                label="Late",
                source="add 11:30",
                pid=0,
            ),
            StoredAlarm(
                alarm_id="early",
                scheduled_for=datetime(2026, 6, 4, 12, 0, 0),
                status="ringing",
                label="Early",
                source="add 11:30",
                pid=0,
            ),
        ]

        active = active_ringing_alarm(alarms)

        self.assertIsNotNone(active)
        self.assertEqual(active.alarm_id, "early")


if __name__ == "__main__":
    unittest.main()
