import unittest
from datetime import datetime, timedelta, time

import _path  # noqa: F401

from alarm_clock.core import (
    AlarmSpec,
    build_alarm_spec,
    next_alarm_time,
    parse_clock_time,
    parse_duration,
)


class DurationParsingTests(unittest.TestCase):
    def test_parses_unit_durations(self):
        self.assertEqual(parse_duration("10s"), timedelta(seconds=10))
        self.assertEqual(parse_duration("5m"), timedelta(minutes=5))
        self.assertEqual(parse_duration("2h"), timedelta(hours=2))
        self.assertEqual(parse_duration("1h30m15s"), timedelta(hours=1, minutes=30, seconds=15))

    def test_parses_colon_durations(self):
        self.assertEqual(parse_duration("01:30"), timedelta(minutes=1, seconds=30))
        self.assertEqual(parse_duration("01:02:03"), timedelta(hours=1, minutes=2, seconds=3))

    def test_rejects_invalid_durations(self):
        for value in ["", "0s", "-5m", "abc", "1d", "1:99", "1:2:3:4"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_duration(value)


class ClockTimeTests(unittest.TestCase):
    def test_parses_clock_time(self):
        self.assertEqual(parse_clock_time("07:30"), time(hour=7, minute=30))
        self.assertEqual(parse_clock_time("23:59:58"), time(hour=23, minute=59, second=58))

    def test_rejects_invalid_clock_time(self):
        for value in ["", "24:00", "12:60", "7", "7:30", "12:00:99"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_clock_time(value)

    def test_next_alarm_time_uses_today_when_future(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        target = next_alarm_time(now, time(hour=12, minute=1))
        self.assertEqual(target, datetime(2026, 6, 4, 12, 1, 0))

    def test_next_alarm_time_rolls_to_tomorrow_when_past(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        target = next_alarm_time(now, time(hour=11, minute=59))
        self.assertEqual(target, datetime(2026, 6, 5, 11, 59, 0))


class AlarmSpecTests(unittest.TestCase):
    def test_builds_relative_alarm_spec(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        spec = build_alarm_spec(mode="in", value="90s", label="Tea", now=now)
        self.assertEqual(
            spec,
            AlarmSpec(
                scheduled_for=datetime(2026, 6, 4, 12, 1, 30),
                label="Tea",
                source="in 90s",
            ),
        )

    def test_builds_clock_alarm_spec(self):
        now = datetime(2026, 6, 4, 12, 0, 0)
        spec = build_alarm_spec(mode="at", value="12:30", label="Lunch", now=now)
        self.assertEqual(spec.scheduled_for, datetime(2026, 6, 4, 12, 30, 0))
        self.assertEqual(spec.label, "Lunch")
        self.assertEqual(spec.source, "at 12:30")

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            build_alarm_spec(mode="after", value="1m", label="Nope", now=datetime.now())
