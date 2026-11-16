"""closing_line is the last line of prose: a fenced block or <evidence-check> element is never quoted as the close."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_turn_judge import CLOSING_LINE_CHARS, closing_line


def test_trailing_evidence_element_yields_the_prose_before_it():
    msg = "Both suites pass.\n\n<evidence-check>\n<claim>x</claim>\n<type>test</type>\n<ref>y</ref>\n<scope>unit</scope>\n</evidence-check>\n"
    assert closing_line(msg) == "Both suites pass."


def test_prose_after_a_fence_is_the_close():
    msg = "The work is done.\n\n<evidence-check>\n<claim>x</claim>\n</evidence-check>\nI also verified it."
    assert closing_line(msg) == "I also verified it."


def test_a_command_fence_is_not_quoted():
    msg = "Run this from the worktree:\n\n```\nmise run test\n```\n"
    assert closing_line(msg) == "Run this from the worktree:"


def test_message_of_only_fences_has_no_closing_line():
    assert closing_line("```\n```") == ""


def test_long_closing_line_is_truncated():
    assert len(closing_line("x" * (CLOSING_LINE_CHARS + 50))) == CLOSING_LINE_CHARS + 1


def test_trailing_happiness_element_yields_the_prose_before_it():
    msg = (
        "Both suites pass.\n\n"
        '<happiness-check checksum="abc">\n<happy>true</happy>\n'
        "<explanation>\nYes, done.\n</explanation>\n</happiness-check>\n"
    )
    assert closing_line(msg) == "Both suites pass."


def test_unclosed_happiness_element_is_not_the_close():
    msg = 'Done.\n\n<happiness-check checksum="abc">\n<happy>true</happy>\nYes, still writing'
    assert closing_line(msg) == "Done."
