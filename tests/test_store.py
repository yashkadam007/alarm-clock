import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from alarm_clock.store import (
    disable_alarm,
    disable_enabled_alarms,
    enable_alarm,
    list_alarms,
    mark_alarm_ringing,
    snooze_ringing_alarm,
    stop_ringing_alarm,
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
                            "source": "add 12:30",
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
        self.assertEqual(alarms[0].clock_time, datetime(2026, 6, 4, 12, 30).time())
        self.assertTrue(alarms[0].enabled)

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
                            "source": "add 07:30",
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

    def test_list_alarms_accepts_ringing_status(self):
        now = datetime(2026, 6, 4, 12, 0, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:00",
                            "status": "ringing",
                            "label": "Tea",
                            "source": "add 12:30",
                            "pid": 123,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            alarms = list_alarms(now=now, state_path=state_path)

        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].status, "ringing")

    def test_mark_alarm_ringing_updates_status_and_pid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:00",
                            "status": "pending",
                            "label": "Tea",
                            "source": "add 12:30",
                            "pid": 0,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            updated = mark_alarm_ringing("a1b2c3", state_path=state_path)
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertTrue(updated)
        self.assertEqual(raw[0]["status"], "ringing")
        self.assertGreater(raw[0]["pid"], 0)

    def test_stop_ringing_one_time_alarm_marks_triggered(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        terminated = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:00",
                            "status": "ringing",
                            "label": "Tea",
                            "source": "add 12:30",
                            "pid": 123,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            stopped = stop_ringing_alarm(
                "a1b2c3",
                now=now,
                state_path=state_path,
                terminator=terminated.append,
            )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIsNotNone(stopped)
        self.assertEqual(terminated, [123])
        self.assertEqual(raw[0]["id"], "a1b2c3")
        self.assertEqual(raw[0]["status"], "triggered")
        self.assertEqual(raw[0]["pid"], 0)
        self.assertFalse(raw[0]["enabled"])

    def test_stop_ringing_recurring_alarm_reschedules_original_clock_time(self):
        now = datetime(2026, 6, 4, 12, 0, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:00",
                            "status": "ringing",
                            "label": "Wake",
                            "source": "add 07:30",
                            "pid": 0,
                            "repeat": "daily",
                            "repeat_days": [],
                            "clock_time": "07:30:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            stopped = stop_ringing_alarm("a1b2c3", now=now, state_path=state_path)
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIsNotNone(stopped)
        self.assertEqual(raw[0]["id"], "a1b2c3")
        self.assertEqual(raw[0]["scheduled_for"], "2026-06-05T07:30:00")
        self.assertEqual(raw[0]["status"], "pending")
        self.assertEqual(raw[0]["clock_time"], "07:30:00")

    def test_snooze_ringing_alarm_preserves_id_and_recurrence_metadata(self):
        now = datetime(2026, 6, 4, 12, 0, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T07:30:00",
                            "status": "ringing",
                            "label": "Wake",
                            "source": "add 07:30",
                            "pid": 0,
                            "repeat": "daily",
                            "repeat_days": [],
                            "clock_time": "07:30:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            snoozed = snooze_ringing_alarm("a1b2c3", now=now, state_path=state_path)
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIsNotNone(snoozed)
        self.assertEqual(raw[0]["id"], "a1b2c3")
        self.assertEqual(raw[0]["scheduled_for"], "2026-06-04T12:10:00")
        self.assertEqual(raw[0]["status"], "pending")
        self.assertEqual(raw[0]["repeat"], "daily")
        self.assertEqual(raw[0]["clock_time"], "07:30:00")

    def test_disable_alarm_keeps_saved_alarm_and_terminates_process(self):
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
                            "source": "add 12:30",
                            "pid": 12345,
                        },
                        {
                            "id": "d4e5f6",
                            "scheduled_for": "2026-06-04T11:30:00",
                            "status": "triggered",
                            "label": "Old",
                            "source": "add 11:30",
                            "pid": 0,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch("alarm_clock.store._pid_is_running", return_value=True):
                canceled = disable_alarm(
                    "a1b2c3",
                    now=now,
                    state_path=state_path,
                    terminator=terminated.append,
                )
            alarms = list_alarms(now=now, state_path=state_path)

        self.assertIsNotNone(canceled)
        self.assertEqual(canceled.alarm_id, "a1b2c3")
        self.assertEqual(terminated, [12345])
        self.assertEqual([alarm.alarm_id for alarm in alarms], ["d4e5f6", "a1b2c3"])
        disabled_alarm = next(alarm for alarm in alarms if alarm.alarm_id == "a1b2c3")
        self.assertFalse(disabled_alarm.enabled)

    def test_disable_enabled_alarms_keeps_saved_alarms(self):
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
                            "source": "add 12:30",
                            "pid": 111,
                        },
                        {
                            "id": "b2c3d4",
                            "scheduled_for": "2026-06-04T12:45:00",
                            "status": "pending",
                            "label": "Stretch",
                            "source": "add 12:45",
                            "pid": 0,
                        },
                        {
                            "id": "d4e5f6",
                            "scheduled_for": "2026-06-04T11:30:00",
                            "status": "triggered",
                            "label": "Old",
                            "source": "add 11:30",
                            "pid": 0,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch("alarm_clock.store._pid_is_running", return_value=True):
                canceled = disable_enabled_alarms(
                    now=now,
                    state_path=state_path,
                    terminator=terminated.append,
                )
            alarms = list_alarms(now=now, state_path=state_path)

        self.assertEqual([alarm.alarm_id for alarm in canceled], ["a1b2c3", "b2c3d4"])
        self.assertEqual(terminated, [111])
        self.assertEqual([alarm.alarm_id for alarm in alarms], ["d4e5f6", "a1b2c3", "b2c3d4"])
        self.assertTrue(all(not alarm.enabled for alarm in alarms))

    def test_enable_alarm_computes_next_occurrence(self):
        now = datetime(2026, 6, 4, 12, 0, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T07:30:00",
                            "status": "triggered",
                            "label": "Wake",
                            "source": "add 07:30",
                            "pid": 0,
                            "repeat": "none",
                            "repeat_days": [],
                            "clock_time": "07:30:00",
                            "enabled": False,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            enabled = enable_alarm("a1b2c3", now=now, state_path=state_path)
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIsNotNone(enabled)
        self.assertEqual(raw[0]["scheduled_for"], "2026-06-05T07:30:00")
        self.assertEqual(raw[0]["status"], "pending")
        self.assertTrue(raw[0]["enabled"])


if __name__ == "__main__":
    unittest.main()
