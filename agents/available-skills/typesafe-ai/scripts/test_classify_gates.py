"""Behavior tests for classify-isjac, classify-ticket, and classify-oncall."""

from __future__ import annotations

import importlib
import io
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Self
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

constants = importlib.import_module("constants")
cli = importlib.import_module("typesafe")

SECRET = "test-key-not-for-logs"
API_KEY_ENV = constants.API_KEY_ENV
SOURCE_FALLBACK = constants.SOURCE_FALLBACK
SOURCE_TYPESAFE = constants.SOURCE_TYPESAFE
GATES = ("classify-isjac", "classify-ticket", "classify-oncall")
MAIL = {"subject": "Login broken", "from": "a@isjac.org", "body": "cannot sign in"}
TICKET = {
    "title": "Login fails for plus-address emails",
    "body": "Users with + in email cannot sign in.",
    "available_labels": ["Bug", "Feature"],
    "open_titles": ["Unify A2A codec"],
}
ALERT = {
    "alert": "ECS CPU alarm",
    "sentry": "0 events",
    "cloudwatch": "CPU 91%",
    "ecs": "tasks stable",
    "health": "200",
    "deploys": "none",
    "linear": "",
    "slack": "",
}


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def getenv_with_key(name: str, default: str | None = None) -> str | None:
    if name == API_KEY_ENV:
        return SECRET
    return os.getenv(name, default)


def getenv_without_key(name: str, default: str | None = None) -> str | None:
    if name == API_KEY_ENV:
        return None
    return os.getenv(name, default)


def choice_answer(choice: str, confidence: float = 0.8) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {choice: confidence},
    }


def noul_answer(value: float) -> dict:
    return {"type": "noul", "noul": value}


def score_answer(score: float, confidence: float = 0.9) -> dict:
    return {
        "type": "score",
        "score": score,
        "confidence": confidence,
        "probabilities": {"0": 0.0, "1": 0.0, "2": 1.0},
        "legend": {"0": "low", "1": "medium", "2": "high"},
    }


def http_error(code: int, body: bytes = b"overloaded") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.typesafe.ai/v1/systemone",
        code,
        "error",
        None,
        io.BytesIO(body),
    )


def isjac_payload(
    *, kind: str = "product_bug", confidence: float = 0.91, in_scope: float = 0.88
) -> dict:
    return {
        "answers": {
            "kind": choice_answer(kind, confidence),
            "in_scope": noul_answer(in_scope),
        },
        "usage": {"input_tokens": 40, "output_tokens": 6},
    }


def ticket_payload(
    *,
    issue_type: str = "bug",
    priority: str = "p2",
    confidence: float = 0.84,
    maybe_duplicate: float = 0.12,
) -> dict:
    return {
        "answers": {
            "issue_type": choice_answer(issue_type, confidence),
            "priority": choice_answer(priority, 0.8),
            "maybe_duplicate": noul_answer(maybe_duplicate),
        },
        "usage": {"input_tokens": 50, "output_tokens": 8},
    }


def oncall_payload(
    *,
    disposition: str = "real",
    cause_class: str = "infra_failure",
    sev: str = "sev2",
    confidence: float = 0.81,
    score: float = 2.0,
) -> dict:
    return {
        "answers": {
            "disposition": choice_answer(disposition, confidence),
            "cause_class": choice_answer(cause_class, 0.8),
            "sev": choice_answer(sev, 0.8),
            "confidence_band": score_answer(score),
        },
        "usage": {"input_tokens": 60, "output_tokens": 10},
    }


def sample_for(command: str) -> dict:
    if command == "classify-isjac":
        return MAIL
    if command == "classify-ticket":
        return TICKET
    return ALERT


