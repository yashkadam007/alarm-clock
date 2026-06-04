import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from alarm_clock.cli import DEFAULT_AUDIO_FILE, main, run_alarm
from alarm_clock.core import AlarmSpec


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
            ["in", "30s", "--label", "Stand up", "--dry-run"],
            now_provider=fake_now,
            sleeper=lambda seconds: self.fail("dry-run should not sleep"),
            stdout=out,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Scheduled alarm for 2026-06-04 12:00:30", out.getvalue())
        self.assertIn("Stand up", out.getvalue())

    def test_invalid_input_returns_error(self):
        out = io.StringIO()
        err = io.StringIO()

        exit_code = main(["in", "0s"], stdout=out, stderr=err)

        self.assertEqual(exit_code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Duration must be greater than zero", err.getvalue())

    def test_message_option_is_not_supported(self):
        out = io.StringIO()
        err = io.StringIO()

        with redirect_stderr(err), self.assertRaises(SystemExit) as context:
            main(["in", "30s", "--message", "Old"], stdout=out, stderr=err)

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("unrecognized arguments: --message Old", err.getvalue())

    def test_m_short_option_is_not_supported(self):
        out = io.StringIO()
        err = io.StringIO()

        with redirect_stderr(err), self.assertRaises(SystemExit) as context:
            main(["in", "30s", "-m", "Old"], stdout=out, stderr=err)

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("unrecognized arguments: -m Old", err.getvalue())

    def test_run_alarm_waits_until_target_and_rings(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 12, 0, 2),
            label="Wake up",
            source="in 2s",
        )

        run_alarm(spec, now_provider=fake.now, sleeper=fake.sleep, stdout=out, bell=True)

        self.assertEqual(fake.sleeps, [1.0, 1.0])
        self.assertIn("\a", out.getvalue())
        self.assertIn("ALARM: Wake up", out.getvalue())

    def test_run_alarm_plays_audio_file_when_alarm_fires(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        played = []
        audio_path = Path("alarm.wav")
        spec = AlarmSpec(
            scheduled_for=datetime(2026, 6, 4, 12, 0, 1),
            label="Wake up",
            source="in 1s",
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
            source="in 1s",
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
            ["in", "1s", "--audio-file", "/does/not/exist.wav", "--dry-run"],
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
                ["in", "30s", "--audio-file", str(audio_path), "--dry-run"],
                now_provider=fake_now,
                stdout=out,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Scheduled alarm for 2026-06-04 12:00:30", out.getvalue())

    def test_main_uses_default_audio_file(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()
        played = []

        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(
                ["in", "1s", "--no-bell"],
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
                    ["in", "1s"],
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
                            "source": "at 07:30",
                            "pid": 0,
                        },
                        {
                            "id": "d4e5f6",
                            "scheduled_for": "2026-06-04T18:10:00",
                            "status": "triggered",
                            "label": "Tea break",
                            "source": "in 30m",
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
        self.assertEqual(lines[0], "ID        Time              Status     Label")
        self.assertIn("d4e5f6    2026-06-04 18:10  triggered  Tea break", lines)
        self.assertIn("a1b2c3    2026-06-05 07:30  pending    Wake up", lines)

    def test_off_removes_pending_alarm_by_id(self):
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
                            "source": "in 30m",
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
        self.assertEqual(remaining, [])

    def test_off_all_removes_all_pending_alarms(self):
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
                            "source": "in 30m",
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

            exit_code = main(
                ["off", "--all"],
                now_provider=lambda: datetime(2026, 6, 4, 12, 0, 0),
                stdout=out,
                state_path=state_path,
            )
            remaining = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("Turned off 1 upcoming alarm.", out.getvalue())
        self.assertEqual([item["id"] for item in remaining], ["d4e5f6"])

    def test_off_returns_not_found_for_non_pending_alarm(self):
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
        self.assertIn("No pending alarm found with ID: missing", err.getvalue())

    def test_completed_alarm_is_marked_triggered_in_list_state(self):
        fake = FakeClock(datetime(2026, 6, 4, 12, 0, 0))
        out = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alarms.json"
            exit_code = main(
                ["in", "2s", "--label", "Done", "--no-bell"],
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
        self.assertIn("triggered", list_out.getvalue())
        self.assertIn("Done", list_out.getvalue())


if __name__ == "__main__":
    unittest.main()
