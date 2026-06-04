import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from alarm_clock.cli import DEFAULT_AUDIO_FILE, _worker_command, main, run_alarm
from alarm_clock.core import AlarmSpec
from alarm_clock.store import update_alarm_schedule


class FakeClock:
    def __init__(self, start):
        self.current = start
        self.sleeps = []

    def now(self):
        return self.current

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


class CliTests(unittest.TestCase):
    def test_dry_run_prints_schedule_without_waiting(self):
        out = io.StringIO()
        fake_now = lambda: datetime(2026, 6, 4, 12, 0, 0)

        exit_code = main(
            ["add", "12:30", "--label", "Stand up", "--dry-run"],
            now_provider=fake_now,
            sleeper=lambda seconds: self.fail("dry-run should not sleep"),
            stdout=out,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Scheduled alarm for 2026-06-04 12:30:00", out.getvalue())
        self.assertIn("Stand up", out.getvalue())

    def test_dry_run_prints_recurring_clock_alarm(self):
        out = io.StringIO()
        fake_now = lambda: datetime(2026, 6, 4, 12, 0, 0)

        exit_code = main(
            [
                "add",
                "09:00",
                "--label",
                "Standup",
                "--repeat",
                "days",
                "--days",
                "mon,tue,wed,thu,fri",
                "--dry-run",
            ],
            now_provider=fake_now,
            sleeper=lambda seconds: self.fail("dry-run should not sleep"),
            stdout=out,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Scheduled alarm for 2026-06-05 09:00:00", out.getvalue())
        self.assertIn("repeat mon,tue,wed,thu,fri", out.getvalue())

    def test_repeat_days_requires_days_option(self):
        err = io.StringIO()

        exit_code = main(["add", "09:00", "--repeat", "days"], stderr=err)

        self.assertEqual(exit_code, 2)
        self.assertIn("--days is required with --repeat days", err.getvalue())

    def test_invalid_input_returns_error(self):
        out = io.StringIO()
        err = io.StringIO()

        exit_code = main(["add", "99:00"], stdout=out, stderr=err)

        self.assertEqual(exit_code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Invalid clock time", err.getvalue())

    def test_message_option_is_not_supported(self):
        out = io.StringIO()
        err = io.StringIO()

        with redirect_stderr(err), self.assertRaises(SystemExit) as context:
            main(["add", "12:30", "--message", "Old"], stdout=out, stderr=err)

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("unrecognized arguments: --message Old", err.getvalue())

    def test_m_short_option_is_not_supported(self):
        out = io.StringIO()
        err = io.StringIO()

        with redirect_stderr(err), self.assertRaises(SystemExit) as context:
            main(["add", "12:30", "-m", "Old"], stdout=out, stderr=err)

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("unrecognized arguments: -m Old", err.getvalue())

    def test_run_alarm_waits_until_target_and_rings(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 12, 0, 2),
            label="Wake up",
            source="add 12:00:02",
        )

        run_alarm(spec, now_provider=fake.now, sleeper=fake.sleep, stdout=out, bell=True)

        self.assertEqual(fake.sleeps, [1.0, 1.0])
        self.assertIn("\a", out.getvalue())
        self.assertIn("ALARM: Wake up", out.getvalue())

    def test_run_alarm_reschedules_recurring_alarm_in_store(self):
        fake = FakeClock(datetime(2026, 6, 4, 7, 29, 58))
        out = io.StringIO()
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 7, 30, 0),
            label="Wake up",
            source="add 07:30",
            repeat="daily",
            clock_time=datetime(2026, 6, 4, 7, 30, 0).time(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T07:30:00",
                            "status": "pending",
                            "label": "Wake up",
                            "source": "add 07:30",
                            "pid": 0,
                            "repeat": "daily",
                            "repeat_days": [],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            run_alarm(
                spec,
                now_provider=fake.now,
                sleeper=fake.sleep,
                stdout=out,
                bell=False,
                alarm_id="a1b2c3",
                state_path=state_path,
                max_fires=1,
            )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(fake.sleeps, [1.0, 1.0])
        self.assertEqual(raw[0]["id"], "a1b2c3")
        self.assertEqual(raw[0]["scheduled_for"], "2026-06-05T07:30:00")
        self.assertEqual(raw[0]["status"], "pending")
        self.assertIn("Rescheduled alarm for 2026-06-05 07:30:00", out.getvalue())

    def test_run_alarm_marks_alarm_ringing_before_output(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 12, 0, 1),
            label="Wake up",
            source="add 12:00:01",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:01",
                            "status": "pending",
                            "label": "Wake up",
                            "source": "add 12:00:01",
                            "pid": 0,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            run_alarm(
                spec,
                now_provider=fake.now,
                sleeper=fake.sleep,
                stdout=out,
                bell=False,
                alarm_id="a1b2c3",
                state_path=state_path,
            )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(raw[0]["status"], "ringing")
        self.assertIn("ALARM: Wake up", out.getvalue())

    def test_run_alarm_plays_audio_file_when_alarm_fires(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        played = []
        audio_path = Path("alarm.wav")
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 12, 0, 1),
            label="Wake up",
            source="add 12:00:01",
            audio_file=audio_path,
        )

        run_alarm(
            spec,
            now_provider=fake.now,
            sleeper=fake.sleep,
            stdout=out,
            audio_player=played.append,
        )

        self.assertEqual(played, [audio_path])
        self.assertIn("ALARM: Wake up", out.getvalue())

    def test_run_alarm_warns_when_audio_playback_fails(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        err = io.StringIO()
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 12, 0, 1),
            label="Wake up",
            source="add 12:00:01",
            audio_file=Path("alarm.wav"),
        )

        def fail_audio(_path):
            raise RuntimeError("Audio playback failed")

        run_alarm(
            spec,
            now_provider=fake.now,
            sleeper=fake.sleep,
            stdout=out,
            stderr=err,
            audio_player=fail_audio,
        )

        self.assertIn("ALARM: Wake up", out.getvalue())
        self.assertIn("Warning: Audio playback failed", err.getvalue())

    def test_invalid_audio_file_returns_error(self):
        out = io.StringIO()
        err = io.StringIO()

        exit_code = main(
            ["add", "12:01", "--audio-file", "/does/not/exist.wav", "--dry-run"],
            stdout=out,
            stderr=err,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Audio file does not exist", err.getvalue())

    def test_dry_run_accepts_existing_audio_file(self):
        out = io.StringIO()
        fake_now = lambda: datetime(2026, 6, 4, 12, 0, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "alarm.wav"
            audio_path.write_bytes(b"not-real-audio")
            exit_code = main(
                ["add", "12:30", "--audio-file", str(audio_path), "--dry-run"],
                now_provider=fake_now,
                stdout=out,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Scheduled alarm for 2026-06-04 12:30:00", out.getvalue())

    def test_main_uses_default_audio_file(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        played = []

        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(
                ["add", "12:00:01", "--no-bell", "--foreground"],
                now_provider=fake.now,
                sleeper=fake.sleep,
                stdout=out,
                state_path=Path(temp_dir) / "alarms.json",
                audio_player=played.append,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(played, [DEFAULT_AUDIO_FILE])

    def test_ctrl_c_returns_interrupted_status(self):
        out = io.StringIO()
        err = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            with patch("alarm_clock.cli.run_alarm", side_effect=KeyboardInterrupt):
                exit_code = main(
                    ["add", "12:00:01", "--foreground"],
                    stdout=out,
                    stderr=err,
                    state_path=state_path,
                )

        self.assertEqual(exit_code, 130)
        self.assertIn("Alarm cancelled", err.getvalue())

    def test_list_prints_no_alarms(self):
        out = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(
                ["list"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                stdout=out,
                state_path=Path(temp_dir) / "alarms.json",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(out.getvalue(), "No alarms.\n")

    def test_tui_command_dispatches_to_tui_runner(self):
        out = io.StringIO()
        err = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            with patch("alarm_clock.tui.run_tui", return_value=0) as run_tui:
                exit_code = main(
                    ["tui"],
                    stdout=out,
                    stderr=err,
                    state_path=state_path,
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        run_tui.assert_called_once_with(state_path=state_path)

    def test_list_prints_alarm_table(self):
        out = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-05T07:30:00",
                            "status": "pending",
                            "label": "Wake up",
                            "source": "add 07:30",
                            "pid": 0,
                        },
                        {
                            "id": "d4e5f6",
                            "scheduled_for": "2026-06-04T18:10:00",
                            "status": "triggered",
                            "label": "Tea break",
                            "source": "add 12:30",
                            "pid": 0,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            exit_code = main(
                ["list"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                stdout=out,
                state_path=state_path,
            )

        self.assertEqual(exit_code, 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "ID        Time              Status     Repeat       Label")
        self.assertIn("d4e5f6    2026-06-04 18:10  off        none         Tea break", lines)
        self.assertIn("a1b2c3    2026-06-05 07:30  on         none         Wake up", lines)

    def test_off_disables_alarm_by_id(self):
        out = io.StringIO()
        err = io.StringIO()

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

            exit_code = main(
                ["off", "a1b2c3"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                stdout=out,
                stderr=err,
                state_path=state_path,
            )
            remaining = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("Turned off alarm a1b2c3: Tea", out.getvalue())
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(remaining[0]["id"], "a1b2c3")
        self.assertFalse(remaining[0]["enabled"])
        self.assertEqual(remaining[0]["status"], "triggered")

    def test_off_all_disables_enabled_alarms(self):
        out = io.StringIO()

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

            exit_code = main(
                ["off", "--all"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                stdout=out,
                state_path=state_path,
            )
            remaining = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("Turned off 1 alarm.", out.getvalue())
        self.assertEqual([item["id"] for item in remaining], ["d4e5f6", "a1b2c3"])
        self.assertTrue(all(not item["enabled"] for item in remaining))

    def test_off_returns_not_found_for_non_enabled_alarm(self):
        out = io.StringIO()
        err = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(
                ["off", "missing"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                stdout=out,
                stderr=err,
                state_path=Path(temp_dir) / "alarms.json",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("No enabled alarm found with ID: missing", err.getvalue())

    def test_completed_alarm_is_marked_off_in_list_state(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            exit_code = main(
                [
                    "add",
                    "12:00:02",
                    "--label",
                    "Done",
                    "--no-bell",
                    "--foreground",
                ],
                now_provider=fake.now,
                sleeper=fake.sleep,
                stdout=out,
                state_path=state_path,
                audio_player=lambda _path: None,
            )

            list_out = io.StringIO()
            list_exit_code = main(
                ["list"],
                now_provider=fake.now,
                stdout=list_out,
                state_path=state_path,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(list_exit_code, 0)
        self.assertIn("off", list_out.getvalue())
        self.assertIn("Done", list_out.getvalue())

    def test_existing_snoozed_recurring_alarm_resumes_original_schedule(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:01",
                            "status": "pending",
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

            def fake_run_alarm(spec, **kwargs):
                self.assertEqual(spec.scheduled_for, datetime(2026, 6, 4, 12, 0, 1))
                self.assertEqual(spec.repeat, "daily")
                self.assertEqual(spec.clock_time, datetime(2026, 6, 4, 7, 30).time())
                update_alarm_schedule(
                    "a1b2c3",
                    datetime(2026, 6, 5, 7, 30, 0),
                    state_path=state_path,
                )

            with patch("alarm_clock.cli.run_alarm", side_effect=fake_run_alarm):
                exit_code = main(
                    [
                        "add",
                        "12:00:01",
                        "--label",
                        "Wake",
                        "--alarm-id",
                        "a1b2c3",
                        "--no-bell",
                        "--foreground",
                    ],
                    now_provider=fake.now,
                    sleeper=fake.sleep,
                    stdout=out,
                    state_path=state_path,
                    audio_player=lambda _path: None,
                )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(raw[0]["id"], "a1b2c3")
        self.assertEqual(raw[0]["scheduled_for"], "2026-06-05T07:30:00")
        self.assertEqual(raw[0]["status"], "pending")
        self.assertEqual(raw[0]["repeat"], "daily")

    def test_add_launches_worker_and_returns_without_waiting(self):
        out = io.StringIO()
        fake_now = lambda: datetime(2026, 6, 4, 12, 0, 0)
        launched = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            exit_code = main(
                ["add", "12:30", "--label", "Tea"],
                now_provider=fake_now,
                sleeper=lambda seconds: self.fail("add should not sleep"),
                stdout=out,
                state_path=state_path,
                worker_launcher=lambda alarm_id: launched.append(alarm_id) or 4321,
            )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(launched), 1)
        self.assertEqual(raw[0]["id"], launched[0])
        self.assertEqual(raw[0]["pid"], 4321)
        self.assertEqual(raw[0]["audio_file"], str(DEFAULT_AUDIO_FILE))
        self.assertIn("Scheduled alarm for 2026-06-04 12:30:00", out.getvalue())

    def test_worker_command_runs_stored_alarm(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        played = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            audio_path = Path(temp_dir) / "alarm.wav"
            audio_path.write_bytes(b"not-real-audio")
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:01",
                            "status": "pending",
                            "label": "Tea",
                            "source": "add 12:00:01",
                            "pid": 0,
                            "enabled": True,
                            "audio_file": str(audio_path),
                        }
                    ]
                ),
                encoding="utf-8",
            )

            exit_code = main(
                ["worker", "a1b2c3", "--no-bell"],
                now_provider=fake.now,
                sleeper=fake.sleep,
                stdout=out,
                state_path=state_path,
                audio_player=played.append,
            )
            raw = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake.sleeps, [1.0])
        self.assertEqual(played, [audio_path])
        self.assertEqual(raw[0]["status"], "triggered")
        self.assertFalse(raw[0]["enabled"])
        self.assertIn("ALARM: Tea", out.getvalue())

    def test_worker_command_ignores_missing_or_disabled_alarm(self):
        out = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            state_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a1b2c3",
                            "scheduled_for": "2026-06-04T12:00:01",
                            "status": "pending",
                            "label": "Tea",
                            "source": "add 12:00:01",
                            "pid": 0,
                            "enabled": False,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            exit_code = main(
                ["worker", "a1b2c3"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                sleeper=lambda seconds: self.fail("disabled worker should not sleep"),
                stdout=out,
                state_path=state_path,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(out.getvalue(), "")

    def test_worker_command_builder_can_disable_bell(self):
        command = _worker_command("a1b2c3", no_bell=True)

        self.assertEqual(command[-3:], ["worker", "a1b2c3", "--no-bell"])


if __name__ == "__main__":
    unittest.main()
