"""The ```evidence fenced-JSON block: extraction, shape validation, and
provenance ("did this actually happen") — computed once, shared by both
H5 (permission-question) and H1 (completion-claim) in completion-gate.py.

Level 1 (shape): claim/type/ref/scope present, type/scope in their enums.
Level 2 (provenance, only attempted when the shape is valid): the claimed
ref must be independently corroborated —
  test/command -> a recorded SUCCESS in this session's bash history whose
                  signature equals the ref's own signature
  commit       -> `git cat-file -e <ref>` resolves
  file         -> the path exists
  http         -> ref's own signature starts with curl/wget AND a recorded
                  SUCCESS in history has that exact signature
  render       -> ref exists AND its mtime is after this session's earliest
                  recorded activity (proxy for "session start")
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from hook_common import GIT, command_signature

EVIDENCE_TYPE_ENUM = ("test", "command", "commit", "http", "file", "render")
EVIDENCE_SCOPE_ENUM = ("unit", "live")
EVIDENCE_TEMPLATE = (
    "```evidence\n"
    '{"claim": "<what you are claiming>", "type": "test|command|commit|http|file|render", '
    '"ref": "<command run, test name, commit sha, url, or file path>", "scope": "unit|live"}\n'
    "```"
)
EVIDENCE_FENCE_MARKER = "```evidence"
FENCE_MARKER = "```"
HTTP_SIGNATURE_TOOLS = ("curl", "wget")
GIT_CAT_FILE_TIMEOUT_SECS = 5
CURRENT_DIRECTORY = "."


def invalid_evidence_block_reason(missing: str) -> str:
    return (
        f"This turn's ```evidence block is missing or has invalid field(s): "
        f"{missing}. Fill in the template:\n{EVIDENCE_TEMPLATE}"
    )


def extract_evidence_block(message: str) -> str:
    """The raw text between a ```evidence fence and the next ``` line.

    Substring matching (not exact-line), matching the awk original: any
    line CONTAINING the marker toggles fence state.
    """
    lines: list[str] = []
    in_fence = False
    for line in message.split("\n"):
        if EVIDENCE_FENCE_MARKER in line:
            in_fence = True
            continue
        if in_fence and FENCE_MARKER in line:
            in_fence = False
            continue
        if in_fence:
            lines.append(line)
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    """A parsed ```evidence block: its shape errors (if any) and provenance."""

    present: bool
    missing: str = ""
    claim_type: str = ""
    ref: str = ""
    provenance_ok: bool = False

    @property
    def shape_valid(self) -> bool:
        return self.present and not self.missing

    @property
    def corroborated(self) -> bool:
        return self.shape_valid and self.provenance_ok


def _missing_fields(payload: dict) -> str:
    missing: list[str] = []
    if not payload.get("claim"):
        missing.append("claim")
    if not payload.get("ref"):
        missing.append("ref")
    claim_type = payload.get("type") or ""
    if not claim_type:
        missing.append("type")
    elif claim_type not in EVIDENCE_TYPE_ENUM:
        missing.append("type (must be one of: test|command|commit|http|file|render)")
    scope = payload.get("scope") or ""
    if not scope:
        missing.append("scope")
    elif scope not in EVIDENCE_SCOPE_ENUM:
        missing.append("scope (must be one of: unit|live)")
    return ", ".join(missing)


def evaluate_evidence_block(
    block_text: str, state_dir: Path, session_id: str
) -> EvidenceClaim:
    """Shape-validate and (if valid) provenance-check a raw ```evidence block.

    ``block_text`` is "" when the message carried no ```evidence fence at
    all — that case is EvidenceClaim(present=False), never a shape error.
    """
    if not block_text:
        return EvidenceClaim(present=False)

    try:
        payload = json.loads(block_text)
    except ValueError:
        return EvidenceClaim(
            present=True, missing="the ```evidence block is not valid JSON"
        )
    if not isinstance(payload, dict):
        return EvidenceClaim(
            present=True, missing="the ```evidence block is not valid JSON"
        )

    missing = _missing_fields(payload)
    claim_type = payload.get("type") or ""
    ref = payload.get("ref") or ""
    if missing:
        return EvidenceClaim(
            present=True, missing=missing, claim_type=claim_type, ref=ref
        )

    provenance_ok = _check_provenance(claim_type, ref, state_dir, session_id)
    return EvidenceClaim(
        present=True, claim_type=claim_type, ref=ref, provenance_ok=provenance_ok
    )


def _bash_history_path(state_dir: Path, session_id: str) -> Path:
    return state_dir / f"bash-history-{session_id}.tsv"


def _history_has_success(history: Path, signature: str) -> bool:
    if not history.is_file():
        return False
    with contextlib.suppress(OSError):
        for line in history.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) >= 3 and fields[2] == "success" and fields[1] == signature:
                return True
    return False


def _session_start_epoch(history: Path) -> int | None:
    if not history.is_file():
        return None
    timestamps: list[int] = []
    with contextlib.suppress(OSError):
        for line in history.read_text().splitlines():
            with contextlib.suppress(ValueError, IndexError):
                timestamps.append(int(line.split("\t", 1)[0]))
    return min(timestamps) if timestamps else None


def _commit_exists(ref: str) -> bool:
    return GIT.run(
        CURRENT_DIRECTORY, "cat-file", "-e", ref, timeout=GIT_CAT_FILE_TIMEOUT_SECS
    ).ok


def _check_provenance(
    claim_type: str, ref: str, state_dir: Path, session_id: str
) -> bool:
    history = _bash_history_path(state_dir, session_id)
    match claim_type:
        case "test" | "command":
            return _history_has_success(history, command_signature(ref))
        case "commit":
            return _commit_exists(ref)
        case "file":
            return os.path.exists(ref)
        case "http":
            signature = command_signature(ref)
            leading_word = signature.split(" ", 1)[0]
            if leading_word not in HTTP_SIGNATURE_TOOLS:
                return False
            return _history_has_success(history, signature)
        case "render":
            if not os.path.exists(ref):
                return False
            session_start = _session_start_epoch(history)
            if session_start is None:
                return False
            with contextlib.suppress(OSError):
                return os.stat(ref).st_mtime > session_start
            return False
        case _:
            return False
