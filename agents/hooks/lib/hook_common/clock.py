"""Time facades: the wall clock and a file's modification time.

Both carry the same test seams as hook-common.sh (hc_now_iso, hc_file_mtime),
so a fixture pins either without touching the real clock or filesystem.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
FILE_MTIME_OVERRIDE_PREFIX = "HC_FILE_MTIME_OVERRIDE_"
# hc_file_mtime's sanitizer: every byte outside [A-Za-z0-9_] becomes "_",
# so two distinct paths never share one override variable.
OVERRIDE_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_]")


@dataclass(frozen=True, slots=True)
class Clock:
    """Wall-clock facade. HC_NOW_ISO_OVERRIDE pins the logged timestamp for tests."""

    iso_override: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Clock:
        return cls(iso_override=env.get("HC_NOW_ISO_OVERRIDE") or None)

    def now_iso(self) -> str:
        if self.iso_override:
            return self.iso_override
        return datetime.now(timezone.utc).strftime(ISO_FORMAT)

    def now_epoch(self) -> float:
        return time.time()


def file_mtime_override_name(path: Path | str) -> str:
    """The env var that pins ``path``'s mtime: HC_FILE_MTIME_OVERRIDE_<sanitized path>."""
    return FILE_MTIME_OVERRIDE_PREFIX + OVERRIDE_UNSAFE_CHARS.sub("_", str(path))


def file_mtime(path: Path | str, env: Mapping[str, str] = os.environ) -> int | None:
    """``path``'s modification time as epoch seconds; None when missing.

    A non-empty override wins; a non-integer override reads as None, the
    same "unknown" the .sh callers get from a non-numeric hc_file_mtime.
    """
    override = env.get(file_mtime_override_name(path))
    if override:
        return int(override) if override.lstrip("-").isdigit() else None
    try:
        return int(Path(path).stat().st_mtime)
    except OSError:
        return None
