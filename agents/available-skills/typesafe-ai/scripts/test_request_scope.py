"""History cannot crowd out the current skill request."""

import unittest

import pick
import rerank
from catalog import Skill


class RequestScopeTests(unittest.TestCase):
    def test_both_requests_prioritize_current_prompt_when_history_is_present(self):
        state = {"prompt": "current", "context": {"conversation_history": [{"id": 1}]}}
        skills = [Skill("demo", "demo")]
        wide = pick.build_request("current", skills, context=state["context"])
        narrow = rerank.build_request(state, skills, {})
        for request in (wide, narrow):
            for question in request["questions"].values():
                self.assertIn("CURRENT user request", question["instructions"])
                self.assertIn("Never let history override", question["instructions"])

    def test_no_history_keeps_existing_instructions(self):
        request = pick.build_request("current", [Skill("demo", "demo")])
        self.assertNotIn("CURRENT user request", request["questions"]["skill::0"]["instructions"])


if __name__ == "__main__":
    unittest.main()
