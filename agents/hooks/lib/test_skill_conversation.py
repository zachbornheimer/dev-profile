"""Conversation history is ordered, excludes the current turn, and fails open."""
import json
import subprocess
import unittest
from unittest.mock import Mock

import skill_conversation


class HistoryTests(unittest.TestCase):
    def test_attaches_prior_turns_only(self):
        turns = [
            {"id": 1, "conversation": [{"speaking": "user", "text": "previous"}, {"speaking": "assistant", "text": "reply"}]},
            {"id": 2, "conversation": [{"speaking": "user", "text": "current"}, {"speaking": "assistant", "text": "future"}]},
        ]
        run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({"output": {"conversation": "claude:id", "turns_history": turns}}), ""))
        result = skill_conversation.history("id", "claude", "current", run=run)
        self.assertEqual(result, [turns[0]])
        self.assertIn("claude:id", run.call_args.args[0][-1])

    def test_timeout_returns_empty(self):
        run = Mock(side_effect=subprocess.TimeoutExpired("aubr", 5))
        self.assertEqual(skill_conversation.history("id", "claude", "current", run=run), [])

    def test_no_supported_session_does_not_run(self):
        run = Mock()
        self.assertEqual(skill_conversation.history("id", "unknown", "current", run=run), [])
        run.assert_not_called()

    def test_other_conversation_is_rejected(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"output":{"conversation":"claude:other","turns_history":[]}}', ""))
        self.assertEqual(skill_conversation.history("id", "claude", "current", run=run), [])


if __name__ == "__main__":
    unittest.main()
