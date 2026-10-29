"""Tests for the ~/.cursor/hooks/*.py wrappers.

These live beside ~/.agents/hooks/tests (not under ~/.cursor/hooks) per the
work order's allowed_writes; they invoke the Cursor wrappers by absolute
path as subprocesses, the same way Cursor's hooks.json does.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

CURSOR_HOOKS_DIR = Path.home() / ".cursor" / "hooks"
RUN_TIMEOUT_SECS = 30


def _run(
    hook: str,
    stdin: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
):
    return subprocess.run(
        [str(CURSOR_HOOKS_DIR / hook), *(args or [])],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=RUN_TIMEOUT_SECS,
        check=False,
    )


# --- skill-lint-stop.py: side-effect only, always emits {} -------------------


def test_skill_lint_stop_emits_empty_object() -> None:
    result = subprocess.run(
        [str(CURSOR_HOOKS_DIR / "skill-lint-stop.py")],
        input=json.dumps({"status": "ok", "loop_count": 1}),
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECS,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


# --- post-edit-lint-cursor.py: payload translation + verdict mapping ---------


def _fake_post_edit_lint_hook(tmp_path: Path, response: dict) -> Path:
    hook = tmp_path / "fake-post-edit-lint"
    hook.write_text(
        f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{json.dumps(response)}'\n"
    )
    hook.chmod(0o755)
    return hook


def test_post_edit_lint_cursor_passes_through_when_no_findings(tmp_path: Path) -> None:
    hook = _fake_post_edit_lint_hook(tmp_path, {"decision": "allow"})
    payload = json.dumps({"tool_input": {"file_path": "/tmp/x.go"}})

    result = _run(
        "post-edit-lint-cursor.py",
        stdin=payload,
        env={"POST_EDIT_LINT_HOOK": str(hook)},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


def test_post_edit_lint_cursor_surfaces_block_reason(tmp_path: Path) -> None:
    hook = _fake_post_edit_lint_hook(
        tmp_path, {"decision": "block", "reason": "line too long"}
    )
    payload = json.dumps({"tool_input": {"path": "/tmp/x.go"}})

    result = _run(
        "post-edit-lint-cursor.py",
        stdin=payload,
        env={"POST_EDIT_LINT_HOOK": str(hook)},
    )

    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert "line too long" in body["additional_context"]


def test_post_edit_lint_cursor_missing_shared_hook_fails_open(tmp_path: Path) -> None:
    payload = json.dumps({"tool_input": {"file_path": "/tmp/x.go"}})
    result = _run(
        "post-edit-lint-cursor.py",
        stdin=payload,
        env={"POST_EDIT_LINT_HOOK": str(tmp_path / "missing")},
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


def test_post_edit_lint_cursor_no_file_path_fails_open(tmp_path: Path) -> None:
    hook = _fake_post_edit_lint_hook(tmp_path, {"decision": "allow"})
    result = _run(
        "post-edit-lint-cursor.py",
        stdin=json.dumps({}),
        env={"POST_EDIT_LINT_HOOK": str(hook)},
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


# --- quality-guard-pretool.py: payload translation + permission mapping ------


def _fake_quality_guard_bin(tmp_path: Path, exit_code: int, stdout: str) -> Path:
    binary = tmp_path / "quality-guard"
    binary.write_text(
        f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{stdout}'\nexit {exit_code}\n"
    )
    binary.chmod(0o755)
    return binary


def test_quality_guard_pretool_allows_when_binary_allows(tmp_path: Path) -> None:
    binary = _fake_quality_guard_bin(tmp_path, 0, json.dumps({"decision": "allow"}))
    payload = json.dumps(
        {
            "tool_name": "Edit",
            "tool_input": {"path": "/tmp/x.go", "contents": "package x"},
        }
    )

    result = _run(
        "quality-guard-pretool.py",
        stdin=payload,
        args=["--mode=fast"],
        env={"QUALITY_GUARD_BIN": str(binary)},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"permission": "allow"}


def test_quality_guard_pretool_denies_on_exit_code_2(tmp_path: Path) -> None:
    binary = _fake_quality_guard_bin(
        tmp_path, 2, json.dumps({"reason": "magic number"})
    )
    payload = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"path": "/tmp/x.go", "contents": "package x"},
        }
    )

    result = _run(
        "quality-guard-pretool.py",
        stdin=payload,
        args=["--mode=pretool-review"],
        env={"QUALITY_GUARD_BIN": str(binary)},
    )

    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body["permission"] == "deny"
    assert "magic number" in body["agent_message"]


def test_quality_guard_pretool_missing_binary_fails_open(tmp_path: Path) -> None:
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"path": "/tmp/x.go"}})
    result = _run(
        "quality-guard-pretool.py",
        stdin=payload,
        env={"QUALITY_GUARD_BIN": str(tmp_path / "missing")},
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"permission": "allow"}
