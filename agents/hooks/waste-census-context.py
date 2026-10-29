#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""UserPromptSubmit — put the waste census in front of a diagnosis, not behind it.

``waste-census.py`` counted the classes a learning loop keeps missing, but
nothing invoked it: every diagnosis started from the tool errors it happened to
notice, so on ``claude:2ed0c871`` four Bash denials produced twelve hypotheses
while three identical escalations and six fetches of the wrong tool's docs —
most of the wall time — went uncounted. The census is correct and unused. This
hook is the caller.

It fires only when the prompt asks for a diagnosis (``diagnose``, ``forensic``,
``why did``, ``waste``, ``hypothes``, ``learn from``), so ordinary prompts pay
nothing. It then reports the census for the session's own transcript and stays
silent if there is no transcript or no waste.

Reporting only. It never blocks, never edits, and never re-diagnoses.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "waste-census-context"
CENSUS_PATH = Path(__file__).resolve().parent / "waste-census.py"
EVENT = "UserPromptSubmit"

# Prompts that are asking for a diagnosis of a run. Anything else is not this
# hook's business.
DIAGNOSIS_PROMPTS = re.compile(
    r"diagnos|forens|post.?mortem|why did .*(fail|stop|stall)"
    r"|\bwaste|hypothes|learn(ing)? (from|loop)|efficien",
    re.IGNORECASE,
)

CLASS_ORDER = (
    "tool_error",
    "repeat_denied_tool",
    "duplicate_call",
    "repeat_text",
    "refetch",
    "user_recovery",
)
REFS_PER_CLASS = 6


def load_census() -> ModuleType:
    """``waste-census.py`` by path: the hyphen blocks ``import``, and the rule is one owner."""
    spec = importlib.util.spec_from_file_location("waste_census", CENSUS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {CENSUS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(path: Path, findings: dict[str, list[str]]) -> str:
    lines = [
        f"Waste census for this session's transcript ({path.name}) — counted, not judged:"
    ]
    for name in CLASS_ORDER:
        refs = findings.get(name, [])
        shown = ", ".join(refs[:REFS_PER_CLASS])
        more = (
            ""
            if len(refs) <= REFS_PER_CLASS
            else f" (+{len(refs) - REFS_PER_CLASS} more)"
        )
        lines.append(f"- {name}: {len(refs)}" + (f" — {shown}{more}" if refs else ""))
    lines.append(
        "A diagnosis that explains only tool_error has not explained this run: "
        "name the classes it leaves out, with their item ids, before proposing a fix."
    )
    return "\n".join(lines)


def decide(event: HookEvent) -> Decision | None:
    prompt = event.field("prompt", "prompt")
    if not DIAGNOSIS_PROMPTS.search(prompt):
        return None

    transcript = Path(event.field("transcript_path", "transcriptPath")).expanduser()
    if not transcript.is_file():
        return None

    census = load_census()
    findings = census.census(census.load(transcript))
    total = sum(len(refs) for refs in findings.values())
    if total == 0:
        return None

    counts = ", ".join(f"{name}={len(findings.get(name, []))}" for name in CLASS_ORDER)
    return Decision.context(
        render(transcript, findings), EVENT, log_label="census", log_detail=counts
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
