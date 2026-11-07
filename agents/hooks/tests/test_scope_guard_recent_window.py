"""The recent-window transcript read must decide exactly what the whole-tail read does.

``scope_decide._observe`` routes every judgment through
``read_recent_facts`` — a fold from the ``RECENT_PROMPTS``-th-newest
prompt-shaped row — except ``mise run ci`` candidates, which keep
``read_transcript_facts`` because ``prohibited_full_ci`` consults prompts
older than any window. These tests pin the equivalence the guard relies on:
the window read yields the same consumer-visible facts (the task's prompts,
the judge's context prompts, ``since_iso``) and the same current-turn runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import pytest
from completion_gate_transcript import (
    PROMPTS_KEPT as TRANSCRIPT_PROMPTS_KEPT,
)
from completion_gate_transcript import (
    read_recent_facts,
    read_transcript_facts,
)
from scope_decide import (
    PROMPTS_KEPT,
    RECENT_PROMPTS,
    RUNS_KEPT,
    TASK_PROMPTS,
)

ATTRIBUTIONS = frozenset({"user", "agent"})


def _row(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def write_session(path: Path, prompts: list[str], echo_marks: str | None = None) -> str:
    """An omp session log: one tool run per turn, then a current turn after the last ask.

    ``echo_marks`` adds a tool result whose content carries the window scan's
    raw byte marks, the shape a transcript gets when it quotes a prompt back.
    """
    rows = [_row({"type": "session", "id": "s-window"})]
    for index, prompt in enumerate(prompts):
        rows.append(
            _row(
                {
                    "type": "message",
                    "timestamp": f"2026-11-02T10:{index:02d}:00Z",
                    "message": {
                        "role": "user",
                        "content": prompt,
                        "attribution": "user",
                    },
                }
            )
        )
        command = f"run-{index}"
        call_id = f"c{index}"
        rows.append(
            _row(
                {
                    "type": "message",
                    "timestamp": f"2026-11-02T10:{index:02d}:30Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "On it."},
                            {
                                "type": "toolCall",
                                "id": call_id,
                                "name": "bash",
                                "arguments": {"command": command},
                            },
                        ],
                    },
                }
            )
        )
        content = echo_marks if (echo_marks and index == 0) else f"ok {index}"
        rows.append(
            _row(
                {
                    "type": "message",
                    "timestamp": f"2026-11-02T10:{index:02d}:31Z",
                    "message": {
                        "role": "toolResult",
                        "toolCallId": call_id,
                        "content": content,
                        "isError": False,
                    },
                }
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


def consumed(facts) -> dict:
    """Exactly what ``scope_decide`` consumes: ``_task_of``'s and ``_context``'s slices."""
    prompts = [item.text for item in facts.prompts if item.text.strip()]
    return {
        "user_prompt": facts.user_prompt,
        "task_prompts": prompts[-TASK_PROMPTS:],
        "context_prompts": prompts[:-1][-PROMPTS_KEPT:],
        "since_iso": str(facts.prompts[-1].at or "") if facts.prompts else "",
        "turn_runs": [
            (run.tool, run.command, run.failed, (run.output or "").strip())
            for run in facts.turn_runs[-RUNS_KEPT:]
        ],
    }


@pytest.mark.parametrize(
    ("prompts", "echo_marks"),
    [
        ([f"ask {index}" for index in range(12)], None),
        ([f"ask {index}" for index in range(3)], None),
        ([f"ask {index}" for index in range(30)], None),
        (
            [f"ask {index}" for index in range(12)],
            'quoted {"role":"user", "attribution":"user"} back',
        ),
    ],
)
def test_the_window_holds_what_a_judgment_consumes(
    tmp_path: Path, prompts: list[str], echo_marks: str | None
) -> None:
    """``read_recent_facts`` must show every prompt and run a judgment consumes.

    With fewer real prompts in the log than the window asks for, the read
    falls back to the whole tail, so the facts are the full read's facts.
    """
    path = tmp_path / "session.jsonl"
    write_session(path, prompts, echo_marks)
    full = read_transcript_facts(str(path), ATTRIBUTIONS)
    window = read_recent_facts(str(path), ATTRIBUTIONS, RECENT_PROMPTS)
    assert full is not None
    assert window is not None
    assert consumed(window) == consumed(full)
    # The fold's own keeps: identical newest prompt and current-turn runs.
    assert window.user_prompt == full.user_prompt
    assert window.turn_runs == full.turn_runs


def test_a_short_log_falls_back_to_the_full_facts(tmp_path: Path) -> None:
    """Under ``RECENT_PROMPTS`` real prompts the fold comes up short and re-reads the tail."""
    path = tmp_path / "session.jsonl"
    write_session(path, ["only ask"])
    full = read_transcript_facts(str(path), ATTRIBUTIONS)
    window = read_recent_facts(str(path), ATTRIBUTIONS, RECENT_PROMPTS)
    assert full is not None
    assert window is not None
    # The fallback is the whole-tail read, so history and every prompt survive.
    assert window == full


def test_a_split_first_tail_line_is_never_counted_as_a_prompt(tmp_path: Path) -> None:
    """A prompt row straddling the tail boundary is dropped by both reads.

    ``_recent_window_start`` skips the partial first line at ``tail_start``
    and counts candidates after it; a window that lands mid-row still folds
    every complete row, and no partial row can fake a candidate.
    """
    path = tmp_path / "session.jsonl"
    write_session(path, [f"ask {index}" for index in range(12)])
    lines = path.read_text(encoding="utf-8").splitlines()
    # Split the third prompt's row in two at a byte boundary inside its text.
    split_at = lines[4].index("ask")
    head, tail = lines[4][:split_at], lines[4][split_at:]
    rows = lines[:4] + [head, tail] + lines[5:]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    full = read_transcript_facts(str(path), ATTRIBUTIONS)
    window = read_recent_facts(str(path), ATTRIBUTIONS, RECENT_PROMPTS)
    assert full is not None
    assert window is not None
    assert consumed(window) == consumed(full)


def test_the_window_covers_every_prompt_a_judgment_slices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window must reach the oldest prompt the judge's context still shows.

    ``RECENT_PROMPTS`` is derived from ``TASK_PROMPTS`` and ``PROMPTS_KEPT``;
    if a future edit widens either consumer, the window must grow with it or
    the guard would judge against a truncated history.
    """
    assert max(TASK_PROMPTS, PROMPTS_KEPT + 1) <= RECENT_PROMPTS
    assert PROMPTS_KEPT < TRANSCRIPT_PROMPTS_KEPT
    path = tmp_path / "session.jsonl"
    write_session(path, [f"ask {index}" for index in range(RECENT_PROMPTS)])
    window = read_recent_facts(str(path), ATTRIBUTIONS, RECENT_PROMPTS)
    full = read_transcript_facts(str(path), ATTRIBUTIONS)
    assert window is not None
    assert full is not None
    assert len(window.prompts) == RECENT_PROMPTS
    assert consumed(window) == consumed(full)


def test_prompt_attributions_still_select_real_asks(tmp_path: Path) -> None:
    """Only attributed user rows count, so the window never trades an ask away.

    The byte scan finds candidate rows anywhere in the tail, but the fold
    keeps only what ``PROMPT_ATTRIBUTIONS`` recognizes; unattributed user
    rows never reach a judgment in either read.
    """
    path = tmp_path / "session.jsonl"
    write_session(path, [f"ask {index}" for index in range(12)])
    lines = path.read_text(encoding="utf-8").splitlines()
    unattributed = _row(
        {
            "type": "message",
            "timestamp": "2026-11-02T09:00:00Z",
            "message": {"role": "user", "content": "not a real ask"},
        }
    )
    rows = [lines[0], unattributed] + lines[1:]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    full = read_transcript_facts(str(path), ATTRIBUTIONS)
    window = read_recent_facts(str(path), ATTRIBUTIONS, RECENT_PROMPTS)
    assert full is not None
    assert window is not None
    assert consumed(window) == consumed(full)
    assert "not a real ask" not in [item.text for item in window.prompts]
