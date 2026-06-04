import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from alarm_clock.store import (
    cancel_alarm,
    cancel_pending_alarms,
    list_alarms,
    update_alarm_schedule,
)


class StoreCancellationTests(unittest.TestCase):
    def test_list_alarms_defaults_missing_recurrence_to_none(self):
        now = datetime(2026, 6, 4, 12, 0, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:30:00",
                            "status": "pending",
                            "label": "Tea",
                            "source": "in 30m",
                            "pid": 0,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            alarms = list_alarms(now=now, state_path=state_path)

        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].repeat, "none")
        self.assertEqual(alarms[0].repeat_days, ())

    def test_update_alarm_schedule_keeps_alarm_pending_with_same_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T07:30:00",
                            "status": "pending",
                            "label": "Wake",
                            "source": "at 07:30",
                            "pid": 111,
                            "repeat": "daily",
                            "repeat_days": [],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            update_alarm_schedule(
                "a1b2c3",
                datetime(2026, 6, 5, 7, 30, 0),
                state_path=state_path,
            )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(raw[0]["id"], "a1b2c3")
        self.assertEqual(raw[0]["scheduled_for"], "2026-06-05T07:30:00")
        self.assertEqual(raw[0]["status"], "pending")
        self.assertEqual(raw[0]["repeat"], "daily")

    def test_cancel_alarm_removes_pending_alarm_and_terminates_process(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        terminated = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:30:00",
                            "status": "pending",
                            "label": "Tea",
                            "source": "in 30m",
                            "pid": 12345,
                        },
                        {
                            "id": "d4e5f6",
                            "scheduled_for": "2026-06-04T11:30:00",
                            "status": "triggered",
                            "label": "Old",
                            "source": "in 10m",
                            "pid": 0,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch("alarm_clock.store._pid_is_running", return_value=True):
                canceled = cancel_alarm(
                    "a1b2c3",
                    now=now,
                    state_path=state_path,
                    terminator=terminated.append,
                )
            alarms = list_alarms(now=now, state_path=state_path)

        self.assertIsNotNone(canceled)
        self.assertEqual(canceled.alarm_id, "a1b2c3")
        self.assertEqual(terminated, [12345])
        self.assertEqual([alarm.alarm_id for alarm in alarms], ["d4e5f6"])

    def test_cancel_pending_alarms_keeps_triggered_alarms(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        terminated = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:30:00",
                            "status": "pending",
                            "label": "Tea",
                            "source": "in 30m",
                            "pid": 111,
                        },
                        {
                            "id": "b2c3d4",
                            "scheduled_for": "2026-06-04T12:45:00",
                            "status": "pending",
                            "label": "Stretch",
                            "source": "in 45m",
                            "pid": 0,
                        },
                        {
                            "id": "d4e5f6",
                            "scheduled_for": "2026-06-04T11:30:00",
                            "status": "triggered",
                            "label": "Old",
                            "source": "in 10m",
                            "pid": 0,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch("alarm_clock.store._pid_is_running", return_value=True):
                canceled = cancel_pending_alarms(
                    now=now,
                    state_path=state_path,
                    terminator=terminated.append,
                )
            alarms = list_alarms(now=now, state_path=state_path)

        self.assertEqual([alarm.alarm_id for alarm in canceled], ["a1b2c3", "b2c3d4"])
        self.assertEqual(terminated, [111])
        self.assertEqual([alarm.alarm_id for alarm in alarms], ["d4e5f6"])


if __name__ == "__main__":
    unittest.main()
