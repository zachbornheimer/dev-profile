"""dictation-rewrite.py: a long dictated prompt gets a structured copy as context; everything else is left alone."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR / "lib"))

from hook_common import HookEvent

LONG_PROMPT = "so um I want the hook to like run on every prompt " * 20
REWRITTEN = "Run the hook on every prompt."


@pytest.fixture
def hook(monkeypatch):
    spec = importlib.util.spec_from_file_location("dictation_rewrite", HOOKS_DIR / "dictation-rewrite.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv(module.NESTED_RUN_ENV, raising=False)
    monkeypatch.delenv(module.TOKEN_LIMIT_ENV, raising=False)
    monkeypatch.delenv(module.MIN_SCORE_ENV, raising=False)
    return module


def stub(hook, monkeypatch, *, tokens, score=0.9, rewritten=REWRITTEN):
    """Replaces the three outside steps; returns the log of which ones ran."""
    calls: list[str] = []

    def count_tokens(text):
        calls.append("tokens")
        return tokens

    def dictation_score(text):
        calls.append("score")
        if isinstance(score, Exception):
            raise score
        return score

    def rewrite(text, timeout, cwd):
        calls.append("rewrite")
        if isinstance(rewritten, Exception):
            raise rewritten
        return rewritten

    monkeypatch.setattr(hook, "load_keys", lambda *args, **kwargs: None)
    monkeypatch.setattr(hook, "count_tokens", count_tokens)
    monkeypatch.setattr(hook, "dictation_score", dictation_score)
    monkeypatch.setattr(hook, "rewrite", rewrite)
    return calls


def decide(hook, prompt=LONG_PROMPT):
    return hook.decide(HookEvent({"prompt": prompt, "cwd": "/tmp"}))


def test_short_prompt_never_reaches_typesafe_or_the_rewrite(hook, monkeypatch):
    calls = stub(hook, monkeypatch, tokens=500)
    decision = decide(hook)
    assert decision.to_json() is None
    assert calls == ["tokens"]


def test_long_dictated_prompt_adds_the_rewrite_in_the_tag(hook, monkeypatch):
    stub(hook, monkeypatch, tokens=501)
    output = json.loads(decide(hook).to_json())["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    assert output["additionalContext"] == (
        f'<reworked-user-input note="{hook.REWORKED_NOTE}">\n{REWRITTEN}\n</reworked-user-input>'
    )


def test_long_typed_prompt_is_left_alone(hook, monkeypatch):
    calls = stub(hook, monkeypatch, tokens=900, score=0.49)
    assert decide(hook).to_json() is None
    assert "rewrite" not in calls


def test_score_at_the_minimum_counts_as_dictated(hook, monkeypatch):
    stub(hook, monkeypatch, tokens=900, score=0.5)
    assert decide(hook).to_json() is not None


def test_token_limit_comes_from_the_environment(hook, monkeypatch):
    stub(hook, monkeypatch, tokens=150)
    assert decide(hook).to_json() is None
    monkeypatch.setenv(hook.TOKEN_LIMIT_ENV, "100")
    assert decide(hook).to_json() is not None


def test_a_failing_score_keeps_the_original_input(hook, monkeypatch):
    stub(hook, monkeypatch, tokens=900, score=hook.Unavailable("typesafe down"))
    assert decide(hook).to_json() is None


def test_a_failing_rewrite_keeps_the_original_input(hook, monkeypatch):
    stub(hook, monkeypatch, tokens=900, rewritten=hook.Unavailable("capability exit 1"))
    assert decide(hook).to_json() is None


def test_a_failing_token_count_keeps_the_original_input(hook, monkeypatch):
    calls = stub(hook, monkeypatch, tokens=900)

    def broken(text):
        raise hook.Unavailable("tokuin missing")

    monkeypatch.setattr(hook, "count_tokens", broken)
    assert decide(hook).to_json() is None
    assert calls == []


def test_a_prompt_another_program_wrapped_in_a_tag_is_skipped(hook, monkeypatch):
    calls = stub(hook, monkeypatch, tokens=900)
    assert decide(hook, "<task-notification>\n" + LONG_PROMPT + "\n</task-notification>") is None
    assert calls == []


def test_a_nested_run_is_skipped(hook, monkeypatch):
    calls = stub(hook, monkeypatch, tokens=900)
    monkeypatch.setenv(hook.NESTED_RUN_ENV, "1")
    assert decide(hook) is None
    assert calls == []


def test_load_keys_fills_only_what_is_unset(hook, tmp_path):
    keys = tmp_path / "keys.env"
    keys.write_text("export OPENROUTER_API_KEY='from-file'\nEXA_API_KEY=other\n# note\n")
    env = {"EXA_API_KEY": "already"}
    hook.load_keys(keys, env)
    assert env == {"EXA_API_KEY": "already", "OPENROUTER_API_KEY": "from-file"}
