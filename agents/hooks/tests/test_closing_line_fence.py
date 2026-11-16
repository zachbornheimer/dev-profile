"""closing_line is the last line of prose: a fenced block (evidence, JSON, commands) is never quoted as the close."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_turn_judge import CLOSING_LINE_CHARS, closing_line


def test_trailing_evidence_fence_yields_the_prose_before_it():
    msg = 'Both suites pass.\n\n```evidence\n{"claim":"x","type":"test","ref":"y","scope":"unit"}\n```\n'
    assert closing_line(msg) == "Both suites pass."


def test_prose_after_a_fence_is_the_close():
    msg = 'The work is done.\n\n```evidence\n{"claim":"x"}\n```\nI also verified it.'
    assert closing_line(msg) == "I also verified it."


def test_a_command_fence_is_not_quoted():
    msg = "Run this from the worktree:\n\n```\nmise run test\n```\n"
    assert closing_line(msg) == "Run this from the worktree:"


def test_message_of_only_fences_has_no_closing_line():
    assert closing_line("```\n```") == ""


def test_long_closing_line_is_truncated():
    assert len(closing_line("x" * (CLOSING_LINE_CHARS + 50))) == CLOSING_LINE_CHARS + 1
