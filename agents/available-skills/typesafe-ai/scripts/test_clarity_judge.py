"""judge-clarity policy. No network."""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

clarity_judge = importlib.import_module("clarity_judge")


def noul(value: float) -> dict:
    return {"type": "noul", "noul": value}


def answers(*, explanation: float, opening: float, words: float, table: float) -> dict:
    return {
        clarity_judge.QUESTION_IS_EXPLANATION: noul(explanation),
        clarity_judge.QUESTION_PLAIN_OPENING: noul(opening),
        clarity_judge.QUESTION_EVERYDAY_WORDS: noul(words),
        clarity_judge.QUESTION_COUNTS_IN_A_TABLE: noul(table),
    }


class DecideTests(unittest.TestCase):
    def test_jargon_report_blocks_on_the_rules_that_failed_cleanly(self) -> None:
        verdict = clarity_judge.decide(
            answers(explanation=0.95, opening=0.03, words=0.02, table=0.05),
            {"message": "report", "prose": "report"},
            {},
        )
        self.assertEqual(verdict.action, clarity_judge.ACTION_BLOCK)
        self.assertEqual(
            verdict.failed,
            (
                clarity_judge.QUESTION_PLAIN_OPENING,
                clarity_judge.QUESTION_EVERYDAY_WORDS,
                clarity_judge.QUESTION_COUNTS_IN_A_TABLE,
            ),
        )
        self.assertIn("15-year-old", verdict.reason)
        self.assertIn("markdown table", verdict.reason)

    def test_middle_score_does_not_block(self) -> None:
        verdict = clarity_judge.decide(
            answers(explanation=0.95, opening=0.75, words=0.44, table=0.27),
            {"message": "report", "prose": "report"},
            {},
        )
        self.assertEqual(verdict.action, clarity_judge.ACTION_ALLOW)

    def test_short_status_is_not_forced_into_a_report_shape(self) -> None:
        verdict = clarity_judge.decide(
            answers(explanation=0.10, opening=0.03, words=0.02, table=0.05),
            {"message": "done", "prose": "done"},
            {},
        )
        self.assertEqual(verdict.action, clarity_judge.ACTION_ALLOW)

    def test_clear_report_allows(self) -> None:
        verdict = clarity_judge.decide(
            answers(explanation=0.95, opening=0.91, words=0.88, table=0.96),
            {"message": "report", "prose": "report"},
            {},
        )
        self.assertEqual(verdict.action, clarity_judge.ACTION_ALLOW)
        self.assertEqual(verdict.failed, ())

    def test_load_state_rejects_an_empty_message(self) -> None:
        with self.assertRaises(ValueError):
            clarity_judge.load_state(json.dumps({"message": "  "}))


if __name__ == "__main__":
    unittest.main()
