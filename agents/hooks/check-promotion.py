#!/usr/bin/env python3
"""Reject a promotion whose mechanism already exists.

AGENTS.md's promotion gate (line 403) says one entry per distinct mechanism.
Nothing enforced it, so 17 entries restated 4 mechanisms and the section grew
while behavior did not. Run this with the proposed skill or instruction name
before writing either one.

    check-promotion.py tool-denial-recovery     -> exit 1, names the collision
    check-promotion.py cache-hit-telemetry      -> exit 0, new mechanism

exit 0 new, 1 duplicate, 2 unusable input. Overlapping tokens are reported so a
human can overrule a false positive; the gate refuses, it does not decide.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKILLS = Path.home() / ".agents" / "available-skills"

# Words that carry no mechanism: every skill name has some of these.
GENERIC = frozenset(
    {
        "skill",
        "skills",
        "tool",
        "tools",
        "recovery",
        "the",
        "and",
        "or",
        "for",
        "of",
        "a",
    }
)

TOKEN = re.compile(r"[a-z0-9]+")


def mechanism_words(name: str) -> frozenset[str]:
    """The tokens of a promotion name that name a mechanism rather than a category."""
    return frozenset(TOKEN.findall(name.lower())) - GENERIC


def existing_skill_words() -> dict[frozenset[str], Path]:
    return {
        words: path
        for path in SKILLS.glob("*/SKILL.md")
        if (words := mechanism_words(path.parent.name))
    }


def find_collision(proposed: str) -> tuple[frozenset[str], Path] | None:
    """The existing skill that already owns this mechanism, or None.

    The single owner of the mechanism-word rule: the CLI below and
    hooks/promotion-gate.py both call it, so a skill cannot slip past one
    gate by being written through the other.
    """
    words = mechanism_words(proposed)
    if not words:
        return None
    for other, path in existing_skill_words().items():
        shared = words & other
        if shared:
            return shared, path
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print(__doc__.strip().splitlines()[7], file=sys.stderr)
        return 2

    proposed = argv[1].strip()
    words = mechanism_words(proposed)
    if not words:
        print(
            f"{proposed}: every word is generic, so it names no mechanism",
            file=sys.stderr,
        )
        return 2

    collision = find_collision(proposed)
    if collision is not None:
        shared, path = collision
        print(f"duplicate of skill '{path.parent.name}' on {sorted(shared)}: {path}")
        return 1

    print(f"new: no existing skill names {sorted(words)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
