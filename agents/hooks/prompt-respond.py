#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""UserPromptSubmit: ask the prompt question file, then run what the answers route to.

One capability call answers every question in the file (``prompt_answers``).
The route table (``prompt-respond-routes.json``) names the script an answer
starts. A yes/no answer is P(yes); a route fires at or above its bar.
``Frustrated`` at 0.7 starts ``frustration-learn.py --judged``, which runs
learn-from-transcript once per session.

Adding a question is a key in the question file. Adding a reaction is a row
in the route table. This script does not grow a branch for either.

A learner session, a nested run, an empty prompt, and a tag-wrapped prompt
ask nothing. A failed call asks nothing and starts nothing: the prompt
goes through.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook
from prompt_routes import Route, routes_for

HOOK_NAME = "prompt-respond"
CAPABILITY = "prompt_answers"
HOOKS = Path(__file__).resolve().parent
ROUTES_FILE = HOOKS / "prompt-respond-routes.json"
GUARD = HOOKS / "nested-run-guard.sh"
KEYS_FILE = Path.home() / ".cache/ai/keys.env"
CAPABILITY_BIN = Path.home() / ".local/share/aube/bin/capability"
ASK_TIMEOUT_SECONDS = 25
ROUTE_TIMEOUT_SECONDS = 5
PROMPT_MAX_CHARS = 4000
KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$")
TAG_WRAPPED = re.compile(r"\A\s*<([A-Za-z][\w:.-]*)(?:\s[^>]*)?>.*</\1>\s*\Z", re.DOTALL)
PROMPT_KEYS = ("prompt", "user_prompt", "text", "message")


def load_keys(env: dict[str, str]) -> None:
    try:
        lines = KEYS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        found = KEY_LINE.match(line)
        if found and not env.get(found.group(1)):
            env[found.group(1)] = found.group(2).strip().strip("'\"")


def prompt_of(event: HookEvent) -> str:
    for key in PROMPT_KEYS:
        text = event.field(key, key)
        if text.strip() and not TAG_WRAPPED.match(text):
            return text[:PROMPT_MAX_CHARS]
    return ""


def nested(env: dict[str, str]) -> bool:
    if env.get("AGENTMUX_NESTED_RUN"):
        return True
    try:
        done = subprocess.run([str(GUARD)], check=False, env=env)
    except OSError:
        return False
    return done.returncode != 0


def load_routes(path: Path) -> tuple[Route, ...]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        Route(row["field"], float(row["at_least"]), tuple(row["argv"])) for row in rows
    )


def ask(prompt: str, env: dict[str, str]) -> dict[str, object]:
    """The amalgamated answers, or empty when the call cannot answer."""
    override = env.get("PROMPT_ANSWERS_CMD")
    argv = [override] if override else [
        str(CAPABILITY_BIN),
        "run",
        CAPABILITY,
        "--input",
        json.dumps({"text": prompt}),
    ]
    child = dict(env)
    child["AGENTMUX_NESTED_RUN"] = "1"
    if not override:
        load_keys(child)
        child["PATH"] = f"{CAPABILITY_BIN.parent}:{child.get('PATH', '')}"
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=ASK_TIMEOUT_SECONDS,
            env=child,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if done.returncode != 0:
        return {}
    try:
        answers = json.loads(done.stdout)["output"]["answers"]
    except (ValueError, KeyError, TypeError):
        return {}
    return answers if isinstance(answers, dict) else {}


def execute(argv: tuple[str, ...], payload: str, env: dict[str, str]) -> None:
    program = argv[0] if argv[0].startswith("/") else str(HOOKS / argv[0])
    subprocess.run(
        [program, *argv[1:]],
        input=payload,
        capture_output=True,
        text=True,
        timeout=ROUTE_TIMEOUT_SECONDS,
        env=env,
        check=False,
    )


def respond(event: HookEvent) -> Decision | None:
    env = dict(os.environ)
    if env.get("LEARNER") == "1" or nested(env):
        return None
    prompt = prompt_of(event)
    if not prompt:
        return None

    answers = ask(prompt, env)
    routes = load_routes(Path(env.get("PROMPT_RESPOND_ROUTES", str(ROUTES_FILE))))
    plan = routes_for(answers, routes)
    payload = json.dumps(event.payload)
    for routed in plan:
        execute(routed.argv, payload, env)
    fired = ",".join(item.field for item in plan) or "none"
    return Decision.no_objection(f"routes={fired}", log_label="ask")


if __name__ == "__main__":
    run_hook(HOOK_NAME, respond)
