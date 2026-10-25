from __future__ import annotations

import argparse
from pathlib import Path

from .inspect import read_report, summarize_report
from .protocol import new_run_id
from .scaffold import create_runner


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ccc")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("new-uuid", help="print a fresh UUID v4")

    scaffold = sub.add_parser("scaffold", help="create a fresh standalone runner")
    scaffold.add_argument(
        "--dir",
        type=Path,
        default=Path.cwd(),
        help="output directory (default: current directory)",
    )

    inspect = sub.add_parser("inspect", help="print the report from an evidence ZIP")
    inspect.add_argument("zip", type=Path)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "new-uuid":
        print(new_run_id())
        return 0

    if args.command == "scaffold":
        args.dir.mkdir(parents=True, exist_ok=True)
        path = create_runner(args.dir)
        print(path)
        return 0

    if args.command == "inspect":
        report = read_report(args.zip)
        print(summarize_report(report))
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
