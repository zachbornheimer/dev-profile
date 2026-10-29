#!/usr/bin/env python3
"""Pick the next diagnose action with TypeSafe System One.

Code owns the loop. TypeSafe returns typed judgments; this script composes them.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"
SYSTEMONE_MODEL = "jev-latest"
API_KEY_ENV = "TYPESAFE_API_KEY"
REQUEST_TIMEOUT_SECONDS = 30
MISSING_KEY_EXIT = 2
MISSING_KEY_MESSAGE = "TypeSafe key was not in env, keychain, or 1Password"
ONEPASSWORD_TIMEOUT_SECONDS = 15
ONEPASSWORD_ITEM_TITLE = "Typesafe AI API key"
ONEPASSWORD_VAULT = "Personal"
ONEPASSWORD_FIELD = "credential"


def _load_typesafe_modules() -> tuple[Any, Any]:
    scripts = Path(__file__).resolve().parents[2] / "typesafe-ai" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    import constants as typesafe_constants
    import systemone as typesafe_systemone

    return typesafe_systemone, typesafe_constants


typesafe_systemone, typesafe_constants = _load_typesafe_modules()

MITIGATION_PROVEN_THRESHOLD = 0.7
DECLARE_CAUSE_FIT_THRESHOLD = 0.75
NEXT_TEST_CONFIDENCE_THRESHOLD = 0.35
SNAPSHOT_ENOUGH_THRESHOLD = 0.5

MOVE_SNAPSHOT_MORE = "snapshot_more"
MOVE_RUN_TEST = "run_test"
MOVE_MITIGATE = "mitigate"
MOVE_DECLARE_CAUSE = "declare_cause"
MOVE_ADD_HYPOTHESES = "add_hypotheses"
NONE_TEST_ID = "none"
READ_ONLY_BLAST = "read-only"

GUESSED_RUNTIME_TOKENS = ("colima", "docker")
GUESSED_RUNTIME_VERBS = ("restart", "stop", "kill")

Getenv = Callable[..., str | None]
Urlopen = Callable[..., Any]
ReadKey = Callable[[], str | None]
WriteKey = Callable[[str], None]


def contrast(what: str, not_for: str) -> dict[str, str]:
    return {"what": what, "not_for": not_for}


NEXT_MOVE_CRITERIA = {
    MOVE_SNAPSHOT_MORE: contrast(
        "Facts are too thin to falsify anything",
        "A listed test would already kill a group",
    ),
    MOVE_RUN_TEST: contrast(
        "A listed test would kill a group",
        "Facts are too thin, or one open hypothesis already uniquely fits",
    ),
    MOVE_MITIGATE: contrast(
        "A proven reversible stop-the-bleed is already in mitigation and facts",
        "A guessed restart, kill, or unproven Colima/docker bounce",
    ),
    MOVE_DECLARE_CAUSE: contrast(
        "One open hypothesis fits the facts and the others do not",
        "Several open hypotheses still fit, or none do",
    ),
    MOVE_ADD_HYPOTHESES: contrast(
        "The remaining set cannot explain the facts",
        "An open hypothesis still fits",
    ),
}

SPLIT_LAYER_CRITERIA = {
    "client": contrast(
        "The observer, browser, or CLI is the hop to split",
        "A later hop already explains the snapshot",
    ),
    "edge": contrast(
        "Proxy, TLS, auth, or ingress is the hop to split",
        "The request is already past the edge",
    ),
    "app": contrast(
        "The application process is the hop to split",
        "The app is reached and healthy; look elsewhere",
    ),
    "runtime": contrast(
        "Container, VM, or supervisor is the hop to split",
        "The runtime is answering; the fault is above or below",
    ),
    "os": contrast(
        "Host kernel, cgroup, or pid namespace is the hop to split",
        "The host is fine; the fault is in a service or dependency",
    ),
    "disk_net": contrast(
        "Disk, mount, NFS, or network is the hop to split",
        "I/O and network are not in the unexplained slice",
    ),
    "dependency": contrast(
        "An upstream, DB, cache, or NAS is the hop to split",
        "Dependencies answered; the fault is local",
    ),
    "unknown": contrast(
        "The snapshot does not locate a hop", "A named hop already fits"
    ),
}


def load_board(raw: str, source: str) -> dict[str, Any]:
    try:
        board = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid board JSON from {source}: {exc.msg}") from exc
    if not isinstance(board, dict):
        raise TypeError(f"board from {source} must be a JSON object")
    return board


def open_items(board: dict[str, Any]) -> list[dict[str, Any]]:
    items = board.get("open") or []
    if not isinstance(items, list):
        raise TypeError("board.open must be a list")
    return [item for item in items if isinstance(item, dict) and item.get("id")]


def listed_tests(board: dict[str, Any]) -> list[dict[str, Any]]:
    items = board.get("tests") or []
    if not isinstance(items, list):
        raise TypeError("board.tests must be a list")
    return [item for item in items if isinstance(item, dict) and item.get("id")]


def mitigation(board: dict[str, Any]) -> dict[str, Any]:
    value = board.get("mitigation") or {}
    return value if isinstance(value, dict) else {}


def is_guessed_runtime_restart(board: dict[str, Any]) -> bool:
    proposed = str(mitigation(board).get("proposed") or "").lower()
    has_runtime = any(token in proposed for token in GUESSED_RUNTIME_TOKENS)
    has_verb = any(verb in proposed for verb in GUESSED_RUNTIME_VERBS)
    return has_runtime and has_verb


def _choice(
    instructions: str | dict[str, Any], criteria: dict[str, Any]
) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _noul(instructions: str | dict[str, Any], true: str, false: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": instructions,
        "criteria": {"true": true, "false": false},
    }


def build_questions(board: dict[str, Any]) -> dict[str, Any]:
    test_criteria: dict[str, Any] = {
        item["id"]: {
            "kills": item.get("kills"),
            "blast": item.get("blast"),
            "seconds": item.get("seconds"),
        }
        for item in listed_tests(board)
    }
    test_criteria[NONE_TEST_ID] = contrast(
        "No listed test would kill remaining mass, or none is safe enough",
        "A listed test is cheap, read-only, and would split the open set",
    )
    questions: dict[str, Any] = {
        "next_move": _choice(
            "What should diagnosis do next given this board?",
            NEXT_MOVE_CRITERIA,
        ),
        "next_test": _choice(
            {
                "task": (
                    "Pick the cheapest safe test that eliminates "
                    "the most remaining probability"
                ),
                "none": "Choose none when no listed test is worth running",
            },
            test_criteria,
        ),
        "snapshot_enough": _noul(
            "Are snapshot.facts enough to pick a falsifying test?",
            "Facts can already falsify at least one open group",
            "Facts are too thin to pick a listed test",
        ),
        "mitigation_proven": _noul(
            "Is mitigation a proven reversible action given the facts?",
            "Already proven by evidence on this board",
            "Guessed restart, kill, or otherwise unproven",
        ),
        "split_layer": _choice(
            "Which hop should diagnosis split next?",
            SPLIT_LAYER_CRITERIA,
        ),
    }
    for item in open_items(board):
        hypothesis_id = item["id"]
        questions[f"fits__{hypothesis_id}"] = _noul(
            {
                "question": (
                    "Does this hypothesis still fit all facts and "
                    "contradict none of ruled_out?"
                ),
                "hypothesis_id": hypothesis_id,
                "hypothesis": item.get("hypothesis"),
            },
            "Fits every fact; none of ruled_out contradict it",
            "A fact or ruled-out kill makes this hypothesis impossible or incomplete",
        )
    return questions


def build_request(board: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": board,
        "model": SYSTEMONE_MODEL,
        "questions": build_questions(board),
    }


def _choice_answer(answers: dict[str, Any], question_id: str) -> dict[str, Any]:
    answer = answers.get(question_id)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError(f"TypeSafe answer {question_id!r} missing choice fields")
    if "choice" not in answer:
        raise ValueError(f"TypeSafe answer {question_id!r} missing choice")
    return {
        "choice": answer["choice"],
        "confidence": answer.get("confidence", 0.0),
        "probabilities": answer.get("probabilities") or {},
    }


def _noul_answer(answers: dict[str, Any], question_id: str) -> float:
    answer = answers.get(question_id)
    if (
        not isinstance(answer, dict)
        or answer.get("type") != "noul"
        or "noul" not in answer
    ):
        raise ValueError(f"TypeSafe answer {question_id!r} missing noul")
    return float(answer["noul"])


def cheapest_read_only_test(board: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in listed_tests(board)
        if str(item.get("blast") or "") == READ_ONLY_BLAST
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (int(item.get("seconds") or 0), str(item["id"])),
    )


def resolve_test(
    board: dict[str, Any],
    next_test_id: str,
    next_test_confidence: float,
    snapshot_enough: float,
) -> tuple[str, str | None, str | None]:
    by_id = {item["id"]: item for item in listed_tests(board)}
    usable = (
        next_test_id
        and next_test_id != NONE_TEST_ID
        and next_test_confidence >= NEXT_TEST_CONFIDENCE_THRESHOLD
        and next_test_id in by_id
    )
    if usable:
        chosen = by_id[next_test_id]
        return MOVE_RUN_TEST, chosen["id"], chosen.get("command")
    if snapshot_enough < SNAPSHOT_ENOUGH_THRESHOLD:
        return MOVE_SNAPSHOT_MORE, None, None
    cheapest = cheapest_read_only_test(board)
    if cheapest is None:
        return MOVE_SNAPSHOT_MORE, None, None
    return MOVE_RUN_TEST, cheapest["id"], cheapest.get("command")


def compose_move(board: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    next_move = _choice_answer(answers, "next_move")
    next_test = _choice_answer(answers, "next_test")
    snapshot_enough = _noul_answer(answers, "snapshot_enough")
    mitigation_proven = _noul_answer(answers, "mitigation_proven")
    layer = _choice_answer(answers, "split_layer")
    fits = {
        item["id"]: _noul_answer(answers, f"fits__{item['id']}")
        for item in open_items(board)
    }

    action = next_move["choice"]
    if action == MOVE_MITIGATE and (
        mitigation_proven < MITIGATION_PROVEN_THRESHOLD
        or is_guessed_runtime_restart(board)
    ):
        action = MOVE_RUN_TEST
    if action == MOVE_DECLARE_CAUSE and (
        not fits or max(fits.values()) < DECLARE_CAUSE_FIT_THRESHOLD
    ):
        action = MOVE_RUN_TEST

    test_id: str | None = None
    command: str | None = None
    if action == MOVE_RUN_TEST:
        action, test_id, command = resolve_test(
            board,
            str(next_test["choice"]),
            float(next_test["confidence"] or 0.0),
            snapshot_enough,
        )

    return {
        "do": action,
        "test_id": test_id,
        "command": command,
        "layer": layer["choice"],
        "fits": fits,
        "raw": {
            "next_move": next_move,
            "mitigation_proven": mitigation_proven,
        },
    }


def call_systemone(
    payload: dict[str, Any],
    api_key: str,
    urlopen: Urlopen | None = None,
) -> dict[str, Any]:
    opener = urlopen if urlopen is not None else urllib.request.urlopen
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        SYSTEMONE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"TypeSafe request failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"TypeSafe request failed: {exc.reason}") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"TypeSafe response was not JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answers"), dict):
        raise TypeError("TypeSafe response missing answers")
    return parsed


def read_board(path: str | None) -> dict[str, Any]:
    if path:
        board_path = Path(path)
        try:
            raw = board_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read board {path}: {exc}") from exc
        return load_board(raw, path)
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("pass --board PATH or board JSON on stdin")
    return load_board(raw, "stdin")


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def fail(message: str, code: int = 1) -> int:
    print(message, file=sys.stderr)
    return code


def default_read_onepassword() -> str | None:
    try:
        completed = subprocess.run(
            [
                "op",
                "item",
                "get",
                ONEPASSWORD_ITEM_TITLE,
                "--vault",
                ONEPASSWORD_VAULT,
                "--fields",
                ONEPASSWORD_FIELD,
                "--reveal",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=ONEPASSWORD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    api_key = completed.stdout.strip()
    return api_key or None


def default_write_keychain(getenv: Getenv, api_key: str) -> None:
    account = getenv("USER") or ""
    if not account:
        return
    typesafe_systemone.write_generic_password(
        account, typesafe_constants.KEYCHAIN_SERVICE, api_key
    )


def resolve_typesafe_key(
    getenv: Getenv,
    read_keychain: ReadKey,
    read_onepassword: ReadKey,
    write_keychain: WriteKey,
) -> str | None:
    found = typesafe_systemone.resolve_api_key(getenv, read_keychain)
    if found:
        return found
    from_onepassword = read_onepassword()
    if from_onepassword is None:
        return None
    stripped = from_onepassword.strip()
    if not stripped:
        return None
    with contextlib.suppress(RuntimeError):
        write_keychain(stripped)
    return stripped


def main(
    argv: list[str] | None = None,
    *,
    getenv: Getenv = os.getenv,
    urlopen: Urlopen | None = None,
    read_keychain: ReadKey | None = None,
    read_onepassword: ReadKey | None = None,
    write_keychain: WriteKey | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Pick the next diagnose move via TypeSafe System One."
    )
    parser.add_argument(
        "--board", metavar="PATH", help="Board JSON path. Default: stdin."
    )
    parser.add_argument(
        "--print-request",
        action="store_true",
        help="Write the POST body to stdout and exit. No network.",
    )
    args = parser.parse_args(argv)

    try:
        board = read_board(args.board)
        request = build_request(board)
        if args.print_request:
            emit(request)
            return 0

        def from_keychain() -> str | None:
            return typesafe_systemone.default_read_keychain(getenv)

        def persist_key(api_key: str) -> None:
            default_write_keychain(getenv, api_key)

        api_key = resolve_typesafe_key(
            getenv,
            read_keychain if read_keychain is not None else from_keychain,
            read_onepassword
            if read_onepassword is not None
            else default_read_onepassword,
            write_keychain if write_keychain is not None else persist_key,
        )
        if not api_key:
            return fail(MISSING_KEY_MESSAGE, MISSING_KEY_EXIT)
        result = call_systemone(request, api_key, urlopen=urlopen)
        emit(compose_move(board, result["answers"]))
        return 0
    except ValueError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
