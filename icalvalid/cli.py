"""Command-line interface: validate or pretty-print an ICS file.

Kept separate from __main__.py so `python -m icalvalid` and the
installed `icalvalid` console script share the same entry point.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .parser import ICalError, parse_all
from .printer import render


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path: str, text: str) -> None:
    if path == "-":
        sys.stdout.write(text)
        return
    # newline="" so the CRLF render() already produced isn't translated
    # into CRCRLF on platforms that rewrite "\n" to os.linesep.
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        calendars = parse_all(_read(args.file))
    except ICalError as exc:
        print(f"{args.file}: {exc}", file=sys.stderr)
        return 1
    noun = "calendar" if len(calendars) == 1 else "calendars"
    print(f"{args.file}: ok ({len(calendars)} {noun})")
    return 0


def _cmd_print(args: argparse.Namespace) -> int:
    try:
        calendars = parse_all(_read(args.file))
    except ICalError as exc:
        print(f"{args.file}: {exc}", file=sys.stderr)
        return 1
    _write(args.output, "".join(render(cal) for cal in calendars))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="icalvalid", description="Validate or pretty-print an ICS file."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate", help="check an ICS file against the RFC 5545 structural rules"
    )
    validate.add_argument("file", help='path to an .ics file, or "-" for stdin')
    validate.set_defaults(func=_cmd_validate)

    pretty = sub.add_parser(
        "print", help="re-print an ICS file with normalized folding and quoting"
    )
    pretty.add_argument("file", help='path to an .ics file, or "-" for stdin')
    pretty.add_argument(
        "-o", "--output", default="-", help="where to write the result (default: stdout)"
    )
    pretty.set_defaults(func=_cmd_print)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
