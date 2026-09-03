"""Decode DATE, DATE-TIME, DURATION, and RECUR property values.

The parser keeps every ContentLine.value in its raw wire form, because how
to decode a value depends on its data type, which is a property of the
calendar's semantics (declared by a VALUE param or implied by the property
name) rather than of the line's syntax. These functions decode one value at
a time, the same way printer.unescape_text does for TEXT, and are meant to
be called by whoever already knows which type a given value should be.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .parser import ICalError


class ValueDecodeError(ICalError):
    """A property value does not match the grammar for its declared type."""


def parse_date(value: str) -> date:
    """Decode a DATE value (RFC 5545 3.3.4), e.g. "20260115"."""
    if len(value) != 8 or not value.isdigit():
        raise ValueDecodeError(f"not a valid DATE value: {value!r}")
    try:
        return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as exc:
        raise ValueDecodeError(f"not a valid DATE value: {value!r}") from exc


def parse_datetime(value: str) -> datetime:
    """Decode a DATE-TIME value (RFC 5545 3.3.5), e.g. "20260115T090000Z".

    A trailing "Z" marks UTC and produces a timezone-aware datetime.
    Anything else produces a naive datetime: a "local time" DATE-TIME is
    meant to be interpreted against the property's TZID parameter, which
    this function has no access to.
    """
    utc = value.endswith("Z")
    body = value[:-1] if utc else value
    digits = body[:8] + body[9:]
    if len(body) != 15 or body[8] != "T" or not digits.isdigit():
        raise ValueDecodeError(f"not a valid DATE-TIME value: {value!r}")
    try:
        dt = datetime(
            int(body[0:4]), int(body[4:6]), int(body[6:8]),
            int(body[9:11]), int(body[11:13]), int(body[13:15]),
        )
    except ValueError as exc:
        raise ValueDecodeError(f"not a valid DATE-TIME value: {value!r}") from exc
    return dt.replace(tzinfo=timezone.utc) if utc else dt


_DURATION_RE = re.compile(
    r"^(?P<sign>[+-]?)P(?:"
    r"(?P<weeks>\d+)W"
    r"|(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
    r")$"
)


def parse_duration(value: str) -> timedelta:
    """Decode a DURATION value (RFC 5545 3.3.6), e.g. "-P1DT2H30M"."""
    match = _DURATION_RE.match(value)
    fields = ("weeks", "days", "hours", "minutes", "seconds")
    if not match or not any(match.group(g) for g in fields):
        raise ValueDecodeError(f"not a valid DURATION value: {value!r}")
    weeks, days, hours, minutes, seconds = (int(match.group(g) or 0) for g in fields)
    delta = timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)
    return -delta if match.group("sign") == "-" else delta


_VALID_FREQ = {
    "SECONDLY", "MINUTELY", "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY",
}
_WEEKDAYS = {"SU", "MO", "TU", "WE", "TH", "FR", "SA"}
_BYDAY_RE = re.compile(r"^([+-]?\d{1,2})?(SU|MO|TU|WE|TH|FR|SA)$")


@dataclass
class RecurrenceRule:
    """A decoded RECUR value (RFC 5545 3.3.10).

    by_day entries are (ordinal, weekday) pairs, e.g. "2MO" decodes to
    (2, "MO") and a bare "MO" decodes to (0, "MO") meaning every Monday.
    """

    freq: str
    interval: int = 1
    count: int | None = None
    until: date | datetime | None = None
    by_second: list[int] = field(default_factory=list)
    by_minute: list[int] = field(default_factory=list)
    by_hour: list[int] = field(default_factory=list)
    by_day: list[tuple[int, str]] = field(default_factory=list)
    by_month_day: list[int] = field(default_factory=list)
    by_year_day: list[int] = field(default_factory=list)
    by_week_no: list[int] = field(default_factory=list)
    by_month: list[int] = field(default_factory=list)
    by_set_pos: list[int] = field(default_factory=list)
    wkst: str = "MO"


def _parse_byday(part: str) -> tuple[int, str]:
    match = _BYDAY_RE.match(part)
    if not match:
        raise ValueDecodeError(f"not a valid BYDAY entry: {part!r}")
    ordinal = int(match.group(1)) if match.group(1) else 0
    return (ordinal, match.group(2))


def _parse_int_list(value: str, low: int, high: int, allow_negative: bool = True) -> list[int]:
    out = []
    for part in value.split(","):
        try:
            n = int(part)
        except ValueError as exc:
            raise ValueDecodeError(f"not a valid integer in {value!r}") from exc
        if n < 0 and not allow_negative:
            raise ValueDecodeError(f"negative value not allowed in {value!r}")
        if not (low <= abs(n) <= high):
            raise ValueDecodeError(f"{n} is out of range in {value!r}")
        out.append(n)
    return out


def parse_recur(value: str) -> RecurrenceRule:
    """Decode a RECUR value, e.g. "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE,FR"."""
    parts: dict[str, str] = {}
    for piece in value.split(";"):
        if not piece:
            continue
        name, sep, part_value = piece.partition("=")
        if not sep:
            raise ValueDecodeError(f"malformed RECUR part {piece!r} in {value!r}")
        parts[name.upper()] = part_value

    freq = parts.get("FREQ")
    if freq is None or freq not in _VALID_FREQ:
        raise ValueDecodeError(f"RECUR value is missing a valid FREQ: {value!r}")

    if "UNTIL" in parts and "COUNT" in parts:
        raise ValueDecodeError("RECUR value has both UNTIL and COUNT, which is not allowed")

    until: date | datetime | None = None
    if "UNTIL" in parts:
        raw_until = parts["UNTIL"]
        until = parse_datetime(raw_until) if len(raw_until) > 8 else parse_date(raw_until)

    count = None
    if "COUNT" in parts:
        try:
            count = int(parts["COUNT"])
        except ValueError as exc:
            raise ValueDecodeError(f"not a valid COUNT: {parts['COUNT']!r}") from exc

    interval = 1
    if "INTERVAL" in parts:
        try:
            interval = int(parts["INTERVAL"])
        except ValueError as exc:
            raise ValueDecodeError(f"not a valid INTERVAL: {parts['INTERVAL']!r}") from exc

    wkst = parts.get("WKST", "MO")
    if wkst not in _WEEKDAYS:
        raise ValueDecodeError(f"not a valid WKST: {wkst!r}")

    return RecurrenceRule(
        freq=freq,
        interval=interval,
        count=count,
        until=until,
        by_second=_parse_int_list(parts["BYSECOND"], 0, 60) if "BYSECOND" in parts else [],
        by_minute=_parse_int_list(parts["BYMINUTE"], 0, 59) if "BYMINUTE" in parts else [],
        by_hour=_parse_int_list(parts["BYHOUR"], 0, 23) if "BYHOUR" in parts else [],
        by_day=[_parse_byday(p) for p in parts["BYDAY"].split(",")] if "BYDAY" in parts else [],
        by_month_day=_parse_int_list(parts["BYMONTHDAY"], 1, 31) if "BYMONTHDAY" in parts else [],
        by_year_day=_parse_int_list(parts["BYYEARDAY"], 1, 366) if "BYYEARDAY" in parts else [],
        by_week_no=_parse_int_list(parts["BYWEEKNO"], 1, 53) if "BYWEEKNO" in parts else [],
        by_month=_parse_int_list(
            parts["BYMONTH"], 1, 12, allow_negative=False
        ) if "BYMONTH" in parts else [],
        by_set_pos=_parse_int_list(parts["BYSETPOS"], 1, 366) if "BYSETPOS" in parts else [],
        wkst=wkst,
    )
