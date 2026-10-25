#!/usr/bin/env python3
"""Behavior tests for typesafe-skill-pick UserPromptSubmit hook."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

HOOK_PATH = Path(__file__).resolve().parents[1] / "typesafe-skill-pick.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("typesafe_skill_pick", HOOK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load hook from {HOOK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS_ENV_KEYS = (
    "GROK_SESSION_ID",
    "GROK_WORKSPACE_ROOT",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_CODE_ENTRYPOINT",
    "CODEX_HOME",
)


class TypesafeSkillPickTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = load_hook()

    def _run_main(
        self,
        pick_result: dict,
        *,
        stdin_payload: dict | None = None,
        clear_harness_env: bool = False,
        skill_picks_dir: Path | None = None,
    ) -> tuple[int, str]:
        stdout = io.StringIO()
        payload = stdin_payload or {"prompt": "need a skill for this"}
        patches = [
            mock.patch.object(self.hook, "pick_skill", return_value=pick_result),
            mock.patch.object(
                self.hook,
                "read_stdin_json",
                return_value=payload,
            ),
            mock.patch.object(self.hook, "log"),
            mock.patch("sys.stdout", stdout),
        ]
        if skill_picks_dir is not None:
            patches.append(
                mock.patch.object(self.hook, "SKILL_PICKS_DIR", skill_picks_dir)
            )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            if clear_harness_env:
                stack.enter_context(mock.patch.dict(os.environ, {}, clear=False))
                for key in HARNESS_ENV_KEYS:
                    os.environ.pop(key, None)
            code = self.hook.main()
        return code, stdout.getvalue()

    def test_fallback_real_skill_emits_local_context(self) -> None:
        code, out = self._run_main(
            {"choice": "tickets", "source": "fallback", "confidence": 0}
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Local skill pick", context)
        self.assertIn("tickets", context)

    def test_fallback_none_prints_nothing(self) -> None:
        code, out = self._run_main({"choice": "none", "source": "fallback"})
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_typesafe_skill_emits_typesafe_template(self) -> None:
        code, out = self._run_main(
            {"choice": "zq", "source": "typesafe", "confidence": 0.9}
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(
            context,
            (
                "TypeSafe skill pick: zq (confidence 0.9). "
                "Load that SKILL.md only. Ignore this if it does not fit."
            ),
        )

    def test_typesafe_skill_with_paths_instructs_read_not_skill_tool(self) -> None:
        code, out = self._run_main(
            {
                "choice": "zq",
                "source": "typesafe",
                "confidence": 0.9,
                "paths": ["/Users/zbornheimer/.agents/available-skills/zq/SKILL.md"],
            }
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(
            "Use the Read tool on this path: "
            "/Users/zbornheimer/.agents/available-skills/zq/SKILL.md",
            context,
        )
        self.assertIn("Do not call the Skill tool", context)
        self.assertNotIn("Load that SKILL.md only.", context)

    def test_typesafe_load_list_names_folded_files(self) -> None:
        code, out = self._run_main(
            {
                "choice": "bar",
                "source": "typesafe",
                "confidence": 0.9,
                "load": ["bar", "review-bar"],
                "paths": [
                    "/Users/zbornheimer/.agents/available-skills/bar/SKILL.md",
                    "/Users/zbornheimer/.agents/available-skills/review-bar/SKILL.md",
                ],
            }
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("bar", context)
        self.assertIn("review-bar", context)
        self.assertIn("Load SKILL.md for: bar, review-bar.", context)
        self.assertIn("Use the Read tool on these paths:", context)
        self.assertIn("Do not call the Skill tool", context)

    def _without_grok_env(self):
        clear_keys = ("GROK_SESSION_ID", "GROK_WORKSPACE_ROOT")
        patched = mock.patch.dict(os.environ, {}, clear=False)
        patched.start()
        for key in clear_keys:
            os.environ.pop(key, None)
        return patched

    def test_split_true_does_not_block_and_emits_skill_context(self) -> None:
        env = self._without_grok_env()
        try:
            code, out = self._run_main(
                {
                    "choice": "zq",
                    "source": "typesafe",
                    "confidence": 0.9,
                    "split": True,
                    "second_product": 0.94,
                    "session_relation": 1.94,
                },
                stdin_payload={
                    "prompt": "person menu gravatar and sign-out",
                    "in_flight": "Sync Mac licks to iPad",
                    "session_id": "01a0b9b1-9b76-7533-be7e-f7b75817e4b9",
                    "cwd": "/tmp/lickbook",
                },
            )
        finally:
            env.stop()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertNotIn("decision", payload)
        self.assertIn("zq", payload["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("Distinct from:", out)

    def test_tag_wrapped_prompt_skips_hook(self) -> None:
        prompts = (
            (
                '<cross-session-message from="uds:/tmp/cc-socks/1.sock">\n'
                "Hand me the branch.\n</cross-session-message>"
            ),
            "<a> </a>",
            "  <b>x</b>\n",
        )
        blocking_pick = {"choice": "zq", "source": "typesafe", "split": True}
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                code, out = self._run_main(
                    blocking_pick,
                    stdin_payload={"prompt": prompt, "in_flight": "other work"},
                )
                self.assertEqual(code, 0)
                self.assertEqual(out, "")

    def test_mismatched_tags_still_route(self) -> None:
        for prompt in ("<a> </b>", "<a>x</a> trailing", "lead <a>x</a>"):
            with self.subTest(prompt=prompt):
                code, out = self._run_main(
                    {"choice": "zq", "source": "typesafe", "confidence": 0.9},
                    stdin_payload={"prompt": prompt},
                )
                self.assertEqual(code, 0)
                self.assertIn("zq", out)

    def test_split_false_omits_block(self) -> None:
        code, out = self._run_main(
            {
                "choice": "zq",
                "source": "typesafe",
                "confidence": 0.9,
                "split": False,
                "second_product": 0.04,
                "session_relation": 0.1,
            }
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TypeSafe skill pick: zq", context)
        self.assertNotIn("decision", payload)
        self.assertNotIn("/new", context)

    def test_split_true_with_choice_none_prints_nothing(self) -> None:
        env = self._without_grok_env()
        try:
            code, out = self._run_main(
                {
                    "choice": "none",
                    "source": "typesafe",
                    "confidence": 0.8,
                    "split": "true",
                    "second_product": 0.91,
                    "session_relation": 1.9,
                },
                stdin_payload={
                    "prompt": "also land zq live",
                    "in_flight": "evo workers",
                },
            )
        finally:
            env.stop()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_old_shaped_json_without_split_does_not_block(self) -> None:
        code, out = self._run_main(
            {"choice": "zq", "source": "typesafe", "confidence": 0.9}
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertNotIn("decision", payload)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("/new", context)

    def test_hook_never_blocks_on_cli_split(self) -> None:
        env = self._without_grok_env()
        try:
            code, out = self._run_main(
                {
                    "choice": "none",
                    "source": "typesafe",
                    "split": True,
                    "second_product": 0.5,
                    "session_relation": 1.6,
                },
                stdin_payload={"prompt": "other product", "in_flight": "open work"},
            )
        finally:
            env.stop()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_empty_in_flight_split_does_not_block(self) -> None:
        code, out = self._run_main(
            {
                "choice": "zq",
                "source": "typesafe",
                "confidence": 0.9,
                "split": True,
            },
            stdin_payload={"prompt": "first prompt of a new session"},
        )
        self.assertEqual(code, 0)
        self.assertTrue(out.strip())
        parsed = json.loads(out)
        self.assertNotEqual(parsed.get("decision"), "block")
        self.assertNotIn("decision", parsed)

    def test_extract_in_flight_prefers_stdin_keys(self) -> None:
        self.assertEqual(
            self.hook.extract_in_flight({"in_flight": "lick sync"}),
            "lick sync",
        )
        self.assertEqual(
            self.hook.extract_in_flight({"session_title": "from title"}),
            "",
        )

    def test_extract_in_flight_reads_grok_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = "/tmp/project"
            session_id = "sess-abc"
            summary_path = (
                home
                / ".grok"
                / "sessions"
                / quote(cwd, safe="")
                / session_id
                / "summary.json"
            )
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "generated_title": "Sync Mac licks to iPad",
                        "last_turn_summary": "turn work in progress",
                        "session_summary": "also ignored when turn present",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(self.hook.Path, "home", return_value=home):
                got = self.hook.extract_in_flight(
                    {"cwd": cwd, "session_id": session_id, "prompt": "x"}
                )
            self.assertEqual(got, "turn work in progress")

    def test_extract_in_flight_falls_back_to_last_turn_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = "/tmp/other"
            session_id = "sess-def"
            summary_path = (
                home
                / ".grok"
                / "sessions"
                / quote(cwd, safe="")
                / session_id
                / "summary.json"
            )
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps({"last_turn_summary": "turn summary only"}),
                encoding="utf-8",
            )
            with mock.patch.object(self.hook.Path, "home", return_value=home):
                got = self.hook.extract_in_flight({"CWD": cwd, "sessionId": session_id})
            self.assertEqual(got, "turn summary only")

    def test_extract_in_flight_reads_claude_transcript_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            lines = [
                json.dumps({"type": "user", "message": {"content": "hi"}}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Working on schema pipeline fix for X",
                                }
                            ]
                        },
                    }
                ),
            ]
            transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
            got = self.hook.extract_in_flight(
                {"transcript_path": str(transcript), "prompt": "x"}
            )
            self.assertEqual(got, "Working on schema pipeline fix for X")

    def test_extract_in_flight_missing_transcript_fails_soft(self) -> None:
        got = self.hook.extract_in_flight(
            {"transcript_path": "/nonexistent/does-not-exist.jsonl", "prompt": "x"}
        )
        self.assertEqual(got, "")

    def test_extract_in_flight_garbage_transcript_fails_soft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "garbage.jsonl"
            transcript.write_text("not json\n{also not json\n", encoding="utf-8")
            got = self.hook.extract_in_flight(
                {"transcript_path": str(transcript), "prompt": "x"}
            )
            self.assertEqual(got, "")

    def test_split_true_with_claude_transcript_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [{"type": "text", "text": "prior work on X"}]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            env = self._without_grok_env()
            try:
                code, out = self._run_main(
                    {
                        "choice": "zq",
                        "source": "typesafe",
                        "confidence": 0.9,
                        "split": True,
                    },
                    stdin_payload={
                        "prompt": "unrelated new request",
                        "transcript_path": str(transcript),
                        "session_id": "sess-transcript-1",
                        "cwd": "/tmp/proj",
                    },
                )
            finally:
                env.stop()
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertNotIn("decision", payload)

    def test_detect_harness_from_env(self) -> None:
        cases = [
            ({"GROK_SESSION_ID": "abc"}, "grok"),
            ({"GROK_WORKSPACE_ROOT": "/tmp"}, "grok"),
            ({"CLAUDE_PROJECT_DIR": "/tmp"}, "claude"),
            ({"CLAUDE_CODE_ENTRYPOINT": "cli"}, "claude"),
            ({"CODEX_HOME": "/tmp"}, "codex"),
        ]
        clear_keys = (
            "GROK_SESSION_ID",
            "GROK_WORKSPACE_ROOT",
            "CLAUDE_PROJECT_DIR",
            "CLAUDE_CODE_ENTRYPOINT",
            "CODEX_HOME",
        )
        for env, want in cases:
            with self.subTest(env=env):
                cleaned = dict.fromkeys(clear_keys, "")
                cleaned.update(env)
                with mock.patch.dict(os.environ, cleaned, clear=False):
                    for key in clear_keys:
                        if key not in env:
                            os.environ.pop(key, None)
                    self.assertEqual(self.hook.detect_harness({}), want)

    def test_detect_harness_from_grok_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = "/tmp/project"
            session_id = "sess-abc"
            summary_path = (
                home
                / ".grok"
                / "sessions"
                / quote(cwd, safe="")
                / session_id
                / "summary.json"
            )
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text("{}", encoding="utf-8")
            clear_keys = (
                "GROK_SESSION_ID",
                "GROK_WORKSPACE_ROOT",
                "CLAUDE_PROJECT_DIR",
                "CLAUDE_CODE_ENTRYPOINT",
                "CODEX_HOME",
            )
            with mock.patch.dict(os.environ, {}, clear=False):
                for key in clear_keys:
                    os.environ.pop(key, None)
                with mock.patch.object(self.hook.Path, "home", return_value=home):
                    got = self.hook.detect_harness(
                        {"cwd": cwd, "session_id": session_id}
                    )
            self.assertEqual(got, "grok")

    def test_pick_skill_passes_in_flight_flag(self) -> None:
        captured: dict = {}
        cli = mock.Mock()
        cli.is_file.return_value = True
        str_cli = "/usr/local/bin/capability"
        cli.__fspath__ = lambda: str_cli
        cli.__str__ = lambda *args: str_cli

        def fake_run(command, **_kwargs):
            captured["command"] = command
            return subprocess_result(
                0,
                json.dumps(
                    {
                        "output": {
                            "Suggestions": [],
                            "Reason": "no catalog entry fits",
                            "Degraded": False,
                        }
                    }
                ),
            )

        with (
            mock.patch.object(self.hook, "cli_path", return_value=cli),
            mock.patch.object(self.hook, "log"),
        ):
            result = self.hook.pick_skill(
                "hello",
                in_flight="open work",
                run=fake_run,
            )
        self.assertIsNotNone(result)
        command = captured["command"]
        self.assertIn("run", command)
        self.assertIn("suggest_skills_tools_and_mcp", command)
        self.assertNotIn("--fresh", command)
        self.assertIn("--text", command)
        self.assertIn("hello", command)
        self.assertEqual(result["choice"], "none")
        self.assertEqual(result["source"], "capability")
        self.assertEqual(result["skills"], [])
        self.assertEqual(result["tools"], [])
        self.assertEqual(result["mcp"], [])

    def test_capability_pick_emits_skills_tools_and_mcp(self) -> None:
        code, out = self._run_main(
            {
                "skills": [
                    {
                        "kind": "skill",
                        "name": "zq",
                        "path": "/Users/zbornheimer/.agents/available-skills/zq/SKILL.md",
                        "description": "word " * 80,
                        "confidence": 0.9,
                    }
                ],
                "tools": [
                    {
                        "kind": "tool",
                        "name": "atask",
                        "how_to_call": "atask list --json",
                        "confidence": 0.8,
                    }
                ],
                "mcp": [
                    {
                        "kind": "mcp_tool",
                        "name": "linear_search",
                        "how_to_call": "mcp__linear__search",
                        "confidence": 0.7,
                    }
                ],
                "choice": "zq",
                "source": "capability",
                "confidence": 0.9,
                "paths": ["/Users/zbornheimer/.agents/available-skills/zq/SKILL.md"],
                "load": ["zq"],
            }
        )
        self.assertEqual(code, 0)
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        full = "word " * 80
        self.assertIn('source="suggest_skills_tools_and_mcp"', context)
        self.assertIn('origin="runtime"', context)
        self.assertIn("<name>zq</name>", context)
        self.assertIn(full.strip(), context)
        self.assertIn(
            "/Users/zbornheimer/.agents/available-skills/zq/SKILL.md", context
        )
        self.assertIn("<confidence>0.9</confidence>", context)
        self.assertIn("<name>atask</name>", context)
        self.assertIn("atask list --json", context)
        self.assertIn("<name>linear_search</name>", context)
        self.assertIn("mcp__linear__search", context)
        self.assertNotIn("Load SKILL.md", context)
        self.assertNotIn("Use the Read tool", context)
        self.assertNotIn("Ignore this if it does not fit.", context)
        self.assertNotIn("...", context)

    def test_slow_agentmux_uses_cached_context_and_emits_before_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "routing-context"
            cache_dir.mkdir()
            cache_key = hashlib.sha256(b"claude:sess-latency").hexdigest()
            (cache_dir / f"{cache_key}.json").write_text(
                json.dumps(
                    {
                        "durable_project_context": {"task": "ship hook fix"},
                        "conversation_history": [
                            {
                                "conversation": [
                                    {"speaking": "user", "text": "prior request"},
                                    {"speaking": "assistant", "text": "prior response"},
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            picked = mock.Mock(
                return_value={
                    "choice": "zq",
                    "source": "typesafe",
                    "confidence": 0.9,
                }
            )
            stdout = io.StringIO()

            def slow_agentmux(_session_id, _harness):
                time.sleep(2.1)
                return {"task": "late task"}

            payload = {
                "prompt": "fix the routing deadline",
                "in_flight": "TypeSafe hook work",
                "session_id": "sess-latency",
                "cwd": "/tmp/project",
                "current_goal": "return a routing decision",
                "open_decisions": ["preserve safety context"],
            }
            with (
                mock.patch.object(self.hook, "read_stdin_json", return_value=payload),
                mock.patch.object(self.hook, "detect_harness", return_value="claude"),
                mock.patch.object(
                    self.hook, "durable_context", side_effect=slow_agentmux
                ),
                mock.patch.object(
                    self.hook,
                    "ROUTING_CONTEXT_CACHE_DIR",
                    cache_dir,
                    create=True,
                ),
                mock.patch("skill_conversation.history", return_value=[]),
                mock.patch.object(self.hook, "pick_skill", picked),
                mock.patch.object(self.hook, "write_skill_pick"),
                mock.patch.object(self.hook, "log"),
                mock.patch("sys.stdout", stdout),
            ):
                started = time.monotonic()
                code = self.hook.main()
                elapsed = time.monotonic() - started

            self.assertEqual(code, 0)
            self.assertLess(elapsed, 1.5)
            self.assertIn("zq", stdout.getvalue())
            context = picked.call_args.kwargs["context"]
            self.assertEqual(context["current_task"], "TypeSafe hook work")
            self.assertEqual(context["current_goal"], "return a routing decision")
            self.assertEqual(context["open_decisions"], ["preserve safety context"])
            self.assertEqual(
                context["durable_project_context"], {"task": "ship hook fix"}
            )
            self.assertEqual(
                context["conversation_history"][0]["conversation"][0]["text"],
                "prior request",
            )

    def test_main_writes_session_pick_file_with_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            picks = Path(tmp) / "skill-picks"
            code, out = self._run_main(
                {
                    "choice": "zq",
                    "source": "typesafe",
                    "confidence": 0.9,
                    "load": ["zq"],
                    "paths": ["/tmp/zq/SKILL.md"],
                    "split": False,
                },
                stdin_payload={
                    "prompt": "land the PR",
                    "session_id": "sess-pick-1",
                },
                skill_picks_dir=picks,
            )
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertIn(
                "TypeSafe skill pick: zq",
                payload["hookSpecificOutput"]["additionalContext"],
            )
            pick_path = picks / "sess-pick-1.json"
            self.assertTrue(pick_path.is_file())
            body = json.loads(pick_path.read_text(encoding="utf-8"))
            self.assertEqual(body["choice"], "zq")
            self.assertEqual(body["load"], ["zq"])
            self.assertEqual(body["paths"], ["/tmp/zq/SKILL.md"])
            self.assertEqual(body["source"], "typesafe")
            self.assertEqual(body["confidence"], 0.9)
            self.assertFalse(body["split"])

    def test_split_does_not_block_and_writes_pick_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            picks = Path(tmp) / "skill-picks"
            env = self._without_grok_env()
            try:
                code, out = self._run_main(
                    {
                        "choice": "zq",
                        "source": "typesafe",
                        "confidence": 0.9,
                        "load": ["zq"],
                        "paths": ["/tmp/zq/SKILL.md"],
                        "split": True,
                    },
                    stdin_payload={
                        "prompt": "person menu",
                        "in_flight": "Sync Mac licks",
                        "session_id": "sess-split-1",
                    },
                    skill_picks_dir=picks,
                    clear_harness_env=True,
                )
            finally:
                env.stop()
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertNotIn("decision", payload)
            pick_path = picks / "sess-split-1.json"
            self.assertTrue(pick_path.is_file())
            body = json.loads(pick_path.read_text(encoding="utf-8"))
            self.assertEqual(body["choice"], "zq")
            self.assertEqual(body["paths"], ["/tmp/zq/SKILL.md"])
            self.assertTrue(body["split"])

    def test_write_skill_pick_failure_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / "blocked"
            blocked.write_text("not-a-dir", encoding="utf-8")
            with mock.patch.object(self.hook, "SKILL_PICKS_DIR", blocked / "nested"):
                self.hook.write_skill_pick(
                    "sess-fail",
                    {
                        "choice": "zq",
                        "source": "typesafe",
                        "paths": ["/tmp/zq/SKILL.md"],
                    },
                )
            code, out = self._run_main(
                {
                    "choice": "zq",
                    "source": "typesafe",
                    "confidence": 0.9,
                    "paths": ["/tmp/zq/SKILL.md"],
                },
                stdin_payload={"prompt": "land it", "session_id": "sess-fail"},
                skill_picks_dir=blocked / "nested",
            )
        self.assertEqual(code, 0)
        self.assertIn(
            "TypeSafe skill pick: zq",
            json.loads(out)["hookSpecificOutput"]["additionalContext"],
        )

    def test_choice_none_still_writes_pick_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            picks = Path(tmp) / "skill-picks"
            code, out = self._run_main(
                {"choice": "none", "source": "fallback", "paths": [], "load": []},
                stdin_payload={"prompt": "thanks", "session_id": "sess-none"},
                skill_picks_dir=picks,
            )
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            body = json.loads((picks / "sess-none.json").read_text(encoding="utf-8"))
            self.assertEqual(body["choice"], "none")
            self.assertEqual(body["paths"], [])
            self.assertEqual(body["load"], [])


def subprocess_result(code: int, stdout: str):
    completed = mock.Mock()
    completed.returncode = code
    completed.stdout = stdout
    completed.stderr = ""
    return completed


if __name__ == "__main__":
    unittest.main()
