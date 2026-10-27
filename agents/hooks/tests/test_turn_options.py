"""The canary is a real prompt, not a toy fixture."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib" / "turn_options.py"
_spec = importlib.util.spec_from_file_location("turn_options", _LIB)
assert _spec is not None and _spec.loader is not None
turn_options = importlib.util.module_from_spec(_spec)
sys.modules["turn_options"] = turn_options
_spec.loader.exec_module(turn_options)

CANARY = "Please do deep web research onthis"
# What pick-skill returned for that phrase on 2026-10-13.
PICK = {
    "choice": "web-research",
    "paths": ["/Users/zbornheimer/.agents/available-skills/web-research/SKILL.md"],
    "shortlist": ["web-research", "investigate", "seo-firecrawl"],
    "fits": {"web-research": 0.93, "investigate": 0.56, "seo-firecrawl": 0.17},
}


class TurnOptionsTests(unittest.TestCase):
    def test_canary_injects_several_skills_and_tools(self) -> None:
        text = turn_options.render_turn_context(CANARY, PICK)
        self.assertIsNotNone(text)
        assert text is not None
        for name in ("web-research", "investigate", "seo-firecrawl"):
            self.assertIn(name, text)
        for tool in ("hermes_web_search", "web_extract", "browser_exec"):
            self.assertIn(tool, text)
        self.assertNotIn("Follow it.", text)
        self.assertIn("not the only option", text)

    def test_higher_fit_is_not_called_the_best_match(self) -> None:
        text = turn_options.render_turn_context(
            "are you happy with how that works?",
            {
                "choice": "self-improve",
                "shortlist": ["self-improve", "skill-creator"],
                "fits": {"self-improve": 0.51, "skill-creator": 0.54},
                "paths": [],
            },
        )
        assert text is not None
        self.assertIn("skill-creator has a higher fit", text)
        self.assertNotIn("The chosen skill is the best match", text)

    def test_unrelated_prompt_does_not_invent_research_tools(self) -> None:
        text = turn_options.render_turn_context(
            "need a skill for this",
            {"choice": "zq", "shortlist": [], "paths": []},
        )
        self.assertIsNotNone(text)
        assert text is not None
        self.assertNotIn("hermes_web_search", text)
        self.assertIn("zq", text)


if __name__ == "__main__":
    unittest.main()
