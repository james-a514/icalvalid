# icalvalid

A validating parser and pretty printer for iCalendar (RFC 5545) files.
Standard library only, no dependencies.

## Why

Every calendar app writes slightly different ICS files. Lines get folded
at 75 octets in the middle of words, text values carry backslash-escaped
commas and semicolons, and parameter values that themselves contain a
colon or comma have to be quoted. Most of the bugs in hand-rolled ICS
handling come from getting one of those three things wrong, or from not
noticing that a file is missing a property RFC 5545 requires.

This library parses an ICS document into a plain tree of components and
properties, checks it against the handful of structural rules that make
a file valid (balanced `BEGIN`/`END`, a `VCALENDAR` root, required
`VERSION`/`PRODID`), and can pretty-print the tree back out with
consistent folding and quoting. That second part is useful on its own:
running two calendars exported from different tools through the printer
gives you a diff you can actually read, instead of one dominated by
incidental line-wrapping differences.

## Usage

```python
from icalvalid import parse, render, ValidationError

ics_text = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//example//test//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Team sync\r\n"
    "DTSTART:20260115T090000Z\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

calendar = parse(ics_text)
event = calendar.children[0]
print(event.get("SUMMARY"))  # "Team sync"

# Re-serialize with normalized folding and parameter quoting.
print(render(calendar))
```

Malformed or structurally invalid input raises an exception you can
catch:

```python
try:
    parse("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
except ValidationError as exc:
    print(exc)  # VCALENDAR is missing the required VERSION property
```

`ParseError` is raised for syntax problems (unbalanced `BEGIN`/`END`, a
content line with no colon); `ValidationError` is raised for input that
parses fine but violates an RFC 5545 structural rule.

Property values are kept in their original wire form (still
backslash-escaped) because how to decode a value depends on its data
type. For TEXT-typed properties, `escape_text`/`unescape_text` handle
the `\,` `\;` `\\` `\n` escapes:

```python
from icalvalid import unescape_text

raw = event.get("SUMMARY")  # e.g. "Room A\, Building 2"
print(unescape_text(raw))   # "Room A, Building 2"
```

DATE, DATE-TIME, DURATION, and RECUR values decode the same way, on
demand, once you know which property you're reading:

```python
from icalvalid import parse_date, parse_datetime, parse_duration, parse_recur

parse_date("20260115")             # date(2026, 1, 15)
parse_datetime("20260115T090000Z") # datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
parse_duration("-P1DT2H30M")       # -timedelta(days=1, hours=2, minutes=30)

rule = parse_recur("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE,FR")
rule.freq       # "WEEKLY"
rule.interval   # 2
rule.by_day     # [(0, "MO"), (0, "WE"), (0, "FR")]
```

A DATE-TIME with no trailing "Z" decodes to a naive `datetime`: local
times are meant to be read against the property's `TZID` parameter,
which isn't part of the value string itself. Malformed values raise
`ValueDecodeError`.

A content line may carry a `group.` prefix to tie related properties
together, e.g. `item1.X-ABLABEL:` and `item1.X-ADR:` both describing
the same address. The group is exposed as `ContentLine.group` and
round-trips through `render` unchanged; it doesn't affect how
`Component.get`/`get_all` look properties up by name.

## What's not here yet

- One `VCALENDAR` per document; concatenated multi-calendar files are
  rejected rather than split.

## Development

No build step, no dependencies. Run the tests with:

```
python -m unittest discover -s tests
```
