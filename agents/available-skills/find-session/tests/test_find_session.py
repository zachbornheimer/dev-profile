from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "find-session.py"
STATUS_SCRIPT = ROOT / "scripts" / "session-status.py"

# ListAgents prints a short hex prefix (SKILL.md example: 2c6e5e). The
# transcript on disk is the full session uuid.
SESSION_ID = "c0ffee00-1111-4222-8333-c0ffee000001"
LISTAGENTS_PREFIX = "c0ffee"
PROJECT_SLUG = "demo-project"
TRANSCRIPT_LINE = '{"type":"user","message":"probe"}\n'
SESSION_END_LINE = '{"type":"session-end","timestamp":"2026-09-17T14:34:31.000Z"}\n'
ENDED_BY_MODEL_LINE = '{"type":"ended-by-model","timestamp":"2026-09-17T14:34:31.000Z","sessionId":"c0ffee00-1111-4222-8333-c0ffee000001"}\n'
ASSISTANT_LINE = (
    '{"type":"assistant","message":{"role":"assistant","content":"working"}}\n'
)
ISOLATED_PATH = os.pathsep.join(("/usr/bin", "/bin"))


class PrefixLookupTests(unittest.TestCase):
    def fake_home(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        transcript = (
            home / ".claude" / "projects" / PROJECT_SLUG / f"{SESSION_ID}.jsonl"
        )
        transcript.parent.mkdir(parents=True)
        transcript.write_text(TRANSCRIPT_LINE)
        return home

    def run_find(self, home: Path, identifier: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["SESSIONS_HOME"] = str(home)
        env["PATH"] = ISOLATED_PATH
        return subprocess.run(
            [sys.executable, str(SCRIPT), identifier],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_short_id_prefix_finds_transcript_jsonl(self) -> None:
        home = self.fake_home()
        transcript = (
            home / ".claude" / "projects" / PROJECT_SLUG / f"{SESSION_ID}.jsonl"
        )

        result = self.run_find(home, LISTAGENTS_PREFIX)

        self.assertEqual(result.returncode, 0, result.stderr)
        match = json.loads(result.stdout)
        self.assertEqual(match["transcript_path"], str(transcript))
        self.assertEqual(match["session_id"], SESSION_ID)


class TranscriptBusyTests(unittest.TestCase):
    def fake_home(self, transcript_text: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        transcript = (
            home / ".claude" / "projects" / PROJECT_SLUG / f"{SESSION_ID}.jsonl"
        )
        transcript.parent.mkdir(parents=True)
        transcript.write_text(transcript_text)
        return home

    def run_status(
        self, home: Path, identifier: str
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["SESSIONS_HOME"] = str(home)
        env["PATH"] = ISOLATED_PATH
        return subprocess.run(
            [sys.executable, str(STATUS_SCRIPT), identifier],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_session_end_last_event_is_not_busy(self) -> None:
        home = self.fake_home(TRANSCRIPT_LINE + SESSION_END_LINE)

        result = self.run_status(home, SESSION_ID)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["busy"])

    def test_assistant_last_event_is_busy(self) -> None:
        home = self.fake_home(TRANSCRIPT_LINE + ASSISTANT_LINE)

        result = self.run_status(home, SESSION_ID)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["busy"])

    def test_ended_by_model_last_event_is_not_busy(self) -> None:
        home = self.fake_home(TRANSCRIPT_LINE + ENDED_BY_MODEL_LINE)

        result = self.run_status(home, SESSION_ID)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["busy"])


if __name__ == "__main__":
    unittest.main()
