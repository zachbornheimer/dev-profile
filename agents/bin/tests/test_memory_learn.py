"""memory-learn: transcript -> _llm -> cm add, with an idempotent ledger."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "memory-learn"
_loader = importlib.machinery.SourceFileLoader("memory_learn", str(SCRIPT))
_spec = importlib.util.spec_from_loader("memory_learn", _loader)
ml = importlib.util.module_from_spec(_spec)
sys.modules["memory_learn"] = ml
_loader.exec_module(ml)
import model_passes  # lib/ is on sys.path once memory-learn loads
import rule_quality
import sessions

LONG_TRANSCRIPT = "USER: do the thing\n" * 200 + "ASSISTANT: second pass exited 0\n"
REPLY = (
    '```json\n[{"content": "[workflow] Run bootstrap twice", "category": "workflow",'
    ' "evidence": "second pass exited 0"}]\n```'
)
KEEP_ALL = '[{"index": 0, "keep": true, "reason": "specific"}]'


class FakeShell:
    def __init__(
        self,
        transcript: str = LONG_TRANSCRIPT,
        reply: str = REPLY,
        verdicts: str = KEEP_ALL,
        facts: str = "[]",
    ) -> None:
        self.transcript, self.reply, self.verdicts = transcript, reply, verdicts
        self.facts = facts
        self.calls: list = []
        self.capability_calls: list = []

    def run(self, args, *, stdin: str = "", timeout: float = 0) -> str:
        self.calls.append((list(args), stdin))
        if args[0] == "claude":
            return json.dumps({"is_error": False, "result": self.facts})
        if args[0] == "_llm":
            return (
                self.verdicts if "review proposed memory rules" in stdin else self.reply
            )
        if args[:3] == ["cm", "onboard", "prompt"]:
            return "INSTRUCTIONS"
        if args[:2] == ["cm", "add"]:
            n = len(json.loads(stdin))
            return json.dumps(
                {"success": True, "data": {"added": [{}] * n, "skipped": []}}
            )
        return self.transcript

    def capability(self, tool, arguments, *, timeout: float = 0) -> dict:
        """get_recent_turns output for the `USER:`/`ASSISTANT:` lines of self.transcript."""
        self.capability_calls.append((tool, arguments))
        speaker = {"USER": "user", "ASSISTANT": "agent"}
        messages = [
            {"from": speaker[role], "timestamp": None, "content": text}
            for role, _, text in (
                line.partition(": ") for line in self.transcript.splitlines()
            )
            if role in speaker
        ]
        return {
            "turns": [{"id": i, "messages": [m]} for i, m in enumerate(messages, 1)]
        }


def _session(tmp_path: Path, agent: str = "claude_code") -> ml.Session:
    """A session whose recorded file holds LONG_TRANSCRIPT, the evidence source."""
    path = tmp_path / "s.jsonl"
    path.write_text(LONG_TRANSCRIPT)
    return ml.Session(str(path), agent, 123)


def _learn(shell, ledger, session, instructions: str, *, dry_run: bool) -> str:
    """One session through harvest + settle, reported without the path prefix."""
    if ledger.is_done(session):
        return "skip: already learned"
    found = ml.harvest(shell, session, instructions)
    if isinstance(found, str):
        if not dry_run:
            ledger.mark(session)
        return found
    lines = ml.settle(shell, ledger, [found], dry_run=dry_run)
    return "\n".join(lines).split(": ", 1)[1]


def test_one_judge_call_covers_every_session_in_a_batch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ml, "LEDGER", tmp_path / "l.json")
    paths = []
    for name in ("a", "b"):
        path = tmp_path / f"{name}.jsonl"
        path.write_text(LONG_TRANSCRIPT)
        paths.append(str(path))
    verdicts = '[{"index": 0, "keep": true, "reason": "x"}, {"index": 1, "keep": true, "reason": "y"}]'
    shell = FakeShell(verdicts=verdicts)
    assert ml.main(paths, shell=shell) == 0
    judge_calls = [
        c for c in shell.calls if c[0][0] == "_llm" and "review proposed" in c[1]
    ]
    assert len(judge_calls) == 1
    assert sum(1 for args, _ in shell.calls if args[:2] == ["cm", "add"]) == 2


def test_parse_rules_accepts_fence_and_strips_category_prefix() -> None:
    assert rule_quality.parse_rules(REPLY) == [
        rule_quality.Rule("Run bootstrap twice", "workflow", "second pass exited 0")
    ]


def test_rule_without_evidence_is_dropped() -> None:
    assert (
        rule_quality.parse_rules('[{"content": "Use X for Y", "category": "git"}]')
        == []
    )


def test_judge_rejection_keeps_rule_out_of_cm(tmp_path) -> None:
    shell = FakeShell(verdicts='[{"index": 0, "keep": false, "reason": "generic"}]')
    result = _learn(
        shell, ml.Ledger(tmp_path / "l.json"), _session(tmp_path), "I", dry_run=False
    )
    assert "judge kept 0" in result
    assert not any(args[:2] == ["cm", "add"] for args, _ in shell.calls)


def test_rule_the_judge_skipped_counts_as_rejected() -> None:
    assert rule_quality.parse_verdicts("[]", 2) == [
        (False, "no verdict"),
        (False, "no verdict"),
    ]


def test_parse_rules_rejects_reply_without_array() -> None:
    with pytest.raises(ValueError, match="no JSON array"):
        rule_quality.parse_rules("I could not find anything")


def test_grok_reads_chat_history_beside_indexed_updates() -> None:
    session = ml.Session("/x/.grok/sessions/w/id/updates.jsonl", "grok")
    assert sessions.reader_ref(session) == "/x/.grok/sessions/w/id/chat_history.jsonl"


def test_learn_adds_rules_then_ledger_skips_same_size(tmp_path) -> None:
    shell, ledger, session = (
        FakeShell(),
        ml.Ledger(tmp_path / "ledger.json"),
        _session(tmp_path),
    )
    assert (
        _learn(shell, ledger, session, "I", dry_run=False)
        == "proposed 1, evidenced 1, judge kept 1, fact-check kept 1, cm added 1, cm rejected 0"
    )
    added = [stdin for args, stdin in shell.calls if args[:2] == ["cm", "add"]]
    assert all(
        "--strict" in args for args, _ in shell.calls if args[:2] == ["cm", "add"]
    )
    assert json.loads(added[0]) == [
        {"content": "Run bootstrap twice", "category": "workflow"}
    ]
    assert (
        _learn(shell, ml.Ledger(tmp_path / "ledger.json"), session, "I", dry_run=False)
        == "skip: already learned"
    )


def test_dry_run_adds_nothing_and_leaves_ledger_empty(tmp_path) -> None:
    shell, ledger = FakeShell(), ml.Ledger(tmp_path / "ledger.json")
    result = _learn(shell, ledger, _session(tmp_path), "I", dry_run=True)
    assert "Run bootstrap twice" in result
    assert not any(args[:2] == ["cm", "add"] for args, _ in shell.calls)
    assert not (tmp_path / "ledger.json").exists()


def test_short_transcript_is_skipped_without_model_call(tmp_path) -> None:
    shell = FakeShell(transcript="USER: hi")
    assert _learn(
        shell, ml.Ledger(tmp_path / "l.json"), _session(tmp_path), "I", dry_run=False
    ).startswith("skip")
    assert not any(args[0] == "_llm" for args, _ in shell.calls)


def test_bad_model_reply_fails_the_run(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ml, "LEDGER", tmp_path / "l.json")
    path = tmp_path / "s.jsonl"
    path.write_text("{}")
    assert ml.main([str(path)], shell=FakeShell(reply="nope")) == 1
    assert "FAILED" in capsys.readouterr().err


def test_cursor_transcripts_newer_than_cutoff_are_found(tmp_path) -> None:
    old = tmp_path / "p1" / "agent-transcripts" / "a" / "a.jsonl"
    new = tmp_path / "p2" / "agent-transcripts" / "b" / "b.jsonl"
    for f, mtime in ((old, 1_000), (new, 9_000)):
        f.parent.mkdir(parents=True)
        f.write_text("{}")
        os.utime(f, (mtime, mtime))
    found = ml.recent_cursor_sessions(tmp_path, cutoff=5_000)
    assert [s.path for s in found] == [str(new)]
    assert found[0].agent == "cursor"


def test_since_cutoff_handles_relative_days_and_hours() -> None:
    assert ml.since_cutoff("-2d", now=200_000) == 200_000 - 2 * 86_400
    assert ml.since_cutoff("-6h", now=200_000) == 200_000 - 6 * 3_600


def test_cursor_path_maps_to_cursor_reader() -> None:
    assert (
        ml.session_for_path("/u/.cursor/projects/x/agent-transcripts/i/i.jsonl").agent
        == "cursor"
    )


@pytest.mark.parametrize(
    ("agent", "path", "ref"),
    [
        (
            "claude_code",
            "/u/.claude/projects/-p/6b255199-3c25-46a2-9ed2-1968057f7a0e.jsonl",
            "claude:6b255199-3c25-46a2-9ed2-1968057f7a0e",
        ),
        ("grok", "/u/.grok/sessions/%2Fw/01a1/updates.jsonl", "grok:01a1"),
        ("grok", "/u/.grok/sessions/%2Fw/01a1/chat_history.jsonl", "grok:01a1"),
        (
            "codex",
            "/u/.codex/sessions/2026/10/20/rollout-2026-10-20T16-32-42-01a15b04-2a3d-76b1-9ff5-32475fedae21.jsonl",
            "codex:01a15b04-2a3d-76b1-9ff5-32475fedae21",
        ),
        (
            "cursor",
            "/u/.cursor/projects/x/agent-transcripts/d772/d772.jsonl",
            "cursor:d772",
        ),
    ],
)
def test_conversation_ref_is_read_off_each_harness_path(agent, path, ref) -> None:
    assert sessions.conversation_ref(ml.Session(path, agent)) == ref


def test_unreadable_harness_and_foreign_codex_file_are_refused() -> None:
    with pytest.raises(RuntimeError, match="no transcript reader"):
        sessions.conversation_ref(ml.Session("/x/s.jsonl", "amp"))
    with pytest.raises(RuntimeError, match="not a codex rollout"):
        sessions.conversation_ref(ml.Session("/x/.codex/s.jsonl", "codex"))


def test_render_turns_labels_speakers_and_drops_harness_system_text() -> None:
    recent = {
        "turns": [
            {
                "id": 1,
                "messages": [
                    {"from": "user", "timestamp": None, "content": "fix it"},
                    {"from": "agent", "timestamp": "t", "content": "done"},
                    {"from": "system", "timestamp": None, "content": "Stop hook feedback: x"},
                ],
            }
        ]
    }
    assert sessions.render_turns(recent) == "USER: fix it\n\nASSISTANT: done\n\n"


def test_transcript_text_asks_for_the_newest_turns_within_the_char_cap(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(sessions, "MAX_TRANSCRIPT_CHARS", 100)
    shell = FakeShell(transcript="USER: " + "x" * 90 + "\n" + "ASSISTANT: newest\n")
    text = sessions.transcript_text(shell, _session(tmp_path))
    tool, arguments = shell.capability_calls[0]
    assert tool == "run_get_recent_turns"
    assert arguments["conversation"].startswith("claude:")
    assert arguments["max_tokens"] == 25
    assert arguments["length_limit"] == sessions.MESSAGE_CHARS
    assert len(text) == 100 and text.endswith("ASSISTANT: newest\n\n")


FAKE_MCP_SERVER = '''#!/usr/bin/env python3
import json, sys
if sys.argv[1:] != ["mcp"]:
    sys.exit(2)
print("banner line that is not JSON-RPC", flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {}}), flush=True)
    if msg["method"] == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}}
    elif msg["params"]["arguments"].get("fail"):
        result = {"isError": True, "content": [{"type": "text", "text": "no transcript found"}]}
    else:
        text = json.dumps({"echo": msg["params"]["arguments"], "pid": __import__("os").getpid()})
        result = {"content": [{"type": "text", "text": text}]}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
'''


def test_shell_capability_reuses_one_mcp_server_and_reports_tool_errors(
    tmp_path, monkeypatch
) -> None:
    server = tmp_path / "capability"
    server.write_text(FAKE_MCP_SERVER)
    server.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    shell = sessions.Shell()
    try:
        first = shell.capability("run_get_recent_turns", {"conversation": "claude:a"})
        second = shell.capability("run_get_recent_turns", {"conversation": "claude:b"})
        assert first["echo"] == {"conversation": "claude:a"}
        assert first["pid"] == second["pid"]
        with pytest.raises(RuntimeError, match="no transcript found"):
            shell.capability("run_get_recent_turns", {"fail": True})
        shell._server.kill()
        shell._server.wait()
        assert shell.capability("run_get_recent_turns", {})["pid"] != first["pid"]
    finally:
        shell.close()


def test_standing_instructions_skip_path_scoped_rules(tmp_path, monkeypatch) -> None:
    (tmp_path / "rules").mkdir()
    (tmp_path / "CLAUDE.md").write_text("Never use *-LLC org names.")
    (tmp_path / "rules" / "always.md").write_text("Edit the live path, then re-add.")
    (tmp_path / "rules" / "go.md").write_text(
        "---\npaths:\n  - '**/*.go'\n---\nGo rules"
    )
    monkeypatch.setattr(model_passes, "STANDING_INSTRUCTIONS_ROOT", tmp_path)
    text = model_passes.standing_instructions()
    assert "Never use *-LLC" in text and "Edit the live path" in text
    assert "Go rules" not in text


def test_rule_whose_evidence_is_not_in_transcript_is_dropped(tmp_path) -> None:
    invented = REPLY.replace("second pass exited 0", "tests all green")
    shell = FakeShell(
        transcript=LONG_TRANSCRIPT + "second pass exited 0\n", reply=invented
    )
    result = _learn(
        shell, ml.Ledger(tmp_path / "l.json"), _session(tmp_path), "I", dry_run=False
    )
    assert "proposed 1, evidenced 0" in result
    assert not any(args[:2] == ["cm", "add"] for args, _ in shell.calls)


def test_elided_evidence_matches_when_each_fragment_is_verbatim() -> None:
    transcript = (
        "$ mise bootstrap\nGenerated 4 configs from profile.pkl\nsecond pass exited 0\n"
    )
    elided = rule_quality.Rule("r", "c", "Generated 4 configs ... second pass exited 0")
    invented = rule_quality.Rule(
        "r", "c", "Generated 9 configs ... second pass exited 0"
    )
    assert rule_quality.evidence_found(elided, transcript)
    assert not rule_quality.evidence_found(invented, transcript)


def test_raw_session_text_includes_tool_output_unescaped(tmp_path) -> None:
    raw = tmp_path / "s.jsonl"
    raw.write_text(
        json.dumps(
            {
                "type": "tool_result",
                "content": 'error: "a config include must be a git:: URL"\nexit 1',
            }
        )
    )
    text = sessions.raw_session_text(ml.Session(str(raw), "claude_code"))
    assert "a config include must be a git:: URL" in text


def test_evidence_with_commentary_matches_on_its_quoted_spans() -> None:
    transcript = (
        "ASSISTANT: Committed form.json still has the old title until productgen\n"
    )
    narrated = rule_quality.Rule(
        "r",
        "c",
        "'Committed form.json still has the old title' — the artifact lagged source",
    )
    assert rule_quality.evidence_found(narrated, transcript)


def test_evidence_matches_across_typographic_quotes() -> None:
    recorded = "Gas City’s order runner can invoke scripts. I found no timer-based resume command."
    rule = rule_quality.Rule(
        "r",
        "c",
        '"Gas City\'s order runner can invoke scripts. I found no timer-based resume"',
    )
    assert rule_quality.evidence_found(rule, recorded)


def test_rules_parse_when_prose_with_brackets_precedes_the_array() -> None:
    reply = 'Note [see below]: ```json\n[{"content": "c", "category": "git", "evidence": "e"}]\n```'
    assert [r.content for r in rule_quality.parse_rules(reply)] == ["c"]


def test_extraction_prompt_fences_transcript_and_ends_with_contract() -> None:
    shell = FakeShell()
    ml.extract_rules(shell, "INSTRUCTIONS", "USER: please answer me directly")
    prompt = next(stdin for args, stdin in shell.calls if args[0] == "_llm")
    assert (
        prompt.index("<session>")
        < prompt.index("please answer me")
        < prompt.index("</session>")
    )
    assert prompt.rstrip().endswith(rule_quality.EXTRACTION_CONTRACT.strip())


def _saved_contents(shell) -> list[str]:
    return [
        r["content"]
        for args, stdin in shell.calls
        if args[:2] == ["cm", "add"]
        for r in json.loads(stdin)
    ]


def test_fact_check_false_rule_is_not_saved(tmp_path) -> None:
    shell = FakeShell(
        facts='[{"index": 0, "verdict": "false", "better_practice": "", "source": "https://doc", "contradiction": "second pass exited 0"}]'
    )
    result = _learn(
        shell, ml.Ledger(tmp_path / "l.json"), _session(tmp_path), "I", dry_run=False
    )
    assert "fact-check kept 0" in result
    assert _saved_contents(shell) == []


def test_fact_check_better_practice_is_appended_with_source(tmp_path) -> None:
    facts = '[{"index": 0, "verdict": "true", "better_practice": "Use a shared preset.", "source": "https://x"}]'
    shell = FakeShell(facts=facts)
    _learn(
        shell, ml.Ledger(tmp_path / "l.json"), _session(tmp_path), "I", dry_run=False
    )
    assert _saved_contents(shell) == [
        "Run bootstrap twice Better practice: Use a shared preset. (https://x)"
    ]


def test_rule_the_fact_checker_skipped_is_kept_as_unverifiable(tmp_path) -> None:
    shell = FakeShell(facts="[]")
    _learn(
        shell, ml.Ledger(tmp_path / "l.json"), _session(tmp_path), "I", dry_run=False
    )
    assert _saved_contents(shell) == ["Run bootstrap twice"]


class PlaybookShell(FakeShell):
    """FakeShell with a two-rule playbook for --rejudge."""

    def run(self, args, *, stdin: str = "", timeout: float = 0) -> str:
        if args[:2] == ["cm", "ls"]:
            rows = [
                {"id": "b-1", "content": "Rule one", "category": "git"},
                {"id": "b-2", "content": "Rule two", "category": "git"},
            ]
            self.calls.append((list(args), stdin))
            return json.dumps({"data": rows})
        return super().run(args, stdin=stdin, timeout=timeout)


def test_rejudge_fact_checks_survivors(tmp_path) -> None:
    keep_both = '[{"index": 0, "keep": true, "reason": "a"}, {"index": 1, "keep": true, "reason": "b"}]'
    facts = (
        '[{"index": 0, "verdict": "false", "better_practice": "", "source": "https://doc", "contradiction": "second pass exited 0"},'
        ' {"index": 1, "verdict": "true", "better_practice": "Use presets.", "source": "s"}]'
    )
    shell = PlaybookShell(verdicts=keep_both, facts=facts)
    ml.rejudge_playbook(shell, dry_run=False)
    removed = [args[2] for args, _ in shell.calls if args[:2] == ["cm", "rm"]]
    assert removed == ["b-1", "b-2"]
    assert _saved_contents(shell) == ["Rule two Better practice: Use presets. (s)"]


def test_false_verdict_without_a_quote_found_at_its_source_is_downgraded() -> None:
    page = "<p>Version updates need a dependabot.yml file in each repository.</p>"
    real = rule_quality.FactCheck(
        "false",
        source="u",
        contradiction="need a dependabot.yml file in each repository",
    )
    made_up = rule_quality.FactCheck(
        "false", source="u", contradiction="org-level version updates are available"
    )
    assert rule_quality.confirm_contradiction(real, page).verdict == "false"
    assert rule_quality.confirm_contradiction(made_up, page).verdict == "unverifiable"
    assert rule_quality.confirm_contradiction(made_up, "").verdict == "unverifiable"
