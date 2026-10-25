"""hooks.log: the append-only decision log shared with every shell hook."""

from __future__ import annotations

import contextlib
import os
import stat

from .clock import Clock
from .settings import HookSettings

SECONDS_PER_DAY = 86400
HOOKS_LOG_NAME = "hooks.log"
REAP_THROTTLE_MARKER = ".reap-throttle"
FAIL_OPEN_LOG_DECISION = "allow"


class HookLog:
    """Writes ``<iso>\\t<hook>\\t<decision>\\t<detail>`` lines, exactly as hc_log does.

    Recording also keeps the state dir bounded, as hc_log does: rotate
    hooks.log past its size budget, and (throttled) reap per-session state
    files older than the age budget. All of it is best-effort.
    """

    def __init__(self, hook_name: str, settings: HookSettings, clock: Clock) -> None:
        self._hook_name = hook_name
        self._settings = settings
        self._clock = clock
        self._path = settings.state_dir / HOOKS_LOG_NAME

    def record(self, decision: str, detail: str = "") -> None:
        with contextlib.suppress(OSError):
            self._settings.state_dir.mkdir(parents=True, exist_ok=True)
            self._rotate()
            self._reap_stale_state()
            line = f"{self._clock.now_iso()}\t{self._hook_name}\t{decision}\t{detail}\n"
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def record_fail_open(self, cause: str) -> None:
        self.record(FAIL_OPEN_LOG_DECISION, f"fail-open: {cause}")

    def _rotate(self) -> None:
        with contextlib.suppress(OSError):
            if self._path.stat().st_size > self._settings.log_max_bytes:
                self._path.replace(self._path.with_name(HOOKS_LOG_NAME + ".1"))

    def _reap_stale_state(self) -> None:
        marker = self._settings.state_dir / REAP_THROTTLE_MARKER
        now = self._clock.now_epoch()
        try:
            last = int(marker.read_text().strip())
        except (OSError, ValueError):
            last = 0
        if now - last < self._settings.reap_throttle_secs:
            return
        max_age_secs = self._settings.state_max_age_days * SECONDS_PER_DAY
        for root, _dirs, files in os.walk(self._settings.state_dir):
            for name in files:
                if name.startswith(HOOKS_LOG_NAME):
                    continue
                path = os.path.join(root, name)
                with contextlib.suppress(OSError):
                    info = os.lstat(path)
                    if stat.S_ISREG(info.st_mode) and now - info.st_mtime > max_age_secs:
                        os.unlink(path)
        with contextlib.suppress(OSError):
            marker.write_text(str(int(now)))
