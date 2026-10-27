"""handoff-doc-refresh.py: a compaction rewrites the session's handoff doc from its current state.

The `capability` CLI (mastra's create_session_handoff_doc workflow, ~11 s, reads the real transcript) is
replaced by a stub named in HANDOFF_CAPABILITY_BIN. The stub records its argv and prints the workflow's
output shape ({"conversation", "markdown", "source"}) with whatever markdown the test has put in its
`state` file, so a test changes "the session's state" between two compactions the way a live session does.
The doc lands in the isolated state dir (HC_STATE_DIR_OVERRIDE), never the live one.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from hook_harness import HookRunner, HookSession

PY_HOOK = "handoff-doc-refresh.py"
SESSION_ID = "01a17a4c-a9ce-76f1-9c6f-f50a26cc4b6d"
OMP_TRANSCRIPT = (
    f"/Users/z/.omp/agent/sessions/-tmp/2026-10-26T22-20-06-990Z_{SESSION_ID}.jsonl"
)
CLAUDE_TRANSCRIPT = f"/Users/z/.claude/projects/-tmp/{SESSION_ID}.jsonl"
FIRST_STATE = "# Handoff Context\n\n## Current Goal\n\nShip the first thing.\n"
SECOND_STATE = "# Handoff Context\n\n## Current Goal\n\nShip the first thing.\n\n## Recent Turns\n\n- user: now ship the second thing\n"

STUB = """#!/bin/sh
# argv -> $0.argv (one arg per line); exit code and markdown come from sibling files the test writes.
printf '%s\\n' "$@" > "$0.argv"
if [ -f "$0.fail" ]; then echo "workflow exploded" >&2; exit 3; fi
python3 - "$0.state" <<'PY'
import json, sys
print(json.dumps({"conversation": "x", "markdown": open(sys.argv[1]).read(), "source": {}}))
PY
"""


class Stub:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.write_text(STUB)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def set_state(self, markdown: str) -> None:
        Path(f"{self.path}.state").write_text(markdown)

    def fail(self) -> None:
        Path(f"{self.path}.fail").write_text("")

    @property
    def argv(self) -> list[str]:
        return Path(f"{self.path}.argv").read_text().splitlines()

    @property
    def was_run(self) -> bool:
        return Path(f"{self.path}.argv").exists()


@pytest.fixture
def stub(tmp_path: Path) -> Stub:
    made = Stub(tmp_path / "capability-stub")
    made.set_state(FIRST_STATE)
    return made


@pytest.fixture
def session(hooks: HookRunner, stub: Stub) -> HookSession:
    return hooks.session(
        "handoff",
        env={"HANDOFF_CAPABILITY_BIN": str(stub.path), "AGENT_HOOKS_AGENT": "claude"},
    )


def _precompact(transcript_path: str = OMP_TRANSCRIPT, **extra: str) -> dict:
    return {
        "session_id": SESSION_ID,
        "transcript_path": transcript_path,
        "cwd": "/tmp",
        "hook_event_name": "PreCompact",
        "trigger": "auto",
        **extra,
    }


def _doc(session: HookSession, harness: str) -> Path:
    return session.state_dir / "handoff" / f"{harness}-{SESSION_ID}.md"


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert run.stdout == ""
    assert not run.failed_open, run.log


def test_compaction_writes_the_handoff_doc(session: HookSession, stub: Stub) -> None:
    run = session.run_payload(PY_HOOK, _precompact())

    assert_clean_run(run)
    assert "refreshed" in run.log
    doc = _doc(session, "omp").read_text()
    assert doc.startswith(
        "<!-- refreshed: 2000-01-01T00:00:00Z at compaction (auto) -->\n"
    )
    assert doc.endswith(FIRST_STATE)
    assert stub.argv[:3] == ["run", "create_session_handoff_doc", "--input"]
    assert json.loads(stub.argv[3]) == {"conversation": f"omp:{SESSION_ID}"}


def test_next_compaction_rewrites_the_doc_with_the_sessions_current_state(
    session: HookSession, stub: Stub
) -> None:
    session.run_payload(PY_HOOK, _precompact())
    assert "second thing" not in _doc(session, "omp").read_text()

    stub.set_state(SECOND_STATE)
    run = session.run_payload(PY_HOOK, _precompact(trigger="manual"))

    assert_clean_run(run)
    doc = _doc(session, "omp").read_text()
    assert "now ship the second thing" in doc
    assert "(manual)" in doc
    assert doc.count("<!-- refreshed: ") == 1
    assert list(_doc(session, "omp").parent.glob(".*")) == [], (
        "no temp file left behind"
    )


def test_harness_comes_from_the_transcript_location(
    session: HookSession, stub: Stub
) -> None:
    run = session.run_payload(PY_HOOK, _precompact(CLAUDE_TRANSCRIPT))

    assert_clean_run(run)
    assert json.loads(stub.argv[3]) == {"conversation": f"claude:{SESSION_ID}"}
    assert _doc(session, "claude").is_file()
    assert not _doc(session, "omp").exists()


def test_harness_falls_back_to_the_dispatcher_agent(
    hooks: HookRunner, stub: Stub
) -> None:
    codex = hooks.session(
        "handoff-codex",
        env={"HANDOFF_CAPABILITY_BIN": str(stub.path), "AGENT_HOOKS_AGENT": "codex"},
    )
    run = codex.run_payload(
        PY_HOOK, {"session_id": SESSION_ID, "hook_event_name": "PreCompact"}
    )

    assert_clean_run(run)
    assert json.loads(stub.argv[3]) == {"conversation": f"codex:{SESSION_ID}"}
    assert _doc(codex, "codex").is_file()


def test_failed_render_keeps_the_previous_doc(session: HookSession, stub: Stub) -> None:
    session.run_payload(PY_HOOK, _precompact())
    before = _doc(session, "omp").read_text()

    stub.fail()
    run = session.run_payload(PY_HOOK, _precompact())

    assert_clean_run(run)
    assert "kept-previous" in run.log
    assert "exit-3" in run.log
    assert _doc(session, "omp").read_text() == before


def test_unreadable_workflow_output_writes_nothing(
    session: HookSession, stub: Stub
) -> None:
    stub.set_state("")

    run = session.run_payload(PY_HOOK, _precompact())

    assert_clean_run(run)
    assert "no-markdown-in-output" in run.log
    assert not _doc(session, "omp").exists()


def test_missing_capability_binary_fails_open_without_a_doc(
    hooks: HookRunner, tmp_path: Path
) -> None:
    gone = hooks.session(
        "handoff-gone",
        env={
            "HANDOFF_CAPABILITY_BIN": str(tmp_path / "no-such-capability"),
            "AGENT_HOOKS_AGENT": "claude",
        },
    )

    run = gone.run_payload(PY_HOOK, _precompact())

    assert_clean_run(run)
    assert "cannot-run" in run.log
    assert not _doc(gone, "omp").exists()


def test_event_naming_no_session_is_skipped(hooks: HookRunner, stub: Stub) -> None:
    unnamed = hooks.session(
        "handoff-unnamed",
        env={"HANDOFF_CAPABILITY_BIN": str(stub.path), "AGENT_HOOKS_AGENT": ""},
    )

    run = unnamed.run_payload(PY_HOOK, {"hook_event_name": "PreCompact", "cwd": "/tmp"})

    assert_clean_run(run)
    assert "skipped" in run.log
    assert not stub.was_run


def test_empty_stdin_is_silent(session: HookSession, stub: Stub) -> None:
    run = session.run_payload(PY_HOOK, "")

    assert_clean_run(run)
    assert not stub.was_run
