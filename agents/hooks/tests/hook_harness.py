"""Run a hook exactly as Claude Code does — by path, payload on stdin — and read its verdict.

Shared by every tests/test_<hook>.py. State (hooks.log, per-session files)
goes to a scratch dir via HC_STATE_DIR_OVERRIDE, and the log clock is
pinned via HC_NOW_ISO_OVERRIDE, so a hook run never touches the real
~/.claude/hooks/state.

Two shapes:
  - ``HookRunner.run_payload``: one call, a fresh state dir each time.
  - ``HookSession``: one state dir reused across calls, like a live session
    (reject caps, repair-by-reference, record-then-repeat).
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HOOKS_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = HOOKS_DIR / "tests" / "fixtures"
HOOK_TIMEOUT_SECS = 30
PINNED_NOW_ISO = "2000-01-01T00:00:00Z"
FAIL_OPEN_MARKER = "\tfail-open: "
HOOKS_LOG_NAME = "hooks.log"
# Who launched the test runner (e.g. a Gas City worker) must not decide a
# hook's verdict; a test that needs a role passes it explicitly.
CALLER_IDENTITY_ENV = frozenset({"GC_AGENT", "ORCHESTRATOR_ONLY_GC_COORDINATORS"})

Payload = str | dict[str, Any]


@dataclass(frozen=True, slots=True)
class HookRun:
    """One finished hook invocation. ``log`` is only what THIS call appended."""

    exit_code: int
    stdout: str
    stderr: str
    log: str

    @property
    def output(self) -> dict[str, Any] | None:
        """Parsed stdout JSON, or None when the hook printed nothing."""
        return json.loads(self.stdout) if self.stdout.strip() else None

    @property
    def decision(self) -> str:
        """deny | allow | block | context | none (silent, i.e. no objection)."""
        output = self.output or {}
        if output.get("decision") == "block":
            return "block"
        specific = output.get("hookSpecificOutput") or {}
        if "permissionDecision" in specific:
            return specific["permissionDecision"]
        return "context" if specific.get("additionalContext") else "none"

    @property
    def failed_open(self) -> bool:
        """True if the hook swallowed an error — a pass that proves nothing."""
        return FAIL_OPEN_MARKER in self.log


def payload_text(payload: Payload) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload)


def fixture_text(fixture: str) -> str:
    return (FIXTURES_DIR / fixture).read_text()


@dataclass(frozen=True, slots=True)
class HookSession:
    """Every call shares ``state_dir``, so state one call writes, the next one reads."""

    state_dir: Path
    env: Mapping[str, str] = field(default_factory=dict)

    @property
    def log(self) -> str:
        """The whole hooks.log so far."""
        path = self.state_dir / HOOKS_LOG_NAME
        return path.read_text() if path.exists() else ""

    def run_fixture(
        self, hook: str, fixture: str, env: Mapping[str, str] | None = None
    ) -> HookRun:
        return self.run_payload(hook, fixture_text(fixture), env)

    def run_payload(
        self,
        hook: str,
        payload: Payload,
        env: Mapping[str, str] | None = None,
        args: Sequence[str] = (),
    ) -> HookRun:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        log_before = self.log
        done = subprocess.run(
            [str(HOOKS_DIR / hook), *args],
            input=payload_text(payload),
            capture_output=True,
            text=True,
            env=self._env(env),
            timeout=HOOK_TIMEOUT_SECS,
            check=False,
        )
        log_after = self.log
        appended = log_after.removeprefix(log_before)
        return HookRun(done.returncode, done.stdout, done.stderr, appended)

    def seed(self, name: str, lines: list[str]) -> Path:
        """Write a state file (one line per entry), as an earlier hook call would have."""
        return self.write(name, "\n".join(lines) + "\n")

    def write(self, name: str, text: str) -> Path:
        """Write a state file verbatim."""
        path = self.state_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def _env(self, extra: Mapping[str, str] | None) -> dict[str, str]:
        inherited = {
            k: v for k, v in os.environ.items() if k not in CALLER_IDENTITY_ENV
        }
        return {
            **inherited,
            "HC_STATE_DIR_OVERRIDE": str(self.state_dir),
            "HC_NOW_ISO_OVERRIDE": PINNED_NOW_ISO,
            **self.env,
            **(extra or {}),
        }


@dataclass(frozen=True, slots=True)
class HookRunner:
    """Hands out isolated state dirs under ``state_root``."""

    state_root: Path

    def run_fixture(self, hook: str, fixture: str) -> HookRun:
        return self.run_payload(hook, fixture_text(fixture))

    def run_payload(self, hook: str, payload: Payload) -> HookRun:
        """One call in a fresh state dir."""
        return self.session(hook).run_payload(hook, payload)

    def session(self, name: str, env: Mapping[str, str] | None = None) -> HookSession:
        """A new state dir that persists across this session's calls."""
        return HookSession(self._fresh_state_dir(name), dict(env or {}))

    def _fresh_state_dir(self, name: str) -> Path:
        index = sum(1 for _ in self.state_root.glob(f"{name}-*"))
        state_dir = self.state_root / f"{name}-{index}"
        state_dir.mkdir(parents=True)
        return state_dir
