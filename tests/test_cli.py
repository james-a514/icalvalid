"""Tests for the icalvalid command-line interface."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest

from icalvalid import cli

VALID_CALENDAR = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//example//test//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:event-1@example.com\r\n"
    "DTSTAMP:20260101T000000Z\r\n"
    "DTSTART:20260115T090000Z\r\n"
    "SUMMARY:Team sync\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

BROKEN_CALENDAR = "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"


class _TempFile:
    """A named temp file pre-filled with text, cleaned up on exit."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.path = ""

    def __enter__(self) -> str:
        fd, self.path = tempfile.mkstemp(suffix=".ics")
        with os.fdopen(fd, "w", newline="") as f:
            f.write(self._text)
        return self.path

    def __exit__(self, *exc_info: object) -> None:
        os.remove(self.path)


class ValidateCommandTests(unittest.TestCase):
    def test_valid_calendar_prints_ok_and_returns_zero(self) -> None:
        with _TempFile(VALID_CALENDAR) as path:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["validate", path])
            self.assertEqual(code, 0)
            self.assertIn("ok (1 calendar)", out.getvalue())

    def test_invalid_calendar_prints_error_and_returns_one(self) -> None:
        with _TempFile(BROKEN_CALENDAR) as path:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = cli.main(["validate", path])
            self.assertEqual(code, 1)
            self.assertIn("VERSION", err.getvalue())

    def test_reads_from_stdin_when_file_is_a_dash(self) -> None:
        real_stdin = sys.stdin
        sys.stdin = io.StringIO(VALID_CALENDAR)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["validate", "-"])
        finally:
            sys.stdin = real_stdin
        self.assertEqual(code, 0)
        self.assertIn("ok (1 calendar)", out.getvalue())


class PrintCommandTests(unittest.TestCase):
    def test_prints_normalized_calendar_to_stdout(self) -> None:
        unfolded = VALID_CALENDAR.replace(
            "SUMMARY:Team sync\r\n", "SUMMARY:Team sync, with a note\r\n"
        )
        with _TempFile(unfolded) as path:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["print", path])
            self.assertEqual(code, 0)
            self.assertIn("SUMMARY:Team sync, with a note\r\n", out.getvalue())

    def test_writes_output_to_a_file_when_given(self) -> None:
        with _TempFile(VALID_CALENDAR) as src, _TempFile("") as dst:
            code = cli.main(["print", src, "-o", dst])
            self.assertEqual(code, 0)
            with open(dst, encoding="utf-8", newline="") as f:
                written = f.read()
            self.assertEqual(written, VALID_CALENDAR)

    def test_invalid_calendar_returns_one_without_writing_output(self) -> None:
        with _TempFile(BROKEN_CALENDAR) as src, _TempFile("untouched") as dst:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = cli.main(["print", src, "-o", dst])
            self.assertEqual(code, 1)
            self.assertTrue(err.getvalue())
            with open(dst, encoding="utf-8") as f:
                self.assertEqual(f.read(), "untouched")


class ArgumentParsingTests(unittest.TestCase):
    def test_missing_command_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main([])
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
