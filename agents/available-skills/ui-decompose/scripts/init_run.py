#!/usr/bin/env python3
"""Create a collision-resistant working directory for one ui-decompose run."""

from __future__ import annotations

import argparse
import secrets
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Create the run directory and print its absolute path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    root = project_dir / ".ui-decompose"
    root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(16):
        candidate = root / f"run-{stamp}-{secrets.token_hex(3)}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        print(candidate)
        return 0

    raise SystemExit("could not allocate a unique ui-decompose run directory")


if __name__ == "__main__":
    raise SystemExit(main())
