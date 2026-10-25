"""Python side of hook-common.sh's worktree target queue.

work-order-gate enqueues one record per isolation:worktree spawn, keyed by
session id; worktree-provision claims the oldest live record. See
hc_worktree_target_claim in hook-common.sh for the correlation contract.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path

from hook_common import file_mtime

TTL_SECS_DEFAULT = 120
QUEUE_DIR_NAME = "worktree-targets"
RECORD_SUFFIX = ".repo"
WRITING_PREFIX = ".writing."
UNSAFE_SESSION_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def queue_dir(state_dir: Path, session_id: str) -> Path | None:
    safe_id = UNSAFE_SESSION_ID_CHARS.sub("_", session_id)
    return state_dir / QUEUE_DIR_NAME / safe_id if safe_id else None


def _ttl_secs() -> int:
    raw = os.environ.get("HC_WORKTREE_TARGET_TTL_SECS", "")
    return int(raw) if raw.isdigit() else TTL_SECS_DEFAULT


def enqueue(state_dir: Path, session_id: str, record: str, now_epoch: float) -> Path | None:
    """Queue ``record`` atomically (write, then rename); its path, or None if nothing was queued."""
    directory = queue_dir(state_dir, session_id)
    if directory is None:
        return None
    pending = directory / f"{WRITING_PREFIX}{os.getpid()}"
    target = directory / f"{int(now_epoch)}-{os.getpid()}{RECORD_SUFFIX}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        pending.write_text(f"{record}\n")
        pending.rename(target)
    except OSError:
        with contextlib.suppress(OSError):
            pending.unlink()
        return None
    return target


def claim(state_dir: Path, session_id: str, now_epoch: float) -> str | None:
    """The oldest live record ("" = no repo target), or None."""
    directory = queue_dir(state_dir, session_id)
    if directory is None or not directory.is_dir():
        return None
    records = sorted(directory.glob(f"*{RECORD_SUFFIX}"), key=lambda p: p.stat().st_mtime_ns)
    for record in records:
        if now_epoch - (file_mtime(record) or 0) > _ttl_secs():
            with contextlib.suppress(OSError):
                record.unlink()
            continue
        claimed = record.with_name(f"{record.name}.claimed.{os.getpid()}")
        try:
            record.rename(claimed)
        except OSError:
            continue
        repo = claimed.read_text().strip()
        with contextlib.suppress(OSError):
            claimed.unlink()
        return repo
    with contextlib.suppress(OSError):
        directory.rmdir()
    return None
