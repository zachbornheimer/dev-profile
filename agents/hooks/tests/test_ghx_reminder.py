"""ghx-reminder.py: no run.sh cases exist for this hook, so payloads are
built inline.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

PY_HOOK = "ghx-reminder.py"


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


PAYLOAD_CASES: dict[str, dict | str] = {
    "gh-search-reminds": _bash("gh search prs --repo foo/bar"),
    "gh-api-graphql-reminds": _bash("gh api graphql -f query=x"),
    "gh-pr-list-reminds": _bash("gh pr list"),
    "gh-issue-view-reminds": _bash("gh issue view 42"),
    "already-routed-through-ghx-silent": _bash("ghx pr list"),
    "gh-clone-not-rate-limited-silent": _bash("gh repo clone foo/bar"),
    "non-bash-tool-silent": {"tool_name": "Read", "tool_input": {"file_path": "/x"}},
    "empty-command-silent": _bash(""),
    "empty-stdin-silent": "",
    "grok-camelcase-reminds": {
        "toolName": "run_terminal_command",
        "toolInput": {"command": "gh issue list --repo foo/bar"},
    },
}


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_decides(hooks: HookRunner, name: str) -> None:
    run = hooks.run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    if name.endswith("-reminds"):
        assert run.decision == "context"
        assert "ghx" in (run.output or {})["hookSpecificOutput"]["additionalContext"]
    else:
        assert run.stdout == ""
