"""Operational knobs, read from the same HC_* variables as hook-common.sh."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

STDIN_TIMEOUT_SECS_DEFAULT = 5.0
HOOKS_LOG_MAX_BYTES_DEFAULT = 5 * 1024 * 1024
STATE_FILE_MAX_AGE_DAYS_DEFAULT = 7
STATE_REAP_THROTTLE_SECS_DEFAULT = 3600


def env_number(env: Mapping[str, str], name: str, default: float) -> float:
    """``env[name]`` as a number, or ``default`` when unset or not numeric."""
    try:
        return float(env[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class HookSettings:
    """Where state lives and how long a hook may take. Every field has an HC_* override."""

    state_dir: Path
    stdin_timeout_secs: float
    log_max_bytes: int
    state_max_age_days: int
    reap_throttle_secs: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> HookSettings:
        override = env.get("HC_STATE_DIR_OVERRIDE")
        state_dir = Path(override) if override else Path.home() / ".claude" / "hooks" / "state"
        return cls(
            state_dir=state_dir,
            stdin_timeout_secs=env_number(env, "HC_STDIN_TIMEOUT_SECS", STDIN_TIMEOUT_SECS_DEFAULT),
            log_max_bytes=int(
                env_number(env, "HC_HOOKS_LOG_MAX_BYTES", HOOKS_LOG_MAX_BYTES_DEFAULT)
            ),
            state_max_age_days=int(
                env_number(env, "HC_STATE_FILE_MAX_AGE_DAYS", STATE_FILE_MAX_AGE_DAYS_DEFAULT)
            ),
            reap_throttle_secs=int(
                env_number(env, "HC_STATE_REAP_THROTTLE_SECS", STATE_REAP_THROTTLE_SECS_DEFAULT)
            ),
        )
