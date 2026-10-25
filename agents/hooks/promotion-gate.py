#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Write|Edit) — a skill whose mechanism already exists is denied.

AGENTS.md's promotion gate (the "Promoted changes" section) is prose: it says
one entry per distinct mechanism and tells the reader to run
check-promotion.py first. Nothing ran it, so a learning cycle appended a
thirteenth restatement of a lesson that was already wired twice.

This hook is the enforcement. On a write that creates a SKILL.md under a
skills directory, it takes the proposed skill's directory name and asks
check-promotion.py's find_collision — the single owner of the mechanism-word
rule — whether an existing skill already names that mechanism. A collision
denies the write and names the existing skill.

Deliberately narrow:

- Only a skill directory name is judged. Editing an existing SKILL.md body, or
  any other file, passes; the gate is about new mechanisms, not prose.
- A directory that already has a SKILL.md passes: that is an edit to an
  existing mechanism, already counted once.
- Any unusable input, missing script, or exception passes. on_failure is not
  set to block, so a broken gate cannot wedge every write.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "promotion-gate"
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
SKILLS_ROOTS = tuple(
    Path.home() / ".agents" / name for name in ("skills", "available-skills")
)
SKILL_FILENAME = "SKILL.md"


def skills_root_of(target: Path) -> Path | None:
    """The skills directory ``target`` sits under, one level deep, or None."""
    for root in SKILLS_ROOTS:
        try:
            relative = target.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) == 2 and relative.name == SKILL_FILENAME:
            return root
    return None


def find_collision(proposed: str):
    """The existing skill that already owns this mechanism, or None.

    ``check-promotion.py`` cannot be imported by name (the hyphen), yet it is
    the single owner of the mechanism-word rule — duplicating that rule here
    would let one gate drift from the other. Load it by path instead.
    """
    import importlib.util

    script = Path(__file__).resolve().parent / "check-promotion.py"
    spec = importlib.util.spec_from_file_location("check_promotion", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.find_collision(proposed)


def decide(event: HookEvent):
    if event.tool_name not in WRITE_TOOLS:
        return None

    raw_path = event.tool_input("file_path")
    if not raw_path:
        return None
    target = Path(raw_path).expanduser()
    if target.name != SKILL_FILENAME:
        return None

    root = skills_root_of(target)
    if root is None:
        return None

    # An existing skill is being edited; its mechanism is already counted.
    if target.exists():
        return None

    proposed = target.parent.name
    collision = find_collision(proposed)
    if collision is None:
        return None

    shared, owner = collision
    return Decision.deny(
        f"Promotion gate: '{proposed}' restates the mechanism of existing skill "
        f"'{owner.parent.name}' (shared: {', '.join(sorted(shared))}). "
        f"AGENTS.md's promotion gate keeps one entry per distinct mechanism. "
        f"Either edit {owner} to carry the new detail, or name a mechanism that "
        f"no skill owns. Do not append a second copy."
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
