"""goals-note-compaction.py: no run.sh cases exist for this hook, so cases
are built inline. This hook has no goals-dir override seam (unlike
goals-recall.py's HC_GOALS_DIR_OVERRIDE) -- it hardcodes $HOME/.claude/goals.
Overriding $HOME itself breaks the hook's `uv run --script` shebang (uv/mise
resolve config off the real HOME), so tests instead use the real
~/.claude/goals directory with a synthetic, collision-proof slug and clean
up the one file they touch.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hook_harness import HookRunner

PY_HOOK = "goals-note-compaction.py"

CWD = "/tmp/zys-goals-compaction-test-only"
SLUG = "-tmp-zys-goals-compaction-test-only"
BODY = "Keep shipping the named ticket."


def _precompact(cwd: str) -> dict:
    return {"cwd": cwd, "hook_event_name": "PreCompact", "trigger": "manual"}


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.fixture
def goals_file():
    goals_dir = Path.home() / ".claude" / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    path = goals_dir / f"{SLUG}.md"
    yield path
    path.unlink(missing_ok=True)


def test_no_goals_file_is_noop(hooks: HookRunner, goals_file) -> None:
    assert not goals_file.exists()
    run = hooks.run_payload(PY_HOOK, _precompact(CWD))
    assert_clean_run(run)
    assert run.stdout == ""
    assert "allow" in run.log


def test_goals_file_gets_marker_prepended(hooks: HookRunner, goals_file) -> None:
    goals_file.write_text(BODY + "\n")

    run = hooks.run_payload(PY_HOOK, _precompact(CWD))

    assert_clean_run(run)
    content = goals_file.read_text()
    assert content.startswith("<!-- compacted: ")
    assert BODY in content
    assert "marked" in run.log


def test_marker_is_replaced_not_stacked(hooks: HookRunner, goals_file) -> None:
    goals_file.write_text(f"<!-- compacted: 1999-01-01T00:00:00Z -->\n{BODY}\n")

    hooks.run_payload(PY_HOOK, _precompact(CWD))

    content = goals_file.read_text()
    assert content.count("<!-- compacted: ") == 1
    assert "1999-01-01T00:00:00Z" not in content


def test_empty_stdin_is_silent(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, "")
    assert_clean_run(run)
    assert run.stdout == ""
