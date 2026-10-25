"""goals-recall.py: scenarios ported from the former tests/goals-recall.sh (ZYS-744).

Returns Decision.context(), which wraps the recall text in structured
hookSpecificOutput JSON — the documented way to inject SessionStart context,
and the one every other ported hook uses.
"""

from __future__ import annotations

from hook_harness import HookRunner

PY_HOOK = "goals-recall.py"

NO_GOALS_CWD = "/tmp/zys744-no-goals"
HAS_GOALS_CWD = "/tmp/zys744-has-goals"
HAS_GOALS_SLUG = "-tmp-zys744-has-goals"
HAS_GOALS_BODY = "Keep shipping the named ticket."


def _session_start(cwd: str) -> dict:
    return {"cwd": cwd, "hook_event_name": "SessionStart"}


def _context_text(run) -> str:
    output = run.output or {}
    return (output.get("hookSpecificOutput") or {}).get("additionalContext", "")


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def test_no_goals_file_refuses_blind_redispatch(
    hooks: HookRunner, tmp_path, monkeypatch
) -> None:
    goals_dir = tmp_path / "goals"
    goals_dir.mkdir()
    monkeypatch.setenv("HC_GOALS_DIR_OVERRIDE", str(goals_dir))
    run = hooks.run_payload(PY_HOOK, _session_start(NO_GOALS_CWD))

    assert_clean_run(run)
    text = _context_text(run)
    assert "Do not invent work" in text
    assert "handoff.md" in text
    assert "no durable goals file" in text.lower()


def test_goals_file_present_emits_body_not_absence_note(
    hooks: HookRunner, tmp_path, monkeypatch
) -> None:
    goals_dir = tmp_path / "goals"
    goals_dir.mkdir()
    (goals_dir / f"{HAS_GOALS_SLUG}.md").write_text(HAS_GOALS_BODY + "\n")
    monkeypatch.setenv("HC_GOALS_DIR_OVERRIDE", str(goals_dir))
    run = hooks.run_payload(PY_HOOK, _session_start(HAS_GOALS_CWD))

    assert_clean_run(run)
    text = _context_text(run)
    assert HAS_GOALS_BODY in text
    assert "Do not invent work" not in text


def test_empty_stdin_is_silent(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, "")
    assert_clean_run(run)
    assert run.stdout == ""
