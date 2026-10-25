"""waste-census must count omp and Claude Code session JSONL, which carry no `source`/`tool_calls`."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

CENSUS = Path(__file__).resolve().parents[1] / "waste-census.py"
spec = importlib.util.spec_from_file_location("waste_census", CENSUS)
census_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census_mod)


def msg(role: str, *parts: dict, **extra: object) -> dict:
    return {"type": "message", "message": {"role": role, "content": list(parts), **extra}}


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def call(name: str, **arguments: object) -> dict:
    return {"type": "toolCall", "id": "c", "name": name, "arguments": arguments}


def result(tool: str, body: str, error: bool = True) -> dict:
    return msg("toolResult", text(body), toolName=tool, isError=error)


def write_session(path: Path, entries: list[dict]) -> Path:
    header = [{"type": "title", "title": "t"}, {"type": "session", "version": 3}]
    path.write_text("\n".join(json.dumps(e) for e in header + entries) + "\n")
    return path


def run(path: Path) -> dict[str, list[str]]:
    return census_mod.census(census_mod.load(path))


def test_omp_errors_and_user_corrections_are_counted_with_line_refs(tmp_path: Path) -> None:
    path = write_session(
        tmp_path / "s.jsonl",
        [
            msg("user", text("HOW MANY TIMES DO I HAVE TO SAY RUN IT THRU MASTRA")),
            msg("assistant", call("bash", command="ls")),
            result("bash", "Bash is disabled; use run_command."),
        ],
    )
    found = run(path)
    assert found["user_recovery"] == ["item:3"]  # raw JSONL line numbers, headers included
    assert found["tool_error"] == ["item:5 (bash)"]


def test_a_denied_device_is_repeat_denied_but_other_devices_on_the_same_tool_are_not(
    tmp_path: Path,
) -> None:
    path = write_session(
        tmp_path / "s.jsonl",
        [
            msg("assistant", call("write", path="xd://missing", content="{}")),
            result("write", "No such tool: xd://missing. Mounted devices: a, b"),
            msg("assistant", call("write", path="xd://present", content="{}")),
            msg("assistant", call("write", path="xd://missing", content="{}")),
        ],
    )
    assert run(path)["repeat_denied_tool"] == ["item:6 (write)"]


def test_results_the_harness_skipped_are_not_tool_errors(tmp_path: Path) -> None:
    path = write_session(
        tmp_path / "s.jsonl",
        [result("wait", "Skipped due to queued user message. Do not count this.")],
    )
    assert "tool_error" not in run(path)


def test_identical_repeated_call_is_a_duplicate(tmp_path: Path) -> None:
    path = write_session(
        tmp_path / "s.jsonl",
        [msg("assistant", call("read", path="a")), msg("assistant", call("read", path="a"))],
    )
    assert run(path)["duplicate_call"] == ["item:4 (read)"]


def claude_line(kind: str, content: object, **extra: object) -> dict:
    return {"type": kind, "message": {"role": kind, "content": content}, **extra}


def write_claude(path: Path, entries: list[dict]) -> Path:
    head = [{"type": "queue-operation"}, {"type": "last-prompt"}]
    path.write_text("\n".join(json.dumps(e) for e in head + entries) + "\n")
    return path


def test_claude_results_take_their_tool_name_from_the_matching_tool_use(tmp_path: Path) -> None:
    path = write_claude(
        tmp_path / "c.jsonl",
        [
            claude_line(
                "assistant",
                [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"c": "ls"}}],
            ),
            claude_line(
                "user",
                [{"type": "tool_result", "tool_use_id": "t1", "content": "boom", "is_error": True}],
            ),
        ],
    )
    assert run(path)["tool_error"] == ["item:4 (Bash)"]


def test_claude_user_corrections_count_but_injected_and_sidechain_text_does_not(
    tmp_path: Path,
) -> None:
    path = write_claude(
        tmp_path / "c.jsonl",
        [
            claude_line("user", "how many times do i have to say it"),
            claude_line("user", "<system-reminder>i already told you</system-reminder>"),
            claude_line("user", "This session is being continued: i told you so"),
            claude_line("user", "i told you", isSidechain=True),
        ],
    )
    assert run(path)["user_recovery"] == ["item:3"]


def test_repeated_wait_is_polling_not_a_duplicate(tmp_path: Path) -> None:
    path = write_session(
        tmp_path / "s.jsonl",
        [msg("assistant", call("wait", ms=1)), msg("assistant", call("wait", ms=1))],
    )
    assert "duplicate_call" not in run(path)


def test_successful_output_that_starts_with_error_is_not_a_tool_error(tmp_path: Path) -> None:
    path = write_session(
        tmp_path / "s.jsonl",
        [
            result(
                "bash",
                "error: failed to push some refs (reported by a script that exited 0)",
                error=False,
            )
        ],
    )
    assert "tool_error" not in run(path)
