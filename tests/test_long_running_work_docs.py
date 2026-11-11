"""Contract test: the long-running-background-tasks skill documents the shipped
launch + single-armed-wait path (run_command background one_off + wait arm),
not the retired poll-cadence guidance.

The skill file is the surface this test pins; run with:
    python -m pytest tests/test_long_running_work_docs.py -q
"""

from pathlib import Path

import pytest

SKILL = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "available-skills"
    / "long-running-background-tasks"
    / "SKILL.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    assert SKILL.is_file(), f"missing skill file: {SKILL}"
    return SKILL.read_text()


def test_launcher_is_run_command_background_one_off(text: str) -> None:
    """The launcher is named: run_command with background: true and one_off: true
    (herdr), whose on_complete defaults to "notify" and which returns wait_id."""
    for needle in (
        "run_command",
        "background: true",
        "one_off: true",
        "on_complete",
        "notify",
        "wait_id",
    ):
        assert needle in text, f"missing {needle!r}"
    # on_complete default stated, not just named.
    assert (
        'on_complete defaults to "notify"' in text
        or "on_complete defaults to notify" in text
    ), "the on_complete default must be stated"


def test_single_arm_call_is_named(text: str) -> None:
    """The single arm call is named verbatim, and the herdr one_off's
    log_sentinel arm is stated as done for you."""
    for needle in (
        'action: "arm"',
        "job_exit",
        "on_fire",
        "notify: true",
    ):
        assert needle in text, f"missing {needle!r}"
    assert "wait_id" in text and "job_id" in text
    assert "log_sentinel" in text, "the herdr one_off sentinel arm must be named"
    assert (
        "arms log_sentinel for you" in text
        or "arms the log_sentinel for you" in text
        or "arms `log_sentinel` for you" in text
        or "arms the `log_sentinel` for you" in text
    ), "the skill must note the herdr one_off arms log_sentinel for you"


def test_three_invariants_stated(text: str) -> None:
    """Each fire settles exactly one wait (a fired arm is marked delivered); a
    job exit is consumed once by its owner; a session wakes once per batch of
    report-back records — hence on_complete/notify is the only armed wait and
    no second waiter or poll loop is added."""
    assert "exactly one wait" in text, "invariant 1 (one fire settles one wait)"
    assert "delivered" in text, "a fired arm is marked delivered"
    assert "consumed once" in text, "invariant 2 (job exit consumed once)"
    assert "wakes once" in text, "invariant 3 (one wake per batch)"
    assert "report-back" in text, "the report-back channel is named"
    assert "only armed wait" in text or "only armed one" in text, (
        "on_complete/notify is the only armed wait"
    )
    assert "no second waiter" in text or "no second armed wait" in text, (
        "no second waiter is added"
    )
    assert (
        "no poll loop" in text or "no poll-loop" in text or "no polling loop" in text
    ), "no poll loop is added"


def test_wait_field_is_one_shot_distinct_from_one_off(text: str) -> None:
    """wait's arm field is named one_shot, distinct from run_command's one_off."""
    assert "one_shot" in text, "wait's arm field one_shot must be named"
    # The distinctness note: both spellings appear, and one_shot is tied to wait.
    assert "one_off" in text and "one_shot" in text
    assert (
        "distinct from" in text or "not the same as" in text or "different from" in text
    ), "one_shot must be called distinct from run_command's one_off"


def test_poll_cadence_text_is_gone(text: str) -> None:
    """The replaced poll-cadence guidance is gone: no monitor/loop cadence
    lists, no 10-hour limit, no kill-duplicate-pollers instructions."""
    for banned in (
        "monitor and loop",
        "poll every 30s",
        "every 10 min",
        "10-hour",
        "kill duplicate pollers",
        "kill any previous ones",
        "spawn a new monitor",
    ):
        assert banned not in text, f"retired text still present: {banned!r}"
