"""Render a parsed Component tree back into RFC 5545 iCalendar text.

Property values on ContentLine are kept in wire form by the parser, so
rendering just needs to re-fold lines and re-quote parameters; it does
not need to re-escape values.
"""

from __future__ import annotations

from .parser import Component, ContentLine

FOLD_LIMIT = 75


def fold_line(line: str, limit: int = FOLD_LIMIT) -> str:
    """Fold a single logical content line to RFC 5545's octet limit.

    Splits are made on UTF-8 byte boundaries without breaking a
    multi-byte character in half. Continuation lines are prefixed with
    a single space, which unfold() strips back off.
    """
    data = line.encode("utf-8")
    if len(data) <= limit:
        return line

    chunks: list[bytes] = []
    start = 0
    first = True
    while start < len(data):
        chunk_limit = limit if first else limit - 1
        end = min(start + chunk_limit, len(data))
        while end > start and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(data[start:end])
        start = end
        first = False

    parts = [chunks[0].decode("utf-8")]
    parts.extend(" " + chunk.decode("utf-8") for chunk in chunks[1:])
    return "\r\n".join(parts)


def escape_text(value: str) -> str:
    """Escape a decoded TEXT value for use as a ContentLine.value."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def unescape_text(value: str) -> str:
    """Decode a TEXT ContentLine.value into its literal string form."""
    out: list[str] = []
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        if ch == "\\" and i + 1 < n:
            nxt = value[i + 1]
            if nxt == "\\":
                out.append("\\")
            elif nxt == ";":
                out.append(";")
            elif nxt == ",":
                out.append(",")
            elif nxt in ("n", "N"):
                out.append("\n")
            else:
                out.append(nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _format_param_value(value: str) -> str:
    if any(ch in value for ch in ':;,"'):
        return f'"{value}"'
    return value


def format_content_line(cl: ContentLine) -> str:
    parts = [f"{cl.group}.{cl.name}" if cl.group else cl.name]
    for pname, values in cl.params.items():
        rendered = ",".join(_format_param_value(v) for v in values)
        parts.append(f";{pname}={rendered}")
    header = "".join(parts)
    return fold_line(f"{header}:{cl.value}")


def _render_component(comp: Component, lines: list[str]) -> None:
    lines.append(f"BEGIN:{comp.name}")
    for prop in comp.properties:
        lines.append(format_content_line(prop))
    for child in comp.children:
        _render_component(child, lines)
    lines.append(f"END:{comp.name}")


def render(component: Component) -> str:
    """Serialize a Component tree to CRLF-terminated iCalendar text."""
    lines: list[str] = []
    _render_component(component, lines)
    return "\r\n".join(lines) + "\r\n"
