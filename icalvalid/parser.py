"""Parse iCalendar (RFC 5545) text into a validated component tree.

The parser is deliberately literal: property values are kept in their
wire form (still backslash-escaped) rather than decoded, because the
correct decoding depends on the value's data type (TEXT, DATE-TIME, ...)
which this module does not track. See printer.unescape_text for TEXT
values and values.py for DATE/DATE-TIME/DURATION/RECUR, both decoded
on demand once the caller knows a value's type.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ICalError(Exception):
    """Base class for problems found while parsing or validating."""


class ParseError(ICalError):
    """The input is not well-formed iCalendar syntax."""


class ValidationError(ICalError):
    """The input parses but violates a structural rule of RFC 5545."""


@dataclass
class ContentLine:
    name: str
    params: dict[str, list[str]]
    value: str
    group: str | None = None


@dataclass
class Component:
    name: str
    properties: list[ContentLine] = field(default_factory=list)
    children: list["Component"] = field(default_factory=list)

    def get(self, name: str) -> str | None:
        """Return the value of the first property with this name, if any."""
        name = name.upper()
        for prop in self.properties:
            if prop.name == name:
                return prop.value
        return None

    def get_all(self, name: str) -> list[str]:
        name = name.upper()
        return [p.value for p in self.properties if p.name == name]


def unfold(text: str) -> list[str]:
    """Reverse RFC 5545 line folding, returning one string per content line.

    A folded continuation line starts with a space or tab; that single
    character is the fold marker and is stripped, not part of the value.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw = normalized.split("\n")
    lines: list[str] = []
    for segment in raw:
        if segment.startswith(" ") or segment.startswith("\t"):
            if not lines:
                raise ParseError("content starts with a continuation line")
            lines[-1] += segment[1:]
        else:
            lines.append(segment)
    return lines


def parse_content_line(raw: str, lineno: int) -> ContentLine:
    """Split one unfolded line into group, name, parameters, and raw value.

    A content line may be prefixed with "group." to tie related
    properties together, e.g. two lines both starting with "item1." so
    a consumer knows they describe the same thing. Group and name share
    the same charset (ALPHA / DIGIT / "-"), so the first "." before any
    ";" or ":" is the group separator.
    """
    n = len(raw)
    i = 0
    while i < n and raw[i] not in ";:":
        i += 1
    if i == 0:
        raise ParseError(f"line {lineno}: empty property name in {raw!r}")
    name_field = raw[:i]
    group, dot, rest = name_field.partition(".")
    if dot:
        if not group:
            raise ParseError(f"line {lineno}: empty group name in {raw!r}")
        if not rest:
            raise ParseError(f"line {lineno}: empty property name in {raw!r}")
        group = group.upper()
        name = rest.upper()
    else:
        group = None
        name = name_field.upper()

    params: dict[str, list[str]] = {}
    while i < n and raw[i] == ";":
        i += 1
        pname_start = i
        while i < n and raw[i] != "=":
            i += 1
        if i >= n:
            raise ParseError(f"line {lineno}: malformed parameter in {raw!r}")
        pname = raw[pname_start:i].upper()
        i += 1

        values: list[str] = []
        while True:
            if i < n and raw[i] == '"':
                i += 1
                val_start = i
                while i < n and raw[i] != '"':
                    i += 1
                if i >= n:
                    raise ParseError(
                        f"line {lineno}: unterminated quoted parameter value in {raw!r}"
                    )
                values.append(raw[val_start:i])
                i += 1
            else:
                val_start = i
                while i < n and raw[i] not in ",;:":
                    i += 1
                values.append(raw[val_start:i])
            if i < n and raw[i] == ",":
                i += 1
                continue
            break
        params[pname] = values

    if i >= n or raw[i] != ":":
        raise ParseError(f"line {lineno}: expected ':' after parameters in {raw!r}")
    value = raw[i + 1 :]
    return ContentLine(name=name, params=params, value=value, group=group)


def parse_all(text: str) -> list[Component]:
    """Parse and validate one or more VCALENDAR documents from one text blob.

    Most producers write a single VCALENDAR per file, but some tools
    (mail attachments in particular) concatenate several with no
    separator between END:VCALENDAR and the next BEGIN:VCALENDAR. Each
    one found at the top level is parsed and validated independently.
    """
    raw_lines = unfold(text)

    stack: list[Component] = []
    roots: list[Component] = []

    for i, raw in enumerate(raw_lines):
        if raw == "":
            continue
        cl = parse_content_line(raw, i + 1)

        if cl.name == "BEGIN":
            comp = Component(name=cl.value.upper())
            if stack:
                stack[-1].children.append(comp)
            else:
                roots.append(comp)
            stack.append(comp)
        elif cl.name == "END":
            if not stack:
                raise ParseError(f"line {i + 1}: END:{cl.value} without matching BEGIN")
            top = stack.pop()
            if top.name != cl.value.upper():
                raise ParseError(
                    f"line {i + 1}: expected END:{top.name}, found END:{cl.value}"
                )
        else:
            if not stack:
                raise ParseError(f"line {i + 1}: property {cl.name} outside any component")
            stack[-1].properties.append(cl)

    if stack:
        names = ", ".join(c.name for c in stack)
        raise ParseError(f"unterminated component(s): {names}")
    if not roots:
        raise ParseError("empty document: no BEGIN:VCALENDAR found")

    for root in roots:
        if root.name != "VCALENDAR":
            raise ValidationError(f"top-level component must be VCALENDAR, found {root.name}")
        _validate_calendar(root)

    return roots


def parse(text: str) -> Component:
    """Parse and validate a single iCalendar document.

    Raises ParseError for malformed syntax (bad content lines, unbalanced
    BEGIN/END) and ValidationError for structurally valid documents that
    violate RFC 5545 requirements (missing VERSION/PRODID, wrong root).
    Also raises ValidationError if the text holds more than one top-level
    VCALENDAR; call parse_all directly to handle that case.
    """
    roots = parse_all(text)
    if len(roots) > 1:
        raise ValidationError(
            f"expected exactly one VCALENDAR, found {len(roots)}; use parse_all instead"
        )
    return roots[0]


def _validate_calendar(cal: Component) -> None:
    if cal.get("VERSION") is None:
        raise ValidationError("VCALENDAR is missing the required VERSION property")
    if cal.get("PRODID") is None:
        raise ValidationError("VCALENDAR is missing the required PRODID property")
