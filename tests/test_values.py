"""Table-driven tests for decoding DATE, DATE-TIME, DURATION, and RECUR
values into their Python types.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from icalvalid.values import (
    RecurrenceRule,
    ValueDecodeError,
    parse_date,
    parse_datetime,
    parse_duration,
    parse_recur,
)


@dataclass
class Case:
    name: str
    fn: Callable[[str], Any]
    value: str
    expected: Any = None
    error: Optional[type] = None


CASES: list[Case] = [
    Case("plain date", parse_date, "20260115", date(2026, 1, 15)),
    Case("date with bad length is rejected", parse_date, "2026115", error=ValueDecodeError),
    Case("date with impossible day is rejected", parse_date, "20260230", error=ValueDecodeError),
    Case(
        "utc date-time",
        parse_datetime,
        "20260115T090000Z",
        datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
    ),
    Case(
        "local date-time is naive",
        parse_datetime,
        "20260115T090000",
        datetime(2026, 1, 15, 9, 0, 0),
    ),
    Case("date-time missing T separator is rejected", parse_datetime, "20260115090000Z",
         error=ValueDecodeError),
    Case("date-time with garbage digits is rejected", parse_datetime, "2026011XT090000Z",
         error=ValueDecodeError),
    Case("duration of days and hours", parse_duration, "P1DT2H30M",
         timedelta(days=1, hours=2, minutes=30)),
    Case("negative duration", parse_duration, "-P1DT2H30M",
         -timedelta(days=1, hours=2, minutes=30)),
    Case("duration in weeks", parse_duration, "P3W", timedelta(weeks=3)),
    Case("duration of seconds only", parse_duration, "PT45S", timedelta(seconds=45)),
    Case("bare P with no components is rejected", parse_duration, "P", error=ValueDecodeError),
    Case("duration missing P prefix is rejected", parse_duration, "1DT2H",
         error=ValueDecodeError),
]


class ValueDecodingTests(unittest.TestCase):
    def test_cases(self) -> None:
        for case in CASES:
            with self.subTest(case.name):
                if case.error is not None:
                    with self.assertRaises(case.error):
                        case.fn(case.value)
                else:
                    self.assertEqual(case.fn(case.value), case.expected)


class RecurTests(unittest.TestCase):
    def test_weekly_with_byday_and_interval(self) -> None:
        rule = parse_recur("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE,FR")
        self.assertEqual(
            rule,
            RecurrenceRule(
                freq="WEEKLY",
                interval=2,
                by_day=[(0, "MO"), (0, "WE"), (0, "FR")],
            ),
        )

    def test_monthly_with_ordinal_byday_and_count(self) -> None:
        rule = parse_recur("FREQ=MONTHLY;COUNT=5;BYDAY=-1SU")
        self.assertEqual(rule.freq, "MONTHLY")
        self.assertEqual(rule.count, 5)
        self.assertEqual(rule.by_day, [(-1, "SU")])

    def test_until_as_date_time(self) -> None:
        rule = parse_recur("FREQ=DAILY;UNTIL=20260201T000000Z")
        self.assertEqual(rule.until, datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc))

    def test_until_as_date(self) -> None:
        rule = parse_recur("FREQ=DAILY;UNTIL=20260201")
        self.assertEqual(rule.until, date(2026, 2, 1))

    def test_yearly_with_bymonth_and_bymonthday(self) -> None:
        rule = parse_recur("FREQ=YEARLY;BYMONTH=1,7;BYMONTHDAY=1,-1")
        self.assertEqual(rule.by_month, [1, 7])
        self.assertEqual(rule.by_month_day, [1, -1])

    def test_missing_freq_is_rejected(self) -> None:
        with self.assertRaises(ValueDecodeError):
            parse_recur("INTERVAL=2")

    def test_until_and_count_together_is_rejected(self) -> None:
        with self.assertRaises(ValueDecodeError):
            parse_recur("FREQ=DAILY;COUNT=5;UNTIL=20260201")

    def test_out_of_range_byhour_is_rejected(self) -> None:
        with self.assertRaises(ValueDecodeError):
            parse_recur("FREQ=DAILY;BYHOUR=25")

    def test_malformed_byday_is_rejected(self) -> None:
        with self.assertRaises(ValueDecodeError):
            parse_recur("FREQ=WEEKLY;BYDAY=XX")


if __name__ == "__main__":
    unittest.main()