def run_gate(
    command: str,
    payload: dict | str,
    *,
    getenv=getenv_with_key,
    urlopen=None,
    read_keychain=None,
) -> tuple[int, Any, str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    stdout = io.StringIO()
    stderr = io.StringIO()
    keychain = read_keychain if read_keychain is not None else (lambda: None)
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(
            [command, "--json"],
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=keychain,
            stdin=io.StringIO(raw),
            stdout=stdout,
        )
    return code, json.loads(stdout.getvalue()), stderr.getvalue()


class FailOpenTests(unittest.TestCase):
    def test_missing_key_falls_open_for_each_gate(self) -> None:
        urlopen = mock.Mock()
        for command in GATES:
            with self.subTest(command=command):
                code, result, stderr = run_gate(
                    command,
                    sample_for(command),
                    getenv=getenv_without_key,
                    urlopen=urlopen,
                    read_keychain=lambda: None,
                )
                self.assertEqual(code, 0)
                self.assertEqual(result["source"], SOURCE_FALLBACK)
                self.assertNotIn(SECRET, stderr)
        urlopen.assert_not_called()

    def test_http_500_falls_open_for_each_gate(self) -> None:
        urlopen = mock.Mock(side_effect=http_error(500))
        for command in GATES:
            with self.subTest(command=command):
                code, result, _stderr = run_gate(command, sample_for(command), urlopen=urlopen)
                self.assertEqual(code, 0)
                self.assertEqual(result["source"], SOURCE_FALLBACK)

    def test_urlerror_timeout_falls_open_for_each_gate(self) -> None:
        urlopen = mock.Mock(side_effect=urllib.error.URLError("timed out"))
        for command in GATES:
            with self.subTest(command=command):
                code, result, _stderr = run_gate(command, sample_for(command), urlopen=urlopen)
                self.assertEqual(code, 0)
                self.assertEqual(result["source"], SOURCE_FALLBACK)
                self.assertEqual(result["reason"], "timeout")

    def test_empty_stdin_falls_open_without_http(self) -> None:
        urlopen = mock.Mock()
        for command in GATES:
            with self.subTest(command=command):
                code, result, _stderr = run_gate(command, "", urlopen=urlopen)
                self.assertEqual(code, 0)
                self.assertEqual(result["source"], SOURCE_FALLBACK)
        urlopen.assert_not_called()


class IsjacGateTests(unittest.TestCase):
    def test_high_confidence_product_bug_stays_product_bug(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(isjac_payload()))
        code, result, stderr = run_gate("classify-isjac", MAIL, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["kind"], "product_bug")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["in_scope"], 0.88)
        self.assertEqual(result["confidence"], 0.91)
        self.assertNotIn(SECRET, stderr)
        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["state"]["subject"], MAIL["subject"])
        self.assertIn("kind", body["questions"])
        self.assertIn("in_scope", body["questions"])

    def test_product_bug_low_in_scope_rewrites_to_ops_skip(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(isjac_payload(in_scope=0.2)))
        code, result, _stderr = run_gate("classify-isjac", MAIL, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["kind"], "ops_skip")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["reason"], "in_scope below floor")
        self.assertEqual(result["in_scope"], 0.2)

    def test_low_confidence_falls_open(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(isjac_payload(confidence=0.40)))
        code, result, _stderr = run_gate("classify-isjac", MAIL, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["kind"], "unknown")
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        urlopen.assert_called_once()


class TicketGateTests(unittest.TestCase):
    def test_bug_maps_to_available_bug_label(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(ticket_payload()))
        code, result, _stderr = run_gate("classify-ticket", TICKET, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["issue_type"], "bug")
        self.assertEqual(result["label"], "Bug")
        self.assertEqual(result["priority"], 2)
        self.assertEqual(result["maybe_duplicate"], 0.12)
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["confidence"], 0.84)

    def test_bug_with_feature_only_labels_emits_empty_label(self) -> None:
        payload = dict(TICKET)
        payload["available_labels"] = ["Feature"]
        urlopen = mock.Mock(return_value=FakeHTTPResponse(ticket_payload()))
        code, result, _stderr = run_gate("classify-ticket", payload, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["issue_type"], "bug")
        self.assertEqual(result["label"], "")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)


class OncallGateTests(unittest.TestCase):
    def test_real_keeps_sev2(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(oncall_payload()))
        code, result, _stderr = run_gate("classify-oncall", ALERT, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["disposition"], "real")
        self.assertEqual(result["cause_class"], "infra_failure")
        self.assertEqual(result["sev"], "sev2")
        self.assertEqual(result["confidence_band"], "high")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["confidence"], 0.81)

    def test_noise_forces_sev_none(self) -> None:
        urlopen = mock.Mock(
            return_value=FakeHTTPResponse(
                oncall_payload(disposition="noise", sev="sev2", score=0.0)
            )
        )
        code, result, _stderr = run_gate("classify-oncall", ALERT, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["disposition"], "noise")
        self.assertEqual(result["sev"], "none")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["confidence_band"], "low")

    def test_low_confidence_falls_open(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(oncall_payload(confidence=0.4)))
        code, result, _stderr = run_gate("classify-oncall", ALERT, urlopen=urlopen)
        self.assertEqual(code, 0)
        self.assertEqual(result["disposition"], "unknown")
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
