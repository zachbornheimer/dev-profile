#!/usr/bin/env python3
"""Batch TypeSafe System One judgments over a forensics report."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

API_KEY_ENV = "TYPESAFE_API_KEY"
SYSTEM_ONE_URL = "https://api.typesafe.ai/v1/systemone"
SYSTEM_ONE_MODEL = "jev-latest"
HTTP_TIMEOUT_SECONDS = 30
ERROR_BODY_LIMIT = 500
SKIP_REASON_UNSET = f"{API_KEY_ENV} unset"
CONTENT_TYPE_JSON = "application/json"

NOUL_IDS = (
    "intent_recognized",
    "intent_accomplished_verified",
    "faster_than_human",
    "turns_proportionate",
    "subagents_justified",
    "should_have_split",
    "user_frustrated",
)
PRIMITIVE_OPTIONS = (
    "command",
    "script",
    "skill",
    "hook",
    "subagent",
    "routing",
    "removal",
    "none",
)
FRICTION_LEVELS = (
    "no extra steering",
    "some corrections",
    "user had to fight the session",
)

PostJson = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]
ReadText = Callable[[Path], str]


class JudgeError(Exception):
    """A forensics report could not be judged."""


def _noul(instructions: str, yes: str, no: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": instructions,
        "criteria": {"true": yes, "false": no},
    }


SCORECARD_QUESTIONS: dict[str, dict[str, Any]] = {
    "intent_recognized": _noul(
        "Did the agent recognize the user's actual intent in this forensics report?",
        "The agent identified the one intended task.",
        "The agent missed the intent or piled on extra work.",
    ),
    "intent_accomplished_verified": _noul(
        "Was the intended outcome verified as accomplished, not merely claimed?",
        "The report shows verified evidence the intent was accomplished.",
        "Accomplishment is claimed without verification, or the intent failed.",
    ),
    "faster_than_human": _noul(
        "Was this session faster than a competent human doing the same work?",
        "The agent finished faster than a human would have.",
        "A human would have been as fast or faster.",
    ),
    "turns_proportionate": _noul(
        "Were the turns and tokens proportionate to the task?",
        "Turn and token cost matched the task's complexity.",
        "The session used far more turns or tokens than the task needed.",
    ),
    "subagents_justified": _noul(
        "Were spawned subagents justified by the work?",
        "Each subagent did isolated work whose raw output would flood the parent.",
        "Subagents were unnecessary, sequential, or did parent-owned work.",
    ),
    "should_have_split": _noul(
        "Should this session have been split into separate tasks or sessions?",
        "Multiple independent intents or jobs were piled into one session.",
        "The session was one coherent task.",
    ),
    "user_frustrated": _noul(
        "Does the report show the user was frustrated?",
        "The user had to fight the session, correct the agent, or express frustration.",
        "The user did not have to fight the session.",
    ),
    "primitive": {
        "type": "choice",
        "instructions": (
            "Which smallest durable primitive should encode the next fix "
            "for this session's waste?"
        ),
        "criteria": {
            "command": "Same argv every time; no judgment.",
            "script": "Deterministic mechanics encoded in a script.",
            "skill": "On-demand procedure the model must follow.",
            "hook": "Must fire even if the model forgets.",
            "subagent": "Work whose raw output would flood the parent.",
            "routing": "Send tiny or mechanical work to a cheaper model.",
            "removal": "An existing instruction is the waste; delete it.",
            "none": "One-off or already fixed; no primitive.",
        },
    },
    "friction": {
        "type": "score",
        "instructions": "How much extra steering did the user have to give?",
        "criteria": list(FRICTION_LEVELS),
    },
}


def skip_payload() -> dict[str, Any]:
    return {"skipped": True, "reason": SKIP_REASON_UNSET}


def api_key(environ: Mapping[str, str]) -> str | None:
    raw = environ.get(API_KEY_ENV)
    if raw is None:
        return None
    key = raw.strip()
    return key or None


def scorecard_request(report: str) -> dict[str, Any]:
    return {
        "state": {"report": report},
        "model": SYSTEM_ONE_MODEL,
        "questions": SCORECARD_QUESTIONS,
    }


def answers_from(response: dict[str, Any]) -> dict[str, Any]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JudgeError("system one response missing answers")
    return answers


def _clip_error_body(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    if len(text) <= ERROR_BODY_LIMIT:
        return text
    return text[:ERROR_BODY_LIMIT]


def post_json(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _clip_error_body(exc.read())
        raise JudgeError(f"system one HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise JudgeError(f"system one request failed for {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise JudgeError(f"system one returned invalid JSON from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise JudgeError(f"system one returned a non-object from {url}")
    return payload


def read_report(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JudgeError(f"failed to read forensics report {path}: {exc}") from exc


def evaluate_report(
    report_path: Path,
    key: str,
    read_text: ReadText,
    post: PostJson,
) -> dict[str, Any]:
    report = read_text(report_path)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": CONTENT_TYPE_JSON,
    }
    response = post(
        SYSTEM_ONE_URL,
        headers,
        scorecard_request(report),
        HTTP_TIMEOUT_SECONDS,
    )
    return answers_from(response)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="judge_scorecard",
        description="Batch TypeSafe System One judgments over a forensics report.",
    )
    parser.add_argument("report", type=Path, help="Path to a forensics markdown report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    key = api_key(os.environ)
    if key is None:
        print(json.dumps(skip_payload()))
        return 0
    try:
        answers = evaluate_report(
            args.report,
            key,
            read_text=read_report,
            post=post_json,
        )
    except JudgeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(answers, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
