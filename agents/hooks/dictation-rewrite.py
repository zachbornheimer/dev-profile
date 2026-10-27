#!/usr/bin/env python3
"""UserPromptSubmit consumer: rewrite a long dictated prompt using shared batch answers.

The prompt-submit batch includes dictation questions only at 500 or more characters. This hook reads those answers
and calls `capability run rewrite_dictated_text` only when their mean P(yes) clears DICTATION_REWRITE_MIN_SCORE.
The rewritten text is added as context because a prompt hook cannot replace the user's message.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "dictation-rewrite"
EVENT_NAME = "UserPromptSubmit"

MIN_SCORE_ENV = "DICTATION_REWRITE_MIN_SCORE"
DEFAULT_MIN_SCORE = 0.5

# The hook must finish inside its 60 s agent-hooks timeout; the rewrite gets what the checks leave. The routed model
# reasons before it answers (15 to 40 s for a long prompt), so a shorter budget drops most rewrites.
HOOK_BUDGET_SECONDS = 58.0
MIN_REWRITE_SECONDS = 5.0
ERROR_LINE_MAX_CHARS = 200

CAPABILITY_FALLBACK = Path.home() / ".local/share/aube/bin/capability"
NESTED_RUN_ENV = "AGENTMUX_NESTED_RUN"
# A prompt another program sent (a tag-wrapped payload) was not dictated.
TAG_WRAPPED = re.compile(
    r"\A\s*<([A-Za-z][\w:.-]*)(?:\s[^>]*)?>.*</\1>\s*\Z", re.DOTALL
)

REWORKED_NOTE = "This input was altered from its original form to make dictated text more structured"
REWORKED_TEMPLATE = (
    '<reworked-user-input note="{note}">\n{text}\n</reworked-user-input>'
)

PROMPT_KEYS = (
    ("prompt", "userPrompt"),
    ("user_prompt", "userPrompt"),
    ("text", "text"),
    ("message", "message"),
)


class Unavailable(Exception):
    """A step could not give an answer; the original input stands."""


def threshold(name: str, default: float, env: Mapping[str, str] = os.environ) -> float:
    try:
        return float(env.get(name, ""))
    except ValueError:
        return default


def prompt_of(event: HookEvent) -> str:
    for snake, camel in PROMPT_KEYS:
        text = event.field(snake, camel)
        if text.strip():
            return text
    return ""


DICTATION_ANSWER_FIELDS = (
    "likely_dictated",
    "speech_disfluencies",
    "transcription_artifacts",
)


def dictation_score(answers: Mapping[str, object]) -> float:
    """Mean P(yes) over the dictation answers produced by prompt_submit_questions."""
    try:
        scores = [float(answers[field]) for field in DICTATION_ANSWER_FIELDS]
    except (KeyError, TypeError, ValueError) as exc:
        raise Unavailable("dictation answers are missing or invalid") from exc
    if not all(0.0 <= score <= 1.0 for score in scores):
        raise Unavailable("dictation answers are outside 0..1")
    return sum(scores) / len(scores)


def capability_binary() -> str:
    return shutil.which("capability") or str(CAPABILITY_FALLBACK)


def failure_line(stderr: str) -> str:
    """The last non-empty stderr line, bounded, so the log says why the capability failed."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1][:ERROR_LINE_MAX_CHARS] if lines else "no stderr"


def rewrite(text: str, timeout: float, cwd: str) -> str:
    env = {**os.environ, NESTED_RUN_ENV: "1"}
    try:
        done = subprocess.run(
            [
                capability_binary(),
                "run",
                "rewrite_dictated_text",
                "--input",
                json.dumps({"text": text}),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd if Path(cwd).is_dir() else Path.home(),
            env=env,
            check=False,
        )
        if done.returncode != 0:
            raise Unavailable(
                f"capability exit {done.returncode}: {failure_line(done.stderr)}"
            )
        rewritten = json.loads(done.stdout)["output"]
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        raise Unavailable(f"capability {type(exc).__name__}") from exc
    if not isinstance(rewritten, str) or not rewritten.strip():
        raise Unavailable("capability returned no text")
    return rewritten.strip()


def decide(event: HookEvent) -> Decision | None:
    started = time.monotonic()
    prompt = prompt_of(event)
    if not prompt or os.environ.get(NESTED_RUN_ENV) or TAG_WRAPPED.match(prompt):
        return None
    if len(prompt) < 500:
        return Decision.no_objection(
            f"characters={len(prompt)} limit=500", log_label="short"
        )
    min_score = threshold(MIN_SCORE_ENV, DEFAULT_MIN_SCORE)
    answers = event.payload.get("answers")
    if not isinstance(answers, Mapping):
        return Decision.no_objection(
            "batch answers unavailable", log_label="unavailable"
        )
    try:
        score = dictation_score(answers)
        if score < min_score:
            return Decision.no_objection(
                f"score={score:.2f} min={min_score}", log_label="typed"
            )
        remaining = max(
            MIN_REWRITE_SECONDS, HOOK_BUDGET_SECONDS - (time.monotonic() - started)
        )
        rewritten = rewrite(prompt, remaining, event.field("cwd", "CWD"))
    except Unavailable as exc:
        return Decision.no_objection(f"original kept: {exc}", log_label="unavailable")
    context = REWORKED_TEMPLATE.format(note=REWORKED_NOTE, text=rewritten)
    return Decision.context(
        context,
        event_name=EVENT_NAME,
        log_label="reworked",
        log_detail=f"score={score:.2f} chars {len(prompt)}->{len(rewritten)}",
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
