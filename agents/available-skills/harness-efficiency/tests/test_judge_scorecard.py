from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "judge_scorecard.py"


def load_mod():
    spec = importlib.util.spec_from_file_location("judge_scorecard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class JudgeScorecardSkipTests(unittest.TestCase):
    def test_exits_zero_and_skipped_when_api_key_unset(self) -> None:
        env = os.environ.copy()
        env.pop("TYPESAFE_API_KEY", None)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "missing.md"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["skipped"])
        self.assertEqual(payload["reason"], "TYPESAFE_API_KEY unset")


class JudgeScorecardHelpTests(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("report", completed.stdout)


class JudgeScorecardRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_mod()

    def test_one_system_one_call_includes_all_questions(self) -> None:
        captured: list[dict[str, Any]] = []

        def post(
            url: str,
            headers: dict[str, str],
            body: dict[str, Any],
            timeout: float,
        ) -> dict[str, Any]:
            captured.append(
                {
                    "url": url,
                    "headers": headers,
                    "body": body,
                    "timeout": timeout,
                }
            )
            return {
                "answers": {
                    "primitive": {"type": "choice", "choice": "none"},
                }
            }

        answers = self.mod.evaluate_report(
            Path("/tmp/report.md"),
            "test-key",
            read_text=lambda path: "forensics body",
            post=post,
        )
        self.assertEqual(len(captured), 1)
        call = captured[0]
        self.assertEqual(call["url"], self.mod.SYSTEM_ONE_URL)
        self.assertEqual(call["timeout"], self.mod.HTTP_TIMEOUT_SECONDS)
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        body = call["body"]
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(body["state"], {"report": "forensics body"})
        questions = body["questions"]
        for question_id in self.mod.NOUL_IDS:
            self.assertEqual(questions[question_id]["type"], "noul")
        self.assertEqual(questions["primitive"]["type"], "choice")
        self.assertEqual(
            set(questions["primitive"]["criteria"]),
            set(self.mod.PRIMITIVE_OPTIONS),
        )
        self.assertEqual(questions["friction"]["type"], "score")
        self.assertEqual(
            questions["friction"]["criteria"],
            list(self.mod.FRICTION_LEVELS),
        )
        self.assertEqual(
            answers,
            {"primitive": {"type": "choice", "choice": "none"}},
        )


if __name__ == "__main__":
    unittest.main()
