"""Table-driven tests for icalvalid, focused on the awkward corners of
RFC 5545: line folding, backslash escaping, and quoted parameter values.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Callable, Optional

from icalvalid import parser as p
from icalvalid.printer import escape_text, fold_line, render, unescape_text


@dataclass
class Case:
    name: str
    text: str
    error: Optional[type] = None
    check: Optional[Callable[[p.Component], None]] = None


CASES: list[Case] = [
    Case(
        name="minimal valid calendar",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "END:VCALENDAR\r\n"
        ),
        check=lambda cal: (
            cal.get("VERSION") == "2.0"
            and cal.get("PRODID") == "-//example//test//EN"
        ),
    ),
    Case(
        name="missing VERSION fails validation",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "PRODID:-//example//test//EN\r\n"
            "END:VCALENDAR\r\n"
        ),
        error=p.ValidationError,
    ),
    Case(
        name="missing PRODID fails validation",
        text="BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
        error=p.ValidationError,
    ),
    Case(
        name="folded line rejoined across a space continuation",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:This is a long summary that wraps across\r\n"
            "  a folded continuation line\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ),
        check=lambda cal: cal.children[0].get("SUMMARY")
        == "This is a long summary that wraps across a folded continuation line",
    ),
    Case(
        name="folded line rejoined across a tab continuation",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "DESCRIPTION:First part\r\n"
            "\t continues here\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ),
        check=lambda cal: cal.children[0].get("DESCRIPTION")
        == "First part continues here",
    ),
    Case(
        name="quoted parameter value keeps its reserved characters",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            'ATTENDEE;CN="Doe, John";DELEGATED-FROM="mailto:a@example.com"'
            ":mailto:john@example.com\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ),
        check=lambda cal: (
            cal.children[0].properties[0].params["CN"] == ["Doe, John"]
            and cal.children[0].properties[0].params["DELEGATED-FROM"]
            == ["mailto:a@example.com"]
            and cal.children[0].properties[0].value == "mailto:john@example.com"
        ),
    ),
    Case(
        name="comma-separated multi-valued parameter",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            'ATTENDEE;MEMBER="mailto:a@example.com","mailto:b@example.com"'
            ":mailto:c@example.com\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ),
        check=lambda cal: cal.children[0].properties[0].params["MEMBER"]
        == ["mailto:a@example.com", "mailto:b@example.com"],
    ),
    Case(
        name="mismatched BEGIN/END is rejected",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:test\r\n"
            "END:VTODO\r\n"
            "END:VCALENDAR\r\n"
        ),
        error=p.ParseError,
    ),
    Case(
        name="unterminated component is rejected",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:test\r\n"
            "END:VCALENDAR\r\n"
        ),
        error=p.ParseError,
    ),
    Case(
        name="content line without a colon is rejected",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BOGUS LINE WITHOUT A SEPARATOR\r\n"
            "END:VCALENDAR\r\n"
        ),
        error=p.ParseError,
    ),
    Case(
        name="group-prefixed property name",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "item1.X-ABLABEL:Home\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ),
        check=lambda cal: (
            cal.children[0].properties[0].group == "ITEM1"
            and cal.children[0].properties[0].name == "X-ABLABEL"
            and cal.children[0].get("X-ABLABEL") == "Home"
        ),
    ),
    Case(
        name="group prefix with no property name is rejected",
        text=(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "item1.:Home\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ),
        error=p.ParseError,
    ),
    Case(
        name="bare LF line endings are accepted like CRLF",
        text=(
            "BEGIN:VCALENDAR\n"
            "VERSION:2.0\n"
            "PRODID:-//example//test//EN\n"
            "END:VCALENDAR\n"
        ),
        check=lambda cal: cal.get("VERSION") == "2.0",
    ),
]


class ParseTableTests(unittest.TestCase):
    def test_cases(self) -> None:
        for case in CASES:
            with self.subTest(case.name):
                if case.error is not None:
                    with self.assertRaises(case.error):
                        p.parse(case.text)
                else:
                    cal = p.parse(case.text)
                    self.assertTrue(case.check(cal), case.name)


class TextEscapingTests(unittest.TestCase):
    def test_round_trip_of_reserved_characters(self) -> None:
        wire = r"Meeting\, Part 1\; Room A\\B\nSecond line"
        decoded = unescape_text(wire)
        self.assertEqual(decoded, "Meeting, Part 1; Room A\\B\nSecond line")
        self.assertEqual(escape_text(decoded), wire)

    def test_parsed_summary_matches_manual_unescape(self) -> None:
        text = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Meeting\\, Part 1\\; Room A\\\\B\\nSecond line\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        cal = p.parse(text)
        raw_value = cal.children[0].get("SUMMARY")
        self.assertEqual(unescape_text(raw_value), "Meeting, Part 1; Room A\\B\nSecond line")


class FoldLineTests(unittest.TestCase):
    LONG_STRINGS = [
        "short value that needs no folding at all",
        "x" * 200,
        "cafe with accents " * 10 + "éééééééé",
    ]

    def test_folded_lines_stay_within_the_octet_limit(self) -> None:
        for value in self.LONG_STRINGS:
            with self.subTest(value[:20]):
                line = f"SUMMARY:{value}"
                folded = fold_line(line)
                for physical in folded.split("\r\n"):
                    self.assertLessEqual(len(physical.encode("utf-8")), 75)

    def test_folded_lines_unfold_back_to_the_original(self) -> None:
        for value in self.LONG_STRINGS:
            with self.subTest(value[:20]):
                line = f"SUMMARY:{value}"
                folded = fold_line(line)
                unfolded = p.unfold(folded)
                self.assertEqual(unfolded, [line])


class RenderRoundTripTests(unittest.TestCase):
    def test_parse_render_parse_preserves_values(self) -> None:
        text = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:" + ("a very long summary line " * 6) + "\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        first = p.parse(text)
        rendered = render(first)
        second = p.parse(rendered)
        self.assertEqual(first.children[0].get("SUMMARY"), second.children[0].get("SUMMARY"))
        self.assertEqual(second.get("VERSION"), "2.0")

    def test_group_prefix_survives_a_render_cycle(self) -> None:
        text = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//example//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "item1.X-ABLABEL:Home\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        first = p.parse(text)
        second = p.parse(render(first))
        prop = second.children[0].properties[0]
        self.assertEqual(prop.group, "ITEM1")
        self.assertEqual(prop.name, "X-ABLABEL")


if __name__ == "__main__":
    unittest.main()
