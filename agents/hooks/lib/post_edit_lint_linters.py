"""Per-extension linter dispatch for post-edit-lint, behind one injectable facade.

Every external tool invocation (golangci-lint, eslint, ruff, ...) goes
through ``LinterRunner``, so a test can substitute a fake process runner and
a fake "which" instead of shelling out to a real linter (never real trunk —
it has hung this machine before).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

LINT_TIMEOUT_SECS = 30
GOLANGCI_LINT_TIMEOUT = "15s"

# Findings worth showing vs "ran clean" — file:line refs, severity markers,
# lint codes. A clean run's output is discarded even if non-empty.
_REAL_FINDING_RE = re.compile(
    r":[0-9]+[: ]|line [0-9]+|severity|✖|✗|FAIL|^\s*(E|W|C|F)[0-9]|error:|warning:|SC[0-9]",
    re.MULTILINE,
)

CommandRunner = Callable[[list[str]], "ProcessResult"]
PathFinder = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class ProcessResult:
    stdout: str
    returncode: int


def _run_command(argv: list[str], cwd: str | None = None) -> ProcessResult:
    result = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=LINT_TIMEOUT_SECS,
        check=False,
    )
    return ProcessResult(stdout=result.stdout + result.stderr, returncode=result.returncode)


@dataclass(frozen=True, slots=True)
class LinterRunner:
    """Injectable boundary for `command -v <tool>` and running it."""

    which: PathFinder
    run: CommandRunner = _run_command

    def is_available(self, tool: str) -> bool:
        return self.which(tool) is not None


def _skip_message(extension: str, *tools: str) -> str:
    return f"LINT SKIPPED: {'/'.join(tools)} not found for {extension} file.\n"


def lint_go(runner: LinterRunner, file_path: str, directory: str) -> tuple[str, str]:
    """Returns (lint_output, finding). golangci-lint only runs inside a Go module."""
    if not runner.is_available("golangci-lint"):
        return "", _skip_message("go", "golangci-lint")
    module_probe = runner.run(["go", "env", "GOMOD"])
    if not module_probe.stdout.strip():
        return "", "LINT SKIPPED: not inside a Go module.\n"
    basename = file_path.rsplit("/", 1)[-1]
    result = runner.run(
        ["golangci-lint", "run", f"--timeout={GOLANGCI_LINT_TIMEOUT}", basename], cwd=directory
    )
    filtered = "\n".join(
        line
        for line in result.stdout.split("\n")
        if not line.startswith("[runner/") and not line.startswith('level=warning msg="[runner/')
    )
    return filtered, ""


def lint_ruff(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if not runner.is_available("ruff"):
        return "", _skip_message("py", "ruff")
    return runner.run(["ruff", "check", file_path]).stdout, ""


def lint_shellcheck(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if not runner.is_available("shellcheck"):
        return "", _skip_message("sh", "shellcheck")
    return runner.run(["shellcheck", file_path]).stdout, ""


def lint_swiftlint(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if not runner.is_available("swiftlint"):
        return "", _skip_message("swift", "swiftlint")
    return runner.run(["swiftlint", "lint", "--path", file_path, "--quiet"]).stdout, ""


def lint_perlcritic(runner: LinterRunner, file_path: str, extension: str) -> tuple[str, str]:
    if not runner.is_available("perlcritic"):
        return "", _skip_message(extension, "perlcritic")
    return runner.run(["perlcritic", "--severity", "3", file_path]).stdout, ""


def lint_rubocop(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if not runner.is_available("rubocop"):
        return "", _skip_message("rb", "rubocop")
    return runner.run(["rubocop", "--format", "simple", file_path]).stdout, ""


def lint_stylelint(runner: LinterRunner, file_path: str, extension: str) -> tuple[str, str]:
    if runner.is_available("stylelint"):
        return runner.run(["stylelint", file_path]).stdout, ""
    if runner.is_available("npx"):
        return runner.run(["npx", "stylelint", file_path]).stdout, ""
    return "", _skip_message(extension, "stylelint")


def lint_sqlfluff(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if not runner.is_available("sqlfluff"):
        return "", _skip_message("sql", "sqlfluff")
    return runner.run(["sqlfluff", "lint", "--dialect", "postgres", file_path]).stdout, ""


def lint_tflint(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if not runner.is_available("tflint"):
        return "", _skip_message("tf", "tflint")
    return runner.run(["tflint", file_path]).stdout, ""


def lint_phpstan_or_phpcs(runner: LinterRunner, file_path: str) -> tuple[str, str]:
    if runner.is_available("phpstan"):
        return runner.run(["phpstan", "analyse", "--no-progress", file_path]).stdout, ""
    if runner.is_available("phpcs"):
        return runner.run(["phpcs", file_path]).stdout, ""
    return "", _skip_message("php", "phpstan/phpcs")


def lint_eslint(runner: LinterRunner, file_path: str, repo_root: str | None) -> tuple[str, str]:
    if repo_root and runner.which(f"{repo_root}/node_modules/.bin/eslint"):
        return runner.run(
            ["npx", "eslint", "--no-error-on-unmatched-pattern", file_path], cwd=repo_root
        ).stdout, ""
    if runner.is_available("eslint"):
        return runner.run(["eslint", "--no-error-on-unmatched-pattern", file_path]).stdout, ""
    return "", _skip_message("js", "eslint")


def strip_clean_output(lint_output: str) -> str:
    """Discards lint output that carries no real finding markers."""
    if lint_output and not _REAL_FINDING_RE.search(lint_output):
        return ""
    return lint_output
