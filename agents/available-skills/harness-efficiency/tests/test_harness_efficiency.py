from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "harness_efficiency.py"
REQUIRED_CASES = (
    "discover_multi_harness",
    "repeated_workflow_to_command",
    "skill_vs_command_vs_subagent",
    "instruction_bloat",
    "linear_dedupe",
    "research_cache_fresh",
    "research_cache_stale",
)


def load_mod():
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("harness_efficiency", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["harness_efficiency"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _sessions(count: int, **kwargs) -> list:
    parse = load_mod().parse
    return [
        parse.Session(
            harness=kwargs.get("harness", "grok"),
            session_id=f"s{index}",
            path=f"/tmp/s{index}",
            model=kwargs.get("model"),
            user_turns=kwargs.get("user_turns", 1),
        )
        for index in range(count)
    ]


class NoiseFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_mod()
        cls.parse = cls.mod.parse

    def test_spawn_subagent_counts_as_subagent(self) -> None:
        session = self.parse.Session(harness="grok", session_id="g1", path="p")
        track = self.parse._ToolTrack()
        self.parse.apply_tool(session, track, "spawn_subagent", {})
        self.parse.apply_tool(session, track, "task", {})
        self.assertEqual(session.subagents, 2)

    def test_grok_default_is_not_an_expensive_tiny_session(self) -> None:
        grok = _sessions(3, model="grok-4.6", user_turns=1)
        self.assertEqual(self.mod.cluster_model_routing(grok), [])
        opus = _sessions(3, harness="claude", model="claude-opus-4", user_turns=1)
        hits = self.mod.cluster_model_routing(opus)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["kind"], "model_routing")

    def test_is_correction_ignores_injected_context(self) -> None:
        parse = self.parse
        self.assertFalse(
            parse.is_correction("user-info\nOS: macos\ndon't do that")
        )
        self.assertFalse(
            parse.is_correction("OS Version: macos\nyou missed a file")
        )
        self.assertFalse(parse.is_correction("<role>system</role>\nyou forgot"))
        self.assertFalse(
            parse.is_correction("You are a helpful assistant. don't do X")
        )
        self.assertTrue(parse.is_correction("No, that's wrong — use mise"))

    def test_stored_user_info_corrections_do_not_produce_a_finding(self) -> None:
        sessions = _sessions(3)
        injected = [
            ("grok", f"s{i}", "correction", "user-info\nOS: macos\ndon't do that")
            for i in range(3)
        ]
        self.assertEqual(self.mod.cluster_corrections(sessions, injected), [])
        real = [
            ("grok", f"s{i}", "correction", "No, that's wrong — use mise")
            for i in range(3)
        ]
        hits = self.mod.cluster_corrections(sessions, real)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["kind"], "correction")

    def test_skill_md_reads_are_not_instruction_bloat(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            skill = Path(tmp.name) / "SKILL.md"
            claude = Path(tmp.name) / "CLAUDE.md"
            skill.write_text("\n".join(f"# rule {i}" for i in range(210)) + "\n")
            claude.write_text("\n".join(f"# rule {i}" for i in range(210)) + "\n")
            sessions = _sessions(3)
            skill_events = [
                ("grok", f"s{i}", "read", str(skill)) for i in range(3)
            ]
            claude_events = [
                ("grok", f"s{i}", "read", str(claude)) for i in range(3)
            ]
            self.assertEqual(
                self.mod.cluster_instruction_bloat(sessions, skill_events), []
            )
            claude_hits = self.mod.cluster_instruction_bloat(
                sessions, claude_events
            )
            self.assertTrue(claude_hits)
            self.assertEqual(claude_hits[0]["kind"], "instruction_bloat")
        finally:
            tmp.cleanup()

    def test_explore_tool_seq_classifies_as_subagent(self) -> None:
        parse = self.parse
        self.assertEqual(
            parse.classify_primitive(
                "repeated_tool_seq", {"title": "read && search && list-dir"}
            ),
            "subagent",
        )
        self.assertEqual(
            parse.classify_primitive(
                "repeated_tool_seq", {"title": "read && read && read"}
            ),
            "subagent",
        )
        self.assertEqual(
            parse.classify_primitive(
                "repeated_tool_seq", {"title": "shell && shell && read"}
            ),
            "command",
        )

    def test_cluster_skips_explore_and_same_tool_windows(self) -> None:
        sessions = _sessions(3)
        explore = []
        same = []
        mixed = []
        for index in range(3):
            sid = f"s{index}"
            explore.extend(
                [
                    ("grok", sid, "tool", "read"),
                    ("grok", sid, "tool", "search"),
                    ("grok", sid, "tool", "list-dir"),
                ]
            )
            same.extend(
                [
                    ("grok", sid, "tool", "read"),
                    ("grok", sid, "tool", "read"),
                    ("grok", sid, "tool", "read"),
                ]
            )
            mixed.extend(
                [
                    ("grok", sid, "tool", "shell"),
                    ("grok", sid, "tool", "shell"),
                    ("grok", sid, "tool", "read"),
                ]
            )
        self.assertEqual(
            self.mod.cluster_events(
                sessions, explore, "tool", "repeated_tool_seq", 3
            ),
            [],
        )
        self.assertEqual(
            self.mod.cluster_events(
                sessions, same, "tool", "repeated_tool_seq", 3
            ),
            [],
        )
        mixed_hits = self.mod.cluster_events(
            sessions, mixed, "tool", "repeated_tool_seq", 3
        )
        self.assertTrue(mixed_hits)
        self.assertEqual(mixed_hits[0]["proposed_primitive"], "command")

    def test_long_repeated_shell_titles_are_skipped(self) -> None:
        sessions = _sessions(3)
        long = "git status " + ("x" * 80)
        short = "git status --short"
        long_events = [("grok", f"s{i}", "shell", long) for i in range(3)]
        short_events = [("grok", f"s{i}", "shell", short) for i in range(3)]
        self.assertEqual(
            self.mod.cluster_events(
                sessions, long_events, "shell", "repeated_shell", 1
            ),
            [],
        )
        short_hits = self.mod.cluster_events(
            sessions, short_events, "shell", "repeated_shell", 1
        )
        self.assertTrue(short_hits)
        self.assertEqual(short_hits[0]["proposed_primitive"], "command")

    def test_report_ranks_top_forty_and_keeps_full_json(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            run_dir = Path(tmp.name) / "run"
            findings = [
                {
                    "id": f"k:{index:02d}",
                    "kind": "repeated_shell",
                    "session_count": index,
                    "proposed_primitive": "command",
                    "status": "new",
                }
                for index in range(50)
            ]
            self.mod.write_outputs(run_dir, findings, _sessions(2))
            ranked = json.loads((run_dir / "patterns.json").read_text())
            self.assertEqual(len(ranked), 50)
            self.assertEqual(ranked[0]["session_count"], 49)
            self.assertEqual(ranked[-1]["session_count"], 0)
            report = (run_dir / "report.md").read_text()
            self.assertIn("Showing 40 of 50; full list in patterns.json", report)
            table_rows = [
                line for line in report.splitlines() if line.startswith("| k:")
            ]
            self.assertEqual(len(table_rows), 40)
            self.assertIn("| k:49 |", report)
            self.assertNotIn("| k:09 |", report)
        finally:
            tmp.cleanup()


class EvalCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_mod()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.state = Path(self.tmp.name) / "state"
        self.home.mkdir()
        self.state.mkdir()
        self._old = {key: os.environ.get(key) for key in ("HE_HOME", "HE_STATE")}
        os.environ["HE_HOME"] = str(self.home)
        os.environ["HE_STATE"] = str(self.state)
        self.mod.write_eval_fixtures(self.home)
        self.ctx = self.mod.load_context()

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_discover_multi_harness(self) -> None:
        disc = self.mod.discover(self.ctx)
        result = self.mod.eval_discover(disc)
        self.assertTrue(result["ok"], result["detail"])

    def test_repeated_workflow_to_command(self) -> None:
        self.mod.index_sessions(self.ctx, days=14)
        findings = self.mod.analyze(self.ctx)
        result = self.mod.eval_repeated(findings)
        self.assertTrue(result["ok"], result["detail"])

    def test_skill_vs_command_vs_subagent(self) -> None:
        result = self.mod.eval_classify()
        self.assertTrue(result["ok"], result["detail"])

    def test_instruction_bloat(self) -> None:
        self.mod.index_sessions(self.ctx, days=14)
        findings = self.mod.analyze(self.ctx)
        result = self.mod.eval_bloat(findings)
        self.assertTrue(result["ok"], result["detail"])

    def test_linear_dedupe(self) -> None:
        result = self.mod.eval_linear()
        self.assertTrue(result["ok"], result["detail"])

    def test_research_cache_fresh(self) -> None:
        result = self.mod.eval_research_fresh(self.ctx)
        self.assertTrue(result["ok"], result["detail"])

    def test_research_cache_stale(self) -> None:
        result = self.mod.eval_research_stale(self.ctx)
        self.assertTrue(result["ok"], result["detail"])

    def test_eval_cli_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "eval"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["passed"], payload)
        for name in REQUIRED_CASES:
            self.assertIn(name, payload["cases"])
            self.assertTrue(payload["cases"][name]["ok"], name)


class WorstAndScorecardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_mod()
        cls.parse = cls.mod.parse

    def test_cost_score_formula(self) -> None:
        session = self.parse.Session(
            harness="claude",
            session_id="s1",
            path="/tmp/s1",
            duration_s=3600,
            subagents=2,
            retries=5,
            user_turns=50,
            agent_turns=50,
        )
        self.assertAlmostEqual(self.mod.session_cost_score(session), 3.1)
        session.duration_s = None
        self.assertAlmostEqual(self.mod.session_cost_score(session), 2.1)

    def test_worst_ranks_long_session_first(self) -> None:
        long = self.parse.Session(
            harness="claude",
            session_id="long",
            path="/tmp/long",
            duration_s=10 * 3600,
            subagents=4,
            retries=2,
            user_turns=40,
            agent_turns=40,
        )
        short = self.parse.Session(
            harness="grok",
            session_id="short",
            path="/tmp/short",
            duration_s=60,
            subagents=0,
            retries=0,
            user_turns=1,
            agent_turns=1,
        )
        ranked = self.mod.rank_worst_sessions([short, long], limit=8)
        self.assertEqual([row["id"] for row in ranked], ["long", "short"])
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])
        self.assertEqual(
            set(ranked[0]),
            {
                "harness",
                "id",
                "path",
                "turns",
                "subagents",
                "retries",
                "duration_s",
                "tokens_cache_read",
                "score",
            },
        )
        self.assertEqual(ranked[0]["turns"], 80)
        self.assertEqual(ranked[0]["harness"], "claude")

    def test_scorecard_returns_identity_fields_from_index(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        old = {key: os.environ.get(key) for key in ("HE_HOME", "HE_STATE")}
        try:
            home = Path(tmp.name) / "home"
            state = Path(tmp.name) / "state"
            home.mkdir()
            state.mkdir()
            os.environ["HE_HOME"] = str(home)
            os.environ["HE_STATE"] = str(state)
            ctx = self.mod.load_context()
            conn = self.mod.connect_index(ctx)
            try:
                session = self.parse.Session(
                    harness="claude",
                    session_id="abc-123",
                    path="/tmp/abc.jsonl",
                    workspace="/repo",
                    model="sonnet",
                    started_at="2026-09-18T12:00:00Z",
                    ended_at="2026-09-18T14:00:00Z",
                    user_turns=10,
                    agent_turns=20,
                    tokens_cache_read=99,
                    events=[self.parse.Event("shell", "git status")],
                )
                self.mod.insert_session(conn, session)
                conn.commit()
            finally:
                conn.close()
            cards = self.mod.scorecard_from_index(ctx, "abc-123")
            self.assertEqual(len(cards), 1)
            card = cards[0]
            self.assertEqual(
                card,
                {
                    "harness": "claude",
                    "session_id": "abc-123",
                    "path": "/tmp/abc.jsonl",
                    "workspace": "/repo",
                    "model": "sonnet",
                    "started_at": "2026-09-18T12:00:00Z",
                    "ended_at": "2026-09-18T14:00:00Z",
                },
            )
            self.assertEqual(self.mod.scorecard_from_index(ctx, "missing"), [])
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            tmp.cleanup()

    def test_worst_help_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "worst", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--limit", completed.stdout)
        self.assertIn("--json", completed.stdout)

    def test_scorecard_help_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "scorecard", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--session", completed.stdout)


class TypesafeClassifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_mod()
        cls.typesafe = cls.mod.typesafe

    def test_missing_cli_skips_classify(self) -> None:
        finding = {
            "id": "retry:retries",
            "kind": "retry",
            "session_count": 3,
            "proposed_primitive": "hook",
        }

        def boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("typesafe CLI must not run when the path is missing")

        self.typesafe.classify_signal_findings(
            [finding],
            cli_path=Path("/no/such/typesafe.py"),
            run=boom,
        )
        self.assertEqual(finding["proposed_primitive"], "hook")
        self.assertNotIn("typesafe_source", finding)

    def test_api_down_still_writes_outputs(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        old = {key: os.environ.get(key) for key in ("HE_HOME", "HE_STATE")}
        try:
            home = Path(tmp.name) / "home"
            state = Path(tmp.name) / "state"
            home.mkdir()
            state.mkdir()
            os.environ["HE_HOME"] = str(home)
            os.environ["HE_STATE"] = str(state)
            self.mod.write_eval_fixtures(home)
            ctx = self.mod.load_context()
            self.mod.index_sessions(ctx, days=14)
            run_dir = state / "runs" / "down"
            cli = Path(tmp.name) / "typesafe.py"
            cli.write_text("# dummy\n", encoding="utf-8")

            def boom(*_args: object, **_kwargs: object) -> None:
                raise subprocess.TimeoutExpired(cmd="typesafe", timeout=15)

            with (
                patch.object(self.typesafe, "TYPESAFE_CLI", cli),
                patch.object(self.typesafe, "run_cli", boom),
            ):
                findings = self.mod.analyze(ctx, run_dir=run_dir)
            self.assertTrue(findings)
            self.assertTrue((run_dir / "patterns.json").is_file())
            self.assertTrue((run_dir / "report.md").is_file())
            ranked = json.loads((run_dir / "patterns.json").read_text())
            self.assertEqual(len(ranked), len(findings))
            for finding in findings:
                self.assertNotIn("typesafe_source", finding)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            tmp.cleanup()

    def test_join_subagent_overwrites_read_read_read_primitive(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            cli = Path(tmp.name) / "typesafe.py"
            cli.write_text("# dummy\n", encoding="utf-8")
            finding_id = "repeated_tool_seq:read-read-read"
            finding = {
                "id": finding_id,
                "kind": "repeated_tool_seq",
                "session_count": 459,
                "proposed_primitive": "command",
                "status": "new",
            }

            def fake_run(
                argv: list[str], stdin: str, timeout: float
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(argv[1:], [str(cli), "classify-findings"])
                self.assertEqual(timeout, self.typesafe.TYPESAFE_TIMEOUT_SECONDS)
                payload = json.loads(stdin)
                self.assertEqual(payload["findings"][0]["id"], finding_id)
                self.assertTrue(payload["tickets"])
                stdout = json.dumps(
                    {
                        "findings": [
                            {
                                "id": finding_id,
                                "typesafe_action": "join",
                                "typesafe_primitive": "subagent",
                                "typesafe_source": "typesafe",
                            }
                        ]
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

            self.typesafe.classify_signal_findings(
                [finding],
                cli_path=cli,
                run=fake_run,
            )
            self.assertEqual(finding["proposed_primitive"], "subagent")
            self.assertEqual(finding["canned_primitive"], "command")
            self.assertEqual(finding["typesafe_action"], "join")
            self.assertEqual(finding["typesafe_primitive"], "subagent")
            self.assertEqual(finding["typesafe_source"], "typesafe")
            run_dir = Path(tmp.name) / "run"
            self.mod.write_outputs(run_dir, [finding], _sessions(2))
            report = (run_dir / "report.md").read_text()
            self.assertIn("| typesafe |", report)
            table_rows = [
                line for line in report.splitlines() if line.startswith("| repeated_tool_seq:")
            ]
            self.assertEqual(len(table_rows), 1)
            self.assertIn("| subagent | subagent | new |", table_rows[0])
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
