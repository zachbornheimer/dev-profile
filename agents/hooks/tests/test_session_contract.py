"""session_contract: build a ticket's contract, persist it, read it back, render it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR

sys.path.insert(0, str(HOOKS_DIR / "lib"))
import session_contract

SESSION_ID = "zys-3843-a269"
CONTRACT = session_contract.build_contract(
    objective="ZYS-3843: the session contract as a persisted, loadable object.",
    acceptance=[
        {
            "id": "acc-proof",
            "kind": "proof",
            "run": "python3 -m pytest tests/test_session_contract.py -q",
        },
        {
            "id": "acc-regression",
            "kind": "regression",
            "run": "python3 -m pytest tests/ -q",
        },
    ],
    context="Worktree on relay/zys-3843-a269 of zachbornheimer/dev-profile.",
    clauses=[
        {
            "id": "clause-worktree",
            "text": "Do the ticket's work in this worktree and nowhere else.",
        },
        {"id": "clause-push", "text": "Push relay/zys-3843-a269 and no other branch."},
        {
            "id": "clause-report",
            "text": "Finish with the branch, the changes, and the verification output.",
        },
    ],
)


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The real on-disk layout (``state/session-contract``), rooted at tmp_path."""
    monkeypatch.setattr(session_contract, "STATE_DIR", tmp_path)
    return tmp_path


def test_state_dir_is_the_hooks_state_directory() -> None:
    assert session_contract.STATE_DIR == HOOKS_DIR / "state"


def test_builds_the_exact_schema() -> None:
    assert list(CONTRACT) == ["objective", "acceptance", "context", "clauses"]
    assert all(list(item) == ["id", "kind", "run"] for item in CONTRACT["acceptance"])
    assert all(list(clause) == ["id", "text"] for clause in CONTRACT["clauses"])
    # Acceptance ids are the caller's stable strings, kept verbatim.
    assert [item["id"] for item in CONTRACT["acceptance"]] == [
        "acc-proof",
        "acc-regression",
    ]


def test_round_trips_through_the_state_directory(state_dir: Path) -> None:
    session_contract.save_contract(SESSION_ID, CONTRACT)
    stored = state_dir / "session-contract" / f"{SESSION_ID}.json"
    assert stored.is_file()
    # The atomic write leaves only the contract behind: no temp file.
    assert list(stored.parent.iterdir()) == [stored]
    assert session_contract.load_contract(SESSION_ID) == CONTRACT


def test_prompt_block_cites_every_clause_id() -> None:
    block = session_contract.to_prompt_block(CONTRACT)
    for clause in CONTRACT["clauses"]:
        assert clause["id"] in block
        assert clause["text"] in block
    for item in CONTRACT["acceptance"]:
        assert item["id"] in block
        assert item["run"] in block
    assert CONTRACT["objective"] in block


def test_load_of_an_unknown_session_is_none(state_dir: Path) -> None:
    assert session_contract.load_contract("no-such-session") is None


@pytest.mark.parametrize("no_contract", [None, "", {}])
def test_prompt_block_without_a_contract_is_empty(no_contract: object) -> None:
    assert session_contract.to_prompt_block(no_contract) == ""  # type: ignore[arg-type]