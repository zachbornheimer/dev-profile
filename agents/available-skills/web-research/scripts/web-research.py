#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Route a web-research ask, and reject quotes that are not in the page.

The model defaults to a report, a clarifying question, or a made-up quote.
This script decides depth, whether to act or stop, and whether a quote is real.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

_DEEP = re.compile(
    r"\bdeep research\b|\bdeep web research\b|\bextensive research\b|\bsynthesize\b|\b10 options\b",
    re.IGNORECASE,
)
_DISCUSS = re.compile(
    r"then we should discuss|we should discuss|let'?s discuss|let us discuss|\bbrainstorm\b",
    re.IGNORECASE,
)
_ACT = re.compile(
    r"\bset it up\b|\bset this up\b|\bmigrate\b|\bcommit\b|\bopen a pr\b|"
    r"\bimplement\b|\bfix it\b|\bland it\b|\bupdate the\b|\bupdate it\b|"
    r"\bcontinue the implementation\b|\bwrite it\b|\bdo it\b",
    re.IGNORECASE,
)
_DEICTIC = re.compile(
    r"\bon this\b|\bonthis\b|\bresearch this\b|\bresearch it\b|\bdo the research\b|"
    r"\bthe notes\b|\bi don't think you're right\b|\bare you sure\b",
    re.IGNORECASE,
)
_OBJECTLESS = re.compile(
    r"(?:do|please do|can you do)(?: some| a bit more)? web research(?: please)?[.?!]?$",
    re.IGNORECASE,
)
_PATH = re.compile(r"~/|https?://|/Users/|\.md\b")
_CHALLENGE = re.compile(
    r"\bi don't think you're right\b|\bare you sure\b|\bthose notes are true\b|"
    r"\bi don't know if those notes\b",
    re.IGNORECASE,
)
_THIS_YEAR = re.compile(
    r"\bbest practices?\b|\bknown issue\b|\bcurrent\b|\blatest\b|\bofficial\b",
    re.IGNORECASE,
)
_SUBAGENT = re.compile(r"\bsubagents?\b", re.IGNORECASE)
_ONE_SUBAGENT = re.compile(r"\b(?:a|one) subagent\b", re.IGNORECASE)
_CHEAP = re.compile(r"\bcheaper model\b|\bcheap model\b|\bcheaper\b", re.IGNORECASE)
_PARENT = re.compile(
    r"instead of waiting|continue the implementation|while we wait",
    re.IGNORECASE,
)
_WRITE = re.compile(
    r"~/Downloads/|write (?:a |the )?(?:report|brief|file)\b", re.IGNORECASE
)
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_FLOOR = re.compile(
    r"(?:since|from|after)\s+(?:(?P<mon1>[A-Za-z]+)\s+)?(?P<year1>20\d{2})"
    r"|(?P<mon2>[A-Za-z]+)\s+(?P<year2>20\d{2})\s+and newer"
    r"|(?P<year3>20\d{2})\s+and newer",
    re.IGNORECASE,
)
_MIN_QUOTE = 24


@dataclass(frozen=True)
class Route:
    """Binding route for one user message. The skill obeys this, it does not renegotiate it."""

    depth: str
    after: str
    bind: str
    workers: int
    cheap_model: bool
    write_file: bool
    parent_continues: bool
    challenge: bool
    recency: str
    not_before: str | None


def route_message(text: str, today: date) -> Route:
    """Classify one user message. Empty input is a caller error."""

    if not text.strip():
        raise ValueError("route needs the user message")
    depth = "deep" if _DEEP.search(text) else "quick"
    if _DISCUSS.search(text):
        after = "discuss"
    elif _ACT.search(text):
        after = "act"
    else:
        after = "answer"
    has_path = _PATH.search(text) is not None
    bind = (
        "thread"
        if not has_path and (_DEICTIC.search(text) or _OBJECTLESS.search(text.strip()))
        else "stated"
    )
    if _ONE_SUBAGENT.search(text):
        workers = 1
    elif _SUBAGENT.search(text):
        workers = 3 if depth == "deep" else 1
    elif depth == "deep":
        workers = 3
    else:
        workers = 0
    floor = _floor(text)
    challenge = _CHALLENGE.search(text) is not None
    this_year = challenge or _THIS_YEAR.search(text) is not None
    if floor is None and this_year:
        floor = date(today.year, 1, 1)
    if floor is None:
        recency = "any"
        not_before = None
    elif floor == date(today.year, 1, 1) and this_year:
        recency = "this-year"
        not_before = floor.isoformat()
    else:
        recency = "dated"
        not_before = floor.isoformat()
    write_file = depth == "deep" or _WRITE.search(text) is not None
    parent_continues = (
        workers >= 1
        and after != "discuss"
        and (after == "act" or _PARENT.search(text) is not None)
    )
    return Route(
        depth=depth,
        after=after,
        bind=bind,
        workers=workers,
        cheap_model=_CHEAP.search(text) is not None,
        write_file=write_file,
        parent_continues=parent_continues,
        challenge=challenge,
        recency=recency,
        not_before=not_before,
    )


def _floor(text: str) -> date | None:
    match = _FLOOR.search(text)
    if match is None:
        return None
    year = int(match.group("year1") or match.group("year2") or match.group("year3"))
    month_name = (match.group("mon1") or match.group("mon2") or "").lower()
    month = _MONTHS.get(month_name, 1)
    return date(year, month, 1)


def quote_in_page(quote: str, page: str) -> str | None:
    """Return a reject reason, or None when the quote is a real span of the page."""

    collapsed = _collapse(quote)
    if len(collapsed) < _MIN_QUOTE:
        return f"quote shorter than {_MIN_QUOTE} characters"
    if collapsed not in _collapse(page):
        return "quote is not in the page"
    return None


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _read_message(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    return sys.stdin.read()


def _cmd_route(args: argparse.Namespace) -> int:
    today = (
        date.fromisoformat(args.today)
        if args.today
        else datetime.now().astimezone().date()
    )
    try:
        decided = route_message(_read_message(args), today)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(asdict(decided), indent=2))
    return 0


def _cmd_quote(args: argparse.Namespace) -> int:
    page = Path(args.from_path).read_text(encoding="utf-8")
    reason = quote_in_page(args.text, page)
    if reason is None:
        print("ok")
        return 0
    print(reason, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Route a web-research ask or check a quote."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    route = sub.add_parser("route")
    route.add_argument("--text", default=None)
    route.add_argument("--today", default=None)
    route.set_defaults(func=_cmd_route)
    quote = sub.add_parser("quote")
    quote.add_argument("--text", required=True)
    quote.add_argument("--from", dest="from_path", required=True)
    quote.set_defaults(func=_cmd_quote)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
