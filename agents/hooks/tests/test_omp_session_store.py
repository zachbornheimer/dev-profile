"""omp_session_store: hooks read the freshest copy of an omp session, on disk or in the session database."""

from __future__ import annotations

import json
import os
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
NOON = 1_793_620_800_000  # an mtime_ms; only the order between copies matters


def transcript(prompt: str) -> str:
    return "\n".join(
        json.dumps(row, separators=(",", ":"))  # compact, as omp writes it
        for row in [
            {"type": "session", "version": 3, "id": SESSION_ID, "cwd": "/w"},
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
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


TRANSCRIPT = transcript("fix the flaky test")


def on_disk(tmp_path: Path, prompt: str, mtime_ms: int) -> Path:
    path = tmp_path / f"2026-11-01T00-00-00-000Z_{SESSION_ID}.jsonl"
    path.write_text(transcript(prompt))
    os.utime(path, ns=(mtime_ms * 1_000_000, mtime_ms * 1_000_000))
    return path


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


def test_a_subagent_session_only_in_the_database_gives_the_guard_its_task(
    store, tmp_path: Path
) -> None:
    """omp keeps a subagent's session at <session>/<Name>.jsonl. The store recognized
    only <stamp>_<id>.jsonl, so the scope guard read no task and allowed every subagent call."""
    subagent = STORED.removesuffix(".jsonl") + "/ScopeTests.jsonl"
    store({STORED: TRANSCRIPT, subagent: transcript("repair the scope guard tests")})
    facts = read_transcript_facts(subagent)
    assert facts is not None
    assert facts.user_prompt == "repair the scope guard tests"
    parent = read_transcript_facts(STORED)
    assert parent is not None
    assert parent.user_prompt == "fix the flaky test"


def test_the_connection_reaches_psql_through_libpq_variables_not_argv(
    store, tmp_path: Path
) -> None:
    store({STORED: TRANSCRIPT})
    copy = omp_session_store.readable_transcript(STORED)
    assert copy is not None and copy.read_text().startswith('{"type":"session"')
    assert copy.stat().st_mode & 0o777 == 0o600
    assert [call["host"] for call in fake_calls(tmp_path)] == ["db.test"]


def test_a_newer_database_copy_wins_over_a_stale_file_on_disk(
    store, tmp_path: Path
) -> None:
    """omp with a session database writes only the database, so a file an earlier run
    left behind freezes. Measured on omp:01a19986: the file stopped at 11:32 while the
    session ran on to 12:12, and the scope guard judged every call against hours-old asks.
    """
    stale = on_disk(tmp_path, "an old request", NOON)
    store({str(stale): [transcript("the current request"), NOON + 60_000]})
    facts = read_transcript_facts(str(stale))
    assert facts is not None
    assert facts.user_prompt == "the current request"


@pytest.mark.parametrize(
    ("row", "host"),
    [
        ([transcript("an older copy"), NOON - 60_000], "db.test"),
        (None, "db.test"),
        ([transcript("a newer copy"), NOON + 60_000], "unreachable"),
    ],
    ids=["database copy older", "session not in the database", "database unreachable"],
)
def test_the_file_on_disk_is_used_when_the_database_has_nothing_newer(
    store, tmp_path: Path, row, host
) -> None:
    current = on_disk(tmp_path, "the request on disk", NOON)
    store({str(current): row} if row else {}, host)
    assert omp_session_store.readable_transcript(current) == current
    assert all(call["sent"] == "nothing" for call in fake_calls(tmp_path))


def test_an_unchanged_database_copy_is_transferred_once(store, tmp_path: Path) -> None:
    """The scope guard reads the transcript on every tool call; an unchanged session
    must cost one small query, not megabytes each time."""
    store({STORED: [TRANSCRIPT, NOON]})
    first = omp_session_store.readable_transcript(STORED)
    second = omp_session_store.readable_transcript(STORED)
    assert first is not None
    assert second == first
    assert [call["sent"] for call in fake_calls(tmp_path)] == ["full", "nothing"]


def test_a_grown_session_transfers_only_what_was_appended(
    store, tmp_path: Path
) -> None:
    """omp appends to a session between tool calls; the read pays for the new rows only."""
    store({STORED: [TRANSCRIPT, NOON]})
    omp_session_store.readable_transcript(STORED)
    grown = TRANSCRIPT + "\n" + transcript("the follow-up request").split("\n", 1)[1]
    store({STORED: [grown, NOON + 60_000]})
    facts = read_transcript_facts(STORED)
    assert facts is not None
    assert facts.user_prompt == "the follow-up request"
    assert [call["sent"] for call in fake_calls(tmp_path)] == ["full", "appended"]


def test_a_session_rewritten_underneath_the_copy_is_fetched_whole(
    store, tmp_path: Path
) -> None:
    """Appending to a copy whose end the database no longer holds would splice two logs."""
    store({STORED: [TRANSCRIPT, NOON]})
    omp_session_store.readable_transcript(STORED)
    store(
        {
            STORED: [
                transcript("a rewritten request, longer than the first"),
                NOON + 60_000,
            ]
        }
    )
    facts = read_transcript_facts(STORED)
    assert facts is not None
    assert facts.user_prompt == "a rewritten request, longer than the first"
    assert [call["sent"] for call in fake_calls(tmp_path)] == ["full", "full"]


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
