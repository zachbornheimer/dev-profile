#!/usr/bin/env python3
"""Check image links in a Markdown file. Usage: check_links.py tutorial.md [--prune]

Exits 1 if any linked image is missing. --prune deletes image files in the
linked directories that the Markdown does not reference.
"""

import pathlib
import re
import sys


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--prune"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    md = pathlib.Path(args[0])
    root = md.parent
    refs = set(re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", md.read_text()))
    local = {r for r in refs if not re.match(r"[a-z]+:", r)}
    missing = sorted(r for r in local if not (root / r).exists())
    pruned = 0
    if "--prune" in sys.argv:
        dirs = {(root / r).parent for r in local}
        keep = {(root / r).resolve() for r in local}
        for d in dirs:
            for p in d.iterdir():
                if (
                    p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                    and p.resolve() not in keep
                ):
                    p.unlink()
                    pruned += 1
    print(
        f"{len(local)} image links, {len(missing)} missing, {pruned} unused files pruned"
    )
    for r in missing:
        print(f"missing: {r}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
