"""The session contract as a persisted, loadable object.

A relay ticket's objective, acceptance, context, and clauses become one dict
(``build_contract``) that a hook saves under ``state/session-contract/
<session_id>.json`` (``save_contract``, an atomic rename) and reads back in a
later turn (``load_contract``, ``None`` when the session has none).
``to_prompt_block`` renders the contract for a prompt with every clause id
verbatim, so a picker can cite them; with no contract it returns ``""``, so a
caller can feed ``load_contract`` straight in without branching on ``None``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parents[1] / "state"
CONTRACTS_DIR_NAME = "session-contract"


def _contract_path(session_id: str) -> Path:
    """Where the session's contract lives, under the hooks state directory."""
    return STATE_DIR / CONTRACTS_DIR_NAME / f"{session_id}.json"


def build_contract(
    objective: str,
    acceptance: Iterable[Mapping[str, str]],
    context: str,
    clauses: Iterable[Mapping[str, str]],
) -> dict[str, Any]:
    """The contract dict in schema order, caller ids copied verbatim.

    Acceptance ids are stable strings the caller supplies: they are kept as
    given, never renumbered, and both lists keep the caller's order.
    """
    return {
        "objective": objective,
        "acceptance": [
            {"id": item["id"], "kind": item["kind"], "run": item["run"]}
            for item in acceptance
        ],
        "context": context,
        "clauses": [{"id": clause["id"], "text": clause["text"]} for clause in clauses],
    }


def save_contract(session_id: str, contract: Mapping[str, Any]) -> None:
    """Persist ``contract`` to ``state/session-contract/<session_id>.json``.

    The write is atomic: the JSON lands in a sibling temp file, then renames
    over the target, so a concurrent ``load_contract`` never reads a
    half-written contract.
    """
    path = _contract_path(session_id)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def load_contract(session_id: str) -> dict[str, Any] | None:
    """The session's saved contract, or ``None`` when it has none."""
    try:
        text = _contract_path(session_id).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        contract = json.loads(text)
    except ValueError:
        return None
    return contract if isinstance(contract, dict) else None


def to_prompt_block(contract: Mapping[str, Any] | None) -> str:
    """The contract as prompt text, ``""`` when there is no contract.

    Clause ids render verbatim in ``[<id>]`` bullets, so a picker can cite
    them as written; ``None``, ``""``, and any empty mapping render ``""``.
    """
    if not isinstance(contract, Mapping) or not contract:
        return ""
    lines = [
        "## Session contract",
        "",
        f"Objective: {contract.get('objective') or ''}",
        "",
        "Acceptance:",
    ]
    for item in contract.get("acceptance") or ():
        identifier, kind, run = (item.get(key, "") for key in ("id", "kind", "run"))
        lines.append(f"- [{identifier}] {kind}: {run}")
    lines += ["", f"Context: {contract.get('context') or ''}", "", "Clauses:"]
    for clause in contract.get("clauses") or ():
        lines.append(f"- [{clause.get('id', '')}] {clause.get('text', '')}")
    return "\n".join(lines) + "\n"
