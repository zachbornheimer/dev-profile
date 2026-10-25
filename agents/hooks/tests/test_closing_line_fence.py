"""ZYS-1230: closing_line must not quote a bare markdown fence."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_turn_judge import _is_fence_only, closing_line


def test_fence_only_lines():
    assert _is_fence_only("```")
    assert _is_fence_only("```json")
    assert _is_fence_only("```evidence")
    assert not _is_fence_only("``` not a fence info with spaces")
    assert not _is_fence_only("code with ``` inside")


def test_closing_line_skips_trailing_fence():
    msg = (
        "identify_intent returns build. Run these from the worktree:\n"
        "\n"
        "```\n"
        'go run ./cmd/agentmux capability run identify_intent --text "x"\n'
        "```\n"
    )
    got = closing_line(msg)
    assert got != "```"
    assert "go run" in got


def test_closing_line_skips_json_fence_closer():
    msg = 'Posted.\n\n```json\n{"ok":true}\n```'
    assert closing_line(msg) == '{"ok":true}'


def test_closing_line_empty_when_only_fences():
    assert closing_line("```\n```") == ""
