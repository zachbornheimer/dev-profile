#!/usr/bin/env python3
"""UserPromptSubmit hook: restructure long dictated prompts for the agent.

A prompt is rewritten only when both hold:
  1. `tokuin --model gpt-4` counts more than DICTATION_REWRITE_TOKEN_LIMIT tokens (default 500). Checked first:
     it is local, so a short prompt never reaches the network.
  2. A TypeSafe judgment says it was dictated: the mean of the three P(yes) answers in
     schemas/dictation-questions.json is at least DICTATION_REWRITE_MIN_SCORE (default 0.5).

The rewrite is `capability run rewrite_dictated_text`. A prompt hook cannot replace the user's message, so the
rewrite is added as context in a <reworked-user-input> tag. On any failure (tokuin, TypeSafe, the capability, a
timeout) the hook prints nothing and the original input stands alone.

Environment:
  DICTATION_REWRITE_TOKEN_LIMIT  token ceiling before a dictated prompt is rewritten (default 500)
  DICTATION_REWRITE_MIN_SCORE    dictation score from 0 to 1 that counts as dictated (default 0.5)
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
from typesafe_location import TYPESAFE_SCRIPTS_DIR

HOOK_NAME = "dictation-rewrite"
EVENT_NAME = "UserPromptSubmit"

TOKEN_LIMIT_ENV = "DICTATION_REWRITE_TOKEN_LIMIT"
DEFAULT_TOKEN_LIMIT = 500
MIN_SCORE_ENV = "DICTATION_REWRITE_MIN_SCORE"
DEFAULT_MIN_SCORE = 0.5

TOKENIZER_MODEL = "gpt-4"
TOKENIZER_TIMEOUT_SECONDS = 5.0
# TypeSafe judges the start of a long prompt: dictation shows within a few thousand characters.
JUDGED_MAX_CHARS = 8000
# The hook must finish inside its 60 s agent-hooks timeout; the rewrite gets what the checks leave. The routed model
# reasons before it answers (15 to 40 s for a long prompt), so a shorter budget drops most rewrites.
HOOK_BUDGET_SECONDS = 58.0
MIN_REWRITE_SECONDS = 5.0
ERROR_LINE_MAX_CHARS = 200

QUESTIONS_FILE = Path(__file__).resolve().parent / "schemas" / "dictation-questions.json"
KEYS_FILE = Path.home() / ".cache/ai/keys.env"
CAPABILITY_FALLBACK = Path.home() / ".local/share/aube/bin/capability"
NESTED_RUN_ENV = "AGENTMUX_NESTED_RUN"
KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$")
# A prompt another program sent (a tag-wrapped payload) was not dictated.
TAG_WRAPPED = re.compile(r"\A\s*<([A-Za-z][\w:.-]*)(?:\s[^>]*)?>.*</\1>\s*\Z", re.DOTALL)

REWORKED_NOTE = "This input was altered from its original form to make dictated text more structured"
REWORKED_TEMPLATE = '<reworked-user-input note="{note}">\n{text}\n</reworked-user-input>'

PROMPT_KEYS = (("prompt", "userPrompt"), ("user_prompt", "userPrompt"), ("text", "text"), ("message", "message"))


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


def load_keys(path: Path = KEYS_FILE, env: dict[str, str] | None = None) -> None:
    """Copies keys from the shared keys file into `env` (default: this process) where unset."""
    target = os.environ if env is None else env
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        found = KEY_LINE.match(line)
        if found and not target.get(found.group(1)):
            target[found.group(1)] = found.group(2).strip().strip("'\"")


def count_tokens(text: str) -> int:
    try:
        done = subprocess.run(
            ["tokuin", "--model", TOKENIZER_MODEL, "--format", "json"],
            input=text,
            capture_output=True,
            text=True,
            timeout=TOKENIZER_TIMEOUT_SECONDS,
            check=False,
        )
        if done.returncode != 0:
            raise Unavailable(f"tokuin exit {done.returncode}")
        return int(json.loads(done.stdout)["tokens"])
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        raise Unavailable(f"tokuin {type(exc).__name__}") from exc


def dictation_score(message: str) -> float:
    """Mean P(yes) over the dictation questions, asked of TypeSafe in one call."""
    sys.path.append(str(TYPESAFE_SCRIPTS_DIR))
    try:
        import constants
        import systemone

        questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
        key = systemone.resolve_api_key(os.getenv, lambda: systemone.default_read_keychain(os.getenv))
        if not key:
            raise Unavailable("no TypeSafe key")
        reply = systemone.ask(
            {
                "model": constants.MODEL,
                "state": {"user_message": message[:JUDGED_MAX_CHARS]},
                "questions": questions,
            },
            key,
        )
        answers = reply["answers"]
        return sum(float(answers[name]["noul"]) for name in questions) / len(questions)
    except Unavailable:
        raise
    except (ImportError, OSError, ValueError, KeyError, TypeError, systemone.JudgmentError) as exc:
        raise Unavailable(f"typesafe {type(exc).__name__}") from exc


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
            [capability_binary(), "run", "rewrite_dictated_text", "--input", json.dumps({"text": text})],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd if Path(cwd).is_dir() else Path.home(),
            env=env,
            check=False,
        )
        if done.returncode != 0:
            raise Unavailable(f"capability exit {done.returncode}: {failure_line(done.stderr)}")
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
    limit = int(threshold(TOKEN_LIMIT_ENV, DEFAULT_TOKEN_LIMIT))
    min_score = threshold(MIN_SCORE_ENV, DEFAULT_MIN_SCORE)
    try:
        tokens = count_tokens(prompt)
        if tokens <= limit:
            return Decision.no_objection(f"tokens={tokens} limit={limit}", log_label="short")
        load_keys()
        score = dictation_score(prompt)
        if score < min_score:
            return Decision.no_objection(f"tokens={tokens} score={score:.2f} min={min_score}", log_label="typed")
        remaining = max(MIN_REWRITE_SECONDS, HOOK_BUDGET_SECONDS - (time.monotonic() - started))
        rewritten = rewrite(prompt, remaining, event.field("cwd", "CWD"))
    except Unavailable as exc:
        return Decision.no_objection(f"original kept: {exc}", log_label="unavailable")
    context = REWORKED_TEMPLATE.format(note=REWORKED_NOTE, text=rewritten)
    return Decision.context(
        context,
        event_name=EVENT_NAME,
        log_label="reworked",
        log_detail=f"tokens={tokens} score={score:.2f} chars {len(prompt)}->{len(rewritten)}",
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
