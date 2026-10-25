"""Behavior tests for the TypeSafe answer field readers."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

answers = importlib.import_module("answers")


class ChoiceDistributionTests(unittest.TestCase):
    def test_reads_the_probability_for_every_option(self) -> None:
        payload = {
            "area": {
                "type": "choice",
                "choice": "area:homelab",
                "confidence": 0.81,
                "probabilities": {"area:homelab": 0.81, "area:ventures": 0.12, "other": 0.07},
            }
        }
        self.assertEqual(
            answers.choice_distribution(payload, "area"),
            {"area:homelab": 0.81, "area:ventures": 0.12, "other": 0.07},
        )

    def test_missing_question_raises(self) -> None:
        with self.assertRaises(ValueError):
            answers.choice_distribution({}, "area")

    def test_wrong_answer_type_raises(self) -> None:
        payload = {"area": {"type": "noul", "noul": 0.5}}
        with self.assertRaises(ValueError):
            answers.choice_distribution(payload, "area")

    def test_missing_probabilities_raises(self) -> None:
        # Matches the reader style of choice()/noul(): a Choice answer that carries a
        # winning option but no distribution must not be silently treated as one.
        payload = {"area": {"type": "choice", "choice": "area:homelab", "confidence": 0.81}}
        with self.assertRaises(ValueError):
            answers.choice_distribution(payload, "area")

    def test_empty_probabilities_raises(self) -> None:
        payload = {
            "area": {
                "type": "choice",
                "choice": "area:homelab",
                "confidence": 0.81,
                "probabilities": {},
            }
        }
        with self.assertRaises(ValueError):
            answers.choice_distribution(payload, "area")


if __name__ == "__main__":
    unittest.main()
