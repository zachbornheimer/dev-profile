#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PostToolUse hook for Edit/Write — runs a language-appropriate linter and
file-structure checks. Output goes to stdout as context for Claude: a real
finding blocks (Claude must fix it before continuing), nothing found allows
with an empty reason.

Unlike the run_hook-based Pre/Stop hooks, this hook was never built on
hook-common.sh: it logs nothing on success, and its own JSON shapes
({"decision":"block",...} / {"reason":""}) aren't the PreToolUse
permissionDecision shape. The port keeps that contract exactly, under
run_fail_open: a crash or a stuck stdin is logged fail-open and exits 0.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import post_edit_lint_linters as linters
from hook_common import GIT, HookEvent, HookSettings, read_stdin, run_fail_open
from post_edit_lint_limits import (
    SizeLimits,
    file_extension,
    file_size_finding,
    function_size_finding,
)
from post_edit_lint_linters import LinterRunner, strip_clean_output

HOOK_NAME = "post-edit-lint"
LINTABLE_TOOL_NAMES = frozenset(
    {"Edit", "Write", "search_replace", "write", "MultiEdit", "Update"}
)
FIX_ISSUES_REASON = "Fix these issues before continuing."
LINT_MAX_LINES = 30
GIT_REV_PARSE_TIMEOUT_SECS = 10

RepoRootFinder = Callable[[str], "str | None"]


def _is_skipped_path(file_path: str) -> bool:
    if "/.claude/plans/" in file_path:
        return True
    if "/docs/" in file_path and file_path.endswith(".md"):
        return True
    basename = file_path.rsplit("/", 1)[-1]
    return basename == "PLAN.md" or "CHANGELOG" in basename or "LICENSE" in basename


def _real_repo_root_of(directory: str) -> str | None:
    """The real git boundary — the only place this hook asks git anything."""
    return (
        GIT.run(
            directory,
            "rev-parse",
            "--show-toplevel",
            timeout=GIT_REV_PARSE_TIMEOUT_SECS,
        ).text
        or None
    )


def _which(name: str) -> str | None:
    return shutil.which(name)


def _default_runner() -> LinterRunner:
    return LinterRunner(which=_which)


def structure_findings(file_path: str, lines: list[str]) -> list[str]:
    limits = SizeLimits.for_file(file_path)
    findings = []
    size_finding = file_size_finding(file_path, len(lines), limits.file_lines)
    if size_finding:
        findings.append(size_finding + "\n")
    func_finding = function_size_finding(
        file_extension(file_path), lines, limits.func_lines
    )
    if func_finding:
        findings.append(func_finding + "\n")
    return findings


def _run_language_linter(
    runner: LinterRunner, file_path: str, extension: str, repo_root_of: RepoRootFinder
) -> tuple[str, str]:
    match extension:
        case "go":
            return linters.lint_go(runner, file_path, str(Path(file_path).parent))
        case "ts" | "tsx" | "js" | "jsx" | "vue":
            repo_root = repo_root_of(str(Path(file_path).parent))
            return linters.lint_eslint(runner, file_path, repo_root)
        case "py":
            return linters.lint_ruff(runner, file_path)
        case "php":
            return linters.lint_phpstan_or_phpcs(runner, file_path)
        case "swift":
            return linters.lint_swiftlint(runner, file_path)
        case "pl" | "pm":
            return linters.lint_perlcritic(runner, file_path, extension)
        case "rb":
            return linters.lint_rubocop(runner, file_path)
        case "sh" | "bash":
            return linters.lint_shellcheck(runner, file_path)
        case "css" | "scss":
            return linters.lint_stylelint(runner, file_path, extension)
        case "sql":
            return linters.lint_sqlfluff(runner, file_path)
        case "tf":
            return linters.lint_tflint(runner, file_path)
        case _:
            return "", ""


def build_reason(
    runner: LinterRunner, file_path: str, lines: list[str], repo_root_of: RepoRootFinder
) -> str | None:
    """None when clean; the block reason text otherwise."""
    findings = structure_findings(file_path, lines)
    extension = file_extension(file_path)
    lint_output, skip_note = _run_language_linter(
        runner, file_path, extension, repo_root_of
    )
    if skip_note:
        findings.append(skip_note)
    lint_output = strip_clean_output(lint_output)

    has_real_findings = any(
        not line.startswith("LINT SKIPPED")
        for line in "".join(findings).split("\n")
        if line
    )
    reason = "".join(findings)

    if lint_output:
        has_real_findings = True
        capped = "\n".join(lint_output.rstrip("\n").split("\n")[:LINT_MAX_LINES])
        # Literal backslash-n, not a real newline: the .sh builds this segment
        # with a plain `REASON+="...\n...\n"` (no `echo -e`), so bash never
        # interprets the \n — it stays two literal characters in the output.
        # Replicated for parity; FINDINGS above DOES go through `echo -e`.
        reason += "LINT (" + extension + "):\\n" + capped + "\\n"

    if not has_real_findings:
        return None
    return reason + FIX_ISSUES_REASON


def decide(
    event: HookEvent,
    runner: LinterRunner,
    repo_root_of: RepoRootFinder = _real_repo_root_of,
) -> dict | None:
    """None means silent (exit 0, no stdout) — parity with the .sh's bare `exit 0`."""
    if event.tool_name not in LINTABLE_TOOL_NAMES:
        return None
    file_path = event.tool_input("file_path") or event.tool_input("path")
    if not file_path or not Path(file_path).is_file():
        return None
    if _is_skipped_path(file_path):
        return None

    lines = Path(file_path).read_text(errors="surrogateescape").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    reason = build_reason(runner, file_path, lines, repo_root_of)
    if reason is not None:
        return {"decision": "block", "reason": reason}
    return {"reason": ""}


def main() -> int:
    raw = read_stdin(HookSettings.from_env().stdin_timeout_secs)
    event = HookEvent.parse(raw) if raw is not None else None
    if event is None:
        return 0
    result = decide(event, _default_runner())
    if result is not None:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, main)
