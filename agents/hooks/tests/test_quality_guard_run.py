"""quality-guard-run.py: no run.sh cases exist for this launcher, so these
cover its three branches directly (Grok dedupe, binary-not-found, and
delegating argv/exit code to the resolved binary).
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
PY_HOOK = "quality-guard-run.py"
HOOK_TIMEOUT_SECS = 30

FAKE_QUALITY_GUARD = """#!/bin/sh
echo "{\\"argv\\":\\"$*\\",\\"level\\":\\"$QUALITY_GUARD_LOG_LEVEL\\",\\"file\\":\\"$QUALITY_GUARD_LOG_FILE\\"}"
exit 7
"""


# A uv binary NOT co-located with the mise-shimmed quality-guard, so PATH
# scrubbed of the real quality-guard's directory still lets `uv run --script`
# resolve the hook's own shebang.
_UV_DIR = (
    "/opt/homebrew/bin"
    if Path("/opt/homebrew/bin/uv").exists()
    else str(Path(shutil.which("uv") or "/usr/bin/uv").parent)
)


def _minimal_env(**overrides: str) -> dict[str, str]:
    base = {
        "HOME": overrides.pop("HOME", "/nonexistent-home"),
        "PATH": f"{_UV_DIR}:/usr/bin:/bin",
    }
    base.update(overrides)
    return base


def _fake_binary_home(tmp_path: Path) -> Path:
    go_bin = tmp_path / "go" / "bin"
    go_bin.mkdir(parents=True)
    binary = go_bin / "quality-guard"
    binary.write_text(FAKE_QUALITY_GUARD)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def run(
    hook: str, argv: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(HOOKS_DIR / hook), *argv],
        capture_output=True,
        text=True,
        env=env,
        timeout=HOOK_TIMEOUT_SECS,
        check=False,
    )


# --- Grok dual-load dedupe -------------------------------------------------


def test_grok_session_without_native_flag_defers(tmp_path: Path) -> None:
    env = _minimal_env(HOME=str(tmp_path), GROK_SESSION_ID="abc123")

    result = run(PY_HOOK, ["--mode=fast"], env)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "decision": "allow",
        "reason": "quality-guard deferred to grok-native hook",
    }


def test_grok_native_source_runs_the_real_check(tmp_path: Path) -> None:
    home = _fake_binary_home(tmp_path)
    env = _minimal_env(
        HOME=str(home), GROK_SESSION_ID="abc123", QUALITY_GUARD_SOURCE="grok-native"
    )

    result = run(PY_HOOK, ["--mode=fast"], env)

    assert result.returncode == 7
    assert json.loads(result.stdout)["argv"] == "--mode=fast"


# --- binary not found --------------------------------------------------


def test_binary_not_found_allows(tmp_path: Path) -> None:
    env = _minimal_env(HOME=str(tmp_path))

    result = run(PY_HOOK, ["--mode=fast"], env)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "decision": "allow",
        "reason": "quality-guard binary not found on PATH",
    }


# --- delegates argv, exit code, and default env to the resolved binary -----


def test_delegates_argv_and_exit_code(tmp_path: Path) -> None:
    home = _fake_binary_home(tmp_path)
    env = _minimal_env(HOME=str(home))

    result = run(PY_HOOK, ["--mode=pretool-review"], env)

    assert result.returncode == 7
    payload = json.loads(result.stdout)
    assert payload["argv"] == "--mode=pretool-review"
    assert payload["level"] == "debug"
    assert payload["file"] == "/tmp/qg-pretool.log"


def test_preserves_caller_supplied_log_settings(tmp_path: Path) -> None:
    home = _fake_binary_home(tmp_path)
    env = _minimal_env(
        HOME=str(home),
        QUALITY_GUARD_LOG_LEVEL="warn",
        QUALITY_GUARD_LOG_FILE="/tmp/custom.log",
    )

    result = run(PY_HOOK, ["--mode=fast"], env)

    payload = json.loads(result.stdout)
    assert payload["level"] == "warn"
    assert payload["file"] == "/tmp/custom.log"
