"""The <evidence-check> element: extraction, shape validation, and
provenance ("did this actually happen") — computed once, shared by both
H5 (permission-question) and H1 (completion-claim) in completion-gate.py.

Level 1 (shape): claim/type/ref/scope children present and non-empty, type in
its enum. Every element in the message is checked.
Level 2 (provenance, only attempted when every element's shape is valid): each
claimed ref must be independently corroborated —
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
import os
import re
from dataclasses import dataclass
from pathlib import Path

from hook_common import GIT, command_signature

EVIDENCE_TYPE_ENUM = ("test", "command", "commit", "http", "file", "render")
EVIDENCE_CHILDREN = ("claim", "type", "ref", "scope")
EVIDENCE_TEMPLATE = (
    "<evidence-check>\n"
    "<claim>what you are claiming</claim>\n"
    "<type>test|command|commit|http|file|render</type>\n"
    "<ref>command run, test name, commit sha, url, or file path</ref>\n"
    "<scope>unit|live, or what the proof covers</scope>\n"
    "</evidence-check>"
)
# Opening tag at the start of a line; an unclosed element is malformed.
EVIDENCE_ELEMENT_RE = re.compile(
    r"^<evidence-check>(.*?)(?:</evidence-check>|\Z)", re.DOTALL | re.MULTILINE
)
CLOSING_TAG = "</evidence-check>"
HTTP_SIGNATURE_TOOLS = ("curl", "wget")
GIT_CAT_FILE_TIMEOUT_SECS = 5
CURRENT_DIRECTORY = "."


@dataclass(frozen=True, slots=True)
class EvidenceElement:
    text: str
    closed: bool


def invalid_evidence_block_reason(missing: str) -> str:
    return (
        f"This turn's <evidence-check> element is missing or has invalid field(s): "
        f"{missing}. Fill in the template:\n{EVIDENCE_TEMPLATE}"
    )


def extract_evidence_elements(message: str) -> list[EvidenceElement]:
    """The raw body of every <evidence-check> element, in order.

    Each is closed at its closing tag; an unclosed one runs to the
    end of the message and is reported as malformed by the shape check.
    """
    return [
        EvidenceElement(match.group(1), match.group(0).endswith(CLOSING_TAG))
        for match in EVIDENCE_ELEMENT_RE.finditer(message)
    ]


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    """The parsed <evidence-check> elements: shape errors (if any) and provenance."""

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


def _child_text(body: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", body, re.DOTALL)
    return match.group(1).strip() if match else ""


def _missing_fields(element: EvidenceElement) -> str:
    if not element.closed:
        return "the <evidence-check> element is not closed with </evidence-check>"
    missing = [
        name
        for name in EVIDENCE_CHILDREN
        if not _child_text(element.text, name)
        or (
            name == "type" and _child_text(element.text, name) not in EVIDENCE_TYPE_ENUM
        )
    ]
    return ", ".join(
        "type (must be one of: test|command|commit|http|file|render)"
        if name == "type" and _child_text(element.text, name)
        else name
        for name in missing
    )


def evaluate_evidence_elements(
    elements: list[EvidenceElement], state_dir: Path, session_id: str
) -> EvidenceClaim:
    """Shape-validate and (if all valid) provenance-check every element.

    No elements -> EvidenceClaim(present=False), never a shape error. Any
    shape error is reported (all joined); otherwise provenance_ok requires
    every element corroborated, and claim_type/ref name the first element
    that failed (or the first, when all pass).
    """
    if not elements:
        return EvidenceClaim(present=False)

    problems = [_missing_fields(element) for element in elements]
    if any(problems):
        first = next(i for i, problem in enumerate(problems) if problem)
        return EvidenceClaim(
            present=True,
            missing="; ".join(problem for problem in problems if problem),
            claim_type=_child_text(elements[first].text, "type"),
            ref=_child_text(elements[first].text, "ref"),
        )

    picked = elements[0]
    provenance_ok = True
    for element in elements:
        claim_type = _child_text(element.text, "type")
        ref = _child_text(element.text, "ref")
        if not _check_provenance(claim_type, ref, state_dir, session_id):
            provenance_ok = False
            picked = element
            break
    return EvidenceClaim(
        present=True,
        claim_type=_child_text(picked.text, "type"),
        ref=_child_text(picked.text, "ref"),
        provenance_ok=provenance_ok,
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
