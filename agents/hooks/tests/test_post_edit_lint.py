"""post-edit-lint.py: no run.sh cases exist for this hook, so these cover its
branches directly through decide()/build_reason() with a fake LinterRunner
(never a real linter — trunk-adjacent tools have hung this machine before),
plus a handful of subprocess-level contract tests (silent tool, missing
file, skipped path).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
PY_HOOK = "post-edit-lint.py"
HOOK_TIMEOUT_SECS = 30

sys.path.insert(0, str(HOOKS_DIR / "lib"))
from hook_common import HookEvent
from post_edit_lint_linters import LinterRunner, ProcessResult

_spec = importlib.util.spec_from_file_location(
    "post_edit_lint", HOOKS_DIR / "post-edit-lint.py"
)
post_edit_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post_edit_lint)


def FakeLinterRunner(
    available: frozenset[str], outputs: dict[str, str]
) -> LinterRunner:
    """A LinterRunner whose tool availability and output are test-controlled."""

    def which(name: str) -> str | None:
        return f"/fake/bin/{name}" if name in available else None

    def run(argv: list[str]) -> ProcessResult:
        return ProcessResult(stdout=outputs.get(argv[0], ""), returncode=0)

    return LinterRunner(which=which, run=run)


def _event(tool_name: str, file_path: str) -> HookEvent:
    return HookEvent({"tool_name": tool_name, "tool_input": {"file_path": file_path}})


def _write(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content)
    return str(path)


# --- tool/path gating (decide()) --------------------------------------------


def test_non_lintable_tool_is_silent(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "x.go", "package main\n")

    result = post_edit_lint.decide(
        _event("Read", file_path), FakeLinterRunner(frozenset(), {})
    )

    assert result is None


def test_missing_file_is_silent(tmp_path: Path) -> None:
    result = post_edit_lint.decide(
        _event("Write", str(tmp_path / "missing.go")), FakeLinterRunner(frozenset(), {})
    )

    assert result is None


@pytest.mark.parametrize(
    "relative_path",
    [".claude/plans/plan.md", "docs/readme.md", "PLAN.md", "CHANGELOG.md", "LICENSE"],
)
def test_skipped_paths_are_silent(tmp_path: Path, relative_path: str) -> None:
    full = tmp_path / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text("content\n")

    result = post_edit_lint.decide(
        _event("Edit", str(full)), FakeLinterRunner(frozenset(), {})
    )

    assert result is None


def test_clean_file_allows_with_empty_reason(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "clean.py", "x = 1\n")

    result = post_edit_lint.decide(
        _event("Write", file_path), FakeLinterRunner(frozenset({"ruff"}), {"ruff": ""})
    )

    assert result == {"reason": ""}


def test_missing_linter_records_skip_but_still_allows(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "clean.py", "x = 1\n")

    result = post_edit_lint.decide(
        _event("Write", file_path), FakeLinterRunner(frozenset(), {})
    )

    assert result == {"reason": ""}


def test_real_lint_finding_blocks(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "bad.py", "import os\n")
    lint_output = "bad.py:1:1: F401 'os' imported but unused\n"

    result = post_edit_lint.decide(
        _event("Edit", file_path),
        FakeLinterRunner(frozenset({"ruff"}), {"ruff": lint_output}),
    )

    assert result["decision"] == "block"
    assert "F401" in result["reason"]
    assert result["reason"].endswith("Fix these issues before continuing.")


def test_oversized_file_blocks_even_without_a_linter(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "big.py", "x = 1\n" * 260)

    result = post_edit_lint.decide(
        _event("Write", file_path), FakeLinterRunner(frozenset(), {})
    )

    assert result["decision"] == "block"
    assert "FILE SIZE" in result["reason"]


def test_test_file_gets_relaxed_size_limit(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "big_test.py", "x = 1\n" * 260)

    result = post_edit_lint.decide(
        _event("Write", file_path), FakeLinterRunner(frozenset(), {})
    )

    assert result == {"reason": ""}


def test_oversized_function_blocks(tmp_path: Path) -> None:
    body = "func Big() {\n" + "\n".join(f"  x{i} := {i}" for i in range(60)) + "\n}\n"
    file_path = _write(tmp_path, "big.go", body)

    result = post_edit_lint.decide(
        _event("Write", file_path), FakeLinterRunner(frozenset(), {})
    )

    assert result["decision"] == "block"
    assert "FUNCTION SIZE" in result["reason"]


def test_go_lint_skipped_outside_a_module(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "x.go", "package main\n")
    runner = FakeLinterRunner(
        frozenset({"golangci-lint"}), {"go": ""}
    )  # `go env GOMOD` returns ""

    result = post_edit_lint.decide(_event("Write", file_path), runner)

    assert result == {"reason": ""}


# --- subprocess-level contract (stdin -> stdout) ----------------------------


def run_hook(hook: str, payload: dict | str) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [str(HOOKS_DIR / hook)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT_SECS,
        check=False,
    )


def test_hook_silent_for_read_tool() -> None:
    result = run_hook(PY_HOOK, {"tool_name": "Read", "tool_input": {"file_path": "/x"}})

    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_silent_for_malformed_json() -> None:
    result = run_hook(PY_HOOK, "{not json")

    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_clean_edit_allows(tmp_path: Path) -> None:
    file_path = _write(tmp_path, "clean.md", "# hi\n")

    result = run_hook(
        PY_HOOK, {"tool_name": "Write", "tool_input": {"file_path": file_path}}
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"reason": ""}
