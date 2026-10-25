"""search-scope-guard.py: find is always denied, home/root searches are always
denied, and known-huge trees require a bounded timeout.

No dedicated .sh exists for this hook — it's Python-native from the start
(see MIGRATION.md for the porting shape this still follows: pure functions
over ShellCommand segments, one Decision per case).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from hook_harness import HookRun, HookRunner

HOOK = "search-scope-guard.py"
CURSOR_ADAPTER = Path.home() / ".cursor" / "hooks" / "search-scope-guard-cursor.py"
DENY = "deny"
SILENT = "none"
REPO_CWD = "/Users/zbornheimer/Developer/Personal/dotfiles"
HOME_CWD = "/Users/zbornheimer"


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    command: str
    expected: str
    cwd: str = REPO_CWD


CASES = (
    # Rule 1: `find` denied in command position, every disguise.
    Case("find-plain-deny", "find ~ -name x", DENY),
    Case("find-after-semicolon-deny", "echo hi; find / -name x", DENY),
    Case("find-after-and-deny", "true && find . -name x", DENY),
    Case("find-after-or-deny", "false || find . -name x", DENY),
    Case("find-after-pipe-deny", "echo x | find . -name x", DENY),
    Case("find-dollar-paren-deny", "echo $(find . -name x)", DENY),
    Case("find-backtick-deny", "echo `find . -name x`", DENY),
    Case("find-after-xargs-deny", "echo . | xargs find -name x", DENY),
    Case("find-after-sudo-deny", "sudo find . -name x", DENY),
    Case("find-after-timeout-n-deny", "timeout 30 find . -name x", DENY),
    Case("find-after-env-deny", "env FOO=1 find . -name x", DENY),
    Case("find-after-nice-deny", "nice find . -name x", DENY),
    Case("find-full-path-deny", "/usr/bin/find . -name x", DENY),
    Case("find-in-heredoc-body-allow", "cat <<'EOF'\nfind / -name x\nEOF\n", SILENT),
    # Rule 1 false positives — `find` as data/argument, not a command.
    Case("find-as-git-grep-arg-allow", "git log --grep find", SILENT),
    Case("find-as-rg-pattern-allow", "rg find", SILENT),
    Case("find-as-echo-arg-allow", "echo find", SILENT),
    Case("find-as-fd-pattern-allow", "fd find", SILENT),
    Case("find-as-flag-value-allow", "mdfind -name find", SILENT),
    Case("git-bisect-allow", "git bisect start", SILENT),
    # Rule 2: home/root roots always denied.
    Case("fd-tilde-deny", "fd x ~", DENY),
    Case("fd-tilde-slash-deny", "fd x ~/", DENY),
    Case("fd-dollar-home-deny", "fd x $HOME", DENY),
    Case("fd-braced-dollar-home-deny", "fd x ${HOME}", DENY),
    Case("fd-literal-home-deny", "fd x /Users/zbornheimer", DENY),
    Case("fd-users-deny", "fd x /Users", DENY),
    Case("fd-bare-root-deny", "fd x /", DENY),
    Case("rg-system-deny", "rg foo /System", DENY),
    Case("rg-cwd-home-no-path-deny", "rg foo", DENY, cwd=HOME_CWD),
    Case("rg-cwd-repo-no-path-allow", "rg foo", SILENT, cwd=REPO_CWD),
    Case("fd-tilde-with-timeout-still-deny", "timeout 30 fd x ~", DENY),
    Case("fd-repo-subpath-allow", "fd x ~/Developer/Personal/dotfiles", SILENT),
    Case("fd-dot-claude-allow", "fd x ~/.claude", SILENT),
    # Rule 3: known-huge trees need a bounded timeout.
    Case("fd-developer-no-timeout-deny", "fd x ~/Developer", DENY),
    Case("fd-developer-org-no-timeout-deny", "fd x ~/Developer/Personal", DENY),
    Case("fd-developer-with-timeout-allow", "timeout 60 fd x ~/Developer", SILENT),
    Case("fd-developer-with-gtimeout-allow", "gtimeout 120 fd x ~/Developer", SILENT),
    Case(
        "fd-developer-with-timeout-suffix-allow", "timeout 2m fd x ~/Developer", SILENT
    ),
    Case("fd-developer-timeout-too-long-deny", "timeout 300 fd x ~/Developer", DENY),
    Case("rg-dropbox-no-timeout-deny", "rg foo ~/Dropbox", DENY),
    Case("rg-library-no-timeout-deny", "rg foo ~/Library", DENY),
    Case("rg-documents-no-timeout-deny", "rg foo ~/Documents", DENY),
    Case("rg-downloads-no-timeout-deny", "rg foo ~/Downloads", DENY),
    Case("rg-cache-no-timeout-deny", "rg foo ~/.cache", DENY),
    Case("rg-go-no-timeout-deny", "rg foo ~/go", DENY),
    # Rule 3: grep -r always denied, regardless of root or timeout.
    Case("grep-r-deny", "grep -r foo .", DENY),
    Case("grep-cap-r-deny", "grep -R foo .", DENY),
    Case("grep-long-recursive-deny", "grep --recursive foo .", DENY),
    Case("grep-ri-combined-deny", "grep -ri foo .", DENY),
    Case("grep-plain-allow", "grep foo file.txt", SILENT),
    # Other search commands, sanity.
    Case("ag-tilde-deny", "ag foo ~", DENY),
    Case("ack-tilde-deny", "ack foo ~", DENY),
    Case("du-developer-no-timeout-deny", "du -sh ~/Developer", DENY),
    Case("tree-tilde-deny", "tree ~", DENY),
    Case("ls-recursive-tilde-deny", "ls -R ~", DENY),
    Case("ls-plain-tilde-allow", "ls ~", SILENT),
    # Unrelated commands never trip the guard.
    Case("mkdir-allow", "mkdir -p /tmp/x", SILENT),
    Case("plain-echo-allow", "echo hello world", SILENT),
)


def _case_id(case: Case) -> str:
    return case.name


def payload(case: Case) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": case.command},
        "cwd": case.cwd,
    }


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_search_scope_guard(hooks: HookRunner, case: Case) -> None:
    run = hooks.run_payload(HOOK, payload(case))
    assert_clean_run(run)
    assert run.decision == case.expected, run.log


def test_malformed_json_fails_open(hooks: HookRunner) -> None:
    run = hooks.run_payload(HOOK, "{not json")
    assert run.exit_code == 0
    assert run.decision == SILENT


def test_non_bash_tool_is_untouched(hooks: HookRunner) -> None:
    run = hooks.run_payload(
        HOOK, {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}
    )
    assert_clean_run(run)
    assert run.decision == SILENT


# --- Multi-harness payload shapes ---------------------------------------
#
# Codex sends the same snake_case shape as Claude Code (tool_name /
# tool_input / cwd), so it needs no adapter — covered by the CASES above via
# the ordinary `payload()` shape. Grok sends camelCase with its own tool
# name for Bash (`run_terminal_command`); hook_common's TOOL_NAME_ALIASES
# and HookEvent.field's snake//camel fallback handle it directly. Cursor's
# beforeShellExecution payload is shaped differently (`command`/`cwd` at
# the top level, no tool_name/tool_input at all) and returns a different
# response shape (`{"permission": ...}` vs Claude's hookSpecificOutput), so
# it goes through the dedicated ~/.cursor/hooks/search-scope-guard-cursor.py
# adapter instead of the shared entry point.


def grok_payload(case: Case) -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "toolName": "run_terminal_command",
        "toolInput": {"command": case.command},
        "cwd": case.cwd,
    }


GROK_SHAPE_CASES = (
    Case("find-plain-deny", "find ~ -name x", DENY),
    Case("fd-repo-subpath-allow", "fd x ~/Developer/Personal/dotfiles", SILENT),
    Case("fd-developer-no-timeout-deny", "fd x ~/Developer", DENY),
)


@pytest.mark.parametrize("case", GROK_SHAPE_CASES, ids=_case_id)
def test_grok_camelcase_payload_shape(hooks: HookRunner, case: Case) -> None:
    """Grok's PreToolUse payload (camelCase, run_terminal_command) decides identically.

    Grok reaches this same script directly: ~/.grok/config.toml sets
    [compat.claude] hooks = true, which scans ~/.claude/settings.json's
    PreToolUse/Bash matcher (search-scope-guard.py is registered there) —
    no separate Grok registration is needed.
    """
    run = hooks.run_payload(HOOK, grok_payload(case))
    assert_clean_run(run)
    assert run.decision == case.expected, run.log


def cursor_payload(case: Case) -> dict:
    return {"command": case.command, "cwd": case.cwd}


CURSOR_SHAPE_CASES = (
    Case("find-plain-deny", "find ~ -name x", "deny"),
    Case("fd-repo-subpath-allow", "fd x ~/Developer/Personal/dotfiles", "allow"),
)


@pytest.mark.skipif(
    not CURSOR_ADAPTER.is_file(), reason="cursor adapter not installed on this machine"
)
@pytest.mark.parametrize("case", CURSOR_SHAPE_CASES, ids=_case_id)
def test_cursor_before_shell_execution_payload_shape(case: Case) -> None:
    """Cursor's beforeShellExecution payload (top-level command/cwd) via the adapter.

    The adapter translates to the shared Claude-shape payload, runs
    search-scope-guard.py as a subprocess, and maps the decision to
    Cursor's {"permission": ...} response schema.
    """
    result = subprocess.run(
        [sys.executable, str(CURSOR_ADAPTER)],
        input=json.dumps(cursor_payload(case)),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body["permission"] == case.expected, result.stdout
