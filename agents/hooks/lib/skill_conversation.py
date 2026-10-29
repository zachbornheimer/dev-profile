"""Bounded cached routing-context adapters for the skill-pick hook."""

import contextlib
import hashlib
import json
import os
import queue
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 0.25
HISTORY_TURNS = 2
HARNESSES = frozenset({"claude", "grok", "codex", "hermes"})
DEFAULT_HOME = Path.home() / "Developer/Personal/capability-replicas/mastra"
HOME_ENV = "TYPESAFE_CONTEXT_HOME"


def _cache_path(cache_dir: Path, session_id: str, harness: str) -> Path:
    identity = f"{harness}:{session_id}".encode()
    return cache_dir / f"{hashlib.sha256(identity).hexdigest()}.json"


def _read_cache(cache_dir: Path, session_id: str, harness: str) -> dict[str, Any]:
    if not session_id:
        return {}
    try:
        value = json.loads(
            _cache_path(cache_dir, session_id, harness).read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in ("durable_project_context", "conversation_history")
        if value.get(key)
    }


def _write_cache(
    cache_dir: Path,
    session_id: str,
    harness: str,
    context: dict[str, Any],
) -> None:
    if not session_id or not context:
        return
    path = _cache_path(cache_dir, session_id, harness)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(context), encoding="utf-8")
        temporary.replace(path)
    except (OSError, TypeError):
        with contextlib.suppress(OSError, TypeError):
            temporary.unlink(missing_ok=True)


def _observe(name: str, operation: Callable[[], Any], observed: queue.Queue) -> None:
    try:
        observed.put((name, operation()))
    except Exception:
        return


def routing_context(
    session_id: str,
    harness: str,
    prompt: str,
    *,
    durable: Callable[[], dict[str, Any]],
    cache_dir: Path,
    wait_seconds: float,
) -> dict[str, Any]:
    """Observe independent context in parallel and fall back to prior facts."""
    context = _read_cache(cache_dir, session_id, harness)
    observed = queue.Queue()
    observations = (
        ("durable_project_context", durable),
        ("conversation_history", lambda: history(session_id, harness, prompt)),
    )
    for name, operation in observations:
        threading.Thread(
            target=_observe,
            args=(name, operation, observed),
            daemon=True,
            name=f"typesafe-{name}",
        ).start()

    deadline = time.monotonic() + wait_seconds
    for _ in observations:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            name, value = observed.get(timeout=remaining)
        except queue.Empty:
            break
        if value:
            context[name] = value
    _write_cache(cache_dir, session_id, harness, context)
    return context


def history(
    session_id: str,
    harness: str,
    prompt: str,
    run: Callable[..., Any] = subprocess.run,
) -> list[dict[str, Any]]:
    """Retrieve paired turns; never block a prompt on a missing capability."""
    if not session_id or harness not in HARNESSES:
        return []
    conversation = f"{harness}:{session_id}"
    home = Path(os.getenv(HOME_ENV) or DEFAULT_HOME)
    command = (
        "ai-keys::exec aubr capability run get_model_conversation_context --text "
        f"{shlex.quote(conversation)}"
    )
    try:
        result = run(
            ["/bin/zsh", "-lic", command],
            cwd=str(home),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            return []
        output = json.loads(result.stdout).get("output", {})
        if output.get("conversation") != conversation:
            return []
        return prior_turns(output.get("turns_history"), prompt)
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return []


def prior_turns(turns: Any, prompt: str) -> list[dict[str, Any]]:
    """Keep paired turn order, dropping the current prompt and anything after it."""
    if not isinstance(turns, list):
        return []
    prior: list[dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict) or not isinstance(turn.get("conversation"), list):
            return []
        messages = turn["conversation"]
        if any(
            isinstance(message, dict)
            and message.get("speaking") == "user"
            and str(message.get("text", "")).strip() == prompt.strip()
            for message in messages
        ):
            break
        prior.append(turn)
    return prior[-HISTORY_TURNS:]
