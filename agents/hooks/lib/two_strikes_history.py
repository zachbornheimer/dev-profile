"""Per-session strike history: a tsv of ``<epoch>\\t<signature>\\t<outcome>``.

Ports the history reading/writing half of two-strikes-gate.sh: whether the
last two recorded outcomes for a signature were both "fail" with no success
between them, and appending a fail entry while pruning ones older than
HISTORY_MAX_AGE_SECS. bash-history-<session>.tsv is written elsewhere (by
bash-signature-record.sh); this hook only ever reads that one and both
reads and writes the edit/work-order deny histories itself.

Reads/writes here fail open on any OSError, matching the shell's own
best-effort `2>/dev/null || true` history handling: a two-strikes gate that
can't see its own history must behave as "no history yet", never crash the
Stop/PreToolUse hook it's inside.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

FAIL_OUTCOME = "fail"
SUCCESS_OUTCOME = "success"
HISTORY_MAX_AGE_SECS = 86400
STRIKES_TO_DENY = 2


def history_two_fails(history: Path, signature: str) -> bool:
    """True when the last two entries for ``signature`` are both fails."""
    if not history.is_file():
        return False
    outcomes = [
        fields[2]
        for line in _read_history_best_effort(history)
        if len(fields := line.split("\t")) >= 3 and fields[1] == signature
    ]
    last_two = outcomes[-STRIKES_TO_DENY:]
    return len(last_two) == STRIKES_TO_DENY and all(outcome == FAIL_OUTCOME for outcome in last_two)


def session_has_edits(state_dir: Path, session_id: str) -> bool:
    edit_counter = state_dir / f"edit-count-{session_id}.txt"
    return edit_counter.is_file() and edit_counter.stat().st_size > 0


def record_fail(history: Path, signature: str, now_epoch: int) -> None:
    """Append a fail entry, pruning ones older than HISTORY_MAX_AGE_SECS.

    Written via a same-directory temp file + atomic replace, mirroring the
    shell's own ``$$``-suffixed-temp-then-mv pattern. Best-effort: an
    OSError here fails open (this call site is never the caller's only
    chance to record — a lost strike just means one denial is forgotten).
    """
    with contextlib.suppress(OSError):
        history.parent.mkdir(parents=True, exist_ok=True)
        cutoff = now_epoch - HISTORY_MAX_AGE_SECS
        kept = [line for line in _read_history_best_effort(history) if _timestamp(line) >= cutoff]
        kept.append(f"{now_epoch}\t{signature}\t{FAIL_OUTCOME}")
        tmp = history.with_suffix(history.suffix + f".tmp.{os.getpid()}")
        tmp.write_text("\n".join(kept) + "\n")
        tmp.replace(history)


def _read_history_best_effort(path: Path) -> list[str]:
    """The history file's non-empty lines, or [] if it can't be read.

    An unreadable history is indistinguishable from "no history yet" to
    every caller here, exactly as `[ -r "$history" ]` treats it in the
    shell original.
    """
    with contextlib.suppress(OSError):
        return [line for line in path.read_text().splitlines() if line]
    return []


def _timestamp(line: str) -> int:
    with contextlib.suppress(ValueError, IndexError):
        return int(line.split("\t", 1)[0])
    return 0
