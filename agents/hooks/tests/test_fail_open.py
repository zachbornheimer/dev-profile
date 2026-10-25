"""Every hook entry file, in both hook dirs, fails open under an injected failure.

Hooks run on every tool call; a crash must never block Claude (or Cursor).
Each hook runs by path, exactly as the harness runs it, under four
failures: malformed JSON, a wrong-shaped payload, and two faults forced
inside the process by tests/fault_injection.py (loaded as sitecustomize) —
one inside ``decide``, one at every I/O boundary. The contract: no
traceback, no deny/block on stdout, and exit 0 (or the hook's documented
non-blocking status below).

HOME is a scratch dir (with the real lib/ and clarify/ linked in), so a
hook that runs to completion can't touch the real ~/.agents, ~/.claude,
or ~/.cursor state.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from hook_harness import HOOK_TIMEOUT_SECS, HOOKS_DIR, PINNED_NOW_ISO

CURSOR_HOOKS_DIR = Path.home() / ".cursor" / "hooks"
FAULT_INJECTOR = Path(__file__).with_name("fault_injection.py")
REAL_UV_CACHE_DIR = Path.home() / ".cache" / "uv"
REAL_UV_PYTHON_DIR = Path.home() / ".local" / "share" / "uv" / "python"
TRACEBACK_MARKER = "Traceback (most recent call last)"
BLOCKING_VERDICTS = ('"deny"', '"block"')
DECIDE_FAULT = "decide"
IO_FAULT = "io"
MALFORMED_JSON = "malformed-json"
WRONG_SHAPE = "wrong-shape"
FAULTS = (DECIDE_FAULT, IO_FAULT, MALFORMED_JSON, WRONG_SHAPE)

# A realistic call, so a hook gets past its early exits and into its logic.
EVENT_PAYLOAD = (
    '{"session_id":"fail-open-test","tool_name":"Bash","hook_event_name":"PreToolUse",'
    '"reason":"end_turn","last_assistant_message":"Done.","cwd":"/tmp",'
    '"tool_input":{"command":"echo hi","file_path":"/tmp/fail-open-test.txt","prompt":"x"}}'
)
STDIN_BY_FAULT = {
    DECIDE_FAULT: EVENT_PAYLOAD,
    IO_FAULT: EVENT_PAYLOAD,
    MALFORMED_JSON: '{"tool_name": "Bash", "tool_input": {"command": ',
    WRONG_SHAPE: '{"tool_name": ["Bash"], "tool_input": "not-an-object", "session_id": 7, "toolInput": 3, "reason": {}}',
}

# Entry files that are not hooks, so have no fail-open contract.
NOT_HOOKS = frozenset(
    {
        "direct-mode.py",  # on|off CLI the /direct skill runs; exits 1 on bad args by design
        "suggested-timeout-for.py",  # hyperfine p95 CLI; not a harness hook
    }
)


@dataclass(frozen=True, slots=True)
class Contract:
    """What "failed open" means for one hook."""

    exit_codes: frozenset[int] = frozenset({0})
    reason: str = ""


DEFAULT_CONTRACT = Contract()
CONTRACTS = {
    # Non-hook stdin (empty, malformed, or not a hook payload) is the CLI
    # mode by design: exit 1 when live ~/.agents is ahead of chezmoi or the
    # drift report is unreadable. Exit 1 is non-blocking.
    "chezmoi-guard.py": Contract(
        frozenset({0, 1}), "non-hook stdin runs the --check CLI"
    ),
    # WorktreeCreate has no open state: without a path on stdout there is
    # no worktree. Every failure is fail()'s one-line reason and exit 1.
    "worktree-provision.py": Contract(
        frozenset({1}), "WorktreeCreate fails closed with a reason"
    ),
    # A launcher: it execs the quality-guard binary, whose own exit status
    # (1 on an unparseable payload; non-blocking) is the hook's.
    "quality-guard-run.py": Contract(
        frozenset({0, 1}), "exec'd quality-guard's non-blocking status"
    ),
}

# Hooks whose code never reads a HookEvent, so the decide fault can't reach them.
NO_HOOK_EVENT = frozenset(
    {
        "gc-aoe-attach.py",
        "comms-recall.py",
        "pick-probe.py",
        "quality-guard-run.py",
        "relocate-synced-skills.py",
        "shared-checkout-guard.py",
        "typesafe-skill-pick.py",
        "unscoped-find-guard.py",
        "clarify-after-agent-response.py",
        "clarify-stop.py",
        "clarify-subagent-stop.py",
        "post-edit-lint-cursor.py",
        "quality-guard-pretool.py",
        "search-scope-guard-cursor.py",
        "skill-lint-stop.py",
    }
)


# Hooks that parse no JSON and spawn nothing on this payload, so the io fault can't reach them.
NO_IO_BOUNDARY = frozenset(
    {
        "comms-recall.py",
        "gc-aoe-attach.py",
        "pick-probe.py",
        "relocate-synced-skills.py",
    }
)

# The Cursor adapters exit early when the tool they wrap is missing; point
# them at a harmless stand-in so the payload is actually parsed.
STAND_IN_TOOLS = {
    "POST_EDIT_LINT_HOOK": "/usr/bin/true",
    "QUALITY_GUARD_BIN": "/usr/bin/true",
    "SEARCH_SCOPE_GUARD_BIN": "/usr/bin/true",
}


def _entry_files() -> list[Path]:
    agents = [p for p in sorted(HOOKS_DIR.glob("*.py")) if p.name not in NOT_HOOKS]
    return agents + sorted(CURSOR_HOOKS_DIR.glob("*.py"))


ENTRY_FILES = _entry_files()


@pytest.fixture
def scratch_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    hooks = home / ".agents" / "hooks"
    hooks.mkdir(parents=True)
    for shared in ("lib", "clarify"):
        (hooks / shared).symlink_to(HOOKS_DIR / shared)
    return home


def _run_with_fault(
    hook: Path, fault: str, home: Path, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    injector_dir = tmp_path / "injector"
    injector_dir.mkdir()
    shutil.copy(FAULT_INJECTOR, injector_dir / "sitecustomize.py")
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GROK_")
    }
    env.update(
        HOME=str(home),
        UV_CACHE_DIR=str(REAL_UV_CACHE_DIR),
        UV_PYTHON_INSTALL_DIR=str(REAL_UV_PYTHON_DIR),
        PYTHONPATH=str(injector_dir),
        HC_STATE_DIR_OVERRIDE=str(tmp_path / "state"),
        HC_NOW_ISO_OVERRIDE=PINNED_NOW_ISO,
        HOOK_TEST_FAULT=fault,
        HOOK_TEST_FAULT_MARKER=str(tmp_path / "fault-fired"),
        **STAND_IN_TOOLS,
    )
    return subprocess.run(
        [str(hook)],
        input=STDIN_BY_FAULT[fault],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=HOOK_TIMEOUT_SECS,
        check=False,
    )


def _fault_fired(tmp_path: Path) -> bool:
    return (tmp_path / "fault-fired").exists()


@pytest.mark.parametrize("fault", FAULTS)
@pytest.mark.parametrize(
    "hook", ENTRY_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}"
)
def test_hook_fails_open(
    hook: Path, fault: str, scratch_home: Path, tmp_path: Path
) -> None:
    contract = CONTRACTS.get(hook.name, DEFAULT_CONTRACT)

    done = _run_with_fault(hook, fault, scratch_home, tmp_path)

    assert TRACEBACK_MARKER not in done.stderr, done.stderr
    assert not any(verdict in done.stdout for verdict in BLOCKING_VERDICTS), done.stdout
    assert done.returncode in contract.exit_codes, (
        contract.reason,
        done.returncode,
        done.stderr,
    )
    unreachable = NO_HOOK_EVENT if fault == DECIDE_FAULT else NO_IO_BOUNDARY
    if fault in (DECIDE_FAULT, IO_FAULT) and hook.name not in unreachable:
        assert _fault_fired(tmp_path), (
            f"the {fault} fault never fired; the test proved nothing"
        )


def test_every_entry_file_is_covered() -> None:
    """A new hook joins the fail-open suite automatically; a rename can't drop one silently."""
    names = {p.name for p in ENTRY_FILES}
    assert set(CONTRACTS) <= names
    assert names >= NO_HOOK_EVENT
    assert names >= NO_IO_BOUNDARY
    assert len(ENTRY_FILES) >= len(NO_HOOK_EVENT) + len(CONTRACTS)
