"""gc-aoe-attach: a Gas City session gets exactly one AoE entry that attaches to it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR / "lib"))

from gc_aoe_attach_plan import (
    SCOPE_ALL,
    SCOPE_NAMED,
    SCOPE_OFF,
    Action,
    AoeEntry,
    plan_attach,
    session_from_env,
)

CITY = "/Users/test/Developer/zach-factory"
MAYOR_ENV = {
    "GC_CITY": CITY,
    "GC_SESSION_ID": "zf-wisp-622",
    "GC_ALIAS": "mayor",
    "GC_PROVIDER": "claude",
}
WORKER_ENV = {
    "GC_CITY": CITY,
    "GC_SESSION_ID": "zf-wisp-z1tusy",
    "GC_PROVIDER": "codex",
}


def _session(env: dict[str, str]):
    session = session_from_env(env)
    assert session is not None
    return session


def test_outside_gas_city_there_is_no_session() -> None:
    assert session_from_env({"GC_PROVIDER": "claude"}) is None


def test_missing_entry_is_added_with_attach_command() -> None:
    plan = plan_attach(_session(MAYOR_ENV), SCOPE_NAMED, [])

    assert plan is not None
    assert plan.action is Action.ADD
    assert plan.title == "zach-factory/mayor"
    assert plan.tool == "gc-claude"
    assert plan.extra_args == f"--city {CITY} session attach mayor"


def test_existing_entry_is_started_not_duplicated() -> None:
    plan = plan_attach(
        _session(MAYOR_ENV), SCOPE_NAMED, [AoeEntry("abc", "zach-factory/mayor")]
    )

    assert plan is not None
    assert plan.action is Action.START
    assert plan.entry_id == "abc"


@pytest.mark.parametrize(
    "env,scope,attached",
    [
        (WORKER_ENV, SCOPE_NAMED, False),
        (WORKER_ENV, SCOPE_ALL, True),
        (MAYOR_ENV, SCOPE_OFF, False),
        ({**MAYOR_ENV, "GC_PROVIDER": "unknown-harness"}, SCOPE_ALL, False),
    ],
    ids=[
        "unnamed-worker-skipped",
        "all-includes-worker",
        "off-disables",
        "unknown-harness-skipped",
    ],
)
def test_scope_and_harness_decide_whether_to_attach(env, scope, attached) -> None:
    assert (plan_attach(_session(env), scope, []) is not None) is attached


@pytest.mark.parametrize(
    "provider,tool",
    [("claude", "gc-claude"), ("codex", "gc-codex"), ("grok", "gc-grok")],
)
def test_every_harness_maps_to_its_aoe_tool(provider: str, tool: str) -> None:
    plan = plan_attach(
        _session({**MAYOR_ENV, "GC_PROVIDER": provider}), SCOPE_NAMED, []
    )

    assert plan is not None and plan.tool == tool


# --- end to end: the hook's apply mode against a fake `aoe` -----------------------


def _fake_aoe(tmp_path: Path, listing: list[dict[str, str]]) -> tuple[Path, Path]:
    calls = tmp_path / "calls.jsonl"
    fake = tmp_path / "aoe"
    fake.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {calls}\n"
        f'[ -n "$TMUX" ] && printf \'TMUX-LEAKED %s\\n\' "$TMUX" >> {calls}\n'
        f"[ \"$1\" = list ] && printf '%s' '{json.dumps(listing)}'\n"
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake, calls


def _apply(tmp_path: Path, fake: Path, env: dict[str, str]) -> None:
    run_env = {k: v for k, v in os.environ.items() if not k.startswith(("GC_", "TMUX"))}
    run_env.update(env)
    run_env["GC_AOE_ATTACH_AOE_BIN"] = str(fake)
    run_env["HC_STATE_DIR_OVERRIDE"] = str(tmp_path / "state")
    subprocess.run(
        [sys.executable, str(HOOKS_DIR / "gc-aoe-attach.py"), "--apply"],
        env=run_env,
        check=True,
        timeout=30,
    )


def test_apply_adds_then_starts_on_second_session_start(tmp_path: Path) -> None:
    fake, calls = _fake_aoe(tmp_path, [])
    _apply(tmp_path, fake, MAYOR_ENV)
    first = calls.read_text().splitlines()

    fake, calls = _fake_aoe(tmp_path, [{"id": "abc", "title": "zach-factory/mayor"}])
    calls.unlink()
    _apply(tmp_path, fake, MAYOR_ENV)
    second = calls.read_text().splitlines()

    assert first[0] == "list --json"
    assert first[1].startswith(
        "add " + CITY + " -t zach-factory/mayor --tool gc-claude"
    )
    assert "--extra-args --city " + CITY + " session attach mayor -l" in first[1]
    assert second == ["list --json", "session start abc"]


GC_TMUX = {"TMUX": "/private/tmp/tmux-503/zach-factory,123,0", "TMUX_PANE": "%1"}


def test_aoe_never_inherits_gas_city_tmux(tmp_path: Path) -> None:
    """aoe must create its panes on its own tmux server, not Gas City's."""
    fake, calls = _fake_aoe(tmp_path, [])
    _apply(tmp_path, fake, {**MAYOR_ENV, **GC_TMUX})

    assert not [
        line
        for line in calls.read_text().splitlines()
        if line.startswith("TMUX-LEAKED")
    ]


def test_trashed_entry_with_same_title_is_replaced_not_started(tmp_path: Path) -> None:
    trashed = {"id": "old", "title": "zach-factory/mayor", "state": "trashed"}
    fake, calls = _fake_aoe(tmp_path, [trashed])
    _apply(tmp_path, fake, MAYOR_ENV)

    lines = calls.read_text().splitlines()
    assert lines[1].startswith("add "), lines


def test_hook_outside_gas_city_never_calls_aoe(tmp_path: Path) -> None:
    fake, calls = _fake_aoe(tmp_path, [])
    _apply(tmp_path, fake, {})

    assert not calls.exists()
