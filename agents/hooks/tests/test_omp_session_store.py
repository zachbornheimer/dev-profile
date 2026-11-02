"""omp_session_store: an omp session kept only in the session database still reaches the hooks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR
from session_db_fake import fake_calls, fake_session_db

sys.path.insert(0, str(HOOKS_DIR / "lib"))
import omp_session_store
from completion_gate_transcript import read_transcript_facts

SESSION_ID = "01a19986-b0fc-7374-b5cb-7d0969770e66"
STORED = f"/home/u/.omp/agent/sessions/-w/2026-11-01T23-51-43-612Z_{SESSION_ID}.jsonl"
TRANSCRIPT = "\n".join(
    json.dumps(row, separators=(",", ":"))  # compact, as omp writes it
    for row in [
        {"type": "session", "version": 3, "id": SESSION_ID, "cwd": "/w"},
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "fix the flaky test"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def use(sessions: dict[str, str], host: str = "db.test") -> None:
        for key, value in fake_session_db(tmp_path, sessions, host).items():
            monkeypatch.setenv(key, value)

    monkeypatch.setenv("HC_STATE_DIR_OVERRIDE", str(tmp_path / "state"))
    return use


def test_a_session_only_in_the_database_gives_the_gate_the_users_prompt(
    store, tmp_path: Path
) -> None:
    """The completion gate could never block an omp turn: it saw no file, so no user request."""
    store({STORED: TRANSCRIPT})
    facts = read_transcript_facts(STORED)
    assert facts is not None
    assert facts.user_prompt == "fix the flaky test"


def test_the_connection_reaches_psql_through_libpq_variables_not_argv(
    store, tmp_path: Path
) -> None:
    store({STORED: TRANSCRIPT})
    copy = omp_session_store.readable_transcript(STORED)
    assert copy is not None and copy.read_text().startswith('{"type":"session"')
    assert copy.stat().st_mode & 0o777 == 0o600
    assert [call["host"] for call in fake_calls(tmp_path)] == ["db.test"]


def test_a_file_on_disk_is_used_as_is_without_asking_the_database(
    store, tmp_path: Path
) -> None:
    store({})
    on_disk = tmp_path / f"2026-11-01T00-00-00-000Z_{SESSION_ID}.jsonl"
    on_disk.write_text(TRANSCRIPT)
    assert omp_session_store.readable_transcript(on_disk) == on_disk
    assert fake_calls(tmp_path) == []


@pytest.mark.parametrize(
    ("sessions", "host"),
    [({}, "db.test"), ({STORED: TRANSCRIPT}, "unreachable")],
    ids=["session not in the database", "database unreachable"],
)
def test_no_transcript_anywhere_is_none_so_hooks_stay_fail_open(
    store, sessions, host
) -> None:
    store(sessions, host)
    assert omp_session_store.readable_transcript(STORED) is None
    assert read_transcript_facts(STORED) is None


def test_a_path_that_is_not_an_omp_session_never_queries(store, tmp_path: Path) -> None:
    store({})
    assert (
        omp_session_store.readable_transcript("/nope/claude-transcript.jsonl") is None
    )
    assert fake_calls(tmp_path) == []


def test_stored_session_path_finds_omps_recorded_path_by_id(store) -> None:
    store({STORED: TRANSCRIPT})
    assert omp_session_store.stored_session_path(SESSION_ID) == STORED
    assert omp_session_store.stored_session_path("not-a-uuid") is None
