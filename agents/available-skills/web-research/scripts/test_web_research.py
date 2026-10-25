"""Routes taken from Zach's research asks. The script is wrong if these drift."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

_SCRIPT = Path(__file__).with_name("web-research.py")
_spec = importlib.util.spec_from_file_location("web_research", _SCRIPT)
assert _spec is not None and _spec.loader is not None
wr = importlib.util.module_from_spec(_spec)
sys.modules["web_research"] = wr
_spec.loader.exec_module(wr)

TODAY = date(2026, 10, 13)


class RouteTests(unittest.TestCase):
    def test_deep_on_this_is_a_brief_not_a_chat_survey(self) -> None:
        got = wr.route_message("do deep research on this", TODAY)
        self.assertEqual(got.depth, "deep")
        self.assertEqual(got.bind, "thread")
        self.assertEqual(got.workers, 3)
        self.assertTrue(got.write_file)
        self.assertEqual(got.after, "answer")

    def test_discuss_stops(self) -> None:
        got = wr.route_message("do some web research then we should discuss", TODAY)
        self.assertEqual(got.depth, "quick")
        self.assertEqual(got.after, "discuss")
        self.assertFalse(got.write_file)
        self.assertEqual(got.workers, 0)

    def test_discuss_beats_act(self) -> None:
        got = wr.route_message("set it up then we should discuss", TODAY)
        self.assertEqual(got.after, "discuss")
        self.assertFalse(got.parent_continues)

    def test_set_it_up_acts(self) -> None:
        text = "Please do web research. Apparently grok import is supported. Please set it up"
        got = wr.route_message(text, TODAY)
        self.assertEqual(got.after, "act")
        self.assertEqual(got.depth, "quick")
        self.assertEqual(got.bind, "stated")

    def test_one_cheap_subagent(self) -> None:
        text = "Have a subagent do web research on the ideal ticket. use a cheaper model"
        got = wr.route_message(text, TODAY)
        self.assertEqual(got.workers, 1)
        self.assertTrue(got.cheap_model)
        self.assertEqual(got.depth, "quick")

    def test_subagent_plus_continue_does_not_block_the_parent(self) -> None:
        text = "have a subagent do research. Please continue the implementation"
        got = wr.route_message(text, TODAY)
        self.assertEqual(got.workers, 1)
        self.assertEqual(got.after, "act")
        self.assertTrue(got.parent_continues)

    def test_july_2026_floor(self) -> None:
        text = "make sure that the research is coming from July 2026 and newer"
        got = wr.route_message(text, TODAY)
        self.assertEqual(got.not_before, "2026-07-01")
        self.assertEqual(got.recency, "dated")

    def test_mutex_stays_quick(self) -> None:
        got = wr.route_message("do web research to see if we need the mutex", TODAY)
        self.assertEqual(got.depth, "quick")
        self.assertEqual(got.workers, 0)
        self.assertFalse(got.write_file)

    def test_challenge_voids_memory_and_binds_the_thread(self) -> None:
        got = wr.route_message("Can you do research on this? i don't think you're right", TODAY)
        self.assertTrue(got.challenge)
        self.assertEqual(got.bind, "thread")
        self.assertEqual(got.not_before, "2026-01-01")
        self.assertEqual(got.recency, "this-year")

    def test_best_practice_requires_this_year(self) -> None:
        got = wr.route_message("do web research on best practices", TODAY)
        self.assertEqual(got.recency, "this-year")
        self.assertEqual(got.not_before, "2026-01-01")

    def test_named_path_is_stated_even_with_this(self) -> None:
        text = "Do web research for ~/.config/worktrunk/config.toml - useful aliases on this"
        got = wr.route_message(text, TODAY)
        self.assertEqual(got.bind, "stated")

    def test_deep_web_research_onthis_is_deep_and_thread(self) -> None:
        got = wr.route_message("Please do deep web research onthis", TODAY)
        self.assertEqual(got.depth, "deep")
        self.assertEqual(got.bind, "thread")
        self.assertTrue(got.write_file)

    def test_empty_message_fails(self) -> None:
        with self.assertRaises(ValueError):
            wr.route_message("  \n", TODAY)


class QuoteTests(unittest.TestCase):
    page = "Ice floats because it is less dense\nthan liquid water."

    def test_whitespace_does_not_save_a_paraphrase(self) -> None:
        self.assertIsNone(wr.quote_in_page("Ice floats because it is less dense than liquid water.", self.page))
        self.assertEqual(
            wr.quote_in_page("Ice floats because it is lighter than liquid water.", self.page),
            "quote is not in the page",
        )

    def test_short_quote_rejected(self) -> None:
        self.assertIn("shorter", wr.quote_in_page("Ice floats", self.page) or "")


if __name__ == "__main__":
    unittest.main()
